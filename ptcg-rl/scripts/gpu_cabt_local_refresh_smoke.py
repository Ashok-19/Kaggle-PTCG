from __future__ import annotations

import argparse
import csv
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from ptcg_rl.gpu_cabt.nvrtc import load_cupy_module
from ptcg_rl.gpu_cabt.rule_static import extract_rule_tables

_SNAPSHOT_WORDS = 848
_MODES = 6


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Broad native CABT vs CUDA RefreshEffect differential")
    parser.add_argument("--deck0", type=Path, required=True)
    parser.add_argument("--deck1", type=Path, required=True)
    return parser.parse_args()


def _load_deck(path: Path) -> list[int]:
    values: list[int] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.reader(handle):
            values.extend(int(value) for value in row if value.strip())
    if len(values) != 60:
        raise ValueError(f"{path} must contain exactly 60 card IDs")
    return values


def _native_snapshot(repo_root: Path, deck0: list[int], deck1: list[int]) -> np.ndarray:
    official = repo_root / "private/assets/official/ptcg_engine/ptcgProgram 22"
    input_text = " ".join(map(str, deck0 + deck1)) + "\n"
    with tempfile.TemporaryDirectory(prefix="gpu-cabt-refresh-native-") as tmp:
        exe = Path(tmp) / "probe"
        subprocess.run(
            [
                "g++",
                "-std=c++23",
                "-O2",
                "-I",
                str(official),
                str(repo_root / "scripts/gpu_cabt_refresh_probe.cpp"),
                "-o",
                str(exe),
            ],
            check=True,
        )
        raw = subprocess.check_output([str(exe)], input=input_text.encode())
    expected_bytes = _MODES * _SNAPSHOT_WORDS * 8
    if len(raw) != expected_bytes:
        raise RuntimeError(f"native refresh bytes {len(raw)} != {expected_bytes}")
    return np.frombuffer(raw, dtype=np.uint64).reshape(_MODES, _SNAPSHOT_WORDS).copy()


