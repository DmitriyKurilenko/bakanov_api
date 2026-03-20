#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv(*_args: Any, **_kwargs: Any) -> bool:
        return False

try:
    import requests
except ModuleNotFoundError:
    requests = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Yandex Metrica segment/offline conversions utility")
    parser.add_argument(
        "--mode",
        default="segment",
        choices=["segment", "offline-conversations-upload", "offline-conversions-upload"],
        help="Action mode: segment (default) or offline-conversions-upload",
    )
    parser.add_argument("--name", default="", help="Segment name shown in Metrica UI")
    parser.add_argument(
        "--expression",
        default="",
        help="Metrica segment expression (optional if yandex IDs are provided)",
    )
    parser.add_argument(
        "--yandex-id",
        action="append",
        default=[],
        help="ClientID/Yandex ID value (can be used multiple times)",
    )
    parser.add_argument(
        "--yandex-ids-file",
        default="",
        help="Path to text file with one yandex_id per line",
    )
    parser.add_argument(
        "--yandex-id-dimension",
        default="ym:s:clientID",
        help="Dimension used for yandex IDs (default: ym:s:clientID)",
    )
    parser.add_argument(
        "--new-goal-id",
        default="",
        help="Deprecated alias for --goal-id",
    )
    parser.add_argument(
        "--goal-id",
        default="",
        help="Goal ID for offline conversions (example: spam_lead)",
    )
    parser.add_argument(
        "--conversion-datetime",
        type=int,
        default=0,
        help="Unix timestamp for conversions (default: now)",
    )
    parser.add_argument(
        "--upload-type",
        default="BASIC",
        choices=["BASIC", "CALLS", "CHATS"],
        help="offline_conversions upload type",
    )
    parser.add_argument(
        "--upload-comment",
        default="",
        help="Optional upload comment (query param comment)",
    )
    parser.add_argument(
        "--counter-id",
        type=int,
        default=0,
        help="Metrica counter ID (fallback: YANDEX_METRIKA_COUNTER_ID)",
    )
    parser.add_argument(
        "--token",
        default="",
        help="OAuth token (fallback: YANDEX_METRIKA_TOKEN)",
    )
    parser.add_argument(
        "--segment-source",
        default="api",
        help="Segment source field (default: api)",
    )
    parser.add_argument(
        "--interface-value",
        default="",
        help="Optional human-readable segment definition for UI",
    )
    parser.add_argument(
        "--base-url",
        default="https://api-metrika.yandex.net",
        help="Metrica API base URL",
    )
    parser.add_argument("--timeout", type=float, default=20.0, help="HTTP timeout in seconds")
    parser.add_argument("--dry-run", action="store_true", help="Print request and exit without API call")
    return parser.parse_args()


def _load_env_fallback(env_path: Path) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _resolve_settings(args: argparse.Namespace, root_dir: Path) -> tuple[int, str]:
    env_path = root_dir / ".env"
    load_dotenv(env_path)
    _load_env_fallback(env_path)

    counter_id = args.counter_id or int(os.getenv("YANDEX_METRIKA_COUNTER_ID", "0") or 0)
    token = (args.token or os.getenv("YANDEX_METRIKA_TOKEN", "")).strip()
    return counter_id, token


def _resolve_goal_ids(args: argparse.Namespace) -> tuple[str, str]:
    goal_id = (args.goal_id or args.new_goal_id or os.getenv("YANDEX_METRIKA_OFFLINE_GOAL_ID", "")).strip()
    new_goal_id = (args.new_goal_id or "").strip()
    return goal_id, new_goal_id


def _parse_ids_file(file_path: Path) -> list[str]:
    if not file_path.exists():
        raise ValueError(f"yandex IDs file does not exist: {file_path}")
    ids: list[str] = []
    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        for token in line.replace(",", " ").split():
            value = token.strip()
            if value:
                ids.append(value)
    return ids


def _normalize_yandex_ids(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw).strip()
        if not value:
            continue
        # ClientId values must be numeric; do not mutate mixed values.
        if not value.isdigit():
            continue
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def _build_ids_expression(dimension: str, yandex_ids: list[str]) -> str:
    if not yandex_ids:
        return ""
    clauses = [f"{dimension}=='{item}'" for item in yandex_ids]
    if len(clauses) == 1:
        return clauses[0]
    return "(" + " OR ".join(clauses) + ")"


