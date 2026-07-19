from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .acquisition import audit_acquisition, load_verified_plan, write_acquisition_records
from .independent_review import independently_review_semantic_report, write_review_report
from .semantic_loader import (
    ReplaySemanticError,
    audit_semantic_loader,
    load_verified_official_card_data_sha256,
    write_semantic_report,
)
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

    semantic = subcommands.add_parser("audit-semantic")
    semantic.add_argument("--plan", type=Path, required=True)
    semantic.add_argument("--episodes", type=Path, required=True)
    semantic.add_argument("--asset-hashes", type=Path, default=Path("asset_hashes.redacted.json"))
    semantic.add_argument(
        "--card-data-file",
        type=Path,
        default=Path("private/assets/official/EN_Card_Data.csv"),
    )
    semantic.add_argument("--card-data-sha256")
    semantic.add_argument("--report", type=Path, required=True)
    semantic.add_argument("--created-at-utc")
    semantic.add_argument("--expected-stream-sha256")
    semantic.add_argument("--max-peak-rss-mib", type=float, default=256.0)

    review = subcommands.add_parser("review-semantic")
    review.add_argument("--plan", type=Path, required=True)
    review.add_argument("--episodes", type=Path, required=True)
    review.add_argument("--semantic-report", type=Path, required=True)
    review.add_argument("--review-report", type=Path, required=True)
    review.add_argument("--created-at-utc")
    review.add_argument("--source-commit")
    review.add_argument("--asset-hashes", type=Path, default=Path("asset_hashes.redacted.json"))
    review.add_argument(
        "--card-data-file",
        type=Path,
        default=Path("private/assets/official/EN_Card_Data.csv"),
    )


def _resolve(repo: Path, path: Path) -> Path:
    return path if path.is_absolute() else repo / path


def _official_card_data_sha256(args: argparse.Namespace, repo: Path) -> str:
    verified = load_verified_official_card_data_sha256(
        _resolve(repo, args.asset_hashes),
        _resolve(repo, args.card_data_file),
    )
    supplied = getattr(args, "card_data_sha256", None)
    if supplied is not None and supplied != verified:
        raise ReplaySemanticError(
            "supplied card-data SHA-256 differs from verified official asset"
        )
    return verified


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

    if args.replay_command == "review-semantic":
        plan = load_verified_plan(_resolve(repo, args.plan))
        semantic_report = json.loads(
            _resolve(repo, args.semantic_report).read_text(encoding="utf-8")
        )
        official_card_data_sha256 = _official_card_data_sha256(args, repo)
        review = independently_review_semantic_report(
            plan,
            _resolve(repo, args.episodes),
            semantic_report,
            created_at_utc=args.created_at_utc,
            source_commit=args.source_commit,
            expected_card_data_sha256=official_card_data_sha256,
        )
        review_path = _resolve(repo, args.review_report)
        write_review_report(review, review_path)
        return {
            "status": review["status"],
            "decision": review["decision"],
            "semantic_stream_sha256": review["semantic_stream_sha256"],
            "review_sha256": review["review_sha256"],
            "review_report": str(review_path.relative_to(repo))
            if review_path.is_relative_to(repo)
            else str(review_path),
            **dict(review["recalculated_coverage"]),
        }

    if args.replay_command == "audit-semantic":
        plan = load_verified_plan(_resolve(repo, args.plan))
        report = audit_semantic_loader(
            plan,
            _resolve(repo, args.episodes),
            card_data_sha256=_official_card_data_sha256(args, repo),
            created_at_utc=args.created_at_utc,
            expected_stream_sha256=args.expected_stream_sha256,
            max_peak_rss_mib=args.max_peak_rss_mib,
        )
        report_path = _resolve(repo, args.report)
        write_semantic_report(report, report_path)
        return {
            "status": report["status"],
            "plan_sha256": report["plan_sha256"],
            "semantic_stream_sha256": report["semantic_stream_sha256"],
            "audit_sha256": report["audit_sha256"],
            "report_path": str(report_path.relative_to(repo))
            if report_path.is_relative_to(repo)
            else str(report_path),
            **dict(report["coverage"]),
            **dict(report["memory"]),
        }

    path = _resolve(repo, args.plan)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReplayPlanError(f"cannot load plan {path}: {error}") from error
    return verify_plan(value)
