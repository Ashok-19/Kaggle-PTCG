from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from ptcg_rl.g3.cloud_plan import (
    CloudPlanError,
    load_cloud_plan,
    review_cloud_plan,
    validate_cloud_plan,
    validate_download_receipt,
)


REQUIRED_SEEDS = [1197953491, 20344180, 1491619630]
STREAMS = [
    "masked-bandit-v1",
    "recurrent-cue-v1",
    "variable-option-multiselect-v1",
    "recurrent-cue-v1-stateless",
]


def plan_fixture() -> dict[str, object]:
    allocations = {
        str(seed): {stream: 25_000 for stream in STREAMS}
        for seed in REQUIRED_SEEDS
    }
    return {
        "schema_version": 1,
        "kind": "KPTCG_G3A_CLOUD_CORRECTNESS_PLAN",
        "plan_id": "g3a-cloud-correctness-v1",
        "authorization": {
            "training_launch_authorized": False,
            "external_mutation_authorized": False,
            "submission_authorized": False,
        },
        "algorithm_boundaries": {
            "algorithm": "recurrent_ppo",
            "actor_information": "public_only",
            "critic_information": "public_only",
            "terminal_reward": "+1/0/-1",
            "reward_shaping": False,
            "privileged_critic": False,
            "behavior_cloning": False,
            "public_replay_action_supervision": False,
            "inference_search": False,
            "maximum_parameters": 2_000_000,
            "exact_deck_specialist": True,
            "ordered_multi_select_with_stop": True,
            "policy_version_lag": 0,
            "pokemon_self_play": False,
            "toy_correctness_only": True,
        },
        "stop_conditions": [
            "invalid_action",
            "illegal_mask_selection",
            "duplicate_ordered_selection",
            "stop_when_unavailable",
            "selection_count_outside_bounds",
            "nan_or_inf",
            "probability_replay_mismatch",
            "initial_ratio_mismatch",
            "stale_recurrent_request",
            "out_of_order_recurrent_request",
            "hidden_state_cross_owner_or_version",
            "unclassified_terminal_or_truncation",
            "timeout",
            "crash_or_swallowed_exception",
            "fallback",
            "checkpoint_or_manifest_mismatch",
            "resume_parity_failure",
            "source_config_or_input_hash_mismatch",
            "dirty_source",
            "unexpected_gpu_core_or_thread_count",
            "network_unexpectedly_available",
            "budget_drift",
            "missing_task_seed_or_control_result",
            "artifact_write_or_download_failure",
        ],
        "source": {
            "commit": "1" * 40,
            "tree": "2" * 40,
            "require_clean_checkout": True,
            "bundle_manifest_sha256": "3" * 64,
        },
        "platform": {
            "selected": "private-kaggle-cpu",
            "private": True,
            "internet": False,
            "gpu": False,
            "tpu": False,
            "maximum_cpu_cores": 4,
            "worker_processes": 0,
            "torch_intraop_threads": 2,
            "torch_interop_threads": 1,
            "thread_environment": {
                "OMP_NUM_THREADS": "2",
                "MKL_NUM_THREADS": "2",
                "OPENBLAS_NUM_THREADS": "1",
                "NUMEXPR_NUM_THREADS": "1",
            },
            "notebook_wall_cap_seconds": 14_400,
            "stream_wall_cap_seconds": 2_400,
            "docker_image": "gcr.io/kaggle-images/python@sha256:" + "8" * 64,
            "kernel_run_type": "Batch",
        },
        "dependencies": {
            "python": "3.12.13",
            "torch": "2.10.0+cpu",
            "numpy": "2.0.2",
            "pydantic": "2.12.3",
            "lock_path": "uv.lock",
            "lock_bytes": 123,
            "lock_sha256": "9" * 64,
        },
        "platform_comparison": [
            {
                "platform": "private-kaggle-cpu",
                "selected": True,
                "availability": "verified through connected private notebook metadata and saved-output APIs",
                "cpu_limit": "four-core ceiling; two active Torch threads; zero workers",
                "internet_off": "private notebook metadata is internet-off and runtime probes must fail",
                "checkpoint_persistence": "versioned checkpoints retained under saved notebook output",
                "output_retention_download": "saved output listing and individual download verified",
                "reproducibility": "exact git bundle, image digest, lock hash, config and manifest hashes",
                "wall_limit": "internal notebook cap 14400 seconds and stream cap 2400 seconds",
                "runtime_basis": "two-thread local 1024-choice measurements with cloud overhead bounds",
                "cost_quota": "CPU notebook; zero accelerator quota and expected zero cost",
                "rejection_reasons": [],
            },
            {
                "platform": "private-colab-cpu",
                "selected": False,
                "availability": "manual session only; no connected status or output retrieval path",
                "cpu_limit": "dynamic CPU resources are not guaranteed",
                "internet_off": "internet-off state is not enforceable by the frozen notebook",
                "checkpoint_persistence": "runtime VM is ephemeral without external Drive mutation",
                "output_retention_download": "manual transfer would be required",
                "reproducibility": "base runtime and resources are dynamic",
                "wall_limit": "free sessions can terminate dynamically and are at most twelve hours",
                "runtime_basis": "no project-native retained Colab timing measurement",
                "cost_quota": "free tier may be zero cost but availability is dynamic",
                "rejection_reasons": ["no verifiable internet-off, persistence, and automated retrieval chain"],
            },
            {
                "platform": "github-actions-private-cpu",
                "selected": False,
                "availability": "no authorized private workflow or private-asset integration exists",
                "cpu_limit": "standard private Linux runner provides two CPUs",
                "internet_off": "hosted jobs are networked by default",
                "checkpoint_persistence": "requires explicit artifact uploads before termination",
                "output_retention_download": "artifact APIs exist but are not integrated in this project",
                "reproducibility": "runner labels are mutable and no exact image digest is frozen here",
                "wall_limit": "hosted job maximum is six hours",
                "runtime_basis": "two CPU cores are plausible but no retained project timing exists",
                "cost_quota": "would consume private Actions minutes and artifact storage",
                "rejection_reasons": ["no repository-supported private-asset workflow is retained"],
            },
        ],
        "work": {
            "seeds": list(REQUIRED_SEEDS),
            "aggregate_non_forced_choices_per_seed": 100_000,
            "allocations": allocations,
            "stateless_control_included_in_aggregate": True,
            "choices_per_update": 64,
            "ppo_epochs": 4,
            "learning_rate": 0.005,
            "adam_epsilon": 0.00001,
            "clip_coefficient": 0.2,
            "value_clip_coefficient": 0.2,
            "value_coefficient": 0.5,
            "entropy_coefficient": 0.01,
            "maximum_gradient_norm": 0.5,
            "evaluation_choices_count_toward_budget": False,
            "evaluation_cadence_choices": 4_096,
            "no_result_dependent_extension": True,
        },
        "checkpoint": {
            "cadence_choices": 4_096,
            "cadence_wall_seconds": 300,
            "maximum_payload_bytes": 536_870_912,
            "intentional_interruptions": {
                str(REQUIRED_SEEDS[0]): {
                    "stream": "recurrent-cue-v1",
                    "after_choices": 12_288,
                },
                str(REQUIRED_SEEDS[1]): {
                    "stream": "variable-option-multiselect-v1",
                    "after_choices": 12_288,
                },
                str(REQUIRED_SEEDS[2]): {
                    "stream": "recurrent-cue-v1-stateless",
                    "after_choices": 12_288,
                },
            },
            "fresh_process_restore_required": True,
            "fixed_evaluation_atol": 0.00001,
            "fixed_evaluation_rtol": 0.0,
            "content_addressed_retention": True,
        },
        "assets": {
            "dataset": {
                "owner": "ashok205",
                "slug": "kptcg-g3a-correctness-inputs",
                "version": 1,
                "publication_state": "PREPARED_LOCAL_NOT_PUBLISHED",
                "files": [
                    {"path": "g3a-cloud-source-v1.bundle", "bytes": 123, "sha256": "4" * 64},
                    {
                        "path": "g3a-cloud-source-manifest-v1.json",
                        "bytes": 234,
                        "sha256": "3" * 64,
                    },
                ],
            },
            "notebook": {
                "owner": "ashok205",
                "slug": "kptcg-g3a-cloud-correctness-v1",
                "version": 1,
                "publication_state": "PREPARED_LOCAL_NOT_PUBLISHED",
            },
        },
        "outputs": {
            "root": "/kaggle/working/kptcg-g3a-cloud-correctness-v1/output",
            "required_files": [
                "g3a-cloud-correctness-report-v1.json",
                "g3a-cloud-independent-review-v1.json",
                "g3a-cloud-output-manifest-v1.json",
                "g3a-cloud-resume-receipt-v1.json",
            ],
            "collision_policy": "FAIL_IF_EXISTS",
        },
        "acceptance": {
            "recurrent_minimum_score": 0.85,
            "stateless_maximum_score": 0.5,
            "recurrent_minimum_margin": 0.25,
            "maximum_probability_error": 0.00001,
            "budget_relative_drift_maximum": 0.0025,
            "zero_tolerance_total": 0,
            "strength_claim_allowed": False,
            "g3b_promotion_allowed": False,
        },
        "edge_case_evidence": {
            "compound_action": ["tests/g3/test_ppo.py"],
            "recurrent_ownership": ["tests/g2/test_neural_policy.py"],
            "checkpoint_resume": ["tests/g3/test_training_checkpoint.py"],
            "cloud_notebook": ["tests/g3/test_cloud_plan.py"],
        },
    }


