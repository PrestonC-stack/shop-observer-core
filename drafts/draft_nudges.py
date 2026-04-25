from __future__ import annotations

from typing import Any


def build_draft_nudges(findings: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Convert rule findings into review-first nudges.

    These nudges are draft-only and are intended for operator review, not
    outbound messaging or automatic action.
    """
    nudges: list[dict[str, str]] = []

    for finding in findings:
        ticket_reference = finding["ticket_reference"]
        rule_id = finding["rule_id"]

        if rule_id == "assigned_no_clock_in":
            message = f"Check technician clock-in status for {ticket_reference}."
        elif rule_id == "active_zero_progress":
            message = f"Review why active work on {ticket_reference} still shows 0 percent complete."
        elif rule_id == "near_completion_low_labor_remaining":
            message = f"Prepare close-out review for {ticket_reference}; labor remaining is low."
        elif rule_id == "approved_no_parts_ordered":
            message = f"Confirm parts ordering status for approved ticket {ticket_reference}."
        elif rule_id == "ordered_not_received_complete_status":
            message = (
                f"Resolve parts receipt mismatch before treating {ticket_reference} as complete."
            )
        elif rule_id == "parts_not_arrived":
            message = f"Confirm ETA for parts not arrived on {ticket_reference}."
        else:
            message = f"Review finding for {ticket_reference}."

        nudges.append(
            {
                "ticket_reference": ticket_reference,
                "severity": finding["severity"],
                "message": message,
                "detail": finding["detail"],
            }
        )

    return nudges
