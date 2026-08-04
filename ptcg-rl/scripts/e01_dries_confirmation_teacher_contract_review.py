from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
DECISION_PATH = ROOT / "docs/decisions/DEC-022_E01_DRIES_CONFIRMATION_TEACHER_PROBE.md"
REQUEST_PATH = ROOT / "configs/e01_dries_confirmation_teacher_probe_request_v1.json"
METADATA_PATH = ROOT / "reports/artifacts/raw/e01-live-confirmation-refresh-v1.json"
SCREENING_REQUEST_PATH = (
    ROOT / "configs/e01_flg_dragapult_screening_expansion_request_v1.json"
)
SCREENING_REVIEW_PATH = (
    ROOT / "reports/artifacts/e01-flg-dragapult-screening-expansion-review-v1.json"
)
OUTPUT_PATH = (
    ROOT / "reports/artifacts/e01-dries-confirmation-teacher-contract-review-v1.json"
)

EXPECTED = {
    "decision": "a6802416e9d2cb03ca267c82a11a482014c22832f575cb310802cb111c93b027",
    "request": "7eb4d5ec21956f6661ce95248d387a497828c20cd16438f13adb280e7cb670a9",
    "metadata": "7642598704cca4899235089c57e6429805ebb8ea496e4c5b47befc677e4b80dc",
    "screening_request": "f16d155948db791e355f561901daf2e4f2ef886d68d638a6fdce4c2d31939583",
    "screening_review": "38f1e6f4f0d68b52677e6e578ac7f69ca0730f819bc895b5205d42387f7c8fc2",
    "screening_review_self": "0346535b89f0f14e153df0afeda90609f51e2a0d75b4b959df38be71dfb7df80",
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
        (SCREENING_REQUEST_PATH, EXPECTED["screening_request"]),
        (SCREENING_REVIEW_PATH, EXPECTED["screening_review"]),
    ):
        require_hash(path, expected)

    request = load_json(REQUEST_PATH)
    metadata = load_json(METADATA_PATH)
    screening_request = load_json(SCREENING_REQUEST_PATH)
    screening_review = load_json(SCREENING_REVIEW_PATH)
    if screening_review.get("review_sha256") != EXPECTED["screening_review_self"]:
        raise ValueError("screening review self hash differs")
    if (
        screening_request.get("status") != "CONSUMED"
        or screening_request.get("authorized") is not False
        or screening_review.get("status") != "PASS"
        or screening_review.get("qualification", {}).get("e01_screening_gate_passed")
        is not True
        or screening_review.get("screening", {}).get(
            "combined_observed_teacher_decisions"
        )
        != 6340
        or screening_review.get("screening", {}).get("qualified_files") != 38
        or screening_review.get("screening", {}).get("rejected_files") != 0
    ):
        raise ValueError("completed flg screening evidence differs")

    selected = metadata.get("selection", {}).get("selected_files")
    episodes = request.get("episodes")
    teacher = request.get("teacher")
    boundary = request.get("review_boundary")
    confirmation = request.get("confirmation_boundary")
    if not all(
        isinstance(value, Mapping) for value in (teacher, boundary, confirmation)
    ):
        raise ValueError("request teacher or review boundaries are missing")
    if not isinstance(selected, list) or selected != episodes or len(selected) != 2:
        raise ValueError("request episodes differ from the frozen selection")
    if sum(int(item["declared_bytes"]) for item in selected) != 1_135_238:
        raise ValueError("request byte total differs")
    if len({int(item["episode_id"]) for item in selected}) != 2:
        raise ValueError("request episode IDs are duplicated")
    strata = Counter(str(item["stratum"]) for item in selected)
    if strata != Counter({"seat_0_loss": 1, "seat_1_win": 1}):
        raise ValueError("Dries probe seat/result pair differs")
    if (
        request.get("decision_id") != "DEC-022"
        or request.get("status") != "READY_UNAUTHORIZED"
        or request.get("request_ready") is not True
        or request.get("authorized") is not False
        or request.get("authorization_scope") is not None
        or request.get("maximum_new_files") != 2
        or request.get("maximum_new_bytes") != 1_135_238
        or request.get("overwrite_authorized") is not False
        or request.get("output_directory")
        != "private/g3/e01/dries-confirmation-teacher-probe-v1"
        or teacher.get("team_id") != 16_531_269
        or teacher.get("team_name") != "Dries @ Tufa Labs"
        or teacher.get("submission_id") != 55_002_825
        or teacher.get("live_rank_at_refresh") != 1
        or teacher.get("live_team_score_at_refresh") != 1205.2
        or teacher.get("submission_public_score") != 1205.2
        or teacher.get("dataset_episode_count") != 128
    ):
        raise ValueError("Dries probe request contract differs")
    if (
        boundary.get("count_only_schema_version") != 1
        or boundary.get("count_only_environment_name") != "cabt"
        or boundary.get("count_only_environment_version") != "1.0.0"
        or boundary.get("count_only_module_version") != "1.32.2"
        or boundary.get("count_only_teacher_submission_id") != 55_002_825
        or boundary.get("require_same_exact_teacher_deck_across_both_files")
        is not True
        or boundary.get("require_current_asset_construction_compatibility")
        != "PASS"
        or boundary.get("require_action_alignment") != "PASS"
        or boundary.get("nonmatching_files_rejected_from_counts") is not True
        or boundary.get("probe_completes_confirmation") is not False
    ):
        raise ValueError("Dries probe review boundary differs")
    if (
        confirmation.get("requires_two_independent_recent_teachers") is not True
        or confirmation.get("requires_at_least_200_episodes") is not True
        or confirmation.get("requires_at_least_25000_meaningful_teacher_decisions")
        is not True
        or confirmation.get("dries_probe_is_confirmation_completion") is not False
        or confirmation.get("training_authorized") is not False
    ):
        raise ValueError("confirmation boundary differs")
    if (
        request.get("agent_logs_authorized") is not False
        or request.get("additional_replays_authorized") is not False
        or request.get("raw_exports_authorized") is not False
        or request.get("training_labels_authorized") is not False
        or request.get("training_authorized") is not False
        or request.get("external_compute_authorized") is not False
        or request.get("submission_authorized") is not False
    ):
        raise ValueError("request authorization boundary differs")
    output_directory = ROOT / str(request["output_directory"])
    if output_directory.exists():
        raise ValueError("Dries probe output directory already exists")

    report: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e01-dries-confirmation-teacher-contract-review-v1",
        "created_at_utc": request.get("created_at_utc"),
        "source_path": "reports/artifacts/e01-dries-confirmation-teacher-contract-review-v1.json",
        "producer": "scripts/e01_dries_confirmation_teacher_contract_review.py",
        "reviewed_decision": "DEC-022",
        "status": "PASS",
        "decision": "ACCEPT_EXACT_TWO_FILE_CURRENT_RANK_1_DRIES_CONFIRMATION_TEACHER_REQUEST_UNAUTHORIZED",
        "inputs": {
            "decision": {
                "path": str(DECISION_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["decision"],
            },
            "request": {
                "path": str(REQUEST_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["request"],
            },
            "live_confirmation_refresh": {
                "path": str(METADATA_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["metadata"],
            },
            "completed_screening_request": {
                "path": str(SCREENING_REQUEST_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["screening_request"],
            },
            "completed_screening_review": {
                "path": str(SCREENING_REVIEW_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["screening_review"],
                "review_sha256": EXPECTED["screening_review_self"],
            },
        },
        "completed_screening": {
            "teacher_submission_id": 55_004_495,
            "teacher_team_name": "flg",
            "qualified_files": 38,
            "rejected_files": 0,
            "combined_observed_teacher_decisions": 6340,
            "minimum_5000_teacher_decisions_met": True,
            "e01_screening_gate_passed": True,
            "current_active_submission_changed": True,
            "current_rank_after_refresh": 4,
        },
        "request": {
            "request_ready": True,
            "authorized": False,
            "maximum_new_files": 2,
            "maximum_new_bytes": 1_135_238,
            "selected_episode_ids": [int(item["episode_id"]) for item in selected],
            "selected_strata": dict(sorted(strata.items())),
            "required_module_version": "1.32.2",
            "require_same_exact_teacher_deck_across_both_files": True,
            "output_directory_exists": False,
            "agent_logs_authorized": False,
            "additional_replays_authorized": False,
            "raw_exports_authorized": False,
            "training_authorized": False,
            "external_compute_authorized": False,
            "submission_authorized": False,
        },
        "teacher": {
            "team_id": 16_531_269,
            "team_name": "Dries @ Tufa Labs",
            "live_rank_at_refresh": 1,
            "live_team_score_at_refresh": 1205.2,
            "submission_id": 55_002_825,
            "submission_public_score": 1205.2,
            "dataset_episode_count": 128,
        },
        "confirmation": {
            "requires_two_independent_recent_teachers": True,
            "requires_at_least_200_episodes": True,
            "requires_at_least_25000_meaningful_teacher_decisions": True,
            "probe_completes_confirmation": False,
            "confirmation_gate_passed": False,
        },
        "qualification": {
            "completed_flg_screening_qualified": True,
            "current_rank_1_dries_strength_metadata_qualified": True,
            "dries_confirmation_probe_request_ready": True,
            "dries_exact_deck_qualified": False,
            "dries_action_alignment_qualified": False,
            "confirmation_gate_passed": False,
            "replay_transfer_authorized": False,
            "training_authorized": False,
        },
        "next_action": "REQUEST_EXPLICIT_APPROVAL_FOR_EXACT_TWO_FILE_DRIES_CONFIRMATION_TEACHER_PROBE",
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
