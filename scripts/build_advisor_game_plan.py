from __future__ import annotations

import json
from datetime import datetime, timezone
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
        return parsed
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


def main() -> None:
    rows = build_rows()

    tasks = [
        {
            "ro": r["ro"],
            "owner": r["owner"],
            "risk": r["risk"],
            "status": r["status"],
            "task": r["next_action"],
            "status_tracking": "pending",
        }
        for r in rows
        if r["risk"] in ("RED", "YELLOW")
    ]

    TASK_FILE.write_text(json.dumps(tasks, indent=2), encoding="utf-8")

    report = "# Advisor Game Plan\n\n"

    if not rows:
        report += "No RO data found.\n"

    for r in rows[:10]:
        report += (
            f"RO {r['ro']} | {r['owner']} | {r['risk']} | Idle {r['idle_hours']}h\n"
            f"Status: {r['status']}\n"
            f"→ {r['next_action']}\n\n"
        )

    OUT_MD.write_text(report, encoding="utf-8")

    print("Created:")
    print(OUT_MD)
    print(TASK_FILE)


if __name__ == "__main__":
    main()