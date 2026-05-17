from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVENT_LOG = ROOT / "data" / "autoflow_events" / "autoflow_events.jsonl"
ACTIVE_ROS_FILE = ROOT / "state" / "active_ros.json"

CLOSED_STATUSES = {"close", "closed", "complete", "completed", "done"}


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


def _first_value(container: dict[str, Any], *paths: tuple[Any, ...]) -> Any:
    for path in paths:
        value = _deep_get(container, path)
        if value not in (None, "", [], {}):
            return value
    return None


def _parse_time(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def _normalize_status(value: Any) -> str:
    if value in (None, "", [], {}):
        return "unknown"
    return " ".join(str(value).strip().lower().split())


def _extract_event(record: dict[str, Any]) -> dict[str, Any]:
    payload = record.get("payload", record)
    if not isinstance(payload, dict):
        payload = {}

    ro = _first_value(
        payload,
        ("ticket", "invoice"),
        ("ticket", "remote_id"),
        ("invoice_or_ro",),
        ("ro",),
        ("invoice",),
        ("invoice_number",),
        ("ro_number",),
        ("roNumber",),
        ("repair_order",),
        ("work_order", "invoice"),
        ("work_order", "ro_number"),
    )

    status = _first_value(
        payload,
        ("ticket", "status"),
        ("ticket_status",),
        ("status",),
        ("current_status",),
        ("workflow_status",),
        ("workflowStatus",),
        ("job_status",),
    )

    timestamp = _first_value(
        payload,
        ("event", "timestamp"),
        ("timestamp",),
        ("received_at",),
    ) or record.get("received_at")

    return {
        "ro": str(ro).strip() if ro not in (None, "", [], {}) else "",
        "status": _normalize_status(status),
        "timestamp": _parse_time(timestamp),
    }


def _load_events() -> list[dict[str, Any]]:
    if not EVENT_LOG.exists():
        return []

    rows: list[dict[str, Any]] = []
    for line in EVENT_LOG.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                rows.append(item)
        except Exception:
            continue
    return rows


def build_active_ros_state() -> dict[str, Any]:
    latest_by_ro: dict[str, dict[str, Any]] = {}

    for record in _load_events():
        event = _extract_event(record)
        ro = event["ro"]
        if not ro:
            continue

        existing = latest_by_ro.get(ro)
        if existing is None or event["timestamp"] >= existing["timestamp"]:
            latest_by_ro[ro] = event

    active_ros = sorted(
        ro
        for ro, event in latest_by_ro.items()
        if event["status"] not in CLOSED_STATUSES
    )

    return {
        "source": "autoflow_events",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "active_ros": active_ros,
        "count": len(active_ros),
    }


def main() -> None:
    state = build_active_ros_state()
    ACTIVE_ROS_FILE.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_ROS_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(ACTIVE_ROS_FILE)
    print(f"Active ROs: {state['count']}")


if __name__ == "__main__":
    main()
