from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BOARD_STATE_FILE = ROOT / "state" / "board_state.json"
RECOMMENDATIONS_FILE = ROOT / "state" / "hermes_recommendations.json"
LOG_DIR = ROOT / "logs"
LOG_FILE = LOG_DIR / "hermes_scheduler.log"

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen2.5-coder:7b"
OLLAMA_TIMEOUT_SECONDS = 75
OVERDUE_HOURS = 24.0


def _configure_logger() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("hermes_scheduler")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger


LOGGER = _configure_logger()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_board_state() -> dict[str, Any]:
    with BOARD_STATE_FILE.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("board_state.json did not contain a JSON object")
    return payload


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _hours_since(value: Any) -> float:
    parsed = _parse_datetime(value)
    if parsed is None:
        return 0.0
    return round((datetime.now(timezone.utc) - parsed).total_seconds() / 3600, 1)


def _time_in_status_hours(job: dict[str, Any]) -> float:
    for key in ("hours_in_status", "status_age_hours", "age_hours"):
        try:
            if job.get(key) not in (None, ""):
                return round(float(job.get(key)), 1)
        except (TypeError, ValueError):
            pass

    for key in ("status_updated_at", "last_updated_at", "updated_at", "generated_at"):
        hours = _hours_since(job.get(key))
        if hours > 0:
            return hours

    source = job.get("source_evidence", {}) if isinstance(job.get("source_evidence"), dict) else {}
    for key in ("status_updated_at", "last_updated_at", "shop_state_generated_at"):
        hours = _hours_since(source.get(key))
        if hours > 0:
            return hours

    return 0.0


def _normalize_status(value: Any) -> str:
    text = str(value or "unknown").strip().lower()
    if not text:
        return "unknown"
    return " ".join(text.replace("_", " ").split())


def _job_label(job: dict[str, Any]) -> str:
    ro = str(job.get("ro") or job.get("ticket_reference") or "Unknown RO").strip()
    customer = str(job.get("customer") or "Unknown Customer").strip()
    status = str(job.get("workflow_status") or job.get("canonical_status") or "unknown").strip()
    waiting_on = str(job.get("waiting_on") or "Needs Review").strip()
    return f"{ro} | {customer} | {status} | waiting on {waiting_on}"


def _summarize_board(board_state: dict[str, Any]) -> dict[str, Any]:
    jobs = [job for job in board_state.get("jobs", []) if isinstance(job, dict)]
    p1_jobs = [job for job in jobs if str(job.get("priority_lane", "")).upper() == "P1"]
    p2_jobs = [job for job in jobs if str(job.get("priority_lane", "")).upper() == "P2"]
    mitch_jobs = [job for job in jobs if str(job.get("waiting_on", "")).lower() == "mitch"]
    drew_jobs = [job for job in jobs if str(job.get("waiting_on", "")).lower() == "drew"]
    unknown_jobs = [
        job
        for job in jobs
        if _normalize_status(job.get("workflow_status") or job.get("canonical_status")) in {"aaa", "unknown"}
    ]

    timed_jobs = [
        {
            "ro": str(job.get("ro") or "Unknown RO"),
            "customer": str(job.get("customer") or "Unknown Customer"),
            "status": str(job.get("workflow_status") or job.get("canonical_status") or "unknown"),
            "waiting_on": str(job.get("waiting_on") or "Needs Review"),
            "hours_in_status": _time_in_status_hours(job),
        }
        for job in jobs
    ]
    timed_jobs.sort(key=lambda row: row["hours_in_status"], reverse=True)
    overdue_jobs = [row for row in timed_jobs if row["hours_in_status"] >= OVERDUE_HOURS]

    return {
        "total_jobs": len(jobs),
        "p1_count": len(p1_jobs),
        "p2_count": len(p2_jobs),
        "overdue_count": len(overdue_jobs),
        "advisor_queues": {
            "mitch": len(mitch_jobs),
            "drew": len(drew_jobs),
        },
        "unknown_status_jobs": [_job_label(job) for job in unknown_jobs[:8]],
        "longest_time_in_status": timed_jobs[:8],
        "overdue_jobs": overdue_jobs[:8],
    }


