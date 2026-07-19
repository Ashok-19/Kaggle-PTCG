from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .planner import ReplayPlanError, build_plan, load_config, verify_plan, write_plan


def add_replay_parsers(commands: argparse._SubParsersAction[Any]) -> None:
    replay = commands.add_parser("replay")
    subcommands = replay.add_subparsers(dest="replay_command", required=True)

    plan = subcommands.add_parser("plan")
    plan.add_argument("--config", type=Path, required=True)
    plan.add_argument("--index-manifest", type=Path, required=True)
    plan.add_argument("--index-receipt", type=Path, required=True)
    plan.add_argument("--daily-manifest", type=Path, required=True)
    plan.add_argument("--daily-receipt", type=Path, required=True)
    plan.add_argument("--out", type=Path, required=True)

    verify = subcommands.add_parser("verify-plan")
    verify.add_argument("--plan", type=Path, required=True)


def _resolve(repo: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo / path


def run_replay(args: argparse.Namespace, repo: Path) -> dict[str, object]:
    if args.replay_command == "plan":
        config = load_config(_resolve(repo, args.config))
        plan = build_plan(
            config,
            _resolve(repo, args.index_manifest),
            _resolve(repo, args.index_receipt),
            _resolve(repo, args.daily_manifest),
            _resolve(repo, args.daily_receipt),
        )
        output = _resolve(repo, args.out)
        write_plan(plan, output)
        return {
            "status": "pass",
            "plan_path": str(output.relative_to(repo)) if output.is_relative_to(repo) else str(output),
            "plan_sha256": plan["plan_sha256"],
            **dict(plan["summary"]),
            "selected_items": plan["selected_items"],
        }

    path = _resolve(repo, args.plan)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReplayPlanError(f"cannot load plan {path}: {error}") from error
    return verify_plan(value)
