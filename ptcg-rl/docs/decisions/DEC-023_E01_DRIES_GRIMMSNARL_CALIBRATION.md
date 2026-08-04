# DEC-023 — Prepare a balanced current-rank-1 Dries Grimmsnarl calibration

Status: Accepted

Date: 2026-07-27

## Context

DEC-021 completed the exact `flg` Dragapult screening set with 6,340 meaningful teacher decisions and passed the 5,000-decision E01 screening floor. A later live leaderboard refresh identified `Dries @ Tufa Labs` as rank 1 with active public submission `55002825` and score `1205.2`.

DEC-022 then transferred exactly two opposite-seat/opposite-result Dries replays totaling 1,135,238 bytes. Independent review qualified both as schema `1`, CABT `1.0.0`, module `1.32.2`, exact-deck consistent, current-card construction compatible and action aligned. The recovered 60-card multiset SHA-256 is:

`cafa7652a6349be806d8ac2b9abfdb6c72ca3821f368e0d912e2d989f3b54cdd`

Official card metadata labels the recovered context **Marnie's Grimmsnarl ex**. The probe supplies 27 Dries teacher decisions. Together with the completed `flg` evidence, the project now has two independent recent teacher identities, 54 reviewed episodes and 6,367 meaningful teacher decisions. The confirmation floor remains blocked by 146 episodes and 18,633 decisions.

## Decision

Prepare one exact request for 12 named July 26 version-1 dataset files totaling **60,869,451 bytes**. Select three files in each seat/result stratum using the 20th, 50th and 80th file-byte quantiles after excluding the two consumed DEC-022 probe episodes.

The exact episode IDs are:

- seat 0 loss: `88282349`, `88309616`, `88278502`
- seat 0 win: `88325741`, `88323126`, `88295625`
- seat 1 loss: `88278632`, `88299587`, `88324713`
- seat 1 win: `88325214`, `88314806`, `88323660`

The output quarantine is:

`private/g3/e01/dries-grimmsnarl-calibration-v1`

## File-by-file acceptance boundary

A replay contributes no evidence unless independent review proves all of the following:

- schema version `1`;
- environment `cabt` version `1.0.0`;
- module version exactly `1.32.2`;
- public metadata binding to Dries submission `55002825` at the recorded player index and terminal result;
- exact teacher deck multiset SHA-256 `cafa7652a6349be806d8ac2b9abfdb6c72ca3821f368e0d912e2d989f3b54cdd`;
- current downloadable card-asset construction compatibility;
- complete lagged request/action alignment.

A nonmatching file is rejected from decision counts. Metadata selection does not guarantee module version, deck identity or action alignment.

## Authorization boundary

This decision does **not** authorize downloading any of the 12 replay bodies. The exact request remains `READY_UNAUTHORIZED` until the user separately approves it.

No overwrite, agent log, additional replay, raw replay export, observation, request, option, action sequence, card-list export, training label, optimizer step, training run, external compute job or competition submission is authorized.

## Purpose and limits

The batch is for balanced consistency and decision-density calibration of the current rank-1 Grimmsnarl policy. It does not by itself satisfy the 200-episode or 25,000-decision confirmation floor, prove exact historical deck legality, authorize behavior cloning or guarantee a medal.

## Revisit triggers

Revisit this decision if the exact request changes, any selected output appears without approval, the active teacher submission changes, a file fails the frozen acceptance boundary, or broader replay, training, compute or submission scope is proposed.
