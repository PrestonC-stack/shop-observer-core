from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVENT_LOG = ROOT / "data" / "autoflow_events" / "autoflow_events.jsonl"

OUT_MD = ROOT / "outputs" / "advisor_game_plan.md"
TASK_FILE = ROOT / "outputs" / "advisor_tasks.json"

DREW_TASK_FILE = ROOT / "outputs" / "tasks_drew.json"
MITCH_TASK_FILE = ROOT / "outputs" / "tasks_mitch.json"
PRESTON_TASK_FILE = ROOT / "outputs" / "tasks_preston.json"

IGNORE_STATUS_KEYWORDS = [
    "closed",
    "paid",
    "posted",
    "void",
    "cancelled",
    "canceled",
    "warranty close",
    "company vehicle",
]

NO_TASK_STATUSES = [
    "scheduled-not here",
    "not started-not here",
    "online action",
    "online /stage",
    "dvi only- not here",
    "drop off/ tow-in",
]


def parse_time(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def clean(value: Any, default: str = "unknown") -> str:
    if value in (None, "", [], {}):
        return default
    return str(value)


def load_events() -> list[dict[str, Any]]:
    if not EVENT_LOG.exists():
        return []

    rows = []
    for line in EVENT_LOG.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                rows.append(item)
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


def vehicle_label(vehicle: dict[str, Any]) -> str:
    parts = [
        clean(vehicle.get("year"), ""),
        clean(vehicle.get("make"), ""),
        clean(vehicle.get("model"), ""),
    ]
    label = " ".join(part for part in parts if part).strip()
    return label or "unknown"


def customer_label(payload: dict[str, Any]) -> str:
    customer = payload.get("customer", {})
    if not isinstance(customer, dict):
        customer = {}

    return (
        clean(customer.get("name"), "")
        or clean(customer.get("full_name"), "")
        or clean(customer.get("display_name"), "")
        or clean(get_nested(payload, "ticket", "customer_name"), "")
        or clean(payload.get("customer_name"), "")
        or "unknown"
    )


def extract_event(record: dict[str, Any]) -> dict[str, Any]:
    payload = record.get("payload", record)
    if not isinstance(payload, dict):
        payload = {}

    ticket = payload.get("ticket", {})
    if not isinstance(ticket, dict):
        ticket = {}

    vehicle = payload.get("vehicle", {})
    if not isinstance(vehicle, dict):
        vehicle = {}

    ro = (
        ticket.get("invoice")
        or ticket.get("remote_id")
        or payload.get("invoice_or_ro")
        or payload.get("ro")
        or payload.get("invoice")
        or "unknown"
    )

    status = ticket.get("status") or payload.get("status") or "unknown"

    timestamp = (
        get_nested(payload, "event", "timestamp")
        or payload.get("timestamp")
        or record.get("received_at")
    )

    return {
        "ro": str(ro),
        "status": str(status),
        "customer": customer_label(payload),
        "vehicle": vehicle_label(vehicle),
        "timestamp": parse_time(timestamp),
    }


def should_ignore_status(status: str) -> bool:
    s = status.lower().strip()

    if not s or s == "unknown":
        return True

    if any(word in s for word in IGNORE_STATUS_KEYWORDS):
        return True

    if s in NO_TASK_STATUSES:
        return True

    if (
        "scheduled" in s
        or "not here" in s
        or "drop off" in s
        or "tow-in" in s
    ):
        return True

    return False


def owner_for(status: str) -> str:
    s = status.lower()

    if should_ignore_status(status):
        return "Ignore"

    if "technical review" in s or "technical advisement" in s:
        return "Preston"

    if (
        "in progress" in s
        or "servicing" in s
        or "testing" in s
        or "dvi" in s
        or "qc" in s
        or "ready for tech" in s
        or "awaiting tech" in s
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
        or "advisor final" in s
        or s == "ready"
    ):
        return "Mitch"

    return "Unknown"


def risk_for(status: str, idle_hours: float, age_hours: float) -> str:
    s = status.lower()

    if should_ignore_status(status):
        return "IGNORE"

    if owner_for(status) == "Unknown":
        return "IGNORE"

    if "technical review" in s or "technical advisement" in s:
        return "RED"

    if "in progress" in s or "servicing" in s:
        if idle_hours >= 2:
            return "RED"
        if idle_hours >= 1:
            return "YELLOW"
        return "NORMAL"

    if "ready for tech" in s or "awaiting tech" in s:
        if idle_hours >= 8:
            return "RED"
        if idle_hours >= 4:
            return "YELLOW"
        return "NORMAL"

    if "advisor estimate" in s or "building estimate" in s:
        if idle_hours >= 4:
            return "RED"
        if idle_hours >= 2:
            return "YELLOW"
        return "NORMAL"

    if "waiting approval" in s or "requires auth" in s or "pending auth" in s:
        if idle_hours >= 4:
            return "RED"
        if idle_hours >= 2:
            return "YELLOW"
        return "NORMAL"

    if "ordering parts" in s or "waiting parts" in s:
        if age_hours >= 48:
            return "RED"
        if age_hours >= 24:
            return "YELLOW"
        return "NORMAL"

    if "customer notified" in s or "waiting for customer" in s:
        if idle_hours >= 24:
            return "RED"
        if idle_hours >= 8:
            return "YELLOW"
        return "NORMAL"

    if "ready" in s or "payment" in s or "collection" in s:
        if idle_hours >= 24:
            return "RED"
        if idle_hours >= 8:
            return "YELLOW"
        return "NORMAL"

    if idle_hours >= 24:
        return "RED"

    if idle_hours >= 4:
        return "YELLOW"

    return "NORMAL"


def action_for(owner: str, status: str) -> str:
    s = status.lower()

    if owner == "Drew":
        if "in progress" in s or "servicing" in s:
            return "Bay-lap progress check. Confirm tech activity, clock-in, parts, blockers, and next action."
        if "ready for tech" in s or "awaiting tech" in s:
            return "Dispatch control. Confirm tech assignment, bay availability, parts readiness, and next job sequence."
        if "dvi" in s:
            return "Review DVI. Verify notes/photos are complete and prepare advisor-ready findings."
        if "testing" in s:
            return "Testing verification. Confirm test result, blocker/no blocker, and whether customer update is needed."
        if "qc" in s:
            return "QC verification. Confirm repair completion, notes, photos, and final readiness."
        return "Shop-side check. Verify actual bay status and next action."

    if owner == "Mitch":
        if "estimate" in s:
            return "Build/sell estimate or document blocker."
        if "approval" in s or "auth" in s:
            return "Push customer approval. Contact customer, document response, and set next follow-up."
        if "parts" in s:
            return "Parts control. Confirm order/source/ETA and update timeline."
        if "customer" in s:
            return "Customer follow-up. Contact customer and document next decision."
        if "payment" in s or "collection" in s or "ready" in s:
            return "Customer closeout. Confirm pickup/payment/final communication and clear RO."
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
        first = events[0]
        latest = events[-1]

        age_hours = max(0, (now - first["timestamp"]).total_seconds() / 3600)
        idle_hours = max(0, (now - latest["timestamp"]).total_seconds() / 3600)

        owner = owner_for(latest["status"])
        risk = risk_for(latest["status"], idle_hours, age_hours)

        rows.append({
            "ro": ro,
            "customer": latest["customer"],
            "vehicle": latest["vehicle"],
            "status": latest["status"],
            "owner": owner,
            "risk": risk,
            "age_hours": round(age_hours, 1),
            "idle_hours": round(idle_hours, 1),
            "next_action": action_for(owner, latest["status"]),
        })

    order = {"RED": 0, "YELLOW": 1, "NORMAL": 2, "IGNORE": 9}
    rows.sort(key=lambda r: (order.get(r["risk"], 8), -r["idle_hours"]))

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

    for row in rows:
        if row["risk"] not in ("RED", "YELLOW"):
            continue

        if row["owner"] in ("Ignore", "Unknown"):
            continue

        key = f"{row['ro']}|{row['owner']}|{row['next_action']}"
        old = existing.get(key, {})

        if old.get("status_tracking") == "completed":
            tasks.append(old)
            continue

        created_at = old.get("created_at") or now.isoformat()

        if old.get("due_by"):
            due_by = old["due_by"]
        else:
            due_by = (
                parse_time(created_at)
                + timedelta(minutes=due_minutes_for(row["risk"]))
            ).isoformat()

        due_by_dt = parse_time(due_by)
        overdue = now > due_by_dt

        tasks.append({
            "ro": row["ro"],
            "customer": row["customer"],
            "vehicle": row["vehicle"],
            "owner": row["owner"],
            "risk": row["risk"],
            "status": row["status"],
            "task": row["next_action"],
            "created_at": created_at,
            "due_by": due_by,
            "status_tracking": "pending",
            "completed_at": None,
            "overdue": overdue,
            "checked_at": now.isoformat(),
        })

    return tasks


def split_tasks_by_owner(tasks: list[dict[str, Any]]) -> None:
    feeds = {"Drew": [], "Mitch": [], "Preston": []}

    for task in tasks:
        if task.get("status_tracking") == "completed":
            continue

        owner = task.get("owner")
        if owner in feeds:
            feeds[owner].append(task)

    for path, owner in [
        (DREW_TASK_FILE, "Drew"),
        (MITCH_TASK_FILE, "Mitch"),
        (PRESTON_TASK_FILE, "Preston"),
    ]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(feeds[owner], indent=2), encoding="utf-8")


