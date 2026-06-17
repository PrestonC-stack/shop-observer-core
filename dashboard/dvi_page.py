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
            "flags": flags,
            "flag_count": len(flags),
            "critical_count": sum(
                1 for flag in flags if str(flag.get("severity", "")).upper() in {"REWORK", "CRITICAL"}
            ),
            "packet_status": packet_status,
            "status_updated_at": job.get("status_updated_at") or job.get("last_updated_at") or "",
            "updated_at": job.get("updated_at") or "",
            "generated_at": job.get("generated_at") or "",
            "priority_lane": job.get("priority_lane") or job.get("priority") or "P4",
            "risk_level": job.get("risk_level") or "",
            "waiting_on": job.get("waiting_on") or review.get("advisor") or "",
            "technician": job.get("technician") or job.get("assigned_technician") or review.get("technician") or "",
            "hermes_next_action": job.get("hermes_next_action") or "",
            "next_action": job.get("next_action") or "",
            "hours_in_status": job.get("hours_in_status"),
            "stale": job.get("stale") is True,
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


def _priority(record: dict) -> str:
    if record.get("lane") == "done":
        return "P4"
    if _is_rework(record):
        return "P1"
    if record.get("lane") == "ready_for_build_packet":
        return "P2"
    if _is_stale_24(record):
        return "P1"
    raw = str(record.get("priority_lane") or record.get("priority") or "P4").upper().strip()
    if raw.startswith("P2"):
        return "P2"
    return raw if raw in {"P1", "P2", "P3", "P4"} else "P4"


def _is_p1(record: dict) -> bool:
    if record.get("lane") == "done":
        return False
    if _is_rework(record):
        return True
    if record.get("lane") == "ready_for_build_packet":
        return False
    if _is_stale_24(record):
        return True
    return _priority(record) == "P1" or str(record.get("risk_level") or "").upper() == "CRITICAL"


def _status_age_hours(record: dict) -> float | None:
    if record.get("lane") == "done":
        return None
    raw_hours = record.get("hours_in_status")
    try:
        if raw_hours not in (None, ""):
            hours = max(0.0, float(raw_hours))
            if hours >= 900:
                return None
            return hours
    except Exception:
        pass
    for key in ("status_updated_at", "updated_at", "generated_at"):
        dt = _parse_dt(record.get(key))
        if dt:
            return max(0.0, (_now_utc() - dt).total_seconds() / 3600)
    return None


def _is_stale_24(record: dict) -> bool:
    if record.get("lane") == "done":
        return False
    if record.get("stale") is True:
        return True
    hours = _status_age_hours(record)
    return bool(hours is not None and hours >= 24)


def _hours_label(record: dict) -> str:
    if record.get("lane") == "done":
        done_time = None
        for key in ("status_updated_at", "updated_at", "generated_at", "gate_ran_at"):
            done_time = _parse_dt(record.get(key))
            if done_time:
                break
        if not done_time:
            return "closed"
        hours = max(0.0, (_now_utc() - done_time).total_seconds() / 3600)
        if hours >= 24:
            return f"closed {int(hours // 24)}d {int(hours % 24)}h ago"
        if hours >= 1:
            return f"closed {int(hours)}h ago"
        return f"closed {int(hours * 60)}m ago"
    hours = _status_age_hours(record)
    if hours is None:
        return "timing unknown"
    if hours >= 24:
        return f"stale {int(hours // 24)}d {int(hours % 24)}h"
    if hours >= 1:
        return f"{int(hours)}h"
    return f"{int(hours * 60)}m"


def _is_rework(record: dict) -> bool:
    return (
        str(record.get("review_status") or "").upper().strip() == "REWORK_REQUIRED"
        and not record.get("review_resolved")
    )


def _flag_gap(record: dict) -> str:
    flags = record.get("flags") if isinstance(record.get("flags"), list) else []
    ordered = sorted(
        [flag for flag in flags if isinstance(flag, dict)],
        key=lambda flag: 0 if str(flag.get("severity", "")).lower() in {"critical", "rework"} else 1,
    )
    if not ordered:
        return "DVI needs correction"
    flag = ordered[0]
    text = str(flag.get("recommended_action") or flag.get("message") or flag.get("item_name") or "DVI needs correction")
    text = " ".join(text.replace("\n", " ").split())
    return text[:80]


