# DEC-044 — Production BC notebook v2 approval-kind mismatch

Status: `ACCEPTED_FAILED_CLOSED`

The exact private CPU notebook `ashok205/kptcg-e01-production-recurrent-bc-v2`, notebook ID `129909738`, version `1`, passed dataset-mount checks, reconstructed the approved checkpoint exactly, and read/hash-verified all `316` authorized train/validation replay bodies totaling `1,327,994,902` bytes.

Execution then failed before semantic parsing and optimizer construction because the v2 wrapper required approval kind `E01_PRODUCTION_RECURRENT_BC_APPROVAL_V2`, while unchanged production implementation `src/ptcg_rl/g3/bc_production_v2.py` requires `E01_PRODUCTION_RECURRENT_BC_APPROVAL_V1`.

Optimizer steps, labels, training, epoch checkpoints, test replay reads, agent-log reads, model promotion, submission, commit and push remained zero. The failed notebook is retained unchanged and is not authorized for rerun.

Evidence:

- `reports/incidents/e01-production-recurrent-bc-notebook-v2-approval-kind-mismatch-v1.json` — file SHA-256 `22b868fe01be4d2551db0ce5971f7905ccbfbdf847347ae2515e48d74c09d48d`, self-hash `21de73713163d70f1b99bbee7ce6f33766c5014f274a30b0df86feda9e3e7561`.
- `reports/artifacts/e01-production-recurrent-bc-notebook-execution-review-v2.json` — file SHA-256 `5846781144cfb37b41bce5f5e07b77176102919bb4860f7a4b28ea026d0265ac`, self-hash `2fb933d2f5bbf4f52d09380ca191cdc1e9793ee3dc569999ce62f51a0c55afab`.
