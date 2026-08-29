from __future__ import annotations

import hashlib
import hmac
import logging
import os
import subprocess
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, request

REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = REPO_ROOT / "logs"
LOG_FILE = LOG_DIR / "deploy.log"
RUNTIME_REPO = Path(r"C:\AI-RUNTIME\shop-observer-core")
TARGET_BRANCH = "ai-build-stabilization"

github_deploy_webhook = Blueprint("github_deploy_webhook", __name__)


def _configure_logger() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("github_deploy_webhook")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
            delay=True,
        )
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    return logger


LOGGER = _configure_logger()


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _valid_signature(raw_body: bytes, signature_header: str, secret: str) -> bool:
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def _safe_payload() -> dict[str, Any]:
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) else {}


@github_deploy_webhook.post("/webhooks/github-deploy")
def receive_github_deploy_webhook():
    timestamp = _utc_timestamp()
    raw_body = request.get_data()
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    signature = request.headers.get("X-Hub-Signature-256", "")

    if not secret:
        LOGGER.error("GitHub deploy webhook rejected: GITHUB_WEBHOOK_SECRET is not set")
        return jsonify({"status": "error", "message": "webhook secret not configured"}), 500

    if not _valid_signature(raw_body, signature, secret):
        LOGGER.warning("GitHub deploy webhook rejected: invalid signature")
        return jsonify({"status": "forbidden"}), 403

    event_type = request.headers.get("X-GitHub-Event", "")
    if event_type != "push":
        LOGGER.info("GitHub deploy webhook ignored: event_type=%s", event_type or "unknown")
        return jsonify({"status": "ignored"}), 200

    payload = _safe_payload()
    ref = str(payload.get("ref", "")).strip()
    if ref != f"refs/heads/{TARGET_BRANCH}":
        LOGGER.info("GitHub deploy webhook ignored: ref=%s", ref or "unknown")
        return jsonify({"status": "ignored"}), 200

    command = [
        "git",
        "-C",
        str(RUNTIME_REPO),
        "pull",
        "origin",
        TARGET_BRANCH,
    ]
    LOGGER.info("GitHub deploy webhook accepted: pulling origin/%s", TARGET_BRANCH)
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except Exception as exc:
        LOGGER.exception("GitHub deploy failed before git pull completed")
        return jsonify({"status": "error", "message": str(exc), "timestamp": timestamp}), 500

    if result.returncode != 0:
        LOGGER.error(
            "GitHub deploy failed: returncode=%s stdout=%r stderr=%r",
            result.returncode,
            result.stdout.strip(),
            result.stderr.strip(),
        )
        return jsonify({"status": "error", "message": "deploy failed", "timestamp": timestamp}), 500

    LOGGER.info(
        "GitHub deploy succeeded: stdout=%r stderr=%r",
        result.stdout.strip(),
        result.stderr.strip(),
    )
    return jsonify({"status": "deployed", "timestamp": timestamp}), 200
