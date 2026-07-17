# 08 — Local, Colab, Kaggle and Modal Runbooks

## General rules for every run

No cloud command is allowed until it has:

- a clean or explicitly recorded Git commit;
- a resolved config and config hash;
- exact asset/card/deck/model/opponent hashes;
- maximum wall time, decisions/games and estimated cost;
- durable output/checkpoint destination;
- resume and kill procedures;
- a unique run ID;
- `doctor`/preflight output;
- a declared question and pass/fail gate.

Training throughput is measured in **non-forced learner-controlled choices/s**, plus complete games/s. Raw engine calls, neural calls, decoder tokens and opponent/forced calls are reported separately.

## Resource roles

| Platform | Primary role | Explicitly avoid |
|---|---|---|
| Local Ubuntu/RTX 3050 | engine correctness, replay catalog/filter, feature/action development, CPU inference, packaging | long GPU training, broad raw replay cache |
| Colab Pro | rapid GPU numerical/model/PPO smoke, checkpoint portability | source-of-truth notebook logic, unattended main run |
| Kaggle notebook | competition/runtime parity, short T4/P100 smoke, controlled bakeoff/evaluation | consuming full 45h before G3; relying on TPU for PyTorch v0 |
| Modal | main actor/learner run, large tournaments, exploiters | any main spend before G4, unbounded functions, uncheckpointed jobs |

## Local runbook

Hardware reported: Ryzen 7 4800H, 16 GiB RAM, RTX 3050 4 GiB, about 30 GiB free.

Start:

```bash
uv sync --frozen --group local --group dev
uv run ptcg doctor --json runs/preflight/local-doctor.json
uv run pytest -m "unit or contract" -q
uv run ptcg engine smoke --games 1000 --workers 1
uv run ptcg engine benchmark --workers 1,2,4,8
```

Use `spawn` multiprocessing explicitly and one battle per worker. Start with 4 workers; benchmark 1/2/4/8 rather than assuming all logical cores improve throughput. Cap memory and preserve an 8 GiB emergency disk floor while replay work is active.

For replay work, set project-local KaggleHub cache and account for it in the disk cap. Default raw replay ceiling is 10 GiB. Use external/Drive/cloud storage for deeper retained corpora.

Local deliverables before cloud:

- engine/resolver corpus and tests;
- deterministic config/run manifest system;
- CPU batch-1 model latency;
- packaged checkpoint round-trip;
- small replay sync/meta snapshot;
- exact cloud input bundle with checksums.

## Colab runbook

Use a thin notebook that:

1. checks out/uploads the exact private commit;
2. installs the platform-specific pinned export without replacing the working CUDA PyTorch build;
3. mounts/accesses private assets without copying them into Git;
4. runs `ptcg doctor` and a 100-game engine smoke;
5. runs a CUDA model forward/backward parity check before any GPU training;
6. executes one CLI command from a resolved config;
7. writes checkpoints/config/metrics to durable storage every 10–15 minutes;
8. downloads/syncs the final run manifest before disconnect.

Recommended Colab jobs:

- forward/backward and mixed-precision tests;
- toy recurrent PPO three-seed validation;
- 25k–1M non-forced learner-choice CABT smoke runs;
- model-width and action-head micro-ablations;
- checkpoint CPU/GPU portability;
- emergency continuation only if Modal is unavailable.

Do not use whichever large GPU appears merely to increase batch size. A 1M model is usually actor/simulator constrained. Record utilization and stop if GPU duty cycle stays very low while actor queues starve.

Colab stop conditions:

- notebook-only edits not committed to the package;
- missing durable checkpoint path;
- invalid/fallback count >0;
- NaN/Inf or unbounded KL;
- remaining session time below two checkpoint intervals;
- asset or card hash mismatch.

## Kaggle notebook runbook

Reported budget: 45 GPU hours, commonly 2×T4 or P100, plus TPU time. TPU is not part of v0 because native CPU engine integration and PyTorch multiprocessing add migration cost.

Use Kaggle for:

- official environment and file-layout parity;
- T4/P100 smoke after local G3 tests;
- equal-budget finalist deck runs where the attached engine is accessible;
- evaluation/tournament jobs separate from the learner;
- clean submission ZIP validation.

Suggested protected GPU-hour envelope (adjust after measured jobs):

| Use | Cap |
|---|---:|
| Environment/model/PPO smoke | 6 h |
| Deck finalist bakeoff | 8 h |
| Controlled challenger/ablation | 10 h |
| Final evaluation/packaging | 10 h |
| Emergency reserve | 11 h |

Do not use both T4s for data parallelism initially. Use one learner/inference GPU and, if useful, the second for evaluation or a different fixed run. Compare against single-GPU throughput first.

Every Kaggle notebook output must include the Git/config hashes, canonical deck hash, deck-file SHA-256 and checkpoint manifest. An attached Kaggle dataset is not automatically the same version as the local package; hash it.

## Modal architecture

### Components

