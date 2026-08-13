# Continue KPTCG — GPU Engine Completion → Accelerated BC / Self-Play PPO

Use this file as the **entry prompt for the next ChatGPT session**.

Continue the 2026 Kaggle Pokémon TCG AI Battle project from the **repository-grounded canonical handoff**. Do not reconstruct the project from memory, assumptions, stale leaderboard data, old assistant summaries, public notebooks or intuition.

The project is now at the transition from an almost-complete GPU CABT engine to learned-controller training. The immediate job is **not another Dawn heuristic iteration** and **not an online PPO launch yet**. The immediate job is to finish the remaining whole-engine qualification and final local benchmark so the training architecture can use the GPU simulator with confidence.

---

## Local MCP / repository routing

Use `Local_mcp`.

Canonical Git/root repo id:

```text
ptcg
```

Canonical Git root:

```text
/home/nnmax/Desktop/kaggle/PTCG
```

Code/source repo view:

```text
ptcg-rl
/home/nnmax/Desktop/kaggle/PTCG/ptcg-rl
```

Use:

- `ptcg` for Git status/diff/review/commit, root docs and `.chatgpt/handoffs`;
- `ptcg-rl` for source/tests/reports/scratch reads and validation.

**Every accepted incremental commit must be made at the root repository.** Do not treat `ptcg-rl` as a separate repository for commits.

Do not push unless explicitly instructed.

---

## Mandatory first reads

Read these **fully and in order** before proposing or changing GPU/training code:

1. `.chatgpt/handoffs/current.local.md`
2. `.chatgpt/handoffs/KPTCG_GPU_TRAINING_MASTER_PROMPT.local.md`
3. the dated GPU continuation handoff named by `current.local.md`
4. this `continue_prompt.md`
5. `RULES.md`
6. `AGENTS.md`
7. `ptcg-rl/AGENTS.md`
8. `ptcg-rl/.chatgpt/KPTCG_PROMOTION_CRITERIA.local.md`
9. `ptcg-rl/.chatgpt/KAGGLE_DATASET_RUNTIME_RULES.local.md`
10. `.chatgpt/handoffs/KPTCG_GOLD_PATH_MASTER_PROMPT.local.md` for the older Dawn/search/live/replay history
11. `ptcg-rl/reports/deterministic/CURRENT_HANDOFF.md` for the later deterministic/BC evidence
12. the current `ptcg-rl/src/ptcg_rl/gpu_cabt/` source tree

Do not skip the older master: it contains important rejected experiments and exact evidence that the new GPU master intentionally summarizes rather than duplicates line-for-line.

---

## Verify actual repository state before doing anything

Run read-only checks first:

```bash
git status --short -uall
git log --oneline --decorate -20
git branch -vv
git remote -v
```

At the final handoff construction snapshot, the accepted GPU code had advanced to:

```text
75ad70b gpu-cabt: hide attack execution metadata
898f98e gpu-cabt: mask private public-log fields
74b322e gpu-cabt: make terminal event projection a no-op
2ea2d3a gpu-cabt: integrate setup and public event runtime
df484a6 docs: add current KPTCG continuation prompt
dc758e2 gpu-cabt: add public policy projection
ba3bf46 gpu-cabt: add unified game runtime
810641a gpu-cabt: derive rule table sizes
cc9becc (origin/main) preserve accumulated KPTCG gold-path evidence
```

`origin/main` was still `cc9becc` and no push was requested.

The documentation/handoff commits created after this text may make HEAD newer. **Do not infer final HEAD from this file. Verify it.**

The public-event/runtime code that was dirty earlier was subsequently accepted and committed in `2ea2d3a`, followed by the terminal projection correction `74b322e`. Therefore the next session must not reset to the older `dc758e2` state or repeat “public logs are still uncommitted” as current truth.

`898f98e` additionally masks private fields from the public-log projection and adds `ptcg-rl/scripts/gpu_cabt_local_public_log_smoke.py`, `ptcg-rl/src/ptcg_rl/gpu_cabt/public_log.py`, and `ptcg-rl/tests/test_gpu_cabt_public_log.py` as durable privacy/qualification support.

That option-projection refinement was subsequently accepted in `75ad70b gpu-cabt: hide attack execution metadata`, covering `policy_projection.cu`, `public_option.py`, and `test_gpu_cabt_public_option.py`. It removes execution-only attack/source metadata from learner-visible options and keeps option parameters aligned with the native agent-visible schema.

