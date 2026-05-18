import json
import os
import sys
from datetime import datetime

from flask import Flask, Response, jsonify

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(CURRENT_DIR)
SHOP_STATE_PATH = os.path.join(REPO_ROOT, "state", "shop_state.json")
BOARD_STATE_PATH = os.path.join(REPO_ROOT, "state", "board_state.json")

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
        .role-tab.active { background: #18181b; color: #fafafa; border-color: #3f3f46; }
        .pulse-card { animation: pulseBorder 1.6s infinite; }
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
            <button class="role-tab active rounded-2xl border border-zinc-700 bg-zinc-900 px-4 py-2 text-sm font-semibold" data-role="board">Board</button>
            <button class="role-tab rounded-2xl border border-zinc-800 bg-zinc-950 px-4 py-2 text-sm font-semibold text-zinc-300" data-role="mitch">Mitch</button>
            <button class="role-tab rounded-2xl border border-zinc-800 bg-zinc-950 px-4 py-2 text-sm font-semibold text-zinc-300" data-role="drew">Drew</button>
            <button class="role-tab rounded-2xl border border-zinc-800 bg-zinc-950 px-4 py-2 text-sm font-semibold text-zinc-300" data-role="preston">Preston</button>
        </div>

        <div class="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-12">
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
                    <h2 class="text-xl font-bold">Hermes Intelligence</h2>
                    <div id="hermes-summary" class="mt-4 rounded-2xl bg-zinc-950 p-4 text-sm leading-relaxed text-zinc-200 min-h-[180px]">Loading Hermes recommendations...</div>
                    <div id="hermes-updated-at" class="mt-3 text-xs text-zinc-500"></div>
                </div>
            </section>
        </div>
    </div>

    <script>
        let currentRole = "board";
        let latestBoardState = null;

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

        function roleMatches(job) {
            if (currentRole === "board") return true;
            const waitingOn = String(job.waiting_on || "").toLowerCase();
            if (currentRole === "mitch") return waitingOn === "mitch";
            if (currentRole === "drew") return waitingOn === "drew";
            if (currentRole === "preston") return waitingOn === "preston";
            return true;
        }

        function formatAlert(job) {
            const alerts = Array.isArray(job.alerts) ? job.alerts : [];
            if (!alerts.length) return "";
            const first = alerts[0];
            return '<div class="mt-3 rounded-xl bg-zinc-950 px-3 py-2 text-xs text-zinc-300 ' +
                'alert-' + escapeHtml(first.severity || "info") + '">' +
                escapeHtml(first.message || "Attention needed.") +
            '</div>';
        }

        function renderJobCard(job) {
            const pulse = (job.risk_level === "CRITICAL" || job.risk_level === "RED" || (job.alerts || []).length > 0) ? " pulse-card" : "";
            const incoming = job.incoming_soon && job.incoming_soon.active
                ? '<div class="mt-3 rounded-xl bg-emerald-500/10 px-3 py-2 text-xs text-emerald-200">Incoming soon: ' +
                    escapeHtml(job.incoming_soon.next_stage || job.incoming_soon.reason || "Next handoff approaching.") +
                  '</div>'
                : "";

            return (
                '<article class="job-card rounded-2xl p-4' + pulse + '">' +
                    '<div class="flex items-start justify-between gap-3">' +
                        '<div>' +
                            '<div class="text-lg font-black">' + escapeHtml(job.ro || "Unknown RO") + '</div>' +
                            '<div class="text-sm font-semibold text-zinc-200">' + escapeHtml(job.customer || "Unknown Customer") + '</div>' +
                            '<div class="text-xs text-zinc-400">' + escapeHtml(job.vehicle || "Unknown Vehicle") + '</div>' +
                        '</div>' +
                        '<div class="space-y-1 text-right">' +
                            '<div class="rounded-full pill px-2 py-1 text-[11px] font-bold text-zinc-100">' + escapeHtml(job.risk_level || "NORMAL") + '</div>' +
                            '<div class="text-[11px] text-zinc-400">Waiting on ' + escapeHtml(job.waiting_on || "Needs Review") + '</div>' +
                        '</div>' +
                    '</div>' +
                    '<div class="mt-3 text-sm text-zinc-300"><span class="font-semibold text-zinc-100">Status:</span> ' + escapeHtml(job.workflow_status || "unknown") + '</div>' +
                    '<div class="mt-2 text-sm text-zinc-300"><span class="font-semibold text-zinc-100">Next move:</span> ' + escapeHtml(job.next_action || "Keep momentum moving.") + '</div>' +
                    formatAlert(job) +
                    incoming +
                '</article>'
            );
        }

        function renderLaneSection(title, jobs, emptyText) {
            if (!jobs.length) {
                return '<div class="rounded-2xl border border-dashed border-white/10 bg-zinc-950/60 p-4 text-sm text-zinc-400">' + escapeHtml(emptyText) + '</div>';
            }
            return (
                '<div class="space-y-3">' +
                    '<div class="text-sm font-semibold uppercase tracking-wide text-white/90">' + escapeHtml(title) + '</div>' +
                    jobs.map(renderJobCard).join("") +
                '</div>'
            );
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
                const incomingSoon = laneJobs.filter((job) => job.incoming_soon && job.incoming_soon.active);
                const remaining = laneJobs.filter((job) => !actionNow.includes(job) && !incomingSoon.includes(job));

                return (
                    '<section class="lane-card rounded-3xl p-4 ' + meta.cls + '">' +
                        '<div class="rounded-2xl bg-black/20 p-4">' +
                            '<div class="flex items-center justify-between gap-3">' +
                                '<div>' +
                                    '<div class="text-4xl font-black">' + escapeHtml(meta.title) + '</div>' +
                                    '<div class="text-sm uppercase tracking-wide text-zinc-200">' + escapeHtml(meta.subtitle) + '</div>' +
                                '</div>' +
                                '<div class="rounded-full bg-white/10 px-4 py-2 text-lg font-black text-white">' + laneJobs.length + '</div>' +
                            '</div>' +
                        '</div>' +
                        '<div class="mt-4 space-y-4">' +
                            renderLaneSection("Action Now", actionNow, "No immediate pressure items.") +
                            renderLaneSection("Incoming Soon", incomingSoon, "No incoming-soon items.") +
                            renderLaneSection("All Jobs", remaining, "This operational lane is currently calm.") +
                        '</div>' +
                    '</section>'
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
                '<div class="rounded-2xl bg-zinc-950 p-4 text-zinc-200"><span class="font-semibold">Visible jobs:</span> ' + jobs.length + '</div>' +
                '<div class="rounded-2xl bg-zinc-950 p-4 text-zinc-200"><span class="font-semibold">Open helper alerts:</span> ' + alerts.length + '</div>' +
                '<div class="rounded-2xl bg-zinc-950 p-4 text-zinc-200"><span class="font-semibold">Current ownership load:</span> ' + escapeHtml(ownerText || "No jobs visible.") + '</div>' +
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
                    '<div class="text-xs uppercase tracking-wide text-zinc-500">Next move ' + (index + 1) + '</div>' +
                    '<div class="mt-1 text-lg font-black text-zinc-100">' + escapeHtml(job.ro || "Unknown RO") + '</div>' +
                    '<div class="text-sm font-semibold text-zinc-300">' + escapeHtml(job.customer || "Unknown Customer") + '</div>' +
                    '<div class="mt-2 text-sm text-zinc-200">' + escapeHtml(job.next_action || "Keep momentum moving.") + '</div>' +
                '</div>'
            )).join("");
        }

        function renderBoardState(boardState) {
            latestBoardState = boardState;
            document.getElementById("board-updated-at").textContent = boardState.generated_at || "__TIMESTAMP__";
            renderLanes(boardState);
            renderSnapshot(boardState);
            renderNextActions(boardState);
        }

        function renderHermesSummary(payload) {
            const target = document.getElementById("hermes-summary");
            if (!target) return;
            const lines = String(payload.summary || "No summary available.")
                .split(/\\n+/)
                .map((line) => line.trim())
                .filter(Boolean);

            target.innerHTML = lines.map((line) => (
                '<div class="mb-3 rounded-2xl bg-zinc-900 px-4 py-3 text-sm text-zinc-100">' + escapeHtml(line) + '</div>'
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

        function setRole(role) {
            currentRole = role;
            document.querySelectorAll(".role-tab").forEach((button) => {
                button.classList.toggle("active", button.dataset.role === role);
            });
            if (latestBoardState) {
                renderBoardState(latestBoardState);
            }
        }

        document.addEventListener("DOMContentLoaded", () => {
            document.getElementById("refresh-jobs").addEventListener("click", refreshBoard);
            document.querySelectorAll(".role-tab").forEach((button) => {
                button.addEventListener("click", () => setRole(button.dataset.role || "board"));
            });
            refreshBoard();
            window.setInterval(refreshBoard, 30000);
        });
    </script>
</body>
</html>"""


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
            return payload
    except Exception:
        pass

    return {
        "source": "board_rules_v1",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": 0,
        "jobs": [],
        "lane_counts": {"P1": 0, "P2": 0, "P3": 0, "P4": 0},
        "waiting_on_counts": {"Mitch": 0, "Drew": 0, "Preston": 0, "External Hold": 0, "Needs Review": 0},
        "open_alert_count": 0,
        "message": "No board_state.json found. Run python scripts/build_board_state.py first.",
    }


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


@app.route("/api/hermes-summary")
def api_hermes_summary():
    try:
        board_state = _load_board_state()
        jobs = board_state.get("jobs", []) if isinstance(board_state, dict) else []
        p1_jobs = [job for job in jobs if isinstance(job, dict) and job.get("priority_lane") == "P1"]
        p2_jobs = [job for job in jobs if isinstance(job, dict) and job.get("priority_lane") == "P2"]
        missing_ro_jobs = [
            job
            for job in jobs
            if isinstance(job, dict) and any(alert.get("code") == "missing_ro" for alert in job.get("alerts", []))
        ]
        clock_in_jobs = [
            job
            for job in jobs
            if isinstance(job, dict)
            and any(alert.get("code") == "verify_tech_clock_in" for alert in job.get("alerts", []))
        ]
        needs_review_jobs = [job for job in jobs if isinstance(job, dict) and job.get("waiting_on") == "Needs Review"]

        recommendations = []
        if p1_jobs:
            top = p1_jobs[:3]
            recommendations.append(
                "Best next actions: "
                + "; ".join(
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


if __name__ == "__main__":
    print("🚀 Starting Country Club Advisor Command Board on 127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True, use_reloader=False)
