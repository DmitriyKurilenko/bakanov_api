from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from apps.crm.models import AmoManagerProfile, ManagerDayOff, ManagerWeekdaySchedule
from apps.crm.services.manager_assignment import manager_list_with_stats
from apps.crm.tasks import sync_amo_managers as sync_amo_managers_task
from apps.dashboard.services.report_catalog import (
    build_report_meta,
    build_report_data,
    can_access_report,
    get_available_reports_for_role,
    get_report_definition,
    refresh_common_report_meta_cache,
)
from apps.dashboard.services.local_analytics import manager_deals_chart, stage_deals_chart
from apps.dashboard.services.report_export import render_report_excel_response, render_report_pdf_response
from apps.users.models import UserRole


def _dashboard_nav_items() -> list[dict[str, str]]:
    return [
        {"key": "home", "label": "Главная", "url": reverse("dashboard:home")},
        {"key": "managers", "label": "Менеджеры", "url": reverse("dashboard:managers")},
        {"key": "analytics", "label": "Аналитика", "url": reverse("dashboard:analytics")},
        {"key": "reports", "label": "Отчеты", "url": reverse("dashboard:reports-home")},
        {"key": "settings", "label": "Настройки", "url": reverse("dashboard:settings")},
    ]


def _build_dashboard_context(request: HttpRequest, *, active_section: str, **extra) -> dict:
    role = request.user.role
    context = {
        "role": role,
        "is_manager": role == UserRole.MANAGER,
        "is_head_or_admin": role in {UserRole.HEAD, UserRole.ADMIN},
        "dashboard_nav_items": _dashboard_nav_items(),
        "active_section": active_section,
    }
    context.update(extra)
    return context


@login_required
def dashboard_home(request):
    role = request.user.role
    context = _build_dashboard_context(
        request,
        active_section="home",
        available_reports=get_available_reports_for_role(role),
    )
    return render(request, "dashboard/home.html", context)


@login_required
@require_POST
def sync_reports_meta(request: HttpRequest):
    if request.user.role not in {UserRole.HEAD, UserRole.ADMIN}:
        messages.error(request, "Недостаточно прав для синхронизации метаданных отчетов")
        return redirect("dashboard:home")

    try:
        sync_amo_managers_task.delay()
    except Exception:
        # Broker may be unavailable in local/test mode; cache refresh below still updates report metadata.
        pass

    try:
        stats = refresh_common_report_meta_cache()
        messages.success(
            request,
            f"Метаданные отчетов синхронизированы (воронки: {stats['pipelines_count']}, менеджеры: {stats['managers_count']})",
        )
    except Exception as exc:
        messages.error(request, f"Ошибка синхронизации метаданных из amoCRM: {exc}")

    return redirect("dashboard:home")


@login_required
def analytics_home(request: HttpRequest):
    return render(
        request,
        "dashboard/analytics_home.html",
        _build_dashboard_context(
            request,
            active_section="analytics",
            reports_url=reverse("dashboard:reports-home"),
        ),
    )


@login_required
def reports_home(request: HttpRequest):
    report_links = []
    for item in get_available_reports_for_role(request.user.role):
        if item.key == "rop_funnel":
            url = reverse("dashboard:reports-rop")
        else:
            continue
        report_links.append({"key": item.key, "title": item.title, "description": item.description, "url": url})
    return render(
        request,
        "dashboard/reports_index.html",
        _build_dashboard_context(
            request,
            active_section="reports",
            report_links=report_links,
        ),
    )


