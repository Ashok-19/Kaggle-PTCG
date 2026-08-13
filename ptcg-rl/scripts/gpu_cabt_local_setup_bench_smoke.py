from __future__ import annotations

import argparse
import csv
import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from ptcg_rl.gpu_cabt.card_static import dense_setup_card_table, extract_setup_card_static
from ptcg_rl.gpu_cabt.nvrtc import load_cupy_module

_SNAPSHOT_SIZE = 68


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Official CPU vs CUDA SetupBenchPokemon differential"
    )
    parser.add_argument("--deck0", type=Path, required=True)
    parser.add_argument("--deck1", type=Path, required=True)
    parser.add_argument("--env-count", type=int, default=600)
    return parser.parse_args()


def _load_deck(path: Path) -> list[int]:
    values: list[int] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.reader(handle):
            values.extend(int(value) for value in row if value.strip())
    if len(values) != 60:
        raise ValueError(f"{path} must contain exactly 60 card IDs")
    return values


def _official_snapshots(
    repo_root: Path,
    deck0_ids: list[int],
    deck1_ids: list[int],
    rows: list[tuple[int, int, int, int, int]],
    setup_card_id: int,
    filler_card_id: int,
) -> np.ndarray:
    official_dir = repo_root / "private/assets/official/ptcg_engine/ptcgProgram 22"
    ids0 = ",".join(str(value) for value in deck0_ids)
    ids1 = ",".join(str(value) for value in deck1_ids)
    source = f"""#include <iostream>\n#include "All.h"\nint main() {{\n InitializeAll(); GameConfig c={{}}; c.seed=1; c.recordLog=false; c.deviceRand=false;\n const int d0[60]={{{ids0}}}; const int d1[60]={{{ids1}}};\n for(int i=0;i<60;++i){{c.decks[0].cards[i]=d0[i];c.decks[1].cards[i]=d1[i];}}\n int first_player,target,eligible,cap_override,bench_count;\n while(std::cin>>first_player>>target>>eligible>>cap_override>>bench_count) {{\n   BattleData b; b.init(c); State& s=b.state; s.firstPlayer=first_player; s.changed=true;\n   for(int p:s.basicPlayerOrder()) Draw(s,p,FIRST_HAND);\n   auto& ps=s.players[target];\n   for(int i=0;i<ps.hand.size();++i) s.getCard(ps.hand[i]).cardId=i<eligible?{setup_card_id}:{filler_card_id};\n   ps.benchCapacity=cap_override; ps.bench.resize(bench_count);\n   SetupBenchPokemon(s,target);\n   auto emit=[](long long v){{std::cout<<v<<' ';}};\n   emit(target); emit((int)ps.hand.size()); emit((int)ps.bench.size()); emit(s.benchCapacity(target)); emit((int)s.selectType); emit((int)s.selectContext); emit((int)s.selectPlayer); emit(s.selectMin); emit(s.selectMax); emit((int)s.options.size());\n   emit(2); emit(7); emit(target); emit(0);\n   for(int i=0;i<8;++i) {{ if(i<(int)s.options.size()) {{ const auto&o=s.options[i]; emit((int)o.type); emit(o.param0); emit(o.param1); emit(o.param2); emit(o.param3); emit(o.param4); }} else for(int f=0;f<6;++f) emit(-1); }}\n   emit((int)s.firstPlayer); emit(s.moveCounter); emit((int)s.changed); emit((int)s.setupDone[target]); emit((int)ps.active.size()); emit((int)ps.benchCapacity); std::cout<<'\\n';\n }}\n}}\n"""
    input_text = "\n".join(" ".join(str(v) for v in row) for row in rows) + "\n"
    with tempfile.TemporaryDirectory(prefix="gpu-cabt-setup-bench-") as tmp:
        cpp, exe = Path(tmp) / "probe.cpp", Path(tmp) / "probe"
        cpp.write_text(source, encoding="utf-8")
        subprocess.run(
            ["g++", "-std=c++23", "-O2", "-I", str(official_dir), str(cpp), "-o", str(exe)],
            check=True,
        )
        output = subprocess.check_output([str(exe)], input=input_text, text=True)
    values = [int(value) for value in output.split()]
    expected = len(rows) * _SNAPSHOT_SIZE
    if len(values) != expected:
        raise RuntimeError(f"official snapshot ints {len(values)} != {expected}")
    return np.asarray(values, dtype=np.int32).reshape(len(rows), _SNAPSHOT_SIZE)


