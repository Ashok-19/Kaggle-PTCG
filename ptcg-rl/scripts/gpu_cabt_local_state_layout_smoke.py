from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from ptcg_rl.gpu_cabt.nvrtc import load_cupy_module


_DESCRIPTOR_NAMES = (
    "area_ref_size",
    "activate_ability_info_size",
    "trigger_info_size",
    "effect_state_size",
    "turn_history_size",
    "card_state_size",
    "player_state_size",
    "battle_core_state_size",
    "battle_players_offset",
    "battle_all_card_offset",
    "battle_effect_state_offset",
    "battle_select_counts_offset",
    "card_continual_state_offset",
    "player_deck_offset",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Host/CUDA GPU CABT state-layout smoke")
    parser.add_argument("--env-count", type=int, default=8192)
    return parser.parse_args()


def _host_layout(repo_root: Path) -> list[int]:
    header_dir = repo_root / "src/ptcg_rl/gpu_cabt/native"
    source = r'''
#include <cstddef>
#include <iostream>
#include "state_core.h"
int main() {
    using namespace gpu_cabt;
    std::cout
        << sizeof(AreaRef) << ' '
        << sizeof(ActivateAbilityInfo) << ' '
        << sizeof(TriggerInfo) << ' '
        << sizeof(EffectState) << ' '
        << sizeof(TurnHistory) << ' '
        << sizeof(CardState) << ' '
        << sizeof(PlayerState) << ' '
        << sizeof(BattleCoreState) << ' '
        << offsetof(BattleCoreState, players) << ' '
        << offsetof(BattleCoreState, all_card) << ' '
        << offsetof(BattleCoreState, effect_state) << ' '
        << offsetof(BattleCoreState, select_counts) << ' '
        << offsetof(CardState, continual_state) << ' '
        << offsetof(PlayerState, deck) << '\n';
}
'''
    with tempfile.TemporaryDirectory(prefix="gpu-cabt-layout-") as tmp:
        tmp_path = Path(tmp)
        cpp_path = tmp_path / "probe.cpp"
        exe_path = tmp_path / "probe"
        cpp_path.write_text(source, encoding="utf-8")
        subprocess.run(
            ["g++", "-std=c++17", "-O2", "-I", str(header_dir), str(cpp_path), "-o", str(exe_path)],
            check=True,
        )
        output = subprocess.check_output([str(exe_path)], text=True).strip()
    return [int(value) for value in output.split()]


def main() -> int:
    args = _parse_args()
    if args.env_count <= 0:
        raise ValueError("env-count must be positive")

    import cupy as cp

    repo_root = Path(__file__).resolve().parents[1]
    header = (repo_root / "src/ptcg_rl/gpu_cabt/native/state_core.h").read_text(encoding="utf-8")
    kernel = (repo_root / "src/ptcg_rl/gpu_cabt/cuda/state_layout_probe.cu").read_text(
        encoding="utf-8"
    )
    module = load_cupy_module(
        cp,
        header + "\n" + kernel,
        kernel_names=("gpu_cabt_state_layout_probe", "gpu_cabt_fill_core_state_pattern"),
    )
    probe = module.get_function("gpu_cabt_state_layout_probe")
    fill = module.get_function("gpu_cabt_fill_core_state_pattern")

    host_values = _host_layout(repo_root)
    device_values = cp.empty(len(_DESCRIPTOR_NAMES), dtype=cp.uint64)
    probe((1,), (1,), (device_values,))
    cp.cuda.Stream.null.synchronize()
    gpu_values = [int(value) for value in cp.asnumpy(device_values)]
    layout_match = host_values == gpu_values

    descriptors = dict(zip(_DESCRIPTOR_NAMES, gpu_values, strict=True))
    state_size = descriptors["battle_core_state_size"]
    free_before, total_vram = cp.cuda.runtime.memGetInfo()
    raw = cp.empty(args.env_count * state_size, dtype=cp.uint8)
    threads = 128
    blocks = (args.env_count + threads - 1) // threads
    fill((blocks,), (threads,), (raw, np.int32(state_size), np.int32(args.env_count)))
    cp.cuda.Stream.null.synchronize()

    sample = cp.asnumpy(raw[: min(raw.size, state_size * 2)])
    pattern_valid = True
    for linear_index, value in enumerate(sample):
        env_index = linear_index // state_size
        offset = linear_index % state_size
        expected = (offset * 131 + env_index * 17 + 23) & 0xFF
        if int(value) != expected:
            pattern_valid = False
            break

    free_after, _ = cp.cuda.runtime.memGetInfo()
    pool_bytes = int(cp.get_default_memory_pool().total_bytes())
    device_name = cp.cuda.runtime.getDeviceProperties(0)["name"]
    if isinstance(device_name, bytes):
        device_name = device_name.decode()
    report = {
        "device": str(device_name),
        "layout_match": layout_match,
        "pattern_valid": pattern_valid,
        "env_count": args.env_count,
        "state_bytes_per_env": state_size,
        "state_allocation_bytes": args.env_count * state_size,
        "total_vram_bytes": int(total_vram),
        "free_vram_before_bytes": int(free_before),
        "free_vram_after_bytes": int(free_after),
        "cupy_pool_bytes": pool_bytes,
        "descriptors": descriptors,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if layout_match and pattern_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
