from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings


@override_settings(BITRIX24_INBOUND_TOKEN="spam-secret")
class Bitrix24SpamWebhookApiTests(SimpleTestCase):
    endpoint = "/api/integrations/webhooks/bitrix24/spam-lead"

    def test_valid_lead_webhook_queues_task(self):
        with patch(
            "apps.integrations.api.process_bitrix24_spam_lead_webhook.delay",
            return_value=SimpleNamespace(id="task-spam-1"),
        ) as mock_delay:
            response = self.client.post(
                self.endpoint,
                data={
                    "entity_type": "lead",
                    "entity_id": "123",
                    "auth[application_token]": "spam-secret",
                },
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["entity_type"], "lead")
        self.assertEqual(body["entity_id"], 123)
        self.assertEqual(body["task_id"], "task-spam-1")
        mock_delay.assert_called_once_with(entity_id=123, entity_type="lead")

    def test_valid_deal_webhook_queues_task(self):
        with patch(
            "apps.integrations.api.process_bitrix24_spam_lead_webhook.delay",
            return_value=SimpleNamespace(id="task-spam-2"),
        ) as mock_delay:
            response = self.client.post(
                self.endpoint,
                data={
                    "entity_type": "deal",
                    "entity_id": "456",
                    "auth[application_token]": "spam-secret",
                },
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["entity_type"], "deal")
        self.assertEqual(body["entity_id"], 456)
        mock_delay.assert_called_once_with(entity_id=456, entity_type="deal")

    def test_no_token_required_for_standard_outgoing_webhook(self):
        """DEC-009: standard Bitrix24 outgoing webhooks do not carry a token
        matching BITRIX24_INBOUND_TOKEN, so this endpoint is intentionally
        token-free. A request with no/foreign token must still be queued."""
        with patch(
            "apps.integrations.api.process_bitrix24_spam_lead_webhook.delay",
            return_value=SimpleNamespace(id="task-no-token"),
        ) as mock_delay:
            response = self.client.post(
                self.endpoint,
                data={
                    "entity_type": "lead",
                    "entity_id": "123",
                    "auth[application_token]": "wrong",
                },
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["entity_id"], 123)
        mock_delay.assert_called_once_with(entity_id=123, entity_type="lead")

    def test_missing_entity_id(self):
        response = self.client.post(
            self.endpoint,
            data={
                "entity_type": "lead",
                "auth[application_token]": "spam-secret",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "error")
        self.assertIn("entity_id", body["detail"].lower())

    def test_invalid_entity_id(self):
        response = self.client.post(
            self.endpoint,
            data={
                "entity_type": "lead",
                "entity_id": "abc",
                "auth[application_token]": "spam-secret",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "error")
        self.assertIn("Invalid entity_id", body["detail"])

    def test_json_payload_works(self):
        with patch(
            "apps.integrations.api.process_bitrix24_spam_lead_webhook.delay",
            return_value=SimpleNamespace(id="task-spam-json"),
        ) as mock_delay:
            response = self.client.post(
                self.endpoint,
                data={
                    "entity_type": "lead",
                    "entity_id": 789,
                    "auth": {"application_token": "spam-secret"},
                },
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["entity_id"], 789)
        mock_delay.assert_called_once_with(entity_id=789, entity_type="lead")

    def test_default_entity_type_is_lead(self):
        with patch(
            "apps.integrations.api.process_bitrix24_spam_lead_webhook.delay",
            return_value=SimpleNamespace(id="task-spam-def"),
        ) as mock_delay:
            response = self.client.post(
                self.endpoint,
                data={
                    "entity_id": "111",
                    "auth[application_token]": "spam-secret",
                },
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["entity_type"], "lead")
        mock_delay.assert_called_once_with(entity_id=111, entity_type="lead")
