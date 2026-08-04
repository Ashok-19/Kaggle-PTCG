# Progress Report

Current gate: **versioned-source wait for current rank-1 haggle submission `55104355`; no replay request is ready**
Current verdict: **G3a SUCCEEDED / PASS; G3b BLOCKED / NOT_REVIEWED**  
E04 engineering status: **SUCCEEDED / PASS**
Gold-path status: **DEC-021 FLG SCREENING PASS; DEC-022 DRIES SECOND-TEACHER PASS; DEC-023 GRIMMSNARL CALIBRATION PASS; DEC-024 CURRENT-RANK-1 SOURCE WAIT; E04 ZERO-UPDATE QUALIFICATION PASS**
Latest completed milestone: **DEC-023 qualified all 12 Dries Grimmsnarl calibration replays; DEC-024 independently proved that no current-rank-1 replay request is source-ready**
Cost: **USD 0**

## DEC-011 Gold Path and DEC-012 Qualification Sizing

DEC-011 preserves all accepted engineering evidence but supersedes the old
1M/5M scratch-PPO execution sequence. The active sequence is exact deck/teacher
qualification, full-compound recurrent BC, held-out and on-policy competence
evaluation, then bounded KL/auxiliary-BC recurrent PPO with at most 500,000
choices before another decision. DEC-012 supersedes only the E04 confirmation
game count, replacing the unsupported 100-game combination with exactly 180
games while preserving the 10,000-decision floor. The unchanged Mega Lucario
rule policy remains a byte-frozen hedge, not the final deck.

DEC-014 resolved the DEC-013 schema incident and the user separately approved
the exact provenance request. `87703034.json` was downloaded once into the
private quarantine at exactly 3,641,302 bytes with SHA-256
`58089ab3824ac703dddb5d1364718684d4770d3ebf853ea198ca00efdc6a43db`.
DEC-015 then separately downloaded `87741212.json`, exactly 559,779 bytes with
SHA-256 `be962b8ca9146320f7d8976460c20244cf5e8bf6b026816816bc4b4ec91a87d2`.
Both one-time authorizations are consumed. The two episodes bind exact Benarg
submission `54933084` in opposite player slots and opposite terminal results,
use the same 60-card multiset hash
`606a775392ffe25e058b19c17801d58a4bf30f7cd8c62782388d3de7e7eb5283`,
and pass action alignment. They expose 157 all-player active requests but only
65 Benarg teacher requests, leaving a 4,935-decision screening shortfall. No
agent log, raw step, action, observation or training-label export occurred.
Exact historical legality and teacher strength remain unproven.

A metadata-only screen of active top-10 submissions selected Luca submission
`54863653`: current rank 2, public score `1180.9`, 357 retained July 23 episodes
and 181/176 seat balance. DEC-016 then transferred exactly `87731214.json` and
`87615736.json`, totaling 1,313,221 bytes. Independent review qualifies Luca as
a strong current teacher, confirms exact deck hash
`cafa7652a6349be806d8ac2b9abfdb6c72ca3821f368e0d912e2d989f3b54cdd`
and validates all 61 aggregate action requests. The pair spans module versions
`1.32.2` and `1.32.1` and contains 37 Luca decisions, leaving a 4,963-decision
screening shortfall. Its one-time authorization is consumed.

DEC-017 transferred exactly 12 balanced Luca calibration files totaling
63,828,057 bytes. All are module `1.32.2`, share the exact Luca deck and pass
aggregate action alignment. They expose 2,258 all-player requests and 1,170
Luca decisions; with the prior probe, 1,207 Luca decisions are observed and the
screening shortfall is 3,793. The consumed request SHA-256 is
`a71621707f597e9f99c9db2dfb549f3dcf626aaf3d4f36ad182cc2d03dcd87f0`.

The July 27 live refresh found DEC-018 stale before execution: Luca had moved
to rank 14 and changed active submission, while current rank-1 `flg` submission
`55004495` had 131 July 26 replays across all four seat/result strata. DEC-018
remains unauthorized and unexecuted. `NNMax` was rank 1,643 of 5,810 with the
visible 754.0 baseline submission at the refresh.

