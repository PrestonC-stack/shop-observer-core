"""
Print-ready TekMetric packet page.
"""

from __future__ import annotations

import html
import json
import os
import re
import socket
import base64
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import Response, jsonify, redirect, request, url_for

from core.cas.tekmetric_packet import (
    ANTHROPIC_MODEL,
    ANTHROPIC_URL,
    PHOTO_FINDINGS_PLACEHOLDER,
    _extract_response_text,
    build_packet,
    clean_ai_response_text,
    compare_packet_to_current_dvi,
    fetch_dvi_from_autoflow,
    format_ts,
    log_packet_cache_hit,
    packet_cache_path,
)

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - runtime convenience if dotenv is unavailable
    def load_dotenv(*_args, **_kwargs):
        return False


REPO_ROOT = Path(__file__).resolve().parents[1]
DVI_REVIEWS_DIR = REPO_ROOT / "state" / "dvi_reviews"
JOB_HISTORY_DIR = REPO_ROOT / "state" / "job_history"
BOARD_STATE_PATH = REPO_ROOT / "state" / "board_state.json"
SHOP_STATE_PATH = REPO_ROOT / "state" / "shop_state.json"
API_COSTS_PATH = REPO_ROOT / "data" / "api_costs" / "api_costs.jsonl"
PACKET_MAX_AGE = timedelta(hours=4)
PHOTO_ANALYSIS_COST = 0.03
COMPLETED_HISTORY_STATUSES = {
    "advisor finalize ro",
    "close",
    "closed",
    "complete",
    "completed",
    "done",
    "finished",
    "ready",
}


def _escape(value) -> str:
    return html.escape(str(value or ""), quote=True)


def _packet_path(ro: str) -> Path:
    return packet_cache_path(ro)


def _legacy_packet_path(ro: str) -> Path:
    return DVI_REVIEWS_DIR / f"packet_{ro}.json"


def _is_fresh(path: Path) -> bool:
    if not path.exists():
        return False
    modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return datetime.now(timezone.utc) - modified < PACKET_MAX_AGE


