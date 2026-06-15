import os
from datetime import datetime

from flask import Flask, Response, jsonify, request, send_from_directory

from board_loader import (
    BOARD_ACTION_LOG_PATH,
    BOARD_OVERRIDE_LOG_PATH,
    HERMES_LOG_PATH,
    _append_jsonl,
    _fallback_jobs_payload,
    _find_job,
    _load_board_state,
    _load_jobs_from_autoflow,
)
from board_renderer import (
    CALLIE_MODEL,
    HTML_TEMPLATE,
    _call_ollama,
    _deterministic_callie_answer,
    _extract_ro_from_question,
    _hermes_answer,
    _is_general_greeting,
    _is_short_general_chat,
    _is_status_explainer_question,
    _load_callie_insights,
)
from confirmations import load_confirmations, record_confirmation
from overrides import record_job_override
from scoring import build_bay_metrics, build_hermes_summary_payload

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)


@app.route("/")
def board():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html = HTML_TEMPLATE.replace("__TIMESTAMP__", timestamp)
    return Response(html, mimetype="text/html")


@app.route("/v2")
def board_v2():
    from dashboard.board_v2 import render_board_v2
    return render_board_v2()


@app.route("/v2/hitlist")
def board_v2_hitlist():
    from dashboard.board_v2 import render_hitlist_page
    return render_hitlist_page()


@app.route("/api/search")
def api_search():
    from dashboard.board_v2 import search_results
    q = request.args.get("q", "").strip().lower()
    return jsonify(search_results(q))


@app.route("/healthz")
def healthz():
    return {"status": "ok"}, 200


@app.route("/drew")
def drew_board():
    return send_from_directory(CURRENT_DIR, "drew_board.html")


@app.route("/mitch")
def mitch_board():
    return send_from_directory(CURRENT_DIR, "mitch_board.html")


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


@app.route("/api/confirmations")
def api_confirmations():
    return jsonify({"status": "ok", "confirmations": load_confirmations()}), 200


@app.route("/api/confirm-step", methods=["POST"])
def api_confirm_step():
    payload = request.get_json(silent=True) or {}
    try:
        entry = record_confirmation(payload)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception as exc:
        return jsonify({"status": "error", "message": f"confirmation_failed: {exc}"}), 500
    return jsonify({"status": "received", "confirmation": entry}), 200


@app.route("/api/override-job", methods=["POST"])
def api_override_job():
    payload = request.get_json(silent=True) or {}
    current_job = _find_job(str(payload.get("ro", "")).strip())
    try:
        entry = record_job_override(payload, current_job=current_job)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception as exc:
        return jsonify({"status": "error", "message": f"override_failed: {exc}"}), 500
    return jsonify({"status": "received", "override": entry}), 200


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
        if job and _is_status_explainer_question(question):
            reply = {
                "response": _deterministic_callie_answer(question, job=job, mode=mode),
                "confidence": 92,
                "model": "fast-status-explainer",
            }
        else:
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
        return jsonify(build_hermes_summary_payload(board_state, insights))
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
    metrics = build_bay_metrics(jobs)
    p1 = metrics["p1"]
    communication_needs = metrics["communication_needs"]
    productivity_needs = metrics["productivity_needs"]
    data_needs = metrics["data_needs"]
    support_score = metrics["support_score"]
    front_score = metrics["front_score"]
    back_score = metrics["back_score"]
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
                <div class="text-sm uppercase tracking-wide text-emerald-300">Board Coverage Score</div>
                <div class="mt-3 text-6xl font-black text-emerald-200">{support_score}%</div>
            </div>
            <div class="rounded-3xl border border-cyan-700 bg-cyan-950/30 p-6">
                <div class="text-sm uppercase tracking-wide text-cyan-300">Front Coverage</div>
                <div class="mt-3 text-6xl font-black text-cyan-200">{front_score}%</div>
            </div>
            <div class="rounded-3xl border border-violet-700 bg-violet-950/30 p-6">
                <div class="text-sm uppercase tracking-wide text-violet-300">Back Coverage</div>
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
                    <div><span class="font-semibold text-zinc-100">Board Coverage Score:</span> this is not sold-hours productivity. It is a board health score across communication, floor visibility, and clean data signals.</div>
                    <div><span class="font-semibold text-zinc-100">Front Coverage:</span> customer updates staying ahead of the surprise and advisor-side action gaps staying under control.</div>
                    <div><span class="font-semibold text-zinc-100">Back Coverage:</span> tech clock-in visibility plus usable inspection/DVI evidence supporting production flow.</div>
                    <div><span class="font-semibold text-zinc-100">P1 Jobs:</span> true pressure items that need direct attention now.</div>
                    <div><span class="font-semibold text-zinc-100">Productivity / Data Needs:</span> combined count of jobs where the board still needs clearer floor evidence or cleaner source data.</div>
                </div>
            </div>
            <div class="rounded-3xl border border-zinc-800 bg-zinc-900 p-6">
                <h2 class="text-2xl font-bold">How To Bring Them Up</h2>
                <div class="mt-4 space-y-3 text-sm text-zinc-300">
                    <div><span class="font-semibold text-zinc-100">Raise Front Coverage:</span> log customer updates sooner, tighten callbacks, and clear waiting-approval drift early.</div>
                    <div><span class="font-semibold text-zinc-100">Raise Back Coverage:</span> keep labor clocked, finish DVI work cleanly, and tighten who is actively on each job.</div>
                    <div><span class="font-semibold text-zinc-100">Raise Board Coverage:</span> reduce flashing board helpers by correcting the real blocker instead of working around it.</div>
                    <div><span class="font-semibold text-zinc-100">Lower P1 count:</span> land the plane faster on ready jobs and remove unknowns before they turn into customer-trust issues.</div>
                    <div><span class="font-semibold text-zinc-100">Lower Productivity / Data Needs:</span> fix missing tech assignment, missing concern detail, missing DVI completion, and bad status usage.</div>
                </div>
            </div>
        </div>
    </div>
