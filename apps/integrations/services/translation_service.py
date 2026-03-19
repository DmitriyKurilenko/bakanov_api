from __future__ import annotations

from functools import lru_cache

try:
    from deep_translator import GoogleTranslator
except Exception:  # pragma: no cover - dependency may be absent before image rebuild
    GoogleTranslator = None


@lru_cache(maxsize=1)
def _translator():
    if GoogleTranslator is None:
        return None
    return GoogleTranslator(source="ru", target="en")


def translate_ru_to_en(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return ""

    translator = _translator()
    if translator is None:
        return f"[EN translation placeholder] {value[:500]}"

    try:
        translated = translator.translate(text=value)
        return str(translated or value)
    except Exception:
        # External translation can fail due network limits/rate limits; keep report generation working.
        return f"[EN translation fallback] {value[:500]}"
