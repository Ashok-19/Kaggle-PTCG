from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from ptcg_rl.g3.evaluation import (
    CONTRACT_ID,
    ZERO_TOLERANCE_COUNTERS,
    EvaluationContractError,
    LoadedEvaluationContract,
    derive_declared_seeds,
    expected_evaluation_contract,
    load_evaluation_contract,
    load_json_object,
    review_g3a_evidence,
    validate_evaluation_contract,
)

HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64
HASH_E = "e" * 64
SOURCE_COMMIT = "1" * 40


def contract_path() -> Path:
    return Path(__file__).resolve().parents[2] / "configs/g3a_evaluation_v1.json"


@pytest.fixture
def loaded_contract() -> LoadedEvaluationContract:
    return load_evaluation_contract(contract_path())


def task_result(task_id: str) -> dict[str, object]:
    result: dict[str, object] = {
        "status": "PASS",
        "task_contract_sha256": HASH_A,
        "metrics_sha256": HASH_B,
        "choices": 8_000,
        "evaluation_cases": 512,
        "failed_cases": 0,
    }
    if task_id == "recurrent-cue-v1":
        result.update(
            {
                "recurrent_score": 0.90,
                "stateless_score": 0.50,
                "margin_vs_stateless": 0.40,
            }
        )
    return result


def valid_evidence(contract: LoadedEvaluationContract) -> dict[str, object]:
    seed_records = []
    for seed in derive_declared_seeds():
        seed_records.append(
            {
                "seed": seed,
                "tasks": {
                    "masked-bandit-v1": task_result("masked-bandit-v1"),
                    "recurrent-cue-v1": task_result("recurrent-cue-v1"),
                    "variable-option-multiselect-v1": task_result(
                        "variable-option-multiselect-v1"
                    ),
                },
                "probability_replay": {
                    "checked_before_first_update": True,
                    "old_compound_log_probability_max_abs_error": 0.00001,
                    "initial_ratio_max_abs_error_from_one": 0.00001,
                },
                "zero_tolerance": {name: 0 for name in ZERO_TOLERANCE_COUNTERS},
                "checkpoint_resume": {
                    "status": "PASS",
                    "components": {
                        "counters": True,
                        "league": True,
                        "model": True,
                        "optimizer": True,
                        "rollout_boundary": True,
                        "scheduler_or_scaler": True,
                    },
                    "available_rng_states": ["numpy", "python", "torch_cpu"],
                    "restored_rng_states": ["numpy", "python", "torch_cpu"],
                    "fixed_tensor_max_abs_diff": 0.00001,
                    "fixed_tensor_rtol": 0.0,
                },
            }
        )
    return {
        "schema_version": 1,
        "contract_id": CONTRACT_ID,
        "contract_file_sha256": contract.file_sha256,
        "run_id": "g3a-unit-proof-v1",
        "source_commit": SOURCE_COMMIT,
        "status": "SUCCEEDED",
        "authorization": {
            "user_training_approval": True,
            "private_bounded_run": True,
            "platform": "kaggle",
            "modal_used": False,
            "submission_created": False,
        },
        "budget": {
            "declared_before_run": True,
            "non_forced_choices_per_seed": [25_000, 25_000, 25_000],
            "task_allocation_sha256": HASH_C,
            "budget_manifest_sha256": HASH_D,
        },
        "seeds": seed_records,
        "artifacts": {
            "run_manifest_path": "runs/g3a-unit-proof-v1/manifest.json",
            "run_manifest_sha256": HASH_A,
            "metrics_sha256": HASH_B,
            "checkpoint_manifest_sha256": HASH_C,
            "independent_review_sha256": HASH_D,
        },
        "claim": {
            "algorithm_proof_only": True,
            "policy_strength_claimed": False,
        },
    }


def review(contract: LoadedEvaluationContract, evidence: dict[str, object]) -> dict[str, object]:
    return review_g3a_evidence(contract, evidence)


