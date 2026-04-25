from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
MOCK_TEKMETRIC_PATH = REPO_ROOT / "inputs" / "mock_tekmetric_parts_activity.json"


def load_mock_tekmetric_activity(input_path: Path | None = None) -> dict[str, Any]:
    """Load placeholder Tekmetric-style parts/activity data from local mock input."""
    source_path = input_path or MOCK_TEKMETRIC_PATH
    with source_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def fetch_tekmetric_data() -> dict[str, Any]:
    """Placeholder connector entrypoint.

    This stays local-only for now and intentionally does not call a real API.
    """
    return load_mock_tekmetric_activity()
