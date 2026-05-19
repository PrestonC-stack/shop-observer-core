import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, Response, jsonify, request

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(CURRENT_DIR)
SHOP_STATE_PATH = os.path.join(REPO_ROOT, "state", "shop_state.json")
BOARD_STATE_PATH = os.path.join(REPO_ROOT, "state", "board_state.json")
BOARD_ACTION_LOG_PATH = os.path.join(REPO_ROOT, "state", "board_actions.jsonl")
HERMES_LOG_PATH = os.path.join(REPO_ROOT, "state", "hermes_feedback.jsonl")
BOARD_OVERRIDE_LOG_PATH = os.path.join(REPO_ROOT, "state", "board_overrides.jsonl")
CALLIE_INSIGHTS_PATH = os.path.join(REPO_ROOT, "data", "callie_insights.json")
CALLIE_MODEL = os.environ.get("CALLIE_MODEL", "qwen2.5-coder:7b")
CALLIE_INSIGHTS_TTL_SECONDS = 90
CALLIE_TIMEOUT_SECONDS = int(os.environ.get("CALLIE_TIMEOUT_SECONDS", "45"))
_CALLIE_INSIGHTS_CACHE = {"expires_at": 0.0, "payload": None}

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
        .pulse-card { animation: pulseBorder 1.1s infinite; }
        .blink-icon { animation: pulseBorder 0.9s infinite; }
        .hidden-panel { display: none; }
        .chip-button { transition: transform 0.15s ease, opacity 0.15s ease; }
        .chip-button:hover { transform: translateY(-1px); opacity: 0.95; }
        .modal-shell { max-height: min(90vh, 980px); overflow-y: auto; width: min(100%, 1080px); }
        .modal-mode-active { background: rgba(16, 185, 129, 0.18); border-color: rgb(16 185 129 / 0.95); color: #ecfdf5; box-shadow: 0 0 0 2px rgba(16, 185, 129, 0.22); }
        .metric-card { background: linear-gradient(180deg, rgba(24, 24, 27, 0.96), rgba(9, 9, 11, 0.96)); }
        .panel-card { background: rgba(24, 24, 27, 0.92); }
        @keyframes pulseBorder {
            0% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.75), 0 0 18px rgba(245, 158, 11, 0.42); filter: brightness(1.05); }
            50% { box-shadow: 0 0 0 6px rgba(245, 158, 11, 0.18), 0 0 24px rgba(245, 158, 11, 0.52); filter: brightness(1.18); }
            100% { box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.0), 0 0 8px rgba(245, 158, 11, 0.18); filter: brightness(1.00); }
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
            <button class="top-tab rounded-2xl border border-zinc-800 bg-zinc-950 px-4 py-2 text-sm font-semibold text-zinc-300" data-panel="data-input-panel">Data Input</button>
            <button class="top-tab rounded-2xl border border-zinc-800 bg-zinc-950 px-4 py-2 text-sm font-semibold text-zinc-300" data-panel="training-panel">Training</button>
            <button id="morning-briefing" class="rounded-2xl border border-zinc-800 bg-zinc-950 px-4 py-2 text-sm font-semibold text-zinc-300">Morning Briefing</button>
            <button id="afternoon-briefing-top" class="rounded-2xl border border-zinc-800 bg-zinc-950 px-4 py-2 text-sm font-semibold text-zinc-300">Afternoon Brief</button>
            <a href="/bay-performance" target="_blank" class="rounded-2xl border border-zinc-800 bg-zinc-950 px-4 py-2 text-sm font-semibold text-zinc-300">Bay View</a>
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
                        <h2 class="text-xl font-bold">Callie Intelligence</h2>
                        <button id="open-hermes-ask" class="rounded-2xl border border-zinc-700 px-3 py-2 text-xs font-semibold text-zinc-200 hover:bg-zinc-800">Ask Callie</button>
                    </div>
                    <div id="hermes-summary" class="mt-4 rounded-2xl bg-zinc-950 p-4 text-sm leading-relaxed text-zinc-200 min-h-[180px]">Loading Callie insights...</div>
                    <div id="hermes-updated-at" class="mt-3 text-xs text-zinc-500"></div>
                </div>
            </section>
        </div>

        <div id="analytics-panel" class="mt-5 hidden-panel space-y-4">
            <div class="grid grid-cols-1 gap-4 md:grid-cols-4">
                <div class="metric-card rounded-3xl border border-zinc-800 p-5">
                    <div class="text-xs uppercase tracking-wide text-zinc-500">Shop Productivity Score</div>
                    <div id="metric-shop-productivity" class="mt-2 text-4xl font-black text-emerald-400">0%</div>
                </div>
                <div class="metric-card rounded-3xl border border-zinc-800 p-5">
                    <div class="text-xs uppercase tracking-wide text-zinc-500">Front Of House Score</div>
                    <div id="metric-front-score" class="mt-2 text-4xl font-black text-cyan-300">0%</div>
                </div>
                <div class="metric-card rounded-3xl border border-zinc-800 p-5">
                    <div class="text-xs uppercase tracking-wide text-zinc-500">Back Of House Score</div>
                    <div id="metric-back-score" class="mt-2 text-4xl font-black text-violet-300">0%</div>
                </div>
                <div class="metric-card rounded-3xl border border-zinc-800 p-5">
                    <div class="text-xs uppercase tracking-wide text-zinc-500">Support Score</div>
                    <div id="metric-support-score" class="mt-2 text-4xl font-black text-amber-300">0%</div>
                </div>
            </div>

            <div class="grid grid-cols-1 gap-4 xl:grid-cols-3">
                <div class="panel-card rounded-3xl border border-zinc-800 p-5">
                    <h2 class="text-xl font-bold">Productivity Pressure</h2>
                    <div id="productivity-patterns" class="mt-4 space-y-3"></div>
                </div>
                <div class="panel-card rounded-3xl border border-zinc-800 p-5">
                    <h2 class="text-xl font-bold">Customer Communication</h2>
                    <div id="communication-patterns" class="mt-4 space-y-3"></div>
                </div>
                <div class="panel-card rounded-3xl border border-zinc-800 p-5">
                    <h2 class="text-xl font-bold">Stuck Jobs</h2>
                    <div id="stuck-patterns" class="mt-4 space-y-3"></div>
                </div>
            </div>

            <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <div class="panel-card rounded-3xl border border-zinc-800 p-5">
                    <h2 class="text-xl font-bold">DVI Quality Watch</h2>
                    <div id="dvi-patterns" class="mt-4 space-y-3"></div>
                </div>
                <div class="panel-card rounded-3xl border border-zinc-800 p-5">
                    <h2 class="text-xl font-bold">Ownership Load</h2>
                    <div id="ownership-patterns" class="mt-4 space-y-3"></div>
                </div>
            </div>
        </div>

        <div id="data-input-panel" class="mt-5 hidden-panel space-y-4">
            <div class="grid grid-cols-1 gap-4 md:grid-cols-3">
                <div class="metric-card rounded-3xl border border-zinc-800 p-5">
                    <div class="text-xs uppercase tracking-wide text-zinc-500">Data Input Issues</div>
                    <div id="metric-data-issues" class="mt-2 text-4xl font-black text-blue-300">0</div>
                </div>
                <div class="metric-card rounded-3xl border border-zinc-800 p-5">
                    <div class="text-xs uppercase tracking-wide text-zinc-500">AutoFlow Cleanup Jobs</div>
                    <div id="metric-data-jobs" class="mt-2 text-4xl font-black text-amber-300">0</div>
                </div>
                <div class="metric-card rounded-3xl border border-zinc-800 p-5">
                    <div class="text-xs uppercase tracking-wide text-zinc-500">Most Common Miss</div>
                    <div id="metric-data-top" class="mt-2 text-xl font-black text-zinc-100">None yet</div>
                </div>
            </div>

            <div class="panel-card rounded-3xl border border-zinc-800 p-5">
                <h2 class="text-xl font-bold">Grouped Data Input Correction</h2>
                <p class="mt-2 text-sm text-zinc-400">Use this to fix what needs to be corrected in AutoFlow so the next pull gives the board cleaner evidence.</p>
                <div id="data-input-groups" class="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2"></div>
            </div>
        </div>

        <div id="training-panel" class="mt-5 hidden-panel space-y-4">
            <div class="grid grid-cols-1 gap-4 md:grid-cols-5">
                <div class="metric-card rounded-3xl border border-zinc-800 p-5"><div class="text-xs uppercase tracking-wide text-zinc-500">Mitch</div><div id="metric-train-mitch" class="mt-2 text-3xl font-black text-zinc-100">0</div></div>
                <div class="metric-card rounded-3xl border border-zinc-800 p-5"><div class="text-xs uppercase tracking-wide text-zinc-500">Drew</div><div id="metric-train-drew" class="mt-2 text-3xl font-black text-zinc-100">0</div></div>
                <div class="metric-card rounded-3xl border border-zinc-800 p-5"><div class="text-xs uppercase tracking-wide text-zinc-500">Preston</div><div id="metric-train-preston" class="mt-2 text-3xl font-black text-zinc-100">0</div></div>
                <div class="metric-card rounded-3xl border border-zinc-800 p-5"><div class="text-xs uppercase tracking-wide text-zinc-500">Technician</div><div id="metric-train-tech" class="mt-2 text-3xl font-black text-zinc-100">0</div></div>
                <div class="metric-card rounded-3xl border border-zinc-800 p-5"><div class="text-xs uppercase tracking-wide text-zinc-500">Overall Shop</div><div id="metric-train-shop" class="mt-2 text-3xl font-black text-zinc-100">0</div></div>
            </div>

            <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <div class="panel-card rounded-3xl border border-zinc-800 p-5">
                    <h2 class="text-xl font-bold">Coach The Repeats</h2>
                    <div id="training-categories" class="mt-4 space-y-3"></div>
                </div>
                <div class="panel-card rounded-3xl border border-zinc-800 p-5">
                    <h2 class="text-xl font-bold">Role Coaching</h2>
                    <div id="training-roles" class="mt-4 space-y-3"></div>
                </div>
            </div>
        </div>

        <div id="job-modal" class="hidden-panel fixed inset-0 z-50 bg-black/70 p-4">
            <div class="modal-shell mx-auto rounded-3xl border border-zinc-700 bg-zinc-950 p-6">
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
                return { label: "Critical", cls: "bg-red-500 text-white" };
            }
            if (normalized === "YELLOW") {
                return { label: "Moderate", cls: "bg-amber-400 text-zinc-950" };
            }
            return { label: "Good", cls: "bg-emerald-500 text-zinc-950" };
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
                alert.code === "missing_info" ||
                alert.code === "missing_customer_concern" ||
                alert.code === "missing_completed_dvi"
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

        function hasAlert(job, codes) {
            const alerts = Array.isArray(job.alerts) ? job.alerts : [];
            return alerts.some((alert) => codes.includes(alert.code));
        }

        function dataInputGroups(jobs) {
            return [
                {
                    key: "missing_tech_assignment",
                    label: "Missing tech assignment",
                    detail: "Dispatch/ownership is not clear enough for the board to trust who is on the job.",
                    jobs: jobs.filter((job) => hasAlert(job, ["missing_tech_assignment", "missing_info"]))
                },
                {
                    key: "missing_customer_concern",
                    label: "Weak or missing customer concern",
                    detail: "Concern detail is too thin for strong handoffs and clean AI guidance.",
                    jobs: jobs.filter((job) => hasAlert(job, ["missing_customer_concern"]))
                },
                {
                    key: "customer_follow_up_due",
                    label: "Missing customer update",
                    detail: "Expectation or callback timing needs to be tightened in AutoFlow notes/workflow.",
                    jobs: jobs.filter((job) => hasAlert(job, ["customer_follow_up_due"]))
                },
                {
                    key: "missing_completed_dvi",
                    label: "Missing completed DVI",
                    detail: "DVI completion or usable inspection evidence is not clear enough yet.",
                    jobs: jobs.filter((job) => hasAlert(job, ["missing_completed_dvi"]))
                },
                {
                    key: "status_mapping_gap",
                    label: "Bad or unclear workflow status",
                    detail: "The visible status is too loose or mismatched for the board to coach cleanly.",
                    jobs: jobs.filter((job) => hasAlert(job, ["status_mapping_gap"]) || job.waiting_on === "Needs Review")
                },
                {
                    key: "missing_ro",
                    label: "Missing RO linkage",
                    detail: "RO linkage or board traceability needs to be corrected before drift grows.",
                    jobs: jobs.filter((job) => hasAlert(job, ["missing_ro"]))
                }
            ];
        }

        function toneForCount(count) {
            if (count >= 5) return { label: "Blunt but fair", cls: "text-red-300" };
            if (count >= 3) return { label: "Firmer coaching", cls: "text-amber-300" };
            return { label: "Coach / helpful", cls: "text-emerald-300" };
        }

        function roleTrainingCounts(jobs) {
            const byRole = { Mitch: 0, Drew: 0, Preston: 0, Technician: 0, "Overall Shop": 0 };
            jobs.forEach((job) => {
                const count = Array.isArray(job.alerts) ? job.alerts.length : 0;
                byRole["Overall Shop"] += count;
                if (job.waiting_on === "Mitch") byRole.Mitch += count;
                if (job.waiting_on === "Drew") byRole.Drew += count;
                if (job.waiting_on === "Preston") byRole.Preston += count;
                if (hasAlert(job, ["missing_tech_assignment", "verify_tech_clock_in", "missing_completed_dvi"])) {
                    byRole.Technician += 1;
                }
            });
            return byRole;
        }

        function renderAnalytics(boardState) {
            const jobs = Array.isArray(boardState.jobs) ? boardState.jobs : [];
            const clocks = jobs.filter((job) => (job.alerts || []).some((alert) => alert.code === "verify_tech_clock_in")).length;
            const communicationNeeds = jobs.filter((job) => (job.alerts || []).some((alert) => alert.code === "customer_follow_up_due")).length;
            const stuckJobs = jobs.filter((job) => job.priority_lane === "P2" || job.waiting_on === "Needs Review").length;
            const dviIssues = jobs.filter((job) => hasAlert(job, ["missing_completed_dvi"])).length;
            const dataNeeds = jobs.filter((job) => (job.alerts || []).some((alert) =>
                alert.code === "missing_ro" ||
                alert.code === "status_mapping_gap" ||
                alert.code === "missing_tech_assignment" ||
                alert.code === "missing_info" ||
                alert.code === "missing_customer_concern" ||
                alert.code === "missing_completed_dvi"
            )).length;
            const clearCommunication = Math.max(0, jobs.length - communicationNeeds);
            const clearProductivity = Math.max(0, jobs.length - clocks);
            const clearData = Math.max(0, jobs.length - dataNeeds);
            const scoreBase = Math.max(jobs.length, 1);
            const shopScore = Math.round(((clearCommunication + clearProductivity + clearData) / (scoreBase * 3)) * 100);
            const frontScore = Math.round(((clearCommunication + Math.max(0, jobs.length - stuckJobs)) / (scoreBase * 2)) * 100);
            const backScore = Math.round(((clearProductivity + Math.max(0, jobs.length - dviIssues)) / (scoreBase * 2)) * 100);

            document.getElementById("metric-shop-productivity").textContent = shopScore + "%";
            document.getElementById("metric-front-score").textContent = frontScore + "%";
            document.getElementById("metric-back-score").textContent = backScore + "%";
            document.getElementById("metric-support-score").textContent = Math.round((frontScore + backScore + shopScore) / 3) + "%";

            const statusCounts = {};
            const ownerCounts = {};
            jobs.forEach((job) => {
                const status = job.workflow_status || "unknown";
                const owner = job.waiting_on || "Needs Review";
                statusCounts[status] = (statusCounts[status] || 0) + 1;
                ownerCounts[owner] = (ownerCounts[owner] || 0) + 1;
            });

            const ownerHtml = Object.entries(ownerCounts)
                .sort((a, b) => b[1] - a[1])
                .map(([owner, count]) => '<div class="rounded-2xl bg-zinc-950 px-4 py-3 text-sm text-zinc-200"><span class="font-semibold">' + escapeHtml(owner) + ":</span> " + count + "</div>")
                .join("");

            document.getElementById("productivity-patterns").innerHTML =
                '<div class="rounded-2xl bg-zinc-950 px-4 py-3 text-sm text-zinc-200"><span class="font-semibold">Clock-in checks:</span> ' + clocks + '</div>' +
                '<div class="rounded-2xl bg-zinc-950 px-4 py-3 text-sm text-zinc-200"><span class="font-semibold">Data clear:</span> ' + clearData + ' / ' + jobs.length + '</div>' +
                '<div class="rounded-2xl bg-zinc-950 px-4 py-3 text-sm text-zinc-200"><span class="font-semibold">Front vs back:</span> front ' + frontScore + '% • back ' + backScore + '%</div>';
            document.getElementById("communication-patterns").innerHTML =
                '<div class="rounded-2xl bg-zinc-950 px-4 py-3 text-sm text-zinc-200"><span class="font-semibold">Communication misses:</span> ' + communicationNeeds + '</div>' +
                '<div class="rounded-2xl bg-zinc-950 px-4 py-3 text-sm text-zinc-200"><span class="font-semibold">Communication clear:</span> ' + clearCommunication + ' / ' + jobs.length + '</div>' +
                '<div class="rounded-2xl bg-zinc-950 px-4 py-3 text-sm text-zinc-200"><span class="font-semibold">Mitch-facing actions:</span> ' + (ownerCounts.Mitch || 0) + '</div>';
            document.getElementById("stuck-patterns").innerHTML =
                '<div class="rounded-2xl bg-zinc-950 px-4 py-3 text-sm text-zinc-200"><span class="font-semibold">Jobs stuck too long / needs movement:</span> ' + stuckJobs + '</div>' +
                Object.entries(statusCounts)
                    .sort((a, b) => b[1] - a[1])
                    .slice(0, 4)
                    .map(([status, count]) => '<div class="rounded-2xl bg-zinc-950 px-4 py-3 text-sm text-zinc-200"><span class="font-semibold">' + escapeHtml(status) + ':</span> ' + count + '</div>')
                    .join("");
            document.getElementById("dvi-patterns").innerHTML =
                '<div class="rounded-2xl bg-zinc-950 px-4 py-3 text-sm text-zinc-200"><span class="font-semibold">Repeated DVI quality issues:</span> ' + dviIssues + '</div>' +
                '<div class="rounded-2xl bg-zinc-950 px-4 py-3 text-sm text-zinc-200"><span class="font-semibold">Support score:</span> ' + shopScore + '%</div>' +
                '<div class="rounded-2xl bg-zinc-950 px-4 py-3 text-sm text-zinc-200"><span class="font-semibold">Data cleanups needed:</span> ' + dataNeeds + '</div>';
            document.getElementById("ownership-patterns").innerHTML =
                (ownerHtml || '<div class="rounded-2xl bg-zinc-950 px-4 py-3 text-sm text-zinc-400">No ownership patterns available yet.</div>') +
                '<div class="rounded-2xl bg-zinc-950 px-4 py-3 text-sm text-zinc-200"><span class="font-semibold">Advisor support load:</span> Mitch actions ' + communicationNeeds + ', Drew checks ' + clocks + ', Data cleanups ' + dataNeeds + '</div>';
        }

        function renderDataInput(boardState) {
            const jobs = Array.isArray(boardState.jobs) ? boardState.jobs : [];
            const groups = dataInputGroups(jobs);
            const issueCount = groups.reduce((sum, group) => sum + group.jobs.length, 0);
            const top = [...groups].sort((a, b) => b.jobs.length - a.jobs.length)[0];

            document.getElementById("metric-data-issues").textContent = String(issueCount);
            document.getElementById("metric-data-jobs").textContent = String(jobs.filter((job) => groupHasJobs(job, groups)).length);
            document.getElementById("metric-data-top").textContent = top && top.jobs.length ? top.label : "None yet";

            document.getElementById("data-input-groups").innerHTML = groups.map((group) => (
                '<div class="rounded-3xl border border-zinc-800 bg-zinc-950 p-5">' +
                    '<div class="flex items-start justify-between gap-3">' +
                        '<div><div class="text-lg font-black text-zinc-100">' + escapeHtml(group.label) + '</div><div class="mt-1 text-sm text-zinc-400">' + escapeHtml(group.detail) + '</div></div>' +
                        '<div class="rounded-full bg-blue-500/10 px-3 py-1 text-sm font-bold text-blue-300">' + group.jobs.length + '</div>' +
                    '</div>' +
                    '<div class="mt-4 space-y-2">' +
                        (group.jobs.length
                            ? group.jobs.slice(0, 6).map((job) => '<button class="w-full rounded-2xl border border-zinc-800 bg-zinc-900 px-4 py-3 text-left text-sm text-zinc-200 hover:bg-zinc-800 data-input-job" data-ro="' + escapeHtml(job.ro || "") + '">' + escapeHtml(job.ro || "Unknown RO") + ' • ' + escapeHtml(job.customer || "Unknown Customer") + ' • ' + escapeHtml(job.workflow_status || "unknown") + '</button>').join("")
                            : '<div class="rounded-2xl border border-dashed border-zinc-800 px-4 py-3 text-sm text-zinc-500">Nothing in this correction bucket right now.</div>') +
                    '</div>' +
                '</div>'
            )).join("");
            wireDataInputJobs();
        }

        function groupHasJobs(job, groups) {
            return groups.some((group) => group.jobs.some((item) => String(item.ro || "") === String(job.ro || "")));
        }

        function renderTraining(boardState) {
            const jobs = Array.isArray(boardState.jobs) ? boardState.jobs : [];
            const groups = dataInputGroups(jobs);
            const roleCounts = roleTrainingCounts(jobs);

            document.getElementById("metric-train-mitch").textContent = String(roleCounts.Mitch);
            document.getElementById("metric-train-drew").textContent = String(roleCounts.Drew);
            document.getElementById("metric-train-preston").textContent = String(roleCounts.Preston);
            document.getElementById("metric-train-tech").textContent = String(roleCounts.Technician);
            document.getElementById("metric-train-shop").textContent = String(roleCounts["Overall Shop"]);

            document.getElementById("training-categories").innerHTML = groups
                .filter((group) => group.jobs.length)
                .sort((a, b) => b.jobs.length - a.jobs.length)
                .map((group) => {
                    const tone = toneForCount(group.jobs.length);
                    return '<div class="rounded-2xl bg-zinc-950 px-4 py-4 text-sm text-zinc-200">' +
                        '<div class="flex items-center justify-between gap-3"><div class="font-semibold">' + escapeHtml(group.label) + '</div><div class="text-xs font-bold ' + tone.cls + '">' + tone.label + '</div></div>' +
                        '<div class="mt-2 text-zinc-400">Seen on ' + group.jobs.length + ' active job(s). Focus on the repeat so the board has better evidence next pull.</div>' +
                        '<div class="mt-2 text-zinc-300">' + escapeHtml(group.detail) + '</div>' +
                    '</div>';
                }).join("") || '<div class="rounded-2xl bg-zinc-950 px-4 py-4 text-sm text-zinc-500">No repeating training rhythms are standing out right now.</div>';

            const roleRows = [
                ["Mitch", roleCounts.Mitch, "Customer updates, estimate handoffs, and closeout rhythm."],
                ["Drew", roleCounts.Drew, "Dispatch clarity, floor checks, and production-control follow-through."],
                ["Preston", roleCounts.Preston, "Escalation clarity and technical review capture."],
                ["Technician", roleCounts.Technician, "Clock-in, DVI completion, and clear work ownership."],
                ["Overall Shop", roleCounts["Overall Shop"], "Shared handoff discipline and better source data."]
            ];
            document.getElementById("training-roles").innerHTML = roleRows.map(([label, count, detail]) => {
                const tone = toneForCount(count);
                return '<div class="rounded-2xl bg-zinc-950 px-4 py-4 text-sm text-zinc-200">' +
                    '<div class="flex items-center justify-between gap-3"><div class="font-semibold">' + escapeHtml(label) + '</div><div class="text-xs font-bold ' + tone.cls + '">' + tone.label + '</div></div>' +
                    '<div class="mt-2 text-zinc-400">' + count + ' current coaching signal(s).</div>' +
                    '<div class="mt-2 text-zinc-300">' + escapeHtml(detail) + '</div>' +
                '</div>';
            }).join("");
        }

        function renderBoardState(boardState) {
            latestBoardState = boardState;
            latestActionState = boardState.action_state || {};
            document.getElementById("board-updated-at").textContent = boardState.generated_at || "__TIMESTAMP__";
            renderLanes(boardState);
            renderSnapshot(boardState);
            renderNextActions(boardState);
            renderAnalytics(boardState);
            renderDataInput(boardState);
            renderTraining(boardState);
            wireJobCards();
            wireHelperChips();
        }

        function renderHermesSummary(payload) {
            const target = document.getElementById("hermes-summary");
            if (!target) return;
            const conflictCount = Number(payload.conflict_count || ((payload.conflicts || []).length) || 0);
            const header = payload.shop_summary || payload.summary || "No summary available.";
            const details = [];
            if (payload.summary && payload.shop_summary && payload.summary !== payload.shop_summary) {
                details.push(payload.summary);
            }
            if (conflictCount > 0) {
                details.push("Active source/data conflicts: " + conflictCount);
            }
            const lines = [header].concat(details).join("\\n")
                .split(/\\n+/)
                .map((line) => line.trim())
                .filter(Boolean);

            target.innerHTML = lines.map((line) => (
                '<div class="mb-3 rounded-2xl bg-zinc-900 px-4 py-3 text-sm text-zinc-100">' + escapeHtml(line) + "</div>"
            )).join("") || '<div class="rounded-2xl bg-zinc-900 px-4 py-3 text-sm text-zinc-400">No summary available.</div>';

            document.getElementById("hermes-updated-at").textContent = "Last Callie update: " + (payload.timestamp || payload.generated_at || "--");
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
            fetch("/api/callie/insights", { cache: "no-store" })
                .then((response) => {
                    if (!response.ok) throw new Error("Request failed");
                    return response.json();
                })
                .then(renderHermesSummary)
                .catch(() => renderHermesSummary({ summary: "Callie insights unavailable.", timestamp: "--" }));
        }

        function refreshBoard() {
            loadBoardState();
            loadHermesSummary();
        }

        function hardRefreshBoard() {
            window.location.reload();
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

        function wireDataInputJobs() {
            document.querySelectorAll(".data-input-job").forEach((button) => {
                button.addEventListener("click", () => openJobModal(button.dataset.ro || "", "data"));
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
                missing: "Missing Info",
                hermes: "Ask Callie",
                details: "Quick Note"
            };

            return (
                '<div class="rounded-2xl bg-zinc-900 p-4">' +
                    '<div class="text-xs uppercase tracking-wide text-zinc-500">Action Center</div>' +
                    '<div class="mt-3 flex flex-wrap gap-2">' +
                        '<button class="modal-mode rounded-2xl border border-zinc-700 px-3 py-2 text-xs font-semibold text-zinc-200 hover:bg-zinc-800" data-mode="communication" type="button">☎ Customer Update</button>' +
                        '<button class="modal-mode rounded-2xl border border-zinc-700 px-3 py-2 text-xs font-semibold text-zinc-200 hover:bg-zinc-800" data-mode="productivity" type="button">⏱ Productivity Check</button>' +
                        '<button class="modal-mode rounded-2xl border border-zinc-700 px-3 py-2 text-xs font-semibold text-zinc-200 hover:bg-zinc-800" data-mode="data" type="button">🧠 Board / Data Fix</button>' +
                        '<button class="modal-mode rounded-2xl border border-zinc-700 px-3 py-2 text-xs font-semibold text-zinc-200 hover:bg-zinc-800" data-mode="missing" type="button">⚠ Missing Info</button>' +
                        '<button class="modal-mode rounded-2xl border border-zinc-700 px-3 py-2 text-xs font-semibold text-zinc-200 hover:bg-zinc-800" data-mode="hermes" type="button">Ask Callie</button>' +
                    "</div>" +
                    '<div class="mt-4 text-sm font-semibold text-zinc-200" id="modal-mode-label">' + escapeHtml(labels[focusMode] || labels.details) + "</div>" +
                    '<div class="mt-2 text-xs text-zinc-400">Green saves a note or applies a local correction. Blue sends the question to Callie and asks for a response.</div>' +
                    '<textarea id="modal-note" class="mt-2 min-h-[120px] w-full rounded-2xl border border-zinc-700 bg-zinc-950 px-4 py-3 text-sm text-zinc-100 outline-none focus:border-emerald-500" placeholder="' + escapeHtml(placeholders[focusMode] || placeholders.details) + '"></textarea>' +
                    '<div class="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2">' +
                        '<div><div class="mb-1 text-xs uppercase tracking-wide text-zinc-500">Override lane</div><select id="override-priority-lane" class="w-full rounded-2xl border border-zinc-700 bg-zinc-950 px-4 py-3 text-sm text-zinc-100"><option value="">No change</option><option value="P1">P1</option><option value="P2">P2</option><option value="P3">P3</option><option value="P4">P4</option></select></div>' +
                        '<div><div class="mb-1 text-xs uppercase tracking-wide text-zinc-500">Override waiting on</div><select id="override-waiting-on" class="w-full rounded-2xl border border-zinc-700 bg-zinc-950 px-4 py-3 text-sm text-zinc-100"><option value="">No change</option><option value="Mitch">Mitch</option><option value="Drew">Drew</option><option value="Preston">Preston</option><option value="External Hold">External Hold</option><option value="Needs Review">Needs Review</option></select></div>' +
                        '<div><div class="mb-1 text-xs uppercase tracking-wide text-zinc-500">Override technician</div><input id="override-technician" class="w-full rounded-2xl border border-zinc-700 bg-zinc-950 px-4 py-3 text-sm text-zinc-100 outline-none focus:border-emerald-500" placeholder="Luis Cervantes, Jonathan L, TC Charleston..."></div>' +
                        '<div><div class="mb-1 text-xs uppercase tracking-wide text-zinc-500">Override summary</div><input id="override-summary" class="w-full rounded-2xl border border-zinc-700 bg-zinc-950 px-4 py-3 text-sm text-zinc-100 outline-none focus:border-emerald-500" placeholder="Clear concern / summary"></div>' +
                    '</div>' +
                    '<div class="mt-3 flex flex-wrap gap-2">' +
                        '<button id="submit-board-action" class="rounded-2xl border border-emerald-700 bg-emerald-900/40 px-4 py-2 text-sm font-semibold text-emerald-100 hover:bg-emerald-900/70" type="button">Save Note / Apply Correction</button>' +
                        '<button id="submit-hermes-question" class="rounded-2xl border border-blue-700 bg-blue-900/40 px-4 py-2 text-sm font-semibold text-blue-100 hover:bg-blue-900/70" type="button">Send to Callie</button>' +
                    "</div>" +
                    '<div id="modal-response" class="mt-4 rounded-2xl border border-zinc-800 bg-zinc-950 p-4 text-sm text-zinc-300">Use this panel to log what happened, capture what was found, or ask Callie what to do next.</div>' +
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
            const reasons = (job.board_reasons || []).map((reason) =>
                "<li class=\\"mb-2\\">" + escapeHtml(reason) + "</li>"
            ).join("");
            const concerns = (job.reason_vehicle_is_here || []).map((item) =>
                "<li class=\\"mb-2\\">" + escapeHtml(item) + "</li>"
            ).join("");
            const techEvidence = (job.technician_candidates || []).length
                ? (job.technician_candidates || []).map((name) => '<span class="rounded-full border border-zinc-700 bg-zinc-950 px-3 py-1 text-xs text-zinc-200">' + escapeHtml(name) + '</span>').join("")
                : '<span class="text-zinc-500">No technician evidence found yet.</span>';
            const sourceBits = [];
            if (job.source_evidence && job.source_evidence.dvi_status) sourceBits.push("DVI: " + job.source_evidence.dvi_status);
            if (job.source_evidence && job.source_evidence.source_work_order_status) sourceBits.push("WO status: " + job.source_evidence.source_work_order_status);
            if (job.source_evidence && job.source_evidence.source_dvi_status) sourceBits.push("DVI status: " + job.source_evidence.source_dvi_status);
            if (job.source_evidence && job.source_evidence.latest_activity) sourceBits.push("Latest activity: " + job.source_evidence.latest_activity);
            if (job.source_evidence && job.source_evidence.routing_bucket_detected) sourceBits.push("Routing bucket detected");

            document.getElementById("modal-body").innerHTML =
                '<div class="grid grid-cols-1 gap-4 md:grid-cols-2">' +
                    '<div class="rounded-2xl bg-zinc-900 p-4"><div class="text-xs uppercase tracking-wide text-zinc-500">Status</div><div class="mt-2 text-lg font-bold text-zinc-100">' + escapeHtml(job.workflow_status || "unknown") + "</div></div>" +
                    '<div class="rounded-2xl bg-zinc-900 p-4"><div class="text-xs uppercase tracking-wide text-zinc-500">Risk</div><div class="mt-2 text-lg font-bold text-zinc-100">' + escapeHtml(job.risk_level || "NORMAL") + "</div></div>" +
                    '<div class="rounded-2xl bg-zinc-900 p-4"><div class="text-xs uppercase tracking-wide text-zinc-500">Advisor</div><div class="mt-2 text-lg font-bold text-zinc-100">' + escapeHtml(job.advisor || "Unknown") + "</div></div>" +
                    '<div class="rounded-2xl bg-zinc-900 p-4"><div class="text-xs uppercase tracking-wide text-zinc-500">Technician</div><div class="mt-2 text-lg font-bold ' + ((String(job.technician || "").toLowerCase() === "unassigned" || !String(job.technician || "").trim()) ? "text-amber-300" : "text-zinc-100") + '">' + escapeHtml(job.technician || "Unassigned") + "</div></div>" +
                "</div>" +
                '<div class="mt-4 rounded-2xl bg-zinc-900 p-4"><div class="text-xs uppercase tracking-wide text-zinc-500">Next Move</div><div class="mt-2 text-zinc-100">' + escapeHtml(job.next_action || "Keep momentum moving.") + "</div></div>" +
                '<div class="mt-4 rounded-2xl bg-zinc-900 p-4"><div class="text-xs uppercase tracking-wide text-zinc-500">Summary</div><div class="mt-2 text-zinc-100">' + escapeHtml(job.summary || "No summary available.") + "</div></div>" +
                '<div class="mt-4 rounded-2xl bg-zinc-900 p-4"><div class="text-xs uppercase tracking-wide text-zinc-500">Customer Concern Evidence</div><ul class="mt-2 text-zinc-100">' + (concerns || "<li>No DVI concern evidence found.</li>") + "</ul></div>" +
                '<div class="mt-4 rounded-2xl bg-zinc-900 p-4"><div class="text-xs uppercase tracking-wide text-zinc-500">Technician Evidence</div><div class="mt-2 flex flex-wrap gap-2">' + techEvidence + '</div><div class="mt-3 text-xs text-zinc-400">' + escapeHtml(sourceBits.join(" • ") || "No extra source evidence available yet.") + '</div></div>' +
                '<div class="mt-4 rounded-2xl bg-zinc-900 p-4"><div class="text-xs uppercase tracking-wide text-zinc-500">Why The Board Put It Here</div><ul class="mt-2 text-zinc-100">' + (reasons || "<li>No board reasoning captured yet.</li>") + "</ul></div>" +
                '<div class="mt-4 rounded-2xl bg-zinc-900 p-4"><div class="text-xs uppercase tracking-wide text-zinc-500">Helper Alerts</div><ul class="mt-2 text-zinc-100">' + (alerts || "<li>No active alerts.</li>") + "</ul></div>" +
                buildActionPanel(job, mode);

            document.getElementById("job-modal").style.display = "flex";
            wireModalActions();
            setModalMode(mode);
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
                missing: "Missing Info",
                hermes: "Ask Callie",
                details: "Quick Note"
            };
            const placeholderMap = {
                communication: "Log what was communicated to the customer, callback time, or new promise window.",
                productivity: "Log what you found on the floor. Who is on it, is labor clocked, and what is blocking progress?",
                data: "Log the board mismatch, missing RO, status cleanup, or data issue you want Hermes to learn from.",
                missing: "Log what info is missing: technician assignment, customer concern detail, RO linkage, or anything else the board needs.",
                hermes: "Ask Callie a targeted question about this job, the blocker, or the next best move.",
                details: "Log a quick support note so the board can help the next handoff."
            };
            const label = document.getElementById("modal-mode-label");
            const note = document.getElementById("modal-note");
            if (label) label.textContent = labelMap[mode] || labelMap.details;
            if (note) note.placeholder = placeholderMap[mode] || placeholderMap.details;
            document.querySelectorAll(".modal-mode").forEach((button) => {
                button.classList.toggle("modal-mode-active", button.dataset.mode === mode);
            });
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
            document.getElementById("data-input-panel").style.display = panelId === "data-input-panel" ? "block" : "none";
            document.getElementById("training-panel").style.display = panelId === "training-panel" ? "block" : "none";
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
                    document.getElementById("job-modal").style.display = "flex";
                    document.getElementById("print-briefing").addEventListener("click", () => openPrintWindow("Morning Briefing", "Quick team focal point for P1/P2 work and lunch reset planning.", lines, payload.timestamp || "--"));
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
                        '<div class="flex flex-wrap gap-2">' +
                        '<button id="print-afternoon-briefing" class="rounded-2xl border border-zinc-700 px-4 py-2 text-sm font-semibold text-zinc-200 hover:bg-zinc-900" type="button">Print Briefing</button>' +
                        '</div>' +
                        '<div class="rounded-2xl bg-zinc-900 p-5 text-xs text-zinc-400">Generated: ' + escapeHtml(payload.timestamp || "--") + '</div>';
                    document.getElementById("job-modal").style.display = "flex";
                    document.getElementById("print-afternoon-briefing").addEventListener("click", () => openPrintWindow("Afternoon Brief", "Post-lunch rollover check for remaining P1/P2 pressure and closeout opportunities.", lines, payload.timestamp || "--"));
                    renderHermesSummary({ summary: payload.briefing || "No briefing available.", timestamp: payload.timestamp || "--" });
                })
                .catch(() => showToast("Afternoon brief unavailable right now.", "error"));
        }

        function openHermesAskModal() {
            activeModalRo = "";
            activeModalMode = "hermes";
            document.getElementById("modal-title").textContent = "Ask Callie";
            document.getElementById("modal-subtitle").textContent = "Ask a board question, flag a pattern, or request help with the next move.";
            document.getElementById("modal-body").innerHTML = buildActionPanel({
                ro: "",
                customer: "General board question"
            }, "hermes");
            document.getElementById("job-modal").style.display = "flex";
            wireModalActions();
            setModalMode("hermes");
        }

        function openPrintWindow(title, subtitle, lines, timestamp) {
            const printWindow = window.open("", "_blank", "width=900,height=760");
            if (!printWindow) {
                showToast("Popup blocked. Allow popups to print the briefing.", "error");
                return;
            }
            const safeLines = (Array.isArray(lines) ? lines : []).filter(Boolean);
            const html = `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>${escapeHtml(title)}</title>
    <style>
        @page { size: auto; margin: 0.5in; }
        body { font-family: Arial, sans-serif; color: #111; background: #fff; margin: 0; }
        .sheet { max-width: 8in; margin: 0 auto; padding: 0.1in 0; }
        h1 { margin: 0; font-size: 22px; }
        .sub { margin-top: 6px; color: #444; font-size: 12px; }
        ol { margin: 18px 0 0 20px; padding: 0; }
        li { margin-bottom: 10px; line-height: 1.35; font-size: 13px; }
        .meta { margin-top: 14px; font-size: 11px; color: #666; }
        .notes { margin-top: 18px; }
        .label { font-weight: bold; font-size: 12px; }
        .box { border: 1px solid #bbb; min-height: 64px; margin-top: 6px; padding: 8px; }
    </style>
</head>
<body>
    <div class="sheet">
        <h1>${escapeHtml(title)}</h1>
        <div class="sub">${escapeHtml(subtitle)}</div>
        <ol>${safeLines.map((line) => `<li>${escapeHtml(line)}</li>`).join("")}</ol>
        <div class="notes">
            <div class="label">Advisor notes / to-dos</div>
            <div class="box"></div>
        </div>
        <div class="notes">
            <div class="label">Tech follow-ups / questions to answer</div>
            <div class="box"></div>
        </div>
        <div class="meta">Generated: ${escapeHtml(timestamp || "--")}</div>
    </div>
</body>
</html>`;
            printWindow.document.open();
            printWindow.document.write(html);
            printWindow.document.close();
            printWindow.focus();
            printWindow.print();
        }

        function submitBoardAction() {
            const note = document.getElementById("modal-note");
            const laneOverride = document.getElementById("override-priority-lane");
            const waitingOverride = document.getElementById("override-waiting-on");
            const technicianOverride = document.getElementById("override-technician");
            const summaryOverride = document.getElementById("override-summary");
            const hasOverride = Boolean(
                (laneOverride && laneOverride.value.trim()) ||
                (waitingOverride && waitingOverride.value.trim()) ||
                (technicianOverride && technicianOverride.value.trim()) ||
                (summaryOverride && summaryOverride.value.trim())
            );
            if ((!note || !note.value.trim()) && !hasOverride) {
                showToast("Add a note or an override so the board knows what changed.", "error");
                return;
            }
            fetch("/api/board-action", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    ro: activeModalRo,
                    action_type: activeModalMode,
                    note: note ? note.value.trim() : "",
                    override_priority_lane: laneOverride ? laneOverride.value.trim() : "",
                    override_waiting_on: waitingOverride ? waitingOverride.value.trim() : "",
                    override_technician: technicianOverride ? technicianOverride.value.trim() : "",
                    override_summary: summaryOverride ? summaryOverride.value.trim() : "",
                    source: "dashboard"
                })
            })
                .then((response) => response.json())
                .then((payload) => {
                    const panel = document.getElementById("modal-response");
                    if (panel) {
                        panel.innerHTML = '<div class="font-semibold text-emerald-300">' + escapeHtml(payload.message || "Update saved.") + '</div>' +
                            (payload.warning ? '<div class="mt-3 rounded-2xl border border-amber-600 bg-amber-950/50 px-4 py-3 text-amber-100"><div class="font-semibold">Warning</div><div class="mt-1">' + escapeHtml(payload.warning) + '</div></div>' : '');
                    }
                    showToast(payload.message || "Update saved.");
                    note.value = "";
                    refreshBoard();
                })
                .catch(() => showToast("Unable to save that update right now.", "error"));
        }

        function submitHermesQuestion() {
            const note = document.getElementById("modal-note");
            if (!note || !note.value.trim()) {
                showToast("Type a question for Callie first.", "error");
                return;
            }
            const panel = document.getElementById("modal-response");
            const question = note.value.trim();
            const sendButton = document.getElementById("submit-hermes-question");
            if (sendButton) sendButton.disabled = true;
            if (panel) {
                panel.innerHTML = '<div class="font-semibold text-blue-300">Callie Response</div><div class="mt-2 text-zinc-200">Callie is checking the board now...</div>';
            }
            const slowModelTimer = window.setTimeout(() => {
                if (panel) {
                    panel.innerHTML = '<div class="font-semibold text-amber-300">Callie Response</div><div class="mt-2 text-zinc-200">Callie is still working on it. If the live model stays slow, the fast board evidence layer will answer instead.</div>';
                }
            }, 8000);
            fetch("/api/callie/ask", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    ro_number: activeModalRo || null,
                    mode: activeModalMode,
                    question: question,
                    source: "dashboard"
                })
            })
                .then((response) => response.json())
                .then((payload) => {
                    window.clearTimeout(slowModelTimer);
                    const answer = payload.response || payload.answer || payload.message || "Callie acknowledged the note.";
                    if (panel) {
                        panel.innerHTML = '<div class="font-semibold text-blue-300">Callie Response</div><div class="mt-2 text-zinc-200">' + escapeHtml(answer) + '</div>';
                    }
                    renderHermesSummary({ summary: answer, timestamp: payload.timestamp || "--" });
                    showToast("Callie updated.");
                })
                .catch(() => {
                    window.clearTimeout(slowModelTimer);
                    if (panel) {
                        panel.innerHTML = '<div class="font-semibold text-amber-300">Callie Response</div><div class="mt-2 text-zinc-200">Callie is a little slow right now. Try a simpler question or refresh the board and try again.</div>';
                    }
                    showToast("Callie could not respond right now.", "error");
                })
                .finally(() => {
                    if (sendButton) sendButton.disabled = false;
                });
        }

        document.addEventListener("DOMContentLoaded", () => {
            document.getElementById("refresh-jobs").addEventListener("click", hardRefreshBoard);
            document.getElementById("close-modal").addEventListener("click", closeJobModal);
            document.getElementById("morning-briefing").addEventListener("click", loadMorningBriefing);
            document.getElementById("afternoon-briefing-top").addEventListener("click", loadAfternoonBriefing);
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


def _recount_board(board_state):
    if not isinstance(board_state, dict):
        return board_state
    jobs = board_state.get("jobs", [])
    if not isinstance(jobs, list):
        return board_state
    lane_counts = {"P1": 0, "P2": 0, "P3": 0, "P4": 0}
    waiting_counts = {"Mitch": 0, "Drew": 0, "Preston": 0, "External Hold": 0, "Needs Review": 0}
    open_alert_count = 0
    for job in jobs:
        if not isinstance(job, dict):
            continue
        lane = str(job.get("priority_lane", "P3"))
        waiting = str(job.get("waiting_on", "Needs Review"))
        lane_counts[lane] = lane_counts.get(lane, 0) + 1
        waiting_counts[waiting] = waiting_counts.get(waiting, 0) + 1
        alerts = job.get("alerts", [])
        if isinstance(alerts, list):
            open_alert_count += len(alerts)
    board_state["lane_counts"] = lane_counts
    board_state["waiting_on_counts"] = waiting_counts
    board_state["open_alert_count"] = open_alert_count
    return board_state


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


def _latest_override_state():
    state = {}
    for row in _read_jsonl(BOARD_OVERRIDE_LOG_PATH):
        ro = str(row.get("ro", "")).strip()
        if not ro:
            continue
        state[ro] = row
    return state


def _apply_override_state(board_state):
    if not isinstance(board_state, dict):
        return board_state
    override_state = _latest_override_state()
    jobs = board_state.get("jobs", [])
    if not isinstance(jobs, list):
        board_state["override_state"] = override_state
        return board_state

    risk_by_lane = {"P1": "CRITICAL", "P2": "YELLOW", "P3": "YELLOW", "P4": "NORMAL"}
    for job in jobs:
        if not isinstance(job, dict):
            continue
        ro = str(job.get("ro", "")).strip()
        override = override_state.get(ro)
        if not override:
            continue
        if override.get("priority_lane"):
            job["priority_lane"] = override["priority_lane"]
            job["risk_level"] = risk_by_lane.get(job["priority_lane"], job.get("risk_level", "NORMAL"))
            if job["priority_lane"] == "P4":
                job["incoming_soon"] = None
        if override.get("waiting_on"):
            job["waiting_on"] = override["waiting_on"]
        if override.get("technician"):
            job["technician"] = override["technician"]
            technicians = [part.strip() for part in str(override["technician"]).split(",") if part.strip()]
            if technicians:
                job["technicians"] = technicians
        if override.get("summary"):
            job["summary"] = override["summary"]
        if override.get("note"):
            reasons = job.get("board_reasons", [])
            if not isinstance(reasons, list):
                reasons = []
            reasons.append("Local override applied: " + str(override["note"]))
            job["board_reasons"] = reasons
        job["override_state"] = override
    board_state["override_state"] = override_state
    return _recount_board(board_state)


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
            if code in {"missing_ro", "status_mapping_gap", "missing_tech_assignment", "missing_info", "missing_customer_concern", "missing_completed_dvi"} and ro_state.get("data_cleared"):
                continue
            filtered_alerts.append(alert)
        job["alerts"] = filtered_alerts
        if ro_state:
            job["action_state"] = ro_state

    board_state["action_state"] = action_state
    return _recount_board(board_state)


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
            return _apply_action_state(_apply_override_state(payload))
    except Exception:
        pass

    return _apply_action_state(_apply_override_state({
        "source": "board_rules_v1",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": 0,
        "jobs": [],
        "lane_counts": {"P1": 0, "P2": 0, "P3": 0, "P4": 0},
        "waiting_on_counts": {"Mitch": 0, "Drew": 0, "Preston": 0, "External Hold": 0, "Needs Review": 0},
        "open_alert_count": 0,
        "message": "No board_state.json found. Run python scripts/build_board_state.py first.",
    }))


def _find_job(ro):
    board_state = _load_board_state()
    jobs = board_state.get("jobs", []) if isinstance(board_state, dict) else []
    for job in jobs:
        if isinstance(job, dict) and str(job.get("ro", "")) == str(ro):
            return job
    return None


def _load_callie_insights(force=False):
    now = time.time()
    cached_payload = _CALLIE_INSIGHTS_CACHE.get("payload")
    expires_at = float(_CALLIE_INSIGHTS_CACHE.get("expires_at", 0.0) or 0.0)
    if not force and cached_payload is not None and now < expires_at:
        return cached_payload

    fallback = {
        "generated_at": datetime.now().isoformat(),
        "shop_summary": "Callie insights are loading. Run python callie_engine.py to refresh the deterministic intelligence layer.",
        "jobs": [],
        "conflicts": [],
        "metrics": {
            "job_count": 0,
            "critical_jobs": 0,
            "near_term_jobs": 0,
            "open_alert_count": 0,
            "conflict_count": 0,
        },
    }
    try:
        path = Path(CALLIE_INSIGHTS_PATH)
        if path.exists():
            with path.open(encoding="utf-8") as handle:
                payload = json.load(handle)
            _CALLIE_INSIGHTS_CACHE["payload"] = payload
            _CALLIE_INSIGHTS_CACHE["expires_at"] = now + CALLIE_INSIGHTS_TTL_SECONDS
            return payload
    except Exception:
        pass

    _CALLIE_INSIGHTS_CACHE["payload"] = fallback
    _CALLIE_INSIGHTS_CACHE["expires_at"] = now + 10
    return fallback


def _trim_text(value, limit=220):
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def _is_general_greeting(question):
    normalized = str(question or "").strip().lower()
    if not normalized:
        return False
    greetings = {
        "hello",
        "hi",
        "hey",
        "good morning",
        "good afternoon",
        "good evening",
        "status",
        "help",
    }
    return normalized in greetings or len(normalized) < 8


def _has_ro_like_token(question):
    text = str(question or "")
    digits = []
    for char in text:
        if char.isdigit():
            digits.append(char)
            if len(digits) >= 4:
                return True
        else:
            digits = []
    return False


def _is_short_general_chat(question):
    normalized = str(question or "").strip()
    if not normalized:
        return False
    return len(normalized) < 10 and not _has_ro_like_token(normalized)


def _extract_ro_from_question(question):
    text = str(question or "")
    for match in re.findall(r"\b(\d{4,6})\b", text):
        if _find_job(match):
            return str(match)
    return ""


def _build_callie_prompt(question, job=None, mode="general"):
    insights = _load_callie_insights()
    prompt_lines = [
        "You are Callie — calm, practical, supportive air-traffic-control copilot for Callahan Auto & Diesel.",
        f"Shop pulse: {_trim_text(insights.get('shop_summary', 'Busy shop'), 180)}",
        f"Interaction mode: {mode}",
    ]
    if job and isinstance(job, dict):
        source = job.get("source_evidence", {}) if isinstance(job.get("source_evidence"), dict) else {}
        alerts = [
            str(alert.get("message", "")).strip()
            for alert in job.get("alerts", [])
            if isinstance(alert, dict) and str(alert.get("message", "")).strip()
        ]
        prompt_lines.extend(
            [
                f"RO: {job.get('ro', 'Unknown RO')}",
                f"Customer: {job.get('customer', '')}",
                f"Vehicle: {job.get('vehicle', '')}",
                f"Board lane: {job.get('priority_lane', '')}",
                f"Waiting on: {job.get('waiting_on', '')}",
                f"Workflow status: {job.get('workflow_status', '')}",
                f"Technician: {job.get('technician', '')}",
                f"Next action: {_trim_text(job.get('next_action', ''), 180)}",
                f"Summary: {_trim_text(job.get('summary', ''), 180)}",
                f"Source WO status: {source.get('source_work_order_status', 'unknown')}",
                f"Source DVI status: {source.get('source_dvi_status', 'unknown')}",
            ]
        )
        if alerts:
            prompt_lines.append("Current alerts: " + " | ".join(_trim_text(alert, 140) for alert in alerts[:3]))
        reasons = job.get("board_reasons", []) if isinstance(job.get("board_reasons"), list) else []
        if reasons:
            prompt_lines.append("Board reasons: " + " | ".join(_trim_text(reason, 140) for reason in reasons[:3]))
        concern = job.get("reason_vehicle_is_here", []) if isinstance(job.get("reason_vehicle_is_here"), list) else []
        if concern:
            prompt_lines.append("Customer concern evidence: " + " | ".join(_trim_text(line, 140) for line in concern[:2]))
    prompt_lines.append(f"User question: {_trim_text(question, 240)}")
    prompt_lines.append(
        "Respond in short, actionable, coaching sentences. Tie back to evidence when possible. "
        "If the user is trying to change something that conflicts with AutoFlow evidence, say so clearly and tell them to fix AutoFlow first."
    )
    return "\n".join(prompt_lines)


def _call_ollama(question, job=None, mode="general"):
    prompt = _build_callie_prompt(question, job=job, mode=mode)
    fallback_answer = _hermes_answer(question, job=job, mode=mode)
    if not shutil.which("ollama"):
        return {
            "response": fallback_answer + " Live model note: Ollama was not available on this machine, so Callie answered from the board evidence layer.",
            "confidence": 45,
            "model": CALLIE_MODEL,
        }

    try:
        result = subprocess.run(
            ["ollama", "run", CALLIE_MODEL, prompt],
            capture_output=True,
            text=True,
            timeout=CALLIE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return {
            "response": fallback_answer + f" Live model note: the local model took longer than {CALLIE_TIMEOUT_SECONDS} seconds, so Callie fell back to the fast board evidence layer.",
            "confidence": 50,
            "model": CALLIE_MODEL,
        }
    except Exception as exc:
        return {
            "response": fallback_answer + f" Live model note: Callie had trouble connecting to the local model ({str(exc)[:160]}), so this answer came from the fast board evidence layer.",
            "confidence": 45,
            "model": CALLIE_MODEL,
        }

    answer = (result.stdout or "").strip()
    if not answer and result.stderr:
        answer = f"Callie could not produce a live reply: {result.stderr.strip()[:220]}"
    if not answer:
        answer = "Callie is connected, but it returned an empty reply. Try asking with the RO, blocker, or expected next move."

    return {
        "response": answer[:1500],
        "confidence": 75 if result.returncode == 0 else 45,
        "model": CALLIE_MODEL,
    }


def _hermes_answer(question, job=None, mode="general"):
    question = str(question or "").strip()
    if not question and not job:
        return "Hermes needs a little more context. Ask what is blocked, what the next move is, or what customer expectation should be protected."

    if job:
        ro = job.get("ro", "Unknown RO")
        waiting_on = job.get("waiting_on", "Needs Review")
        next_action = job.get("next_action", "Keep momentum moving.")
        alerts = [alert.get("message", "") for alert in job.get("alerts", []) if isinstance(alert, dict)]
        reasons = job.get("board_reasons", []) if isinstance(job, dict) else []
        source_work_order_status = ((job.get("source_evidence") or {}).get("source_work_order_status", "unknown")) if isinstance(job, dict) else "unknown"
        source_dvi_status = ((job.get("source_evidence") or {}).get("source_dvi_status", "unknown")) if isinstance(job, dict) else "unknown"
        lead = f"RO {ro} is currently waiting on {waiting_on}. {next_action}"
        if mode == "communication":
            return lead + " For customer contact, confirm the latest expectation, document the callback window, and keep trust ahead of the surprise."
        if mode == "productivity":
            return lead + " On the floor, verify who is actively on it, whether labor is clocked, and what single blocker is keeping it from moving."
        if mode == "data":
            return lead + f" AutoFlow evidence currently shows WO status '{source_work_order_status}' and DVI status '{source_dvi_status}'. Tighten the board evidence by fixing the RO linkage, status mapping, or ownership gap so the coaching becomes more precise."
        if mode == "missing":
            return lead + " The fastest win is to fill the missing operating info first: technician assignment, clearer concern detail, or a confirmed RO trail."
        if question:
            detail = " ".join(reasons[:2]) if reasons else "I can see the board is still missing some reliable evidence."
            return lead + " " + detail + " If your correction conflicts with AutoFlow, fix AutoFlow first, then refresh the board so the source truth and the board stop fighting each other."
        if alerts:
            return lead + " Current helper alerts: " + " ".join(alerts[:2])
        return lead

    return "Callie logged the board question. The next best move is to capture the blocker, the owner, and the promised follow-up so the system can coach the handoff instead of guessing."


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
    current_job = _find_job(str(payload.get("ro", "")).strip())
    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ro": str(payload.get("ro", "")).strip(),
        "action_type": str(payload.get("action_type", "details")).strip() or "details",
        "note": str(payload.get("note", "")).strip(),
        "source": str(payload.get("source", "dashboard")).strip() or "dashboard",
    }
    _append_jsonl(BOARD_ACTION_LOG_PATH, entry)

    override_entry = {
        "timestamp": entry["timestamp"],
        "ro": entry["ro"],
        "priority_lane": str(payload.get("override_priority_lane", "")).strip(),
        "waiting_on": str(payload.get("override_waiting_on", "")).strip(),
        "technician": str(payload.get("override_technician", "")).strip(),
        "summary": str(payload.get("override_summary", "")).strip(),
        "note": entry["note"],
        "source": entry["source"],
    }
    if any(override_entry[key] for key in ("priority_lane", "waiting_on", "technician", "summary")):
        _append_jsonl(BOARD_OVERRIDE_LOG_PATH, override_entry)

    message_map = {
        "communication": "Customer update saved. Keep the promise window visible and the next callback clear.",
        "productivity": "Productivity note saved. Advisors can now coach the next floor follow-up with context.",
        "data": "Board issue saved. This gives Hermes a cleaner trail to improve the board logic.",
        "missing": "Missing-info note saved. The board can now coach the next cleanup step with more context.",
        "details": "Support note saved.",
    }
    if any(override_entry[key] for key in ("priority_lane", "waiting_on", "technician", "summary")):
        conflict_lines = []
        if current_job and isinstance(current_job, dict):
            source = current_job.get("source_evidence", {}) if isinstance(current_job.get("source_evidence", {}), dict) else {}
            source_wo = str(source.get("source_work_order_status", "unknown"))
            source_dvi = str(source.get("source_dvi_status", "unknown"))
            if override_entry["priority_lane"] and current_job.get("priority_lane") != override_entry["priority_lane"]:
                conflict_lines.append(f"Board currently chose {current_job.get('priority_lane')} from AutoFlow evidence.")
            if override_entry["technician"] and str(current_job.get("technician", "")).strip().lower() != override_entry["technician"].strip().lower():
                conflict_lines.append(f"Board currently sees technician '{current_job.get('technician', 'Unassigned')}'.")
            if source_wo not in {"", "unknown"} or source_dvi not in {"", "unknown"}:
                conflict_lines.append(f"AutoFlow source status is WO '{source_wo}' / DVI '{source_dvi}'.")
        message = "Local board correction saved. The board will now show your override and keep the reason on file."
        warning = ""
        if conflict_lines:
            warning = "Hold up: your correction conflicts with live AutoFlow evidence. " + " ".join(conflict_lines) + " Fix the ticket in AutoFlow too, then refresh the board so the source truth and the board line up."
        return jsonify({"status": "received", "message": message, "warning": warning}), 200
    return jsonify({"status": "received", "message": message_map.get(entry["action_type"], "Support note saved.")}), 200


@app.route("/api/hermes-feedback", methods=["POST"])
def api_hermes_feedback():
    payload = request.get_json(silent=True) or {}
    ro = str(payload.get("ro", "")).strip()
    mode = str(payload.get("mode", "general")).strip() or "general"
    question = str(payload.get("question", "")).strip()
    job = _find_job(ro) if ro else None
    live_reply = _call_ollama(question, job=job, mode=mode)
    answer = live_reply.get("response") or _hermes_answer(question, job=job, mode=mode)
    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ro": ro,
        "mode": mode,
        "question": question,
        "answer": answer,
        "source": str(payload.get("source", "dashboard")).strip() or "dashboard",
    }
    _append_jsonl(HERMES_LOG_PATH, entry)
    return jsonify({
        "status": "received",
        "answer": answer,
        "response": answer,
        "confidence": live_reply.get("confidence", 40),
        "timestamp": entry["timestamp"],
    }), 200


@app.route("/api/callie/insights")
def api_callie_insights():
    insights = _load_callie_insights()
    conflicts = insights.get("conflicts", []) if isinstance(insights.get("conflicts"), list) else []
    summary = insights.get("shop_summary", "Callie insights unavailable.")
    return jsonify({
        "summary": summary,
        "shop_summary": summary,
        "timestamp": insights.get("generated_at", datetime.now().isoformat()),
        "generated_at": insights.get("generated_at", datetime.now().isoformat()),
        "conflicts": conflicts[:8],
        "conflict_count": len(conflicts),
        "metrics": insights.get("metrics", {}),
    }), 200


@app.route("/api/callie/ask", methods=["POST"])
def api_callie_ask():
    payload = request.get_json(silent=True) or {}
    raw_question = str(payload.get("question", "")).strip()
    question = raw_question
    ro = str(payload.get("ro_number", payload.get("ro", ""))).strip()
    mode = str(payload.get("mode", "general")).strip() or "general"
    is_greeting = _is_general_greeting(question)
    is_short_general = _is_short_general_chat(question)
    inferred_ro = ""

    if is_greeting or is_short_general:
        ro = ""
    elif not ro:
        inferred_ro = _extract_ro_from_question(question)
        if inferred_ro:
            ro = inferred_ro

    is_board_level = not ro

    if is_greeting or is_short_general:
        reply = {
            "response": "Hello! I'm Callie, your shop's air-traffic-control copilot. How can I help today? You can ask me about a specific job, the overall board, priorities, or what needs attention next.",
            "confidence": 95,
            "model": "fast-greeting",
        }
    else:
        job = _find_job(ro) if ro else None
        live_reply = _call_ollama(question, job=job, mode=mode)
        reply = live_reply
        if is_board_level and not reply.get("response", "").strip():
            reply["response"] = _hermes_answer(question, job=None, mode="general")

    entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "ro": ro,
        "mode": mode,
        "question": question,
        "answer": reply.get("response", ""),
        "source": str(payload.get("source", "dashboard")).strip() or "dashboard",
        "model": reply.get("model", CALLIE_MODEL),
    }
    _append_jsonl(HERMES_LOG_PATH, entry)
    return jsonify({
        "status": "received",
        "response": reply.get("response", ""),
        "confidence": reply.get("confidence", 40),
        "timestamp": datetime.now().isoformat(),
        "model": reply.get("model", CALLIE_MODEL),
    }), 200


