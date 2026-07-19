# Project Status

Last updated UTC: 2026-07-19  
Active repository: `https://github.com/Ashok-19/Kaggle-PTCG` (`PRIVATE`)  
Clean lineage root: `08be5cec0fac9a954a3fe127a3f51122be4736d1`  
Last completed gate: G1R environment/action/recurrent contract recertification (`PASS`)  
Current gates: G2 implementation plus parallel R1 manifest/schema work  
Gate status: AUTHORIZED / QUEUED  
Next review required before: any episode JSON transfer, G3 training, Modal execution, deck freeze, or submission

## Mission Clock

- Official close: `2026-08-16T23:59:00Z` (`2026-08-17 05:29 IST`)
- Entry/team-merger deadline: `2026-08-09T23:59:00Z`
- Architecture freeze: `2026-08-09T23:59:00Z`
- Training code/config freeze: `2026-08-12T23:59:00Z`
- Packaging freeze: `2026-08-14T23:59:00Z`

## Repository And Runtime Disposition

- `Ashok-19/Kaggle-PTCG` is the sole active project repository.
- `Ashok-19/Kaggle-PTCG-RL` is a private, inactive migration backup.
- The GitHub Packages permission gap is recorded and waived for agent development.
- Exact submission Python patch and timeout verification are deferred to final packaging/model compatibility; the submission doctor continues to enforce them.
- Dashboard dependencies remain isolated in the `dashboard` dependency group.
- ROGII is a read-only dashboard/workflow reference and must not be modified.

## Compute Roles

| Environment | Role |
|---|---|
| Local Ubuntu | Source changes, dashboard, metadata, deterministic replay planning, unit/contract tests, tiny engine smoke, packaging and completed-agent inference/runtime tests |
| Kaggle notebooks | Default heavy-workflow platform: accelerator checks, expensive matrices, replay parsing at scale, and bounded training smoke after authorization |
| Colab | Secondary smoke/portability fallback |
| Modal | Main self-play, PPO/league training and large evaluation only after explicit approval |

No meaningful self-play, PPO, league training or large evaluation may run locally. Every heavy Kaggle workflow must be private, bounded, committed, reproducible and artifact-backed.

## Gate Ledger

| Gate | Status | Evidence | Review decision |
|---|---|---|---|
| G0 Repository/environment | passed | `REPOSITORY_CONSOLIDATION_REPORT.md`, G0 reports | PASS with Packages waiver |
| G1 Engine contract/tensor schema | superseded | `G1_ENVIRONMENT_ACTION_CONTRACT_REPORT.md` | historical smoke only |
| G1R Contract recertification | passed | `reports/gates/g1r.json`, `G1R_REMEDIATION_AND_ACCEPTANCE_REPORT.md` | PASS |
| R1 Replay/meta pipeline | queued | `reports/gates/r1.json`, `DEC-010` | implementation authorized; episode JSON blocked pending plan review |
| G2 Model/action schema | queued | `reports/gates/g2.json`, `DEC-010` | implementation authorized; training blocked |
| G3a PPO correctness smoke | not started | strict thresholds in `DEC-010` | Kaggle/Colab smoke only after review |
| G3b PPO competence | not started | strict thresholds in `DEC-010` | cloud only |
| D1 Deck selection | not started | strict thresholds in `DEC-010` | deck freeze requires approval |
| G4 Modal readiness | not started | | Modal canary requires approval |
| G5 Main champion | not started | | Modal only |
| G6 Final package | not started | | submission requires approval |

## Active Experiments And Jobs

No active long-running jobs. G1R contract repair, one-million-operation corpus, final-source parity, 10,080-game arena, throughput matrix, six-hour RSS soak and independent raw-artifact review are complete. Verified project compute cost remains USD `0`.

The Kaggle MCP is connected. On 2026-07-19 the account reported approximately 45 GPU hours and 20 TPU hours available for the current quota period, with only seconds consumed. This is capacity information, not authorization to train.

## Open Blockers And Review Boundaries

- G1R has no open blocker.
- R1 may retrieve the official index manifest and one selected daily manifest. It may not retrieve episode JSON until the exact capped plan is reviewed.
- G2 may implement and qualify the model/action contract. It may not start PPO training.
- The exact Python patch and final effective timeout remain submission-qualification notes, not current blockers.
- Main Modal training, deck freeze, Kaggle submissions and active-submission changes require explicit user approval.

## Decision Log

### DEC-006 - Existing repository is sole source of truth

- Decision: replace `Ashok-19/Kaggle-PTCG/main` with the verified clean lineage and consolidate the dashboard there without merging contaminated ancestry.
- Evidence: restricted-history scan, exact migration tree comparison and force-with-lease receipt in `REPOSITORY_CONSOLIDATION_REPORT.md`.
- Rollback: the private RL repository remains an inactive migration backup.

### DEC-007 - Cloud-first training execution

- Decision: local work stops at development/tiny smoke/package/runtime tests; Kaggle/Colab own bounded heavy smoke and Modal owns meaningful training.
- Expected effect: protect local time/resources while keeping correctness fast.
- Stop condition: any local command proposes meaningful self-play or training.

### DEC-008 - Reopen G1 as G1R

- Decision: retain the former G1 report as historical evidence and require the original handbook acceptance criteria plus independent recalculation.
- Evidence: `docs/decisions/DEC-008_G1_REOPENED.md`.
- Stop condition: any missing criterion keeps G1R blocked.

### DEC-009 - Close G1R

- Decision: accept the final-source qualifying evidence and independent raw-artifact recalculation; close G1R as `SUCCEEDED / PASS`.
- Evidence: `docs/decisions/DEC-009_G1R_CLOSED.md`.

### DEC-010 - Authorize G2/R1 and freeze strict evaluation

- Decision: implement G2 and parallel R1, expand the read-only dashboard fully, use Kaggle notebooks for heavy workflows, enforce two-stage replay transfer and apply strict gold-oriented evaluation thresholds.
- Evidence: `docs/decisions/DEC-010_G2_R1_AND_STRICT_EVALUATION.md`.
- Stop conditions: no episode JSON before plan review; no training before G2/evaluation review; no Modal, deck freeze, submission or push without approval.

## Immediate Next Actions

1. Synchronize and expand the dashboard so machine-readable progress auto-updates in the server and browser.
2. Retrieve and verify the official episode-index manifest and one selected daily manifest through the Kaggle MCP.
3. Generate the immutable capped episode plan and present it for user approval before any episode JSON transfer.
4. Implement G2 model-facing tensor and neural-policy foundations in small commits; use a private Kaggle notebook for heavy CPU/GPU parity and qualification workflows.
