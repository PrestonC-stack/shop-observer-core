import requests
import base64
import os
from dotenv import load_dotenv

load_dotenv()

base_url = os.getenv("AUTOFLOW_BASE_URL")
api_key = os.getenv("AUTOFLOW_API_KEY")
api_password = os.getenv("AUTOFLOW_API_PASSWORD")

if not base_url or not api_key or not api_password:
    raise SystemExit("Missing AUTOFLOW_BASE_URL, AUTOFLOW_API_KEY, or AUTOFLOW_API_PASSWORD in .env")

auth_string = f"{api_key}:{api_password}"
encoded_auth = base64.b64encode(auth_string.encode()).decode()

headers = {
    "Authorization": f"Basic {encoded_auth}",
    "Accept": "application/json",
    "Content-Type": "application/json"
}

ro_number = "13298"  # change this to a real RO if needed

def test_endpoint(endpoint):
    url = f"{base_url.rstrip('/')}{endpoint}"
    print("\n==============================")
    print(f"Testing: {endpoint}")

    response = requests.get(url, headers=headers)

    print(f"Status: {response.status_code}")

    try:
        data = response.json()
        print(data)
    except Exception:
        print(response.text)

test_endpoint(f"/api/v1/work_orders/{ro_number}")
test_endpoint(f"/api/v1/dvi/{ro_number}")
test_endpoint(f"/api/v1/conversations?remote_ticket_id={ro_number}")