def _load_packet(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _load_cache(ro: str) -> dict:
    path = _packet_path(ro)
    if not path.exists():
        return {}
    try:
        data = _load_packet(path)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_cache(ro: str, cache: dict) -> None:
    path = _packet_path(ro)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")


def _packet_timestamp_from_filename(path: Path) -> str:
    match = re.search(r"packet_(\d{8}_\d{6})\.json$", path.name)
    if not match:
        return ""
    try:
        return datetime.strptime(match.group(1), "%Y%m%d_%H%M%S").isoformat()
    except ValueError:
        return ""


def _packet_generated_at(packet: dict, fallback_path: Path | None = None) -> str:
    if isinstance(packet, dict):
        for key in ("generated_at", "regenerated_at", "dvi_pulled_at"):
            value = str(packet.get(key) or "").strip()
            if value:
                return value
    if fallback_path:
        from_name = _packet_timestamp_from_filename(fallback_path)
        if from_name:
            return from_name
        try:
            return datetime.fromtimestamp(fallback_path.stat().st_mtime, tz=timezone.utc).isoformat()
        except OSError:
            return ""
    return ""


def _latest_generation_event(cache: dict) -> dict:
    events = cache.get("generation_log") if isinstance(cache.get("generation_log"), list) else []
    latest = {}
    for item in events:
        if not isinstance(item, dict):
            continue
        timestamp = str(item.get("timestamp") or "").strip()
        if timestamp and timestamp >= str(latest.get("timestamp") or ""):
            latest = item
    return latest


def _history_packet_candidates(ro: str) -> list[dict]:
    ro_text = str(ro or "").strip()
    if not ro_text:
        return []
    candidates = []

    history_dir = JOB_HISTORY_DIR / ro_text
    if history_dir.exists():
        for path in history_dir.glob("packet_*.json"):
            packet = _safe_load_json(path)
            if packet:
                generated_at = _packet_generated_at(packet, path)
                candidates.append({
                    "ro": ro_text,
                    "packet": packet,
                    "cache": {},
                    "packet_html": "",
                    "generated_at": generated_at,
                    "source": "job_history",
                    "path": path,
                    "label": f"Permanent history file: {path.name}",
                })

    cache_path = _packet_path(ro_text)
    cache = _load_cache(ro_text)
    if cache:
        packet = cache.get("packet") if isinstance(cache.get("packet"), dict) else {}
        latest_event = _latest_generation_event(cache)
        generated_at = str(latest_event.get("timestamp") or cache.get("generated_at") or _packet_generated_at(packet, cache_path))
        candidates.append({
            "ro": ro_text,
            "packet": packet,
            "cache": cache,
            "packet_html": str(cache.get("packet_html") or ""),
            "generated_at": generated_at,
            "source": "packet_cache",
            "path": cache_path,
            "label": "Current packet cache",
        })

    legacy_path = _legacy_packet_path(ro_text)
    legacy = _safe_load_json(legacy_path)
    if legacy:
        generated_at = _packet_generated_at(legacy, legacy_path)
        candidates.append({
            "ro": ro_text,
            "packet": legacy,
            "cache": {},
            "packet_html": "",
            "generated_at": generated_at,
            "source": "legacy_packet",
            "path": legacy_path,
            "label": "Legacy packet JSON",
        })

    return candidates


def _latest_stored_packet(ro: str) -> dict:
    candidates = _history_packet_candidates(ro)
    if not candidates:
        return {}
    return sorted(candidates, key=lambda item: str(item.get("generated_at") or ""), reverse=True)[0]


def _iter_state_jobs() -> list[dict]:
    jobs = []
    for path in (BOARD_STATE_PATH, SHOP_STATE_PATH):
        state = _safe_load_json(path)
        for job in state.get("jobs", []) if isinstance(state.get("jobs"), list) else []:
            if isinstance(job, dict):
                jobs.append(job)
    return jobs


def _completed_state_jobs_by_ro() -> dict[str, dict]:
    rows = {}
    for job in _iter_state_jobs():
        ro = str(job.get("ro") or "").strip()
        if not ro:
            continue
        status = str(job.get("workflow_status") or job.get("status") or "").strip().lower().replace("_", " ")
        if status in COMPLETED_HISTORY_STATUSES:
            rows[ro] = job
    return rows


def _packet_history_rows() -> list[dict]:
    rows: dict[str, dict] = {}

    if JOB_HISTORY_DIR.exists():
        for ro_dir in JOB_HISTORY_DIR.iterdir():
            if ro_dir.is_dir():
                ro = ro_dir.name.strip()
                latest = _latest_stored_packet(ro)
                if latest:
                    packet = latest.get("packet") if isinstance(latest.get("packet"), dict) else {}
                    rows[ro] = {
                        "ro": ro,
                        "customer": packet.get("customer", ""),
                        "vehicle": packet.get("vehicle", ""),
                        "status": "closed",
                        "has_packet": True,
                        "generated_at": latest.get("generated_at", ""),
                        "source": latest.get("label", latest.get("source", "")),
                    }

    for path in DVI_REVIEWS_DIR.glob("*_packet.json"):
        ro = path.name[:-12].strip()
        if ro and ro not in rows:
            latest = _latest_stored_packet(ro)
            if latest:
                packet = latest.get("packet") if isinstance(latest.get("packet"), dict) else {}
                rows[ro] = {
                    "ro": ro,
                    "customer": packet.get("customer", ""),
                    "vehicle": packet.get("vehicle", ""),
                    "status": "packet cached",
                    "has_packet": True,
                    "generated_at": latest.get("generated_at", ""),
                    "source": latest.get("label", latest.get("source", "")),
                }

    for path in DVI_REVIEWS_DIR.glob("packet_*.json"):
        ro = path.stem.replace("packet_", "", 1).strip()
        if ro and ro not in rows:
            latest = _latest_stored_packet(ro)
            if latest:
                packet = latest.get("packet") if isinstance(latest.get("packet"), dict) else {}
                rows[ro] = {
                    "ro": ro,
                    "customer": packet.get("customer", ""),
                    "vehicle": packet.get("vehicle", ""),
                    "status": "legacy packet",
                    "has_packet": True,
                    "generated_at": latest.get("generated_at", ""),
                    "source": latest.get("label", latest.get("source", "")),
                }

    for ro, job in _completed_state_jobs_by_ro().items():
        latest = _latest_stored_packet(ro)
        if ro not in rows:
            rows[ro] = {
                "ro": ro,
                "customer": job.get("customer", ""),
                "vehicle": job.get("vehicle", ""),
                "status": job.get("workflow_status") or job.get("status") or "completed",
                "has_packet": bool(latest),
                "generated_at": latest.get("generated_at", "") if latest else "",
                "source": latest.get("label", "") if latest else "No stored packet",
            }
        else:
            rows[ro]["customer"] = rows[ro].get("customer") or job.get("customer", "")
            rows[ro]["vehicle"] = rows[ro].get("vehicle") or job.get("vehicle", "")
            rows[ro]["status"] = job.get("workflow_status") or job.get("status") or rows[ro].get("status", "")

    return sorted(rows.values(), key=lambda row: str(row.get("generated_at") or ""), reverse=True)


def _append_api_cost_log(entry: dict) -> None:
    try:
        API_COSTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with API_COSTS_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as error:
        print(f"Photo analysis cost log failed: {error}")


def _as_list(value) -> list:
    if isinstance(value, list):
        return value
    return []


def _first_text(data: dict, *keys: str) -> str:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def _photo_url_from_value(value) -> str:
    if isinstance(value, str) and value.lower().startswith(("http://", "https://")):
        return value
    if isinstance(value, dict):
        for key in ("url", "photo_url", "image_url", "src", "href", "thumbnail_url"):
            found = value.get(key)
            if isinstance(found, str) and found.lower().startswith(("http://", "https://")):
                return found
    return ""


def _extract_photo_entries(dvi_response) -> list[dict]:
    photos = []
    seen_ids = set()

    def add_photo(url, label, image_id):
        if not url:
            return
        if "motovisuals.com" in str(url):
            return
        key = image_id if image_id else url
        if key in seen_ids:
            return
        seen_ids.add(key)
        label = str(label or "DVI Photo")
        if len(label) > 40:
            label = label[:40] + "..."
        photos.append({
            "url": url,
            "thumbnail_url": url,
            "label": label,
            "image_id": image_id,
        })

    def extract_images(images_list, label):
        for img in (images_list or []):
            if isinstance(img, dict):
                add_photo(
                    img.get("image_url", ""),
                    label,
                    img.get("image_id", img.get("id", "")),
                )
            elif isinstance(img, str) and img:
                add_photo(img, label, img)

    try:
        content = dvi_response.get("content", {}) if isinstance(dvi_response, dict) else {}
        if not content and isinstance(dvi_response, dict):
            content = dvi_response

        # Location 1: reason_vehicle_is_here.
        for item in content.get("reason_vehicle_is_here", []):
            if not isinstance(item, dict):
                continue
            label = item.get("details", item.get("notes", "Customer Concern"))
            extract_images(item.get("images", []), label)
            extract_images(item.get("item_images", []), label)
            for tagged in item.get("tagged_items", []):
                if isinstance(tagged, dict):
                    extract_images(tagged.get("images", []), tagged.get("name", label))
                    extract_images(tagged.get("item_images", []), tagged.get("name", label))

        # Location 2: dvis > dvi_category > dvi_items.
        for dvi in content.get("dvis", []):
            if not isinstance(dvi, dict):
                continue
            for cat in dvi.get("dvi_category", []):
                if not isinstance(cat, dict):
                    continue
                cat_name = cat.get("category_name", "")
                extract_images(cat.get("images", []), cat_name)
                for dvi_item in cat.get("dvi_items", []):
                    if not isinstance(dvi_item, dict):
                        continue
                    item_name = dvi_item.get("item_name", "")
                    item_status = dvi_item.get("item_status", "")
                    label = f"{cat_name} - {item_name}"

                    # Primary: item_images contains real shop photo objects.
                    for img in dvi_item.get("item_images", []):
                        if isinstance(img, dict):
                            url = img.get("image_url", "")
                            image_id = img.get("image_id", img.get("id", ""))
                            add_photo(url, label, image_id)

                    # Fallback: item_picture contains plain URL strings.
                    for url in dvi_item.get("item_picture", []):
                        if isinstance(url, str) and url:
                            add_photo(url, label, url)

                    for rec in dvi_item.get("recommendations", []):
                        if isinstance(rec, dict):
                            for img in rec.get("item_images", rec.get("images", [])):
                                if isinstance(img, dict):
                                    url = img.get("image_url", "")
                                    add_photo(url, f"{label} (rec)", img.get("image_id", url))

        # Location 3: top-level images array.
        extract_images(content.get("images", []), "DVI Photo")

        # Location 4: hunter_results.
        for result in content.get("hunter_results", []):
            if isinstance(result, dict):
                extract_images(result.get("images", []), result.get("name", "Hunter Result"))

        # Location 5: note images.
        for note in content.get("notes", []):
            if isinstance(note, dict):
                extract_images(note.get("images", []), str(note.get("text", "Note Photo"))[:40])

        # Location 6: services array.
        for svc in content.get("services", []):
            if isinstance(svc, dict):
                label = svc.get("name", svc.get("title", "Service"))
                extract_images(svc.get("images", []), label)

        # Location 7: flat items array.
        for item in content.get("items", []):
            if isinstance(item, dict):
                label = item.get("name", item.get("title", "Inspection Item"))
                extract_images(item.get("images", []), label)

        # Location 8: inspections array.
        for insp in content.get("inspections", []):
            if isinstance(insp, dict):
                label = insp.get("name", insp.get("title", "Inspection"))
                extract_images(insp.get("images", []), label)
    except Exception as error:
        print(f"Photo extraction error: {error}")

    print(f"Photo extraction complete: {len(photos)} unique photos found")
    return photos


def _load_dvi_photo_entries(ro: str) -> list[dict]:
    try:
        dvi_response = fetch_dvi_from_autoflow(ro)
    except Exception as error:
        print(f"Photo panel DVI fetch failed for RO {ro}: {error}")
        return []
    if not isinstance(dvi_response, dict):
        return []
    return _extract_photo_entries(dvi_response)


def _render_merged_findings(cache: dict) -> str:
    merged = cache.get("merged_photo_findings") if isinstance(cache, dict) else None
    if not isinstance(merged, dict):
        return PHOTO_FINDINGS_PLACEHOLDER
    ro_notes_block = str(merged.get("ro_notes_block") or "").strip()
    unmatched_findings = str(merged.get("unmatched_findings") or "").strip()
    if not ro_notes_block and not unmatched_findings:
        return PHOTO_FINDINGS_PLACEHOLDER
    timestamp = format_ts(merged.get("timestamp"))
    requested_by = _escape(merged.get("requested_by") or "unknown")
    try:
        findings_count = int(merged.get("findings_count") or 0)
    except (TypeError, ValueError):
        findings_count = 0
    unmatched_html = ""
    if unmatched_findings:
        unmatched_html = f"""
          <div style="margin-top:1rem;padding:1rem; background:#fef9c3;border:1px solid #fbbf24; border-radius:6px;font-size:12px;color:#78350f;">
            <strong>Additional findings not matched to a job block:</strong>
            {_escape(unmatched_findings)}
          </div>
        """
    return f"""
        <div id="photo-findings-merged" style="margin:2rem 0; padding:1.5rem;border:2px solid #185FA5;border-radius:8px; background:#f8faff;">
          <div style="font-size:11px;font-weight:900;color:#185FA5; letter-spacing:.08em;text-transform:uppercase; margin-bottom:1rem;">
            RO Notes - Copy/Paste into TekMetric
            <span style="font-weight:400;color:#666;margin-left:8px;">
            {findings_count} photos analyzed · {requested_by} · {timestamp}
            </span>
          </div>
          <pre style="font-family:inherit;font-size:13px; line-height:1.8;white-space:pre-wrap; background:#fff;border:1px solid #cbd5e1; border-radius:6px;padding:1rem; color:#1a1a1a;margin:0;">{_escape(ro_notes_block)}</pre>
          {unmatched_html}
        </div>
    """


def _render_photo_panel(ro: str, cache: dict) -> str:
    photos = _load_dvi_photo_entries(ro)
    analyzed = set(str(item) for item in _as_list(cache.get("analyzed_photos")))
    if not photos:
        return """
        <section class="photo-panel">
            <h2>Photo evidence review</h2>
            <p class="photo-subtext">No photos found in AutoFlow DVI for this RO.</p>
        </section>
        """

    cards = []
    for idx, photo in enumerate(photos):
        url = str(photo.get("url") or "")
        label = str(photo.get("label") or "DVI photo")
        is_analyzed = url in analyzed
        classes = "photo-card analyzed selected" if is_analyzed else "photo-card"
        checked = "true" if is_analyzed else "false"
        badge = '<div class="photo-analyzed-badge">Analyzed</div>' if is_analyzed else ""
        cards.append(
            f"""
            <button type="button" class="{classes}" data-photo-index="{idx}" data-url="{_escape(url)}" data-selected="{checked}">
                <span class="photo-check">✓</span>
                {badge}
                <img src="{_escape(photo.get("thumbnail_url") or url)}" alt="{_escape(label)}" loading="lazy">
                <span class="photo-label">{_escape(label[:30])}</span>
            </button>
            """
        )

    photo_data = json.dumps(photos, ensure_ascii=True)
    return f"""
        <section class="photo-panel" id="photoPanel">
            <div class="photo-panel-head">
                <div>
                    <h2>Photo evidence review</h2>
                    <p class="photo-subtext">Select photos for AI analysis. Choose scanner data, scope captures, damage photos, and measurement readings. Skip progress shots and overview photos.</p>
                </div>
            </div>
            <div class="photo-grid" id="photoGrid">{''.join(cards)}</div>
            <div class="photo-controls">
                <div class="photo-counter" id="photoCounter">0 photos selected · estimated cost: ~$0.00</div>
                <button type="button" class="btn photo-analyze" id="analyzePhotosBtn" disabled>Analyze selected photos</button>
            </div>
            <div id="photoFindingsPanel"></div>
        </section>
        <script type="application/json" id="photoData">{photo_data}</script>
    """


def _render_cached_photo_panel_notice() -> str:
    return """
        <section class="photo-panel">
            <h2>Photo evidence review</h2>
            <p class="photo-subtext">Stored packet opened from cache. Live DVI photo lookup is intentionally skipped so this page does not regenerate, call AutoFlow, or use AI credits.</p>
        </section>
    """


def _media_type_from_url(url: str) -> str:
    clean = str(url or "").split("?")[0].lower()
    if clean.endswith(".png"):
        return "image/png"
    if clean.endswith(".webp"):
        return "image/webp"
    if clean.endswith(".gif"):
        return "image/gif"
    return "image/jpeg"


def _get_full_res_url(url: str) -> str:
    if url.endswith("_s.jpeg"):
        return url[:-7] + ".jpeg"
    if url.endswith("_s.jpg"):
        return url[:-6] + ".jpg"
    return url


def _download_photo_once(url: str) -> tuple[str, str]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://app.autoflow.com/",
        "Accept": "image/jpeg,image/png,image/*,*/*",
    }
    print(f"Downloading photo: {url[:80]}")
    print(f"Headers: {headers}")
    try:
        req = Request(url, headers=headers)
        with urlopen(req, timeout=15) as response:
            image_bytes = response.read()
            media_type = response.headers.get_content_type() or _media_type_from_url(url)
    except (HTTPError, URLError, OSError, socket.timeout) as error:
        print(f"Download FAILED: {error}")
        raise
    print(f"Downloaded OK: {len(image_bytes)} bytes")
    return base64.b64encode(image_bytes).decode("ascii"), media_type


