# DEC-031 - Renew corpus supplement after module 1.32.4 qualification

- Status: accepted request preparation; execution unauthorized
- Date: 2026-08-05

## Decision

Accept module `1.32.4` for the bounded supplemental corpus review only because the exact one-file DEC-030 compatibility probe passed the existing Mega Lucario deck, current-card construction, terminal/reward and complete lag-aligned compound-action contract.

Prepare one new exact request that may, only after separate hash-bound approval, promote the already-qualified metadata record for `90037133.json` without a third replay-body read and then review at most the remaining 47 frozen DEC-029 files in their preserved relative order. The maximum new replay-body transfer is `175812936` bytes. Promotion of the prequalified record contributes `69` policy-loss targets, making the effective starting count `23529` and leaving `1471` targets to reach the frozen floor of `25000`.

The request must stop at the first completed qualified file that reaches the floor. It may finalize qualified-only corpus v3 metadata, but it may not export replay bodies or agent logs, generate labels, create or step an optimizer, train, mutate or promote a model, submit, commit or push.

## Next boundary

Execution remains unauthorized until the user explicitly approves `configs/e01_corpus_v2_target_shortfall_supplement_request_v2.json` at its exact SHA-256 and repeats the bounded private-Kaggle-CPU scope. Production recurrent BC remains a separate approval after corpus-v3 evidence is independently accepted.
