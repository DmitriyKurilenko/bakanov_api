from unittest.mock import patch

from django.test import TestCase

from apps.integrations.services.telephony_pipeline import TelephonyWebhookResult


class NovofonWebhookApiTests(TestCase):
    def test_novofon_webhook_uses_processor(self):
        fake_result = TelephonyWebhookResult(
            status="ok",
            provider="novofon",
            call_analysis_id=123,
            call_id="call-123",
            deal_id=21688211,
            stt_provider="deepgram",
            audio_file="/media/calls/test.mp3",
        )
        with patch("apps.integrations.api.TelephonyWebhookProcessor.process", return_value=fake_result) as process_mock:
            response = self.client.post(
                "/api/integrations/webhooks/novofon",
                data={"call_id": "call-123", "record_url": "https://example.test/c.mp3", "deal_id": 21688211},
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        process_mock.assert_called_once()
