from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Iterable

from apps.crm.services.amocrm import AmoCRMClient


@dataclass
class RopReportFilters:
    date_from: date
    date_to: date
    manager_ids: list[int]
    pipeline_id: int | None
    stage_status_id: int | None


class RopReportService:
    def __init__(self, amocrm: AmoCRMClient | None = None) -> None:
        self.amocrm = amocrm or AmoCRMClient.from_settings()

    def build_report(self, filters: RopReportFilters) -> dict:
        created_from, created_to = self._to_unix_range(filters.date_from, filters.date_to)
        pipelines = self._safe_list_pipelines()

        effective_pipeline_id = filters.pipeline_id
        if effective_pipeline_id is None and pipelines:
            first_pipeline_id = pipelines[0].get("id")
            if first_pipeline_id is not None:
                effective_pipeline_id = int(first_pipeline_id)

        effective_stage_status_id = filters.stage_status_id
        if effective_stage_status_id is None and effective_pipeline_id is not None:
            effective_stage_status_id = self._first_stage_for_pipeline(pipelines, effective_pipeline_id)

        users = self._safe_list_users()
        users_by_id: dict[int, dict] = {}
        for user in users:
            user_id = user.get("id")
            if user_id is None:
                continue
            users_by_id[int(user_id)] = user

        leads = self._safe_list_leads(
            params=self._build_leads_params(
                created_from=created_from,
                created_to=created_to,
                manager_ids=filters.manager_ids,
                pipeline_id=effective_pipeline_id,
            )
        )

        moved_to_stage_events = self._load_moved_to_stage_events(
            created_from=created_from,
            created_to=created_to,
            manager_ids=filters.manager_ids,
            pipeline_id=effective_pipeline_id,
            stage_status_id=effective_stage_status_id,
        )

        success_pairs = self._resolve_success_status_pairs(effective_pipeline_id, pipelines)
        realized_events = self._load_realized_events(
            created_from=created_from,
            created_to=created_to,
            manager_ids=filters.manager_ids,
            success_pairs=success_pairs,
        )

        arrived_by_manager = self._group_counts(leads, key_name="responsible_user_id")
        moved_by_manager = self._group_counts(moved_to_stage_events, key_name="created_by")
        realized_by_manager = self._group_counts(realized_events, key_name="created_by")

        manager_rows = self._build_manager_rows(
            manager_ids=filters.manager_ids,
            users_by_id=users_by_id,
            arrived_by_manager=arrived_by_manager,
            moved_by_manager=moved_by_manager,
            realized_by_manager=realized_by_manager,
        )

        manager_id_pool = {row["manager_id"] for row in manager_rows}
        manager_id_pool.update(filters.manager_ids)

        managers_payload = []
        for manager_id in sorted(manager_id_pool):
            user = users_by_id.get(manager_id, {})
            managers_payload.append(
                {
                    "id": manager_id,
                    "name": user.get("name") or f"ID {manager_id}",
                }
            )

        if not managers_payload:
            managers_payload = [
                {
                    "id": int(user["id"]),
                    "name": user.get("name") or str(user["id"]),
                }
                for user in users
                if user.get("id") is not None
            ]

        return {
            "filters": {
                "date_from": filters.date_from.isoformat(),
                "date_to": filters.date_to.isoformat(),
                "manager_ids": filters.manager_ids,
                "pipeline_id": effective_pipeline_id,
                "stage_status_id": effective_stage_status_id,
            },
            "summary": {
                "arrived_total": len(leads),
                "moved_to_stage_total": len(moved_to_stage_events),
                "realized_total": len(realized_events),
            },
            "pipelines": self._serialize_pipelines(pipelines),
            "managers": managers_payload,
            "manager_rows": manager_rows,
        }

    def _safe_list_users(self) -> list[dict]:
        try:
            return self.amocrm.list_users()
        except Exception:
            return []

    def _safe_list_pipelines(self) -> list[dict]:
        try:
            return self.amocrm.list_lead_pipelines()
        except Exception:
            return []

    def _safe_list_leads(self, *, params: list[tuple[str, str | int]]) -> list[dict]:
        try:
            return self.amocrm.list_leads(params=params)
        except Exception:
            return []

    def _build_leads_params(
        self,
        *,
        created_from: int,
        created_to: int,
        manager_ids: list[int],
        pipeline_id: int | None,
    ) -> list[tuple[str, str | int]]:
        params: list[tuple[str, str | int]] = [
            ("filter[created_at][from]", created_from),
            ("filter[created_at][to]", created_to),
        ]

        if pipeline_id is not None:
            params.append(("filter[pipeline_id][]", pipeline_id))

        for manager_id in manager_ids:
            params.append(("filter[responsible_user_id][]", manager_id))

        return params

    def _load_moved_to_stage_events(
        self,
        *,
        created_from: int,
        created_to: int,
        manager_ids: list[int],
        pipeline_id: int | None,
        stage_status_id: int | None,
    ) -> list[dict]:
        if pipeline_id is None or stage_status_id is None:
            return []

        base_params: list[tuple[str, str | int]] = [
            ("filter[entity][]", "lead"),
            ("filter[type][]", "lead_status_changed"),
            ("filter[created_at][from]", created_from),
            ("filter[created_at][to]", created_to),
            ("filter[value_after][leads_statuses][0][pipeline_id]", pipeline_id),
            ("filter[value_after][leads_statuses][0][status_id]", stage_status_id),
        ]

        return self._load_events_with_manager_filter(base_params, manager_ids)

    def _load_realized_events(
        self,
        *,
        created_from: int,
        created_to: int,
        manager_ids: list[int],
        success_pairs: list[tuple[int, int]],
    ) -> list[dict]:
        if not success_pairs:
            return []

        base_params: list[tuple[str, str | int]] = [
            ("filter[entity][]", "lead"),
            ("filter[type][]", "lead_status_changed"),
            ("filter[created_at][from]", created_from),
            ("filter[created_at][to]", created_to),
        ]

        for index, (pipeline_id, status_id) in enumerate(success_pairs):
            base_params.append((f"filter[value_after][leads_statuses][{index}][pipeline_id]", pipeline_id))
            base_params.append((f"filter[value_after][leads_statuses][{index}][status_id]", status_id))

        return self._load_events_with_manager_filter(base_params, manager_ids)

    def _load_events_with_manager_filter(
        self,
        base_params: list[tuple[str, str | int]],
        manager_ids: list[int],
    ) -> list[dict]:
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

    def _resolve_success_status_pairs(self, pipeline_id: int | None, pipelines: list[dict]) -> list[tuple[int, int]]:
        result: list[tuple[int, int]] = []

        for pipeline in pipelines:
            current_pipeline_id = pipeline.get("id")
            if current_pipeline_id is None:
                continue
            current_pipeline_id = int(current_pipeline_id)
            if pipeline_id is not None and current_pipeline_id != pipeline_id:
                continue

            statuses = pipeline.get("_embedded", {}).get("statuses", [])
            for status in statuses:
                status_id = status.get("id")
                if status_id is None:
                    continue
                if self._is_success_status(status):
                    result.append((current_pipeline_id, int(status_id)))

        if result:
            return result

        if pipeline_id is not None:
            return [(pipeline_id, 142)]

        pipeline_ids: list[int] = []
        for pipeline in pipelines:
            pipeline_id_value = pipeline.get("id")
            if pipeline_id_value is None:
                continue
            pipeline_ids.append(int(pipeline_id_value))
        if pipeline_ids:
            return [(pid, 142) for pid in pipeline_ids]

        return []

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

    def _first_stage_for_pipeline(self, pipelines: list[dict], pipeline_id: int) -> int | None:
        for pipeline in pipelines:
            current_pipeline_id = pipeline.get("id")
            if current_pipeline_id is None or int(current_pipeline_id) != pipeline_id:
                continue

            statuses = pipeline.get("_embedded", {}).get("statuses", [])
            if not statuses:
                return None

            first_status_id = statuses[0].get("id")
            return int(first_status_id) if first_status_id is not None else None

        return None

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

    def _group_counts(self, items: list[dict], *, key_name: str) -> dict[int, int]:
        grouped: dict[int, int] = defaultdict(int)
        for item in items:
            key = item.get(key_name)
            if key is None:
                continue
            grouped[int(key)] += 1
        return dict(grouped)

    def _build_manager_rows(
        self,
        *,
        manager_ids: list[int],
        users_by_id: dict[int, dict],
        arrived_by_manager: dict[int, int],
        moved_by_manager: dict[int, int],
        realized_by_manager: dict[int, int],
    ) -> list[dict]:
        manager_pool: set[int] = set(arrived_by_manager) | set(moved_by_manager) | set(realized_by_manager)
        if manager_ids:
            manager_pool &= set(manager_ids)
        if not manager_pool and manager_ids:
            manager_pool = set(manager_ids)

        rows: list[dict] = []
        for manager_id in sorted(manager_pool):
            user = users_by_id.get(manager_id, {})
            rows.append(
                {
                    "manager_id": manager_id,
                    "manager_name": user.get("name") or f"ID {manager_id}",
                    "arrived": arrived_by_manager.get(manager_id, 0),
                    "moved_to_stage": moved_by_manager.get(manager_id, 0),
                    "realized": realized_by_manager.get(manager_id, 0),
                }
            )

        return rows

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
