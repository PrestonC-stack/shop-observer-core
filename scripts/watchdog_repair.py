from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
HEALTH_SCRIPT = ROOT / "scripts" / "check_system_health.py"
HEALTH_FILE = ROOT / "outputs" / "system_health.md"
START_SCRIPT = ROOT / "start_advisor_system.bat"
TUNNEL_SCRIPT = ROOT / "scripts" / "restart_tunnel.py"

def main():
    subprocess.run([sys.executable, str(HEALTH_SCRIPT)], cwd=str(ROOT), check=False)

    health = HEALTH_FILE.read_text(encoding="utf-8") if HEALTH_FILE.exists() else ""

    if "SYSTEM ONLINE" in health:
        print("System healthy — no action")
        return

    if "Public Scoreboard" in health or "tasks.callahanautoaz.net" in health:
        print("Public tunnel appears unhealthy — restarting tunnel")
        subprocess.Popen([sys.executable, str(TUNNEL_SCRIPT)], cwd=str(ROOT))
        return

    print("System unhealthy — restarting full advisor system")
    subprocess.Popen(str(START_SCRIPT), cwd=str(ROOT))

if __name__ == "__main__":
    main()