import json
import os
import sys
from datetime import datetime
from flask import Flask, Response, jsonify

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(CURRENT_DIR)
ACTIVE_ROS_STATE_PATH = os.path.join(REPO_ROOT, "state", "active_ros.json")
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

app = Flask(__name__)
# Wallboard HTML Template (CSS braces safely escaped)
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Country Club Advisor Command Board</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body {{ font-family: system-ui, -apple-system, sans-serif; }}
        .p1 {{ border-left: 6px solid #ef4444; }}
        .p2 {{ border-left: 6px solid #f59e0b; }}
        .p3 {{ border-left: 6px solid #3b82f6; }}
        .p4 {{ border-left: 6px solid #6b7280; }}
    </style>
</head>
<body class="bg-zinc-950 text-zinc-100 min-h-screen">
    <div class="max-w-screen-2xl mx-auto p-6">
        <div class="flex justify-between items-center mb-8">
            <div>
                <h1 class="text-4xl font-bold">Country Club Advisor Command Board</h1>
                <p class="text-zinc-400">Last Updated: {timestamp}</p>
            </div>
            <div class="flex items-center gap-3">
                <button
                    id="refresh-jobs"
                    class="px-3 py-1 rounded-full text-sm font-medium bg-zinc-800 text-zinc-200 hover:bg-zinc-700"
                    type="button"
                >
                    Refresh Jobs
                </button>
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
                        <div id="p1-jobs" class="space-y-3">
                            <div class="bg-zinc-800 rounded-lg p-3 text-sm text-zinc-500">Loading jobs...</div>
                        </div>
                    </div>
                    <div class="bg-zinc-900 rounded-xl p-5 p2">
                        <h3 class="text-amber-400 font-bold text-lg mb-3">🟠 P2 - High</h3>
                        <div id="p2-jobs" class="space-y-3">
                            <div class="bg-zinc-800 rounded-lg p-3 text-sm text-zinc-500">Loading jobs...</div>
                        </div>
                    </div>
                    <div class="bg-zinc-900 rounded-xl p-5 p3">
                        <h3 class="text-blue-400 font-bold text-lg mb-3">🔵 P3 - Medium</h3>
                        <div id="p3-jobs" class="space-y-3">
                            <div class="bg-zinc-800 rounded-lg p-3 text-sm text-zinc-500">Loading jobs...</div>
                        </div>
                    </div>
                    <div class="bg-zinc-900 rounded-xl p-5 p4">
                        <h3 class="text-zinc-400 font-bold text-lg mb-3">⚪ P4 - Low</h3>
                        <div id="p4-jobs" class="space-y-3">
                            <div class="bg-zinc-800 rounded-lg p-3 text-sm text-zinc-500">Loading jobs...</div>
                        </div>
                    </div>
                </div>
            </div>
            <!-- Sidebar -->
            <div class="lg:col-span-5 space-y-6">
                <div class="bg-zinc-900 rounded-xl p-5">
                    <h3 class="font-bold text-lg mb-3">📋 Advisor Action Queue</h3>
                    <div id="advisor-queue" class="space-y-2 text-sm">
                        <div class="bg-zinc-800 p-3 rounded-lg text-zinc-500">Loading jobs...</div>
                    </div>
                </div>
                <div class="bg-zinc-900 rounded-xl p-5">
                    <h3 class="font-bold text-lg mb-3">🔧 Technician Action Queue</h3>
                    <div id="technician-queue" class="space-y-2 text-sm">
                        <div class="bg-zinc-800 p-3 rounded-lg text-zinc-500">Loading jobs...</div>
                    </div>
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
    </div>

    <script>
        function escapeHtml(value) {{
            return String(value)
                .replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;")
                .replace(/\"/g, "&quot;")
                .replace(/'/g, "&#39;");
        }}

        function renderEmpty(containerId, message) {{
            const container = document.getElementById(containerId);
            if (!container) return;
            container.innerHTML = '<div class="bg-zinc-800 rounded-lg p-3 text-sm text-zinc-500">' + escapeHtml(message) + '</div>';
        }}

        function renderJobCards(containerId, jobs, emptyMessage) {{
            const container = document.getElementById(containerId);
            if (!container) return;

            if (!jobs.length) {{
                renderEmpty(containerId, emptyMessage);
                return;
            }}

            container.innerHTML = jobs.map(function(job) {{
                const titleParts = [];
                if (job.vehicle) titleParts.push(job.vehicle);
                if (job.customer) titleParts.push(job.customer);
                if (!titleParts.length && job.ro) titleParts.push(job.ro);

                let subtitle = job.summary || job.workflow_status || "No summary";
                if (job.bay) {{
                    subtitle += " • Bay " + job.bay;
                }}

                return (
                    '<div class="bg-zinc-800 rounded-lg p-3 text-sm">' +
                        '<div class="font-medium">' + escapeHtml(titleParts.join(' • ') || 'Unassigned Job') + '</div>' +
                        '<div class="text-zinc-400">' + escapeHtml(subtitle) + '</div>' +
                    '</div>'
                );
            }}).join("");
        }}

        function renderQueue(containerId, jobs, emptyMessage, type) {{
            const container = document.getElementById(containerId);
            if (!container) return;

            if (!jobs.length) {{
                container.innerHTML = '<div class="bg-zinc-800 p-3 rounded-lg text-zinc-500">' + escapeHtml(emptyMessage) + '</div>';
                return;
            }}

            const colorMap = {{
                P1: "text-red-400",
                P2: "text-amber-400",
                P3: "text-blue-400",
                P4: "text-zinc-400"
            }};

            container.innerHTML = jobs.map(function(job) {{
                let text = "";
                if (type === "advisor") {{
                    text = "Review " + (job.customer || job.ro || "job");
                }} else {{
                    const bayPrefix = job.bay ? ("Bay " + job.bay + " - ") : "";
                    text = bayPrefix + (job.vehicle || job.ro || "Job");
                }}

                let suffix = ' <span class="' + (colorMap[job.priority] || "text-zinc-400") + '">(' + escapeHtml(job.priority || "P4") + ')</span>';
                if (type === "technician" && job.technician) {{
                    suffix = ' <span class="text-red-400">(Tech: ' + escapeHtml(job.technician) + ')</span>';
                }}

                return '<div class="bg-zinc-800 p-3 rounded-lg">' + escapeHtml(text) + suffix + '</div>';
            }}).join("");
        }}

        function renderMetrics(jobs) {{
            const techLoadEl = document.getElementById("tech-load");
            const bayUtilEl = document.getElementById("bay-utilization");

            const technicians = new Set();
            const bays = new Set();

            jobs.forEach(function(job) {{
                if (job.technician && job.technician !== "Unassigned") {{
                    technicians.add(job.technician);
                }}
                if (job.bay) {{
                    bays.add(job.bay);
                }}
            }});

            if (techLoadEl) {{
                techLoadEl.textContent = technicians.size ? String(technicians.size) : "0";
            }}

            if (bayUtilEl) {{
                bayUtilEl.textContent = bays.size ? String(bays.size) : "0";
            }}
        }}

        function renderJobs(jobs) {{
            const p1 = jobs.filter(function(job) {{ return job.priority === "P1"; }});
            const p2 = jobs.filter(function(job) {{ return job.priority === "P2"; }});
            const p3 = jobs.filter(function(job) {{ return job.priority === "P3"; }});
            const p4 = jobs.filter(function(job) {{ return job.priority === "P4"; }});

            renderJobCards("p1-jobs", p1, "No jobs in P1");
            renderJobCards("p2-jobs", p2, "No jobs in P2");
            renderJobCards("p3-jobs", p3, "No jobs in P3");
            renderJobCards("p4-jobs", p4, "No jobs in P4");

            renderQueue("advisor-queue", jobs.slice(0, 4), "No advisor actions right now", "advisor");
            renderQueue(
                "technician-queue",
                jobs.filter(function(job) {{ return job.technician && job.technician !== "Unassigned"; }}).slice(0, 4),
                "No technician actions right now",
                "technician"
            );

            renderMetrics(jobs);
        }}

        function renderLoadingState() {{
            renderEmpty("p1-jobs", "Loading jobs...");
            renderEmpty("p2-jobs", "Loading jobs...");
            renderEmpty("p3-jobs", "Loading jobs...");
            renderEmpty("p4-jobs", "Loading jobs...");
            renderEmpty("advisor-queue", "Loading jobs...");
            renderEmpty("technician-queue", "Loading jobs...");
            const techLoadEl = document.getElementById("tech-load");
            const bayUtilEl = document.getElementById("bay-utilization");
            if (techLoadEl) techLoadEl.textContent = "--";
            if (bayUtilEl) bayUtilEl.textContent = "--";
        }}

        function loadJobs() {{
            const refreshButton = document.getElementById("refresh-jobs");
            if (refreshButton) {{
                refreshButton.disabled = true;
                refreshButton.classList.add("opacity-60");
            }}

            renderLoadingState();

            fetch("/api/jobs", {{ cache: "no-store" }})
                .then(function(response) {{
                    if (!response.ok) {{
                        throw new Error("Request failed");
                    }}
                    return response.json();
                }})
                .then(function(payload) {{
                    const jobs = Array.isArray(payload.jobs) ? payload.jobs : [];
                    renderJobs(jobs);
                }})
                .catch(function() {{
                    renderJobCards("p1-jobs", [], "No jobs in P1");
                    renderJobCards("p2-jobs", [], "No jobs in P2");
                    renderJobCards("p3-jobs", [], "No jobs in P3");
                    renderJobCards("p4-jobs", [], "No jobs in P4");
                    renderQueue("advisor-queue", [], "No advisor actions right now", "advisor");
                    renderQueue("technician-queue", [], "No technician actions right now", "technician");
                    renderMetrics([]);
                }})
                .finally(function() {{
                    if (refreshButton) {{
                        refreshButton.disabled = false;
                        refreshButton.classList.remove("opacity-60");
                    }}
                }});
        }}

        document.addEventListener("DOMContentLoaded", function() {{
            const refreshButton = document.getElementById("refresh-jobs");
            if (refreshButton) {{
                refreshButton.addEventListener("click", loadJobs);
            }}
            loadJobs();
        }});
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


def _as_list(value):
    return value if isinstance(value, list) else []


def _first_value(item, *keys, default=""):
    for key in keys:
        value = item.get(key)
        if value not in (None, "", [], {}):
            return value
    return default


def _to_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if value is None:
        return False

    normalized = str(value).strip().lower()
    return normalized in {"true", "1", "yes", "y", "complete", "completed", "closed", "done"}


def _to_float(value, default=0.0):
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value, default=0):
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _normalize_text(value, default=""):
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _load_active_ros():
    try:
        with open(ACTIVE_ROS_STATE_PATH, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return []

    if not isinstance(payload, dict):
        return []

    active_ros = payload.get("active_ros")
    if not isinstance(active_ros, list):
        return []

    normalized = []
    for ro in active_ros:
        text = _normalize_text(ro, "")
        if text:
            normalized.append(text)

    return normalized


def _derive_priority(normalized_job):
    workflow_status = _normalize_text(normalized_job.get("workflow_status", ""), "").lower()
    clocked_in = _to_bool(normalized_job.get("clocked_in"))
    job_marked_complete = _to_bool(normalized_job.get("job_marked_complete"))
    labor_hours_remaining = _to_float(normalized_job.get("labor_hours_remaining"), 0.0)
    progress_percent = _to_int(normalized_job.get("progress_percent"), 0)

    if job_marked_complete or workflow_status in {"complete", "completed", "closed", "done"} or progress_percent >= 100:
        return "P4"

    if (not clocked_in) and labor_hours_remaining > 3:
        return "P1"

    if clocked_in and progress_percent < 25:
        return "P2"

    if progress_percent < 100:
        return "P3"

    return "P4"


def _normalize_job(item):
    ro = _normalize_text(
        _first_value(
            item,
            "ro",
            "ro_number",
            "ticket_reference",
            "repair_order",
            "repairOrder",
            "work_order_number",
            default="",
        ),
        "Unknown RO",
    )

    advisor = _normalize_text(
        _first_value(item, "advisor", "advisor_name", "advisorName", "service_advisor", default=""),
        "Unknown",
    )

    technician = _normalize_text(
        _first_value(
            item,
            "technician",
            "technician_name",
            "technicianName",
            "tech",
            "assigned_technician",
            default="",
        ),
        "Unassigned",
    )

    vehicle = _normalize_text(
        _first_value(item, "vehicle", "vehicle_name", "vehicleDescription", "vehicle_description", default=""),
        "",
    )

    customer = _normalize_text(
        _first_value(item, "customer", "customer_name", "customerName", default=""),
        "",
    )

    bay = _normalize_text(
        _first_value(item, "bay", "bay_name", "bayNumber", "bay_number", default=""),
        "",
    )

    workflow_status = _normalize_text(
        _first_value(item, "workflow_status", "workflowStatus", "status", "job_status", default="unknown"),
        "unknown",
    )

    progress_percent = _to_int(
        _first_value(item, "progress_percent", "progressPercent", "percent_complete", default=0),
        0,
    )

    clocked_in = _to_bool(_first_value(item, "clocked_in", "clockedIn", default=False))
    job_marked_complete = _to_bool(
        _first_value(item, "job_marked_complete", "jobMarkedComplete", "isComplete", default=False)
    )
    labor_hours_remaining = _to_float(
        _first_value(
            item,
            "labor_hours_remaining",
            "laborHoursRemaining",
            "remaining_labor_hours",
            default=0.0,
        ),
        0.0,
    )

    summary = _normalize_text(
        _first_value(item, "summary", "notes", "issue", "concern", "description", default=""),
        workflow_status.replace("_", " ").title(),
    )

    normalized_job = {
        "vehicle": vehicle,
        "customer": customer,
        "advisor": advisor,
        "technician": technician,
        "bay": bay,
        "ro": ro,
        "summary": summary,
        "progress_percent": progress_percent,
        "clocked_in": clocked_in,
        "job_marked_complete": job_marked_complete,
        "labor_hours_remaining": labor_hours_remaining,
        "workflow_status": workflow_status,
    }
    normalized_job["priority"] = _derive_priority(normalized_job)
    return normalized_job


def _normalize_jobs_payload(payload):
    raw_jobs = _as_list(payload.get("jobs"))
    if not raw_jobs:
        raw_jobs = _as_list(payload.get("records"))

    normalized_jobs = []
    for item in raw_jobs:
        if isinstance(item, dict):
            normalized_jobs.append(_normalize_job(item))

    return {
        "source": payload.get("source", "autoflow"),
        "status": payload.get("status", "ok"),
        "jobs": normalized_jobs,
        "count": len(normalized_jobs),
        "message": payload.get("message", ""),
        "timestamp": payload.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    }


def _load_jobs_from_autoflow():
    try:
        from connectors import autoflow
    except Exception as exc:
        return _fallback_jobs_payload(f"import_failed: {exc}")

    active_ros = _load_active_ros()

    try:
        if hasattr(autoflow, "fetch_autoflow_data") and callable(autoflow.fetch_autoflow_data):
            payload = autoflow.fetch_autoflow_data(active_ros)
            if isinstance(payload, dict):
                return _normalize_jobs_payload(payload)
    except Exception as exc:
        return _fallback_jobs_payload(f"fetch_autoflow_data_failed: {exc}")

    try:
        if hasattr(autoflow, "load_mock_autoflow_jobs") and callable(autoflow.load_mock_autoflow_jobs):
            payload = autoflow.load_mock_autoflow_jobs()
            if isinstance(payload, dict):
                return _normalize_jobs_payload(payload)
    except Exception as exc:
        return _fallback_jobs_payload(f"load_mock_autoflow_jobs_failed: {exc}")

    return _fallback_jobs_payload("no_supported_autoflow_payload_found")


@app.route("/")
def board():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html = HTML_TEMPLATE.format(timestamp=timestamp)
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


@app.route("/api/hermes-summary")
def api_hermes_summary():
    try:
        return jsonify(
            {
                "source": "placeholder",
                "status": "ok",
                "summary": "Hermes summary placeholder. Intelligence layer not yet connected.",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        ), 200
    except Exception:
        return jsonify(
            {
                "source": "placeholder",
                "status": "ok",
                "summary": "Hermes summary unavailable.",
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        ), 200


if __name__ == "__main__":
    print("🚀 Starting Country Club Advisor Command Board on 127.0.0.1:5000")
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
        threaded=True,
        use_reloader=False,
    )