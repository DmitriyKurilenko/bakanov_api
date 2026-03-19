from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings

from apps.crm.services.amocrm import AmoCRMClient
from apps.integrations.services.metrika_service import YandexMetricaService


def _parse_int_csv(raw: str) -> set[int]:
    values: set[int] = set()
    for token in str(raw or "").replace(";", ",").split(","):
        token = token.strip()
        if token.isdigit():
            values.add(int(token))
    return values


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
        cleaned = "".join(ch for ch in str(raw) if ch.isdigit())
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def _is_client_id_like_field(*, field_name: str, field_code: str) -> bool:
    haystack = f"{field_name} {field_code}".lower()
    hints = ("clientid", "client_id", "client id", "yandex id", "yandex_id", "metrika")
    return any(hint in haystack for hint in hints)


@dataclass
class AmoCrmSpamLeadSyncResult:
    lead_id: int
    status: str
    detail: str = ""
    uploaded_client_ids: int = 0
    uploading: dict | None = None
    sources: list[str] | None = None


@dataclass
class AmoCrmSpamLeadSyncService:
    amocrm: AmoCRMClient
    metrika: YandexMetricaService

    @classmethod
    def from_settings(cls) -> "AmoCrmSpamLeadSyncService":
        return cls(
            amocrm=AmoCRMClient.from_settings(),
            metrika=YandexMetricaService.from_settings(),
        )

    def sync_lead(self, *, lead_id: int) -> AmoCrmSpamLeadSyncResult:
        lead = self.amocrm.get_lead(int(lead_id))
        client_ids, sources = self._extract_client_ids(lead)
        if not client_ids:
            return AmoCrmSpamLeadSyncResult(
                lead_id=int(lead_id),
                status="error",
                detail="No metrika client ids found in lead/contact/company custom fields",
                sources=sources,
            )

        upload_result = self.metrika.upload_spam_client_ids(
            client_ids=client_ids,
            comment=f"amocrm spam lead webhook, lead_id={lead_id}",
        )
        return AmoCrmSpamLeadSyncResult(
            lead_id=int(lead_id),
            status="ok",
            uploaded_client_ids=len(client_ids),
            uploading=upload_result.uploading,
            sources=sources,
        )

    def _extract_client_ids(self, lead: dict) -> tuple[list[str], list[str]]:
        field_ids = _parse_int_csv(getattr(settings, "AMOCRM_SPAM_CLIENT_ID_FIELD_IDS", ""))
        field_codes = _parse_text_csv(getattr(settings, "AMOCRM_SPAM_CLIENT_ID_FIELD_CODES", ""))
        field_names = _parse_text_csv(getattr(settings, "AMOCRM_SPAM_CLIENT_ID_FIELD_NAMES", ""))
        configured_filter = bool(field_ids or field_codes or field_names)

        sources: list[str] = []
        raw_values: list[object] = []

        lead_values = self._extract_raw_values_from_custom_fields(
            custom_fields=lead.get("custom_fields_values") or [],
            field_ids=field_ids,
            field_codes=field_codes,
            field_names=field_names,
            configured_filter=configured_filter,
        )
        if lead_values:
            raw_values.extend(lead_values)
            sources.append("lead")

        for contact_id in self._extract_embedded_entity_ids(lead, entity_key="contacts"):
            contact = self.amocrm.get_contact(contact_id)
            contact_values = self._extract_raw_values_from_custom_fields(
                custom_fields=contact.get("custom_fields_values") or [],
                field_ids=field_ids,
                field_codes=field_codes,
                field_names=field_names,
                configured_filter=configured_filter,
            )
            if contact_values:
                raw_values.extend(contact_values)
                sources.append(f"contact:{contact_id}")

        for company_id in self._extract_embedded_entity_ids(lead, entity_key="companies"):
            company = self.amocrm.get_company(company_id)
            company_values = self._extract_raw_values_from_custom_fields(
                custom_fields=company.get("custom_fields_values") or [],
                field_ids=field_ids,
                field_codes=field_codes,
                field_names=field_names,
                configured_filter=configured_filter,
            )
            if company_values:
                raw_values.extend(company_values)
                sources.append(f"company:{company_id}")

        return _normalize_client_ids(raw_values), sources

    @staticmethod
    def _extract_embedded_entity_ids(lead: dict, *, entity_key: str) -> list[int]:
        embedded = lead.get("_embedded")
        if not isinstance(embedded, dict):
            return []

        entities = embedded.get(entity_key)
        if not isinstance(entities, list):
            return []

        result: list[int] = []
        seen: set[int] = set()
        for item in entities:
            if not isinstance(item, dict):
                continue
            raw_id = item.get("id")
            if isinstance(raw_id, int):
                entity_id = raw_id
            else:
                raw_id_s = str(raw_id).strip()
                if not raw_id_s.isdigit():
                    continue
                entity_id = int(raw_id_s)
            if entity_id in seen:
                continue
            seen.add(entity_id)
            result.append(entity_id)
        return result

    @staticmethod
    def _extract_raw_values_from_custom_fields(
        *,
        custom_fields: list[dict],
        field_ids: set[int],
        field_codes: set[str],
        field_names: set[str],
        configured_filter: bool,
    ) -> list[object]:
        raw_values: list[object] = []

        for field in custom_fields:
            if not isinstance(field, dict):
                continue
            fid = field.get("field_id")
            fid_int = fid if isinstance(fid, int) else int(str(fid).strip()) if str(fid).strip().isdigit() else None
            fcode = str(field.get("field_code") or "").strip().lower()
            fname = str(field.get("field_name") or "").strip().lower()

            if configured_filter:
                match = False
                if isinstance(fid_int, int) and fid_int in field_ids:
                    match = True
                if fcode and fcode in field_codes:
                    match = True
                if fname and fname in field_names:
                    match = True
                if not match:
                    continue
            elif not _is_client_id_like_field(field_name=fname, field_code=fcode):
                continue

            for value_item in field.get("values") or []:
                if isinstance(value_item, dict) and "value" in value_item:
                    raw_values.append(value_item.get("value"))

        return raw_values
