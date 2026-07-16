"""
Printable Morning Sanity Check report for the Callahan Command Board.
"""

from __future__ import annotations

import html
from datetime import datetime

from flask import Response

from board_loader import _load_board_state
from nav import render_nav


PRIORITY_COLORS = {
    "P1": "#dc2626",
    "P2": "#d97706",
    "P2A": "#d97706",
    "P2B": "#d97706",
    "P2C": "#d97706",
    "P3": "#2563eb",
    "P4": "#16a34a",
}
PRIORITY_ORDER = {
    "P1": 0,
    "P2": 1,
    "P2A": 1,
    "P2B": 1,
    "P2C": 1,
    "P3": 2,
    "P4": 3,
}


def _escape(value) -> str:
    return html.escape(str(value or ""), quote=True)


def _priority(job: dict) -> str:
    return str(job.get("priority_lane") or job.get("priority") or "P4").upper()


def _technician(job: dict) -> str:
    return str(job.get("technician") or job.get("assigned_technician") or "").strip()


def _is_unassigned(job: dict) -> bool:
    return not _technician(job)


def _dvi_status(job: dict) -> str:
    return str(job.get("dvi_review_status") or "NO_DVI").upper()


def _progress(job: dict) -> str:
    value = job.get("progress_percent")
    if value in (None, ""):
        return "0"
    return str(value)


def _alert_label(alert) -> str:
    if isinstance(alert, dict):
        return str(alert.get("label") or alert.get("message") or alert.get("code") or "").strip()
    return str(alert or "").strip()


def _incoming(job: dict) -> dict:
    value = job.get("incoming_soon")
    return value if isinstance(value, dict) else {}


def _sort_key(job: dict):
    return (
        PRIORITY_ORDER.get(_priority(job), 9),
        0 if _is_unassigned(job) else 1,
        str(job.get("ro") or ""),
    )


def _dvi_label(job: dict) -> str:
    status = _dvi_status(job)
    if status == "REWORK_REQUIRED":
        return '<span class="danger">🔴 DVI REWORK REQUIRED</span>'
    if status == "REVIEW":
        return '<span class="warning">🟡 DVI NEEDS REVIEW</span>'
    if status == "PASS":
        return '<span class="ok">✅ DVI CLEAR</span>'
    return '<span class="muted">⬜ NO DVI ON FILE</span>'


def _tech_section(job: dict) -> str:
    technician = _technician(job)
    candidates = job.get("technician_candidates") or []
    if isinstance(candidates, str):
        candidate_text = candidates
    else:
        candidate_text = ", ".join(str(candidate) for candidate in candidates if candidate)
    assignment = (
        f'<div class="danger strong">⚠ NO TECH ASSIGNED</div>'
        if not technician
        else f'<div class="ok strong">✓ Assigned: {_escape(technician)}</div>'
    )
    return f"""
    <div class="section-line">
        <div class="label">Tech Assignment</div>
        {assignment}
        <div class="muted">Candidates: {_escape(candidate_text or "None listed")}</div>
    </div>
    """


def _alerts_section(job: dict) -> str:
    alerts = [_alert_label(alert) for alert in job.get("alerts", []) if _alert_label(alert)]
    if not alerts:
        return ""
    return '<div class="section-line"><div class="label">Alerts</div><ul class="alerts">' + "".join(
        f"<li>{_escape(alert)}</li>" for alert in alerts
    ) + "</ul></div>"


def _job_block(job: dict) -> str:
    priority = _priority(job)
    color = PRIORITY_COLORS.get(priority, "#64748b")
    incoming = _incoming(job)
    incoming_html = ""
    if incoming.get("active") is True:
        incoming_html = f'<div class="incoming">⚡ INCOMING SOON: {_escape(incoming.get("next_stage", ""))}</div>'

    return f"""
    <article class="job-card" style="border-left-color:{color};">
        <div class="job-title">
            RO {_escape(job.get("ro"))} | {_escape(job.get("customer"))} | {_escape(job.get("vehicle"))} |
            Status: {_escape(job.get("workflow_status"))} |
            Waiting: {_escape(job.get("waiting_on"))} |
            Progress: {_escape(_progress(job))}%
        </div>
        {_tech_section(job)}
        <div class="section-line">
            <div class="label">DVI Status</div>
            {_dvi_label(job)}
        </div>
        {_alerts_section(job)}
        <div class="section-line">
            <div class="label">Next Action</div>
            <em>{_escape(job.get("next_action"))}</em>
        </div>
        {incoming_html}
    </article>
    """


def _flag_summary(jobs: list[dict]) -> str:
    flags = []
    for job in jobs:
        ro = _escape(job.get("ro"))
        customer = _escape(job.get("customer"))
        if _is_unassigned(job):
            flags.append(f"<li>RO {ro} — {customer} — NO TECH ASSIGNED</li>")
        if _priority(job) == "P1":
            flags.append(f"<li>RO {ro} — {customer} — P1 PRIORITY</li>")
        if _dvi_status(job) == "REWORK_REQUIRED":
            flags.append(f"<li>RO {ro} — {customer} — DVI REWORK REQUIRED</li>")
        incoming = _incoming(job)
        if incoming.get("active") is True:
            flags.append(f"<li>RO {ro} — {customer} — INCOMING SOON: {_escape(incoming.get('next_stage', ''))}</li>")

    if not flags:
        return '<div class="clean">✅ No immediate flags — board looks clean</div>'
    return "<ul>" + "".join(flags) + "</ul>"


