# Project Status

Last updated UTC: 2026-07-19  
Active repository: `https://github.com/Ashok-19/Kaggle-PTCG` (`PRIVATE`)  
Clean lineage root: `08be5cec0fac9a954a3fe127a3f51122be4736d1`  
Last completed gate: R1 version-pinned semantic replay pipeline (`PASS`)  
Current gate: G2 model qualification  
Gate status: G2 RUNNING / R1 PASS  
Next review required before: any additional episode JSON transfer, G3 training, Modal execution, deck freeze, or submission

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
- A private Kaggle development probe observed Python `3.12.13` and PyTorch `2.10.0+cpu`; this does not resolve the separate provisional submission-runtime Python `3.11.x` record.
- Dashboard dependencies remain isolated in the `dashboard` dependency group.
- The full read-only dashboard expansion is complete at commit `e35b4d07f8cad02edbb9ab6a3b986f9f8416113d`; source changes auto-sync and the browser refreshes every 15 seconds.
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
| R1 Replay/meta pipeline | passed | `reports/replays/r1-semantic-loader.json`, `reports/replays/r1-independent-review.json`, `reports/gates/r1.json` | PASS after independent semantic stream and aggregate recalculation |
| G2 Model/action schema | running | `reports/artifacts/g2-model-schema-v1.json`, `reports/artifacts/g2-card-table-v1.json`, `reports/artifacts/g2-policy-v1.json`, `reports/evaluations/g2-policy-cpu-gpu-parity-v4.json`, `reports/gates/g2.json` | projection, static table, compact model and strict Kaggle CPU/T4 parity PASS; checkpoint package and 10k-game reliability pending; training blocked |
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
- The approved R0 plan SHA-256 `eee76a723f8e9d89c29ea34da4b84765128c5eba8d452893a311b3fc5b7d6934` is fully consumed: 20 files, 83,981,423 bytes, largest 6,303,684 bytes and audit SHA-256 `603df727f237982ea64e70b0f5f4ff5e497fdbf8f2c20188007077df284f4bfe`.
- R1 is closed as PASS after complete-audit correction: 2,999 decisions and 3,275 selected options were decoded from the preceding active request; 21 STOP markers and 16 ordered requests were reconstructed. Metadata now binds to official card-data SHA-256 `a0ea63cf7adcb65d35436ce0eb390de6e2e35654a7c67c065a45f4abaa00f373`; semantic stream SHA-256 is `7174dbc493bfee05c5a308b3c551658e8fb9d5e2736a318c56a3e9495fd76806`, independent review found zero mismatches, and peak loader RSS was 68.17578125 MiB. The resolved provenance incident is recorded at `reports/incidents/r1-card-data-provenance-hash.json`. Additional replay retrieval and action-supervision training remain unauthorized.
- G2 may implement and qualify the model/action contract. It may not start PPO training.
- G2 model schema v1 is sealed at `61f6f71008c847b03bbab913d767da2c6bc6469311a0fe7249f3d03ee512bf68`; raw serial magnitude and option transport order are outside actor features.
- G2 private card table v1 is sealed at `7aa6384644c5dbc22fe6b7e1e84bf3d274bd35e0ff0b0ab9c9f3bf2e1141f8a0`; names and effect text are excluded from model metadata.
- G2 compact policy v1 is corrected and sealed at 970,022 trainable parameters; architecture SHA-256 is `aff9a5f87e1c472761ea56fda29dd96f1124d75b3a5aaec280185397967c42cf`.
- Current-source private qualification bundle v4 is bound to commit `c660f74b26fca74915931091ac0fe365f7f005f5` with SHA-256 `56b4e93671609a8d24887480cbf1d0dfc0c38b60e1cad55d0cf95f4e50744506`. All 11 entries match the manifest and source bytes; local preflight passed all 10 checks with seven selected gradients and no optimizer or training loop. Historical bundles remain retained only as audit evidence for their recorded source commits.
- Private Kaggle GPU version 1 (`336514431`) on Tesla T4 and CPU version 4 (`336517420`) passed strict combined `atol=rtol=1e-5` parity across 1,596 numeric values with zero failures. The maximum absolute difference was `1.52587890625e-05` and maximum tolerance ratio was `0.4138225953505397`. CPU batch-1 p99 latency was `8.802885 ms`; external HTTP was blocked in both CPU probe attempts.
- Kaggle GPU sessions must be selected manually as `GPU T4 x2`. An automatic CLI launch received a Tesla P100 and was rejected before qualification. Future receipts record one or two visible T4 devices and execute deterministically on CUDA device 0.
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

1. Implement and verify the checkpoint package contract without starting PPO training.
2. Execute the 10,000-complete-game neural-policy reliability gate with zero tolerance for invalid selections, crashes, timeouts, fallbacks, stale requests, post-terminal dispatches or recurrent ownership/reset violations.
3. Independently review checkpoint and reliability evidence before any G2 `PASS` decision; training remains blocked.
