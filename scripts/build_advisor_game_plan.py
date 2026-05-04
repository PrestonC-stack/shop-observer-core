from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVENT_LOG = ROOT / "data" / "autoflow_events" / "autoflow_events.jsonl"

OUT_MD = ROOT / "outputs" / "advisor_game_plan.md"
TASK_FILE = ROOT / "outputs" / "advisor_tasks.json"
COMPLETED_REGISTRY = ROOT / "outputs" / "completed_task_registry.json"

DREW_TASK_FILE = ROOT / "outputs" / "tasks_drew.json"
MITCH_TASK_FILE = ROOT / "outputs" / "tasks_mitch.json"
PRESTON_TASK_FILE = ROOT / "outputs" / "tasks_preston.json"

IGNORE_STATUSES = {"close", "apache job"}
NOT_HERE_STATUSES = {"scheduled-not here", "dvi only- not here"}

TECH_CONTROLLED_STATUSES = {
    "ready for tech",
    "testing",
    "dvi updates",
    "awaiting tech",
    "servicing",
    "in progress",
}

P4_EXTERNAL_STATUSES = {
    "waiting approval",
    "ordering parts",
    "waiting parts",
}


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


def normalize_status(status: str) -> str:
    return " ".join(str(status).lower().strip().split())


def task_key(ro: str, owner: str, status: str) -> str:
    return f"{ro}|{owner}|{status}"


