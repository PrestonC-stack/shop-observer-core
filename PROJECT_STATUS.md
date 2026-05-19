# Callahan AI - Shop Command Board

**Last Updated:** May 16, 2026  
**Current Branch:** `ai-build-stabilization`  
**Repo:** https://github.com/PrestonC-stack/shop-observer-core.git

## Progress Update - May 18, 2026 - Real Callie Intelligence Layer

- Real Callie intelligence layer added on top of the live wallboard
- `Send to Callie` now calls the local Ollama model with RO-aware context when available
- Added deterministic `callie_engine.py` to generate cached `data/callie_insights.json`
- Added visible cached Callie insights feed for fast/stable board rendering over Cloudflare Tunnel
- Preserved separation of concerns:
  - board/rules/evidence remain deterministic
  - Callie remains optional augmentation and fails soft if Ollama is unavailable
- Next:
  - refine prompt quality
  - improve source-conflict coaching
  - deepen Callie evidence reasoning and UI polish

## Progress Update - May 18, 2026 - Callie Context Guard + General Chat Fix

- Fixed board-level `Ask Callie` so it explicitly clears stale RO context before sending
- Added a fast greeting/general-question path so simple asks like `hello` do not wait on the heavy local model path
- Added visible loading / slow-model feedback in the Callie modal so users can see what is happening while the request is in flight
- Preserved job-aware context when Callie is opened from a specific RO card
- Kept deterministic board logic separate from Callie augmentation

## Progress Update - May 18, 2026 - Stronger Callie Greeting Guard

- Strengthened the Callie greeting fast-path so greetings and very short general chat clear RO context before any model call
- Added RO-like digit detection so short messages only stay job-aware when they actually reference a ticket
- General `hello` / `hi` / `hey` style asks now return immediately and should not inherit the last job card context

## Checkpoint - May 16, 2026 - Live Webhook State Loop

## Progress Update - May 18, 2026 - Board State Phase 1

### New Implementation Direction

- The board is now being formalized as a three-layer system:
  - `AutoFlow` provides raw facts and visible workflow status
  - `board_state.json` provides deterministic helper logic and supportive operational alerts
  - `Hermes` reads the processed board state and explains what matters next
- This keeps the system supportive and coach-like for the team while still giving ownership visibility into drift and bottlenecks.

### Board State Layer

- Added `scripts/build_board_state.py`
- New output file:
  - `state/board_state.json`
- `board_state.json` is derived from `state/shop_state.json`
- First-pass derived fields now include:
  - `priority_lane`
  - `waiting_on`
  - `risk_level`
  - `incoming_soon`
  - `alerts`
  - `next_action`
  - `source_evidence`

### Phase 1 Rules Included

- `Technical Advisement` and `Technical Overview` escalate toward Preston ownership
- Advisor-side statuses like `Advisor Estimate`, `Waiting approval`, `Ordering Parts`, `Advisor Finalize RO`, and `Ready` are mapped toward Mitch ownership
- Production-control statuses like `Ready for Tech`, `Testing`, `DVI updates`, `Awaiting tech`, `Servicing`, and `QC` are mapped toward Drew ownership
- Stable external-hold statuses such as `Waiting parts`, `Scheduled-Not Here`, `DVI Only-Not Here`, and `APACHE JOB` remain visible but calm in `P4`
- Missing RO linkage is treated as its own board alert
- Missing active tech clock-in on live production statuses is treated as a helper alert for advisor verification

### New Commands

- `python scripts/build_board_state.py`

### New Dashboard/API Path

- Added `/api/board-state`
- `/api/hermes-summary` now reads `board_state.json` and returns a first-pass operational summary based on current helper rules

### Immediate Next Work

1. Refine role-specific views for Mitch, Drew, and Preston from `board_state.json`
2. Add supportive “What do I do next?” board actions
3. Add explicit walkthrough / customer-contact / expectation-timer compliance checks
4. Add technician productivity and drift analytics once the proper technician metrics export is wired in

## Progress Update - May 18, 2026 - Board State Phase 2

- Tightened board-state status mapping for current live AutoFlow statuses such as:
  - `call_shop`
  - `parts`
  - `finished`
  - `unknown`
- Added a board-state-driven dashboard view that now reads `/api/board-state` directly instead of acting as a placeholder shell
- Added Board / Mitch / Drew / Preston helper views in the dashboard UI
- Added stronger helper cards for:
  - `Action Now`
  - `Incoming Soon`
  - `All Jobs`
  - `What Do I Do Next?`
