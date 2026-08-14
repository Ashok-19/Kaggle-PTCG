# GPU-CABT Analysis Handoff

## Status

- Git HEAD: `5b62b60d81e9ed4bd986cf0eadc222a5ad76a3a1`; production source unchanged.
- Fresh GPU timing: blocked because this session has no `/dev/nvidia*` nodes; retained qualification remains the baseline.
- Retained peak: 462.357715 games/s and 56,988.324 decisions/s at 12,000 environments.
- `gpu_cabt_game_step`: approximately 93.5% of retained GPU time.
- Outer profile: 393,398 internal iterations, 188,326 decisions, 2.089 iterations/decision, 80.1% divergent lane-iterations, 14.44/32 matching lanes.
- Main action: 73.63% divergent lane-iterations, 3.25/32 matching lanes; top four stages are 84.54% of main-action stage iterations.
- Current CUBIN: 4,704,232 bytes, 479 text sections, 3,808,000 text bytes, 128 registers/thread, zero local spill.
- Optimized runtime-only compile: LLVM OOM under hard 6 GiB cap; optimized 34 KB leaf: PASS at 130 MB peak RSS.

## First Implementation

Implement only a scratch **internal-stage index queue POC** for PlaySkill, Ability, AttackReady, and AttackAfterRefresh. Do not sort by public `select_type`, do not copy `BattleCoreState` or `BattleRuntimeState`, and do not call the existing full-TU wrappers and call it specialization. Use a generic fallback queue for all other stages.

## Files To Inspect

- [`src/gpu_cabt/cuda/game_runtime.cu`](../../src/gpu_cabt/cuda/game_runtime.cu): interpreter and kernel entry.
- [`src/gpu_cabt/cuda/main_select.cu`](../../src/gpu_cabt/cuda/main_select.cu): full legal main-option scan.
- [`src/gpu_cabt/cuda/main_action.cu`](../../src/gpu_cabt/cuda/main_action.cu): main-action dispatch and resume.
- [`src/gpu_cabt/cuda/attack_frame.cu`](../../src/gpu_cabt/cuda/attack_frame.cu): attack continuation stages.
- [`src/gpu_cabt/cuda/effect_driver.cu`](../../src/gpu_cabt/cuda/effect_driver.cu) and [`effect_resume.cu`](../../src/gpu_cabt/cuda/effect_resume.cu): effect dispatch/selection.
- [`src/gpu_cabt/cuda/target_list.cu`](../../src/gpu_cabt/cuda/target_list.cu) and [`satisfy_condition.cu`](../../src/gpu_cabt/cuda/satisfy_condition.cu): dynamic scans.
- [`src/gpu_cabt/native/state_core.h`](../../src/gpu_cabt/native/state_core.h) and [`runtime_state.h`](../../src/gpu_cabt/native/runtime_state.h): AoS layout.
- [`src/gpu_cabt/source.py`](../../src/gpu_cabt/source.py): canonical TU composition.

## Reproduction Commands

Use the two-core environment guard on a real GPU:

```bash
taskset -c 0,1 nice -n 10 env OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 GPU_CABT_NVRTC_FAST_COMPILE=max .venv/bin/python-local scripts/gpu_cabt_local_final_qualification.py
taskset -c 0,1 nice -n 10 env OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 .venv/bin/python-local .cache/interpreter_profile.py
taskset -c 0,1 nice -n 10 env OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 .venv/bin/python-local .cache/main_stage_profile.py
```

The report bundle is in this directory. `gpu_bottleneck_metrics.json` records exact commands, hashes, retained baseline values, state offsets, rule-table sizes, and compiler results.

## Negative Results And Pitfalls

- Public select-type sorting was 33% slower.
- Register cap 96 was flat.
- 64/128/256 launch geometry was flat; 512 was worse.
- External public-log storage had no meaningful gain.
- Fast PTX driver JIT produced 250 registers and 1,352 local bytes/thread.
- Wrapper-only stage kernels stayed at 128 registers.
- Do not retry monolithic optimized NVRTC or fast-compile mid/full on this laptop.
- Do not call 100% GPU utilization evidence of useful work.
- Do not claim memory bandwidth/cache saturation until Nsight or matched CUDA microbenchmarks exist.
- Any POC must compare terminal results, turns, errors, policy/event projections, and native 8-case/70-case differentials.
