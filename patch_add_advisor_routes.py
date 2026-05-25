from pathlib import Path


TARGET = Path(__file__).resolve().parent / "dashboard" / "advisor_task_viewer.py"
ROUTES = '''

@app.route("/drew")
def drew_board():
    from flask import send_from_directory
    import os
    return send_from_directory(os.path.dirname(__file__), "drew_board.html")


@app.route("/mitch")
def mitch_board():
    from flask import send_from_directory
    import os
    return send_from_directory(os.path.dirname(__file__), "mitch_board.html")
'''


def main():
    text = TARGET.read_text(encoding="utf-8")
    if '@app.route("/drew")' in text and '@app.route("/mitch")' in text:
        print("Advisor routes already present; no changes made.")
        return

    marker = '@app.route("/api/jobs")'
    if marker not in text:
        raise SystemExit("Could not find /api/jobs marker after /healthz route.")

    TARGET.write_text(text.replace(marker, ROUTES + "\n" + marker, 1), encoding="utf-8")
    print("Added /drew and /mitch advisor board routes.")


if __name__ == "__main__":
    main()
