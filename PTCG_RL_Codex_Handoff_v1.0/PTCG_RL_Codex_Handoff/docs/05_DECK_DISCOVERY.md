# 05 — Deck Discovery, Search and Selection

## Why “extensive search” is staged

The submitted agent supplies its own fixed deck; the engine does not randomly assign one. Training one exact-deck specialist is therefore correct. However, “best deck” cannot be identified by raw card/deck frequency alone:

- deck strength depends on the policy piloting it;
- current top replays are selected and may be biased;
- a strategically strong deck may learn slowly under a one-month RL budget;
- the space of legal 60-card multisets is combinatorial;
- matchup strength depends on the changing ladder meta.

Therefore use an extensive **constrained search funnel**, not exhaustive enumeration. Main Modal training begins only after the funnel selects one exact list.

## Search objective

Maintain two distinct identifiers:

- `canonical_deck_hash`: SHA-256 of the card-data/rules version plus sorted `(card_id, multiplicity)` pairs; use for policy compatibility, cache keys and cross-file identity;
- `deck_file_sha256`: SHA-256 of the exact `deck.csv` bytes; use for package provenance.

Never use a file-byte hash as semantic deck identity or omit the byte hash from a submission record.

Use the constrained rule from the decision record:

1. valid/legal/reliable candidates only;
2. exclude pre-declared catastrophic matchup failures;
3. maximize frozen-meta-weighted expected match score `(wins + 0.5 × draws) / games`;
4. use confidence intervals to decide if differences are resolved;
5. use latency, seed variance and simplicity only as ordered tie-breaks.

Do not add learning speed, rule-bot score, deck popularity and win rate into one arbitrary weighted number. Learning speed is a screening constraint and diagnostic, not a substitute for the final objective.

## Tier A — Replay/meta candidate generation

From the most recent 3/7/14-day snapshots:

- extract exact 60-card lists when available;
- canonicalize by `(card_id, count)` and hash;
- cluster near-identical lists into archetypes/variants;
- record observed score/rating, matchup sample, recency and source coverage;
- include established top families, emerging variants and at least one simpler fast-game archetype;
- reject invalid/partial lists from exact-deck finalists but retain them for archetype evidence.

Output 6–10 candidate families with 1–3 representative exact lists each. Avoid choosing ten tiny variants of the same archetype.

## Tier B — Legality and RL-complexity screen

For each exact list, verify official deck rules and run a common corpus in which the candidate deck is piloted only by the generic legal baseline. Official rule agents keep their native supported decks and appear only as opponents; never attach their hard-coded logic to arbitrary candidates. Measure:

- complete-game validity;
- decisions and engine calls/game;
- wall-clock games/s;
- legal option count distribution (median/p90/p99/max);
- multi-select rate and ordered contexts;
- unique selection/option context coverage;
- average game length and terminal modes;
- starting-seat asymmetry;
- rule-agent implementation coverage/fallback rate.

Reject only clear engineering/learning hazards, invalid lists and candidates whose observed meta evidence has already vanished. Do not assume low branching is always better; it is only a resource constraint.

## Tier C — Simulator-guided screening and deck mutations

Official rule agents may act only with the exact decks/variants their hard-coded logic supports; never pretend they are generic pilots for mutated decks. Build and validate a bounded generic candidate-deck pilot from the semantic action system (legal heuristic and, optionally, shallow simulator search) before using Tier-C scores. Report its unhandled-context/fallback rate and reject its rankings if coverage is poor. This evaluator is a **deck-search instrument**, not the final policy.

If a competent generic pilot is not ready within the Tier-C budget, make Tier C optional: use official bots only as native-deck opponents and move replay finalists directly into more aggressive Tier-D RL successive halving. Weak or mismatched pilot scores are worse than missing scores.

For promising base lists:

- mutate small legal packages (usually 1–4 card-count changes) rather than random 60-card generation;
- preserve legality, required evolution/energy synergies and deck size;
- seed mutations from observed replay variants and card metadata;
- evaluate common random numbers only where the engine actually permits; otherwise use larger independent samples with balanced player slots plus separate forced-seat diagnostics;
- use successive halving: small screen → retain top fraction → larger screen;
- retain diversity across archetypes rather than one local variant basin.

