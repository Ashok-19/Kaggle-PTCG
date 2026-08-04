# DEC-017 — Prepare a bounded Luca same-version calibration batch

Status: Accepted  
Date: 2026-07-24  
Scope: E01-A public teacher qualification only

## Context

DEC-016 executed exactly two approved Luca replay transfers. Independent review established that submission `54863653` is a current gold-region teacher, recovered the same exact 60-card deck hash in both episodes, passed current-card-data construction checks, and validated action-aligned supervision. The pair contributed only 37 Luca decisions and crossed CABT module versions `1.32.1` and `1.32.2`, so it cannot establish same-version behavioral consistency or satisfy the 5,000-teacher-decision screening floor.

A read-only metadata screen of the pinned July 23 dataset found 39 Luca episodes at or after the observed `1.32.2` anchor episode `87731214`. Metadata cannot itself prove the module version of each replay body. Therefore any later execution must review every transferred file and fail the qualification if a file is not module `1.32.2`.

## Decision

Prepare one exact, non-authorizing calibration request containing 12 named Luca episodes, balanced as three files in each player-slot/terminal-result stratum. The deterministic selection uses three file-byte quantiles per stratum and is capped below 64 MiB.

The exact batch is:

| Episode | File | Bytes | Luca slot | Luca result |
|---:|---|---:|---:|---:|
| 87732247 | `87732247.json` | 5,999,663 | 0 | +1 |
| 87733289 | `87733289.json` | 5,047,771 | 0 | -1 |
| 87733748 | `87733748.json` | 4,942,976 | 0 | -1 |
| 87734353 | `87734353.json` | 3,934,914 | 0 | +1 |
| 87736454 | `87736454.json` | 5,122,828 | 1 | -1 |
| 87737495 | `87737495.json` | 6,627,479 | 1 | -1 |
| 87739090 | `87739090.json` | 6,109,840 | 0 | -1 |
| 87739639 | `87739639.json` | 6,699,033 | 1 | +1 |
| 87741191 | `87741191.json` | 6,065,629 | 1 | +1 |
| 87744901 | `87744901.json` | 5,544,479 | 1 | +1 |
| 87744904 | `87744904.json` | 4,958,020 | 0 | +1 |
| 87745939 | `87745939.json` | 2,775,425 | 1 | -1 |

Total exact transfer cap: **63,828,057 bytes**.

The batch is a calibration sample, not the full 5,000-decision screen. Its purpose is to measure Luca decision density and verify exact deck, module, schema, and action-alignment consistency before sizing a larger request.

## Required review if separately approved

For every named file, independently verify:

- exact byte count and downloaded SHA-256;
- exact public episode/submission/team binding;
- schema version 1 and CABT environment `1.0.0`;
- module version exactly `1.32.2`;
- Luca's exact 60-card deck multiset hash equals `cafa7652a6349be806d8ac2b9abfdb6c72ca3821f368e0d912e2d989f3b54cdd`;
- current-card-data construction compatibility;
- aggregate lagged request/action alignment;
- Luca-only meaningful decision count and decisions per byte.

The review must report pass or fail without exporting raw requests, options, observations, action sequences, card lists, or training labels.

## Authorization boundary

This decision does **not** authorize downloading any of the 12 replay bodies. Separate explicit user approval of the exact request is required.

Even after such approval, the scope excludes:

- agent logs;
- any replay outside the exact 12-file list;
- overwrite of an existing output directory;
- raw replay, step, action, observation, option, or card-list exports;
- behavior-cloning labels or optimizer steps;
- PPO, self-play, external compute, notebook launch, model publication, deck freeze, or submission.

Execution must stop after the exact calibration review whether it passes or fails. A full screening batch remains separately approval-gated and may be prepared only from the calibration evidence.

## Evidence

- `configs/e01_luca_gold_teacher_probe_request_v1.json`
- `reports/artifacts/e01-luca-gold-teacher-probe-review-v1.json`
- `reports/artifacts/raw/e01-luca-same-version-calibration-candidates-v1.json`

## Revisit trigger

Revisit if any selected episode identity, timestamp, team/submission binding, exact file byte count, dataset version, module anchor, output path, deck hash, transfer cap, or exclusion boundary changes.
