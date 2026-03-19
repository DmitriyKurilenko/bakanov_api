from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.users.models import UserRole


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"])
class ReportExportTests(TestCase):
    def setUp(self) -> None:
        User = get_user_model()
        self.user = User.objects.create_user(
            username="export_admin",
            password="Kapitan123!",
            role=UserRole.ADMIN,
        )
        self.client.force_login(self.user)

    @staticmethod
    def _report_payload():
        return {
            "filters": {
                "date_from": "2026-01-01",
                "date_to": "2026-01-31",
            },
            "manager_rows": [
                {
                    "manager_name": "Менеджер 1",
                    "arrived": 10,
                    "moved_to_stage": 7,
                    "realized": 3,
                },
                {
                    "manager_name": "Менеджер 2",
                    "arrived": 8,
                    "moved_to_stage": 4,
                    "realized": 2,
                },
            ],
        }

    @patch("apps.dashboard.views.build_report_data")
    def test_export_pdf(self, build_report_data_mock):
        build_report_data_mock.return_value = self._report_payload()
        url = reverse("dashboard:report-export-api", args=["rop_funnel", "pdf"])
        response = self.client.get(url, {"date_from": "2026-01-01", "date_to": "2026-01-31"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("attachment;", response["Content-Disposition"])
        self.assertIn(".pdf", response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"%PDF"))

    @patch("apps.dashboard.views.build_report_data")
    def test_export_excel(self, build_report_data_mock):
        build_report_data_mock.return_value = self._report_payload()
        url = reverse("dashboard:report-export-api", args=["rop_funnel", "xls"])
        response = self.client.get(url, {"date_from": "2026-01-01", "date_to": "2026-01-31"})

        self.assertEqual(response.status_code, 200)
        self.assertIn("application/vnd.ms-excel", response["Content-Type"])
        self.assertIn(".xls", response["Content-Disposition"])
        body = response.content.decode("utf-8", errors="ignore")
        self.assertIn("Воронка РОП", body)
        self.assertIn("Менеджер 1", body)
        self.assertIn("Пришло", body)

    @patch("apps.dashboard.views.build_report_meta")
    def test_report_page_contains_export_buttons(self, build_report_meta_mock):
        build_report_meta_mock.return_value = {"pipelines": [], "managers": [], "filters": {}}
        response = self.client.get(reverse("dashboard:reports-rop"))

        self.assertEqual(response.status_code, 200)
        html = response.content.decode("utf-8", errors="ignore")
        self.assertIn("Экспорт PDF", html)
        self.assertIn("Экспорт Excel", html)
