# SYSTEM_STATE.md — AdviseMe Command Board
# Last updated: June 9, 2026
# Branch: ai-build-stabilization
# Runtime: C:\AI-RUNTIME\shop-observer-core
# Board URL: https://tasks.callahanautoaz.net

## SYSTEM STATUS — ALL LIVE

### Live URLs
- Main board (original): https://tasks.callahanautoaz.net
- Drew board: https://tasks.callahanautoaz.net/drew
- Mitch board: https://tasks.callahanautoaz.net/mitch
- DVI page: https://tasks.callahanautoaz.net/dvi
- Packet builder: https://tasks.callahanautoaz.net/dvi/packet/<ro>
- Sanity Check: https://tasks.callahanautoaz.net/sanity-check
- AdviseMe Command Board v2: https://tasks.callahanautoaz.net/v2
- Hit List: https://tasks.callahanautoaz.net/v2/hitlist
- Morning Brief: designed, not yet built as route

### How To Start
Double-click desktop shortcut — three windows:
- Blue: Board (port 8080) — python dashboard\app.py
- Green: Webhook (port 5055) — python webhooks\autoflow_webhook_receiver.py
- Purple: Tunnel (Cloudflare)

If bad gateway: manually run python dashboard\app.py from
C:\AI-RUNTIME\shop-observer-core\dashboard\

---

## SPRINT HISTORY — ALL COMPLETE

### Sprint 1 — DVI Gate
Local rules engine, no API credits. Catches missing photos,
vague notes, missing brake measurements, unaddressed primary
complaints. Saves to state/dvi_reviews/{ro}.json.
Status: COMPLETE

### Sprint 2A — DVI Trigger + /dvi Page
Auto-fires on dvi_signoff webhook (15s delay).
Three-section /dvi page: Needs Attention / In Progress /
Completed Today.
Status: COMPLETE

### Sprint 2B — Visual Polish
Pulse animation on /dvi (red=REWORK, amber=REVIEW).
Time-in-status fix using transitions.jsonl fields ro and
received_at. DVI badge dots on all three boards.
Key fix: scripts/scoring_engine.py is the actual renderer.
Key fix: RO field in shop_state.json is ro not ticket_reference.
Status: COMPLETE

### Sprint 3A — TekMetric Packet Builder
/dvi/packet/<ro> — Claude API generates structured packet.
Color coded: blue=CONCERN, red=SAFETY, green=MAINTENANCE,
dark red=POSSIBLE ADD-ON.
Job history saved to state/job_history/{ro}/.
API costs logged to data/api_costs/api_costs.jsonl.
Cost: ~$0.04 per packet. 4-hour cache.
ANTHROPIC_API_KEY in .env at repo root.
Status: COMPLETE

### Sprint 3B — AdviseMe Command Board v2 at /v2
Dark dispatch center UI. Left sidebar 13 nav tabs.
6 ownership-color columns with correct status routing.
Column mapping locked — status-based not owner-based.
KPI tiles, vehicle silhouettes, weather, live clock.
Advisor dropdown, Demo Mode (press D), search bar.
60-second auto-refresh. AdviseMe.ai purple branding.
Bottom analytics: AI Priority Radar, Shop Today,
Bottlenecks, Comeback Watch, Parts Snapshot.
Fixed: column mapping now routes by workflow_status only.
Fixed: servicing routes to In Progress correctly.
Fixed: Needs Review routes to waiting_other with Drew as owner.
Fixed: aaa/unknown status routes to waiting_other with
AutoFlow update prompt.
Fixed: inactive techs (Eugene Glosch, Johnathan Leithtoff,
Robert) flagged grey with "(no longer active)".
Status: SUBSTANTIALLY COMPLETE — known remaining items below

### Sprint 4A — Packet Cache + Regeneration Gatekeeping
Cache-first loading — saved packet serves instantly, zero cost.
Regeneration requires confirm dialog, requester name (Mitch/
Drew/Preston prompt), cost warning (~$0.04).
Fresh DVI pull on regenerate via AutoFlow GET /api/v1/dvi/{ro}.
Generation log on every packet: timestamp, trigger, requester,
item count, cost.
Per-RO running cost total displayed on packet.
Save as PDF button (window.print()).
Arizona timezone fix in format_ts() — always UTC-7.
Date display: "Mon Jun 9, 2026 · 2:48 PM" everywhere.
Cache file: state/dvi_reviews/{ro}_packet.json
Status: COMPLETE

