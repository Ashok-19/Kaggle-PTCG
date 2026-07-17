# 12 — Exact First-Week Execution

This is the local Codex agent’s initial queue. Complete and report each day/gate; dates may shift, but dependencies may not.

## Day 1 — G0 inventory and bootstrap

Implement:

- private Git repository and root `AGENTS.md`/`PROJECT_STATUS.md`;
- `.gitignore` and staged-file denylist before asset extraction;
- archive-safe asset importer with SHA-256 manifest;
- pinned Python environment and test/lint entry points;
- `ptcg doctor` with redaction;
- read/record engine license and exact official deadline/runtime facts.

Run:

```bash
git status --short
uv lock  # one reviewed creation after platform dependency sources are defined
uv sync --frozen --group local --group dev
uv run ptcg assets import --official-archive ... --sample-agents ... --research ...
uv run ptcg doctor --json runs/preflight/g0-doctor.json
uv run ruff check .
uv run pytest -m unit -q
git status --short
```

Stop and report G0. No cloud use.

## Day 2 — Engine lifecycle

Implement native adapter, immutable transition snapshot, one-battle worker, random legal agent, terminal-first handling, one-shot logs and crash capsules.

Acceptance:

- 1,000 complete random games;
- zero adapter invalids;
- terminal never acts on stale selection;
- new battle cleans all state;
- exact throughput and peak RSS reported.

## Day 3 — Resolver and compound actions

Inventory every observed selection/option pair from rule/random games. Implement canonical semantic options, snapshot-local positional resolution, option permutation/mapping, ordered autoregressive multi-select legality and two-player memory lifecycle stubs.

Acceptance:

- 100,000+ selections initially, then work toward the G1 one-million gate;
- every observed option resolves without silent fallback;
- no 64-option truncation;
- permutation property tests pass;
- min/max/STOP/order/uniqueness tests pass.

## Day 4 — Rule harness, benchmark and soak

Adapt the four official rule notebooks into private test-only agents without treating them as policy labels. Build seat-swapped tournament and 1/2/4/8 process benchmark. Begin six-hour soak.

Acceptance:

- all rule agents/decks finish games;
- matrix/seat split exists;
- raw and encoded throughput baselines exist;
- failure and RSS slopes are reported;
- G1 report submitted when the full gate passes.

## Day 5 — Replay R0 schema/download probe

Implement provider protocol, catalog, exact official index/daily manifest adapters, immutable filter plan, dry-run and hard byte caps. Ask the user for Kaggle MCP details in `LOCAL_KAGGLE_MCP_NOTES.md`. Verify manifests first; then generate, dry-run and obtain review of an immutable one-episode probe plan before downloading that named episode. Otherwise use KaggleHub single-file mode under the same plan contract.

First real plan:

- one recent day;
- at most 20 episode JSONs;
- at most 250 MiB;
- exclude >64 MiB files;
- deterministic rating/time strata;
- no whole-dataset fallback.

Parse, QA, rerun to prove zero duplicate download, then report R0. R1 remains open until a quality-tested seven-day sample and reproducible 3/7-day reports exist. Produce the 14-day stability report only after the explicit days-8-through-14 extension has coverage; otherwise report `INSUFFICIENT_COVERAGE`.

## Day 6 — Tensor schemas and network

Implement exact card table, visible entity/global/event encoders, packed ragged options, Entity-Transformer-GRU, actor/value heads, compound-action cache and strict checkpoint metadata.

Acceptance:

- <2M parameters;
- no silent tensor truncation;
- CPU/GPU serialization parity;
- every legal option scoreable;
- zero structural invalids over 10,000 games;
- parameter, latency, packing and end-to-end throughput reported.

## Day 7 — Recurrent PPO smoke and cloud portability

Implement sequence rollout buffer, GAE, forced-action masks, compound logp, recurrent minibatches, PPO update, health metrics and atomic resume. Prove on toy environments, then run 25k–100k non-forced learner-controlled CABT choices locally/Colab or Kaggle. Build the Modal image and run doctor only.

Acceptance:

- toy memory task learned in 3 seeds;
- actor/learner logp agreement;
- no NaN/Inf/invalid/fallback;
- CABT improvement over random is reported as a diagnostic only and is not required for G3a;
- checkpoint resumes and moves cloud→local;
- Modal preflight passes without main training;
- G3a correctness report submitted; measurable strength is enforced only at G3b, a separate larger bounded run after review.

## Week-one output checklist

- private reproducible repository;
- exact asset/license manifest;
- tested one-battle/process engine adapter;
- complete semantic action resolver;
- benchmark and soak report;
- filtered incremental replay R0 probe and, if time/data permit, first seven-day R1 meta snapshot;
- <2M recurrent policy completing games;
- correct PPO smoke with cloud-portable checkpoint;
- deck candidate shortlist, but no unvalidated main-deck claim;
- Modal image/preflight only, with main budget intact.
