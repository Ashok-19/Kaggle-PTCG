# Project Status

Last updated UTC: 2026-08-06
Active repository: `https://github.com/Ashok-19/Kaggle-PTCG` (`PRIVATE`)  
Clean lineage root: `08be5cec0fac9a954a3fe127a3f51122be4736d1`  
Last completed milestone: DEC-043 prepared corrected production BC notebook v2 after DEC-042 mount-count preflight failure
Current gate: corrected notebook request `configs/e01_production_recurrent_bc_notebook_request_v2.json` at SHA-256 `93ad27ae290bdf56f0e6259a252625d7bd15150054d85139f29c9cae7fb7f4eb` is READY_UNAUTHORIZED; v1 failed before replay reads or training
Gate status: G2 PASS / R1 PASS / G3a PASS / G3b BLOCKED / NOT_REVIEWED  
E04 engineering gate: SUCCEEDED / PASS
Gold-path status: CORPUS V3 362 EPISODES / 25,056 TARGETS / RETAINED DATASET VALID / SOURCE BUNDLE V2 VALID / PRODUCTION BC NOTEBOOK V2 READY / TEST SEALED / TRAINING BLOCKED
Next review required before: creating/running corrected notebook v2, any replay-body read, optimizer step, training/evaluation, model promotion, submission, commit, or push

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

No heavy experiment, meaningful self-play, optimizer-backed training, PPO, league training or large evaluation may run locally. Local work is limited to source changes, metadata, deterministic planning, tests, packaging and very light bounded smokes. Heavier workflows default to private Kaggle CPU with stable versioned inputs. GPU, TPU and every training run require separate exact approval. Every Kaggle workflow must be private, bounded, reproducible and artifact-backed.

## Gate Ledger

| Gate | Status | Evidence | Review decision |
|---|---|---|---|
| G0 Repository/environment | passed | `REPOSITORY_CONSOLIDATION_REPORT.md`, G0 reports | PASS with Packages waiver |
| G1 Engine contract/tensor schema | superseded | `G1_ENVIRONMENT_ACTION_CONTRACT_REPORT.md` | historical smoke only |
| G1R Contract recertification | passed | `reports/gates/g1r.json`, `G1R_REMEDIATION_AND_ACCEPTANCE_REPORT.md` | PASS |
| R1 Replay/meta pipeline | passed | `reports/replays/r1-semantic-loader.json`, `reports/replays/r1-independent-review.json`, `reports/gates/r1.json` | PASS after independent semantic stream and aggregate recalculation |
| G2 Model/action schema | passed | `reports/artifacts/g2-model-schema-v1.json`, `reports/artifacts/g2-card-table-v1.json`, `reports/artifacts/g2-policy-v1.json`, `reports/evaluations/g2-policy-cpu-gpu-parity-v4.json`, `reports/artifacts/g2-policy-checkpoint-v1.json`, `reports/evaluations/g2-neural-reliability-v1.json`, `reports/gates/g2.json` | PASS after exact 10,000-game T4 x2 reliability qualification and independent downloaded-artifact recalculation; training remains separately unauthorized |
| G3a PPO correctness smoke | passed | `configs/g3a_evaluation_v1.json`, `configs/g3a_local_correctness_v1.json`, `configs/kaggle/g3a_cloud_correctness_v1.json`, `reports/artifacts/g3a-ppo-local-correctness-v1.json`, `reports/artifacts/g3a-ppo-local-correctness-review-v1.json`, `reports/artifacts/g3a-cloud-correctness-plan-v1.json`, `reports/artifacts/g3a-cloud-correctness-plan-review-v1.json`, `reports/jobs/g3a-cloud-input-publication-v3.json`, `reports/evaluations/g3a-cloud-correctness-v1.json`, `reports/artifacts/raw/g3a-cloud-correctness-review-v1.json`, `reports/gates/g3a.json` | PASS after user-run private Kaggle saved version 2, exact 12-stream budgets, three fresh-process resumes, complete 220-entry output-manifest verification and byte-exact independent strict review |
| G3b Pokemon policy competence | blocked | `docs/decisions/DEC-025_E01_LIVE_GOLD_REFRESH_CORPUS_FREEZE.md`, `reports/artifacts/raw/e01-live-gold-refresh-20260804-v1.json`, `reports/artifacts/e01-approved-replay-corpus-manifest-v1.json`, `reports/artifacts/e01-approved-replay-corpus-review-v1.json`, `reports/artifacts/e01-approved-replay-policy-loss-recount-v1.json`, `configs/e01_majkel_live_gold_teacher_probe_request_v1.json`, `reports/artifacts/e01-majkel-live-gold-teacher-probe-review-v1.json`, `configs/e01_bc_engineering_canary_request_v1.json`, `reports/gates/g3b.json` | The exact Majkel pair was consumed at 832,877 bytes and passed body-level review: same Mega Lucario deck, opposite seats, both wins, valid current-card construction and action alignment, with a real module transition from `1.32.2` to `1.32.3`. It contains 35 teacher requests, 3 forced singletons and 32 potential policy-loss targets, but no corpus or label promotion is authorized. The frozen approved corpus remains 66 episodes and 7,140 policy-loss targets; BC and all training remain blocked. |
| D1 Deck selection | not started | strict thresholds in `DEC-010` | deck freeze requires approval |
| G4 Modal readiness | not started | | Modal canary requires approval |
| G5 Main champion | not started | | Modal only |
| G6 Final package | not started | | submission requires approval |

