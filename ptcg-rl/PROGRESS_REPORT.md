# Progress Report

Current gate: **DEC-038 rejected private source-bundle dataset ID 11501808/version 2 after checkpoint archive expansion; production BC remains blocked**
Current verdict: **G3a SUCCEEDED / PASS; G3b BLOCKED / NOT_REVIEWED**  
E04 engineering status: **SUCCEEDED / PASS**
Gold-path status: **CORPUS V3 362 / 25,056; RETAINED DATASET VALID; SOURCE BUNDLE V2 REJECTED; PRODUCTION BC V2 BLOCKED; TEST SEALED; TRAINING BLOCKED**
Latest completed milestone: **source-bundle version 2 created, independently metadata-verified, and failed closed because Kaggle expanded the sealed checkpoint archive**
Cost: **USD 0**

## Majkel Two-File Contract Review

The user separately approved the exact request SHA-256
`e0b43f2a507728f5b2048a9ac7d8e30b6f444448e74885503267058477029886`.
Exactly `89651832.json` and `89802438.json` were retrieved from the bound August
3 dataset version into `private/g3/e01/majkel-live-gold-teacher-probe-v1`.
Their byte counts are 376,976 and 455,901, exactly 832,877 total, with SHA-256
`6e03791819464b8376423a7e2d0cda171cf4abfc1541ac84cd2b90069aeec288`
and `ec5ab4bce6e29c8062f504ae24aac754d83c32689103ec3e997d4ab44cfe97e2`.
No additional replay, agent log, export or overwrite occurred.

Body-level review passed schema, environment, terminal, reward, opposite-seat,
current-card deck construction and lag-aligned action checks. Both episodes use
exact Mega Lucario deck multiset SHA-256
`dc8571d0bc2e546a1f85b938696cfc40a1451c68a4ccc1f695e7c3e1c74f1278`.
The pair reveals a genuine module transition: episode `89651832` uses `1.32.2`
and episode `89802438` uses `1.32.3`; both remain action-contract compatible.
Together they contain 40 all-player active requests, 35 Majkel teacher requests,
3 forced singleton requests and 32 potential policy-loss targets.

The one-time request is consumed at SHA-256
`5a35b00b201dd4ab8cf9f054ec62a152ea06ce121726e89c3f78139ff1efd63f`.
The review self-hash is
`a9dfd2d92f10b95aad3032566e3f5bd7973d007d81ef19722ebf3ec4452efead`.
The finalizer reproduced the result in idempotent verify-only mode. Corpus
promotion, label generation, optimizer steps, training and submission remain
unauthorized, so the frozen approved corpus remains unchanged.

Evidence: `reports/artifacts/e01-majkel-next-step-readiness-v1.json`,
`configs/e01_majkel_live_gold_teacher_probe_request_v1.json`, and
`reports/artifacts/e01-majkel-live-gold-teacher-probe-review-v1.json`.

## DEC-027 Pretraining Freeze

The initial learned-policy configuration is now frozen to remove planning delay. Majkel1337 team `16374395` and active submission `55186239` are the primary teacher source. The reviewed Mega Lucario deck hash `dc8571d0bc2e546a1f85b938696cfc40a1451c68a4ccc1f695e7c3e1c74f1278` is the initial BC training deck. The sealed 970,022-parameter G2 architecture remains unchanged for initial BC and the first bounded PPO stage.

The existing 66-episode, 7,140-target multi-teacher corpus remains the diversity set. The exact expansion request reuses the two reviewed Majkel files and names all remaining 269 files in the August 3 version-1 intersection, with a hard new-transfer cap of `1,030,207,171` bytes. Corpus v2 is not final until body-level deck, module, action, terminal, duplicate and target-count review completes.

The execution sequence is frozen: run the separately approved 64-step BC engineering canary and the separately approved Majkel data review in parallel; then freeze corpus v2, prepare production BC, evaluate held-out and on-policy competence, and only then permit bounded KL/auxiliary-BC recurrent PPO. The final submission deck remains pending D1 tournament evidence.

Evidence: `docs/decisions/DEC-027_PRETRAINING_FREEZE_AND_MAJKEL_PRIMARY_SOURCE.md`, `reports/artifacts/e01-pretraining-freeze-review-v1.json`, `configs/e01_majkel_corpus_expansion_request_v1.json`, `reports/artifacts/e01-majkel-corpus-expansion-contract-review-v1.json`, and `configs/e01_pretraining_launch_plan_v1.json`.

