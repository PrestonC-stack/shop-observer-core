"""
core/cas/dvi_gate.py
Callahan Auto & Diesel — Local DVI Rules Engine

Sprint 1: Pure local rules. No AI. No API calls.
Reads AutoFlow DVI JSON and produces a DVIReview with flags.

Rules priority:
  CRITICAL → REWORK_REQUIRED (missing photo, blank note on concern, safety incomplete)
  IMPORTANT → REVIEW (vague note, missing measurement, complaint gap)
  INFO → PASS with notes
"""

import os
import re
import json
import yaml
import logging
from datetime import datetime
from typing import Optional

from core.cas.dvi_schema import (
    DVIReview, DVIFlag,
    ReviewStatus, ReviewSource, TriggerEvent,
    FlagSeverity, FlagCategory, PhotoAccessStatus
)

logger = logging.getLogger(__name__)

# ─── Load Rules ──────────────────────────────────────────────────────────────

RULES_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "config", "cas_rules", "dvi_gate_rules.yaml"
)

def _load_rules() -> dict:
    with open(RULES_PATH, "r") as f:
        return yaml.safe_load(f)

RULES = _load_rules()


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _photo_count(item: dict) -> int:
    return len(item.get("item_images", []))


def _note_text(item: dict) -> str:
    return (item.get("item_notes") or "").strip()


def _item_status(item: dict) -> str:
    return (item.get("item_status") or "").strip()


def _is_concern(item: dict) -> bool:
    return _item_status(item) == RULES["status_codes"]["concern"]


def _is_not_inspected(item: dict) -> bool:
    return _item_status(item) == RULES["status_codes"]["not_inspected"]


def _is_vague(note: str) -> bool:
    """Check if a note matches known vague patterns."""
    if not note or len(note) < RULES["min_note_length"]:
        return True
    note_lower = note.lower().strip()
    for vague in RULES["vague_note_keywords"]:
        if note_lower == vague.lower():
            return True
        # Also flag if note is ONLY the vague keyword with nothing else
        if note_lower.startswith(vague.lower()) and len(note_lower) < len(vague) + 10:
            return True
    return False


def _has_measurement(note: str) -> bool:
    """Check if a note contains measurement data."""
    note_lower = note.lower()
    for keyword in RULES["measurement_keywords"]:
        if keyword.lower() in note_lower:
            return True
    # Also check for any standalone number (e.g. "3mm", "4/32", "12.5")
    if re.search(r'\d+(\.\d+)?(\s*(mm|psi|%|/32|cca|v))?', note_lower):
        return True
    return False


def _extract_primary_complaint(dvi_data: dict) -> str:
    """Pull the primary customer concern from DVI response."""
    reasons = dvi_data.get("content", {}).get("reason_vehicle_is_here", [])
    for reason in reasons:
        if reason.get("type") == 0:  # type 0 = customer concern
            return reason.get("details", "").strip()
    # Fallback: first reason regardless of type
    if reasons:
        return reasons[0].get("details", "").strip()
    return ""


def _complaint_addressed(complaint: str, dvi_items: list) -> bool:
    """
    Check whether the primary complaint is addressed somewhere in the DVI.
    Simple keyword overlap check — no AI needed for this.
    """
    if not complaint:
        return True  # can't evaluate what we don't know
    complaint_words = set(
        w.lower() for w in re.split(r'\W+', complaint) if len(w) > 3
    )
    if not complaint_words:
        return True

    for item in dvi_items:
        name = (item.get("item_name") or "").lower()
        note = _note_text(item).lower()
        combined = name + " " + note
        # If any meaningful complaint word appears in the item name or note, it's addressed
        overlap = complaint_words & set(re.split(r'\W+', combined))
        if len(overlap) >= 1:
            return True
    return False


def _get_section_for_item(item_name: str, dvi_data: dict) -> str:
    """Find which category/section an item belongs to."""
    content = dvi_data.get("content", {})
    for dvi in content.get("dvis", []):
        for cat in dvi.get("dvi_category", []):
            cat_name = cat.get("category_name", "")
            for dvi_item in cat.get("dvi_items", []):
                if dvi_item.get("item_name") == item_name:
                    return cat_name
    return "Unknown"


