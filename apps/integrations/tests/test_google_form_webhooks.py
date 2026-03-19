from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase


def _fake_artifact(report_id: int, url: str):
    report = SimpleNamespace(id=report_id, file=SimpleNamespace(url=url))
    return SimpleNamespace(report=report, file_path="/tmp/fake.pdf")


class GoogleFormWebhookTests(TestCase):
    def test_menu_webhook_returns_bilingual_report_and_sends_two_emails(self):
        fake_result = SimpleNamespace(
            lead_id=21688211,
            form_type="menu",
            ru=_fake_artifact(101, "/media/menus/menu_ru.pdf"),
            en=_fake_artifact(102, "/media/menus/menu_en.pdf"),
        )

        with patch("apps.integrations.api.GoogleFormReportService.generate", return_value=fake_result) as generate_mock, patch(
            "apps.integrations.api.send_form_report_email"
        ) as send_mail_mock:
            response = self.client.post(
                "/api/integrations/webhooks/google-form/menu",
                data={
                    "lead_id": 21688211,
                    "answers": {"Номер договора": "21688211", "Вопрос": "Ответ"},
                },
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["lead_id"], 21688211)
        self.assertEqual(body["form_type"], "menu")
        self.assertEqual(sorted([r["language"] for r in body["reports"]]), ["en", "ru"])
        generate_mock.assert_called_once()
        self.assertEqual(send_mail_mock.call_count, 2)

    def test_cruise_webhook_requires_lead_id(self):
        response = self.client.post(
            "/api/integrations/webhooks/google-form/cruise",
            data={"answers": {"Вопрос": "Ответ"}},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "error")
