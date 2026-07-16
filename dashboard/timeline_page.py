"""RO status timeline and bottleneck report."""

from __future__ import annotations

import html
import json
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from pathlib import Path

try:
    from dashboard.nav import render_nav
except ImportError:  # pragma: no cover
    from nav import render_nav


ROOT = Path(__file__).resolve().parents[1]
RO_ACTIVITY_DIR = ROOT / "data" / "ro_activity"
API_COSTS_PATH = ROOT / "data" / "api_costs" / "api_costs.jsonl"
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
STATUS_RANK = {status: index + 1 for index, status in enumerate(EXPECTED_ORDER)}

STATUS_ALIASES = {
    "check in": "checkin",
    "checked in": "checkin",
    "inspection": "inspecting",
    "inspect": "inspecting",
    "call shop": "call_shop",
    "call-shop": "call_shop",
    "waiting approval": "call_shop",
    "waiting_approval": "call_shop",
    "advisor estimate": "call_shop",
    "waiting parts": "parts",
    "waiting_parts": "parts",
    "ordering parts": "parts",
    "ordering_parts": "parts",
    "in progress": "servicing",
    "servicing / in progress": "servicing",
    "k mech complete": "k_mech_complete",
    "mechanic complete": "k_mech_complete",
    "advisor qc review": "qc",
    "advisor finalize ro": "ready",
    "ready to close": "ready",
    "closed": "finished",
    "close": "finished",
}


def _escape(value: object) -> str:
    return html.escape(str(value or ""))


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


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


def _duration_hours(start: datetime | None, end: datetime | None) -> float | None:
    if not start or not end:
        return None
    return max(0.0, (end - start).total_seconds() / 3600)


def _duration_label(hours: float | None) -> str:
    if hours is None:
        return "unknown"
    if hours < 1:
        return f"{max(0, int(hours * 60))}m"
    if hours < 24:
        whole = int(hours)
        mins = int((hours - whole) * 60)
        return f"{whole}h {mins}m" if mins else f"{whole}h"
    return f"{int(hours // 24)}d {int(hours % 24)}h"


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


def _rank(status: str) -> int:
    return STATUS_RANK.get(_normalize_status(status), 0)


def _event_time(event: dict) -> datetime | None:
    return (
        _parse_dt(event.get("received_at"))
        or _parse_dt(event.get("timestamp"))
        or _parse_dt(event.get("event_timestamp"))
    )


def _event_ro(event: dict, fallback: str = "") -> str:
    return _normalize_ro(event.get("ro") or event.get("invoice") or event.get("ticket_reference") or fallback)


def _event_status(event: dict) -> str:
    return str(event.get("status") or event.get("workflow_status") or "").strip()


def _load_packet_ros() -> set[str]:
    generated = set()
    for row in _read_jsonl(API_COSTS_PATH):
        if str(row.get("action") or "") == "packet_generate":
            ro = _normalize_ro(row.get("ro"))
            if ro:
                generated.add(ro)
    return generated


def _load_ro_activity() -> dict[str, list[dict]]:
    by_ro: dict[str, list[dict]] = defaultdict(list)
    if not RO_ACTIVITY_DIR.exists():
        return {}
    for path in RO_ACTIVITY_DIR.glob("*.jsonl"):
        if path.name.lower() == "none.jsonl":
            continue
        fallback = _normalize_ro(path.stem)
        for event in _read_jsonl(path):
            dt = _event_time(event)
            status = _event_status(event)
            if not dt or not status:
                continue
            ro = _event_ro(event, fallback)
            if not ro:
                continue
            item = dict(event)
            item["_dt"] = dt
            item["_ro"] = ro
            item["_status"] = status
            item["_canonical"] = _normalize_status(status)
            by_ro[ro].append(item)
    for ro, events in list(by_ro.items()):
        by_ro[ro] = sorted(events, key=lambda e: e["_dt"])
    return dict(by_ro)


