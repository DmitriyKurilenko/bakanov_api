from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase


class AmoCrmSpamWebhookApiTests(SimpleTestCase):
    def test_webhook_queues_tasks_for_amo_style_payload(self):
        with patch(
            "apps.integrations.api.process_amocrm_spam_lead_webhook.delay",
            side_effect=[SimpleNamespace(id="task-1"), SimpleNamespace(id="task-2")],
        ):
            response = self.client.post(
                "/api/integrations/webhooks/amocrm/spam-lead",
                data={
                    "leads[add][0][id]": "21688211",
                    "leads[add][1][id]": "21688212",
                },
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["queued"], 2)
        self.assertEqual(body["lead_ids"], [21688211, 21688212])
        self.assertEqual(body["task_ids"], ["task-1", "task-2"])

    def test_webhook_accepts_single_lead_id_json(self):
        with patch(
            "apps.integrations.api.process_amocrm_spam_lead_webhook.delay",
            return_value=SimpleNamespace(id="task-1"),
        ):
            response = self.client.post(
                "/api/integrations/webhooks/amocrm/spam-lead",
                data={"lead_id": "21688211"},
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["queued"], 1)
        self.assertEqual(body["lead_ids"], [21688211])

    def test_webhook_returns_zero_when_no_lead_ids(self):
        response = self.client.post(
            "/api/integrations/webhooks/amocrm/spam-lead",
            data={"foo": "bar"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["queued"], 0)


class AmoCrmOAuthCallbackApiTests(SimpleTestCase):
    def test_callback_returns_code_and_state(self):
        response = self.client.get(
            "/api/integrations/amocrm/oauth/callback",
            data={"code": "auth_code_123", "state": "xyz"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["code"], "auth_code_123")
        self.assertEqual(body["state"], "xyz")

    def test_callback_returns_error_when_code_missing(self):
        response = self.client.get("/api/integrations/amocrm/oauth/callback")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "error")
        self.assertIn("Missing 'code'", body["detail"])

    def test_callback_returns_amocrm_error_payload(self):
        response = self.client.get(
            "/api/integrations/amocrm/oauth/callback",
            data={"error": "access_denied", "error_description": "user denied"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "error")
        self.assertEqual(body["error"], "access_denied")
