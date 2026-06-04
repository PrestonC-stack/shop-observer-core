# Callahan Command Board + CAS — Session Passdown
**Date:** June 4, 2026
**Branch:** ai-build-stabilization
**Repo:** PrestonC-stack/shop-observer-core
**AI Machine:** C:\AI-RUNTIME\shop-observer-core
**Board URL:** https://tasks.callahanautoaz.net

---

## SYSTEM STATUS — WHAT IS WORKING RIGHT NOW

### Board (Live)
- Main board: https://tasks.callahanautoaz.net
- Drew board: https://tasks.callahanautoaz.net/drew
- Mitch board: https://tasks.callahanautoaz.net/mitch
- Preston board: https://tasks.callahanautoaz.net/preston
- DVI page: https://tasks.callahanautoaz.net/dvi ← NEW THIS SESSION
- AutoFlow webhook live on port 5055
- Cloudflare tunnel active
- 22+ active jobs tracking

### Sprint 1 — Complete and Tested
Local DVI gate running. Tested live on RO 13517. Working correctly.

Files in repo:
```
core/cas/dvi_schema.py         — data structures (DVIReview, DVIFlag, TimelineEntry)
core/cas/dvi_gate.py           — local rules engine (no AI, no API credits)
core/cas/rework_slip.py        — HTML + text rework slip generator
core/timeline/job_timeline.py  — per-RO JSONL event logger
core/state/state_manager.py    — save/load DVIReview to disk
config/cas_rules/dvi_gate_rules.yaml — all rule thresholds (edit without code changes)
test_dvi_gate.py               — manual test command
```

What the gate catches automatically:
- Concern item with no photo → CRITICAL flag
- Concern item with blank or vague note → CRITICAL or IMPORTANT flag
- Brake item with no measurement → CRITICAL flag
- Tire item with no tread data → CRITICAL flag
- Leak item with no location or photo → CRITICAL flag
- Safety item not inspected → IMPORTANT flag
- Primary complaint not addressed in DVI → IMPORTANT flag

Result: PASS / REVIEW / REWORK_REQUIRED
Saves to: state/dvi_reviews/{RO}.json
Logs to: state/job_timeline/{RO}.jsonl
Rework slip: state/dvi_reviews/rework_slip_{RO}.html

### Sprint 2A — Complete, In Repo, NOT YET FULLY TESTED IN PRODUCTION
Files added:
```
core/cas/dvi_trigger.py    — webhook handler, unknown event logger, status tracker
dashboard/dvi_page.py      — /dvi page with three sections
```
Webhook receiver patched to call handle_webhook_event() on every event.
app.py patched with /dvi, /dvi/slip/<ro>, /dvi/acknowledge/<ro> routes.

What fires automatically now:
- Every dvi_signoff webhook → waits 15s → pulls DVI → runs gate → saves result
- Every unknown event type → logged to data/unknown_events/unknown_events.jsonl
- Every status_update → timestamped to data/status_transitions/transitions.jsonl

DVI page at /dvi shows:
- Section 1: Needs Attention (REWORK_REQUIRED or REVIEW, unacknowledged)
- Section 2: In Progress (jobs in DVI-related statuses, no completed review)
- Section 3: Completed Today (gate results with timestamps)

### Confirmed Technical Facts
- AutoFlow photo URLs are publicly accessible (S3, no auth required)
- item_status "1" = concern, "2" = pass, "" = not inspected
- item_images array contains photo URLs
- item_notes contains tech notes (measurements typed in here if at all)
- No dedicated measurement field — must detect from note text
- work_orders API returns dvi_items with labor hours and parts
- dvi_signoff webhook fires when tech completes DVI
- Conversations API not yet wired (customer last-contact tracking still outstanding)
- TekMetric clock-in/out not exposed via AutoFlow API (confirmed)
- Status transition timestamps available from status_update webhook events

---

## WHAT IS NOT WORKING / OUTSTANDING

1. **Pulsing animation on /dvi** — rework required items should pulse red to catch attention. Not yet built. Simple CSS addition.

