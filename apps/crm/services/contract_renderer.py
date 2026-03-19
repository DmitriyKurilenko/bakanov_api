from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import uuid

from django.conf import settings
from django.template.loader import render_to_string
from weasyprint import HTML

from apps.crm.services.amocrm import AmoCRMClient
from payments_list import (
    BANK_TOCHKA,
    CIFRA_BANK,
    CRYPTO,
    KAZ_FREEDOM_BANK,
    RAIF_BAKANOVA,
    SBER_BATUKOV,
    SBP_BAKANOV,
    SBP_ZHELONKINA,
    SOVKOM_BAKANOVA,
    TINKOFF_BAKANOV,
    URAL_ZAKHAROV,
    VAKIF,
    YANDEX_BAKANOV,
)


PAYMENT_DETAILS = {
    "Vakif": VAKIF,
    "СБП Баканов": SBP_BAKANOV,
    "СБП Желонкина": SBP_ZHELONKINA,
    "Тинькофф р/с": TINKOFF_BAKANOV,
    "Крипто": CRYPTO,
    "Сбербанк Батюков": SBER_BATUKOV,
    "Райфайзен Баканова": RAIF_BAKANOVA,
    "Уралсиб Захаров": URAL_ZAKHAROV,
    "Яндекс": YANDEX_BAKANOV,
    "Фридом Банк Казахстан": KAZ_FREEDOM_BANK,
    "Совкомбанк Баканова": SOVKOM_BAKANOVA,
    "Цифра Банк": CIFRA_BANK,
    "Банк Точка": BANK_TOCHKA,
}


def _get_custom_field_value(
    custom_fields: list[dict],
    *,
    field_id: int | None = None,
    field_name: str | None = None,
    field_code: str | None = None,
):
    for field in custom_fields or []:
        if field_id is not None and field.get("field_id") == field_id:
            values = field.get("values") or []
            return values[0].get("value") if values else None
        if field_name is not None and field.get("field_name") == field_name:
            values = field.get("values") or []
            return values[0].get("value") if values else None
        if field_code is not None and field.get("field_code") == field_code:
            values = field.get("values") or []
            return values[0].get("value") if values else None
    return None


def _get_custom_field_values(
    custom_fields: list[dict],
    *,
    field_id: int | None = None,
    field_name: str | None = None,
    field_code: str | None = None,
) -> list:
    for field in custom_fields or []:
        if field_id is not None and field.get("field_id") == field_id:
            return [item.get("value") for item in field.get("values", []) if "value" in item]
        if field_name is not None and field.get("field_name") == field_name:
            return [item.get("value") for item in field.get("values", []) if "value" in item]
        if field_code is not None and field.get("field_code") == field_code:
            return [item.get("value") for item in field.get("values", []) if "value" in item]
    return []


def _format_unix_date(value) -> str:
    if not value:
        return ""
    try:
        return datetime.fromtimestamp(int(value)).strftime("%d.%m.%Y")
    except (TypeError, ValueError):
        return ""


def _format_amount(value) -> str:
    try:
        return f"{int(float(value)):,}".replace(",", " ")
    except (TypeError, ValueError):
        return "0"


def _plural_form(value: int, form1: str, form2: str, form5: str) -> str:
    value = abs(value) % 100
    if 11 <= value <= 19:
        return form5
    value = value % 10
    if value == 1:
        return form1
    if 2 <= value <= 4:
        return form2
    return form5