- Added more explicit alerts for:
  - missing tech assignment on production-controlled work
  - status-mapping gaps
  - customer follow-up due
  - verify tech clock-in
- Hermes summary now reports:
  - P1 action pressure
  - P2 action gap
  - productivity watch
  - missing RO cleanup
  - unresolved intelligence gaps

## Progress Update - May 18, 2026 - Working Helper Actions

- The board helper cues are now interactive instead of display-only:
  - `☎ Communication`
  - `⏱ Productivity`
  - `🧠 Data`
- Clicking a helper cue now opens a job action modal with a mode-specific prompt.
- Added a lightweight board action log endpoint:
  - `POST /api/board-action`
- Added a lightweight Hermes question / feedback endpoint:
  - `POST /api/hermes-feedback`
- Added local runtime logs:
  - `state/board_actions.jsonl`
  - `state/hermes_feedback.jsonl`
- `Morning Briefing` now opens a visible modal instead of only replacing the Hermes summary area.
- Added an `Ask Hermes` control directly in the Hermes panel so the board can be used as a working helper surface.
- Saved communication / productivity / data actions now calm their matching helper cues on subsequent board refreshes by overlaying recent action-state evidence from:
  - `state/board_actions.jsonl`
- Added an `Afternoon Brief` endpoint and modal path for post-lunch rollover review.
- Analytics now include a first-pass shop support score plus communication/productivity/data clear counts instead of only raw tallies.

### Immediate Intent

- This is the first practical write-capable layer for the board.
- It does **not** write back into AutoFlow or Tekmetric yet.
- It gives the team a way to:
  - log customer updates
  - log productivity/floor checks
  - flag board/data issues
  - ask Hermes targeted next-step questions

## Progress Update - May 18, 2026 - Data Input / Training / Productivity Phase

- Added two new top-level support surfaces to keep the main board lean:
  - `Data Input`
  - `Training`
- `Data Input` is the board-facing replacement for a generic “fix-it” idea.
  - It groups source-data correction needs into cleaner buckets such as:
    - missing tech assignment
    - weak/missing customer concern
    - missing customer update
    - missing completed DVI
    - bad or unclear workflow status
    - missing RO linkage
- `Training` is now separated from raw correction work.
  - It is designed to teach what keeps getting missed over time.
  - It uses a coach/helpful tone first, then shifts firmer as repeated patterns stack up.
  - It is structured around:
    - Mitch
    - Drew
    - Preston
    - Technician
    - Overall Shop
- Analytics were reweighted around the user’s priority order:
  1. productivity
  2. customer communication misses
  3. jobs stuck too long
  4. repeated DVI quality issues
  5. support scores
- The board now raises explicit DVI/customer-concern quality signals instead of treating everything as one generic data issue.
- The bay-facing performance view now shows a friendlier front-of-house vs back-of-house score split for shop visibility.
- Modal behavior was tightened so action flows open centered, highlight the active mode more clearly, and are easier to use across mixed screen sizes.

## Progress Update - May 18, 2026 - Bay View / Printing / Tech Alias Refinement

- Adjusted board risk-light language to read more naturally for the team:
  - `Critical`
  - `Moderate`
  - `Good`
- Added cleaner briefing print behavior:
  - dedicated single-sheet print layout
  - white paper-friendly output instead of full dark board styling
  - note areas for advisor follow-up and tech questions
  - print support for both Morning Briefing and Afternoon Brief
- Expanded technician-name extraction and alias handling so the system can better recognize short AutoFlow/Tekmetric-style names such as:
  - `L Cervantes`
  - `Jonathan L`
  - `TC Charleston`
  - `Steve C`
  - plus shop-routing aliases like `Shop HitList` and `DI Testing`
- Added explanation sections to the Bay Performance board so the team can understand:
  - what each score means
  - what practical actions raise each score

## Progress Update - May 18, 2026 - Upstream Tech Evidence / Local Override Phase

- Confirmed that some live AutoFlow work orders do **not** expose a clean top-level technician field even when the DVI/work items clearly show who touched the job.
- Upgraded upstream extraction so technician evidence can now be pulled from richer DVI/work-order activity such as:
  - `completed_by`
  - `sms_user`
  - DVI/work item evidence
- Improved summary generation so the system can prefer `reason_vehicle_is_here` concern text over weak placeholders like bare status labels or irrelevant IDs.
- Added a tracked local roster file:
  - `config/employee_roster.json`
- The roster now distinguishes:
  - real people
  - routing buckets / holding buckets
  - suspended users kept for knowledge but excluded from live role matching
