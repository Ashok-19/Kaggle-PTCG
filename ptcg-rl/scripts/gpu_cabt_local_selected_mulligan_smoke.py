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

_SNAPSHOT_SIZE = 17
_DOLL_CARD_ID = 666


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Official CPU vs CUDA SelectedMulligan differential")
    parser.add_argument("--deck0", type=Path, required=True)
    parser.add_argument("--deck1", type=Path, required=True)
    parser.add_argument("--env-count", type=int, default=512)
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


def _official_snapshots(
    repo_root: Path,
    deck0_ids: list[int],
    deck1_ids: list[int],
    first_choices: np.ndarray,
    target_players: np.ndarray,
    mulligan_choices: np.ndarray,
    filler_card_id: int,
) -> np.ndarray:
    official_dir = repo_root / "private/assets/official/ptcg_engine/ptcgProgram 22"
    ids0 = ",".join(str(value) for value in deck0_ids)
    ids1 = ",".join(str(value) for value in deck1_ids)
    source = f'''#include <iostream>\n#include "All.h"\nint main() {{\n InitializeAll(); GameConfig c={{}}; c.seed=1; c.recordLog=false; c.deviceRand=false;\n const int d0[60]={{{ids0}}}; const int d1[60]={{{ids1}}};\n for(int i=0;i<60;++i){{c.decks[0].cards[i]=d0[i];c.decks[1].cards[i]=d1[i];}}\n int first_choice,target,mulligan_choice;\n while(std::cin>>first_choice>>target>>mulligan_choice) {{\n   BattleData b; b.init(c); State& s=b.state;\n   s.changed=true; SetYesNoSelect(s, SelectContext::IsFirst, 0);\n   SelectOption first=s.options.at(first_choice);\n   s.firstPlayer = first.type==SelectOptionType::Yes ? s.selectPlayer : 1-s.selectPlayer;\n   s.clearSelect();\n   for(int p:s.basicPlayerOrder()) Draw(s,p,FIRST_HAND);\n   auto& hand=s.players[target].hand;\n   for(int i=0;i<hand.size();++i) s.getCard(hand[i]).cardId = i==0 ? {_DOLL_CARD_ID} : {filler_card_id};\n   PreSetupActivePokemon(s,target);\n   s.selected.push_back(mulligan_choice);\n   s.callFunction();\n   auto emit=[](long long v){{std::cout<<v<<' ';}};\n   emit(target); emit((int)s.mulligan[0]); emit((int)s.mulligan[1]);\n   emit((int)s.selectType); emit((int)s.selectContext); emit((int)s.selectPlayer);\n   emit(s.selectMin); emit(s.selectMax); emit((int)s.options.size()); emit((int)s.selected.size());\n   emit(1); emit(2); emit(0); emit((int)s.players[target].hand.size());\n   emit((int)s.players[target].deck.size()); emit(s.moveCounter); emit((int)s.changed); std::cout<<'\\n';\n }}\n}}\n'''
    input_text = "\n".join(
        f"{int(first)} {int(target)} {int(choice)}"
        for first, target, choice in zip(first_choices, target_players, mulligan_choices, strict=True)
    ) + "\n"
    with tempfile.TemporaryDirectory(prefix="gpu-cabt-selected-mulligan-") as tmp:
        cpp = Path(tmp) / "probe.cpp"
        exe = Path(tmp) / "probe"
        cpp.write_text(source, encoding="utf-8")
        subprocess.run(
            ["g++", "-std=c++23", "-O2", "-I", str(official_dir), str(cpp), "-o", str(exe)],
            check=True,
        )
        output = subprocess.check_output([str(exe)], input=input_text, text=True)
    values = [int(value) for value in output.split()]
    expected = len(first_choices) * _SNAPSHOT_SIZE
    if len(values) != expected:
        raise RuntimeError(f"official snapshot ints {len(values)} != {expected}")
    return np.asarray(values, dtype=np.int32).reshape(len(first_choices), _SNAPSHOT_SIZE)


def main() -> int:
    args = _parse_args()
    if args.env_count <= 0:
        raise ValueError("env-count must be positive")

    import cupy as cp

    repo_root = Path(__file__).resolve().parents[1]
    deck0 = _load_deck(args.deck0)
    deck1 = _load_deck(args.deck1)
    records = extract_setup_card_static(repo_root / "private/assets/official/ptcg_engine/ptcgProgram 22")
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
            "gpu_cabt_selected_mulligan_snapshot",
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
    mulligan_choices = (np.arange(args.env_count, dtype=np.int32) >> 2) & 1
    device_decks = cp.asarray(np.tile(np.asarray(deck0 + deck1, dtype=np.int32), (args.env_count, 1)))
    first_device = cp.asarray(first_choices)
    targets_device = cp.asarray(target_players)
    choices_device = cp.asarray(mulligan_choices)
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
    module.get_function("gpu_cabt_force_setup_doll_hand")(
        (blocks,), (threads,),
        (raw_states, targets_device, np.int32(_DOLL_CARD_ID), np.int32(filler), np.int32(args.env_count)),
    )
    module.get_function("gpu_cabt_pre_setup_active")(
        (blocks,), (threads,),
        (raw_states, raw_runtimes, card_table_device, np.int32(row_count), targets_device, np.int32(args.env_count)),
    )
    module.get_function("gpu_cabt_selected_mulligan")(
        (blocks,), (threads,),
        (raw_states, raw_runtimes, targets_device, choices_device, np.int32(args.env_count)),
    )
    module.get_function("gpu_cabt_selected_mulligan_snapshot")(
        (blocks,), (threads,),
        (raw_states, raw_runtimes, targets_device, snapshots, np.int32(args.env_count)),
    )
    cp.cuda.Stream.null.synchronize()
    actual = cp.asnumpy(snapshots)
    official = _official_snapshots(
        repo_root, deck0, deck1, first_choices, target_players, mulligan_choices, filler
    )
    differential_match = bool(np.array_equal(actual, official))
    runtime_errors_clear = bool(np.all(actual[:, 12] == 0))
    yes_count = int(np.sum(mulligan_choices == 0))
    no_count = int(np.sum(mulligan_choices == 1))

    free_vram, total_vram = cp.cuda.runtime.memGetInfo()
    device_name = cp.cuda.runtime.getDeviceProperties(0)["name"]
    if isinstance(device_name, bytes):
        device_name = device_name.decode()
    print(
        json.dumps(
            {
                "device": str(device_name),
                "env_count": args.env_count,
                "differential_match": differential_match,
                "runtime_errors_clear": runtime_errors_clear,
                "selected_option0_yes_cases": yes_count,
                "selected_option1_no_cases": no_count,
                "state_bytes_per_env": state_size,
                "runtime_bytes_per_env": runtime_size,
                "free_vram_bytes": int(free_vram),
                "total_vram_bytes": int(total_vram),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if differential_match and runtime_errors_clear and yes_count and no_count else 1


if __name__ == "__main__":
    raise SystemExit(main())
