from datetime import datetime
from flask import Flask, Response

app = Flask(__name__)

# Wallboard HTML Template
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Country Club Advisor Command Board</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { font-family: system-ui, -apple-system, sans-serif; }
        .p1 { border-left: 6px solid #ef4444; }
        .p2 { border-left: 6px solid #f59e0b; }
        .p3 { border-left: 6px solid #3b82f6; }
        .p4 { border-left: 6px solid #6b7280; }
    </style>
</head>
<body class="bg-zinc-950 text-zinc-100 min-h-screen">
    <div class="max-w-screen-2xl mx-auto p-6">
        <div class="flex justify-between items-center mb-8">
            <div>
                <h1 class="text-4xl font-bold">Country Club Advisor Command Board</h1>
                <p class="text-zinc-400">Last Updated: {timestamp}</p>
            </div>
            <span class="px-3 py-1 bg-green-500/20 text-green-400 rounded-full text-sm font-medium">● LIVE</span>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
            <!-- P1-P4 Columns -->
            <div class="lg:col-span-7 space-y-6">
                <h2 class="text-2xl font-semibold mb-4">Jobs by Priority</h2>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div class="bg-zinc-900 rounded-xl p-5 p1">
                        <h3 class="text-red-400 font-bold text-lg mb-3">🔴 P1 - Critical</h3>
                        <div class="bg-zinc-800 rounded-lg p-3 text-sm">
                            <div class="font-medium">2021 Ford F-150 • John D.</div>
                            <div class="text-zinc-400">No start - clicking sound • Bay 2</div>
                        </div>
                    </div>
                    <div class="bg-zinc-900 rounded-xl p-5 p2">
                        <h3 class="text-amber-400 font-bold text-lg mb-3">🟠 P2 - High</h3>
                        <div class="bg-zinc-800 rounded-lg p-3 text-sm">
                            <div class="font-medium">2018 Chevy Silverado • Mike R.</div>
                            <div class="text-zinc-400">Engine misfire diagnosis</div>
                        </div>
                    </div>
                    <div class="bg-zinc-900 rounded-xl p-5 p3">
                        <h3 class="text-blue-400 font-bold text-lg mb-3">🔵 P3 - Medium</h3>
                        <div class="bg-zinc-800 rounded-lg p-3 text-sm">
                            <div class="font-medium">2020 Toyota Camry • Sarah P.</div>
                            <div class="text-zinc-400">Brake inspection + oil change</div>
                        </div>
                    </div>
                    <div class="bg-zinc-900 rounded-xl p-5 p4">
                        <h3 class="text-zinc-400 font-bold text-lg mb-3">⚪ P4 - Low</h3>
                        <div class="bg-zinc-800 rounded-lg p-3 text-sm text-zinc-500">No jobs in P4</div>
                    </div>
                </div>
            </div>

            <!-- Sidebar -->
            <div class="lg:col-span-5 space-y-6">
                <div class="bg-zinc-900 rounded-xl p-5">
                    <h3 class="font-bold text-lg mb-3">📋 Advisor Action Queue</h3>
                    <div class="space-y-2 text-sm">
                        <div class="bg-zinc-800 p-3 rounded-lg">Call back John D. - No-start update <span class="text-amber-400">(P1)</span></div>
                        <div class="bg-zinc-800 p-3 rounded-lg">Follow up with Sarah P. on estimate <span class="text-blue-400">(P3)</span></div>
                    </div>
                </div>

                <div class="bg-zinc-900 rounded-xl p-5">
                    <h3 class="font-bold text-lg mb-3">🔧 Technician Action Queue</h3>
                    <div class="bg-zinc-800 p-3 rounded-lg">Bay 2 - Ford F-150 diagnosis <span class="text-red-400">(Tech: Mike)</span></div>
                </div>

                <div class="grid grid-cols-2 gap-4">
                    <div class="bg-zinc-900 rounded-xl p-5">
                        <h3 class="font-bold">Technician Load</h3>
                        <div class="text-4xl font-bold text-green-400">4/6</div>
                    </div>
                    <div class="bg-zinc-900 rounded-xl p-5">
                        <h3 class="font-bold">Bay Utilization</h3>
                        <div class="text-4xl font-bold text-blue-400">83%</div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</body>
</html>"""

@app.route("/")
def board():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html = HTML_TEMPLATE.format(timestamp=timestamp)
    return Response(html, mimetype="text/html")


@app.route("/healthz")
def healthz():
    return {"status": "ok"}, 200


if __name__ == "__main__":
    print("🚀 Starting Country Club Advisor Command Board on 127.0.0.1:5000")
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False,
        threaded=True,
        use_reloader=False,
    )