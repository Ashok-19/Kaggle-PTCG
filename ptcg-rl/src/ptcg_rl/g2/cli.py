from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from .card_table import build_card_table, load_card_table, verify_card_table, write_card_table


def add_g2_parsers(commands: argparse._SubParsersAction[Any]) -> None:
    g2 = commands.add_parser("g2")
    subcommands = g2.add_subparsers(dest="g2_command", required=True)

    build = subcommands.add_parser("build-card-table")
    build.add_argument("--config", type=Path, required=True)

    verify = subcommands.add_parser("verify-card-table")
    verify.add_argument("--table", type=Path, required=True)


def _resolve(repo: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo / path


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _load_config(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot load G2 config {path}: {error}") from error
    config = _mapping(value, "G2 card-table config")
    allowed = {
        "schema_version",
        "card_csv",
        "expected_card_data_sha256",
        "sample_submission_root",
        "output",
    }
    unknown = sorted(set(config) - allowed)
    if unknown:
        raise ValueError(f"G2 card-table config has unknown keys: {', '.join(unknown)}")
    missing = sorted(allowed - set(config))
    if missing:
        raise ValueError(f"G2 card-table config is missing keys: {', '.join(missing)}")
    if config["schema_version"] != 1:
        raise ValueError("unsupported G2 card-table config schema version")
    return config


def run_g2(args: argparse.Namespace, repo: Path) -> dict[str, object]:
    if args.g2_command == "build-card-table":
        config = _load_config(_resolve(repo, args.config))
        output = _resolve(repo, Path(str(config["output"])))
        table = build_card_table(
            card_csv=_resolve(repo, Path(str(config["card_csv"]))),
            expected_card_data_sha256=str(config["expected_card_data_sha256"]),
            sample_submission_root=_resolve(
                repo, Path(str(config["sample_submission_root"]))
            ),
        )
        write_card_table(table, output)
        summary = verify_card_table(table)
        return {
            **summary,
            "output": str(output.relative_to(repo)) if output.is_relative_to(repo) else str(output),
            "card_data_sha256": table.card_data_sha256,
            "engine_library_sha256": table.engine_library_sha256,
            "wrapper_api_sha256": table.wrapper_api_sha256,
        }
    table = load_card_table(_resolve(repo, args.table))
    return verify_card_table(table)
