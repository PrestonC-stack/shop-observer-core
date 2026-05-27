from datetime import datetime


def build_hermes_summary_payload(board_state, insights):
    jobs = board_state.get("jobs", []) if isinstance(board_state, dict) else []
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
