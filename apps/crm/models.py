from django.conf import settings
from django.db import models
from django.utils import timezone


class DealSnapshot(models.Model):
    amo_deal_id = models.BigIntegerField(unique=True)
    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    responsible_user_id = models.BigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class CallAnalysis(models.Model):
    deal = models.ForeignKey(DealSnapshot, on_delete=models.CASCADE, related_name="call_analyses", null=True, blank=True)
    call_id = models.CharField(max_length=128, db_index=True)
    audio_file = models.FileField(upload_to="calls/%Y/%m/%d/", blank=True)
    audio_source_url = models.URLField(blank=True)
    raw_payload = models.JSONField(default=dict, blank=True)
    stt_provider = models.CharField(max_length=32, blank=True)
    transcript_segments = models.JSONField(default=list, blank=True)
    transcript = models.TextField(blank=True)
    ai_provider = models.CharField(max_length=32, blank=True)
    analysis = models.TextField(blank=True)
    recommendations = models.TextField(blank=True)
    processing_error = models.TextField(blank=True)
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class AmoManagerProfile(models.Model):
    amo_user_id = models.BigIntegerField(unique=True)
    name = models.CharField(max_length=255)
    is_amo_active = models.BooleanField(default=True)  # active in amoCRM
    is_active = models.BooleanField(default=True)  # active in this service (reports/assignment)
    max_active_deals = models.PositiveIntegerField(default=10)
    django_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="amo_manager_profiles",
    )
    last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "amo_user_id"]

    def __str__(self) -> str:
        return f"{self.name} ({self.amo_user_id})"

    def ensure_default_schedule(self) -> None:
        existing = {item.weekday for item in self.weekday_schedules.all()}
        missing = [day for day in range(7) if day not in existing]
        if not missing:
            return
        schedule_rows = [
            ManagerWeekdaySchedule(
                manager=self,
                weekday=day,
                is_working=day < 5,
            )
            for day in missing
        ]
        ManagerWeekdaySchedule.objects.bulk_create(schedule_rows)


class ManagerWeekdaySchedule(models.Model):
    class Weekday(models.IntegerChoices):
        MONDAY = 0, "Пн"
        TUESDAY = 1, "Вт"
        WEDNESDAY = 2, "Ср"
        THURSDAY = 3, "Чт"
        FRIDAY = 4, "Пт"
        SATURDAY = 5, "Сб"
        SUNDAY = 6, "Вс"

    manager = models.ForeignKey(AmoManagerProfile, on_delete=models.CASCADE, related_name="weekday_schedules")
    weekday = models.PositiveSmallIntegerField(choices=Weekday.choices)
    is_working = models.BooleanField(default=True)

    class Meta:
        unique_together = ("manager", "weekday")
        ordering = ["manager_id", "weekday"]

    def __str__(self) -> str:
        return f"{self.manager.name}: {self.get_weekday_display()} ({'work' if self.is_working else 'off'})"


class ManagerDayOff(models.Model):
    manager = models.ForeignKey(AmoManagerProfile, on_delete=models.CASCADE, related_name="days_off")
    date = models.DateField()
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("manager", "date")
        ordering = ["-date", "manager__name"]

    def __str__(self) -> str:
        return f"{self.manager.name} / {self.date}"


class AmoLead(models.Model):
    amo_lead_id = models.BigIntegerField(unique=True)
    name = models.CharField(max_length=255, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    pipeline_id = models.BigIntegerField(null=True, blank=True)
    status_id = models.BigIntegerField(null=True, blank=True)
    responsible_user_id = models.BigIntegerField(null=True, blank=True)
    assigned_manager = models.ForeignKey(
        AmoManagerProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="leads",
    )
    is_closed = models.BooleanField(default=False)
    is_success = models.BooleanField(default=False)
    amo_created_at = models.DateTimeField(null=True, blank=True)
    amo_updated_at = models.DateTimeField(null=True, blank=True)
    first_received_at = models.DateTimeField(default=timezone.now)
    last_webhook_at = models.DateTimeField(default=timezone.now)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-first_received_at", "-amo_lead_id"]

    def __str__(self) -> str:
        return f"{self.amo_lead_id} {self.name}".strip()


class AmoLeadAssignmentEvent(models.Model):
    amo_lead = models.ForeignKey(AmoLead, on_delete=models.CASCADE, related_name="assignment_events")
    manager = models.ForeignKey(AmoManagerProfile, on_delete=models.SET_NULL, null=True, blank=True)
    previous_responsible_user_id = models.BigIntegerField(null=True, blank=True)
    new_responsible_user_id = models.BigIntegerField(null=True, blank=True)
    reason = models.CharField(max_length=255, default="auto_assignment")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.amo_lead_id} -> {self.new_responsible_user_id}"

    @property
    def amo_lead_id(self) -> int:
        return self.amo_lead.amo_lead_id


class GoogleFormReport(models.Model):
    class FormType(models.TextChoices):
        MENU = "menu", "menu"
        CRUISE = "cruise", "cruise"

    class Language(models.TextChoices):
        RU = "ru", "ru"
        EN = "en", "en"

    lead_id = models.BigIntegerField(db_index=True)
    form_type = models.CharField(max_length=16, choices=FormType.choices)
    language = models.CharField(max_length=2, choices=Language.choices)
    payload = models.JSONField(default=dict, blank=True)
    file = models.FileField(upload_to="menus/%Y/%m/%d/")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["lead_id", "form_type", "language", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.form_type}:{self.language} lead={self.lead_id} id={self.id}"
