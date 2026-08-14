# BC-initialized self-play PPO smoke evidence v1

Date: 2026-08-14
Status: PPO correctness smoke passes; full training run is **not authorized**.

## Initializer and policy

- Model package SHA-256: `4dfba2adb9f97607cfa5dabadba075236bb7aae51eafab264584e947feae3827`
- Frozen BC initializer SHA-256: `a6a136f2f0012b40ce67ea3eccbbf005ec0cd22d2670a02eeaf52843c6f29cc4`
- Trainable parameters: 970,022
- Exact current Mega Lucario deck used for both seats.
- Reward: terminal-only +1/-1, draw 0.
- PPO smoke: gamma=.999, lambda=.95, clip=.2, value coefficient=.5, entropy=.01, LR=3e-5, gradient norm cap=1.0, one PPO epoch per rollout.

## Correctness gates

Across the successful smoke runs:

- all GPU-CABT games terminated without runtime/projection errors;
- all post-update games also terminated legally;
- compound option/STOP actions were sampled from the exact legal masks;
- old compound log probabilities replayed exactly before the PPO update;
- old value predictions replayed exactly;
- GAE, PPO losses and gradients were finite;
- each optimizer smoke produced a nonzero parameter change;
- no full training loop was started.

The first 16-env attempt reached complete rollout, GAE and probability replay but stopped before the optimizer because cuDNN requires recurrent modules in training mode for backward. The harness was corrected to enter train mode only for gradient replay; PTCGPolicyV1 has dropout=0.0, so the action distribution remains deterministic. No optimizer step occurred in the failed attempt.

## Successful 16-env smoke

- pre-update recurrent decisions: 2,683
- meaningful policy targets: 2,284
- rollout throughput: 304.1 decisions/s
- exact probability replay actions: 2,683, max logp/value error 0
- post-update approximate KL: 0.00817
- post-update clip fraction: 5.52%
- gradient norm before clipping: 1.5575
- parameter delta L2: 0.02589
- second complete rollout: PASS

## Successful 64-env scalar compound path

- pre-update recurrent decisions: 10,514
- meaningful targets: 8,927
- rollout throughput: 557.0 decisions/s
- exact probability/value replay error: 0
- post-update KL: 0.00465
- post-update clip fraction: 3.21%
- second complete rollout: PASS

This established correctness but exposed per-environment Python compound action sampling/replay as a severe throughput bottleneck.

## Batched compound action path

A tensorized autoregressive sampler/replayer was added and differential-tested against the scalar PPO contract. It preserves exact option/STOP log probabilities while sampling/replaying all active decisions in one GPU-batched loop.

At 64 environments:

- recurrent decisions: 10,235
- rollout throughput: 1,126.5 decisions/s
- post-update rollout: 1,144.5 decisions/s
- exact probability/value replay error: 0
- post-update KL: 0.00456
- post-update clip fraction: 5.79%

This is ~2.0x the scalar 64-env rollout throughput.

## Successful 256-env batched smoke

Modal app: `ap-Jm7bD31Wvm0SFaeKRYU01U`

Pre-update:

- 256/256 complete games
- recurrent decisions: 40,370
- meaningful policy targets: 34,471
- rollout time: 11.507 s
- rollout throughput: **3,508.3 decisions/s**
- exact log-probability replay actions: 40,370
- max log-probability error: 0
- max PPO initial-ratio error from 1: 0
- max value replay error: 0
- terminal player trajectories: 512 (256 wins, 256 losses)
- old value mean/std: 0.00839 / 0.00536

One PPO update:

- gradient norm: 0.72064
- parameter delta L2: 0.02560
- post-update approximate KL: **0.00761**
- post-update clip fraction: **7.70%**
- all metrics finite

Post-update:

- 256/256 complete games
- recurrent decisions: 40,413
- rollout throughput: **4,040.4 decisions/s**
- zero engine/projection failures

Checkpoint SHA-256: `4be43ef388c6bc453b7873c7cf1da8c4b0ec962cbf4f911d8424b037c378a9d6`

## Decision

PPO is **viable as a learning pipeline**: the BC initializer can generate complete self-play trajectories, terminal GAE and exact PPO probability replay work, and a conservative update remains numerically stable.

The current complete-game smoke is **not yet viable as the production throughput architecture**. At ~3.5k pre-update decisions/s, 1B decisions would require roughly 79 hours of rollout time before accounting for optimization/evaluation. This is too slow for the competition deadline.

Do not interpret this as a simulator limitation: standalone GPU-CABT exceeds 1M decisions/s. The bottleneck is neural-in-loop boundary orchestration/model-policy work at the current small active batch.

## Required pre-approval work

1. Measure rollout-only scaling at thousands of environments with GPU utilization/power telemetry and no stored full-game autograd replay.
2. Replace complete-game PPO replay with a production-shaped fixed-horizon recurrent rollout (T around 64-128), recurrent hidden snapshots, GPU GAE and minibatched PPO replay.
3. Add a frozen-opponent league smoke. Keep the BC initializer as the first historical opponent and avoid a continuously mutating live mirror as the sole opponent.
4. Re-run probability replay, finite-gradient, KL/clip, legality and independent native evaluation gates.
5. Only then present a full-run configuration for explicit approval.
