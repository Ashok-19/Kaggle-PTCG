from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
DECISION_PATH = ROOT / "docs/decisions/DEC-019_E01_LIVE_GOLD_TEACHER_REFRESH.md"
SNAPSHOT_PATH = ROOT / "reports/artifacts/raw/e01-live-gold-refresh-v1.json"
REQUEST_PATH = ROOT / "configs/e01_flg_gold_teacher_probe_request_v1.json"
SUPERSEDED_REQUEST_PATH = ROOT / "configs/e01_luca_screening_expansion_request_v1.json"
OUTPUT_PATH = ROOT / "reports/artifacts/e01-flg-gold-teacher-contract-review-v1.json"

EXPECTED = {
    "decision": "111fcc2e740d27aa718ead66be186c82f4f282103f2623441010e604b0a99b5c",
    "snapshot": "410b137a7ed4052111d6e16c373fbdc1b1ae484de4ad152a06420981c0870120",
    "request": "98eeb79dcf23d62d57ddc80f0a9a793cc2e27d0c14dbbb22fdd66c6e2107edb0",
    "superseded_request": "c293268607ce0fc8762d543508bf2c798087ca9583cec05e3031a1906fc26962",
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
        (SNAPSHOT_PATH, EXPECTED["snapshot"]),
        (REQUEST_PATH, EXPECTED["request"]),
        (SUPERSEDED_REQUEST_PATH, EXPECTED["superseded_request"]),
    ):
        require_hash(path, expected)

    snapshot = load_json(SNAPSHOT_PATH)
    request = load_json(REQUEST_PATH)
    superseded = load_json(SUPERSEDED_REQUEST_PATH)
    selection = snapshot.get("selection")
    if not isinstance(selection, Mapping):
        raise ValueError("live selection is missing")
    episodes = request.get("episodes")
    if not isinstance(episodes, list) or len(episodes) != 2:
        raise ValueError("request must contain exactly two episodes")

    if (
        snapshot.get("record_id") != "e01-live-gold-refresh-v1"
        or selection.get("teacher_live_rank") != 1
        or selection.get("teacher_team_id") != 16_380_946
        or selection.get("teacher_team_name") != "flg"
        or selection.get("teacher_submission_id") != 55_004_495
        or selection.get("teacher_submission_public_score") != 1244.2
        or selection.get("selected_total_bytes") != 3_996_398
    ):
        raise ValueError("live rank-1 teacher selection differs")
    if [item.get("episode_id") for item in episodes] != [88_302_734, 88_333_037]:
        raise ValueError("selected episode identities differ")
    if [item.get("declared_bytes") for item in episodes] != [624_407, 3_371_991]:
        raise ValueError("selected file sizes differ")
    if [item.get("teacher_player_index") for item in episodes] != [1, 0]:
        raise ValueError("selected teacher seats differ")
    if [item.get("teacher_reward") for item in episodes] != [-1, 1]:
        raise ValueError("selected teacher outcomes differ")
    if sum(int(item["declared_bytes"]) for item in episodes) != 3_996_398:
        raise ValueError("request byte total differs")

    teacher = request.get("teacher")
    boundary = request.get("inspection_boundary")
    dataset = request.get("dataset")
    if not all(isinstance(value, Mapping) for value in (teacher, boundary, dataset)):
        raise ValueError("request bindings are missing")
    if (
        request.get("decision_id") != "DEC-019"
        or request.get("status") != "READY_UNAUTHORIZED"
        or request.get("request_ready") is not True
        or request.get("authorized") is not False
        or request.get("authorization_scope") is not None
        or request.get("maximum_new_files") != 2
        or request.get("maximum_new_bytes") != 3_996_398
        or request.get("overwrite_authorized") is not False
        or request.get("output_directory")
        != "private/g3/e01/flg-gold-teacher-probe-v1"
        or dataset
        != {
            "owner_slug": "kaggle",
            "dataset_slug": "pokemon-tcg-ai-battle-episodes-2026-07-26",
            "version": 1,
        }
        or teacher.get("submission_id") != 55_004_495
        or teacher.get("team_id") != 16_380_946
        or teacher.get("team_name") != "flg"
        or teacher.get("live_rank_at_refresh") != 1
        or teacher.get("submission_public_score") != 1244.2
        or teacher.get("dataset_episode_count") != 131
    ):
        raise ValueError("request teacher or transfer contract differs")

    required_true = (
        "require_exact_declared_bytes",
        "require_exact_file_sha256",
        "require_submission_binding",
        "require_same_module_version_across_files",
        "require_exact_deck_match_across_files",
        "require_current_asset_deck_construction_checks",
        "require_aggregate_action_alignment",
        "measure_teacher_decisions",
    )
    if any(boundary.get(key) is not True for key in required_true):
        raise ValueError("required review boundary differs")
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

    if (
        superseded.get("decision_id") != "DEC-018"
        or superseded.get("status") != "READY_UNAUTHORIZED"
        or superseded.get("request_ready") is not True
        or superseded.get("authorized") is not False
        or (ROOT / str(superseded.get("output_directory"))).exists()
    ):
        raise ValueError("DEC-018 is not safely superseded and unexecuted")
    if (ROOT / str(request["output_directory"])).exists():
        raise ValueError("rank-1 probe output directory already exists")

    report: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e01-flg-gold-teacher-contract-review-v1",
        "created_at_utc": request.get("created_at_utc"),
        "source_path": "reports/artifacts/e01-flg-gold-teacher-contract-review-v1.json",
        "producer": "scripts/e01_flg_teacher_contract_review.py",
        "reviewed_decision": "DEC-019",
        "status": "PASS",
        "decision": "ACCEPT_EXACT_TWO_FILE_CURRENT_RANK_1_TEACHER_REQUEST_UNAUTHORIZED",
        "inputs": {
            "decision": {"path": str(DECISION_PATH.relative_to(ROOT)), "sha256": EXPECTED["decision"]},
            "live_refresh": {"path": str(SNAPSHOT_PATH.relative_to(ROOT)), "sha256": EXPECTED["snapshot"]},
            "request": {"path": str(REQUEST_PATH.relative_to(ROOT)), "sha256": EXPECTED["request"]},
            "superseded_request": {"path": str(SUPERSEDED_REQUEST_PATH.relative_to(ROOT)), "sha256": EXPECTED["superseded_request"]},
        },
        "teacher": {
            "team_id": 16_380_946,
            "team_name": "flg",
            "submission_id": 55_004_495,
            "live_rank_at_refresh": 1,
            "live_team_score_at_refresh": teacher.get("live_team_score_at_refresh"),
            "submission_public_score": 1244.2,
            "dataset_episode_count": 131,
        },
        "request": {
            "request_ready": True,
            "authorized": False,
            "maximum_new_files": 2,
            "maximum_new_bytes": 3_996_398,
            "episode_ids": [88_302_734, 88_333_037],
            "opposite_teacher_seats": True,
            "opposite_teacher_results": True,
            "output_directory_exists": False,
            "superseded_luca_request_executed": False,
            "agent_logs_authorized": False,
            "additional_replays_authorized": False,
            "raw_exports_authorized": False,
            "training_authorized": False,
            "external_compute_authorized": False,
            "submission_authorized": False,
        },
        "qualification": {
            "live_leaderboard_refreshed": True,
            "current_rank_1_teacher_selected": True,
            "current_daily_dataset_coverage_available": True,
            "rank_1_probe_request_ready": True,
            "replay_transfer_authorized": False,
            "training_authorized": False,
            "e01_screening_gate_passed": False,
        },
        "next_action": "EXECUTE_EXACT_TWO_FILE_FLG_PROBE_UNDER_CURRENT_USER_APPROVAL",
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
