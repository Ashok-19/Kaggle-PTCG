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

_SNAPSHOT_SIZE = 20
_DOLL_CARD_ID = 666


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Official CPU vs CUDA PreSetupActivePokemon differential")
    parser.add_argument("--deck0", type=Path, required=True)
    parser.add_argument("--deck1", type=Path, required=True)
    parser.add_argument("--env-count", type=int, default=8192)
    parser.add_argument("--differential-envs", type=int, default=1024)
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
    rows: list[tuple[int, int, int, list[int], list[int]]],
    filler_card_id: int,
) -> np.ndarray:
    official_dir = repo_root / "private/assets/official/ptcg_engine/ptcgProgram 22"
    ids0 = ",".join(str(value) for value in deck0_ids)
    ids1 = ",".join(str(value) for value in deck1_ids)
    source = f'''#include <iostream>\n#include "All.h"\nint main() {{\n InitializeAll(); GameConfig c={{}}; c.seed=1; c.recordLog=false; c.deviceRand=false;\n const int d0[60]={{{ids0}}}; const int d1[60]={{{ids1}}};\n for(int i=0;i<60;++i){{c.decks[0].cards[i]=d0[i];c.decks[1].cards[i]=d1[i];}}\n int selected,target,doll_mode;\n while(std::cin>>selected>>target>>doll_mode) {{\n   BattleData b; b.init(c); State& s=b.state;\n   for(int p=0;p<2;++p) for(int i=0;i<60;++i) {{ int ref; std::cin>>ref; s.players[p].deck[i]=CardRef(ref); }}\n   s.changed=true; SetYesNoSelect(s, SelectContext::IsFirst, 0);\n   SelectOption first=s.options.at(selected);\n   s.firstPlayer = first.type==SelectOptionType::Yes ? s.selectPlayer : 1-s.selectPlayer;\n   s.clearSelect();\n   for(int p:s.basicPlayerOrder()) Draw(s,p,FIRST_HAND);\n   if(doll_mode) {{\n     auto& hand=s.players[target].hand;\n     for(int i=0;i<hand.size();++i) s.getCard(hand[i]).cardId = i==0 ? {_DOLL_CARD_ID} : {filler_card_id};\n   }}\n   PreSetupActivePokemon(s,target);\n   bool selected_mulligan=false; int selected_mulligan_arg=-1;\n   if(!s.functionStack.empty()) {{\n     const GameFunction& gf=s.functionStack.back();\n     selected_mulligan = FunctionTable.at(gf.functionIndex)==(void*)SelectedMulligan;\n     if(selected_mulligan) selected_mulligan_arg=gf.arg0;\n   }}\n   auto emit=[](long long v){{std::cout<<v<<' ';}};\n   emit(target); emit((int)s.mulligan[0]); emit((int)s.mulligan[1]);\n   emit((int)s.selectType); emit((int)s.selectContext); emit((int)s.selectPlayer);\n   emit(s.selectMin); emit(s.selectMax); emit((int)s.options.size());\n   emit(s.options.size()>0?(int)s.options[0].type:-1); emit(s.options.size()>1?(int)s.options[1].type:-1);\n   emit(1+(selected_mulligan?1:0)); emit(selected_mulligan?3:2); emit(selected_mulligan?selected_mulligan_arg:0);\n   emit(0); emit((int)s.players[target].hand.size()); emit((int)s.players[target].deck.size());\n   emit((int)s.firstPlayer); emit(s.moveCounter); emit((int)s.changed); std::cout<<'\\n';\n }}\n}}\n'''
    input_lines: list[str] = []
    for selected, target, doll_mode, deck0_refs, deck1_refs in rows:
        values = [selected, target, doll_mode, *deck0_refs, *deck1_refs]
        input_lines.append(" ".join(str(value) for value in values))
    with tempfile.TemporaryDirectory(prefix="gpu-cabt-pre-setup-") as tmp:
        cpp = Path(tmp) / "probe.cpp"
        exe = Path(tmp) / "probe"
        cpp.write_text(source, encoding="utf-8")
        subprocess.run(
            ["g++", "-std=c++23", "-O2", "-I", str(official_dir), str(cpp), "-o", str(exe)],
            check=True,
        )
        output = subprocess.check_output([str(exe)], input="\n".join(input_lines) + "\n", text=True)
    values = [int(value) for value in output.split()]
    expected = len(rows) * _SNAPSHOT_SIZE
    if len(values) != expected:
        raise RuntimeError(f"official snapshot ints {len(values)} != {expected}")
    return np.asarray(values, dtype=np.int32).reshape(len(rows), _SNAPSHOT_SIZE)


