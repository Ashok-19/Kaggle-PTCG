from __future__ import annotations

import math
from types import SimpleNamespace

import torch

from ptcg_rl.g3.compound_batch import (
    replay_compound_actions_batched,
    sample_compound_actions_batched,
)
from ptcg_rl.g3.ppo import CompoundActionV1, replay_compound_action


class TinyDecoder:
    def __init__(self) -> None:
        self.config = SimpleNamespace(selection_hidden=3)
        self.stop_embedding = torch.tensor([0.2, -0.1, 0.05])

    @staticmethod
    def decoder_initial(public_hidden: torch.Tensor) -> torch.Tensor:
        return torch.tanh(public_hidden)

    @staticmethod
    def selection_option(options: torch.Tensor) -> torch.Tensor:
        return options

    @staticmethod
    def selection_gru(chosen: torch.Tensor, prefix: torch.Tensor) -> torch.Tensor:
        return torch.tanh(prefix + 0.3 * chosen)

    def decoder_logits(
        self,
        prefix: torch.Tensor,
        options: torch.Tensor,
        available: torch.Tensor,
        stop_available: torch.Tensor | bool,
    ) -> torch.Tensor:
        option_logits = (options * prefix).sum(dim=-1) / math.sqrt(3.0)
        option_logits = option_logits.masked_fill(~available, float("-inf"))
        stop_logit = (self.stop_embedding * prefix).sum() / math.sqrt(3.0)
        stop_mask = torch.as_tensor(stop_available, dtype=torch.bool)
        stop_logit = stop_logit.masked_fill(~stop_mask, float("-inf"))
        return torch.cat((option_logits, stop_logit.reshape(1)))

    @staticmethod
    def decoder_advance(prefix: torch.Tensor, chosen: torch.Tensor) -> torch.Tensor:
        return torch.tanh(prefix + 0.3 * chosen)


def test_batched_compound_sampler_replays_exactly_and_matches_scalar_contract() -> None:
    model = TinyDecoder()
    public_hidden = torch.tensor(
        [[0.1, 0.2, -0.3], [0.4, -0.2, 0.1], [-0.1, 0.3, 0.2]]
    )
    options = torch.tensor(
        [
            [0.5, 0.1, -0.2],
            [-0.3, 0.7, 0.4],
            [0.2, -0.4, 0.8],
            [0.6, -0.2, 0.3],
            [-0.4, 0.5, 0.1],
        ]
    )
    offsets = torch.tensor([0, 3, 5, 5], dtype=torch.long)
    available = torch.tensor([True, False, True, True, True])
    minimum = torch.tensor([1, 0, 0], dtype=torch.long)
    maximum = torch.tensor([2, 1, 0], dtype=torch.long)
    generator = torch.Generator().manual_seed(20260814)

    sampled = sample_compound_actions_batched(
        model,
        public_hidden=public_hidden,
        option_embeddings=options,
        option_offsets=offsets,
        available_mask=available,
        minimum_counts=minimum,
        maximum_counts=maximum,
        generator=generator,
    )
    replayed_logp, replayed_entropy = replay_compound_actions_batched(
        model,
        public_hidden=public_hidden,
        option_embeddings=options,
        option_offsets=offsets,
        available_mask=available,
        minimum_counts=minimum,
        maximum_counts=maximum,
        actions=sampled,
    )
    assert torch.allclose(sampled.log_probabilities, replayed_logp, atol=1e-7, rtol=0)
    assert torch.allclose(sampled.normalized_entropies, replayed_entropy, atol=1e-7, rtol=0)

    for row in range(3):
        start = int(offsets[row])
        end = int(offsets[row + 1])
        length = int(sampled.selected_lengths[row])
        action = CompoundActionV1(
            tuple(int(value) for value in sampled.selected_indices[row, :length].tolist()),
            bool(sampled.stopped[row]),
        )
        scalar = replay_compound_action(
            initial_prefix=model.decoder_initial(public_hidden[row]),
            option_embeddings=options[start:end],
            available_mask=available[start:end],
            action=action,
            minimum_count=int(minimum[row]),
            maximum_count=int(maximum[row]),
            decoder_logits=model.decoder_logits,
            decoder_advance=model.decoder_advance,
        )
        assert torch.allclose(sampled.log_probabilities[row], scalar.log_probability, atol=1e-7, rtol=0)
        assert torch.allclose(sampled.normalized_entropies[row], scalar.normalized_entropy, atol=1e-7, rtol=0)


def test_batched_compound_sampler_respects_bounds_and_no_duplicate_choices() -> None:
    model = TinyDecoder()
    hidden = torch.zeros((8, 3))
    options = torch.randn((32, 3), generator=torch.Generator().manual_seed(7))
    offsets = torch.arange(0, 33, 4, dtype=torch.long)
    available = torch.ones(32, dtype=torch.bool)
    minimum = torch.tensor([0, 1, 2, 1, 0, 3, 2, 1])
    maximum = torch.tensor([1, 2, 3, 4, 2, 3, 4, 2])
    actions = sample_compound_actions_batched(
        model,
        public_hidden=hidden,
        option_embeddings=options,
        option_offsets=offsets,
        available_mask=available,
        minimum_counts=minimum,
        maximum_counts=maximum,
        generator=torch.Generator().manual_seed(19),
    )
    for row in range(8):
        length = int(actions.selected_lengths[row])
        values = actions.selected_indices[row, :length].tolist()
        assert int(minimum[row]) <= length <= int(maximum[row])
        assert len(values) == len(set(values))
        if not bool(actions.stopped[row]):
            assert length == int(maximum[row])
