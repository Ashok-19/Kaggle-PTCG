from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping, Sequence

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
from .models import (
    CompoundActionV1,
    ENTITY_FEATURE_NAMES,
    EngineObservationV1,
    EpisodeSummaryV1,
    LegalOptionV1,
    NumericTensorV1,
    EVENT_FEATURE_NAMES,
    GLOBAL_FEATURE_NAMES,
    OPTION_FEATURE_NAMES,
    PLAYER_FEATURE_NAMES,
    SchemaMetadataV1,
    SelectionRequestV1,
    TransitionRecordV1,
    VisibleEntityV1,
    schema_descriptor,
    stable_hash,
)
from .native import NativeCABTTransport, load_deck
from .semantic import (
    NUMERIC_DROPPED_PUBLIC_FIELDS,
    NUMERIC_FIELD_COVERAGE,
    OPTION_NAMES,
    SELECT_NAMES,
)


def add_g1_parsers(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    g1 = commands.add_parser("g1").add_subparsers(dest="g1_command", required=True)
    inventory = g1.add_parser("inventory")
    inventory.add_argument("--output", type=Path)
    schema = g1.add_parser("schema-export")
    schema.add_argument("--output", type=Path, default=Path("reports/contracts/g1-schema-hashes.json"))
    g1.add_parser("validate")
    for name in ("smoke", "cloud-validate"):
        smoke = g1.add_parser(name)
        smoke.add_argument("--engine-root", type=Path, required=True)
        smoke.add_argument("--card-data", type=Path, required=True)
        smoke.add_argument("--deck", type=Path, required=True)
        smoke.add_argument("--games", type=int, default=50)
        smoke.add_argument("--request-cap", type=int, default=20_000)
        smoke.add_argument("--wall-seconds", type=int, default=1_800)
        smoke.add_argument("--seed", type=int, default=17)
        smoke.add_argument("--output", type=Path)
        smoke.add_argument(
            "--failure-mode", choices=tuple(mode.value for mode in FailureMode), default="development"
        )
        if name == "cloud-validate":
            smoke.add_argument("--contract-only", action="store_true", required=True)
    arena = g1.add_parser("arena")
    arena.add_argument("--engine-root", type=Path, required=True)
    arena.add_argument("--card-data", type=Path, required=True)
    arena.add_argument("--default-deck", type=Path, required=True)
    arena.add_argument("--private-baselines", type=Path, required=True)
    arena.add_argument("--policies", default="random,first,rule:dragapult-ex,rule:iono,rule:mega-abomasnow-ex,rule:mega-lucario-ex")
    arena.add_argument("--games-per-cell", type=int, required=True)
    arena.add_argument("--workers", type=int, default=4)
    arena.add_argument("--request-cap", type=int, default=20_000)
    arena.add_argument("--game-timeout", type=int, default=300)
    arena.add_argument("--wall-seconds", type=int, default=7_200)
    arena.add_argument("--max-evidence-bytes", type=int, default=1_073_741_824)
    arena.add_argument("--seed", type=int, default=17)
    arena.add_argument("--output", type=Path)
    arena.add_argument("--resume", action="store_true")
    one = g1.add_parser("arena-one")
    one.add_argument("--engine-root", type=Path, required=True)
    one.add_argument("--card-data", type=Path, required=True)
    one.add_argument("--default-deck", type=Path, required=True)
    one.add_argument("--private-baselines", type=Path, required=True)
    one.add_argument("--policy0", required=True)
    one.add_argument("--policy1", required=True)
    one.add_argument("--seed", type=int, required=True)
    one.add_argument("--game-id", required=True)
    one.add_argument("--request-cap", type=int, required=True)
    one.add_argument("--game-timeout", type=int, required=True)
    one.add_argument("--failure-directory", type=Path, required=True)
    acceptance = g1.add_parser("acceptance-contract")
    acceptance.add_argument("--valid-operations", type=int, default=1_000_000)
    acceptance.add_argument("--output", type=Path)
    raw = g1.add_parser("raw-one")
    raw.add_argument("--engine-root", type=Path, required=True)
    raw.add_argument("--default-deck", type=Path, required=True)
    raw.add_argument("--game-id", required=True)
    raw.add_argument("--request-cap", type=int, required=True)
    raw.add_argument("--game-timeout", type=int, required=True)
    benchmark = g1.add_parser("benchmark")
    benchmark.add_argument("--engine-root", type=Path, required=True)
    benchmark.add_argument("--card-data", type=Path, required=True)
    benchmark.add_argument("--default-deck", type=Path, required=True)
    benchmark.add_argument("--private-baselines", type=Path, required=True)
    benchmark.add_argument("--rule-policy", default="rule:dragapult-ex")
    benchmark.add_argument("--workers", default="1,2,4,8")
    benchmark.add_argument("--games-per-point", type=int, required=True)
    benchmark.add_argument("--request-cap", type=int, default=20_000)
    benchmark.add_argument("--game-timeout", type=int, default=300)
    benchmark.add_argument("--seed", type=int, default=17)
    benchmark.add_argument("--profile-evidence", type=Path)
    benchmark.add_argument("--output", type=Path)
    compare = g1.add_parser("engine-compare")
    compare.add_argument("--shipped-engine-root", type=Path, required=True)
    compare.add_argument("--built-engine-root", type=Path, required=True)
    compare.add_argument("--card-data", type=Path, required=True)
    compare.add_argument("--default-deck", type=Path, required=True)
    compare.add_argument("--private-baselines", type=Path, required=True)
    compare.add_argument("--games-per-library", type=int, required=True)
    compare.add_argument("--workers", type=int, default=4)
    compare.add_argument("--request-cap", type=int, default=20_000)
    compare.add_argument("--game-timeout", type=int, default=300)
    compare.add_argument("--seed", type=int, default=17)
    compare.add_argument("--ks-max", type=float, required=True)
    compare.add_argument("--mean-relative-max", type=float, required=True)
    compare.add_argument("--mean-se-floor", type=float, required=True)
    compare.add_argument("--output", type=Path)
    soak = g1.add_parser("rss-soak")
    soak.add_argument("--engine-root", type=Path, required=True)
    soak.add_argument("--card-data", type=Path, required=True)
    soak.add_argument("--default-deck", type=Path, required=True)
    soak.add_argument("--private-baselines", type=Path, required=True)
    soak.add_argument("--policy", default="first")
    soak.add_argument("--workers", type=int, default=4)
    soak.add_argument("--duration-seconds", type=int, required=True)
    soak.add_argument("--sample-seconds", type=int, required=True)
    soak.add_argument("--warmup-seconds", type=int, required=True)
    soak.add_argument("--peak-bytes-per-worker", type=int, required=True)
    soak.add_argument("--slope-upper-mib-per-hour", type=float, required=True)
    soak.add_argument("--max-evidence-bytes", type=int, default=1_073_741_824)
    soak.add_argument("--force-restart-after-seconds", type=int)
    soak.add_argument("--request-cap", type=int, default=20_000)
    soak.add_argument("--game-timeout", type=int, default=300)
    soak.add_argument("--seed", type=int, default=17)
    soak.add_argument("--output", type=Path)
    soak.add_argument("--resume", action="store_true")
    verification = g1.add_parser("verify-suite")
    verification.add_argument("--output", type=Path)
    verdict = g1.add_parser("recalculate-gate")
    verdict.add_argument("--output", type=Path, default=Path("reports/gates/g1r.json"))


def _asset_hashes(repo: Path) -> tuple[str, str]:
    manifest = json.loads((repo / "asset_hashes.redacted.json").read_text(encoding="utf-8"))
    hashes = manifest["assets"]["official"]["signature_sha256"]
    return hashes["engine_library"], hashes["card_data"]


def _metadata(repo: Path) -> SchemaMetadataV1:
    engine, cards = _asset_hashes(repo)
    return SchemaMetadataV1.build(engine, cards)


def _write(repo: Path, path: Path, value: dict[str, Any]) -> Path:
    output = path if path.is_absolute() else repo / path
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)
    return output


