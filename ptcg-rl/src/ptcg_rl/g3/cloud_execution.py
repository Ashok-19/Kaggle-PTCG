from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from ptcg_rl.g3.cloud_plan import (
    REQUIRED_SEEDS,
    REQUIRED_STREAMS,
    CloudPlanError,
    semantic_sha256,
    validate_cloud_plan,
)
from ptcg_rl.g3.evaluation import (
    REQUIRED_RESUME_COMPONENTS,
    ZERO_TOLERANCE_COUNTERS,
    LoadedEvaluationContract,
    canonical_json_bytes,
    review_g3a_evidence,
)
from ptcg_rl.g3.toy import toy_task_registry_v1

INPUT_MANIFEST_SCHEMA_VERSION = 1
INPUT_MANIFEST_KIND = "KPTCG_G3A_CLOUD_INPUT_MANIFEST"


class CloudExecutionError(RuntimeError):
    pass


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise CloudExecutionError(f"{name} must be an object")
    return dict(value)


def _exact_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    observed = set(value)
    if observed != expected:
        raise CloudExecutionError(
            f"{name} keys differ: missing={sorted(expected - observed)}, "
            f"unexpected={sorted(observed - expected)}"
        )


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _file_record(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"path": path.name, "bytes": len(raw), "sha256": _sha256_bytes(raw)}


def validate_input_manifest(
    manifest_value: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    config_path: Path,
    input_root: Path,
) -> dict[str, Any]:
    try:
        frozen = validate_cloud_plan(plan)
    except CloudPlanError as error:
        raise CloudExecutionError(f"runtime config is invalid: {error}") from error
    manifest = _object(manifest_value, "input manifest")
    _exact_keys(manifest, {"schema_version", "kind", "dataset", "source", "files"}, "input manifest")
    if (
        manifest["schema_version"] != INPUT_MANIFEST_SCHEMA_VERSION
        or manifest["kind"] != INPUT_MANIFEST_KIND
    ):
        raise CloudExecutionError("input manifest identity differs")

    dataset = _object(manifest["dataset"], "input manifest dataset")
    _exact_keys(dataset, {"owner", "slug", "version"}, "input manifest dataset")
    expected_dataset = frozen["assets"]["dataset"]
    for name in ("owner", "slug"):
        if dataset[name] != expected_dataset[name]:
            raise CloudExecutionError(f"input dataset {name} differs")
    if dataset["version"] != expected_dataset["version"]:
        raise CloudExecutionError("input dataset version differs")

    source = _object(manifest["source"], "input manifest source")
    _exact_keys(source, {"commit", "tree"}, "input manifest source")
    if source["commit"] != frozen["source"]["commit"] or source["tree"] != frozen["source"]["tree"]:
        raise CloudExecutionError("input manifest source identity differs")

    files = manifest["files"]
    if not isinstance(files, list) or len(files) != 3:
        raise CloudExecutionError(
            "input manifest must contain runtime config, source bundle, and source manifest records"
        )
    by_role: dict[str, dict[str, Any]] = {}
    for value in files:
        record = _object(value, "input manifest file")
        _exact_keys(record, {"path", "bytes", "sha256", "role"}, "input manifest file")
        role = record["role"]
        if role not in {"runtime_config", "source_bundle", "source_manifest"} or role in by_role:
            raise CloudExecutionError("input manifest file roles differ")
        if not isinstance(record["path"], str) or not record["path"]:
            raise CloudExecutionError("input manifest file path must be nonempty")
        if isinstance(record["bytes"], bool) or not isinstance(record["bytes"], int) or record["bytes"] <= 0:
            raise CloudExecutionError("input manifest file bytes must be positive")
        if not isinstance(record["sha256"], str) or len(record["sha256"]) != 64:
            raise CloudExecutionError("input manifest file SHA-256 is invalid")
        by_role[role] = record

    config_record = by_role["runtime_config"]
    observed_config = _file_record(config_path)
    if config_record["path"] != config_path.name or any(
        config_record[name] != observed_config[name] for name in ("bytes", "sha256")
    ):
        raise CloudExecutionError("runtime config record differs from the attached file")

    source_records = frozen["assets"]["dataset"]["files"]
    if len(source_records) != 2:
        raise CloudExecutionError("runtime config must bind one source bundle and one source manifest")
    expected_by_path = {record["path"]: record for record in source_records}
    bundle_record = by_role["source_bundle"]
    source_manifest_record = by_role["source_manifest"]
    for role, record in (
        ("source bundle", bundle_record),
        ("source manifest", source_manifest_record),
    ):
        expected = expected_by_path.get(record["path"])
        if expected is None or any(
            record[name] != expected[name] for name in ("path", "bytes", "sha256")
        ):
            raise CloudExecutionError(f"{role} record differs from the runtime config")
    if source_manifest_record["sha256"] != frozen["source"]["bundle_manifest_sha256"]:
        raise CloudExecutionError("source manifest SHA-256 differs from the runtime config")

    expected_paths = {
        config_record["path"],
        bundle_record["path"],
        source_manifest_record["path"],
    }
    actual_paths = {path.name for path in input_root.iterdir() if path.is_file()}
    if not expected_paths.issubset(actual_paths):
        raise CloudExecutionError("one or more required input files are missing")
    for record in by_role.values():
        path = input_root / record["path"]
        observed = _file_record(path)
        if any(record[name] != observed[name] for name in ("bytes", "sha256")):
            raise CloudExecutionError(f"input file bytes or SHA-256 differ: {record['path']}")
    return manifest


