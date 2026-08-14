# GPU-CABT Bottleneck Investigation

Generated UTC: `2026-08-14T07:52:56.684394+00:00`  
Target: standalone `gpu-cabt`  
Git HEAD: `5b62b60d81e9ed4bd986cf0eadc222a5ad76a3a1`  
Investigation mode: analysis/profiling/report generation only

## Evidence Boundary

This report does not claim a fresh GPU run. The repository has the standalone Python/CuPy stack, but this session has no `/dev/nvidia*` device nodes. A later host-level `nvidia-smi` query saw the RTX 3050 at 0% utilization, 11.34 W, and 15 MiB used, but CuPy still failed at device initialization with `cudaErrorNoDevice`; the bounded 24/6000/12000 baseline probe therefore failed before selector module load. The retained qualification at source head `0e891d25c58ddb65cf384c4ef0a7001a962dc970` is therefore the baseline, and every retained dynamic result is labeled as such. No production source was modified.

## Executive Summary

The measured primary cost is `gpu_cabt_game_step`, approximately **93.5%** of retained GPU execution time. The actionable root cause inside that kernel is a one-thread-per-environment serial interpreter running heterogeneous game state machines in the same warps:

1. **Control-flow divergence and serialized state-machine work.** Retained instrumentation measured 80.1% of lane-iterations as divergent, only 14.44 matching lanes per warp iteration, and 47.48% of iterations in `waiting_boundary`. Main-action execution is worse: 73.63% divergent and only 3.25 matching lanes per warp iteration. This is measured evidence, not an inference from utilization alone.
2. **Large generic rule/effect dispatch in the hot path.** Static analysis found 443 functions reachable from `gpu_cabt_game_step`, 409 reachable force-inline functions, 414,934 bytes of reachable function bodies, and 443 loop constructs. The current CUBIN has 479 text sections and about 3.81 MB of device text. `target_single` is 204,800 bytes of CUBIN text; continual and instant-effect handlers are also large. This explains why wrapper-only specialization stayed at 128 registers: it did not create a smaller dependency closure.
3. **Per-environment serial progress and poor work granularity.** `advance_game_to_boundary_full` is a 512-iteration interpreter loop with separate branches for main action, refresh, turn cycle, KO, triggers/effects, setup, and selections. There are no CUDA synchronization primitives in the CUDA source. A warp is therefore not cooperating on one game; it is executing unrelated serialized continuations lockstep where possible and masking the rest.

The strongest next opportunity is a **scratch internal-stage index queue with real stage-family kernels**, starting with the four dominant main-action stages: PlaySkill, AttackReady, Ability, and AttackAfterRefresh. Do not repeat public `select_type` sorting and do not merely wrap the current full translation unit. The first POC should preserve the existing state buffers and move only environment indices.

Expected improvement is conditional, not measured: perfect control-flow agreement would be a 2.22x upper bound for the outer matching-lane metric and a 9.85x upper bound for the isolated main-action matching-lane metric. Amdahl's bound using the measured 20.82% main-action iteration share is only about 1.23x if iteration costs were equal. Therefore 5x or 10x is not supported by current evidence; it requires eliminating more generic work, not only making branches coherent.

## Baseline

| Item | Retained value |
|---|---:|
| GPU | NVIDIA GeForce RTX 3050 Laptop GPU |
| Compute capability | 8.6 |
| SMs | 16 |
| Nominal VRAM | 3,953,393,664 bytes |
| Driver kernel module | 595.84 |
| Python / CuPy / NumPy | 3.11.14 / 14.1.1 / 2.0.2 |
| NVRTC package | 12.9.86 |
| Compiler mode | `GPU_CABT_NVRTC_FAST_COMPILE=max` |
| Stack limit | 16 KiB retained qualification |
| Threads/block | 128 |
| 6,000 environments | 372.224494 games/s; 45391.040 decisions/s |
| 12,000 environments | 462.357715 games/s; 56988.324 decisions/s |
| 12,000 GPU utilization | 99.946% mean; 55.194 W mean |
| 12,000 observed GPU memory | 2125 MiB max |
| Native public CPU reference | 1036.111 games/s, single process |

The retained GPU/native public rate ratio is 0.446; this is a throughput comparison, not a claim of identical launch topology. The old `ptcg-rl` environment is not involved in this investigation.

