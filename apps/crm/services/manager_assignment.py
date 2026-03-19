from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
import logging
from typing import Iterable

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone
import requests

from apps.crm.models import (
    AmoLead,
    AmoLeadAssignmentEvent,
    AmoManagerProfile,
    ManagerDayOff,
    ManagerWeekdaySchedule,
)
from apps.crm.services.amocrm import AmoCRMClient
from apps.integrations.services.telegram_service import send_telegram_message


SYSTEM_SUCCESS_STATUS_ID = 142
SYSTEM_FAILURE_STATUS_ID = 143
logger = logging.getLogger(__name__)


def _amo_user_is_active(user: dict) -> bool:
    if "active" in user:
        return bool(user.get("active"))
    if "is_active" in user:
        return bool(user.get("is_active"))
    rights = user.get("rights")
    if isinstance(rights, dict) and "is_active" in rights:
        return bool(rights.get("is_active"))
    return True


def _parse_amo_datetime(value) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


@dataclass
class AssignmentDecision:
    manager: AmoManagerProfile
    weekly_deals: int
    active_deals: int
    normalized_load: float


class AmoManagerSyncService:
    def __init__(self, amocrm: AmoCRMClient | None = None):
        self.amocrm = amocrm or AmoCRMClient.from_settings()

    def sync_active_managers(self) -> list[AmoManagerProfile]:
        now = timezone.now()
        users = self.amocrm.list_users()
        active_users = [user for user in users if user.get("id") is not None and _amo_user_is_active(user)]
        active_ids = {int(user["id"]) for user in active_users}

        with transaction.atomic():
            synced: list[AmoManagerProfile] = []
            for user in active_users:
                manager, created = AmoManagerProfile.objects.get_or_create(
                    amo_user_id=int(user["id"]),
                    defaults={
                        "name": user.get("name") or f"Менеджер {user['id']}",
                        "is_amo_active": True,
                        "last_synced_at": now,
                    },
                )
                changed = False
                new_name = user.get("name") or manager.name
                if manager.name != new_name:
                    manager.name = new_name
                    changed = True
                if not manager.is_amo_active:
                    manager.is_amo_active = True
                    changed = True
                manager.last_synced_at = now
                changed = True
                if changed and not created:
                    manager.save(update_fields=["name", "is_amo_active", "last_synced_at", "updated_at"])
                manager.ensure_default_schedule()
                synced.append(manager)

            if active_ids:
                AmoManagerProfile.objects.exclude(amo_user_id__in=active_ids).update(is_amo_active=False, last_synced_at=now)

        return synced


