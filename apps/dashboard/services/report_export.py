from __future__ import annotations

import math
from typing import Any

from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils.html import escape
from django.utils.safestring import mark_safe
from django.utils import timezone
from django.utils.text import slugify


def report_payload_to_table(report_key: str, report_title: str, data: dict[str, Any]) -> dict[str, Any]:
    if isinstance(data.get("manager_rows"), list):
        rows = data["manager_rows"]
        return {
            "title": report_title,
            "columns": ["Менеджер", "Пришло", "Перешло в этап", "Реализовано"],
            "rows": [
                [row.get("manager_name"), row.get("arrived", 0), row.get("moved_to_stage", 0), row.get("realized", 0)]
                for row in rows
            ],
        }

    if isinstance(data.get("stage_rows"), list):
        rows = data["stage_rows"]
        return {
            "title": report_title,
            "columns": ["Этап", "Вошло", "Реализовано", "Конверсия %"],
            "rows": [
                [row.get("stage_name"), row.get("entered", 0), row.get("realized", 0), row.get("conversion_percent", 0)]
                for row in rows
            ],
        }

    flat_rows: list[list[Any]] = []
    for key, value in (data or {}).items():
        if isinstance(value, (dict, list)):
            flat_rows.append([key, str(value)])
        else:
            flat_rows.append([key, value])

    return {
        "title": report_title,
        "columns": ["Поле", "Значение"],
        "rows": flat_rows,
    }


def build_export_filename(report_key: str, extension: str) -> str:
    ts = timezone.now().strftime("%Y%m%d_%H%M%S")
    return f"{slugify(report_key) or 'report'}_{ts}.{extension}"


def _human_export_header(report_key: str, data: dict[str, Any]) -> list[dict[str, str]]:
    filters = data.get("filters") or {}
    date_from = filters.get("date_from")
    date_to = filters.get("date_to")
    period_value = ""
    if date_from and date_to:
        period_value = f"{date_from} — {date_to}"
    elif date_from:
        period_value = str(date_from)
    elif date_to:
        period_value = str(date_to)

    rows: list[dict[str, str]] = []
    if period_value:
        rows.append({"label": "Период", "value": period_value})

    if report_key == "rop_funnel":
        selected_ids = {int(x) for x in (filters.get("manager_ids") or []) if str(x).isdigit()}
        managers = data.get("managers") or []
        if selected_ids:
            names = [m.get("name") for m in managers if int(m.get("id", 0) or 0) in selected_ids]
            names = [str(name) for name in names if name]
            manager_value = ", ".join(names) if names else "Выбранные менеджеры"
        else:
            names = [str(m.get("name")) for m in managers if m.get("name")]
            manager_value = ", ".join(names) if names else "Все активные менеджеры"
        rows.append({"label": "Менеджеры", "value": manager_value})

    return rows


def _palette() -> list[str]:
    return ["#2563EB", "#0EA5A4", "#F59E0B", "#EF4444", "#8B5CF6", "#14B8A6", "#F97316", "#64748B"]


def _pie_chart_svg(*, title: str, labels: list[str], values: list[float]) -> str:
    total = sum(v for v in values if v and v > 0)
    if total <= 0:
        return f"<div><div style='font-weight:600;margin-bottom:6px'>{escape(title)}</div><div>Нет данных для диаграммы</div></div>"

    cx, cy, r = 84, 88, 54
    colors = _palette()
    angle = -math.pi / 2
    paths: list[str] = []
    non_zero = [(labels[i], float(values[i] or 0), colors[i % len(colors)]) for i in range(len(labels)) if (values[i] or 0) > 0]

    for idx, (label, value, color) in enumerate(non_zero):
        frac = value / total
        next_angle = angle + 2 * math.pi * frac
        if len(non_zero) == 1:
            # Full circle should be rendered as circle, arc path collapses visually in many renderers.
            paths.append(f"<circle cx='{cx}' cy='{cy}' r='{r}' fill='{color}' stroke='#fff' stroke-width='1' />")
        else:
            x1, y1 = cx + r * math.cos(angle), cy + r * math.sin(angle)
            x2, y2 = cx + r * math.cos(next_angle), cy + r * math.sin(next_angle)
            large_arc = 1 if (next_angle - angle) > math.pi else 0
            path = (
                f"M {cx} {cy} "
                f"L {x1:.2f} {y1:.2f} "
                f"A {r} {r} 0 {large_arc} 1 {x2:.2f} {y2:.2f} Z"
            )
            paths.append(f"<path d='{path}' fill='{color}' stroke='#fff' stroke-width='1' />")
        angle = next_angle

    svg = (
        f"<div style='font-weight:600;margin-bottom:6px'>{escape(title)}</div>"
        "<svg width='100%' height='190' viewBox='0 0 170 190' xmlns='http://www.w3.org/2000/svg'>"
        "<rect x='0.5' y='0.5' width='169' height='189' fill='white' stroke='#e5e7eb' />"
        + "".join(paths)
        + f"<circle cx='{cx}' cy='{cy}' r='28' fill='white' />"
        + f"<text x='{cx}' y='{cy-2}' text-anchor='middle' font-size='10' fill='#444'>Всего</text>"
        + f"<text x='{cx}' y='{cy+12}' text-anchor='middle' font-size='12' font-weight='700' fill='#111'>{int(total) if float(total).is_integer() else round(total,2)}</text>"
        + "</svg>"
    )
    return svg