2. **Sprint 2A not restarted and production-tested** — board was restarted and /dvi loads, but no real dvi_signoff webhook has fired since the patch went in. Need to confirm the auto-trigger works on a real DVI completion.

3. **GitHub token was exposed in chat** — token REVOKE_THIS_TOKEN_AT_GITHUB_SETTINGS_TOKENS was used to push files. REVOKE THIS IMMEDIATELY at https://github.com/settings/tokens before starting next session.

4. **Synology NAS not yet configured** — DS920+ on local network, Container Manager not installed, PostgreSQL not deployed. Data is accumulating locally in JSONL files and will be backfilled to Synology when configured. Not blocking anything.

5. **999h time-in-status display** — AutoFlow timestamps not yet wired into scoring engine. Jobs show 999h instead of real elapsed time.

6. **Conversations API not wired** — customer last-contact tracking not yet built.

7. **Auto-start on reboot** — still not 100% reliable. Lower priority now that system is stable.

---

## SPRINT BUILD SEQUENCE — WHAT COMES NEXT

### NEXT: Sprint 2B — Visual Polish + Pulse Animation
**Do this first. It's small and makes the board feel alive.**

1. Add CSS pulse animation to /dvi Needs Attention section
   - REWORK_REQUIRED items pulse red
   - REVIEW items pulse amber
   - Auto-stops when acknowledged

2. Add DVI status badge to advisor board cards
   - Small badge on each job card: REWORK / REVIEW / DVI CLEAR / NO DVI
   - Red dot for rework, amber for review, green for clear
   - Clicking badge goes to /dvi page
   - Keeps advisor boards clean — just a dot, no detail

3. Fix 999h time-in-status using transition timestamps
   - data/status_transitions/transitions.jsonl now being written
   - scoring.py reads last transition timestamp for each RO
   - Shows real elapsed time instead of 999h

**Codex prompt for Sprint 2B:**
"Add CSS pulse animation to /dvi Needs Attention section for REWORK_REQUIRED (red pulse) and REVIEW (amber pulse) items. Add a small DVI status badge to each job card on drew_board.html and mitch_board.html that shows REWORK/REVIEW/CLEAR based on state/dvi_reviews/{ro}.json if it exists. Fix time-in-status in scoring.py to read from data/status_transitions/transitions.jsonl using the last transition timestamp for each RO instead of showing 999h. Do not modify webhook receiver or dvi_gate.py."

---

### Sprint 3 — TekMetric Packet Builder + Smart Scheduler + Callie Pickup Script
**This is the big one. All three are connected and use the same DVI tier data.**

#### 3A — TekMetric Packet Builder
File: core/cas/tekmetric_packet.py
Triggered by: advisor clicks "Build TekMetric Packet" button on /dvi page
Only available after DVI gate passes or advisor overrides

Output structure (copy-paste ready for TekMetric):
```
TIER 1 — Customer Primary Complaint
[job name, labor hours, parts needed, tech notes]

TIER 2 — Safety Items (present with Tier 1)
[each safety finding with why it matters in plain language]

TIER 3 — Additional Findings
[secondary findings, customer talking point]

TIER 4 — Maintenance Schedule (presented as a plan, not a bill)
Month 1-2: [item]
Month 3-4: [item]
Month 5-6: [item]
```

Rules:
- No pricing generated unless explicitly requested
- No unsupported repairs added
- No fear-selling language
- Tier 4 never presented as urgent

#### 3B — Smart Scheduling Engine
File: core/cas/smart_scheduler.py
Triggered by: after TekMetric packet is built

Logic:
1. Score each deferred item by urgency (severity + season + mileage rate)
   - Coolant seep in November → schedule March before heat season
   - Front main seal seep → schedule by mileage threshold
   - Brakes at 3mm → schedule within 30 days
2. Group items with labor overlap
   - Struts + brakes = shared front end disassembly → same appointment
   - Valve covers + spark plugs = same access → same appointment
   - Flag as "schedule together — shared labor saves X hours"
