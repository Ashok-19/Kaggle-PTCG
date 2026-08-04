from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
DECISION_PATH = ROOT / "docs/decisions/DEC-024_E01_CURRENT_RANK_1_SOURCE_WAIT.md"
CALIBRATION_REQUEST_PATH = ROOT / "configs/e01_dries_grimmsnarl_calibration_request_v1.json"
CALIBRATION_REVIEW_PATH = (
    ROOT / "reports/artifacts/e01-dries-grimmsnarl-calibration-review-v1.json"
)
LIVE_REFRESH_PATH = ROOT / "reports/artifacts/raw/e01-live-confirmation-refresh-v2.json"
OUTPUT_PATH = ROOT / "reports/artifacts/e01-live-confirmation-source-wait-review-v1.json"
HAGGLE_REQUEST_PATH = ROOT / "configs/e01_haggle_confirmation_teacher_probe_request_v1.json"
HAGGLE_OUTPUT_PATH = ROOT / "private/g3/e01/haggle-confirmation-teacher-probe-v1"

EXPECTED = {
    "decision": "19bcd93ad39eddeedd4b7b32a81d503794f77bfea63cb57252da2d832086f2ce",
    "calibration_request": "f026a350d9e5c882080f28f60a811d3060f49c7a3c7375dc85e550865d4f9380",
    "calibration_authorized_payload": "75bc96fe9f5ab595f1443716a96f47c67843687b32f6d55616b05f9a59c8945d",
    "calibration_review": "e2b0437f0cf43ebd1c1a1059714d7d435de5c25f95704e6f0aab423a114a8e45",
    "calibration_review_self": "56e7f1d065c0eaf5132bcac710f903ca4bfab236638d5a7d5b62bddd7ea2a871",
    "live_refresh": "ac8e0a72b9d49a44d1f587929664a444b673866ae677f74f030555e1af889b92",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
        (CALIBRATION_REQUEST_PATH, EXPECTED["calibration_request"]),
        (CALIBRATION_REVIEW_PATH, EXPECTED["calibration_review"]),
        (LIVE_REFRESH_PATH, EXPECTED["live_refresh"]),
    ):
        require_hash(path, expected)

    request = load_json(CALIBRATION_REQUEST_PATH)
    calibration = load_json(CALIBRATION_REVIEW_PATH)
    refresh = load_json(LIVE_REFRESH_PATH)

    approval = request.get("approval")
    execution = request.get("execution")
    if not isinstance(approval, Mapping) or not isinstance(execution, Mapping):
        raise ValueError("calibration approval or execution record is missing")
    if (
        request.get("status") != "CONSUMED"
        or request.get("request_ready") is not False
        or request.get("authorized") is not False
        or request.get("authorization_scope")
        != "CONSUMED_EXACT_12_FILE_DRIES_GRIMMSNARL_CALIBRATION_ONLY"
        or approval.get("authorized_request_sha256")
        != EXPECTED["calibration_authorized_payload"]
        or execution.get("files_downloaded") != 12
        or execution.get("bytes_downloaded") != 60_869_451
    ):
        raise ValueError("completed DEC-023 request differs")
    if calibration.get("review_sha256") != EXPECTED["calibration_review_self"]:
        raise ValueError("DEC-023 calibration review self hash differs")
    confirmation = calibration.get("confirmation")
    consistency = calibration.get("consistency")
    qualification = calibration.get("qualification")
    if not all(
        isinstance(value, Mapping)
        for value in (confirmation, consistency, qualification)
    ):
        raise ValueError("DEC-023 calibration aggregates are missing")
    if (
        calibration.get("status") != "PASS"
        or calibration.get("reviewed_decision") != "DEC-023"
        or calibration.get("decision")
        != "ACCEPT_DRIES_GRIMMSNARL_CALIBRATION_CONFIRMATION_FLOOR_BLOCKED"
        or confirmation.get("observed_independent_recent_teachers") != 2
        or confirmation.get("observed_recent_teacher_episodes") != 66
        or confirmation.get("observed_recent_teacher_decisions") != 7_542
        or confirmation.get("episode_shortfall") != 134
        or confirmation.get("decision_shortfall") != 17_458
        or confirmation.get("confirmation_gate_passed") is not False
        or consistency.get("calibration_teacher_active_selection_requests") != 1_175
        or consistency.get("combined_all_player_active_selection_requests") != 2_171
        or consistency.get("all_same_module_version") is not True
        or consistency.get("exact_teacher_deck_match") is not True
        or consistency.get("all_replay_action_alignment") != "PASS"
        or qualification.get("training_authorized") is not False
    ):
        raise ValueError("DEC-023 calibration result differs")

    rank_1 = refresh.get("current_rank_1")
    prior_dries = refresh.get("prior_dries_teacher")
    dataset = refresh.get("latest_complete_daily_dataset")
    intersection = refresh.get("current_rank_1_dataset_intersection")
    boundary = refresh.get("source_boundary")
    if not all(
        isinstance(value, Mapping)
        for value in (rank_1, prior_dries, dataset, intersection, boundary)
    ):
        raise ValueError("live refresh sections are missing")
    active_submission = rank_1.get("active_submission")
    if not isinstance(active_submission, Mapping):
        raise ValueError("current rank-1 active submission is missing")
    if (
        refresh.get("record_id") != "e01-live-confirmation-refresh-v2"
        or rank_1.get("team_id") != 16_441_077
        or rank_1.get("team_name") != "haggle"
        or rank_1.get("rank") != 1
        or rank_1.get("score") != 1169.5
        or active_submission.get("submission_id") != 55_104_355
        or active_submission.get("public_score") != 1169.5
        or rank_1.get("public_episode_count") != 76
        or rank_1.get("public_episode_strata")
        != {"seat_0_loss": 10, "seat_0_win": 26, "seat_1_loss": 14, "seat_1_win": 26}
        or prior_dries.get("qualified_submission_id") != 55_002_825
        or prior_dries.get("current_top20_rank") is not None
        or prior_dries.get("active_submission_changed") is not True
        or prior_dries.get("completed_evidence_remains_exact_submission_bound")
        is not True
        or dataset.get("versioned_ref")
        != "kaggle/pokemon-tcg-ai-battle-episodes-2026-07-29/1"
        or dataset.get("json_files") != 4_387
        or dataset.get("declared_json_bytes") != 21_474_480_425
        or dataset.get("inventory_sha256")
        != "60c3a6caf58e0df5c33d2b27d2a3ccb76ffb2e72fb3c5b6b27918fec979577ed"
        or intersection.get("episodes") != 0
        or intersection.get("total_bytes") != 0
        or intersection.get("files") != []
        or intersection.get("replay_bodies_used") is not False
        or boundary.get("current_rank_1_probe_request_ready") is not False
        or boundary.get("replay_transfer_authorized") is not False
        or boundary.get("training_authorized") is not False
        or refresh.get("next_action")
        != "WAIT_FOR_DAILY_DATASET_CONTAINING_CURRENT_RANK_1_SUBMISSION_55104355"
    ):
        raise ValueError("live source-wait evidence differs")
    if HAGGLE_REQUEST_PATH.exists():
        raise ValueError("a current-rank-1 request was created despite zero source intersection")
    if HAGGLE_OUTPUT_PATH.exists():
        raise ValueError("a current-rank-1 output directory exists despite zero authorization")

    report: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e01-live-confirmation-source-wait-review-v1",
        "created_at_utc": refresh.get("created_at_utc"),
        "source_path": "reports/artifacts/e01-live-confirmation-source-wait-review-v1.json",
        "producer": "scripts/e01_live_confirmation_source_wait_review.py",
        "reviewed_decision": "DEC-024",
        "status": "PASS",
        "decision": "ACCEPT_CURRENT_RANK_1_SOURCE_WAIT_NO_REPLAY_REQUEST",
        "inputs": {
            "decision": {
                "path": str(DECISION_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["decision"],
            },
            "completed_calibration_request": {
                "path": str(CALIBRATION_REQUEST_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["calibration_request"],
                "authorized_request_sha256": EXPECTED[
                    "calibration_authorized_payload"
                ],
                "authorization_consumed": True,
            },
            "completed_calibration_review": {
                "path": str(CALIBRATION_REVIEW_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["calibration_review"],
                "review_sha256": EXPECTED["calibration_review_self"],
            },
            "live_refresh": {
                "path": str(LIVE_REFRESH_PATH.relative_to(ROOT)),
                "sha256": EXPECTED["live_refresh"],
            },
        },
        "confirmation": {
            "observed_independent_recent_teachers": 2,
            "observed_recent_teacher_episodes": 66,
            "observed_recent_teacher_decisions": 7_542,
            "episode_shortfall": 134,
            "decision_shortfall": 17_458,
            "confirmation_gate_passed": False,
        },
        "current_rank_1": {
            "team_id": 16_441_077,
            "team_name": "haggle",
            "rank": 1,
            "score": 1169.5,
            "submission_id": 55_104_355,
            "public_episode_count": 76,
            "latest_complete_daily_dataset": (
                "kaggle/pokemon-tcg-ai-battle-episodes-2026-07-29/1"
            ),
            "dataset_intersection_files": 0,
            "dataset_intersection_bytes": 0,
        },
        "source_wait": {
            "current_rank_1_probe_request_ready": False,
            "current_rank_1_probe_request_exists": False,
            "current_rank_1_output_exists": False,
            "replay_transfer_authorized": False,
            "agent_logs_authorized": False,
            "raw_exports_authorized": False,
            "training_authorized": False,
            "external_compute_authorized": False,
            "submission_authorized": False,
        },
        "qualification": {
            "dec_023_calibration_qualified": True,
            "two_independent_recent_teachers_qualified": True,
            "minimum_200_recent_teacher_episodes_met": False,
            "minimum_25000_meaningful_teacher_decisions_met": False,
            "confirmation_gate_passed": False,
            "current_rank_1_source_ready": False,
            "replay_transfer_authorized": False,
            "training_authorized": False,
        },
        "next_action": (
            "REFRESH_AFTER_PINNED_DAILY_DATASET_CONTAINS_SUBMISSION_55104355"
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
