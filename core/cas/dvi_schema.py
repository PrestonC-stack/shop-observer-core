"""
core/cas/dvi_schema.py
Callahan Auto & Diesel — DVI Review Data Schema

Defines all data structures for DVI reviews, flags, and timeline entries.
No business logic here — just structure.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Optional
from datetime import datetime
import json


# ─── Review Status Values ────────────────────────────────────────────────────

class ReviewStatus:
    PASS = "PASS"
    REVIEW = "REVIEW"
    REWORK_REQUIRED = "REWORK_REQUIRED"
    ERROR = "ERROR"
    PENDING = "PENDING"


class ReviewSource:
    LOCAL_RULES = "local_rules"
    AI_REVIEW = "ai_review"
    MANUAL = "manual"


class TriggerEvent:
    DVI_SIGNOFF = "dvi_signoff"
    DVI_SIGNOFF_UPDATE = "dvi_signoff_update"
    MANUAL = "manual"
    TEST = "test"


class FlagSeverity:
    CRITICAL = "critical"
    IMPORTANT = "important"
    INFO = "info"


class FlagCategory:
    MISSING_PHOTO = "missing_photo"
    VAGUE_NOTE = "vague_note"
    BLANK_NOTE = "blank_note"
    MISSING_MEASUREMENT = "missing_measurement"
    CONTRADICTION = "contradiction"
    COMPLAINT_GAP = "complaint_gap"
    UNSUPPORTED_RECOMMENDATION = "unsupported_recommendation"
    NOT_INSPECTED = "not_inspected"
    SAFETY_INCOMPLETE = "safety_incomplete"


class PhotoAccessStatus:
    UNKNOWN = "unknown"
    ACCESSIBLE = "accessible"
    BLOCKED = "blocked"
    NOT_TESTED = "not_tested"


# ─── Flag ────────────────────────────────────────────────────────────────────

@dataclass
class DVIFlag:
    severity: str                    # critical | important | info
    category: str                    # FlagCategory value
    item_name: str                   # DVI item name e.g. "Rear Pads / Shoes"
    section: str                     # category name e.g. "Brakes"
    tech_note: str                   # raw tech note text
    photo_count: int                 # number of photos attached
    measurement_present: bool        # whether a measurement was detected in note
    message: str                     # human-readable flag description
    recommended_action: str          # what needs to happen to resolve this flag

    def to_dict(self):
        return asdict(self)

    def to_slip_line(self, index: int) -> str:
        """Format for printable rework slip."""
        return (
            f"{index}. {self.item_name} — {self.message}\n"
            f"   Needed: {self.recommended_action}"
        )


@dataclass
class DVIReasonVehicleEntry:
    entry_type: str                  # Concern | Information | raw AutoFlow type
    notes: str                       # RVH details/notes text
    photo_count: int = 0
    video_count: int = 0
    linked_item_names: List[str] = field(default_factory=list)
    linked_item_ids: List[str] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


# ─── DVI Review ──────────────────────────────────────────────────────────────

@dataclass
class DVIReview:
    ro: str
    customer: str
    vehicle: str
    advisor: str
    technician: str
    review_status: str = ReviewStatus.PENDING
    review_source: str = ReviewSource.LOCAL_RULES
    trigger_event: str = TriggerEvent.MANUAL
    dvi_pulled_at: str = ""
    dvi_api_attempts: int = 0
    photo_access_status: str = PhotoAccessStatus.NOT_TESTED
    primary_complaint: str = ""
    complaint_addressed: bool = False
    rvh_entries: List[DVIReasonVehicleEntry] = field(default_factory=list)
    flags: List[DVIFlag] = field(default_factory=list)
    rework_required: bool = False
    rework_slip_generated: bool = False
    advisor_acknowledged: bool = False
    advisor_override: bool = False
    advisor_override_by: str = ""
    advisor_override_reason: str = ""
    tech_correction_required: bool = False
    corrected_dvi_pulled: bool = False
    cleared_for_estimate: bool = False
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        now = datetime.utcnow().isoformat()
        if not self.created_at:
            self.created_at = now
        self.updated_at = now

    @property
    def critical_flags(self) -> List[DVIFlag]:
        return [f for f in self.flags if f.severity == FlagSeverity.CRITICAL]

    @property
    def important_flags(self) -> List[DVIFlag]:
        return [f for f in self.flags if f.severity == FlagSeverity.IMPORTANT]

    @property
    def flag_count(self) -> int:
        return len(self.flags)

    def finalize_status(self):
        """Set review_status based on flags after rules run."""
        self.updated_at = datetime.utcnow().isoformat()
        if not self.flags:
            self.review_status = ReviewStatus.PASS
            self.rework_required = False
            self.cleared_for_estimate = True
        elif any(f.severity == FlagSeverity.CRITICAL for f in self.flags):
            self.review_status = ReviewStatus.REWORK_REQUIRED
            self.rework_required = True
            self.tech_correction_required = True
            self.cleared_for_estimate = False
        else:
            self.review_status = ReviewStatus.REVIEW
            self.rework_required = False
            self.cleared_for_estimate = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["flags"] = [f.to_dict() for f in self.flags]
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> "DVIReview":
        flags = [DVIFlag(**f) for f in data.pop("flags", [])]
        rvh_entries = [
            DVIReasonVehicleEntry(**entry)
            for entry in data.pop("rvh_entries", [])
            if isinstance(entry, dict)
        ]
        review = cls(**data)
        review.flags = flags
        review.rvh_entries = rvh_entries
        return review


# ─── Timeline Entry ──────────────────────────────────────────────────────────

@dataclass
class TimelineEntry:
    ro: str
    event_type: str
    source: str                      # system | advisor | autoflow | ai
    actor: str                       # Drew | Mitch | Preston | Callie | AutoFlow
    summary: str
    details: dict = field(default_factory=dict)
    requires_action: bool = False
    resolved: bool = False
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    def to_jsonl(self) -> str:
        return json.dumps(self.to_dict())
