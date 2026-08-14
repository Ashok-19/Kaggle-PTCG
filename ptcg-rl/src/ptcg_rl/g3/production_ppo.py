from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import Tensor

from ptcg_rl.g2.network import TorchDecisionBatch
from ptcg_rl.g3.ppo import GAEResultV1, PPOContractError


@dataclass(frozen=True)
class CompleteGameGAEStatsV1:
    trajectory_count: int
    trajectory_length_min: int
    trajectory_length_max: int
    trajectory_length_mean: float
    terminal_wins: int
    terminal_losses: int
    terminal_draws: int


def slice_torch_decision_batch_rows(
    batch: TorchDecisionBatch,
    start: int,
    end: int,
) -> TorchDecisionBatch:
    """Slice a contiguous decision-row range and remap all ragged entity links."""
    if not isinstance(start, int) or not isinstance(end, int):
        raise PPOContractError("decision batch slice bounds must be integers")
    if start < 0 or end <= start or end > batch.batch_size:
        raise PPOContractError("decision batch slice must be a nonempty in-range interval")

    def scalar(value: Tensor) -> int:
        return int(value.item())

    entity_start = scalar(batch.entity_offsets[start])
    entity_end = scalar(batch.entity_offsets[end])
    event_start = scalar(batch.event_offsets[start])
    event_end = scalar(batch.event_offsets[end])
    option_start = scalar(batch.option_offsets[start])
    option_end = scalar(batch.option_offsets[end])
    energy_start = scalar(batch.entity_energy_offsets[entity_start])
    energy_end = scalar(batch.entity_energy_offsets[entity_end])

    def remap(values: Tensor) -> Tensor:
        return torch.where(values >= 0, values - entity_start, values)

    return TorchDecisionBatch(
        batch_size=end - start,
        player_categorical=batch.player_categorical[start:end],
        player_categorical_missing=batch.player_categorical_missing[start:end],
        player_numeric=batch.player_numeric[start:end],
        player_numeric_missing=batch.player_numeric_missing[start:end],
        entity_categorical=batch.entity_categorical[entity_start:entity_end],
        entity_categorical_missing=batch.entity_categorical_missing[entity_start:entity_end],
        entity_numeric=batch.entity_numeric[entity_start:entity_end],
        entity_numeric_missing=batch.entity_numeric_missing[entity_start:entity_end],
        entity_parent_indices=remap(batch.entity_parent_indices[entity_start:entity_end]),
        entity_energy_values=batch.entity_energy_values[energy_start:energy_end],
        entity_energy_offsets=(
            batch.entity_energy_offsets[entity_start : entity_end + 1] - energy_start
        ),
        entity_offsets=batch.entity_offsets[start : end + 1] - entity_start,
        event_categorical=batch.event_categorical[event_start:event_end],
        event_categorical_missing=batch.event_categorical_missing[event_start:event_end],
        event_numeric=batch.event_numeric[event_start:event_end],
        event_numeric_missing=batch.event_numeric_missing[event_start:event_end],
        event_identity=batch.event_identity[event_start:event_end],
        event_identity_missing=batch.event_identity_missing[event_start:event_end],
        event_entity_indices=remap(batch.event_entity_indices[event_start:event_end]),
        event_offsets=batch.event_offsets[start : end + 1] - event_start,
        option_categorical=batch.option_categorical[option_start:option_end],
        option_categorical_missing=batch.option_categorical_missing[option_start:option_end],
        option_numeric=batch.option_numeric[option_start:option_end],
        option_numeric_missing=batch.option_numeric_missing[option_start:option_end],
        option_source_entity_indices=remap(
            batch.option_source_entity_indices[option_start:option_end]
        ),
        option_target_entity_indices=remap(
            batch.option_target_entity_indices[option_start:option_end]
        ),
        option_available=batch.option_available[option_start:option_end],
        option_offsets=batch.option_offsets[start : end + 1] - option_start,
        global_categorical=batch.global_categorical[start:end],
        global_categorical_missing=batch.global_categorical_missing[start:end],
        global_numeric=batch.global_numeric[start:end],
        global_numeric_missing=batch.global_numeric_missing[start:end],
    )


def meaningful_compound_policy_mask(
    batch: TorchDecisionBatch,
    *,
    minimum_counts: Tensor,
    maximum_counts: Tensor,
) -> Tensor:
    """Return rows whose ordered compound selection has more than one legal outcome."""
    if minimum_counts.shape != (batch.batch_size,) or maximum_counts.shape != (batch.batch_size,):
        raise PPOContractError("selection bounds differ from decision batch size")
    lengths = batch.option_offsets[1:] - batch.option_offsets[:-1]
    owner = torch.repeat_interleave(
        torch.arange(batch.batch_size, dtype=torch.long, device=lengths.device),
        lengths,
    )
    available_counts = torch.zeros(
        batch.batch_size, dtype=torch.long, device=lengths.device
    )
    if owner.numel():
        available_counts.scatter_add_(0, owner, batch.option_available.to(torch.long))
    minimum = minimum_counts.to(device=lengths.device, dtype=torch.long)
    maximum = maximum_counts.to(device=lengths.device, dtype=torch.long)
    effective_maximum = torch.minimum(maximum, available_counts)
    if torch.any(minimum < 0) or torch.any(maximum < minimum):
        raise PPOContractError("selection bounds are invalid")
    if torch.any(minimum > effective_maximum):
        raise PPOContractError("selection minimum exceeds available option count")
    # There is exactly one ordered compound outcome only for an explicit empty
    # selection or one mandatory available option. With two mandatory options,
    # order alone creates two distinct PPO outcomes.
    forced = (effective_maximum == 0) | (
        (available_counts == 1) & (minimum == 1)
    )
    return ~forced


