# DEC-024 — Wait for a versioned current-rank-1 replay source

Status: Accepted

Date: 2026-07-30

## Context

DEC-023 executed exactly the approved 12-file Dries @ Tufa Labs calibration batch. All 12 replay files are schema version `1`, CABT `1.0.0`, module `1.32.2`, exact Marnie's Grimmsnarl ex deck multiset SHA-256 `cafa7652a6349be806d8ac2b9abfdb6c72ca3821f368e0d912e2d989f3b54cdd`, current-card construction compatible and action aligned. The batch adds 1,175 Dries teacher decisions and 2,171 all-player active requests.

The exact confirmation evidence now contains two independent recent teacher identities, 66 reviewed episodes and 7,542 meaningful teacher decisions. The 200-episode and 25,000-decision confirmation floors remain short by 134 episodes and 17,458 decisions. The observed Dries calibration density is 97.91666666666667 teacher decisions per episode and 20.241299695638787 teacher decisions per MiB. Density projections are planning evidence, not guarantees.

A metadata-only live refresh after the DEC-023 review found a material source change:

- current rank 1: `haggle`, team `16441077`, score `1169.5`;
- current rank-1 active submission: `55104355`, submitted `2026-07-30T08:43:37.713000Z`;
- current rank-1 public episodes visible through competition metadata: `76`, covering all four seat/result strata;
- Dries is no longer in the top 20 and its active submissions changed from qualified submission `55002825`;
- latest complete daily dataset: `kaggle/pokemon-tcg-ai-battle-episodes-2026-07-29/1`, updated before submission `55104355` existed;
- exact current-rank-1 intersection with that dataset: `0` files and `0` bytes.

The completed Dries evidence remains valid for exact historical submission `55002825`; it is not relabeled as evidence for either new Dries submission or for haggle.

## Decision

Do not prepare, authorize or execute a current-rank-1 replay request while the versioned daily source contains zero files for submission `55104355`.

The next replay request may be prepared only after a metadata-only refresh proves that a pinned daily dataset version contains current-rank-1 submission `55104355` episodes. At that point, prepare the smallest opposite-seat/opposite-result probe that has exact file names and exact declared byte counts, and leave it unauthorized for separate explicit approval.

## Evidence

- `configs/e01_dries_grimmsnarl_calibration_request_v1.json`
  - consumed SHA-256: `f026a350d9e5c882080f28f60a811d3060f49c7a3c7375dc85e550865d4f9380`
  - authorized payload SHA-256: `75bc96fe9f5ab595f1443716a96f47c67843687b32f6d55616b05f9a59c8945d`
- `scripts/e01_dries_grimmsnarl_calibration_review.py`
  - SHA-256: `2aca64877f4f40673041745e0d1cf425643caed4eec9b3303c07daf61b26b2d9`
- `reports/artifacts/e01-dries-grimmsnarl-calibration-review-v1.json`
  - file SHA-256: `e2b0437f0cf43ebd1c1a1059714d7d435de5c25f95704e6f0aab423a114a8e45`
  - review self-hash: `56e7f1d065c0eaf5132bcac710f903ca4bfab236638d5a7d5b62bddd7ea2a871`
- `reports/artifacts/raw/e01-live-confirmation-refresh-v2.json`
  - SHA-256: `ac8e0a72b9d49a44d1f587929664a444b673866ae677f74f030555e1af889b92`

## Authorization boundary

This decision authorizes no replay transfer, agent log, raw replay export, action/observation/option export, training label, optimizer step, behavior cloning, PPO, external compute, deck freeze or submission.

No current-rank-1 request is ready. No current-rank-1 output directory may be created under this decision.

## Revisit trigger

Revisit only when a pinned versioned daily dataset contains one or more files for submission `55104355`, or when the live rank-1 team or active submission changes again. Any subsequent replay transfer requires a new exact request and separate explicit user approval.
