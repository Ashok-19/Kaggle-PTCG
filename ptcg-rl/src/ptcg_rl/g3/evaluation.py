from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

CONTRACT_SCHEMA_VERSION = 1
CONTRACT_ID = "g3a-evaluation-v1"
CONTRACT_KIND = "KPTCG_STRICT_EVALUATION_CONTRACT"
DECISION_PATH = "docs/decisions/DEC-010_G2_R1_AND_STRICT_EVALUATION.md"
DECISION_SHA256 = "c29fdfdfa60720794a825bdb08449da5ae8f7990741fbdad698a3dccab6f86b0"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{2,127}$")
G3A_TASK_IDS = (
    "masked-bandit-v1",
    "recurrent-cue-v1",
    "variable-option-multiselect-v1",
)
ZERO_TOLERANCE_COUNTERS = (
    "crashes",
    "fallbacks",
    "hidden_state_cross_owner_events",
    "invalid_actions",
    "nan_inf",
    "stale_inference_requests",
    "timeouts",
    "unclassified_truncations",
)
REQUIRED_RESUME_COMPONENTS = (
    "counters",
    "league",
    "model",
    "optimizer",
    "rollout_boundary",
    "scheduler_or_scaler",
)


class EvaluationContractError(ValueError):
    pass


@dataclass(frozen=True)
class LoadedEvaluationContract:
    value: dict[str, Any]
    file_sha256: str
    semantic_sha256: str
    bytes: int


def canonical_json_bytes(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise EvaluationContractError(f"value cannot be encoded as canonical JSON: {error}") from error
    return encoded.encode("utf-8") + b"\n"


def contract_semantic_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(dict(value))).hexdigest()


def derive_declared_seeds(namespace: str = CONTRACT_ID, count: int = 3) -> list[int]:
    if not isinstance(namespace, str) or not namespace:
        raise EvaluationContractError("seed namespace must be a nonempty string")
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0 or count > 32:
        raise EvaluationContractError("seed count must be an integer in [1, 32]")
    return [
        int.from_bytes(
            hashlib.sha256(f"{namespace}/seed/{index}".encode("utf-8")).digest()[:4],
            "big",
        )
        for index in range(count)
    ]


