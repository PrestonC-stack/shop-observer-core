import json
import os
import sys
from datetime import datetime

from flask import Flask, Response, jsonify

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(CURRENT_DIR)
ACTIVE_ROS_STATE_PATH = os.path.join(REPO_ROOT, "state", "active_ros.json")
SHOP_STATE_PATH = os.path.join(REPO_ROOT, "state", "shop_state.json")
BOARD_STATE_PATH = os.path.join(REPO_ROOT, "state", "board_state.json")

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

app = Flask(__name__)

# ====================== HERMES SYSTEM PROMPT ======================
HERMES_SYSTEM_PROMPT = """
You are Hermes, Preston Callahan's operational intelligence layer for Callahan Auto & Diesel.

Core Principles:
- Momentum is everything. Never let jobs sit without a clear owner or next step.
- Safety and liability come first.
- Advisors must stay 3–5 steps ahead of technicians.
- If the customer calls first, we already lost.
- Technicians should not wait — move them to productive work immediately.
- Near-complete jobs are high priority.
- Document everything.

Priority Rules:
- P1: Near completion, promise time at risk, safety issue, money waiting, bay blocked.
- P2: Missing information, no clear next step, DVI incomplete.
- P3: Actively progressing under control.
- P4: Legitimate external hold with customer updated.

When recommending:
- Best 2-3 jobs to attack next and why
- Bottlenecks and how to clear them
- Who owns the next move
- Customer communication needed
- When to escalate to Preston

Tone: Direct, practical, confident. Speak like Preston.
"""