DEC-019 transferred exactly `88302734.json` and `88333037.json`, totaling
3,996,398 bytes. Both are schema 1, CABT `1.0.0`, module `1.32.2`, share exact
teacher deck hash
`89e6155f25310ee695c0761c85d3ae8e44f376456ff0539231820f8e803f2d5e`,
and pass all 165 aggregate request/action checks. Official card metadata labels
the recovered deck context **Dragapult ex**. The pair contains 94 teacher
decisions, leaving a 4,906-decision shortfall. Its authorization is consumed.

DEC-020 transferred exactly 12 balanced files totaling 63,562,985 bytes. All
are schema 1, CABT `1.0.0`, module `1.32.2`, share exact Dragapult deck hash
`89e6155f25310ee695c0761c85d3ae8e44f376456ff0539231820f8e803f2d5e`,
and pass current-card construction and every lagged request/action check. They
expose 2,247 all-player requests and 1,292 flg decisions. With the probe, 1,386
teacher decisions are observed and the screening shortfall is 3,614. The
consumed request SHA-256 is
`9140bc26599d08c6c343db19a658cfa728b5425f9a59700d9bb627b3c16c89e8`.

DEC-021 transferred exactly 38 balanced files totaling 254,237,550 bytes.
All 38 are schema 1, CABT `1.0.0`, module `1.32.2`, share the exact flg
Dragapult deck hash, pass current-card construction and satisfy complete lagged
action alignment. The batch adds 8,609 all-player requests and 4,954 flg
teacher decisions. With the prior probe and calibration, 6,340 teacher decisions
are observed, the 5,000-decision screening floor passes and zero files are
rejected. The consumed request SHA-256 is
`f16d155948db791e355f561901daf2e4f2ef886d68d638a6fdce4c2d31939583`.

A fresh post-screen leaderboard refresh found `flg` at rank 4 with a new active
submission and `Dries @ Tufa Labs` rank 1 at `1205.2`, active submission
`55002825`. DEC-022 transferred exactly `88281294.json` and `88332011.json`,
totaling 1,135,238 bytes. Both are schema 1, CABT `1.0.0`, module `1.32.2`,
share exact deck hash
`cafa7652a6349be806d8ac2b9abfdb6c72ca3821f368e0d912e2d989f3b54cdd`,
pass current-card construction and satisfy all 57 action-aligned requests.
Official card metadata labels the deck **Marnie's Grimmsnarl ex**. The pair adds
27 Dries decisions and qualifies the second independent recent teacher. Combined
recent evidence is 54 episodes and 6,367 decisions, leaving shortfalls of 146
episodes and 18,633 decisions. The consumed request SHA-256 is
`9e558be620bcf9722ba69ae7189ebec79145b351c20e4370eb1bb37d2427d2bc`.

DEC-023 transferred exactly 12 balanced files totaling 60,869,451 bytes. All
12 are schema 1, CABT `1.0.0`, module `1.32.2`, share exact Marnie's Grimmsnarl
ex deck hash `cafa7652a6349be806d8ac2b9abfdb6c72ca3821f368e0d912e2d989f3b54cdd`,
pass current-card construction and satisfy complete lagged action alignment.
The batch adds 2,171 all-player requests and 1,175 Dries decisions. Combined
confirmation evidence is two independent teachers, 66 episodes and 7,542
decisions, leaving shortfalls of 134 episodes and 17,458 decisions. The consumed
request SHA-256 is
`f026a350d9e5c882080f28f60a811d3060f49c7a3c7375dc85e550865d4f9380`.

A post-calibration metadata refresh found `haggle` rank 1 at `1169.5` with active
submission `55104355` and 76 public episodes across all four strata. The latest
complete pinned daily dataset is
`kaggle/pokemon-tcg-ai-battle-episodes-2026-07-29/1`, which predates that
submission and has an exact intersection of zero files and zero bytes. DEC-024
therefore records a source wait: no current-rank-1 request or output directory
exists, and no replay transfer is authorized.

