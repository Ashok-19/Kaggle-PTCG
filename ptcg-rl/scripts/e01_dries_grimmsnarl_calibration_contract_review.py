from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
DECISION_PATH = ROOT / "docs/decisions/DEC-023_E01_DRIES_GRIMMSNARL_CALIBRATION.md"
REQUEST_PATH = ROOT / "configs/e01_dries_grimmsnarl_calibration_request_v1.json"
METADATA_PATH = ROOT / "reports/artifacts/raw/e01-dries-grimmsnarl-calibration-candidates-v1.json"
PROBE_REQUEST_PATH = ROOT / "configs/e01_dries_confirmation_teacher_probe_request_v1.json"
PROBE_REVIEW_PATH = ROOT / "reports/artifacts/e01-dries-confirmation-teacher-probe-review-v1.json"
LIVE_PATH = ROOT / "reports/artifacts/raw/e01-live-confirmation-refresh-v1.json"
FLG_SCREENING_PATH = ROOT / "reports/artifacts/e01-flg-dragapult-screening-expansion-review-v1.json"
OUTPUT_PATH = ROOT / "reports/artifacts/e01-dries-grimmsnarl-calibration-contract-review-v1.json"

EXPECTED = {
    "decision": "9ea27e6e2f5f41953a2ef2eb68af0840a0297a7640832480b232674826403460",
    "request": "768cd21cc71fbe38586b07d6807794bd8215cfd7f8aa10601000be5877cb6509",
    "metadata": "18e84036a294c57e6d805114270815c84cddea903cad5599a5cb5bab83603bcd",
    "probe_request": "9e558be620bcf9722ba69ae7189ebec79145b351c20e4370eb1bb37d2427d2bc",
    "probe_review": "42d65b6f40fd2a2767ed3b7ed56852c2a7efb096c159f97f294c8fe6183008e0",
    "probe_review_self": "85845efb12c00b4fc489daa65be9291d1ff0db2d18e55261c66d107c8c64422c",
    "live": "7642598704cca4899235089c57e6429805ebb8ea496e4c5b47befc677e4b80dc",
    "flg_screening": "38f1e6f4f0d68b52677e6e578ac7f69ca0730f819bc895b5205d42387f7c8fc2",
    "flg_screening_self": "0346535b89f0f14e153df0afeda90609f51e2a0d75b4b959df38be71dfb7df80",
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
        (DECISION_PATH, EXPECTED["decision"]),
        (REQUEST_PATH, EXPECTED["request"]),
        (METADATA_PATH, EXPECTED["metadata"]),
        (PROBE_REQUEST_PATH, EXPECTED["probe_request"]),
        (PROBE_REVIEW_PATH, EXPECTED["probe_review"]),
        (LIVE_PATH, EXPECTED["live"]),
        (FLG_SCREENING_PATH, EXPECTED["flg_screening"]),
    ):
        require_hash(path, expected)
    request = load_json(REQUEST_PATH)
    metadata = load_json(METADATA_PATH)
    probe_request = load_json(PROBE_REQUEST_PATH)
    probe_review = load_json(PROBE_REVIEW_PATH)
    flg_screening = load_json(FLG_SCREENING_PATH)
    if probe_review.get("review_sha256") != EXPECTED["probe_review_self"]:
        raise ValueError("probe review self hash differs")
    if flg_screening.get("review_sha256") != EXPECTED["flg_screening_self"]:
        raise ValueError("flg screening review self hash differs")
    consistency = probe_review.get("consistency")
    confirmation = probe_review.get("confirmation")
    qualification = probe_review.get("qualification")
    if not all(
        isinstance(value, Mapping)
        for value in (consistency, confirmation, qualification)
    ):
        raise ValueError("completed Dries probe evidence is missing")
    if (
        probe_request.get("status") != "CONSUMED"
        or probe_request.get("request_ready") is not False
        or probe_request.get("authorized") is not False
        or probe_review.get("status") != "PASS"
        or probe_review.get("reviewed_decision") != "DEC-022"
        or consistency.get("teacher_deck_multiset_sha256") != EXPECTED["deck"]
        or consistency.get("teacher_archetype_context_label")
        != "Marnie's Grimmsnarl ex"
        or consistency.get("module_versions") != ["1.32.2"]
        or consistency.get("combined_teacher_active_selection_requests") != 27
        or qualification.get("second_independent_recent_teacher_qualified")
        is not True
        or confirmation.get("observed_recent_teacher_episodes") != 54
        or confirmation.get("observed_recent_teacher_decisions") != 6_367
        or confirmation.get("confirmation_gate_passed") is not False
    ):
        raise ValueError("completed Dries probe differs")
    flg_data = flg_screening.get("screening")
    if not isinstance(flg_data, Mapping) or (
        flg_data.get("combined_observed_teacher_decisions") != 6_340
        or flg_data.get("qualified_files") != 38
        or flg_data.get("minimum_5000_teacher_decisions_met") is not True
    ):
        raise ValueError("completed flg screening differs")

    episodes = request.get("episodes")
    selection = metadata.get("selection")
    source = metadata.get("source")
    teacher = request.get("teacher")
    boundary = request.get("review_boundary")
    selection_basis = request.get("selection_basis")
    if not all(
        isinstance(value, Mapping)
        for value in (selection, source, teacher, boundary, selection_basis)
    ):
        raise ValueError("calibration bindings are missing")
    if not isinstance(episodes, list) or len(episodes) != 12:
        raise ValueError("calibration must contain 12 episodes")
    if episodes != selection.get("episodes"):
        raise ValueError("request episodes differ from candidate metadata")
    strata = Counter(item.get("stratum") for item in episodes)
    expected_strata = Counter(
        {"seat_0_loss": 3, "seat_0_win": 3, "seat_1_loss": 3, "seat_1_win": 3}
    )
    if strata != expected_strata:
        raise ValueError("calibration strata differ")
    if len({item.get("episode_id") for item in episodes}) != 12:
        raise ValueError("calibration episode IDs are duplicated")
    if any(item.get("episode_id") in {88_281_294, 88_332_011} for item in episodes):
        raise ValueError("probe episode is repeated in calibration")
    if sum(int(item["declared_bytes"]) for item in episodes) != 60_869_451:
        raise ValueError("calibration byte total differs")
    if [item.get("episode_id") for item in episodes] != [
        88_282_349,
        88_309_616,
        88_278_502,
        88_325_741,
        88_323_126,
        88_295_625,
        88_278_632,
        88_299_587,
        88_324_713,
        88_325_214,
        88_314_806,
        88_323_660,
    ]:
        raise ValueError("calibration episode order differs")
    if (
        source.get("submission_episodes_returned") != 454
        or source.get("dataset_inventory_files") != 4_554
        or source.get("dataset_intersection_episodes") != 128
        or source.get("excluded_probe_episode_ids") != [88_281_294, 88_332_011]
    ):
        raise ValueError("calibration source metadata differs")
    if (
        request.get("decision_id") != "DEC-023"
        or request.get("status") != "READY_UNAUTHORIZED"
        or request.get("request_ready") is not True
        or request.get("authorized") is not False
        or request.get("authorization_scope") is not None
        or request.get("approval") is not None
        or request.get("execution") is not None
        or request.get("maximum_new_files") != 12
        or request.get("maximum_new_bytes") != 60_869_451
        or request.get("overwrite_authorized") is not False
        or request.get("output_directory")
        != "private/g3/e01/dries-grimmsnarl-calibration-v1"
        or teacher.get("team_id") != 16_531_269
        or teacher.get("team_name") != "Dries @ Tufa Labs"
        or teacher.get("submission_id") != 55_002_825
        or teacher.get("live_rank_at_refresh") != 1
        or teacher.get("submission_public_score") != 1205.2
        or teacher.get("dataset_episode_count") != 128
        or teacher.get("expected_deck_multiset_sha256") != EXPECTED["deck"]
        or teacher.get("archetype_context_label") != "Marnie's Grimmsnarl ex"
    ):
        raise ValueError("calibration request contract differs")
    if (
        selection_basis.get("method")
        != "20th_50th_80th_file_byte_quantiles_per_seat_result_stratum"
        or selection_basis.get("quantiles") != [0.2, 0.5, 0.8]
        or selection_basis.get("balanced_strata") != dict(expected_strata)
        or selection_basis.get("replay_bodies_used_for_selection") is not False
        or selection_basis.get("metadata_can_guarantee_module_version") is not False
        or selection_basis.get("metadata_can_guarantee_exact_deck") is not False
        or selection_basis.get("metadata_can_guarantee_action_alignment") is not False
    ):
        raise ValueError("calibration selection basis differs")
    if (
        boundary.get("require_schema_version") != 1
        or boundary.get("require_environment_name") != "cabt"
        or boundary.get("require_environment_version") != "1.0.0"
        or boundary.get("require_module_version") != "1.32.2"
        or boundary.get("require_submission_binding") is not True
        or boundary.get("require_exact_deck_hash") != EXPECTED["deck"]
        or boundary.get("require_current_asset_deck_construction_checks")
        is not True
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
            raise ValueError(f"request authorization must remain false: {key}")
    if (ROOT / str(request["output_directory"])).exists():
        raise ValueError("calibration output directory already exists")

    report: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e01-dries-grimmsnarl-calibration-contract-review-v1",
        "created_at_utc": request.get("created_at_utc"),
        "source_path": "reports/artifacts/e01-dries-grimmsnarl-calibration-contract-review-v1.json",
        "producer": "scripts/e01_dries_grimmsnarl_calibration_contract_review.py",
        "reviewed_decision": "DEC-023",
        "status": "PASS",
        "decision": "ACCEPT_EXACT_12_FILE_CURRENT_RANK_1_DRIES_GRIMMSNARL_CALIBRATION_REQUEST_UNAUTHORIZED",
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
            "completed_probe_request": {
                "path": str(PROBE_REQUEST_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["probe_request"],
            },
            "completed_probe_review": {
                "path": str(PROBE_REVIEW_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["probe_review"],
                "review_sha256": EXPECTED["probe_review_self"],
            },
            "live_confirmation_refresh": {
                "path": str(LIVE_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["live"],
            },
            "completed_flg_screening": {
                "path": str(FLG_SCREENING_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["flg_screening"],
                "review_sha256": EXPECTED["flg_screening_self"],
            },
        },
        "request": {
            "request_ready": True,
            "authorized": False,
            "maximum_new_files": 12,
            "maximum_new_bytes": 60_869_451,
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
        "confirmation": {
            "independent_recent_teacher_requirement_met": True,
            "observed_recent_teacher_episodes": 54,
            "episode_shortfall": 146,
            "observed_recent_teacher_decisions": 6_367,
            "decision_shortfall": 18_633,
            "confirmation_gate_passed": False,
        },
        "qualification": {
            "completed_flg_screening_qualified": True,
            "current_rank_1_dries_probe_qualified": True,
            "second_independent_recent_teacher_qualified": True,
            "exact_grimmsnarl_deck_qualified": True,
            "current_rank_1_calibration_request_ready": True,
            "minimum_200_recent_teacher_episodes_met": False,
            "minimum_25000_meaningful_teacher_decisions_met": False,
            "confirmation_gate_passed": False,
            "replay_transfer_authorized": False,
            "training_authorized": False,
        },
        "next_action": "REQUEST_EXPLICIT_APPROVAL_FOR_EXACT_12_FILE_DRIES_GRIMMSNARL_CALIBRATION",
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
