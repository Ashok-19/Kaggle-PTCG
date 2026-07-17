# 03 — Engine Contract and Tests

## Known constraints to re-verify locally

The supplied package audit found these behaviors. Treat them as hypotheses until the local agent reproduces them against the user’s exact package hash.

1. The Python/native wrapper owns one global battle pointer. Use **one active battle per OS process**.
2. The engine normally seeds from nondeterministic system entropy; there is no ordinary user seed hook. Do not claim paired-seed evaluation.
3. Terminal observations may retain stale selection fields. Check `current.result` before reading or acting on `select`.
4. Battle logs are consumptive. Call the data/log getter once per engine transition and route the returned object to all consumers.
5. Log bursts can exceed 200 entries. Do not use a fixed small log buffer in Python.
6. Options contain positional references into current zones and selection-local lists. Resolve them against the **same immutable observation snapshot**.
7. `selectContext` is not reliable enough for dispatch. Dispatch primarily by selection type, option type and present fields; retain context only as an input feature/debug label.
8. A multi-select engine action is one ordered list submitted in one call. Internal neural autoregression must return one final valid list.
9. Order can be strategically/semantically meaningful, including skill-order contexts.
10. Each player needs separate recurrent memory. Reset both at the initial deck request (`select=None`, `current=None`) and on every new battle/error boundary.
11. Face-down setup can make the current state insufficient to identify an earlier own selection; previous action/recurrent memory must retain it.
12. Visualization may expose full state and is forbidden in training/inference hot paths.

## Adapter layers

Keep four layers distinct:

1. **Native transport:** `ctypes`/library loading and exact ABI calls.
2. **Battle lifecycle:** start, one selection, retrieve state/log once, terminal, close.
3. **Canonical resolver:** convert ephemeral engine references into typed snapshot-local entities/options.
4. **Vector environment:** one worker process per live engine; message protocol contains compact tensors/IDs, not large Python trees.

No model code may call the native wrapper directly.

## Immutable transition contract

For transition `t`, capture one immutable object:

```text
TransitionSnapshot
  battle_id, transition_id, acting_player
  terminal_result | null
  public_observation
  selection_request | null
  legal_options[]
  logs[]
  engine_metadata
```

Resolution, recurrent updates, diagnostics and replay logging all consume this same snapshot. Never call the engine again merely to reconstruct data for another consumer.

## Canonical legal option

Each option should contain typed fields with explicit missing masks:

- selection type and factual context;
- option/operation type;
- source entity reference;
- target entity reference;
- card ID plus an internal snapshot-local instance equality/reference key where visible; never feed the numeric identity magnitude to v0;
- player, zone and position;
- attack/skill/ability ID;
- min/max/count/numeric values;
- choice role (source/target/cost/discard/order/etc.);
- original engine index stored only for mapping/debug, never fed to v0;
- stable semantic fingerprint used in permutation tests.

Position references must be range-checked against the current snapshot. Unknown new enum values fail loudly in development and produce a minimized regression fixture.

Transport every inference request with `(episode_uuid, player, policy_id, selection_seq)`. Reject stale/out-of-order requests, cache the exact response for duplicate retries so recurrence updates once, and require reset acknowledgement before reusing an environment ID.

## Multi-select legality

Given minimum `m`, maximum `M`, current chosen sequence `C` and remaining options `R`:

- choose only from the currently legal remaining set;
- remove chosen identity without replacement;
- enable STOP only when `|C| >= m`;
- force termination when `|C| == M`;
- preserve chosen order;
- validate final list using the engine request before native submission;
- sum sub-action log-probabilities for the PPO compound action;
- retain sub-action masks and decoder states for exact log-probability replay.

Do not enumerate all combinations unless a later measured special-case implementation proves bounded and faster.

## Development and submission behavior

Development mode:

- any invalid reference, impossible count, unknown enum, recurrent mismatch or native exception aborts the episode;
- serialize a redacted failure capsule containing engine/package hash, snapshot, selected semantic action, hidden-state metadata and stack trace;
- minimize and add it to regression tests.

Submission mode:

- increment a persistent in-process error counter/log;
- return a deterministic, always-legal fallback derived from the current legal list;
- never attempt network access or retry loops;
- do not hide fallback use from local validation metrics.

## Required tests

### Unit tests

- all enum/JSON parsing and explicit unknown behavior;
- terminal-before-select branching;
- one-shot log fan-out;
- every positional reference resolver;
- option semantic fingerprints;
- min/max/STOP rules;
- compound-action forced classification, including optional STOP and order-sensitive select-all cases;
- ordered multi-select and no replacement;
- deck-request reset and two-player hidden-state isolation;
- fallback always returns a legal correctly shaped selection.

### Property/fuzz tests

- for arbitrary legal engine requests, generated random selection satisfies count, type, range and uniqueness constraints;
- option permutations preserve the semantic option multiset and selected mapping;
- encode/decode round trips preserve all decision-relevant fields;
- every complete game reaches terminal or a declared engine turn/time cap without Python invalid action;
- logs can be empty or arbitrarily bursty without loss/truncation.

### Integration tests

- compile/load the C++20 shared object on Ubuntu 22.04;
- exercise shipped and locally compiled libraries with the same invariant/test distributions; because engine randomness is nondeterministic, compare ABI, legal/terminal invariants, completion/error rates and distributional summaries—not exact trajectories;
- all four official rule agents can start and finish games;
- random/random, rule/random and rule/rule matrices;
- multiprocessing with 1/2/4/8 workers and forced worker restarts;
- terminal cleanup and immediate next-battle reset.

### Regression corpus

Store small, license-safe serialized API observations if permitted by competition terms; otherwise store generators or hashes plus local ignored fixtures. Include:

- optional empty selection;
- single forced option;
- ordered skill selection;
- max-count multi-select;
- selection-local deck/looking reference;
- `SKILL cardId=0` and pseudo-area/player/temp sentinel references;
- face-down setup;
- terminal snapshot with stale selection;
- >200 log burst;
- every observed selection/option enum pair.

## Benchmarks and gates

Measure separately:

1. raw native selection operations/s;
2. canonical resolution/encoding operations/s;
3. neural-policy decisions/s;
4. complete games/s;
5. memory slope and peak RSS;
6. queue wait and inference batch utilization.

Reference audit values on a different host were about 9.5–10.3k raw engine selection calls/s in one process, roughly 67k in a short eight-process smoke, and about 3.5k engine selection calls/s for rule-agent games. These are **not** training-sample rates or acceptance thresholds for the user’s machine; report measured local values and relative overhead.

Acceptance requirements:

- 1,000,000 legal selections with zero adapter invalids;
- 10,000 complete games with zero unexplained native/Python failures;
- encoded throughput at least 70% of raw throughput or a profile explaining the gap;
- six-hour soak with RSS slope confidence interval and no unbounded growth;
- worker death is detected, episode marked, diagnostics retained and replacement bounded;
- no engine/library call from more than one battle in the same process.

If native failures remain, isolate exact reproducibility and engine-versus-wrapper ownership before training. Do not mask them with the submission fallback during development.
