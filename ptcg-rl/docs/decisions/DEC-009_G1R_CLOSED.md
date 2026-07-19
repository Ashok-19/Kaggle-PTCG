# DEC-009: Close G1R

Date: 2026-07-19  
Status: Accepted

## Decision

Close G1R as `SUCCEEDED / PASS`. The repaired environment, semantic action, recurrent,
failure-mode, and provenance contracts are the approved interface for G2.

## Evidence

- Acceptance source commit: `c2540459428cfe99b2c587ab3a361abfacfd2db7`.
- Acceptance source hash: `5a98d55f542d0bfafd333a94ba146b292691bfd1c6a907c21a4da167cd8ac6f8`.
- Final receipt: `runs/g1r-user-long-acceptance/completion-receipt-20260718T205756Z.json`.
- Independent review: `runs/g1r-independent-review-pass-20260719/run_manifest.json`.
- Machine gate: `reports/gates/g1r.json`.
- Human report: `G1R_REMEDIATION_AND_ACCEPTANCE_REPORT.md`.

Every governing criterion passed. No training ran and R0 transferred zero manifest or
episode files. Native entropy still prohibits paired-seed or exact-trajectory claims.

## Consequence

The next reviewed work is G2 plus parallel R1 replay/meta implementation. This decision
does not authorize PPO training, deck promotion, Modal spend, or a Kaggle submission.