def _stage_segments(events: list[dict], now: datetime | None = None) -> list[dict]:
    now = now or _now_utc()
    compressed = []
    last = ""
    for event in events:
        canonical = event["_canonical"]
        if canonical == last:
            continue
        compressed.append(event)
        last = canonical
    segments = []
    for index, event in enumerate(compressed):
        end = compressed[index + 1]["_dt"] if index + 1 < len(compressed) else now
        hours = _duration_hours(event["_dt"], end)
        segments.append({
            "status": event["_canonical"],
            "raw_status": event["_status"],
            "start": event["_dt"],
            "end": end,
            "hours": hours,
            "customer": str(event.get("customer") or "").strip(),
        })
    return segments


def _duration_class(hours: float | None) -> str:
    if hours is None:
        return "neutral"
    if hours > 24:
        return "darkred"
    if hours > 8:
        return "red"
    if hours >= 4:
        return "orange"
    if hours >= 2:
        return "yellow"
    return "green"


def _backwards_explanation(prev: str, cur: str) -> str:
    if prev == "ready" and _rank(cur) <= _rank("qc"):
        return "Rework detected - vehicle returned from ready stage"
    if prev == "qc" and _rank(cur) <= _rank("servicing"):
        return "QC failed - sent back to tech"
    if prev == "servicing" and cur == "parts":
        return "Parts issue discovered mid-repair"
    if prev == "parts" and cur == "inspecting":
        return "Inspection restarted - scope change or new concern"
    if cur == "checkin":
        return "Vehicle returned to shop"
    return "Board correction or status reset"


def _skipped_stages(prev: str, cur: str) -> str:
    prev_i = _rank(prev)
    cur_i = _rank(cur)
    if prev_i <= 0 or cur_i <= prev_i + 1:
        return "none"
    return " -> ".join(EXPECTED_ORDER[prev_i:cur_i - 1])


def _analyze_ro(ro: str, events: list[dict], packet_ros: set[str]) -> dict:
    now = _now_utc()
    segments = _stage_segments(events, now=now)
    current = segments[-1] if segments else {}
    customer = next((segment["customer"] for segment in reversed(segments) if segment.get("customer")), "")
    has_packet = ro in packet_ros
    alerts = {"skips": [], "backwards": [], "over4": [], "bottlenecks": []}

    for index in range(1, len(segments)):
        prev = segments[index - 1]
        cur = segments[index]
        prev_status = prev["status"]
        cur_status = cur["status"]
        prev_rank = _rank(prev_status)
        cur_rank = _rank(cur_status)
        minutes = max(0.0, (cur["start"] - prev["start"]).total_seconds() / 60)

        reason = ""
        skipped = _skipped_stages(prev_status, cur_status)
        if prev_status == "checkin" and cur_rank >= _rank("servicing"):
            reason = "Skipped DVI and parts ordering"
        elif prev_status == "inspecting" and cur_status == "servicing":
            reason = "Skipped customer approval and parts"
        elif prev_status == "parts" and cur_status == "finished":
            reason = "Skipped QC"
        elif prev_status == "k_mech_complete" and cur_status == "finished":
            reason = "Skipped QC and ready staging"
        elif cur_rank - prev_rank >= 3 and minutes < 15:
            reason = "Catch-up board dump - stages were not updated as they happened"
        if reason:
            alerts["skips"].append({
                "from": prev_status,
                "to": cur_status,
                "at": cur["start"],
                "reason": reason,
                "skipped": skipped,
            })

        if cur_rank and prev_rank and cur_rank < prev_rank:
            alerts["backwards"].append({
                "from": prev_status,
                "to": cur_status,
                "at": cur["start"],
                "reason": _backwards_explanation(prev_status, cur_status),
            })

    for segment in segments:
        hours = segment.get("hours")
        status = segment.get("status")
        shop_hours = _shop_hours_between(segment["start"], segment["end"])
        if hours is not None and hours > 4:
            alerts["over4"].append(segment)
        explanation = ""
        if status == "parts" and shop_hours > 4:
            explanation = "Parts delay - supplier lead time or ordering not completed"
        elif status == "call_shop" and shop_hours > 2:
            explanation = "Customer approval pending - follow-up call needed"
        elif status == "inspecting" and shop_hours > 3:
            explanation = "DVI not completed or advisor hasn't reviewed findings"
        elif status == "qc" and shop_hours > 2:
            explanation = "QC hold - possible rework or advisor hasn't cleared vehicle"
        elif status == "servicing" and hours is not None and hours > 8:
            explanation = "Extended repair - verify tech has parts and no hidden blockers"
        elif status == "k_mech_complete" and shop_hours > 1:
            explanation = "Tech done but QC not started - handoff missed"
        elif status == "ready" and shop_hours > 4:
            explanation = "Vehicle ready but customer not contacted or pickup delayed"
        elif shop_hours >= 6:
            explanation = "Board not being updated in real time - verify actual vehicle status"
        if explanation:
            alerts["bottlenecks"].append({**segment, "reason": explanation})

    for alert in alerts["skips"]:
        if "Catch-up board dump" in alert["reason"]:
            alerts["bottlenecks"].append({
                "status": alert["from"] + " -> " + alert["to"],
                "hours": 0.0,
                "start": alert["at"],
                "end": alert["at"],
                "reason": "Catch-up board dump - stages were not updated as they happened",
            })

    total_open = _duration_hours(segments[0]["start"], current.get("end")) if segments else None
    completed_total = None
    first_checkin = next((s for s in segments if s["status"] == "checkin"), None)
    first_finished = next((s for s in segments if s["status"] == "finished"), None)
    if first_checkin and first_finished:
        completed_total = _duration_hours(first_checkin["start"], first_finished["start"])

    return {
        "ro": ro,
        "customer": customer or "Unknown Customer",
        "events": events,
        "segments": segments,
        "current_status": current.get("status", "unknown"),
        "current_time": current.get("hours"),
        "total_open": total_open,
        "completed_total": completed_total,
        "latest": events[-1]["_dt"] if events else None,
        "has_packet": has_packet,
        "alerts": alerts,
        "flagged": bool(alerts["skips"] or alerts["backwards"] or alerts["over4"] or alerts["bottlenecks"] or not has_packet),
    }