## Active Experiments And Jobs

Corpus v3 evidence is complete. DEC-031 promoted one exact prequalified module-1.32.4 metadata record without rereading its body, then reviewed the first 24 remaining approved bodies in frozen order. The run read 98,058,852 new bytes, stopped immediately after `90004101.json` raised the total from 24,987 to 25,056 policy-loss targets, and left 23 approved bodies unread. Corpus v3 contains 362 unique episodes and passes the frozen 25,000-target floor.

No active long-running jobs. Private Kaggle CPU notebook `ashok205/kptcg-e01-corpus-target-supplement-v2` saved version 1 produced exactly four approved metadata outputs, exported zero replay bodies and zero agent logs, generated zero training labels, and performed zero optimizer steps or training. Production recurrent BC remains separately unauthorized.

The exact local-CPU BC engineering canary is also consumed. A forced-only recurrent chunk caused a fail-closed stop after 10 optimizer steps; the scheduler was corrected to skip that zero-loss chunk and exactly 54 additional steps completed, preserving the approved 64-step cumulative cap. Loss and gradients were finite and the step-32 checkpoint restored exactly. The checkpoint is permanently non-promotable and no policy competence is claimed. Production label materialization and training remain unauthorized.

## Open Blockers And Review Boundaries

- G1R has no open blocker.
- The approved R0 plan SHA-256 `eee76a723f8e9d89c29ea34da4b84765128c5eba8d452893a311b3fc5b7d6934` is fully consumed: 20 files, 83,981,423 bytes, largest 6,303,684 bytes and audit SHA-256 `603df727f237982ea64e70b0f5f4ff5e497fdbf8f2c20188007077df284f4bfe`.
- R1 is closed as PASS after complete-audit correction: 2,999 decisions and 3,275 selected options were decoded from the preceding active request; 21 STOP markers and 16 ordered requests were reconstructed. Metadata now binds to official card-data SHA-256 `a0ea63cf7adcb65d35436ce0eb390de6e2e35654a7c67c065a45f4abaa00f373`; semantic stream SHA-256 is `7174dbc493bfee05c5a308b3c551658e8fb9d5e2736a318c56a3e9495fd76806`, independent review found zero mismatches, and peak loader RSS was 68.17578125 MiB. The resolved provenance incident is recorded at `reports/incidents/r1-card-data-provenance-hash.json`. Additional replay retrieval and action-supervision training remain unauthorized.
- G2 is closed as `SUCCEEDED / PASS`.
- The corrected exact cloud plan is frozen and explicitly approved. Dataset `ashok205/kptcg-g3a-correctness-inputs` version `3` is private, `READY` and independently downloaded byte-for-byte; versions `1` and `2` are historical only. The exact notebook remains local-only and requires no Kaggle secret, authorization environment variable, authorization cell or external network probe. PPO training remains unauthorized for assistant launch because the user will import, launch and monitor the notebook personally. Assistant launch remains unauthorized.
- The strict G3a evaluation contract is frozen at implementation commit `6ca84cf7ccd79e49341998314da6d32aa8f1de45`. The project-native PPO correctness harness is implemented at commits `68407689ccfb18236f14f78dd68360704f408682` and `cae42da47bc9f3491869e8afd0e1254061b9f585`. The provenance-hardened source passed 55 focused tests, an isolated clean suite with 334 passes and four environment-dependent skips, and Ruff under a two-thread CPU limit. Three completed candidate experiments rejected the 512-choice configuration for a `0.75` multi-select score and selected the 1,024-choice `lr=0.005` configuration over the higher-gradient `lr=0.01` alternative. The clean committed matrix ran in 294.369 seconds: all three declared seeds scored `1.0` on bandit, recurrent cue and variable-option/multi-select tasks, equal-budget stateless controls remained `0.5`, recurrent margins were `0.5`, probability replay and initial-ratio errors were `0`, all zero-tolerance counters were `0`, and every model/optimizer/scheduler/counter/league/rollout/RNG checkpoint review passed. The 27,889-byte dashboard-valid report SHA-256 is `868fdd277eeafe96d09138f1a0f70bc50899fd58ee03b49a1fe6d8a3c9f4194e`; the independent recalculation passed. The corrected cloud-plan source is commit `6b7975bf518c36ff59338b6793ec52530c73f173`. The version-2 manual run exposed that the cloud runner used greedy argmax rollout collection instead of the seed-bound categorical sampling used by the qualified trainer. The corrected plan binds `seeded_categorical` sampling with seed XOR `23063` and restores that RNG exactly through the Torch CPU checkpoint state. It freezes private Kaggle CPU, internet/GPU/TPU off, two active PyTorch threads, one interop thread, zero workers, a four-core hard ceiling, three declared seeds and exactly 100,000 aggregate non-forced choices per seed split into four 25,000-choice streams including the stateless control. The plan requires atomic checkpoints every 4,096 choices or 300 seconds, final exact-budget checkpoints and one intentional fresh-process resume at 12,288 choices per seed. The corrected canonical config SHA-256 is `c0ea3bfa83cc2e86e1933555926c9f957da01ac9618e13f03e9f85d1a6b7957b`; the plan report SHA-256 is `f9e4f554b610a0b60f7b8ed08f6bbb3ea59d12c50f7fb720f8c90383bc196116`; the independent clean-bundle review report SHA-256 is `47b1c937d5bae45197d2287f0ed154604f52d761125bf0343bf5f18a72a9343e`. Pre-publication validation passed 173 focused G3 tests, the 376-test full Python suite and Ruff; final dashboard/browser validation is recorded in the version-3 publication receipt. The user manually ran the corrected notebook as Kaggle saved version 2 / scriptVersionId `337365875`. The complete 220-entry output manifest covered 20,617,497 bytes with zero missing, extra, byte or SHA-256 mismatches; all 12 streams, 84 checkpoint payloads, 84 sidecars and three fresh-process resumes were verified. Every declared seed passed all tasks, recurrent scores were `1.0` versus stateless `0.5`, all replay/resume errors and zero-tolerance counters were zero, and the assistant strict review was byte-identical to the notebook review. G3a is `SUCCEEDED / PASS`; policy strength remains unestablished. The assistant did not create or launch the notebook session.
- The historical G3b planning contract remains byte-frozen at SHA-256 `99cf090df232ffe37504eee4b86ab70554256b5ad89fe972bb9bb5033115bc26` with independent review SHA-256 `23f5c5c02d74c0db8e91652016d20eb755c1eba515a84067fca6c85d7fb4afe0`. DEC-011 supersedes PPO-first sequencing, DEC-012 supersedes E04 sizing, DEC-013–017 preserve provenance and Luca evidence, DEC-018 is superseded unexecuted, DEC-019–021 complete the exact flg screening path, DEC-022 qualifies exact Dries submission `55002825`, DEC-023 completes balanced Grimmsnarl calibration and DEC-024 records the current-rank-1 source wait. The active work-order SHA-256 is `eb92c61eeaca805864fa571972c4806a314752bfa08b1b6d751be8d697802176`; independent review file SHA-256 is `ba91b59c2f3120e5d145fab32d5695561e7f454d37e9b80a5f61d7796af2c362`, self-hash `71df44763ba4f12e49a1a382abdc0b93b485c7e2c9f83dc86566407acff6119b`. The consumed DEC-023 request SHA-256 is `f026a350d9e5c882080f28f60a811d3060f49c7a3c7375dc85e550865d4f9380`, authorized payload SHA-256 is `75bc96fe9f5ab595f1443716a96f47c67843687b32f6d55616b05f9a59c8945d`; calibration review file SHA-256 is `e2b0437f0cf43ebd1c1a1059714d7d435de5c25f95704e6f0aab423a114a8e45`, self-hash `56e7f1d065c0eaf5132bcac710f903ca4bfab236638d5a7d5b62bddd7ea2a871`. The DEC-024 live refresh SHA-256 is `ac8e0a72b9d49a44d1f587929664a444b673866ae677f74f030555e1af889b92`; source-wait review file SHA-256 is `154aae4429f686e69124ccfdd020805196b550425d4f2863bd562643378a00d2`, self-hash `d98f83f8a22b000ec83213a1b0f2703ee9cb171e399c3ccd1ca64cc030d0fa99`. Current downloadable official assets remain byte-identical; hosted runtime behavior after the July 23 update remains unresolved. Policy confirmation remains unproven and training remains unauthorized.
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

