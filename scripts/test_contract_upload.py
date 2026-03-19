#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="One-off contract generation smoke test")
    parser.add_argument("--lead-id", type=int, required=True, help="AmoCRM lead ID")
    parser.add_argument(
        "--field-id",
        type=int,
        default=None,
        help="AmoCRM file custom field ID. By default uses CONTRACT_FILE_FIELD_ID from .env",
    )
    parser.add_argument(
        "--expect-pdf",
        action="store_true",
        help="Fail if generated file is not PDF",
    )
    parser.add_argument(
        "--render-only",
        action="store_true",
        help="Only render PDF locally without uploading to AmoCRM lead field",
    )
    return parser.parse_args()


def find_field_values(lead: dict, field_id: int) -> list:
    for custom_field in lead.get("custom_fields_values") or []:
        if custom_field.get("field_id") == field_id:
            return custom_field.get("values") or []
    return []


def main() -> int:
    args = parse_args()
    lead_id = args.lead_id

    root_dir = Path(__file__).resolve().parent.parent
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))
    load_dotenv(root_dir / ".env")

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django

    django.setup()

    from django.conf import settings
    from apps.crm.api import generate_contract
    from apps.crm.schemas import LeadRequest
    from apps.crm.services.contract_renderer import ContractRenderer
    from apps.crm.services.amocrm import AmoCRMClient

    if args.render_only:
        renderer = ContractRenderer()
        result = renderer.render_for_lead(lead_id)

        print("render_for_lead file_url:", result.file_url)
        print("render_for_lead file_path:", result.file_path)

        if not result.file_path.exists():
            print("ERROR: PDF file was not created")
            return 9

        if args.expect_pdf and result.file_path.suffix.lower() != ".pdf":
            print(f"ERROR: expected PDF but got {result.file_path.name}")
            return 6

        print("OK: contract generated locally without upload")
        return 0

    field_id = args.field_id or int(getattr(settings, "CONTRACT_FILE_FIELD_ID", 0) or 0)
    if not field_id:
        print("ERROR: field_id is required (pass --field-id or set CONTRACT_FILE_FIELD_ID)")
        return 2

    response = generate_contract(None, LeadRequest(lead_id=lead_id))
    print("generate_contract response:", response)
    if response.get("status") != "ok":
        print("ERROR: generate_contract returned non-ok status")
        return 3

    generated_url = str(response.get("contract_file_url") or "")
    expected_file_name = Path(generated_url).name
    if not expected_file_name:
        print("ERROR: cannot extract generated file name from contract_file_url")
        return 7

    amocrm = AmoCRMClient.from_settings()
    values = []
    for _ in range(5):
        lead = amocrm.get_lead(lead_id)
        values = find_field_values(lead, field_id)
        if any((item.get("value") or {}).get("file_name") == expected_file_name for item in values):
            break
        time.sleep(1)

    if not values:
        print(f"ERROR: field {field_id} has no values in lead {lead_id}")
        return 4

    latest = values[-1].get("value", {})
    file_name = latest.get("file_name", "")
    is_deleted = bool(latest.get("is_deleted"))

    print("latest field value:", latest)

    if not any((item.get("value") or {}).get("file_name") == expected_file_name for item in values):
        print(f"ERROR: generated file {expected_file_name} not found in field {field_id}")
        return 8

    if is_deleted:
        print("ERROR: uploaded file is marked as deleted")
        return 5

    if args.expect_pdf and not file_name.lower().endswith(".pdf"):
        print(f"ERROR: expected PDF but got {file_name}")
        return 6

    print("OK: contract generated and uploaded to AmoCRM field")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted")
        sys.exit(130)
