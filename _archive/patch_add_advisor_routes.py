r"""
patch_add_advisor_routes.py
Run this ONCE from C:\AI-RUNTIME\shop-observer-core to add Drew and Mitch routes.
Usage: python patch_add_advisor_routes.py
"""
import os
import shutil
from datetime import datetime

TARGET = os.path.join('dashboard', 'advisor_task_viewer.py')
DREW_FILE = os.path.join('dashboard', 'drew_board.html')
MITCH_FILE = os.path.join('dashboard', 'mitch_board.html')

# ── Safety check ─────────────────────────────────────────────────
if not os.path.exists(TARGET):
    print(f"ERROR: {TARGET} not found. Run from C:\\AI-RUNTIME\\shop-observer-core")
    exit(1)

if not os.path.exists(DREW_FILE):
    print(f"ERROR: {DREW_FILE} not found. Copy drew_board.html to dashboard/ first.")
    exit(1)

if not os.path.exists(MITCH_FILE):
    print(f"ERROR: {MITCH_FILE} not found. Copy mitch_board.html to dashboard/ first.")
    exit(1)

# ── Backup ───────────────────────────────────────────────────────
backup = TARGET + '.bak.' + datetime.now().strftime('%Y%m%d_%H%M%S')
shutil.copy2(TARGET, backup)
print(f"Backup created: {backup}")

# ── Read file ────────────────────────────────────────────────────
with open(TARGET, 'r', encoding='utf-8') as f:
    content = f.read()

# ── Check if already patched ─────────────────────────────────────
if '/drew' in content and 'drew_board.html' in content:
    print("Routes already exist — no changes needed.")
    exit(0)

# ── Build the new routes ──────────────────────────────────────────
NEW_ROUTES = '''

@app.route("/drew")
def drew_board():
    """Drew personal workflow queue."""
    try:
        from flask import send_from_directory
        return send_from_directory(
            os.path.join(os.path.dirname(__file__)),
            "drew_board.html"
        )
    except Exception as e:
        return f"Drew board not found: {e}", 404


@app.route("/mitch")
def mitch_board():
    """Mitch personal workflow queue."""
    try:
        from flask import send_from_directory
        return send_from_directory(
            os.path.join(os.path.dirname(__file__)),
            "mitch_board.html"
        )
    except Exception as e:
        return f"Mitch board not found: {e}", 404

'''

# ── Find injection point (after the /healthz route) ──────────────
INJECT_AFTER = '@app.route("/healthz")'
if INJECT_AFTER not in content:
    # Fallback: inject before the main route
    INJECT_AFTER = '@app.route("/")'

idx = content.find(INJECT_AFTER)
if idx == -1:
    print("ERROR: Could not find injection point in file.")
    exit(1)

# Find the end of that route function (next @app.route)
next_route = content.find('@app.route', idx + 10)
if next_route == -1:
    print("ERROR: Could not find next route after injection point.")
    exit(1)

# Inject our new routes before the next existing route
content = content[:next_route] + NEW_ROUTES + content[next_route:]

# ── Also make sure 'os' is imported ──────────────────────────────
if 'import os' not in content:
    content = 'import os\n' + content
    print("Added 'import os'")

# ── Write patched file ────────────────────────────────────────────
with open(TARGET, 'w', encoding='utf-8') as f:
    f.write(content)

print(f"SUCCESS: Drew and Mitch routes added to {TARGET}")
print("")
print("Routes added:")
print("  /drew  -> dashboard/drew_board.html")
print("  /mitch -> dashboard/mitch_board.html")
print("")
print("Next steps:")
print("  1. Restart the board: python dashboard\\advisor_task_viewer.py")
print("  2. Visit https://tasks.callahanautoaz.net/drew")
print("  3. Visit https://tasks.callahanautoaz.net/mitch")