def _code_hash(repo: Path) -> str:
    return source_tree_hash(repo)


def _artifact(path: Path, common: Path) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    return {
        "path": resolved.relative_to(common).as_posix(),
        "bytes": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }


def hash_loaded_artifacts(engine_root: Path, card_data: Path, deck: Path) -> dict[str, Any]:
    engine_root = engine_root.resolve(strict=True)
    machine = platform.machine()
    library_name = (
        "libcg-arm64.so" if machine in {"arm64", "aarch64"} else "libcg.so"
    )
    paths = {
        "engine_library": engine_root / "cg" / library_name,
        "game_wrapper": engine_root / "cg" / "game.py",
        "api_wrapper": engine_root / "cg" / "api.py",
        "sim_wrapper": engine_root / "cg" / "sim.py",
        "card_data": card_data.resolve(strict=True),
        "deck": deck.resolve(strict=True),
    }
    common = Path(os.path.commonpath([str(path.resolve()) for path in paths.values()]))
    if common.is_file():
        common = common.parent
    return {name: _artifact(path, common) for name, path in paths.items()}


def smoke_is_promotable(metrics: Mapping[str, Any], requested_games: int) -> bool:
    return metrics.get("games_completed") == requested_games and all(
        metrics.get(name) == 0
        for name in (
            "invalid_selections",
            "failures",
            "timeouts",
            "post_terminal_actions",
            "fallback_actions",
        )
    )


