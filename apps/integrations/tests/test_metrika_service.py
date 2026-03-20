from unittest.mock import patch

from django.test import SimpleTestCase

from apps.integrations.services.metrika_service import YandexMetricaService


class YandexMetricaServiceTests(SimpleTestCase):
    @patch("apps.integrations.services.metrika_service.requests.get")
    @patch("apps.integrations.services.metrika_service.requests.post")
    def test_upload_spam_client_ids_sends_csv_file(self, post_mock, get_mock):
        get_mock.return_value.status_code = 200
        get_mock.return_value.content = b'{"goals":[]}'
        get_mock.return_value.json.return_value = {"goals": []}
        post_mock.return_value.status_code = 200
        post_mock.return_value.text = '{"uploading":{"id":101,"status":"UPLOADED","source_quantity":2,"linked_quantity":1}}'
        post_mock.return_value.json.return_value = {
            "uploading": {
                "id": 101,
                "status": "UPLOADED",
                "source_quantity": 2,
                "linked_quantity": 1,
            }
        }

        service = YandexMetricaService(
            token="token",
            counter_id=49831738,
            spam_goal_id="spam_lead",
            upload_type="BASIC",
        )
        result = service.upload_spam_client_ids(
            client_ids=["1772125921407675467", "1772217754100347291"],
            conversion_timestamp=1700000000,
            comment="spam webhook",
        )

        self.assertEqual(result.id, 101)
        self.assertEqual(result.source_quantity, 2)
        self.assertEqual(result.linked_quantity, 1)
        self.assertTrue(post_mock.called)
        args, kwargs = post_mock.call_args
        self.assertIn("/offline_conversions/upload", args[0])
        self.assertEqual(kwargs["params"]["type"], "BASIC")
        self.assertIn("comment", kwargs["params"])

        file_part = kwargs["files"]["file"]
        self.assertEqual(file_part[0], "offline_conversions.csv")
        self.assertEqual(file_part[2], "text/csv")
        csv_text = file_part[1].decode("utf-8")
        self.assertIn("ClientId,Target,DateTime", csv_text)
        self.assertIn("1772125921407675467,spam_lead,1700000000", csv_text)

    @patch("apps.integrations.services.metrika_service.requests.get")
    @patch("apps.integrations.services.metrika_service.requests.post")
    def test_upload_resolves_numeric_goal_id_to_action_identifier(self, post_mock, get_mock):
        get_mock.return_value.status_code = 200
        get_mock.return_value.content = b'{"goals":[{"id":535794961,"type":"action","conditions":[{"type":"exact","url":"spam_lead"}]}]}'
        get_mock.return_value.json.return_value = {
            "goals": [
                {
                    "id": 535794961,
                    "type": "action",
                    "conditions": [{"type": "exact", "url": "spam_lead"}],
                }
            ]
        }
        post_mock.return_value.status_code = 200
        post_mock.return_value.text = '{"uploading":{"id":201,"status":"UPLOADED","source_quantity":1,"linked_quantity":1}}'
        post_mock.return_value.json.return_value = {
            "uploading": {
                "id": 201,
                "status": "UPLOADED",
                "source_quantity": 1,
                "linked_quantity": 1,
            }
        }

        service = YandexMetricaService(
            token="token",
            counter_id=105288315,
            spam_goal_id="535794961",
            upload_type="BASIC",
        )
        service.upload_spam_client_ids(
            client_ids=["1738823498979764492"],
            conversion_timestamp=1700000000,
        )

        args, kwargs = post_mock.call_args
        csv_text = kwargs["files"]["file"][1].decode("utf-8")
        self.assertIn("1738823498979764492,spam_lead,1700000000", csv_text)

    @patch("apps.integrations.services.metrika_service.requests.get")
    @patch("apps.integrations.services.metrika_service.requests.post")
    def test_upload_spam_client_ids_raises_when_uploading_missing(self, post_mock, get_mock):
        get_mock.return_value.status_code = 200
        get_mock.return_value.content = b'{"goals":[]}'
        get_mock.return_value.json.return_value = {"goals": []}
        post_mock.return_value.status_code = 200
        post_mock.return_value.text = "{}"
        post_mock.return_value.json.return_value = {}

        service = YandexMetricaService(
            token="token",
            counter_id=49831738,
            spam_goal_id="spam_lead",
        )

        with self.assertRaises(Exception):
            service.upload_spam_client_ids(client_ids=["1772125921407675467"])
