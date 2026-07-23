from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

import ptcg_rl.g3.competence_plan as competence
from ptcg_rl.g3.competence_plan import (
    CANARY_SEED,
    DECLARED_SEEDS,
    EVIDENCE_BASE_COMMIT,
    PLAN_ID,
    CompetencePlanError,
    canonical_json_bytes,
    derive_seed,
    expected_competence_plan,
    load_competence_plan,
    review_competence_plan,
    semantic_sha256,
    validate_competence_plan,
)

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "configs/g3b_competence_plan_v1.json"
SCRIPT = ROOT / "scripts/g3b_plan_review.py"
PLAN_SHA256 = "99cf090df232ffe37504eee4b86ab70554256b5ad89fe972bb9bb5033115bc26"


def frozen() -> dict:
    return copy.deepcopy(expected_competence_plan())


def validate_as_expected(monkeypatch: pytest.MonkeyPatch, value: dict) -> None:
    monkeypatch.setattr(competence, "expected_competence_plan", lambda: copy.deepcopy(value))
    validate_competence_plan(value, ROOT)


def test_plan_is_canonical_exact_and_all_private_assets_verify() -> None:
    expected = expected_competence_plan()
    raw = PLAN.read_bytes()
    assert raw == canonical_json_bytes(expected)
    loaded = load_competence_plan(PLAN, ROOT)
    assert loaded.value == expected
    assert loaded.semantic_sha256 == PLAN_SHA256
    assert semantic_sha256(expected) == PLAN_SHA256
    assert expected["evidence_base"]["commit"] == EVIDENCE_BASE_COMMIT
    assert expected["selected_candidate_id"] == "staged-kaggle-t4x2-million-choice-chunks"
    assert expected["authorization"] == {
        "training_launch_authorized": False,
        "external_service_mutation_authorized": False,
        "modal_execution_authorized": False,
        "deck_freeze_authorized": False,
        "submission_authorized": False,
    }


def test_seed_derivation_is_exact_unique_and_separate() -> None:
    assert tuple(derive_seed(f"{PLAN_ID}/seed/{index}") for index in range(3)) == DECLARED_SEEDS
    assert derive_seed(f"{PLAN_ID}/canary") == CANARY_SEED
    assert len(set((*DECLARED_SEEDS, CANARY_SEED))) == 4


def test_candidate_branches_and_runtime_choice_are_complete() -> None:
    plan = expected_competence_plan()
    candidates = {item["candidate_id"]: item for item in plan["candidate_comparison"]}
    assert candidates["direct-kaggle-five-million-single-session"]["decision"] == "REJECT"
    assert candidates["direct-modal-main-training"]["decision"] == "REJECT"
    assert candidates["staged-kaggle-t4x2-million-choice-chunks"]["decision"] == "SELECT"
    canary = next(stage for stage in plan["stages"] if stage["stage_id"] == "topology-canary")
    assert [item["non_forced_choices"] for item in canary["layout_trials"]] == [50_000, 50_000]
    assert sum(item["non_forced_choices"] for item in canary["layout_trials"]) == 100_000
    runtime = plan["runtime_basis"]
    assert runtime["one_million_seconds_at_minimum_rate"] == pytest.approx(1_000_000 / 35.0)
    assert runtime["one_million_seconds_at_minimum_rate"] < plan["platform"][
        "chunk_internal_wall_cap_seconds"
    ]
    assert runtime["five_million_fits_chunk_cap"] is False


def test_primary_and_diagnosis_change_only_preregistered_opponent_schedule() -> None:
    plan = expected_competence_plan()
    primary = plan["configurations"]["primary"]
    alternative = plan["configurations"]["diagnosis_alternative"]
    ignored_primary = {"configuration_id", "opponent_schedule"}
    ignored_alternative = {
        "configuration_id",
        "opponent_schedule",
        "invocation",
        "single_preregistered_factor_changed",
    }
    assert {key: value for key, value in primary.items() if key not in ignored_primary} == {
        key: value for key, value in alternative.items() if key not in ignored_alternative
    }
    assert alternative["single_preregistered_factor_changed"] == "opponent_schedule"
    for configuration in (primary, alternative):
        for period in configuration["opponent_schedule"]:
            assert sum(period["weights"].values()) == pytest.approx(1.0)
            assert all(weight > 0 for weight in period["weights"].values())


