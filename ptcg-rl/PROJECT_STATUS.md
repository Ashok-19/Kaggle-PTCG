# Project Status

Last updated UTC: 2026-07-30
Active repository: `https://github.com/Ashok-19/Kaggle-PTCG` (`PRIVATE`)  
Clean lineage root: `08be5cec0fac9a954a3fe127a3f51122be4736d1`  
Last completed milestone: DEC-023 completed the balanced 12-file Dries Grimmsnarl calibration with 1,175 teacher decisions; DEC-024 independently froze a zero-transfer current-rank-1 source wait
Current gate: wait for a pinned daily episode dataset containing current rank-1 haggle submission `55104355`; no replay request is currently source-ready
Gate status: G2 PASS / R1 PASS / G3a PASS / G3b BLOCKED / NOT_REVIEWED  
E04 engineering gate: SUCCEEDED / PASS
Gold-path status: DEC-021 FLG DRAGAPULT SCREENING PASS / DEC-022 DRIES SECOND-TEACHER PASS / DEC-023 GRIMMSNARL CALIBRATION PASS / DEC-024 CURRENT-RANK-1 SOURCE WAIT / E04 ZERO-UPDATE QUALIFICATION PASS
Next review required before: preparing any current-rank-1 replay request after a nonzero pinned-dataset intersection, any replay or agent-log transfer, BC/PPO optimizer step, further native E04 execution, external compute, deck freeze or submission

## Mission Clock

- Official close: `2026-08-16T23:59:00Z` (`2026-08-17 05:29 IST`)
- Entry/team-merger deadline: `2026-08-09T23:59:00Z`
- Public notebook-sharing cutoff: `2026-08-02T23:59:00Z`
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
| G3a PPO correctness smoke | passed | `configs/g3a_evaluation_v1.json`, `configs/g3a_local_correctness_v1.json`, `configs/kaggle/g3a_cloud_correctness_v1.json`, `reports/artifacts/g3a-ppo-local-correctness-v1.json`, `reports/artifacts/g3a-ppo-local-correctness-review-v1.json`, `reports/artifacts/g3a-cloud-correctness-plan-v1.json`, `reports/artifacts/g3a-cloud-correctness-plan-review-v1.json`, `reports/jobs/g3a-cloud-input-publication-v3.json`, `reports/evaluations/g3a-cloud-correctness-v1.json`, `reports/artifacts/raw/g3a-cloud-correctness-review-v1.json`, `reports/gates/g3a.json` | PASS after user-run private Kaggle saved version 2, exact 12-stream budgets, three fresh-process resumes, complete 220-entry output-manifest verification and byte-exact independent strict review |
| G3b Pokemon policy competence | blocked | `reports/artifacts/e01-dries-grimmsnarl-calibration-review-v1.json`, `reports/artifacts/raw/e01-live-confirmation-refresh-v2.json`, `docs/decisions/DEC-024_E01_CURRENT_RANK_1_SOURCE_WAIT.md`, `reports/artifacts/e01-live-confirmation-source-wait-review-v1.json`, `configs/gold_path_work_orders_v1.json`, `reports/evaluations/e04-qualification-v1.json`, `reports/artifacts/gold-path-work-orders-review-v1.json`, `reports/gates/g3b.json` | E04 zero-update bridge PASS; exact flg screening PASS; two independent recent teachers qualified; DEC-023 adds 1,175 Dries decisions for 66 episodes and 7,542 decisions total, leaving 134 episodes and 17,458 decisions; current rank-1 haggle submission `55104355` has 76 public episodes but zero files in the latest complete July 29 dataset, so no replay request is ready and confirmation/training remain blocked |
| D1 Deck selection | not started | strict thresholds in `DEC-010` | deck freeze requires approval |
| G4 Modal readiness | not started | | Modal canary requires approval |
| G5 Main champion | not started | | Modal only |
| G6 Final package | not started | | submission requires approval |

## Active Experiments And Jobs