- `Shop HitList`, `DIAG TESTING`, and `Admin User` are now treated as routing buckets instead of real technicians.
- Added the first local board override layer:
  - lane override
  - owner override
  - technician override
  - summary override
- Added “Why the board put it here” evidence in the job modal so corrections can be made with clearer context.
- Started shifting user-facing assistant wording from `Hermes` toward `Callie` in the live dashboard UI.

## Progress Update - May 18, 2026 - Callie Response / Source Conflict Phase

- Strengthened the board’s live-source explanation layer so it can now show:
  - work-order source status
  - DVI source status
  - source-status conflicts when those disagree
- Improved AutoFlow merge evidence so board issues can be traced back to which upstream signal is winning.
- Tightened Callie response behavior in the modal:
  - stronger visible response window
  - clearer distinction between:
    - saving a note / local correction
    - sending a question to Callie
- Added a conflict-warning response path for local overrides.
  - If a user applies a board correction that conflicts with live AutoFlow evidence, the UI now warns that the source ticket likely needs to be fixed in AutoFlow too.
- This is the first step toward preventing “override it and hush it up” behavior by making the system explain what the source truth currently says.

### Git / Branch

- Active branch: `ai-build-stabilization`
- Latest checkpoint commit before this status update: `77cdc03`
- AI machine and GitHub are currently in sync
- Working tree should be checked before additional edits

### Confirmed Working Architecture

`AutoFlow webhook/API -> data/autoflow_events/autoflow_events.jsonl -> state/active_ros.json -> state/shop_state.json -> /api/jobs -> dashboard`

- Hermes reads and saves webhook evidence separately
- Hermes is not on the dashboard page-load path
- The local Rules + Evidence path is now the primary board data path

### What Is Working Now

#### Dashboard

- Flask dashboard runs on `127.0.0.1:5000`
- `/healthz` works
- `/api/jobs` works
- Dashboard reads `state/shop_state.json` first
- Dashboard does not call Hermes on page load
- Dashboard does not directly call live AutoFlow during normal page load when `shop_state.json` exists
- Manual `Refresh Jobs` button exists
- Dashboard auto-refreshes `/api/jobs` every 30 seconds using `window.setInterval(loadJobs, 30000)`
- Auto-refresh updates job data only and does not reload the full page

#### Webhook

- Flask webhook receiver runs on `127.0.0.1:5055`
- Public webhook URL is `https://autoflow-webhook.callahanautoaz.net/webhooks/autoflow`
- Public health URL is `https://autoflow-webhook.callahanautoaz.net/health`
- Cloudflare route is fixed and public POST now works
- Webhook appends events to `data/autoflow_events/autoflow_events.jsonl`
- Webhook now triggers:
  - `python scripts/build_active_ros_state.py`
  - `python scripts/build_shop_state.py`
- Confirmed webhook response fields:
  - `active_ros_rebuilt: true`
  - `shop_state_rebuilt: true`
  - `state_rebuild_failures: []`
  - `hermes_saved: true`

#### AutoFlow Enrichment

- `/api/v1/work_orders/{RO}` works for known valid ROs
- `/api/v1/dvi/{RO}` works for known valid ROs
- AutoFlow currently enriches known ROs successfully
- Confirmed real RO `13298` maps:
  - advisor: `Mitch Callahan`
  - customer: `Mitch Weber`
  - vehicle: `2024 RAM 3500 Laramie`
  - workflow_status: `finished`
  - summary/notes: `EIN 97000375`
  - priority: `P3`

#### Active RO State

- `scripts/build_active_ros_state.py` derives active ROs from webhook event evidence
- Runtime state files are ignored by Git:
  - `state/active_ros.json`
  - `state/shop_state.json`
- Current production filters exclude:
  - `TEST`
  - `DEMO`
  - `SAMPLE`
  - `RO-55555`
  - `55555`
  - numeric `99990` through `99999`
- `active_ros.json` now contains valid active ROs discovered from webhook evidence

#### Shop State

- `scripts/build_shop_state.py` builds normalized `state/shop_state.json`
- It uses `state/active_ros.json` as input
- It enriches valid ROs through AutoFlow
- One bad or invalid RO no longer poisons the whole state build
- Failed ROs can be recorded under `skipped_ros`
- It no longer falls back to 4 mock demo jobs when `active_ros` contains real IDs and one ID fails
- Normalized shop-state source is now `rules_evidence`

#### Hermes

- Hermes is connected to the webhook receiver
- Webhook tests confirmed `hermes_saved: true`
- Hermes should treat `state/shop_state.json` as canonical operational evidence
- Hermes remains advisory and analysis-only for now
- No customer messaging
- No AutoFlow or Tekmetric writebacks
- No uncontrolled automation

