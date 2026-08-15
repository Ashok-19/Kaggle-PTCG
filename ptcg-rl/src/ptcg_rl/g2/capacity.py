from __future__ import annotations

from dataclasses import replace

from ptcg_rl.g2.network import PolicyConfigV1


def model_configs() -> dict[str, PolicyConfigV1]:
    """Return the canonical qualified neural-policy capacity configurations.

    This table is shared by BC and RL so a training checkpoint is always
    reconstructed with the exact architecture that produced it.
    """
    base = PolicyConfigV1()
    return {
        "970k": base,
        "1.4m": replace(
            base,
            model_width=160,
            entity_heads=5,
            entity_ff_width=320,
            public_hidden=224,
            selection_hidden=128,
            option_width=160,
            max_trainable_parameters=6_000_000,
            target_trainable_parameters=1_500_000,
        ),
        "1.8m": replace(
            base,
            model_width=192,
            entity_heads=6,
            entity_ff_width=384,
            event_hidden=96,
            public_hidden=256,
            selection_hidden=160,
            option_width=192,
            max_trainable_parameters=6_000_000,
            target_trainable_parameters=2_000_000,
        ),
        "2.9m": replace(
            base,
            model_width=224,
            entity_heads=7,
            entity_layers=3,
            entity_ff_width=448,
            card_id_dim=80,
            attack_id_dim=40,
            event_width=80,
            event_hidden=112,
            public_hidden=320,
            selection_hidden=192,
            option_width=224,
            max_trainable_parameters=6_000_000,
            target_trainable_parameters=3_000_000,
        ),
        "3.7m": replace(
            base,
            model_width=256,
            entity_heads=8,
            entity_layers=3,
            entity_ff_width=512,
            card_id_dim=96,
            attack_id_dim=48,
            event_width=96,
            event_hidden=128,
            public_hidden=384,
            selection_hidden=224,
            option_width=256,
            max_trainable_parameters=6_000_000,
            target_trainable_parameters=4_000_000,
        ),
        "5.0m": replace(
            base,
            model_width=288,
            entity_heads=9,
            entity_layers=4,
            entity_ff_width=512,
            card_id_dim=96,
            attack_id_dim=48,
            event_width=96,
            event_hidden=128,
            public_hidden=432,
            selection_hidden=240,
            option_width=288,
            max_trainable_parameters=6_000_000,
            target_trainable_parameters=5_000_000,
        ),
    }


def model_config(label: str) -> PolicyConfigV1:
    try:
        return model_configs()[label]
    except KeyError as error:
        raise ValueError(f"unknown model capacity label {label!r}") from error
