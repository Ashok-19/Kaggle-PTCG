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

_SNAPSHOT_SIZE = 60
_DOLL_CARD_ID = 666
_MODE_NORMAL = 0
_MODE_DOLL_KEEP = 1
_MODE_DOLL_MULLIGAN = 2
_MODE_FATAL_NO_BASIC = 3
_ERROR_NO_BASIC = 1 << 6


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Official CPU vs CUDA SetupActivePokemon differential")
    parser.add_argument("--deck0", type=Path, required=True)
    parser.add_argument("--deck1", type=Path, required=True)
    parser.add_argument("--env-count", type=int, default=2048)
    parser.add_argument("--differential-envs", type=int, default=1024)
    parser.add_argument("--doll-keep-cases", type=int, default=64)
    parser.add_argument("--doll-mulligan-cases", type=int, default=64)
    parser.add_argument("--fatal-cases", type=int, default=32)
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
    filler_card_id: int,
) -> np.ndarray:
    official_dir = repo_root / "private/assets/official/ptcg_engine/ptcgProgram 22"
    ids0 = ",".join(str(value) for value in deck0_ids)
    ids1 = ",".join(str(value) for value in deck1_ids)
    source = f'''#include <iostream>\n#include "All.h"\nint main() {{\n InitializeAll(); GameConfig c={{}}; c.seed=1; c.recordLog=false; c.deviceRand=false;\n const int d0[60]={{{ids0}}}; const int d1[60]={{{ids1}}};\n for(int i=0;i<60;++i){{c.decks[0].cards[i]=d0[i];c.decks[1].cards[i]=d1[i];}}\n int first_choice,target,mode;\n while(std::cin>>first_choice>>target>>mode) {{\n   BattleData b; b.init(c); State& s=b.state;\n   for(int p=0;p<2;++p) for(int i=0;i<60;++i) {{ int ref; std::cin>>ref; s.players[p].deck[i]=CardRef(ref); }}\n   s.changed=true; SetYesNoSelect(s, SelectContext::IsFirst, 0);\n   SelectOption first=s.options.at(first_choice);\n   s.firstPlayer = first.type==SelectOptionType::Yes ? s.selectPlayer : 1-s.selectPlayer;\n   s.clearSelect();\n   for(int p:s.basicPlayerOrder()) Draw(s,p,FIRST_HAND);\n   if(mode=={_MODE_DOLL_KEEP} || mode=={_MODE_DOLL_MULLIGAN}) {{\n     auto& hand=s.players[target].hand;\n     for(int i=0;i<hand.size();++i) s.getCard(hand[i]).cardId = i==0 ? {_DOLL_CARD_ID} : {filler_card_id};\n   }} else if(mode=={_MODE_FATAL_NO_BASIC}) {{\n     auto& hand=s.players[target].hand; auto& deck=s.players[target].deck;\n     for(CardRef ref:hand) s.getCard(ref).cardId={filler_card_id};\n     for(CardRef ref:deck) s.getCard(ref).cardId={filler_card_id};\n   }}\n   PreSetupActivePokemon(s,target);\n   if(mode=={_MODE_DOLL_KEEP} || mode=={_MODE_DOLL_MULLIGAN}) {{\n     s.selected.push_back(mode=={_MODE_DOLL_KEEP} ? 1 : 0);\n     s.callFunction();\n   }}\n   int error_flags=0;\n   try {{ SetupActivePokemon(s,target); }}\n   catch(const std::runtime_error& e) {{ if(std::string(e.what())=="No Basic Pokemon.") error_flags={_ERROR_NO_BASIC}; else throw; }}\n   bool selected_setup=false; int selected_setup_arg=0;\n   if(!s.functionStack.empty()) {{\n     const GameFunction& gf=s.functionStack.back();\n     selected_setup = FunctionTable.at(gf.functionIndex)==(void*)SelectedSetupActivePokemon;\n     if(selected_setup) selected_setup_arg=gf.arg0;\n   }}\n   auto emit=[](long long v){{std::cout<<v<<' ';}};\n   emit(target); emit((int)s.mulligan[0]); emit((int)s.mulligan[1]);\n   emit((int)s.selectType); emit((int)s.selectContext); emit((int)s.selectPlayer);\n   emit(s.selectMin); emit(s.selectMax); emit((int)s.options.size());\n   emit(1+(selected_setup?1:0)); emit(selected_setup?4:2); emit(selected_setup?selected_setup_arg:0);\n   emit(error_flags); emit((int)s.players[target].hand.size()); emit((int)s.players[target].deck.size());\n   for(int i=0;i<7;++i) {{\n     if(i<(int)s.options.size()) {{ const SelectOption& o=s.options[i]; emit((int)o.type); emit(o.param0); emit(o.param1); emit(o.param2); emit(o.param3); emit(o.param4); }}\n     else {{ for(int f=0;f<6;++f) emit(-1); }}\n   }}\n   emit((int)s.firstPlayer); emit(s.moveCounter); emit((int)s.changed); std::cout<<'\\n';\n }}\n}}\n'''
    lines: list[str] = []
    for first_choice, target, mode, refs0, refs1 in rows:
        values = [first_choice, target, mode, *refs0, *refs1]
        lines.append(" ".join(str(value) for value in values))
    with tempfile.TemporaryDirectory(prefix="gpu-cabt-setup-active-") as tmp:
        cpp = Path(tmp) / "probe.cpp"
        exe = Path(tmp) / "probe"
        cpp.write_text(source, encoding="utf-8")
        subprocess.run(
            ["g++", "-std=c++23", "-O2", "-I", str(official_dir), str(cpp), "-o", str(exe)],
            check=True,
        )
        completed = subprocess.run(
            [str(exe)],
            input="\n".join(lines) + "\n",
            text=True,
            capture_output=True,
            check=True,
        )
    values = [int(value) for value in completed.stdout.split()]
    expected = len(rows) * _SNAPSHOT_SIZE
    if len(values) != expected:
        raise RuntimeError(f"official snapshot ints {len(values)} != {expected}; stderr={completed.stderr}")
    return np.asarray(values, dtype=np.int32).reshape(len(rows), _SNAPSHOT_SIZE)