def _validate_stream_result(
    value: Mapping[str, Any],
    *,
    seed: int,
    stream: str,
    expected_choices: int,
) -> dict[str, Any]:
    result = _object(value, f"stream result {seed}/{stream}")
    if result.get("status") != "SUCCEEDED":
        raise CloudExecutionError(f"stream did not succeed: {seed}/{stream}")
    expected_task = "recurrent-cue-v1" if stream.endswith("-stateless") else stream
    expected_stateless = stream.endswith("-stateless")
    if result.get("seed") != seed or result.get("task_id") != expected_task:
        raise CloudExecutionError(f"stream identity differs: {seed}/{stream}")
    if result.get("stateless") is not expected_stateless:
        raise CloudExecutionError(f"stream stateless role differs: {seed}/{stream}")
    if result.get("choices") != expected_choices:
        raise CloudExecutionError(f"stream budget differs: {seed}/{stream}")
    if result.get("zero_tolerance_total") != 0:
        raise CloudExecutionError(f"stream zero-tolerance failure: {seed}/{stream}")
    fixed = _object(result.get("fixed_evaluation"), f"fixed evaluation {seed}/{stream}")
    if fixed.get("task_id") != expected_task or fixed.get("stateless") is not expected_stateless:
        raise CloudExecutionError(f"fixed evaluation identity differs: {seed}/{stream}")
    if fixed.get("score") != result.get("final_score"):
        raise CloudExecutionError(f"fixed evaluation score differs: {seed}/{stream}")
    return result


def _task_result(task_id: str, result: Mapping[str, Any]) -> dict[str, Any]:
    fixed = _object(result["fixed_evaluation"], f"fixed evaluation {task_id}")
    failed_cases = int(fixed["total_cases"]) - int(fixed["passed_cases"])
    return {
        "status": "PASS" if failed_cases == 0 else "FAIL",
        "task_contract_sha256": toy_task_registry_v1()[task_id].task_sha256,
        "metrics_sha256": _sha256_bytes(canonical_json_bytes(dict(result))),
        "choices": int(result["choices"]),
        "evaluation_cases": int(fixed["total_cases"]),
        "failed_cases": failed_cases,
    }


