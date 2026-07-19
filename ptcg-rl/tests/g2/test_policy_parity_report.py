from __future__ import annotations

import json
from pathlib import Path


def load(root: Path, relative: str):
    return json.loads((root / relative).read_text(encoding="utf-8"))


def test_strict_kaggle_cpu_t4_parity_report_passes_fail_closed_contract() -> None:
    root = Path(__file__).resolve().parents[2]
    report = load(root, "reports/evaluations/g2-policy-cpu-gpu-parity-v4.json")

    assert report["status"] == "SUCCEEDED"
    assert report["decision"] == "PASS"
    assert report["tolerance"]["absolute"] == 0.00001
    assert report["tolerance"]["relative"] == 0.00001
    assert report["identity"]["all_cpu_gpu_identity_fields_match"] is True
    assert report["identity"]["trainable_parameters"] == 970022

    comparison = report["comparison"]
    assert comparison["compared_nodes"] == 1619
    assert comparison["numeric_values"] == 1596
    assert comparison["failure_count"] == 0
    assert comparison["selected_gradient_records_cpu"] == 7
    assert comparison["selected_gradient_records_gpu"] == 7
    assert comparison["all_values_within_tolerance"] is True
    assert comparison["max_tolerance_ratio"] < 1.0

    checks = report["qualification_checks"]
    assert checks["required_checks_per_device"] == 10
    assert checks["cpu_all_checks"] is True
    assert checks["gpu_all_checks"] is True
    assert checks["optimizer_created"] is False
    assert checks["optimizer_steps"] == 0
    assert checks["training_loop_ran"] is False
    assert report["notebooks"]["cpu"]["external_http_probe"] == "BLOCKED"
    assert report["notebooks"]["gpu"]["active_device"] == "Tesla T4"
    assert report["notebooks"]["gpu"]["requested_topology"] == "GPU T4 x2"


def test_cpu_gpu_job_receipts_and_non_t4_incident_are_public_safe() -> None:
    root = Path(__file__).resolve().parents[2]
    gpu = load(root, "reports/jobs/g2-policy-cuda-qualification-v4.json")
    cpu = load(root, "reports/jobs/g2-policy-cpu-qualification-v4.json")
    incident = load(root, "reports/incidents/g2-kaggle-cli-p100-assignment.json")

    assert gpu["status"] == "SUCCEEDED"
    assert gpu["notebook"]["version"] == 1
    assert gpu["requested"]["accelerator"] == "GPU T4 x2"
    assert gpu["observed"]["active_device_name"] == "Tesla T4"
    assert gpu["observed"]["visible_cuda_device_count"] is None
    assert gpu["checks"]["optimizer_created"] is False
    assert gpu["checks"]["training_loop_ran"] is False
    assert gpu["output"]["raw_result"]["sha256"] == (
        "e7f63f73005f7fb31afc1d50bc9358bc86d0e025764dd891f7864012ddb06c99"
    )

    assert cpu["status"] == "SUCCEEDED"
    assert cpu["notebook"]["version"] == 4
    assert cpu["internet_evidence"]["external_http_probe"] == "BLOCKED"
    assert cpu["checks"]["optimizer_created"] is False
    assert cpu["checks"]["training_loop_ran"] is False
    assert cpu["latency_ms"]["batch1_five_options"]["p99"] == 8.802885
    assert cpu["output"]["raw_result"]["sha256"] == (
        "33064df7c642bfb56a219ae71a5a1f332b5ecce5b0626390d9243f97cf48d756"
    )

    assert incident["status"] == "RESOLVED"
    assert incident["trigger"]["observed"] == "Tesla P100-PCIE-16GB"
    assert incident["trigger"]["result"] == "ERROR_BEFORE_QUALIFICATION"
    assert incident["impact"]["official_t4_evidence_changed"] is False
    assert incident["impact"]["training_ran"] is False
    assert incident["resolution"]["automatic_cli_gpu_assignment_accepted"] is False
