# AdvizMe TekMetric Observer

AdvizMe TekMetric Observer is a read-only Chrome extension for watching TekMetric workflow pages and sending lightweight operational signals to the local Flask dashboard.

## Load The Extension

1. Open Chrome.
2. Go to Settings -> Extensions.
3. Turn on Developer mode.
4. Click Load unpacked.
5. Select the `chrome-extension/` folder from this repo.

## What It Does

- Runs only on `https://*.tekmetric.com/*`.
- Watches page changes with a `MutationObserver`.
- Looks for visible signals such as DVI completion, complaint or concern code changes, job status changes, and estimate line item changes.
- Sends detected events to `http://localhost:8080/ingest/tekmetric-event`.
- Debounces repeated events for the same RO and event type with a 3 second cooldown.

## What It Does Not Do

- It does not write to TekMetric.
- It does not click buttons or submit forms.
- It does not retry forever if the local Flask server is offline.
- It does not intentionally store customer phone numbers, emails, VINs, or message bodies.
- It is a read-only observer only.

## Local Server Endpoint

The dashboard Flask app must be running locally on port `8080`. Events are appended to:

```text
state/tekmetric_events.jsonl
```

Each event contains:

```json
{
  "event_type": "job_status_changed",
  "ro_number": "12345",
  "detail": "Status Ready",
  "detected_at_iso": "2026-09-03T12:00:00.000Z",
  "page_url": "https://example.tekmetric.com/..."
}
```
