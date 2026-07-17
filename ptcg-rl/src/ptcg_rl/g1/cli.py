from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from .actions import DeterministicFirstLegalPolicy, RandomLegalPolicy
from .environment import EpisodeEnvironmentV1
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
    SchemaMetadataV1,
    SelectionRequestV1,
    TransitionRecordV1,
    VisibleEntityV1,
    schema_descriptor,
    stable_hash,
)
from .native import NativeCABTTransport, load_deck
from .semantic import OPTION_NAMES, SELECT_NAMES


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
        smoke.add_argument("--deck", type=Path, required=True)
        smoke.add_argument("--games", type=int, default=50)
        smoke.add_argument("--request-cap", type=int, default=20_000)
        smoke.add_argument("--wall-seconds", type=int, default=1_800)
        smoke.add_argument("--seed", type=int, default=17)
        smoke.add_argument(
            "--output", type=Path, default=Path("reports/runs/g1-native-smoke.json")
        )
        if name == "cloud-validate":
            smoke.add_argument("--contract-only", action="store_true", required=True)


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
    digest = hashlib.sha256()
    roots = (repo / "src" / "ptcg_rl" / "g1", repo / "contracts")
    for root in roots:
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            digest.update(path.relative_to(repo).as_posix().encode("utf-8"))
            digest.update(path.read_bytes())
    return digest.hexdigest()


def export_schema(repo: Path, output: Path | None = None) -> dict[str, Any]:
    metadata = _metadata(repo)
    result = {
        "schema_version": 1,
        "metadata": asdict(metadata),
        "observation": {
            "records": schema_descriptor(VisibleEntityV1, EngineObservationV1, NumericTensorV1),
            "entity_features": ENTITY_FEATURE_NAMES,
            "event_features": EVENT_FEATURE_NAMES,
            "global_features": GLOBAL_FEATURE_NAMES,
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
    inventory = json.loads((repo / "contracts" / "native_inventory.v1.json").read_text(encoding="utf-8"))
    metadata = _metadata(repo)
    issues = []
    if inventory.get("schema_version") != 1:
        issues.append("native inventory schema_version is not 1")
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
    deck = load_deck(args.deck)
    metadata = _metadata(repo)
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
            NativeCABTTransport(args.engine_root),
            metadata,
            max_requests=remaining_requests,
            deadline_monotonic=deadline,
            failure_directory=repo / "runs" / "g1-native-smoke" / "failures",
        )
        result = environment.run(f"g1-smoke-{game_index:03d}", deck, deck, policies)
        summaries.append(result.summary)
        remaining_requests -= result.summary.engine_requests
        if result.summary.invalid_selections:
            break
    metrics = _aggregate(summaries)
    wall_seconds = time.monotonic() - started
    config = {
        "games": args.games,
        "request_cap": args.request_cap,
        "wall_seconds": args.wall_seconds,
        "seed": args.seed,
        "roles": "random-legal and deterministic-first-legal alternate player seats",
        "training": False,
    }
    now = datetime.now(timezone.utc).isoformat()
    source_path = (args.output if not args.output.is_absolute() else args.output.relative_to(repo)).as_posix()
    status = "PASS" if (
        metrics["invalid_selections"] == 0
        and metrics["post_terminal_actions"] == 0
        and metrics["games_started"] == metrics["games_completed"] + metrics["failures"]
    ) else "FAIL"
    manifest = {
        "schema_version": 1,
        "record_id": "run-g1-native-smoke",
        "created_at_utc": now,
        "updated_at_utc": now,
        "source_path": source_path,
        "producer": "ptcg.g1.smoke",
        "producer_version": "1",
        "run_id": "g1-native-smoke",
        "gate_id": "G1",
        "kind": "run",
        "status": status,
        "purpose": "Bounded CABT environment/action contract correctness smoke",
        "code_sha256": _code_hash(repo),
        "config": config,
        "config_sha256": stable_hash(config),
        "schema_metadata": asdict(metadata),
        "metrics": metrics,
        "observed_not_guaranteed": {
            "max_options": metrics["max_observed_options"],
            "max_select_count": metrics["max_observed_select_count"],
        },
        "guaranteed_capacities_source": "contracts/native_inventory.v1.json",
        "wall_seconds": wall_seconds,
        "local_cost_usd": 0.0,
        "training_performed": False,
    }
    _write(repo, args.output, manifest)
    return manifest


def run_g1(args: argparse.Namespace, repo: Path) -> dict[str, Any]:
    if args.g1_command == "inventory":
        inventory = json.loads(
            (repo / "contracts" / "native_inventory.v1.json").read_text(encoding="utf-8")
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
    return {"status": result["status"].lower(), "manifest": result["source_path"], **result["metrics"]}
