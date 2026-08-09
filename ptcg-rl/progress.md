# Codex Execution Journal

## CURRENT STATE / RESUME HERE

Updated: 2026-08-09T19:49:05+05:30

- Best live agent: unchanged qualified Grimmsnarl/Froslass Damage-Transfer Control, Kaggle submission `55372188`, freshly verified `COMPLETE` at public score `800.5`. It has 36 public games, 19 wins and 17 losses, plus one successful validation episode. The score fell from 814.0 after two new losses and remains far below the 1000+ target; it is still the strongest live-safe NNMax control.
- Best validated local control: unchanged package `.chatgpt/tmp/submissions/kptcg-grim-control-v1.tar.gz`, 3,640,195 bytes, SHA-256 `e9d4681a5252f563309befc450dd31d8c66171b81455600c9e783b13c6d52657`. Do not rebuild or modify it.
- Best local candidate: no derivative is promoted above the unchanged Grim control. The 80-game history-Majkel c0.70 screen winner is independently rejected after its 480-game confirmation: pure `100/0/140` (`0.41667`) versus c0.70 `98/0/142` (`0.40833`).
- Active hypothesis: an experimental Dragapult-only ToActive guard can avoid a public 70-damage Jet Headbutt liability by preferring a Munkidori projected above 70 HP over a lethal Impidimp, while abstaining when Dragapult is uncharged, no Munkidori survives, no Impidimp is offered, or options are ambiguous. Phantom Dive remains lethal to all choices, so win impact is unknown.
- Most recent decisive evidence: lead artifact audit confirms Stage A completed both native slots, one candidate win and one loss, with zero invalids/fallbacks/post-terminal actions/failures, finite sub-5 ms maximum policy latency, empty stderr, and byte-identical before/after candidate/control hashes. Mechanics PASS grants no strength authority.
- Exact next task: commit the Stage A result journal, then create/audit the smallest resumable Stage B runner for the fixed 240-game targeted Dragapult screen. Predeclare reliability and kill rules before launch; do not promote from the screen.
- Latest relevant session commit: `2a08d53c38ace873f12b07b138852e687444a45b` (`exp: qualify Dragapult promotion guard integration`). Fixture commit is `c71a116290b2f3c5239e2e6acd8bfea127bc1a8c`; exact-state audit `9f6315794975bb87ca2bbd251c120a0bdcefbac1`; Majkel rejection `501cde828bc47ecf85e26334960b4047486e498f`; loader fix `122e7d1f654d75f4b94a5b7dcda2c6986f8c6ef0`. Pre-session HEAD was `e572280f1b1f90fc908ee5b814fc3ca87ee5dc34`.
- Uncommitted session work: this post-commit journal SHA update plus the generated/private scratch candidate tree, which remains intentionally untracked and must not be staged. Private screen bodies remain untracked. Five restricted live replay bodies plus a manifest/analysis exist under `.chatgpt/tmp/grim-live-55372188/`; a local `.git/info/exclude` rule protects that directory and none of it may be staged. Pre-existing worktree state must remain untouched: 17 modified tracked paths and approximately 195 compact untracked entries (85,941 individual untracked files with full expansion) before this file, with tracked diff SHA-256 `dabd0a9451518cfca03c1036e0fb3b0d3e7376fff57e41ba96217a2beb16c1b5`.

RESUME HERE: commit the audited Stage A mechanics PASS, then prepare and predeclare the fixed 240-game Dragapult-only Stage B screen (control/candidate x two opponent proxies x both slots x 30 games); do not promote from this screen.

## Session Guardrails

- Role: research lead, planner, auditor, and orchestrator. Heavy coding, repetitive inspection, debugging, and web/Kaggle research are delegated to `gpt-5.6-luna` agents at `xhigh` reasoning; the lead audits results and maintains this journal.
- Commands are scoped to `/home/nnmax/Desktop/kaggle/PTCG` or its `ptcg-rl` child and prefixed with `rtk`.
- No paid compute, Modal job, training, push, PR, destructive Git/filesystem operation, or live submission has been launched in this session.
- Never call `kaggle_create_benchmark_task_from_prompt`.
- Stage and commit only explicit owned paths. Never use `git add .` or `git add -A`.

## 2026-08-09T14:45:01+05:30 - Step 1: Read-Only Orientation And Knowledge Audit

**Objective/question**

Reconstruct the current project, evidence, dirty worktree, knowledge base, live-safe control, and exact interrupted Majkel task before changing strategy or code.

**Evidence inspected**

- Canonical parent handoffs: `current.local.md`, `KPTCG_GOLD_PATH_MASTER_PROMPT.local.md`, all four Aug-9 dated handoffs through `2026-08-09-1237-kptcg-full-context-reconstruction.local.md`.
- Governing files: parent `AGENTS.md`, `ptcg-rl/AGENTS.md`, `PROJECT_STATUS.md`, `PROGRESS_REPORT.md`, `reports/deterministic/CURRENT_HANDOFF.md`, `reports/decisions/current.json`, `reports/tasks/current.json`, `reports/gates/g3b.json`, relevant DEC-010/011/025-028/047 records, and the 998-line deterministic master prompt.
- `PROJECT_STATUS_ANALYSIS.md` does not exist in the checkout.
- Git branch/log/remote/status and tracked diff classification.
- Full semantic knowledge database, including all requested core and relationship tables; FTS shadow tables were skipped because they duplicate semantic rows.
- Current Majkel history scripts, manifest, compact model metadata/results, generated package receipts, package audit, strength runner, `NativeRulePolicy`, and arena loader.
- Unchanged Grim tarball identity and archive layout (read-only).

**Important commands**

```text
rtk git status -sb
rtk git log --oneline --decorate -20
rtk git branch -vv
rtk git remote -v
rtk git rev-parse --show-toplevel
rtk git diff --stat
rtk git diff | sha256sum
rtk uv run python knowledge_base/validate_db.py
rtk uv run python knowledge_base/query_db.py stats
rtk uv run python knowledge_base/query_db.py unresolved
rtk uv run python knowledge_base/query_db.py rules
rtk sha256sum .chatgpt/tmp/submissions/kptcg-grim-control-v1.tar.gz
```

All paths in the final two commands above are relative to `ptcg-rl/`.

**Test/inspection size**

- Knowledge DB: 56 sources, 62 claims, 20 strategies, 36 decision rules, 14 anti-patterns, 17 archetypes, 49 cards, 12 matchups, 20 matchup plans, 12 interactions, 7 probability models, 16 search features, 10 replay patterns, 6 contradictions, and 15 research questions.
- Source tiers: A=26, B=14, C=16. Claim confidence: VERY_HIGH=16, HIGH=39, MEDIUM=7.
- Majkel corpus: 201 public games; 6,309 MAIN decisions; 1,047 features; 39 observed semantic labels, 38 present in training.

**Results and metrics**

- Knowledge DB validation: `PASS`; warnings are 12 unresolved P0/P1 questions and 3 explicitly unresolved contradictions.
- Strong invariants: terminal-first handling; complete legal-option scoring; semantic legality; ordered unique multi-select with legal STOP; public-only hidden-state reasoning without replacement; exact CABT/card semantics; natural-seat balanced W/D/L evaluation; replay observations are non-causal.
- Highest-value isolated hypotheses remain route plus next-attacker continuity, gust route conversion/threat denial, role-aware bench liability, and information-first resource/prize ledgers. They are hypotheses for isolated CABT ablation, not blanket evaluator authority.
- Actual Git root is the parent `PTCG` directory, despite `ptcg-rl` being the active code subtree. Branch `main`; `origin/main` is `41be61f`; local is five commits ahead.
- No retained `strength-screen-v1.json`, `strength-failures/`, native traceback, or 80-error report exists for the interrupted Majkel run. Therefore the failure cause is not yet evidence-closed.

**Failures / invalid actions / fallbacks**

- Orientation and DB validation: zero command failures relevant to project state; no game actions were executed.
- Historical interrupted screen: 80 control games completed; history candidates had 80 errors each according to the direct handoff, with zero completed candidate games. Invalid/fallback/post-terminal counts cannot be inferred because the exact traceback and run artifact were not retained.
- A separate historical `majkel-current/threshold-strength-v1.json` contains 48 stale Alakazam receipt errors. It is not evidence for the distinct 80-error event.

**Interpretation**

The tracked Aug-6 ledgers and Aug-9 12:37 handoff are historical. The direct current instruction plus newer 201-game scratch artifacts establish the present resume point. Improved imitation is diagnostic only. The integration failure must be reproduced before any model redesign or strength judgment.

**Decision**

`KEEP ALIVE / BLOCKED ON INTEGRATION DIAGNOSIS` for the Majkel history branch. Preserve unchanged Grim as live control. Do not promote, reject, train, submit, or redesign the model yet.

**Reason**

Replay execution and chronological fidelity are positive, while native execution failed uniformly before producing outcome evidence. That pattern is consistent with integration failure and cannot support a strategic rejection.

**Files created/changed**

- Created `ptcg-rl/progress.md` (this journal).
- No strategic source, model, package, replay, tracked ledger, or canonical handoff was modified.

**Artifact paths**

- `.chatgpt/tmp/majkel-history/manifest.json` SHA-256 `17f96700cab084576ccdf8664f5634d2c3b58c61eed2aba2bd13b653a9fd1496`
- `.chatgpt/tmp/majkel-history/history-semantic-compact.pkl.gz` SHA-256 `fca6e3a4110daf7845b4fbb0602fec0c4fc6810597f91d5deb22c216b980512d`
- `.chatgpt/tmp/majkel-history/history-semantic-meta.json` SHA-256 `0cf78f30bde910f83985e693348d23f09680a40f5396be9c2d574daa3bd4d0fe`
- `.chatgpt/tmp/majkel-history/history-semantic-results.json`
- `.chatgpt/tmp/majkel-history/run_strength_screen.py`
- `.chatgpt/tmp/majkel-history/arena-agents/`
- `.chatgpt/tmp/submissions/kptcg-grim-control-v1.tar.gz`

**Next action**

Refresh mutable Kaggle competition, leaderboard, NNMax submission, Grim episode, and Majkel episode facts. Then capture one exact native failure in the smallest bounded process.

**Commit SHA**

`5002e83` (`docs: checkpoint deterministic takeover orientation`).

## 2026-08-09T14:48:44+05:30 - Step 2: Mutable Kaggle State Refresh

**Objective/question**

Replace the handed-off leaderboard, quota, Grim score/episodes, and Majkel episode assumptions with current authenticated Kaggle evidence before using any live fact.

**Evidence inspected**

- Authenticated competition metadata and official Evaluation/Rules/FAQ pages for `pokemon-tcg-ai-battle`.
- Current 50-team leaderboard page.
- NNMax submission history and exact submission metadata for `55372188`.
- Full public episode metadata for `55372188`; replay bodies were not downloaded.
- Majkel team `16374395` public submissions and full episode metadata for scoring submission `55333348`; replay bodies were not downloaded.

**Important read-only calls**

