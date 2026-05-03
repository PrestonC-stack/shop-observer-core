from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, Response


REPO_ROOT = Path(__file__).resolve().parents[1]
EVENT_LOG_PATH = REPO_ROOT / "data" / "autoflow_events" / "autoflow_events.jsonl"
STATE_PATH = REPO_ROOT / "state" / "active_shop_state.json"

app = Flask(__name__)


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


def _safe_text(value: Any, default: str = "unknown") -> str:
    if value in (None, "", [], {}):
        return default
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return default


def _vehicle_summary(payload: dict[str, Any]) -> str:
    year = _first_value(payload, ("vehicle", "year"), ("vehicle_year",), ("vehicleYear",))
    make = _first_value(payload, ("vehicle", "make"), ("vehicle_make",), ("vehicleMake",))
    model = _first_value(payload, ("vehicle", "model"), ("vehicle_model",), ("vehicleModel",))
    parts = [_safe_text(part, "") for part in (year, make, model)]
    return " ".join(part for part in parts if part).strip() or "unknown"


def _parse_timestamp(value: Any) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


def _load_event_records() -> list[dict[str, Any]]:
    if not EVENT_LOG_PATH.exists():
        return []

    records: list[dict[str, Any]] = []
    with EVENT_LOG_PATH.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                event_record = json.loads(line)
            except json.JSONDecodeError:
                records.append(
                    {
                        "received_at": "",
                        "source": "autoflow_webhook",
                        "payload": {},
                        "parse_error": f"Invalid JSONL line {line_number}",
                    }
                )
                continue
            if isinstance(event_record, dict):
                records.append(event_record)
    return records


def _extract_safe_event(record: dict[str, Any]) -> dict[str, str]:
    payload = record.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}

    event_type = _first_value(
        payload,
        ("event", "type"),
        ("event_type",),
        ("eventType",),
        ("type",),
    )
    invoice_or_ro = _first_value(
        payload,
        ("ticket", "invoice"),
        ("invoice",),
        ("invoice_number",),
        ("invoiceNumber",),
        ("ro_number",),
        ("roNumber",),
    )
    ticket_status = _first_value(
        payload,
        ("ticket", "status"),
        ("ticket_status",),
        ("ticketStatus",),
        ("status",),
        ("current_status",),
        ("currentStatus",),
    )
    event_timestamp = _first_value(
        payload,
        ("timestamp",),
        ("event", "timestamp"),
        ("event_timestamp",),
        ("eventTimestamp",),
        ("updated_at",),
        ("updatedAt",),
    )

    timestamp = _safe_text(event_timestamp or record.get("received_at"))

    return {
        "invoice_or_ro": _safe_text(invoice_or_ro),
        "event_type": _safe_text(event_type),
        "current_status": _safe_text(ticket_status),
        "vehicle": _vehicle_summary(payload),
        "last_update": timestamp,
    }


def build_active_shop_state() -> dict[str, Any]:
    events_by_ro: dict[str, list[dict[str, str]]] = {}

    for record in _load_event_records():
        safe_event = _extract_safe_event(record)
        invoice_or_ro = safe_event["invoice_or_ro"]
        if invoice_or_ro == "unknown":
            continue
        events_by_ro.setdefault(invoice_or_ro, []).append(safe_event)

    rows: list[dict[str, Any]] = []
    for invoice_or_ro, events in events_by_ro.items():
        latest_event = max(events, key=lambda event: _parse_timestamp(event["last_update"]))
        rows.append(
            {
                "invoice_or_ro": invoice_or_ro,
                "event_type": latest_event["event_type"],
                "current_status": latest_event["current_status"],
                "vehicle": latest_event["vehicle"],
                "last_update": latest_event["last_update"],
                "event_count": len(events),
            }
        )

    rows.sort(key=lambda row: _parse_timestamp(row["last_update"]), reverse=True)
    status_counts = Counter(row["current_status"] for row in rows)
    latest_event_time = rows[0]["last_update"] if rows else "none"

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "local_autoflow_webhook_events",
        "event_log_path": str(EVENT_LOG_PATH),
        "summary": {
            "total_active_ros": len(rows),
            "status_counts": dict(sorted(status_counts.items())),
            "latest_event_time": latest_event_time,
        },
        "rows": rows,
    }


def write_active_shop_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def _html_escape(value: Any) -> str:
    text = _safe_text(value, "")
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def render_dashboard(state: dict[str, Any]) -> str:
    summary = state["summary"]
    rows = state["rows"]
    status_counts = summary["status_counts"]
    status_text = ", ".join(
        f"{_html_escape(status)}: {count}" for status, count in status_counts.items()
    ) or "none"
    table_rows = "\n".join(
        "<tr>"
        f"<td>{_html_escape(row['invoice_or_ro'])}</td>"
        f"<td>{_html_escape(row['event_type'])}</td>"
        f"<td>{_html_escape(row['current_status'])}</td>"
        f"<td