### DEC-025 - Live source ready and approved corpus frozen

- Evidence: `reports/artifacts/raw/e01-live-gold-refresh-20260804-v1.json`, `reports/artifacts/e01-approved-replay-corpus-manifest-v1.json`, `reports/artifacts/e01-approved-replay-corpus-review-v1.json`, `reports/artifacts/e01-approved-replay-policy-loss-recount-v1.json`, `reports/artifacts/e01-majkel-live-gold-teacher-contract-review-v1.json`, `reports/artifacts/e01-majkel-live-gold-teacher-probe-review-v1.json`, `reports/artifacts/e01-bc-engineering-canary-preflight-review-v1.json`.
- Outcome: the exact Majkel two-file request is consumed and passed contract review, including a reviewed `1.32.2` to `1.32.3` module transition and exact Mega Lucario deck consistency. Its 32 potential policy-loss targets are not promoted. The approved corpus remains frozen at 66 episodes and 7,140 valid policy-loss targets; the BC canary, training and submission remain blocked.

### DEC-024 - Wait for a versioned current-rank-1 source

- Decision: do not prepare a replay request while current rank-1 haggle submission `55104355` has zero files in the latest complete pinned daily dataset.
- Evidence: `reports/artifacts/raw/e01-live-confirmation-refresh-v2.json`, `docs/decisions/DEC-024_E01_CURRENT_RANK_1_SOURCE_WAIT.md`, `reports/artifacts/e01-live-confirmation-source-wait-review-v1.json`.
- Result: haggle has 76 public episodes across all four strata, but `kaggle/pokemon-tcg-ai-battle-episodes-2026-07-29/1` predates the submission and contains zero matching files and bytes. No request or output directory exists.
- Stop conditions: replay transfer, logs, exports, labels, training, compute and submission remain unauthorized.