def test_frozen_contract_matches_exact_implementation_and_seed_derivation(
    loaded_contract: LoadedEvaluationContract,
) -> None:
    assert loaded_contract.value == expected_evaluation_contract()
    assert validate_evaluation_contract(loaded_contract.value) == loaded_contract.value
    assert loaded_contract.file_sha256 == (
        "51f5d0d800a0a3832cc0ea8873828f6c68262eb4f24e55a8b11ae4143a2dae72"
    )
    assert loaded_contract.semantic_sha256 == (
        "bd3e0e6b5331fe6f6028df65403ecf2446250ebb8f375961544de26cf0ffc3b6"
    )
    assert derive_declared_seeds() == [1197953491, 20344180, 1491619630]
    assert loaded_contract.value["authorization"]["training_authorized"] is False
    assert loaded_contract.value["randomness"]["paired_engine_seeds_claimed"] is False
    assert loaded_contract.value["future_strength"]["forbid_blended_score"] is True
    assert loaded_contract.value["future_strength"]["promotion_order"] == [
        "contract_and_reliability",
        "catastrophic_matchup_floors",
        "meta_weighted_strength",
        "runtime_and_package",
        "exploiter_defense",
    ]


@pytest.mark.parametrize("count", [0, -1, 33, True, 1.5])
def test_seed_derivation_rejects_invalid_counts(count: object) -> None:
    with pytest.raises(EvaluationContractError, match="seed count"):
        derive_declared_seeds(count=count)  # type: ignore[arg-type]


@pytest.mark.parametrize("namespace", ["", None, 7])
def test_seed_derivation_rejects_invalid_namespaces(namespace: object) -> None:
    with pytest.raises(EvaluationContractError, match="namespace"):
        derive_declared_seeds(namespace=namespace)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("mutator", "message"),
    [
        (lambda value: value.pop("future_strength"), "keys differ"),
        (lambda value: value.__setitem__("unexpected", True), "keys differ"),
        (
            lambda value: value["authorization"].__setitem__("training_authorized", True),
            "training_authorized",
        ),
        (
            lambda value: value["randomness"].__setitem__("paired_engine_seeds_claimed", True),
            "paired_engine_seeds_claimed",
        ),
        (
            lambda value: value["g3a"]["probability_replay"].__setitem__(
                "maximum_initial_ratio_absolute_error_from_one", 0.001
            ),
            "maximum_initial_ratio",
        ),
        (
            lambda value: value["future_strength"]["g3b"].__setitem__(
                "aggregate_lower_bound_strictly_greater_than", 0.50
            ),
            "aggregate_lower_bound",
        ),
        (
            lambda value: value["future_strength"].__setitem__("forbid_blended_score", False),
            "forbid_blended_score",
        ),
    ],
)
def test_contract_mutations_fail_closed(mutator, message: str) -> None:
    value = expected_evaluation_contract()
    mutator(value)
    with pytest.raises(EvaluationContractError, match=message):
        validate_evaluation_contract(value)


def test_json_loader_rejects_duplicate_keys_non_object_and_nonfinite(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"a":1,"a":2}\n', encoding="utf-8")
    with pytest.raises(EvaluationContractError, match="duplicate key"):
        load_json_object(duplicate)
    array = tmp_path / "array.json"
    array.write_text("[]\n", encoding="utf-8")
    with pytest.raises(EvaluationContractError, match="root must be an object"):
        load_json_object(array)
    nonfinite = tmp_path / "nonfinite.json"
    nonfinite.write_text('{"x":NaN}\n', encoding="utf-8")
    with pytest.raises(EvaluationContractError, match="canonical JSON"):
        load_json_object(nonfinite)


def test_valid_evidence_passes_at_all_inclusive_tolerance_boundaries(
    loaded_contract: LoadedEvaluationContract,
) -> None:
    result = review(loaded_contract, valid_evidence(loaded_contract))
    assert result["status"] == "SUCCEEDED"
    assert result["decision"] == "PASS"
    assert result["failures"] == []
    assert result["declared_seeds"] == derive_declared_seeds()
    assert result["reviewed_seed_count"] == 3
    assert all(item["status"] == "PASS" for item in result["seed_summaries"])
    assert result["algorithm_proof_only"] is True
    assert result["policy_strength_established"] is False


@pytest.mark.parametrize(
    "task_id",
    ["masked-bandit-v1", "recurrent-cue-v1", "variable-option-multiselect-v1"],
)
def test_every_task_must_pass_in_every_seed(
    loaded_contract: LoadedEvaluationContract, task_id: str
) -> None:
    evidence = valid_evidence(loaded_contract)
    evidence["seeds"][1]["tasks"][task_id]["status"] = "FAIL"  # type: ignore[index]
    result = review(loaded_contract, evidence)
    assert result["decision"] == "FAIL"
    assert any(task_id in failure for failure in result["failures"])


