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
    DVIReview, DVIFlag, DVIReasonVehicleEntry,
    ReviewStatus, ReviewSource, TriggerEvent,
    FlagSeverity, FlagCategory, PhotoAccessStatus
)

logger = logging.getLogger(__name__)

# ─── Load Rules ──────────────────────────────────────────────────────────────

RULES_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "config", "cas_rules", "dvi_gate_rules.yaml"
)
CONCERN_RULES_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "config", "concern_checklists.json"
)

def _load_rules() -> dict:
    with open(RULES_PATH, "r") as f:
        return yaml.safe_load(f)

RULES = _load_rules()


def _load_concern_rules() -> dict:
    if not os.path.exists(CONCERN_RULES_PATH):
        return {}
    with open(CONCERN_RULES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


CONCERN_RULES = _load_concern_rules()


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _photo_count(item: dict) -> int:
    count = 0
    for key in ("item_images", "images"):
        value = item.get(key)
        if isinstance(value, list):
            count += len(value)
    value = item.get("item_picture")
    if isinstance(value, list):
        count += len(value)
    return count


def _video_count(item: dict) -> int:
    count = 0
    for key in ("videos", "item_videos", "video", "item_video"):
        value = item.get(key)
        if isinstance(value, list):
            count += len(value)
        elif value:
            count += 1
    return count


def _note_text(item: dict) -> str:
    return (item.get("item_notes") or "").strip()


def _substantive_text(value: str) -> bool:
    text = _normalize_for_match(value)
    if not text or len(text) < RULES["min_note_length"]:
        return False
    return not _is_vague(text)


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


def _as_list(value) -> list:
    return value if isinstance(value, list) else []


def _first_text_value(item: dict, *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _entry_type(value) -> str:
    text = str(value if value is not None else "").strip()
    if text == "0":
        return "Concern"
    if text == "1":
        return "Information"
    return text or "Unknown"


def _tagged_item_names(item: dict) -> list[str]:
    names = []
    for tagged in _as_list(item.get("tagged_items")):
        if not isinstance(tagged, dict):
            continue
        for key in ("name", "item_name", "label", "title"):
            value = tagged.get(key)
            if value:
                names.append(str(value))
    for key in ("tagged_item_names", "linked_item_names"):
        for value in _as_list(item.get(key)):
            if value:
                names.append(str(value))
    return names


def _tagged_item_ids(item: dict) -> list[str]:
    ids = []
    for tagged in _as_list(item.get("tagged_items")):
        if not isinstance(tagged, dict):
            continue
        for key in ("id", "item_id", "dvi_item_id", "inspection_item_id"):
            value = tagged.get(key)
            if value not in (None, ""):
                ids.append(str(value))
    for key in (
        "tagged_item_ids", "linked_item_ids", "dvi_item_ids",
        "reason_vehicle_is_here_id", "reason_id", "rvh_id"
    ):
        value = item.get(key)
        if isinstance(value, list):
            ids.extend(str(v) for v in value if v not in (None, ""))
        elif value not in (None, ""):
            ids.append(str(value))
    return ids


def _extract_rvh_entries(dvi_data: dict) -> list[DVIReasonVehicleEntry]:
    content = dvi_data.get("content", {}) if isinstance(dvi_data, dict) else {}
    entries = []
    for item in _as_list(content.get("reason_vehicle_is_here")):
        if not isinstance(item, dict):
            continue
        notes = _first_text_value(item, "details", "notes", "text", "description")
        entries.append(DVIReasonVehicleEntry(
            entry_type=_entry_type(item.get("type", item.get("entry_type", ""))),
            notes=notes,
            photo_count=_photo_count(item),
            video_count=_video_count(item),
            linked_item_names=_tagged_item_names(item),
            linked_item_ids=_tagged_item_ids(item),
        ))
    return entries


def _normalize_for_match(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").lower()).strip()


def _rvh_corpus(rvh_entries: list[DVIReasonVehicleEntry]) -> str:
    parts = []
    for entry in rvh_entries or []:
        parts.extend([
            entry.notes,
            " ".join(entry.linked_item_names),
            " ".join(entry.linked_item_ids),
        ])
    return _normalize_for_match(" ".join(parts))


def _item_identity_values(item: dict) -> set[str]:
    values = set()
    for key in ("item_name", "name", "item_id", "id", "dvi_item_id", "inspection_item_id"):
        value = item.get(key)
        if value not in (None, ""):
            values.add(_normalize_for_match(value))
    return {value for value in values if value}


def _meaningful_words(value: str) -> set[str]:
    stop = {
        "and", "the", "for", "with", "from", "this", "that", "when",
        "item", "check", "inspect", "inspection", "vehicle", "customer"
    }
    return {
        word for word in re.split(r"\W+", _normalize_for_match(value))
        if len(word) > 3 and word not in stop
    }


def _rvh_entry_covers_item(entry: DVIReasonVehicleEntry, item: dict) -> bool:
    item_values = _item_identity_values(item)
    linked_names = {_normalize_for_match(value) for value in entry.linked_item_names}
    linked_ids = {_normalize_for_match(value) for value in entry.linked_item_ids}
    if item_values & (linked_names | linked_ids):
        return True

    item_name = str(item.get("item_name") or item.get("name") or "")
    item_name_norm = _normalize_for_match(item_name)
    entry_text = _normalize_for_match(" ".join([entry.notes] + entry.linked_item_names))
    if item_name_norm and item_name_norm in entry_text:
        return True

    item_words = _meaningful_words(item_name)
    entry_words = _meaningful_words(entry_text)
    return bool(item_words and len(item_words & entry_words) >= min(2, len(item_words)))


def _rvh_coverage_for_item(item: dict, rvh_entries: list[DVIReasonVehicleEntry]) -> dict:
    coverage = {"note": False, "photo": False, "video": False, "entries": []}
    for entry in rvh_entries or []:
        if not _rvh_entry_covers_item(entry, item):
            continue
        coverage["entries"].append(entry)
        if _substantive_text(entry.notes):
            coverage["note"] = True
        if entry.photo_count > 0:
            coverage["photo"] = True
        if entry.video_count > 0:
            coverage["video"] = True
    return coverage


def _severity_from_config(value: str, default: str = FlagSeverity.CRITICAL) -> str:
    normalized = str(value or "").strip().lower()
    if normalized == FlagSeverity.IMPORTANT:
        return FlagSeverity.IMPORTANT
    if normalized == FlagSeverity.INFO:
        return FlagSeverity.INFO
    return default


def _concern_texts(dvi_data: dict) -> list:
    reasons = dvi_data.get("content", {}).get("reason_vehicle_is_here", [])
    concerns = []
    for reason in reasons:
        text = (reason.get("details") or "").strip()
        if text:
            concerns.append(text)
    return concerns


def _detect_concern_type(concern_text: str) -> Optional[str]:
    text = _normalize_for_match(concern_text)
    patterns = CONCERN_RULES.get("concern_patterns", {})
    for concern_type, keywords in patterns.items():
        for keyword in keywords:
            if _normalize_for_match(keyword) in text:
                return _canonical_concern_type(concern_type)
    return None


def _canonical_concern_type(concern_type: str) -> str:
    aliases = CONCERN_RULES.get("concern_aliases", {})
    return aliases.get(str(concern_type or ""), str(concern_type or ""))


def _item_corpus(all_items: list, rvh_entries: list[DVIReasonVehicleEntry] = None) -> str:
    parts = []
    for item in all_items:
        parts.extend([
            item.get("_section", ""),
            item.get("item_name", ""),
            _note_text(item),
        ])
    for entry in rvh_entries or []:
        parts.extend([
            entry.notes,
            " ".join(entry.linked_item_names),
        ])
    return _normalize_for_match(" ".join(parts))


def _evidence_present(evidence_key: str, all_items: list, rvh_entries: list[DVIReasonVehicleEntry] = None) -> bool:
    corpus = _item_corpus(all_items, rvh_entries)
    patterns = CONCERN_RULES.get("evidence_patterns", {}).get(evidence_key, [])
    regex_patterns = CONCERN_RULES.get("evidence_regex_patterns", {}).get(evidence_key, [])
    if evidence_key == "pad_or_rotor_measurement" and _has_measurement(corpus):
        return True
    for pattern in regex_patterns:
        try:
            if re.search(pattern, corpus, re.IGNORECASE):
                return True
        except re.error:
            logger.warning("Invalid evidence regex for %s: %s", evidence_key, pattern)
    for pattern in patterns:
        if _normalize_for_match(pattern) in corpus:
            return True
    return False


def _evidence_label(evidence_key: str) -> str:
    return CONCERN_RULES.get("evidence_labels", {}).get(
        evidence_key,
        str(evidence_key).replace("_", " "),
    )


def _concern_context_text(concern: str, all_items: list, rvh_entries: list[DVIReasonVehicleEntry] = None) -> str:
    return _normalize_for_match(f"{concern} {_item_corpus(all_items, rvh_entries)}")


def _matches_any(text: str, patterns: list) -> bool:
    normalized = _normalize_for_match(text)
    for pattern in patterns or []:
        if _normalize_for_match(pattern) in normalized:
            return True
    return False


def _has_real_diagnostic_data(text: str) -> bool:
    data_patterns = CONCERN_RULES.get("concern_context", {}).get("diagnostic_data_regex", [])
    for pattern in data_patterns:
        try:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        except re.error:
            logger.warning("Invalid diagnostic data regex: %s", pattern)
    return False


def _concern_context(concern: str, all_items: list, rvh_entries: list[DVIReasonVehicleEntry] = None) -> str:
    text = _concern_context_text(concern, all_items, rvh_entries)
    settings = CONCERN_RULES.get("concern_context", {})
    if _matches_any(text, settings.get("suppress_patterns", [])):
        return "suppressed"
    sold_or_performed = _matches_any(text, settings.get("diagnosed_patterns", []))
    has_data = _has_real_diagnostic_data(text)
    if sold_or_performed or has_data:
        return "diagnosed"
    if _matches_any(text, settings.get("courtesy_patterns", [])):
        return "courtesy"
    return "ambiguous"


def _checklist_tiers(raw_checklist) -> tuple[list, list]:
    if isinstance(raw_checklist, dict):
        required = raw_checklist.get("required", [])
        expected = raw_checklist.get("expected", [])
        return (
            required if isinstance(required, list) else [],
            expected if isinstance(expected, list) else [],
        )
    if isinstance(raw_checklist, list):
        return raw_checklist, []
    return [], []


def _missing_labels(missing: list) -> list:
    return [_evidence_label(evidence) for evidence in missing]


def _check_concern_completeness(dvi_data: dict, all_items: list, rvh_entries: list[DVIReasonVehicleEntry] = None) -> list:
    flags = []
    checklists = CONCERN_RULES.get("concern_checklists", {})
    settings = CONCERN_RULES.get("concern_completeness", {})
    section = settings.get("section", "Customer Concern")
    required_severity = _severity_from_config(settings.get("required_missing_severity"), FlagSeverity.CRITICAL)
    expected_severity = _severity_from_config(settings.get("expected_missing_severity"), FlagSeverity.IMPORTANT)
    ambiguous_severity = _severity_from_config(settings.get("ambiguous_severity"), FlagSeverity.IMPORTANT)

    for concern in _concern_texts(dvi_data):
        concern_type = _detect_concern_type(concern)
        if not concern_type or concern_type not in checklists:
            continue
        required, expected = _checklist_tiers(checklists[concern_type])
        required_missing = [
            evidence for evidence in required
            if not _evidence_present(evidence, all_items, rvh_entries)
        ]
        expected_missing = [
            evidence for evidence in expected
            if not _evidence_present(evidence, all_items, rvh_entries)
        ]
        if not required_missing and not expected_missing:
            continue
        context = _concern_context(concern, all_items, rvh_entries)
        if context == "suppressed":
            continue

        if required_missing and context == "diagnosed":
            missing_labels = _missing_labels(required_missing)
            flags.append(DVIFlag(
                severity=required_severity,
                category=FlagCategory.COMPLAINT_GAP,
                item_name=concern_type,
                section=section,
                tech_note=concern,
                photo_count=0,
                measurement_present=_has_real_diagnostic_data(_concern_context_text(concern, all_items, rvh_entries)),
                message=(
                    f"Diagnosed concern '{concern[:100]}' is missing required evidence: "
                    f"{', '.join(missing_labels)}."
                ),
                recommended_action=(
                    f"Document {', '.join(missing_labels)} for the "
                    f"{concern_type.replace('_', ' ')} concern before customer presentation."
                )
            ))
        elif required_missing and context == "ambiguous":
            missing_labels = _missing_labels(required_missing)
            flags.append(DVIFlag(
                severity=ambiguous_severity,
                category=FlagCategory.COMPLAINT_GAP,
                item_name=concern_type,
                section=section,
                tech_note=concern,
                photo_count=0,
                measurement_present=False,
                message=(
                    f"Concern '{concern[:100]}' is not clearly diagnosed or performed; "
                    f"required evidence would be {', '.join(missing_labels)} if diagnosis was completed."
                ),
                recommended_action=(
                    "Verify whether this was only a courtesy recommendation or a completed diagnosis."
                )
            ))

        if expected_missing and context == "diagnosed":
            missing_labels = _missing_labels(expected_missing)
            flags.append(DVIFlag(
                severity=expected_severity,
                category=FlagCategory.COMPLAINT_GAP,
                item_name=concern_type,
                section=section,
                tech_note=concern,
                photo_count=0,
                measurement_present=_has_real_diagnostic_data(_concern_context_text(concern, all_items, rvh_entries)),
                message=(
                    f"Concern '{concern[:100]}' is missing expected advisory context: "
                    f"{', '.join(missing_labels)}."
                ),
                recommended_action=(
                    f"Add advisory context if available: {', '.join(missing_labels)}."
                )
            ))
    return flags


def _check_contradictions(dvi_data: dict, all_items: list) -> list:
    flags = []
    settings = CONCERN_RULES.get("contradiction_detection", {})
    components = settings.get("components", {})
    configured_ok_values = settings.get("ok_status_values", [RULES["status_codes"]["pass"]])
    ok_values = {
        _normalize_for_match(value)
        for value in configured_ok_values
    }
    severity = _severity_from_config(settings.get("severity"), FlagSeverity.CRITICAL)
    concern_text = _normalize_for_match(" ".join(_concern_texts(dvi_data)))
    seen = set()

    for component_name, component_rules in components.items():
        concern_match = any(
            _normalize_for_match(keyword) in concern_text
            for keyword in component_rules.get("concern_keywords", [])
        )
        failure_match = any(
            _normalize_for_match(keyword) in concern_text
            for keyword in component_rules.get("failure_keywords", [])
        )
        if not (concern_match and failure_match):
            continue

        for item in all_items:
            status = _normalize_for_match(_item_status(item))
            if status not in ok_values:
                continue
            item_name = item.get("item_name", "Unknown")
            item_text = _normalize_for_match(item_name)
            item_match = any(
                _normalize_for_match(keyword) in item_text
                for keyword in component_rules.get("item_keywords", [])
            )
            if not item_match:
                continue
            key = (component_name, item_name)
            if key in seen:
                continue
            seen.add(key)
            flags.append(DVIFlag(
                severity=severity,
                category=FlagCategory.CONTRADICTION,
                item_name=item_name,
                section=item.get("_section", "Unknown"),
                tech_note=_note_text(item),
                photo_count=_photo_count(item),
                measurement_present=_has_measurement(_note_text(item)),
                message=(
                    f"Concern describes a {component_name.replace('_', ' ')} failure, "
                    f"but '{item_name}' is marked OK/green."
                ),
                recommended_action=(
                    f"Recheck '{item_name}' and document whether it confirms or "
                    f"rules out the customer concern."
                )
            ))
    return flags


# ─── Rule Checks ─────────────────────────────────────────────────────────────

def _check_missing_photo(item: dict, section: str, rvh_entries: list[DVIReasonVehicleEntry] = None) -> Optional[DVIFlag]:
    if not _is_concern(item):
        return None
    photos = _photo_count(item)
    rvh_coverage = _rvh_coverage_for_item(item, rvh_entries or [])
    if photos == 0 and (rvh_coverage["photo"] or rvh_coverage["video"]):
        return None
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


def _check_blank_note(item: dict, section: str, rvh_entries: list[DVIReasonVehicleEntry] = None) -> Optional[DVIFlag]:
    if not _is_concern(item):
        return None
    note = _note_text(item)
    rvh_coverage = _rvh_coverage_for_item(item, rvh_entries or [])
    if (not note or len(note) < RULES["min_note_length"]) and rvh_coverage["note"]:
        return None
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
    rvh_entries = _extract_rvh_entries(dvi_data)
    review.rvh_entries = rvh_entries

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
            _check_blank_note(item, section, rvh_entries),
            _check_missing_photo(item, section, rvh_entries),
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

    # Concern-aware advisory checks feed normal flags into the existing gate.
    flags.extend(_check_concern_completeness(dvi_data, all_items, rvh_entries))
    flags.extend(_check_contradictions(dvi_data, all_items))

    review.flags = flags
    review.finalize_status()

    logger.info(
        f"DVI Gate complete — RO {review.ro} — Status: {review.review_status} "
        f"— Flags: {review.flag_count}"
    )

    return review
