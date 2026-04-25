from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
MOCK_AUTOFLOW_PATH = REPO_ROOT / "inputs" / "mock_autoflow_techflow_jobs.json"

DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_WORK_ORDER_PATH_TEMPLATE = "/api/work-orders/{ro_number}"
DEFAULT_DVI_PATH_TEMPLATE = "/api/dvi/{ro_number}"

COMPLETE_STATUSES = {"complete", "completed", "closed", "done"}


def load_mock_autoflow_jobs(input_path: Path | None = None) -> dict[str, Any]:
    """Load placeholder AutoFlow TechFlow-style job/task data from local mock input."""
    source_path = input_path or MOCK_AUTOFLOW_PATH
    with source_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


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
    if normalized in {"true", "1", "yes", "y", "complete", "completed", "received"}:
        return True
    if normalized in {"false", "0", "no", "n", "pending", "open", "not_received"}:
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


def _build_headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}

    token = os.getenv("AUTOFLOW_API_TOKEN", "").strip()
    if token:
        auth_header = os.getenv("AUTOFLOW_AUTH_HEADER", "Authorization").strip()
        auth_prefix = os.getenv("AUTOFLOW_AUTH_PREFIX", "Bearer").strip()
        headers[auth_header] = f"{auth_prefix} {token}".strip() if auth_prefix else token

    return headers


