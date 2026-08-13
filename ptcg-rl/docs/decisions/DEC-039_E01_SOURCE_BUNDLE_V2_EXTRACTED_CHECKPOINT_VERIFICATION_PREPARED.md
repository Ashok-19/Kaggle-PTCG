# DEC-039 — Prepare extracted-checkpoint verification remediation

- **Status:** ACCEPTED_REQUEST_READY_UNAUTHORIZED
- **Created:** 2026-08-06T10:26:44Z
- **Dataset:** `ashok205/kptcg-e01-majkel-corpus-review-inputs`, ID `11501808`, version `2`
- **Remote inventory:** `79` files / `7,645,589` bytes / `2bc151d35af0ef3bd9177f44275ef04be0de017a07ef5cf86b283c94834f83ab`
- **Verification request SHA-256:** `443098120fa03dcbaa1d430e3f74505926d2e45fa5ea382856b80422816bba78`
- **Approval text SHA-256:** `a2ed4213e3cf8f5e51cb451be8af7bfbbaa1acaa4e0831833f91c373056cc860`

## Decision

Prepare, but do not consume, a four-file-only verification request for the checkpoint members expanded by Kaggle. Local proof establishes that the four approved member bytes can deterministically reconstruct the original sealed checkpoint package at `4dfba2adb9f97607cfa5dabadba075236bb7aae51eafab264584e947feae3827` when the archive mode is `0600`.

This is the least-invasive path: preserve dataset versions 1 and 2, avoid version 3, verify only 5,428,744 non-replay bytes, and require reconstruction before any replay-body read. Source-bundle version 2 remains unaccepted until exact remote SHA-256 verification passes.

## Boundaries

- Remote files downloaded during preparation: `0`
- Remote mutations: `0`
- Replay bodies or agent logs accessed: `0`
- Labels, optimizer steps, training, evaluation, or notebook execution: `0`
- Model mutation, promotion, submission, commit, or push: none

## Evidence

- `configs/e01_source_bundle_v2_checkpoint_directory_verification_request_v1.json`
- `reports/artifacts/e01-source-bundle-v2-checkpoint-directory-verification-contract-review-v1.json`
- `reports/artifacts/raw/e01-source-bundle-v2-remote-inventory-20260806-v1.json`
- `reports/incidents/e01-source-bundle-v2-checkpoint-archive-expansion-v1.json`
- `scripts/e01_verify_extracted_checkpoint_delivery.py`
