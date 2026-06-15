# Callahan AI - System State

Last Updated: June 15, 2026
Branch: ai-build-stabilization
Codex workspace: C:\CALLAHAN\AI Workspace\shop-observer-core
Runtime workspace: C:\AI-RUNTIME\shop-observer-core
Public board URL: https://tasks.callahanautoaz.net

This file is the repo truth map. It describes what exists in the codebase now. It is not a roadmap and it should not preserve stale sprint assumptions.

## What Is Working

- Flask board app runs from `dashboard/app.py` on `127.0.0.1:8080`.
- AutoFlow webhook receiver runs from `webhooks/autoflow_webhook_receiver.py` on `127.0.0.1:5055`.
- Cloudflare tunnel exposes the board at `https://tasks.callahanautoaz.net`.
- Active board state is loaded from `state/board_state.json` through `dashboard/board_loader.py`.
- The original board at `/` renders from `dashboard/board_renderer.py`.
- The command-center board at `/v2` renders from `dashboard/board_v2.py`.
- Drew and Mitch personal boards are standalone HTML files served at `/drew` and `/mitch`.
- DVI gate results are rendered at `/dvi`.
- Packet builder pages are served at `/dvi/packet/<ro>`.
- Packet regeneration, photo analysis, and finding merge POST routes are wired in `dashboard/app.py`.
- Webhook events are accepted at `POST /webhooks/autoflow`, logged, sent through Hermes, passed to the DVI trigger, and then rebuild local state.
- Webhook activity is stored globally in `data/status_transitions/transitions.jsonl` and per RO in `data/ro_activity/{ro}.jsonl`.
- Enrichment cache module exists at `scripts/autoflow_enrichment.py` and writes `state/enrichment/{ro}.json`.
- Scoring model in `scripts/scoring_engine.py` uses gated P1 logic, parts enrichment, status normalization, and a progress proxy.

## Active Pages And Routes

### Board App Routes

All routes below are defined in `dashboard/app.py`.

| Route | Method | Responsibility |
| --- | --- | --- |
| `/` | GET | Main legacy board HTML from `dashboard/board_renderer.py`. |
| `/v2` | GET | AdviseMe Command Board v3 from `dashboard/board_v2.py`. |
| `/v2/hitlist` | GET | Print-ready daily hit list from current board state. |
| `/api/search` | GET | Search active board jobs and `state/job_history` folders. |
| `/healthz` | GET | Board app health check. |
| `/drew` | GET | Serves `dashboard/drew_board.html`. |
| `/mitch` | GET | Serves `dashboard/mitch_board.html`. |
| `/api/jobs` | GET | Returns raw shop jobs through `_load_jobs_from_autoflow()`. |
| `/api/board-state` | GET | Returns `_load_board_state()` JSON for all board UIs. |
| `/api/confirmations` | GET | Returns server-side advisor confirmations. |
| `/api/confirm-step` | POST | Appends advisor confirmation to `state/confirmations.jsonl`. |
| `/api/override-job` | POST | Appends manual reassignment override to `state/board_overrides.jsonl`. |
| `/api/board-action` | POST | Appends board action to `state/board_actions.jsonl`; can also append an override. |
| `/api/hermes-feedback` | POST | Saves a Callie/Hermes style interaction to `state/hermes_feedback.jsonl`; uses Ollama if available. |
| `/api/callie/insights` | GET | Loads `data/callie_insights.json` if present. |
| `/api/callie/ask` | POST | Deterministic board answer with optional Ollama fallback. |
| `/api/hermes-summary` | GET | Returns summary payload from `dashboard/scoring.py`. |
| `/api/morning-briefing` | GET | Returns JSON morning briefing from current board state. |
| `/api/afternoon-briefing` | GET | Returns JSON afternoon briefing from current board state. |
| `/bay-performance` | GET | Inline bay performance dashboard. |
| `/dvi` | GET | DVI review board from `dashboard/dvi_page.py`. |
| `/dvi/packet/<ro>` | GET | Packet builder page from `dashboard/packet_page.py`. |
| `/dvi/packet/<ro>/regenerate` | POST | Forces packet regeneration with requester tracking. |
| `/dvi/packet/<ro>/analyze-photos` | POST | Runs selected DVI photos through Claude vision analysis. |
| `/dvi/packet/<ro>/merge-findings` | POST | Merges photo findings into packet cache. |
| `/sanity-check` | GET | Printable morning sanity check report. |
| `/dvi/slip/<ro>` | GET | Serves generated rework slip HTML if present. |
| `/dvi/acknowledge/<ro>` | GET | Marks a DVI review advisor-acknowledged and appends timeline event. |