### DEC-027 - Initial training configuration frozen

- Primary teacher: Majkel1337, team `16374395`, active submission `55186239`.
- Initial BC deck: Mega Lucario ex, exact multiset SHA-256 `dc8571d0bc2e546a1f85b938696cfc40a1451c68a4ccc1f695e7c3e1c74f1278`.
- Architecture: the sealed 970,022-parameter G2 recurrent semantic policy, architecture SHA-256 `aff9a5f87e1c472761ea56fda29dd96f1124d75b3a5aaec280185397967c42cf`.
- Data policy: retain the 66-episode multi-teacher corpus and prepare the exact remaining 269-file Majkel review capped at `1,030,207,171` new bytes; the two reviewed files are reused.
- Execution sequence: the exact 64-step BC canary and exact data review may run in parallel after separate approvals; production BC follows only after both pass and corpus v2 is hash-frozen.
- Final submission deck remains unfrozen pending D1 cross-deck and important-matchup evaluation.

### DEC-028 - Corpus v2 and BC canary closeout

- Exact Majkel review: 269/269 files qualified, zero rejected, 1,030,207,171 new bytes read, zero replay exports.
- Corpus v2: 337 episodes and 23,460 valid targets; the 25,000-target production floor is short by 1,540.
- BC canary: 64 cumulative local CPU AdamW steps, finite loss/gradients, exact step-32 restore, permanently non-promotable.
- Production training remains blocked pending a separately approved supplemental corpus review and a new exact training approval.

### DEC-029 - Exact corpus-target supplemental request ready

