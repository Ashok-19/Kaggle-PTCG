# DEC-020 — Prepare a balanced current rank-1 Dragapult calibration batch

Status: Accepted  
Date: 2026-07-27  
Scope: E01-A current rank-1 teacher calibration only

## Context

DEC-019 refreshed the live leaderboard and superseded the stale Luca expansion. Its exact two-file probe qualified current rank-1 team `flg`, active submission `55004495`, as a strong current teacher. Both replays use CABT module `1.32.2`, the identical 60-card deck hash `89e6155f25310ee695c0761c85d3ae8e44f376456ff0539231820f8e803f2d5e`, current-card construction checks pass, and all 165 aggregate requests align. Official card metadata identifies the recovered deck context as **Dragapult ex**. The pair provides 94 teacher decisions, leaving a 4,906-decision single-teacher screening shortfall.

The July 26 dataset retains 131 exact episodes for submission `55004495`. After excluding the two probe files, all four seat/result strata remain well populated. Metadata alone cannot guarantee replay-body module or deck identity, so every later file must be independently reviewed.

## Decision

Prepare one exact, non-authorizing calibration request containing 12 files: the 20th, 50th and 80th file-byte quantiles within each teacher seat/result stratum. This yields a representative balanced sample below 64 MiB.

| Episode | File | Bytes | flg seat | flg result | Byte quantile |
|---:|---|---:|---:|---|---:|
| 88304411 | `88304411.json` | 4,377,850 | 0 | loss | 0.2 |
| 88312254 | `88312254.json` | 4,954,508 | 0 | loss | 0.5 |
| 88333027 | `88333027.json` | 6,464,753 | 0 | loss | 0.8 |
| 88324168 | `88324168.json` | 4,747,191 | 0 | win | 0.2 |
| 88306996 | `88306996.json` | 6,103,324 | 0 | win | 0.5 |
| 88280071 | `88280071.json` | 7,020,621 | 0 | win | 0.8 |
| 88329376 | `88329376.json` | 2,996,616 | 1 | loss | 0.2 |
| 88286928 | `88286928.json` | 4,415,458 | 1 | loss | 0.5 |
| 88276868 | `88276868.json` | 5,819,313 | 1 | loss | 0.8 |
| 88295387 | `88295387.json` | 4,787,236 | 1 | win | 0.2 |
| 88318931 | `88318931.json` | 5,624,889 | 1 | win | 0.5 |
| 88316351 | `88316351.json` | 6,251,226 | 1 | win | 0.8 |

Exact total: **63,562,985 bytes**.

## Required review if separately approved

For every named file independently verify:

- exact byte count and downloaded SHA-256;
- exact episode/team/submission binding;
- schema version 1 and CABT environment `1.0.0`;
- module version exactly `1.32.2`;
- exact `flg` deck hash `89e6155f25310ee695c0761c85d3ae8e44f376456ff0539231820f8e803f2d5e`;
- current-card construction compatibility;
- aggregate lagged request/action alignment;
- `flg` decision count and decisions per byte/episode;
- Dragapult ex archetype context without exporting the card list.

## Authorization boundary

This decision does **not** authorize downloading the 12 replay bodies. Separate explicit approval of the exact request is required.

Even after approval, the scope excludes agent logs, any replay outside the exact list, overwrite, raw replay/step/request/option/observation/action/card-list exports, labels, BC, PPO, self-play, optimizer steps, external compute, notebook/model publication, deck freeze and submission.

Execution must stop after calibration review whether it passes or fails. Any full 5,000-decision expansion remains separately approval-gated and must be sized from observed Dragapult decision density.

## Evidence

- `reports/artifacts/raw/e01-live-gold-refresh-v1.json`
- `configs/e01_flg_gold_teacher_probe_request_v1.json`
- `reports/artifacts/e01-flg-gold-teacher-probe-review-v1.json`
- `reports/artifacts/raw/e01-flg-dragapult-calibration-candidates-v1.json`

## Revisit trigger

Revisit if the selected metadata, dataset version, exact byte cap, module/deck requirement, output path, active submission or authorization boundary changes.
