from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

APPROVAL_STALE_HOURS = 4
COMMS_RISK_HOURS = 6
OVERDUE_HOURS = 24
DISPATCH_STALE_HOURS = 2
STUCK_HOURS = 8

INACTIVE_STATUSES = {"apache job","close","closed"}
DREW_OWNED_STATUSES = {"online /stage","ready for tech","awaiting tech","testing","dvi updates","technical advisement","technical overview","servicing","qc","advisor qc review","advisor finalize ro","waiting parts"}
MITCH_OWNED_STATUSES = {"drop off/ tow-in","advisor estimate","waiting approval","ordering parts","ready"}
NEAR_CLOSEOUT_STATUSES = {"advisor finalize ro","advisor qc review","qc","ready"}
REAL_STATUSES = {
    "aaa", "call_shop", "checkin", "finished", "inspecting", "k_mech_complete",
    "parts", "qc", "ready", "servicing", "unknown", "waiting approval",
    "advisor estimate", "ordering parts", "waiting parts", "technical advisement",
    "dvi updates", "ready for tech", "awaiting tech", "testing", "advisor qc review",
    "advisor finalize ro", "technical overview", "scheduled-not here",
    "dvi only- not here", "drop off/ tow-in", "online /stage",
}
STATUS_DISPLAY_MAP = {
    "finished": "Ready to Close",
    "ready": "Ready — Notify Customer",
    "inspecting": "DVI In Progress",
    "checkin": "Checking In",
    "k_mech_complete": "Mech Complete — Advisor Action",
    "qc": "QC Review",
    "servicing": "In Service",
    "call_shop": "Customer Follow-Up",
    "parts": "Waiting on Parts",
    "ordering parts": "Parts Ordered",
    "waiting parts": "Parts Inbound",
    "waiting approval": "Waiting Customer Decision",
    "advisor estimate": "Building Estimate",
    "technical advisement": "Tech Advisement",
    "unknown": "Needs Review",
    "aaa": "Status Unknown — Fix in AutoFlow",
}
TRANSITIONS_PATH = Path(__file__).resolve().parents[1] / "data" / "status_transitions" / "transitions.jsonl"
RO_ACTIVITY_DIR = Path(__file__).resolve().parents[1] / "data" / "ro_activity"
latest_transition_by_ro = {}

READY_TO_CLOSE_STATUSES = {"finished", "ready", "advisor finalize ro"}
WAITING_CUSTOMER_STATUSES = {"waiting approval", "call_shop", "advisor estimate"}
WAITING_OTHER_STATUSES = {
    "waiting parts", "ordering parts", "parts", "external hold", "aaa",
    "unknown", "scheduled-not here", "dvi only-not here",
    "dvi only- not here",
}
IN_PROGRESS_STATUSES = {
    "servicing", "inspecting", "testing", "dvi updates", "ready for tech",
    "awaiting tech", "technical advisement", "technical overview",
    "k_mech_complete", "checkin", "qc", "advisor qc review",
    "drop off/tow-in", "drop off/ tow-in", "online/stage",
    "online /stage",
}
INBOUND_EVENT_TYPES = {"inbound_message", "ro_approval"}
OUTBOUND_EVENT_TYPES = {"dvi_sent"}
NEED_ACTION_SORT = {
    "ready_to_collect": 0,
    "customer_waiting": 1,
    "dvi_rework": 2,
}

def _now_utc():
    return datetime.now(timezone.utc)

def _parse_transition_received_at(value):
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)

def _ro_id(job):
    return str(
        job.get("ro")
        or job.get("ticket_reference")
        or job.get("invoice")
        or ""
    ).strip()

def _load_latest_transition_by_ro():
    latest = {}
    try:
        with TRANSITIONS_PATH.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ro = str(event.get("ro") or "").strip()
                received_at = _parse_transition_received_at(event.get("received_at"))
                if not ro or received_at is None:
                    continue

                current = latest.get(ro)
                if current is None or received_at > current:
                    latest[ro] = received_at
    except OSError:
        return {}
    return latest

def _refresh_transition_cache():
    global latest_transition_by_ro
    latest_transition_by_ro = _load_latest_transition_by_ro()

_refresh_transition_cache()