- Source `kaggle/pokemon-tcg-ai-battle-episodes-2026-08-04/1` is READY; dataset id `11506836`, inventory SHA-256 `5620e055a25407c47e7744eaa0ffb9ab2a04fe2287b0f6180f54726cf7a00f77`, manifest SHA-256 `bb190f62f0585dc2a1db2b02752a4d7e6fa6de15a800ed9e769d8daecd8bf9a1`.
- 236 completed new Majkel episodes intersect both inventory and manifest and are absent from corpus v2.
- Exact request: 48 files, 12 per seat/result stratum, 180,695,173 declared bytes.
- Request SHA-256 `d94c12e424ba26a06a4085c7273faeadd512351828b2b2aa84b85bf014a2f92e`; contract review self-hash `28b0d81821aed9ac509fff9296fb7aa29a1d3837f107f82cfd80a5d418a0456b`.
- No replay body was read. Execution, corpus-v3 finalization, labels, training, accelerators, model promotion and submission remain separately unauthorized.

### DEC-030 - Stop supplement on module 1.32.4 drift

- Saved version 1 failed before replay reads on an import-path defect.
- Saved version 2 verified source identity, read only `90037133.json` at 4882237 bytes, observed module `1.32.4`, and failed closed before deck/action qualification.
- Corpus v2 remains 337 episodes and 23,460 targets; corpus v3 does not exist.
- Exact compatibility request `configs/e01_majkel_module_1324_compatibility_probe_request_v1.json` SHA-256 `dc38df7b76e01682d3e735499aab352e963c9d454423c71756ededee98b69331` is READY_UNAUTHORIZED and permits no corpus promotion or training.

## Immediate Next Actions

1. Review `reports/incidents/e01-production-bc-preparation-local-replay-read-v1.json` and preserve the fail-closed boundary.
2. Obtain exact approval before any further replay-body read or transfer.
3. After approval, derive one private production-BC input publication request from corpus-v3 manifest metadata only; keep labels, optimizer steps and training separately approval-gated.

## August 4 source-wait refresh

At `2026-08-04T17:07:38Z`, the exact read-only Kaggle CLI query for
`pokemon-tcg-ai-battle-episodes-2026-08-04` returned `No datasets found`.
Majkel submission `55186239` remained active at a dynamic public-score snapshot
of `1261.0`; completed episode `89975204` was created at
`2026-08-04T16:56:37Z`, after the prior source-wait snapshot. Live activity
continues, but the version-pinned filenames and exact declared byte counts
required to freeze a replay request do not exist yet.

The source-wait plan is now
`configs/e01_corpus_v2_target_shortfall_source_wait_v2.json`. It remains
metadata-only and `request_ready: false`, with zero replay-body reads and every
training, optimizer, accelerator, promotion, submission, commit and push
authorization false.
<!-- E01_SOURCE_WAIT_V2:END -->

### DEC-031 - Complete module-1.32.4-aware supplement and freeze corpus v3

- Approved request: `configs/e01_corpus_v2_target_shortfall_supplement_request_v2.json` SHA-256 `eddb6673d2d90d12038b448ed3d8890c3393124ce4a212cad4fd51cb738c77b3`; runner SHA-256 `2acdfe06fa0dd6a79c29e6add267d9c3ca75a5577cdf4ace51d157369c08b30f`.
- The exact `90037133.json` probe record was promoted with `69` policy-loss targets and its replay body was not reread.
- The private Kaggle CPU run read exactly the first `24` remaining bodies in frozen order, totaling `98058852` bytes, and left `23` approved bodies unread.
- Review-order `23` ended at `24987` targets; review-order `24`, `90004101.json`, raised the corpus to `25056`, so execution stopped immediately.
- Corpus v3 is frozen at `362` unique episodes and `25056` policy-loss targets. Manifest SHA-256 `c032694d3601d2570c8e2199c886e452af11f2d72b47379ad08761f16a6b3267`, self-hash `bb6319e23f3d5b12bd9ed7383b0f3e007dd7059cbf39afcd5325af12392c35a9`.
- Run review SHA-256 `fe067987e72bf1a12cbe0aecc2b38dde714c2484b5e3f7e38124054e287a46a0`; corpus review SHA-256 `5d9c42412659dd6a0d783cd1220bc97e6b4c5aae3e7288fe4e94dbb7f60b500e`; output manifest SHA-256 `a8f3190e7b0f87019abe18e8acf63ba7da6ea76a30b33aa9bf98352b315d5b8d`.
- Zero replay-body outputs, zero agent-log outputs, zero training labels, zero optimizer steps, zero training, zero model mutation/promotion, zero submission and zero Git commit/push occurred.
- Production recurrent BC remains separately approval-gated.

