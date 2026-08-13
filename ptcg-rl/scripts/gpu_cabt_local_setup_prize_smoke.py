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

_SNAPSHOT_SIZE = 70


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Official CPU vs CUDA SetupPrize differential")
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


def _shuffled_ref_decks(*, seed: int, stream: int) -> tuple[list[int], list[int]]:
    decks = [list(range(62, 2, -1)), list(range(122, 62, -1))]
    draw_index = shuffle_in_place(decks[0], seed=seed, stream=stream, draw_index=0)
    shuffle_in_place(decks[1], seed=seed, stream=stream, draw_index=draw_index)
    return decks[0], decks[1]


def _official_snapshots(
    repo_root: Path,
    deck0_ids: list[int],
    deck1_ids: list[int],
    rows: list[tuple[int, int, int, list[int], list[int]]],
    basics: tuple[int, int, int],
    filler_card_id: int,
) -> np.ndarray:
    official_dir = repo_root / "private/assets/official/ptcg_engine/ptcgProgram 22"
    ids0 = ",".join(str(value) for value in deck0_ids)
    ids1 = ",".join(str(value) for value in deck1_ids)
    source = f"""#include <iostream>\n#include "All.h"\nint main() {{\n InitializeAll(); GameConfig c={{}}; c.seed=1; c.recordLog=false; c.deviceRand=false;\n const int d0[60]={{{ids0}}}; const int d1[60]={{{ids1}}}; const int basics[3]={{{basics[0]},{basics[1]},{basics[2]}}};\n for(int i=0;i<60;++i){{c.decks[0].cards[i]=d0[i];c.decks[1].cards[i]=d1[i];}}\n int first_choice,target,active_choice;\n while(std::cin>>first_choice>>target>>active_choice) {{\n   BattleData b; b.init(c); State& s=b.state;\n   for(int p=0;p<2;++p) for(int i=0;i<60;++i) {{ int ref; std::cin>>ref; s.players[p].deck[i]=CardRef(ref); }}\n   s.changed=true; SetYesNoSelect(s, SelectContext::IsFirst, 0); SelectOption first=s.options.at(first_choice);\n   s.firstPlayer=first.type==SelectOptionType::Yes?s.selectPlayer:1-s.selectPlayer; s.clearSelect();\n   for(int p:s.basicPlayerOrder()) Draw(s,p,FIRST_HAND);\n   auto& hand=s.players[target].hand; for(int i=0;i<hand.size();++i) s.getCard(hand[i]).cardId=i<3?basics[i]:{filler_card_id};\n   PreSetupActivePokemon(s,target); SetupActivePokemon(s,target); s.selected.push_back(active_choice); s.callFunction();\n   SetupPrize(s,target);\n   auto emit=[](long long v){{std::cout<<v<<' ';}}; const auto& ps=s.players[target];\n   emit(target); emit((int)ps.deck.size()); emit((int)ps.hand.size()); emit((int)ps.active.size()); emit((int)ps.prize.size()); emit(0); emit(s.moveCounter); emit((int)s.changed); emit((int)s.setupDone[target]);\n   for(int i=0;i<6;++i) {{ CardRef ref=ps.prize[i]; const Card& card=s.getCard(ref); emit((int)ref.cardIndex); emit(card.cardId); emit(card.moveCounter); emit(card.attachMoveCounter); emit(card.skillOrder); emit(card.damage); emit((int)card.playerIndex); emit((int)card.area); emit((int)card.preArea); emit((int)card.reverse); }}\n   emit((int)s.firstPlayer); std::cout<<'\\n';\n }}\n}}\n"""
    lines: list[str] = []
    for first_choice, target, active_choice, refs0, refs1 in rows:
        lines.append(
            " ".join(str(value) for value in (first_choice, target, active_choice, *refs0, *refs1))
        )
    with tempfile.TemporaryDirectory(prefix="gpu-cabt-setup-prize-") as tmp:
        cpp = Path(tmp) / "probe.cpp"
        exe = Path(tmp) / "probe"
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
    filler = next(
        record.card_id
        for record in records
        if not record.is_basic_pokemon and not record.is_setup_doll and not record.can_setup_active
    )
    dense_bytes, row_count = dense_setup_card_table(records)
    dense = np.frombuffer(dense_bytes, dtype=np.uint8).reshape(row_count, 4)

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
        "src/ptcg_rl/gpu_cabt/cuda/selected_mulligan.cu",
        "src/ptcg_rl/gpu_cabt/cuda/setup_active.cu",
        "src/ptcg_rl/gpu_cabt/cuda/selected_setup_active.cu",
        "src/ptcg_rl/gpu_cabt/cuda/setup_prize.cu",
    )
    source = "\n".join((repo_root / path).read_text(encoding="utf-8") for path in source_paths)
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
        "gpu_cabt_setup_prize",
        "gpu_cabt_setup_prize_snapshot",
    )
    module = load_cupy_module(cp, source, kernel_names=names)
    state_out, runtime_out = cp.empty(1, dtype=cp.uint64), cp.empty(1, dtype=cp.uint64)
    module.get_function("gpu_cabt_battle_core_size")((1,), (1,), (state_out,))
    module.get_function("gpu_cabt_runtime_size")((1,), (1,), (runtime_out,))
    cp.cuda.Stream.null.synchronize()
    state_size, runtime_size = int(cp.asnumpy(state_out)[0]), int(cp.asnumpy(runtime_out)[0])

    first = np.arange(args.env_count, dtype=np.int32) & 1
    targets = (np.arange(args.env_count, dtype=np.int32) >> 1) & 1
    active_choices = np.arange(args.env_count, dtype=np.int32) % 3
    device_decks = cp.asarray(
        np.tile(np.asarray(deck0 + deck1, dtype=np.int32), (args.env_count, 1))
    )
    first_d, targets_d, choices_d, table_d = (
        cp.asarray(first),
        cp.asarray(targets),
        cp.asarray(active_choices),
        cp.asarray(dense),
    )
    states, runtimes = (
        cp.empty(args.env_count * state_size, dtype=cp.uint8),
        cp.empty(args.env_count * runtime_size, dtype=cp.uint8),
    )
    snapshots = cp.empty((args.env_count, _SNAPSHOT_SIZE), dtype=cp.int32)
    threads, blocks = 128, (args.env_count + 127) // 128
    module.get_function("gpu_cabt_init_battles")(
        (blocks,), (threads,), (states, device_decks, np.int32(args.env_count))
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
    module.get_function("gpu_cabt_force_basic_candidates")(
        (blocks,),
        (threads,),
        (
            states,
            targets_d,
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
        (states, runtimes, table_d, np.int32(row_count), targets_d, np.int32(args.env_count)),
    )
    module.get_function("gpu_cabt_setup_active")(
        (blocks,),
        (threads,),
        (states, runtimes, table_d, np.int32(row_count), targets_d, np.int32(args.env_count)),
    )
    module.get_function("gpu_cabt_selected_setup_active")(
        (blocks,), (threads,), (states, runtimes, targets_d, choices_d, np.int32(args.env_count))
    )
    module.get_function("gpu_cabt_setup_prize")(
        (blocks,), (threads,), (states, runtimes, targets_d, np.int32(args.env_count))
    )
    module.get_function("gpu_cabt_setup_prize_snapshot")(
        (blocks,), (threads,), (states, runtimes, targets_d, snapshots, np.int32(args.env_count))
    )
    cp.cuda.Stream.null.synchronize()
    actual = cp.asnumpy(snapshots)

    rows = []
    for i in range(args.env_count):
        r0, r1 = _shuffled_ref_decks(seed=args.seed, stream=args.stream_base + i)
        rows.append((int(first[i]), int(targets[i]), int(active_choices[i]), r0, r1))
    official = _official_snapshots(repo_root, deck0, deck1, rows, basics, filler)
    differential_match = bool(np.array_equal(actual, official))
    errors_clear = bool(np.all(actual[:, 5] == 0))
    prize_counts_valid = bool(np.all(actual[:, 4] == 6))
    prize_reverse_valid = bool(np.all(actual[:, 18::10][:, :6] == 1))

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
                "prize_counts_valid": prize_counts_valid,
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
        if differential_match and errors_clear and prize_counts_valid and prize_reverse_valid
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
