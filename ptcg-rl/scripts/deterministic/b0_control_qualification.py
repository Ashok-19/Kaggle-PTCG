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
import importlib.util
import inspect
import json
import math
import os
import resource
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# Direct execution from the repository must resolve the local ``src`` package,
# without requiring an editable install or a caller-specific PYTHONPATH.
_REPO_FOR_IMPORT = Path(__file__).resolve().parents[2]
if str(_REPO_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(_REPO_FOR_IMPORT / "src"))

from ptcg_rl.deterministic.harness import (  # noqa: E402
    B0_EXPERIMENT_ID,
    aggregate_candidate_records,
    candidate_source_sha256,
    permutation_control,
    sanitized_report,
    source_receipt,
    verify_sealed_json,
    write_sealed_json,
)
from ptcg_rl.g1.evidence import (  # noqa: E402
    git_state,
    platform_record,
    source_tree_hash,
    unique_run_id,
)
from ptcg_rl.g1.environment import DevelopmentEpisodeError, EpisodeEnvironmentV1, FailureMode  # noqa: E402
from ptcg_rl.g1.models import SchemaMetadataV1  # noqa: E402
from ptcg_rl.g1.native import NativeCABTTransport, load_deck  # noqa: E402
from ptcg_rl.g1.rule_baseline import NativeRulePolicy  # noqa: E402
from ptcg_rl.g1.evidence import sha256_file  # noqa: E402
from ptcg_rl.g2.card_table import load_card_table, verify_card_table  # noqa: E402


def _inside(path: Path, repo: Path, *, strict: bool = True) -> Path:
    root = repo.resolve(strict=True)
    resolved = path.resolve(strict=strict)
    if not resolved.is_relative_to(root):
        raise ValueError(f"path is outside repository scope: {resolved}")
    if not strict and not resolved.parent.resolve(strict=True).is_relative_to(root):
        raise ValueError(f"output parent is outside repository scope: {resolved.parent}")
    return resolved


def _sanitized_command(command: list[str], repo: Path) -> list[str]:
    root = repo.resolve(strict=True)
    result: list[str] = []
    for value in command:
        candidate = Path(value)
        if candidate.is_absolute():
            resolved = candidate.resolve(strict=False)
            if resolved.is_relative_to(root):
                result.append(resolved.relative_to(root).as_posix())
            else:
                result.append("<external>")
        else:
            result.append(value)
    return result


def _permutations(option_count: int, count: int, seed: int = 17) -> list[tuple[int, ...]]:
    if option_count < 5:
        return []
    if count > math.factorial(option_count):
        raise ValueError("requested permutation count exceeds the true permutation space")
    identity = tuple(range(option_count))
    reversed_order = tuple(reversed(identity))
    permutations = [identity]
    for permutation in (reversed_order, tuple(range(1, option_count)) + (0,)):
        if permutation not in permutations:
            permutations.append(permutation)
    import random

    rng = random.Random(seed)
    while len(permutations) < count:
        candidate = list(identity)
        rng.shuffle(candidate)
        value = tuple(candidate)
        if value not in permutations:
            permutations.append(value)
    return permutations[:count]


def _candidate_latency_values(
    latencies: Any, transitions: Any, candidate_player: int
) -> list[float]:
    """Attribute action timings only when every nonterminal choice has a timing."""
    requests = [transition.request for transition in transitions if transition.request is not None]
    if len(latencies) != len(requests):
        raise ValueError("latency/request cardinality mismatch")
    return [
        float(latency)
        for latency, request in zip(latencies, requests, strict=True)
        if request.acting_player == candidate_player
    ]


def _fresh_session_deadline(wall_seconds: int, now: float | None = None) -> float:
    if wall_seconds <= 0:
        raise ValueError("session wall budget must be positive")
    return (time.monotonic() if now is None else now) + wall_seconds


def _should_stop_after_record(record: dict[str, Any], stop_condition: str) -> bool:
    if not stop_condition.startswith("stop_on_any_"):
        return False
    summary = record.get("summary")
    return (
        record.get("status") != "pass"
        or not isinstance(summary, dict)
        or summary.get("terminal_result") is None
        or summary.get("invalid_selections", 0) != 0
        or summary.get("fallback_actions", 0) != 0
        or summary.get("post_terminal_actions", 0) != 0
        or summary.get("failure_kind") is not None
    )


