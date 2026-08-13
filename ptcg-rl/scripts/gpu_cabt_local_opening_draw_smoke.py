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
from ptcg_rl.gpu_cabt.rng import shuffle_in_place

_SNAPSHOT_SIZE = 249


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Official CPU vs CUDA opening-draw differential")
    parser.add_argument("--deck0", type=Path, required=True)
    parser.add_argument("--deck1", type=Path, required=True)
    parser.add_argument("--env-count", type=int, default=8192)
    parser.add_argument("--differential-envs", type=int, default=512)
    parser.add_argument("--benchmark-repeats", type=int, default=10)
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


def _initial_ref_decks() -> tuple[list[int], list[int]]:
    return list(range(62, 2, -1)), list(range(122, 62, -1))


def _shuffled_ref_decks(*, seed: int, stream: int) -> tuple[list[int], list[int]]:
    deck0, deck1 = _initial_ref_decks()
    draw_index = shuffle_in_place(deck0, seed=seed, stream=stream, draw_index=0)
    shuffle_in_place(deck1, seed=seed, stream=stream, draw_index=draw_index)
    return deck0, deck1


def _official_snapshots(
    repo_root: Path,
    deck0_ids: list[int],
    deck1_ids: list[int],
    rows: list[tuple[int, list[int], list[int]]],
) -> np.ndarray:
    official_dir = repo_root / "private/assets/official/ptcg_engine/ptcgProgram 22"
    ids0 = ",".join(str(value) for value in deck0_ids)
    ids1 = ",".join(str(value) for value in deck1_ids)
    source = f'''#include <iostream>\n#include "All.h"\nint main() {{\n InitializeAll(); GameConfig c={{}}; c.seed=1; c.recordLog=false; c.deviceRand=false;\n const int d0[60]={{{ids0}}}; const int d1[60]={{{ids1}}};\n for(int i=0;i<60;++i){{c.decks[0].cards[i]=d0[i];c.decks[1].cards[i]=d1[i];}}\n int selected;\n while(std::cin>>selected) {{\n   BattleData b; b.init(c); State& s=b.state;\n   for(int p=0;p<2;++p) for(int i=0;i<60;++i) {{ int ref; std::cin>>ref; s.players[p].deck[i]=CardRef(ref); }}\n   s.changed=true; SetYesNoSelect(s, SelectContext::IsFirst, 0);\n   SelectOption option=s.options.at(selected);\n   s.firstPlayer = option.type==SelectOptionType::Yes ? s.selectPlayer : 1-s.selectPlayer;\n   s.clearSelect();\n   for(int p:s.basicPlayerOrder()) Draw(s,p,FIRST_HAND);\n   auto emit=[](long long v){{std::cout<<v<<' ';}};\n   emit((int)s.firstPlayer); emit((int)s.changed); emit(s.moveCounter); emit((int)s.selectType);\n   emit((int)s.selectContext); emit((int)s.selectPlayer); emit(s.selectMin); emit(s.selectMax);\n   emit(0); emit(0); emit(1); emit(0); emit(2);\n   emit((int)s.players[0].deck.size()); emit((int)s.players[0].hand.size());\n   emit((int)s.players[1].deck.size()); emit((int)s.players[1].hand.size());\n   for(int p=0;p<2;++p) {{\n     for(int i=0;i<53;++i) emit((int)s.players[p].deck[i].cardIndex);\n     for(int i=0;i<7;++i) emit((int)s.players[p].hand[i].cardIndex);\n   }}\n   for(int p=0;p<2;++p) for(int i=0;i<7;++i) {{\n     CardRef ref=s.players[p].hand[i]; const Card& card=s.getCard(ref);\n     emit((int)ref.cardIndex); emit(card.cardId); emit(card.moveCounter); emit((int)card.playerIndex);\n     emit((int)card.area); emit((int)card.preArea); emit((int)card.reverse); emit(card.attachMoveCounter);\n   }}\n   std::cout<<'\\n';\n }}\n}}\n'''
    input_lines: list[str] = []
    for selected, deck0_refs, deck1_refs in rows:
        values = [selected, *deck0_refs, *deck1_refs]
        input_lines.append(" ".join(str(value) for value in values))
    input_text = "\n".join(input_lines) + "\n"

    with tempfile.TemporaryDirectory(prefix="gpu-cabt-opening-draw-") as tmp:
        cpp = Path(tmp) / "probe.cpp"
        exe = Path(tmp) / "probe"
        cpp.write_text(source, encoding="utf-8")
        subprocess.run(
            ["g++", "-std=c++23", "-O2", "-I", str(official_dir), str(cpp), "-o", str(exe)],
            check=True,
        )
        output = subprocess.check_output([str(exe)], input=input_text, text=True)
    values = [int(value) for value in output.split()]
    expected_count = len(rows) * _SNAPSHOT_SIZE
    if len(values) != expected_count:
        raise RuntimeError(f"official snapshot ints {len(values)} != {expected_count}")
    return np.asarray(values, dtype=np.int32).reshape(len(rows), _SNAPSHOT_SIZE)


