# Current Deterministic Handoff

Status: `B0_UPPER_SCREEN_PASS_ONLY_B1_BLOCKED_B2_FIXTURE_ONLY_B3_FIXTURE_PASS_B4_BLOCKED`

Audited at `2026-08-08T02:48:19Z`. This is an evidence-first snapshot, not a
promotion, deck-freeze, native-launch, Kaggle, medal, or submission claim.

## Authority and Worktree

- Authoritative deterministic specification: `.chatgpt/codex-runs/2026-08-07T193809Z-build-gold-deterministic-cabt-agent/PROMPT.md`; prompt SHA-256 `c7a081e3669077bd1205d06b8bf31d3e3dcf85b18208839af6b811b26045edd6`.
- Branch: `main`.
- Audited HEAD: `a108353ade9ac57cc293a551fa90572fe0e29f07` (`feat: qualify phase B3 resource ledger fixtures`).
- Knowledge database: `knowledge_base/ptcg_gold.sqlite`, SHA-256 `e6c588fa1dbe4c485e6723926ebf051ddb1a228fd75cdcb396a5bf3370cac60f`; validation is `PASS` with declared open-question and contradiction warnings.
- Pre-edit dirty snapshot at the audit timestamp: 197 porcelain entries, status SHA-256 `aaf3b6d70aa90c2a9731503e407ca43c19c43e12907be7e1ded71b49eb810cf4`. This includes unrelated G3/E01 work and concurrent deterministic B1/B4 work; it is not a clean-tree claim.
- This handoff is the only path owned by this refresh: `reports/deterministic/CURRENT_HANDOFF.md`. No other path was edited, staged, committed, or reverted. The active B1/B4 paths listed below remain unowned and must be re-audited before any commit.

## Owned Commits Since Prior Handoff

The previous handoff was at `59b91d3`. All deterministic commits since it are:

`fda9de6` Phase A closeout; `53f1c3a` Phase B semantic audit; `afee434` B0
harness; `b8aba6b` permutation-policy reset; `f2c8a33` exact-deck binding;
`a6903a5` public deterministic control; `54eb856` B1 experiment preregistration;
`e25100a` B0 harness hardening; `459b104` B1 runtime-oracle audit;
`be41294` B0 mechanical canary; `e1f1197` native Mega Abomasnow route semantics;
`6153f4e` B2 continuity preregistration; `909f792` B0 scale budgets;
`c2de279` B0 local-screen authorization; `492701f` rejected Frost Barrier probe;
`a951ce9` B0 local screen; `b7b53f7` B1 prize-route oracle;
`baaeb55` Frost Barrier response contract; `31d22b7` B0 upper-screen authorization;
`83467f5` Phase A semantic reconciliation; `2f3e773` B0 upper screen;
`c871c55` B3 resource-ledger design; `8cac372` B2 continuity evaluator;
`78b3406` Phase A/B1 capability capsules; `4bd2c59` B4 threat design; and
`a108353` B3 fixture qualification. The full hashes are recoverable from the
current `git log`; no commit was made by this refresh.

## Exact Candidate and Control

- Exact candidate deck profile: `mega-abomasnow-ex`, 60 cards. Current exact
  deck file SHA-256 `7af2d7e111c084da535b89758730b3fd6cbb7c0543a9444499c5b61efdc8aecd`;
  semantic multiset SHA-256 `2de6cda970bdd02af6de83ba8b0865fe751ff9282f381a6e775a4017abbca776`.
- B0 candidate import: `ptcg_rl.deterministic.policy:DeterministicStrategicPolicy`,
  policy ID `deterministic-strategic-mega-abomasnow-v1`. It inherits the public
  deterministic Mega Abomasnow control; it does not integrate B1/B2/B3/B4 as
  native decision authority.
- Frozen B0 comparison control in these runs: exact native `rule:mega-abomasnow-ex`.
  All B0 runs used natural deployment against `rule:dragapult-ex`, `rule:iono`,
  `rule:mega-abomasnow-ex`, and `rule:mega-lucario-ex`, balanced candidate seats,
  candidate-perspective terminal WDL, official engine entropy, no paired-seed
  claim, and no manual randomness control.
