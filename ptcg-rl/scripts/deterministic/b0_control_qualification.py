#!/usr/bin/env python3
"""Run the bounded B0 candidate/control matrix.

The default configuration is deliberately a mechanical canary.  It is not a
promotion run and the script refuses to write outside the repository.  The
native engine is loaded in one fresh subprocess per game, which preserves the
one-active-battle contract and makes worker failures observable.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from ptcg_rl.deterministic.harness import (
    B0_EXPERIMENT_ID,
    aggregate_candidate_records,
    sanitized_report,
    source_receipt,
    write_sealed_json,
)
from ptcg_rl.g1.evidence import (
    git_state,
    platform_record,
    source_tree_hash,
    unique_run_id,
)
from ptcg_rl.g1.environment import DevelopmentEpisodeError, EpisodeEnvironmentV1, FailureMode
from ptcg_rl.g1.models import SchemaMetadataV1
from ptcg_rl.g1.native import NativeCABTTransport, load_deck
from ptcg_rl.g1.rule_baseline import NativeRulePolicy
from ptcg_rl.g1.evidence import sha256_file


DEFAULT_POLICY_IMPORT = "ptcg_rl.deterministic.policy:DeterministicStrategicPolicy"


def _inside(path: Path, repo: Path) -> Path:
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(repo.resolve()):
        raise ValueError(f"path is outside repository scope: {resolved}")
    return resolved


def _load_candidate(import_spec: str) -> Any:
    module_name, separator, class_name = import_spec.partition(":")
    if not separator or not module_name or not class_name:
        raise ValueError("candidate import must be module:Class")
    factory = getattr(importlib.import_module(module_name), class_name)
    return factory()


def _make_policy(spec: str, *, private_baselines: Path, candidate_import: str) -> tuple[Any, list[int]]:
    if spec == "candidate":
        raise RuntimeError("candidate deck must be supplied by the worker")
    if spec.startswith("rule:"):
        policy = NativeRulePolicy(private_baselines / spec.split(":", 1)[1])
        return policy, list(policy.deck)
    raise ValueError(f"unknown B0 policy spec: {spec}")


def run_single_game(args: argparse.Namespace, repo: Path) -> dict[str, Any]:
    repo = repo.resolve(strict=True)
    engine_root = _inside(args.engine_root, repo)
    card_data = _inside(args.card_data, repo)
    default_deck = _inside(args.default_deck, repo)
    private_baselines = _inside(args.private_baselines, repo)
    candidate_deck = load_deck(default_deck)
    try:
        transport = NativeCABTTransport(engine_root)
        policies: dict[int, Any] = {}
        decks: dict[int, list[int]] = {}
        for player, spec in enumerate((args.policy0, args.policy1)):
            if spec == "candidate":
                policies[player] = _load_candidate(args.candidate_import)
                decks[player] = candidate_deck
            else:
                policies[player], decks[player] = _make_policy(
                    spec, private_baselines=private_baselines, candidate_import=args.candidate_import
                )
        metadata = SchemaMetadataV1.build(
            sha256_file(transport.library_path), sha256_file(card_data)
        )
        environment = EpisodeEnvironmentV1(
            transport,
            metadata,
            max_requests=args.request_cap,
            deadline_monotonic=time.monotonic() + args.game_timeout,
            failure_directory=None,
            failure_mode=FailureMode.DEVELOPMENT,
        )
        try:
            result = environment.run(args.game_id, decks[0], decks[1], policies)
        except DevelopmentEpisodeError as error:
            result = error.result
        summary = result.summary
        return {
            "schema_version": 1,
            "game_id": args.game_id,
            "arm": args.arm,
            "evaluated_player": args.evaluated_player,
            "candidate_player": args.evaluated_player,
            "policy0": args.policy0,
            "policy1": args.policy1,
            "status": "pass" if summary.failure_kind is None and summary.terminal_result is not None else "fail",
            "summary": {
                "terminal_result": summary.terminal_result,
                "first_player": summary.first_player,
                "engine_requests": summary.engine_requests,
                "invalid_selections": summary.invalid_selections,
                "fallback_actions": summary.fallback_actions,
                "post_terminal_actions": summary.post_terminal_actions,
                "failure_kind": summary.failure_kind,
            },
            "action_latencies_ms": list(result.action_latencies_ms),
        }
    except Exception as error:  # The orchestrator records, rather than hides, worker errors.
        return {
            "schema_version": 1,
            "game_id": args.game_id,
            "arm": args.arm,
            "evaluated_player": args.evaluated_player,
            "candidate_player": args.evaluated_player,
            "policy0": args.policy0,
            "policy1": args.policy1,
            "status": "fail",
            "failure_kind": "worker_exception",
            "error_type": type(error).__name__,
            "error_message": str(error)[:300],
            "summary": {
                "terminal_result": None,
                "invalid_selections": 0,
                "fallback_actions": 0,
                "post_terminal_actions": 0,
                "failure_kind": "worker_exception",
            },
            "action_latencies_ms": [],
        }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/deterministic/b0_ma_control_v1.json"))
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--engine-root", type=Path)
    parser.add_argument("--card-data", type=Path)
    parser.add_argument("--default-deck", type=Path)
    parser.add_argument("--private-baselines", type=Path)
    parser.add_argument("--candidate-import", default=DEFAULT_POLICY_IMPORT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--single-game", action="store_true")
    parser.add_argument("--game-id")
    parser.add_argument("--arm", choices=("candidate", "control"), default="candidate")
    parser.add_argument("--evaluated-player", type=int, choices=(0, 1), default=0)
    parser.add_argument("--policy0")
    parser.add_argument("--policy1")
    parser.add_argument("--request-cap", type=int, default=20_000)
    parser.add_argument("--game-timeout", type=int, default=180)
    return parser


def _task_id(run_id: str, arm: str, anchor: str, player: int, ordinal: int) -> str:
    safe_anchor = "".join(value if value.isalnum() else "-" for value in anchor)
    return f"{run_id}-{arm}-{safe_anchor}-seat{player}-{ordinal:03d}"


def run_b0(args: argparse.Namespace) -> dict[str, Any]:
    repo = args.repo.resolve(strict=True)
    config_path = _inside(args.config, repo)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("experiment_id") != B0_EXPERIMENT_ID:
        raise ValueError("config is not B0-MA-CONTROL-001")
    for path_name in ("engine_root", "card_data", "default_deck", "private_baselines"):
        value = getattr(args, path_name)
        if value is None:
            raise ValueError(f"--{path_name.replace('_', '-')} is required for a B0 run")
        setattr(args, path_name, _inside(value, repo))
    run_id = unique_run_id(config["mechanical_canary"]["run_id_prefix"])
    run_dir = repo / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "matches").mkdir()
    plan = {
        "schema_version": 1,
        "run_id": run_id,
        "experiment_id": B0_EXPERIMENT_ID,
        "config": config,
        "config_sha256": sha256_file(config_path),
        "repository": git_state(repo),
        "platform": platform_record(),
        "source_sha256": source_tree_hash(repo),
        "loaded_artifacts": source_receipt(
            {
                "config": config_path,
                "card_data": args.card_data,
                "candidate_deck": args.default_deck,
                "native_library": args.engine_root / "cg" / "libcg.so",
                "game_wrapper": args.engine_root / "cg" / "game.py",
                "api_wrapper": args.engine_root / "cg" / "api.py",
                "sim_wrapper": args.engine_root / "cg" / "sim.py",
                **{
                    f"anchor_{anchor.replace(':', '_')}_{name}": private_path / name
                    for anchor in config["anchors"]
                    for private_path in [args.private_baselines / anchor.split(":", 1)[1]]
                    for name in ("receipt.json", "deck.csv", "main.py")
                },
            },
            repo,
        ),
        "paired_seed_claim": False,
        "training_performed": False,
    }
    write_sealed_json(run_dir / "run-plan.json", plan)
    anchors = tuple(config["anchors"])
    per_seat = int(config["mechanical_canary"]["games_per_anchor_per_candidate_seat"])
    tasks = []
    for arm, evaluated_policy in (("candidate", "candidate"), ("control", "rule:mega-abomasnow-ex")):
        for anchor in anchors:
            for player in (0, 1):
                for ordinal in range(per_seat):
                    policy0 = evaluated_policy if player == 0 else anchor
                    policy1 = anchor if player == 0 else evaluated_policy
                    tasks.append((arm, anchor, player, ordinal, policy0, policy1))
    records: dict[str, list[dict[str, Any]]] = {"candidate": [], "control": []}
    script_path = Path(__file__).resolve()
    for arm, anchor, player, ordinal, policy0, policy1 in tasks:
        game_id = _task_id(run_id, arm, anchor, player, ordinal)
        command = [
            sys.executable,
            str(script_path),
            "--single-game",
            "--repo",
            str(repo),
            "--engine-root",
            str(args.engine_root),
            "--card-data",
            str(args.card_data),
            "--default-deck",
            str(args.default_deck),
            "--private-baselines",
            str(args.private_baselines),
            "--candidate-import",
            args.candidate_import,
            "--game-id",
            game_id,
            "--arm",
            arm,
            "--evaluated-player",
            str(player),
            "--policy0",
            policy0,
            "--policy1",
            policy1,
            "--request-cap",
            str(config["mechanical_canary"]["request_cap"]),
            "--game-timeout",
            str(config["mechanical_canary"]["game_timeout_seconds"]),
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=repo,
                text=True,
                capture_output=True,
                check=False,
                timeout=int(config["mechanical_canary"]["game_timeout_seconds"]) + 10,
                env={**os.environ, "UV_CACHE_DIR": str(repo / "data/cache/uv")},
            )
            record = json.loads(completed.stdout) if completed.stdout.strip() else {
                "game_id": game_id,
                "arm": arm,
                "candidate_player": player,
                "status": "fail",
                "summary": {
                    "terminal_result": None,
                    "invalid_selections": 0,
                    "fallback_actions": 0,
                    "post_terminal_actions": 0,
                    "failure_kind": "worker_exit",
                },
                "action_latencies_ms": [],
                "error_message": completed.stderr[-300:],
            }
        except subprocess.TimeoutExpired:
            record = {
                "game_id": game_id,
                "arm": arm,
                "candidate_player": player,
                "status": "fail",
                "summary": {
                    "terminal_result": None,
                    "invalid_selections": 0,
                    "fallback_actions": 0,
                    "post_terminal_actions": 0,
                    "failure_kind": "process_timeout",
                },
                "action_latencies_ms": [],
            }
        records[arm].append(record)
        write_sealed_json(run_dir / "matches" / f"{game_id}.json", record)
    candidate_aggregate = aggregate_candidate_records(
        records["candidate"],
        control_scores=[
            score
            for score in (
                aggregate_candidate_records(records["control"])["candidate_scores"]
            )
        ],
    )
    control_aggregate = aggregate_candidate_records(records["control"])
    aggregate = {
        "candidate_arm": candidate_aggregate,
        "control_arm": control_aggregate,
        "candidate_control_bootstrap_delta": candidate_aggregate.get("control_bootstrap_score_delta"),
        "games_requested": len(tasks),
        "games_completed": candidate_aggregate["games_completed"] + control_aggregate["games_completed"],
    }
    report = sanitized_report(
        run_id=run_id,
        config=config,
        aggregate=aggregate,
        repository=plan["repository"],
        platform=plan["platform"],
        source_sha256=plan["source_sha256"],
        loaded_artifacts=plan["loaded_artifacts"],
        permutation={
            "permutations_requested": config["permutation_control"]["permutations"],
            "status": "PENDING_SEPARATE_SEMANTIC_FIXTURE",
        },
    )
    manifest = {
        **report,
        "run_plan_sha256": sha256_file(run_dir / "run-plan.json"),
        "raw_run_dir": run_dir.relative_to(repo).as_posix(),
    }
    write_sealed_json(run_dir / "run_manifest.json", manifest)
    if args.output is not None:
        output = _inside(args.output, repo)
        write_sealed_json(output, report)
    return manifest


def main() -> int:
    args = _parser().parse_args()
    repo = args.repo.resolve(strict=True)
    if args.single_game:
        if not args.game_id or args.policy0 is None or args.policy1 is None:
            raise SystemExit("single-game mode requires --game-id, --policy0 and --policy1")
        print(json.dumps(run_single_game(args, repo), sort_keys=True))
        return 0
    print(json.dumps(run_b0(args), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
