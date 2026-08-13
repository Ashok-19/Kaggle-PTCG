# KPTCG Rules — GPU-First Gold Path

Last authoritative update: **2026-08-14**

These rules are the durable operating contract for the KPTCG project. They apply to the entire repository unless a more specific file adds a stricter constraint. Direct user instructions in the active conversation take precedence.

The mission is to maximize the probability of a **Kaggle gold/top-10 finish** in the Pokémon TCG AI Battle competition without pretending any result is guaranteed.

The immediate project priority is:

> **Finish and qualify the complete GPU CABT runtime, then use it for fast recurrent BC initialization and full self-play PPO/league training.**

Dawn heuristic polishing is no longer the primary optimization center.

---

## 1. Source of truth

Resolve contradictions in this order:

1. current official Kaggle competition rules, official CABT engine/card data/runtime behavior;
2. direct user decisions in the active conversation;
3. this `RULES.md`;
4. current canonical handoff `.chatgpt/handoffs/KPTCG_GPU_TRAINING_MASTER_PROMPT.local.md` and current dated handoff;
5. accepted source/tests/commits and retained raw evidence;
6. current project reports/decision records;
7. old narrative handoffs, old leaderboard snapshots, public notebooks, intuition.

Never use a report saying `PASS` as proof when its underlying evidence is absent or contradicted by newer repository state.

At the beginning of a new session, verify actual Git state and any mutable Kaggle facts before acting.

---

## 2. Repository and Git discipline

Canonical Git root:

`/home/nnmax/Desktop/kaggle/PTCG`

Code subtree:

`/home/nnmax/Desktop/kaggle/PTCG/ptcg-rl`

Local MCP routing:

- use repo id `ptcg` for root Git operations, root documentation and handoffs;
- use repo id `ptcg-rl` for source/tests/reports/scratch inspection and validation.

### Mandatory Git rules

- **All commits are made from the canonical root repository**, never as a separate/nested repository operation inside `ptcg-rl`.
- Every accepted incremental change gets a **small, narrow local commit**.
- Review exact intended paths before staging.
- Never mass-stage the whole repository.
- Rejected/scratch experiments stay uncommitted.
- Preserve unrelated user work.
- Do not reset, clean, stash, restore or delete active work merely to obtain a clean status.
- Never push unless the user explicitly asks.
- Never claim a push succeeded without checking the remote.

Do not commit official engine/card data, native competition libraries, raw replays, checkpoints, generated submission archives, credentials, signed URLs or private Pokémon-derived assets.

Local handoffs matching `.chatgpt/handoffs/*.local.md` are normally local evidence and should remain untracked unless deliberately changed by project policy.

---

## 3. Current strategic facts

### 3.1 Dawn is historical fallback/evidence, not the main research lane

Raw Dawn once reached a historical live score of 858.3 and remains useful as a rollback/reference opponent. Later Dawn/Search micro-patches repeatedly failed to transfer or overfit small panels.

Do not spend the remaining project time on cosmetic Dawn guard stacking unless new evidence materially changes the strategic picture.

Exact current-turn search remains useful as an **offline tactical proof/oracle** because native long-horizon shuffle RNG is not branch-seedable. It is not general full-game authority.

### 3.2 The exact Mega Lucario deck is already gold-capable

The local deck:

`ptcg-rl/.chatgpt/tmp/today-lucario-variants/lucario-modern-v1`

was verified to match elite public Luca/Majkel 60-card lists. Therefore deck discovery is not the first bottleneck. **Controller quality is.**

Primary learned lane should use this exact deck initially unless later evidence justifies a deliberate deck change.

### 3.3 Existing imitation-only methods are not enough

Do not repeat another shallow LightGBM/CBR/MAIN-GRU classifier simply because it is easy. Existing approaches plateaued around the mid/high-50% imitation range and/or failed native confirmation.

BC is useful as initialization. Final competence is native win strength.

Simulated annealing remains useful for high-level gating/arbitration/curriculum/search/league parameters; shallow raw-action linear SA already failed holdout transfer.

---

## 4. GPU CABT engine non-negotiables

The user explicitly chose a **GPU-resident environment architecture** so self-play training is not bottlenecked by CPU CABT simulation.

### 4.1 No CPU gameplay fallback

For the training hot loop:

`GPU CABT -> GPU public projection/events -> GPU recurrent policy -> GPU action -> GPU CABT`

must remain device-resident.

Do not hide incomplete GPU semantics behind a CPU CABT fallback, Python state machine, CPU log reconstruction or host-side game mutation.

