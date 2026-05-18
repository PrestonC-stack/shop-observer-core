import json
import os
import sys
from datetime import datetime, timedelta

from flask import Flask, Response, jsonify, request

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(CURRENT_DIR)
SHOP_STATE_PATH = os.path.join(REPO_ROOT, "state", "shop_state.json")
BOARD_STATE_PATH = os.path.join(REPO_ROOT, "state", "board_state.json")
BOARD_ACTION_LOG_PATH = os.path.join(REPO_ROOT, "state", "board_actions.jsonl")
HERMES_LOG_PATH = os.path.join(REPO_ROOT, "state", "hermes_feedback.jsonl")

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

app = Flask(__name__)

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Country Club Advisor Command Board</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { font-family: system-ui, -apple-system, sans-serif; }
        .lane-card { min-height: 24rem; }
        .lane-p1 { border: 3px solid #dc2626; background: linear-gradient(180deg, rgba(127, 29, 29, 0.35), rgba(9, 9, 11, 1)); }
        .lane-p2 { border: 3px solid #d97706; background: linear-gradient(180deg, rgba(120, 53, 15, 0.35), rgba(9, 9, 11, 1)); }
        .lane-p3 { border: 3px solid #2563eb; background: linear-gradient(180deg, rgba(30, 64, 175, 0.30), rgba(9, 9, 11, 1)); }
        .lane-p4 { border: 3px solid #16a34a; background: linear-gradient(180deg, rgba(20, 83, 45, 0.30), rgba(9, 9, 11, 1)); }
        .job-card { border: 1px solid rgba(255, 255, 255, 0.08); background: rgba(24, 24, 27, 0.92); }
        .alert-action { border-left: 4px solid #dc2626; }
        .alert-warning { border-left: 4px solid #f59e0b; }
        .alert-info { border-left: 4px solid #3b82f6; }
        .pill { border: 1px solid rgba(255,255,255,0.12); }
        .role-tab.active, .top-tab.active { background: #18181b; color: #fafafa; border-color: #3f3f46; }
        .pulse-card { animation: pulseBorder 1.6s infinite; }
        .blink-icon { animation: pulseBorder 1.2s infinite; }
        .hidden-panel { display: none; }
        .chip-button { transition: transform 0.15s ease, opacity 0.15s ease; }
        .chip-button:hover { transform: translateY(-1px); opacity: 0.95; }
        .modal-shell { max-height: 90vh; overflow-y: auto; }
        @keyframes pulseBorder {
            0% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.45); }
            70% { box-shadow: 0 0 0 10px rgba(245, 158, 11, 0.0); }
            100% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.0); }
        }
    </style>
</head>
<body class="bg-zinc-950 text-zinc-100 min-h-screen">
    <div class="max-w-screen-2xl mx-auto px-4 py-6 md:px-6">
        <div class="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
            <div>
                <h1 class="text-4xl font-black tracking-wide">Shop Command Board</h1>
                <p class="mt-1 text-sm text-zinc-400">Supportive AI copilot for momentum, customer trust, and handoff clarity.</p>
            </div>
            <div class="flex flex-wrap items-center gap-2">
                <div class="rounded-2xl border border-zinc-800 bg-zinc-900 px-4 py-2 text-sm text-zinc-300">
                    Last Updated: <span id="board-updated-at">__TIMESTAMP__</span>
                </div>
                <button id="refresh-jobs" class="rounded-2xl border border-zinc-700 bg-zinc-900 px-4 py-2 text-sm font-semibold text-zinc-100 hover:bg-zinc-800" type="button">Refresh Board</button>
            </div>
        </div>

        <div class="mt-5 flex flex-wrap gap-2">
            <button class="top-tab active rounded-2xl border border-zinc-700 bg-zinc-900 px-4 py-2 text-sm font-semibold" data-panel="board-panel">Board</button>
            <button class="top-tab rounded-2xl border border-zinc-800 bg-zinc-950 px-4 py-2 text-sm font-semibold text-zinc-300" data-panel="analytics-panel">Analytics</button>
            <button id="morning-briefing" class="rounded-2xl border border-zinc-800 bg-zinc-950 px-4 py-2 text-sm font-semibold text-zinc-300">Morning Briefing</button>
        </div>

        <div class="mt-3 flex flex-wrap gap-2">
            <button class="role-tab active rounded-2xl border border-zinc-700 bg-zinc-900 px-4 py-2 text-sm font-semibold" data-role="board">Board</button>
            <button class="role-tab rounded-2xl border border-zinc-800 bg-zinc-950 px-4 py-2 text-sm font-semibold text-zinc-300" data-role="mitch">Mitch</button>
            <button class="role-tab rounded-2xl border border-zinc-800 bg-zinc-950 px-4 py-2 text-sm font-semibold text-zinc-300" data-role="drew">Drew</button>
            <button class="role-tab rounded-2xl border border-zinc-800 bg-zinc-950 px-4 py-2 text-sm font-semibold text-zinc-300" data-role="preston">Preston</button>
        </div>

        <div id="board-panel" class="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-12">
            <section class="lg:col-span-8">
                <div id="lane-grid" class="grid grid-cols-1 gap-4 xl:grid-cols-4"></div>
            </section>

            <section class="space-y-4 lg:col-span-4">
                <div class="rounded-3xl border border-zinc-800 bg-zinc-900 p-5">
                    <div class="flex items-center justify-between">
                        <h2 class="text-xl font-bold">Helper Snapshot</h2>
                        <span class="rounded-full bg-emerald-500/15 px-3 py-1 text-xs font-semibold text-emerald-300">Support Mode</span>
                    </div>
                    <div id="snapshot" class="mt-4 space-y-3 text-sm text-zinc-300"></div>
                </div>

                <div class="rounded-3xl border border-zinc-800 bg-zinc-900 p-5">
                    <h2 class="text-xl font-bold">What Do I Do Next?</h2>
                    <div id="next-actions" class="mt-4 space-y-3"></div>
                </div>

                <div class="rounded-3xl border border-zinc-800 bg-zinc-900 p-5">
                    <div class="flex items-center justify-between gap-3">
                        <h2 class="text-xl font-bold">Hermes Intelligence</h2>
                        <button id="open-hermes-ask" class="rounded-2xl border border-zinc-700 px-3 py-2 text-xs font-semibold text-zinc-200 hover:bg-zinc-800">Ask Hermes</button>
                    </div>
                    <div id="hermes-summary" class="mt-4 rounded-2xl bg-zinc-950 p-4 text-sm leading-relaxed text-zinc-200 min-h-[180px]">Loading Hermes recommendations...</div>
                    <div id="hermes-updated-at" class="mt-3 text-xs text-zinc-500"></div>
                </div>
            </section>
        </div>

        <div id="analytics-panel" class="mt-5 hidden-panel space-y-4">
            <div class="grid grid-cols-1 gap-4 md:grid-cols-4">
                <div class="rounded-3xl border border-zinc-800 bg-zinc-900 p-5">
                    <div class="text-xs uppercase tracking-wide text-zinc-500">P1 Jobs</div>
                    <div id="metric-p1" class="mt-2 text-4xl font-black text-red-400">0</div>
                </div>
                <div class="rounded-3xl border border-zinc-800 bg-zinc-900 p-5">
                    <div class="text-xs uppercase tracking-wide text-zinc-500">Open Alerts</div>
                    <div id="metric-alerts" class="mt-2 text-4xl font-black text-amber-400">0</div>
                </div>
                <div class="rounded-3xl border border-zinc-800 bg-zinc-900 p-5">
                    <div class="text-xs uppercase tracking-wide text-zinc-500">Needs Review</div>
                    <div id="metric-review" class="mt-2 text-4xl font-black text-blue-400">0</div>
                </div>
                <div class="rounded-3xl border border-zinc-800 bg-zinc-900 p-5">
                    <div class="text-xs uppercase tracking-wide text-zinc-500">Clock-In Checks</div>
                    <div id="metric-clocks" class="mt-2 text-4xl font-black text-emerald-400">0</div>
                </div>
            </div>

            <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <div class="rounded-3xl border border-zinc-800 bg-zinc-900 p-5">
                    <h2 class="text-xl font-bold">Status Patterns</h2>
                    <div id="status-patterns" class="mt-4 space-y-3"></div>
                </div>
                <div class="rounded-3xl border border-zinc-800 bg-zinc-900 p-5">
                    <h2 class="text-xl font-bold">Ownership Load</h2>
                    <div id="ownership-patterns" class="mt-4 space-y-3"></div>
                </div>
            </div>
        </div>

        <div id="job-modal" class="hidden-panel fixed inset-0 z-50 bg-black/70 p-4">
            <div class="modal-shell mx-auto mt-2 max-w-4xl rounded-3xl border border-zinc-700 bg-zinc-950 p-6">
                <div class="flex items-start justify-between gap-4">
                    <div>
                        <div id="modal-title" class="text-2xl font-black text-zinc-100"></div>
                        <div id="modal-subtitle" class="mt-1 text-sm text-zinc-400"></div>
                    </div>
                    <button id="close-modal" class="rounded-2xl border border-zinc-700 px-3 py-2 text-sm font-semibold text-zinc-200 hover:bg-zinc-900">Close</button>
                </div>
                <div id="modal-body" class="mt-5 space-y-4"></div>
            </div>
        </div>

        <div id="toast" class="hidden-panel fixed bottom-5 right-5 z-[60] rounded-2xl border border-emerald-700 bg-emerald-950/95 px-4 py-3 text-sm text-emerald-100"></div>
    </div>

    <script>
        let currentRole = "board";
        let latestBoardState = null;
        let currentPanel = "board-panel";
        let activeModalRo = "";
        let activeModalMode = "details";
        let latestActionState = {};

        function escapeHtml(value) {
            return String(value ?? "")
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/\\"/g, "&quot;")
                .replace(/'/g, "&#39;");
        }

        function laneMeta(lane) {
            const map = {
                P1: { cls: "lane-p1", title: "P1", subtitle: "Critical • Action now" },
                P2: { cls: "lane-p2", title: "P2", subtitle: "Needs action • Info gap" },
                P3: { cls: "lane-p3", title: "P3", subtitle: "Monitor • Controlled flow" },
                P4: { cls: "lane-p4", title: "P4", subtitle: "Stable • External hold" }
            };
            return map[lane] || map.P3;
        }

        function riskLight(level) {
            const normalized = String(level || "NORMAL").toUpperCase();
            if (normalized === "CRITICAL" || normalized === "RED") {
                return { label: "Red", cls: "bg-red-500 text-white" };
            }
            if (normalized === "YELLOW") {
                return { label: "Yellow", cls: "bg-amber-400 text-zinc-950" };
            }
            return { label: "Green", cls: "bg-emerald-500 text-zinc-950" };
        }

        function roleMatches(job) {
            if (currentRole === "board") return true;
            const waitingOn = String(job.waiting_on || "").toLowerCase();
            return waitingOn === currentRole;
        }

        function showToast(message, tone = "success") {
            const toast = document.getElementById("toast");
            if (!toast) return;
            toast.textContent = message;
            toast.style.display = "block";
            toast.className = "fixed bottom-5 right-5 z-[60] rounded-2xl border px-4 py-3 text-sm";
            if (tone === "error") {
                toast.className += " border-red-700 bg-red-950/95 text-red-100";
            } else {
                toast.className += " border-emerald-700 bg-emerald-950/95 text-emerald-100";
            }
            window.clearTimeout(window.__toastTimer);
            window.__toastTimer = window.setTimeout(() => { toast.style.display = "none"; }, 2600);
        }

        function actionStateFor(job) {
            return latestActionState[String(job.ro || "")] || {};
        }

        function formatAlert(job) {
            const alerts = Array.isArray(job.alerts) ? job.alerts : [];
            if (!alerts.length) return "";
            const first = alerts[0];
            return '<div class="mt-3 rounded-xl bg-zinc-950 px-3 py-2 text-xs text-zinc-300 alert-' +
                escapeHtml(first.severity || "info") + '">' + escapeHtml(first.message || "Attention needed.") + "</div>";
        }

        function actionIcons(job) {
            const alerts = Array.isArray(job.alerts) ? job.alerts : [];
            const actionState = actionStateFor(job);
            const hasCommunication = alerts.some((alert) => alert.code === "customer_follow_up_due") && !actionState.communication_cleared;
            const hasClock = alerts.some((alert) => alert.code === "verify_tech_clock_in") && !actionState.productivity_cleared;
            const hasData = alerts.some((alert) =>
                alert.code === "missing_ro" ||
                alert.code === "status_mapping_gap" ||
                alert.code === "missing_tech_assignment" ||
                alert.code === "missing_info"
            ) && !actionState.data_cleared;

            const phoneCls = hasCommunication ? " blink-icon border-amber-400 text-amber-300" : " border-zinc-700 text-zinc-500";
            const clockCls = hasClock ? " blink-icon border-red-500 text-red-300" : " border-zinc-700 text-zinc-500";
            const dataCls = hasData ? " blink-icon border-blue-500 text-blue-300" : " border-zinc-700 text-blue-300";

            return (
                '<div class="mt-3 flex flex-wrap gap-2">' +
                    '<button class="chip-button helper-chip rounded-full border px-3 py-1 text-xs font-semibold' + phoneCls + '" data-helper="communication" data-ro="' + escapeHtml(job.ro || "") + '" type="button">☎ Communication</button>' +
                    '<button class="chip-button helper-chip rounded-full border px-3 py-1 text-xs font-semibold' + clockCls + '" data-helper="productivity" data-ro="' + escapeHtml(job.ro || "") + '" type="button">⏱ Productivity</button>' +
                    '<button class="chip-button helper-chip rounded-full border px-3 py-1 text-xs font-semibold' + dataCls + '" data-helper="data" data-ro="' + escapeHtml(job.ro || "") + '" type="button">🧠 Data</button>' +
                '</div>'
            );
        }

        function renderJobCard(job) {
            const alerts = Array.isArray(job.alerts) ? job.alerts : [];
            const alertCodes = alerts.map((alert) => alert.code || "");
            const pulse = (alertCodes.includes("verify_tech_clock_in") || alertCodes.includes("missing_tech_assignment")) ? " pulse-card" : "";
            const incoming = job.incoming_soon && job.incoming_soon.active
                ? '<div class="mt-3 rounded-xl bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200">Incoming soon: ' +
                    escapeHtml(job.incoming_soon.next_stage || job.incoming_soon.reason || "Next handoff approaching.") +
                  "</div>"
                : "";
            const light = riskLight(job.risk_level);

            return (
                '<article class="job-card rounded-2xl p-4 cursor-pointer' + pulse + '" data-ro="' + escapeHtml(job.ro || "") + '">' +
                    '<div class="flex items-start justify-between gap-3">' +
                        "<div>" +
                            '<div class="text-lg font-black">' + escapeHtml(job.ro || "Unknown RO") + "</div>" +
                            '<div class="text-sm font-semibold text-zinc-200">' + escapeHtml(job.customer || "Unknown Customer") + "</div>" +
                            '<div class="text-xs text-zinc-400">' + escapeHtml(job.vehicle || "Unknown Vehicle") + "</div>" +
                        "</div>" +
                        '<div class="space-y-1 text-right">' +
                            '<div class="rounded-full pill px-2 py-1 text-[11px] font-bold ' + light.cls + '">' + escapeHtml(light.label) + "</div>" +
                            '<div class="text-[11px] text-zinc-400">Waiting on ' + escapeHtml(job.waiting_on || "Needs Review") + "</div>" +
                        "</div>" +
                    "</div>" +
                    '<div class="mt-3 text-sm text-zinc-300"><span class="font-semibold text-zinc-100">Status:</span> ' + escapeHtml(job.workflow_status || "unknown") + "</div>" +
                    '<div class="mt-2 text-sm text-zinc-300"><span class="font-semibold text-zinc-100">Next move:</span> ' + escapeHtml(job.next_action || "Keep momentum moving.") + "</div>" +
                    actionIcons(job) +
                    formatAlert(job) +
                    incoming +
                "</article>"
            );
        }

        function renderLaneSection(title, jobs, emptyText) {
            if (!jobs.length) {
                return '<div class="rounded-2xl border border-dashed border-white/10 bg-zinc-950/60 p-4 text-sm text-zinc-400">' + escapeHtml(emptyText) + "</div>";
            }
            return '<div class="space-y-3"><div class="text-sm font-semibold uppercase tracking-wide text-white/90">' +
                escapeHtml(title) + "</div>" + jobs.map(renderJobCard).join("") + "</div>";
        }

        function renderLanes(boardState) {
            const laneGrid = document.getElementById("lane-grid");
            if (!laneGrid) return;
            const jobs = (boardState.jobs || []).filter(roleMatches);
            const lanes = ["P1", "P2", "P3", "P4"];

            laneGrid.innerHTML = lanes.map((lane) => {
                const meta = laneMeta(lane);
                const laneJobs = jobs.filter((job) => job.priority_lane === lane);
                const actionNow = laneJobs.filter((job) => job.risk_level === "CRITICAL" || job.risk_level === "RED");
                const incomingSoon = laneJobs.filter((job) => job.incoming_soon && job.incoming_soon.active && !actionNow.includes(job));
                const remaining = laneJobs.filter((job) => !actionNow.includes(job) && !incomingSoon.includes(job));

                return (
                    '<section class="lane-card rounded-3xl p-4 ' + meta.cls + '">' +
                        '<div class="rounded-2xl bg-black/20 p-4">' +
                            '<div class="flex items-center justify-between gap-3">' +
                                "<div>" +
                                    '<div class="text-4xl font-black">' + escapeHtml(meta.title) + "</div>" +
                                    '<div class="text-sm uppercase tracking-wide text-zinc-200">' + escapeHtml(meta.subtitle) + "</div>" +
                                "</div>" +
                                '<div class="rounded-full bg-white/10 px-4 py-2 text-lg font-black text-white">' + laneJobs.length + "</div>" +
                            "</div>" +
                        "</div>" +
                        '<div class="mt-4 space-y-4">' +
                            renderLaneSection("Action Now", actionNow, "No immediate pressure items.") +
                            renderLaneSection("Incoming Soon", incomingSoon, "No incoming-soon items.") +
                            renderLaneSection("All Jobs", remaining, "This operational lane is currently calm.") +
                        "</div>" +
                    "</section>"
                );
            }).join("");
        }

        function renderSnapshot(boardState) {
            const snapshot = document.getElementById("snapshot");
            if (!snapshot) return;
            const jobs = (boardState.jobs || []).filter(roleMatches);
            const alerts = jobs.flatMap((job) => Array.isArray(job.alerts) ? job.alerts : []);
            const byOwner = {};
            jobs.forEach((job) => {
                const key = job.waiting_on || "Needs Review";
                byOwner[key] = (byOwner[key] || 0) + 1;
            });
            const ownerText = Object.entries(byOwner)
                .sort((a, b) => b[1] - a[1])
                .map(([owner, count]) => owner + ": " + count)
                .join(" • ");

            snapshot.innerHTML =
                '<div class="rounded-2xl bg-zinc-950 p-4 text-zinc-200"><span class="font-semibold">Visible jobs:</span> ' + jobs.length + "</div>" +
                '<div class="rounded-2xl bg-zinc-950 p-4 text-zinc-200"><span class="font-semibold">Open helper alerts:</span> ' + alerts.length + "</div>" +
                '<div class="rounded-2xl bg-zinc-950 p-4 text-zinc-200"><span class="font-semibold">Current ownership load:</span> ' + escapeHtml(ownerText || "No jobs visible.") + "</div>" +
                '<div class="rounded-2xl bg-zinc-950 p-4 text-zinc-300">This board is here to reduce memory burden, tighten handoffs, and keep customers from becoming a surprise.</div>';
        }

        function renderNextActions(boardState) {
            const container = document.getElementById("next-actions");
            if (!container) return;
            const jobs = (boardState.jobs || [])
                .filter(roleMatches)
                .sort((a, b) => {
                    const rank = { CRITICAL: 4, RED: 3, YELLOW: 2, NORMAL: 1 };
                    return (rank[b.risk_level] || 0) - (rank[a.risk_level] || 0);
                })
                .slice(0, 5);

            if (!jobs.length) {
                container.innerHTML = '<div class="rounded-2xl bg-zinc-950 p-4 text-sm text-zinc-400">Nothing urgent right now. Keep working the system and stay ahead of the next handoff.</div>';
                return;
            }

            container.innerHTML = jobs.map((job, index) => (
                '<div class="rounded-2xl bg-zinc-950 p-4">' +
                    '<div class="text-xs uppercase tracking-wide text-zinc-500">Next move ' + (index + 1) + "</div>" +
                    '<div class="mt-1 text-lg font-black text-zinc-100">' + escapeHtml(job.ro || "Unknown RO") + "</div>" +
                    '<div class="text-sm font-semibold text-zinc-300">' + escapeHtml(job.customer || "Unknown Customer") + "</div>" +
                    '<div class="mt-2 text-sm text-zinc-200">' + escapeHtml(job.next_action || "Keep momentum moving.") + "</div>" +
                "</div>"
            )).join("");
        }

        function renderAnalytics(boardState) {
            const jobs = Array.isArray(boardState.jobs) ? boardState.jobs : [];
            const p1 = jobs.filter((job) => job.priority_lane === "P1").length;
            const alerts = jobs.reduce((sum, job) => sum + ((job.alerts || []).length), 0);
            const review = jobs.filter((job) => job.waiting_on === "Needs Review").length;
            const clocks = jobs.filter((job) => (job.alerts || []).some((alert) => alert.code === "verify_tech_clock_in")).length;
            const communicationNeeds = jobs.filter((job) => (job.alerts || []).some((alert) => alert.code === "customer_follow_up_due")).length;
            const dataNeeds = jobs.filter((job) => (job.alerts || []).some((alert) =>
                alert.code === "missing_ro" ||
                alert.code === "status_mapping_gap" ||
                alert.code === "missing_tech_assignment" ||
                alert.code === "missing_info"
            )).length;
            const clearCommunication = Math.max(0, jobs.length - communicationNeeds);
            const clearProductivity = Math.max(0, jobs.length - clocks);
            const clearData = Math.max(0, jobs.length - dataNeeds);
            const scoreBase = Math.max(jobs.length, 1);
            const shopScore = Math.round(((clearCommunication + clearProductivity + clearData) / (scoreBase * 3)) * 100);

            document.getElementById("metric-p1").textContent = String(p1);
            document.getElementById("metric-alerts").textContent = String(alerts);
            document.getElementById("metric-review").textContent = String(review);
            document.getElementById("metric-clocks").textContent = String(clocks);

            const statusCounts = {};
            const ownerCounts = {};
            jobs.forEach((job) => {
                const status = job.workflow_status || "unknown";
                const owner = job.waiting_on || "Needs Review";
                statusCounts[status] = (statusCounts[status] || 0) + 1;
                ownerCounts[owner] = (ownerCounts[owner] || 0) + 1;
            });

            const statusHtml = Object.entries(statusCounts)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 8)
                .map(([status, count]) => '<div class="rounded-2xl bg-zinc-950 px-4 py-3 text-sm text-zinc-200"><span class="font-semibold">' + escapeHtml(status) + ":</span> " + count + "</div>")
                .join("");
            const ownerHtml = Object.entries(ownerCounts)
                .sort((a, b) => b[1] - a[1])
                .map(([owner, count]) => '<div class="rounded-2xl bg-zinc-950 px-4 py-3 text-sm text-zinc-200"><span class="font-semibold">' + escapeHtml(owner) + ":</span> " + count + "</div>")
                .join("");

            document.getElementById("status-patterns").innerHTML =
                '<div class="rounded-2xl bg-zinc-950 px-4 py-3 text-sm text-zinc-200"><span class="font-semibold">Shop support score:</span> ' + shopScore + '%</div>' +
                '<div class="rounded-2xl bg-zinc-950 px-4 py-3 text-sm text-zinc-200"><span class="font-semibold">Communication clear:</span> ' + clearCommunication + ' / ' + jobs.length + '</div>' +
                '<div class="rounded-2xl bg-zinc-950 px-4 py-3 text-sm text-zinc-200"><span class="font-semibold">Productivity clear:</span> ' + clearProductivity + ' / ' + jobs.length + '</div>' +
                '<div class="rounded-2xl bg-zinc-950 px-4 py-3 text-sm text-zinc-200"><span class="font-semibold">Data clear:</span> ' + clearData + ' / ' + jobs.length + '</div>' +
                (statusHtml || '<div class="rounded-2xl bg-zinc-950 px-4 py-3 text-sm text-zinc-400">No status patterns available yet.</div>');
            document.getElementById("ownership-patterns").innerHTML =
                (ownerHtml || '<div class="rounded-2xl bg-zinc-950 px-4 py-3 text-sm text-zinc-400">No ownership patterns available yet.</div>') +
                '<div class="rounded-2xl bg-zinc-950 px-4 py-3 text-sm text-zinc-200"><span class="font-semibold">Advisor support load:</span> Mitch actions ' + communicationNeeds + ', Drew checks ' + clocks + ', Data cleanups ' + dataNeeds + '</div>';
        }

        function renderBoardState(boardState) {
            latestBoardState = boardState;
            latestActionState = boardState.action_state || {};
            document.getElementById("board-updated-at").textContent = boardState.generated_at || "__TIMESTAMP__";
            renderLanes(boardState);
            renderSnapshot(boardState);
            renderNextActions(boardState);
            renderAnalytics(boardState);
            wireJobCards();
            wireHelperChips();
        }

        function renderHermesSummary(payload) {
            const target = document.getElementById("hermes-summary");
            if (!target) return;
            const lines = String(payload.summary || "No summary available.")
                .split(/\\n+/)
                .map((line) => line.trim())
                .filter(Boolean);

            target.innerHTML = lines.map((line) => (
                '<div class="mb-3 rounded-2xl bg-zinc-900 px-4 py-3 text-sm text-zinc-100">' + escapeHtml(line) + "</div>"
            )).join("") || '<div class="rounded-2xl bg-zinc-900 px-4 py-3 text-sm text-zinc-400">No summary available.</div>';

            document.getElementById("hermes-updated-at").textContent = "Last Hermes update: " + (payload.timestamp || "--");
        }

        function loadBoardState() {
            fetch("/api/board-state", { cache: "no-store" })
                .then((response) => {
                    if (!response.ok) throw new Error("Request failed");
                    return response.json();
                })
                .then(renderBoardState)
                .catch(() => renderBoardState({
                    generated_at: "__TIMESTAMP__",
                    jobs: [],
                    message: "Board state unavailable."
                }));
        }

        function loadHermesSummary() {
            fetch("/api/hermes-summary", { cache: "no-store" })
                .then((response) => {
                    if (!response.ok) throw new Error("Request failed");
                    return response.json();
                })
                .then(renderHermesSummary)
                .catch(() => renderHermesSummary({ summary: "Hermes summary unavailable.", timestamp: "--" }));
        }

        function refreshBoard() {
            loadBoardState();
            loadHermesSummary();
        }

        function wireJobCards() {
            document.querySelectorAll("[data-ro].job-card").forEach((card) => {
                card.addEventListener("click", () => openJobModal(card.dataset.ro || "", "details"));
            });
        }

        function wireHelperChips() {
            document.querySelectorAll(".helper-chip").forEach((button) => {
                button.addEventListener("click", (event) => {
                    event.stopPropagation();
                    openJobModal(button.dataset.ro || "", button.dataset.helper || "details");
                });
            });
        }

        function findJobByRo(ro) {
            if (!latestBoardState) return null;
            return (latestBoardState.jobs || []).find((item) => String(item.ro || "") === String(ro)) || null;
        }

        function buildActionPanel(job, focusMode) {
            const placeholders = {
                communication: "Log what was communicated to the customer, callback time, or new promise window.",
                productivity: "Log what you found on the floor. Who is on it, is labor clocked, and what is blocking progress?",
                data: "Log the board mismatch, missing RO, status cleanup, or data issue you want Hermes to learn from.",
                hermes: "Ask Hermes a targeted question about this job, the blocker, or the next best move.",
                details: "Log a quick support note so the board can help the next handoff."
            };
            const labels = {
                communication: "Customer Update",
                productivity: "Productivity Check",
                data: "Board / Data Fix",
                hermes: "Ask Hermes",
                details: "Quick Note"
            };

            return (
                '<div class="rounded-2xl bg-zinc-900 p-4">' +
                    '<div class="text-xs uppercase tracking-wide text-zinc-500">Action Center</div>' +
                    '<div class="mt-3 flex flex-wrap gap-2">' +
                        '<button class="modal-mode rounded-2xl border border-zinc-700 px-3 py-2 text-xs font-semibold text-zinc-200 hover:bg-zinc-800" data-mode="communication" type="button">☎ Customer Update</button>' +
                        '<button class="modal-mode rounded-2xl border border-zinc-700 px-3 py-2 text-xs font-semibold text-zinc-200 hover:bg-zinc-800" data-mode="productivity" type="button">⏱ Productivity Check</button>' +
                        '<button class="modal-mode rounded-2xl border border-zinc-700 px-3 py-2 text-xs font-semibold text-zinc-200 hover:bg-zinc-800" data-mode="data" type="button">🧠 Board / Data Fix</button>' +
                        '<button class="modal-mode rounded-2xl border border-zinc-700 px-3 py-2 text-xs font-semibold text-zinc-200 hover:bg-zinc-800" data-mode="hermes" type="button">Ask Hermes</button>' +
                    "</div>" +
                    '<div class="mt-4 text-sm font-semibold text-zinc-200" id="modal-mode-label">' + escapeHtml(labels[focusMode] || labels.details) + "</div>" +
                    '<textarea id="modal-note" class="mt-2 min-h-[120px] w-full rounded-2xl border border-zinc-700 bg-zinc-950 px-4 py-3 text-sm text-zinc-100 outline-none focus:border-emerald-500" placeholder="' + escapeHtml(placeholders[focusMode] || placeholders.details) + '"></textarea>' +
                    '<div class="mt-3 flex flex-wrap gap-2">' +
                        '<button id="submit-board-action" class="rounded-2xl border border-emerald-700 bg-emerald-900/40 px-4 py-2 text-sm font-semibold text-emerald-100 hover:bg-emerald-900/70" type="button">Save Update</button>' +
                        '<button id="submit-hermes-question" class="rounded-2xl border border-blue-700 bg-blue-900/40 px-4 py-2 text-sm font-semibold text-blue-100 hover:bg-blue-900/70" type="button">Send to Hermes</button>' +
                    "</div>" +
                    '<div id="modal-response" class="mt-4 rounded-2xl bg-zinc-950 p-4 text-sm text-zinc-300">Use this panel to log what happened, capture what was found, or ask Hermes what to do next.</div>' +
                "</div>"
            );
        }

        function openJobModal(ro, mode = "details") {
            const job = findJobByRo(ro);
            if (!job) return;
            activeModalRo = ro;
            activeModalMode = mode;

            document.getElementById("modal-title").textContent = job.ro + " • " + (job.customer || "Unknown Customer");
            document.getElementById("modal-subtitle").textContent = (job.vehicle || "Unknown Vehicle") + " • Waiting on " + (job.waiting_on || "Needs Review");

            const alerts = (job.alerts || []).map((alert) =>
                "<li class=\\"mb-2\\">" + escapeHtml(alert.message || "Attention needed.") + "</li>"
            ).join("");

            document.getElementById("modal-body").innerHTML =
                '<div class="grid grid-cols-1 gap-4 md:grid-cols-2">' +
                    '<div class="rounded-2xl bg-zinc-900 p-4"><div class="text-xs uppercase tracking-wide text-zinc-500">Status</div><div class="mt-2 text-lg font-bold text-zinc-100">' + escapeHtml(job.workflow_status || "unknown") + "</div></div>" +
                    '<div class="rounded-2xl bg-zinc-900 p-4"><div class="text-xs uppercase tracking-wide text-zinc-500">Risk</div><div class="mt-2 text-lg font-bold text-zinc-100">' + escapeHtml(job.risk_level || "NORMAL") + "</div></div>" +
                    '<div class="rounded-2xl bg-zinc-900 p-4"><div class="text-xs uppercase tracking-wide text-zinc-500">Advisor</div><div class="mt-2 text-lg font-bold text-zinc-100">' + escapeHtml(job.advisor || "Unknown") + "</div></div>" +
                    '<div class="rounded-2xl bg-zinc-900 p-4"><div class="text-xs uppercase tracking-wide text-zinc-500">Technician</div><div class="mt-2 text-lg font-bold ' + ((String(job.technician || "").toLowerCase() === "unassigned" || !String(job.technician || "").trim()) ? "text-amber-300" : "text-zinc-100") + '">' + escapeHtml(job.technician || "Unassigned") + "</div></div>" +
                "</div>" +
                '<div class="mt-4 rounded-2xl bg-zinc-900 p-4"><div class="text-xs uppercase tracking-wide text-zinc-500">Next Move</div><div class="mt-2 text-zinc-100">' + escapeHtml(job.next_action || "Keep momentum moving.") + "</div></div>" +
                '<div class="mt-4 rounded-2xl bg-zinc-900 p-4"><div class="text-xs uppercase tracking-wide text-zinc-500">Summary</div><div class="mt-2 text-zinc-100">' + escapeHtml(job.summary || "No summary available.") + "</div></div>" +
                '<div class="mt-4 rounded-2xl bg-zinc-900 p-4"><div class="text-xs uppercase tracking-wide text-zinc-500">Helper Alerts</div><ul class="mt-2 text-zinc-100">' + (alerts || "<li>No active alerts.</li>") + "</ul></div>" +
                buildActionPanel(job, mode);

            document.getElementById("job-modal").style.display = "block";
            wireModalActions();
            const note = document.getElementById("modal-note");
            if (note) {
                note.focus();
                note.scrollIntoView({ block: "center", behavior: "smooth" });
            }
        }

        function wireModalActions() {
            document.querySelectorAll(".modal-mode").forEach((button) => {
                button.addEventListener("click", () => setModalMode(button.dataset.mode || "details"));
            });
            const actionButton = document.getElementById("submit-board-action");
            const hermesButton = document.getElementById("submit-hermes-question");
            if (actionButton) actionButton.addEventListener("click", submitBoardAction);
            if (hermesButton) hermesButton.addEventListener("click", submitHermesQuestion);
        }

        function setModalMode(mode) {
            activeModalMode = mode;
            const labelMap = {
                communication: "Customer Update",
                productivity: "Productivity Check",
                data: "Board / Data Fix",
                hermes: "Ask Hermes",
                details: "Quick Note"
            };
            const placeholderMap = {
                communication: "Log what was communicated to the customer, callback time, or new promise window.",
                productivity: "Log what you found on the floor. Who is on it, is labor clocked, and what is blocking progress?",
                data: "Log the board mismatch, missing RO, status cleanup, or data issue you want Hermes to learn from.",
                hermes: "Ask Hermes a targeted question about this job, the blocker, or the next best move.",
                details: "Log a quick support note so the board can help the next handoff."
            };
            const label = document.getElementById("modal-mode-label");
            const note = document.getElementById("modal-note");
            if (label) label.textContent = labelMap[mode] || labelMap.details;
            if (note) note.placeholder = placeholderMap[mode] || placeholderMap.details;
        }

        function closeJobModal() {
            document.getElementById("job-modal").style.display = "none";
        }

        function setTopPanel(panelId) {
            currentPanel = panelId;
            document.querySelectorAll(".top-tab").forEach((button) => {
                button.classList.toggle("active", button.dataset.panel === panelId);
            });
            document.getElementById("board-panel").style.display = panelId === "board-panel" ? "grid" : "none";
            document.getElementById("analytics-panel").style.display = panelId === "analytics-panel" ? "block" : "none";
        }

        function setRole(role) {
            currentRole = role;
            document.querySelectorAll(".role-tab").forEach((button) => {
                button.classList.toggle("active", button.dataset.role === role);
            });
            if (latestBoardState) {
                renderBoardState(latestBoardState);
            }
        }

        function loadMorningBriefing() {
            fetch("/api/morning-briefing", { cache: "no-store" })
                .then((response) => {
                    if (!response.ok) throw new Error("Request failed");
                    return response.json();
                })
                .then((payload) => {
                    document.getElementById("modal-title").textContent = "Morning Briefing";
                    document.getElementById("modal-subtitle").textContent = "Quick team focal point for P1/P2 work and lunch reset planning.";
                    const lines = String(payload.briefing || "No briefing available.").split(/\\n+/).filter(Boolean);
                    document.getElementById("modal-body").innerHTML =
                        '<div class="rounded-2xl bg-zinc-900 p-5 text-sm leading-relaxed text-zinc-100"><ol class="space-y-3 list-decimal pl-5">' +
                        lines.map((line) => '<li>' + escapeHtml(line) + '</li>').join("") +
                        '</ol></div>' +
                        '<div class="flex flex-wrap gap-2">' +
                        '<button id="print-briefing" class="rounded-2xl border border-zinc-700 px-4 py-2 text-sm font-semibold text-zinc-200 hover:bg-zinc-900" type="button">Print Briefing</button>' +
                        '<button id="afternoon-briefing" class="rounded-2xl border border-zinc-700 px-4 py-2 text-sm font-semibold text-zinc-200 hover:bg-zinc-900" type="button">Afternoon Brief</button>' +
                        '</div>' +
                        '<div class="rounded-2xl bg-zinc-900 p-5 text-xs text-zinc-400">Generated: ' + escapeHtml(payload.timestamp || "--") + "</div>";
                    document.getElementById("job-modal").style.display = "block";
                    document.getElementById("print-briefing").addEventListener("click", () => window.print());
                    document.getElementById("afternoon-briefing").addEventListener("click", loadAfternoonBriefing);
                    renderHermesSummary({ summary: payload.briefing || "No briefing available.", timestamp: payload.timestamp || "--" });
                })
                .catch(() => showToast("Morning briefing unavailable right now.", "error"));
        }

        function loadAfternoonBriefing() {
            fetch("/api/afternoon-briefing", { cache: "no-store" })
                .then((response) => {
                    if (!response.ok) throw new Error("Request failed");
                    return response.json();
                })
                .then((payload) => {
                    const lines = String(payload.briefing || "No briefing available.").split(/\\n+/).filter(Boolean);
                    document.getElementById("modal-title").textContent = "Afternoon Brief";
                    document.getElementById("modal-subtitle").textContent = "Post-lunch rollover check for remaining P1/P2 pressure and closeout opportunities.";
                    document.getElementById("modal-body").innerHTML =
                        '<div class="rounded-2xl bg-zinc-900 p-5 text-sm leading-relaxed text-zinc-100"><ol class="space-y-3 list-decimal pl-5">' +
                        lines.map((line) => '<li>' + escapeHtml(line) + '</li>').join("") +
                        '</ol></div>' +
                        '<div class="rounded-2xl bg-zinc-900 p-5 text-xs text-zinc-400">Generated: ' + escapeHtml(payload.timestamp || "--") + '</div>';
                    document.getElementById("job-modal").style.display = "block";
                    renderHermesSummary({ summary: payload.briefing || "No briefing available.", timestamp: payload.timestamp || "--" });
                })
                .catch(() => showToast("Afternoon brief unavailable right now.", "error"));
        }

        function openHermesAskModal() {
            document.getElementById("modal-title").textContent = "Ask Hermes";
            document.getElementById("modal-subtitle").textContent = "Ask a board question, flag a pattern, or request help with the next move.";
            document.getElementById("modal-body").innerHTML = buildActionPanel({
                ro: "",
                customer: "General board question"
            }, "hermes");
            document.getElementById("job-modal").style.display = "block";
            wireModalActions();
        }

        function submitBoardAction() {
            const note = document.getElementById("modal-note");
            if (!note || !note.value.trim()) {
                showToast("Add a quick note first so the board knows what changed.", "error");
                return;
            }
            fetch("/api/board-action", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    ro: activeModalRo,
                    action_type: activeModalMode,
                    note: note.value.trim(),
                    source: "dashboard"
                })
            })
                .then((response) => response.json())
                .then((payload) => {
                    const panel = document.getElementById("modal-response");
                    if (panel) panel.textContent = payload.message || "Update saved.";
                    showToast(payload.message || "Update saved.");
                    note.value = "";
                    refreshBoard();
                })
                .catch(() => showToast("Unable to save that update right now.", "error"));
        }

        function submitHermesQuestion() {
            const note = document.getElementById("modal-note");
            if (!note || !note.value.trim()) {
                showToast("Type a question for Hermes first.", "error");
                return;
            }
            fetch("/api/hermes-feedback", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    ro: activeModalRo,
                    mode: activeModalMode,
                    question: note.value.trim(),
                    source: "dashboard"
                })
            })
                .then((response) => response.json())
                .then((payload) => {
                    const panel = document.getElementById("modal-response");
                    const answer = payload.answer || payload.message || "Hermes acknowledged the note.";
                    if (panel) panel.textContent = answer;
                    renderHermesSummary({ summary: answer, timestamp: payload.timestamp || "--" });
                    showToast("Hermes updated.");
                })
                .catch(() => showToast("Hermes could not respond right now.", "error"));
        }

        document.addEventListener("DOMContentLoaded", () => {
            document.getElementById("refresh-jobs").addEventListener("click", refreshBoard);
            document.getElementById("close-modal").addEventListener("click", closeJobModal);
            document.getElementById("morning-briefing").addEventListener("click", loadMorningBriefing);
            document.getElementById("open-hermes-ask").addEventListener("click", openHermesAskModal);
            document.querySelectorAll(".role-tab").forEach((button) => {
                button.addEventListener("click", () => setRole(button.dataset.role || "board"));
            });
            document.querySelectorAll(".top-tab").forEach((button) => {
                button.addEventListener("click", () => setTopPanel(button.dataset.panel || "board-panel"));
            });
            refreshBoard();
            window.setInterval(refreshBoard, 30000);
        });
    </script>
