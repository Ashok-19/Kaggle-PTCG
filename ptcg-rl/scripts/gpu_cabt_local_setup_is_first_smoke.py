from __future__ import annotations

import argparse
import csv
import json
import subprocess
import tempfile
import time
from pathlib import Path

import numpy as np

from ptcg_rl.gpu_cabt.rng import shuffle_in_place
from ptcg_rl.gpu_cabt.nvrtc import load_cupy_module

_SNAPSHOT_SIZE = 140


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CUDA SetupGame -> IsFirst boundary differential")
    parser.add_argument("--deck0", type=Path, required=True)
    parser.add_argument("--deck1", type=Path, required=True)
    parser.add_argument("--env-count", type=int, default=8192)
    parser.add_argument("--benchmark-repeats", type=int, default=10)
    parser.add_argument("--differential-envs", type=int, default=None)
    parser.add_argument("--seed", type=int, default=0x123456789ABCDEF0)
    parser.add_argument("--stream-base", type=int, default=0xABC00000)
    return parser.parse_args()


def _load_deck(path: Path) -> list[int]:
    values: list[int] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.reader(handle):
            values.extend(int(value) for value in row if value.strip())
    if len(values) != 60:
        raise ValueError(f"{path} must contain exactly 60 card IDs")
    return values


def _official_semantic_prefix(repo_root: Path, deck0: list[int], deck1: list[int]) -> list[int]:
    official_dir = repo_root / "private/assets/official/ptcg_engine/ptcgProgram 22"
    arrays = [",".join(str(value) for value in deck) for deck in (deck0, deck1)]
    source = f'''#include <iostream>\n#include "All.h"\nint main() {{\n InitializeAll(); GameConfig c={{}}; c.seed=1; c.recordLog=false; c.deviceRand=false;\n const int d0[60]={{{arrays[0]}}}; const int d1[60]={{{arrays[1]}}};\n for(int i=0;i<60;++i){{c.decks[0].cards[i]=d0[i];c.decks[1].cards[i]=d1[i];}}\n BattleData b; b.init(c); State& s=b.state;\n s.changed=true; SetYesNoSelect(s, SelectContext::IsFirst, 0); s.pushFunction(SelectedIsFirst);\n auto emit=[](long long v){{std::cout<<v<<' ';}};\n emit(s.changed); emit((int)s.selectType); emit((int)s.selectContext); emit((int)s.selectPlayer);\n emit(s.selectMin); emit(s.selectMax); emit((int)s.options.size()); emit((int)s.selected.size());\n emit((int)s.functionStack.size()); emit(0); emit(0); emit(0);\n emit((int)s.options[0].type); emit((int)s.options[1].type);\n auto &gf=s.functionStack.back(); emit(FunctionTable.at(gf.functionIndex)==(void*)SelectedIsFirst ? 1 : -1); emit((int)gf.callCount);\n emit((int)s.players[0].deck.size()); emit((int)s.players[1].deck.size());\n for(int p=0;p<2;++p) for(int i=0;i<60;++i) emit((int)s.players[p].deck[i].cardIndex);\n emit(s.moveCounter); emit(s.turn); std::cout<<'\\n';\n}}\n'''
    with tempfile.TemporaryDirectory(prefix="gpu-cabt-setup-semantic-") as tmp:
        cpp = Path(tmp) / "probe.cpp"
        exe = Path(tmp) / "probe"
        cpp.write_text(source, encoding="utf-8")
        subprocess.run(
            ["g++", "-std=c++23", "-O2", "-I", str(official_dir), str(cpp), "-o", str(exe)],
            check=True,
        )
        values = [int(value) for value in subprocess.check_output([str(exe)], text=True).split()]
    if len(values) != _SNAPSHOT_SIZE:
        raise RuntimeError(f"official semantic prefix length {len(values)} != {_SNAPSHOT_SIZE}")
    return values


def _expected_snapshot(
    semantic_prefix: list[int], *, seed: int, stream: int
) -> np.ndarray:
    expected = list(semantic_prefix)
    deck0 = expected[18:78]
    deck1 = expected[78:138]
    draw_index = 0
    draw_index = shuffle_in_place(deck0, seed=seed, stream=stream, draw_index=draw_index)
    draw_index = shuffle_in_place(deck1, seed=seed, stream=stream, draw_index=draw_index)
    expected[10] = draw_index & 0xFFFFFFFF
    expected[11] = (draw_index >> 32) & 0xFFFFFFFF
    expected[18:78] = deck0
    expected[78:138] = deck1
    return np.asarray(expected, dtype=np.int32)


def _host_runtime_size(repo_root: Path) -> int:
    source = '''#include <iostream>\n#include "state_core.h"\n#include "runtime_state.h"\nint main(){std::cout<<sizeof(gpu_cabt::BattleRuntimeState)<<"\\n";}\n'''
    include_dir = repo_root / "src/ptcg_rl/gpu_cabt/native"
    with tempfile.TemporaryDirectory(prefix="gpu-cabt-runtime-size-") as tmp:
        cpp = Path(tmp) / "probe.cpp"
        exe = Path(tmp) / "probe"
        cpp.write_text(source, encoding="utf-8")
        subprocess.run(
            ["g++", "-std=c++17", "-O2", "-I", str(include_dir), str(cpp), "-o", str(exe)],
            check=True,
        )
        return int(subprocess.check_output([str(exe)], text=True).strip())


