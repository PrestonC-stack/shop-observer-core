# Callahan AI - System State

Last Updated: August 12, 2026  
Branch: ai-build-stabilization  
Codex workspace: `C:\CALLAHAN\AI Workspace\shop-observer-core`  
Runtime workspace: `C:\AI-RUNTIME\shop-observer-core`  
Public board URL: `https://tasks.callahanautoaz.net`

This is the repo truth map. It reflects what exists now, not a roadmap. It should be updated whenever routes, runtime ownership, packet/DVI flow, or scoring behavior changes.

## Production Incident - AutoFlow Webhook Outage (2026-08-01 to 2026-08-12)

The AutoFlow webhook receiver silently stopped processing events for roughly 11 days. No AutoFlow status updates, DVI completions, or new RO data were captured during the outage window unless they were later reconstructed manually.

Root causes found in sequence:

- `bridge.process_autoflow_event()` in the Hermes integration had no timeout, causing every webhook request to hang indefinitely. Fixed by wrapping the call in a background thread with a 3-second timeout via `_process_autoflow_event_with_timeout` in commit `86edc7d`. This protection was briefly dropped in a later commit and restored in commit `99a484a`.
- `webhooks/autoflow_webhook_receiver.py` line ~409 crashed on startup with `UnicodeEncodeError` when launched with redirected or non-console output, due to an emoji character in a print statement. Fixed by removing the emoji in commit `4a7a470`.
- A second identical Unicode crash existed in `C:\AI-RUNTIME\hermes\orchestration\hermes_webhook_bridge.py`. This file is outside the `shop-observer-core` repo and is not visible to or editable by Codex. It required a manual fix directly on the runtime machine, was not committed to any repo, and must be reapplied manually if the machine is rebuilt unless the file is brought under version control.
- The webhook handler previously ran the full state rebuild chain (`active_ros` -> `shop_state` -> `board_state`) synchronously inside the request, taking 60+ seconds and risking AutoFlow-side timeouts or retries. Fixed by moving the rebuild chain to a background thread after the response is sent in commit `86edc7d`.

Known follow-ups still open:

- RO `13684`, and any other RO created or updated during the 2026-08-01 to 2026-08-12 outage window, was never backfilled. Its history is permanently missing unless manually reconstructed from TekMetric/AutoFlow directly.
- `C:\AI-RUNTIME\hermes\orchestration\hermes_webhook_bridge.py` is not under version control anywhere Codex can access. Bring it into a repo Codex can see, or document it clearly as a manual-edit-only runtime file.
- No scheduled task exists for `scripts/build_active_ros_state.py`, `scripts/build_shop_state.py`, or `scripts/build_board_state.py`. They only run via webhook trigger or manual invocation, so if the webhook pipeline breaks silently again, the board can go stale with no automatic recovery.
- Basic file logging was added to the webhook receiver during this incident at `logs/autoflow_webhook_receiver.log`; this made final diagnosis possible. Extend the same logging pattern to `scripts/build_shop_state.py`, `scripts/build_active_ros_state.py`, and `scripts/build_board_state.py`.
- `scripts/health_check.py` and `scripts/register_scheduled_tasks.ps1` currently exist as untracked files. Confirm whether they were completed and commit them, or note them as incomplete.

## Production Entry Points

- Live board app: `dashboard/app.py`, started as `python dashboard\app.py` on `127.0.0.1:8080`.
- Live webhook receiver: `webhooks/autoflow_webhook_receiver.py`, started as `python webhooks\autoflow_webhook_receiver.py` on `127.0.0.1:5055`.
- Live public access: Cloudflare tunnel `shop-tasks`, started by runtime launcher/autostart scripts.
- Manual launcher: `Start-Callahan-AI.ps1` and `Start-Callahan-AI.bat` from repo root; both target `C:\AI-RUNTIME\shop-observer-core`.
- Autostart installer: `install_autostart.ps1`; registers hidden Windows Task Scheduler tasks for board, webhook, and tunnel.

Superseded or non-production entrypoints:

