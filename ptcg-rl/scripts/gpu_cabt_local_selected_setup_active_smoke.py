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

_SNAPSHOT_SIZE = 47
_DOLL_CARD_ID = 666
_MODE_BASIC = 0
_MODE_DOLL = 1


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Official CPU vs CUDA SelectedSetupActivePokemon differential")
    parser.add_argument("--deck0", type=Path, required=True)
    parser.add_argument("--deck1", type=Path, required=True)
    parser.add_argument("--env-count", type=int, default=512)
    parser.add_argument("--doll-cases", type=int, default=64)
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
    rows: list[tuple[int, int, int, int, list[int], list[int]]],
    basics: tuple[int, int, int],
    filler_card_id: int,
) -> np.ndarray:
    official_dir = repo_root / "private/assets/official/ptcg_engine/ptcgProgram 22"
    ids0 = ",".join(str(value) for value in deck0_ids)
    ids1 = ",".join(str(value) for value in deck1_ids)
    source = f'''#include <iostream>\n#include "All.h"\nint main() {{\n InitializeAll(); GameConfig c={{}}; c.seed=1; c.recordLog=false; c.deviceRand=false;\n const int d0[60]={{{ids0}}}; const int d1[60]={{{ids1}}};\n const int basics[3]={{{basics[0]},{basics[1]},{basics[2]}}};\n for(int i=0;i<60;++i){{c.decks[0].cards[i]=d0[i];c.decks[1].cards[i]=d1[i];}}\n int first_choice,target,mode,active_choice;\n while(std::cin>>first_choice>>target>>mode>>active_choice) {{\n   BattleData b; b.init(c); State& s=b.state;\n   for(int p=0;p<2;++p) for(int i=0;i<60;++i) {{ int ref; std::cin>>ref; s.players[p].deck[i]=CardRef(ref); }}\n   s.changed=true; SetYesNoSelect(s, SelectContext::IsFirst, 0);\n   SelectOption first=s.options.at(first_choice);\n   s.firstPlayer = first.type==SelectOptionType::Yes ? s.selectPlayer : 1-s.selectPlayer;\n   s.clearSelect();\n   for(int p:s.basicPlayerOrder()) Draw(s,p,FIRST_HAND);\n   auto& hand=s.players[target].hand;\n   if(mode=={_MODE_DOLL}) {{\n     for(int i=0;i<hand.size();++i) s.getCard(hand[i]).cardId=i==0?{_DOLL_CARD_ID}:{filler_card_id};\n   }} else {{\n     for(int i=0;i<hand.size();++i) s.getCard(hand[i]).cardId=i<3?basics[i]:{filler_card_id};\n   }}\n   PreSetupActivePokemon(s,target);\n   if(mode=={_MODE_DOLL}) {{ s.selected.push_back(1); s.callFunction(); }}\n   SetupActivePokemon(s,target);\n   s.selected.push_back(active_choice); s.callFunction();\n   auto emit=[](long long v){{std::cout<<v<<' ';}};\n   const auto& ps=s.players[target]; CardRef active=ps.active.at(0); const Card& card=s.getCard(active);\n   emit(target); emit((int)s.setupDone[0]); emit((int)s.setupDone[1]); emit((int)s.mulligan[0]); emit((int)s.mulligan[1]);\n   emit((int)s.selectType); emit((int)s.selectContext); emit((int)s.selectPlayer); emit(s.selectMin); emit(s.selectMax);\n   emit((int)s.options.size()); emit((int)s.selected.size()); emit(1); emit(2); emit(0);\n   emit((int)ps.hand.size()); emit((int)ps.active.size()); emit((int)active.cardIndex);\n   for(int i=0;i<6;++i) emit(i<ps.hand.size()?(int)ps.hand[i].cardIndex:-1);\n   emit(card.cardId); emit(card.moveCounter); emit(card.attachMoveCounter); emit(card.skillOrder); emit(card.damage);\n   emit((int)card.playerIndex); emit((int)card.area); emit((int)card.preArea); emit((int)card.reverse); emit((int)card.abilityUsed.size());\n   emit(card.nextEnemyTurnEndStateBattleField); emit(card.nextEnemyTurnEndState); emit(card.turnState[0]); emit(card.turnState[1]); emit(card.turnState[2]);\n   emit((long long)card.continualState[0]); emit((long long)card.continualState[1]); emit((long long)card.continualState[2]); emit((long long)card.continualState[3]); emit((long long)card.continualState[4]);\n   emit((int)s.firstPlayer); emit(s.moveCounter); emit((int)s.changed); std::cout<<'\\n';\n }}\n}}\n'''
    lines: list[str] = []
    for first_choice, target, mode, active_choice, refs0, refs1 in rows:
        values = [first_choice, target, mode, active_choice, *refs0, *refs1]
        lines.append(" ".join(str(value) for value in values))
    with tempfile.TemporaryDirectory(prefix="gpu-cabt-selected-setup-active-") as tmp:
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
    return np.asarray(values, dtype=np.int64).reshape(len(rows), _SNAPSHOT_SIZE)


