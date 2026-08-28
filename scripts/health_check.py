from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "logs"
LOG_FILE = LOG_DIR / "health_check.log"
WEBHOOK_HEALTH_URL = "http://localhost:5055/health"
DASHBOARD_URL = "http://localhost:8080"
STATE_FILES = [
    ROOT / "state" / "board_state.json",
    ROOT / "state" / "shop_state.json",
    ROOT / "state" / "active_ros.json",
]
DEFAULT_FRESHNESS_MINUTES = 30
DEFAULT_TIMEOUT_SECONDS = 5


def _configure_logger() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("health_check")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        )
        logger.addHandler(handler)
    return logger


LOGGER = _configure_logger()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp() -> str:
    return _now().isoformat()


def _request_url(url: str, timeout_seconds: int) -> tuple[bool, str]:
    request = Request(url, headers={"Accept": "application/json,text/html"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            status_code = response.status
            payload = response.read(1024).decode("utf-8", errors="replace")
    except HTTPError as exc:
        return False, f"{url} returned HTTP {exc.code}"
    except URLError as exc:
        return False, f"{url} failed: {exc.reason}"
    except TimeoutError:
        return False, f"{url} timed out after {timeout_seconds}s"
    except Exception as exc:
        return False, f"{url} failed: {type(exc).__name__}: {exc}"

    if status_code < 200 or status_code >= 300:
        return False, f"{url} returned HTTP {status_code}"

    return True, payload


def _check_webhook(timeout_seconds: int) -> list[str]:
    ok, payload = _request_url(WEBHOOK_HEALTH_URL, timeout_seconds)
    if not ok:
        return [f"Webhook health check failed: {payload}"]

    try:
        data: Any = json.loads(payload)
    except json.JSONDecodeError:
        return [f"Webhook health check returned non-JSON response from {WEBHOOK_HEALTH_URL}"]

    if not isinstance(data, dict) or data.get("status") != "ok":
        return [f"Webhook health check returned unexpected payload: {data}"]

    return []


def _check_dashboard(timeout_seconds: int) -> list[str]:
    ok, payload = _request_url(DASHBOARD_URL, timeout_seconds)
    if not ok:
        return [f"Dashboard check failed: {payload}"]
    if not payload.strip():
        return [f"Dashboard check failed: {DASHBOARD_URL} returned an empty response"]
    return []


def _check_state_freshness(freshness_minutes: int) -> list[str]:
    failures: list[str] = []
    current_time = _now().timestamp()
    max_age_seconds = freshness_minutes * 60

    for state_file in STATE_FILES:
        if not state_file.exists():
            failures.append(f"State file missing: {state_file}")
            continue

        modified_at = state_file.stat().st_mtime
        age_seconds = current_time - modified_at
        age_minutes = round(age_seconds / 60, 1)
        if age_seconds > max_age_seconds:
            failures.append(
                f"State file stale: {state_file} age_minutes={age_minutes} "
                f"threshold_minutes={freshness_minutes}"
            )

    return failures


def run_health_check(freshness_minutes: int, timeout_seconds: int) -> list[str]:
    failures: list[str] = []
    failures.extend(_check_webhook(timeout_seconds))
    failures.extend(_check_dashboard(timeout_seconds))
    failures.extend(_check_state_freshness(freshness_minutes))
    return failures


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check Callahan AI local service health.")
    parser.add_argument(
        "--freshness-minutes",
        type=int,
        default=int(os.getenv("HEALTH_CHECK_FRESHNESS_MINUTES", DEFAULT_FRESHNESS_MINUTES)),
        help="Maximum allowed state file age in minutes. Defaults to 30.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=int(os.getenv("HEALTH_CHECK_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)),
        help="HTTP timeout for service checks. Defaults to 5.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    failures = run_health_check(args.freshness_minutes, args.timeout_seconds)

    if failures:
        for failure in failures:
            message = f"{_timestamp()} HEALTH CHECK FAILED: {failure}"
            LOGGER.error(message)
            print(message)
        return 1

    message = (
        f"{_timestamp()} HEALTH CHECK OK: services responding and state files "
        f"fresh within {args.freshness_minutes} minutes"
    )
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
