from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "state"
ACTIVE_ROS_FILE = STATE_DIR / "active_ros.json"
SHOP_STATE_FILE = STATE_DIR / "shop_state.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from connectors import autoflow


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _first_value(item: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, "", [], {}):
            return value
    return default


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if value is None:
        return False

    normalized = str(value).strip().lower()
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


def _normalize_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _derive_priority(job: dict[str, Any]) -> str:
    workflow_status = _normalize_text(job.get("workflow_status", ""), "").lower()
    clocked_in = _to_bool(job.get("clocked_in"))
    job_marked_complete = _to_bool(job.get("job_marked_complete"))
    labor_hours_remaining = _to_float(job.get("labor_hours_remaining"), 0.0)
    progress_percent = _to_int(job.get("progress_percent"), 0)

    if job_marked_complete or workflow_status in {"complete", "completed", "closed", "done"} or progress_percent >= 100:
        return "P4"

    if (not clocked_in) and labor_hours_remaining > 3:
        return "P1"

    if clocked_in and progress_percent < 25:
        return "P2"

    if progress_percent < 100:
        return "P3"

    return "P4"


def _normalize_job(item: dict[str, Any]) -> dict[str, Any]:
    ro = _normalize_text(
        _first_value(
            item,
            "ro",
            "ro_number",
            "ticket_reference",
            "repair_order",
            "repairOrder",
            "work_order_number",
            default="",
        ),
        "Unknown RO",
    )

    advisor = _normalize_text(
        _first_value(item, "advisor", "advisor_name", "advisorName", "service_advisor", default=""),
        "Unknown",
    )

    technician = _normalize_text(
        _first_value(
            item,
            "technician",
            "technician_name",
            "technicianName",
            "tech",
            "tech_name",
            "assignedTechName",
            "tech_display",
            "assignedTo",
            "assigned_to",
            "assigned_technician",
            default="",
        ),
        "Unassigned",
    )
    technician_candidates = _as_list(_first_value(item, "technician_candidates", default=[]))
    if technician == "Unassigned" and technician_candidates:
        technician = _normalize_text(technician_candidates[0], "Unassigned")

    customer = _normalize_text(
        _first_value(item, "customer", "customer_name", "customerName", default=""),
        "",
    )

    vehicle = _normalize_text(
        _first_value(item, "vehicle", "vehicle_name", "vehicleDescription", "vehicle_description", default=""),
        "",
    )

    bay = _normalize_text(
        _first_value(item, "bay", "bay_name", "bayNumber", "bay_number", default=""),
        "",
    )

    workflow_status = _normalize_text(
        _first_value(item, "workflow_status", "workflowStatus", "status", "job_status", default="unknown"),
        "unknown",
    )

    notes = _normalize_text(
        _first_value(item, "notes", "additional_notes", default=""),
        "",
    )

    latest_activity = _normalize_text(
        _first_value(item, "latest_activity", "latestActivity", default=""),
        "",
    )

    summary = _normalize_text(
        _first_value(item, "summary", "issue", "concern", "description", default=""),
        notes or latest_activity or workflow_status.replace("_", " ").title(),
    )
    reason_vehicle_is_here = _as_list(_first_value(item, "reason_vehicle_is_here", default=[]))

    normalized_job = {
        "ro": ro,
        "workflow_status": workflow_status,
        "advisor": advisor,
        "technician": technician,
        "technician_candidates": technician_candidates,
        "customer": customer,
        "vehicle": vehicle,
        "bay": bay,
        "summary": summary,
        "notes": notes,
        "reason_vehicle_is_here": reason_vehicle_is_here,
        "progress_percent": _to_int(
            _first_value(item, "progress_percent", "progressPercent", "percent_complete", default=0),
            0,
        ),
        "clocked_in": _to_bool(_first_value(item, "clocked_in", "clockedIn", default=False)),
        "job_marked_complete": _to_bool(
            _first_value(item, "job_marked_complete", "jobMarkedComplete", "isComplete", default=False)
        ),
        "labor_hours_remaining": _to_float(
            _first_value(item, "labor_hours_remaining", "laborHoursRemaining", "remaining_labor_hours", default=0.0),
            0.0,
        ),
        "approval_status": _normalize_text(
            _first_value(item, "approval_status", "approvalStatus", default="unknown"),
            "unknown",
        ),
        "location": _normalize_text(_first_value(item, "location", "locationName", default="Unknown"), "Unknown"),
        "latest_activity": latest_activity,
        "dvi_status": _normalize_text(_first_value(item, "dvi_status", default="unknown"), "unknown"),
        "dvi_completed": _to_bool(_first_value(item, "dvi_completed", default=False)),
        "source_refs": item.get("source_refs") if isinstance(item.get("source_refs"), dict) else {},
    }
    normalized_job["priority"] = _derive_priority(normalized_job)
    return normalized_job


