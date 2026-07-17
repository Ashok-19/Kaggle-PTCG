# 06 — Observation, Model and Action Schema

## Design goals

- represent factual card/game semantics without requiring the network to memorize every rule from raw IDs;
- preserve hidden-information legality;
- remember public information that disappears from the current snapshot;
- score every variable legal option in one batched model call;
- make invalid actions structurally impossible;
- remain below 2M trainable parameters and safe for CPU submission inference;
- permit later ablations without rewriting the engine adapter.

## Observation boundary

The deployed actor may consume only information legally supplied to that player by the official API plus its own prior legal observations/actions. It may not consume visualizer/full-state data, opponent hidden cards, search internals or training-only truth.

The v0 critic shares this same public boundary. A privileged critic is a separate later experiment with a distinct config/checkpoint type and must never alter actor inputs.

## Static card table

Build one versioned table from the exact English card CSV/hash:

- card ID and explicit unknown/padding IDs;
- card category/type, evolution stage and Pokémon type;
- HP, retreat cost and factual numeric attributes;
- attack/skill identifiers and energy-cost composition;
- stable metadata present in the official data.

Use card ID **plus** structured metadata. IDs preserve card-specific effects; metadata enables learning across related cards. Do not parse natural-language card text in v0. Normalize numeric fields by declared constants and retain missing masks.

## Visible entity tokens

One token per visible physical card/entity instance where possible. Deduplicate physical cards by a stable snapshot identity such as `(relative_owner, serial)`; use serial only for identity/reference resolution and never embed its numeric magnitude as a feature:

```text
static:
  card_id, category, stage, type, hp_base, retreat, attacks/skills
dynamic:
  owner, zone, active/bench/index role, damage, hp_remaining,
  status, attached energy/tool counts and types, evolution state,
  visibility/reveal flags, entered/revealed-this-turn
```

Physical instance identity remains an internal equality/reference key for deduplication and option resolution. It is not a numeric model feature; the network sees gathered entity embeddings and explicit source/target relations instead.

Add explicit tokens for important non-card slots/collections only if needed. Entity order must not convey accidental semantics except for roles that truly are ordered. Active and numbered bench positions receive role embeddings; unordered collections use no arbitrary positional embedding.

Derive the true maximum visible entities and field bounds from engine source plus a large observation corpus. Do not silently truncate. If padding is necessary, assert the bound and create an overflow test; alternatively use packed ragged entities.

## Global features

Include factual public/global values:

- acting player, starting seat and turn/phase;
- prizes and public deck/hand/discard counts;
- supporter/stadium/retreat/energy-per-turn flags;
- selection type and factual min/max counts;
- public terminal/board/resource counters;
- previous compound action summary and elapsed selection count;
- missing/unknown masks.

All categorical values and enums need explicit `UNKNOWN` buckets because new values may appear during the competition. Unknowns raise/report in development while remaining representable by the submission fallback path.

## Public event memory

At every engine selection, process **every ordered event** from the one-shot logs plus the actor’s previous action. Never silently truncate a burst. Convert raw records to typed public events such as reveal, draw count, move, attach, damage, knockout and shuffle; use an unknown-event bucket, but do not feed unbounded raw strings. Run a small shared event encoder/GRU over all events (chunk internally if necessary), then feed its final summary into the main public GRU.

Sequence behavior:

1. pool current entity/global/event representation;
2. update the acting player’s GRU state;
3. score the current legal options from that state;
4. record the selected semantic action summary for the next step;
5. update memory even when only one legal action exists;
6. fold forced choices into memory but exclude them from v0 policy and value/GAE loss nodes;
7. maintain separate hidden state for each player and reset both on battle start/error.

## Ragged legal-option batch

Do not use a fixed global action vocabulary or first-64 truncation. Flatten options across a batch:

```text
option_features: [total_options, option_feature_dim]
option_batch_id: [total_options]
option_offsets: [batch + 1]
```

Encode each option using:

- selection and option type;
- source/target role;
- source/target entity encodings gathered from the current entity table;
- card/attack/skill IDs and structured fields;
- player/zone/position;
- counts/numeric parameters and missing masks;
- current autoregressive chosen-set summary.

Use a shared option MLP and a state–option interaction (dot/bilinear plus small MLP) to produce one logit per option. Apply segmented masked softmax over each request. Store original engine index outside model input solely to map the chosen semantic option back.

Minimum resolver coverage includes:

- `CARD`: state area/index/player plus selection-local deck/looking lists;
- `TOOL_CARD`, `ENERGY_CARD`, `ENERGY`: Pokémon and attachment index;
- `PLAY`: own-hand entity;
- `ATTACH`, `EVOLVE`: source plus in-play target;
- `ABILITY`, `DISCARD`: referenced in-play entity;
- `ATTACK`: active Pokémon plus attack identity;
- `SKILL`: card ID/serial resolution, plus an explicit non-card sentinel when `cardId=0` denotes special-condition or skill ordering rather than a physical card;
- number, yes/no, retreat, end and condition options with no entity reference.