#### Cloudflare

- Dashboard Cloudflare route works
- Webhook Cloudflare route was fixed and public POST is working
- Cloudflare Zero Trust public hostname must route:
  - `autoflow-webhook.callahanautoaz.net -> http://127.0.0.1:5055`
- Correct webhook path is `/webhooks/autoflow`
- `GET /webhooks/autoflow` returns Method Not Allowed, which is expected because the endpoint is POST-only
- Local `config.yml` was not the controlling factor because `cloudflared` is running through the service-token setup

### Current Known Limits

- Full automatic "all active ROs" sync is not solved yet
- AutoFlow does not currently expose a confirmed authoritative list-all-open-work-orders endpoint
- Tested list-style endpoints returned `404`:
  - `/api/v1/work_orders`
  - `/api/v1/tickets`
  - `/api/v1/invoices`
  - `/api/v1/repair_orders`
  - `/api/v1/orders`
- `/api/v1/appointments` works, but current payload does not expose true shop RO/invoice values that can serve as authoritative discovery
- Webhook activity discovers active ROs event-by-event, not from a full shop snapshot
- `connectors/tekmetric.py` is still mock-only and does not provide live active/open RO discovery

### Immediate Technical Validation Still Needed

- Confirm a real AutoFlow live-RO status movement triggers the full loop:
  - webhook event received
  - `active_ros.json` rebuilt
  - `shop_state.json` rebuilt
  - `/api/jobs` updated
  - dashboard reflects the change within 30 seconds
- Once that is confirmed, document it as the first fully working real-time board loop

### Next Major Phase

- Focus next on the Operational Intelligence layer, not more UI work

Recommended sequence:

1. Stabilize the current webhook -> state -> dashboard loop.
2. Add a small `state/board_state.json` intelligence layer built from `shop_state.json`.
3. Use `board_state.json` to calculate:
   - stale jobs
   - waiting too long
   - advisor next action
   - technician next action
   - blockers
   - priority explanations
   - aging timers
   - handoff ownership
4. Keep Hermes advisory:
   - Observe -> Analyze -> Prioritize -> Present
5. Do not let Hermes write to AutoFlow, Tekmetric, or customers.

## Progress Update - May 16, 2026

## Progress Update - May 16, 2026 - Shop State Layer

- Added `scripts/build_active_ros_state.py` to derive active ROs from webhook events.
- Added `scripts/build_shop_state.py` to build normalized `state/shop_state.json`.
- Added `scripts/bootstrap_active_ros.py` to sync `active_ros.json` and `shop_state.json` in one step.
- Added `scripts/sync_active_appointments.py` to merge appointment-discovered AutoFlow ROs with webhook-derived active ROs.
- AutoFlow webhook intake now rebuilds `state/active_ros.json` and `state/shop_state.json` after accepted events.
- Confirmed live AutoFlow RO `13298` maps advisor, customer, vehicle, workflow status, notes, and priority.
- Updated `/api/jobs` to prefer local `state/shop_state.json` before live/mock fallback.
- `state/shop_state.json` is the canonical Rules/Evidence operational board-state file for both dashboard reads and future Hermes intelligence reads.
- Preserved Hermes separation: no Hermes/Ollama execution on dashboard page load.
- Dashboard now refreshes `/api/jobs` every 30 seconds without reloading the page.

### Current Data Flow

`AutoFlow webhook log → active_ros.json → shop_state.json → /api/jobs → dashboard`

- Stabilized the Flask dashboard and confirmed it works locally and through Cloudflare.
- Fixed dashboard repo-root import path so `connectors/autoflow.py` can load correctly.
- Connected `/api/jobs` to `fetch_autoflow_data([])` with mock fallback.
- Added normalized `/api/jobs` payload for frontend-safe rendering.
- Added first-pass frontend rendering from `/api/jobs`.
- Confirmed `/healthz` returns 200 OK.
- Confirmed `/api/jobs` returns 200 OK with 4 normalized jobs.
- Preserved Hermes separation: no Hermes/Ollama work runs on the main dashboard page load.
- No polling has been added yet.
- Added a Rules/Evidence active RO state layer sourced from `data/autoflow_events/autoflow_events.jsonl`.
- Added command to build active RO state: `python scripts/build_active_ros_state.py`.
- Added command to sync appointment-discovered active ROs: `python scripts/sync_active_appointments.py`.
- Added command to build normalized board state: `python scripts/build_shop_state.py`.
- Added command to bootstrap the synced local state: `python scripts/bootstrap_active_ros.py`.

