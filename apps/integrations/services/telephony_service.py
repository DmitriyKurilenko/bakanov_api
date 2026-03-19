from __future__ import annotations

from dataclasses import dataclass
import mimetypes
from pathlib import Path
from urllib.parse import urlparse

import requests


@dataclass
class DownloadedCallRecord:
    content: bytes
    content_type: str
    file_name: str


def _guess_name_from_url(url: str) -> str:
    path = urlparse(url).path
    name = Path(path).name or "call_record.bin"
    return name


def download_call_record(url: str) -> bytes:
    return download_call_record_detailed(url).content


def download_call_record_detailed(url: str) -> DownloadedCallRecord:
    parsed = urlparse(url)
    if parsed.scheme == "file":
        local_path = Path(parsed.path)
        if not local_path.exists():
            raise FileNotFoundError(f"Local file not found: {local_path}")
        content = local_path.read_bytes()
        content_type = (mimetypes.guess_type(local_path.name)[0] or "application/octet-stream").split(";")[0].strip()
        file_name = local_path.name or "call_record.bin"
        return DownloadedCallRecord(
            content=content,
            content_type=content_type,
            file_name=file_name,
        )
    if parsed.scheme in ("", None):
        local_path = Path(url)
        if local_path.exists():
            content = local_path.read_bytes()
            content_type = (mimetypes.guess_type(local_path.name)[0] or "application/octet-stream").split(";")[0].strip()
            return DownloadedCallRecord(
                content=content,
                content_type=content_type,
                file_name=local_path.name or "call_record.bin",
            )

    response = requests.get(url, timeout=30)
    response.raise_for_status()

    content_type = str(response.headers.get("Content-Type") or "application/octet-stream").split(";")[0].strip()
    file_name = _guess_name_from_url(url)
    if "." not in file_name:
        if "mpeg" in content_type or "mp3" in content_type:
            file_name = f"{file_name}.mp3"
        elif "wav" in content_type:
            file_name = f"{file_name}.wav"
        elif "ogg" in content_type:
            file_name = f"{file_name}.ogg"
    return DownloadedCallRecord(
        content=response.content,
        content_type=content_type,
        file_name=file_name,
    )
