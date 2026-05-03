from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EVENT_LOG = ROOT / "data" / "autoflow_events" / "autoflow_events.jsonl"
OUT_MD = ROOT / "outputs" / "advisor_game_plan.md"
OUT_JSON = ROOT / "outputs" / "accountability_scoreboard.json"

OWNER_RULES = {
    "technical review": "Preston",
    "technical advisement": "Preston",

    "in progress": "Drew",
    "servicing": "Drew",
    "testing": "Drew",
    "dvi updates": "Drew",
    "ready for tech": "Drew",
    "awaiting tech": "Drew",
    "advisor qc": "Drew",
    "qc": "Drew",

    "advisor estimate": "Mitch",
    "building estimate": "Mitch",
    "waiting approval": "Mitch",
    "requires auth": "Mitch",
    "pending auth": "Mitch",
    "ordering parts": "Mitch",
    "waiting parts": "Mitch",
    "customer notified": "Mitch",
    "waiting for customer": "Mitch",
    "payment collected": "Mitch",
    "collection issues": "Mitch",
    "advisor final": "Mitch",
    "ready": "Mitch",
}


def parse_time(value: Any) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
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
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                rows.append(item)
        except Exception:
            continue
    return rows


def get_payload(record: dict[str, Any]) -> dict[str, Any]:
    payload = record.get("payload", record)
    return payload if isinstance(payload, dict) else {}


def clean(value: Any, default: str = "unknown") -> str:
    if value in (None, "", [], {}):
        return default
    return str(value)


def owner_for(status: str) -> str:
    s = status.lower()
    for key, owner in OWNER_RULES.items():
        if key in s:
            return owner
    return "Unknown"


def action_for(owner: str, status: str) -> str:
    s = status.lower()

    if owner == "Preston":
        return (
            "Technical escalation. Preston needs to review the issue, give diagnostic direction, "
            "and unblock the tech/advisor chain."
        )

    if owner == "Drew":
        if "in progress" in s or "servicing" in s:
            return (
                "Bay-lap progress check due. Confirm tech is actively working, clocked in correctly, "
                "has correct parts, has no technical hangup, and is still on pace."
            )
        if "dvi" in s:
            return (
                "Review DVI through AI, verify photos/notes are complete, identify missing info, "
                "and prepare clean findings for Mitch to build/sell."
            )
        if "ready for tech" in s or "awaiting tech" in s:
            return (
                "Dispatch control. Verify tech assignment, bay availability, parts readiness, "
                "and the next two jobs in sequence."
            )
        if "testing" in s:
            return (
                "Testing verification. Confirm what is being tested, expected result, failure result, "
                "and when Mitch/customer should be updated."
            )
        if "qc" in s:
            return (
                "QC verification. Confirm repair completion, photos, notes, test drive/result, "
                "and whether Mitch can finalize customer closeout."
            )
        return (
            "Drew needs to verify shop-side status, identify blocker/no blocker, "
            "and update the next action."
        )

    if owner == "Mitch":
        if "estimate" in s:
            return (
                "Build/sell estimate. Confirm AI/DVI info is complete, structure the ticket, "
                "present to customer, and document approval/blocker."
            )
        if "approval" in s or "auth" in s:
            return (
                "Customer approval push. Contact customer, explain priority clearly, "
                "document yes/no/waiting, and set next follow-up."
            )
        if "ordering parts" in s:
            return (
                "Parts ordering control. Order parts, enter source/ETA in AutoFlow, "
                "and confirm whether tech can keep working or needs a new job."
            )
        if "waiting parts" in s or "parts" in s:
            return (
                "Parts follow-up. Confirm ETA/source, identify missing/late parts, "
                "update AutoFlow, and notify customer if timeline changed."
            )
        if "ready" in s or "customer notified" in s or "payment" in s or "collection" in s:
            return (
                "Customer closeout. Confirm pickup/payment/final communication, "
                "clear the RO, and prevent vehicle from sitting finished."
            )
        if "waiting for customer" in s:
            return (
                "Customer follow-up required. Call/text customer, document response, "
                "and set next decision point."
            )
        return (
            "Mitch needs to handle the customer-facing or ticket-building action "
            "and document the next step."
        )

    return "Assign owner and define the next action immediately."


