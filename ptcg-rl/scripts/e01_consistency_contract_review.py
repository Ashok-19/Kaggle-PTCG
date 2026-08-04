from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
REQUEST_PATH = ROOT / "configs/e01_same_submission_consistency_request_v1.json"
DECISION_PATH = ROOT / "docs/decisions/DEC-015_E01_SAME_SUBMISSION_CONSISTENCY_PROBE.md"
PROBE_REQUEST_PATH = ROOT / "configs/e01_provenance_probe_request_v2.json"
PROBE_REVIEW_PATH = ROOT / "reports/artifacts/e01-provenance-probe-review-v1.json"
CANDIDATE_METADATA_PATH = (
    ROOT / "reports/artifacts/raw/e01-benarg-consistency-candidate-metadata-v1.json"
)
OUTPUT_PATH = (
    ROOT / "reports/artifacts/e01-same-submission-consistency-contract-review-v1.json"
)
PRIVATE_OUTPUT = ROOT / "private/g3/e01/consistency-probe-v1"

EXPECTED = {
    "request_sha256": "3cee666da8c141f19c4a6f7ab8ce68e477b8bb27675c48c0427e095941aaaaa2",
    "decision_sha256": "884ef8dd592d4296042b474f4900cbb18c89e3bf2ec9e6aebee4e35dde5dda1e",
    "probe_request_sha256": "b9e27cd30f4ebd8f3db767c3da5708b3330a5052f651b5f666420e02815ce34b",
    "probe_review_sha256": "94c8d1e90400f9fb950f1950e1a3ef37b66fca3a81767c0ab502affa5e58d92c",
    "probe_review_self_hash": "f09117848e457b836c020c7c8112519d24daf392a74f14ba4c26a81b1618fec7",
    "candidate_metadata_sha256": "971e4f2b9323aa17bfa98e6b6a16f17a99d4e4b17af2acbae1b7dd02d69ff577",
}


class ConsistencyContractError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def load_object(path: Path, label: str) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ConsistencyContractError(f"{label} must be an object")
    return value