The E04 bridge fails closed on invalid/fallback actions,
stale/duplicate/out-of-order requests, policy lag, recurrent owner crossing,
nonfinite values, probability replay mismatches, terminal errors, worker death
and optimizer-step attempts. It advances recurrence through forced calls while
excluding them from learner nodes, represents terminal or truncation boundaries
for both players even when one player has zero decisions, and supports
deterministic checkpoint/resume state parity. Under three exact approved
scopes, the one-game trace, ten-game smoke and 180-game local CPU qualification
completed with the frozen G2 checkpoint, unchanged Mega Lucario deck and
byte-verified official assets. Across all stages, 191 games produced 12,972
engine decisions: 11,961 meaningful and 1,011 forced. The qualification alone
produced 12,194 engine decisions, 11,250 meaningful decisions and 944 forced
decisions. All 180 qualification games closed terminally for both players;
maximum compound replay error was `2.3479170385698467e-07`; every reliability
counter and optimizer-step count was zero. Its wall time was
`294.104991952001` seconds. The one-game post-report incident was recovered
from its atomic bridge checkpoint without another CABT execution, and no later
stage required recovery or rerun.

Single-trace evidence SHA-256 is
`d169bb3c955197607bb4ae9c13c46ba9aedb79afbc708548d5b680374ba99653`.
Ten-game smoke evidence SHA-256 is
`66d00da9e0b99783fd3f7ec441a89fa298597acbc1818220014a97481ba68236`.
Qualification evidence SHA-256 is
`1d475ad630594fbf78b2b0b4bf542f100689d843cc68695025bec3b2c952d7db`,
with independent review self-hash
`5b9708a49fbb1ae044aa0f700d8f9aa409bb382f913e8c454dd08ca6132df0ff`.
DEC-012 SHA-256 is
`4667d8c08f9fb6782d37729f14ed097323c4b31efafdd87f44da9bdb2ad40307`;
its sizing-review file SHA-256 is
`f89c4279c77e8441824cf08acba2c4f109a778dfe145791cd9856052984709a1`.
The consumed qualification request SHA-256 is
`13aa4465404599827e22a494181ac2f0af4e591b316e4f933500b0ed942a497b`.
All three native approvals are consumed; no E04 rerun, later native stage,
optimizer step, external compute or training is authorized.

The project-native recurrent PPO correctness implementation is committed at
`68407689ccfb18236f14f78dd68360704f408682` and provenance-hardened at
`cae42da47bc9f3491869e8afd0e1254061b9f585`. It includes exact ordered
compound-action log-probability replay with first-class `STOP`, complete-action
forced classification, clipped policy/value losses, GAE with explicit terminal
and live-truncation bootstrap, recurrent owner/version slicing, finite-gradient
gates, and an atomic SHA-bound training checkpoint restored through PyTorch's
restricted `weights_only=True` loader.

The three frozen versioned toy tasks are implemented:

- `masked-bandit-v1` for legal masking and basic PPO learning;
- `recurrent-cue-v1`, whose final decision observation is identical across cues;
- `variable-option-multiselect-v1` for variable option counts, optional `STOP`,
  ordered unique selections and variable minimum/maximum counts.

Three complete local candidate experiments were compared under the hard local
boundary of CPU only, two PyTorch threads, one interop thread, zero workers,
zero CABT games and at most 4,096 choices per model:

- 512 choices at learning rate `0.005` was rejected because the multi-select
  score stopped at `0.75`;
- 1,024 choices at learning rate `0.005` passed and was selected;
- 1,024 choices at learning rate `0.01` passed but was rejected because its
  peak pre-clip gradient norm was `1.5519`, versus `0.8668` for the selected run.