```text
mcp__kaggle__get_competition
mcp__kaggle__list_competition_pages
mcp__kaggle__get_competition_leaderboard
mcp__kaggle__search_competition_submissions
mcp__kaggle__get_competition_submission (55372188 only)
mcp__kaggle__list_submission_episodes
mcp__kaggle__list_team_public_submissions
```

No upload, submit, session, dataset, replay-download, or benchmark-task tool was called.

**Test/inspection size**

- Leaderboard: first 100 teams across the lead and independent refreshes.
- NNMax: 7 visible historical submissions.
- Grim `55372188`: 21 public episodes plus 1 validation episode.
- Majkel `55333348`: 201 public episodes plus 1 validation episode.

**Results and metrics**

- Competition ID `116727`; final deadline `2026-08-16T23:59:00Z`; new-entrant deadline `2026-08-09T23:59:00Z`; user entered; maximum 5 submissions/day; metric `cabt`.
- Official Evaluation page confirms only the latest 2 submissions are tracked/active for final evaluation, while the leaderboard displays the best-scoring active agent. Rules allow up to 2 final submissions.
- Current leaderboard #1 remains Majkel1337, team `16374395`, score `1226.6`. The former Aug-9 top-eight snapshot is stale: current #2 AlphaStarmie `1171.6`, #3 James/Henry `1170.3`, #4 palsystem `1162.9`, #5 MissingNo. `1149.1`, #6 flg `1142.5`, #7 Thai `1127.3`, #8 Raihan Ramadistra `1127.0`.
- NNMax competition user rank moved from `816` during the lead refresh to `815` in the later independent refresh, confirming it is mutable.
- Grim `55372188`: submitted `2026-08-09T08:00:30.530Z`, exact file size 3,640,195 bytes, description and filename match the qualified control, status `COMPLETE`, public score `817.3`.
- Grim public W/D/L is `12/0/9` over 21 games (`57.14%` raw match score); public episodes span `91260285` through latest `91276498`. One validation episode completed successfully.
- Majkel public-active submissions are `55333348` at `1226.6` and `55337430` at `963.6`; therefore `55333348` remains the scoring agent. It exposes exactly 201 public episodes, so the local 201-game manifest is current and complete relative to the API snapshot. Latest public episode remains `91264222`; the weaker alternate has newer games but is not the target controller.
- Majkel `55333348` episode W/D/L is `115/0/86` over the 201 public games; the additional validation win makes the raw all-episode count `116/0/86`.
- Only one NNMax submission is visible on Aug 9 (`55372188`). The connector exposes the five-per-day maximum but not an authoritative remaining-attempt counter or reset-window semantics; exact remaining quota is therefore not claimed.
- The official FAQ still returns unresolved template placeholders for archive size, RAM, vCPU, and disk. The cached conservative local values remain engineering assumptions, not freshly reverified external values.

**Failures / invalid actions / fallbacks**

- Kaggle refresh: zero read-only API failures affecting the conclusions. Direct metadata access to another team's private submission was permission-restricted, so public team-submission metadata was used instead.
- No game actions, invalid selections, fallbacks, post-terminal actions, or external mutations occurred.

**Interpretation**

Grim has moved from a two-game `738.6` canary to `817.3` after 21 public games. It is the strongest NNMax live agent, but current live evidence does not support a gold/1000+ claim. The current leaderboard composition changed materially, so old 12.5%-each top-eight weights cannot be used as present-tense meta frequencies. Majkel's 201-game history corpus has not become stale since training.

**Decision**

`KEEP LIVE CONTROL / DO NOT REPLACE`; `KEEP MAJKEL HISTORY BRANCH ALIVE` pending the native integration diagnosis.

**Reason**

Grim is reliable and currently stronger than NNMax alternatives, while no qualified challenger exists. Majkel remains #1 and the exact 201-game public corpus still matches current exposed data, so diagnosing its history controller remains high-value.

**Files created/changed**

- Updated `ptcg-rl/progress.md` only.
- No Kaggle replay, submission artifact, source, package, or external object was created or changed.

**Artifact paths**

- Live submission ID `55372188`; public episode IDs are available from the authenticated API.
- Majkel scoring submission `55333348`; local mirror manifest remains `.chatgpt/tmp/majkel-history/manifest.json`.

**Next action**

Run one bounded native `arena-one` reproduction for `grim-majkel-h-g020` as player 0 versus `dragapult-ex`, capture the exact process traceback/failure, and stop before any fix.

**Commit SHA**

`122e7d1f654d75f4b94a5b7dcda2c6986f8c6ef0` (integration diagnosis and fix milestone).

## 2026-08-09T14:55:55+05:30 - Step 3: Exact Majkel Native Failure Reproduction

**Objective/question**

Reproduce exactly one history-aware Majkel native failure, retain the traceback, and determine whether the interrupted all-error screen reflects strategy or integration.

**Evidence inspected**

- One fresh native process using the generated `grim-majkel-h-g020` package as player 0 and `dragapult-ex` as player 1.
- The generated candidate's `main.py` sibling import.
- `NativeRulePolicy._load_module()` in `src/ptcg_rl/g1/rule_baseline.py`.
- The contrasting loader in `.chatgpt/tmp/majkel-history/audit_packages.py`.

**Important command**

```text
rtk run 'timeout --signal=TERM --kill-after=2s 25s .venv/bin/ptcg g1 arena-one --engine-root private/assets/official/sample_submission/sample_submission --card-data private/assets/official/EN_Card_Data.csv --default-deck private/baselines/mega-lucario-ex/deck.csv --private-baselines .chatgpt/tmp/majkel-history/arena-agents --request-cap 20000 --game-timeout 180 --failure-directory .chatgpt/tmp/majkel-history/strength-failures --policy0 rule:grim-majkel-h-g020 --policy1 rule:dragapult-ex --seed 202625000 --game-id mjh-native-repro-20260809T092047.076198923Z-grim-majkel-h-g020-vs-dragapult-ex'
```

The command ran from `ptcg-rl/` and was bounded to one game process with a 25-second outer cap.

**Test/experiment size**

- Exactly one attempted native game process.
- Candidate seat: player 0.
- Opponent: `dragapult-ex`.
- No policy/model redesign, package regeneration, or broad screen was run.

**Results and metrics**

- Return code `1`; wall time `0.029221384s`; stdout empty.
- Stderr ends with `ModuleNotFoundError: No module named 'majkel_history'` while loading the candidate policy.
- Failure occurs before `EpisodeEnvironmentV1` construction, so no game began and no failure capsule was created.
- `NativeRulePolicy._load_module()` changes CWD to the policy directory but does not add that directory to `sys.path`; the generated candidate imports sibling `majkel_history` absolutely.
- The replay package audit explicitly inserts the package directory into `sys.path`; an isolated probe using that pattern loaded the same candidate successfully.

**Failures / invalid actions / fallbacks**

- Native startup failures: `1/1`.
- Completed games: `0/1`.
- Invalid actions, fallbacks, timeouts, and post-terminal actions: not applicable because policy import failed before the environment and first request existed.
- No failure capsule exists; exact traceback was returned directly by the bounded process.

**Interpretation**

The immediate cause of the history variants' native failure is now proven: the native policy loader does not support sibling imports, while the replay audit loader does. This is a package/loading integration defect, not evidence that the history controller is weak. The existing model, thresholds, features, and strategic policy logic should remain unchanged.

The strength runner's uncaught subprocess timeout and zero-completion division remain separate evidence-retention risks. They did not cause this 29 ms import failure and are not part of the first minimal fix.

**Decision**

`KEEP ALIVE / FIX INTEGRATION ONLY`.

**Reason**

One deterministic startup traceback fully explains why candidate games never began. Native outcome evidence remains absent, while replay execution and chronological imitation evidence remain intact.

**Files created/changed**

- Updated `ptcg-rl/progress.md` only.
- No source, generated package, model, replay, or strategic configuration was modified.
- The requested failure directory remained absent because loading failed before environment creation.

**Artifact paths**

- Candidate package: `.chatgpt/tmp/majkel-history/arena-agents/grim-majkel-h-g020/`
- Generated sibling module: `.chatgpt/tmp/majkel-history/arena-agents/grim-majkel-h-g020/majkel_history.py`
- Native loader: `src/ptcg_rl/g1/rule_baseline.py`
- Replay audit loader: `.chatgpt/tmp/majkel-history/audit_packages.py`

**Next action**

Add one focused regression that loads a private policy importing a sibling module from outside its directory and verifies caller CWD/`sys.path` restoration. Apply the smallest loader fix, run the narrow test and bounded native mechanics checks, audit the explicit diff, update this journal, and make a focused commit.

**Commit SHA**

`122e7d1f654d75f4b94a5b7dcda2c6986f8c6ef0` (integration diagnosis and fix milestone).

## 2026-08-09T15:00:34+05:30 - Step 4: Minimal Loader Fix And Mechanics Qualification

**Objective/question**

Fix only the proven native sibling-import boundary, prove context restoration on success and failure, and verify that the history-aware Majkel candidate can complete native games legally in both seats.

**Evidence inspected**

- Exact diff in `src/ptcg_rl/g1/rule_baseline.py` and `tests/unit/test_g1_environment.py`.
- Existing `NativeRulePolicy` deck/module receipt verification and final action-validator tests.
- Focused regression failure before the fix: `ModuleNotFoundError: No module named 'helper'`.
- Fresh unit, lint, and two-seat native smoke outputs after the fix.

**Important commands**

```text
rtk uv run pytest -q tests/unit/test_g1_environment.py -k 'sibling or import_context'
rtk uv run pytest -q tests/unit/test_g1_environment.py
rtk uv run ruff check src/ptcg_rl/g1/rule_baseline.py tests/unit/test_g1_environment.py
rtk .venv/bin/ptcg g1 arena-one --engine-root private/assets/official/sample_submission/sample_submission --card-data private/assets/official/EN_Card_Data.csv --default-deck private/baselines/mega-lucario-ex/deck.csv --private-baselines .chatgpt/tmp/majkel-history/arena-agents --request-cap 20000 --game-timeout 180 --failure-directory .chatgpt/tmp/majkel-history/strength-failures --policy0 rule:grim-majkel-h-g020 --policy1 rule:dragapult-ex --seed 202615000 --game-id mjh-loader-fix-g020-vs-dragapult-p0
rtk .venv/bin/ptcg g1 arena-one --engine-root private/assets/official/sample_submission/sample_submission --card-data private/assets/official/EN_Card_Data.csv --default-deck private/baselines/mega-lucario-ex/deck.csv --private-baselines .chatgpt/tmp/majkel-history/arena-agents --request-cap 20000 --game-timeout 180 --failure-directory .chatgpt/tmp/majkel-history/strength-failures --policy0 rule:dragapult-ex --policy1 rule:grim-majkel-h-g020 --seed 202615050 --game-id mjh-loader-fix-g020-vs-dragapult-p1
rtk git diff --check -- ptcg-rl/src/ptcg_rl/g1/rule_baseline.py ptcg-rl/tests/unit/test_g1_environment.py ptcg-rl/progress.md
```

**Test/experiment size**

- Two new focused unit regressions: sibling-import success plus import-failure context restoration.
- Full relevant unit module: 8 tests.
- Native mechanics: exactly 2 games, one candidate game per seat, both versus `dragapult-ex`.