def _window_cutoff(window: str) -> datetime | None:
    if window == "7":
        return _now_utc() - timedelta(days=7)
    if window == "all":
        return None
    return _now_utc() - timedelta(days=30)


def _filter_rows(rows: list[dict], window: str, status_filter: str, alert_filter: str) -> list[dict]:
    cutoff = _window_cutoff(window)
    filtered = []
    for row in rows:
        if cutoff and (not row.get("latest") or row["latest"] < cutoff):
            continue
        current = row.get("current_status")
        completed = current in {"finished"}
        if status_filter == "active" and completed:
            continue
        if status_filter == "completed" and not completed:
            continue
        if alert_filter == "flagged" and not row.get("flagged"):
            continue
        filtered.append(row)
    return filtered


def _select(name: str, selected: str, options: list[tuple[str, str]]) -> str:
    option_html = "".join(
        f'<option value="{_escape(value)}"{" selected" if value == selected else ""}>{_escape(label)}</option>'
        for value, label in options
    )
    return f'<select name="{_escape(name)}">{option_html}</select>'


def _stage_pill(segment: dict) -> str:
    cls = _duration_class(segment.get("hours"))
    flag = " ALERT" if cls == "darkred" else ""
    return (
        f'<span class="stage {cls}">'
        f'<b>{_escape(segment.get("status"))}</b>'
        f'<small>{_duration_label(segment.get("hours"))}{flag}</small>'
        "</span>"
    )


def _alert_badges(row: dict) -> str:
    alerts = row["alerts"]
    badges = [
        ("skips", len(alerts["skips"])),
        ("backwards", len(alerts["backwards"])),
        ("over 4h", len(alerts["over4"])),
    ]
    if not row["has_packet"]:
        badges.append(("no packet", 1))
    return "".join(f'<span class="alert-badge">{count} {_escape(label)}</span>' for label, count in badges if count)


