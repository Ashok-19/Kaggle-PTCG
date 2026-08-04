# DEC-018 — Prepare a calibrated Luca screening expansion batch

Status: Accepted  
Date: 2026-07-24  
Scope: E01-A public teacher screening only

## Context

DEC-017 transferred and independently reviewed exactly 12 Luca calibration replays. All 12 are CABT module `1.32.2`, use the same exact Luca deck multiset hash `cafa7652a6349be806d8ac2b9abfdb6c72ca3821f368e0d912e2d989f3b54cdd`, pass current-card construction checks and pass aggregate lagged request/action alignment. They contribute 1,170 Luca decisions. Together with the 37-decision DEC-016 probe, 1,207 Luca decisions are observed, leaving a 3,793-decision shortfall against the 5,000-decision E01 screening floor.

The calibration mean is 97.5 Luca decisions per episode and 19.220919101454083 decisions per MiB. The minimum observed file-level density is 16.264384083698396 decisions per MiB. A metadata-only screen of the pinned July 23 dataset selected enough exact bytes to cover 110% of the remaining shortfall at that minimum observed density.

## Decision

Prepare one exact, non-authorizing screening-expansion request containing 51 named Luca episodes totaling **270,807,738 bytes**. The batch contains every remaining dataset episode at or after the known module-`1.32.2` anchor and the 24 nearest pre-anchor boundary episodes.

The 27 at-or-after-anchor files are the highest-confidence same-version group. Metadata cannot prove module versions for any untransferred replay body. Therefore every file must be independently reviewed. A file counts toward the screening floor only if it proves schema version 1, CABT environment `1.0.0`, module version exactly `1.32.2`, Luca submission/team binding, the exact deck hash, current-card construction compatibility and valid action alignment. A nonmatching file is rejected from decision counts; it does not invalidate independently passing files.

At the conservative minimum observed density, the exact batch projects 4,200.478614492002 Luca decisions and 5,407.478614492002 combined observed decisions. This is a sizing projection, not a competence claim or guarantee.

## Exact batch

