from __future__ import annotations

import json
import pstats
import resource
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from statistics import mean
from typing import Any

from .evidence import (
    git_state,
    platform_record,
    sha256_file,
    source_tree_hash,
    technical_run_envelope,
    unique_run_id,
    write_immutable_json,
)
from .models import stable_hash
from .native import NativeCABTTransport, load_deck


def run_raw_match(args, repo: Path) -> dict[str, Any]:
    process_started = time.process_time()
    wall_started = time.monotonic()
    transport = NativeCABTTransport(args.engine_root.resolve(strict=True))
    deck = load_deck(args.default_deck.resolve(strict=True))
    raw = transport.start(deck, deck)
    requests = 0
    first_player = None
    latencies: list[float] = []
    failure = None
    try:
        while raw["current"]["result"] == -1:
            if requests >= args.request_cap or time.monotonic() - wall_started >= args.game_timeout:
                raise TimeoutError("raw benchmark cap reached")
            if raw["current"].get("firstPlayer") in (0, 1):
                first_player = raw["current"]["firstPlayer"]
            selected = list(range(raw["select"]["maxCount"]))
            selected_started = time.perf_counter()
            raw = transport.select(selected)
            latencies.append((time.perf_counter() - selected_started) * 1_000)
            requests += 1
        result = raw["current"]["result"]
    except Exception as error:
        result = None
        failure = type(error).__name__
    finally:
        transport.finish()
    return {
        "status": "pass" if result is not None and failure is None else "fail",
        "game_id": args.game_id,
        "summary": {"terminal_result": result, "engine_requests": requests,
                    "first_player": first_player, "failure_kind": failure,
                    "invalid_selections": 0, "fallback_actions": 0,
                    "post_terminal_actions": 0},
        "action_latencies_ms": latencies,
        "process_metrics": {
            "cpu_seconds": time.process_time() - process_started,
            "wall_seconds": time.monotonic() - wall_started,
            "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        },
    }


def _percentile(values: list[float], fraction: float) -> float | None:
    values.sort()
    return values[min(len(values) - 1, int(fraction * (len(values) - 1)))] if values else None


def _point(mode: str, workers: int, args, repo: Path, run_dir: Path) -> dict[str, Any]:
    engine_root = args.engine_root.resolve(strict=True)
    card_data = args.card_data.resolve(strict=True)
    default_deck = args.default_deck.resolve(strict=True)
    private_baselines = args.private_baselines.resolve(strict=True)
    executable = str(Path(sys.executable).with_name("ptcg"))

    def execute(game: int) -> dict[str, Any]:
        game_id = f"{mode}-w{workers}-{game:05d}-{uuid.uuid4().hex[:8]}"
        common = ["--engine-root", str(engine_root), "--default-deck", str(default_deck),
                  "--game-id", game_id, "--request-cap", str(args.request_cap),
                  "--game-timeout", str(args.game_timeout)]
        if mode == "raw-engine":
            command = [executable, "g1", "raw-one", *common]
        else:
            policy = args.rule_policy if mode == "rule-policy" else "first"
            command = [
                executable, "g1", "arena-one", *common,
                "--card-data", str(card_data), "--private-baselines", str(private_baselines),
                "--policy0", policy, "--policy1", policy, "--seed", str(args.seed + game),
                "--failure-directory", str(run_dir / "failures" / game_id),
            ]
        try:
            completed = subprocess.run(command, cwd=repo, text=True, capture_output=True,
                                       timeout=args.game_timeout + 10, check=False)
        except subprocess.TimeoutExpired:
            return {"status": "fail", "game_id": game_id, "failure_kind": "process_timeout"}
        if completed.returncode:
            return {"status": "fail", "game_id": game_id, "failure_kind": "worker_exit",
                    "stderr": completed.stderr[-500:]}
        return json.loads(completed.stdout)

    started = time.monotonic()
    records: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(execute, game) for game in range(args.games_per_point)]
        for future in as_completed(futures):
            record = future.result()
            records.append(record)
            write_immutable_json(
                run_dir / "matches" / mode / f"workers-{workers}" / f"{record['game_id']}.json",
                record,
            )
    wall = time.monotonic() - started
    complete = [record for record in records if "summary" in record]
    latencies = [value for record in complete for value in record["action_latencies_ms"]]
    choices = sum(record["summary"]["engine_requests"] for record in complete)
    result = {
        "mode": mode,
        "workers": workers,
        "games_requested": args.games_per_point,
        "games_completed": sum(record["summary"]["terminal_result"] is not None for record in complete),
        "failures": sum(record["status"] != "pass" for record in records),
        "engine_requests": choices,
        "games_per_second": len(complete) / wall,
        "choices_per_second": choices / wall,
        "action_latency_ms": {"p50": _percentile(latencies.copy(), 0.50),
                              "p95": _percentile(latencies.copy(), 0.95),
                              "p99": _percentile(latencies.copy(), 0.99)},
        "cpu_percent": 100 * sum(
            record["process_metrics"]["cpu_seconds"] for record in complete
        ) / wall,
        "peak_rss_bytes": max(
            (record["process_metrics"]["peak_rss_bytes"] for record in complete), default=0
        ),
        "mean_requests_per_game": mean(
            [record["summary"]["engine_requests"] for record in complete]
        ) if complete else None,
        "wall_seconds": wall,
    }
    write_immutable_json(run_dir / f"{mode}-workers-{workers}.json", result)
    return result


