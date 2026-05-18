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
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_advisor_game_plan.py"
ACTIVE_ROS_BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_active_ros_state.py"
SHOP_STATE_BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_shop_state.py"
BOARD_STATE_BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_board_state.py"

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

def _append_event(payload: dict[str, Any], received_at: str) -> None:
    EVENT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    event_record = {"received_at": received_at, "source": "autoflow_webhook", "payload": payload}
    with EVENT_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event_record, separators=(",", ":"), sort_keys=True))
        handle.write("\n")

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
