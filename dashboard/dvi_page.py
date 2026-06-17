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
FOLLOWUPS_PATH = ROOT / "state" / "followups.json"

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
        "subtitle": "Closed-loop checklist before the RO moves fully into History.",
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


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def _load_followups() -> dict:
    data = _read_json(FOLLOWUPS_PATH)
    return data if isinstance(data, dict) else {}


def _is_followup_archived(ro: str) -> bool:
    entry = _load_followups().get(str(ro))
    return bool(isinstance(entry, dict) and entry.get("completed_at"))


def record_done_followup(ro: str, payload: dict | None = None) -> dict:
    ro_text = _normalize_ro_key(ro)
    if not ro_text:
        raise ValueError("RO is required")
    payload = payload or {}
    followups = _load_followups()
    entry = {
        "ro": ro_text,
        "followed_up": str(payload.get("followed_up", "")).lower() in {"1", "true", "yes", "on"},
        "appointment_date": str(payload.get("appointment_date") or "").strip(),
        "appointment_scheduled": str(payload.get("appointment_scheduled", "")).lower() in {"1", "true", "yes", "on"},
        "completed_at": _now_utc().isoformat(),
        "source": "dvi_recently_done",
    }
    # Future step: create/update the actual appointment through AutoFlow's appointments API.
    followups[ro_text] = entry
    _write_json(FOLLOWUPS_PATH, followups)
    return entry


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


def _demo_dt(hours_ago: float) -> str:
    return (_now_utc() - timedelta(hours=hours_ago)).isoformat()


def _demo_record(
    ro: str,
    customer: str,
    vehicle: str,
    workflow_status: str,
    review_status: str,
    priority: str,
    technician: str,
    hours_ago: float,
    packet_current: bool = False,
    packet_exists: bool = False,
    flags: list[dict] | None = None,
    next_action: str = "",
    hours_in_status: float | None = None,
) -> dict:
    flags = flags or []
    packet_status = {
        "exists": packet_exists or packet_current,
        "current": packet_current,
        "stale": False,
        "state": "current" if packet_current else "no packet yet",
        "generated_at": _demo_dt(hours_ago / 2),
        "source": "demo",
    }
    record = {
        "ro": ro,
        "customer": customer,
        "vehicle": vehicle,
        "workflow_status": workflow_status,
        "normalized_status": _normalize_status(workflow_status),
        "is_live_job": True,
        "stale_review": False,
        "review_status": review_status,
        "review_resolved": False,
        "advisor_acknowledged": False,
        "gate_ran_at": _demo_dt(max(0.2, hours_ago - 0.2)),
        "flags": flags,
        "flag_count": len(flags),
        "critical_count": len(flags),
        "packet_status": packet_status,
        "status_updated_at": _demo_dt(hours_ago),
        "updated_at": "",
        "generated_at": _demo_dt(hours_ago),
        "priority_lane": priority,
        "risk_level": "CRITICAL" if priority == "P1" else "",
        "waiting_on": "Demo",
        "technician": technician,
        "hermes_next_action": next_action,
        "next_action": next_action,
        "hours_in_status": hours_in_status,
        "stale": False,
        "demo_mode": True,
    }
    record["lane"] = assign_dvi_lane(record)
    return record


def _demo_records() -> list[dict]:
    return [
        _demo_record(
            "D9001", "Jordan Bell", "2020 Ford F-250 Powerstroke", "servicing",
            "REWORK_REQUIRED", "P1", "Alex",
            2.4,
            flags=[{"message": "Missing fuel pressure reading after hard-start concern."}],
        ),
        _demo_record(
            "D9002", "Maria Reyes", "2018 Honda Odyssey", "waiting parts",
            "REWORK_REQUIRED", "P1", "Sam",
            4.1,
            flags=[{"message": "Brake noise concern needs which-corner note and pad measurement."}],
        ),
        _demo_record(
            "D9003", "Evan Brooks", "2017 Jeep Grand Cherokee", "advisor qc review",
            "REWORK_REQUIRED", "P2", "Luis",
            1.3,
            flags=[{"message": "Warning light concern needs code photo attached."}],
        ),
        _demo_record(
            "D9004", "Nina Patel", "2019 Chevy Silverado 1500", "servicing",
            "PASS", "P3", "Marco",
            27.0,
            next_action="WATCH PRODUCTION",
            hours_in_status=27,
        ),
        _demo_record(
            "D9005", "Theo Martin", "2021 Toyota Tacoma", "unknown",
            "PASS", "P3", "Demo Tech",
            0.8,
        ),
        _demo_record(
            "D9006", "Paige Stone", "2016 Dodge Durango", "unknown",
            "PASS", "P3", "Demo Tech",
            1.0,
            packet_current=True,
            packet_exists=True,
        ),
        _demo_record(
            "D9007", "Chris Nolan", "2022 Ford Ranger", "servicing",
            "PASS", "P3", "Riley",
            3.2,
            next_action="Inspecting driveline vibration",
        ),
        _demo_record(
            "D9008", "Lena Ortiz", "2015 Toyota 4Runner", "waiting parts",
            "PASS", "P3", "Parts",
            5.6,
            next_action="Waiting on lower control arm ETA",
        ),
        _demo_record(
            "D9009", "Calvin Price", "2020 Honda CR-V", "awaiting tech",
            "NO_REVIEW", "P4", "",
            0.6,
            next_action="Assign next available tech",
        ),
        _demo_record(
            "D9010", "Avery Kim", "2019 Subaru Outback", "advisor qc review",
            "PASS", "P3", "Morgan",
            0.9,
        ),
        _demo_record(
            "D9011", "Sofia Grant", "2018 Toyota Camry", "finished",
            "PASS", "P4", "Jamie",
            3.0,
            packet_current=True,
            packet_exists=True,
        ),
        _demo_record(
            "D9012", "Marcus Hill", "2021 Chevy Tahoe", "ready",
            "PASS", "P4", "Taylor",
            6.5,
            packet_current=True,
            packet_exists=True,
        ),
    ]


