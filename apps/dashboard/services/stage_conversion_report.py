from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Iterable

from apps.crm.services.amocrm import AmoCRMClient


@dataclass
class StageConversionFilters:
    date_from: date
    date_to: date
    manager_ids: list[int]
    pipeline_id: int | None


class StageConversionReportService:
    def __init__(self, amocrm: AmoCRMClient | None = None) -> None:
        self.amocrm = amocrm or AmoCRMClient.from_settings()

    def build_report(self, filters: StageConversionFilters) -> dict:
        created_from, created_to = self._to_unix_range(filters.date_from, filters.date_to)
        pipelines = self._safe_list_pipelines()

        effective_pipeline_id = filters.pipeline_id
        if effective_pipeline_id is None and pipelines:
            first_pipeline_id = pipelines[0].get("id")
            if first_pipeline_id is not None:
                effective_pipeline_id = int(first_pipeline_id)

        users = self._safe_list_users()
        managers = [
            {
                "id": int(user["id"]),
                "name": user.get("name") or str(user["id"]),
            }
            for user in users
            if user.get("id") is not None
        ]

        statuses = self._pipeline_statuses(pipelines, effective_pipeline_id)
        if effective_pipeline_id is None or not statuses:
            return {
                "filters": {
                    "date_from": filters.date_from.isoformat(),
                    "date_to": filters.date_to.isoformat(),
                    "manager_ids": filters.manager_ids,
                    "pipeline_id": effective_pipeline_id,
                },
                "summary": {
                    "transitions_total": 0,
                    "realized_total": 0,
                },
                "pipelines": self._serialize_pipelines(pipelines),
                "managers": managers,
                "stages": [],
            }

        events = self._load_pipeline_status_change_events(
            created_from=created_from,
            created_to=created_to,
            manager_ids=filters.manager_ids,
            pipeline_id=effective_pipeline_id,
            statuses=statuses,
        )

        entered_by_stage: dict[int, int] = {int(stage["id"]): 0 for stage in statuses}
        for event in events:
            stage_id = self._event_stage_id(event)
            if stage_id is None:
                continue
            if stage_id in entered_by_stage:
                entered_by_stage[stage_id] += 1

        success_stage_ids = self._success_stage_ids(statuses)
        realized_total = sum(entered_by_stage.get(stage_id, 0) for stage_id in success_stage_ids)

        stages_payload: list[dict] = []
        for stage in statuses:
            stage_id = int(stage["id"])
            entered_count = entered_by_stage.get(stage_id, 0)
            conversion = round((realized_total / entered_count) * 100, 2) if entered_count else 0.0
            stages_payload.append(
                {
                    "stage_id": stage_id,
                    "stage_name": stage.get("name") or f"Этап {stage_id}",
                    "entered_count": entered_count,
                    "conversion_to_realized_percent": conversion,
                    "is_success": stage_id in success_stage_ids,
                }
            )

        return {
            "filters": {
                "date_from": filters.date_from.isoformat(),
                "date_to": filters.date_to.isoformat(),
                "manager_ids": filters.manager_ids,
                "pipeline_id": effective_pipeline_id,
            },
            "summary": {
                "transitions_total": len(events),
                "realized_total": realized_total,
            },
            "pipelines": self._serialize_pipelines(pipelines),
            "managers": managers,
            "stages": stages_payload,
        }

    def _safe_list_pipelines(self) -> list[dict]:
        try:
            return self.amocrm.list_lead_pipelines()
        except Exception:
            return []

    def _safe_list_users(self) -> list[dict]:
        try:
            return self.amocrm.list_users()
        except Exception:
            return []

    def _pipeline_statuses(self, pipelines: list[dict], pipeline_id: int | None) -> list[dict]:
        if pipeline_id is None:
            return []

        for pipeline in pipelines:
            current_pipeline_id = pipeline.get("id")
            if current_pipeline_id is None or int(current_pipeline_id) != pipeline_id:
                continue
            return [stage for stage in pipeline.get("_embedded", {}).get("statuses", []) if stage.get("id") is not None]

        return []

    def _load_pipeline_status_change_events(
        self,
        *,
        created_from: int,
        created_to: int,
        manager_ids: list[int],
        pipeline_id: int,
        statuses: list[dict],
    ) -> list[dict]:
        base_params: list[tuple[str, str | int]] = [
            ("filter[entity][]", "lead"),
            ("filter[type][]", "lead_status_changed"),
            ("filter[created_at][from]", created_from),
            ("filter[created_at][to]", created_to),
        ]

        for index, status in enumerate(statuses):
            status_id = status.get("id")
            if status_id is None:
                continue
            base_params.append((f"filter[value_after][leads_statuses][{index}][pipeline_id]", pipeline_id))
            base_params.append((f"filter[value_after][leads_statuses][{index}][status_id]", int(status_id)))

        if not manager_ids:
            return self._safe_list_events(params=base_params)

        events: list[dict] = []
        for chunk in self._chunked(manager_ids, 10):
            params = list(base_params)
            for manager_id in chunk:
                params.append(("filter[created_by][]", manager_id))
            events.extend(self._safe_list_events(params=params))

        return events

    def _safe_list_events(self, *, params: list[tuple[str, str | int]]) -> list[dict]:
        try:
            return self.amocrm.list_events(params=params)
        except Exception:
            return []

    def _event_stage_id(self, event: dict) -> int | None:
        value_after = event.get("value_after") or []
        if not value_after:
            return None
        lead_status = value_after[0].get("lead_status") if isinstance(value_after[0], dict) else None
        if not isinstance(lead_status, dict):
            return None
        stage_id = lead_status.get("id")
        if stage_id is None:
            return None
        return int(stage_id)

    def _success_stage_ids(self, statuses: list[dict]) -> set[int]:
        success_ids: set[int] = set()
        for status in statuses:
            status_id = status.get("id")
            if status_id is None:
                continue
            if self._is_success_status(status):
                success_ids.add(int(status_id))
        if not success_ids:
            for status in statuses:
                status_id = status.get("id")
                if status_id is None:
                    continue
                if int(status_id) == 142:
                    success_ids.add(142)
        return success_ids

    def _is_success_status(self, status: dict) -> bool:
        status_id = status.get("id")
        status_type = status.get("type")
        status_name = (status.get("name") or "").lower()

        if status_id == 142:
            return True
        if status_type in {1, "1", "success", "won", "closed_won"}:
            return True
        if "успеш" in status_name or "success" in status_name:
            return True
        return False

    def _serialize_pipelines(self, pipelines: list[dict]) -> list[dict]:
        serialized: list[dict] = []
        for pipeline in pipelines:
            pipeline_id = pipeline.get("id")
            if pipeline_id is None:
                continue

            statuses_payload: list[dict] = []
            for status in pipeline.get("_embedded", {}).get("statuses", []):
                status_id = status.get("id")
                if status_id is None:
                    continue
                statuses_payload.append(
                    {
                        "id": int(status_id),
                        "name": status.get("name") or f"Этап {status_id}",
                    }
                )

            serialized.append(
                {
                    "id": int(pipeline_id),
                    "name": pipeline.get("name") or f"Воронка {pipeline_id}",
                    "statuses": statuses_payload,
                }
            )

        return serialized

    def _to_unix_range(self, date_from: date, date_to: date) -> tuple[int, int]:
        dt_from = datetime.combine(date_from, time.min)
        dt_to = datetime.combine(date_to, time.max)
        return int(dt_from.timestamp()), int(dt_to.timestamp())

    def _chunked(self, source: Iterable[int], size: int) -> list[list[int]]:
        chunk: list[int] = []
        chunks: list[list[int]] = []

        for item in source:
            chunk.append(item)
            if len(chunk) == size:
                chunks.append(chunk)
                chunk = []

        if chunk:
            chunks.append(chunk)

        return chunks