**Results and metrics**

- Focused tests: `2 passed`.
- Full `test_g1_environment.py`: `8 passed in 0.04s` on lead rerun.
- Ruff: all checks passed. `git diff --check`: clean.
- Player-0 smoke `mjh-loader-fix-g020-vs-dragapult-p0`: candidate loss, rewards `[-1.0, 1.0]`, status `pass`, 185 requests, 186 transitions, peak RSS `160,768,000` bytes, wall `1.5261s`.
- Player-1 smoke `mjh-loader-fix-g020-vs-dragapult-p1`: candidate win, rewards `[-1.0, 1.0]`, status `pass`, 168 requests, 169 transitions, peak RSS `160,010,240` bytes, wall `1.3677s`.
- Combined candidate W/D/L `1/0/1`; this sample is mechanics-only and says nothing reliable about comparative strength.
- Implementation is three source lines: copy caller `sys.path`, temporarily prepend the resolved private policy directory while executing `main.py`, and restore the exact list contents in `finally`; existing CWD restoration remains in the same `finally` block.

**Failures / invalid actions / fallbacks**

- Post-fix native startup failures: `0/2`.
- Invalid selections: `0/2`; development/submission fallbacks: `0/2`; post-terminal actions: `0/2`; timeouts: `0/2`.
- No native failure artifact was produced.

**Interpretation**

The minimal shared loader repair closes the exact integration defect without touching the history model, thresholds, policy semantics, deck, generated package, or final action validator. Success and exception paths restore the caller's import/CWD context. Both seats now reach terminal native outcomes cleanly, so the branch is ready for outcome screening.

Absolute sibling-module names can still collide if multiple private packages with the same helper name are loaded into one long-lived process. The current native invariant is one active battle per process and the planned runner launches a fresh process per game, so this is a bounded residual risk rather than a reason for a broader import architecture refactor now.

**Decision**

`PROMOTE INTEGRATION FIX / KEEP CANDIDATE ALIVE FOR STRENGTH SCREEN`.

**Reason**

The fix is directly tied to the reproduced traceback, is minimal, passes success/failure regressions, and restores zero-error mechanics in both seats. No strategic-strength conclusion is drawn from two games.

**Files created/changed**

- `ptcg-rl/src/ptcg_rl/g1/rule_baseline.py`
- `ptcg-rl/tests/unit/test_g1_environment.py`
- `ptcg-rl/progress.md`
- No generated history package, model, deck, replay, private engine asset, or live object changed.

**Artifact paths**

- Candidate mechanics package: `.chatgpt/tmp/majkel-history/arena-agents/grim-majkel-h-g020/`
- Failure directory was not created because both games passed.

**Next action**

Stage only the two reviewed source/test paths plus `progress.md`, inspect the staged diff, commit the focused integration fix, then rerun the intended diverse native strength comparison with better per-game evidence retention before judging any variant.

**Commit SHA**

`122e7d1f654d75f4b94a5b7dcda2c6986f8c6ef0` (`fix: load sibling modules in native rule policies`).

## 2026-08-09T15:16:37+05:30 - Step 5: Bounded Live Grim Loss Audit

**Objective/question**

Use current public ladder losses to identify repeated, concrete Grim failure motifs that could support later isolated native ablations, without treating top-agent behavior or retrospective replay state as causal proof.

**Evidence inspected**

- The nine explicitly named public losses known at the `55372188` Kaggle snapshot.
- Five replay bodies retrieved before the byte guard aborted: `91262954`, `91267456`, `91269238`, `91269364`, and `91270142`.
- Semantic decision, action, board, damage, move, prize, and terminal summaries produced from those five bodies.
- Current knowledge-base rules for prize-route planning, next-attacker continuity, bench liability, and replay non-causality.

**Important calls/commands**

```text
GET /api/v1/competitions/episodes/{episode_id}/replay  (only explicitly named public losses)
rtk jq ... ptcg-rl/.chatgpt/tmp/grim-live-55372188/manifest.json
rtk sha256sum ptcg-rl/.chatgpt/tmp/grim-live-55372188/manifest.json ptcg-rl/.chatgpt/tmp/grim-live-55372188/analysis.json ptcg-rl/.chatgpt/tmp/grim-live-55372188/replays/*.json
rtk git check-ignore -v ptcg-rl/.chatgpt/tmp/grim-live-55372188/replays/91262954.json
```

No daily dataset, unrelated episode, upload, submission, benchmark task, training job, or paid compute was touched.

**Test/inspection size**

- Requested: 9 named loss episodes, maximum 9 files / 25 MiB acquisition body bytes.
- Persisted and semantically parsed: 5 files, 24,978,496 bytes.
- Unretrieved: `91271961`, `91272874`, `91273793`, and `91275555`.
- Retrieved archetypes: Grim mirror `2`, Mega Lucario `1`, Dragapult `1`, Archaludon `1`; NNMax seats player 0=`3`, player 1=`2`.

**Results and metrics**

- All 5 were losses. NNMax final prizes remaining were `2, 2, 6, 4, 6`; opponents had `2, 1, 1, 1, 1`.
- NNMax attack counts by episode were `4, 3, 3, 2, 0`; the Archaludon loss `91270142` was the single attackless loss despite repeated development and `END` decisions.
- Munkidori and Spikemuth Gym appeared in all `5/5`; Punk Up context appeared in `4/5`. This supports auditing route/bench use but does not support globally removing any of those cards or actions.
- Terminal opponent attacks were visible in `3/5`; two Grim mirrors ended through board removals without a terminal attack event.
- Strongest repeated public motifs are role-aware bench liability, attack/next-attacker continuity, and finite prize-route planning.
- Three deliberately narrow future ablations were retained: archetype-gated low-HP bench liability versus public Dragapult/Archaludon signatures; an attack-continuity guard in one-prize-risk states; and route-preserving target choice in Mega Lucario/Grim-mirror states.

**Failures / invalid actions / fallbacks**

- Semantic parse/legality errors: `0/5`.
- A required acquisition guard failed: after 24,978,496 persisted bytes, the fetch loop read two 1 MiB chunks from `91271961` before aborting. Acquisition body bytes were 27,075,648, exceeding the 26,214,400-byte cap by `861,248` bytes. The partial was deleted and no sixth body was retained. No further episode was contacted.
- An unrelated endpoint-discovery probe had read 256 bytes from an already selected episode; it is excluded from the acquisition-batch arithmetic but recorded here for completeness.
- Because the cap was exceeded, no remaining live loss body may be retrieved under this reviewed acquisition batch.

**Interpretation**

The five replays are valuable failure-state discovery but are retrospective, incomplete, and non-causal. Exact opponent deck fingerprints are audit metadata, not admissible hidden production input. The evidence argues for small archetype/state-gated interventions rather than a broad evaluator or blanket attack/Munkidori rule.

The byte-limit overrun is an evidence-discipline defect. It is explicitly recorded rather than hidden; acquisition is stopped, and the raw directory is locally ignored. Any future replay retrieval needs a content-length preflight or a remaining-budget-aware stream guard that refuses before reading the chunk that would cross the cap.

**Decision**

`INCONCLUSIVE FOR POLICY PROMOTION / RETAIN THREE ISOLATED HYPOTHESES`; `STOP THIS ACQUISITION BATCH`.

**Reason**

The motifs recur in current live losses and align with strong knowledge-base principles, but five selectively observed losses cannot establish that an intervention wins games. The cap overrun blocks expanding this retrieval batch.

**Files created/changed**

- Restricted/untracked: `.chatgpt/tmp/grim-live-55372188/replays/` with five replay bodies.
- Restricted/untracked: `.chatgpt/tmp/grim-live-55372188/manifest.json` and `analysis.json`.
- Local-only safety change: `.git/info/exclude` now ignores `/ptcg-rl/.chatgpt/tmp/grim-live-55372188/`.
- Updated `ptcg-rl/progress.md`; no source or policy file changed.

**Artifact paths**

- Manifest SHA-256 `ac36e5d40867f5d79e779c180d044ed34f117348ee9edc2bdbf828244be03809`.
- Analysis SHA-256 `92e3e9cf017696d696d3894f360aeb7cada3971140cd077974fe9fdaa1b8b790`.
- Replay file SHA-256 values are recorded in the manifest; persisted byte total is 24,978,496.

**Next action**

Finish and audit the already-running history-Majkel native screen. Do not implement a Grim heuristic until current outcome evidence closes that branch and one live motif is translated into exact current-engine states plus a smallest isolated native intervention.

**Commit SHA**

`5a77ce85d4d9b3e5be0fb9d795f8037aaaf218ef` (`docs: record current Grim loss audit`); restricted replay artifacts were not staged.

## 2026-08-09T15:21:30+05:30 - Step 6: History-Majkel Diverse Native Strength Screen

**Objective/question**

Determine whether the replay-fidelity gains from direct history control, tune-selected gain0.20 residual control, or confidence-0.70 residual control transfer into native game outcomes against the intended diverse panel after fixing the loader.

**Evidence inspected**

- A hardened one-off runner that journals every attempted game before final aggregation, uses unique output directories, catches process/timeout/JSON errors, never divides by zero, and stops on the first reliability anomaly.
- One complete fresh-process native cohort: 4 variants x 8 opponents x 2 candidate seats x 5 games per cell.
- Append-only JSONL records, final aggregate, and managed run journal.

**Important commands**

```text
rtk uv run python .chatgpt/tmp/majkel-history/run_strength_screen.py --self-check
rtk uv run python .chatgpt/tmp/majkel-history/run_strength_screen.py
```

The screen was foreground-managed, bounded to 30 seconds per subprocess and 1,200 seconds overall. The engine's internal game timeout remained 180 seconds and request cap 20,000. Native engine trajectories remain nondeterministic; integer seeds control policy-side randomness only and do not create paired games.

**Test/experiment size**

- `320/320` attempted and completed native games.
- Per variant: 80 games, 10 per opponent, balanced 5 in each candidate seat.
- Opponents: `dragapult-ex`, `mega-lucario-ex`, `lopunny-v9`, `roman-v10`, `crustle-v1`, `nithin-1084`, `alakazam-v9`, and `grim-floor4`.
- Variants: `mk-lgb-0p9-pure`, `grim-majkel-h-direct`, `grim-majkel-h-g020`, and `grim-majkel-h-c070`.

**Results and metrics**

- Total managed runtime: `675.431452s`.
- Pure fallback: W/D/L `33/0/47`, expected match score `0.4125`, mean/p95/max process wall `1.185/3.869/5.148s`, peak RSS `102,555,648` bytes.
- Direct history: `27/1/52`, score `0.34375`, mean/p95/max `2.005/4.639/5.639s`, peak RSS `178,380,800` bytes.
- Gain0.20: `37/0/43`, score `0.4625`, mean/p95/max `2.217/5.706/6.623s`, peak RSS `180,219,904` bytes.
- Confidence0.70: `46/0/34`, score `0.5750`, mean/p95/max `2.169/5.235/8.034s`, peak RSS `180,867,072` bytes.
- Pooled opponent scores, not variant-specific causal effects: Dragapult `0.600`, Mega Lucario `0.725`, Lopunny `0.900`, Roman `0.250`, Crustle `0.150`, Nithin `0.4625`, Alakazam `0.225`, Grim `0.275`.
- Pooled seat scores: candidate seat 0 `0.4719` over `160`; candidate seat 1 `0.4250` over `160`. Variant-specific seat/matchup splits and confidence intervals await independent recalculation.

