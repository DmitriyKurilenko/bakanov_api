from django.test import SimpleTestCase, override_settings

from apps.integrations.services.stt_service import STTResult, transcribe_audio


class STTServiceTests(SimpleTestCase):
    @override_settings(DEEPGRAM_API_KEY="", YANDEX_API_KEY="", STT_PROVIDER="deepgram")
    def test_transcribe_audio_returns_fallback_when_providers_not_configured(self):
        result = transcribe_audio(b"fake-bytes", mime_type="audio/mpeg")

        self.assertIsInstance(result, STTResult)
        self.assertEqual(result.provider, "fallback")
        self.assertTrue(result.transcript.startswith("STT unavailable"))
        self.assertTrue(result.segments)
        self.assertIn("Система", result.segments[0]["role"])
