from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "state"
SHOP_STATE_FILE = STATE_DIR / "shop_state.json"
BOARD_STATE_FILE = STATE_DIR / "board_state.json"
ACTIVE_TECHS = {"luis cervantes", "jonathan leithoff", "johnathanl", "tc charleston", "steve chubb"}
ACTIVE_ADVISORS = {"mitch callahan", "drew mize", "admin user"}


def _normalize_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = _normalize_text(value, "").lower()
    return normalized in {"true", "1", "yes", "y", "complete", "completed", "closed", "done"}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _slugify_status(value: str) -> str:
    return _normalize_text(value, "unknown").lower().replace("/", " ").replace("-", " ").replace("_", " ").strip()


def _canonical_status(raw_status: str) -> str:
    normalized = _slugify_status(raw_status)
    aliases = {
        "call shop": "waiting approval",
        "call_shop": "waiting approval",
        "parts": "waiting parts",
        "part": "waiting parts",
        "finished": "ready",
        "complete": "ready",
        "completed": "ready",
        "drop off tow in": "drop off tow in",
        "online stage": "online stage",
    }
    return aliases.get(normalized, normalized)


def _normalize_owner_name(name: str) -> str:
    normalized = _normalize_text(name, "").lower()
    if normalized in {"mitch", "mitch callahan", "mcallahan"}:
        return "Mitch"
    if normalized in {"drew", "drew mize", "dmize"}:
        return "Drew"
    if normalized in {"preston", "preston callahan"}:
        return "Preston"
    return ""


def _split_people(value: Any) -> list[str]:
    text = _normalize_text(value, "")
    if not text:
        return []
    return [_normalize_text(part, "") for part in text.split(",") if _normalize_text(part, "")]


