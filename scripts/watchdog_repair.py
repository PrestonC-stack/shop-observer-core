from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
HEALTH_FILE = ROOT / "outputs" / "system_health.md"
START_SCRIPT = ROOT / "start_advisor_system.bat"

def main():
    if not HEALTH_FILE.exists():
        print("Health file missing — restarting system")
        subprocess.Popen(str(START_SCRIPT))
        return

    health = HEALTH_FILE.read_text(encoding="utf-8")

    if "SYSTEM ONLINE" in health:
        print("System healthy — no action")
    else:
        print("System unhealthy — restarting")
        subprocess.Popen(str(START_SCRIPT))

if __name__ == "__main__":
    main()