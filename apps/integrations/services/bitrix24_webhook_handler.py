import logging
from dataclasses import dataclass, field

import requests
from django.conf import settings

from apps.integrations.services.bitrix24_service import Bitrix24Client

logger = logging.getLogger(__name__)

# Bitrix24 CRM event types we handle.
LEAD_EVENTS = frozenset({
    "ONCRMLEADADD",
    "ONCRMLEADUPDATE",
    "ONCRMLEADDELETE",
})
DEAL_EVENTS = frozenset({
    "ONCRMDEALDD",
    "ONCRMDEALUPDATE",
    "ONCRMDEALDELETE",
})
CONTACT_EVENTS = frozenset({
    "ONCRMCONTACTADD",
    "ONCRMCONTACTUPDATE",
    "ONCRMCONTACTDELETE",
})
ALL_KNOWN_EVENTS = LEAD_EVENTS | DEAL_EVENTS | CONTACT_EVENTS


@dataclass
class Bitrix24WebhookResult:
    """Result of processing a single incoming Bitrix24 webhook."""

    event: str
    entity_id: int | None = None
    status: str = "ok"
    detail: str = ""
    entity_data: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "event": self.event,
            "entity_id": self.entity_id,
            "status": self.status,
            "detail": self.detail,
        }


def verify_inbound_token(token: str) -> bool:
    """Check that the inbound webhook token matches the configured one."""
    expected = getattr(settings, "BITRIX24_INBOUND_TOKEN", "")
    if not expected:
        logger.warning(
            "BITRIX24_INBOUND_TOKEN is not configured; "
            "rejecting all inbound webhooks."
        )
        return False
    return token == expected


def extract_webhook_payload(data: dict) -> tuple[str, int | None, str]:
    """Extract event type, entity ID, and auth token from Bitrix24 webhook.

    Bitrix24 sends POST with form-encoded or JSON body:
        event=ONCRMLEADADD
        data[FIELDS][ID]=123
        auth[application_token]=secret
    """
    event = str(data.get("event", "")).strip().upper()

    entity_id: int | None = None
    fields = data.get("data[FIELDS][ID]") or data.get("data", {})
    if isinstance(fields, dict):
        inner = fields.get("FIELDS", {})
        if isinstance(inner, dict):
            raw_id = inner.get("ID")
        else:
            raw_id = None
    else:
        raw_id = fields

    if raw_id is not None:
        raw_str = str(raw_id).strip()
        if raw_str.isdigit():
            entity_id = int(raw_str)

    auth = data.get("auth[application_token]") or data.get("auth", {})
    if isinstance(auth, dict):
        token = str(auth.get("application_token", "")).strip()
    else:
        token = str(auth).strip()

    return event, entity_id, token


@dataclass
class Bitrix24WebhookProcessor:
    """Process incoming Bitrix24 webhook events.

    Fetches entity data from Bitrix24 API so tasks can work
    with a full snapshot rather than just the ID.
    """

    client: Bitrix24Client | None = None

    def _ensure_client(self) -> Bitrix24Client:
        if self.client is None:
            self.client = Bitrix24Client.from_settings()
        return self.client

    def process(
        self,
        event: str,
        entity_id: int | None,
    ) -> Bitrix24WebhookResult:
        if not event:
            return Bitrix24WebhookResult(
                event="",
                status="error",
                detail="Missing event type",
            )

        if event not in ALL_KNOWN_EVENTS:
            logger.info("Bitrix24 webhook: unhandled event %s", event)
            return Bitrix24WebhookResult(
                event=event,
                entity_id=entity_id,
                status="skipped",
                detail=f"Unhandled event type: {event}",
            )

        if entity_id is None:
            return Bitrix24WebhookResult(
                event=event,
                status="error",
                detail="Missing entity ID",
            )

        # For delete events we don't fetch — entity no longer exists.
        if event.endswith("DELETE"):
            logger.info(
                "Bitrix24 webhook: %s entity_id=%s (delete — no fetch)",
                event,
                entity_id,
            )
            return Bitrix24WebhookResult(
                event=event,
                entity_id=entity_id,
                status="ok",
                detail="Delete event received",
            )

        entity_data = self._fetch_entity(event, entity_id)
        return Bitrix24WebhookResult(
            event=event,
            entity_id=entity_id,
            status="ok",
            entity_data=entity_data,
        )

    def _fetch_entity(self, event: str, entity_id: int) -> dict:
        client = self._ensure_client()
        try:
            if event in LEAD_EVENTS:
                return client.get_lead(entity_id)
            if event in DEAL_EVENTS:
                return client.get_deal(entity_id)
            if event in CONTACT_EVENTS:
                return client.get_contact(entity_id)
        except requests.RequestException:
            # Transient/transport error (rate limit, network, Bitrix 5xx,
            # revoked token).  Propagate so the Celery task retries instead
            # of silently treating the entity as "no data" and dropping the
            # downstream spam-conversion upload.
            logger.warning(
                "Bitrix24: transient fetch error for %s id=%s — will retry",
                event,
                entity_id,
            )
            raise
        except Exception:
            # Unexpected non-transport error: don't poison generic webhook
            # processing, but make it loud in logs.
            logger.exception(
                "Bitrix24: unexpected error fetching entity for %s id=%s",
                event,
                entity_id,
            )
        return {}
