from __future__ import annotations

import json
import math
import resource
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from statistics import mean, stdev
from typing import Any, Mapping

from .actions import DeterministicFirstLegalPolicy, RandomLegalPolicy
from .environment import DevelopmentEpisodeError, EpisodeEnvironmentV1, FailureMode
from .evidence import (
    git_state,
    platform_record,
    sha256_file,
    source_tree_hash,
    technical_run_envelope,
    unique_run_id,
    write_immutable_json,
)
from .models import SchemaMetadataV1, stable_hash
from .native import NativeCABTTransport, load_deck
from .rule_baseline import NativeRulePolicy


def _policy(spec: str, seed: int, default_deck: list[int], private_root: Path):
    if spec == "random":
        return RandomLegalPolicy(seed), default_deck
    if spec == "first":
        return DeterministicFirstLegalPolicy(), default_deck
    if spec.startswith("rule:"):
        policy = NativeRulePolicy(private_root / spec.split(":", 1)[1])
        return policy, policy.deck
    raise ValueError(f"unknown arena policy: {spec}")


def run_one_native_match(args, repo: Path) -> dict[str, Any]:
    process_started = time.process_time()
    wall_started = time.monotonic()
    engine_root = args.engine_root.resolve(strict=True)
    card_data = args.card_data.resolve(strict=True)
    default_deck = load_deck(args.default_deck.resolve(strict=True))
    transport = NativeCABTTransport(engine_root)
    policy0, deck0 = _policy(args.policy0, args.seed, default_deck, args.private_baselines)
    policy1, deck1 = _policy(args.policy1, args.seed + 1, default_deck, args.private_baselines)
    metadata = SchemaMetadataV1.build(sha256_file(transport.library_path), sha256_file(card_data))
    environment = EpisodeEnvironmentV1(
        transport,
        metadata,
        max_requests=args.request_cap,
        deadline_monotonic=time.monotonic() + args.game_timeout,
        failure_directory=args.failure_directory,
        failure_mode=FailureMode.DEVELOPMENT,
    )
    try:
        result = environment.run(args.game_id, deck0, deck1, {0: policy0, 1: policy1})
    except DevelopmentEpisodeError as error:
        result = error.result
    summary = asdict(result.summary)
    passed = summary["terminal_result"] is not None and all(
        summary[name] == 0
        for name in ("invalid_selections", "post_terminal_actions", "fallback_actions")
    ) and summary["failure_kind"] is None
    return {
        "status": "pass" if passed else "fail",
        "game_id": args.game_id,
        "policy0": args.policy0,
        "policy1": args.policy1,
        "seed_scope": "Python policy only; native trajectories are nondeterministic",
        "summary": summary,
        "action_latencies_ms": result.action_latencies_ms,
        "process_metrics": {
            "cpu_seconds": time.process_time() - process_started,
            "wall_seconds": time.monotonic() - wall_started,
            "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        },
    }


def _score_interval(values: list[float]) -> list[float]:
    if len(values) < 2:
        return [values[0], values[0]] if values else [0.0, 1.0]
    half = 1.96 * stdev(values) / math.sqrt(len(values))
    center = mean(values)
    return [max(0.0, center - half), min(1.0, center + half)]


def _aggregate(records: list[Mapping[str, Any]]) -> dict[str, Any]:
    cells: dict[str, list[Mapping[str, Any]]] = {}
    for record in records:
        cells.setdefault(f"{record['policy0']}__vs__{record['policy1']}", []).append(record)
    result: dict[str, Any] = {}
    for cell, games in sorted(cells.items()):
        scores = [
            1.0 if game["summary"]["terminal_result"] == 0 else
            0.5 if game["summary"]["terminal_result"] == 2 else 0.0
            for game in games if game["summary"]["terminal_result"] is not None
        ]
        result[cell] = {
            "games": len(games),
            "complete": len(scores),
            "failures": sum(game["status"] != "pass" for game in games),
            "player0_score_mean": mean(scores) if scores else None,
            "player0_score_normal_approx_95": _score_interval(scores),
            "realized_first_player": {
                str(player): sum(game["summary"]["first_player"] == player for game in games)
                for player in (0, 1)
            },
            "engine_requests": sum(game["summary"]["engine_requests"] for game in games),
        }
    return result


def run_arena(args, repo: Path) -> dict[str, Any]:
    policies = tuple(args.policies.split(","))
    if not policies or len(set(policies)) != len(policies):
        raise ValueError("arena policies must be a unique comma-separated list")
    if args.games_per_cell <= 0 or args.workers <= 0:
        raise ValueError("games-per-cell and workers must be positive")
    engine_root = args.engine_root.resolve(strict=True)
    card_data = args.card_data.resolve(strict=True)
    default_deck = args.default_deck.resolve(strict=True)
    private_baselines = args.private_baselines.resolve(strict=True)
    tasks = [
        (left, right, game)
        for left in policies
        for right in policies
        for game in range(args.games_per_cell)
    ]
    estimated_bytes = len(tasks) * 65_536
    if estimated_bytes > args.max_evidence_bytes:
        raise ValueError("arena evidence estimate exceeds configured byte cap")
    run_id = unique_run_id("g1r-arena")
    if args.resume and args.output is None:
        raise ValueError("arena resume requires an explicit output directory")
    run_dir = (args.output or repo / "runs" / run_id).resolve()
    config = {
        "policies": policies, "games_per_cell": args.games_per_cell,
        "workers": args.workers, "request_cap": args.request_cap,
        "game_timeout": args.game_timeout, "wall_seconds": args.wall_seconds,
        "max_evidence_bytes": args.max_evidence_bytes, "seed": args.seed,
        "natural_deployment": True, "training": False,
    }
    if args.resume:
        plan = json.loads((run_dir / "run-plan.json").read_text(encoding="utf-8"))
        if plan["config_sha256"] != stable_hash(config):
            raise ValueError("arena resume config differs from immutable run plan")
        run_id = plan["run_id"]
    else:
        if shutil.disk_usage(run_dir.parent).free < estimated_bytes * 2:
            raise ValueError("arena disk preflight failed")
        run_dir.mkdir(parents=True, exist_ok=False)
        plan = {
            "schema_version": 1, "run_id": run_id, "started_epoch": time.time(),
            "config": config, "config_sha256": stable_hash(config),
            "repository": git_state(repo), "platform": platform_record(),
            "source_sha256": source_tree_hash(repo), "command": list(sys.argv),
            "loaded_artifacts": {
                "engine_library": {"sha256": sha256_file(engine_root / "cg" / "libcg.so")},
                "game_wrapper": {"sha256": sha256_file(engine_root / "cg" / "game.py")},
                "api_wrapper": {"sha256": sha256_file(engine_root / "cg" / "api.py")},
                "sim_wrapper": {"sha256": sha256_file(engine_root / "cg" / "sim.py")},
                "card_data": {"sha256": sha256_file(card_data)},
                "default_deck": {"sha256": sha256_file(default_deck)},
                "private_baseline_receipts": {
                    path.parent.name: sha256_file(path)
                    for path in sorted(private_baselines.glob("*/receipt.json"))
                },
            },
            "task_count": len(tasks), "estimated_evidence_bytes": estimated_bytes,
            "resumable": True,
        }
        write_immutable_json(run_dir / "run-plan.json", plan)
    # Each resume gets the same bounded work window; offline gaps are not work.
    deadline_epoch = time.time() + args.wall_seconds

    def game_id(task: tuple[str, str, int]) -> str:
        left, right, game = task
        def safe(value: str) -> str:
            return "".join(character if character.isalnum() else "-" for character in value)
        return f"{run_id}-{safe(left)}-vs-{safe(right)}-{game:05d}"

    def execute(task: tuple[str, str, int]) -> dict[str, Any]:
        left, right, game = task
        identifier = game_id(task)
        if time.time() >= deadline_epoch:
            return {"status": "fail", "game_id": identifier, "policy0": left,
                    "policy1": right, "failure_kind": "arena_wall_timeout"}
        command = [
            str(Path(sys.executable).with_name("ptcg")), "g1", "arena-one",
            "--engine-root", str(engine_root), "--card-data", str(card_data),
            "--default-deck", str(default_deck),
            "--private-baselines", str(private_baselines),
            "--policy0", left, "--policy1", right, "--seed", str(args.seed + game),
            "--game-id", identifier, "--request-cap", str(args.request_cap),
            "--game-timeout", str(args.game_timeout),
            "--failure-directory", str(run_dir / "failures" / identifier),
        ]
        try:
            completed = subprocess.run(
                command, cwd=repo, text=True, capture_output=True,
                timeout=args.game_timeout + 10, check=False,
            )
        except subprocess.TimeoutExpired:
            return {"status": "fail", "game_id": identifier, "policy0": left,
                    "policy1": right, "failure_kind": "process_timeout"}
        if completed.returncode:
            return {"status": "fail", "game_id": identifier, "policy0": left,
                    "policy1": right, "failure_kind": "worker_exit",
                    "stderr": completed.stderr[-500:]}
        return json.loads(completed.stdout)

    records = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((run_dir / "matches").glob("*.json"))
    ]
    completed_ids = {record["game_id"] for record in records}
    pending = [task for task in tasks if game_id(task) not in completed_ids]
    session_started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(execute, task): task for task in pending}
        for future in as_completed(futures):
            record = future.result()
            records.append(record)
            write_immutable_json(run_dir / "matches" / f"{record['game_id']}.json", record)
            with (run_dir / "results.jsonl").open("a", encoding="utf-8") as journal:
                journal.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
    completed_records = [record for record in records if "summary" in record]
    latencies = sorted(
        latency for record in completed_records for latency in record["action_latencies_ms"]
    )

    def percentile(fraction: float) -> float | None:
        if not latencies:
            return None
        return latencies[min(len(latencies) - 1, int(fraction * (len(latencies) - 1)))]

    session_wall_seconds = time.monotonic() - session_started
    wall_seconds = time.time() - plan["started_epoch"]
    metrics = {
        "games_requested": len(tasks),
        "games_recorded": len(records),
        "games_completed": sum(
            record["summary"]["terminal_result"] is not None for record in completed_records
        ),
        "failures": sum(record["status"] != "pass" for record in records),
        "invalid_selections": sum(
            record["summary"]["invalid_selections"] for record in completed_records
        ),
        "fallback_actions": sum(
            record["summary"]["fallback_actions"] for record in completed_records
        ),
        "post_terminal_actions": sum(
            record["summary"]["post_terminal_actions"] for record in completed_records
        ),
        "engine_requests": sum(
            record["summary"]["engine_requests"] for record in completed_records
        ),
        "games_per_second": len(pending) / session_wall_seconds if session_wall_seconds else 0,
        "choices_per_second": sum(
            record["summary"]["engine_requests"] for record in completed_records
        ) / wall_seconds,
        "action_latency_ms": {
            "p50": percentile(0.50), "p95": percentile(0.95), "p99": percentile(0.99)
        },
        "cpu_percent": 100 * sum(
            record["process_metrics"]["cpu_seconds"] for record in completed_records
        ) / wall_seconds,
        "peak_rss_bytes": max(
            (record["process_metrics"]["peak_rss_bytes"] for record in completed_records),
            default=0,
        ),
    }
    passed = metrics["games_completed"] == len(tasks) and all(metrics[key] == 0 for key in (
            "failures", "invalid_selections", "fallback_actions", "post_terminal_actions"
        ))
    manifest_path = run_dir / "run_manifest.json"
    manifest = {
        **technical_run_envelope(repo, manifest_path, run_id, "ptcg.g1r.arena", passed),
        "natural_deployment": True,
        "paired_seed_claim": False,
        "policies": policies,
        "games_per_ordered_cell": args.games_per_cell,
        "metrics": metrics,
        "cells": _aggregate(completed_records),
        "wall_seconds": wall_seconds,
        "session_wall_seconds": session_wall_seconds,
        "run_plan_sha256": sha256_file(run_dir / "run-plan.json"),
        "config": config,
        "repository": plan["repository"],
        "platform": plan["platform"],
        "source_sha256": plan["source_sha256"],
        "loaded_artifacts": plan["loaded_artifacts"],
        "training_performed": False,
        "local_cost_usd": 0.0,
    }
    write_immutable_json(manifest_path, manifest)
    (run_dir / "run_manifest.json.sha256").write_text(
        f"{sha256_file(manifest_path)}  run_manifest.json\n", encoding="ascii"
    )
    return manifest