def main() -> int:
    args = _parse_args()
    if args.env_count <= 0 or args.benchmark_repeats <= 0:
        raise ValueError("env-count and benchmark-repeats must be positive")
    if args.differential_envs <= 0 or args.differential_envs > args.env_count:
        raise ValueError("differential-envs must be in [1, env-count]")

    import cupy as cp

    repo_root = Path(__file__).resolve().parents[1]
    deck0 = _load_deck(args.deck0)
    deck1 = _load_deck(args.deck1)
    source_paths = (
        "src/ptcg_rl/gpu_cabt/native/state_core.h",
        "src/ptcg_rl/gpu_cabt/native/runtime_state.h",
        "src/ptcg_rl/gpu_cabt/cuda/rng_shuffle.cu",
        "src/ptcg_rl/gpu_cabt/cuda/battle_init.cu",
        "src/ptcg_rl/gpu_cabt/cuda/setup_is_first.cu",
        "src/ptcg_rl/gpu_cabt/cuda/card_move.cu",
        "src/ptcg_rl/gpu_cabt/cuda/opening_draw.cu",
    )
    source = "\n".join((repo_root / path).read_text(encoding="utf-8") for path in source_paths)
    module = load_cupy_module(
        cp,
        source,
        kernel_names=(
            "gpu_cabt_battle_core_size",
            "gpu_cabt_runtime_size",
            "gpu_cabt_init_battles",
            "gpu_cabt_setup_is_first",
            "gpu_cabt_opening_draw_after_is_first",
            "gpu_cabt_opening_draw_snapshot",
        ),
    )
    state_size_kernel = module.get_function("gpu_cabt_battle_core_size")
    runtime_size_kernel = module.get_function("gpu_cabt_runtime_size")
    init_kernel = module.get_function("gpu_cabt_init_battles")
    setup_kernel = module.get_function("gpu_cabt_setup_is_first")
    opening_kernel = module.get_function("gpu_cabt_opening_draw_after_is_first")
    snapshot_kernel = module.get_function("gpu_cabt_opening_draw_snapshot")

    state_size_out = cp.empty(1, dtype=cp.uint64)
    runtime_size_out = cp.empty(1, dtype=cp.uint64)
    state_size_kernel((1,), (1,), (state_size_out,))
    runtime_size_kernel((1,), (1,), (runtime_size_out,))
    cp.cuda.Stream.null.synchronize()
    state_size = int(cp.asnumpy(state_size_out)[0])
    runtime_size = int(cp.asnumpy(runtime_size_out)[0])

    pair = np.asarray(deck0 + deck1, dtype=np.int32)
    device_decks = cp.asarray(np.tile(pair, (args.env_count, 1)))
    selected_host = np.arange(args.env_count, dtype=np.int32) & 1
    selected_device = cp.asarray(selected_host)
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
    opening_kernel(
        (blocks,), (threads,), (raw_states, raw_runtimes, selected_device, np.int32(args.env_count))
    )
    snapshot_kernel((blocks,), (threads,), (raw_states, raw_runtimes, snapshots, np.int32(args.env_count)))
    cp.cuda.Stream.null.synchronize()
    gpu_snapshots = cp.asnumpy(snapshots)

    oracle_rows: list[tuple[int, list[int], list[int]]] = []
    for env_index in range(args.differential_envs):
        shuffled0, shuffled1 = _shuffled_ref_decks(
            seed=args.seed, stream=args.stream_base + env_index
        )
        oracle_rows.append((int(selected_host[env_index]), shuffled0, shuffled1))
    official = _official_snapshots(repo_root, deck0, deck1, oracle_rows)
    differential_match = bool(
        np.array_equal(gpu_snapshots[: args.differential_envs], official)
    )
    runtime_errors_clear = bool(np.all(gpu_snapshots[:, 11] == 0))
    zone_counts_valid = bool(
        np.all(gpu_snapshots[:, 13] == 53)
        and np.all(gpu_snapshots[:, 14] == 7)
        and np.all(gpu_snapshots[:, 15] == 53)
        and np.all(gpu_snapshots[:, 16] == 7)
    )

    init_kernel((blocks,), (threads,), (raw_states, device_decks, np.int32(args.env_count)))
    setup_kernel(
        (blocks,),
        (threads,),
        (raw_states, raw_runtimes, np.uint64(args.seed), np.uint64(args.stream_base), np.int32(args.env_count)),
    )
    opening_kernel(
        (blocks,), (threads,), (raw_states, raw_runtimes, selected_device, np.int32(args.env_count))
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
        opening_kernel(
            (blocks,), (threads,), (raw_states, raw_runtimes, selected_device, np.int32(args.env_count))
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
        "differential_envs": args.differential_envs,
        "differential_match": differential_match,
        "runtime_errors_clear": runtime_errors_clear,
        "zone_counts_valid": zone_counts_valid,
        "state_bytes_per_env": state_size,
        "runtime_bytes_per_env": runtime_size,
        "benchmark_repeats": args.benchmark_repeats,
        "benchmark_seconds": elapsed,
        "init_setup_opening_draws_per_second": args.env_count * args.benchmark_repeats / elapsed,
        "cupy_pool_bytes": int(cp.get_default_memory_pool().total_bytes()),
        "free_vram_bytes": int(free_vram),
        "total_vram_bytes": int(total_vram),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if differential_match and runtime_errors_clear and zone_counts_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
