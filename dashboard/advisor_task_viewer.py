from http.server import BaseHTTPRequestHandler, HTTPServer
import html
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]

TASK_FILE = ROOT / "outputs" / "advisor_tasks.json"
ACTIVITY_LOG = ROOT / "outputs" / "advisor_activity_log.jsonl"

TASK_FILES = {
    "Drew": ROOT / "outputs" / "tasks_drew.json",
    "Mitch": ROOT / "outputs" / "tasks_mitch.json",
    "Preston": ROOT / "outputs" / "tasks_preston.json",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def append_activity(event: dict) -> None:
    event["logged_at"] = utc_now()
    ACTIVITY_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ACTIVITY_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")


def parse_dt(value: str):
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def human_duration(start_value: str) -> str:
    start = parse_dt(start_value)
    if not start:
        return "Unknown"

    total_minutes = int((datetime.now(timezone.utc) - start).total_seconds() / 60)

    if total_minutes < 60:
        return f"{total_minutes} min"

    hours = total_minutes // 60
    minutes = total_minutes % 60

    if hours < 24:
        return f"{hours} hr {minutes} min"

    days = hours // 24
    rem_hours = hours % 24
    return f"{days} day {rem_hours} hr"


def short_time(value: str) -> str:
    dt = parse_dt(value)
    if not dt:
        return "Unknown"
    return dt.astimezone().strftime("%m/%d %I:%M %p")


def active_tasks(tasks: list[dict]) -> list[dict]:
    return [
        task for task in tasks
        if task.get("status_tracking") != "completed"
    ]


def write_owner_feeds(tasks: list[dict]) -> None:
    feeds = {owner: [] for owner in TASK_FILES}

    for task in active_tasks(tasks):
        owner = task.get("owner")
        if owner in feeds:
            feeds[owner].append(task)

    for owner, path in TASK_FILES.items():
        save_json(path, feeds[owner])


def mark_complete(ro: str, owner: str) -> bool:
    tasks = load_json(TASK_FILE)
    now = utc_now()
    changed = False

    for task in tasks:
        if (
            str(task.get("ro")) == str(ro)
            and str(task.get("owner")) == str(owner)
            and task.get("status_tracking") != "completed"
        ):
            task["status_tracking"] = "completed"
            task["completed_at"] = now
            task["completion_source"] = "manual_button"
            task["completed_by"] = owner
            task["overdue"] = False

            append_activity({
                "event_type": "task_completed_manual",
                "ro": task.get("ro"),
                "owner": task.get("owner"),
                "task": task.get("task"),
                "status": task.get("status"),
                "risk": task.get("risk"),
                "created_at": task.get("created_at"),
                "due_by": task.get("due_by"),
                "completed_at": now,
                "completed_by": owner,
                "completion_source": "manual_button",
            })

            changed = True

    if changed:
        save_json(TASK_FILE, tasks)
        write_owner_feeds(tasks)

    return changed


def load_tasks(owner: str):
    path = TASK_FILES.get(owner)
    if not path:
        return []
    return active_tasks(load_json(path))


def html_shell(title: str, body: str) -> str:
    return f"""
    <html>
    <head>
        <title>{html.escape(title)}</title>
        <meta http-equiv="refresh" content="10">
        <style>
            body {{
                font-family: Arial, sans-serif;
                padding: 20px;
                background: #f4f4f4;
            }}
            a {{
                margin-right: 12px;
                font-weight: bold;
                color: #222;
            }}
            .card {{
                background: white;
                padding: 18px;
                margin-bottom: 14px;
                border-radius: 8px;
                box-shadow: 0 1px 4px rgba(0,0,0,.15);
            }}
            .RED {{ border-left: 8px solid #b00020; }}
            .YELLOW {{ border-left: 8px solid #c78b00; }}
            .NORMAL {{ border-left: 8px solid #268a35; }}
            button {{
                padding: 11px 18px;
                margin-top: 10px;
                font-weight: bold;
                cursor: pointer;
                border-radius: 6px;
                border: 1px solid #333;
                background: #efefef;
            }}
            .due {{
                background: #f1f1f1;
                padding: 10px;
                border-radius: 6px;
                margin-top: 10px;
            }}
            .grid {{
                display: grid;
                grid-template-columns: repeat(3,1fr);
                gap: 14px;
            }}
            .score {{
                background: white;
                padding: 18px;
                border-radius: 8px;
                text-align: center;
            }}
            .count {{
                font-size: 42px;
                font-weight: bold;
            }}
        </style>
    </head>
    <body>
        <h1>{html.escape(title)}</h1>
        <a href="/board">Board</a>
        <a href="/drew">Drew</a>
        <a href="/mitch">Mitch</a>
        <a href="/preston">Preston</a>
        <hr>
        {body}
    </body>
    </html>
    """


def render_task(task: dict) -> str:
    risk = html.escape(str(task.get("risk", "NORMAL")))
    ro = html.escape(str(task.get("ro", "")))
    owner = html.escape(str(task.get("owner", "")))
    status = html.escape(str(task.get("status", "")))
    task_text = html.escape(str(task.get("task", "")))

    created_at = task.get("created_at", "")
    due_by = task.get("due_by", "")

    return f"""
    <div class="card {risk}">
        <h2>RO {ro}</h2>
        <p><b>Owner:</b> {owner}</p>
        <p><b>Risk:</b> {risk}</p>
        <p><b>AutoFlow Status:</b> {status}</p>
        <p><b>Task:</b> {task_text}</p>

        <div class="due">
            <div><b>Time Open:</b> {human_duration(created_at)}</div>
            <div><b>Created:</b> {short_time(created_at)}</div>
            <div><b>Due:</b> {short_time(due_by)}</div>
            <div><b>Overdue:</b> {task.get("overdue", False)}</div>
        </div>

        <form method="GET" action="/complete">
            <input type="hidden" name="ro" value="{ro}">
            <input type="hidden" name="owner" value="{owner}">
            <button type="submit">COMPLETE</button>
        </form>
    </div>
    """


def render_owner(owner: str) -> str:
    tasks = load_tasks(owner)
    body = "<h2>No active tasks</h2>" if not tasks else "".join(render_task(task) for task in tasks)
    return html_shell(f"{owner} Task Board", body)


def render_board() -> str:
    body = '<div class="grid">'
    load_summary = []

    for owner in TASK_FILES:
        tasks = load_tasks(owner)

        total = len(tasks)
        red = sum(1 for t in tasks if t.get("risk") == "RED")
        yellow = sum(1 for t in tasks if t.get("risk") == "YELLOW")
        overdue = sum(1 for t in tasks if t.get("overdue") is True)

        if red >= 3 or overdue >= 2:
            load = "CRITICAL"
        elif red >= 1 or total >= 5:
            load = "HEAVY"
        else:
            load = "OK"

        load_summary.append((owner, load, red, overdue, total))

        body += f"""
        <div class="score">
            <h2>{owner}</h2>
            <div class="count">{total}</div>
            <p>Active Tasks</p>
            <p>RED: {red}</p>
            <p>YELLOW: {yellow}</p>
            <p>OVERDUE: {overdue}</p>
            <p><b>LOAD: {load}</b></p>
        </div>
        """

    body += "</div>"

    bottleneck = max(load_summary, key=lambda x: (x[2], x[3], x[4]), default=None)

    if bottleneck and bottleneck[4] > 0:
        body += f"""
        <div class="card RED">
            <h2>System Bottleneck</h2>
            <p><b>{bottleneck[0]}</b> is currently the constraint.</p>
            <p>RED: {bottleneck[2]} | OVERDUE: {bottleneck[3]} | TOTAL: {bottleneck[4]}</p>
        </div>
        """
    else:
        body += """
        <div class="card NORMAL">
            <h2>System Bottleneck</h2>
            <p>No active bottleneck detected.</p>
        </div>
        """

    return html_shell("Shop Scoreboard", body)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.lower()

        if path == "/complete":
            qs = parse_qs(parsed.query)
            ro = qs.get("ro", [""])[0]
            owner = qs.get("owner", [""])[0]

            mark_complete(ro, owner)

            self.send_response(302)
            self.send_header("Location", f"/{owner.lower()}" if owner else "/board")
            self.end_headers()
            return

        if path in ("", "/", "/board"):
            content = render_board()
        elif path == "/drew":
            content = render_owner("Drew")
        elif path == "/mitch":
            content = render_owner("Mitch")
        elif path == "/preston":
            content = render_owner("Preston")
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not found")
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))


def run():
    write_owner_feeds(load_json(TASK_FILE))

    server = HTTPServer(("0.0.0.0", 8080), Handler)
    print("Advisor Task Viewer running with load balancing board")
    server.serve_forever()


if __name__ == "__main__":
    run()