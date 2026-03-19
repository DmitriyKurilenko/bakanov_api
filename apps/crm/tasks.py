from celery import shared_task
from django.core.mail import send_mail

from apps.crm.services.manager_assignment import AmoManagerSyncService, DealAssignmentService


@shared_task
def send_daily_deals_report() -> str:
    send_mail(
        subject="Ежедневный отчет по новым сделкам",
        message="Автоматический отчет по сделкам сформирован. Расширенная аналитика будет добавлена далее.",
        from_email=None,
        recipient_list=[],
        fail_silently=True,
    )
    return "daily report queued"


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 5})
def process_amo_new_deal_webhook(self, lead_id: int) -> dict:
    service = DealAssignmentService()
    return service.handle_single_new_deal(lead_id=int(lead_id))


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def sync_amo_managers(self) -> dict:
    synced = AmoManagerSyncService().sync_active_managers()
    return {"synced": len(synced)}
