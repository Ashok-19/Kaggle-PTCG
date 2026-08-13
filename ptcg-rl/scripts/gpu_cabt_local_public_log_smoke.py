from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from ptcg_rl.gpu_cabt.nvrtc import load_cupy_module
from ptcg_rl.gpu_cabt.public_log import project_public_log_for_actor
from ptcg_rl.gpu_cabt.source import build_cuda_source


_PROBE_SOURCE = r'''
extern "C" __global__ void gpu_cabt_public_log_probe(
    const gc_i32* raw,
    const gc_i32* actors,
    gc_i32* out,
    gc_i32 count
) {
    const gc_i32 i = (gc_i32)(blockDim.x * blockIdx.x + threadIdx.x);
    if (i >= count) return;
    const gc_i32* src = raw + (gc_i64)i * 9;
    gpu_cabt::PublicLogState log{};
    log.type = (gc_u8)src[0];
    log.param_count = (gc_u8)src[1];
    #pragma unroll
    for (gc_i32 p = 0; p < 7; ++p) log.param[p] = src[2 + p];
    gpu_cabt::project_public_log_for_actor(log, actors[i], out + (gc_i64)i * 10);
}
'''


def _raw(log_type: int, params: tuple[int, ...]) -> list[int]:
    if len(params) > 7:
        raise ValueError("raw public log supports at most seven parameters")
    return [log_type, len(params), *params, *([0] * (7 - len(params)))]


