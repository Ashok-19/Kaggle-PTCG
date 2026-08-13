from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from ptcg_rl.gpu_cabt.device_runtime import GpuCabtRuntime


DEFAULT_LUCARIO = Path(".chatgpt/tmp/today-lucario-variants/lucario-modern-v1/deck.csv")
DEFAULT_OPPONENTS = (
    ("dragapult", Path(".chatgpt/tmp/aura-upgrade/arena-agents/dragapult-ex/deck.csv")),
    ("alakazam", Path(".chatgpt/tmp/grim-source-oracle/arena-agents/alakazam-v9/deck.csv")),
    ("lopunny", Path(".chatgpt/tmp/grim-source-oracle/arena-agents/lopunny-v9/deck.csv")),
    ("iono", Path(".chatgpt/tmp/aura-upgrade/arena-agents/iono/deck.csv")),
    ("abomasnow", Path(".chatgpt/tmp/aura-upgrade/arena-agents/mega-abomasnow-ex/deck.csv")),
    ("grim", Path(".chatgpt/tmp/grim-lana-current-eval-agents/grim-v15-control/deck.csv")),
)


def _load_deck(repo_root: Path, relative_path: Path) -> np.ndarray:
    path = repo_root / relative_path
    deck = np.loadtxt(path, dtype=np.int32)
    if deck.shape != (60,):
        raise ValueError(f"expected a 60-card deck at {path}, got shape {deck.shape}")
    return deck


def _build_matchups(
    repo_root: Path,
    repeats: int,
    families: set[str] | None = None,
) -> tuple[np.ndarray, list[str]]:
    lucario = _load_deck(repo_root, DEFAULT_LUCARIO)
    selected = [
        (name, path)
        for name, path in DEFAULT_OPPONENTS
        if families is None or name in families
    ]
    if not selected:
        raise ValueError("no opponent families selected")
    rows: list[np.ndarray] = []
    labels: list[str] = []
    for repeat in range(repeats):
        suffix = f":r{repeat}" if repeats > 1 else ""
        for name, path in selected:
            opponent = _load_deck(repo_root, path)
            rows.append(np.stack((lucario, opponent)))
            labels.append(f"{name}:luc-p0{suffix}")
            rows.append(np.stack((opponent, lucario)))
            labels.append(f"{name}:luc-p1{suffix}")
    return np.stack(rows).astype(np.int32, copy=False), labels


