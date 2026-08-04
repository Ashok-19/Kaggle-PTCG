from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
DECISION_PATH = ROOT / "docs/decisions/DEC-017_E01_LUCA_SAME_VERSION_CALIBRATION.md"
METADATA_PATH = ROOT / "reports/artifacts/raw/e01-luca-same-version-calibration-candidates-v1.json"
REQUEST_PATH = ROOT / "configs/e01_luca_same_version_calibration_request_v1.json"
PRIOR_REQUEST_PATH = ROOT / "configs/e01_luca_gold_teacher_probe_request_v1.json"
PRIOR_REVIEW_PATH = ROOT / "reports/artifacts/e01-luca-gold-teacher-probe-review-v1.json"
OUTPUT_PATH = ROOT / "reports/artifacts/e01-luca-same-version-calibration-contract-review-v1.json"

EXPECTED = {
    "decision": "1dd14efd37f07fdf00de5e50925556c00736aea04222f2972b6812a0ee0bfd83",
    "metadata": "9efd5da48e7f6d76bdd7065c3cbbb95c1be26bb22cb642707994a8be7504d1e0",
    "request": "5b8b6b91d4d407cf06ff3270f1852c55c334d33ef34c4e915bf0097de262009a",
    "prior_request": "b70efe6228d08f78c104e75c3007d4e1b99c747223d05d1d14e9808f975146a2",
    "prior_review": "533cb71425a8f233885855ca1377d2fc67b56d24ced96a09a8f52934ce083c70",
    "prior_review_self": "071784291ac0acc772337c326857f261f1781ab21901d4bf26ab928ec8cb543c",
    "deck": "cafa7652a6349be806d8ac2b9abfdb6c72ca3821f368e0d912e2d989f3b54cdd",
}
EXPECTED_FILES = {
    87732247: ("87732247.json", 5999663, 0, 1),
    87733289: ("87733289.json", 5047771, 0, -1),
    87733748: ("87733748.json", 4942976, 0, -1),
    87734353: ("87734353.json", 3934914, 0, 1),
    87736454: ("87736454.json", 5122828, 1, -1),
    87737495: ("87737495.json", 6627479, 1, -1),
    87739090: ("87739090.json", 6109840, 0, -1),
    87739639: ("87739639.json", 6699033, 1, 1),
    87741191: ("87741191.json", 6065629, 1, 1),
    87744901: ("87744901.json", 5544479, 1, 1),
    87744904: ("87744904.json", 4958020, 0, 1),
    87745939: ("87745939.json", 2775425, 1, -1),
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


def item_binding(item: Mapping[str, Any]) -> tuple[str, int, int, int]:
    episode_id = item.get("episode_id")
    if isinstance(episode_id, bool) or not isinstance(episode_id, int):
        raise ValueError("episode id differs")
    return (
        str(item.get("file_name")),
        int(item.get("declared_bytes", -1)),
        int(item.get("teacher_player_index", -1)),
        int(item.get("teacher_reward", 0)),
    )


def build_report() -> dict[str, Any]:
    for path, expected in (
        (DECISION_PATH, EXPECTED["decision"]),
        (METADATA_PATH, EXPECTED["metadata"]),
        (REQUEST_PATH, EXPECTED["request"]),
        (PRIOR_REQUEST_PATH, EXPECTED["prior_request"]),
        (PRIOR_REVIEW_PATH, EXPECTED["prior_review"]),
    ):
        require_hash(path, expected)
    metadata = load_json(METADATA_PATH)
    request = load_json(REQUEST_PATH)
    prior_request = load_json(PRIOR_REQUEST_PATH)
    prior_review = load_json(PRIOR_REVIEW_PATH)
    if prior_request.get("status") != "CONSUMED" or prior_request.get("authorized") is not False:
        raise ValueError("prior Luca request is not consumed")
    if prior_review.get("status") != "PASS" or prior_review.get("review_sha256") != EXPECTED["prior_review_self"]:
        raise ValueError("prior Luca review differs")
    prior_qualification = prior_review.get("qualification")
    if not isinstance(prior_qualification, Mapping):
        raise ValueError("prior qualification is missing")
    if (
        prior_qualification.get("teacher_strength_qualified") is not True
        or prior_qualification.get("exact_deck_consistency_qualified") is not True
        or prior_qualification.get("action_aligned_supervision_available") is not True
        or prior_qualification.get("same_module_version_qualified") is not False
        or prior_qualification.get("minimum_5000_teacher_decisions_met") is not False
    ):
        raise ValueError("prior Luca qualification differs")

    if (
        metadata.get("schema_version") != 1
        or metadata.get("record_id") != "e01-luca-same-version-calibration-candidates-v1"
        or metadata.get("collection_boundary", {}).get("replay_bodies_downloaded") != 0
        or metadata.get("collection_boundary", {}).get("agent_logs_downloaded") != 0
        or metadata.get("collection_boundary", {}).get("training_labels_created") != 0
        or metadata.get("collection_boundary", {}).get("optimizer_steps") != 0
    ):
        raise ValueError("metadata collection boundary differs")
    selection = metadata.get("selection")
    if not isinstance(selection, Mapping):
        raise ValueError("metadata selection is missing")
    metadata_items = selection.get("selected_items")
    if not isinstance(metadata_items, list) or len(metadata_items) != 12:
        raise ValueError("metadata selected file count differs")
    metadata_bindings = {
        int(item["episode_id"]): item_binding(item)
        for item in metadata_items
        if isinstance(item, Mapping)
    }
    if metadata_bindings != EXPECTED_FILES:
        raise ValueError("metadata exact file bindings differ")
    if selection.get("total_bytes") != 63828057 or selection.get("maximum_total_bytes") != 67108864:
        raise ValueError("metadata byte cap differs")
    strata = Counter((binding[2], binding[3]) for binding in metadata_bindings.values())
    if strata != Counter({(0, 1): 3, (0, -1): 3, (1, 1): 3, (1, -1): 3}):
        raise ValueError("metadata stratum balance differs")

    if (
        request.get("schema_version") != 1
        or request.get("record_id") != "e01-luca-same-version-calibration-request-v1"
        or request.get("decision_id") != "DEC-017"
        or request.get("status") != "READY_UNAUTHORIZED"
        or request.get("request_ready") is not True
        or request.get("authorized") is not False
        or request.get("authorization_scope") is not None
        or request.get("maximum_new_files") != 12
        or request.get("maximum_new_bytes") != 63828057
        or request.get("overwrite_authorized") is not False
    ):
        raise ValueError("request authorization boundary differs")
    request_items = request.get("episodes")
    if not isinstance(request_items, list) or len(request_items) != 12:
        raise ValueError("request file count differs")
    request_bindings = {
        int(item["episode_id"]): item_binding(item)
        for item in request_items
        if isinstance(item, Mapping)
    }
    if request_bindings != EXPECTED_FILES or request_bindings != metadata_bindings:
        raise ValueError("request exact file bindings differ")
    if request.get("candidate_metadata_sha256") != EXPECTED["metadata"]:
        raise ValueError("request metadata hash differs")
    if request.get("completed_teacher_probe_review_sha256") != EXPECTED["prior_review"]:
        raise ValueError("request prior review hash differs")
    if request.get("completed_teacher_probe_review_self_hash") != EXPECTED["prior_review_self"]:
        raise ValueError("request prior review self hash differs")
    teacher = request.get("teacher")
    boundary = request.get("review_boundary")
    if not isinstance(teacher, Mapping) or not isinstance(boundary, Mapping):
        raise ValueError("teacher or review boundary is missing")
    if (
        teacher.get("submission_id") != 54863653
        or teacher.get("team_name") != "Luca"
        or teacher.get("leaderboard_rank") != 2
        or teacher.get("expected_deck_multiset_sha256") != EXPECTED["deck"]
        or boundary.get("require_module_version") != "1.32.2"
        or boundary.get("require_exact_deck_hash") != EXPECTED["deck"]
        or boundary.get("agent_log_downloads") != 0
        or boundary.get("additional_replay_downloads_after_named_files") != 0
        or boundary.get("raw_step_exports") != 0
        or boundary.get("action_sequence_exports") != 0
        or boundary.get("observation_exports") != 0
        or boundary.get("training_label_exports") != 0
        or boundary.get("optimizer_steps") != 0
        or boundary.get("external_compute") is not False
        or boundary.get("training") is not False
        or boundary.get("submission") is not False
    ):
        raise ValueError("teacher or review boundary differs")
    output_directory = ROOT / str(request.get("output_directory"))
    if output_directory.exists():
        raise ValueError("calibration output directory already exists")

    decision_text = DECISION_PATH.read_text(encoding="utf-8")
    for required in (
        "Status: Accepted",
        "63,828,057 bytes",
        "does **not** authorize downloading",
        "module version exactly `1.32.2`",
        "any replay outside the exact 12-file list",
    ):
        if required not in decision_text:
            raise ValueError(f"DEC-017 is missing required text: {required}")

    report: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e01-luca-same-version-calibration-contract-review-v1",
        "created_at_utc": request.get("created_at_utc"),
        "source_path": "reports/artifacts/e01-luca-same-version-calibration-contract-review-v1.json",
        "producer": "scripts/e01_luca_calibration_contract_review.py",
        "reviewed_decision": "DEC-017",
        "status": "PASS",
        "decision": "ACCEPT_EXACT_12_FILE_LUCA_CALIBRATION_REQUEST_UNAUTHORIZED",
        "inputs": {
            "decision": {"path": str(DECISION_PATH.relative_to(ROOT)), "sha256": EXPECTED["decision"]},
            "candidate_metadata": {"path": str(METADATA_PATH.relative_to(ROOT)), "sha256": EXPECTED["metadata"]},
            "request": {"path": str(REQUEST_PATH.relative_to(ROOT)), "sha256": EXPECTED["request"]},
            "completed_teacher_probe_request": {"path": str(PRIOR_REQUEST_PATH.relative_to(ROOT)), "sha256": EXPECTED["prior_request"]},
            "completed_teacher_probe_review": {"path": str(PRIOR_REVIEW_PATH.relative_to(ROOT)), "sha256": EXPECTED["prior_review"], "review_sha256": EXPECTED["prior_review_self"]},
        },
        "teacher": {
            "submission_id": 54863653,
            "team_id": 16448747,
            "team_name": "Luca",
            "leaderboard_rank": 2,
            "leaderboard_team_score": 1190.4,
            "submission_public_score": 1180.9,
            "expected_deck_multiset_sha256": EXPECTED["deck"],
        },
        "request": {
            "request_ready": True,
            "authorized": False,
            "maximum_new_files": 12,
            "maximum_new_bytes": 63828057,
            "output_directory_exists": False,
            "balanced_strata": {"seat_0_win": 3, "seat_0_loss": 3, "seat_1_win": 3, "seat_1_loss": 3},
            "required_module_version": "1.32.2",
            "agent_logs_authorized": False,
            "additional_replays_authorized": False,
            "raw_exports_authorized": False,
            "training_authorized": False,
            "external_compute_authorized": False,
        },
        "qualification": {
            "gold_region_teacher_qualified": True,
            "exact_deck_consistency_from_probe_qualified": True,
            "calibration_candidate_pool_available": True,
            "calibration_request_ready": True,
            "same_version_policy_consistency_qualified": False,
            "minimum_5000_teacher_decisions_met": False,
            "e01_screening_gate_passed": False,
            "replay_transfer_authorized": False,
            "training_authorized": False,
        },
        "next_action": "REQUEST_EXPLICIT_APPROVAL_FOR_EXACT_12_FILE_LUCA_CALIBRATION_BATCH",
        "cost_usd": 0.0,
    }
    report["review_sha256"] = self_hash(report, "review_sha256")
    return report


def main() -> None:
    report = build_report()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT_PATH.with_suffix(OUTPUT_PATH.suffix + ".partial")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(OUTPUT_PATH)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