@pytest.mark.parametrize("failed_cases", [1, 5])
def test_task_failed_evaluation_cases_block_pass(
    loaded_contract: LoadedEvaluationContract, failed_cases: int
) -> None:
    evidence = valid_evidence(loaded_contract)
    evidence["seeds"][0]["tasks"]["masked-bandit-v1"]["failed_cases"] = failed_cases  # type: ignore[index]
    result = review(loaded_contract, evidence)
    assert result["decision"] == "FAIL"
    assert any("failed evaluation cases" in failure for failure in result["failures"])


@pytest.mark.parametrize(
    ("recurrent", "stateless", "margin", "passes"),
    [
        (0.85, 0.60, 0.25, True),
        (0.849999, 0.50, 0.349999, False),
        (0.90, 0.650001, 0.249999, False),
        (1.0, 0.5, 0.5, True),
    ],
)
def test_recurrent_score_and_margin_boundaries(
    loaded_contract: LoadedEvaluationContract,
    recurrent: float,
    stateless: float,
    margin: float,
    passes: bool,
) -> None:
    evidence = valid_evidence(loaded_contract)
    task = evidence["seeds"][0]["tasks"]["recurrent-cue-v1"]  # type: ignore[index]
    task["recurrent_score"] = recurrent
    task["stateless_score"] = stateless
    task["margin_vs_stateless"] = margin
    result = review(loaded_contract, evidence)
    assert (result["decision"] == "PASS") is passes


def test_recurrent_margin_must_be_arithmetically_consistent(
    loaded_contract: LoadedEvaluationContract,
) -> None:
    evidence = valid_evidence(loaded_contract)
    evidence["seeds"][0]["tasks"]["recurrent-cue-v1"]["margin_vs_stateless"] = 0.39  # type: ignore[index]
    with pytest.raises(EvaluationContractError, match="arithmetically inconsistent"):
        review(loaded_contract, evidence)


@pytest.mark.parametrize(
    ("field", "value", "passes"),
    [
        ("old_compound_log_probability_max_abs_error", 0.00001, True),
        ("old_compound_log_probability_max_abs_error", 0.000010001, False),
        ("initial_ratio_max_abs_error_from_one", 0.00001, True),
        ("initial_ratio_max_abs_error_from_one", 0.000010001, False),
    ],
)
def test_probability_replay_tolerance_boundaries(
    loaded_contract: LoadedEvaluationContract, field: str, value: float, passes: bool
) -> None:
    evidence = valid_evidence(loaded_contract)
    evidence["seeds"][2]["probability_replay"][field] = value  # type: ignore[index]
    result = review(loaded_contract, evidence)
    assert (result["decision"] == "PASS") is passes


def test_probability_replay_must_precede_first_update(
    loaded_contract: LoadedEvaluationContract,
) -> None:
    evidence = valid_evidence(loaded_contract)
    evidence["seeds"][0]["probability_replay"]["checked_before_first_update"] = False  # type: ignore[index]
    result = review(loaded_contract, evidence)
    assert result["decision"] == "FAIL"
    assert any("before the first update" in failure for failure in result["failures"])


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_metrics_are_invalid_evidence(
    loaded_contract: LoadedEvaluationContract, value: float
) -> None:
    evidence = valid_evidence(loaded_contract)
    evidence["seeds"][0]["probability_replay"][
        "old_compound_log_probability_max_abs_error"
    ] = value  # type: ignore[index]
    with pytest.raises(EvaluationContractError, match="finite|canonical JSON"):
        review(loaded_contract, evidence)


@pytest.mark.parametrize("counter", ZERO_TOLERANCE_COUNTERS)
def test_every_zero_tolerance_counter_blocks_on_first_event(
    loaded_contract: LoadedEvaluationContract, counter: str
) -> None:
    evidence = valid_evidence(loaded_contract)
    evidence["seeds"][1]["zero_tolerance"][counter] = 1  # type: ignore[index]
    result = review(loaded_contract, evidence)
    assert result["decision"] == "FAIL"
    assert any(counter in failure for failure in result["failures"])


