# 09 — Evaluation, Promotion, Ladder and Submission

## Evaluation is a separate system

Every serious checkpoint is evaluated by an immutable service/config on a frozen population. The service never updates the policy, league estimates or meta weights during a tournament. The matrix may contain **seen regression anchors** that also appeared in curriculum, but these cells are labeled and never presented as held-out evidence. A predeclared decisive subset of policies and deck variants remains genuinely outside training matchmaking.

## Population composition

Maintain and tag each member as `seen_regression` or `held_out`:

- four official rule-agent/deck anchors;
- one random/noisy agent for smoke only;
- strongest engineering heuristic/search policies;
- 8–16 diverse frozen RL checkpoints once available;
- multiple important current-meta deck archetypes;
- deck variants held out from training;
- targeted exploiters;
- trusted live anchor and candidate challenger.

Avoid counting many near-identical historical checkpoints as independent diversity. Tag policies by deck, lineage, training window and style. Official rule agents used in training remain useful regression cells, but success against them cannot establish generalization or by itself decide promotion.

## Match protocol

The engine distinguishes player slot from who actually goes first: player 0 may choose the first-player assignment. Maintain two modes:

- **Natural deployment (primary):** swap candidate/opponent between player slots equally and let the policy make the official first-player choice. This estimates ordinary submitted behavior.
- **Forced-seat diagnostic:** override the first-player choice to create equal actual-first/actual-second samples. Label this diagnostic; never report it as the policy’s natural win rate.

For every opponent/deck cell:

- balance player slots in primary mode and actual first/second status only in the separate diagnostic mode;
- keep opponent fixed for each episode;
- record engine/package/card/deck/policy hashes;
- use independent large samples because there is no ordinary engine seed hook;
- record draw, invalid, crash, timeout and fallback separately;
- report p50/p95/p99 policy and end-to-end decision latency;
- retain losing replay/state capsules for diagnosis.

The complete matrix is the primary artifact. Aggregate scores without cells are insufficient.

## Evaluation tiers

| Tier | Purpose | Starting sample guidance |
|---|---|---:|
| E0 | package/crash smoke only | 25–50 total games |
| E1 | reject clearly weak checkpoints | 200–400 total stratified games |
| E2 | serious promotion | 1,500–3,000 total, at least about 200 per important archetype |
| E3 | final candidates | 5,000+ stratified games when compute permits |

These are planning values, not magical cutoffs. Near 50%, roughly 50 games has about ±14 percentage points of 95% sampling uncertainty; distinguishing 52% from 50% may require around 3,850 or more games. Compute exact intervals/power for the declared design.

## Statistics

For each cell report:

- games, wins, draws, losses;
- win rate, draw rate and loss rate separately;
- declared score `(wins + 0.5*draws)/games` for aggregation;
- Dirichlet-multinomial posterior or predeclared bootstrap interval for that score; Wilson/Jeffreys binomial intervals are not valid for fractional half-win draws;
- player-slot split, actual-first/actual-second split and natural-versus-forced mode;
- reliability counters;
- candidate-minus-anchor difference with a bootstrap/Bayesian interval appropriate for independent games.

Freeze the confidence/credible level (initially 95%) and one method in config. “Positive interval” means the 95% lower bound of candidate-minus-anchor score is above zero. Do not switch methods to obtain promotion.

Meta-weighted expected match score:

\[
\hat W = \sum_d p_d\hat w_d.
\]

Use a stratified bootstrap or posterior simulation to propagate cell uncertainty while keeping frozen weights `p_d`. Report the interval and effective sample by stratum.

Report sensitivity under frozen 3-, 7- and 14-day meta snapshots, while keeping the 7-day snapshot as the declared primary decision. In natural mode, average player-slot assignments equally within each archetype before applying meta weights. Report actual-first/second outcomes separately. Forced-seat diagnostics use equal actual-seat weights but do not replace the natural primary result.