**Failures / invalid actions / fallbacks**

- Process/native/timeout/malformed-result errors: `0/320`.
- Invalid selections: `0`; fallback actions: `0`; post-terminal actions: `0`; reliability stop condition: not triggered.
- No candidate package/model/deck changed during the screen.

**Interpretation**

Direct history control regressed despite the highest imitation fidelity, reinforcing that imitation is diagnostic rather than the objective. Gain0.20's +5 percentage-point screen difference over pure fallback is not clear evidence. Confidence0.70's +16.25-point difference is large enough to earn independent audit and, if the matchup distribution is not catastrophic, a fresh larger confirmation. It is not sufficient to promote, package, or spend a live slot.

The pure fallback's fresh `0.4125` differs from the lost earlier cohort's approximate `0.45`, another reminder that unpaired stochastic small screens move materially.

**Decision**

Provisional pending independent recomputation: `REJECT DIRECT`; `DO NOT PROMOTE GAIN0.20`; `KEEP C0.70 ALIVE FOR LARGER CONFIRMATION`.

**Reason**

Only c0.70 produced a screen-scale advantage large enough to justify more games, and all mechanics remained clean. Eighty games per variant cannot establish promotion and the project has repeatedly seen larger confirmations erase smaller apparent gains.

**Files created/changed**

- Hardened experimental runner: `.chatgpt/tmp/majkel-history/run_strength_screen.py` (safe source, staging decision pending audit).
- Private scratch results directory: `.chatgpt/tmp/majkel-history/strength-screen-20260809T093708793392Z-dc9f9afe/`.
- Updated `ptcg-rl/progress.md`; no model, package, deck, production policy, or live object changed.

**Artifact paths**

- `aggregate.json`: 9,274 bytes, SHA-256 `0e2cca11ee0b8f6d137ef42233de16a2ed7d4968ba1aed822934b305ccdc52fd`.
- `results.jsonl`: 1,333,727 bytes, SHA-256 `e22c998b3e23fcced2fb746ae963620d324fc5268bc8d8bd06628849cac685a2`.
- `run-journal.md`: 2,769 bytes, SHA-256 `1b2f97a02153c4907a143f053f88b2a273852ad7a4c6e4afea921427c9ef77bd`.
- Hardened runner: 17,129 bytes, SHA-256 `913e17c524c329de2b7b4d8cadb87695e3635b27c7d6ea3fe282ec8cbc5902f8`.

**Next action**

Independently recalculate completeness, W/D/L, reliability, latency/RSS, per-opponent/seat splits, and uncertainty from JSONL. Inspect the runner for evidence corruption. If the result survives, freeze c0.70 unchanged and run a substantially larger independent confirmation against the same panel before any package qualification or live decision.

**Independent audit additions**

- Integrity: exact complete `4 x 8 x 2 x 5` design; 320 unique game IDs and 320 unique policy seeds; all records returned code 0/status `pass`; all failure kinds null; all engine/card/action/observation/trajectory hashes identical.
- Pure Wilson 95% interval `[0.3111,0.5220]`; direct `[0.2435,0.4464]`; gain0.20 `[0.3575,0.5710]`; c0.70 `[0.4657,0.6774]`.
- C0.70 versus pure is an unpaired difference `+0.1625`, approximate 95% interval `[+0.0096,+0.3154]`; a 100,000-resample independent bootstrap with seed `20260809` gives `[+0.0125,+0.3125]`.
- C0.70 candidate-seat splits: seat 0 `25/0/15` (`0.625`), seat 1 `21/0/19` (`0.525`). Actual first-player assignment was player 0 in 240 games and player 1 in 80; this is policy-chosen natural deployment, not a forced first/second diagnostic.
- C0.70 opponent cells: Dragapult `0.90`, Mega Lucario `0.90`, Lopunny `0.90`, Roman `0.40`, Crustle `0.10`, Nithin `0.60`, Alakazam `0.40`, Grim `0.40`, each `n=10`. Relative to pure it improved six cells, regressed Lopunny `1.00 -> 0.90`, and regressed Crustle `0.30 -> 0.10`.
- Overall engine requests were 44,799, range `18..246`; overall max wall/CPU was `8.034/8.031s`; peak RSS was 180,867,072 bytes.
- Runner audit found sound record fsync, collision-safe run directories, exact aggregate recomputation, and stop-on-error/reliability handling for this completed run. Residual harness risk: a timed-out `start_new_session=True` subprocess is not explicitly killed by process group. No timeout occurred, so this does not affect this evidence; fix it before future bounded runs.

**Decision after independent audit**

`REJECT DIRECT`; `DO NOT ADVANCE GAIN0.20`; `KEEP C0.70 ALIVE FOR ONE FRESH 480-GAME CONFIRMATION`; `NO PROMOTION / PACKAGE / LIVE SLOT YET`.

**Reason after independent audit**

The c0.70 advantage survived independent arithmetic and is just large enough to merit confirmation, but multiple comparisons, unpaired native entropy, only 80 games per variant, and a `1/10` Crustle cell prevent promotion. The next experiment must preserve the policy unchanged and increase each opponent/seat cell from 5 to 15 fresh games.

**Commit SHA**

`01ee1534afc6b88c91a2c230928ef4089acc4b8f` (`exp: retain history-aware Majkel strength screen`); private result bodies were not staged.

## 2026-08-09T15:32:53+05:30 - Step 7: Freeze Fresh C0.70 Confirmation Design

**Objective/question**

Prepare the smallest reproducible larger confirmation that preserves the screen-winning c0.70 policy unchanged, uses fresh unpaired native games, retains every attempt, and cannot leak or orphan timed-out native processes.

**Evidence inspected**

- Independent screen audit recommendation and the historical project requirement that apparent 80-game gains receive roughly 480-game confirmation.
- Exact runner control flow, seed arithmetic, timeout cleanup, record journal, aggregate, and CLI mode separation.
- No-native self-check output, Ruff, bytecode compilation, and CLI help.

**Important commands**

```text
rtk uv run ruff check .chatgpt/tmp/majkel-history/run_strength_screen.py
rtk uv run python -m py_compile .chatgpt/tmp/majkel-history/run_strength_screen.py
rtk uv run python .chatgpt/tmp/majkel-history/run_strength_screen.py --self-check
rtk uv run python .chatgpt/tmp/majkel-history/run_strength_screen.py --help
```

No arena game was launched while preparing or checking the confirmation mode.

**Test/experiment size**

- Default-mode arithmetic remains exactly `4 x 8 x 2 x 5 = 320` and retains seed base `202615000`.
- Confirmation mode is exactly `2 x 8 x 2 x 15 = 480`: `mk-lgb-0p9-pure` versus unchanged `grim-majkel-h-c070`, the same eight opponents, both candidate seats.
- Confirmation seed base `202640000` is disjoint from the default screen's policy seeds. Seeds still do not control native engine entropy.

**Results and metrics**

- Ruff: all checks passed.
- Bytecode compilation: passed.
- Self-check: `PASS (no arena games launched)`; it verifies default/confirmation arithmetic, exact variants, seed disjointness, record interpretation, zero-completion aggregation, and termination/reaping of a no-native sleeping process group.
- Confirmation CLI is explicit: `--confirmation`; output directories are collision-safe and labeled `strength-confirmation-*`.
- Outer game cap remains 30 seconds; confirmation overall cap is 2,400 seconds; engine timeout 180 seconds and request cap 20,000 remain explicit.
- The first correct draft was 594 lines and was rejected as over-engineered for a one-off runner. The audited version is 311 lines while preserving the required evidence, timeout, and fail-closed behavior.
- Final validation also rejects missing/negative/non-integer reliability counters, invalid terminal/request counts, and missing/negative/nonfinite wall, CPU, or RSS metrics; self-checks cover a negative fallback count and infinite CPU metric.
- Updated runner: 16,841 bytes, SHA-256 `39eb7db55daf44da077c8c166f97581b9c0994ea1cf6841c67f6a44f95ca93cc`.

**Failures / invalid actions / fallbacks**

- No native game or policy request occurred in this preparation step.
- Previous timeout residual is fixed for future runs: on subprocess timeout, the runner sends SIGTERM to the new process group, waits two seconds, escalates to SIGKILL if required, reaps the process, and retains the timeout record/output before stopping.
- Residual risk: timeout cleanup is tested with a no-native process group rather than an actual hung CABT child. The confirmation remains stop-on-first timeout/error/reliability counter.

**Interpretation**

This is a bounded confirmation of one frozen candidate, not another tuning screen. Default screen reproduction remains available and distinctly labeled; confirmation cannot silently reuse its policy seeds or overwrite its evidence. No model, threshold, deck, package, or opponent schedule changed.

**Decision**

`AUTHORIZE LOCAL 480-GAME CONFIRMATION AFTER FOCUSED COMMIT`; no external compute or live action is authorized.

**Reason**

C0.70 is the only screen variant with an independently verified improvement large enough to justify more local games. The confirmation is the smallest historical-strength check likely to expose another 80-game false positive while keeping compute bounded and evidence auditable.

**Files created/changed**

- Safe reproducible source: `.chatgpt/tmp/majkel-history/run_strength_screen.py`.
- Updated `ptcg-rl/progress.md`.
- No private results, generated package, model, deck, replay, production policy, or live object changed.

**Artifact paths**

- Runner path and SHA-256 as above.
- Planned confirmation outputs will be created only under a new `.chatgpt/tmp/majkel-history/strength-confirmation-*/` directory.

**Next action**

Stage only the safe runner and `progress.md`, inspect and commit them, then execute exactly:

```text
rtk uv run python .chatgpt/tmp/majkel-history/run_strength_screen.py --confirmation
```

Remain foreground-managed until completion or the first stop condition.

**Commit SHA**

`01ee1534afc6b88c91a2c230928ef4089acc4b8f` (`exp: retain history-aware Majkel strength screen`).

## 2026-08-09T15:43:28+05:30 - Step 8: Launch Local C0.70 Confirmation And Freeze Decision Rule

**Objective/question**

Run the single frozen larger confirmation authorized by the audited screen, while fixing the acceptance/rejection rule before seeing its result.

**Evidence inspected**

- Committed runner and c0.70 package identities; no model/package regeneration occurred.
- Existing deterministic confirmation discipline in `phase-b1-prize-route-design-v1.json` and related reviewed designs: hard reliability floors, anchor/seat-stratified independent bootstrap, lower 95% delta bound above `+0.02`, and no anchor point-estimate regression below `-0.10`.
- Fresh confirmation output path and append-only record count only; partial W/D/L was deliberately not inspected or interpreted.

**Important command**

```text
rtk uv run python .chatgpt/tmp/majkel-history/run_strength_screen.py --confirmation
```