### Webhook Receiver Routes

Defined in `webhooks/autoflow_webhook_receiver.py`.

| Route | Method | Responsibility |
| --- | --- | --- |
| `/webhooks/autoflow` | POST | Accepts AutoFlow JSON webhook payloads, logs full payload, updates transitions/activity, triggers DVI handler, and rebuilds local board state. |
| `/health` | GET | Receiver health check. |

## Module Responsibilities

### Dashboard Modules

- `dashboard/app.py`: Flask app entrypoint and route registry. No template ownership except small inline API/debug pages.
- `dashboard/board_loader.py`: Loads `state/board_state.json`, applies local action state, overrides, timestamp fallbacks, DVI review status injection, and recent activity feeds.
- `dashboard/board_renderer.py`: Original board HTML template and briefing button area for `/`.
- `dashboard/board_v2.py`: AdviseMe Command Board v3 renderer, v2 hit list renderer, search helper, unread inbox count helper, packet metadata injection, demo mode JS, vehicle silhouettes, drawer UI, columns, analytics, alert bar.
- `dashboard/dvi_page.py`: DVI review board with Needs Attention, In Progress, and Completed Today sections.
- `dashboard/packet_page.py`: Packet page renderer plus regenerate, photo extraction, photo analysis, synthesis, and merge endpoints.
- `dashboard/sanity_check.py`: Printable Morning Sanity Check report from current board state.
- `dashboard/confirmations.py`: Server-side confirmation JSONL storage.
- `dashboard/overrides.py`: Manual advisor reassignment JSONL storage.
- `dashboard/scoring.py`: Display-time summary helpers and transition-based elapsed-time display for Hermes/bay metrics.
- `dashboard/drew_board.html`: Standalone Drew queue board.
- `dashboard/mitch_board.html`: Standalone Mitch queue board.

### Core CAS Modules

- `core/cas/dvi_schema.py`: Dataclasses and enums for DVI reviews, flags, severities, and final status calculation.
- `core/cas/dvi_gate.py`: Deterministic DVI rule engine. No AI and no API call inside the evaluator.
- `core/cas/dvi_trigger.py`: Webhook-triggered DVI evaluation flow, transition tracking, unknown event logging, and delayed DVI gate execution.
- `core/cas/rework_slip.py`: Printable rework slip generation for DVI rework.
- `core/cas/tekmetric_packet.py`: DVI packet generation with Claude, packet cache, packet history, cost logging, parse hardening, and Arizona display timestamp formatting.

### Connector And Pipeline Modules

- `connectors/autoflow.py`: AutoFlow JSON connector using `.env`, Basic auth by default, live work order/DVI fetches, and mock fallback.
- `connectors/tekmetric.py`: TekMetric connector placeholder/skeleton.
- `scripts/build_active_ros_state.py`: Builds `state/active_ros.json` from webhook/event evidence.
- `scripts/build_shop_state.py`: Builds `state/shop_state.json` by fetching AutoFlow work order and DVI data for active ROs.
- `scripts/build_board_state.py`: Builds `state/board_state.json`; it currently wraps `scripts/scoring_engine.py` but still contains older helper logic.
- `scripts/scoring_engine.py`: Current main scoring model used to score each job.
- `scripts/autoflow_enrichment.py`: Pull/cache enrichment layer for work orders, repair orders, and conversations.
- `scripts/build_advisor_game_plan.py`: Rebuilt by webhook receiver; produces advisor task/game-plan artifacts.
- `scripts/sync_active_appointments.py`: Appointment sync utility.
- `scripts/check_system_health.py`, `scripts/watchdog_check.py`, `scripts/watchdog_repair.py`, `scripts/restart_tunnel.py`: Runtime support/watchdog scripts.

### State And Timeline Modules

