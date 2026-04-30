# TechFlow Screenshot Extraction Plan

## Purpose

Add a draft-only TechFlow screenshot intake layer that can accept local screenshot files now and structured OCR or vision text later. The layer supports review, matching, and hybrid analysis without sending messages, using credentials, or writing to AutoFlow.

## Folder Layout

- `inputs/techflow_screenshots/` stores local screenshot files or temporary OCR text files.
- `extractors/techflow_screenshot_extractor.py` creates draft JSON from OCR text or marks image-only files as pending OCR.
- `outputs/techflow_extraction_drafts/` stores review-only extraction drafts and example hybrid outputs.
- `normalizers/hybrid_shop_state_builder.py` merges TechFlow drafts with AutoFlow API shop state.

## Draft Extraction Schema

Required target fields:

- `ro_number`
- `technician_name`
- `vehicle`
- `customer`
- `job_name`
- `workflow_status`
- `percent_complete`
- `labor_sold_hours`
- `labor_clocked_hours`
- `labor_remaining_hours`
- `priority_position`
- `confidence_score`
- `extraction_flags`

Drafts must include `review_status: needs_review`. A screenshot draft is never allowed to update AutoFlow or overwrite AutoFlow truth automatically.

## Hybrid Merge Rules

Merge order:

1. RO number
2. Vehicle
3. Technician
4. Job name

RO number match is considered strongest. Vehicle, technician, and job-name matches can suggest a match, but the merged job stays flagged for review if confidence is below the high-confidence threshold.

Source labels:

- `autoflow_api`
- `techflow_screenshot`
- `merged_hybrid`

## Draft Priority Rules

The hybrid layer can generate draft-only nudges for:

- assigned job but no clock-in detected
- active job with 0 percent complete
- job has low remaining labor and should be prioritized
- technician working lower-priority job while faster closeout exists
- part not arrived but job appears active or complete
- completed job still has unarrived parts

## Safety Rules

- Do not connect Telegram yet.
- Do not send messages.
- Do not write to AutoFlow.
- Do not store or require credentials.
- Do not require live OCR yet.
- Keep all screenshot extraction as draft JSON pending human review.

## Test Flow

1. Place screenshots or OCR text files in `inputs/techflow_screenshots/`.
2. Run `py extractors/techflow_screenshot_extractor.py`.
3. Review JSON files in `outputs/techflow_extraction_drafts/`.
4. Use `normalizers/hybrid_shop_state_builder.py` from a future orchestration step to merge approved drafts with AutoFlow API shop state.
