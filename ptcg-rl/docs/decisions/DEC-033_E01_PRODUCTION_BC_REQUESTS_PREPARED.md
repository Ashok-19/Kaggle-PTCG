# DEC-033 - Prepare Production Recurrent BC Requests Without Replay Access

- Status: accepted request preparation; publication and training unauthorized
- Date: 2026-08-05

## Decision

Accept the exact manifest-only preparation of one private replay-input publication request and one implementation-bound production recurrent BC request. Preserve corpus v3 at 362 episodes and 25,056 policy-loss targets. The publication request contains only 58 retained flg/Dries train/validation replay records and excludes all test records. The training request uses 284 train episodes and 32 validation episodes, seals all 46 test episodes, and caps a deterministic four-epoch 80/20 primary/legacy schedule at 844 optimizer steps.

## Frozen requests

- Replay input publication: `configs/e01_production_bc_input_publication_request_v1.json`, SHA-256 `aeacd6377db8bf2b0bce0bfd5e3f20f71094735fd2cb51cfdacd9b7348a60c7b`.
- Production recurrent BC: `configs/e01_production_recurrent_bc_request_v1.json`, SHA-256 `709837e07d7d8e6089662e3b03e1e131b3be72111894eab2cc70d54bb8d5520b`.
- Publication runner: `scripts/e01_prepare_production_bc_input_dataset.py`, SHA-256 `36b7185e5652a867c8bc4d3aa2aebde01493e6c09e5e236270e1a14eafe82588`.
- Training runner: `scripts/e01_production_recurrent_bc.py`, SHA-256 `57e4d828056b3532cb5920dc3dab1f1d755f4087d3f5920e9d8b39021dd83d6d`.
- Shared implementation: `src/ptcg_rl/g3/bc_production.py`, SHA-256 `6d7526d430caff7f90542bd98cffd3bc14716f0291706a03f1ddd30efad4f7e5`.

## Dependencies

The retained replay dataset does not exist yet. The existing private corpus-review source bundle remains version 1 and lacks the sealed initial checkpoint and new production runner. The training request therefore binds an exact version-2 overlay plan and cannot execute until both private dataset operations are separately approved, completed, and independently inventoried.

## Authorization boundary

Preparation used corpus-manifest metadata only and performed zero replay-body reads, zero agent-log reads, zero copies, zero staging, zero uploads, zero label materialization, zero optimizer construction or steps, zero training/evaluation, zero model mutation/promotion, zero submission, and zero Git commit/push. Any publication or execution requires a separate exact approval.