No active long-running jobs. G1R, R1, G2, G3a and the E04 zero-update bridge engineering gate are complete. E01 has transferred exactly 82 replay bodies totaling 453,143,981 bytes under nine consumed one-time approvals: two Benarg files, two Luca teacher-probe files, 12 Luca calibration files, two flg probe files, 12 flg calibration files, 38 flg screening-expansion files, two Dries confirmation-teacher files and 12 Dries Grimmsnarl calibration files. DEC-023 independently qualifies all 12 calibration files as schema version 1, CABT `1.0.0`, module `1.32.2`, exact Marnie's Grimmsnarl ex deck hash `cafa7652a6349be806d8ac2b9abfdb6c72ca3821f368e0d912e2d989f3b54cdd`, current-card compatible and action aligned. The batch adds 1,175 Dries decisions and 2,171 all-player requests; combined confirmation evidence is two teachers, 66 episodes and 7,542 decisions, leaving shortfalls of 134 episodes and 17,458 decisions. A post-calibration metadata refresh found current rank-1 `haggle` submission `55104355` with 76 public episodes, but the latest complete pinned daily dataset `kaggle/pokemon-tcg-ai-battle-episodes-2026-07-29/1` has an exact intersection of zero files and zero bytes. DEC-024 therefore creates no request and authorizes no transfer. No agent log, extra replay, raw export, notebook, model, training run, accelerator job or submission was created or launched. Verified project compute cost remains USD `0`.

The Kaggle MCP is connected. On 2026-07-24 the account reported approximately 24.358 GPU hours and 18.425 TPU hours remaining in the current quota period. This is volatile capacity information, not authorization to train.

## Open Blockers And Review Boundaries

