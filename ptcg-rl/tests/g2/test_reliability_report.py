from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
READINESS = ROOT / "reports/artifacts/g2-neural-reliability-readiness-v1.json"
TASKS = ROOT / "reports/tasks/current.json"
GATE = ROOT / "reports/gates/g2.json"
EVENTS = ROOT / "reports/events/g2-policy-events.json"
STATUS = ROOT / "PROJECT_STATUS.md"


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_reliability_readiness_report_binds_verified_artifacts_without_claiming_qualification() -> None:
    report = read(READINESS)
    assert report["status"] == "SUCCEEDED"
    assert report["decision"] == "READY_FOR_MANUAL_KAGGLE_RUN"
    assert report["source_commit"] == "b536f3ac66796cdabc382f318126a99b0eeeae85"
    assert report["implementation"]["python_tests_passed"] == 202
    assert report["implementation"]["training_performed"] is False
    assert report["selected_topology"] == {
        "inference_servers": 2,
        "devices": ["cuda:0", "cuda:1"],
        "required_accelerator": "GPU T4 x2",
        "workers_per_device": 8,
        "total_engine_workers": 16,
        "max_batch": 8,
        "batch_wait_ms": 2.0,
        "games": 10000,
        "internet": "OFF",
    }
    smoke = report["exact_topology_local_smoke"]
    assert smoke["games"] == 32
    assert smoke["engine_requests"] == smoke["server_decisions"] == 3892
    assert smoke["zero_tolerance_failures"] == 0
    assert smoke["independent_review"]["status"] == "PASS"
    assert report["live_fail_closed_audit"]["branch_count"] == 7
    assert report["live_fail_closed_audit"]["all_branches_completed"] is True
    assert report["sealed_input"]["archive"]["duplicate_build_byte_match"] is True
    assert report["manual_notebook"]["code_cell_exact_match"] is True
    assert report["manual_notebook"]["assistant_launched_kaggle_run"] is False
    assert report["kaggle_dataset"]["status"] == "NOT_CREATED"
    assert "10,000 complete neural-policy games" in report["qualification_not_claimed"]
    assert "G2 PASS" in report["qualification_not_claimed"]


def test_task_and_gate_remain_open_until_manual_run_and_independent_review() -> None:
    tasks = {task["task_id"]: task for task in read(TASKS)}
    reliability = tasks["T-G2-005"]
    assert reliability["status"] == "AWAITING_USER_ACTION"
    assert reliability["readiness_evidence"] == READINESS.relative_to(ROOT).as_posix()
    assert reliability["kaggle_dataset_status"] == "NOT_CREATED"
    assert reliability["assistant_kaggle_run_performed"] is False
    assert tasks["T-G2-002"]["status"] == "RUNNING"
    assert tasks["T-G2-002"]["remaining_work"] == [
        "10,000 complete neural-policy games"
    ]

    gate = read(GATE)
    assert gate["status"] == "RUNNING"
    assert gate["decision"] == "NOT_REVIEWED"
    check = next(
        item
        for item in gate["technical_checks"]
        if item["name"] == "10,000 complete neural-policy games"
    )
    assert check["status"] == "READY_FOR_USER_RUN"
    assert check["evidence"] == READINESS.relative_to(ROOT).as_posix()
    assert gate["blockers"]
    assert all(item["status"] != "PASS" for item in [check])


def test_event_and_project_status_preserve_manual_run_boundary() -> None:
    events = read(EVENTS)
    event = next(
        item
        for item in events
        if item["record_id"] == "event-g2-neural-reliability-ready-20260719"
    )
    assert event["status_after"] == "RUNNING"
    assert event["source_path"] == READINESS.relative_to(ROOT).as_posix()
    assert "assistant launched no Kaggle notebook" in event["summary"]

    status = STATUS.read_text(encoding="utf-8")
    assert "10k-game result pending" in status
    assert "The assistant must never launch or rerun this notebook." in status
    assert "training remains blocked" in status