def _normalize_payload(payload: dict[str, Any], active_ro_source: str) -> dict[str, Any]:
    raw_jobs = _as_list(payload.get("jobs"))
    if not raw_jobs:
        raw_jobs = _as_list(payload.get("records"))

    jobs = []
    for item in raw_jobs:
        if isinstance(item, dict):
            jobs.append(_normalize_job(item))

    return {
        "source": payload.get("source", "autoflow"),
        "generated_at": payload.get("generated_at", datetime.now(timezone.utc).isoformat()),
        "active_ro_source": active_ro_source,
        "count": len(jobs),
        "jobs": jobs,
        "skipped_ros": payload.get("skipped_ros", []),
        "message": payload.get("fallback_reason", payload.get("message", "")),
    }


def _empty_shop_state(message: str) -> dict[str, Any]:
    return {
        "source": "rules_evidence",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "active_ro_source": str(ACTIVE_ROS_FILE.relative_to(ROOT)),
        "count": 0,
        "jobs": [],
        "skipped_ros": [],
        "message": message,
    }


def _load_active_ros() -> list[str]:
    if not ACTIVE_ROS_FILE.exists():
        return []

    try:
        payload = json.loads(ACTIVE_ROS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []

    if not isinstance(payload, dict):
        return []

    active_ros = payload.get("active_ros")
    if not isinstance(active_ros, list):
        return []

    normalized = []
    for ro in active_ros:
        text = _normalize_text(ro, "")
        if text:
            normalized.append(text)
    return normalized


def _fetch_live_jobs(active_ros: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    jobs: list[dict[str, Any]] = []
    skipped_ros: list[dict[str, str]] = []

    for ro in active_ros:
        try:
            work_order = autoflow.get_work_order(ro)
            dvi = autoflow.get_dvi(ro)
            jobs.append(_normalize_job(autoflow.merge_work_order_and_dvi(work_order, dvi, ro)))
        except Exception as exc:
            skipped_ros.append({"ro": ro, "reason": str(exc)})

    return jobs, skipped_ros


def build_shop_state() -> dict[str, Any]:
    active_ro_source = str(ACTIVE_ROS_FILE.relative_to(ROOT))
    active_ros = _load_active_ros()
    if not active_ros:
        return _empty_shop_state("No active RO state found. Run python scripts/build_active_ros_state.py first.")

    jobs, skipped_ros = _fetch_live_jobs(active_ros)
    message = ""
    if skipped_ros:
        message = f"Skipped {len(skipped_ros)} RO(s) during live AutoFlow enrichment."

    return {
        "source": "rules_evidence",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "active_ro_source": active_ro_source,
        "count": len(jobs),
        "jobs": jobs,
        "skipped_ros": skipped_ros,
        "message": message,
    }


def main() -> None:
    state = build_shop_state()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SHOP_STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(SHOP_STATE_FILE)
    print(f"Jobs: {state['count']}")


if __name__ == "__main__":
    main()
