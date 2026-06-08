"""
AdviseMe Command Board v2.
"""

from __future__ import annotations

import json
from pathlib import Path

from flask import Response

from board_loader import _load_board_state


REPO_ROOT = Path(__file__).resolve().parents[1]
DVI_REVIEWS_DIR = REPO_ROOT / "state" / "dvi_reviews"
PRIORITY_ORDER = {"P1": 0, "P2": 1, "P2A": 1, "P2B": 1, "P2C": 1, "P3": 2, "P4": 3}


def _priority(job: dict) -> str:
    return str(job.get("priority_lane") or job.get("priority") or "P4").upper()


def _risk_rank(job: dict) -> int:
    return 0 if str(job.get("risk_level") or "").upper() == "CRITICAL" else 1


def _incoming_rank(job: dict) -> int:
    incoming = job.get("incoming_soon")
    return 0 if isinstance(incoming, dict) and incoming.get("active") is True else 1


def _packet_built(ro) -> bool:
    ro_text = str(ro or "").strip()
    return bool(ro_text and (DVI_REVIEWS_DIR / f"packet_{ro_text}.json").exists())


def _dvi_review_meta(ro) -> dict:
    ro_text = str(ro or "").strip()
    path = DVI_REVIEWS_DIR / f"{ro_text}.json"
    if not ro_text or not path.exists():
        return {"flag_count": 0, "critical_count": 0}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"flag_count": 0, "critical_count": 0}
    flags = data.get("flags", []) if isinstance(data, dict) else []
    if not isinstance(flags, list):
        flags = []
    critical = sum(1 for flag in flags if isinstance(flag, dict) and flag.get("severity") == "critical")
    return {"flag_count": len(flags), "critical_count": critical}


def _sort_key(job: dict):
    return (
        PRIORITY_ORDER.get(_priority(job), 9),
        _risk_rank(job),
        _incoming_rank(job),
        str(job.get("ro") or ""),
    )


