from datetime import datetime, timezone
from pathlib import Path
import socket
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "system_health.md"

CHECKS = [
    ("Advisor Viewer Local", "http://127.0.0.1:8080/board"),
    ("Public Scoreboard", "https://tasks.callahanautoaz.net/board"),
    ("Drew Board", "https://tasks.callahanautoaz.net/drew"),
    ("Mitch Board", "https://tasks.callahanautoaz.net/mitch"),
]

PORTS = [
    ("Advisor Viewer Port 8080", "127.0.0.1", 8080),
]

def check_url(url, attempts=3):
    for _ in range(attempts):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 ShopObserverHealthCheck/1.0",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
            with urllib.request.urlopen(request, timeout=15) as response:
                if response.status < 500:
                    return True
        except Exception:
            time.sleep(2)
    return False

def check_port(host, port):
    try:
        with socket.create_connection((host, port), timeout=5):
            return True
    except Exception:
        return False

def main():
    lines = [
        "# Shop Observer System Health",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Port Checks",
    ]

    overall_ok = True

    for name, host, port in PORTS:
        ok = check_port(host, port)
        overall_ok = overall_ok and ok
        lines.append(f"- {'OK' if ok else 'FAIL'} {name}")

    lines.append("")
    lines.append("## URL Checks")

    for name, url in CHECKS:
        ok = check_url(url)
        overall_ok = overall_ok and ok
        lines.append(f"- {'OK' if ok else 'FAIL'} {name}: {url}")

    lines.append("")
    lines.append("## Overall Status")
    lines.append("SYSTEM ONLINE" if overall_ok else "SYSTEM NEEDS ATTENTION")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")

    print(f"Created: {OUT}")

if __name__ == "__main__":
    main()