This is a foreground-managed local CPU evaluation, not training, paid compute, Kaggle compute, or a live submission.

**Test/experiment size**

- Planned: 480 fresh games, 240 per policy.
- Exact design: 2 policies x 8 opponents x 2 candidate seats x 15 games/cell.
- Policy seed base: `202640000`, disjoint from the screen; native trajectories remain unseeded system-entropy draws and are not paired.
- Checkpoint only: 80 records had been durably journaled when this entry was written. No interim score was read.

**Predeclared decision rule**

- Reliability eligibility requires `480/480` completed and zero timeout, process/native/malformed failures, invalid selections, fallbacks, post-terminal actions, nonfinite metrics, or hash/schema inconsistency.
- Primary effect is the equal-weight mean of the 16 opponent x candidate-seat cell c0.70-minus-pure EMS deltas. Because cell sizes are equal, pooled EMS is descriptive and should agree in point estimate.
- Uncertainty is a 100,000-resample independent, cell-stratified bootstrap with fixed analysis seed `20260809`.
- C0.70 becomes an experimental package-qualification challenger only if its point estimate is at least the pure control, the bootstrap 95% lower bound is strictly greater than `+0.02`, and no opponent-level pooled point delta is below `-0.10`.
- If reliability fails, reject the run. If the interval crosses zero or its lower bound is at most `+0.02`, reject c0.70 as a global replacement under the user's instruction to stop when larger confirmation does not clearly transfer. If aggregate passes but an opponent floor fails, reject global promotion; preserve only a separately testable matchup-specialist hypothesis if public identification is reliable.
- Passing this rule would authorize package qualification only. It would not authorize a live submission, replacement of Grim, gold/1000+ claims, or deck freeze.

**Failures / invalid actions / fallbacks**

- None known at launch/checkpoint; partial aggregates were intentionally not inspected.
- The runner will stop and retain the triggering record on the first anomaly.

**Decision**

`RUNNING / NO STRENGTH VERDICT`.

**Reason**

The independently audited 80-game c0.70 signal earned one larger test, and the acceptance rule is now fixed before its outcome is known.

**Files created/changed**

- Private scratch output directory `.chatgpt/tmp/majkel-history/strength-confirmation-20260809T101230531677Z-a6273434/`.
- Updated `ptcg-rl/progress.md`; no policy, model, deck, source, package, or external object changed.

**Artifact paths**

- Append-only journal: `.chatgpt/tmp/majkel-history/strength-confirmation-20260809T101230531677Z-a6273434/results.jsonl`.
- Final aggregate will appear in the same directory only after completion/stop.

**Next action**

Do not inspect partial W/D/L. Wait for the managed run to finish, independently recompute its complete records against the fixed rule, and then commit the result whether positive or negative.

**Commit SHA**

`501cde828bc47ecf85e26334960b4047486e498f` (confirmation result milestone); runner source is committed at `01ee1534afc6b88c91a2c230928ef4089acc4b8f`.

## 2026-08-09T15:44:27+05:30 - Step 9: Second Mutable Kaggle Refresh

**Objective/question**

Refresh live Grim, Majkel, and leaderboard facts while the local confirmation runs, without downloading another replay or mutating Kaggle.

**Evidence inspected**

- Authenticated competition metadata, current top-20 leaderboard, NNMax submission history, full episode metadata for `55372188`, Majkel active submissions, and episode metadata for scoring submission `55333348`.

**Important read-only calls**

```text
mcp__kaggle__get_competition
mcp__kaggle__get_competition_leaderboard
mcp__kaggle__search_competition_submissions
mcp__kaggle__get_competition_submission
mcp__kaggle__list_submission_episodes
mcp__kaggle__list_team_public_submissions
```

No replay body, file, upload, submission, session, benchmark task, or external mutation occurred.

**Test/inspection size**

- Leaderboard top 20.
- Grim: 34 public games plus 1 validation.
- Majkel scoring submission: 202 public games plus 1 validation.

**Results and metrics**

- Snapshot UTC `2026-08-09T10:13:43.808Z`.
- Deadline remains `2026-08-16T23:59:00Z`; new-entrant deadline `2026-08-09T23:59:00Z`; maximum 5 submissions/day; metric `cabt`.
- Majkel remains #1 and moved to `1230.1`. Current #2 James/Henry `1173.6`, #3 AlphaStarmie `1171.6`, #4 palsystem `1159.4`, #5 MissingNo. `1153.0`.
- NNMax rank fluctuated `827 -> 828` within seconds; latest observed `828` is mutable.
- Grim `55372188`: `COMPLETE`, public score `814.0`, public W/D/L `19/0/15` over 34 games. Latest public episode `91288248` was a loss at `10:08:03.934Z`.
- The live score moved from the prior `817.3`/21-game snapshot to `814.0`/34 games; neither is a settled strength estimate.
- NNMax active submissions remain Grim `55372188` at `814.0` and older `55356773` at `656.7`. Only one Aug-9 attempt is visible, but exact remaining quota is not claimed.
- Majkel active submissions remain scoring `55333348` at `1230.1` and alternate `55337430` at `964.3`.
- Majkel `55333348` now exposes 202 public games, W/D/L `116/0/86`; latest `91289085` was a win. The local 201-game training manifest is now one public game behind the live API, but the running confirmation correctly keeps its frozen model/corpus unchanged.

**Failures / invalid actions / fallbacks**

- Read-only refresh failures: zero affecting conclusions.
- No game action, live candidate, or retrieval batch changed.

**Interpretation**

Grim remains the only qualified live-safe control but is not near the target rating. The additional live evidence strengthens the need for a materially better challenger rather than a cosmetic imitation gain. One new Majkel episode does not justify contaminating an already running frozen confirmation.

**Decision**

`KEEP GRIM ACTIVE / NO LIVE REPLACEMENT`; `KEEP CONFIRMATION FROZEN`.

**Reason**

No qualified challenger exists, and changing the c0.70 corpus/model during confirmation would invalidate the experiment.

**Files created/changed**

- Updated `ptcg-rl/progress.md` only.
- No replay, source, package, or external object changed.

**Artifact paths**

- Live IDs: Grim `55372188`, latest episode `91288248`; Majkel scoring `55333348`, latest episode `91289085`.

**Next action**

Finish and independently audit the frozen local confirmation. Do not spend a live slot from mutable score pressure.

**Commit SHA**

`501cde828bc47ecf85e26334960b4047486e498f` (live refresh and confirmation-result progress commit).

## 2026-08-09T15:59:10+05:30 - Step 10: Complete C0.70 Larger Confirmation

**Objective/question**

Test whether the c0.70 history override's 80-game advantage survives a fresh 480-game confirmation against the unchanged pure Majkel fallback.

**Evidence inspected**

- Complete append-only confirmation JSONL and final aggregate from the committed runner.
- Preliminary run-level W/D/L, reliability, latency, and RSS summaries; independent record-level recomputation is underway.

**Important command**

```text
rtk uv run python .chatgpt/tmp/majkel-history/run_strength_screen.py --confirmation
```

The command ran foreground-managed from `ptcg-rl/` and returned normally.

**Test/experiment size**

- Exactly `480/480` completed native games.
- Pure and c0.70: 240 games each.
- Each policy: 8 opponents x 2 candidate seats x 15 fresh games per cell.
- Started `2026-08-09T10:12:30.531831Z`; ended `2026-08-09T10:27:14.434240Z`; managed runtime `883.902409s`.

**Results and metrics**

- Pure fallback: W/D/L `100/0/140`, EMS `0.4166667`, mean wall `1.211766s`, peak RSS `105,975,808` bytes.
- C0.70: `98/0/142`, EMS `0.4083333`, mean wall `2.096768s`, peak RSS `179,822,592` bytes.
- Preliminary c0.70-minus-pure delta: `-0.0083334`, reversing the screen's `+0.1625` observation.
- Pooled opponent scores across both policies: Dragapult `0.5833`, Mega Lucario `0.6333`, Lopunny `0.9000`, Roman `0.1333`, Crustle `0.0667`, Nithin `0.5167`, Alakazam `0.0833`, Grim `0.3833`.
- Pooled candidate-seat scores: seat 0 `0.4000`; seat 1 `0.4250`.
- Overall mean/p95 wall `1.6543/4.5282s`; overall peak RSS `179,822,592` bytes.

**Failures / invalid actions / fallbacks**

- Errors/timeouts/malformed outputs: `0/480`.
- Invalid selections: `0`; fallback actions: `0`; post-terminal actions: `0`; stop reason: none.
- Status `PASS` means execution/reliability only. It does not make c0.70 a strength pass.

**Interpretation**

The larger cohort eliminates the apparent global c0.70 advantage. This is the same recurring project lesson: improved imitation and an exciting 80-game screen do not establish CABT strength. C0.70 is also slower and larger in memory than pure. No threshold retuning on this confirmation set is permitted; doing so would turn confirmation into training/tuning leakage.

**Decision**

Preliminary pending independent arithmetic: `REJECT C0.70 AS GLOBAL CHALLENGER`; `CLOSE GLOBAL MAJKEL-HISTORY BRANCH`; `NO PACKAGE / SUBMISSION`.

**Reason**

The candidate did not merely miss the preregistered lower-bound floor; its point estimate fell below the unchanged control after 240 games per arm.

**Files created/changed**

- Private scratch results: `.chatgpt/tmp/majkel-history/strength-confirmation-20260809T101230531677Z-a6273434/`.
- Updated `ptcg-rl/progress.md`; no policy, model, package, deck, source, or external object changed.

**Artifact paths**

- `aggregate.json`: 6,850 bytes, SHA-256 `f0788e07999c1f75a68730e179597e3ba02155130c51b63c3cb356a6f9e00745`.
- `results.jsonl`: 1,510,765 bytes, SHA-256 `74f0a77a2161005e981a5bf5221e636889871568c2d991985afad83405038596`.

**Next action**

Independently recompute completeness, hashes, W/D/L, cell deltas, runtime, and the predeclared cell-stratified bootstrap. Commit the negative evidence. Do not build c0.80/c0.90 or retune confidence using these results.

**Commit SHA**

`501cde828bc47ecf85e26334960b4047486e498f` (`exp: reject history-aware Majkel c070`).

**Independent audit result**

- Exact `2 x 8 x 2 x 15` design, 480 unique game IDs/seeds, 15 records in each of 32 cells, consistent candidate reward/terminal mapping, and identical engine/card/action/observation/trajectory hashes.
- Primary equal-cell c0.70-minus-pure effect `-0.008333`.
- Predeclared independent within-cell bootstrap, 100,000 resamples with seed `20260809`: 95% interval approximately `[-0.079167,+0.062500]`, crossing zero and far below the required lower bound `>+0.02`.
- Ordinary unpaired 95% interval `[-0.096409,+0.079743]`; Wilson intervals pure `[0.356086,0.479873]`, c0.70 `[0.348067,0.471488]`.
- Opponent-level pooled c0.70 regressions below the predeclared `-0.10` floor: Mega Lucario `-0.133333` and Alakazam `-0.166667`.
- Positive pooled deltas versus Dragapult `+0.10`, Roman `+0.133333`, Nithin `+0.033333`, and Grim `+0.033333` all have ordinary 95% intervals crossing zero at 30 games/arm. No c0.70 matchup-specialist hypothesis is retained from this confirmation.
- C0.70 mean wall/CPU `2.096768/2.096648s` versus pure `1.211766/1.211609s`; peak RSS `179,822,592` versus `105,975,808` bytes.
- Aggregate recomputation and artifact hashes match exactly; no evidence anomaly remains.