- G1R has no open blocker.
- The approved R0 plan SHA-256 `eee76a723f8e9d89c29ea34da4b84765128c5eba8d452893a311b3fc5b7d6934` is fully consumed: 20 files, 83,981,423 bytes, largest 6,303,684 bytes and audit SHA-256 `603df727f237982ea64e70b0f5f4ff5e497fdbf8f2c20188007077df284f4bfe`.
- R1 is closed as PASS after complete-audit correction: 2,999 decisions and 3,275 selected options were decoded from the preceding active request; 21 STOP markers and 16 ordered requests were reconstructed. Metadata now binds to official card-data SHA-256 `a0ea63cf7adcb65d35436ce0eb390de6e2e35654a7c67c065a45f4abaa00f373`; semantic stream SHA-256 is `7174dbc493bfee05c5a308b3c551658e8fb9d5e2736a318c56a3e9495fd76806`, independent review found zero mismatches, and peak loader RSS was 68.17578125 MiB. The resolved provenance incident is recorded at `reports/incidents/r1-card-data-provenance-hash.json`. Additional replay retrieval and action-supervision training remain unauthorized.
- G2 is closed as `SUCCEEDED / PASS`.
- The corrected exact cloud plan is frozen and explicitly approved. Dataset `ashok205/kptcg-g3a-correctness-inputs` version `3` is private, `READY` and independently downloaded byte-for-byte; versions `1` and `2` are historical only. The exact notebook remains local-only and requires no Kaggle secret, authorization environment variable, authorization cell or external network probe. PPO training remains unauthorized for assistant launch because the user will import, launch and monitor the notebook personally. Assistant launch remains unauthorized.
- The strict G3a evaluation contract is frozen at implementation commit `6ca84cf7ccd79e49341998314da6d32aa8f1de45`. The project-native PPO correctness harness is implemented at commits `68407689ccfb18236f14f78dd68360704f408682` and `cae42da47bc9f3491869e8afd0e1254061b9f585`. The provenance-hardened source passed 55 focused tests, an isolated clean suite with 334 passes and four environment-dependent skips, and Ruff under a two-thread CPU limit. Three completed candidate experiments rejected the 512-choice configuration for a `0.75` multi-select score and selected the 1,024-choice `lr=0.005` configuration over the higher-gradient `lr=0.01` alternative. The clean committed matrix ran in 294.369 seconds: all three declared seeds scored `1.0` on bandit, recurrent cue and variable-option/multi-select tasks, equal-budget stateless controls remained `0.5`, recurrent margins were `0.5`, probability replay and initial-ratio errors were `0`, all zero-tolerance counters were `0`, and every model/optimizer/scheduler/counter/league/rollout/RNG checkpoint review passed. The 27,889-byte dashboard-valid report SHA-256 is `868fdd277eeafe96d09138f1a0f70bc50899fd58ee03b49a1fe6d8a3c9f4194e`; the independent recalculation passed. The corrected cloud-plan source is commit `6b7975bf518c36ff59338b6793ec52530c73f173`. The version-2 manual run exposed that the cloud runner used greedy argmax rollout collection instead of the seed-bound categorical sampling used by the qualified trainer. The corrected plan binds `seeded_categorical` sampling with seed XOR `23063` and restores that RNG exactly through the Torch CPU checkpoint state. It freezes private Kaggle CPU, internet/GPU/TPU off, two active PyTorch threads, one interop thread, zero workers, a four-core hard ceiling, three declared seeds and exactly 100,000 aggregate non-forced choices per seed split into four 25,000-choice streams including the stateless control. The plan requires atomic checkpoints every 4,096 choices or 300 seconds, final exact-budget checkpoints and one intentional fresh-process resume at 12,288 choices per seed. The corrected canonical config SHA-256 is `c0ea3bfa83cc2e86e1933555926c9f957da01ac9618e13f03e9f85d1a6b7957b`; the plan report SHA-256 is `f9e4f554b610a0b60f7b8ed08f6bbb3ea59d12c50f7fb720f8c90383bc196116`; the independent clean-bundle review report SHA-256 is `47b1c937d5bae45197d2287f0ed154604f52d761125bf0343bf5f18a72a9343e`. Pre-publication validation passed 173 focused G3 tests, the 376-test full Python suite and Ruff; final dashboard/browser validation is recorded in the version-3 publication receipt. The user manually ran the corrected notebook as Kaggle saved version 2 / scriptVersionId `337365875`. The complete 220-entry output manifest covered 20,617,497 bytes with zero missing, extra, byte or SHA-256 mismatches; all 12 streams, 84 checkpoint payloads, 84 sidecars and three fresh-process resumes were verified. Every declared seed passed all tasks, recurrent scores were `1.0` versus stateless `0.5`, all replay/resume errors and zero-tolerance counters were zero, and the assistant strict review was byte-identical to the notebook review. G3a is `SUCCEEDED / PASS`; policy strength remains unestablished. The assistant did not create or launch the notebook session.
- The historical G3b planning contract remains byte-frozen at SHA-256 `99cf090df232ffe37504eee4b86ab70554256b5ad89fe972bb9bb5033115bc26` with independent review SHA-256 `23f5c5c02d74c0db8e91652016d20eb755c1eba515a84067fca6c85d7fb4afe0`. DEC-011 supersedes PPO-first sequencing, DEC-012 supersedes E04 sizing, DEC-013–017 preserve provenance and Luca evidence, DEC-018 is superseded unexecuted, DEC-019–021 complete the exact flg screening path, DEC-022 qualifies exact Dries submission `55002825`, DEC-023 completes balanced Grimmsnarl calibration and DEC-024 records the current-rank-1 source wait. The active work-order SHA-256 is `4e65f7ebf2b34fab9178478137c23202ef1a360316d99447dadd149924031883`; independent review file SHA-256 is `b0b033017333f984e27fa998f54cb065df895e6a2855545a92e3563f6ddbe0d9`, self-hash `1ec37283e3269128211d2b985a9e27ecf1423a91d1192c5f47280e51e53a19a5`. The consumed DEC-023 request SHA-256 is `f026a350d9e5c882080f28f60a811d3060f49c7a3c7375dc85e550865d4f9380`, authorized payload SHA-256 is `75bc96fe9f5ab595f1443716a96f47c67843687b32f6d55616b05f9a59c8945d`; calibration review file SHA-256 is `e2b0437f0cf43ebd1c1a1059714d7d435de5c25f95704e6f0aab423a114a8e45`, self-hash `56e7f1d065c0eaf5132bcac710f903ca4bfab236638d5a7d5b62bddd7ea2a871`. The DEC-024 live refresh SHA-256 is `ac8e0a72b9d49a44d1f587929664a444b673866ae677f74f030555e1af889b92`; source-wait review file SHA-256 is `154aae4429f686e69124ccfdd020805196b550425d4f2863bd562643378a00d2`, self-hash `d98f83f8a22b000ec83213a1b0f2703ee9cb171e399c3ccd1ca64cc030d0fa99`. Current downloadable official assets remain byte-identical; hosted runtime behavior after the July 23 update remains unresolved. Policy confirmation remains unproven and training remains unauthorized.
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

