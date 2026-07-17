# G0 Review and Next Directions

Review date: 2026-07-17  
Reviewed report: `PROGRESS_REPORT.md`, run `G0-local-20260717`  
Target: top-20/gold finish in Pokémon TCG AI Battle

## Decision

**G0 remains blocked. Do not begin G1 yet.**

Most of the local implementation is good: the asset import is reproducible, hashes match, the native engine completed a real start/select/finish probe, lint and unit tests pass, and the current staging audit found no restricted paths. The block is not a failure of the implementation. It is missing gate evidence and repository exposure risk.

The archive-size limit and runtime family are now sufficiently resolved from first-party Kaggle sources: the simulation agent limit is `202400 KB`, and the pinned Kaggle image is `gcr.io/kaggle-images/python:v163`, whose source is Python 3.11-based. The exact Python 3.11 patch and the competition timeout still require an official-runtime/package probe. Those two remaining unknowns do not need to hold G1 after the security, regression and clean-clone requirements below pass, but they must remain visible and block final submission qualification until verified.

## What passed

| Area | Evidence | Review |
|---|---|---|
| Asset provenance | 75 imported files; 327,589,562 official bytes; hashes recorded | Pass |
| Native loading | Engine library loaded | Pass |
| Native lifecycle | Start, at least one selection, and finish after correcting the sentinel check | Pass, pending regression test |
| Card data | 2,022 rows / 1,267 IDs with consistency check | Pass |
| Python quality | Ruff clean; 4 unit tests pass | Pass for G0 scope |
| Current staged-file audit | No currently staged restricted paths | Pass, but does not inspect history |
| Cost/scope | Local-only, USD 0, no later gate started | Pass |
| Preservation of user edit | Existing `CODEX_MASTER_PROMPT.md` change remained unstaged | Pass if the user confirms it is intentional |

## Blocking findings

### 1. Public-history exposure

The report says the existing public repository previously tracked sample-agent artifacts. Untracking current files does not remove blobs from reachable Git history, releases, caches, forks, mirrors or prior clones.

Until the applicable license/competition terms are confirmed, treat those bytes as restricted and already exposed. Freeze pushes. Do not add dashboard or G1 work to the same unsafe remote.

Required evidence:

- remote URL and current visibility, reported without credentials;
- a read-only scan of every reachable local and remote ref, tags and Git LFS objects;
- a release/package/artifact audit;
- offending commit IDs, blob IDs and paths without printing file contents;
- a sanitized private remote with no restricted blobs across reachable history.

Preferred remediation, after explicit user authorization:

1. make the affected remote private immediately;
2. create a new private repository from a sanitized current-tree snapshot, without importing the contaminated history;
3. keep only reviewed source/config/test/documentation files;
4. add ignored private assets through the asset bootstrap after clone;
5. verify the new remote and every reachable ref;
6. separately decide whether the old remote should be archived privately, history-rewritten or deleted.

Changing remote visibility, rewriting history, force-pushing or deleting a remote are external/destructive operations. The local Codex agent must show the audit and request approval before performing them.

If any credential or signed URL ever appeared in history, rotate it; history rewriting is not credential rotation.

### 2. No clean-clone reproduction

The report demonstrates setup in the working repository but not the required second clean clone. G0 requires proof that the repository, lock and asset bootstrap work without relying on untracked local state.

From the sanitized private remote, the next report must show:

- a genuinely new clone directory;
- `uv sync --frozen --group local --group dev` without modifying the lock;
- asset bootstrap/verification from explicit private archive paths;
- `ptcg doctor` and the native probe;
- lint and unit tests;
- current-tree and full-history restricted-file audits;
- final clean worktree;
- matching commit and lock hashes between source and clone.

### 3. Missing regression for the native result sentinel

The original probe treated ongoing `result=-1` as truthy and skipped selection. The correction is plausible, but a test must prevent recurrence.

Add tests proving:

- ongoing result `-1` enters selection logic;
- every terminal result bypasses selection;
- a native smoke run records `selection_count > 0`;
- the smoke reaches a declared terminal result;
- stale terminal selection fields cannot trigger a post-terminal engine action.

### 4. Local runtime does not match the official runtime family

The current environment was locked and tested with Python 3.12.13, while the official pinned Kaggle simulation image is Python 3.11-based. Python 3.12.13 is acceptable as a secondary local-development compatibility target, but it is not the primary runtime-matching profile and should remain labeled `provisional_local`.

Before choosing dependencies that affect the submitted agent:

- install or select an approved Python 3.11 interpreter;
- establish the runtime-matching local/submission profile under Python 3.11 without silently rewriting the existing lock;
- document whether this requires a compatible shared lock or separate, explicitly named local/submission locks;
- test imports, unit tests and the native lifecycle under Python 3.11;
- optionally retain Python 3.12 as a secondary compatibility job;
- keep dashboard dependencies in a separate optional group so they cannot enter the submission environment;
- capture `sys.version`, ABI/platform information and installed package versions from the first official-runtime or submission-like probe;
- use that probe to resolve the exact Python 3.11 patch.

## Verified host facts and remaining provisional fields

Record these values in the authoritative competition/runtime configuration with source and verification timestamp:

- final deadline: `2026-08-16T23:59:00Z`;
- entry/team-merger deadline: `2026-08-09T23:59:00Z`;
- submissions: 5 per day and 2 active/scored agents;
- package: `.tar.gz` with `main.py` and `deck.csv` at archive root;
- simulation agent package hard limit: `202400 KB`;
- internal operational package target: below `190 MB` to preserve headroom;
- runtime image: `gcr.io/kaggle-images/python:v163`;
- runtime family: Python 3.11.x; exact patch still provisional;
- current raw simulation settings: `agentDiskKb=12388608`, `agentRamKb=12815744`, `agentCpuCoresPercent=200`, `enableInternet=false`—approximately 11.81 GiB disk, 12.22 GiB RAM and 2 CPU cores;
- timeout: unresolved because the report's 600-second value conflicts with a different value in current environment source and no decisive competition-runtime value was verified.

