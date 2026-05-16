from __future__ import annotations

import base64
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.parse import urljoin
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
MOCK_AUTOFLOW_PATH = REPO_ROOT / "inputs" / "mock_autoflow_techflow_jobs.json"

DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_WORK_ORDER_PATH_TEMPLATE = "/api/v1/work_orders/{ro_number}"
DEFAULT_DVI_PATH_TEMPLATE = "/api/v1/dvi/{ro_number}"
DEFAULT_AUTH_MODE = "basic"

COMPLETE_STATUSES = {"complete", "completed", "closed", "done"}

LOGGER = logging.getLogger("shop_observer.autoflow")
if not LOGGER.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("[autoflow] %(levelname)s %(message)s"))
    LOGGER.addHandler(handler)
LOGGER.setLevel(logging.INFO)
LOGGER.propagate = False
_ENV_LOADED = False


def load_mock_autoflow_jobs(input_path: Path | None = None) -> dict[str, Any]:
    """Load placeholder AutoFlow TechFlow-style job/task data from local mock input."""
    source_path = input_path or MOCK_AUTOFLOW_PATH
    with source_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_local_env_file() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return

    env_path = REPO_ROOT / ".env"
    if env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value

    _ENV_LOADED = True


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
    _load_local_env_file()
    headers = {"Accept": "application/json"}

    api_key = os.getenv("AUTOFLOW_API_KEY", "").strip()
    password = os.getenv("AUTOFLOW_API_PASSWORD", "").strip()
    auth_mode = os.getenv("AUTOFLOW_AUTH_MODE", DEFAULT_AUTH_MODE).strip().lower()
    token = os.getenv("AUTOFLOW_API_TOKEN", "").strip()

    if api_key and password:
        if auth_mode == "headers":
            key_header = os.getenv("AUTOFLOW_API_KEY_HEADER", "X-API-Key").strip()
            password_header = os.getenv(
                "AUTOFLOW_API_PASSWORD_HEADER", "X-API-Password"
            ).strip()
            headers[key_header] = api_key
            headers[password_header] = password
            return headers

        credentials = base64.b64encode(f"{api_key}:{password}".encode("utf-8")).decode(
            "ascii"
        )
        headers["Authorization"] = f"Basic {credentials}"
        return headers

    if token:
        auth_header = os.getenv("AUTOFLOW_AUTH_HEADER", "Authorization").strip()
        auth_prefix = os.getenv("AUTOFLOW_AUTH_PREFIX", "Bearer").strip()
        headers[auth_header] = f"{auth_prefix} {token}".strip() if auth_prefix else token

    return headers


