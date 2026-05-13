import logging

import requests
from celery import shared_task

from apps.integrations.services.amocrm_spam_lead_service import AmoCrmSpamLeadSyncService
from apps.integrations.services.telegram_service import send_telegram_message

logger = logging.getLogger(__name__)


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


# ------------------------------------------------------------------
# Bitrix24
# ------------------------------------------------------------------

@shared_task(
    autoretry_for=(requests.RequestException,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 5},
)
def process_bitrix24_webhook(event: str, entity_id: int) -> dict:
    """Async processing of an incoming Bitrix24 CRM event."""
    from apps.integrations.services.bitrix24_webhook_handler import (
        Bitrix24WebhookProcessor,
    )

    processor = Bitrix24WebhookProcessor()
    result = processor.process(event=event, entity_id=entity_id)
    logger.info(
        "Bitrix24 task done: event=%s entity_id=%s status=%s",
        result.event,
        result.entity_id,
        result.status,
    )
    return result.as_dict()


@shared_task(
    autoretry_for=(requests.RequestException,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 5},
)
def process_bitrix24_spam_lead_webhook(entity_id: int, entity_type: str) -> dict:
    """Async processing of Bitrix24 spam lead — upload client_id to Metrica."""
    from apps.integrations.services.bitrix24_spam_lead_service import (
        Bitrix24SpamLeadSyncService,
    )

    result = Bitrix24SpamLeadSyncService.from_settings().sync_entity(
        entity_id=int(entity_id),
        entity_type=str(entity_type),
    )
    logger.info(
        "Bitrix24 spam task done: entity_type=%s entity_id=%s status=%s uploaded=%s",
        result.entity_type,
        result.entity_id,
        result.status,
        result.uploaded_client_ids,
    )
    return {
        "entity_id": result.entity_id,
        "entity_type": result.entity_type,
        "status": result.status,
        "detail": result.detail,
        "uploaded_client_ids": result.uploaded_client_ids,
        "uploading": result.uploading or {},
        "sources": result.sources or [],
    }