- Strongest separately observed deterministic rule anchor remains exact native
  `mega-lucario-ex`: 42 wins / 22 losses / 0 draws in 64 games (`0.65625`) over
  the four anchors (per-anchor `11-5`, `14-2`, `9-7`, `8-8`). Its scratch
  evidence lacks a complete gate reliability receipt; it is a benchmark, not a
  promoted deck or submission policy.

## B0 Evidence

The following are the reviewed B0 artifacts. Scores are candidate-perspective
`(wins + 0.5 * draws) / games`; all runs had zero invalid selections,
fallbacks, post-terminal actions, timeouts, failures, incomplete games, and
missing outputs. Intervals are descriptive independent-game bootstrap/Wilson
quantities from the retained reports, not promotion confidence.

| stage | run ID | candidate W-D-L / score (interval) | control W-D-L / score (interval) | delta bootstrap | callback latency candidate p50/p95/p99/max ms (n) | control p50/p95/p99/max ms (n) |
|---|---|---|---|---|---|---|
| 16-game canary | `b0-ma-control-20260807T225553.105921Z-5bd7d7f197ab` | `6-0-2 / 0.75` (no Wilson interval) | `3-0-5 / 0.375` (no Wilson interval) | `[-0.125, 0.375, 0.75]` (p2.5/p50/p97.5) | `3.276682 / 5.671528 / 6.780634 / 7.854330` (248) | `0.427020 / 0.745225 / 1.030882 / 1.887297` (245) |
| 64-game local screen | `b0-ma-control-20260807T234227.364853Z-dd0536b23914` | `15-0-17 / 0.468750` (`[0.308694, 0.635505]` Wilson 95%) | `13-0-19 / 0.406250` (`[0.255196, 0.577399]` Wilson 95%) | `[-0.1875, 0.0625, 0.3125]` (p2.5/p50/p97.5) | `3.204383 / 5.578336 / 7.125700 / 9.515298` (994) | `0.432276 / 0.714351 / 0.983036 / 2.079636` (958) |
| 128-game local upper screen | `b0-ma-control-20260808T001832.741228Z-776704d147fd` | `27-0-37 / 0.421875` (`[0.308698, 0.543900]` Wilson 95%) | `21-0-43 / 0.328125` (`[0.225706, 0.450009]` Wilson 95%) | `[-0.078125, 0.093750, 0.265625]` (p2.5/p50/p97.5) | `3.060159 / 5.762443 / 7.372947 / 11.520767` (1741) | `0.394472 / 0.716307 / 0.943995 / 2.378633` (1836) |

The review verdicts are respectively `PASS_FOR_16_GAME_MECHANICAL_CANARY_ONLY`,
`PASS_FOR_64_GAME_LOCAL_SCREEN_EXECUTION_ONLY`, and
`PASS_FOR_128_GAME_LOCAL_UPPER_STAGE_EXECUTION_ONLY`. The 128-game candidate
loses 6/8 in Dragapult seat 0, Iono seat 0, Mega Abomasnow seat 1, and Mega
Lucario seat 1; its delta interval crosses zero. No B0 result establishes
competence, deck selection, promotion, private Kaggle launch, or submission.

## Current Architecture and Authority

The live deterministic stack is a public-information extension around the
existing G1 contracts:

1. `g1.models`, `g1.actions`, `g1.semantic`, and `PublicStateV1` define the
   canonical public observation, complete legal options, semantic fingerprints,
   CompoundActionBuilder/STOP contract, and lifecycle identities.
2. `deterministic.control` and `deterministic.policy` implement the exact-deck
   B0 public semantic control. It scores the complete current option set,
   rejects stale/ambiguous/non-public records, resets at lifecycle boundaries,
   and never uses raw option order or successor observations.
3. `deterministic.b1_oracle` is a separate current-state route evaluator. The
   uncommitted B1 policy/component harness is not part of the B0 import.
4. `deterministic.b2_continuity` and `deterministic.b3_ledger` are isolated
   fixture evaluators. They consume public current-state records and delegate
   unknown, partial, unsupported, compound, or unqualified cases to B0.
