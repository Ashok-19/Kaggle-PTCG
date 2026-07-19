# DEC-010: Authorize G2/R1 and Freeze Strict Evaluation

Date: 2026-07-19  
Status: Accepted  
User decisions: dashboard `1C`, Kaggle MCP `2`, replay authorization `3A`, strict evaluation `4C`, local-main commits `5A`

## Decision

Authorize implementation of G2 and parallel R1 after G1R closure. Expand the local dashboard into a full evidence-driven research cockpit inspired by the read-only ROGII design, without modifying the ROGII repository. Use the reconnected Kaggle MCP and private Kaggle notebooks for heavy workflows. Commit small cohesive changes directly to local `main`; never push without approval.

This decision does not authorize PPO training, a deck freeze, a Kaggle submission, active-submission changes, paid compute, or Modal execution.

## R1 transfer boundary

R1 follows a two-stage approval:

1. The agent may retrieve the official episode-index `manifest.csv` and one selected daily dataset `manifest.csv`, each pinned to an integer dataset version with retained hashes and receipts.
2. The agent may generate an immutable dry-run plan capped at 20 episode files, 250 MiB total declared bytes, and 64 MiB per file.
3. Before any episode JSON transfer, show the user the exact dataset versions, filenames, declared bytes, rejection reasons, hard caps, and plan SHA-256.
4. No whole-dataset fallback is permitted. A changed dataset version, manifest hash, plan hash, unknown file size, missing receipt, or cap violation fails closed.

## Compute placement

- Local: source changes, unit/contract tests, metadata inspection, deterministic planning, tiny engine smoke, dashboard, packaging, and completed-agent inference checks.
- Kaggle notebooks: GPU/model numerical checks, expensive test matrices, replay parsing at scale, PPO smoke after authorization, and other workflows expected to take more than roughly 15 minutes or materially benefit from accelerator/remote compute.
- Modal: main training and large league/evaluation only after explicit approval.

Every Kaggle notebook run must be private and record the exact Git SHA, source/config hashes, attached data sources and versions, accelerator, internet setting, time/choice cap, stop condition, outputs, and artifact hashes. Notebook-only logic is not a source of truth.

## Strict G2 acceptance

G2 remains in review until all applicable criteria pass:

1. The production actor has fewer than 2,000,000 trainable parameters. The target range is 0.8–1.25 million; exceeding 1.25 million requires a recorded explanation.
2. Every G1R corpus option resolves to a model token. No visible entity, event, or legal option is silently truncated.
3. Raw serial magnitude and arbitrary option-list position are not actor features. Entity identity is represented through equality and source/target relations.
4. Native/permuted legal-option orders produce equivalent semantic logits after inverse mapping within `1e-5` absolute tolerance in float32 fixtures.
5. CPU/GPU checkpoint round-trip and fixed-fixture actor/value/hidden-state parity pass within `1e-5` absolute tolerance in float32.
6. Compound-action actor/learner log-probability replay error is at most `1e-5`.
7. Gradient reaches card/entity, event/recurrent, option, selection-decoder, actor, and value components.
8. Ten thousand complete neural-policy games finish with zero invalid selections, crashes, timeouts, post-terminal dispatches, development fallbacks, stale requests, or recurrent ownership/reset violations.
9. On the declared CPU qualification host, projected p99 cumulative policy inference time at the G1R p99 non-forced decision count is at most 120 seconds per game; peak process RSS is below 6 GiB. Final submission qualification may impose a stricter measured limit.
10. All evidence is independently recalculated before `PASS`.

## Strict G3a correctness acceptance

1. Masked bandit, recurrent partial-observation task, and variable-option/multi-select toy environment each pass in three of three declared seeds.
2. The recurrent task must demonstrate a preregistered margin over a stateless control in every seed.
3. Stored old compound log-probabilities reproduce before the first update with maximum absolute error `<=1e-5`; initial PPO ratios remain within `1e-5` of one.
4. No NaN/Inf, invalid action, timeout, fallback, stale inference request, hidden-state cross-owner event, or unclassified truncation occurs.
5. Checkpoint resume restores model, optimizer, scheduler/scaler, counters, league, rollout boundary, and available RNG states. Fixed-tensor outputs before and after restore match within `1e-5`.
6. G3a is an algorithm proof and does not establish strength.

