# 07 — Recurrent PPO and Self-Play League

## Why synchronous recurrent PPO first

It is the smallest auditable algorithm that supports on-policy compound actions, recurrent partial observability and population opponents. APPO and R2D2 add policy lag/replay complexity before the action and state contracts are proven. The system may later decouple actors asynchronously while preserving a strict policy-version boundary.

## Process topology

```text
N engine worker processes
  ↕ compact requests/actions
inference service (current actor + grouped frozen opponents)
  → recurrent rollout store
  → PPO learner
  → immutable policy version
  → evaluation + league registry
```

Each engine worker owns one battle. The learner never touches the native engine. The inference service maintains hidden states keyed by `(episode_uuid, player, policy_id)` and deletes them on acknowledged reset, terminal or worker failure.

Every inference request carries `(episode_uuid, player, policy_id, selection_seq)`. The service rejects stale or out-of-order sequence numbers, returns a cached action without a second recurrent update for an exact duplicate request, and acknowledges reset before an environment ID can be reused. This idempotency contract is mandatory for both local queues and Modal actors.

Benchmark two inference layouts before Modal scale:

- actor-local CPU inference;
- central batched GPU inference with a 1–2 ms maximum batching window.

Choose by games/second, cost, p95 queue delay and stability. A small model may be faster and cheaper actor-local; GPU preference is not evidence.

## Rollout unit

The recurrent stream processes every engine selection, including forced choices. The v0 PPO/value/GAE time axis, however, contains only non-forced learner-controlled choice points plus terminal boundaries. A request is forced only when the **compound action space contains exactly one legal ordered submitted list**. Raw option count is insufficient: one option with `min=0,max=1` is not forced because STOP exists, while two options with `min=max=2` may remain strategic because order can matter. Within an autoregressive decoder, a substep with only one valid continuation has zero log-probability, but that fact alone does not make the whole request forced.

Fold every truly forced call into the recurrent state before the next learner choice and store the complete intervening event/call sequence without truncation; they create no actor or value loss node. A recurrent training slice starts from a stored/detached hidden state and may cross neither terminal nor learner policy-version boundaries. This prevents `gae_lambda<1` from imposing arbitrary credit decay merely because the engine emitted many forced micro-selections. Keep a separately tested “all engine calls as value nodes” ablation only if later evidence justifies it.

One non-forced engine selection request is one PPO action; decoder sub-selections are internal to that compound action and are not environment timesteps.

Construct learning sequences per `(episode_id, player, policy_id)`. Never interleave the two players into one GRU/GAE sequence. At terminal, attach the signed terminal outcome to **both** player trajectories even when one player’s last choice occurred before the opponent’s final move; use a terminal boundary record rather than inventing a policy action. In current-version self-play the two streams have opposite outcomes. Against a frozen opponent, only the current learner’s stream enters PPO.

Minimum record:

```text
run_id, episode_id, env_id, player, seat, t
policy_id, opponent_policy_id, canonical_deck_hash, opponent_canonical_deck_hash
observation tensors or lossless packed representation
legal option tensors/offsets/masks
GRU state at sequence start
compound semantic action and subchoices
old compound logp, subchoice logps, entropy, value
reward, terminal, truncation, outcome
forced_policy_mask, valid_transition
engine/card/schema/config hashes
```

At rollout freeze, the batch and every active learner player stream use exactly one immutable current-policy version. Opponents use immutable registry IDs for the full episode. v0 never carries a GRU state created by policy version N into version N+1 and never mixes learner versions in one PPO batch. Finish active episodes before publishing an update; if an operational boundary prevents that, terminate and restart those games as infrastructure truncations rather than continuing their hidden state. The permitted learner policy-version lag is exactly zero.

## Returns and reward

v0 reward:

- win `+1`;
- draw `0`;
- loss `-1`;
- no intermediate shaping.

Start with `gamma=1.0` so value estimates eventual outcome and `gae_lambda=0.95`. Test terminal/truncation carefully. If a collector horizon is reached during a live game, do not assign terminal value zero. Continue folding intervening opponent and forced events, then bootstrap from the next non-forced learner decision; alternatively finish the episode before freezing the batch. A worker/error truncation is separately classified and excluded unless its bootstrap state is valid. Add regression tests for truncation during an opponent turn and during a forced-selection chain. A draw penalty or shaping is an ablation only after replays and diagnostics identify a concrete looping/credit-assignment failure.

The engine opponent’s terminal result must be the negative reward where appropriate. Invalid/crash outcomes are separately counted; never silently turn infrastructure failure into an ordinary strategic loss during development.

## PPO loss

For non-forced actor decisions:

```text
ratio = exp(new_compound_logp - old_compound_logp)
policy_loss = -mean(min(ratio*A, clip(ratio, 1-eps, 1+eps)*A))
v_clipped = old_value + clip(new_value - old_value, -value_eps, value_eps)
value_loss = 0.5 * mean(max((new_value-return)^2, (v_clipped-return)^2))
total = policy_loss + vf_coef*value_loss - ent_coef*normalized_entropy
```

Forced selections:

- are processed in the recurrent event stream and folded into the next learner choice;
- policy mask is zero;
- create no v0 policy/value/GAE node and do not affect entropy, KL or clip-fraction denominators.

Normalize advantages globally over valid current-policy non-forced decisions initially; per-context normalization would unintentionally overweight rare contexts. Mask padding/burn-in from all losses. Recompute option masks and compound log-probabilities exactly. Before the first optimizer step, require probability ratios for stored actions to equal 1 within about `1e-5`; mismatch is a fatal rollout error.

## Initial smoke configuration

These are starting values, not locked truths:

| Setting | Initial value |
|---|---:|
| Optimizer | Adam (`eps=1e-5`) |
| Learning rate | `3e-4`, linear decay |
| PPO clip | `0.2` |
| Value clip | `0.2` |
| Value coefficient | `0.5` |
| Entropy coefficient | context-normalized `0.01` |
| Max gradient norm | `0.5` |
| Gamma | `1.0` |
| GAE lambda | `0.95` |
| PPO epochs | `3`; stop an epoch early on KL gate |
| Non-forced learner choices/update | about `32k`; benchmark `16k–64k` |
| Recurrent unroll | `64` non-forced PPO nodes with intervening forced/event folds; verify against game stats |
| Burn-in | `0` for on-policy stored hidden starts; add only if needed |
| Target/stop approximate KL | `0.02` / `0.03` |

Log LR, outcomes, entropy by selection type, approximate KL, clip fraction, value loss, explained variance, gradient/hidden-state norms, option counts, compound lengths, queue lag, invalid/fallback counts and memory. Report separate rates for raw engine calls, neural calls, non-forced trainable choices, decoder tokens and completed games.

Hard update gates:

- any invalid action, NaN/Inf or log-probability mismatch stops immediately;
- approximate KL above `0.03` ends the PPO epoch;
- clip fraction persistently above `0.30` rolls back the update and lowers learning rate;
- exploding/invalid hidden state stops and writes a reproduction capsule;
- three fixed-evaluation cycles without improvement trigger representation/opponent diagnosis before an algorithm change.

## PPO correctness ladder

1. Unit tests for masked categorical, compound logp, compound-action forced classification, long forced-call chains, clipped value loss, GAE, continuing-game bootstrap, idempotent inference sequencing and recurrent batching without cross-terminal/version slices.
2. Tiny deterministic bandit with legal masks.
3. Tiny partially observable memory task where stateless fails and GRU succeeds.
4. Toy variable-option/multi-select environment.
5. CABT random opponent on the engineering deck.
6. Fixed public rule agents.
7. Current self-play and frozen checkpoints.

Require at least three toy/smoke seeds. One lucky run is not algorithm validation.

## League registry

Every policy entry is immutable:

```text
policy_id, checkpoint_hash, parent_id, role, canonical_deck_hash, schema_version,
created_step, evaluation_summary, active/inactive, artifact_path
```

Roles:

- `rule_anchor`;
- `random_anchor`;
- `current`;
- `historical`;
- `champion`;
- `exploiter`;
- `heldout` (evaluation only).

Keep the opponent fixed for a complete episode. Never overwrite a frozen checkpoint file.

### Policy–deck compatibility and meta coverage

Every policy is bound to its exact `canonical_deck_hash`; never run a recurrent checkpoint with a different deck merely to create diversity. The submitted/current learner always uses the D1 main deck, but opponents should cover important meta decks through:

- official/strong heuristic agents bound to their supported decks;
- frozen RL policies retained from the equal-budget deck bakeoff;
- separately trained deck-specific RL opponents/exploiters when an important matchup lacks a competent pilot;
- held-out deck variants for evaluation only.

Do not claim cross-deck robustness from mirror self-play. If a major archetype has only a random/weak pilot, mark that matchup evidence low-confidence and prioritize building a stronger opponent rather than inflating the champion’s reported win rate.

## Curriculum and sampling

Bootstrap:

1. random legal only until end-to-end learning is demonstrated;
2. rule agents until obvious basics are stable;
3. current-policy mirror;
4. frozen historical checkpoints;
5. PFSP over an eligible pool;
6. dedicated exploiters.