The current-session preflight failed before launching gameplay because CuPy cannot see a CUDA device. This is a blocker for fresh CUDA-event timings, Nsight counters, per-matchup runs, SoA benchmarks, compaction, and semantic POCs.

## Hot Kernel Breakdown

Retained CUDA timing attributes approximately 93.5% of GPU execution to `gpu_cabt_game_step`, 5.6% to policy projection, less than 1% to public events, and negligible status/selector/launch overhead. This is why the report does not recommend optimizing Python, public projection, or launch geometry first.

The kernel is a one-thread-per-environment adapter at [`game_runtime.cu:184`](../../src/gpu_cabt/cuda/game_runtime.cu:184). It loads a 21,016-byte `BattleCoreState` and a 62,320-byte `BattleRuntimeState`, validates a response, then enters [`advance_game_to_boundary_full`](../../src/gpu_cabt/cuda/game_runtime.cu:70). The interpreter checks terminal/error state, selection waits, main action, refresh, turn cycle, KO, trigger/effect, setup, main selection, and unsupported states in sequence on every internal iteration.

The loop bound is 512. The retained profile observed 393,398 internal iterations for 188,326 decisions, or 2.089 internal iterations per decision. The branch mix was waiting boundary 47.48%, main selection 29.18%, main action 20.82%, setup 2.14%, and terminal/error 0.39%.

## Warp Divergence

The outer retained profile gives a control-flow efficiency proxy of `14.44 / 32 = 45.125%` matching lanes per warp iteration. The main-action proxy is `3.25 / 32 = 10.156%`. These are branch-agreement measurements from `__match_any_sync`, not Nsight's warp-active metric. They directly show that same-kernel state-machine execution is wasting issue slots on masked lanes.

Main-action stage distribution:

| Stage | Share |
|---|---:|
| PlaySkill | 37.06% |
| AttackReady | 20.45% |
| Ability | 15.90% |
| AttackAfterRefresh | 11.13% |
| RetreatSwitch | 4.32% |
| RetreatEnergy | 3.77% |
| AttackPostEffects | 3.44% |
| PostRefresh | 3.33% |
| Other | 0.60% |

The top four stages account for 84.54% of measured main-action stage iterations. This is the quantitative basis for testing stage queues. It is not a claim that they account for 84.54% of total GPU time; stage cost is unequal and must be timed in the POC.

The 47.48% waiting-boundary share also means that a dense launch can execute many lanes that are not actively interpreting. Terminal/inactive lane percentage by boundary was not retained, so active-environment compaction remains an unmeasured candidate rather than a diagnosed bottleneck.

## State / Memory Layout

The state is AoS at the environment level: adjacent threads address `states[i * 21016]` and `runtimes[i * 62320]`. A same-field load from neighboring threads is therefore 21,016 or 62,320 bytes apart. The hot control fields are at low offsets, but the large arrays are embedded in the same per-environment objects. For example, `BattleRuntimeState` places `public_logs` at offset 128, `options` at 32,896, `selected` at 34,432, `targets` at 40,064, and `triggers` at 54,400. These offsets were measured with a host ABI probe and match the retained sizes.

Static hot-file counts are strongest for `runtime.error_flags`, `runtime.pending_effect_kind`, `state.all_card`, `state.players`, `state.select_type`, `runtime.main_action_stage`, and `runtime.effect_execution_active`. The source-level access map is in `gpu_bottleneck_metrics.json`. It is a count of references, not a dynamic load count.

No AoS-vs-SoA CUDA microbenchmark could run in this session. The evidence supports a narrow hot-control SoA or index queue experiment, not a whole-state rewrite. Keep the mutable rule state in place until an indirect stage kernel proves a gain.

## Rule Table / Cache Behavior

The extracted rule graph is 650,760 bytes: 91,296 bytes of card masters, 20,880 skills, 87,192 attacks, 441,648 effects, 8,624 triggers, and 1,120 substring-mask bytes. Accesses are ID/offset based. Main selection scans the hand, bench, stadium, and attacks; target building scans area candidates and calls card/attack metadata; condition checking can scan later effects and target candidates. These are not purely sequential accesses.

