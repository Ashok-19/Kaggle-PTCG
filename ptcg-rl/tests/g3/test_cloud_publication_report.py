from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports/jobs/g3a-cloud-input-publication-v2.json"
HISTORICAL_REPORT = ROOT / "reports/jobs/g3a-cloud-input-publication-v1.json"
CONFIG = ROOT / "configs/kaggle/g3a_cloud_correctness_v1.json"
NOTEBOOK = ROOT / "private/kaggle/notebooks/kptcg-g3a-cloud-correctness-v1.ipynb"

EXPECTED_FILES = {
    "g3a-cloud-input-manifest-v1.json": (
        724,
        "2c9fa5e441701c2b9ff92e2d05e73513173ddd8ff362565c424c37b5c620ff52",
    ),
    "g3a-cloud-plan-v1.json": (
        8329,
        "617c46cbf05a985f4cd1d462f9408a8ce39dc63f20104396dc21335f7184855b",
    ),
    "g3a-cloud-source-manifest-v1.json": (
        3056,
        "d7cc817551f79fa5d093111d960bbd4c3958b2a8dd0956d6c3a07e22a8a37cea",
    ),
    "g3a-cloud-source-v1.bundle": (
        6_961_132,
        "102b802fb1d54355308ebf8d19b759909950f507559cdad329f279d47cbe4fe5",
    ),
}


def load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def notebook_code() -> str:
    notebook = load(NOTEBOOK)
    return "".join(
        "".join(cell["source"])
        for cell in notebook["cells"]
        if cell["cell_type"] == "code"
    )


def test_corrective_publication_binds_version_two_and_local_notebook() -> None:
    report = load(REPORT)
    assert report["status"] == "SUCCEEDED"
    assert report["verdict"] == (
        "PASS_FOR_USER_MANUAL_NOTEBOOK_IMPORT_AND_RUN_WITH_DATASET_VERSION_2"
    )
    assert HISTORICAL_REPORT.is_file()

    correction = report["correction"]
    assert correction["kaggle_secret_required"] is False
    assert correction["authorization_environment_variable_required"] is False
    assert correction["authorization_cli_flag_required"] is False
    assert correction["external_network_probe_performed"] is False

    dataset = report["dataset"]
    assert dataset["ref"] == "ashok205/kptcg-g3a-correctness-inputs"
    assert dataset["version"] == 2
    assert dataset["previous_version_retained"] == 1
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
    assert len(raw) == notebook["bytes"] == 4_787
    assert hashlib.sha256(raw).hexdigest() == notebook["sha256"]
    code = notebook_code()
    for forbidden in (
        "KPTCG_G3A_TRAINING_APPROVED",
        "--authorize-training",
        "urllib.request",
        "urlopen(",
        "UserSecretsClient",
        "get_secret(",
    ):
        assert forbidden not in code
    assert report["training_launched"] is False
    assert report["notebook_session_created"] is False
    assert report["external_service_mutated"] is True
    assert report["validation"] == {
        "pre_freeze_targeted_tests": {"passed": 6, "failed": 0},
        "post_publication_targeted_tests": {"passed": 17, "failed": 0},
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
        "post_publication_validation_pending": False,
    }


def test_revised_plan_and_receipt_bind_the_clean_source_commit() -> None:
    report = load(REPORT)
    config_raw = CONFIG.read_bytes()
    config = json.loads(config_raw)
    assert hashlib.sha256(config_raw).hexdigest() == (
        "617c46cbf05a985f4cd1d462f9408a8ce39dc63f20104396dc21335f7184855b"
    )
    assert report["source"]["plan_config_sha256"] == hashlib.sha256(
        config_raw
    ).hexdigest()
    assert report["source"]["executable_source_commit"] == (
        "95651d6c3979f12e5a8a63556b0030745d6fab34"
    )
    assert config["source"]["commit"] == report["source"]["executable_source_commit"]
    assert config["assets"]["dataset"]["version"] == 2
    assert config["authorization"] == {
        "external_mutation_authorized": False,
        "submission_authorized": False,
        "training_launch_authorized": False,
    }
    assert len(report["completed_negative_results"]) == 3
    assert all(
        item["mutation_occurred"] is False
        for item in report["completed_negative_results"]
    )
    assert all(
        item["training_started"] is False
        for item in report["completed_negative_results"]
    )


def test_gate_and_task_ledgers_require_only_the_user_run_and_outputs() -> None:
    gate = load(ROOT / "reports/gates/g3a.json")
    tasks = load(ROOT / "reports/tasks/current.json")
    assert gate["status"] == "BLOCKED"
    assert gate["decision"] == "NOT_REVIEWED"
    checks = {item["name"]: item for item in gate["technical_checks"]}
    assert checks["explicit user training approval recorded"]["status"] == "PASS"
    assert checks[
        "private Kaggle input dataset version 2 ready and byte verified"
    ]["status"] == "PASS"
    assert checks["single local notebook frozen and ready for user import"]["status"] == "PASS"
    assert checks["bounded three-seed private correctness smoke"]["status"] == "BLOCKED"
    assert len(gate["blockers"]) == 1
    assert "version 2" in gate["approved_next_action"]
    assert "secret" in gate["approved_next_action"]
    assert "network probe" in gate["approved_next_action"]

    publication = next(item for item in tasks if item.get("task_id") == "T-G3-PUBLISH-001")
    assert publication["status"] == "SUCCEEDED"
    assert publication["dataset_version"] == 2
    assert publication["dataset_status"] == "READY"
    assert publication["remote_download_hashes_match"] is True
    assert publication["secret_or_environment_authorization_required"] is False
    assert publication["network_probe_performed"] is False
    assert publication["training_launched"] is False
    assert publication["completion_evidence"] == REPORT.relative_to(ROOT).as_posix()
    assert publication["completion_evidence_sha256"] == hashlib.sha256(
        REPORT.read_bytes()
    ).hexdigest()

    launch = next(item for item in tasks if item.get("task_id") == "T-G3-001")
    assert launch["status"] == "BLOCKED"
    assert launch["user_training_approval_granted"] is True
    assert launch["dataset_version"] == 2
    assert launch["dataset_status"] == "READY"
    assert launch["user_manual_run_required"] is True
    assert launch["assistant_launch_performed"] is False
    assert launch["secret_or_environment_authorization_required"] is False
    assert launch["network_probe_performed"] is False
