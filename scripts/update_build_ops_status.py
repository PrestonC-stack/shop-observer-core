from pathlib import Path
from datetime import datetime, timezone
import json

ROOT = Path(__file__).resolve().parents[1]

HANDOFF = ROOT / "handoffs" / "current-handoff.md"
TASK_QUEUE = ROOT / "automation" / "task-queue.json"
OUT = ROOT / "outputs" / "build_ops_status.md"

def read_text(path):
    return path.read_text(encoding="utf-8") if path.exists() else "Missing."

def read_json(path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"error": "Could not parse JSON"}

def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)

    tasks = read_json(TASK_QUEUE)
    handoff = read_text(HANDOFF)

    active = tasks.get("active", [])
    queued = tasks.get("queued", [])
    completed = tasks.get("completed", [])

    report = f"""# AI Build Ops Status

Generated: {datetime.now(timezone.utc).isoformat()}

## Current System State

- Repo: shop-observer-core
- Branch: ai-build-stabilization
- Source of Truth: GitHub
- Runtime Machine: AI MACHINE
- Current Phase: Control Layer / Status Tracking

## Active Tasks

{format_tasks(active)}

## Queued Tasks

{format_tasks(queued)}

## Completed Tasks

{format_tasks(completed)}

## Current Handoff

{handoff}

## Next Recommended Step

Add real queued tasks for:
1. Advisor Game Plan improvement
2. Build Ops fallback workflow
3. OpenClaw execution loop
4. Hermes continuity loop

## Do Not Touch

- TechMetric integration
- Customer-facing automation
- Secrets / .env
- Production branch main
"""

    OUT.write_text(report, encoding="utf-8")
    print(f"Created: {OUT}")

def format_tasks(items):
    if not items:
        return "None."
    lines = []
    for i, item in enumerate(items, 1):
        if isinstance(item, dict):
            lines.append(f"{i}. {item.get('task', item)}")
        else:
            lines.append(f"{i}. {item}")
    return "\n".join(lines)

if __name__ == "__main__":
    main()