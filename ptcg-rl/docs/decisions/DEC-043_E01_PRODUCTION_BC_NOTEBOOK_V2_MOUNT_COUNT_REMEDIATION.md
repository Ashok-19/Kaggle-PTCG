# DEC-043 — Prepare production BC notebook v2 mount-count remediation

- **Status:** ACCEPTED_REQUEST_READY_UNAUTHORIZED
- **Created:** 2026-08-06T15:11:18Z
- **Corrected notebook request SHA-256:** `93ad27ae290bdf56f0e6259a252625d7bd15150054d85139f29c9cae7fb7f4eb`
- **Approval text SHA-256:** `2e6f98386958bf207a3eeb10bacaf88a03e712ba67d20b3f3105bf8f32397c21`

## Decision

Prepare, but do not execute, a new private CPU notebook contract at slug `ashok205/kptcg-e01-production-recurrent-bc-v2`. Change only the August 3 mount aggregate from `4,724` to the official mounted summary of `4,721` files. Preserve every replay, checkpoint, dataset version, hyperparameter, four-epoch limit, 844-step cap, test seal, and output-review boundary.

## Boundary

No replay body, agent log, optimizer step, training, notebook retry, remote mutation, model operation, submission, commit, or push is authorized by this decision.

Evidence: `configs/e01_production_recurrent_bc_notebook_request_v2.json` and `reports/artifacts/e01-production-recurrent-bc-notebook-contract-review-v2.json` at file SHA-256 `ea3fd0eeaf398c2782326882b8352dc584d72ef94080fce7e20f5e58433197de`, self-hash `2a1e93b12a939a23de6224c640b1d024caba8b6e2b5c65ba80a71847458d6caf`.
