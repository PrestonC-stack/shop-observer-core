"""
Advisor activity and accountability page.

Server-rendered only. Reads local JSONL telemetry and never calls AutoFlow.
"""

from __future__ import annotations

import html
import json
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    from dashboard.nav import render_nav
except ImportError:  # pragma: no cover
    from nav import render_nav


ROOT = Path(__file__).resolve().parents[1]
API_COSTS_PATH = ROOT / "data" / "api_costs" / "api_costs.jsonl"
RO_ACTIVITY_DIR = ROOT / "data" / "ro_activity"
STATUS_TRANSITIONS_DIR = ROOT / "data" / "status_transitions"
ARIZONA_TZ = timezone(timedelta(hours=-7))
SHOP_OPEN = time(7, 0)
SHOP_CLOSE = time(18, 0)

EXPECTED_ORDER = [
    "checkin",
    "inspecting",
    "call_shop",
    "parts",
    "servicing",
    "k_mech_complete",
    "qc",
    "ready",
    "finished",
]
EXPECTED_INDEX = {stage: index for index, stage in enumerate(EXPECTED_ORDER)}

STATUS_ALIASES = {
    "check in": "checkin",
    "checked in": "checkin",
    "inspection": "inspecting",
    "inspect": "inspecting",
    "call shop": "call_shop",
    "call-shop": "call_shop",
    "waiting approval": "call_shop",
    "advisor estimate": "call_shop",
    "technical advisement": "call_shop",
    "waiting parts": "parts",
    "ordering parts": "parts",
    "part": "parts",
    "servicing / in progress": "servicing",
    "in progress": "servicing",
    "k mech complete": "k_mech_complete",
    "mechanic complete": "k_mech_complete",
    "mech complete": "k_mech_complete",
    "advisor qc review": "qc",
    "quality control": "qc",
    "advisor finalize ro": "ready",
    "close": "finished",
    "closed": "finished",
}


def _escape(value: object) -> str:
    return html.escape(str(value or ""))


def _parse_dt(value: object) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _az(dt: datetime) -> datetime:
    return dt.astimezone(ARIZONA_TZ)


def _fmt_az(value: object) -> str:
    dt = _parse_dt(value)
    if not dt:
        return "unknown"
    local = _az(dt)
    hour = local.hour % 12 or 12
    ampm = "AM" if local.hour < 12 else "PM"
    return f"{local.strftime('%a %b')} {local.day} &middot; {hour}:{local.strftime('%M')} {ampm}"


