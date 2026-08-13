# DEC-037 — Consume retained-dataset remediation and prepare source-bundle v2 approval

- **Status:** ACCEPTED_REMEDIATION_CONSUMED_SOURCE_BUNDLE_APPROVAL_READY
- **Created:** 2026-08-06T09:38:01Z
- **Remediation request SHA-256:** `24abd3c96a95b57cbef294c04332bafad16e0ba24557f86b6cd912eae476b080`
- **Renewed production BC request SHA-256:** `297679d5a1a2ca43b3f8ef1dc158cdc82fc68e8c5fe7b6791d790bded586ea0d`
- **Source-bundle approval text SHA-256:** `f99906186f531a5635ec7525eccbfe8eec3314bc932a7b2e9f8c05e18ccd06b5`

## Decision

Retain `ashok205/new-benchmark-task-b1c52` unchanged as incident evidence. Consume the exact metadata-only root-basename remediation for private retained dataset ID `11514316`, version `1`, after live metadata-only verification reproduced 58 files, 341,559,745 bytes and inventory SHA-256 `d03105906d9e066045410bc4da07ec7bd045f5b1285d35ddc516c1e7960b5c43`.

The source-bundle version-2 publication remains unauthorized. Prepare exact approval text that preserves all 66 version-1 files and adds the frozen 10-file overlay, yielding an expected 76-file, 7,646,035-byte version 2 with inventory SHA-256 `78fa9caa32782729a28cb9254449f22e46a6edcb5f83b7b2f763756bd970fa90`.

## Boundaries

- Replay bodies or agent logs accessed: `0`
- Kaggle dataset, notebook, model, or benchmark-task mutations: `0`
- Labels, optimizer steps, training, or evaluation: `0`
- Model promotion, submission, commit, or push: none

## Evidence

- `reports/artifacts/e01-production-bc-remediation-consumption-review-v2.json`
- `reports/artifacts/e01-production-bc-remediation-consumption-review-v1.json`
- `configs/e01_production_bc_retained_dataset_remediation_request_v1.json`
- `configs/e01_production_recurrent_bc_request_v2.json`
