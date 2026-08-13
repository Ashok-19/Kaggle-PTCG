# DEC-038 — Fail closed on source-bundle version-2 checkpoint archive expansion

- **Status:** ACCEPTED_FAILED_CLOSED
- **Created:** 2026-08-06T09:55:04Z
- **Dataset:** `ashok205/kptcg-e01-majkel-corpus-review-inputs`, ID `11501808`, version `2`
- **Expected inventory:** `76` files / `7,646,035` bytes / `78fa9caa32782729a28cb9254449f22e46a6edcb5f83b7b2f763756bd970fa90`
- **Actual inventory:** `79` files / `7,645,589` bytes / `2bc151d35af0ef3bd9177f44275ef04be0de017a07ef5cf86b283c94834f83ab`

## Decision

Reject source-bundle version 2 as a production recurrent BC dependency. Kaggle recursively expanded the sealed `private/g2/checkpoint-v1/g2-policy-checkpoint-v1.zip` into four internal files while processing the parent directory archive. This violates the exact path, file-count, byte-count, metadata-inventory, and sealed-checkpoint identity contract.

Version 1 remains preserved. Version 2 remains private and Ready but unusable under the frozen request. No deletion, replacement, version 3, notebook wrapper, training, or evaluation is authorized.

## Boundaries

- Replay bodies or agent logs accessed: `0`
- Labels materialized: `0`
- Optimizer steps and training: `0`
- Remote mutations after detecting the mismatch: `0`
- Model mutation, promotion, submission, commit, or push: none

## Evidence

- `reports/artifacts/raw/e01-source-bundle-v2-remote-inventory-20260806-v1.json`
- `reports/incidents/e01-source-bundle-v2-checkpoint-archive-expansion-v1.json`
- `reports/artifacts/e01-source-bundle-v2-publication-execution-review-v1.json`
