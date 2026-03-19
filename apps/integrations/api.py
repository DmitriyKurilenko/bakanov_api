import json
import logging

from ninja import Router

from apps.crm.models import GoogleFormReport
from apps.crm.services.manager_assignment import DealAssignmentService
from apps.integrations.schemas import GoogleFormWebhookPayload
from apps.integrations.services.email_service import send_analysis_email, send_form_report_email
from apps.integrations.services.pdf_service import generate_bilingual_pdf
from apps.integrations.services.google_form_report_service import GoogleFormReportService
from apps.integrations.services.telephony_pipeline import (
    TelephonyWebhookProcessor,
    extract_telephony_payload,
)
from apps.integrations.tasks import process_amocrm_spam_lead_webhook
from apps.integrations.services.translation_service import translate_ru_to_en

router = Router(tags=["integrations"])
logger = logging.getLogger(__name__)


@router.post("/webhooks/zadarma")
def zadarma_webhook(request):
    raw_data = extract_telephony_payload(request)
    return TelephonyWebhookProcessor().process(provider="zadarma", raw_data=raw_data).as_dict()


@router.post("/webhooks/novofon")
def novofon_webhook(request):
    raw_data = extract_telephony_payload(request)
    return TelephonyWebhookProcessor().process(provider="novofon", raw_data=raw_data).as_dict()


@router.post("/webhooks/google-form")
def google_form_webhook(request, payload: GoogleFormWebhookPayload):
    en_text = translate_ru_to_en(payload.source_text)
    pdf_url = generate_bilingual_pdf(payload.source_text, en_text)
    send_analysis_email(
        subject=f"Google Form: {payload.name}",
        body=f"PDF сформирован: {pdf_url}",
    )
    return {"status": "ok", "pdf_url": pdf_url}


def _extract_request_payload(request) -> dict:
    data: dict = {}
    if request.body:
        try:
            parsed = json.loads(request.body.decode("utf-8"))
            if isinstance(parsed, dict):
                data.update(parsed)
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass

    for key in request.POST.keys():
        values = request.POST.getlist(key)
        if not values:
            continue
        data[key] = values if len(values) > 1 else values[0]

    return data


def _extract_google_form_payload(request) -> dict:
    return _extract_request_payload(request)


def _detect_lead_id(data: dict, *, include_amocrm_nested_keys: bool = False) -> int | None:
    candidates = [
        data.get("lead_id"),
        data.get("Номер договора"),
        data.get("номер договора"),
        data.get("contract_number"),
        data.get("deal_id"),
    ]
    for item in candidates:
        if isinstance(item, list) and item:
            item = item[0]
        if item is None:
            continue
        item_s = str(item).strip()
        if item_s.isdigit():
            return int(item_s)

    if include_amocrm_nested_keys:
        for key, value in data.items():
            key_l = str(key).lower()
            if "lead" not in key_l or not key_l.endswith("[id]"):
                continue
            value_s = str(value).strip()
            if value_s.isdigit():
                return int(value_s)

    return None


def _normalize_answers_from_payload(data: dict) -> dict:
    answers = data.get("answers")
    if isinstance(answers, dict):
        return answers

    ignored_keys = {"lead_id", "contract_number", "deal_id", "form_type", "answers", "Номер договора", "номер договора"}
    return {k: v for k, v in data.items() if k not in ignored_keys}


def _google_form_report_response(result):
    return {
        "status": "ok",
        "lead_id": result.lead_id,
        "form_type": result.form_type,
        "reports": [
            {
                "language": GoogleFormReport.Language.RU,
                "report_id": result.ru.report.id,
                "file": result.ru.report.file.url if result.ru.report.file else "",
            },
            {
                "language": GoogleFormReport.Language.EN,
                "report_id": result.en.report.id,
                "file": result.en.report.file.url if result.en.report.file else "",
            },
        ],
    }


def _send_google_form_report_emails(result) -> None:
    for language, artifact in (
        (GoogleFormReport.Language.RU, result.ru),
        (GoogleFormReport.Language.EN, result.en),
    ):
        send_form_report_email(
            lead_id=int(result.lead_id),
            form_type=str(result.form_type),
            language=str(language),
            file_url=artifact.report.file.url if artifact.report.file else "",
            attachment_path=artifact.file_path,
        )


@router.post("/webhooks/google-form/menu")
def google_form_menu_webhook(request):
    data = _extract_google_form_payload(request)
    lead_id = _detect_lead_id(data)
    if not lead_id:
        return {"status": "error", "detail": "lead_id / Номер договора is required"}
    answers = _normalize_answers_from_payload(data)
    result = GoogleFormReportService().generate(
        lead_id=lead_id,
        form_type=GoogleFormReport.FormType.MENU,
        answers=answers,
    )
    _send_google_form_report_emails(result)
    return _google_form_report_response(result)


@router.post("/webhooks/amocrm/spam-lead")
def amocrm_spam_lead_webhook(request):
    data = _extract_request_payload(request)
    service = DealAssignmentService()
    lead_ids = service.extract_webhook_lead_ids(raw_body=data, post_data=request.POST)

    if not lead_ids:
        single_lead_id = _detect_lead_id(data, include_amocrm_nested_keys=True)
        if single_lead_id:
            lead_ids = [single_lead_id]

    if not lead_ids:
        return {"status": "ok", "queued": 0, "processed": 0, "message": "No lead ids in webhook payload"}

    return {
        "status": "ok",
        "queued": len(lead_ids),
        "processed": 0,
        "lead_ids": lead_ids,
        "task_ids": [process_amocrm_spam_lead_webhook.delay(lead_id).id for lead_id in lead_ids],
    }


@router.get("/amocrm/oauth/callback")
def amocrm_oauth_callback(request):
    error = str(request.GET.get("error") or "").strip()
    if error:
        error_description = str(request.GET.get("error_description") or "").strip()
        logger.warning(
            "amoCRM oauth callback returned error: error=%s, description=%s",
            error,
            error_description,
        )
        return {
            "status": "error",
            "error": error,
            "error_description": error_description,
        }

    code = str(request.GET.get("code") or "").strip()
    state = str(request.GET.get("state") or "").strip()
    if not code:
        return {
            "status": "error",
            "detail": "Missing 'code' query param",
        }

    logger.info(
        "amoCRM oauth callback received: code_len=%s state_present=%s",
        len(code),
        bool(state),
    )
    return {
        "status": "ok",
        "detail": "Authorization code received",
        "code": code,
        "state": state,
    }


@router.post("/webhooks/google-form/cruise")
def google_form_cruise_webhook(request):
    data = _extract_google_form_payload(request)
    lead_id = _detect_lead_id(data)
    if not lead_id:
        return {"status": "error", "detail": "lead_id / Номер договора is required"}
    answers = _normalize_answers_from_payload(data)
    result = GoogleFormReportService().generate(
        lead_id=lead_id,
        form_type=GoogleFormReport.FormType.CRUISE,
        answers=answers,
    )
    _send_google_form_report_emails(result)
    return _google_form_report_response(result)