- `_archive/dashboard/advisor_task_viewer.py` is a legacy monolithic Flask board. It currently contains unresolved conflict markers and is not the live production entry.
- `_archive/dashboard/autoflow_live_dashboard.py` is an older simple standalone dashboard on port 5000 using mock/live connector experiments; it is not referenced by the current launcher or `dashboard/app.py`.
- `_archive/dashboard/autoflow_live_dashboard.backup.py` is a backup/older standalone dashboard that wrote `state/active_shop_state.json`.
- `observer.py` is a separate observer/Callie endpoint experiment and is not launched by the current production scripts.
- `start_advisor_system.bat` and `dashboard/1-Start-Dashboard.ps1` still point at `advisor_task_viewer.py`; treat them as older launchers unless deliberately revived.

## Live Routes

All board routes below are defined in `dashboard/app.py`.

| Route | Method | Responsibility |
| --- | --- | --- |
| `/` | GET | Legacy/main command board HTML from `dashboard/board_renderer.py`. |
| `/v2` | GET | AdviseMe Command Board v3 from `dashboard/board_v2.py`. |
| `/v2/hitlist` | GET | Print-ready daily hit list from current board state. |
| `/api/search` | GET | Searches active board jobs and `state/job_history` folder names. |
| `/healthz` | GET | Board app health check. |
| `/drew` | GET | Serves standalone `dashboard/drew_board.html`. |
| `/mitch` | GET | Serves standalone `dashboard/mitch_board.html`. |
| `/api/jobs` | GET | Returns raw `state/shop_state.json` payload through `board_loader`. |
| `/api/board-state` | GET | Returns `_load_board_state()` JSON for board UIs. |
| `/api/confirmations` | GET | Reads server-side advisor confirmations. |
| `/api/confirm-step` | POST | Writes advisor confirmations to `state/confirmations.jsonl`. |
| `/api/override-job` | POST | Writes manual job override records to `state/board_overrides.jsonl`. |
| `/api/board-action` | POST | Writes board actions and optional overrides. |
| `/api/hermes-feedback` | POST | Saves Callie/Hermes feedback and optional Ollama answer. |
| `/api/callie/insights` | GET | Reads optional `data/callie_insights.json`. |
| `/api/callie/ask` | POST | Deterministic board answer with optional Ollama fallback. |
| `/api/hermes-summary` | GET | Summary payload from `dashboard/scoring.py`. |
| `/api/morning-briefing` | GET | JSON morning briefing from current board state. |
| `/api/afternoon-briefing` | GET | JSON afternoon briefing from current board state. |
| `/bay-performance` | GET | Inline bay performance/support score page. |
| `/dvi` | GET | DVI workflow board from `dashboard/dvi_page.py`. |
| `/dvi/packet/<ro>` | GET | TekMetric packet page from `dashboard/packet_page.py`. |
| `/dvi/packet/<ro>/regenerate` | POST | Regenerates packet from latest DVI; does not auto-run on stale detection. |
| `/dvi/packet/<ro>/analyze-photos` | POST | Runs selected DVI photos through Claude vision analysis. |
| `/dvi/packet/<ro>/merge-findings` | POST | Merges confirmed photo findings into packet cache. |
| `/sanity-check` | GET | Printable Morning Sanity Check report. |
| `/dvi/slip/<ro>` | GET | Serves generated DVI rework slip HTML if present. |
| `/dvi/acknowledge/<ro>` | GET | Marks DVI review advisor-acknowledged and logs timeline event. |

Webhook routes in `webhooks/autoflow_webhook_receiver.py`:

| Route | Method | Responsibility |
| --- | --- | --- |
| `/webhooks/autoflow` | POST | Accepts AutoFlow JSON, logs full payload, writes transition/activity records, runs Hermes bridge, triggers DVI handler, rebuilds local state. |
| `/health` | GET | Webhook receiver health check. |

Other route-bearing files:

- `_archive/dashboard/advisor_task_viewer.py` defines many duplicate routes but is legacy and currently contains conflict markers.
- `_archive/dashboard/autoflow_live_dashboard.py` defines `/` only for its standalone app.
- `observer.py` defines `/api/callie/ask` and `/api/callie/insights` for a separate observer app, not the live board app.

## Dashboard Modules