### Sprint 4B — Photo Analysis Panel
Photo grid below packet — pulls from AutoFlow DVI via
GET /api/v1/dvi/{ro}.
Extracts photos from ALL DVI locations:
  - reason_vehicle_is_here[N].images[N].image_url
  - dvis[N].dvi_category[N].dvi_items[N].item_images[N]
  - item_picture fallback (plain URL strings)
  - Filters motovisuals.com stock icons automatically
Selective analysis — Drew picks diagnostic photos only.
S3 download requires browser-like headers (User-Agent,
Referer, Accept) — confirmed working.
Two-pass Claude vision analysis:
  Phase 1: individual photo descriptions
  Phase 2: synthesis call produces:
    - technical_summary (for repair order)
    - customer_explanation (plain language, read to customer)
Smart job block injection — findings injected into matching
packet job blocks by title matching.
RO Notes block at bottom — copy/paste ready for TekMetric.
Requester name prompt on Analyze (same as Regenerate).
Cost estimate shown before analysis (~$0.03/photo).
Generation log updated with photo analysis events.
Routes:
  POST /dvi/packet/<ro>/analyze-photos
  POST /dvi/packet/<ro>/merge-findings
Status: COMPLETE

### Sprint 5A — Full Webhook Payload Storage
Every AutoFlow webhook event now stores full payload.
data/status_transitions/transitions.jsonl — expanded fields:
  received_at, event_type, event_timestamp, ro, ticket_id,
  status, customer, vehicle, advisor, techs, event_id,
  callback_endpoint, tech_on_job, hours_since_last_event
data/ro_activity/{ro}.jsonl — per-RO event log, created on
first event, appended on every subsequent event.
tech_on_job: first tech name in techs array or "unassigned".
hours_since_last_event: calculated from previous ro_activity
entry for same RO.
Fail-safe: storage failures do not break webhook acceptance,
DVI trigger, or board rebuilds.
Confirmed live: Steve Chubb appearing correctly in ro_activity
files for ROs 13543 and 13544.
Status: COMPLETE

---

## TEAM ROSTER — CURRENT

### Advisors
- Drew Mize — shop-side (dispatching, DVI, staging, QC)
- Mitch Callahan — customer-facing (approvals, communication,
  parts ordering)

### Technicians (active)
- Steve Chubb
- Luis Cervantes
- TC Charleston
- Preston Callahan (occasional, only if on an RO)

### No longer with shop
- Eugene Glosch (eglosch)
- Johnathan Leithtoff (jonathanleithtoff)
- Robert (advisor)

---

## KEY TECHNICAL FACTS — CONFIRMED

### AutoFlow API
Base URL: https://callahanautomotive.autotext.me/api/v1/
Auth: Basic auth with base64(API_KEY:API_PASSWORD)
Photo URLs: publicly accessible S3 — requires browser-like
headers for server-side download:
  User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)
  Referer: https://app.autoflow.com/
  Accept: image/jpeg,image/png,image/*,*/*

### Confirmed working endpoints
GET /api/v1/dvi/{ro} — DVI with photos, items, categories
GET /api/v1/work_orders/{ro} — approved jobs, parts with
  arrived field (0/1), labor with quantity (sold hours),
  sms_user (tech assignment per job)
GET /api/v1/appointments — schedule tab, upcoming
GET /api/v1/conversations — needs customer_id or status_id

### Confirmed NOT available via API
- Tech clock-in/clock-out times
- Individual labor line completion status
- Hours actually worked vs hours sold
These exist in AutoFlow internally but are not exposed
in the public API. Data flows to TekMetric via private
backend integration not accessible to us.

### Work order data available
dvi_items array per RO contains:
  name, group, added_by, notes, sms_user (tech),
  remote_id, parts[], labor[]
Parts: description, quantity, part_number, arrived (0/1),
  sms_id, price