def _detail_block(row: dict) -> str:
    history = []
    segments = row["segments"]
    if len(segments) <= 1:
        history.append("<li>Only one event recorded</li>")
    else:
        for segment in segments:
            history.append(
                f"<li><b>{_escape(segment['status'])}</b> at {_fmt_az(segment['start'].isoformat())} "
                f"- duration {_duration_label(segment.get('hours'))}</li>"
            )
    alert_lines = []
    for skip in row["alerts"]["skips"]:
        alert_lines.append(f"<li>Skip: {_escape(skip['from'])} -> {_escape(skip['to'])}. {_escape(skip['reason'])}. Skipped: {_escape(skip['skipped'])}</li>")
    for move in row["alerts"]["backwards"]:
        alert_lines.append(f"<li>Backwards: {_escape(move['from'])} -> {_escape(move['to'])}. {_escape(move['reason'])}</li>")
    for bottleneck in row["alerts"]["bottlenecks"]:
        alert_lines.append(f"<li>Bottleneck: {_escape(bottleneck['status'])} for {_duration_label(bottleneck.get('hours'))}. {_escape(bottleneck['reason'])}</li>")
    if not alert_lines:
        alert_lines.append("<li>No alerts on this RO.</li>")
    packet = "Yes" if row["has_packet"] else "No"
    return (
        '<div class="detail">'
        '<div><h4>Chronological status history</h4><ul>' + "".join(history) + "</ul></div>"
        '<div><h4>Alert details</h4><ul>' + "".join(alert_lines) + "</ul></div>"
        f'<div><h4>Packet generated?</h4><p>{packet}</p></div>'
        "</div>"
    )


def _timeline_table(rows: list[dict]) -> str:
    if not rows:
        return '<div class="empty">No webhook data found - ensure the webhook receiver is running.</div>'
    body = []
    for row in rows:
        stages = "".join(_stage_pill(segment) for segment in row["segments"]) or "Only one event recorded"
        body.append(f"""
        <tr>
          <td>
            <details>
              <summary>RO {_escape(row["ro"])}</summary>
              {_detail_block(row)}
            </details>
          </td>
          <td>{_escape(row["customer"])}</td>
          <td>{_escape(row["current_status"])}</td>
          <td>{_duration_label(row["total_open"])}</td>
          <td><div class="stage-line">{stages}</div></td>
          <td>{_alert_badges(row) or '<span class="muted">none</span>'}</td>
        </tr>
        """)
    return '<table><thead><tr><th>RO</th><th>Customer</th><th>Current Status</th><th>Total Time Open</th><th>Stages</th><th>Alerts</th></tr></thead><tbody>' + "".join(body) + "</tbody></table>"


def _backwards_table(rows: list[dict]) -> str:
    moves = []
    for row in rows:
        for move in row["alerts"]["backwards"]:
            moves.append((row, move))
    if not moves:
        return '<div class="clean">No backwards movements detected.</div>'
    body = []
    for row, move in sorted(moves, key=lambda x: x[1]["at"], reverse=True):
        body.append(
            f"<tr><td>RO {_escape(row['ro'])}</td><td>{_escape(row['customer'])}</td>"
            f"<td>{_escape(move['from'])}</td><td>{_escape(move['to'])}</td>"
            f"<td>{_fmt_az(move['at'].isoformat())}</td><td>{_escape(move['reason'])}</td></tr>"
        )
    return '<table><thead><tr><th>RO</th><th>Customer</th><th>Moved from</th><th>Moved to</th><th>At</th><th>Possible explanation</th></tr></thead><tbody>' + "".join(body) + "</tbody></table>"


def _bottleneck_cards(rows: list[dict]) -> str:
    cards = []
    for row in rows:
        for item in row["alerts"]["bottlenecks"]:
            cards.append(f"""
            <div class="bottle-card">
              <b>RO {_escape(row["ro"])}</b>
              <span>{_escape(row["customer"])}</span>
              <strong>{_escape(item["status"])} - {_duration_label(item.get("hours"))}</strong>
              <p>{_escape(item["reason"])}</p>
            </div>
            """)
    if not cards:
        return '<div class="clean">No bottlenecks detected in this window.</div>'
    return '<div class="bottle-grid">' + "".join(cards) + "</div>"


def _skip_cards(rows: list[dict]) -> str:
    cards = []
    for row in rows:
        for skip in row["alerts"]["skips"]:
            cards.append(f"""
            <div class="skip-card">
              <b>RO {_escape(row["ro"])}</b>
              <span>{_escape(row["customer"])}</span>
              <strong>{_escape(skip["from"])} -> {_escape(skip["to"])}</strong>
              <p>{_escape(skip["reason"])}. Skipped: {_escape(skip["skipped"])}.</p>
            </div>
            """)
    if not cards:
        return '<div class="clean">No workflow skips detected.</div>'
    return '<div class="bottle-grid">' + "".join(cards) + "</div>"


