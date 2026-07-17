# 01 — Master Implementation Plan

## Outcome

Deliver a reproducible, legal, fast and statistically evaluated recurrent RL specialist, trained on the best evidence-selected deck and packaged as a safe Kaggle submission. The plan deliberately separates engineering proof, deck discovery, algorithm proof and expensive scaling.

## Workstreams

1. Engine/environment correctness.
2. Filtered replay ingestion and current-meta intelligence.
3. Deck discovery and controlled selection.
4. Semantic recurrent policy and action decoder.
5. Recurrent PPO and population training.
6. Evaluation, ladder feedback and submission reliability.
7. Reproducible compute across local, Colab, Kaggle and Modal.

## Phases and hard gates

### Phase 0 — Inventory and reproducible repository (Gate G0)

Tasks:

- create a private Git repository;
- record SHA-256 hashes and provenance for every supplied archive;
- inspect rather than assume archive layout/version;
- copy/link competition-only engine assets into ignored local paths;
- implement `scripts/bootstrap_assets.py` and `ptcg doctor`;
- create pinned base/dev/cloud dependency locks;
- capture OS, Python, compiler, CUDA/PyTorch and native-library versions;
- record the official deadline, submission limits and engine version in project status.

Gate G0 requires:

- one clean command creates the environment from a fresh clone;
- `ptcg doctor` finds all required assets and reports actionable errors;
- no secret, engine binary/source, replay, checkpoint or large generated artifact is tracked;
- unit-test discovery works;
- the repository instructions and status files exist.

### Phase 1 — Engine contract and test harness (Gate G1)

Implement the thin engine adapter, canonical observation/action objects, battle lifecycle, legal random agent and deterministic test fixtures where possible. Establish one battle per process. Treat terminal state, logs and multi-select as explicit contracts.

Gate G1 requires:

- build/load test on Ubuntu 22.04;
- at least 10,000 complete random/rule games with zero Python invalid selections;
- at least 1,000,000 legal selection operations across fuzz/property tests;
- terminal result checked before stale selection data;
- log retrieval called once and burst sizes handled without truncation;
- multi-select order/uniqueness/min/max invariants tested;
- separate recurrent-memory lifecycle tested for both players;
- 6-hour or equivalent bounded soak with RSS trend reported;
- raw, encoded and rule-policy throughput at 1/2/4/8 workers recorded.

Do not begin PPO implementation if G1 fails.

### Phase 2 — Filtered replay and meta pipeline (Gate R1)

Build the provider-neutral catalog and downloader described in `04_REPLAY_META_PIPELINE.md`. First retrieve the tiny official index and the `manifest.csv` for selected daily datasets. Discover the exact daily manifest schema before implementing row filters. Never fall back to a whole-dataset download.

Gate R1 requires:

- index update and version/dataset diff are idempotent;
- dry-run lists exact files, estimated bytes and rejection reasons;
- hard download byte/file limits are enforced before network writes;
- a small user-approved filtered set is individually downloaded;
- re-running downloads zero duplicate bytes;
- corrupt/incomplete files are quarantined;
- normalized episode/deck/event tables pass schema and referential checks;
- raw-to-derived lineage and hashes are queryable;
- a seven-day meta snapshot and coverage report can be generated;
- public actions cannot enter PPO storage by construction.

### Phase 3 — Tensor/action environment and model (Gate G2)

Implement visible-state entity packing, global features, semantic legal-option resolution, ragged batching, recurrent memory and the <2M network. Create a Gym-like internal interface only if it does not force an incorrect fixed action space.

Gate G2 requires:

- every option from the G1 corpus resolves to a canonical token or fails with a minimized fixture;
- option permutations map back to the same engine choices;
- all legal options are scoreable, including option counts above 64;
- autoregressive multi-select emits only ordered, unique, legal lists;
- forced choices update memory but create no v0 policy/value/GAE loss node;
- hidden-state reset/ownership tests pass;
- forward/backward/serialization parity tests pass on CPU and GPU;
- parameter count <2M and latency/memory benchmarks are reported;
- policy can complete 10,000 games with zero structural invalid actions.

### Phase 4 — PPO proof (G3a correctness → G3b competence)

Use Colab/Kaggle for short training, but keep source/configs in the repository and artifacts in durable storage. Validate PPO on a tiny deterministic toy environment before CABT. Then train on the engineering deck against random/rule agents.

