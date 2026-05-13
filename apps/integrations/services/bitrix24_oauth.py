import logging
from datetime import timedelta

import requests
from django.conf import settings
from django.utils import timezone

from apps.integrations.models import Bitrix24Portal

logger = logging.getLogger(__name__)

OAUTH_TOKEN_URL = "https://oauth.bitrix.info/oauth/token/"


def save_portal_from_request(data: dict) -> Bitrix24Portal:
    """Create or update a portal record from Bitrix24 install/app POST data."""
    member_id = data["member_id"]
    domain = data.get("DOMAIN", "")
    access_token = data.get("AUTH_ID", "")
    refresh_token = data.get("REFRESH_ID", "")
    expires_in = int(data.get("AUTH_EXPIRES", 3600))
    app_status = data.get("status", "L")

    portal, _ = Bitrix24Portal.objects.update_or_create(
        member_id=member_id,
        defaults={
            "domain": domain,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "access_token_expires_at": timezone.now()
            + timedelta(seconds=expires_in),
            "app_status": app_status,
            "is_active": True,
        },
    )
    logger.info("Saved portal %s (domain=%s)", member_id, domain)
    return portal


def refresh_tokens(portal: Bitrix24Portal) -> Bitrix24Portal:
    """Refresh access / refresh tokens for a portal via Bitrix24 OAuth."""
    app_id = getattr(settings, "BITRIX24_APP_ID", "")
    app_secret = getattr(settings, "BITRIX24_APP_SECRET", "")
    if not app_id or not app_secret:
        raise ValueError(
            "BITRIX24_APP_ID and BITRIX24_APP_SECRET must be configured."
        )

    response = requests.get(
        OAUTH_TOKEN_URL,
        params={
            "grant_type": "refresh_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "refresh_token": portal.refresh_token,
        },
        timeout=int(getattr(settings, "BITRIX24_TIMEOUT", 30)),
    )
    response.raise_for_status()
    payload = response.json()

    if "error" in payload:
        raise requests.RequestException(
            f"OAuth refresh failed for {portal.domain}: "
            f"{payload['error']} — {payload.get('error_description', '')}"
        )

    portal.access_token = payload["access_token"]
    portal.refresh_token = payload["refresh_token"]
    portal.access_token_expires_at = timezone.now() + timedelta(
        seconds=int(payload.get("expires_in", 3600))
    )
    portal.save(
        update_fields=[
            "access_token",
            "refresh_token",
            "access_token_expires_at",
            "updated_at",
        ]
    )
    logger.info("Refreshed tokens for portal %s", portal.member_id)
    return portal


def ensure_valid_token(portal: Bitrix24Portal) -> Bitrix24Portal:
    """Return portal with a guaranteed non-expired access token."""
    if portal.is_token_expired:
        portal = refresh_tokens(portal)
    return portal