def main() -> int:
    args = _parse_args()
    special = args.doll_keep_cases + args.doll_mulligan_cases + args.fatal_cases
    if not 0 <= special <= args.differential_envs <= args.env_count:
        raise ValueError("special cases must fit within differential-envs <= env-count")

    import cupy as cp

    repo_root = Path(__file__).resolve().parents[1]
    deck0 = _load_deck(args.deck0)
    deck1 = _load_deck(args.deck1)
    records = extract_setup_card_static(repo_root / "private/assets/official/ptcg_engine/ptcgProgram 22")
    by_id = {record.card_id: record for record in records}
    doll = by_id.get(_DOLL_CARD_ID)
    if doll is None or not doll.is_setup_doll or not doll.can_setup_active:
        raise RuntimeError("setup-doll qualification anchor changed")
    filler = next(
        record.card_id
        for record in records
        if not record.is_basic_pokemon and not record.is_setup_doll and not record.can_setup_active
    )
    dense_bytes, row_count = dense_setup_card_table(records)
    dense = np.frombuffer(dense_bytes, dtype=np.uint8).reshape(row_count, 4)

    source_paths = (
        "src/ptcg_rl/gpu_cabt/native/state_core.h",
        "src/ptcg_rl/gpu_cabt/native/state_fields.h",
        "src/ptcg_rl/gpu_cabt/native/runtime_state.h",
        "src/ptcg_rl/gpu_cabt/cuda/public_log_core.cu",
        "src/ptcg_rl/gpu_cabt/cuda/public_log_emit.cu",
        "src/ptcg_rl/gpu_cabt/native/card_static.h",
        "src/ptcg_rl/gpu_cabt/cuda/rng_shuffle.cu",
        "src/ptcg_rl/gpu_cabt/cuda/battle_init.cu",
        "src/ptcg_rl/gpu_cabt/cuda/setup_is_first.cu",
        "src/ptcg_rl/gpu_cabt/cuda/card_move.cu",
        "src/ptcg_rl/gpu_cabt/cuda/opening_draw.cu",
        "src/ptcg_rl/gpu_cabt/cuda/pre_setup_active.cu",
        "src/ptcg_rl/gpu_cabt/cuda/selected_mulligan.cu",
        "src/ptcg_rl/gpu_cabt/cuda/setup_active.cu",
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
            "gpu_cabt_pre_setup_active",
            "gpu_cabt_selected_mulligan",
            "gpu_cabt_force_no_basic_player",
            "gpu_cabt_setup_active",
            "gpu_cabt_setup_active_snapshot",
        ),
    )
    state_size_out = cp.empty(1, dtype=cp.uint64)
    runtime_size_out = cp.empty(1, dtype=cp.uint64)
    module.get_function("gpu_cabt_battle_core_size")((1,), (1,), (state_size_out,))
    module.get_function("gpu_cabt_runtime_size")((1,), (1,), (runtime_size_out,))
    cp.cuda.Stream.null.synchronize()
    state_size = int(cp.asnumpy(state_size_out)[0])
    runtime_size = int(cp.asnumpy(runtime_size_out)[0])

    modes = np.zeros(args.env_count, dtype=np.int32)
    doll_keep_start = 0
    doll_mulligan_start = doll_keep_start + args.doll_keep_cases
    fatal_start = doll_mulligan_start + args.doll_mulligan_cases
    modes[doll_keep_start:doll_mulligan_start] = _MODE_DOLL_KEEP
    modes[doll_mulligan_start:fatal_start] = _MODE_DOLL_MULLIGAN
    modes[fatal_start : fatal_start + args.fatal_cases] = _MODE_FATAL_NO_BASIC
    first_choices = np.arange(args.env_count, dtype=np.int32) & 1
    target_players = (np.arange(args.env_count, dtype=np.int32) >> 1) & 1

    device_decks = cp.asarray(np.tile(np.asarray(deck0 + deck1, dtype=np.int32), (args.env_count, 1)))
    first_device = cp.asarray(first_choices)
    targets_device = cp.asarray(target_players)
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
    doll_total = args.doll_keep_cases + args.doll_mulligan_cases
    if doll_total:
        doll_blocks = (doll_total + threads - 1) // threads
        module.get_function("gpu_cabt_force_setup_doll_hand")(
            (doll_blocks,), (threads,),
            (raw_states, targets_device, np.int32(_DOLL_CARD_ID), np.int32(filler), np.int32(doll_total)),
        )
    if args.fatal_cases:
        fatal_blocks = (args.fatal_cases + threads - 1) // threads
        module.get_function("gpu_cabt_force_no_basic_player")(
            (fatal_blocks,), (threads,),
            (
                raw_states,
                targets_device,
                np.int32(filler),
                np.int32(fatal_start),
                np.int32(args.fatal_cases),
            ),
        )
    module.get_function("gpu_cabt_pre_setup_active")(
        (blocks,), (threads,),
        (raw_states, raw_runtimes, card_table_device, np.int32(row_count), targets_device, np.int32(args.env_count)),
    )
    if doll_total:
        doll_choices = np.concatenate(
            (
                np.ones(args.doll_keep_cases, dtype=np.int32),
                np.zeros(args.doll_mulligan_cases, dtype=np.int32),
            )
        )
        doll_choices_device = cp.asarray(doll_choices)
        doll_blocks = (doll_total + threads - 1) // threads
        module.get_function("gpu_cabt_selected_mulligan")(
            (doll_blocks,), (threads,),
            (raw_states, raw_runtimes, targets_device, doll_choices_device, np.int32(doll_total)),
        )
    module.get_function("gpu_cabt_setup_active")(
        (blocks,), (threads,),
        (raw_states, raw_runtimes, card_table_device, np.int32(row_count), targets_device, np.int32(args.env_count)),
    )
    module.get_function("gpu_cabt_setup_active_snapshot")(
        (blocks,), (threads,),
        (raw_states, raw_runtimes, targets_device, snapshots, np.int32(args.env_count)),
    )
    cp.cuda.Stream.null.synchronize()
    actual = cp.asnumpy(snapshots)

    oracle_rows: list[tuple[int, int, int, list[int], list[int]]] = []
    for env_index in range(args.differential_envs):
        refs0, refs1 = _shuffled_ref_decks(seed=args.seed, stream=args.stream_base + env_index)
        oracle_rows.append(
            (
                int(first_choices[env_index]),
                int(target_players[env_index]),
                int(modes[env_index]),
                refs0,
                refs1,
            )
        )
    official = _official_snapshots(repo_root, deck0, deck1, oracle_rows, filler)
    differential_match = bool(np.array_equal(actual[: args.differential_envs], official))

    diff = actual[: args.differential_envs]
    fatal_mask = diff[:, 12] == _ERROR_NO_BASIC
    unexpected_error_mask = (diff[:, 12] != 0) & ~fatal_mask
    active_selection_mask = (diff[:, 3] == 2) & (diff[:, 8] > 0) & (diff[:, 12] == 0)
    mulligan_no_selection_mask = (diff[:, 8] == 0) & (diff[:, 12] == 0)
    branch_counts = {
        "active_selection": int(np.sum(active_selection_mask)),
        "mulligan_no_selection": int(np.sum(mulligan_no_selection_mask)),
        "fatal_no_basic": int(np.sum(fatal_mask)),
        "doll_keep": args.doll_keep_cases,
        "doll_mulligan": args.doll_mulligan_cases,
    }
    branches_covered = (
        branch_counts["active_selection"] > 0
        and branch_counts["mulligan_no_selection"] > 0
        and branch_counts["fatal_no_basic"] == args.fatal_cases
        and args.doll_keep_cases > 0
        and args.doll_mulligan_cases > 0
    )

    free_vram, total_vram = cp.cuda.runtime.memGetInfo()
    device_name = cp.cuda.runtime.getDeviceProperties(0)["name"]
    if isinstance(device_name, bytes):
        device_name = device_name.decode()
    print(
        json.dumps(
            {
                "device": str(device_name),
                "env_count": args.env_count,
                "differential_envs": args.differential_envs,
                "differential_match": differential_match,
                "branches_covered": branches_covered,
                "branch_counts": branch_counts,
                "unexpected_error_rows": int(np.sum(unexpected_error_mask)),
                "state_bytes_per_env": state_size,
                "runtime_bytes_per_env": runtime_size,
                "free_vram_bytes": int(free_vram),
                "total_vram_bytes": int(total_vram),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if differential_match and branches_covered and not np.any(unexpected_error_mask) else 1


if __name__ == "__main__":
    raise SystemExit(main())
