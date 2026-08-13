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

_SNAPSHOT_SIZE = 50


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CPU/CUDA one-attempt ResetupActivePokemon differential"
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


def _retry_refs(
    *, seed: int, stream: int, target: int
) -> tuple[list[int], list[int], list[int], int]:
    refs0, refs1 = list(range(62, 2, -1)), list(range(122, 62, -1))
    cursor = shuffle_in_place(refs0, seed=seed, stream=stream, draw_index=0)
    cursor = shuffle_in_place(refs1, seed=seed, stream=stream, draw_index=cursor)
    retry = list(refs0 if target == 0 else refs1)
    cursor = shuffle_in_place(retry, seed=seed, stream=stream, draw_index=cursor)
    return refs0, refs1, retry, cursor


def _official_snapshots(
    repo_root: Path,
    deck0_ids: list[int],
    deck1_ids: list[int],
    rows: list[tuple[int, int, list[int], list[int], list[int]]],
    filler_card_id: int,
) -> np.ndarray:
    official_dir = repo_root / "private/assets/official/ptcg_engine/ptcgProgram 22"
    ids0 = ",".join(str(value) for value in deck0_ids)
    ids1 = ",".join(str(value) for value in deck1_ids)
    source = f"""#include <iostream>\n#include "All.h"\nint main() {{\n InitializeAll(); GameConfig c={{}}; c.seed=1; c.recordLog=false; c.deviceRand=false;\n const int d0[60]={{{ids0}}}; const int d1[60]={{{ids1}}};\n for(int i=0;i<60;++i){{c.decks[0].cards[i]=d0[i];c.decks[1].cards[i]=d1[i];}}\n int first_choice,target;\n while(std::cin>>first_choice>>target) {{\n   BattleData b; b.init(c); State& s=b.state; int retry[60];\n   for(int p=0;p<2;++p) for(int i=0;i<60;++i) {{ int ref; std::cin>>ref; s.players[p].deck[i]=CardRef(ref); }}\n   for(int i=0;i<60;++i) std::cin>>retry[i];\n   s.changed=true; SetYesNoSelect(s, SelectContext::IsFirst, 0); SelectOption first=s.options.at(first_choice);\n   s.firstPlayer=first.type==SelectOptionType::Yes?s.selectPlayer:1-s.selectPlayer; s.clearSelect();\n   for(int p:s.basicPlayerOrder()) Draw(s,p,FIRST_HAND);\n   auto& ps=s.players[target]; for(CardRef ref:ps.hand) s.getCard(ref).cardId={filler_card_id};\n   PreSetupActivePokemon(s,target);\n   if(s.mulliganCount[target] < DECK_SIZE-FIRST_HAND-PRIZE_SIZE) s.mulliganCount[target] += 1;\n   while(ps.hand.size()>0) {{ auto [ref,index]=MoveCardFromLast(ps.hand,ps.deck); (void)index; s.cardMoved(ref,AreaType::Deck); }}\n   for(int i=0;i<60;++i) ps.deck[i]=CardRef(retry[i]);\n   Draw(s,target,FIRST_HAND);\n   s.pushFunction(AfterResetupActivePokemon,target); s.pushFunction(SetupActivePokemon,target); PreSetupActivePokemon(s,target);\n   auto emit=[](long long v){{std::cout<<v<<' ';}};\n   emit(target); emit(s.mulliganCount[0]); emit(s.mulliganCount[1]); emit((int)s.mulligan[0]); emit((int)s.mulligan[1]);\n   emit((int)ps.hand.size()); emit((int)ps.deck.size()); emit(s.moveCounter); emit((int)s.changed); emit((int)s.selectType); emit((int)s.selectContext); emit((int)s.selectPlayer); emit(s.selectMin); emit(s.selectMax); emit((int)s.options.size());\n   bool selected_mulligan=!s.functionStack.empty() && FunctionTable.at(s.functionStack.back().functionIndex)==(void*)SelectedMulligan;\n   emit(3+(selected_mulligan?1:0)); emit(selected_mulligan?3:6); emit(selected_mulligan?s.functionStack.back().arg0:target); emit(0); emit(0); emit(0);\n   for(int i=0;i<7;++i) {{ CardRef ref=ps.hand[i]; emit((int)ref.cardIndex); emit(s.getCard(ref).cardId); }}\n   for(int i=0;i<12;++i) emit((int)ps.deck[ps.deck.size()-1-i].cardIndex);\n   emit((int)s.firstPlayer); emit((int)s.setupDone[target]); emit((int)ps.prize.size()); std::cout<<'\\n';\n }}\n}}\n"""
    lines = []
    for first_choice, target, refs0, refs1, retry in rows:
        lines.append(
            " ".join(str(value) for value in (first_choice, target, *refs0, *refs1, *retry))
        )
    with tempfile.TemporaryDirectory(prefix="gpu-cabt-resetup-once-") as tmp:
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
    filler = next(
        record.card_id
        for record in records
        if not record.is_basic_pokemon and not record.is_setup_doll and not record.can_setup_active
    )
    dense_bytes, row_count = dense_setup_card_table(records)
    dense = np.frombuffer(dense_bytes, dtype=np.uint8).reshape(row_count, 4)

    paths = (
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
        "src/ptcg_rl/gpu_cabt/cuda/open_return_shuffle.cu",
        "src/ptcg_rl/gpu_cabt/cuda/resetup_active_once.cu",
    )
    source = "\n".join((repo_root / path).read_text(encoding="utf-8") for path in paths)
    names = (
        "gpu_cabt_battle_core_size",
        "gpu_cabt_runtime_size",
        "gpu_cabt_init_battles",
        "gpu_cabt_setup_is_first",
        "gpu_cabt_opening_draw_after_is_first",
        "gpu_cabt_force_no_basic_hand",
        "gpu_cabt_pre_setup_active",
        "gpu_cabt_resetup_active_once",
        "gpu_cabt_resetup_active_once_snapshot",
    )
    module = load_cupy_module(cp, source, kernel_names=names)
    state_out, runtime_out = cp.empty(1, dtype=cp.uint64), cp.empty(1, dtype=cp.uint64)
    module.get_function("gpu_cabt_battle_core_size")((1,), (1,), (state_out,))
    module.get_function("gpu_cabt_runtime_size")((1,), (1,), (runtime_out,))
    cp.cuda.Stream.null.synchronize()
    state_size, runtime_size = int(cp.asnumpy(state_out)[0]), int(cp.asnumpy(runtime_out)[0])

    first = np.arange(args.env_count, dtype=np.int32) & 1
    targets = (np.arange(args.env_count, dtype=np.int32) >> 1) & 1
    first_d, targets_d, table_d = cp.asarray(first), cp.asarray(targets), cp.asarray(dense)
    decks_d = cp.asarray(np.tile(np.asarray(deck0 + deck1, dtype=np.int32), (args.env_count, 1)))
    states, runtimes = (
        cp.empty(args.env_count * state_size, dtype=cp.uint8),
        cp.empty(args.env_count * runtime_size, dtype=cp.uint8),
    )
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
    module.get_function("gpu_cabt_force_no_basic_hand")(
        (blocks,), (threads,), (states, targets_d, np.int32(filler), np.int32(args.env_count))
    )
    module.get_function("gpu_cabt_pre_setup_active")(
        (blocks,),
        (threads,),
        (states, runtimes, table_d, np.int32(row_count), targets_d, np.int32(args.env_count)),
    )
    module.get_function("gpu_cabt_resetup_active_once")(
        (blocks,),
        (threads,),
        (
            states,
            runtimes,
            table_d,
            np.int32(row_count),
            targets_d,
            np.uint64(args.seed),
            np.uint64(args.stream_base),
            np.int32(args.env_count),
        ),
    )
    module.get_function("gpu_cabt_resetup_active_once_snapshot")(
        (blocks,), (threads,), (states, runtimes, targets_d, snapshots, np.int32(args.env_count))
    )
    cp.cuda.Stream.null.synchronize()
    actual = cp.asnumpy(snapshots)

    rows = []
    cursors = []
    for i in range(args.env_count):
        refs0, refs1, retry, cursor = _retry_refs(
            seed=args.seed, stream=args.stream_base + i, target=int(targets[i])
        )
        rows.append((int(first[i]), int(targets[i]), refs0, refs1, retry))
        cursors.append(cursor)
    official = _official_snapshots(repo_root, deck0, deck1, rows, filler)
    for i, cursor in enumerate(cursors):
        official[i, 19] = cursor & 0xFFFFFFFF
        official[i, 20] = (cursor >> 32) & 0xFFFFFFFF
    differential_match = bool(np.array_equal(actual, official))
    errors_clear = bool(np.all(actual[:, 18] == 0))
    target_counts = np.where(targets == 0, actual[:, 1], actual[:, 2])
    target_mulligan = np.where(targets == 0, actual[:, 3], actual[:, 4])
    count_valid = bool(np.all(target_counts == 1))
    branch_counts = {
        "new_hand_has_basic": int(np.sum(target_mulligan == 0)),
        "retry_again": int(np.sum(target_mulligan == 1)),
    }
    branches_seen = all(value > 0 for value in branch_counts.values())

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
                "mulligan_count_valid": count_valid,
                "branch_counts": branch_counts,
                "branches_seen": branches_seen,
                "state_bytes_per_env": state_size,
                "runtime_bytes_per_env": runtime_size,
                "free_vram_bytes": int(free_vram),
                "total_vram_bytes": int(total_vram),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if differential_match and errors_clear and count_valid and branches_seen else 1


if __name__ == "__main__":
    raise SystemExit(main())
