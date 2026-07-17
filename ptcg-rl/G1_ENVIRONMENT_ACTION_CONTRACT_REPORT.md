# G1 Environment and Action Contract Report

Date: 2026-07-18  
Outcome: **PASS**  
Gate recommendation: **Close G1 and proceed to filtered replay/meta plus quantitative deck discovery.**

## Repository State

- Sole active repository: `https://github.com/Ashok-19/Kaggle-PTCG`
- G1 implementation commit: `35dcd235143bdfe2b498001d301061fab5e5c629`
- Dirty state immediately after that commit: **clean**
- This report is a documentation-only follow-up to that exact implementation commit.
- Training performed locally: **none**

## Components Changed

- `src/ptcg_rl/g1/`: typed V1 records, raw-to-semantic adapter, ragged tensor encoder,
  reversible actions, compound multi-select, explicit episode state machine, native transport,
  legal baselines, smoke runner, schema export and cloud-validation CLI.
- `contracts/native_inventory.v1.json` and `docs/G1_NATIVE_CONTRACT.md`: source-backed
  native inventory and human contract.
- `tests/unit/test_g1_*` and `tests/integration/test_g1_dashboard_ingestion.py`: lifecycle,
  privacy, serialization, permutation, multi-select, overflow, failure and ingestion coverage.
- `scripts/g1_cloud_validate.sh`: frozen, non-interactive contract-only Colab/Kaggle entry.
- `reports/{contracts,runs,gates,events}/`: authoritative hashes, smoke manifest, decision and
  dashboard events.
- Dashboard store/frontend: G1 run ingestion, passed criteria, unknowns and next action.

Core/submission dependencies remain empty. G1 uses the Python standard library; dashboard
dependencies remain isolated in the existing `dashboard` dependency group.

## Native Contract Inventory

Evidence comes from the official ignored package, not guessed API behavior:

- Lifecycle: `battle_start` accepts two 60-card decks, one global battle pointer is active,
  `battle_select(list[int])` submits original option indices, and `battle_finish` releases it.
- Results: `-1` ongoing, `0` player-0 win, `1` player-1 win and `2` draw. Terminal is checked
  before any selection field.
- Acting player: `current.yourIndex`, constrained to seats `0` and `1`.
- Request surface: 11 selection types, 49 contexts, exact `minCount`/`maxCount`, remaining
  damage/energy counters, option list, selection-local deck, context card and effect card.
- Option surface: all 17 official types and all 14 optional fields are preserved semantically.
- Multi-select: ordered unique original indices, inclusive min/max bounds, legal optional
  empty list, STOP after minimum, forced completion at maximum and no replacement.
- Visibility: opponent hand must be `null`; facedown active/prize entries remain unknown.
  Search serialization, visualizer/full state and engine-internal phase are excluded.
- Events: all 24 official log types and fields are retained in order with dynamic length.
- Native errors: `4` invalid count, `5` bad index, `6` duplicate index and `30` broken pointer.
  Python validates all counts, indices and uniqueness before native submission.

Primary locations are `sample_submission/cg/{api.py,game.py,sim.py}`,
`ptcg_engine/ptcgProgram 22/{Core.h,State.h,Api.h,ToJson.h,Export.cpp}` and the official
local-battle sample notebook. Exact line references are recorded in the inventory.

## Contract Versions and Hashes

All records are schema version `1`.

| Contract/artifact | SHA-256 |
|---|---|
| Engine library | `feafd4046b2f688bdb33a4972c139b78e13e243ab5707ece52c43cf39a34b887` |
| Card data | `a0ea63cf7adcb65d35436ce0eb390de6e2e35654a7c67c065a45f4abaa00f373` |
| Native inventory | `55f14ddc39c50afc62b4d8e4a4ad024a84cc2c5b04b6bc1d14c695272d59cbfd` |
| Observation plus ragged tensor schema | `0b1ffde016ee688a41d3313ae781aaadbd6d1d5da4f5853ccdfa6b2ecbc572f6` |
| Legal-option/compound-action schema | `c35f3618ac4c35a847f048a61ad8b669ea5194f8a6f9da77a532697818f207f3` |
| Transition/episode schema | `cc2f2a55ac59095c019e2cdcc3da59e9b88138eb0c567df350d7d06df322f694` |
| Smoke code | `c502400e7a307c9bbe9f34e723d39d727fbb8eeb5b3028fcc3f13a41d7beee80` |
| Smoke resolved config | `470795d9b4ac8a2cf729bd5e47ba3f44870f6e4f320ad05059311d92a01d0ed8` |

The typed records are `EngineObservationV1`, `SelectionRequestV1`, `LegalOptionV1`,
`CompoundActionV1`, `TransitionRecordV1`, `EpisodeSummaryV1`, `SchemaMetadataV1` and
`NumericTensorV1`. Missing values use `None` plus numeric missing masks; numeric zero remains
distinct. Serial and original option positions never enter model features.

## Verification