The authoritative matrix ran from a clean isolated checkout of commit
`cae42da47bc9f3491869e8afd0e1254061b9f585` and reran the selected configuration
across seeds `1197953491`, `20344180`, and `1491619630`. In every seed:

- masked bandit, recurrent cue and variable-option/multi-select scores were `1.0`;
- the equal-budget stateless cue control remained `0.5`;
- the recurrent-over-stateless margin was `0.5`;
- maximum old-log-probability replay error and initial-ratio error were `0`;
- every zero-tolerance counter was `0`;
- model, optimizer, scheduler, counters, league, rollout boundary and available
  Python/NumPy/PyTorch RNG states restored, with exact model tensors and fixed evaluation.

The complete runner took `294.369` seconds. Its dashboard-valid 27,889-byte
report SHA-256 is `868fdd277eeafe96d09138f1a0f70bc50899fd58ee03b49a1fe6d8a3c9f4194e`.
An independent recalculation reproduced every candidate disposition, seed
threshold, resource claim, clean-Git claim, source/config hash and authorization boundary.

Validation completed:

- 55 focused implementation tests passed before the clean-source run;
- the isolated clean source suite passed 334 tests with four environment-dependent skips;
- final promotion validation passed 144 focused G3 tests and the 347-test full Python suite;
- Ruff, dashboard rebuild with 111 records and zero quarantine, dashboard doctor,
  seven frontend unit tests, the production build and four browser tests passed;
- the actual sealed G2 decoder passed the generic compound-replay boundary test;
- no training was launched; no GPU, CABT match, Kaggle/Colab launch, Modal use,
  deck change, submission or external service mutation occurred.

Authoritative evidence:

- `reports/artifacts/g3a-ppo-local-correctness-v1.json`
- `reports/artifacts/g3a-ppo-local-correctness-review-v1.json`
- `configs/g3a_local_correctness_v1.json`
- `reports/gates/g3a.json`

This local result remains a toy-only micro-qualification. It does not satisfy the
frozen cloud budget and does not establish policy strength.

## Frozen Private Kaggle CPU Plan

The complete cloud-plan lifecycle is now finished against clean source commit
`6b7975bf518c36ff59338b6793ec52530c73f173`. A fresh Python process cloned the
exact offline Git bundle, loaded the canonical plan and independently reproduced
the plan review as `PASS`. No notebook, dataset or model was published and no
training process was started.

The immutable work allocation is:

- declared seeds: `1197953491`, `20344180`, `1491619630`;
- exactly `100,000` aggregate non-forced choices per seed;
- exactly four `25,000`-choice streams per seed: masked bandit, recurrent cue,
  variable-option ordered multi-select, and recurrent-cue stateless control;
- seed-bound categorical rollout sampling with seed XOR `23063`; evaluation remains greedy and choices are excluded from the training budget;
- `64` choices per update, four PPO epochs, learning rate `0.005`, Adam epsilon
  `1e-5`, clip/value-clip `0.2`, entropy coefficient `0.01`, value coefficient
  `0.5` and maximum gradient norm `0.5`.

The selected runtime is one private Kaggle CPU notebook with internet, GPU and
TPU off; two active PyTorch threads, one interop thread, zero workers and a
four-core hard ceiling. The exact environment is Python `3.12.13`, PyTorch
`2.10.0+cpu`, NumPy `2.0.2`, Pydantic `2.12.3`, the frozen `uv.lock`, and Kaggle
image digest `dafd4ce5668bbf1ad422e4c109e0f18c9623c3a7c7f48b0235f13142755c40b9`.
The notebook cap is four hours and each child stream cap is 2,400 seconds.
Measured two-thread local evidence gives a linear twelve-stream estimate near
4,132 seconds; the frozen operational estimate is 5,400-10,800 seconds.

Atomic checkpoints are written every `4,096` choices or `300` seconds, plus a
final exact-budget checkpoint. One stream in every seed intentionally stops at
`12,288` choices and resumes in a fresh child process. The restored model,
optimizer, scheduler, counters, league, rollout boundary, Python/NumPy/Torch RNG
states and fixed evaluation must match exactly. Corruption, stale source,
wrong versions, unexpected GPU/core/thread state, budget drift, missing
outputs, dashboard-envelope failure or download/hash mismatch fails closed.

