from django.urls import path

from apps.dashboard.views import (
    analytics_home,
    analytics_report_page,
    dashboard_home,
    manager_day_off_add,
    manager_day_off_delete,
    manager_update,
    managers_deals_chart_api,
    managers_page,
    managers_sync,
    placeholder_page,
    report_api,
    report_export_api,
    report_meta_api,
    reports_home,
    rop_report_api,
    settings_page,
    stages_deals_chart_api,
    sync_reports_meta,
)

app_name = "dashboard"

urlpatterns = [
    path("", dashboard_home, name="home"),
    path("reports/meta/sync/", sync_reports_meta, name="reports-meta-sync"),
    path("analytics/", analytics_home, name="analytics"),
    path("reports/rop-funnel/", analytics_report_page, {"report_key": "rop_funnel"}, name="reports-rop"),
    path("reports/", reports_home, name="reports-home"),
    path("managers/", managers_page, name="managers"),
    path("managers/sync/", managers_sync, name="managers-sync"),
    path("managers/<int:manager_id>/update/", manager_update, name="manager-update"),
    path("managers/<int:manager_id>/days-off/add/", manager_day_off_add, name="manager-dayoff-add"),
    path(
        "managers/<int:manager_id>/days-off/<int:day_off_id>/delete/",
        manager_day_off_delete,
        name="manager-dayoff-delete",
    ),
    path(
        "calls/",
        placeholder_page,
        {"section_key": "calls", "section_title": "Звонки"},
        name="calls",
    ),
    path(
        "messages/",
        placeholder_page,
        {"section_key": "messages", "section_title": "Сообщения"},
        name="messages",
    ),
    path("settings/", settings_page, name="settings"),
    path("reports/api/<str:report_key>/", report_api, name="report-api"),
    path("reports/api/<str:report_key>/export/<str:export_format>/", report_export_api, name="report-export-api"),
    path("reports/api/<str:report_key>/meta/", report_meta_api, name="report-meta-api"),
    path("analytics/reports/api/<str:report_key>/", report_api, name="report-api-legacy"),
    path("analytics/reports/api/<str:report_key>/meta/", report_meta_api, name="report-meta-api-legacy"),
    path("api/rop-report/", rop_report_api, name="rop-report"),
    path("api/analytics/managers-deals/", managers_deals_chart_api, name="analytics-managers-deals"),
    path("api/analytics/stages-deals/", stages_deals_chart_api, name="analytics-stages-deals"),
]
