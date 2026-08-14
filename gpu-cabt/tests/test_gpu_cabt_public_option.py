from gpu_cabt.public_option import (
    OPTION_ATTACK,
    OPTION_CARD,
    OPTION_ENERGY,
    OPTION_SKILL,
    public_option_params,
)


def test_attack_projection_excludes_execution_metadata() -> None:
    assert public_option_params(OPTION_ATTACK, (120, 110, 3, 0, 0)) == (120,)


def test_card_and_energy_projection_keep_public_coordinates() -> None:
    assert public_option_params(OPTION_CARD, (2, 4, 1, 9, 8)) == (2, 4, 1)
    assert public_option_params(OPTION_ENERGY, (4, 0, 0, 2, 3)) == (4, 0, 0, 2, 3)


def test_skill_projection_keeps_card_id_but_not_serial() -> None:
    assert public_option_params(OPTION_SKILL, (20, 91, 0, 0, 0)) == (20,)