Cache `(canonical_deck_hash, opponent_canonical_deck_hash, evaluator_version)` results. Stop searching when improvement plateaus under the frozen evaluator or budget cap. Search results are hypotheses because rule/search policies can rank decks differently from PPO.

## Tier D — Equal-compute RL bakeoff

This is the decisive tier because it measures both achievable policy strength and learnability under the actual algorithm.

Protocol:

1. choose 3–5 finalists;
2. freeze and separately hash the training opponent population and the held-out evaluation population, plus code commit, model family, hyperparameters, transition budget, wall-clock cap, seats and evaluation meta snapshot;
3. initialize each from independent but recorded seeds; do not transfer a policy between different exact decks in v0;
4. allocate identical **non-forced learner-choice** budgets to every candidate within each successive-halving round, with wall-clock/cost as safety caps;
5. use one small seed for the broad first round, two for the surviving two or three candidates and three seeds only for the final one or two unresolved candidates; predeclare successive-halving budgets;
6. evaluate every checkpoint on one frozen population that the trainer does not sample;
7. compare learning-curve area for sample efficiency, but make final selection only among candidates that reached the same declared final-round cumulative budget, using constrained held-out strength at that common budget;
8. report uncertainty and full deck × opponent × seat matrix.

Do not give a slower-learning deck extra decisions after seeing early results unless all candidates still eligible in that round receive the same revised budget. Eliminated candidates need not receive later-round compute; equality applies within each round, and final comparisons require equal cumulative final-round budgets.

## Candidate population

The frozen bakeoff population should contain:

- four official rule agents/decks;
- random/noisy policy only as a smoke anchor;
- recent exact/archetype decks from the seven-day snapshot;
- the candidate decks in cross-play when policies exist;
- several frozen early RL checkpoints;
- held-out deck variants and at least one emerging three-day deck;
- no public replay actions as opponent imitation.

In primary natural-deployment evaluation, balance player slots and let the policy choose first-player assignment. Run forced actual-first/actual-second games only as labeled diagnostics. Because the engine lacks a normal seed hook, report independent-sample uncertainty and larger samples rather than claiming paired tests.

## Selection record

Before evaluation, write:

```yaml
meta_snapshot: <hash>
meta_weights: {archetype_a: 0.0, archetype_b: 0.0}
important_matchups: [archetype_a, archetype_b]
catastrophic_rule:
  type: absolute_important_matchup_floor
  minimum_win_rate_or_lower_bound: <declared value and interpretation>
reliability_games: <declared count>
screen_games_per_cell: <declared count>
serious_games_per_cell: <declared count>
primary_metric: meta_weighted_expected_match_score
confidence_method: stratified_dirichlet_multinomial_posterior_simulation
confidence_level: 0.95
tie_breaks: [latency, seed_variance, operational_simplicity]
```

Do not choose thresholds after viewing the finalist matrix. If no candidate is eligible, report that result and revise the deck population or training—not the threshold post hoc.

## Compute allocation

Reserve roughly 5–10% of total cross-platform training compute for the full funnel. Use a predeclared three-round successive-halving split such as 20% broad one-seed screen, 30% survivor confirmation and 50% final one/two-candidate resolution; convert those fractions to choice counts only after G3b measures throughput. Most Tier A/B work is CPU/data; Tier C is optional parallel CPU simulation; Tier D uses short Colab/Kaggle canaries. Keep the main Modal league budget untouched until D1.

## Gate D1 acceptance

- candidate source, canonical deck hash and exact deck-file SHA-256 recorded;
- no legality errors across the full simulator corpus;
- at least 3 distinct archetypes reach Tier D unless current evidence strongly rules them out;
- every candidate receives the same declared budget within each round, and final selection compares only candidates with the same cumulative final-round budget;
- full frozen-population natural evaluation with balanced player slots and separate actual-first/second diagnostics recorded;
- reliability and catastrophic constraints applied first;
- main deck selected on meta-weighted held-out performance with uncertainty;
- runner-up exact deck and reason retained;
- deck file frozen and referenced by SHA-256 in all subsequent configs/checkpoints;
- any future deck change forces a new D1 decision and prevents accidental checkpoint reuse.
