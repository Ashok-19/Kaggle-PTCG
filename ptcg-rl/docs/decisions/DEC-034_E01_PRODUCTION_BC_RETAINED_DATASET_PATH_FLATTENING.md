# DEC-034 — Fail closed on retained dataset remote path flattening

- **Status:** ACCEPTED_FAILED_CLOSED
- **Created:** 2026-08-05T11:15:36.894998Z
- **Request SHA-256:** `aeacd6377db8bf2b0bce0bfd5e3f20f71094735fd2cb51cfdacd9b7348a60c7b`
- **Dataset:** `ashok205/kptcg-e01-production-bc-retained-inputs`
- **Dataset ID / version:** `11514316` / `1`

## Decision

Reject private dataset version 1 as a production recurrent BC input dependency and stop without training. Kaggle created a private Ready dataset with the exact 58 replay basenames and exact total of 341,559,745 bytes, but flattened every approved `episodes/<episode_id>.json` path to root-level `<episode_id>.json`.

## Evidence

- Remote files: 58
- Remote bytes: 341,559,745
- Remote inventory SHA-256: `d03105906d9e066045410bc4da07ec7bd045f5b1285d35ddc516c1e7960b5c43`
- Filename mismatches: 58
- Test replay uploads: 0
- Agent-log reads: 0
- Optimizer steps: 0
- Training/evaluation/model promotion/submission: none

The dataset remains private and was not deleted or versioned after failure because neither remediation was authorized. A new exact approval must bind the remediation method and resulting dataset identity before any production BC execution.

## Evidence files

- `reports/artifacts/raw/e01-production-bc-retained-dataset-verification-20260805-v1.json`
- `reports/artifacts/e01-production-bc-input-publication-execution-review-v1.json`
- `reports/incidents/e01-production-bc-retained-dataset-path-flattening-v1.json`
