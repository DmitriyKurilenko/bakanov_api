"""Service for generating contracts from Bitrix24 deal data.

Maps Bitrix24 CRM fields (UF_CRM_*) to the normalized format
expected by ``ContractRenderer.build_context_from_data()``.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
import uuid

from django.conf import settings
from django.template.loader import render_to_string
from weasyprint import HTML

from apps.crm.services.contract_renderer import ContractRenderResult, ContractRenderer
from apps.integrations.services.bitrix24_service import Bitrix24Client

logger = logging.getLogger(__name__)


def _b24_field(deal: dict, field_code: str) -> str | None:
    """Get a scalar value from a Bitrix24 entity dict by UF_CRM_* code."""
    value = deal.get(field_code)
    if value in (None, "", []):
        return None
    if isinstance(value, list):
        return str(value[0]) if value else None
    return str(value)


def _b24_multi_field(entity: dict, field_code: str) -> list[str]:
    """Get a multi-value list from a Bitrix24 entity dict."""
    value = entity.get(field_code)
    if not value:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def _b24_contact_phone(contact: dict) -> str:
    """Extract first phone from contact's PHONE array."""
    phones = contact.get("PHONE") or []
    if isinstance(phones, list) and phones:
        return str(phones[0].get("VALUE", ""))
    return ""


def _b24_contact_email(contact: dict) -> str:
    """Extract first email from contact's EMAIL array."""
    emails = contact.get("EMAIL") or []
    if isinstance(emails, list) and emails:
        return str(emails[0].get("VALUE", ""))
    return ""


def _format_b24_date(value: str | None) -> str:
    """Convert Bitrix24 date (dd.mm.YYYY or YYYY-MM-DD or unix) to dd.mm.YYYY."""
    if not value:
        return ""
    # Already dd.mm.YYYY
    if len(value) == 10 and value[2] == "." and value[5] == ".":
        return value
    # YYYY-MM-DD
    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        try:
            return datetime.strptime(value, "%Y-%m-%d").strftime("%d.%m.%Y")
        except ValueError:
            return ""
    # Unix timestamp
    try:
        return datetime.fromtimestamp(int(value)).strftime("%d.%m.%Y")
    except (TypeError, ValueError, OSError):
        return ""


