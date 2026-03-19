import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings

from apps.crm.models import CallAnalysis
from apps.integrations.services.stt_service import STTResult
from apps.integrations.services.telephony_pipeline import TelephonyWebhookProcessor, pick_first, pick_int
from apps.integrations.services.telephony_service import DownloadedCallRecord


class TelephonyHelperTests(TestCase):
    def test_pick_first_and_pick_int(self):
        data = {
            "record_link": ["https://example.test/a.mp3"],
            "deal_id": "lead-21688211",
        }
        self.assertEqual(pick_first(data, "record_url", "record_link"), "https://example.test/a.mp3")
        self.assertEqual(pick_int(data, "deal_id"), 21688211)
        self.assertIsNone(pick_int({"deal_id": "abc"}, "deal_id"))


class TelephonyWebhookProcessorTests(TestCase):
    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DOCUMENTS_EMAIL_TO="qa@example.test",
        DEFAULT_FROM_EMAIL="noreply@example.test",
    )
    def test_process_saves_audio_transcript_and_recommendations(self):
        mail.outbox = []
        with tempfile.TemporaryDirectory() as tmpdir:
            with override_settings(MEDIA_ROOT=tmpdir, MEDIA_URL="/media/"):
                downloaded = DownloadedCallRecord(
                    content=b"FAKE_MP3",
                    content_type="audio/mpeg",
                    file_name="test.mp3",
                )
                stt = STTResult(
                    transcript="Спикер 0: Добрый день",
                    provider="deepgram",
                    segments=[{"role": "Спикер 0", "text": "Добрый день"}],
                    language="ru",
                    raw={"ok": True},
                )
                ai = {
                    "provider": "yandexgpt",
                    "analysis": "Анализ",
                    "recommendations": "Рекомендации",
                }

                with patch(
                    "apps.integrations.services.telephony_pipeline.download_call_record_detailed", return_value=downloaded
                ), patch("apps.integrations.services.telephony_pipeline.transcribe_audio", return_value=stt), patch(
                    "apps.integrations.services.telephony_pipeline.analyze_call_text", return_value=ai
                ):
                    result = TelephonyWebhookProcessor().process(
                        provider="novofon",
                        raw_data={
                            "call_id": "call-1",
                            "record_url": "https://example.test/call.mp3",
                            "deal_id": "21688211",
                        },
                    )

                self.assertEqual(result.status, "ok")
                self.assertEqual(result.provider, "novofon")
                self.assertEqual(result.stt_provider, "deepgram")

                call = CallAnalysis.objects.get(call_id="call-1")
                self.assertEqual(call.stt_provider, "deepgram")
                self.assertEqual(call.ai_provider, "yandexgpt")
                self.assertTrue(call.transcript_segments)
                self.assertTrue(call.audio_file.name.endswith(".mp3"))
                self.assertTrue(Path(call.audio_file.path).exists())
                self.assertEqual(len(mail.outbox), 1)
                self.assertIn("Текст разговора", mail.outbox[0].body)
                self.assertIn("Рекомендации", mail.outbox[0].body)

    def test_process_returns_error_when_required_fields_missing(self):
        result = TelephonyWebhookProcessor().process(provider="novofon", raw_data={"call_id": "x"})
        self.assertEqual(result.status, "error")
        self.assertIn("record_url", result.detail or "")
