from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from apps.integrations.services.bitrix24_spam_lead_service import (
    Bitrix24SpamLeadSyncResult,
    Bitrix24SpamLeadSyncService,
    _is_client_id_like_field,
    _normalize_client_ids,
    _parse_text_csv,
)


class ParseTextCsvTests(SimpleTestCase):
    def test_parses_comma_separated(self):
        result = _parse_text_csv("foo, bar, BAZ")
        self.assertEqual(result, {"foo", "bar", "baz"})

    def test_parses_semicolon_separated(self):
        result = _parse_text_csv("a; b; C")
        self.assertEqual(result, {"a", "b", "c"})

    def test_empty_returns_empty(self):
        self.assertEqual(_parse_text_csv(""), set())
        self.assertEqual(_parse_text_csv(None), set())


class NormalizeClientIdsTests(SimpleTestCase):
    def test_filters_non_numeric(self):
        result = _normalize_client_ids(["123", "abc", "456", "123"])
        self.assertEqual(result, ["123", "456"])

    def test_skips_none(self):
        self.assertEqual(_normalize_client_ids([None, "789"]), ["789"])

    def test_empty_list(self):
        self.assertEqual(_normalize_client_ids([]), [])


class IsClientIdLikeFieldTests(SimpleTestCase):
    def test_detects_yandex_id(self):
        self.assertTrue(_is_client_id_like_field(field_name="yandex_id"))

    def test_detects_client_id(self):
        self.assertTrue(_is_client_id_like_field(field_name="client_id"))

    def test_rejects_unrelated(self):
        self.assertFalse(_is_client_id_like_field(field_name="phone"))


