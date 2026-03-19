from pathlib import Path
import uuid

from django.conf import settings
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def generate_contract_pdf(deal: dict) -> str:
    contracts_dir = Path(settings.MEDIA_ROOT) / "contracts"
    contracts_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"contract_{deal.get('id', 'unknown')}_{uuid.uuid4().hex}.pdf"
    file_path = contracts_dir / file_name

    c = canvas.Canvas(str(file_path), pagesize=A4)
    c.setFont("Helvetica", 12)
    c.drawString(80, 800, "ДОГОВОР")
    c.drawString(80, 770, f"Сделка: {deal.get('name', 'Без названия')}")
    c.drawString(80, 750, f"ID сделки: {deal.get('id', 'N/A')}")
    c.drawString(80, 730, "Текст договора будет расширен в следующих итерациях.")
    c.showPage()
    c.save()

    return f"/media/contracts/{file_name}"


def generate_bilingual_pdf(content_ru: str, content_en: str) -> str:
    forms_dir = Path(settings.MEDIA_ROOT) / "forms"
    forms_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"form_{uuid.uuid4().hex}.pdf"
    file_path = forms_dir / file_name

    c = canvas.Canvas(str(file_path), pagesize=A4)
    c.setFont("Helvetica", 11)
    c.drawString(40, 800, "Русский текст:")
    c.drawString(40, 780, content_ru[:140])
    c.drawString(40, 740, "English text:")
    c.drawString(40, 720, content_en[:140])
    c.showPage()
    c.save()

    return f"/media/forms/{file_name}"
