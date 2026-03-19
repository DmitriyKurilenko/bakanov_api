import requests
from celery import shared_task

from apps.integrations.services.amocrm_spam_lead_service import AmoCrmSpamLeadSyncService
from apps.integrations.services.telegram_service import send_telegram_message


@shared_task
def publish_evening_telegram_post() -> str:
    send_telegram_message("Вечерний пост по шаблону: шаблон будет добавлен позже.")
    return "telegram post sent"


@shared_task(
    autoretry_for=(requests.RequestException,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 5},
)
def process_amocrm_spam_lead_webhook(lead_id: int) -> dict:
    result = AmoCrmSpamLeadSyncService.from_settings().sync_lead(lead_id=int(lead_id))
    return {
        "lead_id": result.lead_id,
        "status": result.status,
        "detail": result.detail,
        "uploaded_client_ids": result.uploaded_client_ids,
        "uploading": result.uploading or {},
        "sources": result.sources or [],
    }