class Bitrix24SpamLeadSyncServiceTests(SimpleTestCase):
    def _make_service(self, client=None, metrika=None):
        return Bitrix24SpamLeadSyncService(
            client=client or MagicMock(),
            metrika=metrika or MagicMock(),
        )

    def test_unsupported_entity_type(self):
        svc = self._make_service()
        result = svc.sync_entity(entity_id=1, entity_type="task")
        self.assertEqual(result.status, "error")
        self.assertIn("Unsupported", result.detail)

    def test_entity_not_found(self):
        client = MagicMock()
        client.get_lead.return_value = {}
        svc = self._make_service(client=client)
        result = svc.sync_entity(entity_id=1, entity_type="lead")
        self.assertEqual(result.status, "error")
        self.assertIn("not found", result.detail)

    @override_settings(BITRIX24_SPAM_CLIENT_ID_FIELD_CODES="UF_CRM_123")
    @patch("apps.integrations.services.bitrix24_spam_lead_service.YandexMetricaService")
    def test_sync_lead_with_client_id(self, mock_metrika_cls):
        client = MagicMock()
        client.get_lead.return_value = {
            "ID": "10",
            "DATE_CREATE": "2026-05-13T10:00:00+03:00",
            "UF_CRM_123": "987654321",
        }
        metrika = MagicMock()
        metrika.upload_spam_client_ids.return_value = MagicMock(uploading={"id": 42})
        mock_metrika_cls.from_settings.return_value = metrika

        svc = Bitrix24SpamLeadSyncService(client=client, metrika=metrika)
        result = svc.sync_entity(entity_id=10, entity_type="lead")

        self.assertEqual(result.status, "ok")
        self.assertEqual(result.uploaded_client_ids, 1)
        self.assertIn("lead", result.sources)
        metrika.upload_spam_client_ids.assert_called_once()

    @override_settings(BITRIX24_SPAM_CLIENT_ID_FIELD_CODES="")
    @override_settings(BITRIX24_SPAM_CLIENT_ID_FIELD_NAMES="")
    def test_no_client_ids_found(self):
        client = MagicMock()
        client.get_lead.return_value = {
            "ID": "10",
            "DATE_CREATE": "2026-05-13T10:00:00+03:00",
            "UF_CRM_999": "not_a_number",
        }
        svc = self._make_service(client=client)
        result = svc.sync_entity(entity_id=10, entity_type="lead")
        self.assertEqual(result.status, "error")
        self.assertIn("No metrika client ids", result.detail)

    @override_settings(BITRIX24_SPAM_CLIENT_ID_FIELD_CODES="UF_CRM_456")
    def test_fetches_linked_contact(self):
        client = MagicMock()
        client.get_lead.return_value = {
            "ID": "10",
            "DATE_CREATE": "2026-05-13T10:00:00+03:00",
            "CONTACT_ID": "5",
        }
        client.get_contact.return_value = {
            "ID": "5",
            "UF_CRM_456": "111222333",
        }
        metrika = MagicMock()
        metrika.upload_spam_client_ids.return_value = MagicMock(uploading={"id": 1})

        svc = Bitrix24SpamLeadSyncService(client=client, metrika=metrika)
        result = svc.sync_entity(entity_id=10, entity_type="lead")

        self.assertEqual(result.status, "ok")
        self.assertIn("contact:5", result.sources)

    @override_settings(BITRIX24_SPAM_CLIENT_ID_FIELD_CODES="UF_CRM_789")
    def test_fetches_linked_company(self):
        client = MagicMock()
        client.get_lead.return_value = {
            "ID": "10",
            "DATE_CREATE": "2026-05-13T10:00:00+03:00",
            "COMPANY_ID": "7",
        }
        client.get_company.return_value = {
            "ID": "7",
            "UF_CRM_789": "444555666",
        }
        metrika = MagicMock()
        metrika.upload_spam_client_ids.return_value = MagicMock(uploading={"id": 1})

        svc = Bitrix24SpamLeadSyncService(client=client, metrika=metrika)
        result = svc.sync_entity(entity_id=10, entity_type="lead")

        self.assertEqual(result.status, "ok")
        self.assertIn("company:7", result.sources)

    def test_extract_linked_contact_ids_variants(self):
        svc = Bitrix24SpamLeadSyncService(client=MagicMock(), metrika=MagicMock())

        self.assertEqual(svc._extract_linked_contact_ids({"CONTACT_ID": 5}), [5])
        self.assertEqual(svc._extract_linked_contact_ids({"CONTACT_ID": "5"}), [5])
        self.assertEqual(
            svc._extract_linked_contact_ids({"CONTACT_IDS": [{"ID": "5"}, {"ID": 6}]}),
            [5, 6],
        )
        self.assertEqual(svc._extract_linked_contact_ids({}), [])

    def test_extract_linked_company_ids_variants(self):
        svc = Bitrix24SpamLeadSyncService(client=MagicMock(), metrika=MagicMock())

        self.assertEqual(svc._extract_linked_company_ids({"COMPANY_ID": 7}), [7])
        self.assertEqual(svc._extract_linked_company_ids({"COMPANY_ID": "7"}), [7])
        self.assertEqual(svc._extract_linked_company_ids({}), [])

    def test_extract_raw_values_heuristic(self):
        svc = Bitrix24SpamLeadSyncService(client=MagicMock(), metrika=MagicMock())
        fields = {
            "UF_CRM_111": "12345",
            "UF_CRM_YANDEX_ID": "67890",
            "PHONE": "+7999",
            "UF_CRM_NAME": "not numeric",
        }
        values = svc._extract_raw_values_from_fields(
            fields=fields,
            field_codes=set(),
            field_names=set(),
            configured_filter=False,
        )
        # UF_CRM_111 is not heuristic-matched; UF_CRM_YANDEX_ID is.
        self.assertNotIn("12345", values)
        self.assertIn("67890", values)
        self.assertNotIn("+7999", values)

    def test_extract_raw_values_configured_filter(self):
        svc = Bitrix24SpamLeadSyncService(client=MagicMock(), metrika=MagicMock())
        fields = {
            "UF_CRM_111": "12345",
            "UF_CRM_222": "67890",
        }
        values = svc._extract_raw_values_from_fields(
            fields=fields,
            field_codes={"uf_crm_222"},
            field_names=set(),
            configured_filter=True,
        )
        self.assertEqual(values, ["67890"])

    def test_resolve_conversion_timestamp(self):
        svc = Bitrix24SpamLeadSyncService(client=MagicMock(), metrika=MagicMock())
        ts = svc._resolve_conversion_timestamp({"DATE_CREATE": "2026-05-13T10:00:00+03:00"})
        self.assertGreater(ts, 0)
        self.assertIsInstance(ts, int)

        ts_now = svc._resolve_conversion_timestamp({})
        self.assertGreaterEqual(ts_now, int(__import__("time").time()) - 5)


class Bitrix24SpamLeadSyncResultTests(SimpleTestCase):
    def test_defaults(self):
        result = Bitrix24SpamLeadSyncResult(entity_id=1, entity_type="lead", status="ok")
        self.assertEqual(result.detail, "")
        self.assertEqual(result.uploaded_client_ids, 0)
