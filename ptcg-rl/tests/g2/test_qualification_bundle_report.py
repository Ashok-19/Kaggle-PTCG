from __future__ import annotations

import json
from pathlib import Path


BUNDLE_SHA256 = "56b4e93671609a8d24887480cbf1d0dfc0c38b60e1cad55d0cf95f4e50744506"
SOURCE_COMMIT = "c660f74b26fca74915931091ac0fe365f7f005f5"
PARITY_REPORT = "reports/evaluations/g2-policy-cpu-gpu-parity-v4.json"


def load(root: Path, relative: str):
    return json.loads((root / relative).read_text(encoding="utf-8"))


def test_current_source_bundle_report_is_sealed_and_no_training() -> None:
    root = Path(__file__).resolve().parents[2]
    report = load(root, "reports/artifacts/g2-policy-qualification-bundle-v4.json")

    assert report["status"] == "SUCCEEDED"
    assert report["source_commit"] == SOURCE_COMMIT
    assert report["bundle_sha256"] == BUNDLE_SHA256
    assert report["bundle_bytes"] == 67540
    assert report["manifest_sha256"] == (
        "827cf0f6ebb3f36676540280367e599bfd2e88312f070b3b0a8686d69f788ad1"
    )
    assert report["included_files"] == 11
    assert set(report["archive_validation"].values()) == {"PASS", 0}
    preflight = report["local_preflight"]
    assert preflight["status"] == "PASS"
    assert preflight["required_checks"] == 10
    assert preflight["all_checks"] is True
    assert preflight["selected_gradient_records"] == 7
    assert preflight["optimizer_created"] is False
    assert preflight["training_loop_ran"] is False
    assert report["kaggle_input"]["dataset_version"] == 3
    assert report["kaggle_input"]["external_model_ref"] is None
    assert report["authorization"] == {
        "numerical_qualification_only": True,
        "training_included": False,
        "optimizer_created": False,
        "kaggle_launch_performed": True,
    }


def test_gate_and_task_close_only_the_parity_slice() -> None:
    root = Path(__file__).resolve().parents[2]
    gate = load(root, "reports/gates/g2.json")
    tasks = load(root, "reports/tasks/current.json")

    checks = {item["name"]: item for item in gate["technical_checks"]}
    assert checks["latest-clean-source qualification bundle"] == {
        "name": "latest-clean-source qualification bundle",
        "status": "PASS",
        "evidence": "reports/artifacts/g2-policy-qualification-bundle-v4.json",
    }
    assert checks["Kaggle CPU/GPU numerical and latency qualification"] == {
        "name": "Kaggle CPU/GPU numerical and latency qualification",
        "status": "PASS",
        "evidence": PARITY_REPORT,
    }
    assert checks["10,000 complete neural-policy games"]["status"] == "QUEUED"
    assert gate["status"] == "RUNNING"
    assert gate["decision"] == "NOT_REVIEWED"
    assert gate["blockers"] == []

    parity_task = next(item for item in tasks if item.get("task_id") == "T-G2-003")
    assert parity_task["status"] == "SUCCEEDED"
    assert parity_task["bundle_report"] == (
        "reports/artifacts/g2-policy-qualification-bundle-v4.json"
    )
    assert parity_task["bundle_sha256"] == BUNDLE_SHA256
    assert parity_task["bundle_source_commit"] == SOURCE_COMMIT
    assert parity_task["completion_evidence"] == PARITY_REPORT
    assert parity_task["no_training"] is True

    policy_task = next(item for item in tasks if item.get("task_id") == "T-G2-002")
    assert policy_task["status"] == "RUNNING"
    assert policy_task["remaining_work"] == [
        "checkpoint package contract",
        "10,000 complete neural-policy games",
    ]