- `dashboard/app.py`: Live Flask app entrypoint and route registry.
- `dashboard/board_loader.py`: Loads `state/board_state.json`, applies action/override state, timestamp fallbacks, DVI review injection, activity feeds, and safe fallback payloads.
- `dashboard/board_renderer.py`: Legacy/main `/` board HTML template, deterministic Callie helpers, and original board UI behavior.
- `dashboard/board_v2.py`: AdviseMe Command Board v3 renderer, hit list renderer, search helper, unread inbox count, packet metadata decoration, packet-stale board tagging, vehicle silhouettes, drawer UI, analytics, alert bar, and demo-mode JS.
- `dashboard/dvi_page.py`: DVI workflow board with Needs Attention, In Progress, and Completed Today sections. Applies red/amber CSS pulse to unacknowledged `REWORK_REQUIRED` and `REVIEW`.
- `dashboard/packet_page.py`: Packet page renderer, packet cache wrapper, regenerate handler, photo extraction, photo download, photo analysis, synthesis, merge-findings, stale packet comparison display.
- `dashboard/sanity_check.py`: Printable Morning Sanity Check report from `_load_board_state()`.
- `dashboard/confirmations.py`: Server-side advisor confirmation JSONL storage.
- `dashboard/overrides.py`: Manual job reassignment/override JSONL storage.
- `dashboard/scoring.py`: Display-time Hermes/bay summary helpers and `transitions.jsonl` elapsed-time formatter.
- `dashboard/drew_board.html`: Standalone Drew queue board.
- `dashboard/mitch_board.html`: Standalone Mitch queue board.

## Core/CAS Modules

- `core/cas/dvi_schema.py`: Dataclasses/enums for DVI reviews, flags, statuses, trigger events, and timeline entries.
- `core/cas/dvi_gate.py`: Deterministic DVI rule engine. It has no AI call and no write-side API call.
- `core/cas/dvi_trigger.py`: Webhook-triggered DVI runner. Delays 15 seconds, retries AutoFlow DVI pulls, runs the gate, saves reviews/slips/timeline, and logs unknown event types.
- `core/cas/rework_slip.py`: Printable text/HTML DVI rework slip generator.
- `core/cas/tekmetric_packet.py`: Claude-backed TekMetric packet generator, packet cache compatibility writer, permanent job-history packet writer, API cost logging, response parse hardening, Arizona timestamp display, DVI snapshot hashing, and stale DVI comparison helpers.
- `core/state/state_manager.py`: Saves/loads DVIReview JSON files under `state/dvi_reviews`.
- `core/timeline/job_timeline.py`: Per-RO JSONL timeline logger under `state/job_timeline`.

## Connectors, Scripts, And Pipelines

- `connectors/autoflow.py`: Read-only AutoFlow connector using `.env` credentials and mock fallback; merges work order + DVI into raw records.
- `connectors/tekmetric.py`: Local mock TekMetric connector placeholder; no live TechMetric write integration.
- `normalizers/shop_state_normalizer.py`: Normalizes source payloads into shop-state style records for older observer flow.
- `observer-rules/shop_rules.py`: Rule catalog for older observer/nudge flow.
- `callie_engine.py`: Deterministic insight generator that reads `state/board_state.json` and writes optional `data/callie_insights.json`; referenced by UI text but not imported by live app.
- `scripts/build_active_ros_state.py`: Builds `state/active_ros.json` from AutoFlow webhook/event evidence.
- `scripts/build_shop_state.py`: Builds `state/shop_state.json` from active ROs using `connectors/autoflow.py`.
- `scripts/build_board_state.py`: Builds `state/board_state.json` from shop state and `scripts/scoring_engine.py`. It still contains older helper functions, but current scoring is delegated through `score_job`.
- `scripts/scoring_engine.py`: Current scoring model used by `build_board_state`.
- `scripts/autoflow_enrichment.py`: Pull/cache enrichment for work orders, repair orders, and conversations into `state/enrichment/{ro}.json`.
- `scripts/build_advisor_game_plan.py`: Rebuilt by webhook receiver; advisor task/game-plan artifact builder.
- `scripts/sync_active_appointments.py`: Appointment sync utility.
- `scripts/check_system_health.py`, `scripts/watchdog_check.py`, `scripts/watchdog_repair.py`, `scripts/restart_tunnel.py`: Runtime support/watchdog utilities.

## DVI Gate Flow

The DVI gate is deterministic and config-driven.

