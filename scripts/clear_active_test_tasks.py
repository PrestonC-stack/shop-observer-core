import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASK_FILE = ROOT / "outputs" / "advisor_tasks.json"
DREW_FILE = ROOT / "outputs" / "tasks_drew.json"

CLEAR_ROS = {"13298", "TEST123"}

now = datetime.now(timezone.utc).isoformat()

tasks = json.loads(TASK_FILE.read_text(encoding="utf-8"))

for task in tasks:
    if str(task.get("ro")) in CLEAR_ROS:
        task["status_tracking"] = "completed"
        task["completed_at"] = task.get("completed_at") or now
        task["completed_by"] = task.get("completed_by") or "Manual cleanup"
        task["completion_source"] = "manual_cleanup"
        task["overdue"] = False

TASK_FILE.write_text(json.dumps(tasks, indent=2), encoding="utf-8")

active_drew = [
    task for task in tasks
    if task.get("owner") == "Drew" and task.get("status_tracking") != "completed"
]

DREW_FILE.write_text(json.dumps(active_drew, indent=2), encoding="utf-8")

print("Cleared active test/stale tasks.")