# --- START REPLACEMENT FILE ---

from __future__ import annotations
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from flask import Flask, Response

REPO_ROOT = Path(__file__).resolve().parents[1]
EVENT_LOG_PATH = REPO_ROOT / "data" / "autoflow_events" / "autoflow_events.jsonl"
STATE_PATH = REPO_ROOT / "state" / "active_shop_state.json"

app = Flask(__name__)

def _parse_timestamp(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except:
        return datetime.min.replace(tzinfo=timezone.utc)

def _load():
    if not EVENT_LOG_PATH.exists():
        return []
    out=[]
    for line in EVENT_LOG_PATH.read_text().splitlines():
        try:
            out.append(json.loads(line))
        except:
            continue
    return out

def build_state():
    now = datetime.now(timezone.utc)
    ros = {}

    for r in _load():
        p = r.get("payload", {})
        ro = str(p.get("ticket", {}).get("invoice", "unknown"))
        status = str(p.get("ticket", {}).get("status", "unknown"))
        ts = _parse_timestamp(p.get("timestamp") or r.get("received_at"))

        if ro == "unknown":
            continue

        ros.setdefault(ro, []).append({
            "status": status,
            "ts": ts,
            "vehicle": f"{p.get('vehicle',{}).get('year','')} {p.get('vehicle',{}).get('make','')} {p.get('vehicle',{}).get('model','')}"
        })

    rows=[]
    for ro, events in ros.items():
        events.sort(key=lambda x: x["ts"])
        first = events[0]["ts"]
        last = events[-1]["ts"]
        status = events[-1]["status"]

        age = (now - first).total_seconds()/60
        idle = (now - last).total_seconds()/60

        level = "none"
        reason = ""

        if "In Progress" in status:
            if idle >= 120:
                level="red"; reason="No progress >120m"
            elif idle >= 60:
                level="yellow"; reason="No progress >60m"

        if "Part" in status:
            if age >= 2880:
                level="red"; reason="Waiting parts >2d"
            elif age >= 1440:
                level="yellow"; reason="Waiting parts >1d"

        if age >= 7200:
            level="red"; reason="Car >5d"
        elif age >= 4320 and level!="red":
            level="yellow"; reason="Car >3d"

        rows.append({
            "ro": ro,
            "status": status,
            "vehicle": events[-1]["vehicle"],
            "last": last.isoformat(),
            "count": len(events),
            "age": int(age),
            "idle": int(idle),
            "level": level,
            "reason": reason
        })

    rows.sort(key=lambda x: x["idle"], reverse=True)

    return {
        "rows": rows,
        "summary": {
            "total": len(rows),
            "red": sum(1 for r in rows if r["level"]=="red"),
            "yellow": sum(1 for r in rows if r["level"]=="yellow")
        }
    }

def render(s):
    rows=s["rows"]

    def color(l):
        return "red" if l=="red" else "orange" if l=="yellow" else "black"

    trs="".join(f"""
    <tr>
    <td>{r['ro']}</td>
    <td>{r['status']}</td>
    <td>{r['vehicle']}</td>
    <td>{r['age']}m</td>
    <td>{r['idle']}m</td>
    <td style='color:{color(r['level'])}'>{r['level']}</td>
    <td>{r['reason']}</td>
    </tr>
    """ for r in rows)

    return f"""
    <html><head>
    <meta http-equiv="refresh" content="10">
    <style>
    body{{font-family:Arial;padding:20px}}
    table{{width:100%;border-collapse:collapse}}
    td,th{{border:1px solid #ccc;padding:8px}}
    </style>
    </head><body>

    <h2>Shop Dashboard</h2>

    <div>
    Total: {s['summary']['total']} |
    Red: {s['summary']['red']} |
    Yellow: {s['summary']['yellow']}
    </div>

    <table>
    <tr>
    <th>RO</th><th>Status</th><th>Vehicle</th>
    <th>Age</th><th>Idle</th><th>Attention</th><th>Reason</th>
    </tr>
    {trs}
    </table>

    </body></html>
    """

@app.get("/")
def home():
    s = build_state()
    return Response(render(s), mimetype="text/html")

if __name__=="__main__":
    app.run(port=5080)

# --- END FILE ---