Inputs:

- AutoFlow DVI payload from `GET /api/v1/dvi/{ro}`.
- DVI thresholds/rules in `config/cas_rules/dvi_gate_rules.yaml`.
- Concern completeness/contradiction config in `config/concern_checklists.json`.

Flow:

1. `webhooks/autoflow_webhook_receiver.py` receives an AutoFlow event and calls `core.cas.dvi_trigger.handle_webhook_event()`.
2. `dvi_trigger` always logs unknown event types and runs its older status transition tracker for `status_update`.
3. For `dvi_signoff` or `dvi_signoff_update`, `dvi_trigger` starts a background thread.
4. The thread waits 15 seconds, retries DVI pull up to 3 times, optionally pulls work order data, then calls `run_dvi_gate()`.
5. `run_dvi_gate()` flattens DVI items, applies deterministic checks, adds concern-completeness/contradiction flags, finalizes status, and returns a `DVIReview`.
6. Reviews are saved to `state/dvi_reviews/{ro}.json`; rework slips are saved if needed; timeline events are appended.

Statuses:

- `PASS`: no flags; cleared for estimate.
- `REVIEW`: important/informational flags only; advisor review required.
- `REWORK_REQUIRED`: at least one critical flag; not cleared for estimate.
- `PENDING`: schema-supported pending status.
- `ERROR`: schema-supported error status.

Deterministic checks:

- Concern item missing photo.
- Concern item blank/too-short note.
- Vague concern note.
- Missing measurement on configured brake/tire/measurement categories.
- Leak concern without location/severity/photo.
- Safety item not inspected.
- Primary complaint not clearly addressed.
- Concern completeness checklists for `ac_blowing_warm`, `brake_noise`, and `no_start`.
- Narrow contradiction detection when a component is marked OK/green but the concern describes failure on that same configured component.

## Packet Builder And Stale DVI Logic

Active files:

- `core/cas/tekmetric_packet.py`
- `dashboard/packet_page.py`
- `dashboard/board_v2.py`

Packet generation flow:

1. `/dvi/packet/<ro>` loads primary cache `state/dvi_reviews/{ro}_packet.json` if present.
2. If no cache exists, packet generation requires `state/dvi_reviews/{ro}.json`.
3. Regenerate POST forces a fresh AutoFlow DVI pull and rebuilds the packet.
4. Claude packet generation uses Anthropic messages API with model `claude-opus-4-6`, `max_tokens=8000`, and 150-second timeout.
5. Python owns the final `generated_at`, `dvi_pulled_at`, `dvi_item_count`, DVI snapshot hash, normalized DVI snapshot, and snapshot captured timestamp.
6. Compatibility packet JSON is written to `state/dvi_reviews/packet_{ro}.json`.
7. Page cache wrapper is written to `state/dvi_reviews/{ro}_packet.json`.
8. Permanent packet history is written to `state/job_history/{ro}/packet_{timestamp}.json`.
9. API cost logs append to `data/api_costs/api_costs.jsonl`; parse/debug failures append to `data/api_costs/packet_errors.jsonl`.

Packet categories:

- `CONCERN`
- `SAFETY`
- `MAINTENANCE`
- `POSSIBLE ADD-ON`

Photo analysis:

- Photo extraction checks multiple AutoFlow DVI locations, including `reason_vehicle_is_here`, `dvis.dvi_category.dvi_items.item_images`, `item_picture`, recommendations, notes, services, flat items, inspections, and hunter results.
- `motovisuals.com` stock illustrations are filtered out.
- DVI Photo Analysis: Fixed S3 fetch failure - browser-like headers (`User-Agent`, `Referer`, `Accept`) now sent with all TekMetric photo URL requests. Non-200 responses, non-image content types, and empty responses are rejected before Claude. Bad photos are skipped and logged. If all selected photos fail, `/analyze-photos` returns JSON 422 with readable browser alert. Implemented in `dashboard/packet_page.py`.
- S3 photo downloads use browser-like headers and full-resolution fallback.
- Claude vision analyzes individual photos.
- A synthesis call creates structured RO notes/job findings for merge.
- Merge updates the packet cache; it does not write to AutoFlow or TechMetric.

Stale packet detection:

