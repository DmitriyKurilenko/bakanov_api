from __future__ import annotations

import mimetypes
from pathlib import Path

from django.conf import settings
from django.core.mail import EmailMessage, send_mail


def _default_recipient() -> str:
    return str(getattr(settings, "DOCUMENTS_EMAIL_TO", "") or settings.EMAIL_HOST_USER or "").strip()


def send_email_with_attachment(*, subject: str, body: str, attachment_path: str | Path | None = None, recipient: str | None = None) -> bool:
    email_to = str(recipient or _default_recipient() or "").strip()
    if not email_to:
        return False

    message = EmailMessage(
        subject=subject,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email_to],
    )
    if attachment_path:
        path = Path(attachment_path)
        if path.exists():
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            with path.open("rb") as f:
                message.attach(path.name, f.read(), content_type)

    try:
        message.send(fail_silently=True)
        return True
    except Exception:
        return False


def send_contract_email(lead: dict, contract_file_url: str, attachment_path: str | Path | None = None) -> None:
    lead_name = str(lead.get("name", "")).strip()
    send_email_with_attachment(
        subject=f"Договор по сделке {lead_name or lead.get('id', '')}",
        body=f"Договор сформирован.\n\nСделка: {lead_name or '-'}\nСсылка: {contract_file_url}",
        attachment_path=attachment_path,
    )


def send_extra_contract_email(*, lead_id: int, file_url: str, attachment_path: str | Path | None = None) -> None:
    send_email_with_attachment(
        subject=f"Допсоглашение по сделке {lead_id}",
        body=f"Дополнительное соглашение сформировано.\n\nСделка: {lead_id}\nСсылка: {file_url}",
        attachment_path=attachment_path,
    )


def send_form_report_email(*, lead_id: int, form_type: str, language: str, file_url: str, attachment_path: str | Path | None = None) -> None:
    titles = {
        ("menu", "ru"): "Меню (RU)",
        ("menu", "en"): "Menu (EN)",
        ("cruise", "ru"): "Пожелания (RU)",
        ("cruise", "en"): "Cruise preferences (EN)",
    }
    title = titles.get((str(form_type), str(language)), f"{form_type}/{language}")
    send_email_with_attachment(
        subject=f"{title} по сделке {lead_id}",
        body=f"Сформирован документ: {title}\n\nСделка: {lead_id}\nСсылка: {file_url}",
        attachment_path=attachment_path,
    )


def send_analysis_email(subject: str, body: str) -> None:
    recipient = _default_recipient()
    if not recipient:
        return
    send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[recipient],
        fail_silently=True,
    )
