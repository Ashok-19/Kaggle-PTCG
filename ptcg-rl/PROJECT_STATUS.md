# Project Status

Last updated UTC: 2026-07-22  
Active repository: `https://github.com/Ashok-19/Kaggle-PTCG` (`PRIVATE`)  
Clean lineage root: `08be5cec0fac9a954a3fe127a3f51122be4736d1`  
Last completed milestone: approved private Kaggle G3a input dataset version 1 published and byte-verified; exact notebook retained locally  
Current gate: G3a recurrent PPO correctness proof  
Gate status: G2 PASS / R1 PASS / G3a BLOCKED / NOT_REVIEWED  
Next review required before: accepting any G3a run result, additional episode JSON transfer, Modal execution, deck freeze, or submission

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
| G2 Model/action schema | passed | `reports/artifacts/g2-model-schema-v1.json`, `reports/artifacts/g2-card-table-v1.json`, `reports/artifacts/g2-policy-v1.json`, `reports/evaluations/g2-policy-cpu-gpu-parity-v4.json`, `reports/artifacts/g2-policy-checkpoint-v1.json`, `reports/evaluations/g2-neural-reliability-v1.json`, `reports/gates/g2.json` | PASS after exact 10,000-game T4 x2 reliability qualification and independent downloaded-artifact recalculation; training remains separately unauthorized |
| G3a PPO correctness smoke | blocked | `configs/g3a_evaluation_v1.json`, `configs/g3a_local_correctness_v1.json`, `configs/kaggle/g3a_cloud_correctness_v1.json`, `reports/artifacts/g3a-ppo-local-correctness-v1.json`, `reports/artifacts/g3a-ppo-local-correctness-review-v1.json`, `reports/artifacts/g3a-cloud-correctness-plan-v1.json`, `reports/artifacts/g3a-cloud-correctness-plan-review-v1.json`, `reports/jobs/g3a-cloud-input-publication-v1.json`, `reports/gates/g3a.json` | Contract, local harness, exact plan, explicit user approval and private dataset version 1 passed review; the user-run notebook outputs and strict run review remain open |
| G3b PPO competence | not started | strict thresholds in `DEC-010` | cloud only |
| D1 Deck selection | not started | strict thresholds in `DEC-010` | deck freeze requires approval |
| G4 Modal readiness | not started | | Modal canary requires approval |
| G5 Main champion | not started | | Modal only |
| G6 Final package | not started | | submission requires approval |

## Active Experiments And Jobs

No active long-running jobs. G1R contract repair, one-million-operation corpus, final-source parity, 10,080-game arena, throughput matrix, six-hour RSS soak, independent raw-artifact review, the G2 10,000-game T4 x2 neural reliability qualification, the bounded G3a local PPO correctness matrix, the complete G3a cloud-plan freeze/review lifecycle and private input-dataset publication are complete. Dataset `ashok205/kptcg-g3a-correctness-inputs` version `1` is `READY`; no G3a notebook session or cloud run has started. Verified project compute cost remains USD `0`.

The Kaggle MCP is connected. On 2026-07-19 the account reported approximately 45 GPU hours and 20 TPU hours available for the current quota period, with only seconds consumed. This is capacity information, not authorization to train.

## Open Blockers And Review Boundaries

