from unittest.mock import patch, MagicMock

import requests
from django.test import SimpleTestCase, override_settings

from apps.integrations.services.bitrix24_service import Bitrix24Client


@override_settings(BITRIX24_WEBHOOK_URL="https://test.bitrix24.ru/rest/1/test-token")
class Bitrix24ClientFromSettingsTests(SimpleTestCase):
    def test_from_settings_creates_client(self):
        client = Bitrix24Client.from_settings()
        self.assertEqual(
            client.webhook_url,
            "https://test.bitrix24.ru/rest/1/test-token",
        )
        self.assertEqual(client.timeout, 30)

    @override_settings(BITRIX24_WEBHOOK_URL="", BITRIX24_TIMEOUT=15)
    def test_from_settings_raises_when_url_empty(self):
        with self.assertRaises(ValueError):
            Bitrix24Client.from_settings()


class Bitrix24ClientCallTests(SimpleTestCase):
    def setUp(self):
        self.client = Bitrix24Client(
            webhook_url="https://test.bitrix24.ru/rest/1/tok",
            timeout=10,
        )

    @patch("apps.integrations.services.bitrix24_service.requests.post")
    def test_call_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": {"ID": "42"}}
        mock_post.return_value = mock_response

        result = self.client._call("crm.lead.get", {"ID": 42})

        mock_post.assert_called_once_with(
            "https://test.bitrix24.ru/rest/1/tok/crm.lead.get",
            json={"ID": 42},
            timeout=10,
        )
        self.assertEqual(result, {"result": {"ID": "42"}})

    @patch("apps.integrations.services.bitrix24_service.requests.post")
    def test_call_http_error(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        with self.assertRaises(requests.RequestException):
            self.client._call("crm.lead.get", {"ID": 42})

    @patch("apps.integrations.services.bitrix24_service.requests.post")
    def test_call_api_error(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "error": "ACCESS_DENIED",
            "error_description": "Forbidden",
        }
        mock_post.return_value = mock_response

        with self.assertRaises(requests.RequestException) as ctx:
            self.client._call("crm.lead.get", {"ID": 42})
        self.assertIn("ACCESS_DENIED", str(ctx.exception))

    @patch("apps.integrations.services.bitrix24_service.requests.post")
    def test_get_lead(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {"ID": "42", "TITLE": "Test Lead"},
        }
        mock_post.return_value = mock_response

        lead = self.client.get_lead(42)
        self.assertEqual(lead["ID"], "42")
        self.assertEqual(lead["TITLE"], "Test Lead")

    @patch("apps.integrations.services.bitrix24_service.requests.post")
    def test_create_lead(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": 99}
        mock_post.return_value = mock_response

        lead_id = self.client.create_lead({"TITLE": "New Lead"})
        self.assertEqual(lead_id, 99)
        call_args = mock_post.call_args
        self.assertEqual(
            call_args[1]["json"],
            {"fields": {"TITLE": "New Lead"}},
        )

    @patch("apps.integrations.services.bitrix24_service.requests.post")
    def test_update_lead(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": True}
        mock_post.return_value = mock_response

        ok = self.client.update_lead(42, {"TITLE": "Updated"})
        self.assertTrue(ok)

    @patch("apps.integrations.services.bitrix24_service.requests.post")
    def test_get_deal(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {"ID": "7", "TITLE": "Deal"},
        }
        mock_post.return_value = mock_response

        deal = self.client.get_deal(7)
        self.assertEqual(deal["ID"], "7")

    @patch("apps.integrations.services.bitrix24_service.requests.post")
    def test_create_deal(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": 55}
        mock_post.return_value = mock_response

        deal_id = self.client.create_deal({"TITLE": "New Deal"})
        self.assertEqual(deal_id, 55)

    @patch("apps.integrations.services.bitrix24_service.requests.post")
    def test_get_contact(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {"ID": "3", "NAME": "John"},
        }
        mock_post.return_value = mock_response

        contact = self.client.get_contact(3)
        self.assertEqual(contact["NAME"], "John")

    @patch("apps.integrations.services.bitrix24_service.requests.post")
    def test_get_company(self, mock_post):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {"ID": "1", "TITLE": "Corp"},
        }
        mock_post.return_value = mock_response

        company = self.client.get_company(1)
        self.assertEqual(company["TITLE"], "Corp")

    @patch("apps.integrations.services.bitrix24_service.requests.post")
    def test_list_all_pagination(self, mock_post):
        page1 = MagicMock()
        page1.status_code = 200
        page1.json.return_value = {
            "result": [{"ID": "1"}, {"ID": "2"}],
            "next": 50,
            "total": 3,
        }
        page2 = MagicMock()
        page2.status_code = 200
        page2.json.return_value = {
            "result": [{"ID": "3"}],
            "total": 3,
        }
        mock_post.side_effect = [page1, page2]

        items = self.client.list_leads()
        self.assertEqual(len(items), 3)
        self.assertEqual(items[2]["ID"], "3")