---

# Mission

The strategic goal is a **gold/top-10 level KPTCG agent**, with >1000 Elo as an operational milestone and the existing hard promotion target of **>95% broad native win rate** across diverse opponents/both seats.

No result is guaranteed.

The user's current strategic decision is:

> **Fully exploit GPU-resident CABT simulation so BC/self-play PPO can train vastly faster than the old CPU-environment path. Complete the GPU engine first, test everything on the local 4 GB GPU, then plan online training.**

The user is open to a larger recurrent model and full self-play PPO if measured GPU throughput supports it.

Do not compromise CABT semantics or public-information boundaries to get a flattering throughput number.

---

# Current strategic pivot

## Dawn is no longer the primary optimization center

Historical raw Dawn remains useful as a reference/fallback and once achieved a historical live score around 858.3. Later Dawn/Search micro-patches repeatedly failed to transfer, and live scores/current active submissions are far below gold.

Do not resume a Dawn guard-stacking loop unless materially new evidence changes the strategy.

Exact current-turn search remains useful as an offline tactical proof/counterfactual oracle. Native long-horizon RNG cannot be branch-seeded reliably, so full-game search rollouts are not authoritative value labels.

## Exact Mega Lucario deck is already proven elite

The local deck:

```text
ptcg-rl/.chatgpt/tmp/today-lucario-variants/lucario-modern-v1
```

was verified to match elite public Luca/Majkel 60-card lists.

Exact list:

```text
13 Fighting Energy         6
4  Mega Lucario ex         678
4  Ultra Ball              1121
4  Premium Power Pro       1141
4  Fighting Gong           1142
4  Poke Pad                1152
4  Judge                   1213
4  Lillie                  1227
3  Solrock                 676
3  Riolu                   677
2  Makuhita                673
2  Hariyama                674
2  Lunatone                675
2  Switch                  1123
2  Boss's Orders           1182
2  Wally                   1229
1  Hero's Cape             1159
```

Earlier verified public snapshots had Luca ~1222 and Majkel ~1173 using this exact shell. The important fact is not the stale score: **the deck itself is demonstrably capable of gold-region strength. The missing ingredient is controller quality.**

Primary learned lane should therefore use this exact deck initially.

---

# Elite replay/controller evidence

Current Luca corpus:

```text
ptcg-rl/scratch/elite-distill-2026-08-13/luca-55447414/
```

- 76 replay files downloaded;
- ~302 MB;
- 75 usable Luca-vs-other episodes after excluding validation/self.

Elite-vs-elite sample:

```text
ptcg-rl/scratch/elite-distill-2026-08-13/replays/
```

Existing local Lucario controller audit against Luca:

```text
5022 active decisions
overall semantic agreement 2992/5022 = 59.58%
MAIN/context0 agreement 1214/2752 = 44.11%
```

Forced/subselection contexts are often 80–98%+, so the strategic gap is MAIN sequencing:

- Lunatone use vs END;
- attack-now vs development;
- Fighting Energy attachment target;
- Premium Power Pro/Fighting Gong/Poke Pad/Ultra Ball sequencing;
- Judge/Lillie/Boss/Wally timing.

Do not waste time solving already-high-accuracy forced subcontexts while ignoring MAIN strategy.

---

# Negative learned-controller history — do not repeat blindly

### Luca LightGBM ranker

```text
scratch/elite-distill-2026-08-13/train_luca_lgbm_v2.py
```

Approximate results:

```text
train MAIN semantic ~91.6%
validation ~58.4%
sealed test 57.6%
existing Lucario baseline on same test ~45.6%
```

Not enough.

### Focused MAIN GRU

```text
scratch/elite-distill-2026-08-13/train_elite_main_gru_v1.py
```

```text
216 train / 30 validation / 30 test episodes
7108 / 1047 / 906 MAIN decisions
54 semantic action tokens
best validation ~56.16%
sealed test ~56.29%
```

Did not break the tabular/tree ceiling.

### Tiny full recurrent canary

```text
scratch/elite-distill-2026-08-13/train_elite_recurrent_canary.py
```

32-step canary only:

```text
train loss 1.951 -> 1.556
validation overall 39.3%, MAIN 32.2%
test overall 42.3%, MAIN 32.3%
```