def main() -> int:
    args = _parse_args()
    if args.env_count <= 0 or args.benchmark_repeats <= 0:
        raise ValueError("env-count and benchmark-repeats must be positive")
    differential_envs = args.env_count if args.differential_envs is None else args.differential_envs
    if differential_envs <= 0 or differential_envs > args.env_count:
        raise ValueError("differential-envs must be in [1, env-count]")

    import cupy as cp

    repo_root = Path(__file__).resolve().parents[1]
    deck0 = _load_deck(args.deck0)
    deck1 = _load_deck(args.deck1)
    semantic_prefix = _official_semantic_prefix(repo_root, deck0, deck1)

    state_header = (repo_root / "src/ptcg_rl/gpu_cabt/native/state_core.h").read_text()
    runtime_header = (repo_root / "src/ptcg_rl/gpu_cabt/native/runtime_state.h").read_text()
    rng_source = (repo_root / "src/ptcg_rl/gpu_cabt/cuda/rng_shuffle.cu").read_text()
    init_source = (repo_root / "src/ptcg_rl/gpu_cabt/cuda/battle_init.cu").read_text()
    setup_source = (repo_root / "src/ptcg_rl/gpu_cabt/cuda/setup_is_first.cu").read_text()
    module = load_cupy_module(
        cp,
        "\n".join((state_header, runtime_header, rng_source, init_source, setup_source)),
        kernel_names=(
            "gpu_cabt_battle_core_size",
            "gpu_cabt_runtime_size",
            "gpu_cabt_init_battles",
            "gpu_cabt_setup_is_first",
            "gpu_cabt_setup_is_first_snapshot",
        ),
    )
    state_size_kernel = module.get_function("gpu_cabt_battle_core_size")
    runtime_size_kernel = module.get_function("gpu_cabt_runtime_size")
    init_kernel = module.get_function("gpu_cabt_init_battles")
    setup_kernel = module.get_function("gpu_cabt_setup_is_first")
    snapshot_kernel = module.get_function("gpu_cabt_setup_is_first_snapshot")

    state_size_out = cp.empty(1, dtype=cp.uint64)
    runtime_size_out = cp.empty(1, dtype=cp.uint64)
    state_size_kernel((1,), (1,), (state_size_out,))
    runtime_size_kernel((1,), (1,), (runtime_size_out,))
    cp.cuda.Stream.null.synchronize()
    state_size = int(cp.asnumpy(state_size_out)[0])
    runtime_size = int(cp.asnumpy(runtime_size_out)[0])
    host_runtime_size = _host_runtime_size(repo_root)

    pair = np.asarray(deck0 + deck1, dtype=np.int32)
    device_decks = cp.asarray(np.tile(pair, (args.env_count, 1)))
    raw_states = cp.empty(args.env_count * state_size, dtype=cp.uint8)
    raw_runtimes = cp.empty(args.env_count * runtime_size, dtype=cp.uint8)
    snapshots = cp.empty((args.env_count, _SNAPSHOT_SIZE), dtype=cp.int32)
    threads = 128
    blocks = (args.env_count + threads - 1) // threads

    init_kernel((blocks,), (threads,), (raw_states, device_decks, np.int32(args.env_count)))
    setup_kernel(
        (blocks,),
        (threads,),
        (raw_states, raw_runtimes, np.uint64(args.seed), np.uint64(args.stream_base), np.int32(args.env_count)),
    )
    snapshot_kernel((blocks,), (threads,), (raw_states, raw_runtimes, snapshots, np.int32(args.env_count)))
    cp.cuda.Stream.null.synchronize()
    gpu_snapshots = cp.asnumpy(snapshots)

    runtime_errors_clear = bool(np.all(gpu_snapshots[:, 9] == 0))
    all_match = True
    for env_index in range(differential_envs):
        expected = _expected_snapshot(
            semantic_prefix, seed=args.seed, stream=args.stream_base + env_index
        )
        if not np.array_equal(gpu_snapshots[env_index], expected):
            all_match = False
            break

    init_kernel((blocks,), (threads,), (raw_states, device_decks, np.int32(args.env_count)))
    setup_kernel(
        (blocks,),
        (threads,),
        (raw_states, raw_runtimes, np.uint64(args.seed), np.uint64(args.stream_base), np.int32(args.env_count)),
    )
    cp.cuda.Stream.null.synchronize()
    started = time.perf_counter()
    for _ in range(args.benchmark_repeats):
        init_kernel((blocks,), (threads,), (raw_states, device_decks, np.int32(args.env_count)))
        setup_kernel(
            (blocks,),
            (threads,),
            (raw_states, raw_runtimes, np.uint64(args.seed), np.uint64(args.stream_base), np.int32(args.env_count)),
        )
    cp.cuda.Stream.null.synchronize()
    elapsed = time.perf_counter() - started

    free_vram, total_vram = cp.cuda.runtime.memGetInfo()
    device_name = cp.cuda.runtime.getDeviceProperties(0)["name"]
    if isinstance(device_name, bytes):
        device_name = device_name.decode()
    report = {
        "device": str(device_name),
        "env_count": args.env_count,
        "differential_envs": differential_envs,
        "state_bytes_per_env": state_size,
        "runtime_bytes_per_env": runtime_size,
        "host_cuda_runtime_layout_match": runtime_size == host_runtime_size,
        "differential_match": all_match,
        "runtime_errors_clear": runtime_errors_clear,
        "benchmark_repeats": args.benchmark_repeats,
        "benchmark_seconds": elapsed,
        "init_plus_setup_boundaries_per_second": args.env_count * args.benchmark_repeats / elapsed,
        "cupy_pool_bytes": int(cp.get_default_memory_pool().total_bytes()),
        "free_vram_bytes": int(free_vram),
        "total_vram_bytes": int(total_vram),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if all_match and runtime_errors_clear and runtime_size == host_runtime_size else 1


if __name__ == "__main__":
    raise SystemExit(main())
