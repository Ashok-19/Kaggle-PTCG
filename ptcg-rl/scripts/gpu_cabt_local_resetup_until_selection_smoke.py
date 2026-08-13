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

_SNAPSHOT_SIZE = 86


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Official-primitives vs CUDA full mulligan-loop differential"
    )
    parser.add_argument("--deck0", type=Path, required=True)
    parser.add_argument("--deck1", type=Path, required=True)
    parser.add_argument("--env-count", type=int, default=2048)
    parser.add_argument("--differential-envs", type=int, default=512)
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
    rows: list[tuple[int, int, int]],
    filler_card_id: int,
    seed: int,
) -> np.ndarray:
    official_dir = repo_root / "private/assets/official/ptcg_engine/ptcgProgram 22"
    ids0 = ",".join(str(value) for value in deck0_ids)
    ids1 = ",".join(str(value) for value in deck1_ids)
    source = f"""#include <cstdint>\n#include <iostream>\n#include "All.h"\nusing u32=std::uint32_t; using u64=std::uint64_t;\nstatic constexpr u32 M0=0xD2511F53u,M1=0xCD9E8D57u,W0=0x9E3779B9u,W1=0xBB67AE85u;\nvoid philox(u32& c0,u32& c1,u32& c2,u32& c3,u32 k0,u32 k1){{for(int r=0;r<10;++r){{u64 p0=(u64)M0*c0,p1=(u64)M1*c2;u32 hi0=p0>>32,lo0=p0,hi1=p1>>32,lo1=p1;u32 n0=hi1^c1^k0,n1=lo1,n2=hi0^c3^k1,n3=lo0;c0=n0;c1=n1;c2=n2;c3=n3;if(r!=9){{k0+=W0;k1+=W1;}}}}}}\nu32 rnd(u64 seed,u64 stream,u64 idx){{u64 block=idx>>2;u32 lane=idx&3,c0=block,c1=block>>32,c2=stream,c3=stream>>32;philox(c0,c1,c2,c3,(u32)seed,(u32)(seed>>32));return lane==0?c0:lane==1?c1:lane==2?c2:c3;}}\nu32 bounded(u64 seed,u64 stream,u64& idx,u32 bound){{u32 threshold=(u32)(-bound)%bound;for(;;){{u32 value=rnd(seed,stream,idx++);u64 product=(u64)value*bound;u32 low=product;if(low>=threshold)return product>>32;}}}}\ntemplate<class L> void shuffle_philox(L& list,u64 seed,u64 stream,u64& idx){{for(int i=(int)list.size()-1;i>0;--i){{u32 j=bounded(seed,stream,idx,(u32)(i+1));std::swap(list[i],list[j]);}}}}\nint main(){{\n InitializeAll(); GameConfig c={{}}; c.seed=1;c.recordLog=false;c.deviceRand=false; const int d0[60]={{{ids0}}};const int d1[60]={{{ids1}}};for(int i=0;i<60;++i){{c.decks[0].cards[i]=d0[i];c.decks[1].cards[i]=d1[i];}}\n int first_choice,target; unsigned long long stream; while(std::cin>>first_choice>>target>>stream){{BattleData b;b.init(c);State& s=b.state;u64 cursor=0;shuffle_philox(s.players[0].deck,{seed}ull,stream,cursor);shuffle_philox(s.players[1].deck,{seed}ull,stream,cursor);s.changed=true;SetYesNoSelect(s,SelectContext::IsFirst,0);SelectOption first=s.options.at(first_choice);s.firstPlayer=first.type==SelectOptionType::Yes?s.selectPlayer:1-s.selectPlayer;s.clearSelect();for(int p:s.basicPlayerOrder())Draw(s,p,FIRST_HAND);auto& ps=s.players[target];for(CardRef ref:ps.hand)s.getCard(ref).cardId={filler_card_id};PreSetupActivePokemon(s,target);int error=0;int attempts=0;\n while(error==0 && s.selectType==SelectType::None){{if(attempts++>=64){{error=128;break;}}if(s.mulliganCount[target]<DECK_SIZE-FIRST_HAND-PRIZE_SIZE)s.mulliganCount[target]++;while(ps.hand.size()>0){{auto [ref,index]=MoveCardFromLast(ps.hand,ps.deck);(void)index;s.cardMoved(ref,AreaType::Deck);}}shuffle_philox(ps.deck,{seed}ull,stream,cursor);s.changed=true;Draw(s,target,FIRST_HAND);auto [hasBasic,hasDoll]=HasBasic(s,target);if(hasBasic){{s.mulligan[target]=false;s.pushFunction(AfterResetupActivePokemon,target);SetupActivePokemon(s,target);break;}}if(hasDoll){{s.pushFunction(AfterResetupActivePokemon,target);s.pushFunction(SetupActivePokemon,target);PreSetupActivePokemon(s,target);break;}}s.mulligan[target]=true;try{{SetupActivePokemon(s,target);}}catch(const std::runtime_error& e){{if(std::string(e.what())=="No Basic Pokemon.")error=64;else throw;}}}}\n auto emit=[](long long v){{std::cout<<v<<' ';}};emit(target);emit(s.mulliganCount[0]);emit(s.mulliganCount[1]);emit((int)s.mulligan[0]);emit((int)s.mulligan[1]);emit((int)ps.hand.size());emit((int)ps.deck.size());emit(s.moveCounter);emit((int)s.changed);emit((int)s.selectType);emit((int)s.selectContext);emit((int)s.selectPlayer);emit(s.selectMin);emit(s.selectMax);emit((int)s.options.size());int opcode=0,arg0=0;if(!s.functionStack.empty()){{const GameFunction& gf=s.functionStack.back();void* fp=FunctionTable.at(gf.functionIndex);opcode=fp==(void*)SelectedSetupActivePokemon?4:fp==(void*)SelectedMulligan?3:fp==(void*)SetupActivePokemon?6:fp==(void*)AfterResetupActivePokemon?5:0;arg0=gf.arg0;}}emit(1+(int)s.functionStack.size());emit(opcode);emit(arg0);emit(error);emit((long long)(cursor&0xffffffffull));emit((long long)(cursor>>32));for(int i=0;i<7;++i){{CardRef ref=ps.hand[i];emit((int)ref.cardIndex);emit(s.getCard(ref).cardId);}}for(int i=0;i<7;++i){{if(i<(int)s.options.size()){{const auto&o=s.options[i];emit((int)o.type);emit(o.param0);emit(o.param1);emit(o.param2);emit(o.param3);emit(o.param4);}}else for(int f=0;f<6;++f)emit(-1);}}for(int i=0;i<6;++i)emit((int)ps.deck[ps.deck.size()-1-i].cardIndex);emit((int)s.firstPlayer);emit((int)s.setupDone[target]);emit((int)ps.prize.size());std::cout<<'\\n';}}}}\n"""
    input_text = "\n".join(f"{first} {target} {stream}" for first, target, stream in rows) + "\n"
    with tempfile.TemporaryDirectory(prefix="gpu-cabt-resetup-loop-") as tmp:
        cpp, exe = Path(tmp) / "probe.cpp", Path(tmp) / "probe"
        cpp.write_text(source, encoding="utf-8")
        subprocess.run(
            ["g++", "-std=c++23", "-O2", "-I", str(official_dir), str(cpp), "-o", str(exe)],
            check=True,
        )
        completed = subprocess.run(
            [str(exe)], input=input_text, text=True, capture_output=True, check=True
        )
    values = [int(value) for value in completed.stdout.split()]
    expected = len(rows) * _SNAPSHOT_SIZE
    if len(values) != expected:
        raise RuntimeError(
            f"official snapshot ints {len(values)} != {expected}; stderr={completed.stderr}"
        )
    return np.asarray(values, dtype=np.int32).reshape(len(rows), _SNAPSHOT_SIZE)


