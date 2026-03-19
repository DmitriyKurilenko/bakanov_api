from dataclasses import dataclass
from pathlib import Path
import mimetypes

import requests
from django.conf import settings


@dataclass
class AmoCRMClient:
    base_url: str
    access_token: str
    dashboard_timeout: int = 6

    @classmethod
    def from_settings(cls) -> "AmoCRMClient":
        base_url = settings.AMOCRM_BASE_URL.rstrip("/")
        if base_url.endswith("/api/v4"):
            base_url = base_url[: -len("/api/v4")]
        dashboard_timeout = int(getattr(settings, "AMOCRM_DASHBOARD_TIMEOUT", 6))
        return cls(
            base_url=base_url,
            access_token=settings.AMOCRM_ACCESS_TOKEN,
            dashboard_timeout=dashboard_timeout,
        )

    @property
    def api_v4_url(self) -> str:
        return f"{self.base_url}/api/v4"

    @property
    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        params: list[tuple[str, str | int]] | None = None,
        headers: dict | None = None,
        json_data: dict | list | None = None,
        data: bytes | None = None,
        timeout: int = 30,
    ) -> dict:
        response = requests.request(
            method=method,
            url=url,
            headers=headers or self.headers,
            params=params,
            json=json_data,
            data=data,
            timeout=timeout,
        )

        if response.status_code >= 400:
            body_preview = (response.text or "").strip().replace("\n", " ")[:500]
            raise requests.RequestException(
                f"AmoCRM request failed ({response.status_code}) for {method} {url}: {body_preview or 'empty body'}"
            )

        if not response.content:
            raise requests.RequestException(f"AmoCRM returned empty response for {method} {url}")

        try:
            return response.json()
        except ValueError as exc:
            body_preview = (response.text or "").strip().replace("\n", " ")[:500]
            raise requests.RequestException(
                f"AmoCRM returned non-JSON response for {method} {url}: {body_preview or 'empty body'}"
            ) from exc

    def _get_paginated(
        self,
        endpoint: str,
        embedded_key: str,
        params: list[tuple[str, str | int]] | None = None,
        *,
        max_pages: int = 10,
    ) -> list[dict]:
        page = 1
        items: list[dict] = []

        while page <= max_pages:
            query_params = list(params or [])
            query_params.append(("page", page))
            query_params.append(("limit", 250))

            response = requests.get(
                f"{self.api_v4_url}{endpoint}",
                headers=self.headers,
                params=query_params,
                timeout=self.dashboard_timeout,
            )
            if response.status_code >= 400:
                body_preview = (response.text or "").strip().replace("\n", " ")[:500]
                raise requests.RequestException(
                    f"AmoCRM pagination request failed ({response.status_code}) for GET {self.api_v4_url}{endpoint}: {body_preview or 'empty body'}"
                )

            if not response.content:
                break

            try:
                payload = response.json()
            except ValueError:
                body_preview = (response.text or "").strip().replace("\n", " ")[:500]
                raise requests.RequestException(
                    f"AmoCRM pagination returned non-JSON for GET {self.api_v4_url}{endpoint}: {body_preview or 'empty body'}"
                )

            chunk = payload.get("_embedded", {}).get(embedded_key, [])
            if not chunk:
                break

            items.extend(chunk)

            links = payload.get("_links", {})
            if "next" not in links:
                break

            page += 1

        return items

    def get_lead(self, lead_id: int) -> dict:
        return self._request_json(
            "GET",
            f"{self.api_v4_url}/leads/{lead_id}?with=contacts,companies",
            timeout=20,
        )

    def get_contact(self, contact_id: int) -> dict:
        return self._request_json("GET", f"{self.api_v4_url}/contacts/{contact_id}", timeout=20)

    def get_company(self, company_id: int) -> dict:
        return self._request_json("GET", f"{self.api_v4_url}/companies/{company_id}", timeout=20)

    def list_users(self) -> list[dict]:
        try:
            payload = self._request_json("GET", f"{self.api_v4_url}/users", timeout=self.dashboard_timeout)
            return payload.get("_embedded", {}).get("users", [])
        except requests.RequestException:
            payload = self._request_json("GET", f"{self.api_v4_url}/account?with=users", timeout=self.dashboard_timeout)
            embedded = payload.get("_embedded", {})
            return embedded.get("users", [])

    def list_leads(self, params: list[tuple[str, str | int]] | None = None) -> list[dict]:
        return self._get_paginated("/leads", "leads", params=params, max_pages=10)

    def list_events(self, params: list[tuple[str, str | int]] | None = None) -> list[dict]:
        return self._get_paginated("/events", "events", params=params, max_pages=12)

    def list_lead_pipelines(self) -> list[dict]:
        return self._get_paginated(
            "/leads/pipelines",
            "pipelines",
            params=[("with", "statuses")],
            max_pages=3,
        )

    def update_lead_responsible(self, lead_id: int, responsible_user_id: int) -> None:
        payload = [{"id": lead_id, "responsible_user_id": responsible_user_id}]
        self._request_json(
            "PATCH",
            f"{self.api_v4_url}/leads",
            json_data=payload,
            timeout=20,
        )

    def upload_contract_link(self, lead_id: int, file_url: str) -> None:
        payload = [{"id": lead_id, "custom_fields_values": [{"field_code": "CONTRACT_URL", "values": [{"value": file_url}]}]}]
        self._request_json(
            "PATCH",
            f"{self.api_v4_url}/leads",
            json_data=payload,
            timeout=20,
        )

    def get_drive_url(self) -> str:
        payload = self._request_json("GET", f"{self.api_v4_url}/account?with=drive_url", timeout=20)
        drive_url = payload.get("drive_url")
        if not drive_url:
            raise requests.RequestException("AmoCRM drive_url is not available")
        return drive_url.rstrip("/")

    def upload_file_to_lead_field(self, lead_id: int, file_path: Path, field_id: int) -> str:
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        drive_url = self.get_drive_url()
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        file_size = file_path.stat().st_size

        session_payload = {
            "file_name": file_path.name,
            "file_size": int(file_size),
            "content_type": content_type,
        }

        session_payload_response = self._request_json(
            "POST",
            f"{drive_url}/v1.0/sessions",
            json_data=session_payload,
            timeout=30,
        )
        upload_url = session_payload_response.get("upload_url")
        if not upload_url:
            raise requests.RequestException("AmoCRM upload_url was not returned")

        upload_headers = {"Content-Type": content_type}
        with file_path.open("rb") as source:
            upload_payload = self._request_json(
                "POST",
                upload_url,
                headers=upload_headers,
                data=source.read(),
                timeout=120,
            )

        while upload_payload.get("next_url"):
            with file_path.open("rb") as source:
                upload_payload = self._request_json(
                    "POST",
                    upload_payload["next_url"],
                    headers=upload_headers,
                    data=source.read(),
                    timeout=120,
                )

        file_uuid = upload_payload.get("uuid")
        if not file_uuid:
            raise requests.RequestException("AmoCRM file uuid was not returned")

        patch_payload = {
            "custom_fields_values": [
                {
                    "field_id": int(field_id),
                    "values": [{"value": {"file_uuid": file_uuid}}],
                }
            ]
        }
        self._request_json(
            "PATCH",
            f"{self.api_v4_url}/leads/{lead_id}",
            json_data=patch_payload,
            timeout=30,
        )
        return file_uuid