def _lane_records(records: list[dict]) -> dict[str, list[dict]]:
    lanes = {lane["key"]: [] for lane in LANES}
    seen: set[str] = set()
    for record in records:
        ro = record["ro"]
        if ro in seen:
            continue
        seen.add(ro)
        lane = record["lane"]
        if lane == "done" and _is_followup_archived(ro):
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
    if record.get("demo_mode"):
        return '<span class="do-btn demo-inert">Demo only</span>'
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
        return f'<a class="do-btn purple" href="/dvi/packet/{ro}" target="_blank" rel="noopener">Build Packet</a>'
    if lane == "tekmetric_ready" or packet.get("exists"):
        return f'<a class="do-btn green" href="{_card_href(record)}" target="_blank" rel="noopener">Open Packet</a>'
    if lane == "advisor_qc_review":
        return f'<a class="do-btn orange" href="{_card_href(record)}" target="_blank" rel="noopener">Review</a>'
    if lane == "done":
        return '<a class="do-btn green" href="/dvi/history" target="_blank" rel="noopener">Open History</a>'
    return f'<a class="do-btn blue" href="{_card_href(record)}" target="_blank" rel="noopener">Open</a>'


def _stage_meta(record: dict) -> tuple[str, str]:
    lane = record.get("lane")
    packet = record.get("packet_status", {})
    status = _normalize_status(record.get("workflow_status"))
    if _is_rework(record):
        return "Owner: Tech", f"{record.get('flag_count', 0)} failed checks"
    if lane == "ready_for_build_packet":
        return "Owner: Advisor", "Inspection: clean"
    if lane == "tekmetric_ready":
        return "Owner: Advisor", "Packet current" if packet.get("current") else str(packet.get("state") or "Packet ready")
    if lane == "advisor_qc_review":
        return "Owner: Advisor", "Tech QC done"
    if status in {"waiting parts", "ordering parts", "parts"}:
        return "Owner: Parts", f"Stage: {status}"
    if lane == "done":
        return "Owner: History", _hours_label(record)
    return "Owner: Tech", f"Stage: {status}" if status else "Stage: in progress"


def _awaiting_followup_label(record: dict) -> str:
    done_time = None
    for key in ("status_updated_at", "updated_at", "generated_at", "gate_ran_at"):
        done_time = _parse_dt(record.get(key))
        if done_time:
            break
    if not done_time:
        return "awaiting follow-up"
    hours = max(0.0, (_now_utc() - done_time).total_seconds() / 3600)
    if hours >= 24:
        return f"awaiting follow-up {int(hours // 24)}d {int(hours % 24)}h"
    if hours >= 1:
        return f"awaiting follow-up {int(hours)}h"
    return f"awaiting follow-up {int(hours * 60)}m"


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
        if lane == "done" and _is_followup_archived(ro):
            continue
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
        gate_time = _time_ago(record.get("gate_ran_at"))
        gate_label = "Gate: not run" if gate_time == "unknown" else f"Gate ran {gate_time}"
        parts.append(f'<span class="pill muted">{html.escape(gate_label)}</span>')
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
        click = "" if record.get("demo_mode") else f" onclick=\"if(!event.target.closest('a,button,form')) window.open('{href}','_blank','noopener')\""
        cards.append(f"""
        <article class="screamer po{index % 3}"{click}>
          <div class="ro-line"><span class="ro">RO {ro}</span><span class="beacon"></span><span class="veh">{html.escape(vehicle)}</span></div>
          <div class="directive">{html.escape(_directive(record))}</div>
          {_render_meta(record)}
        </article>
        """)
    return '<div class="donow">' + "\n".join(cards) + "</div>"


def _render_stage_card(record: dict, rgb: str) -> str:
    if record.get("lane") == "done":
        return _render_done_card(record, rgb)
    ro = html.escape(str(record.get("ro") or ""))
    href = html.escape(_card_href(record))
    vehicle = f"{record.get('customer') or 'Unknown'} · {record.get('vehicle') or ''}".strip(" ·")
    opacity = "opacity:.72;" if record.get("lane") == "done" else ""
    click = "" if record.get("demo_mode") else f" onclick=\"if(!event.target.closest('a,button,form')) window.open('{href}','_blank','noopener')\""
    return f"""
    <article class="row" style="--rgb:{rgb};{opacity}"{click}>
      <div class="ro-line"><span class="ro">RO {ro}</span><span class="veh">{html.escape(vehicle)}</span></div>
      <div class="directive">{html.escape(_directive(record))}</div>
      {_render_meta(record)}
    </article>
    """