- `core/state/state_manager.py`: Shared state manager utility.
- `core/timeline/job_timeline.py`: Job timeline utility.
- `normalizers/shop_state_normalizer.py`: Normalization helper for shop state style payloads.

## DVI Gate Logic

The DVI gate is deterministic and local.

Inputs:

- AutoFlow DVI data fetched by `fetch_dvi_from_autoflow()` in `core/cas/tekmetric_packet.py` or passed from webhook-triggered flow.
- Rule thresholds in `config/cas_rules/dvi_gate_rules.yaml`.

Outputs:

- `state/dvi_reviews/{ro}.json`
- Optional rework slip HTML in `state/dvi_reviews/rework_slip_{ro}.html`
- Timeline entries under `state/job_timeline`

Statuses:

- `PASS`: No flags. `cleared_for_estimate` is true.
- `REVIEW`: Important or informational flags exist, but no critical flag. Advisor review required before estimate/customer presentation.
- `REWORK_REQUIRED`: At least one critical flag exists. Tech correction is required and the job is not cleared for estimate.
- `PENDING`: Schema-supported status for work not completed yet.
- `ERROR`: Schema-supported status for gate failure/error conditions.

Primary rule classes:

- Missing photo on a concern item can create critical rework.
- Blank or too-short note can create critical rework on customer concern evidence.
- Vague notes can create review flags.
- Brakes, tires, and battery categories can require measurements.
- Leak items require location/severity detail.
- Safety categories and safety items are always evaluated.
- Customer concern coverage is checked against the DVI evidence.

The `/dvi` page groups unacknowledged `REWORK_REQUIRED` and `REVIEW` items into Needs Attention. `REWORK_REQUIRED` cards pulse red and `REVIEW` cards pulse amber until acknowledged.

## Packet Builder Flow

Active files:

- Page and API handlers: `dashboard/packet_page.py`
- Packet generation engine: `core/cas/tekmetric_packet.py`

Flow:

1. `/dvi/packet/<ro>` loads packet cache if present.
2. Cache path is primarily `state/dvi_reviews/{ro}_packet.json`.
3. Generation also writes compatibility cache `state/dvi_reviews/packet_{ro}.json`.
4. If no cache exists, packet generation requires a DVI review at `state/dvi_reviews/{ro}.json`.
5. Regenerate route can force a fresh AutoFlow DVI pull and rebuild the packet.
6. Claude packet call uses Anthropic messages API with `claude-opus-4-6`, `max_tokens=8000`, and a 150 second timeout.
7. Packet JSON gets Python-owned `generated_at` set at generation time.
8. Permanent packet history is saved to `state/job_history/{ro}/packet_{timestamp}.json`.
9. API cost events append to `data/api_costs/api_costs.jsonl`.
10. Parse failures append to `data/api_costs/packet_errors.jsonl`.

Packet tiers/categories:

- `CONCERN`: Customer concern or diagnosis-driven work.
- `SAFETY`: Safety-critical work.
- `MAINTENANCE`: Maintenance and condition-based recommendations.
- `POSSIBLE ADD-ON`: Lower-certainty or optional opportunities.

Photo analysis:

- `/dvi/packet/<ro>/analyze-photos` accepts selected photo URLs and requester.
- Photos are extracted from multiple AutoFlow DVI structures, including `reason_vehicle_is_here`, `dvis.dvi_category.dvi_items.item_images`, `item_picture`, recommendations, notes, services, items, inspections, and hunter results.
- `motovisuals.com` stock illustrations are filtered out.
- Server-side S3 downloads use browser-like headers and full-resolution fallback.
- Claude vision analyzes individual photos, then a synthesis call produces `technical_summary` and `customer_explanation`.
- `/dvi/packet/<ro>/merge-findings` merges confirmed summaries into the packet cache.

## Scoring Model

Current scoring owner: `scripts/scoring_engine.py`.

Inputs:

- `state/shop_state.json`
- `data/status_transitions/transitions.jsonl`
- `data/ro_activity/{ro}.jsonl`
- `state/enrichment/{ro}.json`
- `state/dvi_reviews/{ro}.json`

Important field names:

- RO id: `ro`
- Status: `workflow_status`
- Advisor/owner routing: `waiting_on`
- Tech display: `technician`
- DVI status: `dvi_review_status`
- Parts enrichment: `summary.parts_total`, `summary.parts_arrived`, `summary.parts_outstanding`, `summary.sold_labor_hours`

P1 gate:

- DVI rework unacknowledged.
- Ready to collect: `workflow_status` in `finished` or `ready` and there is no outbound contact in `ro_activity` since the RO entered that status. If no activity exists, it does not become P1 from this trigger.
- Customer waiting on us: latest `ro_activity` event is inbound (`inbound_message` or `ro_approval`).

Removed as standalone P1 triggers:

- Finished age alone.
- Waiting approval age alone.
- 24-hour staleness alone.

Lane mapping:

- Need Immediate Action: only P1 gate-passers.
- Ready to Close: `finished`, `ready`, `advisor finalize ro` when not caught by the P1 gate.
- Waiting / Customer: `waiting approval`, `call_shop`, `advisor estimate`.
- Waiting / Other: `external hold`, `aaa`, `unknown`, `scheduled-not here`, `dvi only-not here`, `Needs Review`, and external holds.
- In Progress: `servicing`, `inspecting`, `testing`, `dvi updates`, `ready for tech`, `awaiting tech`, `technical advisement`, `technical overview`, `k_mech_complete`, `checkin`, `qc`, `advisor qc review`, `drop off/tow-in`, `online/stage`.
- Parts / Inventory: `waiting parts`, `ordering parts`, and parts enrichment where outstanding parts exist.

Priority lanes:

- `P1`: P1 gate pass.
- `P2A`: checked in/no info captured style state.
- `P2B`: awaiting tech, DVI, or dispatch movement.
- `P2C`: advisor/customer state is stuck.
- `P3`: active and controlled.
- `P4`: legitimate external hold.

Staleness:

- `hours_in_status > 24` sets stale flags/badges and sorts up within the existing lane.
- Staleness does not create P1 by itself.

Parts enrichment:

- Outstanding parts route to Parts/Inventory with reason like `parts X/Y in, N outstanding`.
- Outstanding parts plus stale status adds attention reason, but does not blanket-promote to P1.
- All parts arrived and not already in closeout/QC creates a positive movement prompt and routes toward dispatch/tech movement.

Progress:

- `progress_percent` is now a proxy, not true labor completion.
- It blends workflow stage and parts arrival when parts data exists.
- It is clamped, rounded, and labeled as estimated.

## Data Stored On Disk

### Runtime State

- `state/active_ros.json`: active RO list created by `scripts/build_active_ros_state.py`.
- `state/shop_state.json`: normalized active shop jobs created by `scripts/build_shop_state.py`.
- `state/board_state.json`: scored board payload created by `scripts/build_board_state.py`.
- `state/confirmations.jsonl`: advisor confirmation log.
- `state/board_overrides.jsonl`: manual override/reassignment log.
- `state/board_actions.jsonl`: board action log.
- `state/hermes_feedback.jsonl`: Callie/Hermes interaction log.
- `state/dvi_reviews/{ro}.json`: DVI gate result.
- `state/dvi_reviews/{ro}_packet.json`: primary packet cache.
- `state/dvi_reviews/packet_{ro}.json`: compatibility packet cache used by parts of `/v2`.
- `state/dvi_reviews/rework_slip_{ro}.html`: generated DVI rework slips.
- `state/job_history/{ro}/packet_{timestamp}.json`: permanent packet history.
- `state/enrichment/{ro}.json`: cached enrichment raw responses and summaries.
- `state/job_timeline`: timeline storage used by DVI trigger/gate flow.

### Data Logs

- `data/autoflow_events/autoflow_events.jsonl`: full webhook payload event log.
- `data/status_transitions/transitions.jsonl`: status/activity transition records.
- `data/ro_activity/{ro}.jsonl`: per-RO activity stream.
- `data/api_costs/api_costs.jsonl`: packet and cache cost log.
- `data/api_costs/packet_errors.jsonl`: Claude response parse/debug errors.
- `data/unknown_events`: unknown webhook/event captures.
- `data/callie_insights.json`: optional insights file loaded by `/api/callie/insights`.

### Config