Labor: description, quantity (sold hours), sms_id, price
arrived: 1 = parts received, 0 = parts outstanding
This is the source of truth for parts blocking status.

### Webhook events captured
status_update, dvi_signoff, dvi_signoff_update, wo_signoff,
ro_approval, dvi_sent, appointment_create, appointment_update,
inbound_message, message_status
All stored to transitions.jsonl and ro_activity/{ro}.jsonl
with full techs array and advisor data.

### Data fields in shop_state.json jobs
RO field: ro (NOT ticket_reference or invoice)
Key fields: ro, customer, vehicle, workflow_status,
waiting_on, priority_lane, risk_level, technician,
technicians, progress_percent, sold_hours,
labor_hours_completed, incoming_soon, alerts,
dvi_review_status, hermes_next_action, hermes_score_reason

### Real AutoFlow workflow_status values (confirmed)
aaa, call_shop, checkin, finished, inspecting,
k_mech_complete, parts, qc, ready, servicing, unknown,
waiting approval, advisor estimate, ordering parts,
waiting parts, technical advisement, dvi updates,
ready for tech, awaiting tech, testing, advisor qc review,
advisor finalize ro, technical overview,
scheduled-not here, dvi only-not here, drop off/tow-in,
online/stage

### Real waiting_on values observed
Drew, Mitch, External Hold, Needs Review, Preston

### Column mapping — locked (board_v2.py)
Need Immediate Action: P1, stale 24h+, DVI rework
  unacknowledged, finished+not called >4hrs,
  waiting approval >4hrs
Waiting/Customer: waiting approval, call_shop,
  advisor estimate
Waiting/Other: waiting parts, ordering parts, external hold,
  Needs Review (Drew to triage), aaa, unknown,
  scheduled-not here, dvi only-not here
In Progress: servicing, inspecting, testing, dvi updates,
  ready for tech, awaiting tech, technical advisement,
  technical overview, k_mech_complete, checkin, qc,
  advisor qc review, drop off/tow-in, online/stage
Ready to Close: finished (≤4hrs), ready, advisor finalize ro
Parts/Inventory: waiting parts, ordering parts (primary hold)

### Priority logic — locked
P1: ready+Mitch waiting, finished+Mitch+>4hrs,
  waiting approval+>4hrs, DVI rework unacknowledged
P2A: no info captured
P2B: checked in, waiting on tech/DVI
P2C: advisor stuck
P3: active and controlled
P4: legitimate external hold
Stale: hours_in_status > 24 → floats to top, red glow,
  "24H NO MOVEMENT" badge

---

## FILE STRUCTURE — CURRENT

C:\AI-RUNTIME\shop-observer-core\
├── core/cas/
│   ├── dvi_schema.py
│   ├── dvi_gate.py
│   ├── dvi_trigger.py
│   ├── rework_slip.py
│   └── tekmetric_packet.py
├── dashboard/
│   ├── app.py
│   ├── board_v2.py
│   ├── dvi_page.py
│   ├── packet_page.py
│   ├── sanity_check.py
│   ├── board_loader.py
│   ├── board_renderer.py
│   ├── scoring.py
│   ├── drew_board.html
│   └── mitch_board.html
├── scripts/
│   └── scoring_engine.py
├── webhooks/
│   └── autoflow_webhook_receiver.py
├── state/
│   ├── dvi_reviews/         ← DVI gate results + packet cache
│   ├── job_history/{ro}/    ← permanent job history
│   └── shop_state.json
├── data/
│   ├── status_transitions/transitions.jsonl  ← EXPANDED
│   ├── ro_activity/{ro}.jsonl               ← NEW Sprint 5A
│   ├── api_costs/api_costs.jsonl
│   ├── api_costs/packet_errors.jsonl
│   └── unknown_events/
├── Start-Callahan-AI.ps1
└── SYSTEM_STATE.md

---

## AUTOFLOW API — WHAT IS AVAILABLE

| Endpoint | Status | Use |
|----------|--------|-----|
| /api/v1/appointments | 200 OK | Schedule tab |
| /api/v1/conversations | needs params | Inbox |
| /api/v1/dvi/{ro} | 200 OK | Packet builder, photos |
| /api/v1/work_orders/{ro} | 200 OK | Parts status, tech |
| /api/v1/repair_order/{inv} | 200 OK | Authorization |
| /api/v1/work-orders/{ro} | 404 | Not available |
| /api/v1/tickets/{ro} | 404 | Not available |

