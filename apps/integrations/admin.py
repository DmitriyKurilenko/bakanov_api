from django.contrib import admin

from apps.integrations.models import Bitrix24Portal


@admin.register(Bitrix24Portal)
class Bitrix24PortalAdmin(admin.ModelAdmin):
    list_display = ("domain", "member_id", "app_status", "is_active", "installed_at")
    list_filter = ("is_active", "app_status")
    search_fields = ("domain", "member_id")
    readonly_fields = ("access_token", "refresh_token", "access_token_expires_at", "created_at", "updated_at")