def _collect_yandex_ids(args: argparse.Namespace) -> list[str]:
    raw_ids: list[str] = list(args.yandex_id or [])
    if args.yandex_ids_file.strip():
        raw_ids.extend(_parse_ids_file(Path(args.yandex_ids_file).expanduser().resolve()))
    return _normalize_yandex_ids(raw_ids)


def _resolve_expression(args: argparse.Namespace, yandex_ids: list[str]) -> str:
    expression = (args.expression or "").strip()
    ids_expression = _build_ids_expression(args.yandex_id_dimension.strip(), yandex_ids)
    if expression and ids_expression:
        return f"({expression}) AND {ids_expression}"
    if ids_expression:
        return ids_expression
    return expression


def _build_payload(args: argparse.Namespace) -> dict:
    payload = {
        "segment": {
            "name": args.name,
            "expression": args.expression,
            "segment_source": args.segment_source,
        }
    }
    if args.interface_value.strip():
        payload["segment"]["interface_value"] = args.interface_value.strip()
    return payload


def _normalize_mode(mode: str) -> str:
    if mode == "offline-conversations-upload":
        return "offline-conversions-upload"
    return mode


def _build_offline_conversions_csv(
    *,
    yandex_ids: list[str],
    goal_id: str,
    conversion_datetime: int,
) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["ClientId", "Target", "DateTime"])
    for yandex_id in yandex_ids:
        writer.writerow([yandex_id, goal_id, str(conversion_datetime)])
    return buffer.getvalue()


def _validate_expression(expression: str) -> str | None:
    expr = expression.strip()
    if not expr:
        return "expression must not be empty"

    operators = ("==", "!=", ">=", "<=", ">", "<", "=@", "!@", "=*", "!*", "=~", "!~")
    if not any(op in expr for op in operators):
        return (
            "expression must follow Metrica filters syntax, for example: "
            "ym:s:regionCountry=='Russia'"
        )

    if "ym:" not in expr:
        return (
            "expression usually contains a Metrica dimension/metric id, for example: "
            "ym:s:regionCountry=='Russia'"
        )
    return None


def _post_segment(
    *,
    base_url: str,
    counter_id: int,
    token: str,
    payload: dict,
    timeout: float,
) -> Any:
    if requests is None:
        raise RuntimeError("missing dependency: requests")

    headers = {
        "Authorization": f"OAuth {token}",
        "Content-Type": "application/json",
    }

    endpoints = [
        f"{base_url.rstrip('/')}/management/v1/counter/{counter_id}/apisegment/segments",
        f"{base_url.rstrip('/')}/management/v1/counter/{counter_id}/segments",
    ]
    last_response = None
    for index, url in enumerate(endpoints):
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if response.status_code != 404 or index == len(endpoints) - 1:
            return response
        last_response = response

    if last_response is None:
        raise RuntimeError("Failed to call Metrica API: no response")
    return last_response


def _post_offline_conversions(
    *,
    base_url: str,
    counter_id: int,
    token: str,
    csv_payload: str,
    upload_type: str,
    upload_comment: str,
    timeout: float,
) -> Any:
    if requests is None:
        raise RuntimeError("missing dependency: requests")

    headers = {
        "Authorization": f"OAuth {token}",
    }
    params: dict[str, str] = {"type": upload_type}
    if upload_comment.strip():
        params["comment"] = upload_comment.strip()
    url = f"{base_url.rstrip('/')}/management/v1/counter/{counter_id}/offline_conversions/upload"
    files = {"file": ("offline_conversions.csv", csv_payload.encode("utf-8"), "text/csv")}
    return requests.post(url, headers=headers, params=params, files=files, timeout=timeout)


