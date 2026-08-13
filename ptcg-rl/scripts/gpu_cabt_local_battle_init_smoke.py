from __future__ import annotations

import argparse
import csv
import json
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np

from ptcg_rl.gpu_cabt.nvrtc import load_cupy_module

_SNAPSHOT_SIZE = 625


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Official CPU vs CUDA BattleData::init differential")
    parser.add_argument("--deck0", type=Path, required=True)
    parser.add_argument("--deck1", type=Path, required=True)
    parser.add_argument("--env-count", type=int, default=8192)
    parser.add_argument("--benchmark-repeats", type=int, default=10)
    return parser.parse_args()


def _load_deck(path: Path) -> list[int]:
    values: list[int] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.reader(handle):
            values.extend(int(value) for value in row if value.strip())
    if len(values) != 60:
        raise ValueError(f"{path} must contain exactly 60 card IDs, found {len(values)}")
    return values


def _official_init_snapshot(repo_root: Path, deck0: list[int], deck1: list[int]) -> list[int]:
    official_dir = repo_root / "private/assets/official/ptcg_engine/ptcgProgram 22"
    deck0_cpp = ",".join(str(value) for value in deck0)
    deck1_cpp = ",".join(str(value) for value in deck1)
    source = f'''#include <iostream>\n#include "All.h"\n\nint main() {{\n    InitializeAll();\n    GameConfig config = {{}};\n    config.seed = 123456789u;\n    config.recordLog = false;\n    config.deviceRand = false;\n    const int deck0[60] = {{{deck0_cpp}}};\n    const int deck1[60] = {{{deck1_cpp}}};\n    for (int i = 0; i < 60; ++i) {{\n        config.decks[0].cards[i] = deck0[i];\n        config.decks[1].cards[i] = deck1[i];\n    }}\n    BattleData battle;\n    battle.init(config);\n    const State& state = battle.state;\n    auto emit = [](int value) {{ std::cout << value << ' '; }};\n    emit(state.moveCounter);\n    emit((int)state.firstPlayer);\n    emit(state.turn);\n    emit(state.turnActionCount);\n    emit(state.effectActionCount);\n    emit(state.turnAttackCount);\n    emit((int)state.phase);\n    emit((int)state.gameResult);\n    emit((int)state.finishReason);\n    emit((int)state.players[0].playerIndex);\n    emit((int)state.players[1].playerIndex);\n    emit((int)state.players[0].deck.size());\n    emit((int)state.players[1].deck.size());\n    for (int player = 0; player < 2; ++player) {{\n        for (int i = 0; i < 60; ++i) emit((int)state.players[player].deck[i].cardIndex);\n    }}\n    for (int i = 0; i <= 122; ++i) {{\n        const Card& card = state.allCard[i];\n        emit(card.cardId);\n        emit(card.moveCounter);\n        emit((int)card.playerIndex);\n        emit((int)card.area);\n    }}\n    std::cout << '\\n';\n}}\n'''
    with tempfile.TemporaryDirectory(prefix="gpu-cabt-official-init-") as tmp:
        tmp_path = Path(tmp)
        cpp_path = tmp_path / "probe.cpp"
        exe_path = tmp_path / "probe"
        cpp_path.write_text(source, encoding="utf-8")
        subprocess.run(
            [
                "g++",
                "-std=c++23",
                "-O2",
                "-I",
                str(official_dir),
                str(cpp_path),
                "-o",
                str(exe_path),
            ],
            check=True,
        )
        output = subprocess.check_output([str(exe_path)], text=True)
    values = [int(value) for value in output.split()]
    if len(values) != _SNAPSHOT_SIZE:
        raise RuntimeError(f"official snapshot length {len(values)} != {_SNAPSHOT_SIZE}")
    return values


def main() -> int:
    args = _parse_args()
    if args.env_count <= 0 or args.benchmark_repeats <= 0:
        raise ValueError("env-count and benchmark-repeats must be positive")

    import cupy as cp

    repo_root = Path(__file__).resolve().parents[1]
    deck0 = _load_deck(args.deck0)
    deck1 = _load_deck(args.deck1)
    official_snapshot = np.asarray(_official_init_snapshot(repo_root, deck0, deck1), dtype=np.int32)

    header = (repo_root / "src/ptcg_rl/gpu_cabt/native/state_core.h").read_text(encoding="utf-8")
    kernel_source = (repo_root / "src/ptcg_rl/gpu_cabt/cuda/battle_init.cu").read_text(
        encoding="utf-8"
    )
    module = load_cupy_module(
        cp,
        header + "\n" + kernel_source,
        kernel_names=(
            "gpu_cabt_battle_core_size",
            "gpu_cabt_init_battles",
            "gpu_cabt_init_snapshot",
        ),
    )
    size_kernel = module.get_function("gpu_cabt_battle_core_size")
    init_kernel = module.get_function("gpu_cabt_init_battles")
    snapshot_kernel = module.get_function("gpu_cabt_init_snapshot")

    size_out = cp.empty(1, dtype=cp.uint64)
    size_kernel((1,), (1,), (size_out,))
    cp.cuda.Stream.null.synchronize()
    state_size = int(cp.asnumpy(size_out)[0])

    deck_pair = np.asarray(deck0 + deck1, dtype=np.int32)
    host_decks = np.tile(deck_pair, (args.env_count, 1))
    device_decks = cp.asarray(host_decks)
    raw_states = cp.empty(args.env_count * state_size, dtype=cp.uint8)
    snapshots = cp.empty((args.env_count, _SNAPSHOT_SIZE), dtype=cp.int32)

    threads = 128
    blocks = (args.env_count + threads - 1) // threads
    init_kernel((blocks,), (threads,), (raw_states, device_decks, np.int32(args.env_count)))
    snapshot_kernel((blocks,), (threads,), (raw_states, snapshots, np.int32(args.env_count)))
    cp.cuda.Stream.null.synchronize()
    gpu_snapshots = cp.asnumpy(snapshots)
    differential_match = bool(np.all(gpu_snapshots == official_snapshot[None, :]))

    init_kernel((blocks,), (threads,), (raw_states, device_decks, np.int32(args.env_count)))
    cp.cuda.Stream.null.synchronize()
    started = time.perf_counter()
    for _ in range(args.benchmark_repeats):
        init_kernel((blocks,), (threads,), (raw_states, device_decks, np.int32(args.env_count)))
    cp.cuda.Stream.null.synchronize()
    elapsed = time.perf_counter() - started

    free_vram, total_vram = cp.cuda.runtime.memGetInfo()
    device_name = cp.cuda.runtime.getDeviceProperties(0)["name"]
    if isinstance(device_name, bytes):
        device_name = device_name.decode()
    report = {
        "device": str(device_name),
        "env_count": args.env_count,
        "state_bytes_per_env": state_size,
        "differential_match": differential_match,
        "snapshot_ints": _SNAPSHOT_SIZE,
        "benchmark_repeats": args.benchmark_repeats,
        "benchmark_seconds": elapsed,
        "battle_inits_per_second": (args.env_count * args.benchmark_repeats) / elapsed,
        "cupy_pool_bytes": int(cp.get_default_memory_pool().total_bytes()),
        "free_vram_bytes": int(free_vram),
        "total_vram_bytes": int(total_vram),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if differential_match else 1


if __name__ == "__main__":
    raise SystemExit(main())