There is no direct L1/L2/cache or DRAM counter in the retained evidence. It is therefore not valid to call rule-table cache misses the primary bottleneck. The table is small enough that a cache-friendly hot subset is plausible, while the dynamic target and state scans are more concerning than table capacity alone.

The seven deck fixtures contain 84 unique card IDs in their union, versus 1,268 card-master rows. A deck-local training graph could reduce card metadata and reachable skill/effect roots substantially, but the transitive effect/trigger closure must be measured before claiming a reduction. This is a training specialization option, not a general engine change.

## Instruction / Register / Compiler Analysis

The canonical source is 564,511 bytes and 12,672 lines across 46 modules. Static analysis found 482 device/global functions, 441 force-inline functions, 475 loop constructs, 1,996 `if` statements, and 21 switches. The `gpu_cabt_game_step` call graph reaches 443 functions, 409 force-inline functions, 414,934 bytes of function bodies, 443 loops, 1,897 `if` statements, and 19 switches.

The current cached CUBIN is 4,704,232 bytes with 479 `.text.*` sections and 3,808,000 bytes of device text. The selected sections are:

| Compiled function | Text bytes |
|---|---:|
| `gpu_cabt_game_step` | 11,008 |
| `advance_game_to_boundary_full` | 10,112 |
| `resume_main_action_full` | 16,768 |
| `resume_attack_full` | 15,744 |
| `resume_effect_selection_full` | 32,512 |
| `begin_main_select_full` | 37,376 |
| `target_single` | 204,800 |
| `effect_continual` | 130,560 |
| `effect_instant_0_29` | 99,456 |

The retained game-step resource probe reports 128 registers/thread, zero local-memory spill, and max 512 threads/block. A simple 96-register cap did not improve throughput. Thus registers are a real occupancy constraint but not the measured first-order lever. The fast-PTX driver-JIT experiment was clearly worse at 250 registers/thread and 1,352 local bytes/thread.

The safe compiler investigation is decisive about one narrow point. Runtime-only source without policy still failed full optimization under a hard 6 GiB address-space limit with `LLVM ERROR: out of memory`; a 538,269-byte fast-compile runtime-only source compiled in 3.384 s to a 4,461,816-byte CUBIN. A 34,085-byte isolated hot-field leaf compiled fully optimized in 0.177 s at 130,113,536-byte peak RSS. Therefore, a smaller dependency-closed gameplay TU may help, but simply removing policy projection is not enough. Wrapper kernels over the existing source are not isolation.

## Stage-Level Analysis

`begin_main_select_full` scans the full hand, active, bench, stadium, and attack slots and performs rule-card, skill, attack, condition, energy, and retreat checks ([`main_select.cu:322`](../../src/gpu_cabt/cuda/main_select.cu:322)). `start_selected_main_full` dispatches to play, attach, evolve, ability, discard, retreat, end-turn, or attack ([`main_action.cu:320`](../../src/gpu_cabt/cuda/main_action.cu:320)). The stage resume path then calls effect selection, refresh, turn cycle, and attack continuations.

Attack is not a leaf: `resume_attack_full` routes special choices, double choices, pre-effects, damage, post-effects, after-attack triggers, pre-refresh active handling, after-refresh, and turn cycle ([`attack_frame.cu:651`](../../src/gpu_cabt/cuda/attack_frame.cu:651)). Effect execution routes by effect spans, effect type, selection, target lists, and conditions. `target_single` has 24 static loops and a 204,800-byte compiled text section. `satisfy_condition` is explicitly noinline and has condition-dependent target scans; this is useful for code-size control but introduces more dynamic paths.

No fresh CUDA event timing could separate setup, select-main, generic action, PlaySkill, Ability, attack, refresh, effect resume, target building, or conditions. Those must be the first measurements after restoring GPU access. The existing whole-kernel and divergence results are sufficient to prioritize the measurement, not to assign exact subsystem percentages.

## Scheduling Experiments

The public `select_type` sort was 33% slower, so it is rejected. It is too coarse and pays scheduling/copy costs without matching internal stage. A future scheduler must build queues by `main_action_stage` and process indices without moving `BattleCoreState` or `BattleRuntimeState`.

Persistent stage queues, active-environment compaction, two-kernel splits, generic-vs-attack splits, top-four stage specialization, and one-warp-per-game were not executed because the device is unavailable. They are not wins, losses, or recommendations by themselves. The exact experiments and acceptance gates are in `gpu_architecture_experiments.json` and `GPU_OPTIMIZATION_PLAN.md`.