This was deliberately tiny/undertrained and does **not** prove the G2 recurrent architecture is incapable.

### Majkel history model

A model with ~65.8% imitation failed the larger native confirmation:

```text
pure control       100/240 = 41.67%
history c0.70       98/240 = 40.83%
```

Rejected. Do not retune the same threshold again.

### CBR + SA

~9061 MAIN decisions; validation ~58.1%, descriptive test ~56.3%. Rejected as primary policy.

High-confidence exact-state lookup has low ~5–7% coverage but very high observed precision in some samples. It may later become a tiny fast-path/cache, not the controller.

### Counterfactual simulated annealing

C++ SA itself is extremely fast, but shallow linear residual strategy weights failed independent holdouts:

```text
single-batch -> external batch2 mean reward change -0.039
robust two-batch -> untouched batch3 -0.0156
```

Conclusion: keep SA for high-level gating/league/search/training hyperparameters, not raw linear action policy.

---

# Historical BC status

Older E01 notebook documentation includes multiple blocked/unauthorized incidents, but later repository evidence supersedes the claim that production BC never ran.

`ptcg-rl/reports/deterministic/CURRENT_HANDOFF.md` records a completed advisor-only BC run:

```text
284 train episodes
32 validation episodes
840 optimizer steps
epoch-4 validation NLL 1.374653
native H2H:
  rule                         11-5
  pure BC                       2-14
  BC at MAIN/rule subselect     4-12
```

BC is not champion authority. Use BC as initialization before PPO.

---

# Existing recurrent PPO infrastructure

Important files:

```text
ptcg-rl/src/ptcg_rl/g2/network.py
ptcg-rl/src/ptcg_rl/g3/ppo.py
ptcg-rl/src/ptcg_rl/g3/checkpoint.py
ptcg-rl/src/ptcg_rl/g3/cloud_runner.py
ptcg-rl/reports/evaluations/e04-qualification-v1.json
ptcg-rl/reports/artifacts/g3b-competence-plan-v1.json
```

G2 recurrent semantic policy is roughly **970k parameters**.

Historical G2 reliability included 10,000 native games with zero reliability failures.

Historical native actor/model stack measured approximately:

```text
1,156,383 meaningful choices
5,058.581 s
228.598 choices/s
```

The GPU CABT port was created to remove this environment-generation bottleneck.

G3a PPO mathematical/toy correctness was completed historically; E04 actor/learner integration later passed. What has **not** happened is a convincing Pokémon self-play competence campaign that produced a gold controller.

---

# GPU CABT engine — accepted architecture

The runtime is pointer-free/fixed-capacity. One CUDA thread owns one environment and runs until a genuine decision boundary or terminal result.

Core files:

```text
ptcg-rl/src/ptcg_rl/gpu_cabt/native/state_core.h
ptcg-rl/src/ptcg_rl/gpu_cabt/native/state_fields.h
ptcg-rl/src/ptcg_rl/gpu_cabt/native/runtime_state.h
ptcg-rl/src/ptcg_rl/gpu_cabt/native/rule_static.h

ptcg-rl/src/ptcg_rl/gpu_cabt/cuda/setup_runtime.cu
ptcg-rl/src/ptcg_rl/gpu_cabt/cuda/game_runtime.cu
ptcg-rl/src/ptcg_rl/gpu_cabt/cuda/policy_projection.cu
ptcg-rl/src/ptcg_rl/gpu_cabt/cuda/public_log_core.cu
ptcg-rl/src/ptcg_rl/gpu_cabt/cuda/public_log_emit.cu
ptcg-rl/src/ptcg_rl/gpu_cabt/cuda/public_log_project.cu
ptcg-rl/src/ptcg_rl/gpu_cabt/cuda/runtime_api.cu
ptcg-rl/src/ptcg_rl/gpu_cabt/source.py
ptcg-rl/src/ptcg_rl/gpu_cabt/device_runtime.py
```

Do not introduce CPU gameplay fallback.

---

# Accepted GPU functionality

The accepted GPU implementation now includes:

- battle reset/deck card state;
- shuffle and persistent per-env RNG;
- IsFirst;
- opening hand;
- basic/doll/mulligan handling;
- automatic repeated mulligan/resetup;
- Active selection;
- prize setup;
- mulligan compensation draw selection;
- Bench setup;
- setup reveal/move-counter normalization;
- TurnStart rollover/draw;
- full fixed runtime buffers;
- complete flattened rule graph;
- exact packed native state-field views;
- all 102 TargetType predicates;
- all 24 ConditionType cases;
- all 74 continual effects 171–244;
- all 171 instant effects 0–170;
- central effect selection/pause/resume;
- triggered ability collection/order/activation;
- KO/prize/Lucky Bonus;
- state-based Refresh;
- bench/tool legality cleanup;
- Active replacement;
- Pokemon Checkup;
- turn end/checkup/start cycle;
- exact Main legal-option generation;
- Main action execution/resume;
- retreat interaction;
- attacks and special attack branches;
- terminal/result processing;
- unified `gpu_cabt_game_reset` / `gpu_cabt_game_step` dispatcher;
- public policy projection;
- device-native public event/log accumulation/projection;
- Python/CuPy/Torch runtime wrapper.

Do not assume every accepted subsystem proves final whole-game parity; complete-game qualification remains important.

---

# Important accepted semantic evidence

Examples already qualified:

```text
packed Card/Player/State ABI: native GCC vs NVRTC exact
full static rule graph device checksum exact
Refresh Lucario-Dragapult: 5088 / 5088 uint64 words exact
Refresh Lucario-Alakazam: 5088 / 5088 exact
```

Effect pause/resume probes covered:

- ordinary card selection;
- attached Energy;
- direct evolution;
- ability branch selection;
- effect decline/accept jump;
- iterative Energy discard;
- damage-counter movement/removal/placement.

Trigger probes covered:

- simultaneous ordering;
- ownership reversal;
- depth-0 outer-loop behavior;
- depth-1 recursive behavior.

KO gate covered:

- Mega-ex 3-prize handling;
- simultaneous KO obligation ordering;
- PreKO activation before movement;
- nested Lucky Bonus.

Refresh integration covered:

- bench overflow;
- tool overflow and continual recomputation;
- KO -> Active replacement;
- terminal finish;
- Checkup KO skip.

Turn/Main/attack integration probes also passed multiple normal and exotic paths.

Read the master handoff for more detail.

---

# Flattened rule graph

The rule graph is extracted at runtime from the local official engine. Do not commit official rule/card rows.

Current verified sizes:

```text
card rows       1268
skill rows       435
attack rows     1557
effect rows     3067
trigger rows      77
substring masks    7 x 40 words
total bytes     650760
strides          card72 skill48 attack56 effect144 trigger112
```

An earlier uint8 EnergyType truncation hazard was fixed. Preserve wide energy/type values.

---

# Unified setup/game runtime

Accepted at `ba3bf46`.

The setup state machine follows official `SetupProc.h`, including the subtle ordering around mulligan compensation.

Important native detail:

- compensation callbacks are pushed in basic-player order but execute LIFO;
- the second player's mulligan compensation may therefore resolve first.

`game_runtime.cu` validates:

- response count within native min/max;
- option indexes in range;
- uniqueness;
- selected stride;
- then resumes setup/effects/triggers/KO/Refresh/turn/Main/attack until next decision/terminal.

The policy host should not need a parallel CABT state machine.

---

# Public policy projection

Accepted at `dc758e2`.

Current public policy ABI:

```text
global width        24
player width        12 x 2
entity capacity     128
entity width        18
option capacity     128
option width        20
```

Visibility firewall:

- own hand visible;
- opponent hidden hand invisible;
- own/opponent deck identities hidden unless CABT selection explicitly exposes them;
- prize identities hidden unless revealed;
- field reverse state respected;
- attached visibility follows parent visibility;
- looking-zone visibility follows CABT actor/mode;
- legal option source/target semantic IDs only when publicly visible.

Do not weaken this for training convenience.

---

# Public event/log runtime

Accepted in `2ea2d3a`, with terminal no-selection event projection correction `74b322e`.

The runtime adds native-style ordered public events for:

```text
Shuffle
HasBasicPokemon
TurnStart
TurnEnd
Draw / DrawReverse
MoveCard / MoveCardReverse
Switch
Change
Play
Attach
Evolve
Devolve
MoveAttached
Attack
HpChange
Poisoned
Burned
Asleep
Paralyzed
Confused
Coin
Result
```

Current public log design:

```text
capacity       1024 events / environment
PublicLogState 32 bytes
event row       10 int32 fields
```

