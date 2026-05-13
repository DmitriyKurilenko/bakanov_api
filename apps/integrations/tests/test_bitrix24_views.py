from django.test import TestCase
from django.urls import reverse

from apps.integrations.models import Bitrix24Portal


class Bitrix24InstallViewTests(TestCase):
    def test_get_returns_405(self):
        resp = self.client.get(reverse("bitrix24-install"))
        self.assertEqual(resp.status_code, 405)

    def test_post_without_member_id_returns_400(self):
        resp = self.client.post(reverse("bitrix24-install"), {"DOMAIN": "x.bitrix24.ru"})
        self.assertEqual(resp.status_code, 400)

    def test_post_success_creates_portal(self):
        data = {
            "member_id": "inst-member",
            "DOMAIN": "new.bitrix24.ru",
            "AUTH_ID": "tok123",
            "REFRESH_ID": "ref123",
            "AUTH_EXPIRES": "3600",
            "status": "L",
        }
        resp = self.client.post(reverse("bitrix24-install"), data)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"installFinish", resp.content)
        self.assertTrue(Bitrix24Portal.objects.filter(member_id="inst-member").exists())

    def test_no_csrf_required(self):
        """Bitrix24 iframes cannot send CSRF tokens."""
        resp = self.client.post(
            reverse("bitrix24-install"),
            {"member_id": "csrf-test", "DOMAIN": "d.bitrix24.ru", "AUTH_ID": "t", "REFRESH_ID": "r"},
        )
        self.assertNotEqual(resp.status_code, 403)


class Bitrix24AppViewTests(TestCase):
    def test_get_returns_405(self):
        resp = self.client.get(reverse("bitrix24-app"))
        self.assertEqual(resp.status_code, 405)

    def test_post_unknown_portal_returns_404(self):
        resp = self.client.post(reverse("bitrix24-app"), {"member_id": "unknown"})
        self.assertEqual(resp.status_code, 404)

    def test_post_success_renders_app(self):
        Bitrix24Portal.objects.create(
            member_id="app-member",
            domain="app.bitrix24.ru",
            access_token="atok",
            refresh_token="rtok",
        )
        data = {
            "member_id": "app-member",
            "DOMAIN": "app.bitrix24.ru",
            "AUTH_ID": "fresh-tok",
            "REFRESH_ID": "fresh-ref",
            "AUTH_EXPIRES": "3600",
        }
        resp = self.client.post(reverse("bitrix24-app"), data)
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"bx24App", resp.content)
        self.assertIn(b"app.bitrix24.ru", resp.content)

    def test_inactive_portal_returns_404(self):
        Bitrix24Portal.objects.create(
            member_id="inactive",
            domain="x.bitrix24.ru",
            access_token="t",
            refresh_token="r",
            is_active=False,
        )
        resp = self.client.post(reverse("bitrix24-app"), {"member_id": "inactive"})
        self.assertEqual(resp.status_code, 404)

    def test_xframe_header_absent(self):
        """Iframe pages must not have X-Frame-Options."""
        Bitrix24Portal.objects.create(
            member_id="xframe",
            domain="xf.bitrix24.ru",
            access_token="t",
            refresh_token="r",
        )
        resp = self.client.post(reverse("bitrix24-app"), {"member_id": "xframe"})
        self.assertNotIn("X-Frame-Options", resp)
