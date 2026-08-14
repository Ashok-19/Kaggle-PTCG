from __future__ import annotations

import torch

from ptcg_rl.g2.network import TorchDecisionBatch
from ptcg_rl.g3.ppo import compute_gae
from ptcg_rl.g3.production_ppo import (
    compute_complete_game_gae,
    meaningful_compound_policy_mask,
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
