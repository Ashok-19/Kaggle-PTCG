# Progress Report

Current gate: **G1R contract recertification**  
Outcome: **BLOCKED / NOT_REVIEWED**  
Cost: **USD 0**

The reviewed false-pass, loaded-asset provenance, adapter-boundary validation,
terminal parsing, fail-closed semantic, STOP trace, recurrent lifecycle, failure-mode,
and evidence-reproducibility defects are repaired and regression tested.

Current retained evidence includes 57 passing Python tests, Ruff, dashboard tests/build,
asset and contract validation, a 1,000,000-valid-operation corpus, a 257-event log burst,
forced worker replacement, all four exact rule-agent/deck bindings, a clean 25-game
integration matrix, a clean 50-game native smoke, Ubuntu 22.04 source build/load, profiling,
and interrupted-run resume proof. These are technical successes, not a gate `PASS`.

Authoritative evidence:

- `reports/gates/g1r.json`
- `contracts/g1r_acceptance_plan.v1.json`
- `docs/decisions/DEC-008_G1_REOPENED.md`
- ignored raw preflight evidence under `runs/g1r-preflight-20260718T115802Z/`
- ignored one-million corpus and verification manifests under `runs/`
- `G1R_REMEDIATION_AND_ACCEPTANCE_REPORT.md`

The unattended run passed the 1,000-game-per-library shipped/built comparison. Its
benchmark attempt retained 71 failures caused by an overly strict negative-HP check during
native knockout cleanup; the contract fix and focused reruns now pass. Independent
recalculation leaves G1R blocked on the throughput matrix, 10,000-game arena, and six-hour
RSS soak. Re-running the same command skips comparison, retries benchmark, and then runs
the remaining jobs before refreshing the dashboard. R0 still contains zero episode JSON
files. No training or meaningful self-play ran locally.
