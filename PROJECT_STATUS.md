# Callahan AI - Shop Command Board

**Last Updated:** May 16, 2026  
**Current Branch:** `ai-build-stabilization`  
**Repo:** https://github.com/PrestonC-stack/shop-observer-core.git

## Checkpoint - May 16, 2026 - Live Webhook State Loop

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