5. The B4 threat evaluator is concurrent and uncommitted. It is not in the
   promoted policy path and its current fixture review remains blocked.

**Promoted implementation or evidence boundary:** G1 terminal-first,
complete-option, semantic-source/target/role, public-only, lifecycle/reset,
no-manual-randomness, and fail-closed contracts; the existing public B0
control; and Phase A route status `PASS` only for Carmine, Lillie's
Determination, Ultra Ball, Precious Trolley, and Snover evolution. These are
implementation/evidence boundaries, not a strength or deck-freeze claim.

**Fixture-only:** B1 route formulations and capability receipts; B2-A
next-attacker and B2-B two-attacker-tail continuity; B3-A/B resource ledger;
and B4-A/B visible-threat formulations. Fixture PASS proves arithmetic,
permutation/lifecycle/fail-closed behavior within the fixture contract only.

**Rejected, invalid, or not promoted:** naive one-ply, broad beam, PUCT as
general authority, static macro leaves, broad terminal macro search,
replay-learned value leaves, pure BC, BC/rule hybrid, and direct terminal
search with manual coin handling. Search feasibility is mechanical only.
The completed BC run remains advisor-only (284 train / 32 validation episodes,
840 optimizer steps, epoch-4 validation NLL `1.374653`; native head-to-head
rule `11-5`, pure BC `2-14`, BC-at-MAIN/rule-subselection `4-12`). No search,
BC, B1, B2, B3, or B4 feature is production authority.

## B1 Exact-Deck Gate and Current Blockers

The old Phase A/B1 capability capsule report is useful semantic evidence but
does not close current integration:

- `reports/deterministic/phase-a-b1-capability-capsules-v1.json` is reviewed
  `PASS` at `2026-08-08T01:11:48.180116Z`, with 264/264 completed native games,
  zero aggregate reliability counters, proofs for prize targets and Snover
  attacks 1044/1045, and 52 Snover-to-Mega evolution proofs. It explicitly
  grants no PolicyV1 integration, native integration, production, or strength
  authority.
- Its candidate-deck receipt is `7d5f90c8c53f22fcdba99acce88a9e76c8a91f7e9e5a5b41315dd9dbcd2a0aa2`,
  which is not the current exact production deck hash above. The Phase A
  reconciliation at `83467f5` therefore preserved these paths as
  non-authoritative; do not use this matrix to unlock current B1.

The exact production-deck plan is
`configs/deterministic/phase_b1_exact_deck_capability_rerun_v1.json` (current
SHA-256 `7a459695535a909dfae79eef6c81fe0a58f1441b1cda038272301eba0078ca88`).
It binds the 60-card exact deck, proof goals `snover_1044_first`,
`snover_1045_first`, `snover_to_mega_evolution`, and `prize_route_targets`,
and is currently `BLOCKED_PENDING_INDEPENDENT_TECHNICAL_REVIEW` with
`native_execution=NOT_RUN_BY_DESIGN`, zero capability proofs, and zero native
games. The paired raw plan evidence and report are also blocked plan-only
artifacts (report SHA-256 `8591505d...`, raw SHA-256
`3e24247d...`). The route receipt v2 is only
`ROUTE_CAPABILITY_ONLY`, not native or policy authority.

The current review
`reports/deterministic/phase-b1-native-integration-review-v1.json` was created
at `2026-08-08T02:34:56Z`, audited historical HEAD `4bd2c59a...`, and is
`REVIEW_COMPLETE_BLOCKED` / `BLOCKED_NO_EXACT_DECK_CAPABILITY_OR_24_GAME_RECEIPT`.
It found four release blockers:

- claimed duplicate hashes, scopes, and component paths are not all
  independently cross-checked or repository-bound;
- a format-only forged stage-0 review digest can unlock the 192-game screen;
- caller-forged reliability metadata can bypass resume stop-on-defect; and
- resume accepts a changed run ID instead of enforcing run-lineage continuity.