def _report_pdf_charts(report_key: str, data: dict[str, Any]) -> list[dict[str, str]]:
    if report_key != "rop_funnel" or not isinstance(data.get("manager_rows"), list):
        return []

    rows = data["manager_rows"]
    labels = [str(r.get("manager_name") or "—") for r in rows]
    arrived = [float(r.get("arrived") or 0) for r in rows]
    moved = [float(r.get("moved_to_stage") or 0) for r in rows]
    realized = [float(r.get("realized") or 0) for r in rows]
    charts: list[dict[str, str]] = [
        {
            "title": "Распределение: Пришло",
            "svg": mark_safe(_pie_chart_svg(title="Распределение: Пришло", labels=labels, values=arrived)),
        },
        {
            "title": "Распределение: Перешло в этап",
            "svg": mark_safe(_pie_chart_svg(title="Распределение: Перешло в этап", labels=labels, values=moved)),
        },
    ]
    if any(v > 0 for v in realized):
        charts.append(
            {
                "title": "Распределение: Реализовано",
                "svg": mark_safe(_pie_chart_svg(title="Распределение: Реализовано", labels=labels, values=realized)),
            }
        )
    return charts


def _charts_grid_rows(charts: list[dict[str, str]]) -> list[list[dict[str, str] | None]]:
    rows: list[list[dict[str, str] | None]] = []
    for i in range(0, len(charts), 2):
        pair: list[dict[str, str] | None] = [charts[i]]
        pair.append(charts[i + 1] if i + 1 < len(charts) else None)
        rows.append(pair)
    return rows


def _report_pdf_shared_legend(report_key: str, data: dict[str, Any]) -> list[dict[str, str]]:
    if report_key != "rop_funnel" or not isinstance(data.get("manager_rows"), list):
        return []
    rows = data["manager_rows"]
    colors = _palette()
    legend: list[dict[str, str]] = []
    for idx, row in enumerate(rows):
        legend.append(
            {
                "name": str(row.get("manager_name") or "—"),
                "color": colors[idx % len(colors)],
            }
        )
    return legend


def render_report_pdf_response(*, report_key: str, report_title: str, filters: dict[str, Any], data: dict[str, Any]) -> HttpResponse:
    from weasyprint import HTML

    table = report_payload_to_table(report_key, report_title, data)
    charts = _report_pdf_charts(report_key, data)
    html = render_to_string(
        "dashboard/report_export_pdf.html",
        {
            "report_title": report_title,
            "generated_at": timezone.localtime(),
            "header_rows": _human_export_header(report_key, data),
            "table": table,
            "charts": charts,
            "chart_grid_rows": _charts_grid_rows(charts),
            "chart_legend": _report_pdf_shared_legend(report_key, data),
        },
    )
    pdf_bytes = HTML(string=html).write_pdf()
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{build_export_filename(report_key, "pdf")}"'
    return response


def render_report_excel_response(*, report_key: str, report_title: str, filters: dict[str, Any], data: dict[str, Any]) -> HttpResponse:
    # Excel-compatible export as HTML table with .xls extension (opens in Excel).
    table = report_payload_to_table(report_key, report_title, data)
    html = render_to_string(
        "dashboard/report_export_excel.html",
        {
            "report_title": report_title,
            "generated_at": timezone.localtime(),
            "filters": filters or {},
            "table": table,
        },
    )
    payload = html.encode("utf-8")
    response = HttpResponse(payload, content_type="application/vnd.ms-excel; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{build_export_filename(report_key, "xls")}"'
    return response
