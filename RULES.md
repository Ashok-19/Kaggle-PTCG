# KPTCG Operating Rules — Top-10 / Gold-Oriented Lane Research

Updated: 2026-08-13 00:27 IST

This file is a durable operating contract for the KPTCG Pokémon TCG AI Battle project. Its purpose is to maximize the probability of a top-10 / gold-range finish without pretending that any local result guarantees a leaderboard outcome.

## 1. Mission and truth standard

1. The goal is a **materially stronger competition agent**, not a prettier codebase, a higher imitation score, or a narrow matchup exploit.
2. Target a **top-10 / gold-range live result**, but never claim a guaranteed rank or Elo before live evidence exists.
3. The current hard promotion target recorded in `ptcg-rl/.chatgpt/KPTCG_PROMOTION_CRITERIA.local.md` is **>95% overall native win rate on a broad, diverse, both-seat evaluation suite while remaining generalized**.
4. A candidate that improves one matchup, one proxy, one deck, or one tiny screen is not a promotion.
5. Repository evidence, exact artifacts, current engine behavior, and fresh Kaggle data outrank memory, intuition, stale narratives, or a result that merely “looks strategic.”
6. If a local result and the live ladder disagree, treat the ladder as strong counterevidence and diagnose the mismatch rather than rationalizing it away.

## 2. Mandatory lane approach

Never spend the whole remaining budget climbing one local hill. Maintain a small portfolio of **structurally different lanes**.

At minimum, active research should distinguish:

- **Lane A — current generalist champion:** improve the strongest generalized control without changing its principle unnecessarily.
- **Lane B — alternative strategic principle/deck:** test a genuinely different deck or game plan drawn from current high-level evidence, not a one-card cosmetic swap.
- **Lane C — policy/control architecture:** investigate a different decision mechanism, state/resource representation, or deterministic planner/distillation method that can generalize across opponents.
- **Lane D — current-meta intelligence and holdouts:** use current public replays and broad local opponents to discover what the other lanes are missing; this lane is evaluation/research, not opponent-name routing.

Each lane must have:

- a falsifiable hypothesis;
- a frozen control;
- a limited discovery budget;
- a clear kill condition;
- a promotion condition;
- at least one independent holdout not used to invent the change.

Do not keep a lane alive because much work has already been invested in it. Sunk cost is not evidence.

## 3. Avoid local optima

1. Do not equate incremental accepted commits with strategic progress.
2. After two or three consecutive improvements from the same mechanism, explicitly ask whether the mechanism is saturating. If live or broad holdout evidence is flat/regressive, branch to a different principle.
3. Prefer changes that alter **resource flow, tempo, prize conversion, board resilience, search consistency, or decision quality across many states** over one narrow trigger.
4. A top player's deck is not automatically a good lane for us. Deck strength and pilot/controller strength are entangled. A deck swap without a faithful policy is not evidence.
5. Conversely, if a different top player changes deck/principle and gains materially, treat that as evidence that a different strategic basin may exist and test it independently.
6. Use the exact current engine and current card pool. Do not optimize against stale archetype assumptions.
7. Revisit rejected branches only when a premise materially changes: new card/deck, new replay corpus, new evaluator, new engine capability, or a previously missing failure mode.

## 4. Avoid one-meta overfitting

1. Never optimize only against the current #1, a single known opponent, or a single public deck.
2. Every serious evaluation panel must include:
   - current/meta-relevant opponents;
   - older strong families;
   - both seats;
   - at least one holdout family not used to derive the latest change;
   - at least one different strategic style where feasible (tempo, control, spread, one-shot/mega, lock/disruption, multi-prize race, etc.).
3. Refresh current leaderboard/deck evidence before making a meta claim. Do not freeze weights from an old top-eight snapshot.
4. Do not route on opponent/team/submission identity.
5. Do not use hidden deck order, hidden prizes, private opponent state, or exact hidden-deck knowledge in a submitted policy.
6. Public-state recognition may be used for research diagnostics, but do not turn “recognized named deck” into a brittle shortcut that violates the generalized promotion requirement. Prefer generic public-state features and strategic conditions.
7. Keep Kanga/Slowking-style final holdout material isolated until the final designated holdout stage unless the user explicitly changes that rule.

