#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Google Forms menu/cruise reports smoke test")
    parser.add_argument("--lead-id", type=int, default=21688211, help="AmoCRM TEST lead ID (default: 21688211)")
    parser.add_argument("--menu-only", action="store_true", help="Generate only menu reports")
    parser.add_argument("--cruise-only", action="store_true", help="Generate only cruise reports")
    parser.add_argument("--expect-pdf", action="store_true", help="Validate .pdf files")
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
    from django.test import Client
    from apps.crm.models import GoogleFormReport

    if args.menu_only and args.cruise_only:
        print("ERROR: --menu-only and --cruise-only are mutually exclusive")
        return 2

    allowed_hosts = [host for host in settings.ALLOWED_HOSTS if host and host != "*"]
    test_host = allowed_hosts[0] if allowed_hosts else "localhost"
    client = Client(HTTP_HOST=test_host)

    scenarios = []
    if not args.cruise_only:
        scenarios.append(
            (
                "/api/integrations/webhooks/google-form/menu",
                {
                    "lead_id": args.lead_id,
                    "answers": {
                        "Номер договора": str(args.lead_id),
                        "Ваши имя и фамилия": "Тестовый Клиент",
                        "Есть ли ограничения по продуктам?": ["Без свинины", "Без лактозы"],
                        "Предпочтения по завтракам": "Овсянка, яйца, фрукты",
                    },
                },
                GoogleFormReport.FormType.MENU,
            )
        )
    if not args.menu_only:
        scenarios.append(
            (
                "/api/integrations/webhooks/google-form/cruise",
                {
                    "lead_id": args.lead_id,
                    "answers": {
                        "Номер договора": str(args.lead_id),
                        "Ваши имя и фамилия": "Тестовый Клиент",
                        "Пожелания по маршруту": "Больше спокойных бухт и 1-2 активные стоянки",
                        "Особые пожелания": ["SUP на борту", "Ранний check-in при возможности"],
                    },
                },
                GoogleFormReport.FormType.CRUISE,
            )
        )

    before_ids = set(GoogleFormReport.objects.values_list("id", flat=True))

    for url, payload, form_type in scenarios:
        response = client.post(url, data=payload, content_type="application/json")
        print(url, response.status_code, response.content.decode("utf-8", errors="ignore"))
        if response.status_code != 200:
            return 3
        body = response.json()
        if body.get("status") != "ok":
            print("ERROR: webhook returned non-ok")
            return 4
        reports = body.get("reports") or []
        if len(reports) != 2:
            print("ERROR: expected 2 reports (ru/en) but got", len(reports))
            return 5
        langs = sorted(item.get("language") for item in reports)
        if langs != ["en", "ru"]:
            print("ERROR: expected ru/en languages but got", langs)
            return 6

    new_reports = list(GoogleFormReport.objects.exclude(id__in=before_ids).order_by("id"))
    expected_total = len(scenarios) * 2
    print("new reports created:", len(new_reports))
    if len(new_reports) != expected_total:
        print(f"ERROR: expected {expected_total} new reports, got {len(new_reports)}")
        return 7

    for report in new_reports:
        if report.lead_id != args.lead_id:
            print("ERROR: report lead_id mismatch", report.id, report.lead_id)
            return 8
        if not report.file or not report.file.name:
            print("ERROR: file is empty for report", report.id)
            return 9
        file_path = Path(report.file.path)
        print("report", report.id, report.form_type, report.language, file_path)
        if not file_path.exists():
            print("ERROR: file does not exist", file_path)
            return 10
        if args.expect_pdf and file_path.suffix.lower() != ".pdf":
            print("ERROR: expected pdf", file_path)
            return 11

    print("OK: google form menu/cruise reports generated (ru/en) for test lead")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted")
        sys.exit(130)
