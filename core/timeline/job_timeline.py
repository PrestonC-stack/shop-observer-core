"""
core/timeline/job_timeline.py
Callahan Auto & Diesel — RO Job Timeline Logger

Records every system and advisor action to a per-RO JSONL file.
This becomes the job memory — every event, in order, forever.
No AI. No API calls. Just logging.
"""

import os
import json
import logging
from datetime import datetime
from typing import Optional

from core.cas.dvi_schema import TimelineEntry, DVIReview, ReviewStatus

logger = logging.getLogger(__name__)

TIMELINE_DIR = os.path.join("state", "job_timeline")


def _timeline_path(ro: str) -> str:
    os.makedirs(TIMELINE_DIR, exist_ok=True)
    return os.path.join(TIMELINE_DIR, f"{ro}.jsonl")


def log_event(
    ro: str,
    event_type: str,
    source: str,
    actor: str,
    summary: str,
    details: dict = None,
    requires_action: bool = False,
    resolved: bool = False
) -> TimelineEntry:
    """
    Log a single event to the RO timeline.
    Appends one JSON line to state/job_timeline/{RO}.jsonl
    """
    entry = TimelineEntry(
        ro=ro,
        event_type=event_type,
        source=source,
        actor=actor,
        summary=summary,
        details=details or {},
        requires_action=requires_action,
        resolved=resolved
    )

    path = _timeline_path(ro)
    with open(path, "a") as f:
        f.write(entry.to_jsonl() + "\n")

    logger.info(f"Timeline [{ro}] {event_type}: {summary}")
    return entry


def log_dvi_gate_result(review: DVIReview) -> TimelineEntry:
    """Log a DVI gate result to the timeline."""
    status_emoji = {
        ReviewStatus.PASS: "✅",
        ReviewStatus.REVIEW: "⚠️",
        ReviewStatus.REWORK_REQUIRED: "❌",
        ReviewStatus.ERROR: "🔴",
    }.get(review.review_status, "❓")

    summary = (
        f"{status_emoji} DVI gate ran — {review.review_status} — "
        f"{review.flag_count} flag(s)"
    )

    return log_event(
        ro=review.ro,
        event_type="dvi_gate_result",
        source="system",
        actor="Callie",
        summary=summary,
        details={
            "review_status": review.review_status,
            "flag_count": review.flag_count,
            "critical_count": len(review.critical_flags),
            "important_count": len(review.important_flags),
            "rework_required": review.rework_required,
            "cleared_for_estimate": review.cleared_for_estimate,
            "primary_complaint": review.primary_complaint,
            "complaint_addressed": review.complaint_addressed,
            "flags": [f.to_dict() for f in review.flags]
        },
        requires_action=review.rework_required or review.review_status == ReviewStatus.REVIEW,
        resolved=review.review_status == ReviewStatus.PASS
    )


def log_rework_slip_generated(review: DVIReview, slip_path: str) -> TimelineEntry:
    return log_event(
        ro=review.ro,
        event_type="rework_slip_generated",
        source="system",
        actor="Callie",
        summary=f"Rework slip generated — {review.flag_count} items require correction",
        details={"slip_path": slip_path, "flag_count": review.flag_count},
        requires_action=True,
        resolved=False
    )


def log_advisor_acknowledged(ro: str, advisor: str, note: str = "") -> TimelineEntry:
    return log_event(
        ro=ro,
        event_type="advisor_acknowledged",
        source="advisor",
        actor=advisor,
        summary=f"{advisor} acknowledged DVI review{': ' + note if note else ''}",
        details={"note": note},
        requires_action=False,
        resolved=True
    )


def log_advisor_override(ro: str, advisor: str, reason: str) -> TimelineEntry:
    return log_event(
        ro=ro,
        event_type="advisor_override",
        source="advisor",
        actor=advisor,
        summary=f"{advisor} overrode rework requirement: {reason}",
        details={"override_reason": reason},
        requires_action=False,
        resolved=True
    )


def log_advisor_note(ro: str, advisor: str, note: str) -> TimelineEntry:
    return log_event(
        ro=ro,
        event_type="advisor_note",
        source="advisor",
        actor=advisor,
        summary=f"Note from {advisor}: {note[:80]}{'...' if len(note) > 80 else ''}",
        details={"full_note": note},
        requires_action=False,
        resolved=False
    )


def log_autoflow_event(ro: str, event_type: str, status: str) -> TimelineEntry:
    return log_event(
        ro=ro,
        event_type=f"autoflow_{event_type}",
        source="autoflow",
        actor="AutoFlow",
        summary=f"AutoFlow event: {event_type} — status: {status}",
        details={"autoflow_event": event_type, "status": status},
        requires_action=False,
        resolved=False
    )


def get_timeline(ro: str) -> list:
    """Read all timeline entries for an RO. Returns list of dicts."""
    path = _timeline_path(ro)
    if not os.path.exists(path):
        return []
    entries = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning(f"Bad timeline line in {ro}: {line[:50]}")
    return entries


def get_open_actions(ro: str) -> list:
    """Return unresolved timeline entries that require action."""
    return [
        e for e in get_timeline(ro)
        if e.get("requires_action") and not e.get("resolved")
    ]
