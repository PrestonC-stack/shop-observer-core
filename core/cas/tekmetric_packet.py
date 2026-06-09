"""
TekMetric packet generator for DVI-reviewed repair orders.
"""

from __future__ import annotations

import json
import os
import base64
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - runtime convenience if dotenv is unavailable
    def load_dotenv(*_args, **_kwargs):
        return False


REPO_ROOT = Path(__file__).resolve().parents[2]
DVI_REVIEWS_DIR = REPO_ROOT / "state" / "dvi_reviews"
CACHE_DIR = DVI_REVIEWS_DIR
SHOP_STATE_PATH = REPO_ROOT / "state" / "shop_state.json"
JOB_HISTORY_DIR = REPO_ROOT / "state" / "job_history"
API_COSTS_PATH = REPO_ROOT / "data" / "api_costs" / "api_costs.jsonl"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = "claude-opus-4-6"


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def packet_cache_path(ro: str) -> Path:
    return CACHE_DIR / f"{str(ro).strip()}_packet.json"


def format_ts(iso_string):
    if not iso_string:
        return ""
    try:
        dt = datetime.fromisoformat(str(iso_string).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return str(iso_string)
    day = str(dt.day)
    hour = dt.hour % 12 or 12
    minute = dt.strftime("%M")
    ampm = "AM" if dt.hour < 12 else "PM"
    month = dt.strftime("%b")
    year = dt.year
    weekday = dt.strftime("%a")
    return f"{weekday} {month} {day}, {year} · {hour}:{minute} {ampm}"


def fetch_dvi_from_autoflow(ro):
    try:
        import requests
        from dotenv import load_dotenv as _load_dotenv
    except ImportError:
        return None

    _load_dotenv(REPO_ROOT / ".env")
    api_key = os.getenv("AUTOFLOW_API_KEY")
    api_password = os.getenv("AUTOFLOW_API_PASSWORD")
    if not api_key or not api_password:
        return None

    token = base64.b64encode(f"{api_key}:{api_password}".encode()).decode()
    url = f"https://callahanautomotive.autotext.me/api/v1/dvi/{str(ro).strip()}"
    headers = {"Authorization": f"Basic {token}"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
    except requests.RequestException:
        return None
    if response.status_code == 200:
        try:
            return response.json()
        except ValueError:
            return None
    return None


def _find_job(shop_state: dict, ro: str) -> dict:
    jobs = shop_state.get("jobs", []) if isinstance(shop_state, dict) else []
    for job in jobs:
        if isinstance(job, dict) and str(job.get("ro") or "").strip() == ro:
            return job
    return {}


def _job_value(job: dict, *keys: str) -> str:
    for key in keys:
        value = job.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _extract_response_text(response_payload: dict) -> str:
    content = response_payload.get("content", [])
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        return "\n".join(parts).strip()
    return str(content).strip()


def _parse_packet_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    return json.loads(cleaned)


def _save_job_history_packet(ro: str, packet: dict, timestamp: str) -> None:
    try:
        history_dir = JOB_HISTORY_DIR / ro
        history_dir.mkdir(parents=True, exist_ok=True)
        history_path = history_dir / f"packet_{timestamp}.json"
        history_path.write_text(json.dumps(packet, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as error:
        print(f"Packet history save failed for RO {ro}: {error}")


def _append_api_cost_log(entry: dict) -> None:
    try:
        API_COSTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with API_COSTS_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as error:
        print(f"Packet API cost log failed: {error}")


def _safe_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def log_packet_cache_hit(ro: str, requested_by: str = "system") -> None:
    _append_api_cost_log({
        "timestamp": datetime.utcnow().isoformat(),
        "action": "packet_cache_hit",
        "trigger": "cache_hit",
        "requested_by": requested_by,
        "ro": str(ro),
        "input_tokens": 0,
        "output_tokens": 0,
        "estimated_cost_usd": 0.0,
        "cached": True,
    })


def _dvi_item_count(review: dict) -> int:
    if not isinstance(review, dict):
        return 0
    for key in ("items", "dvi_items", "findings", "inspection_items"):
        value = review.get(key)
        if isinstance(value, list):
            return len(value)
    payload = review.get("payload")
    if isinstance(payload, dict):
        for key in ("items", "dvi_items", "findings", "inspection_items"):
            value = payload.get(key)
            if isinstance(value, list):
                return len(value)
    return 0


def _build_prompt(ro: str, review: dict, job: dict) -> str:
    customer = _job_value(job, "customer_name", "customer") or str(review.get("customer", ""))
    vehicle = _job_value(job, "vehicle") or str(review.get("vehicle", ""))
    mileage = _job_value(job, "mileage", "odometer")
    mileage = mileage or "Not recorded"
    month = datetime.now().strftime("%B %Y")
    dvi_findings_json = json.dumps(review, indent=2, ensure_ascii=False)

    return f"""
You are a shop management AI for Callahan Auto & Diesel in Mesa, Arizona.
Generate a TekMetric Packet for the following repair order.

VEHICLE INFO:
Customer: {customer}
Vehicle: {vehicle}
Mileage: {mileage}
RO: {ro}
Current Month: {month}
Location: Mesa, Arizona (hot desert climate)

DVI FINDINGS:
{dvi_findings_json}

Generate a structured packet in valid JSON format with this exact structure:

{{
  "ro": "{ro}",
  "customer": "{customer}",
  "vehicle": "{vehicle}",
  "mileage": "{mileage}",
  "generated_at": "<ISO timestamp>",
  "advisor_gate": "<2-3 sentence advisor mental gate — what to ask customer before deferring maintenance. Consider: towing use if truck, Arizona heat season warnings, upcoming trip risk. Be specific to this vehicle and findings.>",
  "drag_order": [
    "CONCERN 1 - <job name>",
    "SAFETY 1 - <job name>",
    "MAINTENANCE 1 - <job name>",
    "POSSIBLE ADD-ON - <job name>"
  ],
  "jobs": [
    {{
      "category": "CONCERN",
      "number": 1,
      "title": "CONCERN 1 - <descriptive job name>",
      "labor_items": [
        "R&R <specific operation> — <vehicle specific details>",
        "⚠ Don't forget: <common missed add-on labor>"
      ],
      "parts_items": [
        "<Brand> <Part Name> — <Part Number if known>",
        "<Part> x<qty> — <note if applicable>"
      ],
      "note_justification": "<2-4 sentences in plain language justifying this repair. Reference DVI findings. No fear selling. Customer-facing.>",
      "note_conditional": "<1-2 sentences of if/then conditional language if applicable. Leave empty string if none.>",
      "is_possible_addon": false
    }}
  ]
}}

CATEGORIZATION RULES:
- CONCERN: Items that directly address why the customer brought the vehicle in
- SAFETY: Items that will leave the customer stranded, cause breakdown, or create danger. Brakes, fluid leaks under load, electrical safety, fuel system integrity.
- MAINTENANCE: Items that are currently working but degraded. Schedule for future. Include season logic — Arizona heat means coolant/AC critical before March/April.
- POSSIBLE ADD-ON: Items that cannot be confirmed until disassembly. Mark is_possible_addon: true. These are advisor radar only, never presented to customer as confirmed repairs.

VEHICLE CONTEXT RULES:
- If diesel engine: flag 6.0L known failure points (EGR, oil cooler, head gaskets) as possible add-ons
- If truck (F250, F350, Ram 2500, etc): ask about towing in advisor gate
- If Arizona + coolant finding + month October through February: flag as critical before summer
- If vehicle has been sitting (storage): elevate fluid services, prioritize getting running first

LABOR REMINDER RULES (always check these for applicable jobs):
- Brakes → remind about brake fluid flush as separate job
- Front suspension/struts → remind about alignment
- AC work → remind about freon evacuation and recharge
- Timing belt/chain → remind about water pump if accessible
- Transmission service → confirm transmission model for correct fluid spec
- Diesel fuel system → verify wiring corrections, check for secondary fuel system components

ORDERING RULES:
- All CONCERN jobs first (numbered 1, 2, 3...)
- All SAFETY jobs next (numbered 1, 2, 3...)
- All MAINTENANCE jobs next (numbered 1, 2, 3...)
- POSSIBLE ADD-ON jobs last
- Within each category order by severity/urgency

Return ONLY valid JSON. No markdown. No explanation. No code blocks.
""".strip()


def generate_packet(ro, force_refresh=False, requested_by="unknown"):
    ro = str(ro).strip()
    review_path = DVI_REVIEWS_DIR / f"{ro}.json"
    if not review_path.exists():
        return {"error": "No DVI review found for this RO"}

    try:
        local_review = _load_json(review_path)
        fresh_review = fetch_dvi_from_autoflow(ro) if force_refresh else None
        review = fresh_review if isinstance(fresh_review, dict) else local_review
        dvi_pulled_at = datetime.utcnow().isoformat()
        shop_state = _load_json(SHOP_STATE_PATH) if SHOP_STATE_PATH.exists() else {}
        job = _find_job(shop_state, ro)
        prompt = _build_prompt(ro, review, job)

        load_dotenv(REPO_ROOT / ".env")
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return {"error": "Packet generation failed", "detail": "ANTHROPIC_API_KEY is not set"}

        request_body = {
            "model": ANTHROPIC_MODEL,
            "max_tokens": 4000,
            "messages": [{"role": "user", "content": prompt}],
        }
        request = Request(
            ANTHROPIC_URL,
            data=json.dumps(request_body).encode("utf-8"),
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            method="POST",
        )

        with urlopen(request, timeout=90) as response:
            response_payload = json.loads(response.read().decode("utf-8"))

        packet = _parse_packet_json(_extract_response_text(response_payload))
        generated_at = datetime.utcnow().isoformat()
        packet["generated_at"] = generated_at
        packet["dvi_pulled_at"] = dvi_pulled_at
        packet["dvi_item_count"] = _dvi_item_count(review)
        output_path = DVI_REVIEWS_DIR / f"packet_{ro}.json"
        output_path.write_text(json.dumps(packet, indent=2, ensure_ascii=False), encoding="utf-8")
        _save_job_history_packet(ro, packet, datetime.utcnow().strftime("%Y%m%d_%H%M%S"))

        usage = response_payload.get("usage", {}) if isinstance(response_payload.get("usage"), dict) else {}
        input_tokens = _safe_int(usage.get("input_tokens"))
        output_tokens = _safe_int(usage.get("output_tokens"))
        estimated_cost = (input_tokens * 0.000003) + (output_tokens * 0.000015)
        trigger = "regenerate" if force_refresh else "initial"
        packet["api_cost_usd"] = estimated_cost
        packet["trigger"] = trigger
        packet["requested_by"] = requested_by
        _append_api_cost_log({
            "timestamp": generated_at,
            "action": "packet_generate",
            "trigger": trigger,
            "requested_by": requested_by,
            "ro": ro,
            "customer": str(packet.get("customer") or ""),
            "vehicle": str(packet.get("vehicle") or ""),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_usd": estimated_cost,
            "cached": False,
        })
        return packet
    except (HTTPError, URLError, OSError, json.JSONDecodeError, ValueError) as error:
        return {"error": "Packet generation failed", "detail": str(error)}


def build_packet(ro, force_refresh=False, requested_by="unknown"):
    return generate_packet(ro, force_refresh=force_refresh, requested_by=requested_by)
