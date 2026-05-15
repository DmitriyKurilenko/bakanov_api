import logging

import requests
from celery import shared_task

from apps.integrations.services.amocrm_spam_lead_service import AmoCrmSpamLeadSyncService
from apps.integrations.services.redis_client import get_redis_client
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
    """Async processing of an incoming Bitrix24 CRM event.

    When a lead moves into the СПАМ stage we *dispatch* a separate,
    independently-retried and de-duplicated task to push the client_id to
    Yandex.Metrica.  The spam upload is intentionally decoupled from generic
    webhook processing: a Metrica/network failure must neither abort the
    generic handling nor be silently swallowed.
    """
    from django.conf import settings
    from apps.integrations.services.bitrix24_webhook_handler import (
        Bitrix24WebhookProcessor,
    )

    processor = Bitrix24WebhookProcessor()
    # A transient Bitrix fetch error now propagates here as RequestException
    # and triggers Celery autoretry instead of yielding empty entity_data
    # (which previously made the spam branch silently no-op).
    result = processor.process(event=event, entity_id=entity_id)

    spam_status = getattr(settings, "BITRIX24_SPAM_STATUS_ID", "IN_PROCESS")
    if (
        event == "ONCRMLEADUPDATE"
        and result.entity_data.get("STATUS_ID") == spam_status
    ):
        spam_task = process_bitrix24_spam_lead_webhook.delay(
            entity_id=int(entity_id),
            entity_type="lead",
        )
        logger.info(
            "Bitrix24 spam auto-dispatch: lead_id=%s status=%s task_id=%s",
            entity_id,
            spam_status,
            spam_task.id,
        )

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
    """Async processing of a Bitrix24 spam lead — upload client_id to Metrica.

    Reliability contract:
    * **Dedup** — a per-entity Redis lock absorbs Bitrix' repeated
      ONCRMLEADUPDATE bursts while a lead sits in the СПАМ stage.  The lock
      is *released* on any failure so a Celery retry or a later redelivery
      can run; it is *kept* (and refreshed) only after a successful upload.
    * **Retry** — transient Bitrix/Metrica errors raise
      ``requests.RequestException`` and are retried by Celery.
    * **Loud failure** — a definitive failure (no client_id, misconfigured
      Metrica token, unexpected error) is logged at ERROR and reported to
      Telegram, never silently swallowed.
    """
    from django.conf import settings

    from apps.integrations.services.bitrix24_spam_lead_service import (
        Bitrix24SpamLeadSyncService,
    )

    cache_key = f"bitrix24:spam:processed:{entity_type}:{entity_id}"
    ttl = int(getattr(settings, "BITRIX24_SPAM_DEDUP_TTL", 3600))
    redis = get_redis_client()
    if not redis.set(cache_key, "1", nx=True, ex=ttl):
        logger.info(
            "Bitrix24 spam webhook duplicate skipped: entity_type=%s entity_id=%s",
            entity_type,
            entity_id,
        )
        return {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "status": "skipped",
            "detail": "Duplicate webhook",
            "uploaded_client_ids": 0,
        }

    try:
        result = Bitrix24SpamLeadSyncService.from_settings().sync_entity(
            entity_id=int(entity_id),
            entity_type=str(entity_type),
        )
    except requests.RequestException:
        # Transient — release the lock so Celery's autoretry can run again.
        redis.delete(cache_key)
        logger.warning(
            "Bitrix24 spam task transient error, will retry: entity_type=%s entity_id=%s",
            entity_type,
            entity_id,
        )
        raise
    except Exception as exc:
        # Definitive non-transport failure (e.g. Metrica token/counter not
        # configured -> ValueError).  Do not retry forever on a config error,
        # but make it impossible to miss.
        redis.delete(cache_key)
        logger.exception(
            "Bitrix24 spam task crashed: entity_type=%s entity_id=%s",
            entity_type,
            entity_id,
        )
        send_telegram_message(
            f"⚠️ Bitrix24 → Метрика: сбой загрузки спам-лида "
            f"{entity_type} #{entity_id}: {exc}"
        )
        return {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "status": "error",
            "detail": str(exc),
            "uploaded_client_ids": 0,
        }

    if result.status != "ok":
        # No client_id on the entity / not found after a successful fetch:
        # release the lock so a corrected redelivery can retry, and alert.
        redis.delete(cache_key)
        logger.error(
            "Bitrix24 spam upload failed: entity_type=%s entity_id=%s detail=%s",
            result.entity_type,
            result.entity_id,
            result.detail,
        )
        send_telegram_message(
            f"⚠️ Bitrix24 → Метрика: лид {result.entity_type} "
            f"#{result.entity_id} не загружен ({result.detail})"
        )
    else:
        # Success — keep the dedup lock and refresh its TTL.
        redis.set(cache_key, "1", ex=ttl)
        logger.info(
            "Bitrix24 spam task done: entity_type=%s entity_id=%s "
            "status=%s uploaded=%s sources=%s",
            result.entity_type,
            result.entity_id,
            result.status,
            result.uploaded_client_ids,
            result.sources,
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