**Final decision after audit**

`REJECT C0.70 GLOBALLY`; `CLOSE THE GLOBAL MAJKEL-HISTORY BRANCH`; `NO RETUNING ON CONFIRMATION`; `NO PACKAGE / SUBMISSION`.

**Final reason**

C0.70 fails three independently fixed strength requirements: its point estimate is below control, its bootstrap lower bound does not exceed `+0.02`, and two opponent floors regress by more than 10 points. Clean mechanics do not rescue failed outcome criteria.

## 2026-08-09T16:29:01+05:30 - Step 11: Exact-State Grim Loss Hypothesis Audit

**Objective/question**

Before changing the live controller, prove or falsify whether the attackless Archaludon loss and exposed-Impidimp Dragapult loss contained a legal, strategically meaningful alternative at the recorded decision point.

**Evidence inspected**

- Restricted replay `91270142` (Archaludon) and `91269364` (Dragapult).
- Qualified tarball SHA-256 `e9d4681a5252f563309befc450dd31d8c66171b81455600c9e783b13c6d52657` and its existing exact extraction; all 385 archive files are byte-identical.
- Exact package re-execution on every recorded NNMax observation with semantic duplicate normalization.
- Controller scoring/routing in `strategic_policy.py`, `human_controller.py`, `main.py`, `matchup_router.py`, and `experts/mirror/manual_policy.py`.

**Important commands/inspection**

Read-only replay parsing, tar/hash comparison, and isolated package-agent calls were used. No native arena game, network call, source write, package rebuild, or external action occurred.

**Test/inspection size**

- Archaludon: all 25 NNMax MAIN decisions, 7 END selections, every legal semantic option and turn progression.
- Dragapult: the opening/development sequence, prior public Phantom Dive spread, turn-8 bench fill, turn-9 KO, five-option ToActive request, turn-10 evolution, and terminal attack.
- Exact package semantic action agreement: all inspected decisions matched replay.

**Results and metrics**

- Archaludon episode `91270142`: ATTACK legally offered `0/25`; END offered `25/25`, selected `7/25`. Every no-attack turn was resource/active-state forced. A turn-9 alternative could set up a later 10-damage Impidimp attack, but it creates no prize route against a 300-HP four-Energy Archaludon and is not a meaningful continuity fix.
- Dragapult episode `91269364`: after the active Munkidori KO, ToActive offered Froslass 90 HP, Munkidori 100/110, Munkidori 80/110, damaged Impidimp 10/70, and fresh Impidimp 70/70. The mirror expert's role priority selected the fresh Impidimp.
- Public Froslass checkup would leave the two Munkidori at 90 and 70 HP before the next attack. Froslass stays 90 HP. Therefore Froslass and the 90-HP Munkidori survive the observed 70-damage Jet Headbutt; the 70-HP Munkidori and both Impidimp do not.
- All five candidates still lose to the available 200-damage Phantom Dive. The counterfactual opponent response is unknown, so this proves only avoidable liability under the observed lower-damage line, not a saved game.
- The exact controller path is the mirror expert promotion score: Impidimp role priority 80, Munkidori 30, Froslass 10, with same-role HP tie breaking. Downstream guards retained that choice.

**Failures / invalid actions / fallbacks**

- Replay/package execution errors: zero; legality errors: zero.
- A research-audit error was caught before implementation: the first counterfactual assumed damaged Impidimp would become full-HP Morgrem. CABT correctly preserves 60 damage through evolution, producing Morgrem at 40/100, still KO'd by 70. The invalid evolution-bridge intervention is rejected and explicitly retained as negative evidence.

**Interpretation**

The attack-continuity story is falsified for the inspected Archaludon episode and must not be implemented. The Dragapult promotion choice is a real, narrow survivability ordering issue, but it is not yet native-win evidence. The smallest next step is a sanitized fixture that preserves exact current HP, post-checkup Froslass damage, duplicate physical identities, public opponent energy/attack threat, and damage counters through evolution.

**Decision**

`REJECT ARCHALUDON ATTACK-CONTINUITY ABLATION`; `KEEP DRAGAPULT PROMOTION-SURVIVABILITY ALIVE FOR FIXTURE ONLY`; `NO STRATEGIC AUTHORITY YET`.

**Reason**

Only the Dragapult promotion has a legal option that strictly survives the observed 70-damage line. One retrospective state cannot justify a global promotion rule or establish win impact.

**Files created/changed**

- Updated `ptcg-rl/progress.md` only.
- No replay, source, test, package, deck, model, or live object changed.

**Artifact paths**

- Archaludon replay SHA-256 `c0a6993f3a8f299b8a0242b1fc2524ec6b7a4d1dfc5506f89502952119cfc3ac`.
- Dragapult replay SHA-256 `e0658d6a180a1e527979dc792ba621bbbc390c73bdf8e43f6ae29168c682abcc` (recorded in the restricted manifest).
- Qualified tarball path `.chatgpt/tmp/submissions/kptcg-grim-control-v1.tar.gz`.

**Next action**

Commit this audit. Then delegate a fixture-only change in an experimental copy/test path that proves the corrected state and expected threat-aware ranking without touching the qualified tarball or granting the heuristic live authority.

**Commit SHA**

`9f6315794975bb87ca2bbd251c120a0bdcefbac1` (`docs: audit current Grim loss states`).

## 2026-08-09T16:41:34+05:30 - Step 12: Sanitize Promotion Fixture And Audit Reuse Point

**Objective/question**

Prove the corrected Dragapult promotion-state arithmetic in a safe reproducible fixture and determine whether an existing historical guard can be reused before granting any experimental policy authority.

**Evidence inspected**

- Corrected public-state values from replay `91269364` and qualified package behavior.
- All historical v22 promotion guards plus their `manual_guards` wiring in current-deck-proxies and grim-source-oracle.
- Qualified top-level mirror, strategic, human-controller, and downstream action chain on the exact ToActive observation.

**Important commands**

```text
rtk uv run python .chatgpt/tmp/grim-promotion-liability-fixture/check_fixture.py
rtk uv run ruff check .chatgpt/tmp/grim-promotion-liability-fixture/check_fixture.py
rtk uv run python -m py_compile .chatgpt/tmp/grim-promotion-liability-fixture/check_fixture.py
rtk sha256sum .chatgpt/tmp/grim-promotion-liability-fixture/fixture.json .chatgpt/tmp/grim-promotion-liability-fixture/check_fixture.py
```

Historical guards were invoked read-only on the retained private observation; no arena game or policy edit occurred.

**Test/inspection size**

- One positive sanitized five-option ToActive fixture.
- Two negative controls: uncharged Dragapult and no option surviving 70.
- All 23 existing manual guards evaluated on the exact live state.
- A second Dragapult ToActive replay state at step 123 audited as a false-positive boundary because it contains no Impidimp.

**Results and metrics**

- Fixture checker: PASS; Ruff: PASS; bytecode compilation: PASS.
- Positive survivor set under Jet Headbutt 70 is exactly `Froslass73` and `Munkidori77`; Phantom Dive 200 survivor set is empty.
- Evolution assertion preserves 60 damage: Impidimp `10/70` becomes Morgrem `40/100`, not full HP.
- Current exact package choice is index 4 fresh Impidimp; preferred Munkidori is a declared hypothesis with `win_authority=false`.
- All 23 historical guards returned `None`; none expresses the five-option, damaged, late-prize state. The nearest energized-Munkidori guard requires exactly three full-HP options and an early prize shape.
- The mirror expert and human controller both favor fresh Impidimp; later stages preserve it. `manual_guards` is only a coalition voter, so extending it would not reliably change final authority.
- Smallest future extension point is an early `context==4` branch in `human_controller._direct_selection`, using public Dragapult ID/energy, factual option identities, projected post-checkup HP, and semantic abstention.

**Failures / invalid actions / fallbacks**

- Initial fixture audit found and corrected two evidence defects before commit: replay hash was null/mislabelled and Munkidori current HP had been conflated with max HP. Final fixture binds replay SHA-256 `e0658d6a180a1e527979dc792ba621bbbc390c73bdf8e43f6ae29168c682abcc`, states no replay body is embedded, and uses max HP 110 for both Munkidori.
- No runtime, legality, native, fallback, or external action occurred.

**Interpretation**

The fixture now supports exactly one implementation hypothesis and its abstention boundaries. It does not claim the opponent would choose Jet Headbutt counterfactually or that survival wins the game. Existing guards should not be broadened blindly; a tiny top-level experimental branch is both simpler and more causally auditable.

**Decision**

`FIXTURE PASS`; `AUTHORIZE ONE EXPERIMENTAL GUARD IMPLEMENTATION`; `NO NATIVE SCREEN UNTIL REPLAY/UNIT QUALIFICATION`; `NO LIVE AUTHORITY`.

**Reason**

The state arithmetic, legal alternatives, and current policy cause are now independently explicit, while negative controls bound the proposed activation.

**Files created/changed**

- `.chatgpt/tmp/grim-promotion-liability-fixture/fixture.json`
- `.chatgpt/tmp/grim-promotion-liability-fixture/check_fixture.py`
- `ptcg-rl/progress.md`
- No qualified package, replay body, strategic source, deck, model, or external object changed.

**Artifact paths**

- Fixture: 2,807 bytes, SHA-256 `c877c089eb506482bb51c63bcf1dbe54174b91e134cf08cafc0355e0be9a1e99`.
- Checker: 3,653 bytes, SHA-256 `7aa83a0ec22fcd215f79884071ca02c766e14db93d419f4276edba887a2d0baa`.

**Next action**

Stage and commit only the two safe fixture files plus `progress.md`. Then create an experimental candidate copy via the existing scratch builder, add the minimal top-level guard plus focused abstention tests, and replay-audit exact activation before any native strength run.

**Commit SHA**

`c71a116290b2f3c5239e2e6acd8bfea127bc1a8c` (`exp: add Dragapult promotion liability fixture`).

## 2026-08-09T17:07:55+05:30 - Step 13: Reject Dead Guard Integration Draft

**Objective/question**

Implement the smallest experimental Dragapult promotion guard and prove that it changes only the intended exact replay state before running any native game.

**Evidence inspected**

- Scratch builder and checker under `.chatgpt/tmp/grim-promotion-liability/`.
- Generated candidate copied from the unchanged `grim-punk-floor4` source.
- Guard unit matrix and direct `_direct_selection` replay audit supplied by the implementation agent.
- Lead read-through of the actual `main.agent -> human_controller.choose` routing path.

**Important commands/inspection**

