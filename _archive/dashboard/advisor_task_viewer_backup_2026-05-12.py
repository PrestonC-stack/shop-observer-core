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
    return [task for task in tasks if task.get("status_tracking") != "completed"]


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
    import json
    from pathlib import Path

    ROOT = Path(__file__).resolve().parents[1]
    TASK_FILE = ROOT / "outputs" / "advisor_tasks.json"

    try:
        tasks = json.loads(TASK_FILE.read_text(encoding="utf-8"))
    except Exception:
        tasks = []

    columns = {"P1": [], "P2": [], "P3": [], "P4": []}

    for task in tasks:
        if task.get("status_tracking") == "completed":
            continue
        priority = task.get("priority", "P4")
        columns.setdefault(priority, []).append(task)

    priority_styles = {
        "P1": {"bg": "#fff1f1", "border": "#c00000", "header": "#b00020"},
        "P2": {"bg": "#fff8e1", "border": "#d18b00", "header": "#c77700"},
        "P3": {"bg": "#eef7ff", "border": "#2274a5", "header": "#1f6f9f"},
        "P4": {"bg": "#f3f7f0", "border": "#4b8a3f", "header": "#3e7a34"},
    }

    body = """
    <style>
        body {
            background: #f6f7fb !important;
            color: #111 !important;
        }

        .print-controls {
            margin: 10px 0 18px 0;
            padding: 12px;
            background: white;
            border-radius: 10px;
            box-shadow: 0 1px 4px rgba(0,0,0,.12);
        }

        .print-controls button {
            margin-right: 8px;
            padding: 10px 14px;
            font-weight: bold;
            border-radius: 8px;
            border: 1px solid #333;
            cursor: pointer;
            background: #ffffff;
        }

        .command-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 14px;
            align-items: start;
        }

        .priority-column {
            border-radius: 14px;
            padding: 10px;
            min-height: 85vh;
            border: 4px solid #ddd;
            box-shadow: 0 2px 8px rgba(0,0,0,.16);
        }

        .priority-title {
            color: white;
            text-align: center;
            padding: 10px;
            border-radius: 10px;
            font-size: 30px;
            font-weight: 900;
            margin-bottom: 10px;
        }

        .section {
            background: rgba(255,255,255,.86);
            padding: 8px;
            margin-bottom: 12px;
            border-radius: 10px;
            border: 1px solid rgba(0,0,0,.12);
        }

        .section-title {
            font-weight: 900;
            font-size: 18px;
            margin-bottom: 6px;
        }

        .action-title { color: #0044cc; }
        .incoming-title { color: #b26000; }
        .all-title { color: #444; }

        .task-card {
            background: white;
            color: #111;
            margin: 7px 0;
            padding: 9px;
            border-radius: 9px;
            border-left: 8px solid #999;
            box-shadow: 0 1px 4px rgba(0,0,0,.16);
            font-size: 15px;
            line-height: 1.25;
        }

        .task-card.RED {
            border-left-color: #d00000;
            background: #fff2f2;
        }

        .task-card.CRITICAL {
            border-left-color: #ff0000;
            background: #ffe1e1;
            animation: criticalFlash 1.2s infinite;
        }

        .task-card.YELLOW {
            border-left-color: #e7a000;
            background: #fff8dc;
        }

        .task-card.NORMAL {
            border-left-color: #248a3d;
            background: #f1fff4;
        }

        @keyframes criticalFlash {
            0% { box-shadow: 0 0 0 rgba(255,0,0,0); }
            50% { box-shadow: 0 0 18px rgba(255,0,0,.9); background: #ffd0d0; }
            100% { box-shadow: 0 0 0 rgba(255,0,0,0); }
        }

        .ro-line {
            font-size: 18px;
            font-weight: 900;
        }

        .waiting-line {
            font-weight: 900;
            color: #b00020;
        }

        .small-line {
            font-size: 13px;
            color: #333;
        }

        .rolling-row {
            border-bottom: 1px solid #ddd;
            padding: 5px 2px;
            font-size: 14px;
        }

        @media print {
            body {
                background: white !important;
            }

            .print-controls,
            a,
            hr {
                display: none !important;
            }

            .command-grid {
                display: block;
            }

            .priority-column {
                display: none;
                page-break-after: always;
                min-height: auto;
                box-shadow: none;
                border: 2px solid #333;
            }

            body.print-P1 .priority-P1,
            body.print-P2 .priority-P2,
            body.print-P3 .priority-P3,
            body.print-P4 .priority-P4,
            body.print-all .priority-column {
                display: block !important;
            }
        }
    </style>

    <script>
        function printPriority(priority) {
            document.body.classList.remove("print-P1", "print-P2", "print-P3", "print-P4", "print-all");
            document.body.classList.add("print-" + priority);
            window.print();
            setTimeout(function() {
                document.body.classList.remove("print-" + priority);
            }, 500);
        }

        function printAllPriorities() {
            document.body.classList.remove("print-P1", "print-P2", "print-P3", "print-P4");
            document.body.classList.add("print-all");
            window.print();
            setTimeout(function() {
                document.body.classList.remove("print-all");
            }, 500);
        }
    </script>

    <div class="print-controls">
        <b>Print Hit Lists:</b>
        <button onclick="printPriority('P1')">Print P1 Blitz List</button>
        <button onclick="printPriority('P2')">Print P2 Info Needed</button>
        <button onclick="printPriority('P3')">Print P3 Controlled Work</button>
        <button onclick="printPriority('P4')">Print P4 Waiting</button>
        <button onclick="printAllPriorities()">Print All</button>
    </div>

    <div class="command-grid">
    """

    for p in ["P1", "P2", "P3", "P4"]:
        style = priority_styles[p]

        body += f"""
        <div class="priority-column priority-{p}" style="background:{style['bg']};border-color:{style['border']};">
            <div class="priority-title" style="background:{style['header']};">{p}</div>
        """

        # ACTION NOW
        body += """
            <div class="section">
                <div class="section-title action-title">Action Now</div>
        """

        for task in columns[p][:8]:
            risk = task.get("risk", "NORMAL")
            body += f"""
                <div class="task-card {risk}">
                    <div class="ro-line">RO {task.get('ro')}</div>
                    <div class="waiting-line">Waiting On: {task.get('owner')}</div>
                    <div><b>Risk:</b> {risk}</div>
                    <div><b>Status:</b> {task.get('status')}</div>
                    <div class="small-line">{task.get('task', '')[:95]}</div>
                </div>
            """

        body += "</div>"

        # INCOMING SOON
        body += """
            <div class="section">
                <div class="section-title incoming-title">Incoming Soon</div>
        """

        for task in columns[p]:
            status = task.get("status", "").lower()
            idle = task.get("idle_hours", 0)

            if (
                ("servicing" in status or "in progress" in status)
                and idle < 2
                and task.get("priority") != "P4"
            ):
                risk = task.get("risk", "NORMAL")
                body += f"""
                <div class="task-card {risk}">
                    <div class="ro-line">RO {task.get('ro')}</div>
                    <div><b>ETA Soon</b> → {task.get('owner')}</div>
                    <div><b>Status:</b> {task.get('status')}</div>
                </div>
                """

        body += "</div>"

        # ALL JOBS
        body += """
            <div class="section">
                <div class="section-title all-title">All Jobs</div>
        """

        for task in columns[p]:
            body += f"""
                <div class="rolling-row">
                    <b>RO {task.get('ro')}</b> | {task.get('owner')} | {task.get('risk')} | {task.get('status')}
                </div>
            """

        body += """
            </div>
        </div>
        """

    body += "</div>"

    return html_shell("Shop Command Board", body)


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