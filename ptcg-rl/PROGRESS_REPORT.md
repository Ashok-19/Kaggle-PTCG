# Progress Report

Current gate: **G3a recurrent PPO correctness proof**  
Current verdict: **BLOCKED / NOT_REVIEWED**  
Latest completed milestone: **local PPO correctness harness passed independent micro-qualification**  
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

This is a toy-only local micro-qualification. It does not satisfy the frozen
25,000-to-100,000-choice per-seed G3a cloud budget and does not establish policy strength.
The remaining blockers are an exact reviewed private Kaggle/Colab run plan and
explicit user training approval before launch.
