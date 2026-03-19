from __future__ import annotations

import json
from typing import Any

import requests
from django.conf import settings


YANDEX_GPT_COMPLETION_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"


def _extract_yandex_gpt_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    result = payload.get("result") if isinstance(payload.get("result"), dict) else payload
    alternatives = result.get("alternatives") if isinstance(result, dict) else None
    if isinstance(alternatives, list) and alternatives:
        alt0 = alternatives[0] if isinstance(alternatives[0], dict) else {}
        message = alt0.get("message") if isinstance(alt0.get("message"), dict) else {}
        text = message.get("text")
        if isinstance(text, str):
            return text.strip()
        if isinstance(alt0.get("text"), str):
            return str(alt0.get("text")).strip()
    return str(result.get("text") or "").strip() if isinstance(result, dict) else ""


def _extract_json_object(text: str) -> dict | None:
    if not text:
        return None
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _yandex_gpt_analyze_call_text(transcript: str) -> dict:
    system = (
        "Ты — руководитель отдела продаж (РОП). "
        "Проанализируй текст звонка менеджера с клиентом. "
        "Верни СТРОГО JSON с ключами: analysis (строка), recommendations (строка). "
        "Пиши по-русски, без markdown и без лишних ключей."
    )
    user = (
        "Транскрипт звонка ниже.\n\n"
        f"{transcript[:12000]}\n\n"
        "Сформируй:\n"
        '- analysis: кратко и по делу (качество контакта, выявление потребностей, возражения, следующий шаг).\n'
        "- recommendations: конкретные следующие действия для менеджера.\n"
    )

    resp = requests.post(
        YANDEX_GPT_COMPLETION_URL,
        headers={
            "Authorization": f"Api-Key {settings.YANDEX_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "modelUri": settings.YANDEX_MODEL_URI,
            "completionOptions": {
                "stream": False,
                "temperature": 0.2,
                "maxTokens": 1200,
            },
            "messages": [
                {"role": "system", "text": system},
                {"role": "user", "text": user},
            ],
        },
        timeout=120,
    )
    resp.raise_for_status()
    payload = resp.json()
    text = _extract_yandex_gpt_text(payload)
    parsed = _extract_json_object(text)
    if parsed:
        analysis = str(parsed.get("analysis") or "").strip()
        recommendations = str(parsed.get("recommendations") or "").strip()
        if analysis or recommendations:
            return {
                "provider": "yandexgpt",
                "analysis": analysis or text,
                "recommendations": recommendations or "",
                "raw": payload if isinstance(payload, dict) else {"raw": payload},
            }
    return {
        "provider": "yandexgpt",
        "analysis": text or f"Анализ звонка (YandexGPT): {transcript[:500]}",
        "recommendations": "",
        "raw": payload if isinstance(payload, dict) else {"raw": payload},
    }


def analyze_call_text(transcript: str) -> dict:
    if not settings.YANDEX_API_KEY or not settings.YANDEX_MODEL_URI:
        return {
            "provider": "fallback",
            "analysis": f"Анализ разговора (роль: РОП):\n{transcript[:1000]}",
            "recommendations": "Рекомендации РОП: уточнить бюджет, сроки, ЛПР и зафиксировать следующий шаг.",
        }

    try:
        return _yandex_gpt_analyze_call_text(transcript)
    except Exception as exc:
        return {
            "provider": "fallback",
            "analysis": f"AI unavailable: {exc}\n\n{transcript[:1000]}",
            "recommendations": "Проверьте YANDEX_API_KEY / YANDEX_MODEL_URI и доступ в интернет.",
        }
