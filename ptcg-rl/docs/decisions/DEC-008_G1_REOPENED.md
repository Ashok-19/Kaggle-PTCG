# DEC-008 - Reopen G1 As G1R

Date: 2026-07-18
Status: accepted

## Decision

The former G1 `PASS` is historical and superseded by G1R. G1R remains
`BLOCKED / NOT_REVIEWED` until every original handbook criterion is independently
recalculated from retained raw evidence.

## Reason

The former 50-game smoke was useful contract evidence but was not the governing G1
acceptance run. It omitted the million valid-operation corpus, 10,000 complete games
with all four exact rule baselines, shipped-versus-built comparison, log burst,
worker restart, 1/2/4/8-worker throughput, and six-hour RSS soak. Review also found
false-pass, provenance, adapter-boundary validation, terminal parsing, semantic
fail-open, STOP trace, recurrent lifecycle, and evidence-reproducibility defects.

## Governing Closure Rule

The numeric rules in the supplied `03_ENGINE_CONTRACT_TESTS.md` and
`01_MASTER_PLAN.md` govern closure. Missing thresholds are preregistered as proposals
and require user approval before a qualifying long acceptance run starts. Technical
completion is `SUCCEEDED / NOT_REVIEWED`; only an independent artifact recalculation
may set `PASS`.

No PPO, model-strength, reward, critic, deck, behavior-cloning, search, promotion,
training, submission, or external compute decision is authorized by this record.