def _source_path(path: Path, repo: Path) -> Path:
    """Resolve a Python source path and prove it is repository-owned."""
    if path.suffix == ".pyc":
        try:
            path = Path(importlib.util.source_from_cache(str(path)))
        except (NotImplementedError, ValueError) as error:
            raise ValueError("candidate module source is not recoverable") from error
    if path.suffix != ".py":
        raise ValueError("candidate module source is not a Python source file")
    return _inside(path, repo)


def _resolve_candidate_import(
    import_spec: str, repo: Path, *, expected_import: str | None = None
) -> tuple[Any, Path]:
    """Resolve the configured class and prove its module/class source is local."""
    if expected_import is not None and import_spec != expected_import:
        raise ValueError("candidate import differs from configured candidate import")
    module_name, separator, class_name = import_spec.partition(":")
    if not separator or not module_name or not class_name:
        raise ValueError("candidate import must be module:Class")
    try:
        module_spec = importlib.util.find_spec(module_name)
    except (ImportError, ValueError) as error:
        raise ValueError("candidate module cannot be resolved") from error
    if module_spec is None or not module_spec.origin or module_spec.origin in {"built-in", "frozen"}:
        raise ValueError("candidate module source cannot be proven")
    module = importlib.import_module(module_name)
    module_file = getattr(module, "__file__", None)
    if not module_file:
        raise ValueError("candidate module source cannot be proven")
    origin_path = _source_path(Path(module_spec.origin), repo)
    loaded_path = _source_path(Path(module_file), repo)
    if origin_path != loaded_path:
        raise ValueError("candidate module source changed during import")
    try:
        factory = getattr(module, class_name)
    except AttributeError as error:
        raise ValueError("configured candidate class is missing") from error
    factory_source = inspect.getsourcefile(factory)
    if factory_source is None or _source_path(Path(factory_source), repo) != loaded_path:
        raise ValueError("candidate class source cannot be proven inside the repository")
    if not callable(factory):
        raise ValueError("configured candidate class is not callable")
    return factory, loaded_path


def _load_candidate(import_spec: str, repo: Path) -> Any:
    factory, _ = _resolve_candidate_import(import_spec, repo)
    return factory()


def _make_policy(spec: str, *, private_baselines: Path, candidate_import: str) -> tuple[Any, list[int]]:
    if spec == "candidate":
        raise RuntimeError("candidate deck must be supplied by the worker")
    if spec.startswith("rule:"):
        policy = NativeRulePolicy(private_baselines / spec.split(":", 1)[1])
        return policy, list(policy.deck)
    raise ValueError(f"unknown B0 policy spec: {spec}")


def _worker_config_import(config_path: Path, repo: Path) -> str:
    worker_config_path = _inside(config_path, repo)
    worker_config = json.loads(worker_config_path.read_text(encoding="utf-8"))
    configured_import = worker_config.get("candidate", {}).get("import_spec")
    if not isinstance(configured_import, str) or not configured_import:
        raise ValueError("worker config must freeze candidate.import_spec")
    return configured_import


def _worker_command(
    *,
    script_path: Path,
    repo: Path,
    config_path: Path,
    engine_root: Path,
    card_data: Path,
    card_table: Path,
    default_deck: Path,
    private_baselines: Path,
    candidate_import: str,
    candidate_policy_id: str,
    game_id: str,
    anchor: str,
    arm: str,
    player: int,
    policy0: str,
    policy1: str,
    request_cap: int,
    game_timeout: int,
    permutation_count: int,
) -> list[str]:
    return [
        sys.executable,
        str(script_path),
        "--single-game",
        "--repo",
        str(repo),
        "--config",
        str(config_path),
        "--engine-root",
        str(engine_root),
        "--card-data",
        str(card_data),
        "--card-table",
        str(card_table),
        "--default-deck",
        str(default_deck),
        "--private-baselines",
        str(private_baselines),
        "--candidate-import",
        candidate_import,
        "--candidate-policy-id",
        candidate_policy_id,
        "--game-id",
        game_id,
        "--anchor",
        anchor,
        "--arm",
        arm,
        "--evaluated-player",
        str(player),
        "--policy0",
        policy0,
        "--policy1",
        policy1,
        "--request-cap",
        str(request_cap),
        "--game-timeout",
        str(game_timeout),
        "--permutation-count",
        str(permutation_count),
    ]


