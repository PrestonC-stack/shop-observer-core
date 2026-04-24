from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


NOW = datetime.now()
PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}
INPUTS_DIR = Path(__file__).resolve().parent / "inputs"
CURRENT_SHOP_SNAPSHOT_FILE = INPUTS_DIR / "current_shop_snapshot.json"
INPUT_FILE = INPUTS_DIR / "sample_input.json"
OUTPUTS_DIR = Path(__file__).resolve().parent / "outputs"
HISTORY_DIR = OUTPUTS_DIR / "history"


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


def load_items_from_json(input_path: Path) -> list[MonitoredItem]:
    with input_path.open("r", encoding="utf-8") as handle:
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


def sample_items() -> list[MonitoredItem]:
    if CURRENT_SHOP_SNAPSHOT_FILE.exists():
        return load_items_from_json(CURRENT_SHOP_SNAPSHOT_FILE)
    if INPUT_FILE.exists():
        return load_items_from_json(INPUT_FILE)
    return fallback_sample_items()


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


def display_ticket_reference(item: MonitoredItem) -> str:
    ticket_reference = item.ticket_reference.strip()
    if ticket_reference and ticket_reference != "RO-XXXX":
        return ticket_reference

    location_prefix = {
        "Country Club": "CC",
        "Apache": "AP",
        "Mobile": "MB",
    }.get(item.location, "UNK")
    return f"{location_prefix}-{item.item_id}"


