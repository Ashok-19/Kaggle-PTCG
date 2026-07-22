from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

import torch

from ptcg_rl.g3.checkpoint import restore_training_checkpoint, save_training_checkpoint
from ptcg_rl.g3.evaluation import canonical_json_bytes, load_json_object
from ptcg_rl.g3.ppo import LocalExecutionLimitsV1
from ptcg_rl.g3.toy import (
    ToyRecurrentPolicyV1,
    ToyTrainingConfigV1,
    evaluate_toy_policy,
    masked_bandit_task_v1,
    recurrent_cue_task_v1,
    toy_result_record,
    train_toy_policy,
    variable_option_multiselect_task_v1,
)

LOCAL_CORRECTNESS_SCHEMA_VERSION = 1
LOCAL_CORRECTNESS_CONFIG_SHA256 = "10874b321250cf87ff4824aafa7de35c557ad194bc76d255d2afc0d4a91471aa"


class LocalCorrectnessError(ValueError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def expected_local_correctness_config() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[3] / "configs/g3a_local_correctness_v1.json"
    if _sha256(path) != LOCAL_CORRECTNESS_CONFIG_SHA256:
        raise LocalCorrectnessError("repository local correctness config SHA-256 differs")
    return json.loads(path.read_text(encoding="utf-8"))


def load_local_correctness_config(path: Path) -> dict[str, Any]:
    value = load_json_object(path)
    if _sha256(path) != LOCAL_CORRECTNESS_CONFIG_SHA256:
        raise LocalCorrectnessError("local correctness config SHA-256 differs")
    expected = expected_local_correctness_config()
    if value != expected:
        raise LocalCorrectnessError("local correctness config differs from the frozen contract")
    return value


def _training_config(candidate: Mapping[str, Any], fixed: Mapping[str, Any]) -> ToyTrainingConfigV1:
    return ToyTrainingConfigV1(
        total_non_forced_choices=int(candidate["total_non_forced_choices"]),
        choices_per_update=int(candidate["choices_per_update"]),
        ppo_epochs=int(candidate["ppo_epochs"]),
        learning_rate=float(candidate["learning_rate"]),
        adam_epsilon=float(fixed["adam_epsilon"]),
        clip_coefficient=float(fixed["clip_coefficient"]),
        value_clip_coefficient=float(fixed["value_clip_coefficient"]),
        value_coefficient=float(fixed["value_coefficient"]),
        entropy_coefficient=float(fixed["entropy_coefficient"]),
        maximum_gradient_norm=float(fixed["maximum_gradient_norm"]),
    )


def _checkpoint_round_trip(
    *,
    model: ToyRecurrentPolicyV1,
    optimizer: torch.optim.Optimizer,
    scheduler: Any,
    task,
    stateless: bool,
    result,
    config: ToyTrainingConfigV1,
) -> dict[str, Any]:
    before = evaluate_toy_policy(model, task, stateless=stateless)
    with tempfile.TemporaryDirectory(prefix="g3a-local-checkpoint-") as directory:
        path = Path(directory) / "checkpoint.pt"
        saved = save_training_checkpoint(
            path,
            model=model,
            optimizer=optimizer,
            scheduler=scheduler,
            scaler=None,
            counters={"choices": result.choices, "updates": result.updates},
            league={"entries": ["toy-policy-v1"], "current": "toy-policy-v1"},
            rollout_boundary={"complete": True, "task_id": task.task_id},
            include_cuda_rng=False,
        )
        restored_model = ToyRecurrentPolicyV1().cpu()
        restored_optimizer = torch.optim.Adam(
            restored_model.parameters(), lr=config.learning_rate, eps=config.adam_epsilon
        )
        restored_scheduler = torch.optim.lr_scheduler.LinearLR(
            restored_optimizer,
            start_factor=1.0,
            end_factor=0.25,
            total_iters=max(result.updates, 1),
        )
        loaded = restore_training_checkpoint(
            path,
            model=restored_model,
            optimizer=restored_optimizer,
            scheduler=restored_scheduler,
            scaler=None,
            expected_sha256=saved["payload_sha256"],
            restore_rng=True,
        )
        after = evaluate_toy_policy(restored_model, task, stateless=stateless)
        model_exact = all(
            torch.equal(value, restored_model.state_dict()[name])
            for name, value in model.state_dict().items()
        )
        return {
            "status": "PASS" if before == after and model_exact else "FAIL",
            "payload_bytes": saved["payload_bytes"],
            "payload_sha256": saved["payload_sha256"],
            "fixed_evaluation_exact": before == after,
            "model_tensors_exact": model_exact,
            "counters": loaded.counters,
            "league": loaded.league,
            "rollout_boundary": loaded.rollout_boundary,
            "restored_rng_states": list(loaded.restored_rng_states),
        }


def _run_task(task, *, seed: int, config: ToyTrainingConfigV1, stateless: bool) -> dict[str, Any]:
    model, optimizer, scheduler, result = train_toy_policy(
        task,
        seed=seed,
        config=config,
        stateless=stateless,
    )
    record = toy_result_record(result)
    record["checkpoint"] = _checkpoint_round_trip(
        model=model,
        optimizer=optimizer,
        scheduler=scheduler,
        task=task,
        stateless=stateless,
        result=result,
        config=config,
    )
    return record


def _candidate_run(candidate: Mapping[str, Any], fixed: Mapping[str, Any], seed: int) -> dict[str, Any]:
    config = _training_config(candidate, fixed)
    bandit = _run_task(masked_bandit_task_v1(), seed=seed, config=config, stateless=False)
    multi = _run_task(
        variable_option_multiselect_task_v1(), seed=seed, config=config, stateless=False
    )
    cue_task = recurrent_cue_task_v1()
    recurrent = _run_task(cue_task, seed=seed, config=config, stateless=False)
    stateless = _run_task(cue_task, seed=seed, config=config, stateless=True)
    return {
        "candidate_id": candidate["candidate_id"],
        "config": asdict(config),
        "runs": {
            "masked-bandit-v1": bandit,
            "variable-option-multiselect-v1": multi,
            "recurrent-cue-v1": recurrent,
            "recurrent-cue-v1-stateless": stateless,
        },
        "recurrent_margin": recurrent["final_score"] - stateless["final_score"],
    }


def _passes(run: Mapping[str, Any], requirements: Mapping[str, Any]) -> bool:
    runs = run["runs"]
    records = list(runs.values())
    return bool(
        runs["masked-bandit-v1"]["final_score"] >= requirements["masked_bandit_score"]
        and runs["variable-option-multiselect-v1"]["final_score"]
        >= requirements["variable_option_multiselect_score"]
        and runs["recurrent-cue-v1"]["final_score"] >= requirements["minimum_recurrent_score"]
        and runs["recurrent-cue-v1-stateless"]["final_score"]
        <= requirements["maximum_stateless_score"]
        and run["recurrent_margin"] >= requirements["minimum_recurrent_margin"]
        and all(
            record["maximum_probability_replay_error"]
            <= requirements["maximum_probability_replay_error"]
            and record["maximum_initial_ratio_error"]
            <= requirements["maximum_initial_ratio_error"]
            and record["zero_tolerance_total"] == requirements["zero_tolerance_total"]
            and record["checkpoint"]["status"] == "PASS"
            for record in records
        )
    )


def run_local_correctness(
    *,
    root: Path,
    config_path: Path,
    source_commit: str,
) -> dict[str, Any]:
    if len(source_commit) != 40 or any(character not in "0123456789abcdef" for character in source_commit):
        raise LocalCorrectnessError("source commit must be a lowercase 40-character Git SHA")
    config = load_local_correctness_config(config_path)
    resources = config["resources"]
    limits = LocalExecutionLimitsV1(
        max_cpu_threads=resources["maximum_cpu_threads"],
        max_worker_processes=1,
        max_non_forced_choices=resources["maximum_non_forced_choices_per_model"],
        max_wall_seconds=resources["maximum_wall_seconds_per_model"],
        allow_cuda=False,
    )
    if resources["maximum_worker_processes"] != 0 or resources["device"] != "cpu":
        raise LocalCorrectnessError("local correctness execution must be CPU-only with zero workers")
    fixed = config["fixed_ppo"]
    candidate_runs = [
        _candidate_run(candidate, fixed, config["candidate_seed"])
        for candidate in config["candidates"]
    ]
    selected_definition = next(
        candidate
        for candidate in config["candidates"]
        if candidate["candidate_id"] == config["selected_candidate_id"]
    )
    selected_config = _training_config(selected_definition, fixed)
    if selected_config.total_non_forced_choices > limits.max_non_forced_choices:
        raise LocalCorrectnessError("selected local candidate exceeds resource limits")
    selected_runs = [
        _candidate_run(selected_definition, fixed, seed) for seed in config["declared_seeds"]
    ]
    requirements = config["pass_requirements"]
    candidate_dispositions = []
    for run in candidate_runs:
        passed = _passes(run, requirements)
        candidate_dispositions.append(
            {
                "candidate_id": run["candidate_id"],
                "passes": passed,
                "selected": run["candidate_id"] == config["selected_candidate_id"],
                "maximum_gradient_norm_before_clip": max(
                    item["maximum_gradient_norm_before_clip"]
                    for item in run["runs"].values()
                ),
                "variable_option_multiselect_score": run["runs"][
                    "variable-option-multiselect-v1"
                ]["final_score"],
                "recurrent_margin": run["recurrent_margin"],
            }
        )
    selected_pass = all(_passes(run, requirements) for run in selected_runs)
    selected_matches = next(item for item in candidate_dispositions if item["selected"])
    lower_gradient_passers = [
        item
        for item in candidate_dispositions
        if item["passes"]
        and item["maximum_gradient_norm_before_clip"]
        < selected_matches["maximum_gradient_norm_before_clip"]
    ]
    if lower_gradient_passers:
        raise LocalCorrectnessError("selected candidate is not the lowest-gradient passing candidate")
    source_paths = (
        "src/ptcg_rl/g3/ppo.py",
        "src/ptcg_rl/g3/checkpoint.py",
        "src/ptcg_rl/g3/toy.py",
        "src/ptcg_rl/g3/local_correctness.py",
        "configs/g3a_local_correctness_v1.json",
        "scripts/g3a_local_correctness.py",
    )
    report = {
        "schema_version": LOCAL_CORRECTNESS_SCHEMA_VERSION,
        "kind": "KPTCG_G3A_LOCAL_CORRECTNESS_REPORT",
        "status": "SUCCEEDED" if selected_pass else "FAILED",
        "decision": "PASS" if selected_pass else "FAIL",
        "scope": "Toy-only local PPO correctness micro-qualification; not G3a qualification or policy strength.",
        "source_commit": source_commit,
        "config": {
            "path": config_path.relative_to(root).as_posix(),
            "bytes": config_path.stat().st_size,
            "sha256": _sha256(config_path),
        },
        "source_files": [
            {
                "path": path,
                "bytes": (root / path).stat().st_size,
                "sha256": _sha256(root / path),
            }
            for path in source_paths
        ],
        "resources": {
            **resources,
            "torch_threads_observed": torch.get_num_threads(),
            "torch_interop_threads_observed": torch.get_num_interop_threads(),
        },
        "candidate_runs": candidate_runs,
        "candidate_dispositions": candidate_dispositions,
        "selected_candidate_id": config["selected_candidate_id"],
        "selected_seed_runs": selected_runs,
        "all_selected_seeds_pass": selected_pass,
        "authorization": config["authorization"],
        "training_launch_authorized": False,
        "cabt_games": 0,
        "external_service_mutated": False,
    }
    canonical_json_bytes(report)
    return report


def write_local_correctness_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    temporary.write_bytes(canonical_json_bytes(dict(report)))
    temporary.replace(path)
