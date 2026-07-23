from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "reports/jobs/g3a-cloud-input-publication-v3.json"
HISTORICAL_REPORTS = (
    ROOT / "reports/jobs/g3a-cloud-input-publication-v1.json",
    ROOT / "reports/jobs/g3a-cloud-input-publication-v2.json",
)
CONFIG = ROOT / "configs/kaggle/g3a_cloud_correctness_v1.json"
NOTEBOOK = ROOT / "private/kaggle/notebooks/kptcg-g3a-cloud-correctness-v1.ipynb"

EXPECTED_FILES = {
    "g3a-cloud-input-manifest-v1.json": (
        724,
        "4a5394d0deb34e4d0064f1539304aafcd13227414ce6122c1e6985dc0e7126ab",
    ),
    "g3a-cloud-plan-v1.json": (
        8_394,
        "c0ea3bfa83cc2e86e1933555926c9f957da01ac9618e13f03e9f85d1a6b7957b",
    ),
    "g3a-cloud-source-manifest-v1.json": (
        3_056,
        "f4d79f1bf6e17d88621df240672a60fbfedb1529a75efaa6daafd0133d6f8afb",
    ),
    "g3a-cloud-source-v1.bundle": (
        7_541_761,
        "048a76aa4f0e1d44b4d178dd0ffe91e830215b7942b55aaad820b2910ceab030",
    ),
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def notebook_code() -> str:
    notebook = load(NOTEBOOK)
    return "".join(
        "".join(cell["source"])
        for cell in notebook["cells"]
        if cell["cell_type"] == "code"
    )


def test_version_three_publication_binds_seeded_rollout_fix() -> None:
    report = load(REPORT)
    assert report["status"] == "SUCCEEDED"
    assert report["verdict"] == "PASS_FOR_USER_MANUAL_RERUN_WITH_DATASET_VERSION_3"
    assert all(path.is_file() for path in HISTORICAL_REPORTS)
    assert report["trigger"]["manual_user_run"] is True
    assert report["trigger"]["passing_g3a_result_produced"] is False

    root_cause = report["root_cause"]
    assert root_cause["classification"] == "CLOUD_RUNNER_EXPLORATION_MISMATCH"
    assert root_cause["threshold_or_budget_issue"] is False
    assert root_cause["kaggle_hardware_issue"] is False
    assert set(root_cause["bounded_reproduction"]["corrected_cloud_runner_scores"].values()) == {
        1.0
    }

    correction = report["correction"]
    assert correction["rollout_sampling"] == "seeded_categorical"
    assert correction["rollout_seed_xor"] == 0x5A17
    assert correction["rollout_rng_checkpointed_as"] == "torch_cpu"
    assert correction["fixed_evaluation_remains_greedy_argmax"] is True
    assert correction["learning_rate_changed"] is False
    assert correction["budget_changed"] is False
    assert correction["thresholds_changed"] is False
    assert correction["tasks_changed"] is False

    dataset = report["dataset"]
    assert dataset["ref"] == "ashok205/kptcg-g3a-correctness-inputs"
    assert dataset["version"] == 3
    assert dataset["historical_versions_retained"] == [1, 2]
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


def test_revised_plan_notebook_and_source_are_exactly_bound() -> None:
    report = load(REPORT)
    config_raw = CONFIG.read_bytes()
    config = json.loads(config_raw)
    assert hashlib.sha256(config_raw).hexdigest() == (
        "c0ea3bfa83cc2e86e1933555926c9f957da01ac9618e13f03e9f85d1a6b7957b"
    )
    assert report["source"]["plan_config_sha256"] == hashlib.sha256(
        config_raw
    ).hexdigest()
    assert report["source"]["executable_source_commit"] == (
        "6b7975bf518c36ff59338b6793ec52530c73f173"
    )
    assert config["source"]["commit"] == report["source"]["executable_source_commit"]
    assert config["assets"]["dataset"]["version"] == 3
    assert config["work"]["rollout_sampling"] == "seeded_categorical"
    assert config["work"]["rollout_seed_xor"] == 0x5A17

    notebook = report["notebook"]
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


def test_gate_and_tasks_require_dataset_three_rerun() -> None:
    gate = load(ROOT / "reports/gates/g3a.json")
    tasks = load(ROOT / "reports/tasks/current.json")
    assert gate["status"] == "BLOCKED"
    assert gate["decision"] == "NOT_REVIEWED"
    checks = {item["name"]: item for item in gate["technical_checks"]}
    assert checks[
        "private Kaggle input dataset version 3 ready and byte verified"
    ]["status"] == "PASS"
    assert checks["bounded three-seed private correctness smoke"]["status"] == "BLOCKED"
    assert "version 3" in gate["approved_next_action"]
    assert "Versions 1 and 2" in " ".join(gate["warnings"])

    by_id = {item["task_id"]: item for item in tasks}
    publication = by_id["T-G3-PUBLISH-001"]
    assert publication["dataset_version"] == 3
    assert publication["dataset_status"] == "READY"
    assert publication["remote_download_hashes_match"] is True
    assert publication["completion_evidence"] == REPORT.relative_to(ROOT).as_posix()
    assert publication["completion_evidence_sha256"] == hashlib.sha256(
        REPORT.read_bytes()
    ).hexdigest()

    fix = by_id["T-G3-FIX-001"]
    assert fix["status"] == "SUCCEEDED"
    assert fix["completion_commit"] == "6b7975bf518c36ff59338b6793ec52530c73f173"
    assert fix["thresholds_changed"] is False
    assert fix["budget_changed"] is False
    assert fix["assistant_training_launch_performed"] is False

    launch = by_id["T-G3-001"]
    assert launch["status"] == "BLOCKED"
    assert launch["dataset_version"] == 3
    assert launch["previous_user_run_status"] == "FAILED_STRICT_FINAL_REVIEW"
    assert launch["rollout_sampling"] == "seeded_categorical"
    assert launch["assistant_launch_performed"] is False
