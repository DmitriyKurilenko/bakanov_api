#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="End-to-end test Novofon webhook using a local audio file (file://)")
    parser.add_argument("--audio", required=True, help="Path to audio file in the repo (will be used as file:// URL)")
    parser.add_argument("--lead-id", type=int, default=0, help="Optional Amo lead id (DealSnapshot)")
    parser.add_argument("--call-id", default="real-local-001", help="call_id value for webhook payload")
    parser.add_argument(
        "--send-email",
        action="store_true",
        help="Send email via configured SMTP (default: locmem backend, nothing leaves the container)",
    )
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

    from apps.crm.models import CallAnalysis

    audio_path = Path(args.audio).expanduser().resolve()
    if not audio_path.exists():
        print("ERROR: audio file not found:", audio_path)
        return 2
    record_url = f"file://{audio_path.as_posix()}"

    settings_override = {}
    if not args.send_email:
        settings_override = {
            "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
            "DOCUMENTS_EMAIL_TO": "qa-calls@example.test",
            "DEFAULT_FROM_EMAIL": "noreply@example.test",
        }

    with override_settings(**settings_override):
        if not args.send_email:
            mail.outbox = []

        allowed_hosts = [host for host in settings.ALLOWED_HOSTS if host and host != "*"]
        test_host = allowed_hosts[0] if allowed_hosts else "localhost"

        before_ids = set(CallAnalysis.objects.values_list("id", flat=True))
        resp = Client(HTTP_HOST=test_host).post(
            "/api/integrations/webhooks/novofon",
            data={
                "call_id": args.call_id,
                "record_url": record_url,
                "deal_id": args.lead_id or "",
            },
            content_type="application/json",
        )

        print("status_code:", resp.status_code)
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.content.decode("utf-8", errors="ignore")}
        print("response:", body)

        created = CallAnalysis.objects.exclude(id__in=before_ids).order_by("-id").first()
        if not created:
            print("ERROR: CallAnalysis row not created")
            return 3

        print("call_analysis_id:", created.id)
        print("stt_provider:", created.stt_provider)
        print("ai_provider:", created.ai_provider)
        print("transcript_len:", len(created.transcript or ""))
        print("analysis_len:", len(created.analysis or ""))
        print("recommendations_len:", len(created.recommendations or ""))
        if created.processing_error:
            print("processing_error:", created.processing_error)
        if not args.send_email:
            print("emails_sent(locmem):", len(mail.outbox))
            if mail.outbox:
                print("email_subject:", mail.outbox[0].subject)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted")
        sys.exit(130)
