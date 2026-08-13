# DEC-028: Accept Corpus v2 and the BC Engineering Canary, Retain the Production Target Floor

Date: 2026-08-04
Status: Accepted

## Decision

Accept the exact private Kaggle CPU review of all 269 newly authorized Majkel replay bodies and freeze qualified corpus v2. Accept the bounded local BC engineering canary as a non-promotable engineering PASS. Do not start production training because corpus v2 contains 23,460 policy-loss targets, 1,540 below the frozen 25,000-target floor.

## Evidence

- 269/269 new Majkel files qualified, zero rejected, exactly 1,030,207,171 newly read bytes.
- Corpus v2: 337 unique episodes, 1,414,841,670 bytes, 25,058 active teacher requests, 1,598 forced recurrent calls, and 23,460 policy-loss targets.
- Deterministic split: 266 train, 29 validation, 42 test episodes.
- Teacher composition: 271 Majkel, 52 flg, and 14 Dries episodes.
- BC canary: exactly 64 cumulative AdamW steps, finite loss and gradients, step-32 checkpoint and exact restore, non-promotable. The first attempt failed closed after 10 steps on a forced-only chunk; the scheduler was corrected to skip that chunk and only the remaining 54 steps were executed.

## Authorization boundary

No additional replay transfer, label materialization, production optimizer step, GPU/TPU use, external training, model promotion, submission, commit, or push is authorized. The next smallest action is metadata-only selection of enough version-pinned qualified source candidates to cover the remaining 1,540-target shortfall, followed by separate exact replay approval. Production BC requires another explicit approval after the floor passes.

## Frozen hashes

- corpus-v2 manifest file: `ccc247edbc4cac0aba11c6acb26fc5e2a8c75e0a4f005d1441ce6949c0c4997f`
- corpus-v2 manifest self-hash: `e736f609209805c28bb4aa97106e163386667d639b9b21573f8ea749b11925b6`
- corpus-v2 review file: `87eaee15513189d7f2ff4ca44e631016b3f937165df31db8696383a30c1cad56`
- corpus-v2 review self-hash: `dc995dfd07d509c0271f1c7e4138408248cabbe2a64134b04439b9b121ced6c3`
- independent review file: `b27c53b8047bd481c608bfe35bcd24b9e5f3895cc422a0d207e93f7e18a771d3`
- independent review self-hash: `6025b5d9602e4f73d0398f46018e303c5ad23b38e51358d80e641694acd2f57a`
- BC canary execution: `51e06333619f1e8fc34ebb889d84cb196997632b0e347c731fe558df7813c1ee`
- BC canary execution review: `1f25828a78400801f6dc5d2d8630890579e29584762ad95b18af795ca810c100`
