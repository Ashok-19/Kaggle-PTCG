from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
DECISION_PATH = (
    ROOT / "docs/decisions/DEC-021_E01_FLG_DRAGAPULT_SCREENING_EXPANSION.md"
)
REQUEST_PATH = (
    ROOT / "configs/e01_flg_dragapult_screening_expansion_request_v1.json"
)
METADATA_PATH = (
    ROOT
    / "reports/artifacts/raw/e01-flg-dragapult-screening-expansion-candidates-v1.json"
)
CALIBRATION_REQUEST_PATH = (
    ROOT / "configs/e01_flg_dragapult_calibration_request_v1.json"
)
CALIBRATION_REVIEW_PATH = (
    ROOT / "reports/artifacts/e01-flg-dragapult-calibration-review-v1.json"
)
OUTPUT_PATH = (
    ROOT
    / "reports/artifacts/e01-flg-dragapult-screening-expansion-contract-review-v1.json"
)

EXPECTED = {
    "decision": "3533c0c1b099193ab8f02eee54e60cd89dedab1399eb2e33668041e4c103d23c",
    "request": "1c9a5b893af29f19dad214b3377919f996b48b62145e5401f189a6dc231ac559",
    "metadata": "06afd9c1aaafe5fbf207ad4fd07bf9852fa1097c29ab8aaa9a862124731f1e37",
    "calibration_request": "9140bc26599d08c6c343db19a658cfa728b5425f9a59700d9bb627b3c16c89e8",
    "calibration_authorized_request": "42b97e0fbb26e293a62747e5437315ae2018bdb7d5c07c0d28004dcc604adce7",
    "calibration_review": "719c08aac0bfc9d8c66c163cd85cea45cd8af8107a946c006e356ed9df248038",
    "calibration_review_self": "be2704b2f09126a1b77340e25971c4231c2f515e52ca4e41e3c9d32b8daa7282",
    "deck": "89e6155f25310ee695c0761c85d3ae8e44f376456ff0539231820f8e803f2d5e",
}

