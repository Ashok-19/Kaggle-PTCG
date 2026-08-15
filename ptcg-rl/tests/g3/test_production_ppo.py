from __future__ import annotations

import torch

from ptcg_rl.g2.network import TorchDecisionBatch
from ptcg_rl.g3.ppo import compute_gae
from ptcg_rl.g3.production_ppo import (
    compute_complete_game_gae,
    compute_fixed_horizon_gae,
    meaningful_compound_policy_mask,
    slice_torch_decision_batch_rows,
)


def _minimal_batch() -> TorchDecisionBatch:
    empty_long = torch.empty((0, 1), dtype=torch.long)
    empty_bool = torch.empty((0, 1), dtype=torch.bool)
    empty_float = torch.empty((0, 1), dtype=torch.float32)
    return TorchDecisionBatch(
        batch_size=4,
        player_categorical=torch.zeros((4, 2, 2), dtype=torch.long),
        player_categorical_missing=torch.zeros((4, 2, 2), dtype=torch.bool),
        player_numeric=torch.zeros((4, 2, 6)),
        player_numeric_missing=torch.zeros((4, 2, 6), dtype=torch.bool),
        entity_categorical=empty_long,
        entity_categorical_missing=empty_bool,
        entity_numeric=empty_float,
        entity_numeric_missing=empty_bool,
        entity_parent_indices=torch.empty(0, dtype=torch.long),
        entity_energy_values=torch.empty(0, dtype=torch.long),
        entity_energy_offsets=torch.zeros(1, dtype=torch.long),
        entity_offsets=torch.zeros(5, dtype=torch.long),
        event_categorical=empty_long,
        event_categorical_missing=empty_bool,
        event_numeric=empty_float,
        event_numeric_missing=empty_bool,
        event_identity=empty_long,
        event_identity_missing=empty_bool,
        event_entity_indices=empty_long,
        event_offsets=torch.zeros(5, dtype=torch.long),
        option_categorical=torch.zeros((6, 12), dtype=torch.long),
        option_categorical_missing=torch.zeros((6, 12), dtype=torch.bool),
        option_numeric=torch.zeros((6, 2)),
        option_numeric_missing=torch.zeros((6, 2), dtype=torch.bool),
        option_source_entity_indices=torch.full((6,), -1, dtype=torch.long),
        option_target_entity_indices=torch.full((6,), -1, dtype=torch.long),
        option_available=torch.tensor([True, True, True, True, True, False]),
        option_offsets=torch.tensor([0, 0, 1, 3, 6], dtype=torch.long),
        global_categorical=torch.zeros((4, 7), dtype=torch.long),
        global_categorical_missing=torch.zeros((4, 7), dtype=torch.bool),
        global_numeric=torch.zeros((4, 12)),
        global_numeric_missing=torch.zeros((4, 12), dtype=torch.bool),
    )


def test_meaningful_compound_policy_mask_distinguishes_ordered_forced_cases() -> None:
    batch = _minimal_batch()
    mask = meaningful_compound_policy_mask(
        batch,
        minimum_counts=torch.tensor([0, 1, 2, 1]),
        maximum_counts=torch.tensor([0, 1, 2, 3]),
    )
    # empty/0..0 and one mandatory option are forced. Two mandatory options have
    # two possible orders, while the final row has multiple available options.
    assert mask.tolist() == [False, False, True, True]


