from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports/jobs/g3a-cloud-input-publication-v1.json"
CONFIG = ROOT / "configs/kaggle/g3a_cloud_correctness_v1.json"
NOTEBOOK = ROOT / "private/kaggle/notebooks/kptcg-g3a-cloud-correctness-v1.ipynb"

EXPECTED_FILES = {
    "g3a-cloud-input-manifest-v1.json": (
        724,
        "116a3cdebbd2b93becf6472b7ad34a4a1318e597cc8769adca18ea6d8cda036c",
    ),
    "g3a-cloud-plan-v1.json": (
        8309,
        "ea1e722657f358a85f64688e2df90397799bc17920adffe971a3ee7df72c871e",
    ),
    "g3a-cloud-source-manifest-v1.json": (
        3056,
        "c74480148bef75ccb29a214d6c1fabcd00d03542803a6d2882002c145d7ac36c",
    ),
    "g3a-cloud-source-v1.bundle": (
        5_052_825,
        "17580d32cb6b7dcc5ebffefccdf4cff8278b2f263a2c2a35558d5c456e85c532",
    ),
}


def load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_publication_receipt_binds_approval_dataset_and_local_notebook() -> None:
    report = load(REPORT)
    assert report["status"] == "SUCCEEDED"
    assert report["verdict"] == "PASS_FOR_USER_MANUAL_NOTEBOOK_IMPORT_AND_RUN"
    authorization = report["authorization"]
    assert authorization["user_plan_approval_received"] is True
    assert authorization["dataset_publication_authorized"] is True
    assert authorization["assistant_training_launch_authorized"] is False
    assert authorization["assistant_monitoring_authorized"] is False

    dataset = report["dataset"]
    assert dataset["ref"] == "ashok205/kptcg-g3a-correctness-inputs"
    assert dataset["version"] == 1
    assert dataset["private"] is True
    assert dataset["status"] == "READY"
    assert dataset["file_count"] == 4
    assert dataset["extra_remote_files"] == 0
    assert dataset["remote_download_verified"] is True
    observed = {
        item["name"]: (item["bytes"], item["sha256"])
        for item in dataset["files"]
    }
    assert observed == EXPECTED_FILES

    notebook = report["notebook"]
    assert notebook["state"] == "LOCAL_ONLY_READY"
    assert notebook["remote_notebook_created"] is False
    raw = NOTEBOOK.read_bytes()
    assert len(raw) == notebook["bytes"] == 5_581
    assert hashlib.sha256(raw).hexdigest() == notebook["sha256"]
    assert report["training_launched"] is False
    assert report["notebook_session_created"] is False
    assert report["external_service_mutated"] is True
    assert report["validation"] == {
        "targeted_publication_state_tests": {"passed": 15, "failed": 0},
        "focused_g3_tests": {"passed": 172, "failed": 0},
        "full_python_suite": {"passed": 375, "failed": 0},
        "ruff": "PASS",
        "dashboard_rebuild": {
            "ingested": 115,
            "quarantined": 0,
            "status": "PASS",
        },
        "dashboard_doctor": "PASS",
        "frontend_unit_tests": {"passed": 7, "failed": 0},
        "frontend_build": "PASS",
        "browser_tests": {"passed": 4, "failed": 0},
    }


def test_preapproval_plan_remains_immutable_and_authorization_is_separate() -> None:
    config = load(CONFIG)
    assert config["authorization"] == {
        "external_mutation_authorized": False,
        "submission_authorized": False,
        "training_launch_authorized": False,
    }
    report = load(REPORT)
    assert report["source"]["plan_config_sha256"] == hashlib.sha256(
        CONFIG.read_bytes()
    ).hexdigest()
    assert len(report["completed_negative_results"]) == 2
    assert all(
        item["mutation_occurred"] is False
        for item in report["completed_negative_results"]
    )


def test_gate_and_task_ledger_require_the_user_run_and_outputs() -> None:
    gate = load(ROOT / "reports/gates/g3a.json")
    tasks = load(ROOT / "reports/tasks/current.json")
    assert gate["status"] == "BLOCKED"
    assert gate["decision"] == "NOT_REVIEWED"
    assert gate["authorization"] == (
        "USER_APPROVAL_RECORDED_DATASET_READY_ASSISTANT_LAUNCH_NOT_PERFORMED"
    )
    checks = {item["name"]: item for item in gate["technical_checks"]}
    assert checks["explicit user training approval recorded"]["status"] == "PASS"
    assert checks[
        "private Kaggle input dataset version 1 ready and byte verified"
    ]["status"] == "PASS"
    assert checks["single local notebook frozen and ready for user import"]["status"] == "PASS"
    assert checks["bounded three-seed private correctness smoke"]["status"] == "BLOCKED"
    assert len(gate["blockers"]) == 1

    publication = next(item for item in tasks if item.get("task_id") == "T-G3-PUBLISH-001")
    assert publication["status"] == "SUCCEEDED"
    assert publication["dataset_version"] == 1
    assert publication["dataset_status"] == "READY"
    assert publication["remote_download_hashes_match"] is True
    assert publication["training_launched"] is False

    launch = next(item for item in tasks if item.get("task_id") == "T-G3-001")
    assert launch["status"] == "BLOCKED"
    assert launch["user_training_approval_granted"] is True
    assert launch["dataset_status"] == "READY"
    assert launch["user_manual_run_required"] is True
    assert launch["assistant_launch_performed"] is False
