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
- Packet builder: https://tasks.callahanautoaz.net/dvi/packet/<ro>
- AutoFlow webhook live on port 5055
- Cloudflare tunnel active
- 22+ active jobs tracking

---

## Sprint History

### Sprint 1 — Complete and Confirmed
Local DVI gate running. Tested live on RO 13517.
Files: core/cas/dvi_schema.py, dvi_gate.py, rework_slip.py,
core/timeline/job_timeline.py, core/state/state_manager.py,
config/cas_rules/dvi_gate_rules.yaml, test_dvi_gate.py

Gate catches: missing photos, vague notes, missing brake measurements,
missing tire tread, missing leak location, uninspected safety items,
primary complaint not addressed.
Result: PASS / REVIEW / REWORK_REQUIRED
Saves to: state/dvi_reviews/{RO}.json

### Sprint 2A — Complete and Confirmed
Files: core/cas/dvi_trigger.py, dashboard/dvi_page.py
Every dvi_signoff webhook triggers gate automatically.
Status transitions logged to data/status_transitions/transitions.jsonl
Unknown events logged to data/unknown_events/unknown_events.jsonl
DVI page at /dvi: Needs Attention / In Progress / Completed Today

### Sprint 2B — Complete and Confirmed
Commits: 9fc6cc0, 45fc764, 63fa0aa, bf5fd1d, 93da05c, 3d8089a,
8ce8797, 7fc068f

1. Pulse animation on /dvi — REWORK_REQUIRED red, REVIEW amber
2. Time-in-status fix — reads data/status_transitions/transitions.jsonl
   using fields "ro" and "received_at". Falls back to 999h if no record.
   Root cause was wrong field names (ticket_reference/invoice vs ro)
   and wrong file (dashboard/scoring.py vs scripts/scoring_engine.py)
3. DVI badge dots on all three boards
   - board_loader.py: _inject_dvi_status() reads state/dvi_reviews/{ro}.json
   - drew_board.html + mitch_board.html: badge in JS template literal
   - board_renderer.py: badge on customer name line
   - Red=REWORK_REQUIRED, amber=REVIEW, green=PASS, nothing=NO_DVI
   - Main board requires server restart for template changes

### Sprint 3A — Complete and Confirmed
Commits: 812ce96, c3f727a, c165908, 5ca9693

TekMetric Packet Builder — fully live and tested on RO 13526.

Files added:
- core/cas/tekmetric_packet.py — Claude API packet generator
- dashboard/packet_page.py — print-ready packet page renderer

What it does:
- Advisor clicks "Build Packet" on /dvi page
- Opens /dvi/packet/<ro> in new tab
- Claude API reads DVI review JSON + job data
- Generates structured packet with:
  - Drag order for TekMetric
  - Advisor mental gate (vehicle/season/usage aware)
  - CONCERN jobs (customer complaint)
  - SAFETY jobs (breakdown/stranded/danger items)
  - MAINTENANCE jobs (future schedule items)
  - POSSIBLE ADD-ON jobs (advisor radar only, not customer-facing)
- Each job block has: job title (copy), labor checklist (look up),
  parts checklist (look up), customer note (copy), conditional note
- Color coded: blue=CONCERN, red=SAFETY, green=MAINTENANCE,
  dark red=POSSIBLE ADD-ON
- Print button — clean printable view
- Regenerate button — forces new API call
- 4-hour cache prevents unnecessary API charges

Data saved:
- state/dvi_reviews/packet_{ro}.json — 4hr cache
- state/job_history/{ro}/packet_{timestamp}.json — permanent history
- data/api_costs/api_costs.jsonl — every API call logged with
  token counts and estimated cost

Cost: ~$0.04 per packet generated. Cache hits = $0.00.
Estimated monthly cost at current volume: $30-40/month total.

Known: mileage shows "Not recorded" — AutoFlow does not push
mileage into board state or DVI review JSON. Fix when AutoFlow
API is wired more deeply.

---

## Key Technical Facts (Confirmed)

- shop_state.json RO field: "ro" (NOT ticket_reference or invoice)
- transitions.jsonl fields: "ro", "received_at", "status", "customer",
  "vehicle", "ticket_id"
- dvi_reviews/{ro}.json gate result field: "review_status"
- packet_{ro}.json packet result field: "jobs" array
- AutoFlow photo URLs: publicly accessible S3, no auth required
- item_status: "1"=concern, "2"=pass, ""=not inspected
- No dedicated measurement field — detect from note text
- TekMetric clock-in/out not exposed via AutoFlow API (confirmed)
- Conversations API not yet wired
- Main board served as static HTML_TEMPLATE from board_renderer.py —
  requires server restart for template changes
- Drew/Mitch boards are static HTML files — hard refresh sufficient
- ANTHROPIC_API_KEY is in .env at repo root
- Codex saves to C:\CALLAHAN\AI Workspace\ — always verify runtime
  path C:\AI-RUNTIME\shop-observer-core\ after Codex runs

