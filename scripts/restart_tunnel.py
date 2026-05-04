from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
CLOUDFLARED = ROOT / "cloudflared.exe"

def main():
    subprocess.Popen(
        [str(CLOUDFLARED), "tunnel", "run", "shop-tasks"],
        cwd=str(ROOT),
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
    time.sleep(2)
    print("Cloudflare tunnel restart requested.")

if __name__ == "__main__":
    main()
