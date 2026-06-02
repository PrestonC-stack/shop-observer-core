"""
dashboard/dvi_page.py
Callahan Auto & Diesel — DVI Workflow Page

Serves the /dvi page with three sections:
1. Needs Attention — rework required or review needed
2. In Progress — DVIs not yet completed
3. Completed Today — completed DVIs with timestamps and gate results

No business logic here — just reading state and rendering.
"""

import os
import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DVI_REVIEWS_DIR = REPO_ROOT / "state" / "dvi_reviews"
TRANSITIONS_PATH = REPO_ROOT / "data" / "status_transitions" / "transitions.jsonl"
SHOP_STATE_PATH = REPO_ROOT / "state" / "shop_state.json"


def _load_shop_state() -> dict:
    try:
        return json.loads(SHOP_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_all_reviews() -> list:
    reviews = []
    if not DVI_REVIEWS_DIR.exists():
        return reviews
    for f in DVI_REVIEWS_DIR.glob("*.json"):
        if f.name.startswith("rework_slip"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            reviews.append(data)
        except Exception:
            continue
    return reviews


def _time_ago(iso_str: str) -> str:
    if not iso_str:
        return "unknown"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        mins = int(delta.total_seconds() / 60)
        if mins < 60:
            return f"{mins}m ago"
        hours = mins // 60
        if hours < 24:
            return f"{hours}h ago"
        return f"{hours // 24}d ago"
    except Exception:
        return "unknown"


def _is_today(iso_str: str) -> bool:
    if not iso_str:
        return False
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return dt.date() == now.date()
    except Exception:
        return False


def _get_in_progress_dvis(shop_state: dict) -> list:
    """
    Jobs currently in DVI-related statuses with no completed DVI review.
    """
    dvi_statuses = {"testing", "dvi updates", "dvi_updates", "ready for tech", "awaiting tech"}
    completed_ros = set()
    if DVI_REVIEWS_DIR.exists():
        for f in DVI_REVIEWS_DIR.glob("*.json"):
            if not f.name.startswith("rework_slip"):
                completed_ros.add(f.stem)

    in_progress = []
    jobs = shop_state.get("jobs", []) or shop_state.get("active_ros", []) or []
    for job in jobs:
        status = str(job.get("workflow_status", "") or job.get("status", "")).lower()
        ro = str(job.get("invoice", "") or job.get("ro", ""))
        if any(s in status for s in dvi_statuses) and ro not in completed_ros:
            in_progress.append({
                "ro": ro,
                "customer": job.get("customer_name", job.get("customer", "")),
                "vehicle": job.get("vehicle", ""),
                "status": job.get("workflow_status", job.get("status", "")),
                "advisor": job.get("waiting_on", job.get("advisor", "")),
                "tech": job.get("technician", ""),
            })
    return in_progress


def render_dvi_page() -> str:
    reviews = _load_all_reviews()
    shop_state = _load_shop_state()

    needs_attention = [r for r in reviews if r.get("review_status") in ("REWORK_REQUIRED", "REVIEW") and not r.get("advisor_acknowledged")]
    completed_today = [r for r in reviews if _is_today(r.get("dvi_pulled_at", "")) and r.get("review_status") not in ("PENDING", "ERROR")]
    in_progress = _get_in_progress_dvis(shop_state)

    def status_badge(status):
        colors = {
            "REWORK_REQUIRED": ("❌", "#c00", "#fff"),
            "REVIEW": ("⚠", "#e67e00", "#fff"),
            "PASS": ("✓", "#2d7a2d", "#fff"),
            "PENDING": ("…", "#888", "#fff"),
            "ERROR": ("!", "#c00", "#fff"),
        }
        emoji, bg, fg = colors.get(status, ("?", "#888", "#fff"))
        return f'<span style="background:{bg};color:{fg};padding:2px 8px;border-radius:4px;font-size:12px;font-weight:bold;">{emoji} {status}</span>'

    # Build needs attention section
    attention_rows = ""
    for r in sorted(needs_attention, key=lambda x: x.get("dvi_pulled_at", ""), reverse=True):
        flags = r.get("flags", [])
        critical = sum(1 for f in flags if f.get("severity") == "critical")
        slip_link = ""
        slip_path = REPO_ROOT / "state" / "dvi_reviews" / f"rework_slip_{r['ro']}.html"
        if slip_path.exists():
            slip_link = f'<a href="/dvi/slip/{r["ro"]}" target="_blank" style="background:#c00;color:#fff;padding:3px 10px;border-radius:4px;font-size:12px;text-decoration:none;margin-left:8px;">Print Slip</a>'

        attention_rows += f"""
        <tr style="border-bottom:1px solid #333;">
            <td style="padding:10px;font-weight:bold;">RO {r['ro']}</td>
            <td style="padding:10px;">{r.get('customer','')}</td>
            <td style="padding:10px;">{r.get('vehicle','')}</td>
            <td style="padding:10px;">{status_badge(r.get('review_status',''))}</td>
            <td style="padding:10px;color:#ff6b6b;">{critical} critical, {len(flags)-critical} important</td>
            <td style="padding:10px;color:#888;">{_time_ago(r.get('dvi_pulled_at',''))}</td>
            <td style="padding:10px;">{slip_link}
                <a href="/dvi/acknowledge/{r['ro']}" style="background:#444;color:#fff;padding:3px 10px;border-radius:4px;font-size:12px;text-decoration:none;margin-left:4px;">Acknowledge</a>
            </td>
        </tr>"""

    if not attention_rows:
        attention_rows = '<tr><td colspan="7" style="padding:20px;text-align:center;color:#666;">No DVIs require attention right now</td></tr>'

    # Build in progress section
    progress_rows = ""
    for job in in_progress:
        progress_rows += f"""
        <tr style="border-bottom:1px solid #333;">
            <td style="padding:10px;font-weight:bold;">RO {job['ro']}</td>
            <td style="padding:10px;">{job['customer']}</td>
            <td style="padding:10px;">{job['vehicle']}</td>
            <td style="padding:10px;color:#888;">{job['status']}</td>
            <td style="padding:10px;">{job['tech'] or '—'}</td>
            <td style="padding:10px;">{job['advisor'] or '—'}</td>
        </tr>"""

    if not progress_rows:
        progress_rows = '<tr><td colspan="6" style="padding:20px;text-align:center;color:#666;">No DVIs currently in progress</td></tr>'

    # Build completed today section
    completed_rows = ""
    for r in sorted(completed_today, key=lambda x: x.get("dvi_pulled_at", ""), reverse=True):
        flags = r.get("flags", [])
        packet_check = "✓" if r.get("cleared_for_estimate") else "—"
        completed_rows += f"""
        <tr style="border-bottom:1px solid #333;">
            <td style="padding:10px;font-weight:bold;">RO {r['ro']}</td>
            <td style="padding:10px;">{r.get('customer','')}</td>
            <td style="padding:10px;">{r.get('vehicle','')}</td>
            <td style="padding:10px;">{r.get('technician','—')}</td>
            <td style="padding:10px;">{status_badge(r.get('review_status',''))}</td>
            <td style="padding:10px;color:#888;">{len(flags)} flags</td>
            <td style="padding:10px;color:#888;">{_time_ago(r.get('dvi_pulled_at',''))}</td>
            <td style="padding:10px;text-align:center;color:#2d7a2d;font-weight:bold;">{packet_check}</td>
        </tr>"""

    if not completed_rows:
        completed_rows = '<tr><td colspan="8" style="padding:20px;text-align:center;color:#666;">No DVIs completed today yet</td></tr>'

    attention_count = len(needs_attention)
    banner = ""
    if attention_count > 0:
        banner = f"""
        <div style="background:#c00;color:#fff;padding:12px 20px;border-radius:6px;margin-bottom:20px;font-weight:bold;font-size:15px;">
            ❌ {attention_count} DVI{'s' if attention_count > 1 else ''} require{'s' if attention_count == 1 else ''} attention before estimate can be built
        </div>"""

    now = datetime.now(timezone.utc).strftime("%m/%d/%Y %I:%M %p UTC")

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>DVI Workflow — Callahan Auto & Diesel</title>
    <meta http-equiv="refresh" content="60">
    <style>
        body {{font-family:Arial,sans-serif;background:#111;color:#eee;margin:0;padding:0;}}
        .header {{background:#1a1a1a;padding:16px 24px;border-bottom:1px solid #333;display:flex;align-items:center;justify-content:space-between;}}
        .header h1 {{margin:0;font-size:20px;}}
        .nav a {{color:#888;text-decoration:none;margin-left:16px;font-size:14px;}}
        .nav a:hover {{color:#fff;}}
        .content {{padding:24px;}}
        .section {{margin-bottom:32px;}}
        .section-title {{font-size:16px;font-weight:bold;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid #333;}}
        table {{width:100%;border-collapse:collapse;background:#1a1a1a;border-radius:6px;overflow:hidden;}}
        th {{padding:10px;text-align:left;background:#222;color:#888;font-size:12px;text-transform:uppercase;letter-spacing:0.5px;}}
        tr:hover {{background:#222;}}
        .timestamp {{color:#888;font-size:12px;}}
        @media print {{body{{background:#fff;color:#000;}} .nav{{display:none;}}}}
    </style>
</head>
<body>
    <div class="header">
        <h1>DVI Workflow</h1>
        <div class="nav">
            <a href="/">← Board</a>
            <a href="/drew">Drew</a>
            <a href="/mitch">Mitch</a>
            <a href="/preston">Preston</a>
            <span class="timestamp">Auto-refreshes every 60s &nbsp;|&nbsp; {now}</span>
        </div>
    </div>
    <div class="content">
        {banner}

        <div class="section">
            <div class="section-title">❌ Needs Attention ({len(needs_attention)})</div>
            <table>
                <thead><tr>
                    <th>RO</th><th>Customer</th><th>Vehicle</th><th>Status</th>
                    <th>Flags</th><th>Gate Ran</th><th>Actions</th>
                </tr></thead>
                <tbody>{attention_rows}</tbody>
            </table>
        </div>

        <div class="section">
            <div class="section-title">🔄 DVI In Progress ({len(in_progress)})</div>
            <table>
                <thead><tr>
                    <th>RO</th><th>Customer</th><th>Vehicle</th><th>Status</th>
                    <th>Tech</th><th>Advisor</th>
                </tr></thead>
                <tbody>{progress_rows}</tbody>
            </table>
        </div>

        <div class="section">
            <div class="section-title">✅ Completed Today ({len(completed_today)})</div>
            <table>
                <thead><tr>
                    <th>RO</th><th>Customer</th><th>Vehicle</th><th>Tech</th>
                    <th>Gate Result</th><th>Flags</th><th>Completed</th><th>TekMetric Ready</th>
                </tr></thead>
                <tbody>{completed_rows}</tbody>
            </table>
        </div>
    </div>
</body>
</html>"""