Each player has its own acknowledgment index. The buffer can compact only after both players have consumed the corresponding prefix.

Terminal/no-current-actor event projection was explicitly corrected to a safe no-op instead of reading stale selection actor state.

The next session should still **verify retained/public-log tests and whole-game event parity**, especially >200-event bursts and realistic games, before treating public logging as globally finished.

---

# Python/Torch GPU runtime

Current wrapper:

```text
ptcg-rl/src/ptcg_rl/gpu_cabt/device_runtime.py
```

Canonical CUDA source list:

```text
ptcg-rl/src/ptcg_rl/gpu_cabt/source.py
```

`GpuCabtRuntime` supports:

```text
reset(...)
step(...)
project_policy()
project_events(acknowledge=True)
status()
synchronize()
```

Policy/event/status batches expose `.torch()` using DLPack.

The intended actor path is:

```text
GPU CABT state
  -> GPU policy projection + unread public events
  -> Torch recurrent policy on same device
  -> GPU-selected legal option indexes
  -> gpu_cabt_game_step
```

Do not add an avoidable state/projection/action copy through CPU.

---

# Current GPU ABI after public logs

Latest handoff compile of the full canonical source reported:

```text
source bytes        560655
fast compile        ~6.166 s
BattleCoreState     21016 bytes
BattleRuntimeState  62320 bytes
policy global       24
player              12
entities            128 x 18
options             128 x 20
selected capacity   128
deck size           60
all-card capacity   128
public log capacity 1024
public event width  10
```

`GpuCabtRuntime(1)` initialization passed with this ABI.

Reverify after any subsequent commit.

---

# CUDA build/runtime facts

- The giant interpreter initially compiled extremely slowly because large switches were force-inlined.
- Heavy interpreter functions were changed to `__noinline__`; this eliminated the >180s NVRTC optimizer explosion.
- Native CUBIN loading is accepted.
- For development qualification, `GPU_CABT_NVRTC_FAST_COMPILE=max` typically reduces compile to a few seconds.
- Production training should build an optimized CUBIN once and cache/reuse it.
- CUDA default device stack was insufficient for deep effect call chains.
- 4 KiB passed the central activation probe; 8/16 KiB passed too.
- Current wrapper uses 16 KiB as a safety margin.
- Do not blindly set 64 KiB and destroy occupancy.

---

# Local GPU performance evidence

Hardware:

```text
RTX 3050 Laptop GPU
4 GB VRAM
```

## Refresh-only benchmark

```text
native CPU single thread ~2.29M Refresh operations/s
CUDA                  ~6.25M Refresh operations/s at batch 32768
speedup                ~2.73x
```

## Unified post-setup synthetic decision benchmark — BEFORE public log memory expansion

First sweep:

```text
64 env       ~27.2k decisions/s
128          ~51.0k
256          ~99.2k
512          ~187k
1024         ~453k
1536         ~652k
2048         ~825k
```

Larger sweep:

```text
2048         ~670k/s
3072         ~863k/s
4096         ~1.003M/s
6144         ~1.125M/s
8192         ~1.091M/s
```

Old sweet spot around 6144 envs.

The original 8192 timeout was a **benchmark fixture bug**: synthetic card refs exceeded fixed 128-card capacity and corrupted states. With bounded refs, 8192 executed normally.

### Critical warning

Those ~1.1M decisions/s figures used a runtime around 29.5 KB/env.

Current public-event runtime is ~62.3 KB/env.

**Do not quote 1.125M/s as current training throughput. Rebenchmark the accepted log-enabled engine.**

---

# Immediate next task — do this before training planning

The accepted engine is now mechanically broad enough that the remaining work should focus on **whole-system qualification**, not another large opcode port.

## Gate 1 — verify current accepted public-event runtime

Inspect the tests/evidence that supported `2ea2d3a`/`74b322e` and add any missing native comparisons.

Required coverage:

- setup event order;
- shuffle/draw/open/reverse semantics;
- play/move distinction without double logging;
- attach/evolve/devolve/transform;
- damage/heal including zero-damage/public cases;
- statuses and recovery;
- coin ownership/order;
- attack/turn/result ordering;
- LookAndReturn synthetic movement logs;
- independent per-player consumption;
- acknowledgment/compaction;
- terminal no-selection projection;
- **>200-event burst preservation**;
- near-capacity behavior / fail-closed overflow.

