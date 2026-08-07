# Deterministic Gold Architecture and Evidence Audit v1

Status: `PHASE_0_ASSIMILATION_COMPLETE_NOT_IMPLEMENTED`

This is the tracked Phase 0 boundary for the deterministic/search CABT agent. It
is an evidence audit and architecture contract, not a claim of policy strength,
deck freeze, production readiness, or gold-level performance.

## Provenance and Worktree Boundary

- Authoritative specification: `.chatgpt/codex-runs/2026-08-07T193809Z-build-gold-deterministic-cabt-agent/PROMPT.md`.
- The current strategic directive overrides stale PPO-first sequencing: build one
  exact-deck deterministic strategic planner first, then exact card/deck rules,
  route/prize/resource/threat reasoning, matchup policies, public belief, and
  only measured selective search. Full PPO/self-play is parked. The completed BC
  model is an advisor/prior experiment only.
- Frozen pre-work reference supplied by the Phase 0 handoff: HEAD
  `56a88794bf27ee63a95adfb7b29ce34808ca8ed4`; dirty snapshot `406` entries,
  `38145` bytes, SHA-256 prefix `464030...`.
- Current repository at authorship: branch `main`, HEAD
  `fef015f4c7be47cbd8c9c996d0f473da01ccaeb5`, the validated KB-support commit.
  An independent-review status snapshot, recomputed after the Phase 0 draft was
  authored and therefore not a frozen pre-authorship fact, was `403` expanded
  porcelain entries / `38098` bytes, SHA-256
  `74b249bb5ebdf41845f09a6e99269a70ad3b289d1e76ed628f73194aa2ffb0b6`.
  This differs from the frozen pre-work snapshot because other work landed after
  the reference capture; neither snapshot is a reason to clean or rewrite the
  worktree.
- This milestone owns only `reports/deterministic/deterministic-gold-architecture-v1.md`,
  `reports/deterministic/prior-experiment-evidence-v1.json`, and
  `reports/deterministic/CURRENT_HANDOFF.md`. No production source, private
  asset, existing dirty file, external service, Kaggle submission, or staged
  file was touched.
- The complete pre-existing dirty inventory remains represented by its frozen
  status count/hash rather than copied into a tracked file. All paths reported
  before these three files are pre-existing; owned paths are exactly the three
  named above.

## Knowledge-Base Assimilation

The read-only SQLite database was revalidated immediately before this audit and
the relevant FTS/table queries were rerun. The default `uv` cache was read-only,
so the equivalent command used a temporary cache directory:

```text
UV_CACHE_DIR=/tmp/ptcg-uv-cache uv run python knowledge_base/validate_db.py
UV_CACHE_DIR=/tmp/ptcg-uv-cache uv run python knowledge_base/query_db.py stats
UV_CACHE_DIR=/tmp/ptcg-uv-cache uv run python knowledge_base/query_db.py unresolved
UV_CACHE_DIR=/tmp/ptcg-uv-cache uv run python knowledge_base/query_db.py rules
UV_CACHE_DIR=/tmp/ptcg-uv-cache uv run python knowledge_base/query_db.py search "route attacker resource"
UV_CACHE_DIR=/tmp/ptcg-uv-cache uv run python knowledge_base/query_db.py search "belief hidden without replacement"
UV_CACHE_DIR=/tmp/ptcg-uv-cache uv run python knowledge_base/query_db.py search "search beam PUCT option"
UV_CACHE_DIR=/tmp/ptcg-uv-cache uv run python knowledge_base/query_db.py search "anti-pattern immediate prize"
UV_CACHE_DIR=/tmp/ptcg-uv-cache uv run python knowledge_base/query_db.py matchup "Mega Abomasnow" "Dragapult"
UV_CACHE_DIR=/tmp/ptcg-uv-cache uv run python knowledge_base/query_db.py matchup "Mega Abomasnow" "Mega Lucario"
UV_CACHE_DIR=/tmp/ptcg-uv-cache uv run python knowledge_base/query_db.py matchup "Mega Abomasnow" "Iono"
```