def main() -> None:
    import cupy as cp

    cases: list[tuple[str, int, int, tuple[int, ...]]] = [
        ("draw-self", 0, 4, (0, 678, 91)),
        ("draw-opponent", 0, 4, (1, 678, 91)),
        ("draw-reverse", 0, 5, (1,)),
        ("move-public-a0", 0, 6, (1, 678, 91, 2, 3, 0)),
        ("move-public-a1", 1, 6, (0, 678, 91, 2, 3, 0)),
        ("move-owner-private", 0, 6, (0, 678, 91, 2, 3, 1)),
        ("move-opponent-private", 1, 6, (0, 678, 91, 2, 3, 1)),
        ("move-hidden-a0", 0, 6, (0, 678, 91, 2, 3, 2)),
        ("move-hidden-a1", 1, 6, (0, 678, 91, 2, 3, 2)),
        ("move-viewer0-visible", 0, 6, (1, 678, 91, 2, 3, 3)),
        ("move-viewer0-hidden", 1, 6, (1, 678, 91, 2, 3, 3)),
        ("move-viewer1-hidden", 0, 6, (1, 678, 91, 2, 3, 4)),
        ("move-viewer1-visible", 1, 6, (0, 678, 91, 2, 3, 4)),
        ("move-reverse", 0, 7, (1, 2, 3)),
        ("coin-pass-through", 1, 22, (0, 1)),
    ]

    raw = np.asarray([_raw(log_type, params) for _, _, log_type, params in cases], dtype=np.int32)
    actors = np.asarray([actor for _, actor, _, _ in cases], dtype=np.int32)
    source = (
        build_cuda_source()
        + "\n"
        + _PROBE_SOURCE
        + "\n"
        + Path(__file__).with_name("gpu_cabt_public_log_probe.cu").read_text()
    )
    kernel_names = (
        "gpu_cabt_runtime_info",
        "gpu_cabt_project_events",
        "gpu_cabt_public_log_probe",
        "gpu_cabt_public_log_burst_setup",
        "gpu_cabt_public_log_set_actor",
        "gpu_cabt_public_log_terminal_setup",
        "gpu_cabt_public_log_effect_win_setup",
        "gpu_cabt_public_log_runtime_snapshot",
    )
    module = load_cupy_module(cp, source, kernel_names=kernel_names)
    kernel = module.get_function("gpu_cabt_public_log_probe")
    raw_gpu = cp.asarray(raw)
    actors_gpu = cp.asarray(actors)
    out_gpu = cp.zeros((len(cases), 10), dtype=cp.int32)
    blocks = (len(cases) + 127) // 128
    kernel((blocks,), (128,), (raw_gpu, actors_gpu, out_gpu, np.int32(len(cases))))
    cp.cuda.Stream.null.synchronize()
    actual = out_gpu.get()

    mismatches: list[dict[str, object]] = []
    for index, (label, actor, log_type, params) in enumerate(cases):
        expected_type, expected_params = project_public_log_for_actor(log_type, params, actor=actor)
        expected = np.zeros(10, dtype=np.int32)
        expected[0] = expected_type
        expected[1] = len(expected_params)
        expected[2 : 2 + len(expected_params)] = expected_params
        if not np.array_equal(actual[index], expected):
            mismatches.append(
                {
                    "label": label,
                    "actor": actor,
                    "actual": actual[index].tolist(),
                    "expected": expected.tolist(),
                }
            )

    runtime_info = cp.empty(14, dtype=cp.int32)
    module.get_function("gpu_cabt_runtime_info")((1,), (1,), (runtime_info,))
    abi = runtime_info.get().tolist()
    state_bytes = int(abi[0])
    runtime_bytes = int(abi[1])
    event_capacity = int(abi[12])
    event_width = int(abi[13])
    states = cp.empty(state_bytes, dtype=cp.uint8)
    runtimes = cp.empty(runtime_bytes, dtype=cp.uint8)
    events = cp.zeros((1, event_capacity, event_width), dtype=cp.int32)
    event_counts = cp.empty(1, dtype=cp.int32)
    event_status = cp.empty(1, dtype=cp.uint32)
    runtime_snapshot = cp.empty(4, dtype=cp.int32)
    event_kernel = module.get_function("gpu_cabt_project_events")
    snapshot_kernel = module.get_function("gpu_cabt_public_log_runtime_snapshot")

    burst_count = 257
    module.get_function("gpu_cabt_public_log_burst_setup")(
        (1,), (1,), (states, runtimes, np.int32(burst_count))
    )
    event_kernel(
        (1,),
        (128,),
        (
            states,
            runtimes,
            events,
            event_counts,
            event_status,
            np.uint8(1),
            np.int32(1),
        ),
    )
    snapshot_kernel((1,), (1,), (runtimes, runtime_snapshot))
    cp.cuda.Stream.null.synchronize()
    first_count = int(event_counts.get()[0])
    first_status = int(event_status.get()[0])
    first_snapshot = runtime_snapshot.get().tolist()
    first_events = events.get()[0, :burst_count]
    expected_burst = np.zeros((burst_count, event_width), dtype=np.int32)
    sequence = np.arange(burst_count, dtype=np.int32)
    expected_burst[:, 0] = 22
    expected_burst[:, 1] = 2
    expected_burst[:, 2] = sequence & 1
    expected_burst[:, 3] = (sequence >> 1) & 1
    if (
        first_count != burst_count
        or first_status != 0
        or first_snapshot != [burst_count, burst_count, 0, 0]
        or not np.array_equal(first_events, expected_burst)
    ):
        mismatches.append(
            {
                "label": "burst-first-ack",
                "count": first_count,
                "status": first_status,
                "snapshot": first_snapshot,
            }
        )

    module.get_function("gpu_cabt_public_log_set_actor")(
        (1,), (1,), (states, np.int32(1))
    )
    event_kernel(
        (1,),
        (128,),
        (
            states,
            runtimes,
            events,
            event_counts,
            event_status,
            np.uint8(1),
            np.int32(1),
        ),
    )
    snapshot_kernel((1,), (1,), (runtimes, runtime_snapshot))
    cp.cuda.Stream.null.synchronize()
    second_count = int(event_counts.get()[0])
    second_status = int(event_status.get()[0])
    second_snapshot = runtime_snapshot.get().tolist()
    second_events = events.get()[0, :burst_count]
    if (
        second_count != burst_count
        or second_status != 0
        or second_snapshot != [0, 0, 0, 0]
        or not np.array_equal(second_events, expected_burst)
    ):
        mismatches.append(
            {
                "label": "burst-second-ack",
                "count": second_count,
                "status": second_status,
                "snapshot": second_snapshot,
            }
        )

    module.get_function("gpu_cabt_public_log_terminal_setup")(
        (1,), (1,), (states, runtimes, np.int32(1))
    )
    event_kernel(
        (1,),
        (128,),
        (
            states,
            runtimes,
            events,
            event_counts,
            event_status,
            np.uint8(0),
            np.int32(1),
        ),
    )
    cp.cuda.Stream.null.synchronize()
    terminal_count = int(event_counts.get()[0])
    terminal_status = int(event_status.get()[0])
    terminal_event = events.get()[0, 0]
    expected_terminal = np.zeros(event_width, dtype=np.int32)
    expected_terminal[:4] = (23, 2, 0, 1)
    if (
        terminal_count != 1
        or terminal_status != 0
        or not np.array_equal(terminal_event, expected_terminal)
    ):
        mismatches.append(
            {
                "label": "terminal-result",
                "count": terminal_count,
                "status": terminal_status,
                "event": terminal_event.tolist(),
            }
        )

    module.get_function("gpu_cabt_public_log_effect_win_setup")(
        (1,), (1,), (states, runtimes)
    )
    event_kernel(
        (1,),
        (128,),
        (
            states,
            runtimes,
            events,
            event_counts,
            event_status,
            np.uint8(0),
            np.int32(1),
        ),
    )
    cp.cuda.Stream.null.synchronize()
    effect_win_count = int(event_counts.get()[0])
    effect_win_status = int(event_status.get()[0])
    effect_win_event = events.get()[0, 0]
    expected_effect_win = np.zeros(event_width, dtype=np.int32)
    expected_effect_win[:4] = (23, 2, 0, 4)
    if (
        effect_win_count != 1
        or effect_win_status != 0
        or not np.array_equal(effect_win_event, expected_effect_win)
    ):
        mismatches.append(
            {
                "label": "effect-win-result",
                "count": effect_win_count,
                "status": effect_win_status,
                "event": effect_win_event.tolist(),
            }
        )

    result = {
        "status": "PASS" if not mismatches else "FAIL",
        "cases": len(cases),
        "mismatches": mismatches,
    }
    print(json.dumps(result, sort_keys=True))
    if mismatches:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
