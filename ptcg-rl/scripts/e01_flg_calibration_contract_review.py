from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
DECISION_PATH = ROOT / "docs/decisions/DEC-020_E01_FLG_DRAGAPULT_CALIBRATION.md"
REQUEST_PATH = ROOT / "configs/e01_flg_dragapult_calibration_request_v1.json"
METADATA_PATH = ROOT / "reports/artifacts/raw/e01-flg-dragapult-calibration-candidates-v1.json"
PROBE_REQUEST_PATH = ROOT / "configs/e01_flg_gold_teacher_probe_request_v1.json"
PROBE_REVIEW_PATH = ROOT / "reports/artifacts/e01-flg-gold-teacher-probe-review-v1.json"
LIVE_PATH = ROOT / "reports/artifacts/raw/e01-live-gold-refresh-v1.json"
OUTPUT_PATH = ROOT / "reports/artifacts/e01-flg-dragapult-calibration-contract-review-v1.json"

EXPECTED = {
    "decision": "1f30b8081cdfea4113f60fdfe76213902f1bf3afc645ab0a4a0c1b4301766547",
    "request": "644be06359e6ad1f49224bab4fee68af562e026d4be93f536ae86bbc00f74eb8",
    "metadata": "038d88b1350b4463aec5879b5be8f496630804fe62e3d2e298e2075e9d98c42e",
    "probe_request": "b1b0b81014fddeea8c5bb9d5be41a61ea538e1a3723eb64a246c87668c49b349",
    "probe_review": "c20c15c9325b44b81adf58a81ef962f1820bb53c68e7c5872bee81ae7398a17a",
    "probe_review_self": "b6769479e7969688ba613ac9ab99b6f7a3cd27f54684e5c4b4a44ef60282a7a4",
    "live": "410b137a7ed4052111d6e16c373fbdc1b1ae484de4ad152a06420981c0870120",
    "deck": "89e6155f25310ee695c0761c85d3ae8e44f376456ff0539231820f8e803f2d5e",
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
        (PROBE_REQUEST_PATH, EXPECTED["probe_request"]),
        (PROBE_REVIEW_PATH, EXPECTED["probe_review"]),
        (LIVE_PATH, EXPECTED["live"]),
    ):
        require_hash(path, expected)
    request = load_json(REQUEST_PATH)
    metadata = load_json(METADATA_PATH)
    probe_request = load_json(PROBE_REQUEST_PATH)
    probe_review = load_json(PROBE_REVIEW_PATH)
    if probe_review.get("review_sha256") != EXPECTED["probe_review_self"]:
        raise ValueError("probe review self hash differs")
    if (
        probe_request.get("status") != "CONSUMED"
        or probe_request.get("authorized") is not False
        or probe_review.get("status") != "PASS"
        or probe_review.get("consistency", {}).get("teacher_deck_multiset_sha256")
        != EXPECTED["deck"]
        or probe_review.get("consistency", {}).get("teacher_archetype_context_label")
        != "Dragapult ex"
        or probe_review.get("consistency", {}).get("combined_teacher_active_selection_requests")
        != 94
    ):
        raise ValueError("completed current rank-1 probe differs")

    episodes = request.get("episodes")
    selection = metadata.get("selection")
    teacher = request.get("teacher")
    boundary = request.get("review_boundary")
    if not all(isinstance(value, Mapping) for value in (selection, teacher, boundary)):
        raise ValueError("calibration bindings are missing")
    if not isinstance(episodes, list) or len(episodes) != 12:
        raise ValueError("calibration must contain 12 episodes")
    if episodes != selection.get("episodes"):
        raise ValueError("request episodes differ from candidate metadata")
    strata = Counter(item.get("stratum") for item in episodes)
    if strata != Counter(
        {"seat_0_loss": 3, "seat_0_win": 3, "seat_1_loss": 3, "seat_1_win": 3}
    ):
        raise ValueError("calibration strata differ")
    if len({item.get("episode_id") for item in episodes}) != 12:
        raise ValueError("calibration episode IDs are duplicated")
    if any(item.get("episode_id") in {88_302_734, 88_333_037} for item in episodes):
        raise ValueError("probe episode is repeated in calibration")
    if sum(int(item["declared_bytes"]) for item in episodes) != 63_562_985:
        raise ValueError("calibration byte total differs")
    if (
        request.get("decision_id") != "DEC-020"
        or request.get("status") != "READY_UNAUTHORIZED"
        or request.get("request_ready") is not True
        or request.get("authorized") is not False
        or request.get("authorization_scope") is not None
        or request.get("maximum_new_files") != 12
        or request.get("maximum_new_bytes") != 63_562_985
        or request.get("overwrite_authorized") is not False
        or request.get("output_directory")
        != "private/g3/e01/flg-dragapult-calibration-v1"
        or teacher.get("team_id") != 16_380_946
        or teacher.get("team_name") != "flg"
        or teacher.get("submission_id") != 55_004_495
        or teacher.get("live_rank_at_refresh") != 1
        or teacher.get("submission_public_score") != 1244.2
        or teacher.get("dataset_episode_count") != 131
        or teacher.get("expected_deck_multiset_sha256") != EXPECTED["deck"]
        or teacher.get("archetype_context_label") != "Dragapult ex"
    ):
        raise ValueError("calibration request contract differs")
    if (
        boundary.get("require_module_version") != "1.32.2"
        or boundary.get("require_exact_deck_hash") != EXPECTED["deck"]
        or boundary.get("require_aggregate_action_alignment") is not True
        or boundary.get("measure_teacher_decision_density") is not True
    ):
        raise ValueError("calibration review boundary differs")
    for key in (
        "agent_log_downloads",
        "additional_replay_downloads_after_named_files",
        "raw_replay_body_exports",
        "raw_step_exports",
        "request_exports",
        "option_exports",
        "observation_exports",
        "action_sequence_exports",
        "card_list_exports",
        "training_label_exports",
        "optimizer_steps",
    ):
        if boundary.get(key) != 0:
            raise ValueError(f"boundary must remain zero: {key}")
    for key in ("training", "external_compute", "submission"):
        if boundary.get(key) is not False:
            raise ValueError(f"boundary must remain false: {key}")
    if (ROOT / str(request["output_directory"])).exists():
        raise ValueError("calibration output directory already exists")

    report: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e01-flg-dragapult-calibration-contract-review-v1",
        "created_at_utc": request.get("created_at_utc"),
        "source_path": "reports/artifacts/e01-flg-dragapult-calibration-contract-review-v1.json",
        "producer": "scripts/e01_flg_calibration_contract_review.py",
        "reviewed_decision": "DEC-020",
        "status": "PASS",
        "decision": "ACCEPT_EXACT_12_FILE_CURRENT_RANK_1_DRAGAPULT_CALIBRATION_REQUEST_UNAUTHORIZED",
        "inputs": {
            "decision": {"path": str(DECISION_PATH.relative_to(ROOT)), "sha256": EXPECTED["decision"]},
            "request": {"path": str(REQUEST_PATH.relative_to(ROOT)), "sha256": EXPECTED["request"]},
            "candidate_metadata": {"path": str(METADATA_PATH.relative_to(ROOT)), "sha256": EXPECTED["metadata"]},
            "completed_probe_request": {"path": str(PROBE_REQUEST_PATH.relative_to(ROOT)), "sha256": EXPECTED["probe_request"]},
            "completed_probe_review": {"path": str(PROBE_REVIEW_PATH.relative_to(ROOT)), "sha256": EXPECTED["probe_review"], "review_sha256": EXPECTED["probe_review_self"]},
            "live_refresh": {"path": str(LIVE_PATH.relative_to(ROOT)), "sha256": EXPECTED["live"]},
        },
        "request": {
            "request_ready": True,
            "authorized": False,
            "maximum_new_files": 12,
            "maximum_new_bytes": 63_562_985,
            "required_module_version": "1.32.2",
            "required_deck_multiset_sha256": EXPECTED["deck"],
            "balanced_strata": dict(sorted(strata.items())),
            "output_directory_exists": False,
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
            "current_rank_1_calibration_request_ready": True,
            "minimum_5000_teacher_decisions_met": False,
            "e01_screening_gate_passed": False,
            "replay_transfer_authorized": False,
            "training_authorized": False,
        },
        "next_action": "REQUEST_EXPLICIT_APPROVAL_FOR_EXACT_12_FILE_FLG_DRAGAPULT_CALIBRATION",
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
