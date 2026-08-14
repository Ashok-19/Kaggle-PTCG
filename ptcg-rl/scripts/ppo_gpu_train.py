from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import resource
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import torch
from torch import Tensor

from gpu_cabt.device_runtime import GpuCabtRuntime
from ptcg_rl.g2.checkpoint import load_checkpoint_package, state_dict_sha256
from ptcg_rl.g2.network import PTCGPolicyV1, TorchDecisionBatch
from ptcg_rl.g3.checkpoint import (
    load_training_checkpoint_model_state,
    restore_training_checkpoint,
    save_training_checkpoint,
)
from ptcg_rl.g3.compound_batch import (
    BatchedCompoundActionV1,
    replay_compound_actions_batched,
    sample_compound_actions_batched,
)
from ptcg_rl.g3.gpu_policy_bridge import build_torch_policy_batch
from ptcg_rl.g3.ppo import ppo_loss, require_finite_gradients
from ptcg_rl.g3.production_ppo import (
    compute_complete_game_gae,
    meaningful_compound_policy_mask,
    slice_torch_decision_batch_rows,
)


class PPOTrainError(RuntimeError):
    pass


@dataclass(frozen=True)
class LearnerStepV1:
    boundary: int
    batch: TorchDecisionBatch
    env_indices: Tensor
    actors: Tensor
    minimum_counts: Tensor
    maximum_counts: Tensor
    actions: BatchedCompoundActionV1
    flat_start: int
    flat_end: int


@dataclass
class RolloutV1:
    steps: list[LearnerStepV1]
    chunk_hidden_snapshots: dict[int, Tensor]
    owner_ids: Tensor
    old_log_probabilities: Tensor
    old_values: Tensor
    old_entropies: Tensor
    policy_mask: Tensor
    final_results: Tensor
    metrics: dict[str, Any]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_deck(path: Path) -> np.ndarray:
    values = np.loadtxt(path, dtype=np.int32)
    if values.shape != (60,):
        raise PPOTrainError(f"expected exactly 60 card ids at {path}, got {values.shape}")
    return values


def _model_state_sha(model: PTCGPolicyV1) -> str:
    return state_dict_sha256(
        {name: tensor.detach().cpu() for name, tensor in model.state_dict().items()}
    )


def _parameter_snapshot(model: PTCGPolicyV1) -> tuple[Tensor, ...]:
    return tuple(parameter.detach().clone() for parameter in model.parameters())


def _parameter_delta_l2(model: PTCGPolicyV1, before: Sequence[Tensor]) -> float:
    squared = 0.0
    for parameter, reference in zip(model.parameters(), before, strict=True):
        squared += float((parameter.detach().float() - reference.float()).square().sum().item())
    result = math.sqrt(squared)
    if not math.isfinite(result):
        raise PPOTrainError("parameter delta is nonfinite")
    return result


def _host_peak_rss_bytes() -> int:
    # Linux reports ru_maxrss in KiB.
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024


def _league_assignment(
    env_count: int,
    *,
    historical_fraction: float,
    seed: int,
    device: torch.device,
) -> tuple[Tensor, dict[str, Any]]:
    if not (0.0 <= historical_fraction <= 1.0):
        raise PPOTrainError("historical opponent fraction must be within [0, 1]")
    rng = np.random.default_rng(seed ^ 0x6C6561677565)
    historical = rng.random(env_count) < historical_fraction
    historical_seats = rng.integers(0, 2, size=env_count, dtype=np.int64)
    learner = np.ones((env_count, 2), dtype=np.bool_)
    rows = np.nonzero(historical)[0]
    learner[rows, historical_seats[rows]] = False
    assignment = torch.from_numpy(learner).to(device=device)
    return assignment, {
        "current_selfplay_envs": int((~historical).sum()),
        "historical_bc_envs": int(historical.sum()),
        "historical_fraction_realized": float(historical.mean()),
        "historical_seat_0": int(np.sum(historical & (historical_seats == 0))),
        "historical_seat_1": int(np.sum(historical & (historical_seats == 1))),
    }


def _clone_actions(actions: BatchedCompoundActionV1) -> BatchedCompoundActionV1:
    return BatchedCompoundActionV1(
        selected_indices=actions.selected_indices.detach().clone(),
        selected_lengths=actions.selected_lengths.detach().clone(),
        stopped=actions.stopped.detach().clone(),
        log_probabilities=actions.log_probabilities.detach().float().clone(),
        normalized_entropies=actions.normalized_entropies.detach().float().clone(),
    )


def _compact_batch_to_cpu(batch: TorchDecisionBatch) -> TorchDecisionBatch:
    """Losslessly compact GPU-bridge observations for bounded rollout retention.

    GPU-CABT bridge numeric fields are integer-valued public quantities represented
    as float32. Float16 therefore preserves the current qualified ranges exactly,
    while categorical/index tensors fit in signed int32. The learner restores the
    model-facing dtypes before replay; probability replay is the fail-closed guard.
    """
    values: dict[str, Any] = {"batch_size": batch.batch_size}
    for name, value in batch.__dict__.items():
        if name == "batch_size":
            continue
        tensor = value.detach()
        if tensor.dtype == torch.long:
            tensor = tensor.to(dtype=torch.int32)
        elif tensor.dtype == torch.float32:
            if tensor.numel() and torch.any(torch.abs(tensor) > 2048):
                raise PPOTrainError(
                    f"cannot losslessly compact {name}: numeric value exceeds float16 exact-integer range"
                )
            if tensor.numel() and torch.any(tensor != tensor.round()):
                raise PPOTrainError(
                    f"cannot losslessly compact {name}: GPU bridge numeric field is fractional"
                )
            tensor = tensor.to(dtype=torch.float16)
        values[name] = tensor.cpu()
    return TorchDecisionBatch(**values)


