# Project Status

Last updated UTC: 2026-07-17  
Active repository: `https://github.com/Ashok-19/Kaggle-PTCG` (`PRIVATE`)  
Clean lineage root: `08be5cec0fac9a954a3fe127a3f51122be4736d1`  
Current gate: G1 Engine contract and tensor schema  
Gate status: planned and authorized next work  
Next review required before: meaningful cloud training or a material architecture change

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
| G1 Engine contract/tensor schema | planned | `reports/gates/g1.json` | authorized next work |
| R1 Replay/meta pipeline | not started | | |
| G2 Model/action schema | not started | | |
| G3a PPO correctness smoke | not started | | cloud smoke only |
| G3b PPO competence | not started | | cloud only |
| D1 Deck selection | not started | | |
| G4 Modal readiness | not started | | |
| G5 Main champion | not started | | Modal only |
| G6 Final package | not started | | |

## Active Experiments And Jobs

None. Verified project compute cost remains USD `0`.

## Open Blockers

None for agent implementation. The exact Python patch and timeout remain final
submission-qualification notes, not G1 blockers.

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

## Immediate Next Actions

1. Implement the exact CABT environment/action contract and tensor schema.
2. Build replay index/filter/download and dashboard metadata integration.
3. Keep the first training smoke on Colab/Kaggle and main training on Modal.