- Packet generation stores a SHA-256 hash of normalized DVI content plus the normalized snapshot used to build the packet.
- `compare_packet_to_current_dvi()` re-reads the current AutoFlow DVI, recomputes the normalized hash, and returns `changed`, hashes, and a simple human-readable diff for added/removed/edited concerns/items/notes/photos/statuses.
- `dashboard/packet_page.py` refreshes stale state when the packet page is loaded and stores `packet_stale` in `{ro}_packet.json`.
- If stale, the packet page shows a red banner and diff. It does not auto-regenerate.
- `dashboard/board_v2.py` reads cached stale state and decorates that RO as `rework returned / re-review`, assigns `waiting_on` to `Needs Review`, sets `priority_lane` to `P2C`, and surfaces the diff through packet summary data.

## Scoring Model

Current scorer: `scripts/scoring_engine.py`.

Inputs:

- `state/shop_state.json`
- `data/status_transitions/transitions.jsonl`
- `data/ro_activity/{ro}.jsonl`
- `state/enrichment/{ro}.json`
- DVI status fields injected through board state/loaders.

P1 gate:

- DVI rework unacknowledged.
- Ready to collect: status `finished` or `ready` and no outbound contact in RO activity since entering that status. If no RO activity exists, this trigger does not mark P1.
- Customer waiting on us: latest RO activity event is inbound (`inbound_message` or `ro_approval`).

Not standalone P1 triggers:

- Finished age alone.
- Waiting approval age alone.
- 24-hour staleness alone.

Lane mapping:

- Need Immediate Action: only P1 gate passers.
- Ready to Close: `finished`, `ready`, `advisor finalize ro` when not caught by P1 gate.
- Waiting / Customer: `waiting approval`, `call_shop`, `advisor estimate`.
- Waiting / Other: external hold/status cleanup states such as `aaa`, `unknown`, scheduled-not-here, DVI-only-not-here, Needs Review.
- In Progress: servicing, inspecting, testing, DVI updates, ready/awaiting tech, technical advisement/overview, QC, checkin, drop-off/stage.
- Parts / Inventory: waiting/ordering parts and enrichment records with outstanding parts.

Priority lanes:

- `P1`: P1 gate pass.
- `P2A`: checked in/no information captured.
- `P2B`: awaiting tech, DVI, or dispatch movement.
- `P2C`: advisor/customer/review state is stuck.
- `P3`: active and controlled.
- `P4`: legitimate external hold.

Staleness:

- `hours_in_status > 24` adds a stale flag/badge and sorts up within the existing lane.
- Staleness does not create P1 by itself.

Parts enrichment:

- Outstanding parts route to Parts/Inventory with reason like `parts X/Y in, N outstanding`.
- Outstanding parts plus stale status adds attention reason but does not blanket-promote to P1.
- All parts arrived and not already in closeout/QC creates a positive movement prompt and routes toward dispatch/tech movement.

Progress:

- `progress_percent` is an estimated proxy, not true labor completion.
- It blends workflow status stage with parts-arrival ratio when parts data exists.

## Data And State On Disk

Tracked `data/` layout currently in this workspace:

- `data/.gitkeep`
- `data/board_state.json` - tracked sample/older artifact, not the production board state path.

Tracked `state/` layout currently in this workspace:

- `state/active_shop_state.json` - tracked old/legacy artifact.

Runtime/gitignored state expected during operation:

- `state/active_ros.json`: active RO list from `scripts/build_active_ros_state.py`.
- `state/shop_state.json`: normalized active shop jobs from `scripts/build_shop_state.py`.
- `state/board_state.json`: scored board payload from `scripts/build_board_state.py`.
- `state/confirmations.jsonl`: advisor confirmation log.
- `state/board_overrides.jsonl`: manual override/reassignment log.
- `state/board_actions.jsonl`: board action log.
- `state/hermes_feedback.jsonl`: Callie/Hermes interaction log.
- `state/dvi_reviews/{ro}.json`: DVI gate result.
- `state/dvi_reviews/{ro}_packet.json`: primary packet page cache.
- `state/dvi_reviews/packet_{ro}.json`: compatibility packet JSON.
- `state/dvi_reviews/rework_slip_{ro}.html`: generated DVI rework slip.
- `state/job_history/{ro}/packet_{timestamp}.json`: permanent packet history.
- `state/enrichment/{ro}.json`: AutoFlow enrichment cache.
- `state/job_timeline/{ro}.jsonl`: per-RO DVI/timeline events.
- `data/autoflow_events/autoflow_events.jsonl`: full webhook payload event log.
- `data/status_transitions/transitions.jsonl`: transition/activity records.
- `data/ro_activity/{ro}.jsonl`: per-RO activity stream.
- `data/api_costs/api_costs.jsonl`: packet/photo API cost log.
- `data/api_costs/packet_errors.jsonl`: packet parse/debug errors.
- `data/unknown_events/unknown_events.jsonl`: unknown webhook event discovery.
- `data/callie_insights.json`: optional Callie insights output.

