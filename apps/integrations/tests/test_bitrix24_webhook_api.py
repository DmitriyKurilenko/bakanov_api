from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings


@override_settings(BITRIX24_INBOUND_TOKEN="test-secret-token")
class Bitrix24WebhookApiTests(SimpleTestCase):
    endpoint = "/api/integrations/webhooks/bitrix24"

    def test_valid_webhook_queues_task(self):
        with patch(
            "apps.integrations.api.process_bitrix24_webhook.delay",
            return_value=SimpleNamespace(id="task-abc"),
        ) as mock_delay:
            response = self.client.post(
                self.endpoint,
                data={
                    "event": "ONCRMLEADADD",
                    "data[FIELDS][ID]": "123",
                    "auth[application_token]": "test-secret-token",
                },
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["event"], "ONCRMLEADADD")
        self.assertEqual(body["entity_id"], 123)
        self.assertEqual(body["task_id"], "task-abc")
        mock_delay.assert_called_once_with(
            event="ONCRMLEADADD",
            entity_id=123,
        )

    def test_invalid_token_rejected(self):
        response = self.client.post(
            self.endpoint,
            data={
                "event": "ONCRMLEADADD",
                "data[FIELDS][ID]": "123",
                "auth[application_token]": "wrong-token",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "error")
        self.assertIn("Invalid token", body["detail"])

    @override_settings(BITRIX24_INBOUND_TOKEN="")
    def test_empty_inbound_token_rejects_all(self):
        response = self.client.post(
            self.endpoint,
            data={
                "event": "ONCRMLEADADD",
                "data[FIELDS][ID]": "123",
                "auth[application_token]": "anything",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "error")

    def test_missing_event_returns_error(self):
        response = self.client.post(
            self.endpoint,
            data={
                "data[FIELDS][ID]": "123",
                "auth[application_token]": "test-secret-token",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "error")
        self.assertIn("event", body["detail"].lower())

    def test_missing_entity_id_returns_error(self):
        response = self.client.post(
            self.endpoint,
            data={
                "event": "ONCRMLEADADD",
                "auth[application_token]": "test-secret-token",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "error")
        self.assertIn("entity ID", body["detail"])

    def test_json_payload_works(self):
        with patch(
            "apps.integrations.api.process_bitrix24_webhook.delay",
            return_value=SimpleNamespace(id="task-json"),
        ):
            response = self.client.post(
                self.endpoint,
                data={
                    "event": "ONCRMDEALUPDATE",
                    "data": {"FIELDS": {"ID": 456}},
                    "auth": {"application_token": "test-secret-token"},
                },
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["event"], "ONCRMDEALUPDATE")
        self.assertEqual(body["entity_id"], 456)
