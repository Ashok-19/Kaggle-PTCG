from __future__ import annotations

import argparse
import copy
import json
import math
import os
import resource
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import torch
from torch import Tensor

from ptcg_rl.bc.materialized import MaterializedEpisodeV1, load_materialized_episode
from ptcg_rl.bc.training import (
    PackedMegaRecurrentGroup,
    pack_mega_recurrent_group,
    packed_mega_recurrent_chunk_loss,
)

from gpu_cabt.device_runtime import GpuCabtRuntime
from ptcg_rl.g2.capacity import model_config, model_configs
from ptcg_rl.g2.card_table import load_card_table
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
from ptcg_rl.g3.ppo import ppo_loss, require_finite_gradients, sampled_reference_kl
from ptcg_rl.g3.production_ppo import (
    compute_fixed_horizon_gae,
    meaningful_compound_policy_mask,
    slice_torch_decision_batch_rows,
)


class PPOTrainError(RuntimeError):
    pass


_FAST_VALIDATED_GPU_PATH = os.environ.get("KPTCG_FAST_VALIDATED_GPU_PATH") == "1"


POLICY_LEARNER = 0
POLICY_FROZEN_REFERENCE = 1
POLICY_FROZEN_V7 = 2
POLICY_FROZEN_V5 = 3

ACTOR_SNAPSHOT_SCHEMA_VERSION = 1
ACTOR_SNAPSHOT_KIND = "KPTCG_G3_GPU_ACTOR_SNAPSHOT"
MAX_ACTOR_SNAPSHOT_BYTES = 1024 * 1024 * 1024


@dataclass
class ActorStateV1:
    hidden: Tensor
    reference_hidden: Tensor
    assignment: Tensor
    horizon_index: int = 0


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
    reference_hidden_snapshot: Tensor


def _load_deck(path: Path) -> np.ndarray:
    values = np.loadtxt(path, dtype=np.int32)
    if values.shape != (60,):
        raise PPOTrainError(f"expected exactly 60 card ids at {path}, got {values.shape}")
    return values


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


def _parameter_delta_partitions(
    model: PTCGPolicyV1, before: Sequence[Tensor]
) -> tuple[float, float]:
    critic_ids = {id(parameter) for parameter in model.value_head.parameters()}
    actor_squared = 0.0
    critic_squared = 0.0
    for parameter, reference in zip(model.parameters(), before, strict=True):
        squared = float((parameter.detach().float() - reference.float()).square().sum().item())
        if id(parameter) in critic_ids:
            critic_squared += squared
        else:
            actor_squared += squared
    actor_delta = math.sqrt(actor_squared)
    critic_delta = math.sqrt(critic_squared)
    if not math.isfinite(actor_delta) or not math.isfinite(critic_delta):
        raise PPOTrainError("partitioned parameter delta is nonfinite")
    return actor_delta, critic_delta


def _configure_trainable_policy(
    model: PTCGPolicyV1,
    *,
    freeze_observation_encoder: bool,
) -> dict[str, int]:
    trainable_prefixes = (
        "state_projection.",
        "public_gru.",
        "policy_state.",
        "policy_interaction.",
        "value_head.",
        "selection_initial.",
        "selection_option.",
        "selection_gru.",
    )
    trainable_parameters = 0
    frozen_parameters = 0
    for name, parameter in model.named_parameters():
        trainable = (
            not freeze_observation_encoder
            or name == "stop_embedding"
            or name.startswith(trainable_prefixes)
        )
        parameter.requires_grad_(trainable)
        if trainable:
            trainable_parameters += parameter.numel()
        else:
            frozen_parameters += parameter.numel()
    if trainable_parameters <= 0:
        raise PPOTrainError("PPO trainable parameter set is empty")
    return {
        "trainable_parameters": trainable_parameters,
        "frozen_parameters": frozen_parameters,
    }


def _flatten_recurrent_parameters(model: PTCGPolicyV1) -> None:
    model.event_gru.flatten_parameters()


def _zero_untrained_bc_value_output(model: PTCGPolicyV1) -> None:
    """Zero only the critic output layer; actor logits are structurally untouched."""
    output = model.value_head[-1]
    if not isinstance(output, torch.nn.Linear):
        raise PPOTrainError("value head output layer is not linear")
    with torch.no_grad():
        output.weight.zero_()
        if output.bias is not None:
            output.bias.zero_()


def _host_peak_rss_bytes() -> int:
    # Linux reports ru_maxrss in KiB.
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024


def _actor_snapshot_path(checkpoint_path: Path) -> Path:
    return checkpoint_path.with_name(checkpoint_path.name + ".actor-state.pt")


def _exact_resume_configuration(
    *,
    args: argparse.Namespace,
    runtime: GpuCabtRuntime,
) -> dict[str, Any]:
    return {
        "source_commit": args.source_commit,
        "model_label": args.model_label,
        "card_table_path": args.card_table.as_posix(),
        "initializer_checkpoint_path": args.bc_checkpoint.as_posix(),
        "policy_warmstart_checkpoint_path": (
            args.policy_warmstart_checkpoint.as_posix()
            if args.policy_warmstart_checkpoint is not None
            else None
        ),
        "v7_checkpoint_path": (
            args.v7_checkpoint.as_posix() if args.v7_checkpoint is not None else None
        ),
        "v5_checkpoint_path": (
            args.v5_checkpoint.as_posix() if args.v5_checkpoint is not None else None
        ),
        "deck_path": args.deck.as_posix(),
        "engine_abi": asdict(runtime.abi),
        "env_count": args.env_count,
        "stack_bytes": args.stack_bytes,
        "rollout_horizon": args.rollout_horizon,
        "chunk_boundaries": args.chunk_boundaries,
        "learner_lane_envs": args.learner_lane_envs,
        "optimizer_lanes_per_update": args.optimizer_lanes_per_update,
        "freeze_observation_encoder": args.freeze_observation_encoder,
        "checkpoint_entity_transformer": args.checkpoint_entity_transformer,
        "checkpoint_entity_transformer_first_layer_only": args.checkpoint_entity_transformer_first_layer_only,
        "frozen_reference_fraction": args.frozen_reference_fraction,
        "rollout_storage": args.rollout_storage,
        "frozen_v7_fraction": args.frozen_v7_fraction,
        "frozen_v5_fraction": args.frozen_v5_fraction,
        "seed": args.seed,
        "gamma": args.gamma,
        "gae_lambda": args.gae_lambda,
        "clip_coefficient": args.clip_coefficient,
        "value_clip_coefficient": args.value_clip_coefficient,
        "value_coefficient": args.value_coefficient,
        "entropy_coefficient": args.entropy_coefficient,
        "reference_kl_coefficient": args.reference_kl_coefficient,
        "bc_anchor_coefficient": args.bc_anchor_coefficient,
        "bc_anchor_episodes_per_corpus": args.bc_anchor_episodes_per_corpus,
        "bc_anchor_batch_size": args.bc_anchor_batch_size,
        "bc_anchor_sequence_length": args.bc_anchor_sequence_length,
        "bc_anchor_live_root": (
            args.bc_anchor_live_root.as_posix() if args.bc_anchor_live_root is not None else None
        ),
        "bc_anchor_exact_root": (
            args.bc_anchor_exact_root.as_posix() if args.bc_anchor_exact_root is not None else None
        ),
        "replay_tolerance": args.replay_tolerance,
        "post_validation_lanes": args.post_validation_lanes,
        "critic_calibration_terminal_trajectories": args.critic_calibration_terminal_trajectories,
        "critic_calibration_max_horizons": args.critic_calibration_max_horizons,
        "critic_calibration_learning_rate": args.critic_calibration_learning_rate,
        "completed_trajectories_only": args.completed_trajectories_only,
        "minimum_terminal_actor_trajectories": args.minimum_terminal_actor_trajectories,
        "maximum_post_kl": args.maximum_post_kl,
        "maximum_clip_fraction": args.maximum_clip_fraction,
        "learning_rate": args.learning_rate,
        "critic_learning_rate": args.critic_learning_rate,
        "max_gradient_norm": args.max_gradient_norm,
    }


def _save_exact_actor_snapshot(
    *,
    checkpoint_path: Path,
    actor_state: ActorStateV1,
    runtime: GpuCabtRuntime,
    configuration: dict[str, Any],
) -> dict[str, Any]:
    runtime.synchronize()
    snapshot_path = _actor_snapshot_path(checkpoint_path)
    payload = {
        "schema_version": ACTOR_SNAPSHOT_SCHEMA_VERSION,
        "kind": ACTOR_SNAPSHOT_KIND,
        "checkpoint_path": checkpoint_path.name,
        "configuration": configuration,
        "actor_state": {
            "hidden": actor_state.hidden.detach().to(device="cpu", dtype=torch.float32).contiguous(),
            "reference_hidden": actor_state.reference_hidden.detach()
            .to(device="cpu", dtype=torch.float32)
            .contiguous(),
            "assignment": actor_state.assignment.detach().to(device="cpu", dtype=torch.int8).contiguous(),
            "horizon_index": int(actor_state.horizon_index),
        },
        "engine": {
            "states": torch.from_numpy(runtime.states.get()).clone(),
            "runtimes": torch.from_numpy(runtime.runtimes.get()).clone(),
        },
    }
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = snapshot_path.with_name(snapshot_path.name + ".partial")
    size = 0
    try:
        torch.save(payload, temporary)
        size = temporary.stat().st_size
        if size <= 0 or size > MAX_ACTOR_SNAPSHOT_BYTES:
            raise PPOTrainError(
                f"actor snapshot size {size} is outside 1..{MAX_ACTOR_SNAPSHOT_BYTES} bytes"
            )
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, snapshot_path)
    finally:
        temporary.unlink(missing_ok=True)
    return {"path": snapshot_path.as_posix(), "payload_bytes": size}


def _restore_exact_actor_snapshot(
    *,
    checkpoint_path: Path,
    checkpoint_rollout_boundary: dict[str, Any],
    model: PTCGPolicyV1,
    runtime: GpuCabtRuntime,
    configuration: dict[str, Any],
) -> tuple[ActorStateV1, dict[str, Any]]:
    snapshot_path = _actor_snapshot_path(checkpoint_path)
    try:
        size = snapshot_path.stat().st_size
    except OSError as error:
        raise PPOTrainError(f"actor snapshot is missing: {error}") from error
    if size <= 0 or size > MAX_ACTOR_SNAPSHOT_BYTES:
        raise PPOTrainError("actor snapshot size is outside the supported bound")
    try:
        payload = torch.load(snapshot_path, map_location="cpu", weights_only=True)
    except Exception as error:
        raise PPOTrainError(f"restricted actor snapshot load failed: {error}") from error
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "kind",
        "checkpoint_path",
        "configuration",
        "actor_state",
        "engine",
    }:
        raise PPOTrainError("actor snapshot payload keys differ")
    if payload["schema_version"] != ACTOR_SNAPSHOT_SCHEMA_VERSION or payload["kind"] != ACTOR_SNAPSHOT_KIND:
        raise PPOTrainError("actor snapshot identity differs")
    if payload["checkpoint_path"] != checkpoint_path.name:
        raise PPOTrainError("actor snapshot is not linked to the requested training checkpoint")
    if payload["configuration"] != configuration:
        raise PPOTrainError("exact-resume configuration differs from the actor snapshot")
    expected_sidecar = checkpoint_rollout_boundary.get("actor_state_sidecar")
    if (
        checkpoint_rollout_boundary.get("actor_state_persisted") is not True
        or checkpoint_rollout_boundary.get("exact_resume_supported") is not True
        or expected_sidecar != snapshot_path.name
    ):
        raise PPOTrainError("training checkpoint does not declare an exact actor-state sidecar")
    actor = payload["actor_state"]
    engine = payload["engine"]
    if not isinstance(actor, dict) or set(actor) != {
        "hidden",
        "reference_hidden",
        "assignment",
        "horizon_index",
    }:
        raise PPOTrainError("actor snapshot recurrent state keys differ")
    if not isinstance(engine, dict) or set(engine) != {"states", "runtimes"}:
        raise PPOTrainError("actor snapshot engine keys differ")
    hidden = actor["hidden"]
    reference_hidden = actor["reference_hidden"]
    assignment = actor["assignment"]
    horizon_index = actor["horizon_index"]
    expected_hidden_shape = (runtime.env_count, 2, model.config.public_hidden)
    if (
        not isinstance(hidden, Tensor)
        or hidden.dtype != torch.float32
        or tuple(hidden.shape) != expected_hidden_shape
        or not torch.isfinite(hidden).all()
    ):
        raise PPOTrainError("actor snapshot hidden state differs")
    if (
        not isinstance(reference_hidden, Tensor)
        or reference_hidden.dtype != torch.float32
        or tuple(reference_hidden.shape) != expected_hidden_shape
        or not torch.isfinite(reference_hidden).all()
    ):
        raise PPOTrainError("actor snapshot reference hidden state differs")
    if (
        not isinstance(assignment, Tensor)
        or assignment.dtype != torch.int8
        or tuple(assignment.shape) != (runtime.env_count, 2)
    ):
        raise PPOTrainError("actor snapshot league assignment differs")
    if torch.any((assignment < POLICY_LEARNER) | (assignment > POLICY_FROZEN_V5)):
        raise PPOTrainError("actor snapshot contains an unknown policy id")
    _league_metrics_from_assignment(assignment)
    if not isinstance(horizon_index, int) or isinstance(horizon_index, bool) or horizon_index <= 0:
        raise PPOTrainError("actor snapshot horizon index must be a positive integer")
    if horizon_index != checkpoint_rollout_boundary.get("horizon_index"):
        raise PPOTrainError("actor snapshot horizon index differs from training checkpoint")
    raw_states = engine["states"]
    raw_runtimes = engine["runtimes"]
    if (
        not isinstance(raw_states, Tensor)
        or raw_states.dtype != torch.uint8
        or raw_states.ndim != 1
        or raw_states.numel() != runtime.states.size
    ):
        raise PPOTrainError("actor snapshot GPU-CABT core-state bytes differ")
    if (
        not isinstance(raw_runtimes, Tensor)
        or raw_runtimes.dtype != torch.uint8
        or raw_runtimes.ndim != 1
        or raw_runtimes.numel() != runtime.runtimes.size
    ):
        raise PPOTrainError("actor snapshot GPU-CABT runtime bytes differ")
    runtime.states.set(raw_states.contiguous().numpy())
    runtime.runtimes.set(raw_runtimes.contiguous().numpy())
    runtime.synchronize()
    status = runtime.status().torch(torch)
    runtime.synchronize()
    if torch.any(status.error_flags != 0):
        raise PPOTrainError("restored GPU-CABT state contains runtime error flags")
    device = next(model.parameters()).device
    restored = ActorStateV1(
        hidden=hidden.to(device=device),
        reference_hidden=reference_hidden.to(device=device),
        assignment=assignment.to(device=device),
        horizon_index=horizon_index,
    )
    return restored, {
        "path": snapshot_path.as_posix(),
        "payload_bytes": size,
        "horizon_index": horizon_index,
    }