### DEC-032 - Production BC preparation failed closed

- A local hash-verification helper read 66 retained flg/Dries replay files totaling 383,801,622 bytes outside exact replay-read approval.
- The helper did not parse replay JSON; every byte count and SHA-256 matched corpus v3.
- No replay copy/export, Kaggle mutation, labels, optimizer, training, model mutation, submission, commit or push occurred.
- Evidence: `reports/incidents/e01-production-bc-preparation-local-replay-read-v1.json` SHA-256 `9df0a700478da719442f89687f7d372d6f3d1cd26561aaf92c03322747464536`, self-hash `de139b89f032ef9d51fd57250d517c43cd7574dd5a318f9f5250755660ac8b26`.
- Production BC request preparation is stopped pending a new exact approval.

### DEC-033 - Production BC requests prepared without replay access

- Retained replay publication request: `configs/e01_production_bc_input_publication_request_v1.json`, SHA-256 `aeacd6377db8bf2b0bce0bfd5e3f20f71094735fd2cb51cfdacd9b7348a60c7b`; exactly 58 train/validation bodies / 341559745 bytes; zero test records.
- Production recurrent BC request: `configs/e01_production_recurrent_bc_request_v1.json`, SHA-256 `709837e07d7d8e6089662e3b03e1e131b3be72111894eab2cc70d54bb8d5520b`; 284 train episodes / 19646 targets, 32 validation episodes / 2318 targets, and 46 sealed test episodes / 3092 targets.
- Deterministic sampling is four Majkel seat/result chunks plus one retained flg/Dries chunk per step, at most 211 steps per epoch, four epochs and 844 optimizer steps.
- The existing source bundle requires one exact version-2 overlay containing the new implementation, runner, corpus-v3 metadata and sealed checkpoint. It remains unpublished.
- Preparation read zero replay bodies and agent logs and performed zero copy, staging, upload, label, optimizer, training, evaluation, model, submission or Git operations.

## DEC-034 retained dataset publication failed closed (2026-08-05T11:15:36.894998Z)

Private Kaggle dataset `ashok205/kptcg-e01-production-bc-retained-inputs` was created as dataset ID `11514316`, version `1`, private and Ready. It contains the exact 58 replay basenames and 341,559,745 bytes, but Kaggle flattened all requested `episodes/<episode_id>.json` paths to root-level filenames. Dataset version 1 is rejected for production BC. No test replay, agent log, label, optimizer step, training, evaluation, model promotion, submission, commit or push occurred. Remediation requires a new exact approval.

## DEC-035 Root-Basename Remediation Prepared

Private dataset `ashok205/kptcg-e01-production-bc-retained-inputs`, ID `11514316`, version `1`, remains unchanged, private and Ready with 58 root-level replay basenames and 341,559,745 bytes. The contract-only remediation request is `24abd3c96a95b57cbef294c04332bafad16e0ba24557f86b6cd912eae476b080`. It adopts those verified root basenames without deleting, versioning, uploading to, downloading from, or rereading the dataset.

Production recurrent BC v2 is frozen at `297679d5a1a2ca43b3f8ef1dc158cdc82fc68e8c5fe7b6791d790bded586ea0d` under versioned implementation `4e30361f7319673b8f597ca65c65ea191e6c82a46a839c355bc6a59b8644dbde` and runner `92e2eeab5986d21e648b8db64ee19a85ffadb60904351863af528d48c4c94413`. It keeps the 284/32 train-validation split, 46 sealed test episodes, deterministic 80/20 recurrent sampling, four epochs and an 844-step cap. Remediation consumption, source-bundle version 2, notebook execution and training all remain separately unauthorized.

Evidence: `reports/artifacts/e01-production-bc-retained-dataset-remediation-contract-review-v1.json`, `reports/artifacts/e01-production-recurrent-bc-contract-review-v2.json`, and `docs/decisions/DEC-035_E01_PRODUCTION_BC_ROOT_BASENAME_REMEDIATION_PREPARED.md`.

## DEC-036 Unauthorized Kaggle Benchmark-Task Incident