Gate G3a uses the 25k–100k-choice smoke configuration and requires:

- toy recurrent POMDP learns in at least 3 seeds;
- stored old log-probabilities reproduce before an update;
- masked/forced actions produce correct loss terms;
- GAE/returns, truncation and terminal handling have unit tests;
- no NaN/Inf; KL, clip fraction, entropy, explained variance and gradient norms are logged;
- checkpoint resume reproduces counters, optimizer, league and RNG state as far as engine randomness permits;
- neural rollout throughput and cost are measured.

G3a is an algorithm/integration proof, not a strength claim. Gate G3b then allocates bounded 1–5M non-forced learner choices through successive halving and requires the engineering-deck policy to materially beat random and improve against at least two fixed rule anchors with multi-seed evidence. Set the actual G3b choice budget from measured throughput before launching it.

If G3a fails, debug correctness. If G3a passes but G3b fails, diagnose representation, sparse credit and opponent coverage before changing algorithms. D1 Tier-D bakeoff may not begin until G3b passes.

### Phase 5 — Deck discovery and equal-budget RL bakeoff (Gate D1)

Run four tiers:

1. recent replay/meta shortlist;
2. legality and structural-complexity screening;
3. optional simulator screening with a validated generic candidate-deck pilot; official rule agents remain bound to native decks;
4. same-code, multi-seed PPO successive halving with equal transition budgets within each round and a common cumulative budget for final comparison.

Freeze opponent population, seats, compute/transition budget and meta weights before Tier 4. Details are in `05_DECK_DISCOVERY.md`.

Gate D1 requires:

- 6–10 candidate families documented, then 3–5 finalists;
- valid exact deck lists and provenance for every finalist;
- within-round equal-budget learning curves and uncertainty; final selection compares equal-cumulative-budget candidates, using 3 seeds where the predeclared budget permits;
- complete finalist matchup matrices on a frozen population;
- reliability and catastrophic-matchup constraints applied before the primary objective;
- exact main deck selected and hashed;
- one runner-up retained as fallback; no further deck changes without a decision review.

### Phase 6 — Scale readiness and main Modal league (G4 → G5)

Before spending the main budget, run a short Modal canary. Benchmark actor-local CPU inference and central batched GPU inference. Select the cheapest architecture that meets throughput and stability—not the one with the most GPU utilization.

Gate G4 (scale readiness) requires:

- container can rebuild from a pinned image;
- persistent checkpoint/log volume tested through forced restart;
- 2-hour canary has stable memory, no invalids, bounded queue lag and expected cost;
- learner policy-version lag is exactly zero, one learner version spans each complete recurrent episode/batch, and hidden state never crosses versions;
- throughput and projected cost fit the remaining budget;
- kill switch and spending cap verified.

Main run:

- train the exact D1 deck;
- bootstrap from rule/fixed policies only as long as useful;
- add current/frozen checkpoints and PFSP;
- promote champions only by evaluation;
- retain immutable snapshots and a trusted anchor;
- start exploiters only after a competent champion exists.

Gate G5 requires a champion that beats the frozen baseline population with statistically credible aggregate improvement, has no constraint violation and survives full runtime/reliability evaluation.

### Phase 7 — Exploitation defense and finalization (G6)

- train targeted RL exploiters against the champion;
- mine lost replay contexts and hard matchups;
- use curriculum/opponent weighting before reward shaping;
- run only pre-approved ablations with a controlled challenger;
- optionally test quantization, privileged critic, auxiliary heads or search distillation one at a time;
- freeze architecture at T−7 and training code/config at T−4;
- package anchor and challenger; validate offline with network disabled.

Gate G6 requires:

- final matchup matrix with seats and frozen meta weights;
- key matchups receive serious sample counts;
- zero invalid/crash/timeout events in final soak;
- load time, package size and p50/p95/p99 latency inside official limits with margin;
- deterministic legal fallback tested by injected failures;
- exact submission ZIP hash recorded;
- rollback anchor preserved.

## Review protocol

After each gate:

1. stop expensive work;
2. fill the progress report;
3. include the exact Git commit, resolved configuration, data/model hashes and raw outputs;
4. report failures as well as passes;
5. request review before changing a locked decision or entering the next compute-heavy phase.

Low-cost test fixes within the current gate do not require separate approval. Main training, a deck change, an algorithm switch, reward shaping, behavior cloning or inference search always require an explicit decision update.