def _render_done_card(record: dict, rgb: str) -> str:
    ro = html.escape(str(record.get("ro") or ""))
    customer = html.escape(str(record.get("customer") or "Unknown Customer"))
    vehicle = html.escape(str(record.get("vehicle") or ""))
    closed = html.escape(_hours_label(record))
    awaiting = html.escape(_awaiting_followup_label(record))
    form_action = "#" if record.get("demo_mode") else f"/dvi/followup/{ro}"
    disabled = " disabled" if record.get("demo_mode") else ""
    button_label = "Demo only" if record.get("demo_mode") else "Archive to History"
    return f"""
    <article class="row done-card" style="--rgb:{rgb}">
      <div class="done-head">
        <div>
          <div class="ro-line"><span class="ro">RO {ro}</span><span class="veh">{customer}</span></div>
          <div class="done-vehicle">{vehicle}</div>
        </div>
        <span class="closed-pill">{closed}</span>
      </div>
      <div class="follow-box">
        <div class="follow-title">Close the loop</div>
        <div class="follow-age">{awaiting}</div>
        <form class="follow-form" method="post" action="{form_action}" onsubmit="{'return false;' if record.get('demo_mode') else ''}">
          <label class="date-label">
            <span>Next appointment</span>
            <input type="date" name="appointment_date"{disabled}>
          </label>
          <label class="check-label">
            <input type="checkbox" name="appointment_scheduled" value="1"{disabled}>
            <span>Appointment scheduled</span>
          </label>
          <label class="check-label">
            <input type="checkbox" name="followed_up" value="1"{disabled}>
            <span>Followed up</span>
          </label>
          <button class="archive-btn" type="submit"{disabled}>{button_label}</button>
        </form>
      </div>
    </article>
    """


def _render_stage(title: str, records: list[dict], rgb: str) -> str:
    body = (
        '<div class="rows">' + "\n".join(_render_stage_card(record, rgb) for record in records) + "</div>"
        if records else '<div class="empty-wide">Nothing queued in this stage.</div>'
    )
    return _render_divider(title, len(records), rgb) + body