@app.route("/api/hermes-summary")
def api_hermes_summary():
    try:
        insights = _load_callie_insights()
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
        dvi_quality_jobs = [
            job for job in jobs
            if isinstance(job, dict) and any(alert.get("code") == "missing_completed_dvi" for alert in job.get("alerts", []))
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
        if dvi_quality_jobs:
            recommendations.append(
                f"DVI quality watch: {len(dvi_quality_jobs)} job(s) still need clearer completed inspection evidence before the repair story is fully trustworthy."
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

        summary_text = "\n".join(recommendations)
        if insights.get("shop_summary"):
            summary_text = str(insights.get("shop_summary")).strip() + "\n" + summary_text

        conflicts = insights.get("conflicts", []) if isinstance(insights.get("conflicts"), list) else []
        return jsonify(
            {
                "source": "board_rules_v1",
                "status": "ok",
                "summary": summary_text,
                "shop_summary": insights.get("shop_summary", ""),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "conflicts": conflicts[:8],
                "conflict_count": len(conflicts),
            }
        )
    except Exception:
        return jsonify({"summary": "Callie temporarily unavailable.", "timestamp": "--"})


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


@app.route("/bay-performance")
def bay_performance():
    board_state = _load_board_state()
    jobs = board_state.get("jobs", []) if isinstance(board_state, dict) else []
    p1 = len([job for job in jobs if isinstance(job, dict) and job.get("priority_lane") == "P1"])
    communication_needs = len([
        job for job in jobs
        if isinstance(job, dict) and any(alert.get("code") == "customer_follow_up_due" for alert in job.get("alerts", []))
    ])
    productivity_needs = len([
        job for job in jobs
        if isinstance(job, dict) and any(alert.get("code") == "verify_tech_clock_in" for alert in job.get("alerts", []))
    ])
    data_needs = len([
        job for job in jobs
        if isinstance(job, dict) and any(alert.get("code") in {"missing_ro", "status_mapping_gap", "missing_tech_assignment", "missing_info", "missing_customer_concern", "missing_completed_dvi"} for alert in job.get("alerts", []))
    ])
    total = max(len(jobs), 1)
    support_score = round(((total - communication_needs) + (total - productivity_needs) + (total - data_needs)) / (total * 3) * 100)
    front_score = round((((total - communication_needs) + (total - len([job for job in jobs if isinstance(job, dict) and job.get("priority_lane") == "P2"]))) / (total * 2)) * 100)
    back_score = round((((total - productivity_needs) + (total - len([job for job in jobs if isinstance(job, dict) and any(alert.get("code") == "missing_completed_dvi" for alert in job.get("alerts", []))]))) / (total * 2)) * 100)
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bay Performance Board</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-zinc-950 text-zinc-100 min-h-screen">
    <div class="max-w-7xl mx-auto px-6 py-8">
        <h1 class="text-5xl font-black tracking-wide">Bay Performance Board</h1>
        <p class="mt-2 text-zinc-400">Live support view for technicians and shop momentum.</p>
        <div class="mt-8 grid grid-cols-1 gap-6 md:grid-cols-5">
            <div class="rounded-3xl border border-emerald-700 bg-emerald-950/30 p-6">
                <div class="text-sm uppercase tracking-wide text-emerald-300">Shop Support Score</div>
                <div class="mt-3 text-6xl font-black text-emerald-200">{support_score}%</div>
            </div>
            <div class="rounded-3xl border border-cyan-700 bg-cyan-950/30 p-6">
                <div class="text-sm uppercase tracking-wide text-cyan-300">Front Of House</div>
                <div class="mt-3 text-6xl font-black text-cyan-200">{front_score}%</div>
            </div>
            <div class="rounded-3xl border border-violet-700 bg-violet-950/30 p-6">
                <div class="text-sm uppercase tracking-wide text-violet-300">Back Of House</div>
                <div class="mt-3 text-6xl font-black text-violet-200">{back_score}%</div>
            </div>
            <div class="rounded-3xl border border-red-700 bg-red-950/30 p-6">
                <div class="text-sm uppercase tracking-wide text-red-300">P1 Jobs</div>
                <div class="mt-3 text-6xl font-black text-red-200">{p1}</div>
            </div>
            <div class="rounded-3xl border border-blue-700 bg-blue-950/30 p-6">
                <div class="text-sm uppercase tracking-wide text-blue-300">Productivity / Data Needs</div>
                <div class="mt-3 text-6xl font-black text-blue-200">{productivity_needs + data_needs}</div>
            </div>
        </div>
        <div class="mt-8 rounded-3xl border border-zinc-800 bg-zinc-900 p-6">
            <h2 class="text-2xl font-bold">Live Message</h2>
            <p class="mt-4 text-2xl leading-relaxed text-zinc-200">Keep the bays moving, keep labor clocked, and help the front stay ahead of the next customer promise.</p>
        </div>
        <div class="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-2">
            <div class="rounded-3xl border border-zinc-800 bg-zinc-900 p-6">
                <h2 class="text-2xl font-bold">What The Scores Mean</h2>
                <div class="mt-4 space-y-3 text-sm text-zinc-300">
                    <div><span class="font-semibold text-zinc-100">Shop Support Score:</span> overall health across communication, productivity, and clean data signals.</div>
                    <div><span class="font-semibold text-zinc-100">Front Of House:</span> customer updates staying ahead of the surprise and advisor-side action gaps staying under control.</div>
                    <div><span class="font-semibold text-zinc-100">Back Of House:</span> tech clock-in visibility plus usable inspection/DVI evidence supporting production flow.</div>
                    <div><span class="font-semibold text-zinc-100">P1 Jobs:</span> true pressure items that need direct attention now.</div>
                    <div><span class="font-semibold text-zinc-100">Productivity / Data Needs:</span> combined count of jobs where the board still needs clearer floor evidence or cleaner source data.</div>
                </div>
            </div>
            <div class="rounded-3xl border border-zinc-800 bg-zinc-900 p-6">
                <h2 class="text-2xl font-bold">How To Bring Them Up</h2>
                <div class="mt-4 space-y-3 text-sm text-zinc-300">
                    <div><span class="font-semibold text-zinc-100">Raise Front Of House:</span> log customer updates sooner, tighten callbacks, and clear waiting-approval drift early.</div>
                    <div><span class="font-semibold text-zinc-100">Raise Back Of House:</span> keep labor clocked, finish DVI work cleanly, and tighten who is actively on each job.</div>
                    <div><span class="font-semibold text-zinc-100">Raise Shop Support:</span> reduce flashing board helpers by correcting the real blocker instead of working around it.</div>
                    <div><span class="font-semibold text-zinc-100">Lower P1 count:</span> land the plane faster on ready jobs and remove unknowns before they turn into customer-trust issues.</div>
                    <div><span class="font-semibold text-zinc-100">Lower Productivity / Data Needs:</span> fix missing tech assignment, missing concern detail, missing DVI completion, and bad status usage.</div>
                </div>
            </div>
        </div>
    </div>
</body>
</html>"""
    return Response(html, mimetype="text/html")


if __name__ == "__main__":
    print("🚀 Starting Country Club Advisor Command Board on 127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True, use_reloader=False)