class DealAssignmentService:
    def __init__(self, amocrm: AmoCRMClient | None = None):
        self.amocrm = amocrm or AmoCRMClient.from_settings()

    def _week_bounds(self, target_date: date) -> tuple[date, date]:
        week_start = target_date - timedelta(days=target_date.weekday())
        week_end = week_start + timedelta(days=6)
        return week_start, week_end

    def _working_days_for_week(self, manager: AmoManagerProfile, target_date: date) -> int:
        week_start, week_end = self._week_bounds(target_date)
        schedule_days = {
            row.weekday
            for row in manager.weekday_schedules.all()
            if row.is_working
        }
        if not schedule_days:
            return 0
        days_off = set(
            manager.days_off.filter(date__gte=week_start, date__lte=week_end).values_list("date", flat=True)
        )
        count = 0
        current = week_start
        while current <= week_end:
            if current.weekday() in schedule_days and current not in days_off:
                count += 1
            current += timedelta(days=1)
        return count

    def _is_available_today(self, manager: AmoManagerProfile, target_date: date) -> bool:
        is_working = manager.weekday_schedules.filter(weekday=target_date.weekday(), is_working=True).exists()
        if not is_working:
            return False
        if manager.days_off.filter(date=target_date).exists():
            return False
        return True

    def _candidate_queryset(self):
        return (
            AmoManagerProfile.objects.filter(is_amo_active=True, is_active=True)
            .prefetch_related("weekday_schedules", "days_off")
        )

    def choose_manager(self, *, target_date: date | None = None) -> AssignmentDecision | None:
        target_date = target_date or timezone.localdate()
        managers = list(self._candidate_queryset())
        if not managers:
            return None

        week_start, week_end = self._week_bounds(target_date)
        lead_stats = (
            AmoLead.objects.filter(assigned_manager__in=managers)
            .values("assigned_manager_id")
            .annotate(
                active_deals=Count("id", filter=Q(is_closed=False)),
                weekly_deals=Count(
                    "id",
                    filter=Q(first_received_at__date__gte=week_start, first_received_at__date__lte=week_end),
                ),
            )
        )
        stats_map = {row["assigned_manager_id"]: row for row in lead_stats}

        candidates: list[AssignmentDecision] = []
        for manager in managers:
            if not self._is_available_today(manager, target_date):
                continue
            row = stats_map.get(manager.id, {})
            active_deals = int(row.get("active_deals") or 0)
            weekly_deals = int(row.get("weekly_deals") or 0)
            working_days = self._working_days_for_week(manager, target_date)
            if working_days <= 0:
                continue
            normalized = weekly_deals / working_days
            candidates.append(
                AssignmentDecision(
                    manager=manager,
                    weekly_deals=weekly_deals,
                    active_deals=active_deals,
                    normalized_load=normalized,
                )
            )

        if not candidates:
            return None

        candidates.sort(
            key=lambda item: (
                item.normalized_load,
                item.weekly_deals,
                item.active_deals,
                item.manager.name.lower(),
                item.manager.amo_user_id,
            )
        )
        return candidates[0]

    def _extract_lead_ids(self, raw_body: dict, post_data) -> list[int]:
        lead_ids: set[int] = set()
        for key in post_data.keys():
            if "leads" in key and key.endswith("[id]"):
                value = post_data.get(key)
                if value and str(value).isdigit():
                    lead_ids.add(int(value))

        if isinstance(raw_body, dict):
            leads = raw_body.get("leads") or raw_body.get("_embedded", {}).get("leads")
            if isinstance(leads, list):
                for lead in leads:
                    if isinstance(lead, dict) and str(lead.get("id", "")).isdigit():
                        lead_ids.add(int(lead["id"]))
            if isinstance(raw_body.get("lead_id"), int):
                lead_ids.add(int(raw_body["lead_id"]))

        return sorted(lead_ids)

    def extract_webhook_lead_ids(self, *, raw_body: dict | None, post_data) -> list[int]:
        return self._extract_lead_ids(raw_body or {}, post_data)

    def _upsert_lead_from_payload(self, lead_id: int, lead_payload: dict, selected: AmoManagerProfile | None) -> AmoLead:
        status_id = lead_payload.get("status_id")
        status_id_int = int(status_id) if str(status_id).isdigit() else None
        is_success = status_id_int == SYSTEM_SUCCESS_STATUS_ID
        is_closed = status_id_int in {SYSTEM_SUCCESS_STATUS_ID, SYSTEM_FAILURE_STATUS_ID}
        defaults = {
            "name": lead_payload.get("name") or "",
            "price": Decimal(str(lead_payload.get("price") or 0)),
            "pipeline_id": int(lead_payload["pipeline_id"]) if str(lead_payload.get("pipeline_id", "")).isdigit() else None,
            "status_id": status_id_int,
            "responsible_user_id": selected.amo_user_id if selected else lead_payload.get("responsible_user_id"),
            "assigned_manager": selected,
            "is_closed": is_closed,
            "is_success": is_success,
            "amo_created_at": _parse_amo_datetime(lead_payload.get("created_at")),
            "amo_updated_at": _parse_amo_datetime(lead_payload.get("updated_at")),
            "last_webhook_at": timezone.now(),
            "payload": lead_payload or {},
        }
        lead, created = AmoLead.objects.get_or_create(amo_lead_id=lead_id, defaults=defaults)
        if not created:
            changed_fields = []
            for field, value in defaults.items():
                if getattr(lead, field) != value:
                    setattr(lead, field, value)
                    changed_fields.append(field)
            if changed_fields:
                changed_fields.append("updated_at")
                lead.save(update_fields=changed_fields)
        return lead

    def handle_new_deals_webhook(self, *, raw_body: dict | None, post_data) -> dict:
        lead_ids = self._extract_lead_ids(raw_body or {}, post_data)
        if not lead_ids:
            return {"processed": 0, "assigned": 0, "details": [], "message": "No lead ids in webhook payload"}

        processed = 0
        assigned = 0
        details: list[dict] = []
        for lead_id in lead_ids:
            processed += 1
            lead_payload = {"id": lead_id}
            lead_fetch_error = None
            try:
                lead_payload = self.amocrm.get_lead(lead_id)
            except requests.RequestException as exc:
                lead_fetch_error = str(exc)
                logger.warning("Failed to load lead from amoCRM for lead_id=%s: %s", lead_id, exc)

            decision = self.choose_manager()
            selected_manager = decision.manager if decision else None
            previous_responsible = lead_payload.get("responsible_user_id")
            assignment_error = None

            if selected_manager is not None:
                try:
                    self.amocrm.update_lead_responsible(lead_id, int(selected_manager.amo_user_id))
                    assigned += 1
                except requests.RequestException as exc:
                    assignment_error = str(exc)
                    # Keep record even if amoCRM update fails; UI/reporting should show the attempt/result.
                    logger.warning("Failed to update responsible in amoCRM for lead_id=%s manager_id=%s: %s", lead_id, selected_manager.amo_user_id, exc)

            lead = self._upsert_lead_from_payload(lead_id, lead_payload, selected_manager)

            if selected_manager is not None:
                AmoLeadAssignmentEvent.objects.create(
                    amo_lead=lead,
                    manager=selected_manager,
                    previous_responsible_user_id=int(previous_responsible) if str(previous_responsible).isdigit() else None,
                    new_responsible_user_id=selected_manager.amo_user_id,
                    reason="webhook_new_deal_auto_assignment",
                )
                lead_link = f"{self.amocrm.base_url}/leads/detail/{lead_id}" if self.amocrm.base_url else str(lead_id)
                send_telegram_message(
                    f"Новая сделка: {lead.name or ('#' + str(lead_id))}\n"
                    f"Ответственный: {selected_manager.name}\n"
                    f"Ссылка: {lead_link}"
                )

            details.append(
                {
                    "lead_id": lead_id,
                    "assigned_manager": selected_manager.name if selected_manager else None,
                    "assigned_manager_amo_user_id": selected_manager.amo_user_id if selected_manager else None,
                    "normalized_load": round(decision.normalized_load, 3) if decision else None,
                    "weekly_deals": decision.weekly_deals if decision else None,
                    "active_deals": decision.active_deals if decision else None,
                    "lead_fetch_error": lead_fetch_error,
                    "assignment_error": assignment_error,
                }
            )

        return {
            "processed": processed,
            "assigned": assigned,
            "details": details,
        }

    def handle_single_new_deal(self, *, lead_id: int) -> dict:
        result = self.handle_new_deals_webhook(raw_body={"lead_id": int(lead_id)}, post_data={})
        if result.get("details"):
            return result["details"][0]
        return {"lead_id": int(lead_id), "assigned_manager": None}


