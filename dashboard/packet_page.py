"""
Print-ready TekMetric packet page.
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Response, request

from core.cas.tekmetric_packet import generate_packet


REPO_ROOT = Path(__file__).resolve().parents[1]
DVI_REVIEWS_DIR = REPO_ROOT / "state" / "dvi_reviews"
PACKET_MAX_AGE = timedelta(hours=4)


def _escape(value) -> str:
    return html.escape(str(value or ""), quote=True)


def _packet_path(ro: str) -> Path:
    return DVI_REVIEWS_DIR / f"packet_{ro}.json"


def _is_fresh(path: Path) -> bool:
    if not path.exists():
        return False
    modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return datetime.now(timezone.utc) - modified < PACKET_MAX_AGE


def _load_packet(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _header_class(category: str) -> str:
    category = str(category or "").upper()
    if category == "SAFETY":
        return "safety"
    if category == "MAINTENANCE":
        return "maintenance"
    if category == "POSSIBLE ADD-ON":
        return "addon"
    return "concern"


def _render_labor_items(items) -> str:
    lines = []
    for item in items or []:
        text = _escape(item)
        cls = " reminder" if "⚠" in str(item) or "don't forget" in str(item).lower() else ""
        lines.append(f'<li class="{cls}"><span class="box">□</span>{text}</li>')
    return "\n".join(lines) or '<li><span class="box">□</span>No labor lookup items generated.</li>'


def _render_parts_items(items) -> str:
    lines = []
    for item in items or []:
        lines.append(f'<li><span class="box">□</span>{_escape(item)}</li>')
    return "\n".join(lines) or '<li><span class="box">□</span>No parts lookup items generated.</li>'


def _render_job(job: dict) -> str:
    category = str(job.get("category", "CONCERN")).upper()
    title = _escape(job.get("title", "Untitled job"))
    header_class = _header_class(category)
    addon_banner = ""
    addon_toggle = ""
    if header_class == "addon" or job.get("is_possible_addon"):
        addon_banner = '<div class="addon-banner">⚠ NOT PRESENTED TO CUSTOMER — ADVISOR RADAR ONLY</div>'
        addon_toggle = '<div class="toggle-row">[ ] Include in estimate&nbsp;&nbsp;&nbsp;[✓] Advisor talking point only</div>'

    conditional = str(job.get("note_conditional") or "").strip()
    conditional_html = ""
    if conditional:
        conditional_html = f'<hr><p class="conditional"><em>{_escape(conditional)}</em></p>'

    return f"""
    <section class="job-block">
        <div class="job-header {header_class}">{title}</div>
        {addon_banner}
        <div class="job-body">
            {addon_toggle}
            <div class="lookup">
                <div class="label">LOOK UP LABOR</div>
                <ul>{_render_labor_items(job.get("labor_items", []))}</ul>
            </div>
            <div class="lookup">
                <div class="label">LOOK UP PARTS</div>
                <ul>{_render_parts_items(job.get("parts_items", []))}</ul>
            </div>
            <div class="copy-note">
                <div class="copy-label">📋 COPY → NOTE</div>
                <p>{_escape(job.get("note_justification", ""))}</p>
                {conditional_html}
            </div>
        </div>
    </section>
    """


def _render_error(ro: str, packet: dict) -> Response:
    message = _escape(packet.get("error", "Packet error"))
    detail = _escape(packet.get("detail", ""))
    html_text = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Packet Error — RO {_escape(ro)}</title></head>
<body style="font-family:Arial,sans-serif;background:#f8fafc;color:#111827;padding:40px;">
    <h1>TekMetric Packet Error</h1>
    <p><strong>RO:</strong> {_escape(ro)}</p>
    <p>{message}</p>
    <pre style="background:#fee2e2;border:1px solid #fecaca;padding:16px;border-radius:8px;white-space:pre-wrap;">{detail}</pre>
</body>
</html>"""
    return Response(html_text, mimetype="text/html")


