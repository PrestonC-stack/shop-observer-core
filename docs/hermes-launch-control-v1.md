# Hermes Launch Control v1

## Purpose

Hermes Launch Control v1 is a safe local control center for the Shop Observer.

Its job is to give a simple local operator interface for running the observer, opening outputs, and reviewing the most important current questions without turning Hermes into a broad autonomous system.

Version 1 should stay local, operator-driven, and tightly scoped to the observer workflow.

## What v1 Can Do

Hermes Launch Control v1 can:

- pull the latest GitHub code for the local repo
- run the observer locally
- open the latest summary output
- open the history folder
- display Questions for Preston

These actions should be initiated by the operator and kept visible and reviewable.

## What v1 Cannot Do

Hermes Launch Control v1 cannot:

- log into Tekmetric or Autoflow
- delete files
- make autonomous edits
- handle credentials

It should also avoid acting as a general-purpose machine controller.

## Proposed Command/Menu Layout

Recommended v1 menu:

1. Pull Latest Code
2. Run Shop Observer
3. Open Latest Summary
4. Open History Folder
5. Show Questions for Preston
6. Exit

Recommended command aliases:

- `pull`
- `run`
- `latest`
- `history`
- `questions`
- `exit`

Recommended operator flow:

1. pull latest code
2. run observer
3. review latest summary
4. review Questions for Preston
5. open history if trend review is needed

## Future Telegram Commands

If Telegram control is added later, these command ideas should map to the same local control concepts:

- `/run_shop`
- `/latest`
- `/questions`
- `/top3`

Suggested meanings:

- `/run_shop` runs the observer against the current snapshot
- `/latest` returns or opens the latest summary
- `/questions` returns the current Questions for Preston section
- `/top3` returns the current Top 3 Actions Right Now section

Telegram should remain a thin control surface and should not bypass local safety rules.

## Future Memory Layer Concept

A future memory layer could organize operational memory around:

- `outputs/history`
- answers from Preston
- recurring patterns

Possible memory uses later:

- track repeated DVI issues by advisor or location
- track repeated estimate stalls
- track recurring parts-delay patterns
- preserve answers Preston gives so the observer can improve future questions

Memory should remain reviewable and bounded. It should not become an uncontrolled source-of-truth.

## Tool Options To Evaluate Later

Potential tools worth evaluating in later phases:

- AIngram for local memory
- LangGraph for stateful workflows
- OpenClaw for scoped execution

Evaluation guidance:

- AIngram should be considered only if local memory needs become too large for simple file-based review.
- LangGraph should be considered only when the workflow needs explicit state transitions and durable control flow.
- OpenClaw should be considered only for tightly scoped execution after boundaries, approvals, and safety constraints are well defined.

None of these tools should be part of Launch Control v1 by default.

## Safety Rules

- local operator control only
- no credential handling
- no direct Tekmetric or Autoflow login
- no destructive actions
- no file deletion
- no autonomous edits
- no hidden background execution
- no automatic overwrite of approved snapshot data without review
- no broad filesystem access outside the intended repo workflow
- no automatic customer communication

Launch Control v1 should stay transparent, narrow, and easy to stop at any time.
