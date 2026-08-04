# DEC-021: E01 Current Rank-1 Dragapult Screening Expansion

Status: Accepted

Date: 2026-07-27

## Context

DEC-019 refreshed the live competition state and selected current rank-1 `flg`
submission `55004495`. DEC-020 then transferred and independently reviewed a
balanced 12-file calibration batch. Every calibration replay is schema version
1, CABT `1.0.0`, module `1.32.2`, exact Dragapult deck multiset SHA-256
`89e6155f25310ee695c0761c85d3ae8e44f376456ff0539231820f8e803f2d5e`,
current-card construction compatible and action aligned.

The completed rank-1 probe and calibration expose 1,386 accepted teacher
decisions. The E01 screening floor is 5,000 teacher decisions, leaving a
3,614-decision shortfall.

The minimum observed calibration density is
`16.446242027673883` teacher decisions per MiB. Applying the frozen 110%
coverage multiplier gives a minimum metadata sizing target of exactly
253,462,708 bytes. This is a sizing projection, not a guarantee of accepted
decisions.

## Decision

Prepare exactly 38 named July 26 dataset files totaling exactly 254,237,550
bytes for a current rank-1 Dragapult screening expansion. The frozen selection
is balanced across teacher seat and result strata:

- `seat_0_loss`: 10 files
- `seat_0_win`: 10 files
- `seat_1_loss`: 9 files
- `seat_1_win`: 9 files

The selection uses only public episode metadata and dataset file sizes. It
excludes all 14 episodes already transferred under DEC-019 and DEC-020.

## Acceptance rule

A transferred file may contribute teacher decisions only when independent
review proves all of the following:

1. schema version `1`, CABT `1.0.0` and module version exactly `1.32.2`;
2. the frozen `flg` submission/team metadata binding for submission `55004495`;
3. exact teacher deck multiset SHA-256
   `89e6155f25310ee695c0761c85d3ae8e44f376456ff0539231820f8e803f2d5e`;
4. current-card construction compatibility;
5. valid lagged full-action alignment for every active request;
6. no duplicate episode or file outside the frozen list.

A nonmatching file is rejected from decision counts. The 254,237,550-byte
projection does not guarantee that the 5,000-decision floor will pass.

## Authorization boundary

This decision does **not** authorize downloading any of the 38 replay bodies.
The exact request remains `READY_UNAUTHORIZED` until a new explicit user
approval binds its final SHA-256.

The request excludes:

- overwrite;
- agent logs;
- any replay outside the 38 named files;
- raw replay, step, action, observation, option, request or card-list exports;
- training-label creation;
- behavior cloning or PPO optimizer steps;
- external compute, notebook launch, model publication or submission.

## Stop conditions

After an approved transfer, independently review every file, publish accepted
and rejected counts, consume the one-time authorization and stop whether the
5,000-decision screen passes or remains blocked. Any confirmation corpus,
second teacher, training, evaluation, deck freeze or submission requires a new
decision and explicit approval.