@pytest.mark.parametrize(
    ("totals", "passes"),
    [
        ([25_000, 25_000, 25_000], True),
        ([100_000, 100_000, 100_000], True),
        ([24_999, 24_999, 24_999], False),
        ([100_001, 100_001, 100_001], False),
        ([25_000, 25_000, 25_001], False),
    ],
)
def test_budget_bounds_and_exact_cross_seed_equality(
    loaded_contract: LoadedEvaluationContract, totals: list[int], passes: bool
) -> None:
    evidence = valid_evidence(loaded_contract)
    evidence["budget"]["non_forced_choices_per_seed"] = totals  # type: ignore[index]
    result = review(loaded_contract, evidence)
    assert (result["decision"] == "PASS") is passes


@pytest.mark.parametrize("component", [
    "counters",
    "league",
    "model",
    "optimizer",
    "rollout_boundary",
    "scheduler_or_scaler",
])
def test_every_checkpoint_component_is_required(
    loaded_contract: LoadedEvaluationContract, component: str
) -> None:
    evidence = valid_evidence(loaded_contract)
    evidence["seeds"][0]["checkpoint_resume"]["components"][component] = False  # type: ignore[index]
    result = review(loaded_contract, evidence)
    assert result["decision"] == "FAIL"
    assert any(component in failure for failure in result["failures"])


@pytest.mark.parametrize(
    ("diff", "rtol", "passes"),
    [(0.00001, 0.0, True), (0.000010001, 0.0, False), (0.0, 1e-9, False)],
)
def test_checkpoint_fixed_tensor_tolerances(
    loaded_contract: LoadedEvaluationContract, diff: float, rtol: float, passes: bool
) -> None:
    evidence = valid_evidence(loaded_contract)
    resume = evidence["seeds"][2]["checkpoint_resume"]  # type: ignore[index]
    resume["fixed_tensor_max_abs_diff"] = diff
    resume["fixed_tensor_rtol"] = rtol
    result = review(loaded_contract, evidence)
    assert (result["decision"] == "PASS") is passes


def test_checkpoint_must_restore_all_available_rng_states(
    loaded_contract: LoadedEvaluationContract,
) -> None:
    evidence = valid_evidence(loaded_contract)
    evidence["seeds"][1]["checkpoint_resume"]["restored_rng_states"] = [  # type: ignore[index]
        "numpy",
        "python",
    ]
    result = review(loaded_contract, evidence)
    assert result["decision"] == "FAIL"
    assert any("every available RNG state" in failure for failure in result["failures"])


@pytest.mark.parametrize(
    "rng_states",
    [[], ["python", "python"], ["torch_cpu", "python"], ["", "python"]],
)
def test_rng_state_lists_must_be_nonempty_sorted_and_unique(
    loaded_contract: LoadedEvaluationContract, rng_states: list[str]
) -> None:
    evidence = valid_evidence(loaded_contract)
    evidence["seeds"][0]["checkpoint_resume"]["available_rng_states"] = rng_states  # type: ignore[index]
    with pytest.raises(EvaluationContractError, match="available RNG states"):
        review(loaded_contract, evidence)


@pytest.mark.parametrize(
    ("field", "value", "failure_text"),
    [
        ("user_training_approval", False, "approval"),
        ("private_bounded_run", False, "private and bounded"),
        ("modal_used", True, "Modal"),
        ("submission_created", True, "submission"),
    ],
)
def test_authorization_boundaries_fail_closed(
    loaded_contract: LoadedEvaluationContract, field: str, value: bool, failure_text: str
) -> None:
    evidence = valid_evidence(loaded_contract)
    evidence["authorization"][field] = value  # type: ignore[index]
    result = review(loaded_contract, evidence)
    assert result["decision"] == "FAIL"
    assert any(failure_text in failure for failure in result["failures"])


@pytest.mark.parametrize("platform", ["local", "modal", "unknown", 3])
def test_only_kaggle_or_colab_is_valid_for_bounded_g3a_run(
    loaded_contract: LoadedEvaluationContract, platform: object
) -> None:
    evidence = valid_evidence(loaded_contract)
    evidence["authorization"]["platform"] = platform  # type: ignore[index]
    result = review(loaded_contract, evidence)
    assert result["decision"] == "FAIL"
    assert any("platform" in failure for failure in result["failures"])