def main() -> int:
    args = parse_args()
    root_dir = Path(__file__).resolve().parent.parent

    counter_id, token = _resolve_settings(args, root_dir)
    if counter_id <= 0:
        print("ERROR: counter ID is required (--counter-id or YANDEX_METRIKA_COUNTER_ID)")
        return 2

    try:
        yandex_ids = _collect_yandex_ids(args)
    except ValueError as exc:
        print("ERROR:", exc)
        return 9

    response_mode = _normalize_mode(args.mode)
    payload: dict[str, Any] = {}
    csv_payload = ""

    if response_mode == "segment":
        if not args.name.strip():
            print("ERROR: --name is required in segment mode")
            return 10

        resolved_expression = _resolve_expression(args, yandex_ids)
        validation_error = _validate_expression(resolved_expression)
        if validation_error:
            print(f"ERROR: {validation_error}")
            return 8

        args.expression = resolved_expression
        payload = _build_payload(args)
    else:
        if not yandex_ids:
            print("ERROR: at least one yandex_id is required for offline-conversions-upload mode")
            return 11

        goal_id, new_goal_id = _resolve_goal_ids(args)
        if not goal_id and not new_goal_id:
            print(
                "ERROR: goal ID is required "
                "(--goal-id / YANDEX_METRIKA_OFFLINE_GOAL_ID or --new-goal-id)"
            )
            return 12

        conversion_datetime = args.conversion_datetime or int(time.time())
        if conversion_datetime <= 0:
            print("ERROR: conversion datetime must be positive unix timestamp")
            return 13

        csv_payload = _build_offline_conversions_csv(
            yandex_ids=yandex_ids,
            goal_id=goal_id,
            conversion_datetime=conversion_datetime,
        )

    if args.dry_run:
        print("DRY RUN")
        print("mode:", response_mode)
        print("base_url:", args.base_url)
        print("counter_id:", counter_id)
        if yandex_ids:
            print("yandex_ids_count:", len(yandex_ids))
        if response_mode == "segment":
            print("payload:")
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("upload_type:", args.upload_type)
            if args.upload_comment.strip():
                print("upload_comment:", args.upload_comment.strip())
            print("csv_preview:")
            print("\n".join(csv_payload.splitlines()[:6]))
        return 0

    if not token:
        print("ERROR: OAuth token is required (--token or YANDEX_METRIKA_TOKEN)")
        return 3

    try:
        if response_mode == "segment":
            response = _post_segment(
                base_url=args.base_url,
                counter_id=counter_id,
                token=token,
                payload=payload,
                timeout=args.timeout,
            )
        else:
            response = _post_offline_conversions(
                base_url=args.base_url,
                counter_id=counter_id,
                token=token,
                csv_payload=csv_payload,
                upload_type=args.upload_type,
                upload_comment=args.upload_comment,
                timeout=args.timeout,
            )
    except RuntimeError as exc:
        print("ERROR:", exc)
        return 7
    except Exception as exc:
        print("ERROR: request failed:", exc)
        return 4

    body_text = response.text.strip()
    try:
        body = response.json()
    except ValueError:
        body = {}

    if response.status_code >= 400:
        print(f"ERROR: API returned {response.status_code}")
        if body:
            print(json.dumps(body, ensure_ascii=False, indent=2))
        elif body_text:
            print(body_text)
        if isinstance(body, dict):
            errors = body.get("errors")
            if isinstance(errors, list):
                has_4001 = any(
                    isinstance(item, dict) and "4001" in str(item.get("message") or "")
                    for item in errors
                )
                if has_4001:
                    print("HINT: expression must match Reporting API filters syntax.")
                    print("HINT: example -> ym:s:regionCountry=='Russia'")
        return 5

    if response_mode == "segment":
        segment = body.get("segment") if isinstance(body, dict) else None
        if not isinstance(segment, dict):
            print("ERROR: unexpected response payload")
            if body:
                print(json.dumps(body, ensure_ascii=False, indent=2))
            elif body_text:
                print(body_text)
            return 6

        print("OK: segment created")
        print("id:", segment.get("id"))
        print("name:", segment.get("name"))
        print("expression:", segment.get("expression"))
        print("segment_source:", segment.get("segment_source"))
    else:
        print("OK: offline conversions upload accepted")
        if body:
            print(json.dumps(body, ensure_ascii=False, indent=2))
        elif body_text:
            print(body_text)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted")
        sys.exit(130)
