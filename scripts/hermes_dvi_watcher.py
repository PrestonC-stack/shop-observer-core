from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TEKMETRIC_EVENTS_FILE = ROOT / "state" / "tekmetric_events.jsonl"
BOARD_STATE_FILE = ROOT / "state" / "board_state.json"
HERMES_RECOMMENDATIONS_FILE = ROOT / "state" / "hermes_recommendations.json"
SUPPRESSION_FILE = ROOT / "state" / "hermes_dvi_alert_suppressions.json"

LOOKBACK_HOURS = 4
SUPPRESSION_HOURS = 2
MIN_PART_MARGIN_PERCENT = 40.0
MIN_LABOR_RATE_PER_HOUR = 125.0
STALE_AUTOFLOW_LABELS = {"waiting approval", "waiting_approval", "in progress", "in_progress", "servicing"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _parse_time(value: Any) -> datetime | None:
    if value in (None, "", [], {}):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_ro(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text.startswith("RO-"):
        text = text[3:].strip()
    return text


def _display_ro(ro: str) -> str:
    clean = _normalize_ro(ro)
    return f"RO-{clean}" if clean else "RO-UNKNOWN"


def _normalize_status(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return "unknown"
    return " ".join(text.replace("-", " ").replace("_", " ").split())


def _to_float(value: Any) -> float | None:
    if value in (None, "", [], {}):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        text = str(value).replace("$", "").replace(",", "").strip()
        try:
            return float(text)
        except (TypeError, ValueError):
            return None


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def _recent_tekmetric_events() -> list[dict[str, Any]]:
    cutoff = _now() - timedelta(hours=LOOKBACK_HOURS)
    recent = []
    for event in _read_jsonl(TEKMETRIC_EVENTS_FILE):
        event_time = _parse_time(event.get("detected_at_iso")) or _parse_time(event.get("received_at"))
        if event_time is None or event_time < cutoff:
            continue
        recent.append(event)
    return recent


def _group_events_by_ro(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        ro = _normalize_ro(event.get("ro_number"))
        if not ro:
            continue
        grouped.setdefault(ro, []).append(event)
    return grouped


def _board_jobs_by_ro() -> dict[str, dict[str, Any]]:
    board_state = _read_json(BOARD_STATE_FILE, {})
    jobs = board_state.get("jobs", []) if isinstance(board_state, dict) else []
    result: dict[str, dict[str, Any]] = {}
    for job in jobs:
        if not isinstance(job, dict):
            continue
        ro = _normalize_ro(job.get("ro") or job.get("ticket_reference"))
        if ro:
            result[ro] = job
    return result


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _concern_count(job: dict[str, Any]) -> int:
    for key in ("dvi_concern_count", "concern_count", "dvi_findings_count", "findings_count"):
        try:
            value = int(job.get(key))
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass

    for key in ("dvi_findings", "findings", "concerns", "dvi_items"):
        items = _as_list(job.get(key))
        if items:
            return len(items)

    source = job.get("source_evidence", {}) if isinstance(job.get("source_evidence"), dict) else {}
    for key in ("dvi_findings", "findings", "concerns", "dvi_items"):
        items = _as_list(source.get(key))
        if items:
            return len(items)

    raw = job.get("raw", {}) if isinstance(job.get("raw"), dict) else {}
    for key in ("dvi_items", "findings", "concerns"):
        items = _as_list(raw.get(key))
        if items:
            return len(items)

    alerts = _as_list(job.get("alerts"))
    return 1 if any(isinstance(alert, dict) and "dvi" in str(alert.get("code", "")).lower() for alert in alerts) else 0


def _gate_ran_at(job: dict[str, Any]) -> str:
    for key in ("gate_ran_at", "dvi_gate_ran_at", "dvi_reviewed_at"):
        value = str(job.get(key) or "").strip()
        if value:
            return value

    source = job.get("source_evidence", {}) if isinstance(job.get("source_evidence"), dict) else {}
    for key in ("gate_ran_at", "dvi_gate_ran_at", "dvi_reviewed_at"):
        value = str(source.get(key) or "").strip()
        if value:
            return value

    if str(job.get("dvi_review_status") or "").strip() not in {"", "NO_DVI"}:
        return str(job.get("generated_at") or source.get("shop_state_generated_at") or _now_iso())
    return ""


def _workflow_status(job: dict[str, Any]) -> str:
    return str(
        job.get("workflow_status")
        or job.get("canonical_status")
        or job.get("source_tekmetric_status")
        or "unknown"
    ).strip()


def _line_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        event
        for event in events
        if event.get("event_type") in {"estimate_line_added", "estimate_line_modified"}
    ]


def _latest_event(events: list[dict[str, Any]], event_types: set[str]) -> dict[str, Any] | None:
    matches = [event for event in events if event.get("event_type") in event_types]
    if not matches:
        return None
    return sorted(
        matches,
        key=lambda event: _parse_time(event.get("detected_at_iso")) or _parse_time(event.get("received_at")) or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )[0]


def _event_data(event: dict[str, Any]) -> dict[str, Any]:
    data = event.get("data")
    return data if isinstance(data, dict) else {}


def _alert(ro: str, alert_type: str, message: str, priority_lane: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "alert_type": alert_type,
        "ro_number": _normalize_ro(ro),
        "message": message,
        "priority_lane": priority_lane,
        "data": data or {},
        "generated_at": _now_iso(),
        "source": "hermes_dvi_watcher",
    }


def _load_suppressions() -> dict[str, str]:
    payload = _read_json(SUPPRESSION_FILE, {})
    return payload if isinstance(payload, dict) else {}


def _suppression_key(ro: str, alert_type: str) -> str:
    return f"{_normalize_ro(ro)}:{alert_type}"


def _is_suppressed(suppressions: dict[str, str], ro: str, alert_type: str) -> bool:
    until = _parse_time(suppressions.get(_suppression_key(ro, alert_type)))
    return bool(until and until > _now())


def _mark_suppressed(suppressions: dict[str, str], ro: str, alert_type: str) -> None:
    suppressions[_suppression_key(ro, alert_type)] = (_now() + timedelta(hours=SUPPRESSION_HOURS)).isoformat()


def resolve_alert(ro_number: str, alert_type: str) -> None:
    suppressions = _load_suppressions()
    _mark_suppressed(suppressions, ro_number, alert_type)
    _write_json(SUPPRESSION_FILE, suppressions)


def _unsuppressed(alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    suppressions = _load_suppressions()
    active_suppressions = {
        key: value
        for key, value in suppressions.items()
        if (_parse_time(value) or datetime.min.replace(tzinfo=timezone.utc)) > _now()
    }
    kept = []
    for alert in alerts:
        ro = str(alert.get("ro_number") or "")
        alert_type = str(alert.get("alert_type") or "")
        if _is_suppressed(active_suppressions, ro, alert_type):
            continue
        kept.append(alert)
    _write_json(SUPPRESSION_FILE, active_suppressions)
    return kept


def _status_mismatch_tekmetric_status(events: list[dict[str, Any]]) -> str:
    if _latest_event(events, {"invoice_created"}):
        return "invoice_created"
    if _latest_event(events, {"work_authorized"}):
        return "work_authorized"
    return ""


def _build_alerts() -> list[dict[str, Any]]:
    events_by_ro = _group_events_by_ro(_recent_tekmetric_events())
    jobs_by_ro = _board_jobs_by_ro()
    alerts: list[dict[str, Any]] = []

    for ro, job in jobs_by_ro.items():
        events = events_by_ro.get(ro, [])
        line_events = _line_events(events)
        concern_count = _concern_count(job)
        gate_ran = _gate_ran_at(job)

        if concern_count > 0 and len(line_events) < concern_count:
            alerts.append(_alert(
                ro,
                "ESTIMATE_INCOMPLETE",
                f"{_display_ro(ro)} - {concern_count} DVI finding(s) may not be on estimate. Review.",
                "DVI_ESTIMATE",
                {"dvi_concern_count": concern_count, "estimate_line_count": len(line_events)},
            ))

        if gate_ran and not _latest_event(events, {"estimate_line_added", "estimate_sent"}):
            alerts.append(_alert(
                ro,
                "ESTIMATE_NOT_STARTED",
                f"{_display_ro(ro)} - Gate complete, estimate not started. Build it now.",
                "DVI_ESTIMATE",
                {"gate_ran_at": gate_ran},
            ))

        tekmetric_status = _status_mismatch_tekmetric_status(events)
        autoflow_label = _workflow_status(job)
        if tekmetric_status and _normalize_status(autoflow_label) in STALE_AUTOFLOW_LABELS:
            alerts.append(_alert(
                ro,
                "STATUS_MISMATCH",
                f"{_display_ro(ro)} - {tekmetric_status} in TekMetric but AutoFlow shows '{autoflow_label}'. Update the label.",
                "ADVISOR_ACTION",
                {"tekmetric_status": tekmetric_status, "autoflow_label": autoflow_label},
            ))

    for ro, events in events_by_ro.items():
        for event in _line_events(events):
            data = _event_data(event)
            line_type = str(data.get("line_type") or "").strip().lower()
            description = str(data.get("description") or data.get("part_number") or "estimate line").strip()
            margin = _to_float(data.get("margin"))
            sell_price = _to_float(data.get("sell_price"))
            hours = _to_float(data.get("hours"))

            if line_type == "part" and margin is not None and margin < MIN_PART_MARGIN_PERCENT:
                alerts.append(_alert(
                    ro,
                    "LOW_MARGIN",
                    f"{_display_ro(ro)} - Low margin: {description} at {margin:.1f}%. Fix before sending.",
                    "ADVISOR_ACTION",
                    data,
                ))
            elif line_type == "labor" and sell_price is not None and hours and hours > 0:
                effective_rate = sell_price / hours
                if effective_rate < MIN_LABOR_RATE_PER_HOUR:
                    alert_data = dict(data)
                    alert_data["effective_labor_rate"] = round(effective_rate, 2)
                    alerts.append(_alert(
                        ro,
                        "LOW_MARGIN",
                        f"{_display_ro(ro)} - Low margin: {description} at ${effective_rate:.2f}/hr. Fix before sending.",
                        "ADVISOR_ACTION",
                        alert_data,
                    ))

    return alerts


def _merge_recommendations(alerts: list[dict[str, Any]]) -> dict[str, Any]:
    recommendations = _read_json(HERMES_RECOMMENDATIONS_FILE, {})
    if not isinstance(recommendations, dict):
        recommendations = {}
    recommendations["dvi_alerts"] = alerts
    recommendations["dvi_alerts_generated_at"] = _now_iso()
    recommendations["dvi_alert_count"] = len(alerts)
    _write_json(HERMES_RECOMMENDATIONS_FILE, recommendations)
    return recommendations


def run_dvi_watch() -> dict[str, Any]:
    alerts = _unsuppressed(_build_alerts())
    return _merge_recommendations(alerts)


if __name__ == "__main__":
    result = run_dvi_watch()
    print(HERMES_RECOMMENDATIONS_FILE)
    print(f"DVI alerts: {result.get('dvi_alert_count', 0)}")
