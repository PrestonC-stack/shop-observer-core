from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from connectors.autoflow import build_shop_state as build_autoflow_shop_state
from connectors.autoflow import load_mock_autoflow_jobs
from connectors.tekmetric import load_mock_tekmetric_activity


def normalize_shop_state(
    autoflow_data: dict[str, Any], tekmetric_data: dict[str, Any]
) -> dict[str, Any]:
    """Merge source-specific payloads into a unified shop_state object."""
    tekmetric_by_ticket = {
        ticket["ticket_reference"]: ticket
        for ticket in tekmetric_data.get("tickets", [])
    }

    if autoflow_data.get("shop_state_version") and autoflow_data.get("jobs"):
        normalized_jobs = deepcopy(autoflow_data.get("jobs", []))
        generated_at = autoflow_data.get("generated_at")
        sources = deepcopy(autoflow_data.get("sources", {}))
    else:
        normalized_jobs = []
        for job in autoflow_data.get("jobs", []):
            normalized_jobs.append(
                {
                    "job_id": job["job_id"],
                    "ticket_reference": job["ticket_reference"],
                    "location": job["location"],
                    "advisor_name": job["advisor_name"],
                    "technician_name": job["technician_name"],
                    "workflow_status": job["workflow_status"],
                    "clocked_in": job["clocked_in"],
                    "progress_percent": job["progress_percent"],
                    "labor_hours_remaining": job["labor_hours_remaining"],
                    "job_marked_complete": job["job_marked_complete"],
                    "notes": job.get("notes", ""),
                    "source_refs": {
                        "autoflow_job_id": job["job_id"],
                    },
                }
            )
        generated_at = autoflow_data.get("generated_at")
        sources = {
            "autoflow": autoflow_data.get("source", "autoflow-techflow-mock"),
        }

    for job in normalized_jobs:
        ticket_reference = job["ticket_reference"]
        tekmetric_ticket = tekmetric_by_ticket.get(ticket_reference, {})

        job["approval_status"] = tekmetric_ticket.get(
            "approval_status", job.get("approval_status", "unknown")
        )
        job["parts_ordered"] = tekmetric_ticket.get(
            "parts_ordered", job.get("parts_ordered", False)
        )
        job["parts_received"] = tekmetric_ticket.get(
            "parts_received", job.get("parts_received", False)
        )
        job["latest_activity"] = tekmetric_ticket.get(
            "latest_activity", job.get("latest_activity", "")
        )
        job["source_refs"] = {
            **job.get("source_refs", {}),
            "tekmetric_ticket_reference": ticket_reference,
        }

    return {
        "shop_state_version": autoflow_data.get("shop_state_version", "v1-draft"),
        "generated_at": generated_at,
        "sources": {
            **sources,
            "tekmetric": tekmetric_data.get("source", "tekmetric-mock"),
        },
        "jobs": normalized_jobs,
    }


def load_mock_shop_state(
    autoflow_path: Path | None = None, tekmetric_path: Path | None = None
) -> dict[str, Any]:
    autoflow_data = load_mock_autoflow_jobs(autoflow_path)
    tekmetric_data = load_mock_tekmetric_activity(tekmetric_path)
    return normalize_shop_state(autoflow_data, tekmetric_data)


def load_shop_state_from_autoflow(ro_numbers: list[str] | tuple[str, ...]) -> dict[str, Any]:
    autoflow_shop_state = build_autoflow_shop_state(ro_numbers)
    return normalize_shop_state(autoflow_shop_state, {"source": "tekmetric-unset", "tickets": []})


def clone_shop_state(shop_state: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(shop_state)