def _build_prompt(summary: dict[str, Any]) -> str:
    return (
        "You are Hermes, the Callahan Auto shop operations copilot. "
        "Read the structured board snapshot and return JSON only. "
        "Keep the summary to one short paragraph. Alerts and suggestions should be practical, calm, and specific.\n\n"
        "Required JSON shape:\n"
        "{\n"
        '  "summary": "<one paragraph shop pulse>",\n'
        '  "alerts": ["<alert 1>", "<alert 2>"],\n'
        '  "suggestions": ["<suggestion 1>", "<suggestion 2>"]\n'
        "}\n\n"
        "Board snapshot:\n"
        + json.dumps(summary, ensure_ascii=True, indent=2)
    )


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = str(text or "").strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`").strip()
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start >= 0 and end >= start:
        stripped = stripped[start : end + 1]

    parsed = json.loads(stripped)
    if not isinstance(parsed, dict):
        raise ValueError("Ollama response JSON was not an object")
    return parsed


def _call_ollama(prompt: str) -> dict[str, Any]:
    request_body = json.dumps(
        {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.2},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        OLLAMA_URL,
        data=request_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=OLLAMA_TIMEOUT_SECONDS) as response:
        raw = response.read().decode("utf-8", errors="replace")
    outer = json.loads(raw)
    if not isinstance(outer, dict):
        raise ValueError("Ollama API response was not a JSON object")
    return _extract_json_object(str(outer.get("response", "")))


def _clean_list(value: Any, limit: int = 5) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned = [str(item).strip() for item in value if str(item).strip()]
    return cleaned[:limit]


def _fallback_recommendations(summary: dict[str, Any], reason: str = "") -> dict[str, Any]:
    total = int(summary.get("total_jobs", 0) or 0)
    p1 = int(summary.get("p1_count", 0) or 0)
    p2 = int(summary.get("p2_count", 0) or 0)
    overdue = int(summary.get("overdue_count", 0) or 0)
    queues = summary.get("advisor_queues", {}) if isinstance(summary.get("advisor_queues"), dict) else {}
    mitch = int(queues.get("mitch", 0) or 0)
    drew = int(queues.get("drew", 0) or 0)
    unknown_jobs = summary.get("unknown_status_jobs", []) if isinstance(summary.get("unknown_status_jobs"), list) else []
    longest = summary.get("longest_time_in_status", []) if isinstance(summary.get("longest_time_in_status"), list) else []

    alerts: list[str] = []
    if p1:
        alerts.append(f"{p1} P1 job(s) need first attention.")
    if overdue:
        alerts.append(f"{overdue} job(s) have been in status at least {int(OVERDUE_HOURS)} hours.")
    if unknown_jobs:
        alerts.append(f"{len(unknown_jobs)} job(s) have aaa/unknown status and need source cleanup.")
    if not alerts:
        alerts.append("No major board pressure detected by the deterministic fallback.")

    suggestions = [
        "Review P1 and P2 jobs first, then clear unknown status records before they become invisible.",
        "Balance advisor follow-up load if Mitch and Drew queues drift apart by three or more jobs.",
    ]
    if longest:
        first = longest[0]
        suggestions.insert(
            0,
            f"Check longest time-in-status item: {first.get('ro', 'Unknown RO')} at {first.get('hours_in_status', 0)} hours.",
        )
    if reason:
        suggestions.append(f"Model fallback reason: {reason[:180]}")

    return {
        "summary": f"Board pulse: {total} active job(s), {p1} P1, {p2} P2, and {overdue} overdue by status age.",
        "alerts": alerts[:5],
        "suggestions": suggestions[:5],
        "load_balance": {
            "mitch": mitch,
            "drew": drew,
            "flag": abs(mitch - drew) >= 3,
        },
    }


def _build_recommendations(board_summary: dict[str, Any]) -> dict[str, Any]:
    try:
        model_result = _call_ollama(_build_prompt(board_summary))
        recommendations = {
            "summary": str(model_result.get("summary") or "").strip(),
            "alerts": _clean_list(model_result.get("alerts")),
            "suggestions": _clean_list(model_result.get("suggestions")),
            "load_balance": _fallback_recommendations(board_summary)["load_balance"],
        }
        if not recommendations["summary"]:
            raise ValueError("Ollama JSON did not include a summary")
        LOGGER.info("Ollama recommendations generated successfully")
        return recommendations
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, OSError) as exc:
        LOGGER.warning("Ollama recommendation generation failed, using fallback: %s", exc)
        return _fallback_recommendations(board_summary, reason=str(exc))


def main() -> int:
    LOGGER.info("Hermes scheduler run started")
    try:
        board_state = _load_board_state()
        board_summary = _summarize_board(board_state)
        recommendations = _build_recommendations(board_summary)
        output = {
            "generated_at": _now_iso(),
            "summary": recommendations["summary"],
            "alerts": recommendations["alerts"],
            "suggestions": recommendations["suggestions"],
            "load_balance": recommendations["load_balance"],
        }
        RECOMMENDATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        RECOMMENDATIONS_FILE.write_text(json.dumps(output, ensure_ascii=True, indent=2), encoding="utf-8")
        LOGGER.info(
            "Hermes scheduler run completed: total_jobs=%s p1=%s p2=%s overdue=%s alerts=%s suggestions=%s",
            board_summary["total_jobs"],
            board_summary["p1_count"],
            board_summary["p2_count"],
            board_summary["overdue_count"],
            len(output["alerts"]),
            len(output["suggestions"]),
        )
        print(RECOMMENDATIONS_FILE)
        print(f"Alerts: {len(output['alerts'])}")
        print(f"Suggestions: {len(output['suggestions'])}")
        return 0
    except Exception:
        LOGGER.exception("Hermes scheduler run failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