def test_fixed_evaluation_exceeds_minimum_and_balances_every_slot() -> None:
    plan = expected_competence_plan()
    evaluation = plan["evaluation"]
    assert evaluation["games_per_seed_per_population"] == 400
    assert evaluation["learner_slot_zero_games_per_seed_per_population"] == 200
    assert evaluation["learner_slot_one_games_per_seed_per_population"] == 200
    assert evaluation["total_games_per_population"] == 1200
    assert evaluation["total_games_per_population"] >= plan["contract"]["g3b"][
        "random_anchor_minimum_games"
    ]
    assert evaluation["total_games_per_cycle"] == 6000
    assert "random-engineering-deck" not in evaluation["aggregate_population"]
    assert sum(evaluation["aggregate_weights"].values()) == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value["authorization"].__setitem__("training_launch_authorized", True), "differs"),
        (lambda value: value.__setitem__("selected_candidate_id", "direct-modal-main-training"), "differs"),
        (lambda value: value["seeds"].__setitem__("canary", DECLARED_SEEDS[0]), "differs"),
        (
            lambda value: value["contract"]["g3b"].__setitem__(
                "aggregate_lower_bound_strictly_greater_than", 0.50
            ),
            "differs",
        ),
        (
            lambda value: next(
                stage for stage in value["stages"] if stage["stage_id"] == "broad-screen"
            ).__setitem__("non_forced_choices_per_seed", 999_999),
            "differs",
        ),
        (
            lambda value: value["evaluation"].__setitem__("games_per_seed_per_population", 399),
            "differs",
        ),
        (
            lambda value: value["evaluation"]["aggregate_population"].append(
                "random-engineering-deck"
            ),
            "differs",
        ),
        (
            lambda value: value["checkpoint"]["required_components"].remove("torch_cuda_rng"),
            "differs",
        ),
        (
            lambda value: value["stop_conditions"].remove("probability_replay_mismatch"),
            "differs",
        ),
        (
            lambda value: value["platform"].__setitem__("internet", True),
            "differs",
        ),
    ],
)
def test_any_frozen_plan_mutation_fails_closed(tmp_path: Path, mutation, message: str) -> None:
    value = frozen()
    mutation(value)
    path = tmp_path / "mutated.json"
    path.write_bytes(canonical_json_bytes(value))
    with pytest.raises(CompetencePlanError, match=message):
        load_competence_plan(path, ROOT)


def test_duplicate_json_keys_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.json"
    path.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
    with pytest.raises(CompetencePlanError, match="duplicate JSON key"):
        competence.load_json_object(path)


def test_path_traversal_is_rejected_after_exact_plan_override(monkeypatch: pytest.MonkeyPatch) -> None:
    value = frozen()
    value["assets"]["native_engine"]["path"] = "../outside.so"
    monkeypatch.setattr(competence, "expected_competence_plan", lambda: copy.deepcopy(value))
    with pytest.raises(CompetencePlanError, match="safe repository-relative"):
        validate_competence_plan(value, ROOT)


def test_symlink_asset_is_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target.bin"
    target.write_bytes(b"safe")
    link = tmp_path / "link.bin"
    link.symlink_to(target)
    record = {
        "path": "link.bin",
        "bytes": 4,
        "sha256": "8b3369944dd2a3fab39e32d1aeb1f6d9a0b8b0d47b9f4a21b229025a4a9f74b8",
    }
    with pytest.raises(CompetencePlanError, match="non-symlink"):
        competence._verify_file(tmp_path, record)


def test_contract_threshold_drift_is_rejected_after_exact_plan_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = frozen()
    value["contract"]["g3b"]["minimum_seed_point_estimate"] = 0.49
    monkeypatch.setattr(competence, "expected_competence_plan", lambda: copy.deepcopy(value))
    with pytest.raises(CompetencePlanError, match="thresholds differ"):
        validate_competence_plan(value, ROOT)


def test_diagnosis_change_beyond_opponent_schedule_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = frozen()
    value["configurations"]["diagnosis_alternative"]["learning_rate"] = 1e-4
    monkeypatch.setattr(competence, "expected_competence_plan", lambda: copy.deepcopy(value))
    with pytest.raises(CompetencePlanError, match="more than opponent schedule"):
        validate_competence_plan(value, ROOT)