## Compiler / Translation Unit Experiments

The compile results reject the easy version of “split policy projection and optimize the rest.” They support a dependency-closure project: isolate an actual gameplay stage plus the minimum rule/effect helpers it calls, compile it with full optimization under a hard 6 GiB cap, inspect registers/local memory, then run a semantic POC. Do not retry the monolithic optimized CUBIN or the known-bad fast-PTX driver-JIT path on this laptop.

## Per-Deck Findings

Per-matchup dynamic work was not measured in this session. The fixture set is seven families: Lucario, Dragapult, Alakazam, Lopunny, Iono, Abomasnow, and Grim. The six Lucario-opponent cells in the requested matrix, with both Lucario seat orientations, are represented as `NOT_MEASURED_CURRENT_SESSION` in `gpu_hotpath_profile.json`. Do not infer that one deck is the runtime culprit from static card count alone.

## Rejected Hypotheses

- Python package isolation: old and standalone throughput are already essentially identical, and this investigation targets standalone only.
- Public policy projection first: it is only about 5.6% of retained GPU time.
- Public event projection first: less than 1% of retained GPU time.
- Launch overhead: negligible in the retained breakdown; 64/128/256 thread geometries were flat.
- Public select-type sorting: 33% slower.
- Externalizing the public log: correctness preserved, no meaningful gain.
- Register cap alone: 96 registers did not improve whole-game throughput.
- Fast-PTX driver JIT: 250 registers and 1,352 local bytes/thread, clearly worse.
- Wrapper-only stage specialization: stage 1/2/8/15 wrappers stayed at 128 registers because the large dependency tree remained.
- Synchronization as the primary cost: no `__syncthreads`, `__syncwarp`, cooperative launch, or device barrier appears in the CUDA source.

## Ranked Optimization Candidates

1. **Internal stage-index queues with real stage-family kernels.** Expected opportunity: 1.3-2.5x, confidence MEDIUM for direction and LOW for range until measured. Complexity HIGH; correctness risk HIGH. Touch a new scratch dispatcher first, then `game_runtime.cu` and new stage modules. Evidence: 84.54% of main-action stage iterations are four stages and main-stage control efficiency is 10.16%. Reject unless whole-game decisions/s improves at least 20% at both 6,000 and 12,000 environments, queue overhead is under 10% of baseline step time, and all differential gates remain exact.
2. **Hot control-state SoA plus index indirection.** Expected opportunity: 1.1-1.5x, confidence LOW. Complexity MEDIUM/HIGH; correctness risk HIGH. Touch a new scheduler buffer and selected hot flags only. Evidence: adjacent-thread AoS strides are 21,016/62,320 bytes. Reject unless a matched CUDA microbenchmark shows at least 20% lower hot-field time and whole-game throughput improves at least 10% with no semantic changes.
3. **Dependency-closed optimized stage TUs.** Expected opportunity: unknown, likely 1.1-2x if code quality changes; confidence LOW. Complexity HIGH; correctness risk HIGH. Touch source composition and new stage kernels. Evidence: runtime-only optimization still OOMs at 6 GiB, while a small leaf compiles in 0.177 s. Accept only with compile RSS <=6 GiB, no spill regression, and >=20% whole-game gain on the same workload.
4. **Deck-local compact rule graph.** Expected opportunity: 1.05-1.4x, confidence LOW. Complexity MEDIUM/HIGH; correctness risk HIGH. Touch rule extraction and device upload only after a transitive closure tool exists. Evidence: 84 fixture card IDs versus 1,268 card rows; effects are 68% of table bytes. Reject if cache/memory timing does not improve or if any card/effect differential changes.
5. **Active-environment compaction.** Expected opportunity: unknown, confidence LOW. Complexity MEDIUM; correctness risk MEDIUM/HIGH. Evidence: 47.48% waiting-boundary iterations, but terminal waste is not measured. Accept only if compaction cost plus step cost beats dense execution by 15% at late-game boundaries and by 10% whole-game.

## Recommended First Change

