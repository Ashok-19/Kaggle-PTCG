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
from ptcg_rl.gpu_cabt.rng import shuffle_in_place

_SNAPSHOT_SIZE = 48
_SELECTED_STRIDE = 5


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Official CPU vs CUDA selected AreaRef capture")
    parser.add_argument("--deck0", type=Path, required=True)
    parser.add_argument("--deck1", type=Path, required=True)
    parser.add_argument("--env-count", type=int, default=256)
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


def _shuffled_refs(*, seed: int, stream: int) -> tuple[list[int], list[int]]:
    refs0, refs1 = list(range(62, 2, -1)), list(range(122, 62, -1))
    cursor = shuffle_in_place(refs0, seed=seed, stream=stream, draw_index=0)
    shuffle_in_place(refs1, seed=seed, stream=stream, draw_index=cursor)
    return refs0, refs1


def _host_runtime_size(repo_root: Path) -> int:
    include_dir = repo_root / "src/ptcg_rl/gpu_cabt/native"
    source = '#include <iostream>\n#include "state_core.h"\n#include "runtime_state.h"\nint main(){std::cout<<sizeof(gpu_cabt::BattleRuntimeState)<<"\\n";}\n'
    with tempfile.TemporaryDirectory(prefix="gpu-cabt-target-runtime-size-") as tmp:
        cpp, exe = Path(tmp) / "probe.cpp", Path(tmp) / "probe"
        cpp.write_text(source, encoding="utf-8")
        subprocess.run(
            ["g++", "-std=c++17", "-O2", "-I", str(include_dir), str(cpp), "-o", str(exe)],
            check=True,
        )
        return int(subprocess.check_output([str(exe)], text=True).strip())


