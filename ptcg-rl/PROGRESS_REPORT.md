# Progress Report

Milestone/gate: G0 Repository/environment  
Date/time UTC: 2026-07-17T14:27:56Z  
Status: BLOCKED  
Git commit and dirty state: `04fc9038001f33be1bec5d427384c28d2fd9a4e6`; only the user's pre-existing `CODEX_MASTER_PROMPT.md` edit remains unstaged  
Run IDs: G0-local-20260717  
Question this work tested: Can a fresh local repository safely import and verify the supplied private assets and expose reproducible G0 checks without starting later gates?

## Outcome first

- Gate decision: BLOCKED; implementation and local checks pass, but two required official facts remain unresolved
- Most important result: all 327,589,562 official asset bytes match provenance and the native engine loads, starts, selects, and finishes
- Blocker/risk: Kaggle's FAQ exposes placeholders rather than the exact package-size limit and Python interpreter
- Recommended next action: resolve those two official fields and confirm repository privacy; do not start G1 yet

## Changes

- Files/components changed: minimal `src/ptcg_rl` CLI, safe asset importer, native/system doctor, staged-file audit, environment locks, status/provenance files
- New tests/fixtures: archive traversal rejection, minimal asset import/verification, denylist matching, unresolved-config rejection
- Deliberate deviations from plan: Python 3.12 is provisional because 3.11 is absent and the submission runtime is not yet verified.

## Exact commands

```text
rtk git status --short --branch
  existing branch main; pre-existing CODEX_MASTER_PROMPT.md modification preserved
rtk sha256sum ../pokemon-tcg-ai-battle.zip ../sample-agents.zip ../PTCG_RL_Codex_Handoff_v1.0.zip
  official 09ad210b15476f5064c1509addb32a459c777d92d4e4e7db470f9d0c039c3282
  samples  ba6e7ea62d58bd38373e16df30e070631d3b4f5ad6c7d223575e01565490cd41
  handoff  d4d3c1153d1b9b6ce83540916d04a47a889adddc477a47268efac0416a452478
rtk uv lock
  resolved 8 packages with CPython 3.12.13
rtk uv sync --frozen --group local --group dev
  installed pinned project, pytest 8.4.1, ruff 0.12.4
rtk uv run ptcg assets import --official-archive ... --sample-agents ... --research ...
  official: 60 files / 327589562 bytes; samples: 6 / 415961; research: 9 / 104255
rtk uv run ptcg doctor --json runs/preflight/g0-doctor.json
  asset/card/native/license/platform/git/provider checks pass; official_limits fails on two REQUIRED values
rtk uv run ruff check .
  All checks passed!
rtk uv run pytest -m unit -q
  4 passed in 0.02s
rtk uv run ptcg audit-staged
  pass; zero restricted paths
```

## Reproducibility

| Item | Value/hash |
|---|---|
| Code commit | `04fc9038001f33be1bec5d427384c28d2fd9a4e6` |
| Resolved config | `configs/official.json`; exact Python/package-size values intentionally remain REQUIRED |
| Official engine/card assets | archive `09ad210b...c3282`; engine `feafd404...b887`; card CSV `a0ea63cf...f373` |
| Deck canonical hash / file SHA-256 | engineering deck only; main deck not selected |
| Model/checkpoint | not applicable to G0 |
| Opponent population/meta snapshot | not applicable to G0 |
| Replay index/daily versions | not accessed |
| Platform/image/Python/PyTorch/CUDA | Ubuntu 22.04 / x86_64 / Python 3.12.13 / torch deferred / no working local NVIDIA driver |

## Tests and correctness

| Test/gate | Result | Count | Wall time | Evidence |
|---|---:|---:|---:|---|
| Unit tests | PASS | 4 | 0.02s | pytest output above |
| Ruff | PASS | project | <1s | ruff output above |
| Asset hash verification | PASS | 75 files | doctor JSON | all imported files match |
| Native start/select/finish | PASS | 1 probe | doctor JSON | all four lifecycle flags true |
| Card CSV consistency | PASS | 2,022 rows / 1,267 IDs | doctor JSON | duplicate move rows consistent by card name |
| Official runtime facts | BLOCKED | 2 unresolved | Kaggle MCP/pages | exact Python and package size placeholders |

- Invalid actions: not applicable to G0
- Crashes/native errors: 0 in the G0 native probe
- Timeouts: none
- Submission fallbacks: not implemented or used in G0
- Quarantined replay files and reasons: no replay access

## Performance

Not applicable to G0; no G1 benchmark or training was started.

## Compute/cost and artifacts

- Platform/resources: local Ubuntu 22.04 host
- Maximum and actual wall time/cost: local only, USD 0
- Checkpoints/configs/logs/reports with hashes: `asset_hashes.redacted.json`; ignored `runs/preflight/g0-doctor.json`
- Resume/kill test: not applicable; no training/cloud job

## Unexpected behavior and failed attempts

- Kaggle MCP verified the 2026-08-16 23:59 UTC close, five daily/two active submissions, `.tar.gz` layout, `kaggle-environments 1.14.10`, 600-second agent budget, CPU-only 1.6 vCPU and 8 GiB RAM. Its FAQ leaves package size and exact Python as unresolved placeholders.
- The first native probe treated ongoing `result=-1` as truthy and skipped selection. The root check was corrected to `result == -1`; the rerun selected successfully.
- The existing public repository already contained sample-agent artifacts. This change untracks current copies but does not rewrite remote history.

## Decisions requested from reviewer

1. Confirm a private remote/history-remediation plan and provide or identify the resolved official Python/package-size limits.