def main() -> int:
    args = _parse_args()
    import cupy as cp

    repo_root = Path(__file__).resolve().parents[1]
    official = repo_root / "private/assets/official/ptcg_engine/ptcgProgram 22"
    deck0, deck1 = _load_deck(args.deck0), _load_deck(args.deck1)
    blob = extract_rule_tables(official, repo_root)
    rule_parts = (
        blob.cards,
        blob.skills,
        blob.attacks,
        blob.effects,
        blob.triggers,
        blob.substring_masks,
    )
    rule_device = [
        cp.asarray(np.frombuffer(part, dtype=np.uint8)) for part in rule_parts
    ]

    source_paths = (
        "src/ptcg_rl/gpu_cabt/native/state_core.h",
        "src/ptcg_rl/gpu_cabt/native/state_fields.h",
        "src/ptcg_rl/gpu_cabt/native/runtime_state.h",
        "src/ptcg_rl/gpu_cabt/native/rule_static.h",
        "src/ptcg_rl/gpu_cabt/cuda/rng_shuffle.cu",
        "src/ptcg_rl/gpu_cabt/cuda/battle_init.cu",
        "src/ptcg_rl/gpu_cabt/cuda/setup_is_first.cu",
        "src/ptcg_rl/gpu_cabt/cuda/rule_runtime_helpers.cu",
        "src/ptcg_rl/gpu_cabt/cuda/target_list.cu",
        "src/ptcg_rl/gpu_cabt/cuda/satisfy_condition.cu",
        "src/ptcg_rl/gpu_cabt/cuda/effect_continual.cu",
        "src/ptcg_rl/gpu_cabt/cuda/refresh_effect.cu",
        "src/ptcg_rl/gpu_cabt/cuda/refresh_probe.cu",
    )
    source = "\n".join(
        (repo_root / path).read_text(encoding="utf-8") for path in source_paths
    )
    module = load_cupy_module(
        cp,
        source,
        kernel_names=(
            "gpu_cabt_battle_core_size",
            "gpu_cabt_runtime_size",
            "gpu_cabt_init_battles",
            "gpu_cabt_force_refresh_synthetic",
            "gpu_cabt_refresh_effect_kernel",
            "gpu_cabt_refresh_probe_snapshot",
        ),
    )
    state_size_out = cp.empty(1, dtype=cp.uint64)
    runtime_size_out = cp.empty(1, dtype=cp.uint64)
    module.get_function("gpu_cabt_battle_core_size")((1,), (1,), (state_size_out,))
    module.get_function("gpu_cabt_runtime_size")((1,), (1,), (runtime_size_out,))
    cp.cuda.Stream.null.synchronize()
    state_size = int(cp.asnumpy(state_size_out)[0])
    runtime_size = int(cp.asnumpy(runtime_size_out)[0])

    decks = cp.asarray(
        np.tile(np.asarray(deck0 + deck1, dtype=np.int32), (_MODES, 1))
    )
    states = cp.empty(_MODES * state_size, dtype=cp.uint8)
    runtimes = cp.empty(_MODES * runtime_size, dtype=cp.uint8)
    modes = cp.asarray(np.arange(_MODES, dtype=np.int32))
    snapshots = cp.empty((_MODES, _SNAPSHOT_WORDS), dtype=cp.uint64)
    errors = cp.empty(_MODES, dtype=cp.uint32)
    threads, blocks = 64, 1
    module.get_function("gpu_cabt_init_battles")(
        (blocks,), (threads,), (states, decks, np.int32(_MODES))
    )
    module.get_function("gpu_cabt_force_refresh_synthetic")(
        (blocks,), (threads,), (states, runtimes, modes, np.int32(_MODES))
    )
    module.get_function("gpu_cabt_refresh_effect_kernel")(
        (blocks,),
        (threads,),
        (
            states,
            runtimes,
            *rule_device,
            np.int32(blob.card_count),
            np.int32(blob.skill_count),
            np.int32(blob.attack_count),
            np.int32(blob.effect_count),
            np.int32(blob.trigger_count),
            np.int32(blob.substring_mask_count),
            np.int32(blob.substring_mask_words),
            np.int32(_MODES),
        ),
    )
    module.get_function("gpu_cabt_refresh_probe_snapshot")(
        (blocks,),
        (threads,),
        (states, runtimes, snapshots, errors, np.int32(_MODES)),
    )
    cp.cuda.Stream.null.synchronize()
    actual = cp.asnumpy(snapshots)
    error_values = cp.asnumpy(errors)
    expected = _native_snapshot(repo_root, deck0, deck1)
    match = bool(np.array_equal(actual, expected))
    mismatch_count = int(np.count_nonzero(actual != expected))
    first_mismatch = None
    if mismatch_count:
        location = np.argwhere(actual != expected)[0]
        mode, column = map(int, location)
        first_mismatch = {
            "mode": mode,
            "column": column,
            "native": int(expected[mode, column]),
            "cuda": int(actual[mode, column]),
        }
    errors_clear = bool(np.all(error_values == 0))
    free_vram, total_vram = cp.cuda.runtime.memGetInfo()
    device_name = cp.cuda.runtime.getDeviceProperties(0)["name"]
    if isinstance(device_name, bytes):
        device_name = device_name.decode()
    result = {
        "device": str(device_name),
        "modes": _MODES,
        "snapshot_words_per_mode": _SNAPSHOT_WORDS,
        "compared_words": int(expected.size),
        "differential_match": match,
        "mismatch_count": mismatch_count,
        "first_mismatch": first_mismatch,
        "runtime_errors": [int(value) for value in error_values.tolist()],
        "runtime_errors_clear": errors_clear,
        "state_bytes_per_env": state_size,
        "runtime_bytes_per_env": runtime_size,
        "rule_table_bytes": blob.total_bytes,
        "free_vram_bytes": int(free_vram),
        "total_vram_bytes": int(total_vram),
    }
    print(result)
    return 0 if match and errors_clear else 1


if __name__ == "__main__":
    raise SystemExit(main())
