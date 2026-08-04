# DEC-022 — Probe the current rank-1 confirmation teacher

Status: Accepted

Date: 2026-07-27

## Context

DEC-021 completed the exact current-rank-1 `flg` Dragapult screening expansion. All 38 selected replay files qualified, adding 4,954 teacher decisions and bringing the exact submission `55004495` evidence total to 6,340 decisions. The 5,000-decision E01 screening floor is therefore met.

A fresh leaderboard check after the DEC-021 review materially changed the live state. `flg` changed its active submission and moved to rank 4. `Dries @ Tufa Labs` is now rank 1 with team score 1,205.2 and active public submission `55002825`. The completed `flg` screening remains valid for the exact historical submission that produced it, but it cannot be treated as proof that the currently active leader has the same deck, module, or behavior contract.

The confirmation boundary still requires two independent recent teachers, at least 200 qualifying episodes, and at least 25,000 meaningful teacher decisions. A two-file Dries probe is only an identity, deck, module, construction, and action-alignment qualification step. It is not confirmation completion and does not authorize behavior cloning.

## Decision

Prepare exactly two public replay files for Dries submission `55002825`:

- `88281294.json` — 625,479 bytes, teacher seat 1, teacher win;
- `88332011.json` — 509,759 bytes, teacher seat 0, teacher loss.

Total authorized-request size if separately approved: **1,135,238 bytes**.

The pair is the smallest dataset-intersecting pair with opposite teacher seats and opposite terminal results. Selection used public episode metadata and dataset file sizes only; replay bodies were not used for selection.

## Required independent review

Each file must independently satisfy all of the following before any teacher decision is counted:

1. schema version exactly `1`;
2. CABT environment name `cabt` and version `1.0.0`;
3. module version exactly `1.32.2`;
4. episode, seat, reward, team, and public submission metadata binding to Dries submission `55002825`;
5. a 60-card teacher deck that passes current official-card construction checks;
6. the exact same teacher deck multiset across both files;
7. complete lagged request/action alignment for both players.

Any nonmatching file is rejected from decision counts. Exact historical engine-card mapping and historical legality remain unproven unless separately established.

## Authorization boundary

This decision does **not** authorize downloading the two replay bodies. Separate explicit approval must name the exact request file and thereby authorize only these two files totaling 1,135,238 bytes.

It does not authorize:

- overwrite;
- any third replay or agent log;
- raw replay, step, request, option, observation, action, deck, or label export;
- behavior cloning, PPO, self-play, or any optimizer step;
- notebook, GPU, TPU, Modal, or other external compute;
- deck freeze or competition submission.

## Stop condition

After a separately approved transfer, stop after independent review whether the probe passes or fails. A passing probe may support a later bounded confirmation-coverage request, but does not itself meet the 200-episode or 25,000-decision confirmation floor.
