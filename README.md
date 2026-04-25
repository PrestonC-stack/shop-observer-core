# shop-observer-core

Core logic engine for shop activity monitoring, draft intake normalization, and review-first observer nudges for service advisor workflow tracking.

## System Purpose

This project is a local-first Shop Observer focused on:

- ingesting shop activity from safe local sources
- normalizing source data into one reviewable shop state
- applying observer rules to detect operational gaps
- outputting draft nudges for operator review

The current build is intentionally advisory-first.

## Intake Architecture

First-pass intake architecture:

- `connectors/`
  Placeholder source readers for AutoFlow and Tekmetric mock data
- `inputs/`
  Local mock source payloads and shop input examples
- `normalizers/`
  Conversion layer that merges source-specific payloads into one `shop_state`
- `observer-rules/`
  Rule catalog for first-pass operational findings
- `drafts/`
  Draft nudge output builders for review-first operator prompts

Current source flow:

`mock source data -> normalized shop_state -> observer rules -> draft nudges`

## Approval-Before-Action Rule

This system is review-first.

- no automatic live business-system changes
- no automatic customer communication
- no destructive actions
- no hidden execution paths
- no credential handling in source code

Draft nudges are intended for human review and approval before any future action layer is considered.

## Next Build Steps

1. Add `current_shop_snapshot.json` as the approved live state target.
2. Add pasted-text intake parsing into a draft review path.
3. Add screenshot/photo intake as draft-only with confidence scoring.
4. Expand normalizers for stronger source field mapping.
5. Grow the observer rules into a dedicated reviewable rule library.
6. Add source-specific CSV/API evaluation only after read-only boundaries are clear.
