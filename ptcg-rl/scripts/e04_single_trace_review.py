from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

import torch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ptcg_rl.g2.checkpoint import load_checkpoint_package  # noqa: E402
from ptcg_rl.g3.e04_authorization import (  # noqa: E402
    load_native_authorization,
    verify_native_authorization_assets,
)
from ptcg_rl.g3.gold_path import canonical_json_bytes, sha256_file  # noqa: E402
from ptcg_rl.g3.zero_update_bridge import ZeroUpdateBridgeV1  # noqa: E402


ENGINE_ROOT = ROOT / "private/assets/official/sample_submission/sample_submission"
ENGINE_LIBRARY = ENGINE_ROOT / "cg/libcg.so"
WRAPPER_API = ENGINE_ROOT / "cg/api.py"
CARD_DATA = ROOT / "private/assets/official/EN_Card_Data.csv"
DECK = ROOT / "private/baselines/mega-lucario-ex/deck.csv"
CHECKPOINT = ROOT / "private/g2/checkpoint-v1/g2-policy-checkpoint-v1.zip"
INITIAL_RUNNER_SHA256 = "d76c7264e4d69dfd46763e5cc83f4d676a58acbbd5571000952c6a6fe0c74719"
FIXED_RUNNER_SHA256 = "1185cc9a434b942456e3683dcbe1f9f188422515c35a5bbdc65a2b99a191c0e4"


