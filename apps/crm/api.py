from ninja import Router
import json
import logging
import requests
from django.conf import settings

from apps.crm.schemas import AssignmentResponse, ContractResponse, ExtraContractResponse, LeadRequest, GenericResponse
from apps.crm.tasks import process_amo_new_deal_webhook, sync_amo_managers as sync_amo_managers_task
from apps.crm.services.amocrm import AmoCRMClient
from apps.crm.services.manager_assignment import DealAssignmentService
from apps.crm.services.contract_renderer import ContractRenderer
from apps.integrations.services.email_service import send_contract_email, send_extra_contract_email
from apps.integrations.services.telegram_service import send_telegram_message

router = Router(tags=["crm"])
logger = logging.getLogger(__name__)


def _lead_id(payload: LeadRequest) -> int:
    return int(payload.lead_id)


@router.post("/contract/generate", response=ContractResponse)
def generate_contract(request, payload: LeadRequest):
    lead_id = _lead_id(payload)
    amocrm = AmoCRMClient.from_settings()
    lead = amocrm.get_lead(lead_id)
    renderer = ContractRenderer(amocrm=amocrm)
    result = renderer.render_for_lead(lead_id)
    contract_file_url = result.file_url
    send_contract_email(lead, contract_file_url, attachment_path=result.file_path)

    warnings: list[str] = []
    try:
        amocrm.upload_contract_link(lead_id, contract_file_url)
    except requests.RequestException as exc:
        warning = f"failed to upload contract link to amoCRM lead: {exc}"
        warnings.append(warning)
        logger.warning("Contract link upload failed for lead_id=%s: %s", lead_id, exc)

    if settings.CONTRACT_FILE_FIELD_ID:
        try:
            amocrm.upload_file_to_lead_field(
                lead_id=lead_id,
                file_path=result.file_path,
                field_id=settings.CONTRACT_FILE_FIELD_ID,
            )
        except requests.RequestException as exc:
            warning = f"failed to upload contract file to amoCRM lead field: {exc}"
            warnings.append(warning)
            logger.warning("Contract file upload failed for lead_id=%s, field_id=%s: %s", lead_id, settings.CONTRACT_FILE_FIELD_ID, exc)

    if warnings:
        return {
            "status": "warning",
            "contract_file_url": contract_file_url,
            "detail": "Contract generated, but some amoCRM upload operations failed",
            "warnings": warnings,
        }

    return {"status": "ok", "contract_file_url": contract_file_url}


@router.post("/contract/extra/generate", response=ExtraContractResponse)
def generate_extra_contract(request, payload: LeadRequest):
    lead_id = _lead_id(payload)
    amocrm = AmoCRMClient.from_settings()
    renderer = ContractRenderer(amocrm=amocrm)
    result = renderer.render_extra_agreement_for_lead(lead_id)

    warnings: list[str] = []
    try:
        extra_field_id = int(getattr(settings, "EXTRA_CONTRACT_FILE_FIELD_ID", 0) or 0)
        contract_field_id = int(getattr(settings, "CONTRACT_FILE_FIELD_ID", 0) or 0)
        upload_field_id = extra_field_id or contract_field_id
        if upload_field_id:
            amocrm.upload_file_to_lead_field(
                lead_id=lead_id,
                file_path=result.file_path,
                field_id=upload_field_id,
            )
    except requests.RequestException as exc:
        warning = f"failed to upload extra contract file to amoCRM lead field: {exc}"
        warnings.append(warning)
        logger.warning("Extra contract file upload failed for lead_id=%s: %s", lead_id, exc)

    send_extra_contract_email(
        lead_id=lead_id,
        file_url=result.file_url,
        attachment_path=result.file_path,
    )

    if warnings:
        return {
            "status": "warning",
            "extra_contract_file_url": result.file_url,
            "detail": "Extra contract generated, but amoCRM upload failed",
            "warnings": warnings,
        }

    return {"status": "ok", "extra_contract_file_url": result.file_url}


@router.post("/lead/assign-min-load", response=AssignmentResponse)
def assign_lead_to_free_manager(request, payload: LeadRequest):
    lead_id = _lead_id(payload)
    amocrm = AmoCRMClient.from_settings()
    assignment_service = DealAssignmentService(amocrm=amocrm)
    decision = assignment_service.choose_manager()
    if decision is None:
        return {"status": "error", "responsible_user_id": 0}
    selected_user_id = int(decision.manager.amo_user_id)
    amocrm.update_lead_responsible(lead_id, selected_user_id)
    return {"status": "ok", "responsible_user_id": selected_user_id}


@router.post("/lead/new/telegram-notify", response=GenericResponse)
def notify_telegram_about_new_lead(request, payload: LeadRequest):
    lead_id = _lead_id(payload)
    amocrm = AmoCRMClient.from_settings()
    lead = amocrm.get_lead(lead_id)
    lead_name = lead.get("name", "Без названия")
    lead_link = f"{amocrm.base_url}/leads/detail/{lead_id}"
    send_telegram_message(f"Новый lead: {lead_name}\nСсылка: {lead_link}")
    return {"status": "ok", "detail": "Telegram notification sent"}


@router.post("/amo/managers/sync", response=GenericResponse)
def sync_amo_managers(request):
    task = sync_amo_managers_task.delay()
    return {"status": "ok", "detail": f"Sync task queued: {task.id}"}


@router.post("/amo/webhook/new-deals")
def amo_new_deals_webhook(request):
    raw_body = {}
    if request.body:
        try:
            raw_body = json.loads(request.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raw_body = {}

    service = DealAssignmentService()
    lead_ids = service.extract_webhook_lead_ids(raw_body=raw_body, post_data=request.POST)
    if not lead_ids:
        return {"status": "ok", "queued": 0, "processed": 0, "message": "No lead ids in webhook payload"}

    task_ids = [process_amo_new_deal_webhook.delay(lead_id).id for lead_id in lead_ids]
    return {
        "status": "ok",
        "queued": len(lead_ids),
        "processed": 0,
        "lead_ids": lead_ids,
        "task_ids": task_ids,
    }