def export_schema(repo: Path, output: Path | None = None) -> dict[str, Any]:
    metadata = _metadata(repo)
    result = {
        "schema_version": 1,
        "metadata": asdict(metadata),
        "observation": {
            "records": schema_descriptor(VisibleEntityV1, EngineObservationV1, NumericTensorV1),
            "entity_features": ENTITY_FEATURE_NAMES,
            "player_features": PLAYER_FEATURE_NAMES,
            "event_features": EVENT_FEATURE_NAMES,
            "global_features": GLOBAL_FEATURE_NAMES,
            "numeric_drop_allowlist": NUMERIC_DROPPED_PUBLIC_FIELDS,
            "numeric_field_coverage": NUMERIC_FIELD_COVERAGE,
        },
        "action": {
            "records": schema_descriptor(LegalOptionV1, SelectionRequestV1, CompoundActionV1),
            "option_features": OPTION_FEATURE_NAMES,
        },
        "trajectory": schema_descriptor(TransitionRecordV1, EpisodeSummaryV1),
    }
    if output is not None:
        _write(repo, output, result)
    return result


def validate_contract(repo: Path) -> dict[str, Any]:
    inventory = json.loads((repo / "contracts" / "native_inventory.v2.json").read_text(encoding="utf-8"))
    metadata = _metadata(repo)
    issues = []
    if inventory.get("schema_version") != 2:
        issues.append("native inventory schema_version is not 2")
    if inventory.get("engine_library_sha256") != metadata.engine_sha256:
        issues.append("native inventory engine hash differs from asset manifest")
    if inventory.get("card_data_sha256") != metadata.card_data_sha256:
        issues.append("native inventory card-data hash differs from asset manifest")
    if inventory["result_values"].get("-1") != "ONGOING":
        issues.append("ongoing result contract is missing")
    return {
        "status": "fail" if issues else "pass",
        "issues": issues,
        "inventory_sha256": stable_hash(inventory),
        "schema_metadata": asdict(metadata),
    }


def _aggregate(summaries: Sequence[EpisodeSummaryV1]) -> dict[str, Any]:
    selection: dict[str, int] = {}
    options: dict[str, int] = {}
    for summary in summaries:
        for key, count in summary.selection_type_counts.items():
            name = SELECT_NAMES.get(int(key), f"UNKNOWN_{key}")
            selection[name] = selection.get(name, 0) + count
        for key, count in summary.option_type_counts.items():
            options[key] = options.get(key, 0) + count
    return {
        "games_started": len(summaries),
        "games_completed": sum(item.terminal_result is not None for item in summaries),
        "engine_requests": sum(item.engine_requests for item in summaries),
        "meaningful_choices": sum(item.meaningful_choices for item in summaries),
        "forced_requests": sum(item.forced_requests for item in summaries),
        "multi_select_requests": sum(item.multi_select_requests for item in summaries),
        "invalid_selections": sum(item.invalid_selections for item in summaries),
        "post_terminal_actions": sum(item.post_terminal_actions for item in summaries),
        "fallback_actions": sum(item.fallback_actions for item in summaries),
        "failures": sum(item.failure_kind is not None for item in summaries),
        "timeouts": sum(item.failure_kind == "timeout" for item in summaries),
        "max_observed_options": max((item.max_observed_options for item in summaries), default=0),
        "max_observed_select_count": max(
            (item.max_observed_select_count for item in summaries), default=0
        ),
        "selection_type_coverage": selection,
        "option_type_coverage": options,
        "unseen_selection_types": sorted(set(SELECT_NAMES.values()) - set(selection)),
        "unseen_option_types": sorted(set(OPTION_NAMES.values()) - set(options)),
    }


