from types import SimpleNamespace

from django.test import SimpleTestCase, override_settings

from apps.integrations.services.amocrm_spam_lead_service import AmoCrmSpamLeadSyncService


class AmoCrmSpamLeadSyncServiceTests(SimpleTestCase):
    @override_settings(AMOCRM_SPAM_CLIENT_ID_FIELD_NAMES="yandex_id")
    def test_sync_lead_uploads_ids_from_configured_custom_field(self):
        lead_payload = {
            "id": 21688211,
            "custom_fields_values": [
                {"field_name": "yandex_id", "values": [{"value": "1772125921407675467"}]},
            ],
        }
        amocrm = SimpleNamespace(
            get_lead=lambda _lead_id: lead_payload,
            get_contact=lambda _contact_id: {},
            get_company=lambda _company_id: {},
        )
        upload_result = SimpleNamespace(uploading={"id": 101, "status": "UPLOADED", "source_quantity": 1, "linked_quantity": 1})
        metrika = SimpleNamespace(upload_spam_client_ids=lambda **_kwargs: upload_result)

        service = AmoCrmSpamLeadSyncService(amocrm=amocrm, metrika=metrika)
        result = service.sync_lead(lead_id=21688211)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.uploaded_client_ids, 1)
        self.assertEqual(result.uploading["id"], 101)
        self.assertEqual(result.sources, ["lead"])

    @override_settings(AMOCRM_SPAM_CLIENT_ID_FIELD_IDS="952089")
    def test_sync_lead_falls_back_to_contact_custom_fields(self):
        lead_payload = {
            "id": 21688211,
            "custom_fields_values": [],
            "_embedded": {"contacts": [{"id": 111}]},
        }

        def _get_contact(contact_id: int) -> dict:
            if contact_id != 111:
                return {}
            return {
                "id": 111,
                "custom_fields_values": [
                    {"field_id": 952089, "values": [{"value": "1772125921407675467"}]},
                ],
            }

        amocrm = SimpleNamespace(
            get_lead=lambda _lead_id: lead_payload,
            get_contact=_get_contact,
            get_company=lambda _company_id: {},
        )
        upload_result = SimpleNamespace(uploading={"id": 102, "status": "UPLOADED", "source_quantity": 1, "linked_quantity": 1})
        metrika = SimpleNamespace(upload_spam_client_ids=lambda **_kwargs: upload_result)

        service = AmoCrmSpamLeadSyncService(amocrm=amocrm, metrika=metrika)
        result = service.sync_lead(lead_id=21688211)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.uploaded_client_ids, 1)
        self.assertEqual(result.uploading["id"], 102)
        self.assertEqual(result.sources, ["contact:111"])

    @override_settings(AMOCRM_SPAM_CLIENT_ID_FIELD_IDS="952089")
    def test_sync_lead_collects_and_deduplicates_values_from_multiple_entities(self):
        lead_payload = {
            "id": 21688211,
            "custom_fields_values": [
                {"field_id": 952089, "values": [{"value": "1772125921407675467"}]},
            ],
            "_embedded": {"contacts": [{"id": 111}], "companies": [{"id": 222}]},
        }

        amocrm = SimpleNamespace(
            get_lead=lambda _lead_id: lead_payload,
            get_contact=lambda _contact_id: {
                "id": 111,
                "custom_fields_values": [
                    {"field_id": 952089, "values": [{"value": "1772125921407675467"}, {"value": "1772217754100347291"}]},
                ],
            },
            get_company=lambda _company_id: {
                "id": 222,
                "custom_fields_values": [
                    {"field_id": 952089, "values": [{"value": "1772217754100347291"}, {"value": "1772010046373670895"}]},
                ],
            },
        )

        uploaded: dict = {}

        def _upload_spam_client_ids(**kwargs):
            uploaded.update(kwargs)
            return SimpleNamespace(uploading={"id": 103, "status": "UPLOADED", "source_quantity": 3, "linked_quantity": 3})

        metrika = SimpleNamespace(upload_spam_client_ids=_upload_spam_client_ids)

        service = AmoCrmSpamLeadSyncService(amocrm=amocrm, metrika=metrika)
        result = service.sync_lead(lead_id=21688211)

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.uploaded_client_ids, 3)
        self.assertEqual(
            uploaded["client_ids"],
            ["1772125921407675467", "1772217754100347291", "1772010046373670895"],
        )
        self.assertEqual(result.sources, ["lead", "contact:111", "company:222"])

    def test_sync_lead_returns_error_when_no_client_ids(self):
        lead_payload = {"id": 21688211, "custom_fields_values": []}
        amocrm = SimpleNamespace(
            get_lead=lambda _lead_id: lead_payload,
            get_contact=lambda _contact_id: {},
            get_company=lambda _company_id: {},
        )
        metrika = SimpleNamespace(upload_spam_client_ids=lambda **_kwargs: None)

        service = AmoCrmSpamLeadSyncService(amocrm=amocrm, metrika=metrika)
        result = service.sync_lead(lead_id=21688211)

        self.assertEqual(result.status, "error")
        self.assertIn("No metrika client ids", result.detail)
        self.assertEqual(result.sources, [])
