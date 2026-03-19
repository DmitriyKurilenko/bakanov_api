#!/usr/bin/env python3
from __future__ import annotations

import argparse
import mimetypes
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _guess_mime(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0]
    if mime:
        return mime
    ext = path.suffix.lower().lstrip(".")
    if ext == "mp3":
        return "audio/mpeg"
    if ext == "wav":
        return "audio/wav"
    if ext in {"ogg", "opus"}:
        return "audio/ogg"
    if ext == "m4a":
        return "audio/mp4"
    return "application/octet-stream"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Run real STT + AI analysis on a local audio file")
    ap.add_argument("--audio", required=True, help="Path to audio file (mp3/wav/ogg/opus)")
    ap.add_argument("--lead-id", type=int, default=0, help="Optional Amo lead id for DealSnapshot/CallAnalysis")
    ap.add_argument("--call-id", default="", help="Optional call id (default: derived from filename)")
    ap.add_argument("--provider", default="local", help="Telephony provider label (default: local)")
    ap.add_argument(
        "--stt-provider",
        default="",
        choices=["", "deepgram", "yandex"],
        help="Override STT_PROVIDER for this run",
    )
    ap.add_argument(
        "--send-email",
        action="store_true",
        help="Send email via configured SMTP (default: locmem backend, nothing leaves the container)",
    )
    return ap.parse_args()


def main() -> int:
    args = parse_args()

    root_dir = Path(__file__).resolve().parent.parent
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))

    load_dotenv(root_dir / ".env")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    if args.stt_provider:
        os.environ["STT_PROVIDER"] = args.stt_provider

    import django

    django.setup()

    from django.core import mail
    from django.core.files.base import ContentFile
    from django.test import override_settings

    from apps.crm.models import CallAnalysis, DealSnapshot
    from apps.integrations.services.ai_service import analyze_call_text
    from apps.integrations.services.email_service import send_analysis_email
    from apps.integrations.services.stt_service import transcribe_audio

    audio_path = Path(args.audio).expanduser().resolve()
    if not audio_path.exists():
        print("ERROR: audio file not found:", audio_path)
        return 2

    call_id = args.call_id.strip() or audio_path.stem[:120]
    audio_bytes = audio_path.read_bytes()
    mime_type = _guess_mime(audio_path)

    deal = None
    if args.lead_id:
        deal, _ = DealSnapshot.objects.get_or_create(
            amo_deal_id=args.lead_id,
            defaults={"name": f"Deal {args.lead_id}"},
        )

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

        call = CallAnalysis.objects.create(
            deal=deal,
            call_id=call_id,
            audio_source_url=f"file://{audio_path.as_posix()}",
            raw_payload={
                "source": "local_file",
                "provider": args.provider,
                "file": str(audio_path),
                "mime_type": mime_type,
                "size_bytes": len(audio_bytes),
            },
        )
        call.audio_file.save(audio_path.name, ContentFile(audio_bytes), save=False)

        try:
            stt = transcribe_audio(audio_bytes, mime_type=mime_type)
            ai = analyze_call_text(stt.transcript)

            call.stt_provider = stt.provider
            call.transcript_segments = stt.segments
            call.transcript = stt.transcript
            call.ai_provider = str(ai.get("provider") or "")
            call.analysis = str(ai.get("analysis") or "")
            call.recommendations = str(ai.get("recommendations") or "")
            call.processing_error = ""
            call.save()

            send_analysis_email(
                subject=f"Анализ звонка {call_id} ({args.provider})",
                body=(
                    f"Lead: {args.lead_id or '-'}\n"
                    f"Call ID: {call_id}\n"
                    f"STT provider: {call.stt_provider}\n"
                    f"AI provider: {call.ai_provider or '-'}\n\n"
                    f"Текст разговора:\n{call.transcript}\n\n"
                    f"Анализ:\n{call.analysis}\n\n"
                    f"Рекомендации:\n{call.recommendations}"
                ),
            )
        except Exception as exc:
            call.processing_error = str(exc)
            call.save(update_fields=["processing_error", "updated_at"])
            print("ERROR:", exc)
            print("call_analysis_id:", call.id)
            return 3

        print("OK")
        print("call_analysis_id:", call.id)
        print("stt_provider:", call.stt_provider)
        print("ai_provider:", call.ai_provider)
        print("audio_file:", call.audio_file.url if call.audio_file else "")
        print("transcript_len:", len(call.transcript or ""))
        print("analysis_len:", len(call.analysis or ""))
        print("recommendations_len:", len(call.recommendations or ""))
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
