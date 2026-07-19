from __future__ import annotations

import json
from pathlib import Path

PACKAGE_SHA256 = "4dfba2adb9f97607cfa5dabadba075236bb7aae51eafab264584e947feae3827"
MANIFEST_SHA256 = "1185c97d1fca8cb795e2c5f84f5d0a915cf41fac242aefed888b4e0dd84b267c"
IMPLEMENTATION_COMMIT = "6b3a3b4829b205d62e210fae7e396db33fdb9a5a"
STATE_SHA256 = "531b799b29830954dce62cd7d1b455eb30d5189cf670158723ee01b3e2ed6ab0"
REPORT_PATH = "reports/artifacts/g2-policy-checkpoint-v1.json"


def load(root: Path, relative: str):
    return json.loads((root / relative).read_text(encoding="utf-8"))


def test_checkpoint_report_records_deterministic_pickle_free_package() -> None:
    root = Path(__file__).resolve().parents[2]
    report = load(root, REPORT_PATH)

    assert report["status"] == "SUCCEEDED"
    assert report["implementation_commit"] == IMPLEMENTATION_COMMIT
    assert report["qualification_source_commit"] == IMPLEMENTATION_COMMIT
    assert report["model"]["qualification_state_sha256"] == STATE_SHA256
    assert report["model"]["trainable_parameters"] == 970022

    package = report["private_artifacts"]["package"]
    assert package["path"] == "private/g2/checkpoint-v1/g2-policy-checkpoint-v1.zip"
    assert package["bytes"] == 5429190
    assert package["sha256"] == PACKAGE_SHA256
    assert package["manifest_sha256"] == MANIFEST_SHA256

    format_decision = report["format_decision"]
    assert "ZIP_STORED" in format_decision["archive"]
    assert "pickle-free" in format_decision["state"]
    assert format_decision["state_entries"] == 141
    selection = format_decision["selection_evidence"]
    assert selection["torch_save"]["insertion_order_independent"] is False
    assert selection["numpy_npz"]["insertion_order_independent"] is False
    assert selection["numpy_npz_compressed"]["insertion_order_independent"] is False
    assert selection["canonical_tensor_stream"]["insertion_order_independent"] is True
    assert selection["safetensors_available_in_locked_environment"] is False

    authorization = report["authorization"]
    assert authorization == {
        "optimizer_created": False,
        "optimizer_steps": 0,
        "training_loop_ran": False,
        "training_state_included": False,
        "pickle_used": False,
        "kaggle_run_performed": False,
        "external_service_mutated": False,
    }
    assert report["privacy"]["package_ignored"] is True
    assert report["privacy"]["raw_tensor_values_in_public_report"] is False


def test_checkpoint_report_records_completed_reference_and_adversarial_validation() -> None:
    root = Path(__file__).resolve().parents[2]
    report = load(root, REPORT_PATH)
    qualification = report["qualification"]

    assert qualification["status"] == "PASS"
    assert qualification["duplicate_build_byte_match"] is True
    assert qualification["source_files_verified"] == 13
    assert qualification["model_relevant_files_unchanged_since_kaggle_parity"] == 11
    assert qualification["state_matches_kaggle_parity"] is True
    assert qualification["reference_numeric_values"] == 1150
    assert qualification["reference_exact_values"] == 16
    assert qualification["reference_max_absolute_difference"] == 0.0
    assert qualification["compound_log_probability_tolerance"] == 0.00001
    assert qualification["current_tree_verifications"] == 2
    assert qualification["isolated_clean_runtime_verification"] == "PASS"
    assert qualification["isolated_module_origins_under_copied_source"] == 7
    assert qualification["adversarial_fail_closed_branches"] == 25
    assert qualification["unit_and_contract_tests"] == 27
    assert qualification["full_python_suite"] == {"passed": 159, "failed": 0}
    assert len(report["fail_closed_scope"]) == 9

    private = report["private_artifacts"]
    assert private["qualification_receipt"]["sha256"] == (
        "fbf73b7f8344691e69ba7e56864bed03142a660f0ab47a7ca2ba445342678d93"
    )
    assert private["second_verification"]["sha256"] == (
        "ba872f8d2c47a4bb8ed74cf203eb1ca5e7796cd09961dddb32b4e9edbabe32f8"
    )
    assert private["adversarial_audit"]["sha256"] == (
        "97b236267b9425f2f4a76a16acf70a004a6b85a8d1baa61626c5e66a46a25c97"
    )


def test_gate_and_tasks_close_checkpoint_only_and_keep_g2_running() -> None:
    root = Path(__file__).resolve().parents[2]
    gate = load(root, "reports/gates/g2.json")
    tasks = load(root, "reports/tasks/current.json")
    policy = load(root, "reports/artifacts/g2-policy-v1.json")

    checks = {item["name"]: item for item in gate["technical_checks"]}
    assert checks["deterministic fail-closed checkpoint package"] == {
        "name": "deterministic fail-closed checkpoint package",
        "status": "PASS",
        "evidence": REPORT_PATH,
    }
    reliability = checks["10,000 complete neural-policy games"]
    assert reliability == {
        "name": "10,000 complete neural-policy games",
        "status": "READY_FOR_USER_RUN",
        "evidence": "reports/artifacts/g2-neural-reliability-readiness-v1.json",
    }
    assert reliability["status"] != "PASS"
    assert gate["status"] == "RUNNING"
    assert gate["decision"] == "NOT_REVIEWED"
    assert gate["blockers"] == [
        "The private Kaggle reliability input dataset has not been created because the available execution interfaces blocked the external create transaction before network access."
    ]

    checkpoint_task = next(item for item in tasks if item.get("task_id") == "T-G2-004")
    assert checkpoint_task["status"] == "SUCCEEDED"
    assert checkpoint_task["implementation_commit"] == IMPLEMENTATION_COMMIT
    assert checkpoint_task["completion_evidence"] == REPORT_PATH
    assert checkpoint_task["package_sha256"] == PACKAGE_SHA256
    assert checkpoint_task["qualification_state_sha256"] == STATE_SHA256
    assert checkpoint_task["adversarial_fail_closed_branches"] == 25
    assert checkpoint_task["no_training"] is True
    assert checkpoint_task["kaggle_run_performed"] is False

    policy_task = next(item for item in tasks if item.get("task_id") == "T-G2-002")
    assert policy_task["status"] == "RUNNING"
    assert policy_task["checkpoint_evidence"] == REPORT_PATH
    assert policy_task["remaining_work"] == ["10,000 complete neural-policy games"]

    assert policy["external_qualification"] == {
        "checkpoint_package": REPORT_PATH,
        "cpu_gpu_parity": "reports/evaluations/g2-policy-cpu-gpu-parity-v4.json",
    }
    assert policy["not_yet_qualified"] == [
        "10,000 complete neural-policy games",
        "submission-runtime parity",
        "policy strength or learning",
    ]
