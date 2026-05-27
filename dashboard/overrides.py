import json
import os
from datetime import datetime

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(CURRENT_DIR)
BOARD_OVERRIDE_LOG_PATH = os.path.join(REPO_ROOT, "state", "board_overrides.jsonl")


def _append_jsonl(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def record_job_override(payload, current_job=None):
    ro = str(payload.get("ro", "")).strip()
    if not ro:
        raise ValueError("ro is required")
    to_status = str(payload.get("to_status", payload.get("workflow_status", ""))).strip()
    advisor = str(payload.get("advisor", "")).strip()
    entry = {
        "ro": ro,
        "advisor": advisor,
        "from_status": str(payload.get("from_status", (current_job or {}).get("workflow_status", ""))).strip(),
        "to_status": to_status,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": str(payload.get("source", "advisor_board")).strip() or "advisor_board",
        "note": str(payload.get("note", "manual advisor reassignment")).strip(),
        "workflow_status": to_status,
    }
    if advisor:
        entry["waiting_on"] = advisor
    _append_jsonl(BOARD_OVERRIDE_LOG_PATH, entry)
    return entry