Host orchestration may launch kernels, manage checkpoints or collect bounded diagnostics, but game semantics belong on the GPU runtime.

### 4.2 Official CABT semantics are operational truth

Never simplify a rule just for throughput. Every speed optimization must preserve observed CABT semantics.

The full GPU port includes, at minimum:

- reset/deck initialization;
- shuffle/RNG;
- IsFirst/opening draw;
- mulligan/doll/basic handling;
- prize and bench setup;
- mulligan compensation draw selection;
- TurnStart;
- exact legal-option generation;
- all Main actions;
- attack execution;
- instant and continual effects;
- targeting and conditions;
- triggers and trigger ordering;
- KO/prize/Lucky Bonus;
- state-based Refresh;
- Active replacement;
- Pokémon Checkup;
- turn end/start cycle;
- terminal/result state;
- public policy projection;
- consumptive public event/log projection;
- ordered multi-select response/resume.

Any unsupported reachable transition is a blocker, not a reason to silently approximate.

### 4.3 Fail closed

Fixed-capacity buffers are acceptable only with explicit overflow/error flags. A promotable/training-quality reliability run requires zero:

- invalid selection;
- option/target/zone/continuation overflow;
- trigger/KO/history/log overflow;
- unsupported transition;
- interpreter-limit failure;
- stale or malformed response;
- hidden CPU fallback.

### 4.4 RNG truth

GPU training may use deterministic per-environment Philox streams for reproducible GPU experiments.

Official/native CABT uses nondeterministic system entropy for shuffle. Therefore:

- do not claim Python seeds causally pair complete native games;
- do not claim exact native/GPU whole-game trajectory identity when shuffle randomness differs;
- use exact deterministic fixtures for semantic parity and broad invariant/statistical native comparisons for stochastic full games.

### 4.5 Public-information firewall

The simulator internally owns hidden game state, but actor/critic projections must obey the approved public-information contract.

Never expose:

- opponent hidden hand identities;
- hidden deck order;
- unrevealed prize identities;
- future RNG outcomes;
- named opponent/team/submission identity;
- any private engine field not derivable from the official public observation/log contract.

Own hand and explicitly revealed/looking/deck information may be exposed only when CABT makes it public to the acting player.

### 4.6 Public event/log semantics

The recurrent policy depends on ordered public history. GPU logs must reproduce native consumptive behavior.

Rules:

- preserve exact event order;
- preserve all semantically relevant numeric/public fields;
- each player has an independent read/acknowledgment position;
- compact only after both players have acknowledged prior events;
- never silently truncate a burst;
- a >200-event burst regression is mandatory;
- log overflow is a fail-closed reliability failure;
- terminal/no-selection event projection must have defined safe behavior, not stale actor access.

### 4.7 GPU qualification before online training

The local RTX 3050 Laptop GPU has 4 GB VRAM. Use it for correctness and bounded stress first.

Do not begin online/main PPO until the engine passes:

1. whole-game GPU-only execution from reset to terminal;
2. public policy and event parity tests;
3. broad multi-deck/both-seat zero-error reliability;
4. native/GPU controlled differential/invariant suite;
5. memory/stack/occupancy stress;
6. the user-requested final local CPU-vs-GPU benchmark.

---

## 5. GPU performance rules

Performance claims must state what is included.

Distinguish:

- isolated kernel throughput;
- environment decisions/s;
- complete games/s;
- environment + public projection/events throughput;
- environment + recurrent policy inference throughput;
- PPO actor/learner throughput.

Do not extrapolate a synthetic attack loop directly to training.

Historical pre-public-log synthetic GPU dispatcher measurement on the local RTX 3050 reached roughly 1.125M decisions/s near 6,144 environments, but that used an earlier ~29.5 KB runtime. The public-log runtime grew materially; rebenchmark after current integration.

Record batch size, stack size, source/build mode, VRAM, errors, p50/p95/p99 and exact workload for final claims.

Development may use `GPU_CABT_NVRTC_FAST_COMPILE=max` for fast qualification. Production training should compile an optimized CUBIN once and cache/reuse it.

Do not reserve an unnecessarily huge device stack. The current working safety default is 16 KiB; smaller/larger values require measurement.

---

## 6. Strict lane-based research

Every strength experiment belongs to a lane with a hypothesis, bounded budget, control, kill criterion and holdout.

### Lane 1 — GPU engine / performance correctness

Purpose:

- CABT parity;
- public projection/log correctness;
- reliability;
- memory;
- kernel/runtime throughput;
- Torch/DLPack integration.

