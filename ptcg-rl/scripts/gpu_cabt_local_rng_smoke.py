from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from ptcg_rl.gpu_cabt.rng import shuffle_in_place


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Local CUDA RNG/shuffle differential smoke")
    parser.add_argument("--correctness-envs", type=int, default=256)
    parser.add_argument("--benchmark-envs", type=int, default=16384)
    parser.add_argument("--benchmark-repeats", type=int, default=20)
    parser.add_argument("--seed", type=int, default=0x123456789ABCDEF0)
    parser.add_argument("--stream-base", type=int, default=0xABC00000)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.correctness_envs <= 0 or args.benchmark_envs <= 0 or args.benchmark_repeats <= 0:
        raise ValueError("environment and repeat counts must be positive")

    import cupy as cp

    source_path = Path(__file__).resolve().parents[1] / "src/ptcg_rl/gpu_cabt/cuda/rng_shuffle.cu"
    source = source_path.read_text(encoding="utf-8")
    module = cp.RawModule(code=source, options=("--std=c++14",), name_expressions=("shuffle_decks",))
    kernel = module.get_function("shuffle_decks")

    properties = cp.cuda.runtime.getDeviceProperties(0)
    device_name = properties["name"]
    if isinstance(device_name, bytes):
        device_name = device_name.decode()
    free_before, total_bytes = cp.cuda.runtime.memGetInfo()

    deck_size = 60
    host_deck = np.arange(deck_size, dtype=np.int32)
    device_deck = cp.asarray(host_deck)

    correctness_out = cp.empty((args.correctness_envs, deck_size), dtype=cp.int32)
    threads = 128
    correctness_blocks = (args.correctness_envs + threads - 1) // threads
    kernel(
        (correctness_blocks,),
        (threads,),
        (
            device_deck,
            correctness_out,
            np.uint64(args.seed),
            np.uint64(args.stream_base),
            np.int32(args.correctness_envs),
            np.int32(deck_size),
        ),
    )
    cp.cuda.Stream.null.synchronize()
    first_gpu = cp.asnumpy(correctness_out)

    deterministic_out = cp.empty_like(correctness_out)
    kernel(
        (correctness_blocks,),
        (threads,),
        (
            device_deck,
            deterministic_out,
            np.uint64(args.seed),
            np.uint64(args.stream_base),
            np.int32(args.correctness_envs),
            np.int32(deck_size),
        ),
    )
    cp.cuda.Stream.null.synchronize()
    second_gpu = cp.asnumpy(deterministic_out)
    deterministic_replay = bool(np.array_equal(first_gpu, second_gpu))

    differential_match = True
    for env_index in range(args.correctness_envs):
        expected = list(range(deck_size))
        shuffle_in_place(expected, seed=args.seed, stream=args.stream_base + env_index)
        if not np.array_equal(first_gpu[env_index], np.asarray(expected, dtype=np.int32)):
            differential_match = False
            break

    permutation_valid = bool(
        np.all(np.sort(first_gpu, axis=1) == np.arange(deck_size, dtype=np.int32)[None, :])
    )

    benchmark_out = cp.empty((args.benchmark_envs, deck_size), dtype=cp.int32)
    benchmark_blocks = (args.benchmark_envs + threads - 1) // threads
    kernel(
        (benchmark_blocks,),
        (threads,),
        (
            device_deck,
            benchmark_out,
            np.uint64(args.seed),
            np.uint64(args.stream_base + 1_000_000),
            np.int32(args.benchmark_envs),
            np.int32(deck_size),
        ),
    )
    cp.cuda.Stream.null.synchronize()

    started = time.perf_counter()
    for repeat in range(args.benchmark_repeats):
        kernel(
            (benchmark_blocks,),
            (threads,),
            (
                device_deck,
                benchmark_out,
                np.uint64(args.seed + repeat),
                np.uint64(args.stream_base + 1_000_000),
                np.int32(args.benchmark_envs),
                np.int32(deck_size),
            ),
        )
    cp.cuda.Stream.null.synchronize()
    elapsed = time.perf_counter() - started

    free_after, _ = cp.cuda.runtime.memGetInfo()
    memory_pool_bytes = int(cp.get_default_memory_pool().total_bytes())
    report = {
        "device": str(device_name),
        "total_vram_bytes": int(total_bytes),
        "free_vram_before_bytes": int(free_before),
        "free_vram_after_bytes": int(free_after),
        "cupy_pool_bytes": memory_pool_bytes,
        "correctness_envs": args.correctness_envs,
        "differential_match": differential_match,
        "deterministic_replay": deterministic_replay,
        "permutation_valid": permutation_valid,
        "benchmark_envs": args.benchmark_envs,
        "benchmark_repeats": args.benchmark_repeats,
        "benchmark_seconds": elapsed,
        "deck_shuffles_per_second": (args.benchmark_envs * args.benchmark_repeats) / elapsed,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if differential_match and deterministic_replay and permutation_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