Validation result: `PASS`, with 56 sources (A=26, B=14, C=16), 62 claims,
20 strategies, 36 decision rules, 14 anti-patterns, 16 search features,
17 archetypes, 49 cards, 12 matchups, 20 matchup plans, 10 replay patterns,
6 contradictions, and 15 research questions. Warnings remain for 3 unresolved
contradictions and 12 open/in-review/blocked P0/P1 questions; these are not
silently treated as facts.

## Stale Historical Framing

The repository's older PPO-first sequencing and the database's historical
search-competence framing remain useful provenance, but the current prompt
overrides that strategy order only. Engine legality, public-information,
replay-firewall, provenance, reliability, and outcome-evaluation controls remain
binding. `DR-034` is treated as a historical guard against weak search leaves,
not as a ban on the current selective-search hypothesis; old status/gate text is
not evidence of deterministic policy strength.

The strongest interface and evidence rules in play are:

- `DR-001`, `DR-002`, `DR-003`, `DR-022`, `DR-023`, `DR-024`, `DR-025`,
  `DR-029`, `DR-030`, `DR-031`, `DR-032`, `DR-033`, `DR-035`, `DR-036`:
  terminal-first handling, complete current legal options, exact deck request,
  public-only information, legal without-replacement worlds, CABT semantics,
  version-bound evidence, natural-seat outcome evaluation, exact IDs, and
  non-causal replay/timing interpretation. These are `VERY_HIGH` except
  `DR-030`, which is `HIGH`.
- `STR-001` through `STR-010`, `STR-013`, `STR-014`, `STR-015`, `STR-016`, `STR-019`,
  and `STR-020` are the initial high-confidence route, ledger, sequencing,
  exact-deck, legal-scoring, provenance, and outcome-evaluation substrate.
  `STR-011`/`STR-012` are `MEDIUM`; `STR-017` is `MEDIUM`; `STR-018`
  selective tactical search is `HYPOTHESIS`.
- Search/evaluator features: `SF-001` prize-map distance, `SF-002` immediate
  KO threat, `SF-003` opponent KO threat, `SF-004` next-attacker readiness,
  `SF-005` backup attacker count, `SF-006` bench liability, `SF-007` gust
  coverage, `SF-008` resource exhaustion, `SF-009` deck-out risk, `SF-010`
  expected outs, `SF-012` turn compression, `SF-013` irreversible commitment,
  and `SF-016` terminal outcome are `HIGH`/`VERY_HIGH`; `SF-011` hidden-state
  sensitivity, `SF-014` information gain, and `SF-015` option-order ablation
  are `MEDIUM`.
- Highest-priority guards are `AP-009` hidden-card certainty, `AP-010` format
  import, `AP-012` teacher rank as proof, and `AP-014` manual randomness
  control (`VERY_HIGH` in the KB); `AP-001` losing Prize trade and `AP-004`
  irreplaceable-resource discard are `HIGH`. `AP-002`, `AP-003`, `AP-005`,
  `AP-007`, `AP-008`, `AP-011`, and `AP-013` remain high/medium guards.

The unresolved contradictions are `CON-001` immediate Prize versus full route,
`CON-002` deck thinning versus opportunity cost, and `CON-004` semantic option
order versus raw generation order. Default resolution is full route/opponent
response, conditional thinning, and semantic scoring with option order isolated
as a version-controlled ablation. `CON-003`, `CON-005`, and `CON-006` are
resolved by CABT semantics, held-out competence evidence, and explicit format
scope respectively.

The P0 questions still blocking claims are `RQ-001` hosted engine/module parity,
`RQ-002` hosted card-universe parity, `RQ-003` hidden opponent distribution,
`RQ-004` Mega Abomasnow routes under native natural deployment, and `RQ-015`
final enforceable runtime/deadline limits. P1 questions `RQ-005` route-feature
ablation, `RQ-006` option-order permutation, `RQ-007` exact card transitions,
`RQ-008` selective-search benefit, `RQ-009` belief benefit, `RQ-010` teacher
transfer (blocked), and `RQ-014` discussion refresh remain open or in review.

## CABT Stack and Non-Negotiable Boundary

