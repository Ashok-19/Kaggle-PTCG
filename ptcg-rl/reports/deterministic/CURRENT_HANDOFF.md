# Current Deterministic Handoff

Status: `PHASE_A_NATIVE_SEMANTICS_CANARY_SUCCEEDED_WITH_INCONCLUSIVE_ROUTE_COVERAGE`

## Checkpoint

- Branch: `main`
- Last commit before this owned milestone: `fef015f4c7be47cbd8c9c996d0f473da01ccaeb5`
- Owned audit content commit: `883f9d6d47736cdf744def7238e6a0a633131097`
- Frozen pre-work reference: `56a88794bf27ee63a95adfb7b29ce34808ca8ed4`
- Frozen pre-work dirty snapshot: 406 entries / 38145 bytes / SHA-256 prefix `464030...`
- Independent-review status snapshot, recomputed after the Phase 0 draft was authored (not a frozen pre-authorship fact): 403 expanded porcelain entries / 38098 bytes / SHA-256 `74b249bb5ebdf41845f09a6e99269a70ad3b289d1e76ed628f73194aa2ffb0b6`
- The Phase A canary audit owns exactly `configs/deterministic/phase_a_native_semantics_v1.json`, `scripts/deterministic/phase_a_native_semantics.py`, `tests/deterministic/test_phase_a_native_semantics.py`, `reports/deterministic/phase-a-native-semantics-v1.json`, and this file. Existing Phase 0 content remains unchanged.
- Kaggle runs for this milestone: none. No Kaggle submission, external mutation, training launch, deck freeze, private-asset mutation, or production source change occurred.

## Current Best Candidate and Control

The current strongest proven deterministic control is the exact native
`mega-lucario-ex` rule agent: 42 wins / 22 losses / 0 draws in 64 natural
private-engine games against Dragapult, Iono, Mega Abomasnow, and the Mega
Lucario mirror (`0.65625`). Per-anchor results are `11-5`, `14-2`, `9-7`, and
`8-8`. The retained scratch JSON does not expose a complete gate-style
reliability counter set, so this is not a reliability qualification. The
smaller 16-game rule screen was 12-4 but is not the promotion control. No
deterministic planner feature, search branch, or BC model is promoted.

BC remains an advisor-only experiment: 284 train episodes, 32 validation
episodes, 840 optimizer steps, epoch-4 validation NLL `1.374653`, zero test
replay reads, and native head-to-head rule `11-5` versus pure BC `2-14` and
BC-MAIN/rule-subselections `4-12`.

## Promoted and Rejected

- Promoted: only existing native interface/action invariants and the validated
  KB support at `fef015f4...`; no new deterministic strategy.
- Rejected or not promoted: naive one-ply, broad beam, PUCT as general authority,
  static macro leaves, broad terminal macro search, replay-learned value leaves,
  pure BC, BC hybrid, and manual-coin direct terminal search. Full details and
  artifact hashes are in `prior-experiment-evidence-v1.json`.
- Search feasibility canary is mechanical PASS only. It does not establish
  outcome strength.

## Phase A Native Semantic Canary

The retained report `phase-a-native-semantics-v1.json` is `SUCCEEDED` with
decision `PASS_WITH_INCONCLUSIVE_ROUTE_COVERAGE`. It completed exactly two
native games under the configured two-game/20,000-request/180-second limits,
balanced candidate seat assignment across the two games, and recorded zero
semantic, invalid-action, option-bound, hidden-hand, unknown-card, timeout,
native-failure, fallback, request-cap, or manual-randomness-control failures.
The terminal-first checks observed and ignored stale terminal selection data;
all native option lists were checked without truncation, and optional and
multi-select requests were exercised. The report has no policy-strength or
promotion claim, and the candidate's two-game outcomes are not an evaluation
result.

The report is hash-bound to the configured card data, card table, engine,
wrapper/API, both baseline decks and both loaded baseline modules. The runner
also verifies at runtime that the policy bytes and receipt deck hashes match
the configured assets. Output is aggregate-only and contains no absolute
paths or raw native observations. A fresh independent two-game rerun also
completed with zero fail-closed counters; native engine entropy changed which
route attacks/effects were observed, so those observations are not treated as
deterministic. Route-effect coverage remains explicitly `INCONCLUSIVE` (the
retained report is missing Carmine and Lillie's Determination), and no
route-specific effect is qualified.

## Active KB IDs

Interface invariants: `DR-001`, `DR-002`, `DR-003`, `DR-022`, `DR-023`, `DR-024`,
`DR-025`, `DR-029`, `DR-030`, `DR-031`, `DR-032`, `DR-033`, `DR-035`, `DR-036`.
Initial route substrate: `STR-001` through `STR-010`, `STR-013`, `STR-014`, `STR-015`,
`STR-016`, `STR-019`, `STR-020`; search features `SF-001` through `SF-010`,
`SF-012`, `SF-013`, `SF-016`; unresolved contradictions `CON-001`, `CON-002`,
`CON-004`; first matchup hypotheses `MU-001` through `MU-004` and
`MUP-001` through `MUP-012`.

## Tests and Evidence

KB validation PASS was rerun immediately before authorship. The baseline full
suite was `UV_CACHE_DIR=/tmp/ptcg-uv-cache uv run pytest -q`: 471 passed, 1
failed in 28.28s. The lone
failure is pre-existing dirty-worktree drift at
`tests/g3/test_competence_plan_report.py:149` (expects DEC-028; dirty
`reports/gates/g3b.json` reports DEC-047). Do not edit unrelated files to make
that test green.

The top-20 timing artifact scanned 14,182 replays; score versus median call time
was `0.0219765`, supporting fast deterministic defaults with selective expensive
branches. Direct terminal-search results with manual coin handling are invalid
and must never be cited as strength evidence.

Phase A focused Ruff checks passed, and the canary/config/deck tests passed
(`8 passed`). The full repository suite currently reports `484 passed, 3
failed`: the known unrelated DEC-047 report-drift assertion, plus two
deterministic state-fixture failures from concurrent unowned state-module
changes. Those failures are not part of the native canary paths and were not
silently repaired here. KB validation remains `PASS` with the documented 12
open/in-review/blocked P0/P1 questions and 3 unresolved contradictions.

## Exact Assets and Deck Labels

The first research harness is exact `mega-abomasnow-ex`; other exact native
anchors are `mega-lucario-ex`, `dragapult-ex`, and `iono`. Their deck hashes,
official card-data hash, native library hash, card-table hash, and checkpoint
hash are recorded without private paths in the architecture report and JSON.

## Exact Next Task

1. Add the smallest exact card-transition fixtures needed to cover the
   still-unobserved route-effect cards, without converting metadata into
   executable effect assumptions.
2. Preserve the native canary's public/private, terminal-first, complete-option,
   no-manual-randomness, exact-hash, fail-closed, and sanitized-output
   boundaries in every follow-on transition test.
3. Keep route-effect claims, deterministic policy strength, deck selection,
   deck freeze, external training, and submissions blocked until independent
   natural-seat outcome evidence exists.
