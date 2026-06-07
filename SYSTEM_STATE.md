# Callahan AI — System State
Last Updated: 2026-06-07
Branch: ai-build-stabilization
Repo: https://github.com/PrestonC-stack/shop-observer-core

---

## What Is Working (Live and Confirmed)

- Main board: https://tasks.callahanautoaz.net (port 8080)
- Drew board: https://tasks.callahanautoaz.net/drew
- Mitch board: https://tasks.callahanautoaz.net/mitch
- Preston board: https://tasks.callahanautoaz.net/preston
- DVI page: https://tasks.callahanautoaz.net/dvi
- AutoFlow webhook live on port 5055
- Cloudflare tunnel active
- 22+ active jobs tracking

---

## Sprint History

### Sprint 1 — Complete and Confirmed
Local DVI gate running. Tested live on RO 13517.

Files:
- core/cas/dvi_schema.py — data structures
- core/cas/dvi_gate.py — local rules engine (no AI, no API credits)
- core/cas/rework_slip.py — HTML + text rework slip generator
- core/timeline/job_timeline.py — per-RO JSONL event logger
- core/state/state_manager.py — save/load DVIReview to disk
- config/cas_rules/dvi_gate_rules.yaml — all rule thresholds
- test_dvi_gate.py — manual test command

Gate catches: missing photos, vague notes, missing brake measurements, missing tire tread, missing leak location, uninspected safety items, primary complaint not addressed.
Result: PASS / REVIEW / REWORK_REQUIRED
Saves to: state/dvi_reviews/{RO}.json

### Sprint 2A — Complete and Confirmed
Files added:
- core/cas/dvi_trigger.py — webhook handler, unknown event logger, status tracker
- dashboard/dvi_page.py — /dvi page with three sections

What fires automatically:
- Every dvi_signoff webhook → waits 15s → pulls DVI → runs gate → saves result
- Every unknown event → logged to data/unknown_events/unknown_events.jsonl
- Every status_update → timestamped to data/status_transitions/transitions.jsonl

DVI page sections:
1. Needs Attention (REWORK_REQUIRED or REVIEW, unacknowledged)
2. In Progress (jobs in DVI-related statuses, no completed review)
3. Completed Today (gate results with timestamps)

### Sprint 2B — Complete and Confirmed
Commits: 9fc6cc0, 45fc764, 63fa0aa, bf5fd1d, 93da05c, 3d8089a, 8ce8797, 7fc068f

1. Pulse animation on /dvi Needs Attention
   - REWORK_REQUIRED pulses red, REVIEW pulses amber
   - Acknowledged cards get no pulse
   - CSS keyframes inline in dvi_page.py

2. Time-in-status fix (999h — real elapsed time)
   - Root cause: scoring_engine.py was reading ticket_reference/invoice
     fields that do not exist — correct field is "ro"
   - dashboard/scoring.py is NOT in the board render path —
     actual renderer is scripts/scoring_engine.py
   - Fix: _load_latest_transition_by_ro() reads transitions.jsonl
     using fields "ro" and "received_at"
   - Jobs without transition records correctly fall back to 999h
     until they fire a status_update webhook

3. DVI status badge dots on all three boards
   - board_loader.py: _inject_dvi_status() reads state/dvi_reviews/{ro}.json
     and injects dvi_review_status into each job
   - drew_board.html + mitch_board.html: badge inside JS template literal
     after ${noteBadge}
   - board_renderer.py: badge inline on customer name line
   - Red = REWORK_REQUIRED, amber = REVIEW, green = PASS, nothing = NO_DVI
   - Clicking dot goes to /dvi

---

## Key Technical Facts (Confirmed)

