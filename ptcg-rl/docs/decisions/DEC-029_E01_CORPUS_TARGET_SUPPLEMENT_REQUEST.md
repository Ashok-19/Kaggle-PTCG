# DEC-029 - Freeze the exact corpus-target supplemental request

- Status: accepted request preparation; execution unauthorized
- Date: 2026-08-05

## Decision

Accept the version-pinned August 4 daily source as READY and freeze one exact balanced supplemental request for the remaining 1,540-policy-target corpus shortfall. The request names 48 Majkel replay files, exactly 12 per seat/result stratum, in deterministic newest-first round-robin review order. It may be executed only after separate exact approval.

## Evidence

- Source: `kaggle/pokemon-tcg-ai-battle-episodes-2026-08-04/1`, dataset id `11506836`.
- Dataset inventory: `4812` files / `21457813826` bytes, SHA-256 `5620e055a25407c47e7744eaa0ffb9ab2a04fe2287b0f6180f54726cf7a00f77`.
- Manifest SHA-256: `bb190f62f0585dc2a1db2b02752a4d7e6fa6de15a800ed9e769d8daecd8bf9a1`; `5` manifest rows have no JSON body and none are selected.
- Public episode metadata SHA-256: `53ce7e4428227844a9038431ea09f4b7fca18cb9d7fa147b5d24decc3381e64a`.
- Eligible new completed Majkel episodes: `236`.
- Eligible strata: `{"seat_0_loss": 36, "seat_0_win": 93, "seat_1_loss": 35, "seat_1_win": 72}`.
- Selected request: 48 files, `180695173` exact declared bytes, 12 per stratum.
- Corpus v2 remains 337 episodes and 23,460 targets; no corpus mutation occurred.

## Boundaries

No replay body was read while preparing this request. Execution, qualified-only corpus-v3 finalization, replay-body reads, label materialization, optimizer steps, training, accelerators, model mutation or promotion, submission, Git commit and Git push remain unauthorized. A later exact approval must bind the request path and file SHA-256.