def _restore_batch_to_device(batch: TorchDecisionBatch, device: torch.device) -> TorchDecisionBatch:
    values: dict[str, Any] = {"batch_size": batch.batch_size}
    for name, value in batch.__dict__.items():
        if name == "batch_size":
            continue
        tensor = value
        if tensor.dtype == torch.int32:
            tensor = tensor.to(device=device, dtype=torch.long)
        elif tensor.dtype == torch.float16:
            tensor = tensor.to(device=device, dtype=torch.float32)
        else:
            tensor = tensor.to(device=device)
        values[name] = tensor
    return TorchDecisionBatch(**values)


def _compact_actions_to_cpu(actions: BatchedCompoundActionV1) -> BatchedCompoundActionV1:
    return BatchedCompoundActionV1(
        selected_indices=actions.selected_indices.detach().to(dtype=torch.int32).cpu(),
        selected_lengths=actions.selected_lengths.detach().to(dtype=torch.int32).cpu(),
        stopped=actions.stopped.detach().cpu(),
        log_probabilities=actions.log_probabilities.detach().float().cpu(),
        normalized_entropies=actions.normalized_entropies.detach().float().cpu(),
    )


def _restore_actions_to_device(
    actions: BatchedCompoundActionV1, device: torch.device
) -> BatchedCompoundActionV1:
    return BatchedCompoundActionV1(
        selected_indices=actions.selected_indices.to(device=device, dtype=torch.long),
        selected_lengths=actions.selected_lengths.to(device=device, dtype=torch.long),
        stopped=actions.stopped.to(device=device),
        log_probabilities=actions.log_probabilities.to(device=device),
        normalized_entropies=actions.normalized_entropies.to(device=device),
    )


def _slice_actions_rows(
    actions: BatchedCompoundActionV1, start: int, end: int
) -> BatchedCompoundActionV1:
    return BatchedCompoundActionV1(
        selected_indices=actions.selected_indices[start:end],
        selected_lengths=actions.selected_lengths[start:end],
        stopped=actions.stopped[start:end],
        log_probabilities=actions.log_probabilities[start:end],
        normalized_entropies=actions.normalized_entropies[start:end],
    )


def _slice_step_rows(step: LearnerStepV1, start: int, end: int) -> LearnerStepV1:
    return LearnerStepV1(
        boundary=step.boundary,
        batch=slice_torch_decision_batch_rows(step.batch, start, end),
        env_indices=step.env_indices[start:end],
        actors=step.actors[start:end],
        minimum_counts=step.minimum_counts[start:end],
        maximum_counts=step.maximum_counts[start:end],
        actions=_slice_actions_rows(step.actions, start, end),
        flat_start=step.flat_start + start,
        flat_end=step.flat_start + end,
    )


def _lane_steps_and_indices(
    steps: Sequence[LearnerStepV1],
    *,
    env_start: int,
    env_end: int,
) -> tuple[list[LearnerStepV1], Tensor]:
    lane_steps: list[LearnerStepV1] = []
    indices: list[Tensor] = []
    for step in steps:
        start_value = torch.tensor(env_start, dtype=step.env_indices.dtype)
        end_value = torch.tensor(env_end, dtype=step.env_indices.dtype)
        row_start = int(torch.searchsorted(step.env_indices, start_value, right=False).item())
        row_end = int(torch.searchsorted(step.env_indices, end_value, right=False).item())
        if row_end <= row_start:
            continue
        sliced = _slice_step_rows(step, row_start, row_end)
        lane_steps.append(sliced)
        indices.append(torch.arange(sliced.flat_start, sliced.flat_end, dtype=torch.long))
    if not lane_steps:
        return [], torch.empty(0, dtype=torch.long)
    return lane_steps, torch.cat(indices)


def _apply_actions(
    *,
    response_present: Tensor,
    selected_counts: Tensor,
    selected_indices: Tensor,
    env_indices: Tensor,
    actions: BatchedCompoundActionV1,
) -> None:
    response_present[env_indices] = 1
    selected_counts[env_indices] = actions.selected_lengths.to(torch.int32)
    copy_width = int(actions.selected_lengths.max().item()) if actions.batch_size else 0
    if copy_width > selected_indices.shape[1]:
        raise PPOTrainError("sampled compound action exceeds GPU-CABT selected capacity")
    if copy_width:
        values = actions.selected_indices[:, :copy_width]
        selected_indices[env_indices, :copy_width] = torch.where(
            values >= 0, values, torch.zeros_like(values)
        ).to(torch.int32)