def _load_shop_state() -> dict[str, Any]:
    if not SHOP_STATE_FILE.exists():
        return {
            "source": "rules_evidence",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "count": 0,
            "jobs": [],
            "message": "No shop_state.json found. Run python scripts/build_shop_state.py first.",
        }

    try:
        payload = json.loads(SHOP_STATE_FILE.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass

    return {
        "source": "rules_evidence",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "count": 0,
        "jobs": [],
        "message": "Unable to read shop_state.json.",
    }


def _waiting_on(job: dict[str, Any], normalized_status: str) -> str:
    advisor_owner = _normalize_owner_name(job.get("advisor", ""))

    if normalized_status in {"technical advisement", "technical overview"}:
        return "Preston"

    if normalized_status in {"advisor estimate", "waiting approval", "ordering parts", "advisor finalize ro", "ready"}:
        return "Mitch"

    if normalized_status in {
        "online stage",
        "online  stage",
        "ready for tech",
        "testing",
        "dvi updates",
        "awaiting tech",
        "servicing",
        "qc",
        "advisor qc review",
        "drop off tow in",
    }:
        return "Drew"

    if normalized_status in {"waiting parts", "scheduled not here", "dvi only not here", "apache job"}:
        return "External Hold"

    if advisor_owner:
        return advisor_owner

    return "Needs Review"


def _priority_lane(job: dict[str, Any], normalized_status: str) -> str:
    progress = _to_int(job.get("progress_percent"), 0)
    labor_remaining = _to_float(job.get("labor_hours_remaining"), 0.0)
    complete = _to_bool(job.get("job_marked_complete")) or normalized_status in {"closed", "complete", "completed", "done"}

    if complete:
        return "P4"

    if normalized_status in {"waiting parts", "scheduled not here", "dvi only not here", "apache job", "appointment"}:
        return "P4"

    if normalized_status in {"technical advisement", "technical overview"}:
        return "P1"

    if normalized_status in {"advisor estimate", "waiting approval", "ordering parts", "dvi updates", "testing", "awaiting tech", "online stage", "drop off tow in"}:
        return "P2"

    if normalized_status in {"call shop", "unknown"}:
        return "P2"

    if progress >= 90 or (labor_remaining > 0 and labor_remaining <= 1):
        return "P1"

    if normalized_status in {"ready for tech", "servicing", "qc", "advisor qc review"}:
        return "P3"

    if normalized_status == "ready":
        return "P1"

    return "P3"


def _collect_alerts(job: dict[str, Any], normalized_status: str, waiting_on: str, lane: str) -> list[dict[str, str]]:
    alerts: list[dict[str, str]] = []
    ro = _normalize_text(job.get("ro"), "")
    technician_names = _split_people(job.get("technician", ""))
    known_active_tech = any(name.lower() in ACTIVE_TECHS for name in technician_names)
    summary = _normalize_text(job.get("summary"), "")
    notes = _normalize_text(job.get("notes"), "")
    dvi_status = _normalize_text(job.get("dvi_status"), "").lower()

    if not ro or ro.lower() in {"unknown ro", "0", "unknown"}:
        alerts.append(
            {
                "code": "missing_ro",
                "severity": "warning",
                "message": "Repair order number missing. Verify the AutoFlow item is linked to a real shop RO.",
            }
        )

    if waiting_on == "Drew" and normalized_status in {"ready for tech", "awaiting tech", "servicing", "testing", "dvi updates"}:
        if not _to_bool(job.get("clocked_in")):
            alerts.append(
                {
                    "code": "verify_tech_clock_in",
                    "severity": "warning" if lane == "P3" else "action",
                    "message": "No active technician clock-in detected. Quick floor check recommended.",
                }
            )

    if waiting_on == "Drew" and normalized_status in {"servicing", "ready for tech", "awaiting tech"} and not known_active_tech:
        alerts.append(
            {
                "code": "missing_tech_assignment",
                "severity": "warning",
                "message": "No clear active technician assignment is available in the current evidence. Verify dispatch and ownership on the floor.",
            }
        )

    if not technician_names or _normalize_text(job.get("technician"), "").lower() in {"", "unassigned", "unknown"}:
        alerts.append(
            {
                "code": "missing_info",
                "severity": "info" if lane == "P4" else "warning",
                "message": "Key operating info is incomplete. Confirm technician assignment and core ticket details.",
            }
        )

    if not summary and not notes:
        alerts.append(
            {
                "code": "missing_customer_concern",
                "severity": "warning" if lane in {"P1", "P2"} else "info",
                "message": "Customer concern detail is thin right now. Tighten the concern or summary so the next handoff is clearer.",
            }
        )
    elif len(summary) < 12 and len(notes) < 12:
        alerts.append(
            {
                "code": "missing_customer_concern",
                "severity": "info",
                "message": "Customer concern detail is light. A clearer write-up would help the board coach the next move better.",
            }
        )

    if normalized_status in {"dvi updates", "testing", "technical advisement", "advisor estimate", "waiting approval"}:
        if dvi_status not in {"complete", "completed", "signed off", "complete multi point check", "passed"}:
            alerts.append(
                {
                    "code": "missing_completed_dvi",
                    "severity": "warning",
                    "message": "Completed DVI evidence is missing or unclear. Confirm the inspection is finished and the findings are usable.",
                }
            )

    if waiting_on == "Mitch" and normalized_status in {"waiting approval", "advisor estimate", "ready", "advisor finalize ro"}:
        alerts.append(
            {
                "code": "customer_follow_up_due",
                "severity": "warning" if lane != "P1" else "action",
                "message": "Customer communication may be due. Confirm expectation, callback time, or closeout plan.",
            }
        )

    if waiting_on == "External Hold" and lane == "P4":
        alerts.append(
            {
                "code": "expectation_timer_needed",
                "severity": "info",
                "message": "External hold is acceptable, but it should carry a clear follow-up expectation.",
            }
        )

    if normalized_status == "unknown":
        alerts.append(
            {
                "code": "status_mapping_gap",
                "severity": "info",
                "message": "The current status could not be mapped cleanly. Review the AutoFlow evidence and tighten the board rules.",
            }
        )

    return alerts


def _risk_level(lane: str, alerts: list[dict[str, str]]) -> str:
    if lane == "P1":
        return "CRITICAL"
    if any(alert["severity"] == "action" for alert in alerts):
        return "RED"
    if lane == "P2" or any(alert["severity"] == "warning" for alert in alerts):
        return "YELLOW"
    return "NORMAL"


def _incoming_soon(job: dict[str, Any], normalized_status: str, lane: str) -> dict[str, Any] | None:
    progress = _to_int(job.get("progress_percent"), 0)
    labor_remaining = _to_float(job.get("labor_hours_remaining"), 0.0)

    if lane == "P4":
        return None

    if progress >= 75 or (labor_remaining > 0 and labor_remaining <= 2):
        return {
            "active": True,
            "reason": "Job appears to be within roughly two hours of its next handoff or completion.",
            "next_stage": "Advisor closeout and customer expectation prep",
        }

    if normalized_status in {"testing", "dvi updates", "advisor estimate", "waiting approval"}:
        return {
            "active": True,
            "reason": "Current status usually leads to an advisor handoff or customer conversation soon.",
            "next_stage": "Prepare the next customer-facing or production-control move",
        }

    if normalized_status in {"ready", "advisor finalize ro", "qc"}:
        return {
            "active": True,
            "reason": "This job is close to a customer-facing finish line and should be prepared before it becomes reactive.",
            "next_stage": "Land the plane and protect the delivery experience",
        }

    return None


def _next_action(job: dict[str, Any], waiting_on: str, lane: str, alerts: list[dict[str, str]], incoming_soon: dict[str, Any] | None) -> str:
    normalized_status = _canonical_status(_normalize_text(job.get("workflow_status"), "unknown"))

    if any(alert["code"] == "missing_ro" for alert in alerts):
        return "Link or confirm the RO number so the job can be tracked cleanly through the board."

    if any(alert["code"] == "verify_tech_clock_in" for alert in alerts):
        return "Touch base with the tech floor, verify who is actively on the job, and make sure labor is clocked."

    if waiting_on == "Preston":
        return "Provide a short escalation note so Preston can solve the blocker without a reactive phone call."

    if waiting_on == "Mitch":
        if normalized_status == "waiting approval":
            return "Prepare the next customer touch and tighten the approval plan before momentum drifts."
        if normalized_status == "advisor estimate":
            return "Finish the estimate package, set customer expectations, and keep the handoff moving."
        if normalized_status == "ordering parts":
            return "Get the parts plan locked in, set expectations clearly, and keep the repair from idling."
        if normalized_status in {"advisor finalize ro", "ready"}:
            return "Land the plane: finalize closeout, prep delivery, and protect customer trust."

    if waiting_on == "Drew":
        if normalized_status == "dvi updates":
            return "Run the DVI findings through the repair-planning flow and redispatch the next move quickly."
        if normalized_status == "awaiting tech":
            return "Check technician availability, confirm the next dispatch, and keep the job from stalling."
        if normalized_status == "ready for tech":
            return "Verify staging is complete and make sure the technician has everything needed to start cleanly."
        if normalized_status == "servicing":
            return "Check live progress, confirm the labor story matches the floor reality, and stay ahead of the next advisor handoff."

    if incoming_soon:
        return "Use the early warning to prepare the next handoff before the job becomes reactive."

    if lane == "P4":
        return "Keep the hold calm and documented, with a clear follow-up expectation."

    return "Take the next small step that removes uncertainty and keeps momentum moving."


def _build_job_state(job: dict[str, Any]) -> dict[str, Any]:
    raw_status = _normalize_text(job.get("workflow_status"), "unknown")
    normalized_status = _canonical_status(raw_status)
    waiting_on = _waiting_on(job, normalized_status)
    lane = _priority_lane(job, normalized_status)
    alerts = _collect_alerts(job, normalized_status, waiting_on, lane)
    incoming_soon = _incoming_soon(job, normalized_status, lane)
    technicians = _split_people(job.get("technician", ""))

    return {
        "ro": _normalize_text(job.get("ro"), "Unknown RO"),
        "customer": _normalize_text(job.get("customer"), "Unknown Customer"),
        "vehicle": _normalize_text(job.get("vehicle"), "Unknown Vehicle"),
        "workflow_status": raw_status,
        "canonical_status": normalized_status,
        "advisor": _normalize_text(job.get("advisor"), "Unknown"),
        "technician": _normalize_text(job.get("technician"), "Unassigned"),
        "technicians": technicians,
        "summary": _normalize_text(job.get("summary"), ""),
        "notes": _normalize_text(job.get("notes"), ""),
        "clocked_in": _to_bool(job.get("clocked_in")),
        "progress_percent": _to_int(job.get("progress_percent"), 0),
        "labor_hours_remaining": _to_float(job.get("labor_hours_remaining"), 0.0),
        "priority_lane": lane,
        "waiting_on": waiting_on,
        "risk_level": _risk_level(lane, alerts),
        "incoming_soon": incoming_soon,
        "alerts": alerts,
        "next_action": _next_action(job, waiting_on, lane, alerts, incoming_soon),
        "source_evidence": {
            "shop_state_generated_at": _normalize_text(job.get("generated_at"), ""),
            "location": _normalize_text(job.get("location"), "Unknown"),
            "dvi_status": _normalize_text(job.get("dvi_status"), "unknown"),
            "latest_activity": _normalize_text(job.get("latest_activity"), ""),
            "advisor_known": _normalize_text(job.get("advisor"), "").lower() in ACTIVE_ADVISORS,
            "active_tech_detected": any(name.lower() in ACTIVE_TECHS for name in technicians),
        },
    }


def build_board_state() -> dict[str, Any]:
    shop_state = _load_shop_state()
    raw_jobs = shop_state.get("jobs") if isinstance(shop_state, dict) else []
    jobs = [_build_job_state(job) for job in raw_jobs if isinstance(job, dict)]

    lane_counts = {lane: 0 for lane in ("P1", "P2", "P3", "P4")}
    owner_counts = {owner: 0 for owner in ("Mitch", "Drew", "Preston", "External Hold", "Needs Review")}
    open_alert_count = 0

    for job in jobs:
        lane_counts[job["priority_lane"]] = lane_counts.get(job["priority_lane"], 0) + 1
        owner_counts[job["waiting_on"]] = owner_counts.get(job["waiting_on"], 0) + 1
        open_alert_count += len(job["alerts"])

    return {
        "source": "board_rules_v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "shop_state_source": str(SHOP_STATE_FILE.relative_to(ROOT)),
        "count": len(jobs),
        "jobs": jobs,
        "lane_counts": lane_counts,
        "waiting_on_counts": owner_counts,
        "open_alert_count": open_alert_count,
        "message": shop_state.get("message", "") if isinstance(shop_state, dict) else "",
    }


def main() -> None:
    board_state = build_board_state()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    BOARD_STATE_FILE.write_text(json.dumps(board_state, indent=2), encoding="utf-8")
    print(BOARD_STATE_FILE)
    print(f"Jobs: {board_state['count']}")


if __name__ == "__main__":
    main()