def _balanced_rehearsal_records(root: Path, limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        raise PPOTrainError("BC anchor episode limit must be positive")
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise PPOTrainError(f"BC anchor manifest is missing: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PPOTrainError(f"cannot read BC anchor manifest {manifest_path}: {error}") from error
    records = manifest.get("records")
    if not isinstance(records, list):
        raise PPOTrainError(f"BC anchor manifest has no record list: {manifest_path}")
    buckets: dict[str, list[dict[str, Any]]] = {}
    for value in records:
        if not isinstance(value, dict) or value.get("split") != "train":
            continue
        team = str(value.get("teacher_team_name") or "")
        if not team:
            continue
        buckets.setdefault(team, []).append(value)
    if not buckets:
        raise PPOTrainError(f"BC anchor manifest has no training records: {manifest_path}")
    for values in buckets.values():
        values.sort(
            key=lambda record: (
                -float(record.get("teacher_score_qualification_value") or 0.0),
                int(record["episode_id"]),
            )
        )
    selected: list[dict[str, Any]] = []
    teams = sorted(buckets)
    while len(selected) < limit:
        advanced = False
        for team in teams:
            values = buckets[team]
            if not values:
                continue
            selected.append(values.pop(0))
            advanced = True
            if len(selected) >= limit:
                break
        if not advanced:
            break
    if not selected:
        raise PPOTrainError(f"BC anchor selection is empty: {manifest_path}")
    return selected


def _load_bc_anchor_groups(
    *,
    roots: Sequence[Path],
    episodes_per_corpus: int,
    batch_size: int,
    sequence_length: int,
) -> tuple[tuple[PackedMegaRecurrentGroup, ...], dict[str, Any]]:
    if not roots:
        raise PPOTrainError("BC anchor requires at least one materialized corpus root")
    if batch_size <= 0 or sequence_length <= 0:
        raise PPOTrainError("BC anchor batch size and sequence length must be positive")
    selected_by_root: list[list[MaterializedEpisodeV1]] = []
    source_records: list[dict[str, Any]] = []
    for root in roots:
        records = _balanced_rehearsal_records(root, episodes_per_corpus)
        episodes: list[MaterializedEpisodeV1] = []
        for record in records:
            path = root / str(record["path"])
            episode = load_materialized_episode(path)
            if episode.split != "train" or episode.episode_id != int(record["episode_id"]):
                raise PPOTrainError(f"BC anchor episode identity differs: {path}")
            episodes.append(episode)
        selected_by_root.append(episodes)
        source_records.append(
            {
                "root": str(root),
                "episodes": len(episodes),
                "teacher_teams": len({episode.teacher_team_name for episode in episodes}),
                "policy_targets": sum(episode.policy_targets for episode in episodes),
            }
        )
    interleaved: list[MaterializedEpisodeV1] = []
    maximum = max(len(episodes) for episodes in selected_by_root)
    for index in range(maximum):
        for episodes in selected_by_root:
            if index < len(episodes):
                interleaved.append(episodes[index])
    groups: list[PackedMegaRecurrentGroup] = []
    for start in range(0, len(interleaved), batch_size):
        batch = interleaved[start : start + batch_size]
        groups.append(
            pack_mega_recurrent_group(
                tuple(episode.decisions for episode in batch),
                sequence_length=sequence_length,
                pin_memory=True,
            )
        )
    if not groups:
        raise PPOTrainError("BC anchor packing produced no groups")
    return tuple(groups), {
        "sources": source_records,
        "groups": len(groups),
        "episodes": len(interleaved),
        "policy_targets": sum(group.policy_targets for group in groups),
        "batch_size": batch_size,
        "sequence_length": sequence_length,
    }


def _backward_bc_anchor(
    *,
    model: PTCGPolicyV1,
    group: PackedMegaRecurrentGroup,
    coefficient: float,
) -> dict[str, Any]:
    if coefficient <= 0 or not math.isfinite(coefficient):
        raise PPOTrainError("BC anchor coefficient must be finite and positive")
    device = next(model.parameters()).device
    hidden = model.initial_hidden(group.batch_size, device)
    weighted_loss = 0.0
    policy_targets = 0
    recurrent_decisions = 0
    started = time.perf_counter()
    for chunk in group.chunks:
        result = packed_mega_recurrent_chunk_loss(
            model,
            chunk,
            hidden=hidden,
            non_blocking=device.type == "cuda",
        )
        hidden = result.next_hidden.detach()
        recurrent_decisions += result.recurrent_decisions
        if result.loss is None:
            continue
        weight = result.policy_targets / group.policy_targets
        (coefficient * result.loss * weight).backward()
        weighted_loss += float(result.loss.detach().item()) * result.policy_targets
        policy_targets += result.policy_targets
    if policy_targets != group.policy_targets or policy_targets <= 0:
        raise PPOTrainError("BC anchor target accounting differs from packed group")
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    elapsed = time.perf_counter() - started
    return {
        "coefficient": coefficient,
        "episodes": group.batch_size,
        "policy_targets": policy_targets,
        "recurrent_decisions": recurrent_decisions,
        "mean_nll": weighted_loss / policy_targets,
        "seconds": elapsed,
        "policy_targets_per_second": policy_targets / max(elapsed, 1e-9),
    }


def _league_assignment(
    env_count: int,
    *,
    frozen_reference_fraction: float,
    frozen_v7_fraction: float,
    frozen_v5_fraction: float,
    seed: int,
    device: torch.device,
) -> tuple[Tensor, dict[str, Any]]:
    for value, label in (
        (frozen_reference_fraction, "frozen-reference fraction"),
        (frozen_v7_fraction, "frozen-v7 fraction"),
        (frozen_v5_fraction, "frozen-v5 fraction"),
    ):
        if not (0.0 <= value <= 1.0) or not math.isfinite(value):
            raise PPOTrainError(f"{label} must be finite and within [0, 1]")
    frozen_total = frozen_reference_fraction + frozen_v7_fraction + frozen_v5_fraction
    if frozen_total > 1.0:
        raise PPOTrainError("frozen league fractions must sum to <= 1")
    rng = np.random.default_rng(seed ^ 0x6C6561677565)
    draw = rng.random(env_count)
    reference_env = draw < frozen_reference_fraction
    v7_env = (draw >= frozen_reference_fraction) & (
        draw < frozen_reference_fraction + frozen_v7_fraction
    )
    v5_env = (draw >= frozen_reference_fraction + frozen_v7_fraction) & (draw < frozen_total)
    frozen_env = reference_env | v7_env | v5_env
    frozen_seats = rng.integers(0, 2, size=env_count, dtype=np.int64)
    assignment = np.full((env_count, 2), POLICY_LEARNER, dtype=np.int8)
    reference_rows = np.nonzero(reference_env)[0]
    v7_rows = np.nonzero(v7_env)[0]
    v5_rows = np.nonzero(v5_env)[0]
    assignment[reference_rows, frozen_seats[reference_rows]] = POLICY_FROZEN_REFERENCE
    assignment[v7_rows, frozen_seats[v7_rows]] = POLICY_FROZEN_V7
    assignment[v5_rows, frozen_seats[v5_rows]] = POLICY_FROZEN_V5
    tensor = torch.from_numpy(assignment).to(device=device)
    return tensor, {
        "current_selfplay_envs": int((~frozen_env).sum()),
        "frozen_reference_envs": int(reference_env.sum()),
        "frozen_v7_envs": int(v7_env.sum()),
        "frozen_v5_envs": int(v5_env.sum()),
        "frozen_fraction_realized": float(frozen_env.mean()),
        "frozen_reference_seat_0": int(np.sum(reference_env & (frozen_seats == 0))),
        "frozen_reference_seat_1": int(np.sum(reference_env & (frozen_seats == 1))),
        "frozen_v7_seat_0": int(np.sum(v7_env & (frozen_seats == 0))),
        "frozen_v7_seat_1": int(np.sum(v7_env & (frozen_seats == 1))),
        "frozen_v5_seat_0": int(np.sum(v5_env & (frozen_seats == 0))),
        "frozen_v5_seat_1": int(np.sum(v5_env & (frozen_seats == 1))),
    }


def _league_metrics_from_assignment(assignment: Tensor) -> dict[str, Any]:
    if assignment.ndim != 2 or assignment.shape[1] != 2 or assignment.dtype != torch.int8:
        raise PPOTrainError("league assignment must be an int8 [env, 2] policy-id tensor")
    if torch.any((assignment < POLICY_LEARNER) | (assignment > POLICY_FROZEN_V5)):
        raise PPOTrainError("league assignment contains an unknown policy id")
    frozen_0 = assignment[:, 0] != POLICY_LEARNER
    frozen_1 = assignment[:, 1] != POLICY_LEARNER
    if torch.any(frozen_0 & frozen_1):
        raise PPOTrainError("league assignment cannot freeze both seats in one environment")
    frozen_env = frozen_0 | frozen_1
    return {
        "current_selfplay_envs": int((~frozen_env).sum().item()),
        "frozen_reference_envs": int(torch.any(assignment == POLICY_FROZEN_REFERENCE, dim=1).sum().item()),
        "frozen_v7_envs": int(torch.any(assignment == POLICY_FROZEN_V7, dim=1).sum().item()),
        "frozen_v5_envs": int(torch.any(assignment == POLICY_FROZEN_V5, dim=1).sum().item()),
        "frozen_fraction_realized": float(frozen_env.float().mean().item()),
        "frozen_reference_seat_0": int((assignment[:, 0] == POLICY_FROZEN_REFERENCE).sum().item()),
        "frozen_reference_seat_1": int((assignment[:, 1] == POLICY_FROZEN_REFERENCE).sum().item()),
        "frozen_v7_seat_0": int((assignment[:, 0] == POLICY_FROZEN_V7).sum().item()),
        "frozen_v7_seat_1": int((assignment[:, 1] == POLICY_FROZEN_V7).sum().item()),
        "frozen_v5_seat_0": int((assignment[:, 0] == POLICY_FROZEN_V5).sum().item()),
        "frozen_v5_seat_1": int((assignment[:, 1] == POLICY_FROZEN_V5).sum().item()),
    }


def _initialize_actor_state(
    *,
    model: PTCGPolicyV1,
    runtime: GpuCabtRuntime,
    decks: Any,
    seed: int,
    frozen_reference_fraction: float,
    frozen_v7_fraction: float,
    frozen_v5_fraction: float,
) -> ActorStateV1:
    device = next(model.parameters()).device
    assignment, _ = _league_assignment(
        runtime.env_count,
        frozen_reference_fraction=frozen_reference_fraction,
        frozen_v7_fraction=frozen_v7_fraction,
        frozen_v5_fraction=frozen_v5_fraction,
        seed=seed,
        device=device,
    )
    runtime.reset(decks, seed=seed, stream_base=0)
    runtime.synchronize()
    hidden = model.initial_hidden(runtime.env_count * 2, device).reshape(
        runtime.env_count, 2, model.config.public_hidden
    )
    return ActorStateV1(
        hidden=hidden,
        reference_hidden=hidden.detach().clone(),
        assignment=assignment,
    )


def _recycle_terminal_envs(
    *,
    actor_state: ActorStateV1,
    runtime: GpuCabtRuntime,
    decks: Any,
    seed: int,
    frozen_reference_fraction: float,
    frozen_v7_fraction: float,
    frozen_v5_fraction: float,
) -> int:
    if actor_state.horizon_index == 0:
        return 0
    raw_status = runtime.status()
    runtime.synchronize()
    status = raw_status.torch(torch)
    terminal = status.game_results != 0
    count = int(terminal.sum().item())
    if count == 0:
        return 0
    fresh_assignment, _ = _league_assignment(
        runtime.env_count,
        frozen_reference_fraction=frozen_reference_fraction,
        frozen_v7_fraction=frozen_v7_fraction,
        frozen_v5_fraction=frozen_v5_fraction,
        seed=seed,
        device=actor_state.assignment.device,
    )
    runtime.reset_selected(
        decks,
        terminal.to(dtype=torch.uint8),
        seed=seed,
        stream_base=actor_state.horizon_index * runtime.env_count,
    )
    actor_state.hidden[terminal] = 0
    actor_state.reference_hidden[terminal] = 0
    actor_state.assignment[terminal] = fresh_assignment[terminal]
    runtime.synchronize()
    return count


def _clone_actions(actions: BatchedCompoundActionV1) -> BatchedCompoundActionV1:
    return BatchedCompoundActionV1(
        selected_indices=actions.selected_indices.detach().clone(),
        selected_lengths=actions.selected_lengths.detach().clone(),
        stopped=actions.stopped.detach().clone(),
        log_probabilities=actions.log_probabilities.detach().float().clone(),
        normalized_entropies=actions.normalized_entropies.detach().float().clone(),
    )


def _compact_batch_for_rollout(
    batch: TorchDecisionBatch,
    *,
    storage: str,
) -> TorchDecisionBatch:
    """Losslessly compact rollout observations on CPU or CUDA."""
    if storage not in {"cpu-compact", "cuda-compact"}:
        raise PPOTrainError(f"unsupported rollout storage {storage!r}")
    values: dict[str, Any] = {"batch_size": batch.batch_size}
    for name, value in batch.__dict__.items():
        if name == "batch_size":
            continue
        tensor = value.detach()
        if tensor.dtype == torch.long:
            tensor = tensor.to(dtype=torch.int32)
        elif tensor.dtype == torch.float32:
            if not _FAST_VALIDATED_GPU_PATH:
                if tensor.numel() and torch.any(torch.abs(tensor) > 2048):
                    raise PPOTrainError(
                        f"cannot losslessly compact {name}: numeric value exceeds float16 exact-integer range"
                    )
                if tensor.numel() and torch.any(tensor != tensor.round()):
                    raise PPOTrainError(
                        f"cannot losslessly compact {name}: GPU bridge numeric field is fractional"
                    )
            tensor = tensor.to(dtype=torch.float16)
        if storage == "cpu-compact":
            tensor = tensor.cpu()
        values[name] = tensor
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


def _compact_actions_for_rollout(
    actions: BatchedCompoundActionV1,
    *,
    storage: str,
) -> BatchedCompoundActionV1:
    if storage not in {"cpu-compact", "cuda-compact"}:
        raise PPOTrainError(f"unsupported rollout storage {storage!r}")
    device = torch.device("cpu") if storage == "cpu-compact" else actions.selected_lengths.device
    return BatchedCompoundActionV1(
        selected_indices=actions.selected_indices.detach().to(device=device, dtype=torch.int32),
        selected_lengths=actions.selected_lengths.detach().to(device=device, dtype=torch.int32),
        stopped=actions.stopped.detach().to(device=device),
        log_probabilities=actions.log_probabilities.detach().to(device=device, dtype=torch.float32),
        normalized_entropies=actions.normalized_entropies.detach().to(device=device, dtype=torch.float32),
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
        if step.env_indices.numel():
            first_env = int(step.env_indices[0].item())
            last_env = int(step.env_indices[-1].item())
            if first_env >= env_start and last_env < env_end:
                lane_steps.append(step)
                indices.append(torch.arange(step.flat_start, step.flat_end, dtype=torch.long))
                continue
            if last_env < env_start or first_env >= env_end:
                continue
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


def _collect_fixed_horizon_rollout(
    *,
    model: PTCGPolicyV1,
    frozen_reference_model: PTCGPolicyV1,
    frozen_v7_model: PTCGPolicyV1,
    frozen_v5_model: PTCGPolicyV1,
    actor_state: ActorStateV1,
    runtime: GpuCabtRuntime,
    decks: Any,
    seed: int,
    frozen_reference_fraction: float,
    frozen_v7_fraction: float,
    frozen_v5_fraction: float,
    rollout_horizon: int,
    chunk_boundaries: int,
    learner_lane_envs: int,
    bf16: bool,
    rollout_storage: str,
    heartbeat_seconds: float = 10.0,
) -> RolloutV1:
    device = next(model.parameters()).device
    recycled_envs = _recycle_terminal_envs(
        actor_state=actor_state,
        runtime=runtime,
        decks=decks,
        seed=seed,
        frozen_reference_fraction=frozen_reference_fraction,
        frozen_v7_fraction=frozen_v7_fraction,
        frozen_v5_fraction=frozen_v5_fraction,
    )
    hidden = actor_state.hidden
    assignment = actor_state.assignment
    reference_hidden_snapshot = actor_state.reference_hidden.detach().clone()
    league_metrics = _league_metrics_from_assignment(assignment)
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
    frozen_reference_decisions = 0
    frozen_v7_decisions = 0
    frozen_v5_decisions = 0
    meaningful_targets = 0
    projection_seconds = 0.0
    bridge_seconds = 0.0
    model_seconds = 0.0
    engine_seconds = 0.0
    boundaries_executed = 0
    started = time.perf_counter()
    last_heartbeat = started
    learner_inference_groups = 0

    autocast = lambda: torch.autocast(  # noqa: E731
        device_type='cuda', dtype=torch.bfloat16, enabled=bf16
    )

    with torch.inference_mode(), autocast():
        for cached_policy in (model, frozen_reference_model, frozen_v7_model, frozen_v5_model):
            cached_policy.catalog.prepare_encoded_cache()

    for boundary in range(rollout_horizon):
        raw_status = runtime.status()
        runtime.synchronize()
        status = raw_status.torch(torch)
        errors = status.error_flags.to(torch.long)
        if torch.any(errors != 0):
            bad = torch.nonzero(errors != 0, as_tuple=False).squeeze(1).cpu().tolist()[:16]
            raise PPOTrainError(f'GPU-CABT runtime error before boundary {boundary}: {bad}')
        active = status.game_results == 0
        active_indices = torch.nonzero(active, as_tuple=False).squeeze(1).to(torch.long)
        active_count = int(active_indices.numel())
        if active_count == 0:
            break
        if torch.any(active & (status.select_types == 0)):
            bad = torch.nonzero(active & (status.select_types == 0), as_tuple=False).squeeze(1)
            raise PPOTrainError(
                f'active environment has no selection boundary: {bad[:16].cpu().tolist()}'
            )
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
        active_policy_ids = assignment[active_indices, active_actors]
        learner_envs = active_indices[active_policy_ids == POLICY_LEARNER]
        frozen_reference_envs = active_indices[active_policy_ids == POLICY_FROZEN_REFERENCE]
        frozen_v7_envs = active_indices[active_policy_ids == POLICY_FROZEN_V7]
        frozen_v5_envs = active_indices[active_policy_ids == POLICY_FROZEN_V5]

        response_present.zero_()
        selected_counts.zero_()
        selected_indices.zero_()

        def run_group(
            env_indices: Tensor,
            policy: PTCGPolicyV1,
            *,
            policy_id: int,
        ) -> None:
            nonlocal flat_offset, bridge_seconds, model_seconds
            nonlocal learner_decisions, frozen_reference_decisions, frozen_v7_decisions, frozen_v5_decisions, meaningful_targets
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
                    primary_option_logits=output.option_logits,
                    option_embeddings=output.option_embeddings,
                    option_offsets=output.option_offsets,
                    available_mask=batch.option_available,
                    minimum_counts=meta.minimum_counts,
                    maximum_counts=meta.maximum_counts,
                    generator=generator,
                )
            runtime.synchronize()
            model_seconds += time.perf_counter() - model_started
            if not _FAST_VALIDATED_GPU_PATH:
                if not torch.isfinite(output.values).all() or not torch.isfinite(output.hidden).all():
                    raise PPOTrainError('rollout policy emitted a nonfinite value or hidden state')
                if not torch.isfinite(actions.log_probabilities).all():
                    raise PPOTrainError('rollout compound sampler emitted a nonfinite log probability')
            hidden[meta.env_indices, meta.actors] = output.hidden.to(hidden.dtype)
            _apply_actions(
                response_present=response_present,
                selected_counts=selected_counts,
                selected_indices=selected_indices,
                env_indices=meta.env_indices,
                actions=actions,
            )
            if policy_id == POLICY_FROZEN_REFERENCE:
                frozen_reference_decisions += batch.batch_size
                return
            if policy_id == POLICY_FROZEN_V7:
                frozen_v7_decisions += batch.batch_size
                return
            if policy_id == POLICY_FROZEN_V5:
                frozen_v5_decisions += batch.batch_size
                return
            if policy_id != POLICY_LEARNER:
                raise PPOTrainError(f"unknown rollout policy id {policy_id}")

            policy_mask = meaningful_compound_policy_mask(
                batch,
                minimum_counts=meta.minimum_counts,
                maximum_counts=meta.maximum_counts,
                validated_fast_path=_FAST_VALIDATED_GPU_PATH,
            )
            count = batch.batch_size
            learner_decisions += count
            owners.append((meta.env_indices * 2 + meta.actors).detach().clone())
            old_logps.append(actions.log_probabilities.detach().float().clone())
            old_values.append(output.values.detach().float().clone())
            old_entropies.append(actions.normalized_entropies.detach().float().clone())
            policy_masks.append(policy_mask.detach().clone())
            steps.append(
                LearnerStepV1(
                    boundary=boundary,
                    batch=_compact_batch_for_rollout(batch, storage=rollout_storage),
                    env_indices=meta.env_indices.detach().to(dtype=torch.int32).cpu(),
                    actors=meta.actors.detach().to(dtype=torch.int32).cpu(),
                    minimum_counts=meta.minimum_counts.detach().to(dtype=torch.int32).cpu(),
                    maximum_counts=meta.maximum_counts.detach().to(dtype=torch.int32).cpu(),
                    actions=_compact_actions_for_rollout(actions, storage=rollout_storage),
                    flat_start=flat_offset,
                    flat_end=flat_offset + count,
                )
            )
            flat_offset += count

        for env_start in range(0, runtime.env_count, learner_lane_envs):
            env_end = min(runtime.env_count, env_start + learner_lane_envs)
            lane_mask = (learner_envs >= env_start) & (learner_envs < env_end)
            lane_envs = learner_envs[lane_mask]
            if lane_envs.numel():
                run_group(lane_envs, model, policy_id=POLICY_LEARNER)
                learner_inference_groups += 1
        run_group(frozen_reference_envs, frozen_reference_model, policy_id=POLICY_FROZEN_REFERENCE)
        run_group(frozen_v7_envs, frozen_v7_model, policy_id=POLICY_FROZEN_V7)
        run_group(frozen_v5_envs, frozen_v5_model, policy_id=POLICY_FROZEN_V5)
        actor_decisions += active_count

        engine_started = time.perf_counter()
        runtime.step(response_present, selected_counts, selected_indices)
        runtime.synchronize()
        engine_seconds += time.perf_counter() - engine_started
        boundaries_executed = boundary + 1

        now = time.perf_counter()
        if heartbeat_seconds > 0 and now - last_heartbeat >= heartbeat_seconds:
            print(
                json.dumps(
                    {
                        'event': 'ppo_rollout_heartbeat',
                        'horizon': actor_state.horizon_index,
                        'boundary': boundary + 1,
                        'rollout_horizon': rollout_horizon,
                        'active_envs': active_count,
                        'actor_decisions': actor_decisions,
                        'actor_dps': actor_decisions / max(now - started, 1e-9),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            last_heartbeat = now

    for cached_policy in (model, frozen_reference_model, frozen_v7_model, frozen_v5_model):
        cached_policy.catalog.clear_encoded_cache()

    if policy_masks:
        meaningful_targets = int(torch.cat(policy_masks).sum().item())

    raw_final_status = runtime.status()
    runtime.synchronize()
    final_status = raw_final_status.torch(torch)
    final_errors = final_status.error_flags.to(torch.long)
    if torch.any(final_errors != 0):
        bad = torch.nonzero(final_errors != 0, as_tuple=False).squeeze(1).cpu().tolist()[:16]
        raise PPOTrainError(f'GPU-CABT runtime error at horizon end: {bad}')
    final_results = final_status.game_results.to(torch.long).clone()
    active_last = int((final_results == 0).sum().item())
    terminal_envs = runtime.env_count - active_last
    elapsed = time.perf_counter() - started
    actor_state.horizon_index += 1
    if not owners:
        raise PPOTrainError('fixed-horizon rollout produced no learner decisions')
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
            'boundaries': boundaries_executed,
            'rollout_seconds': elapsed,
            'actor_recurrent_decisions': actor_decisions,
            'learner_recurrent_decisions': learner_decisions,
            'frozen_reference_recurrent_decisions': frozen_reference_decisions,
            'frozen_v7_recurrent_decisions': frozen_v7_decisions,
            'frozen_v5_recurrent_decisions': frozen_v5_decisions,
            'meaningful_policy_targets': meaningful_targets,
            'actor_decisions_per_second': actor_decisions / max(elapsed, 1e-9),
            'learner_decisions_per_second': learner_decisions / max(elapsed, 1e-9),
            'learner_inference_groups': learner_inference_groups,
            'learner_inference_lane_envs': learner_lane_envs,
            'active_first': runtime.env_count,
            'active_last': active_last,
            'terminal_envs': terminal_envs,
            'recycled_envs': recycled_envs,
            'league': league_metrics,
            'timing_accumulators_seconds': {
                'projection': projection_seconds,
                'bridge': bridge_seconds,
                'model_and_compound': model_seconds,
                'engine_step': engine_seconds,
            },
        },
        reference_hidden_snapshot=reference_hidden_snapshot,
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
    compute_entropy: bool,
) -> tuple[Tensor, Tensor, Tensor]:
    device = hidden_snapshot.device
    hidden = hidden_snapshot.reshape(-1, model.config.public_hidden)
    log_probabilities: list[Tensor] = []
    values: list[Tensor] = []
    entropies: list[Tensor] = []
    context = torch.enable_grad() if gradient else torch.inference_mode()
    autocast = torch.autocast(device_type="cuda", dtype=torch.bfloat16, enabled=bf16)
    with context, autocast:
        model.catalog.prepare_encoded_cache()
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
            replay_values = (
                model.value_head(output.hidden.detach()).squeeze(-1)
                if gradient
                else output.values
            )
            replay_logp, replay_entropy = replay_compound_actions_batched(
                model,
                public_hidden=output.hidden,
                primary_option_logits=output.option_logits,
                option_embeddings=output.option_embeddings,
                option_offsets=output.option_offsets,
                available_mask=batch.option_available,
                minimum_counts=minimum_counts,
                maximum_counts=maximum_counts,
                actions=actions,
                compute_entropy=compute_entropy,
            )
            log_probabilities.append(replay_logp.float())
            values.append(replay_values.float())
            entropies.append(replay_entropy.float())
            hidden = hidden.index_copy(0, owner, output.hidden.to(hidden.dtype))
        model.catalog.clear_encoded_cache()
    return torch.cat(log_probabilities), torch.cat(values), torch.cat(entropies)


def _replay_reference_log_probabilities(
    *,
    model: PTCGPolicyV1,
    rollout: RolloutV1,
    bf16: bool,
) -> tuple[Tensor, Tensor, float]:
    device = next(model.parameters()).device
    hidden = rollout.reference_hidden_snapshot.reshape(-1, model.config.public_hidden).clone()
    reference_logp = torch.full_like(rollout.old_log_probabilities, float("nan"))
    started = time.perf_counter()
    model.eval()
    with torch.inference_mode(), torch.autocast(
        device_type="cuda", dtype=torch.bfloat16, enabled=bf16
    ):
        model.catalog.prepare_encoded_cache()
        for step in rollout.steps:
            batch = _restore_batch_to_device(step.batch, device)
            env_indices = step.env_indices.to(device=device, dtype=torch.long)
            actors = step.actors.to(device=device, dtype=torch.long)
            minimum_counts = step.minimum_counts.to(device=device, dtype=torch.long)
            maximum_counts = step.maximum_counts.to(device=device, dtype=torch.long)
            actions = _restore_actions_to_device(step.actions, device)
            owner = env_indices * 2 + actors
            hidden_before = hidden.index_select(0, owner)
            output = model(batch, hidden_before)
            replay_logp, _ = replay_compound_actions_batched(
                model,
                public_hidden=output.hidden,
                primary_option_logits=output.option_logits,
                option_embeddings=output.option_embeddings,
                option_offsets=output.option_offsets,
                available_mask=batch.option_available,
                minimum_counts=minimum_counts,
                maximum_counts=maximum_counts,
                actions=actions,
                compute_entropy=False,
            )
            reference_logp[step.flat_start : step.flat_end] = replay_logp.float()
            hidden = hidden.index_copy(0, owner, output.hidden.to(hidden.dtype))
        model.catalog.clear_encoded_cache()
    torch.cuda.synchronize(device)
    elapsed = time.perf_counter() - started
    if not torch.isfinite(reference_logp).all():
        raise PPOTrainError("frozen reference replay did not cover every learner recurrent node")
    return (
        reference_logp,
        hidden.reshape_as(rollout.reference_hidden_snapshot),
        elapsed,
    )


def _terminal_outcome_targets(rollout: RolloutV1) -> tuple[Tensor, Tensor, int]:
    owner_envs = torch.div(rollout.owner_ids, 2, rounding_mode="floor")
    owner_players = rollout.owner_ids.remainder(2)
    results = rollout.final_results.index_select(0, owner_envs)
    if torch.any((results < 0) | (results > 3)):
        raise PPOTrainError("terminal-outcome calibration saw an invalid game result")
    terminal_mask = results != 0
    targets = torch.where(
        results == 3,
        torch.zeros_like(rollout.old_values),
        torch.where(
            results == owner_players + 1,
            torch.ones_like(rollout.old_values),
            -torch.ones_like(rollout.old_values),
        ),
    )
    terminal_trajectories = int(torch.unique(rollout.owner_ids[terminal_mask]).numel())
    return targets, terminal_mask, terminal_trajectories


def _critic_calibration_update(
    *,
    model: PTCGPolicyV1,
    optimizer: torch.optim.Optimizer,
    rollout: RolloutV1,
    chunk_boundaries: int,
    learner_lane_envs: int,
    max_gradient_norm: float,
    bf16: bool,
) -> dict[str, Any]:
    targets, terminal_mask, terminal_trajectories = _terminal_outcome_targets(rollout)
    terminal_nodes = int(terminal_mask.sum().item())
    if terminal_nodes == 0:
        return {
            "updated": False,
            "terminal_trajectories": 0,
            "terminal_nodes": 0,
            "loss": None,
            "gradient_norm": None,
        }
    chunks = _steps_by_chunk(rollout, chunk_boundaries)
    lane_ranges = [
        (start, min(start + learner_lane_envs, rollout.final_results.numel()))
        for start in range(0, rollout.final_results.numel(), learner_lane_envs)
    ]
    optimizer.zero_grad(set_to_none=True)
    weighted_loss = 0.0
    replayed_terminal_nodes = 0
    started = time.perf_counter()
    model.train()
    for chunk_index, steps in chunks:
        hidden_snapshot = rollout.chunk_hidden_snapshots[chunk_index]
        for env_start, env_end in lane_ranges:
            lane_steps, cpu_indices = _lane_steps_and_indices(
                steps, env_start=env_start, env_end=env_end
            )
            if not lane_steps:
                continue
            indices = cpu_indices.to(device=rollout.old_values.device)
            lane_terminal = terminal_mask.index_select(0, indices)
            lane_nodes = int(lane_terminal.sum().item())
            if lane_nodes == 0:
                continue
            _, values, _ = _replay_chunk(
                model=model,
                steps=lane_steps,
                hidden_snapshot=hidden_snapshot,
                gradient=True,
                bf16=bf16,
                compute_entropy=False,
            )
            lane_targets = targets.index_select(0, indices)
            loss = 0.5 * (values[lane_terminal] - lane_targets[lane_terminal]).square().mean()
            weight = lane_nodes / terminal_nodes
            (loss * weight).backward()
            weighted_loss += float(loss.detach().item()) * weight
            replayed_terminal_nodes += lane_nodes
    if replayed_terminal_nodes != terminal_nodes:
        raise PPOTrainError(
            f"critic calibration replay covered {replayed_terminal_nodes} / {terminal_nodes} terminal nodes"
        )
    require_finite_gradients(model.value_head.parameters())
    gradient_norm_sq = 0.0
    for parameter in model.value_head.parameters():
        if parameter.grad is not None:
            gradient_norm_sq += float(parameter.grad.detach().float().square().sum().item())
    gradient_norm = math.sqrt(gradient_norm_sq)
    torch.nn.utils.clip_grad_norm_(model.value_head.parameters(), max_gradient_norm)
    optimizer.step()
    return {
        "updated": True,
        "terminal_trajectories": terminal_trajectories,
        "terminal_nodes": terminal_nodes,
        "loss": weighted_loss,
        "gradient_norm": gradient_norm,
        "seconds": time.perf_counter() - started,
    }


def _weighted_metrics_accumulator(device: torch.device) -> dict[str, Tensor]:
    return {
        name: torch.zeros((), dtype=torch.float32, device=device)
        for name in (
            "total_loss",
            "policy_loss",
            "value_loss",
            "entropy",
            "approximate_kl",
            "clip_fraction",
            "reference_kl",
        )
    }


def _add_weighted_loss(
    target: dict[str, Tensor],
    loss: Any,
    *,
    policy_weight: Tensor | float,
    value_weight: Tensor | float,
    value_coefficient: float,
    entropy_coefficient: float,
    reference_kl: Tensor,
    reference_kl_coefficient: float,
) -> None:
    target["policy_loss"] += loss.policy.detach().float() * policy_weight
    target["value_loss"] += loss.value.detach().float() * value_weight
    target["entropy"] += loss.entropy.detach().float() * policy_weight
    target["approximate_kl"] += loss.approximate_kl.detach().float() * policy_weight
    target["clip_fraction"] += loss.clip_fraction.detach().float() * policy_weight
    target["reference_kl"] += reference_kl.detach().float() * policy_weight
    target["total_loss"] = (
        target["policy_loss"]
        + value_coefficient * target["value_loss"]
        - entropy_coefficient * target["entropy"]
        + reference_kl_coefficient * target["reference_kl"]
    )


def _materialize_weighted_metrics(target: dict[str, Tensor]) -> dict[str, float]:
    names = tuple(target)
    values = torch.stack([target[name] for name in names]).detach().cpu().tolist()
    return {name: float(value) for name, value in zip(names, values, strict=True)}


def _explained_variance(values: Tensor, targets: Tensor) -> float:
    if values.shape != targets.shape or values.numel() == 0:
        raise PPOTrainError("explained-variance tensors must be nonempty and shape-matched")
    target_variance = targets.float().var(unbiased=False)
    if not torch.isfinite(target_variance):
        raise PPOTrainError("explained-variance target variance is nonfinite")
    if float(target_variance.item()) <= 1e-12:
        return 0.0
    residual_variance = (targets.float() - values.float()).var(unbiased=False)
    value = 1.0 - float((residual_variance / target_variance).item())
    if not math.isfinite(value):
        raise PPOTrainError("explained variance is nonfinite")
    return value


def _ppo_update(
    *,
    model: PTCGPolicyV1,
    optimizer: torch.optim.Optimizer,
    scheduler: Any,
    rollout: RolloutV1,
    advantages: Tensor,
    returns: Tensor,
    value_mask: Tensor,
    reference_log_probabilities: Tensor,
    chunk_boundaries: int,
    learner_lane_envs: int,
    clip_coefficient: float,
    optimizer_lanes_per_update: int,
    optimizer_lane_offset: int,
    value_clip_coefficient: float,
    value_coefficient: float,
    entropy_coefficient: float,
    reference_kl_coefficient: float,
    bc_anchor_group: PackedMegaRecurrentGroup | None,
    bc_anchor_coefficient: float,
    max_gradient_norm: float,
    replay_tolerance: float,
    maximum_post_kl: float,
    maximum_clip_fraction: float,
    full_post_replay: bool,
    post_validation_lanes: int,
    post_validation_lane_offset: int,
    bf16: bool,
) -> dict[str, Any]:
    if value_mask.shape != rollout.old_values.shape or value_mask.dtype != torch.bool:
        raise PPOTrainError("fixed-horizon value mask must be boolean and match rollout rows")
    full_policy_mask = rollout.policy_mask & value_mask
    full_valid = int(full_policy_mask.sum().item())
    if full_valid <= 0:
        raise PPOTrainError("rollout contains no meaningful learner actions")
    full_value_nodes = int(value_mask.sum().item())
    if full_value_nodes <= 0:
        raise PPOTrainError("rollout contains no learner recurrent value nodes")
    if reference_log_probabilities.shape != rollout.old_log_probabilities.shape:
        raise PPOTrainError("frozen reference log probabilities differ from rollout shape")
    if reference_kl_coefficient < 0 or not math.isfinite(reference_kl_coefficient):
        raise PPOTrainError("reference KL coefficient must be finite and nonnegative")
    if bc_anchor_coefficient < 0 or not math.isfinite(bc_anchor_coefficient):
        raise PPOTrainError("BC anchor coefficient must be finite and nonnegative")
    if (bc_anchor_group is None) != (bc_anchor_coefficient == 0.0):
        raise PPOTrainError("BC anchor group/coefficient enablement differs")
    if replay_tolerance < 0 or not math.isfinite(replay_tolerance):
        raise PPOTrainError("replay tolerance must be finite and nonnegative")
    if maximum_post_kl <= 0 or not math.isfinite(maximum_post_kl):
        raise PPOTrainError("maximum post-update KL must be finite and positive")
    if not (0 < maximum_clip_fraction <= 1) or not math.isfinite(maximum_clip_fraction):
        raise PPOTrainError("maximum clip fraction must be within (0, 1]")
    if post_validation_lanes <= 0:
        raise PPOTrainError("post-validation lane count must be positive")
    chunks = _steps_by_chunk(rollout, chunk_boundaries)
    env_count = int(next(iter(rollout.chunk_hidden_snapshots.values())).shape[0])
    if learner_lane_envs <= 0 or learner_lane_envs > env_count:
        raise PPOTrainError("learner lane env count must stay within 1..env_count")
    lane_ranges = [
        (start, min(env_count, start + learner_lane_envs))
        for start in range(0, env_count, learner_lane_envs)
    ]
    if optimizer_lanes_per_update < 0:
        raise PPOTrainError("optimizer lane count must be nonnegative")
    if optimizer_lanes_per_update == 0 or optimizer_lanes_per_update >= len(lane_ranges):
        optimizer_lane_ranges = lane_ranges
    else:
        start_lane = optimizer_lane_offset % len(lane_ranges)
        optimizer_lane_ranges = [
            lane_ranges[(start_lane + index) % len(lane_ranges)]
            for index in range(optimizer_lanes_per_update)
        ]
    owner_envs = torch.div(rollout.owner_ids, 2, rounding_mode="floor")
    optimizer_row_mask = torch.zeros_like(value_mask)
    for env_start, env_end in optimizer_lane_ranges:
        optimizer_row_mask |= (owner_envs >= env_start) & (owner_envs < env_end)
    value_mask = value_mask & optimizer_row_mask
    policy_mask = rollout.policy_mask & value_mask
    total_valid = int(policy_mask.sum().item())
    total_value_nodes = int(value_mask.sum().item())
    if total_valid <= 0 or total_value_nodes <= 0:
        raise PPOTrainError("selected optimizer lanes contain no trainable PPO samples")
    selected_advantages = advantages[policy_mask]
    advantage_mean = selected_advantages.mean()
    advantage_std = selected_advantages.std(unbiased=False)
    normalized_advantages = advantages.clone()
    normalized_advantages[policy_mask] = (
        selected_advantages - advantage_mean
    ) / (advantage_std + 1e-8)
    before = _parameter_snapshot(model)
    optimizer.zero_grad(set_to_none=True)
    model.train()
    pre_metrics_device = _weighted_metrics_accumulator(policy_mask.device)
    replay_max_logp_error_device = torch.zeros((), device=policy_mask.device)
    replay_max_ratio_error_device = torch.zeros((), device=policy_mask.device)
    replay_max_value_error_device = torch.zeros((), device=policy_mask.device)
    replayed_actions = 0
    started = time.perf_counter()

    learner_minibatches = 0
    for chunk_index, steps in chunks:
        hidden_snapshot = rollout.chunk_hidden_snapshots[chunk_index]
        for env_start, env_end in optimizer_lane_ranges:
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
                compute_entropy=entropy_coefficient > 0.0,
            )
            old_logp = rollout.old_log_probabilities.index_select(0, indices)
            old_values = rollout.old_values.index_select(0, indices)
            lane_mask = policy_mask.index_select(0, indices)
            lane_value_mask = value_mask.index_select(0, indices)
            if _FAST_VALIDATED_GPU_PATH:
                policy_weight = lane_mask.float().sum() / total_valid
                value_weight = lane_value_mask.float().sum() / total_value_nodes
            else:
                lane_valid = int(lane_mask.sum().item())
                lane_value_nodes = int(lane_value_mask.sum().item())
                if lane_value_nodes <= 0:
                    continue
                policy_weight = lane_valid / total_valid
                value_weight = lane_value_nodes / total_value_nodes
            lane_advantages = normalized_advantages.index_select(0, indices)
            lane_returns = returns.index_select(0, indices)
            lane_reference_logp = reference_log_probabilities.index_select(0, indices)
            logp_difference = torch.abs(new_logp.detach() - old_logp)
            ratio_error = torch.abs(torch.exp(new_logp.detach() - old_logp) - 1.0)
            replay_max_logp_error_device = torch.maximum(
                replay_max_logp_error_device, logp_difference.max()
            )
            replay_max_ratio_error_device = torch.maximum(
                replay_max_ratio_error_device, ratio_error.max()
            )
            replay_max_value_error_device = torch.maximum(
                replay_max_value_error_device,
                torch.abs(new_values.detach() - old_values).max(),
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
                value_mask=lane_value_mask,
                clip_coefficient=clip_coefficient,
                value_clip_coefficient=value_clip_coefficient,
                value_coefficient=value_coefficient,
                entropy_coefficient=entropy_coefficient,
                normalize_advantages=False,
                validated_fast_path=_FAST_VALIDATED_GPU_PATH,
            )
            reference_kl = (
                sampled_reference_kl(
                    new_log_probabilities=new_logp,
                    old_log_probabilities=old_logp,
                    reference_log_probabilities=lane_reference_logp,
                    policy_mask=lane_mask,
                )
                if reference_kl_coefficient > 0.0
                else new_logp.new_zeros(())
            )
            weighted_total = (
                loss.policy * policy_weight
                + value_coefficient * loss.value * value_weight
                - entropy_coefficient * loss.entropy * policy_weight
                + reference_kl_coefficient * reference_kl * policy_weight
            )
            weighted_total.backward()
            _add_weighted_loss(
                pre_metrics_device,
                loss,
                policy_weight=policy_weight,
                value_weight=value_weight,
                value_coefficient=value_coefficient,
                entropy_coefficient=entropy_coefficient,
                reference_kl=reference_kl,
                reference_kl_coefficient=reference_kl_coefficient,
            )
            learner_minibatches += 1

    replay_max_logp_error, replay_max_ratio_error, replay_max_value_error = (
        float(value)
        for value in torch.stack(
            (
                replay_max_logp_error_device,
                replay_max_ratio_error_device,
                replay_max_value_error_device,
            )
        ).detach().cpu().tolist()
    )
    pre_metrics = _materialize_weighted_metrics(pre_metrics_device)

    if replay_max_logp_error > replay_tolerance or replay_max_ratio_error > replay_tolerance:
        raise PPOTrainError(
            "old-policy probability replay mismatch: "
            f"logp={replay_max_logp_error} ratio={replay_max_ratio_error} "
            f"tolerance={replay_tolerance}"
        )
    if replay_max_value_error > replay_tolerance:
        raise PPOTrainError(
            "old critic replay mismatch: "
            f"value={replay_max_value_error} tolerance={replay_tolerance}"
        )

    bc_anchor_metrics: dict[str, Any] = {
        "enabled": False,
        "coefficient": bc_anchor_coefficient,
        "seconds": 0.0,
    }
    if bc_anchor_group is not None:
        bc_anchor_metrics = {
            "enabled": True,
            **_backward_bc_anchor(
                model=model,
                group=bc_anchor_group,
                coefficient=bc_anchor_coefficient,
            ),
        }

    clip_grad = torch.nn.utils.clip_grad_norm_(
        model.parameters(),
        max_gradient_norm,
        error_if_nonfinite=True,
    )
    gradient_norm = float(clip_grad.item())
    clip_grad_return = gradient_norm
    optimizer.step()
    scheduler.step()
    update_seconds = time.perf_counter() - started
    parameter_delta = _parameter_delta_l2(model, before)
    actor_parameter_delta, critic_parameter_delta = _parameter_delta_partitions(model, before)
    if parameter_delta <= 0:
        raise PPOTrainError("PPO optimizer step did not change model parameters")

    # Keep the same deterministic train-mode kernels used by rollout and gradient replay.
    # PTCGPolicyV1 has zero dropout, so module mode changes numerics but not stochasticity.
    # Exact old-policy replay above always covers every learner sample. Post-step safety
    # replay can rotate over a lane subset on ordinary updates, but checkpoint/final
    # updates must validate the full rollout.
    model.train()
    if len(optimizer_lane_ranges) < len(lane_ranges):
        post_lane_ranges = optimizer_lane_ranges[:post_validation_lanes]
    elif full_post_replay or post_validation_lanes >= len(lane_ranges):
        post_lane_ranges = lane_ranges
    else:
        lane_count = min(post_validation_lanes, len(lane_ranges))
        start = post_validation_lane_offset % len(lane_ranges)
        post_lane_ranges = [
            lane_ranges[(start + index) % len(lane_ranges)] for index in range(lane_count)
        ]
    validation_cpu_indices: list[Tensor] = []
    for _chunk_index, validation_steps in chunks:
        for env_start, env_end in post_lane_ranges:
            _lane_steps, cpu_indices = _lane_steps_and_indices(
                validation_steps, env_start=env_start, env_end=env_end
            )
            if cpu_indices.numel():
                validation_cpu_indices.append(cpu_indices)
    if not validation_cpu_indices:
        raise PPOTrainError("post-update validation selected no learner samples")
    validation_indices = torch.cat(validation_cpu_indices).to(device=policy_mask.device)
    validation_policy_mask = policy_mask.index_select(0, validation_indices)
    validation_value_mask = value_mask.index_select(0, validation_indices)
    validation_valid = int(validation_policy_mask.sum().item())
    validation_value_nodes = int(validation_value_mask.sum().item())
    if validation_valid <= 0 or validation_value_nodes <= 0:
        raise PPOTrainError("post-update validation selected no trainable policy/value samples")
    post_metrics_device = _weighted_metrics_accumulator(policy_mask.device)
    post_values = torch.full_like(rollout.old_values, float("nan"))
    post_value_mask = torch.zeros_like(value_mask)
    post_value_mask.index_fill_(0, validation_indices, True)
    post_value_mask &= value_mask
    post_started = time.perf_counter()
    for chunk_index, steps in chunks:
        hidden_snapshot = rollout.chunk_hidden_snapshots[chunk_index]
        for env_start, env_end in post_lane_ranges:
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
                compute_entropy=entropy_coefficient > 0.0,
            )
            lane_mask = policy_mask.index_select(0, indices)
            lane_value_mask = value_mask.index_select(0, indices)
            if _FAST_VALIDATED_GPU_PATH:
                post_policy_weight = lane_mask.float().sum() / validation_valid
                post_value_weight = lane_value_mask.float().sum() / validation_value_nodes
            else:
                lane_valid = int(lane_mask.sum().item())
                lane_value_nodes = int(lane_value_mask.sum().item())
                if lane_value_nodes <= 0:
                    continue
                post_policy_weight = lane_valid / validation_valid
                post_value_weight = lane_value_nodes / validation_value_nodes
            post_values.index_copy_(0, indices, new_values.detach())
            old_logp = rollout.old_log_probabilities.index_select(0, indices)
            lane_reference_logp = reference_log_probabilities.index_select(0, indices)
            loss = ppo_loss(
                new_log_probabilities=new_logp,
                old_log_probabilities=old_logp,
                advantages=normalized_advantages.index_select(0, indices),
                new_values=new_values,
                old_values=rollout.old_values.index_select(0, indices),
                returns=returns.index_select(0, indices),
                normalized_entropies=new_entropies,
                policy_mask=lane_mask,
                value_mask=lane_value_mask,
                clip_coefficient=clip_coefficient,
                value_clip_coefficient=value_clip_coefficient,
                value_coefficient=value_coefficient,
                entropy_coefficient=entropy_coefficient,
                normalize_advantages=False,
                validated_fast_path=_FAST_VALIDATED_GPU_PATH,
            )
            reference_kl = (
                sampled_reference_kl(
                    new_log_probabilities=new_logp,
                    old_log_probabilities=old_logp,
                    reference_log_probabilities=lane_reference_logp,
                    policy_mask=lane_mask,
                )
                if reference_kl_coefficient > 0.0
                else new_logp.new_zeros(())
            )
            _add_weighted_loss(
                post_metrics_device,
                loss,
                policy_weight=post_policy_weight,
                value_weight=post_value_weight,
                value_coefficient=value_coefficient,
                entropy_coefficient=entropy_coefficient,
                reference_kl=reference_kl,
                reference_kl_coefficient=reference_kl_coefficient,
            )
    post_metrics = _materialize_weighted_metrics(post_metrics_device)
    post_replay_seconds = time.perf_counter() - post_started
    if not torch.isfinite(post_values[post_value_mask]).all():
        raise PPOTrainError("post-update critic validation did not cover every selected value node")
    if post_metrics["approximate_kl"] > maximum_post_kl:
        raise PPOTrainError(
            f"post-update PPO KL {post_metrics['approximate_kl']} exceeds {maximum_post_kl}"
        )
    if post_metrics["clip_fraction"] > maximum_clip_fraction:
        raise PPOTrainError(
            f"post-update clip fraction {post_metrics['clip_fraction']} exceeds {maximum_clip_fraction}"
        )
    model.eval()

    return {
        "learner_samples": total_valid,
        "learner_recurrent_samples": replayed_actions,
        "critic_samples": total_value_nodes,
        "rollout_policy_samples": full_valid,
        "rollout_value_samples": full_value_nodes,
        "optimizer_lane_count": len(optimizer_lane_ranges),
        "total_lane_count": len(lane_ranges),
        "policy_sample_fraction": total_valid / full_valid,
        "value_sample_fraction": total_value_nodes / full_value_nodes,
        "learner_samples_per_second": total_valid / max(update_seconds, 1e-9),
        "learner_recurrent_samples_per_second": replayed_actions / max(update_seconds, 1e-9),
        "update_seconds": update_seconds,
        "post_replay_seconds": post_replay_seconds,
        "reference_kl_coefficient": reference_kl_coefficient,
        "bc_anchor": bc_anchor_metrics,
        "chunk_count": len(chunks),
        "chunk_boundaries": chunk_boundaries,
        "learner_lane_envs": learner_lane_envs,
        "learner_minibatches": learner_minibatches,
        "pre_update": pre_metrics,
        "post_update": post_metrics,
        "post_validation": {
            "full": bool(
                len(optimizer_lane_ranges) == len(lane_ranges)
                and (full_post_replay or len(post_lane_ranges) == len(lane_ranges))
            ),
            "lane_count": len(post_lane_ranges),
            "total_lane_count": len(lane_ranges),
            "policy_samples": validation_valid,
            "value_samples": validation_value_nodes,
            "policy_fraction": validation_valid / total_valid,
            "value_fraction": validation_value_nodes / total_value_nodes,
        },
        "probability_replay": {
            "checked_actions": replayed_actions,
            "max_log_probability_absolute_error": replay_max_logp_error,
            "max_ratio_absolute_error_from_one": replay_max_ratio_error,
            "max_value_absolute_error": replay_max_value_error,
        },
        "gradient_norm": gradient_norm,
        "clip_grad_norm_return": clip_grad_return,
        "parameter_delta_l2": parameter_delta,
        "actor_parameter_delta_l2": actor_parameter_delta,
        "critic_parameter_delta_l2": critic_parameter_delta,
        "advantage_normalization_mean": float(advantage_mean.item()),
        "advantage_normalization_std": float(advantage_std.item()),
        "old_value_explained_variance": _explained_variance(
            rollout.old_values[value_mask], returns[value_mask]
        ),
        "post_value_explained_variance": _explained_variance(
            post_values[post_value_mask], returns[post_value_mask]
        ),
        "post_value_mean": float(post_values[post_value_mask].mean().item()),
        "post_value_std": float(post_values[post_value_mask].std(unbiased=False).item()),
        "post_value_min": float(post_values[post_value_mask].min().item()),
        "post_value_max": float(post_values[post_value_mask].max().item()),
    }


def _terminal_counts(results: Tensor) -> dict[str, int]:
    return {str(code): int((results == code).sum().item()) for code in (0, 1, 2, 3)}


def run(args: argparse.Namespace) -> dict[str, Any]:
    device = torch.device(args.device)
    if device.type != "cuda" or not torch.cuda.is_available():
        raise PPOTrainError("production PPO trainer requires CUDA")
    if args.env_count <= 0 or args.env_count > 8192:
        raise PPOTrainError("env_count must stay within the qualified 1..8192 range")
    if args.decision_budget <= 0 or args.decision_budget > 50_000_000:
        raise PPOTrainError("bounded trainer decision budget must stay within 1..50M")
    if args.chunk_boundaries < 16 or args.chunk_boundaries > 128:
        raise PPOTrainError("recurrent chunk boundaries must stay within 16..128")
    if args.rollout_horizon < 16 or args.rollout_horizon > 256:
        raise PPOTrainError("rollout horizon must stay within 16..256")
    if args.learner_lane_envs <= 0 or args.learner_lane_envs > args.env_count:
        raise PPOTrainError("learner lane envs must stay within 1..env_count")
    if args.optimizer_lanes_per_update < 0:
        raise PPOTrainError("optimizer lanes per update must be nonnegative")
    if args.rollout_horizon < args.chunk_boundaries:
        raise PPOTrainError("rollout horizon must not be smaller than recurrent chunk size")
    if args.checkpoint_every_updates <= 0:
        raise PPOTrainError("checkpoint cadence must be a positive update count")
    if args.post_validation_lanes <= 0:
        raise PPOTrainError("post-validation lane count must be positive")
    if args.max_initial_signal_horizons <= 0:
        raise PPOTrainError("max initial signal horizons must be positive")
    if args.critic_calibration_terminal_trajectories < 0:
        raise PPOTrainError("critic calibration terminal-trajectory target must be nonnegative")
    if args.critic_calibration_max_horizons <= 0:
        raise PPOTrainError("critic calibration max horizons must be positive")
    if not (0.0 < args.critic_calibration_learning_rate <= 0.1):
        raise PPOTrainError("critic calibration learning rate must stay within (0, 0.1]")
    if args.minimum_terminal_actor_trajectories <= 0:
        raise PPOTrainError("minimum terminal actor trajectories must be positive")
    for value, label in (
        (args.frozen_reference_fraction, "frozen-reference fraction"),
        (args.frozen_v7_fraction, "frozen-v7 fraction"),
        (args.frozen_v5_fraction, "frozen-v5 fraction"),
    ):
        if not (0.0 <= value <= 1.0) or not math.isfinite(value):
            raise PPOTrainError(f"{label} must be finite and within [0, 1]")
    if args.frozen_reference_fraction + args.frozen_v7_fraction + args.frozen_v5_fraction > 1.0:
        raise PPOTrainError("frozen league fractions must sum to <= 1")
    if args.frozen_v7_fraction > 0 and args.v7_checkpoint is None:
        raise PPOTrainError("positive frozen-v7 fraction requires --v7-checkpoint")
    if args.frozen_v5_fraction > 0 and args.v5_checkpoint is None:
        raise PPOTrainError("positive frozen-v5 fraction requires --v5-checkpoint")
    if args.bc_anchor_coefficient < 0 or not math.isfinite(args.bc_anchor_coefficient):
        raise PPOTrainError("BC anchor coefficient must be finite and nonnegative")
    if args.bc_anchor_coefficient > 0:
        if args.bc_anchor_live_root is None or args.bc_anchor_exact_root is None:
            raise PPOTrainError("enabled BC anchor requires live and exact materialized roots")
        if args.bc_anchor_episodes_per_corpus <= 0:
            raise PPOTrainError("BC anchor episodes per corpus must be positive")
        if args.bc_anchor_batch_size <= 0 or args.bc_anchor_sequence_length <= 0:
            raise PPOTrainError("BC anchor batch size/sequence length must be positive")

    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)
    np.random.seed(args.seed & 0xFFFFFFFF)
    torch.cuda.reset_peak_memory_stats(device)

    card_table = load_card_table(args.card_table)
    model = PTCGPolicyV1(card_table, model_config(args.model_label)).to(device)
    model.checkpoint_entity_transformer = args.checkpoint_entity_transformer
    model.checkpoint_entity_transformer_first_layer_only = (
        args.checkpoint_entity_transformer_first_layer_only
    )
    load_training_checkpoint_model_state(args.bc_checkpoint, model=model)
    # Keep the frozen reference anchored to the selected BC initializer even when
    # the trainable policy is warm-started from a prior RL checkpoint under a new
    # PPO regime. Exact resumes restore the full trainable state later below.
    frozen_reference_model = copy.deepcopy(model).eval()
    for parameter in frozen_reference_model.parameters():
        parameter.requires_grad_(False)
    if args.resume_checkpoint is None and args.policy_warmstart_checkpoint is not None:
        load_training_checkpoint_model_state(args.policy_warmstart_checkpoint, model=model)
    if (
        args.resume_checkpoint is None
        and args.policy_warmstart_checkpoint is None
        and not args.preserve_initial_value_head
    ):
        _zero_untrained_bc_value_output(model)

    frozen_v7_model = PTCGPolicyV1(card_table, model_config(args.model_label)).to(device)
    if args.v7_checkpoint is not None:
        load_training_checkpoint_model_state(args.v7_checkpoint, model=frozen_v7_model)
    else:
        frozen_v7_model.load_state_dict(frozen_reference_model.state_dict(), strict=True)
    frozen_v7_model.eval()
    for parameter in frozen_v7_model.parameters():
        parameter.requires_grad_(False)

    frozen_v5_model = PTCGPolicyV1(card_table, model_config(args.model_label)).to(device)
    if args.v5_checkpoint is not None:
        load_training_checkpoint_model_state(args.v5_checkpoint, model=frozen_v5_model)
    else:
        frozen_v5_model.load_state_dict(frozen_reference_model.state_dict(), strict=True)
    frozen_v5_model.eval()
    for parameter in frozen_v5_model.parameters():
        parameter.requires_grad_(False)
    _flatten_recurrent_parameters(model)
    _flatten_recurrent_parameters(frozen_reference_model)
    _flatten_recurrent_parameters(frozen_v7_model)
    _flatten_recurrent_parameters(frozen_v5_model)

    bc_anchor_load_started = time.perf_counter()
    bc_anchor_groups: tuple[PackedMegaRecurrentGroup, ...] = ()
    bc_anchor_setup: dict[str, Any] = {
        "enabled": False,
        "coefficient": args.bc_anchor_coefficient,
        "load_seconds": 0.0,
    }
    if args.bc_anchor_coefficient > 0:
        assert args.bc_anchor_live_root is not None
        assert args.bc_anchor_exact_root is not None
        bc_anchor_groups, bc_anchor_details = _load_bc_anchor_groups(
            roots=(args.bc_anchor_live_root, args.bc_anchor_exact_root),
            episodes_per_corpus=args.bc_anchor_episodes_per_corpus,
            batch_size=args.bc_anchor_batch_size,
            sequence_length=args.bc_anchor_sequence_length,
        )
        bc_anchor_setup = {
            "enabled": True,
            "coefficient": args.bc_anchor_coefficient,
            **bc_anchor_details,
            "load_seconds": time.perf_counter() - bc_anchor_load_started,
        }

    trainable_policy = _configure_trainable_policy(
        model,
        freeze_observation_encoder=args.freeze_observation_encoder,
    )
    critic_parameter_ids = {id(parameter) for parameter in model.value_head.parameters()}
    actor_parameters = [
        parameter
        for parameter in model.parameters()
        if parameter.requires_grad and id(parameter) not in critic_parameter_ids
    ]
    critic_parameters = list(model.value_head.parameters())
    optimizer = torch.optim.AdamW(
        [
            {"params": actor_parameters, "lr": args.learning_rate},
            {"params": critic_parameters, "lr": args.critic_learning_rate},
        ],
        weight_decay=0.0,
    )
    scheduler = torch.optim.lr_scheduler.LambdaLR(
        optimizer, lr_lambda=[lambda _: 1.0, lambda _: 1.0]
    )
    total_actor_decisions = 0
    total_learner_decisions = 0
    total_meaningful_targets = 0
    completed_updates = 0
    initial_signal_wait_horizons = 0

    deck = _load_deck(args.deck)
    decks = np.broadcast_to(deck, (args.env_count, 2, 60)).copy()
    runtime_started = time.perf_counter()
    runtime = GpuCabtRuntime(args.env_count, stack_size_bytes=args.stack_bytes)
    runtime.synchronize()
    decks_device = runtime.cp.asarray(decks)
    resume_configuration = _exact_resume_configuration(args=args, runtime=runtime)
    resume_record: dict[str, Any] = {
        "exact_resume_supported": True,
        "resumed": False,
        "checkpoint": None,
        "actor_snapshot": None,
    }
    if args.resume_checkpoint is not None:
        loaded_resume = restore_training_checkpoint(
            args.resume_checkpoint,
            model=model,
            optimizer=optimizer,
            scheduler=scheduler,
            scaler=None,
            restore_rng=True,
        )
        required_counters = {
            "ppo_updates",
            "actor_decisions",
            "learner_decisions",
            "meaningful_policy_targets",
            "initial_signal_wait_horizons",
        }
        if set(loaded_resume.counters) != required_counters:
            raise PPOTrainError("resume checkpoint counters differ from the exact production set")
        counters = loaded_resume.counters
        if any(
            not isinstance(counters[name], int)
            or isinstance(counters[name], bool)
            or counters[name] < 0
            for name in required_counters
        ):
            raise PPOTrainError("resume checkpoint counters must be nonnegative integers")
        completed_updates = int(counters["ppo_updates"])
        total_actor_decisions = int(counters["actor_decisions"])
        total_learner_decisions = int(counters["learner_decisions"])
        total_meaningful_targets = int(counters["meaningful_policy_targets"])
        initial_signal_wait_horizons = int(counters["initial_signal_wait_horizons"])
        if completed_updates <= 0:
            raise PPOTrainError("exact resume requires at least one completed PPO update")
        actor_state, actor_snapshot_record = _restore_exact_actor_snapshot(
            checkpoint_path=args.resume_checkpoint,
            checkpoint_rollout_boundary=loaded_resume.rollout_boundary,
            model=model,
            runtime=runtime,
            configuration=resume_configuration,
        )
        resume_record = {
            "exact_resume_supported": True,
            "resumed": True,
            "checkpoint": args.resume_checkpoint.as_posix(),
            "restored_rng_states": list(loaded_resume.restored_rng_states),
            "actor_snapshot": actor_snapshot_record,
        }
    else:
        actor_state = _initialize_actor_state(
            model=model,
            runtime=runtime,
            decks=decks_device,
            seed=args.seed,
            frozen_reference_fraction=args.frozen_reference_fraction,
            frozen_v7_fraction=args.frozen_v7_fraction,
            frozen_v5_fraction=args.frozen_v5_fraction,
        )
    _flatten_recurrent_parameters(model)
    _flatten_recurrent_parameters(frozen_reference_model)
    _flatten_recurrent_parameters(frozen_v7_model)
    _flatten_recurrent_parameters(frozen_v5_model)
    model.eval()
    runtime_init_seconds = time.perf_counter() - runtime_started
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    critic_calibration: dict[str, Any] = {
        "enabled": False,
        "target_terminal_trajectories": args.critic_calibration_terminal_trajectories,
        "completed_terminal_trajectories": 0,
        "horizons": [],
        "actor_decisions": 0,
        "learner_decisions": 0,
        "seconds": 0.0,
    }
    if (
        args.resume_checkpoint is None
        and args.policy_warmstart_checkpoint is None
        and not args.preserve_initial_value_head
        and args.critic_calibration_terminal_trajectories > 0
    ):
        calibration_started = time.perf_counter()
        for parameter in model.parameters():
            parameter.requires_grad_(False)
        for parameter in model.value_head.parameters():
            parameter.requires_grad_(True)
        calibration_optimizer = torch.optim.AdamW(
            model.value_head.parameters(),
            lr=args.critic_calibration_learning_rate,
            weight_decay=0.0,
        )
        completed_terminal_trajectories = 0
        calibration_horizons: list[dict[str, Any]] = []
        calibration_actor_decisions = 0
        calibration_learner_decisions = 0
        for calibration_index in range(args.critic_calibration_max_horizons):
            rollout_seed = args.seed + (actor_state.horizon_index + 1) * 1_000_003
            model.train()
            calibration_rollout = _collect_fixed_horizon_rollout(
                model=model,
                frozen_reference_model=frozen_reference_model,
                frozen_v7_model=frozen_v7_model,
                frozen_v5_model=frozen_v5_model,
                actor_state=actor_state,
                runtime=runtime,
                decks=decks_device,
                seed=rollout_seed,
                frozen_reference_fraction=args.frozen_reference_fraction,
                frozen_v7_fraction=args.frozen_v7_fraction,
                frozen_v5_fraction=args.frozen_v5_fraction,
                rollout_horizon=args.rollout_horizon,
                chunk_boundaries=args.chunk_boundaries,
                bf16=args.bf16,
                learner_lane_envs=args.learner_lane_envs,
                rollout_storage=args.rollout_storage,
                heartbeat_seconds=args.heartbeat_seconds,
            )
            # The value head does not feed recurrent hidden or action logits, so the
            # trainable policy remains exactly the frozen initializer during calibration.
            actor_state.reference_hidden.copy_(actor_state.hidden)
            calibration_update = _critic_calibration_update(
                model=model,
                optimizer=calibration_optimizer,
                rollout=calibration_rollout,
                chunk_boundaries=args.chunk_boundaries,
                learner_lane_envs=args.learner_lane_envs,
                max_gradient_norm=args.max_gradient_norm,
                bf16=args.bf16,
            )
            completed_terminal_trajectories += int(
                calibration_update["terminal_trajectories"]
            )
            calibration_actor_decisions += int(
                calibration_rollout.metrics["actor_recurrent_decisions"]
            )
            calibration_learner_decisions += int(
                calibration_rollout.metrics["learner_recurrent_decisions"]
            )
            calibration_record = {
                "horizon": calibration_index + 1,
                "terminal_trajectories": calibration_update["terminal_trajectories"],
                "terminal_nodes": calibration_update["terminal_nodes"],
                "loss": calibration_update["loss"],
                "gradient_norm": calibration_update["gradient_norm"],
                "update_seconds": calibration_update.get("seconds", 0.0),
                "rollout_seconds": calibration_rollout.metrics["rollout_seconds"],
                "cumulative_terminal_trajectories": completed_terminal_trajectories,
            }
            calibration_horizons.append(calibration_record)
            print(
                json.dumps(
                    {"event": "ppo_critic_calibration", **calibration_record},
                    sort_keys=True,
                ),
                flush=True,
            )
            del calibration_rollout
            if completed_terminal_trajectories >= args.critic_calibration_terminal_trajectories:
                break
        for parameter in model.parameters():
            parameter.requires_grad_(True)
        if completed_terminal_trajectories < args.critic_calibration_terminal_trajectories:
            raise PPOTrainError(
                "critic calibration did not reach the required completed learner trajectories"
            )
        critic_calibration = {
            "enabled": True,
            "target_terminal_trajectories": args.critic_calibration_terminal_trajectories,
            "completed_terminal_trajectories": completed_terminal_trajectories,
            "horizons": calibration_horizons,
            "actor_decisions": calibration_actor_decisions,
            "learner_decisions": calibration_learner_decisions,
            "seconds": time.perf_counter() - calibration_started,
            "learning_rate": args.critic_calibration_learning_rate,
        }
        _flatten_recurrent_parameters(model)
        model.eval()

    terminal_outcome_wait_horizons = 0

    run_start_actor_decisions = total_actor_decisions
    run_start_learner_decisions = total_learner_decisions
    updates: list[dict[str, Any]] = []
    checkpoint_records: list[dict[str, Any]] = []
    run_started = time.perf_counter()

    while (
        total_learner_decisions - run_start_learner_decisions < args.decision_budget
        or completed_updates == 0
    ):
        update_number = completed_updates + 1
        rollout_seed = args.seed + (actor_state.horizon_index + 1) * 1_000_003
        # Gradient replay must use train mode for cuDNN recurrence. With dropout=0,
        # sample in the same mode under inference_mode so old-policy replay is exact.
        model.train()
        rollout = _collect_fixed_horizon_rollout(
            model=model,
            frozen_reference_model=frozen_reference_model,
            frozen_v7_model=frozen_v7_model,
            frozen_v5_model=frozen_v5_model,
            actor_state=actor_state,
            runtime=runtime,
            decks=decks_device,
            seed=rollout_seed,
            frozen_reference_fraction=args.frozen_reference_fraction,
            frozen_v7_fraction=args.frozen_v7_fraction,
            frozen_v5_fraction=args.frozen_v5_fraction,
            rollout_horizon=args.rollout_horizon,
            chunk_boundaries=args.chunk_boundaries,
            bf16=args.bf16,
            learner_lane_envs=args.learner_lane_envs,
            rollout_storage=args.rollout_storage,
            heartbeat_seconds=args.heartbeat_seconds,
        )
        gae_started = time.perf_counter()
        gae, value_mask, gae_stats = compute_fixed_horizon_gae(
            owner_ids=rollout.owner_ids,
            values=rollout.old_values,
            final_results=rollout.final_results,
            env_count=args.env_count,
            gamma=args.gamma,
            gae_lambda=args.gae_lambda,
        )
        torch.cuda.synchronize(device)
        gae_seconds = time.perf_counter() - gae_started
        terminal_targets, terminal_node_mask, terminal_actor_trajectories = (
            _terminal_outcome_targets(rollout)
        )
        if args.completed_trajectories_only:
            value_mask = value_mask & terminal_node_mask
            if terminal_actor_trajectories < args.minimum_terminal_actor_trajectories:
                # No policy/trunk parameter has changed, so the frozen initializer and
                # learner recurrent states remain identical. Keep reference recurrence
                # aligned without paying for a redundant full frozen-model replay.
                actor_state.reference_hidden.copy_(actor_state.hidden)
                terminal_outcome_wait_horizons += 1
                print(
                    json.dumps(
                        {
                            "event": "ppo_terminal_outcome_wait",
                            "horizon": actor_state.horizon_index,
                            "terminal_actor_trajectories": terminal_actor_trajectories,
                            "minimum_terminal_actor_trajectories": args.minimum_terminal_actor_trajectories,
                            "wait_horizons": terminal_outcome_wait_horizons,
                            "reason": "completed-game-only PPO requires a sufficiently large exact-outcome batch",
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
                del rollout, gae, value_mask, terminal_targets, terminal_node_mask
                continue
            if not torch.any(value_mask):
                raise PPOTrainError("completed-game-only PPO selected no trainable recurrent nodes")
            maximum_return_error = float(
                torch.abs(gae.returns[value_mask] - terminal_targets[value_mask]).max().item()
            )
            if maximum_return_error > 1e-5:
                raise PPOTrainError(
                    "completed-game Monte Carlo returns differ from exact terminal outcomes: "
                    f"{maximum_return_error}"
                )
        if args.reference_kl_coefficient > 0.0:
            reference_logp, reference_hidden, reference_replay_seconds = (
                _replay_reference_log_probabilities(
                    model=frozen_reference_model,
                    rollout=rollout,
                    bf16=args.bf16,
                )
            )
            actor_state.reference_hidden.copy_(reference_hidden)
        else:
            reference_logp = rollout.old_log_probabilities.detach()
            reference_replay_seconds = 0.0
            actor_state.reference_hidden.copy_(actor_state.hidden)
        if (
            completed_updates == 0
            and args.resume_checkpoint is None
            and not args.preserve_initial_value_head
            and args.critic_calibration_terminal_trajectories == 0
            and gae_stats.terminal_trajectories == 0
        ):
            actor_decisions = int(rollout.metrics["actor_recurrent_decisions"])
            learner_decisions = int(rollout.metrics["learner_recurrent_decisions"])
            meaningful_targets = int(rollout.metrics["meaningful_policy_targets"])
            total_actor_decisions += actor_decisions
            total_learner_decisions += learner_decisions
            total_meaningful_targets += meaningful_targets
            initial_signal_wait_horizons += 1
            print(
                json.dumps(
                    {
                        "event": "ppo_initial_terminal_signal_wait",
                        "horizon": actor_state.horizon_index,
                        "wait_horizons": initial_signal_wait_horizons,
                        "actor_decisions": total_actor_decisions,
                        "learner_decisions": total_learner_decisions,
                        "reason": "zero-output BC critic and no terminal trajectory; actor remains frozen",
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            if initial_signal_wait_horizons >= args.max_initial_signal_horizons:
                raise PPOTrainError(
                    "no terminal learner trajectory observed during initial critic signal wait"
                )
            del rollout, gae, value_mask, reference_logp
            torch.cuda.empty_cache()
            continue
        bc_anchor_group = (
            bc_anchor_groups[(update_number - 1) % len(bc_anchor_groups)]
            if bc_anchor_groups
            else None
        )
        print(
            json.dumps(
                {
                    "event": "ppo_learner_start",
                    "update": update_number,
                    "horizon": actor_state.horizon_index,
                    "actor_decisions": int(rollout.metrics["actor_recurrent_decisions"]),
                    "learner_decisions": int(rollout.metrics["learner_recurrent_decisions"]),
                    "meaningful_policy_targets": int(rollout.metrics["meaningful_policy_targets"]),
                    "rollout_seconds": float(rollout.metrics["rollout_seconds"]),
                    "actor_dps": float(rollout.metrics["actor_decisions_per_second"]),
                    "reference_replay_seconds": reference_replay_seconds,
                    "learner_lane_envs": args.learner_lane_envs,
                    "cuda_allocated_bytes": int(torch.cuda.memory_allocated(device)),
                    "cuda_reserved_bytes": int(torch.cuda.memory_reserved(device)),
                },
                sort_keys=True,
            ),
            flush=True,
        )
        projected_run_learner_decisions = (
            total_learner_decisions
            - run_start_learner_decisions
            + int(rollout.metrics["learner_recurrent_decisions"])
        )
        full_post_replay = (
            update_number % args.checkpoint_every_updates == 0
            or projected_run_learner_decisions >= args.decision_budget
        )
        lane_count = math.ceil(args.env_count / args.learner_lane_envs)
        update = _ppo_update(
            model=model,
            optimizer=optimizer,
            scheduler=scheduler,
            rollout=rollout,
            advantages=gae.advantages,
            returns=gae.returns,
            value_mask=value_mask,
            reference_log_probabilities=reference_logp,
            chunk_boundaries=args.chunk_boundaries,
            learner_lane_envs=args.learner_lane_envs,
            clip_coefficient=args.clip_coefficient,
            optimizer_lanes_per_update=args.optimizer_lanes_per_update,
            optimizer_lane_offset=update_number - 1,
            value_clip_coefficient=args.value_clip_coefficient,
            value_coefficient=args.value_coefficient,
            entropy_coefficient=args.entropy_coefficient,
            reference_kl_coefficient=args.reference_kl_coefficient,
            bc_anchor_group=bc_anchor_group,
            bc_anchor_coefficient=args.bc_anchor_coefficient,
            max_gradient_norm=args.max_gradient_norm,
            replay_tolerance=args.replay_tolerance,
            maximum_post_kl=args.maximum_post_kl,
            maximum_clip_fraction=args.maximum_clip_fraction,
            full_post_replay=full_post_replay,
            post_validation_lanes=args.post_validation_lanes,
            post_validation_lane_offset=(update_number - 1) % lane_count,
            bf16=args.bf16,
        )
        actor_decisions = int(rollout.metrics["actor_recurrent_decisions"])
        update["reference_replay_seconds"] = reference_replay_seconds
        learner_decisions = int(rollout.metrics["learner_recurrent_decisions"])
        meaningful_targets = int(rollout.metrics["meaningful_policy_targets"])
        total_actor_decisions += actor_decisions
        total_learner_decisions += learner_decisions
        total_meaningful_targets += meaningful_targets
        completed_updates = update_number

        advantage = gae.advantages[value_mask]
        returns = gae.returns[value_mask]
        train_policy_mask = rollout.policy_mask & value_mask
        rollout_record = {
            **rollout.metrics,
            "terminal_counts": _terminal_counts(rollout.final_results),
            "runtime_memory_bytes": runtime.memory_bytes(),
            "old_value_mean": float(rollout.old_values[value_mask].mean().item()),
            "old_value_std": float(rollout.old_values[value_mask].std(unbiased=False).item()),
            "old_value_min": float(rollout.old_values[value_mask].min().item()),
            "old_value_max": float(rollout.old_values[value_mask].max().item()),
            "old_entropy_mean": float(rollout.old_entropies[train_policy_mask].mean().item()),
            "trainable_recurrent_nodes": int(value_mask.sum().item()),
            "trainable_policy_targets": int(train_policy_mask.sum().item()),
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

        run_complete = (
            total_learner_decisions - run_start_learner_decisions >= args.decision_budget
        )
        checkpoint_due = (
            update_number % args.checkpoint_every_updates == 0 or run_complete
        )
        checkpoint_seconds = 0.0
        if checkpoint_due:
            checkpoint_started = time.perf_counter()
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
                    "initial_signal_wait_horizons": initial_signal_wait_horizons,
                },
                league={
                    "mode": "current-selfplay-plus-frozen-reference-v7-v5",
                    "frozen_reference_fraction_requested": args.frozen_reference_fraction,
                    "frozen_v7_fraction_requested": args.frozen_v7_fraction,
                    "frozen_v5_fraction_requested": args.frozen_v5_fraction,
                    "reference_policy": {"id": "frozen-initializer-reference"},
                    "historical_opponents": [
                        {"id": "frozen-initializer-opponent"},
                        {"id": "bc-v7-frozen-opponent"},
                        {"id": "bc-v5-frozen-opponent"},
                    ],
                },
                rollout_boundary={
                    "horizon_index": actor_state.horizon_index,
                    "terminal_counts": rollout_record["terminal_counts"],
                    "rollout_seed": rollout_seed,
                    "rollout_horizon": args.rollout_horizon,
                    "chunk_boundaries": args.chunk_boundaries,
                    "actor_state_persisted": True,
                    "actor_state_sidecar": _actor_snapshot_path(checkpoint_path).name,
                    "exact_resume_supported": True,
                },
                include_cuda_rng=True,
            )
            actor_snapshot = _save_exact_actor_snapshot(
                checkpoint_path=checkpoint_path,
                actor_state=actor_state,
                runtime=runtime,
                configuration=resume_configuration,
            )
            checkpoint_seconds = time.perf_counter() - checkpoint_started
            checkpoint_record = {
                "update": update_number,
                "path": checkpoint_path.as_posix(),
                "payload_bytes": checkpoint["payload_bytes"],
                "actor_state_path": actor_snapshot["path"],
                "actor_state_payload_bytes": actor_snapshot["payload_bytes"],
                "write_seconds": checkpoint_seconds,
                "model_only_continuation_safe": True,
                "exact_resume_safe": True,
            }
            checkpoint_records.append(checkpoint_record)
            update_record["checkpoint"] = checkpoint_record
        update_record["checkpoint_seconds"] = checkpoint_seconds

        progress = {
            "event": "ppo_update_complete",
            "update": update_number,
            "actor_decisions": total_actor_decisions,
            "run_actor_decisions": total_actor_decisions - run_start_actor_decisions,
            "run_learner_decisions": total_learner_decisions - run_start_learner_decisions,
            "actor_dps": rollout_record["actor_decisions_per_second"],
            "learner_samples_per_second": update["learner_samples_per_second"],
            "rollout_seconds": rollout_record["rollout_seconds"],
            "update_seconds": update["update_seconds"],
            "post_kl": update["post_update"]["approximate_kl"],
            "post_clip_fraction": update["post_update"]["clip_fraction"],
            "bc_anchor_nll": (
                update["bc_anchor"].get("mean_nll")
                if update["bc_anchor"].get("enabled")
                else None
            ),
            "checkpoint_seconds": checkpoint_seconds,
        }
        print(json.dumps(progress, sort_keys=True), flush=True)
        del rollout, gae, advantage, returns, value_mask, train_policy_mask, reference_logp

    run_seconds = time.perf_counter() - run_started
    run_actor_decisions = total_actor_decisions - run_start_actor_decisions
    run_learner_decisions = total_learner_decisions - run_start_learner_decisions
    total_rollout_seconds = sum(float(item["rollout"]["rollout_seconds"]) for item in updates)
    total_update_seconds = sum(float(item["learner"]["update_seconds"]) for item in updates)
    total_post_replay_seconds = sum(float(item["learner"]["post_replay_seconds"]) for item in updates)
    total_reference_replay_seconds = sum(
        float(item["learner"]["reference_replay_seconds"]) for item in updates
    )
    total_gae_seconds = sum(float(item["gae"]["seconds"]) for item in updates)
    total_checkpoint_seconds = sum(float(item["checkpoint_seconds"]) for item in updates)
    measured_work_seconds = (
        total_rollout_seconds
        + total_reference_replay_seconds
        + total_update_seconds
        + total_post_replay_seconds
        + total_gae_seconds
        + total_checkpoint_seconds
    )

    report: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "kptcg-production-shaped-ppo-bounded-v1",
        "status": "PASS",
        "source_commit": args.source_commit,
        "device": str(device),
        "gpu_name": torch.cuda.get_device_name(device),
        "bf16": bool(args.bf16),
        "model_label": args.model_label,
        "initializer_interpretation": (
            "exact full-state resume from PPO checkpoint"
            if args.resume_checkpoint is not None
            else (
                "model-only warm start from prior PPO checkpoint with fresh optimizer/actor state"
                if args.policy_warmstart_checkpoint is not None
                else "model-only warm start from selected BC checkpoint"
            )
        ),
        "policy_checkpoints": {
            "initializer_and_reference": args.bc_checkpoint.as_posix(),
            "trainable_policy_warmstart": (
                args.policy_warmstart_checkpoint.as_posix()
                if args.policy_warmstart_checkpoint is not None
                else None
            ),
            "frozen_v7_opponent": (
                args.v7_checkpoint.as_posix() if args.v7_checkpoint is not None else None
            ),
            "frozen_v5_opponent": (
                args.v5_checkpoint.as_posix() if args.v5_checkpoint is not None else None
            ),
        },
        "model_parameters": model.trainable_parameter_count,
        "optimizer_parameter_partition": trainable_policy,
        "deck": {"path": args.deck.as_posix()},
        "configuration": {
            "env_count": args.env_count,
            "learner_decision_budget_requested": args.decision_budget,
            "rollout_horizon": args.rollout_horizon,
            "recurrent_chunk_boundaries": args.chunk_boundaries,
            "learner_lane_envs": args.learner_lane_envs,
            "heartbeat_seconds": args.heartbeat_seconds,
            "optimizer_lanes_per_update": args.optimizer_lanes_per_update,
            "freeze_observation_encoder": args.freeze_observation_encoder,
            "checkpoint_entity_transformer": args.checkpoint_entity_transformer,
            "checkpoint_entity_transformer_first_layer_only": args.checkpoint_entity_transformer_first_layer_only,
            "rollout_storage": args.rollout_storage,
            "checkpoint_every_updates": args.checkpoint_every_updates,
            "frozen_reference_fraction": args.frozen_reference_fraction,
            "frozen_v7_fraction": args.frozen_v7_fraction,
            "frozen_v5_fraction": args.frozen_v5_fraction,
            "gamma": args.gamma,
            "gae_lambda": args.gae_lambda,
            "clip_coefficient": args.clip_coefficient,
            "value_clip_coefficient": args.value_clip_coefficient,
            "value_coefficient": args.value_coefficient,
            "entropy_coefficient": args.entropy_coefficient,
            "reference_kl_coefficient": args.reference_kl_coefficient,
            "bc_anchor_coefficient": args.bc_anchor_coefficient,
            "bc_anchor_episodes_per_corpus": args.bc_anchor_episodes_per_corpus,
            "bc_anchor_batch_size": args.bc_anchor_batch_size,
            "bc_anchor_sequence_length": args.bc_anchor_sequence_length,
            "replay_tolerance": args.replay_tolerance,
            "post_validation_lanes": args.post_validation_lanes,
            "critic_calibration_terminal_trajectories": args.critic_calibration_terminal_trajectories,
            "critic_calibration_max_horizons": args.critic_calibration_max_horizons,
            "critic_calibration_learning_rate": args.critic_calibration_learning_rate,
            "completed_trajectories_only": args.completed_trajectories_only,
            "minimum_terminal_actor_trajectories": args.minimum_terminal_actor_trajectories,
            "terminal_outcome_wait_horizons": terminal_outcome_wait_horizons,
            "maximum_post_kl": args.maximum_post_kl,
            "maximum_clip_fraction": args.maximum_clip_fraction,
            "learning_rate": args.learning_rate,
            "critic_learning_rate": args.critic_learning_rate,
            "critic_gradient_into_actor_trunk": False,
            "max_gradient_norm": args.max_gradient_norm,
            "ppo_epochs_per_rollout": 1,
            "critic_initialization": (
                "restored_from_rl_checkpoint"
                if args.resume_checkpoint is not None
                else (
                    "restored_from_policy_warmstart"
                    if args.policy_warmstart_checkpoint is not None
                    else (
                        "preserved_from_initializer"
                        if args.preserve_initial_value_head
                        else "zero_output_layer_from_untrained_bc_head"
                    )
                )
            ),
            "max_initial_signal_horizons": args.max_initial_signal_horizons,
            "initial_signal_wait_horizons": initial_signal_wait_horizons,
            "reward": "terminal-only +1/-1, draw 0",
            "rollout_policy": "fixed-horizon recurrent actor with GPU selective terminal recycling",
            "recurrent_replay": "chunk-start hidden snapshot plus in-chunk recurrent unroll",
        },
        "bc_anchor_setup": bc_anchor_setup,
        "critic_calibration": critic_calibration,
        "resume": resume_record,
        "runtime_init_seconds": runtime_init_seconds,
        "run": {
            "updates": len(updates),
            "actor_decisions": run_actor_decisions,
            "learner_decisions": run_learner_decisions,
            "learner_decisions_requested": args.decision_budget,
            "wall_seconds": run_seconds,
            "end_to_end_actor_decisions_per_second": run_actor_decisions / max(run_seconds, 1e-9),
            "end_to_end_learner_decisions_per_second": run_learner_decisions / max(run_seconds, 1e-9),
            "rollout_seconds": total_rollout_seconds,
            "update_seconds": total_update_seconds,
            "post_update_replay_seconds": total_post_replay_seconds,
            "reference_replay_seconds": total_reference_replay_seconds,
            "gae_seconds": total_gae_seconds,
            "checkpoint_seconds": total_checkpoint_seconds,
            "actor_duty_cycle": total_rollout_seconds / max(measured_work_seconds, 1e-9),
            "reference_replay_duty_cycle": total_reference_replay_seconds / max(measured_work_seconds, 1e-9),
            "learner_duty_cycle": total_update_seconds / max(measured_work_seconds, 1e-9),
            "post_replay_duty_cycle": total_post_replay_seconds / max(measured_work_seconds, 1e-9),
            "gae_duty_cycle": total_gae_seconds / max(measured_work_seconds, 1e-9),
            "checkpoint_duty_cycle": total_checkpoint_seconds / max(measured_work_seconds, 1e-9),
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
    parser.add_argument("--card-table", type=Path, required=True)
    parser.add_argument("--model-label", default="3.7m", choices=tuple(model_configs()))
    parser.add_argument("--bc-checkpoint", type=Path, required=True)
    parser.add_argument("--resume-checkpoint", type=Path)
    parser.add_argument("--policy-warmstart-checkpoint", type=Path)
    parser.add_argument("--v7-checkpoint", type=Path)
    parser.add_argument("--v5-checkpoint", type=Path)
    parser.add_argument("--deck", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--env-count", type=int, default=8192)
    parser.add_argument("--decision-budget", type=int, required=True)
    parser.add_argument("--rollout-horizon", type=int, default=64)
    parser.add_argument("--chunk-boundaries", type=int, default=64)
    parser.add_argument("--learner-lane-envs", type=int, default=1024)
    parser.add_argument("--optimizer-lanes-per-update", type=int, default=0)
    parser.add_argument("--freeze-observation-encoder", action="store_true")
    parser.add_argument("--checkpoint-entity-transformer", action="store_true")
    parser.add_argument(
        "--checkpoint-entity-transformer-first-layer-only", action="store_true"
    )
    parser.add_argument(
        "--rollout-storage",
        choices=("cpu-compact", "cuda-compact"),
        default="cpu-compact",
    )
    parser.add_argument("--heartbeat-seconds", type=float, default=10.0)
    parser.add_argument("--checkpoint-every-updates", type=int, default=10)
    parser.add_argument("--frozen-reference-fraction", type=float, default=0.30)
    parser.add_argument("--frozen-v7-fraction", type=float, default=0.15)
    parser.add_argument("--frozen-v5-fraction", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=20260815)
    parser.add_argument("--stack-bytes", type=int, default=16 * 1024)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--bf16", action="store_true")
    parser.add_argument("--gamma", type=float, default=1.0)
    parser.add_argument("--gae-lambda", type=float, default=0.95)
    parser.add_argument("--clip-coefficient", type=float, default=0.2)
    parser.add_argument("--value-clip-coefficient", type=float, default=0.2)
    parser.add_argument("--value-coefficient", type=float, default=0.5)
    parser.add_argument("--entropy-coefficient", type=float, default=0.01)
    parser.add_argument("--reference-kl-coefficient", type=float, default=0.0)
    parser.add_argument("--bc-anchor-coefficient", type=float, default=0.0)
    parser.add_argument("--bc-anchor-live-root", type=Path)
    parser.add_argument("--bc-anchor-exact-root", type=Path)
    parser.add_argument("--bc-anchor-episodes-per-corpus", type=int, default=8)
    parser.add_argument("--bc-anchor-batch-size", type=int, default=8)
    parser.add_argument("--bc-anchor-sequence-length", type=int, default=32)
    parser.add_argument("--replay-tolerance", type=float, default=1e-5)
    parser.add_argument("--post-validation-lanes", type=int, default=1)
    parser.add_argument("--critic-calibration-terminal-trajectories", type=int, default=2048)
    parser.add_argument("--critic-calibration-max-horizons", type=int, default=8)
    parser.add_argument("--critic-calibration-learning-rate", type=float, default=3e-4)
    parser.add_argument("--completed-trajectories-only", action="store_true")
    parser.add_argument("--minimum-terminal-actor-trajectories", type=int, default=512)
    parser.add_argument("--maximum-post-kl", type=float, default=0.03)
    parser.add_argument("--maximum-clip-fraction", type=float, default=0.30)
    parser.add_argument("--learning-rate", type=float, default=1e-8)
    parser.add_argument("--critic-learning-rate", type=float, default=3e-4)
    parser.add_argument("--max-gradient-norm", type=float, default=1.0)
    parser.add_argument("--preserve-initial-value-head", action="store_true")
    parser.add_argument("--max-initial-signal-horizons", type=int, default=16)
    args = parser.parse_args()
    result = run(args)
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
