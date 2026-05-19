from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
BOARD_STATE_PATH = REPO_ROOT / "state" / "board_state.json"
OUTPUT_PATH = REPO_ROOT / "data" / "callie_insights.json"


def _load_board_state() -> dict:
    if not BOARD_STATE_PATH.exists():
        return {
            "generated_at": "",
            "jobs": [],
            "lane_counts": {"P1": 0, "P2": 0, "P3": 0, "P4": 0},
            "waiting_on_counts": {},
            "open_alert_count": 0,
            "message": "board_state.json is missing. Run python scripts/build_board_state.py first.",
        }

    try:
        return json.loads(BOARD_STATE_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "generated_at": "",
            "jobs": [],
            "lane_counts": {"P1": 0, "P2": 0, "P3": 0, "P4": 0},
            "waiting_on_counts": {},
            "open_alert_count": 0,
            "message": f"Unable to read board_state.json: {exc}",
        }


def _job_conflicts(job: dict) -> list[dict]:
    conflicts: list[dict] = []
    source = job.get("source_evidence", {}) if isinstance(job.get("source_evidence"), dict) else {}
    alerts = job.get("alerts", []) if isinstance(job.get("alerts"), list) else []

    source_wo = str(source.get("source_work_order_status", "unknown")).strip() or "unknown"
    source_dvi = str(source.get("source_dvi_status", "unknown")).strip() or "unknown"

    if source_wo not in {"", "unknown"} and source_dvi not in {"", "unknown"} and source_wo.lower() != source_dvi.lower():
        conflicts.append(
            {
                "kind": "source_status_conflict",
                "title": "Work-order and DVI statuses disagree",
                "detail": f"WO shows '{source_wo}' while DVI shows '{source_dvi}'.",
            }
        )

    for alert in alerts:
        if not isinstance(alert, dict):
            continue
        code = str(alert.get("code", "")).strip()
        if code in {"missing_tech_assignment", "missing_completed_dvi", "status_mapping_gap", "routing_bucket_active"}:
            conflicts.append(
                {
                    "kind": code,
                    "title": code.replace("_", " ").title(),
                    "detail": str(alert.get("message", "")).strip(),
                }
            )

    return conflicts


def _build_shop_summary(board_state: dict) -> str:
    lane_counts = board_state.get("lane_counts", {}) if isinstance(board_state.get("lane_counts"), dict) else {}
    p1 = int(lane_counts.get("P1", 0) or 0)
    p2 = int(lane_counts.get("P2", 0) or 0)
    p3 = int(lane_counts.get("P3", 0) or 0)
    p4 = int(lane_counts.get("P4", 0) or 0)
    alert_count = int(board_state.get("open_alert_count", 0) or 0)
    waiting = board_state.get("waiting_on_counts", {}) if isinstance(board_state.get("waiting_on_counts"), dict) else {}

    hot_owner = "Needs Review"
    hot_owner_count = -1
    for owner, count in waiting.items():
        safe_count = int(count or 0)
        if safe_count > hot_owner_count:
            hot_owner = str(owner)
            hot_owner_count = safe_count

    if p1:
        return f"Callie sees {p1} critical job(s), {p2} near-term move(s), and {alert_count} open helper signal(s). The heaviest current ownership load is {hot_owner}."
    if p2:
        return f"Callie sees no critical fires, but {p2} jobs need forward motion soon. Current helper signals open: {alert_count}. Heaviest ownership load: {hot_owner}."
    if p3 or p4:
        return f"Callie sees a calmer floor with {p3 + p4} monitor-or-hold jobs and {alert_count} open helper signal(s). Heaviest ownership load: {hot_owner}."
    return "Callie is waiting on fresh board data."


def build_insights(board_state: dict) -> dict:
    jobs = board_state.get("jobs", []) if isinstance(board_state.get("jobs"), list) else []
    conflicts: list[dict] = []
    job_cards: list[dict] = []

    for job in jobs:
        if not isinstance(job, dict):
            continue
        job_conflicts = _job_conflicts(job)
        conflicts.extend(
            [{"ro": str(job.get("ro", "Unknown RO")), **conflict} for conflict in job_conflicts]
        )
        job_cards.append(
            {
                "ro": str(job.get("ro", "")),
                "customer": str(job.get("customer", "")),
                "priority_lane": str(job.get("priority_lane", "")),
                "waiting_on": str(job.get("waiting_on", "")),
                "next_action": str(job.get("next_action", "")),
                "conflicts": job_conflicts,
                "board_reasons": job.get("board_reasons", []) if isinstance(job.get("board_reasons"), list) else [],
            }
        )

    return {
        "generated_at": datetime.now().isoformat(),
        "board_generated_at": str(board_state.get("generated_at", "")),
        "shop_summary": _build_shop_summary(board_state),
        "metrics": {
            "job_count": len(job_cards),
            "critical_jobs": int((board_state.get("lane_counts", {}) or {}).get("P1", 0) or 0),
            "near_term_jobs": int((board_state.get("lane_counts", {}) or {}).get("P2", 0) or 0),
            "open_alert_count": int(board_state.get("open_alert_count", 0) or 0),
            "conflict_count": len(conflicts),
        },
        "conflicts": conflicts,
        "jobs": job_cards,
        "message": str(board_state.get("message", "")),
    }


def write_insights(insights: dict) -> Path:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(insights, indent=2), encoding="utf-8")
    return OUTPUT_PATH


def main() -> None:
    board_state = _load_board_state()
    insights = build_insights(board_state)
    output_path = write_insights(insights)
    print(output_path)
    print(f"Jobs analyzed: {insights['metrics']['job_count']}")
    print(f"Conflicts found: {insights['metrics']['conflict_count']}")


if __name__ == "__main__":
    main()
