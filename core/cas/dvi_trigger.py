"""
core/cas/dvi_trigger.py
Callahan Auto & Diesel — DVI Signoff Trigger Handler

Called by the webhook receiver when a dvi_signoff or dvi_signoff_update
event is received from AutoFlow. Runs the DVI gate automatically.

Also handles:
- Unknown event logging for analytics discovery
- Status transition tracking for bottleneck analysis
"""

import os
import json
import time
import base64
import logging
import requests
import threading
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
UNKNOWN_EVENTS_PATH = REPO_ROOT / "data" / "unknown_events" / "unknown_events.jsonl"
TRANSITIONS_PATH = REPO_ROOT / "data" / "status_transitions" / "transitions.jsonl"

# Known event types we already handle
KNOWN_EVENT_TYPES = {
    "status_update",
    "dvi_signoff",
    "dvi_signoff_update",
    "dvi_viewed",
    "ro_approval",
    "wo_signoff",
    "appointment_create",
    "appointment_update",
    "message_status",
    "inbound_message",
}

# DVI pull retry settings
DVI_PULL_DELAY_SECONDS = 15
DVI_PULL_MAX_RETRIES = 3
DVI_PULL_RETRY_WAIT = 10


# ─── AutoFlow API Helper ──────────────────────────────────────────────────────

def _fetch_autoflow(endpoint: str) -> dict:
    api_key = os.getenv("AUTOFLOW_API_KEY")
    api_password = os.getenv("AUTOFLOW_API_PASSWORD")
    subdomain = os.getenv("AUTOFLOW_SUBDOMAIN", "callahanautomotive")

    creds = base64.b64encode(f"{api_key}:{api_password}".encode()).decode()
    headers = {
        "accept": "application/json",
        "Authorization": f"Basic {creds}"
    }
    url = f"https://{subdomain}.autotext.me/api/v1/{endpoint}"
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp.json()


# ─── Unknown Event Logger ─────────────────────────────────────────────────────

def log_unknown_event(payload: dict, received_at: str) -> None:
    """
    Log any event type we haven't seen before.
    This is how we discover new AutoFlow/Techflow data we can use.
    """
    event_type = payload.get("event", {}).get("type", "unknown")
    if event_type in KNOWN_EVENT_TYPES:
        return

    UNKNOWN_EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "received_at": received_at,
        "event_type": event_type,
        "payload_keys": list(payload.keys()),
        "event_keys": list(payload.get("event", {}).keys()),
        "ticket_keys": list(payload.get("ticket", {}).keys()),
        "full_payload": payload
    }
    with UNKNOWN_EVENTS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    logger.info(f"UNKNOWN EVENT LOGGED: {event_type} — may contain new trackable data")
    print(f"[DISCOVERY] Unknown event type: {event_type} — logged for analysis")


# ─── Status Transition Tracker ────────────────────────────────────────────────

def track_status_transition(payload: dict, received_at: str) -> None:
    """
    Record every status change with timestamp for bottleneck analytics.
    Tracks time-in-status per RO over the full workflow.
    """
    event_type = payload.get("event", {}).get("type", "")
    if event_type != "status_update":
        return

    ticket = payload.get("ticket", {})
    ro = str(ticket.get("invoice", "") or ticket.get("remote_id", "") or "unknown")
    status = ticket.get("status", "unknown")
    ticket_id = str(ticket.get("id", ""))

    customer = payload.get("customer", {})
    vehicle = payload.get("vehicle", {})

    record = {
        "received_at": received_at,
        "ro": ro,
        "ticket_id": ticket_id,
        "status": status,
        "customer": f"{customer.get('firstname','')} {customer.get('lastname','')}".strip(),
        "vehicle": f"{vehicle.get('year','')} {vehicle.get('make','')} {vehicle.get('model','')}".strip(),
    }

    TRANSITIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with TRANSITIONS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    logger.info(f"Transition tracked: RO {ro} → {status}")


def get_dvi_start_time(ro: str) -> str:
    """
    Find when this RO last entered 'DVI updates' status.
    Uses the last entry (not first) to handle back-and-forth correctly.
    Returns ISO timestamp or empty string if not found.
    """
    if not TRANSITIONS_PATH.exists():
        return ""

    last_entry_time = ""
    with TRANSITIONS_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                if (str(record.get("ro", "")) == str(ro) and
                        "dvi" in record.get("status", "").lower()):
                    last_entry_time = record.get("received_at", "")
            except json.JSONDecodeError:
                continue

    return last_entry_time


# ─── DVI Gate Runner ─────────────────────────────────────────────────────────

