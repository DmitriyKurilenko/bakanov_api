from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.integrations.models import Bitrix24Portal
from apps.integrations.services.bitrix24_contract_service import (
    Bitrix24ContractService,
    _b24_contact_email,
    _b24_contact_phone,
    _b24_field,
    _b24_multi_field,
    _format_b24_date,
)


class B24FieldHelpersTests(TestCase):
    def test_b24_field_scalar(self):
        self.assertEqual(_b24_field({"UF_CRM_1": "value"}, "UF_CRM_1"), "value")

    def test_b24_field_none(self):
        self.assertIsNone(_b24_field({}, "UF_CRM_1"))
        self.assertIsNone(_b24_field({"UF_CRM_1": None}, "UF_CRM_1"))
        self.assertIsNone(_b24_field({"UF_CRM_1": ""}, "UF_CRM_1"))
        self.assertIsNone(_b24_field({"UF_CRM_1": []}, "UF_CRM_1"))

    def test_b24_field_list(self):
        self.assertEqual(_b24_field({"UF_CRM_1": ["a", "b"]}, "UF_CRM_1"), "a")

    def test_b24_multi_field(self):
        self.assertEqual(_b24_multi_field({"UF_CRM_1": ["a", "b"]}, "UF_CRM_1"), ["a", "b"])

    def test_b24_multi_field_empty(self):
        self.assertEqual(_b24_multi_field({}, "UF_CRM_1"), [])
        self.assertEqual(_b24_multi_field({"UF_CRM_1": None}, "UF_CRM_1"), [])

    def test_b24_contact_phone(self):
        contact = {"PHONE": [{"VALUE": "+79991234567", "VALUE_TYPE": "WORK"}]}
        self.assertEqual(_b24_contact_phone(contact), "+79991234567")

    def test_b24_contact_phone_empty(self):
        self.assertEqual(_b24_contact_phone({}), "")
        self.assertEqual(_b24_contact_phone({"PHONE": []}), "")

    def test_b24_contact_email(self):
        contact = {"EMAIL": [{"VALUE": "test@example.com", "VALUE_TYPE": "WORK"}]}
        self.assertEqual(_b24_contact_email(contact), "test@example.com")

    def test_b24_contact_email_empty(self):
        self.assertEqual(_b24_contact_email({}), "")

    def test_format_b24_date_dd_mm_yyyy(self):
        self.assertEqual(_format_b24_date("15.06.2025"), "15.06.2025")

    def test_format_b24_date_iso(self):
        self.assertEqual(_format_b24_date("2025-06-15"), "15.06.2025")

    def test_format_b24_date_unix(self):
        self.assertEqual(_format_b24_date("1750000000"), "15.06.2025")

    def test_format_b24_date_empty(self):
        self.assertEqual(_format_b24_date(None), "")
        self.assertEqual(_format_b24_date(""), "")


class Bitrix24ContractServiceBuildContextTests(TestCase):
    def _make_service(self):
        client = MagicMock()
        return Bitrix24ContractService(client)

    def test_build_context_from_deal_basic(self):
        service = self._make_service()
        deal = {
            "ID": "123",
            "OPPORTUNITY": "5000",
            "TITLE": "Test Deal",
        }
        context = service.build_context_from_deal(deal)
        self.assertEqual(context["number"], "123")
        self.assertEqual(context["price_eur"], 5000.0)
        self.assertFalse(context["is_legal_entity"])

    def test_build_context_with_contact(self):
        service = self._make_service()
        deal = {"ID": "123", "OPPORTUNITY": "5000"}
        contact = {
            "NAME": "Иван",
            "LAST_NAME": "Иванов",
            "EMAIL": [{"VALUE": "ivan@test.com"}],
            "PHONE": [{"VALUE": "+79991234567"}],
        }
        context = service.build_context_from_deal(deal, contact=contact)
        self.assertEqual(context["client_fullname"], "Иванов Иван")
        self.assertEqual(context["email"], "ivan@test.com")
        self.assertEqual(context["phone"], "+79991234567")

    def test_build_context_with_company(self):
        service = self._make_service()
        deal = {"ID": "123", "OPPORTUNITY": "5000"}
        company = {"TITLE": "ООО Рога"}
        context = service.build_context_from_deal(deal, company=company)
        self.assertTrue(context["is_legal_entity"])
        self.assertEqual(context["company_fullname"], "ООО Рога")

    def test_build_context_with_overrides(self):
        service = self._make_service()
        deal = {"ID": "123", "OPPORTUNITY": "5000"}
        overrides = {"price_eur": "8000", "marina": "Турция"}
        context = service.build_context_from_deal(deal, overrides=overrides)
        self.assertEqual(context["price_eur"], 8000.0)
        self.assertEqual(context["marina"], "Турция")


