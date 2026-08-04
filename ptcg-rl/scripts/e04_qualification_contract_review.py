from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ptcg_rl.g3.e04_authorization import load_native_authorization  # noqa: E402
from ptcg_rl.g3.gold_path import canonical_json_bytes, sha256_file  # noqa: E402


SMOKE_SHA256 = "66d00da9e0b99783fd3f7ec441a89fa298597acbc1818220014a97481ba68236"
DECISION_SHA256 = "4667d8c08f9fb6782d37729f14ed097323c4b31efafdd87f44da9bdb2ad40307"
RUNNER_SHA256 = "cd5ef3a7e987f92172f218991084e3a0a1f3002e9df9acac57919a4ee23c63b7"
AUTHORIZATION_VALIDATOR_SHA256 = (
    "f84fa26251c4ae4cf0294b12eadf5b0b87fdd9193909ed21b4f116776e7941e3"
)
ONE_SIDED_99_PERCENT_T_CRITICAL_DF9 = 2.821437925025808
SELECTED_GAMES = 180
DECISION_FLOOR = 10_000


class E04QualificationContractReviewError(ValueError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise E04QualificationContractReviewError(
            f"cannot load JSON {path}: {error}"
        ) from error
    if not isinstance(value, dict):
        raise E04QualificationContractReviewError(
            f"JSON root must be an object: {path}"
        )
    return value


def relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError as error:
        raise E04QualificationContractReviewError(
            f"review path escapes project root: {path}"
        ) from error


def self_hash(value: Mapping[str, Any], field: str) -> str:
    payload = dict(value)
    payload.pop(field, None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def review_contract(
    *,
    smoke_path: Path,
    decision_path: Path,
    request_path: Path,
    runner_path: Path,
    authorization_validator_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    observed_hashes = {
        "smoke_evidence": sha256_file(smoke_path),
        "decision": sha256_file(decision_path),
        "request": sha256_file(request_path),
        "runner": sha256_file(runner_path),
        "authorization_validator": sha256_file(authorization_validator_path),
    }
    expected_hashes = {
        "smoke_evidence": SMOKE_SHA256,
        "decision": DECISION_SHA256,
        "runner": RUNNER_SHA256,
        "authorization_validator": AUTHORIZATION_VALIDATOR_SHA256,
    }
    for name, expected in expected_hashes.items():
        if observed_hashes[name] != expected:
            raise E04QualificationContractReviewError(
                f"qualification contract source hash differs: {name}"
            )

    smoke = load_json(smoke_path)
    request_raw = load_json(request_path)
    request = load_native_authorization(request_path, require_authorized=False)
    if request.authorized:
        raise E04QualificationContractReviewError(
            "qualification request must remain non-authorizing"
        )
    if request.stage != "qualification":
        raise E04QualificationContractReviewError(
            "qualification request stage differs"
        )
    if request.games != SELECTED_GAMES:
        raise E04QualificationContractReviewError(
            "qualification game count differs"
        )
    if request.minimum_meaningful_decisions != DECISION_FLOOR:
        raise E04QualificationContractReviewError(
            "qualification decision floor differs"
        )
    if request.bridge_checkpoint_interval_games != 10:
        raise E04QualificationContractReviewError(
            "qualification bridge checkpoint interval differs"
        )
    if request.optimizer_steps_authorized != 0:
        raise E04QualificationContractReviewError(
            "qualification request authorizes optimizer steps"
        )
    if request.external_compute_authorized:
        raise E04QualificationContractReviewError(
            "qualification request authorizes external compute"
        )
    if request_raw.get("decision_sha256") != observed_hashes["decision"]:
        raise E04QualificationContractReviewError(
            "qualification request decision hash differs"
        )
    if request_raw.get("prerequisite_evidence_sha256") != observed_hashes[
        "smoke_evidence"
    ]:
        raise E04QualificationContractReviewError(
            "qualification request smoke hash differs"
        )
    if request_raw.get("runner_sha256") != observed_hashes["runner"]:
        raise E04QualificationContractReviewError(
            "qualification request runner hash differs"
        )
    if request_raw.get("authorization_validator_sha256") != observed_hashes[
        "authorization_validator"
    ]:
        raise E04QualificationContractReviewError(
            "qualification request authorization-validator hash differs"
        )
    if request_raw.get("maximum_requests_per_game") != 20_000:
        raise E04QualificationContractReviewError(
            "qualification request maximum requests differs"
        )
    if request_raw.get("game_timeout_seconds") != 300.0:
        raise E04QualificationContractReviewError(
            "qualification request game timeout differs"
        )
    if (ROOT / request.output_directory).exists():
        raise E04QualificationContractReviewError(
            "qualification output directory already exists"
        )

    if smoke.get("status") != "SUCCEEDED" or smoke.get("decision") != "PASS":
        raise E04QualificationContractReviewError(
            "ten-game smoke is not an accepted PASS"
        )
    results = smoke.get("results")
    execution = smoke.get("execution")
    if not isinstance(results, Mapping) or not isinstance(execution, Mapping):
        raise E04QualificationContractReviewError(
            "ten-game smoke results or execution are missing"
        )
    per_game = results.get("per_game")
    if not isinstance(per_game, list) or len(per_game) != 10:
        raise E04QualificationContractReviewError(
            "ten-game smoke per-game evidence differs"
        )
    observations = [int(game["meaningful_decisions"]) for game in per_game]
    if observations != [58, 70, 57, 70, 56, 70, 70, 66, 63, 68]:
        raise E04QualificationContractReviewError(
            "ten-game smoke decision observations differ"
        )
    if results.get("meaningful_decisions") != sum(observations):
        raise E04QualificationContractReviewError(
            "ten-game smoke decision total differs"
        )
    if results.get("games") != 10:
        raise E04QualificationContractReviewError(
            "ten-game smoke game count differs"
        )
    if set(results.get("zero_tolerance", {}).values()) != {0}:
        raise E04QualificationContractReviewError(
            "ten-game smoke contains a zero-tolerance failure"
        )
    if execution.get("optimizer_steps") != 0:
        raise E04QualificationContractReviewError(
            "ten-game smoke used optimizer steps"
        )

    mean = statistics.mean(observations)
    sample_stdev = statistics.stdev(observations)
    standard_error = sample_stdev / math.sqrt(len(observations))
    lower_bound = mean - ONE_SIDED_99_PERCENT_T_CRITICAL_DF9 * standard_error
    observed_minimum = min(observations)
    observed_maximum = max(observations)
    games_at_observed_minimum = math.ceil(DECISION_FLOOR / observed_minimum)
    games_at_lower_bound = math.ceil(DECISION_FLOOR / lower_bound)
    if games_at_observed_minimum != 179 or games_at_lower_bound != 168:
        raise E04QualificationContractReviewError(
            "qualification sizing calculation differs"
        )
    if SELECTED_GAMES < games_at_observed_minimum:
        raise E04QualificationContractReviewError(
            "selected qualification size is below observed-minimum sizing"
        )
    if 100 * observed_maximum >= DECISION_FLOOR:
        raise E04QualificationContractReviewError(
            "old 100-game contract is not disproven by the smoke range"
        )

    seconds_per_game = float(execution["wall_seconds"]) / int(results["games"])
    report: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e04-qualification-contract-review-v1",
        "created_at_utc": "2026-07-24T13:10:00Z",
        "source_path": relative(output_path),
        "producer": "scripts/e04_qualification_contract_review.py",
        "status": "PASS",
        "decision": "ACCEPT_180_GAME_QUALIFICATION_CONTRACT",
        "supersedes": {
            "decision": "DEC-011",
            "scope": "E04 qualification game count only",
            "old_games": 100,
            "old_minimum_meaningful_decisions": DECISION_FLOOR,
        },
        "accepted_decision": {
            "decision": "DEC-012",
            "path": relative(decision_path),
            "sha256": observed_hashes["decision"],
            "games": SELECTED_GAMES,
            "minimum_meaningful_decisions": DECISION_FLOOR,
            "bridge_checkpoint_interval_games": 10,
        },
        "smoke_evidence": {
            "path": relative(smoke_path),
            "sha256": observed_hashes["smoke_evidence"],
            "observations": observations,
            "games": 10,
            "meaningful_decisions": sum(observations),
            "mean": mean,
            "sample_standard_deviation": sample_stdev,
            "observed_minimum": observed_minimum,
            "observed_maximum": observed_maximum,
            "zero_tolerance_total": 0,
            "optimizer_steps": 0,
        },
        "sizing": {
            "old_100_game_projection_at_mean": 100 * mean,
            "old_100_game_projection_at_observed_maximum": 100
            * observed_maximum,
            "one_sided_99_percent_t_critical_df9": (
                ONE_SIDED_99_PERCENT_T_CRITICAL_DF9
            ),
            "one_sided_99_percent_lower_bound_mean": lower_bound,
            "games_required_at_99_percent_lower_bound": games_at_lower_bound,
            "games_required_at_observed_minimum": games_at_observed_minimum,
            "selected_games": SELECTED_GAMES,
            "selected_projection_at_mean": SELECTED_GAMES * mean,
            "selected_projection_at_observed_minimum": SELECTED_GAMES
            * observed_minimum,
            "selected_projection_at_99_percent_lower_bound": SELECTED_GAMES
            * lower_bound,
        },
        "runtime_projection": {
            "observed_seconds_per_game": seconds_per_game,
            "linear_seconds_for_selected_games": seconds_per_game
            * SELECTED_GAMES,
            "planning_only": True,
        },
        "request": {
            "path": relative(request_path),
            "sha256": observed_hashes["request"],
            "authorized": False,
            "output_directory": request.output_directory,
            "output_directory_exists": False,
            "optimizer_steps_authorized": 0,
            "external_compute_authorized": False,
        },
        "source_contract": {
            "runner_path": relative(runner_path),
            "runner_sha256": observed_hashes["runner"],
            "authorization_validator_path": relative(authorization_validator_path),
            "authorization_validator_sha256": observed_hashes[
                "authorization_validator"
            ],
        },
        "authorization": {
            "repository_implementation": True,
            "unit_tests": True,
            "qualification_execution": False,
            "rerun_or_overwrite": False,
            "optimizer_steps": False,
            "external_compute": False,
            "replay_transfer": False,
            "submission": False,
        },
        "revisit_trigger": (
            "The qualification request, decision floor, game count, runner, "
            "authorization validator, assets, deck, checkpoint or prerequisite "
            "smoke evidence changes."
        ),
    }
    report["review_sha256"] = self_hash(report, "review_sha256")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--smoke",
        type=Path,
        default=ROOT / "reports/evaluations/e04-ten-game-smoke-v1.json",
    )
    parser.add_argument(
        "--decision",
        type=Path,
        default=ROOT / "docs/decisions/DEC-012_E04_QUALIFICATION_RESIZED.md",
    )
    parser.add_argument(
        "--request",
        type=Path,
        default=ROOT / "configs/e04_qualification_request_v1.json",
    )
    parser.add_argument(
        "--runner",
        type=Path,
        default=ROOT / "scripts/e04_native_zero_update.py",
    )
    parser.add_argument(
        "--authorization-validator",
        type=Path,
        default=ROOT / "src/ptcg_rl/g3/e04_authorization.py",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT
        / "reports/artifacts/e04-qualification-contract-review-v1.json",
    )
    args = parser.parse_args()
    report = review_contract(
        smoke_path=args.smoke,
        decision_path=args.decision,
        request_path=args.request,
        runner_path=args.runner,
        authorization_validator_path=args.authorization_validator,
        output_path=args.out,
    )
    atomic_json(args.out, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
