import json
import os
from datetime import datetime, timedelta

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(CURRENT_DIR)
SHOP_STATE_PATH = os.path.join(REPO_ROOT, "state", "shop_state.json")
BOARD_STATE_PATH = os.path.join(REPO_ROOT, "state", "board_state.json")
BOARD_ACTION_LOG_PATH = os.path.join(REPO_ROOT, "state", "board_actions.jsonl")
HERMES_LOG_PATH = os.path.join(REPO_ROOT, "state", "hermes_feedback.jsonl")
BOARD_OVERRIDE_LOG_PATH = os.path.join(REPO_ROOT, "state", "board_overrides.jsonl")
WEBHOOK_EVENT_LOG_PATHS = [
    os.path.join(REPO_ROOT, "state", "autoflow_webhook_events.jsonl"),
    os.path.join(REPO_ROOT, "state", "webhook_events.jsonl"),
    os.path.join(REPO_ROOT, "data", "autoflow_events", "autoflow_webhook_events.jsonl"),
]


def _append_jsonl(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def _read_jsonl(path):
    if not os.path.exists(path):
        return []
    rows = []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except Exception:
                    continue
                if isinstance(payload, dict):
                    rows.append(payload)
    except Exception:
        return []
    return rows


def _inject_dvi_status(jobs):
    dvi_dir = os.path.join(REPO_ROOT, "state", "dvi_reviews")
    for job in jobs:
        if not isinstance(job, dict):
            continue
        ro = str(job.get("ro") or "").strip()
        if not ro:
            job["dvi_review_status"] = "NO_DVI"
            continue
        review_path = os.path.join(dvi_dir, f"{ro}.json")
        if not os.path.exists(review_path):
            job["dvi_review_status"] = "NO_DVI"
            continue
        try:
            with open(review_path, "r", encoding="utf-8") as f:
                review = json.load(f)
            job["dvi_review_status"] = review.get("review_status", "NO_DVI")
        except Exception:
            job["dvi_review_status"] = "NO_DVI"


def _recent_source_activity(jobs, limit=8):
    items = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        ro = str(job.get("ro", "")).strip() or "Unknown RO"
        customer = str(job.get("customer", "")).strip() or "Unknown Customer"
        activity = str((((job.get("source_evidence") or {}).get("latest_activity")) or "")).strip()
        status = str(job.get("workflow_status", "unknown")).strip() or "unknown"
        if activity:
            items.append({
                "title": f"RO {ro} - {customer}",
                "detail": f"{activity} Current AutoFlow status: {status}.",
            })
            continue
        conflict = job.get("source_conflict", {}) if isinstance(job.get("source_conflict"), dict) else {}
        if conflict.get("has_conflict"):
            items.append({
                "title": f"RO {ro} - source conflict",
                "detail": str(conflict.get("summary", "")).strip(),
            })
    return items[:limit]


def _recent_ai_activity(limit=8):
    items = []
    combined = []
    for row in _read_jsonl(BOARD_ACTION_LOG_PATH):
        if isinstance(row, dict):
            combined.append(("board_action", row))
    for row in _read_jsonl(BOARD_OVERRIDE_LOG_PATH):
        if isinstance(row, dict):
            combined.append(("override", row))
    for row in _read_jsonl(HERMES_LOG_PATH):
        if isinstance(row, dict):
            combined.append(("callie", row))

    def _stamp(entry):
        payload = entry[1]
        return str(payload.get("timestamp", ""))

    for kind, row in sorted(combined, key=_stamp, reverse=True):
        ro = str(row.get("ro", "")).strip()
        ro_label = f"RO {ro}" if ro else "Board"
        if kind == "board_action":
            action_type = str(row.get("action_type", "details")).strip() or "details"
            note = str(row.get("note", "")).strip() or "No note captured."
            items.append({
                "title": f"{ro_label} - {action_type.replace('_', ' ').title()} - {row.get('timestamp', '--')}",
                "detail": note,
            })
        elif kind == "override":
            changed = [label for label, key in (
                ("lane", "priority_lane"),
                ("owner", "waiting_on"),
                ("technician", "technician"),
                ("summary", "summary"),
            ) if str(row.get(key, "")).strip()]
            if changed:
                items.append({
                    "title": f"{ro_label} - override - {row.get('timestamp', '--')}",
                    "detail": "Changed " + ", ".join(changed) + ". " + (str(row.get("note", "")).strip() or "No override note captured."),
                })
        else:
            question = str(row.get("question", "")).strip() or "No question captured."
            answer = str(row.get("answer", "")).strip() or "No answer captured."
            items.append({
                "title": f"{ro_label} - Callie - {row.get('timestamp', '--')}",
                "detail": f"Q: {question} | A: {answer[:220]}",
            })
        if len(items) >= limit:
            break
    return items


def _recount_board(board_state):
    if not isinstance(board_state, dict):
        return board_state
    jobs = board_state.get("jobs", [])
    if not isinstance(jobs, list):
        return board_state
    lane_counts = {"P1": 0, "P2": 0, "P3": 0, "P4": 0}
    waiting_counts = {"Mitch": 0, "Drew": 0, "Preston": 0, "External Hold": 0, "Needs Review": 0}
    open_alert_count = 0
    for job in jobs:
        if not isinstance(job, dict):
            continue
        lane = str(job.get("priority_lane", "P3"))
        waiting = str(job.get("waiting_on", "Needs Review"))
        lane_counts[lane] = lane_counts.get(lane, 0) + 1
        waiting_counts[waiting] = waiting_counts.get(waiting, 0) + 1
        alerts = job.get("alerts", [])
        if isinstance(alerts, list):
            open_alert_count += len(alerts)
    board_state["lane_counts"] = lane_counts
    board_state["waiting_on_counts"] = waiting_counts
    board_state["open_alert_count"] = open_alert_count
    return board_state


def _latest_action_state():
    state = {}
    horizon = datetime.now() - timedelta(hours=12)
    for row in _read_jsonl(BOARD_ACTION_LOG_PATH):
        ro = str(row.get("ro", "")).strip()
        action_type = str(row.get("action_type", "")).strip()
        if not ro or not action_type:
            continue
        try:
            stamp = datetime.strptime(str(row.get("timestamp", "")), "%Y-%m-%d %H:%M:%S")
        except Exception:
            stamp = datetime.now()
        if stamp < horizon:
            continue
        entry = state.setdefault(ro, {})
        entry[f"{action_type}_cleared"] = True
        entry[f"{action_type}_updated_at"] = stamp.strftime("%Y-%m-%d %H:%M:%S")
    return state


def _latest_override_state():
    state = {}
    for row in _read_jsonl(BOARD_OVERRIDE_LOG_PATH):
        ro = str(row.get("ro", "")).strip()
        if not ro:
            continue
        state[ro] = row
    return state


def _extract_event_ro(row):
    payload = row.get("payload", {}) if isinstance(row.get("payload"), dict) else {}
    ticket = payload.get("ticket", {}) if isinstance(payload.get("ticket"), dict) else {}
    return str(row.get("ro") or row.get("ro_number") or row.get("repair_order_id") or ticket.get("invoice") or payload.get("ro") or "").strip()


def _extract_event_timestamp(row):
    payload = row.get("payload", {}) if isinstance(row.get("payload"), dict) else {}
    return str(row.get("timestamp") or row.get("received_at") or payload.get("timestamp") or "").strip()


def _latest_webhook_timestamps():
    latest = {}
    for path in WEBHOOK_EVENT_LOG_PATHS:
        for row in _read_jsonl(path):
            ro = _extract_event_ro(row)
            timestamp = _extract_event_timestamp(row)
            if ro and timestamp:
                latest[ro] = timestamp
    return latest


def _apply_timestamp_fallbacks(board_state):
    if not isinstance(board_state, dict):
        return board_state
    jobs = board_state.get("jobs", [])
    if not isinstance(jobs, list):
        return board_state
    event_timestamps = _latest_webhook_timestamps()
    generated_at = str(board_state.get("generated_at") or board_state.get("timestamp") or "").strip()
    for job in jobs:
        if not isinstance(job, dict):
            continue
        if str(job.get("status_updated_at") or "").strip():
            continue
        ro = str(job.get("ro", "")).strip()
        fallback_timestamp = event_timestamps.get(ro) or generated_at
        if fallback_timestamp:
            job["status_updated_at"] = fallback_timestamp
            job["status_updated_at_source"] = "webhook_event" if event_timestamps.get(ro) else "board_generated_at"
    return board_state


def _apply_override_state(board_state):
    if not isinstance(board_state, dict):
        return board_state
    override_state = _latest_override_state()
    jobs = board_state.get("jobs", [])
    if not isinstance(jobs, list):
        board_state["override_state"] = override_state
        return board_state

    risk_by_lane = {"P1": "CRITICAL", "P2": "YELLOW", "P3": "YELLOW", "P4": "NORMAL"}
    for job in jobs:
        if not isinstance(job, dict):
            continue
        ro = str(job.get("ro", "")).strip()
        override = override_state.get(ro)
        if not override:
            continue
        if override.get("priority_lane"):
            job["priority_lane"] = override["priority_lane"]
            job["risk_level"] = risk_by_lane.get(job["priority_lane"], job.get("risk_level", "NORMAL"))
            if job["priority_lane"] == "P4":
                job["incoming_soon"] = None
        if override.get("waiting_on"):
            job["waiting_on"] = override["waiting_on"]
        if override.get("workflow_status") or override.get("to_status"):
            job["workflow_status"] = str(override.get("workflow_status") or override.get("to_status")).strip()
        if override.get("technician"):
            job["technician"] = override["technician"]
            technicians = [part.strip() for part in str(override["technician"]).split(",") if part.strip()]
            if technicians:
                job["technicians"] = technicians
        if override.get("summary"):
            job["summary"] = override["summary"]
        if override.get("note"):
            reasons = job.get("board_reasons", [])
            if not isinstance(reasons, list):
                reasons = []
            reasons.append("Local override applied: " + str(override["note"]))
            job["board_reasons"] = reasons
        job["override_state"] = override
    board_state["override_state"] = override_state
    return _recount_board(board_state)


def _apply_action_state(board_state):
    if not isinstance(board_state, dict):
        return board_state
    action_state = _latest_action_state()
    jobs = board_state.get("jobs", [])
    if not isinstance(jobs, list):
        board_state["action_state"] = action_state
        return board_state

    for job in jobs:
        if not isinstance(job, dict):
            continue
        ro = str(job.get("ro", "")).strip()
        ro_state = action_state.get(ro, {})
        alerts = job.get("alerts", [])
        if not isinstance(alerts, list):
            alerts = []
        filtered_alerts = []
        for alert in alerts:
            code = alert.get("code") if isinstance(alert, dict) else ""
            if code == "customer_follow_up_due" and ro_state.get("communication_cleared"):
                continue
            if code == "verify_tech_clock_in" and ro_state.get("productivity_cleared"):
                continue
            if code in {"missing_ro", "status_mapping_gap", "missing_tech_assignment", "missing_info", "missing_customer_concern", "missing_completed_dvi"} and ro_state.get("data_cleared"):
                continue
            filtered_alerts.append(alert)
        job["alerts"] = filtered_alerts
        if ro_state:
            job["action_state"] = ro_state

    board_state["action_state"] = action_state
    return _recount_board(board_state)


def _fallback_jobs_payload(reason="autoflow_unavailable"):
    return {
        "source": "fallback",
        "status": "ok",
        "jobs": [],
        "count": 0,
        "message": reason,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _load_jobs_from_autoflow():
    try:
        with open(SHOP_STATE_PATH, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload
    except Exception:
        return _fallback_jobs_payload("shop_state_not_found")


def _load_board_state():
    try:
        with open(BOARD_STATE_PATH, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            board_state = _apply_timestamp_fallbacks(_apply_action_state(_apply_override_state(payload)))
            jobs = board_state.get("jobs", []) if isinstance(board_state.get("jobs"), list) else []
            _inject_dvi_status(jobs)
            board_state["fetched_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            board_state["activity_feed"] = _recent_source_activity(jobs)
            board_state["ai_activity_feed"] = _recent_ai_activity()
            return board_state
    except Exception:
        pass

    board_state = _apply_action_state(_apply_override_state({
        "source": "board_rules_v1",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": 0,
        "jobs": [],
        "lane_counts": {"P1": 0, "P2": 0, "P3": 0, "P4": 0},
        "waiting_on_counts": {"Mitch": 0, "Drew": 0, "Preston": 0, "External Hold": 0, "Needs Review": 0},
        "open_alert_count": 0,
        "message": "No board_state.json found. Run python scripts/build_board_state.py first.",
    }))
    board_state["fetched_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    board_state["activity_feed"] = []
    board_state["ai_activity_feed"] = _recent_ai_activity()
    return board_state


def _find_job(ro):
    board_state = _load_board_state()
    jobs = board_state.get("jobs", []) if isinstance(board_state, dict) else []
    for job in jobs:
        if isinstance(job, dict) and str(job.get("ro", "")) == str(ro):
            return job
    return None