class Bitrix24ContractService:
    """Generates contracts from Bitrix24 deal data."""

    def __init__(self, client: Bitrix24Client) -> None:
        self.client = client

    @classmethod
    def from_portal(cls, portal) -> "Bitrix24ContractService":
        """Create service from a Bitrix24Portal instance."""
        client = Bitrix24Client.from_portal(portal)
        return cls(client)

    def get_deal_data(self, deal_id: int) -> dict:
        """Fetch deal from Bitrix24."""
        return self.client.get_deal(deal_id)

    def get_contact_data(self, contact_id: int) -> dict:
        """Fetch contact from Bitrix24."""
        return self.client.get_contact(contact_id)

    def get_company_data(self, company_id: int) -> dict:
        """Fetch company from Bitrix24."""
        return self.client.get_company(company_id)

    def build_context_from_deal(
        self,
        deal: dict,
        contact: dict | None = None,
        company: dict | None = None,
        overrides: dict | None = None,
    ) -> dict:
        """Map Bitrix24 deal/contact/company fields → normalized data dict.

        Args:
            deal: Bitrix24 deal dict (from ``crm.deal.get``).
            contact: Bitrix24 contact dict (from ``crm.contact.get``). Optional.
            company: Bitrix24 company dict (from ``crm.company.get``). Optional.
            overrides: User-edited fields from the UI form. These take
                precedence over CRM data.

        Returns:
            Data dict suitable for ``ContractRenderer.build_context_from_data()``.
        """
        overrides = overrides or {}

        # Field mapping settings (UF_CRM_* codes from env)
        field_marina = getattr(settings, "BITRIX24_CONTRACT_FIELD_MARINA", "")
        field_boat_type = getattr(settings, "BITRIX24_CONTRACT_FIELD_BOAT_TYPE", "")
        field_cabins = getattr(settings, "BITRIX24_CONTRACT_FIELD_CABINS", "")
        field_clients = getattr(settings, "BITRIX24_CONTRACT_FIELD_CLIENTS", "")
        field_client_country = getattr(settings, "BITRIX24_CONTRACT_FIELD_CLIENT_COUNTRY", "")
        field_trip_start = getattr(settings, "BITRIX24_CONTRACT_FIELD_TRIP_START", "")
        field_trip_end = getattr(settings, "BITRIX24_CONTRACT_FIELD_TRIP_END", "")
        field_cruise_type = getattr(settings, "BITRIX24_CONTRACT_FIELD_CRUISE_TYPE", "")
        field_extra = getattr(settings, "BITRIX24_CONTRACT_FIELD_EXTRA", "")
        field_tax = getattr(settings, "BITRIX24_CONTRACT_FIELD_TAX", "")
        field_birthdate = getattr(settings, "BITRIX24_CONTRACT_FIELD_BIRTHDATE", "")
        field_passport_number = getattr(settings, "BITRIX24_CONTRACT_FIELD_PASSPORT_NUMBER", "")
        field_passport_date = getattr(settings, "BITRIX24_CONTRACT_FIELD_PASSPORT_DATE", "")
        field_passport_issued = getattr(settings, "BITRIX24_CONTRACT_FIELD_PASSPORT_ISSUED", "")
        field_passport_bplace = getattr(settings, "BITRIX24_CONTRACT_FIELD_PASSPORT_BPLACE", "")

        # Extract from deal
        marina = _b24_field(deal, field_marina) if field_marina else ""
        boat_type = _b24_field(deal, field_boat_type) if field_boat_type else ""
        cabins = _b24_field(deal, field_cabins) if field_cabins else ""
        clients = _b24_field(deal, field_clients) if field_clients else ""
        client_country = _b24_field(deal, field_client_country) if field_client_country else ""
        trip_start = _format_b24_date(_b24_field(deal, field_trip_start)) if field_trip_start else ""
        trip_end = _format_b24_date(_b24_field(deal, field_trip_end)) if field_trip_end else ""
        cruise_type = _b24_field(deal, field_cruise_type) if field_cruise_type else ""
        extra_items = _b24_multi_field(deal, field_extra) if field_extra else []
        tax_value = _b24_field(deal, field_tax) if field_tax else None

        # Price from deal
        price_eur = float(deal.get("OPPORTUNITY") or 0)
        eur_rate = float(getattr(settings, "CONTRACT_EUR_RATE", 100.0))

        # Extract from contact
        client_fullname = ""
        email = ""
        phone = ""
        client_bdate = ""
        client_passport_number = ""
        client_passport_date = ""
        client_passport_text = ""
        client_passport_bplace = ""

        if contact:
            name = contact.get("NAME") or ""
            last_name = contact.get("LAST_NAME") or ""
            second_name = contact.get("SECOND_NAME") or ""
            client_fullname = " ".join(filter(None, [last_name, name, second_name]))
            email = _b24_contact_email(contact)
            phone = _b24_contact_phone(contact)
            client_bdate = _format_b24_date(_b24_field(contact, field_birthdate)) if field_birthdate else ""
            client_passport_number = _b24_field(contact, field_passport_number) if field_passport_number else ""
            client_passport_date = _format_b24_date(_b24_field(contact, field_passport_date)) if field_passport_date else ""
            client_passport_text = _b24_field(contact, field_passport_issued) if field_passport_issued else ""
            client_passport_bplace = _b24_field(contact, field_passport_bplace) if field_passport_bplace else ""

        # Extract from company
        is_legal_entity = bool(company)
        company_fullname = ""
        company_address = ""
        company_account = ""
        company_currency = ""
        company_inn = ""
        company_kpp = ""
        company_bik = ""
        company_bank = ""
        company_korr = ""

        if company:
            company_fullname = company.get("TITLE") or ""
            # Company UF_CRM_* fields are typically less standardized,
            # so we try common patterns
            company_address = company.get("ADDRESS") or ""
            company_inn = str(company.get("UF_CRM_INN") or company.get("REQUISITES_INN") or "")
            company_kpp = str(company.get("UF_CRM_KPP") or company.get("REQUISITES_KPP") or "")

        # Apply overrides from UI form
        data = {
            "number": overrides.get("number") or deal.get("ID", ""),
            "price_eur": float(overrides.get("price_eur", price_eur)),
            "eur_rate": float(overrides.get("eur_rate", eur_rate)),
            "marina": overrides.get("marina", marina) or "",
            "boat_type": overrides.get("boat_type", boat_type) or "",
            "cabins": overrides.get("cabins", cabins) or "",
            "clients": overrides.get("clients", clients),
            "client_country": overrides.get("client_country", client_country) or "",
            "trip_start": overrides.get("trip_start", trip_start) or "",
            "trip_end": overrides.get("trip_end", trip_end) or "",
            "cruise_type": overrides.get("cruise_type", cruise_type) or "",
            "client_fullname": overrides.get("client_fullname", client_fullname) or "",
            "email": overrides.get("email", email) or "",
            "phone": overrides.get("phone", phone) or "",
            "client_bdate": overrides.get("client_bdate", client_bdate) or "",
            "client_passport_number": overrides.get("client_passport_number", client_passport_number) or "",
            "client_passport_date": overrides.get("client_passport_date", client_passport_date) or "",
            "client_passport_text": overrides.get("client_passport_text", client_passport_text) or "",
            "client_passport_bplace": overrides.get("client_passport_bplace", client_passport_bplace) or "",
            "payment_values": overrides.get("payment_values") or [],
            "extra_items": overrides.get("extra_items", extra_items) or [],
            "tax_value": overrides.get("tax_value", tax_value),
            "payment_parts": overrides.get("payment_parts"),
            "is_legal_entity": is_legal_entity,
            "company_fullname": overrides.get("company_fullname", company_fullname) or "",
            "company_address": overrides.get("company_address", company_address) or "",
            "company_account": overrides.get("company_account", company_account) or "",
            "company_currency": overrides.get("company_currency", company_currency) or "",
            "company_inn": overrides.get("company_inn", company_inn) or "",
            "company_kpp": overrides.get("company_kpp", company_kpp) or "",
            "company_bik": overrides.get("company_bik", company_bik) or "",
            "company_bank": overrides.get("company_bank", company_bank) or "",
            "company_korr": overrides.get("company_korr", company_korr) or "",
        }

        return data

    def render_contract(
        self,
        deal_id: int,
        overrides: dict | None = None,
    ) -> ContractRenderResult:
        """Full pipeline: fetch data from Bitrix24 → build context → render PDF.

        Args:
            deal_id: Bitrix24 deal ID.
            overrides: User-edited fields from the UI form.

        Returns:
            ContractRenderResult with file_url, file_path, context.
        """
        deal = self.get_deal_data(deal_id)

        # Resolve contact
        contact_id = deal.get("CONTACT_ID")
        contact = self.get_contact_data(int(contact_id)) if contact_id else None

        # Resolve company
        company_id = deal.get("COMPANY_ID")
        company = self.get_company_data(int(company_id)) if company_id else None

        data = self.build_context_from_deal(deal, contact, company, overrides)
        context = ContractRenderer.build_context_from_data(data)

        contracts_dir = Path(settings.MEDIA_ROOT) / "contracts"
        contracts_dir.mkdir(parents=True, exist_ok=True)

        output_pdf_name = f"contract_b24_{deal_id}_{uuid.uuid4().hex}.pdf"
        output_path = contracts_dir / output_pdf_name
        template_name = (
            settings.CONTRACT_HTML_TEMPLATE_U
            if context.get("is_legal_entity")
            else settings.CONTRACT_HTML_TEMPLATE
        )
        html_content = render_to_string(template_name, context)
        HTML(string=html_content, base_url=str(settings.BASE_DIR)).write_pdf(output_path)
        file_url = f"{settings.MEDIA_URL}contracts/{output_path.name}"

        return ContractRenderResult(file_url=file_url, file_path=output_path, context=context)