def build_item_record(item: MonitoredItem) -> dict[str, object]:
    exceptions = detect_exceptions(item)
    priority = assign_priority(item, exceptions)
    return {
        "item_id": item.item_id,
        "ticket_reference": item.ticket_reference,
        "display_ticket_reference": display_ticket_reference(item),
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


def build_action_line(item: dict[str, object]) -> str:
    exceptions = item["exceptions"]
    ticket_reference = item["display_ticket_reference"]

    if "dvi_missing_incomplete" in exceptions:
        return f"Complete DVI - missing photos/notes for {ticket_reference}"
    if "status_mismatch" in exceptions:
        return f"Fix status mismatch for {ticket_reference}"
    if "estimate_stalled" in exceptions:
        return f"Follow up on estimate - waiting approval for {ticket_reference}"
    if "waiting_on_parts" in exceptions:
        return f"Check parts ETA - possible delay for {ticket_reference}"
    if "overdue_follow_up" in exceptions:
        return f"Call customer - overdue follow-up for {ticket_reference}"
    return f"Review {ticket_reference}"


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


def build_executive_summary(
    by_location: dict[str, dict[str, int]], top_actions: list[str]
) -> list[str]:
    lines: list[str] = []

    highest_location = None
    highest_high_count = -1
    for location, counts in by_location.items():
        if counts["high"] > highest_high_count:
            highest_high_count = counts["high"]
            highest_location = location

    if highest_location is not None and highest_high_count > 0:
        lines.append(
            f"Highest high-priority load: {highest_location} with {highest_high_count} high-priority item(s)."
        )
    else:
        lines.append("No high-priority items are currently flagged.")

    dvi_locations = [
        location
        for location, counts in by_location.items()
        if counts["dvi_missing_incomplete"] > 0
    ]
    if dvi_locations:
        lines.append(f"DVI issues are present in: {', '.join(dvi_locations)}.")

    stalled_locations = [
        location
        for location, counts in by_location.items()
        if counts["estimate_stalled"] > 0
    ]
    if stalled_locations:
        lines.append(f"Stalled estimates are present in: {', '.join(stalled_locations)}.")

    if top_actions:
        lines.append(f"Main focus right now: {top_actions[0]}.")
    else:
        lines.append("Main focus right now: review current ticket flow and exceptions.")

    return lines[:5]


def build_question_for_preston(
    exceptions: list[str], ticket_reference: str
) -> str:
    if "estimate_stalled" in exceptions:
        return f"What is blocking the estimate for {ticket_reference}?"
    if "dvi_missing_incomplete" in exceptions:
        return f"What DVI support is missing for {ticket_reference}?"
    if "waiting_on_parts" in exceptions:
        return f"Is the parts ETA known for {ticket_reference}?"
    if "overdue_follow_up" in exceptions:
        return f"Does {ticket_reference} need a customer update right now?"
    if "status_mismatch" in exceptions:
        return f"Which status is accurate for {ticket_reference}?"
    return f"What follow-up is needed for {ticket_reference}?"


def build_follow_up_task(item: dict[str, object]) -> dict[str, object]:
    exceptions = item.get("exceptions", [])
    exception_summary = ", ".join(exceptions) or "manual follow-up needed"

    suggested_question = suggested_follow_up_question(exceptions)
    if not suggested_question.strip():
        suggested_question = (
            f"What follow-up is needed for {item['display_ticket_reference']}?"
        )

    return {
        "ticket_reference": item["display_ticket_reference"],
        "advisor_name": item["advisor_name"],
        "priority": item["priority"],
        "exception_summary": exception_summary,
        "suggested_follow_up_question": suggested_question,
    }


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
    by_advisor: dict[str, dict[str, int]] = {}
    by_location: dict[str, dict[str, int]] = {}

    for item in monitored_items:
        for exception in item["exceptions"]:
            counts_by_exception[exception] += 1
        counts_by_priority[item["priority"]] += 1

        advisor_name = item["advisor_name"]
        if advisor_name not in by_advisor:
            by_advisor[advisor_name] = {
                "estimate_stalled": 0,
                "overdue_follow_up": 0,
                "dvi_missing_incomplete": 0,
                "waiting_on_parts": 0,
                "status_mismatch": 0,
            }
        for exception in item["exceptions"]:
            if exception in by_advisor[advisor_name]:
                by_advisor[advisor_name][exception] += 1

        location = item["location"]
        if location not in by_location:
            by_location[location] = {
                "total_items": 0,
                "high": 0,
                "medium": 0,
                "low": 0,
                "estimate_stalled": 0,
                "overdue_follow_up": 0,
                "dvi_missing_incomplete": 0,
                "waiting_on_parts": 0,
                "status_mismatch": 0,
            }

        by_location[location]["total_items"] += 1
        by_location[location][item["priority"]] += 1
        for exception in item["exceptions"]:
            if exception in by_location[location]:
                by_location[location][exception] += 1

    critical_items = [
        item for item in monitored_items if item["priority"] in {"high", "medium"}
    ]

    top_actions = []
    used_action_types = set()

    for item in monitored_items:
        action_line = build_action_line(item)

        # Extract action type (text before " - ")
        action_type = action_line.split(" - ")[0]

        if action_type not in used_action_types:
            top_actions.append(action_line)
            used_action_types.add(action_type)

        if len(top_actions) == 3:
            break

    # If fewer than 3 unique actions exist, fill remaining slots
    if len(top_actions) < 3:
        for item in monitored_items:
            action_line = build_action_line(item)
            if action_line not in top_actions:
                top_actions.append(action_line)
            if len(top_actions) == 3:
                break

    executive_summary = build_executive_summary(by_location, top_actions)

    follow_up_tasks = []
    questions_for_preston = []
    for item in monitored_items:
        if item["exceptions"] or item["follow_up_needed"]:
            follow_up_tasks.append(build_follow_up_task(item))
            questions_for_preston.append(
                build_question_for_preston(
                    item["exceptions"], item["display_ticket_reference"]
                )
            )

    return {
        "generated_at": NOW.isoformat(),
        "total_items": len(items),
        "counts_by_exception": counts_by_exception,
        "counts_by_priority": counts_by_priority,
        "executive_summary": executive_summary,
        "top_actions": top_actions,
        "by_advisor": by_advisor,
        "by_location": by_location,
        "critical_items": critical_items,
        "follow_up_tasks": follow_up_tasks,
        "questions_for_preston": questions_for_preston,
        "items": monitored_items,
    }


def print_summary(summary: dict[str, object]) -> None:
    print("SHOP ACTIVITY SUMMARY")
    print(f"Generated at: {summary['generated_at']}")
    print(f"Total items: {summary['total_items']}")
    print()

    print("EXECUTIVE SUMMARY")
    if summary["executive_summary"]:
        for line in summary["executive_summary"]:
            print(f"- {line}")
    else:
        print("- none")
    print()

    print("TOP 3 ACTIONS RIGHT NOW")
    if summary["top_actions"]:
        for action in summary["top_actions"]:
            print(f"- {action}")
    else:
        print("- none")
    print()

    print("BY ADVISOR")
    if summary["by_advisor"]:
        for advisor_name, counts in summary["by_advisor"].items():
            visible_counts = [
                f"{category}: {count}"
                for category, count in counts.items()
                if count > 0
            ]
            if visible_counts:
                print(f"- {advisor_name}")
                for line in visible_counts:
                    print(f"  {line}")
    else:
        print("- none")
    print()

    print("BY LOCATION")
    if summary["by_location"]:
        for location, counts in summary["by_location"].items():
            print(f"{location}:")
            print(f"- total items: {counts['total_items']}")
            print(f"- high: {counts['high']}")
            print(f"- medium: {counts['medium']}")
            print(f"- low: {counts['low']}")
            if counts["estimate_stalled"] > 0:
                print(f"- stalled estimates: {counts['estimate_stalled']}")
            if counts["overdue_follow_up"] > 0:
                print(f"- overdue follow-ups: {counts['overdue_follow_up']}")
            if counts["dvi_missing_incomplete"] > 0:
                print(f"- dvi issues: {counts['dvi_missing_incomplete']}")
            if counts["waiting_on_parts"] > 0:
                print(f"- waiting on parts: {counts['waiting_on_parts']}")
            if counts["status_mismatch"] > 0:
                print(f"- status mismatches: {counts['status_mismatch']}")
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
            print(f"- {item['display_ticket_reference']} | {item['priority']}")
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

    print("QUESTIONS FOR PRESTON")
    if summary["questions_for_preston"]:
        for question in summary["questions_for_preston"]:
            print(f"- {question}")
    else:
        print("- none")
    print()

    print("FULL ITEM LIST")
    for item in summary["items"]:
        print(
            f"- {item['item_id']} | {item['display_ticket_reference']} | {item['priority']}"
        )
        print(f"  location: {item['location']}")
        print(f"  advisor: {item['advisor_name']}")
        print(f"  status: {item['current_status']}")
        print(f"  age_hours: {item['last_update_age_hours']}")
        print(f"  exceptions: {', '.join(item['exceptions']) or 'none'}")
        print(f"  notes: {item['notes']}")


def write_report_outputs(report_text: str) -> None:
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    latest_summary_path = OUTPUTS_DIR / "latest_summary.txt"
    history_summary_path = HISTORY_DIR / f"shop_summary_{NOW.strftime('%Y-%m-%d_%H%M')}.txt"

    latest_summary_path.write_text(report_text, encoding="utf-8")
    history_summary_path.write_text(report_text, encoding="utf-8")


def main() -> None:
    items = sample_items()
    summary = summarize_items(items)
    report_buffer = io.StringIO()
    with redirect_stdout(report_buffer):
        print_summary(summary)

    report_text = report_buffer.getvalue()
    print(report_text, end="")
    write_report_outputs(report_text)


if __name__ == "__main__":
    main()
