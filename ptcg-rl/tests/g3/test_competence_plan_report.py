from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "configs/g3b_competence_plan_v1.json"
REPORT = ROOT / "reports/artifacts/g3b-competence-plan-v1.json"
REVIEW = ROOT / "reports/artifacts/g3b-competence-plan-review-v1.json"
GATE = ROOT / "reports/gates/g3b.json"
TASKS = ROOT / "reports/tasks/current.json"
HYPOTHESES = ROOT / "reports/hypotheses/current.json"
EVENTS = ROOT / "reports/events/g3b-events.json"
PLAN_SHA256 = "99cf090df232ffe37504eee4b86ab70554256b5ad89fe972bb9bb5033115bc26"
REVIEW_SHA256 = "23f5c5c02d74c0db8e91652016d20eb755c1eba515a84067fca6c85d7fb4afe0"
PLANNER_COMMIT = "098997ae96b3e96a8739cc407fcb16e845c60774"
PLANNER_TREE = "d118a6d1c729b5b9726e18d2d445a08b9dfa37f7"


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_plan_report_binds_immutable_source_plan_and_independent_review() -> None:
    report = read(REPORT)
    assert report["status"] == "SUCCEEDED"
    assert report["decision"] == "PASS"
    assert report["identity"]["planner_commit"] == PLANNER_COMMIT
    assert report["identity"]["planner_tree"] == PLANNER_TREE
    assert report["identity"]["canonical_plan"] == {
        "path": PLAN.relative_to(ROOT).as_posix(),
        "bytes": 12_291,
        "sha256": PLAN_SHA256,
    }
    assert PLAN.stat().st_size == 12_291
    assert sha(PLAN) == PLAN_SHA256
    assert report["identity"]["independent_review"] == {
        "path": REVIEW.relative_to(ROOT).as_posix(),
        "bytes": 1_496,
        "sha256": REVIEW_SHA256,
    }
    assert REVIEW.stat().st_size == 1_496
    assert sha(REVIEW) == REVIEW_SHA256
    review = read(REVIEW)
    assert review["decision"] == "PASS"
    assert review["planner_commit"] == PLANNER_COMMIT
    assert review["plan_semantic_sha256"] == PLAN_SHA256
    assert set(review["checks"].values()) == {True}


def test_all_candidate_branches_are_completed_and_selected_plan_is_exact() -> None:
    report = read(REPORT)
    candidates = {item["candidate_id"]: item for item in report["candidate_evaluation"]}
    assert candidates["direct-kaggle-five-million-single-session"]["decision"] == "REJECT"
    assert candidates["direct-modal-main-training"]["decision"] == "REJECT"
    assert candidates["staged-kaggle-t4x2-million-choice-chunks"]["decision"] == "SELECT"
    assert report["selected_plan"]["declared_seeds"] == [
        3559096134,
        178618376,
        3063530691,
    ]
    assert report["selected_plan"]["canary_seed"] == 290023920
    assert report["work_order"]["topology_canary"] == {
        "counts_toward_g3b_budget": False,
        "total_non_forced_choices": 100_000,
        "layout_trials": 2,
        "choices_per_layout": 50_000,
        "minimum_non_forced_choices_per_second": 35.0,
        "checkpoint_reused_for_broad_screen": False,
    }
    assert report["work_order"]["broad_screen"]["non_forced_choices_per_seed"] == 1_000_000
    assert report["work_order"]["competence_confirmation"][
        "cumulative_non_forced_choices_per_seed"
    ] == 5_000_000
    assert report["configuration_control"]["only_changed_factor"] == "opponent schedule"


def test_runtime_evaluation_and_checkpoint_design_are_evidence_bound() -> None:
    report = read(REPORT)
    runtime = report["runtime_evidence"]
    assert runtime["meaningful_choices"] == 1_156_383
    assert runtime["runner_wall_seconds"] == 5058.581121050001
    assert runtime["measured_inference_only_choices_per_second"] == 228.59829116666842
    assert runtime["one_million_hours_at_25_percent_rate"] == 4.860539881730842
    assert runtime["five_million_hours_at_25_percent_rate"] == 24.30269940865421
    assert runtime["one_million_seconds_at_minimum_rate"] < runtime[
        "chunk_internal_wall_cap_seconds"
    ]
    evaluation = report["evaluation_design"]
    assert evaluation["balanced_player_slots"] is True
    assert evaluation["games_per_seed_per_population"] == 400
    assert evaluation["games_per_player_slot_per_seed_per_population"] == 200
    assert evaluation["total_games_per_population"] == 1200
    assert evaluation["total_games_per_cycle"] == 6000
    assert evaluation["random_anchor_in_rule_aggregate"] is False
    assert evaluation["rule_anchor_aggregate_weights"] == [0.25, 0.25, 0.25, 0.25]
    assert report["statistical_size_probe"][
        "promotion_decisions_must_recalculate_from_actual_win_draw_loss_counts"
    ] is True
    checkpoint = report["checkpoint_contract"]
    assert checkpoint["fresh_process_resume_canary_after_choices"] == 50_000
    assert checkpoint["torch_cuda_rng_required"] is True
    assert checkpoint["remote_publication_requires_byte_hash_verification"] is True


