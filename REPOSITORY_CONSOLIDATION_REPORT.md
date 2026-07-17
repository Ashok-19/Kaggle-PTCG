# Repository Consolidation Report

Date: 2026-07-17  
Outcome: **PASS**  
Active source of truth: **`Ashok-19/Kaggle-PTCG` only**

## Repository Result

| Item | Result |
|---|---|
| Existing repository | `https://github.com/Ashok-19/Kaggle-PTCG` |
| Visibility | `PRIVATE` before and after |
| Old remote `main` | `70b44042b2a5b2e5e361bb897bfb72452c2b2699` |
| Old local `main` | `e5308b5b410f14ce84adce0ca4fd3582f8118f19` |
| Verified clean root | `08be5cec0fac9a954a3fe127a3f51122be4736d1` |
| Dashboard consolidation commit installed on `main` | `d5431efaa7d25dc7147cc20e05c091ac55c15af9` |
| Temporary migration source | local `ee2c65ecefebc5d8413e7a6d0af4c5895e54a653` |
| Remote refs after replacement | only `refs/heads/main`; no tags |

`main` was replaced with `--force-with-lease` pinned to the exact old remote
SHA. Contaminated ancestry was not merged. The temporary migration remote was
removed from the active worktree; its sole remote is now `origin` pointing to
`Ashok-19/Kaggle-PTCG`.

`Ashok-19/Kaggle-PTCG-RL` remains private and unused as a temporary backup. It
is not an active project repository and was not deleted.

## Dashboard Transfer

The reviewed transfer included:

- `ptcg-rl/dashboard/`: frontend source, package lock, Vite/TypeScript config,
  Playwright suite and operating README;
- `ptcg-rl/src/ptcg_rl/dashboard/`: FastAPI app, CLI, Pydantic models and
  allowlisted SQLite ingestion/cache;
- `ptcg-rl/schemas/dashboard/` and `ptcg-rl/tests/dashboard/`;
- `ptcg-rl/reports/{dashboard,events,gates,incidents}/`, including screenshots;
- CLI integration, G0 sentinel/runtime support, project configuration,
  dependency groups, Python lock and documentation required by the dashboard.

Before corrective edits, the staged destination tree and temporary migration
source tree were identical at Git tree
`bab69f208a36ca8b239b93eccb595d36fd8399cb`. The reviewed migration patch
SHA-256 was
`e11ae67614777025ba21628d2f5e37f319aaf9fd68bc2a8669e3905caf735543`.
No `.git`, private asset, engine/card file, sample notebook/archive, credential,
replay body, checkpoint or submission artifact was copied.

Dashboard dependencies remain confined to the `dashboard` dependency group.
The core/submission dependency list remains empty, and core-only test collection
skips dashboard tests when Pydantic is absent.

## Verification

| Check | Result |
|---|---|
| Python Ruff | PASS |
| Python tests | 10 passed |
| Frontend unit tests | 2 passed |
| Frontend production build | PASS; about 205 KB JS and 12 KB CSS |
| Playwright | 3 passed; desktop, roadmap/history and mobile |
| npm audit | 0 vulnerabilities |
| Asset verification | PASS |
| Dashboard rebuild | 13 records, 0 quarantined |
| Restricted staged-path audit | PASS; 0 paths |
| Credential-pattern scan | PASS; 0 matches |
| Fresh-clone worktree | clean, matching `origin/main` |
| Fresh-clone history | 3 commits after this report, one root `08be5cec...` |
| LFS | none |

Fresh-clone history verification found:

- exposing commit `70b44042b2a5b2e5e361bb897bfb72452c2b2699`: absent;
- seven reported restricted blob IDs: 7/7 absent;
- seven reported restricted paths: 7/7 absent across all reachable refs.

The GitHub Packages permission gap is recorded and explicitly waived as
non-blocking for agent development. It will not be reopened. Exact Kaggle
Python patch and timeout verification are deferred to submission/final-model
compatibility and do not block G1.

## Preserved User Work

The pre-existing `CODEX_MASTER_PROMPT.md` edit was not applied or discarded.
It remains at the ignored local path:

`ptcg-rl/private/preserved-user-edits/CODEX_MASTER_PROMPT.pre-sanitize.patch`

SHA-256:
`18fde2231074583a0dabf8f895b70dde3fe1c3705c411f4cd3a877a72ed44e61`.

The legacy untracked G0/dashboard prompts and reports were also moved under
`ptcg-rl/private/preserved-user-edits/legacy-root-20260717/` before lineage
replacement.

## Fixed Compute Scope

- Local: development, dashboard, metadata, filtered acquisition, unit/contract
  tests, tiny engine smoke, packaging and final-model inference/runtime tests.
- Colab/Kaggle: small training smoke, short validation and profiler runs.
- Modal: meaningful self-play, PPO/league training, large evaluation and long jobs.

No RL training or large local benchmark was performed during consolidation.
There is no repository/security blocker to G1 agent implementation.
