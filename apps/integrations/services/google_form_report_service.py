from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
import uuid

from django.core.files.base import ContentFile
from django.template.loader import render_to_string
from django.utils import timezone
from weasyprint import HTML

from apps.crm.models import GoogleFormReport
from apps.crm.services.amocrm import AmoCRMClient
from apps.crm.services.contract_renderer import _format_unix_date
from apps.integrations.services.translation_service import translate_ru_to_en


FORM_TITLES_RU = {
    GoogleFormReport.FormType.MENU: "Отчет по меню",
    GoogleFormReport.FormType.CRUISE: "Отчет по пожеланиям к круизу",
}
FORM_TITLES_EN = {
    GoogleFormReport.FormType.MENU: "Menu report",
    GoogleFormReport.FormType.CRUISE: "Cruise preferences report",
}


@dataclass
class FormReportArtifact:
    report: GoogleFormReport
    file_path: Path


@dataclass
class GeneratedFormReports:
    lead_id: int
    form_type: str
    ru: FormReportArtifact
    en: FormReportArtifact


class GoogleFormReportService:
    def __init__(self, amocrm: AmoCRMClient | None = None) -> None:
        self.amocrm = amocrm or AmoCRMClient.from_settings()

    def generate(self, *, lead_id: int, form_type: str, answers: dict) -> GeneratedFormReports:
        normalized_answers = self._normalize_answers(answers)
        lead_context = self._load_lead_context(lead_id)

        ru_payload = normalized_answers
        en_payload = self._translate_payload(normalized_answers)

        ru_context = self._build_render_context(lead_id=lead_id, form_type=form_type, language="ru", answers=ru_payload, lead_ctx=lead_context)
        en_context = self._build_render_context(lead_id=lead_id, form_type=form_type, language="en", answers=en_payload, lead_ctx=lead_context)

        ru_artifact = self._render_and_store(lead_id=lead_id, form_type=form_type, language=GoogleFormReport.Language.RU, payload=ru_payload, context=ru_context)
        en_artifact = self._render_and_store(lead_id=lead_id, form_type=form_type, language=GoogleFormReport.Language.EN, payload=en_payload, context=en_context)

        return GeneratedFormReports(lead_id=lead_id, form_type=form_type, ru=ru_artifact, en=en_artifact)

    def _normalize_answers(self, answers: dict) -> dict:
        result: dict = {}
        for key, value in (answers or {}).items():
            if value is None:
                continue
            key_s = str(key).strip()
            if not key_s:
                continue
            if isinstance(value, (list, tuple)):
                cleaned = [str(v).strip() for v in value if str(v).strip()]
                result[key_s] = cleaned
            else:
                result[key_s] = str(value).strip()
        return result

    def _translate_payload(self, payload: dict) -> dict:
        translated: dict = {}
        for key, value in payload.items():
            key_en = translate_ru_to_en(str(key))
            if isinstance(value, list):
                translated[key_en] = [translate_ru_to_en(str(item)) for item in value]
            else:
                translated[key_en] = translate_ru_to_en(str(value))
        return translated

    def _load_lead_context(self, lead_id: int) -> dict:
        lead = self.amocrm.get_lead(int(lead_id))
        contact_name = ""
        contacts = lead.get("_embedded", {}).get("contacts", [])
        if contacts:
            contact_id = contacts[0].get("id")
            if contact_id:
                try:
                    contact = self.amocrm.get_contact(int(contact_id))
                    contact_name = str(contact.get("name") or "")
                except Exception:
                    contact_name = ""

        custom_fields = lead.get("custom_fields_values") or []
        clients = ""
        trip_start = ""
        trip_end = ""
        for field in custom_fields:
            field_name = str(field.get("field_name") or "")
            values = field.get("values") or []
            if not values:
                continue
            raw = values[0].get("value")
            if field_name == "Количество человек" and raw not in (None, ""):
                raw_s = str(raw)
                clients = f"{raw_s} человека" if raw_s and raw_s[-1] in {"2", "3", "4"} else f"{raw_s} человек"
            if field_name == "Дата круиза":
                trip_start = _format_unix_date(raw)
                try:
                    start_dt = datetime.fromtimestamp(int(raw), tz=timezone.get_current_timezone())
                    trip_end = (start_dt + timedelta(days=7)).strftime("%d.%m.%Y")
                except Exception:
                    trip_end = ""

        return {
            "organizer_name": contact_name or str(lead.get("name") or ""),
            "clients": clients,
            "trip_start": trip_start,
            "trip_end": trip_end,
        }

    def _build_render_context(self, *, lead_id: int, form_type: str, language: str, answers: dict, lead_ctx: dict) -> dict:
        is_en = language == "en"
        answer_rows = []
        for key, value in (answers or {}).items():
            if isinstance(value, list):
                answer_rows.append({"question": key, "is_list": True, "items": value, "value": ""})
            else:
                answer_rows.append({"question": key, "is_list": False, "items": [], "value": value})
        return {
            "lead_id": int(lead_id),
            "generated_at": timezone.localtime().strftime("%d.%m.%Y %H:%M"),
            "title": FORM_TITLES_EN.get(form_type, "Form report") if is_en else FORM_TITLES_RU.get(form_type, "Отчет по форме"),
            "subtitle": ("From Google Form + CRM" if is_en else "Из Google Формы + CRM"),
            "labels": {
                "organizer": "Organizer" if is_en else "Организатор",
                "clients": "Clients" if is_en else "Количество участников",
                "trip_period": "Trip dates" if is_en else "Даты круиза",
                "from": "from" if is_en else "с",
                "to": "to" if is_en else "по",
                "answers": "Form answers" if is_en else "Ответы анкеты",
                "lead": "Lead" if is_en else "Сделка",
            },
            "language": language,
            "form_type": form_type,
            "answers": answers,
            "answer_rows": answer_rows,
            **lead_ctx,
        }

    def _render_and_store(self, *, lead_id: int, form_type: str, language: str, payload: dict, context: dict) -> FormReportArtifact:
        html = render_to_string("forms/google_form_report.html", context)
        reports_dir = Path("/app/media/menus")
        reports_dir.mkdir(parents=True, exist_ok=True)
        file_name = f"{form_type}_{language}_{lead_id}_{uuid.uuid4().hex}.pdf"
        file_path = reports_dir / file_name
        HTML(string=html, base_url="/app").write_pdf(file_path)

        report = GoogleFormReport.objects.create(
            lead_id=int(lead_id),
            form_type=form_type,
            language=language,
            payload=payload,
        )
        with file_path.open("rb") as source:
            report.file.save(file_name, ContentFile(source.read()), save=True)

        stored_path = Path(report.file.path)
        if stored_path != file_path and file_path.exists():
            try:
                file_path.unlink()
            except OSError:
                pass
            file_path = stored_path

        return FormReportArtifact(report=report, file_path=file_path)