The implementation agent ran the fixture checker, Ruff, `py_compile`, 17 fresh-process guard cases, 146 fresh isolated direct-selection replay calls, and a construction-only `NativeRulePolicy` load. The lead then inspected `main.py` and `human_controller.choose()` read-only. No native game was run.

**Test/experiment size**

- Direct helper matrix: 17 isolated cases covering the positive state and abstention boundaries.
- Direct-selection replay audit: 73 selection observations, candidate plus control in fresh processes (`146` calls).
- Top-level `main.agent` replay audit: not completed by this draft.

**Results and metrics**

- Helper/direct-selection checks reported zero exceptions, semantic agreement at `72/73`, activation only at step `158`, intended candidate action Munkidori serial 77, control action fresh Impidimp, and abstention at step `123`.
- Receipt correctly binds experimental `main.py`, `human_controller.py`, and deck hashes; qualified tarball SHA-256 remained `e9d4681a5252f563309befc450dd31d8c66171b81455600c9e783b13c6d52657`.
- Lead integration audit found the decisive defect: the guard was inserted only in `_direct_selection`, but the full `human_controller.choose()` path never calls `_direct_selection` for context 4. The generated candidate therefore has no proven top-level behavior change despite its helper-level PASS.

**Failures / invalid actions / fallbacks**

- Integration qualification failure: helper-level evidence was incorrectly presented as package behavior evidence. This is a test-boundary failure, not a native exception or illegal action.
- Top-level activation remains unproven; native error/invalid/fallback/post-terminal counts are not claimed because native games were correctly withheld.

**Interpretation**

A test that bypasses the package's authoritative routing path cannot qualify a strategic intervention. The hypothesis remains alive, but this exact integration draft is rejected. The minimal correction is one legal guard call near the start of `human_controller.choose()`, before baseline/coalition routing, with the redundant dead call removed.

**Decision**

`REJECT FIRST INTEGRATION DRAFT`; `KEEP NARROW HYPOTHESIS ALIVE`; `BLOCK NATIVE SCREEN UNTIL TOP-LEVEL REPLAY PARITY PASSES`.

**Reason**

The intended logic is bounded and its helper behavior is correct, but it is not on the actual package execution path. Running native games now would falsely test an unchanged controller.

**Files created/changed**

- `.chatgpt/tmp/grim-promotion-liability/build_candidate.py`
- `.chatgpt/tmp/grim-promotion-liability/check_guard.py`
- Generated private scratch candidate under `.chatgpt/tmp/grim-promotion-liability/arena-agents/grim-promotion-dragapult/`
- Updated `ptcg-rl/progress.md`.
- No qualified tarball, live submission, deck, replay body, or production policy changed.

**Artifact paths**

- Scratch builder/checker and generated candidate: `.chatgpt/tmp/grim-promotion-liability/`.
- Qualified control remains `.chatgpt/tmp/submissions/kptcg-grim-control-v1.tar.gz`.

**Next action**

Move the guard to the single authoritative `human_controller.choose()` path in the scratch build, remove the redundant dead integration, and rerun the actual top-level `main.agent` over all 73 replay selection observations. Require exactly one semantic delta at step 158 and parity everywhere else before any native game.

**Commit SHA**

Pending corrected end-to-end integration and focused commit.

## 2026-08-09T17:13:27+05:30 - Step 14: Correct Guard Entry Point And Top-Level Replay Audit

**Objective/question**

Correct the rejected dead integration without broadening the guard, then test the real package entry point rather than a helper.

**Evidence inspected**

- Implementation-agent report for the rebuilt scratch candidate.
- Fresh isolated top-level `main.agent` candidate/control replay audit over every NNMax selection observation in Dragapult replay `91269364`.
- Generated receipt and qualified-control tarball hash check.

**Important commands/inspection**

The implementation agent rebuilt the scratch candidate, ran the fixture checker, Ruff, `py_compile`, `NativeRulePolicy` construction, and the strengthened `check_guard.py` full-package audit. No native game was run. Lead independent rerun and source-diff audit are the immediate next step.

**Test/experiment size**

- 73 replay selection observations.
- Fresh isolated top-level candidate and control process per observation.
- Focused guard matrix plus explicit step-123 negative boundary.

**Results and metrics**

- Agent-reported top-level exceptions: `0`.
- Semantic parity: `72/73`; sole delta step `158`.
- Step 158 candidate: Munkidori serial 77 at semantic option `[1]`; control: option `[4]` fresh Impidimp.
- Step 123: guard abstains and candidate matches control.
- Guard activation list: `[158]`; fix-minus-break `1-0` against the declared replay-state hypothesis.
- Candidate `human_controller.py`: 24,546 bytes, SHA-256 `566710fecf9e88f22cd3bdd082115323b6f0d8efaa5f9cf371433f08f29b227b`.
- Candidate `main.py`: 10,469 bytes, SHA-256 `2c45168eada3aad6fa7b959df23e74b3f188ff4459a0f8cca6e069a8ef779775`.
- Candidate deck: 252 bytes, SHA-256 `92b92bac9f9163ecff933b3dc39294d2cc154c8684f3c8497877661419ebc59d`.
- Receipt SHA-256 `c6fc4dad6c82ab25adb526042b0ad7cb690bd043e52059c655460f3f7253ff35`.
- Qualified control tarball reportedly remains SHA-256 `e9d4681a5252f563309befc450dd31d8c66171b81455600c9e783b13c6d52657`.

**Failures / invalid actions / fallbacks**

- The rejected first draft is retained as `failed_iteration_dead_integration.json` rather than erased.
- Corrected replay audit reports zero exceptions. Native invalid/fallback/post-terminal counts are not yet available because native execution remains intentionally blocked pending independent audit.

**Interpretation**

Moving the one guarded decision to the authoritative `choose()` entry point repairs the test-boundary defect while keeping the intervention narrow. Replay parity establishes mechanical targeting only; it still does not establish that the alternative wins games.

**Decision**

`PROVISIONAL END-TO-END MECHANICS PASS / INDEPENDENT AUDIT PENDING`; `NO NATIVE STRENGTH VERDICT`; `NO LIVE AUTHORITY`.

**Reason**

The reported package behavior now matches the declared intervention exactly, but lead verification is required before committing or spending native evaluation time.

**Files created/changed**

- Updated `.chatgpt/tmp/grim-promotion-liability/build_candidate.py`.
- Updated `.chatgpt/tmp/grim-promotion-liability/check_guard.py`.
- Added `.chatgpt/tmp/grim-promotion-liability/failed_iteration_dead_integration.json`.
- Regenerated private scratch candidate under `.chatgpt/tmp/grim-promotion-liability/arena-agents/grim-promotion-dragapult/`.
- Updated `ptcg-rl/progress.md`.
- No qualified package, live submission, production source, deck, model, or replay body changed.

**Artifact paths**

- `.chatgpt/tmp/grim-promotion-liability/`
- Qualified control `.chatgpt/tmp/submissions/kptcg-grim-control-v1.tar.gz`.

**Next action**

Lead-audit the exact builder/checker diff and rerun all focused checks, including top-level replay parity and hashes. Commit only the reproducible scripts, retained failed-iteration receipt, and `progress.md` if the audit passes.

**Commit SHA**

Pending independent audit and focused commit.

## 2026-08-09T17:20:55+05:30 - Step 15: Independent Integration Audit Finds Stateful Boundary Gap

**Objective/question**

Independently verify that the corrected helper is the only runtime delta, that the top-level check is real, and that the builder is minimal and preserves package state semantics.

**Evidence inspected**

- Byte diff between untouched `grim-punk-floor4/human_controller.py` and the generated candidate.
- Builder/checker source, sanitized failed-iteration receipt, generated receipt, candidate tree, card metadata, replay-state facts, and qualified tarball identity.
- Independent rerun of the 17-case matrix and 73-observation fresh-isolated top-level audit.
- `human_memory.update()` and its original call order in `human_controller.choose()`.

**Important commands/inspection**

Read-only source diffs, metadata lookup, file enumeration/hash recomputation, fixture check, and `check_guard.py` rerun. No native game, network call, staging, commit, or artifact mutation occurred.

**Test/experiment size**

- Generated candidate tree: 189 files / approximately 8.3 MiB, inspected only to delimit commit scope.
- Guard matrix: 17 fresh processes.
- Fresh-isolated replay comparison: 73 selection observations, candidate and control.
- Stateful chronological replay comparison: not yet present; now required before native execution.

**Results and metrics**

- Independent fresh-isolated audit reproduces zero exceptions, semantic parity `72/73`, sole step-158 activation, and step-123 abstention.
- Runtime diff contains only the guard helper plus one `choose()` call; `_direct_selection` has no remaining hook.
- Card facts independently match: Dragapult 121, Jet Headbutt 70 for one Colorless, Phantom Dive 200, Froslass checkup damage to Ability Pokémon on both sides, Munkidori max HP 110, and exact replay energies Psychic 5 plus Fire 2.
- Generated receipt hashes match; qualified tarball remains SHA-256 `e9d4681a5252f563309befc450dd31d8c66171b81455600c9e783b13c6d52657`.
- Independent audit found a redundant builder insert-then-remove sequence that has no runtime effect but is not acceptable final reproducible logic.
- Lead audit found the more important state-boundary defect: the guard runs before `hm.update(obs)` and returns early on activation. The original controller updates public-state memory on every selection. Fresh-process-per-observation testing cannot prove the absence of downstream state effects.

**Failures / invalid actions / fallbacks**

- Builder minimality failure: one redundant no-op sequence.
- Stateful regression evidence missing: current top-level test resets the process for every observation.
- Native invalid/fallback/post-terminal counts remain unclaimed because the screen is still correctly blocked.

**Interpretation**

The fresh top-level result is genuine but insufficient for a stateful controller. The smallest correct integration must preserve the original memory update before returning the guarded action. A single-process chronological replay regression is the cheapest check for unintended downstream controller-state changes.

**Decision**

`BLOCK COMMIT AND NATIVE EXECUTION PENDING MEMORY-PRESERVING FIX`; `KEEP HYPOTHESIS ALIVE`.

**Reason**

One skipped state update can broaden a nominally one-decision ablation into later decisions. Removing that confound is both smaller and safer than attempting to diagnose it after outcome games.

**Files created/changed**

- Updated `ptcg-rl/progress.md` only during the lead audit.
- Scratch builder/checker/candidate remain uncommitted and are being corrected by the implementation agent.

**Artifact paths**

- `.chatgpt/tmp/grim-promotion-liability/`
- Base source `.chatgpt/tmp/grim-punk-tuning/arena-agents/grim-punk-floor4/`.

**Next action**

Move the guard call after the original memory update, remove the builder no-op and unnecessary tie-break helper, add a chronological one-process replay audit alongside the isolated audit, then rerun all checks and hashes.

**Commit SHA**

Pending corrected stateful integration and focused commit.

## 2026-08-09T17:24:39+05:30 - Step 16: Third Mutable Kaggle Refresh

**Objective/question**

Refresh live Grim and current ladder evidence while the local integration correction proceeds, without downloading another replay or mutating Kaggle.

**Evidence inspected**

- Authenticated competition metadata, current top-20 leaderboard, NNMax submission history/active slots, full public episode metadata for `55372188`, and public Majkel episode metadata for `55333348`.