def test_negative_attempts_and_edge_cases_are_retained() -> None:
    report = read(REPORT)
    attempts = {item["attempt"]: item for item in report["completed_negative_results"]}
    assert set(attempts) == {
        "assumed_native_library_filename",
        "system_python_posterior_probe",
        "wrong_working_directory_posterior_probe",
        "implicit_external_review_source_path",
    }
    assert set(item["result"] for item in attempts.values()) == {"FAILED_CLOSED"}
    validation = report["edge_case_validation"]
    assert validation["targeted_tests_passed"] == 27
    assert validation["complete_g3_tests_passed"] == 201
    assert validation["complete_python_tests_passed"] == 404
    assert validation["ruff"] == "PASS"
    promotion = report["promotion_validation"]
    assert promotion["targeted_plan_and_report_tests"] == {"passed": 33, "failed": 0}
    assert promotion["complete_g3_tests"] == {"passed": 207, "failed": 0}
    assert promotion["complete_python_suite"] == {"passed": 410, "failed": 0}
    assert promotion["ruff"] == "PASS"
    assert promotion["dashboard_rebuild"] == {
        "ingested": 124,
        "quarantined": 0,
        "status": "PASS",
    }
    assert promotion["dashboard_doctor"] == "PASS"
    assert promotion["frontend_unit_tests"] == {"passed": 7, "failed": 0}
    assert promotion["frontend_build"] == "PASS"
    assert promotion["browser_tests"] == {"passed": 4, "failed": 0}
    assert "authorization escalation" in validation["covered"]
    assert "path traversal and symlink assets" in validation["covered"]
    assert "random anchor aggregate inflation" in validation["covered"]
    assert "review output collision" in validation["covered"]


def test_gate_and_tasks_preserve_blocked_integration_and_launch_boundaries() -> None:
    gate = read(GATE)
    assert gate["status"] == "BLOCKED"
    assert gate["decision"] == "NOT_REVIEWED"
    checks = {item["name"]: item for item in gate["technical_checks"]}
    assert checks["independent frozen-plan review"]["status"] == "PASS"
    assert checks["CABT actor learner bridge implemented and independently qualified"][
        "status"
    ] == "BLOCKED"
    assert checks["private T4x2 topology and resume canary"]["status"] == "BLOCKED"
    assert checks["three-seed one-million-choice broad screen"]["status"] == "BLOCKED"
    assert checks["three-seed five-million-choice competence confirmation"][
        "status"
    ] == "BLOCKED"
    assert len(gate["blockers"]) == 2
    assert "Implement and independently qualify" in gate["approved_next_action"]

    tasks = {item["task_id"]: item for item in read(TASKS)}
    plan_task = tasks["T-G3B-PLAN-001"]
    assert plan_task["status"] == "SUCCEEDED"
    assert plan_task["planner_commit"] == PLANNER_COMMIT
    assert plan_task["planner_tree"] == PLANNER_TREE
    assert plan_task["config_sha256"] == PLAN_SHA256
    assert plan_task["independent_review_sha256"] == REVIEW_SHA256
    assert plan_task["training_launched"] is False
    assert plan_task["external_service_mutated"] is False
    assert plan_task["policy_competence_claimed"] is False
    assert plan_task["completion_evidence"] == REPORT.relative_to(ROOT).as_posix()
    assert plan_task["completion_evidence_sha256"] == sha(REPORT)

    integration = tasks["T-G3B-INTEGRATION-001"]
    assert integration["status"] == "PLANNED"
    assert integration["meaningful_training_allowed"] is False
    assert integration["cloud_launch_allowed"] is False
    assert integration["local_cabt_training_choices_allowed"] == 0


def test_hypothesis_event_and_status_documents_are_current_without_overclaim() -> None:
    hypotheses = {item["hypothesis_id"]: item for item in read(HYPOTHESES)}
    h003 = hypotheses["H003"]
    assert h003["status"] == "ACTIVE"
    assert "No CABT actor/learner bridge" in h003["evidence_against"]
    assert "without meaningful training" in h003["next_test"]

    events = read(EVENTS)
    assert len(events) == 1
    event = events[0]
    assert event["status_after"] == "BLOCKED"
    assert event["source_path"] == REPORT.relative_to(ROOT).as_posix()
    assert "No G3b launch is authorized" in event["summary"]

    agents = (ROOT.parent / "AGENTS.md").read_text(encoding="utf-8")
    project = (ROOT / "PROJECT_STATUS.md").read_text(encoding="utf-8")
    progress = (ROOT / "PROGRESS_REPORT.md").read_text(encoding="utf-8")
    assert "`G3b`: `BLOCKED / NOT_REVIEWED`" in agents
    assert "G3b BLOCKED / NOT_REVIEWED" in project
    assert "Current verdict: **G3a SUCCEEDED / PASS; G3b BLOCKED / NOT_REVIEWED**" in progress
    assert "No notebook, dataset, model, canary or training run was created or launched." in progress
    assert "zero meaningful training" in project