Reduce weak rule-agent training probability after consistent dominance, but keep a small anchor probability to detect forgetting.

PFSP variant for “challenging but learnable” opponents:

\[
w_i = \epsilon + (4\hat p_i(1-\hat p_i))^\alpha,
\]

where `p_i` is the player-slot-balanced natural-deployment posterior score of the **current rollout learner version** against opponent `i`, estimated with a Beta prior and draws counted as half a win. Key estimates by `(learner_policy_id/version, opponent_policy_id, learner_deck, opponent_deck, player_slot)`. A new learner version may initialize from its parent posterior, but its observations refresh a distinct record; never pool materially different versions without an explicit decay/version rule. Start with `alpha=1`. This peaks near 50%, has an exploration floor and avoids spending everything on trivial or impossible opponents. Require minimum samples, cap any one opponent’s probability and retain uniform/diversity mass. Record the exact formula/version.

Example mature mixture to test, not blindly adopt:

- 10% rule-agent regression anchors;
- 25% frozen current-version mirror;
- 40% PFSP historical/challenging;
- 10% uniform historical diversity;
- 15% champion, alternate-deck specialists or exploiters.

Matchmaking must also balance opponent deck archetype and player slot while allowing the policy’s natural `IS_FIRST` behavior. Any forced actual-first/actual-second curriculum is separately labeled and cannot replace natural episodes. PFSP alone can collapse onto many checkpoints of one archetype.

Retain roughly 16–32 archive policies: the first competent policy, every promoted champion, strategically distinct policies and successful exploiters. Prune redundant easy policies rather than simply the oldest. Evaluation may include labeled **seen regression anchors** that also appeared in training, but promotion must reserve a genuinely held-out decisive subset of policies/deck variants outside matchmaking. Results against seen rule agents or historical opponents are regression evidence, not held-out generalization evidence.

## Champion promotion

The newest policy is never automatically champion. Promotion invokes the frozen evaluation protocol in `09_EVALUATION_SUBMISSION.md` and requires:

- reliability eligibility;
- no catastrophic important-matchup regression;
- positive meta-weighted improvement with sufficient evidence;
- safe latency/memory;
- no immediate exploiter collapse.

Keep one immutable trusted anchor and one current challenger.

## Exploiters

Start only after a champion beats rule anchors and historical self-play reliably. An exploiter is a separate RL policy trained primarily against a frozen champion, with diversity/reset controls. Its purpose is to find weaknesses, not to become the final agent automatically.

When an exploiter succeeds:

1. verify the exploit in a large held-out match sample;
2. cluster failure contexts/replays;
3. add the exploiter and nearby deck/opponent variants to training with bounded weight;
4. retrain challenger;
5. re-evaluate the whole population to prevent overfitting.

An initial escalation threshold is exploiter win rate above 55% over at least 600 player-slot-balanced natural-deployment held-out games. When crossed, block champion promotion until the weakness and any repair are evaluated under the full constrained protocol.

## Checkpoints and recovery

Checkpoint at a time/transition interval that loses no more than 10–15 minutes:

- actor, critic and optimizer;
- scheduler/AMP scaler;
- global decision/game/update counters;
- RNG states available in Python/NumPy/PyTorch;
- league registry and matchup estimates;
- resolved config, code commit and data/deck hashes;
- latest completed rollout boundary.

Resume only from a committed complete checkpoint written atomically. Engine randomness will prevent bit-identical trajectories; state/counters and statistical behavior must still restore.

## Algorithm change gate

Do not switch because one CABT run is noisy. Consider R2D2/APPO only after:

- G1–G3 correctness passes;
- at least two PPO configurations and three seeds show the same plateau;
- sufficient decisions have been collected to show no credible improvement versus fixed anchors;
- policy/value/entropy/KL diagnostics are healthy;
- representation/action coverage and opponent curriculum have been inspected;
- the expected benefit justifies the remaining engineering time.

If throughput, not sample efficiency, is the bottleneck, optimize actor/inference architecture or use bounded APPO. If reusing rare states is the bottleneck, prototype R2D2 on a small branch, never replace the working PPO path in place.

## Gate G3/G4 evidence

G3 reports:

- toy-task three-seed learning curves;
- CABT reward/win curves against fixed anchors;
- exact transitions, games and wall time;
- PPO health metrics;
- invalid/crash/timeout/fallback counts;
- checkpoint-resume result;
- neural SPS and bottleneck profile.

G4 additionally reports:

- policy-version lag distribution;
- actor CPU, inference GPU and queue utilization;
- central-versus-local inference comparison;
- two-hour Modal canary stability and projected cost;
- restart recovery and checkpoint integrity;
- scale configuration selected with evidence.
