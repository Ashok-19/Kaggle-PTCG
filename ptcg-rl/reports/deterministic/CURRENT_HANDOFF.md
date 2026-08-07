# Current Deterministic Handoff

Status: `PHASE_A_FOUNDATION_PASS_ROUTE_SEMANTICS_PARTIAL`

## Checkpoint

- Branch: `main`
- Audited HEAD: `59b91d30852f8b84078aa6928dca6edcc1eb7fb3`
- Closeout report: `reports/deterministic/phase-a-foundation-closeout-v1.json`
- Prior owned audit commit: `883f9d6d47736cdf744def7238e6a0a633131097`
- Frozen pre-work reference: `56a88794bf27ee63a95adfb7b29ce34808ca8ed4`
- Frozen pre-work dirty snapshot: 406 entries / 38145 bytes / SHA-256 prefix `464030...`
- Independent-review status snapshot, recomputed after the Phase 0 draft was authored (not a frozen pre-authorship fact): 403 expanded porcelain entries / 38098 bytes / SHA-256 `74b249bb5ebdf41845f09a6e99269a70ad3b289d1e76ed628f73194aa2ffb0b6`
- This closeout owns exactly `reports/deterministic/phase-a-foundation-closeout-v1.json` and this file. Existing source, private assets, and unrelated dirty files remain unchanged.
- Kaggle runs for this closeout: none. No Kaggle submission, external mutation, training launch, deck freeze, private-asset mutation, or production source change occurred.

## Phase A Foundation Closeout

The independent closeout separates three claims. The public-state/deck-profile
foundation is `PASS`; the native semantic boundary and mechanical canary are
`PASS`; route-specific card semantics are `PARTIAL`. Generic Phase B boundary
integration is not blocked by this closeout, but card-specific production rules
must not rely on any `PARTIAL` route semantics.

The actual native `mega-abomasnow-ex` deck is 60 cards with 9 distinct IDs and
matches the numeric fixture order exactly. Rebuilding `private/g2/card-table-v1.json`
from the official CSV and native catalog reproduced the stored semantic hash
`7aa6384644c5dbc22fe6b7e1e84bf3d274bd35e0ff0b0ab9c9f3bf2e1141f8a0` with 1,267
cards, 1,556 attacks, and 2,022 CSV rows. The resulting profile hash is
`cb438f9e2083e53f93ed3df6bf8555d95acf6487b421ae194d2e2963ce220ce7`.

The v2 native canary completed `8/8` games: four against `iono` and four
against the `mega-abomasnow-ex` mirror, with candidate seats `4/4`. It recorded
739 requests, 7,754 public log events, 6,852 face-down slots, 31,469 public
reveal entities, eight terminal-first checks, eight stale terminal selections
observed and zero fail-closed counters. These are mechanical diagnostics only;
terminal results are not policy-strength evidence.

### Route Status Matrix

`PASS`: Carmine, Lillie's Determination, Ultra Ball, Precious Trolley, and
Snover evolution. `PARTIAL`: Kyogre Riptide, Kyogre Swirling Waves, Surfing
Beach, Hammer-lanche, and Frost Barrier. Exact proof counts and asset/source
hashes are retained in `phase-a-foundation-closeout-v1.json`.

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

The retained report `phase-a-native-semantics-v2.json` is `SUCCEEDED` with
decision `PASS_WITH_ROUTE_STATUS_MATRIX`. It completed exactly eight native
games under the configured eight-game/20,000-request/180-second limits, with
four `iono` games and four Mega Abomasnow mirror games and balanced candidate
seats. It recorded zero semantic, invalid-action, option-bound, hidden-hand,
unknown-card, timeout, native-failure, fallback, request-cap, public-delta, or
manual-randomness-control failures. Terminal-first checks observed and ignored
stale terminal selection data; all native option lists were checked without
truncation, and optional and multi-select requests were exercised.

The report is hash-bound to the configured card data, card table, engine,
wrapper/API, both baseline decks and both loaded baseline modules. The runner
verifies at runtime that policy bytes and receipt deck hashes match the
configured assets. Output is aggregate-only and contains no absolute paths or
raw native observations. Route status is PASS for Carmine, Lillie's
Determination, Ultra Ball, Precious Trolley, and Snover evolution; it is
PARTIAL for Riptide, Swirling Waves, Surfing Beach, Hammer-lanche, and Frost
Barrier. These route statuses are not policy-strength evidence.

## Active KB IDs

Interface invariants: `DR-001`, `DR-002`, `DR-003`, `DR-022`, `DR-023`, `DR-024`,
`DR-025`, `DR-029`, `DR-030`, `DR-031`, `DR-032`, `DR-033`, `DR-035`, `DR-036`.
Initial route substrate: `STR-001` through `STR-010`, `STR-013`, `STR-014`, `STR-015`,
`STR-016`, `STR-019`, `STR-020`; search features `SF-001` through `SF-010`,
`SF-012`, `SF-013`, `SF-016`; unresolved contradictions `CON-001`, `CON-002`,
`CON-004`; first matchup hypotheses `MU-001` through `MU-004` and
`MUP-001` through `MUP-012`.

## Tests and Evidence

KB validation PASS was rerun immediately before authorship with the
repository-local `data/cache/uv` cache. The lead full-suite result at the
audited HEAD is `512 passed, 1 failed in 27.99s`. The lone failure is
pre-existing dirty-worktree drift at `tests/g3/test_competence_plan_report.py:149`
(expects DEC-028; dirty `reports/gates/g3b.json` reports DEC-047). Do not edit
unrelated files to make that test green.

The top-20 timing artifact scanned 14,182 replays; score versus median call time
was `0.0219765`, supporting fast deterministic defaults with selective expensive
branches. Direct terminal-search results with manual coin handling are invalid
and must never be cited as strength evidence.

Phase A focused deterministic checks independently passed (`41 passed in
0.35s`), and the scoped Ruff check passed. The known failure was independently
rerun in isolation (`1 failed in 0.04s`) and remains unrelated to this closeout;
no unrelated file was edited. KB validation remains `PASS` with the documented
12 open/in-review/blocked P0/P1 questions and 3 unresolved contradictions.

## Exact Assets and Deck Labels

The first research harness is exact `mega-abomasnow-ex`; other exact native
anchors are `mega-lucario-ex`, `dragapult-ex`, and `iono`. Their deck hashes,
official card-data hash, native library hash, card-table hash, and checkpoint
hash are recorded without private paths in the architecture report and JSON.

## Exact Next Task

1. Add the smallest exact native public-transition fixtures needed to cover
   Riptide, Swirling Waves, Surfing Beach, Hammer-lanche, and Frost Barrier,
   without converting metadata into executable effect assumptions.
2. Preserve the native canary's public/private, terminal-first, complete-option,
   no-manual-randomness, exact-hash, fail-closed, and sanitized-output
   boundaries in every follow-on transition test.
3. Keep PARTIAL route semantics out of card-specific production rules. Generic
   Phase B boundary integration is not blocked, but deterministic policy
   strength, deck selection, deck freeze, external training, and submissions
   still require independent natural-seat outcome evidence.
