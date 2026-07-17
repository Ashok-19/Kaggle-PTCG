# Project Status

Last updated UTC: 2026-07-17T14:25:32Z  
Current Git commit: `04fc9038001f33be1bec5d427384c28d2fd9a4e6` (G0 implementation)  
Worktree: dirty only because the user's pre-existing root `CODEX_MASTER_PROMPT.md` edit remains intentionally unstaged  
Current gate: G0 Repository/environment  
Gate status: blocked  
Next review required before: G1 engine adapter work

## Mission clock

- Official close instant UTC (verified URL/date): 2026-08-16T23:59:00Z; Kaggle MCP competition search/timeline, verified 2026-07-17
- Official close in user timezone: 2026-08-17 05:29 IST
- Days/hours remaining: about 30 days 9 hours at last update
- Architecture freeze (derived T-7): 2026-08-09T23:59:00Z
- Training code/config freeze (derived T-4): 2026-08-12T23:59:00Z
- Packaging freeze (derived T-2): 2026-08-14T23:59:00Z

## Fixed artifact hashes

| Artifact | Version/path | SHA-256 | Notes |
|---|---|---|---|
| Official package | `../pokemon-tcg-ai-battle.zip` | `09ad210b15476f5064c1509addb32a459c777d92d4e4e7db470f9d0c039c3282` | competition-only |
| Engine library/source | ignored `private/assets/official/` | `feafd4046b2f688bdb33a4972c139b78e13e243ab5707ece52c43cf39a34b887` | `libcg.so`; competition-only |
| English card data | ignored private assets | `a0ea63cf7adcb65d35436ce0eb390de6e2e35654a7c67c065a45f4abaa00f373` | 1,267 unique card IDs |
| Sample agents | `../sample-agents.zip` | `ba6e7ea62d58bd38373e16df30e070631d3b4f5ad6c7d223575e01565490cd41` | private engineering reference |
| Research source | `../research-docs/` | `cf0e86e7736e711e42a870f81bba5c676c67391a32f5c1cff06dcf0dc4c63678` | secondary competition context only |
| Handoff bundle | `../PTCG_RL_Codex_Handoff_v1.0.zip` | `d4d3c1153d1b9b6ce83540916d04a47a889adddc477a47268efac0416a452478` | governing implementation bundle |
| Current main deck | not selected | | not selected until D1 |
| Trusted anchor checkpoint | not available | | |
| Challenger checkpoint | not available | | |

## Gate ledger

| Gate | Status | Commit | Evidence/report | Review decision |
|---|---|---|---|---|
| G0 Repository/environment | blocked | `04fc903` | `PROGRESS_REPORT.md`, `runs/preflight/g0-doctor.json` | two official limits unresolved |
| G1 Engine correctness | not started | | | blocked until G0 review |
| R1 Replay/meta pipeline | not started | | | |
| G2 Model/action schema | not started | | | |
| G3a PPO correctness smoke | not started | | | |
| G3b PPO competence | not started | | | |
| D1 Deck selection | not started | | | |
| G4 Modal readiness | not started | | | |
| G5 Main champion | not started | | | |
| G6 Final package | not started | | | |

## Active experiments/jobs

None. G0 performs no replay download, cloud job, training, or external mutation.

## Best verified results

None; training and deck selection have not started.

## Open blockers/questions

1. Kaggle's official FAQ returns unresolved placeholders for the exact submission package-size limit and exact Python interpreter. The current Docker base is `gcr.io/kaggle-images/python:v163`; those two facts are not guessed.
2. The supplied GitHub repository is public and sample-agent artifacts exist in its history. This G0 commit untracks the current copies but does not rewrite or push remote history.
3. The handoff requests Python 3.11, but this machine exposes Python 3.10 and 3.12. G0 provisionally pins 3.12 until the official submission interpreter is verified.

## Decision log

### DEC-001 - Keep private assets out of the existing repository

- Date/evidence: 2026-07-17; the existing remote is public and sample agents were tracked in its initial commit.
- Decision: keep implementation in `ptcg-rl/` under the existing Git repository, untrack current sample-agent files, and keep imported assets under ignored `ptcg-rl/private/`.
- Alternatives: retain a nested repository; rewrite/push remote history.
- Expected effect: the requested existing repository owns the code while no new private asset bytes are committed.
- Risk/rollback: public history still contains prior sample-agent bytes; repository visibility/history cleanup requires an explicit external operation.
- Reviewer approval: user directed use of the existing repository; remote cleanup remains pending.

### DEC-002 - Keep G0 dependencies minimal

- Date/evidence: 2026-07-17; G0 asset and doctor functions require only the Python standard library.
- Decision: pin Python 3.12 plus `pytest` and `ruff`; defer PyTorch/CUDA pins to target-platform preflight.
- Alternatives: install the full future RL/data stack before engine/runtime facts are known.
- Expected effect: reproducible small G0 environment without risking a wrong CUDA wheel.
- Risk/rollback: update the Python/profile locks after official runtime verification.
- Reviewer approval: pending.

## Immediate next actions

1. Obtain the exact package-size limit and Python interpreter from a resolved official competition configuration.
2. Confirm repository privacy or approve a remote history cleanup before any push.
3. Review this blocked G0 report before G1; do not begin engine-adapter work.
