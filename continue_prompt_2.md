# Continue KPTCG GPU-CABT / Gold-Path Work — copy/paste into a new ChatGPT session

Continue the KPTCG Kaggle Pokémon TCG AI Battle project from the **current repository state and this handoff**, not from assumptions and not from the older root `continue_prompt.md` alone.

The older `continue_prompt.md` is a useful historical Dawn-era handoff, but it is now materially stale. **This `continue_prompt_2.md` supersedes it for the current GPU-CABT / Lucario / training-preparation track.**

## Repository roots and access

Use Local MCP with both approved repository roots:

- `ptcg` = `/home/nnmax/Desktop/kaggle/PTCG` — actual Git top-level / canonical repository root.
- `ptcg-rl` = `/home/nnmax/Desktop/kaggle/PTCG/ptcg-rl` — main source, tests, GPU-CABT code, reports and scratch experiments.

The Git top-level is `/home/nnmax/Desktop/kaggle/PTCG`.

Do not assume the worktree is clean. Read it first.

## Mandatory first actions

Before editing anything:

1. Read this file fully.
2. Read root `RULES.md` and root `AGENTS.md` using repo id `ptcg`.
3. Read `ptcg-rl/AGENTS.md`.
4. Read `ptcg-rl/src/ptcg_rl/gpu_cabt/README.md`.
5. Inspect the current GPU-CABT source tree under `ptcg-rl/src/ptcg_rl/gpu_cabt/`.
6. Read the latest accepted GPU files and the current uncommitted GPU files listed below.
7. Run read-only Git state checks:

```bash
git status --short -uall
git log --oneline --decorate -25
git branch -vv
git remote -v
```

Do **not** reset, clean, stash, checkout away, or mass-stage the worktree.

At handoff, current accepted HEAD is:

```text
dc758e2 gpu-cabt: add public policy projection
```

`origin/main` is still at:

```text
cc9becc preserve accumulated KPTCG gold-path evidence
```

Do not push unless the user explicitly asks.

The user requires **every accepted incremental project change to be committed locally**. Use narrow exact-path commits. Rejected or incomplete experiments must remain uncommitted.

## Mission right now

The immediate mission is **not PPO yet**.

The user explicitly said:

- complete the full GPU port as fast as possible;
- do not make compromises;
- no CPU gameplay fallback;
- fully utilize GPU execution so later self-play/PPO can be much faster;
- use the local GPU for all qualification first;
- local GPU is an RTX 3050 Laptop GPU with only **4 GB VRAM**;
- only after all local correctness/reliability/performance tests pass should online training be planned/launched;
- after the port is complete, run **one final local CPU-vs-GPU benchmark**;
- then discuss/plan online PPO/training.

Do not start online PPO or paid cloud training before the GPU engine is locally qualified end-to-end.

## Codex constraint

If using a Codex agent for code generation, the user explicitly requires **`gpt-5.6-luna-xhigh` only**.

That model was tested through the local Codex CLI during this project and the account returned a hard unsupported-model error. Therefore:

- do not silently substitute another Codex model;
- if `gpt-5.6-luna-xhigh` remains unavailable, do the work directly without Codex.

## Strategic game-strength context

Dawn is no longer the optimization center. Current/live evidence established that the **Mega Lucario deck itself is gold-capable** and the bottleneck is controller quality.

Historical live evidence captured during this project:

- Luca reached roughly **1222 Elo** with the exact Mega Lucario 60-card list below.
- Majkel1337 reached roughly **1173 Elo** with the exact same 60-card list.
- NNMax's then-active submissions had fallen below 800 Elo.

Exact gold-proven Mega Lucario deck:

- 13 Fighting Energy — card 6
- 4 Mega Lucario ex — 678
- 4 Ultra Ball — 1121
- 4 Premium Power Pro — 1141
- 4 Fighting Gong — 1142
- 4 Poké Pad — 1152
- 4 Judge — 1213
- 4 Lillie — 1227
- 3 Solrock — 676
- 3 Riolu — 677
- 2 Makuhita — 673
- 2 Hariyama — 674
- 2 Lunatone — 675
- 2 Switch — 1123
- 2 Boss's Orders — 1182
- 2 Wally — 1229
- 1 Hero's Cape — 1159