Consequently the exact-deck semantic capability receipt is not preparable, the
required stage-0 matrix (B0/B1-A/B1-B x four anchors x candidate seats 0/1 =
24 games) is not authorized, and the 192-game screen is inaccessible. Current
B1 status is no native launch, no Kaggle run, no training, no submission, and
no deck freeze.

## B2, B3, and B4

- **B2 continuity:** Design `phase-b2-continuity-design-v1.json` is
  `DESIGN_COMPLETE_NATIVE_BLOCKED`; evaluator/config/tests landed in
  `8cac372`. B2-A (`next-attacker threshold`) and B2-B (`two-attacker chain
  tail`) remain fixture-only. There is no retained independent B2 fixture PASS
  report and no native capability receipt for the required 1044/1045,
  evolution/status, or current local-delta semantics. Native is blocked.
- **B3 resource ledger:** Design review is
  `DESIGN_READY_FIXTURE_AND_NATIVE_BLOCKED`. Commit `a108353` retains
  `phase-b3-resource-ledger-fixture-review-v1.json`, status
  `REVIEW_COMPLETE_FIXTURE_ONLY_PASS_NATIVE_BLOCKED`, verdict
  `FIXTURE_IMPLEMENTATION_PASS_NATIVE_BLOCKED`. The final recheck at
  `2026-08-08T02:39:35Z` closes RED-001 through RED-010 for the fixture
  boundary, including exact `Fraction` probability math, known/unknown
  separation, capacity-bound allocations, complete-option-before-STOP,
  lifecycle/mirror checks, and fail-closed delegation. Focused final evidence
  includes 30 B3 tests, 66 B3/state/control/policy tests, and 210 deterministic
  tests with concurrent B4 excluded. This is fixture-only; native and
  production remain blocked.
- **B4 opponent threat:** Design commit `4bd2c59` is
  `PASS_AFTER_REPORT_ONLY_CORRECTIONS` for design and fixture/native blocked.
  Current active uncommitted review
  `phase-b4-opponent-threat-fixture-review-v1.json` was created
  `2026-08-08T01:42:01Z`, updated `2026-08-08T02:21:21Z`, and is
  `REVIEW_COMPLETE_BLOCKED` / `BLOCKED_RESIDUAL_RECEIPT_CONTENT_AND_SEMANTIC_BOUNDARY`.
  Corrected implementation/config/test hashes are respectively
  `e4592d68...`, `890cadd4...`, and `8bc27660...`. RED-008 still permits a
  forged whole capability receipt; RED-009 leaves target/status/energy and
  source/target ownership semantics insufficiently bound to the exact public
  option/entity. The dedicated 18-test fixture and latest 228-test
  deterministic suite pass, but no native or production activation is
  authorized.

## Tests and Knowledge Base

- `UV_CACHE_DIR=.uv-cache uv run python knowledge_base/validate_db.py`: `PASS`;
  56 sources, 62 claims, 20 strategies, 36 rules, 16 search features, 17
  archetypes, 49 cards, 12 matchups, 20 matchup plans, 10 replay patterns,
  6 contradictions, and 15 research questions. Warnings are 12 open/in-review/
  blocked P0/P1 questions and 3 unresolved contradictions.
- Latest retained deterministic suite: `228 passed` after concurrent B1/B3
  reconciliation, as recorded by the B4 review. Earlier B3-scoped runs that
  included the concurrently incomplete B4 module had collection failures; the
  B3 report labels them `PASS_WITH_CONCURRENT_UNTRACKED_B4` or excludes B4.
- B1 focused review: 54 selected tests passed; Ruff and compileall passed;
  native execution was intentionally not run. B4 focused review: 18 passed;
  Ruff and compileall passed. These are implementation/fixture checks, not
  native strength evidence.
- Retained project full-suite baseline remains `512 passed, 1 failed`; the
  failure is the unrelated dirty-state expectation at
  `tests/g3/test_competence_plan_report.py:149` (expects DEC-028 while dirty
  `reports/gates/g3b.json` reports DEC-047). It was not changed or used as
  deterministic evidence.