def render_board_v2() -> Response:
    board_state = _load_board_state()
    jobs = board_state.get("jobs", []) if isinstance(board_state, dict) else []
    enriched_jobs = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        row = dict(job)
        row["packet_built"] = _packet_built(row.get("ro"))
        row["dvi_review_meta"] = _dvi_review_meta(row.get("ro"))
        enriched_jobs.append(row)
    enriched_jobs.sort(key=_sort_key)

    jobs_json = json.dumps(enriched_jobs, ensure_ascii=False).replace("</", "<\\/")
    generated_at = json.dumps(board_state.get("generated_at") or "")
    html = HTML_TEMPLATE.replace("__BOARD_JOBS__", jobs_json).replace("__GENERATED_AT__", generated_at)
    return Response(html, mimetype="text/html")


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AdviseMe Command Board</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-main: #050816;
            --bg-card: #0F172A;
            --bg-panel: #0B1220;
            --border-soft: #1E293B;
            --border-medium: #334155;
            --text-primary: #F8FAFC;
            --text-secondary: #CBD5E1;
            --text-muted: #94A3B8;
            --text-faint: #64748B;
            --status-immediate: #FF3B30;
            --status-immediate-bg: rgba(255,59,48,0.12);
            --status-immediate-border: rgba(255,59,48,0.75);
            --status-immediate-glow: rgba(255,59,48,0.48);
            --status-customer: #FF9500;
            --status-customer-bg: rgba(255,149,0,0.12);
            --status-customer-border: rgba(255,149,0,0.70);
            --status-customer-glow: rgba(255,149,0,0.40);
            --status-progress: #3B82F6;
            --status-progress-bg: rgba(59,130,246,0.12);
            --status-progress-border: rgba(59,130,246,0.65);
            --status-ready: #22C55E;
            --status-ready-bg: rgba(34,197,94,0.13);
            --status-ready-border: rgba(34,197,94,0.68);
            --status-parts: #00E5FF;
            --status-parts-bg: rgba(0,229,255,0.12);
            --status-parts-border: rgba(0,229,255,0.68);
            --status-ai: #A855F7;
            --status-ai-bg: rgba(168,85,247,0.14);
            --status-ai-border: rgba(168,85,247,0.72);
            --status-ai-glow: rgba(168,85,247,0.45);
            --p1-bg: #FF2D2D;
            --p2-bg: #FF7A00;
            --p3-bg: #FFD400;
            --p3-text: #111827;
        }

        * { box-sizing: border-box; }
        html, body { height: 100%; }
        body {
            margin: 0;
            height: 100vh;
            overflow: hidden;
            display: grid;
            grid-template-rows: 78px 1fr 190px 56px;
            grid-template-columns: 1fr;
            background: radial-gradient(circle at top left, #111B3A 0%, #050816 38%, #020617 100%);
            color: var(--text-primary);
            font-family: Inter, system-ui, -apple-system, sans-serif;
        }

        .topbar {
            grid-row: 1;
            display: grid;
            grid-template-columns: 240px 1fr 440px;
            align-items: center;
            gap: 12px;
            padding: 10px;
            border-bottom: 1px solid var(--border-soft);
            background: rgba(2, 6, 23, 0.72);
        }
        .brand-main { font-size: 18px; font-weight: 800; color: #fff; letter-spacing: 0.03em; }
        .brand-sub { margin-top: 3px; font-size: 10px; font-weight: 700; letter-spacing: 0.16em; color: var(--status-ai); text-transform: uppercase; }
        .kpis { display: flex; justify-content: center; gap: 8px; min-width: 0; }
        .kpi {
            width: 90px;
            height: 56px;
            border-radius: 10px;
            border: 1px solid var(--border-soft);
            background: var(--bg-card);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
        }
        .kpi .num { font-size: 28px; font-weight: 900; line-height: 1; }
        .kpi .label { margin-top: 5px; font-size: 9px; font-weight: 700; letter-spacing: 0.06em; color: var(--text-faint); text-transform: uppercase; }
        .top-actions { display: grid; grid-template-columns: 108px 1fr; align-items: center; gap: 12px; }
        .clock { text-align: right; }
        .clock-time { font-size: 20px; font-weight: 800; color: #fff; line-height: 1; }
        .clock-date, .last-update { margin-top: 4px; font-size: 11px; color: var(--text-secondary); }
        .action-buttons { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 6px; }
        .action-buttons a {
            height: 28px;
            border-radius: 6px;
            border: 1px solid var(--border-medium);
            background: transparent;
            color: var(--text-muted);
            font-size: 10px;
            font-weight: 700;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            padding: 0 9px;
        }
        .legend {
            position: fixed;
            top: 78px;
            left: 0;
            right: 0;
            z-index: 15;
            height: 22px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 14px;
            border-bottom: 1px solid rgba(30,41,59,0.75);
            background: rgba(5, 8, 22, 0.88);
            color: var(--text-faint);
            font-size: 9px;
            font-weight: 700;
        }
        .legend-dot, .status-dot {
            display: inline-block;
            border-radius: 999px;
            vertical-align: middle;
        }
        .legend-dot { width: 8px; height: 8px; margin-right: 4px; }

        .board {
            grid-row: 2;
            display: grid;
            grid-template-columns: repeat(6, minmax(180px, 1fr));
            gap: 10px;
            padding: 32px 10px 10px;
            overflow: hidden;
        }
        .column {
            min-width: 0;
            overflow-y: auto;
            padding: 10px;
            border-radius: 16px;
            border: 1px solid var(--border-soft);
            background: rgba(15,23,42,0.62);
        }
        .column::-webkit-scrollbar, .drawer::-webkit-scrollbar { width: 7px; }
        .column::-webkit-scrollbar-thumb, .drawer::-webkit-scrollbar-thumb { background: var(--border-medium); border-radius: 999px; }
        .column-header {
            height: 56px;
            border-radius: 12px;
            margin-bottom: 10px;
            padding: 0 12px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            border: 1px solid;
            font-size: 12px;
            font-weight: 900;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }
        .count-badge { min-width: 28px; height: 24px; display: inline-flex; align-items: center; justify-content: center; border-radius: 999px; background: rgba(255,255,255,0.08); color: #fff; }
        .immediate { color: var(--status-immediate); background: var(--status-immediate-bg); border-color: var(--status-immediate-border); box-shadow: 0 0 22px var(--status-immediate-glow); }
        .customer { color: var(--status-customer); background: var(--status-customer-bg); border-color: var(--status-customer-border); box-shadow: 0 0 18px var(--status-customer-glow); }
        .other { color: #FFD400; background: rgba(255,212,0,0.11); border-color: rgba(255,212,0,0.60); }
        .progress { color: var(--status-progress); background: var(--status-progress-bg); border-color: var(--status-progress-border); }
        .ready { color: var(--status-ready); background: var(--status-ready-bg); border-color: var(--status-ready-border); }
        .parts { color: var(--status-parts); background: var(--status-parts-bg); border-color: var(--status-parts-border); }

        .job-card {
            min-height: 120px;
            border-radius: 14px;
            background: linear-gradient(180deg, rgba(15,23,42,0.96), rgba(2,6,23,0.94));
            border: 1px solid var(--border-medium);
            padding: 12px;
            margin-bottom: 10px;
            cursor: pointer;
            transition: all 0.18s ease;
        }
        .job-card:hover { transform: translateY(-2px); border-color: var(--text-faint); }
        .job-card.p1 { animation: p1Pulse 2.4s ease-in-out infinite; }
        @keyframes p1Pulse {
            0%,100% { box-shadow: 0 0 18px rgba(255,59,48,.24); }
            50% { box-shadow: 0 0 34px rgba(255,59,48,.55); }
        }
        .card-top, .card-bottom { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
        .ro { font-size: 16px; font-weight: 900; color: #fff; }
        .priority {
            height: 24px;
            min-width: 31px;
            padding: 0 8px;
            border-radius: 7px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 11px;
            font-weight: 800;
            color: #fff;
        }
        .priority.p1 { background: var(--p1-bg); }
        .priority.p2 { background: var(--p2-bg); }
        .priority.p3 { background: var(--p3-bg); color: var(--p3-text); }
        .priority.p4 { background: var(--status-ready); color: #052e16; }
        .customer-name { margin-top: 8px; font-size: 13px; font-weight: 600; color: #E2E8F0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .vehicle { margin-top: 3px; font-size: 12px; font-weight: 500; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .action { margin-top: 10px; font-size: 12px; font-weight: 800; letter-spacing: 0.04em; text-transform: uppercase; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .detail { margin-top: 5px; font-size: 11px; color: var(--text-faint); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .small-pill { height: 20px; border-radius: 999px; padding: 0 8px; display: inline-flex; align-items: center; font-size: 10px; font-weight: 800; text-transform: uppercase; border: 1px solid currentColor; }
        .time-waiting { font-size: 12px; font-weight: 800; }
        .incoming-pill { margin-top: 8px; display: inline-flex; height: 20px; align-items: center; border-radius: 999px; padding: 0 8px; background: rgba(255,212,0,0.12); border: 1px solid rgba(255,212,0,0.62); color: #FFD400; font-size: 10px; font-weight: 900; }
        .dots { margin-top: 10px; display: flex; gap: 7px; }
        .status-dot { width: 7px; height: 7px; }
        .green { background: var(--status-ready); }
        .amber { background: var(--status-customer); }
        .red { background: var(--status-immediate); animation: dotPulse 1.2s ease-in-out infinite; }
        .gray { background: var(--border-medium); }
        @keyframes dotPulse {
            0%,100% { box-shadow: 0 0 0 rgba(255,59,48,0); }
            50% { box-shadow: 0 0 8px rgba(255,59,48,.8); }
        }

        .drawer {
            position: fixed;
            right: 0;
            top: 0;
            z-index: 80;
            width: 360px;
            height: 100vh;
            overflow-y: auto;
            padding: 16px;
            background: rgba(11,18,32,0.97);
            border-left: 1px solid var(--border-medium);
            transform: translateX(360px);
            transition: transform 0.26s cubic-bezier(0.2,0.8,0.2,1);
        }
        .drawer.open { transform: translateX(0); }
        .drawer-head { position: relative; padding-right: 32px; }
        .drawer-title { display: flex; align-items: center; gap: 10px; font-size: 20px; font-weight: 900; color: #fff; }
        .drawer-sub { margin-top: 4px; color: var(--text-muted); font-size: 12px; }
        .close { position: absolute; top: 0; right: 0; width: 28px; height: 28px; border: 1px solid var(--border-medium); border-radius: 8px; background: transparent; color: var(--text-muted); cursor: pointer; }
        .photo-row { margin-top: 16px; display: grid; grid-template-columns: 140px 1fr; gap: 12px; }
        .photo { width: 140px; height: 88px; border-radius: 10px; background: #020617; border: 1px dashed var(--border-medium); color: var(--text-faint); display: flex; align-items: center; justify-content: center; font-size: 11px; }
        .field { margin-bottom: 7px; }
        .field-label { font-size: 10px; color: var(--text-muted); text-transform: uppercase; }
        .field-value { font-size: 12px; color: var(--text-primary); font-weight: 700; }
        .tabs { margin-top: 16px; display: grid; grid-template-columns: repeat(5, 1fr); gap: 5px; }
        .tab { height: 30px; border: 0; border-radius: 8px; background: transparent; color: var(--text-muted); font-size: 10px; font-weight: 800; cursor: pointer; }
        .tab.active { background: linear-gradient(135deg,#6D28D9,#4F46E5); color: white; box-shadow: 0 0 18px rgba(168,85,247,0.40); }
        .ai-box { margin-top: 14px; border-radius: 14px; padding: 14px; background: linear-gradient(135deg,rgba(88,28,135,0.38),rgba(30,41,59,0.88)); border: 1px solid rgba(168,85,247,0.72); box-shadow: 0 0 28px rgba(168,85,247,0.28); }
        .ai-label { color: var(--status-ai); font-size: 10px; font-weight: 900; letter-spacing: .12em; text-transform: uppercase; }
        .ai-content { margin-top: 8px; display: grid; grid-template-columns: 1fr 76px; gap: 12px; align-items: center; color: var(--text-secondary); font-size: 12px; line-height: 1.45; }
        .score-ring { width: 64px; height: 64px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #fff; font-weight: 900; background: conic-gradient(var(--status-ai) var(--score), rgba(255,255,255,.08) 0); box-shadow: 0 0 18px rgba(168,85,247,.35); }
        .drawer-button { margin-top: 12px; height: 30px; width: 100%; border: 1px solid rgba(34,197,94,.65); border-radius: 8px; background: rgba(34,197,94,.18); color: #bbf7d0; font-weight: 900; cursor: pointer; }
        .drawer-panel { margin-top: 14px; }
        .drawer-card { border: 1px solid var(--border-soft); border-radius: 12px; padding: 12px; background: rgba(15,23,42,.62); color: var(--text-secondary); font-size: 12px; line-height: 1.5; }
        .drawer-card a { color: var(--status-parts); font-weight: 900; }

        .analytics {
            grid-row: 3;
            display: grid;
            grid-template-columns: repeat(5, 1fr);
            gap: 10px;
            padding: 0 10px 10px;
        }
        .analytics-card { border: 1px solid var(--border-soft); border-radius: 14px; background: rgba(11,18,32,.86); padding: 14px; min-width: 0; overflow: hidden; }
        .analytics-card h3 { margin: 0 0 10px; font-size: 12px; color: var(--text-primary); letter-spacing: .06em; text-transform: uppercase; }
        .analytics-card.purple { border-color: rgba(168,85,247,0.55); }
        .analytics-card.pink { border-color: rgba(255,0,110,0.45); background: linear-gradient(180deg, rgba(255,0,110,0.08), rgba(11,18,32,.86)); }
        .analytics-card.cyan { border-color: rgba(0,229,255,0.48); }
        .radar-row, .bottle-row { display: flex; justify-content: space-between; gap: 8px; color: var(--text-secondary); font-size: 11px; margin: 7px 0; }
        .big-number { font-size: 42px; font-weight: 900; color: var(--text-primary); line-height: 1; }
        .italic-note { margin-top: 10px; color: var(--text-faint); font-size: 11px; font-style: italic; line-height: 1.35; }
        .alertbar {
            grid-row: 4;
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 0 14px;
            overflow-x: auto;
            background: rgba(11,18,32,0.95);
            border-top: 1px solid var(--border-soft);
        }
        .alert-pill { height: 40px; border-radius: 10px; padding: 0 14px; display: inline-flex; align-items: center; white-space: nowrap; font-size: 11px; font-weight: 700; border: 1px solid; }
        .alert-pill.red { color: var(--status-immediate); background: var(--status-immediate-bg); border-color: var(--status-immediate-border); }
        .alert-pill.orange { color: var(--status-customer); background: var(--status-customer-bg); border-color: var(--status-customer-border); }
        .alert-pill.yellow { color: #FFD400; background: rgba(255,212,0,.10); border-color: rgba(255,212,0,.55); }
        .alert-pill.cyan { color: var(--status-parts); background: var(--status-parts-bg); border-color: var(--status-parts-border); }
        .alert-pill.purple { color: var(--status-ai); background: var(--status-ai-bg); border-color: var(--status-ai-border); }
        @media (max-width: 1280px) {
            .topbar { grid-template-columns: 210px 1fr 360px; }
            .kpi { width: 78px; }
            .board { grid-template-columns: repeat(3, minmax(220px, 1fr)); overflow-y: auto; }
            body { overflow: auto; grid-template-rows: 78px minmax(700px, auto) auto 56px; }
            .analytics { grid-template-columns: repeat(2, 1fr); }
        }
    </style>
</head>
<body>
    <header class="topbar">
        <div>
            <div class="brand-main">CALLAHAN AUTO & DIESEL</div>
            <div class="brand-sub">Powered by AdviseMe.ai</div>
        </div>
        <div id="kpis" class="kpis"></div>
        <div class="top-actions">
            <div class="clock">
                <div id="clock-time" class="clock-time">--:--</div>
                <div id="clock-date" class="clock-date">--</div>
                <div id="last-update" class="last-update">Last updated --</div>
            </div>
            <div class="action-buttons">
                <a href="/api/morning-briefing" target="_blank">Morning Brief</a>
                <a href="/api/afternoon-briefing" target="_blank">Afternoon Brief</a>
                <a href="/sanity-check" target="_blank">Sanity Check</a>
                <a href="/sanity-check" target="_blank">Tech Sheet</a>
            </div>
        </div>
    </header>
    <div class="legend">
        <span><span class="legend-dot" style="background:var(--status-immediate)"></span>Red=Advisor action now</span>
        <span><span class="legend-dot" style="background:var(--status-customer)"></span>Orange=Customer owns</span>
        <span><span class="legend-dot" style="background:var(--status-progress)"></span>Blue=Tech/Drew</span>
        <span><span class="legend-dot" style="background:var(--status-ready)"></span>Green=Ready/Mitch</span>
        <span><span class="legend-dot" style="background:var(--status-parts)"></span>Cyan=Parts</span>
        <span><span class="legend-dot" style="background:var(--status-ai)"></span>Purple=AI insight</span>
        <span><span class="legend-dot" style="background:#FF006E"></span>Pink=Comeback</span>
        <span><span class="legend-dot" style="background:#FFD400"></span>Yellow=Incoming soon</span>
    </div>
    <main id="board" class="board"></main>
    <aside id="drawer" class="drawer"></aside>
    <section id="analytics" class="analytics"></section>
    <footer id="alertbar" class="alertbar"></footer>

    <script>
        let BOARD_JOBS = __BOARD_JOBS__;
        let GENERATED_AT = __GENERATED_AT__;
        let selectedJob = null;
        let activeDrawerTab = "overview";
        let lastRefreshAt = new Date();

        const columns = [
            { id: "immediate", title: "Need Immediate Action", cls: "immediate", color: "var(--status-immediate)" },
            { id: "customer", title: "Waiting / Customer", cls: "customer", color: "var(--status-customer)" },
            { id: "other", title: "Waiting / Other", cls: "other", color: "#FFD400" },
            { id: "progress", title: "In Progress", cls: "progress", color: "var(--status-progress)" },
            { id: "ready", title: "Ready to Close", cls: "ready", color: "var(--status-ready)" },
            { id: "parts", title: "Parts / Inventory", cls: "parts", color: "var(--status-parts)" }
        ];

        function esc(value) {
            return String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
        }
        function status(job) { return String(job.workflow_status || "").toLowerCase(); }
        function waiting(job) { return String(job.waiting_on || ""); }
        function priority(job) {
            const raw = String(job.priority_lane || job.priority || "P3").toUpperCase();
            return raw.startsWith("P2") ? "P2" : raw;
        }
        function incoming(job) { return Boolean(job.incoming_soon && job.incoming_soon.active === true); }
        function isP1(job) { return priority(job) === "P1" || String(job.risk_level || "").toUpperCase() === "CRITICAL"; }
        function inList(value, list) { return list.includes(String(value || "").toLowerCase()); }
        function columnFor(job) {
            const s = status(job);
            const w = waiting(job);
            if (isP1(job)) return "immediate";
            if (w === "Mitch" && ["waiting approval", "advisor estimate"].includes(s)) return "customer";
            if (["External Hold", "Needs Review", "Preston"].includes(w)) return "other";
            if (["servicing", "awaiting tech", "testing", "qc", "dvi updates", "ready for tech", "technical advisement"].includes(s)) return "progress";
            if (["ready", "advisor finalize ro", "advisor qc review", "technical overview", "qc"].includes(s)) return "ready";
            if (["ordering parts", "waiting parts"].includes(s)) return "parts";
            return "other";
        }
        function jobAction(job) { return job.hermes_next_action || job.next_action || job.workflow_status || "Review job"; }
        function hoursLabel(job) {
            const num = Number(job.hours_in_status);
            if (!Number.isFinite(num)) return job.workflow_status || "--";
            const total = Math.round(num * 60);
            const h = Math.floor(total / 60);
            const m = total % 60;
            if (h >= 24) return Math.floor(h / 24) + "d " + (h % 24) + "h";
            if (h && m) return h + "h " + m + "m";
            if (h) return h + "h";
            return m + "m";
        }
        function progressPercent(job) {
            const p = Number(job.progress_percent);
            if (Number.isFinite(p)) return Math.max(0, Math.min(100, p));
            if (priority(job) === "P1") return 92;
            if (priority(job) === "P2") return 68;
            if (priority(job) === "P3") return 52;
            return 36;
        }
        function dot(cls, label) { return '<span class="status-dot ' + cls + '" title="' + esc(label) + '"></span>'; }
        function statusDots(job) {
            const dvi = String(job.dvi_review_status || "NO_DVI").toUpperCase();
            const s = status(job);
            const ticketGreen = ["waiting approval","ordering parts","waiting parts","awaiting tech","servicing","qc","advisor qc review","advisor finalize ro","ready"];
            const callGreen = ["waiting approval","ordering parts","waiting parts","awaiting tech","servicing","qc","advisor qc review","advisor finalize ro","ready"];
            const qcGreen = ["qc","advisor qc review","advisor finalize ro","ready"];
            return [
                dvi === "PASS" ? dot("green", "DVI pass") : dvi === "REVIEW" ? dot("amber", "DVI review") : dvi === "REWORK_REQUIRED" ? dot("red", "DVI rework") : dot("gray", "No DVI"),
                ticketGreen.includes(s) ? dot("green", "Ticket built") : s === "technical advisement" ? dot("amber", "Technical advisement") : dot("gray", "Ticket pending"),
                callGreen.includes(s) ? dot("green", "Customer called") : dot("gray", "Call not verified"),
                qcGreen.includes(s) ? dot("green", "QC done") : dot("gray", "QC pending"),
                dot("gray", "Appointment not built")
            ].join("");
        }
        function kpis() {
            const waitingCust = BOARD_JOBS.filter(j => waiting(j) === "Mitch" && ["waiting approval", "advisor estimate"].includes(status(j))).length;
            const progress = BOARD_JOBS.filter(j => ["servicing", "awaiting tech"].includes(status(j))).length;
            const ready = BOARD_JOBS.filter(j => ["ready", "advisor finalize ro", "advisor qc review"].includes(status(j))).length;
            const parts = BOARD_JOBS.filter(j => ["ordering parts", "waiting parts"].includes(status(j))).length;
            return [
                ["ACTIVE ROs", BOARD_JOBS.length, "#38BDF8"],
                ["NEED ACTION", BOARD_JOBS.filter(isP1).length, "#FF3B30"],
                ["WAITING CUST", waitingCust, "#FF9500"],
                ["IN PROGRESS", progress, "#3B82F6"],
                ["READY CLOSE", ready, "#22C55E"],
                ["PARTS", parts, "#00E5FF"]
            ];
        }
        function renderKpis() {
            document.getElementById("kpis").innerHTML = kpis().map(([label, count, color]) =>
                '<div class="kpi"><div class="num" style="color:' + color + '">' + count + '</div><div class="label">' + label + '</div></div>'
            ).join("");
        }
        function renderBoard() {
            const board = document.getElementById("board");
            board.innerHTML = columns.map(col => {
                const jobs = BOARD_JOBS.filter(j => columnFor(j) === col.id);
                return '<section class="column">' +
                    '<div class="column-header ' + col.cls + '"><span>' + col.title + '</span><span class="count-badge">' + jobs.length + '</span></div>' +
                    jobs.map(j => renderCard(j, col)).join("") +
                '</section>';
            }).join("");
            board.querySelectorAll(".job-card").forEach(card => {
                card.addEventListener("click", () => {
                    const ro = card.dataset.ro;
                    selectedJob = BOARD_JOBS.find(j => String(j.ro || "") === ro) || null;
                    activeDrawerTab = "overview";
                    renderDrawer();
                });
            });
        }
        function renderCard(job, col) {
            const p = priority(job);
            const pillCls = p.toLowerCase();
            const tech = job.technician || job.assigned_technician || "No tech";
            const bottom = col.id === "parts" ? "RELAY" : col.id === "ready" ? "READY" : "WAITING";
            return '<article class="job-card ' + (isP1(job) ? "p1" : "") + '" data-ro="' + esc(job.ro || "") + '" style="border-color:' + col.color + '">' +
                '<div class="card-top"><div class="ro">RO' + esc(job.ro || "") + '</div><span class="priority ' + pillCls + '">' + p + '</span></div>' +
                '<div class="customer-name">' + esc(job.customer || "Unknown") + '</div>' +
                '<div class="vehicle">' + esc(job.vehicle || "Unknown vehicle") + '</div>' +
                '<div class="action" style="color:' + col.color + '">' + esc(jobAction(job)) + '</div>' +
                '<div class="detail">' + esc(tech) + ' · ' + esc(job.workflow_status || "unknown") + '</div>' +
                '<div class="card-bottom"><span class="small-pill" style="color:' + col.color + '">' + bottom + '</span><span class="time-waiting" style="color:' + col.color + '">' + esc(hoursLabel(job)) + '</span></div>' +
                (incoming(job) ? '<div class="incoming-pill">INCOMING</div>' : '') +
                '<div class="dots">' + statusDots(job) + '</div>' +
            '</article>';
        }
        function renderDrawer() {
            const drawer = document.getElementById("drawer");
            if (!selectedJob) { drawer.classList.remove("open"); drawer.innerHTML = ""; return; }
            const job = selectedJob;
            const col = columns.find(c => c.id === columnFor(job)) || columns[2];
            drawer.classList.add("open");
            const p = priority(job);
            const insight = job.hermes_score_reason || job.hermes_next_action || "No AI recommendation recorded yet.";
            drawer.innerHTML = '<div class="drawer-head">' +
                '<button class="close" id="drawer-close">X</button>' +
                '<div class="drawer-title">RO' + esc(job.ro || "") + '<span class="priority ' + p.toLowerCase() + '">' + p + '</span></div>' +
                '<div class="drawer-sub">' + esc(job.customer || "Unknown") + ' · ' + esc(job.workflow_status || "unknown") + '</div>' +
                '<div style="margin-top:8px"><span class="small-pill" style="color:' + col.color + '">' + col.title + '</span></div>' +
            '</div>' +
            '<div class="photo-row"><div class="photo">No vehicle photo</div><div>' +
                field("Owner", waiting(job) || "Unassigned") +
                field("Next Move", jobAction(job)) +
                field("Waiting On", waiting(job) || "Unknown") +
                field("Time Waiting", hoursLabel(job)) +
            '</div></div>' +
            '<div class="tabs">' + ["overview","dvi","packet","history","files"].map(tab => '<button class="tab ' + (activeDrawerTab === tab ? "active" : "") + '" data-tab="' + tab + '">' + tab.charAt(0).toUpperCase() + tab.slice(1) + '</button>').join("") + '</div>' +
            renderDrawerTab(job, insight);
            document.getElementById("drawer-close").addEventListener("click", () => { selectedJob = null; renderDrawer(); });
            drawer.querySelectorAll(".tab").forEach(btn => btn.addEventListener("click", () => { activeDrawerTab = btn.dataset.tab; renderDrawer(); }));
        }
        function field(label, value) {
            return '<div class="field"><div class="field-label">' + esc(label) + '</div><div class="field-value">' + esc(value) + '</div></div>';
        }
        function renderDrawerTab(job, insight) {
            if (activeDrawerTab === "overview") {
                const pct = progressPercent(job);
                return '<section class="drawer-panel">' +
                    '<div class="ai-box"><div class="ai-label">AI Recommendation</div><div class="ai-content"><div>' + esc(insight) + '</div><div class="score-ring" style="--score:' + pct + '%">' + pct + '%</div></div>' +
                    (waiting(job) === "Mitch" ? '<button class="drawer-button">Call Customer Now</button>' : '') + '</div>' +
                    '<div class="drawer-card" style="margin-top:14px">' +
                    field("Technician", job.technician || job.assigned_technician || "No tech assigned") +
                    field("Progress", pct + "%") +
                    field("Sold Hours", job.sold_hours || "Not connected") +
                    field("Labor Remaining", job.labor_hours_remaining || "Not connected") +
                    '</div></section>';
            }
            if (activeDrawerTab === "dvi") {
                const meta = job.dvi_review_meta || {};
                return '<section class="drawer-panel"><div class="drawer-card">' +
                    field("DVI Status", job.dvi_review_status || "NO_DVI") +
                    field("Flag Count", meta.flag_count || 0) +
                    field("Critical Flags", meta.critical_count || 0) +
                    '<a href="/dvi/packet/' + encodeURIComponent(job.ro || "") + '" target="_blank">Build Packet</a>' +
                '</div></section>';
            }
            if (activeDrawerTab === "packet") {
                return '<section class="drawer-panel"><div class="drawer-card">' +
                    (job.packet_built ? 'Packet ready — <a href="/dvi/packet/' + encodeURIComponent(job.ro || "") + '" target="_blank">view full packet</a>' : '<a href="/dvi/packet/' + encodeURIComponent(job.ro || "") + '" target="_blank">Build Packet</a>') +
                '</div></section>';
            }
            return '<section class="drawer-panel"><div class="drawer-card" style="color:var(--status-ai)">AI agents training — full history intelligence coming soon</div></section>';
        }
        function renderAnalytics() {
            const top = [...BOARD_JOBS].sort((a,b) => (isP1(b) - isP1(a)) || (progressPercent(b) - progressPercent(a))).slice(0,4);
            const sold = BOARD_JOBS.reduce((sum, job) => sum + (Number(job.sold_hours) || 0), 0);
            const waitingCustomer = BOARD_JOBS.filter(j => waiting(j) === "Mitch").length;
            const parts = BOARD_JOBS.filter(j => ["ordering parts", "waiting parts"].includes(status(j))).length;
            const dviRework = BOARD_JOBS.filter(j => String(j.dvi_review_status || "").toUpperCase() === "REWORK_REQUIRED").length;
            const noTech = BOARD_JOBS.filter(j => !(j.technician || j.assigned_technician)).length;
            document.getElementById("analytics").innerHTML =
                '<div class="analytics-card purple"><h3>AI Priority Radar</h3>' + top.map((j,i) => '<div class="radar-row"><span>#' + (i+1) + ' RO' + esc(j.ro) + ' ' + esc(j.customer || '') + '</span><strong>' + progressPercent(j) + '%</strong></div>').join("") + '<div class="italic-note">Full radar intelligence — AdviseMe.ai agents calibrating...</div></div>' +
                '<div class="analytics-card"><h3>Shop Today</h3><div class="big-number">' + BOARD_JOBS.length + '</div><div class="radar-row"><span>Sold Hours</span><strong>' + sold.toFixed(1) + '</strong></div><div class="italic-note">Hours projection — TekMetric integration coming soon</div></div>' +
                '<div class="analytics-card"><h3>Bottlenecks</h3><div class="bottle-row"><span>Waiting on Customer</span><strong>' + waitingCustomer + '</strong></div><div class="bottle-row"><span>Parts delayed</span><strong>' + parts + '</strong></div><div class="bottle-row"><span>DVI rework</span><strong>' + dviRework + '</strong></div><div class="bottle-row"><span>No tech assigned</span><strong>' + noTech + '</strong></div><div class="italic-note">Pattern engine — AI training in progress</div></div>' +
                '<div class="analytics-card pink"><h3>Comeback Watch</h3><div style="color:#FF006E;font-size:12px;line-height:1.5">AdviseMe.ai comeback detection agents warming up. Pattern recognition active after 30 days of shop data.</div></div>' +
                '<div class="analytics-card cyan"><h3>Parts Snapshot</h3><div class="big-number" style="color:var(--status-parts)">' + parts + '</div><div class="italic-note" style="color:var(--status-parts)">Connecting to parts intelligence neural network — AdviseMe.ai inventory agents initializing</div></div>';
        }
        function renderAlerts() {
            const p1 = BOARD_JOBS.filter(isP1).length;
            const approvals = BOARD_JOBS.filter(j => status(j) === "waiting approval").length;
            const rework = BOARD_JOBS.filter(j => String(j.dvi_review_status || "").toUpperCase() === "REWORK_REQUIRED").length;
            const parts = BOARD_JOBS.filter(j => ["ordering parts", "waiting parts"].includes(status(j))).length;
            document.getElementById("alertbar").innerHTML =
                '<span class="alert-pill red">' + p1 + ' P1 jobs need immediate action</span>' +
                '<span class="alert-pill orange">' + approvals + ' estimates waiting customer decision</span>' +
                '<span class="alert-pill yellow">' + rework + ' DVI rework required</span>' +
                '<span class="alert-pill cyan">' + parts + ' jobs waiting on parts</span>' +
                '<span class="alert-pill purple">AdviseMe.ai monitoring ' + BOARD_JOBS.length + ' active ROs</span>';
        }
        function renderAll() {
            renderKpis();
            renderBoard();
            renderAnalytics();
            renderAlerts();
            renderDrawer();
            updateLastUpdated();
        }
        function updateClock() {
            const now = new Date();
            document.getElementById("clock-time").textContent = now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
            document.getElementById("clock-date").textContent = now.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
            updateLastUpdated();
        }
        function updateLastUpdated() {
            const seconds = Math.max(0, Math.floor((new Date() - lastRefreshAt) / 1000));
            document.getElementById("last-update").textContent = "Last updated " + seconds + " seconds ago";
        }
        function refreshData() {
            fetch("/api/board-state", { cache: "no-store" })
                .then(response => response.json())
                .then(payload => {
                    const existing = new Map(BOARD_JOBS.map(j => [String(j.ro || ""), j]));
                    BOARD_JOBS = (Array.isArray(payload.jobs) ? payload.jobs : []).map(job => {
                        const old = existing.get(String(job.ro || "")) || {};
                        return Object.assign({}, job, {
                            packet_built: Boolean(old.packet_built || job.packet_built),
                            dvi_review_meta: old.dvi_review_meta || job.dvi_review_meta || { flag_count: 0, critical_count: 0 }
                        });
                    });
                    GENERATED_AT = payload.generated_at || new Date().toLocaleTimeString();
                    lastRefreshAt = new Date();
                    if (selectedJob) selectedJob = BOARD_JOBS.find(j => String(j.ro || "") === String(selectedJob.ro || "")) || null;
                    renderAll();
                })
                .catch(() => { document.getElementById("last-update").textContent = "Last updated unavailable"; });
        }
        updateClock();
        renderAll();
        setInterval(updateClock, 1000);
        setInterval(refreshData, 60000);
    </script>
</body>
</html>
"""