def render_sanity_check():
    board_state = _load_board_state()
    jobs = board_state.get("jobs", []) if isinstance(board_state, dict) else []
    jobs = [job for job in jobs if isinstance(job, dict)]
    sorted_jobs = sorted(jobs, key=_sort_key)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    total_jobs = len(jobs)
    p1_count = sum(1 for job in jobs if _priority(job) == "P1")
    unassigned_count = sum(1 for job in jobs if _is_unassigned(job))
    dvi_pending_count = sum(1 for job in jobs if _dvi_status(job) in {"NO_DVI", "PENDING", ""})

    html_text = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Morning Sanity Check</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{ font-family: Arial, Helvetica, sans-serif; background: #f1f5f9; color: #111827; margin: 0; padding: 0 24px 24px; }}
        .page {{ max-width: 1120px; margin: 0 auto; background: #fff; padding: 28px; border-radius: 14px; box-shadow: 0 16px 34px rgba(15, 23, 42, 0.14); }}
        .top {{ display: flex; justify-content: space-between; gap: 24px; border-bottom: 3px solid #111827; padding-bottom: 18px; margin-bottom: 20px; }}
        .shop {{ font-size: 26px; font-weight: 900; letter-spacing: 0.08em; }}
        .title {{ margin-top: 4px; font-size: 15px; font-weight: 900; color: #475569; letter-spacing: 0.16em; }}
        .meta {{ text-align: right; color: #475569; font-size: 13px; line-height: 1.7; }}
        .print-button {{ border: 0; border-radius: 8px; background: #1e40af; color: #fff; padding: 8px 14px; font-weight: 800; cursor: pointer; }}
        .summary {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 18px 0; }}
        .summary-card {{ border: 1px solid #cbd5e1; border-radius: 10px; padding: 12px; background: #f8fafc; }}
        .summary-card .label {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: #64748b; }}
        .summary-card .value {{ margin-top: 4px; font-size: 30px; font-weight: 900; }}
        .flags {{ background: #fef3c7; border: 2px solid #f59e0b; border-radius: 12px; padding: 16px; margin: 20px 0; }}
        .flags h2 {{ margin: 0 0 10px; font-size: 15px; letter-spacing: 0.08em; }}
        .flags ul {{ margin: 0; padding-left: 20px; line-height: 1.65; }}
        .clean {{ font-weight: 800; color: #166534; }}
        .job-card {{ border: 1px solid #cbd5e1; border-left: 8px solid #64748b; border-radius: 10px; padding: 14px 16px; margin: 14px 0; page-break-inside: avoid; background: #fff; }}
        .job-title {{ font-weight: 900; font-size: 14px; color: #111827; line-height: 1.5; }}
        .section-line {{ margin-top: 10px; font-size: 13px; line-height: 1.45; }}
        .label {{ font-weight: 900; color: #475569; text-transform: uppercase; letter-spacing: 0.05em; font-size: 11px; margin-bottom: 3px; }}
        .strong {{ font-weight: 900; }}
        .danger {{ color: #dc2626; }}
        .warning {{ color: #b45309; font-weight: 900; }}
        .ok {{ color: #15803d; }}
        .muted {{ color: #64748b; }}
        .alerts {{ margin: 4px 0 0; padding-left: 18px; }}
        .incoming {{ margin-top: 10px; color: #b45309; font-weight: 900; }}
        @media print {{
            @page {{ margin: 0.5in; }}
            body {{ background: #fff; padding: 0; }}
            .page {{ box-shadow: none; border-radius: 0; max-width: none; padding: 0; }}
            .print-button {{ display: none; }}
            .job-card {{ page-break-inside: avoid; }}
            .job-card {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
        }}
    </style>
</head>
<body>
    {render_nav("Sanity Check")}
    <main class="page">
        <header class="top">
            <div>
                <div class="shop">CALLAHAN AUTO & DIESEL</div>
                <div class="title">MORNING SANITY CHECK</div>
            </div>
            <div class="meta">
                <button class="print-button" onclick="window.print()">Print</button>
                <div><strong>Generated:</strong> {_escape(timestamp)}</div>
            </div>
        </header>

        <section class="summary">
            <div class="summary-card"><div class="label">Total Active ROs</div><div class="value">{total_jobs}</div></div>
            <div class="summary-card"><div class="label">P1 Count</div><div class="value">{p1_count}</div></div>
            <div class="summary-card"><div class="label">Unassigned Jobs</div><div class="value">{unassigned_count}</div></div>
            <div class="summary-card"><div class="label">DVI Pending</div><div class="value">{dvi_pending_count}</div></div>
        </section>

        <section class="flags">
            <h2>⚠ ITEMS NEEDING IMMEDIATE ATTENTION</h2>
            {_flag_summary(sorted_jobs)}
        </section>

        <section>
            {''.join(_job_block(job) for job in sorted_jobs)}
        </section>
    </main>
</body>
</html>"""
    return Response(html_text, mimetype="text/html")