def test_opponent_weight_drift_and_zero_weight_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = frozen()
    weights = value["configurations"]["primary"]["opponent_schedule"][0]["weights"]
    weights["random-engineering-deck"] = 0.0
    weights["rule-dragapult-ex"] = 0.4
    monkeypatch.setattr(competence, "expected_competence_plan", lambda: copy.deepcopy(value))
    with pytest.raises(CompetencePlanError, match="positive probability"):
        validate_competence_plan(value, ROOT)


def test_confirmation_chunk_arithmetic_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    value = frozen()
    confirmation = next(
        stage for stage in value["stages"] if stage["stage_id"] == "competence-confirmation"
    )
    confirmation["cumulative_chunks_per_seed"] = 4
    monkeypatch.setattr(competence, "expected_competence_plan", lambda: copy.deepcopy(value))
    with pytest.raises(CompetencePlanError, match="chunk arithmetic"):
        validate_competence_plan(value, ROOT)


def test_unbalanced_or_undersized_evaluation_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    value = frozen()
    evaluation = value["evaluation"]
    evaluation["games_per_seed_per_population"] = 300
    evaluation["learner_slot_zero_games_per_seed_per_population"] = 200
    evaluation["learner_slot_one_games_per_seed_per_population"] = 100
    evaluation["total_games_per_population"] = 900
    monkeypatch.setattr(competence, "expected_competence_plan", lambda: copy.deepcopy(value))
    with pytest.raises(CompetencePlanError, match="undersized"):
        validate_competence_plan(value, ROOT)


def test_random_anchor_cannot_enter_aggregate(monkeypatch: pytest.MonkeyPatch) -> None:
    value = frozen()
    evaluation = value["evaluation"]
    evaluation["aggregate_population"] = [
        "random-engineering-deck",
        "rule-dragapult-ex",
        "rule-iono",
        "rule-mega-abomasnow-ex",
    ]
    evaluation["aggregate_weights"] = {
        name: 0.25 for name in evaluation["aggregate_population"]
    }
    monkeypatch.setattr(competence, "expected_competence_plan", lambda: copy.deepcopy(value))
    with pytest.raises(CompetencePlanError, match="must not inflate"):
        validate_competence_plan(value, ROOT)


def test_runtime_floor_must_fit_chunk_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    value = frozen()
    value["platform"]["chunk_internal_wall_cap_seconds"] = 28_000
    monkeypatch.setattr(competence, "expected_competence_plan", lambda: copy.deepcopy(value))
    with pytest.raises(CompetencePlanError, match="does not fit"):
        validate_competence_plan(value, ROOT)


def test_review_is_dashboard_valid_non_authorizing_and_hash_bound() -> None:
    loaded = load_competence_plan(PLAN, ROOT)
    review = review_competence_plan(
        loaded,
        created_at_utc="2026-07-23T11:30:00Z",
        source_path="reports/artifacts/g3b-competence-plan-review-v1.json",
        planner_commit=EVIDENCE_BASE_COMMIT,
    )
    assert review["status"] == "SUCCEEDED"
    assert review["decision"] == "PASS"
    assert review["plan_semantic_sha256"] == PLAN_SHA256
    assert review["selected_candidate_id"] == "staged-kaggle-t4x2-million-choice-chunks"
    assert set(review["checks"].values()) == {True}
    assert review["training_launch_authorized"] is False
    assert review["external_service_mutated"] is False
    assert review["policy_competence_claimed"] is False


def test_standalone_review_writes_once_and_refuses_collision(tmp_path: Path) -> None:
    output = tmp_path / "review.json"
    command = [
        sys.executable,
        str(SCRIPT),
        "--plan",
        str(PLAN),
        "--repo",
        str(ROOT),
        "--planner-commit",
        EVIDENCE_BASE_COMMIT,
        "--created-at-utc",
        "2026-07-23T11:30:00Z",
        "--source-path",
        "reports/artifacts/g3b-competence-plan-review-v1.json",
        "--output",
        str(output),
    ]
    first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    assert first.returncode == 0, first.stderr
    written = json.loads(output.read_text(encoding="utf-8"))
    assert written["decision"] == "PASS"
    second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    assert second.returncode != 0
    assert "already exists" in second.stderr
