from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SCREENSHOT_INPUT_DIR = REPO_ROOT / "inputs" / "techflow_screenshots"
DRAFT_OUTPUT_DIR = REPO_ROOT / "outputs" / "techflow_extraction_drafts"

TARGET_FIELDS = [
    "ro_number",
    "technician_name",
    "vehicle",
    "customer",
    "job_name",
    "workflow_status",
    "percent_complete",
    "labor_sold_hours",
    "labor_clocked_hours",
    "labor_remaining_hours",
    "priority_position",
]

FIELD_ALIASES = {
    "ro_number": ["ro", "ro_number", "repair_order", "repair order"],
    "technician_name": ["technician", "tech", "technician_name"],
    "vehicle": ["vehicle"],
    "customer": ["customer"],
    "job_name": ["job", "job_name", "operation"],
    "workflow_status": ["status", "workflow_status"],
    "percent_complete": ["percent_complete", "complete", "% complete"],
    "labor_sold_hours": ["sold_hours", "labor_sold_hours", "sold"],
    "labor_clocked_hours": ["clocked_hours", "labor_clocked_hours", "clocked"],
    "labor_remaining_hours": ["remaining_hours", "labor_remaining_hours", "remaining"],
    "priority_position": ["priority", "priority_position", "position"],
}


def _empty_extraction() -> dict[str, Any]:
    return {field: None for field in TARGET_FIELDS}


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _coerce_number(value: str) -> float | int | None:
    match = re.search(r"-?\d+(?:\.\d+)?", value)
    if not match:
        return None
    number = float(match.group(0))
    if number.is_integer():
        return int(number)
    return number


def _assign_field(extracted: dict[str, Any], key: str, value: str) -> bool:
    normalized_key = _normalize_key(key)
    for field, aliases in FIELD_ALIASES.items():
        if normalized_key in {_normalize_key(alias) for alias in aliases}:
            if field in {
                "percent_complete",
                "labor_sold_hours",
                "labor_clocked_hours",
                "labor_remaining_hours",
                "priority_position",
            }:
                extracted[field] = _coerce_number(value)
            else:
                extracted[field] = value.strip() or None
            return True
    return False


def extract_from_ocr_text(
    ocr_text: str, source_file: str | None = None
) -> dict[str, Any]:
    """Build a review-only TechFlow draft from structured OCR/vision text."""
    extracted = _empty_extraction()
    flags: list[str] = ["review_required"]

    for raw_line in ocr_text.splitlines():
        line = raw_line.strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        _assign_field(extracted, key, value)

    populated_fields = sum(1 for value in extracted.values() if value not in (None, ""))
    confidence_score = round(populated_fields / len(TARGET_FIELDS), 2)

    if confidence_score >= 0.8:
        flags.append("high_confidence")
    elif confidence_score >= 0.5:
        flags.append("medium_confidence")
    else:
        flags.append("low_confidence")

    missing_fields = [
        field for field, value in extracted.items() if value in (None, "")
    ]
    if missing_fields:
        flags.append("missing_fields:" + ",".join(missing_fields))

    return {
        "schema_version": "techflow_screenshot_draft_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_label": "techflow_screenshot",
        "source_file": source_file,
        "extracted": extracted,
        "confidence_score": confidence_score,
        "extraction_flags": flags,
        "review_status": "needs_review",
        "raw_ocr_text": ocr_text,
    }


def extract_from_file(input_path: Path) -> dict[str, Any]:
    """Accept OCR text now; mark image-only files as pending future OCR."""
    if input_path.suffix.lower() in {".txt", ".md"}:
        return extract_from_ocr_text(
            input_path.read_text(encoding="utf-8"),
            source_file=str(input_path),
        )

    draft = {
        "schema_version": "techflow_screenshot_draft_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_label": "techflow_screenshot",
        "source_file": str(input_path),
        "extracted": _empty_extraction(),
        "confidence_score": 0.0,
        "extraction_flags": [
            "review_required",
            "low_confidence",
            "ocr_not_available",
            "image_pending_ocr_or_vision",
        ],
        "review_status": "needs_review",
        "raw_ocr_text": "",
    }
    return draft


def write_draft(draft: dict[str, Any], output_dir: Path = DRAFT_OUTPUT_DIR) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    source_name = Path(draft.get("source_file") or "techflow").stem
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"{source_name}_{timestamp}.json"
    output_path.write_text(json.dumps(draft, indent=2), encoding="utf-8")
    return output_path


def extract_folder(
    input_dir: Path = SCREENSHOT_INPUT_DIR,
    output_dir: Path = DRAFT_OUTPUT_DIR,
) -> list[Path]:
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_paths: list[Path] = []

    for input_path in sorted(input_dir.iterdir()):
        if input_path.name.startswith(".") or not input_path.is_file():
            continue
        draft = extract_from_file(input_path)
        output_paths.append(write_draft(draft, output_dir))

    return output_paths


def main() -> None:
    output_paths = extract_folder()
    if not output_paths:
        print("No TechFlow screenshot or OCR text files found.")
        print(f"Place files in: {SCREENSHOT_INPUT_DIR}")
        return

    print("TECHFLOW DRAFT EXTRACTIONS")
    for output_path in output_paths:
        print(f"- {output_path}")


if __name__ == "__main__":
    main()
