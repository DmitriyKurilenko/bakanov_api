from django.db import models
from django.utils import timezone


class Bitrix24Portal(models.Model):
    """Credentials for a connected Bitrix24 portal (local app)."""

    member_id = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="Unique portal identifier from Bitrix24.",
    )
    domain = models.CharField(
        max_length=255,
        help_text="Portal domain, e.g. company.bitrix24.ru",
    )
    access_token = models.CharField(max_length=512)
    refresh_token = models.CharField(max_length=512)
    access_token_expires_at = models.DateTimeField(null=True, blank=True)
    app_status = models.CharField(
        max_length=32,
        blank=True,
        help_text="L=local, F=free, D=demo, T=trial, P=paid",
    )
    is_active = models.BooleanField(default=True)
    installed_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-installed_at"]

    def __str__(self) -> str:
        return f"{self.domain} ({self.member_id})"

    @property
    def is_token_expired(self) -> bool:
        if not self.access_token_expires_at:
            return True
        return timezone.now() >= self.access_token_expires_at

    @property
    def rest_url(self) -> str:
        return f"https://{self.domain}/rest"
