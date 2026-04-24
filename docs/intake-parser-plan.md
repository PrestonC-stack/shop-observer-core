# Intake Parser Plan

## Purpose

This document defines the next phase for replacing manual JSON entry with safer intake paths for pasted shop data, screenshot/photo review, and future structured exports.

The goal is to reduce manual editing of `current_shop_snapshot.json` while keeping all intake reviewable, operator-approved, and bounded by clear safety rules.

This phase should improve intake quality without introducing direct business-system access.

## Supported Intake Types

The parser should eventually support these intake types:

- pasted text
- screenshots/photos
- future CSV/API export

Recommended rollout order:

1. pasted text
2. screenshots/photos
3. future CSV/API export

Pasted text should be the first implemented path because it is the easiest to validate and the lowest-risk bridge from manual entry.

## Draft Intake Flow

Recommended flow:

`raw input -> parsed draft -> confidence score -> Preston approval -> current_shop_snapshot.json`

Meaning of each stage:

- raw input: original pasted text, screenshot, photo, or export file
- parsed draft: normalized ticket objects built from the raw input
- confidence score: parser confidence about field extraction quality
- Preston approval: human review before promotion
- `current_shop_snapshot.json`: approved live observer snapshot

The parser should never skip the review step for non-trivial intake.

## Required Folders

Recommended structure:

- `inputs/intake_raw/`
- `inputs/intake_drafts/`
- `inputs/current_shop_snapshot.json`

Suggested purpose:

- `inputs/intake_raw/`
  Store raw pasted captures, screenshot files, photo files, or import files that need processing.
- `inputs/intake_drafts/`
  Store structured parsed drafts that are awaiting review or correction.
- `inputs/current_shop_snapshot.json`
  Store the approved live snapshot used by the observer.

`current_shop_snapshot.json` should remain the only live source consumed by the observer.

## Rules

- screenshots never overwrite live data directly
- low confidence requires clarification
- no credentials stored
- no direct Tekmetric or Autoflow login yet

Additional operational rules:

- pasted text should be validated before draft promotion
- screenshots/photos should always route through draft review
- malformed input should not silently write partial live data
- API or CSV imports should still produce a reviewable draft layer first

## Telegram Role

Telegram should be treated as an intake and alert channel, not a system-of-record.

Telegram responsibilities:

- alerts
- pasted ticket intake
- screenshot/photo upload later

Recommended behavior by stage:

- alerts should remain simple outbound summaries and priority notifications
- pasted ticket intake should support structured text blocks first
- screenshot/photo upload should be added only after draft parsing and confidence review are stable

Telegram should not become a direct command path for destructive actions or business-system access.

## Hermes Role

Hermes should act as a local intake coordinator and review assistant.

Hermes responsibilities:

- ask clarifying questions
- remember approved corrections
- build pattern history from `outputs/history`

Practical examples:

- ask for missing timestamps or unclear advisor names
- remember repeated approved field corrections so future drafts improve
- detect repeated DVI issues, stalled estimates, or follow-up gaps from history trends

Hermes should support intake improvement, not bypass human review.

## API Discovery Checklist For Tekmetric/Autoflow

Before any API-based intake is implemented, verify:

1. whether an official API exists
2. what authentication model is required
3. what read-only endpoints are available
4. whether ticket status, advisor, notes, estimates, and parts state can be exported cleanly
5. whether timestamps are normalized and reliable
6. whether rate limits or usage restrictions exist
7. whether CSV export is easier and safer than API intake at first
8. whether a sandbox or test environment is available
9. whether any terms or compliance restrictions affect automation
10. whether read-only ingestion can be isolated from any write capability

No API discovery outcome should automatically lead to direct login or direct write access.

## Phase 1 Implementation Tasks

1. Define the exact pasted-text intake format and keep it narrow.
2. Create `inputs/intake_raw/` and `inputs/intake_drafts/` as the parser working folders.
3. Add a parser that converts pasted ticket blocks into structured draft objects.
4. Add confidence scoring for parsed drafts.
5. Add a review step that shows accepted fields, uncertain fields, and clarification questions.
6. Require Preston approval before writing any draft into `current_shop_snapshot.json`.
7. Add a simple correction memory file or rule set for repeated approved fixes.
8. Add screenshot/photo draft parsing only after pasted-text parsing is stable.
9. Evaluate CSV export intake before attempting API intake.
10. Keep all live observer reads pointed only at `current_shop_snapshot.json`.
