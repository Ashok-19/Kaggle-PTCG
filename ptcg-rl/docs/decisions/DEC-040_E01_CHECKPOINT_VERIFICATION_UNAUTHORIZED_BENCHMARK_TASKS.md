# DEC-040 — Fail closed on unauthorized benchmark-task creation during checkpoint verification

- **Status:** ACCEPTED_FAILED_CLOSED
- **Created:** 2026-08-06T14:27:56Z
- **Approved request:** `configs/e01_source_bundle_v2_checkpoint_directory_verification_request_v1.json` at `443098120fa03dcbaa1d430e3f74505926d2e45fa5ea382856b80422816bba78`
- **Checkpoint files downloaded:** `0`
- **Unauthorized remote mutations:** `2`

## Decision

Do not consume the approved four-file checkpoint-directory verification. Two out-of-scope Kaggle benchmark-task objects were created by incorrect connector invocations before any approved checkpoint file was downloaded:

- `ashok205/new-benchmark-task-daa06` — `/code/ashok205/new-benchmark-task-daa06/edit/run/340605099`
- `ashok205/new-benchmark-task-4abba` — `/code/ashok205/new-benchmark-task-4abba/edit/run/340605166`

Both objects remain unchanged. Their privacy and execution state are unresolved. No deletion, cancellation, modification, or additional inspection is authorized under the checkpoint-verification approval.

The source-bundle version-2 checkpoint directory is therefore not remotely verified, source-bundle version 2 is not accepted as a production dependency, and the notebook-wrapper contract and approval text are not prepared.

## Boundaries

- Approved checkpoint files downloaded or hashed remotely: `0`
- Replay bodies or agent logs accessed: `0`
- Labels materialized: `0`
- Optimizer steps, training, or evaluation: `0`
- Dataset, model, submission, commit, or push mutations: none
- Remote mutations after fail-closed detection: `0`

## Evidence

- `reports/incidents/e01-source-bundle-v2-verification-unauthorized-benchmark-tasks-v1.json`
- `reports/artifacts/e01-source-bundle-v2-checkpoint-directory-verification-execution-review-v1.json`