Build **one scratch, correctness-gated internal-stage queue POC for the top-four main-action stages**, with no production rewrite yet. The queue contains environment IDs only. Use one generic fallback kernel for all other states and dedicated kernels for PlaySkill, Ability, AttackReady, and AttackAfterRefresh. The dispatcher should retain the same state/runtime buffers, use the existing functions only after they are moved behind genuinely smaller dependency closures, and record queue-build time separately from stage execution time.

This is the first change because it attacks the only directly measured inefficiency inside the 93.5% hot kernel: main-stage matching is 3.25/32, and the top four stages cover 84.54% of main-action stage iterations. It also avoids repeating the proven-bad public sorting experiment. Do not call the current large inline functions from wrappers and call that specialization.

## Recommended Architecture

The likely final architecture is a persistent or bounded worklist dispatcher over environment IDs, with compact hot control fields and stage-family kernels. Each stage kernel advances a state until a bounded transition point, writes its next internal stage, and enqueues the environment for the next stage. Large effect/target operations should have separate dependency-closed kernels or compact specialized rule graphs. A single-thread fallback remains for rare/complex transitions until coverage is proven. One warp per game should be used only for explicitly parallel scans; the state mutation sequence remains lane-serialized.

This is an architecture hypothesis, not a production approval. It requires exact final-state, turn, policy, event, error, terminal, and native differential equivalence.

## Microarchitecture Answers

1. **Why 100% utilization loses to CPU:** utilization means the GPU has active issue work; it does not mean all 32 lanes do useful same-path work. The retained 45.1% outer and 10.2% main-stage control-efficiency proxies explain how an apparently busy GPU can lose to one CPU process.
2. **Useful arithmetic or serialized work:** measured evidence favors divergent serialized interpreter/rule work, not useful dense arithmetic.
3. **Effective warp utilization:** 45.125% outer matching-lane proxy; 10.156% main-action proxy. These are not Nsight warp-active counters.
4. **Register pressure:** 128 registers/thread is high, zero spills, and theoretical occupancy is constrained, but the 96-register cap had no throughput gain. Not first-order.
5. **Higher occupancy:** not demonstrated to help; cap experiment was flat.
6. **Memory bandwidth:** unknown. No Nsight counters and no device in this session. Do not claim saturation.
7. **Kernel class:** primarily control-flow/instruction/latency-bound from current evidence; memory/cache contribution remains unmeasured.
8. **Is 80% divergence enough alone:** no. The outer matching metric gives at most 2.216x for that proxy, and equal-cost Amdahl with 20.82% main-action share gives only about 1.23x for perfect main-action coherence.
9. **Perfect coherence:** 32/14.44 = 2.216x outer matching proxy; 32/3.25 = 9.846x isolated main-action proxy. Neither is whole-game speedup.
10. **One thread per game:** it is a poor match for heterogeneous serial state machines, but the magnitude must be established by the stage-queue POC.
11. **One warp per game:** likely useful for scans, not for the whole mutable continuation; no measurement yet.
12. **SoA:** plausible for the small hot control header; a whole-state SoA rewrite is not justified.
13. **Stage queues:** strongest first POC; no speedup measured yet.
14. **Smaller TUs:** promising only with real dependency closure; simple runtime-only split failed optimized compilation at 6 GiB.
15. **Fast compile:** likely limits code quality, but the safe CUBIN has no spills and optimized whole-runtime evidence is unavailable. Treat as a secondary unknown.
16. **Realistic throughput:** public projection removal cannot exceed about 1.07x from the retained breakdown. A 1.2-2x stage-queue result is a testable opportunity, not a forecast. 5x/10x requires additional architectural evidence.

## Remaining Unknowns

- Fresh CUDA event timings for every requested subsystem.
- Nsight warp, instruction, memory, cache, occupancy, and DRAM counters.
- Active/terminal lane waste by boundary and game-length composition.
- AoS-vs-SoA measured latency and bandwidth.
- Effect/target/condition dynamic counts and per-deck distributions.
- Correctness and speed of index queues, active compaction, stage splits, and cooperative scans.
- An optimized, dependency-closed stage TU that compiles under the 6 GiB local cap.

Raw machine-readable detail is in [`gpu_bottleneck_metrics.json`](gpu_bottleneck_metrics.json), [`gpu_hotpath_profile.json`](gpu_hotpath_profile.json), and [`gpu_architecture_experiments.json`](gpu_architecture_experiments.json).
