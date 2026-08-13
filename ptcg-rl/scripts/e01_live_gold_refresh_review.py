from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOW = "2026-08-04T10:40:05Z"


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def file_sha(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def obj_hash(value: dict, field: str) -> str:
    payload = copy.deepcopy(value)
    payload.pop(field, None)
    encoded = (
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def write(path: str, value: dict) -> None:
    value["review_sha256"] = obj_hash(value, "review_sha256")
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


live = load("reports/artifacts/raw/e01-live-gold-refresh-20260804-v1.json")
assert live["evidence_sha256"] == obj_hash(live, "evidence_sha256")
latest = live["latest_leaderboard_snapshot"]
assert latest["fetched_at_utc"] == NOW
assert latest["scores_are_dynamic_snapshot_only"] is True
assert latest["top_five"][0]["team_id"] == 16_374_395
assert latest["top_five"][0]["active_submission_id"] == 55_186_239
assert live["daily_dataset"]["source_ready_json_files"] == 4_720
assert live["daily_dataset"]["manifest_rows"] == 4_724
assert live["daily_dataset"]["manifest_rows_without_json_body"] == 4

request = load("configs/e01_majkel_live_gold_teacher_probe_request_v1.json")
selection = live["smallest_balanced_winning_probe"]
assert request["authorized"] is False
assert request["request_ready"] is True
assert [item["episode_id"] for item in request["selection"]["episodes"]] == selection[
    "episode_ids"
]
assert request["selection"]["maximum_new_bytes"] == selection["total_bytes"] == 832_877
assert request["selection"]["selection_mode"] == "win"
assert request["source"]["leaderboard_snapshot"]["score_is_authorization_basis"] is False
assert request["source"]["available_json_file_count"] == 4_720
assert request["source"]["manifest_rows_without_json_body"] == 4
assert not (ROOT / request["output_directory"]).exists()

replay_review = {
    "schema_version": 1,
    "record_id": "e01-majkel-live-gold-teacher-contract-review-v1",
    "source_path": "reports/artifacts/e01-majkel-live-gold-teacher-contract-review-v1.json",
    "created_at_utc": NOW,
    "producer": "scripts/e01_live_gold_refresh_review.py",
    "reviewed_decision": "DEC-025",
    "status": "PASS",
    "decision": "ACCEPT_EXACT_TWO_FILE_MAJKEL_CURRENT_RANK_1_PROBE_REQUEST_UNAUTHORIZED",
    "review_sha256": None,
    "inputs": {
        "live_refresh": {
            "path": live["source_path"],
            "sha256": file_sha(live["source_path"]),
            "evidence_sha256": live["evidence_sha256"],
        },
        "request": {
            "path": request["source_path"],
            "sha256": file_sha(request["source_path"]),
        },
    },
    "request": {
        "request_ready": True,
        "authorized": False,
        "selected_episode_ids": selection["episode_ids"],
        "maximum_new_files": 2,
        "maximum_new_bytes": 832_877,
        "opposite_teacher_seats": True,
        "both_teacher_wins": True,
        "output_directory_exists": False,
        "replay_transfer_authorized": False,
        "agent_logs_authorized": False,
        "raw_exports_authorized": False,
        "training_authorized": False,
        "external_compute_authorized": False,
        "submission_authorized": False,
    },
    "next_action": "REQUEST_SEPARATE_EXPLICIT_APPROVAL_FOR_THE_EXACT_TWO_NAMED_REPLAY_BODIES",
}
write(replay_review["source_path"], replay_review)

manifest = load("reports/artifacts/e01-approved-replay-corpus-manifest-v1.json")
recount = load("reports/artifacts/e01-approved-replay-policy-loss-recount-v1.json")
assert manifest["manifest_sha256"] == obj_hash(manifest, "manifest_sha256")
assert recount["coverage"]["episodes"] == 66
assert recount["coverage"]["teacher_active_requests"] == 7_542
assert recount["coverage"]["forced_teacher_requests"] == 402
assert recount["coverage"]["policy_loss_targets"] == 7_140
assert recount["coverage"]["recorded_active_request_mismatch_episodes"] == 0
assert recount["inputs"]["corpus_manifest"]["manifest_sha256"] == manifest[
    "manifest_sha256"
]
assert recount["inputs"]["corpus_manifest"]["sha256"] == file_sha(
    manifest["source_path"]
)

files = manifest["inventory"]["files"]
assert len(files) == 82
assert sum(item["bytes"] for item in files) == 453_143_981
assert len({item["episode_id"] for item in files}) == 82
assert len({item["sha256"] for item in files}) == 82
for item in files:
    replay_path = ROOT / item["path"]
    replay_bytes = replay_path.read_bytes()
    assert len(replay_bytes) == item["bytes"]
    assert hashlib.sha256(replay_bytes).hexdigest() == item["sha256"]

qualified = manifest["qualified_training_corpus"]["episode_records"]
assert len(qualified) == 66
assert sum(item["meaningful_teacher_decisions"] for item in qualified) == 7_140
assert sum(item["teacher_active_requests"] for item in qualified) == 7_542
assert sum(item["forced_teacher_requests"] for item in qualified) == 402
assert Counter(item["split"] for item in qualified) == Counter(
    {"train": 50, "validation": 8, "test": 8}
)
assert (
    sum(
        item["meaningful_teacher_decisions"]
        for item in qualified
        if item["split"] == "train"
    )
    == 5_653
)
assert (
    sum(
        item["meaningful_teacher_decisions"]
        for item in qualified
        if item["split"] == "validation"
    )
    == 734
)
assert (
    sum(
        item["meaningful_teacher_decisions"]
        for item in qualified
        if item["split"] == "test"
    )
    == 753
)

corpus_review = {
    "schema_version": 1,
    "record_id": "e01-approved-replay-corpus-review-v1",
    "source_path": "reports/artifacts/e01-approved-replay-corpus-review-v1.json",
    "created_at_utc": NOW,
    "producer": "scripts/e01_live_gold_refresh_review.py",
    "reviewed_decision": "DEC-025",
    "status": "PASS",
    "decision": "ACCEPT_IMMUTABLE_APPROVED_CORPUS_INVENTORY_AND_LEAKAGE_SAFE_EPISODE_SPLITS",
    "review_sha256": None,
    "inputs": {
        "manifest": {
            "path": manifest["source_path"],
            "sha256": file_sha(manifest["source_path"]),
            "manifest_sha256": manifest["manifest_sha256"],
        },
        "policy_loss_recount": {
            "path": recount["source_path"],
            "sha256": file_sha(recount["source_path"]),
            "review_sha256": recount["review_sha256"],
        },
    },
    "inventory": {
        "files": 82,
        "bytes": 453_143_981,
        "unique_episode_ids": 82,
        "unique_content_hashes": 82,
        "mismatches": 0,
    },
    "qualified_corpus": {
        "episodes": 66,
        "teacher_active_requests": 7_542,
        "forced_teacher_requests": 402,
        "meaningful_teacher_decisions": 7_140,
        "policy_loss_targets": 7_140,
        "split_counts": {"train": 50, "validation": 8, "test": 8},
        "split_decisions": {"train": 5_653, "validation": 734, "test": 753},
        "episode_level_leakage": 0,
    },
    "semantics": {
        "ordered_multi_selection": True,
        "stop_first_class": True,
        "legal_option_mask": True,
        "forced_recurrence_without_policy_loss": True,
        "lag_alignment": True,
    },
    "authorization": {
        "label_generation": False,
        "optimizer_steps": False,
        "external_compute": False,
        "production_training": False,
    },
}
write(corpus_review["source_path"], corpus_review)

canary_request = load("configs/e01_bc_engineering_canary_request_v1.json")
assert canary_request["authorized"] is False
assert canary_request["execution"]["maximum_optimizer_steps"] == 64
assert canary_request["execution"]["platform"] == "local_cpu_only"
assert canary_request["execution"]["external_compute"] is False
qualified_by_id = {item["episode_id"]: item for item in qualified}
assert len(canary_request["corpus"]["episodes"]) == 8
for item in canary_request["corpus"]["episodes"]:
    source = qualified_by_id[item["episode_id"]]
    assert source["split"] == "train"
    assert source["sha256"] == item["sha256"]
assert not (ROOT / canary_request["execution"]["checkpoint_output"]).exists()

canary_review = {
    "schema_version": 1,
    "record_id": "e01-bc-engineering-canary-contract-review-v1",
    "source_path": "reports/artifacts/e01-bc-engineering-canary-contract-review-v1.json",
    "created_at_utc": NOW,
    "producer": "scripts/e01_live_gold_refresh_review.py",
    "reviewed_decision": "DEC-025",
    "status": "PASS",
    "decision": "ACCEPT_EXACT_64_STEP_EIGHT_EPISODE_BC_ENGINEERING_CANARY_REQUEST_UNAUTHORIZED",
    "review_sha256": None,
    "inputs": {
        "corpus_manifest": {
            "path": manifest["source_path"],
            "manifest_sha256": manifest["manifest_sha256"],
        },
        "request": {
            "path": canary_request["source_path"],
            "sha256": file_sha(canary_request["source_path"]),
        },
    },
    "boundary": {
        "episodes": 8,
        "teachers": 2,
        "seat_result_strata_per_teacher": 4,
        "maximum_optimizer_steps": 64,
        "platform": "local_cpu_only",
        "external_compute": False,
        "checkpoint_output_exists": False,
        "production_checkpoint_eligible": False,
    },
    "qualification": {
        "implementation_preflight_required": True,
        "request_ready": True,
        "optimizer_steps_authorized": False,
        "production_training_authorized": False,
        "policy_competence_claimed": False,
    },
    "next_action": "REQUEST_SEPARATE_EXPLICIT_APPROVAL_FOR_THIS_EXACT_HASH_BOUND_64_STEP_LOCAL_CPU_CANARY",
}
write(canary_review["source_path"], canary_review)
print(
    json.dumps(
        {
            "replay_review": "PASS",
            "corpus_review": "PASS",
            "canary_review": "PASS",
        },
        sort_keys=True,
    )
)
