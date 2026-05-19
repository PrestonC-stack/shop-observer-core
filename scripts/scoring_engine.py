"""
scoring_engine.py
Callahan Auto & Diesel - Shop Observer Core
Branch: ai-build-stabilization
Location: scripts/scoring_engine.py

PURPOSE:
    Takes a normalized job dict (from shop_state.json) and returns a scored
    result: P1/P2A/P2B/P2C/P3/P4, owner, next action, risk flags, and a
    plain-English board message.

RULES SOURCE:
    Hermes Shop Intelligence Training Master File
    (Preston Callahan decision model - do not change rules without updating
    that document and this file together.)

DESIGN RULES:
    - Read-only. Never writes to AutoFlow or any live system.
    - Every rule is named and commented so Preston can read and verify it.
    - No hidden logic. If it scores P1, you can see exactly why.
    - Scores are deterministic - same input always produces same output.

USAGE:
    from scripts.scoring_engine import score_job

    scored = score_job(job)
    # scored["priority"]     -> "P1" | "P2A" | "P2B" | "P2C" | "P3" | "P4"
    # scored["owner"]        -> "Mitch" | "Drew" | "Preston" | "Tech" | "External"
    # scored["next_action"]  -> plain English string
    # scored["board_signal"] -> "fire" | "blocked" | "comms" | "money" | "clear"
    # scored["bay_message"]  -> what the 65" TV shows techs
    # scored["risk_flags"]   -> list of active risk strings
    # scored["score_reason"] -> why this priority was assigned
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# CONSTANTS - edit here if thresholds need tuning
# ---------------------------------------------------------------------------

APPROVAL_STALE_HOURS = 4
COMMS_RISK_HOURS = 6
OVERDUE_HOURS = 24
DISPATCH_STALE_HOURS = 2
STUCK_HOURS = 8

INACTIVE_STATUSES = {
    "scheduled-not here",
    "dvi only- not here",
    "apache job",
    "close",
    "closed",
}

DREW_OWNED_STATUSES = {
    "online /stage",
    "ready for tech",
    "awaiting tech",
    "testing",
    "dvi updates",
    "technical advisement",
    "technical overview",
    "servicing",
    "qc",
    "advisor qc review",
    "advisor finalize ro",
    "waiting parts",
}

MITCH_OWNED_STATUSES = {
    "drop off/ tow-in",
    "advisor estimate",
    "waiting approval",
    "ordering parts",
    "ready",
}

NEAR_CLOSEOUT_STATUSES = {
    "advisor finalize ro",
    "advisor qc review",
    "qc",
    "ready",
}


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _hours_since(dt_value: Any) -> float:
    if not dt_value:
        return 999.0
    try:
        if isinstance(dt_value, datetime):
            ts = dt_value
        else:
            ts = datetime.fromisoformat(str(dt_value).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        delta = _now_utc() - ts
        return round(delta.total_seconds() / 3600, 1)
    except (ValueError, TypeError):
        return 999.0


def _normalize_status(raw: Any) -> str:
    if not raw:
        return "unknown"
    return str(raw).strip().lower()


def _is_inactive(status: str) -> bool:
    return status in INACTIVE_STATUSES


def _has_dvi(job: dict) -> bool:
    return bool(job.get("dvi_completed") or job.get("dvi_signoff"))


def _has_customer_concern(job: dict) -> bool:
    reason = job.get("reason") or job.get("customer_concern") or ""
    return bool(str(reason).strip())


def _has_tech_assigned(job: dict) -> bool:
    return bool(job.get("technician") or job.get("tech_name"))


def _is_approved(job: dict) -> bool:
    approval = _normalize_status(job.get("approval_status", ""))
    return approval in {"approved", "authorized", "customer_approved", "complete"}


def _parts_on_order(job: dict) -> bool:
    return bool(job.get("parts_ordered") and not job.get("parts_received"))


def _parts_arrived(job: dict) -> bool:
    return bool(job.get("parts_received"))


def _etc_hours_remaining(job: dict) -> float:
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
        delta = ts - _now_utc()
        return round(delta.total_seconds() / 3600, 1)
    except (ValueError, TypeError):
        return 999.0


def _last_update_hours(job: dict) -> float:
    return _hours_since(
        job.get("last_updated_at")
        or job.get("last_activity_at")
        or job.get("generated_at")
    )


def _last_customer_contact_hours(job: dict) -> float:
    return _hours_since(job.get("last_customer_contact_at"))


def _determine_owner(status: str, job: dict) -> str:
    if status in MITCH_OWNED_STATUSES:
        return "Mitch"
    if status in DREW_OWNED_STATUSES:
        return "Drew"
    if status in {"technical advisement", "technical overview"}:
        return "Preston"
    return "Unknown"


def _detect_risk_flags(status: str, job: dict) -> list[str]:
    flags: list[str] = []
    hours_since_update = _last_update_hours(job)
    hours_since_customer = _last_customer_contact_hours(job)
    etc_remaining = _etc_hours_remaining(job)

    if hours_since_customer > COMMS_RISK_HOURS and status in {
        "waiting approval", "ordering parts", "waiting parts", "servicing"
    }:
        flags.append("customer_contact_overdue")

    if not _has_dvi(job) and status in {
        "technical advisement", "advisor estimate", "waiting approval",
        "ordering parts", "waiting parts", "servicing"
    }:
        flags.append("dvi_missing")

    if not _has_customer_concern(job):
        flags.append("no_customer_concern")

    if not _has_tech_assigned(job) and status in {
        "ready for tech", "awaiting tech", "testing", "servicing"
    }:
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


def _assign_priority(status: str, job: dict, flags: list[str]) -> tuple[str, str]:
    if status in NEAR_CLOSEOUT_STATUSES:
        return "P1", "Near closeout - vehicle ready to collect or finalize"
    if "etc_overdue" in flags:
        return "P1", "ETC overdue - customer promise is broken, call now"
    if "etc_approaching" in flags:
        return "P1", "ETC approaching within 2 hours - advisor must prepare now"
    if "approval_stale" in flags:
        return "P1", f"Approval waiting {_last_update_hours(job):.0f}h - customer contact overdue"
    if "ready_not_collected" in flags:
        return "P1", "Vehicle marked Ready - customer not notified or pickup delayed"
    if "customer_contact_overdue" in flags:
        return "P1", "Customer update overdue - risk of customer calling first"
    if "no_customer_concern" in flags and status in {
        "online /stage", "ready for tech", "awaiting tech",
        "testing", "drop off/ tow-in", "unknown"
    }:
        return "P2A", "No customer concern captured - job cannot move without intake"
    if status == "unknown":
        return "P2A", "Status unknown - nobody can explain what this job is waiting on"
    if status in {"ready for tech", "awaiting tech"} and "dispatch_stale" in flags:
        return "P2B", "Awaiting tech too long - dispatch is stuck"
    if status in {"testing", "dvi updates"} and "dvi_missing" in flags:
        return "P2B", "In testing/DVI but no DVI completion signal yet"
    if status in {"ready for tech", "awaiting tech", "testing", "dvi updates"}:
        return "P2B", "Waiting on tech or DVI - advisor should stay ahead"
    if status == "advisor estimate" and "dvi_missing" in flags:
        return "P2C", "Advisor estimate stage but DVI not complete - cannot build estimate"
    if status in {"technical advisement", "technical overview"}:
        return "P2C", "Waiting on technical direction before advisor can proceed"
    if status == "waiting parts" and _parts_on_order(job) and not _parts_arrived(job):
        return "P4", "Waiting on external parts - legitimate hold (Drew monitors ETA)"
    if status == "waiting approval" and "approval_stale" not in flags:
        return "P4", "Waiting on customer decision - advisor has made contact"
    if "no_movement" in flags:
        return "P3", f"Active but no movement in {_last_update_hours(job):.0f}h - watch this"
    return "P3", f"Active and progressing - status: {status}"


def _build_next_action(priority: str, status: str, owner: str, flags: list[str], job: dict) -> str:
    ro = job.get("ticket_reference") or job.get("invoice") or "this RO"
    customer = job.get("customer_name") or "customer"

    if priority == "P1":
        if status == "ready":
            return f"Call {customer} - vehicle is ready, collect payment and close out"
        if status in {"advisor finalize ro", "advisor qc review"}:
            return "Finalize RO - clean notes, confirm charges, prepare invoice"
        if status == "qc":
            return "Complete QC - verify repairs, confirm photos and notes are done"
        if "approval_stale" in flags:
            return f"Call {customer} now - approval has been waiting too long"
        if "etc_overdue" in flags:
            return f"Call {customer} - promise time has passed, reset expectations"
        if "etc_approaching" in flags:
            return "Confirm job will be done oncd "C:\AI-RUNTIME\shop-observer-core"

git checkout ai-build-stabilization

$content = @'
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any

APPROVAL_STALE_HOURS = 4
COMMS_RISK_HOURS = 6
OVERDUE_HOURS = 24
DISPATCH_STALE_HOURS = 2
STUCK_HOURS = 8

INACTIVE_STATUSES = {"scheduled-not here","dvi only- not here","apache job","close","closed"}

DREW_OWNED_STATUSES = {"online /stage","ready for tech","awaiting tech","testing","dvi updates","technical advisement","technical overview","servicing","qc","advisor qc review","advisor finalize ro","waiting parts"}

MITCH_OWNED_STATUSES = {"drop off/ tow-in","advisor estimate","waiting approval","ordering parts","ready"}

NEAR_CLOSEOUT_STATUSES = {"advisor finalize ro","advisor qc review","qc","ready"}

def _now_utc():
    return datetime.now(timezone.utc)

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
    return _hours_since(job.get("last_updated_at") or job.get("last_activity_at") or job.get("generated_at"))

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
    if status in NEAR_CLOSEOUT_STATUSES:
        return "P1", "Near closeout - vehicle ready to collect or finalize"
    if "etc_overdue" in flags:
        return "P1", "ETC overdue - customer promise is broken, call now"
    if "etc_approaching" in flags:
        return "P1", "ETC approaching within 2 hours - advisor must prepare now"
    if "approval_stale" in flags:
        return "P1", f"Approval waiting {_last_update_hours(job):.0f}h - customer contact overdue"
    if "ready_not_collected" in flags:
        return "P1", "Vehicle marked Ready - customer not notified or pickup delayed"
    if "customer_contact_overdue" in flags:
        return "P1", "Customer update overdue - risk of customer calling first"
    if "no_customer_concern" in flags and status in {"online /stage","ready for tech","awaiting tech","testing","drop off/ tow-in","unknown"}:
        return "P2A", "No customer concern captured - job cannot move without intake"
    if status == "unknown":
        return "P2A", "Status unknown - nobody can explain what this job is waiting on"
    if status in {"ready for tech","awaiting tech"} and "dispatch_stale" in flags:
        return "P2B", "Awaiting tech too long - dispatch is stuck"
    if status in {"testing","dvi updates"} and "dvi_missing" in flags:
        return "P2B", "In testing/DVI but no DVI completion signal yet"
    if status in {"ready for tech","awaiting tech","testing","dvi updates"}:
        return "P2B", "Waiting on tech or DVI - advisor should stay ahead"
    if status == "advisor estimate" and "dvi_missing" in flags:
        return "P2C", "Advisor estimate stage but DVI not complete - cannot build estimate"
    if status in {"technical advisement","technical overview"}:
        return "P2C", "Waiting on technical direction before advisor can proceed"
    if status == "waiting parts" and _parts_on_order(job) and not _parts_arrived(job):
        return "P4", "Waiting on external parts - legitimate hold (Drew monitors ETA)"
    if status == "waiting approval" and "approval_stale" not in flags:
        return "P4", "Waiting on customer decision - advisor has made contact"
    if "no_movement" in flags:
        return "P3", f"Active but no movement in {_last_update_hours(job):.0f}h - watch this"
    return "P3", f"Active and progressing - status: {status}"

def _build_next_action(priority, status, owner, flags, job):
    ro = job.get("ticket_reference") or job.get("invoice") or "this RO"
    customer = job.get("customer_name") or "customer"
    if priority == "P1":
        if status == "ready":
            return f"Call {customer} - vehicle is ready, collect payment and close out"
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
    raw_status = job.get("workflow_status") or job.get("current_status") or "unknown"
    status = _normalize_status(raw_status)
    if _is_inactive(status):
        return {
            "ticket_reference": job.get("ticket_reference") or job.get("invoice"),
            "priority": "INACTIVE",
            "owner": "None",
            "board_signal": "clear",
            "next_action": "Job is not active - no action needed",
            "bay_message": "",
            "risk_flags": [],
            "score_reason": f"Status '{raw_status}' is inactive - excluded from board",
            "hours_in_status": _last_update_hours(job),
        }
    flags = _detect_risk_flags(status, job)
    priority, reason = _assign_priority(status, job, flags)
    owner = _determine_owner(status, job)
    next_action = _build_next_action(priority, status, owner, flags, job)
    bay_message = _build_bay_message(priority, status, flags, job)
    signal = _board_signal(priority, flags)
    return {
        "ticket_reference": job.get("ticket_reference") or job.get("invoice"),
        "customer_name": job.get("customer_name", ""),
        "vehicle": job.get("vehicle", ""),
        "advisor_name": job.get("advisor_name") or job.get("service_writer", ""),
        "technician": job.get("technician") or job.get("tech_name", ""),
        "priority": priority,
        "score_reason": reason,
        "owner": owner,
        "board_signal": signal,
        "next_action": next_action,
        "bay_message": bay_message,
        "risk_flags": flags,
        "autoflow_status": raw_status,
        "hours_in_status": _last_update_hours(job),
        "etc_hours_remaining": _etc_hours_remaining(job),
        "has_dvi": _has_dvi(job),
        "parts_on_order": _parts_on_order(job),
        "parts_arrived": _parts_arrived(job),
        "is_approved": _is_approved(job),
    }

def score_all_jobs(shop_state):
    priority_order = {"P1": 0, "P2A": 1, "P2B": 2, "P2C": 3, "P3": 4, "P4": 5}
    scored = []
    for job in shop_state.get("jobs", []):
        result = score_job(job)
        if result["priority"] != "INACTIVE":
            scored.append(result)
    scored.sort(key=lambda r: (priority_order.get(r["priority"], 9), -r["hours_in_status"]))
    return scored
