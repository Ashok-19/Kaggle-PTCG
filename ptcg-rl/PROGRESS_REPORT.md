# Progress Report

Current gate: **G3b CABT actor/learner integration qualification**  
Current verdict: **G3a SUCCEEDED / PASS; G3b BLOCKED / NOT_REVIEWED**  
Latest completed milestone: **G3b competence plan frozen and independently reviewed after three completed execution-path comparisons**  
Cost: **USD 0**

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

## Frozen G3b Competence Plan

The exact G3b planning contract is committed at `098997ae96b3e96a8739cc407fcb16e845c60774`. Three execution paths were completed and compared. A direct five-million-choice Kaggle session was rejected because the CABT learner bridge and PPO training throughput are unqualified and the retained T4 x2 inference rate projects one seed at roughly 6.08–24.30 hours under the tested slowdown range. Direct Modal training was rejected because G4 canary, restart and cost evidence are absent. Staged private Kaggle T4 x2 with exact one-million-choice resumable chunks was selected.

The plan binds the engineering deck, initial 970,022-parameter checkpoint, native engine, card table and four exact rule anchors by byte count and SHA-256. It derives three training seeds and a separate canary seed by SHA-256. Before the fixed one-million-choice broad screen, it requires zero-training CABT bridge qualification and a 100,000-choice topology canary split into two complete 50,000-choice layouts; neither canary checkpoint may seed the broad screen. Confirmation reaches exactly five one-million-choice chunks per seed. The preregistered diagnosis configuration may run only after a complete primary failure and differs only by opponent schedule.

Each fixed evaluation cycle contains 6,000 balanced natural-deployment games: 400 games per seed against random and each of four rule anchors, split equally between learner player slots. The rule-anchor aggregate excludes random and uses equal fixed weights because the retained replay sample is selected and cannot support a defensible current meta weighting. Checkpoints are atomic and content-addressed every 100,000 choices or 900 seconds, include CPU and CUDA RNG, and require byte-verified publication before cross-notebook resume.

The canonical plan is `configs/g3b_competence_plan_v1.json`, 12,291 bytes, SHA-256 `99cf090df232ffe37504eee4b86ab70554256b5ad89fe972bb9bb5033115bc26`. The independent review SHA-256 is `23f5c5c02d74c0db8e91652016d20eb755c1eba515a84067fca6c85d7fb4afe0`. Before the source commit, 27 targeted edge-case tests, 201 G3 tests, 404 total Python tests and Ruff passed. No notebook, dataset, model, canary or training run was created or launched.

G3b remains `BLOCKED / NOT_REVIEWED`. The next task is `T-G3B-INTEGRATION-001`: implement and independently qualify the CABT actor/learner bridge with zero meaningful training. Cloud execution remains separately approval-gated.