def run_single_game(args: argparse.Namespace, repo: Path) -> dict[str, Any]:
    process_started = time.process_time()
    wall_started = time.monotonic()
    repo = repo.resolve(strict=True)
    configured_import = _worker_config_import(args.config, repo)
    if args.candidate_import != configured_import:
        raise ValueError("worker candidate import differs from configured candidate import")
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
                policies[player] = _load_candidate(args.candidate_import, repo)
                expected_policy_id = getattr(args, "candidate_policy_id", None)
                if expected_policy_id and policies[player].policy_id != expected_policy_id:
                    raise ValueError("candidate policy ID differs from configured policy")
                declared_deck = getattr(policies[player], "deck", None)
                if declared_deck is not None and tuple(declared_deck) != tuple(candidate_deck):
                    raise ValueError("candidate policy deck differs from the configured exact deck")
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
        candidate_latencies = _candidate_latency_values(
            result.action_latencies_ms, result.transitions, args.evaluated_player
        )
        passed = (
            summary.failure_kind is None
            and summary.terminal_result is not None
            and summary.invalid_selections == 0
            and summary.fallback_actions == 0
            and summary.post_terminal_actions == 0
        )
        permutation = {"status": "NOT_RUN", "pass": False, "paired_seed_claim": False}
        if args.arm == "candidate":
            candidate_transition = next(
                (
                    transition
                    for transition in result.transitions
                    if transition.request is not None
                    and transition.request.acting_player == args.evaluated_player
                    and len(transition.request.options) >= 5
                ),
                None,
            )
            if candidate_transition is not None and candidate_transition.request is not None:
                permutations = _permutations(
                    len(candidate_transition.request.options), args.permutation_count
                )
                if permutations:
                    permutation = permutation_control(
                        lambda: _load_candidate(args.candidate_import, repo),
                        candidate_transition.observation,
                        candidate_transition.request,
                        permutations,
                    )
                    permutation["ordering"] = candidate_transition.request.ordering
                else:
                    permutation = {
                        "status": "INSUFFICIENT_OPTIONS",
                        "permutations_requested": args.permutation_count,
                        "pass": False,
                        "paired_seed_claim": False,
                    }
        process_metrics = {
            "cpu_seconds": time.process_time() - process_started,
            "wall_seconds": time.monotonic() - wall_started,
            "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
        }
        return {
            "schema_version": 1,
            "game_id": args.game_id,
            "arm": args.arm,
            "evaluated_player": args.evaluated_player,
            "candidate_player": args.evaluated_player,
            "anchor": getattr(args, "anchor", "unknown"),
            "policy0": args.policy0,
            "policy1": args.policy1,
            "status": "pass" if passed else "fail",
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
            "candidate_action_latencies_ms": candidate_latencies,
            "process_metrics": process_metrics,
            "permutation_control": permutation,
        }
    except Exception as error:  # The orchestrator records, rather than hides, worker errors.
        return {
            "schema_version": 1,
            "game_id": args.game_id,
            "arm": args.arm,
            "evaluated_player": args.evaluated_player,
            "candidate_player": args.evaluated_player,
            "anchor": getattr(args, "anchor", "unknown"),
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
            "candidate_action_latencies_ms": [],
            "process_metrics": {
                "cpu_seconds": time.process_time() - process_started,
                "wall_seconds": time.monotonic() - wall_started,
                "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024,
            },
            "permutation_control": {
                "status": "NOT_RUN", "pass": False, "paired_seed_claim": False
            },
        }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/deterministic/b0_ma_control_v1.json"))
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--engine-root", type=Path)
    parser.add_argument("--card-data", type=Path)
    parser.add_argument("--card-table", type=Path)
    parser.add_argument("--default-deck", type=Path)
    parser.add_argument("--private-baselines", type=Path)
    parser.add_argument("--candidate-import")
    parser.add_argument("--candidate-policy-id")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--single-game", action="store_true")
    parser.add_argument("--game-id")
    parser.add_argument("--anchor", default="unknown")
    parser.add_argument("--arm", choices=("candidate", "control"), default="candidate")
    parser.add_argument("--evaluated-player", type=int, choices=(0, 1), default=0)
    parser.add_argument("--policy0")
    parser.add_argument("--policy1")
    parser.add_argument("--request-cap", type=int, default=20_000)
    parser.add_argument("--game-timeout", type=int, default=180)
    parser.add_argument("--permutation-count", type=int, default=32)
    parser.add_argument("--resume-run", type=Path)
    return parser


