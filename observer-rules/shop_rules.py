from __future__ import annotations

from typing import Any


COMPLETE_STATUSES = {"complete", "completed", "closed", "done"}
APPROVED_STATUSES = {"approved", "authorized", "customer_approved"}


def _to_float(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def evaluate_shop_rules(shop_state: dict[str, Any]) -> list[dict[str, Any]]:
    """Evaluate read-only first-pass rule findings against a normalized shop_state."""
    findings: list[dict[str, Any]] = []

    for job in shop_state.get("jobs", []):
        ticket_reference = str(job.get("ticket_reference", "UNKNOWN"))
        workflow_status = str(job.get("workflow_status", "unknown")).lower()
        clocked_in = bool(job.get("clocked_in", False))
        progress_percent = _to_float(job.get("progress_percent", 0))
        labor_hours_remaining = _to_float(job.get("labor_hours_remaining", 0))
        approval_status = str(job.get("approval_status", "unknown")).lower()
        parts_ordered = bool(job.get("parts_ordered", False))
        parts_received = bool(job.get("parts_received", False))
        job_marked_complete = bool(job.get("job_marked_complete", False)) or workflow_status in COMPLETE_STATUSES

        if workflow_status == "assigned" and not clocked_in:
            findings.append(
                {
                    "rule_id": "assigned_no_clock_in",
                    "ticket_reference": ticket_reference,
                    "severity": "medium",
                    "title": "Assigned job with no clock-in",
                    "detail": "Job is assigned but the technician has not clocked in yet.",
                }
            )

        if workflow_status == "active" and progress_percent == 0:
            findings.append(
                {
                    "rule_id": "active_zero_progress",
                    "ticket_reference": ticket_reference,
                    "severity": "medium",
                    "title": "Active job with 0 percent complete",
                    "detail": "Job is active but no progress has been logged.",
                }
            )

        if workflow_status == "active" and labor_hours_remaining <= 0.5:
            findings.append(
                {
                    "rule_id": "near_completion_low_labor_remaining",
                    "ticket_reference": ticket_reference,
                    "severity": "low",
                    "title": "Job near completion",
                    "detail": "Labor remaining is low and the job appears close to completion.",
                }
            )

        if approval_status in APPROVED_STATUSES and not parts_ordered:
            findings.append(
                {
                    "rule_id": "approved_no_parts_ordered",
                    "ticket_reference": ticket_reference,
                    "severity": "high",
                    "title": "Approved job with no parts ordered",
                    "detail": "Work is approved but parts still have not been ordered.",
                }
            )

        if parts_ordered and not parts_received and job_marked_complete:
            findings.append(
                {
                    "rule_id": "ordered_not_received_complete_status",
                    "ticket_reference": ticket_reference,
                    "severity": "high",
                    "title": "Part ordered but not received while job marked complete",
                    "detail": "Completion status conflicts with parts receipt state.",
                }
            )

    return findings
