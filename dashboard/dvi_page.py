"""
DVI workflow lifecycle page.

This page is intentionally deterministic: it only reads local board/review/cache
state and never calls AutoFlow or AI while rendering.
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DVI_REVIEWS_DIR = ROOT / "state" / "dvi_reviews"
SHOP_STATE_PATH = ROOT / "state" / "shop_state.json"
BOARD_STATE_PATH = ROOT / "state" / "board_state.json"


STATUS_ALIASES = {
    "waiting_approval": "waiting approval",
    "waiting parts": "waiting parts",
    "waiting_parts": "waiting parts",
    "ordering_parts": "ordering parts",
    "call shop": "call_shop",
    "call-shop": "call_shop",
    "estimate": "advisor estimate",
    "est": "advisor estimate",
    "in progress": "servicing",
    "servicing / in progress": "servicing",
    "advisor_qc_review": "advisor qc review",
    "advisor_finalize_ro": "advisor finalize ro",
    "dvi only- not here": "dvi only-not here",
    "online /stage": "online/stage",
    "drop off/ tow-in": "drop off/tow-in",
    "closed": "close",
}

DONE_STATUSES = {"close", "finished"}
DONE_OTHER_STATUSES = {"ready", "advisor finalize ro"}
ADVISOR_QC_STATUSES = {"advisor qc review"}
IN_PROGRESS_STATUSES = {
    "servicing",
    "inspecting",
    "testing",
    "dvi updates",
    "ready for tech",
    "awaiting tech",
    "technical advisement",
    "technical overview",
    "k_mech_complete",
    "checkin",
    "qc",
    "drop off/tow-in",
    "online/stage",
    "waiting approval",
    "ordering parts",
    "waiting parts",
    "parts",
}

LANES = [
    {
        "key": "needs_rework",
        "title": "Needs Rework",
        "subtitle": "DVI failed gate and needs correction before packet/estimate work.",
        "tone": "red",
    },
    {
        "key": "advisor_qc_review",
        "title": "Advisor QC Review",
        "subtitle": "Advisor needs to review documentation before closeout.",
        "tone": "violet",
    },
    {
        "key": "in_progress",
        "title": "In Progress",
        "subtitle": "RO is still moving through production, parts, approval, or QC.",
        "tone": "blue",
    },
    {
        "key": "tekmetric_ready",
        "title": "TekMetric Ready",
        "subtitle": "Packet exists and is current with the latest DVI snapshot.",
        "tone": "green",
    },
    {
        "key": "ready_for_build_packet",
        "title": "Ready For Build Packet",
        "subtitle": "Clean/pre-work ROs that still need a packet built or refreshed.",
        "tone": "amber",
    },
    {
        "key": "done",
        "title": "Recently Done",
        "subtitle": "Ready, finished, or closed ROs from the last 24 hours. Older packets live in History.",
        "tone": "slate",
    },
]


def _parse_dt(value: object) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _time_ago(value: object) -> str:
    dt = _parse_dt(value)
    if not dt:
        return "unknown"
    delta = _now_utc() - dt
    seconds = max(0, int(delta.total_seconds()))
    minutes = seconds // 60
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h {minutes % 60}m ago"
    days = hours // 24
    return f"{days}d ago"


def _display_ts(value: object) -> str:
    dt = _parse_dt(value)
    if not dt:
        return "unknown"
    local = dt.astimezone(timezone(timedelta(hours=-7)))
    hour = local.hour % 12 or 12
    ampm = "AM" if local.hour < 12 else "PM"
    return f"{local.strftime('%b')} {local.day}, {hour}:{local.strftime('%M')} {ampm}"


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _ro_id(value: dict) -> str:
    return str(
        value.get("ro")
        or value.get("invoice")
        or value.get("repair_order")
        or value.get("repair_order_id")
        or ""
    ).strip()


def _normalize_status(status: object) -> str:
    raw = str(status or "").lower().strip()
    raw = raw.replace("_", " ")
    raw = " ".join(raw.split())
    return STATUS_ALIASES.get(raw, raw)


def _load_jobs_by_ro() -> dict[str, dict]:
    jobs: dict[str, dict] = {}
    for path in (SHOP_STATE_PATH, BOARD_STATE_PATH):
        data = _read_json(path)
        for job in data.get("jobs", []) or data.get("active_ros", []) or []:
            if not isinstance(job, dict):
                continue
            ro = _ro_id(job)
            if not ro:
                continue
            existing = jobs.get(ro, {})
            merged = {**existing, **job}
            jobs[ro] = merged
    return jobs


def _load_all_reviews() -> dict[str, dict]:
    reviews: dict[str, dict] = {}
    if not DVI_REVIEWS_DIR.exists():
        return reviews

    for path in DVI_REVIEWS_DIR.glob("*.json"):
        name = path.name.lower()
        if (
            name.startswith("packet_")
            or name.endswith("_packet.json")
            or name.startswith("rework_slip")
        ):
            continue
        review = _read_json(path)
        if not isinstance(review, dict):
            continue
        if "review_status" not in review:
            continue
        ro = _ro_id(review)
        if ro:
            reviews[ro] = review
    return reviews


def _packet_paths(ro: str) -> tuple[Path, Path]:
    return (
        DVI_REVIEWS_DIR / f"{ro}_packet.json",
        DVI_REVIEWS_DIR / f"packet_{ro}.json",
    )


def _latest_history_packet(ro: str) -> Path | None:
    history_dir = ROOT / "state" / "job_history" / ro
    if not history_dir.exists():
        return None
    packets = sorted(history_dir.glob("packet_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return packets[0] if packets else None


def _packet_status(ro: str) -> dict:
    cache_path, legacy_path = _packet_paths(ro)
    data = {}
    source = ""

    if cache_path.exists():
        data = _read_json(cache_path)
        source = "cache"
    elif legacy_path.exists():
        data = _read_json(legacy_path)
        source = "legacy"

    if not data:
        history = _latest_history_packet(ro)
        if history:
            return {
                "exists": True,
                "current": False,
                "stale": False,
                "state": "stored history",
                "generated_at": datetime.fromtimestamp(history.stat().st_mtime, tz=timezone.utc).isoformat(),
                "source": "history",
            }
        return {
            "exists": False,
            "current": False,
            "stale": False,
            "state": "no packet yet",
            "generated_at": "",
            "source": "",
        }

    packet = data.get("packet") if isinstance(data.get("packet"), dict) else data
    stale_info = data.get("packet_stale") or packet.get("packet_stale") or {}
    stale = stale_info.get("changed") is True
    hash_present = bool(data.get("dvi_snapshot_hash") or packet.get("dvi_snapshot_hash"))
    current = bool(hash_present and not stale)

    generated_at = (
        data.get("generated_at")
        or packet.get("generated_at")
        or data.get("fetched_at")
        or packet.get("fetched_at")
        or ""
    )

    if stale:
        state = "stale - regenerate"
    elif current:
        state = "current"
    else:
        state = "packet exists - currency unknown"

    return {
        "exists": True,
        "current": current,
        "stale": stale,
        "state": state,
        "generated_at": generated_at,
        "source": source,
    }


def _gate_ran_at(review: dict) -> str:
    return str(
        review.get("dvi_pulled_at")
        or review.get("gate_ran_at")
        or review.get("reviewed_at")
        or review.get("created_at")
        or review.get("timestamp")
        or ""
    )


def _review_resolved(review: dict) -> bool:
    return bool(
        review.get("advisor_acknowledged")
        or review.get("acknowledged")
        or review.get("resolved")
        or review.get("dvi_acknowledged")
    )


def _recent_done(record: dict) -> bool:
    candidates = [
        record.get("status_updated_at"),
        record.get("updated_at"),
        record.get("generated_at"),
        record.get("gate_ran_at"),
    ]
    for candidate in candidates:
        dt = _parse_dt(candidate)
        if dt:
            return (_now_utc() - dt) <= timedelta(hours=24)
    return True


def assign_dvi_lane(record: dict) -> str:
    """Assign a DVI workflow row to exactly one lifecycle lane."""
    status = _normalize_status(record.get("workflow_status"))
    review_status = str(record.get("review_status") or "").upper().strip()
    packet = record.get("packet_status") or {}

    if status in DONE_STATUSES:
        return "done"
    if review_status == "REWORK_REQUIRED" and not record.get("review_resolved"):
        return "needs_rework"
    if status in ADVISOR_QC_STATUSES:
        return "advisor_qc_review"
    if status in IN_PROGRESS_STATUSES:
        return "in_progress"
    if status in DONE_OTHER_STATUSES:
        return "done"
    if packet.get("current"):
        return "tekmetric_ready"
    return "ready_for_build_packet"


def _build_records() -> list[dict]:
    jobs = _load_jobs_by_ro()
    reviews = _load_all_reviews()
    all_ros = sorted(set(jobs) | set(reviews), key=lambda x: int(x) if x.isdigit() else x)
    records: list[dict] = []

    for ro in all_ros:
        job = jobs.get(ro, {})
        review = reviews.get(ro, {})
        workflow_status = (
            job.get("workflow_status")
            or job.get("status")
            or review.get("workflow_status")
            or "unknown"
        )
        packet_status = _packet_status(ro)
        flags = review.get("flags") if isinstance(review.get("flags"), list) else []
        gate_ran_at = _gate_ran_at(review)
        review_status = str(review.get("review_status") or "NO_REVIEW").upper().strip()

        record = {
            "ro": ro,
            "customer": job.get("customer") or review.get("customer") or "Unknown Customer",
            "vehicle": job.get("vehicle") or review.get("vehicle") or "",
            "workflow_status": workflow_status,
            "normalized_status": _normalize_status(workflow_status),
            "review_status": review_status,
            "review_resolved": _review_resolved(review),
            "advisor_acknowledged": bool(review.get("advisor_acknowledged")),
            "gate_ran_at": gate_ran_at,
            "flag_count": len(flags),
            "critical_count": sum(
                1 for flag in flags if str(flag.get("severity", "")).upper() in {"REWORK", "CRITICAL"}
            ),
            "packet_status": packet_status,
            "status_updated_at": job.get("status_updated_at") or job.get("last_updated_at") or "",
            "updated_at": job.get("updated_at") or "",
            "generated_at": job.get("generated_at") or "",
        }
        record["lane"] = assign_dvi_lane(record)
        records.append(record)

    return records


def _lane_records(records: list[dict]) -> dict[str, list[dict]]:
    lanes = {lane["key"]: [] for lane in LANES}
    seen: set[str] = set()
    for record in records:
        ro = record["ro"]
        if ro in seen:
            continue
        seen.add(ro)
        lane = record["lane"]
        if lane == "done" and not _recent_done(record):
            continue
        lanes.setdefault(lane, []).append(record)

    for lane_items in lanes.values():
        lane_items.sort(
            key=lambda r: (
                0 if r.get("review_status") == "REWORK_REQUIRED" else 1,
                0 if r.get("packet_status", {}).get("stale") else 1,
                r.get("ro", ""),
            )
        )
    return lanes


def _status_badge(review_status: str) -> str:
    status = str(review_status or "NO_REVIEW").upper()
    classes = {
        "PASS": "pass",
        "REVIEW": "review",
        "REWORK_REQUIRED": "rework",
        "NO_REVIEW": "none",
    }
    labels = {
        "PASS": "Gate Pass",
        "REVIEW": "Review",
        "REWORK_REQUIRED": "Rework Required",
        "NO_REVIEW": "No Gate Run",
    }
    cls = classes.get(status, "none")
    label = labels.get(status, status.replace("_", " ").title())
    return f'<span class="badge {cls}">{html.escape(label)}</span>'


def _packet_badge(packet: dict) -> str:
    state = packet.get("state", "no packet yet")
    if packet.get("stale"):
        cls = "packet-stale"
    elif packet.get("current"):
        cls = "packet-ready"
    elif packet.get("exists"):
        cls = "packet-unknown"
    else:
        cls = "packet-missing"
    return f'<span class="packet {cls}">{html.escape(state)}</span>'


def _packet_action(ro: str, packet: dict) -> str:
    if packet.get("exists"):
        href = f"/dvi/packet/{html.escape(ro)}/stored"
        label = "Open Stored Packet"
    else:
        href = f"/dvi/packet/{html.escape(ro)}"
        label = "Build Packet"
    return f'<a class="action-link" href="{href}">{label}</a>'


def _card_actions(record: dict) -> str:
    ro = html.escape(record["ro"])
    actions = []
    if record.get("lane") == "needs_rework":
        slip_path = DVI_REVIEWS_DIR / f"rework_slip_{record['ro']}.html"
        if slip_path.exists():
            actions.append(f'<a class="action-link secondary" href="/dvi/slip/{ro}" target="_blank">Print Slip</a>')
        actions.append(f'<a class="action-link secondary" href="/dvi/acknowledge/{ro}">Acknowledge</a>')
    actions.append(_packet_action(ro, record.get("packet_status", {})))
    return "\n".join(actions)


def _render_card(record: dict) -> str:
    ro = html.escape(record["ro"])
    packet = record.get("packet_status", {})
    pulse = ""
    if record.get("lane") == "needs_rework":
        pulse = " pulse-red" if record.get("review_status") == "REWORK_REQUIRED" else " pulse-amber"

    gate_value = record.get("gate_ran_at")
    packet_time = packet.get("generated_at")
    return f"""
      <article class="dvi-card{pulse}">
        <div class="card-head">
          <div>
            <div class="ro">RO {ro}</div>
            <div class="customer">{html.escape(str(record.get("customer") or "Unknown Customer"))}</div>
            <div class="vehicle">{html.escape(str(record.get("vehicle") or ""))}</div>
          </div>
          {_status_badge(record.get("review_status"))}
        </div>
        <div class="meta-grid">
          <div><span>Workflow</span><strong>{html.escape(str(record.get("workflow_status") or "unknown"))}</strong></div>
          <div><span>Gate Ran</span><strong title="{html.escape(str(gate_value or ''))}">{html.escape(_display_ts(gate_value))}</strong></div>
          <div><span>TekMetric Ready</span><strong>{_packet_badge(packet)}</strong></div>
          <div><span>Packet Time</span><strong>{html.escape(_time_ago(packet_time))}</strong></div>
        </div>
        <div class="card-foot">
          <span>{int(record.get("flag_count") or 0)} flags · {int(record.get("critical_count") or 0)} critical</span>
          <div class="actions">
            {_card_actions(record)}
          </div>
        </div>
      </article>
    """


def _render_lane(lane: dict, records: list[dict]) -> str:
    cards = "\n".join(_render_card(record) for record in records)
    if not cards:
        cards = '<div class="empty">Nothing here right now.</div>'
    return f"""
      <section class="lane {lane['tone']}">
        <div class="lane-head">
          <div>
            <h2>{html.escape(lane['title'])}</h2>
            <p>{html.escape(lane['subtitle'])}</p>
          </div>
          <span class="count">{len(records)}</span>
        </div>
        <div class="lane-body">{cards}</div>
      </section>
    """


def render_dvi_page() -> str:
    records = _build_records()
    lanes = _lane_records(records)
    active_count = sum(len(lanes[lane["key"]]) for lane in LANES if lane["key"] != "done")
    done_count = len(lanes.get("done", []))
    duplicate_count = len(records) - len({record["ro"] for record in records})
    generated_at = _display_ts(_now_utc().isoformat())

    lane_html = "\n".join(_render_lane(lane, lanes.get(lane["key"], [])) for lane in LANES)

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DVI Workflow | Callahan Auto</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #08111f;
      --panel: #0f172a;
      --line: #1e293b;
      --text: #f8fafc;
      --muted: #94a3b8;
      --red: #ef4444;
      --amber: #f59e0b;
      --green: #22c55e;
      --blue: #38bdf8;
      --violet: #a855f7;
      --slate: #64748b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background:
        radial-gradient(circle at 20% 0%, rgba(56,189,248,.18), transparent 30%),
        radial-gradient(circle at 80% 0%, rgba(168,85,247,.14), transparent 28%),
        var(--bg);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      -webkit-font-smoothing: antialiased;
    }}
    header {{
      padding: 24px 28px 18px;
      border-bottom: 1px solid var(--line);
      background: rgba(8,17,31,.92);
      position: sticky;
      top: 0;
      z-index: 10;
      backdrop-filter: blur(14px);
    }}
    .top-row {{ display:flex; justify-content:space-between; gap:18px; align-items:flex-start; }}
    h1 {{ margin:0; font-size:28px; letter-spacing:.02em; }}
    .sub {{ color:var(--muted); margin-top:6px; font-size:13px; }}
    .nav {{ display:flex; gap:10px; flex-wrap:wrap; }}
    .nav a {{
      color:var(--text);
      text-decoration:none;
      border:1px solid #334155;
      background:#0f172a;
      border-radius:999px;
      padding:8px 12px;
      font-size:12px;
      font-weight:800;
    }}
    .stats {{ display:flex; gap:12px; margin-top:18px; flex-wrap:wrap; }}
    .stat {{
      min-width:150px;
      border:1px solid var(--line);
      background:rgba(15,23,42,.78);
      border-radius:14px;
      padding:12px 14px;
    }}
    .stat b {{ display:block; font-size:26px; }}
    .stat span {{ color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:.08em; }}
    main {{ padding:22px 28px 34px; }}
    .lane {{
      border:1px solid var(--line);
      background:rgba(15,23,42,.72);
      border-radius:20px;
      margin-bottom:20px;
      overflow:hidden;
      box-shadow:0 18px 40px rgba(0,0,0,.24);
    }}
    .lane.red {{ border-color:rgba(239,68,68,.45); }}
    .lane.violet {{ border-color:rgba(168,85,247,.45); }}
    .lane.blue {{ border-color:rgba(56,189,248,.42); }}
    .lane.green {{ border-color:rgba(34,197,94,.42); }}
    .lane.amber {{ border-color:rgba(245,158,11,.42); }}
    .lane.slate {{ border-color:rgba(100,116,139,.55); }}
    .lane-head {{
      display:flex;
      justify-content:space-between;
      align-items:center;
      padding:16px 18px;
      border-bottom:1px solid rgba(148,163,184,.14);
      background:linear-gradient(90deg, rgba(255,255,255,.055), rgba(255,255,255,.015));
    }}
    .lane-head h2 {{ margin:0; font-size:17px; text-transform:uppercase; letter-spacing:.08em; }}
    .lane-head p {{ margin:4px 0 0; color:var(--muted); font-size:12px; }}
    .count {{
      display:grid;
      place-items:center;
      min-width:36px;
      height:32px;
      border-radius:12px;
      background:rgba(255,255,255,.08);
      font-weight:900;
    }}
    .lane-body {{
      display:grid;
      grid-template-columns:repeat(auto-fill, minmax(340px, 1fr));
      gap:14px;
      padding:16px;
    }}
    .dvi-card {{
      position:relative;
      border:1px solid rgba(148,163,184,.22);
      background:linear-gradient(180deg, rgba(30,41,59,.96), rgba(15,23,42,.96));
      border-radius:18px;
      padding:16px;
      overflow:hidden;
    }}
    .dvi-card:before {{
      content:"";
      position:absolute;
      left:0;
      top:0;
      bottom:0;
      width:5px;
      background:var(--blue);
    }}
    .lane.red .dvi-card:before {{ background:var(--red); }}
    .lane.violet .dvi-card:before {{ background:var(--violet); }}
    .lane.green .dvi-card:before {{ background:var(--green); }}
    .lane.amber .dvi-card:before {{ background:var(--amber); }}
    .lane.slate .dvi-card:before {{ background:var(--slate); }}
    .card-head {{ display:flex; justify-content:space-between; gap:12px; align-items:flex-start; }}
    .ro {{ font-size:18px; font-weight:950; letter-spacing:.02em; }}
    .customer {{ margin-top:5px; font-size:13px; font-weight:800; }}
    .vehicle {{ color:var(--muted); font-size:12px; margin-top:2px; }}
    .badge, .packet {{
      display:inline-flex;
      align-items:center;
      border-radius:999px;
      padding:5px 8px;
      font-size:10px;
      font-weight:900;
      text-transform:uppercase;
      letter-spacing:.06em;
      white-space:nowrap;
    }}
    .badge.pass, .packet-ready {{ color:#bbf7d0; border:1px solid rgba(34,197,94,.55); background:rgba(34,197,94,.13); }}
    .badge.review, .packet-unknown {{ color:#fde68a; border:1px solid rgba(245,158,11,.55); background:rgba(245,158,11,.12); }}
    .badge.rework, .packet-stale {{ color:#fecaca; border:1px solid rgba(239,68,68,.6); background:rgba(239,68,68,.14); }}
    .badge.none, .packet-missing {{ color:#cbd5e1; border:1px solid rgba(148,163,184,.35); background:rgba(148,163,184,.10); }}
    .meta-grid {{
      display:grid;
      grid-template-columns:1fr 1fr;
      gap:10px;
      margin-top:15px;
    }}
    .meta-grid div {{
      border:1px solid rgba(148,163,184,.14);
      background:rgba(2,6,23,.28);
      border-radius:12px;
      padding:10px;
      min-height:58px;
    }}
    .meta-grid span {{
      display:block;
      color:var(--muted);
      font-size:10px;
      text-transform:uppercase;
      letter-spacing:.08em;
      margin-bottom:5px;
    }}
    .meta-grid strong {{ font-size:12px; overflow-wrap:anywhere; }}
    .card-foot {{
      display:flex;
      justify-content:space-between;
      gap:12px;
      align-items:center;
      margin-top:14px;
      color:var(--muted);
      font-size:12px;
    }}
    .actions {{ display:flex; gap:8px; flex-wrap:wrap; justify-content:flex-end; }}
    .action-link {{
      color:#dbeafe;
      text-decoration:none;
      border:1px solid rgba(59,130,246,.45);
      background:rgba(59,130,246,.14);
      border-radius:999px;
      padding:6px 9px;
      font-size:11px;
      font-weight:800;
    }}
    .action-link.secondary {{ color:#c4b5fd; border-color:rgba(168,85,247,.38); background:rgba(168,85,247,.12); }}
    .empty {{
      color:var(--muted);
      border:1px dashed rgba(148,163,184,.24);
      border-radius:16px;
      padding:22px;
      text-align:center;
      font-size:13px;
    }}
    @keyframes pulseRed {{
      0%,100% {{ box-shadow:0 0 0 1px rgba(239,68,68,.65), 0 0 14px rgba(239,68,68,.30); }}
      50% {{ box-shadow:0 0 0 3px rgba(239,68,68,.9), 0 0 24px rgba(239,68,68,.55); }}
    }}
    @keyframes pulseAmber {{
      0%,100% {{ box-shadow:0 0 0 1px rgba(245,158,11,.55), 0 0 12px rgba(245,158,11,.25); }}
      50% {{ box-shadow:0 0 0 3px rgba(245,158,11,.85), 0 0 22px rgba(245,158,11,.45); }}
    }}
    .pulse-red {{ animation:pulseRed 2.4s ease-in-out infinite; }}
    .pulse-amber {{ animation:pulseAmber 2.4s ease-in-out infinite; }}
    @media (prefers-reduced-motion: reduce) {{
      .pulse-red, .pulse-amber {{ animation:none !important; }}
    }}
    @media (max-width: 760px) {{
      header, main {{ padding-left:14px; padding-right:14px; }}
      .top-row, .card-foot {{ flex-direction:column; align-items:flex-start; }}
      .lane-body {{ grid-template-columns:1fr; }}
      .meta-grid {{ grid-template-columns:1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="top-row">
      <div>
        <h1>DVI Workflow</h1>
        <div class="sub">Lifecycle lanes from workflow status, DVI gate result, and packet cache state. Generated {html.escape(generated_at)}.</div>
      </div>
      <nav class="nav">
        <a href="/v2">Command Board</a>
        <a href="/dvi/history">Packet History</a>
        <a href="/sanity-check">Sanity Check</a>
      </nav>
    </div>
    <div class="stats">
      <div class="stat"><b>{len(records)}</b><span>Total DVI Rows</span></div>
      <div class="stat"><b>{active_count}</b><span>Active Lanes</span></div>
      <div class="stat"><b>{done_count}</b><span>Recently Done</span></div>
      <div class="stat"><b>{duplicate_count}</b><span>Duplicate Listings</span></div>
    </div>
  </header>
  <main>
    {lane_html}
  </main>
</body>
</html>"""
