from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


HIGH_CONFIDENCE_THRESHOLD = 0.8


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _draft_extracted(draft: dict[str, Any]) -> dict[str, Any]:
    return draft.get("extracted", {})


def _match_score(job: dict[str, Any], extracted: dict[str, Any]) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    ro_number = _norm(extracted.get("ro_number")).replace("ro-", "")
    job_ro = _norm(job.get("ticket_reference")).replace("ro-", "")
    if ro_number and job_ro and ro_number == job_ro:
        return 100, ["ro_number"]

    if _norm(extracted.get("vehicle")) and _norm(extracted.get("vehicle")) == _norm(job.get("vehicle")):
        score += 30
        reasons.append("vehicle")
    if _norm(extracted.get("technician_name")) and _norm(extracted.get("technician_name")) == _norm(job.get("technician_name")):
        score += 20
        reasons.append("technician")
    if _norm(extracted.get("job_name")) and _norm(extracted.get("job_name")) == _norm(job.get("job_name")):
        score += 10
        reasons.append("job_name")

    return score, reasons


def _find_match(
    autoflow_jobs: list[dict[str, Any]],
    draft: dict[str, Any],
) -> tuple[dict[str, Any] | None, list[str], bool]:
    extracted = _draft_extracted(draft)
    best_job: dict[str, Any] | None = None
    best_reasons: list[str] = []
    best_score = 0

    for job in autoflow_jobs:
        score, reasons = _match_score(job, extracted)
        if score > best_score:
            best_score = score
            best_job = job
            best_reasons = reasons

    if best_score >= 100:
        return best_job, best_reasons, False
    if best_score >= 40:
        return best_job, best_reasons, True
    return None, [], True


def _techflow_overlay(draft: dict[str, Any]) -> dict[str, Any]:
    extracted = _draft_extracted(draft)
    return {
        "source_label": "techflow_screenshot",
        "confidence_score": draft.get("confidence_score", 0.0),
        "extraction_flags": draft.get("extraction_flags", []),
        "review_status": draft.get("review_status", "needs_review"),
        "fields": deepcopy(extracted),
    }


def merge_hybrid_shop_state(
    autoflow_shop_state: dict[str, Any],
    techflow_drafts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Merge review-only TechFlow screenshot drafts with AutoFlow shop state."""
    autoflow_jobs = deepcopy(autoflow_shop_state.get("jobs", []))
    unmatched_drafts: list[dict[str, Any]] = []

    for draft in techflow_drafts:
        matched_job, match_reasons, needs_review = _find_match(autoflow_jobs, draft)
        if not matched_job:
            unmatched = deepcopy(draft)
            unmatched["review_status"] = "needs_match_review"
            unmatched["source_labels"] = ["techflow_screenshot"]
            unmatched_drafts.append(unmatched)
            continue

        overlay = _techflow_overlay(draft)
        matched_job.setdefault("techflow_screenshot", []).append(overlay)
        matched_job["source_labels"] = sorted(
            set(matched_job.get("source_labels", ["autoflow_api"]))
            | {"autoflow_api", "techflow_screenshot", "merged_hybrid"}
        )
        matched_job["hybrid_match"] = {
            "match_reasons": match_reasons,
            "needs_review": needs_review
            or draft.get("confidence_score", 0.0) < HIGH_CONFIDENCE_THRESHOLD,
        }

    return {
        "shop_state_version": "v1-hybrid-draft",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_labels": ["autoflow_api", "techflow_screenshot", "merged_hybrid"],
        "jobs": autoflow_jobs,
        "unmatched_techflow_drafts": unmatched_drafts,
    }


def build_hybrid_draft_nudges(hybrid_shop_state: dict[str, Any]) -> list[dict[str, Any]]:
    nudges: list[dict[str, Any]] = []
    jobs = hybrid_shop_state.get("jobs", [])

    closeout_candidates = [
        job for job in jobs if float(job.get("labor_hours_remaining") or 0) <= 0.5
    ]

    for job in jobs:
        ticket_reference = job.get("ticket_reference", "UNKNOWN")
        workflow_status = _norm(job.get("workflow_status"))
        clocked_in = bool(job.get("clocked_in", False))
        percent_complete = float(job.get("progress_percent") or 0)
        labor_remaining = float(job.get("labor_hours_remaining") or 0)
        parts_not_arrived = bool(job.get("parts_not_arrived", False))
        job_complete = workflow_status in {"complete", "completed", "finished", "closed"}

        if workflow_status == "assigned" and not clocked_in:
            nudges.append(
                {
                    "ticket_reference": ticket_reference,
                    "rule_id": "assigned_no_clock_in",
                    "message": "Assigned job has no clock-in detected.",
                }
            )
        if workflow_status == "active" and percent_complete == 0:
            nudges.append(
                {
                    "ticket_reference": ticket_reference,
                    "rule_id": "active_zero_percent_complete",
                    "message": "Active job still shows 0 percent complete.",
                }
            )
        if labor_remaining <= 0.5:
            nudges.append(
                {
                    "ticket_reference": ticket_reference,
                    "rule_id": "low_remaining_labor_priority",
                    "message": "Low remaining labor suggests this could be prioritized for closeout.",
                }
            )
        if closeout_candidates and labor_remaining > 0.5 and workflow_status == "active":
            nudges.append(
                {
                    "ticket_reference": ticket_reference,
                    "rule_id": "lower_priority_active_while_closeout_exists",
                    "message": "Technician may be active on a lower-priority job while a faster closeout exists.",
                }
            )
        if parts_not_arrived and workflow_status in {"active", "complete", "completed", "finished"}:
            nudges.append(
                {
                    "ticket_reference": ticket_reference,
                    "rule_id": "parts_not_arrived_active_or_complete",
                    "message": "Parts have not arrived while job appears active or complete.",
                }
            )
        if parts_not_arrived and job_complete:
            nudges.append(
                {
                    "ticket_reference": ticket_reference,
                    "rule_id": "completed_job_unarrived_parts",
                    "message": "Completed job still has unarrived parts.",
                }
            )

    return nudges
