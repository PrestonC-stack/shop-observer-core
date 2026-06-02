"""
core/state/state_manager.py
Callahan Auto & Diesel — DVI Review State Manager

Handles saving and loading DVIReview objects to/from disk.
Simple JSON files per RO. No database needed for Sprint 1.
"""

import os
import json
import logging
from typing import Optional
from core.cas.dvi_schema import DVIReview

logger = logging.getLogger(__name__)

DVI_REVIEWS_DIR = os.path.join("state", "dvi_reviews")
TEKMETRIC_PACKETS_DIR = os.path.join("state", "tekmetric_packets")


def save_dvi_review(review: DVIReview) -> str:
    """Save DVIReview to state/dvi_reviews/{RO}.json. Returns file path."""
    os.makedirs(DVI_REVIEWS_DIR, exist_ok=True)
    path = os.path.join(DVI_REVIEWS_DIR, f"{review.ro}.json")
    with open(path, "w") as f:
        f.write(review.to_json())
    logger.info(f"DVI review saved: {path}")
    return path


def load_dvi_review(ro: str) -> Optional[DVIReview]:
    """Load DVIReview from disk. Returns None if not found."""
    path = os.path.join(DVI_REVIEWS_DIR, f"{ro}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        data = json.load(f)
    return DVIReview.from_dict(data)


def list_dvi_reviews() -> list:
    """Return list of all ROs with saved DVI reviews."""
    if not os.path.exists(DVI_REVIEWS_DIR):
        return []
    return [
        f.replace(".json", "")
        for f in os.listdir(DVI_REVIEWS_DIR)
        if f.endswith(".json") and not f.startswith("rework_slip")
    ]


def get_open_reworks() -> list:
    """Return all reviews where rework is required and not yet resolved."""
    open_reworks = []
    for ro in list_dvi_reviews():
        review = load_dvi_review(ro)
        if review and review.rework_required and not review.advisor_acknowledged:
            open_reworks.append(review)
    return open_reworks