### Next Priorities

1. Monitor Cloudflare stability and watch for recurring 524 behavior.
2. Validate real AutoFlow RO data path when live RO input is available.
3. Keep `/api/jobs` using `active_ros.json` when present and mock fallback when not.
---

## Project Goal

Build a **local-first, remote-accessible Advisor Command Board** for Callahan Auto that helps reduce operational chaos by providing:

- Clear P1–P4 priority visibility
- Advisor and Technician action queues
- Technician Load and Bay Utilization
- Hermes Intelligence layer for operational summaries and recommendations
- Secure remote access via Cloudflare Tunnel

---

## Current Tech Stack

| Component                    | Technology                          | Status      | Notes |
|-----------------------------|-------------------------------------|-------------|-------|
| Web Dashboard               | Flask (`dashboard/advisor_task_viewer.py`) | Active      | Port 5000 |
| Intelligence Layer          | Hermes + Ollama (Qwen2.5-coder:7b)     | Active      | Summary & recommendations |
| Webhook Receiver            | Flask (`webhooks/autoflow_webhook_receiver.py`) | Active | Port 5055 |
| Cloudflare Tunnel           | cloudflared (Windows Service)          | Active      | Remote access |
| Desktop Launchers           | PowerShell `.ps1` files                | Active      | Easy startup |
| Data Source                 | AutoFlow (Webhook + Connector)         | Partial     | Using mock data in some areas |

---

## Architecture Decisions

- **Separation of Concerns**:
  - **Rules + Evidence Layer**: Handles ownership, priority scoring, timing, and action queues.
  - **Hermes Layer**: Reads structured board data and provides summaries, explanations, and recommendations.
- Hermes should **read `state/shop_state.json` as the primary operational evidence file** once intelligence summaries are wired in.
- Hermes should **not** perform heavy data processing or direct calculations.
- **Stability first** — Performance and reliability (especially remote access) take priority over new features.
- Use desktop PowerShell launchers for reliable daily startup.

---

## Current Status (as of May 16, 2026)

- Remote dashboard is accessible via Cloudflare but **unstable** (frequent 524 Timeouts).
- Cloudflared service is installed but **unstable** (frequently starts/stops).
- Hermes works when Ollama is running, but page load performance needs improvement.
- P1–P4 structure exists but is still mostly placeholder.
- Desktop launchers are created and working.

---

## Known Issues

| Issue                    | Severity | Notes |
|--------------------------|----------|-------|
| Cloudflared instability  | High     | Main cause of 524 Timeouts |
| Dashboard page load time | High     | Triggers Cloudflare timeouts |
| Hermes connection errors | Medium   | Happens when Ollama is not running |
| Limited real AutoFlow data in UI | Medium | Still using mock data in some places |

---

## Next Priorities (In Order)

1. **Stabilize Remote Access** (Highest Priority)
   - Fix/reduce 524 Timeouts
   - Improve Cloudflared stability or configuration

2. **Improve Dashboard Performance**
   - Move heavy operations (especially Hermes) to background where possible
   - Make error handling more graceful

3. **Enhance P1–P4 Columns & Queues**
   - Pull real data from AutoFlow
   - Build Advisor Action Queue and Technician Action Queue
   - Add Technician Load and Bay Utilization

4. **Strengthen Hermes Layer**
   - Improve reliability when Ollama is running
   - Make summaries more actionable

---

## Key Files

| File Path                                      | Purpose                              | Notes |
|------------------------------------------------|--------------------------------------|-------|
| `dashboard/advisor_task_viewer.py`             | Main Flask dashboard                 | Core file |
| `hermes/intelligence/shop_intelligence_llm.py` | Hermes intelligence logic            | Summary generation |
| `connectors/autoflow.py`                       | AutoFlow data connector              | Data source |
| `webhooks/autoflow_webhook_receiver.py`        | Webhook receiver                     | Event intake |
| `PROJECT_STATUS.md`                            | Living project status document       | This file |

---

## Branch Strategy (Current)

- **Working Branch:** `ai-build-stabilization`
- All active development should happen on this branch until further notice.
- Major stable versions may be merged into `main` later.

---

## Rules for AI Assistants (Grok & Codex)

- Always work incrementally.
- Prioritize **stability and performance** before adding new features.
- When editing code, prefer providing the **full updated file**.
- Maintain separation between Rules/Evidence layer and Hermes.
- Reference this document and the GitHub branch when making decisions.
- Ask clarifying questions instead of making assumptions.

---

**This document should be updated regularly** as progress is made.