def compute_complete_game_gae(
    *,
    owner_ids: Tensor,
    values: Tensor,
    final_results: Tensor,
    env_count: int,
    gamma: float = 0.999,
    gae_lambda: float = 0.95,
) -> tuple[GAEResultV1, CompleteGameGAEStatsV1]:
    """Compute terminal-only GAE for interleaved complete-game player trajectories.

    ``owner_ids`` identifies ``env * 2 + player`` for each recurrent policy
    decision in chronological collection order. The implementation groups those
    interleaved decisions on device, pads only for the GAE calculation, and runs
    the reverse recurrence vectorized across player trajectories.
    """
    if not isinstance(env_count, int) or isinstance(env_count, bool) or env_count <= 0:
        raise PPOContractError("env_count must be a positive integer")
    if owner_ids.ndim != 1 or owner_ids.dtype != torch.long:
        raise PPOContractError("GAE owner ids must be a one-dimensional long tensor")
    if values.ndim != 1 or values.shape != owner_ids.shape or values.numel() == 0:
        raise PPOContractError("GAE values must be a nonempty vector matching owner ids")
    if final_results.ndim != 1 or final_results.numel() != env_count:
        raise PPOContractError("final results must contain one result per environment")
    if not torch.isfinite(values).all():
        raise PPOContractError("GAE values contain NaN or infinity")
    if not (0.0 <= gamma <= 1.0) or not (0.0 <= gae_lambda <= 1.0):
        raise PPOContractError("GAE gamma and lambda must be within [0, 1]")
    owner_count = env_count * 2
    if torch.any((owner_ids < 0) | (owner_ids >= owner_count)):
        raise PPOContractError("GAE owner id is outside the environment/player range")
    results = final_results.to(device=values.device, dtype=torch.long)
    if torch.any((results < 1) | (results > 3)):
        raise PPOContractError("complete-game GAE requires terminal result 1, 2, or 3")

    lengths = torch.bincount(owner_ids, minlength=owner_count)
    populated = lengths > 0
    if not torch.any(populated):
        raise PPOContractError("complete-game GAE contains no player trajectories")

    order = torch.argsort(owner_ids, stable=True)
    sorted_owners = owner_ids.index_select(0, order)
    sorted_values = values.index_select(0, order)
    starts = torch.cumsum(lengths, dim=0) - lengths
    repeated_starts = torch.repeat_interleave(starts, lengths)
    positions = torch.arange(values.numel(), device=values.device, dtype=torch.long) - repeated_starts
    maximum_length = int(lengths.max().item())

    padded_values = values.new_zeros((owner_count, maximum_length))
    padded_values[sorted_owners, positions] = sorted_values
    padded_advantages = torch.zeros_like(padded_values)

    owner_index = torch.arange(owner_count, device=values.device, dtype=torch.long)
    owner_env = torch.div(owner_index, 2, rounding_mode="floor")
    owner_player = owner_index.remainder(2)
    owner_result = results.index_select(0, owner_env)
    terminal_rewards = torch.where(
        owner_result == 3,
        torch.zeros(owner_count, device=values.device, dtype=values.dtype),
        torch.where(
            owner_result == owner_player + 1,
            torch.ones(owner_count, device=values.device, dtype=values.dtype),
            -torch.ones(owner_count, device=values.device, dtype=values.dtype),
        ),
    )

    next_advantage = values.new_zeros((owner_count,))
    for position in range(maximum_length - 1, -1, -1):
        active = lengths > position
        has_next = lengths > position + 1
        reward = torch.where(
            active & ~has_next,
            terminal_rewards,
            torch.zeros_like(terminal_rewards),
        )
        next_value = torch.where(
            has_next,
            padded_values[:, min(position + 1, maximum_length - 1)],
            torch.zeros_like(terminal_rewards),
        )
        delta = reward + gamma * next_value - padded_values[:, position]
        current = delta + gamma * gae_lambda * torch.where(
            has_next, next_advantage, torch.zeros_like(next_advantage)
        )
        current = torch.where(active, current, torch.zeros_like(current))
        padded_advantages[:, position] = current
        next_advantage = current

    sorted_advantages = padded_advantages[sorted_owners, positions]
    advantages = torch.empty_like(values)
    advantages.index_copy_(0, order, sorted_advantages)
    returns = advantages + values
    if not torch.isfinite(advantages).all() or not torch.isfinite(returns).all():
        raise PPOContractError("complete-game GAE produced a nonfinite result")

    populated_lengths = lengths[populated]
    populated_rewards = terminal_rewards[populated]
    stats = CompleteGameGAEStatsV1(
        trajectory_count=int(populated.sum().item()),
        trajectory_length_min=int(populated_lengths.min().item()),
        trajectory_length_max=int(populated_lengths.max().item()),
        trajectory_length_mean=float(populated_lengths.float().mean().item()),
        terminal_wins=int((populated_rewards > 0).sum().item()),
        terminal_losses=int((populated_rewards < 0).sum().item()),
        terminal_draws=int((populated_rewards == 0).sum().item()),
    )
    return GAEResultV1(advantages=advantages, returns=returns), stats
