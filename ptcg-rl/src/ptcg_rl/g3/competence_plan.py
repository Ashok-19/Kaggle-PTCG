from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ptcg_rl.g1.native import load_deck


class CompetencePlanError(ValueError):
    """Raised when the frozen G3b competence plan is incomplete or altered."""


PLAN_ID = "g3b-competence-v1"
PLAN_KIND = "KPTCG_G3B_COMPETENCE_PLAN"
EVIDENCE_BASE_COMMIT = "da0a89f2f1d664c707786d31fe033857e332abdc"
DECLARED_SEEDS = (3559096134, 178618376, 3063530691)
CANARY_SEED = 290023920


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


def semantic_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CompetencePlanError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_pairs)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CompetencePlanError(f"cannot load plan JSON: {path}") from error
    if not isinstance(value, dict):
        raise CompetencePlanError("plan JSON must contain one object")
    return value


def derive_seed(label: str) -> int:
    return int.from_bytes(hashlib.sha256(label.encode("utf-8")).digest()[:4], "big")


def expected_competence_plan() -> dict[str, Any]:
    common_ppo = {
        "optimizer": "adam",
        "adam_epsilon": 1e-5,
        "learning_rate": 3e-4,
        "learning_rate_schedule": "linear",
        "gamma": 1.0,
        "gae_lambda": 0.95,
        "clip_coefficient": 0.2,
        "value_clip_coefficient": 0.2,
        "value_coefficient": 0.5,
        "entropy_coefficient": 0.01,
        "maximum_gradient_norm": 0.5,
        "epochs": 3,
        "target_approximate_kl": 0.02,
        "stop_epoch_approximate_kl": 0.03,
        "rollback_clip_fraction_threshold": 0.30,
        "mixed_precision": False,
        "non_forced_choices_per_update": 16384,
        "recurrent_sequence_length": 64,
        "policy_version_lag": 0,
    }
    fixed_uniform = {
        "random-engineering-deck": 0.20,
        "rule-dragapult-ex": 0.20,
        "rule-iono": 0.20,
        "rule-mega-abomasnow-ex": 0.20,
        "rule-mega-lucario-ex": 0.20,
    }
    diagnosis_warmup = {
        "random-engineering-deck": 0.50,
        "rule-dragapult-ex": 0.125,
        "rule-iono": 0.125,
        "rule-mega-abomasnow-ex": 0.125,
        "rule-mega-lucario-ex": 0.125,
    }
    diagnosis_anchor = {
        "random-engineering-deck": 0.10,
        "rule-dragapult-ex": 0.225,
        "rule-iono": 0.225,
        "rule-mega-abomasnow-ex": 0.225,
        "rule-mega-lucario-ex": 0.225,
    }
    return {
        "schema_version": 1,
        "kind": PLAN_KIND,
        "plan_id": PLAN_ID,
        "evidence_base": {
            "commit": EVIDENCE_BASE_COMMIT,
            "clean_worktree_required": True,
            "g3a_gate_status": "SUCCEEDED",
            "g3a_gate_decision": "PASS",
        },
        "contract": {
            "path": "configs/g3a_evaluation_v1.json",
            "bytes": 6435,
            "sha256": "51f5d0d800a0a3832cc0ea8873828f6c68262eb4f24e55a8b11ae4143a2dae72",
            "g3b": {
                "broad_screen_non_forced_choices_per_seed": 1_000_000,
                "confirmation_cumulative_non_forced_choices_per_seed": 5_000_000,
                "declared_seed_count": 3,
                "maximum_choice_budget_relative_difference": 0.0025,
                "random_anchor_minimum_games": 1000,
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
        },
        "authorization": {
            "training_launch_authorized": False,
            "external_service_mutation_authorized": False,
            "modal_execution_authorized": False,
            "deck_freeze_authorized": False,
            "submission_authorized": False,
        },
        "claims": {
            "plan_only": True,
            "cabt_actor_learner_integration_complete": False,
            "training_source_frozen": False,
            "policy_competence_established": False,
            "policy_strength_established": False,
        },
        "candidate_comparison": [
            {
                "candidate_id": "direct-kaggle-five-million-single-session",
                "decision": "REJECT",
                "reasons": [
                    "CABT actor/learner integration is not implemented or qualified",
                    "no measured PPO training throughput exists",
                    "five million choices may exceed one notebook session under measured slowdown sensitivity",
                    "single-session failure would risk incomplete checkpoint recovery evidence",
                ],
            },
            {
                "candidate_id": "direct-modal-main-training",
                "decision": "REJECT",
                "reasons": [
                    "G4 Modal canary and restart proof are not complete",
                    "cost and throughput are not measured for this workload",
                    "the free private Kaggle T4x2 path is already verified for native-engine inference",
                ],
            },
            {
                "candidate_id": "staged-kaggle-t4x2-million-choice-chunks",
                "decision": "SELECT",
                "reasons": [
                    "separates integration correctness from policy competence",
                    "uses verified T4x2 native-engine topology as the starting evidence",
                    "one-million-choice chunks fit the eight-hour internal cap at the preregistered minimum rate",
                    "every chunk ends at an exact budget and produces a portable content-addressed checkpoint",
                ],
            },
        ],
        "selected_candidate_id": "staged-kaggle-t4x2-million-choice-chunks",
        "assets": {
            "native_engine": {
                "path": "private/assets/official/sample_submission/sample_submission/cg/libcg.so",
                "bytes": 1_342_400,
                "sha256": "feafd4046b2f688bdb33a4972c139b78e13e243ab5707ece52c43cf39a34b887",
            },
            "card_data": {
                "path": "private/assets/official/EN_Card_Data.csv",
                "bytes": 359_151,
                "sha256": "a0ea63cf7adcb65d35436ce0eb390de6e2e35654a7c67c065a45f4abaa00f373",
            },
            "engineering_deck": {
                "path": "private/assets/official/sample_submission/sample_submission/deck.csv",
                "bytes": 245,
                "sha256": "42068a1803902756badcfd418f6f348b7901365a281d78af0692cbf2589f0799",
                "cards": 60,
                "role": "fixed_learner_deck",
            },
            "initial_checkpoint": {
                "path": "private/g2/checkpoint-v1/g2-policy-checkpoint-v1.zip",
                "bytes": 5_429_190,
                "sha256": "4dfba2adb9f97607cfa5dabadba075236bb7aae51eafab264584e947feae3827",
                "trainable_parameters": 970_022,
                "architecture_sha256": "aff9a5f87e1c472761ea56fda29dd96f1124d75b3a5aaec280185397967c42cf",
            },
            "rule_anchor_receipts": [
                {
                    "baseline_id": "dragapult-ex",
                    "path": "private/baselines/dragapult-ex/receipt.json",
                    "sha256": "abc733a20c9a1f9be0877b35ce69d1ae98ec308f9d44b8322ed9a5f3df6abd40",
                },
                {
                    "baseline_id": "iono",
                    "path": "private/baselines/iono/receipt.json",
                    "sha256": "436b1ea6a55d744f7307e1505091050bfd2199f4edc70014dd9172673502023f",
                },
                {
                    "baseline_id": "mega-abomasnow-ex",
                    "path": "private/baselines/mega-abomasnow-ex/receipt.json",
                    "sha256": "d64f79fdf534977a3c417a5526fa406fbac288907fb59ecbe8e1bd057741b9ae",
                },
                {
                    "baseline_id": "mega-lucario-ex",
                    "path": "private/baselines/mega-lucario-ex/receipt.json",
                    "sha256": "dc94ec50448e7a0dd40423d62cd33c480d6021870d2726c9849ba0429045713e",
                },
            ],
        },
        "algorithm": {
            "family": "synchronous_recurrent_ppo",
            "actor_information": "public_only",
            "critic_information": "public_only",
            "terminal_reward": {"win": 1.0, "draw": 0.0, "loss": -1.0},
            "reward_shaping": False,
            "behavior_cloning": False,
            "privileged_critic": False,
            "inference_search": False,
            "public_replay_action_supervision": False,
            "exact_deck_specialist": True,
            "ordered_multiselect_stop": True,
        },
        "configurations": {
            "primary": {
                **common_ppo,
                "configuration_id": "ppo-uniform-anchor-mixture-v1",
                "opponent_schedule": [
                    {"start_choice": 0, "end_choice": 5_000_000, "weights": fixed_uniform}
                ],
            },
            "diagnosis_alternative": {
                **common_ppo,
                "configuration_id": "ppo-random-warmup-anchor-curriculum-v1",
                "invocation": "only_after_primary_five_million_failure_and_bounded_diagnosis",
                "single_preregistered_factor_changed": "opponent_schedule",
                "opponent_schedule": [
                    {"start_choice": 0, "end_choice": 1_000_000, "weights": diagnosis_warmup},
                    {"start_choice": 1_000_000, "end_choice": 5_000_000, "weights": diagnosis_anchor},
                ],
            },
        },
        "seeds": {
            "derivation": "sha256-first-u32-big-endian over g3b-competence-v1/seed/<index>",
            "declared": list(DECLARED_SEEDS),
            "canary_derivation": "sha256-first-u32-big-endian over g3b-competence-v1/canary",
            "canary": CANARY_SEED,
        },
        "stages": [
            {
                "stage_id": "integration-qualification",
                "launch_required": False,
                "training_choices": 0,
                "purpose": "implement and exhaustively test the CABT actor/learner bridge without meaningful training",
                "requirements": [
                    "exact G2 projection and decoder are used",
                    "stored compound actions replay before the first optimizer step",
                    "both player terminal boundaries are attached correctly",
                    "forced calls advance recurrence but create no PPO node",
                    "worker death and duplicate/stale/out-of-order requests fail closed",
                    "checkpoint restore covers learner, optimizer, counters, rollout boundary, league and RNG",
                ],
            },
            {
                "stage_id": "topology-canary",
                "launch_required": True,
                "counts_toward_g3b_budget": False,
                "seed": CANARY_SEED,
                "total_non_forced_choices": 100_000,
                "layout_trials": [
                    {
                        "layout_id": "two-inference-servers-learner-shared-cuda0",
                        "non_forced_choices": 50_000,
                    },
                    {
                        "layout_id": "one-inference-server-cuda0-dedicated-learner-cuda1",
                        "non_forced_choices": 50_000,
                    },
                ],
                "checkpoint_reused_for_broad_screen": False,
                "selection_order": [
                    "zero_tolerance_and_parity",
                    "minimum_non_forced_choices_per_second",
                    "p95_queue_delay",
                    "peak_memory",
                ],
                "minimum_non_forced_choices_per_second": 35.0,
                "maximum_internal_wall_seconds": 10_800,
            },
            {
                "stage_id": "broad-screen",
                "configuration": "primary",
                "non_forced_choices_per_seed": 1_000_000,
                "chunk_non_forced_choices": 1_000_000,
                "chunks_per_seed": 1,
                "evaluation_cycle": "broad-screen-fixed-population",
            },
            {
                "stage_id": "competence-confirmation",
                "configuration": "primary",
                "cumulative_non_forced_choices_per_seed": 5_000_000,
                "chunk_non_forced_choices": 1_000_000,
                "cumulative_chunks_per_seed": 5,
                "additional_chunks_after_broad_screen": 4,
                "evaluation_cycle": "confirmation-fixed-population",
            },
            {
                "stage_id": "bounded-diagnosis-branch",
                "configuration": "diagnosis_alternative",
                "invocation": "only_if_primary_fails_fixed_g3b_acceptance",
                "diagnosis_before_launch_required": True,
                "cumulative_non_forced_choices_per_seed": 5_000_000,
                "evaluation_cycles_per_seed": [1_000_000, 5_000_000],
                "no_result_dependent_budget_extension": True,
            },
        ],
        "platform": {
            "selected": "private-kaggle-t4x2",
            "private": True,
            "internet": False,
            "required_visible_devices": ["Tesla T4", "Tesla T4"],
            "engine_workers": 32,
            "inference_servers_under_canary": [1, 2],
            "maximum_batch": 16,
            "batch_wait_ms": 1.0,
            "multiprocessing_start_method": "spawn",
            "chunk_internal_wall_cap_seconds": 28_800,
            "evaluation_internal_wall_cap_seconds": 14_400,
            "docker_image_digest": None,
            "docker_image_digest_must_be_captured_by_canary": True,
            "modal_rejected_until_g4_canary": True,
        },
        "evaluation": {
            "natural_deployment": True,
            "balanced_player_slots": True,
            "forced_actual_first_second_separate": True,
            "games_per_seed_per_population": 400,
            "learner_slot_zero_games_per_seed_per_population": 200,
            "learner_slot_one_games_per_seed_per_population": 200,
            "total_games_per_population": 1200,
            "populations": [
                "random-engineering-deck",
                "rule-dragapult-ex",
                "rule-iono",
                "rule-mega-abomasnow-ex",
                "rule-mega-lucario-ex",
            ],
            "total_games_per_cycle": 6000,
            "aggregate_population": [
                "rule-dragapult-ex",
                "rule-iono",
                "rule-mega-abomasnow-ex",
                "rule-mega-lucario-ex",
            ],
            "aggregate_weights": {
                "rule-dragapult-ex": 0.25,
                "rule-iono": 0.25,
                "rule-mega-abomasnow-ex": 0.25,
                "rule-mega-lucario-ex": 0.25,
            },
            "weight_basis": "equal fixed weights because the retained replay sample is selected and insufficient for a defensible current meta distribution",
            "posterior": {
                "method": "dirichlet_multinomial_posterior_simulation",
                "prior_win_draw_loss": [0.5, 0.5, 0.5],
                "credible_level": 0.95,
                "simulation_draws": 10_000,
                "score_formula": "wins + 0.5 * draws over games",
            },
            "promotion_threshold_source": "contract.g3b",
            "reliability_zero_tolerance": True,
        },
        "checkpoint": {
            "cadence_non_forced_choices": 100_000,
            "cadence_wall_seconds": 900,
            "atomic": True,
            "content_addressed": True,
            "final_exact_chunk_checkpoint": True,
            "fresh_process_resume_canary_after_choices": 50_000,
            "portable_between_saved_notebook_versions": True,
            "remote_checkpoint_publication_requires_byte_hash_verification": True,
            "required_components": [
                "model",
                "optimizer",
                "scheduler_or_scaler",
                "counters",
                "league_registry",
                "opponent_schedule_position",
                "rollout_boundary",
                "python_rng",
                "numpy_rng",
                "torch_cpu_rng",
                "torch_cuda_rng",
            ],
        },
        "runtime_basis": {
            "source": "reports/evaluations/g2-neural-reliability-v1.json",
            "source_sha256": "d6b934a43cc449a5b8ba6648cc97eb191ab690f9689b3757a9f663da782d3f69",
            "meaningful_choices": 1_156_383,
            "runner_wall_seconds": 5058.581121050001,
            "measured_inference_only_choices_per_second": 228.59829116666842,
            "minimum_canary_choices_per_second": 35.0,
            "one_million_seconds_at_minimum_rate": 28_571.428571428572,
            "one_million_fits_chunk_cap": True,
            "five_million_fits_chunk_cap": False,
        },
        "stop_conditions": [
            "invalid_action",
            "illegal_mask_selection",
            "duplicate_ordered_selection",
            "selection_count_outside_bounds",
            "nan_or_inf",
            "probability_replay_mismatch",
            "initial_ratio_mismatch",
            "stale_or_out_of_order_request",
            "hidden_state_cross_owner_or_version",
            "unclassified_terminal_or_truncation",
            "policy_version_lag_nonzero",
            "timeout",
            "crash_or_swallowed_exception",
            "fallback",
            "checkpoint_or_manifest_mismatch",
            "resume_parity_failure",
            "source_config_asset_or_deck_hash_mismatch",
            "unexpected_device_or_internet_state",
            "choice_budget_drift_above_contract",
            "canary_throughput_below_minimum",
            "missing_seed_population_or_player_slot",
            "artifact_write_upload_or_download_failure",
        ],
        "outputs": {
            "collision_policy": "FAIL_IF_EXISTS",
            "manifest_first_download": True,
            "required_per_chunk": [
                "run-manifest.json",
                "metrics.jsonl",
                "checkpoint-manifest.json",
                "final-checkpoint",
                "output-manifest.json",
            ],
            "required_per_evaluation": [
                "games.jsonl",
                "evaluation-summary.json",
                "independent-review.json",
                "output-manifest.json",
            ],
        },
        "next_gate": {
            "task": "T-G3B-INTEGRATION-001",
            "action": "implement and independently qualify the CABT actor/learner bridge without launching G3b training",
            "training_requires_new_explicit_user_approval": True,
        },
    }


@dataclass(frozen=True)
class LoadedCompetencePlan:
    value: dict[str, Any]
    semantic_sha256: str


def _verify_file(repo: Path, record: Mapping[str, Any]) -> Path:
    relative = record.get("path")
    if not isinstance(relative, str) or not relative or relative.startswith("/") or ".." in Path(relative).parts:
        raise CompetencePlanError("asset path must be a safe repository-relative path")
    candidate = repo / relative
    if candidate.is_symlink():
        raise CompetencePlanError("asset must be a regular non-symlink file")
    path = candidate.resolve(strict=True)
    repository = repo.resolve(strict=True)
    if path != repository and repository not in path.parents:
        raise CompetencePlanError("asset path escapes the repository")
    if not path.is_file():
        raise CompetencePlanError("asset must be a regular non-symlink file")
    raw = path.read_bytes()
    if len(raw) != record.get("bytes"):
        raise CompetencePlanError(f"asset byte count differs: {relative}")
    if hashlib.sha256(raw).hexdigest() != record.get("sha256"):
        raise CompetencePlanError(f"asset SHA-256 differs: {relative}")
    return path


def _verify_anchor_receipts(repo: Path, records: list[dict[str, Any]]) -> None:
    if [item.get("baseline_id") for item in records] != [
        "dragapult-ex",
        "iono",
        "mega-abomasnow-ex",
        "mega-lucario-ex",
    ]:
        raise CompetencePlanError("rule anchor order or membership differs")
    for item in records:
        receipt_path = _verify_file(repo, {**item, "bytes": (repo / item["path"]).stat().st_size})
        receipt = load_json_object(receipt_path)
        if receipt.get("baseline_id") != item["baseline_id"]:
            raise CompetencePlanError("rule anchor receipt identity differs")
        base = receipt_path.parent
        for name, filename in (("deck", "deck.csv"), ("module", "main.py")):
            nested = receipt.get(name)
            if not isinstance(nested, dict):
                raise CompetencePlanError("rule anchor receipt is incomplete")
            path = base / filename
            raw = path.read_bytes()
            if len(raw) != nested.get("bytes") or hashlib.sha256(raw).hexdigest() != nested.get("sha256"):
                raise CompetencePlanError(f"rule anchor {name} bytes differ")
        if len(load_deck(base / "deck.csv")) != 60:
            raise CompetencePlanError("rule anchor deck does not contain exactly 60 cards")


def validate_competence_plan(value: Mapping[str, Any], repo: Path) -> None:
    expected = expected_competence_plan()
    if value != expected:
        raise CompetencePlanError("plan differs from the frozen G3b competence plan")
    if derive_seed(f"{PLAN_ID}/canary") != CANARY_SEED:
        raise CompetencePlanError("canary seed derivation differs")
    if tuple(derive_seed(f"{PLAN_ID}/seed/{index}") for index in range(3)) != DECLARED_SEEDS:
        raise CompetencePlanError("declared seed derivation differs")
    if len(set(DECLARED_SEEDS + (CANARY_SEED,))) != 4:
        raise CompetencePlanError("declared and canary seeds must be unique")
    if not re.fullmatch(r"[0-9a-f]{40}", value["evidence_base"]["commit"]):
        raise CompetencePlanError("evidence base commit must be a full Git SHA")

    contract_path = _verify_file(repo, value["contract"])
    contract = load_json_object(contract_path)
    if contract.get("future_strength", {}).get("g3b") != value["contract"]["g3b"]:
        raise CompetencePlanError("G3b thresholds differ from the frozen evaluation contract")

    assets = value["assets"]
    for name in ("native_engine", "card_data", "engineering_deck", "initial_checkpoint"):
        _verify_file(repo, assets[name])
    if len(load_deck(repo / assets["engineering_deck"]["path"])) != 60:
        raise CompetencePlanError("engineering deck does not contain exactly 60 cards")
    _verify_anchor_receipts(repo, assets["rule_anchor_receipts"])

    candidates = value["candidate_comparison"]
    selected = [item for item in candidates if item.get("decision") == "SELECT"]
    if len(selected) != 1 or selected[0].get("candidate_id") != value["selected_candidate_id"]:
        raise CompetencePlanError("exactly one planning candidate must be selected")

    primary = value["configurations"]["primary"]
    alternative = value["configurations"]["diagnosis_alternative"]
    primary_without = {key: val for key, val in primary.items() if key not in {"configuration_id", "opponent_schedule"}}
    alternative_without = {
        key: val
        for key, val in alternative.items()
        if key not in {"configuration_id", "opponent_schedule", "invocation", "single_preregistered_factor_changed"}
    }
    if primary_without != alternative_without:
        raise CompetencePlanError("diagnosis configuration changes more than opponent schedule")
    for configuration in (primary, alternative):
        for period in configuration["opponent_schedule"]:
            weights = period["weights"]
            if not math.isclose(sum(weights.values()), 1.0, rel_tol=0.0, abs_tol=1e-12):
                raise CompetencePlanError("opponent weights must sum exactly to one")
            if any(weight <= 0 for weight in weights.values()):
                raise CompetencePlanError("every frozen opponent must retain positive probability")

    stages = {stage["stage_id"]: stage for stage in value["stages"]}
    broad = stages["broad-screen"]
    confirmation = stages["competence-confirmation"]
    if broad["non_forced_choices_per_seed"] != value["contract"]["g3b"][
        "broad_screen_non_forced_choices_per_seed"
    ]:
        raise CompetencePlanError("broad-screen budget differs from contract")
    if confirmation["cumulative_non_forced_choices_per_seed"] != value["contract"]["g3b"][
        "confirmation_cumulative_non_forced_choices_per_seed"
    ]:
        raise CompetencePlanError("confirmation budget differs from contract")
    if confirmation["cumulative_chunks_per_seed"] * confirmation["chunk_non_forced_choices"] != confirmation[
        "cumulative_non_forced_choices_per_seed"
    ]:
        raise CompetencePlanError("confirmation chunk arithmetic differs")

    evaluation = value["evaluation"]
    if evaluation["games_per_seed_per_population"] != (
        evaluation["learner_slot_zero_games_per_seed_per_population"]
        + evaluation["learner_slot_one_games_per_seed_per_population"]
    ):
        raise CompetencePlanError("evaluation player slots are not balanced")
    if evaluation["total_games_per_population"] != evaluation["games_per_seed_per_population"] * 3:
        raise CompetencePlanError("evaluation population game total differs")
    if evaluation["total_games_per_population"] < value["contract"]["g3b"]["random_anchor_minimum_games"]:
        raise CompetencePlanError("random anchor evaluation is undersized")
    if not math.isclose(sum(evaluation["aggregate_weights"].values()), 1.0, abs_tol=1e-12):
        raise CompetencePlanError("aggregate weights must sum exactly to one")
    if list(evaluation["aggregate_weights"]) != evaluation["aggregate_population"]:
        raise CompetencePlanError("aggregate population and weights differ")
    if "random-engineering-deck" in evaluation["aggregate_population"]:
        raise CompetencePlanError("random anchor must not inflate the rule-anchor aggregate")

    runtime = value["runtime_basis"]
    expected_seconds = 1_000_000 / runtime["minimum_canary_choices_per_second"]
    if not math.isclose(runtime["one_million_seconds_at_minimum_rate"], expected_seconds, rel_tol=1e-12):
        raise CompetencePlanError("runtime chunk derivation differs")
    if expected_seconds > value["platform"]["chunk_internal_wall_cap_seconds"]:
        raise CompetencePlanError("one-million-choice chunk does not fit the internal cap")

    if any(value["authorization"].values()):
        raise CompetencePlanError("the planning artifact must not authorize external execution")


def load_competence_plan(path: Path, repo: Path) -> LoadedCompetencePlan:
    value = load_json_object(path)
    validate_competence_plan(value, repo)
    return LoadedCompetencePlan(value=value, semantic_sha256=semantic_sha256(value))


def review_competence_plan(
    loaded: LoadedCompetencePlan,
    *,
    created_at_utc: str,
    source_path: str,
    planner_commit: str,
) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{40}", planner_commit):
        raise CompetencePlanError("planner commit must be a full Git SHA")
    value = loaded.value
    return {
        "schema_version": 1,
        "record_id": "artifact-g3b-competence-plan-review-v1",
        "created_at_utc": created_at_utc,
        "updated_at_utc": created_at_utc,
        "source_path": source_path,
        "producer": "g3b-competence-plan-independent-review",
        "producer_version": "1",
        "gate_id": "G3b",
        "kind": "KPTCG_G3B_COMPETENCE_PLAN_REVIEW",
        "status": "SUCCEEDED",
        "decision": "PASS",
        "plan_id": value["plan_id"],
        "plan_semantic_sha256": loaded.semantic_sha256,
        "planner_commit": planner_commit,
        "evidence_base_commit": value["evidence_base"]["commit"],
        "selected_candidate_id": value["selected_candidate_id"],
        "checks": {
            "frozen_contract_exact": True,
            "all_private_assets_byte_verified": True,
            "four_exact_rule_anchors_verified": True,
            "three_declared_seeds_unique_and_derived": True,
            "canary_seed_separate": True,
            "one_million_chunk_runtime_derived": True,
            "five_million_single_session_rejected": True,
            "two_topology_canary_branches_complete": True,
            "primary_and_diagnosis_differ_only_by_opponent_schedule": True,
            "evaluation_slots_balanced": True,
            "random_anchor_minimum_games_exceeded": True,
            "aggregate_weights_frozen": True,
            "checkpoint_and_resume_requirements_complete": True,
            "zero_tolerance_stop_conditions_complete": True,
            "external_execution_not_authorized": True,
        },
        "next_task": value["next_gate"]["task"],
        "training_launch_authorized": False,
        "external_service_mutated": False,
        "policy_competence_claimed": False,
        "cost_usd": 0.0,
    }