Do not re-open implementation that already passes unless a native difference is found.

Commit any accepted fix separately from the root.

## Gate 2 — true GPU-only full games

Run real decks from:

```text
reset -> setup/mulligan -> Main/turns -> terminal
```

through `GpuCabtRuntime`.

Consume/project policy state and public events at every policy boundary.

Use multiple deck families and both seats.

The agent for the qualification can be a deterministic legal policy; the point here is engine reachability/reliability, not strength.

Require zero:

- invalid selections;
- unsupported transitions;
- option/target/zone overflow;
- trigger/KO/history/log overflow;
- interpreter-limit error;
- stale selection;
- CPU simulator fallback.

Do not call a post-setup loop or one-turn loop a full-game test.

## Gate 3 — native CPU vs GPU parity/invariants

Native CABT system RNG means whole stochastic trajectories are not pairable by Python seed.

Use:

- deterministic synthetic state fixtures;
- controlled coin/effect fixtures;
- exact selection snapshots;
- native/GPU public state/event comparisons at deterministic boundaries;
- replay/captured-state differentials where stochastic realization is already known;
- broad full-game invariants/statistics rather than fake paired-seed claims.

## Gate 4 — 4 GB stress

With current 62.3 KB runtime, re-sweep realistic env counts.

Record:

```text
env count
stack size
GPU VRAM
steps/decisions per second
games per second
policy projection throughput
public event throughput
p50/p95/p99 step time
runtime error counters
```

Do not optimize only for maximum environment count. Find the throughput optimum.

## Gate 5 — final local benchmark

The user explicitly requested **one final local benchmark after the GPU port is complete**.

At minimum compare:

```text
native CPU complete-game/decision throughput
GPU CABT complete-game/decision throughput
GPU CABT + policy projection + public events
GPU CABT + recurrent policy inference, if readily wired
memory / stack / batch optimum
zero-error counters
speedup ratios
```

This benchmark is the trigger for training planning.

---

# Training plan after those gates pass

Do **not** launch main training before the gates above.

## Phase A — recurrent BC initialization

Primary exact-deck teacher data:

- Luca current exact-Lucarion shell replay corpus;
- Majkel exact-deck replay corpus;
- optionally older qualified auxiliary exact-deck data if it improves held-out/native initialization.

Replay alignment must be revalidated. Current known visualizer convention is approximately:

```text
observation(t) -> action(t+1)
```

Split by whole episode.

BC is initialization. Immediately evaluate native competence.

## Phase B — GPU self-play PPO

Start from existing G2/G3 recurrent architecture unless measured evidence justifies a change.

Default PPO contract:

```text
terminal reward +1 / 0 / -1
public actor
public critic
complete legal option scoring
ordered without-replacement multi-select
separate recurrent state per env/player/policy
SELF_ROLLOUT-only PPO buffers
both seats
rule/BC/frozen checkpoint anchors
snapshot/PFSP-style opponent mixture
```

Do not use replay actions as PPO rollout data.

The user is open to a larger model, but profile first. Existing model ~970k parameters may be enough when properly trained.

## Phase C — league robustness

Training/evaluation opponent population should cover multiple families, not one mirror:

- Mega Lucario mirrors;
- current Dragapult families;
- Alakazam;
- Lopunny/Froslass;
- Grim/Dawn historical generalists;
- Iono/Abomasnow/stock rule families;
- faithful current Ogerpon/Hydrapple or other top deck family if available;
- frozen learned checkpoints;
- designated final holdout kept isolated.

No named-opponent routing.

## Phase D — optional tactical/SA layer only after competence

After a strong learned policy exists, consider:

- high-confidence exact lookup;
- tactical exact-search proof override;
- SA optimization of arbitration/confidence/search/curriculum parameters.

Do not add complexity before the learned controller demonstrates competence.

---

# Strict lane architecture

Maintain at least these four lanes:

## Lane 1 — engine/performance correctness

GPU CABT parity, events, reliability, memory, Torch integration, speed.

No strength claims from this lane.

## Lane 2 — primary learned Lucario controller

BC -> PPO -> league -> native promotion.

## Lane 3 — genuinely independent strategic/controller basin

Only if evidence justifies it. A tiny parameter fork does not count.

## Lane 4 — live-meta / replay / holdout intelligence