The same deck is available locally around:

`ptcg-rl/.chatgpt/tmp/today-lucario-variants/lucario-modern-v1`

The strategic conclusion is: **fixed gold-proven deck + much stronger learned/self-play controller**, not more Dawn micro-heuristics or random deck mutation.

Refresh live Kaggle truth before any future submission/training decision because leaderboard values above are historical snapshots.

## Why the GPU port exists

Multiple imitation/controller approaches converged too low:

- current hand-written Lucario MAIN policy: ~44% semantic agreement with Luca on strategic MAIN decisions;
- tree/ranker methods: ~57–58%;
- case-based retrieval / SA: ~56%;
- focused true GRU: ~56%;
- pairwise priority model: ~53%;
- old history model had higher offline fidelity but failed native confirmation.

A production-scale recurrent BC/PPO competence run was never genuinely completed.

The user changed direction explicitly: build a high-throughput exact GPU simulator so we can perform much larger self-play/BC/PPO experiments instead of being bottlenecked by CPU CABT simulation.

## GPU-CABT accepted architecture and major facts

The GPU engine is an **exact-rule port**, not an approximate simulator.

Static flattened rule graph extracted at runtime from the official local competition engine:

- 1,267 cards
- 433 skills
- 1,556 attacks
- 3,067 effects
- 77 triggers
- 1,011 target conditions
- total rule graph around 0.65 MB after corrected EnergyType widths

Official card/rule rows must never be committed. Only schemas/extractors/interpreter code are committed.

Core architecture:

```text
GPU-resident BattleCoreState[]
GPU-resident BattleRuntimeState[]
GPU-resident flattened rule tables
        ↓
batched CUDA dispatcher
        ↓
advance each environment until a real policy decision or terminal state
        ↓
GPU public-policy projection
        ↓
future batched recurrent policy / PPO learner
```

No host/CPU gameplay state machine should be inserted between decisions.

### Major accepted semantic surfaces

The accepted port now includes:

- setup primitives and setup selection semantics;
- TurnStart packed-state rollover;
- all dynamic native State lists represented with bounded fixed-capacity GPU buffers;
- exact packed Card/Player/State bitfield ABI;
- full rule-table transport;
- all **102 TargetType** cases;
- all **24 ConditionType** cases;
- all **74 continual effects** (`171..244`);
- all **171 instant effect enum values** (`0..170`) represented/handled;
- generic EffectProc pause/resume state machine;
- trigger collection, ordering and activation;
- KO / prize / Lucky Bonus processing;
- state-based Refresh stabilization;
- Pokémon Checkup and special conditions;
- persistent TurnEnd → Checkup → TurnStart cycle;
- exact Main legal action generation;
- Main action execution/resume including retreat;
- complete attack frame including normal damage, pre/post effects, copied attacks, confusion, coin gates, trigger draining, double attack and exotic attack-source branches;
- unified game runtime/reset dispatcher;
- public policy projection for learned policies.

Important source locations:

- `ptcg-rl/src/ptcg_rl/gpu_cabt/native/state_core.h`
- `ptcg-rl/src/ptcg_rl/gpu_cabt/native/state_fields.h`
- `ptcg-rl/src/ptcg_rl/gpu_cabt/native/runtime_state.h`
- `ptcg-rl/src/ptcg_rl/gpu_cabt/native/rule_static.h`
- `ptcg-rl/src/ptcg_rl/gpu_cabt/cuda/`
- `ptcg-rl/src/ptcg_rl/gpu_cabt/nvrtc.py`
- `ptcg-rl/src/ptcg_rl/gpu_cabt/rule_static.py`
- `ptcg-rl/scripts/gpu_cabt_rule_extract.cpp`

## Important accepted commit chain

Recent accepted local commits, newest first at handoff:

```text
dc758e2 gpu-cabt: add public policy projection
ba3bf46 gpu-cabt: add unified game runtime
810641a gpu-cabt: derive rule table sizes
cc9becc preserve accumulated KPTCG gold-path evidence
336d1f9 chore: ignore local KPTCG scratch state
9c3a6eb gpu-cabt: execute attacks on device
0552b88 gpu-cabt: execute Main actions on device
b748775 gpu-cabt: generate exact Main actions
9a5f544 gpu-cabt: add persistent turn cycle
a374a18 gpu-cabt: resolve Pokemon Checkup conditions
a313ae4 gpu-cabt: add state-based refresh frame
70f4db4 gpu-cabt: load native cubin modules
5b6dc4a gpu-cabt: add KO and prize state machine
ad09046 gpu-cabt: resolve triggered abilities
eea0517 gpu-cabt: add full effect interpreter substrate
d1408cd gpu-cabt: port generic continual refresh engine
850c8ea gpu-cabt: preserve full energy type widths
3577f7f gpu-cabt: qualify packed native state fields
a38201b gpu-cabt: port turn start state rollover
041eb64 gpu-cabt: model full native runtime lists
6b56980 gpu-cabt: transport full static rule graph
ac13d0a ... paired setup-bench composition accepted earlier
```

Do not squash or rewrite these commits.

## Important correctness evidence already obtained

Do not redo these from scratch unless a later shared-ABI change requires regression qualification.

Examples of accepted gates:

- setup option construction: **600/600 exact**;
- selected-card stable target capture: **256/256 exact**;
- selected setup Hand→Bench movement: **256/256 exact**;
- paired setup Bench composition: exact pre-TurnStart boundary;
- TurnStart rollover: **256/256 exact** with nonzero packed-state sentinels;
- full flattened rule transport: byte-identical GPU checksum;
- packed state-field ABI: native GCC and NVRTC raw words bit-identical;
- generic Refresh on Lucario–Dragapult: **5,088/5,088 64-bit state words exact**;
- generic Refresh on Lucario–Alakazam: **5,088/5,088 exact**;
- central effect-selection resume probes passed across card, attached-card, Energy, evolution, damage-counter, branch and break/jump paths;
- trigger simultaneous ordering / depth behavior passed;
- KO matrix passed for Mega-ex 3-prize, simultaneous KO ordering, PreKO-before-movement and nested Lucky Bonus;
- state-based Refresh integration passed bench overflow, tool overflow, KO→Active replacement, terminal prize win and Checkup KO skip;
- Pokémon Checkup pseudo-trigger/status test passed;
- turn-cycle edge gates passed deck-out, Checkup KO replacement and TurnEnd triggers;
- Main legal action surface and restriction surface passed;
- Main mutation/resume passed eight action classes including two-step retreat;
- attack frame passed normal, pre/post, copied, confusion, damage-trigger, double attack and exotic copied/deck-top branches.

Treat any later ABI/shared-helper edit as requiring the relevant regression subset again.

## CUDA compile/runtime engineering facts

The large combined CUDA interpreter originally caused NVRTC/driver-JIT stalls because heavyweight interpreter functions were force-inlined.

Accepted fixes:

- heavyweight interpreter functions use non-forced/no-inline where needed;
- direct native CUBIN loading is supported;
- development qualification can use NVRTC `--Ofast-compile=max`;
- production should compile the optimized native CUBIN once and cache/reuse it.

Fast qualification compile dropped from >60–180 seconds to low single-digit seconds for the large translation unit.

CUDA device-stack probing:

- 4 KiB passed the central activation path;
- 8 KiB and 16 KiB passed;
- working runtime safety margin was intentionally kept at **16 KiB** while deeper frames were being added.

Recheck this after the current public-log/runtime expansion.

## Local RTX 3050 throughput evidence

The first meaningful batched post-setup dispatcher benchmark is already very encouraging.

The benchmark is GPU-resident between decisions and repeatedly selects the synthetic attack/Main path; host copies occur only outside the timed loop.

