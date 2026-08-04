# DEC-014 — Reconcile E01 Source Schema and Prepare One Provenance Probe

Status: Accepted

Date: 2026-07-24

## Context

DEC-013 reopened E01-A because the currently downloadable daily `manifest.csv` differs from the object recorded by the accepted zero-transfer dry run. Further read-only reconciliation established that the discrepancy is caused by conflating three distinct metadata sources:

1. the current daily manifest exposes raw fields `id`, `create_time`, `agents`, `score1`, `score2`, `data_size`, `file_name`;
2. Kaggle dataset file-list metadata exposes the exact uncompressed file byte count;
3. the public simulation episode endpoint exposes exact nanosecond episode timestamps and both teams and submission IDs.

For all eight accepted candidate IDs, the file-list `total_bytes` values match the accepted `declared_bytes` exactly, and the public episode `createTime` values match the accepted `create_time` exactly after normalizing the trailing `Z` and insignificant zero padding. Each episode is public, completed, contains exactly two agents and now has exact team and submission identity.

The precise per-agent rating field used to derive the accepted `avg_score` and `min_score` is no longer present in the current raw API response or current generated SDK schema. The current manifest's integer `score1` and `score2` fields are not semantically or numerically equivalent. Therefore the original ranking calculation cannot be rerun and no strength, teacher quality or competence claim may rely on those scores.

## Decision

Accept a narrowly scoped source-schema adapter for provenance probing only:

- `episode_id`: public episode API `id`;
- `create_time`: public episode API `createTime`;
- `agent_count`: length of public episode API `agents`;
- `file_name`: dataset file-list `name`;
- `size_bytes`: dataset file-list `total_bytes`;
- teacher/submission identity: public episode API agent `teamId`, `teamName` and `submissionId`;
- rating fields: unresolved and excluded from all new decisions.

Do not rerank the accepted candidate set. Treat it only as a historical acquisition candidate set. For a provenance-only inspection, select the smallest member under independently reproduced file-list bytes: `87703034.json`, exactly 3,641,302 bytes.

The episode is a completed public game between:

- Benarg — team ID `16401597`, submission ID `54933084`, reward `1`;
- junlee789 — team ID `16422150`, submission ID `54775633`, reward `-1`.

Prepare one exact non-authorizing request for this file. The probe may become executable only after separate explicit user approval.

## Probe Boundary

If separately approved, the probe may:

1. download exactly `87703034.json` from `kaggle/pokemon-tcg-ai-battle-episodes-2026-07-23` version 1;
2. reject the transfer unless the downloaded file is exactly 3,641,302 bytes;
3. store the bytes only under `private/g3/e01/provenance-probe-v1` without overwrite;
4. hash the full file;
5. inspect only enough structure to determine exact deck lists or deck hashes, policy or agent version identity, submission binding and whether action-aligned supervision exists;
6. publish only bounded provenance findings, never raw replay steps, observations, actions or labels.

The probe must stop after this one file whether it passes or fails. It may not download agent logs, another replay, a different version, or any training input.

## Non-Authorization

This decision does **not** authorize the file transfer. It does not qualify either submission as a strong teacher, prove deck legality, authorize action-supervision export, behavior cloning, PPO, self-play, external compute, deck freeze or submission.

## Revisit Trigger

Revisit if any bound metadata hash, dataset version, episode identity, submission identity, exact byte count, output path or probe boundary changes, or after the one-file authorization is consumed.