Fresh public replays, failure taxonomy, curriculum/evaluation, new top archetypes.

No hidden knowledge or named-opponent policy routing.

Each experimental lane must have:

- explicit hypothesis;
- control;
- bounded budget;
- kill criterion;
- independent holdout.

---

# Promotion requirements

Read:

```text
ptcg-rl/.chatgpt/KPTCG_PROMOTION_CRITERIA.local.md
```

Hard current target:

```text
>95% overall native win rate
broad diverse deck families
both seats
zero reliability defects
holdout confirmation
no opponent identity / hidden deck routing
```

A small screen, a simulator-only score or imitation accuracy is not promotion evidence.

Report per-family cells so an aggregate cannot hide a catastrophic matchup.

Final candidate still needs official/native CABT evaluation and package/runtime qualification.

---

# Replay/data rules

- index manifest -> daily manifest -> explicitly chosen episode files;
- never pull a whole daily replay dataset just because it is available;
- enforce byte/file/free-space caps;
- public replay population is elite/rating/availability biased;
- raw replay bodies remain ignored/private;
- do not feed hidden visualizer state to actor/critic;
- compare semantic action meaning where duplicate physical options exist;
- validate temporal alignment for every new replay schema/family;
- PPO buffers accept `SELF_ROLLOUT` only.

Relevant retained paths:

```text
ptcg-rl/scratch/elite-distill-2026-08-13/luca-55447414/
ptcg-rl/scratch/elite-distill-2026-08-13/replays/
ptcg-rl/.chatgpt/tmp/majkel-history/
ptcg-rl/scratch/anneal-lucario-2026-08-13/
```

---

# Current Kaggle/live snapshot — historical only, requery before using

A fresh leaderboard query during handoff showed:

```text
1  LiamK                 1249.4
2  flg                   1212.8
3  palsystem             1207.9
4  Luca                  1191.6
5  ANDPAD                1173.3
6  Thai                  1164.7
7  Sixth Sense           1158.2
8  Rmy                   1153.5
9  AlphaTCG              1144.3
10 LumenLiquidity        1135.8
```

Fresh NNMax public-safe active submissions at that snapshot:

```text
55465516   764.2
55468166   694.8
```

Historical `55454433` raw Dawn once showed 858.3 but is not the current active pair.

Simulation scores move. Refresh before discussing current placement or deciding a submission.

Do not submit anything merely to “try it” while the learned lane is not promoted.

---

# Online compute after local qualification

Do not choose cloud hardware from GPU marketing specs alone.

After the final local benchmark, profile where time goes:

```text
environment step
public projection/events
policy recurrent inference
rollout packing
PPO learner forward/backward
checkpoint/evaluation
```

Then choose Kaggle/A100/H100/L40S/etc. from the measured bottleneck.

Known prior constraint:

- Kaggle H100 access was restricted to AIMO3, not KPTCG. Do not use it for this competition unless current official policy explicitly changed.

Paid/external compute requires explicit user authorization.

A single H100 may become valuable now that environment simulation is GPU-resident, but measure rather than assume.

---

# Kaggle notebook/input rules

Read:

```text
ptcg-rl/.chatgpt/KAGGLE_DATASET_RUNTIME_RULES.local.md
```

Key points:

- Kaggle auto-extracts ZIP;
- Kaggle auto-decompresses `.gz`;
- mounted input filenames/tree are source of truth;
- do not build unnecessary archive/hash transport machinery into research notebooks;
- user generally wants the assistant to prepare/update stable notebook/dataset/model inputs and the user to manually launch heavy notebooks;
- keep dataset/model versions tidy instead of creating noisy one-offs.

No benchmark-task creation unless the user explicitly asks for a benchmark task.

---

# Codex restriction

If you delegate repository code generation to Codex, use **only**:

```text
gpt-5.6-luna-xhigh
```

The local Codex account previously returned a hard 400 saying that exact model was unsupported.

Therefore:

- do not substitute a different Codex model;
- continue directly if unavailable;
- retry Codex only if the exact permitted model later becomes supported.

---

# Git rules — strict

The user explicitly requires **all accepted incremental changes committed**.

For every accepted gate/fix:

1. validate narrow change;
2. review exact root diff;
3. stage exact paths only;
4. commit from repo id `ptcg` / root;
5. verify commit path list;
6. continue.

