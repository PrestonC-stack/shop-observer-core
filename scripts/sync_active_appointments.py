from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = ROOT / "state"
ACTIVE_ROS_FILE = STATE_DIR / "active_ros.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from connectors import autoflow
from scripts.build_active_ros_state import _is_production_ro, build_active_ros_state

APPOINTMENTS_PATH = "/api/v1/appointments"


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
    return value


def _first_value(container: Any, *paths: tuple[Any, ...]) -> Any:
    for path in paths:
        value = _deep_get(container, path)
        if value not in (None, "", [], {}):
            return value
    return None


def _normalize_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _date_window() -> tuple[str, str]:
    today = datetime.now().date()
    start_date = (today - timedelta(days=7)).isoformat()
    end_date = (today + timedelta(days=14)).isoformat()
    return start_date, end_date


def _request_appointments() -> Any:
    autoflow._load_local_env_file()
    base_url = autoflow.os.getenv("AUTOFLOW_API_BASE_URL", "").strip()
    if not base_url:
        raise RuntimeError("AUTOFLOW_API_BASE_URL is required for appointment sync")

    headers = autoflow._build_headers()
    if len(headers) == 1:
        raise RuntimeError(
            "AutoFlow credentials are required via AUTOFLOW_API_KEY/AUTOFLOW_API_PASSWORD or AUTOFLOW_API_TOKEN"
        )

    start_date, end_date = _date_window()
    query_variants = [
        {"start_date": start_date, "end_date": end_date},
        {"from": start_date, "to": end_date},
        {"startDate": start_date, "endDate": end_date},
        {"date_from": start_date, "date_to": end_date},
    ]

    last_error: Exception | None = None
    for query in query_variants:
        request_url = urljoin(base_url.rstrip("/") + "/", APPOINTMENTS_PATH.lstrip("/"))
        request_url = f"{request_url}?{urlencode(query)}"
        request = Request(request_url, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=20) as response:
                payload = response.read().decode("utf-8")
            return json.loads(payload)
        except Exception as exc:
            last_error = exc
            continue

    if last_error is not None:
        raise RuntimeError(f"Appointment sync failed: {last_error}") from last_error

    raise RuntimeError("Appointment sync failed: no query variants were attempted")


def _extract_records(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        return []

    for key in ("appointments", "data", "results", "items", "content", "response"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    return [payload]


def _extract_ro(record: dict[str, Any]) -> str:
    value = _first_value(
        record,
        ("remote_id",),
        ("ticket", "remote_id"),
        ("ticket", "invoice"),
        ("invoice_or_ro",),
        ("ro",),
        ("invoice",),
        ("invoice_number",),
        ("ro_number",),
        ("roNumber",),
        ("repair_order",),
        ("work_order", "invoice"),
        ("work_order", "ro_number"),
        ("appointment", "invoice"),
        ("appointment", "ro_number"),
        ("id",),
    )
    return _normalize_text(value, "")


def build_active_ros_from_appointments() -> dict[str, Any]:
    webhook_state = build_active_ros_state()
    webhook_ros = webhook_state.get("active_ros", []) if isinstance(webhook_state, dict) else []

    payload = _request_appointments()
    records = _extract_records(payload)

    appointment_ros = set()
    for record in records:
        ro = _extract_ro(record)
        if ro and _is_production_ro(ro):
            appointment_ros.add(ro)

    merged_ros = sorted(set(webhook_ros) | appointment_ros)
    start_date, end_date = _date_window()

    return {
        "source": "autoflow_events+autoflow_appointments",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "active_ros": merged_ros,
        "count": len(merged_ros),
        "appointment_window": {
            "start_date": start_date,
            "end_date": end_date,
        },
        "sources": {
            "webhook_count": len(webhook_ros),
            "appointment_count": len(appointment_ros),
        },
    }


def main() -> None:
    state = build_active_ros_from_appointments()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    ACTIVE_ROS_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(ACTIVE_ROS_FILE)
    print(f"Active ROs: {state['count']}")


if __name__ == "__main__":
    main()