def main() -> int:
    args = _parse_args()
    if not 0 <= args.doll_cases <= args.differential_envs <= args.env_count:
        raise ValueError("require 0 <= doll-cases <= differential-envs <= env-count")

    import cupy as cp

    repo_root = Path(__file__).resolve().parents[1]
    deck0 = _load_deck(args.deck0)
    deck1 = _load_deck(args.deck1)
    records = extract_setup_card_static(repo_root / "private/assets/official/ptcg_engine/ptcgProgram 22")
    by_id = {record.card_id: record for record in records}
    doll = by_id.get(_DOLL_CARD_ID)
    if doll is None or not doll.is_setup_doll or doll.is_basic_pokemon:
        raise RuntimeError("official card 666 no longer matches the qualified setup-doll edge case")
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
            "gpu_cabt_pre_setup_active_snapshot",
        ),
    )
    state_size_kernel = module.get_function("gpu_cabt_battle_core_size")
    runtime_size_kernel = module.get_function("gpu_cabt_runtime_size")
    init_kernel = module.get_function("gpu_cabt_init_battles")
    setup_kernel = module.get_function("gpu_cabt_setup_is_first")
    opening_kernel = module.get_function("gpu_cabt_opening_draw_after_is_first")
    force_doll_kernel = module.get_function("gpu_cabt_force_setup_doll_hand")
    pre_setup_kernel = module.get_function("gpu_cabt_pre_setup_active")
    snapshot_kernel = module.get_function("gpu_cabt_pre_setup_active_snapshot")

    state_size_out = cp.empty(1, dtype=cp.uint64)
    runtime_size_out = cp.empty(1, dtype=cp.uint64)
    state_size_kernel((1,), (1,), (state_size_out,))
    runtime_size_kernel((1,), (1,), (runtime_size_out,))
    cp.cuda.Stream.null.synchronize()
    state_size = int(cp.asnumpy(state_size_out)[0])
    runtime_size = int(cp.asnumpy(runtime_size_out)[0])

    device_decks = cp.asarray(np.tile(np.asarray(deck0 + deck1, dtype=np.int32), (args.env_count, 1)))
    first_choices = np.arange(args.env_count, dtype=np.int32) & 1
    target_players = (np.arange(args.env_count, dtype=np.int32) >> 1) & 1
    first_device = cp.asarray(first_choices)
    targets_device = cp.asarray(target_players)
    card_table_device = cp.asarray(dense)
    raw_states = cp.empty(args.env_count * state_size, dtype=cp.uint8)
    raw_runtimes = cp.empty(args.env_count * runtime_size, dtype=cp.uint8)
    snapshots = cp.empty((args.env_count, _SNAPSHOT_SIZE), dtype=cp.int32)
    threads = 128
    blocks = (args.env_count + threads - 1) // threads

    init_kernel((blocks,), (threads,), (raw_states, device_decks, np.int32(args.env_count)))
    setup_kernel(
        (blocks,), (threads,),
        (raw_states, raw_runtimes, np.uint64(args.seed), np.uint64(args.stream_base), np.int32(args.env_count)),
    )
    opening_kernel((blocks,), (threads,), (raw_states, raw_runtimes, first_device, np.int32(args.env_count)))
    if args.doll_cases:
        doll_blocks = (args.doll_cases + threads - 1) // threads
        force_doll_kernel(
            (doll_blocks,), (threads,),
            (raw_states, targets_device, np.int32(_DOLL_CARD_ID), np.int32(filler), np.int32(args.doll_cases)),
        )
    pre_setup_kernel(
        (blocks,), (threads,),
        (raw_states, raw_runtimes, card_table_device, np.int32(row_count), targets_device, np.int32(args.env_count)),
    )
    snapshot_kernel(
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
                int(env_index < args.doll_cases),
                refs0,
                refs1,
            )
        )
    official = _official_snapshots(repo_root, deck0, deck1, oracle_rows, filler)
    differential_match = bool(np.array_equal(actual[: args.differential_envs], official))
    runtime_errors_clear = bool(np.all(actual[:, 14] == 0))

    diff = actual[: args.differential_envs]
    target = diff[:, 0]
    target_mulligan = np.where(target == 0, diff[:, 1], diff[:, 2])
    doll_branch = diff[:, 8] == 2
    no_basic_branch = (target_mulligan == 1) & ~doll_branch
    basic_branch = (target_mulligan == 0) & ~doll_branch
    branch_counts = {
        "basic": int(np.sum(basic_branch)),
        "mulligan": int(np.sum(no_basic_branch)),
        "doll": int(np.sum(doll_branch)),
    }
    branches_covered = all(branch_counts[name] > 0 for name in ("basic", "mulligan", "doll"))

    free_vram, total_vram = cp.cuda.runtime.memGetInfo()
    device_name = cp.cuda.runtime.getDeviceProperties(0)["name"]
    if isinstance(device_name, bytes):
        device_name = device_name.decode()
    report = {
        "device": str(device_name),
        "env_count": args.env_count,
        "differential_envs": args.differential_envs,
        "doll_cases": args.doll_cases,
        "differential_match": differential_match,
        "runtime_errors_clear": runtime_errors_clear,
        "branches_covered": branches_covered,
        "branch_counts": branch_counts,
        "filler_card_id": filler,
        "state_bytes_per_env": state_size,
        "runtime_bytes_per_env": runtime_size,
        "free_vram_bytes": int(free_vram),
        "total_vram_bytes": int(total_vram),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if differential_match and runtime_errors_clear and branches_covered else 1


if __name__ == "__main__":
    raise SystemExit(main())
