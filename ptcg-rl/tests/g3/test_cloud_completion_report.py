from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports/evaluations/g3a-cloud-correctness-v1.json"
REVIEW = ROOT / "reports/artifacts/raw/g3a-cloud-correctness-review-v1.json"


def load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_verified_g3a_cloud_completion_closes_only_algorithm_correctness() -> None:
    report = load(REPORT)
    assert report["status"] == "SUCCEEDED"
    assert report["decision"] == "PASS"
    assert report["identity"]["saved_version_number"] == 2
    assert report["identity"]["script_version_id"] == 337365875
    assert report["identity"]["source_commit"] == "6b7975bf518c36ff59338b6793ec52530c73f173"
    assert report["input"]["dataset_version"] == 3
    assert report["results"]["stream_count"] == 12
    assert report["results"]["exact_budget_complete"] is True
    assert report["results"]["all_task_failed_cases"] == 0
    assert report["results"]["recurrent_scores"] == [1.0, 1.0, 1.0]
    assert report["results"]["stateless_control_scores"] == [0.5, 0.5, 0.5]
    assert report["results"]["recurrent_margins"] == [0.5, 0.5, 0.5]
    assert report["results"]["zero_tolerance_total"] == 0
    assert report["results"]["fresh_process_resume_count"] == 3
    manifest = report["artifacts"]["output_manifest"]
    assert manifest["declared_file_count"] == 220
    assert manifest["declared_total_bytes"] == 20_617_497
    assert manifest["missing_file_count"] == 0
    assert manifest["extra_file_count"] == 0
    assert manifest["byte_or_sha256_mismatch_count"] == 0
    assert report["artifacts"]["checkpoint_manifest"]["checkpoint_payload_count"] == 84
    assert report["artifacts"]["checkpoint_manifest"]["checkpoint_sidecar_count"] == 84
    assert report["artifacts"]["stderr_files_empty"] is True
    review_raw = REVIEW.read_bytes()
    assert len(review_raw) == 1008
    assert hashlib.sha256(review_raw).hexdigest() == "abc8dcd3db3489a968840d98fc4450d3164c699473a3336e7625c7295ea8565b"
    review = json.loads(review_raw)
    assert review["decision"] == "PASS"
    assert review["failures"] == []
    assert report["claim"] == {
        "algorithm_proof_only": True,
        "policy_strength_established": False,
        "g3b_promotion_automatic": False,
    }
    gate = load(ROOT / "reports/gates/g3a.json")
    assert gate["status"] == "SUCCEEDED"
    assert gate["decision"] == "PASS"
    assert gate["blockers"] == []
    tasks = load(ROOT / "reports/tasks/current.json")
    task = next(item for item in tasks if item.get("task_id") == "T-G3-001")
    assert task["status"] == "SUCCEEDED"
    assert task["completion_evidence_sha256"] == hashlib.sha256(REPORT.read_bytes()).hexdigest()
    assert task["script_version_id"] == 337365875
    assert task["manifest_mismatch_count"] == 0
    assert task["strict_review_status"] == "PASS"
    assert task["assistant_launch_performed"] is False