def _summary(rows: list[dict]) -> str:
    completed = [row["completed_total"] for row in rows if row.get("completed_total") is not None]
    avg = sum(completed) / len(completed) if completed else None
    stats = [
        ("Total ROs", len(rows)),
        ("Workflow skips", sum(1 for row in rows if row["alerts"]["skips"])),
        ("Backwards moves", sum(1 for row in rows if row["alerts"]["backwards"])),
        ("Stage over 4h", sum(1 for row in rows if row["alerts"]["over4"])),
        ("Avg checkin -> finished", _duration_label(avg)),
        ("No packet", sum(1 for row in rows if not row["has_packet"])),
    ]
    return '<div class="stats">' + "".join(f'<div class="stat"><b>{_escape(value)}</b><span>{_escape(label)}</span></div>' for label, value in stats) + "</div>"


def render_timeline_page(window: str = "30", status_filter: str = "all", alert_filter: str = "all") -> str:
    if window not in {"7", "30", "all"}:
        window = "30"
    if status_filter not in {"all", "active", "completed"}:
        status_filter = "all"
    if alert_filter not in {"all", "flagged"}:
        alert_filter = "all"

    activity = _load_ro_activity()
    packets = _load_packet_ros()
    analyzed = [_analyze_ro(ro, events, packets) for ro, events in activity.items()]
    rows = _filter_rows(analyzed, window, status_filter, alert_filter)
    rows.sort(key=lambda row: row.get("latest") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    generated = _fmt_az(_now_utc().isoformat())

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="300">
  <title>RO Timeline | Callahan Auto</title>
  <style>
    :root{{--navy:#0f172a;--bg:#07111f;--panel:#0f1b2d;--card:#111f33;--line:#23364f;--txt:#fff;--mut:#94a3b8;--teal:#2dd4bf;--red:#ef4444;--orange:#f97316;--yellow:#eab308;--green:#22c55e}}
    *{{box-sizing:border-box}}
    body{{margin:0;background:radial-gradient(circle at top left,#172554 0%,#07111f 42%,#020617 100%);color:var(--txt);font-family:Inter,ui-sans-serif,system-ui,Arial,sans-serif;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}}
    .hero{{background:#0f172a;border-bottom:1px solid rgba(148,163,184,.24);padding:20px 24px}}
    h1{{margin:0;font-size:22px;font-weight:950;letter-spacing:.08em}}
    .sub{{color:#cbd5e1;font-size:12px;margin-top:6px;font-weight:800;letter-spacing:.04em}}
    main{{max-width:1540px;margin:0 auto;padding:22px 24px 60px}}
    .filters{{display:flex;gap:10px;flex-wrap:wrap;align-items:end;background:rgba(15,27,45,.84);border:1px solid var(--line);border-radius:14px;padding:14px;margin-bottom:18px}}
    label{{display:grid;gap:5px;color:#cbd5e1;font-size:11px;font-weight:900;text-transform:uppercase;letter-spacing:.08em}}
    select,button{{height:36px;border-radius:9px;border:1px solid #334155;background:#020617;color:#fff;padding:0 10px;font-weight:800}}
    button{{cursor:pointer;background:#0f766e;border-color:#14b8a6}}
    section{{background:rgba(15,27,45,.88);border:1px solid var(--line);border-radius:16px;padding:18px;margin-bottom:18px;box-shadow:0 16px 38px rgba(0,0,0,.24)}}
    h2{{margin:0 0 14px;font-size:16px;letter-spacing:.08em;text-transform:uppercase;color:#e2e8f0}}
    .stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px}}
    .stat{{background:#111f33;border:1px solid #2b405c;border-radius:13px;padding:14px}}
    .stat b{{display:block;font-size:25px;font-weight:950;color:#fff}}.stat span{{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:#94a3b8;margin-top:5px;font-weight:850}}
    table{{width:100%;border-collapse:collapse;font-size:13px}}th{{text-align:left;color:#94a3b8;background:#0b1626;font-size:11px;text-transform:uppercase;letter-spacing:.08em;padding:10px;border-bottom:1px solid #263954}}td{{padding:12px 10px;border-bottom:1px solid #1e2f49;vertical-align:top}}
    details summary{{cursor:pointer;font-weight:950;color:#fff}}.detail{{margin-top:12px;background:#07111f;border:1px solid #23364f;border-radius:12px;padding:12px;display:grid;gap:10px}}.detail h4{{margin:0 0 6px;color:#99f6e4}}.detail ul{{margin:0;padding-left:18px;color:#cbd5e1;line-height:1.55}}
    .stage-line{{display:flex;gap:7px;flex-wrap:wrap}}.stage{{display:inline-grid;gap:2px;border-radius:10px;padding:7px 9px;min-width:72px;text-align:center;border:1px solid transparent}}.stage b{{font-size:11px;text-transform:uppercase}}.stage small{{font-size:10px;font-weight:850}}
    .green{{background:rgba(34,197,94,.14);border-color:rgba(34,197,94,.45);color:#bbf7d0}}.yellow{{background:rgba(234,179,8,.14);border-color:rgba(234,179,8,.45);color:#fef08a}}.orange{{background:rgba(249,115,22,.15);border-color:rgba(249,115,22,.5);color:#fdba74}}.red{{background:rgba(239,68,68,.18);border-color:rgba(239,68,68,.56);color:#fecaca}}.darkred{{background:#7f1d1d;border-color:#ef4444;color:#fff}}.neutral{{background:#1e293b;border-color:#334155;color:#cbd5e1}}
    .alert-badge{{display:inline-flex;border-radius:999px;background:#7f1d1d;color:#fff;padding:4px 8px;font-size:11px;font-weight:900;margin:2px}}.muted{{color:#64748b}}.empty,.clean{{border:1px dashed #334155;border-radius:12px;padding:16px;text-align:center;color:#94a3b8;font-weight:800}}.clean{{background:rgba(34,197,94,.1);color:#86efac;border-color:rgba(34,197,94,.35)}}
    .bottle-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px}}.bottle-card,.skip-card{{background:#111f33;border:1px solid #334155;border-left:5px solid #ef4444;border-radius:13px;padding:13px}}.bottle-card b,.skip-card b{{display:block;font-size:16px}}.bottle-card span,.skip-card span{{display:block;color:#94a3b8;font-size:12px;margin:2px 0 8px}}.bottle-card strong,.skip-card strong{{color:#fca5a5}}.bottle-card p,.skip-card p{{color:#cbd5e1;line-height:1.45;margin:8px 0 0}}
    @media(max-width:900px){{main{{padding:14px}}table{{font-size:12px}}td,th{{padding:8px 6px}}}}
  </style>
</head>
<body>
  {render_nav("Timeline")}
  <header class="hero">
    <h1>RO STATUS TIMELINE &amp; BOTTLENECK REPORT</h1>
    <div class="sub">Generated {generated} &middot; Covers last 30 days &middot; Auto-refreshes every 5 minutes</div>
  </header>
  <main>
    <form class="filters" method="get" action="/timeline">
      <label>Time window {_select("window", window, [("7", "Last 7 days"), ("30", "Last 30 days"), ("all", "All time")])}</label>
      <label>Status filter {_select("status", status_filter, [("all", "All statuses"), ("active", "Active only"), ("completed", "Completed only")])}</label>
      <label>Alert filter {_select("alerts", alert_filter, [("all", "All ROs"), ("flagged", "Flagged only")])}</label>
      <button type="submit">Apply</button>
    </form>
    <section><h2>Shop Summary</h2>{_summary(rows)}</section>
    <section><h2>RO Timeline Table</h2>{_timeline_table(rows)}</section>
    <section><h2>Backwards Movement Log</h2>{_backwards_table(rows)}</section>
    <section><h2>Bottleneck Analysis</h2>{_bottleneck_cards(rows)}</section>
    <section><h2>Workflow Skip Alerts</h2>{_skip_cards(rows)}</section>
  </main>
</body>
</html>"""
