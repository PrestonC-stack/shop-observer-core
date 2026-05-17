# Callahan AI - Shop Command Board

**Last Updated:** May 16, 2026  
**Current Branch:** `ai-build-stabilization`  
**Repo:** https://github.com/PrestonC-stack/shop-observer-core.git
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
