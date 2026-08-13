from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np

from ptcg_rl.gpu_cabt.card_static import dense_setup_card_table, extract_setup_card_static
from ptcg_rl.gpu_cabt.nvrtc import load_cupy_module
from ptcg_rl.gpu_cabt.rng import shuffle_in_place


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GPU CABT opening-hand setup-profile differential")
    parser.add_argument("--deck0", type=Path, required=True)
    parser.add_argument("--deck1", type=Path, required=True)
    parser.add_argument("--env-count", type=int, default=8192)
    parser.add_argument("--differential-envs", type=int, default=2048)
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


def _card_id_for_ref(ref: int, deck0: list[int], deck1: list[int]) -> int:
    if 3 <= ref <= 62:
        return deck0[ref - 3]
    if 63 <= ref <= 122:
        return deck1[ref - 63]
    raise ValueError(f"unexpected physical card ref {ref}")


def _expected_profile(
    *,
    deck0: list[int],
    deck1: list[int],
    dense: np.ndarray,
    seed: int,
    stream: int,
) -> np.ndarray:
    ref_decks = [list(range(62, 2, -1)), list(range(122, 62, -1))]
    draw_index = shuffle_in_place(ref_decks[0], seed=seed, stream=stream, draw_index=0)
    shuffle_in_place(ref_decks[1], seed=seed, stream=stream, draw_index=draw_index)
    hands: list[list[int]] = [[], []]
    for player in range(2):
        for _ in range(7):
            hands[player].append(ref_decks[player].pop())

    result: list[int] = []
    for player, hand in enumerate(hands):
        ids = [_card_id_for_ref(ref, deck0, deck1) for ref in hand]
        hand_meta = dense[np.asarray(ids, dtype=np.int32)]
        deck_ids = [_card_id_for_ref(ref, deck0, deck1) for ref in ref_decks[player]]
        deck_meta = dense[np.asarray(deck_ids, dtype=np.int32)]
        active_mask = sum(int(row[3]) << index for index, row in enumerate(hand_meta))
        result.extend(
            (
                int(np.any(hand_meta[:, 0])),
                int(np.any(hand_meta[:, 1])),
                int(np.sum(hand_meta[:, 3])),
                active_mask,
                int(np.sum(deck_meta[:, 0])),
            )
        )
    return np.asarray(result, dtype=np.int32)


def main() -> int:
    args = _parse_args()
    if args.env_count <= 0 or args.differential_envs <= 0 or args.differential_envs > args.env_count:
        raise ValueError("invalid environment counts")

    import cupy as cp

    repo_root = Path(__file__).resolve().parents[1]
    deck0 = _load_deck(args.deck0)
    deck1 = _load_deck(args.deck1)
    engine_root = repo_root / "private/assets/official/ptcg_engine/ptcgProgram 22"
    records = extract_setup_card_static(engine_root)
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
        "src/ptcg_rl/gpu_cabt/cuda/setup_hand_profile.cu",
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
            "gpu_cabt_setup_hand_profile",
        ),
    )
    state_size_kernel = module.get_function("gpu_cabt_battle_core_size")
    runtime_size_kernel = module.get_function("gpu_cabt_runtime_size")
    init_kernel = module.get_function("gpu_cabt_init_battles")
    setup_kernel = module.get_function("gpu_cabt_setup_is_first")
    opening_kernel = module.get_function("gpu_cabt_opening_draw_after_is_first")
    profile_kernel = module.get_function("gpu_cabt_setup_hand_profile")

    state_size_out = cp.empty(1, dtype=cp.uint64)
    runtime_size_out = cp.empty(1, dtype=cp.uint64)
    state_size_kernel((1,), (1,), (state_size_out,))
    runtime_size_kernel((1,), (1,), (runtime_size_out,))
    cp.cuda.Stream.null.synchronize()
    state_size = int(cp.asnumpy(state_size_out)[0])
    runtime_size = int(cp.asnumpy(runtime_size_out)[0])

    pair = np.asarray(deck0 + deck1, dtype=np.int32)
    device_decks = cp.asarray(np.tile(pair, (args.env_count, 1)))
    selected_host = np.arange(args.env_count, dtype=np.int32) & 1
    selected_device = cp.asarray(selected_host)
    card_table_device = cp.asarray(dense)
    raw_states = cp.empty(args.env_count * state_size, dtype=cp.uint8)
    raw_runtimes = cp.empty(args.env_count * runtime_size, dtype=cp.uint8)
    profiles = cp.empty((args.env_count, 10), dtype=cp.int32)
    threads = 128
    blocks = (args.env_count + threads - 1) // threads

    init_kernel((blocks,), (threads,), (raw_states, device_decks, np.int32(args.env_count)))
    setup_kernel(
        (blocks,),
        (threads,),
        (raw_states, raw_runtimes, np.uint64(args.seed), np.uint64(args.stream_base), np.int32(args.env_count)),
    )
    opening_kernel(
        (blocks,), (threads,), (raw_states, raw_runtimes, selected_device, np.int32(args.env_count))
    )
    profile_kernel(
        (blocks,),
        (threads,),
        (raw_states, card_table_device, np.int32(row_count), profiles, np.int32(args.env_count)),
    )
    cp.cuda.Stream.null.synchronize()
    actual = cp.asnumpy(profiles)

    differential_match = True
    for env_index in range(args.differential_envs):
        expected = _expected_profile(
            deck0=deck0,
            deck1=deck1,
            dense=dense,
            seed=args.seed,
            stream=args.stream_base + env_index,
        )
        if not np.array_equal(actual[env_index], expected):
            differential_match = False
            break
    invalid_rows = int(np.sum(np.any(actual < 0, axis=1)))
    player0_mulligan_candidates = int(np.sum((actual[:, 0] == 0) & (actual[:, 1] == 0)))
    player1_mulligan_candidates = int(np.sum((actual[:, 5] == 0) & (actual[:, 6] == 0)))

    free_vram, total_vram = cp.cuda.runtime.memGetInfo()
    device_name = cp.cuda.runtime.getDeviceProperties(0)["name"]
    if isinstance(device_name, bytes):
        device_name = device_name.decode()
    report = {
        "device": str(device_name),
        "env_count": args.env_count,
        "differential_envs": args.differential_envs,
        "differential_match": differential_match,
        "invalid_rows": invalid_rows,
        "player0_mulligan_candidates": player0_mulligan_candidates,
        "player1_mulligan_candidates": player1_mulligan_candidates,
        "card_table_bytes": len(dense_bytes),
        "state_bytes_per_env": state_size,
        "runtime_bytes_per_env": runtime_size,
        "free_vram_bytes": int(free_vram),
        "total_vram_bytes": int(total_vram),
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if differential_match and invalid_rows == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