---

## CODEX PATH WARNING — CRITICAL
Codex saves to:
  C:\CALLAHAN\AI Workspace\shop-observer-core\
Runtime path:
  C:\AI-RUNTIME\shop-observer-core\
Every Codex session must:
1. Edit files in Codex workspace path
2. git add + git commit + git push origin ai-build-stabilization
3. Confirm commit hash and push result
4. Then on runtime: git pull origin ai-build-stabilization

---

## WHAT COMES NEXT — PRIORITY ORDER

### Immediate
1. Morning Brief page at /v2/morning-brief
   - Design complete (mockup built June 9)
   - Route: GET /v2/morning-brief
   - Data: shop_state.json, P1/P2 filter, grouped by advisor
   - Print-safe layout, no JS required
2. Work order enrichment — pull /api/v1/work_orders/{ro}
   on board refresh, store parts arrived status per job,
   show parts blocking status on board cards
3. Hit List print fix — broken CSS, black lines only
4. Afternoon Brief — same layout as Morning Brief,
   different data focus (rollover jobs, unanswered estimates)

### Sprint 5B — Tech Activity from ro_activity data
Use data/ro_activity/{ro}.jsonl to show on board cards:
  - Who has been on this job and when
  - Time-in-current-status per tech
  - Estimated completion based on sold hours vs elapsed time
  - Parts blocking flag from work_orders API arrived field

### Sprint 5C — Parts Intelligence
Pull work_orders/{ro} on board refresh.
Flag jobs where all parts arrived: 1 but status not moving.
Flag jobs where parts arrived: 0 blocking production.
Show parts status summary on board cards.

### Sprint 6 — Callie Tier 1
Deterministic answers from board data — zero API cost.
Job status, next action coaching, who owns what.
Only complex questions use Claude API (Tier 2).

### Future
- Smart Scheduling Engine
- KPI Targets tab
- Hermes learning loop
- PostgreSQL on Synology NAS
- AdviseMe.ai SaaS product

---

## REVENUE CONTEXT
Target: $72,986/month (proven October 2025)
Current: $29K-$60K range
Gap: ~$34K/month
Root cause: Advisor execution consistency
This system closes the gap by enforcing process.

---

## KNOWN ISSUES — OUTSTANDING
- Morning Brief button on /v2 not yet wired to a route
- Afternoon Brief layout needs complete redesign
- Hit List print broken (black lines only)
- Tech Sheet same as Sanity Check — needs own page
- Callie tab not functional
- Schedule tab is placeholder
- KPI Targets tab is placeholder
- Auto-start on Windows reboot still unreliable
- transitions.jsonl has old minimal-format entries before
  Sprint 5A — new full-format entries in ro_activity/{ro}.jsonl
  are authoritative source going forward

---

## SESSION PASSDOWN — June 9 2026
Major work completed this session:
- Sprint 4A: Packet caching, regeneration gate, requester
  prompt, cost warning, generation log, Arizona timezone
- Sprint 4B: Photo analysis panel, Claude vision integration,
  two-pass synthesis, job block injection, RO notes block,
  exhaustive DVI photo extraction (all AutoFlow locations)
- Sprint 3B: Column mapping fix, Needs Review routing,
  inactive tech flagging, aaa/unknown status routing
- Sprint 5A: Full webhook payload storage, per-RO activity
  log, tech_on_job tracking confirmed live
- Morning Brief layout designed (mockup only, not built)
- Three advisor emails written and ready to send
- Confirmed AutoFlow has no clock-in/clock-out API
- Confirmed work_orders API returns parts arrived status
  and tech assignment per job — valuable for Sprint 5B/5C

START OF NEXT SESSION:
1. cd C:\AI-RUNTIME\shop-observer-core
2. git pull origin ai-build-stabilization
3. Start services via desktop shortcut
4. Verify /v2 loads and column routing looks correct
5. Check ro_activity folder has files building up
6. Begin Morning Brief route — highest daily impact
