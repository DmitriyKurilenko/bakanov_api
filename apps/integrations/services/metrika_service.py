from __future__ import annotations

from dataclasses import dataclass
import csv
import io
import logging
import time

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass
class OfflineConversionsUploadResult:
    uploading: dict

    @property
    def id(self) -> int | None:
        raw = self.uploading.get("id")
        return int(raw) if isinstance(raw, int) else None

    @property
    def status(self) -> str:
        return str(self.uploading.get("status") or "")

    @property
    def source_quantity(self) -> int:
        raw = self.uploading.get("source_quantity")
        return int(raw) if isinstance(raw, int) else 0

    @property
    def linked_quantity(self) -> int:
        raw = self.uploading.get("linked_quantity")
        return int(raw) if isinstance(raw, int) else 0


@dataclass
class YandexMetricaService:
    token: str
    counter_id: int
    spam_goal_id: str
    upload_type: str = "BASIC"
    base_url: str = "https://api-metrika.yandex.net"
    timeout: float = 30.0
    _resolved_target_cache: str | None = None

    @classmethod
    def from_settings(cls) -> "YandexMetricaService":
        return cls(
            token=str(getattr(settings, "YANDEX_METRIKA_TOKEN", "") or "").strip(),
            counter_id=int(getattr(settings, "YANDEX_METRIKA_COUNTER_ID", 0) or 0),
            spam_goal_id=str(getattr(settings, "YANDEX_METRIKA_OFFLINE_GOAL_ID", "") or "").strip(),
            upload_type=str(getattr(settings, "YANDEX_METRIKA_UPLOAD_TYPE", "BASIC") or "BASIC").strip().upper(),
        )

    def upload_spam_client_ids(
        self,
        *,
        client_ids: list[str],
        conversion_timestamp: int | None = None,
        comment: str = "",
    ) -> OfflineConversionsUploadResult:
        if not self.token:
            raise ValueError("YANDEX_METRIKA_TOKEN is not configured")
        if self.counter_id <= 0:
            raise ValueError("YANDEX_METRIKA_COUNTER_ID is not configured")
        if not self.spam_goal_id:
            raise ValueError("YANDEX_METRIKA_OFFLINE_GOAL_ID is not configured")
        if not client_ids:
            raise ValueError("client_ids is empty")

        ts = int(conversion_timestamp or int(time.time()))
        target = self._resolve_target_identifier()
        csv_payload = self._build_csv(client_ids=client_ids, goal_id=target, conversion_timestamp=ts)

        url = f"{self.base_url.rstrip('/')}/management/v1/counter/{self.counter_id}/offline_conversions/upload"
        headers = {
            "Authorization": f"OAuth {self.token}",
        }
        params = {"type": self.upload_type}
        if comment.strip():
            params["comment"] = comment.strip()[:255]

        files = {
            "file": ("offline_conversions.csv", csv_payload.encode("utf-8"), "text/csv"),
        }
        response = requests.post(
            url,
            headers=headers,
            params=params,
            files=files,
            timeout=self.timeout,
        )

        body_text = (response.text or "").strip()
        try:
            payload = response.json()
        except ValueError:
            payload = {}

        if response.status_code >= 400:
            details = body_text[:1000]
            raise requests.RequestException(f"Metrica API returned {response.status_code}: {details}")

        uploading = payload.get("uploading") if isinstance(payload, dict) else None
        if not isinstance(uploading, dict):
            raise requests.RequestException("Metrica API returned unexpected payload: 'uploading' not found")

        return OfflineConversionsUploadResult(uploading=uploading)

    def _resolve_target_identifier(self) -> str:
        raw_target = str(self.spam_goal_id or "").strip()
        if not raw_target:
            return raw_target
        if not raw_target.isdigit():
            return raw_target
        if self._resolved_target_cache is not None:
            return self._resolved_target_cache

        resolved = raw_target
        goals_url = f"{self.base_url.rstrip('/')}/management/v1/counter/{self.counter_id}/goals"
        headers = {"Authorization": f"OAuth {self.token}"}

        try:
            response = requests.get(goals_url, headers=headers, timeout=self.timeout)
            if response.status_code >= 400:
                logger.warning(
                    "Metrica goals lookup failed (%s), using numeric target=%s",
                    response.status_code,
                    raw_target,
                )
                self._resolved_target_cache = resolved
                return resolved

            payload = response.json() if response.content else {}
            goals = payload.get("goals") if isinstance(payload, dict) else None
            if not isinstance(goals, list):
                self._resolved_target_cache = resolved
                return resolved

            goal = next((item for item in goals if str(item.get("id")) == raw_target), None)
            if not isinstance(goal, dict):
                self._resolved_target_cache = resolved
                return resolved

            if str(goal.get("type") or "").lower() == "action":
                for condition in goal.get("conditions") or []:
                    if not isinstance(condition, dict):
                        continue
                    identifier = str(condition.get("url") or "").strip()
                    if identifier:
                        resolved = identifier
                        break
        except requests.RequestException as exc:
            logger.warning("Metrica goals lookup request failed, using numeric target=%s: %s", raw_target, exc)
        except ValueError as exc:
            logger.warning("Metrica goals lookup JSON parse failed, using numeric target=%s: %s", raw_target, exc)

        self._resolved_target_cache = resolved
        return resolved

    @staticmethod
    def _build_csv(*, client_ids: list[str], goal_id: str, conversion_timestamp: int) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(["ClientId", "Target", "DateTime"])
        for cid in client_ids:
            writer.writerow([cid, goal_id, str(conversion_timestamp)])
        return buf.getvalue()
