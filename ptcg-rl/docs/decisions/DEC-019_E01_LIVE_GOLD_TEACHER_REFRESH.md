# DEC-019 — Supersede stale Luca expansion and probe the current rank-1 teacher

Status: Accepted  
Date: 2026-07-27  
Scope: E01-A live gold-teacher refresh only

## Context

The user returned after two days and explicitly requested a leaderboard, discussion and project-memory refresh before the next gold-oriented action. The live refresh at `2026-07-27T14:48:51.929778Z` showed that the teacher premise behind DEC-018 had become stale: Luca had moved from rank 2 to rank 14 and had replaced the previously qualified submission, while team `flg` was current rank 1 with live team score `1234.2` and active submission `55004495` with public submission score `1244.2`.

The July 26 official daily replay dataset contains 131 public episodes for exact `flg` submission `55004495`, with all four seat/result strata represented. Current ranks 2 and 3 have 128 and 134 retained episodes respectively. The smallest pair for the rank-1 submission with opposite teacher seats and opposite teacher results totals only 3,996,398 bytes.

Recent official discussion confirms that the competition remains best-of-one and that episode frequency will increase after the deadline. Public notebook sharing closes on August 2, 2026 at 23:59 UTC. A July 23 engine bug fix was announced. Community analyses report a rapidly shifting top-band deck meta and mixed outcomes for BC/RL; these observations motivate freshness but are not qualification or authorization evidence.

## Decision

1. Supersede DEC-018 as the active next action without executing it. Its 51-file Luca request remains unauthorized, unconsumed and absent on disk.
2. Select current rank-1 team `flg`, exact active submission `55004495`, as the next teacher candidate.
3. Prepare and, under the user's current explicit “proceed with next step” instruction, execute exactly the following two-file probe from dataset `kaggle/pokemon-tcg-ai-battle-episodes-2026-07-26`, version 1:

| Episode | File | Bytes | flg seat | flg result | Opponent |
|---:|---|---:|---:|---:|---|
| 88302734 | `88302734.json` | 624,407 | 1 | loss | Pokemon Siuuuu (`54977294`) |
| 88333037 | `88333037.json` | 3,371,991 | 0 | win | Dries @ Tufa Labs (`55002825`) |

Exact transfer cap: **3,996,398 bytes**.

## Required review

For each file independently verify:

- exact file name, byte count and downloaded SHA-256;
- exact episode, team and submission binding;
- schema and CABT environment identity;
- observed module version, requiring the two files to match each other;
- exact 60-card rank-1 teacher deck hash, requiring equality across both files;
- current-card construction compatibility;
- aggregate lagged request/action alignment;
- rank-1 teacher meaningful decision count;
- detected deck archetype as contextual evidence only.

## Authorization boundary

The user's instruction authorizes only the exact two files above. It does not authorize:

- any DEC-018 Luca file;
- a third `flg` replay or any agent log;
- overwrite of an existing output directory;
- raw replay, step, request, option, observation, action-sequence or card-list exports;
- training labels, BC, PPO, self-play, optimizer steps or external compute;
- notebook publication, model publication, deck freeze or competition submission.

Execution must stop after the exact two-file review whether it passes or fails. Any broader rank-1 screening batch requires a separately frozen request and explicit approval.

## Evidence

- `reports/artifacts/raw/e01-live-gold-refresh-v1.json`
- `configs/e01_luca_screening_expansion_request_v1.json`
- `reports/artifacts/e01-luca-same-version-calibration-review-v1.json`

## Revisit trigger

Revisit if the current active submission, selected episode metadata, dataset version, exact byte counts, output path, engine/module identity, recovered deck hash, live competition rules or authorization boundary changes.
