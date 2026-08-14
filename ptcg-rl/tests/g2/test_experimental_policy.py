from __future__ import annotations

from pathlib import Path

import torch

from ptcg_rl.g2.experimental_policy import (
    OptionEntityCrossAttentionConfigV1,
    PTCGPolicyCrossAttentionV1,
)
from ptcg_rl.g2.network import PTCGPolicyV1, collate_projected

from .test_card_table import build_fixture
from .test_network import card_decision, number_decision, zero_option_decision


def _cross_policy(tmp_path: Path, *, gated: bool) -> PTCGPolicyCrossAttentionV1:
    table = build_fixture(tmp_path / ("cards-gated.csv" if gated else "cards-cross.csv"))
    return PTCGPolicyCrossAttentionV1(
        table,
        cross_attention=OptionEntityCrossAttentionConfigV1(gated_residual=gated),
    )


def test_cross_attention_parameter_overhead_is_small_and_explicit(tmp_path: Path) -> None:
    table = build_fixture(tmp_path / "cards.csv")
    baseline = PTCGPolicyV1(table)
    plain = PTCGPolicyCrossAttentionV1(table)
    gated = PTCGPolicyCrossAttentionV1(
        table,
        cross_attention=OptionEntityCrossAttentionConfigV1(gated_residual=True),
    )
    assert plain.trainable_parameter_count - baseline.trainable_parameter_count == 49_792
    assert gated.trainable_parameter_count - plain.trainable_parameter_count == 32_896
    assert len({baseline.architecture_sha256, plain.architecture_sha256, gated.architecture_sha256}) == 3


def test_cross_attention_forward_supports_ragged_options_and_entities(tmp_path: Path) -> None:
    batch = collate_projected((number_decision(70)[2], card_decision(), zero_option_decision()))
    for gated in (False, True):
        policy = _cross_policy(tmp_path, gated=gated).eval()
        with torch.no_grad():
            output = policy(batch)
        assert output.option_logits.shape == (71,)
        assert output.option_embeddings.shape == (71, policy.config.option_width)
        assert output.option_offsets.tolist() == [0, 70, 71, 71]
        assert torch.isfinite(output.option_logits).all()
        assert torch.isfinite(output.option_embeddings).all()
        assert torch.isfinite(output.hidden).all()


def test_cross_attention_forward_supports_all_zero_options(tmp_path: Path) -> None:
    batch = collate_projected((zero_option_decision(), zero_option_decision()))
    for gated in (False, True):
        policy = _cross_policy(tmp_path, gated=gated).eval()
        with torch.no_grad():
            output = policy(batch)
        assert output.option_logits.shape == (0,)
        assert output.option_embeddings.shape == (0, policy.config.option_width)
        assert torch.isfinite(output.values).all()
        assert torch.isfinite(output.hidden).all()


def test_cross_attention_receives_policy_gradient(tmp_path: Path) -> None:
    policy = _cross_policy(tmp_path, gated=True).train()
    batch = collate_projected((number_decision(5)[2], card_decision()))
    output = policy(batch)
    loss = output.option_logits.square().mean() + output.values.square().mean()
    loss.backward()
    query_grad = policy.option_cross_query.weight.grad
    key_grad = policy.entity_cross_key.weight.grad
    gate = policy.option_cross_gate
    assert query_grad is not None and torch.isfinite(query_grad).all() and query_grad.abs().sum() > 0
    assert key_grad is not None and torch.isfinite(key_grad).all() and key_grad.abs().sum() > 0
    assert gate is not None
    assert gate.weight.grad is not None and torch.isfinite(gate.weight.grad).all()