def main() -> int:
    args = _parse_args()
    if args.env_count <= 0:
        raise ValueError("env-count must be positive")

    import cupy as cp

    repo_root = Path(__file__).resolve().parents[1]
    deck0, deck1 = _load_deck(args.deck0), _load_deck(args.deck1)
    records = extract_setup_card_static(
        repo_root / "private/assets/official/ptcg_engine/ptcgProgram 22"
    )
    setup_card = next(record.card_id for record in records if record.can_setup)
    filler = next(
        record.card_id for record in records if not record.can_setup and not record.can_setup_active
    )
    dense_bytes, row_count = dense_setup_card_table(records)
    dense = np.frombuffer(dense_bytes, dtype=np.uint8).reshape(row_count, 4)

    modes = (
        (0, 0, 0),
        (2, 0, 0),
        (6, 0, 0),
        (6, 3, 0),
        (6, 8, 0),
        (6, 3, 2),
    )
    eligible = np.asarray([modes[i % len(modes)][0] for i in range(args.env_count)], dtype=np.int32)
    capacity_overrides = np.asarray(
        [modes[i % len(modes)][1] for i in range(args.env_count)], dtype=np.int32
    )
    bench_counts = np.asarray(
        [modes[i % len(modes)][2] for i in range(args.env_count)], dtype=np.int32
    )
    first_players = np.arange(args.env_count, dtype=np.int32) & 1
    targets = (np.arange(args.env_count, dtype=np.int32) >> 1) & 1

    source_paths = (
        "src/ptcg_rl/gpu_cabt/native/state_core.h",
        "src/ptcg_rl/gpu_cabt/native/runtime_state.h",
        "src/ptcg_rl/gpu_cabt/native/card_static.h",
        "src/ptcg_rl/gpu_cabt/cuda/rng_shuffle.cu",
        "src/ptcg_rl/gpu_cabt/cuda/battle_init.cu",
        "src/ptcg_rl/gpu_cabt/cuda/setup_is_first.cu",
        "src/ptcg_rl/gpu_cabt/cuda/card_move.cu",
        "src/ptcg_rl/gpu_cabt/cuda/opening_draw.cu",
        "src/ptcg_rl/gpu_cabt/cuda/pre_setup_active.cu",
        "src/ptcg_rl/gpu_cabt/cuda/setup_active.cu",
        "src/ptcg_rl/gpu_cabt/cuda/setup_bench.cu",
    )
    source = "\n".join((repo_root / path).read_text(encoding="utf-8") for path in source_paths)
    names = (
        "gpu_cabt_battle_core_size",
        "gpu_cabt_runtime_size",
        "gpu_cabt_init_battles",
        "gpu_cabt_setup_is_first",
        "gpu_cabt_opening_draw_after_is_first",
        "gpu_cabt_force_setup_bench_case",
        "gpu_cabt_setup_bench",
        "gpu_cabt_setup_bench_snapshot",
    )
    module = load_cupy_module(cp, source, kernel_names=names)
    state_out, runtime_out = cp.empty(1, dtype=cp.uint64), cp.empty(1, dtype=cp.uint64)
    module.get_function("gpu_cabt_battle_core_size")((1,), (1,), (state_out,))
    module.get_function("gpu_cabt_runtime_size")((1,), (1,), (runtime_out,))
    cp.cuda.Stream.null.synchronize()
    state_size, runtime_size = int(cp.asnumpy(state_out)[0]), int(cp.asnumpy(runtime_out)[0])

    decks_d = cp.asarray(np.tile(np.asarray(deck0 + deck1, dtype=np.int32), (args.env_count, 1)))
    first_d, targets_d = cp.asarray(first_players), cp.asarray(targets)
    eligible_d, caps_d, bench_d = (
        cp.asarray(eligible),
        cp.asarray(capacity_overrides),
        cp.asarray(bench_counts),
    )
    table_d = cp.asarray(dense)
    states = cp.empty(args.env_count * state_size, dtype=cp.uint8)
    runtimes = cp.empty(args.env_count * runtime_size, dtype=cp.uint8)
    snapshots = cp.empty((args.env_count, _SNAPSHOT_SIZE), dtype=cp.int32)
    threads, blocks = 128, (args.env_count + 127) // 128

    module.get_function("gpu_cabt_init_battles")(
        (blocks,), (threads,), (states, decks_d, np.int32(args.env_count))
    )
    module.get_function("gpu_cabt_setup_is_first")(
        (blocks,),
        (threads,),
        (states, runtimes, np.uint64(123456789), np.uint64(987654321), np.int32(args.env_count)),
    )
    # Opening-draw kernel only needs first_player state; selected index 0/1 maps to first_player 0/1.
    module.get_function("gpu_cabt_opening_draw_after_is_first")(
        (blocks,), (threads,), (states, runtimes, first_d, np.int32(args.env_count))
    )
    module.get_function("gpu_cabt_force_setup_bench_case")(
        (blocks,),
        (threads,),
        (
            states,
            targets_d,
            np.int32(setup_card),
            np.int32(filler),
            eligible_d,
            caps_d,
            bench_d,
            np.int32(args.env_count),
        ),
    )
    module.get_function("gpu_cabt_setup_bench")(
        (blocks,),
        (threads,),
        (states, runtimes, table_d, np.int32(row_count), targets_d, np.int32(args.env_count)),
    )
    module.get_function("gpu_cabt_setup_bench_snapshot")(
        (blocks,), (threads,), (states, runtimes, targets_d, snapshots, np.int32(args.env_count))
    )
    cp.cuda.Stream.null.synchronize()
    actual = cp.asnumpy(snapshots)

    rows = [
        (
            int(first_players[i]),
            int(targets[i]),
            int(eligible[i]),
            int(capacity_overrides[i]),
            int(bench_counts[i]),
        )
        for i in range(args.env_count)
    ]
    official = _official_snapshots(repo_root, deck0, deck1, rows, setup_card, filler)
    differential_match = bool(np.array_equal(actual, official))
    errors_clear = bool(np.all(actual[:, 13] == 0))
    observed_max_by_mode = {
        str(mode): sorted(set(actual[np.arange(args.env_count) % len(modes) == mode, 8].tolist()))
        for mode in range(len(modes))
    }
    expected_max = {"0": [0], "1": [2], "2": [5], "3": [3], "4": [6], "5": [1]}
    clipping_valid = observed_max_by_mode == expected_max

    free_vram, total_vram = cp.cuda.runtime.memGetInfo()
    name = cp.cuda.runtime.getDeviceProperties(0)["name"]
    name = name.decode() if isinstance(name, bytes) else str(name)
    print(
        json.dumps(
            {
                "device": name,
                "env_count": args.env_count,
                "differential_match": differential_match,
                "runtime_errors_clear": errors_clear,
                "select_max_by_mode": observed_max_by_mode,
                "capacity_clipping_valid": clipping_valid,
                "setup_card_id": setup_card,
                "filler_card_id": filler,
                "state_bytes_per_env": state_size,
                "runtime_bytes_per_env": runtime_size,
                "free_vram_bytes": int(free_vram),
                "total_vram_bytes": int(total_vram),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if differential_match and errors_clear and clipping_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