Do not retain the report's 1.6-vCPU/8-GiB resource values as current truth. Do not turn either timeout candidate into a hard-coded limit until the exact supplied competition package or a validation episode resolves it.

Implement two doctor policies for the two remaining provisional values—the exact Python patch and timeout:

- `development`: show a visible warning but do not stop G1 after all other G0 blockers pass;
- `submission`: fail qualification until the exact runtime has been probed and a safe timeout policy has been tested.

Preserve the primary-source receipt, access time and raw field name for each value. Do not substitute the general competition upload limit for the simulation agent limit.

## Exact next-action order

### Step 1 — Freeze and audit

- Stop pushes to the current public remote.
- Perform the read-only current-tree, full-history, LFS, tag, release and remote-visibility audit.
- Preserve a redacted audit report.
- Ask the user for approval of the remediation target.

**Stop condition:** the remote or exposure scope is still unknown.

### Step 2 — Establish the sanitized private source of truth

- Create or select the approved private remote.
- Import only the sanitized current source tree.
- Verify denylist and `.gitignore` before private asset bootstrap.
- Confirm no restricted content in all reachable refs.
- Preserve old exposure as an incident record; do not pretend rewriting makes prior exposure disappear.

**Stop condition:** any restricted blob remains reachable.

### Step 3 — Close the sentinel regression

- Add the result-sentinel unit and native integration regressions.
- Run all G0 tests.
- Record the corrected commit.

**Stop condition:** the smoke has zero selections, acts after terminal, or does not reach terminal.

### Step 4 — Establish the Python 3.11 runtime-matching profile

- Select an approved Python 3.11 interpreter.
- Update the authoritative runtime configuration with the verified image, package and resource fields above.
- Decide and document the lock strategy; do not silently rewrite the working Python 3.12 lock.
- Run environment import, unit, doctor and native lifecycle checks under Python 3.11.
- Keep the exact patch and timeout visibly provisional until probed.

**Stop condition:** the engine or submission-bound dependencies do not work under Python 3.11.

### Step 5 — Prove a fresh clone

- Clone the sanitized private remote into a new directory.
- Run the frozen Python 3.11 environment setup and complete G0 acceptance commands.
- Verify lock and commit identity and a clean worktree.

**Stop condition:** setup depends on files not produced by the documented bootstrap.

### Step 6 — Reissue the G0 report

The replacement report must include:

- private-remote verification and history-audit summary;
- fresh-clone path identifier, commit and lock hashes;
- regression test names/results;
- native selection count and terminal result;
- Python 3.11 runtime-profile evidence and the disposition of the earlier Python 3.12 lock;
- authoritative `202400 KB` package limit and current resource settings;
- exact-Python-patch and timeout probe status;
- official-source receipts with verification timestamps;
- a reviewed disposition for the pre-existing master-prompt edit;
- final clean worktree.

### Step 7 — Review and authorize G1

Once Steps 1–6 pass, authorize G1 even if the exact Python patch and timeout remain provisional. Keep those two fields prominent in the dashboard and block final submission qualification until resolved.

## Dashboard timing

Do not build new dashboard code in the contaminated public repository.

After the sanitized private repository exists, dashboard Phase D0 may run alongside the G0 re-report/G1 preparation with a strict four-hour initial cap. It is an observability workstream, not a new critical-path gate. If the polished UI cannot be completed inside the cap, stop after:

1. structured report/run ingestion;
2. an overview page;
3. gate/blocker history;
4. experiment/run table including failures;
5. a reliable one-command local server.

Then continue G1 and improve the dashboard incrementally as real data arrives.

## Reviewer instruction to give local Codex now

> G0 remains blocked. Freeze pushes and do not start G1. First perform a read-only remote/history/LFS/release exposure audit and report the exact restricted paths/blobs without printing their contents. Ask before changing remote visibility, creating/replacing a remote, rewriting history, force-pushing or deleting anything. After approval, establish a sanitized private repository, add the ongoing-result/terminal regression tests, establish and test the primary Python 3.11 runtime profile, prove G0 from a genuinely fresh clone with an unchanged approved lock, and issue a replacement progress report. Record the verified `202400 KB` agent-package limit and current raw resource settings. Keep only the exact Python 3.11 patch and timeout provisional; warn in development and fail final submission qualification until both are probed. Do not begin the dashboard until the sanitized private repository is the source of truth.

## Primary-source references

- [Official Kaggle environment Dockerfile](https://github.com/Kaggle/kaggle-environments/blob/master/docker/Dockerfile) — pins the simulation base image to `gcr.io/kaggle-images/python:v163`.
- [Official Kaggle Python image v163 release](https://github.com/Kaggle/docker-python/releases/tag/bf0b407a5ed73626191ae2259063a0090ae36666c8f00ffdfae3fb543eae750d) — source for the Python 3.11-based image family.
- [Official competition submission instructions](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/overview/how-to-submit-to-this-competition) — archive layout and submission workflow.
- [Official competition timeline](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/overview/timeline) — competition and entry deadlines.
- Kaggle HostService `GetCompetitionSimulationSettings` for competition ID `116727` — raw source for `submissionSizeLimitKb` and current agent disk/RAM/CPU/internet fields; preserve the response receipt in project provenance.
