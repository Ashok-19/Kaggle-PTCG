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

_SNAPSHOT_SIZE = 43
_SELECTED_STRIDE = 5


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Official CPU vs CUDA paired setup-Bench pre-TurnStart differential"
    )
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


def _official_snapshots(
    repo_root: Path,
    deck0_ids: list[int],
    deck1_ids: list[int],
    rows: list[tuple[int, int, list[int], list[int], list[int], list[int]]],
    basics: tuple[int, int, int],
    setup_card_id: int,
    filler_card_id: int,
) -> np.ndarray:
    official_dir = repo_root / "private/assets/official/ptcg_engine/ptcgProgram 22"
    ids0 = ",".join(str(value) for value in deck0_ids)
    ids1 = ",".join(str(value) for value in deck1_ids)
    source = f"""#include <iostream>\n#include "All.h"\nint main(){{\n InitializeAll();GameConfig c={{}};c.seed=1;c.recordLog=false;c.deviceRand=false;const int d0[60]={{{ids0}}};const int d1[60]={{{ids1}}};const int basics[3]={{{basics[0]},{basics[1]},{basics[2]}}};for(int i=0;i<60;++i){{c.decks[0].cards[i]=d0[i];c.decks[1].cards[i]=d1[i];}}\n int first,swapflag,firstcount,secondcount;while(std::cin>>first>>swapflag>>firstcount){{BattleData b;b.init(c);State&s=b.state;for(int p=0;p<2;++p)for(int i=0;i<60;++i){{int ref;std::cin>>ref;s.players[p].deck[i]=CardRef(ref);}}std::vector<int> firstsel(firstcount);for(int&i:firstsel)std::cin>>i;std::cin>>secondcount;std::vector<int> secondsel(secondcount);for(int&i:secondsel)std::cin>>i;s.firstPlayer=first;s.changed=true;for(int p:s.basicPlayerOrder())Draw(s,p,FIRST_HAND);int second=1-first;for(int p=0;p<2;++p){{auto&hand=s.players[p].hand;for(int i=0;i<hand.size();++i)s.getCard(hand[i]).cardId=i<3?basics[i]:{filler_card_id};}}for(int p:s.basicPlayerOrder()){{PreSetupActivePokemon(s,p);SetupActivePokemon(s,p);s.selected.push_back(0);s.callFunction();}}if(swapflag){{Card&a=s.getCard(s.players[first].getActive());Card&z=s.getCard(s.players[second].getActive());if(a.moveCounter<z.moveCounter)std::swap(a.moveCounter,z.moveCounter);}}for(int p=0;p<2;++p){{auto&hand=s.players[p].hand;for(CardRef ref:hand)s.getCard(ref).cardId={setup_card_id};}}SetupBenchPokemon(s,first);for(int x:firstsel)s.selected.push_back(x);s.setSelectedCardTarget();SetupBenchPokemon(s,second);for(int x:secondsel)s.selected.push_back(x);MoveToBenchSelected(s,first);s.setSelectedCardTarget();MoveToBenchSelected(s,second);s.setupDone={{}};for(int p:s.basicPlayerOrder()){{auto&ps=s.players[p];s.getCard(ps.active.at(0)).reverse=false;for(CardRef ref:ps.bench)s.getCard(ref).reverse=false;}}Card&c0=s.getCard(s.players[first].getActive());Card&c1=s.getCard(s.players[second].getActive());if(c0.moveCounter>c1.moveCounter)std::swap(c0.moveCounter,c1.moveCounter);auto emit=[](long long v){{std::cout<<v<<' ';}};emit((int)s.firstPlayer);emit((int)s.setupDone[0]);emit((int)s.setupDone[1]);emit(0);emit(1);emit(2);emit((int)s.targetList.size());emit(s.moveCounter);emit((int)s.selectType);for(int p=0;p<2;++p){{const auto&ps=s.players[p];emit((int)ps.hand.size());emit((int)ps.bench.size());emit((int)ps.active[0].cardIndex);const auto&a=s.getCard(ps.active[0]);emit((int)a.reverse);emit(a.moveCounter);for(int i=0;i<4;++i)emit(i<ps.bench.size()?(int)ps.bench[i].cardIndex:-1);for(int i=0;i<4;++i)emit(i<ps.bench.size()?(int)s.getCard(ps.bench[i]).reverse:-1);for(int i=0;i<4;++i)emit(i<ps.bench.size()?s.getCard(ps.bench[i]).moveCounter:-1);}}std::cout<<'\\n';}}}}\n"""
    lines: list[str] = []
    for first, swapflag, firstsel, secondsel, refs0, refs1 in rows:
        values = [
            first,
            swapflag,
            len(firstsel),
            *refs0,
            *refs1,
            *firstsel,
            len(secondsel),
            *secondsel,
        ]
        lines.append(" ".join(str(value) for value in values))
    with tempfile.TemporaryDirectory(prefix="gpu-cabt-bench-pair-") as tmp:
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
    basics = tuple(record.card_id for record in records if record.is_basic_pokemon)[:3]
    setup_card = next(record.card_id for record in records if record.can_setup)
    filler = next(
        record.card_id for record in records if not record.can_setup and not record.can_setup_active
    )
    dense_bytes, row_count = dense_setup_card_table(records)
    dense = np.frombuffer(dense_bytes, dtype=np.uint8).reshape(row_count, 4)

    first_patterns = ((), (0,), (4, 1, 5), (5, 0, 3, 1))
    second_patterns = ((2,), (5, 0, 3, 1), (), (4, 2))
    first_players = np.arange(args.env_count, dtype=np.int32) & 1
    second_players = 1 - first_players
    swap_flags = (np.arange(args.env_count, dtype=np.int32) >> 1) & 1
    first_counts = np.asarray(
        [len(first_patterns[i % 4]) for i in range(args.env_count)], dtype=np.int32
    )
    second_counts = np.asarray(
        [len(second_patterns[i % 4]) for i in range(args.env_count)], dtype=np.int32
    )
    first_matrix = np.zeros((args.env_count, _SELECTED_STRIDE), dtype=np.int32)
    second_matrix = np.zeros((args.env_count, _SELECTED_STRIDE), dtype=np.int32)
    for i in range(args.env_count):
        first_pattern, second_pattern = first_patterns[i % 4], second_patterns[i % 4]
        first_matrix[i, : len(first_pattern)] = first_pattern
        second_matrix[i, : len(second_pattern)] = second_pattern

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
        "src/ptcg_rl/gpu_cabt/cuda/selected_setup_active.cu",
        "src/ptcg_rl/gpu_cabt/cuda/setup_bench.cu",
        "src/ptcg_rl/gpu_cabt/cuda/selected_card_targets.cu",
        "src/ptcg_rl/gpu_cabt/cuda/move_selected_to_bench.cu",
        "src/ptcg_rl/gpu_cabt/cuda/selected_setup_bench_pair.cu",
    )
    source = "\n".join((repo_root / path).read_text(encoding="utf-8") for path in paths)
    names = (
        "gpu_cabt_battle_core_size",
        "gpu_cabt_runtime_size",
        "gpu_cabt_init_battles",
        "gpu_cabt_setup_is_first",
        "gpu_cabt_opening_draw_after_is_first",
        "gpu_cabt_force_basic_candidates",
        "gpu_cabt_pre_setup_active",
        "gpu_cabt_setup_active",
        "gpu_cabt_selected_setup_active",
        "gpu_cabt_force_setup_bench_case",
        "gpu_cabt_setup_bench",
        "gpu_cabt_selected_setup_bench_first",
        "gpu_cabt_selected_setup_bench_second_before_turn_start",
        "gpu_cabt_force_active_move_counter_swap_case",
        "gpu_cabt_setup_bench_pair_snapshot",
    )
    module = load_cupy_module(cp, source, kernel_names=names)
    state_out, runtime_out = cp.empty(1, dtype=cp.uint64), cp.empty(1, dtype=cp.uint64)
    module.get_function("gpu_cabt_battle_core_size")((1,), (1,), (state_out,))
    module.get_function("gpu_cabt_runtime_size")((1,), (1,), (runtime_out,))
    cp.cuda.Stream.null.synchronize()
    state_size, runtime_size = int(cp.asnumpy(state_out)[0]), int(cp.asnumpy(runtime_out)[0])

    decks_d = cp.asarray(np.tile(np.asarray(deck0 + deck1, dtype=np.int32), (args.env_count, 1)))
    first_d, second_d, table_d = (
        cp.asarray(first_players),
        cp.asarray(second_players),
        cp.asarray(dense),
    )
    zero_choices_d = cp.asarray(np.zeros(args.env_count, dtype=np.int32))
    swap_d = cp.asarray(swap_flags)
    first_counts_d, second_counts_d = cp.asarray(first_counts), cp.asarray(second_counts)
    first_matrix_d, second_matrix_d = cp.asarray(first_matrix), cp.asarray(second_matrix)
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
    for players_d in (first_d, second_d):
        module.get_function("gpu_cabt_force_basic_candidates")(
            (blocks,),
            (threads,),
            (
                states,
                players_d,
                np.int32(basics[0]),
                np.int32(basics[1]),
                np.int32(basics[2]),
                np.int32(filler),
                np.int32(0),
                np.int32(args.env_count),
            ),
        )
        module.get_function("gpu_cabt_pre_setup_active")(
            (blocks,),
            (threads,),
            (states, runtimes, table_d, np.int32(row_count), players_d, np.int32(args.env_count)),
        )
        module.get_function("gpu_cabt_setup_active")(
            (blocks,),
            (threads,),
            (states, runtimes, table_d, np.int32(row_count), players_d, np.int32(args.env_count)),
        )
        module.get_function("gpu_cabt_selected_setup_active")(
            (blocks,),
            (threads,),
            (states, runtimes, players_d, zero_choices_d, np.int32(args.env_count)),
        )
    module.get_function("gpu_cabt_force_active_move_counter_swap_case")(
        (blocks,), (threads,), (states, swap_d, np.int32(args.env_count))
    )
    for players_d in (first_d, second_d):
        module.get_function("gpu_cabt_force_setup_bench_case")(
            (blocks,),
            (threads,),
            (
                states,
                players_d,
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
        (states, runtimes, table_d, np.int32(row_count), first_d, np.int32(args.env_count)),
    )
    module.get_function("gpu_cabt_selected_setup_bench_first")(
        (blocks,),
        (threads,),
        (
            states,
            runtimes,
            first_d,
            first_counts_d,
            first_matrix_d,
            np.int32(_SELECTED_STRIDE),
            np.int32(args.env_count),
        ),
    )
    module.get_function("gpu_cabt_setup_bench")(
        (blocks,),
        (threads,),
        (states, runtimes, table_d, np.int32(row_count), second_d, np.int32(args.env_count)),
    )
    module.get_function("gpu_cabt_selected_setup_bench_second_before_turn_start")(
        (blocks,),
        (threads,),
        (
            states,
            runtimes,
            second_d,
            second_counts_d,
            second_matrix_d,
            np.int32(_SELECTED_STRIDE),
            np.int32(args.env_count),
        ),
    )
    module.get_function("gpu_cabt_setup_bench_pair_snapshot")(
        (blocks,), (threads,), (states, runtimes, snapshots, np.int32(args.env_count))
    )
    cp.cuda.Stream.null.synchronize()
    actual = cp.asnumpy(snapshots)

    rows: list[tuple[int, int, list[int], list[int], list[int], list[int]]] = []
    for i in range(args.env_count):
        refs0, refs1 = _shuffled_refs(seed=args.seed, stream=args.stream_base + i)
        rows.append(
            (
                int(first_players[i]),
                int(swap_flags[i]),
                list(first_patterns[i % 4]),
                list(second_patterns[i % 4]),
                refs0,
                refs1,
            )
        )
    official = _official_snapshots(repo_root, deck0, deck1, rows, basics, setup_card, filler)
    differential_match = bool(np.array_equal(actual, official))
    errors_clear = bool(np.all(actual[:, 3] == 0))
    continuation_valid = bool(np.all(actual[:, 4] == 1) and np.all(actual[:, 5] == 2))
    setup_done_reset = bool(np.all(actual[:, 1:3] == 0))
    select_cleared = bool(np.all(actual[:, 8] == 0))
    active_revealed = bool(np.all(actual[:, [12, 29]] == 0))
    target_count_valid = bool(np.array_equal(actual[:, 6], second_counts))
    normalized = True
    benches_revealed = True
    for i in range(args.env_count):
        first = int(first_players[i])
        first_move = int(actual[i, 13 if first == 0 else 30])
        second_move = int(actual[i, 30 if first == 0 else 13])
        if first_move > second_move:
            normalized = False
            break
        for player, bench_count_index, reverse_start in ((0, 10, 18), (1, 27, 35)):
            bench_count = int(actual[i, bench_count_index])
            if bench_count and not np.all(
                actual[i, reverse_start : reverse_start + bench_count] == 0
            ):
                benches_revealed = False
                break
        if not benches_revealed:
            break

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
                "continuation_boundary_valid": continuation_valid,
                "setup_done_reset": setup_done_reset,
                "selection_cleared": select_cleared,
                "active_revealed": active_revealed,
                "benches_revealed": benches_revealed,
                "active_move_counters_normalized": normalized,
                "second_target_count_valid": target_count_valid,
                "forced_swap_cases": int(np.sum(swap_flags)),
                "state_bytes_per_env": state_size,
                "runtime_bytes_per_env": runtime_size,
                "free_vram_bytes": int(free_vram),
                "total_vram_bytes": int(total_vram),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return (
        0
        if all(
            (
                differential_match,
                errors_clear,
                continuation_valid,
                setup_done_reset,
                select_cleared,
                active_revealed,
                benches_revealed,
                normalized,
                target_count_valid,
            )
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