def run_benchmark(args, repo: Path) -> dict[str, Any]:
    workers = tuple(int(value) for value in args.workers.split(","))
    if workers != (1, 2, 4, 8):
        raise ValueError("G1R benchmark workers must be exactly 1,2,4,8")
    if args.games_per_point <= 0:
        raise ValueError("games-per-point must be positive")
    run_id = unique_run_id("g1r-throughput")
    run_dir = (args.output or repo / "runs" / run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    engine_root = args.engine_root.resolve(strict=True)
    card_data = args.card_data.resolve(strict=True)
    default_deck = args.default_deck.resolve(strict=True)
    config = {
        "workers": workers, "games_per_point": args.games_per_point,
        "rule_policy": args.rule_policy, "request_cap": args.request_cap,
        "game_timeout": args.game_timeout, "seed": args.seed, "training": False,
    }
    points = [
        _point(mode, worker_count, args, repo, run_dir)
        for worker_count in workers
        for mode in ("raw-engine", "encoded-observation", "rule-policy")
    ]
    ratios = {}
    for worker_count in workers:
        raw = next(point for point in points if point["workers"] == worker_count
                   and point["mode"] == "raw-engine")
        encoded = next(point for point in points if point["workers"] == worker_count
                       and point["mode"] == "encoded-observation")
        ratios[str(worker_count)] = encoded["choices_per_second"] / raw["choices_per_second"]
    complete = all(point["games_completed"] == args.games_per_point and point["failures"] == 0
                   for point in points)
    needs_profile = any(ratio < 0.70 for ratio in ratios.values())
    profile_sha256 = None
    if args.profile_evidence:
        profile_path = args.profile_evidence.resolve(strict=True)
        profile = pstats.Stats(str(profile_path))
        if not any(function == "semantic_snapshot" for _, _, function in profile.stats):
            raise ValueError("profile evidence does not contain encoded observation work")
        profile_sha256 = sha256_file(profile_path)
    passed = complete and (not needs_profile or profile_sha256 is not None)
    manifest_path = run_dir / "run_manifest.json"
    manifest = {
        **technical_run_envelope(repo, manifest_path, run_id, "ptcg.g1r.benchmark", passed),
        "failure_reason": "PROFILE_REQUIRED" if complete and needs_profile and not profile_sha256 else
                          "INCOMPLETE_OR_FAILED_GAMES" if not complete else None,
        "games_per_point": args.games_per_point,
        "points": points,
        "encoded_to_raw_choices_per_second_ratio": ratios,
        "profile_required": needs_profile,
        "profile_evidence_sha256": profile_sha256,
        "config": config, "config_sha256": stable_hash(config),
        "repository": git_state(repo), "platform": platform_record(),
        "source_sha256": source_tree_hash(repo), "command": list(sys.argv),
        "loaded_artifacts": {
            "engine_library": sha256_file(engine_root / "cg" / "libcg.so"),
            "game_wrapper": sha256_file(engine_root / "cg" / "game.py"),
            "card_data": sha256_file(card_data), "default_deck": sha256_file(default_deck),
        },
        "training_performed": False, "local_cost_usd": 0.0,
    }
    write_immutable_json(manifest_path, manifest)
    (run_dir / "run_manifest.json.sha256").write_text(
        f"{sha256_file(manifest_path)}  run_manifest.json\n", encoding="ascii"
    )
    return manifest