## 5. Avoid evaluation overfitting

1. The native engine uses system entropy. Do not claim paired-seed or deterministic trajectory causality from a Python seed.
2. Small independent A/B native panels are descriptive screens, not causal proofs.
3. Use captured states / exact current-turn search snapshots for causal tactical comparisons when possible.
4. Once a policy is fixed, use larger independent native panels across both seats and multiple families.
5. Do not reuse the same tiny state set to invent and validate a rule.
6. Near the >95% target, require a **substantially larger fresh confirmation** and report per-family cells, not just aggregate rate.
7. Zero invalid selections, fallback actions, runtime failures, swallowed exceptions, and timeouts are required for any promotable run.
8. Report failures as failures. Never silently drop them from the denominator.

## 6. Promotion hierarchy

A candidate should move through these stages:

1. **Mechanical validity:** legal actions, correct lifecycle/reset behavior, no package/import failures.
2. **Targeted causal proof:** the intended mechanism actually changes the intended states and solves the claimed failure.
3. **Broad discovery screen:** multiple archetypes, both seats, zero reliability defects.
4. **Independent holdout screen:** families/states not used to invent the change.
5. **Large fresh confirmation:** enough independent games to reject obvious variance-driven “wins.”
6. **Competition package qualification:** exact archive, raw `exec`, startup, realistic callbacks, CABT/native games, no undeclared dependencies.
7. **Live submission:** only after the candidate is a real promotion under the project criteria or the user explicitly changes the gate.

A high aggregate cannot hide a catastrophic matchup. Keep worst-cell performance visible.

## 7. Current live-feedback rule

The strongest observed live NNMax result as of the 2026-08-13 handoff is raw Dawn submission `55454433` at `858.3` public Elo. Two newer locally attractive variants later scored only `682.8` (`55464450`, 4-Dawn/3-Spikemuth) and `605.3` (`55465516`, `d501448`). Therefore:

- Do not treat exact tactical proof additions as sufficient live-strength evidence.
- Do not keep stacking similar heuristic guards simply because each is locally defensible.
- Before the next submission, require a **different-order improvement**: broad structural gain, substantially better decision principle, or a faithful alternative strategic lane.
- Analyze live episode failures of the weak new submissions versus raw Dawn and use them to identify evaluation blind spots.

These scores are mutable ladder facts; reverify before a future decision.

## 8. Search / simulator rules

1. Exact current-turn search is an **offline proof/oracle tool**, not automatically a live controller.
2. The official native shuffle RNG is not exposed/seeded branch-locally. Full-game continuation values are nondeterministic and must not be treated as deterministic labels.
3. Current-turn terminal/prize outcomes can be exact enough for tactical proofs; future board/value rollouts are much less reproducible.
4. The current exact-search runtime lane already timed out badly when layered live. Do not reintroduce it into the submission path without a measured runtime redesign and fresh strength evidence.
5. Search completeness, better witness recovery, or more expansions are not useful if action ranking/strategic horizon is the bottleneck.
6. Distill repeatable strategic invariants from search where possible instead of shipping a slow oracle.

## 9. Replay / public-data rules

1. Use the official episode index -> daily manifest -> explicitly selected episode JSON workflow. Do not download entire daily datasets unnecessarily.
2. Public top episodes are elite/availability biased; do not call them unbiased ladder frequencies.
3. Validate observation/action temporal alignment before imitation claims. Existing project convention: the teacher action for observation at step `t` is often stored at `steps[t+1][seat].action`; reverify against the actual replay schema used.
4. Split by whole episode, preferably chronologically for live-policy reconstruction.
5. Measure semantic action agreement, not physical-copy index agreement.
6. Held-out imitation accuracy is a diagnostic, not a promotion metric. Native game strength decides.
7. Do not build a fake opponent proxy by swapping an unrelated deck under a low-overlap policy and then call it representative.
8. If a faithful proxy is not possible, keep the family as replay/deck evidence instead of manufacturing confidence.

## 10. Model/training rule