3. Read AutoFlow appointments API for open slots
   - GET /api/v1/appointments with date range
   - Find gaps that aren't stacked
   - Avoid days already at capacity
4. Output two date + time options per priority group

Output format:
```
GROUP 1 — Schedule within 30 days (safety)
Front brakes + front struts — do together, shared labor
Option A: Tuesday 6/10 at 8am
Option B: Thursday 6/12 at 1pm
Est. time: 3.5 hrs

GROUP 2 — Schedule by March (before heat season)
Coolant seep — minor now, critical by summer
Option A: Tuesday 3/3 at 8am
Option B: Thursday 3/5 at 2pm
Est. time: 2 hrs
```

#### 3C — Callie Pickup Script
File: core/cas/callie_pickup.py
Triggered by: job moves to Ready status OR advisor clicks "Pickup Checklist"

Checklist enforced before Ready closes:
- Primary complaint resolved ✓/✗
- Safety items repaired or formally declined ✓/✗
- Future work presented ✓/✗
- Scheduling conversation happened ✓/✗
- Next appointment offered ✓/✗
- CAS presentation completed ✓/✗

Callie generates advisor script:
"Before [customer] leaves — [customer name], while we had everything apart 
today we found a few things coming up. I put together a plan so we're not 
hitting you with everything at once. The brakes and struts we'd want to get 
done in the next few weeks — I have [Option A] or [Option B] available. 
Which works better for you?"

#### 3D — Scheduling Pulse and Verification
When a job closes and deferred items exist with no scheduled appointment:
- Card pulses on /dvi and on advisor board
- appointment_create webhook fires when Mitch books follow-up
- System matches appointment to customer, surfaces to Mitch:
  "New appointment for [customer] — does this cover deferred items from RO [X]?"
- One-click confirm stops the pulse

---

### Sprint 4 — Analytics + Hermes Learning Foundation
File: core/analytics/bottleneck_report.py

Reports built from accumulated data in:
- data/status_transitions/transitions.jsonl
- state/job_timeline/{RO}.jsonl
- state/dvi_reviews/{RO}.json

KPIs to track:
- DVI completion time (entry to DVI updates → signoff)
- Advisor response time (DVI signoff → acknowledged)
- Estimate build time (DVI acknowledged → Advisor Estimate status)
- First-pass DVI rate per tech (% that pass without rework)
- Rework flag categories (which flags appear most often)
- Approval rate by advisor (estimates approved vs declined)
- Average time per status per RO type

Hermes integration:
- Hermes reads accumulated JSONL data
- Surfaces pattern observations to Preston
- Preston reviews and approves or rejects
- Approved patterns update config/cas_rules/ YAML files
- Human always approves rule changes — system never self-modifies

---

### Sprint 5 — Synology NAS + PostgreSQL
Setup steps (already documented in session):
1. Install Container Manager on DS920+
2. Deploy postgres:latest container
   - Port: 5432
   - Volume: /postgres-data → /var/lib/postgresql/data
   - Env: POSTGRES_DB=callahan, POSTGRES_USER=callahan_admin
3. Note Synology local IP (192.168.1.X)
4. Add to .env: SYNOLOGY_DB_HOST, SYNOLOGY_DB_PORT, SYNOLOGY_DB_NAME, SYNOLOGY_DB_USER, SYNOLOGY_DB_PASSWORD
5. Build db_writer.py to push all JSONL data to PostgreSQL
6. Backfill existing JSONL files

Data stored in PostgreSQL:
- autoflow_events (every webhook payload)
- dvi_reviews (every gate result)
- status_transitions (every status change with timestamp)
- job_timeline (every RO event)
- unknown_events (discovery log)
- advisor_notes (all notes from confirmations.jsonl)

---

## FILE STRUCTURE AS OF THIS SESSION