Config:

- `.env`: local credentials; gitignored and must not be committed.
- `config/cas_rules/dvi_gate_rules.yaml`: deterministic DVI gate thresholds and terms.
- `config/concern_checklists.json`: concern completeness and narrow contradiction config.
- `config/employee_roster.json`: active/inactive people and routing buckets.
- `config/source_precedence.json`: source trust/precedence settings.

## External APIs And Credentials

- AutoFlow work order/DVI APIs use Basic auth from `AUTOFLOW_API_KEY` and `AUTOFLOW_API_PASSWORD`.
- `connectors/autoflow.py` reads base URL from `AUTOFLOW_API_BASE_URL`.
- `scripts/autoflow_enrichment.py` currently uses fixed base `https://callahanautomotive.autotext.me/api/v1`.
- `/v2` unread inbox helper uses Bearer `AUTOFLOW_API_KEY` against `https://api.autoflow.com/api/v1/conversations`.
- Anthropic packet/photo analysis uses `ANTHROPIC_API_KEY`.
- Ollama is optional; board routes fall back to deterministic text if it is unavailable.
- Cloudflare tunnel details live in local runtime scripts/config, not application route logic.

## Known Constraints

- TekMetric photo URLs (S3): require browser-like headers for server-side download - `User-Agent`, `Referer` (`tekmetric.com`), and image `Accept` types. Without these, S3 can return an HTML redirect instead of image bytes, causing downstream Claude/JSON handling failures.

## Parked Or Disabled Features

- `/preston` is linked from some UI code but no route exists in `dashboard/app.py`.
- `/analytics` is linked from `/v2` sidebar as a possible route, but no route exists in `dashboard/app.py`.
- `/v2` sidebar modules Customers, Parts, Alerts, Schedule, KPI Targets, Accounting, Callie, and Settings are placeholder overlays.
- Tech Sheet button in `/v2` points to `/sanity-check`; there is no dedicated tech-sheet route.
- `connectors/tekmetric.py` is mock-only and does not write to TechMetric.
- There are no customer-message send routes.
- There are no AutoFlow write routes.
- There are no TechMetric write routes.

## Candidate Dead / Duplicate Files

Do not delete these automatically. Preston should review them deliberately.

- `_archive/dashboard/advisor_task_viewer.py`: legacy monolithic board duplicate; contains unresolved conflict markers and is superseded by `dashboard/app.py` plus modular files.
- `_archive/dashboard/advisor_task_viewer.py.bak.20260525_160432`: backup of legacy monolith.
- `_archive/dashboard/advisor_task_viewer_backup_2026-05-12.py`: older HTTP-server style backup.
- `_archive/dashboard/autoflow_live_dashboard.py`: older standalone port-5000 dashboard experiment; not referenced by current launcher/app.
- `_archive/dashboard/autoflow_live_dashboard.backup.py`: backup of older active-shop-state dashboard.
- `_archive/patch_add_advisor_routes.py`: one-time route patch script for the old monolith; no longer needed for live app route wiring.
- `callie_engine.ai-machine-backup.py`: backup copy of `callie_engine.py`.
- `drafts/draft_nudges.py`: draft/experimental nudge builder, not imported by live app.
- `start_advisor_system.bat`: old launcher still starts `dashboard\advisor_task_viewer.py`.
- `dashboard/1-Start-Dashboard.ps1`: old launcher still starts `advisor_task_viewer.py`.
- `dashboard/3-Start-Ollama.ps1`: optional/old helper; current board does not require Ollama to start.
- `dashboard/4-Start-All.ps1`: older dashboard/webhook/tunnel launcher in dashboard folder; root `Start-Callahan-AI.ps1` is the current launcher.
- `docs/AUTOFLOW-LIVE-DASHBOARD.backup.md`: backup documentation.
- `data/board_state.json`: tracked sample/old artifact; production board state is `state/board_state.json`.
- `state/active_shop_state.json`: tracked legacy state artifact from older live-dashboard path.
- `inputs/mock_autoflow_techflow_jobs.json`, `inputs/mock_tekmetric_parts_activity.json`, `inputs/sample_input.json`: mock/sample data, useful for tests but not production runtime state.

