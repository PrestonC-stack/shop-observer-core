# Callahan AI — System State
Last Updated: 2026-05-27

## What Is Working
- Board live at https://tasks.callahanautoaz.net (port 8080)
- Drew board at /drew, Mitch board at /mitch
- AutoFlow webhook live on port 5055
- Webhook fires -> board rebuilds automatically
- 22 active jobs currently tracked
- Real workflow_status values: call_shop, parts, ready, servicing, unknown, waiting_approval
- Jobs split by waiting_on: Drew, Mitch, External Hold, Preston

## File Structure
- dashboard/app.py - Flask app initialization, routes, and port 8080 runner
- dashboard/advisor_task_viewer.py - compatibility runner that imports dashboard/app.py
- dashboard/board_loader.py - board state loading, overrides, action-state application, timestamp fallbacks, recounts
- dashboard/board_renderer.py - main board HTML template, Callie/Hermes prompt and response helpers, briefing helpers
- dashboard/scoring.py - Hermes summary scoring and bay performance metric helpers
- dashboard/confirmations.py - server-side confirmation logging to state/confirmations.jsonl
- dashboard/overrides.py - manual advisor job reassignment logging to state/board_overrides.jsonl
- dashboard/drew_board.html - standalone Drew workflow queue
- dashboard/mitch_board.html - standalone Mitch workflow queue
- connectors/autoflow.py - AutoFlow API connector
- webhooks/autoflow_webhook_receiver.py - webhook receiver on port 5055
- scripts/build_board_state.py - rebuilds board from shop state
- scripts/build_shop_state.py - builds shop state from active ROs
- state/board_state.json - live board data (gitignored)
- state/shop_state.json - live shop data (gitignored)

## What Is Not Working / Known Issues
- Timestamps can be incomplete when status_updated_at is null; board_loader now falls back to recent webhook timestamps or board generated_at when available
- Task Scheduler auto-start not triggering on reboot reliably
- Manual job reassignment added in this refactor and should be validated live after pull

## Credentials Location
- .env file at repo root (gitignored, never commit)
- Cloudflare cert: C:\Users\CallahanAi\.cloudflared\cert.pem

## How To Start The System
- Double-click Start-Callahan-AI.bat on desktop
- Or right-click Start-Callahan-AI.ps1 -> Run with PowerShell
- Three windows open: Blue (board), Green (webhook), Purple (tunnel)

## GitHub
- Repo: https://github.com/PrestonC-stack/shop-observer-core
- Branch: ai-build-stabilization
