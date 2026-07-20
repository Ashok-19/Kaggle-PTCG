from __future__ import annotations

import json
from pathlib import Path

from ptcg_rl.g3.evaluation import expected_evaluation_contract, load_evaluation_contract

IMPLEMENTATION_COMMIT = "6ca84cf7ccd79e49341998314da6d32aa8f1de45"
CONFIG_FILE_SHA256 = "51f5d0d800a0a3832cc0ea8873828f6c68262eb4f24e55a8b11ae4143a2dae72"
CONFIG_SEMANTIC_SHA256 = "bd3e0e6b5331fe6f6028df65403ecf2446250ebb8f375961544de26cf0ffc3b6"
REPORT_PATH = "reports/artifacts/g3a-evaluation-contract-v1.json"


def load(root: Path, relative: str):
    return json.loads((root / relative).read_text(encoding="utf-8"))


def test_g3a_evaluation_report_binds_exact_contract_and_validation() -> None:
    root = Path(__file__).resolve().parents[2]
    report = load(root, REPORT_PATH)
    contract = load_evaluation_contract(root / "configs/g3a_evaluation_v1.json")

    assert report["status"] == "SUCCEEDED"
    assert report["decision"] == "PASS"
    assert report["implementation"]["commit"] == IMPLEMENTATION_COMMIT
    assert report["implementation"]["config_file_sha256"] == CONFIG_FILE_SHA256
    assert report["implementation"]["config_semantic_sha256"] == CONFIG_SEMANTIC_SHA256
    assert contract.file_sha256 == CONFIG_FILE_SHA256
    assert contract.semantic_sha256 == CONFIG_SEMANTIC_SHA256
    assert contract.value == expected_evaluation_contract()

    designs = report["design_evaluation"]["candidates"]
    assert [item["disposition"] for item in designs] == [
        "REJECT",
        "REJECT_THRESHOLD_DRIFT_RISK",
        "SELECT",
    ]
    assert designs[0]["unresolved_placeholders"] == 5
    assert designs[2]["g3a_criteria_covered"] == 9
    assert designs[2]["sampled_future_thresholds_covered"] == 9

    proof = report["recurrent_task_proof"]
    assert proof["stateless_theoretical_ceiling"] == 0.5
    assert proof["recurrent_oracle_ceiling"] == 1.0
    assert proof["frozen_minimum_recurrent_score"] == 0.85
    assert proof["frozen_minimum_margin_vs_stateless"] == 0.25

    validation = report["validation"]
    assert validation["focused_tests"] == {"passed": 83, "failed": 0}
    assert validation["full_python_suite"] == {"passed": 286, "failed": 0}
    assert validation["ruff"] == "PASS"
    assert validation["independent_contract_mutation_branches_rejected"] == 10
    assert validation["independent_evidence_failure_branches_rejected"] == 17
    assert validation["independent_valid_evidence_review"] == "PASS"

    promotion = report["promotion_validation"]
    assert promotion["focused_g3_tests"] == {"passed": 86, "failed": 0}
    assert promotion["full_python_suite"] == {"passed": 289, "failed": 0}
    assert promotion["ruff"] == "PASS"
    assert promotion["dashboard_rebuild"]["ingested"] == 107
    assert promotion["dashboard_rebuild"]["quarantined"] == 0
    assert promotion["dashboard_doctor"] == "PASS"
    assert promotion["frontend_unit_tests"] == {"passed": 7, "failed": 0}
    assert promotion["frontend_build"] == "PASS"
    assert promotion["browser_tests"] == {"passed": 4, "failed": 0}

    assert report["authorization"] == {
        "training_authorized": False,
        "kaggle_run_performed": False,
        "colab_run_performed": False,
        "modal_used": False,
        "submission_created": False,
        "external_service_mutated": False,
    }


def test_g3a_gate_and_tasks_preserve_blocked_training_boundary() -> None:
    root = Path(__file__).resolve().parents[2]
    gate = load(root, "reports/gates/g3a.json")
    tasks = load(root, "reports/tasks/current.json")

    assert gate["status"] == "BLOCKED"
    assert gate["decision"] == "NOT_REVIEWED"
    assert gate["authorization"] == "EVALUATION_CONTRACT_FROZEN_TRAINING_NOT_AUTHORIZED"
    checks = {item["name"]: item for item in gate["technical_checks"]}
    assert checks["strict evaluation contract frozen"] == {
        "name": "strict evaluation contract frozen",
        "status": "PASS",
        "evidence": REPORT_PATH,
    }
    assert checks["PPO correctness harness and versioned toy task implementations"][
        "status"
    ] == "BLOCKED"
    assert checks["bounded three-seed private correctness smoke"]["status"] == "BLOCKED"
    assert len(gate["blockers"]) == 3

    contract_task = next(item for item in tasks if item.get("task_id") == "T-G3-EVAL-001")
    assert contract_task["status"] == "SUCCEEDED"
    assert contract_task["completion_commit"] == IMPLEMENTATION_COMMIT
    assert contract_task["completion_evidence"] == REPORT_PATH
    assert contract_task["config_file_sha256"] == CONFIG_FILE_SHA256
    assert contract_task["no_training"] is True

    smoke_task = next(item for item in tasks if item.get("task_id") == "T-G3-001")
    assert smoke_task["status"] == "BLOCKED"
    assert "PPO_CORRECTNESS_HARNESS_IMPLEMENTED" in smoke_task["depends_on"]
    assert "USER_TRAINING_APPROVAL" in smoke_task["depends_on"]
    assert smoke_task["evaluation_contract_evidence"] == REPORT_PATH


def test_status_documents_do_not_overclaim_g3a_completion_or_authorization() -> None:
    root = Path(__file__).resolve().parents[2]
    agents = (root.parent / "AGENTS.md").read_text(encoding="utf-8")
    project = (root / "PROJECT_STATUS.md").read_text(encoding="utf-8")
    progress = (root / "PROGRESS_REPORT.md").read_text(encoding="utf-8")

    assert IMPLEMENTATION_COMMIT in agents
    assert "`G3a` remains `BLOCKED / NOT_REVIEWED`" in agents
    assert "Gate status: G2 PASS / R1 PASS / G3a BLOCKED" in project
    assert "PPO training remains unauthorized" in project
    assert "PPO implementation is not complete" in project
    assert "Current verdict: **BLOCKED / NOT_REVIEWED**" in progress
    assert "no training" in progress.lower()
    assert "policy strength" in progress.lower()
