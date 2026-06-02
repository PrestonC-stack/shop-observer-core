# Sprint 1 — Local DVI Gate

## What This Is

Local rules-only DVI quality gate for the Callahan Command Board.
No AI. No API credits. Pure deterministic rules.

When a DVI is signed off, this system:
1. Pulls the DVI data from AutoFlow
2. Runs it through the local rules engine
3. Produces PASS / REVIEW / REWORK_REQUIRED
4. Generates a printable rework slip if needed
5. Logs everything to the RO timeline

## Files Added

```
core/
  cas/
    dvi_schema.py       — data structures (DVIReview, DVIFlag, TimelineEntry)
    dvi_gate.py         — local rules engine (no AI)
    rework_slip.py      — text + HTML slip generator
  timeline/
    job_timeline.py     — per-RO JSONL event logger
  state/
    state_manager.py    — save/load DVIReview to disk

config/
  cas_rules/
    dvi_gate_rules.yaml — all rule thresholds (edit without touching code)

state/
  dvi_reviews/          — one JSON per RO
  job_timeline/         — one JSONL per RO

test_dvi_gate.py        — manual test command
requirements_sprint1.txt
```

## Setup

```powershell
cd C:\AI-RUNTIME\shop-observer-core

# Install dependencies
pip install pyyaml python-dotenv requests

# Copy Sprint 1 files into the repo
# (copy all files maintaining the directory structure above)
```

## Test Against Real ROs

```powershell
# Test RO 13517 (pulls live from AutoFlow, saves fixture, runs gate)
python test_dvi_gate.py 13517

# Test and print the text rework slip
python test_dvi_gate.py 13517 --print-slip

# Test and save the HTML rework slip
python test_dvi_gate.py 13517 --save-slip

# Test RO 13505
python test_dvi_gate.py 13505 --save-slip

# Run against saved fixture (no API call, for offline testing)
python test_dvi_gate.py 13517 --fixture tests/fixtures/dvi_13517.json
```

## What Gets Created

After running the test:

```
state/
  dvi_reviews/
    13517.json              — full DVIReview with all flags
    rework_slip_13517.html  — printable HTML slip
  job_timeline/
    13517.jsonl             — RO event log

tests/
  fixtures/
    dvi_13517.json          — saved API response for offline testing
```

## Expected Results for RO 13517

Based on the DVI data already pulled, expect:
- REWORK_REQUIRED
- Flags on: Rear Pads (no measurement), Ignition Switch (vague note),
  Transmission Fluid (leak with photos but vague location in note)
- HTML rework slip generated

## Expected Results for RO 13505

Based on the DVI data pulled:
- No completed DVI categories found (dvis array is empty)
- REVIEW status
- Flag: DVI may be incomplete

## Adjusting Rules

Edit `config/cas_rules/dvi_gate_rules.yaml` to:
- Add/remove vague note keywords
- Change minimum note length
- Add brake/tire/leak items
- Adjust who can override

No code changes needed.

## What Sprint 2 Adds

- DVI QC badge on each board card (PASS / REVIEW / REWORK)
- Print Rework Slip button on board
- Advisor acknowledgment button
- Stale rework indicator

## What Sprint 3 Adds

- Webhook trigger on dvi_signoff event
- Automatic gate runs on DVI completion
- 10-15 second delay + retry logic