def _download_photo(url: str) -> tuple[str, str]:
    try:
        return _download_photo_once(url)
    except (HTTPError, URLError, OSError, socket.timeout):
        full_res_url = _get_full_res_url(url)
        if full_res_url == url:
            raise
        return _download_photo_once(full_res_url)


def _call_claude_vision(photo_b64: str, media_type: str) -> str:
    load_dotenv(REPO_ROOT / ".env")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return "Photo analysis unavailable: ANTHROPIC_API_KEY is not set."

    media_type = "image/jpeg"
    prompt_text = (
        "You are an automotive diagnostic assistant. Analyze this photo from a vehicle inspection and describe "
        "what you see in detail. Focus on: scanner/scan tool data (PIDs, codes, live data values, freeze frame), "
        "oscilloscope/scope waveforms, measurement readings, visible damage or wear, warning lights or dash displays. "
        "If this is a progress or overview photo with no diagnostic value, say so clearly. Be concise and technical.\n\n"
        "Describe what diagnostic information is visible in this photo and how it relates to vehicle repair."
    )
    body = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 500,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": photo_b64,
                    },
                },
                {
                    "type": "text",
                    "text": prompt_text,
                },
            ],
        }],
    }
    print(f"Sending to Claude vision: {len(photo_b64)} chars base64, media_type: {media_type}")
    req = Request(
        ANTHROPIC_URL,
        data=json.dumps(body, ensure_ascii=True).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        error_body = error.read().decode("utf-8")
        print(f"Claude API error {error.code}: {error_body[:500]}")
        raise
    return clean_ai_response_text(_extract_response_text(payload))


def _extract_job_titles(packet_html: str) -> list[str]:
    pattern = r'class="job-header[^"]*">([^<]+)<'
    job_titles = re.findall(pattern, str(packet_html or ""))
    return [title.replace("&amp;", "&").strip() for title in job_titles if title.strip()]


def _parse_synthesis_response(text: str) -> dict | None:
    cleaned = clean_ai_response_text(text)
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()
    try:
        data = json.loads(cleaned)
    except (TypeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _fallback_synthesis_data(findings: list[dict], reason: str = "") -> dict:
    diagnostic_findings = [
        str(item.get("finding") or "").strip()
        for item in findings
        if item.get("has_diagnostic_value") and str(item.get("finding") or "").strip()
    ]
    ro_notes = "\n".join(_suggested_merge_text(item) for item in diagnostic_findings if _suggested_merge_text(item))
    unmatched = " ".join(diagnostic_findings[:3])
    if reason:
        unmatched = f"Synthesis JSON parse failed: {reason}. {unmatched}".strip()
    return {
        "job_findings": [],
        "ro_notes_block": clean_ai_response_text(ro_notes),
        "unmatched_findings": clean_ai_response_text(unmatched),
    }


def _clean_synthesis_data(data: dict | None, fallback_findings: list[dict]) -> dict:
    if not isinstance(data, dict):
        return _fallback_synthesis_data(fallback_findings, "invalid response")
    job_findings = []
    for item in _as_list(data.get("job_findings")):
        if not isinstance(item, dict):
            continue
        job_findings.append({
            "job_title_match": clean_ai_response_text(item.get("job_title_match") or ""),
            "technical_note": clean_ai_response_text(item.get("technical_note") or ""),
            "customer_script": clean_ai_response_text(item.get("customer_script") or ""),
            "ro_note": clean_ai_response_text(item.get("ro_note") or ""),
        })
    return {
        "job_findings": job_findings,
        "ro_notes_block": clean_ai_response_text(data.get("ro_notes_block") or ""),
        "unmatched_findings": clean_ai_response_text(data.get("unmatched_findings") or ""),
    }


def _render_job_finding_block(item: dict, requested_by: str, timestamp: str, customer_first: str) -> str:
    technical_note = _escape(item.get("technical_note") or "")
    customer_script = _escape(item.get("customer_script") or "")
    ro_note = _escape(item.get("ro_note") or "")
    return f"""
<div style="margin-top:16px;padding:14px;
border-left:4px solid #185FA5;background:#f0f7ff;
border-radius:0 8px 8px 0;">
  <div style="font-size:10px;font-weight:900;color:#185FA5;
  letter-spacing:.08em;text-transform:uppercase;
  margin-bottom:6px;">
    Photo-Verified Finding · {_escape(requested_by)} · {timestamp}
  </div>
  <div style="font-size:13px;color:#1e293b;
  line-height:1.6;margin-bottom:8px;">
    <strong>Technical:</strong> {technical_note}
  </div>
  <div style="font-size:13px;color:#166534;
  line-height:1.6;margin-bottom:8px;">
    <strong>Tell {_escape(customer_first)}:</strong>
    {customer_script}
  </div>
  <div style="font-size:11px;color:#64748b;
  font-style:italic;line-height:1.5;">
    <strong>RO Note:</strong> {ro_note}
  </div>
</div>
"""


def _inject_finding_into_job_block(packet_html: str, item: dict, requested_by: str, timestamp: str, customer_first: str) -> tuple[str, bool]:
    title = clean_ai_response_text(item.get("job_title_match") or "")
    if not title:
        return packet_html, False
    title_candidates = [html.escape(title, quote=False), title]
    header_pos = -1
    for candidate in title_candidates:
        header_pos = packet_html.find(candidate)
        if header_pos != -1:
            break
    if header_pos == -1:
        return packet_html, False

    body_start = packet_html.find('<div class="job-body">', header_pos)
    if body_start == -1:
        return packet_html, False
    next_job = packet_html.find('class="job-block"', body_start + 1)
    body_scope_end = next_job if next_job != -1 else packet_html.find('<section class="generation-log"', body_start)
    if body_scope_end == -1:
        body_scope_end = len(packet_html)
    insert_pos = packet_html.rfind("</ul>", body_start, body_scope_end)
    if insert_pos == -1:
        insert_pos = packet_html.find("</div>", body_start)
        if insert_pos == -1:
            return packet_html, False
    else:
        insert_pos += len("</ul>")

    injected_html = _render_job_finding_block(item, requested_by, timestamp, customer_first)
    return packet_html[:insert_pos] + injected_html + packet_html[insert_pos:], True


def _call_claude_synthesis(packet: dict, findings: list[dict], packet_html: str) -> dict:
    diagnostic_findings = [
        str(item.get("finding") or "").strip()
        for item in findings
        if item.get("has_diagnostic_value") and str(item.get("finding") or "").strip()
    ]
    if not diagnostic_findings:
        return {"job_findings": [], "ro_notes_block": "", "unmatched_findings": ""}

    vehicle = str(packet.get("vehicle") or "Vehicle")
    mileage = str(packet.get("mileage") or "Not recorded")
    customer_first = str(packet.get("customer") or "").split()[0] if str(packet.get("customer") or "").split() else "Customer"
    job_titles = _extract_job_titles(packet_html)
    numbered_findings = "\n".join(
        f"{index}. {finding}" for index, finding in enumerate(diagnostic_findings, start=1)
    )
    numbered_jobs = "\n".join(
        f"{index}. {title}" for index, title in enumerate(job_titles, start=1)
    ) or "No job blocks found in packet HTML."
    user_prompt = f"""
Vehicle: {vehicle} | Mileage: {mileage}
Customer: {customer_first}

The following diagnostic evidence was observed during inspection:
{numbered_findings}

The repair order contains these job blocks:
{numbered_jobs}

Produce a JSON response with this exact structure - no markdown,
no code fences, just raw JSON:

{{
  "job_findings": [
    {{
      "job_title_match": "exact job title from the list above that this finding belongs to",
      "technical_note": "1-2 sentence factual technical finding supported by photo evidence. Professional terminology. Under 60 words.",
      "customer_script": "1-2 sentence plain language explanation the advisor reads to the customer on the phone. No codes, no jargon. Warm and direct. Under 50 words.",
      "ro_note": "1 sentence copy-paste ready for TekMetric RO notes field. State what was found and confirmed. Under 30 words."
    }}
  ],
  "ro_notes_block": "Complete RO notes section combining all ro_note entries separated by newlines. Ready to paste into TekMetric. Under 150 words total.",
  "unmatched_findings": "Any findings that do not clearly match a job block - brief summary, 2-3 sentences max."
}}

Only include job_findings entries where photo evidence directly
supports that specific job. Do not force matches.
If a finding matches multiple jobs, use the most specific one.
""".strip()

    load_dotenv(REPO_ROOT / ".env")
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return "", "Photo synthesis unavailable: ANTHROPIC_API_KEY is not set."

    body = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 2500,
        "system": (
            "You are an automotive service advisor and diagnostic report writer for a professional auto repair shop. "
            "You translate technical diagnostic findings into concise, factual summaries that get injected directly "
            "into specific repair order job blocks. Every statement must be supported by the evidence provided. "
            "Never speculate beyond the evidence."
        ),
        "messages": [{"role": "user", "content": user_prompt}],
    }
    req = Request(
        ANTHROPIC_URL,
        data=json.dumps(body, ensure_ascii=True).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=45) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        error_body = error.read().decode("utf-8")
        print(f"Claude synthesis API error {error.code}: {error_body[:500]}")
        raise
    parsed = _parse_synthesis_response(_extract_response_text(payload))
    if parsed is None:
        return _fallback_synthesis_data(findings, "Claude returned non-JSON synthesis")
    return _clean_synthesis_data(parsed, findings)


def _has_diagnostic_value(finding: str) -> bool:
    lowered = str(finding or "").lower()
    return not any(phrase in lowered for phrase in (
        "no diagnostic value",
        "progress photo",
        "overview",
        "cannot determine",
    ))


def _suggested_merge_text(finding: str) -> str:
    text = " ".join(str(finding or "").split())
    if not text:
        return ""
    sentences = []
    for part in text.replace("! ", ". ").replace("? ", ". ").split(". "):
        part = part.strip(" .")
        if part:
            sentences.append(part)
        if len(sentences) >= 2:
            break
    return ". ".join(sentences)[:500].strip() + ("." if sentences else "")


def _event_label(trigger: str) -> str:
    return {
        "initial": "Initial generation",
        "regenerate": "Post-DVI regeneration",
    }.get(str(trigger or ""), str(trigger or "Packet event"))


def _make_cache(ro: str, packet: dict, packet_html: str, previous_cache: dict | None, trigger: str, requested_by: str) -> dict:
    generated_at = str(packet.get("generated_at") or datetime.utcnow().isoformat())
    dvi_pulled_at = str(packet.get("dvi_pulled_at") or generated_at)
    cost = float(packet.get("api_cost_usd") or 0.0)
    previous_log = []
    previous_total = 0.0
    analyzed_photos = []
    merged_photo_findings = None
    if isinstance(previous_cache, dict):
        previous_log = previous_cache.get("generation_log", []) if isinstance(previous_cache.get("generation_log"), list) else []
        previous_total = float(previous_cache.get("total_cost_usd") or 0.0)
        analyzed_photos = previous_cache.get("analyzed_photos", []) if isinstance(previous_cache.get("analyzed_photos"), list) else []
        merged_photo_findings = previous_cache.get("merged_photo_findings") if isinstance(previous_cache.get("merged_photo_findings"), dict) else None
    generation_log = previous_log + [{
        "timestamp": generated_at,
        "trigger": trigger,
        "requested_by": requested_by or "unknown",
        "dvi_item_count": int(packet.get("dvi_item_count") or 0),
        "api_cost_usd": cost,
    }]
    cache = {
        "ro": ro,
        "generated_at": generated_at,
        "dvi_pulled_at": dvi_pulled_at,
        "dvi_snapshot_hash": packet.get("dvi_snapshot_hash", ""),
        "dvi_snapshot": packet.get("dvi_snapshot", {}),
        "dvi_snapshot_captured_at": packet.get("dvi_snapshot_captured_at", ""),
        "packet_stale": {
            "checked_at": generated_at,
            "can_check": bool(packet.get("dvi_snapshot_hash")),
            "changed": False,
            "stored_hash": packet.get("dvi_snapshot_hash", ""),
            "current_hash": packet.get("dvi_snapshot_hash", ""),
            "diff": [],
        },
        "packet_html": packet_html,
        "packet": packet,
        "generation_log": generation_log,
        "total_cost_usd": previous_total + cost,
        "analyzed_photos": analyzed_photos,
    }
    if merged_photo_findings:
        cache["merged_photo_findings"] = merged_photo_findings
    return cache


def _stale_changed(cache: dict) -> bool:
    stale = cache.get("packet_stale") if isinstance(cache, dict) else {}
    return isinstance(stale, dict) and stale.get("changed") is True


def _refresh_packet_stale_state(ro: str, cache: dict) -> dict:
    if not isinstance(cache, dict) or not cache:
        return cache
    result = compare_packet_to_current_dvi(ro, packet_cache=cache)
    if result.get("can_check"):
        cache["packet_stale"] = result
        packet = cache.get("packet")
        if isinstance(packet, dict):
            packet["packet_stale"] = result
        try:
            _save_cache(ro, cache)
        except OSError as error:
            print(f"Packet stale cache save failed for RO {ro}: {error}")
    return cache


def _render_stale_diff(cache: dict) -> str:
    stale = cache.get("packet_stale") if isinstance(cache, dict) else {}
    if not isinstance(stale, dict) or not stale.get("changed"):
        return ""
    diff_items = stale.get("diff") if isinstance(stale.get("diff"), list) else []
    diff_html = "".join(f"<li>{_escape(item)}</li>" for item in diff_items[:12])
    if not diff_html:
        diff_html = "<li>DVI content changed after packet generation.</li>"
    return (
        '<div class="packet-stale-diff">'
        "<strong>DVI updated since packet - stale packet. Re-review before presenting.</strong>"
        f"<ul>{diff_html}</ul>"
        "</div>"
    )


def _render_banner(cache: dict, just_regenerated: bool = False, requested_by: str = "") -> str:
    generated_at = format_ts(cache.get("generated_at"))
    dvi_pulled_at = format_ts(cache.get("dvi_pulled_at"))
    if _stale_changed(cache):
        text = f"DVI updated since packet · Original DVI pulled {dvi_pulled_at} · Packet generated {generated_at}"
        return f'<div class="packet-banner stale"><span>{_escape(text)}</span>{_render_stale_diff(cache)}</div>'
    if just_regenerated:
        text = f"Packet updated · DVI pulled fresh from AutoFlow · {generated_at} · Requested by {requested_by or 'unknown'}"
        return f'<div class="packet-banner fresh">{_escape(text)}</div>'
    text = f"Viewing saved packet · DVI pulled {dvi_pulled_at} · Generated {generated_at}"
    return f'<div class="packet-banner cached"><span>{_escape(text)}</span></div>'


def _render_generation_log(ro: str, cache: dict) -> str:
    rows = []
    for item in cache.get("generation_log", []) if isinstance(cache.get("generation_log"), list) else []:
        rows.append(
            "<tr>"
            f"<td>{_escape(_event_label(item.get('trigger')))}</td>"
            f"<td>{_escape(format_ts(item.get('timestamp')))}</td>"
            f"<td>{_escape(item.get('requested_by') or 'unknown')}</td>"
            f"<td>{_escape(item.get('dvi_item_count') or 0)}</td>"
            f"<td>${float(item.get('api_cost_usd') or 0.0):.4f}</td>"
            "</tr>"
        )
    total = float(cache.get("total_cost_usd") or 0.0)
    rows.append(
        '<tr class="total-row">'
        '<td colspan="4">Total API cost this RO</td>'
        f"<td>${total:.4f}</td>"
        "</tr>"
    )
    return f"""
        <section class="generation-log">
            <h2>Packet history — RO {_escape(ro)}</h2>
            <table>
                <thead><tr><th>Event</th><th>When</th><th>Requested by</th><th>Items in DVI</th><th>Cost</th></tr></thead>
                <tbody>{''.join(rows)}</tbody>
            </table>
        </section>
    """


def _header_class(category: str) -> str:
    category = str(category or "").upper()
    if category == "SAFETY":
        return "safety"
    if category == "MAINTENANCE":
        return "maintenance"
    if category == "POSSIBLE ADD-ON":
        return "addon"
    return "concern"


def _render_labor_items(items) -> str:
    lines = []
    for item in items or []:
        text = _escape(item)
        cls = " reminder" if "⚠" in str(item) or "don't forget" in str(item).lower() else ""
        lines.append(f'<li class="{cls}"><span class="box">□</span>{text}</li>')
    return "\n".join(lines) or '<li><span class="box">□</span>No labor lookup items generated.</li>'


def _render_parts_items(items) -> str:
    lines = []
    for item in items or []:
        lines.append(f'<li><span class="box">□</span>{_escape(item)}</li>')
    return "\n".join(lines) or '<li><span class="box">□</span>No parts lookup items generated.</li>'


def _render_job(job: dict) -> str:
    category = str(job.get("category", "CONCERN")).upper()
    title = _escape(job.get("title", "Untitled job"))
    header_class = _header_class(category)
    addon_banner = ""
    addon_toggle = ""
    if header_class == "addon" or job.get("is_possible_addon"):
        addon_banner = '<div class="addon-banner">⚠ NOT PRESENTED TO CUSTOMER — ADVISOR RADAR ONLY</div>'
        addon_toggle = '<div class="toggle-row">[ ] Include in estimate&nbsp;&nbsp;&nbsp;[✓] Advisor talking point only</div>'

    conditional = str(job.get("note_conditional") or "").strip()
    conditional_html = ""
    if conditional:
        conditional_html = f'<hr><p class="conditional"><em>{_escape(conditional)}</em></p>'

    return f"""
    <section class="job-block">
        <div class="job-header {header_class}">{title}</div>
        {addon_banner}
        <div class="job-body">
            {addon_toggle}
            <div class="lookup">
                <div class="label">LOOK UP LABOR</div>
                <ul>{_render_labor_items(job.get("labor_items", []))}</ul>
            </div>
            <div class="lookup">
                <div class="label">LOOK UP PARTS</div>
                <ul>{_render_parts_items(job.get("parts_items", []))}</ul>
            </div>
            <div class="copy-note">
                <div class="copy-label">📋 COPY → NOTE</div>
                <p>{_escape(job.get("note_justification", ""))}</p>
                {conditional_html}
            </div>
        </div>
    </section>
    """


def _render_error(ro: str, packet: dict) -> Response:
    message = _escape(packet.get("error", "Packet error"))
    detail = _escape(packet.get("detail", ""))
    html_text = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Packet Error — RO {_escape(ro)}</title></head>
<body style="font-family:Arial,sans-serif;background:#f8fafc;color:#111827;padding:40px;">
    <h1>TekMetric Packet Error</h1>
    <p><strong>RO:</strong> {_escape(ro)}</p>
    <p>{message}</p>
    <pre style="background:#fee2e2;border:1px solid #fecaca;padding:16px;border-radius:8px;white-space:pre-wrap;">{detail}</pre>
</body>
</html>"""
    return Response(html_text, mimetype="text/html")


def _render_packet_html(ro: str, packet: dict, cache: dict | None = None, just_regenerated: bool = False, requested_by: str = "", include_photo_panel: bool = True) -> str:
    drag_items = "\n".join(f"<li>{_escape(item)}</li>" for item in packet.get("drag_order", []))
    jobs_html = "\n".join(_render_job(job) for job in packet.get("jobs", []))
    generated_at = _escape(format_ts(packet.get("generated_at", datetime.now(timezone.utc).isoformat())))
    cache = cache or {}
    banner_html = _render_banner(cache, just_regenerated=just_regenerated, requested_by=requested_by) if cache else ""
    generation_log_html = _render_generation_log(ro, cache) if cache else ""
    photo_panel_html = _render_photo_panel(ro, cache) if include_photo_panel else _render_cached_photo_panel_notice()
    merged_findings_html = _render_merged_findings(cache)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TekMetric Packet — RO {_escape(ro)}</title>
    <style>
        * {{box-sizing:border-box;}}
        body {{font-family:Arial,Helvetica,sans-serif;background:#e5e7eb;color:#111827;margin:0;padding:24px;}}
        .page {{max-width:1020px;margin:0 auto;background:#fff;padding:28px;border-radius:12px;box-shadow:0 12px 30px rgba(15,23,42,0.16);}}
        .header {{display:flex;justify-content:space-between;gap:24px;border-bottom:3px solid #111827;padding-bottom:18px;margin-bottom:22px;}}
        .shop {{font-size:26px;font-weight:900;letter-spacing:0.08em;}}
        .label-top {{font-size:14px;font-weight:800;color:#475569;letter-spacing:0.16em;margin-top:4px;}}
        .meta {{font-size:13px;line-height:1.7;color:#334155;}}
        .actions {{display:flex;gap:8px;justify-content:flex-end;margin-bottom:12px;}}
        .btn {{border:0;border-radius:8px;padding:9px 13px;font-weight:800;color:#fff;background:#185FA5;text-decoration:none;cursor:pointer;font-size:13px;}}
        .btn.regen {{background:#EF9F27;color:#1f2937;}}
        .packet-banner {{border-radius:10px;padding:12px 14px;margin:0 0 16px;font-weight:900;display:flex;align-items:center;justify-content:space-between;gap:12px;}}
        .packet-banner.cached {{background:#fef3c7;border:1px solid #f59e0b;color:#78350f;}}
        .packet-banner.fresh {{background:#dcfce7;border:1px solid #16a34a;color:#14532d;}}
        .packet-banner.stale {{display:block;background:#fee2e2;border:2px solid #dc2626;color:#7f1d1d;}}
        .packet-stale-diff {{margin-top:10px;font-size:13px;line-height:1.5;font-weight:700;}}
        .packet-stale-diff ul {{margin:8px 0 0 18px;padding:0;}}
        .section-box {{background:#f3f4f6;border:1px solid #d1d5db;border-radius:10px;padding:18px;margin:20px 0;}}
        h2 {{font-size:16px;letter-spacing:0.08em;margin:0 0 12px;text-transform:uppercase;}}
        .drag-order ol {{margin:0;padding-left:24px;font-size:15px;line-height:1.8;}}
        .advisor-gate {{background:#fef3c7;border:2px solid #f59e0b;color:#111827;}}
        .advisor-gate h2 {{color:#92400e;}}
        .job-block {{background:#fff;border:1px solid #cbd5e1;border-radius:10px;margin:24px 0;overflow:hidden;page-break-inside:avoid;}}
        .job-header {{padding:12px 16px;color:#fff;font-weight:900;letter-spacing:0.04em;}}
        .job-header.concern {{background:#1e40af;}}
        .job-header.safety {{background:#dc2626;}}
        .job-header.maintenance {{background:#15803d;}}
        .job-header.addon {{background:#7f1d1d;}}
        .addon-banner {{background:#fca5a5;color:#111827;font-weight:900;padding:10px 16px;text-align:center;}}
        .job-body {{padding:18px;}}
        .lookup {{margin-bottom:16px;}}
        .label {{font-size:12px;font-weight:900;color:#64748b;letter-spacing:0.1em;margin-bottom:8px;}}
        ul {{list-style:none;margin:0;padding:0;}}
        li {{padding:5px 0;color:#374151;line-height:1.45;}}
        .box {{font-weight:900;margin-right:8px;color:#111827;}}
        .reminder {{color:#b45309;font-weight:700;}}
        .copy-note {{background:#dbeafe;border:1px solid #93c5fd;border-radius:10px;padding:16px;margin-top:16px;}}
        .copy-label {{font-weight:900;color:#1e3a8a;margin-bottom:8px;letter-spacing:0.05em;}}
        .copy-note p {{margin:0;line-height:1.55;}}
        .copy-note hr {{border:0;border-top:1px solid #93c5fd;margin:12px 0;}}
        .conditional {{font-size:14px;color:#334155;}}
        .toggle-row {{font-weight:900;color:#7f1d1d;margin-bottom:14px;}}
        .generation-log {{margin-top:28px;border-top:2px solid #111827;padding-top:18px;page-break-inside:avoid;}}
        .generation-log table {{width:100%;border-collapse:collapse;font-size:13px;}}
        .generation-log th,.generation-log td {{border:1px solid #cbd5e1;padding:8px;text-align:left;}}
        .generation-log th {{background:#f1f5f9;color:#334155;text-transform:uppercase;font-size:11px;letter-spacing:0.08em;}}
        .generation-log .total-row td {{font-weight:900;background:#f8fafc;}}
        .photo-panel {{margin-top:28px;border:2px solid #d1d5db;border-radius:12px;padding:18px;background:#f8fafc;page-break-inside:avoid;}}
        .photo-panel h2 {{margin-bottom:6px;}}
        .photo-subtext {{margin:0 0 14px;color:#475569;line-height:1.45;font-size:14px;}}
        .photo-grid {{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px;margin-top:14px;}}
        .photo-card {{position:relative;border:2px solid transparent;border-radius:10px;background:#fff;padding:0 0 10px;overflow:hidden;cursor:pointer;text-align:left;box-shadow:0 2px 8px rgba(15,23,42,0.08);}}
        .photo-card img {{display:block;width:100%;height:120px;object-fit:cover;background:#e5e7eb;}}
        .photo-card.selected {{border-color:#EF9F27;box-shadow:0 0 0 3px rgba(239,159,39,0.18);}}
        .photo-card.analyzed {{border-color:#16a34a;}}
        .photo-check {{position:absolute;right:8px;top:8px;width:24px;height:24px;border-radius:999px;background:#EF9F27;color:#111827;display:none;align-items:center;justify-content:center;font-weight:900;z-index:2;}}
        .photo-card.selected .photo-check {{display:flex;}}
        .photo-card.analyzed .photo-check {{background:#16a34a;color:#fff;}}
        .photo-analyzed-badge {{position:absolute;left:8px;top:8px;background:#16a34a;color:#fff;border-radius:999px;padding:4px 8px;font-size:10px;font-weight:900;text-transform:uppercase;z-index:2;}}
        .photo-label {{display:block;padding:8px 8px 0;color:#334155;font-size:12px;font-weight:800;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
        .photo-controls {{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-top:16px;}}
        .photo-counter {{font-weight:900;color:#334155;}}
        .btn.photo-analyze:disabled,.btn.merge-btn:disabled {{background:#cbd5e1;color:#64748b;cursor:not-allowed;}}
        .findings-panel {{margin-top:18px;border:1px solid #cbd5e1;border-radius:12px;background:#fff;padding:16px;}}
        .finding-row {{display:grid;grid-template-columns:92px 28px 1fr;gap:12px;align-items:start;border:1px solid #bbf7d0;border-radius:10px;padding:12px;margin:10px 0;background:#f0fdf4;}}
        .finding-row.no-value {{border-color:#d1d5db;background:#f3f4f6;color:#6b7280;}}
        .finding-row img {{width:80px;height:60px;object-fit:cover;border-radius:8px;background:#e5e7eb;}}
        .finding-row input {{margin-top:4px;}}
        .finding-text {{font-size:13px;line-height:1.45;color:#111827;}}
        .finding-row.no-value .finding-text {{color:#6b7280;}}
        .finding-suggested {{margin-top:8px;color:#64748b;font-size:12px;font-style:italic;}}
        .finding-label {{display:inline-block;margin-bottom:6px;border-radius:999px;background:#e5e7eb;color:#475569;padding:3px 8px;font-size:10px;font-weight:900;text-transform:uppercase;}}
        .matched-preview {{border:2px solid #185FA5;border-radius:12px;background:#f8faff;padding:14px;margin:16px 0;}}
        .matched-preview h3,.ro-notes-preview h3 {{margin:0 0 10px;font-size:12px;text-transform:uppercase;letter-spacing:0.08em;color:#185FA5;}}
        .matched-preview ul {{list-style:disc;margin-left:18px;}}
        .matched-preview li {{font-size:13px;line-height:1.55;}}
        .ro-notes-preview {{border:2px solid #3B6D11;border-radius:12px;background:#f8fff8;padding:14px;margin:16px 0;}}
        .ro-notes-preview textarea {{width:100%;min-height:130px;border:1px solid #cbd5e1;border-radius:8px;padding:10px;font-size:13px;line-height:1.6;color:#1a1a1a;}}
        .merge-success {{margin-top:14px;background:#dcfce7;border:1px solid #16a34a;color:#14532d;border-radius:10px;padding:12px;font-weight:900;display:flex;justify-content:space-between;gap:12px;align-items:center;}}
        .merged-photo-findings {{margin-top:28px;border:2px solid #185FA5;border-radius:12px;background:#eff6ff;padding:18px;page-break-inside:avoid;}}
        .merged-photo-findings h2 {{color:#1e3a8a;margin-bottom:8px;}}
        .merged-meta {{font-weight:900;color:#334155;margin-bottom:10px;}}
        .merged-rule {{height:2px;background:#93c5fd;margin:12px 0;}}
        .merged-photo-findings li {{list-style:disc;margin-left:20px;color:#111827;}}
        .footer {{margin-top:28px;border-top:2px solid #111827;padding-top:14px;text-align:center;font-weight:900;color:#334155;}}
        @media print {{
            body {{background:#fff;padding:0;}}
            .page {{box-shadow:none;border-radius:0;max-width:none;padding:0;}}
            .actions,.packet-banner,.photo-panel {{display:none;}}
            .job-block {{page-break-inside:avoid;}}
            .job-header,.addon-banner {{-webkit-print-color-adjust:exact;print-color-adjust:exact;}}
        }}
    </style>
</head>
<body>
    <main class="page">
        {banner_html}
        <div class="actions">
            <button class="btn" onclick="window.print()">Save as PDF</button>
            <button class="btn regen" id="regenBtn" onclick="regeneratePacket()">Regenerate — Pull Latest DVI</button>
        </div>
        <header class="header">
            <div>
                <div class="shop">CALLAHAN AUTO & DIESEL</div>
                <div class="label-top">TEKMETRIC PACKET</div>
            </div>
            <div class="meta">
                <div><strong>RO:</strong> {_escape(packet.get("ro", ro))}</div>
                <div><strong>Customer:</strong> {_escape(packet.get("customer", ""))}</div>
                <div><strong>Vehicle:</strong> {_escape(packet.get("vehicle", ""))}</div>
                <div><strong>Mileage:</strong> {_escape(packet.get("mileage", ""))}</div>
                <div><strong>Generated:</strong> {generated_at}</div>
            </div>
        </header>

        <section class="section-box drag-order">
            <h2>DRAG ORDER FOR TEKMETRIC</h2>
            <ol>{drag_items}</ol>
        </section>

        <section class="section-box advisor-gate">
            <h2>⚠ ADVISOR MENTAL GATE — READ BEFORE CALLING CUSTOMER</h2>
            <div>{_escape(packet.get("advisor_gate", ""))}</div>
        </section>

        {jobs_html}

        {photo_panel_html}

        {merged_findings_html}

        {generation_log_html}

        <footer class="footer">END OF PACKET — RO {_escape(ro)}<br>{generated_at}</footer>
    </main>
    <script>
    function regeneratePacket() {{
        var ok = window.confirm("Regenerating pulls a fresh DVI from AutoFlow and charges ~$0.04 in\\nAPI credits. Only use this after new DVI findings have been added by\\nthe tech. Who is requesting this regeneration?");
        if (!ok) return;
        var requester = window.prompt("Select requester: type Mitch, Drew, or Preston");
        if (!requester) return;
        var btn = document.getElementById("regenBtn");
        btn.textContent = "Regenerating...";
        btn.disabled = true;
        var form = document.createElement("form");
        form.method = "POST";
        form.action = "/dvi/packet/{_escape(ro)}/regenerate";
        var input = document.createElement("input");
        input.type = "hidden";
        input.name = "requested_by";
        input.value = requester;
        form.appendChild(input);
        document.body.appendChild(form);
        form.submit();
    }}
    var PHOTO_COST = {PHOTO_ANALYSIS_COST:.2f};
    var PHOTO_RO = "{_escape(ro)}";
    var PACKET_CUSTOMER_FIRST = {json.dumps(str(packet.get("customer") or "").split()[0] if str(packet.get("customer") or "").split() else "the customer", ensure_ascii=True)};
    var photoCards = Array.prototype.slice.call(document.querySelectorAll(".photo-card"));
    var analyzeBtn = document.getElementById("analyzePhotosBtn");
    var photoCounter = document.getElementById("photoCounter");
    var findingsPanel = document.getElementById("photoFindingsPanel");
    var photoAnalysisRequester = "";
    var latestSynthesisData = null;
    var latestFindingsCount = 0;

    function selectedPhotoUrls() {{
        return photoCards
            .filter(function(card) {{ return card.getAttribute("data-selected") === "true"; }})
            .map(function(card) {{ return card.getAttribute("data-url"); }})
            .filter(Boolean);
    }}

    function updatePhotoCounter() {{
        if (!photoCounter || !analyzeBtn) return;
        var count = selectedPhotoUrls().length;
        photoCounter.textContent = count + " photos selected · estimated cost: ~$" + (count * PHOTO_COST).toFixed(2);
        analyzeBtn.disabled = count === 0;
    }}

    photoCards.forEach(function(card) {{
        card.addEventListener("click", function() {{
            var selected = card.getAttribute("data-selected") === "true";
            card.setAttribute("data-selected", selected ? "false" : "true");
            card.classList.toggle("selected", !selected);
            updatePhotoCounter();
        }});
    }});

    function renderFindings(data) {{
        if (!findingsPanel) return;
        var findings = data.findings || [];
        if (!findings.length) {{
            findingsPanel.innerHTML = '<div class="findings-panel"><strong>No findings returned.</strong></div>';
            return;
        }}
        latestSynthesisData = data.synthesis_data || {{job_findings: [], ro_notes_block: "", unmatched_findings: ""}};
        latestFindingsCount = findings.filter(function(finding) {{ return !!finding.has_diagnostic_value; }}).length;
        var rows = findings.map(function(finding, index) {{
            var hasValue = !!finding.has_diagnostic_value;
            var checked = hasValue ? "checked" : "";
            var disabled = hasValue ? "" : "";
            var cls = hasValue ? "finding-row" : "finding-row no-value";
            var label = hasValue ? "Diagnostic finding" : "No diagnostic value - skip";
            return '<div class="' + cls + '" data-finding-index="' + index + '">' +
                '<img src="' + escapeHtml(finding.thumbnail_url || finding.photo_url || "") + '" alt="Photo finding">' +
                '<input type="checkbox" class="finding-check" ' + checked + ' ' + disabled + '>' +
                '<div>' +
                '<span class="finding-label">' + label + '</span>' +
                '<div class="finding-text">' + escapeHtml(finding.finding || "") + '</div>' +
                '<div class="finding-suggested">' + escapeHtml(finding.suggested_merge_text || "") + '</div>' +
                '</div>' +
                '</div>';
        }}).join("");
        var matchedRows = (latestSynthesisData.job_findings || []).map(function(item) {{
            var preview = String(item.technical_note || "").slice(0, 40);
            if (String(item.technical_note || "").length > 40) preview += "...";
            return '<li><strong>' + escapeHtml(item.job_title_match || "Unmatched job") + '</strong> &rarr; ' + escapeHtml(preview) + '</li>';
        }}).join("");
        if (!matchedRows) matchedRows = '<li>No findings were confidently matched to packet job blocks.</li>';
        findingsPanel.innerHTML =
            '<div class="findings-panel">' +
            '<h2>Photo findings — review before merging</h2>' +
            '<p class="photo-subtext">Uncheck any finding that is inaccurate or irrelevant before merging into the packet.</p>' +
            '<h3>Individual photos</h3>' +
            rows +
            '<div class="matched-preview">' +
            '<h3>Matched findings preview</h3>' +
            '<ul>' + matchedRows + '</ul>' +
            '</div>' +
            '<div class="ro-notes-preview">' +
            '<h3>RO Notes preview — copy anytime</h3>' +
            '<textarea readonly>' + escapeHtml(latestSynthesisData.ro_notes_block || "") + '</textarea>' +
            '</div>' +
            '<button type="button" class="btn merge-btn" id="mergeFindingsBtn">Merge findings into job blocks</button>' +
            '<div id="mergeResult"></div>' +
            '</div>';
        var mergeBtn = document.getElementById("mergeFindingsBtn");
        var checks = Array.prototype.slice.call(document.querySelectorAll(".finding-check"));
        function updateMergeButton() {{
            mergeBtn.disabled = checks.filter(function(check) {{ return check.checked; }}).length === 0;
        }}
        checks.forEach(function(check) {{ check.addEventListener("change", updateMergeButton); }});
        updateMergeButton();
        mergeBtn.addEventListener("click", function() {{
            var selected = [];
            checks.forEach(function(check, idx) {{
                if (check.checked && findings[idx] && findings[idx].suggested_merge_text) {{
                    selected.push(findings[idx].suggested_merge_text);
                }}
            }});
            mergeFindings(selected, mergeBtn);
        }});
    }}

    function mergeFindings(findings, btn) {{
        if (!latestSynthesisData) return;
        btn.disabled = true;
        btn.textContent = "Merging...";
        fetch("/dvi/packet/" + encodeURIComponent(PHOTO_RO) + "/merge-findings", {{
            method: "POST",
            headers: {{"Content-Type": "application/json"}},
            body: JSON.stringify({{
                synthesis_data: latestSynthesisData,
                requested_by: photoAnalysisRequester || "unknown",
                findings_count: latestFindingsCount || findings.length
            }})
        }})
        .then(function(resp) {{ return resp.json(); }})
        .then(function(data) {{
            var target = document.getElementById("mergeResult");
            target.innerHTML = '<div class="merge-success">' +
                '<span>' + data.findings_count + ' findings merged into packet — reload to see updated packet</span>' +
                '<button type="button" class="btn" onclick="window.location.reload()">Reload</button>' +
                '</div>';
        }})
        .catch(function(error) {{
            alert("Photo findings merge failed: " + error);
            btn.disabled = false;
            btn.textContent = "Merge confirmed findings into packet";
        }});
    }}

    function analyzeSelectedPhotos() {{
        var urls = selectedPhotoUrls();
        if (!urls.length || !analyzeBtn) return;
        var requester = prompt("Who is requesting this photo analysis?\\nType: Mitch, Drew, or Preston");
        if (!requester) return;
        requester = requester.trim();
        if (!requester) return;
        photoAnalysisRequester = requester;
        analyzeBtn.disabled = true;
        analyzeBtn.textContent = "Analyzing " + urls.length + " photos...";
        fetch("/dvi/packet/" + encodeURIComponent(PHOTO_RO) + "/analyze-photos", {{
            method: "POST",
            headers: {{"Content-Type": "application/json"}},
            body: JSON.stringify({{photo_urls: urls, requested_by: requester}})
        }})
        .then(function(resp) {{ return resp.json(); }})
        .then(function(data) {{
            photoAnalysisRequester = data.requested_by || requester;
            renderFindings(data);
            analyzeBtn.textContent = "Analyze selected photos";
            updatePhotoCounter();
        }})
        .catch(function(error) {{
            alert("Photo analysis failed: " + error);
            analyzeBtn.textContent = "Analyze selected photos";
            updatePhotoCounter();
        }});
    }}

    function escapeHtml(value) {{
        return String(value || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }}

    function customerizeExplanation(value) {{
        return String(value || "").replace(/the customer/gi, PACKET_CUSTOMER_FIRST);
    }}

    if (analyzeBtn) analyzeBtn.addEventListener("click", analyzeSelectedPhotos);
    updatePhotoCounter();
    </script>
</body>
</html>"""


def _render_no_stored_packet(ro: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>No Stored Packet - RO {_escape(ro)}</title>
    <style>
        body {{font-family:Arial,Helvetica,sans-serif;background:#0f172a;color:#e5e7eb;margin:0;padding:40px;}}
        .card {{max-width:720px;margin:0 auto;background:#111827;border:1px solid #334155;border-radius:16px;padding:28px;box-shadow:0 18px 42px rgba(0,0,0,.28);}}
        h1 {{margin:0 0 10px;font-size:28px;color:#fff;}}
        p {{color:#cbd5e1;line-height:1.6;}}
        .actions {{display:flex;gap:12px;margin-top:22px;flex-wrap:wrap;}}
        a {{display:inline-block;border-radius:10px;padding:11px 15px;text-decoration:none;font-weight:900;}}
        .build {{background:#185FA5;color:#fff;}}
        .history {{border:1px solid #475569;color:#cbd5e1;}}
    </style>
</head>
<body>
    <main class="card">
        <h1>No stored packet yet</h1>
        <p>RO {_escape(ro)} does not have a saved packet in the cache or permanent job history store. Opening this history route did not regenerate anything and did not call AutoFlow or AI.</p>
        <p>Build Packet is available only because no stored packet exists yet.</p>
        <div class="actions">
            <a class="build" href="/dvi/packet/{_escape(ro)}">Build Packet</a>
            <a class="history" href="/dvi/history">Back to History</a>
        </div>
    </main>
</body>
</html>"""


def render_packet_stored(ro):
    ro = str(ro).strip()
    latest = _latest_stored_packet(ro)
    if not latest:
        return Response(_render_no_stored_packet(ro), mimetype="text/html")

    packet = latest.get("packet") if isinstance(latest.get("packet"), dict) else {}
    cache = latest.get("cache") if isinstance(latest.get("cache"), dict) else {}
    if not cache:
        generated_at = _packet_generated_at(packet) or str(latest.get("generated_at") or datetime.utcnow().isoformat())
        cache = {
            "ro": ro,
            "generated_at": generated_at,
            "dvi_pulled_at": packet.get("dvi_pulled_at") or generated_at,
            "packet": packet,
            "packet_stale": packet.get("packet_stale") if isinstance(packet.get("packet_stale"), dict) else {},
            "generation_log": [{
                "timestamp": generated_at,
                "trigger": packet.get("trigger") or "stored_packet_open",
                "requested_by": packet.get("requested_by") or "cache",
                "dvi_item_count": packet.get("dvi_item_count") or 0,
                "api_cost_usd": 0,
            }],
            "total_cost_usd": 0,
            "analyzed_photos": [],
        }

    if packet:
        log_packet_cache_hit(ro, requested_by="history_view")
        return Response(_render_packet_html(ro, packet, cache=cache, include_photo_panel=False), mimetype="text/html")

    packet_html = str(latest.get("packet_html") or "")
    if packet_html:
        log_packet_cache_hit(ro, requested_by="history_view")
        return Response(packet_html, mimetype="text/html")

    return Response(_render_no_stored_packet(ro), mimetype="text/html")


def render_packet_history():
    rows = _packet_history_rows()
    row_html = []
    for row in rows:
        ro = str(row.get("ro") or "")
        generated = str(row.get("generated_at") or "")
        generated_display = format_ts(generated) if generated else "No stored packet"
        if row.get("has_packet"):
            action = f'<a class="open" href="/dvi/packet/{_escape(ro)}/stored">Open stored packet</a>'
            status_class = "ready"
            packet_state = "Stored packet ready"
        else:
            action = f'<a class="build" href="/dvi/packet/{_escape(ro)}">Build Packet</a>'
            status_class = "missing"
            packet_state = "No stored packet"
        row_html.append(
            "<tr>"
            f'<td class="ro">RO {_escape(ro)}</td>'
            f"<td>{_escape(row.get('customer') or 'Unknown')}</td>"
            f"<td>{_escape(row.get('vehicle') or '')}</td>"
            f"<td>{_escape(row.get('status') or '')}</td>"
            f"<td>{_escape(generated_display)}</td>"
            f'<td><span class="pill {status_class}">{packet_state}</span><br><small>{_escape(row.get("source") or "")}</small></td>'
            f"<td>{action}</td>"
            "</tr>"
        )
    if not row_html:
        row_html.append(
            '<tr><td colspan="7" class="empty">No completed, closed, or packet-history ROs found yet. Stored packets will appear here after packet generation.</td></tr>'
        )

    html_text = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Completed RO Packet History</title>
    <style>
        body {{font-family:Arial,Helvetica,sans-serif;background:#07111f;color:#e5e7eb;margin:0;padding:24px;}}
        .page {{max-width:1180px;margin:0 auto;}}
        .top {{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;margin-bottom:22px;}}
        h1 {{margin:0;color:#fff;font-size:30px;letter-spacing:.04em;}}
        .sub {{color:#94a3b8;margin-top:6px;font-size:14px;}}
        .back {{border:1px solid #334155;border-radius:10px;color:#cbd5e1;text-decoration:none;padding:10px 14px;font-weight:900;}}
        table {{width:100%;border-collapse:separate;border-spacing:0 10px;}}
        th {{text-align:left;color:#64748b;font-size:11px;text-transform:uppercase;letter-spacing:.08em;padding:0 12px;}}
        td {{background:#111827;border-top:1px solid #1e293b;border-bottom:1px solid #1e293b;padding:14px 12px;vertical-align:middle;}}
        td:first-child {{border-left:1px solid #1e293b;border-radius:12px 0 0 12px;}}
        td:last-child {{border-right:1px solid #1e293b;border-radius:0 12px 12px 0;}}
        .ro {{font-weight:900;color:#fff;}}
        .pill {{display:inline-block;border-radius:999px;padding:4px 9px;font-size:11px;font-weight:900;margin-bottom:4px;}}
        .pill.ready {{background:#064e3b;color:#86efac;border:1px solid #10b981;}}
        .pill.missing {{background:#451a03;color:#fdba74;border:1px solid #f97316;}}
        small {{color:#64748b;}}
        a.open,a.build {{display:inline-block;border-radius:9px;padding:9px 12px;text-decoration:none;font-weight:900;white-space:nowrap;}}
        a.open {{background:#185FA5;color:#fff;}}
        a.build {{background:#f59e0b;color:#111827;}}
        .empty {{text-align:center;color:#94a3b8;padding:28px;}}
    </style>
</head>
<body>
    <main class="page">
        <div class="top">
            <div>
                <h1>Completed RO Packet History</h1>
                <div class="sub">Cache-first view of completed and closed ROs. Opening a packet here does not regenerate, call AutoFlow, or use AI credits.</div>
            </div>
            <a class="back" href="/v2">Back to Board</a>
        </div>
        <table>
            <thead>
                <tr><th>RO</th><th>Customer</th><th>Vehicle</th><th>Status</th><th>Latest Packet Date</th><th>Packet State</th><th>Action</th></tr>
            </thead>
            <tbody>{''.join(row_html)}</tbody>
        </table>
    </main>
</body>
</html>"""
    return Response(html_text, mimetype="text/html")


def render_packet_page(ro):
    ro = str(ro).strip()
    cache = _load_cache(ro)
    if cache:
        cache = _refresh_packet_stale_state(ro, cache)

    if cache and cache.get("packet_html"):
        log_packet_cache_hit(ro)
        if cache.get("job_block_photo_findings_merged") and not _stale_changed(cache):
            return Response(str(cache.get("packet_html")), mimetype="text/html")
        packet = cache.get("packet") if isinstance(cache.get("packet"), dict) else {}
        if packet:
            return Response(_render_packet_html(ro, packet, cache=cache), mimetype="text/html")
        return Response(str(cache.get("packet_html")), mimetype="text/html")

    packet = build_packet(ro, force_refresh=False, requested_by="system")
    if packet.get("error"):
        return _render_error(ro, packet)

    cache = _make_cache(ro, packet, "", {}, "initial", "system")
    packet_html = _render_packet_html(ro, packet, cache=cache)
    cache["packet_html"] = packet_html
    _save_cache(ro, cache)
    return Response(packet_html, mimetype="text/html")


def render_packet_regenerate(ro):
    ro = str(ro).strip()
    requested_by = str(request.form.get("requested_by") or "unknown").strip() or "unknown"
    previous_cache = _load_cache(ro)
    packet = build_packet(ro, force_refresh=True, requested_by=requested_by)
    if packet.get("error"):
        return _render_error(ro, packet)

    cache = _make_cache(ro, packet, "", previous_cache, "regenerate", requested_by)
    packet_html = _render_packet_html(ro, packet, cache=cache, just_regenerated=True, requested_by=requested_by)
    cache["packet_html"] = packet_html
    _save_cache(ro, cache)
    try:
        return redirect(url_for("dvi_packet", ro=ro))
    except Exception:
        return Response(packet_html, mimetype="text/html")


def render_packet_analyze_photos(ro):
    ro = str(ro).strip()
    body = request.get_json(silent=True) or {}
    photo_urls = [str(url).strip() for url in _as_list(body.get("photo_urls")) if str(url).strip()]
    requested_by = str(body.get("requested_by") or "Drew").strip() or "Drew"
    findings = []
    cache = _load_cache(ro)
    packet = cache.get("packet") if isinstance(cache.get("packet"), dict) else {}

    for url in photo_urls:
        try:
            photo_b64, media_type = _download_photo(url)
            finding_text = _call_claude_vision(photo_b64, media_type)
        except (HTTPError, URLError, OSError, socket.timeout, json.JSONDecodeError, ValueError) as error:
            finding_text = f"Photo could not be loaded: {error}"
        finding_text = clean_ai_response_text(finding_text)
        has_value = _has_diagnostic_value(finding_text)
        findings.append({
            "photo_url": url,
            "thumbnail_url": url,
            "finding": finding_text,
            "has_diagnostic_value": has_value,
            "suggested_merge_text": _suggested_merge_text(finding_text) if has_value else "",
        })

    packet_html = str(cache.get("packet_html") or "")
    try:
        synthesis_data = _call_claude_synthesis(packet, findings, packet_html)
    except (HTTPError, URLError, OSError, socket.timeout, json.JSONDecodeError, ValueError) as error:
        print(f"Photo synthesis failed for RO {ro}: {error}")
        synthesis_data = _fallback_synthesis_data(findings, str(error))

    cost = len(photo_urls) * PHOTO_ANALYSIS_COST
    _append_api_cost_log({
        "timestamp": datetime.utcnow().isoformat(),
        "action": "photo_analysis",
        "trigger": "photo_analysis",
        "requested_by": requested_by,
        "ro": ro,
        "photos_analyzed": len(photo_urls),
        "cost_usd": cost,
        "estimated_cost_usd": cost,
        "cached": False,
    })

    analyzed = set(str(item) for item in _as_list(cache.get("analyzed_photos")))
    analyzed.update(photo_urls)
    cache["analyzed_photos"] = sorted(analyzed)
    _save_cache(ro, cache)

    return jsonify({
        "findings": findings,
        "synthesis_data": synthesis_data,
        "photos_analyzed": len(photo_urls),
        "cost_usd": cost,
        "requested_by": requested_by,
    })


def render_packet_merge_findings(ro):
    ro = str(ro).strip()
    body = request.get_json(silent=True) or {}
    requested_by = str(body.get("requested_by") or "Drew").strip() or "Drew"
    synthesis_data = _clean_synthesis_data(body.get("synthesis_data"), [])
    try:
        findings_count = int(body.get("findings_count") or 0)
    except (TypeError, ValueError):
        findings_count = 0
    cache = _load_cache(ro)
    timestamp = datetime.utcnow().isoformat()
    timestamp_display = format_ts(timestamp)
    packet = cache.get("packet") if isinstance(cache.get("packet"), dict) else {}
    customer_first = str(packet.get("customer") or "").split()[0] if str(packet.get("customer") or "").split() else "customer"
    cache["merged_photo_findings"] = {
        "timestamp": timestamp,
        "requested_by": requested_by,
        "synthesis_data": synthesis_data,
        "ro_notes_block": synthesis_data.get("ro_notes_block", ""),
        "unmatched_findings": synthesis_data.get("unmatched_findings", ""),
        "findings_count": findings_count,
    }
    generation_log = cache.get("generation_log") if isinstance(cache.get("generation_log"), list) else []
    generation_log.append({
        "timestamp": timestamp,
        "trigger": "photo_findings_merged",
        "requested_by": requested_by,
        "findings_count": findings_count,
        "api_cost_usd": 0,
    })
    cache["generation_log"] = generation_log

    merged_html = _render_merged_findings(cache)
    packet_html = str(cache.get("packet_html") or "")
    if packet_html:
        unmatched_from_failed_matches = []
        for item in _as_list(synthesis_data.get("job_findings")):
            packet_html, injected = _inject_finding_into_job_block(
                packet_html,
                item,
                requested_by,
                timestamp_display,
                customer_first,
            )
            if not injected:
                summary = item.get("technical_note") or item.get("ro_note") or item.get("job_title_match")
                if summary:
                    unmatched_from_failed_matches.append(clean_ai_response_text(summary))
        if unmatched_from_failed_matches:
            existing_unmatched = str(cache["merged_photo_findings"].get("unmatched_findings") or "").strip()
            combined_unmatched = "\n".join([existing_unmatched] + unmatched_from_failed_matches).strip()
            cache["merged_photo_findings"]["unmatched_findings"] = combined_unmatched
            merged_html = _render_merged_findings(cache)
        if PHOTO_FINDINGS_PLACEHOLDER in packet_html:
            packet_html = packet_html.replace(PHOTO_FINDINGS_PLACEHOLDER, merged_html)
        elif 'id="photo-findings-merged"' in packet_html:
            start = packet_html.find('<div id="photo-findings-merged"')
            if start == -1:
                start = packet_html.find('<section id="photo-findings-merged"')
            next_section = packet_html.find('<section class="generation-log"', start)
            if start != -1 and next_section != -1:
                packet_html = packet_html[:start] + merged_html + "\n\n        " + packet_html[next_section:]
            else:
                packet_html += merged_html
        else:
            packet_html += merged_html
        cache["packet_html"] = packet_html
        cache["job_block_photo_findings_merged"] = True

    _save_cache(ro, cache)
    return jsonify({"status": "merged", "findings_count": findings_count})
