from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
HEALTH_SCRIPT = ROOT / "scripts" / "check_system_health.py"
HEALTH_FILE = ROOT / "outputs" / "system_health.md"
OUT = ROOT / "outputs" / "watchdog_status.md"

def main():
    subprocess.run([sys.executable, str(HEALTH_SCRIPT)], cwd=str(ROOT), check=False)

    health = HEALTH_FILE.read_text(encoding="utf-8") if HEALTH_FILE.exists() else ""

    status = "OK" if "SYSTEM ONLINE" in health else "NEEDS ATTENTION"

    report = f"""# Shop Observer Watchdog Status
Generated: {datetime.now(timezone.utc).isoformat()}

## Status
{status}

## Source
{HEALTH_FILE}

## Recommended Action
{"No action needed." if status == "OK" else "Run start_advisor_system.bat or restart the AI machine."}
"""

    OUT.write_text(report, encoding="utf-8")
    print(f"Created: {OUT}")

if __name__ == "__main__":
    main()