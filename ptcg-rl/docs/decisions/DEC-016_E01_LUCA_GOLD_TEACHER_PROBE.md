# DEC-016 — Probe the strongest replay-rich gold-region teacher

Status: Accepted

Date: 2026-07-24

## Context

DEC-015 completed the exact same-submission consistency probe for Benarg submission
`54933084`. The two reviewed replays use the same exact 60-card deck hash and both
pass action-alignment checks, but they contain only 65 Benarg decisions against the
5,000-decision E01 screening floor. Benarg's current leaderboard position is also
outside the present gold region, so blindly expanding that teacher is not the
highest-value path.

A new metadata-only screen examined both active submissions for each current top-10
team and intersected their public episodes with version 1 of
`kaggle/pokemon-tcg-ai-battle-episodes-2026-07-23`. No replay body or agent log was
used for this selection.

## Decision

Select Luca submission `54863653` as the next exact teacher candidate.

The selection is based on the combination of:

- current leaderboard rank 2;
- public submission score `1180.9`, within the current gold region;
- 357 exact July 23 replay files in the pinned dataset;
- 181 player-0 and 176 player-1 episodes;
- enough available coverage to plausibly satisfy the 5,000-teacher-decision screen;
- substantially more coverage than the current rank-1 submission's 59 files.

Prepare one bounded two-file provenance and consistency probe using the smallest
pair that places the exact submission in opposite player slots and opposite
terminal results:

1. `87731214.json`, exactly 574,428 bytes, Luca in player slot 1 with reward `-1`;
2. `87615736.json`, exactly 738,793 bytes, Luca in player slot 0 with reward `1`.

The exact combined transfer cap is 1,313,221 bytes.

The probe may determine only:

- replay, schema and module identity;
- public-metadata submission binding;
- exact Luca 60-card deck hashes and cross-episode equality;
- current-card-data construction compatibility;
- aggregate request/action alignment and per-teacher decision counts.

## Authorization boundary

This decision does **not** authorize either file transfer.

A separate exact user approval is required for
`configs/e01_luca_gold_teacher_probe_request_v1.json`.

The request must remain fail-closed with:

- exactly two named files and no third replay;
- exact total bytes of 1,313,221;
- no overwrite;
- no agent logs;
- no raw replay-body, step, action-sequence or observation export;
- no training labels;
- zero optimizer steps;
- no notebook, accelerator, external compute, deck freeze or submission.

## Acceptance interpretation

A passing two-file probe may qualify exact same-submission deck consistency and
action-supervision availability for a gold-region teacher. It does not by itself
satisfy the 5,000-decision screening floor, establish exact historical legality,
authorize a larger replay batch, authorize behavior cloning, or establish policy
competence.

## Evidence

- `reports/artifacts/e01-same-submission-consistency-review-v1.json`
- `reports/artifacts/raw/e01-gold-teacher-coverage-v1.json`
- `configs/e01_luca_gold_teacher_probe_request_v1.json`

## Revisit trigger

Revisit this decision if the leaderboard or submission identity changes materially,
the pinned dataset version or exact file sizes differ, either selected replay is
missing, the two Luca deck hashes disagree, action alignment fails, or any broader
transfer or training action is proposed.