def run_smoke(args: argparse.Namespace, repo: Path) -> dict[str, Any]:
    if args.games <= 0 or args.request_cap <= 0 or args.wall_seconds <= 0:
        raise ValueError("games, request-cap, and wall-seconds must be positive")
    engine_root = args.engine_root.resolve(strict=True)
    card_data = args.card_data.resolve(strict=True)
    deck_path = args.deck.resolve(strict=True)
    artifacts = hash_loaded_artifacts(engine_root, card_data, deck_path)
    deck = load_deck(deck_path)
    metadata = SchemaMetadataV1.build(
        artifacts["engine_library"]["sha256"], artifacts["card_data"]["sha256"]
    )
    run_id = unique_run_id("g1r-native-smoke")
    output_argument = args.output or Path("runs") / run_id / "run_manifest.json"
    output = output_argument if output_argument.is_absolute() else repo / output_argument
    output = output.resolve()
    started = time.monotonic()
    deadline = started + args.wall_seconds
    summaries: list[EpisodeSummaryV1] = []
    remaining_requests = args.request_cap
    for game_index in range(args.games):
        if time.monotonic() >= deadline or remaining_requests <= 0:
            break
        policies = (
            {0: RandomLegalPolicy(args.seed + game_index), 1: DeterministicFirstLegalPolicy()}
            if game_index % 2 == 0
            else {0: DeterministicFirstLegalPolicy(), 1: RandomLegalPolicy(args.seed + game_index)}
        )
        environment = EpisodeEnvironmentV1(
            NativeCABTTransport(engine_root),
            metadata,
            max_requests=remaining_requests,
            deadline_monotonic=deadline,
            failure_directory=output.parent / "failures",
            failure_mode=FailureMode(args.failure_mode),
        )
        try:
            result = environment.run(
                f"{run_id}-game-{game_index:05d}-{uuid.uuid4().hex}", deck, deck, policies
            )
        except DevelopmentEpisodeError as error:
            result = error.result
        summaries.append(result.summary)
        remaining_requests -= result.summary.engine_requests
        if result.summary.failure_kind is not None or result.summary.fallback_actions:
            break
    metrics = _aggregate(summaries)
    wall_seconds = time.monotonic() - started
    config = {
        "games": args.games,
        "request_cap": args.request_cap,
        "wall_seconds": args.wall_seconds,
        "seed": args.seed,
        "failure_mode": args.failure_mode,
        "roles": "random-legal and deterministic-first-legal alternate player seats",
        "training": False,
    }
    passed = smoke_is_promotable(metrics, args.games)
    manifest = {
        **technical_run_envelope(repo, output, run_id, "ptcg.g1.smoke", passed),
        "kind": "run",
        "purpose": "Bounded CABT environment/action contract correctness smoke",
        "code_sha256": _code_hash(repo),
        "repository": git_state(repo),
        "platform": platform_record(),
        "command": list(sys.argv),
        "loaded_artifacts": artifacts,
        "config": config,
        "config_sha256": stable_hash(config),
        "schema_metadata": asdict(metadata),
        "metrics": metrics,
        "observed_not_guaranteed": {
            "max_options": metrics["max_observed_options"],
            "max_select_count": metrics["max_observed_select_count"],
        },
        "guaranteed_capacities_source": "contracts/native_inventory.v2.json",
        "wall_seconds": wall_seconds,
        "local_cost_usd": 0.0,
        "training_performed": False,
    }
    write_immutable_json(output, manifest)
    seal = output.with_suffix(output.suffix + ".sha256")
    with seal.open("x", encoding="ascii") as destination:
        destination.write(f"{sha256_file(output)}  {output.name}\n")
    return manifest


def run_g1(args: argparse.Namespace, repo: Path) -> dict[str, Any]:
    if args.g1_command == "acceptance-contract":
        from .acceptance import run_contract_acceptance

        return run_contract_acceptance(args, repo)
    if args.g1_command == "raw-one":
        from .benchmark import run_raw_match

        return run_raw_match(args, repo)
    if args.g1_command == "benchmark":
        from .benchmark import run_benchmark

        return run_benchmark(args, repo)
    if args.g1_command == "engine-compare":
        from .engine_compare import run_engine_compare

        return run_engine_compare(args, repo)
    if args.g1_command == "rss-soak":
        from .soak import run_soak

        return run_soak(args, repo)
    if args.g1_command == "verify-suite":
        from .verification import run_verification

        return run_verification(args, repo)
    if args.g1_command == "recalculate-gate":
        from .verdict import recalculate_gate

        return recalculate_gate(args, repo)
    if args.g1_command == "arena-one":
        from .arena import run_one_native_match

        return run_one_native_match(args, repo)
    if args.g1_command == "arena":
        from .arena import run_arena

        return run_arena(args, repo)
    if args.g1_command == "inventory":
        inventory = json.loads(
            (repo / "contracts" / "native_inventory.v2.json").read_text(encoding="utf-8")
        )
        if args.output:
            _write(repo, args.output, inventory)
        return {"status": "pass", "inventory_sha256": stable_hash(inventory)}
    if args.g1_command == "schema-export":
        result = export_schema(repo, args.output)
        return {"status": "pass", **result["metadata"]}
    if args.g1_command == "validate":
        return validate_contract(repo)
    if args.g1_command == "cloud-validate":
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "tests/unit", "tests/integration"],
            cwd=repo,
            check=False,
        )
        if completed.returncode:
            return {"status": "fail", "contract_tests_exit_code": completed.returncode}
    result = run_smoke(args, repo)
    return {
        "status": "pass" if result["internal_verdict"] == "PASS" else "fail",
        "manifest": result["source_path"],
        **result["metrics"],
    }