def _hours_since(dt_value):
    if not dt_value:
        return 999.0
    try:
        if isinstance(dt_value, datetime):
            ts = dt_value
        else:
            ts = datetime.fromisoformat(str(dt_value).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return round((_now_utc() - ts).total_seconds() / 3600, 1)
    except (ValueError, TypeError):
        return 999.0

def _normalize_status(raw):
    if not raw:
        return "unknown"
    return str(raw).strip().lower()

def _clean_status(status):
    return STATUS_DISPLAY_MAP.get(status, status)

def _is_inactive(status):
    return status in INACTIVE_STATUSES

def _has_dvi(job):
    return bool(job.get("dvi_completed") or job.get("dvi_signoff"))

def _has_customer_concern(job):
    reason = job.get("reason") or job.get("customer_concern") or ""
    return bool(str(reason).strip())

def _has_tech_assigned(job):
    return bool(job.get("technician") or job.get("tech_name"))

def _is_approved(job):
    approval = _normalize_status(job.get("approval_status", ""))
    return approval in {"approved","authorized","customer_approved","complete"}

def _parts_on_order(job):
    return bool(job.get("parts_ordered") and not job.get("parts_received"))

def _parts_arrived(job):
    return bool(job.get("parts_received"))

def _etc_hours_remaining(job):
    etc = job.get("etc") or job.get("promised_time")
    if not etc:
        return 999.0
    try:
        if isinstance(etc, datetime):
            ts = etc
        else:
            ts = datetime.fromisoformat(str(etc).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return round((ts - _now_utc()).total_seconds() / 3600, 1)
    except (ValueError, TypeError):
        return 999.0

def _last_update_hours(job):
    ro = _ro_id(job)
    transition_ts = latest_transition_by_ro.get(ro)
    if transition_ts is not None:
        return round((_now_utc() - transition_ts).total_seconds() / 3600, 1)
    return _hours_since(job.get("last_updated_at") or job.get("last_activity_at") or job.get("generated_at"))

def _read_ro_activity(ro):
    if not ro:
        return []
    path = RO_ACTIVITY_DIR / f"{ro}.jsonl"
    events = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                events.append(event)
    except OSError:
        return []
    return events

def _event_type(event):
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    payload_event = payload.get("event") if isinstance(payload.get("event"), dict) else {}
    return str(
        event.get("event_type")
        or payload_event.get("type")
        or ""
    ).strip().lower()

def _event_received_at(event):
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    return _parse_transition_received_at(
        event.get("received_at")
        or event.get("event_timestamp")
        or payload.get("timestamp")
    )

def _event_status(event):
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    ticket = payload.get("ticket") if isinstance(payload.get("ticket"), dict) else {}
    return _normalize_status(event.get("status") or ticket.get("status") or "")

def _direction_text(event):
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    candidates = [
        event.get("direction"),
        event.get("message_direction"),
        event.get("source"),
        message.get("direction"),
        message.get("status"),
    ]
    return " ".join(str(value).lower() for value in candidates if value)

def _is_inbound_event(event):
    return _event_type(event) in INBOUND_EVENT_TYPES

def _is_outbound_event(event):
    event_type = _event_type(event)
    if event_type in OUTBOUND_EVENT_TYPES:
        return True
    if event_type != "message_status":
        return False
    direction = _direction_text(event)
    if any(token in direction for token in ("inbound", "customer_reply", "from_customer")):
        return False
    return True

def _latest_activity_event(activity):
    latest = None
    latest_ts = None
    for event in activity:
        ts = _event_received_at(event)
        if ts is None:
            continue
        if latest_ts is None or ts > latest_ts:
            latest = event
            latest_ts = ts
    return latest

def _status_started_at(status, activity):
    latest_ts = None
    for event in activity:
        event_status = _event_status(event)
        if event_status != status:
            continue
        ts = _event_received_at(event)
        if ts is None:
            continue
        if latest_ts is None or ts > latest_ts:
            latest_ts = ts
    return latest_ts

def _has_outbound_since(activity, since_ts):
    if since_ts is None:
        return False
    for event in activity:
        ts = _event_received_at(event)
        if ts is None or ts < since_ts:
            continue
        if _is_outbound_event(event):
            return True
    return False

def _format_hours(hours):
    if hours >= 24:
        days = int(hours // 24)
        rem = int(hours % 24)
        return f"{days}d {rem}h" if rem else f"{days}d"
    if hours >= 1:
        return f"{int(hours)}h"
    minutes = max(0, int(hours * 60))
    return f"{minutes}m"

def _is_dvi_rework_unacknowledged(job):
    dvi_status = str(job.get("dvi_review_status") or "").strip().upper()
    dvi_acknowledged = bool(
        job.get("dvi_acknowledged")
        or job.get("dvi_review_acknowledged")
        or job.get("acknowledged")
        or job.get("dvi_rework_override")
    )
    return "REWORK" in dvi_status and not dvi_acknowledged

def _p1_gate(status, job, flags, activity, hours_in_status):
    if status in {"finished", "ready"} and activity:
        status_start = _status_started_at(status, activity)
        if status_start is not None and not _has_outbound_since(activity, status_start):
            return (
                True,
                "ready_to_collect",
                f"Ready to collect - no outbound contact since {status} {_format_hours(hours_in_status)} ago",
            )

    latest_event = _latest_activity_event(activity)
    if latest_event and _is_inbound_event(latest_event):
        event_type = _event_type(latest_event) or "inbound event"
        return (
            True,
            "customer_waiting",
            f"Customer waiting - last event {event_type.replace('_', ' ')}",
        )

    if _is_dvi_rework_unacknowledged(job):
        return True, "dvi_rework", "DVI rework unacknowledged"

    return False, "", ""

def _status_based_column(status, job, priority):
    waiting_on = str(job.get("waiting_on") or "").strip().lower()
    if priority == "P1":
        return "Need Immediate Action"
    if status in READY_TO_CLOSE_STATUSES:
        return "Ready to Close"
    if status in {"waiting parts", "ordering parts", "parts"}:
        return "Parts / Inventory"
    if status in WAITING_CUSTOMER_STATUSES:
        return "Waiting / Customer"
    if (
        status in WAITING_OTHER_STATUSES
        or "external" in waiting_on
        or "needs review" in waiting_on
        or "needs review" in status
    ):
        return "Waiting / Other"
    if status in IN_PROGRESS_STATUSES:
        return "In Progress"
    return "In Progress"

def _fallback_priority_reason(status, job):
    waiting_on = str(job.get("waiting_on") or "").strip().lower()
    if status in {"checkin", "drop off/tow-in", "drop off/ tow-in", "online/stage", "online /stage"}:
        if not _has_customer_concern(job):
            return "P2A", "Checked in - no customer concern captured"
        return "P3", "Checked in - intake captured"
    if status in {"awaiting tech", "ready for tech", "testing", "dvi updates", "inspecting"}:
        return "P2B", "Awaiting tech or DVI progress"
    if status in {"advisor estimate", "waiting approval", "call_shop"}:
        if status == "waiting approval":
            return "P2C", "Waiting on customer approval"
        if status == "call_shop":
            return "P2C", "Advisor follow-up needed"
        return "P2C", "Advisor estimate needs action"
    if status in {"technical advisement", "technical overview", "qc", "advisor qc review", "k_mech_complete"}:
        return "P2C", "Advisor or technical review needed"
    if (
        status in WAITING_OTHER_STATUSES
        or "external" in waiting_on
        or "needs review" in waiting_on
        or "needs review" in status
    ):
        return "P4", "Legitimate external hold or status cleanup"
    if status in READY_TO_CLOSE_STATUSES:
        return "P3", "Ready to close - outbound contact handled or not yet proven missing"
    if _has_tech_assigned(job):
        return "P3", "In progress - tech assigned"
    return "P3", "Active and controlled"

def _last_customer_contact_hours(job):
    return _hours_since(job.get("last_customer_contact_at"))

def _determine_owner(status, job):
    if status in MITCH_OWNED_STATUSES:
        return "Mitch"
    if status in DREW_OWNED_STATUSES:
        return "Drew"
    if status in {"technical advisement","technical overview"}:
        return "Preston"
    return "Unknown"

def _detect_risk_flags(status, job):
    flags = []
    hours_since_customer = _last_customer_contact_hours(job)
    hours_since_update = _last_update_hours(job)
    etc_remaining = _etc_hours_remaining(job)
    if hours_since_customer > COMMS_RISK_HOURS and status in {"waiting approval","ordering parts","waiting parts","servicing"}:
        flags.append("customer_contact_overdue")
    if not _has_dvi(job) and status in {"technical advisement","advisor estimate","waiting approval","ordering parts","waiting parts","servicing"}:
        flags.append("dvi_missing")
    if not _has_customer_concern(job):
        flags.append("no_customer_concern")
    if not _has_tech_assigned(job) and status in {"ready for tech","awaiting tech","testing","servicing"}:
        flags.append("no_tech_assigned")
    if _parts_on_order(job):
        flags.append("waiting_on_parts")
    if etc_remaining < 0 and status not in NEAR_CLOSEOUT_STATUSES:
        flags.append("etc_overdue")
    if 0 < etc_remaining <= 2:
        flags.append("etc_approaching")
    if hours_since_update > STUCK_HOURS and status not in INACTIVE_STATUSES:
        flags.append("no_movement")
    if status == "waiting approval" and hours_since_update > APPROVAL_STALE_HOURS:
        flags.append("approval_stale")
    if status == "awaiting tech" and hours_since_update > DISPATCH_STALE_HOURS:
        flags.append("dispatch_stale")
    if status == "ready" and hours_since_update > 2:
        flags.append("ready_not_collected")
    return flags

def _assign_priority(status, job, flags):
    hours_in_status = _last_update_hours(job)
    try:
        activity = _read_ro_activity(_ro_id(job))
        gate_passed, gate_kind, gate_reason = _p1_gate(
            status, job, flags, activity, hours_in_status
        )
        if gate_passed:
            return "P1", gate_reason, gate_kind

        priority, reason = _fallback_priority_reason(status, job)
        return priority, reason, ""
    except Exception:
        priority, _reason = _fallback_priority_reason(status, job)
        return priority, "default (incomplete data)", ""

def _build_next_action(priority, status, owner, flags, job):
    ro = job.get("ro") or "this RO"
    customer = job.get("customer_name") or "customer"
    if priority == "P1":
        if _is_dvi_rework_unacknowledged(job):
            return "Review DVI rework - acknowledge, correct, or send back to tech"
        if status == "ready":
            return f"Call {customer} - vehicle is ready, collect payment and close out"
        if status == "finished":
            return f"Call {customer} - repairs are complete, collect payment and close out"
        if status in {"advisor finalize ro","advisor qc review"}:
            return "Finalize RO - clean notes, confirm charges, prepare invoice"
        if status == "qc":
            return "Complete QC - verify repairs, confirm photos and notes are done"
        if "approval_stale" in flags:
            return f"Call {customer} now - approval has been waiting too long"
        if "etc_overdue" in flags:
            return f"Call {customer} - promise time has passed, reset expectations"
        if "etc_approaching" in flags:
            return "Confirm job will be done on time - ETC is within 2 hours"
        if "customer_contact_overdue" in flags:
            return f"Update {customer} - no contact in over {COMMS_RISK_HOURS} hours"
        if "ready_not_collected" in flags:
            return f"Notify {customer} - vehicle is ready for pickup"
        return f"Immediate attention needed on {ro} - see risk flags"
    if priority == "P2A":
        return f"Capture customer concern for {ro} - job cannot move without clear intake"
    if priority == "P2B":
        if "dispatch_stale" in flags:
            return f"Assign tech to {ro} - dispatch has been waiting too long"
        if "dvi_missing" in flags:
            return f"Confirm DVI is underway for {ro} - no completion signal yet"
        return f"Monitor tech progress on {ro} - stay 3-5 steps ahead"
    if priority == "P2C":
        if "dvi_missing" in flags:
            return f"DVI must be complete before estimate can be built for {ro}"
        if status in {"technical advisement","technical overview"}:
            return f"Get technical direction on {ro} - advisor is blocked without it"
        return f"Advisor needs more information before {ro} can move forward"
    if priority == "P3":
        if "no_movement" in flags:
            return f"Check on {ro} - no movement in {_last_update_hours(job):.0f}h"
        if status == "servicing":
            return f"Monitor tech progress on {ro} - confirm no blockers"
        if status == "waiting parts":
            return f"Confirm parts ETA for {ro} - update customer if delay"
        return f"Keep {ro} moving - status is {status}"
    if priority == "P4":
        if status == "waiting parts":
            return f"Monitor parts ETA for {ro} - notify {customer} of any delay"
        if status == "waiting approval":
            return f"Waiting on {customer} decision - follow up if no response soon"
        return f"External hold on {ro} - document and monitor"
    return f"Review {ro}"

def _build_bay_message(priority, status, flags, job):
    customer = job.get("customer_name") or "Customer"
    if status == "ready":
        return f"{customer} notified - vehicle ready for pickup"
    if status == "waiting approval":
        if "approval_stale" in flags:
            return f"Advisor following up with {customer} - waiting on decision"
        return f"Advisor contacted {customer} - waiting on approval"
    if status == "waiting parts":
        return f"Parts on order - advisor monitoring ETA for {customer}"
    if status == "servicing":
        return "Repairs in progress - tech on the vehicle"
    if status == "awaiting tech":
        return "Ready for tech - Drew assigning now"
    if status in {"testing","dvi updates"}:
        return "Tech inspecting vehicle - DVI in progress"
    if status in {"qc","advisor qc review"}:
        return "Quality check in progress - almost done"
    if status == "advisor finalize ro":
        return "Advisor finalizing paperwork - vehicle nearly ready"
    if status == "advisor estimate":
        return "Advisor building estimate - waiting on customer presentation"
    if status == "ordering parts":
        return "Parts being sourced - advisor has this"
    if priority == "P2A":
        return "Waiting on intake - advisor needs more information"
    if priority == "P1":
        return "Needs immediate attention - see advisor"
    return f"In progress - {status}"

def _board_signal(priority, flags):
    if priority == "P1":
        if "ready_not_collected" in flags or "etc_approaching" in flags:
            return "money"
        if "customer_contact_overdue" in flags or "approval_stale" in flags:
            return "comms"
        return "fire"
    if priority in {"P2A","P2B","P2C"}:
        return "blocked"
    if priority == "P3" and "no_movement" in flags:
        return "blocked"
    return "clear"

def score_job(job):
    try:
        raw_status = job.get("workflow_status") or job.get("current_status") or "unknown"
        status = _normalize_status(raw_status)
        hours_in_status = _last_update_hours(job)
    except Exception:
        raw_status = "unknown"
        status = "unknown"
        hours_in_status = 999.0
    if _is_inactive(status):
        return {
            "ticket_reference": _ro_id(job),
            "priority": "INACTIVE",
            "priority_lane": "INACTIVE",
            "priority_reason": f"Status '{raw_status}' is inactive - excluded from board",
            "owner": "None",
            "board_signal": "clear",
            "next_action": "Job is not active - no action needed",
            "bay_message": "",
            "risk_flags": [],
            "score_reason": f"Status '{raw_status}' is inactive - excluded from board",
            "hours_in_status": hours_in_status,
            "stale": hours_in_status > OVERDUE_HOURS,
            "clean_status": _clean_status(status),
        }
    try:
        flags = _detect_risk_flags(status, job)
        priority, reason, need_action_kind = _assign_priority(status, job, flags)
        owner = _determine_owner(status, job)
        next_action = _build_next_action(priority, status, owner, flags, job)
        bay_message = _build_bay_message(priority, status, flags, job)
        signal = _board_signal(priority, flags)
    except Exception:
        flags = []
        priority, reason = _fallback_priority_reason(status, job)
        reason = "default (incomplete data)"
        need_action_kind = ""
        owner = _determine_owner(status, job)
        next_action = f"Review {_ro_id(job) or 'this RO'} - incomplete data"
        bay_message = "Incomplete data - review in AutoFlow"
        signal = "blocked" if priority.startswith("P2") else "clear"

    column = _status_based_column(status, job, priority)
    if hours_in_status > OVERDUE_HOURS and "24H NO MOVEMENT" not in flags:
        flags.append("24H NO MOVEMENT")
    return {
        "ticket_reference": _ro_id(job),
        "customer_name": job.get("customer_name", ""),
        "vehicle": job.get("vehicle", ""),
        "advisor_name": job.get("advisor_name") or job.get("service_writer", ""),
        "technician": job.get("technician") or job.get("tech_name", ""),
        "priority": priority,
        "priority_lane": priority,
        "priority_reason": reason,
        "score_reason": reason,
        "need_action_kind": need_action_kind,
        "column": column,
        "owner": owner,
        "board_signal": signal,
        "next_action": next_action,
        "bay_message": bay_message,
        "risk_flags": flags,
        "autoflow_status": raw_status,
        "hours_in_status": hours_in_status,
        "stale": hours_in_status > OVERDUE_HOURS,
        "clean_status": _clean_status(status),
        "etc_hours_remaining": _etc_hours_remaining(job),
        "has_dvi": _has_dvi(job),
        "parts_on_order": _parts_on_order(job),
        "parts_arrived": _parts_arrived(job),
        "is_approved": _is_approved(job),
    }

def score_all_jobs(shop_state):
    _refresh_transition_cache()
    priority_order = {"P1": 0, "P2": 1, "P2A": 1, "P2B": 2, "P2C": 3, "P3": 4, "P4": 5}
    scored = []
    for job in shop_state.get("jobs", []):
        result = score_job(job)
        if result["priority"] != "INACTIVE":
            scored.append(result)
    scored.sort(key=lambda r: (
        priority_order.get(r["priority"], 9),
        NEED_ACTION_SORT.get(r.get("need_action_kind", ""), 9),
        0 if r.get("stale") else 1,
        -r["hours_in_status"],
    ))
    column_counts = {}
    for result in scored:
        column = result.get("column", "Unknown")
        column_counts[column] = column_counts.get(column, 0) + 1
    counts = ", ".join(
        f"{column}={count}" for column, count in sorted(column_counts.items())
    )
    p1_lines = [
        f"{result.get('ticket_reference')} - {result.get('priority_reason')}"
        for result in scored
        if result.get("priority") == "P1"
    ]
    print(f"Scoring lane summary: {counts}")
    print("Need Immediate Action: " + ("; ".join(p1_lines) if p1_lines else "none"))
    return scored