# ====================== WALLBOARD HTML ======================
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Country Club Advisor Command Board</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { font-family: system-ui, -apple-system, sans-serif; }
        .p1 { border-left: 6px solid #ef4444; }
        .p2 { border-left: 6px solid #f59e0b; }
        .p3 { border-left: 6px solid #3b82f6; }
        .p4 { border-left: 6px solid #6b7280; }
    </style>
</head>
<body class="bg-zinc-950 text-zinc-100 min-h-screen">
    <div class="max-w-screen-2xl mx-auto p-6">
        <div class="flex justify-between items-center mb-8">
            <div>
                <h1 class="text-4xl font-bold">Country Club Advisor Command Board</h1>
                <p class="text-zinc-400">Last Updated: __TIMESTAMP__</p>
            </div>
            <div class="flex items-center gap-3">
                <button id="refresh-jobs" class="px-3 py-1 rounded-full text-sm font-medium bg-zinc-800 text-zinc-200 hover:bg-zinc-700" type="button">Refresh Jobs</button>
                <span class="px-3 py-1 bg-green-500/20 text-green-400 rounded-full text-sm font-medium">● LIVE</span>
            </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
            <!-- P1–P4 Columns -->
            <div class="lg:col-span-7 space-y-6">
                <h2 class="text-2xl font-semibold mb-4">Jobs by Priority</h2>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div class="bg-zinc-900 rounded-xl p-5 p1">
                        <h3 class="text-red-400 font-bold text-lg mb-3">🔴 P1 - Critical</h3>
                        <div id="p1-jobs" class="space-y-3"></div>
                    </div>
                    <div class="bg-zinc-900 rounded-xl p-5 p2">
                        <h3 class="text-amber-400 font-bold text-lg mb-3">🟠 P2 - High</h3>
                        <div id="p2-jobs" class="space-y-3"></div>
                    </div>
                    <div class="bg-zinc-900 rounded-xl p-5 p3">
                        <h3 class="text-blue-400 font-bold text-lg mb-3">🔵 P3 - Medium</h3>
                        <div id="p3-jobs" class="space-y-3"></div>
                    </div>
                    <div class="bg-zinc-900 rounded-xl p-5 p4">
                        <h3 class="text-zinc-400 font-bold text-lg mb-3">⚪ P4 - Low</h3>
                        <div id="p4-jobs" class="space-y-3"></div>
                    </div>
                </div>
            </div>

            <!-- Sidebar -->
            <div class="lg:col-span-5 space-y-6">
                <div class="bg-zinc-900 rounded-xl p-5">
                    <h3 class="font-bold text-lg mb-3">📋 Advisor Action Queue</h3>
                    <div id="advisor-queue" class="space-y-2 text-sm"></div>
                </div>
                <div class="bg-zinc-900 rounded-xl p-5">
                    <h3 class="font-bold text-lg mb-3">🔧 Technician Action Queue</h3>
                    <div id="technician-queue" class="space-y-2 text-sm"></div>
                </div>
                <div class="grid grid-cols-2 gap-4">
                    <div class="bg-zinc-900 rounded-xl p-5">
                        <h3 class="font-bold">Technician Load</h3>
                        <div id="tech-load" class="text-4xl font-bold text-green-400">--</div>
                    </div>
                    <div class="bg-zinc-900 rounded-xl p-5">
                        <h3 class="font-bold">Bay Utilization</h3>
                        <div id="bay-utilization" class="text-4xl font-bold text-blue-400">--</div>
                    </div>
                </div>
            </div>
        </div>

        <div class="mt-6 bg-zinc-900 rounded-xl p-5">
            <h3 class="font-bold text-lg mb-3">Hermes Intelligence</h3>
            <div id="hermes-summary" class="bg-zinc-800 rounded-lg p-4 text-sm leading-relaxed min-h-[140px]">
                Loading Hermes recommendations...
            </div>
            <div id="hermes-updated-at" class="mt-2 text-xs text-zinc-500"></div>
        </div>
    </div>

    <script>
        // Basic rendering functions (add your full JS if needed)
        function loadJobs() {
            fetch("/api/jobs", { cache: "no-store" })
                .then(r => r.json())
                .then(data => console.log("Jobs:", data))
                .catch(err => console.error(err));
        }

        function loadHermesSummary() {
            fetch("/api/hermes-summary", { cache: "no-store" })
                .then(r => r.json())
                .then(data => {
                    document.getElementById("hermes-summary").innerHTML = data.summary || "No summary available.";
                    document.getElementById("hermes-updated-at").textContent = "Last update: " + (data.timestamp || "--");
                })
                .catch(() => {
                    document.getElementById("hermes-summary").innerHTML = "Hermes temporarily unavailable.";
                });
        }

        document.addEventListener("DOMContentLoaded", () => {
            loadJobs();
            loadHermesSummary();
            setInterval(() => { loadJobs(); loadHermesSummary(); }, 30000);
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
        with open(SHOP_STATE_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload
    except Exception:
        return _fallback_jobs_payload("shop_state_not_found")


def _load_board_state():
    try:
        with open(BOARD_STATE_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
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
        payload = _load_jobs_from_autoflow()
        return jsonify(payload), 200
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
        missing_ro_jobs = [job for job in jobs if isinstance(job, dict) and any(alert.get("code") == "missing_ro" for alert in job.get("alerts", []))]
        clock_in_jobs = [job for job in jobs if isinstance(job, dict) and any(alert.get("code") == "verify_tech_clock_in" for alert in job.get("alerts", []))]

        recommendations = []
        if p1_jobs:
            top = p1_jobs[:3]
            recommendations.append(
                "Best next actions: " + "; ".join(
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
        if not recommendations:
            recommendations.append("Momentum looks steady right now. Keep advisors ahead of technicians and protect the next customer promise window.")

        return jsonify(
            {
                "source": "board_rules_v1",
                "status": "ok",
                "summary": "\n".join(recommendations),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    except Exception:
        return jsonify({"summary": "Hermes temporarily unavailable."})


if __name__ == "__main__":
    print("🚀 Starting Country Club Advisor Command Board on 127.0.0.1:5000")
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
        threaded=True,
        use_reloader=False,
    )