def _tech_name(record: dict) -> str:
    raw = str(record.get("technician") or "").strip()
    if not raw or raw.lower() in {"unknown", "none", "n/a"}:
        return "TECH"
    return raw.split()[0].upper()


def _directive(record: dict) -> str:
    lane = record.get("lane")
    status = _normalize_status(record.get("workflow_status"))
    if _is_rework(record):
        return f"SEND BACK TO {_tech_name(record)} - {_flag_gap(record)}"
    if lane == "ready_for_build_packet":
        return "BUILD PACKET"
    if lane == "tekmetric_ready":
        return "PUSH TO TEKMETRIC"
    if lane == "advisor_qc_review":
        return "REVIEW & FINALIZE"
    if lane == "in_progress":
        if status in {"waiting parts", "ordering parts", "parts"}:
            return "PARTS NOT IN YET - HOLD"
        if status in {"awaiting tech", "ready for tech"}:
            return "WAITING ON TECH"
        if status == "waiting approval":
            return "WAITING ON CUSTOMER"
        if status in {"testing", "dvi updates", "inspecting"}:
            return "WAITING ON TECH - DVI FLOW"
        return str(record.get("hermes_next_action") or record.get("next_action") or "WATCH PRODUCTION").upper()
    if lane == "done":
        return "CLOSED - OPEN HISTORY IF NEEDED"
    return str(record.get("hermes_next_action") or record.get("next_action") or "REVIEW JOB").upper()


def _card_href(record: dict) -> str:
    ro = html.escape(str(record.get("ro") or ""))
    packet = record.get("packet_status", {})
    if packet.get("exists"):
        return f"/dvi/packet/{ro}/stored"
    if record.get("lane") == "done":
        return "/dvi/history"
    return f"/dvi/packet/{ro}"


def _action_button(record: dict) -> str:
    ro = html.escape(str(record.get("ro") or ""))
    lane = record.get("lane")
    packet = record.get("packet_status", {})
    if _is_rework(record):
        return (
            f'<form class="inline-form" method="post" action="/dvi/rerun/{ro}">'
            '<button class="do-btn red" type="submit">Re-run Gate</button>'
            '</form>'
        )
    if lane == "ready_for_build_packet":
        return f'<a class="do-btn purple" href="/dvi/packet/{ro}">Build Packet</a>'
    if lane == "tekmetric_ready" or packet.get("exists"):
        return f'<a class="do-btn green" href="{_card_href(record)}">Open Packet</a>'
    if lane == "advisor_qc_review":
        return f'<a class="do-btn orange" href="{_card_href(record)}">Review</a>'
    if lane == "done":
        return '<a class="do-btn green" href="/dvi/history">Open History</a>'
    return f'<a class="do-btn blue" href="{_card_href(record)}">Open</a>'


def _stage_meta(record: dict) -> tuple[str, str]:
    lane = record.get("lane")
    packet = record.get("packet_status", {})
    status = _normalize_status(record.get("workflow_status"))
    if _is_rework(record):
        return "Tech", f"{record.get('flag_count', 0)} failed checks"
    if lane == "ready_for_build_packet":
        return "Advisor", "DVI clean"
    if lane == "tekmetric_ready":
        return "Advisor", "Packet current" if packet.get("current") else str(packet.get("state") or "Packet ready")
    if lane == "advisor_qc_review":
        return "Advisor", "Tech QC done"
    if status in {"waiting parts", "ordering parts", "parts"}:
        return "Parts", status.title()
    if lane == "done":
        return "History", _hours_label(record)
    return "Tech", status.title() if status else "In progress"


def _do_now(record: dict) -> bool:
    if record.get("lane") == "done":
        return False
    if _is_rework(record):
        return True
    if record.get("lane") == "ready_for_build_packet":
        return False
    return _is_stale_24(record) or _is_p1(record)


