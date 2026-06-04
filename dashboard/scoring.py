import json
from datetime import datetime, timezone
from pathlib import Path


TRANSITIONS_PATH = Path(__file__).resolve().parents[1] / "data" / "status_transitions" / "transitions.jsonl"
MISSING_TRANSITION_FALLBACK = "999h"


def _parse_transition_timestamp(value):
    if not value:
        return None

    text = str(value).strip()
    if not text:
        return None

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    if parsed.tzinfo:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _format_elapsed_time(started_at, now=None):
    now_dt = now or datetime.utcnow()
    if now_dt.tzinfo:
        now_dt = now_dt.astimezone(timezone.utc).replace(tzinfo=None)

    elapsed_seconds = max(int((now_dt - started_at).total_seconds()), 0)
    elapsed_minutes = elapsed_seconds // 60
    days = elapsed_minutes // 1440
    hours = (elapsed_minutes % 1440) // 60
    minutes = elapsed_minutes % 60

    if days:
        return f"{days}d {hours}h" if hours else f"{days}d"
    if hours:
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"
    return f"{minutes}m"


def _load_latest_transition_timestamps(path=TRANSITIONS_PATH):
    if not path.exists():
        return {}

    latest_by_ro = {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                ro_number = str(event.get("ro_number") or "").strip()
                timestamp = _parse_transition_timestamp(event.get("timestamp"))
                if not ro_number or not timestamp:
                    continue

                current = latest_by_ro.get(ro_number)
                if current is None or timestamp > current:
                    latest_by_ro[ro_number] = timestamp
    except OSError:
        return {}

    return latest_by_ro


def get_time_in_status_display(ro_number, transitions=None, now=None):
    ro_key = str(ro_number or "").strip()
    if not ro_key:
        return MISSING_TRANSITION_FALLBACK

    transition_map = transitions if transitions is not None else _load_latest_transition_timestamps()
    started_at = transition_map.get(ro_key)
    if not started_at:
        return MISSING_TRANSITION_FALLBACK

    return _format_elapsed_time(started_at, now=now)


def _apply_transition_time_display(jobs):
    transitions = _load_latest_transition_timestamps()
    for job in jobs:
        if not isinstance(job, dict):
            continue

        ro_number = job.get("ro") or job.get("ro_number")
        elapsed_display = get_time_in_status_display(ro_number, transitions=transitions)
        job["time_in_status"] = elapsed_display
        job["time_in_status_display"] = elapsed_display
    return jobs


def build_hermes_summary_payload(board_state, insights):
    jobs = board_state.get("jobs", []) if isinstance(board_state, dict) else []
    _apply_transition_time_display(jobs)
    p1_jobs = [job for job in jobs if isinstance(job, dict) and job.get("priority_lane") == "P1"]
    p2_jobs = [job for job in jobs if isinstance(job, dict) and job.get("priority_lane") == "P2"]
    missing_ro_jobs = [
        job for job in jobs
        if isinstance(job, dict) and any(alert.get("code") == "missing_ro" for alert in job.get("alerts", []))
    ]
    clock_in_jobs = [
        job for job in jobs
        if isinstance(job, dict) and any(alert.get("code") == "verify_tech_clock_in" for alert in job.get("alerts", []))
    ]
    dvi_quality_jobs = [
        job for job in jobs
        if isinstance(job, dict) and any(alert.get("code") == "missing_completed_dvi" for alert in job.get("alerts", []))
    ]
    needs_review_jobs = [job for job in jobs if isinstance(job, dict) and job.get("waiting_on") == "Needs Review"]

    recommendations = []
    if p1_jobs:
        top = p1_jobs[:3]
        recommendations.append(
            "Best next actions: " +
            "; ".join(
                f"{job.get('ro', 'Unknown RO')} ({job.get('waiting_on', 'Needs Review')}): {job.get('next_action', '')}"
                for job in top
            )
        )
    if p2_jobs:
        recommendations.append(
            f"Controlled action gap: {len(p2_jobs)} job(s) currently need information, estimate work, approval follow-up, or production-control movement."
        )
    if clock_in_jobs:
        recommendations.append(
            f"Productivity watch: {len(clock_in_jobs)} job(s) need a quick tech clock-in verification so advisors can trust the progress signal."
        )
    if dvi_quality_jobs:
        recommendations.append(
            f"DVI quality watch: {len(dvi_quality_jobs)} job(s) still need clearer completed inspection evidence before the repair story is fully trustworthy."
        )
    if missing_ro_jobs:
        recommendations.append(
            f"Data quality: {len(missing_ro_jobs)} board item(s) are missing a confirmed RO and should be cleaned up before they drift."
        )
    if needs_review_jobs:
        recommendations.append(
            f"Intelligence gap: {len(needs_review_jobs)} job(s) still need stronger status mapping so the board can coach more precisely."
        )
    if not recommendations:
        recommendations.append(
            "Momentum looks steady right now. Keep advisors ahead of technicians and protect the next customer promise window."
        )

    summary_text = "\n".join(recommendations)
    if insights.get("shop_summary"):
        summary_text = str(insights.get("shop_summary")).strip() + "\n" + summary_text

    conflicts = insights.get("conflicts", []) if isinstance(insights.get("conflicts"), list) else []
    return {
        "source": "board_rules_v1",
        "status": "ok",
        "summary": summary_text,
        "shop_summary": insights.get("shop_summary", ""),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "conflicts": conflicts[:8],
        "conflict_count": len(conflicts),
    }


def build_bay_metrics(jobs):
    _apply_transition_time_display(jobs)
    p1 = len([job for job in jobs if isinstance(job, dict) and job.get("priority_lane") == "P1"])
    communication_needs = len([
        job for job in jobs
        if isinstance(job, dict) and any(alert.get("code") == "customer_follow_up_due" for alert in job.get("alerts", []))
    ])
    productivity_needs = len([
        job for job in jobs
        if isinstance(job, dict) and any(alert.get("code") == "verify_tech_clock_in" for alert in job.get("alerts", []))
    ])
    data_needs = len([
        job for job in jobs
        if isinstance(job, dict) and any(alert.get("code") in {"missing_ro", "status_mapping_gap", "missing_tech_assignment", "missing_info", "missing_customer_concern", "missing_completed_dvi"} for alert in job.get("alerts", []))
    ])
    total = max(len(jobs), 1)
    support_score = round(((total - communication_needs) + (total - productivity_needs) + (total - data_needs)) / (total * 3) * 100)
    front_score = round((((total - communication_needs) + (total - len([job for job in jobs if isinstance(job, dict) and job.get("priority_lane") == "P2"]))) / (total * 2)) * 100)
    back_score = round((((total - productivity_needs) + (total - len([job for job in jobs if isinstance(job, dict) and any(alert.get("code") == "missing_completed_dvi" for alert in job.get("alerts", []))]))) / (total * 2)) * 100)
    return {
        "p1": p1,
        "communication_needs": communication_needs,
        "productivity_needs": productivity_needs,
        "data_needs": data_needs,
        "support_score": support_score,
        "front_score": front_score,
        "back_score": back_score,
    }
