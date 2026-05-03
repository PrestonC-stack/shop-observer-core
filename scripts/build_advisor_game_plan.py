from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVENT_LOG = ROOT / "data" / "autoflow_events" / "autoflow_events.jsonl"

OUT_MD = ROOT / "outputs" / "advisor_game_plan.md"
TASK_FILE = ROOT / "outputs" / "advisor_tasks.json"


def parse_time(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def load_events() -> list[dict[str, Any]]:
    if not EVENT_LOG.exists():
        return []

    rows = []
    for line in EVENT_LOG.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def get_nested(d: dict[str, Any], *keys: str) -> Any:
    cur = d
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def extract_event(record: dict[str, Any]) -> dict[str, Any]:
    payload = record.get("payload", record)

    ro = (
        get_nested(payload, "ticket", "invoice")
        or get_nested(payload, "ticket", "remote_id")
        or payload.get("invoice_or_ro")
        or payload.get("ro")
        or payload.get("invoice")
        or "unknown"
    )

    status = (
        get_nested(payload, "ticket", "status")
        or payload.get("status")
        or "unknown"
    )

    timestamp = (
        get_nested(payload, "event", "timestamp")
        or payload.get("timestamp")
        or record.get("received_at")
    )

    return {
        "ro": str(ro),
        "status": str(status),
        "timestamp": parse_time(timestamp),
    }


def owner_for(status: str) -> str:
    s = status.lower()

    if "technical review" in s or "technical advisement" in s:
        return "Preston"

    if (
        "in progress" in s
        or "servicing" in s
        or "testing" in s
        or "dvi" in s
        or "ready for tech" in s
        or "awaiting tech" in s
        or "qc" in s
    ):
        return "Drew"

    if (
        "estimate" in s
        or "approval" in s
        or "auth" in s
        or "parts" in s
        or "customer" in s
        or "payment" in s
        or "collection" in s
        or s == "ready"
    ):
        return "Mitch"

    return "Unknown"


def risk_for(status: str, idle_hours: float) -> str:
    s = status.lower()

    if owner_for(status) == "Unknown":
        return "RED"

    if "in progress" in s or "servicing" in s:
        if idle_hours >= 2:
            return "RED"
        if idle_hours >= 1:
            return "YELLOW"

    if idle_hours >= 24:
        return "RED"

    if idle_hours >= 4:
        return "YELLOW"

    return "NORMAL"


def action_for(owner: str, status: str) -> str:
    if owner == "Drew":
        return "Bay-lap progress check. Confirm tech activity, clock-in, parts, blockers, and next action."

    if owner == "Mitch":
        return "Customer/ticket action. Confirm estimate, approval, parts, update, payment, or closeout."

    if owner == "Preston":
        return "Technical escalation. Review and give direction."

    return f"Assign owner immediately. Current status could not be mapped: {status}"


def due_minutes_for(risk: str) -> int:
    if risk == "RED":
        return 30

    if risk == "YELLOW":
        return 120

    return 240


def build_rows() -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    grouped: dict[str, list[dict[str, Any]]] = {}

    for record in load_events():
        event = extract_event(record)

        if event["ro"] == "unknown":
            continue

        grouped.setdefault(event["ro"], []).append(event)

    rows = []

    for ro, events in grouped.items():
        events.sort(key=lambda x: x["timestamp"])
        latest = events[-1]

        idle_hours = max(0, (now - latest["timestamp"]).total_seconds() / 3600)
        owner = owner_for(latest["status"])
        risk = risk_for(latest["status"], idle_hours)

        rows.append({
            "ro": ro,
            "status": latest["status"],
            "owner": owner,
            "risk": risk,
            "idle_hours": round(idle_hours, 1),
            "next_action": action_for(owner, latest["status"]),
        })

    order = {"RED": 0, "YELLOW": 1, "NORMAL": 2}
    rows.sort(key=lambda r: (order.get(r["risk"], 9), -r["idle_hours"]))

    return rows


def load_existing_tasks() -> dict[str, dict[str, Any]]:
    if not TASK_FILE.exists():
        return {}

    try:
        raw = json.loads(TASK_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

    existing = {}

    for task in raw:
        if not isinstance(task, dict):
            continue

        key = f"{task.get('ro')}|{task.get('owner')}|{task.get('task')}"
        existing[key] = task

    return existing


def build_tasks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    existing = load_existing_tasks()
    tasks = []

    for r in rows:
        if r["risk"] not in ("RED", "YELLOW"):
            continue

        key = f"{r['ro']}|{r['owner']}|{r['next_action']}"
        old = existing.get(key, {})

        created_at = old.get("created_at") or now.isoformat()

        if old.get("due_by"):
            due_by = old["due_by"]
        else:
            due_by = (
                parse_time(created_at)
                + timedelta(minutes=due_minutes_for(r["risk"]))
            ).isoformat()

        due_by_dt = parse_time(due_by)

        status_tracking = old.get("status_tracking", "pending")

        completed_at = old.get("completed_at")
        if status_tracking == "completed" and not completed_at:
            completed_at = now.isoformat()

        overdue = status_tracking == "pending" and now > due_by_dt

        tasks.append({
            "ro": r["ro"],
            "owner": r["owner"],
            "risk": r["risk"],
            "status": r["status"],
            "task": r["next_action"],
            "created_at": created_at,
            "due_by": due_by,
            "status_tracking": status_tracking,
            "completed_at": completed_at,
            "overdue": overdue,
            "checked_at": now.isoformat(),
        })

    return tasks


def build_report(rows: list[dict[str, Any]], tasks: list[dict[str, Any]]) -> str:
    report = "# Advisor Game Plan\n\n"

    overdue_tasks = [
        task for task in tasks
        if task.get("overdue") is True
    ]

    completed_tasks = [
        task for task in tasks
        if task.get("status_tracking") == "completed"
    ]

    if overdue_tasks:
        report += "## MISSED / OVERDUE ACTIONS\n\n"

        for task in overdue_tasks:
            report += (
                f"- RO {task['ro']} | {task['owner']} | {task['risk']}\n"
                f"  - Status: {task['status']}\n"
                f"  - Task: {task['task']}\n"
                f"  - Due By: {task['due_by']}\n"
                f"  - Checked At: {task['checked_at']}\n\n"
            )

    report += "## Current Priorities\n\n"

    if not rows:
        report += "No RO data found.\n"

    for row in rows[:10]:
        report += (
            f"RO {row['ro']} | {row['owner']} | {row['risk']} | Idle {row['idle_hours']}h\n"
            f"Status: {row['status']}\n"
            f"→ {row['next_action']}\n\n"
        )

    if completed_tasks:
        report += "## Completed Tasks\n\n"

        for task in completed_tasks:
            report += (
                f"- RO {task['ro']} | {task['owner']}\n"
                f"  - Task: {task['task']}\n"
                f"  - Completed At: {task.get('completed_at')}\n\n"
            )

    return report


def main() -> None:
    rows = build_rows()
    tasks = build_tasks(rows)

    TASK_FILE.parent.mkdir(parents=True, exist_ok=True)
    TASK_FILE.write_text(json.dumps(tasks, indent=2), encoding="utf-8")

    report = build_report(rows, tasks)
    OUT_MD.write_text(report, encoding="utf-8")

    print("Created:")
    print(OUT_MD)
    print(TASK_FILE)


if __name__ == "__main__":
    main()