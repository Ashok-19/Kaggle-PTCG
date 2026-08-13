from __future__ import annotations

from collections.abc import Sequence

OPTION_NUMBER = 0
OPTION_CARD = 3
OPTION_TOOL_CARD = 4
OPTION_ENERGY_CARD = 5
OPTION_ENERGY = 6
OPTION_PLAY = 7
OPTION_ATTACH = 8
OPTION_EVOLVE = 9
OPTION_ABILITY = 10
OPTION_DISCARD = 11
OPTION_ATTACK = 13
OPTION_SKILL = 15
OPTION_SPECIAL_CONDITION = 16


def public_option_params(option_type: int, params: Sequence[int]) -> tuple[int, ...]:
    """Return actor-feature parameters allowed by CABT's public option API.

    Skill serials are deliberately omitted from actor features, matching the
    semantic schema. Attack source-attack and bench-index parameters are private
    engine execution metadata and are never returned.
    """
    values = tuple(int(value) for value in params)
    if len(values) < 5:
        values = values + (0,) * (5 - len(values))

    if option_type in (OPTION_NUMBER, OPTION_PLAY, OPTION_SPECIAL_CONDITION, OPTION_SKILL):
        return (values[0],)
    if option_type == OPTION_CARD:
        return values[:3]
    if option_type in (OPTION_TOOL_CARD, OPTION_ENERGY_CARD, OPTION_ATTACH, OPTION_EVOLVE):
        return values[:4]
    if option_type == OPTION_ENERGY:
        return values[:5]
    if option_type in (OPTION_ABILITY, OPTION_DISCARD):
        return values[:2]
    if option_type == OPTION_ATTACK:
        return (values[0],)
    return ()