Pseudo/non-card areas and references to player, temporary or special roles must resolve to typed sentinel option/entity representations, never to a failed card lookup or an arbitrary real card. Preserve missing masks so these sentinels are distinguishable from unknown corrupted data.

## Ordered autoregressive multi-select

For one engine request:

1. encode state/entities once;
2. initialize a small selection GRU/MLP state from the public policy state;
3. score remaining options and STOP if legal;
4. choose/sample one;
5. append its semantic identity, remove it and update selection state;
6. repeat until STOP or maximum count;
7. submit the complete ordered list in one native call.

Do not advance the main public GRU during decoder sub-selections: the engine observation has not changed. Only the separate decoder prefix state changes.

Classify the whole request as forced only when exactly one legal ordered submitted list exists. A raw single-option request can still have STOP as a second compound action; a select-all request can still have multiple legal orderings. Only an individual decoder substep with one valid continuation contributes zero substep log-probability.

PPO treats this as one compound action:

```text
logp_compound = sum(logp_subchoice)
entropy_compound = mean(entropy_subchoice / log(valid_count_subchoice))
```

Use one PPO probability ratio and one advantage for the whole compound action; never apply the same advantage separately to each item, which would overweight long selections. Handle one-valid-option entropy safely as zero. Store every subchoice mask/identity so the learner can recompute the exact distribution. Cache the expensive entity encoder within the compound action.

## Option-order robustness

v0 rules:

- do not feed original option-list index;
- randomly permute options during training and map results back;
- permutation seed is recorded in the rollout;
- evaluate with both native and permuted orders;
- maintain a cheap engine-order baseline only as a regression reference.

The permutation test is exact up to declared floating tolerance: permute options, remap logits to semantic order and require equality. Also require the chosen semantic action and engine-index round trip to match.

If a later controlled ablation finds stable useful ordering, add a coarse/order feature only with held-out engine-version tests. Never let it replace semantic resolution.

## Recommended v0 network

Starting point, adjusted only after measured memory/latency/learning evidence:

| Component | Initial size |
|---|---:|
| Card ID embedding | 96 |
| Other categorical embeddings | 8–32 each |
| Entity model width | 128 |
| Entity attention | 2 blocks, 4 heads |
| Feed-forward width | 256 |
| Global/event projection | 128 |
| Public GRU | 160 hidden units |
| Option embedding | 128 |
| Selection autoregression | 64–96 hidden units |
| Actor/critic heads | small 2-layer MLPs |

Target 0.8–1.2M parameters. CI warns and requires an explicit architecture decision above 1.2M, and fails at `>=2,000,000` trainable parameters. Report embeddings separately but include them in the hard total.

Use LayerNorm and orthogonal/sensible initialization; avoid dropout in recurrent PPO v0. Share actor/critic state encoder initially. The value head returns scalar expected terminal outcome.

## Inference modes

Training uses masked categorical sampling. Local serious evaluation and submission normally use deterministic argmax unless a pre-declared stochastic-policy ablation wins. Forced choices bypass sampling but still update recurrence.

The checkpoint contains:

- architecture/config version;
- card-table and engine hashes;
- canonical deck hash plus exact `deck.csv` SHA-256;
- model/optimizer state;
- observation/action schema versions;
- training counters and policy version;
- league provenance.

Reject mismatched card, deck or schema hashes by default.

## Required tests and Gate G2

- observation contains no opponent-hidden/full-state fields;
- metadata table matches exact card CSV hash and handles unknown IDs;
- entity packing has no silent truncation;
- all engine option enum/field combinations in the corpus resolve, including generated `SKILL cardId=0` and pseudo-area/player/temp sentinel fixtures;
- ragged softmax sums to one per non-forced request;
- masks produce exactly zero invalid probability;
- permutation equivalence and mapping-back property tests;
- ordered multi-select uniqueness/min/max/STOP tests;
- compound log-probability recomputes identically in actor and learner;
- two-player hidden states never cross and reset correctly;
- compound-action forced-classification tests cover optional STOP, order-sensitive select-all and one-valid-continuation decoder steps;
- truly forced actions change hidden state but create zero v0 policy/value/GAE loss;
- CPU/GPU forward and checkpoint round-trip within numerical tolerance;
- gradient reaches card/entity, recurrence and option encoder;
- trainable parameters <2M;
- 10,000 complete neural-policy games with zero structural invalids;
- p50/p95/p99 inference and encoding time reported for batch 1 and training batch sizes.

Do not optimize or quantize until correctness tests pass.
