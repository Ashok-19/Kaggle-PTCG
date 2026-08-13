from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from ptcg_rl.gpu_cabt.nvrtc import load_cupy_module
from ptcg_rl.gpu_cabt.source import build_cuda_source

FIELDS = {
    0: ("playerIndex",),
    1: ("playerIndex", "hasBasicPokemon"),
    2: ("playerIndex",),
    3: ("playerIndex",),
    4: ("playerIndex", "cardId", "serial"),
    5: ("playerIndex",),
    6: ("playerIndex", "cardId", "serial", "fromArea", "toArea"),
    7: ("playerIndex", "fromArea", "toArea"),
    8: ("playerIndex", "cardIdActive", "serialActive", "cardIdBench", "serialBench"),
    9: ("playerIndex", "cardIdBefore", "serialBefore", "cardIdAfter", "serialAfter"),
    10: ("playerIndex", "cardId", "serial"),
    11: ("playerIndex", "cardId", "serial", "cardIdTarget", "serialTarget"),
    12: ("playerIndex", "cardId", "serial", "cardIdTarget", "serialTarget"),
    13: ("playerIndex", "cardId", "serial", "cardIdTarget", "serialTarget"),
    14: ("playerIndex", "cardId", "serial", "cardIdBefore", "serialBefore", "cardIdAfter", "serialAfter"),
    15: ("playerIndex", "cardId", "serial", "attackId"),
    16: ("playerIndex", "cardId", "serial", "value", "putDamageCounter"),
    17: ("playerIndex", "isRecover", "cardId", "serial"),
    18: ("playerIndex", "isRecover", "cardId", "serial"),
    19: ("playerIndex", "isRecover", "cardId", "serial"),
    20: ("playerIndex", "isRecover", "cardId", "serial"),
    21: ("playerIndex", "isRecover", "cardId", "serial"),
    22: ("playerIndex", "head"),
    23: ("result", "reason"),
}

PROBE = r'''
extern "C" __global__ void gpu_cabt_public_log_diff_probe(
    const gc_i32* raw, const gc_i32* actors, gc_i32* out, gc_i32 count
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


def raw(log_type: int, params: tuple[int, ...]) -> list[int]:
    if len(params) > 7:
        raise ValueError("at most seven parameters")
    return [log_type, len(params), *params, *([0] * (7 - len(params)))]


def cases() -> list[tuple[str, int, int, tuple[int, ...]]]:
    base = {
        0: (0,), 1: (0, 1), 2: (0,), 3: (1,), 4: (0, 678, 47), 5: (1,),
        7: (1, 2, 3), 8: (0, 678, 47, 676, 44), 9: (0, 677, 47, 678, 47),
        10: (0, 1121, 20), 11: (0, 6, 18, 677, 47), 12: (0, 678, 20, 677, 47),
        13: (0, 677, 47, 678, 20), 14: (0, 6, 18, 677, 47, 676, 44),
        15: (0, 677, 47, 1556), 16: (1, 119, 63, -30, 1),
        17: (1, 0, 119, 63), 18: (1, 1, 119, 63), 19: (0, 0, 677, 47),
        20: (0, 1, 677, 47), 21: (1, 0, 119, 63), 22: (0, 1), 23: (0, 4),
    }
    result: list[tuple[str, int, int, tuple[int, ...]]] = []
    for actor in (0, 1):
        for log_type, params in base.items():
            result.append((f"type-{log_type}-actor-{actor}", actor, log_type, params))
        for owner in (0, 1):
            result.append((f"draw-owner-{owner}-actor-{actor}", actor, 4, (owner, 678, 91)))
            for open_type in (0, 1, 2, 3, 4):
                result.append((f"move-owner-{owner}-open-{open_type}-actor-{actor}", actor, 6, (owner, 678, 91, 2, 3, open_type)))
    return result


def native_rows(repo_root: Path, rows: list[tuple[str, int, int, tuple[int, ...]]]) -> list[dict[str, object]]:
    official = repo_root / "private/assets/official/ptcg_engine/ptcgProgram 22"
    source = repo_root / "scripts/gpu_cabt_public_log_native_probe.cpp"
    lines = [str(len(rows))]
    for _, actor, log_type, params in rows:
        values = [actor, log_type, len(params), *params, *([0] * (7 - len(params)))]
        lines.append(" ".join(str(value) for value in values))
    with tempfile.TemporaryDirectory(prefix="gpu-cabt-public-log-native-") as tmp:
        exe = Path(tmp) / "probe"
        subprocess.run(["g++", "-std=c++23", "-O2", "-I", str(official), str(source), "-o", str(exe)], check=True)
        output = subprocess.check_output([str(exe)], input=("\n".join(lines) + "\n").encode())
    parsed = [json.loads(line) for line in output.decode().splitlines() if line]
    if len(parsed) != len(rows):
        raise RuntimeError(f"native rows {len(parsed)} != {len(rows)}")
    return parsed


def expected_row(value: dict[str, object]) -> np.ndarray:
    log_type = int(value["type"])
    params = tuple(int(value[name]) for name in FIELDS[log_type])
    out = np.zeros(10, dtype=np.int32)
    out[0] = log_type
    out[1] = len(params)
    out[2 : 2 + len(params)] = params
    return out


def main() -> None:
    import cupy as cp

    repo_root = Path(__file__).resolve().parents[1]
    rows = cases()
    native = native_rows(repo_root, rows)
    raw_host = np.asarray([raw(log_type, params) for _, _, log_type, params in rows], dtype=np.int32)
    actors = np.asarray([actor for _, actor, _, _ in rows], dtype=np.int32)
    module = load_cupy_module(cp, build_cuda_source() + "\n" + PROBE, kernel_names=("gpu_cabt_public_log_diff_probe",))
    raw_gpu = cp.asarray(raw_host)
    actors_gpu = cp.asarray(actors)
    out_gpu = cp.empty((len(rows), 10), dtype=cp.int32)
    blocks = (len(rows) + 127) // 128
    module.get_function("gpu_cabt_public_log_diff_probe")((blocks,), (128,), (raw_gpu, actors_gpu, out_gpu, np.int32(len(rows))))
    cp.cuda.Stream.null.synchronize()
    actual = out_gpu.get()

    mismatches: list[dict[str, object]] = []
    covered_types: set[int] = set()
    for index, ((label, actor, raw_type, params), native_value) in enumerate(zip(rows, native, strict=True)):
        expected = expected_row(native_value)
        covered_types.add(int(native_value["type"]))
        if not np.array_equal(actual[index], expected):
            mismatches.append({
                "label": label, "actor": actor, "raw_type": raw_type, "params": list(params),
                "native": native_value, "expected": expected.tolist(), "actual": actual[index].tolist(),
            })
    required = set(range(24))
    if covered_types != required:
        mismatches.append({"coverage": sorted(covered_types), "missing": sorted(required - covered_types)})
    result = {
        "status": "PASS" if not mismatches else "FAIL",
        "cases": len(rows),
        "covered_public_types": sorted(covered_types),
        "mismatches": mismatches,
    }
    print(json.dumps(result, sort_keys=True))
    if mismatches:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
