# CABT Native Contract V2

This is the active G1R contract. The former V1 document and G1 report remain
historical evidence. Machine-readable claims and source locations are in
`contracts/native_inventory.v2.json`.

## Episode And Request Identity

One live battle owns one native pointer. Every inference request carries
`(episode_uuid, player, policy_id, selection_seq, request_id)`. `selection_seq` is
monotonic across the episode; the recurrent owner is separate for each player/policy.
Exact duplicate requests return the cached response without a second recurrence update.
Stale and out-of-order requests fail. Start/deck, terminal, error, and worker replacement
are reset boundaries.

`current.result == -1` is ongoing. Results `0`, `1`, and `2` are terminal. Terminal is
decided before `select`, `select.deck`, or any other selection-local field is read.

## Public Observation

Only actor-facing JSON is accepted. A non-null opponent hand fails closed. Face-down
active/prize slots are represented by masked slot entities without card identity or
serial. Visible cards retain engine serials for semantic reference resolution. Search,
visualizer, and engine-internal state are excluded.

The numeric view is ragged and masked. Every public semantic field has a checked encoding
location or a versioned derivation/provenance rationale in the schema export. Raw option
position is transport metadata and is deliberately not a model feature. No legal option
or visible entity is silently truncated.

## Semantic Options And Compound Actions

Unknown enums, missing type-required fields, unexpected type fields, impossible positions,
and unresolved physical references fail closed. Each option has a canonical source kind,
source reference, target kind, target reference, and choice role. Selection-local deck and
looking cards, skill-zero, player/pseudo/temporary sentinels, face-down slots, ordered skill
choices, and attached-card owner/index semantics have generated regressions.

A multi-select request is one compound action. Options are chosen without replacement.
`STOP` is a real decoder token only when `chosen_count >= minCount` and
`chosen_count < maxCount`. Every option/STOP substep retains the exact mask, chosen prefix,
normalized reference distribution, token, semantic fingerprint, original index, and
log-probability. The compound log-probability is the exact sum. Forced outcomes stay in the
recurrent sequence with `policy_loss_mask = 0`.

Immediately before native dispatch, one validator rechecks schema, episode, player,
sequence, request, count, integer/range, uniqueness, availability, permutation, trace,
STOP, loss-mask, and joint-log-probability invariants against the unpermuted request.

## Failure And Evidence Modes

Development mode fails and retains a bounded redacted reproduction capsule. Submission
mode uses one deterministic legal fallback for policy/output failures, records bounded
diagnostics, increments `fallback_actions`, and makes the run non-promotable. Native state
failures are classified rather than guessed around.

Run manifests hash the exact resolved engine library, wrappers, card data, deck, and source
tree. They include actual Git commit/dirty digest, command, strict limits, UTC/platform, a
unique run ID, immutable output, and a sidecar seal. Generated reports, run artifacts,
bytecode, and caches do not affect the source hash.

## Guarantees And Unknowns

Two players, 60-card decks, one active slot, bench default five/hard maximum eight, six
initial prizes, and seven initial hand cards are source guarantees. Legal-option count,
event burst length, and total selection-local visible entities have no declared global
bound. Observed maxima remain observations. The binding exposes no engine semantic version,
public phase, or documented `BattleStart.errorType` mapping.