The exact DEC-035 remediation approval was received but not consumed. During metadata-only preflight, an incorrect connector call created `ashok205/new-benchmark-task-b1c52` and returned `/code/ashok205/new-benchmark-task-b1c52/edit/run/340537492`. Read-only listing confirmed the object; a status query returned 404, so privacy and execution state remain unresolved. The object was not deleted or modified. No replay body, agent log, dataset update, source-bundle publication, label, optimizer step, training, evaluation, model mutation, submission, commit, or push followed. Exact deletion-or-retention authorization is required before resuming.

## DEC-037 Remediation Consumed And Source-Bundle V2 Approval Prepared

The unauthorized Kaggle benchmark task `ashok205/new-benchmark-task-b1c52` is retained unchanged as incident evidence. No deletion, modification, or execution was attempted.

The exact metadata-only root-basename remediation request `24abd3c96a95b57cbef294c04332bafad16e0ba24557f86b6cd912eae476b080` is consumed. Live metadata-only reconstruction still reports private retained dataset ID `11514316`, version `1`, Ready, 58 root-level files, 341,559,745 bytes, and inventory SHA-256 `d03105906d9e066045410bc4da07ec7bd045f5b1285d35ddc516c1e7960b5c43`.

Exact source-bundle version-2 approval text is prepared at SHA-256 `f99906186f531a5635ec7525eccbfe8eec3314bc932a7b2e9f8c05e18ccd06b5`. The planned version preserves 66 base files and adds the frozen 10-file overlay, for 76 files, 7,646,035 bytes, and expected inventory SHA-256 `78fa9caa32782729a28cb9254449f22e46a6edcb5f83b7b2f763756bd970fa90`. Publication, notebook execution, replay access, labels, optimizer steps, and training remain unauthorized.

Evidence: `reports/artifacts/e01-production-bc-remediation-consumption-review-v2.json` and `docs/decisions/DEC-037_E01_REMEDIATION_CONSUMED_AND_SOURCE_BUNDLE_V2_APPROVAL_PREPARED.md`.

## DEC-038 Source-Bundle Version 2 Rejected

Private dataset `ashok205/kptcg-e01-majkel-corpus-review-inputs`, ID `11501808`, version `2`, is Ready and private but failed the exact publication contract. Kaggle expanded the sealed checkpoint ZIP into four internal members. The expected 76-file / 7,646,035-byte inventory `78fa9caa32782729a28cb9254449f22e46a6edcb5f83b7b2f763756bd970fa90` became 79 files / 7,645,589 bytes with inventory `2bc151d35af0ef3bd9177f44275ef04be0de017a07ef5cf86b283c94834f83ab`. Version 1 remains preserved; no mutation followed the mismatch.

Production training and notebook-wrapper preparation remain blocked. Evidence: `reports/artifacts/e01-source-bundle-v2-publication-execution-review-v1.json`, `reports/incidents/e01-source-bundle-v2-checkpoint-archive-expansion-v1.json`, and `docs/decisions/DEC-038_E01_SOURCE_BUNDLE_V2_CHECKPOINT_ARCHIVE_EXPANSION.md`.

## DEC-039 Extracted-Checkpoint Verification Prepared

Source-bundle dataset ID `11501808`, version `2`, remains unchanged, private and Ready at 79 files and 7,645,589 bytes. A four-file-only verification request is frozen at `443098120fa03dcbaa1d430e3f74505926d2e45fa5ea382856b80422816bba78`. It authorizes nothing currently.

Local positive and negative tests prove that the four expected checkpoint members reconstruct the exact original 5,429,190-byte package at `4dfba2adb9f97607cfa5dabadba075236bb7aae51eafab264584e947feae3827` only under the frozen deterministic archive metadata. A successful remote verification would avoid dataset version 3 and allow notebook preflight to reconstruct the ZIP before any replay-body read.

Evidence: `reports/artifacts/e01-source-bundle-v2-checkpoint-directory-verification-contract-review-v1.json` and `docs/decisions/DEC-039_E01_SOURCE_BUNDLE_V2_EXTRACTED_CHECKPOINT_VERIFICATION_PREPARED.md`.

## DEC-040 Checkpoint Verification Fail-Closed Incident

The corrected four-file verification approval was not consumed. Before any approved checkpoint member was downloaded, incorrect Kaggle connector invocations created `ashok205/new-benchmark-task-daa06` and `ashok205/new-benchmark-task-4abba`. Both remain unchanged; privacy and execution state are unresolved. Checkpoint downloads, replay access, labels, optimizer steps, training, notebook-wrapper preparation, dataset/model/submission mutations, commit, and push remained zero.