def _training_steps() -> list[dict]:
    sample_card = """
      <div class="sample-card">
        <div class="tag top">Directive: the next move</div>
        <div class="ro-line"><span class="ro">RO D9001</span><span class="veh">Jordan Bell - 2020 Ford F-250</span></div>
        <div class="directive">SEND BACK TO ALEX - Missing fuel pressure reading</div>
        <div class="meta sample-meta">
          <span class="pill muted">Owner: Tech</span>
          <span class="pill stale-pill">Stale 1d 3h</span>
          <span class="pill muted">2 failed checks</span>
          <span class="pill muted">Gate ran 18m ago</span>
          <span class="pill muted">Stage: servicing</span>
        </div>
        <div class="callouts">
          <span>Directive = gate result + workflow status</span>
          <span>Owner = who has the next move</span>
          <span>Gate = DVI quality gate timestamp/result</span>
          <span>Stage = AutoFlow workflow_status</span>
          <span>Stale = time since last update</span>
        </div>
      </div>
    """
    done_card = """
      <div class="sample-card done-card training-done">
        <div class="done-head">
          <div>
            <div class="ro-line"><span class="ro">RO D9011</span><span class="veh">Sofia Grant</span></div>
            <div class="done-vehicle">2018 Toyota Camry</div>
          </div>
          <span class="closed-pill">closed 3h ago</span>
        </div>
        <div class="follow-box">
          <div class="follow-title">Close the loop</div>
          <div class="follow-age">awaiting follow-up 3h</div>
          <div class="training-form">
            <span>Next appointment: 2026-06-24</span>
            <span>Appointment scheduled</span>
            <span>Followed up</span>
            <span>Archive to History</span>
          </div>
        </div>
      </div>
    """
    owner_visual = """
      <div class="pill-grid">
        <span><b>Owner: Tech</b><small>Technician has the next move: inspection, rework fix, testing, or production update.</small></span>
        <span><b>Owner: Advisor</b><small>Advisor has the next move: build packet, push packet, call, review, or finalize.</small></span>
        <span><b>Owner: Parts</b><small>Parts department has the next move: ETA, arrival, staging, or parts blocker.</small></span>
      </div>
    """
    priority_visual = """
      <div class="priority-stack">
        <span class="p1">P1 - Drop everything. Most urgent.</span>
        <span class="p2">P2 - High priority. Handle after P1.</span>
        <span class="p3">P3 - Normal controlled work.</span>
        <span class="p4">P4 - Lowest pressure / background work.</span>
      </div>
    """
    action_visual = """
      <div class="button-grid">
        <span class="red">Re-run Gate - re-check the DVI after a tech fixes rework.</span>
        <span class="purple">Build Packet - create the estimate packet from a clean DVI.</span>
        <span class="green">Open / Open Packet - open an already-built packet.</span>
        <span class="orange">Review - advisor QC/finalization work.</span>
      </div>
    """
    header_visual = """
      <div class="button-grid">
        <span>Command Board - returns to the main /v2 shop command board.</span>
        <span>History - opens completed/stored packet history without regenerating.</span>
        <span>Training - this walkthrough.</span>
        <span>Sanity Check - printable morning sanity-check report.</span>
      </div>
    """
    return [
        {
            "title": "What This Board Is",
            "body": "The DVI Execution Queue tells advisors what to do next. Work top-down: clear Do Now first, then move through each stage band. The board removes guessing by turning gate results, workflow status, packet status, and timing into one action queue.",
            "visual": '<div class="training-hero">Work top-down. Clear the loudest blockers first. Let the queue tell you the next move.</div>',
        },
        {
            "title": "Do Now",
            "body": "Do Now is the genuine urgent few: active rework, active stale jobs, and true P1 work. These cards float out of their stage so they cannot hide lower on the page. Clear Do Now before building packets or doing routine follow-up.",
            "visual": '<div class="mini-lanes"><span class="hot">Active rework</span><span class="hot">Stale 24h+</span><span class="hot">True P1</span></div>',
        },
        {
            "title": "The Stage Bands",
            "body": "Ready for Build Packet means the inspection is clean but no current packet exists. TekMetric Ready means a current packet exists. In Progress means the RO is still moving through production, parts, approval, or tech flow. Advisor QC Review is advisor action before closeout. Recently Done is the close-the-loop checklist.",
            "visual": '<div class="band-stack"><span>Ready for Build Packet -> build packet</span><span>TekMetric Ready -> push to TekMetric</span><span>In Progress -> monitor blocker</span><span>Advisor QC Review -> review and finalize</span><span>Recently Done -> close the loop</span></div>',
        },
        {
            "title": "Anatomy Of A Card",
            "body": "The directive is the largest text because it is the action. Supporting pills explain why: Owner, Stage, Gate, Stale, and failed checks. Data comes from AutoFlow board state, the DVI quality gate, packet cache, and time since the latest update.",
            "visual": sample_card,
        },
        {
            "title": "Owners",
            "body": "The Owner pill says who has the next move, not who owns the whole repair order forever. Tech means the technician needs to act. Advisor means the advisor needs to act. Parts means the job is waiting on parts movement or confirmation.",
            "visual": owner_visual,
        },
        {
            "title": "Priority P1-P4",
            "body": "P1 through P4 is the urgency ladder. P1 means drop everything. P4 is the lowest pressure. Do Now uses this priority plus rework and stale timing so the top card is the most urgent card to handle first.",
            "visual": priority_visual,
        },
        {
            "title": "Stage And Gate",
            "body": "Stage is the AutoFlow workflow_status, like servicing, waiting parts, advisor QC review, ready, or finished. Gate is the DVI quality gate result: pass, review, or rework. Stage tells where the RO is. Gate tells whether the DVI is clean enough to build from.",
            "visual": '<div class="pill-grid"><span><b>Stage: servicing</b><small>From AutoFlow workflow_status.</small></span><span><b>Gate ran 18m ago</b><small>From the deterministic DVI quality gate.</small></span><span><b>Inspection: clean</b><small>DVI gate passed and is safe to build from.</small></span><span><b>2 failed checks</b><small>Gate found specific rework gaps.</small></span></div>',
        },
        {
            "title": "Action Buttons",
            "body": "Re-run Gate re-checks the DVI in place after a tech fixes rework. It does not delete or resubmit the inspection. Build Packet means no current packet exists yet. Open or Open Packet means the packet is already built and opens in a new tab.",
            "visual": action_visual,
        },
        {
            "title": "Header Buttons",
            "body": "The header buttons are quick exits. Command Board opens the main shop board. History opens completed or stored packet records. Training opens this walkthrough. Sanity Check opens the printable morning report.",
            "visual": header_visual,
        },
        {
            "title": "Recently Done",
            "body": "Closed jobs are not ranked work. They stay in Recently Done until the advisor confirms follow-up, optionally records the next appointment date, and archives the RO to History. This is a local checklist only; it does not create an AutoFlow appointment yet.",
            "visual": done_card,
        },
        {
            "title": "What's Coming",
            "body": "Next versions can use TekMetric data for customer approval and declined-work follow-ups, plus real appointment booking through the AutoFlow appointments API. For now, the board stays deterministic and only shows what the connected data can support.",
            "visual": '<div class="coming-grid"><span>TekMetric-powered directives</span><span>Declined-work follow-up</span><span>Real appointment booking</span><span>More precise ownership</span></div>',
        },
    ]


