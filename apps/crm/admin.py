from django.contrib import admin

from apps.crm.models import AmoLead, AmoLeadAssignmentEvent, AmoManagerProfile, CallAnalysis, ManagerDayOff, ManagerWeekdaySchedule


class ManagerWeekdayScheduleInline(admin.TabularInline):
    model = ManagerWeekdaySchedule
    extra = 0


class ManagerDayOffInline(admin.TabularInline):
    model = ManagerDayOff
    extra = 0


@admin.register(AmoManagerProfile)
class AmoManagerProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "amo_user_id", "is_amo_active", "is_active", "max_active_deals", "last_synced_at")
    list_filter = ("is_amo_active", "is_active")
    search_fields = ("name", "amo_user_id")
    inlines = [ManagerWeekdayScheduleInline, ManagerDayOffInline]


@admin.register(AmoLead)
class AmoLeadAdmin(admin.ModelAdmin):
    list_display = ("amo_lead_id", "name", "assigned_manager", "responsible_user_id", "is_closed", "status_id", "first_received_at")
    list_filter = ("is_closed", "is_success")
    search_fields = ("amo_lead_id", "name")


@admin.register(AmoLeadAssignmentEvent)
class AmoLeadAssignmentEventAdmin(admin.ModelAdmin):
    list_display = ("amo_lead", "manager", "new_responsible_user_id", "reason", "created_at")
    list_filter = ("reason",)
    search_fields = ("amo_lead__amo_lead_id", "manager__name")


@admin.register(CallAnalysis)
class CallAnalysisAdmin(admin.ModelAdmin):
    list_display = ("call_id", "deal", "stt_provider", "ai_provider", "created_at")
    search_fields = ("call_id", "deal__amo_deal_id", "transcript", "recommendations")
    readonly_fields = ("created_at", "updated_at")
