# DEC-042 — Production BC notebook v1 failed on August 3 mount count

- **Status:** ACCEPTED_FAILED_CLOSED
- **Created:** 2026-08-06T15:11:18Z
- **Notebook:** `ashok205/kptcg-e01-production-recurrent-bc-v1`, ID `129904937`, version `1`, private
- **Approved request SHA-256:** `6d50e6b70c2a144948342bf8366ea481ee1330744bd96f6b82924500cc735d30`

## Decision

Reject the v1 notebook execution because its preflight expected `4,724` August 3 mount files while Kaggle mounted the officially summarized `4,721` files at the same exact `21,451,850,075` bytes. The failure occurred before selected replay verification, checkpoint reconstruction, optimizer construction, or training.

## Boundary

- Notebook creations/runs: `1`
- Replay bodies/bytes read: `0` / `0`
- Agent logs: `0`
- Optimizer steps: `0`
- Training/evaluation/model/submission: none
- Retry, dataset mutation, commit, push: none

Evidence: `reports/incidents/e01-production-recurrent-bc-notebook-v1-august3-mount-count-v1.json` at file SHA-256 `e7d4b3b8e10c61de8c872634dd09cc7db241602ddf3ea00580bce9a0dce9e6b8` and `reports/artifacts/e01-production-recurrent-bc-notebook-execution-review-v1.json` at file SHA-256 `1f1f76cf9bcba191f46b774f668b0ff04d45a206814f51d600bea8687ab2f593`.
