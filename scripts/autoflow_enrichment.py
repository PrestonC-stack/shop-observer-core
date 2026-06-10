"""
Pull and cache AutoFlow enrichment data for active repair orders.

This module intentionally does not wire enrichment into scoring or board
rendering. It only fetches, derives a small summary, and writes a safe cache.
"""

from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from scripts.scoring_engine import _hours_since, _now_utc, _ro_id

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - runtime convenience if dotenv is unavailable
    def load_dotenv(*_args, **_kwargs):
        return False


REPO_ROOT = Path(__file__).resolve().parents[1]
SHOP_STATE_PATH = REPO_ROOT / "state" / "shop_state.json"
ENRICHMENT_DIR = REPO_ROOT / "state" / "enrichment"
AUTOFLOW_BASE_URL = "https://callahanautomotive.autotext.me/api/v1"
API_TIMEOUT_SECONDS = 15

API_CALL_COUNT = 0
FIRST_CONVERSATIONS_URL_LOGGED = False


class EnrichmentError(RuntimeError):
    """Raised when an RO enrichment pull should be treated as failed."""


class AutoFlowHTTPError(EnrichmentError):
    def __init__(self, path: str, code: int, detail: str):
        self.path = path
        self.code = code
        self.detail = detail
        super().__init__(f"AutoFlow HTTP {code} for {path}: {detail}")


def _utc_now_iso() -> str:
    return _now_utc().isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _autoflow_headers() -> dict[str, str]:
    load_dotenv(REPO_ROOT / ".env")
    api_key = os.getenv("AUTOFLOW_API_KEY")
    api_password = os.getenv("AUTOFLOW_API_PASSWORD")
    if not api_key or not api_password:
        raise EnrichmentError("AUTOFLOW_API_KEY/AUTOFLOW_API_PASSWORD not configured")

    token = base64.b64encode(f"{api_key}:{api_password}".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "Accept": "application/json",
    }


def _api_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    global API_CALL_COUNT
    url = f"{AUTOFLOW_BASE_URL}/{path.lstrip('/')}"
    if params:
        url = f"{url}?{urlencode(params)}"
    req = Request(url, headers=_autoflow_headers(), method="GET")
    API_CALL_COUNT += 1
    try:
        with urlopen(req, timeout=API_TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:300]
        if not detail:
            detail = str(error.reason or "HTTP error")
        raise AutoFlowHTTPError(path, error.code, detail) from error
    except (URLError, OSError) as error:
        raise EnrichmentError(f"AutoFlow request failed for {path}: {error}") from error

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as error:
        raise EnrichmentError(f"AutoFlow returned non-JSON for {path}") from error
    if not isinstance(parsed, dict):
        raise EnrichmentError(f"AutoFlow returned unexpected JSON for {path}")
    return parsed


def _cache_path(ro: str) -> Path:
    return ENRICHMENT_DIR / f"{str(ro).strip()}.json"


def _cache_is_fresh(ro: str, max_age_minutes: int) -> bool:
    path = _cache_path(ro)
    if not path.exists():
        return False
    try:
        payload = _load_json(path)
    except (OSError, json.JSONDecodeError):
        return False
    hours_old = _hours_since(payload.get("fetched_at"))
    if hours_old >= 999:
        return False
    return hours_old <= (max_age_minutes / 60)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True),
        encoding="utf-8",
    )
    tmp_path.replace(path)


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _nested_dict(value: Any, *keys: str) -> dict[str, Any]:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    return current if isinstance(current, dict) else {}


def _first_dict(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict):
            return value
    return {}


