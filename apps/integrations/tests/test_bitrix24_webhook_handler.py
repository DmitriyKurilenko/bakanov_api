from unittest.mock import patch, MagicMock

from django.test import SimpleTestCase, override_settings

from apps.integrations.services.bitrix24_webhook_handler import (
    Bitrix24WebhookProcessor,
    Bitrix24WebhookResult,
    extract_webhook_payload,
    verify_inbound_token,
)


class ExtractWebhookPayloadTests(SimpleTestCase):
    def test_form_encoded_style(self):
        data = {
            "event": "ONCRMLEADADD",
            "data[FIELDS][ID]": "123",
            "auth[application_token]": "secret",
        }
        event, entity_id, token = extract_webhook_payload(data)
        self.assertEqual(event, "ONCRMLEADADD")
        self.assertEqual(entity_id, 123)
        self.assertEqual(token, "secret")

    def test_json_style(self):
        data = {
            "event": "ONCRMDEALUPDATE",
            "data": {"FIELDS": {"ID": 456}},
            "auth": {"application_token": "tok"},
        }
        event, entity_id, token = extract_webhook_payload(data)
        self.assertEqual(event, "ONCRMDEALUPDATE")
        self.assertEqual(entity_id, 456)
        self.assertEqual(token, "tok")

    def test_missing_fields(self):
        event, entity_id, token = extract_webhook_payload({})
        self.assertEqual(event, "")
        self.assertIsNone(entity_id)
        self.assertEqual(token, "")

    def test_non_numeric_id_ignored(self):
        data = {
            "event": "ONCRMLEADADD",
            "data[FIELDS][ID]": "abc",
            "auth[application_token]": "secret",
        }
        event, entity_id, token = extract_webhook_payload(data)
        self.assertIsNone(entity_id)


@override_settings(BITRIX24_INBOUND_TOKEN="valid-token")
class VerifyInboundTokenTests(SimpleTestCase):
    def test_valid_token(self):
        self.assertTrue(verify_inbound_token("valid-token"))

    def test_invalid_token(self):
        self.assertFalse(verify_inbound_token("wrong-token"))

    @override_settings(BITRIX24_INBOUND_TOKEN="")
    def test_empty_config_rejects_all(self):
        self.assertFalse(verify_inbound_token("anything"))


class Bitrix24WebhookProcessorTests(SimpleTestCase):
    def test_empty_event_returns_error(self):
        processor = Bitrix24WebhookProcessor()
        result = processor.process(event="", entity_id=None)
        self.assertEqual(result.status, "error")
        self.assertIn("Missing event", result.detail)

    def test_unknown_event_returns_skipped(self):
        processor = Bitrix24WebhookProcessor()
        result = processor.process(event="SOME_UNKNOWN", entity_id=1)
        self.assertEqual(result.status, "skipped")

    def test_missing_entity_id_returns_error(self):
        processor = Bitrix24WebhookProcessor()
        result = processor.process(event="ONCRMLEADADD", entity_id=None)
        self.assertEqual(result.status, "error")
        self.assertIn("entity ID", result.detail)

    def test_delete_event_does_not_fetch(self):
        processor = Bitrix24WebhookProcessor()
        result = processor.process(event="ONCRMLEADDELETE", entity_id=42)
        self.assertEqual(result.status, "ok")
        self.assertIn("Delete", result.detail)
        self.assertEqual(result.entity_data, {})

    @patch(
        "apps.integrations.services.bitrix24_webhook_handler.Bitrix24Client.from_settings"
    )
    def test_lead_add_fetches_entity(self, mock_from_settings):
        mock_client = MagicMock()
        mock_client.get_lead.return_value = {"ID": "10", "TITLE": "Lead"}
        mock_from_settings.return_value = mock_client

        processor = Bitrix24WebhookProcessor()
        result = processor.process(event="ONCRMLEADADD", entity_id=10)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.entity_id, 10)
        self.assertEqual(result.entity_data["TITLE"], "Lead")
        mock_client.get_lead.assert_called_once_with(10)

    @patch(
        "apps.integrations.services.bitrix24_webhook_handler.Bitrix24Client.from_settings"
    )
    def test_deal_update_fetches_entity(self, mock_from_settings):
        mock_client = MagicMock()
        mock_client.get_deal.return_value = {"ID": "5", "TITLE": "Deal"}
        mock_from_settings.return_value = mock_client

        processor = Bitrix24WebhookProcessor()
        result = processor.process(event="ONCRMDEALUPDATE", entity_id=5)

        self.assertEqual(result.status, "ok")
        mock_client.get_deal.assert_called_once_with(5)

    @patch(
        "apps.integrations.services.bitrix24_webhook_handler.Bitrix24Client.from_settings"
    )
    def test_fetch_failure_returns_empty_data(self, mock_from_settings):
        mock_client = MagicMock()
        mock_client.get_lead.side_effect = Exception("connection error")
        mock_from_settings.return_value = mock_client

        processor = Bitrix24WebhookProcessor()
        result = processor.process(event="ONCRMLEADADD", entity_id=10)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.entity_data, {})


class Bitrix24WebhookResultTests(SimpleTestCase):
    def test_as_dict(self):
        result = Bitrix24WebhookResult(
            event="ONCRMLEADADD",
            entity_id=10,
            status="ok",
            detail="",
            entity_data={"ID": "10"},
        )
        d = result.as_dict()
        self.assertEqual(d["event"], "ONCRMLEADADD")
        self.assertEqual(d["entity_id"], 10)
        self.assertEqual(d["status"], "ok")
        # entity_data is intentionally not in as_dict (internal)
        self.assertNotIn("entity_data", d)
