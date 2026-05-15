from __future__ import annotations

from dataclasses import dataclass
import logging
import time

import requests
from django.conf import settings

from apps.integrations.services.bitrix24_service import Bitrix24Client
from apps.integrations.services.metrika_service import YandexMetricaService

logger = logging.getLogger(__name__)


def _parse_text_csv(raw: str) -> set[str]:
    values: set[str] = set()
    for token in str(raw or "").replace(";", ",").split(","):
        token = token.strip()
        if token:
            values.add(token.lower())
    return values


def _normalize_client_ids(raw_values: list[object]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        if raw is None:
            continue
        value = str(raw).strip()
        if not value.isdigit() or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _is_client_id_like_field(*, field_name: str) -> bool:
    haystack = field_name.lower()
    hints = ("clientid", "client_id", "client id", "yandex id", "yandex_id", "metrika")
    return any(hint in haystack for hint in hints)


@dataclass
class Bitrix24SpamLeadSyncResult:
    entity_id: int
    entity_type: str
    status: str
    detail: str = ""
    uploaded_client_ids: int = 0
    uploading: dict | None = None
    sources: list[str] | None = None


@dataclass
class Bitrix24SpamLeadSyncService:
    """Extract ClientId from Bitrix24 CRM entities and upload to Yandex.Metrica.

    Searches custom fields (UF_CRM_*) on the entity, then on linked
    contact/company.  Matching is controlled by env variables or falls
    back to heuristics.
    """

    client: Bitrix24Client
    metrika: YandexMetricaService

    @classmethod
    def from_settings(cls) -> "Bitrix24SpamLeadSyncService":
        return cls(
            client=Bitrix24Client.from_settings(),
            metrika=YandexMetricaService.from_settings(),
        )

    def sync_entity(
        self,
        *,
        entity_id: int,
        entity_type: str,
    ) -> Bitrix24SpamLeadSyncResult:
        entity_type = str(entity_type or "").strip().lower()
        if entity_type not in {"lead", "deal"}:
            return Bitrix24SpamLeadSyncResult(
                entity_id=entity_id,
                entity_type=entity_type,
                status="error",
                detail=f"Unsupported entity type: {entity_type}",
            )

        entity = self._fetch_entity(entity_type, entity_id)
        if not entity:
            return Bitrix24SpamLeadSyncResult(
                entity_id=entity_id,
                entity_type=entity_type,
                status="error",
                detail=f"Entity not found: {entity_type} id={entity_id}",
            )

        client_ids, sources = self._extract_client_ids(entity, entity_type=entity_type)
        if not client_ids:
            return Bitrix24SpamLeadSyncResult(
                entity_id=entity_id,
                entity_type=entity_type,
                status="error",
                detail="No metrika client ids found in entity/contact/company custom fields",
                sources=sources,
            )

        conversion_timestamp = self._resolve_conversion_timestamp(entity)
        upload_result = self.metrika.upload_spam_client_ids(
            client_ids=client_ids,
            conversion_timestamp=conversion_timestamp,
            comment=f"bitrix24 spam {entity_type} webhook, {entity_type}_id={entity_id}",
        )
        return Bitrix24SpamLeadSyncResult(
            entity_id=entity_id,
            entity_type=entity_type,
            status="ok",
            uploaded_client_ids=len(client_ids),
            uploading=upload_result.uploading,
            sources=sources,
        )

    def _fetch_entity(self, entity_type: str, entity_id: int) -> dict:
        try:
            if entity_type == "lead":
                result = self.client.get_lead(entity_id)
            elif entity_type == "deal":
                result = self.client.get_deal(entity_id)
            else:
                result = {}
            if isinstance(result, dict):
                uf_keys = [k for k in result.keys() if isinstance(k, str) and k.startswith("UF_CRM_")]
                logger.info(
                    "Bitrix24 spam: fetched %s id=%s keys=%s uf_fields=%s",
                    entity_type,
                    entity_id,
                    list(result.keys()),
                    uf_keys,
                )
            return result
        except requests.RequestException:
            # Transient Bitrix error — propagate so the Celery task retries
            # rather than mis-reporting the entity as "not found" and
            # permanently losing the conversion.
            logger.warning(
                "Bitrix24 spam: transient fetch error for %s id=%s — will retry",
                entity_type,
                entity_id,
            )
            raise
        except Exception:
            logger.exception(
                "Bitrix24 spam: unexpected error fetching %s id=%s",
                entity_type,
                entity_id,
            )
            return {}

    def _fetch_contact(self, contact_id: int) -> dict:
        try:
            return self.client.get_contact(contact_id)
        except requests.RequestException:
            logger.warning(
                "Bitrix24 spam: transient fetch error for contact id=%s — will retry",
                contact_id,
            )
            raise
        except Exception:
            logger.exception("Bitrix24 spam: unexpected error fetching contact id=%s", contact_id)
            return {}

    def _fetch_company(self, company_id: int) -> dict:
        try:
            return self.client.get_company(company_id)
        except requests.RequestException:
            logger.warning(
                "Bitrix24 spam: transient fetch error for company id=%s — will retry",
                company_id,
            )
            raise
        except Exception:
            logger.exception("Bitrix24 spam: unexpected error fetching company id=%s", company_id)
            return {}

    @staticmethod
    def _resolve_conversion_timestamp(entity: dict) -> int:
        now_ts = int(time.time())
        raw_created = entity.get("DATE_CREATE") or entity.get("DATE_CREATE_SHORT")
        if raw_created:
            try:
                from datetime import datetime
                for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                    try:
                        dt = datetime.strptime(str(raw_created).strip(), fmt)
                        return int(dt.timestamp())
                    except ValueError:
                        continue
            except Exception:
                pass
        return now_ts

    def _extract_client_ids(
        self,
        entity: dict,
        *,
        entity_type: str,
    ) -> tuple[list[str], list[str]]:
        field_codes = _parse_text_csv(getattr(settings, "BITRIX24_SPAM_CLIENT_ID_FIELD_CODES", ""))
        field_names = _parse_text_csv(getattr(settings, "BITRIX24_SPAM_CLIENT_ID_FIELD_NAMES", ""))
        configured_filter = bool(field_codes or field_names)

        sources: list[str] = []
        raw_values: list[object] = []

        entity_values = self._extract_raw_values_from_fields(
            fields=entity,
            field_codes=field_codes,
            field_names=field_names,
            configured_filter=configured_filter,
        )
        if entity_values:
            raw_values.extend(entity_values)
            sources.append(entity_type)
            logger.info(
                "Bitrix24 spam: found values in %s: %s (codes=%s names=%s configured=%s)",
                entity_type,
                entity_values,
                field_codes,
                field_names,
                configured_filter,
            )

        contact_ids = self._extract_linked_contact_ids(entity)
        for contact_id in contact_ids:
            contact = self._fetch_contact(contact_id)
            if not contact:
                continue
            contact_values = self._extract_raw_values_from_fields(
                fields=contact,
                field_codes=field_codes,
                field_names=field_names,
                configured_filter=configured_filter,
            )
            if contact_values:
                raw_values.extend(contact_values)
                sources.append(f"contact:{contact_id}")

        company_ids = self._extract_linked_company_ids(entity)
        for company_id in company_ids:
            company = self._fetch_company(company_id)
            if not company:
                continue
            company_values = self._extract_raw_values_from_fields(
                fields=company,
                field_codes=field_codes,
                field_names=field_names,
                configured_filter=configured_filter,
            )
            if company_values:
                raw_values.extend(company_values)
                sources.append(f"company:{company_id}")

        return _normalize_client_ids(raw_values), sources

    @staticmethod
    def _extract_linked_contact_ids(entity: dict) -> list[int]:
        ids: set[int] = set()
        raw = entity.get("CONTACT_ID")
        if isinstance(raw, int) and raw > 0:
            ids.add(raw)
        elif isinstance(raw, str) and raw.isdigit():
            ids.add(int(raw))

        raw_ids = entity.get("CONTACT_IDS")
        if isinstance(raw_ids, list):
            for item in raw_ids:
                if isinstance(item, int) and item > 0:
                    ids.add(item)
                elif isinstance(item, str) and item.isdigit():
                    ids.add(int(item))
                elif isinstance(item, dict):
                    cid = item.get("CONTACT_ID") or item.get("ID")
                    if isinstance(cid, int) and cid > 0:
                        ids.add(cid)
                    elif isinstance(cid, str) and cid.isdigit():
                        ids.add(int(cid))
        return list(ids)

    @staticmethod
    def _extract_linked_company_ids(entity: dict) -> list[int]:
        ids: set[int] = set()
        raw = entity.get("COMPANY_ID")
        if isinstance(raw, int) and raw > 0:
            ids.add(raw)
        elif isinstance(raw, str) and raw.isdigit():
            ids.add(int(raw))
        return list(ids)

    @staticmethod
    def _extract_raw_values_from_fields(
        *,
        fields: dict,
        field_codes: set[str],
        field_names: set[str],
        configured_filter: bool,
    ) -> list[object]:
        raw_values: list[object] = []
        if not isinstance(fields, dict):
            return raw_values

        for key, value in fields.items():
            if not isinstance(key, str):
                continue
            key_lower = key.lower()

            if not key_lower.startswith("uf_crm_"):
                continue

            if configured_filter:
                match = False
                if key_lower in field_codes:
                    match = True
                if not match:
                    continue
            elif not _is_client_id_like_field(field_name=key_lower):
                continue

            if value is None:
                continue
            if isinstance(value, list):
                raw_values.extend(value)
            else:
                raw_values.append(value)

        return raw_values
