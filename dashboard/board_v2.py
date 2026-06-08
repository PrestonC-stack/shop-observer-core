"""
Version 2 command board surface for Callahan Auto & Diesel.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from flask import Response

from board_loader import _load_board_state


REPO_ROOT = Path(__file__).resolve().parents[1]
DVI_REVIEWS_DIR = REPO_ROOT / "state" / "dvi_reviews"
PRIORITY_ORDER = {"P1": 0, "P2": 1, "P2A": 1, "P2B": 1, "P2C": 1, "P3": 2, "P4": 3}


def _priority(job: dict) -> str:
    return str(job.get("priority_lane") or job.get("priority") or "P4").upper()


def _incoming_active(job: dict) -> bool:
    incoming = job.get("incoming_soon")
    return isinstance(incoming, dict) and incoming.get("active") is True


def _sort_key(job: dict):
    return (
        PRIORITY_ORDER.get(_priority(job), 9),
        0 if str(job.get("risk_level") or "").upper() == "CRITICAL" else 1,
        0 if _incoming_active(job) else 1,
        str(job.get("ro") or ""),
    )


def _packet_built(ro) -> bool:
    ro_text = str(ro or "").strip()
    return bool(ro_text and (DVI_REVIEWS_DIR / f"packet_{ro_text}.json").exists())


def render_board_v2():
    board_state = _load_board_state()
    jobs = board_state.get("jobs", []) if isinstance(board_state, dict) else []
    safe_jobs = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        job_copy = dict(job)
        job_copy["packet_built"] = _packet_built(job_copy.get("ro"))
        safe_jobs.append(job_copy)

    safe_jobs.sort(key=_sort_key)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    jobs_json = json.dumps(safe_jobs, ensure_ascii=False).replace("</", "<\\/")
    generated_json = json.dumps(generated_at)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Callahan Command Board v2</title>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            margin: 0;
            background: #f8fafc;
            color: #1e293b;
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }}
        .top-bar {{
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            z-index: 50;
            display: grid;
            grid-template-columns: minmax(180px, 1fr) auto minmax(280px, 1fr);
            align-items: center;
            gap: 16px;
            min-height: 68px;
            padding: 10px 18px;
            background: #ffffff;
            border-bottom: 1px solid #e2e8f0;
        }}
        .brand {{
            color: #64748b;
            font-size: 12px;
            font-weight: 900;
            letter-spacing: 0.14em;
        }}
        .last-updated {{
            margin-top: 3px;
            color: #94a3b8;
            font-size: 11px;
            letter-spacing: 0.02em;
        }}
        .kpis, .actions, .filters, .legend {{
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 8px;
        }}
        .kpis {{ justify-content: center; }}
        .actions {{ justify-content: flex-end; }}
        .pill {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 5px 9px;
            border-radius: 999px;
            border: 1px solid #e2e8f0;
            background: #f1f5f9;
            color: #475569;
            font-size: 12px;
            font-weight: 800;
            white-space: nowrap;
        }}
        .pill.red {{ background: #fef2f2; color: #991b1b; border-color: #fecaca; }}
        .pill.amber {{ background: #fffbeb; color: #92400e; border-color: #fde68a; }}
        .action-btn {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-height: 32px;
            padding: 6px 10px;
            border-radius: 999px;
            border: 1px solid #cbd5e1;
            background: #ffffff;
            color: #334155;
            font-size: 12px;
            font-weight: 800;
            text-decoration: none;
            white-space: nowrap;
        }}
        .workspace {{
            padding-top: 68px;
        }}
        .filter-shell {{
            position: sticky;
            top: 68px;
            z-index: 40;
            background: rgba(248, 250, 252, 0.96);
            border-bottom: 1px solid #e2e8f0;
            backdrop-filter: blur(12px);
        }}
        .filters {{
            padding: 12px 18px 8px;
        }}
        .filter-tab {{
            border: 0;
            border-radius: 999px;
            background: #f1f5f9;
            color: #475569;
            padding: 8px 12px;
            font-size: 13px;
            font-weight: 900;
            cursor: pointer;
            transition: background 0.15s ease, color 0.15s ease, transform 0.15s ease;
        }}
        .filter-tab:hover {{ transform: translateY(-1px); }}
        .filter-tab.active {{ background: #2563eb; color: #ffffff; }}
        .legend {{
            padding: 0 18px 12px;
            color: #64748b;
            font-size: 12px;
        }}
        .dot {{
            display: inline-block;
            width: 10px;
            height: 10px;
            border-radius: 999px;
            background: #cbd5e1;
            vertical-align: middle;
        }}
        .dot.green {{ background: #16a34a; }}
        .dot.amber {{ background: #d97706; }}
        .dot.red {{ background: #dc2626; animation: pulseRed 1.4s ease-in-out infinite; }}
        .dot.gray {{ background: #cbd5e1; }}
        @keyframes pulseRed {{
            0%, 100% {{ box-shadow: 0 0 0 0 rgba(220, 38, 38, 0.0); }}
            50% {{ box-shadow: 0 0 0 5px rgba(220, 38, 38, 0.2); }}
        }}
        .content {{
            display: grid;
            grid-template-columns: minmax(0, 1fr) 0;
            transition: grid-template-columns 0.2s ease;
            min-height: calc(100vh - 126px);
        }}
        .content.drawer-open {{
            grid-template-columns: minmax(0, 1fr) 300px;
        }}
        .card-list {{
            overflow-y: auto;
            padding: 18px;
        }}
        .lane-label {{
            margin: 18px 0 8px;
            color: #334155;
            font-size: 12px;
            font-weight: 1000;
            letter-spacing: 0.12em;
            text-transform: uppercase;
        }}
        .job-card {{
            display: grid;
            grid-template-columns: auto minmax(0, 1fr) minmax(190px, auto);
            align-items: center;
            gap: 12px;
            width: 100%;
            margin-bottom: 8px;
            padding: 11px 12px;
            border: 1px solid #e2e8f0;
            border-left: 6px solid #cbd5e1;
            border-radius: 12px;
            background: #ffffff;
            color: #1e293b;
            text-align: left;
            cursor: pointer;
            transition: background 0.15s ease, border-color 0.15s ease, transform 0.15s ease, box-shadow 0.15s ease;
        }}
        .job-card:hover {{ background: #f1f5f9; transform: translateY(-1px); }}
        .job-card.active {{ border-color: #2563eb; background: #eff6ff; }}
        .job-card.critical {{ box-shadow: inset 8px 0 14px rgba(220, 38, 38, 0.14); }}
        .priority-badge {{
            min-width: 34px;
            border: 1px solid #e2e8f0;
            border-radius: 999px;
            padding: 4px 8px;
            text-align: center;
            font-size: 12px;
            font-weight: 1000;
        }}
        .priority-badge.p1 {{ background: #fef2f2; color: #991b1b; border-color: #fecaca; }}
        .priority-badge.p2 {{ background: #fffbeb; color: #92400e; border-color: #fde68a; }}
        .priority-badge.p3 {{ background: #eff6ff; color: #1e40af; border-color: #bfdbfe; }}
        .priority-badge.p4 {{ background: #f0fdf4; color: #166534; border-color: #bbf7d0; }}
        .job-main {{ min-width: 0; }}
        .job-title {{
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            font-size: 14px;
            font-weight: 900;
        }}
        .job-action {{
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            margin-top: 3px;
            color: #64748b;
            font-size: 12px;
            font-weight: 650;
        }}
        .job-side {{
            text-align: right;
            color: #64748b;
            font-size: 11px;
        }}
        .time-label {{ font-weight: 900; color: #334155; }}
        .dots-row {{
            display: flex;
            justify-content: flex-end;
            gap: 5px;
            margin: 5px 0;
        }}
        .incoming-badge {{
            display: inline-flex;
            margin-left: 8px;
            padding: 2px 7px;
            border-radius: 999px;
            background: #fffbeb;
            color: #92400e;
            border: 1px solid #fde68a;
            font-size: 10px;
            font-weight: 1000;
            text-transform: uppercase;
        }}
        .drawer {{
            width: 300px;
            overflow: hidden;
            background: #ffffff;
            border-left: 1px solid #e2e8f0;
            transform: translateX(100%);
            transition: transform 0.2s ease;
        }}
        .content.drawer-open .drawer {{ transform: translateX(0); }}
        .drawer-inner {{
            height: calc(100vh - 126px);
            overflow-y: auto;
            padding: 16px;
        }}
        .drawer-header {{
            display: flex;
            justify-content: space-between;
            gap: 12px;
            border-bottom: 1px solid #e2e8f0;
            padding-bottom: 12px;
        }}
        .close-btn {{
            border: 1px solid #e2e8f0;
            border-radius: 999px;
            background: #ffffff;
            color: #64748b;
            width: 30px;
            height: 30px;
            cursor: pointer;
            font-weight: 900;
        }}
        .insight {{
            margin: 14px 0;
            padding: 12px;
            border: 1px solid #ddd6fe;
            border-radius: 12px;
            background: #f5f3ff;
            color: #4c1d95;
            font-size: 12px;
            line-height: 1.45;
        }}
        .insight-label {{
            margin-bottom: 5px;
            font-size: 10px;
            font-weight: 1000;
            letter-spacing: 0.12em;
            text-transform: uppercase;
        }}
        .drawer-tabs {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 4px;
            margin: 12px 0;
        }}
        .drawer-tab {{
            border: 0;
            border-radius: 8px;
            background: #f1f5f9;
            color: #475569;
            padding: 7px 4px;
            font-size: 11px;
            font-weight: 900;
            cursor: pointer;
        }}
        .drawer-tab.active {{ background: #2563eb; color: #ffffff; }}
        .timeline-step {{
            display: grid;
            grid-template-columns: 16px 1fr;
            gap: 8px;
            align-items: center;
            margin: 8px 0;
            color: #475569;
            font-size: 12px;
        }}
        .timeline-step.active {{
            color: #1e40af;
            font-weight: 1000;
        }}
        .drawer-actions {{
            display: grid;
            gap: 7px;
            margin: 14px 0;
        }}
        .drawer-actions a {{
            display: block;
            border: 1px solid #e2e8f0;
            border-radius: 10px;
            padding: 9px 10px;
            color: #334155;
            background: #ffffff;
            text-decoration: none;
            font-size: 12px;
            font-weight: 900;
        }}
        .progress-track {{
            height: 8px;
            overflow: hidden;
            border-radius: 999px;
            background: #e2e8f0;
        }}
        .progress-fill {{
            height: 100%;
            background: #2563eb;
        }}
        .drawer-field {{
            margin-top: 10px;
            font-size: 12px;
            color: #475569;
        }}
        .drawer-field strong {{ color: #1e293b; }}
        .empty {{
            padding: 28px;
            border: 1px dashed #cbd5e1;
            border-radius: 14px;
            color: #64748b;
            background: #ffffff;
            text-align: center;
            font-weight: 800;
        }}
        @media (max-width: 920px) {{
            .top-bar {{
                position: static;
                grid-template-columns: 1fr;
                gap: 10px;
            }}
            .kpis, .actions {{ justify-content: flex-start; }}
            .workspace {{ padding-top: 0; }}
            .filter-shell {{ top: 0; }}
            .content, .content.drawer-open {{ grid-template-columns: 1fr; }}
            .drawer {{
                position: fixed;
                top: 0;
                right: 0;
                bottom: 0;
                z-index: 80;
                box-shadow: -20px 0 40px rgba(15, 23, 42, 0.16);
            }}
            .drawer-inner {{ height: 100vh; }}
            .job-card {{
                grid-template-columns: auto minmax(0, 1fr);
            }}
            .job-side {{
                grid-column: 1 / -1;
                text-align: left;
            }}
            .dots-row {{ justify-content: flex-start; }}
        }}
    </style>
</head>
<body>
    <header class="top-bar">
        <div>
            <div class="brand">CALLAHAN AUTO & DIESEL</div>
            <div class="last-updated">Last updated: <span id="last-updated"></span></div>
        </div>
        <div id="kpi-pills" class="kpis"></div>
        <div class="actions">
            <a class="action-btn" href="/api/morning-brief" target="_blank">Morning Brief</a>
            <a class="action-btn" href="/api/afternoon-brief" target="_blank">Afternoon Brief</a>
            <a class="action-btn" href="/sanity-check" target="_blank">Sanity Check</a>
            <a class="action-btn" href="/sanity-check" target="_blank">Tech Sheet</a>
        </div>
    </header>

    <main class="workspace">
        <section class="filter-shell">
            <div id="filters" class="filters"></div>
            <div class="legend">
                <span class="dot green"></span> Green = verified done
                <span class="dot amber"></span> Amber = done, unverified
                <span class="dot red"></span> Red = overdue / needs action
                <span class="dot gray"></span> Gray = not yet relevant
                <strong>Dots:</strong> DVI · Ticket · Call · QC · Appt
            </div>
        </section>

        <section id="content" class="content">
            <div id="card-list" class="card-list"></div>
            <aside id="drawer" class="drawer">
                <div class="drawer-inner">
                    <div id="drawer-body"></div>
                </div>
            </aside>
        </section>
    </main>

    <script>
        let BOARD_JOBS = {jobs_json};
        let GENERATED_AT = {generated_json};
        let activeFilter = "all";
        let selectedRo = null;
        let drawerTab = "summary";

        const priorityMeta = {{
            P1: {{ label: "P1", cls: "p1", color: "#dc2626", lane: "P1 — Action Now" }},
            P2: {{ label: "P2", cls: "p2", color: "#d97706", lane: "P2 — Controlled Action" }},
            P2A: {{ label: "P2", cls: "p2", color: "#d97706", lane: "P2 — Controlled Action" }},
            P2B: {{ label: "P2", cls: "p2", color: "#d97706", lane: "P2 — Controlled Action" }},
            P2C: {{ label: "P2", cls: "p2", color: "#d97706", lane: "P2 — Controlled Action" }},
            P3: {{ label: "P3", cls: "p3", color: "#2563eb", lane: "P3 — Active" }},
            P4: {{ label: "P4", cls: "p4", color: "#16a34a", lane: "P4 — Monitoring" }}
        }};

        function escapeHtml(value) {{
            return String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
        }}

        function priority(job) {{
            return String(job.priority_lane || job.priority || "P4").toUpperCase();
        }}

        function priorityGroup(job) {{
            const lane = priority(job);
            return lane.startsWith("P2") ? "P2" : lane;
        }}

        function incomingActive(job) {{
            return Boolean(job.incoming_soon && job.incoming_soon.active === true);
        }}

        function nextText(job) {{
            return job.hermes_next_action || job.next_action || "No next action recorded";
        }}

        function formatHours(value, fallback) {{
            const num = Number(value);
            if (!Number.isFinite(num)) return fallback || "";
            const totalMinutes = Math.max(0, Math.round(num * 60));
            const hours = Math.floor(totalMinutes / 60);
            const mins = totalMinutes % 60;
            if (hours >= 24) return Math.floor(hours / 24) + "d " + (hours % 24) + "h";
            if (hours > 0 && mins > 0) return hours + "h " + mins + "m";
            if (hours > 0) return hours + "h";
            return mins + "m";
        }}

        function dot(cls, title) {{
            return '<span class="dot ' + cls + '" title="' + escapeHtml(title) + '"></span>';
        }}

        function statusDots(job) {{
            const dvi = String(job.dvi_review_status || "NO_DVI").toUpperCase();
            const status = String(job.workflow_status || "").toLowerCase();
            const ticketGreen = ["advisor estimate", "waiting approval", "ordering parts", "waiting parts", "awaiting tech", "servicing", "qc", "advisor qc review", "advisor finalize ro", "ready"];
            const qcGreen = ["qc", "advisor qc review", "advisor finalize ro", "ready"];
            const estimateGreen = ["waiting approval", "ordering parts", "waiting parts", "awaiting tech", "servicing", "qc", "advisor qc review", "advisor finalize ro", "ready"];
            return [
                dvi === "PASS" ? dot("green", "DVI clear") : dvi === "REVIEW" ? dot("amber", "DVI needs review") : dvi === "REWORK_REQUIRED" ? dot("red", "DVI rework required") : dot("gray", "No DVI on file"),
                ticketGreen.includes(status) ? dot("green", "Ticket built") : status === "technical advisement" ? dot("amber", "Ticket needs technical direction") : dot("gray", "Ticket not verified"),
                ["waiting approval", "ordering parts", "waiting parts"].includes(status) ? dot("green", "Customer contact assumed by status") : dot("gray", "Customer contact not verified"),
                qcGreen.includes(status) ? dot("green", "QC path active") : dot("gray", "QC not yet relevant"),
                dot("gray", "Appointment not built yet")
            ].join("");
        }}

        function kpiCounts(jobs) {{
            return {{
                total: jobs.length,
                p1: jobs.filter((job) => priorityGroup(job) === "P1").length,
                p2: jobs.filter((job) => priorityGroup(job) === "P2").length,
                incoming: jobs.filter(incomingActive).length,
                dviIssues: jobs.filter((job) => ["REWORK_REQUIRED", "REVIEW"].includes(String(job.dvi_review_status || "").toUpperCase())).length,
                noDvi: jobs.filter((job) => String(job.dvi_review_status || "NO_DVI").toUpperCase() === "NO_DVI").length
            }};
        }}

        function filterJobs(jobs) {{
            return jobs.filter((job) => {{
                const group = priorityGroup(job);
                const waiting = String(job.waiting_on || "").toLowerCase();
                if (activeFilter === "all") return true;
                if (["P1", "P2", "P3", "P4"].includes(activeFilter)) return group === activeFilter;
                if (activeFilter === "mitch") return waiting === "mitch";
                if (activeFilter === "drew") return waiting === "drew";
                if (activeFilter === "incoming") return incomingActive(job);
                return true;
            }});
        }}

        function tabCount(filter) {{
            const old = activeFilter;
            activeFilter = filter;
            const count = filterJobs(BOARD_JOBS).length;
            activeFilter = old;
            return count;
        }}

        function renderKpis() {{
            const counts = kpiCounts(BOARD_JOBS);
            document.getElementById("kpi-pills").innerHTML =
                '<span class="pill">● Total active ' + counts.total + '</span>' +
                '<span class="pill red">● P1 ' + counts.p1 + '</span>' +
                '<span class="pill amber">● P2 ' + counts.p2 + '</span>' +
                '<span class="pill amber">● Incoming soon ' + counts.incoming + '</span>' +
                '<span class="pill red">● DVI pending ' + counts.dviIssues + '</span>' +
                '<span class="pill">● No DVI ' + counts.noDvi + '</span>';
        }}

        function renderFilters() {{
            const tabs = [
                ["all", "All"], ["P1", "P1"], ["P2", "P2"], ["P3", "P3"], ["P4", "P4"],
                ["mitch", "Waiting: Mitch"], ["drew", "Waiting: Drew"], ["incoming", "Incoming Soon"]
            ];
            document.getElementById("filters").innerHTML = tabs.map(([key, label]) =>
                '<button class="filter-tab ' + (activeFilter === key ? "active" : "") + '" data-filter="' + key + '">' +
                escapeHtml(label) + ' <span>(' + tabCount(key) + ')</span></button>'
            ).join("");
            document.querySelectorAll(".filter-tab").forEach((button) => {{
                button.addEventListener("click", () => {{
                    activeFilter = button.dataset.filter || "all";
                    selectedRo = null;
                    drawerTab = "summary";
                    renderAll();
                }});
            }});
        }}

        function renderCards() {{
            const filtered = filterJobs(BOARD_JOBS);
            const lanes = [["P1", "P1 — Action Now"], ["P2", "P2 — Controlled Action"], ["P3", "P3 — Active"], ["P4", "P4 — Monitoring"]];
            let html = "";
            lanes.forEach(([lane, label]) => {{
                const laneJobs = filtered.filter((job) => priorityGroup(job) === lane);
                if (!laneJobs.length) return;
                html += '<div class="lane-label">' + label + '</div>';
                html += laneJobs.map(renderCard).join("");
            }});
            document.getElementById("card-list").innerHTML = html || '<div class="empty">No jobs match this filter.</div>';
            document.querySelectorAll(".job-card").forEach((card) => {{
                card.addEventListener("click", () => {{
                    selectedRo = card.dataset.ro;
                    drawerTab = "summary";
                    renderAll();
                }});
            }});
        }}

        function renderCard(job) {{
            const p = priorityGroup(job);
            const meta = priorityMeta[p] || priorityMeta.P4;
            const time = job.hours_in_status !== undefined ? formatHours(job.hours_in_status, job.workflow_status || "") : (job.workflow_status || "");
            const incoming = incomingActive(job) ? '<span class="incoming-badge">⚡ Incoming</span>' : "";
            return '<button class="job-card ' + (selectedRo === String(job.ro || "") ? "active " : "") + (String(job.risk_level || "").toUpperCase() === "CRITICAL" ? "critical" : "") + '" data-ro="' + escapeHtml(job.ro || "") + '" style="border-left-color:' + meta.color + '">' +
                '<span class="priority-badge ' + meta.cls + '">' + meta.label + '</span>' +
                '<span class="job-main">' +
                    '<span class="job-title">RO ' + escapeHtml(job.ro || "") + ' · ' + escapeHtml(job.customer || "Unknown Customer") + ' · ' + escapeHtml(job.vehicle || "Unknown Vehicle") + incoming + '</span>' +
                    '<span class="job-action">' + escapeHtml(nextText(job)) + '</span>' +
                '</span>' +
                '<span class="job-side">' +
                    '<span class="time-label">' + escapeHtml(time) + '</span>' +
                    '<span class="dots-row">' + statusDots(job) + '</span>' +
                    '<span>Waiting: ' + escapeHtml(job.waiting_on || "Unassigned") + '</span>' +
                '</span>' +
            '</button>';
        }}

        function currentStepIndex(job) {{
            const status = String(job.workflow_status || "").toLowerCase();
            if (["advisor finalize ro", "ready"].includes(status)) return 6;
            if (["servicing", "qc", "advisor qc review"].includes(status)) return 5;
            if (["waiting approval"].includes(status)) return 4;
            if (["ordering parts", "waiting parts", "awaiting tech"].includes(status)) return 3;
            if (job.packet_built) return 2;
            if (String(job.dvi_review_status || "NO_DVI").toUpperCase() !== "NO_DVI") return 1;
            return 0;
        }}

        function timelineDot(state) {{
            return dot(state, state);
        }}

        function renderTimeline(job) {{
            const status = String(job.workflow_status || "").toLowerCase();
            const dvi = String(job.dvi_review_status || "NO_DVI").toUpperCase();
            const estimateStatuses = ["waiting approval", "ordering parts", "waiting parts", "awaiting tech", "servicing", "qc", "advisor qc review", "advisor finalize ro", "ready"];
            const productionStatuses = ["servicing", "qc", "advisor qc review", "advisor finalize ro", "ready"];
            const active = currentStepIndex(job);
            const steps = [
                ["Drop Off", "green"],
                ["DVI Complete", dvi === "REWORK_REQUIRED" ? "red" : dvi !== "NO_DVI" ? "green" : "gray"],
                ["Packet Built", job.packet_built ? "green" : "gray"],
                ["Estimate Built", estimateStatuses.includes(status) ? "green" : "gray"],
                ["Customer Called", status === "waiting approval" ? "amber" : "gray"],
                ["In Production", productionStatuses.includes(status) ? "green" : "gray"],
                ["QC & Close", ["advisor finalize ro", "ready"].includes(status) ? "green" : "gray"]
            ];
            return steps.map(([label, state], index) =>
                '<div class="timeline-step ' + (index === active ? "active" : "") + '">' + timelineDot(state) + '<span>' + label + (index === active ? ' <strong>Current</strong>' : '') + '</span></div>'
            ).join("");
        }}

        function renderDrawer() {{
            const content = document.getElementById("content");
            const body = document.getElementById("drawer-body");
            const job = BOARD_JOBS.find((item) => String(item.ro || "") === String(selectedRo || ""));
            if (!job) {{
                content.classList.remove("drawer-open");
                body.innerHTML = "";
                return;
            }}
            content.classList.add("drawer-open");
            const p = priorityGroup(job);
            const meta = priorityMeta[p] || priorityMeta.P4;
            const insight = job.hermes_score_reason || job.hermes_next_action || "";
            const tabBody = drawerTab === "summary" ? renderSummaryTab(job) : '<div class="empty">Coming in Sprint 3C</div>';
            body.innerHTML =
                '<div class="drawer-header">' +
                    '<div><div class="job-title">RO ' + escapeHtml(job.ro || "") + ' · ' + escapeHtml(job.customer || "Unknown Customer") + '</div>' +
                    '<div class="job-action">' + escapeHtml(job.vehicle || "Unknown Vehicle") + ' · ' + escapeHtml(job.workflow_status || "unknown") + '</div>' +
                    '<div style="margin-top:8px;"><span class="priority-badge ' + meta.cls + '">' + meta.label + '</span></div></div>' +
                    '<button class="close-btn" id="close-drawer" type="button">X</button>' +
                '</div>' +
                (insight ? '<div class="insight"><div class="insight-label">Callie insight</div>' + escapeHtml(insight) + '</div>' : '') +
                '<div class="drawer-tabs">' +
                    ["summary", "dvi", "packet", "history"].map((tab) => '<button class="drawer-tab ' + (drawerTab === tab ? "active" : "") + '" data-tab="' + tab + '">' + tab.charAt(0).toUpperCase() + tab.slice(1) + '</button>').join("") +
                '</div>' + tabBody;
            document.getElementById("close-drawer").addEventListener("click", () => {{
                selectedRo = null;
                renderDrawer();
                renderCards();
            }});
            document.querySelectorAll(".drawer-tab").forEach((button) => {{
                button.addEventListener("click", () => {{
                    drawerTab = button.dataset.tab || "summary";
                    renderDrawer();
                }});
            }});
        }}

        function renderSummaryTab(job) {{
            const progress = Number(job.progress_percent || 0);
            const safeProgress = Math.max(0, Math.min(100, Number.isFinite(progress) ? progress : 0));
            return '<div>' +
                '<div class="label">Timeline</div>' +
                renderTimeline(job) +
                '<div class="drawer-actions">' +
                    '<a href="/api/board-action" target="_blank">Log Customer Call</a>' +
                    '<a href="/dvi/packet/' + encodeURIComponent(job.ro || "") + '" target="_blank">View / Build Packet</a>' +
                    '<a href="/dvi" target="_blank">View DVI Report</a>' +
                    '<a href="/api/board-action" target="_blank">Add Note</a>' +
                '</div>' +
                '<div class="drawer-field"><strong>Tech Assignment:</strong> ' + (job.technician ? escapeHtml(job.technician) : '<span class="danger">⚠ No tech assigned</span>') + '</div>' +
                '<div class="drawer-field"><strong>Progress:</strong> ' + safeProgress + '%</div>' +
                '<div class="progress-track"><div class="progress-fill" style="width:' + safeProgress + '%"></div></div>' +
                '<div class="drawer-field"><strong>Sold Hours:</strong> ' + escapeHtml(job.sold_hours || "—") + '</div>' +
                '<div class="drawer-field"><strong>Labor Remaining:</strong> ' + escapeHtml(job.labor_hours_remaining || "—") + '</div>' +
            '</div>';
        }}

        function renderAll() {{
            document.getElementById("last-updated").textContent = GENERATED_AT || new Date().toLocaleTimeString();
            renderKpis();
            renderFilters();
            renderCards();
            renderDrawer();
        }}

        function refreshBoardData() {{
            fetch("/api/board-state", {{ cache: "no-store" }})
                .then((response) => response.json())
                .then((payload) => {{
                    const packetBuiltByRo = new Map(BOARD_JOBS.map((job) => [String(job.ro || ""), Boolean(job.packet_built)]));
                    BOARD_JOBS = (Array.isArray(payload.jobs) ? payload.jobs : []).map((job) => {{
                        const copy = Object.assign({{}}, job);
                        copy.packet_built = packetBuiltByRo.get(String(copy.ro || "")) || Boolean(copy.packet_built);
                        return copy;
                    }});
                    GENERATED_AT = payload.generated_at || new Date().toLocaleTimeString();
                    renderAll();
                }})
                .catch(() => {{
                    document.getElementById("last-updated").textContent = "refresh unavailable";
                }});
        }}

        renderAll();
        window.setInterval(refreshBoardData, 60000);
    </script>
</body>
</html>"""
    return Response(html, mimetype="text/html")
