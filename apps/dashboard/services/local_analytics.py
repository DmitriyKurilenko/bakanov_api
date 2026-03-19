from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

from django.db.models import Count, Q
from django.utils import timezone

from apps.crm.models import AmoLead, AmoManagerProfile


PERIODS = {"week": 7, "month": 30, "quarter": 90}


@dataclass(frozen=True)
class PeriodWindow:
    code: str
    date_from: date
    date_to: date


def resolve_period(code: str | None) -> PeriodWindow:
    normalized = code if code in PERIODS else "week"
    today = timezone.localdate()
    return PeriodWindow(
        code=normalized,
        date_from=today - timedelta(days=PERIODS[normalized] - 1),
        date_to=today,
    )


def _bucket_key(dt, period_code: str) -> date:
    d = dt.date() if hasattr(dt, "date") else dt
    if period_code == "week":
        return d
    if period_code == "month":
        return d.replace(day=1)
    # quarter
    month = ((d.month - 1) // 3) * 3 + 1
    return d.replace(month=month, day=1)


def _bucket_label(bucket: date, period_code: str) -> str:
    if period_code == "week":
        return bucket.strftime("%d.%m")
    if period_code == "month":
        return bucket.strftime("%m.%Y")
    quarter = (bucket.month - 1) // 3 + 1
    return f"Q{quarter} {bucket.year}"


def manager_deals_chart(period_code: str) -> dict:
    window = resolve_period(period_code)
    qs = (
        AmoLead.objects.filter(
            first_received_at__date__gte=window.date_from,
            first_received_at__date__lte=window.date_to,
            assigned_manager__is_active=True,
            assigned_manager__is_amo_active=True,
        )
        .select_related("assigned_manager")
        .order_by("first_received_at")
    )

    manager_names = {
        m.id: m.name
        for m in AmoManagerProfile.objects.filter(is_amo_active=True, is_active=True)
    }
    buckets: list[date] = []
    bucket_set: set[date] = set()
    counts: dict[int | None, dict[date, int]] = {}

    for lead in qs:
        bucket = _bucket_key(lead.first_received_at, window.code)
        if bucket not in bucket_set:
            bucket_set.add(bucket)
            buckets.append(bucket)
        manager_id = lead.assigned_manager_id
        counts.setdefault(manager_id, {})
        counts[manager_id][bucket] = counts[manager_id].get(bucket, 0) + 1
        if manager_id and manager_id not in manager_names and lead.assigned_manager:
            manager_names[manager_id] = lead.assigned_manager.name

    buckets.sort()
    labels = [_bucket_label(bucket, window.code) for bucket in buckets]

    datasets = []
    for manager_id, bucket_counts in sorted(
        counts.items(),
        key=lambda item: (manager_names.get(item[0], "Без менеджера").lower(), item[0] or 0),
    ):
        datasets.append(
            {
                "label": manager_names.get(manager_id, "Без менеджера"),
                "data": [bucket_counts.get(bucket, 0) for bucket in buckets],
            }
        )

    totals = (
        qs.values("assigned_manager_id")
        .annotate(total=Count("id"), in_work=Count("id", filter=Q(is_closed=False)))
        .order_by("-total")
    )
    manager_rows = [
        {
            "manager_name": manager_names.get(row["assigned_manager_id"], "Без менеджера"),
            "deals_total": int(row["total"]),
            "deals_in_work": int(row["in_work"]),
        }
        for row in totals
    ]

    return {
        "period": window.code,
        "date_from": window.date_from.isoformat(),
        "date_to": window.date_to.isoformat(),
        "labels": labels,
        "datasets": datasets,
        "rows": manager_rows,
    }


def stage_deals_chart(period_code: str) -> dict:
    window = resolve_period(period_code)
    qs = (
        AmoLead.objects.filter(
            first_received_at__date__gte=window.date_from,
            first_received_at__date__lte=window.date_to,
            assigned_manager__is_active=True,
            assigned_manager__is_amo_active=True,
        )
        .order_by("first_received_at")
    )
    buckets: list[date] = []
    bucket_set: set[date] = set()
    counts: dict[str, dict[date, int]] = {}

    for lead in qs:
        bucket = _bucket_key(lead.first_received_at, window.code)
        if bucket not in bucket_set:
            bucket_set.add(bucket)
            buckets.append(bucket)
        stage_label = f"Этап {lead.status_id}" if lead.status_id else "Без этапа"
        counts.setdefault(stage_label, {})
        counts[stage_label][bucket] = counts[stage_label].get(bucket, 0) + 1

    buckets.sort()
    labels = [_bucket_label(bucket, window.code) for bucket in buckets]
    datasets = [
        {
            "label": stage_label,
            "data": [bucket_counts.get(bucket, 0) for bucket in buckets],
        }
        for stage_label, bucket_counts in sorted(counts.items(), key=lambda item: item[0])
    ]

    stage_rows = (
        qs.values("status_id")
        .annotate(total=Count("id"), in_work=Count("id", filter=Q(is_closed=False)))
        .order_by("-total")
    )
    rows = [
        {
            "stage_name": f"Этап {row['status_id']}" if row["status_id"] else "Без этапа",
            "deals_total": int(row["total"]),
            "deals_in_work": int(row["in_work"]),
        }
        for row in stage_rows
    ]

    return {
        "period": window.code,
        "date_from": window.date_from.isoformat(),
        "date_to": window.date_to.isoformat(),
        "labels": labels,
        "datasets": datasets,
        "rows": rows,
    }


def analytics_summary_cards() -> dict:
    now = timezone.localdate()
    week_start = now - timedelta(days=now.weekday())
    month_start = now.replace(day=1)
    return {
        "deals_total": AmoLead.objects.count(),
        "deals_in_work": AmoLead.objects.filter(is_closed=False).count(),
        "new_this_week": AmoLead.objects.filter(first_received_at__date__gte=week_start).count(),
        "new_this_month": AmoLead.objects.filter(first_received_at__date__gte=month_start).count(),
        "managers_active": AmoManagerProfile.objects.filter(is_amo_active=True, is_active=True).count(),
    }
