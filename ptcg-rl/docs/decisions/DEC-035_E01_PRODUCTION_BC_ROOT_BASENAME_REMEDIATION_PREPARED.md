# DEC-035 — Prepare root-basename retained-dataset remediation

- **Status:** ACCEPTED_REQUEST_READY_UNAUTHORIZED
- **Created:** 2026-08-06T07:23:00Z
- **Dataset:** `ashok205/kptcg-e01-production-bc-retained-inputs` ID `11514316`, version `1`
- **Remote inventory SHA-256:** `d03105906d9e066045410bc4da07ec7bd045f5b1285d35ddc516c1e7960b5c43`
- **Remediation request SHA-256:** `24abd3c96a95b57cbef294c04332bafad16e0ba24557f86b6cd912eae476b080`
- **Renewed production BC request SHA-256:** `297679d5a1a2ca43b3f8ef1dc158cdc82fc68e8c5fe7b6791d790bded586ea0d`

## Decision

Prepare, but do not consume, a contract-only remediation that adopts the already verified root-level `<episode_id>.json` names. Keep dataset version 1 unchanged. Renew production recurrent BC under versioned implementation and runner paths so historical DEC-033 hashes remain intact.

## Boundaries

- Replay bodies read or downloaded: `0`
- Dataset deletions, creations, versions, or uploads: `0`
- Agent logs read: `0`
- Labels materialized: `0`
- Optimizer steps or training: `0`
- Model mutation, evaluation, promotion, submission, commit, or push: none

The remediation request requires a separate exact approval. Source-bundle version 2 and production training remain separately gated.

## Evidence

- `configs/e01_production_bc_retained_dataset_remediation_request_v1.json`
- `reports/artifacts/e01-production-bc-retained-dataset-remediation-contract-review-v1.json`
- `configs/e01_production_recurrent_bc_request_v2.json`
- `reports/artifacts/e01-production-recurrent-bc-contract-review-v2.json`
- `docs/decisions/DEC-034_E01_PRODUCTION_BC_RETAINED_DATASET_PATH_FLATTENING.md`