The current user-directed Dawn strategy is deterministic/search-heavy; **do not start new Dawn RL/model training by default**. Existing learned Dawn components may remain fallback/prior infrastructure. Full PPO is parked unless the user explicitly changes direction.

If a lightweight model is used for an evaluation-only proxy or research ranker:

- keep it provenance-isolated;
- split by episode;
- test held-out semantics;
- package inference dependency-free where possible;
- do not confuse proxy fidelity with Dawn strength.

The repo `.venv` contains LightGBM; the generic system Python previously did not. Verify the interpreter before declaring a tooling failure.

## 11. Kaggle rules

1. Before any current claim, refresh competition metadata, leaderboard, submission status, and daily quota/eligibility.
2. **NEVER use `kaggle_create_benchmark_task_from_prompt`** unless the user explicitly asks to create a benchmark task. Historical accidental benchmark-task incidents must not recur.
3. Discover exact Kaggle connector tool names/schemas before invoking a write-like action.
4. User normally runs heavy Kaggle notebooks manually. The assistant may prepare/update the notebook and inputs, then inspect/download outputs after the user-run completes.
5. Keep Kaggle datasets/models clean by updating versions instead of proliferating noisy one-off assets when practical.
6. Follow `ptcg-rl/.chatgpt/KAGGLE_DATASET_RUNTIME_RULES.local.md`: Kaggle auto-extracts ZIP and auto-decompresses `.gz`; mounted filenames are source of truth; do not add gratuitous checksum bureaucracy unless the user asks.
7. Do not launch paid compute or unexpected external mutations.
8. A submission is allowed only under explicit user authorization. The user has explicitly asked that, after the current lane-improvement cycle is completed, the **current best agent** be submitted. That is not permission to burn slots on intermediate cosmetic candidates.

## 12. Git / filesystem rules

1. Actual Git top-level is `/home/nnmax/Desktop/kaggle/PTCG`.
2. `Local_mcp` repo id `ptcg` addresses the canonical root and `.chatgpt/handoffs`.
3. `Local_mcp` repo id `ptcg-rl` addresses the main code/experiment subtree.
4. The worktree is intentionally very dirty. Never reset, clean, stash, restore unrelated files, or mass-stage.
5. Use narrow path commits only.
6. The user explicitly requires **every accepted incremental change to be committed locally**. Rejected experiments should be reverted/not committed.
7. Never push unless explicitly requested.
8. Never commit restricted official engine/native libraries/card data/raw replays/checkpoints/submission archives/credentials/signed URLs.
9. Before commit, review exact paths and preserve unrelated staging/worktree changes.

## 13. Submission discipline

Before submitting a candidate:

- package from the exact evaluated source;
- ensure `main.py` and `deck.csv` are at archive root;
- include only competition-compatible dependencies;
- raw-exec test with no implicit `__file__` assumption;
- startup returns exactly the submitted 60-card deck;
- run realistic non-start callbacks;
- run both-seat native package games;
- require zero invalid/fallback/runtime/package failures;
- record archive size/SHA and source/deck identity;
- keep a rollback artifact.

Do not submit because a daily slot exists. Submit because the candidate is meaningfully stronger.

## 14. Required research reporting

For each lane/candidate, record:

- hypothesis;
- exact source/deck identity;
- what changed and why it is structural rather than cosmetic;
- discovery panel and holdout panel;
- both-seat results;
- per-family cells;
- runtime/reliability counters;
- rejected alternatives;
- whether the result is descriptive, causal, or live;
- commit if accepted;
- package/submission ID if deployed.

Preserve negative results. A rejected branch prevents repeated local-optimum loops.

## 15. Stop conditions

Stop or kill a branch when:

- it fails mechanical validity;
- it regresses independent holdout materially;
- it solves only one named opponent;
- its gain disappears on fresh games;
- it needs hidden/opponent-identity information;
- runtime is unsafe;
- it increases imitation accuracy without native strength;
- it duplicates a previously rejected mechanism without new evidence;
- it is only a cosmetic variant of the current 858-class live agent.

The project wins by finding a better strategic basin, not by accumulating patches.
