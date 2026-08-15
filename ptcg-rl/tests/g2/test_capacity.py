from __future__ import annotations

import pytest

from ptcg_rl.g2.capacity import model_config, model_configs


def test_capacity_registry_preserves_v7_3p7m_architecture() -> None:
    configs = model_configs()
    assert tuple(configs) == ("970k", "1.4m", "1.8m", "2.9m", "3.7m", "5.0m")

    config = configs["3.7m"]
    assert config.model_width == 256
    assert config.entity_heads == 8
    assert config.entity_layers == 3
    assert config.entity_ff_width == 512
    assert config.card_id_dim == 96
    assert config.attack_id_dim == 48
    assert config.event_width == 96
    assert config.event_hidden == 128
    assert config.public_hidden == 384
    assert config.selection_hidden == 224
    assert config.option_width == 256
    assert config.max_trainable_parameters == 6_000_000
    assert config.target_trainable_parameters == 4_000_000
    assert model_config("3.7m") == config


def test_capacity_registry_rejects_unknown_label() -> None:
    with pytest.raises(ValueError, match="unknown model capacity label"):
        model_config("unknown")