def build_report() -> dict[str, Any]:
    observed = {
        "request_sha256": sha256_file(REQUEST_PATH),
        "decision_sha256": sha256_file(DECISION_PATH),
        "probe_request_sha256": sha256_file(PROBE_REQUEST_PATH),
        "probe_review_sha256": sha256_file(PROBE_REVIEW_PATH),
        "candidate_metadata_sha256": sha256_file(CANDIDATE_METADATA_PATH),
    }
    for key, expected in EXPECTED.items():
        if key in observed and observed[key] != expected:
            raise ConsistencyContractError(f"hash differs for {key}")

    request = load_object(REQUEST_PATH, "request")
    probe_request = load_object(PROBE_REQUEST_PATH, "completed probe request")
    probe_review = load_object(PROBE_REVIEW_PATH, "completed probe review")
    metadata = load_object(CANDIDATE_METADATA_PATH, "candidate metadata")

    if (
        request.get("status") != "READY_UNAUTHORIZED"
        or request.get("request_ready") is not True
        or request.get("authorized") is not False
        or request.get("authorization_scope") is not None
    ):
        raise ConsistencyContractError("request authorization boundary differs")
    if probe_request.get("status") != "CONSUMED" or probe_request.get("authorized") is not False:
        raise ConsistencyContractError("completed probe request is not consumed")
    if (
        probe_review.get("status") != "PASS"
        or probe_review.get("decision")
        != "ACCEPT_PROVENANCE_ONLY_E01_SCREENING_BLOCKED"
        or probe_review.get("review_sha256") != EXPECTED["probe_review_self_hash"]
    ):
        raise ConsistencyContractError("completed probe review differs")

    existing = request.get("existing_probe")
    additional = request.get("additional_episode")
    selection = request.get("selection_basis")
    boundary = request.get("comparison_boundary")
    if not all(isinstance(value, Mapping) for value in (existing, additional, selection, boundary)):
        raise ConsistencyContractError("request sections are missing")
    if (
        existing.get("episode_id") != 87_703_034
        or existing.get("submission_id") != 54_933_084
        or existing.get("submission_player_index") != 0
        or existing.get("submission_reward") != 1
        or existing.get("deck_multiset_sha256")
        != "606a775392ffe25e058b19c17801d58a4bf30f7cd8c62782388d3de7e7eb5283"
    ):
        raise ConsistencyContractError("existing probe binding differs")
    if (
        additional.get("episode_id") != 87_741_212
        or additional.get("file_name") != "87741212.json"
        or additional.get("declared_bytes") != 559_779
        or additional.get("submission_id") != 54_933_084
        or additional.get("team_id") != 16_401_597
        or additional.get("team_name") != "Benarg"
        or additional.get("submission_player_index") != 1
        or additional.get("submission_reward") != -1
    ):
        raise ConsistencyContractError("additional episode binding differs")
    if (
        request.get("maximum_new_files") != 1
        or request.get("maximum_new_bytes") != 559_779
        or request.get("output_directory") != "private/g3/e01/consistency-probe-v1"
        or request.get("overwrite_authorized") is not False
        or PRIVATE_OUTPUT.exists()
    ):
        raise ConsistencyContractError("output or byte boundary differs")
    if selection != {
        "same_exact_submission": True,
        "smallest_additional_file": True,
        "other_same_submission_candidates_considered": 111,
        "opposite_player_slot": True,
        "opposite_terminal_result": True,
        "leaderboard_rating_used": False,
        "replay_body_used_for_selection": False,
    }:
        raise ConsistencyContractError("selection basis differs")
    required_true = {
        "compare_submission_id",
        "compare_team_name",
        "compare_replay_schema",
        "compare_module_version",
        "compare_exact_60_card_deck_hash",
        "compare_current_asset_deck_construction_checks",
        "compare_aggregate_action_alignment",
    }
    if any(boundary.get(key) is not True for key in required_true):
        raise ConsistencyContractError("required comparison is disabled")
    expected_zero = {
        "agent_log_downloads",
        "additional_replay_downloads_after_named_file",
        "raw_replay_body_exports",
        "raw_step_exports",
        "action_sequence_exports",
        "observation_exports",
        "training_label_exports",
        "optimizer_steps",
    }
    if any(boundary.get(key) != 0 for key in expected_zero):
        raise ConsistencyContractError("zero-export boundary differs")
    if any(boundary.get(key) is not False for key in ("external_compute", "training", "submission")):
        raise ConsistencyContractError("execution boundary differs")

    metadata_selected = metadata.get("selected_additional_candidate")
    metadata_existing = metadata.get("existing_probe")
    metadata_selection = metadata.get("selection_basis")
    if not all(isinstance(value, Mapping) for value in (metadata_selected, metadata_existing, metadata_selection)):
        raise ConsistencyContractError("candidate metadata sections are missing")
    if (
        metadata_selected.get("episode_id") != additional.get("episode_id")
        or metadata_selected.get("file_name") != additional.get("file_name")
        or metadata_selected.get("declared_bytes") != additional.get("declared_bytes")
        or metadata_existing.get("episode_id") != existing.get("episode_id")
        or metadata.get("submission", {}).get("other_episodes_present_in_dataset") != 111
        or metadata_selection.get("smallest_declared_file_among_other_same_submission_dataset_episodes")
        is not True
    ):
        raise ConsistencyContractError("request is not reproduced by candidate metadata")

    decision_text = DECISION_PATH.read_text(encoding="utf-8")
    for required in (
        "Status: Accepted",
        "87741212.json",
        "559779",
        "does **not** authorize",
        "no third replay",
    ):
        if required not in decision_text:
            raise ConsistencyContractError(f"DEC-015 missing required text: {required}")

    report: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e01-same-submission-consistency-contract-review-v1",
        "created_at_utc": "2026-07-24T16:29:06.837912Z",
        "source_path": "reports/artifacts/e01-same-submission-consistency-contract-review-v1.json",
        "producer": "scripts/e01_consistency_contract_review.py",
        "reviewed_decision": "DEC-015",
        "status": "PASS",
        "decision": "ACCEPT_ONE_FILE_CONSISTENCY_REQUEST_UNAUTHORIZED",
        "inputs": {
            "request": {
                "path": "configs/e01_same_submission_consistency_request_v1.json",
                "sha256": EXPECTED["request_sha256"],
            },
            "decision": {
                "path": "docs/decisions/DEC-015_E01_SAME_SUBMISSION_CONSISTENCY_PROBE.md",
                "sha256": EXPECTED["decision_sha256"],
            },
            "completed_probe_request": {
                "path": "configs/e01_provenance_probe_request_v2.json",
                "sha256": EXPECTED["probe_request_sha256"],
            },
            "completed_probe_review": {
                "path": "reports/artifacts/e01-provenance-probe-review-v1.json",
                "sha256": EXPECTED["probe_review_sha256"],
                "review_sha256": EXPECTED["probe_review_self_hash"],
            },
            "candidate_metadata": {
                "path": "reports/artifacts/raw/e01-benarg-consistency-candidate-metadata-v1.json",
                "sha256": EXPECTED["candidate_metadata_sha256"],
            },
        },
        "request": {
            "request_ready": True,
            "authorized": False,
            "output_directory_exists": False,
            "maximum_new_files": 1,
            "maximum_new_bytes": 559_779,
            "episode_id": 87_741_212,
            "file_name": "87741212.json",
            "same_submission_id": 54_933_084,
            "opposite_player_slot": True,
            "opposite_terminal_result": True,
            "agent_logs_authorized": False,
            "third_replay_authorized": False,
            "training_authorized": False,
            "external_compute_authorized": False,
        },
        "qualification": {
            "completed_provenance_probe_passed": True,
            "same_submission_consistency_qualified": False,
            "teacher_strength_qualified": False,
            "exact_historical_deck_legality_qualified": False,
            "e01_screening_gate_passed": False,
            "replay_transfer_authorized": False,
            "training_authorized": False,
        },
        "next_action": (
            "REQUEST_EXPLICIT_APPROVAL_FOR_EXACT_87741212_JSON_CONSISTENCY_PROBE"
        ),
        "cost_usd": 0.0,
    }
    report["review_sha256"] = canonical_sha256(
        {key: value for key, value in report.items() if key != "review_sha256"}
    )
    return report


def main() -> int:
    report = build_report()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT_PATH.with_suffix(OUTPUT_PATH.suffix + ".partial")
    temporary.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(OUTPUT_PATH)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