```
C:\AI-RUNTIME\shop-observer-core\
├── core/
│   ├── cas/
│   │   ├── __init__.py
│   │   ├── dvi_schema.py        ← data structures
│   │   ├── dvi_gate.py          ← local rules engine
│   │   ├── dvi_trigger.py       ← webhook handler + event logger
│   │   └── rework_slip.py       ← slip generator
│   ├── timeline/
│   │   └── job_timeline.py      ← per-RO event logger
│   ├── state/
│   │   └── state_manager.py     ← save/load reviews
│   └── ai/
│       └── __init__.py          ← placeholder for Sprint 4
├── config/
│   └── cas_rules/
│       └── dvi_gate_rules.yaml  ← all rule thresholds
├── dashboard/
│   ├── app.py                   ← Flask entry (has /dvi routes)
│   ├── dvi_page.py              ← /dvi page renderer
│   ├── board_loader.py
│   ├── board_renderer.py
│   ├── scoring.py
│   ├── confirmations.py
│   ├── overrides.py
│   ├── drew_board.html
│   └── mitch_board.html
├── webhooks/
│   └── autoflow_webhook_receiver.py  ← patched with dvi_trigger call
├── state/
│   ├── dvi_reviews/             ← one JSON per RO
│   ├── job_timeline/            ← one JSONL per RO
│   ├── board_state.json
│   └── shop_state.json
├── data/
│   ├── autoflow_events/         ← all webhook payloads
│   ├── status_transitions/      ← timestamped status changes
│   └── unknown_events/          ← undiscovered event types
├── tests/
│   └── fixtures/
│       └── dvi_13517.json       ← saved DVI response for offline testing
├── test_dvi_gate.py             ← manual test command
├── Start-Callahan-AI.ps1        ← master launcher
└── SYSTEM_STATE.md              ← GitHub truth file
```

---

## HOW TO START THE SYSTEM

Double-click Callahan AI on desktop. Three windows open:
- Blue — Board (port 8080)
- Green — Webhook (port 5055)
- Purple — Tunnel (Cloudflare)

Or manually:
```powershell
python dashboard\app.py
python webhooks\autoflow_webhook_receiver.py
.\cloudflared.exe tunnel --origincert "C:\Users\CallahanAi\.cloudflared\cert.pem" --config "C:\Users\CallahanAi\.cloudflared\config.yml" run shop-tasks
```

---

## HOW TO TEST DVI GATE MANUALLY

```powershell
cd C:\AI-RUNTIME\shop-observer-core
python test_dvi_gate.py 13517 --save-slip
python test_dvi_gate.py 13505 --save-slip
python test_dvi_gate.py {RO} --fixture tests/fixtures/dvi_{RO}.json
```

---

## START OF NEXT SESSION CHECKLIST

1. FIRST — Revoke GitHub token at https://github.com/settings/tokens
2. Pull latest: git pull origin ai-build-stabilization
3. Restart services (double-click desktop shortcut)
4. Verify /dvi page loads and shows correct data
5. Confirm dvi_signoff webhook auto-trigger has fired at least once
   - Check data/status_transitions/transitions.jsonl exists and has entries
   - Check data/unknown_events/ for any new event types discovered
6. Build Sprint 2B — pulse animation + advisor board badges + fix 999h

---

## REVENUE CONTEXT

Target: $72,986/month (proven October 2025)
Current pace: $29K-$60K range
Gap: ~$34K/month
Root cause: Advisor execution consistency
This system closes the gap by enforcing process, not adding capacity.

---

## KEY DECISIONS MADE THIS SESSION

- Separate /dvi page (not cluttering advisor boards) ✓
- Rules first, AI second, vision only when needed ✓
- Any advisor can override REWORK_REQUIRED with logged reason ✓
- Synology NAS for data storage (DS920+, PostgreSQL in Docker) — not yet configured ✓
- Hermes learning loop: system surfaces patterns → Preston approves → rules update ✓
- Smart scheduler: two date/time options per priority group, labor overlap grouping ✓
- Scheduling verification: appointment_create webhook + one-click Mitch confirm ✓
- CAS ChatGPT project remains the estimate intelligence layer — board enforces, CAS advises ✓
- Human always approves rule changes — system never self-modifies ✓
