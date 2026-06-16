"""
DVI workflow lifecycle page.

This page is intentionally deterministic: it only reads local board/review/cache
state and never calls AutoFlow or AI while rendering.
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DVI_REVIEWS_DIR = ROOT / "state" / "dvi_reviews"

try:
    from board_loader import _load_board_state
except ImportError:  # pragma: no cover - supports package imports in tests
    from dashboard.board_loader import _load_board_state


STATUS_ALIASES = {
    "waiting_approval": "waiting approval",
    "waiting parts": "waiting parts",
    "waiting_parts": "waiting parts",
    "ordering_parts": "ordering parts",
    "call shop": "call_shop",
    "call-shop": "call_shop",
    "estimate": "advisor estimate",
    "est": "advisor estimate",
    "in progress": "servicing",
    "servicing / in progress": "servicing",
    "advisor_qc_review": "advisor qc review",
    "advisor_finalize_ro": "advisor finalize ro",
    "dvi only- not here": "dvi only-not here",
    "online /stage": "online/stage",
    "drop off/ tow-in": "drop off/tow-in",
    "closed": "close",
}

DONE_STATUSES = {"close", "finished"}
DONE_OTHER_STATUSES = {"ready", "advisor finalize ro"}
ADVISOR_QC_STATUSES = {"advisor qc review"}
IN_PROGRESS_STATUSES = {
    "servicing",
    "inspecting",
    "testing",
    "dvi updates",
    "ready for tech",
    "awaiting tech",
    "technical advisement",
    "technical overview",
    "k_mech_complete",
    "checkin",
    "qc",
    "drop off/tow-in",
    "online/stage",
    "waiting approval",
    "ordering parts",
    "waiting parts",
    "parts",
}

LANES = [
    {
        "key": "needs_rework",
        "title": "Needs Rework",
        "subtitle": "DVI failed gate and needs correction before packet/estimate work.",
        "tone": "immediate",
        "rgb": "255,59,48",
    },
    {
        "key": "ready_for_build_packet",
        "title": "Ready For Build Packet",
        "subtitle": "Clean/pre-work ROs that still need a packet built or refreshed.",
        "tone": "ai",
        "rgb": "168,85,247",
    },
    {
        "key": "tekmetric_ready",
        "title": "TekMetric Ready",
        "subtitle": "Packet exists and is current with the latest DVI snapshot.",
        "tone": "ready",
        "rgb": "34,197,94",
    },
    {
        "key": "in_progress",
        "title": "In Progress",
        "subtitle": "RO is still moving through production, parts, approval, or QC.",
        "tone": "progress",
        "rgb": "59,130,246",
    },
    {
        "key": "advisor_qc_review",
        "title": "Advisor QC Review",
        "subtitle": "Advisor needs to review documentation before closeout.",
        "tone": "customer",
        "rgb": "255,149,0",
    },
    {
        "key": "done",
        "title": "Recently Done",
        "subtitle": "Ready, finished, or closed ROs from the last 24 hours. Older packets live in History.",
        "tone": "done",
        "rgb": "34,197,94",
    },
]


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


def _time_ago(value: object) -> str:
    dt = _parse_dt(value)
    if not dt:
        return "unknown"
    delta = _now_utc() - dt
    seconds = max(0, int(delta.total_seconds()))
    minutes = seconds // 60
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h {minutes % 60}m ago"
    days = hours // 24
    return f"{days}d ago"


def _display_ts(value: object) -> str:
    dt = _parse_dt(value)
    if not dt:
        return "unknown"
    local = dt.astimezone(timezone(timedelta(hours=-7)))
    hour = local.hour % 12 or 12
    ampm = "AM" if local.hour < 12 else "PM"
    return f"{local.strftime('%b')} {local.day}, {hour}:{local.strftime('%M')} {ampm}"


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _normalize_ro_key(value: object) -> str:
    text = str(value or "").strip()
    if text.lower().startswith("ro"):
        text = text[2:].strip()
    return text


def _ro_id(value: dict) -> str:
    return _normalize_ro_key(
        value.get("ro")
        or value.get("invoice")
        or value.get("repair_order")
        or value.get("repair_order_id")
        or ""
    ).strip()


def _normalize_status(status: object) -> str:
    raw = str(status or "").lower().strip()
    raw = raw.replace("_", " ")
    raw = " ".join(raw.split())
    return STATUS_ALIASES.get(raw, raw)


def _load_jobs_by_ro() -> dict[str, dict]:
    jobs: dict[str, dict] = {}
    board_state = _load_board_state()
    live_jobs = board_state.get("jobs", []) if isinstance(board_state, dict) else []
    if not isinstance(live_jobs, list):
        return jobs

    for job in live_jobs:
        if not isinstance(job, dict):
            continue
        ro = _ro_id(job)
        if not ro:
            continue
        jobs[ro] = dict(job)
    return jobs


def _load_all_reviews() -> dict[str, dict]:
    reviews: dict[str, dict] = {}
    if not DVI_REVIEWS_DIR.exists():
        return reviews

    for path in DVI_REVIEWS_DIR.glob("*.json"):
        name = path.name.lower()
        if (
            name.startswith("packet_")
            or name.endswith("_packet.json")
            or name.startswith("rework_slip")
        ):
            continue
        review = _read_json(path)
        if not isinstance(review, dict):
            continue
        if "review_status" not in review:
            continue
        ro = _ro_id(review) or _normalize_ro_key(path.stem)
        if ro:
            reviews[ro] = review
    return reviews


def _packet_paths(ro: str) -> tuple[Path, Path]:
    return (
        DVI_REVIEWS_DIR / f"{ro}_packet.json",
        DVI_REVIEWS_DIR / f"packet_{ro}.json",
    )


def _latest_history_packet(ro: str) -> Path | None:
    history_dir = ROOT / "state" / "job_history" / ro
    if not history_dir.exists():
        return None
    packets = sorted(history_dir.glob("packet_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return packets[0] if packets else None


def _packet_status(ro: str) -> dict:
    cache_path, legacy_path = _packet_paths(ro)
    data = {}
    source = ""

    if cache_path.exists():
        data = _read_json(cache_path)
        source = "cache"
    elif legacy_path.exists():
        data = _read_json(legacy_path)
        source = "legacy"

    if not data:
        history = _latest_history_packet(ro)
        if history:
            return {
                "exists": True,
                "current": False,
                "stale": False,
                "state": "stored history",
                "generated_at": datetime.fromtimestamp(history.stat().st_mtime, tz=timezone.utc).isoformat(),
                "source": "history",
            }
        return {
            "exists": False,
            "current": False,
            "stale": False,
            "state": "no packet yet",
            "generated_at": "",
            "source": "",
        }

    packet = data.get("packet") if isinstance(data.get("packet"), dict) else data
    stale_info = data.get("packet_stale") or packet.get("packet_stale") or {}
    stale = stale_info.get("changed") is True
    hash_present = bool(data.get("dvi_snapshot_hash") or packet.get("dvi_snapshot_hash"))
    current = bool(hash_present and not stale)

    generated_at = (
        data.get("generated_at")
        or packet.get("generated_at")
        or data.get("fetched_at")
        or packet.get("fetched_at")
        or ""
    )

    if stale:
        state = "stale - regenerate"
    elif current:
        state = "current"
    else:
        state = "packet exists - currency unknown"

    return {
        "exists": True,
        "current": current,
        "stale": stale,
        "state": state,
        "generated_at": generated_at,
        "source": source,
    }


def _gate_ran_at(review: dict) -> str:
    return str(
        review.get("dvi_pulled_at")
        or review.get("gate_ran_at")
        or review.get("reviewed_at")
        or review.get("created_at")
        or review.get("timestamp")
        or ""
    )


def _review_resolved(review: dict) -> bool:
    return bool(
        review.get("advisor_acknowledged")
        or review.get("acknowledged")
        or review.get("resolved")
        or review.get("dvi_acknowledged")
    )


def _recent_done(record: dict) -> bool:
    candidates = [
        record.get("status_updated_at"),
        record.get("updated_at"),
        record.get("generated_at"),
        record.get("gate_ran_at"),
    ]
    for candidate in candidates:
        dt = _parse_dt(candidate)
        if dt:
            return (_now_utc() - dt) <= timedelta(hours=24)
    return True


def assign_dvi_lane(record: dict) -> str:
    """Assign a DVI workflow row to exactly one lifecycle lane."""
    status = _normalize_status(record.get("workflow_status"))
    review_status = str(record.get("review_status") or "").upper().strip()
    packet = record.get("packet_status") or {}

    if status in DONE_STATUSES:
        return "done"
    if review_status == "REWORK_REQUIRED" and not record.get("review_resolved"):
        return "needs_rework"
    if status in ADVISOR_QC_STATUSES:
        return "advisor_qc_review"
    if status in IN_PROGRESS_STATUSES:
        return "in_progress"
    if status in DONE_OTHER_STATUSES:
        return "done"
    if packet.get("current"):
        return "tekmetric_ready"
    return "ready_for_build_packet"


def _build_records() -> list[dict]:
    jobs = _load_jobs_by_ro()
    reviews = _load_all_reviews()
    all_ros = sorted(set(jobs) | set(reviews), key=lambda x: int(x) if x.isdigit() else x)
    records: list[dict] = []

    for ro in all_ros:
        job = jobs.get(ro, {})
        review = reviews.get(ro, {})
        is_live_job = ro in jobs
        workflow_status = (
            job.get("workflow_status")
            or job.get("status")
            or review.get("workflow_status")
            or "unknown"
        )
        if not is_live_job:
            workflow_status = "close"
        packet_status = _packet_status(ro)
        flags = review.get("flags") if isinstance(review.get("flags"), list) else []
        gate_ran_at = _gate_ran_at(review)
        review_status = str(review.get("review_status") or "NO_REVIEW").upper().strip()

        record = {
            "ro": ro,
            "customer": job.get("customer") or review.get("customer") or "Unknown Customer",
            "vehicle": job.get("vehicle") or review.get("vehicle") or "",
            "workflow_status": workflow_status,
            "normalized_status": _normalize_status(workflow_status),
            "is_live_job": is_live_job,
            "stale_review": not is_live_job and bool(review),
            "review_status": review_status,
            "review_resolved": _review_resolved(review),
            "advisor_acknowledged": bool(review.get("advisor_acknowledged")),
            "gate_ran_at": gate_ran_at,
            "flag_count": len(flags),
            "critical_count": sum(
                1 for flag in flags if str(flag.get("severity", "")).upper() in {"REWORK", "CRITICAL"}
            ),
            "packet_status": packet_status,
            "status_updated_at": job.get("status_updated_at") or job.get("last_updated_at") or "",
            "updated_at": job.get("updated_at") or "",
            "generated_at": job.get("generated_at") or "",
        }
        record["lane"] = assign_dvi_lane(record)
        records.append(record)

    return records


def _lane_records(records: list[dict]) -> dict[str, list[dict]]:
    lanes = {lane["key"]: [] for lane in LANES}
    seen: set[str] = set()
    for record in records:
        ro = record["ro"]
        if ro in seen:
            continue
        seen.add(ro)
        lane = record["lane"]
        if lane == "done" and not _recent_done(record):
            continue
        lanes.setdefault(lane, []).append(record)

    for lane_items in lanes.values():
        lane_items.sort(
            key=lambda r: (
                0 if r.get("review_status") == "REWORK_REQUIRED" else 1,
                0 if r.get("packet_status", {}).get("stale") else 1,
                r.get("ro", ""),
            )
        )
    return lanes


def _status_badge(review_status: str) -> str:
    status = str(review_status or "NO_REVIEW").upper()
    classes = {
        "PASS": "pass",
        "REVIEW": "review",
        "REWORK_REQUIRED": "rework",
        "NO_REVIEW": "none",
    }
    labels = {
        "PASS": "Gate Pass",
        "REVIEW": "Review",
        "REWORK_REQUIRED": "Rework Required",
        "NO_REVIEW": "No Gate Run",
    }
    cls = classes.get(status, "none")
    label = labels.get(status, status.replace("_", " ").title())
    return f'<span class="badge {cls}">{html.escape(label)}</span>'


def _packet_badge(packet: dict) -> str:
    state = packet.get("state", "no packet yet")
    if packet.get("stale"):
        cls = "packet-stale"
    elif packet.get("current"):
        cls = "packet-ready"
    elif packet.get("exists"):
        cls = "packet-unknown"
    else:
        cls = "packet-missing"
    return f'<span class="packet {cls}">{html.escape(state)}</span>'


def _packet_action(ro: str, packet: dict) -> str:
    if packet.get("exists"):
        href = f"/dvi/packet/{html.escape(ro)}/stored"
        label = "Open Stored Packet"
    else:
        href = f"/dvi/packet/{html.escape(ro)}"
        label = "Build Packet"
    return f'<a class="action-link" href="{href}">{label}</a>'


def _card_actions(record: dict) -> str:
    ro = html.escape(record["ro"])
    actions = []
    if record.get("lane") == "needs_rework":
        actions.append(
            f'<form class="inline-form" method="post" action="/dvi/rerun/{ro}">'
            '<button class="action-link rerun" type="submit">Re-run Gate</button>'
            '</form>'
        )
        slip_path = DVI_REVIEWS_DIR / f"rework_slip_{record['ro']}.html"
        if slip_path.exists():
            actions.append(f'<a class="action-link secondary" href="/dvi/slip/{ro}" target="_blank">Print Slip</a>')
        actions.append(f'<a class="action-link secondary" href="/dvi/acknowledge/{ro}">Acknowledge</a>')
    actions.append(_packet_action(ro, record.get("packet_status", {})))
    return "\n".join(actions)


def _headline(record: dict) -> str:
    lane = record.get("lane")
    packet = record.get("packet_status", {})
    if lane == "needs_rework":
        return "DVI REWORK REQUIRED"
    if lane == "ready_for_build_packet":
        return "BUILD PACKET"
    if lane == "tekmetric_ready":
        return "TEKMETRIC READY"
    if lane == "in_progress":
        return "DVI IN PRODUCTION FLOW"
    if lane == "advisor_qc_review":
        return "ADVISOR QC REVIEW"
    if packet.get("stale"):
        return "STALE - REGENERATE"
    return "DONE / ARCHIVED"


def _render_card(record: dict, lane: dict, pulse_offset: int | None = None) -> str:
    ro = html.escape(record["ro"])
    packet = record.get("packet_status", {})
    is_stale = packet.get("stale") is True
    urgent = record.get("lane") == "needs_rework" or is_stale
    pulse_class = ""
    beacon = ""
    if urgent:
        pulse_class = "p1" if record.get("lane") == "needs_rework" else "stale"
        pulse_class += f" pulse-offset-{pulse_offset or 0}"
        beacon = '<span class="beacon-dot"></span>'

    gate_value = record.get("gate_ran_at")
    packet_time = packet.get("generated_at")
    status_text = html.escape(str(record.get("workflow_status") or "unknown"))
    gate_text = html.escape(_display_ts(gate_value))
    packet_time_text = html.escape(_time_ago(packet_time))
    return f"""
      <article class="card lane-{lane['tone']} {pulse_class}" style="--rgb:{lane['rgb']}">
        <div class="card-top">
          <div>
            <div class="ro">RO{ro}{beacon}</div>
          </div>
          {_status_badge(record.get("review_status"))}
        </div>
        <div class="cust">{html.escape(str(record.get("customer") or "Unknown Customer"))}</div>
        <div class="veh">{html.escape(str(record.get("vehicle") or ""))}</div>
        <div class="act" style="color:rgb({lane['rgb']})">{html.escape(_headline(record))}</div>
        <div class="pill-row">
          <span class="pill" style="color:rgb({lane['rgb']})">STATUS {status_text}</span>
          <span class="pill">GATE {gate_text}</span>
          {_packet_badge(packet)}
          <span class="time-badge" style="color:rgb({lane['rgb']})">PACKET {packet_time_text}</span>
        </div>
        <div class="card-foot">
          <span>{int(record.get("flag_count") or 0)} flags / {int(record.get("critical_count") or 0)} critical</span>
          <div class="actions">
            {_card_actions(record)}
          </div>
        </div>
      </article>
    """


def _render_lane(lane: dict, records: list[dict]) -> str:
    pulse_index = 0
    rendered_cards = []
    for record in records:
        offset = None
        if record.get("lane") == "needs_rework" or record.get("packet_status", {}).get("stale") is True:
            offset = pulse_index % 4
            pulse_index += 1
        rendered_cards.append(_render_card(record, lane, offset))
    cards = "\n".join(rendered_cards)
    if not cards:
        cards = '<div class="empty">Nothing here right now.</div>'
    return f"""
      <section class="col" style="--rgb:{lane['rgb']}">
        <div class="col-head {lane['tone']}">
          <div class="lane-left">
            <span class="lane-title">{html.escape(lane['title'])}<span class="lane-subtitle">{html.escape(lane['subtitle'])}</span></span>
          </div>
          <span class="count">{len(records)}</span>
        </div>
        {cards}
      </section>
    """


def render_dvi_page() -> str:
    records = _build_records()
    lanes = _lane_records(records)
    active_count = sum(len(lanes[lane["key"]]) for lane in LANES if lane["key"] != "done")
    done_count = len(lanes.get("done", []))
    duplicate_count = len(records) - len({record["ro"] for record in records})
    generated_at = _display_ts(_now_utc().isoformat())

    lane_html = "\n".join(_render_lane(lane, lanes.get(lane["key"], [])) for lane in LANES)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DVI Workflow | Callahan Auto</title>
  <style>
    :root {{
      --bg-main:#050816;--bg-card:#0F172A;--bg-panel:#0B1220;--border-soft:#1E293B;--border-medium:#334155;
      --text-primary:#FFFFFF;--text-secondary:#CBD5E1;--text-muted:#94A3B8;--text-faint:#64748B;
      --status-immediate:#FF3B30;--status-immediate-bg:rgba(255,59,48,0.12);--status-immediate-border:rgba(255,59,48,0.75);--status-immediate-glow:rgba(255,59,48,0.48);
      --status-customer:#FF9500;--status-customer-bg:rgba(255,149,0,0.12);--status-customer-border:rgba(255,149,0,0.70);--status-customer-glow:rgba(255,149,0,0.40);
      --status-progress:#3B82F6;--status-progress-bg:rgba(59,130,246,0.12);--status-progress-border:rgba(59,130,246,0.65);
      --status-ready:#22C55E;--status-ready-bg:rgba(34,197,94,0.13);--status-ready-border:rgba(34,197,94,0.68);
      --status-parts:#00E5FF;--status-parts-bg:rgba(0,229,255,0.12);--status-parts-border:rgba(0,229,255,0.68);
      --status-ai:#A855F7;--status-ai-bg:rgba(168,85,247,0.14);--status-ai-border:rgba(168,85,247,0.72);--status-ai-glow:rgba(168,85,247,0.45);
      --p1-bg:#FF2D2D;--p2-bg:#FF7A00;--p3-bg:#FFD400;--p3-text:#111827;
    }}
    *{{box-sizing:border-box}}html,body{{min-height:100%}}
    body{{margin:0;background:radial-gradient(circle at top left,#111B3A 0%,#050816 38%,#020617 100%);color:#FFFFFF;font-family:Inter,ui-sans-serif,system-ui,sans-serif;-webkit-font-smoothing:antialiased;overflow:hidden}}
    header{{height:86px;padding:12px 16px;border-bottom:1px solid var(--border-soft);background:rgba(2,6,23,.72);display:grid;grid-template-columns:1fr auto;gap:14px;align-items:center}}
    .top-row{{display:flex;justify-content:space-between;gap:18px;align-items:center;min-width:0}}
    h1{{margin:0;font-size:24px;font-weight:950;letter-spacing:.06em;text-transform:uppercase;color:#fff}}
    .sub{{color:var(--text-faint);margin-top:4px;font-size:11px;font-weight:700;letter-spacing:.04em}}
    .nav{{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}}
    .nav a{{height:28px;border-radius:7px;border:1px solid var(--border-medium);background:rgba(15,23,42,.75);color:var(--text-muted);font-size:10px;font-weight:900;padding:7px 10px;text-decoration:none;display:inline-flex;align-items:center}}
    .nav a:hover{{background:var(--border-soft);color:#fff}}
    .stats{{display:flex;gap:8px;grid-column:1/-1;margin-top:-4px}}
    .stat{{min-width:120px;height:38px;border:1px solid var(--border-soft);background:rgba(15,23,42,.68);border-radius:10px;padding:6px 10px;display:flex;align-items:center;gap:8px;box-shadow:inset 0 1px 0 rgba(255,255,255,.06)}}
    .stat b{{font-size:22px;line-height:1;color:#38BDF8;font-weight:950}}
    .stat span{{color:var(--text-faint);font-size:9px;text-transform:uppercase;letter-spacing:.08em;font-weight:900}}
    main.pipeline{{height:calc(100vh - 86px);display:grid;grid-template-columns:repeat(6,minmax(210px,1fr));gap:10px;padding:10px;overflow:hidden}}
    .col{{min-width:0;background:rgba(15,23,42,.62);border:1px solid var(--border-soft);border-radius:16px;padding:9px;overflow-y:auto;box-shadow:inset 0 1px 0 rgba(255,255,255,.035)}}
    .col-head{{min-height:58px;border-radius:12px;padding:10px 10px;margin-bottom:10px;display:flex;justify-content:space-between;align-items:flex-start;border:1px solid rgba(var(--rgb),.62);box-shadow:0 0 22px rgba(var(--rgb),.18),inset 0 1px 0 rgba(255,255,255,.08)}}
    .col-head.immediate{{background:linear-gradient(90deg,rgba(255,59,48,.22),rgba(255,59,48,.06))}}
    .col-head.ai{{background:linear-gradient(90deg,rgba(168,85,247,.21),rgba(168,85,247,.055))}}
    .col-head.ready{{background:linear-gradient(90deg,rgba(34,197,94,.18),rgba(34,197,94,.05))}}
    .col-head.progress{{background:linear-gradient(90deg,rgba(59,130,246,.18),rgba(59,130,246,.05))}}
    .col-head.customer{{background:linear-gradient(90deg,rgba(255,149,0,.20),rgba(255,149,0,.055))}}
    .col-head.done{{background:linear-gradient(90deg,rgba(34,197,94,.10),rgba(100,116,139,.045));opacity:.78}}
    .lane-title{{font-size:12px;font-weight:950;line-height:1.1;text-transform:uppercase;letter-spacing:.05em;color:#fff}}
    .lane-subtitle{{display:block;margin-top:4px;font-size:9px;font-weight:800;letter-spacing:.04em;line-height:1.18;color:rgba(203,213,225,.64);text-transform:none}}
    .count{{display:grid;place-items:center;min-width:28px;height:26px;border-radius:999px;background:rgba(255,255,255,.11);font-size:12px;font-weight:950;color:#fff}}
    .card{{position:relative;overflow:hidden;background:linear-gradient(180deg,rgba(15,23,42,.98),rgba(7,12,24,.96));border:1px solid rgba(var(--rgb),.70);border-radius:14px;padding:10px 10px 11px 13px;margin-bottom:9px;box-shadow:inset 0 1px 0 rgba(255,255,255,.06),0 10px 22px rgba(0,0,0,.24)}}
    .card:before{{content:"";position:absolute;inset:0;pointer-events:none;opacity:.14;background:radial-gradient(circle at 10% 0%,rgba(var(--rgb),.42),transparent 44%),linear-gradient(90deg,rgba(var(--rgb),.55) 0%,transparent 42%)}}
    .card:after{{content:"";position:absolute;left:0;top:0;bottom:0;width:5px;border-radius:14px 0 0 14px;background:rgb(var(--rgb));box-shadow:0 0 20px rgba(var(--rgb),.60)}}
    .card>*{{position:relative;z-index:1}}
    .card-top{{display:flex;justify-content:space-between;align-items:flex-start;gap:8px}}
    .ro{{font-size:16px;font-weight:1000;line-height:1;color:#fff;letter-spacing:.02em}}
    .cust{{font-size:11px;font-weight:900;color:#E2E8F0;margin-top:8px;line-height:1.2;text-transform:uppercase}}
    .veh{{font-size:10px;font-weight:700;color:var(--text-muted);margin-top:3px;line-height:1.2}}
    .act{{margin-top:10px;font-size:15px;font-weight:1000;letter-spacing:.06em;line-height:1.08;text-transform:uppercase;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;min-height:32px;overflow:hidden}}
    .pill-row{{display:flex;flex-wrap:wrap;gap:5px;margin-top:9px}}
    .badge, .packet {{
      display:inline-flex;
      align-items:center;
      border-radius:999px;
      padding:4px 6px;
      font-size:8px;
      font-weight:900;
      text-transform:uppercase;
      letter-spacing:.045em;
      white-space:nowrap;
    }}
    .badge.pass, .packet-ready {{ color:#bbf7d0; border:1px solid rgba(34,197,94,.55); background:rgba(34,197,94,.13); }}
    .badge.review, .packet-unknown {{ color:#fde68a; border:1px solid rgba(245,158,11,.55); background:rgba(245,158,11,.12); }}
    .badge.rework, .packet-stale {{ color:#fecaca; border:1px solid rgba(239,68,68,.6); background:rgba(239,68,68,.14); }}
    .badge.none, .packet-missing {{ color:#cbd5e1; border:1px solid rgba(148,163,184,.35); background:rgba(148,163,184,.10); }}
    .pill,.time-badge{{display:inline-flex;align-items:center;border-radius:999px;border:1px solid rgba(148,163,184,.20);background:rgba(2,6,23,.34);padding:4px 6px;font-size:8px;font-weight:950;letter-spacing:.045em;text-transform:uppercase;color:#CBD5E1;max-width:100%;overflow:hidden;text-overflow:ellipsis}}
    .card-foot{{display:flex;flex-direction:column;gap:8px;margin-top:10px;color:var(--text-faint);font-size:10px;font-weight:800}}
    .actions{{display:flex;gap:5px;flex-wrap:wrap}}
    .inline-form{{display:inline;margin:0}}
    .action-link{{border:1px solid rgba(var(--rgb),.48);background:linear-gradient(180deg,rgba(15,23,42,.94),rgba(30,41,59,.76));box-shadow:inset 0 1px 0 rgba(255,255,255,.10);color:#fff;border-radius:7px;padding:5px 7px;font-size:9px;font-weight:950;text-decoration:none;cursor:pointer;font-family:inherit}}
    .action-link.secondary{{border-color:rgba(168,85,247,.38);color:#d8b4fe}}
    .action-link.rerun{{border-color:rgba(255,59,48,.62);color:#fecaca}}
    .empty{{color:var(--text-faint);border:1px dashed rgba(148,163,184,.20);border-radius:14px;padding:18px 10px;text-align:center;font-size:11px;font-weight:800;background:rgba(2,6,23,.22)}}
    .card.p1,.card.stale{{animation:cardBeaconPulse 2.8s ease-in-out infinite}}
    .card.p1:before,.card.stale:before{{opacity:.20;background:radial-gradient(circle at 16% 8%,rgba(255,59,48,.36),transparent 44%),linear-gradient(90deg,rgba(255,59,48,.70) 0%,transparent 45%)}}
    .card.p1.pulse-offset-0,.card.stale.pulse-offset-0{{animation-delay:0s}}
    .card.p1.pulse-offset-1,.card.stale.pulse-offset-1{{animation-delay:.65s}}
    .card.p1.pulse-offset-2,.card.stale.pulse-offset-2{{animation-delay:1.3s}}
    .card.p1.pulse-offset-3,.card.stale.pulse-offset-3{{animation-delay:1.95s}}
    @keyframes cardBeaconPulse{{0%,100%{{box-shadow:0 0 0 1px rgba(255,59,48,.75),0 0 14px rgba(255,59,48,.45),inset 0 0 12px rgba(255,59,48,.10)}}45%{{box-shadow:0 0 0 3px rgba(255,59,48,.95),0 0 22px rgba(255,59,48,.70),inset 0 0 20px rgba(255,59,48,.18)}}}}
    .beacon-dot{{width:9px;height:9px;border-radius:999px;background:#FF3B30;box-shadow:0 0 10px rgba(255,59,48,.85);animation:beaconDotPulse 1.4s ease-in-out infinite;display:inline-block;margin-left:8px;vertical-align:middle}}
    @keyframes beaconDotPulse{{0%,100%{{transform:scale(.85);opacity:.65}}50%{{transform:scale(1.35);opacity:1}}}}
    @media (prefers-reduced-motion: reduce){{.card.p1,.card.stale,.beacon-dot{{animation:none!important}}}}
    @media (max-width: 1300px){{main.pipeline{{overflow-x:auto;grid-template-columns:repeat(6,minmax(230px,250px))}}}}
    @media (max-width: 760px){{body{{overflow:auto}}header{{height:auto;display:block}}.top-row{{display:block}}.nav{{justify-content:flex-start;margin-top:10px}}.stats{{flex-wrap:wrap;margin-top:10px}}main.pipeline{{height:auto;display:block;overflow:visible}}.col{{margin:10px 0;max-height:none}}}}
  </style>
</head>
<body>
  <header>
    <div class="top-row">
      <div>
        <h1>DVI Workflow</h1>
        <div class="sub">Lifecycle lanes from workflow status, DVI gate result, and packet cache state. Generated {html.escape(generated_at)}.</div>
      </div>
      <nav class="nav">
        <a href="/v2">Command Board</a>
        <a href="/dvi/history">Packet History</a>
        <a href="/sanity-check">Sanity Check</a>
      </nav>
    </div>
    <div class="stats">
      <div class="stat"><b>{len(records)}</b><span>Total DVI Rows</span></div>
      <div class="stat"><b>{active_count}</b><span>Active Lanes</span></div>
      <div class="stat"><b>{done_count}</b><span>Recently Done</span></div>
      <div class="stat"><b>{duplicate_count}</b><span>Duplicate Listings</span></div>
    </div>
  </header>
  <main class="pipeline">
    {lane_html}
  </main>
</body>
</html>"""
