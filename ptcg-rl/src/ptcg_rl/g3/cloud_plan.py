from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from ptcg_rl.g3.evaluation import canonical_json_bytes

PLAN_SCHEMA_VERSION = 1
PLAN_KIND = "KPTCG_G3A_CLOUD_CORRECTNESS_PLAN"
PLAN_ID = "g3a-cloud-correctness-v1"
REQUIRED_SEEDS = (1197953491, 20344180, 1491619630)
REQUIRED_STREAMS = (
    "masked-bandit-v1",
    "recurrent-cue-v1",
    "variable-option-multiselect-v1",
    "recurrent-cue-v1-stateless",
)
SELECTED_PLATFORM = "private-kaggle-cpu"
EXPECTED_ALGORITHM_BOUNDARIES = {
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
}
REQUIRED_STOP_CONDITIONS = (
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
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class CloudPlanError(ValueError):
    pass


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise CloudPlanError(f"{name} must be an object")
    return dict(value)


def _list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise CloudPlanError(f"{name} must be a list")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    observed = set(value)
    if observed != expected:
        raise CloudPlanError(
            f"{name} keys differ: missing={sorted(expected - observed)}, "
            f"unexpected={sorted(observed - expected)}"
        )


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CloudPlanError(f"{name} must be a positive integer")
    return value


def _finite_number(value: Any, name: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CloudPlanError(f"{name} must be numeric")
    result = float(value)
    if result != result or result in (float("inf"), float("-inf")):
        raise CloudPlanError(f"{name} must be finite")
    if minimum is not None and result < minimum:
        raise CloudPlanError(f"{name} must be at least {minimum}")
    return result


def _sha256(value: Any, name: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise CloudPlanError(f"{name} must be a lowercase SHA-256")
    return value


def _commit(value: Any, name: str) -> str:
    if not isinstance(value, str) or _COMMIT_RE.fullmatch(value) is None:
        raise CloudPlanError(f"{name} must be a lowercase 40-character commit")
    return value


def semantic_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(dict(value))).hexdigest()


def load_cloud_plan(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise CloudPlanError(f"cannot read cloud plan: {path}") from error
    if not isinstance(value, dict):
        raise CloudPlanError("cloud plan root must be an object")
    if canonical_json_bytes(value) != raw:
        raise CloudPlanError("cloud plan must use canonical JSON")
    return validate_cloud_plan(value)


def validate_cloud_plan(value: Mapping[str, Any]) -> dict[str, Any]:
    plan = _object(value, "cloud plan")
    _exact_keys(
        plan,
        {
            "schema_version",
            "kind",
            "plan_id",
            "authorization",
            "algorithm_boundaries",
            "stop_conditions",
            "source",
            "platform",
            "dependencies",
            "platform_comparison",
            "work",
            "checkpoint",
            "assets",
            "outputs",
            "acceptance",
            "edge_case_evidence",
        },
        "cloud plan",
    )
    if plan["schema_version"] != PLAN_SCHEMA_VERSION or plan["kind"] != PLAN_KIND:
        raise CloudPlanError("cloud plan identity differs")
    if plan["plan_id"] != PLAN_ID:
        raise CloudPlanError("cloud plan ID differs")

    authorization = _object(plan["authorization"], "authorization")
    _exact_keys(
        authorization,
        {"training_launch_authorized", "external_mutation_authorized", "submission_authorized"},
        "authorization",
    )
    if any(value is not False for value in authorization.values()):
        raise CloudPlanError("authorization must remain false before explicit user approval")

    boundaries = _object(plan["algorithm_boundaries"], "algorithm boundaries")
    if boundaries != EXPECTED_ALGORITHM_BOUNDARIES:
        raise CloudPlanError("algorithm boundaries differ from the frozen G3a contract")
    stop_conditions = _list(plan["stop_conditions"], "stop conditions")
    if tuple(stop_conditions) != REQUIRED_STOP_CONDITIONS:
        raise CloudPlanError("fail-closed stop conditions differ from the frozen plan")

    source = _object(plan["source"], "source")
    _exact_keys(
        source,
        {"commit", "tree", "require_clean_checkout", "bundle_manifest_sha256"},
        "source",
    )
    _commit(source["commit"], "source commit")
    _commit(source["tree"], "source tree")
    _sha256(source["bundle_manifest_sha256"], "source bundle manifest SHA-256")
    if source["require_clean_checkout"] is not True:
        raise CloudPlanError("source must require a clean checkout")

    platform = _object(plan["platform"], "platform")
    _exact_keys(
        platform,
        {
            "selected",
            "private",
            "internet",
            "gpu",
            "tpu",
            "maximum_cpu_cores",
            "worker_processes",
            "torch_intraop_threads",
            "torch_interop_threads",
            "thread_environment",
            "notebook_wall_cap_seconds",
            "stream_wall_cap_seconds",
            "docker_image",
            "kernel_run_type",
        },
        "platform",
    )
    if platform["selected"] != SELECTED_PLATFORM:
        raise CloudPlanError("the frozen plan must select private Kaggle CPU")
    if platform["private"] is not True or any(
        platform[name] is not False for name in ("internet", "gpu", "tpu")
    ):
        raise CloudPlanError("Kaggle plan must be private, CPU-only, and internet-off")
    cores = _positive_int(platform["maximum_cpu_cores"], "maximum CPU cores")
    if cores > 4:
        raise CloudPlanError("maximum CPU cores exceeds four")
    if platform["worker_processes"] != 0:
        raise CloudPlanError("worker processes must be zero")
    intraop = _positive_int(platform["torch_intraop_threads"], "Torch intra-op threads")
    interop = _positive_int(platform["torch_interop_threads"], "Torch inter-op threads")
    if intraop > cores or interop > 1:
        raise CloudPlanError("Torch thread limits exceed the frozen CPU envelope")
    thread_environment = _object(platform["thread_environment"], "thread environment")
    expected_environment = {
        "OMP_NUM_THREADS": str(intraop),
        "MKL_NUM_THREADS": str(intraop),
        "OPENBLAS_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
    }
    if thread_environment != expected_environment:
        raise CloudPlanError("thread environment differs from the frozen envelope")
    _positive_int(platform["notebook_wall_cap_seconds"], "notebook wall cap")
    _positive_int(platform["stream_wall_cap_seconds"], "stream wall cap")
    docker_image = platform["docker_image"]
    if (
        not isinstance(docker_image, str)
        or not docker_image.startswith("gcr.io/kaggle-images/python@sha256:")
        or len(docker_image.rsplit(":", 1)[-1]) != 64
    ):
        raise CloudPlanError("Kaggle Docker image digest is invalid")
    if platform["kernel_run_type"] != "Batch":
        raise CloudPlanError("Kaggle kernel run type must be Batch")

    dependencies = _object(plan["dependencies"], "dependencies")
    _exact_keys(
        dependencies,
        {"python", "torch", "numpy", "pydantic", "lock_path", "lock_bytes", "lock_sha256"},
        "dependencies",
    )
    expected_versions = {
        "python": "3.12.13",
        "torch": "2.10.0+cpu",
        "numpy": "2.0.2",
        "pydantic": "2.12.3",
    }
    for name, expected in expected_versions.items():
        if dependencies[name] != expected:
            raise CloudPlanError(f"dependency {name} version differs")
    if dependencies["lock_path"] != "uv.lock":
        raise CloudPlanError("dependency lock path differs")
    _positive_int(dependencies["lock_bytes"], "dependency lock bytes")
    _sha256(dependencies["lock_sha256"], "dependency lock SHA-256")

    comparison = _list(plan["platform_comparison"], "platform comparison")
    if len(comparison) < 3:
        raise CloudPlanError("platform comparison must retain at least three branches")
    selected_entries = []
    compared_names = set()
    for index, entry_value in enumerate(comparison):
        entry = _object(entry_value, f"platform comparison entry {index}")
        _exact_keys(
            entry,
            {
                "platform",
                "selected",
                "availability",
                "cpu_limit",
                "internet_off",
                "checkpoint_persistence",
                "output_retention_download",
                "reproducibility",
                "wall_limit",
                "runtime_basis",
                "cost_quota",
                "rejection_reasons",
            },
            "platform comparison entry",
        )
        name = entry["platform"]
        if not isinstance(name, str) or not name or name in compared_names:
            raise CloudPlanError("platform comparison names must be unique nonempty strings")
        compared_names.add(name)
        for detail in (
            "availability",
            "cpu_limit",
            "internet_off",
            "checkpoint_persistence",
            "output_retention_download",
            "reproducibility",
            "wall_limit",
            "runtime_basis",
            "cost_quota",
        ):
            if not isinstance(entry[detail], str) or not entry[detail]:
                raise CloudPlanError(f"platform comparison {detail} must be nonempty")
        reasons = _list(entry["rejection_reasons"], "platform rejection reasons")
        if entry["selected"] is True:
            selected_entries.append(name)
            if reasons:
                raise CloudPlanError("selected platform cannot have rejection reasons")
        elif entry["selected"] is False:
            if not reasons or any(not isinstance(reason, str) or not reason for reason in reasons):
                raise CloudPlanError("rejected platforms require explicit reasons")
        else:
            raise CloudPlanError("platform selected flag must be boolean")
    if selected_entries != [SELECTED_PLATFORM]:
        raise CloudPlanError("platform comparison selection differs")

    work = _object(plan["work"], "work")
    _exact_keys(
        work,
        {
            "seeds",
            "aggregate_non_forced_choices_per_seed",
            "allocations",
            "stateless_control_included_in_aggregate",
            "rollout_sampling",
            "rollout_seed_xor",
            "choices_per_update",
            "ppo_epochs",
            "learning_rate",
            "adam_epsilon",
            "clip_coefficient",
            "value_clip_coefficient",
            "value_coefficient",
            "entropy_coefficient",
            "maximum_gradient_norm",
            "evaluation_choices_count_toward_budget",
            "evaluation_cadence_choices",
            "no_result_dependent_extension",
        },
        "work",
    )
    if work["seeds"] != list(REQUIRED_SEEDS):
        raise CloudPlanError("declared seed set or order differs")
    aggregate = _positive_int(
        work["aggregate_non_forced_choices_per_seed"],
        "aggregate non-forced choices per seed",
    )
    if aggregate != 100_000:
        raise CloudPlanError("aggregate budget must be exactly 100,000 choices per seed")
    if work["stateless_control_included_in_aggregate"] is not True:
        raise CloudPlanError("stateless control must be included in the aggregate budget")
    if work["rollout_sampling"] != "seeded_categorical":
        raise CloudPlanError("rollout sampling must be seeded categorical")
    if work["rollout_seed_xor"] != 0x5A17:
        raise CloudPlanError("rollout seed XOR differs from the frozen value")
    allocations = _object(work["allocations"], "allocations")
    if set(allocations) != {str(seed) for seed in REQUIRED_SEEDS}:
        raise CloudPlanError("allocation seed keys differ")
    for seed in REQUIRED_SEEDS:
        seed_allocation = _object(allocations[str(seed)], f"allocation for seed {seed}")
        if set(seed_allocation) != set(REQUIRED_STREAMS):
            raise CloudPlanError(f"allocation streams differ for seed {seed}")
        amounts = [_positive_int(seed_allocation[stream], f"allocation {seed}/{stream}") for stream in REQUIRED_STREAMS]
        if any(amount != 25_000 for amount in amounts) or sum(amounts) != aggregate:
            raise CloudPlanError(f"allocation arithmetic differs for seed {seed}")
    _positive_int(work["choices_per_update"], "choices per update")
    _positive_int(work["ppo_epochs"], "PPO epochs")
    for name in (
        "learning_rate",
        "adam_epsilon",
        "clip_coefficient",
        "value_clip_coefficient",
        "value_coefficient",
        "entropy_coefficient",
        "maximum_gradient_norm",
    ):
        _finite_number(work[name], name, minimum=0.0)
    if work["evaluation_choices_count_toward_budget"] is not False:
        raise CloudPlanError("evaluation choices must not count toward the training budget")
    _positive_int(work["evaluation_cadence_choices"], "evaluation cadence choices")
    if work["no_result_dependent_extension"] is not True:
        raise CloudPlanError("result-dependent budget extension must be forbidden")

    checkpoint = _object(plan["checkpoint"], "checkpoint")
    _exact_keys(
        checkpoint,
        {
            "cadence_choices",
            "cadence_wall_seconds",
            "maximum_payload_bytes",
            "intentional_interruptions",
            "fresh_process_restore_required",
            "fixed_evaluation_atol",
            "fixed_evaluation_rtol",
            "content_addressed_retention",
        },
        "checkpoint",
    )
    cadence_choices = _positive_int(checkpoint["cadence_choices"], "checkpoint cadence choices")
    choices_per_update = int(work["choices_per_update"])
    if cadence_choices % choices_per_update:
        raise CloudPlanError("checkpoint cadence must align with update boundaries")
    _positive_int(checkpoint["cadence_wall_seconds"], "checkpoint cadence wall seconds")
    _positive_int(checkpoint["maximum_payload_bytes"], "maximum checkpoint payload bytes")
    interruptions = _object(checkpoint["intentional_interruptions"], "intentional interruptions")
    if set(interruptions) != {str(seed) for seed in REQUIRED_SEEDS}:
        raise CloudPlanError("intentional interruption seeds differ")
    for seed in REQUIRED_SEEDS:
        interruption = _object(interruptions[str(seed)], f"interruption for seed {seed}")
        _exact_keys(interruption, {"stream", "after_choices"}, "intentional interruption")
        if interruption["stream"] not in REQUIRED_STREAMS:
            raise CloudPlanError("intentional interruption stream differs")
        after_choices = _positive_int(interruption["after_choices"], "intentional interruption choices")
        if after_choices >= 25_000 or after_choices % choices_per_update:
            raise CloudPlanError("intentional interruption must be an aligned interior boundary")
    if checkpoint["fresh_process_restore_required"] is not True:
        raise CloudPlanError("fresh-process restore must be required")
    if checkpoint["content_addressed_retention"] is not True:
        raise CloudPlanError("content-addressed checkpoint retention must be required")
    if _finite_number(checkpoint["fixed_evaluation_atol"], "fixed evaluation atol", minimum=0) != 1e-5:
        raise CloudPlanError("fixed evaluation atol differs")
    if _finite_number(checkpoint["fixed_evaluation_rtol"], "fixed evaluation rtol", minimum=0) != 0:
        raise CloudPlanError("fixed evaluation rtol differs")

    assets = _object(plan["assets"], "assets")
    _exact_keys(assets, {"dataset", "notebook"}, "assets")
    dataset = _object(assets["dataset"], "dataset asset")
    _exact_keys(
        dataset,
        {"owner", "slug", "version", "publication_state", "files"},
        "dataset asset",
    )
    for name in ("owner", "slug", "publication_state"):
        if not isinstance(dataset[name], str) or not dataset[name]:
            raise CloudPlanError(f"dataset {name} must be nonempty")
    _positive_int(dataset["version"], "dataset version")
    files = _list(dataset["files"], "dataset files")
    if not files:
        raise CloudPlanError("dataset files must be nonempty")
    file_names = set()
    for file_value in files:
        file_record = _object(file_value, "dataset file")
        _exact_keys(file_record, {"path", "bytes", "sha256"}, "dataset file")
        path = file_record["path"]
        if not isinstance(path, str) or not path or path in file_names:
            raise CloudPlanError("dataset file paths must be unique and nonempty")
        file_names.add(path)
        _positive_int(file_record["bytes"], f"dataset file bytes {path}")
        _sha256(file_record["sha256"], f"dataset file SHA-256 {path}")
    notebook = _object(assets["notebook"], "notebook asset")
    _exact_keys(
        notebook,
        {"owner", "slug", "version", "publication_state"},
        "notebook asset",
    )
    for name in ("owner", "slug", "publication_state"):
        if not isinstance(notebook[name], str) or not notebook[name]:
            raise CloudPlanError(f"notebook {name} must be nonempty")
    _positive_int(notebook["version"], "notebook version")

    outputs = _object(plan["outputs"], "outputs")
    _exact_keys(outputs, {"root", "required_files", "collision_policy"}, "outputs")
    if not isinstance(outputs["root"], str) or not outputs["root"].startswith("/kaggle/working/"):
        raise CloudPlanError("output root must be under /kaggle/working")
    required_files = _list(outputs["required_files"], "required output files")
    if not required_files or len(required_files) != len(set(required_files)):
        raise CloudPlanError("required output files must be unique and nonempty")
    if outputs["collision_policy"] != "FAIL_IF_EXISTS":
        raise CloudPlanError("output collision policy must fail closed")

    acceptance = _object(plan["acceptance"], "acceptance")
    _exact_keys(
        acceptance,
        {
            "recurrent_minimum_score",
            "stateless_maximum_score",
            "recurrent_minimum_margin",
            "maximum_probability_error",
            "budget_relative_drift_maximum",
            "zero_tolerance_total",
            "strength_claim_allowed",
            "g3b_promotion_allowed",
        },
        "acceptance",
    )
    expected_numbers = {
        "recurrent_minimum_score": 0.85,
        "stateless_maximum_score": 0.5,
        "recurrent_minimum_margin": 0.25,
        "maximum_probability_error": 1e-5,
        "budget_relative_drift_maximum": 0.0025,
    }
    for name, expected in expected_numbers.items():
        if _finite_number(acceptance[name], name, minimum=0) != expected:
            raise CloudPlanError(f"acceptance {name} differs")
    if acceptance["zero_tolerance_total"] != 0:
        raise CloudPlanError("zero-tolerance acceptance must equal zero")
    if acceptance["strength_claim_allowed"] is not False or acceptance["g3b_promotion_allowed"] is not False:
        raise CloudPlanError("G3a strength and G3b claims must remain forbidden")

    evidence = _object(plan["edge_case_evidence"], "edge-case evidence")
    required_evidence = {"compound_action", "recurrent_ownership", "checkpoint_resume", "cloud_notebook"}
    _exact_keys(evidence, required_evidence, "edge-case evidence")
    for category, paths in evidence.items():
        path_list = _list(paths, f"edge-case evidence {category}")
        if not path_list or any(not isinstance(path, str) or not path for path in path_list):
            raise CloudPlanError(f"edge-case evidence {category} must list test paths")

    return plan


def review_cloud_plan(
    value: Mapping[str, Any],
    *,
    root: Path,
    expected_source_commit: str,
) -> dict[str, Any]:
    plan = validate_cloud_plan(value)
    expected = _commit(expected_source_commit, "expected source commit")
    if plan["source"]["commit"] != expected:
        raise CloudPlanError("source commit differs from the reviewed clean commit")
    missing = []
    for paths in plan["edge_case_evidence"].values():
        for relative in paths:
            if not (root / relative).is_file():
                missing.append(relative)
    if missing:
        raise CloudPlanError(f"edge-case evidence paths are missing: {sorted(set(missing))}")
    return {
        "schema_version": 1,
        "kind": "KPTCG_G3A_CLOUD_PLAN_REVIEW",
        "record_id": "g3a-cloud-plan-review-v1",
        "status": "PASS",
        "plan_id": plan["plan_id"],
        "source_commit": expected,
        "plan_semantic_sha256": semantic_sha256(plan),
        "budget": {
            "choices_per_seed": plan["work"]["aggregate_non_forced_choices_per_seed"],
            "same_across_seeds": True,
            "stateless_included": True,
        },
        "authorization": dict(plan["authorization"]),
        "strength_claim_allowed": False,
    }


def validate_download_receipt(
    manifest: Mapping[str, Any],
    *,
    listed_files: list[str],
    downloaded: Mapping[str, Mapping[str, Any]],
) -> None:
    manifest_object = _object(manifest, "output manifest")
    files = _object(manifest_object.get("files"), "output manifest files")
    expected_names = set(files)
    if set(listed_files) != expected_names:
        raise CloudPlanError("output list differs from the notebook manifest")
    if set(downloaded) != expected_names:
        raise CloudPlanError("downloaded output set differs from the notebook manifest")
    for name, expected_value in files.items():
        expected = _object(expected_value, f"output manifest file {name}")
        observed = _object(downloaded[name], f"download receipt file {name}")
        if observed.get("bytes") != expected.get("bytes"):
            raise CloudPlanError(f"download byte count differs for {name}")
        if observed.get("sha256") != expected.get("sha256"):
            raise CloudPlanError(f"download SHA-256 differs for {name}")
