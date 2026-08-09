# Codex Execution Journal

## CURRENT STATE / RESUME HERE

Updated: 2026-08-09T15:16:37+05:30

- Best live agent: unchanged qualified Grimmsnarl/Froslass Damage-Transfer Control, Kaggle submission `55372188`, freshly verified `COMPLETE` at public score `817.3`. It has 21 public games, 12 wins and 9 losses, plus one successful self-play validation episode. This is stronger than the two-game snapshot but remains far below the 1000+ target and too small for a settled strength claim.
- Best validated local control: unchanged package `.chatgpt/tmp/submissions/kptcg-grim-control-v1.tar.gz`, 3,640,195 bytes, SHA-256 `e9d4681a5252f563309befc450dd31d8c66171b81455600c9e783b13c6d52657`. Do not rebuild or modify it.
- Best local candidate: no derivative is promoted above the unchanged Grim control. The active candidate family is the exact-current-Majkel-deck 201-game history-aware MAIN controller (`direct`, `gain>=0.20`, `c0.70`, optionally `c0.90`). Its native loader integration is now fixed and mechanically clean in one game per seat, but actual strength remains unknown.
- Active hypothesis: improved chronological semantic imitation may transfer into native wins once the now-proven sibling-import defect is removed. This remains a strength hypothesis, not a promotion claim.
- Most recent decisive evidence: the minimal loader change is committed and mechanically clean in both seats. Separately, five capped live Grim loss replays expose one attackless Archaludon loss plus repeated public signs of bench liability, attack-continuity failure, and unfinished prize routes; these are observational hypotheses only and do not justify a global heuristic.
- Exact next task: let the managed 320-game diverse native screen finish, audit its per-game journal and aggregate, and reject the branch or authorize an independent larger confirmation from outcome evidence.
- Latest relevant session commit: `122e7d1f654d75f4b94a5b7dcda2c6986f8c6ef0` (`fix: load sibling modules in native rule policies`). Pre-session HEAD was `e572280f1b1f90fc908ee5b814fc3ca87ee5dc34` (`Add weighted public deck belief`). Actual Git toplevel is `/home/nnmax/Desktop/kaggle/PTCG`; code lives under `ptcg-rl/`.
- Uncommitted session work: this post-commit journal update only. Five restricted live replay bodies plus a manifest/analysis exist under `.chatgpt/tmp/grim-live-55372188/`; a local `.git/info/exclude` rule now protects that entire directory and none of it may be staged. The strength screen is writing private scratch evidence in its own timestamped directory. Pre-existing worktree state must remain untouched: 17 modified tracked paths and approximately 195 compact untracked entries (85,941 individual untracked files with full expansion) before this file, with tracked diff SHA-256 `dabd0a9451518cfca03c1036e0fb3b0d3e7376fff57e41ba96217a2beb16c1b5`.

`RESUME HERE: audit the in-progress timestamped 320-game history-Majkel strength screen when it completes; do not promote from the small screen.`

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

Pending the next focused evidence/progress commit; restricted replay artifacts will not be staged.