def render_packet_page(ro):
    ro = str(ro).strip()
    path = _packet_path(ro)
    force_refresh = request.args.get("refresh") == "1"

    if not force_refresh and _is_fresh(path):
        try:
            packet = _load_packet(path)
        except Exception as error:
            packet = {"error": "Packet generation failed", "detail": str(error)}
        else:
            from core.cas.tekmetric_packet import log_packet_cache_hit
            log_packet_cache_hit(ro)
    else:
        packet = generate_packet(ro)

    if packet.get("error"):
        return _render_error(ro, packet)

    drag_items = "\n".join(f"<li>{_escape(item)}</li>" for item in packet.get("drag_order", []))
    jobs_html = "\n".join(_render_job(job) for job in packet.get("jobs", []))
    generated_at = _escape(packet.get("generated_at", datetime.now(timezone.utc).isoformat()))

    html_text = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TekMetric Packet — RO {_escape(ro)}</title>
    <style>
        * {{box-sizing:border-box;}}
        body {{font-family:Arial,Helvetica,sans-serif;background:#e5e7eb;color:#111827;margin:0;padding:24px;}}
        .page {{max-width:1020px;margin:0 auto;background:#fff;padding:28px;border-radius:12px;box-shadow:0 12px 30px rgba(15,23,42,0.16);}}
        .header {{display:flex;justify-content:space-between;gap:24px;border-bottom:3px solid #111827;padding-bottom:18px;margin-bottom:22px;}}
        .shop {{font-size:26px;font-weight:900;letter-spacing:0.08em;}}
        .label-top {{font-size:14px;font-weight:800;color:#475569;letter-spacing:0.16em;margin-top:4px;}}
        .meta {{font-size:13px;line-height:1.7;color:#334155;}}
        .actions {{display:flex;gap:8px;justify-content:flex-end;margin-bottom:12px;}}
        .btn {{border:0;border-radius:8px;padding:8px 12px;font-weight:800;color:#fff;background:#1e40af;text-decoration:none;cursor:pointer;font-size:13px;}}
        .btn.secondary {{background:#334155;}}
        .section-box {{background:#f3f4f6;border:1px solid #d1d5db;border-radius:10px;padding:18px;margin:20px 0;}}
        h2 {{font-size:16px;letter-spacing:0.08em;margin:0 0 12px;text-transform:uppercase;}}
        .drag-order ol {{margin:0;padding-left:24px;font-size:15px;line-height:1.8;}}
        .advisor-gate {{background:#fef3c7;border:2px solid #f59e0b;color:#111827;}}
        .advisor-gate h2 {{color:#92400e;}}
        .job-block {{background:#fff;border:1px solid #cbd5e1;border-radius:10px;margin:24px 0;overflow:hidden;page-break-inside:avoid;}}
        .job-header {{padding:12px 16px;color:#fff;font-weight:900;letter-spacing:0.04em;}}
        .job-header.concern {{background:#1e40af;}}
        .job-header.safety {{background:#dc2626;}}
        .job-header.maintenance {{background:#15803d;}}
        .job-header.addon {{background:#7f1d1d;}}
        .addon-banner {{background:#fca5a5;color:#111827;font-weight:900;padding:10px 16px;text-align:center;}}
        .job-body {{padding:18px;}}
        .lookup {{margin-bottom:16px;}}
        .label {{font-size:12px;font-weight:900;color:#64748b;letter-spacing:0.1em;margin-bottom:8px;}}
        ul {{list-style:none;margin:0;padding:0;}}
        li {{padding:5px 0;color:#374151;line-height:1.45;}}
        .box {{font-weight:900;margin-right:8px;color:#111827;}}
        .reminder {{color:#b45309;font-weight:700;}}
        .copy-note {{background:#dbeafe;border:1px solid #93c5fd;border-radius:10px;padding:16px;margin-top:16px;}}
        .copy-label {{font-weight:900;color:#1e3a8a;margin-bottom:8px;letter-spacing:0.05em;}}
        .copy-note p {{margin:0;line-height:1.55;}}
        .copy-note hr {{border:0;border-top:1px solid #93c5fd;margin:12px 0;}}
        .conditional {{font-size:14px;color:#334155;}}
        .toggle-row {{font-weight:900;color:#7f1d1d;margin-bottom:14px;}}
        .footer {{margin-top:28px;border-top:2px solid #111827;padding-top:14px;text-align:center;font-weight:900;color:#334155;}}
        @media print {{
            body {{background:#fff;padding:0;}}
            .page {{box-shadow:none;border-radius:0;max-width:none;padding:0;}}
            .actions {{display:none;}}
            .job-block {{page-break-inside:avoid;}}
            .job-header,.addon-banner {{-webkit-print-color-adjust:exact;print-color-adjust:exact;}}
        }}
    </style>
</head>
<body>
    <main class="page">
        <div class="actions">
            <button class="btn" onclick="window.print()">Print</button>
            <a class="btn secondary" href="/dvi/packet/{_escape(ro)}?refresh=1">Regenerate Packet</a>
        </div>
        <header class="header">
            <div>
                <div class="shop">CALLAHAN AUTO & DIESEL</div>
                <div class="label-top">TEKMETRIC PACKET</div>
            </div>
            <div class="meta">
                <div><strong>RO:</strong> {_escape(packet.get("ro", ro))}</div>
                <div><strong>Customer:</strong> {_escape(packet.get("customer", ""))}</div>
                <div><strong>Vehicle:</strong> {_escape(packet.get("vehicle", ""))}</div>
                <div><strong>Mileage:</strong> {_escape(packet.get("mileage", ""))}</div>
                <div><strong>Generated:</strong> {generated_at}</div>
            </div>
        </header>

        <section class="section-box drag-order">
            <h2>DRAG ORDER FOR TEKMETRIC</h2>
            <ol>{drag_items}</ol>
        </section>

        <section class="section-box advisor-gate">
            <h2>⚠ ADVISOR MENTAL GATE — READ BEFORE CALLING CUSTOMER</h2>
            <div>{_escape(packet.get("advisor_gate", ""))}</div>
        </section>

        {jobs_html}

        <footer class="footer">END OF PACKET — RO {_escape(ro)}<br>{generated_at}</footer>
    </main>
</body>
</html>"""
    return Response(html_text, mimetype="text/html")