## DEC-026 Compute Placement and Kaggle CPU Infrastructure

Local work is now limited to source changes, metadata, deterministic planning,
tests, packaging and very light bounded smokes. Heavier workflows default to a
private Kaggle CPU notebook with stable versioned inputs. GPU, TPU and every
optimizer-backed or otherwise meaningful training run require separate exact
approval before launch.

A bounded private CPU notebook, `ashok205/kptcg-e01-cpu-infra-v1` (kernel ID
`129685552`), was created with internet, GPU and TPU off and a 900-second cap.
Versions 1 and 2 remain retained failed-closed attempts with no input access.
The user corrected the competition attachment and mounted path, then ran saved
version 4 / scriptVersionId `340139179`. The run completed `PASS`; Kaggle
metadata explicitly lists `pokemon-tcg-ai-battle`, with verified root
`/kaggle/input/competitions` and competition path
`/kaggle/input/competitions/pokemon-tcg-ai-battle`.

The four-core runtime used Python `3.12.13` and PyTorch `2.10.0+cpu`, with zero
CUDA devices and no TPU environment. It enumerated 67 metadata entries—60 files
and 7 directories—but read no file or replay bodies. No optimizer, optimizer
step, training loop, model mutation, accelerator or submission occurred. The
8,918-byte receipt SHA-256 is
`1111472bd2e6782c684228214b524446c220958b86dab361c12c1716389e2454`; the
296-byte output-manifest SHA-256 is
`9931a23da9049959ea4ad3557485c4289fce38feb5d911b3a0dfddfd54538efc`, and
it binds the receipt exactly.

Evidence: `docs/decisions/DEC-026_COMPUTE_PLACEMENT_AND_KAGGLE_CPU_DEFAULT.md`,
`reports/jobs/e01-kaggle-cpu-infra-qualification-v1.json`, and
`reports/artifacts/e01-kaggle-cpu-infra-qualification-review-v1.json`.

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
decisions, leaving shortfalls of 134 episodes and 17,860 policy-loss targets. The consumed
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

The historical plan remains immutable evidence. DEC-011 supersedes its active 1M/5M sequencing, DEC-012 supersedes E04 sizing, DEC-013–017 preserve provenance and Luca evidence, DEC-018 is superseded unexecuted, DEC-019–021 complete the exact flg screening path, DEC-022 qualifies exact Dries submission `55002825`, DEC-023 completes balanced Grimmsnarl calibration and DEC-024 freezes a zero-transfer current-rank-1 source wait. Exactly 82 replay bodies totaling 453,143,981 bytes were transferred under nine consumed one-time approvals; no agent log, raw export, notebook, model, training run or external compute job was created or launched. E04 is `SUCCEEDED / PASS`, while G3b remains `BLOCKED / NOT_REVIEWED`: the 5,000-decision screening floor and two-teacher requirement pass, but combined evidence is 66 episodes and 7,140 policy-loss targets from 7,542 active requests versus confirmation floors of 200 and 25,000. Current rank-1 haggle submission `55104355` has 76 public episodes but zero files in the latest complete pinned daily dataset, so no replay request is ready. Every replay transfer, agent log, BC, PPO, cloud execution, E04 rerun, deck freeze and submission remains separately approval-gated.

## DEC-025 live refresh and corpus freeze

Authenticated metadata proves current rank-1 Majkel submission `55186239` intersects the complete August 3 version-1 dataset in 271 available JSON files totaling 1,031,040,048 bytes. The smallest opposite-seat, both-winning pair is `89651832.json` plus `89802438.json`, exactly 832,877 bytes; it remains unauthorized and no body was retrieved. The already approved corpus is frozen at 82 files, 453,143,981 bytes, 66 episodes, 7,140 valid policy-loss targets, 402 forced recurrence-only calls, and leakage-safe 50/8/8 episode splits. A separate eight-episode, 64-step local-CPU BC engineering canary request is preflight-qualified but unauthorized. No optimizer step, external compute, production training, model promotion or submission occurred.

## 2026-08-04 — Corpus v2 and BC engineering canary