## Constrained promotion rule

Before running E2, freeze:

- population and meta snapshot/hash;
- important matchups and catastrophic-regression rule;
- game count per cell, player-slot balance and any separate forced-seat diagnostic policy;
- reliability/latency limits;
- confidence method and minimum meaningful effect;
- primary objective and tie-break order.

Promotion sequence:

1. **Reliability:** candidate must have zero invalid/crash/timeout/fallback events in the declared promotion soak and remain under official runtime/package limits with safety margin.
2. **Matchup floor:** candidate must not violate the predeclared important-cell absolute/relative floor. A reasonable first proposal is no important-cell regression larger than 5 percentage points versus anchor, but it must be frozen before results and may be changed only prospectively with justification.
3. **Strength:** candidate’s meta-weighted difference over anchor must be positive with the declared credibility/confidence requirement or large enough to justify a challenger trial when unresolved.
4. **Exploiter defense:** no verified immediate exploiter collapse beyond the declared floor.
5. **Tie-break:** latency, seed/run variance, operational simplicity.

There is no blended “robustness + strength + speed” score.

## Replay-driven diagnosis

For losses, cluster by:

- exact matchup and starting seat;
- terminal cause;
- selection type/context;
- legal branching/multi-select length;
- game phase and resource/prize state;
- model confidence/entropy and value surprise;
- fallback/latency anomalies;
- repeated semantic action patterns.

Manually review a stratified sample of high-confidence losses, low-confidence wins, catastrophic cells and novel contexts. Convert actual failures into opponent curriculum, fixtures or feature bugs. Do not add reward shaping merely because a game was lost.

## Ladder policy

Kaggle is the final external truth but its rating is noisy and matchmaking/meta changes. Use two active roles:

- **anchor:** last trusted, fully validated package;
- **challenger:** only candidate that passed local constraints/promotion or a clearly labeled diagnostic trial.

Although up to five daily submissions may be available, do not churn all five. Suggested practice:

- 25–50 games: package/crash/gross-strength smoke only;
- retain submissions long enough to gather meaningful opponents and replay evidence;
- inspect opponent/deck mix and seat split before attributing rating changes to the model;
- if local strength rises but ladder falls, first check sample size, meta mismatch, runtime/fallback, deck drift and lost replays;
- keep anchor live until challenger evidence is credible;
- never replace both active slots with unproven experiments.

Record submission time, ZIP hash, checkpoint/deck/config, rating/rank trajectory, episode count, opponents and failures.

## Submission build

The builder must stage only required files in an ignored directory and produce a deterministic manifest:

- `main.py` and exact official interface;
- exact 60-card `deck.csv` selected at D1;
- permitted engine/runtime files;
- actor checkpoint and minimal inference code;
- no optimizer, training code, replay data, cloud client, credential, debug fixture or network dependency.

Validation:

1. inspect official current packaging/runtime/size rules;
2. verify deck count/IDs, canonical deck hash and exact file SHA-256;
3. create clean environment/container matching competition runtime;
4. disable network;
5. unpack and import from a new working directory;
6. measure cold load and batch-1 CPU inference;
7. run 1,000+ packaged-agent games across the validation population;
8. inject model-load and inference exceptions to test legal fallback;
9. scan ZIP for secrets, unexpected paths and restricted non-required files;
10. record ZIP contents, sizes and SHA-256.

Development failures remain loud. Submission fallback is deterministic and legal, with local counter instrumentation. A normal final soak must have fallback count zero.

## Final report

For anchor and challenger include:

- canonical deck hash, deck-file/checkpoint/submission SHA-256 values;
- architecture/parameter count;
- complete matchup × seat matrix;
- frozen meta weights and weighted result interval;
- anchor difference interval;
- exploiter results;
- invalid/crash/timeout/fallback counts;
- cold load and latency percentiles;
- peak memory and package size;
- local/cloud run provenance and cost;
- known weaknesses and rollback command.