class Bitrix24ContractFormViewTests(TestCase):
    def test_get_returns_405(self):
        resp = self.client.get("/bitrix24/contract/")
        self.assertEqual(resp.status_code, 405)

    def test_post_without_member_id_returns_400(self):
        resp = self.client.post("/bitrix24/contract/")
        self.assertEqual(resp.status_code, 400)

    def test_post_unknown_portal_returns_404(self):
        resp = self.client.post("/bitrix24/contract/", {"member_id": "unknown"})
        self.assertEqual(resp.status_code, 404)

    def test_post_success_renders_form(self):
        Bitrix24Portal.objects.create(
            member_id="contract-member",
            domain="c.bitrix24.ru",
            access_token="t",
            refresh_token="r",
        )
        resp = self.client.post("/bitrix24/contract/", {"member_id": "contract-member"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"contractApp", resp.content)
        self.assertIn(b"contract-member", resp.content)

    def test_no_csrf_required(self):
        resp = self.client.post("/bitrix24/contract/", {"member_id": "x"})
        self.assertNotEqual(resp.status_code, 403)

    def test_xframe_header_absent(self):
        Bitrix24Portal.objects.create(
            member_id="xf-contract",
            domain="xf.bitrix24.ru",
            access_token="t",
            refresh_token="r",
        )
        resp = self.client.post("/bitrix24/contract/", {"member_id": "xf-contract"})
        self.assertNotIn("X-Frame-Options", resp)


class Bitrix24ContractGenerateViewTests(TestCase):
    def test_get_returns_405(self):
        resp = self.client.get("/bitrix24/contract/generate/")
        self.assertEqual(resp.status_code, 405)

    def test_post_invalid_json_returns_400(self):
        resp = self.client.post(
            "/bitrix24/contract/generate/",
            data="not json",
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_post_missing_member_id_returns_400(self):
        resp = self.client.post(
            "/bitrix24/contract/generate/",
            data='{"deal_id": 123}',
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_post_missing_deal_id_returns_400(self):
        resp = self.client.post(
            "/bitrix24/contract/generate/",
            data='{"member_id": "m1"}',
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_post_unknown_portal_returns_404(self):
        resp = self.client.post(
            "/bitrix24/contract/generate/",
            data='{"member_id": "unknown", "deal_id": 123}',
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 404)

    @patch("apps.integrations.views.Bitrix24ContractService")
    @patch("apps.integrations.views.send_contract_email")
    def test_post_success_generates_contract(self, mock_email, mock_service_cls):
        Bitrix24Portal.objects.create(
            member_id="gen-member",
            domain="g.bitrix24.ru",
            access_token="t",
            refresh_token="r",
        )
        from pathlib import Path
        import tempfile

        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp.write(b"%PDF-1.4 test")
        tmp.close()

        mock_result = MagicMock()
        mock_result.file_url = "/media/contracts/test.pdf"
        mock_result.file_path = Path(tmp.name)
        mock_result.context = {}

        mock_service = MagicMock()
        mock_service.render_contract.return_value = mock_result
        mock_service_cls.from_portal.return_value = mock_service

        resp = self.client.post(
            "/bitrix24/contract/generate/",
            data='{"member_id": "gen-member", "deal_id": 456}',
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("file_url", data)
        mock_service.render_contract.assert_called_once_with(456, overrides={})