### DEC-011 - Supersede PPO-first sequencing with the evidence-gated gold path

- Decision: preserve all accepted evidence, retain the old G3b plan as immutable history, qualify exact-deck teachers and the native zero-update CABT bridge before bounded BC or PPO, cap any later PPO authorization at 500,000 choices before another decision, and keep the unchanged Mega Lucario rule policy as a shippable hedge rather than the frozen final deck.
- Evidence: `docs/decisions/DEC-011_GOLD_PATH_SEQUENCING.md`, `configs/gold_path_work_orders_v1.json`, `reports/artifacts/gold-path-work-orders-review-v1.json`.
- Stop conditions: no replay body, native E04 run, optimizer step, notebook, accelerator, paid compute, deck freeze or submission without the smallest separate explicit approval.
- Compatibility note: the historical G3b integration record remains `PLANNED` and blocked to preserve immutable prior-report checks; active E04 source work is separate and still permits zero meaningful training only.

### DEC-012 - Resize E04 qualification to 180 games

- Decision: preserve the 10,000-meaningful-decision floor and all zero-tolerance conditions, but replace the unsupported 100-game qualification count with exactly 180 games.
- Evidence: `docs/decisions/DEC-012_E04_QUALIFICATION_RESIZED.md`, `reports/artifacts/e04-qualification-contract-review-v1.json`, `configs/e04_qualification_request_v1.json`, `reports/evaluations/e04-qualification-v1.json`.
- Basis: 179 games were required at the accepted smoke's observed minimum decision rate; the approved 180-game run completed with 11,250 meaningful decisions and zero reliability failures.
- Implementation: `PASS`; the authorization is consumed, rerun is unauthorized, and no optimizer step or external compute occurred.

### DEC-013 - Reopen E01-A source provenance

- Decision: block every replay-body and agent-log transfer until the accepted daily manifest object is reproduced or an independently reviewed schema-adapter contract recertifies source identity, field semantics and exact file byte caps.
- Evidence: `docs/decisions/DEC-013_E01_PROVENANCE_PROBE.md`, `reports/artifacts/raw/e01-public-manifest-metadata-v1.json`, `reports/artifacts/e01-teacher-deck-metadata-review-v1.json`, `configs/e01_provenance_probe_request_v1.json`.
- Finding: the same declared version-1 daily manifest differs in SHA-256, byte count and schema; all eight retained episode IDs differ in timestamp and byte metadata.
- Stop conditions: the placeholder remains `request_ready: false`, `authorized: false`, with zero files, zero bytes and no output directory.

### DEC-014 - Reconcile E01 source schema and prepare one provenance probe

- Decision: accept public episode timestamps and team/submission identities plus dataset file-list exact byte counts for provenance probing only; exclude the unavailable historical rating field from authorization and competence claims.
- Evidence: `docs/decisions/DEC-014_E01_SOURCE_SCHEMA_RECONCILED.md`, `reports/artifacts/raw/e01-public-source-schema-reconciliation-raw-v1.json`, `reports/artifacts/e01-source-schema-reconciliation-v1.json`, `configs/e01_provenance_probe_request_v2.json`.
- Exact request: `87703034.json`, 3,641,302 bytes, Benarg submission `54933084` versus junlee789 submission `54775633`, private quarantine only.
- Stop conditions: request remains `authorized: false`; no agent logs, additional replay, raw-step export, labels, training or external compute.

### DEC-015 - Complete the smallest same-submission consistency probe