| Check | Result |
|---|---|
| Ruff | PASS |
| Python suite | 23 passed |
| Frontend unit suite | 2 passed |
| Frontend production build | PASS |
| Playwright desktop/roadmap/mobile | 3 passed |
| Contract inventory/hash validation | PASS |
| Official asset verification | PASS |
| Dashboard rebuild | 17 records, 0 quarantined |
| Staged restricted-path audit | PASS |
| Staged credential-pattern scan | PASS |
| Cloud entry-point local proof | 19 contract tests and 2 native games passed |

Focused regressions cover every required terminal branch, no stale post-terminal selection,
forced recurrent records with `policy_loss_mask=0`, optional empty actions, ordered unique
multi-select, permutation inversion, 70 options without truncation, overflow failure,
semantic/tensor/trajectory round trips, zero-versus-missing masks, schema drift, hidden-hand
rejection, recurrent reset, bounded redacted failures and dashboard ingestion without API
coupling. All official selection/context/option numeric codes receive synthetic structural
coverage.

## Bounded Native Smoke

Command:

```bash
uv run --no-sync ptcg g1 smoke \
  --engine-root private/assets/official/sample_submission/sample_submission \
  --deck private/assets/official/sample_submission/sample_submission/deck.csv \
  --games 50 --request-cap 20000 --wall-seconds 1800 --seed 17 \
  --output reports/runs/g1-native-smoke.json
```

The official engineering deck was used in both seats. Random-legal and deterministic-first-
legal policies alternated player roles.

| Metric | Result |
|---|---:|
| Games started/completed | 50 / 50 |
| Engine requests | 2,219 |
| Meaningful choices | 1,987 |
| Forced recurrent requests | 232 |
| Multi-select requests | 59 |
| Invalid selections | 0 |
| Native failures/crashes | 0 |
| Timeouts | 0 |
| Post-terminal actions | 0 |
| Maximum observed legal options | 52 |
| Maximum observed selected count | 3 |
| Local smoke wall time | 1.593 seconds |
| Local/cloud cost | USD 0 |

Observed selection types were `MAIN`, `CARD`, `ENERGY`, `COUNT` and `YES_NO`. Observed
option types were `NUMBER`, `YES`, `NO`, `CARD`, `ENERGY`, `PLAY`, `ATTACH`, `EVOLVE`,
`RETREAT`, `ATTACK` and `END`.

`ATTACHED_CARD`, `CARD_OR_ATTACHED_CARD`, `SKILL`, selection-level `ATTACK`, selection-level
`EVOLVE`, `SPECIAL_CONDITION`, and option types `TOOL_CARD`, `ENERGY_CARD`, `ABILITY`,
`DISCARD`, `SKILL`, `SPECIAL_CONDITION` are honestly marked `UNSEEN` in live smoke. Their
official field/bound rules are represented and synthetically tested; no live coverage was
fabricated.

## Guaranteed Versus Observed Capacity

Engine guarantees: two players, 60 cards per deck, one active slot, maximum eight bench
slots, six prize slots and seven initial hand cards. Legal options and event logs are dynamic
engine vectors with no declared global maximum. V1 therefore uses ragged arrays. Optional
development capacities raise an explicit overflow failure and never truncate.

The observed maxima of 52 options and three selected indices are coverage facts only, not
batching guarantees.

## Unresolved Questions

- No semantic engine version string is exposed. Impact: non-blocking; engine-library hash is
  the compatibility version.
- `BattleStart.errorType` meanings are not exposed in the Python binding. Impact:
  non-blocking; numeric values remain in bounded local diagnostics.
- No actor-visible phase field exists. Impact: non-blocking and privacy-safe; V1 does not
  infer or encode a phase.
- Rare request/option types were unseen live. Impact: cloud validation should broaden soak
  coverage before PPO, while structural correctness is already tested.

No ambiguity remains that can make current submitted indices incorrect, leak hidden opponent
information or corrupt the native process.

## Cloud Validation

Portable entry point:

```bash
export PTCG_ENGINE_ROOT=/private/path/to/sample_submission
export PTCG_DECK_PATH=/private/path/to/deck.csv
sh scripts/g1_cloud_validate.sh
```

It runs `uv sync --frozen`, contract tests and the same configurable capped smoke. It writes
the same hashes, coverage and failure metrics. Assets and credentials remain external. The
entry point has no training mode and requires the explicit `--contract-only` CLI flag.

## Deviations and Failed Attempts

- Official rule-agent notebook code was not imported into the source package or committed.
  The bounded smoke used the official engineering deck and the two G1 non-learning legal
  baselines in both seats; private notebooks remain ignored.
- Initial Playwright attempts could not bind inside the filesystem sandbox and still expected
  the previous `PLANNED` dashboard state. The isolated test port was moved to `18765`, the
  assertions were updated to the completed G1 state, and the escalated final run passed 3/3.
- Live smoke did not encounter every official enum type; these remain `UNSEEN`, not claimed.
- No PPO, self-play campaign, GPU work, large benchmark or Modal job was started.

## Recommended Next Phase

Close G1. Implement the filtered replay index/filter/download pipeline together with
quantitative deck discovery and replay-metadata dashboard ingestion. Then run the first small
training smoke on Colab/Kaggle. Meaningful self-play and PPO/league training remain on Modal.