1. **Build/preflight function:** creates pinned image, imports private assets from an approved secret/volume, runs doctor/tests and exits.
2. **Actor workers:** CPU-heavy containers, multiple one-engine processes each; optionally actor-local CPU policy.
3. **Inference/learner:** one T4/L4/A10-class GPU only after benchmark; batches current and frozen policies; runs PPO.
4. **Evaluation workers:** isolated CPU containers reading immutable checkpoints.
5. **Persistent volume:** checkpoints, resolved configs, metric logs, league registry and redacted reports.

Do not place the engine in a public image or artifact. Confirm competition terms for private cloud storage and create a post-competition deletion checklist.

The first topology benchmark should colocate one learner/inference GPU with roughly 8–16 CPU actor processes in one Modal application/container boundary using shared memory or local IPC. Never make one remote function/RPC call per engine decision; network scheduling latency would dominate. Scale actor processes across 1/2/4/8/16/32 only while games/hour and cost per useful choice improve.

### Required Modal controls

- `timeout` on every function;
- `retries` only for idempotent setup/evaluation tasks, not blind learner duplication;
- concurrency and container-count caps;
- dollar/time budget guard inside the coordinator;
- verified-price resource-second/container caps that do not depend on delayed live billing data;
- heartbeat and last-checkpoint age monitor;
- atomic checkpoint writes to temporary name then rename;
- one elected learner via lock/lease;
- clean SIGTERM checkpoint path;
- queue backlog and policy-version-lag limits;
- volume commit/reload test;
- documented stop command.

### Preflight progression

```text
image build → doctor → 100 games → 10-minute actor/inference test
→ 2-hour canary → forced restart/resume → approved main run
```

At each stage compare:

- actor-local CPU inference;
- central GPU inference with batch sizes 16/32/64/128 and 1–2 ms delay;
- 1/2/4/... engine processes per container;
- queue serialization overhead;
- games/s and non-forced learner-controlled choices/s;
- memory slope and estimated dollars per million useful decisions.

Select the configuration minimizing cost per useful decision subject to learner stability and wall-clock deadline.

### Modal budget envelope

Treat the two reported $30 credits as separate account envelopes, and use both only if permitted by Modal’s current terms. Persistent volumes, secrets and checkpoints do not implicitly cross accounts. Keep each account below a conservative $28 cap:

| Account | Category | Provisional cap |
|---|---|---:|
| A | image/preflight/canaries | $4 |
| A | initial champion league | $24 |
| B | approved champion continuation or hard-matchup work | $12 |
| B | large evaluation/exploiters | $10 |
| B | emergency reserve | $6 |

Before any account-B continuation, prove an explicit export/import drill: atomically export checkpoint, optimizer, league registry, resolved config and hashes from account A to a user-controlled approved private location; verify checksums locally; bootstrap the private assets and pinned image in account B; import; run numerical/checkpoint-resume parity; and preserve separate cost ledgers. If cross-account use is not permitted or this drill fails, account A’s $28 envelope is the complete Modal campaign unless the user explicitly approves paid overage. Check current prices at execution and calculate caps from actual CPU, RAM, GPU, storage and egress. A coordinator must stop before the declared cap, not merely report cost afterward.

## Main-run protocol

1. Verify G4, the D1 canonical deck hash and exact deck-file SHA-256.
2. Create an immutable campaign record composed of bounded resumable chunks (initially no longer than about six hours each); never rely on one 60-hour function invocation.
3. Start a short rollout and inspect reward/outcome distributions manually.
4. Enable the approved opponent mixture.
5. Checkpoint every 10–15 minutes and at evaluation boundaries.
6. Run fixed evaluation asynchronously only from immutable snapshots.
7. Promote through the evaluation service; do not let the learner overwrite champion.
8. Stop automatically on invalid/fallback, NaN/Inf, excessive KL, queue/version lag, memory/cost threshold or stale checkpoint.
9. Export the last safe checkpoint and full manifest even after failure.

At G4, snapshot current platform prices and translate the dollar envelope into conservative maximum GPU/CPU/RAM resource-seconds and container counts. Enforce both resource caps and the USD estimate; real-time billing may lag and is not the sole kill switch.

## Portability tests

Every candidate checkpoint must load:

- locally on CPU;
- on the smoke GPU platform;
- in the Modal image;
- inside a submission-like clean environment with network disabled.

Compare logits/value/hidden-state updates on a fixed observation fixture within numerical tolerance. Quantized models require their own parity and full evaluation, not an assumption.

For final CPU submission benchmarking, test `torch.set_num_threads(1)` and any officially permitted alternatives, preload weights once globally, and report per-call plus cumulative per-game inference time. Use the current official runtime limit rather than an invented millisecond threshold.

Allocate experiments by successive halving: several bounded 1–5M non-forced-choice smoke runs, then one champion and one controlled challenger. Do not fund four full PPO configurations.

## Compute progress report

For each cloud run report:

- platform/device/container image;
- run/config/commit hashes, canonical deck hash, deck-file/checkpoint hashes;
- requested and actual wall time/cost;
- actor processes and inference layout;
- raw/encoded/neural/non-forced learner-choice/decoder-token rates and games/s;
- CPU/GPU utilization, inference batch p50/p95 and queue lag;
- peak/slope memory;
- checkpoint interval and forced-resume result;
- PPO health metrics and opponent distribution;
- evaluation result, reliability counters and next recommendation.
