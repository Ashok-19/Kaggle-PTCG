# 00 — Decision Record

## Mission and constraints

| Item | Decision |
|---|---|
| Outcome | Target a top-20/gold finish, not merely a valid submission |
| Time | One-month greenfield program ending 2026-08-16; verify exact close time |
| Team | Solo user, normally 2–3 active hours/day; automation may run unattended |
| Strategic method | RL controls every in-game strategic choice |
| Model size | Prefer about 0.8–1.2M parameters; hard initial ceiling 2M |
| First policy scope | One exact-deck specialist |
| Main training | One evidence-selected deck on Modal |
| Smoke training | Colab and Kaggle; local machine for correctness/profiling |
| Active ladder slots | Trusted anchor plus challenger |

## Training-data boundary

The policy may learn from environment rewards and its own rollouts. Public replays may be used for:

- current-meta and deck-list discovery;
- matchup-frequency estimation;
- deck candidate construction;
- state/action-context coverage measurements;
- failure diagnosis and replay inspection;
- designing a held-out evaluation population.

For v0, public/human/other-agent actions must **not** be policy supervision, behavior-cloning targets, PPO samples or value targets. Replay-derived card/deck frequencies and factual metadata are permitted. If a future experiment changes this boundary, it requires an explicit decision-record update before code or data changes.

## Locked v0 choices

| Area | v0 decision |
|---|---|
| Framework | PyTorch with a custom CleanRL-style trainer |
| Algorithm | Synchronous recurrent PPO |
| Observation | Visible card/entity tokens + global factual features + recurrent public history |
| Model | Two small entity-attention blocks + GRU + semantic option ranker + value head |
| Action space | Score every legal option semantically; never truncate to the first 64 |
| Multi-select | Ordered, without-replacement autoregression with legal STOP |
| Option order | Exclude raw list index in v0; permute legal options during training |
| Critic | Shared public-observation trunk; privileged critic only as later ablation |
| Reward | Terminal win `+1`, draw `0`, loss `-1`; no shaping in v0 |
| Memory | Separate hidden state for each player; reset at battle start |
| Opponents | Rule bootstrap → current/frozen self-play → PFSP → exploiters |
| Search | Not part of v0 inference or PPO; preserve a later teacher/search interface |
| Failure behavior | Development fails loudly; submission logs and uses a legal fallback |
| Deck | Baseline sample deck for engineering only; main deck selected by evidence |

## Deck/checkpoint objective: constrained, not blended

Do not combine strength, robustness, latency and reliability into an arbitrary weighted score.

Use a constrained decision in this order:

1. **Reliability eligibility:** zero invalid actions, crashes and timeouts in the specified soak; submission size and latency inside official limits.
2. **Catastrophic-matchup eligibility:** no important matchup violates the threshold declared *before* evaluation. During cross-deck D1 selection, use a predeclared absolute floor because no comparable trusted cross-deck anchor exists. After the exact deck is fixed, checkpoint promotions may use a relative regression floor versus the trusted same-deck anchor. Do not tune either after seeing results.
3. **Primary objective:** among eligible candidates, maximize the meta-weighted expected match score `(wins + 0.5 × draws) / games`
   \[
   W=\sum_d p_d\,\hat w_d,
   \]
   where `p_d` is the frozen evaluation meta weight and `w_d` is natural-deployment win rate against deck/opponent stratum `d`, with player slots balanced and actual first/second outcomes reported separately.
4. **Uncertainty:** confidence intervals decide whether the evidence distinguishes candidates; they are not an added score component.
5. **Tie-break:** if statistically indistinguishable, prefer lower decision latency, lower variance across seeds and simpler operational risk, in that order.

Freeze meta weights, matchup floors, samples and tie-breaks before each serious comparison.

## Provisional choices that measurements may change

- exact entity and GRU widths within the 2M ceiling;
- centralized GPU inference versus CPU actor-local inference;
- PPO hyperparameters and rollout length;
- draw reward ablation;
- number and mixture of league opponents;
- exact deck and challenger deck;
- quantization for submission;
- auxiliary heads, privileged critic, search distillation or R2D2 after v0 gates.

## Explicit non-goals for v0

- rewriting the engine in JAX/CUDA;
- universal multi-deck policy;
- reproducing the sample AlphaZero/MCTS notebook as the training system;
- behavior cloning from public actions;
- exhaustively enumerating all legal 60-card decks;
- training four full algorithms in parallel;
- relying on Kaggle ladder rating as the only experiment evaluator;
- downloading complete ~20 GiB daily replay datasets to the 30 GiB local disk;
- modifying the competition engine semantics.

## Change-control rule

Every material change needs: observed evidence, alternative considered, expected upside, cost, rollback, and a decision ID in `PROJECT_STATUS.md`. Prefer controlled ablations. After the architecture freeze, only correctness or packaging fixes are permitted.
