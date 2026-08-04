from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
DECISION_PATH = ROOT / "docs/decisions/DEC-016_E01_LUCA_GOLD_TEACHER_PROBE.md"
REQUEST_PATH = ROOT / "configs/e01_luca_gold_teacher_probe_request_v1.json"
COVERAGE_PATH = ROOT / "reports/artifacts/raw/e01-gold-teacher-coverage-v1.json"
CONSISTENCY_REVIEW_PATH = ROOT / "reports/artifacts/e01-same-submission-consistency-review-v1.json"
OUTPUT_PATH = ROOT / "reports/artifacts/e01-luca-gold-teacher-contract-review-v1.json"

EXPECTED = {
    "decision": "e52bf2d91a504db6e9828de3190aa652dde59c46aa93b0035912e675d17792f8",
    "request": "02a672b1950da7002e98c62e5e0f807bc5f539488e2a4c614a6c845cb84a6a89",
    "coverage": "f73d67ea3aa8450f712ab046f35a97e887d1e287813c9968efbb33f8fd06acb7",
    "consistency_review": "4ec60a2a4dffeb9ffae898fad8ae44a0e77c0c5e51a50e155df21b90ae665966",
    "consistency_review_self": "dae9bd135831b745d7050b49872b7f1404bbea45ab49b7cd20195f74885862bb",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")


def self_hash(value: Mapping[str, Any], field: str) -> str:
    payload = dict(value)
    payload.pop(field, None)
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def load_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must contain an object")
    return value


def require_hash(path: Path, expected: str) -> None:
    observed = sha256_file(path)
    if observed != expected:
        raise ValueError(f"hash differs for {path}: {observed}")


def main() -> None:
    for path, expected in (
        (DECISION_PATH, EXPECTED["decision"]),
        (REQUEST_PATH, EXPECTED["request"]),
        (COVERAGE_PATH, EXPECTED["coverage"]),
        (CONSISTENCY_REVIEW_PATH, EXPECTED["consistency_review"]),
    ):
        require_hash(path, expected)

    request = load_json(REQUEST_PATH)
    coverage = load_json(COVERAGE_PATH)
    consistency = load_json(CONSISTENCY_REVIEW_PATH)
    if consistency.get("status") != "PASS":
        raise ValueError("completed consistency review is not PASS")
    if consistency.get("review_sha256") != EXPECTED["consistency_review_self"]:
        raise ValueError("completed consistency review self hash differs")
    qualification = consistency.get("qualification")
    if not isinstance(qualification, Mapping):
        raise ValueError("completed consistency qualification is missing")
    if qualification.get("exact_deck_consistency_qualified") is not True:
        raise ValueError("completed consistency deck result differs")
    if qualification.get("e01_screening_gate_passed") is not False:
        raise ValueError("completed consistency review overstates E01")

    if request.get("schema_version") != 1 or request.get("decision_id") != "DEC-016":
        raise ValueError("request identity differs")
    if request.get("status") != "READY_UNAUTHORIZED":
        raise ValueError("request status differs")
    if request.get("request_ready") is not True or request.get("authorized") is not False:
        raise ValueError("request authorization differs")
    if request.get("authorization_scope") is not None:
        raise ValueError("authorization scope must remain null")
    if request.get("maximum_new_files") != 2 or request.get("maximum_new_bytes") != 1_313_221:
        raise ValueError("request transfer caps differ")
    if request.get("overwrite_authorized") is not False:
        raise ValueError("overwrite authorization differs")
    if request.get("output_directory") != "private/g3/e01/luca-gold-teacher-probe-v1":
        raise ValueError("output directory differs")
    if (ROOT / str(request["output_directory"])).exists():
        raise ValueError("output directory already exists")

    dataset = request.get("dataset")
    if dataset != {
        "owner_slug": "kaggle",
        "dataset_slug": "pokemon-tcg-ai-battle-episodes-2026-07-23",
        "version": 1,
    }:
        raise ValueError("dataset binding differs")
    teacher = request.get("teacher")
    if not isinstance(teacher, Mapping):
        raise ValueError("teacher binding is missing")
    expected_teacher = {
        "team_id": 16448747,
        "team_name": "Luca",
        "submission_id": 54863653,
        "leaderboard_rank": 2,
        "leaderboard_team_score": 1190.4,
        "submission_public_score": 1180.9,
        "dataset_episode_count": 357,
        "dataset_seat_0_count": 181,
        "dataset_seat_1_count": 176,
        "strength_basis": "CURRENT_PUBLIC_GOLD_REGION_SCORE_AND_RANK",
        "rating_field_from_historical_manifest_used": False,
    }
    if dict(teacher) != expected_teacher:
        raise ValueError("teacher binding differs")

    episodes = request.get("episodes")
    if not isinstance(episodes, list) or len(episodes) != 2:
        raise ValueError("episode list differs")
    expected_episodes = [
        {
            "episode_id": 87731214,
            "file_name": "87731214.json",
            "declared_bytes": 574428,
            "teacher_player_index": 1,
            "teacher_reward": -1,
            "teacher_submission_id": 54863653,
        },
        {
            "episode_id": 87615736,
            "file_name": "87615736.json",
            "declared_bytes": 738793,
            "teacher_player_index": 0,
            "teacher_reward": 1,
            "teacher_submission_id": 54863653,
        },
    ]
    for observed, expected in zip(episodes, expected_episodes, strict=True):
        if not isinstance(observed, Mapping):
            raise ValueError("episode entry differs")
        for key, value in expected.items():
            if observed.get(key) != value:
                raise ValueError(f"episode field differs: {key}")
    if sum(int(episode["declared_bytes"]) for episode in episodes) != 1_313_221:
        raise ValueError("episode bytes do not match total cap")

    boundary = request.get("inspection_boundary")
    if not isinstance(boundary, Mapping):
        raise ValueError("inspection boundary is missing")
    for field in (
        "agent_log_downloads",
        "additional_replay_downloads_after_named_files",
        "raw_replay_body_exports",
        "raw_step_exports",
        "action_sequence_exports",
        "observation_exports",
        "training_label_exports",
        "optimizer_steps",
    ):
        if boundary.get(field) != 0:
            raise ValueError(f"inspection boundary differs: {field}")
    for field in ("external_compute", "training", "submission"):
        if boundary.get(field) is not False:
            raise ValueError(f"inspection boundary differs: {field}")

    selected = coverage.get("selection")
    if not isinstance(selected, Mapping):
        raise ValueError("coverage selection is missing")
    if (
        selected.get("teacher_submission_id") != 54863653
        or selected.get("teacher_leaderboard_rank") != 2
        or selected.get("teacher_submission_public_score") != 1180.9
        or selected.get("teacher_dataset_episode_count") != 357
        or selected.get("probe_total_bytes") != 1_313_221
        or selected.get("opposite_player_slots") is not True
        or selected.get("opposite_terminal_results") is not True
        or selected.get("smallest_qualifying_pair") is not True
    ):
        raise ValueError("coverage selection differs")

    report: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e01-luca-gold-teacher-contract-review-v1",
        "created_at_utc": request.get("created_at_utc"),
        "source_path": "reports/artifacts/e01-luca-gold-teacher-contract-review-v1.json",
        "producer": "scripts/e01_luca_teacher_contract_review.py",
        "reviewed_decision": "DEC-016",
        "status": "PASS",
        "decision": "ACCEPT_EXACT_TWO_FILE_LUCA_GOLD_TEACHER_REQUEST_UNAUTHORIZED",
        "inputs": {
            "decision": {
                "path": str(DECISION_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["decision"],
            },
            "request": {
                "path": str(REQUEST_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["request"],
            },
            "coverage": {
                "path": str(COVERAGE_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["coverage"],
            },
            "completed_consistency_review": {
                "path": str(CONSISTENCY_REVIEW_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["consistency_review"],
                "review_sha256": EXPECTED["consistency_review_self"],
            },
        },
        "teacher": expected_teacher,
        "request": {
            "request_ready": True,
            "authorized": False,
            "maximum_new_files": 2,
            "maximum_new_bytes": 1_313_221,
            "output_directory_exists": False,
            "episodes": expected_episodes,
            "agent_logs_authorized": False,
            "third_replay_authorized": False,
            "training_authorized": False,
            "external_compute_authorized": False,
        },
        "qualification": {
            "gold_region_teacher_selected": True,
            "gold_region_strength_metadata_available": True,
            "teacher_replay_coverage_sufficient_for_future_screening_plan": True,
            "teacher_exact_deck_qualified": False,
            "teacher_policy_consistency_qualified": False,
            "minimum_5000_teacher_decisions_met": False,
            "e01_screening_gate_passed": False,
            "replay_transfer_authorized": False,
            "training_authorized": False,
        },
        "next_action": "REQUEST_EXPLICIT_APPROVAL_FOR_EXACT_TWO_FILE_LUCA_GOLD_TEACHER_PROBE",
        "cost_usd": 0.0,
    }
    report["review_sha256"] = self_hash(report, "review_sha256")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_bytes(canonical_bytes(report))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
