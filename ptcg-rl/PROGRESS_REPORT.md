# Progress Report

Milestone/gate: G0 repository consolidation and dashboard transfer  
Date/time UTC: 2026-07-17  
Status: PASS  
Active repository: `https://github.com/Ashok-19/Kaggle-PTCG`  
Question: Can the existing private repository become the sole clean source of truth without merging restricted history or losing the completed dashboard?

## Outcome First

- Gate decision: PASS; G1 agent implementation is the approved next work.
- Most important result: the completed migration tree transferred byte-for-byte
  onto clean root `08be5cec...`, then the repository/cloud-first override was
  integrated and verified.
- Non-blocking notes: GitHub Packages permission is waived; exact submission
  Python patch and timeout are deferred to packaging/final-model compatibility.
- Local scope: code, metadata, tests, tiny engine smoke, packaging and final-model
  inference only. Meaningful training and large evaluation are cloud-only.

## Changes

- Replaced contaminated local `main` ancestry with the verified one-root clean lineage.
- Transferred dashboard backend/frontend, schemas, reports, screenshots, tests,
  package configuration and lock changes through a reviewed Git patch.
- Preserved the pre-existing `CODEX_MASTER_PROMPT.md` edit as an ignored patch;
  it was not applied or discarded.
- Updated project records and dashboard from blocked G0 to passed G0/planned G1.
- Kept dashboard dependencies isolated from core/submission dependencies.

## Verification

```text
uv sync --frozen --group local --group dev --group dashboard    PASS
uv run --no-sync ruff check .                                   PASS
uv run --no-sync pytest -q                                      10 passed
uv run --no-sync ptcg assets verify                             PASS
npm ci                                                           0 vulnerabilities
npm test                                                         2 passed
npm run build                                                    PASS
npm run e2e                                                      3 passed
ptcg dashboard rebuild                                          13 records, 0 quarantined
```

No RL training, broad self-play, replay download, cloud job or large benchmark
was run. Cost remains USD `0`.

## Reproducibility

| Item | Value |
|---|---|
| Clean root | `08be5cec0fac9a954a3fe127a3f51122be4736d1` |
| Migration source | local `ee2c65ecefebc5d8413e7a6d0af4c5895e54a653` |
| Exact transferred tree | `bab69f208a36ca8b239b93eccb595d36fd8399cb` |
| Migration patch SHA-256 | `e11ae67614777025ba21628d2f5e37f319aaf9fd68bc2a8669e3905caf735543` |
| Preserved user patch SHA-256 | `18fde2231074583a0dabf8f895b70dde3fe1c3705c411f4cd3a877a72ed44e61` |
| Python lock SHA-256 | `184cdd93ed1a2c94fb07d32127e322d33bead1839c78b7b258b47c615eeb7daa` |

## Next Action

Implement G1's exact CABT environment/action contract and tensor schema with
unit/contract tests and tiny local engine smoke only.