Relevant KB IDs re-queried by the active reports include interface and outcome
guards `DR-001`, `DR-002`, `DR-003`, `DR-022`, `DR-023`, `DR-024`, `DR-025`,
`DR-029`, `DR-030`, `DR-031`, `DR-032`, `DR-033`, `DR-035`, `DR-036`; route,
continuity, ledger, and threat rules `DR-004`, `DR-005`, `DR-006`, `DR-007`,
`DR-008`, `DR-012`, `DR-013`, `DR-014`, `DR-016`, `DR-017`, `DR-018`,
`DR-023`, `DR-024`; strategies `STR-003`, `STR-004`, `STR-007`; search
features `SF-002`, `SF-003`, `SF-004`, `SF-005`, `SF-009`, `SF-010`; and
anti-patterns `AP-001`, `AP-008`, `AP-009`, `AP-011`, `AP-014`.

Open questions remain `RQ-001`/`RQ-002` host and card-universe parity,
`RQ-003` hidden opponent prevalence, `RQ-004` exact routes,
`RQ-005` route-feature ablation, `RQ-006` option-order ablation,
`RQ-007` exact card interactions, `RQ-008` selective search,
`RQ-009` public belief, `RQ-010` teacher transfer (blocked), `RQ-014`
discussion refresh (in review), and `RQ-015` final rules/runtime. P2 questions
`RQ-011` timing, `RQ-012` deck-out frequency, and `RQ-013` public archetype
classification also remain open. Unresolved contradictions are `CON-001`
Prize trade versus immediate Prize, `CON-002` conditional deck thinning, and
`CON-004` option order versus semantic legality.

## Concurrent Refresh Boundary

At the audit timestamp the following uncommitted B1/B4 paths were observed and
must be re-hashed, re-reviewed, and checked against the current HEAD immediately
before any parent commit: `src/ptcg_rl/deterministic/b1_oracle.py` (modified);
B1 configs `phase_b1_component_qualification_v1/v2.json`,
`phase_b1_exact_deck_capability_rerun_v1.json`,
`phase_b1_native_route_receipt_v1/v2.json`; B1 reports
`phase-b1-exact-deck-capability-rerun-v1.json` and `.raw.json`,
`phase-b1-native-integration-package-v1/v2.json`, and
`phase-b1-native-integration-review-v1.json`; B1 scripts
`phase_b1_component_qualification.py` and
`phase_b1_exact_deck_capability_rerun.py`; B1 sources/tests
`b1_component_harness.py`, `b1_policy.py`,
`test_phase_b1_component_harness.py`, and `test_phase_b1_policy.py`; and B4
`phase_b4_opponent_threat_fixture_v1.json`,
`phase-b4-opponent-threat-fixture-review-v1.json`,
`b4_opponent_threat.py`, and `test_phase_b4_opponent_threat.py`.

Audited current hashes for the key active artifacts were: B1 integration review
`d1870130...`; B1 exact-deck plan/report/raw
`7a459695...` / `8591505d...` / `3e24247d...`; B1 component plan
`0e8c898a...`; B1 route receipt `5a924ac4...`; B4 review/config/source/tests
`d0d5a7c7...` / `890cadd4...` / `e4592d68...` / `8bc27660...`.
These are timestamped observations, not sealed commit receipts. Refresh this
section and the B1/B4 verdicts again before commit if any concurrent path moves.

## Risks and Exact Next Task

Primary risks are unresolved hosted engine/card-universe/runtime parity,
unknown opponent prevalence, incomplete exact CABT capability receipts,
public-only hidden-state uncertainty, option-order/version drift, and a
concurrent dirty worktree. Never turn fixture arithmetic into native effect
authority or use the old B0 delta as a competence claim.

The next task is precisely: refresh the active B1/B4 hashes and current status;
fix and independently review B1 duplicate-hash/scope/path enforcement, sealed
stage-0 review binding, derived reliability recomputation, and run-lineage
continuity; close B4 RED-008 and RED-009 with canonical capability-content and
public semantic binding; then obtain a fresh independent exact-deck capability
review. Until that review passes, do not run the 24-game native canary, unlock
the 192-game screen, launch Kaggle, train, freeze a deck, or submit.
