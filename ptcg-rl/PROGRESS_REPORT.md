# Progress Report

Current gate: **G3a recurrent PPO correctness preparation**  
Current verdict: **BLOCKED / NOT_REVIEWED**  
Latest completed milestone: **strict evaluation contract frozen and independently audited**  
Cost: **USD 0**

The evaluation-only G3a contract is implemented at
`configs/g3a_evaluation_v1.json` and bound to implementation commit
`6ca84cf7ccd79e49341998314da6d32aa8f1de45`. It freezes the exact
three-seed toy-task rules, recurrent-over-stateless margin, probability-replay
tolerances, zero-tolerance counters, checkpoint-resume requirements and the
accepted G3b, D1 and champion thresholds without adding PPO hyperparameters or
authorizing training.

Evidence used to select the design:

- the legacy evaluation YAML covered none of nine checked G3a criteria, none of
  nine sampled future thresholds and contained five unresolved placeholders;
- a G3a-only contract was rejected because it would permit future threshold drift;
- the selected exact versioned contract covers all checked current and future
  criteria and structurally forbids paired-engine-seed claims, blended promotion
  scores and unauthorized training;
- the recurrent cue task has an exhaustive stateless ceiling of `0.50`, recurrent
  oracle ceiling of `1.00`, frozen minimum recurrent score of `0.85` and minimum
  per-seed margin of `0.25`.

Validation completed:

- 83 implementation-focused G3a edge-case tests passed before the implementation commit;
- final promotion validation passed 86 focused G3 tests and 289 complete Python tests;
- Ruff passed;
- dashboard rebuild ingested 107 records with zero quarantine, dashboard doctor passed,
  seven frontend unit tests passed, the production build passed and all four browser tests passed;
- an independent committed-tree audit rejected 10 contract mutations and 17
  evidence-failure branches and accepted a separately constructed valid record;
- no training, Kaggle/Colab launch, Modal use, submission or external mutation occurred.

Authoritative evidence:

- `reports/artifacts/g3a-evaluation-contract-v1.json`
- `reports/gates/g3a.json`
- `tests/g3/test_evaluation.py`
- `tests/g3/test_evaluation_script.py`

The remaining G3a blockers are the PPO correctness implementation, versioned toy
environments, measured smoke allocation, exact bounded three-seed run plan and
explicit user approval before launch. The next work is local correctness code and
tests only; it must not be described as training progress or policy strength.
