"""Reliability tests for the Bitrix24 → Yandex.Metrica spam flow.

Covers the root causes of the "worked once or twice then stopped" defect:
* generic webhook no longer swallows transient Bitrix errors silently;
* the spam upload is dispatched as an independent, deduplicated task;
* every definitive failure is loud (Telegram alert), never silent;
* the dedup lock is released on failure so a retry/redelivery can recover.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import requests
from django.test import SimpleTestCase, override_settings

from apps.integrations.services.bitrix24_webhook_handler import (
    Bitrix24WebhookProcessor,
)
from apps.integrations.tasks import (
    process_bitrix24_spam_lead_webhook,
    process_bitrix24_webhook,
)


class FakeRedis:
    """Minimal Redis stand-in supporting set(nx, ex) / delete semantics."""

    def __init__(self):
        self.store: dict[str, str] = {}

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    def delete(self, key):
        self.store.pop(key, None)
        return True


@override_settings(BITRIX24_SPAM_STATUS_ID="UC_Q4I0BY")
class ProcessBitrix24WebhookDispatchTests(SimpleTestCase):
    def test_spam_status_dispatches_independent_task(self):
        with patch.object(
            Bitrix24WebhookProcessor, "_fetch_entity",
            return_value={"ID": "10", "STATUS_ID": "UC_Q4I0BY"},
        ), patch(
            "apps.integrations.tasks.process_bitrix24_spam_lead_webhook.delay",
            return_value=SimpleNamespace(id="spam-task-1"),
        ) as mock_delay:
            process_bitrix24_webhook(event="ONCRMLEADUPDATE", entity_id=10)

        mock_delay.assert_called_once_with(entity_id=10, entity_type="lead")

    def test_non_spam_status_does_not_dispatch(self):
        with patch.object(
            Bitrix24WebhookProcessor, "_fetch_entity",
            return_value={"ID": "10", "STATUS_ID": "NEW"},
        ), patch(
            "apps.integrations.tasks.process_bitrix24_spam_lead_webhook.delay",
        ) as mock_delay:
            process_bitrix24_webhook(event="ONCRMLEADUPDATE", entity_id=10)

        mock_delay.assert_not_called()

    def test_transient_fetch_error_propagates_for_retry(self):
        """A Bitrix rate-limit/5xx must raise (Celery retries) instead of
        producing empty data and silently skipping the spam upload."""
        client = MagicMock()
        client.get_lead.side_effect = requests.RequestException("429 rate limit")
        processor = Bitrix24WebhookProcessor(client=client)

        with self.assertRaises(requests.RequestException):
            processor.process(event="ONCRMLEADUPDATE", entity_id=10)


@override_settings(BITRIX24_SPAM_DEDUP_TTL=3600)
class ProcessBitrix24SpamLeadTaskTests(SimpleTestCase):
    def _run(self, sync_result=None, sync_exc=None):
        fake_redis = FakeRedis()
        svc = MagicMock()
        if sync_exc is not None:
            svc.sync_entity.side_effect = sync_exc
        else:
            svc.sync_entity.return_value = sync_result
        with patch(
            "apps.integrations.tasks.get_redis_client", return_value=fake_redis,
        ), patch(
            "apps.integrations.services.bitrix24_spam_lead_service."
            "Bitrix24SpamLeadSyncService.from_settings",
            return_value=svc,
        ), patch(
            "apps.integrations.tasks.send_telegram_message",
        ) as mock_tg:
            out = process_bitrix24_spam_lead_webhook(entity_id=10, entity_type="lead")
        return out, fake_redis, mock_tg

    def test_success_keeps_dedup_and_second_call_skipped(self):
        ok = SimpleNamespace(
            entity_id=10, entity_type="lead", status="ok", detail="",
            uploaded_client_ids=1, uploading={"id": 5}, sources=["lead"],
        )
        out, fake_redis, mock_tg = self._run(sync_result=ok)
        self.assertEqual(out["status"], "ok")
        self.assertIn("bitrix24:spam:processed:lead:10", fake_redis.store)
        mock_tg.assert_not_called()

        # Second delivery within TTL → skipped (no re-upload).
        svc = MagicMock()
        svc.sync_entity.return_value = ok
        with patch("apps.integrations.tasks.get_redis_client", return_value=fake_redis), \
             patch(
                 "apps.integrations.services.bitrix24_spam_lead_service."
                 "Bitrix24SpamLeadSyncService.from_settings", return_value=svc):
            again = process_bitrix24_spam_lead_webhook(entity_id=10, entity_type="lead")
        self.assertEqual(again["status"], "skipped")
        svc.sync_entity.assert_not_called()

    def test_config_error_is_loud_and_releases_lock(self):
        out, fake_redis, mock_tg = self._run(
            sync_exc=ValueError("YANDEX_METRIKA_TOKEN is not configured"),
        )
        self.assertEqual(out["status"], "error")
        self.assertIn("YANDEX_METRIKA_TOKEN", out["detail"])
        self.assertNotIn("bitrix24:spam:processed:lead:10", fake_redis.store)
        mock_tg.assert_called_once()

    def test_transient_error_releases_lock_and_reraises(self):
        fake_redis = FakeRedis()
        svc = MagicMock()
        svc.sync_entity.side_effect = requests.RequestException("Metrica 503")
        with patch("apps.integrations.tasks.get_redis_client", return_value=fake_redis), \
             patch(
                 "apps.integrations.services.bitrix24_spam_lead_service."
                 "Bitrix24SpamLeadSyncService.from_settings", return_value=svc):
            with self.assertRaises(requests.RequestException):
                process_bitrix24_spam_lead_webhook(entity_id=10, entity_type="lead")
        self.assertNotIn("bitrix24:spam:processed:lead:10", fake_redis.store)

    def test_no_client_id_result_alerts_and_releases_lock(self):
        err = SimpleNamespace(
            entity_id=10, entity_type="lead", status="error",
            detail="No metrika client ids found", uploaded_client_ids=0,
            uploading=None, sources=["lead"],
        )
        out, fake_redis, mock_tg = self._run(sync_result=err)
        self.assertEqual(out["status"], "error")
        self.assertNotIn("bitrix24:spam:processed:lead:10", fake_redis.store)
        mock_tg.assert_called_once()