@login_required
def analytics_report_page(request: HttpRequest, report_key: str):
    report = get_report_definition(report_key)
    if report is None:
        return redirect("dashboard:analytics")
    if not can_access_report(request.user.role, report_key):
        messages.error(request, "Недостаточно прав для просмотра отчета")
        return redirect("dashboard:analytics")

    today = date.today()
    default_from = today - timedelta(days=7)
    report_links = []
    for item in get_available_reports_for_role(request.user.role):
        if item.key == "rop_funnel":
            url = reverse("dashboard:reports-rop")
        else:
            continue
        report_links.append({"key": item.key, "title": item.title, "url": url})

    try:
        report_meta_initial = build_report_meta(report_key, QueryDict(""))
    except Exception:
        report_meta_initial = {"pipelines": [], "managers": [], "filters": {}}

    return render(
        request,
        "dashboard/report_page.html",
        _build_dashboard_context(
            request,
            active_section="reports",
            report=report,
            report_links=report_links,
            report_defaults={
                "date_from": default_from.isoformat(),
                "date_to": today.isoformat(),
            },
            report_meta_initial=report_meta_initial,
        ),
    )


@login_required
def placeholder_page(request: HttpRequest, section_key: str, section_title: str):
    return render(
        request,
        "dashboard/placeholder.html",
        _build_dashboard_context(
            request,
            active_section=section_key,
            section_title=section_title,
        ),
    )


@login_required
def managers_page(request: HttpRequest):
    return render(
        request,
        "dashboard/managers.html",
        _build_dashboard_context(
            request,
            active_section="managers",
            manager_cards=manager_list_with_stats(),
            weekday_choices=ManagerWeekdaySchedule.Weekday.choices,
        ),
    )


def _render_managers_partial(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "dashboard/partials/managers_list.html",
        {
            "manager_cards": manager_list_with_stats(),
            "weekday_choices": ManagerWeekdaySchedule.Weekday.choices,
        },
    )


@login_required
@require_POST
def managers_sync(request: HttpRequest):
    try:
        task = sync_amo_managers_task.delay()
        messages.success(request, f"Задача синхронизации менеджеров поставлена в очередь Celery: {task.id}")
    except Exception as exc:
        messages.error(request, f"Ошибка синхронизации amoCRM: {exc}")
    if request.headers.get("HX-Request") == "true":
        return _render_managers_partial(request)
    return redirect("dashboard:managers")


@login_required
@require_POST
def manager_update(request: HttpRequest, manager_id: int):
    manager = get_object_or_404(AmoManagerProfile, pk=manager_id)
    try:
        manager.is_active = request.POST.get("is_active") == "on"
        manager.save(update_fields=["is_active", "updated_at"])
        selected_days = {int(day) for day in request.POST.getlist("workdays") if str(day).isdigit()}
        manager.ensure_default_schedule()
        schedules = {item.weekday: item for item in manager.weekday_schedules.all()}
        for weekday in range(7):
            item = schedules.get(weekday)
            if item is None:
                continue
            should_work = weekday in selected_days
            if item.is_working != should_work:
                item.is_working = should_work
                item.save(update_fields=["is_working"])
        messages.success(request, f"Настройки менеджера «{manager.name}» сохранены")
    except Exception as exc:
        messages.error(request, f"Ошибка сохранения менеджера: {exc}")
    if request.headers.get("HX-Request") == "true":
        return _render_managers_partial(request)
    return redirect("dashboard:managers")


@login_required
@require_POST
def manager_day_off_add(request: HttpRequest, manager_id: int):
    manager = get_object_or_404(AmoManagerProfile, pk=manager_id)
    day_value = request.POST.get("day_off_date")
    if not day_value:
        messages.warning(request, "Дата не указана")
    else:
        try:
            day_off = date.fromisoformat(day_value)
            ManagerDayOff.objects.get_or_create(
                manager=manager,
                date=day_off,
                defaults={"reason": (request.POST.get("day_off_reason") or "").strip()},
            )
            messages.success(request, f"Нерабочий день добавлен для «{manager.name}»")
        except ValueError:
            messages.error(request, "Некорректная дата нерабочего дня")
    if request.headers.get("HX-Request") == "true":
        return _render_managers_partial(request)
    return redirect("dashboard:managers")