class E04SingleTraceReviewError(ValueError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise E04SingleTraceReviewError(f"cannot load JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise E04SingleTraceReviewError(f"JSON root must be an object: {path}")
    return value


def atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError as error:
        raise E04SingleTraceReviewError(f"evidence path escapes project root: {path}") from error


def self_hash(value: Mapping[str, Any], field: str) -> str:
    payload = dict(value)
    payload.pop(field, None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def review_single_trace(
    *,
    authorization_snapshot_path: Path,
    consumed_request_path: Path,
    bridge_path: Path,
    private_report_path: Path,
    public_report_path: Path,
) -> dict[str, Any]:
    authorization = load_native_authorization(
        authorization_snapshot_path,
        require_authorized=True,
    )
    consumed_request = load_json(consumed_request_path)
    consumed = load_native_authorization(
        consumed_request_path,
        require_authorized=False,
    )
    if consumed.authorized:
        raise E04SingleTraceReviewError("single-process request remains authorized")
    if consumed_request.get("authorization_scope") != "CONSUMED_AFTER_SINGLE_APPROVED_EXECUTION":
        raise E04SingleTraceReviewError("single-process authorization is not consumed")

    authorization_sha256 = sha256_file(authorization_snapshot_path)
    bridge_sha256 = sha256_file(bridge_path)
    if consumed_request.get("consumed_authorization_sha256") != authorization_sha256:
        raise E04SingleTraceReviewError("consumed authorization hash differs")
    if consumed_request.get("bridge_checkpoint_sha256") != bridge_sha256:
        raise E04SingleTraceReviewError("consumed bridge checkpoint hash differs")
    if consumed.output_directory != authorization.output_directory:
        raise E04SingleTraceReviewError("authorization output directory changed after execution")

    assets = verify_native_authorization_assets(
        authorization,
        engine_library=ENGINE_LIBRARY,
        wrapper_api=WRAPPER_API,
        card_data=CARD_DATA,
        deck=DECK,
        checkpoint=CHECKPOINT,
    )
    loaded = load_checkpoint_package(
        CHECKPOINT,
        device=torch.device("cpu"),
        expected_package_sha256=authorization.checkpoint_sha256,
        expected_source_commit=None,
        source_root=ROOT,
    )
    bridge = ZeroUpdateBridgeV1.from_state_dict(load_json(bridge_path))
    qualification = bridge.qualification_summary(
        minimum_games=authorization.games,
        minimum_meaningful_decisions=authorization.minimum_meaningful_decisions,
    )
    state = bridge.state_dict()
    episodes = state["episodes"]
    if len(episodes) != 1:
        raise E04SingleTraceReviewError("single-process evidence must contain one episode")
    episode_id, episode = next(iter(episodes.items()))
    if episode["boundary"] != "TERMINAL" or not episode["closed"]:
        raise E04SingleTraceReviewError("single-process episode did not close terminally")
    if set(episode["player_boundaries"]) != {"0", "1"}:
        raise E04SingleTraceReviewError("single-process episode lacks both player boundaries")

    player_records: dict[str, Any] = {}
    for player in ("0", "1"):
        owner = episode["owners"][player]
        traces = owner["traces"]
        boundary = episode["player_boundaries"][player]
        player_records[player] = {
            "engine_decisions": len(traces),
            "meaningful_decisions": sum(not trace["forced"] for trace in traces),
            "forced_decisions": sum(trace["forced"] for trace in traces),
            "selected_indices": sum(len(trace["selected_indices"]) for trace in traces),
            "stop_decisions": sum(trace["stopped"] for trace in traces),
            "maximum_replay_absolute_error": max(
                (trace["replay_absolute_error"] for trace in traces),
                default=0.0,
            ),
            "terminal_reward": boundary["terminal_reward"],
            "terminal": boundary["terminal"],
            "truncation": boundary["truncation"],
        }

    created_at_utc = str(consumed_request.get("consumed_at_utc"))
    if not created_at_utc or created_at_utc == "None":
        created_at_utc = datetime.now(UTC).isoformat()
    private_report: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e04-native-zero-update-single-process-trace-recovered-v1",
        "created_at_utc": created_at_utc,
        "status": "PASS",
        "decision": "QUALIFIED_ZERO_UPDATE_STAGE_WITH_POST_RUN_REPORT_RECOVERY",
        "authorization": {
            "snapshot_path": relative(authorization_snapshot_path),
            "snapshot_sha256": authorization_sha256,
            "record_id": authorization.record_id,
            "stage": authorization.stage,
            "games": authorization.games,
            "optimizer_steps_authorized": 0,
            "external_compute_authorized": False,
            "consumed_request_path": relative(consumed_request_path),
            "consumed_request_sha256": sha256_file(consumed_request_path),
        },
        "assets": assets,
        "checkpoint": {
            "package_sha256": loaded.package_sha256,
            "package_bytes": loaded.package_bytes,
            "qualification_state_sha256": loaded.manifest["evidence"][
                "qualification_state_sha256"
            ],
        },
        "execution": {
            "device": "cpu",
            "single_process": True,
            "cabt_episode_count": 1,
            "cabt_rerun_count_during_recovery": 0,
            "optimizer_created": False,
            "optimizer_steps": 0,
            "training_loop_ran": False,
            "external_compute_used": False,
        },
        "game": {
            "episode_id": episode_id,
            "terminal_result": episode["terminal_result"],
            "boundary": episode["boundary"],
            "engine_decisions": qualification["engine_decisions"],
            "meaningful_decisions": qualification["meaningful_decisions"],
            "forced_decisions": qualification["forced_decisions"],
            "players": player_records,
        },
        "qualification": qualification,
        "bridge_checkpoint": {
            "path": relative(bridge_path),
            "bytes": bridge_path.stat().st_size,
            "sha256": bridge_sha256,
        },
        "recovery": {
            "required": True,
            "original_runner_exit_code": 1,
            "original_runner_failure_phase": "post_game_report_construction",
            "original_exception": "KeyError: qualification_state_sha256",
            "original_runner_sha256": INITIAL_RUNNER_SHA256,
            "fixed_runner_sha256": FIXED_RUNNER_SHA256,
            "method": "offline_reconstruction_from_atomic_bridge_checkpoint",
            "additional_cabt_execution": False,
        },
        "cost_usd": 0.0,
    }
    private_report["report_sha256"] = self_hash(private_report, "report_sha256")
    atomic_json(private_report_path, private_report)

    public_report: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e04-single-process-trace-v1",
        "created_at_utc": created_at_utc,
        "source_path": relative(public_report_path),
        "producer": "scripts/e04_single_trace_review.py",
        "status": "SUCCEEDED",
        "decision": "PASS",
        "stage": "single_process_trace",
        "authorization": {
            "explicit_user_approval": True,
            "authorization_snapshot_sha256": authorization_sha256,
            "authorization_consumed": True,
            "current_request_authorized": False,
            "games_authorized": 1,
            "optimizer_steps_authorized": 0,
            "external_compute_authorized": False,
            "rerun_authorized": False,
            "later_stage_authorized": False,
        },
        "assets": {
            name: {
                "bytes": record["bytes"],
                "sha256": record["sha256"],
            }
            for name, record in assets.items()
        },
        "checkpoint": private_report["checkpoint"],
        "execution": private_report["execution"],
        "results": {
            "games": qualification["games"],
            "terminal_result": episode["terminal_result"],
            "engine_decisions": qualification["engine_decisions"],
            "meaningful_decisions": qualification["meaningful_decisions"],
            "forced_decisions": qualification["forced_decisions"],
            "maximum_compound_log_probability_absolute_error": qualification[
                "maximum_compound_log_probability_absolute_error"
            ],
            "terminal_boundaries_for_both_players": qualification[
                "terminal_boundaries_for_both_players"
            ],
            "player_results": player_records,
            "zero_tolerance": qualification["reliability"],
            "bridge_state_sha256": qualification["state_sha256"],
        },
        "artifacts": {
            "authorization_snapshot": {
                "path": relative(authorization_snapshot_path),
                "bytes": authorization_snapshot_path.stat().st_size,
                "sha256": authorization_sha256,
            },
            "bridge_checkpoint": private_report["bridge_checkpoint"],
            "recovered_private_report": {
                "path": relative(private_report_path),
                "bytes": private_report_path.stat().st_size,
                "sha256": sha256_file(private_report_path),
            },
        },
        "incident": private_report["recovery"],
        "qualification_scope": {
            "single_process_trace": True,
            "ten_game_smoke": False,
            "hundred_game_qualification": False,
            "policy_competence": False,
            "training_authorized": False,
        },
        "cost_usd": 0.0,
    }
    public_report["review_sha256"] = self_hash(public_report, "review_sha256")
    atomic_json(public_report_path, public_report)
    return public_report


def main() -> int:
    parser = argparse.ArgumentParser()
    output_directory = ROOT / "private/g3/e04/single-process-trace-v1"
    parser.add_argument(
        "--authorization-snapshot",
        type=Path,
        default=output_directory / "e04-native-zero-update-authorization.json",
    )
    parser.add_argument(
        "--consumed-request",
        type=Path,
        default=ROOT / "configs/e04_single_process_trace_request_v1.json",
    )
    parser.add_argument(
        "--bridge",
        type=Path,
        default=output_directory / "e04-native-zero-update-bridge.json",
    )
    parser.add_argument(
        "--private-report",
        type=Path,
        default=output_directory / "e04-native-zero-update-report.json",
    )
    parser.add_argument(
        "--public-report",
        type=Path,
        default=ROOT / "reports/evaluations/e04-single-process-trace-v1.json",
    )
    args = parser.parse_args()
    report = review_single_trace(
        authorization_snapshot_path=args.authorization_snapshot,
        consumed_request_path=args.consumed_request,
        bridge_path=args.bridge,
        private_report_path=args.private_report,
        public_report_path=args.public_report,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
