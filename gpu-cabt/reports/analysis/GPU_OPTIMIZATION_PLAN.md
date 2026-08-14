# GPU Optimization Plan

This plan follows the retained evidence and keeps production unchanged until a scratch POC passes. All heavy commands use `taskset -c 0,1`, `nice -n 10`, `OMP_NUM_THREADS=2`, `OPENBLAS_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, and `NUMEXPR_NUM_THREADS=1`.

## P0 - Restore And Reprofile

- Objective: rerun the retained 6,000 and 12,000 environment baseline on the actual standalone checkout and collect Nsight data if available.
- Evidence: current session has no CUDA device; retained peak is 462.357715 games/s and 56,988.324 decisions/s at 12,000 environments.
- Files affected: none; use `.cache/` scripts and report outputs.
- Implementation sketch: restore device access, run the qualification-sized workload once, then run the existing interpreter and main-stage probes. Add CUDA events around setup, select-main, generic action, attack, refresh, effect resume, target, and condition paths without changing semantics.
- Expected performance effect: none; measurement gate only.
- Correctness risks: instrumentation must not alter control flow or state layout.
- Benchmark required: 6,000 and 12,000 environments, seven-deck sweep, same seed/config.
- Accept only if: all games terminate with zero errors and the baseline is within +/-10% of retained throughput; otherwise stop and diagnose environment drift.

## P1 - Top-Four Internal Stage Queue POC

- Objective: test whether internal stage coherence beats dense one-thread-per-environment dispatch.
- Evidence: main-action control-efficiency proxy is 10.156%; top four stages cover 84.54% of main-action stage iterations; public select sorting was 33% slower.
- Files affected: new `.cache/` CUDA source first; later a new stage dispatcher and `game_runtime.cu` only after approval.
- Implementation sketch: maintain `env_ids` only; build four queues by `runtime.main_action_stage`; launch dedicated kernels for PlaySkill, Ability, AttackReady, and AttackAfterRefresh; use a generic fallback for other stages. Do not copy either large state struct.
- Expected performance effect: measured by POC; 1.3-2.5x is only an opportunity range, not a claim.
- Correctness risks: queue duplicates, dropped environments, stale selection response, different transition order, and effect continuation errors.
- Benchmark required: same 6,000/12,000 whole-game workload plus deterministic state/result/turn hashes.
- Accept only if: whole-game decisions/s improves >=20% at both sizes, queue overhead is <10% of baseline step time, zero errors/fallbacks occur, all games terminate, final results/turns/policy/event projections are identical, and native 8-case/70-case differentials remain exact.

## P2 - Dependency-Closed Stage Translation Units

- Objective: determine whether compiler quality improves once a stage's actual helper closure is separated.
- Evidence: runtime-only source still LLVM-OOMed under a hard 6 GiB cap; a 34 KB leaf optimized at 130 MB RSS; wrapper-only stages stayed at 128 registers.
- Files affected: `src/gpu_cabt/source.py` only after scratch dependency inventory; new CUDA modules; no official data changes.
- Implementation sketch: use P1's top-four queues, list exact callees for one stage, compile only that closure with full optimization under `RLIMIT_AS=6 GiB`, inspect CUBIN resources, then run semantic POC.
- Expected performance effect: unknown, potentially lower instruction footprint/register pressure.
- Correctness risks: missing rule/effect helper, changed static initialization, different noinline/inline semantics.
- Benchmark required: compile RSS/time/CUBIN size/registers/local bytes and the P1 matched gameplay workload.
- Accept only if: compile stays <=6 GiB RSS, CUBIN loads, no spills or new errors appear, and whole-game decisions/s improves >=20% over P1 baseline.

## P3 - Hot Control SoA / Header

- Objective: test whether coalescing only the hot control fields helps enough to justify layout work.
- Evidence: adjacent-thread AoS strides are 21,016 and 62,320 bytes; hot fields are flags/stages at low offsets.
- Files affected: scratch state mirror and dispatcher first; later `device_runtime.py` and ABI headers if accepted.
- Implementation sketch: mirror only `game_result`, `select_type`, `error_flags`, `main_action_stage`, pending-kind, active flags, and queue state. Keep full mutable structs authoritative.
- Expected performance effect: 1.1-1.5x opportunity, unmeasured.
- Correctness risks: stale mirror, write-back ordering, and hidden semantic dependence on full structs.
- Benchmark required: matched hot-field CUDA microbenchmarks and whole games with queue POC.
- Accept only if: hot-field kernel time improves >=20% and whole-game decisions/s improves >=10% with exact semantics.

## P4 - Deck-Local Rule Graph Experiment

- Objective: quantify whether known deck families permit a safe compact rule table.
- Evidence: 84 unique fixture card IDs versus 1,268 card-master rows; effects are 441,648 of 650,760 rule bytes.
- Files affected: scratch rule-closure extractor and rule upload path; no production promotion yet.
- Implementation sketch: compute transitive closure from the 84 card IDs through skills, attacks, effects, triggers, target conditions, and name masks; remap IDs; compare table bytes and cache behavior.
- Expected performance effect: unknown; capacity reduction alone is not a speedup claim.
- Correctness risks: omitted cross-card/evolution/trigger references.
- Benchmark required: closure counts, table bytes, cache counters if available, and native 8/70 differentials.
- Accept only if: closure is complete, all semantic gates are exact, and whole-game decisions/s improves >=10% without increasing memory or compile cost.

## P5 - Active-Environment Compaction

- Objective: test whether terminal/waiting lanes make dense launches wasteful after the early game.
- Evidence: waiting-boundary branch is 47.48%; terminal lane fraction was not retained.
- Files affected: scratch index queue only.
- Implementation sketch: compact active IDs at early/mid/late boundaries; time compaction separately; never move state/runtime structs.
- Expected performance effect: unknown.
- Correctness risks: queue order, duplicate/missing IDs, and recurrent response identity.
- Benchmark required: early/mid/late boundary snapshots and whole games.
- Accept only if: late-boundary step cost improves >=15%, whole-game decisions/s improves >=10%, and compaction overhead is included in the result.

## P6 - Cooperative Scan Microkernels

- Objective: determine whether one-warp-per-game helps target/effect scans without parallelizing mutation.
- Evidence: `target_single` and condition code contain bounded scans; whole-game state transitions remain serial.
- Files affected: scratch target/condition kernels only.
- Implementation sketch: use warp lanes for read-only candidate scans, reduce into lane 0, then keep state mutation serialized. Compare against scalar scan on captured valid states.
- Expected performance effect: unknown; do not extrapolate from synthetic empty states.
- Correctness risks: reduction order, mask semantics, dynamic target legality.
- Benchmark required: real captured states from whole-game execution and native/public differential tests.
- Accept only if: representative scan time improves >=25% and whole-game decisions/s improves >=10% without changed target sets.
