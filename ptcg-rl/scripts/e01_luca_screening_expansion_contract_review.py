from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
REQUEST_PATH = ROOT / "configs/e01_luca_screening_expansion_request_v1.json"
DECISION_PATH = ROOT / "docs/decisions/DEC-018_E01_LUCA_SCREENING_EXPANSION.md"
METADATA_PATH = ROOT / "reports/artifacts/raw/e01-luca-screening-expansion-candidates-v1.json"
CALIBRATION_REQUEST_PATH = ROOT / "configs/e01_luca_same_version_calibration_request_v1.json"
CALIBRATION_REVIEW_PATH = ROOT / "reports/artifacts/e01-luca-same-version-calibration-review-v1.json"
OUTPUT_PATH = ROOT / "reports/artifacts/e01-luca-screening-expansion-contract-review-v1.json"

EXPECTED = {
    "request": "c293268607ce0fc8762d543508bf2c798087ca9583cec05e3031a1906fc26962",
    "decision": "ce617725a0481d3a83c40885fb72d3049306a15f8a83cc99dda669d27a0f5a68",
    "metadata": "56e5e1e348b5bcbf0210efd039154df16f51727fe401f71ed67af41600c60c3e",
    "calibration_request": "a71621707f597e9f99c9db2dfb549f3dcf626aaf3d4f36ad182cc2d03dcd87f0",
    "calibration_review": "c5688e712d32919e495517e4ae5911e9cd7e01ad7f096dda84eea18e563d5bc4",
    "calibration_review_self": "c8436471020021b6137b24dfc4a501d6d6ec5164e4714132ed9384833fd82440",
    "deck": "cafa7652a6349be806d8ac2b9abfdb6c72ca3821f368e0d912e2d989f3b54cdd",
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
        (REQUEST_PATH, EXPECTED["request"]),
        (DECISION_PATH, EXPECTED["decision"]),
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
        or calibration_request.get("authorized") is not False
        or calibration_review.get("status") != "PASS"
        or calibration_review.get("decision")
        != "ACCEPT_LUCA_SAME_VERSION_CALIBRATION_SCREENING_FLOOR_BLOCKED"
        or calibration_review.get("review_sha256") != EXPECTED["calibration_review_self"]
        or calibration_review.get("density", {}).get("combined_observed_luca_decisions")
        != 1207
        or calibration_review.get("density", {}).get("screening_teacher_decision_shortfall")
        != 3793
        or calibration_review.get("qualification", {}).get("same_module_version_qualified")
        is not True
        or calibration_review.get("qualification", {}).get(
            "same_version_replay_contract_consistency_qualified"
        )
        is not True
        or calibration_review.get("qualification", {}).get(
            "policy_behavior_consistency_qualified"
        )
        is not True
        or calibration_review.get("qualification", {}).get(
            "minimum_5000_teacher_decisions_met"
        )
        is not False
    ):
        raise ValueError("completed calibration evidence differs")

    episodes = request.get("episodes")
    selected = metadata.get("selection", {}).get("selected_items")
    if not isinstance(episodes, list) or episodes != selected or len(episodes) != 51:
        raise ValueError("exact selected episode list differs")
    if (
        request.get("schema_version") != 1
        or request.get("decision_id") != "DEC-018"
        or request.get("status") != "READY_UNAUTHORIZED"
        or request.get("request_ready") is not True
        or request.get("authorized") is not False
        or request.get("authorization_scope") is not None
        or request.get("maximum_new_files") != 51
        or request.get("maximum_new_bytes") != 270_807_738
        or request.get("overwrite_authorized") is not False
        or request.get("teacher", {}).get("submission_id") != 54_863_653
        or request.get("teacher", {}).get("expected_deck_multiset_sha256")
        != EXPECTED["deck"]
        or request.get("dataset")
        != {
            "owner_slug": "kaggle",
            "dataset_slug": "pokemon-tcg-ai-battle-episodes-2026-07-23",
            "version": 1,
        }
    ):
        raise ValueError("screening expansion request differs")
    if sum(int(item["declared_bytes"]) for item in episodes) != 270_807_738:
        raise ValueError("exact request byte total differs")
    if len({str(item["file_name"]) for item in episodes}) != 51:
        raise ValueError("duplicate file name in screening expansion request")
    if len({int(item["episode_id"]) for item in episodes}) != 51:
        raise ValueError("duplicate episode id in screening expansion request")
    if any(item["file_name"] != f"{item['episode_id']}.json" for item in episodes):
        raise ValueError("episode/file-name binding differs")
    if any(int(item["teacher_submission_id"]) != 54_863_653 for item in episodes):
        raise ValueError("teacher submission binding differs")

    selection = metadata.get("selection")
    basis = metadata.get("calibration_basis")
    module = metadata.get("module_boundary")
    if not isinstance(selection, Mapping) or not isinstance(basis, Mapping) or not isinstance(module, Mapping):
        raise ValueError("metadata selection basis is missing")
    if (
        selection.get("selected_files") != 51
        or selection.get("selected_bytes") != 270_807_738
        or selection.get("at_or_after_anchor_files") != 27
        or selection.get("pre_anchor_boundary_files") != 24
        or selection.get("projected_luca_decisions_at_conservative_density")
        != 4200.478614492002
        or selection.get("projected_combined_luca_decisions") != 5407.478614492002
        or basis.get("screening_shortfall") != 3793
        or basis.get("conservative_density_per_mib") != 16.264384083698396
        or basis.get("reserve_multiplier") != 1.1
        or module.get("anchor_episode_id") != 87_731_214
        or module.get("file_by_file_required_module_version") != "1.32.2"
        or module.get("nonmatching_files_must_be_rejected_from_decision_counts")
        is not True
    ):
        raise ValueError("metadata sizing contract differs")

    boundary = request.get("review_boundary")
    if not isinstance(boundary, Mapping):
        raise ValueError("review boundary is missing")
    if (
        boundary.get("count_only_module_version") != "1.32.2"
        or boundary.get("reject_nonmatching_module_files_from_decision_counts")
        is not True
        or boundary.get("require_exact_deck_hash_for_counted_files") != EXPECTED["deck"]
        or boundary.get("require_aggregate_action_alignment") is not True
        or boundary.get("report_accepted_and_rejected_files") is not True
    ):
        raise ValueError("file-by-file acceptance boundary differs")
    zero_fields = (
        "raw_replay_body_exports",
        "raw_step_exports",
        "action_sequence_exports",
        "observation_exports",
        "option_exports",
        "card_list_exports",
        "training_label_exports",
        "agent_log_downloads",
        "additional_replay_downloads_after_named_files",
        "optimizer_steps",
    )
    if any(boundary.get(field) != 0 for field in zero_fields):
        raise ValueError("request authorizes a prohibited export or execution")
    if any(boundary.get(field) is not False for field in ("training", "external_compute", "submission")):
        raise ValueError("request authorizes prohibited execution")

    output = ROOT / str(request["output_directory"])
    if output.exists():
        raise ValueError("screening expansion output directory already exists")
    decision_raw = DECISION_PATH.read_text(encoding="utf-8")
    for required in (
        "Status: Accepted",
        "51 named Luca episodes",
        "270,807,738 bytes",
        "does **not** authorize downloading any of the 51 replay bodies",
        "A nonmatching file is rejected from decision counts",
    ):
        if required not in decision_raw:
            raise ValueError(f"DEC-018 is missing required text: {required}")

    report: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e01-luca-screening-expansion-contract-review-v1",
        "created_at_utc": request.get("created_at_utc"),
        "source_path": "reports/artifacts/e01-luca-screening-expansion-contract-review-v1.json",
        "producer": "scripts/e01_luca_screening_expansion_contract_review.py",
        "reviewed_decision": "DEC-018",
        "status": "PASS",
        "decision": "ACCEPT_EXACT_51_FILE_LUCA_SCREENING_EXPANSION_REQUEST_UNAUTHORIZED",
        "inputs": {
            "decision": {"path": str(DECISION_PATH.relative_to(ROOT)), "sha256": EXPECTED["decision"]},
            "request": {"path": str(REQUEST_PATH.relative_to(ROOT)), "sha256": EXPECTED["request"]},
            "candidate_metadata": {"path": str(METADATA_PATH.relative_to(ROOT)), "sha256": EXPECTED["metadata"]},
            "calibration_request": {"path": str(CALIBRATION_REQUEST_PATH.relative_to(ROOT)), "sha256": EXPECTED["calibration_request"]},
            "calibration_review": {
                "path": str(CALIBRATION_REVIEW_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["calibration_review"],
                "review_sha256": EXPECTED["calibration_review_self"],
            },
        },
        "request": {
            "request_ready": True,
            "authorized": False,
            "output_directory_exists": False,
            "maximum_new_files": 51,
            "maximum_new_bytes": 270_807_738,
            "at_or_after_anchor_files": 27,
            "pre_anchor_boundary_files": 24,
            "count_only_module_version": "1.32.2",
            "nonmatching_files_rejected_from_counts": True,
            "agent_logs_authorized": False,
            "additional_replays_authorized": False,
            "raw_exports_authorized": False,
            "training_authorized": False,
            "external_compute_authorized": False,
        },
        "calibration": {
            "combined_observed_luca_decisions": 1207,
            "screening_shortfall": 3793,
            "conservative_density_per_mib": 16.264384083698396,
            "reserve_multiplier": 1.1,
            "projected_additional_luca_decisions": 4200.478614492002,
            "projection_is_guarantee": False,
        },
        "qualification": {
            "gold_region_teacher_qualified": True,
            "same_version_source_consistency_qualified": True,
            "minimum_5000_teacher_decisions_met": False,
            "e01_screening_gate_passed": False,
            "screening_expansion_request_ready": True,
            "replay_transfer_authorized": False,
            "training_authorized": False,
        },
        "next_action": "REQUEST_EXPLICIT_APPROVAL_FOR_EXACT_51_FILE_LUCA_SCREENING_EXPANSION",
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
