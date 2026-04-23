from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


NOW = datetime.now()
PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}
INPUT_FILE = Path(__file__).resolve().parent / "inputs" / "sample_input.json"


@dataclass
class MonitoredItem:
    item_id: str
    location: str
    advisor_name: str
    ticket_reference: str
    current_status: str
    last_update_at: datetime
    has_parts_hold: bool = False
    dvi_complete: bool = True
    estimate_complete: bool = True
    status_mismatch: bool = False
    follow_up_needed: bool = False
    notes: str = ""


def fallback_sample_items() -> list[MonitoredItem]:
    return [
        MonitoredItem(
            item_id="ITEM-001",
            location="Country Club",
            advisor_name="Drew",
            ticket_reference="RO-1201",
            current_status="waiting_on_parts",
            last_update_at=datetime(2026, 4, 22, 8, 10, 0),
            has_parts_hold=True,
            notes="Brake parts on order.",
        ),
        MonitoredItem(
            item_id="ITEM-002",
            location="Apache",
            advisor_name="Preston",
            ticket_reference="RO-1202",
            current_status="inspection_complete",
            last_update_at=datetime(2026, 4, 22, 7, 0, 0),
            dvi_complete=False,
            notes="Photos missing from inspection.",
        ),
        MonitoredItem(
            item_id="ITEM-003",
            location="Country Club",
            advisor_name="Drew",
            ticket_reference="RO-1203",
            current_status="estimate_pending",
            last_update_at=datetime(2026, 4, 21, 15, 0, 0),
            estimate_complete=False,
            follow_up_needed=True,
            notes="Customer waiting on estimate callback.",
        ),
        MonitoredItem(
            item_id="ITEM-004",
            location="Mobile",
            advisor_name="Drew",
            ticket_reference="RO-1204",
            current_status="ready",
            last_update_at=datetime(2026, 4, 21, 10, 30, 0),
            status_mismatch=True,
            notes="Ticket marked ready but note says still diagnosing.",
        ),
        MonitoredItem(
            item_id="ITEM-005",
            location="Apache",
            advisor_name="Preston",
            ticket_reference="RO-1205",
            current_status="active",
            last_update_at=datetime(2026, 4, 20, 16, 0, 0),
            follow_up_needed=True,
            notes="No recent customer update logged.",
        ),
    ]


def sample_items() -> list[MonitoredItem]:
    if not INPUT_FILE.exists():
        return fallback_sample_items()

    with INPUT_FILE.open("r", encoding="utf-8") as handle:
        raw_items = json.load(handle)

    return [
        MonitoredItem(
            item_id=item["item_id"],
            location=item["location"],
            advisor_name=item["advisor_name"],
            ticket_reference=item["ticket_reference"],
            current_status=item["current_status"],
            last_update_at=datetime.fromisoformat(item["last_update_at"]),
            has_parts_hold=item.get("has_parts_hold", False),
            dvi_complete=item.get("dvi_complete", True),
            estimate_complete=item.get("estimate_complete", True),
            status_mismatch=item.get("status_mismatch", False),
            follow_up_needed=item.get("follow_up_needed", False),
            notes=item.get("notes", ""),
        )
        for item in raw_items
    ]


def age_hours(item: MonitoredItem) -> float:
    return round((NOW - item.last_update_at).total_seconds() / 3600, 1)


def detect_exceptions(item: MonitoredItem) -> list[str]:
    exceptions: list[str] = []

    if item.has_parts_hold:
        exceptions.append("waiting_on_parts")
    if not item.dvi_complete:
        exceptions.append("dvi_missing_incomplete")
    if not item.estimate_complete and age_hours(item) >= 4:
        exceptions.append("estimate_stalled")
    if item.status_mismatch:
        exceptions.append("status_mismatch")
    if age_hours(item) >= 24:
        exceptions.append("overdue_follow_up")

    return exceptions


def assign_priority(item: MonitoredItem, exceptions: list[str]) -> str:
    score = 0

    if "status_mismatch" in exceptions:
        score += 3
    if "estimate_stalled" in exceptions:
        score += 2
    if "dvi_missing_incomplete" in exceptions:
        score += 2
    if "overdue_follow_up" in exceptions:
        score += 2
    if "waiting_on_parts" in exceptions:
        score += 1

    if age_hours(item) >= 24:
        score += 1

    if score >= 5:
        return "high"
    if score >= 3:
        return "medium"
    return "low"


def suggested_follow_up_question(exceptions: list[str]) -> str:
    if "status_mismatch" in exceptions:
        return "Which status is correct, and what is the immediate next step on this ticket?"
    if "estimate_stalled" in exceptions:
        return "What is blocking the estimate, and who needs to move it forward today?"
    if "dvi_missing_incomplete" in exceptions:
        return "What missing DVI support needs to be added before this can move forward?"
    if "overdue_follow_up" in exceptions:
        return "Who owns the next follow-up, and when will that update happen?"
    if "waiting_on_parts" in exceptions:
        return "What is the current parts ETA, and does the customer need an update now?"
    return "What is the next clear action for this item?"


def build_item_record(item: MonitoredItem) -> dict[str, object]:
    exceptions = detect_exceptions(item)
    priority = assign_priority(item, exceptions)
    return {
        "item_id": item.item_id,
        "ticket_reference": item.ticket_reference,
        "location": item.location,
        "advisor_name": item.advisor_name,
        "current_status": item.current_status,
        "last_update_age_hours": age_hours(item),
        "exceptions": exceptions,
        "priority": priority,
        "follow_up_needed": item.follow_up_needed,
        "notes": item.notes,
    }