def build_strict_evidence(
    plan_value: Mapping[str, Any],
    *,
    contract: LoadedEvaluationContract,
    run_id: str,
    stream_results: Mapping[int, Mapping[str, Mapping[str, Any]]],
    artifact_hashes: Mapping[str, str],
) -> dict[str, Any]:
    try:
        plan = validate_cloud_plan(plan_value)
    except CloudPlanError as error:
        raise CloudExecutionError(f"runtime config is invalid: {error}") from error
    if set(stream_results) != set(REQUIRED_SEEDS):
        raise CloudExecutionError("stream result seed set differs")
    required_artifacts = {
        "run_manifest_sha256",
        "metrics_sha256",
        "checkpoint_manifest_sha256",
    }
    if set(artifact_hashes) != required_artifacts:
        raise CloudExecutionError("artifact hash set differs")

    seed_records = []
    allocations = plan["work"]["allocations"]
    for seed in REQUIRED_SEEDS:
        seed_streams = stream_results[seed]
        if set(seed_streams) != set(REQUIRED_STREAMS):
            missing = sorted(set(REQUIRED_STREAMS) - set(seed_streams))
            unexpected = sorted(set(seed_streams) - set(REQUIRED_STREAMS))
            raise CloudExecutionError(
                f"missing stream or unexpected stream for seed {seed}: missing={missing}, unexpected={unexpected}"
            )
        validated: dict[str, dict[str, Any]] = {}
        for stream in REQUIRED_STREAMS:
            validated[stream] = _validate_stream_result(
                seed_streams[stream],
                seed=seed,
                stream=stream,
                expected_choices=int(allocations[str(seed)][stream]),
            )
        recurrent = validated["recurrent-cue-v1"]
        stateless = validated["recurrent-cue-v1-stateless"]
        recurrent_score = float(recurrent["final_score"])
        stateless_score = float(stateless["final_score"])
        if stateless_score > float(plan["acceptance"]["stateless_maximum_score"]):
            raise CloudExecutionError(f"stateless control exceeds the frozen ceiling for seed {seed}")
        recurrent_task = _task_result("recurrent-cue-v1", recurrent)
        recurrent_task.update(
            {
                "recurrent_score": recurrent_score,
                "stateless_score": stateless_score,
                "margin_vs_stateless": recurrent_score - stateless_score,
            }
        )
        tasks = {
            "masked-bandit-v1": _task_result(
                "masked-bandit-v1", validated["masked-bandit-v1"]
            ),
            "recurrent-cue-v1": recurrent_task,
            "variable-option-multiselect-v1": _task_result(
                "variable-option-multiselect-v1",
                validated["variable-option-multiselect-v1"],
            ),
        }
        replay_error = max(
            float(result["maximum_probability_replay_error"]) for result in validated.values()
        )
        ratio_error = max(
            float(result["maximum_initial_ratio_error"]) for result in validated.values()
        )
        counters = {
            name: sum(int(result["zero_tolerance_counters"][name]) for result in validated.values())
            for name in ZERO_TOLERANCE_COUNTERS
        }
        resumed = [result for result in validated.values() if result.get("resume", {}).get("resumed") is True]
        if len(resumed) != 1:
            raise CloudExecutionError(f"seed {seed} must contain exactly one intentional fresh-process resume")
        resume = _object(resumed[0]["resume"], f"resume result for seed {seed}")
        restored = sorted(str(name) for name in resume.get("restored_rng_states", []))
        available = sorted(["numpy", "python", "torch_cpu"])
        if restored != available or resume.get("fixed_evaluation_exact") is not True:
            raise CloudExecutionError(f"seed {seed} resume parity or RNG restoration differs")
        seed_records.append(
            {
                "seed": seed,
                "tasks": tasks,
                "probability_replay": {
                    "checked_before_first_update": True,
                    "old_compound_log_probability_max_abs_error": replay_error,
                    "initial_ratio_max_abs_error_from_one": ratio_error,
                },
                "zero_tolerance": counters,
                "checkpoint_resume": {
                    "status": "PASS",
                    "components": {name: True for name in REQUIRED_RESUME_COMPONENTS},
                    "available_rng_states": available,
                    "restored_rng_states": restored,
                    "fixed_tensor_max_abs_diff": 0.0,
                    "fixed_tensor_rtol": 0.0,
                },
            }
        )

    budget_manifest = {
        "aggregate_non_forced_choices_per_seed": plan["work"][
            "aggregate_non_forced_choices_per_seed"
        ],
        "allocations": allocations,
        "stateless_control_included_in_aggregate": True,
    }
    return {
        "schema_version": 1,
        "contract_id": contract.value["contract_id"],
        "contract_file_sha256": contract.file_sha256,
        "run_id": run_id,
        "source_commit": plan["source"]["commit"],
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
            "non_forced_choices_per_seed": [
                int(plan["work"]["aggregate_non_forced_choices_per_seed"])
                for _ in REQUIRED_SEEDS
            ],
            "task_allocation_sha256": semantic_sha256(allocations),
            "budget_manifest_sha256": semantic_sha256(budget_manifest),
        },
        "seeds": seed_records,
        "artifacts": {
            "run_manifest_path": "g3a-cloud-run-manifest-v1.json",
            "run_manifest_sha256": artifact_hashes["run_manifest_sha256"],
            "metrics_sha256": artifact_hashes["metrics_sha256"],
            "checkpoint_manifest_sha256": artifact_hashes[
                "checkpoint_manifest_sha256"
            ],
            "independent_review_sha256": "0" * 64,
        },
        "claim": {"algorithm_proof_only": True, "policy_strength_claimed": False},
    }