EXCLUDED_EPISODES = {
    88_302_734,
    88_333_037,
    88_304_411,
    88_312_254,
    88_333_027,
    88_324_168,
    88_306_996,
    88_280_071,
    88_329_376,
    88_286_928,
    88_276_868,
    88_295_387,
    88_318_931,
    88_316_351,
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


def build_report() -> dict[str, Any]:
    for path, expected in (
        (DECISION_PATH, EXPECTED["decision"]),
        (REQUEST_PATH, EXPECTED["request"]),
        (METADATA_PATH, EXPECTED["metadata"]),
        (CALIBRATION_REQUEST_PATH, EXPECTED["calibration_request"]),
        (CALIBRATION_REVIEW_PATH, EXPECTED["calibration_review"]),
    ):
        require_hash(path, expected)

    request = load_json(REQUEST_PATH)
    metadata = load_json(METADATA_PATH)
    calibration_request = load_json(CALIBRATION_REQUEST_PATH)
    calibration_review = load_json(CALIBRATION_REVIEW_PATH)

    if (
        calibration_request.get("status") != "CONSUMED"
        or calibration_request.get("request_ready") is not False
        or calibration_request.get("authorized") is not False
        or calibration_request.get("approval", {}).get(
            "authorized_request_sha256"
        )
        != EXPECTED["calibration_authorized_request"]
        or calibration_review.get("status") != "PASS"
        or calibration_review.get("review_sha256")
        != EXPECTED["calibration_review_self"]
        or calibration_review.get("consistency", {}).get(
            "teacher_deck_multiset_sha256"
        )
        != EXPECTED["deck"]
        or calibration_review.get("consistency", {}).get(
            "calibration_teacher_active_selection_requests"
        )
        != 1_292
        or calibration_review.get("density", {}).get(
            "combined_observed_teacher_decisions"
        )
        != 1_386
        or calibration_review.get("density", {}).get(
            "screening_teacher_decision_shortfall"
        )
        != 3_614
    ):
        raise ValueError("completed Dragapult calibration differs")

    selection = metadata.get("selection")
    sizing = metadata.get("sizing")
    source = metadata.get("source")
    boundary = request.get("review_boundary")
    teacher = request.get("teacher")
    if not all(
        isinstance(value, Mapping)
        for value in (selection, sizing, source, boundary, teacher)
    ):
        raise ValueError("screening-expansion bindings are missing")

    episodes = request.get("episodes")
    if not isinstance(episodes, list) or len(episodes) != 38:
        raise ValueError("screening expansion must contain 38 episodes")
    if episodes != selection.get("episodes"):
        raise ValueError("request episodes differ from candidate metadata")
    episode_ids = [int(item["episode_id"]) for item in episodes]
    if len(set(episode_ids)) != 38:
        raise ValueError("screening expansion episode IDs are duplicated")
    if EXCLUDED_EPISODES.intersection(episode_ids):
        raise ValueError("completed probe or calibration episode was reselected")

    strata = Counter(str(item.get("stratum")) for item in episodes)
    expected_strata = Counter(
        {"seat_0_loss": 10, "seat_0_win": 10, "seat_1_loss": 9, "seat_1_win": 9}
    )
    if strata != expected_strata:
        raise ValueError("screening expansion strata differ")
    if sum(int(item["declared_bytes"]) for item in episodes) != 254_237_550:
        raise ValueError("screening expansion byte total differs")

    if (
        request.get("decision_id") != "DEC-021"
        or request.get("status") != "READY_UNAUTHORIZED"
        or request.get("request_ready") is not True
        or request.get("authorized") is not False
        or request.get("authorization_scope") is not None
        or request.get("approval") is not None
        or request.get("execution") is not None
        or request.get("maximum_new_files") != 38
        or request.get("maximum_new_bytes") != 254_237_550
        or request.get("output_directory")
        != "private/g3/e01/flg-dragapult-screening-expansion-v1"
        or request.get("overwrite_authorized") is not False
        or request.get("projection_is_guarantee") is not False
        or request.get("balanced_strata") != dict(expected_strata)
    ):
        raise ValueError("screening expansion request contract differs")

    if (
        teacher.get("team_name") != "flg"
        or teacher.get("team_id") != 16_380_946
        or teacher.get("submission_id") != 55_004_495
        or teacher.get("submission_public_score") != 1244.2
        or teacher.get("live_rank_at_refresh") != 1
        or teacher.get("archetype_context_label") != "Dragapult ex"
        or teacher.get("required_deck_multiset_sha256") != EXPECTED["deck"]
    ):
        raise ValueError("screening expansion teacher contract differs")

    if (
        sizing.get("observed_combined_teacher_decisions") != 1_386
        or sizing.get("screening_minimum_teacher_decisions") != 5_000
        or sizing.get("screening_teacher_decision_shortfall") != 3_614
        or sizing.get("minimum_observed_calibration_decisions_per_mib")
        != 16.446242027673883
        or sizing.get("coverage_multiplier") != 1.1
        or sizing.get("minimum_target_bytes") != 253_462_708
        or sizing.get("projection_is_guarantee") is not False
        or selection.get("selected_files") != 38
        or selection.get("selected_bytes") != 254_237_550
        or source.get("dataset_intersection_episodes") != 131
        or source.get("remaining_pool_counts")
        != {
            "seat_0_loss": 16,
            "seat_0_win": 28,
            "seat_1_loss": 25,
            "seat_1_win": 48,
        }
    ):
        raise ValueError("screening expansion sizing differs")

    if (
        boundary.get("count_only_schema_version") != 1
        or boundary.get("count_only_environment_name") != "cabt"
        or boundary.get("count_only_environment_version") != "1.0.0"
        or boundary.get("count_only_module_version") != "1.32.2"
        or boundary.get("count_only_teacher_submission_id") != 55_004_495
        or boundary.get("count_only_deck_multiset_sha256") != EXPECTED["deck"]
        or boundary.get("require_current_asset_construction_compatibility")
        != "PASS"
        or boundary.get("require_action_alignment") != "PASS"
        or boundary.get("nonmatching_files_rejected_from_counts") is not True
    ):
        raise ValueError("screening expansion review boundary differs")

    for key in (
        "agent_logs_authorized",
        "additional_replays_authorized",
        "raw_exports_authorized",
        "training_labels_authorized",
        "training_authorized",
        "external_compute_authorized",
        "submission_authorized",
    ):
        if request.get(key) is not False:
            raise ValueError(f"request boundary must remain false: {key}")

    output_exists = (ROOT / str(request["output_directory"])).exists()
    if output_exists:
        raise ValueError("screening expansion output directory already exists")

    report: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e01-flg-dragapult-screening-expansion-contract-review-v1",
        "created_at_utc": request.get("created_at_utc"),
        "source_path": (
            "reports/artifacts/"
            "e01-flg-dragapult-screening-expansion-contract-review-v1.json"
        ),
        "producer": "scripts/e01_flg_screening_expansion_contract_review.py",
        "reviewed_decision": "DEC-021",
        "status": "PASS",
        "decision": (
            "ACCEPT_EXACT_38_FILE_CURRENT_RANK_1_DRAGAPULT_"
            "SCREENING_EXPANSION_REQUEST_UNAUTHORIZED"
        ),
        "inputs": {
            "decision": {
                "path": str(DECISION_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["decision"],
            },
            "request": {
                "path": str(REQUEST_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["request"],
            },
            "candidate_metadata": {
                "path": str(METADATA_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["metadata"],
            },
            "completed_calibration_request": {
                "path": str(CALIBRATION_REQUEST_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["calibration_request"],
                "authorized_request_sha256": EXPECTED[
                    "calibration_authorized_request"
                ],
            },
            "completed_calibration_review": {
                "path": str(CALIBRATION_REVIEW_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["calibration_review"],
                "review_sha256": EXPECTED["calibration_review_self"],
            },
        },
        "request": {
            "request_ready": True,
            "authorized": False,
            "maximum_new_files": 38,
            "maximum_new_bytes": 254_237_550,
            "minimum_target_bytes": 253_462_708,
            "balanced_strata": dict(sorted(strata.items())),
            "required_module_version": "1.32.2",
            "required_deck_multiset_sha256": EXPECTED["deck"],
            "output_directory_exists": False,
            "projection_is_guarantee": False,
            "agent_logs_authorized": False,
            "additional_replays_authorized": False,
            "raw_exports_authorized": False,
            "training_authorized": False,
            "external_compute_authorized": False,
            "submission_authorized": False,
        },
        "qualification": {
            "current_rank_1_teacher_qualified": True,
            "exact_dragapult_deck_qualified": True,
            "same_version_replay_contract_consistency_qualified": True,
            "screening_expansion_request_ready": True,
            "minimum_5000_teacher_decisions_met": False,
            "e01_screening_gate_passed": False,
            "replay_transfer_authorized": False,
            "training_authorized": False,
        },
        "next_action": (
            "REQUEST_EXPLICIT_APPROVAL_FOR_EXACT_38_FILE_"
            "FLG_DRAGAPULT_SCREENING_EXPANSION"
        ),
        "cost_usd": 0.0,
    }
    report["review_sha256"] = self_hash(report, "review_sha256")
    return report


def main() -> None:
    report = build_report()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT_PATH.with_suffix(OUTPUT_PATH.suffix + ".partial")
    temporary.write_text(
        json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(OUTPUT_PATH)
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
