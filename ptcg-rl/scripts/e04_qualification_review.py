from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

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
DECISION = ROOT / "docs/decisions/DEC-012_E04_QUALIFICATION_RESIZED.md"
REPLAY_TOLERANCE = 1e-5
EXPECTED_GAMES = 180
EXPECTED_MINIMUM_MEANINGFUL_DECISIONS = 10_000
EXPECTED_CHECKPOINT_INTERVAL_GAMES = 10


class E04QualificationReviewError(ValueError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise E04QualificationReviewError(
            f"cannot load JSON {path}: {error}"
        ) from error
    if not isinstance(value, dict):
        raise E04QualificationReviewError(f"JSON root must be an object: {path}")
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
        raise E04QualificationReviewError(
            f"evidence path escapes project root: {path}"
        ) from error


def self_hash(value: Mapping[str, Any], field: str) -> str:
    payload = dict(value)
    payload.pop(field, None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def review_qualification(
    *,
    authorization_snapshot_path: Path,
    consumed_request_path: Path,
    games_path: Path,
    bridge_path: Path,
    private_report_path: Path,
    public_report_path: Path,
) -> dict[str, Any]:
    authorization = load_native_authorization(
        authorization_snapshot_path,
        require_authorized=True,
    )
    if (
        authorization.stage != "qualification"
        or authorization.games != EXPECTED_GAMES
        or authorization.minimum_meaningful_decisions
        != EXPECTED_MINIMUM_MEANINGFUL_DECISIONS
        or authorization.bridge_checkpoint_interval_games
        != EXPECTED_CHECKPOINT_INTERVAL_GAMES
    ):
        raise E04QualificationReviewError(
            "authorization is not the exact DEC-012 qualification stage"
        )

    consumed_request = load_json(consumed_request_path)
    consumed = load_native_authorization(
        consumed_request_path,
        require_authorized=False,
    )
    if consumed.authorized:
        raise E04QualificationReviewError("qualification request remains authorized")
    if consumed_request.get("authorization_scope") != (
        "CONSUMED_AFTER_180_GAME_APPROVED_EXECUTION"
    ):
        raise E04QualificationReviewError("qualification authorization is not consumed")

    authorization_sha256 = sha256_file(authorization_snapshot_path)
    if consumed_request.get("authorization_snapshot_sha256") != authorization_sha256:
        raise E04QualificationReviewError(
            "consumed authorization snapshot hash differs"
        )
    if consumed.output_directory != authorization.output_directory:
        raise E04QualificationReviewError(
            "authorization output directory changed after execution"
        )

    runner_path = ROOT / "scripts/e04_native_zero_update.py"
    validator_path = ROOT / "src/ptcg_rl/g3/e04_authorization.py"
    prerequisite_path = ROOT / str(
        consumed_request.get("prerequisite_evidence", "")
    )
    if sha256_file(runner_path) != consumed_request.get("runner_sha256"):
        raise E04QualificationReviewError("qualification runner hash differs")
    if sha256_file(validator_path) != consumed_request.get(
        "authorization_validator_sha256"
    ):
        raise E04QualificationReviewError(
            "qualification authorization validator hash differs"
        )
    if sha256_file(DECISION) != consumed_request.get("decision_sha256"):
        raise E04QualificationReviewError("DEC-012 hash differs")
    if sha256_file(prerequisite_path) != consumed_request.get(
        "prerequisite_evidence_sha256"
    ):
        raise E04QualificationReviewError(
            "ten-game prerequisite evidence hash differs"
        )

    assets = verify_native_authorization_assets(
        authorization,
        engine_library=ENGINE_LIBRARY,
        wrapper_api=WRAPPER_API,
        card_data=CARD_DATA,
        deck=DECK,
        checkpoint=CHECKPOINT,
    )
    private_report = load_json(private_report_path)
    ledger = load_json(games_path)
    bridge_state = load_json(bridge_path)
    bridge = ZeroUpdateBridgeV1.from_state_dict(bridge_state)
    qualification = bridge.qualification_summary(
        minimum_games=EXPECTED_GAMES,
        minimum_meaningful_decisions=EXPECTED_MINIMUM_MEANINGFUL_DECISIONS,
    )

    if private_report.get("status") != "PASS" or private_report.get(
        "decision"
    ) != "QUALIFIED_ZERO_UPDATE_STAGE":
        raise E04QualificationReviewError("native qualification report did not pass")
    execution = private_report.get("execution")
    if not isinstance(execution, Mapping):
        raise E04QualificationReviewError(
            "native qualification execution record is invalid"
        )
    if (
        execution.get("device") != "cpu"
        or execution.get("single_process") is not True
        or execution.get("optimizer_created") is not False
        or execution.get("optimizer_steps") != 0
        or execution.get("training_loop_ran") is not False
        or execution.get("bridge_checkpoint_interval_games")
        != EXPECTED_CHECKPOINT_INTERVAL_GAMES
    ):
        raise E04QualificationReviewError(
            "native qualification execution boundary differs"
        )

    report_authorization = private_report.get("authorization")
    if not isinstance(report_authorization, Mapping):
        raise E04QualificationReviewError(
            "native qualification report authorization is invalid"
        )
    if (
        report_authorization.get("sha256") != authorization_sha256
        or report_authorization.get("stage") != "qualification"
        or report_authorization.get("games") != EXPECTED_GAMES
        or report_authorization.get("optimizer_steps_authorized") != 0
        or report_authorization.get("external_compute_authorized") is not False
    ):
        raise E04QualificationReviewError(
            "native qualification report authorization differs"
        )

    report_games = private_report.get("games")
    ledger_games = ledger.get("games")
    if not isinstance(report_games, list) or not isinstance(ledger_games, list):
        raise E04QualificationReviewError(
            "native qualification game ledger is invalid"
        )
    if report_games != ledger_games or len(report_games) != EXPECTED_GAMES:
        raise E04QualificationReviewError(
            "native qualification report and game ledger differ"
        )
    if private_report.get("qualification") != qualification:
        raise E04QualificationReviewError(
            "native qualification summary differs from bridge reconstruction"
        )

    bridge_sha256 = sha256_file(bridge_path)
    games_sha256 = sha256_file(games_path)
    private_report_sha256 = sha256_file(private_report_path)
    if private_report.get("bridge_checkpoint", {}).get("sha256") != bridge_sha256:
        raise E04QualificationReviewError(
            "native qualification bridge hash differs"
        )
    if private_report.get("game_ledger", {}).get("sha256") != games_sha256:
        raise E04QualificationReviewError(
            "native qualification game-ledger hash differs"
        )
    if consumed_request.get("bridge_checkpoint_sha256") != bridge_sha256:
        raise E04QualificationReviewError(
            "consumed request bridge hash differs"
        )
    if consumed_request.get("game_ledger_sha256") != games_sha256:
        raise E04QualificationReviewError(
            "consumed request game-ledger hash differs"
        )
    if consumed_request.get("native_report_sha256") != private_report_sha256:
        raise E04QualificationReviewError(
            "consumed request native-report hash differs"
        )

    episodes = bridge_state.get("episodes")
    if not isinstance(episodes, Mapping) or len(episodes) != EXPECTED_GAMES:
        raise E04QualificationReviewError(
            "native qualification bridge episode count differs"
        )

    per_game: list[dict[str, Any]] = []
    terminal_result_counts = {"-1": 0, "0": 0, "1": 0}
    for expected_index, record in enumerate(report_games):
        if not isinstance(record, Mapping):
            raise E04QualificationReviewError(
                "native qualification game record is invalid"
            )
        episode_id = record.get("episode_id")
        expected_episode_id = f"e04-qualification-{expected_index:04d}"
        if (
            record.get("game_index") != expected_index
            or episode_id != expected_episode_id
        ):
            raise E04QualificationReviewError(
                "native qualification game ordering differs"
            )
        if record.get("failure") is not None:
            raise E04QualificationReviewError(
                f"native qualification game failed: {episode_id}"
            )
        summary = record.get("summary")
        episode = episodes.get(episode_id)
        if not isinstance(summary, Mapping) or not isinstance(episode, Mapping):
            raise E04QualificationReviewError(
                "native qualification game evidence is incomplete"
            )
        if episode.get("closed") is not True or episode.get("boundary") != "TERMINAL":
            raise E04QualificationReviewError(
                f"native qualification episode did not close: {episode_id}"
            )
        boundaries = episode.get("player_boundaries")
        owners = episode.get("owners")
        if not isinstance(boundaries, Mapping) or set(boundaries) != {"0", "1"}:
            raise E04QualificationReviewError(
                f"native qualification boundaries differ: {episode_id}"
            )
        if not isinstance(owners, Mapping) or set(owners) != {"0", "1"}:
            raise E04QualificationReviewError(
                f"native qualification owners differ: {episode_id}"
            )
        if any(
            boundary.get("terminal") is not True
            or boundary.get("truncation") is not False
            for boundary in boundaries.values()
        ):
            raise E04QualificationReviewError(
                f"native qualification terminal boundary differs: {episode_id}"
            )

        traces = [
            trace
            for owner in owners.values()
            for trace in owner.get("traces", [])
        ]
        engine_decisions = len(traces)
        meaningful_decisions = sum(not trace["forced"] for trace in traces)
        forced_decisions = sum(trace["forced"] for trace in traces)
        maximum_error = max(
            (trace["replay_absolute_error"] for trace in traces),
            default=0.0,
        )
        terminal_result = summary.get("terminal_result")
        if terminal_result not in (-1, 0, 1) or terminal_result != episode.get(
            "terminal_result"
        ):
            raise E04QualificationReviewError(
                f"native qualification terminal result differs: {episode_id}"
            )
        if (
            summary.get("engine_requests") != engine_decisions
            or summary.get("meaningful_choices") != meaningful_decisions
            or summary.get("forced_requests") != forced_decisions
            or summary.get("fallback_actions") != 0
            or summary.get("invalid_selections") != 0
            or summary.get("post_terminal_actions") != 0
            or summary.get("failure_kind") is not None
        ):
            raise E04QualificationReviewError(
                f"native qualification game counters differ: {episode_id}"
            )
        if maximum_error > REPLAY_TOLERANCE:
            raise E04QualificationReviewError(
                f"native qualification replay tolerance failed: {episode_id}"
            )
        terminal_result_counts[str(terminal_result)] += 1
        per_game.append(
            {
                "game_index": expected_index,
                "episode_id": episode_id,
                "terminal_result": terminal_result,
                "engine_decisions": engine_decisions,
                "meaningful_decisions": meaningful_decisions,
                "forced_decisions": forced_decisions,
                "maximum_replay_absolute_error": maximum_error,
                "wall_seconds": summary.get("wall_seconds"),
            }
        )

    if qualification["games"] != EXPECTED_GAMES:
        raise E04QualificationReviewError("qualification game count differs")
    if qualification["meaningful_decisions"] < (
        EXPECTED_MINIMUM_MEANINGFUL_DECISIONS
    ):
        raise E04QualificationReviewError(
            "qualification meaningful-decision floor failed"
        )
    if qualification["terminal_boundaries_for_both_players"] != EXPECTED_GAMES:
        raise E04QualificationReviewError(
            "qualification both-player terminal boundary count differs"
        )
    if any(qualification["reliability"].values()):
        raise E04QualificationReviewError(
            "qualification zero-tolerance counters are nonzero"
        )
    if qualification["maximum_compound_log_probability_absolute_error"] > (
        REPLAY_TOLERANCE
    ):
        raise E04QualificationReviewError(
            "qualification aggregate replay tolerance failed"
        )

    public_report: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e04-qualification-v1",
        "created_at_utc": private_report.get("created_at_utc"),
        "source_path": relative(public_report_path),
        "producer": "scripts/e04_qualification_review.py",
        "status": "SUCCEEDED",
        "decision": "PASS",
        "stage": "qualification",
        "authorization": {
            "explicit_user_approval": True,
            "authorization_snapshot_sha256": authorization_sha256,
            "authorization_consumed": True,
            "current_request_authorized": False,
            "games_authorized": EXPECTED_GAMES,
            "minimum_meaningful_decisions": (
                EXPECTED_MINIMUM_MEANINGFUL_DECISIONS
            ),
            "optimizer_steps_authorized": 0,
            "external_compute_authorized": False,
            "rerun_authorized": False,
            "later_native_stage_authorized": False,
        },
        "assets": {
            name: {"bytes": record["bytes"], "sha256": record["sha256"]}
            for name, record in assets.items()
        },
        "execution": dict(execution),
        "results": {
            "games": qualification["games"],
            "engine_decisions": qualification["engine_decisions"],
            "meaningful_decisions": qualification["meaningful_decisions"],
            "forced_decisions": qualification["forced_decisions"],
            "maximum_compound_log_probability_absolute_error": qualification[
                "maximum_compound_log_probability_absolute_error"
            ],
            "terminal_boundaries_for_both_players": qualification[
                "terminal_boundaries_for_both_players"
            ],
            "terminal_result_counts": terminal_result_counts,
            "zero_tolerance": qualification["reliability"],
            "bridge_state_sha256": qualification["state_sha256"],
            "per_game": per_game,
        },
        "artifacts": {
            "authorization_snapshot": {
                "path": relative(authorization_snapshot_path),
                "bytes": authorization_snapshot_path.stat().st_size,
                "sha256": authorization_sha256,
            },
            "current_consumed_request": {
                "path": relative(consumed_request_path),
                "bytes": consumed_request_path.stat().st_size,
                "sha256": sha256_file(consumed_request_path),
            },
            "game_ledger": {
                "path": relative(games_path),
                "bytes": games_path.stat().st_size,
                "sha256": games_sha256,
            },
            "bridge_checkpoint": {
                "path": relative(bridge_path),
                "bytes": bridge_path.stat().st_size,
                "sha256": bridge_sha256,
            },
            "native_report": {
                "path": relative(private_report_path),
                "bytes": private_report_path.stat().st_size,
                "sha256": private_report_sha256,
            },
        },
        "qualification_scope": {
            "single_process_trace": True,
            "ten_game_smoke": True,
            "qualification": True,
            "zero_update_bridge_qualified": True,
            "policy_competence": False,
            "training_authorized": False,
            "external_compute_authorized": False,
            "submission_authorized": False,
        },
        "cost_usd": 0.0,
    }
    public_report["review_sha256"] = self_hash(public_report, "review_sha256")
    atomic_json(public_report_path, public_report)
    return public_report


def main() -> int:
    parser = argparse.ArgumentParser()
    output_directory = ROOT / "private/g3/e04/qualification-v1"
    parser.add_argument(
        "--authorization-snapshot",
        type=Path,
        default=output_directory / "e04-native-zero-update-authorization.json",
    )
    parser.add_argument(
        "--consumed-request",
        type=Path,
        default=ROOT / "configs/e04_qualification_request_v1.json",
    )
    parser.add_argument(
        "--games",
        type=Path,
        default=output_directory / "e04-native-zero-update-games.json",
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
        default=ROOT / "reports/evaluations/e04-qualification-v1.json",
    )
    args = parser.parse_args()
    report = review_qualification(
        authorization_snapshot_path=args.authorization_snapshot,
        consumed_request_path=args.consumed_request,
        games_path=args.games,
        bridge_path=args.bridge,
        private_report_path=args.private_report,
        public_report_path=args.public_report,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
