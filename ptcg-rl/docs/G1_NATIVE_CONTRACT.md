# CABT Native Contract V1

This contract is derived from the locally imported official competition package whose
engine library SHA-256 is
`feafd4046b2f688bdb33a4972c139b78e13e243ab5707ece52c43cf39a34b887`.
The machine-readable inventory is `contracts/native_inventory.v1.json`. Official source
and sample files remain ignored and are not redistributed.

## Lifecycle

The wrapper owns one global battle pointer. A process may start one battle from two exact
60-card decks, repeatedly submit one ordered `list[int]`, and finish the battle to release
the pointer. Each submitted integer addresses the original option array for that exact
request. The adapter retrieves one immutable observation after start or selection and never
calls the consumptive log getter again for another consumer.

Evidence: `sample_submission/cg/game.py:19-68`, `sample_submission/cg/sim.py:5-44`,
`ptcg_engine/ptcgProgram 22/Api.h:99-140`, and the official local-battle sample notebook.

## Results and requests

`current.result == -1` is ongoing. Terminal results are winner seat `0`, winner seat `1`,
or draw `2`. Terminal is checked before `select`; any stale terminal selection is ignored.
`current.yourIndex` is the acting player for an ongoing request.

`minCount <= len(selection) <= maxCount`, every index must be in range, and indices must
be unique. Order is preserved. Empty selection is legal exactly when `minCount == 0`.
The engine clamps request maximum to the number of options, but Python validates the
unmodified request before native submission.

Evidence: `sample_submission/cg/api.py:366-409`, `sample_submission/main.py:22-38`,
`ptcg_engine/ptcgProgram 22/State.h:335-367,1735-1778` and
`ptcg_engine/ptcgProgram 22/Api.h:122-140`.

## Visibility

The semantic observation contains only the official actor-facing JSON. The opponent hand
must be `null`; facedown active and prize cards are `null` entries. A non-null opponent hand
is a contract violation rather than data to be silently discarded. The engine-internal
phase and search serialization are not actor features. `search_begin_input`, visualizer
state and full search state are never encoded.

Visible card instances retain card IDs and stable metadata references. Serial numbers are
used only as equality/reference keys and are excluded from numeric features. Card-effect
text is not processed.

Evidence: `sample_submission/cg/api.py:332-445`,
`ptcg_engine/ptcgProgram 22/ToJson.h:95-128,270-299` and
`ptcg_engine/ptcgProgram 22/State.h:280-314`.

## Capacities

Engine guarantees are two players, 60 cards per deck, one active slot, default five and
hard maximum eight bench slots, six prizes, and seven initial hand cards. These values are
from `Core.h` and `PlayerState.h`; they are guarantees, not smoke observations.

Legal options and logs are dynamic `std::vector` values. There is no declared global bound.
V1 therefore uses ragged arrays and preserves every item. Optional development batching
caps raise an overflow error and never truncate.

## Native failures

Selection errors are `4` invalid count, `5` out-of-range index, `6` duplicate index and
`30` broken pointer. The official wrapper collapses `4/5/6` to `IndexError`; the G1 adapter
validates all lengths, uniqueness and membership before submission and emits a bounded,
redacted failure artifact on any failure.

## Explicit unknowns

- The binding exposes no engine semantic-version string; the library hash is the version key.
- No legal-option, event-log or global visible-entity maximum is declared.
- No public phase field exists, so phase is not inferred from one observed game.
- Numeric meanings for `BattleStart.errorType` are not declared by the Python binding.

Observed smoke maxima and unseen enum coverage belong in the G1 run manifest and must not
be promoted to guarantees.