</body>
</html>"""


def _append_jsonl(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def _read_jsonl(path):
    if not os.path.exists(path):
        return []
    rows = []
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except Exception:
                    continue
                if isinstance(payload, dict):
                    rows.append(payload)
    except Exception:
        return []
    return rows


def _latest_action_state():
    state = {}
    horizon = datetime.now() - timedelta(hours=12)
    for row in _read_jsonl(BOARD_ACTION_LOG_PATH):
        ro = str(row.get("ro", "")).strip()
        action_type = str(row.get("action_type", "")).strip()
        if not ro or not action_type:
            continue
        try:
            stamp = datetime.strptime(str(row.get("timestamp", "")), "%Y-%m-%d %H:%M:%S")
        except Exception:
            stamp = datetime.now()
        if stamp < horizon:
            continue
        entry = state.setdefault(ro, {})
        entry[f"{action_type}_cleared"] = True
        entry[f"{action_type}_updated_at"] = stamp.strftime("%Y-%m-%d %H:%M:%S")
    return state


def _apply_action_state(board_state):
    if not isinstance(board_state, dict):
        return board_state
    action_state = _latest_action_state()
    jobs = board_state.get("jobs", [])
    if not isinstance(jobs, list):
        board_state["action_state"] = action_state
        return board_state

    for job in jobs:
        if not isinstance(job, dict):
            continue
        ro = str(job.get("ro", "")).strip()
        ro_state = action_state.get(ro, {})
        alerts = job.get("alerts", [])
        if not isinstance(alerts, list):
            alerts = []
        filtered_alerts = []
        for alert in alerts:
            code = alert.get("code") if isinstance(alert, dict) else ""
            if code == "customer_follow_up_due" and ro_state.get("communication_cleared"):
                continue
            if code == "verify_tech_clock_in" and ro_state.get("productivity_cleared"):
                continue
            if code in {"missing_ro", "status_mapping_gap", "missing_tech_assignment", "missing_info"} and ro_state.get("data_cleared"):
                continue
            filtered_alerts.append(alert)
        job["alerts"] = filtered_alerts
        if ro_state:
            job["action_state"] = ro_state

    board_state["open_alert_count"] = sum(len(job.get("alerts", [])) for job in jobs if isinstance(job, dict))
    board_state["action_state"] = action_state
    return board_state


def _fallback_jobs_payload(reason="autoflow_unavailable"):
    return {
        "source": "fallback",
        "status": "ok",
        "jobs": [],
        "count": 0,
        "message": reason,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _load_jobs_from_autoflow():
    try:
        with open(SHOP_STATE_PATH, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload
    except Exception:
        return _fallback_jobs_payload("shop_state_not_found")


def _load_board_state():
    try:
        with open(BOARD_STATE_PATH, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            return _apply_action_state(payload)
    except Exception:
        pass

    return _apply_action_state({
        "source": "board_rules_v1",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": 0,
        "jobs": [],
        "lane_counts": {"P1": 0, "P2": 0, "P3": 0, "P4": 0},
        "waiting_on_counts": {"Mitch": 0, "Drew": 0, "Preston": 0, "External Hold": 0, "Needs Review": 0},
        "open_alert_count": 0,
        "message": "No board_state.json found. Run python scripts/build_board_state.py first.",
    })


def _find_job(ro):
    board_state = _load_board_state()
    jobs = board_state.get("jobs", []) if isinstance(board_state, dict) else []
    for job in jobs:
        if isinstance(job, dict) and str(job.get("ro", "")) == str(ro):
            return job
    return None


def _hermes_answer(question, job=None, mode="general"):
    question = str(question or "").strip()
    if not question and not job:
        return "Hermes needs a little more context. Ask what is blocked, what the next move is, or what customer expectation should be protected."

    if job:
        ro = job.get("ro", "Unknown RO")
        waiting_on = job.get("waiting_on", "Needs Review")
        next_action = job.get("next_action", "Keep momentum moving.")
        alerts = [alert.get("message", "") for alert in job.get("alerts", []) if isinstance(alert, dict)]
        lead = f"RO {ro} is currently waiting on {waiting_on}. {next_action}"
        if mode == "communication":
            return lead + " For customer contact, confirm the latest expectation, document the callback window, and keep trust ahead of the surprise."
        if mode == "productivity":
            return lead + " On the floor, verify who is actively on it, whether labor is clocked, and what single blocker is keeping it from moving."
        if mode == "data":
            return lead + " Tighten the board evidence by fixing the RO linkage, status mapping, or ownership gap so the coaching becomes more precise."
        if alerts:
            return lead + " Current helper alerts: " + " ".join(alerts[:2])
        return lead

    return "Hermes logged the board question. The next best move is to capture the blocker, the owner, and the promised follow-up so the system can coach the handoff instead of guessing."


@app.route("/")
def board():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html = HTML_TEMPLATE.replace("__TIMESTAMP__", timestamp)
    return Response(html, mimetype="text/html")


@app.route("/healthz")
def healthz():
    return {"status": "ok"}, 200


@app.route("/api/jobs")
def api_jobs():
    try:
        return jsonify(_load_jobs_from_autoflow()), 200
    except Exception as exc:
        return jsonify(_fallback_jobs_payload(f"unexpected_error: {exc}")), 200


@app.route("/api/board-state")
def api_board_state():
    try:
        return jsonify(_load_board_state()), 200
    except Exception as exc:
        return jsonify(
            {
                "source": "board_rules_v1",
                "status": "error",
                "message": f"unexpected_error: {exc}",
                "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "jobs": [],
            }
        ), 200


@app.route("/api/board-action", methods=["POST"])
def api_board_action():
    payload = request.get_json(silent=True) or {}
    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ro": str(payload.get("ro", "")).strip(),
        "action_type": str(payload.get("action_type", "details")).strip() or "details",
        "note": str(payload.get("note", "")).strip(),
        "source": str(payload.get("source", "dashboard")).strip() or "dashboard",
    }
    _append_jsonl(BOARD_ACTION_LOG_PATH, entry)

    message_map = {
        "communication": "Customer update saved. Keep the promise window visible and the next callback clear.",
        "productivity": "Productivity note saved. Advisors can now coach the next floor follow-up with context.",
        "data": "Board issue saved. This gives Hermes a cleaner trail to improve the board logic.",
        "details": "Support note saved.",
    }
    return jsonify({"status": "received", "message": message_map.get(entry["action_type"], "Support note saved.")}), 200


@app.route("/api/hermes-feedback", methods=["POST"])
def api_hermes_feedback():
    payload = request.get_json(silent=True) or {}
    ro = str(payload.get("ro", "")).strip()
    mode = str(payload.get("mode", "general")).strip() or "general"
    question = str(payload.get("question", "")).strip()
    job = _find_job(ro) if ro else None
    answer = _hermes_answer(question, job=job, mode=mode)
    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ro": ro,
        "mode": mode,
        "question": question,
        "answer": answer,
        "source": str(payload.get("source", "dashboard")).strip() or "dashboard",
    }
    _append_jsonl(HERMES_LOG_PATH, entry)
    return jsonify({"status": "received", "answer": answer, "timestamp": entry["timestamp"]}), 200


@app.route("/api/hermes-summary")
def api_hermes_summary():
    try:
        board_state = _load_board_state()
        jobs = board_state.get("jobs", []) if isinstance(board_state, dict) else []
        p1_jobs = [job for job in jobs if isinstance(job, dict) and job.get("priority_lane") == "P1"]
        p2_jobs = [job for job in jobs if isinstance(job, dict) and job.get("priority_lane") == "P2"]
        missing_ro_jobs = [
            job for job in jobs
            if isinstance(job, dict) and any(alert.get("code") == "missing_ro" for alert in job.get("alerts", []))
        ]
        clock_in_jobs = [
            job for job in jobs
            if isinstance(job, dict) and any(alert.get("code") == "verify_tech_clock_in" for alert in job.get("alerts", []))
        ]
        needs_review_jobs = [job for job in jobs if isinstance(job, dict) and job.get("waiting_on") == "Needs Review"]

        recommendations = []
        if p1_jobs:
            top = p1_jobs[:3]
            recommendations.append(
                "Best next actions: " +
                "; ".join(
                    f"{job.get('ro', 'Unknown RO')} ({job.get('waiting_on', 'Needs Review')}): {job.get('next_action', '')}"
                    for job in top
                )
            )
        if p2_jobs:
            recommendations.append(
                f"Controlled action gap: {len(p2_jobs)} job(s) currently need information, estimate work, approval follow-up, or production-control movement."
            )
        if clock_in_jobs:
            recommendations.append(
                f"Productivity watch: {len(clock_in_jobs)} job(s) need a quick tech clock-in verification so advisors can trust the progress signal."
            )
        if missing_ro_jobs:
            recommendations.append(
                f"Data quality: {len(missing_ro_jobs)} board item(s) are missing a confirmed RO and should be cleaned up before they drift."
            )
        if needs_review_jobs:
            recommendations.append(
                f"Intelligence gap: {len(needs_review_jobs)} job(s) still need stronger status mapping so the board can coach more precisely."
            )
        if not recommendations:
            recommendations.append(
                "Momentum looks steady right now. Keep advisors ahead of technicians and protect the next customer promise window."
            )

        return jsonify(
            {
                "source": "board_rules_v1",
                "status": "ok",
                "summary": "\n".join(recommendations),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    except Exception:
        return jsonify({"summary": "Hermes temporarily unavailable.", "timestamp": "--"})


@app.route("/api/morning-briefing")
def api_morning_briefing():
    board_state = _load_board_state()
    jobs = board_state.get("jobs", []) if isinstance(board_state, dict) else []
    p1_jobs = [job for job in jobs if isinstance(job, dict) and job.get("priority_lane") == "P1"]
    p2_jobs = [job for job in jobs if isinstance(job, dict) and job.get("priority_lane") == "P2"]
    clock_alerts = [
        job for job in jobs
        if isinstance(job, dict) and any(alert.get("code") == "verify_tech_clock_in" for alert in job.get("alerts", []))
    ]

    lines = [
        f"Morning focal point: {len(p1_jobs)} P1 job(s) and {len(p2_jobs)} P2 job(s) need the strongest attention from 8 to noon."
    ]
    if p1_jobs:
        lines.append(
            "Top fires: " + "; ".join(
                f"{job.get('ro', 'Unknown RO')} waiting on {job.get('waiting_on', 'Needs Review')}" for job in p1_jobs[:3]
            )
        )
    if p2_jobs:
        lines.append(
            "Action gap: " + "; ".join(
                f"{job.get('ro', 'Unknown RO')} in {job.get('workflow_status', 'unknown')}" for job in p2_jobs[:4]
            )
        )
    if clock_alerts:
        lines.append(
            f"Productivity watch: {len(clock_alerts)} job(s) need a quick tech clock-in verification before the lunch reset."
        )
    if not p1_jobs and not p2_jobs:
        lines.append("No major fires right now. Keep momentum steady, protect customer trust, and prepare the next handoff early.")

    return jsonify({"briefing": "\n".join(lines), "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})


@app.route("/api/afternoon-briefing")
def api_afternoon_briefing():
    board_state = _load_board_state()
    jobs = board_state.get("jobs", []) if isinstance(board_state, dict) else []
    p1_jobs = [job for job in jobs if isinstance(job, dict) and job.get("priority_lane") == "P1"]
    p2_jobs = [job for job in jobs if isinstance(job, dict) and job.get("priority_lane") == "P2"]
    ready_jobs = [
        job for job in jobs
        if isinstance(job, dict) and job.get("workflow_status") in {"ready", "finished", "advisor_finalize_ro"}
    ]
    unresolved = [job for job in jobs if isinstance(job, dict) and job.get("waiting_on") == "Needs Review"]

    lines = [
        f"Afternoon rollover: {len(p1_jobs)} P1 job(s) and {len(p2_jobs)} P2 job(s) still need protection before close of day."
    ]
    if ready_jobs:
        lines.append("Low-hanging closeouts: " + "; ".join(f"{job.get('ro', 'Unknown RO')} for {job.get('customer', 'Unknown Customer')}" for job in ready_jobs[:4]))
    if unresolved:
        lines.append(f"Cleanup watch: {len(unresolved)} job(s) still need stronger mapping or ownership cleanup before the late-day rush.")
    if not ready_jobs and not unresolved:
        lines.append("The afternoon board looks controlled. Keep customer promises tight and clear the final handoffs before close.")

    return jsonify({"briefing": "\n".join(lines), "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})


if __name__ == "__main__":
    print("🚀 Starting Country Club Advisor Command Board on 127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True, use_reloader=False)