def _number_to_russian_words(value: int) -> str:
    if value == 0:
        return "ноль"

    units_male = ["", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
    units_female = ["", "одна", "две", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять"]
    teens = ["десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать", "пятнадцать", "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать"]
    tens = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят", "восемьдесят", "девяносто"]
    hundreds = ["", "сто", "двести", "триста", "четыреста", "пятьсот", "шестьсот", "семьсот", "восемьсот", "девятьсот"]

    scales = [
        ("", "", "", False),
        ("тысяча", "тысячи", "тысяч", True),
        ("миллион", "миллиона", "миллионов", False),
        ("миллиард", "миллиарда", "миллиардов", False),
    ]

    parts: list[str] = []
    scale_index = 0

    while value > 0:
        chunk = value % 1000
        value //= 1000
        if chunk == 0:
            scale_index += 1
            continue

        h = chunk // 100
        t = (chunk % 100) // 10
        u = chunk % 10

        chunk_words: list[str] = []
        if h:
            chunk_words.append(hundreds[h])

        if t == 1:
            chunk_words.append(teens[u])
        else:
            if t:
                chunk_words.append(tens[t])
            if u:
                unit_words = units_female if scale_index < len(scales) and scales[scale_index][3] else units_male
                chunk_words.append(unit_words[u])

        if scale_index > 0 and scale_index < len(scales):
            chunk_words.append(
                _plural_form(chunk, scales[scale_index][0], scales[scale_index][1], scales[scale_index][2])
            )

        parts.insert(0, " ".join(word for word in chunk_words if word))
        scale_index += 1

    return " ".join(parts).strip()


def _amount_to_words(value, currency: str) -> str:
    try:
        amount = int(float(value))
    except (TypeError, ValueError):
        amount = 0

    words = _number_to_russian_words(amount)
    if currency == "RUB":
        currency_word = _plural_form(amount, "рубль", "рубля", "рублей")
        return f"{words} {currency_word}"

    if currency == "EUR":
        return f"{words} евро"

    return words


def _build_destination(marina: str) -> tuple[str, str, str]:
    destination = ""
    destination_flight = ""
    nalog = ""

    if "Турция" in marina:
        destination = "Турецкой Республики"
        destination_flight = "Турция"
    elif "Сейшел" in marina or "Маэ" in marina or "Праслин" in marina:
        destination = "Республики Сейшелы"
        destination_flight = "Сейшелы"
        nalog = "Налоги и сборы оплачиваются дополнительно по условиям яхтенной компании."
    elif "Тайланд" in marina or "Таиланд" in marina:
        destination = "Королевства Таиланд"
        destination_flight = "Таиланд"
    elif "Черногория" in marina:
        destination = "Черногории"
        destination_flight = "Черногория"

    return destination, destination_flight, nalog


def _calculate_payment_parts(custom_fields: list[dict], total_price_eur: float, eur_rate: float) -> list[dict]:
    parts = []

    def append_part(amount_field_id: int, date_field_id: int, fallback_days: int):
        amount = _get_custom_field_value(custom_fields, field_id=amount_field_id)
        if amount in (None, ""):
            return

        date_raw = _get_custom_field_value(custom_fields, field_id=date_field_id)
        date_value = _format_unix_date(date_raw) if date_raw else (datetime.today() + timedelta(days=fallback_days)).strftime("%d.%m.%Y")
        amount_f = float(amount)
        percent = round((amount_f / total_price_eur) * 100, 2) if total_price_eur else 0
        rub_amount = int(amount_f * eur_rate)

        parts.append(
            {
                "description": f"До {date_value}",
                "euro": _format_amount(amount_f),
                "rub": _format_amount(rub_amount),
                "euro_text": _amount_to_words(amount_f, "EUR"),
                "rub_text": _amount_to_words(rub_amount, "RUB"),
                "percent": percent,
            }
        )

    append_part(1072893, 1072895, 2)
    append_part(1072897, 1072899, 30)
    append_part(1072901, 1072903, 60)
    append_part(1072905, 1072907, 90)

    if not parts:
        rub_amount = int(total_price_eur * eur_rate)
        parts.append(
            {
                "description": f"До {(datetime.today() + timedelta(days=2)).strftime('%d.%m.%Y')}",
                "euro": _format_amount(total_price_eur),
                "rub": _format_amount(rub_amount),
                "euro_text": _amount_to_words(total_price_eur, "EUR"),
                "rub_text": _amount_to_words(rub_amount, "RUB"),
                "percent": 100,
            }
        )

    return parts


@dataclass
class ContractRenderResult:
    file_url: str
    file_path: Path
    context: dict


class ContractRenderer:
    def __init__(self, amocrm: AmoCRMClient | None = None) -> None:
        self.amocrm = amocrm or AmoCRMClient.from_settings()

    def render_for_lead(self, lead_id: int) -> ContractRenderResult:
        lead = self.amocrm.get_lead(lead_id)
        contact = self._resolve_primary_contact(lead)
        company = self._resolve_primary_company(lead)
        context = self._build_context(lead, contact, company)

        contracts_dir = Path(settings.MEDIA_ROOT) / "contracts"
        contracts_dir.mkdir(parents=True, exist_ok=True)

        output_pdf_name = f"contract_{lead_id}_{uuid.uuid4().hex}.pdf"
        output_path = contracts_dir / output_pdf_name
        template_name = settings.CONTRACT_HTML_TEMPLATE_U if context.get("is_legal_entity") else settings.CONTRACT_HTML_TEMPLATE
        html_content = render_to_string(template_name, context)
        HTML(string=html_content, base_url=str(settings.BASE_DIR)).write_pdf(output_path)
        file_url = f"{settings.MEDIA_URL}contracts/{output_path.name}"

        return ContractRenderResult(file_url=file_url, file_path=output_path, context=context)

    def render_extra_agreement_for_lead(self, lead_id: int) -> ContractRenderResult:
        lead = self.amocrm.get_lead(lead_id)
        contact = self._resolve_primary_contact(lead)
        context = self._build_extra_agreement_context(lead, contact)

        contracts_dir = Path(settings.MEDIA_ROOT) / "contracts"
        contracts_dir.mkdir(parents=True, exist_ok=True)

        output_pdf_name = f"extra_agreement_{lead_id}_{uuid.uuid4().hex}.pdf"
        output_path = contracts_dir / output_pdf_name
        template_name = getattr(settings, "EXTRA_CONTRACT_HTML_TEMPLATE", "contracts/extra_contract.html")
        html_content = render_to_string(template_name, context)
        HTML(string=html_content, base_url=str(settings.BASE_DIR)).write_pdf(output_path)
        file_url = f"{settings.MEDIA_URL}contracts/{output_path.name}"

        return ContractRenderResult(file_url=file_url, file_path=output_path, context=context)

    def _resolve_primary_contact(self, lead: dict) -> dict:
        contacts = lead.get("_embedded", {}).get("contacts", [])
        if not contacts:
            return {}
        contact_id = contacts[0].get("id")
        if not contact_id:
            return {}
        return self.amocrm.get_contact(int(contact_id))

    def _resolve_primary_company(self, lead: dict) -> dict:
        companies = lead.get("_embedded", {}).get("companies", [])
        if not companies:
            return {}
        company_id = companies[0].get("id")
        if not company_id:
            return {}
        return self.amocrm.get_company(int(company_id))

    def _build_context(self, lead: dict, contact: dict, company: dict | None = None) -> dict:
        custom_fields = lead.get("custom_fields_values") or []
        contact_fields = contact.get("custom_fields_values") or []
        company_fields = (company or {}).get("custom_fields_values") or []

        marina = _get_custom_field_value(custom_fields, field_name="Марина") or ""
        destination, destination_flight, nalog = _build_destination(str(marina))

        price_eur = float(lead.get("price") or 0)
        eur_rate = float(getattr(settings, "CONTRACT_EUR_RATE", 100.0))
        currency_percent_raw = _get_custom_field_value(custom_fields, field_id=1076365)
        if currency_percent_raw not in (None, ""):
            try:
                eur_rate = round(eur_rate + (eur_rate * (float(currency_percent_raw) / 100)), 4)
            except (TypeError, ValueError):
                pass
        price_rub = int(float(price_eur) * eur_rate)

        date_start_unix = _get_custom_field_value(custom_fields, field_name="Дата круиза")
        date_end_unix = _get_custom_field_value(custom_fields, field_id=1055427)
        trip_start = _format_unix_date(date_start_unix)
        trip_end = _format_unix_date(date_end_unix)
        if not trip_end and trip_start:
            start = datetime.strptime(trip_start, "%d.%m.%Y")
            trip_end = (start + timedelta(days=7)).strftime("%d.%m.%Y")

        clients_raw = _get_custom_field_value(custom_fields, field_name="Количество человек")
        clients_text = ""
        if clients_raw is not None:
            clients_str = str(clients_raw)
            if clients_str in {"2", "3", "4"}:
                clients_text = f"{clients_str} человека"
            else:
                clients_text = f"{clients_str} человек"

        client_fullname = contact.get("name") or ""
        cruise_type = _get_custom_field_value(custom_fields, field_name="Вид договора") or ""

        payment_values = _get_custom_field_values(custom_fields, field_id=1054105)
        payment_lines = [PAYMENT_DETAILS.get(str(value), str(value)) for value in payment_values]
        payment = [line for line in payment_lines if line]

        extra_include = []
        extra_include.extend([str(v) for v in _get_custom_field_values(custom_fields, field_id=1055020)])
        extra_include.extend([str(v) for v in _get_custom_field_values(custom_fields, field_id=1055897)])
        extra_text = ""
        if extra_include:
            extra_text = "\n".join(f"- {item}" for item in extra_include)

        tax_value = _get_custom_field_value(custom_fields, field_id=1076917)
        if tax_value not in (None, ""):
            nalog = f"Налоги и сборы в размере {tax_value} евро."

        if cruise_type == "Групповой" or extra_include:
            part13 = (
                "1.3. Поставщиками услуг, оказывающими Заказчику услуги, являются "
                "непосредственные исполнители (яхтенные компании и уполномоченные лица)."
            )
        else:
            part13 = ""

        parts = _calculate_payment_parts(custom_fields, price_eur, eur_rate)

        context = {
            "number": lead.get("id", ""),
            "contract_date": datetime.now().strftime("%d.%m.%Y"),
            "boat_type": _get_custom_field_value(custom_fields, field_name="Тип яхты") or "",
            "cabins": _get_custom_field_value(custom_fields, field_name="Количество кают") or "",
            "client_country": _get_custom_field_value(custom_fields, field_name="Страна клиента") or "",
            "client_fullname": client_fullname,
            "clients": clients_text,
            "destination": destination,
            "destination_flight": destination_flight,
            "extra": extra_text,
            "marina": marina,
            "trip_start": trip_start,
            "trip_end": trip_end,
            "price": _format_amount(price_eur),
            "price_text": _amount_to_words(price_eur, "EUR"),
            "price_rub": _format_amount(price_rub),
            "price_rub_text": _amount_to_words(price_rub, "RUB"),
            "email": _get_custom_field_value(contact_fields, field_name="Email") or "",
            "phone": _get_custom_field_value(contact_fields, field_name="Телефон")
            or _get_custom_field_value(contact_fields, field_code="PHONE")
            or "",
            "client_bdate": _format_unix_date(_get_custom_field_value(contact_fields, field_name="День рождения")),
            "client_passport_number": _get_custom_field_value(contact_fields, field_name="Паспорт номер") or "",
            "client_passport_date": _format_unix_date(_get_custom_field_value(contact_fields, field_name="Паспорт дата")),
            "client_passport_text": _get_custom_field_value(contact_fields, field_name="Паспорт кем выдан") or "",
            "client_passport_bplace": _get_custom_field_value(contact_fields, field_name="Паспорт место рождения") or "",
            "nalog": nalog,
            "part13": part13,
            "p": "",
            "checkIn": "16:00",
            "checkOut": "09:00",
            "part": parts,
            "payment": payment,
            "payment_parts": parts,
            "is_legal_entity": bool(company),
            "company_fullname": (company or {}).get("name") or "",
            "company_address": _get_custom_field_value(company_fields, field_name="Адрес") or "",
            "company_account": _get_custom_field_value(company_fields, field_name="Номер счета") or "",
            "company_currency": _get_custom_field_value(company_fields, field_name="Валюта") or "",
            "company_inn": _get_custom_field_value(company_fields, field_name="ИНН") or "",
            "company_kpp": _get_custom_field_value(company_fields, field_name="КПП") or "",
            "company_bik": _get_custom_field_value(company_fields, field_name="БИК") or "",
            "company_bank": _get_custom_field_value(company_fields, field_name="Банк") or "",
            "company_korr": _get_custom_field_value(company_fields, field_name="Корр счет") or "",
        }

        return context

    def _build_extra_agreement_context(self, lead: dict, contact: dict) -> dict:
        custom_fields = lead.get("custom_fields_values") or []
        contact_fields = contact.get("custom_fields_values") or []
        extra_payments = _get_custom_field_value(custom_fields, field_id=1074173) or ""
        contract_date = datetime.now().strftime("%d.%m.%Y")

        client_fullname = (
            contact.get("name")
            or _get_custom_field_value(contact_fields, field_name="ФИО")
            or _get_custom_field_value(contact_fields, field_name="Имя")
            or "Клиент"
        )

        return {
            "number": lead.get("id", ""),
            "contract_date": contract_date,
            "client_fullname": client_fullname,
            "extra_payments": str(extra_payments).strip(),
        }