No controller-strength conclusion may come from this lane alone.

### Lane 2 — primary learned Mega Lucario controller

Purpose:

- exact-deck elite BC initialization;
- recurrent policy competence;
- self-play PPO;
- snapshot/league training;
- native promotion evaluation.

This is the primary gold path because the deck itself is already proven elite.

### Lane 3 — genuinely different strategic/controller basin

Open this lane only when evidence indicates Lane 2 is stuck or when a different architecture/deck offers a materially different causal advantage.

A cosmetic threshold or tiny Lucario heuristic fork is not an independent lane.

Possible future examples: a faithful different elite deck/controller, materially different recurrent architecture, or a validated tactical-policy hybrid.

### Lane 4 — meta / replay / holdout intelligence

Purpose:

- fresh leaderboard/replay analysis;
- elite failure taxonomy;
- opponent-family coverage;
- curriculum/evaluation design;
- final holdouts.

This lane may inform training but **must never become named-opponent routing or hidden-deck exploitation**.

---

## 7. No single-agent overfitting

Never promote because a candidate dominates one submitted agent, one mirror, one replay stream or one deck.

Required robustness principles:

- both seats;
- multiple independent deck families;
- fresh seeds/independent games;
- training opponents plus frozen checkpoints and rule anchors;
- at least one independent holdout not used to derive the latest change;
- per-family reporting so aggregate strength cannot hide a catastrophic cell.

Preserve the designated Kanga/Slowking-style final holdout until its intended final stage unless the user explicitly changes this rule.

No opponent identity, submission ID, team name, episode ID, hidden exact deck identity or seed-specific routing in production policy.

---

## 8. Learned-controller training rules

### 8.1 BC initialization

BC may initialize the recurrent policy from public replay state/action supervision.

Primary corpus should prioritize exact-deck elite Mega Lucario teachers such as current Luca/Majkel data.

Before materializing labels for a new replay family, verify temporal alignment. Current known convention is approximately `observation(t) -> action(t+1)` for public replay visualizer data, but **revalidate it** rather than assuming all schemas match.

Split by whole episode. Never leak adjacent states from one episode across train/test.

Imitation accuracy is diagnostic, not promotion evidence.

### 8.2 PPO provenance

PPO rollout buffers accept **SELF_ROLLOUT** provenance only.

Public replay actions may initialize BC. They must never masquerade as on-policy PPO trajectories.

### 8.3 PPO baseline contract

Default until evidence/approval changes it:

- recurrent semantic policy;
- complete legal-option scoring;
- ordered without-replacement multi-select;
- public-information actor;
- public-information critic;
- terminal reward `+1 / 0 / -1`;
- isolated recurrent state per environment/player/policy;
- hidden state reset at every lifecycle boundary;
- rule/BC/frozen checkpoint anchors in the league;
- both seats;
- snapshot/PFSP-style opponent mixture rather than pure mirror-only self-play.

Reward shaping, privileged critic, hidden-state belief shortcuts and inference search require separate evidence/approval if they materially change the learned contract.

### 8.4 Model size

The existing G2 recurrent policy is roughly 970k parameters and is a valid starting baseline.

The user is open to a larger model once GPU training is fast. Do not scale merely because an H100 exists. First profile whether policy inference/learner capacity is the measured bottleneck after GPU environment acceleration.

---

## 9. Replay/data firewall

- Acquisition order: episode index -> daily manifest -> explicitly selected episode files.
- Do not download entire daily datasets without a reviewed reason/cap.
- Public replay population is elite/rating/availability biased; never call it an unbiased ladder sample.
- Keep raw replay bodies private/ignored.
- Use semantic action meaning for duplicate physical-card options where necessary.
- Hidden visualizer data is not actor input merely because it exists in a replay JSON.
- Validate replay schema/version and temporal alignment before supervision.

Relevant current local corpora include Luca exact-deck and Majkel history/teacher data; see the canonical master handoff for paths.

---

## 10. Promotion gate

The hard user target remains:

> **Greater than 95% overall native CABT win rate on a broad, diverse evaluation suite while remaining generalized.**

Do not weaken this because the deadline is close.

Promotion order:

1. contract/reliability: zero errors/fallbacks/timeouts;
2. catastrophic-matchup floors;
3. broad native expected match strength;
4. holdout confirmation;
5. runtime/package constraints;
6. submission only after explicit approval.

A GPU-simulator win rate does not replace final official/native evaluation.

Report overall rate and per-archetype cells. Large fresh confirmation is required near promotion.

Gold/top-10/>1000 Elo is the strategic target, not a guarantee.

