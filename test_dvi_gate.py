"""
test_dvi_gate.py
Callahan Auto & Diesel — Manual DVI Gate Test

Run this from C:\AI-RUNTIME\shop-observer-core to test the DVI gate
against a real RO without triggering the webhook.

Usage:
    python test_dvi_gate.py 13517
    python test_dvi_gate.py 13505
    python test_dvi_gate.py 13517 --print-slip
"""

import sys
import os
import json
import base64
import time
import argparse
import requests
from dotenv import load_dotenv

# Add project root to path so imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

from core.cas.dvi_gate import run_dvi_gate
from core.cas.rework_slip import generate_text_slip, generate_html_slip, save_slip
from core.cas.dvi_schema import TriggerEvent
from core.timeline.job_timeline import log_dvi_gate_result, log_rework_slip_generated
from core.state.state_manager import save_dvi_review


def fetch_autoflow(endpoint: str) -> dict:
    api_key = os.getenv("AUTOFLOW_API_KEY")
    api_password = os.getenv("AUTOFLOW_API_PASSWORD")
    subdomain = os.getenv("AUTOFLOW_SUBDOMAIN", "callahanautomotive")

    creds = base64.b64encode(f"{api_key}:{api_password}".encode()).decode()
    headers = {
        "accept": "application/json",
        "Authorization": f"Basic {creds}"
    }
    url = f"https://{subdomain}.autotext.me/api/v1/{endpoint}"
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def main():
    parser = argparse.ArgumentParser(description="Test DVI gate against a real RO")
    parser.add_argument("ro", help="RO number to test")
    parser.add_argument("--print-slip", action="store_true", help="Print text rework slip")
    parser.add_argument("--save-slip", action="store_true", help="Save HTML rework slip")
    parser.add_argument("--fixture", help="Load from local JSON fixture instead of API")
    args = parser.parse_args()

    ro = args.ro
    print(f"\n{'='*55}")
    print(f"DVI GATE TEST — RO {ro}")
    print(f"{'='*55}\n")

    # Load DVI data
    if args.fixture:
        print(f"Loading from fixture: {args.fixture}")
        with open(args.fixture) as f:
            dvi_data = json.load(f)
        wo_data = {}
    else:
        print(f"Pulling DVI from AutoFlow API...")
        time.sleep(2)  # brief delay to ensure API is ready
        try:
            dvi_data = fetch_autoflow(f"dvi/{ro}")
            print(f"DVI pulled OK — status: {dvi_data.get('message')}")
        except Exception as e:
            print(f"ERROR pulling DVI: {e}")
            sys.exit(1)

        print(f"Pulling work order from AutoFlow API...")
        try:
            wo_data = fetch_autoflow(f"work_orders/{ro}")
            print(f"Work order pulled OK\n")
        except Exception as e:
            print(f"Work order pull failed (non-fatal): {e}")
            wo_data = {}

    # Save fixture for future offline testing
    fixture_dir = os.path.join("tests", "fixtures")
    os.makedirs(fixture_dir, exist_ok=True)
    fixture_path = os.path.join(fixture_dir, f"dvi_{ro}.json")
    if not args.fixture:
        with open(fixture_path, "w") as f:
            json.dump(dvi_data, f, indent=2)
        print(f"Fixture saved: {fixture_path}")

    # Run the gate
    print(f"\nRunning DVI gate...\n")
    review = run_dvi_gate(
        dvi_data=dvi_data,
        work_order_data=wo_data,
        ro=ro,
        trigger_event=TriggerEvent.TEST
    )

    # Print results
    print(f"RESULT: {review.review_status}")
    print(f"Customer: {review.customer}")
    print(f"Vehicle:  {review.vehicle}")
    print(f"Tech:     {review.technician}")
    print(f"Advisor:  {review.advisor}")
    print(f"Primary Complaint: {review.primary_complaint[:100] if review.primary_complaint else 'None'}")
    print(f"Complaint Addressed: {review.complaint_addressed}")
    print(f"Total Flags: {review.flag_count}")
    print(f"Critical:  {len(review.critical_flags)}")
    print(f"Important: {len(review.important_flags)}")
    print(f"Cleared for Estimate: {review.cleared_for_estimate}")
    print()

    if review.flags:
        print("FLAGS:")
        print("-" * 40)
        for i, flag in enumerate(review.flags, 1):
            severity_label = {
                "critical": "❌ CRITICAL",
                "important": "⚠️  IMPORTANT",
                "info": "ℹ️  INFO"
            }.get(flag.severity, flag.severity.upper())
            print(f"{i}. {severity_label} — [{flag.section}] {flag.item_name}")
            print(f"   {flag.message}")
            print(f"   → {flag.recommended_action}")
            print()

    # Save review to state
    saved_path = save_dvi_review(review)
    print(f"Review saved: {saved_path}")

    # Log to timeline
    log_dvi_gate_result(review)
    print(f"Timeline updated: state/job_timeline/{ro}.jsonl")

    # Print rework slip
    if args.print_slip or review.rework_required:
        print("\n" + generate_text_slip(review))

    # Save HTML slip
    if args.save_slip or review.rework_required:
        slip_path = save_slip(review)
        log_rework_slip_generated(review, slip_path)
        print(f"\nHTML slip saved: {slip_path}")
        print(f"Open in browser: file:///{os.path.abspath(slip_path)}")

    print(f"\n{'='*55}")
    print(f"DVI GATE TEST COMPLETE — RO {ro} — {review.review_status}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
