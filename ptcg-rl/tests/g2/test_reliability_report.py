from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
READINESS = ROOT / "reports/artifacts/g2-neural-reliability-readiness-v1.json"
FINAL = ROOT / "reports/evaluations/g2-neural-reliability-v1.json"
TASKS = ROOT / "reports/tasks/current.json"
GATE = ROOT / "reports/gates/g2.json"
EVENTS = ROOT / "reports/events/g2-policy-events.json"
STATUS = ROOT / "PROJECT_STATUS.md"


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_historical_readiness_report_remains_sealed_without_retroactive_claims() -> None:
    report = read(READINESS)
    assert report["status"] == "SUCCEEDED"
    assert report["decision"] == "READY_FOR_MANUAL_KAGGLE_RUN"
    assert report["source_commit"] == "b536f3ac66796cdabc382f318126a99b0eeeae85"
    assert report["implementation"]["python_tests_passed"] == 202
    assert report["implementation"]["training_performed"] is False
    assert report["manual_notebook"]["assistant_launched_kaggle_run"] is False
    assert "10,000 complete neural-policy games" in report["qualification_not_claimed"]
    assert "G2 PASS" in report["qualification_not_claimed"]


def test_final_reliability_evaluation_binds_exact_downloaded_and_recalculated_evidence() -> None:
    report = read(FINAL)
    assert report["status"] == "SUCCEEDED"
    assert report["decision"] == "PASS"
    assert report["identity"]["source_commit"] == (
        "b536f3ac66796cdabc382f318126a99b0eeeae85"
    )
    assert report["identity"]["script_version_id"] == 336684242
    assert report["identity"]["notebook_file_sha256"] == (
        "58abcac4b975dae048e07f6419c039f14922ef28044ab13d6074ecf131b36b21"
    )
    assert report["identity"]["canonical_notebook_source_sha256"] == (
        "d15820fe5b758ef17fdad9d6429999de96a3d1d9f0baebfc130c9277a4ff0316"
    )
    assert report["identity"][
        "saved_source_matches_canonical_after_surrounding_whitespace"
    ] is True
    assert report["input"]["dataset_version"] == 1
    assert report["input"]["dataset_status"] == "READY"

    execution = report["execution"]
    assert execution["manual_user_run"] is True
    assert execution["assistant_launched_kaggle_run"] is False
    assert execution["internet"] == "BLOCKED"
    assert execution["visible_cuda_device_count"] == 2
    assert execution["visible_cuda_device_names"] == ["Tesla T4", "Tesla T4"]
    assert execution["inference_servers"] == 2
    assert execution["workers_per_device"] == 16
    assert execution["total_engine_workers"] == 32
    assert execution["max_batch"] == 16
    assert execution["batch_wait_ms"] == 1.0
    assert execution["optimizer_created"] is False
    assert execution["training_loop_ran"] is False
    assert execution["ppo_ran"] is False

    results = report["results"]
    assert results["expected_games"] == results["observed_games"] == 10_000
    assert results["complete_game_index_set"] is True
    assert results["duplicate_indices"] == []
    assert results["missing_index_count"] == 0
    assert results["unexpected_index_count"] == 0
    assert results["failing_game_count"] == 0
    assert results["engine_requests"] == 1_213_203
    assert results["multi_select_requests"] == 20_791
    assert results["max_observed_options"] == 53
    assert results["max_observed_select_count"] == 3
    for group in results["zero_tolerance"].values():
        assert set(group.values()) == {0}
    process = results["process_evidence"]
    assert process["status"] == "PASS"
    assert process["expected_workers"] == process["observed_workers"] == 32
    assert process["expected_servers"] == process["observed_servers"] == 2
    assert process["server_decisions"] == results["engine_requests"]
    assert process["failures"] == []

    artifacts = report["artifacts"]
    assert artifacts["games_jsonl"] == {
        "bytes": 28_783_333,
        "sha256": "39d7d43d142bec64bcace5da5151ca6bccba2bd533c47d1957a4ad7505cc918f",
    }
    assert artifacts["runner_receipt"]["sha256"] == (
        "9afc97ffe2df08dcb84ebe087e993649b868719e547204efb04c51b776f7c3e7"
    )
    assert artifacts["output_manifest"]["downloaded_file_mismatch_count"] == 0
    independent = report["independent_recalculation"]
    assert independent["status"] == "PASS"
    assert independent["canonical_game_records_streamed"] == 10_000
    assert independent["compared_summary_fields"] == 21
    assert independent["all_compared_fields_exact_match"] is True
    assert independent["process_accounting_recalculated"] is True
    assert independent["assistant_review_sha256"] == (
        "7a1f77f452db96015a18c54631952b3d67b8bcd7cea7314372f3e45003681e6e"
    )


def test_task_and_gate_close_g2_but_preserve_training_boundary() -> None:
    tasks = {task["task_id"]: task for task in read(TASKS)}
    reliability = tasks["T-G2-005"]
    assert reliability["status"] == "SUCCEEDED"
    assert reliability["completion_evidence"] == FINAL.relative_to(ROOT).as_posix()
    assert reliability["kaggle_dataset_status"] == "READY"
    assert reliability["kaggle_dataset_version"] == 1
    assert reliability["games"] == 10_000
    assert reliability["zero_tolerance_failures"] == 0
    assert reliability["independent_review_status"] == "PASS"
    assert reliability["assistant_kaggle_run_performed"] is False
    assert tasks["T-G2-002"]["status"] == "SUCCEEDED"
    assert tasks["T-G2-002"]["no_training"] is True
    assert tasks["T-G3-001"]["status"] == "BLOCKED"
    assert "explicit user training approval" in tasks["T-G3-001"]["blocker"]

    gate = read(GATE)
    assert gate["status"] == "SUCCEEDED"
    assert gate["decision"] == "PASS"
    assert gate["blockers"] == []
    check = next(
        item
        for item in gate["technical_checks"]
        if item["name"] == "10,000 complete neural-policy games"
    )
    assert check == {
        "name": "10,000 complete neural-policy games",
        "status": "PASS",
        "evidence": FINAL.relative_to(ROOT).as_posix(),
    }
    assert "TRAINING_NOT_AUTHORIZED" in gate["authorization"]


def test_event_and_project_status_record_final_pass_without_training() -> None:
    events = read(EVENTS)
    event = next(
        item
        for item in events
        if item["record_id"] == "event-g2-neural-reliability-passed-20260720"
    )
    assert event["status_after"] == "SUCCEEDED"
    assert event["source_path"] == FINAL.relative_to(ROOT).as_posix()
    assert "exactly 10,000 games" in event["summary"]
    assert "no optimizer or training loop ran" in event["summary"]

    status = STATUS.read_text(encoding="utf-8")
    assert "G2 PASS / R1 PASS / G3a BLOCKED" in status
    assert "Exactly 10,000 games" in status
    assert "The assistant did not launch or rerun the notebook." in status
    assert "PPO training remains unauthorized" in status