def _task_id(run_id: str, arm: str, anchor: str, player: int, ordinal: int) -> str:
    safe_anchor = "".join(value if value.isalnum() else "-" for value in anchor)
    return f"{run_id}-{arm}-{safe_anchor}-seat{player}-{ordinal:03d}"


def _failure_record(
    *,
    game_id: str,
    arm: str,
    anchor: str,
    player: int,
    policy0: str,
    policy1: str,
    failure_kind: str,
    missing_output: int = 0,
    error_message: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "game_id": game_id,
        "arm": arm,
        "anchor": anchor,
        "evaluated_player": player,
        "candidate_player": player,
        "policy0": policy0,
        "policy1": policy1,
        "status": "fail",
        "failure_kind": failure_kind,
        "missing_output": missing_output,
        "error_message": error_message,
        "summary": {
            "terminal_result": None,
            "first_player": None,
            "engine_requests": 0,
            "invalid_selections": 0,
            "fallback_actions": 0,
            "post_terminal_actions": 0,
            "failure_kind": failure_kind,
        },
        "action_latencies_ms": [],
        "candidate_action_latencies_ms": [],
        "process_metrics": {"cpu_seconds": 0.0, "wall_seconds": 0.0, "peak_rss_bytes": 0},
        "permutation_control": {"status": "NOT_RUN", "pass": False, "paired_seed_claim": False},
    }


def _evidence_bytes(run_dir: Path) -> int:
    return sum(path.stat().st_size for path in run_dir.rglob("*") if path.is_file())


def _sealed_payload_size(path: Path, value: dict[str, Any]) -> int:
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    sidecar = len("0" * 64) + 2 + len(path.name) + 1
    return len(payload) + sidecar


def _validate_budget_scopes(config: dict[str, Any], anchor_count: int) -> None:
    """Reject ambiguous or arithmetically inconsistent arm budgets."""
    canary = config["mechanical_canary"]
    canary_per_arm = int(canary["games_per_anchor_per_candidate_seat"]) * anchor_count * 2
    if canary.get("games_total_scope") != "all_arms":
        raise ValueError("mechanical canary games_total must be scoped to all_arms")
    if int(canary.get("games_total_per_arm", -1)) != canary_per_arm:
        raise ValueError("mechanical canary per-arm total differs from seat/anchor counts")
    if int(canary.get("games_total_all_arms", -1)) != canary_per_arm * 2:
        raise ValueError("mechanical canary all-arm total differs from per-arm total")
    if int(canary.get("games_total", -1)) != int(canary["games_total_all_arms"]):
        raise ValueError("mechanical canary games_total is not the all-arm total")
    if int(canary.get("candidate_arm_games_total", -1)) != canary_per_arm:
        raise ValueError("mechanical canary candidate-arm total is inconsistent")
    if int(canary.get("control_arm_games_total", -1)) != canary_per_arm:
        raise ValueError("mechanical canary control-arm total is inconsistent")
    for name, budget in config.get("scale_budgets", {}).items():
        per_arm = int(budget.get("games_total_per_arm", -1))
        all_arms = int(budget.get("games_total_all_arms", -1))
        expected_per_arm = int(budget.get("games_per_anchor_per_candidate_seat", -1)) * anchor_count * 2
        if budget.get("games_total_scope") != "per_arm":
            raise ValueError(f"scale budget {name} must declare games_total_scope=per_arm")
        if per_arm != expected_per_arm or all_arms != per_arm * 2:
            raise ValueError(f"scale budget {name} has inconsistent arm totals")
        if int(budget.get("games_total", -1)) != per_arm:
            raise ValueError(f"scale budget {name} games_total is not its per-arm total")