## Strict G3b competence acceptance

All games use balanced player slots under natural deployment and immutable exact-deck opponents. Forced actual-first/actual-second games remain separate diagnostics.

### Training budgets

- Broad screen: three seeds, exactly 1,000,000 non-forced learner choices per seed.
- Competence confirmation: surviving configuration reaches exactly 5,000,000 cumulative non-forced choices per seed across the same three seeds.
- Choice budgets between compared runs must agree within 0.25%. Code, model family, optimizer family, opponent population, evaluation population, reward, and stopping rules are identical unless the comparison explicitly changes one preregistered factor.

### Fixed evaluation thresholds

- Random/noisy anchor: at least 1,000 total games and a 95% lower credible bound on match score of at least 0.85.
- Rule anchors: against at least three of the four exact native rule-agent/deck anchors, the 95% lower credible bound on match score must exceed 0.50 and posterior probability that score exceeds 0.50 must be at least 0.975.
- Remaining rule anchor: 95% lower credible bound must be at least 0.35.
- Frozen aggregate: the 95% lower credible bound of the preregistered meta-weighted score across the fixed competence population must exceed 0.52.
- Seed robustness: no declared seed may have a meta-weighted point estimate below 0.50, and the across-seed standard deviation must be reported.
- Reliability remains zero-tolerance.

Failing a threshold does not permit threshold revision. It triggers one bounded diagnosis cycle.

## Strict deck and checkpoint eligibility

- Reliability: zero invalid, crash, timeout, fallback, stale-request, and package-parity failures in the declared soak.
- Cross-deck D1 important-matchup floor: 95% lower credible bound on score at least 0.40 for every preregistered important matchup, with posterior probability of score below 0.40 less than 0.025.
- Same-deck checkpoint regression floor: for every important cell, posterior probability of a regression greater than 0.03 versus the trusted anchor must be below 0.025; the absolute 95% lower bound must remain at least 0.40.
- Final deck comparison uses at least three seeds for every unresolved finalist and equal cumulative non-forced-choice budgets.

## Strict champion promotion

A candidate becomes the trusted champion only when all conditions hold:

1. At least 3,000 frozen-population natural-deployment games, including at least 300 games per important archetype where feasible.
2. Posterior probability that the meta-weighted candidate-minus-anchor score is positive is at least 0.99.
3. The 95% lower credible bound of candidate-minus-anchor score is at least `+0.02` and the posterior mean improvement is at least `+0.03`.
4. All absolute and relative important-matchup floors pass.
5. CPU latency, memory, package, checkpoint, and clean-runtime parity pass with margin.
6. No verified immediate exploiter collapse under the preregistered exploiter test.

An unresolved or merely positive point estimate may remain an experimental challenger, but it cannot replace the trusted anchor or be called champion.

## Algorithm pivot trigger

A PPO failure is established only after:

- two preregistered bounded PPO configurations;
- three seeds per configuration;
- at least 3,000,000 non-forced choices per valid seed;
- healthy numerical, policy/value, entropy, KL, gradient, recurrent-state, and throughput diagnostics;
- two fixed evaluation cycles per configuration; and
- one bounded representation/opponent-curriculum diagnosis cycle after the initial miss.

If both configurations still fail G3b competence, stop scaling PPO and review the strongest validated rule-agent path plus narrowly controlled improvements. Switching to APPO, R2D2, behavior cloning, reward shaping, privileged state, or inference search requires a new explicit decision.

## Dashboard consequence

The dashboard will become a read-only projection of structured records for gates, tasks, hypotheses, decisions, experiments, runs, replay snapshots, decks, evaluations, submissions, costs, artifacts, and learning documentation. It must auto-sync when allowlisted sources change and refresh the browser without manual reload. Missing producers remain `NOT_STARTED`; no synthetic score or completion is permitted.
