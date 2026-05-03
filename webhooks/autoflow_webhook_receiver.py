from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request


REPO_ROOT = Path(__file__).resolve().parents[1]
EVENT_LOG_PATH = REPO_ROOT / "data" / "autoflow_events" / "autoflow_events.jsonl"

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


def _first_value(payload: dict[str, Any], *paths: tuple[Any, ...]) -> Any:
    for path in paths:
        value = _deep_get(payload, path)
        if value not in (None, "", [], {}):
            return value
    return None


def _safe_text(value: Any) -> str:
    if value in (None, "", [], {}):
        return "unknown"
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return "unknown"


def _safe_summary(payload: dict[str, Any], received_at: str) -> dict[str, str]:
    # ✅ FIXED: prioritize nested AutoFlow structure
    event_type = _first_value(
        payload,
        ("event", "type"),  # 🔥 FIX
        ("event_type",),
        ("eventType",),
        ("type",),
        ("meta", "event_type"),
    )

    invoice_or_ro = _first_value(
        payload,
        ("ticket", "invoice"),  # 🔥 FIX
        ("invoice",),
        ("invoice_number",),
        ("invoiceNumber",),
        ("ro_number",),
        ("roNumber",),
        ("repair_order",),
        ("repairOrder",),
        ("work_order", "invoice"),
        ("work_order", "ro_number"),
        ("workOrder", "invoiceNumber"),
        ("workOrder", "roNumber"),
    )

    ticket_status = _first_value(
        payload,
        ("ticket", "status"),  # 🔥 FIX
        ("ticket_status",),
        ("ticketStatus",),
        ("status",),
        ("current_status",),
        ("currentStatus",),
        ("work_order", "status"),
        ("workOrder", "status"),
    )

    vehicle_year = _first_value(
        payload,
        ("vehicle", "year"),
        ("vehicle_year",),
        ("vehicleYear",),
        ("work_order", "vehicle", "year"),
        ("workOrder", "vehicle", "year"),
    )

    vehicle_make = _first_value(
        payload,
        payload,
        ("vehicle", "make"),
        ("vehicle_make",),
        ("vehicleMake",),
        ("work_order", "vehicle", "make"),
        ("workOrder", "vehicle", "make"),
    )

    vehicle_model = _first_value(
        payload,
        ("vehicle", "model"),
        ("vehicle_model",),
        ("vehicleModel",),
        ("work_order", "vehicle", "model"),
        ("workOrder", "vehicle", "model"),
    )

    event_timestamp = _first_value(
        payload,
        ("timestamp",),
        ("event", "timestamp"),  # 🔥 FIX
        ("event_timestamp",),
        ("eventTimestamp",),
        ("updated_at",),
        ("updatedAt",),
        ("meta", "timestamp"),
    )

    vehicle_parts = [
        _safe_text(vehicle_year),
        _safe_text(vehicle_make),
        _safe_text(vehicle_model),
    ]
    vehicle = " ".join(part for part in vehicle_parts if part != "unknown") or "unknown"

    return {
        "event_type": _safe_text(event_type),
        "invoice_or_ro": _safe_text(invoice_or_ro),
        "ticket_status": _safe_text(ticket_status),
        "vehicle": vehicle,
        "timestamp": _safe_text(event_timestamp or received_at),
    }


def _append_event(payload: dict[str, Any], received_at: str) -> None:
    EVENT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    event_record = {
        "received_at": received_at,
        "source": "autoflow_webhook",
        "payload": payload,
    }
    with EVENT_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event_record, separators=(",", ":"), sort_keys=True))
        handle.write("\n")


def _print_summary(summary: dict[str, str]) -> None:
    print("AUTOFLOW WEBHOOK EVENT")
    print(f"- event type: {summary['event_type']}")
    print(f"- invoice/RO: {summary['invoice_or_ro']}")
    print(f"- ticket status: {summary['ticket_status']}")
    print(f"- vehicle: {summary['vehicle']}")
    print(f"- timestamp: {summary['timestamp']}")


@app.post("/webhooks/autoflow")
def receive_autoflow_webhook():
    if not request.is_json:
        return jsonify({"status": "error", "message": "JSON payload required"}), 400

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"status": "error", "message": "JSON object required"}), 400

    received_at = datetime.now(timezone.utc).isoformat()
    _append_event(payload, received_at)
    summary = _safe_summary(payload, received_at)
    _print_summary(summary)

    return jsonify(
        {
            "status": "received",
            "saved": True,
            "event_type": summary["event_type"],
            "invoice_or_ro": summary["invoice_or_ro"],
        }
    )


@app.get("/health")
def health_check():
    return jsonify({"status": "ok", "service": "autoflow_webhook_receiver"})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5055, debug=False)