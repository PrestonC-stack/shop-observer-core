"""
TekMetric packet generator for DVI-reviewed repair orders.
"""

from __future__ import annotations

import json
import os
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
SHOP_STATE_PATH = REPO_ROOT / "state" / "shop_state.json"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = "claude-opus-4-6"


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


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


def generate_packet(ro):
    ro = str(ro).strip()
    review_path = DVI_REVIEWS_DIR / f"{ro}.json"
    if not review_path.exists():
        return {"error": "No DVI review found for this RO"}

    try:
        review = _load_json(review_path)
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
        packet["generated_at"] = datetime.utcnow().isoformat()
        output_path = DVI_REVIEWS_DIR / f"packet_{ro}.json"
        output_path.write_text(json.dumps(packet, indent=2, ensure_ascii=False), encoding="utf-8")
        return packet
    except (HTTPError, URLError, OSError, json.JSONDecodeError, ValueError) as error:
        return {"error": "Packet generation failed", "detail": str(error)}