Frozen identities:

- config: `configs/kaggle/g3a_cloud_correctness_v1.json`, SHA-256
  `c0ea3bfa83cc2e86e1933555926c9f957da01ac9618e13f03e9f85d1a6b7957b`;
- source bundle: 7,541,761 bytes, SHA-256
  `048a76aa4f0e1d44b4d178dd0ffe91e830215b7942b55aaad820b2910ceab030`;
- source manifest SHA-256
  `f4d79f1bf6e17d88621df240672a60fbfedb1529a75efaa6daafd0133d6f8afb`;
- input manifest SHA-256
  `4a5394d0deb34e4d0064f1539304aafcd13227414ce6122c1e6985dc0e7126ab`;
- single notebook SHA-256
  `3ab68cdfc8b686d5b7b643469b65d66eed6c1500e4c867ba22d82910e4127345`;
- safe plan report SHA-256
  `f9e4f554b610a0b60f7b8ed08f6bbb3ea59d12c50f7fb720f8c90383bc196116`;
- independent review report SHA-256
  `47b1c937d5bae45197d2287f0ed154604f52d761125bf0343bf5f18a72a9343e`.

Pre-publication validation passed 173 G3 tests, all 376 Python tests, repository-wide Ruff,
dashboard rebuild with 115 ingested records and zero quarantine, dashboard
doctor, seven frontend unit tests, the production build and four Playwright
browser tests. Five failed or transient plan-freeze branches are retained with
their evidence, correction and successful rerun in the safe plan report.

The first complete user-run version-2 notebook trained for approximately one hour and then failed the strict final review. Investigation found that `cloud_runner.py` passed `generator=None` during training, which means greedy argmax collection, while the locally qualified trainer used seed-bound categorical sampling. A 1,024-choice diagnostic reproduced the reported seed-119 bandit `0.5` score and seed-149 multi-select `0.75` score. The corrected cloud runner scored `1.0` on all four reported seed/task diagnostics without changing the plan budget, thresholds, tasks, optimizer or learning rate.

## Approved Publication State

The corrective publication is recorded in
`reports/jobs/g3a-cloud-input-publication-v3.json`. The private dataset
`ashok205/kptcg-g3a-correctness-inputs` version `3` is `READY`; versions `1` and `2` are retained only for audit. Kaggle exposes exactly the four corrected files, and an
independent remote download reproduced every local byte count and SHA-256.

The corrected notebook remains local-only at
`private/kaggle/notebooks/kptcg-g3a-cloud-correctness-v1.ipynb`, 4,787 bytes,
SHA-256 `3ab68cdfc8b686d5b7b643469b65d66eed6c1500e4c867ba22d82910e4127345`.
It contains no Kaggle secret lookup, authorization environment-variable check,
authorization CLI flag or external URL request. The assistant did not create,
launch or monitor a Kaggle notebook session.

## Final Private G3a Qualification

The user manually ran `ashok205/kptcg-g3a-cloud-correctness-v1` as Kaggle saved version `2` / scriptVersionId `337365875`. The run used source commit `6b7975bf518c36ff59338b6793ec52530c73f173` and private dataset version `3`. All twelve exact 25,000-choice streams succeeded, producing exactly 100,000 aggregate non-forced choices per seed. Every seed scored `1.0` on masked bandit, recurrent cue and variable-option ordered multi-select; stateless controls remained `0.5` and recurrent margins were `0.5`. All probability-replay errors, initial-ratio errors, fixed-tensor resume differences and zero-tolerance counters were `0`.