---

## File Structure (Current)

- core/cas/dvi_schema.py
- core/cas/dvi_gate.py
- core/cas/dvi_trigger.py
- core/cas/rework_slip.py
- core/cas/tekmetric_packet.py      ← NEW Sprint 3A
- core/timeline/job_timeline.py
- core/state/state_manager.py
- core/ai/__init__.py
- config/cas_rules/dvi_gate_rules.yaml
- dashboard/app.py
- dashboard/dvi_page.py             ← Build Packet button added
- dashboard/packet_page.py          ← NEW Sprint 3A
- dashboard/board_loader.py         ← _inject_dvi_status() Sprint 2B
- dashboard/board_renderer.py       ← DVI badge Sprint 2B
- dashboard/scoring.py
- dashboard/confirmations.py
- dashboard/overrides.py
- dashboard/drew_board.html         ← DVI badge Sprint 2B
- dashboard/mitch_board.html        ← DVI badge Sprint 2B
- scripts/scoring_engine.py         ← transition reader Sprint 2B
- scripts/build_board_state.py
- scripts/build_shop_state.py
- webhooks/autoflow_webhook_receiver.py
- state/dvi_reviews/                ← one JSON per RO + packet cache
- state/job_history/{ro}/           ← NEW permanent job history
- state/job_timeline/
- state/board_state.json
- state/shop_state.json
- data/status_transitions/transitions.jsonl
- data/api_costs/api_costs.jsonl    ← NEW API cost log
- data/unknown_events/
- data/autoflow_events/
- test_dvi_gate.py
- Start-Callahan-AI.ps1
- SYSTEM_STATE.md

---

## Outstanding Issues

- Auto-start on reboot still unreliable — lower priority
- Conversations API not wired — customer last-contact tracking
- Synology NAS not configured — data accumulating locally
- Mileage not available in AutoFlow board state — shows Not recorded
- Jobs with junk statuses (e.g. "aaa") show 999h — fix in AutoFlow
- Cache-hit logger wired but needs live test to confirm firing

---

## What Comes Next — Sprint 3B (Active Target)

Dashboard rework — compact cards, status dots, hover tooltips,
slide-out drawer, higher energy visual design.

Design direction locked from reference mockups (Grok + ChatGPT):
- Top KPI bar: Active ROs / Waiting Approval / Parts Delayed / Comebacks
- Filter tabs: All / P1 / P2 / P3 / Waiting / My ROs
- Compact job cards in priority swimlanes
- Each card: RO, customer, vehicle, next move, owner, time, priority
  color, status dots (DVI / Ticket / Customer Called / Production /
  QC / Appointment)
- Hover card: AI insight tooltip from Hermes
- Click card: slide-out drawer from right with tabs:
  Summary / DVI / Estimate / Packet / Audit / History
- Packet builder lives inside drawer as a tab
- Lighter color scheme, higher contrast, higher energy feel
- Mobile-friendly bottom nav for Drew and Mitch

Accountability dots per card:
- DVI done: auto-verified when gate result exists
- Ticket built: auto-verified when job reaches Advisor Estimate status
- Customer called: advisor clicks + required written note + timestamp
- Production hold: auto-verified when job reaches Servicing status
- QC done: auto-verified when job reaches QC status
- Appointment set: verified when AutoFlow calendar API confirms it

Tech assignment sheet: print button shows all ROs with job-level
tech assignments, flags unassigned job lines.

Sprint 3C (after 3B):
- Upload/audit panel per RO
- Document log in job_history
- AI estimate audit (Claude reads uploaded estimate vs DVI findings)
- Photo analysis pipeline

Sprint 3D:
- Smart scheduling engine
- AutoFlow appointments API integration
- Two date/time options per maintenance group
- Labor hour aware scheduling

Sprint 4:
- Analytics page at /analytics
- Action log (who did what, when, on which RO)
- API cost dashboard
- DVI quality report (rework rate, flag categories, tech performance)
- Packet usage tracking

Sprint 5:
- Synology NAS + PostgreSQL
- Backfill all JSONL data

---

## How To Start The System

Double-click Callahan AI on desktop:
- Blue — Board (port 8080)
- Green — Webhook (port 5055)
- Purple — Tunnel (Cloudflare)

---

## How To Test

DVI gate:
cd C:\AI-RUNTIME\shop-observer-core
python test_dvi_gate.py 13517 --save-slip

Packet builder:
Navigate to https://tasks.callahanautoaz.net/dvi
Click Build Packet on any REWORK_REQUIRED job
Opens /dvi/packet/<ro> in new tab

---

## Revenue Context

Target: $72,986/month (proven October 2025)
Current: $29K-$60K range | Gap: ~$34K/month
Root cause: Advisor execution consistency
This system closes the gap by enforcing process, not adding capacity.
