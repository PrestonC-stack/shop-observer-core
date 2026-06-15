# API Coverage

Last Updated: June 15, 2026
Branch: ai-build-stabilization

This file documents the routes and external endpoints currently represented in the repository. It is documentation only.

## Local Flask Board App

Entrypoint: `dashboard/app.py`
Host/port: `127.0.0.1:8080`

| Route | Method | Handler | Notes |
| --- | --- | --- | --- |
| `/` | GET | `board()` | Original board UI from `dashboard/board_renderer.py`. |
| `/v2` | GET | `board_v2()` | AdviseMe Command Board renderer from `dashboard/board_v2.py`. |
| `/v2/hitlist` | GET | `hitlist_v2()` | Print-ready hit list from board state. |
| `/api/search` | GET | `api_search()` | Searches active jobs and `state/job_history` folder names. |
| `/healthz` | GET | `healthz()` | Board health check. |
| `/drew` | GET | `drew_board()` | Static Drew advisor board. |
| `/mitch` | GET | `mitch_board()` | Static Mitch advisor board. |
| `/api/jobs` | GET | `api_jobs()` | Raw shop state loader. |
| `/api/board-state` | GET | `api_board_state()` | Primary board JSON consumed by UIs. |
| `/api/confirmations` | GET | `api_confirmations()` | Reads `state/confirmations.jsonl`. |
| `/api/confirm-step` | POST | `api_confirm_step()` | Writes confirmation records. |
| `/api/override-job` | POST | `api_override_job()` | Writes manual override records. |
| `/api/board-action` | POST | `api_board_action()` | Writes board actions and optional overrides. |
| `/api/hermes-feedback` | POST | `api_hermes_feedback()` | Saves Callie/Hermes feedback and optional Ollama answer. |
| `/api/callie/insights` | GET | `api_callie_insights()` | Reads `data/callie_insights.json` if present. |
| `/api/callie/ask` | POST | `api_callie_ask()` | Deterministic board answer with optional Ollama fallback. |
| `/api/hermes-summary` | GET | `api_hermes_summary()` | Board summary payload from `dashboard/scoring.py`. |
| `/api/morning-briefing` | GET | `api_morning_briefing()` | JSON morning briefing. |
| `/api/afternoon-briefing` | GET | `api_afternoon_briefing()` | JSON afternoon briefing. |
| `/bay-performance` | GET | `bay_performance()` | Inline bay performance page. |
| `/dvi` | GET | `dvi_board()` | DVI review board. |
| `/dvi/packet/<ro>` | GET | `packet_page()` | Packet page and cache display. |
| `/dvi/packet/<ro>/regenerate` | POST | `regenerate_packet()` | Packet regeneration endpoint. |
| `/dvi/packet/<ro>/analyze-photos` | POST | `analyze_packet_photos()` | Claude vision photo analysis endpoint. |
| `/dvi/packet/<ro>/merge-findings` | POST | `merge_packet_findings()` | Merges photo summaries into packet cache. |
| `/sanity-check` | GET | `sanity_check()` | Printable sanity check report. |
| `/dvi/slip/<ro>` | GET | `dvi_slip()` | Serves generated rework slip HTML if present. |
| `/dvi/acknowledge/<ro>` | GET | `dvi_acknowledge()` | Marks DVI review acknowledged. |

## Local Webhook Receiver

Entrypoint: `webhooks/autoflow_webhook_receiver.py`
Host/port: `127.0.0.1:5055`

| Route | Method | Notes |
| --- | --- | --- |
| `/webhooks/autoflow` | POST | Accepts AutoFlow webhook JSON, logs full payload, updates transition/activity logs, triggers DVI handling, and rebuilds local state. |
| `/health` | GET | Receiver health check. |

## AutoFlow Endpoints

### Basic Auth Endpoints

Base used by connector/config: `AUTOFLOW_API_BASE_URL`
Base used by enrichment module: `https://callahanautomotive.autotext.me/api/v1`
Auth: Basic auth using `AUTOFLOW_API_KEY` and `AUTOFLOW_API_PASSWORD`.