The existing stack is the source of the adapter contract: `g1/models.py` and
`g1/actions.py` define observations and compound legal actions; `g1/environment.py`
and `g1/native.py` own engine transitions; `g1/semantic.py` resolves public
option meaning; `g1/rule_baseline.py` and `g1/arena.py` provide native controls;
`g2/card_table.py` binds compact card metadata. The new deterministic package
must call this stack rather than replace or patch official semantics.

The final adapter must preserve these invariants:

1. Check terminal outcome before reading stale selection-local fields.
2. Return the exact 60-card deck only for the deck request.
3. Score every current legal option; never truncate, synthesize a tabletop
   action, or trust a fixed option prefix.
4. Return unique in-range indexes satisfying the exact current type/count
   contract, including ordered multi-select and legal `STOP`.
5. Resolve references against the same current snapshot, retrieve consumptive
   logs once, and keep public/private information boundaries explicit.
6. Keep planner/belief/search state isolated by episode, player, and policy;
   reset at deck/start, terminal, error, and worker replacement boundaries.
7. Development fails loudly; submission mode may use only a deterministic legal
   fallback, and promotable experiments require zero fallback use.
8. Never manually control coins or other engine randomness. Search may model or
   branch on engine-consistent outcomes only.

The extension boundary is a new `src/ptcg_rl/deterministic/` package. It may
consume normalized public observations, the exact card table, and the existing
legal-action validator. It must not modify `g1`, `g2`, the native library, card
data, private baselines, or submission packaging while Phase A is open.

## Exact Anchors and Assets

The four local native controls are exact private anchors, not claims about hidden
meta prevalence:

| label | deck bytes | deck SHA-256 | adapter SHA-256 | native receipt label |
|---|---:|---|---|---|
| `mega-abomasnow-ex` | 248 | `7af2d7e111c084da535b89758730b3fd6cbb7c0543a9444499c5b61efdc8aecd` | `d1ef4a86413b7f548270657385c6d5c3cb114b473082cd04e2a0f1733158482b` | exact native rule anchor |
| `mega-lucario-ex` | 305 | `406e2e9bd6ae82b8008b16ee64ffcbb58e4a50cd6bc36e33ae655456c6b9afee` | `ab8563b67b88b3666c2ff9c308505085a84fdac676c194c5b484d8544478c3b2` | exact native rule anchor |
| `dragapult-ex` | 321 | `30c8c7365c75f38fd6e7e1d8543c42ce7055ed6fd1c6e9eb244e44484b78e724` | `ef8936859fd215e6c704071042e5438d55e2e972b8f1806fb6eddbd03027e0b9` | exact native rule anchor |
| `iono` | 279 | `e36d46c5bcafdef8a5d0e6caeb34dd8db09119c62d8fb67c99e89e7eed39f974` | `9fa360307e0b9ccd4cd8469aad50c93872468c8dfa8ff8ebb6718cacf9faa8fa` | exact native rule anchor |

Asset bindings used for research are: official card-data SHA-256
`a0ea63cf7adcb65d35436ce0eb390de6e2e35654a7c67c065a45f4abaa00f373`, native
library SHA-256 `feafd4046b2f688bdb33a4972c139b78e13e243ab5707ece52c43cf39a34b887`,
card-table file SHA-256 `5fc3a1cf31dd5f4b1b3542fc1baa91fe2b68b772cb5748f50f0f75c9a74f7714`,
card-table semantic hash `7aa6384644c5dbc22fe6b7e1e84bf3d274bd35e0ff0b0ab9c9f3bf2e1141f8a0`,
and the qualified G2 checkpoint archive SHA-256
`4dfba2adb9f97607cfa5dabadba075236bb7aae51eafab264584e947feae3827`.

The initial exact-deck research harness is Mega Abomasnow. Native constants
identify Kyogre `721`, Snover `722`, Mega Abomasnow ex `723`, Ultra Ball `1121`,
Precious Trolley `1126`, Carmine `1192`, Lillie's Determination `1227`, Surfing
Beach `1262`, and Basic Water Energy `3`. These labels are implementation
targets for local semantic canaries, not permission to infer effects from memory.

## Strongest Control and Prior Evidence