- Decision: execute exactly one additional replay from Benarg submission `54933084` for deck and aggregate action consistency.
- Evidence: `docs/decisions/DEC-015_E01_SAME_SUBMISSION_CONSISTENCY_PROBE.md`, `configs/e01_same_submission_consistency_request_v1.json`, `reports/artifacts/e01-same-submission-consistency-review-v1.json`.
- Result: `87741212.json`, 559,779 bytes, SHA-256 `be962b8ca9146320f7d8976460c20244cf5e8bf6b026816816bc4b4ec91a87d2`; exact Benarg deck match and action alignment PASS, but only 65 combined Benarg teacher decisions.
- Stop conditions: authorization consumed; no agent logs, third replay, raw export, labels, training or external compute.

### DEC-016 - Complete the strongest replay-rich gold-region teacher probe

- Decision: execute exactly two opposite-slot/opposite-result files for current rank-2 Luca submission `54863653`.
- Evidence: `docs/decisions/DEC-016_E01_LUCA_GOLD_TEACHER_PROBE.md`, `configs/e01_luca_gold_teacher_probe_request_v1.json`, `reports/artifacts/e01-luca-gold-teacher-probe-review-v1.json`.
- Result: 1,313,221 bytes transferred; exact Luca deck and action alignment PASS; teacher strength PASS; module versions are `1.32.2` and `1.32.1`; 37 Luca decisions leave a 4,963-decision screening shortfall.
- Stop conditions: authorization consumed; no logs, third replay, exports, labels, training or external compute.

### DEC-017 - Complete the bounded Luca same-version calibration batch

- Decision: execute exactly 12 Luca files balanced three-per-seat/result stratum for module `1.32.2` calibration and decision-density measurement.
- Evidence: `docs/decisions/DEC-017_E01_LUCA_SAME_VERSION_CALIBRATION.md`, `configs/e01_luca_same_version_calibration_request_v1.json`, `reports/artifacts/e01-luca-same-version-calibration-review-v1.json`.
- Result: 12 files / 63,828,057 bytes; all module `1.32.2`; exact Luca deck and action alignment PASS; 1,170 Luca decisions and 1,207 cumulative observed decisions leave a 3,793-decision shortfall.
- Stop conditions: authorization consumed; no logs, extra replay, raw exports, labels, training or external compute.

### DEC-018 - Supersede the calibrated Luca screening expansion without execution

- Original decision: prepare 51 named Luca files totaling 270,807,738 bytes.
- July 27 result: superseded by DEC-019 after Luca fell to rank 14 and replaced its active submission; no DEC-018 file was transferred and the request remains unauthorized with absent output path.

### DEC-019 - Refresh the live gold path and complete the current rank-1 probe

- Decision: select current rank-1 `flg` submission `55004495` and execute exactly two opposite-seat/opposite-result July 26 files totaling 3,996,398 bytes.
- Evidence: `docs/decisions/DEC-019_E01_LIVE_GOLD_TEACHER_REFRESH.md`, `reports/artifacts/raw/e01-live-gold-refresh-v1.json`, `configs/e01_flg_gold_teacher_probe_request_v1.json`, `reports/artifacts/e01-flg-gold-teacher-probe-review-v1.json`.
- Result: both module `1.32.2`; exact Dragapult ex deck hash and action alignment PASS; 94 teacher decisions leave a 4,906-decision shortfall.
- Stop conditions: authorization consumed; no third replay, logs, exports, labels, training or external compute.

### DEC-020 - Complete the balanced current rank-1 Dragapult calibration batch

- Decision: execute exactly 12 files totaling 63,562,985 bytes, using the 20th, 50th and 80th file-byte quantiles in each seat/result stratum.
- Evidence: `docs/decisions/DEC-020_E01_FLG_DRAGAPULT_CALIBRATION.md`, `configs/e01_flg_dragapult_calibration_request_v1.json`, `reports/artifacts/e01-flg-dragapult-calibration-review-v1.json`.
- Result: all 12 files are module `1.32.2`, exact-deck consistent, current-card compatible and action aligned; 1,292 calibration decisions and 1,386 cumulative observed decisions leave a 3,614-decision shortfall.
- Stop conditions: authorization consumed; no logs, extra replay, exports, labels, training or external compute.