def run_b0(args: argparse.Namespace) -> dict[str, Any]:
    repo = args.repo.resolve(strict=True)
    config_path = _inside(args.config, repo)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("experiment_id") != B0_EXPERIMENT_ID:
        raise ValueError("config is not B0-MA-CONTROL-001")
    candidate_config = config.get("candidate", {})
    configured_import = candidate_config.get("import_spec")
    if not isinstance(configured_import, str) or not configured_import:
        raise ValueError("B0 config must freeze candidate.import_spec")
    if args.candidate_import is None:
        args.candidate_import = configured_import
    elif args.candidate_import != configured_import:
        raise ValueError("candidate import differs from configured candidate import")
    _, imported_candidate_source = _resolve_candidate_import(
        args.candidate_import, repo, expected_import=configured_import
    )
    configured_source_files = candidate_config.get("source_files")
    if not isinstance(configured_source_files, list) or not configured_source_files:
        raise ValueError("B0 config must list explicit candidate source_files")
    candidate_source_paths: list[Path] = []
    for source_name in configured_source_files:
        if not isinstance(source_name, str) or not source_name:
            raise ValueError("candidate source_files must contain nonempty paths")
        source_path = _inside(repo / source_name, repo)
        if source_path in candidate_source_paths:
            raise ValueError("candidate source_files contain a duplicate path")
        candidate_source_paths.append(source_path)
    if imported_candidate_source not in candidate_source_paths:
        raise ValueError("imported candidate module is absent from source_files")

    assets = config.get("assets", {})
    card_data_asset = assets.get("card_data", {})
    candidate_asset = assets.get("candidate_deck", {})
    card_table_asset = assets.get("card_table", {})
    if args.card_data is None and card_data_asset.get("path"):
        args.card_data = repo / card_data_asset["path"]
    if args.default_deck is None and candidate_asset.get("path"):
        args.default_deck = repo / candidate_asset["path"]
    if args.card_table is None and card_table_asset.get("path"):
        args.card_table = repo / card_table_asset["path"]
    for path_name in (
        "engine_root",
        "card_data",
        "card_table",
        "default_deck",
        "private_baselines",
    ):
        value = getattr(args, path_name)
        if value is None:
            raise ValueError(f"--{path_name.replace('_', '-')} is required for a B0 run")
        setattr(args, path_name, _inside(value, repo))

    if candidate_asset.get("path"):
        configured_deck = _inside(repo / candidate_asset["path"], repo)
        if args.default_deck != configured_deck:
            raise ValueError("candidate deck differs from the exact deck configured for B0")
    for asset_name, path in (
        ("candidate_deck", args.default_deck),
        ("card_data", args.card_data),
        ("card_table", args.card_table),
    ):
        expected = assets.get(asset_name, {}).get("sha256")
        if expected and sha256_file(path) != expected:
            raise ValueError(f"{asset_name} hash differs from configured receipt")
    table = load_card_table(args.card_table)
    card_table_verification = verify_card_table(table)
    expected_semantic = card_table_asset.get("semantic_sha256")
    if expected_semantic and card_table_verification["table_sha256"] != expected_semantic:
        raise ValueError("card-table semantic hash differs from configured receipt")

    candidate_source_files = {
        "candidate_config": config_path,
        "candidate_imported_module": imported_candidate_source,
        **{
            f"candidate_transitive_{index:02d}": path
            for index, path in enumerate(candidate_source_paths)
        },
    }
    candidate_source_digest = candidate_source_sha256(candidate_source_files, repo)
    config_sha256 = sha256_file(config_path)
    command = _sanitized_command(list(sys.argv), repo)
    anchors = tuple(config["anchors"])
    _validate_budget_scopes(config, len(anchors))
    per_seat = int(config["mechanical_canary"]["games_per_anchor_per_candidate_seat"])
    if per_seat <= 0:
        raise ValueError("mechanical canary games per seat must be positive")
    args.permutation_count = int(config["permutation_control"]["permutations"])
    if args.permutation_count < 1:
        raise ValueError("permutation count must be positive")
    if config["mechanical_canary"]["stop_condition"] != (
        "stop_on_any_invalid_fallback_timeout_failure_or_incomplete_game"
    ):
        raise ValueError("unsupported B0 stop condition")

    tasks = []
    for arm, evaluated_policy in (("candidate", "candidate"), ("control", "rule:mega-abomasnow-ex")):
        for anchor in anchors:
            for player in (0, 1):
                for ordinal in range(per_seat):
                    policy0 = evaluated_policy if player == 0 else anchor
                    policy1 = anchor if player == 0 else evaluated_policy
                    tasks.append((arm, anchor, player, ordinal, policy0, policy1))
    canary = config["mechanical_canary"]
    max_evidence_bytes = int(canary["max_evidence_bytes"])
    if max_evidence_bytes <= 0:
        raise ValueError("maximum evidence bytes must be positive")
    if int(canary["wall_seconds"]) <= 0 or int(canary["game_timeout_seconds"]) <= 0:
        raise ValueError("B0 wall and game timeouts must be positive")
    if int(canary["request_cap"]) <= 0:
        raise ValueError("B0 request cap must be positive")

    loaded_paths: dict[str, Path] = {
        "config": config_path,
        "card_data": args.card_data,
        "card_table": args.card_table,
        "candidate_deck": args.default_deck,
        "native_library": args.engine_root / "cg" / "libcg.so",
        "game_wrapper": args.engine_root / "cg" / "game.py",
        "api_wrapper": args.engine_root / "cg" / "api.py",
        "sim_wrapper": args.engine_root / "cg" / "sim.py",
    }
    loaded_paths.update(candidate_source_files)
    loaded_paths.update(
        {
            f"anchor_{anchor.replace(':', '_')}_{name}": private_path / name
            for anchor in anchors
            for private_path in [args.private_baselines / anchor.split(":", 1)[1]]
            for name in ("receipt.json", "deck.csv", "main.py")
        }
    )
    loaded_receipt = source_receipt(loaded_paths, repo)

    resumed = args.resume_run is not None
    if resumed:
        run_dir = _inside(args.resume_run, repo)
        prior_manifests = sorted(run_dir.glob("run_manifest*.json"))
        for prior_manifest in prior_manifests:
            verify_sealed_json(prior_manifest)
            prior_value = json.loads(prior_manifest.read_text(encoding="utf-8"))
            if prior_value.get("status") == "SUCCEEDED" or prior_value.get("aggregate", {}).get(
                "games_recorded", 0
            ) >= len(tasks):
                raise ValueError("a complete B0 run cannot be resumed")
        plan_path = run_dir / "run-plan.json"
        verify_sealed_json(plan_path)
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        if plan.get("config_sha256") != config_sha256:
            raise ValueError("resume config differs from immutable run plan")
        if plan.get("config_path") != config_path.relative_to(repo).as_posix():
            raise ValueError("resume config path differs from immutable run plan")
        if plan.get("candidate_import_spec") != args.candidate_import:
            raise ValueError("resume candidate import differs from immutable run plan")
        if plan.get("candidate_source_sha256") != candidate_source_digest:
            raise ValueError("resume candidate source differs from immutable run plan")
        if plan.get("candidate_source_receipt") != source_receipt(candidate_source_files, repo):
            raise ValueError("resume candidate source receipt differs from immutable run plan")
        if plan.get("loaded_artifacts") != loaded_receipt:
            raise ValueError("resume loaded asset receipt differs from immutable run plan")
        if plan.get("card_table_semantic_sha256") != card_table_verification["table_sha256"]:
            raise ValueError("resume card-table semantics differ from immutable run plan")
        run_id = plan["run_id"]
        matches_dir = run_dir / "matches"
        if not matches_dir.is_dir():
            raise ValueError("resume run is missing its matches directory")
    else:
        run_id = unique_run_id(config["mechanical_canary"]["run_id_prefix"])
        run_dir = repo / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        matches_dir = run_dir / "matches"
        matches_dir.mkdir()
        plan = None

    expected_ids = {
        _task_id(run_id, arm, anchor, player, ordinal): (arm, anchor, player, ordinal, policy0, policy1)
        for arm, anchor, player, ordinal, policy0, policy1 in tasks
    }
    records: dict[str, list[dict[str, Any]]] = {"candidate": [], "control": []}
    seen_ids: set[str] = set()
    for path in sorted(matches_dir.glob("*.json")):
        verify_sealed_json(path)
        record = json.loads(path.read_text(encoding="utf-8"))
        game_id = record.get("game_id")
        if game_id not in expected_ids or game_id in seen_ids:
            raise ValueError("resume match record is unknown or duplicated")
        seen_ids.add(game_id)
        arm = record.get("arm")
        if arm not in records:
            raise ValueError("resume match record has unknown arm")
        expected = expected_ids[game_id]
        if tuple(record.get(key) for key in ("arm", "anchor", "candidate_player", "policy0", "policy1")) != (
            expected[0], expected[1], expected[2], expected[4], expected[5]
        ):
            raise ValueError("resume match record identity differs from the immutable task plan")
        records[arm].append(record)

    if plan is None:
        plan = {
            "schema_version": 1,
            "run_id": run_id,
            "experiment_id": B0_EXPERIMENT_ID,
            "config": config,
            "config_path": config_path.relative_to(repo).as_posix(),
            "config_sha256": config_sha256,
            "command": command,
            "repository": git_state(repo),
            "platform": platform_record(),
            "source_sha256": source_tree_hash(repo),
            "candidate_import_spec": args.candidate_import,
            "candidate_source_sha256": candidate_source_digest,
            "candidate_source_receipt": source_receipt(candidate_source_files, repo),
            "card_table_semantic_sha256": card_table_verification["table_sha256"],
            "loaded_artifacts": loaded_receipt,
            "paired_seed_claim": False,
            "training_performed": False,
            "started_epoch": time.time(),
            "task_count": len(tasks),
            "resumable": True,
        }
        write_sealed_json(run_dir / "run-plan.json", plan)
        if _evidence_bytes(run_dir) > max_evidence_bytes:
            raise ValueError("run plan exceeds configured evidence byte cap")

    session_started_monotonic = time.monotonic()
    session_deadline_monotonic = _fresh_session_deadline(
        int(canary["wall_seconds"]), session_started_monotonic
    )
    session_id = unique_run_id("b0-session")
    script_path = Path(__file__).resolve()
    stop_reason: str | None = None
    for task in tasks:
        arm, anchor, player, ordinal, policy0, policy1 = task
        game_id = _task_id(run_id, arm, anchor, player, ordinal)
        if game_id in seen_ids:
            continue
        if time.monotonic() >= session_deadline_monotonic:
            record = _failure_record(
                game_id=game_id,
                arm=arm,
                anchor=anchor,
                player=player,
                policy0=policy0,
                policy1=policy1,
                failure_kind="arena_wall_timeout",
                missing_output=1,
            )
        elif _evidence_bytes(run_dir) >= max_evidence_bytes:
            stop_reason = "evidence_cap"
            break
        else:
            command = _worker_command(
                script_path=script_path,
                repo=repo,
                config_path=config_path,
                engine_root=args.engine_root,
                card_data=args.card_data,
                card_table=args.card_table,
                default_deck=args.default_deck,
                private_baselines=args.private_baselines,
                candidate_import=args.candidate_import,
                candidate_policy_id=config["candidate"]["policy_id"],
                game_id=game_id,
                anchor=anchor,
                arm=arm,
                player=player,
                policy0=policy0,
                policy1=policy1,
                request_cap=config["mechanical_canary"]["request_cap"],
                game_timeout=config["mechanical_canary"]["game_timeout_seconds"],
                permutation_count=args.permutation_count,
            )
            try:
                completed = subprocess.run(
                    command,
                    cwd=repo,
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=int(config["mechanical_canary"]["game_timeout_seconds"]) + 10,
                    env={
                        **os.environ,
                        "UV_CACHE_DIR": str(repo / "data/cache/uv"),
                        "PYTHONPYCACHEPREFIX": str(repo / "data/cache/pycache"),
                    },
                )
                if completed.returncode != 0:
                    record = _failure_record(
                        game_id=game_id,
                        arm=arm,
                        anchor=anchor,
                        player=player,
                        policy0=policy0,
                        policy1=policy1,
                        failure_kind="worker_exit",
                        missing_output=1,
                        error_message=completed.stderr[-300:],
                    )
                else:
                    try:
                        record = json.loads(completed.stdout)
                        required_fields = {
                            "game_id",
                            "arm",
                            "anchor",
                            "candidate_player",
                            "policy0",
                            "policy1",
                            "status",
                            "summary",
                            "action_latencies_ms",
                            "candidate_action_latencies_ms",
                            "process_metrics",
                            "permutation_control",
                        }
                        if (
                            not isinstance(record, dict)
                            or record.get("game_id") != game_id
                            or set(record) < required_fields
                            or record.get("arm") != arm
                            or record.get("anchor") != anchor
                            or record.get("candidate_player") != player
                            or not isinstance(record.get("summary"), dict)
                        ):
                            raise ValueError("worker JSON has the wrong game identity")
                    except (TypeError, ValueError, json.JSONDecodeError) as error:
                        record = _failure_record(
                            game_id=game_id,
                            arm=arm,
                            anchor=anchor,
                            player=player,
                            policy0=policy0,
                            policy1=policy1,
                            failure_kind="missing_output",
                            missing_output=1,
                            error_message=str(error),
                        )
            except subprocess.TimeoutExpired:
                record = _failure_record(
                    game_id=game_id,
                    arm=arm,
                    anchor=anchor,
                    player=player,
                    policy0=policy0,
                    policy1=policy1,
                    failure_kind="process_timeout",
                    missing_output=1,
                )
        match_path = matches_dir / f"{game_id}.json"
        if _evidence_bytes(run_dir) + _sealed_payload_size(match_path, record) > max_evidence_bytes:
            stop_reason = "evidence_cap"
            break
        records[arm].append(record)
        write_sealed_json(match_path, record)
        seen_ids.add(game_id)
        if _should_stop_after_record(record, config["mechanical_canary"]["stop_condition"]):
            stop_reason = record.get("failure_kind") or record.get("summary", {}).get(
                "failure_kind", "reliability_failure"
            )
            break
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
    combined_reliability = {
        key: candidate_aggregate["reliability"][key] + control_aggregate["reliability"][key]
        for key in candidate_aggregate["reliability"]
    }
    permutation_records = [
        record.get("permutation_control", {}) for record in records["candidate"]
    ]
    permutation = {
        "permutations_requested": args.permutation_count,
        "permutations_executed": sum(
            int(value.get("permutations_requested", 0)) for value in permutation_records
        ),
        "games_checked": len(permutation_records),
        "policy_reset_before_each_permutation": True,
        "pass": bool(permutation_records)
        and all(value.get("pass") is True for value in permutation_records)
        and all(
            int(value.get("permutations_requested", 0)) == args.permutation_count
            for value in permutation_records
        ),
        "status": "PASS" if permutation_records and all(value.get("pass") is True for value in permutation_records) else "FAILED",
        "paired_seed_claim": False,
    }
    aggregate = {
        "candidate_arm": candidate_aggregate,
        "control_arm": control_aggregate,
        "candidate_control_bootstrap_delta": candidate_aggregate.get("control_bootstrap_score_delta"),
        "games_requested": len(tasks),
        "games_recorded": len(records["candidate"]) + len(records["control"]),
        "games_completed": candidate_aggregate["games_completed"] + control_aggregate["games_completed"],
        "stop_reason": stop_reason,
        "resumed": resumed,
        "session_id": session_id,
        "session_wall_seconds": time.monotonic() - session_started_monotonic,
        "cumulative_wall_seconds": max(0.0, time.time() - float(plan["started_epoch"])),
        "reliability": combined_reliability,
        "promotable_reliability": (
            len(records["candidate"]) + len(records["control"]) == len(tasks)
            and not any(combined_reliability.values())
        ),
        "process_metrics": {
            "candidate_cpu_seconds": sum(
                float(record.get("process_metrics", {}).get("cpu_seconds", 0.0))
                for record in records["candidate"]
            ),
            "control_cpu_seconds": sum(
                float(record.get("process_metrics", {}).get("cpu_seconds", 0.0))
                for record in records["control"]
            ),
            "candidate_peak_rss_bytes": max(
                (int(record.get("process_metrics", {}).get("peak_rss_bytes", 0)) for record in records["candidate"]),
                default=0,
            ),
            "control_peak_rss_bytes": max(
                (int(record.get("process_metrics", {}).get("peak_rss_bytes", 0)) for record in records["control"]),
                default=0,
            ),
        },
    }
    report = sanitized_report(
        run_id=run_id,
        config=config,
        aggregate=aggregate,
        repository=plan["repository"],
        platform=plan["platform"],
        source_sha256=plan["source_sha256"],
        loaded_artifacts=plan["loaded_artifacts"],
        permutation=permutation,
        command=plan["command"],
        candidate_source_sha256=plan["candidate_source_sha256"],
        card_table_semantic_sha256=plan["card_table_semantic_sha256"],
    )
    match_digests = {
        path.relative_to(run_dir).as_posix(): {
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for path in sorted(matches_dir.glob("*.json"))
    }
    manifest = {
        **report,
        "run_plan_sha256": sha256_file(run_dir / "run-plan.json"),
        "raw_run_dir": run_dir.relative_to(repo).as_posix(),
        "match_digests": match_digests,
        "evidence_bytes": _evidence_bytes(run_dir),
        "max_evidence_bytes": max_evidence_bytes,
        "session_id": session_id,
        "resumed": resumed,
    }
    manifest_path = run_dir / ("run_manifest.json" if not resumed else f"run_manifest-{session_id}.json")
    manifest["manifest_path"] = manifest_path.relative_to(run_dir).as_posix()
    if _evidence_bytes(run_dir) + _sealed_payload_size(manifest_path, manifest) > max_evidence_bytes:
        raise ValueError("run manifest exceeds configured evidence byte cap")
    write_sealed_json(manifest_path, manifest)
    if args.output is not None:
        output = _inside(args.output, repo, strict=False)
        if _evidence_bytes(run_dir) + _sealed_payload_size(output, report) > max_evidence_bytes:
            raise ValueError("sanitized report exceeds configured evidence byte cap")
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
