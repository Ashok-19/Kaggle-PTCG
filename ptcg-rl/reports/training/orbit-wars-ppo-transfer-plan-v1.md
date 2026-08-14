# Orbit Wars -> KPTCG PPO transfer plan v1

Date: 2026-08-14
Status: smoke-only implementation authorized; full PPO run requires explicit user approval.

## Decision

Behavioral cloning is frozen as an initializer. Use the current specialist BC epoch-1 checkpoint as the initial actor/critic weights, but do not spend further training budget optimizing imitation loss.

The first PPO work is a correctness and viability smoke, not a production-scale training run.

## Orbit Wars evidence reviewed

### Isaiah Pressman / Tufa Labs — 1st place

Source: `Scaling Reinforcement Learning to the Stars` (Tufa Labs, 2026).

Transferable observations:

- Pure terminal outcome reward and standard PPO/GAE can reach very high strength.
- Head-to-head checkpoint promotion was used as the progress signal; >70% against the previous best promoted a new best.
- KL/value regularization against the previous best checkpoint was used for stability.
- One forward pass for all players materially reduced rollout inference cost.
- Isaiah explicitly identified historical-checkpoint league play as a missing improvement for preventing strategic cycles/self-overfitting.
- Gamma=1 encouraged already-winning agents to stall, wasting rollout compute.
- A compact domain-aware observation could have cut average frame compute dramatically despite the winning solution deliberately preferring scaling.

### Yijie Yuan — ~1.2M parameter self-play PPO solution

Source: `Kaggle Orbit Wars Solution` (2026).

Transferable observations:

- Small structured model (~1.2M parameters) remained highly competitive when paired with strong representation and training discipline.
- PPO recipe: gamma=.999, lambda=.95, clip=.2, value coefficient=.5, gradient clip=1.0, one epoch per rollout, entropy=.01 in 2p.
- League: 80% current self-play / 20% frozen historical checkpoint; historical opponents sampled approximately proportional to `1 - winrate` with a small floor (linear PFSP).
- Checkpoints were admitted only after sufficient evaluation evidence rather than every learner update.
- Final checkpoints were selected by large independent round-robin evaluation, not PPO loss.
- High-quality data/feature selection was more useful than indiscriminate volume during imitation experiments.
- Fresh unseen evaluation states were essential to avoid false progress.

### Audun Henriksen / Eirik Torp — 7th place

Source: `7th Place Solution - How structured experiments saved my sanity` (Kaggle, 2026).

Transferable observations:

- Observation engineering was reported as the largest performance lever.
- Auxiliary future-state prediction heads helped the shared trunk and were discarded at inference.
- Pure terminal reward beat attempted reward shaping by a large margin.
- Training against a live copy of the learner performed much worse than using a frozen opponent.
- A historical opponent pool spanning the whole training history fixed a serious self-play local minimum.
- Low-entropy finetuning plus evaluation only against own checkpoints contributed to 2p overfitting.
- Every plausible training change was trusted only after independent tournament evaluation.

### Billy Bradley / Ender — top-10 solution

Source: public Ender technical summary / Kaggle writeup link (2026).

Transferable observations:

- PPO+GAE with leagues of past checkpoints was competitive on modest hardware.
- Autoregressive within-turn micro-decisions were treated as individual RL trajectory steps.
- This maps closely to KPTCG compound selections: individual option/STOP subchoices must have exact probability accounting rather than collapsing the whole request to an opaque label.
- Short inference-time rollout/search can add strength after the policy/value function becomes trustworthy, but is not part of the initial PPO smoke.

### Felix Neumann — 3rd place

Source: public solution summary (2026).

Transferable observation:

- A 6.2M transformer trained with pure self-play PPO earned solo gold. This is another counterexample to the idea that a 100M+ model is required.

### Avinash Kaur — 2nd place

Source: public solution summary (2026).

Transferable observation:

- The winning recipe explicitly progressed through rule systems, behavioral cloning and RL, while keeping the eventual model simple and relying on self-play/compute.

## KPTCG PPO smoke design

### Frozen initializer

- Start from the specialist BC epoch-1 model.
- Treat BC as initial weights only; do not retain a permanent imitation objective in the first PPO smoke.
- Preserve the frozen BC checkpoint as the first historical opponent/reference.

### Reward and credit assignment

- Terminal reward only: +1 for winner, -1 for loser. Draw handling must be explicit and tested if encountered.
- No handcrafted reward shaping in the first smoke.
- Gamma: 0.999.
- GAE lambda: 0.95.
- Reuse the existing validated `ptcg_rl.g3.ppo.compute_gae` implementation.

### PPO objective

- Clip coefficient: 0.2.
- Value coefficient: 0.5.
- Entropy coefficient: start at 0.01.
- Gradient norm clip: 1.0.
- One PPO epoch per rollout for the first smoke.
- Warm-start learning rate should be conservative; first smoke uses a small fixed LR and measures KL/clip fraction before any schedule is selected.
- Reuse existing compound-action probability replay and `ppo_loss`; do not create a second PPO math implementation.

### Opponent policy

Do not build the production loop around a continuously-mutating live mirror.

Smoke stages:

1. Correctness smoke: both seats use the same frozen BC-initialized policy version to generate complete games. This validates the GPU bridge, recurrent ownership, terminal rewards, GAE, and PPO update.
2. League-ready smoke: learner plays mostly current/frozen-current self-play while a minority of games use the frozen BC initializer/reference. The opponent remains frozen for each rollout.

Production candidate after smoke approval:

- approximately 80% current-policy self-play / 20% historical pool initially;
- historical sampling using a PFSP-like weight based on learner weakness against each opponent, with a nonzero floor;
- retain opponents across the full training history, not just the newest checkpoint;
- checkpoint admission by independent tournament evidence.

### Evaluation

Training self-play win rate is not a strength metric because symmetric self-play stays near 50%.

The smoke must report:

- zero GPU-CABT runtime/projection errors;
- zero illegal selections or fallbacks;
- complete terminal games;
- exact/near-exact old log-probability replay before update and initial PPO ratios near one;
- finite GAE, losses, gradients and parameter updates;
- KL and clip fraction after update;
- native before/after games on the exact current Mega Lucario deck against frozen references/baselines;
- no catastrophic loss of legality after the update.

No full run is authorized by a successful smoke alone; report the results and request explicit approval.

## Feature-engineering work before a full run

Do not block the first PPO correctness smoke on new features, but test high-value feature additions before a full training commitment.

The current model schema transports `entity_energy_values` and `entity_energy_offsets`, but `PTCGPolicyV1` does not consume them. This is a material TCG representation gap: the model can see attached-energy count and card identity but lacks the explicit energy-type composition needed to reason efficiently about attack readiness.

Candidate compact derived features to test independently:

- effective attached-energy type summary / attack-payability features;
- active and bench attack-readiness / energy-deficit features;
- retreat-cost readiness;
- public prize-distance and KO-pressure summaries;
- source/target tactical deltas for legal options;
- auxiliary prediction heads for short-horizon public state changes, trained only as trunk regularizers and removed at inference if helpful.

Each feature family must be an isolated experiment with native tournament comparison. Do not bundle speculative changes.

## Non-goals for the smoke

- no full PPO training run;
- no reward shaping;
- no large model scaling;
- no CUDA simulator ABI redesign unless a correctness blocker is proven;
- no inference-time search until the learned value function has demonstrated useful calibration;
- no micro-optimization of BC data loading/training.