def load_completed_registry() -> set[str]:
    if not COMPLETED_REGISTRY.exists():
        return set()
    try:
        data = json.loads(COMPLETED_REGISTRY.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return set(str(item) for item in data)
    except Exception:
        pass
    return set()


def save_completed_registry(keys: set[str]) -> None:
    COMPLETED_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    COMPLETED_REGISTRY.write_text(json.dumps(sorted(keys), indent=2), encoding="utf-8")


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


def first_value(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


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

    ro = first_value(
        ticket.get("invoice"),
        ticket.get("remote_id"),
        payload.get("invoice_or_ro"),
        payload.get("ro"),
        payload.get("invoice"),
        "unknown",
    )

    status = first_value(
        ticket.get("status"),
        payload.get("status"),
        "unknown",
    )

    timestamp = first_value(
        get_nested(payload, "event", "timestamp"),
        payload.get("timestamp"),
        record.get("received_at"),
    )

    promised_at = first_value(
        ticket.get("promised_at"),
        ticket.get("promise_time"),
        ticket.get("promisedTime"),
        payload.get("promised_at"),
        payload.get("promise_time"),
        payload.get("promisedTime"),
    )

    appointment_at = first_value(
        ticket.get("appointment_at"),
        ticket.get("appointmentTime"),
        payload.get("appointment_at"),
        payload.get("appointmentTime"),
    )

    customer_updated_at = first_value(
        ticket.get("customer_updated_at"),
        ticket.get("last_customer_update"),
        payload.get("customer_updated_at"),
        payload.get("last_customer_update"),
    )

    return {
        "ro": str(ro),
        "status": str(status),
        "customer": customer_label(payload),
        "vehicle": vehicle_label(vehicle),
        "timestamp": parse_time(timestamp),
        "promised_at": parse_time(promised_at) if promised_at else None,
        "appointment_at": parse_time(appointment_at) if appointment_at else None,
        "customer_updated_at": parse_time(customer_updated_at) if customer_updated_at else None,
    }


def is_today(dt: datetime | None, now: datetime) -> bool:
    if not dt or dt == datetime.min.replace(tzinfo=timezone.utc):
        return False
    return dt.astimezone().date() == now.astimezone().date()


def should_ignore_status(status: str) -> bool:
    s = normalize_status(status)
    return s in IGNORE_STATUSES or s == "unknown"


def owner_for(status: str) -> str:
    s = normalize_status(status)

    if should_ignore_status(status):
        return "Ignore"

    if s in NOT_HERE_STATUSES:
        return "Ignore"

    if "technical advisement" in s or "technical overview" in s:
        return "Preston"

    if (
        "online /stage" in s
        or "drop off" in s
        or "tow-in" in s
        or "ready for tech" in s
        or "awaiting tech" in s
        or "testing" in s
        or "dvi updates" in s
        or "servicing" in s
        or "in progress" in s
        or s == "qc"
        or "advisor qc review" in s
        or "advisor finalize ro" in s
    ):
        return "Drew"

    if (
        "advisor estimate" in s
        or "waiting approval" in s
        or "ordering parts" in s
        or "waiting parts" in s
        or s == "ready"
    ):
        return "Mitch"

    return "Unknown"


def risk_for(status: str, idle_hours: float, age_hours: float) -> str:
    if should_ignore_status(status):
        return "IGNORE"

    owner = owner_for(status)
    if owner in ("Ignore", "Unknown"):
        return "IGNORE"

    if idle_hours >= 4:
        return "CRITICAL"

    if idle_hours >= 2:
        return "RED"

    if idle_hours >= 1:
        return "YELLOW"

    if age_hours >= 48:
        return "RED"

    if age_hours >= 24:
        return "YELLOW"

    return "NORMAL"


def priority_for(
    status: str,
    risk: str,
    idle_hours: float,
    age_hours: float,
    promised_at: datetime | None,
    appointment_at: datetime | None,
    customer_updated_at: datetime | None,
    now: datetime,
) -> str:
    s = normalize_status(status)

    if s in IGNORE_STATUSES:
        return "P4"

    if s in NOT_HERE_STATUSES:
        return "P4"

    if risk in ("CRITICAL", "RED"):
        return "P1"

    if is_today(appointment_at, now):
        return "P1"

    if promised_at:
        hours_to_promise = (promised_at - now).total_seconds() / 3600
        if hours_to_promise <= 24:
            return "P1"

    if s == "ready":
        return "P1"

    if s in P4_EXTERNAL_STATUSES:
        return "P4"

    if s in TECH_CONTROLLED_STATUSES:
        if customer_updated_at:
            return "P3"
        return "P2"

    if "advisor estimate" in s:
        return "P2"

    if "technical advisement" in s or "technical overview" in s:
        return "P2"

    if "advisor qc review" in s or "advisor finalize ro" in s or s == "qc":
        return "P2"

    if age_hours >= 24:
        return "P2"

    return "P3"


def action_for(owner: str, status: str) -> str:
    s = normalize_status(status)

    if owner == "Drew":
        if "online /stage" in s or "drop off" in s or "tow-in" in s:
            return "Vehicle intake/staging. Take starting photos, verify vehicle/key/tag, and prep for tech handoff."
        if "ready for tech" in s or "awaiting tech" in s:
            return "Dispatch control. Assign tech, confirm bay readiness, and remove blockers."
        if "testing" in s:
            return "Testing verification. Confirm test result, blocker/no blocker, and next action."
        if "dvi updates" in s:
            return "Review DVI/photos and prepare advisor-ready findings."
        if "servicing" in s or "in progress" in s:
            return "Production check. Confirm tech progress, blockers, parts, and next completion estimate."
        if s == "qc":
            return "QC verification. Confirm repair complete and ready for advisor QC."
        if "advisor qc review" in s:
            return "Advisor QC review. Confirm notes, photos, repair story, and ready-to-close status."
        if "advisor finalize ro" in s:
            return "Finalize RO. Clean notes, confirm charges, and prep invoice for customer closeout."
        return "Shop-side check. Verify actual bay status and next action."

    if owner == "Mitch":
        if "advisor estimate" in s:
            return "Final estimate/customer strategy. Review, prepare, and sell the estimate."
        if "waiting approval" in s:
            return "Customer approval follow-up. Contact customer, document response, and set next move."
        if "ordering parts" in s:
            return "Parts ordering. Confirm source, ETA, and job timeline."
        if "waiting parts" in s:
            return "Parts ETA tracking. Confirm ETA and update customer/job timeline."
        if s == "ready":
            return "Customer closeout. Confirm pickup, payment, final communication, and delivery."
        return "Customer/ticket action. Confirm estimate, approval, parts, update, payment, or closeout."

    if owner == "Preston":
        return "Technical escalation. Review and give direction."

    return f"Assign owner immediately. Current status could not be mapped: {status}"


def due_minutes_for(priority: str, risk: str) -> int:
    if priority == "P1" or risk == "CRITICAL":
        return 30
    if priority == "P2" or risk == "RED":
        return 60
    if priority == "P3" or risk == "YELLOW":
        return 240
    return 480


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

        priority = priority_for(
            latest["status"],
            risk,
            idle_hours,
            age_hours,
            latest.get("promised_at"),
            latest.get("appointment_at"),
            latest.get("customer_updated_at"),
            now,
        )

        rows.append({
            "ro": ro,
            "customer": latest["customer"],
            "vehicle": latest["vehicle"],
            "status": latest["status"],
            "owner": owner,
            "risk": risk,
            "priority": priority,
            "age_hours": round(age_hours, 1),
            "idle_hours": round(idle_hours, 1),
            "next_action": action_for(owner, latest["status"]),
        })

    priority_order = {"P1": 0, "P2": 1, "P3": 2, "P4": 3}
    risk_order = {"CRITICAL": 0, "RED": 1, "YELLOW": 2, "NORMAL": 3, "IGNORE": 9}

    rows.sort(
        key=lambda r: (
            priority_order.get(r["priority"], 9),
            risk_order.get(r["risk"], 9),
            -r["idle_hours"],
        )
    )

    return rows


def load_existing_tasks() -> dict[str, dict[str, Any]]:
    if not TASK_FILE.exists():
        return {}

    try:
        raw = json.loads(TASK_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

    existing = {}
    completed = load_completed_registry()

    for task in raw:
        if not isinstance(task, dict):
            continue

        key = task_key(
            str(task.get("ro")),
            str(task.get("owner")),
            str(task.get("status")),
        )

        if task.get("status_tracking") == "completed":
            completed.add(key)

        existing[key] = task

    save_completed_registry(completed)
    return existing


def build_tasks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    existing = load_existing_tasks()
    completed = load_completed_registry()
    tasks = []

    for row in rows:
        if row["owner"] in ("Ignore", "Unknown"):
            continue

        if row["priority"] == "P4" and row["risk"] in ("NORMAL", "IGNORE"):
            continue

        if row["risk"] not in ("CRITICAL", "RED", "YELLOW") and row["priority"] not in ("P1", "P2"):
            continue

        key = task_key(row["ro"], row["owner"], row["status"])

        if key in completed:
            continue

        old = existing.get(key, {})

        if old.get("status_tracking") == "completed":
            completed.add(key)
            save_completed_registry(completed)
            continue

        created_at = old.get("created_at") or now.isoformat()

        if old.get("due_by"):
            due_by = old["due_by"]
        else:
            due_by = (
                parse_time(created_at)
                + timedelta(minutes=due_minutes_for(row["priority"], row["risk"]))
            ).isoformat()

        due_by_dt = parse_time(due_by)
        overdue = now > due_by_dt

        tasks.append({
            "ro": row["ro"],
            "customer": row["customer"],
            "vehicle": row["vehicle"],
            "owner": row["owner"],
            "risk": row["risk"],
            "priority": row["priority"],
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

    report += "## Priority Summary\n\n"
    for priority in ["P1", "P2", "P3", "P4"]:
        count = sum(1 for row in rows if row["priority"] == priority)
        report += f"- {priority}: {count} jobs\n"

    report += "\n## Current Priorities\n\n"

    active_task_keys = {
        task_key(str(task["ro"]), str(task["owner"]), str(task["status"]))
        for task in tasks
        if task.get("status_tracking") != "completed"
    }

    active_count = 0

    for row in rows[:30]:
        key = task_key(row["ro"], row["owner"], row["status"])
        if key not in active_task_keys:
            continue

        active_count += 1
        report += (
            f"RO {row['ro']} | {row['priority']} | {row['owner']} | {row['risk']} | Idle {row['idle_hours']}h\n"
            f"Customer: {row.get('customer', 'unknown')}\n"
            f"Vehicle: {row.get('vehicle', 'unknown')}\n"
            f"Status: {row['status']}\n"
            f"Action: {row['next_action']}\n\n"
        )

    if active_count == 0:
        report += "No active pending priorities.\n\n"

    report += "## Rolling Job Board\n\n"
    for row in rows[:60]:
        report += (
            f"- {row['priority']} | RO {row['ro']} | {row['status']} | Waiting on: {row['owner']} | "
            f"Risk: {row['risk']} | Idle: {row['idle_hours']}h | {row['vehicle']}\n"
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