Never:

- `git add .`;
- mass-stage unrelated work;
- reset/clean/stash active source;
- commit raw private competition assets;
- push without explicit user instruction.

Rejected experiments stay in ignored scratch.

---

# Files that matter immediately

GPU runtime:

```text
ptcg-rl/src/ptcg_rl/gpu_cabt/native/state_core.h
ptcg-rl/src/ptcg_rl/gpu_cabt/native/state_fields.h
ptcg-rl/src/ptcg_rl/gpu_cabt/native/runtime_state.h
ptcg-rl/src/ptcg_rl/gpu_cabt/native/rule_static.h
ptcg-rl/src/ptcg_rl/gpu_cabt/cuda/setup_runtime.cu
ptcg-rl/src/ptcg_rl/gpu_cabt/cuda/game_runtime.cu
ptcg-rl/src/ptcg_rl/gpu_cabt/cuda/policy_projection.cu
ptcg-rl/src/ptcg_rl/gpu_cabt/cuda/public_log_core.cu
ptcg-rl/src/ptcg_rl/gpu_cabt/cuda/public_log_emit.cu
ptcg-rl/src/ptcg_rl/gpu_cabt/cuda/public_log_project.cu
ptcg-rl/src/ptcg_rl/gpu_cabt/cuda/runtime_api.cu
ptcg-rl/src/ptcg_rl/gpu_cabt/source.py
ptcg-rl/src/ptcg_rl/gpu_cabt/device_runtime.py
ptcg-rl/src/ptcg_rl/gpu_cabt/nvrtc.py
ptcg-rl/src/ptcg_rl/gpu_cabt/rule_static.py
ptcg-rl/scripts/gpu_cabt_rule_extract.cpp
```

Training:

```text
ptcg-rl/src/ptcg_rl/g2/network.py
ptcg-rl/src/ptcg_rl/g3/ppo.py
ptcg-rl/src/ptcg_rl/g3/checkpoint.py
ptcg-rl/src/ptcg_rl/g3/cloud_runner.py
ptcg-rl/reports/evaluations/e04-qualification-v1.json
ptcg-rl/reports/artifacts/g3b-competence-plan-v1.json
```

Current deck/evidence:

```text
ptcg-rl/.chatgpt/tmp/today-lucario-variants/lucario-modern-v1/
ptcg-rl/scratch/elite-distill-2026-08-13/
ptcg-rl/.chatgpt/tmp/majkel-history/
ptcg-rl/.chatgpt/tmp/current-engine-v1/
ptcg-rl/.chatgpt/tmp/eod-h2h-v1/agents/dawn-raw/
```

Do not delete them during continuation.

---

# Definition of done for the current GPU phase

Do not say “GPU port complete” until all are true:

```text
[ ] reset/setup/mulligan/prizes/bench all device-native
[ ] all legal selection classes device-resumable
[ ] Main/actions device-native
[ ] attack/effects/triggers/KO/Refresh/checkup/turn cycle device-native
[ ] terminal/result device-native
[ ] persistent device RNG
[ ] public state projection parity
[ ] public consumptive event/log parity
[ ] Torch/DLPack device runtime usable without CPU game loop
[ ] real reset-to-terminal multi-deck games zero-error
[ ] native-vs-GPU deterministic/invariant suite passes
[ ] >200 public-event burst preserved
[ ] 4 GB stress passes
[ ] final realistic local CPU-vs-GPU benchmark recorded
[ ] accepted incremental fixes committed from root
```

After that, stop engine work and prepare the exact accelerated training campaign.

---

# Desired outcome of the next session

Do not merely provide a status update.

The next session should, unless blocked by a genuine tool/hardware failure:

1. verify the accepted public-event/runtime commits and current tests;
2. complete any missing native event parity/burst tests;
3. run true real-deck GPU games from reset to terminal with public projections/events;
4. fix any semantic/reliability defects and commit each accepted increment;
5. run broad both-seat/multi-deck local stress on the 4 GB RTX 3050;
6. run the **final local CPU-vs-GPU benchmark** with the current log-enabled runtime;
7. leave the GPU engine demonstrably training-ready;
8. then produce a concrete BC + GPU self-play PPO + league plan with hardware choice based on measured bottlenecks.

The first priority is **finishing the GPU runtime without compromises**. Training planning begins only after that gate.
