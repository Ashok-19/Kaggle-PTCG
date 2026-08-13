# DEC-045 — Prepare production BC notebook v3 shared-approval remediation

Status: `ACCEPTED_REQUEST_READY_UNAUTHORIZED`

Prepare a new versioned wrapper and notebook request that change only the notebook-side approval kind from `E01_PRODUCTION_RECURRENT_BC_APPROVAL_V2` to the production implementation's existing `E01_PRODUCTION_RECURRENT_BC_APPROVAL_V1`.

The production implementation, training request, runner, dataset mounts, `316` replay records, `1,327,994,902` replay bytes, checkpoint, hyperparameters, four-epoch limit, `844`-step cap, and `46` sealed test episodes are unchanged.

- Request: `configs/e01_production_recurrent_bc_notebook_request_v3.json` — SHA-256 `30b7b049f6fe8e069f3253fac7fde8db44dc7cd862e923d47db84bfd5894c9bd`.
- Wrapper: `scripts/kaggle/e01_production_recurrent_bc_notebook_v3.py` — SHA-256 `7f63cf6331ef0ee8122522cf2849e765e247f6f9a1a4c77bf4677101c1cf0b8d`.
- Builder: `scripts/kaggle/build_e01_production_recurrent_bc_notebook_v3.py` — SHA-256 `425ee2fe2ed3674424a0e432b95ea45327cf89676f553dca41cfd73e663d8421`.
- Focused test: `tests/g3/test_e01_production_bc_notebook_v3.py` — SHA-256 `3ff70ea20c6446bd5f375cbcdd1efd3a6f09f02ac03a28535fb2a0b2cdd645d5`.
- Contract review: `reports/artifacts/e01-production-recurrent-bc-notebook-contract-review-v3.json` — file SHA-256 `cf9796b7fcaa3b5c8ce79edd17033006ddada4043046803cfaab73fb612ad74f`, self-hash `12d0d21197396f44179641c1c750be0eae5a2d4cb57a9d91cb8c2c8bbc520ed0`.
- Approval text SHA-256: `4cf80c5be4f1dfa40fbcd0e158dffe4113845862ac2d15421e51e28e8b3f0fbb`.

No notebook creation, replay access, optimizer step, training, evaluation, model mutation, submission, commit or push is authorized by this decision.