Files that appear imported/referenced nowhere in current live code scan:

- `_archive/dashboard/autoflow_live_dashboard.py`
- `_archive/dashboard/autoflow_live_dashboard.backup.py`
- `_archive/dashboard/advisor_task_viewer_backup_2026-05-12.py`

## LAUNCHER CLEANUP - PENDING PRESTON CONFIRMATION

Do not remove or repoint these until Preston confirms which shortcut is still in use:

- `dashboard/1-Start-Dashboard.ps1` still starts `advisor_task_viewer.py`, which is now archived under `_archive/dashboard/advisor_task_viewer.py`.
- `start_advisor_system.bat` still starts `dashboard\advisor_task_viewer.py`, which is now archived under `_archive/dashboard/advisor_task_viewer.py`.

Current production launchers continue to be `Start-Callahan-AI.ps1`, `Start-Callahan-AI.bat`, and `install_autostart.ps1`, which target `dashboard\app.py`.
- `drafts/draft_nudges.py`
- `connectors/tekmetric.py`
- `normalizers/shop_state_normalizer.py` outside `observer.py`
- `observer-rules/shop_rules.py` outside older observer flow
- `callie_engine.py` is not imported by live app but is referenced in UI/help text as a manual insight generator.

## Discrepancies Found

- `_archive/dashboard/advisor_task_viewer.py` has unresolved merge conflict markers, so any script pointing at the old `dashboard/advisor_task_viewer.py` location is unsafe for production.
- `start_advisor_system.bat` and `dashboard/1-Start-Dashboard.ps1` still launch the legacy monolith, while current production launchers use `dashboard/app.py`.
- `scripts/build_board_state.py` contains older lane/progress helper logic alongside delegation to `scripts.scoring_engine.score_job`, which can confuse future readers.
- `core/cas/dvi_trigger.py` has an older `track_status_transition()` that only records `status_update`, while `webhooks/autoflow_webhook_receiver.py` now writes richer transition/activity records for every event before calling the trigger.
- Packet cache naming is intentionally mixed: `{ro}_packet.json` is the primary page cache, while `packet_{ro}.json` is the compatibility packet JSON used by some board checks.
- `.gitignore` contains malformed-looking entry `state/active_shop_state.jsoncloudflared.exe`.
- `API_COVERAGE.md` mostly matches current routes, but some handler names in the table are descriptive/old labels rather than exact function names from `dashboard/app.py`.
- `README.md` still describes the older local-first observer architecture and does not reflect the current dashboard/DVI/packet production runtime.

## How To Start The System

Manual runtime start:

1. Double-click `Start-Callahan-AI.bat`, or run `Start-Callahan-AI.ps1`.
2. Blue board window starts `python dashboard\app.py`.
3. Green webhook window starts `python webhooks\autoflow_webhook_receiver.py`.
4. Purple tunnel window starts Cloudflare tunnel `shop-tasks`.

Autostart:

1. Run `install_autostart.ps1` once as Administrator from `C:\AI-RUNTIME\shop-observer-core`.
2. It registers `CallahanAI-Board`, `CallahanAI-Webhook`, and `CallahanAI-Tunnel`.

Git/runtime flow:

1. Commit and push from `C:\CALLAHAN\AI Workspace\shop-observer-core`.
2. Pull on runtime machine from `C:\AI-RUNTIME\shop-observer-core`.
3. Restart local windows/tasks if Python route/render/runtime files changed.

## GitHub

- Repo: `https://github.com/PrestonC-stack/shop-observer-core`
- Branch: `ai-build-stabilization`
