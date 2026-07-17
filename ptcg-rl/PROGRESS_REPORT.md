# Progress Report

Current gate: **G1 CABT environment and action contract**  
Outcome: **PASS recommended**  
Cost: **USD 0**

Implemented versioned public observations, semantic legal options, reversible option
permutation, ordered compound multi-select traces, ragged numeric tensors, terminal-only
episode lifecycle, redacted failures, random/deterministic legal baselines, native inventory,
schema export and a contract-only cloud validation entry point.

The bounded local smoke completed 50/50 games and 2,219 engine requests with 1,987
meaningful choices, 232 forced requests, zero invalid selections, zero crashes/timeouts and
zero post-terminal actions. Maximum observed options was 52 and maximum observed compound
selection length was 3; neither is treated as an engine guarantee.

Authoritative evidence:

- `contracts/native_inventory.v1.json`
- `reports/contracts/g1-schema-hashes.json`
- `reports/runs/g1-native-smoke.json`
- `reports/gates/g1.json`
- `G1_ENVIRONMENT_ACTION_CONTRACT_REPORT.md`

No training or meaningful self-play ran locally. After review, proceed to filtered
replay/meta acquisition and quantitative deck discovery before the first cloud smoke.
