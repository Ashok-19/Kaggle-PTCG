from __future__ import annotations

PUBLIC_LOOKING_NONE = 0
PUBLIC_LOOKING_VISIBLE = 1
PUBLIC_LOOKING_FACEDOWN = 2


def public_looking_mode(*, count: int, looking_player: int, actor: int) -> int:
    """Normalize CABT looking visibility to information present in ToJsonApi.

    CABT serializes actor-only and both-player visible looking lists identically,
    so the learner must not receive a bit that distinguishes those internal modes.
    """
    if actor not in (0, 1):
        raise ValueError("actor must be 0 or 1")
    if count <= 0:
        return PUBLIC_LOOKING_NONE
    if looking_player == actor or looking_player == 2:
        return PUBLIC_LOOKING_VISIBLE
    if looking_player == actor + 3:
        return PUBLIC_LOOKING_FACEDOWN
    return PUBLIC_LOOKING_NONE