def _collect_all_dvi_items(dvi_data: dict) -> list:
    """Flatten all DVI items from all categories into one list with section info."""
    items = []
    content = dvi_data.get("content", {})
    for dvi in content.get("dvis", []):
        for cat in dvi.get("dvi_category", []):
            section = cat.get("category_name", "Unknown")
            for item in cat.get("dvi_items", []):
                item["_section"] = section
                items.append(item)
    return items


# ─── Rule Checks ─────────────────────────────────────────────────────────────

def _check_missing_photo(item: dict, section: str) -> Optional[DVIFlag]:
    if not _is_concern(item):
        return None
    photos = _photo_count(item)
    if photos == 0:
        return DVIFlag(
            severity=FlagSeverity.CRITICAL,
            category=FlagCategory.MISSING_PHOTO,
            item_name=item.get("item_name", "Unknown"),
            section=section,
            tech_note=_note_text(item),
            photo_count=0,
            measurement_present=_has_measurement(_note_text(item)),
            message="Item marked as concern but no photo attached.",
            recommended_action="Add at least one photo documenting this concern."
        )
    return None


def _check_blank_note(item: dict, section: str) -> Optional[DVIFlag]:
    if not _is_concern(item):
        return None
    note = _note_text(item)
    if not note or len(note) < RULES["min_note_length"]:
        return DVIFlag(
            severity=FlagSeverity.CRITICAL,
            category=FlagCategory.BLANK_NOTE,
            item_name=item.get("item_name", "Unknown"),
            section=section,
            tech_note=note,
            photo_count=_photo_count(item),
            measurement_present=False,
            message="Item marked as concern but note is blank or too short.",
            recommended_action="Add a specific note describing what was found."
        )
    return None


def _check_vague_note(item: dict, section: str) -> Optional[DVIFlag]:
    if not _is_concern(item):
        return None
    note = _note_text(item)
    if not note:
        return None  # already caught by blank_note check
    if _is_vague(note):
        return DVIFlag(
            severity=FlagSeverity.IMPORTANT,
            category=FlagCategory.VAGUE_NOTE,
            item_name=item.get("item_name", "Unknown"),
            section=section,
            tech_note=note,
            photo_count=_photo_count(item),
            measurement_present=_has_measurement(note),
            message=f"Note is too vague: '{note}'",
            recommended_action="Add location, severity, test result, or measurement."
        )
    return None


def _check_missing_measurement(item: dict, section: str) -> Optional[DVIFlag]:
    """Flag brake and tire concerns that lack measurements."""
    if not _is_concern(item):
        return None
    item_name = item.get("item_name", "")
    needs_measurement = (
        item_name in RULES["brake_items"] or
        item_name in RULES["tire_items"] or
        section in RULES["measurement_required_categories"]
    )
    if not needs_measurement:
        return None
    note = _note_text(item)
    if not _has_measurement(note):
        return DVIFlag(
            severity=FlagSeverity.CRITICAL,
            category=FlagCategory.MISSING_MEASUREMENT,
            item_name=item_name,
            section=section,
            tech_note=note,
            photo_count=_photo_count(item),
            measurement_present=False,
            message=f"{item_name} flagged as concern but no measurement recorded.",
            recommended_action="Add pad/rotor measurement (mm or 32nds) or tire tread depth."
        )
    return None


def _check_leak_detail(item: dict, section: str) -> Optional[DVIFlag]:
    """Leak items need location and severity."""
    if not _is_concern(item):
        return None
    item_name = item.get("item_name", "")
    if item_name not in RULES["leak_items"]:
        return None
    note = _note_text(item)
    photos = _photo_count(item)
    # Need either a photo or a location/severity description
    has_location = any(
        word in note.lower()
        for word in ["front", "rear", "left", "right", "top", "bottom",
                     "pan", "seal", "gasket", "line", "fitting", "hose",
                     "valve", "cover", "sump", "drain"]
    )
    if not has_location and photos == 0:
        return DVIFlag(
            severity=FlagSeverity.CRITICAL,
            category=FlagCategory.MISSING_PHOTO,
            item_name=item_name,
            section=section,
            tech_note=note,
            photo_count=photos,
            measurement_present=False,
            message="Leak reported but no photo and no location/severity in note.",
            recommended_action="Add photo and describe leak location and severity."
        )
    return None