def _last_updated_sort_value(record: dict) -> float:
    for key in ("status_updated_at", "updated_at", "generated_at", "gate_ran_at"):
        dt = _parse_dt(record.get(key))
        if dt:
            return dt.timestamp()
    ro = str(record.get("ro") or "")
    try:
        return float(ro)
    except Exception:
        return 0.0


def _ro_sort_value(record: dict) -> int:
    try:
        return int(str(record.get("ro") or "0"))
    except Exception:
        return 999999


def _urgency_rank(record: dict) -> tuple:
    priority = _priority(record)
    lane = record.get("lane")
    stale = _is_stale_24(record)
    if _is_rework(record):
        bucket = 0 if priority == "P1" else 1 if priority == "P2" else 2 if stale else 3
    elif lane == "ready_for_build_packet":
        bucket = 4 if priority in {"P1", "P2"} else 5
    elif lane == "tekmetric_ready":
        bucket = 6 if priority in {"P1", "P2"} else 7
    elif lane == "in_progress":
        bucket = 8
    elif lane == "advisor_qc_review":
        bucket = 9
    elif lane == "done":
        bucket = 10
    else:
        bucket = 11
    return (bucket, 0 if stale else 1, _last_updated_sort_value(record), _ro_sort_value(record))


def _queue_sections(records: list[dict]) -> tuple[list[dict], dict[str, list[dict]]]:
    seen: set[str] = set()
    do_now = []
    stages = {lane["key"]: [] for lane in LANES if lane["key"] != "needs_rework"}
    for record in sorted(records, key=_urgency_rank):
        ro = str(record.get("ro") or "")
        if ro in seen:
            continue
        seen.add(ro)
        if _do_now(record):
            do_now.append(record)
            continue
        lane = record.get("lane")
        if lane == "needs_rework":
            do_now.append(record)
        elif lane in stages:
            stages[lane].append(record)
    for lane_key in stages:
        stages[lane_key].sort(key=_urgency_rank)
    return do_now, stages


def _render_divider(title: str, count: int, rgb: str) -> str:
    return f"""
    <div class="divider" style="--c:{rgb}">
      <span class="dline l"></span>
      <span class="dtitle">{html.escape(title)} <span class="cnt">{count}</span></span>
      <span class="dline r"></span>
    </div>
    """


def _priority_badge(record: dict) -> str:
    priority = _priority(record)
    return f'<span class="pri {priority}">{priority}</span>'


def _render_meta(record: dict, include_gate: bool = True) -> str:
    owner, detail = _stage_meta(record)
    parts = [
        _priority_badge(record),
        f'<span class="pill muted">{html.escape(owner)}</span>',
        f'<span class="pill muted">{html.escape(detail)}</span>',
    ]
    if _is_stale_24(record):
        parts.insert(1, f'<span class="pill stale-pill">{html.escape(_hours_label(record))}</span>')
    if include_gate:
        parts.append(f'<span class="pill muted">Gate {html.escape(_time_ago(record.get("gate_ran_at")))}</span>')
    parts.append(_action_button(record))
    return '<div class="meta">' + "".join(parts) + "</div>"


def _render_do_now(records: list[dict]) -> str:
    if not records:
        return '<div class="empty-wide">No immediate DVI action right now.</div>'
    cards = []
    for index, record in enumerate(records):
        ro = html.escape(str(record.get("ro") or ""))
        href = html.escape(_card_href(record))
        vehicle = f"{record.get('customer') or 'Unknown'} · {record.get('vehicle') or ''}".strip(" ·")
        cards.append(f"""
        <article class="screamer po{index % 3}" onclick="if(!event.target.closest('a,button,form')) window.location='{href}'">
          <div class="ro-line"><span class="ro">RO {ro}</span><span class="beacon"></span><span class="veh">{html.escape(vehicle)}</span></div>
          <div class="directive">{html.escape(_directive(record))}</div>
          {_render_meta(record)}
        </article>
        """)
    return '<div class="donow">' + "\n".join(cards) + "</div>"


