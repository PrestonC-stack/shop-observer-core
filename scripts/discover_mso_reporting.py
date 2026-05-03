
import os
import requests
from datetime import datetime, timedelta

from pathlib import Path

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"

if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

BASE_URL = os.getenv("AUTOFLOW_API_BASE_URL")
API_KEY = os.getenv("AUTOFLOW_API_KEY")

if not BASE_URL or not API_KEY:
    print("Missing AUTOFLOW_API_BASE_URL or AUTOFLOW_API_KEY")
    exit()

end_time = datetime.utcnow()
start_time = end_time - timedelta(hours=1)

url = f"{BASE_URL}/api/v1/mso/reporting"
params = {
    "month": datetime.now().strftime("%m"),
    "year": datetime.now().strftime("%Y")
}

headers = {
    "accept": "application/json",
    "authorization": f"Basic {API_KEY}",
    "content-type": "application/json"
}

print("Requesting MSO reporting...")

try:
    response = requests.get(url, headers=headers, params=params, timeout=15)

    print(f"HTTP status: {response.status_code}")

    if response.status_code != 200:
        print("Request failed")
        print(response.text[:500])
        exit()

    data = response.json()

    print(f"API message: {data.get('message')}")
    print(f"API status: {data.get('status')}")

    shops = data.get("response", {}).get("shops", [])

    print(f"Shop count: {len(shops)}")

    for shop in shops:
        print("\n--- SHOP ---")
        print(f"Name: {shop.get('shop_name')}")

        visits = shop.get("visits", [])
        print(f"Visit count: {len(visits)}")

        for v in visits[:10]:  # limit output
            print(f"- Invoice: {v.get('invoice')}")
            print(f"  Advisor: {v.get('service_advisor')}")
            vehicle = v.get("vehicle", {})
            print(f"  Vehicle: {vehicle.get('year')} {vehicle.get('make')} {vehicle.get('model')}")

except Exception as e:
    print("Error occurred:")
    print(str(e))