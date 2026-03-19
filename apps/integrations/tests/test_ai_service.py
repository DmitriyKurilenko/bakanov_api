from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from apps.integrations.services.ai_service import analyze_call_text


class AIServiceTests(SimpleTestCase):
    @override_settings(YANDEX_API_KEY="", YANDEX_MODEL_URI="")
    def test_analyze_call_text_returns_fallback_when_not_configured(self):
        result = analyze_call_text("Спикер 0: тест")
        self.assertEqual(result["provider"], "fallback")
        self.assertIn("Анализ разговора", result["analysis"])

    @override_settings(YANDEX_API_KEY="k", YANDEX_MODEL_URI="gpt://test/model")
    def test_analyze_call_text_uses_yandexgpt_when_configured(self):
        fake_response = Mock()
        fake_response.raise_for_status = Mock()
        fake_response.json.return_value = {
            "result": {
                "alternatives": [
                    {
                        "message": {
                            "role": "assistant",
                            "text": '{"analysis":"ok","recommendations":"do it"}',
                        }
                    }
                ]
            }
        }
        with patch("apps.integrations.services.ai_service.requests.post", return_value=fake_response) as post_mock:
            result = analyze_call_text("hello")
        self.assertEqual(result["provider"], "yandexgpt")
        self.assertEqual(result["analysis"], "ok")
        self.assertEqual(result["recommendations"], "do it")
        post_mock.assert_called_once()

