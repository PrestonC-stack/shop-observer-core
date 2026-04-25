from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from connectors.autoflow import build_shop_state as build_autoflow_shop_state
from connectors.autoflow import load_mock_autoflow_jobs
from connectors.tekmetric import load_mock_tekmetric_activity


def _deep_get(container: Any, path: tuple[Any, ...]) -> Any:
    value = container
    for key in path:
        if isinstance(value, dict):
            value = value.get(key)
        elif isinstance(value, list) and isinstance(key, int):
            if key < 0 or key >= len(value):
                return None
            value = value[key]
        else:
            return None

        if value is None:
            return None

    return value


def _first_value(container: Any, *paths: tuple[Any, ...], default: Any = None) -> Any:
    for path in paths:
        value = _deep_get(container, path)
        if value not in (None, "", [], {}):
            return value
    return default


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)

    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y", "complete", "completed", "received", "arrived"}:
        return True
    if normalized in {"false", "0", "no", "n", "pending", "open", "not_received", "ordered"}:
        return False
    return default


def _to_float(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_status(value: Any, default: str = "unknown") -> str:
    if value in (None, ""):
        return default
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def _extract_dvi_items(dvi: dict[str, Any]) -> list[dict[str, Any]]:
    items = _first_value(
        dvi,
        ("dvi_items",),
        ("dviItems",),
        ("inspectionItems",),
        ("inspection", "items"),
        ("items",),
        default=[],
    )
    if isinstance(items, list) and items:
        return [item for item in items if isinstance(item, dict)]
    return []


def _normalize_parts_list(
    work_order: dict[str, Any], dvi_item: dict[str, Any] | None
) -> list[dict[str, Any]]:
    raw_parts = _first_value(
        dvi_item or {},
        ("parts",),
        ("recommendedParts",),
        default=_first_value(
            work_order,
            ("parts",),
            ("partsList",),
            ("lineItems", "parts"),
            default=[],
        ),
    )
    if not isinstance(raw_parts, list):
        return []

    normalized_parts: list[dict[str, Any]] = []
    for index, part in enumerate(raw_parts, start=1):
        if not isinstance(part, dict):
            continue

        arrived = _to_bool(
            _first_value(
                part,
                ("arrived",),
                ("isArrived",),
                ("received",),
                ("isReceived",),
                default=False,
            )
        )
        ordered = _to_bool(
            _first_value(
                part,
                ("ordered",),
                ("isOrdered",),
                ("onOrder",),
                default=arrived,
            )
        )
        if arrived:
            part_status = "received"
        elif ordered:
            part_status = "ordered"
        else:
            part_status = "pending"

        normalized_parts.append(
            {
                "part_id": str(
                    _first_value(
                        part,
                        ("id",),
                        ("partId",),
                        ("lineId",),
                        default=f"part-{index}",
                    )
                ),
                "part_number": str(
                    _first_value(
                        part,
                        ("partNumber",),
                        ("sku",),
                        ("number",),
                        default="",
                    )
                ),
                "description": str(
                    _first_value(
                        part,
                        ("description",),
                        ("name",),
                        ("label",),
                        default="",
                    )
                ),
                "quantity": _to_float(
                    _first_value(
                        part,
                        ("quantity",),
                        ("qty",),
                        ("orderedQuantity",),
                        default=1,
                    ),
                    default=1.0,
                ),
                "arrived": arrived,
                "ordered": ordered,
                "status": part_status,
            }
        )

    return normalized_parts


def _normalize_autoflow_record(record: dict[str, Any]) -> list[dict[str, Any]]:
    work_order = record.get("work_order", {})
    dvi = record.get("dvi", {})
    dvi_items = _extract_dvi_items(dvi)
    if not dvi_items:
        dvi_items = [{}]

    ticket_reference = str(
        record.get("ticket_reference")
        or _first_value(
            work_order,
            ("ro_number",),
            ("roNumber",),
            ("work_order_number",),
            ("workOrderNumber",),
            default="UNKNOWN",
        )
    )
    location = str(
        record.get("location")
        or _first_value(
            work_order,
            ("location", "name"),
            ("shop", "name"),
            ("locationName",),
            default="Unknown",
        )
    )
    advisor_name = str(
        record.get("advisor_name")
        or _first_value(
            work_order,
            ("advisor", "name"),
            ("serviceAdvisor", "name"),
            ("advisorName",),
            default="Unknown",
        )
    )
    technician_name = str(
        record.get("technician_name")
        or _first_value(
            work_order,
            ("technician", "name"),
            ("assignedTech", "name"),
            ("technicianName",),
            default="Unassigned",
        )
    )
    base_workflow_status = _normalize_status(
        record.get("workflow_status")
        or _first_value(
            work_order,
            ("workflow_status",),
            ("workflowStatus",),
            ("status",),
            default="unknown",
        )
    )
    approval_status = _normalize_status(
        record.get("approval_status")
        or _first_value(
            work_order,
            ("approval_status",),
            ("approvalStatus",),
            ("estimate", "approvalStatus"),
            default="unknown",
        )
    )
    dvi_completed = _to_bool(
        record.get("dvi_completed"),
        default=_to_bool(
            _first_value(
                dvi,
                ("completed",),
                ("isCompleted",),
                ("summary", "completed"),
                default=False,
            )
        ),
    )

    normalized_jobs: list[dict[str, Any]] = []
    for index, dvi_item in enumerate(dvi_items, start=1):
        job_name = str(
            _first_value(
                dvi_item,
                ("job_name",),
                ("jobName",),
                ("title",),
                ("name",),
                ("label",),
                default=f"Job {index}",
            )
        )
        sold_hours = _to_float(
            _first_value(
                dvi_item,
                ("labor_quantity",),
                ("laborQuantity",),
                ("labor", "quantity"),
                ("sold_hours",),
                ("soldHours",),
                ("hours",),
                default=_first_value(
                    work_order,
                    ("labor_quantity",),
                    ("laborQuantity",),
                    ("labor", "soldHours"),
                    ("estimatedLaborHours",),
                    default=0.0,
                ),
            )
        )
        progress_percent = _to_float(
            _first_value(
                dvi_item,
                ("progress_percent",),
                ("progressPercent",),
                ("percent_complete",),
                default=record.get("progress_percent", 0),
            )
        )
        labor_hours_remaining = _to_float(
            _first_value(
                dvi_item,
                ("labor_hours_remaining",),
                ("laborHoursRemaining",),
                ("remaining_labor_hours",),
                ("remainingHours",),
                default=record.get("labor_hours_remaining"),
            ),
            default=max(sold_hours - ((sold_hours * progress_percent) / 100), 0.0),
        )
        parts_list = _normalize_parts_list(work_order, dvi_item)
        ordered_parts = [part for part in parts_list if part["status"] in {"ordered", "received"}]
        parts_received = bool(ordered_parts) and all(
            part["status"] == "received" for part in ordered_parts
        )
        inspection_status = _normalize_status(
            _first_value(
                dvi_item,
                ("inspection_status",),
                ("inspectionStatus",),
                ("status",),
                default="completed" if dvi_completed else "pending",
            )
        )

        normalized_jobs.append(
            {
                "job_id": str(
                    _first_value(
                        dvi_item,
                        ("id",),
                        ("itemId",),
                        ("jobId",),
                        default=f"{ticket_reference}-{index}",
                    )
                ),
                "ticket_reference": ticket_reference,
                "job_name": job_name,
                "location": location,
                "advisor_name": advisor_name,
                "technician_name": technician_name,
                "workflow_status": _normalize_status(
                    _first_value(
                        dvi_item,
                        ("workflow_status",),
                        ("workflowStatus",),
                        ("job_status",),
                        ("jobStatus",),
                        default=base_workflow_status,
                    )
                ),
                "clocked_in": _to_bool(record.get("clocked_in", False)),
                "progress_percent": progress_percent,
                "sold_hours": sold_hours,
                "labor_hours_remaining": labor_hours_remaining,
                "job_marked_complete": _to_bool(
                    record.get("job_marked_complete"),
                    default=base_workflow_status in {"complete", "completed", "closed", "done"},
                ),
                "approval_status": approval_status,
                "parts_list": parts_list,
                "parts_ordered": bool(ordered_parts),
                "parts_received": parts_received,
                "dvi_completed": dvi_completed,
                "inspection_status": inspection_status,
                "latest_activity": str(record.get("latest_activity", "")),
                "notes": str(
                    _first_value(
                        dvi_item,
                        ("notes",),
                        ("comment",),
                        default=record.get("notes", ""),
                    )
                ),
                "source_refs": {
                    **deepcopy(record.get("source_refs", {})),
                    "autoflow_ticket_reference": ticket_reference,
                    "dvi_item_id": _first_value(
                        dvi_item, ("id",), ("itemId",), ("jobId",), default=""
                    ),
                },
                "raw": {
                    "work_order": deepcopy(work_order),
                    "dvi": deepcopy(dvi),
                    "dvi_item": deepcopy(dvi_item),
                },
            }
        )

    return normalized_jobs


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
    elif autoflow_data.get("records"):
        normalized_jobs = []
        for record in autoflow_data.get("records", []):
            normalized_jobs.extend(_normalize_autoflow_record(record))
        generated_at = autoflow_data.get("generated_at")
        sources = {
            "autoflow": autoflow_data.get("source", "autoflow-api"),
            "autoflow_mode": autoflow_data.get("mode", "api"),
        }
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
                    "sold_hours": job.get("sold_hours", 0.0),
                    "labor_hours_remaining": job["labor_hours_remaining"],
                    "job_marked_complete": job["job_marked_complete"],
                    "parts_list": job.get("parts_list", []),
                    "inspection_status": job.get("inspection_status", "unknown"),
                    "dvi_completed": job.get("dvi_completed", False),
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
        job.setdefault("parts_list", [])
        job.setdefault("inspection_status", "unknown")
        job.setdefault("sold_hours", 0.0)
        job.setdefault("dvi_completed", False)

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
