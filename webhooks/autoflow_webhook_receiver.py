"""
AutoFlow Webhook Receiver + Hermes Memory Integration
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request

# ====================== PATH SETUP ======================
REPO_ROOT = Path(__file__).resolve().parents[1]

# Add hermes and shop-observer-core to Python path
root = Path("C:/AI-RUNTIME")
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "shop-observer-core"))

from hermes.orchestration.hermes_webhook_bridge import HermesWebhookBridge

# ====================== EXISTING CODE ======================
EVENT_LOG_PATH = REPO_ROOT / "data" / "autoflow_events" / "autoflow_events.jsonl"
TRANSITIONS_PATH = REPO_ROOT / "data" / "status_transitions" / "transitions.jsonl"
RO_ACTIVITY_DIR = REPO_ROOT / "data" / "ro_activity"
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_advisor_game_plan.py"
ACTIVE_ROS_BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_active_ros_state.py"
SHOP_STATE_BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_shop_state.py"
BOARD_STATE_BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_board_state.py"
STATUS_TIMESTAMPS_PATH = REPO_ROOT / "state" / "status_timestamps.json"


from core.cas.dvi_trigger import handle_webhook_event
app = Flask(__name__)
bridge = HermesWebhookBridge()   # ← Hermes Bridge

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
    event_type = _first_value(
        payload, ("event", "type"), ("event_type",), ("eventType",), ("type",), ("meta", "event_type")
    )
    invoice_or_ro = _first_value(
        payload, ("ticket", "invoice"), ("invoice",), ("invoice_number",), ("ro_number",), ("roNumber",),
        ("repair_order",), ("work_order", "invoice"), ("work_order", "ro_number")
    )
    # ... (keeping your full function)
    ticket_status = _first_value(payload, ("ticket", "status"), ("ticket_status",), ("status",), ("current_status",))
    vehicle_year = _first_value(payload, ("vehicle", "year"), ("vehicle_year",), ("work_order", "vehicle", "year"))
    vehicle_make = _first_value(payload, ("vehicle", "make"), ("vehicle_make",), ("work_order", "vehicle", "make"))
    vehicle_model = _first_value(payload, ("vehicle", "model"), ("vehicle_model",), ("work_order", "vehicle", "model"))
    
    vehicle = " ".join([_safe_text(x) for x in [vehicle_year, vehicle_make, vehicle_model] if x != "unknown"]) or "unknown"
    
    return {
        "event_type": _safe_text(event_type),
        "invoice_or_ro": _safe_text(invoice_or_ro),
        "ticket_status": _safe_text(ticket_status),
        "vehicle": vehicle,
        "timestamp": _safe_text(received_at),
    }

def _vehicle_string(payload: dict[str, Any]) -> str:
    vehicle_year = _first_value(payload, ("vehicle", "year"), ("vehicle_year",), ("work_order", "vehicle", "year"))
    vehicle_make = _first_value(payload, ("vehicle", "make"), ("vehicle_make",), ("work_order", "vehicle", "make"))
    vehicle_model = _first_value(payload, ("vehicle", "model"), ("vehicle_model",), ("work_order", "vehicle", "model"))
    return " ".join([_safe_text(x) for x in [vehicle_year, vehicle_make, vehicle_model] if x not in (None, "", "unknown")]) or "unknown"

def _parse_iso_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None

def _last_ro_activity(ro: str) -> dict[str, Any] | None:
    path = RO_ACTIVITY_DIR / f"{ro}.jsonl"
    if not path.exists():
        return None
    try:
        last_line = ""
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    last_line = line
        return json.loads(last_line) if last_line else None
    except Exception as exc:
        print(f"RO activity read failed for {ro}: {exc}")
        return None

def _hours_between(start: Any, end: Any) -> float | None:
    start_dt = _parse_iso_timestamp(start)
    end_dt = _parse_iso_timestamp(end)
    if not start_dt or not end_dt:
        return None
    return round(max(0.0, (end_dt - start_dt).total_seconds() / 3600), 4)

def _first_tech_name(techs: Any) -> str:
    if isinstance(techs, list) and techs:
        first = techs[0]
        if isinstance(first, dict):
            return _safe_text(first.get("name") or first.get("full_name") or first.get("tech_name"))
        return _safe_text(first)
    return "unassigned"

def _safe_ro_filename(ro: str) -> str:
    safe = "".join(ch for ch in str(ro or "unknown") if ch.isalnum() or ch in ("-", "_"))
    return safe or "unknown"

def _load_status_timestamps() -> dict[str, Any]:
    try:
        if STATUS_TIMESTAMPS_PATH.exists():
            data = json.loads(STATUS_TIMESTAMPS_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception as exc:
        print(f"STATUS TIMESTAMP READ FAILED: {exc}")
    return {}

def _write_status_timestamps(data: dict[str, Any]) -> None:
    STATUS_TIMESTAMPS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = STATUS_TIMESTAMPS_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=True, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(STATUS_TIMESTAMPS_PATH)

def _normalize_status_for_clock(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").split())

def _update_status_timestamp(payload: dict[str, Any], received_at: str) -> None:
    """Clock status age from deploy time forward; first-seen entries are lower bounds."""
    ticket = payload.get("ticket", {}) if isinstance(payload.get("ticket"), dict) else {}
    ro = str(ticket.get("invoice", "")).strip()
    status = str(ticket.get("status", "")).strip()
    if not ro or not status:
        return

    data = _load_status_timestamps()
    current = data.get(ro) if isinstance(data.get(ro), dict) else None
    if not current:
        data[ro] = {"status": status, "status_since": received_at, "since_first_seen": True}
    elif _normalize_status_for_clock(current.get("status", "")) != _normalize_status_for_clock(status):
        data[ro] = {"status": status, "status_since": received_at, "since_first_seen": False}
    _write_status_timestamps(data)

def _update_status_timestamp_safely(payload: dict[str, Any], received_at: str) -> None:
    try:
        _update_status_timestamp(payload, received_at)
    except Exception as exc:
        print(f"STATUS TIMESTAMP WRITE FAILED: {exc}")

def _append_event(payload: dict[str, Any], received_at: str) -> None:
    EVENT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    event_record = {"received_at": received_at, "source": "autoflow_webhook", "payload": payload}
    with EVENT_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event_record, separators=(",", ":"), sort_keys=True))
        handle.write("\n")

def _append_transition_and_activity(payload: dict[str, Any], received_at: str) -> None:
    event_data = payload.get("event", {}) if isinstance(payload.get("event"), dict) else {}
    ticket = payload.get("ticket", {}) if isinstance(payload.get("ticket"), dict) else {}
    customer_data = payload.get("customer", {}) if isinstance(payload.get("customer"), dict) else {}
    vehicle_data = payload.get("vehicle", {}) if isinstance(payload.get("vehicle"), dict) else {}

    event_type = event_data.get("type", "unknown")
    invoice = str(ticket.get("invoice", "")).strip()
    ticket_id = str(ticket.get("id", "")).strip()
    status = ticket.get("status", "")
    customer = customer_data.get("firstname", "") + " " + customer_data.get("lastname", "")
    customer = customer.strip()
    vehicle_year = str(vehicle_data.get("year", ""))
    vehicle_make = vehicle_data.get("make", "")
    vehicle_model = vehicle_data.get("model", "")
    vehicle_str = f"{vehicle_year} {vehicle_make} {vehicle_model}".strip()
    advisor = ticket.get("advisor", {})
    techs = ticket.get("techs", [])
    event_timestamp = event_data.get("timestamp", "")
    event_id = event_data.get("id", "")
    callback_endpoint = event_data.get("callback_endpoint", "")
    if not isinstance(advisor, dict):
        advisor = {}
    if not isinstance(techs, list):
        techs = []

    previous = _last_ro_activity(invoice)
    hours_since_last_event = _hours_between(previous.get("received_at") if previous else "", received_at)
    tech_on_job = techs[0]["name"] if techs and isinstance(techs[0], dict) and "name" in techs[0] else "unassigned"
    transition = {
        "received_at": received_at,
        "event_type": event_type,
        "event_timestamp": event_timestamp,
        "ro": invoice,
        "ticket_id": ticket_id,
        "status": status,
        "customer": customer,
        "vehicle": vehicle_str,
        "advisor": advisor,
        "techs": techs,
        "event_id": event_id,
        "callback_endpoint": callback_endpoint,
        "tech_on_job": tech_on_job,
        "hours_since_last_event": hours_since_last_event
    }

    TRANSITIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TRANSITIONS_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(transition, ensure_ascii=True, separators=(",", ":"), sort_keys=True))
        handle.write("\n")

    RO_ACTIVITY_DIR.mkdir(parents=True, exist_ok=True)
    ro_path = RO_ACTIVITY_DIR / f"{_safe_ro_filename(invoice)}.jsonl"
    with ro_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(transition, ensure_ascii=True, separators=(",", ":"), sort_keys=True))
        handle.write("\n")

def _append_transition_and_activity_safely(payload: dict[str, Any], received_at: str) -> None:
    try:
        _append_transition_and_activity(payload, received_at)
    except Exception as exc:
        print(f"TRANSITION ACTIVITY WRITE FAILED: {exc}")

def _rebuild_advisor_tasks() -> None:
    try:
        subprocess.run([sys.executable, str(BUILD_SCRIPT)], cwd=str(REPO_ROOT), check=False)
        print("TASK REBUILD TRIGGERED")
    except Exception as e:
        print(f"TASK REBUILD FAILED: {e}")


def _run_build_script(script_path: Path, label: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(REPO_ROOT),
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print(f"{label} REBUILD TRIGGERED")
            return True, ""

        reason = (result.stderr or result.stdout or f"exit_code={result.returncode}").strip()
        print(f"{label} REBUILD FAILED: {reason}")
        return False, reason
    except Exception as exc:
        reason = str(exc)
        print(f"{label} REBUILD FAILED: {reason}")
        return False, reason


def _rebuild_local_state() -> dict[str, Any]:
    active_ros_ok, active_ros_reason = _run_build_script(ACTIVE_ROS_BUILD_SCRIPT, "ACTIVE RO STATE")
    shop_state_ok, shop_state_reason = _run_build_script(SHOP_STATE_BUILD_SCRIPT, "SHOP STATE")
    board_state_ok, board_state_reason = _run_build_script(BOARD_STATE_BUILD_SCRIPT, "BOARD STATE")

    failures = []
    if not active_ros_ok:
        failures.append({"step": "build_active_ros_state", "reason": active_ros_reason})
    if not shop_state_ok:
        failures.append({"step": "build_shop_state", "reason": shop_state_reason})
    if not board_state_ok:
        failures.append({"step": "build_board_state", "reason": board_state_reason})

    return {
        "active_ros_rebuilt": active_ros_ok,
        "shop_state_rebuilt": shop_state_ok,
        "board_state_rebuilt": board_state_ok,
        "failures": failures,
    }

def _print_summary(summary: dict[str, str]) -> None:
    print("AUTOFLOW WEBHOOK EVENT")
    print(f"- event type: {summary['event_type']}")
    print(f"- invoice/RO: {summary['invoice_or_ro']}")
    print(f"- ticket status: {summary['ticket_status']}")
    print(f"- vehicle: {summary['vehicle']}")
    print(f"- timestamp: {summary['timestamp']}")

# ====================== MAIN ROUTE ======================
@app.post("/webhooks/autoflow")
def receive_autoflow_webhook():
    if not request.is_json:
        return jsonify({"status": "error", "message": "JSON payload required"}), 400
    
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"status": "error", "message": "JSON object required"}), 400

    received_at = datetime.now(timezone.utc).isoformat()

    # === HERMES INTEGRATION ===
    hermes_result = bridge.process_autoflow_event(payload)

    # Your original logic continues
    _append_event(payload, received_at)
    _append_transition_and_activity_safely(payload, received_at)
    _update_status_timestamp_safely(payload, received_at)
    handle_webhook_event(payload, received_at)
    _rebuild_advisor_tasks()
    state_rebuild = _rebuild_local_state()
    
    summary = _safe_summary(payload, received_at)
    _print_summary(summary)

    return jsonify({
        "status": "received",
        "hermes_saved": hermes_result.get("saved_to_hermes", False),
        "event_type": summary["event_type"],
        "invoice_or_ro": summary["invoice_or_ro"],
        "tasks_rebuilt": True,
        "active_ros_rebuilt": state_rebuild["active_ros_rebuilt"],
        "shop_state_rebuilt": state_rebuild["shop_state_rebuilt"],
        "board_state_rebuilt": state_rebuild["board_state_rebuilt"],
        "state_rebuild_failures": state_rebuild["failures"],
    })

@app.get("/health")
def health_check():
    return jsonify({"status": "ok", "service": "autoflow_webhook_receiver", "hermes": "connected"})

if __name__ == "__main__":
    print("🚀 Starting AutoFlow Webhook Receiver with Hermes Memory...")
    app.run(host="127.0.0.1", port=5055, debug=False)