The complete saved output tree was downloaded despite Kaggle pagination. Its 220-entry manifest covered 20,617,497 bytes with zero missing, extra, byte-count or SHA-256 mismatches. The tree contains 84 checkpoint payloads, 84 sidecars, 12 final checkpoints and three intentional fresh-process resumes. All 15 retained stderr files are empty. The assistant reran `scripts/g3a_review.py`; its 1,008-byte result is byte-identical to the notebook review with SHA-256 `abc8dcd3db3489a968840d98fc4450d3164c699473a3336e7625c7295ea8565b`.

Authoritative evidence is `reports/evaluations/g3a-cloud-correctness-v1.json` and `reports/artifacts/raw/g3a-cloud-correctness-review-v1.json`. G3a is `SUCCEEDED / PASS`. This proves only the frozen toy algorithm-correctness gate; it does not establish Pokémon policy competence or strength, and it does not authorize G3b training automatically.

## Historical G3b Competence Plan

The exact G3b planning contract is committed at `098997ae96b3e96a8739cc407fcb16e845c60774`. Three execution paths were completed and compared. A direct five-million-choice Kaggle session was rejected because the CABT learner bridge and PPO training throughput are unqualified and the retained T4 x2 inference rate projects one seed at roughly 6.08–24.30 hours under the tested slowdown range. Direct Modal training was rejected because G4 canary, restart and cost evidence are absent. Staged private Kaggle T4 x2 with exact one-million-choice resumable chunks was selected.

The plan binds the engineering deck, initial 970,022-parameter checkpoint, native engine, card table and four exact rule anchors by byte count and SHA-256. It derives three training seeds and a separate canary seed by SHA-256. Before the fixed one-million-choice broad screen, it requires zero-training CABT bridge qualification and a 100,000-choice topology canary split into two complete 50,000-choice layouts; neither canary checkpoint may seed the broad screen. Confirmation reaches exactly five one-million-choice chunks per seed. The preregistered diagnosis configuration may run only after a complete primary failure and differs only by opponent schedule.

Each fixed evaluation cycle contains 6,000 balanced natural-deployment games: 400 games per seed against random and each of four rule anchors, split equally between learner player slots. The rule-anchor aggregate excludes random and uses equal fixed weights because the retained replay sample is selected and cannot support a defensible current meta weighting. Checkpoints are atomic and content-addressed every 100,000 choices or 900 seconds, include CPU and CUDA RNG, and require byte-verified publication before cross-notebook resume.

The canonical plan is `configs/g3b_competence_plan_v1.json`, 12,291 bytes, SHA-256 `99cf090df232ffe37504eee4b86ab70554256b5ad89fe972bb9bb5033115bc26`. The independent review SHA-256 is `23f5c5c02d74c0db8e91652016d20eb755c1eba515a84067fca6c85d7fb4afe0`. Before the source commit, 27 targeted edge-case tests, 201 G3 tests, 404 total Python tests and Ruff passed. No notebook, dataset, model, canary or training run was created or launched.

The historical plan remains immutable evidence. DEC-011 supersedes its active 1M/5M sequencing, DEC-012 supersedes E04 sizing, DEC-013–017 preserve provenance and Luca evidence, DEC-018 is superseded unexecuted, DEC-019–021 complete the exact flg screening path, DEC-022 qualifies exact Dries submission `55002825`, DEC-023 completes balanced Grimmsnarl calibration and DEC-024 freezes a zero-transfer current-rank-1 source wait. Exactly 82 replay bodies totaling 453,143,981 bytes were transferred under nine consumed one-time approvals; no agent log, raw export, notebook, model, training run or external compute job was created or launched. E04 is `SUCCEEDED / PASS`, while G3b remains `BLOCKED / NOT_REVIEWED`: the 5,000-decision screening floor and two-teacher requirement pass, but combined evidence is 66 episodes and 7,542 decisions versus confirmation floors of 200 and 25,000. Current rank-1 haggle submission `55104355` has 76 public episodes but zero files in the latest complete pinned daily dataset, so no replay request is ready. Every replay transfer, agent log, BC, PPO, cloud execution, E04 rerun, deck freeze and submission remains separately approval-gated.