### DEC-021 - Complete the conservative current rank-1 Dragapult screening expansion

- Decision: execute exactly 38 files totaling 254,237,550 bytes, balanced 10/10/9/9 across seat/result strata and independently reject any nonmatching file.
- Evidence: `docs/decisions/DEC-021_E01_FLG_DRAGAPULT_SCREENING_EXPANSION.md`, `configs/e01_flg_dragapult_screening_expansion_request_v1.json`, `reports/artifacts/e01-flg-dragapult-screening-expansion-review-v1.json`.
- Result: all 38 files qualify; 4,954 teacher decisions and 8,609 all-player requests are added, producing 6,340 cumulative flg decisions, zero rejected files and a passed 5,000-decision screening floor.
- Stop conditions: authorization consumed; no logs, extra replay, exports, labels, training or external compute.

### DEC-022 - Qualify the current rank-1 Dries confirmation teacher

- Decision: execute exactly `88281294.json` and `88332011.json`, totaling 1,135,238 bytes, as the smallest opposite-seat/opposite-result pair for Dries submission `55002825`.
- Evidence: `reports/artifacts/raw/e01-live-confirmation-refresh-v1.json`, `docs/decisions/DEC-022_E01_DRIES_CONFIRMATION_TEACHER_PROBE.md`, `configs/e01_dries_confirmation_teacher_probe_request_v1.json`, `reports/artifacts/e01-dries-confirmation-teacher-probe-review-v1.json`.
- Result: both files are module `1.32.2`, exact-deck consistent, current-card compatible and action aligned. The deck hash is `cafa7652a6349be806d8ac2b9abfdb6c72ca3821f368e0d912e2d989f3b54cdd`, labeled Marnie's Grimmsnarl ex; 27 teacher decisions qualify the second independent recent teacher.
- Stop conditions: authorization consumed; no logs, third replay, exports, labels, training or external compute.

### DEC-023 - Complete balanced Dries Grimmsnarl calibration

- Decision: execute exactly 12 files totaling 60,869,451 bytes, balanced three per seat/result stratum using the 20th, 50th and 80th file-byte quantiles after excluding the DEC-022 pair.
- Evidence: `docs/decisions/DEC-023_E01_DRIES_GRIMMSNARL_CALIBRATION.md`, `configs/e01_dries_grimmsnarl_calibration_request_v1.json`, `reports/artifacts/e01-dries-grimmsnarl-calibration-review-v1.json`.
- Result: all 12 files qualify as module `1.32.2`, exact-deck consistent, current-card compatible and action aligned; they add 1,175 teacher decisions and 2,171 all-player requests. Confirmation now contains two teachers, 66 episodes and 7,542 decisions.
- Stop conditions: authorization consumed; no logs, additional replay, exports, labels, training or external compute.

### DEC-024 - Wait for a versioned current-rank-1 source

- Decision: do not prepare a replay request while current rank-1 haggle submission `55104355` has zero files in the latest complete pinned daily dataset.
- Evidence: `reports/artifacts/raw/e01-live-confirmation-refresh-v2.json`, `docs/decisions/DEC-024_E01_CURRENT_RANK_1_SOURCE_WAIT.md`, `reports/artifacts/e01-live-confirmation-source-wait-review-v1.json`.
- Result: haggle has 76 public episodes across all four strata, but `kaggle/pokemon-tcg-ai-battle-episodes-2026-07-29/1` predates the submission and contains zero matching files and bytes. No request or output directory exists.
- Stop conditions: replay transfer, logs, exports, labels, training, compute and submission remain unauthorized.

## Immediate Next Actions

1. Refresh metadata only after a pinned daily dataset can contain submission `55104355`, or when the live rank-1 team/submission changes.
2. Prepare a bounded replay request only after a nonzero exact dataset intersection is proven; leave that request unauthorized for separate explicit approval.
3. Keep every replay transfer, agent log, BC, PPO, self-play, notebook, accelerator, Modal, E04 rerun, deck freeze and submission blocked until separate evidence and approval gates.