Measured on the local 4 GB RTX 3050 Laptop GPU with zero runtime errors:

```text
64 envs      ~27,202 decisions/s
128          ~50,976 decisions/s
256          ~99,184 decisions/s
512         ~187,093 decisions/s
1,024       ~453,499 decisions/s
1,536       ~652,050 decisions/s
2,048       ~825,455 decisions/s   (first sweep)

second larger sweep:
2,048       ~669,847 decisions/s
3,072       ~862,830 decisions/s
4,096     ~1,003,140 decisions/s
6,144     ~1,124,941 decisions/s   <- best measured local point
8,192     ~1,090,792 decisions/s
```

The old 8,192-env timeout was caused by a corrupt synthetic fixture using card refs beyond the fixed 128-card state capacity, plus expensive CUDA module JIT—not by a fundamental GPU scaling collapse.

Current observed local sweet spot for that synthetic workload is around **6k environments**, but this must be re-benchmarked after the latest public-log/runtime changes and on real whole-game workloads.

Do not convert the synthetic ~1.12M decisions/s into a claimed whole-game speedup yet. The final benchmark must use complete reset/setup/gameplay/terminal execution and a realistic policy-action workload.

## Current accepted unified runtime

Commit `ba3bf46` added:

- `gpu_cabt_game_reset`
- `gpu_cabt_post_setup_begin`
- `gpu_cabt_game_step`
- unified setup/runtime state machine

Commit `dc758e2` added the public policy projection (`policy_projection.cu`) so future learned policies do not need raw private engine state.

The setup state machine was designed from official `SetupProc.h`, including the non-obvious rules:

- first-player selection;
- opening draw;
- Basic/Doll/mulligan handling;
- simultaneous no-Basic rerolls;
- mulligan compensation draw-count selection;
- Active selection;
- Prize setup timing;
- Bench setup;
- setup reveal/move-counter normalization;
- handoff to TurnStart/Main.

One source audit correction to preserve: there is **no TurnStart TriggerType** in native CABT. The official TriggerType enum begins `None, TurnEnd, PokemonCheckup, ...`. Do not invent a TurnStart trigger pass.

## CURRENT UNCOMMITTED WORK — DO NOT DISCARD

At this handoff the worktree is intentionally dirty again after the previous cleanup.

Tracked modified GPU files include:

- `cuda/attach_full.cu`
- `cuda/attack_frame.cu`
- `cuda/card_move.cu`
- `cuda/card_move_full.cu`
- `cuda/coin_runtime.cu`
- `cuda/damage_heal.cu`
- `cuda/effect_instant_0_29.cu`
- `cuda/effect_instant_56_71.cu`
- `cuda/effect_instant_96_110.cu`
- `cuda/effect_resume.cu`
- `cuda/evolution_full.cu`
- `cuda/main_action.cu`
- `cuda/main_select.cu`
- `cuda/refresh_effect.cu`
- `cuda/rule_runtime_helpers.cu`
- `cuda/setup_runtime.cu`
- `cuda/special_condition_checkup.cu`
- `cuda/state_based_refresh.cu`
- `cuda/turn_cycle.cu`
- `native/runtime_state.h`

Untracked current GPU files include:

- `cuda/public_log_core.cu`
- `cuda/public_log_emit.cu`
- `cuda/runtime_api.cu`
- `device_runtime.py`
- `source.py`

These are an active **public-log / runtime API / Python device-runtime integration** slice. Do not restore/delete them merely because HEAD is cleaner.

### Known issues in this uncommitted slice that must be fixed before acceptance

There are concrete inconsistencies visible at handoff:

1. `runtime_api.cu::gpu_cabt_runtime_info` currently writes **14 integers** (`out[0]..out[13]`), while `device_runtime.py::_read_abi()` allocates only `cp.empty(12)` and `RuntimeAbi` currently has 12 fields. Running that as-is risks an out-of-bounds device write. Fix the ABI contract before executing this path.

