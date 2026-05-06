import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASK_FILE = ROOT / "outputs" / "advisor_tasks.json"
DREW_FILE = ROOT / "outputs" / "tasks_drew.json"

now = datetime.now(timezone.utc)

task = {
    "ro": "TEST-DREW",
    "customer": "Test Customer",
    "vehicle": "Test Vehicle",
    "owner": "Drew",
    "risk": "RED",
    "status": "In Progress",
    "task": "TEST TASK - verify COMPLETE button removes this task.",
    "created_at": now.isoformat(),
    "due_by": (now + timedelta(minutes=30)).isoformat(),
    "status_tracking": "pending",
    "completed_at": None,
    "overdue": False,
    "checked_at": now.isoformat(),
}

TASK_FILE.parent.mkdir(parents=True, exist_ok=True)

tasks = []
if TASK_FILE.exists():
    try:
        tasks = json.loads(TASK_FILE.read_text(encoding="utf-8"))
    except Exception:
        tasks = []

tasks = [t for t in tasks if t.get("ro") != "TEST-DREW"]
tasks.append(task)

TASK_FILE.write_text(json.dumps(tasks, indent=2), encoding="utf-8")
DREW_FILE.write_text(json.dumps([task], indent=2), encoding="utf-8")

print("Created TEST-DREW task.")
print("Open: https://tasks.callahanautoaz.net/drew")