def render_dvi_page(demo: bool = False) -> str:
    records = _demo_records() if demo else _build_records()
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
    demo_banner = (
        '<div class="demo-banner">DEMO MODE - Synthetic sample queue. No real ROs, no writes, no API calls.</div>'
        if demo else ""
    )
    demo_button = (
        '<a class="btn live" href="/dvi">Exit Demo</a>'
        if demo else '<a class="btn" href="/dvi?demo=1">Demo Mode</a>'
    )

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
    body{{margin:0;font-family:Inter,ui-sans-serif,system-ui,Arial,sans-serif;background:radial-gradient(circle at top left,#111B3A 0%,#050816 40%,#020617 100%);color:var(--txt);-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;padding:22px 26px 60px}}
    .top{{display:flex;justify-content:space-between;align-items:center;gap:16px;border-bottom:1px solid var(--soft);padding-bottom:16px;margin-bottom:8px;flex-wrap:wrap}}
    .title{{font-size:22px;font-weight:900;letter-spacing:.06em}}
    .title small{{display:block;font-size:10px;font-weight:800;letter-spacing:.18em;color:#A855F7;text-transform:uppercase;margin-top:5px}}
    .stats{{display:flex;gap:9px;flex-wrap:wrap}}
    .stat{{min-width:78px;height:50px;background:linear-gradient(180deg,rgba(15,23,42,.96),rgba(2,6,23,.9));border:1px solid #263954;border-radius:11px;display:flex;flex-direction:column;align-items:center;justify-content:center}}
    .stat b{{font-size:22px;font-weight:900;line-height:1}}
    .stat span{{font-size:8.5px;font-weight:800;letter-spacing:.07em;text-transform:uppercase;color:var(--faint);margin-top:4px}}
    .ctrls{{display:flex;gap:8px;align-items:center;flex-wrap:wrap}}
    .btn{{height:32px;border-radius:8px;border:1px solid var(--med);background:rgba(15,23,42,.85);color:var(--txt2);font-size:11px;font-weight:800;padding:8px 12px;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center}}
    .btn.live{{border-color:rgba(168,85,247,.7);color:#C084FC;box-shadow:0 0 16px rgba(168,85,247,.25)}}
    .demo-banner{{position:sticky;top:0;z-index:20;margin:-6px auto 18px;width:max-content;max-width:100%;border:1px solid rgba(168,85,247,.75);background:linear-gradient(90deg,rgba(168,85,247,.92),rgba(59,130,246,.9));color:#fff;border-radius:0 0 14px 14px;padding:8px 24px;font-size:12px;font-weight:900;letter-spacing:.12em;text-transform:uppercase;box-shadow:0 0 28px rgba(168,85,247,.42)}}
    .divider{{display:flex;align-items:center;gap:16px;margin:34px 0 16px}}
    .dline{{flex:1;height:2px;border-radius:2px}}
    .dline.l{{background:linear-gradient(90deg,transparent,rgba(var(--c),.55))}}
    .dline.r{{background:linear-gradient(90deg,rgba(var(--c),.55),transparent)}}
    .dtitle{{font-size:15px;font-weight:900;letter-spacing:.16em;text-transform:uppercase;color:rgb(var(--c));white-space:nowrap;display:flex;align-items:center;gap:11px;text-align:center}}
    .cnt{{font-size:12px;font-weight:900;background:rgba(var(--c),.18);border:1px solid rgba(var(--c),.55);border-radius:999px;padding:3px 11px;color:rgb(var(--c));letter-spacing:.02em}}
    .ro-line{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:4px}}
    .ro{{font-size:16px;font-weight:900}}
    .veh{{font-size:12px;color:var(--mut);font-weight:600}}
    .directive{{font-weight:1000;letter-spacing:.02em;line-height:1.15;text-transform:uppercase}}
    .meta{{display:flex;gap:7px;flex-wrap:wrap;align-items:center;margin-top:12px}}
    .pill{{height:24px;border-radius:999px;padding:0 10px;display:inline-flex;align-items:center;gap:5px;font-size:10.5px;font-weight:900;text-transform:uppercase;letter-spacing:.025em;border:1px solid currentColor}}
    .pill.muted{{color:#CBD5E1;background:rgba(148,163,184,.07);border-color:rgba(203,213,225,.38)}}.pill.stale-pill{{color:#FF6B6B}}
    .pri{{height:22px;border-radius:7px;padding:0 8px;font-size:11px;font-weight:900;display:inline-flex;align-items:center;color:#fff}}
    .pri.P1{{background:#FF2D2D}}.pri.P2{{background:#FF7A00}}.pri.P3{{background:#FFD400;color:#111}}.pri.P4{{background:#22C55E;color:#052e16}}
    .do-btn{{margin-left:auto;min-height:30px;border-radius:8px;font-size:11px;font-weight:900;padding:7px 13px;cursor:pointer;text-decoration:none;font-family:inherit;display:inline-flex;align-items:center}}
    .do-btn.red{{border:1px solid rgba(255,59,48,.7);background:rgba(255,59,48,.16);color:#FF8A82}}
    .do-btn.purple{{border:1px solid rgba(168,85,247,.6);background:rgba(168,85,247,.14);color:#C084FC}}
    .do-btn.green{{border:1px solid rgba(34,197,94,.6);background:rgba(34,197,94,.14);color:#86EFAC}}
    .do-btn.orange{{border:1px solid rgba(255,149,0,.6);background:rgba(255,149,0,.14);color:#FFB020}}
    .do-btn.blue{{border:1px solid rgba(59,130,246,.6);background:rgba(59,130,246,.14);color:#93C5FD}}
    .do-btn.demo-inert{{border:1px solid rgba(148,163,184,.38);background:rgba(148,163,184,.08);color:#CBD5E1;cursor:default}}
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
    .done-card{{cursor:default;opacity:.72;background:linear-gradient(180deg,rgba(15,23,42,.82),rgba(7,12,24,.76));border-color:rgba(34,197,94,.28)}}
    .done-card:after{{opacity:.45;box-shadow:0 0 10px rgba(34,197,94,.24)}}
    .done-head{{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:10px}}
    .done-vehicle{{font-size:11px;color:#64748B;font-weight:700;margin-top:2px}}
    .closed-pill{{border:1px solid rgba(34,197,94,.38);background:rgba(34,197,94,.08);color:#86EFAC;border-radius:999px;padding:5px 9px;font-size:10px;font-weight:900;white-space:nowrap;text-transform:uppercase}}
    .follow-box{{border:1px solid rgba(148,163,184,.18);background:rgba(2,6,23,.35);border-radius:11px;padding:10px;margin-top:8px}}
    .follow-title{{font-size:12px;font-weight:900;color:#CBD5E1;text-transform:uppercase;letter-spacing:.08em}}
    .follow-age{{font-size:11px;color:#94A3B8;margin-top:3px;margin-bottom:9px}}
    .follow-form{{display:grid;grid-template-columns:1fr 1fr;gap:8px;align-items:center}}
    .date-label{{grid-column:1/-1;display:grid;gap:4px;font-size:10px;font-weight:900;color:#64748B;text-transform:uppercase;letter-spacing:.06em}}
    .date-label input{{height:31px;border-radius:8px;border:1px solid rgba(148,163,184,.26);background:#020617;color:#E2E8F0;padding:0 9px;font-family:inherit}}
    .check-label{{display:flex;align-items:center;gap:7px;font-size:11px;font-weight:800;color:#CBD5E1}}
    .check-label input{{accent-color:#22C55E}}
    .archive-btn{{grid-column:1/-1;min-height:31px;border-radius:8px;border:1px solid rgba(34,197,94,.48);background:rgba(34,197,94,.12);color:#86EFAC;font-size:11px;font-weight:900;cursor:pointer;font-family:inherit;text-transform:uppercase;letter-spacing:.05em}}
    .archive-btn:hover{{background:rgba(34,197,94,.2)}}
    .empty-wide{{border:1px dashed rgba(148,163,184,.24);border-radius:13px;background:rgba(15,23,42,.55);color:#64748B;font-size:12px;font-weight:800;text-align:center;padding:18px}}
    .legend{{margin-top:30px;padding-top:14px;border-top:1px solid var(--soft);font-size:11px;color:var(--faint);line-height:1.6}}
    .legend b{{color:var(--txt2);font-weight:800}}
    @media (prefers-reduced-motion:reduce){{.screamer,.beacon{{animation:none}}}}
    @media(max-width:760px){{body{{padding:16px 14px 40px}}.dtitle{{font-size:12px;white-space:normal}}.divider{{gap:9px}}.screamer .directive{{font-size:18px}}}}
  </style>
</head>
<body>
  {demo_banner}
  <div class="top">
    <div class="title">DVI EXECUTION QUEUE<small>Powered by AdviseMe.ai · Generated {html.escape(generated_at)}</small></div>
    <div class="stats">
      <div class="stat"><b style="color:#FF3B30">{rework_count}</b><span>Rework</span></div>
      <div class="stat"><b style="color:#FFD400">{stale_count}</b><span>Stale 24h+</span></div>
      <div class="stat"><b style="color:#00E5FF">{parts_held}</b><span>Parts Held</span></div>
      <div class="stat"><b style="color:#3B82F6">{in_progress_count}</b><span>In Progress</span></div>
      <div class="stat"><b style="color:#22C55E">{done_count}</b><span>Recently Done</span></div>
    </div>
    <div class="ctrls">
      <a class="btn" href="/v2">Command Board</a>
      <a class="btn" href="/dvi/history">History</a>
      <a class="btn" href="/dvi/training" target="_blank" rel="noopener">Training</a>
      <a class="btn live" href="/sanity-check">Sanity Check</a>
      {demo_button}
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


def render_dvi_training_page() -> str:
    steps = _training_steps()
    step_html = []
    for index, step in enumerate(steps):
        active = " active" if index == 0 else ""
        step_html.append(f"""
        <section class="step{active}" data-step="{index}">
          <div class="eyebrow">Step {index + 1} of {len(steps)}</div>
          <h2>{html.escape(step["title"])}</h2>
          <p>{html.escape(step["body"])}</p>
          <div class="visual">{step["visual"]}</div>
        </section>
        """)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DVI Queue Training | Callahan Auto</title>
  <style>
    :root{{--bg:#050816;--card:#0F172A;--soft:#1E293B;--med:#334155;--txt:#fff;--txt2:#CBD5E1;--mut:#94A3B8;--faint:#64748B;--status-immediate:#FF3B30;--status-customer:#FF9500;--status-progress:#3B82F6;--status-ready:#22C55E;--status-parts:#00E5FF;--status-ai:#A855F7}}
    *{{box-sizing:border-box}}
    body{{margin:0;font-family:Inter,ui-sans-serif,system-ui,Arial,sans-serif;background:radial-gradient(circle at top left,#111B3A 0%,#050816 40%,#020617 100%);color:var(--txt);-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;padding:24px}}
    .shell{{max-width:1120px;margin:0 auto}}
    .top{{display:flex;justify-content:space-between;align-items:flex-end;gap:18px;border-bottom:1px solid var(--soft);padding-bottom:18px;margin-bottom:24px;flex-wrap:wrap}}
    h1{{margin:0;font-size:28px;font-weight:1000;letter-spacing:.06em}}
    .sub{{color:#A855F7;font-size:10px;font-weight:900;letter-spacing:.18em;text-transform:uppercase;margin-top:6px}}
    .btn{{height:34px;border-radius:9px;border:1px solid var(--med);background:rgba(15,23,42,.85);color:var(--txt2);font-size:11px;font-weight:900;padding:9px 13px;text-decoration:none;display:inline-flex;align-items:center}}
    .btn.live{{border-color:rgba(168,85,247,.7);color:#C084FC;box-shadow:0 0 16px rgba(168,85,247,.25)}}
    .panel{{border:1px solid rgba(168,85,247,.35);background:linear-gradient(180deg,rgba(15,23,42,.92),rgba(2,6,23,.88));border-radius:22px;padding:22px;box-shadow:0 0 40px rgba(0,0,0,.28), inset 0 1px 0 rgba(255,255,255,.06)}}
    .progress{{display:flex;justify-content:space-between;align-items:center;gap:14px;margin-bottom:18px;color:#94A3B8;font-size:12px;font-weight:900;text-transform:uppercase;letter-spacing:.08em}}
    .bar{{height:8px;flex:1;border-radius:999px;background:#111827;overflow:hidden;border:1px solid #1E293B}}
    .fill{{height:100%;width:16.66%;background:linear-gradient(90deg,#A855F7,#3B82F6);box-shadow:0 0 18px rgba(168,85,247,.7);transition:width .2s ease}}
    .step{{display:none;min-height:520px}}
    .step.active{{display:grid;grid-template-columns:minmax(0,1fr) minmax(360px,1.1fr);gap:28px;align-items:center}}
    .eyebrow{{color:#A855F7;font-size:11px;font-weight:900;letter-spacing:.16em;text-transform:uppercase;margin-bottom:10px}}
    h2{{font-size:38px;line-height:1.02;margin:0 0 16px;font-weight:1000;letter-spacing:.02em}}
    p{{font-size:17px;line-height:1.65;color:#CBD5E1;margin:0;max-width:620px}}
    .visual{{border:1px solid rgba(148,163,184,.22);border-radius:18px;background:rgba(2,6,23,.42);padding:18px;min-height:280px;display:flex;align-items:center;justify-content:center}}
    .training-hero{{font-size:30px;line-height:1.2;font-weight:1000;text-align:center;color:#fff;max-width:440px}}
    .mini-lanes,.band-stack,.coming-grid{{display:grid;gap:12px;width:100%}}
    .mini-lanes span,.band-stack span,.coming-grid span{{border:1px solid rgba(168,85,247,.42);background:rgba(168,85,247,.10);border-radius:13px;padding:14px 16px;font-size:14px;font-weight:900;color:#E9D5FF}}
    .mini-lanes .hot{{border-color:rgba(255,59,48,.7);background:rgba(255,59,48,.12);color:#FF8A82;box-shadow:0 0 18px rgba(255,59,48,.18)}}
    .band-stack span:nth-child(1){{border-color:rgba(168,85,247,.55);color:#C084FC}}
    .band-stack span:nth-child(2){{border-color:rgba(34,197,94,.55);color:#86EFAC}}
    .band-stack span:nth-child(3){{border-color:rgba(59,130,246,.55);color:#93C5FD}}
    .band-stack span:nth-child(4){{border-color:rgba(255,149,0,.55);color:#FDBA74}}
    .band-stack span:nth-child(5){{border-color:rgba(34,197,94,.32);color:#CBD5E1}}
    .pill-grid,.priority-stack,.button-grid{{display:grid;gap:12px;width:100%}}
    .pill-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}
    .pill-grid span,.priority-stack span,.button-grid span{{border:1px solid rgba(148,163,184,.28);background:rgba(15,23,42,.72);border-radius:13px;padding:14px 16px;color:#CBD5E1;font-size:13px;line-height:1.45}}
    .pill-grid b{{display:block;color:#fff;font-size:14px;margin-bottom:5px}}
    .pill-grid small{{display:block;color:#94A3B8;font-size:12px;line-height:1.45}}
    .priority-stack span{{font-weight:1000}}
    .priority-stack .p1{{border-color:rgba(255,59,48,.68);color:#FF8A82;background:rgba(255,59,48,.10)}}
    .priority-stack .p2{{border-color:rgba(255,149,0,.68);color:#FDBA74;background:rgba(255,149,0,.10)}}
    .priority-stack .p3{{border-color:rgba(255,212,0,.58);color:#FDE68A;background:rgba(255,212,0,.08)}}
    .priority-stack .p4{{border-color:rgba(34,197,94,.46);color:#86EFAC;background:rgba(34,197,94,.08)}}
    .button-grid{{grid-template-columns:repeat(2,minmax(0,1fr))}}
    .button-grid span{{font-weight:900}}
    .button-grid .red{{border-color:rgba(255,59,48,.65);color:#FF8A82;background:rgba(255,59,48,.10)}}
    .button-grid .purple{{border-color:rgba(168,85,247,.65);color:#C084FC;background:rgba(168,85,247,.10)}}
    .button-grid .green{{border-color:rgba(34,197,94,.60);color:#86EFAC;background:rgba(34,197,94,.10)}}
    .button-grid .orange{{border-color:rgba(255,149,0,.60);color:#FDBA74;background:rgba(255,149,0,.10)}}
    .sample-card{{position:relative;width:100%;border-radius:16px;padding:18px;background:linear-gradient(180deg,rgba(15,23,42,.98),rgba(7,12,24,.96));border:1px solid rgba(255,59,48,.7);box-shadow:0 0 24px rgba(255,59,48,.25);overflow:hidden}}
    .sample-card:after{{content:"";position:absolute;left:0;top:0;bottom:0;width:5px;background:#FF3B30;box-shadow:0 0 18px rgba(255,59,48,.75)}}
    .tag{{position:absolute;right:12px;top:10px;border:1px solid rgba(255,59,48,.6);background:rgba(255,59,48,.12);color:#FF8A82;border-radius:999px;padding:5px 9px;font-size:10px;font-weight:900;text-transform:uppercase}}
    .ro-line{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:6px}}
    .ro{{font-size:16px;font-weight:1000;color:#fff}}
    .veh{{font-size:12px;color:#94A3B8;font-weight:700}}
    .directive{{font-size:23px;line-height:1.1;font-weight:1000;color:#FF5247;text-transform:uppercase;margin:12px 0}}
    .meta{{display:flex;gap:7px;flex-wrap:wrap;align-items:center;margin-top:12px}}
    .pill{{height:24px;border-radius:999px;padding:0 10px;display:inline-flex;align-items:center;gap:5px;font-size:10.5px;font-weight:900;text-transform:uppercase;letter-spacing:.025em;border:1px solid currentColor}}
    .pill.muted{{color:#CBD5E1;background:rgba(148,163,184,.07);border-color:rgba(203,213,225,.38)}}.pill.stale-pill{{color:#FF6B6B}}
    .callouts{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:16px}}
    .callouts span{{border:1px dashed rgba(148,163,184,.32);border-radius:10px;padding:9px;color:#CBD5E1;font-size:11px;line-height:1.35}}
    .done-card{{border-color:rgba(34,197,94,.28);box-shadow:none;opacity:.86}}
    .done-card:after{{background:#22C55E;opacity:.45;box-shadow:0 0 10px rgba(34,197,94,.24)}}
    .done-head{{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:10px}}
    .done-vehicle{{font-size:11px;color:#64748B;font-weight:700;margin-top:2px}}
    .closed-pill{{border:1px solid rgba(34,197,94,.38);background:rgba(34,197,94,.08);color:#86EFAC;border-radius:999px;padding:5px 9px;font-size:10px;font-weight:900;white-space:nowrap;text-transform:uppercase}}
    .follow-box{{border:1px solid rgba(148,163,184,.18);background:rgba(2,6,23,.35);border-radius:11px;padding:10px;margin-top:8px}}
    .follow-title{{font-size:12px;font-weight:900;color:#CBD5E1;text-transform:uppercase;letter-spacing:.08em}}
    .follow-age{{font-size:11px;color:#94A3B8;margin-top:3px;margin-bottom:9px}}
    .training-form{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}
    .training-form span{{border:1px solid rgba(34,197,94,.26);background:rgba(34,197,94,.08);border-radius:8px;padding:9px;color:#CFFAFE;font-size:11px;font-weight:900}}
    .nav{{display:flex;justify-content:space-between;gap:12px;margin-top:18px}}
    .nav button{{height:38px;border-radius:10px;border:1px solid #334155;background:#111827;color:#fff;padding:0 18px;font-weight:900;cursor:pointer}}
    .nav button.primary{{border-color:rgba(168,85,247,.7);background:rgba(168,85,247,.18);color:#E9D5FF}}
    .nav button:disabled{{opacity:.45;cursor:default}}
    @media(max-width:840px){{.step.active{{grid-template-columns:1fr}}h2{{font-size:30px}}body{{padding:16px}}}}
  </style>
</head>
<body>
  <main class="shell">
    <div class="top">
      <div>
        <h1>DVI EXECUTION QUEUE TRAINING</h1>
        <div class="sub">Self-contained advisor walkthrough - works with no live data</div>
      </div>
      <a class="btn live" href="/dvi">Back to Board</a>
    </div>
    <section class="panel">
      <div class="progress">
        <span id="counter">Step 1 of {len(steps)}</span>
        <div class="bar"><div class="fill" id="fill"></div></div>
      </div>
      {"".join(step_html)}
      <div class="nav">
        <button type="button" id="backBtn">Back</button>
        <button type="button" class="primary" id="nextBtn">Next</button>
      </div>
    </section>
  </main>
  <script>
    const steps = Array.from(document.querySelectorAll('.step'));
    let current = 0;
    function showStep(index) {{
      current = Math.max(0, Math.min(index, steps.length - 1));
      steps.forEach((step, i) => step.classList.toggle('active', i === current));
      document.getElementById('counter').textContent = 'Step ' + (current + 1) + ' of ' + steps.length;
      document.getElementById('fill').style.width = (((current + 1) / steps.length) * 100) + '%';
      document.getElementById('backBtn').disabled = current === 0;
      document.getElementById('nextBtn').textContent = current === steps.length - 1 ? 'Restart' : 'Next';
    }}
    document.getElementById('backBtn').addEventListener('click', () => showStep(current - 1));
    document.getElementById('nextBtn').addEventListener('click', () => showStep(current === steps.length - 1 ? 0 : current + 1));
    document.addEventListener('keydown', (event) => {{
      if (event.key === 'ArrowRight') showStep(current === steps.length - 1 ? 0 : current + 1);
      if (event.key === 'ArrowLeft') showStep(current - 1);
    }});
    showStep(0);
  </script>
</body>
</html>"""