- G1R has no open blocker.
- The approved R0 plan SHA-256 `eee76a723f8e9d89c29ea34da4b84765128c5eba8d452893a311b3fc5b7d6934` is fully consumed: 20 files, 83,981,423 bytes, largest 6,303,684 bytes and audit SHA-256 `603df727f237982ea64e70b0f5f4ff5e497fdbf8f2c20188007077df284f4bfe`.
- R1 is closed as PASS after complete-audit correction: 2,999 decisions and 3,275 selected options were decoded from the preceding active request; 21 STOP markers and 16 ordered requests were reconstructed. Metadata now binds to official card-data SHA-256 `a0ea63cf7adcb65d35436ce0eb390de6e2e35654a7c67c065a45f4abaa00f373`; semantic stream SHA-256 is `7174dbc493bfee05c5a308b3c551658e8fb9d5e2736a318c56a3e9495fd76806`, independent review found zero mismatches, and peak loader RSS was 68.17578125 MiB. The resolved provenance incident is recorded at `reports/incidents/r1-card-data-provenance-hash.json`. Additional replay retrieval and action-supervision training remain unauthorized.
- G2 is closed as `SUCCEEDED / PASS`.
- The exact cloud plan is frozen and explicitly approved. Dataset `ashok205/kptcg-g3a-correctness-inputs` version `1` is private, `READY` and independently downloaded byte-for-byte; the exact notebook remains local-only. PPO training remains unauthorized for assistant launch because the user will import, launch and monitor the notebook personally. Assistant launch remains unauthorized.
- The strict G3a evaluation contract is frozen at implementation commit `6ca84cf7ccd79e49341998314da6d32aa8f1de45`. The project-native PPO correctness harness is implemented at commits `68407689ccfb18236f14f78dd68360704f408682` and `cae42da47bc9f3491869e8afd0e1254061b9f585`. The provenance-hardened source passed 55 focused tests, an isolated clean suite with 334 passes and four environment-dependent skips, and Ruff under a two-thread CPU limit. Three completed candidate experiments rejected the 512-choice configuration for a `0.75` multi-select score and selected the 1,024-choice `lr=0.005` configuration over the higher-gradient `lr=0.01` alternative. The clean committed matrix ran in 294.369 seconds: all three declared seeds scored `1.0` on bandit, recurrent cue and variable-option/multi-select tasks, equal-budget stateless controls remained `0.5`, recurrent margins were `0.5`, probability replay and initial-ratio errors were `0`, all zero-tolerance counters were `0`, and every model/optimizer/scheduler/counter/league/rollout/RNG checkpoint review passed. The 27,889-byte dashboard-valid report SHA-256 is `868fdd277eeafe96d09138f1a0f70bc50899fd58ee03b49a1fe6d8a3c9f4194e`; the independent recalculation passed. The exact cloud-plan source is commit `78633d33769b0771eecb56e788bb90586acd5864`. It freezes private Kaggle CPU, internet/GPU/TPU off, two active PyTorch threads, one interop thread, zero workers, a four-core hard ceiling, three declared seeds and exactly 100,000 aggregate non-forced choices per seed split into four 25,000-choice streams including the stateless control. The plan requires atomic checkpoints every 4,096 choices or 300 seconds, final exact-budget checkpoints and one intentional fresh-process resume at 12,288 choices per seed. The canonical config SHA-256 is `ea1e722657f358a85f64688e2df90397799bc17920adffe971a3ee7df72c871e`; the plan report SHA-256 is `b826361bc1443682280936c4fc3bdceacbdf916fc829f02deb7ea1ec71b705d7`; the independent clean-bundle review report SHA-256 is `b3340459613a4af46ad2b02602df5641e5b9789f90afefc4e4adbbc95c64c701`. Final validation passed 172 focused G3 tests, the 375-test full Python suite, Ruff, dashboard ingestion with 115 records and zero quarantine, dashboard doctor, seven frontend unit tests, the production build and four browser tests. This closes the immutable plan, approval and input-publication prerequisites only. The assistant did not create or launch a notebook session. The user must run the exact local notebook and provide the saved outputs; no cloud qualification or policy-strength evidence exists.
- G2 model schema v1 is sealed at `61f6f71008c847b03bbab913d767da2c6bc6469311a0fe7249f3d03ee512bf68`; raw serial magnitude and option transport order are outside actor features.
- G2 private card table v1 is sealed at `7aa6384644c5dbc22fe6b7e1e84bf3d274bd35e0ff0b0ab9c9f3bf2e1141f8a0`; names and effect text are excluded from model metadata.
- G2 compact policy v1 is corrected and sealed at 970,022 trainable parameters; architecture SHA-256 is `aff9a5f87e1c472761ea56fda29dd96f1124d75b3a5aaec280185397967c42cf`.
- Current-source private qualification bundle v4 is bound to commit `c660f74b26fca74915931091ac0fe365f7f005f5` with SHA-256 `56b4e93671609a8d24887480cbf1d0dfc0c38b60e1cad55d0cf95f4e50744506`. All 11 entries match the manifest and source bytes; local preflight passed all 10 checks with seven selected gradients and no optimizer or training loop. Historical bundles remain retained only as audit evidence for their recorded source commits.
- Private Kaggle GPU version 1 (`336514431`) on Tesla T4 and CPU version 4 (`336517420`) passed strict combined `atol=rtol=1e-5` parity across 1,596 numeric values with zero failures. The maximum absolute difference was `1.52587890625e-05` and maximum tolerance ratio was `0.4138225953505397`. CPU batch-1 p99 latency was `8.802885 ms`; external HTTP was blocked in both CPU probe attempts.
- Kaggle GPU sessions must be selected manually as `GPU T4 x2`. An automatic CLI launch received a Tesla P100 and was rejected before qualification. The final user-run reliability receipt records exactly two visible Tesla T4 devices and executes one centralized inference server on each GPU.
- G2 checkpoint package v1 is bound to implementation commit `6b3a3b4829b205d62e210fae7e396db33fdb9a5a` and SHA-256 `4dfba2adb9f97607cfa5dabadba075236bb7aae51eafab264584e947feae3827`. It is a 5,429,190-byte sorted `ZIP_STORED` archive containing a pickle-free canonical tensor stream, numeric card table, manifest and fixed reference. Duplicate builds match exactly; current and isolated-source verification reproduced 1,150 numeric and 16 exact actor/value/recurrent/decoder/log-probability values with zero drift; 25 adversarial branches failed closed. No optimizer, training loop, Kaggle run or external mutation occurred.
- G2 neural reliability readiness is sealed at source commit `b536f3ac66796cdabc382f318126a99b0eeeae85`. The harness passes 202 repository tests, independently reviewed local smokes and seven live fail-closed branches. Private dataset `ashok205/g2-neural-reliability-inputs` version 1 is `READY`; its sealed archive is 12,088,771 bytes with SHA-256 `d4fa4a09e5c86cc3a2c93461b2127634dc197a7241d99d36f78bc35ce878b6ec`.
- Final G2 reliability evidence is `reports/evaluations/g2-neural-reliability-v1.json`. The user manually ran `ashok205/kptcg-g2-neural-reliability-v1` (script version id `336684242`) with internet off and two Tesla T4 GPUs. Exactly 10,000 games, 1,213,203 engine requests and 20,791 multi-select requests completed with zero invalid selections, fallbacks, post-terminal actions, recurrent-state violations, nonfinite outputs, crashes or timeouts. The 28,783,333-byte games ledger SHA-256 is `39d7d43d142bec64bcace5da5151ca6bccba2bd533c47d1957a4ad7505cc918f`; all downloaded manifest hashes matched and 21 review fields matched the assistant's independent recalculation exactly. The assistant did not launch or rerun the notebook.
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

1. The user imports `private/kaggle/notebooks/kptcg-g3a-cloud-correctness-v1.ipynb` into a private Kaggle CPU session, attaches only `ashok205/kptcg-g3a-correctness-inputs` version `1`, keeps internet/GPU/TPU off, sets `KPTCG_G3A_TRAINING_APPROVED=YES` and runs all cells without editing.
2. After the user saves the completed notebook version, list all saved outputs with pagination, download the output manifest first, verify every listed byte count and SHA-256, run the strict independent review and keep G3a blocked on any mismatch.
3. Keep additional replay retrieval, action-supervision training, Modal execution, deck freeze and submission blocked until their separate approval gates.