- Exact Majkel expansion: 269/269 qualified, 0 rejected, 1,030,207,171 newly read bytes, no replay-body exports.
- Corpus v2: 337 episodes, 23,460 policy-loss targets, 1,598 forced recurrence calls; target shortfall 1,540.
- BC canary: 64 cumulative AdamW steps, finite losses/gradients, deterministic step-32 restore, non-promotable.
- Production training, further replay transfer, accelerators, model promotion and submission remain unauthorized.
- DEC-028: `aaaed58c9fe42ae1456550d3af198ff485b08eb4479ed0d912bbd4917d9bf53d`.
- Independent review: `b27c53b8047bd481c608bfe35bcd24b9e5f3895cc422a0d207e93f7e18a771d3` / self `6025b5d9602e4f73d0398f46018e303c5ad23b38e51358d80e641694acd2f57a`.

## 2026-08-04 DEC-028 closeout

- The exact 269-file private Kaggle CPU Majkel review passed: 269 qualified, zero rejected, 1,030,207,171 new bytes read and zero replay-body exports.
- Corpus v2 now contains 337 episodes and 23,460 policy-loss targets. The episode floor passes; the target floor is short by 1,540.
- The 64-step local-CPU BC engineering canary passed within the cumulative cap after a fail-closed 10-step scheduler bug and 54-step recovery. Its checkpoint is non-promotable.
- Production training remains unauthorized and blocked on the supplemental target shortfall plus a separate exact training approval.

<!-- E01_SOURCE_WAIT_V2:START -->
## 2026-08-04 — Supplemental source wait refresh

The exact Kaggle dataset search for the August 4 replay source returned
`No datasets found` at `2026-08-04T17:07:38Z`. Majkel submission `55186239` remains active;
episode `89975204` completed after the prior snapshot. Because there is still
no immutable dataset version, manifest filename or declared byte inventory,
the maximum-48-file supplemental request remains unready.

No replay body or agent log was read. No label, optimizer step, training,
accelerator, model promotion, submission, commit or push was authorized.
<!-- E01_SOURCE_WAIT_V2:END -->

<!-- E01_DEC029:START -->
## 2026-08-05 — Exact corpus-target supplemental request

- Version-pinned source: `kaggle/pokemon-tcg-ai-battle-episodes-2026-08-04/1`, dataset id `11506836`, READY, inventory SHA-256 `5620e055a25407c47e7744eaa0ffb9ab2a04fe2287b0f6180f54726cf7a00f77`, manifest SHA-256 `bb190f62f0585dc2a1db2b02752a4d7e6fa6de15a800ed9e769d8daecd8bf9a1`.
- 236 completed new Majkel episodes are eligible after corpus-v2 exclusion.
- Exact selection: 48 files, 12 per seat/result stratum, 180,695,173 declared bytes.
- Request: `configs/e01_corpus_v2_target_shortfall_supplement_request_v1.json`, SHA-256 `d94c12e424ba26a06a4085c7273faeadd512351828b2b2aa84b85bf014a2f92e`.
- Contract review: `reports/artifacts/e01-corpus-v2-target-shortfall-supplement-contract-review-v1.json`, SHA-256 `efaceaf27f97388f95d4fff4139e2ea3fd6cde9d182e98a20f10b21f902d4de7`, self-hash `28b0d81821aed9ac509fff9296fb7aa29a1d3837f107f82cfd80a5d418a0456b`.
- Replay bodies read: 0. Corpus promotion, labels, optimizer steps, training, accelerators, model promotion and submission remain unauthorized.
<!-- E01_DEC029:END -->

## 2026-08-05 — Module 1.32.4 supplement stop

- Saved version 1 failed before replay-body access because of a temporary import path.
- Saved version 2 read exactly review-order-1 `90037133.json` (4882237 bytes) and stopped on module `1.32.4`, outside the approved `1.32.2`/`1.32.3` set.
- Metadata outputs: 0. Corpus v3: not finalized. Corpus v2 remains 337 episodes / 23,460 targets.
- Compatibility probe request: `configs/e01_majkel_module_1324_compatibility_probe_request_v1.json`, SHA-256 `dc38df7b76e01682d3e735499aab352e963c9d454423c71756ededee98b69331`, READY_UNAUTHORIZED.
- No further replay reads, labels, optimizer steps, training, accelerators, promotion, submission, commit or push are authorized.

### DEC-031 - Supplement execution completed

