"""
Callahan AI - Advisor Command Board (Simple & Reliable)
"""

import sys
from pathlib import Path
from flask import Flask
from datetime import datetime

ROOT = Path("C:/AI-RUNTIME")
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "shop-observer-core"))

# Import your existing stuff
try:
    from connectors.autoflow import fetch_autoflow_data
    from hermes.intelligence.shop_intelligence_llm import ShopIntelligenceLLM
    print("✅ Connectors loaded")
except Exception as e:
    print("Import error:", e)

app = Flask(__name__)

@app.route("/")
def advisor_board():
    # Get data
    try:
        shop_data = fetch_autoflow_data([])  # mock for now
        num_active = len(shop_data.get("records", []))
    except:
        num_active = 0

    # Get intelligence
    try:
        intel = ShopIntelligenceLLM()
        summary = intel.generate_smart_summary()
    except Exception as e:
        summary = f"Intelligence loading... ({str(e)[:100]})"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Country Club Advisor Command Board</title>
        <meta http-equiv="refresh" content="60">
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; background: #f8f9fa; }}
            h1 {{ color: #1e3a8a; }}
            .card {{ background: white; padding: 25px; margin: 20px 0; border-radius: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }}
            pre {{ background: #f1f5f9; padding: 20px; border-radius: 8px; }}
        </style>
    </head>
    <body>
        <h1>🚀 Country Club Advisor Command Board</h1>
        <p><strong>Last Updated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        
        <div class="card">
            <h2>📊 Shop Overview</h2>
            <p><strong>Active Repair Orders:</strong> {num_active}</p>
        </div>

        <div class="card">
            <h2>🧠 Live Intelligence</h2>
            <pre>{summary}</pre>
        </div>

        <p style="text-align:center; color:#666;">
            Refreshing every 60 seconds
        </p>
    </body>
    </html>
    """
    return html

if __name__ == "__main__":
    print("🚀 Advisor Command Board Running")
    print("Open in browser → http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000, debug=False)