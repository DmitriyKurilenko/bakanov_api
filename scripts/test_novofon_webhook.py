#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from unittest.mock import patch

from dotenv import load_dotenv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test Novofon webhook with mocked audio/STT/AI")
    parser.add_argument("--lead-id", type=int, default=21688211, help="AmoCRM TEST lead ID (default: 21688211)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    root_dir = Path(__file__).resolve().parent.parent
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))
    load_dotenv(root_dir / ".env")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django

    django.setup()

    from django.conf import settings
    from django.core import mail
    from django.test import Client, override_settings

    from apps.crm.models import CallAnalysis, DealSnapshot
    from apps.integrations.services.stt_service import STTResult
    from apps.integrations.services.telephony_service import DownloadedCallRecord

    allowed_hosts = [host for host in settings.ALLOWED_HOSTS if host and host != "*"]
    test_host = allowed_hosts[0] if allowed_hosts else "localhost"

    before_ids = set(CallAnalysis.objects.values_list("id", flat=True))

    with override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DOCUMENTS_EMAIL_TO="qa-calls@example.test",
        STT_PROVIDER="deepgram",
    ):
        mail.outbox = []
        client = Client(HTTP_HOST=test_host)

        mocked_audio = DownloadedCallRecord(
            content=b"FAKE_MP3_DATA",
            content_type="audio/mpeg",
            file_name="novofon_test_call.mp3",
        )
        mocked_stt = STTResult(
            transcript="Спикер 0: Добрый день.\nСпикер 1: Добрый день, интересует круиз.",
            provider="deepgram",
            segments=[
                {"role": "Спикер 0", "speaker": 0, "start": 0.0, "end": 1.2, "text": "Добрый день."},
                {"role": "Спикер 1", "speaker": 1, "start": 1.3, "end": 4.8, "text": "Добрый день, интересует круиз."},
            ],
            language="ru",
            raw={"mock": True},
        )
        mocked_ai = {
            "provider": "yandexgpt",
            "analysis": "Менеджер установил контакт, но слабо квалифицировал клиента.",
            "recommendations": "Уточнить бюджет, даты, состав группы и договориться о следующем шаге.",
        }

        with patch("apps.integrations.api.download_call_record_detailed", return_value=mocked_audio), patch(
            "apps.integrations.api.transcribe_audio", return_value=mocked_stt
        ), patch("apps.integrations.api.analyze_call_text", return_value=mocked_ai):
            response = client.post(
                "/api/integrations/webhooks/novofon",
                data={
                    "call_id": "test-call-001",
                    "record_url": "https://example.test/calls/test-call-001.mp3",
                    "deal_id": args.lead_id,
                    "caller": "+79990001122",
                },
                content_type="application/json",
            )

        print("novofon webhook:", response.status_code, response.content.decode("utf-8", errors="ignore"))
        if response.status_code != 200:
            return 2
        body = response.json()
        if body.get("status") != "ok":
            print("ERROR: webhook returned non-ok")
            return 3
        if body.get("stt_provider") != "deepgram":
            print("ERROR: unexpected stt_provider", body.get("stt_provider"))
            return 4

        created = CallAnalysis.objects.exclude(id__in=before_ids).order_by("-id").first()
        if not created:
            print("ERROR: CallAnalysis row not created")
            return 5
        print("call_analysis_id:", created.id)
        print("deal:", created.deal_id, "call_id:", created.call_id)
        print("stt_provider:", created.stt_provider, "ai_provider:", created.ai_provider)
        print("audio_file:", created.audio_file.path if created.audio_file else "")

        if created.call_id != "test-call-001":
            print("ERROR: call_id mismatch")
            return 6
        if not created.deal or int(created.deal.amo_deal_id) != args.lead_id:
            print("ERROR: DealSnapshot not linked to test deal")
            return 7
        if "Спикер" not in (created.transcript or ""):
            print("ERROR: transcript by roles not saved")
            return 8
        if not created.transcript_segments:
            print("ERROR: transcript_segments empty")
            return 9
        if not created.recommendations:
            print("ERROR: recommendations empty")
            return 10
        if not created.audio_file or not Path(created.audio_file.path).exists():
            print("ERROR: audio file not saved")
            return 11
        if len(mail.outbox) != 1:
            print("ERROR: expected 1 email, got", len(mail.outbox))
            return 12
        msg = mail.outbox[0]
        if "Текст разговора" not in msg.body or "Рекомендации" not in msg.body:
            print("ERROR: transcript/recommendations missing in email body")
            return 13

        deal = DealSnapshot.objects.get(pk=created.deal_id)
        print("deal snapshot:", deal.amo_deal_id, deal.name)
        print("email subject:", msg.subject)

    print("OK: Novofon webhook saved audio/transcript/recommendations and sent email")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted")
        sys.exit(130)
