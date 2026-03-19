from __future__ import annotations

from dataclasses import dataclass

from django.core.files.base import ContentFile

from apps.crm.models import CallAnalysis, DealSnapshot
from apps.integrations.services.ai_service import analyze_call_text
from apps.integrations.services.email_service import send_analysis_email
from apps.integrations.services.stt_service import transcribe_audio
from apps.integrations.services.telephony_service import download_call_record_detailed


def extract_telephony_payload(request) -> dict:
    import json

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


def pick_first(data: dict, *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            value = value[0] if value else ""
        if value not in (None, ""):
            return str(value).strip()
    return ""


def pick_int(data: dict, *keys: str) -> int | None:
    raw = pick_first(data, *keys)
    if not raw:
        return None
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


@dataclass
class TelephonyWebhookResult:
    status: str
    provider: str
    call_analysis_id: int | None = None
    call_id: str | None = None
    deal_id: int | None = None
    stt_provider: str | None = None
    audio_file: str | None = None
    detail: str | None = None

    def as_dict(self) -> dict:
        data = {
            "status": self.status,
            "provider": self.provider,
        }
        if self.call_analysis_id is not None:
            data["call_analysis_id"] = self.call_analysis_id
        if self.call_id:
            data["call_id"] = self.call_id
        if self.deal_id is not None:
            data["deal_id"] = self.deal_id
        if self.stt_provider:
            data["stt_provider"] = self.stt_provider
        if self.audio_file is not None:
            data["audio_file"] = self.audio_file
        if self.detail:
            data["detail"] = self.detail
        return data


class TelephonyWebhookProcessor:
    def process(self, *, provider: str, raw_data: dict) -> TelephonyWebhookResult:
        call_id = pick_first(raw_data, "call_id", "pbx_call_id", "id", "uniqueid")
        record_url = pick_first(raw_data, "record_url", "record_link", "link", "record")
        deal_id = pick_int(raw_data, "deal_id", "crm_deal_id", "lead_id", "amocrm_deal_id")
        if not call_id or not record_url:
            return TelephonyWebhookResult(
                status="error",
                provider=provider,
                detail="call_id and record_url/record_link are required",
            )

        deal = None
        if deal_id:
            deal, _ = DealSnapshot.objects.get_or_create(
                amo_deal_id=deal_id,
                defaults={"name": f"Deal {deal_id}"},
            )

        call = CallAnalysis.objects.create(
            deal=deal if deal else DealSnapshot.objects.first(),
            call_id=call_id,
            audio_source_url=record_url,
            raw_payload=raw_data or {},
        )

        try:
            downloaded = download_call_record_detailed(record_url)
            call.audio_file.save(downloaded.file_name, ContentFile(downloaded.content), save=False)

            stt_result = transcribe_audio(downloaded.content, mime_type=downloaded.content_type)
            ai_result = analyze_call_text(stt_result.transcript)

            call.stt_provider = stt_result.provider
            call.transcript_segments = stt_result.segments
            call.transcript = stt_result.transcript
            call.ai_provider = str(ai_result.get("provider") or "")
            call.analysis = str(ai_result.get("analysis") or "")
            call.recommendations = str(ai_result.get("recommendations") or "")
            call.processing_error = ""
            call.save()

            send_analysis_email(
                subject=f"Анализ звонка {call_id} ({provider})",
                body=(
                    f"Сделка: {deal_id or '-'}\n"
                    f"Call ID: {call_id}\n"
                    f"STT provider: {call.stt_provider}\n"
                    f"AI provider: {call.ai_provider or '-'}\n\n"
                    f"Текст разговора:\n{call.transcript}\n\n"
                    f"Анализ:\n{call.analysis}\n\n"
                    f"Рекомендации:\n{call.recommendations}"
                ),
            )
        except Exception as exc:
            call.processing_error = str(exc)
            call.save(update_fields=["processing_error", "updated_at"])
            return TelephonyWebhookResult(
                status="error",
                provider=provider,
                call_analysis_id=call.id,
                detail=str(exc),
            )

        return TelephonyWebhookResult(
            status="ok",
            provider=provider,
            call_analysis_id=call.id,
            call_id=call_id,
            deal_id=deal_id,
            stt_provider=call.stt_provider,
            audio_file=call.audio_file.url if call.audio_file else "",
        )