def test_slice_torch_decision_batch_rows_remaps_nested_ragged_links() -> None:
    batch = TorchDecisionBatch(
        batch_size=3,
        player_categorical=torch.arange(12).reshape(3, 2, 2),
        player_categorical_missing=torch.zeros((3, 2, 2), dtype=torch.bool),
        player_numeric=torch.arange(36, dtype=torch.float32).reshape(3, 2, 6),
        player_numeric_missing=torch.zeros((3, 2, 6), dtype=torch.bool),
        entity_categorical=torch.arange(5).reshape(5, 1),
        entity_categorical_missing=torch.zeros((5, 1), dtype=torch.bool),
        entity_numeric=torch.arange(5, dtype=torch.float32).reshape(5, 1),
        entity_numeric_missing=torch.zeros((5, 1), dtype=torch.bool),
        entity_parent_indices=torch.tensor([-1, 0, -1, -1, 3]),
        entity_energy_values=torch.tensor([5, 7, 8, 9]),
        entity_energy_offsets=torch.tensor([0, 1, 1, 2, 2, 4]),
        entity_offsets=torch.tensor([0, 2, 3, 5]),
        event_categorical=torch.tensor([[10], [20]]),
        event_categorical_missing=torch.zeros((2, 1), dtype=torch.bool),
        event_numeric=torch.tensor([[1.0], [2.0]]),
        event_numeric_missing=torch.zeros((2, 1), dtype=torch.bool),
        event_identity=torch.tensor([[1], [2]]),
        event_identity_missing=torch.zeros((2, 1), dtype=torch.bool),
        event_entity_indices=torch.tensor([[1, -1], [4, 3]]),
        event_offsets=torch.tensor([0, 1, 1, 2]),
        option_categorical=torch.arange(4).reshape(4, 1),
        option_categorical_missing=torch.zeros((4, 1), dtype=torch.bool),
        option_numeric=torch.arange(4, dtype=torch.float32).reshape(4, 1),
        option_numeric_missing=torch.zeros((4, 1), dtype=torch.bool),
        option_source_entity_indices=torch.tensor([0, 2, -1, 4]),
        option_target_entity_indices=torch.tensor([1, -1, 2, 3]),
        option_available=torch.ones(4, dtype=torch.bool),
        option_offsets=torch.tensor([0, 1, 3, 4]),
        global_categorical=torch.arange(6).reshape(3, 2),
        global_categorical_missing=torch.zeros((3, 2), dtype=torch.bool),
        global_numeric=torch.arange(6, dtype=torch.float32).reshape(3, 2),
        global_numeric_missing=torch.zeros((3, 2), dtype=torch.bool),
    )
    sliced = slice_torch_decision_batch_rows(batch, 1, 3)
    assert sliced.batch_size == 2
    assert sliced.entity_offsets.tolist() == [0, 1, 3]
    assert sliced.entity_parent_indices.tolist() == [-1, -1, 1]
    assert sliced.entity_energy_values.tolist() == [7, 8, 9]
    assert sliced.entity_energy_offsets.tolist() == [0, 1, 1, 3]
    assert sliced.event_offsets.tolist() == [0, 0, 1]
    assert sliced.event_entity_indices.tolist() == [[2, 1]]
    assert sliced.option_offsets.tolist() == [0, 2, 3]
    assert sliced.option_source_entity_indices.tolist() == [0, -1, 2]
    assert sliced.option_target_entity_indices.tolist() == [-1, 0, 1]
    assert torch.equal(sliced.global_categorical, batch.global_categorical[1:3])