@login_required
@require_POST
def manager_day_off_delete(request: HttpRequest, manager_id: int, day_off_id: int):
    manager = get_object_or_404(AmoManagerProfile, pk=manager_id)
    ManagerDayOff.objects.filter(id=day_off_id, manager=manager).delete()
    messages.success(request, f"Нерабочий день удален для «{manager.name}»")
    if request.headers.get("HX-Request") == "true":
        return _render_managers_partial(request)
    return redirect("dashboard:managers")


@login_required
def settings_page(request: HttpRequest):
    from django.conf import settings as dj_settings

    context = _build_dashboard_context(
        request,
        active_section="settings",
        integrations_status={
            "amocrm_base_url": bool(dj_settings.AMOCRM_BASE_URL),
            "amocrm_token": bool(dj_settings.AMOCRM_ACCESS_TOKEN),
            "telegram_token": bool(dj_settings.TELEGRAM_BOT_TOKEN),
            "telegram_chat_id": bool(dj_settings.TELEGRAM_CHAT_ID),
            "redis_url": bool(getattr(dj_settings, "CELERY_BROKER_URL", "")),
        },
        webhook_examples={
            "ninja_webhook_url": request.build_absolute_uri("/api/crm/amo/webhook/new-deals"),
            "sync_managers_url": request.build_absolute_uri("/api/crm/amo/managers/sync"),
        },
    )
    return render(request, "dashboard/settings.html", context)


@login_required
@require_GET
def report_api(request: HttpRequest, report_key: str):
    report = get_report_definition(report_key)
    if report is None:
        return JsonResponse({"status": "error", "detail": "Отчёт не найден"}, status=404)

    if not can_access_report(request.user.role, report_key):
        return JsonResponse({"status": "error", "detail": "Недостаточно прав"}, status=403)

    try:
        payload = build_report_data(report_key, request.GET)
    except Exception as exc:
        return JsonResponse({"status": "error", "detail": str(exc)}, status=502)

    return JsonResponse({"status": "ok", "report": report.key, "data": payload})


@login_required
@require_GET
def report_meta_api(request: HttpRequest, report_key: str):
    report = get_report_definition(report_key)
    if report is None:
        return JsonResponse({"status": "error", "detail": "Отчёт не найден"}, status=404)

    if not can_access_report(request.user.role, report_key):
        return JsonResponse({"status": "error", "detail": "Недостаточно прав"}, status=403)

    try:
        payload = build_report_meta(report_key, request.GET)
    except Exception as exc:
        return JsonResponse({"status": "error", "detail": str(exc)}, status=502)

    return JsonResponse({"status": "ok", "report": report.key, "data": payload})


@login_required
@require_GET
def report_export_api(request: HttpRequest, report_key: str, export_format: str):
    report = get_report_definition(report_key)
    if report is None:
        return JsonResponse({"status": "error", "detail": "Отчёт не найден"}, status=404)
    if not can_access_report(request.user.role, report_key):
        return JsonResponse({"status": "error", "detail": "Недостаточно прав"}, status=403)

    try:
        payload = build_report_data(report_key, request.GET)
    except Exception as exc:
        return JsonResponse({"status": "error", "detail": str(exc)}, status=502)

    if export_format == "pdf":
        return render_report_pdf_response(
            report_key=report.key,
            report_title=report.title,
            filters=dict(request.GET.lists()),
            data=payload,
        )
    if export_format in {"xls", "excel"}:
        return render_report_excel_response(
            report_key=report.key,
            report_title=report.title,
            filters=dict(request.GET.lists()),
            data=payload,
        )
    return JsonResponse({"status": "error", "detail": "Неподдерживаемый формат"}, status=400)


@login_required
@require_GET
def rop_report_api(request: HttpRequest):
    return report_api(request, "rop_funnel")


@login_required
@require_GET
def managers_deals_chart_api(request: HttpRequest):
    period = request.GET.get("period", "week")
    return JsonResponse({"status": "ok", "data": manager_deals_chart(period)})


@login_required
@require_GET
def stages_deals_chart_api(request: HttpRequest):
    period = request.GET.get("period", "week")
    return JsonResponse({"status": "ok", "data": stage_deals_chart(period)})
