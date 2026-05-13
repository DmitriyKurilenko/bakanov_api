import logging
from dataclasses import dataclass

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass
class Bitrix24Client:
    """Client for Bitrix24 REST API.

    Two modes:
    1. **Webhook mode** — ``webhook_url`` contains auth token.
    2. **OAuth mode** — ``rest_url`` + ``access_token`` (local/server app).
    """

    webhook_url: str = ""
    rest_url: str = ""
    access_token: str = ""
    timeout: int = 30

    @classmethod
    def from_settings(cls) -> "Bitrix24Client":
        webhook_url = getattr(settings, "BITRIX24_WEBHOOK_URL", "")
        if not webhook_url:
            raise ValueError(
                "BITRIX24_WEBHOOK_URL is not configured. "
                "Set it in environment variables."
            )
        timeout = int(getattr(settings, "BITRIX24_TIMEOUT", 30))
        return cls(
            webhook_url=webhook_url.rstrip("/"),
            timeout=timeout,
        )

    @classmethod
    def from_portal(cls, portal: "Bitrix24Portal") -> "Bitrix24Client":  # noqa: F821
        """Create a client backed by OAuth tokens from a portal record."""
        from apps.integrations.services.bitrix24_oauth import ensure_valid_token

        portal = ensure_valid_token(portal)
        return cls(
            rest_url=portal.rest_url.rstrip("/"),
            access_token=portal.access_token,
            timeout=int(getattr(settings, "BITRIX24_TIMEOUT", 30)),
        )

    # ------------------------------------------------------------------
    # Low-level transport
    # ------------------------------------------------------------------

    def _call(
        self,
        method: str,
        params: dict | None = None,
    ) -> dict:
        """Call a Bitrix24 REST method and return the JSON response.

        Bitrix24 REST always returns ``{"result": ...}`` on success and
        ``{"error": "...", "error_description": "..."}`` on failure.
        """
        if self.access_token and self.rest_url:
            url = f"{self.rest_url}/{method}"
            call_params = dict(params or {})
            call_params["auth"] = self.access_token
        else:
            url = f"{self.webhook_url}/{method}"
            call_params = params or {}

        response = requests.post(
            url,
            json=call_params,
            timeout=self.timeout,
        )

        if response.status_code >= 400:
            body_preview = (
                (response.text or "").strip().replace("\n", " ")[:500]
            )
            raise requests.RequestException(
                f"Bitrix24 request failed ({response.status_code}) "
                f"for {method}: {body_preview or 'empty body'}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            body_preview = (
                (response.text or "").strip().replace("\n", " ")[:500]
            )
            raise requests.RequestException(
                f"Bitrix24 returned non-JSON for {method}: "
                f"{body_preview or 'empty body'}"
            ) from exc

        if "error" in payload:
            raise requests.RequestException(
                f"Bitrix24 API error for {method}: "
                f"{payload.get('error')} — "
                f"{payload.get('error_description', '')}"
            )

        return payload

    def _list_all(
        self,
        method: str,
        params: dict | None = None,
        *,
        max_pages: int = 20,
    ) -> list[dict]:
        """Paginate through a Bitrix24 list method.

        Bitrix24 uses ``start`` parameter for pagination (step = 50).
        Each response has ``"next"`` key when more pages are available.
        """
        all_items: list[dict] = []
        query_params = dict(params or {})
        start = 0

        for _ in range(max_pages):
            query_params["start"] = start
            payload = self._call(method, query_params)

            result = payload.get("result")
            if isinstance(result, list):
                all_items.extend(result)
            elif isinstance(result, dict):
                # Some methods return {"tasks": [...]} etc.
                for value in result.values():
                    if isinstance(value, list):
                        all_items.extend(value)
                        break

            next_start = payload.get("next")
            if next_start is None:
                break

            start = int(next_start)

        return all_items

    # ------------------------------------------------------------------
    # CRM: Leads
    # ------------------------------------------------------------------

    def get_lead(self, lead_id: int) -> dict:
        payload = self._call("crm.lead.get", {"ID": lead_id})
        return payload.get("result", {})

    def list_leads(
        self,
        filters: dict | None = None,
        select: list[str] | None = None,
    ) -> list[dict]:
        params: dict = {}
        if filters:
            params["filter"] = filters
        if select:
            params["select"] = select
        return self._list_all("crm.lead.list", params)

    def create_lead(self, fields: dict) -> int:
        payload = self._call("crm.lead.add", {"fields": fields})
        return int(payload["result"])

    def update_lead(self, lead_id: int, fields: dict) -> bool:
        payload = self._call(
            "crm.lead.update",
            {"ID": lead_id, "fields": fields},
        )
        return bool(payload.get("result"))

    def delete_lead(self, lead_id: int) -> bool:
        payload = self._call("crm.lead.delete", {"ID": lead_id})
        return bool(payload.get("result"))

    # ------------------------------------------------------------------
    # CRM: Deals
    # ------------------------------------------------------------------

    def get_deal(self, deal_id: int) -> dict:
        payload = self._call("crm.deal.get", {"ID": deal_id})
        return payload.get("result", {})

    def list_deals(
        self,
        filters: dict | None = None,
        select: list[str] | None = None,
    ) -> list[dict]:
        params: dict = {}
        if filters:
            params["filter"] = filters
        if select:
            params["select"] = select
        return self._list_all("crm.deal.list", params)

    def create_deal(self, fields: dict) -> int:
        payload = self._call("crm.deal.add", {"fields": fields})
        return int(payload["result"])

    def update_deal(self, deal_id: int, fields: dict) -> bool:
        payload = self._call(
            "crm.deal.update",
            {"ID": deal_id, "fields": fields},
        )
        return bool(payload.get("result"))

    def delete_deal(self, deal_id: int) -> bool:
        payload = self._call("crm.deal.delete", {"ID": deal_id})
        return bool(payload.get("result"))

    # ------------------------------------------------------------------
    # CRM: Contacts
    # ------------------------------------------------------------------

    def get_contact(self, contact_id: int) -> dict:
        payload = self._call("crm.contact.get", {"ID": contact_id})
        return payload.get("result", {})

    def list_contacts(
        self,
        filters: dict | None = None,
        select: list[str] | None = None,
    ) -> list[dict]:
        params: dict = {}
        if filters:
            params["filter"] = filters
        if select:
            params["select"] = select
        return self._list_all("crm.contact.list", params)

    def create_contact(self, fields: dict) -> int:
        payload = self._call("crm.contact.add", {"fields": fields})
        return int(payload["result"])

    def update_contact(self, contact_id: int, fields: dict) -> bool:
        payload = self._call(
            "crm.contact.update",
            {"ID": contact_id, "fields": fields},
        )
        return bool(payload.get("result"))

    # ------------------------------------------------------------------
    # CRM: Companies
    # ------------------------------------------------------------------

    def get_company(self, company_id: int) -> dict:
        payload = self._call("crm.company.get", {"ID": company_id})
        return payload.get("result", {})

    def list_companies(
        self,
        filters: dict | None = None,
        select: list[str] | None = None,
    ) -> list[dict]:
        params: dict = {}
        if filters:
            params["filter"] = filters
        if select:
            params["select"] = select
        return self._list_all("crm.company.list", params)

    def create_company(self, fields: dict) -> int:
        payload = self._call("crm.company.add", {"fields": fields})
        return int(payload["result"])

    def update_company(self, company_id: int, fields: dict) -> bool:
        payload = self._call(
            "crm.company.update",
            {"ID": company_id, "fields": fields},
        )
        return bool(payload.get("result"))