- Request SHA-256: `eddb6673d2d90d12038b448ed3d8890c3393124ce4a212cad4fd51cb738c77b3`; runner SHA-256: `2acdfe06fa0dd6a79c29e6add267d9c3ca75a5577cdf4ace51d157369c08b30f`.
- One prequalified module-`1.32.4` metadata record was promoted with `69` targets and zero body rereads.
- Exactly `24` new replay bodies were read in the frozen request prefix, totaling `98058852` bytes; `23` approved bodies remained unread.
- The corpus was at `24987` targets after review-order `23`; `90004101.json` at review-order `24` raised it to `25056`, triggering the mandatory stop.
- Corpus v3 contains `362` episodes and `25056` policy-loss targets. Manifest SHA-256: `c032694d3601d2570c8e2199c886e452af11f2d72b47379ad08761f16a6b3267`; self-hash: `bb6319e23f3d5b12bd9ed7383b0f3e007dd7059cbf39afcd5325af12392c35a9`.
- Execution review SHA-256: `fe067987e72bf1a12cbe0aecc2b38dde714c2484b5e3f7e38124054e287a46a0`; corpus review SHA-256: `5d9c42412659dd6a0d783cd1220bc97e6b4c5aae3e7288fe4e94dbb7f60b500e`; output manifest SHA-256: `a8f3190e7b0f87019abe18e8acf63ba7da6ea76a30b33aa9bf98352b315d5b8d`.
- No replay body or agent log was exported. No labels, optimizer steps, training, model mutation, promotion, submission, commit or push occurred.
- Production recurrent BC requires a separate exact approval.

## 2026-08-05 — DEC-032 production BC preparation incident

- Intended operation: manifest-only production BC input planning.
- Actual local raw-byte verification: 66 retained flg/Dries replay files / 383,801,622 bytes.
- Test split included in the accidental hash read: 8 files / 42,241,877 bytes.
- Replay JSON was not parsed; all byte counts and hashes matched corpus v3.
- Persistent replay outputs, Kaggle dataset changes, labels, optimizer steps, training, model changes, submission, commit and push: zero.
- Evidence: `reports/incidents/e01-production-bc-preparation-local-replay-read-v1.json` SHA-256 `9df0a700478da719442f89687f7d372d6f3d1cd26561aaf92c03322747464536`, self-hash `de139b89f032ef9d51fd57250d517c43cd7574dd5a318f9f5250755660ac8b26`.
- Production BC request preparation stopped and remains blocked on a new exact approval.

## 2026-08-05 — DEC-033 production BC requests prepared

- Exact retained replay publication: 58 train/validation files, 341559745 bytes, zero test files; request SHA-256 `aeacd6377db8bf2b0bce0bfd5e3f20f71094735fd2cb51cfdacd9b7348a60c7b`.
- Exact production recurrent BC: 284 train episodes / 19646 targets, 32 validation episodes / 2318 targets, 46 test episodes sealed; request SHA-256 `709837e07d7d8e6089662e3b03e1e131b3be72111894eab2cc70d54bb8d5520b`.
- Sampling: one Majkel chunk from each of four seat/result strata plus one retained legacy chunk per step; maximum 211 steps per epoch, four epochs, 844 optimizer steps.
- Publication runner SHA-256 `36b7185e5652a867c8bc4d3aa2aebde01493e6c09e5e236270e1a14eafe82588`; training runner SHA-256 `57e4d828056b3532cb5920dc3dab1f1d755f4087d3f5920e9d8b39021dd83d6d`; implementation SHA-256 `6d7526d430caff7f90542bd98cffd3bc14716f0291706a03f1ddd30efad4f7e5`.
- No replay body or agent log was opened. No dataset, notebook or model was created or updated. Labels, optimizer steps, training, evaluation, promotion, submission, commit and push remain unauthorized.

## DEC-034 retained dataset publication failed closed (2026-08-05T11:15:36.894998Z)

Private Kaggle dataset `ashok205/kptcg-e01-production-bc-retained-inputs` was created as dataset ID `11514316`, version `1`, private and Ready. It contains the exact 58 replay basenames and 341,559,745 bytes, but Kaggle flattened all requested `episodes/<episode_id>.json` paths to root-level filenames. Dataset version 1 is rejected for production BC. No test replay, agent log, label, optimizer step, training, evaluation, model promotion, submission, commit or push occurred. Remediation requires a new exact approval.

## DEC-035 Root-Basename Remediation Preparation

Dataset ID `11514316`, version `1`, was not changed. The exact 58-file, 341,559,745-byte root-level inventory remains bound by SHA-256 `d03105906d9e066045410bc4da07ec7bd045f5b1285d35ddc516c1e7960b5c43`. The new metadata-only remediation request is `24abd3c96a95b57cbef294c04332bafad16e0ba24557f86b6cd912eae476b080` and requires separate exact approval.

