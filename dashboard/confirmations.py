import json
import os
from datetime import datetime

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(CURRENT_DIR)
CONFIRMATION_LOG_PATH = os.path.join(REPO_ROOT, "state", "confirmations.jsonl")


def _append_jsonl(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def _read_jsonl(path):
    if not os.path.exists(path):
        return []
    rows = []
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
    return rows


def record_confirmation(payload):
    entry = {
        "ro": str(payload.get("ro", "")).strip(),
        "advisor": str(payload.get("advisor", "")).strip(),
        "step": str(payload.get("step", payload.get("bucket", ""))).strip(),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mins_taken": payload.get("mins_taken", payload.get("mins", 0)),
    }
    if not entry["ro"]:
        raise ValueError("ro is required")
    _append_jsonl(CONFIRMATION_LOG_PATH, entry)
    return entry


def load_confirmations():
    return _read_jsonl(CONFIRMATION_LOG_PATH)