</body>
</html>"""
    return Response(html, mimetype="text/html")




from dashboard.dvi_page import render_dvi_page
from pathlib import Path as _Path

@app.route("/dvi")
def dvi_workflow():
    return render_dvi_page()

@app.route("/dvi/packet/<ro>")
def dvi_packet(ro):
    from dashboard.packet_page import render_packet_page
    return render_packet_page(ro)

@app.route("/dvi/history")
def dvi_packet_history():
    from dashboard.packet_page import render_packet_history
    return render_packet_history()

@app.route("/dvi/packet/<ro>/stored")
def dvi_packet_stored(ro):
    from dashboard.packet_page import render_packet_stored
    return render_packet_stored(ro)

@app.route("/dvi/packet/<ro>/regenerate", methods=["POST"])
def dvi_packet_regenerate(ro):
    from dashboard.packet_page import render_packet_regenerate
    return render_packet_regenerate(ro)


@app.route("/dvi/packet/<ro>/analyze-photos", methods=["POST"])
def dvi_packet_analyze_photos(ro):
    from dashboard.packet_page import render_packet_analyze_photos
    return render_packet_analyze_photos(ro)


@app.route("/dvi/packet/<ro>/merge-findings", methods=["POST"])
def dvi_packet_merge_findings(ro):
    from dashboard.packet_page import render_packet_merge_findings
    return render_packet_merge_findings(ro)

@app.route("/sanity-check")
def sanity_check():
    from dashboard.sanity_check import render_sanity_check
    return render_sanity_check()

@app.route("/dvi/slip/<ro>")
def dvi_slip(ro):
    slip_path = _Path(__file__).parent.parent / "state" / "dvi_reviews" / f"rework_slip_{ro}.html"
    if slip_path.exists():
        return slip_path.read_text(encoding="utf-8")
    return "Slip not found", 404

@app.route("/dvi/acknowledge/<ro>")
def dvi_acknowledge(ro):
    from core.state.state_manager import load_dvi_review, save_dvi_review
    from core.timeline.job_timeline import log_advisor_acknowledged
    review = load_dvi_review(ro)
    if review:
        review.advisor_acknowledged = True
        save_dvi_review(review)
        log_advisor_acknowledged(ro, "Advisor", "Acknowledged via board")
    return f"<script>window.location='/dvi'</script>"


if __name__ == "__main__":
    print(" Starting Country Club Advisor Command Board on 127.0.0.1:8080")
    app.run(host="127.0.0.1", port=8080, debug=False, threaded=True, use_reloader=False)
