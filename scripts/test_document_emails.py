#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test document emails with attachments (locmem backend)")
    parser.add_argument("--lead-id", type=int, default=21688211, help="AmoCRM TEST lead ID (default: 21688211)")
    return parser.parse_args()


def _assert_pdf_attachment(message, *, label: str) -> None:
    if not message.attachments:
        raise AssertionError(f"{label}: email has no attachments")
    name = message.attachments[0][0] if isinstance(message.attachments[0], tuple) else getattr(message.attachments[0], "filename", "")
    if not str(name).lower().endswith(".pdf"):
        raise AssertionError(f"{label}: attachment is not pdf ({name})")


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

    from apps.crm.api import generate_contract, generate_extra_contract
    from apps.crm.schemas import LeadRequest

    allowed_hosts = [host for host in settings.ALLOWED_HOSTS if host and host != "*"]
    test_host = allowed_hosts[0] if allowed_hosts else "localhost"

    with override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DOCUMENTS_EMAIL_TO="qa-docs@example.test",
    ):
        mail.outbox = []

        contract_resp = generate_contract(None, LeadRequest(lead_id=args.lead_id))
        print("generate_contract:", contract_resp)
        if contract_resp.get("status") != "ok":
            print("ERROR: contract generation failed")
            return 2
        if len(mail.outbox) != 1:
            print("ERROR: expected 1 email after contract, got", len(mail.outbox))
            return 3
        _assert_pdf_attachment(mail.outbox[-1], label="contract")

        extra_resp = generate_extra_contract(None, LeadRequest(lead_id=args.lead_id))
        print("generate_extra_contract:", extra_resp)
        if extra_resp.get("status") != "ok":
            print("ERROR: extra contract generation failed")
            return 4
        if len(mail.outbox) != 2:
            print("ERROR: expected 2 emails after extra contract, got", len(mail.outbox))
            return 5
        _assert_pdf_attachment(mail.outbox[-1], label="extra_contract")

        client = Client(HTTP_HOST=test_host)

        menu_resp = client.post(
            "/api/integrations/webhooks/google-form/menu",
            data={
                "lead_id": args.lead_id,
                "answers": {
                    "Номер договора": str(args.lead_id),
                    "Ваши имя и фамилия": "Тестовый Клиент",
                    "Предпочтения по завтракам": "Фрукты и яйца",
                },
            },
            content_type="application/json",
        )
        print("menu webhook:", menu_resp.status_code, menu_resp.content.decode("utf-8", errors="ignore"))
        if menu_resp.status_code != 200:
            return 6
        if len(mail.outbox) != 4:
            print("ERROR: expected 4 emails after menu webhook (ru/en), got", len(mail.outbox))
            return 7
        _assert_pdf_attachment(mail.outbox[-1], label="menu_en")
        _assert_pdf_attachment(mail.outbox[-2], label="menu_ru")

        cruise_resp = client.post(
            "/api/integrations/webhooks/google-form/cruise",
            data={
                "lead_id": args.lead_id,
                "answers": {
                    "Номер договора": str(args.lead_id),
                    "Ваши имя и фамилия": "Тестовый Клиент",
                    "Пожелания по маршруту": "Больше тихих бухт",
                },
            },
            content_type="application/json",
        )
        print("cruise webhook:", cruise_resp.status_code, cruise_resp.content.decode("utf-8", errors="ignore"))
        if cruise_resp.status_code != 200:
            return 8
        if len(mail.outbox) != 6:
            print("ERROR: expected 6 emails after cruise webhook (ru/en), got", len(mail.outbox))
            return 9
        _assert_pdf_attachment(mail.outbox[-1], label="cruise_en")
        _assert_pdf_attachment(mail.outbox[-2], label="cruise_ru")

        for idx, msg in enumerate(mail.outbox, start=1):
            print(f"email[{idx}] to={msg.to} subject={msg.subject}")

    print("OK: document emails with PDF attachments were sent for contract/extra/menu/cruise")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted")
        sys.exit(130)