def test_valid_plan_binds_one_hundred_thousand_choices_per_seed() -> None:
    plan = validate_cloud_plan(plan_fixture())
    assert plan["work"]["aggregate_non_forced_choices_per_seed"] == 100_000
    for seed in REQUIRED_SEEDS:
        assert sum(plan["work"]["allocations"][str(seed)].values()) == 100_000
        assert set(plan["work"]["allocations"][str(seed)]) == set(STREAMS)


def test_plan_rejects_budget_that_excludes_stateless_control() -> None:
    value = plan_fixture()
    value["work"]["stateless_control_included_in_aggregate"] = False
    with pytest.raises(CloudPlanError, match="stateless"):
        validate_cloud_plan(value)


def test_plan_rejects_budget_arithmetic_drift() -> None:
    value = plan_fixture()
    value["work"]["allocations"][str(REQUIRED_SEEDS[0])][STREAMS[0]] -= 1
    with pytest.raises(CloudPlanError, match="allocation"):
        validate_cloud_plan(value)


def test_plan_rejects_launch_authorization_or_external_mutation() -> None:
    for key in ("training_launch_authorized", "external_mutation_authorized", "submission_authorized"):
        value = plan_fixture()
        value["authorization"][key] = True
        with pytest.raises(CloudPlanError, match="authorization"):
            validate_cloud_plan(value)