def _duration_label(hours: float | None) -> str:
    if hours is None:
        return "unknown"
    hours = max(0.0, hours)
    if hours < 1:
        return f"{int(hours * 60)}m"
    if hours < 24:
        whole = int(hours)
        mins = int((hours - whole) * 60)
        return f"{whole}h {mins}m" if mins else f"{whole}h"
    days = int(hours // 24)
    return f"{days}d {int(hours % 24)}h"


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                if isinstance(item, dict):
                    rows.append(item)
    except Exception:
        return []
    return rows


def _normalize_ro(value: object) -> str:
    text = str(value or "").strip()
    if text.lower().startswith("ro"):
        text = text[2:].strip()
    return text


def _normalize_status(value: object) -> str:
    text = str(value or "").strip().lower().replace("_", " ")
    text = " ".join(text.split())
    return STATUS_ALIASES.get(text, text)


def _event_time(event: dict) -> datetime | None:
    return (
        _parse_dt(event.get("received_at"))
        or _parse_dt(event.get("event_timestamp"))
        or _parse_dt(event.get("timestamp"))
    )


def _api_time(event: dict) -> datetime | None:
    return _parse_dt(event.get("timestamp") or event.get("created_at") or event.get("generated_at"))


def _event_ro(event: dict) -> str:
    return _normalize_ro(event.get("ro") or event.get("invoice") or event.get("ticket_reference"))


def _status(event: dict) -> str:
    return str(event.get("status") or event.get("workflow_status") or "").strip()


def _customer(event: dict) -> str:
    return str(event.get("customer") or "").strip()


def _load_api_costs() -> list[dict]:
    rows = []
    for item in _read_jsonl(API_COSTS_PATH):
        dt = _api_time(item)
        item["_dt"] = dt
        item["_ro"] = _normalize_ro(item.get("ro"))
        rows.append(item)
    return rows


def _load_ro_activity() -> dict[str, list[dict]]:
    by_ro: dict[str, list[dict]] = defaultdict(list)
    if RO_ACTIVITY_DIR.exists():
        for path in RO_ACTIVITY_DIR.glob("*.jsonl"):
            fallback_ro = _normalize_ro(path.stem)
            for event in _read_jsonl(path):
                ro = _event_ro(event) or fallback_ro
                if not ro:
                    continue
                event["_dt"] = _event_time(event)
                event["_ro"] = ro
                by_ro[ro].append(event)

    if STATUS_TRANSITIONS_DIR.exists():
        for path in STATUS_TRANSITIONS_DIR.glob("*.jsonl"):
            for event in _read_jsonl(path):
                ro = _event_ro(event)
                if not ro:
                    continue
                event["_dt"] = _event_time(event)
                event["_ro"] = ro
                by_ro[ro].append(event)

    for ro, events in list(by_ro.items()):
        seen = set()
        unique = []
        for event in sorted(events, key=lambda e: e.get("_dt") or datetime.min.replace(tzinfo=timezone.utc)):
            key = (
                (event.get("_dt").isoformat() if event.get("_dt") else ""),
                _normalize_status(_status(event)),
                str(event.get("event_type") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(event)
        by_ro[ro] = unique
    return dict(by_ro)


def _today_activity(api_rows: list[dict]) -> list[dict]:
    today = _az(_now_utc()).date()
    allowed = {"packet_generate", "photo_analysis"}
    rows = []
    for item in api_rows:
        dt = item.get("_dt")
        if not dt or _az(dt).date() != today:
            continue
        if str(item.get("action") or "").strip() not in allowed:
            continue
        rows.append(item)
    return sorted(rows, key=lambda x: x.get("_dt") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)


def _who_badge(name: object) -> str:
    raw = str(name or "system").strip() or "system"
    key = raw.lower()
    cls = "gray"
    if key == "drew":
        cls = "blue"
    elif key == "mitch":
        cls = "green"
    elif key == "preston":
        cls = "purple"
    return f'<span class="who {cls}">{_escape(raw)}</span>'


def _render_activity_feed(rows: list[dict]) -> str:
    if not rows:
        return '<div class="alert red">NO ADVISOR ACTIVITY LOGGED TODAY</div>'
    body = []
    labels = {
        "packet_generate": "Packet Generated",
        "photo_analysis": "Photo Analysis",
    }
    for item in rows:
        action = str(item.get("action") or "")
        body.append(
            "<tr>"
            f"<td>{_fmt_az(item.get('timestamp'))}</td>"
            f"<td>RO {_escape(item.get('_ro'))}</td>"
            f"<td>{_escape(item.get('customer'))}</td>"
            f"<td>{_who_badge(item.get('requested_by'))}</td>"
            f"<td>{_escape(labels.get(action, action))}</td>"
            "</tr>"
        )
    return '<table><thead><tr><th>Time</th><th>RO</th><th>Customer</th><th>Who</th><th>Action</th></tr></thead><tbody>' + "".join(body) + "</tbody></table>"


def _render_who_worked(rows: list[dict]) -> str:
    summary: dict[str, dict] = {}
    for item in rows:
        who = str(item.get("requested_by") or "system").strip()
        if not who or who.lower() == "system":
            continue
        key = who.lower()
        entry = summary.setdefault(key, {"name": who, "packet_generate": 0, "photo_analysis": 0, "last": None})
        action = str(item.get("action") or "")
        if action in {"packet_generate", "photo_analysis"}:
            entry[action] += 1
        if item.get("_dt") and (entry["last"] is None or item["_dt"] > entry["last"]):
            entry["last"] = item["_dt"]

    if not summary:
        return '<div class="empty">No named advisor activity logged today.</div>'

    cards = []
    for entry in sorted(summary.values(), key=lambda e: str(e["name"]).lower()):
        cards.append(f"""
        <div class="summary-card">
          <div class="name">{_escape(entry["name"])}</div>
          <div class="metric"><b>{entry["packet_generate"]}</b><span>Packets generated</span></div>
          <div class="metric"><b>{entry["photo_analysis"]}</b><span>Photo analyses run</span></div>
          <div class="last">Last action: {_fmt_az(entry["last"].isoformat() if entry["last"] else "")}</div>
        </div>
        """)
    return '<div class="summary-grid">' + "".join(cards) + "</div>"


def _status_sequence(events: list[dict]) -> list[dict]:
    sequence = []
    last_status = ""
    for event in events:
        status = _normalize_status(_status(event))
        dt = event.get("_dt")
        if not status or not dt or status not in EXPECTED_INDEX:
            continue
        if status == last_status:
            continue
        sequence.append({
            "status": status,
            "raw_status": _status(event),
            "dt": dt,
            "customer": _customer(event),
            "event": event,
        })
        last_status = status
    return sequence


def _skipped_stages(prev: str, current: str) -> str:
    prev_i = EXPECTED_INDEX.get(prev)
    cur_i = EXPECTED_INDEX.get(current)
    if prev_i is None or cur_i is None or cur_i <= prev_i + 1:
        return "none"
    return " -> ".join(EXPECTED_ORDER[prev_i + 1:cur_i])


def _skip_alerts(activity: dict[str, list[dict]]) -> list[dict]:
    cutoff = _now_utc() - timedelta(days=7)
    alerts = []
    for ro, events in activity.items():
        recent = [event for event in events if event.get("_dt") and event["_dt"] >= cutoff]
        sequence = _status_sequence(recent)
        if len(sequence) < 2:
            continue
        customer = next((row["customer"] for row in reversed(sequence) if row["customer"]), "")
        for index in range(1, len(sequence)):
            prev = sequence[index - 1]
            cur = sequence[index]
            prev_status = prev["status"]
            cur_status = cur["status"]
            prev_i = EXPECTED_INDEX[prev_status]
            cur_i = EXPECTED_INDEX[cur_status]
            minutes = max(0.0, (cur["dt"] - prev["dt"]).total_seconds() / 60)
            reason = ""
            skipped = _skipped_stages(prev_status, cur_status)

            if prev_status == "checkin" and cur_i >= EXPECTED_INDEX["servicing"]:
                reason = "Skipped DVI and parts ordering"
            elif prev_status == "inspecting" and cur_status == "servicing":
                reason = "Skipped customer approval and parts"
            elif prev_status == "parts" and cur_status in {"finished", "ready"}:
                reason = "Skipped QC"
            elif prev_status == "k_mech_complete" and cur_status == "finished":
                reason = "Skipped QC and ready staging"
            elif cur_i - prev_i >= 3 and minutes < 10:
                reason = "Board catch-up dump, not real-time updates"

            if index >= 2:
                two_back = sequence[index - 2]
                if two_back["status"] == "inspecting" and prev_status == "parts" and cur_status == "servicing":
                    between = [row["status"] for row in sequence[index - 2:index + 1]]
                    if "call_shop" not in between:
                        reason = "Skipped customer approval"
                        skipped = "call_shop"

            if reason:
                alerts.append({
                    "ro": ro,
                    "customer": customer,
                    "reason": reason,
                    "time": cur["dt"],
                    "from": prev_status,
                    "to": cur_status,
                    "skipped": skipped,
                })
    return sorted(alerts, key=lambda x: x["time"], reverse=True)


def _render_skip_alerts(alerts: list[dict]) -> str:
    if not alerts:
        return '<div class="alert green">No workflow skips detected.</div>'
    cards = []
    for alert in alerts:
        cards.append(f"""
        <div class="skip-card">
          <div class="ro">RO {_escape(alert["ro"])}</div>
          <div class="cust">{_escape(alert.get("customer") or "Unknown Customer")}</div>
          <div class="bad">{_escape(alert["reason"])}</div>
          <div class="small">Jump: {_escape(alert["from"])} -> {_escape(alert["to"])} at {_fmt_az(alert["time"].isoformat())}</div>
          <div class="small">Stages skipped: {_escape(alert["skipped"])}</div>
        </div>
        """)
    return '<div class="skip-grid">' + "".join(cards) + "</div>"


def _shop_hours_between(start_utc: datetime, end_utc: datetime) -> float:
    if end_utc <= start_utc:
        return 0.0
    start = _az(start_utc)
    end = _az(end_utc)
    total = 0.0
    day = start.date()
    while day <= end.date():
        open_dt = datetime.combine(day, SHOP_OPEN, tzinfo=ARIZONA_TZ)
        close_dt = datetime.combine(day, SHOP_CLOSE, tzinfo=ARIZONA_TZ)
        segment_start = max(start, open_dt)
        segment_end = min(end, close_dt)
        if segment_end > segment_start:
            total += (segment_end - segment_start).total_seconds() / 3600
        day += timedelta(days=1)
    return total


def _duration_class(hours: float | None) -> str:
    if hours is None:
        return "neutral"
    if hours > 8:
        return "darkred"
    if hours > 4:
        return "red"
    if hours >= 2:
        return "yellow"
    return "green"


def _active_ros(activity: dict[str, list[dict]], hours: int) -> dict[str, list[dict]]:
    cutoff = _now_utc() - timedelta(hours=hours)
    return {
        ro: events
        for ro, events in activity.items()
        if any(event.get("_dt") and event["_dt"] >= cutoff for event in events)
    }


def _render_bottlenecks(activity: dict[str, list[dict]]) -> str:
    active = _active_ros(activity, 48)
    if not active:
        return '<div class="empty">No RO activity in the last 48 hours.</div>'
    rows = []
    now = _now_utc()
    for ro, events in sorted(active.items()):
        seq = _status_sequence(events)
        if not seq:
            continue
        current = seq[-1]
        prev = seq[-2] if len(seq) >= 2 else None
        current_hours = max(0.0, (now - current["dt"]).total_seconds() / 3600)
        prev_hours = max(0.0, (current["dt"] - prev["dt"]).total_seconds() / 3600) if prev else None
        shop_hours = _shop_hours_between(current["dt"], now)
        row_class = " class=\"hot-row\"" if shop_hours > 4 else ""
        current_flag = " ALERT" if current_hours > 8 else ""
        rows.append(
            f"<tr{row_class}>"
            f"<td>RO {_escape(ro)}</td>"
            f"<td>{_escape(current.get('customer') or 'Unknown')}</td>"
            f"<td>{_escape(current['status'])}</td>"
            f"<td><span class=\"stage-pill {_duration_class(current_hours)}\">{_duration_label(current_hours)}{current_flag}</span></td>"
            f"<td>{_escape(prev['status'] if prev else 'none')}</td>"
            f"<td><span class=\"stage-pill {_duration_class(prev_hours)}\">{_duration_label(prev_hours)}</span></td>"
            "</tr>"
        )
    if not rows:
        return '<div class="empty">No status-stage records found in the last 48 hours.</div>'
    return '<table><thead><tr><th>RO</th><th>Customer</th><th>Current Status</th><th>Time in Current Stage</th><th>Previous Stage</th><th>Time in Previous Stage</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table>"


def _render_no_packet_gaps(activity: dict[str, list[dict]], api_rows: list[dict]) -> str:
    active = _active_ros(activity, 48)
    generated = {
        _normalize_ro(row.get("_ro") or row.get("ro"))
        for row in api_rows
        if str(row.get("action") or "") == "packet_generate"
    }
    gaps = []
    for ro, events in active.items():
        if ro in generated:
            continue
        latest = max((event.get("_dt") for event in events if event.get("_dt")), default=None)
        gaps.append((ro, latest))
    if not gaps:
        return '<div class="alert green">Every recently active RO has a packet_generate record.</div>'
    items = []
    for ro, latest in sorted(gaps, key=lambda item: item[1] or datetime.min.replace(tzinfo=timezone.utc), reverse=True):
        items.append(f"<li><b>RO {_escape(ro)}</b><span>Last webhook: {_fmt_az(latest.isoformat() if latest else '')}</span></li>")
    return '<div class="alert orange">These ROs are active but no TekMetric Packet has been generated</div><ul class="gap-list">' + "".join(items) + "</ul>"


def render_activity_page(selected_user: str = "") -> str:
    api_rows = _load_api_costs()
    activity = _load_ro_activity()
    today_rows = _today_activity(api_rows)
    skip_alerts = _skip_alerts(activity)
    selected = selected_user if selected_user in {"Preston", "Drew", "Mitch"} else ""
    generated = _fmt_az(_now_utc().isoformat())

    options = ["", "Preston", "Drew", "Mitch"]
    option_html = "".join(
        f'<option value="{_escape(option)}"{" selected" if option == selected else ""}>{_escape(option or "Select user")}</option>'
        for option in options
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="120">
  <title>Advisor Activity | Callahan Auto</title>
  <style>
    :root{{--navy:#0f172a;--bg:#07111f;--panel:#0f1b2d;--card:#111f33;--line:#23364f;--text:#fff;--muted:#94a3b8;--red:#ef4444;--green:#22c55e;--orange:#f97316;--purple:#8b5cf6;--blue:#3b82f6}}
    *{{box-sizing:border-box}}
    body{{margin:0;background:radial-gradient(circle at top left,#172554 0%,#07111f 42%,#020617 100%);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,Arial,sans-serif;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}}
    .topbar{{background:var(--navy);color:#fff;padding:18px 24px;display:flex;align-items:center;justify-content:space-between;gap:18px;box-shadow:0 6px 18px rgba(0,0,0,.28);border-bottom:1px solid rgba(148,163,184,.24)}}
    .title{{font-size:20px;font-weight:950;letter-spacing:.08em}}
    .sub{{font-size:11px;color:#cbd5e1;margin-top:4px;letter-spacing:.05em;text-transform:uppercase}}
    .user-actions{{display:flex;gap:10px;align-items:center;flex-wrap:wrap}}
    .user-actions button{{height:34px;border-radius:9px;border:1px solid rgba(255,255,255,.18);background:rgba(255,255,255,.08);color:#fff;text-decoration:none;padding:8px 12px;font-size:12px;font-weight:800;cursor:pointer}}
    .user-form{{display:flex;gap:8px;align-items:center;background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.16);border-radius:12px;padding:8px}}
    .user-form label{{font-size:11px;font-weight:900;color:#cbd5e1;text-transform:uppercase;letter-spacing:.08em}}
    select{{height:32px;border-radius:8px;border:1px solid #334155;background:#020617;color:#fff;padding:0 9px;font-weight:800}}
    main{{padding:22px 24px 50px;max-width:1480px;margin:0 auto}}
    section{{background:rgba(15,27,45,.88);border:1px solid var(--line);border-radius:16px;box-shadow:0 16px 38px rgba(0,0,0,.24);padding:18px;margin-bottom:18px}}
    h2{{margin:0 0 12px;font-size:17px;letter-spacing:.04em;text-transform:uppercase;color:#e2e8f0}}
    .section-note{{font-size:12px;color:var(--muted);margin:-6px 0 14px}}
    table{{width:100%;border-collapse:collapse;font-size:13px}}
    th{{text-align:left;background:#0b1626;color:#94a3b8;text-transform:uppercase;letter-spacing:.06em;font-size:11px;padding:10px;border-bottom:1px solid #263954}}
    td{{padding:11px 10px;border-bottom:1px solid #1e2f49;vertical-align:middle;color:#e2e8f0}}
    tr.hot-row{{background:rgba(239,68,68,.12)}}
    .alert{{border-radius:12px;padding:14px 16px;font-weight:900;font-size:13px;letter-spacing:.03em}}
    .alert.red{{background:#fee2e2;color:#991b1b;border:1px solid #fecaca}}
    .alert.green{{background:#dcfce7;color:#166534;border:1px solid #bbf7d0}}
    .alert.orange{{background:#ffedd5;color:#9a3412;border:1px solid #fed7aa;margin-bottom:10px}}
    .empty{{border:1px dashed #334155;border-radius:12px;padding:16px;color:#94a3b8;font-weight:800;text-align:center;background:#0b1626}}
    .who{{display:inline-flex;align-items:center;border-radius:999px;padding:5px 10px;font-size:11px;font-weight:950;color:#fff;text-transform:uppercase;letter-spacing:.04em}}
    .who.blue{{background:var(--blue)}}.who.purple{{background:var(--purple)}}.who.green{{background:var(--green)}}.who.gray{{background:#64748b}}
    .summary-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}}
    .summary-card{{border:1px solid #263954;border-radius:14px;padding:14px;background:#111f33}}
    .summary-card .name{{font-size:18px;font-weight:950;margin-bottom:10px}}
    .metric{{display:flex;align-items:baseline;gap:8px;margin:6px 0}}.metric b{{font-size:24px}}.metric span{{font-size:12px;color:#94a3b8;font-weight:800}}
    .last{{font-size:12px;color:#94a3b8;margin-top:10px;font-weight:800}}
    .skip-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}}
    .skip-card{{background:rgba(127,29,29,.26);border:2px solid #ef4444;border-radius:14px;padding:14px}}
    .skip-card .ro{{font-size:18px;font-weight:950;color:#fecaca}}.skip-card .cust{{font-size:13px;color:#cbd5e1;font-weight:800;margin:3px 0 10px}}.bad{{font-size:14px;font-weight:950;color:#fca5a5;margin-bottom:8px}}.small{{font-size:12px;color:#cbd5e1;line-height:1.45}}
    .stage-pill{{display:inline-flex;border-radius:999px;padding:5px 9px;font-size:11px;font-weight:950;color:#111827;border:1px solid transparent}}
    .stage-pill.green{{background:#dcfce7;color:#166534;border-color:#bbf7d0}}.stage-pill.yellow{{background:#fef9c3;color:#854d0e;border-color:#fde68a}}.stage-pill.red{{background:#fee2e2;color:#991b1b;border-color:#fecaca}}.stage-pill.darkred{{background:#7f1d1d;color:#fff;border-color:#450a0a}}.stage-pill.neutral{{background:#e2e8f0;color:#334155;border-color:#cbd5e1}}
    .gap-list{{list-style:none;margin:0;padding:0;display:grid;gap:8px}}.gap-list li{{display:flex;justify-content:space-between;gap:12px;align-items:center;background:rgba(154,52,18,.24);border:1px solid #f97316;border-radius:10px;padding:10px 12px}}.gap-list span{{color:#fdba74;font-size:12px;font-weight:800}}
    @media(max-width:760px){{.topbar{{align-items:flex-start;flex-direction:column}}main{{padding:14px}}table{{font-size:12px}}td,th{{padding:8px 6px}}}}
  </style>
</head>
<body>
  {render_nav("Activity")}
  <header class="topbar">
    <div>
      <div class="title">ADVISOR ACTIVITY &amp; ACCOUNTABILITY</div>
      <div class="sub">Generated {generated} &middot; auto-refreshes every 2 minutes</div>
    </div>
    <div class="user-actions">
      <form class="user-form" method="get" action="/activity">
        <label for="user">Who are you?</label>
        <select id="user" name="user">{option_html}</select>
        <button type="submit">Save</button>
      </form>
    </div>
  </header>
  <main>
    <section>
      <h2>Today's Activity Feed</h2>
      <div class="section-note">Shows packet generation and photo analysis only. Cache hits and history views are intentionally hidden.</div>
      {_render_activity_feed(today_rows)}
    </section>
    <section>
      <h2>Who Worked Today</h2>
      {_render_who_worked(today_rows)}
    </section>
    <section>
      <h2>Workflow Skip Alerts (Critical)</h2>
      <div class="section-note">Flags illegal AutoFlow status jumps from the last 7 days.</div>
      {_render_skip_alerts(skip_alerts)}
    </section>
    <section>
      <h2>Time in Stage (Bottleneck Tracker)</h2>
      <div class="section-note">Active ROs from the last 48 hours. Rows turn red when current-stage shop-hours exceed 4 hours.</div>
      {_render_bottlenecks(activity)}
    </section>
    <section>
      <h2>ROs With No Packet (Gap Alert)</h2>
      {_render_no_packet_gaps(activity, api_rows)}
    </section>
  </main>
</body>
</html>"""
