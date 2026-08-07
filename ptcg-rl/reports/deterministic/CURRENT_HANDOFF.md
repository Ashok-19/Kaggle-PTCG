# Current Deterministic Handoff

Status: `PHASE_0_ASSIMILATION_COMPLETE_NOT_IMPLEMENTED`

## Checkpoint

- Branch: `main`
- Last commit before this owned milestone: `fef015f4c7be47cbd8c9c996d0f473da01ccaeb5`
- Owned audit content commit: `883f9d6d47736cdf744def7238e6a0a633131097`
- Frozen pre-work reference: `56a88794bf27ee63a95adfb7b29ce34808ca8ed4`
- Frozen pre-work dirty snapshot: 406 entries / 38145 bytes / SHA-256 prefix `464030...`
- Independent-review status snapshot, recomputed after the Phase 0 draft was authored (not a frozen pre-authorship fact): 403 expanded porcelain entries / 38098 bytes / SHA-256 `74b249bb5ebdf41845f09a6e99269a70ad3b289d1e76ed628f73194aa2ffb0b6`
- Owned paths in this milestone: `reports/deterministic/deterministic-gold-architecture-v1.md`, `reports/deterministic/prior-experiment-evidence-v1.json`, and this file. The audit content is committed above; this handoff update records the post-review state.
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

## Exact Assets and Deck Labels

The first research harness is exact `mega-abomasnow-ex`; other exact native
anchors are `mega-lucario-ex`, `dragapult-ex`, and `iono`. Their deck hashes,
official card-data hash, native library hash, card-table hash, and checkpoint
hash are recorded without private paths in the architecture report and JSON.

## Exact Next Task

1. Independently review the three owned Phase 0 files and the JSON recalculations.
2. Re-run `UV_CACHE_DIR=/tmp/ptcg-uv-cache uv run python knowledge_base/validate_db.py`
   and the exact route/belief/search/matchup queries before Phase A changes.
3. Create semantic/state regression fixtures for Mega Abomasnow route-critical
   cards and transient/public CABT states; add no search or BC authority.
4. Implement only the smallest new public-state foundation under
   `src/ptcg_rl/deterministic/`, preserving the G1/G2 action validator and all
   private baseline/assets.
5. Close the Phase A canary with raw evidence before any tournament or deck
   decision. Keep all external training, submissions, and deck freeze blocked.