The renewed production recurrent BC request is `297679d5a1a2ca43b3f8ef1dc158cdc82fc68e8c5fe7b6791d790bded586ea0d`, implementation `4e30361f7319673b8f597ca65c65ea191e6c82a46a839c355bc6a59b8644dbde`, runner `92e2eeab5986d21e648b8db64ee19a85ffadb60904351863af528d48c4c94413`. No replay body or agent log was read, no dataset was mutated, no label was materialized, and no optimizer, training, evaluation, model, submission, commit or push operation occurred.

## DEC-036 Fail-Closed Remediation Consumption

The remediation approval was not consumed. An incorrect Kaggle connector invocation created `ashok205/new-benchmark-task-b1c52`, outside the approved metadata-only scope. The remote object remains unchanged because deletion or modification was not authorized. Privacy and execution state are unresolved. Source-bundle approval preparation did not proceed. No replay bodies or agent logs were read, and no optimizer step or training occurred.

Evidence: `reports/artifacts/e01-production-bc-remediation-consumption-review-v1.json` and `docs/decisions/DEC-036_E01_REMEDIATION_CONSUMPTION_UNAUTHORIZED_KAGGLE_BENCHMARK_INCIDENT.md`.

## DEC-037 Remediation Consumption

The user directed retention of `ashok205/new-benchmark-task-b1c52` as incident evidence and continuation of the exact prior metadata-only approval. The object was left unchanged. The retained dataset remediation is now consumed after exact local-hash and live metadata inventory reconstruction.

Source-bundle version-2 approval text is frozen at SHA-256 `f99906186f531a5635ec7525eccbfe8eec3314bc932a7b2e9f8c05e18ccd06b5`. The source dataset remains private Ready version 1; version 2 has not been created. Zero replay bodies, agent logs, labels, optimizer steps, training, evaluation, model changes, submissions, commits, or pushes occurred.

Evidence: `reports/artifacts/e01-production-bc-remediation-consumption-review-v2.json` and `docs/decisions/DEC-037_E01_REMEDIATION_CONSUMED_AND_SOURCE_BUNDLE_V2_APPROVAL_PREPARED.md`.

## DEC-038 Source-Bundle Publication Failure

The approved source-bundle version-2 publication created private Ready dataset version 2, but independent metadata verification found 79 files and 7,645,589 bytes instead of the exact 76 files and 7,646,035 bytes. Kaggle replaced `private/g2/checkpoint-v1/g2-policy-checkpoint-v1.zip` with its four internal files. Version 2 is rejected and no remote mutation followed detection. No replay, label, optimizer, training, evaluation, notebook, model, submission, commit, or push occurred.

Evidence: `reports/artifacts/e01-source-bundle-v2-publication-execution-review-v1.json` and `reports/incidents/e01-source-bundle-v2-checkpoint-archive-expansion-v1.json`.

## DEC-039 Extracted-Checkpoint Verification Preparation

The least-invasive remediation was prepared without remote download or mutation. The exact request `443098120fa03dcbaa1d430e3f74505926d2e45fa5ea382856b80422816bba78` permits a later approval to download only four checkpoint members totaling 5,428,744 bytes, verify their SHA-256 identities, and reconstruct the original sealed package at `4dfba2adb9f97607cfa5dabadba075236bb7aae51eafab264584e947feae3827`. Three focused tests passed, including extra-file and member-hash negative controls. Source-bundle version 2 remains unaccepted, no notebook wrapper was prepared, and training remains blocked.

Evidence: `configs/e01_source_bundle_v2_checkpoint_directory_verification_request_v1.json`, `reports/artifacts/e01-source-bundle-v2-checkpoint-directory-verification-contract-review-v1.json`, and `docs/decisions/DEC-039_E01_SOURCE_BUNDLE_V2_EXTRACTED_CHECKPOINT_VERIFICATION_PREPARED.md`.

## DEC-040 Checkpoint Verification Failed Closed

The exact four-file source-bundle version-2 verification approval remained unconsumed. Two incorrect Kaggle connector invocations created `ashok205/new-benchmark-task-daa06` and `ashok205/new-benchmark-task-4abba` before any approved checkpoint member was downloaded. Both objects were retained unchanged because deletion or modification was outside scope; privacy and execution state remain unresolved.