Evidence: `reports/artifacts/e01-source-bundle-v2-checkpoint-directory-verification-execution-review-v1.json` and `reports/incidents/e01-source-bundle-v2-verification-unauthorized-benchmark-tasks-v1.json`.

## DEC-041 Source Bundle Accepted And Production BC Notebook Ready

The four extracted checkpoint members from private source-bundle dataset ID `11501808`, version `2`, were downloaded and matched their exact hashes. Deterministic reconstruction produced the approved `5,429,190`-byte checkpoint at SHA-256 `4dfba2adb9f97607cfa5dabadba075236bb7aae51eafab264584e947feae3827` and was byte-identical to the local approved checkpoint.

The exact private CPU notebook request is `6d50e6b70c2a144948342bf8366ea481ee1330744bd96f6b82924500cc735d30`. Its wrapper is `44dfdc02b0c0f180c2929fa3fca4bb32426a99721d9892f129b7ffdc4bca0ebe`, builder `8c8ba2194138d14d139157dfce3c0ecf40f7079c74a92303ff51f0c615fcc026`, and approval text `4b00bce447f7372d3503086326bfc8f5a6c2e732745e708f642613d8693f06cf`. The planned run is 316 train/validation replay bodies, four epochs, and at most 844 optimizer steps. No notebook was created or run and training remains unauthorized.

## DEC-042/043 Production BC Notebook Mount-Count Remediation

The exact v1 notebook was created private and CPU-only, but failed in roughly ten seconds at the August 3 mount preflight: Kaggle mounted `4,721` files and `21,451,850,075` bytes while the wrapper expected a historical `4,724` count. No replay body, checkpoint reconstruction, optimizer step or training occurred.

The corrected v2 request changes only that mounted-file count. Request SHA-256: `93ad27ae290bdf56f0e6259a252625d7bd15150054d85139f29c9cae7fb7f4eb`; wrapper SHA-256: `59db2271582b45f886347755ef7e401af1603ac761977ba2d6600e70233bcf52`; approval text SHA-256: `2e6f98386958bf207a3eeb10bacaf88a03e712ba67d20b3f3105bf8f32397c21`. A separate exact approval is required before the new v2 notebook can run.

## DEC-044/045 Production BC Notebook Approval-Kind Remediation

Private CPU notebook `ashok205/kptcg-e01-production-recurrent-bc-v2`, version 1, passed all dataset and checkpoint preflights and read/hash-verified exactly `316` approved train/validation replay bodies totaling `1,327,994,902` bytes. It then failed before semantic parsing because the wrapper required approval kind `E01_PRODUCTION_RECURRENT_BC_APPROVAL_V2` while the unchanged production implementation requires `E01_PRODUCTION_RECURRENT_BC_APPROVAL_V1`. Optimizer construction, optimizer steps, labels, training, epoch checkpoints, test replay reads and agent-log reads remained zero.

The v3 remediation changes only the wrapper-side approval kind and adds a focused integration test proving one V1 receipt passes both validators. Request SHA-256: `30b7b049f6fe8e069f3253fac7fde8db44dc7cd862e923d47db84bfd5894c9bd`; wrapper SHA-256: `7f63cf6331ef0ee8122522cf2849e765e247f6f9a1a4c77bf4677101c1cf0b8d`; builder SHA-256: `425ee2fe2ed3674424a0e432b95ea45327cf89676f553dca41cfd73e663d8421`; approval text SHA-256: `4cf80c5be4f1dfa40fbcd0e158dffe4113845862ac2d15421e51e28e8b3f0fbb`. A separate exact approval is required before notebook v3 can run.

## DEC-046/047 Notebook V3 Benchmark Incident And Approval Renewal

The exact v3 approval failed closed before notebook creation after an incorrect connector invocation created `ashok205/new-benchmark-task-8065e`. The object was left unchanged. The approved notebook, replay reads, optimizer construction, optimizer steps, and training all remained zero.

The unchanged v3 request remains `30b7b049f6fe8e069f3253fac7fde8db44dc7cd862e923d47db84bfd5894c9bd`. A renewed exact approval is prepared at SHA-256 `48c575e4aae749d1f830b554d046f59d4830ce7bc7604d1733b9744ffa90f151`; it adds only the new object to the retain-unchanged boundary and authorizes nothing until accepted.
