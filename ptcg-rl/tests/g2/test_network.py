from __future__ import annotations

import io
from pathlib import Path

import torch

from ptcg_rl.g1.actions import permute_request
from ptcg_rl.g1.semantic import semantic_snapshot
from ptcg_rl.g2.network import (
    PTCGPolicyV1,
    collate_projected,
    policy_metadata,
)
from ptcg_rl.g2.projection import project_decision
from ..g1_fixtures import raw_observation
from .test_card_table import build_fixture

CARD_HASH = "c" * 64


def number_decision(count: int = 5):
    raw = raw_observation(options=[{"type": 0, "number": value} for value in range(count)])
    raw["select"].update({"type": 8, "context": 38, "minCount": 1, "maxCount": 1})
    observation, request = semantic_snapshot(raw, "number-decision", 0, CARD_HASH)
    assert request is not None
    return observation, request, project_decision(observation, request)


def card_decision():
    raw = raw_observation(options=[{"type": 15, "cardId": 1, "serial": 10}])
    raw["select"].update({"type": 5, "context": 34, "minCount": 1, "maxCount": 1})
    raw["current"]["players"][0]["active"] = [
        {
            "id": 1,
            "serial": 10,
            "playerIndex": 0,
            "hp": 50,
            "maxHp": 70,
            "appearThisTurn": False,
            "energies": [1],
            "energyCards": [],
            "tools": [],
            "preEvolution": [],
        }
    ]
    raw["logs"] = [
        {
            "type": 15,
            "playerIndex": 0,
            "cardId": 1,
            "serial": 10,
            "attackId": 1,
        },
        {
            "type": 16,
            "cardIdTarget": 1,
            "serialTarget": 10,
            "value": -20,
            "putDamageCounter": False,
            "isRecover": False,
        },
    ]
    observation, request = semantic_snapshot(raw, "card-decision", 0, CARD_HASH)
    assert request is not None
    return project_decision(observation, request)


def model(tmp_path: Path) -> PTCGPolicyV1:
    return PTCGPolicyV1(build_fixture(tmp_path / "cards.csv"))


def test_policy_stays_inside_target_parameter_budget(tmp_path: Path) -> None:
    policy = model(tmp_path)
    metadata = policy_metadata(policy)
    assert metadata["trainable_parameters"] < 1_250_000
    assert metadata["trainable_parameters"] == policy.trainable_parameter_count
    assert len(metadata["architecture_sha256"]) == 64
    assert len(metadata["config_sha256"]) == 64


def test_forward_supports_ragged_batches_and_more_than_64_options(tmp_path: Path) -> None:
    policy = model(tmp_path).eval()
    _, _, large = number_decision(70)
    small = card_decision()
    batch = collate_projected((large, small))
    output = policy(batch)
    assert output.option_logits.shape == (71,)
    assert output.values.shape == (2,)
    assert output.hidden.shape == (2, policy.config.public_hidden)
    assert output.option_offsets.tolist() == [0, 70, 71]
    assert torch.isfinite(output.option_logits).all()
    assert torch.isfinite(output.values).all()


def test_option_permutation_is_equivariant_and_state_is_invariant(tmp_path: Path) -> None:
    policy = model(tmp_path).eval()
    observation, request, original = number_decision(5)
    permutation = [4, 1, 3, 0, 2]
    permuted_request = permute_request(request, permutation)
    permuted = project_decision(observation, permuted_request)
    with torch.no_grad():
        first = policy(collate_projected((original,)))
        second = policy(collate_projected((permuted,)))
    assert torch.allclose(
        second.option_logits,
        first.option_logits[torch.tensor(permutation)],
        rtol=0,
        atol=1e-6,
    )
    assert torch.allclose(second.values, first.values, rtol=0, atol=1e-6)
    assert torch.allclose(second.hidden, first.hidden, rtol=0, atol=1e-6)


def test_backward_reaches_catalog_attention_recurrence_policy_value_and_decoder(
    tmp_path: Path,
) -> None:
    policy = model(tmp_path).train()
    batch = collate_projected((card_decision(),))
    first = policy(batch)
    output = policy(batch, first.hidden)
    prefix = policy.decoder_initial(output.hidden[0])
    decoder_logits = policy.decoder_logits(
        prefix,
        output.option_embeddings,
        torch.ones(1, dtype=torch.bool),
        True,
    )
    advanced = policy.decoder_advance(prefix, output.option_embeddings[0])
    loss = (
        output.option_logits.sum()
        + output.values.sum()
        + output.hidden.square().mean()
        + decoder_logits.sum()
        + advanced.square().mean()
    )
    loss.backward()
    required = {
        "catalog.card_id_embedding.weight",
        "entity_transformer.layers.0.self_attn.in_proj_weight",
        "public_gru.weight_hh",
        "option_projection.0.weight",
        "value_head.0.weight",
        "selection_gru.weight_hh",
        "stop_embedding",
    }
    gradients = {
        name: float(torch.linalg.vector_norm(parameter.grad))
        for name, parameter in policy.named_parameters()
        if parameter.grad is not None and torch.isfinite(parameter.grad).all()
    }
    assert required <= gradients.keys()
    assert all(gradients[name] > 0 for name in required)


def test_decoder_masks_options_and_stop_without_advancing_public_memory(tmp_path: Path) -> None:
    policy = model(tmp_path).eval()
    output = policy(collate_projected((number_decision(3)[2],)))
    prefix = policy.decoder_initial(output.hidden[0])
    before = output.hidden.detach().clone()
    logits = policy.decoder_logits(
        prefix,
        output.option_embeddings,
        torch.tensor([True, False, True]),
        False,
    )
    assert logits.shape == (4,)
    assert torch.isneginf(logits[1])
    assert torch.isneginf(logits[-1])
    advanced = policy.decoder_advance(prefix, output.option_embeddings[0])
    assert advanced.shape == prefix.shape
    assert torch.equal(output.hidden, before)


def test_state_dict_round_trip_preserves_outputs(tmp_path: Path) -> None:
    first = model(tmp_path).eval()
    batch = collate_projected((card_decision(), number_decision(7)[2]))
    with torch.no_grad():
        expected = first(batch)
    buffer = io.BytesIO()
    torch.save(first.state_dict(), buffer)
    buffer.seek(0)
    second = model(tmp_path).eval()
    second.load_state_dict(torch.load(buffer, weights_only=True))
    with torch.no_grad():
        observed = second(batch)
    assert torch.equal(expected.option_logits, observed.option_logits)
    assert torch.equal(expected.values, observed.values)
    assert torch.equal(expected.hidden, observed.hidden)
