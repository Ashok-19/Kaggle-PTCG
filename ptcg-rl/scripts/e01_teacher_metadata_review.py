from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
DRY_RUN = ROOT / "reports/artifacts/e01a-public-replay-dry-run-v1.json"
SNAPSHOT = ROOT / "reports/artifacts/raw/e01-public-manifest-metadata-v1.json"
DECISION = ROOT / "docs/decisions/DEC-013_E01_PROVENANCE_PROBE.md"
REQUEST = ROOT / "configs/e01_provenance_probe_request_v1.json"
OUTPUT = ROOT / "reports/artifacts/e01-teacher-deck-metadata-review-v1.json"

class E01MetadataReviewError(ValueError):
    pass

def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise E01MetadataReviewError(f"JSON root must be an object: {path}")
    return value

def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")

def self_hash(value: Mapping[str, Any], field: str) -> str:
    payload = dict(value)
    payload.pop(field, None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()

def atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)

def review() -> dict[str, Any]:
    dry_run = load_json(DRY_RUN)
    snapshot = load_json(SNAPSHOT)
    request = load_json(REQUEST)
    decision_text = DECISION.read_text(encoding="utf-8")
    if dry_run.get("status") != "DRY_RUN_PASS_TRANSFER_BLOCKED" or dry_run.get("episode_json_transferred") != 0:
        raise E01MetadataReviewError("accepted dry run boundary differs")
    daily = dry_run.get("daily_source")
    current = snapshot.get("dataset")
    if not isinstance(daily, Mapping) or not isinstance(current, Mapping):
        raise E01MetadataReviewError("manifest source records are invalid")
    accepted_columns = ["episode_id", "create_time", "avg_score", "min_score", "sum_score", "agent_count", "size_bytes"]
    current_columns = current.get("manifest_columns")
    if current_columns == accepted_columns:
        raise E01MetadataReviewError("expected manifest schema mismatch is absent")
    if (
        daily.get("dataset_owner") != current.get("owner_slug")
        or daily.get("dataset_slug") != current.get("dataset_slug")
        or daily.get("dataset_version") != current.get("version")
        or daily.get("manifest_filename") != current.get("manifest_name")
    ):
        raise E01MetadataReviewError("comparison does not address the same declared dataset object")
    if daily.get("manifest_sha256") == current.get("manifest_sha256") or daily.get("manifest_bytes") == current.get("manifest_bytes"):
        raise E01MetadataReviewError("expected daily manifest object mismatch is absent")
    accepted = {int(item["episode_id"]): item for item in dry_run.get("selected_items", [])}
    observed = {int(item["id"]): item for item in snapshot.get("selected_rows", [])}
    if set(accepted) != set(observed) or len(accepted) != 8:
        raise E01MetadataReviewError("selected episode identity set differs")
    mismatches = []
    for episode_id in sorted(accepted):
        old, new = accepted[episode_id], observed[episode_id]
        mismatch = {
            "episode_id": episode_id,
            "accepted_file_name": old["remote_filename"],
            "current_file_name": new["file_name"],
            "accepted_declared_bytes": old["declared_bytes"],
            "current_manifest_data_size": new["data_size"],
            "accepted_create_time": old["create_time"],
            "current_create_time": new["create_time"],
            "byte_count_matches": old["declared_bytes"] == new["data_size"],
            "create_time_matches": old["create_time"] == new["create_time"],
        }
        mismatches.append(mismatch)
    if any(item["byte_count_matches"] or item["create_time_matches"] for item in mismatches):
        raise E01MetadataReviewError("expected selected-row mismatch is incomplete")
    if (
        request.get("status") != "BLOCKED_SOURCE_MANIFEST_CONTRACT_UNRESOLVED"
        or request.get("request_ready") is not False
        or request.get("authorized") is not False
        or request.get("episode_id") is not None
        or request.get("file_name") is not None
        or request.get("declared_bytes") is not None
        or request.get("maximum_files") != 0
        or request.get("maximum_total_bytes") != 0
        or request.get("output_directory") is not None
    ):
        raise E01MetadataReviewError("probe placeholder is not fail-closed")
    boundary = request.get("inspection_boundary")
    if not isinstance(boundary, Mapping) or any(value not in (0, False) for value in boundary.values()):
        raise E01MetadataReviewError("probe placeholder authorizes activity")
    for text in ("Status: Accepted", "block every replay-body transfer", "does **not** authorize any replay body"):
        if text not in decision_text:
            raise E01MetadataReviewError(f"DEC-013 missing required text: {text}")
    report: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e01-teacher-deck-metadata-review-v1",
        "created_at_utc": "2026-07-24T14:52:18Z",
        "source_path": "reports/artifacts/e01-teacher-deck-metadata-review-v1.json",
        "producer": "scripts/e01_teacher_metadata_review.py",
        "status": "PASS",
        "decision": "BLOCK_E01_SOURCE_MANIFEST_CONTRACT_UNRESOLVED",
        "reviewed_decision": "DEC-013",
        "inputs": {
            "dry_run": {"path": DRY_RUN.relative_to(ROOT).as_posix(), "sha256": sha256_file(DRY_RUN)},
            "current_manifest_snapshot": {"path": SNAPSHOT.relative_to(ROOT).as_posix(), "sha256": sha256_file(SNAPSHOT)},
            "decision": {"path": DECISION.relative_to(ROOT).as_posix(), "sha256": sha256_file(DECISION)},
            "probe_placeholder": {"path": REQUEST.relative_to(ROOT).as_posix(), "sha256": sha256_file(REQUEST)},
        },
        "manifest_comparison": {
            "same_declared_owner_slug_version_and_filename": True,
            "accepted_manifest_bytes": daily["manifest_bytes"],
            "accepted_manifest_sha256": daily["manifest_sha256"],
            "current_manifest_bytes": current["manifest_bytes"],
            "current_manifest_sha256": current["manifest_sha256"],
            "accepted_columns": accepted_columns,
            "current_columns": current_columns,
            "manifest_object_matches": False,
            "schema_matches": False,
            "selected_episode_ids_match": True,
            "selected_row_mismatches": mismatches,
        },
        "qualification": {
            "source_provenance_qualified": False,
            "teacher_qualified": False,
            "deck_qualified": False,
            "policy_consistency_qualified": False,
            "e01_screening_gate_passed": False,
            "named_replay_transfer_authorized": False,
        },
        "probe": {
            "request_ready": False,
            "request_authorized": False,
            "files_authorized": 0,
            "bytes_authorized": 0,
            "agent_logs_authorized": False,
            "training_authorized": False,
            "external_compute_authorized": False,
        },
        "next_action": "RECERTIFY_DAILY_MANIFEST_SOURCE_AND_SCHEMA_BEFORE_ANY_REPLAY_TRANSFER",
        "cost_usd": 0.0,
    }
    report["review_sha256"] = self_hash(report, "review_sha256")
    atomic_json(OUTPUT, report)
    return report

def main() -> int:
    print(json.dumps(review(), indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