def risk_level(status: str, idle_hours: float, age_hours: float) -> str:
    s = status.lower()

    if "technical review" in s or "technical advisement" in s:
        return "RED"

    if "in progress" in s or "servicing" in s:
        if idle_hours >= 2:
            return "RED"
        if idle_hours >= 1:
            return "YELLOW"

    if "advisor estimate" in s or "building estimate" in s:
        if idle_hours >= 4:
            return "RED"
        if idle_hours >= 2:
            return "YELLOW"

    if "waiting approval" in s or "requires auth" in s or "pending auth" in s:
        if idle_hours >= 4:
            return "RED"
        if idle_hours >= 2:
            return "YELLOW"

    if "waiting parts" in s or "ordering parts" in s:
        if age_hours >= 48:
            return "RED"
        if age_hours >= 24:
            return "YELLOW"

    if "ready for tech" in s or "awaiting tech" in s:
        if idle_hours >= 8:
            return "RED"
        if idle_hours >= 4:
            return "YELLOW"

    if "ready" in s or "customer notified" in s or "payment" in s or "collection" in s:
        if idle_hours >= 24:
            return "RED"
        if idle_hours >= 8:
            return "YELLOW"

    if idle_hours >= 24:
        return "RED"
    if idle_hours >= 4:
        return "YELLOW"

    return "NORMAL"


def build_rows() -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    grouped = defaultdict(list)

    for record in load_events():
        payload = get_payload(record)
        ticket = payload.get("ticket", {}) if isinstance(payload.get("ticket"), dict) else {}
        vehicle = payload.get("vehicle", {}) if isinstance(payload.get("vehicle"), dict) else {}
        event = payload.get("event", {}) if isinstance(payload.get("event"), dict) else {}

        ro = clean(ticket.get("invoice") or ticket.get("remote_id"))
        if ro == "unknown":
            continue

        ts = parse_time(
            payload.get("timestamp")
            or event.get("timestamp")
            or record.get("received_at")
        )

        grouped[ro].append(
            {
                "ro": ro,
                "status": clean(ticket.get("status")),
                "event_type": clean(event.get("type")),
                "vehicle": " ".join(
                    x
                    for x in [
                        clean(vehicle.get("year"), ""),
                        clean(vehicle.get("make"), ""),
                        clean(vehicle.get("model"), ""),
                    ]
                    if x
                )
                or "unknown",
                "timestamp": ts,
            }
        )

    rows = []

    for ro, events in grouped.items():
        events.sort(key=lambda x: x["timestamp"])
        first = events[0]
        latest = events[-1]

        age_hours = max(0, (now - first["timestamp"]).total_seconds() / 3600)
        idle_hours = max(0, (now - latest["timestamp"]).total_seconds() / 3600)

        owner = owner_for(latest["status"])
        risk = risk_level(latest["status"], idle_hours, age_hours)

        rows.append(
            {
                "ro": ro,
                "vehicle": latest["vehicle"],
                "status": latest["status"],
                "event_type": latest["event_type"],
                "owner": owner,
                "risk": risk,
                "age_hours": round(age_hours, 1),
                "idle_hours": round(idle_hours, 1),
                "event_count": len(events),
                "last_update": latest["timestamp"].isoformat(),
                "next_action": action_for(owner, latest["status"]),
            }
        )

    risk_order = {"RED": 0, "YELLOW": 1, "NORMAL": 2}
    rows.sort(key=lambda r: (risk_order.get(r["risk"], 9), -r["idle_hours"]))
    return rows


def section(title: str, rows: list[dict[str, Any]]) -> str:
    if not rows:
        return f"\n## {title}\n\nNone.\n"

    lines = [f"\n## {title}\n"]
    for i, r in enumerate(rows, 1):
        lines.append(
            f"{i}. **RO #{r['ro']}** — {r['vehicle']}\n"
            f"   - Status: {r['status']}\n"
            f"   - Owner: {r['owner']}\n"
            f"   - Risk: {r['risk']}\n"
            f"   - Idle: {r['idle_hours']} hrs | Age: {r['age_hours']} hrs\n"
            f"   - Event Count: {r['event_count']}\n"
            f"   - Last Update: {r['last_update']}\n"
            f"   - Next Action: {r['next_action']}\n"
        )
    return "\n".join(lines)