---

## 11. Native evaluation rules

The primary deployment-style native arena must balance seats and use sufficient independent games.

Because native RNG is not deterministically pairable:

- report counts, distributions and uncertainty honestly;
- do not present nominal Python-seed pairs as causal paired games;
- forced actual-first/second diagnostics may be useful but must be labeled separately from natural deployment.

When a candidate nears promotion, include strong current-meta proxies and untouched/less-tuned families.

---

## 12. Search and simulated annealing

Exact current-turn search remains useful for:

- tactical proof;
- counterfactual labels;
- attack/prize/resource tactical arbitration;
- debugging learned-policy mistakes.

Do not use full-game search rollouts as authoritative value estimates when native branch RNG cannot be held fixed.

Simulated annealing is approved as a fast optimizer for well-defined higher-level genomes, for example:

- policy/search arbitration;
- lookup confidence gates;
- league sampling weights;
- risk modes;
- bounded search depth/beam;
- training/runtime hyperparameters.

Objective functions must penalize worst-matchup regressions, seat imbalance, reliability failures and runtime breaches. Do not repeat the rejected shallow linear action-weight representation.

---

## 13. Kaggle/online compute rules

Do not start main online training before local GPU qualification.

When ready:

- choose hardware from measured end-to-end bottleneck;
- main paid/external compute requires explicit user authorization;
- Kaggle H100 was previously restricted to another competition and must not be used for KPTCG unless official policy changes and is reverified;
- ordinary Kaggle GPU availability/quota changes and must be rechecked;
- user generally prefers to run heavy Kaggle notebooks manually after the assistant prepares clean notebook/input versions;
- keep datasets/models tidy by versioning stable resources rather than proliferating one-off slugs.

Kaggle mounted input layout is source of truth. ZIPs are auto-extracted and `.gz` inputs are auto-decompressed; do not build needless archive/checksum machinery into research notebooks unless explicitly requested.

No submission or active-submission mutation without explicit user authorization.

---

## 14. Codex rule

If repository-local Codex code generation is used, the only permitted model is:

`gpt-5.6-luna-xhigh`

The local Codex account previously returned a hard 400 stating that exact model was unsupported. In that situation:

- do not substitute another model;
- continue implementation directly with ChatGPT/Local MCP;
- retry Codex only if that exact model later becomes available.

---

## 15. Evidence requirements for accepted GPU changes

Every accepted GPU semantic increment should retain enough evidence to reproduce the decision:

- exact Git state;
- exact source paths;
- compile mode / GPU architecture;
- command or retained validation script;
- deterministic fixture inputs where applicable;
- expected/native output;
- CUDA output;
- error flags;
- runtime/memory data for performance changes.

Compile success proves compilation only. It does not prove CABT semantic parity.

For broad final qualification, retain a machine-readable summary rather than relying on conversational claims.

---

## 16. Definition of GPU-port complete

The GPU CABT port is complete only when all are true:

1. reset/setup/mulligan/prizes/bench/TurnStart are GPU-native;
2. all reachable legal selection classes resume correctly on GPU;
3. Main legal generation and action execution are GPU-native;
4. attack/damage are GPU-native;
5. all reachable instant/continual effect semantics are covered;
6. triggers/KO/prizes/Refresh/Active/checkup/turn cycles/result are GPU-native;
7. stochastic shuffle/coin use persistent per-environment GPU RNG;
8. policy projection obeys public-information boundaries;
9. public event/log stream is native-equivalent and consumptive;
10. Python/Torch runtime keeps state/projection/events/actions device-resident;
11. complete real games reach terminal at scale with zero runtime errors;
12. native-vs-GPU controlled differential/invariant suite passes;
13. 4 GB local stress passes;
14. final local realistic CPU-vs-GPU benchmark is recorded;
15. accepted work is committed incrementally from repository root.

Only then move to online BC/PPO planning/execution.

---

## 17. Immediate continuation order

At the current project stage, the next session should not re-plan from scratch. It should:

1. read `continue_prompt.md` and the canonical handoffs;
2. verify Git state and inspect the latest GPU commits;
3. verify the now-integrated public event/runtime API against native event semantics and retained tests;
4. run true real-deck reset-to-terminal GPU games with policy/event consumption;
5. close any remaining engine/public-observation defects;
6. run broad 4 GB reliability/stress;
7. run the final realistic CPU-vs-GPU benchmark;
8. only then design the exact BC + self-play PPO + league campaign based on measured throughput.

Do not stop at a status report if safe local implementation/qualification work remains.