def _official_snapshots(
    repo_root: Path,
    deck0_ids: list[int],
    deck1_ids: list[int],
    rows: list[tuple[int, int, list[int], list[int], list[int]]],
    setup_card_id: int,
    filler_card_id: int,
) -> np.ndarray:
    official_dir = repo_root / "private/assets/official/ptcg_engine/ptcgProgram 22"
    ids0 = ",".join(str(value) for value in deck0_ids)
    ids1 = ",".join(str(value) for value in deck1_ids)
    source = f"""#include <iostream>\n#include "All.h"\nint main(){{\n InitializeAll();GameConfig c={{}};c.seed=1;c.recordLog=false;c.deviceRand=false;const int d0[60]={{{ids0}}};const int d1[60]={{{ids1}}};for(int i=0;i<60;++i){{c.decks[0].cards[i]=d0[i];c.decks[1].cards[i]=d1[i];}}\n int first_player,target,count;while(std::cin>>first_player>>target>>count){{BattleData b;b.init(c);State&s=b.state;for(int p=0;p<2;++p)for(int i=0;i<60;++i){{int ref;std::cin>>ref;s.players[p].deck[i]=CardRef(ref);}}s.firstPlayer=first_player;s.changed=true;for(int p:s.basicPlayerOrder())Draw(s,p,FIRST_HAND);auto&ps=s.players[target];for(int i=0;i<ps.hand.size();++i)s.getCard(ps.hand[i]).cardId=i<6?{setup_card_id}:{filler_card_id};SetupBenchPokemon(s,target);for(int i=0;i<count;++i){{int x;std::cin>>x;s.selected.push_back(x);}}s.setSelectedCardTarget();auto emit=[](long long v){{std::cout<<v<<' ';}};emit((int)s.targetList.size());emit((int)s.options.size());emit((int)s.selected.size());emit((int)s.selectType);emit((int)s.selectContext);emit((int)s.selectPlayer);emit(s.selectMin);emit(s.selectMax);emit((int)s.contextCard.cardIndex);emit((int)s.selectDeck);emit(2);emit(7);emit(0);for(int i=0;i<8;++i){{if(i<(int)s.targetList.size()){{const auto&t=s.targetList[i];const auto&card=s.getCard(t.card);emit((int)t.card.cardIndex);emit(t.moveCounter);emit(card.cardId);emit((int)card.area);}}else for(int f=0;f<4;++f)emit(-1);}}emit(s.moveCounter);emit((int)s.changed);emit((int)s.firstPlayer);std::cout<<'\\n';}}}}\n"""
    lines: list[str] = []
    for first_player, target, selected, refs0, refs1 in rows:
        values = [first_player, target, len(selected), *refs0, *refs1, *selected]
        lines.append(" ".join(str(value) for value in values))
    with tempfile.TemporaryDirectory(prefix="gpu-cabt-selected-targets-") as tmp:
        cpp, exe = Path(tmp) / "probe.cpp", Path(tmp) / "probe"
        cpp.write_text(source, encoding="utf-8")
        subprocess.run(
            ["g++", "-std=c++23", "-O2", "-I", str(official_dir), str(cpp), "-o", str(exe)],
            check=True,
        )
        output = subprocess.check_output([str(exe)], input="\n".join(lines) + "\n", text=True)
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

    patterns = ((), (0,), (4, 1, 5), (5, 0, 3, 1))
    first_players = np.arange(args.env_count, dtype=np.int32) & 1
    targets = (np.arange(args.env_count, dtype=np.int32) >> 1) & 1
    selected_counts = np.asarray(
        [len(patterns[i % len(patterns)]) for i in range(args.env_count)], dtype=np.int32
    )
    selected_matrix = np.zeros((args.env_count, _SELECTED_STRIDE), dtype=np.int32)
    for env_index in range(args.env_count):
        pattern = patterns[env_index % len(patterns)]
        selected_matrix[env_index, : len(pattern)] = pattern

    paths = (
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
        "src/ptcg_rl/gpu_cabt/cuda/selected_card_targets.cu",
    )
    source = "\n".join((repo_root / path).read_text(encoding="utf-8") for path in paths)
    names = (
        "gpu_cabt_battle_core_size",
        "gpu_cabt_runtime_size",
        "gpu_cabt_init_battles",
        "gpu_cabt_setup_is_first",
        "gpu_cabt_opening_draw_after_is_first",
        "gpu_cabt_force_setup_bench_case",
        "gpu_cabt_setup_bench",
        "gpu_cabt_capture_selected_card_targets",
        "gpu_cabt_selected_card_targets_snapshot",
    )
    module = load_cupy_module(cp, source, kernel_names=names)
    state_out, runtime_out = cp.empty(1, dtype=cp.uint64), cp.empty(1, dtype=cp.uint64)
    module.get_function("gpu_cabt_battle_core_size")((1,), (1,), (state_out,))
    module.get_function("gpu_cabt_runtime_size")((1,), (1,), (runtime_out,))
    cp.cuda.Stream.null.synchronize()
    state_size, runtime_size = int(cp.asnumpy(state_out)[0]), int(cp.asnumpy(runtime_out)[0])
    host_runtime_size = _host_runtime_size(repo_root)

    decks_d = cp.asarray(np.tile(np.asarray(deck0 + deck1, dtype=np.int32), (args.env_count, 1)))
    first_d, targets_d, table_d = cp.asarray(first_players), cp.asarray(targets), cp.asarray(dense)
    selected_counts_d, selected_matrix_d = cp.asarray(selected_counts), cp.asarray(selected_matrix)
    eligible_d = cp.asarray(np.full(args.env_count, 6, dtype=np.int32))
    caps_d = cp.asarray(np.zeros(args.env_count, dtype=np.int32))
    bench_d = cp.asarray(np.zeros(args.env_count, dtype=np.int32))
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
        (
            states,
            runtimes,
            np.uint64(args.seed),
            np.uint64(args.stream_base),
            np.int32(args.env_count),
        ),
    )
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
    module.get_function("gpu_cabt_capture_selected_card_targets")(
        (blocks,),
        (threads,),
        (
            states,
            runtimes,
            selected_counts_d,
            selected_matrix_d,
            np.int32(_SELECTED_STRIDE),
            np.int32(args.env_count),
        ),
    )
    module.get_function("gpu_cabt_selected_card_targets_snapshot")(
        (blocks,), (threads,), (states, runtimes, snapshots, np.int32(args.env_count))
    )
    cp.cuda.Stream.null.synchronize()
    actual = cp.asnumpy(snapshots)

    rows: list[tuple[int, int, list[int], list[int], list[int]]] = []
    for env_index in range(args.env_count):
        refs0, refs1 = _shuffled_refs(seed=args.seed, stream=args.stream_base + env_index)
        rows.append(
            (
                int(first_players[env_index]),
                int(targets[env_index]),
                list(patterns[env_index % len(patterns)]),
                refs0,
                refs1,
            )
        )
    official = _official_snapshots(repo_root, deck0, deck1, rows, setup_card, filler)
    differential_match = bool(np.array_equal(actual, official))
    errors_clear = bool(np.all(actual[:, 12] == 0))
    runtime_layout_match = runtime_size == host_runtime_size
    target_counts_by_pattern = {
        str(pattern): sorted(
            set(actual[np.arange(args.env_count) % len(patterns) == index, 0].tolist())
        )
        for index, pattern in enumerate(patterns)
    }
    target_counts_valid = all(
        target_counts_by_pattern[str(pattern)] == [len(pattern)] for pattern in patterns
    )

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
                "host_cuda_runtime_layout_match": runtime_layout_match,
                "runtime_bytes_per_env": runtime_size,
                "target_counts_by_pattern": target_counts_by_pattern,
                "target_counts_valid": target_counts_valid,
                "state_bytes_per_env": state_size,
                "free_vram_bytes": int(free_vram),
                "total_vram_bytes": int(total_vram),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return (
        0
        if differential_match and errors_clear and runtime_layout_match and target_counts_valid
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