def expected_evaluation_contract() -> dict[str, Any]:
    return {
        "schema_version": CONTRACT_SCHEMA_VERSION,
        "contract_id": CONTRACT_ID,
        "kind": CONTRACT_KIND,
        "status": "FROZEN",
        "decision_source": {"path": DECISION_PATH, "sha256": DECISION_SHA256},
        "authorization": {
            "purpose": "evaluation_contract_only",
            "training_authorized": False,
            "kaggle_launch_authorized": False,
            "modal_authorized": False,
            "submission_authorized": False,
        },
        "randomness": {
            "engine_trajectory_reproduction_claimed": False,
            "paired_engine_seeds_claimed": False,
            "toy_seed_derivation": "sha256-first-u32-big-endian",
            "toy_seed_namespace": CONTRACT_ID,
            "declared_toy_seeds": derive_declared_seeds(),
            "natural_deployment_primary": True,
            "balance_player_slots": True,
            "policy_controls_first_player_choice": True,
            "forced_actual_first_second_diagnostics_separate": True,
        },
        "g3a": {
            "pass_rule": "ALL_TASKS_PASS_IN_ALL_DECLARED_SEEDS",
            "budget": {
                "minimum_non_forced_choices_per_seed": 25_000,
                "maximum_non_forced_choices_per_seed": 100_000,
                "exact_budget_required_before_run": True,
                "same_budget_across_seeds": True,
                "maximum_relative_budget_difference": 0.0025,
                "task_allocation_required_before_run": True,
            },
            "tasks": {
                "masked-bandit-v1": {
                    "kind": "masked_bandit",
                    "legal_mask_required": True,
                    "invalid_action_is_failure": True,
                    "pass_definition": (
                        "VERSIONED_TASK_CONTRACT_PASS_WITH_ZERO_FAILED_EVALUATION_CASES"
                    ),
                },
                "recurrent-cue-v1": {
                    "kind": "recurrent_partial_observation",
                    "cue_values": [0, 1],
                    "decision_observation_identical_across_cues": True,
                    "stateless_theoretical_ceiling": 0.5,
                    "recurrent_oracle_ceiling": 1.0,
                    "minimum_recurrent_score": 0.85,
                    "minimum_margin_vs_stateless": 0.25,
                    "margin_required_every_seed": True,
                    "pass_definition": (
                        "VERSIONED_TASK_CONTRACT_PASS_WITH_ZERO_FAILED_EVALUATION_CASES"
                    ),
                },
                "variable-option-multiselect-v1": {
                    "kind": "variable_option_multi_select",
                    "ordered_unique_selection_required": True,
                    "stop_is_first_class": True,
                    "variable_option_count_required": True,
                    "variable_min_max_count_required": True,
                    "invalid_action_is_failure": True,
                    "pass_definition": (
                        "VERSIONED_TASK_CONTRACT_PASS_WITH_ZERO_FAILED_EVALUATION_CASES"
                    ),
                },
            },
            "probability_replay": {
                "checked_before_first_update": True,
                "maximum_old_compound_log_probability_absolute_error": 1e-5,
                "maximum_initial_ratio_absolute_error_from_one": 1e-5,
            },
            "zero_tolerance_counters": list(ZERO_TOLERANCE_COUNTERS),
            "checkpoint_resume": {
                "required_components": list(REQUIRED_RESUME_COMPONENTS),
                "restore_all_available_rng_states": True,
                "fixed_tensor_atol": 1e-5,
                "fixed_tensor_rtol": 0.0,
            },
            "strength_claim_allowed": False,
        },
        "future_strength": {
            "score_formula": "(wins + 0.5 * draws) / games",
            "posterior": {
                "method": "dirichlet_multinomial_posterior_simulation",
                "prior_win_draw_loss": [0.5, 0.5, 0.5],
                "credible_level": 0.95,
                "simulation_draws": 10_000,
                "primary_meta_window_days": 7,
                "sensitivity_meta_window_days": [3, 7, 14],
                "insufficient_coverage_result": "INSUFFICIENT_COVERAGE",
            },
            "g3b": {
                "broad_screen_non_forced_choices_per_seed": 1_000_000,
                "confirmation_cumulative_non_forced_choices_per_seed": 5_000_000,
                "declared_seed_count": 3,
                "maximum_choice_budget_relative_difference": 0.0025,
                "random_anchor_minimum_games": 1_000,
                "random_anchor_lower_bound_minimum": 0.85,
                "rule_anchor_count": 4,
                "rule_anchors_required_above_even": 3,
                "rule_anchor_lower_bound_strictly_greater_than": 0.5,
                "rule_anchor_probability_above_even_minimum": 0.975,
                "remaining_rule_anchor_lower_bound_minimum": 0.35,
                "aggregate_lower_bound_strictly_greater_than": 0.52,
                "minimum_seed_point_estimate": 0.5,
                "report_across_seed_standard_deviation": True,
                "reliability_zero_tolerance": True,
            },
            "d1": {
                "important_matchup_lower_bound_minimum": 0.4,
                "important_matchup_probability_below_floor_maximum": 0.025,
                "same_deck_regression_magnitude": 0.03,
                "same_deck_probability_regression_exceeds_magnitude_maximum": 0.025,
                "same_deck_absolute_lower_bound_minimum": 0.4,
                "minimum_unresolved_finalist_seeds": 3,
                "equal_cumulative_non_forced_choice_budgets": True,
                "reliability_zero_tolerance": True,
            },
            "champion": {
                "minimum_frozen_population_games": 3_000,
                "minimum_games_per_important_archetype_where_feasible": 300,
                "probability_meta_weighted_improvement_positive_minimum": 0.99,
                "candidate_minus_anchor_lower_bound_minimum": 0.02,
                "candidate_minus_anchor_mean_minimum": 0.03,
                "all_absolute_and_relative_matchup_floors_required": True,
                "runtime_package_checkpoint_parity_required": True,
                "no_verified_immediate_exploiter_collapse_required": True,
                "reliability_zero_tolerance": True,
            },
            "promotion_order": [
                "contract_and_reliability",
                "catastrophic_matchup_floors",
                "meta_weighted_strength",
                "runtime_and_package",
                "exploiter_defense",
            ],
            "forbid_blended_score": True,
        },
        "run_manifest_requirements": {
            "required_identity_fields": [
                "artifact_hashes",
                "card_data_hash",
                "config_hash",
                "deck_hashes",
                "engine_hash",
                "opponent_population_hash",
                "policy_hash",
                "source_commit",
            ],
            "population_and_weights_frozen_before_run": True,
            "opponent_fixed_for_episode": True,
            "complete_matchup_matrix_required": True,
            "seat_split_required": True,
            "forced_seat_results_separate": True,
            "loss_capsules_required": True,
            "latency_percentiles": [50, 95, 99],
            "zero_tolerance_evidence_required": True,
            "independent_review_required": True,
        },
    }