| # | Episode | File | Bytes | Luca slot | Result | Anchor relation |
|---:|---:|---|---:|---:|---:|---|
| 1 | 87731725 | `87731725.json` | 5,619,220 | 0 | +1 | AT_OR_AFTER |
| 2 | 87732250 | `87732250.json` | 2,717,517 | 1 | -1 | AT_OR_AFTER |
| 3 | 87732772 | `87732772.json` | 6,883,922 | 1 | +1 | AT_OR_AFTER |
| 4 | 87733285 | `87733285.json` | 6,931,636 | 1 | -1 | AT_OR_AFTER |
| 5 | 87734349 | `87734349.json` | 2,375,741 | 1 | -1 | AT_OR_AFTER |
| 6 | 87734884 | `87734884.json` | 6,407,363 | 1 | +1 | AT_OR_AFTER |
| 7 | 87734896 | `87734896.json` | 6,502,921 | 1 | -1 | AT_OR_AFTER |
| 8 | 87735399 | `87735399.json` | 3,920,949 | 0 | +1 | AT_OR_AFTER |
| 9 | 87735930 | `87735930.json` | 4,931,727 | 0 | +1 | AT_OR_AFTER |
| 10 | 87736977 | `87736977.json` | 5,746,389 | 0 | +1 | AT_OR_AFTER |
| 11 | 87737499 | `87737499.json` | 4,012,892 | 1 | -1 | AT_OR_AFTER |
| 12 | 87738031 | `87738031.json` | 6,111,165 | 0 | +1 | AT_OR_AFTER |
| 13 | 87738038 | `87738038.json` | 7,317,442 | 1 | -1 | AT_OR_AFTER |
| 14 | 87738044 | `87738044.json` | 4,743,640 | 0 | +1 | AT_OR_AFTER |
| 15 | 87738578 | `87738578.json` | 4,817,561 | 1 | -1 | AT_OR_AFTER |
| 16 | 87739626 | `87739626.json` | 5,891,533 | 1 | -1 | AT_OR_AFTER |
| 17 | 87740136 | `87740136.json` | 6,607,003 | 1 | +1 | AT_OR_AFTER |
| 18 | 87740145 | `87740145.json` | 4,597,750 | 0 | +1 | AT_OR_AFTER |
| 19 | 87740660 | `87740660.json` | 5,070,345 | 1 | -1 | AT_OR_AFTER |
| 20 | 87741201 | `87741201.json` | 4,898,511 | 1 | +1 | AT_OR_AFTER |
| 21 | 87741238 | `87741238.json` | 8,117,381 | 1 | +1 | AT_OR_AFTER |
| 22 | 87742263 | `87742263.json` | 6,126,331 | 1 | -1 | AT_OR_AFTER |
| 23 | 87742786 | `87742786.json` | 6,136,228 | 0 | +1 | AT_OR_AFTER |
| 24 | 87743306 | `87743306.json` | 5,578,739 | 1 | +1 | AT_OR_AFTER |
| 25 | 87743839 | `87743839.json` | 4,976,756 | 0 | +1 | AT_OR_AFTER |
| 26 | 87745419 | `87745419.json` | 4,692,583 | 1 | +1 | AT_OR_AFTER |
| 27 | 87746466 | `87746466.json` | 3,466,924 | 0 | +1 | AT_OR_AFTER |
| 28 | 87730787 | `87730787.json` | 4,652,635 | 0 | +1 | BEFORE |
| 29 | 87730159 | `87730159.json` | 7,310,386 | 1 | -1 | BEFORE |
| 30 | 87730138 | `87730138.json` | 4,244,780 | 0 | +1 | BEFORE |
| 31 | 87729592 | `87729592.json` | 8,322,368 | 0 | -1 | BEFORE |
| 32 | 87729588 | `87729588.json` | 5,898,654 | 1 | +1 | BEFORE |
| 33 | 87729079 | `87729079.json` | 5,895,372 | 1 | +1 | BEFORE |
| 34 | 87729067 | `87729067.json` | 1,438,679 | 0 | +1 | BEFORE |
| 35 | 87729060 | `87729060.json` | 7,295,679 | 1 | +1 | BEFORE |
| 36 | 87729057 | `87729057.json` | 3,677,048 | 0 | +1 | BEFORE |
| 37 | 87728514 | `87728514.json` | 5,583,579 | 0 | +1 | BEFORE |
| 38 | 87728513 | `87728513.json` | 5,162,445 | 0 | +1 | BEFORE |
| 39 | 87727992 | `87727992.json` | 4,953,377 | 0 | -1 | BEFORE |
| 40 | 87727476 | `87727476.json` | 4,959,150 | 1 | +1 | BEFORE |
| 41 | 87726953 | `87726953.json` | 4,950,362 | 1 | +1 | BEFORE |
| 42 | 87726428 | `87726428.json` | 4,722,680 | 1 | -1 | BEFORE |
| 43 | 87725902 | `87725902.json` | 6,555,045 | 0 | -1 | BEFORE |
| 44 | 87725379 | `87725379.json` | 3,954,974 | 1 | +1 | BEFORE |
| 45 | 87724847 | `87724847.json` | 3,850,288 | 1 | +1 | BEFORE |
| 46 | 87724327 | `87724327.json` | 5,378,239 | 0 | +1 | BEFORE |
| 47 | 87723825 | `87723825.json` | 5,731,148 | 1 | -1 | BEFORE |
| 48 | 87723810 | `87723810.json` | 5,293,692 | 0 | -1 | BEFORE |
| 49 | 87723291 | `87723291.json` | 5,667,571 | 1 | +1 | BEFORE |
| 50 | 87722764 | `87722764.json` | 4,431,720 | 0 | -1 | BEFORE |
| 51 | 87722257 | `87722257.json` | 5,677,698 | 0 | -1 | BEFORE |

Exact maximum: **51 files / 270,807,738 bytes**.

## Required review if separately approved

For every named file:

- verify exact byte count and downloaded SHA-256;
- verify public episode, Luca submission `54863653`, team and player-slot/result binding;
- verify schema version 1 and CABT environment `1.0.0`;
- record module version and count only module `1.32.2` files;
- require Luca deck multiset SHA-256 `cafa7652a6349be806d8ac2b9abfdb6c72ca3821f368e0d912e2d989f3b54cdd` for every counted file;
- require current-card construction compatibility and aggregate request/action alignment;
- report accepted/rejected files, accepted Luca decisions, cumulative decision count and remaining shortfall.

No raw request, option, observation, action sequence, card list or training-label export is permitted.

## Authorization boundary

This decision does **not** authorize downloading any of the 51 replay bodies. Separate explicit user approval of the exact request is required.

The scope excludes agent logs, any replay outside the exact list, overwrite, raw exports, labels, optimizer steps, BC, PPO, self-play, notebook or external-compute launch, model publication, deck freeze and submission. Execution must stop after the exact screening review whether the floor passes or remains blocked.

## Evidence

- `configs/e01_luca_same_version_calibration_request_v1.json`
- `reports/artifacts/e01-luca-same-version-calibration-review-v1.json`
- `reports/artifacts/raw/e01-luca-screening-expansion-candidates-v1.json`

## Revisit trigger

Revisit if the calibration evidence, conservative density, shortfall, selected episode identity, timestamp, file size, dataset version, anchor, exact list, output path or exclusion boundary changes.