def main() -> None:
    rows = build_rows()
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)

    by_owner = defaultdict(list)
    for r in rows:
        by_owner[r["owner"]].append(r)

    counts = Counter(r["owner"] for r in rows)
    risk_counts = Counter(r["risk"] for r in rows)

    scoreboard = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_ros": len(rows),
        "waiting_on": dict(counts),
        "risk_counts": dict(risk_counts),
        "rows": rows,
    }

    OUT_JSON.write_text(json.dumps(scoreboard, indent=2), encoding="utf-8")

    report = f"""# Callahan Auto & Diesel — Advisor Game Plan

Generated: {scoreboard['generated_at']}

## Bottleneck Counts

- Waiting on Drew: {counts.get('Drew', 0)}
- Waiting on Mitch: {counts.get('Mitch', 0)}
- Waiting on Preston: {counts.get('Preston', 0)}
- Unknown / No Owner: {counts.get('Unknown', 0)}

## Risk Counts

- RED: {risk_counts.get('RED', 0)}
- YELLOW: {risk_counts.get('YELLOW', 0)}
- NORMAL: {risk_counts.get('NORMAL', 0)}

## Top Priorities

    # START HERE SECTION
    top_actions = rows[:5]

    start_here = "\n## START HERE\n\n"
    if not top_actions:
        start_here += "No immediate actions.\n"
    else:
        for i, r in enumerate(top_actions, 1):
            start_here += (
                f"{i}. {r['owner']} → GO CHECK RO #{r['ro']}\n"
                f"   Reason: {r['status']} | Idle {r['idle_hours']} hrs | Risk {r['risk']}\n"
                f"   Required:\n"
                f"   - Confirm tech is working\n"
                f"   - Confirm clock-in is correct\n"
                f"   - Verify parts status\n"
                f"   - Identify any blocker\n"
                f"   - Decide next action immediately\n\n"
            )

    report += start_here

Sorted by risk first, then longest idle time.

"""

    report += section("RED — Needs Immediate Attention", [r for r in rows if r["risk"] == "RED"])
    report += section("YELLOW — Needs Follow-Up", [r for r in rows if r["risk"] == "YELLOW"])
    report += section("NORMAL — Currently Moving", [r for r in rows if r["risk"] == "NORMAL"])
    report += section("Waiting on Drew", by_owner["Drew"])
    report += section("Waiting on Mitch", by_owner["Mitch"])
    report += section("Waiting on Preston", by_owner["Preston"])
    report += section("Unknown / Needs Assignment", by_owner["Unknown"])

    report += """

## Drew Bay-Lap Checklist

Use this when walking the bays:

- Is the vehicle physically in the expected bay?
- Is the tech actively working on it?
- Is the tech clocked in on the correct job?
- Are the correct parts present?
- Are any parts missing or wrong?
- Is there a technical hangup?
- Is the job still on pace?
- Are mid-job photos needed?
- Does Mitch need a customer update, approval, or parts action?

## Mitch Customer / Ticket Checklist

- Is the estimate built?
- Has the customer been contacted?
- Are approvals documented?
- Are parts ordered with ETA/source?
- Is AutoFlow status accurate?
- Does the customer need an update before end of day?
- Is the RO ready for pickup, payment, or final closeout?

## Current System Limits

AI cannot fully confirm these yet:

- Exact assigned tech
- Booked labor hours
- Clocked labor hours
- Percent complete
- Parts ordered/received detail
- DVI photo quality
- Actual physical vehicle location
- Whether a tech is physically stalled unless bay-lap or TechFlow data confirms it

These require TechFlow/API data, Telegram bay-lap notes, screenshots, or future vision/camera integration.
"""

    OUT_MD.write_text(report, encoding="utf-8")

    print(f"Created: {OUT_MD}")
    print(f"Created: {OUT_JSON}")
    print()
    print("Open report:")
    print(f"notepad {OUT_MD}")


if __name__ == "__main__":
    main()