- `.env`: local credentials; gitignored and must not be committed.
- `config/cas_rules/dvi_gate_rules.yaml`: DVI gate thresholds and rule terms.
- `config/employee_roster.json`: active/inactive advisor, tech, owner, accounting, and routing bucket roster.
- `config/source_precedence.json`: source trust/precedence settings.

## External APIs And Credentials

- AutoFlow work order/DVI APIs use Basic auth from `AUTOFLOW_API_KEY` and `AUTOFLOW_API_PASSWORD`.
- Default connector base comes from `AUTOFLOW_API_BASE_URL`; enrichment currently uses `https://callahanautomotive.autotext.me/api/v1`.
- `/v2` unread inbox helper uses Bearer `AUTOFLOW_API_KEY` against `https://api.autoflow.com/api/v1/conversations`.
- Anthropic packet and photo analysis calls use `ANTHROPIC_API_KEY`.
- Ollama is optional for local Callie/Hermes responses; failure falls back to deterministic text.
- Cloudflare tunnel uses local cert/config on the runtime machine.

## Parked Or Disabled Features

- `dashboard/advisor_task_viewer.py`: old monolithic board app. It is still present but has a syntax issue at line 1 in the current scan and should be treated as legacy/parked, not production.
- `dashboard/advisor_task_viewer.py.bak.*` and `dashboard/advisor_task_viewer_backup_2026-05-12.py`: backups.
- `dashboard/autoflow_live_dashboard.py` and `.backup.py`: older standalone dashboard experiments.
- `callie_engine.ai-machine-backup.py`: backup copy.
- `patch_add_advisor_routes.py`: one-time historical patch helper.
- `drafts/draft_nudges.py`: draft/experimental.
- `inputs/mock_autoflow_techflow_jobs.json`, `inputs/mock_tekmetric_parts_activity.json`, `inputs/sample_input.json`: mock/sample input.
- `data/board_state.json` and `state/active_shop_state.json`: tracked sample/old state artifacts; production uses `state/board_state.json` and `state/shop_state.json`.
- `/preston` is linked from some UI code but no route exists in `dashboard/app.py`.
- Several `/v2` sidebar tabs are placeholder overlays: Customers, Parts, Alerts, Schedule, KPI Targets, Accounting, Callie, Settings. Some related data exists, but those tabs are not full modules.
- Tech Sheet button currently routes to `/sanity-check`; it is not a separate tech sheet module.
- `connectors/tekmetric.py` is not a live write integration.

## Discrepancies Found In Current Files

- The previous `SYSTEM_STATE.md` said stale age, finished age, and waiting-approval age created P1 by themselves. Current `scripts/scoring_engine.py` no longer does that.
- `scripts/build_board_state.py` still contains older lane/progress helper logic even though it imports and uses `scripts.scoring_engine.score_job`; this is a potential source of confusion.
- `dashboard/advisor_task_viewer.py` appears legacy and syntactically broken in the current scan.
- `dashboard/board_v2.py` and `scripts/build_board_state.py` were flagged by AST scanning for a BOM/non-printable first character. They are still present in repo; no logic was changed here.
- `.gitignore` contains a malformed-looking line: `state/active_shop_state.jsoncloudflared.exe`.
- The roster file marks Johnathan Leithoff active, while older docs/sprint notes described a similarly spelled Johnathan Leithtoff as inactive. Treat roster as the current config until corrected deliberately.
- Packet cache naming is mixed: primary packet code uses `{ro}_packet.json`, while `/v2` packet-built checks also look for `packet_{ro}.json`. Packet generation currently writes both forms.

## How To Start The System

Manual start:

1. Double-click `Start-Callahan-AI.bat`, or run `Start-Callahan-AI.ps1`.
2. Board window starts `python dashboard\app.py`.
3. Webhook window starts `python webhooks\autoflow_webhook_receiver.py`.
4. Tunnel window starts Cloudflare tunnel `shop-tasks`.

Runtime pull flow:

1. Commit and push from `C:\CALLAHAN\AI Workspace\shop-observer-core`.
2. Pull on runtime machine from `C:\AI-RUNTIME\shop-observer-core`.
3. Restart services if Python files or launch scripts changed.

## GitHub

- Repo: https://github.com/PrestonC-stack/shop-observer-core
- Branch: `ai-build-stabilization`