def test_plan_rejects_wrong_seed_or_asset_version() -> None:
    wrong_seed = plan_fixture()
    wrong_seed["work"]["seeds"][0] = 1
    with pytest.raises(CloudPlanError, match="seed"):
        validate_cloud_plan(wrong_seed)

    wrong_version = plan_fixture()
    wrong_version["assets"]["dataset"]["version"] = 0
    with pytest.raises(CloudPlanError, match="version"):
        validate_cloud_plan(wrong_version)


def test_plan_rejects_dirty_source_and_unselected_platform() -> None:
    dirty = plan_fixture()
    dirty["source"]["require_clean_checkout"] = False
    with pytest.raises(CloudPlanError, match="clean"):
        validate_cloud_plan(dirty)

    wrong_platform = plan_fixture()
    wrong_platform["platform"]["selected"] = "private-colab-cpu"
    with pytest.raises(CloudPlanError, match="Kaggle"):
        validate_cloud_plan(wrong_platform)


def test_load_plan_requires_canonical_json(tmp_path: Path) -> None:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan_fixture(), indent=2), encoding="utf-8")
    with pytest.raises(CloudPlanError, match="canonical"):
        load_cloud_plan(path)


def test_review_rejects_missing_evidence_paths(tmp_path: Path) -> None:
    plan = plan_fixture()
    with pytest.raises(CloudPlanError, match="evidence"):
        review_cloud_plan(plan, root=tmp_path, expected_source_commit="1" * 40)


def test_download_receipt_requires_listed_and_downloaded_hash_parity() -> None:
    manifest = {
        "files": {
            "report.json": {"bytes": 4, "sha256": "a" * 64},
            "review.json": {"bytes": 5, "sha256": "b" * 64},
        }
    }
    listed = ["report.json", "review.json"]
    downloads = {
        "report.json": {"bytes": 4, "sha256": "a" * 64},
        "review.json": {"bytes": 5, "sha256": "b" * 64},
    }
    validate_download_receipt(manifest, listed_files=listed, downloaded=downloads)

    missing = copy.deepcopy(downloads)
    missing.pop("review.json")
    with pytest.raises(CloudPlanError, match="download"):
        validate_download_receipt(manifest, listed_files=listed, downloaded=missing)

    wrong_hash = copy.deepcopy(downloads)
    wrong_hash["report.json"]["sha256"] = "c" * 64
    with pytest.raises(CloudPlanError, match="SHA-256"):
        validate_download_receipt(manifest, listed_files=listed, downloaded=wrong_hash)