def _check_not_inspected_safety(item: dict, section: str) -> Optional[DVIFlag]:
    """Safety items left blank should be flagged."""
    item_name = item.get("item_name", "")
    if item_name not in RULES["safety_items"]:
        return None
    if _is_not_inspected(item):
        return DVIFlag(
            severity=FlagSeverity.IMPORTANT,
            category=FlagCategory.NOT_INSPECTED,
            item_name=item_name,
            section=section,
            tech_note="",
            photo_count=0,
            measurement_present=False,
            message=f"Safety item '{item_name}' was not inspected.",
            recommended_action="Inspect and document this safety item before estimate is built."
        )
    return None


# ─── Main Gate Function ───────────────────────────────────────────────────────

def run_dvi_gate(
    dvi_data: dict,
    work_order_data: dict = None,
    ro: str = "",
    trigger_event: str = TriggerEvent.MANUAL
) -> DVIReview:
    """
    Main entry point. Run all local rules against AutoFlow DVI data.
    Returns a DVIReview with flags and final status.

    Args:
        dvi_data: Raw response from GET /api/v1/dvi/{RO}
        work_order_data: Raw response from GET /api/v1/work_orders/{RO} (optional)
        ro: RO number string
        trigger_event: What triggered this review
    """
    content = dvi_data.get("content", {})

    # Build basic review object
    customer_first = content.get("customer_firstname", "")
    customer_last = content.get("customer_lastname", "")
    year = content.get("year", "")
    make = content.get("make", "")
    model = content.get("model", "")

    review = DVIReview(
        ro=ro or str(content.get("invoice", "")),
        customer=f"{customer_first} {customer_last}".strip(),
        vehicle=f"{year} {make} {model}".strip(),
        advisor=content.get("service_advisor_name", ""),
        technician="",  # extracted below
        trigger_event=trigger_event,
        dvi_pulled_at=datetime.utcnow().isoformat(),
        dvi_api_attempts=1,
        photo_access_status=PhotoAccessStatus.ACCESSIBLE,  # confirmed in test
    )

    # Extract technician from first completed DVI
    dvis = content.get("dvis", [])
    if dvis:
        review.technician = dvis[0].get("completed_by", "")

    # Extract primary complaint
    primary_complaint = _extract_primary_complaint(dvi_data)
    review.primary_complaint = primary_complaint

    # Collect all DVI items
    all_items = _collect_all_dvi_items(dvi_data)

    if not all_items:
        review.review_status = ReviewStatus.REVIEW
        review.flags.append(DVIFlag(
            severity=FlagSeverity.IMPORTANT,
            category=FlagCategory.COMPLAINT_GAP,
            item_name="DVI",
            section="General",
            tech_note="",
            photo_count=0,
            measurement_present=False,
            message="No DVI category items found in response. DVI may be incomplete.",
            recommended_action="Verify DVI was completed and signed off in AutoFlow."
        ))
        review.finalize_status()
        return review

    # Run all rule checks on each item
    flags = []
    for item in all_items:
        section = item.get("_section", "Unknown")

        checks = [
            _check_blank_note(item, section),
            _check_missing_photo(item, section),
            _check_vague_note(item, section),
            _check_missing_measurement(item, section),
            _check_leak_detail(item, section),
            _check_not_inspected_safety(item, section),
        ]

        for flag in checks:
            if flag is not None:
                flags.append(flag)

    # Check primary complaint coverage
    review.complaint_addressed = _complaint_addressed(primary_complaint, all_items)
    if primary_complaint and not review.complaint_addressed:
        flags.append(DVIFlag(
            severity=FlagSeverity.IMPORTANT,
            category=FlagCategory.COMPLAINT_GAP,
            item_name="Primary Complaint",
            section="General",
            tech_note=primary_complaint,
            photo_count=0,
            measurement_present=False,
            message=f"Primary complaint not clearly addressed in DVI findings: '{primary_complaint[:100]}'",
            recommended_action="Verify tech addressed the primary customer complaint and documented findings."
        ))

    review.flags = flags
    review.finalize_status()

    logger.info(
        f"DVI Gate complete — RO {review.ro} — Status: {review.review_status} "
        f"— Flags: {review.flag_count}"
    )

    return review