def test_complete_game_gae_matches_scalar_per_player_contract() -> None:
    # Chronological interleave: env0/p0, env0/p1, env1/p0, env0/p0,
    # env1/p1, env0/p1, env1/p0, env1/p1.
    owners = torch.tensor([0, 1, 2, 0, 3, 1, 2, 3], dtype=torch.long)
    values = torch.tensor([0.1, -0.2, 0.3, 0.15, -0.1, -0.25, 0.35, -0.05])
    final_results = torch.tensor([1, 2], dtype=torch.long)
    result, stats = compute_complete_game_gae(
        owner_ids=owners,
        values=values,
        final_results=final_results,
        env_count=2,
        gamma=0.999,
        gae_lambda=0.95,
    )

    expected_advantages = torch.zeros_like(values)
    expected_returns = torch.zeros_like(values)
    for owner in range(4):
        indices = torch.nonzero(owners == owner, as_tuple=False).squeeze(1)
        owner_values = values.index_select(0, indices)
        rewards = torch.zeros_like(owner_values)
        player = owner % 2
        result_code = int(final_results[owner // 2])
        rewards[-1] = 1.0 if result_code == player + 1 else -1.0
        bootstrap = torch.zeros_like(owner_values)
        bootstrap[:-1] = owner_values[1:]
        terminals = torch.zeros(owner_values.numel(), dtype=torch.bool)
        terminals[-1] = True
        continues = torch.ones_like(terminals)
        continues[-1] = False
        scalar = compute_gae(
            rewards=rewards,
            values=owner_values,
            bootstrap_values=bootstrap,
            terminals=terminals,
            truncations=torch.zeros_like(terminals),
            trace_continues=continues,
            gamma=0.999,
            gae_lambda=0.95,
        )
        expected_advantages.index_copy_(0, indices, scalar.advantages)
        expected_returns.index_copy_(0, indices, scalar.returns)

    assert torch.allclose(result.advantages, expected_advantages, atol=1e-7, rtol=0)
    assert torch.allclose(result.returns, expected_returns, atol=1e-7, rtol=0)
    assert stats.trajectory_count == 4
    assert stats.trajectory_length_min == 2
    assert stats.trajectory_length_max == 2
    assert stats.terminal_wins == 2
    assert stats.terminal_losses == 2
    assert stats.terminal_draws == 0


def test_fixed_horizon_gae_uses_terminal_rewards_and_live_bootstrap_tail() -> None:
    owners = torch.tensor(
        [0, 1, 2, 3, 0, 1, 2, 3, 0, 1, 2, 3], dtype=torch.long
    )
    values = torch.tensor(
        [0.10, -0.10, 0.20, -0.20, 0.15, -0.15, 0.25, -0.25, 0.30, -0.30, 0.40, -0.40]
    )
    # env0 terminates with player 0 winning; env1 remains live at the horizon.
    result, train_mask, stats = compute_fixed_horizon_gae(
        owner_ids=owners,
        values=values,
        final_results=torch.tensor([1, 0], dtype=torch.long),
        env_count=2,
        gamma=1.0,
        gae_lambda=0.95,
    )

    expected_advantages = torch.zeros_like(values)
    expected_returns = values.clone()
    expected_mask = torch.zeros(values.numel(), dtype=torch.bool)
    for owner in range(4):
        indices = torch.nonzero(owners == owner, as_tuple=False).squeeze(1)
        owner_values = values.index_select(0, indices)
        if owner < 2:
            rewards = torch.zeros_like(owner_values)
            rewards[-1] = 1.0 if owner == 0 else -1.0
            bootstrap = torch.zeros_like(owner_values)
            bootstrap[:-1] = owner_values[1:]
            terminals = torch.tensor([False, False, True])
            truncations = torch.zeros(3, dtype=torch.bool)
            continues = torch.tensor([True, True, False])
            used_indices = indices
            used_values = owner_values
        else:
            # Withhold the final live node and use its value to bootstrap the
            # preceding node at the artificial horizon boundary.
            rewards = torch.zeros(2)
            bootstrap = torch.tensor([owner_values[1], owner_values[2]])
            terminals = torch.zeros(2, dtype=torch.bool)
            truncations = torch.tensor([False, True])
            continues = torch.tensor([True, False])
            used_indices = indices[:2]
            used_values = owner_values[:2]
        scalar = compute_gae(
            rewards=rewards,
            values=used_values,
            bootstrap_values=bootstrap,
            terminals=terminals,
            truncations=truncations,
            trace_continues=continues,
            gamma=1.0,
            gae_lambda=0.95,
        )
        expected_advantages.index_copy_(0, used_indices, scalar.advantages)
        expected_returns.index_copy_(0, used_indices, scalar.returns)
        expected_mask[used_indices] = True

    assert torch.equal(train_mask, expected_mask)
    assert torch.allclose(result.advantages, expected_advantages, atol=1e-7, rtol=0)
    assert torch.allclose(result.returns, expected_returns, atol=1e-7, rtol=0)
    assert stats.trajectory_count == 4
    assert stats.terminal_trajectories == 2
    assert stats.truncated_trajectories == 2
    assert stats.dropped_live_tail_nodes == 2
    assert stats.trainable_nodes == 10


def test_fixed_horizon_gae_drops_singleton_live_trace() -> None:
    owners = torch.tensor([0, 1, 2, 0, 1], dtype=torch.long)
    values = torch.tensor([0.1, -0.1, 0.5, 0.2, -0.2])
    result, train_mask, stats = compute_fixed_horizon_gae(
        owner_ids=owners,
        values=values,
        final_results=torch.tensor([1, 0], dtype=torch.long),
        env_count=2,
    )
    singleton_index = int(torch.nonzero(owners == 2, as_tuple=False).item())
    assert not bool(train_mask[singleton_index])
    assert float(result.advantages[singleton_index]) == 0.0
    assert stats.dropped_live_tail_nodes == 1
