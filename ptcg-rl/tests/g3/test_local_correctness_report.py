from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPORT = "reports/artifacts/g3a-ppo-local-correctness-v1.json"
REVIEW = "reports/artifacts/g3a-ppo-local-correctness-review-v1.json"
REPORT_SHA256 = "868fdd277eeafe96d09138f1a0f70bc50899fd58ee03b49a1fe6d8a3c9f4194e"
SOURCE_COMMIT = "cae42da47bc9f3491869e8afd0e1254061b9f585"


def load(root: Path, relative: str):
    return json.loads((root / relative).read_text(encoding="utf-8"))


def test_local_correctness_report_is_hash_bound_dashboard_valid_and_non_authorizing() -> None:
    root = Path(__file__).resolve().parents[2]
    raw = (root / REPORT).read_bytes()
    report = json.loads(raw)
    assert len(raw) == 27889
    assert hashlib.sha256(raw).hexdigest() == REPORT_SHA256
    assert report["schema_version"] == 1
    assert report["record_id"] == "artifact-g3a-ppo-local-correctness-v1"
    assert report["created_at_utc"] == "2026-07-22T10:24:05Z"
    assert report["source_path"] == REPORT
    assert report["producer"] == "g3a-local-correctness-runner"
    assert report["run_id"] == "g3a-local-correctness-v1-cae42da47bc9"
    assert report["status"] == "SUCCEEDED"
    assert report["decision"] == "PASS"
    assert report["source_commit"] == SOURCE_COMMIT
    assert report["git"] == {
        "head": SOURCE_COMMIT,
        "clean_before_run": True,
        "status_sha256": hashlib.sha256(b"").hexdigest(),
    }
    assert report["resources"]["device"] == "cpu"
    assert report["resources"]["maximum_cpu_threads"] == 2
    assert report["resources"]["maximum_worker_processes"] == 0
    assert report["resources"]["torch_threads_observed"] == 2
    assert report["resources"]["torch_interop_threads_observed"] == 1
    assert report["cabt_games"] == 0
    assert report["training_launch_authorized"] is False
    assert report["external_service_mutated"] is False
    assert report["authorization"] == {
        "cabt_games_allowed": False,
        "cloud_launch_allowed": False,
        "meaningful_self_play_allowed": False,
        "policy_strength_claim_allowed": False,
    }
    config = report["config"]
    config_path = root / config["path"]
    assert config_path.stat().st_size == config["bytes"]
    assert hashlib.sha256(config_path.read_bytes()).hexdigest() == config["sha256"]
    for record in report["source_files"]:
        path = root / record["path"]
        assert path.stat().st_size == record["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]


def test_candidate_selection_and_all_declared_seed_results_recalculate_exactly() -> None:
    root = Path(__file__).resolve().parents[2]
    report = load(root, REPORT)
    dispositions = {item["candidate_id"]: item for item in report["candidate_dispositions"]}
    assert dispositions["a-512-lr5e3"]["passes"] is False
    assert dispositions["a-512-lr5e3"]["variable_option_multiselect_score"] == 0.75
    assert dispositions["b-1024-lr5e3"]["passes"] is True
    assert dispositions["b-1024-lr5e3"]["selected"] is True
    assert dispositions["c-1024-lr1e2"]["passes"] is True
    assert dispositions["b-1024-lr5e3"]["maximum_gradient_norm_before_clip"] < dispositions[
        "c-1024-lr1e2"
    ]["maximum_gradient_norm_before_clip"]
    assert report["all_selected_seeds_pass"] is True
    assert {run["runs"]["masked-bandit-v1"]["seed"] for run in report["selected_seed_runs"]} == {
        1197953491,
        20344180,
        1491619630,
    }
    for run in report["selected_seed_runs"]:
        records = run["runs"]
        assert records["masked-bandit-v1"]["final_score"] == 1.0
        assert records["variable-option-multiselect-v1"]["final_score"] == 1.0
        assert records["recurrent-cue-v1"]["final_score"] == 1.0
        assert records["recurrent-cue-v1-stateless"]["final_score"] == 0.5
        assert run["recurrent_margin"] == 0.5
        for record in records.values():
            assert record["maximum_probability_replay_error"] == 0.0
            assert record["maximum_initial_ratio_error"] == 0.0
            assert record["zero_tolerance_total"] == 0
            assert record["checkpoint"]["status"] == "PASS"
            assert record["checkpoint"]["fixed_evaluation_exact"] is True
            assert record["checkpoint"]["model_tensors_exact"] is True
            assert record["checkpoint"]["restored_rng_states"] == [
                "python",
                "numpy",
                "torch_cpu",
            ]


def test_independent_review_and_gate_preserve_cloud_blocker() -> None:
    root = Path(__file__).resolve().parents[2]
    review = load(root, REVIEW)
    gate = load(root, "reports/gates/g3a.json")
    tasks = load(root, "reports/tasks/current.json")
    assert review["decision"] == "PASS"
    assert review["reviewed_artifact"]["sha256"] == REPORT_SHA256
    assert review["reviewed_artifact"]["bytes"] == 27889
    assert review["overall_independent_recalculation"] == "PASS"
    assert review["identity_review"]["dashboard_envelope_complete"] is True
    assert review["identity_review"]["clean_worktree_before_run"] is True
    assert review["identity_review"]["source_hash_mismatches"] == 0
    assert all(item["status"] == "PASS" for item in review["selected_seed_recalculation"])
    assert review["resource_review"]["cabt_games"] == 0
    assert review["authorization_review"]["training_launch_authorized"] is False
    promotion = review["promotion_validation"]
    assert promotion["focused_g3_tests"] == {"passed": 144, "failed": 0}
    assert promotion["full_python_suite"] == {"passed": 347, "failed": 0}
    assert promotion["ruff"] == "PASS"
    assert promotion["dashboard_rebuild"] == {
        "ingested": 111,
        "quarantined": 0,
        "status": "PASS",
    }
    assert promotion["dashboard_doctor"] == "PASS"
    assert promotion["frontend_unit_tests"] == {"passed": 7, "failed": 0}
    assert promotion["frontend_build"] == "PASS"
    assert promotion["browser_tests"] == {"passed": 4, "failed": 0}
    assert promotion["tracked_browser_artifacts_restored"] == 4
    assert gate["status"] == "BLOCKED"
    assert gate["decision"] == "NOT_REVIEWED"
    assert len(gate["blockers"]) == 1
    checks = {item["name"]: item for item in gate["technical_checks"]}
    assert checks["PPO correctness harness and versioned toy task implementations"]["status"] == "PASS"
    assert checks["bounded three-seed private correctness smoke"]["status"] == "BLOCKED"
    smoke = next(item for item in tasks if item.get("task_id") == "T-G3-001")
    assert smoke["status"] == "BLOCKED"
    assert "G3A_CLOUD_PLAN_FROZEN" in smoke["depends_on"]
    assert "USER_TRAINING_APPROVAL" in smoke["depends_on"]
