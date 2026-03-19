from __future__ import annotations

from dataclasses import dataclass

import requests
from django.conf import settings


@dataclass
class STTResult:
    transcript: str
    provider: str
    segments: list[dict]
    language: str
    raw: dict


def _segments_to_text(segments: list[dict]) -> str:
    lines: list[str] = []
    for segment in segments:
        role = str(segment.get("role") or "Спикер")
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        lines.append(f"{role}: {text}")
    return "\n".join(lines)


def _deepgram_transcribe(file_bytes: bytes, mime_type: str) -> STTResult:
    url = "https://api.deepgram.com/v1/listen?model=nova-2&language=ru&smart_format=true&punctuate=true&diarize=true&utterances=true"
    resp = requests.post(
        url,
        data=file_bytes,
        headers={
            "Authorization": f"Token {settings.DEEPGRAM_API_KEY}",
            "Content-Type": mime_type or "application/octet-stream",
        },
        timeout=120,
    )
    resp.raise_for_status()
    payload = resp.json()

    results = payload.get("results") or {}
    utterances = results.get("utterances") or []
    segments: list[dict] = []
    for item in utterances:
        speaker = item.get("speaker")
        segments.append(
            {
                "role": f"Спикер {speaker}" if speaker is not None else "Спикер",
                "speaker": speaker,
                "start": item.get("start"),
                "end": item.get("end"),
                "text": item.get("transcript", ""),
            }
        )

    transcript = _segments_to_text(segments)
    if not transcript:
        channels = ((results.get("channels") or [{}])[0]).get("alternatives") or [{}]
        transcript = str((channels[0] or {}).get("transcript") or "")
        if transcript:
            segments = [{"role": "Спикер 1", "speaker": 1, "start": None, "end": None, "text": transcript}]

    return STTResult(
        transcript=transcript.strip(),
        provider="deepgram",
        segments=segments,
        language="ru",
        raw=payload if isinstance(payload, dict) else {},
    )


def _yandex_speechkit_transcribe(file_bytes: bytes, mime_type: str) -> STTResult:
    if not settings.YANDEX_API_KEY:
        raise RuntimeError("YANDEX_API_KEY is not configured")
    # Minimal SpeechKit call (sync recognize); diarization is not guaranteed here.
    mime = (mime_type or "").lower()
    params = {"lang": "ru-RU"}
    if "mpeg" in mime or "mp3" in mime:
        params["format"] = "mp3"
    elif "ogg" in mime or "opus" in mime:
        params["format"] = "oggopus"
    else:
        # Fallback for wav/unknown. SpeechKit may require exact sample rate for lpcm.
        params["format"] = "lpcm"
        params["sampleRateHertz"] = 8000

    resp = requests.post(
        "https://stt.api.cloud.yandex.net/speech/v1/stt:recognize",
        params=params,
        data=file_bytes,
        headers={"Authorization": f"Api-Key {settings.YANDEX_API_KEY}"},
        timeout=120,
    )
    resp.raise_for_status()
    payload = resp.json()
    text = str(payload.get("result") or "").strip()
    segments = [{"role": "Спикер 1", "speaker": 1, "start": None, "end": None, "text": text}] if text else []
    return STTResult(
        transcript=text,
        provider="yandex_speechkit",
        segments=segments,
        language="ru",
        raw=payload if isinstance(payload, dict) else {},
    )


def transcribe_audio(file_bytes: bytes, *, mime_type: str = "application/octet-stream") -> STTResult:
    provider_pref = str(getattr(settings, "STT_PROVIDER", "deepgram") or "deepgram").lower()
    errors: list[str] = []

    providers = [provider_pref]
    if provider_pref != "deepgram":
        providers.append("deepgram")
    if provider_pref != "yandex":
        providers.append("yandex")

    for provider in providers:
        try:
            if provider == "deepgram":
                if not settings.DEEPGRAM_API_KEY:
                    raise RuntimeError("DEEPGRAM_API_KEY is not configured")
                return _deepgram_transcribe(file_bytes, mime_type)
            if provider == "yandex":
                return _yandex_speechkit_transcribe(file_bytes, mime_type)
        except Exception as exc:
            errors.append(f"{provider}: {exc}")

    fallback_text = "STT unavailable: " + "; ".join(errors) if errors else "STT unavailable"
    return STTResult(
        transcript=fallback_text,
        provider="fallback",
        segments=[{"role": "Система", "speaker": None, "start": None, "end": None, "text": fallback_text}],
        language="ru",
        raw={"errors": errors},
    )