@pytest.mark.parametrize(
    ("algorithm_only", "strength_claimed"),
    [(False, False), (True, True), (False, True)],
)
def test_g3a_cannot_claim_policy_strength(
    loaded_contract: LoadedEvaluationContract,
    algorithm_only: bool,
    strength_claimed: bool,
) -> None:
    evidence = valid_evidence(loaded_contract)
    evidence["claim"] = {
        "algorithm_proof_only": algorithm_only,
        "policy_strength_claimed": strength_claimed,
    }
    result = review(loaded_contract, evidence)
    assert result["decision"] == "FAIL"


def test_seed_identity_order_count_and_duplicates_fail_closed(
    loaded_contract: LoadedEvaluationContract,
) -> None:
    reversed_evidence = valid_evidence(loaded_contract)
    reversed_evidence["seeds"] = list(reversed(reversed_evidence["seeds"]))  # type: ignore[arg-type]
    with pytest.raises(EvaluationContractError, match="seed order/identity"):
        review(loaded_contract, reversed_evidence)

    missing = valid_evidence(loaded_contract)
    missing["seeds"] = missing["seeds"][:2]  # type: ignore[index]
    with pytest.raises(EvaluationContractError, match="exactly three"):
        review(loaded_contract, missing)

    duplicate = valid_evidence(loaded_contract)
    duplicate["seeds"][2]["seed"] = duplicate["seeds"][1]["seed"]  # type: ignore[index]
    with pytest.raises(EvaluationContractError, match="seed order/identity"):
        review(loaded_contract, duplicate)


def test_contract_hash_source_commit_run_id_and_artifact_identity_are_strict(
    loaded_contract: LoadedEvaluationContract,
) -> None:
    cases = []
    wrong_hash = valid_evidence(loaded_contract)
    wrong_hash["contract_file_sha256"] = HASH_E
    cases.append((wrong_hash, "contract file SHA-256"))
    bad_commit = valid_evidence(loaded_contract)
    bad_commit["source_commit"] = "x"
    cases.append((bad_commit, "source commit"))
    bad_run = valid_evidence(loaded_contract)
    bad_run["run_id"] = "x"
    cases.append((bad_run, "run ID"))
    bad_artifact = valid_evidence(loaded_contract)
    bad_artifact["artifacts"]["metrics_sha256"] = "ABC"  # type: ignore[index]
    cases.append((bad_artifact, "SHA-256"))
    unsafe_path = valid_evidence(loaded_contract)
    unsafe_path["artifacts"]["run_manifest_path"] = "../escape.json"  # type: ignore[index]
    cases.append((unsafe_path, "safe canonical"))
    for evidence, message in cases:
        with pytest.raises(EvaluationContractError, match=message):
            review(loaded_contract, evidence)


def test_unknown_or_missing_evidence_fields_are_rejected(
    loaded_contract: LoadedEvaluationContract,
) -> None:
    extra = valid_evidence(loaded_contract)
    extra["unexpected"] = True
    with pytest.raises(EvaluationContractError, match="keys differ"):
        review(loaded_contract, extra)
    missing = valid_evidence(loaded_contract)
    missing.pop("artifacts")
    with pytest.raises(EvaluationContractError, match="keys differ"):
        review(loaded_contract, missing)


def test_valid_but_failed_run_status_returns_fail_not_invalid(
    loaded_contract: LoadedEvaluationContract,
) -> None:
    evidence = valid_evidence(loaded_contract)
    evidence["status"] = "FAILED"
    result = review(loaded_contract, evidence)
    assert result["status"] == "FAILED"
    assert result["decision"] == "FAIL"
    assert result["failures"] == ["G3a run status is not SUCCEEDED"]


def test_evidence_copy_is_not_mutated(loaded_contract: LoadedEvaluationContract) -> None:
    evidence = valid_evidence(loaded_contract)
    before = copy.deepcopy(evidence)
    review(loaded_contract, evidence)
    assert evidence == before


def test_config_file_is_valid_json_without_duplicate_keys() -> None:
    raw = contract_path().read_text(encoding="utf-8")
    assert json.loads(raw) == expected_evaluation_contract()
    assert "REQUIRED" not in raw