def _first_difference(expected: Any, observed: Any, path: str = "contract") -> str | None:
    if type(expected) is not type(observed):
        return f"{path} type differs: expected {type(expected).__name__}, got {type(observed).__name__}"
    if isinstance(expected, dict):
        expected_keys = set(expected)
        observed_keys = set(observed)
        if expected_keys != observed_keys:
            return (
                f"{path} keys differ: missing={sorted(expected_keys - observed_keys)}, "
                f"unexpected={sorted(observed_keys - expected_keys)}"
            )
        for key in sorted(expected):
            difference = _first_difference(expected[key], observed[key], f"{path}.{key}")
            if difference is not None:
                return difference
        return None
    if isinstance(expected, list):
        if len(expected) != len(observed):
            return f"{path} length differs: expected {len(expected)}, got {len(observed)}"
        for index, (left, right) in enumerate(zip(expected, observed, strict=True)):
            difference = _first_difference(left, right, f"{path}[{index}]")
            if difference is not None:
                return difference
        return None
    if expected != observed:
        return f"{path} differs: expected {expected!r}, got {observed!r}"
    return None


def validate_evaluation_contract(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise EvaluationContractError("evaluation contract root must be an object")
    observed = dict(value)
    canonical_json_bytes(observed)
    difference = _first_difference(expected_evaluation_contract(), observed)
    if difference is not None:
        raise EvaluationContractError(difference)
    return observed


def _reject_duplicate_object_pairs(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise EvaluationContractError(f"JSON object contains duplicate key: {key}")
        value[key] = item
    return value


def load_json_object(path: Path, name: str = "JSON document") -> dict[str, Any]:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise EvaluationContractError(f"cannot read {name} {path}: {error}") from error
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicate_object_pairs)
    except UnicodeError as error:
        raise EvaluationContractError(f"{name} is not valid UTF-8") from error
    except json.JSONDecodeError as error:
        raise EvaluationContractError(f"{name} is not valid JSON: {error}") from error
    if not isinstance(value, dict):
        raise EvaluationContractError(f"{name} root must be an object")
    canonical_json_bytes(value)
    return value


def load_evaluation_contract(path: Path) -> LoadedEvaluationContract:
    raw = path.read_bytes()
    value = load_json_object(path, "evaluation contract")
    validate_evaluation_contract(value)
    return LoadedEvaluationContract(
        value=value,
        file_sha256=hashlib.sha256(raw).hexdigest(),
        semantic_sha256=contract_semantic_sha256(value),
        bytes=len(raw),
    )


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    observed = set(value)
    if observed != expected:
        raise EvaluationContractError(
            f"{name} keys differ: missing={sorted(expected - observed)}, "
            f"unexpected={sorted(observed - expected)}"
        )


def _require_mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise EvaluationContractError(f"{name} must be an object")
    return value


def _require_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise EvaluationContractError(f"{name} must be a boolean")
    return value


def _require_int(value: Any, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise EvaluationContractError(f"{name} must be an integer >= {minimum}")
    return value


def _require_finite(value: Any, name: str, minimum: float | None = None, maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EvaluationContractError(f"{name} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise EvaluationContractError(f"{name} must be finite")
    if minimum is not None and number < minimum:
        raise EvaluationContractError(f"{name} must be >= {minimum}")
    if maximum is not None and number > maximum:
        raise EvaluationContractError(f"{name} must be <= {maximum}")
    return number


def _require_sha256(value: Any, name: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise EvaluationContractError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _require_commit(value: Any, name: str) -> str:
    if not isinstance(value, str) or COMMIT_RE.fullmatch(value) is None:
        raise EvaluationContractError(f"{name} must be a lowercase 40-character Git commit")
    return value


def _safe_relative_path(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise EvaluationContractError(f"{name} must be a canonical POSIX relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(part in {"", ".", ".."} for part in path.parts):
        raise EvaluationContractError(f"{name} must be a safe canonical relative path")
    return value


def _validate_task_result(task_id: str, value: Any, failures: list[str], seed: int) -> None:
    result = _require_mapping(value, f"seed {seed} task {task_id}")
    base_keys = {
        "status",
        "task_contract_sha256",
        "metrics_sha256",
        "choices",
        "evaluation_cases",
        "failed_cases",
    }
    recurrent_keys = base_keys | {"recurrent_score", "stateless_score", "margin_vs_stateless"}
    _require_exact_keys(
        result,
        recurrent_keys if task_id == "recurrent-cue-v1" else base_keys,
        f"seed {seed} task {task_id}",
    )
    if result["status"] != "PASS":
        failures.append(f"seed {seed} task {task_id} status is not PASS")
    _require_sha256(result["task_contract_sha256"], f"seed {seed} task contract SHA-256")
    _require_sha256(result["metrics_sha256"], f"seed {seed} task metrics SHA-256")
    _require_int(result["choices"], f"seed {seed} task choices", 1)
    _require_int(result["evaluation_cases"], f"seed {seed} task evaluation cases", 1)
    failed_cases = _require_int(result["failed_cases"], f"seed {seed} task failed cases")
    if failed_cases != 0:
        failures.append(f"seed {seed} task {task_id} has {failed_cases} failed evaluation cases")
    if task_id == "recurrent-cue-v1":
        recurrent_score = _require_finite(
            result["recurrent_score"], f"seed {seed} recurrent score", 0.0, 1.0
        )
        stateless_score = _require_finite(
            result["stateless_score"], f"seed {seed} stateless score", 0.0, 1.0
        )
        margin = _require_finite(
            result["margin_vs_stateless"], f"seed {seed} recurrent margin", -1.0, 1.0
        )
        if abs(margin - (recurrent_score - stateless_score)) > 1e-12:
            raise EvaluationContractError(f"seed {seed} recurrent margin is arithmetically inconsistent")
        task_contract = expected_evaluation_contract()["g3a"]["tasks"][task_id]
        if recurrent_score < task_contract["minimum_recurrent_score"]:
            failures.append(
                f"seed {seed} recurrent score {recurrent_score} is below "
                f"{task_contract['minimum_recurrent_score']}"
            )
        if margin < task_contract["minimum_margin_vs_stateless"]:
            failures.append(
                f"seed {seed} recurrent margin {margin} is below "
                f"{task_contract['minimum_margin_vs_stateless']}"
            )


def review_g3a_evidence(
    contract: LoadedEvaluationContract,
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    validate_evaluation_contract(contract.value)
    root = _require_mapping(evidence, "G3a evidence")
    _require_exact_keys(
        root,
        {
            "schema_version",
            "contract_id",
            "contract_file_sha256",
            "run_id",
            "source_commit",
            "status",
            "authorization",
            "budget",
            "seeds",
            "artifacts",
            "claim",
        },
        "G3a evidence",
    )
    if root["schema_version"] != 1:
        raise EvaluationContractError("unsupported G3a evidence schema version")
    if root["contract_id"] != CONTRACT_ID:
        raise EvaluationContractError("G3a evidence contract ID differs")
    if root["contract_file_sha256"] != contract.file_sha256:
        raise EvaluationContractError("G3a evidence contract file SHA-256 differs")
    if not isinstance(root["run_id"], str) or RUN_ID_RE.fullmatch(root["run_id"]) is None:
        raise EvaluationContractError("G3a run ID is invalid")
    _require_commit(root["source_commit"], "G3a source commit")
    failures: list[str] = []
    if root["status"] != "SUCCEEDED":
        failures.append("G3a run status is not SUCCEEDED")

    authorization = _require_mapping(root["authorization"], "G3a authorization")
    _require_exact_keys(
        authorization,
        {
            "user_training_approval",
            "private_bounded_run",
            "platform",
            "modal_used",
            "submission_created",
        },
        "G3a authorization",
    )
    if not _require_bool(authorization["user_training_approval"], "user training approval"):
        failures.append("explicit user training approval is absent")
    if not _require_bool(authorization["private_bounded_run"], "private bounded run"):
        failures.append("run was not declared private and bounded")
    if authorization["platform"] not in {"kaggle", "colab"}:
        failures.append("G3a platform is neither kaggle nor colab")
    if _require_bool(authorization["modal_used"], "Modal used"):
        failures.append("Modal use is outside G3a authorization")
    if _require_bool(authorization["submission_created"], "submission created"):
        failures.append("submission creation is outside G3a authorization")

    budget = _require_mapping(root["budget"], "G3a budget")
    _require_exact_keys(
        budget,
        {
            "declared_before_run",
            "non_forced_choices_per_seed",
            "task_allocation_sha256",
            "budget_manifest_sha256",
        },
        "G3a budget",
    )
    if not _require_bool(budget["declared_before_run"], "budget declared before run"):
        failures.append("G3a budget was not declared before the run")
    per_seed = budget["non_forced_choices_per_seed"]
    if not isinstance(per_seed, list) or len(per_seed) != 3:
        raise EvaluationContractError("G3a budget must contain exactly three seed totals")
    totals = [_require_int(item, "G3a non-forced choices per seed", 1) for item in per_seed]
    limits = contract.value["g3a"]["budget"]
    for index, total in enumerate(totals):
        if total < limits["minimum_non_forced_choices_per_seed"]:
            failures.append(f"seed budget {index} is below the frozen minimum")
        if total > limits["maximum_non_forced_choices_per_seed"]:
            failures.append(f"seed budget {index} exceeds the frozen maximum")
    if len(set(totals)) != 1:
        failures.append("non-forced choice budgets differ across declared seeds")
    _require_sha256(budget["task_allocation_sha256"], "task allocation SHA-256")
    _require_sha256(budget["budget_manifest_sha256"], "budget manifest SHA-256")

    seeds = root["seeds"]
    if not isinstance(seeds, list) or len(seeds) != 3:
        raise EvaluationContractError("G3a evidence must contain exactly three seed records")
    expected_seeds = contract.value["randomness"]["declared_toy_seeds"]
    observed_seeds: list[int] = []
    seed_summaries: list[dict[str, Any]] = []
    for record_value in seeds:
        record = _require_mapping(record_value, "G3a seed record")
        _require_exact_keys(
            record,
            {
                "seed",
                "tasks",
                "probability_replay",
                "zero_tolerance",
                "checkpoint_resume",
            },
            "G3a seed record",
        )
        seed = _require_int(record["seed"], "G3a seed")
        observed_seeds.append(seed)
        tasks = _require_mapping(record["tasks"], f"seed {seed} tasks")
        _require_exact_keys(tasks, set(G3A_TASK_IDS), f"seed {seed} tasks")
        before_failure_count = len(failures)
        for task_id in G3A_TASK_IDS:
            _validate_task_result(task_id, tasks[task_id], failures, seed)

        replay = _require_mapping(record["probability_replay"], f"seed {seed} probability replay")
        _require_exact_keys(
            replay,
            {
                "checked_before_first_update",
                "old_compound_log_probability_max_abs_error",
                "initial_ratio_max_abs_error_from_one",
            },
            f"seed {seed} probability replay",
        )
        if not _require_bool(
            replay["checked_before_first_update"],
            f"seed {seed} checked before first update",
        ):
            failures.append(f"seed {seed} probability replay was not checked before the first update")
        old_error = _require_finite(
            replay["old_compound_log_probability_max_abs_error"],
            f"seed {seed} old log-probability error",
            0.0,
        )
        ratio_error = _require_finite(
            replay["initial_ratio_max_abs_error_from_one"],
            f"seed {seed} initial ratio error",
            0.0,
        )
        replay_contract = contract.value["g3a"]["probability_replay"]
        if old_error > replay_contract["maximum_old_compound_log_probability_absolute_error"]:
            failures.append(f"seed {seed} old compound log-probability replay exceeds tolerance")
        if ratio_error > replay_contract["maximum_initial_ratio_absolute_error_from_one"]:
            failures.append(f"seed {seed} initial PPO ratio differs from one beyond tolerance")

        counters = _require_mapping(record["zero_tolerance"], f"seed {seed} zero tolerance")
        _require_exact_keys(counters, set(ZERO_TOLERANCE_COUNTERS), f"seed {seed} zero tolerance")
        for name in ZERO_TOLERANCE_COUNTERS:
            count = _require_int(counters[name], f"seed {seed} {name}")
            if count != 0:
                failures.append(f"seed {seed} zero-tolerance counter {name} is {count}")

        resume = _require_mapping(record["checkpoint_resume"], f"seed {seed} checkpoint resume")
        _require_exact_keys(
            resume,
            {
                "status",
                "components",
                "available_rng_states",
                "restored_rng_states",
                "fixed_tensor_max_abs_diff",
                "fixed_tensor_rtol",
            },
            f"seed {seed} checkpoint resume",
        )
        if resume["status"] != "PASS":
            failures.append(f"seed {seed} checkpoint resume status is not PASS")
        components = _require_mapping(resume["components"], f"seed {seed} resume components")
        _require_exact_keys(
            components,
            set(REQUIRED_RESUME_COMPONENTS),
            f"seed {seed} resume components",
        )
        for component in REQUIRED_RESUME_COMPONENTS:
            if not _require_bool(components[component], f"seed {seed} resume {component}"):
                failures.append(f"seed {seed} did not restore {component}")
        available = resume["available_rng_states"]
        restored = resume["restored_rng_states"]
        if (
            not isinstance(available, list)
            or not available
            or any(not isinstance(item, str) or not item for item in available)
            or available != sorted(set(available))
        ):
            raise EvaluationContractError(f"seed {seed} available RNG states must be sorted and unique")
        if not isinstance(restored, list) or restored != sorted(set(restored)):
            raise EvaluationContractError(f"seed {seed} restored RNG states must be sorted and unique")
        if restored != available:
            failures.append(f"seed {seed} did not restore every available RNG state")
        fixed_diff = _require_finite(
            resume["fixed_tensor_max_abs_diff"],
            f"seed {seed} fixed tensor max absolute difference",
            0.0,
        )
        fixed_rtol = _require_finite(
            resume["fixed_tensor_rtol"], f"seed {seed} fixed tensor rtol", 0.0
        )
        resume_contract = contract.value["g3a"]["checkpoint_resume"]
        if fixed_diff > resume_contract["fixed_tensor_atol"]:
            failures.append(f"seed {seed} checkpoint fixed-tensor output exceeds tolerance")
        if fixed_rtol != resume_contract["fixed_tensor_rtol"]:
            failures.append(f"seed {seed} checkpoint fixed-tensor rtol differs from zero")
        seed_summaries.append(
            {
                "seed": seed,
                "status": "PASS" if len(failures) == before_failure_count else "FAIL",
                "old_log_probability_max_abs_error": old_error,
                "initial_ratio_max_abs_error_from_one": ratio_error,
                "fixed_tensor_max_abs_diff": fixed_diff,
            }
        )
    if observed_seeds != expected_seeds:
        raise EvaluationContractError(
            f"G3a seed order/identity differs: expected {expected_seeds}, got {observed_seeds}"
        )

    artifacts = _require_mapping(root["artifacts"], "G3a artifacts")
    _require_exact_keys(
        artifacts,
        {
            "run_manifest_path",
            "run_manifest_sha256",
            "metrics_sha256",
            "checkpoint_manifest_sha256",
            "independent_review_sha256",
        },
        "G3a artifacts",
    )
    _safe_relative_path(artifacts["run_manifest_path"], "G3a run manifest path")
    for name in (
        "run_manifest_sha256",
        "metrics_sha256",
        "checkpoint_manifest_sha256",
        "independent_review_sha256",
    ):
        _require_sha256(artifacts[name], f"G3a artifact {name}")

    claim = _require_mapping(root["claim"], "G3a claim")
    _require_exact_keys(claim, {"algorithm_proof_only", "policy_strength_claimed"}, "G3a claim")
    if not _require_bool(claim["algorithm_proof_only"], "algorithm proof only"):
        failures.append("G3a is not explicitly limited to an algorithm proof")
    if _require_bool(claim["policy_strength_claimed"], "policy strength claimed"):
        failures.append("G3a evidence improperly claims policy strength")

    return {
        "schema_version": 1,
        "contract_id": CONTRACT_ID,
        "contract_file_sha256": contract.file_sha256,
        "contract_semantic_sha256": contract.semantic_sha256,
        "run_id": root["run_id"],
        "source_commit": root["source_commit"],
        "status": "SUCCEEDED" if not failures else "FAILED",
        "decision": "PASS" if not failures else "FAIL",
        "failures": failures,
        "declared_seeds": expected_seeds,
        "reviewed_seed_count": len(seed_summaries),
        "seed_summaries": seed_summaries,
        "algorithm_proof_only": True,
        "policy_strength_established": False,
    }