- shop_state.json RO field: "ro" (NOT ticket_reference or invoice)
- transitions.jsonl fields: "ro", "received_at", "status", "customer", "vehicle", "ticket_id"
- dvi_reviews/{ro}.json gate result field: "review_status"
- AutoFlow photo URLs: publicly accessible S3, no auth required
- item_status: "1" = concern, "2" = pass, "" = not inspected
- No dedicated measurement field — must detect from note text
- TekMetric clock-in/out not exposed via AutoFlow API (confirmed)
- Conversations API not yet wired
- Main board served as static HTML_TEMPLATE string from board_renderer.py —
  requires server restart to pick up template changes (not just browser refresh)
- Drew/Mitch boards are static HTML files — hard refresh (Ctrl+Shift+R) is enough

---

## File Structure (Current)

- core/cas/dvi_schema.py
- core/cas/dvi_gate.py
- core/cas/dvi_trigger.py
- core/cas/rework_slip.py
- core/timeline/job_timeline.py
- core/state/state_manager.py
- core/ai/__init__.py
- config/cas_rules/dvi_gate_rules.yaml
- dashboard/app.py
- dashboard/dvi_page.py
- dashboard/board_loader.py — _inject_dvi_status() added Sprint 2B
- dashboard/board_renderer.py — DVI badge added Sprint 2B
- dashboard/scoring.py
- dashboard/confirmations.py
- dashboard/overrides.py
- dashboard/drew_board.html — DVI badge added Sprint 2B
- dashboard/mitch_board.html — DVI badge added Sprint 2B
- scripts/scoring_engine.py — transition reader fixed Sprint 2B
- scripts/build_board_state.py
- scripts/build_shop_state.py
- webhooks/autoflow_webhook_receiver.py
- state/dvi_reviews/ — one JSON per RO
- state/job_timeline/
- state/board_state.json
- state/shop_state.json
- data/status_transitions/transitions.jsonl
- data/unknown_events/
- data/autoflow_events/
- test_dvi_gate.py
- Start-Callahan-AI.ps1
- SYSTEM_STATE.md

---

## Outstanding Issues

- Auto-start on reboot still unreliable — lower priority
- Conversations API not wired — customer last-contact tracking outstanding
- Synology NAS not configured — data accumulating in JSONL locally
- Jobs with junk statuses (e.g. "aaa") show 999h permanently — fix in AutoFlow

---

## What Comes Next — Sprint 3 (Active Target)

### 3A — TekMetric Packet Builder
File: core/cas/tekmetric_packet.py
Triggered by: advisor clicks "Build TekMetric Packet" on /dvi page
Only available after DVI gate passes or advisor overrides
Output: tiered copy-paste structure for TekMetric
Rules: no pricing unless requested, no fear-selling, Tier 4 never urgent
NOTE: Confirm exact output structure with Preston before building.

### 3B — Smart Scheduling Engine
File: core/cas/smart_scheduler.py
Score deferred items by urgency, group by labor overlap, read AutoFlow
appointments API, output two date/time options per priority group.

### 3C — Callie Pickup Script
File: core/cas/callie_pickup.py
Triggered by job moving to Ready. Enforces checklist, generates advisor
script for scheduling conversation before customer leaves.

### 3D — Scheduling Pulse
Card pulses when job closes with deferred items and no follow-up booked.
Stops when appointment_create webhook fires and Mitch confirms.

---

## How To Start The System

Double-click Callahan AI on desktop:
- Blue — Board (port 8080)
- Green — Webhook (port 5055)
- Purple — Tunnel (Cloudflare)

---

## How To Test DVI Gate Manually

cd C:\AI-RUNTIME\shop-observer-core
python test_dvi_gate.py 13517 --save-slip
python test_dvi_gate.py {RO} --fixture tests/fixtures/dvi_{RO}.json

---

## Codex Path Warning

Codex saves to: C:\CALLAHAN\AI Workspace\shop-observer-core\
Runtime path:   C:\AI-RUNTIME\shop-observer-core\
Always verify and re-apply to the correct location after Codex runs.

---

## Revenue Context

Target: $72,986/month (proven October 2025)
Current: $29K-$60K range | Gap: ~$34K/month
Root cause: Advisor execution consistency
This system closes the gap by enforcing process, not adding capacity.