def build_report(rows: list[dict[str, Any]], tasks: list[dict[str, Any]]) -> str:
    report = "# Advisor Game Plan\n\n"

    overdue_tasks = [task for task in tasks if task.get("overdue") is True]
    active_task_keys = {
        f"{task['ro']}|{task['owner']}|{task['task']}"
        for task in tasks
        if task.get("status_tracking") != "completed"
    }
    completed_tasks = [
        task for task in tasks
        if task.get("status_tracking") == "completed"
    ]

    if overdue_tasks:
        report += "## MISSED / OVERDUE ACTIONS\n\n"
        for task in overdue_tasks:
            report += (
                f"- RO {task['ro']} | {task['owner']} | {task['risk']}\n"
                f"  - Customer: {task.get('customer', 'unknown')}\n"
                f"  - Vehicle: {task.get('vehicle', 'unknown')}\n"
                f"  - Status: {task['status']}\n"
                f"  - Task: {task['task']}\n"
                f"  - Due By: {task['due_by']}\n"
                f"  - Checked At: {task['checked_at']}\n\n"
            )

    report += "## Current Priorities\n\n"
    active_count = 0

    for row in rows[:15]:
        key = f"{row['ro']}|{row['owner']}|{row['next_action']}"
        if key not in active_task_keys:
            continue

        active_count += 1
        report += (
            f"RO {row['ro']} | {row['owner']} | {row['risk']} | Idle {row['idle_hours']}h\n"
            f"Customer: {row.get('customer', 'unknown')}\n"
            f"Vehicle: {row.get('vehicle', 'unknown')}\n"
            f"Status: {row['status']}\n"
            f"→ {row['next_action']}\n\n"
        )

    if active_count == 0:
        report += "No active pending priorities.\n\n"

    if completed_tasks:
        report += "## Completed Tasks\n\n"
        for task in completed_tasks:
            report += (
                f"- RO {task['ro']} | {task['owner']}\n"
                f"  - Customer: {task.get('customer', 'unknown')}\n"
                f"  - Vehicle: {task.get('vehicle', 'unknown')}\n"
                f"  - Task: {task['task']}\n"
                f"  - Completed At: {task.get('completed_at')}\n\n"
            )

    return report


def main() -> None:
    rows = build_rows()
    tasks = build_tasks(rows)

    TASK_FILE.parent.mkdir(parents=True, exist_ok=True)
    TASK_FILE.write_text(json.dumps(tasks, indent=2), encoding="utf-8")

    split_tasks_by_owner(tasks)

    report = build_report(rows, tasks)
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(report, encoding="utf-8")

    print("Created:")
    print(OUT_MD)
    print(TASK_FILE)
    print(DREW_TASK_FILE)
    print(MITCH_TASK_FILE)
    print(PRESTON_TASK_FILE)


if __name__ == "__main__":
    main()