def _collect_complete_rollout(
    *,
    model: PTCGPolicyV1,
    historical_model: PTCGPolicyV1,
    runtime: GpuCabtRuntime,
    decks: np.ndarray,
    seed: int,
    historical_fraction: float,
    chunk_boundaries: int,
    max_boundaries: int,
    bf16: bool,
) -> RolloutV1:
    device = next(model.parameters()).device
    assignment, league_metrics = _league_assignment(
        runtime.env_count,
        historical_fraction=historical_fraction,
        seed=seed,
        device=device,
    )
    runtime.reset(decks, seed=seed)
    runtime.synchronize()
    hidden = model.initial_hidden(runtime.env_count * 2, device).reshape(
        runtime.env_count, 2, model.config.public_hidden
    )
    generator = torch.Generator(device=device).manual_seed(seed ^ 0x5A17C0DE)
    response_present = torch.zeros(runtime.env_count, dtype=torch.uint8, device=device)
    selected_counts = torch.zeros(runtime.env_count, dtype=torch.int32, device=device)
    selected_indices = torch.zeros(
        (runtime.env_count, runtime.abi.selected_capacity), dtype=torch.int32, device=device
    )

    steps: list[LearnerStepV1] = []
    chunk_snapshots: dict[int, Tensor] = {}
    owners: list[Tensor] = []
    old_logps: list[Tensor] = []
    old_values: list[Tensor] = []
    old_entropies: list[Tensor] = []
    policy_masks: list[Tensor] = []
    flat_offset = 0
    actor_decisions = 0
    learner_decisions = 0
    historical_decisions = 0
    meaningful_targets = 0
    active_first = 0
    active_last = 0
    projection_seconds = 0.0
    bridge_seconds = 0.0
    model_seconds = 0.0
    engine_seconds = 0.0
    started = time.perf_counter()

    autocast = lambda: torch.autocast(  # noqa: E731
        device_type="cuda", dtype=torch.bfloat16, enabled=bf16
    )

    for boundary in range(max_boundaries):
        raw_status = runtime.status()
        runtime.synchronize()
        status = raw_status.torch(torch)
        errors = status.error_flags.to(torch.long)
        if torch.any(errors != 0):
            bad = torch.nonzero(errors != 0, as_tuple=False).squeeze(1).cpu().tolist()[:16]
            raise PPOTrainError(f"GPU-CABT runtime error before boundary {boundary}: {bad}")
        active = status.game_results == 0
        active_indices = torch.nonzero(active, as_tuple=False).squeeze(1).to(torch.long)
        active_count = int(active_indices.numel())
        if boundary == 0:
            active_first = active_count
        active_last = active_count
        if active_count == 0:
            elapsed = time.perf_counter() - started
            final_results = status.game_results.to(torch.long).clone()
            if not owners:
                raise PPOTrainError("complete-game rollout produced no learner decisions")
            return RolloutV1(
                steps=steps,
                chunk_hidden_snapshots=chunk_snapshots,
                owner_ids=torch.cat(owners),
                old_log_probabilities=torch.cat(old_logps),
                old_values=torch.cat(old_values),
                old_entropies=torch.cat(old_entropies),
                policy_mask=torch.cat(policy_masks),
                final_results=final_results,
                metrics={
                    "boundaries": boundary,
                    "rollout_seconds": elapsed,
                    "actor_recurrent_decisions": actor_decisions,
                    "learner_recurrent_decisions": learner_decisions,
                    "historical_recurrent_decisions": historical_decisions,
                    "meaningful_policy_targets": meaningful_targets,
                    "actor_decisions_per_second": actor_decisions / max(elapsed, 1e-9),
                    "learner_decisions_per_second": learner_decisions / max(elapsed, 1e-9),
                    "active_first": active_first,
                    "active_last": active_last,
                    "terminal_envs": runtime.env_count,
                    "league": league_metrics,
                    "timing_accumulators_seconds": {
                        "projection": projection_seconds,
                        "bridge": bridge_seconds,
                        "model_and_compound": model_seconds,
                        "engine_step": engine_seconds,
                    },
                },
            )
        if torch.any(active & (status.select_types == 0)):
            bad = torch.nonzero(active & (status.select_types == 0), as_tuple=False).squeeze(1)
            raise PPOTrainError(f"active environment has no selection boundary: {bad[:16].cpu().tolist()}")
        if boundary % chunk_boundaries == 0:
            chunk_snapshots[boundary // chunk_boundaries] = hidden.detach().clone()

        projection_started = time.perf_counter()
        raw_events = runtime.project_events(acknowledge=True)
        raw_projection = runtime.project_policy()
        runtime.synchronize()
        events = raw_events.torch(torch)
        projection = raw_projection.torch(torch)
        projection_seconds += time.perf_counter() - projection_started

        active_actors = status.select_players.index_select(0, active_indices).to(torch.long)
        learner_active = assignment[active_indices, active_actors]
        learner_envs = active_indices[learner_active]
        historical_envs = active_indices[~learner_active]

        response_present.zero_()
        selected_counts.zero_()
        selected_indices.zero_()

        def run_group(env_indices: Tensor, policy: PTCGPolicyV1, *, learner: bool) -> None:
            nonlocal flat_offset, bridge_seconds, model_seconds
            nonlocal learner_decisions, historical_decisions, meaningful_targets
            if env_indices.numel() == 0:
                return
            bridge_started = time.perf_counter()
            batch, meta = build_torch_policy_batch(
                projection, events, status, env_indices=env_indices
            )
            bridge_seconds += time.perf_counter() - bridge_started
            hidden_before = hidden[meta.env_indices, meta.actors]
            model_started = time.perf_counter()
            with torch.inference_mode(), autocast():
                output = policy(batch, hidden_before)
                actions = sample_compound_actions_batched(
                    policy,
                    public_hidden=output.hidden,
                    option_embeddings=output.option_embeddings,
                    option_offsets=output.option_offsets,
                    available_mask=batch.option_available,
                    minimum_counts=meta.minimum_counts,
                    maximum_counts=meta.maximum_counts,
                    generator=generator,
                )
            runtime.synchronize()
            model_seconds += time.perf_counter() - model_started
            if not torch.isfinite(output.values).all() or not torch.isfinite(output.hidden).all():
                raise PPOTrainError("rollout policy emitted a nonfinite value or hidden state")
            if not torch.isfinite(actions.log_probabilities).all():
                raise PPOTrainError("rollout compound sampler emitted a nonfinite log probability")
            hidden[meta.env_indices, meta.actors] = output.hidden.to(hidden.dtype)
            _apply_actions(
                response_present=response_present,
                selected_counts=selected_counts,
                selected_indices=selected_indices,
                env_indices=meta.env_indices,
                actions=actions,
            )
            if not learner:
                historical_decisions += batch.batch_size
                return

            policy_mask = meaningful_compound_policy_mask(
                batch,
                minimum_counts=meta.minimum_counts,
                maximum_counts=meta.maximum_counts,
            )
            count = batch.batch_size
            learner_decisions += count
            meaningful_targets += int(policy_mask.sum().item())
            owners.append((meta.env_indices * 2 + meta.actors).detach().clone())
            old_logps.append(actions.log_probabilities.detach().float().clone())
            old_values.append(output.values.detach().float().clone())
            old_entropies.append(actions.normalized_entropies.detach().float().clone())
            policy_masks.append(policy_mask.detach().clone())
            steps.append(
                LearnerStepV1(
                    boundary=boundary,
                    batch=_compact_batch_to_cpu(batch),
                    env_indices=meta.env_indices.detach().to(dtype=torch.int32).cpu(),
                    actors=meta.actors.detach().to(dtype=torch.int32).cpu(),
                    minimum_counts=meta.minimum_counts.detach().to(dtype=torch.int32).cpu(),
                    maximum_counts=meta.maximum_counts.detach().to(dtype=torch.int32).cpu(),
                    actions=_compact_actions_to_cpu(actions),
                    flat_start=flat_offset,
                    flat_end=flat_offset + count,
                )
            )
            flat_offset += count

        run_group(learner_envs, model, learner=True)
        run_group(historical_envs, historical_model, learner=False)
        actor_decisions += active_count

        engine_started = time.perf_counter()
        runtime.step(response_present, selected_counts, selected_indices)
        runtime.synchronize()
        engine_seconds += time.perf_counter() - engine_started

    raise PPOTrainError(
        f"complete-game rollout did not terminate within {max_boundaries} selection boundaries"
    )


def _steps_by_chunk(rollout: RolloutV1, chunk_boundaries: int) -> list[tuple[int, list[LearnerStepV1]]]:
    grouped: dict[int, list[LearnerStepV1]] = {}
    for step in rollout.steps:
        grouped.setdefault(step.boundary // chunk_boundaries, []).append(step)
    return sorted(grouped.items())


def _replay_chunk(
    *,
    model: PTCGPolicyV1,
    steps: Sequence[LearnerStepV1],
    hidden_snapshot: Tensor,
    gradient: bool,
    bf16: bool,
) -> tuple[Tensor, Tensor, Tensor]:
    device = hidden_snapshot.device
    hidden = hidden_snapshot.reshape(-1, model.config.public_hidden)
    log_probabilities: list[Tensor] = []
    values: list[Tensor] = []
    entropies: list[Tensor] = []
    context = torch.enable_grad() if gradient else torch.inference_mode()
    autocast = torch.autocast(device_type="cuda", dtype=torch.bfloat16, enabled=bf16)
    with context, autocast:
        for step in steps:
            batch = _restore_batch_to_device(step.batch, device)
            env_indices = step.env_indices.to(device=device, dtype=torch.long)
            actors = step.actors.to(device=device, dtype=torch.long)
            minimum_counts = step.minimum_counts.to(device=device, dtype=torch.long)
            maximum_counts = step.maximum_counts.to(device=device, dtype=torch.long)
            actions = _restore_actions_to_device(step.actions, device)
            owner = env_indices * 2 + actors
            hidden_before = hidden.index_select(0, owner)
            output = model(batch, hidden_before)
            replay_logp, replay_entropy = replay_compound_actions_batched(
                model,
                public_hidden=output.hidden,
                option_embeddings=output.option_embeddings,
                option_offsets=output.option_offsets,
                available_mask=batch.option_available,
                minimum_counts=minimum_counts,
                maximum_counts=maximum_counts,
                actions=actions,
            )
            log_probabilities.append(replay_logp.float())
            values.append(output.values.float())
            entropies.append(replay_entropy.float())
            hidden = hidden.index_copy(0, owner, output.hidden.to(hidden.dtype))
    return torch.cat(log_probabilities), torch.cat(values), torch.cat(entropies)


def _weighted_metrics_accumulator() -> dict[str, float]:
    return {
        "total_loss": 0.0,
        "policy_loss": 0.0,
        "value_loss": 0.0,
        "entropy": 0.0,
        "approximate_kl": 0.0,
        "clip_fraction": 0.0,
    }


def _add_weighted_loss(target: dict[str, float], loss: Any, weight: float) -> None:
    target["total_loss"] += float(loss.total.detach().item()) * weight
    target["policy_loss"] += float(loss.policy.detach().item()) * weight
    target["value_loss"] += float(loss.value.detach().item()) * weight
    target["entropy"] += float(loss.entropy.detach().item()) * weight
    target["approximate_kl"] += float(loss.approximate_kl.detach().item()) * weight
    target["clip_fraction"] += float(loss.clip_fraction.detach().item()) * weight


def _ppo_update(
    *,
    model: PTCGPolicyV1,
    optimizer: torch.optim.Optimizer,
    scheduler: Any,
    rollout: RolloutV1,
    advantages: Tensor,
    returns: Tensor,
    chunk_boundaries: int,
    learner_lane_envs: int,
    clip_coefficient: float,
    value_clip_coefficient: float,
    value_coefficient: float,
    entropy_coefficient: float,
    max_gradient_norm: float,
    bf16: bool,
) -> dict[str, Any]:
    policy_mask = rollout.policy_mask
    total_valid = int(policy_mask.sum().item())
    if total_valid <= 0:
        raise PPOTrainError("rollout contains no meaningful learner actions")
    selected_advantages = advantages[policy_mask]
    advantage_mean = selected_advantages.mean()
    advantage_std = selected_advantages.std(unbiased=False)
    normalized_advantages = advantages.clone()
    normalized_advantages[policy_mask] = (
        selected_advantages - advantage_mean
    ) / (advantage_std + 1e-8)

    chunks = _steps_by_chunk(rollout, chunk_boundaries)
    env_count = int(next(iter(rollout.chunk_hidden_snapshots.values())).shape[0])
    if learner_lane_envs <= 0 or learner_lane_envs > env_count:
        raise PPOTrainError("learner lane env count must stay within 1..env_count")
    lane_ranges = [
        (start, min(env_count, start + learner_lane_envs))
        for start in range(0, env_count, learner_lane_envs)
    ]
    before = _parameter_snapshot(model)
    optimizer.zero_grad(set_to_none=True)
    model.train()
    pre_metrics = _weighted_metrics_accumulator()
    replay_max_logp_error = 0.0
    replay_max_ratio_error = 0.0
    replay_max_value_error = 0.0
    replayed_actions = 0
    started = time.perf_counter()

    learner_minibatches = 0
    for chunk_index, steps in chunks:
        hidden_snapshot = rollout.chunk_hidden_snapshots[chunk_index]
        for env_start, env_end in lane_ranges:
            lane_steps, cpu_indices = _lane_steps_and_indices(
                steps, env_start=env_start, env_end=env_end
            )
            if not lane_steps:
                continue
            indices = cpu_indices.to(device=policy_mask.device)
            new_logp, new_values, new_entropies = _replay_chunk(
                model=model,
                steps=lane_steps,
                hidden_snapshot=hidden_snapshot,
                gradient=True,
                bf16=bf16,
            )
            old_logp = rollout.old_log_probabilities.index_select(0, indices)
            old_values = rollout.old_values.index_select(0, indices)
            lane_mask = policy_mask.index_select(0, indices)
            lane_valid = int(lane_mask.sum().item())
            if lane_valid <= 0:
                continue
            lane_advantages = normalized_advantages.index_select(0, indices)
            lane_returns = returns.index_select(0, indices)
            logp_difference = torch.abs(new_logp.detach() - old_logp)
            ratio_error = torch.abs(torch.exp(new_logp.detach() - old_logp) - 1.0)
            replay_max_logp_error = max(
                replay_max_logp_error, float(logp_difference.max().item())
            )
            replay_max_ratio_error = max(
                replay_max_ratio_error, float(ratio_error.max().item())
            )
            replay_max_value_error = max(
                replay_max_value_error,
                float(torch.abs(new_values.detach() - old_values).max().item()),
            )
            replayed_actions += int(new_logp.numel())
            loss = ppo_loss(
                new_log_probabilities=new_logp,
                old_log_probabilities=old_logp,
                advantages=lane_advantages,
                new_values=new_values,
                old_values=old_values,
                returns=lane_returns,
                normalized_entropies=new_entropies,
                policy_mask=lane_mask,
                clip_coefficient=clip_coefficient,
                value_clip_coefficient=value_clip_coefficient,
                value_coefficient=value_coefficient,
                entropy_coefficient=entropy_coefficient,
                normalize_advantages=False,
            )
            weight = lane_valid / total_valid
            (loss.total * weight).backward()
            _add_weighted_loss(pre_metrics, loss, weight)
            learner_minibatches += 1

    gradient_norm = require_finite_gradients(tuple(model.parameters()))
    clip_grad_return = float(
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_gradient_norm).item()
    )
    optimizer.step()
    scheduler.step()
    update_seconds = time.perf_counter() - started
    parameter_delta = _parameter_delta_l2(model, before)
    if parameter_delta <= 0:
        raise PPOTrainError("PPO optimizer step did not change model parameters")

    model.eval()
    post_metrics = _weighted_metrics_accumulator()
    post_values_all: list[Tensor] = []
    post_started = time.perf_counter()
    for chunk_index, steps in chunks:
        hidden_snapshot = rollout.chunk_hidden_snapshots[chunk_index]
        for env_start, env_end in lane_ranges:
            lane_steps, cpu_indices = _lane_steps_and_indices(
                steps, env_start=env_start, env_end=env_end
            )
            if not lane_steps:
                continue
            indices = cpu_indices.to(device=policy_mask.device)
            new_logp, new_values, new_entropies = _replay_chunk(
                model=model,
                steps=lane_steps,
                hidden_snapshot=hidden_snapshot,
                gradient=False,
                bf16=bf16,
            )
            lane_mask = policy_mask.index_select(0, indices)
            lane_valid = int(lane_mask.sum().item())
            if lane_valid <= 0:
                continue
            loss = ppo_loss(
                new_log_probabilities=new_logp,
                old_log_probabilities=rollout.old_log_probabilities.index_select(0, indices),
                advantages=normalized_advantages.index_select(0, indices),
                new_values=new_values,
                old_values=rollout.old_values.index_select(0, indices),
                returns=returns.index_select(0, indices),
                normalized_entropies=new_entropies,
                policy_mask=lane_mask,
                clip_coefficient=clip_coefficient,
                value_clip_coefficient=value_clip_coefficient,
                value_coefficient=value_coefficient,
                entropy_coefficient=entropy_coefficient,
                normalize_advantages=False,
            )
            _add_weighted_loss(post_metrics, loss, lane_valid / total_valid)
            post_values_all.append(new_values.detach())
    post_replay_seconds = time.perf_counter() - post_started
    post_values = torch.cat(post_values_all)

    return {
        "learner_samples": total_valid,
        "learner_recurrent_samples": int(rollout.old_values.numel()),
        "learner_samples_per_second": total_valid / max(update_seconds, 1e-9),
        "learner_recurrent_samples_per_second": int(rollout.old_values.numel()) / max(update_seconds, 1e-9),
        "update_seconds": update_seconds,
        "post_replay_seconds": post_replay_seconds,
        "chunk_count": len(chunks),
        "chunk_boundaries": chunk_boundaries,
        "learner_lane_envs": learner_lane_envs,
        "learner_minibatches": learner_minibatches,
        "pre_update": pre_metrics,
        "post_update": post_metrics,
        "probability_replay": {
            "checked_actions": replayed_actions,
            "max_log_probability_absolute_error": replay_max_logp_error,
            "max_ratio_absolute_error_from_one": replay_max_ratio_error,
            "max_value_absolute_error": replay_max_value_error,
        },
        "gradient_norm": gradient_norm,
        "clip_grad_norm_return": clip_grad_return,
        "parameter_delta_l2": parameter_delta,
        "advantage_normalization_mean": float(advantage_mean.item()),
        "advantage_normalization_std": float(advantage_std.item()),
        "post_value_mean": float(post_values.mean().item()),
        "post_value_std": float(post_values.std(unbiased=False).item()),
        "post_value_min": float(post_values.min().item()),
        "post_value_max": float(post_values.max().item()),
    }


def _terminal_counts(results: Tensor) -> dict[str, int]:
    return {str(code): int((results == code).sum().item()) for code in (1, 2, 3)}


def _code_hashes(script_path: Path) -> dict[str, str]:
    root = script_path.resolve().parents[1]
    paths = {
        "trainer": script_path,
        "production_ppo": root / "src/ptcg_rl/g3/production_ppo.py",
        "ppo_contract": root / "src/ptcg_rl/g3/ppo.py",
        "compound_batch": root / "src/ptcg_rl/g3/compound_batch.py",
        "gpu_policy_bridge": root / "src/ptcg_rl/g3/gpu_policy_bridge.py",
        "network": root / "src/ptcg_rl/g2/network.py",
    }
    return {name: _sha256_file(path) for name, path in paths.items()}


def run(args: argparse.Namespace) -> dict[str, Any]:
    device = torch.device(args.device)
    if device.type != "cuda" or not torch.cuda.is_available():
        raise PPOTrainError("production PPO trainer requires CUDA")
    if args.env_count <= 0 or args.env_count > 8192:
        raise PPOTrainError("env_count must stay within the qualified 1..8192 range")
    if args.decision_budget <= 0 or args.decision_budget > 30_000_000:
        raise PPOTrainError("bounded trainer decision budget must stay within 1..30M")
    if args.chunk_boundaries < 16 or args.chunk_boundaries > 128:
        raise PPOTrainError("recurrent chunk boundaries must stay within 16..128")
    if args.learner_lane_envs <= 0 or args.learner_lane_envs > args.env_count:
        raise PPOTrainError("learner lane envs must stay within 1..env_count")
    if args.max_boundaries < args.chunk_boundaries:
        raise PPOTrainError("max boundaries must not be smaller than recurrent chunk size")

    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)
    np.random.seed(args.seed & 0xFFFFFFFF)
    torch.cuda.reset_peak_memory_stats(device)

    loaded = load_checkpoint_package(args.checkpoint_package, device=device)
    model = loaded.model
    initializer = load_training_checkpoint_model_state(
        args.bc_checkpoint,
        model=model,
        expected_sha256=args.bc_checkpoint_sha256,
    )
    historical_model = copy.deepcopy(model).eval()
    for parameter in historical_model.parameters():
        parameter.requires_grad_(False)

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=0.0)
    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda=lambda _: 1.0)
    total_actor_decisions = 0
    total_learner_decisions = 0
    total_meaningful_targets = 0
    completed_updates = 0
    resume_record: dict[str, Any] | None = None
    if args.resume_checkpoint is not None:
        restored = restore_training_checkpoint(
            args.resume_checkpoint,
            model=model,
            optimizer=optimizer,
            scheduler=scheduler,
            scaler=None,
            expected_sha256=args.resume_checkpoint_sha256,
            restore_rng=True,
        )
        total_actor_decisions = int(restored.counters.get("actor_decisions", 0))
        total_learner_decisions = int(restored.counters.get("learner_decisions", 0))
        total_meaningful_targets = int(restored.counters.get("meaningful_policy_targets", 0))
        completed_updates = int(restored.counters.get("ppo_updates", 0))
        resume_record = {
            "checkpoint": args.resume_checkpoint.as_posix(),
            "sha256": restored.payload_sha256,
            "restored_rng_states": list(restored.restored_rng_states),
            "starting_counters": restored.counters,
        }
    model.eval()

    deck = _load_deck(args.deck)
    decks = np.broadcast_to(deck, (args.env_count, 2, 60)).copy()
    runtime_started = time.perf_counter()
    runtime = GpuCabtRuntime(args.env_count, stack_size_bytes=args.stack_bytes)
    runtime.synchronize()
    runtime_init_seconds = time.perf_counter() - runtime_started
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    run_start_actor_decisions = total_actor_decisions
    updates: list[dict[str, Any]] = []
    checkpoint_records: list[dict[str, Any]] = []
    run_started = time.perf_counter()

    while total_actor_decisions - run_start_actor_decisions < args.decision_budget:
        update_number = completed_updates + 1
        rollout_seed = args.seed + update_number * 1_000_003
        model.eval()
        rollout = _collect_complete_rollout(
            model=model,
            historical_model=historical_model,
            runtime=runtime,
            decks=decks,
            seed=rollout_seed,
            historical_fraction=args.historical_fraction,
            chunk_boundaries=args.chunk_boundaries,
            max_boundaries=args.max_boundaries,
            bf16=args.bf16,
        )
        gae_started = time.perf_counter()
        gae, gae_stats = compute_complete_game_gae(
            owner_ids=rollout.owner_ids,
            values=rollout.old_values,
            final_results=rollout.final_results,
            env_count=args.env_count,
            gamma=args.gamma,
            gae_lambda=args.gae_lambda,
        )
        torch.cuda.synchronize(device)
        gae_seconds = time.perf_counter() - gae_started
        update = _ppo_update(
            model=model,
            optimizer=optimizer,
            scheduler=scheduler,
            rollout=rollout,
            advantages=gae.advantages,
            returns=gae.returns,
            chunk_boundaries=args.chunk_boundaries,
            learner_lane_envs=args.learner_lane_envs,
            clip_coefficient=args.clip_coefficient,
            value_clip_coefficient=args.value_clip_coefficient,
            value_coefficient=args.value_coefficient,
            entropy_coefficient=args.entropy_coefficient,
            max_gradient_norm=args.max_gradient_norm,
            bf16=args.bf16,
        )
        actor_decisions = int(rollout.metrics["actor_recurrent_decisions"])
        learner_decisions = int(rollout.metrics["learner_recurrent_decisions"])
        meaningful_targets = int(rollout.metrics["meaningful_policy_targets"])
        total_actor_decisions += actor_decisions
        total_learner_decisions += learner_decisions
        total_meaningful_targets += meaningful_targets
        completed_updates = update_number

        advantage = gae.advantages
        returns = gae.returns
        rollout_record = {
            **rollout.metrics,
            "terminal_counts": _terminal_counts(rollout.final_results),
            "runtime_memory_bytes": runtime.memory_bytes(),
            "old_value_mean": float(rollout.old_values.mean().item()),
            "old_value_std": float(rollout.old_values.std(unbiased=False).item()),
            "old_value_min": float(rollout.old_values.min().item()),
            "old_value_max": float(rollout.old_values.max().item()),
            "old_entropy_mean": float(rollout.old_entropies[rollout.policy_mask].mean().item()),
        }
        update_record = {
            "update": update_number,
            "rollout_seed": rollout_seed,
            "rollout": rollout_record,
            "gae": {
                **asdict(gae_stats),
                "seconds": gae_seconds,
                "advantage_mean": float(advantage.mean().item()),
                "advantage_std": float(advantage.std(unbiased=False).item()),
                "advantage_min": float(advantage.min().item()),
                "advantage_max": float(advantage.max().item()),
                "return_mean": float(returns.mean().item()),
                "return_std": float(returns.std(unbiased=False).item()),
                "return_min": float(returns.min().item()),
                "return_max": float(returns.max().item()),
            },
            "learner": update,
            "cumulative": {
                "actor_decisions": total_actor_decisions,
                "learner_decisions": total_learner_decisions,
                "meaningful_policy_targets": total_meaningful_targets,
            },
        }
        updates.append(update_record)

        checkpoint_path = output_dir / f"ppo-update-{update_number:04d}.pt"
        checkpoint = save_training_checkpoint(
            checkpoint_path,
            model=model,
            optimizer=optimizer,
            scheduler=scheduler,
            scaler=None,
            counters={
                "ppo_updates": completed_updates,
                "actor_decisions": total_actor_decisions,
                "learner_decisions": total_learner_decisions,
                "meaningful_policy_targets": total_meaningful_targets,
            },
            league={
                "mode": "80pct-frozen-current-selfplay-plus-historical",
                "historical_fraction_requested": args.historical_fraction,
                "historical_opponents": [
                    {
                        "id": "bc-specialist-epoch-1",
                        "checkpoint_sha256": initializer.payload_sha256,
                    }
                ],
                "retained_intermediate_policy_updates": list(range(1, completed_updates + 1)),
            },
            rollout_boundary={
                "complete_games": args.env_count,
                "terminal_counts": rollout_record["terminal_counts"],
                "rollout_seed": rollout_seed,
                "chunk_boundaries": args.chunk_boundaries,
            },
            include_cuda_rng=True,
        )
        checkpoint_record = {
            "update": update_number,
            "path": checkpoint_path.as_posix(),
            "payload_sha256": checkpoint["payload_sha256"],
            "payload_bytes": checkpoint["payload_bytes"],
            "model_state_sha256": _model_state_sha(model),
        }
        checkpoint_records.append(checkpoint_record)
        update_record["checkpoint"] = checkpoint_record

        progress = {
            "event": "ppo_update_complete",
            "update": update_number,
            "actor_decisions": total_actor_decisions,
            "run_actor_decisions": total_actor_decisions - run_start_actor_decisions,
            "actor_dps": rollout_record["actor_decisions_per_second"],
            "learner_samples_per_second": update["learner_samples_per_second"],
            "rollout_seconds": rollout_record["rollout_seconds"],
            "update_seconds": update["update_seconds"],
            "post_kl": update["post_update"]["approximate_kl"],
            "post_clip_fraction": update["post_update"]["clip_fraction"],
            "checkpoint_sha256": checkpoint["payload_sha256"],
        }
        print(json.dumps(progress, sort_keys=True), flush=True)
        del rollout, gae, advantage, returns
        torch.cuda.empty_cache()

    run_seconds = time.perf_counter() - run_started
    run_actor_decisions = total_actor_decisions - run_start_actor_decisions
    total_rollout_seconds = sum(float(item["rollout"]["rollout_seconds"]) for item in updates)
    total_update_seconds = sum(float(item["learner"]["update_seconds"]) for item in updates)
    total_post_replay_seconds = sum(float(item["learner"]["post_replay_seconds"]) for item in updates)
    total_gae_seconds = sum(float(item["gae"]["seconds"]) for item in updates)
    measured_work_seconds = total_rollout_seconds + total_update_seconds + total_post_replay_seconds + total_gae_seconds

    report: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "kptcg-production-shaped-ppo-bounded-v1",
        "status": "PASS",
        "source_commit": args.source_commit,
        "code_sha256": _code_hashes(Path(__file__)),
        "device": str(device),
        "gpu_name": torch.cuda.get_device_name(device),
        "bf16": bool(args.bf16),
        "model_package_sha256": loaded.package_sha256,
        "bc_initializer_sha256": initializer.payload_sha256,
        "initializer_interpretation": "frozen specialist epoch-1 satisfies requested one-epoch BC warmup",
        "model_parameters": model.trainable_parameter_count,
        "architecture_sha256": model.architecture_sha256,
        "deck": {
            "path": args.deck.as_posix(),
            "file_sha256": _sha256_file(args.deck),
        },
        "configuration": {
            "env_count": args.env_count,
            "decision_budget_requested": args.decision_budget,
            "recurrent_chunk_boundaries": args.chunk_boundaries,
            "learner_lane_envs": args.learner_lane_envs,
            "max_game_boundaries": args.max_boundaries,
            "historical_fraction": args.historical_fraction,
            "gamma": args.gamma,
            "gae_lambda": args.gae_lambda,
            "clip_coefficient": args.clip_coefficient,
            "value_clip_coefficient": args.value_clip_coefficient,
            "value_coefficient": args.value_coefficient,
            "entropy_coefficient": args.entropy_coefficient,
            "learning_rate": args.learning_rate,
            "max_gradient_norm": args.max_gradient_norm,
            "ppo_epochs_per_rollout": 1,
            "reward": "terminal-only +1/-1, draw 0",
            "rollout_policy": "frozen for each complete-game rollout",
            "recurrent_replay": "chunk-start hidden snapshot plus in-chunk recurrent unroll",
        },
        "resume": resume_record,
        "runtime_init_seconds": runtime_init_seconds,
        "run": {
            "updates": len(updates),
            "actor_decisions": run_actor_decisions,
            "actor_decisions_requested": args.decision_budget,
            "wall_seconds": run_seconds,
            "end_to_end_actor_decisions_per_second": run_actor_decisions / max(run_seconds, 1e-9),
            "rollout_seconds": total_rollout_seconds,
            "update_seconds": total_update_seconds,
            "post_update_replay_seconds": total_post_replay_seconds,
            "gae_seconds": total_gae_seconds,
            "actor_duty_cycle": total_rollout_seconds / max(measured_work_seconds, 1e-9),
            "learner_duty_cycle": total_update_seconds / max(measured_work_seconds, 1e-9),
            "post_replay_duty_cycle": total_post_replay_seconds / max(measured_work_seconds, 1e-9),
            "gae_duty_cycle": total_gae_seconds / max(measured_work_seconds, 1e-9),
        },
        "cumulative": {
            "ppo_updates": completed_updates,
            "actor_decisions": total_actor_decisions,
            "learner_decisions": total_learner_decisions,
            "meaningful_policy_targets": total_meaningful_targets,
        },
        "memory": {
            "torch_peak_allocated_bytes": int(torch.cuda.max_memory_allocated(device)),
            "torch_peak_reserved_bytes": int(torch.cuda.max_memory_reserved(device)),
            "gpu_cabt_runtime_bytes": runtime.memory_bytes(),
            "host_peak_rss_bytes": _host_peak_rss_bytes(),
        },
        "updates": updates,
        "checkpoints": checkpoint_records,
        "final_checkpoint": checkpoint_records[-1],
        "full_unbounded_run_authorized": False,
    }
    report_path = output_dir / "training-report.json"
    temporary = report_path.with_suffix(".json.partial")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(report_path)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded production-shaped recurrent PPO trainer")
    parser.add_argument("--checkpoint-package", type=Path, required=True)
    parser.add_argument("--bc-checkpoint", type=Path, required=True)
    parser.add_argument("--bc-checkpoint-sha256", required=True)
    parser.add_argument("--deck", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--env-count", type=int, default=8192)
    parser.add_argument("--decision-budget", type=int, required=True)
    parser.add_argument("--chunk-boundaries", type=int, default=64)
    parser.add_argument("--learner-lane-envs", type=int, default=1024)
    parser.add_argument("--max-boundaries", type=int, default=3000)
    parser.add_argument("--historical-fraction", type=float, default=0.20)
    parser.add_argument("--seed", type=int, default=20260815)
    parser.add_argument("--stack-bytes", type=int, default=16 * 1024)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--bf16", action="store_true")
    parser.add_argument("--gamma", type=float, default=0.999)
    parser.add_argument("--gae-lambda", type=float, default=0.95)
    parser.add_argument("--clip-coefficient", type=float, default=0.2)
    parser.add_argument("--value-clip-coefficient", type=float, default=0.2)
    parser.add_argument("--value-coefficient", type=float, default=0.5)
    parser.add_argument("--entropy-coefficient", type=float, default=0.01)
    parser.add_argument("--learning-rate", type=float, default=3e-5)
    parser.add_argument("--max-gradient-norm", type=float, default=1.0)
    parser.add_argument("--resume-checkpoint", type=Path)
    parser.add_argument("--resume-checkpoint-sha256")
    args = parser.parse_args()
    if (args.resume_checkpoint is None) != (args.resume_checkpoint_sha256 is None):
        parser.error("resume checkpoint and SHA-256 must be supplied together")
    result = run(args)
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