def main() -> int:
    args = _parse_args()
    if not 0 < args.doll_cases < args.env_count:
        raise ValueError("doll-cases must be in (0, env-count)")

    import cupy as cp

    repo_root = Path(__file__).resolve().parents[1]
    deck0 = _load_deck(args.deck0)
    deck1 = _load_deck(args.deck1)
    records = extract_setup_card_static(repo_root / "private/assets/official/ptcg_engine/ptcgProgram 22")
    basics = tuple(record.card_id for record in records if record.is_basic_pokemon)[:3]
    if len(basics) != 3:
        raise RuntimeError("need three Basic Pokémon qualification anchors")
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
            "gpu_cabt_force_setup_doll_hand",
            "gpu_cabt_force_basic_candidates",
            "gpu_cabt_pre_setup_active",
            "gpu_cabt_selected_mulligan",
            "gpu_cabt_setup_active",
            "gpu_cabt_selected_setup_active",
            "gpu_cabt_selected_setup_active_snapshot",
        ),
    )
    state_size_out = cp.empty(1, dtype=cp.uint64)
    runtime_size_out = cp.empty(1, dtype=cp.uint64)
    module.get_function("gpu_cabt_battle_core_size")((1,), (1,), (state_size_out,))
    module.get_function("gpu_cabt_runtime_size")((1,), (1,), (runtime_size_out,))
    cp.cuda.Stream.null.synchronize()
    state_size = int(cp.asnumpy(state_size_out)[0])
    runtime_size = int(cp.asnumpy(runtime_size_out)[0])

    first_choices = np.arange(args.env_count, dtype=np.int32) & 1
    target_players = (np.arange(args.env_count, dtype=np.int32) >> 1) & 1
    modes = np.full(args.env_count, _MODE_BASIC, dtype=np.int32)
    modes[: args.doll_cases] = _MODE_DOLL
    active_choices = np.zeros(args.env_count, dtype=np.int32)
    active_choices[args.doll_cases :] = np.arange(args.env_count - args.doll_cases, dtype=np.int32) % 3

    device_decks = cp.asarray(np.tile(np.asarray(deck0 + deck1, dtype=np.int32), (args.env_count, 1)))
    first_device = cp.asarray(first_choices)
    targets_device = cp.asarray(target_players)
    active_choices_device = cp.asarray(active_choices)
    card_table_device = cp.asarray(dense)
    raw_states = cp.empty(args.env_count * state_size, dtype=cp.uint8)
    raw_runtimes = cp.empty(args.env_count * runtime_size, dtype=cp.uint8)
    snapshots = cp.empty((args.env_count, _SNAPSHOT_SIZE), dtype=cp.int32)
    threads = 128
    blocks = (args.env_count + threads - 1) // threads

    module.get_function("gpu_cabt_init_battles")(
        (blocks,), (threads,), (raw_states, device_decks, np.int32(args.env_count))
    )
    module.get_function("gpu_cabt_setup_is_first")(
        (blocks,), (threads,),
        (raw_states, raw_runtimes, np.uint64(args.seed), np.uint64(args.stream_base), np.int32(args.env_count)),
    )
    module.get_function("gpu_cabt_opening_draw_after_is_first")(
        (blocks,), (threads,), (raw_states, raw_runtimes, first_device, np.int32(args.env_count))
    )
    doll_blocks = (args.doll_cases + threads - 1) // threads
    module.get_function("gpu_cabt_force_setup_doll_hand")(
        (doll_blocks,), (threads,),
        (raw_states, targets_device, np.int32(_DOLL_CARD_ID), np.int32(filler), np.int32(args.doll_cases)),
    )
    basic_count = args.env_count - args.doll_cases
    basic_blocks = (basic_count + threads - 1) // threads
    module.get_function("gpu_cabt_force_basic_candidates")(
        (basic_blocks,), (threads,),
        (
            raw_states,
            targets_device,
            np.int32(basics[0]),
            np.int32(basics[1]),
            np.int32(basics[2]),
            np.int32(filler),
            np.int32(args.doll_cases),
            np.int32(basic_count),
        ),
    )
    module.get_function("gpu_cabt_pre_setup_active")(
        (blocks,), (threads,),
        (raw_states, raw_runtimes, card_table_device, np.int32(row_count), targets_device, np.int32(args.env_count)),
    )
    doll_no_choices = cp.asarray(np.ones(args.doll_cases, dtype=np.int32))
    module.get_function("gpu_cabt_selected_mulligan")(
        (doll_blocks,), (threads,),
        (raw_states, raw_runtimes, targets_device, doll_no_choices, np.int32(args.doll_cases)),
    )
    module.get_function("gpu_cabt_setup_active")(
        (blocks,), (threads,),
        (raw_states, raw_runtimes, card_table_device, np.int32(row_count), targets_device, np.int32(args.env_count)),
    )
    module.get_function("gpu_cabt_selected_setup_active")(
        (blocks,), (threads,),
        (raw_states, raw_runtimes, targets_device, active_choices_device, np.int32(args.env_count)),
    )
    module.get_function("gpu_cabt_selected_setup_active_snapshot")(
        (blocks,), (threads,),
        (raw_states, raw_runtimes, targets_device, snapshots, np.int32(args.env_count)),
    )
    cp.cuda.Stream.null.synchronize()
    actual = cp.asnumpy(snapshots).astype(np.int64)

    oracle_rows: list[tuple[int, int, int, int, list[int], list[int]]] = []
    for env_index in range(args.env_count):
        refs0, refs1 = _shuffled_ref_decks(seed=args.seed, stream=args.stream_base + env_index)
        oracle_rows.append(
            (
                int(first_choices[env_index]),
                int(target_players[env_index]),
                int(modes[env_index]),
                int(active_choices[env_index]),
                refs0,
                refs1,
            )
        )
    official = _official_snapshots(repo_root, deck0, deck1, oracle_rows, basics, filler)
    differential_match = bool(np.array_equal(actual, official))
    runtime_errors_clear = bool(np.all(actual[:, 14] == 0))
    setup_done_valid = bool(
        np.all(np.where(target_players == 0, actual[:, 1], actual[:, 2]) == 1)
    )
    active_area_valid = bool(np.all(actual[:, 30] == 4))
    appear_bit_valid = bool(np.all(actual[:, 37] == (1 << 24)))
    index_counts = {
        str(index): int(np.sum(active_choices[args.doll_cases :] == index)) for index in range(3)
    }

    free_vram, total_vram = cp.cuda.runtime.memGetInfo()
    device_name = cp.cuda.runtime.getDeviceProperties(0)["name"]
    if isinstance(device_name, bytes):
        device_name = device_name.decode()
    print(
        json.dumps(
            {
                "device": str(device_name),
                "env_count": args.env_count,
                "doll_cases": args.doll_cases,
                "differential_match": differential_match,
                "runtime_errors_clear": runtime_errors_clear,
                "setup_done_valid": setup_done_valid,
                "active_area_valid": active_area_valid,
                "appear_bit_valid": appear_bit_valid,
                "basic_selected_option_index_counts": index_counts,
                "state_bytes_per_env": state_size,
                "runtime_bytes_per_env": runtime_size,
                "free_vram_bytes": int(free_vram),
                "total_vram_bytes": int(total_vram),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if differential_match and runtime_errors_clear and setup_done_valid and active_area_valid and appear_bit_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