def run(args: argparse.Namespace) -> dict[str, object]:
    repo_root = Path(__file__).resolve().parents[1]
    families = set(args.family) if args.family else None
    known_families = {name for name, _ in DEFAULT_OPPONENTS}
    unknown_families = sorted((families or set()) - known_families)
    if unknown_families:
        raise ValueError(f"unknown opponent families: {unknown_families}")
    decks, labels = _build_matchups(repo_root, args.repeats, families)
    env_count = len(labels)

    init_start = time.perf_counter()
    runtime = GpuCabtRuntime(env_count, stack_size_bytes=args.stack_bytes)
    runtime.reset(decks, seed=args.seed)
    runtime.synchronize()
    init_seconds = time.perf_counter() - init_start

    selected_indices = np.broadcast_to(
        np.arange(runtime.abi.selected_capacity, dtype=np.int32),
        (env_count, runtime.abi.selected_capacity),
    ).copy()
    event_totals = np.zeros(env_count, dtype=np.int64)
    terminal_seen = np.zeros(env_count, dtype=bool)
    failure: dict[str, object] | None = None
    boundaries = 0

    run_start = time.perf_counter()
    for boundary in range(args.max_boundaries):
        status = runtime.status()
        runtime.synchronize()
        errors = status.error_flags.get()
        results = status.game_results.get()
        select_types = status.select_types.get()
        turns = status.turns.get()
        active = (results == 0) & (errors == 0)

        bad_runtime = np.flatnonzero(errors != 0)
        if bad_runtime.size:
            failure = {
                "kind": "runtime",
                "boundary": boundary,
                "envs": [
                    {
                        "label": labels[index],
                        "error": int(errors[index]),
                        "result": int(results[index]),
                        "select_type": int(select_types[index]),
                        "turn": int(turns[index]),
                    }
                    for index in bad_runtime
                ],
            }
            break

        stalled = np.flatnonzero(active & (select_types == 0))
        if stalled.size:
            failure = {
                "kind": "active-without-selection",
                "boundary": boundary,
                "envs": [labels[index] for index in stalled],
            }
            break

        if not np.any(active):
            boundaries = boundary
            break

        events = runtime.project_events(acknowledge=True)
        projection = runtime.project_policy()
        runtime.synchronize()
        event_counts = events.counts.get()
        event_status = events.status.get()
        globals_host = projection.globals.get()
        option_counts = projection.option_counts.get()
        projection_status = projection.status.get()
        event_totals += event_counts
        terminal_seen |= results != 0

        bad_projection: list[dict[str, object]] = []
        for index in np.flatnonzero(active):
            minimum = int(globals_host[index, 8])
            maximum = int(globals_host[index, 9])
            options = int(option_counts[index])
            if (
                int(event_status[index]) != 0
                or int(projection_status[index]) != 0
                or minimum < 0
                or minimum > maximum
                or minimum > options
            ):
                bad_projection.append(
                    {
                        "label": labels[index],
                        "event_status": int(event_status[index]),
                        "projection_status": int(projection_status[index]),
                        "select_type": int(select_types[index]),
                        "min": minimum,
                        "max": maximum,
                        "option_count": options,
                        "turn": int(turns[index]),
                    }
                )
        if bad_projection:
            failure = {
                "kind": "projection",
                "boundary": boundary,
                "envs": bad_projection,
            }
            break

        response_present = (active & (select_types != 0)).astype(np.uint8)
        selected_counts = np.where(
            response_present != 0, globals_host[:, 8], 0
        ).astype(np.int32)
        runtime.step(response_present, selected_counts, selected_indices)
        runtime.synchronize()
        boundaries = boundary + 1
    else:
        failure = {"kind": "boundary-limit", "boundary": args.max_boundaries}

    final_status = runtime.status()
    final_events = runtime.project_events(acknowledge=False)
    runtime.synchronize()
    final_errors = final_status.error_flags.get()
    final_results = final_status.game_results.get()
    final_select_types = final_status.select_types.get()
    final_select_players = final_status.select_players.get()
    final_turns = final_status.turns.get()
    final_event_counts = final_events.counts.get()
    final_event_status = final_events.status.get()
    for index in range(env_count):
        if not terminal_seen[index] and final_results[index] != 0:
            event_totals[index] += final_event_counts[index]

    run_seconds = time.perf_counter() - run_start
    games = [
        {
            "label": labels[index],
            "error": int(final_errors[index]),
            "result": int(final_results[index]),
            "turn": int(final_turns[index]),
            "last_select_type": int(final_select_types[index]),
            "last_select_player": int(final_select_players[index]),
            "events": int(event_totals[index]),
            "final_event_count": int(final_event_counts[index]),
            "final_event_status": int(final_event_status[index]),
        }
        for index in range(env_count)
    ]
    all_terminal = bool(np.all(final_results != 0))
    zero_errors = bool(np.all(final_errors == 0) and np.all(final_event_status == 0))
    passed = failure is None and all_terminal and zero_errors
    return {
        "status": "PASS" if passed else "FAIL",
        "seed": args.seed,
        "env_count": env_count,
        "repeats": args.repeats,
        "families": sorted(families) if families is not None else "all",
        "stack_bytes": args.stack_bytes,
        "boundaries": boundaries,
        "all_terminal": all_terminal,
        "zero_errors": zero_errors,
        "failure": failure,
        "init_seconds": init_seconds,
        "run_seconds": run_seconds,
        "memory_bytes": runtime.memory_bytes(),
        "abi": runtime.abi.__dict__,
        "games": games,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20260814)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument(
        "--family",
        action="append",
        choices=tuple(name for name, _ in DEFAULT_OPPONENTS),
        help="limit qualification to one or more opponent families",
    )
    parser.add_argument("--max-boundaries", type=int, default=5000)
    parser.add_argument("--stack-bytes", type=int, default=16 * 1024)
    args = parser.parse_args()
    if args.repeats <= 0:
        parser.error("--repeats must be positive")
    result = run(args)
    print(json.dumps(result, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