2. `source.py` currently lists `public_log_project.cu` in `CUDA_RUNTIME_MODULES`, but that file was not present in Git status / current source set at handoff. Reconcile the canonical module list and either implement the missing projection or remove the stale reference based on intended architecture.

3. `device_runtime.py` has its own `_CUDA_MODULES`/`build_cuda_source()` list that does not yet match `source.py` and does not include the new public-log core/emit modules. Consolidate to one canonical source builder instead of maintaining divergent lists.

4. Public logging adds a fixed `kPublicLogCapacity = 1024` with 32-byte `PublicLogState` entries, i.e. ~32 KiB additional per environment. This materially changes per-env memory/bandwidth and therefore the previously measured 6k-env throughput sweet spot. Re-measure VRAM and throughput after correctness is restored.

5. The public-log ring/compaction must preserve **actor-relative public observation semantics** without leaking hidden opponent hand/deck/prize information. The future policy projection must only expose information the real CABT agent receives.

Do not commit this slice until compile + native/public-observation differential + runtime stress passes.

## Public policy projection requirements

The learned policy must consume an actor-relative public state equivalent to CABT observations, not privileged simulator internals.

The projection should preserve:

- acting-player orientation;
- own visible hand/resources;
- public board/attachments/status/damage;
- deck/hand/prize counts where public;
- opponent hidden information masked;
- exact legal options and their public parameters;
- public logs/history necessary to recover sequential context;
- terminal/status information;
- stable DLPack/CUDA tensors for zero-copy Torch integration where possible.

Never train or submit a controller using opponent identity, hidden deck order, hidden hand/card IDs, hidden prize identities, or other private simulator state.

## Immediate next tasks

Continue from the active public-log/runtime slice, not from another redesign.

### 1. Repair and qualify the canonical GPU runtime build

- fix the 14-vs-12 runtime ABI mismatch;
- eliminate duplicated/divergent CUDA source lists;
- resolve `public_log_project.cu` reference;
- compile the complete runtime + policy projection with fast qualification CUBIN;
- verify state/runtime sizes and VRAM budget on RTX 3050 4 GB;
- retain 16 KiB device stack unless a deeper measured requirement changes it.

### 2. Qualify public logs / observation equivalence

Use native CABT replays or synthetic native states to compare the projected public observation/log stream at real decision boundaries.

Must cover at least:

- reset / IsFirst;
- opening draw;
- mulligans including simultaneous mulligan and compensation draw;
- Active/Bench setup;
- draw / play / attach / evolve / switch;
- damage / heal / status / coin;
- attack;
- KO / prize / Lucky Bonus;
- TurnEnd / Checkup / next TurnStart;
- terminal result.

Hidden information must remain masked.

### 3. End-to-end GPU-only games

Run complete environments from:

```text
reset → shuffle → setup → Main decisions → attacks/effects/triggers/KO/checkup → terminal
```

No CPU gameplay mutations between decisions.

Use real 60-card decks, starting with the gold-proven Mega Lucario deck against several independent families (Dragapult, Alakazam, Lopunny, Grim, Iono/Abomasnow/other retained anchors as available).

Initially use deterministic/simple legal-action policies only to qualify mechanics, not to judge strength.

Require:

- zero runtime error flags;
- zero invalid selections;
- zero interpreter/stack/overflow failures;
- terminal completion;
- both seats;
- broad rule-path coverage.

### 4. Whole-game native differential

Because native CABT shuffle RNG is system-entropy/unseeded, full games cannot generally be causally paired by Python seed. Use deterministic current-turn/state fixtures and public replay alignment where exact pairing is possible, and broad invariant/reliability comparison where RNG prevents exact causal pairing.

Do not fake deterministic equivalence where native RNG does not permit it.

### 5. Final local performance qualification

After correctness is complete:

- sweep realistic env counts under the new larger runtime;
- measure decisions/s, completed games/s, GPU utilization, VRAM, stack use and error rate;
- benchmark complete reset/setup/gameplay rather than only post-setup synthetic attacks;
- run a sustained reliability test (thousands of environments, many decisions/games);
- compare to the existing native CPU CABT throughput using the same workload definition.

