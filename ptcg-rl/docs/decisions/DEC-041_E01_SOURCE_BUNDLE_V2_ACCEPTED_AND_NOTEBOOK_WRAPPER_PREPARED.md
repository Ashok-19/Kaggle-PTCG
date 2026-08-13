# DEC-041 — Accept source-bundle v2 checkpoint delivery and prepare production BC notebook

- **Status:** ACCEPTED_SOURCE_BUNDLE_VALID_NOTEBOOK_READY_UNAUTHORIZED
- **Created:** 2026-08-06T14:52:03Z
- **Source-bundle dataset:** `ashok205/kptcg-e01-majkel-corpus-review-inputs`, ID `11501808`, version `2`
- **Checkpoint:** `4dfba2adb9f97607cfa5dabadba075236bb7aae51eafab264584e947feae3827` / `5429190` bytes
- **Notebook request SHA-256:** `6d50e6b70c2a144948342bf8366ea481ee1330744bd96f6b82924500cc735d30`
- **Approval text SHA-256:** `4b00bce447f7372d3503086326bfc8f5a6c2e732745e708f642613d8693f06cf`

## Decision

Accept source-bundle version 2 through exact verification of the four extracted checkpoint members and deterministic byte-for-byte reconstruction of the approved checkpoint ZIP. Prepare one private Kaggle CPU notebook wrapper for production recurrent BC, but do not create or run it without the separate exact approval.

The planned run is capped at four epochs, 844 optimizer steps and 14,400 seconds. It may read only the exact 316 train/validation replay bodies after approval; all 46 test episodes remain sealed.

## Boundaries

- Verification files downloaded: `4` / `5428744` bytes
- Replay bodies and agent logs read during this step: `0`
- Optimizer steps and training: `0`
- Notebook creation or execution: none
- Model promotion, submission, commit or push: none
- Three benchmark-task incident objects remain unchanged as evidence

## Evidence

- `reports/artifacts/e01-source-bundle-v2-checkpoint-directory-verification-execution-review-v2.json`
- `reports/artifacts/e01-production-recurrent-bc-notebook-contract-review-v1.json`
- `configs/e01_production_recurrent_bc_notebook_request_v1.json`
- `scripts/kaggle/e01_production_recurrent_bc_notebook_v1.py`
- `scripts/kaggle/build_e01_production_recurrent_bc_notebook.py`