def _first_value(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _parse_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    from datetime import datetime, timezone

    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _is_arrived(part: dict[str, Any]) -> bool:
    arrived = part.get("arrived")
    if isinstance(arrived, bool):
        return arrived
    return str(arrived).strip().lower() in {"1", "true", "yes", "arrived", "received"}


def _work_order_payload(raw_work_order: dict[str, Any]) -> dict[str, Any]:
    return _first_dict(
        raw_work_order.get("work_order"),
        _nested_dict(raw_work_order, "response", "work_order"),
        _nested_dict(raw_work_order, "data", "work_order"),
        raw_work_order,
    )


def _repair_order_payload(raw_repair_order: dict[str, Any]) -> dict[str, Any]:
    return _first_dict(
        raw_repair_order.get("repair_order"),
        _nested_dict(raw_repair_order, "response", "repair_order"),
        _nested_dict(raw_repair_order, "data", "repair_order"),
        raw_repair_order,
    )


def _conversation_entries(raw_conversations: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = [
        raw_conversations.get("conversation"),
        raw_conversations.get("conversations"),
        _nested_dict(raw_conversations, "response").get("conversation"),
        _nested_dict(raw_conversations, "response").get("conversations"),
        _nested_dict(raw_conversations, "data").get("conversation"),
        _nested_dict(raw_conversations, "data").get("conversations"),
    ]
    entries: list[dict[str, Any]] = []
    for candidate in candidates:
        for item in _as_list(candidate):
            if isinstance(item, dict):
                entries.append(item)
        if entries:
            break
    return entries


def _conversation_ts(entry: dict[str, Any]) -> datetime | None:
    return _parse_ts(_first_value(
        entry.get("created_at"),
        entry.get("sent_at"),
        entry.get("received_at"),
        entry.get("timestamp"),
        entry.get("updated_at"),
    ))


def _conversation_direction(entry: dict[str, Any]) -> str | None:
    text = " ".join(
        str(value).strip().lower()
        for value in (
            entry.get("direction"),
            entry.get("type"),
            entry.get("message_type"),
            entry.get("sender_type"),
            entry.get("source"),
            entry.get("from"),
        )
        if value not in (None, "")
    )
    if any(token in text for token in ("inbound", "customer", "incoming", "received")):
        return "inbound"
    if any(token in text for token in ("outbound", "advisor", "shop", "sent", "employee")):
        return "outbound"

    for key in ("is_inbound", "from_customer", "customer_message"):
        if entry.get(key) is True:
            return "inbound"
    for key in ("is_outbound", "from_shop", "sent_by_shop"):
        if entry.get(key) is True:
            return "outbound"
    return None


def _auth_approved(auth: dict[str, Any]) -> bool:
    text = " ".join(
        str(value).strip().lower()
        for value in (
            auth.get("status"),
            auth.get("authorization_status"),
            auth.get("decision"),
        )
        if value not in (None, "")
    )
    return bool(
        auth.get("approved_at")
        or auth.get("authorized_at")
        or auth.get("approved") is True
        or "approved" in text
        or "authorized" in text
    )


def _derive_summary(
    raw_work_order: dict[str, Any],
    raw_repair_order: dict[str, Any] | None,
    raw_conversations: dict[str, Any],
    work_order_ok: bool = True,
    repair_order_ok: bool = True,
    conversations_ok: bool = True,
) -> dict[str, Any]:
    work_order = _work_order_payload(raw_work_order)
    repair_order = _repair_order_payload(raw_repair_order or {})
    dvi_items = _as_list(work_order.get("dvi_items"))

    parts_total = 0
    parts_arrived = 0
    sold_labor_hours = 0.0
    for item in dvi_items:
        if not isinstance(item, dict):
            continue
        for part in _as_list(item.get("parts")):
            if not isinstance(part, dict):
                continue
            parts_total += 1
            if _is_arrived(part):
                parts_arrived += 1
        for labor in _as_list(item.get("labor")):
            if isinstance(labor, dict):
                sold_labor_hours += _parse_float(labor.get("quantity"))

    authorizations = [
        item for item in _as_list(repair_order.get("authorizations"))
        if isinstance(item, dict)
    ]
    auth_sent_at = _first_value(repair_order.get("sent_at"), work_order.get("sent_at"))
    auth_viewed_at = _first_value(repair_order.get("viewed_at"), work_order.get("viewed_at"))
    auth_approved = False
    for auth in authorizations:
        auth_sent_at = _first_value(auth_sent_at, auth.get("sent_at"))
        auth_viewed_at = _first_value(auth_viewed_at, auth.get("viewed_at"))
        auth_approved = auth_approved or _auth_approved(auth)

    conversations = _conversation_entries(raw_conversations)
    latest_contact = None
    latest_contact_ts = None
    for entry in conversations:
        ts = _conversation_ts(entry)
        if ts is None:
            continue
        if latest_contact_ts is None or ts > latest_contact_ts:
            latest_contact = entry
            latest_contact_ts = ts

    return {
        "work_order_ok": bool(work_order_ok),
        "repair_order_ok": bool(repair_order_ok),
        "conversations_ok": bool(conversations_ok),
        "parts_total": parts_total,
        "parts_arrived": parts_arrived,
        "parts_outstanding": max(parts_total - parts_arrived, 0),
        "sold_labor_hours": round(sold_labor_hours, 2),
        "wo_emailed_on": work_order.get("emailed_on"),
        "wo_texted_on": work_order.get("texted_on"),
        "wo_viewed_on": work_order.get("viewed_on"),
        "auth_sent_at": auth_sent_at,
        "auth_viewed_at": auth_viewed_at,
        "auth_approved": bool(auth_approved),
        "last_contact_at": latest_contact_ts.isoformat() if latest_contact_ts else None,
        "last_contact_direction": (
            _conversation_direction(latest_contact)
            if isinstance(latest_contact, dict)
            else None
        ),
        "conversation_count": len(conversations),
    }


def _invoice_from_work_order(raw_work_order: dict[str, Any]) -> str:
    work_order = _work_order_payload(raw_work_order)
    return str(_first_value(
        work_order.get("invoice"),
        work_order.get("remote_ticket_id"),
        work_order.get("ticket_invoice"),
    ) or "").strip()


def enrich_ro(ro: str) -> dict[str, Any]:
    global FIRST_CONVERSATIONS_URL_LOGGED
    ro = str(ro).strip()
    if not ro:
        raise EnrichmentError("missing RO")

    raw_work_order = {}
    raw_repair_order = {}
    raw_conversations = {}
    work_order_ok = False
    repair_order_ok = False
    conversations_ok = False

    try:
        raw_work_order = _api_get(f"work_orders/{ro}")
        work_order_ok = True
    except Exception as error:
        print(f"Enrichment warning: work_orders failed for RO {ro}: {error}")

    invoice = _invoice_from_work_order(raw_work_order)
    if invoice:
        try:
            raw_repair_order = _api_get(f"repair_order/{invoice}")
            repair_order_ok = True
        except Exception as error:
            print(f"Enrichment warning: repair_order failed for RO {ro}: {error}")
    else:
        print(f"Enrichment note: no invoice found for RO {ro}; skipping repair_order")

    conversation_params = {"remote_ticket_id": ro}
    if not FIRST_CONVERSATIONS_URL_LOGGED:
        url = f"{AUTOFLOW_BASE_URL}/conversations?{urlencode(conversation_params)}"
        print(f"First conversations request URL: {url}")
        FIRST_CONVERSATIONS_URL_LOGGED = True
    try:
        raw_conversations = _api_get("conversations", conversation_params)
        conversations_ok = True
    except AutoFlowHTTPError as error:
        detail = str(error.detail or "").lower()
        if error.code == 404:
            print(f"Enrichment note: no conversations exist for RO {ro}: {error.detail}")
            raw_conversations = {}
            conversations_ok = False
        else:
            print(f"Enrichment warning: conversations failed for RO {ro}: {error}")
    except Exception as error:
        print(f"Enrichment warning: conversations failed for RO {ro}: {error}")

    summary = _derive_summary(
        raw_work_order,
        raw_repair_order,
        raw_conversations,
        work_order_ok=work_order_ok,
        repair_order_ok=repair_order_ok,
        conversations_ok=conversations_ok,
    )
    if conversations_ok and summary["conversation_count"] == 0:
        print(f"Enrichment note: no conversations returned for RO {ro}")
    payload = {
        "ro": ro,
        "fetched_at": _utc_now_iso(),
        "raw": {
            "work_order": raw_work_order,
            "repair_order": raw_repair_order,
            "conversations": raw_conversations,
        },
        "summary": summary,
    }
    _atomic_write_json(_cache_path(ro), payload)
    return payload


def _active_ros(shop_state: dict[str, Any]) -> list[str]:
    jobs = shop_state.get("jobs", []) if isinstance(shop_state, dict) else []
    seen = set()
    ros = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        status = str(job.get("workflow_status") or "").strip()
        if not status:
            continue
        status_key = status.lower()
        if status_key in {"close", "closed", "apache job"}:
            continue
        ro = _ro_id(job)
        if ro and ro not in seen:
            seen.add(ro)
            ros.append(ro)
    return ros


def enrich_all_active(
    shop_state: dict[str, Any],
    max_age_minutes: int = 15,
    delay_s: float = 0.15,
) -> dict[str, int]:
    counts = {"enriched": 0, "skipped": 0, "failed": 0}
    ros = _active_ros(shop_state)
    for index, ro in enumerate(ros):
        if _cache_is_fresh(ro, max_age_minutes):
            counts["skipped"] += 1
            if delay_s > 0 and index < len(ros) - 1:
                time.sleep(delay_s)
            continue
        try:
            enrich_ro(ro)
        except Exception as error:
            counts["failed"] += 1
            print(f"Enrichment failed to write cache for RO {ro}: {error}")
            if delay_s > 0 and index < len(ros) - 1:
                time.sleep(delay_s)
            continue
        counts["enriched"] += 1
        if delay_s > 0 and index < len(ros) - 1:
            time.sleep(delay_s)
    return counts


def _age_text(iso_value: Any) -> str:
    ts = _parse_ts(iso_value)
    if ts is None:
        return "unknown"
    minutes = int((_now_utc() - ts).total_seconds() // 60)
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h"
    return f"{hours // 24}d {hours % 24}h"


def _print_sample_rows(limit: int = 5) -> None:
    paths = sorted(
        ENRICHMENT_DIR.glob("*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for path in paths[:limit]:
        try:
            payload = _load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
        ro = payload.get("ro") or path.stem
        direction = summary.get("last_contact_direction") or "none"
        age = _age_text(summary.get("last_contact_at"))
        print(
            f"{ro} | "
            f"{summary.get('parts_arrived', 0)}/{summary.get('parts_total', 0)} parts | "
            f"auth(sent={summary.get('auth_sent_at')}, "
            f"viewed={summary.get('auth_viewed_at')}, "
            f"approved={summary.get('auth_approved')}) | "
            f"last_contact {direction} {age} | "
            f"ok(wo={summary.get('work_order_ok')}, "
            f"ro={summary.get('repair_order_ok')}, "
            f"conv={summary.get('conversations_ok')})"
        )


def _coverage_counts(ros: list[str]) -> dict[str, int]:
    counts = {"work_order_ok": 0, "repair_order_ok": 0, "conversations_ok": 0}
    for ro in ros:
        path = _cache_path(ro)
        try:
            payload = _load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
        for key in counts:
            if summary.get(key) is True:
                counts[key] += 1
    return counts


def main() -> int:
    global API_CALL_COUNT
    API_CALL_COUNT = 0
    if not SHOP_STATE_PATH.exists():
        print(f"shop_state missing: {SHOP_STATE_PATH}")
        return 1
    try:
        shop_state = _load_json(SHOP_STATE_PATH)
    except (OSError, json.JSONDecodeError) as error:
        print(f"Could not read shop_state: {error}")
        return 1

    counts = enrich_all_active(shop_state)
    ros = _active_ros(shop_state)
    coverage = _coverage_counts(ros)
    total = counts["enriched"] + counts["skipped"] + counts["failed"]
    print(
        "AutoFlow enrichment complete: "
        f"enriched={counts['enriched']} "
        f"skipped={counts['skipped']} "
        f"failed={counts['failed']} "
        f"active={total} "
        f"api_calls={API_CALL_COUNT} "
        f"coverage(work_order_ok={coverage['work_order_ok']}, "
        f"repair_order_ok={coverage['repair_order_ok']}, "
        f"conversations_ok={coverage['conversations_ok']})"
    )
    print("ROs used: " + (", ".join(ros) if ros else "none"))
    _print_sample_rows(limit=5)
    return 0 if counts["failed"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