def _request_json(path_template: str, ro_number: str) -> dict[str, Any]:
    base_url = os.getenv("AUTOFLOW_API_BASE_URL", "").strip()
    if not base_url:
        raise RuntimeError("AUTOFLOW_API_BASE_URL is required for real AutoFlow intake")

    path = path_template.format(ro_number=ro_number)
    request_url = path if path.startswith("http") else urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    timeout_seconds = int(os.getenv("AUTOFLOW_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))

    request = Request(request_url, headers=_build_headers(), method="GET")

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = response.read().decode("utf-8")
    except HTTPError as exc:
        raise RuntimeError(
            f"AutoFlow request failed for RO {ro_number}: HTTP {exc.code}"
        ) from exc
    except URLError as exc:
        raise RuntimeError(
            f"AutoFlow request failed for RO {ro_number}: {exc.reason}"
        ) from exc

    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"AutoFlow response for RO {ro_number} was not valid JSON"
        ) from exc

    if not isinstance(data, dict):
        raise RuntimeError(
            f"AutoFlow response for RO {ro_number} must be a JSON object"
        )

    return data


def get_work_order(ro_number: str) -> dict[str, Any]:
    """Read a single AutoFlow work order by RO number."""
    path_template = os.getenv(
        "AUTOFLOW_WORK_ORDER_PATH_TEMPLATE", DEFAULT_WORK_ORDER_PATH_TEMPLATE
    )
    return _request_json(path_template, ro_number)


def get_dvi(ro_number: str) -> dict[str, Any]:
    """Read a single AutoFlow DVI by RO number."""
    path_template = os.getenv("AUTOFLOW_DVI_PATH_TEMPLATE", DEFAULT_DVI_PATH_TEMPLATE)
    return _request_json(path_template, ro_number)


def merge_work_order_and_dvi(
    work_order: dict[str, Any], dvi: dict[str, Any], ro_number: str
) -> dict[str, Any]:
    """Merge read-only AutoFlow work order + DVI payloads into one normalized job."""
    ticket_reference = str(
        _first_value(
            work_order,
            ("ro_number",),
            ("roNumber",),
            ("work_order_number",),
            ("workOrderNumber",),
            default=ro_number,
        )
    )
    workflow_status = _normalize_status(
        _first_value(
            work_order,
            ("workflow_status",),
            ("workflowStatus",),
            ("status",),
            ("job_status",),
            default="unknown",
        )
    )
    progress_percent = _to_float(
        _first_value(
            dvi,
            ("progress_percent",),
            ("progressPercent",),
            ("completionPercent",),
            ("inspection", "progressPercent"),
            ("summary", "completionPercent"),
            ("percent_complete",),
            default=_first_value(
                work_order,
                ("progress_percent",),
                ("progressPercent",),
                default=0,
            ),
        )
    )
    labor_hours_remaining = _to_float(
        _first_value(
            work_order,
            ("labor_hours_remaining",),
            ("laborHoursRemaining",),
            ("labor", "hoursRemaining"),
            ("estimatedHoursRemaining",),
            ("remaining_labor_hours",),
            default=0.0,
        )
    )
    approval_status = _normalize_status(
        _first_value(
            work_order,
            ("approval_status",),
            ("approvalStatus",),
            ("estimate", "approvalStatus"),
            ("work_status",),
            default="unknown",
        )
    )
    parts_ordered = _to_bool(
        _first_value(
            work_order,
            ("parts_ordered",),
            ("partsOrdered",),
            ("parts_summary", "ordered"),
            ("parts", "ordered"),
            ("parts", "isOrdered"),
            default=False,
        )
    )
    parts_received = _to_bool(
        _first_value(
            work_order,
            ("parts_received",),
            ("partsReceived",),
            ("parts_summary", "received"),
            ("parts", "received"),
            ("parts", "isReceived"),
            default=False,
        )
    )
    job_marked_complete = _to_bool(
        _first_value(
            work_order,
            ("job_marked_complete",),
            ("jobMarkedComplete",),
            ("isComplete",),
            default=workflow_status in COMPLETE_STATUSES,
        )
    )
    dvi_completed = _to_bool(
        _first_value(
            dvi,
            ("completed",),
            ("isCompleted",),
            ("status",),
            ("summary", "completed"),
            default=False,
        ),
        default=False,
    )

    return {
        "job_id": str(
            _first_value(
                work_order,
                ("id",),
                ("work_order_id",),
                ("workOrderId",),
                default=ticket_reference,
            )
        ),
        "ticket_reference": ticket_reference,
        "location": str(
            _first_value(
                work_order,
                ("location", "name"),
                ("shop", "name"),
                ("locationName",),
                default="Unknown",
            )
        ),
        "advisor_name": str(
            _first_value(
                work_order,
                ("advisor", "name"),
                ("serviceAdvisor", "name"),
                ("advisor_name",),
                ("advisorName",),
                default="Unknown",
            )
        ),
        "technician_name": str(
            _first_value(
                work_order,
                ("technician", "name"),
                ("assignedTech", "name"),
                ("assigned_technician", "name"),
                ("technicianName",),
                default="Unassigned",
            )
        ),
        "workflow_status": workflow_status,
        "clocked_in": _to_bool(
            _first_value(
                work_order,
                ("clocked_in",),
                ("clockedIn",),
                ("labor", "clockedIn"),
                ("activeClock", "isOpen"),
                default=False,
            )
        ),
        "progress_percent": progress_percent,
        "labor_hours_remaining": labor_hours_remaining,
        "job_marked_complete": job_marked_complete,
        "approval_status": approval_status,
        "parts_ordered": parts_ordered,
        "parts_received": parts_received,
        "dvi_completed": dvi_completed,
        "dvi_status": _normalize_status(
            _first_value(dvi, ("status",), ("inspection", "status"), default="unknown")
        ),
        "latest_activity": str(
            _first_value(
                work_order,
                ("latest_activity",),
                ("latestActivity",),
                ("timeline", "latestEvent"),
                default="",
            )
        ),
        "notes": str(
            _first_value(
                dvi,
                ("summary",),
                ("notes",),
                ("inspection", "notes"),
                default=_first_value(
                    work_order,
                    ("notes",),
                    ("customerConcern",),
                    default="",
                ),
            )
        ),
        "source_refs": {
            "ro_number": ticket_reference,
            "work_order_id": _first_value(
                work_order, ("id",), ("work_order_id",), ("workOrderId",), default=""
            ),
            "dvi_id": _first_value(dvi, ("id",), ("dvi_id",), ("dviId",), default=""),
        },
        "raw": {
            "work_order": work_order,
            "dvi": dvi,
        },
    }


def build_shop_state(ro_numbers: Iterable[str]) -> dict[str, Any]:
    jobs: list[dict[str, Any]] = []

    for ro_number in ro_numbers:
        work_order = get_work_order(ro_number)
        dvi = get_dvi(ro_number)
        jobs.append(merge_work_order_and_dvi(work_order, dvi, ro_number))

    return {
        "shop_state_version": "v1-autoflow-readonly",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "autoflow": os.getenv("AUTOFLOW_API_BASE_URL", "autoflow-api"),
        },
        "jobs": jobs,
    }


def fetch_autoflow_data(ro_numbers: Iterable[str]) -> dict[str, Any]:
    """Read-only connector entrypoint for real AutoFlow intake."""
    return build_shop_state(ro_numbers)