The strongest completed deterministic control is the native `mega-lucario-ex`
rule policy in `terminal-macro-all-anchor-confirmation-v1`: 64 games, natural
private-engine screen, four anchors, 42 wins / 22 losses / 0 draws, outcome
score `42/64 = 0.65625`, and zero search overrides. The retained scratch JSON
does not expose a complete gate-style reliability counter set; completed
fail-fast harness execution is not a substitute for a future reliability gate.
Per opponent anchor: Dragapult `11-5`, Iono `14-2`, Mega Abomasnow `9-7`, and
Mega Lucario mirror `8-8`. A smaller 16-game full-corpus screen produced rule
`12-4` (`0.75`); it is a useful diagnostic but not stronger promotion evidence.

The recurrent BC run completed 284 train episodes, 32 validation episodes, four
epochs, 840 optimizer steps, and selected epoch 4. Validation NLL decreased
monotonically `1.832771 -> 1.542337 -> 1.444911 -> 1.408741 -> 1.374653`.
It read zero test replay bodies and did not promote or submit a model. Native
head-to-head was rule `11-5`, pure BC `2-14`, and BC-at-MAIN/rule-subselection
`4-12` over 16 games. BC is therefore advisory-only and not decision authority.

Prior search/value branches are closed as follows:

| branch | retained evidence | result and caveat |
|---|---|---|
| mechanical search feasibility | `cabt-search-feasibility-canary-v1` | PASS for state snapshot/branching/edge rejection only; not strength evidence |
| naive one-ply | `hybrid-search-rule-tournament-v1`, `hybrid-search-conservative-sweep-v1` | one-ply-0 `1/16`, one-ply-50 `7/16`; conservative one-ply-200 `12/16` versus small-screen rule `8/16`, not confirmed and not promoted |
| beam search | same sweep reports | `7/16` or `8/16` depending formulation, with roughly `149-169s` search over 16 games; no reliable gain |
| PUCT | rule tournament and Dragapult confirmation | initial PUCT `6/16`; PUCT90 `10/16` versus rule `8/16` in a small sweep, then `10/16` versus rule `11/16` in 16-game Dragapult confirmation; no general promotion |
| static macro heuristic | `macro-heuristic-tournament-v1` | variants ranged `0/8` to `3/8` versus rule `5/8`; reject static leaf tuning |
| terminal macro search | `terminal-macro-all-anchor-confirmation-v1` | terminal8 `28/64`, rule `42/64`; expensive and harmful |
| replay-learned value | `full-corpus-value-oneply-sweep-v1`, learned-value reports | held-out replay outcome-sign accuracy reached about `0.875-1.0`, but best search screens remained below rule (`m050 10/16` versus `12/16`; learned PUCT `8/16` versus `9/16`); leaf ranking is the bottleneck |
| direct terminal search | `direct-terminal-search-tournament-v1` | `39/64` versus rule `30/64`, but `manual_coin: true`; invalid/non-authoritative and must never be repeated as a strength claim |

The interpretation is not that search is impossible. It is that raw search,
static value prediction, or a replay-derived leaf signal is not a trustworthy
decision evaluator yet. Search remains a later, selective, route-grounded
hypothesis.

## Timing and Runtime Implication

The top-20 timing scan processed 14,182 replays and 5,248 matched files. Score
versus median call time correlation was only `0.0219765`; rank versus median call
time was about `-0.1865`. Representative median MAIN times were LiamK `~63ms`,
flg `~82ms`, matsurih `~39ms` with median replay p90 call time `~7.9s`, Marshall Maximizer
`~0.386s`, and Petit Canard `~0.922s`. The measured implication is a fast
deterministic default with expensive work only on hard strategic states. Timing
does not reveal an opponent algorithm.

## Modular Architecture and Phase A Hypothesis

The proposed boundaries are deliberately small and testable; this is a
future-facing architecture sketch, not Phase A authority:

```text
deterministic/
  state.py          public normalized state and stable/transient semantics
  deck_profile.py   one exact deck, card roles, thresholds, and hashes
  ledger.py         own resources, public opponent counts, Prize/inaccessible copies
  threats.py        immediate/next-turn threat and response calculations
  prize_route.py    complete target/attacker route candidates
  attackers.py      current/next/backup readiness and continuity
  sequencing.py     information-first and irreversible-action ordering
  resources.py      attachment/search/supporter/recovery preservation
  bench.py          role/liability/capacity decisions
  gust.py           Boss/gust route conversion
  belief.py         deterministic public-only probabilistic worlds
  matchups.py       only experimentally promoted matchup rules
  planner.py        lexicographic objectives and feature diagnostics
  search.py         later selective tactical search at stable boundaries
  policy.py         final legal adapter and deterministic fallback
  diagnostics.py    bounded, sanitized decision explanations
```

Phase A implementation authority is limited to the public normalized state,
exact Mega Abomasnow deck profile, and semantic/state fixtures. The later route,
attacker, ledger, threat, sequencing, gust, belief, matchup, and search modules
are hypotheses only until their own experiments. The Phase A hypothesis is that
this foundation can support later route decisions without modifying engine
semantics or adding search. The first falsifiable work order is semantic state
fixtures and exact card-transition canaries, followed by isolated route,
attacker, ledger, sequencing, and gust ablations against the frozen native rule
control. No feature becomes production authority from a unit test or tiny
screen; each requires zero failures, natural-seat evaluation, per-matchup
reporting, and scaled confirmation.

## Promotion, Rejection, and Evaluation Contract

Every feature follows `source/KB evidence -> exact CABT semantics -> explicit
hypothesis -> local canary -> 16-32 game screen -> targeted 64-128 game screen
-> scaled confirmation -> promote or reject`. An infrastructure timeout is
inconclusive, not a negative result. A negative result is durable only after
plausible alternatives are tested or the hypothesis is structurally falsified.

Promotion requires complete legal-option handling, zero invalid/post-terminal/
fallback/crash/timeout failures, targeted behavior fixtures, balanced natural
seats, a held-out win/draw/loss improvement with uncertainty, no unexplained
catastrophic regression, and exact code/engine/card/deck hashes. Promotion order
is reliability, catastrophic-matchup floors, meta-weighted expected match score
`(wins + 0.5 * draws) / games`, then runtime/package constraints. Prize margin,
timing, raw search confidence, replay rank, and tiny screens never substitute
for game outcomes.

Deck selection remains an experiment. Screen Mega Abomasnow, Mega Lucario,
Dragapult, Iono, and any exact-semantic candidate under identical reliability,
natural-seat, and outcome criteria. Do not freeze a deck or submit without the
explicit user decision required by the repository policy.

## Risks and P0 Questions

- Hosted engine/card/module parity and final runtime limits are unresolved
  (`RQ-001`, `RQ-002`, `RQ-015`); bind every experiment to actual hashes.
- Matchup plans `MU-001` through `MU-004` are LOW/HYPOTHESIS and must generate
  experiments, not hard-coded authority. `DR-027` and `DR-028` remain LOW.
- Hidden state is public-only and probabilistic; `select.effect`, resolving
  Trainers, setup face-down cards, and transient logs need transition fixtures.
- Option order may correlate with engine generation but is version-sensitive;
  semantic option permutation controls are mandatory.
- Search may improve one matchup while damaging another or violating cumulative
  CPU limits. Search activation and p99 latency must be measured prospectively.
- Card interactions, deck-out, spread, prize modifiers, and random outcomes can
  differ from tabletop assumptions. Native transitions override memory.
- Existing dirty files and a known baseline suite failure must remain untouched.

The pre-existing full-suite baseline supplied for this milestone was
`rtk uv run pytest -q`: 471 passed, 1 failed in 28.55 seconds. The failure is
`tests/g3/test_competence_plan_report.py:149`, where the test expects DEC-028
but the pre-existing dirty `reports/gates/g3b.json` reports DEC-047. It is
unrelated to this audit and is recorded for the next agent; no source or report
was changed to hide it.

## Next Authorized Work

Only after independent review of this audit should Phase A begin: re-query the
KB, add semantic/state regression fixtures, inspect exact local transitions for
the route-critical Mega Abomasnow cards, and implement the smallest public-state
foundation in a new deterministic package. Do not launch training, submit,
freeze a deck, or promote BC/search authority.
