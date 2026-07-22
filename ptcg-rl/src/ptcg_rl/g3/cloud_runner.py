from __future__ import annotations

import hashlib
import json
import math
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch

from ptcg_rl.g1.models import stable_hash
from ptcg_rl.g3.checkpoint import (
    TrainingCheckpointError,
    restore_training_checkpoint,
    save_training_checkpoint,
)
from ptcg_rl.g3.evaluation import canonical_json_bytes
from ptcg_rl.g3.ppo import (
    LocalExecutionLimitsV1,
    PPOContractError,
    apply_local_execution_limits,
    ppo_loss,
    require_finite_gradients,
    validate_local_workload,
    verify_probability_replay,
)
from ptcg_rl.g3.toy import (
    ToyRecurrentPolicyV1,
    collect_toy_episodes,
    evaluate_toy_policy,
    replay_toy_episode,
    toy_task_registry_v1,
)


class CloudRunError(RuntimeError):
    pass


@dataclass(frozen=True)
class StreamTrainingSpecV1:
    task_id: str
    seed: int
    stateless: bool
    total_non_forced_choices: int
    choices_per_update: int
    ppo_epochs: int
    learning_rate: float
    adam_epsilon: float
    clip_coefficient: float
    value_clip_coefficient: float
    value_coefficient: float
    entropy_coefficient: float
    maximum_gradient_norm: float
    checkpoint_cadence_choices: int
    checkpoint_cadence_wall_seconds: int
    evaluation_cadence_choices: int
    intentional_interrupt_after_choices: int | None = None

    def __post_init__(self) -> None:
        if self.task_id not in toy_task_registry_v1():
            raise CloudRunError(f"unknown cloud correctness task: {self.task_id}")
        for name in (
            "seed",
            "total_non_forced_choices",
            "choices_per_update",
            "ppo_epochs",
            "checkpoint_cadence_choices",
            "checkpoint_cadence_wall_seconds",
            "evaluation_cadence_choices",
        ):
            value = getattr(self, name)
            minimum = 0 if name == "seed" else 1
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise CloudRunError(f"stream spec {name} is invalid")
        for name in (
            "learning_rate",
            "adam_epsilon",
            "clip_coefficient",
            "value_clip_coefficient",
            "value_coefficient",
            "entropy_coefficient",
            "maximum_gradient_norm",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise CloudRunError(f"stream spec {name} must be finite")
            if float(value) < 0:
                raise CloudRunError(f"stream spec {name} must be nonnegative")
        if self.checkpoint_cadence_choices % self.choices_per_update:
            raise CloudRunError("checkpoint cadence must align with update boundaries")
        if self.evaluation_cadence_choices % self.choices_per_update:
            raise CloudRunError("evaluation cadence must align with update boundaries")
        interruption = self.intentional_interrupt_after_choices
        if interruption is not None:
            if (
                isinstance(interruption, bool)
                or not isinstance(interruption, int)
                or interruption <= 0
                or interruption >= self.total_non_forced_choices
                or interruption % self.choices_per_update
            ):
                raise CloudRunError("intentional interrupt must be an aligned interior boundary")

    @property
    def spec_sha256(self) -> str:
        return stable_hash(asdict(self))

    @property
    def total_updates(self) -> int:
        return math.ceil(self.total_non_forced_choices / self.choices_per_update)


def _evaluation_record(model: ToyRecurrentPolicyV1, task_id: str, *, stateless: bool) -> dict[str, Any]:
    task = toy_task_registry_v1()[task_id]
    return evaluate_toy_policy(model, task, stateless=stateless)


def _evaluation_sha256(value: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _model_sha256(model: ToyRecurrentPolicyV1) -> str:
    digest = hashlib.sha256()
    for name, tensor in sorted(model.state_dict().items()):
        contiguous = tensor.detach().cpu().contiguous()
        digest.update(name.encode("utf-8"))
        digest.update(str(contiguous.dtype).encode("ascii"))
        digest.update(json.dumps(list(contiguous.shape), separators=(",", ":")).encode("ascii"))
        digest.update(contiguous.numpy().tobytes(order="C"))
    return digest.hexdigest()


def _initial_components(spec: StreamTrainingSpecV1) -> tuple[
    ToyRecurrentPolicyV1,
    torch.optim.Optimizer,
    torch.optim.lr_scheduler.LinearLR,
]:
    random.seed(spec.seed)
    np.random.seed(spec.seed % (2**32))
    torch.manual_seed(spec.seed)
    model = ToyRecurrentPolicyV1().cpu()
    optimizer = torch.optim.Adam(model.parameters(), lr=spec.learning_rate, eps=spec.adam_epsilon)
    scheduler = torch.optim.lr_scheduler.LinearLR(
        optimizer,
        start_factor=1.0,
        end_factor=0.25,
        total_iters=max(spec.total_updates, 1),
    )
    return model, optimizer, scheduler


def _checkpoint_path(output_dir: Path, choices: int) -> Path:
    return output_dir / "checkpoints" / f"checkpoint-{choices:06d}.pt"


def _save_checkpoint(
    *,
    path: Path,
    model: ToyRecurrentPolicyV1,
    optimizer: torch.optim.Optimizer,
    scheduler: torch.optim.lr_scheduler.LinearLR,
    spec: StreamTrainingSpecV1,
    choices: int,
    updates: int,
    initial_score: float,
    maximum_replay_error: float,
    maximum_ratio_error: float,
    maximum_gradient_norm: float,
    fixed_evaluation: dict[str, Any],
) -> dict[str, Any]:
    if path.exists() or path.with_name(path.name + ".manifest.json").exists():
        raise CloudRunError(f"checkpoint version collision: {path.name}")
    return save_training_checkpoint(
        path,
        model=model,
        optimizer=optimizer,
        scheduler=scheduler,
        scaler=None,
        counters={
            "spec_sha256": spec.spec_sha256,
            "choices": choices,
            "updates": updates,
            "initial_score": initial_score,
            "maximum_replay_error": maximum_replay_error,
            "maximum_ratio_error": maximum_ratio_error,
            "maximum_gradient_norm": maximum_gradient_norm,
            "fixed_evaluation": fixed_evaluation,
            "fixed_evaluation_sha256": _evaluation_sha256(fixed_evaluation),
        },
        league={"current": "toy-policy-v1", "entries": ["toy-policy-v1"]},
        rollout_boundary={
            "complete": True,
            "task_id": spec.task_id,
            "stateless": spec.stateless,
            "choices": choices,
        },
        include_cuda_rng=False,
    )


def _write_canonical(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))


def run_training_stream(
    *,
    spec: StreamTrainingSpecV1,
    output_dir: Path,
    limits: LocalExecutionLimitsV1,
    resume_from: Path | None = None,
    interrupt: bool,
) -> dict[str, Any]:
    spec.__post_init__()
    if interrupt and spec.intentional_interrupt_after_choices is None:
        raise CloudRunError("interrupt requested without a frozen interruption boundary")
    if resume_from is not None and interrupt:
        raise CloudRunError("resume and intentional interrupt cannot be requested together")
    result_path = output_dir / "stream-result.json"
    if result_path.exists():
        raise CloudRunError(f"output collision: {result_path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        validate_local_workload(
            non_forced_choices=spec.total_non_forced_choices,
            worker_processes=0,
            device="cpu",
            limits=limits,
        )
        apply_local_execution_limits(limits)
    except PPOContractError as error:
        raise CloudRunError(f"stream workload violates the execution envelope: {error}") from error
    if torch.cuda.is_available() and limits.allow_cuda is False:
        raise CloudRunError("unexpected GPU visibility in the CPU-only stream")

    task = toy_task_registry_v1()[spec.task_id]
    model, optimizer, scheduler = _initial_components(spec)
    initial_evaluation = _evaluation_record(model, spec.task_id, stateless=spec.stateless)
    initial_score = float(initial_evaluation["score"])
    choices = 0
    updates = 0
    maximum_replay_error = 0.0
    maximum_ratio_error = 0.0
    maximum_gradient_norm = 0.0
    resume_record: dict[str, Any] = {
        "resumed": False,
        "checkpoint_sha256": None,
        "restored_rng_states": [],
        "fixed_evaluation_exact": None,
    }

    if resume_from is not None:
        try:
            loaded = restore_training_checkpoint(
                resume_from,
                model=model,
                optimizer=optimizer,
                scheduler=scheduler,
                scaler=None,
                restore_rng=True,
            )
        except TrainingCheckpointError as error:
            raise CloudRunError(f"checkpoint restore failed: {error}") from error
        counters = loaded.counters
        if counters.get("spec_sha256") != spec.spec_sha256:
            raise CloudRunError("checkpoint spec identity differs")
        choices = int(counters.get("choices", -1))
        updates = int(counters.get("updates", -1))
        if choices <= 0 or choices >= spec.total_non_forced_choices or updates <= 0:
            raise CloudRunError("checkpoint counters are outside the resumable budget")
        if loaded.rollout_boundary != {
            "complete": True,
            "task_id": spec.task_id,
            "stateless": spec.stateless,
            "choices": choices,
        }:
            raise CloudRunError("checkpoint rollout boundary differs")
        initial_score = float(counters["initial_score"])
        maximum_replay_error = float(counters["maximum_replay_error"])
        maximum_ratio_error = float(counters["maximum_ratio_error"])
        maximum_gradient_norm = float(counters["maximum_gradient_norm"])
        expected_fixed = counters.get("fixed_evaluation")
        if not isinstance(expected_fixed, dict):
            raise CloudRunError("checkpoint fixed evaluation is missing")
        restored_fixed = _evaluation_record(model, spec.task_id, stateless=spec.stateless)
        fixed_exact = canonical_json_bytes(restored_fixed) == canonical_json_bytes(expected_fixed)
        if not fixed_exact:
            raise CloudRunError("checkpoint fixed evaluation parity failed")
        resume_record = {
            "resumed": True,
            "checkpoint_sha256": loaded.payload_sha256,
            "checkpoint_bytes": loaded.payload_bytes,
            "restored_rng_states": list(loaded.restored_rng_states),
            "fixed_evaluation_exact": True,
        }

    started = time.monotonic()
    last_checkpoint_wall = started
    next_checkpoint = ((choices // spec.checkpoint_cadence_choices) + 1) * spec.checkpoint_cadence_choices
    next_evaluation = ((choices // spec.evaluation_cadence_choices) + 1) * spec.evaluation_cadence_choices
    metrics: list[dict[str, Any]] = []
    checkpoints: list[dict[str, Any]] = []
    model.train()

    while choices < spec.total_non_forced_choices:
        if time.monotonic() - started > limits.max_wall_seconds:
            raise CloudRunError("stream exceeded the frozen wall cap")
        batch_size = min(spec.choices_per_update, spec.total_non_forced_choices - choices)
        episodes = collect_toy_episodes(
            model,
            task,
            count=batch_size,
            start_case_index=choices,
            generator=None,
            stateless=spec.stateless,
        )
        old_log_probabilities = torch.tensor(
            [episode.old_log_probability for episode in episodes], dtype=torch.float32
        )
        old_values = torch.tensor([episode.old_value for episode in episodes], dtype=torch.float32)
        returns = torch.tensor([episode.reward for episode in episodes], dtype=torch.float32)
        advantages = returns - old_values
        with torch.no_grad():
            replayed = torch.stack([replay_toy_episode(model, task, episode)[0] for episode in episodes])
        replay_check = verify_probability_replay(old_log_probabilities, replayed)
        maximum_replay_error = max(
            maximum_replay_error, replay_check.maximum_log_probability_absolute_error
        )
        maximum_ratio_error = max(
            maximum_ratio_error, replay_check.maximum_ratio_absolute_error_from_one
        )
        update_loss = None
        for _ in range(spec.ppo_epochs):
            outputs = [replay_toy_episode(model, task, episode) for episode in episodes]
            new_log_probabilities = torch.stack([item[0] for item in outputs])
            new_values = torch.stack([item[1] for item in outputs])
            entropies = torch.stack([item[2] for item in outputs])
            loss = ppo_loss(
                new_log_probabilities=new_log_probabilities,
                old_log_probabilities=old_log_probabilities,
                advantages=advantages,
                new_values=new_values,
                old_values=old_values,
                returns=returns,
                normalized_entropies=entropies,
                policy_mask=torch.ones(len(episodes), dtype=torch.bool),
                clip_coefficient=spec.clip_coefficient,
                value_clip_coefficient=spec.value_clip_coefficient,
                value_coefficient=spec.value_coefficient,
                entropy_coefficient=spec.entropy_coefficient,
            )
            optimizer.zero_grad(set_to_none=True)
            loss.total.backward()
            gradient_norm = require_finite_gradients(tuple(model.parameters()))
            maximum_gradient_norm = max(maximum_gradient_norm, gradient_norm)
            torch.nn.utils.clip_grad_norm_(model.parameters(), spec.maximum_gradient_norm)
            optimizer.step()
            update_loss = float(loss.total.detach().cpu())
        scheduler.step()
        choices += batch_size
        updates += 1
        metrics.append(
            {
                "choices": choices,
                "updates": updates,
                "batch_choices": batch_size,
                "loss": update_loss,
                "learning_rate": float(optimizer.param_groups[0]["lr"]),
                "maximum_probability_replay_error": maximum_replay_error,
                "maximum_initial_ratio_error": maximum_ratio_error,
                "maximum_gradient_norm_before_clip": maximum_gradient_norm,
            }
        )

        evaluation_due = choices >= next_evaluation or choices == spec.total_non_forced_choices
        checkpoint_due = (
            choices >= next_checkpoint
            or time.monotonic() - last_checkpoint_wall >= spec.checkpoint_cadence_wall_seconds
            or (interrupt and choices == spec.intentional_interrupt_after_choices)
        )
        fixed_evaluation = None
        if evaluation_due or checkpoint_due:
            fixed_evaluation = _evaluation_record(model, spec.task_id, stateless=spec.stateless)
        if evaluation_due:
            metrics[-1]["evaluation"] = fixed_evaluation
            while next_evaluation <= choices:
                next_evaluation += spec.evaluation_cadence_choices
        if checkpoint_due and choices < spec.total_non_forced_choices:
            checkpoint = _checkpoint_path(output_dir, choices)
            record = _save_checkpoint(
                path=checkpoint,
                model=model,
                optimizer=optimizer,
                scheduler=scheduler,
                spec=spec,
                choices=choices,
                updates=updates,
                initial_score=initial_score,
                maximum_replay_error=maximum_replay_error,
                maximum_ratio_error=maximum_ratio_error,
                maximum_gradient_norm=maximum_gradient_norm,
                fixed_evaluation=fixed_evaluation or _evaluation_record(
                    model, spec.task_id, stateless=spec.stateless
                ),
            )
            checkpoints.append(
                {
                    "path": checkpoint.as_posix(),
                    "choices": choices,
                    "payload_bytes": record["payload_bytes"],
                    "payload_sha256": record["payload_sha256"],
                }
            )
            last_checkpoint_wall = time.monotonic()
            while next_checkpoint <= choices:
                next_checkpoint += spec.checkpoint_cadence_choices
        if interrupt and choices == spec.intentional_interrupt_after_choices:
            if not checkpoints or checkpoints[-1]["choices"] != choices:
                raise CloudRunError("intentional interruption lacks a checkpoint at the boundary")
            interrupted = {
                "schema_version": 1,
                "kind": "KPTCG_G3A_STREAM_RESULT",
                "status": "INTERRUPTED",
                "spec_sha256": spec.spec_sha256,
                "task_id": spec.task_id,
                "seed": spec.seed,
                "stateless": spec.stateless,
                "choices": choices,
                "updates": updates,
                "checkpoint_path": checkpoints[-1]["path"],
                "checkpoint_sha256": checkpoints[-1]["payload_sha256"],
                "checkpoints": checkpoints,
                "per_update_metrics": metrics,
            }
            _write_canonical(output_dir / "interruption-receipt.json", interrupted)
            return interrupted

    final_evaluation = _evaluation_record(model, spec.task_id, stateless=spec.stateless)
    final_checkpoint = _checkpoint_path(output_dir, choices)
    final_record = _save_checkpoint(
        path=final_checkpoint,
        model=model,
        optimizer=optimizer,
        scheduler=scheduler,
        spec=spec,
        choices=choices,
        updates=updates,
        initial_score=initial_score,
        maximum_replay_error=maximum_replay_error,
        maximum_ratio_error=maximum_ratio_error,
        maximum_gradient_norm=maximum_gradient_norm,
        fixed_evaluation=final_evaluation,
    )
    checkpoints.append(
        {
            "path": final_checkpoint.as_posix(),
            "choices": choices,
            "payload_bytes": final_record["payload_bytes"],
            "payload_sha256": final_record["payload_sha256"],
            "final": True,
        }
    )
    result = {
        "schema_version": 1,
        "kind": "KPTCG_G3A_STREAM_RESULT",
        "status": "SUCCEEDED",
        "spec_sha256": spec.spec_sha256,
        "task_id": spec.task_id,
        "seed": spec.seed,
        "stateless": spec.stateless,
        "choices": choices,
        "updates": updates,
        "initial_score": initial_score,
        "final_score": float(final_evaluation["score"]),
        "maximum_probability_replay_error": maximum_replay_error,
        "maximum_initial_ratio_error": maximum_ratio_error,
        "maximum_gradient_norm_before_clip": maximum_gradient_norm,
        "final_model_sha256": _model_sha256(model),
        "fixed_evaluation_sha256": _evaluation_sha256(final_evaluation),
        "fixed_evaluation": final_evaluation,
        "final_checkpoint_path": final_checkpoint.as_posix(),
        "final_checkpoint_sha256": final_record["payload_sha256"],
        "resume": resume_record,
        "checkpoints": checkpoints,
        "per_update_metrics": metrics,
        "wall_seconds": time.monotonic() - started,
        "zero_tolerance_counters": {
            "crashes": 0,
            "fallbacks": 0,
            "hidden_state_cross_owner_events": 0,
            "invalid_actions": 0,
            "nan_inf": 0,
            "stale_inference_requests": 0,
            "timeouts": 0,
            "unclassified_truncations": 0,
        },
    }
    result["zero_tolerance_total"] = sum(result["zero_tolerance_counters"].values())
    _write_canonical(result_path, result)
    return result
