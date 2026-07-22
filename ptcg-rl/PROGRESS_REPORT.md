# Progress Report

Current gate: **G3a recurrent PPO correctness proof**  
Current verdict: **BLOCKED / NOT_REVIEWED**  
Latest completed milestone: **corrected private Kaggle input dataset version 2 published and independently byte-verified; exact notebook no longer requires secret or network preflight checks**  
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
`95651d6c3979f12e5a8a63556b0030745d6fab34`. A fresh Python process cloned the
exact offline Git bundle, loaded the canonical plan and independently reproduced
the plan review as `PASS`. No notebook, dataset or model was published and no
training process was started.

The immutable work allocation is:

- declared seeds: `1197953491`, `20344180`, `1491619630`;
- exactly `100,000` aggregate non-forced choices per seed;
- exactly four `25,000`-choice streams per seed: masked bandit, recurrent cue,
  variable-option ordered multi-select, and recurrent-cue stateless control;
- evaluation choices excluded from the training budget and no result-dependent extension;
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
  `617c46cbf05a985f4cd1d462f9408a8ce39dc63f20104396dc21335f7184855b`;
- source bundle: 6,961,132 bytes, SHA-256
  `102b802fb1d54355308ebf8d19b759909950f507559cdad329f279d47cbe4fe5`;
- source manifest SHA-256
  `d7cc817551f79fa5d093111d960bbd4c3958b2a8dd0956d6c3a07e22a8a37cea`;
- input manifest SHA-256
  `2c9fa5e441701c2b9ff92e2d05e73513173ddd8ff362565c424c37b5c620ff52`;
- single notebook SHA-256
  `1eb6192891f96ca128ce75342dc3d0dbb41d2a66acb367a1275d4c3589c9447c`;
- safe plan report SHA-256
  `f409ab1bb0d0fdffa4a9ddce7df952253485ad605c16ce7deb71f211346afc05`;
- independent review report SHA-256
  `d7e6b3f41bcd47494a95bf07f964c6caeea27268a244cf152f79edf478913f64`.

Final validation passed 172 G3 tests, all 375 Python tests, repository-wide Ruff,
dashboard rebuild with 115 ingested records and zero quarantine, dashboard
doctor, seven frontend unit tests, the production build and four Playwright
browser tests. Five failed or transient plan-freeze branches are retained with
their evidence, correction and successful rerun in the safe plan report.

## Approved Publication State

The corrective publication is recorded in
`reports/jobs/g3a-cloud-input-publication-v2.json`. The private dataset
`ashok205/kptcg-g3a-correctness-inputs` version `2` is `READY`; version `1` is
retained only for audit. Kaggle exposes exactly the four corrected files, and an
independent remote download reproduced every local byte count and SHA-256.

The corrected notebook remains local-only at
`private/kaggle/notebooks/kptcg-g3a-cloud-correctness-v1.ipynb`, 4,787 bytes,
SHA-256 `1eb6192891f96ca128ce75342dc3d0dbb41d2a66acb367a1275d4c3589c9447c`.
It contains no Kaggle secret lookup, authorization environment-variable check,
authorization CLI flag or external URL request. The assistant did not create,
launch or monitor a Kaggle notebook session.

G3a remains `BLOCKED / NOT_REVIEWED`. The user imports the corrected notebook,
attaches only dataset version `2`, selects CPU and runs all cells without adding
a secret, environment variable, authorization cell or network probe. The
remaining evidence is the complete saved-output download, byte/SHA-256
verification and passing strict run review. Neither the plan nor dataset
publication makes a Pokemon policy-strength claim.