def main() -> int:
    args = _parse_args()
    if not 0 < args.differential_envs <= args.env_count:
        raise ValueError("differential-envs must be in (0, env-count]")
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
        "src/ptcg_rl/gpu_cabt/native/runtime_state.h",
        "src/ptcg_rl/gpu_cabt/native/card_static.h",
        "src/ptcg_rl/gpu_cabt/cuda/rng_shuffle.cu",
        "src/ptcg_rl/gpu_cabt/cuda/battle_init.cu",
        "src/ptcg_rl/gpu_cabt/cuda/setup_is_first.cu",
        "src/ptcg_rl/gpu_cabt/cuda/card_move.cu",
        "src/ptcg_rl/gpu_cabt/cuda/opening_draw.cu",
        "src/ptcg_rl/gpu_cabt/cuda/pre_setup_active.cu",
        "src/ptcg_rl/gpu_cabt/cuda/setup_active.cu",
        "src/ptcg_rl/gpu_cabt/cuda/open_return_shuffle.cu",
        "src/ptcg_rl/gpu_cabt/cuda/resetup_active_once.cu",
        "src/ptcg_rl/gpu_cabt/cuda/resetup_until_selection.cu",
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
        "gpu_cabt_resetup_until_selection",
        "gpu_cabt_resetup_until_selection_snapshot",
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
    module.get_function("gpu_cabt_resetup_until_selection")(
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
    module.get_function("gpu_cabt_resetup_until_selection_snapshot")(
        (blocks,), (threads,), (states, runtimes, targets_d, snapshots, np.int32(args.env_count))
    )
    cp.cuda.Stream.null.synchronize()
    actual = cp.asnumpy(snapshots)
    rows = [
        (int(first[i]), int(targets[i]), args.stream_base + i)
        for i in range(args.differential_envs)
    ]
    official = _official_snapshots(repo_root, deck0, deck1, rows, filler, args.seed)
    differential_match = bool(np.array_equal(actual[: args.differential_envs], official))
    errors_clear = bool(np.all(actual[:, 18] == 0))
    active_boundaries = bool(np.all(actual[:, 9] == 2) and np.all(actual[:, 14] > 0))
    target_counts = np.where(targets == 0, actual[:, 1], actual[:, 2])
    max_mulligan_count = int(np.max(target_counts))
    mean_mulligan_count = float(np.mean(target_counts))
    option_count_min = int(np.min(actual[:, 14]))
    option_count_max = int(np.max(actual[:, 14]))
    free_vram, total_vram = cp.cuda.runtime.memGetInfo()
    name = cp.cuda.runtime.getDeviceProperties(0)["name"]
    name = name.decode() if isinstance(name, bytes) else str(name)
    print(
        json.dumps(
            {
                "device": name,
                "env_count": args.env_count,
                "differential_envs": args.differential_envs,
                "differential_match": differential_match,
                "runtime_errors_clear": errors_clear,
                "all_active_selection_boundaries": active_boundaries,
                "max_mulligan_count": max_mulligan_count,
                "mean_mulligan_count": mean_mulligan_count,
                "option_count_min": option_count_min,
                "option_count_max": option_count_max,
                "state_bytes_per_env": state_size,
                "runtime_bytes_per_env": runtime_size,
                "free_vram_bytes": int(free_vram),
                "total_vram_bytes": int(total_vram),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if differential_match and errors_clear and active_boundaries else 1


if __name__ == "__main__":
    raise SystemExit(main())
