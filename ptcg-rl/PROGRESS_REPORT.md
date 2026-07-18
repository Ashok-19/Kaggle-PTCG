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

Independent recalculation leaves G1R blocked on the qualifying 10,000-game arena,
shipped-versus-built corpus, throughput matrix, and six-hour RSS soak. Threshold approval
is still required before launching those long jobs. A checked, resumable unattended runner
now executes those four jobs and automatically recalculates the gate and refreshes the
dashboard. R0 has transferred zero files because no qualifying long run is active. No
training or meaningful self-play ran locally.