| Endpoint | Used By | Behavior |
| --- | --- | --- |
| `GET /api/v1/work_orders/{ro}` or `GET /work_orders/{ro}` | `connectors/autoflow.py`, `scripts/autoflow_enrichment.py` | Work order details. Enrichment reads invoice, DVI items, parts arrival, labor quantity/sold hours, communication sent/viewed markers. |
| `GET /api/v1/dvi/{ro}` or `GET /dvi/{ro}` | `connectors/autoflow.py`, `core/cas/tekmetric_packet.py`, DVI/packet flows | DVI content, DVI categories/items, photos, notes, and reason-vehicle-is-here structures. |
| `GET /repair_order/{invoice}` | `scripts/autoflow_enrichment.py` | Repair order/authorization data using invoice from work order. Missing invoice skips this gracefully. |
| `GET /conversations?remote_ticket_id={ro}` | `scripts/autoflow_enrichment.py` | Conversation history keyed by RO number. 404 is treated as no conversation and not a fatal enrichment failure. |
| `GET /api/v1/appointments` | `scripts/sync_active_appointments.py` | Appointment sync utility. |

### Bearer Auth Inbox Endpoint

| Endpoint | Used By | Behavior |
| --- | --- | --- |
| `GET https://api.autoflow.com/api/v1/conversations?status=unread&limit=50` | `dashboard/board_v2.py` | Counts unread inbox conversations for the `/v2` sidebar badge. Timeout/failure returns count 0 and never breaks board rendering. |

## Anthropic Endpoints

Auth: `ANTHROPIC_API_KEY`

| Endpoint | Used By | Behavior |
| --- | --- | --- |
| `POST https://api.anthropic.com/v1/messages` | `core/cas/tekmetric_packet.py` | Generates packet JSON from DVI/review data using `claude-opus-4-6`, `max_tokens=8000`, timeout 150 seconds. |
| `POST https://api.anthropic.com/v1/messages` | `dashboard/packet_page.py` | Photo vision analysis and two-section synthesis for packet photo findings. |

## Local/Optional Services

| Service | Used By | Behavior |
| --- | --- | --- |
| Ollama CLI | `dashboard/app.py` | Optional Callie/Hermes response path. If unavailable, app returns deterministic fallback text. |
| Cloudflare tunnel | launch scripts | Exposes local board app publicly. No application route logic lives in Cloudflare config here. |

## Storage Side Effects By Endpoint

| Endpoint/Flow | Writes |
| --- | --- |
| `POST /webhooks/autoflow` | `data/autoflow_events/autoflow_events.jsonl`, `data/status_transitions/transitions.jsonl`, `data/ro_activity/{ro}.jsonl`, plus rebuilt `state/active_ros.json`, `state/shop_state.json`, `state/board_state.json`. |
| DVI trigger | `state/dvi_reviews/{ro}.json`, optional `state/dvi_reviews/rework_slip_{ro}.html`, timeline entries. |
| `POST /api/confirm-step` | `state/confirmations.jsonl`. |
| `POST /api/override-job` | `state/board_overrides.jsonl`. |
| `POST /api/board-action` | `state/board_actions.jsonl`, optionally `state/board_overrides.jsonl`. |
| `POST /api/hermes-feedback` | `state/hermes_feedback.jsonl`. |
| Packet generation/regeneration | `state/dvi_reviews/{ro}_packet.json`, `state/dvi_reviews/packet_{ro}.json`, `state/job_history/{ro}/packet_{timestamp}.json`, `data/api_costs/api_costs.jsonl`, error log on parse failure. |
| Photo merge | Updates packet cache with merged photo findings. |
| Enrichment script | `state/enrichment/{ro}.json`. |

## Known Coverage Gaps And Notes

- No route exists for `/preston` even though some UI navigation references it.
- No dedicated Tech Sheet route exists; the v2 Tech Sheet button points to `/sanity-check`.
- Sidebar modules for Customers, Parts, Alerts, Schedule, KPI Targets, Accounting, Callie, and Settings are placeholders in `/v2`.
- `connectors/tekmetric.py` is not a live TechMetric write integration.
- There are no customer-message send routes in the board app.
- There are no AutoFlow write routes in the board app.
- There are no TechMetric write routes in the board app.