This is the **one final local benchmark** the user requested before training planning.

Only after this is green should the conversation move to BC/PPO architecture and online compute.

## Likely training direction after GPU completion — do not launch yet

The probable next strategy is:

1. recurrent BC initialization using current exact-deck Luca + Majkel teacher episodes;
2. native/GPU competence gate;
3. bounded recurrent PPO/self-play with snapshot/opponent league;
4. terminal win/loss objective plus KL / auxiliary BC regularization;
5. evaluate every bounded checkpoint rather than blindly train millions of choices;
6. optionally use C++ simulated annealing later for higher-level arbitration/gating parameters, not shallow raw action weights.

Existing G2/G3 infrastructure is under `ptcg-rl/src/ptcg_rl/g2/` and `g3/`.

The prior G2 recurrent semantic policy is roughly 970k parameters. The user is open to a larger model if the GPU simulator throughput makes full self-play feasible.

Do not promise gold/Elo guarantees. Same-deck 1200+ live evidence proves the deck/controller combination can be elite, not that our future learner will automatically reach it.

## Compute facts for later discussion

Historical CPU/native evidence from project reports showed roughly 228 meaningful choices/s for the old native stack in one measured setup, with much lower conservative planning floors. The new GPU synthetic dispatcher has already reached >1M decision boundaries/s locally, but these are not directly apples-to-apples until the final whole-game benchmark.

Kaggle H100 availability was checked during this project: Kaggle's H100 machines were restricted to the AIMO3 competition, so do not plan to use Kaggle H100 for KPTCG unless current official rules later change.

External H100/A100/L40S can be considered after local qualification. Never launch paid cloud compute without explicit user authorization.

The main future scaling architecture should remain:

```text
thousands of GPU-resident CABT envs
        ↓
public projection tensors on GPU
        ↓
batched recurrent policy inference
        ↓
selected legal actions on GPU
        ↓
GPU CABT step
        ↓
rollout buffer / PPO learner on GPU
```

Avoid host round trips for every decision.

## Git / repository rules

- Commit every **accepted** incremental change locally.
- Do not commit failed/rejected scratch experiments simply because they exist.
- Use exact intended paths; never `git add -A` over the dirty project.
- Never reset, clean, stash or checkout away unrelated work.
- Never push unless explicitly requested.
- Do not commit official engine/card data, raw protected competition assets, generated submission archives or generated card tables embedding official data.
- Runtime-extracted flattened rule blobs stay ephemeral.
- Local scratch/corpora are intentionally ignored after commit `336d1f9`; do not delete them just to make status smaller.

## Kaggle / submission rules

Do not submit anything during the GPU-port qualification phase.

Before a future submission:

- refresh current leaderboard/submission state;
- verify quota/eligibility;
- package cold from scratch;
- validate both seats;
- confirm exact 60-card deck;
- ensure no hidden-information routing;
- preserve rollback artifact and archive identity.

## What “GPU port complete” means

Do not call the port complete merely because CUDA compiles.

It is complete only when all of these are true:

1. reset/setup/gameplay/terminal progression is GPU-native;
2. all reachable current-engine rules/effects are handled or intentionally fail closed with proof they are unreachable;
3. policy decisions can be supplied in batch without host gameplay mutation;
4. public observation/policy projection matches CABT information boundaries;
5. no hidden information leaks to the future learner;
6. real complete games terminate across broad decks and both seats;
7. sustained large-batch reliability has zero runtime/overflow/invalid-selection defects;
8. the local 4 GB GPU memory/stack constraints are respected;
9. final whole-game CPU-vs-GPU throughput benchmark is recorded;
10. every accepted increment is committed locally.

Then stop porting and move to training planning with the user.

## Resume point in one sentence

**Start by fixing and qualifying the current uncommitted public-log/runtime-API/device-runtime slice on top of accepted HEAD `dc758e2`, preserve all current dirty GPU files, then complete end-to-end public-observation-equivalent GPU games and the final local benchmark before discussing PPO.**