def _run_gate_for_ro(ro: str, trigger_event: str) -> None:
    """
    Pull DVI from AutoFlow and run the gate.
    Called in a background thread so webhook returns immediately.
    Includes delay + retry logic for API timing.
    """
    from core.cas.dvi_gate import run_dvi_gate
    from core.cas.rework_slip import save_slip
    from core.cas.dvi_schema import TriggerEvent
    from core.timeline.job_timeline import log_dvi_gate_result, log_rework_slip_generated
    from core.state.state_manager import save_dvi_review

    print(f"[DVI GATE] RO {ro} — waiting {DVI_PULL_DELAY_SECONDS}s for API to populate...")
    time.sleep(DVI_PULL_DELAY_SECONDS)

    dvi_data = None
    for attempt in range(1, DVI_PULL_MAX_RETRIES + 1):
        try:
            print(f"[DVI GATE] RO {ro} — pulling DVI (attempt {attempt}/{DVI_PULL_MAX_RETRIES})")
            dvi_data = _fetch_autoflow(f"dvi/{ro}")

            # Check if DVI has actual content
            content = dvi_data.get("content", {})
            if content and content.get("dvis"):
                print(f"[DVI GATE] RO {ro} — DVI data ready")
                break
            else:
                print(f"[DVI GATE] RO {ro} — DVI incomplete, retrying in {DVI_PULL_RETRY_WAIT}s")
                if attempt < DVI_PULL_MAX_RETRIES:
                    time.sleep(DVI_PULL_RETRY_WAIT)

        except Exception as e:
            print(f"[DVI GATE] RO {ro} — pull failed attempt {attempt}: {e}")
            if attempt < DVI_PULL_MAX_RETRIES:
                time.sleep(DVI_PULL_RETRY_WAIT)

    if not dvi_data:
        print(f"[DVI GATE] RO {ro} — could not pull DVI after {DVI_PULL_MAX_RETRIES} attempts")
        from core.timeline.job_timeline import log_event
        log_event(
            ro=ro,
            event_type="dvi_gate_error",
            source="system",
            actor="Callie",
            summary=f"DVI gate failed — could not pull DVI after {DVI_PULL_MAX_RETRIES} attempts",
            details={"trigger_event": trigger_event},
            requires_action=True,
            resolved=False
        )
        return

    # Pull work order too (non-fatal if it fails)
    wo_data = {}
    try:
        wo_data = _fetch_autoflow(f"work_orders/{ro}")
    except Exception as e:
        print(f"[DVI GATE] RO {ro} — work order pull failed (non-fatal): {e}")

    # Run the gate
    print(f"[DVI GATE] RO {ro} — running gate...")
    review = run_dvi_gate(
        dvi_data=dvi_data,
        work_order_data=wo_data,
        ro=ro,
        trigger_event=trigger_event
    )

    # Save everything
    save_dvi_review(review)
    log_dvi_gate_result(review)

    if review.rework_required:
        slip_path = save_slip(review)
        log_rework_slip_generated(review, slip_path)
        print(f"[DVI GATE] RO {ro} — REWORK REQUIRED — {review.flag_count} flags — slip saved")
    elif review.review_status == "REVIEW":
        print(f"[DVI GATE] RO {ro} — REVIEW NEEDED — {review.flag_count} flags")
    else:
        print(f"[DVI GATE] RO {ro} — PASSED — cleared for estimate")

    print(f"[DVI GATE] RO {ro} — complete: {review.review_status}")


# ─── Main Entry Point ─────────────────────────────────────────────────────────

def handle_webhook_event(payload: dict, received_at: str) -> None:
    """
    Main entry point called from webhook receiver for every incoming event.
    Routes to the right handler based on event type.
    Always runs unknown event check and status transition tracking.
    """
    event_type = payload.get("event", {}).get("type", "unknown")
    ticket = payload.get("ticket", {})
    ro = str(ticket.get("invoice", "") or ticket.get("remote_id", "") or "")

    # Always track status transitions for analytics
    track_status_transition(payload, received_at)

    # Always log unknown events for discovery
    log_unknown_event(payload, received_at)

    # Handle DVI signoff — trigger gate in background thread
    if event_type in ("dvi_signoff", "dvi_signoff_update"):
        if not ro or ro == "unknown":
            # Try to get RO from callback endpoint
            callback = payload.get("event", {}).get("callback_endpoint", "")
            if "/dvi/" in callback:
                ro = callback.split("/dvi/")[-1].strip("/")

        if ro and ro != "unknown":
            print(f"[DVI GATE] Triggered by {event_type} for RO {ro}")
            thread = threading.Thread(
                target=_run_gate_for_ro,
                args=(ro, event_type),
                daemon=True
            )
            thread.start()
        else:
            print(f"[DVI GATE] Could not extract RO from {event_type} payload")
