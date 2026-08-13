from __future__ import annotations

import argparse
import csv
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from ptcg_rl.gpu_cabt.nvrtc import load_cupy_module

_SNAPSHOT_SIZE = 46


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CABT CPU vs CUDA TurnStart-frame differential")
    parser.add_argument("--deck0", type=Path, required=True)
    parser.add_argument("--deck1", type=Path, required=True)
    parser.add_argument("--env-count", type=int, default=256)
    return parser.parse_args()


def _load_deck(path: Path) -> list[int]:
    values: list[int] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.reader(handle):
            values.extend(int(value) for value in row if value.strip())
    if len(values) != 60:
        raise ValueError(f"{path} must contain exactly 60 card IDs")
    return values


def _official(repo_root: Path, deck0: list[int], deck1: list[int], count: int) -> np.ndarray:
    official = repo_root / "private/assets/official/ptcg_engine/ptcgProgram 22"
    d0 = ",".join(map(str, deck0))
    d1 = ",".join(map(str, deck1))
    source = f'''#include <iostream>\n#include "All.h"\nint main(){{InitializeAll();GameConfig c={{}};c.recordLog=false;c.deviceRand=false;const int d0[60]={{{d0}}};const int d1[60]={{{d1}}};for(int i=0;i<60;++i){{c.decks[0].cards[i]=d0[i];c.decks[1].cards[i]=d1[i];}}for(int e=0;e<{count};++e){{BattleData b;b.init(c);State&s=b.state;s.turn=e%5;s.turnActionCount=70+e;s.firstPlayer=e&1;s.phase=(GamePhase)0;for(int p=0;p<2;++p){{auto&ps=s.players[p];if(ps.active.empty()){{CardRef r(p==0?3:63);ps.active.push_back(r);s.getCard(r).area=AreaType::Active;}}ps.thisTurn.value=0x11110000u+(unsigned)(p*0x100+e);ps.nextTurn.value=0x22220000u+(unsigned)(p*0x100+e);Card&card=s.getCard(ps.active[0]);card.takeAttackDamageThisTurn=300+p*10+e;card.takeAttackDamagePreTurn=-1;for(int w=0;w<4;++w){{card.thisTurn.value[w]=0x10000000u+p*0x10000u+w*0x100u+e;card.nextTurn.value[w]=0x20000000u+p*0x10000u+w*0x100u+e;}}card.thisTurnEnemy.value[0]=0x30000000u+p*0x10000u+e;card.nextTurnEnemy.value[0]=0x40000000u+p*0x10000u+e;}}for(int h=0;h<3;++h){{s.turnHistories[h].turnAttackId=1000+h*100+e;s.turnHistories[h].takePrizeCountTurnPlayer=h+1;}}s.turn++;s.turnActionCount=0;int ap=s.activePlayerIndex();s.phase=GamePhase::Main;s.turnUsedSkill.clear();s.turnPlay.clear();s.turnHeal.clear();s.turnEvolve.clear();s.turnHistories[2]=s.turnHistories[1];s.turnHistories[1]=s.turnHistories[0];s.turnHistories[0]={{}};for(CardRef r:s.stadium)s.getCard(r).turnStart(ap);for(int p:s.basicPlayerOrder()){{auto&ps=s.players[p];ps.turnStart(ap);for(CardRef r:ps.active)s.getCard(r).turnStart(ap);for(CardRef r:ps.bench)s.getCard(r).turnStart(ap);}}auto emit=[](long long v){{std::cout<<v<<' ';}};emit(s.turn);emit(s.turnActionCount);emit((int)s.phase);emit(ap);emit(0);emit(0);emit(0);emit(0);emit(0);for(int h=0;h<3;++h){{emit(s.turnHistories[h].turnAttackId);emit(s.turnHistories[h].takePrizeCountTurnPlayer);}}for(int p=0;p<2;++p){{auto&ps=s.players[p];emit((int)ps.thisTurn.value);emit((int)ps.nextTurn.value);Card&card=s.getCard(ps.active[0]);emit(card.takeAttackDamageThisTurn);emit(card.takeAttackDamagePreTurn);for(int w=0;w<4;++w)emit((int)card.thisTurn.value[w]);for(int w=0;w<4;++w)emit((int)card.nextTurn.value[w]);emit((int)card.thisTurnEnemy.value[0]);emit((int)card.nextTurnEnemy.value[0]);}}for(int z=0;z<3;++z)emit(0);std::cout<<'\\n';}}}}'''
    with tempfile.TemporaryDirectory(prefix="gpu-cabt-turn-start-") as tmp:
        cpp, exe = Path(tmp) / "probe.cpp", Path(tmp) / "probe"
        cpp.write_text(source, encoding="utf-8")
        subprocess.run(
            ["g++", "-std=c++23", "-O2", "-I", str(official), str(cpp), "-o", str(exe)],
            check=True,
        )
        output = subprocess.check_output([str(exe)], text=True)
    values = np.asarray([int(value) for value in output.split()], dtype=np.int64)
    expected = count * _SNAPSHOT_SIZE
    if values.size != expected:
        raise RuntimeError(f"official snapshot ints {values.size} != {expected}")
    return values.astype(np.int32).reshape(count, _SNAPSHOT_SIZE)


