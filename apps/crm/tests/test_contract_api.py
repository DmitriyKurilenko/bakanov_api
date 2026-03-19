from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import requests
from django.test import SimpleTestCase, override_settings


class ContractApiTests(SimpleTestCase):
    @override_settings(CONTRACT_FILE_FIELD_ID=1049055)
    def test_generate_contract_returns_warning_when_amocrm_upload_fails(self):
        amocrm = SimpleNamespace(
            get_lead=lambda _lead_id: {"id": 21688211},
            upload_contract_link=lambda _lead_id, _url: (_ for _ in ()).throw(requests.RequestException("link failed")),
            upload_file_to_lead_field=lambda **_kwargs: (_ for _ in ()).throw(requests.RequestException("file failed")),
        )
        renderer_instance = SimpleNamespace(
            render_for_lead=lambda _lead_id: SimpleNamespace(
                file_url="https://example.com/contract.pdf",
                file_path=Path("/tmp/contract.pdf"),
            )
        )

        with (
            patch("apps.crm.api.AmoCRMClient.from_settings", return_value=amocrm),
            patch("apps.crm.api.ContractRenderer", return_value=renderer_instance),
            patch("apps.crm.api.send_contract_email"),
        ):
            response = self.client.post(
                "/api/crm/contract/generate",
                data={"lead_id": 21688211},
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "warning")
        self.assertEqual(body["contract_file_url"], "https://example.com/contract.pdf")
        self.assertIn("amoCRM upload operations failed", body["detail"])
        self.assertEqual(len(body["warnings"]), 2)

    @override_settings(EXTRA_CONTRACT_FILE_FIELD_ID=1049055)
    def test_generate_extra_contract_returns_warning_when_amocrm_upload_fails(self):
        amocrm = SimpleNamespace(
            upload_file_to_lead_field=lambda **_kwargs: (_ for _ in ()).throw(requests.RequestException("upload failed")),
        )
        renderer_instance = SimpleNamespace(
            render_extra_agreement_for_lead=lambda _lead_id: SimpleNamespace(
                file_url="https://example.com/extra.pdf",
                file_path=Path("/tmp/extra.pdf"),
            )
        )

        with (
            patch("apps.crm.api.AmoCRMClient.from_settings", return_value=amocrm),
            patch("apps.crm.api.ContractRenderer", return_value=renderer_instance),
            patch("apps.crm.api.send_extra_contract_email"),
        ):
            response = self.client.post(
                "/api/crm/contract/extra/generate",
                data={"lead_id": 21688211},
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "warning")
        self.assertEqual(body["extra_contract_file_url"], "https://example.com/extra.pdf")
        self.assertIn("amoCRM upload failed", body["detail"])
        self.assertEqual(len(body["warnings"]), 1)
