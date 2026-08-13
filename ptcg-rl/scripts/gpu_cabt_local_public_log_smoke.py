from __future__ import annotations

import json

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
    gpu_cabt::project_public_log_for_actor(log, actors[i], i, out + (gc_i64)i * 10);
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
    source = build_cuda_source() + "\n" + _PROBE_SOURCE
    module = load_cupy_module(cp, source, kernel_names=("gpu_cabt_public_log_probe",))
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
        expected[9] = index
        if not np.array_equal(actual[index], expected):
            mismatches.append(
                {
                    "label": label,
                    "actor": actor,
                    "actual": actual[index].tolist(),
                    "expected": expected.tolist(),
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