def sort_records(records: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(
        records,
        key=lambda record: (
            PRIORITY_RANK[record["priority"]],
            -record["last_update_age_hours"],
        ),
    )


def action_type_for_item(item: dict[str, object]) -> str:
    exceptions = item["exceptions"]

    if "dvi_missing_incomplete" in exceptions:
        return "dvi_missing_incomplete"
    if "status_mismatch" in exceptions:
        return "status_mismatch"
    if "estimate_stalled" in exceptions:
        return "estimate_stalled"
    if "waiting_on_parts" in exceptions:
        return "waiting_on_parts"
    if "overdue_follow_up" in exceptions:
        return "overdue_follow_up"
    return "review"


def build_action_line(item: dict[str, object]) -> str:
    action_type = action_type_for_item(item)
    ticket_reference = item["ticket_reference"]

    if action_type == "estimate_stalled":
        return f"Follow up on estimate â€” waiting approval for {ticket_reference}"
    if action_type == "overdue_follow_up":
        return f"Call customer â€” overdue follow-up for {ticket_reference}"
    if action_type == "dvi_missing_incomplete":
        return f"Complete DVI â€” missing photos/notes for {ticket_reference}"
    if action_type == "waiting_on_parts":
        return f"Check parts ETA â€” possible delay for {ticket_reference}"
    if action_type == "status_mismatch":
        return f"Fix status mismatch for {ticket_reference}"
    return f"Review {ticket_reference}"


def summarize_items(items: list[MonitoredItem]) -> dict[str, object]:
    monitored_items = [build_item_record(item) for item in items]
    monitored_items = sort_records(monitored_items)

    counts_by_exception = {
        "waiting_on_parts": 0,
        "dvi_missing_incomplete": 0,
        "estimate_stalled": 0,
        "status_mismatch": 0,
        "overdue_follow_up": 0,
    }
    counts_by_priority = {"high": 0, "medium": 0, "low": 0}

    for item in monitored_items:
        for exception in item["exceptions"]:
            counts_by_exception[exception] += 1
        counts_by_priority[item["priority"]] += 1

    critical_items = [
        item for item in monitored_items if item["priority"] in {"high", "medium"}
    ]

    top_actions = []
    seen_action_types: set[str] = set()
    for item in monitored_items:
        action_type = action_type_for_item(item)
        if action_type in seen_action_types:
            continue
        top_actions.append(build_action_line(item))
        seen_action_types.add(action_type)
        if len(top_actions) == 3:
            break

    follow_up_tasks = []
    for item in monitored_items:
        if item["exceptions"] or item["follow_up_needed"]:
            follow_up_tasks.append(
                {
                    "ticket_reference": item["ticket_reference"],
                    "advisor_name": item["advisor_name"],
                    "priority": item["priority"],
                    "exception_summary": ", ".join(item["exceptions"])
                    or "manual follow-up needed",
                    "suggested_follow_up_question": suggested_follow_up_question(
                        item["exceptions"]
                    ),
                }
            )

    return {
        "generated_at": NOW.isoformat(),
        "total_items": len(items),
        "counts_by_exception": counts_by_exception,
        "counts_by_priority": counts_by_priority,
        "top_actions": top_actions,
        "critical_items": critical_items,
        "follow_up_tasks": follow_up_tasks,
        "items": monitored_items,
    }


def print_summary(summary: dict[str, object]) -> None:
    print("SHOP ACTIVITY SUMMARY")
    print(f"Generated at: {summary['generated_at']}")
    print(f"Total items: {summary['total_items']}")
    print()

    print("TOP 3 ACTIONS RIGHT NOW")
    if summary["top_actions"]:
        for action in summary["top_actions"]:
            print(f"- {action}")
    else:
        print("- none")
    print()

    print("Counts by exception:")
    for name, count in summary["counts_by_exception"].items():
        print(f"- {name}: {count}")
    print()

    print("Counts by priority:")
    for name, count in summary["counts_by_priority"].items():
        print(f"- {name}: {count}")
    print()

    print("CRITICAL / PRIORITY ITEMS")
    if summary["critical_items"]:
        for item in summary["critical_items"]:
            print(f"- {item['ticket_reference']} | {item['priority']}")
            print(f"  advisor: {item['advisor_name']}")
            print(f"  status: {item['current_status']}")
            print(f"  age_hours: {item['last_update_age_hours']}")
            print(f"  exceptions: {', '.join(item['exceptions'])}")
            print(f"  notes: {item['notes']}")
    else:
        print("- none")
    print()

    print("FOLLOW-UP TASKS")
    if summary["follow_up_tasks"]:
        for task in summary["follow_up_tasks"]:
            print(f"- ticket_reference: {task['ticket_reference']}")
            print(f"  advisor_name: {task['advisor_name']}")
            print(f"  priority: {task['priority']}")
            print(f"  exception_summary: {task['exception_summary']}")
            print(
                f"  suggested_follow_up_question: {task['suggested_follow_up_question']}"
            )
    else:
        print("- none")
    print()

    print("FULL ITEM LIST")
    for item in summary["items"]:
        print(f"- {item['item_id']} | {item['ticket_reference']} | {item['priority']}")
        print(f"  location: {item['location']}")
        print(f"  advisor: {item['advisor_name']}")
        print(f"  status: {item['current_status']}")
        print(f"  age_hours: {item['last_update_age_hours']}")
        print(f"  exceptions: {', '.join(item['exceptions']) or 'none'}")
        print(f"  notes: {item['notes']}")


def main() -> None:
    items = sample_items()
    summary = summarize_items(items)
    print_summary(summary)


if __name__ == "__main__":
    main()
PS C:\CALLAHAN\AI Workspace\AI-WORKSPACE\AI-TOOLS\Hermes-Runtime\modules>
