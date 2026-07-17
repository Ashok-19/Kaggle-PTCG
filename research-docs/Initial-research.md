## Verdict

You are probably right that a learned component is needed for the ceiling. I disagree that the winning submission should be pure, tabula-rasa RL.

My gold-oriented hypothesis is:

> **One highly optimized deck specialist → rule/search demonstrations → behavior cloning → recurrent league PPO → belief-aware root search → deterministic safety fallback.**

RL improves an already competent policy instead of spending most of your compute rediscovering legality, setup, sequencing, and obvious tactics.

That conclusion is supported by both your Orbit Wars archive and the currently available Pokémon evidence. One competitor reports pure RL eventually reaching silver, while another public 21-submission project reports that its rules/shallow-search agents substantially outperformed PPO, AlphaZero, and narrow MCTS. Both are participant self-reports, not organizer-verified results, but together they argue strongly for a hybrid. [RL journey discussion](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/discussion/717697), [21-submission project](https://github.com/TomBombadyl/kaggle_pokemon).

No plan guarantees gold—especially in a field currently exceeding 5,000 teams—but this is the highest-upside design I found for your compute budget.

## What the competition mechanics imply

The final deadline is August 16, 2026 at 23:59 UTC; the entry and team-merger deadline is August 9. The ladder uses outcome-based Gaussian skill estimation, so winning narrowly is worth the same as winning convincingly. Five submissions are allowed daily, but only two recent eligible agents play, and evaluation continues after the deadline while ratings converge. [Competition page](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle), [evaluation](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/overview/evaluation), [submission instructions](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/overview/how-to-submit-to-this-competition).

| Competition property                                     | Strategic consequence                                                                   |
| -------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| Win/draw/loss is the final objective                     | Use terminal `+1/0/-1`; do not optimize prize margin as the main reward.                |
| Hidden hands, prizes and decks                           | Vanilla AlphaZero-style search is invalid without a belief model.                       |
| Structured legal options are supplied                    | Score the legal options; do not learn legality through a giant fixed action vocabulary. |
| Exact search API exists                                  | Learning a world model with MuZero wastes compute.                                      |
| CPU-constrained deployment                               | Keep the network around 2–6M parameters and search selectively.                         |
| Current engine exposes 600 seconds of cumulative overage | Reserve substantial time for safety; never search every selection.                      |
| Public episodes and top submissions can be inspected     | Replay mining and meta modeling may be your cheapest source of strong supervision.      |

The environment defines rewards as `-1/0/1`, `runTimeout=2000`, and `remainingOverageTime=600`. [Official environment configuration](https://github.com/Kaggle/kaggle-environments/blob/master/kaggle_environments/envs/cabt/cabt.json).

The API exposes 11 selection types, detailed contexts, structured option fields, logs, state objects, and `search_begin/search_step/search_end`. Importantly, `search_begin` requires predictions for hidden zones. [cabt API documentation](https://matsuoinstitute.github.io/cabt/api.html).

## What the Orbit Wars solutions actually teach

The top three Orbit solutions are not reproducible under your budget:

| Orbit rank |                                      Approximate scale | Relevance                                   |
| ---------: | -----------------------------------------------------: | ------------------------------------------- |
|          1 | 200M parameters, 15B PPO steps, about 2,400 B200-hours | Architecture ideas only                     |
|          2 |        4.3M model, 10B PPO steps, about 576 H100-hours | Small model good; training scale impossible |
|          3 |                                6.2M model, 11.1B steps | PFSP and semantic actions transfer          |

The useful templates are lower down:

* **Rank 8:** small transformer, autoregressive micro-actions, checkpoint league, value-guided search, and KL regularization toward a sensible prior. This is the closest compute-constrained gold template.

* **Rank 19:** fast simulator, behavior-cloning warm start, critic warmup, PPO against historical policies, then deployment calibration. This is the best overall blueprint for Pokémon.

* **Rank 49:** conditional behavior cloning worked; PPO later collapsed. Mixing contradictory teacher styles without teacher/deck conditioning is dangerous.

* **Rank 60:** exploiters broke a passive self-play equilibrium and produced a large local improvement.

* **Rank 72 and 349:** later checkpoints were sometimes worse, and local/ladder ratings were noisy. More training is not automatically better.

* **Rank 223:** a rule planner with a learned value veto and BC tie-breaker was effective. This is your fallback design if full PPO fails.

The common lesson is not simply “RL wins.” It is:

> Make every transition cheap, give the model a compact semantic action representation, start from competence, and select checkpoints through population evaluation.

Unlike Orbit Wars, I would not immediately rewrite the simulator. The Pokémon engine already has a native simulation/search implementation. Profile multiprocessing and batched inference first; rewrite only if measured rollout throughput makes it necessary.

## Recommended agent

### 1. Specialize in one deck first

Do not train a universal agent over the entire card pool initially. Your budget could disappear before it learns one archetype well.

Build a replay-derived deck matrix:

1. Download top-team episodes.
2. Infer deck fingerprints from revealed cards and submitted deck information where available.
3. Cluster the major archetypes.
4. Estimate matchup frequency and outcomes.
5. Select one archetype with:

   * strong current top-table incidence;
   * an existing competent rule agent;
   * a manageable decision tree;
   * relatively few disastrous matchups.

Dragapult is a sensible initial engineering candidate because an official rule-based implementation exists, but the final choice should come from current replay data rather than its historical public rating. Kaggle also provides Lucario, Abomasnow and Iono sample agents.

The official CLI supports inspecting leaderboard teams, submissions, episodes, replays and agent logs:

```bash
kaggle competitions leaderboard pokemon-tcg-ai-battle -s
kaggle competitions team-submissions <team_id>
kaggle competitions episodes <submission_id>
kaggle competitions replay <episode_id> -p replays
```

[Official simulation-competition CLI guide](https://github.com/Kaggle/kaggle-cli/blob/main/docs/simulation_competitions.md).

Only after the first specialist is strong should you build a second, complementary deck as a counter-meta challenger.

### 2. Network architecture

Target roughly 2–6M parameters.

**State encoder**

* Card-ID embedding plus card type, HP, stage, energy, retreat cost, attack and ability tags.
* Zone, owner, visibility and active/bench embeddings.
* Instance features: damage, status, attached energy/tools, evolution history, whether it appeared this turn.
* Separate set encoders for hand, active, bench, discard, stadium and revealed/search buffers.
* Global features: turn, prizes, deck/hand counts, supporter/energy/retreat flags and first-player state.
* A 128–256 dimensional GRU over public logs and prior decisions.

The recurrence matters. The current observation alone does not adequately summarize everything inferred from earlier actions and reveals.

**Action encoder**

Score the legal options supplied by the environment. Each option representation should contain:

* selection type and context;
* option type;
* card/source/target identity;
* area and player;
* attack or skill ID;
* count/numeric value;
* affected entities;
* one-step simulator-derived deltas when available.

For `minCount/maxCount` selections, use an autoregressive pointer head with a small beam and a stop action. Do not enumerate arbitrary combinations and then retain the first 64.

**Heads**

* Masked legal-action policy.
* Observation-only win/draw/loss value head for deployment and search.
* Training-only privileged critic that sees the true simulator state.
* Auxiliary opponent-archetype and hidden-card belief heads.
* Optional next-public-event and prize-race heads.

The actor must never receive hidden information. A privileged critic is only a training device.

### 3. Use the Search API as an action-feature oracle

This may deliver more gain per simulation than generic MCTS.

For each important legal root option, simulate one step and extract:

* damage and knockouts;
* status changes;
* hand/deck/discard/bench changes;
* energy and tool changes;
* prize changes;
* switching;
* terminal status;
* newly available follow-up actions.

Feed these deltas into a neural or rule-based reranker. This lets the network reason about consequences without memorizing every card effect from scratch.

## Training curriculum

| Stage                  | Work                                                                          | Promotion gate                               |
| ---------------------- | ----------------------------------------------------------------------------- | -------------------------------------------- |
| 0. Infrastructure      | Exact replay tests, seeded games, action legality tests, throughput profiling | Zero divergence/crashes                      |
| 1. Teachers            | 10k–50k games from official rules, improved heuristics and shallow search     | Teachers beat the evaluation population      |
| 2. Supervised          | Behavior cloning, belief heads, observable value and privileged critic        | Clone approaches teacher population strength |
| 3. Critic warmup       | Freeze policy; train value heads from complete games                          | Values calibrated across decks and seats     |
| 4. League RL           | Recurrent masked PPO against an 8–16-policy league                            | Improvement against mixture, not just mirror |
| 5. Exploiters          | Train policies targeting the champion’s weak matchups                         | Champion survives approximate best responses |
| 6. Search distillation | Add successful root-search decisions to the BC buffer                         | Search gain retained with fewer simulations  |

A practical league mixture:

* 40–50% current champion or current policy;
* 20–30% frozen historical checkpoints selected by PFSP;
* 10–20% strong public rule/search agents;
* 10–20% exploiters, unusual decks and intentionally awkward policies.

Freeze the sampled opponent for the entire episode. Maintain a complete cross-play matrix, because self-play can cycle between non-transitive strategies.

Use PPO as the primary learner, with:

* KL regularization toward the competent BC policy;
* low or adaptive entropy rather than aggressive uniform exploration;
* terminal reward as the actual optimization target;
* prize, damage and resource targets as auxiliary predictions rather than dominant shaped rewards.

[PPO](https://arxiv.org/abs/1707.06347) is the safest primary algorithm here. AlphaStar’s league and exploiters provide the appropriate conceptual model for opponent diversity. [AlphaStar](https://www.nature.com/articles/s41586-019-1724-z).

If PPO proves too sample-inefficient, recurrent replay methods such as [R2D2](https://openreview.net/forum?id=r1lyTjAqYX) are the backup, but off-policy learning against changing opponents is harder to stabilize.

## Hidden-information search

Do not create independent random guesses for every hidden zone. That produces impossible worlds.

For every particle:

1. Start from a legal 60-card deck hypothesis.
2. Subtract every visible or previously revealed card.
3. Partition remaining cards across hand, prizes and deck **without replacement**.
4. Maintain deck order where known.
5. Sample opponent deck archetypes from the current replay-derived meta prior.
6. Reweight archetypes as cards and actions are revealed.

Then use **root-only belief evaluation**:

* Select the policy’s top 4–8 root actions.
* Sample 8–16 internally consistent particles.
* Spend only 16–64 simulations in total, not per particle.
* Roll forward one or two turns.
* Ensure both simulated actors receive only their legitimate observations.
* Aggregate expected terminal or leaf value across particles.
* Mix the search result back with the policy prior according to sample confidence.

Search only when:

* policy entropy or policy/value disagreement is high;
* a main action has several plausible lines;
* an attack, target, discard, search or switching decision is consequential;
* the game is near a prize-race or terminal threshold.

Do not search forced setup responses or obvious one-option selections.

Keep `manual_coin=False`; never let the search choose favorable coin outcomes.

This is closer to a lightweight combination of [POMCP](https://papers.nips.cc/paper/4031-monte-carlo-planning-in-large-pomdps), [ISMCTS](https://eprints.whiterose.ac.uk/id/eprint/75048/1/CowlingPowleyWhitehouse2012.pdf), and [Gumbel search](https://openreview.net/forum?id=bERaNdoegnO) than standard AlphaZero. Full [ReBeL](https://arxiv.org/abs/2007.13544) is theoretically attractive but too complicated for this budget.

I would reject full AlphaZero, MuZero, Deep CFR and NFSP as the main plan:

* AlphaZero assumes perfect information.
* MuZero learns dynamics even though you already possess the exact engine.
* Deep CFR requires expensive repeated game-tree traversals.
* NFSP adds large replay and average-policy machinery without exploiting the available exact search API.

## The official RL notebook is only an interface tutorial

The [official RL+MCTS sample](https://www.kaggle.com/code/kiyotah/reinforcement-learning-and-mcts-sample-code) should not be treated as a competitive baseline. An audit of its [public mirror](https://github.com/TomBombadyl/kaggle_pokemon/blob/main/reinforcement-learning-and-mcts-sample-code.ipynb) found:

* own deck and prizes are sampled independently, permitting impossible duplicate assignments;
* opponent hidden cards are represented by placeholder Snorlax/basic-energy assumptions;
* no recurrent public-history state;
* arbitrary first-64 action-combination truncation;
* only ten MCTS simulations;
* tiny mirror-self-play batches;
* evaluation mainly against random.

Its reported random-agent improvement shows that the code learns something; it says almost nothing about ladder strength.

## Compute allocation

### Kaggle: 45 GPU hours

| Use                                                          | Hours |
| ------------------------------------------------------------ | ----: |
| BC, value and belief pretraining                             |     6 |
| Main league PPO run                                          |    24 |
| Hard-matchup and exploiter fine-tuning                       |     8 |
| Ablations, quantization, runtime tests and packaging reserve |     7 |

Do not run four full PPO configurations. Use successive halving:

1. Three or four small smoke runs.
2. Eliminate unstable configurations quickly.
3. Spend most of the budget on one champion and one controlled challenger.

### Modal: approximately $60

Modal’s current rates are about $0.590/hour for a bare T4, $0.799/hour for an L4 and $1.102/hour for an A10, before CPU and memory. Four physical cores plus 8 GiB RAM cost about $0.253/hour, so $60 is roughly 237 CPU-container hours or about 71 T4 hours when that CPU/memory allocation is included. [Modal pricing](https://modal.com/pricing).

Your highest-return Modal workload is probably:

* parallel teacher-game generation;
* replay preprocessing;
* belief-particle/search label generation;
* large evaluation tournaments;
* approximate best-response training.

Use a T4/L4 learner only when Colab or Kaggle GPU is unavailable. The small network should not require A100/H100-class hardware.

Count both $30 credits only if both accounts are legitimately usable under Modal’s terms; do not make the project dependent on duplicate-account credit.

### Colab

Use Colab for:

* encoder and action-head experiments;
* BC runs;
* auxiliary-head tuning;
* checkpoint evaluation;
* search distillation;
* emergency continuation of interrupted training.

Checkpoint frequently and keep actor-generation separate from learner training.

## Evaluation discipline

Random-agent wins and mirror-self-play wins are smoke tests only.

Build a fixed population containing:

* the four official rule agents;
* your strongest heuristic/search teachers;
* 8–16 frozen league checkpoints;
* several different deck archetypes;
* targeted exploiters;
* one random/noisy agent for robustness only.

For every meaningful comparison:

* swap first and second player;
* use shared seeds where possible;
* report the complete matchup matrix;
* measure mean win rate and worst-archetype win rate;
* track crash, illegal-action and timeout rates;
* measure policy and search p50/p95 latency.

Useful sample-size gates near a 50% matchup:

* About 200 games for preliminary rejection.
* About 600 games to detect approximately 55% versus 50% with reasonable power.
* About 1,500 games for approximately ±2.5 percentage-point precision.
* Around 3,850 games may be needed to distinguish 52% from 50%.

Promote a checkpoint only if:

1. its paired win-rate improvement against the population is positive with a credible interval;
2. no important matchup collapses;
3. first-player bias is controlled;
4. runtime remains safe;
5. an exploiter cannot immediately destroy it.

For ladder usage, keep one trusted anchor and one challenger. Do not churn all five daily submissions; the two live slots are strategically scarce and ratings need time to become informative.

## Schedule to August 16

| Dates        | Deliverable                                                                             |
| ------------ | --------------------------------------------------------------------------------------- |
| Jul 16–20    | Reproduce official bots, exact environment tests, replay pipeline, throughput benchmark |
| Jul 21–26    | Current meta/deck matrix, shallow-search teacher, initial BC specialist                 |
| Jul 27–Aug 2 | Critic warmup and main league PPO run                                                   |
| Aug 3–8      | Exploiters, hard matchups, belief model and search feature oracle                       |
| Aug 9        | Entry/team deadline; architecture and team should be settled                            |
| Aug 10–13    | Final PPO continuation, search distillation, quantization and full tournament           |
| Aug 14       | Submit trusted anchor and best challenger                                               |
| Aug 15–16    | Packaging/runtime smoke tests and emergency fallback only                               |

Do not make architectural changes during the final 48 hours.

## The highest-value first 72 hours

Before spending meaningful GPU time:

1. Reproduce at least two official rule agents.
2. Download and parse several hundred top episodes.
3. Benchmark games and decision points per second with 1, 2, 4 and 8 actor processes.
4. Create a deck × opponent × starting-seat evaluation matrix.
5. Implement correct without-replacement belief particles.
6. Replace the sample notebook’s first-64 action logic with a structural legal-option scorer.
7. Run one search-augmented teacher against the rule population.

If that teacher cannot beat the public rule population, do not start PPO yet.

The likely gold edge is not a bigger transformer. It is the combination of a strong specialist, correct hidden-state reasoning, simulator-informed action features, league diversity, and evaluation strict enough to stop you from promoting fake improvements.

