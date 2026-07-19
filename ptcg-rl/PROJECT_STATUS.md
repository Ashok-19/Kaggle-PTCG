# Project Status

Last updated UTC: 2026-07-19  
Active repository: `https://github.com/Ashok-19/Kaggle-PTCG` (`PRIVATE`)  
Clean lineage root: `08be5cec0fac9a954a3fe127a3f51122be4736d1`  
Last completed gate: G1R environment/action/recurrent contract recertification (`PASS`)  
Current gate: G2 plus parallel R1 work-order review  
Gate status: NOT_STARTED / REVIEW_REQUIRED  
Next review required before: G2 or R1 implementation; training remains unauthorized

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
- Exact submission Python patch and timeout verification are deferred to final
  packaging/model compatibility; the submission doctor continues to enforce them.
- Dashboard dependencies remain isolated in the `dashboard` dependency group.

## Compute Roles

| Environment | Role |
|---|---|
| Local Ubuntu | Code, dashboard, metadata, filtered acquisition, unit/contract tests, tiny engine smoke, packaging and final-model inference/runtime tests |
| Colab/Kaggle | Small training smoke, short validation, profiling and controlled preliminary experiments |
| Modal | Main self-play, PPO/league training, large evaluation and long-running compute |

No meaningful self-play, PPO, league training or large evaluation may run locally.

## Gate Ledger

| Gate | Status | Evidence | Review decision |
|---|---|---|---|
| G0 Repository/environment | passed | `REPOSITORY_CONSOLIDATION_REPORT.md`, G0 reports | PASS with Packages waiver |
| G1 Engine contract/tensor schema | superseded | `G1_ENVIRONMENT_ACTION_CONTRACT_REPORT.md` | historical smoke only |
| G1R Contract recertification | passed | `reports/gates/g1r.json`, `G1R_REMEDIATION_AND_ACCEPTANCE_REPORT.md` | PASS |
| R1 Replay/meta pipeline | not started | | |
| G2 Model/action schema | not started | | |
| G3a PPO correctness smoke | not started | | cloud smoke only |
| G3b PPO competence | not started | | cloud only |
| D1 Deck selection | not started | | |
| G4 Modal readiness | not started | | |
| G5 Main champion | not started | | Modal only |
| G6 Final package | not started | | |

## Active Experiments And Jobs

No active long-running jobs. G1R contract repair, one-million-operation corpus,
final-source parity, 10,080-game arena, throughput matrix, six-hour RSS soak, and
independent raw-artifact review are complete. Verified project compute cost remains USD `0`.

## Open Blockers

- G1R has no open blocker. R0/R1 replay acquisition remains not started and transferred
  zero episode JSON files.
- The exact Python patch and timeout remain final submission-qualification notes,
  not G1R blockers.

## Decision Log

### DEC-006 - Existing repository is sole source of truth

- Decision: replace `Ashok-19/Kaggle-PTCG/main` with the verified clean lineage
  and consolidate the dashboard there without merging contaminated ancestry.
- Evidence: restricted-history scan, exact migration tree comparison and
  force-with-lease receipt in `REPOSITORY_CONSOLIDATION_REPORT.md`.
- Rollback: the private RL repository remains an inactive migration backup.

### DEC-007 - Cloud-first training execution

- Decision: local work stops at development/tiny smoke/package/runtime tests;
  Colab/Kaggle own small training smoke and Modal owns meaningful training.
- Expected effect: protect local time/resources while keeping correctness fast.
- Stop condition: any local command proposes meaningful self-play or training.

### DEC-008 - Reopen G1 as G1R

- Decision: retain the former G1 report as historical evidence and require the
  original handbook acceptance criteria plus independent recalculation.
- Evidence: `docs/decisions/DEC-008_G1_REOPENED.md`.
- Stop condition: any missing criterion keeps G1R blocked.

### DEC-009 - Close G1R

- Decision: accept the final-source qualifying evidence and independent raw-artifact
  recalculation; close G1R as `SUCCEEDED / PASS`.
- Evidence: `docs/decisions/DEC-009_G1R_CLOSED.md`.
- Next boundary: G2 plus parallel R1 require a fresh reviewed work order; training remains
  unauthorized.

## Immediate Next Actions

1. Review and authorize the G2 model/action-schema work order.
2. Run R1 replay/meta manifest implementation in parallel under explicit transfer caps.
3. After G2 review, launch the first small Colab/Kaggle training smoke; keep main training on Modal.
