from flask import Flask
from datetime import datetime

app = Flask(__name__)

@app.route("/")
def board():
    return f"""
    <h1>Country Club Advisor Command Board</h1>
    <p><strong>Last Updated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    <p>✅ Dashboard is running.</p>
    <p>If you see this, the basic page loads fine.</p>
    """

if __name__ == "__main__":
    print("🚀 Ultra Light Dashboard Running")
    app.run(host="127.0.0.1", port=5000, debug=False)