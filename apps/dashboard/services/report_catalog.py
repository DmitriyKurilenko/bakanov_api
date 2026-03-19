"""Central registry of dashboard reports and their access rules.

This module provides:
- report metadata (title/description/allowed roles),
- input parsing helpers for shared query params,
- builders that map HTTP query params to report service filters,
- access checks used by dashboard views.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import hashlib
import json

from django.conf import settings
from django.core.cache import cache
from django.http import QueryDict

from apps.crm.models import AmoManagerProfile
from apps.crm.services.amocrm import AmoCRMClient
from apps.dashboard.services.rop_report import RopReportFilters, RopReportService
from apps.users.models import UserRole


@dataclass(frozen=True)
class ReportDefinition:
    """Declarative metadata describing a dashboard report."""

    key: str
    title: str
    description: str
    allowed_roles: frozenset[str]


def _parse_date(value: str | None, fallback: date) -> date:
    """Parse ISO date string from query params with safe fallback."""
    if not value:
        return fallback
    try:
        return date.fromisoformat(value)
    except ValueError:
        return fallback


def _parse_int(value: str | None) -> int | None:
    """Parse optional integer query parameter."""
    if value in (None, ""):
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _service_active_amo_user_ids() -> list[int]:
    return list(
        AmoManagerProfile.objects.filter(is_amo_active=True, is_active=True)
        .order_by("amo_user_id")
        .values_list("amo_user_id", flat=True)
    )


def _build_rop_funnel_report(query_params: QueryDict) -> dict:
    """Build payload for the ROP funnel report from request query params."""
    today = date.today()
    default_from = today - timedelta(days=7)

    date_from = _parse_date(query_params.get("date_from"), default_from)
    date_to = _parse_date(query_params.get("date_to"), today)
    if date_from > date_to:
        date_from, date_to = date_to, date_from

    allowed_manager_ids = set(_service_active_amo_user_ids())
    manager_ids: list[int] = []
    for raw in query_params.getlist("manager_ids"):
        parsed = _parse_int(raw)
        if parsed is not None and (not allowed_manager_ids or parsed in allowed_manager_ids):
            manager_ids.append(parsed)
    if not manager_ids:
        manager_ids = sorted(allowed_manager_ids)

    pipeline_id = _parse_int(query_params.get("pipeline_id"))
    stage_status_id = _parse_int(query_params.get("stage_status_id"))

    filters = RopReportFilters(
        date_from=date_from,
        date_to=date_to,
        manager_ids=manager_ids,
        pipeline_id=pipeline_id,
        stage_status_id=stage_status_id,
    )
    return RopReportService().build_report(filters)


def _build_stage_conversion_report(query_params: QueryDict) -> dict:
    """Build payload for the stage conversion report from request query params."""
    today = date.today()
    default_from = today - timedelta(days=7)

    date_from = _parse_date(query_params.get("date_from"), default_from)
    date_to = _parse_date(query_params.get("date_to"), today)
    if date_from > date_to:
        date_from, date_to = date_to, date_from

    allowed_manager_ids = set(_service_active_amo_user_ids())
    manager_ids: list[int] = []
    for raw in query_params.getlist("manager_ids"):
        parsed = _parse_int(raw)
        if parsed is not None and (not allowed_manager_ids or parsed in allowed_manager_ids):
            manager_ids.append(parsed)
    if not manager_ids:
        manager_ids = sorted(allowed_manager_ids)

    pipeline_id = _parse_int(query_params.get("pipeline_id"))

    filters = StageConversionFilters(
        date_from=date_from,
        date_to=date_to,
        manager_ids=manager_ids,
        pipeline_id=pipeline_id,
    )
    return StageConversionReportService().build_report(filters)


def _serialize_pipelines(pipelines: list[dict]) -> list[dict]:
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


def _collect_common_meta() -> tuple[list[dict], list[dict]]:
    cache_key = "dashboard:reports:common_meta:v3"
    cached_value = cache.get(cache_key)
    if isinstance(cached_value, dict):
        cached_pipelines = cached_value.get("pipelines")
        cached_managers = cached_value.get("managers")
        if isinstance(cached_pipelines, list) and isinstance(cached_managers, list):
            return cached_pipelines, cached_managers

    amocrm = AmoCRMClient.from_settings()

    try:
        pipelines = amocrm.list_lead_pipelines()
    except Exception:
        pipelines = []

    managers = list(
        AmoManagerProfile.objects.filter(is_amo_active=True, is_active=True)
        .order_by("name", "amo_user_id")
        .values("amo_user_id", "name")
    )
    managers = [{"id": int(row["amo_user_id"]), "name": row["name"]} for row in managers]

    if not managers:
        try:
            users = amocrm.list_users()
        except Exception:
            users = []
        managers = []
        for user in users:
            user_id = user.get("id")
            if user_id is None:
                continue
            if any(
                [
                    ("active" in user and not bool(user.get("active"))),
                    ("is_active" in user and not bool(user.get("is_active"))),
                    (
                        isinstance(user.get("rights"), dict)
                        and "is_active" in user["rights"]
                        and not bool(user["rights"].get("is_active"))
                    ),
                ]
            ):
                continue
            managers.append({"id": int(user_id), "name": user.get("name") or str(user_id)})

    serialized_pipelines = _serialize_pipelines(pipelines)
    cache_ttl = int(getattr(settings, "REPORT_META_CACHE_TTL", 2592000))
    # Do not pin empty metadata for a long time: transient amoCRM/network failures happen.
    effective_ttl = cache_ttl if (serialized_pipelines or managers) else 60
    cache.set(
        cache_key,
        {
            "pipelines": serialized_pipelines,
            "managers": managers,
        },
        timeout=effective_ttl,
    )

    return serialized_pipelines, managers


def refresh_common_report_meta_cache() -> dict:
    """Force refresh of report metadata cache from amoCRM and local manager profiles."""
    cache.delete("dashboard:reports:common_meta:v3")
    pipelines, managers = _collect_common_meta()
    return {"pipelines_count": len(pipelines), "managers_count": len(managers)}


def _build_rop_funnel_meta(query_params: QueryDict) -> dict:
    pipelines, managers = _collect_common_meta()

    pipeline_id = _parse_int(query_params.get("pipeline_id"))
    if pipeline_id is None and pipelines:
        pipeline_id = int(pipelines[0]["id"])

    stage_status_id = _parse_int(query_params.get("stage_status_id"))
    if stage_status_id is None and pipeline_id is not None:
        selected_pipeline = next((item for item in pipelines if int(item["id"]) == pipeline_id), None)
        if selected_pipeline and selected_pipeline.get("statuses"):
            stage_status_id = int(selected_pipeline["statuses"][0]["id"])

    return {
        "filters": {
            "pipeline_id": pipeline_id,
            "stage_status_id": stage_status_id,
        },
        "pipelines": pipelines,
        "managers": managers,
    }


def _build_stage_conversion_meta(query_params: QueryDict) -> dict:
    pipelines, managers = _collect_common_meta()

    pipeline_id = _parse_int(query_params.get("pipeline_id"))
    if pipeline_id is None and pipelines:
        pipeline_id = int(pipelines[0]["id"])

    return {
        "filters": {
            "pipeline_id": pipeline_id,
        },
        "pipelines": pipelines,
        "managers": managers,
    }


REPORTS: dict[str, ReportDefinition] = {
    "rop_funnel": ReportDefinition(
        key="rop_funnel",
        title="Воронка РОП",
        description="Пришло сделок, перешло в выбранный этап, реализовано с фильтрами по менеджерам.",
        allowed_roles=frozenset({UserRole.HEAD, UserRole.ADMIN}),
    ),
}


REPORT_BUILDERS = {
    "rop_funnel": _build_rop_funnel_report,
}

REPORT_META_BUILDERS = {
    "rop_funnel": _build_rop_funnel_meta,
}


def get_available_reports_for_role(role: str) -> list[ReportDefinition]:
    """Return all reports accessible by the specified user role."""
    return [report for report in REPORTS.values() if role in report.allowed_roles]


def get_report_definition(report_key: str) -> ReportDefinition | None:
    """Return report metadata by key or ``None`` when unknown."""
    return REPORTS.get(report_key)


def can_access_report(role: str, report_key: str) -> bool:
    """Check whether a role has access to a report key."""
    report = get_report_definition(report_key)
    if report is None:
        return False
    return role in report.allowed_roles


def build_report_data(report_key: str, query_params: QueryDict) -> dict:
    """Execute report builder by key and return JSON-serializable payload."""
    builder = REPORT_BUILDERS.get(report_key)
    if builder is None:
        raise KeyError(f"Unknown report key: {report_key}")
    cache_ttl = int(getattr(settings, "REPORT_DATA_CACHE_TTL", 600))
    if cache_ttl <= 0:
        return builder(query_params)

    normalized_items: list[tuple[str, list[str]]] = []
    for key in sorted(query_params.keys()):
        values = [str(v) for v in query_params.getlist(key)]
        if key == "manager_ids":
            values = sorted(values)
        normalized_items.append((key, values))

    cache_payload = {
        "report_key": report_key,
        "params": normalized_items,
    }
    cache_hash = hashlib.md5(json.dumps(cache_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    cache_key = f"dashboard:report:data:v1:{report_key}:{cache_hash}"
    cached = cache.get(cache_key)
    if isinstance(cached, dict):
        return cached

    result = builder(query_params)
    cache.set(cache_key, result, timeout=cache_ttl)
    return result


def build_report_meta(report_key: str, query_params: QueryDict) -> dict:
    """Execute lightweight metadata builder for report filters/selectors."""
    builder = REPORT_META_BUILDERS.get(report_key)
    if builder is None:
        raise KeyError(f"Unknown report key: {report_key}")
    return builder(query_params)
