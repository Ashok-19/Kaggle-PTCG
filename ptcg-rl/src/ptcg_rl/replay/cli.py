from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .acquisition import audit_acquisition, load_verified_plan, write_acquisition_records
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

    audit = subcommands.add_parser("audit-acquisition")
    audit.add_argument("--plan", type=Path, required=True)
    audit.add_argument("--episodes", type=Path, required=True)
    audit.add_argument("--receipt", type=Path, required=True)
    audit.add_argument("--report", type=Path, required=True)
    audit.add_argument("--provider", required=True)
    audit.add_argument("--acquired-at-utc")


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

    if args.replay_command == "audit-acquisition":
        plan = load_verified_plan(_resolve(repo, args.plan))
        report = audit_acquisition(
            plan,
            _resolve(repo, args.episodes),
            provider=args.provider,
            acquired_at_utc=args.acquired_at_utc,
        )
        receipt_path = _resolve(repo, args.receipt)
        report_path = _resolve(repo, args.report)
        write_acquisition_records(
            report,
            receipt_path=receipt_path,
            report_path=report_path,
        )
        return {
            "status": report["status"],
            "plan_sha256": report["plan_sha256"],
            "audit_sha256": report["audit_sha256"],
            "receipt_path": str(receipt_path.relative_to(repo)) if receipt_path.is_relative_to(repo) else str(receipt_path),
            "report_path": str(report_path.relative_to(repo)) if report_path.is_relative_to(repo) else str(report_path),
            **dict(report["acquisition"]),
            **dict(report["replay_contract"]),
        }

    path = _resolve(repo, args.plan)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReplayPlanError(f"cannot load plan {path}: {error}") from error
    return verify_plan(value)