def _request_json(path_template: str, ro_number: str) -> dict[str, Any]:
    _load_local_env_file()
    base_url = os.getenv("AUTOFLOW_API_BASE_URL", "").strip()
    if not base_url:
        raise RuntimeError("AUTOFLOW_API_BASE_URL is required for real AutoFlow intake")

    headers = _build_headers()
    if len(headers) == 1:
        raise RuntimeError(
            "AutoFlow credentials are required via AUTOFLOW_API_KEY/AUTOFLOW_API_PASSWORD or AUTOFLOW_API_TOKEN"
        )

    path = path_template.format(ro_number=ro_number)
    request_url = (
        path
        if path.startswith("http")
        else urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    )
    sanitized_endpoint = path
    if path.startswith("http"):
        parsed_url = urlparse(path)
        sanitized_endpoint = parsed_url.path or "/"
        if parsed_url.query:
            sanitized_endpoint = f"{sanitized_endpoint}?{parsed_url.query}"

    LOGGER.info("AUTOFLOW REQUEST: GET %s", sanitized_endpoint)
    timeout_seconds = int(os.getenv("AUTOFLOW_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))

    request = Request(request_url, headers=headers, method="GET")

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
    """Merge read-only AutoFlow work order + DVI payloads into one raw record."""
    ticket_reference = str(
        _first_value(
            work_order,
            ("ro_number",),
            ("roNumber",),
            ("work_order_number",),
            ("workOrderNumber",),
            default=ro_number,
        )
    ).strip() or ro_number
    return {
        "ticket_reference": ticket_reference,
        "ro_number": ticket_reference,
        "work_order_id": str(
            _first_value(work_order, ("id",), ("work_order_id",), ("workOrderId",), default="")
        ),
        "dvi_id": str(_first_value(dvi, ("id",), ("dvi_id",), ("dviId",), default="")),
        "workflow_status": _normalize_status(
            _first_value(
                work_order,
                ("workflow_status",),
                ("workflowStatus",),
                ("status",),
                ("job_status",),
                default="unknown",
            )
        ),
        "job_marked_complete": _to_bool(
            _first_value(
                work_order,
                ("job_marked_complete",),
                ("jobMarkedComplete",),
                ("isComplete",),
                default=False,
            )
        ),
        "approval_status": _normalize_status(
            _first_value(
                work_order,
                ("approval_status",),
                ("approvalStatus",),
                ("estimate", "approvalStatus"),
                ("work_status",),
                default="unknown",
            )
        ),
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
        "progress_percent": _to_float(
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
        ),
        "labor_hours_remaining": _to_float(
            _first_value(
                work_order,
                ("labor_hours_remaining",),
                ("laborHoursRemaining",),
                ("labor", "hoursRemaining"),
                ("estimatedHoursRemaining",),
                ("remaining_labor_hours",),
                default=0.0,
            )
        ),
        "dvi_completed": _to_bool(
            _first_value(
                dvi,
                ("completed",),
                ("isCompleted",),
                ("status",),
                ("summary", "completed"),
                default=False,
            ),
            default=False,
        ),
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
        "work_order": work_order,
        "dvi": dvi,
    }


def build_shop_state(ro_numbers: Iterable[str]) -> dict[str, Any]:
    return fetch_autoflow_data(ro_numbers)


def fetch_autoflow_data(ro_numbers: Iterable[str]) -> dict[str, Any]:
    """Read-only connector entrypoint for real AutoFlow intake with safe mock fallback."""
    ro_list = [str(ro_number).strip() for ro_number in ro_numbers if str(ro_number).strip()]
    if not ro_list:
        LOGGER.warning("No RO numbers were provided; using mock AutoFlow fallback.")
        mock_data = load_mock_autoflow_jobs()
        mock_data["mode"] = "mock_fallback"
        mock_data["source"] = "autoflow-techflow-mock-fallback"
        return mock_data

    try:
        records: list[dict[str, Any]] = []
        for ro_number in ro_list:
            work_order = get_work_order(ro_number)
            dvi = get_dvi(ro_number)
            records.append(merge_work_order_and_dvi(work_order, dvi, ro_number))
        LOGGER.info("Using live AutoFlow API data for %s RO(s).", len(records))
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "api",
            "source": os.getenv("AUTOFLOW_API_BASE_URL", "autoflow-api"),
            "records": records,
        }
    except Exception as exc:
        LOGGER.warning("AutoFlow API unavailable; using mock fallback. %s", exc)
        mock_data = load_mock_autoflow_jobs()
        mock_data["mode"] = "mock_fallback"
        mock_data["source"] = "autoflow-techflow-mock-fallback"
        mock_data["fallback_reason"] = str(exc)
        return mock_data
# Add this at the very end of the file
def get_active_ros_summary() -> dict:
    """Simple helper to get current shop overview"""
    try:
        data = fetch_autoflow_data([])  # uses mock or live depending on config
        records = data.get("records", [])
        return {
            "total_active": len(records),
            "generated_at": data.get("generated_at"),
            "mode": data.get("mode", "unknown"),
            "sample_ros": [r.get("ro_number") for r in records[:5]]
        }
    except:
        return {"total_active": 0, "error": "Failed to fetch"}