def _render_stage_card(record: dict, rgb: str) -> str:
    ro = html.escape(str(record.get("ro") or ""))
    href = html.escape(_card_href(record))
    vehicle = f"{record.get('customer') or 'Unknown'} · {record.get('vehicle') or ''}".strip(" ·")
    opacity = "opacity:.72;" if record.get("lane") == "done" else ""
    return f"""
    <article class="row" style="--rgb:{rgb};{opacity}" onclick="if(!event.target.closest('a,button,form')) window.location='{href}'">
      <div class="ro-line"><span class="ro">RO {ro}</span><span class="veh">{html.escape(vehicle)}</span></div>
      <div class="directive">{html.escape(_directive(record))}</div>
      {_render_meta(record)}
    </article>
    """


def _render_stage(title: str, records: list[dict], rgb: str) -> str:
    body = (
        '<div class="rows">' + "\n".join(_render_stage_card(record, rgb) for record in records) + "</div>"
        if records else '<div class="empty-wide">Nothing queued in this stage.</div>'
    )
    return _render_divider(title, len(records), rgb) + body


def render_dvi_page() -> str:
    records = _build_records()
    do_now, stages = _queue_sections(records)
    rework_count = sum(1 for record in records if _is_rework(record))
    stale_count = sum(1 for record in records if _is_stale_24(record))
    parts_held = sum(
        1 for record in records
        if _normalize_status(record.get("workflow_status")) in {"waiting parts", "ordering parts", "parts"}
    )
    in_progress_count = len(stages.get("in_progress", []))
    done_count = len(stages.get("done", []))
    duplicate_count = len(records) - len({record["ro"] for record in records})
    generated_at = _display_ts(_now_utc().isoformat())

    stage_html = "\n".join([
        _render_stage("Ready for Build Packet", stages.get("ready_for_build_packet", []), "168,85,247"),
        _render_stage("TekMetric Ready", stages.get("tekmetric_ready", []), "34,197,94"),
        _render_stage("In Progress", stages.get("in_progress", []), "59,130,246"),
        _render_stage("Advisor QC Review", stages.get("advisor_qc_review", []), "255,149,0"),
        _render_stage("Recently Done", stages.get("done", []), "34,197,94"),
    ])

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DVI Workflow | Callahan Auto</title>
  <style>
    :root{{--bg:#050816;--card:#0F172A;--soft:#1E293B;--med:#334155;--txt:#fff;--txt2:#CBD5E1;--mut:#94A3B8;--faint:#64748B;--status-immediate:#FF3B30;--status-customer:#FF9500;--status-progress:#3B82F6;--status-ready:#22C55E;--status-parts:#00E5FF;--status-ai:#A855F7}}
    *{{box-sizing:border-box}}
    body{{margin:0;font-family:Inter,ui-sans-serif,system-ui,Arial,sans-serif;background:radial-gradient(circle at top left,#111B3A 0%,#050816 40%,#020617 100%);color:var(--txt);-webkit-font-smoothing:antialiased;padding:22px 26px 60px}}
    .top{{display:flex;justify-content:space-between;align-items:center;gap:16px;border-bottom:1px solid var(--soft);padding-bottom:16px;margin-bottom:8px;flex-wrap:wrap}}
    .title{{font-size:22px;font-weight:900;letter-spacing:.06em}}
    .title small{{display:block;font-size:10px;font-weight:800;letter-spacing:.18em;color:#A855F7;text-transform:uppercase;margin-top:5px;text-shadow:0 0 12px rgba(168,85,247,.6)}}
    .stats{{display:flex;gap:9px;flex-wrap:wrap}}
    .stat{{min-width:78px;height:50px;background:linear-gradient(180deg,rgba(15,23,42,.96),rgba(2,6,23,.9));border:1px solid #263954;border-radius:11px;display:flex;flex-direction:column;align-items:center;justify-content:center}}
    .stat b{{font-size:22px;font-weight:900;line-height:1;text-shadow:0 0 14px currentColor}}
    .stat span{{font-size:8.5px;font-weight:800;letter-spacing:.07em;text-transform:uppercase;color:var(--faint);margin-top:4px}}
    .ctrls{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}}
    .btn{{height:32px;border-radius:8px;border:1px solid var(--med);background:rgba(15,23,42,.85);color:var(--txt2);font-size:11px;font-weight:800;padding:8px 12px;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center}}
    .btn.live{{border-color:rgba(168,85,247,.7);color:#C084FC;box-shadow:0 0 16px rgba(168,85,247,.25)}}
    .divider{{display:flex;align-items:center;gap:16px;margin:34px 0 16px}}
    .dline{{flex:1;height:2px;border-radius:2px}}
    .dline.l{{background:linear-gradient(90deg,transparent,rgba(var(--c),.55))}}
    .dline.r{{background:linear-gradient(90deg,rgba(var(--c),.55),transparent)}}
    .dtitle{{font-size:15px;font-weight:900;letter-spacing:.16em;text-transform:uppercase;color:rgb(var(--c));text-shadow:0 0 16px rgba(var(--c),.55);white-space:nowrap;display:flex;align-items:center;gap:11px;text-align:center}}
    .cnt{{font-size:12px;font-weight:900;background:rgba(var(--c),.18);border:1px solid rgba(var(--c),.55);border-radius:999px;padding:3px 11px;color:rgb(var(--c));letter-spacing:.02em}}
    .ro-line{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:4px}}
    .ro{{font-size:16px;font-weight:900}}
    .veh{{font-size:12px;color:var(--mut);font-weight:600}}
    .directive{{font-weight:1000;letter-spacing:.02em;line-height:1.15;text-transform:uppercase}}
    .meta{{display:flex;gap:7px;flex-wrap:wrap;align-items:center;margin-top:12px}}
    .pill{{height:22px;border-radius:999px;padding:0 9px;display:inline-flex;align-items:center;gap:5px;font-size:10px;font-weight:900;text-transform:uppercase;letter-spacing:.03em;border:1px solid currentColor}}
    .pill.muted{{color:#94A3B8}}.pill.stale-pill{{color:#FF6B6B}}
    .pri{{height:22px;border-radius:7px;padding:0 8px;font-size:11px;font-weight:900;display:inline-flex;align-items:center;color:#fff}}
    .pri.P1{{background:#FF2D2D}}.pri.P2{{background:#FF7A00}}.pri.P3{{background:#FFD400;color:#111}}.pri.P4{{background:#22C55E;color:#052e16}}
    .do-btn{{margin-left:auto;min-height:30px;border-radius:8px;font-size:11px;font-weight:900;padding:7px 13px;cursor:pointer;text-decoration:none;font-family:inherit;display:inline-flex;align-items:center}}
    .do-btn.red{{border:1px solid rgba(255,59,48,.7);background:rgba(255,59,48,.16);color:#FF8A82}}
    .do-btn.purple{{border:1px solid rgba(168,85,247,.6);background:rgba(168,85,247,.14);color:#C084FC}}
    .do-btn.green{{border:1px solid rgba(34,197,94,.6);background:rgba(34,197,94,.14);color:#86EFAC}}
    .do-btn.orange{{border:1px solid rgba(255,149,0,.6);background:rgba(255,149,0,.14);color:#FFB020}}
    .do-btn.blue{{border:1px solid rgba(59,130,246,.6);background:rgba(59,130,246,.14);color:#93C5FD}}
    .inline-form{{display:inline;margin:0;margin-left:auto}}
    .donow{{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:12px}}
    .screamer{{position:relative;overflow:hidden;border-radius:16px;padding:16px 18px 16px 22px;background:linear-gradient(180deg,rgba(15,23,42,.98),rgba(7,12,24,.96));border:1px solid rgba(255,59,48,.85);animation:beat 2.1s ease-in-out infinite;cursor:pointer}}
    .screamer:after{{content:"";position:absolute;left:0;top:0;bottom:0;width:6px;background:#FF3B30;box-shadow:0 0 24px rgba(255,59,48,.9)}}
    .screamer .directive{{font-size:21px;color:#FF5247;margin:2px 0 12px}}
    .beacon{{width:11px;height:11px;border-radius:999px;background:#FF3B30;box-shadow:0 0 14px rgba(255,59,48,1);display:inline-block;animation:dot 1.2s ease-in-out infinite}}
    .po0{{animation-delay:0s}}.po1{{animation-delay:.7s}}.po2{{animation-delay:1.4s}}
    @keyframes beat{{0%,100%{{box-shadow:0 0 0 1px rgba(255,59,48,.7),0 0 16px rgba(255,59,48,.5),inset 0 1px 0 rgba(255,255,255,.06);transform:scale(1)}}50%{{box-shadow:0 0 0 4px rgba(255,59,48,1),0 0 54px rgba(255,59,48,1),inset 0 1px 0 rgba(255,255,255,.12);transform:scale(1.018)}}}}
    @keyframes dot{{0%,100%{{transform:scale(.8);opacity:.6}}50%{{transform:scale(1.55);opacity:1;box-shadow:0 0 20px rgba(255,59,48,1)}}}}
    .rows{{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:10px}}
    .row{{position:relative;overflow:hidden;border-radius:13px;padding:12px 14px 12px 18px;background:linear-gradient(180deg,rgba(15,23,42,.98),rgba(7,12,24,.96));border:1px solid rgba(var(--rgb),.55);box-shadow:inset 0 1px 0 rgba(255,255,255,.05);cursor:pointer}}
    .row:after{{content:"";position:absolute;left:0;top:0;bottom:0;width:5px;background:rgb(var(--rgb));box-shadow:0 0 16px rgba(var(--rgb),.5)}}
    .row .directive{{font-size:15px;margin:0 0 9px;color:rgb(var(--rgb))}}
    .row .ro{{font-size:14px}}
    .empty-wide{{border:1px dashed rgba(148,163,184,.24);border-radius:13px;background:rgba(15,23,42,.55);color:#64748B;font-size:12px;font-weight:800;text-align:center;padding:18px}}
    .legend{{margin-top:30px;padding-top:14px;border-top:1px solid var(--soft);font-size:11px;color:var(--faint);line-height:1.6}}
    .legend b{{color:var(--txt2);font-weight:800}}
    @media (prefers-reduced-motion:reduce){{.screamer,.beacon{{animation:none}}}}
    @media(max-width:760px){{body{{padding:16px 14px 40px}}.dtitle{{font-size:12px;white-space:normal}}.divider{{gap:9px}}.screamer .directive{{font-size:18px}}}}
  </style>
</head>
<body>
  <div class="top">
    <div class="title">DVI EXECUTION QUEUE<small>Powered by AdviseMe.ai · Generated {html.escape(generated_at)}</small></div>
    <div class="stats">
      <div class="stat"><b style="color:#FF3B30">{rework_count}</b><span>Rework</span></div>
      <div class="stat"><b style="color:#FFD400">{stale_count}</b><span>Stale 24h+</span></div>
      <div class="stat"><b style="color:#00E5FF">{parts_held}</b><span>Parts Held</span></div>
      <div class="stat"><b style="color:#3B82F6">{in_progress_count}</b><span>In Progress</span></div>
      <div class="stat"><b style="color:#22C55E">{done_count}</b><span>Done Today</span></div>
    </div>
    <div class="ctrls">
      <a class="btn" href="/v2">Command Board</a>
      <a class="btn" href="/dvi/history">History</a>
      <a class="btn live" href="/sanity-check">Sanity Check</a>
    </div>
  </div>

  {_render_divider("Do Now", len(do_now), "255,59,48")}
  {_render_do_now(do_now)}
  {stage_html}
  <div class="legend">
    <b>How to read it:</b> the directive is the loudest thing on every card. Work straight down: Do Now first, then each band. Rework, stale 24h+, and P1 jobs are pulled into Do Now and removed from stage bands, so there are <b>{duplicate_count}</b> duplicate listings.
  </div>
</body>
</html>"""