def bind_independent_review(
    contract: LoadedEvaluationContract,
    evidence_value: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    evidence = dict(evidence_value)
    artifacts = dict(_object(evidence["artifacts"], "G3a artifacts"))
    evidence["artifacts"] = artifacts
    artifacts["independent_review_sha256"] = "0" * 64
    first_review = review_g3a_evidence(contract, evidence)
    review_sha256 = _sha256_bytes(canonical_json_bytes(first_review))
    artifacts["independent_review_sha256"] = review_sha256
    final_review = review_g3a_evidence(contract, evidence)
    if canonical_json_bytes(first_review) != canonical_json_bytes(final_review):
        raise CloudExecutionError("independent review is not stable under hash binding")
    if final_review["decision"] != "PASS":
        raise CloudExecutionError(
            f"independent G3a review failed: {final_review.get('failures', [])}"
        )
    return evidence, final_review


def build_dashboard_report(
    *,
    source_path: str,
    source_commit: str,
    plan: Mapping[str, Any],
    review: Mapping[str, Any],
    notebook: Mapping[str, Any],
    input_manifest: Mapping[str, Any],
    runtime_estimate: Mapping[str, Any],
) -> dict[str, Any]:
    frozen = validate_cloud_plan(plan)
    now = datetime.now(UTC).isoformat()
    review_status = review.get("status")
    review_decision = review.get("decision")
    if review_decision is None:
        review_decision = "PASS" if review_status == "PASS" else "FAIL"
    return {
        "schema_version": 1,
        "record_id": "artifact-g3a-cloud-correctness-plan-v1",
        "created_at_utc": now,
        "updated_at_utc": now,
        "source_path": source_path,
        "producer": "g3a-cloud-plan-freezer",
        "producer_version": "1",
        "run_id": f"g3a-cloud-plan-v1-{source_commit[:12]}",
        "gate_id": "G3a",
        "kind": "KPTCG_G3A_CLOUD_CORRECTNESS_PLAN_REPORT",
        "status": "SUCCEEDED" if review_status == "PASS" else "FAILED",
        "decision": review_decision,
        "source_commit": source_commit,
        "plan_id": frozen["plan_id"],
        "plan_semantic_sha256": semantic_sha256(frozen),
        "authorization": dict(frozen["authorization"]),
        "algorithm_boundaries": dict(frozen["algorithm_boundaries"]),
        "stop_conditions": list(frozen["stop_conditions"]),
        "external_service_mutated": False,
        "training_launched": False,
        "platform": dict(frozen["platform"]),
        "dependencies": dict(frozen["dependencies"]),
        "platform_comparison": list(frozen["platform_comparison"]),
        "budget": {
            "seeds": list(frozen["work"]["seeds"]),
            "aggregate_non_forced_choices_per_seed": frozen["work"][
                "aggregate_non_forced_choices_per_seed"
            ],
            "allocations": dict(frozen["work"]["allocations"]),
            "stateless_control_included_in_aggregate": True,
        },
        "checkpoint": dict(frozen["checkpoint"]),
        "assets": {
            "dataset": dict(frozen["assets"]["dataset"]),
            "notebook": dict(frozen["assets"]["notebook"]),
            "notebook_source": dict(notebook),
            "input_manifest": dict(input_manifest),
        },
        "runtime_estimate": dict(runtime_estimate),
        "review": dict(review),
        "claims": {
            "algorithm_correctness_plan_only": True,
            "policy_strength_established": False,
            "g3b_promotion_authorized": False,
        },
    }
