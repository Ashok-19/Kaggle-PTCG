# Codex Execution Journal

## CURRENT STATE / RESUME HERE

Updated: 2026-08-09T14:45:01+05:30

- Best live agent: unchanged qualified Grimmsnarl/Froslass Damage-Transfer Control, Kaggle submission `55372188`. The last handed-off snapshot was `COMPLETE`, validation succeeded, with two public wins and provisional score `738.6`; this mutable state has not yet been refreshed in this session.
- Best validated local control: unchanged package `.chatgpt/tmp/submissions/kptcg-grim-control-v1.tar.gz`, 3,640,195 bytes, SHA-256 `e9d4681a5252f563309befc450dd31d8c66171b81455600c9e783b13c6d52657`. Do not rebuild or modify it.
- Best local candidate: no derivative is promoted above the unchanged Grim control. The active candidate family is the exact-current-Majkel-deck 201-game history-aware MAIN controller (`direct`, `gain>=0.20`, `c0.70`, optionally `c0.90`), whose replay fidelity improved but whose native strength is unknown because all history variants failed at integration/runtime before completing a game.
- Active hypothesis: the all-error native screen is a package/import/runtime integration defect, not strategic evidence. A sibling-module import difference between replay audit and `NativeRulePolicy` loading is a concrete hypothesis, but remains unproven until one exact native failure is reproduced and captured.
- Most recent decisive evidence: chronological 201-game wall, oldest 161 train / next 20 tune / newest 20 untouched test. On 564 untouched MAIN decisions, fallback semantic agreement was `0.59397`, direct history model `0.65780`, and tune-selected `gain>=0.20` had 70 fixes versus 33 breaks. Replay package audit reported zero execution exceptions. The intended native script completed 80 control games at about `0.45`, then each history candidate produced 80 errors and the script lost the traceback/evidence when its zero-completion summary divided by zero.
- Exact next task: refresh read-only Kaggle state, then reproduce one candidate failure with one bounded `g1 arena-one` process and retain stdout/stderr before changing code.
- Latest Git commit before this session: `e572280f1b1f90fc908ee5b814fc3ca87ee5dc34` (`Add weighted public deck belief`). Actual Git toplevel is `/home/nnmax/Desktop/kaggle/PTCG`; code lives under `ptcg-rl/`.
- Uncommitted session work: this new `ptcg-rl/progress.md` only. Pre-existing worktree state must remain untouched: 17 modified tracked paths and approximately 195 compact untracked entries (85,941 individual untracked files with full expansion) before this file, with tracked diff SHA-256 `dabd0a9451518cfca03c1036e0fb3b0d3e7376fff57e41ba96217a2beb16c1b5`.

`RESUME HERE: refresh Kaggle facts, then run and capture one exact history-Majkel native failure.`

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

Pending initial progress checkpoint commit.