def main() -> int:
    args = _parse_args()
    import cupy as cp

    repo_root = Path(__file__).resolve().parents[1]
    deck0, deck1 = _load_deck(args.deck0), _load_deck(args.deck1)
    source = "\n".join(
        (repo_root / path).read_text(encoding="utf-8")
        for path in (
            "src/ptcg_rl/gpu_cabt/native/state_core.h",
            "src/ptcg_rl/gpu_cabt/native/runtime_state.h",
            "src/ptcg_rl/gpu_cabt/cuda/rng_shuffle.cu",
            "src/ptcg_rl/gpu_cabt/cuda/battle_init.cu",
            "src/ptcg_rl/gpu_cabt/cuda/setup_is_first.cu",
            "src/ptcg_rl/gpu_cabt/cuda/turn_start_frame.cu",
        )
    )
    module = load_cupy_module(
        cp,
        source,
        kernel_names=(
            "gpu_cabt_battle_core_size",
            "gpu_cabt_runtime_size",
            "gpu_cabt_init_battles",
            "gpu_cabt_setup_is_first",
            "gpu_cabt_force_turn_start_case",
            "gpu_cabt_turn_start_frame",
            "gpu_cabt_turn_start_frame_snapshot",
        ),
    )
    state_size_out = cp.empty(1, dtype=cp.uint64)
    runtime_size_out = cp.empty(1, dtype=cp.uint64)
    module.get_function("gpu_cabt_battle_core_size")((1,), (1,), (state_size_out,))
    module.get_function("gpu_cabt_runtime_size")((1,), (1,), (runtime_size_out,))
    cp.cuda.Stream.null.synchronize()
    state_size = int(cp.asnumpy(state_size_out)[0])
    runtime_size = int(cp.asnumpy(runtime_size_out)[0])
    decks = cp.asarray(np.tile(np.asarray(deck0 + deck1, dtype=np.int32), (args.env_count, 1)))
    states = cp.empty(args.env_count * state_size, dtype=cp.uint8)
    runtimes = cp.empty(args.env_count * runtime_size, dtype=cp.uint8)
    snapshots = cp.empty((args.env_count, _SNAPSHOT_SIZE), dtype=cp.int32)
    threads, blocks = 128, (args.env_count + 127) // 128
    module.get_function("gpu_cabt_init_battles")((blocks,), (threads,), (states, decks, np.int32(args.env_count)))
    module.get_function("gpu_cabt_setup_is_first")(
        (blocks,),
        (threads,),
        (states, runtimes, np.uint64(1), np.uint64(100), np.int32(args.env_count)),
    )
    module.get_function("gpu_cabt_force_turn_start_case")(
        (blocks,), (threads,), (states, runtimes, np.int32(args.env_count))
    )
    module.get_function("gpu_cabt_turn_start_frame")(
        (blocks,), (threads,), (states, runtimes, np.int32(args.env_count))
    )
    module.get_function("gpu_cabt_turn_start_frame_snapshot")(
        (blocks,), (threads,), (states, runtimes, snapshots, np.int32(args.env_count))
    )
    cp.cuda.Stream.null.synchronize()
    actual = cp.asnumpy(snapshots)
    expected = _official(repo_root, deck0, deck1, args.env_count)
    match = bool(np.array_equal(actual, expected))
    errors_clear = bool(np.all(actual[:, 4] == 0))
    print(
        {
            "env_count": args.env_count,
            "differential_match": match,
            "runtime_errors_clear": errors_clear,
            "state_bytes_per_env": state_size,
            "runtime_bytes_per_env": runtime_size,
        }
    )
    return 0 if match and errors_clear else 1


if __name__ == "__main__":
    raise SystemExit(main())
