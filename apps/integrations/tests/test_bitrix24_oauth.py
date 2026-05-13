from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.integrations.models import Bitrix24Portal
from apps.integrations.services.bitrix24_oauth import (
    ensure_valid_token,
    refresh_tokens,
    save_portal_from_request,
)


class SavePortalFromRequestTests(TestCase):
    def test_creates_new_portal(self):
        data = {
            "member_id": "abc123",
            "DOMAIN": "test.bitrix24.ru",
            "AUTH_ID": "access-tok",
            "REFRESH_ID": "refresh-tok",
            "AUTH_EXPIRES": "3600",
            "status": "L",
        }
        portal = save_portal_from_request(data)
        self.assertEqual(portal.member_id, "abc123")
        self.assertEqual(portal.domain, "test.bitrix24.ru")
        self.assertEqual(portal.access_token, "access-tok")
        self.assertTrue(portal.is_active)

    def test_updates_existing_portal(self):
        Bitrix24Portal.objects.create(
            member_id="abc123",
            domain="old.bitrix24.ru",
            access_token="old-tok",
            refresh_token="old-ref",
        )
        data = {
            "member_id": "abc123",
            "DOMAIN": "new.bitrix24.ru",
            "AUTH_ID": "new-tok",
            "REFRESH_ID": "new-ref",
            "AUTH_EXPIRES": "7200",
            "status": "F",
        }
        portal = save_portal_from_request(data)
        self.assertEqual(portal.domain, "new.bitrix24.ru")
        self.assertEqual(portal.access_token, "new-tok")
        self.assertEqual(Bitrix24Portal.objects.count(), 1)


@override_settings(
    BITRIX24_APP_ID="app-id",
    BITRIX24_APP_SECRET="app-secret",
    BITRIX24_TIMEOUT=10,
)
class RefreshTokensTests(TestCase):
    def _make_portal(self, **kwargs):
        defaults = dict(
            member_id="test-member",
            domain="test.bitrix24.ru",
            access_token="old-access",
            refresh_token="old-refresh",
            access_token_expires_at=timezone.now() - timedelta(hours=1),
        )
        defaults.update(kwargs)
        return Bitrix24Portal.objects.create(**defaults)

    @patch("apps.integrations.services.bitrix24_oauth.requests.get")
    def test_refresh_success(self, mock_get):
        portal = self._make_portal()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 3600,
        }
        mock_get.return_value = mock_response

        result = refresh_tokens(portal)
        self.assertEqual(result.access_token, "new-access")
        self.assertEqual(result.refresh_token, "new-refresh")
        mock_get.assert_called_once()

    @patch("apps.integrations.services.bitrix24_oauth.requests.get")
    def test_refresh_api_error(self, mock_get):
        portal = self._make_portal()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "error": "expired_token",
            "error_description": "Token expired",
        }
        mock_get.return_value = mock_response

        from requests import RequestException

        with self.assertRaises(RequestException):
            refresh_tokens(portal)

    @override_settings(BITRIX24_APP_ID="", BITRIX24_APP_SECRET="")
    def test_refresh_raises_without_credentials(self):
        portal = self._make_portal()
        with self.assertRaises(ValueError):
            refresh_tokens(portal)


class EnsureValidTokenTests(TestCase):
    def test_non_expired_returns_same(self):
        portal = Bitrix24Portal.objects.create(
            member_id="m1",
            domain="d.bitrix24.ru",
            access_token="tok",
            refresh_token="ref",
            access_token_expires_at=timezone.now() + timedelta(hours=1),
        )
        result = ensure_valid_token(portal)
        self.assertEqual(result.pk, portal.pk)
        self.assertEqual(result.access_token, "tok")

    @override_settings(
        BITRIX24_APP_ID="app-id",
        BITRIX24_APP_SECRET="app-secret",
    )
    @patch("apps.integrations.services.bitrix24_oauth.requests.get")
    def test_expired_triggers_refresh(self, mock_get):
        portal = Bitrix24Portal.objects.create(
            member_id="m2",
            domain="d.bitrix24.ru",
            access_token="old",
            refresh_token="ref",
            access_token_expires_at=timezone.now() - timedelta(hours=1),
        )
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "refreshed",
            "refresh_token": "new-ref",
            "expires_in": 3600,
        }
        mock_get.return_value = mock_response

        result = ensure_valid_token(portal)
        self.assertEqual(result.access_token, "refreshed")