Remote checkpoint files downloaded: `0`. Replay bodies and agent logs: `0`. Labels, optimizer steps, training, evaluation, notebook-wrapper preparation, dataset/model/submission changes, commit, and push: `0`. Source-bundle version 2 remains unaccepted.

Evidence: `reports/artifacts/e01-source-bundle-v2-checkpoint-directory-verification-execution-review-v1.json` and `reports/incidents/e01-source-bundle-v2-verification-unauthorized-benchmark-tasks-v1.json`.

## DEC-041 Checkpoint Verification And Notebook Preparation

Source-bundle version 2 is accepted through four-file remote verification and exact deterministic checkpoint reconstruction. Reconstruction SHA-256 is `4dfba2adb9f97607cfa5dabadba075236bb7aae51eafab264584e947feae3827` and the package is byte-identical to the approved local checkpoint.

The one-run private Kaggle CPU production-BC request is `6d50e6b70c2a144948342bf8366ea481ee1330744bd96f6b82924500cc735d30` with approval text SHA-256 `4b00bce447f7372d3503086326bfc8f5a6c2e732745e708f642613d8693f06cf`. Wrapper `44dfdc02b0c0f180c2929fa3fca4bb32426a99721d9892f129b7ffdc4bca0ebe` and builder `8c8ba2194138d14d139157dfce3c0ecf40f7079c74a92303ff51f0c615fcc026` passed 17 focused/regression tests. No replay body, agent log, optimizer step, training, notebook, model, submission, commit or push occurred during preparation.

## DEC-042/043 Production BC Notebook V1 Failure And V2 Preparation

Private notebook `ashok205/kptcg-e01-production-recurrent-bc-v1` version 1 failed closed before replay reads because its August 3 aggregate expected `4,724` files; both the live mount and official Kaggle file summary contain `4,721` files at the exact approved byte total. Output contained only the original hash-matching wrapper and approval receipt. Optimizer steps and training remained zero.

Corrected notebook request v2 is `93ad27ae290bdf56f0e6259a252625d7bd15150054d85139f29c9cae7fb7f4eb` and remains unauthorized. The only contract change is `AUGUST_3_FILES: 4724 -> 4721`; all 316 replay records, hashes, four epochs, 844-step cap, checkpoint, test seal and output-review boundaries are unchanged.

## DEC-044/045 Production BC Notebook V2 Failure And V3 Preparation

Private CPU notebook `ashok205/kptcg-e01-production-recurrent-bc-v2`, version 1, passed all dataset and checkpoint preflights and read/hash-verified exactly `316` approved train/validation replay bodies totaling `1,327,994,902` bytes. It then failed before semantic parsing because the wrapper required approval kind `E01_PRODUCTION_RECURRENT_BC_APPROVAL_V2` while the unchanged production implementation requires `E01_PRODUCTION_RECURRENT_BC_APPROVAL_V1`. Optimizer construction, optimizer steps, labels, training, epoch checkpoints, test replay reads and agent-log reads remained zero.

The v3 remediation changes only the wrapper-side approval kind and adds a focused integration test proving one V1 receipt passes both validators. Request SHA-256: `30b7b049f6fe8e069f3253fac7fde8db44dc7cd862e923d47db84bfd5894c9bd`; wrapper SHA-256: `7f63cf6331ef0ee8122522cf2849e765e247f6f9a1a4c77bf4677101c1cf0b8d`; builder SHA-256: `425ee2fe2ed3674424a0e432b95ea45327cf89676f553dca41cfd73e663d8421`; approval text SHA-256: `4cf80c5be4f1dfa40fbcd0e158dffe4113845862ac2d15421e51e28e8b3f0fbb`. A separate exact approval is required before notebook v3 can run.

## DEC-046/047 Notebook V3 Benchmark Incident And Approval Renewal

The exact v3 approval failed closed before notebook creation after an incorrect connector invocation created `ashok205/new-benchmark-task-8065e`. The object was left unchanged. The approved notebook, replay reads, optimizer construction, optimizer steps, and training all remained zero.

The unchanged v3 request remains `30b7b049f6fe8e069f3253fac7fde8db44dc7cd862e923d47db84bfd5894c9bd`. A renewed exact approval is prepared at SHA-256 `48c575e4aae749d1f830b554d046f59d4830ce7bc7604d1733b9744ffa90f151`; it adds only the new object to the retain-unchanged boundary and authorizes nothing until accepted.