def manager_dashboard_stats() -> dict:
    now = timezone.localdate()
    week_start = now - timedelta(days=now.weekday())
    week_end = week_start + timedelta(days=6)
    avg_start = now - timedelta(days=27)

    active_qs = AmoLead.objects.filter(is_closed=False)
    weekly_qs = AmoLead.objects.filter(first_received_at__date__gte=week_start, first_received_at__date__lte=week_end)

    total_active = active_qs.count()
    total_managers = AmoManagerProfile.objects.filter(is_amo_active=True, is_active=True).count()
    weekly_counts = list(
        weekly_qs.values("assigned_manager_id").annotate(total=Count("id")).values_list("total", flat=True)
    )
    avg_weekly = (sum(weekly_counts) / len(weekly_counts)) if weekly_counts else 0

    return {
        "active_deals_total": total_active,
        "active_managers_total": total_managers,
        "avg_weekly_deals_per_manager": round(float(avg_weekly or 0), 2),
    }


def manager_list_with_stats() -> list[dict]:
    managers = (
        AmoManagerProfile.objects.prefetch_related("weekday_schedules", "days_off")
        .filter(is_amo_active=True)
        .order_by("name")
    )
    now = timezone.localdate()
    week_start = now - timedelta(days=now.weekday())
    week_end = week_start + timedelta(days=6)
    avg_start = now - timedelta(days=27)

    lead_counts = (
        AmoLead.objects.filter(assigned_manager__in=managers)
        .values("assigned_manager_id")
        .annotate(
            in_work=Count("id", filter=Q(is_closed=False)),
            weekly=Count("id", filter=Q(first_received_at__date__gte=week_start, first_received_at__date__lte=week_end)),
            avg_window=Count("id", filter=Q(first_received_at__date__gte=avg_start, first_received_at__date__lte=now)),
        )
    )
    counts_map = {row["assigned_manager_id"]: row for row in lead_counts}

    result = []
    for manager in managers:
        manager.ensure_default_schedule()
        counts = counts_map.get(manager.id, {})
        schedule_rows = [
            {
                "weekday": row.weekday,
                "label": row.get_weekday_display(),
                "is_working": row.is_working,
            }
            for row in sorted(manager.weekday_schedules.all(), key=lambda item: item.weekday)
        ]
        days_off = list(manager.days_off.filter(date__gte=now - timedelta(days=14)).order_by("date")[:10])
        result.append(
            {
                "manager": manager,
                "stats": {
                    "in_work": int(counts.get("in_work") or 0),
                    "weekly": int(counts.get("weekly") or 0),
                    "avg_weekly": round((int(counts.get("avg_window") or 0) / 4), 2),
                },
                "schedule_rows": schedule_rows,
                "days_off": days_off,
            }
        )
    return result