**Important read-only calls**

The NVIDIA Kaggle skill and authenticated read-only competition/leaderboard/submission/episode endpoints were used. No benchmark-task tool, replay-body download, session, upload, submission, or external mutation occurred.

**Test/inspection size**

- Leaderboard top 20.
- Grim: 36 public episodes plus 1 validation.
- Majkel scoring submission: 202 public episodes plus 1 validation.

**Results and metrics**

- Snapshot UTC `2026-08-09T11:53:59.100Z`.
- Competition deadline remains `2026-08-16T23:59:00Z`; new-entrant deadline `2026-08-09T23:59:00Z`; maximum 5 submissions/day; 6,642 teams.
- Grim `55372188`: `COMPLETE`, public score `800.5`, public W/D/L `19/0/17` over 36 games. This is down from `814.0` at `19/0/15`.
- New loss `91299777` at `11:00:02Z` versus Remielle submission `55373723`.
- New loss and latest episode `91304959` at `11:24:02Z` versus Voyager submission `55376362`.
- The two new episode bodies were not downloaded. These exact IDs are the next candidates for a separately capped retrieval after the current integration milestone.
- NNMax active agents remain Grim `55372188` at `800.5` and Lucario canary `55356773` at `656.7`; current rank field `925` is mutable.
- Majkel `55333348` remains `1230.1`, 202 public games, W/D/L `116/0/86`, latest episode `91289085`. No new public game appeared since the prior snapshot.
- Current leaderboard top five: Majkel1337 `1230.1`, AlphaStarmie `1174.3`, James/Henry `1167.9`, palsystem `1159.4`, MissingNo. `1157.2`.

**Failures / invalid actions / fallbacks**

- Direct private metadata access for the non-owned Majkel submission remained permission-restricted; public leaderboard/episode endpoints supplied the required facts.
- No local game actions or external mutations occurred.

**Interpretation**

Grim's live evidence continues to weaken and is nowhere near the target. This increases the value of concrete new-loss diagnosis, but score pressure does not justify bypassing the guard's stateful integration checks or spending a live slot on an unqualified branch.

**Decision**

`KEEP GRIM ACTIVE AS ONLY QUALIFIED CONTROL`; `NO LIVE REPLACEMENT`; `QUEUE TWO NEW LOSS IDS FOR LATER CAPPED AUDIT`.

**Reason**

No stronger qualified candidate exists. The two new losses are more actionable than the aggregate rating, but their replay bodies must be acquired under a new explicit cap after the bounded current milestone.

**Files created/changed**

- Updated `ptcg-rl/progress.md` only.
- No replay, source, package, submission, model, or external object changed.

**Artifact paths**

- Live submission `55372188`; queued episode IDs `91299777` and `91304959`.

**Next action**

Finish the memory-preserving guard integration and stateful chronological replay check. Then commit that bounded milestone before any capped new-loss retrieval.

**Commit SHA**

Pending current guard-integration milestone commit.

## 2026-08-09T17:29:33+05:30 - Step 17: Memory-Preserving Guard Build And Stateful Replay Check

**Objective/question**

Remove the remaining builder/state confounds and demonstrate that the one-decision guard does not create later controller differences on the recorded control trajectory.

**Evidence inspected**

- Second corrected scratch builder/candidate/checker report.
- Fresh-isolated and one-process chronological top-level `main.agent` comparisons.
- Final candidate receipt and qualified-tar hash check.

**Important commands/inspection**

The implementation agent rebuilt the scratch candidate, ran the fixture checker, Ruff, `py_compile`, `NativeRulePolicy` construction, the existing isolated replay audit, and a new persistent-process replay audit with startup/deck callback. No native game was run. Final independent rerun/source audit is now in progress.

**Test/experiment size**

- Isolated comparison: 73 selection observations, fresh process per observation/package.
- Stateful comparison: one fresh persistent process per package, startup callback plus all 73 selection observations in chronological order.
- Focused guard matrix and exact step-123 negative boundary retained.

**Results and metrics**

- Builder no-op removed; `_semantic_value` tie-break abstraction removed.
- `human_controller.choose()` now executes the existing `hm.update(obs)` before the sole guard early return.
- Agent-reported isolated audit: zero exceptions, `72/73` semantic matches, sole delta step 158.
- Agent-reported stateful recorded-control-trajectory audit: zero exceptions, `72/73` semantic matches, changed steps exactly `[158]`; startup/deck callback executed.
- This is regression evidence only, not a claim about the counterfactual post-step-158 trajectory or game outcome.
- Final candidate `human_controller.py`: 24,090 bytes, SHA-256 `77801996e2a50b947f5d717d6c4d3af2de3be0c64bfc4dcc729704c00dc2dc1b`.
- `main.py`: 10,469 bytes, SHA-256 `2c45168eada3aad6fa7b959df23e74b3f188ff4459a0f8cca6e069a8ef779775`.
- Deck: 252 bytes, SHA-256 `92b92bac9f9163ecff933b3dc39294d2cc154c8684f3c8497877661419ebc59d`.
- Receipt SHA-256 `17139708d6cbb97e3cce32fe024920d59425e9892520737ba80bf4aa0ef7543a`.
- Qualified tarball reportedly remains `e9d4681a5252f563309befc450dd31d8c66171b81455600c9e783b13c6d52657`.

**Failures / invalid actions / fallbacks**

- No reported test/replay exceptions after correction.
- Native invalid/fallback/post-terminal counts remain unclaimed because no native game has run.
- Final independent audit confirmed the chronological check uses exactly two persistent workers, each with a startup/deck callback and all 73 selection observations; hashes match. No native reliability counters are claimed yet.
- Lead rerun after the environment handoff independently reproduced both replay PASS lines and the 17-process matrix; Ruff and `py_compile` also pass. The interrupted pre-handoff checker result was not inferred or counted.

**Interpretation**

The implementation now preserves the original state update and removes unnecessary builder logic. If independently reproduced, it is mechanically narrow enough to commit and advance to the two-game Stage A native smoke. Replay parity still grants no outcome authority.

**Decision**

`STATEFUL REPLAY MECHANICS PASS`; `AUTHORIZE TWO-GAME STAGE A NATIVE SMOKE`; `NO NATIVE STRENGTH VERDICT`; `NO LIVE AUTHORITY`.

**Reason**

Both test modes independently reproduce exactly the intended single semantic change, the known state-update confound is removed, and the generated package/qualified-control hashes match.

**Files created/changed**

- Updated scratch builder/checker and regenerated private candidate under `.chatgpt/tmp/grim-promotion-liability/`.
- Updated `ptcg-rl/progress.md`.
- No qualified package, live submission, production source, deck, replay body, or external object changed.

**Artifact paths**

- `.chatgpt/tmp/grim-promotion-liability/`.

**Next action**

Commit only `build_candidate.py`, `check_guard.py`, `failed_iteration_dead_integration.json`, and `progress.md`. Then run exactly one native game in each candidate policy slot versus `dragapult-ex`, stopping on any reliability defect.

**Commit SHA**

`2a08d53c38ace873f12b07b138852e687444a45b` (`exp: qualify Dragapult promotion guard integration`).

## 2026-08-09T19:44:32+05:30 - Step 18: Launch Fixed Stage A Native Mechanics Smoke

**Objective/question**

Verify that the exact experimental candidate loads, completes a native CABT game in each policy slot, and retains zero reliability defects before any outcome screen.

**Evidence inspected**

- Independently qualified scratch candidate and unchanged `dragapult-ex` native rule opponent.
- Existing repository-native `ptcg g1 arena-one` command contract.

**Important command/design**

Two fresh bounded `arena-one` processes are authorized, sequentially:

- Candidate slot 0, opponent slot 1, policy seed `2026080910`, game ID `grim-promotion-stagea-slot0-20260809`.
- Opponent slot 0, candidate slot 1, policy seed `2026080911`, game ID `grim-promotion-stagea-slot1-20260809`.

Both use the official sample engine root, official private card data, request cap 20,000, game timeout 180 seconds, and a bounded outer timeout. Native trajectories remain system-entropy draws and are not paired by these policy seeds.

**Test/experiment size**

- Planned maximum: exactly 2 games, one per candidate policy slot.
- Stop after game 1 on any nonzero exit, timeout, malformed/missing terminal output, invalid selection, fallback, post-terminal action, or unexplained failure.

**Results and metrics**

- Agent-reported completion: candidate W/D/L `1/0/1`; slot 0 won at reward `+1`, slot 1 lost at reward `-1`.
- Slot 0: actual first player 0, 178 requests / 179 transitions, wall/CPU `0.528/0.521s`, peak RSS 58,368,000 bytes, mean/max policy latency `1.195/4.135ms`.
- Slot 1: actual first player 1, 164 requests / 165 transitions, wall/CPU `0.464/0.464s`, peak RSS 57,356,288 bytes, mean/max policy latency `1.000/4.133ms`.
- Lead JSON recomputation confirms both processes exited 0 with status `pass`; latency-array lengths exactly equal engine-request counts and every latency is finite/nonnegative.

**Failures / invalid actions / fallbacks**

- Lead-confirmed invalid selections `0`, fallbacks `0`, post-terminal actions `0`, failure kind null, and both stderr files exactly 0 bytes. Failure directories were absent rather than empty because no failure capsule was emitted; the agent's wording was corrected during audit.
- Before/after hash files are byte-identical, SHA-256 `6924bbb210d1c4880fc283b179df551bf956e30eddf8fabcfe9a31e82feee8e7`; qualified tar remains `e9d4681a5252f563309befc450dd31d8c66171b81455600c9e783b13c6d52657`.
- Slot stdout SHA-256: slot 0 `6dd40fba13369911589ea878a3f5b758675dec0de977f88594578c4bb043e7fa`; slot 1 `aa31bf77664393d66f287ea515c077681a658254f365dc74205d018bb61652a0`.

**Interpretation**

This is mechanics evidence only. Two native outcomes cannot support a win-rate, matchup, promotion, or live-submission claim.

**Decision**

`STAGE A MECHANICS PASS`; `AUTHORIZE FIXED TARGETED STAGE B SCREEN`; `NO STRENGTH VERDICT`; `NO LIVE AUTHORITY`.

**Reason**

Replay callbacks cover the rare branch, while one native process per policy slot is the smallest check for loader, lifecycle, seat, and terminal integration.

**Files created/changed**

- Expected private scratch outputs only under `.chatgpt/tmp/grim-promotion-liability/stage-a-*`.
- Updated `ptcg-rl/progress.md`.
- No policy source, qualified tarball, live submission, deck, model, or external object changed.

**Artifact paths**

- Candidate `.chatgpt/tmp/grim-promotion-liability/arena-agents/grim-promotion-dragapult/`.
- Stage A outputs/failures `.chatgpt/tmp/grim-promotion-liability/stage-a-*`.

**Next action**

Commit this audited result. Then prepare and audit a resumable Stage B runner for the already fixed 240-game Dragapult-only screen; predeclare the exact run ID/seed design and kill rules before launch.

**Commit SHA**

Pending completed Stage A result milestone.
