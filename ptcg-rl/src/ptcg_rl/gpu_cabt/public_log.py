from __future__ import annotations

from collections.abc import Sequence

LOG_DRAW = 4
LOG_DRAW_REVERSE = 5
LOG_MOVE_CARD = 6
LOG_MOVE_CARD_REVERSE = 7


def public_event_actor(select_type: int, select_player: int, game_result: int) -> int | None:
    """Return the CABT viewer for a decision/terminal observation boundary."""
    if select_player not in (0, 1):
        return None
    if select_type != 0 or game_result != 0:
        return select_player
    return None


def project_public_log_for_actor(
    log_type: int,
    params: Sequence[int],
    *,
    actor: int,
) -> tuple[int, tuple[int, ...]]:
    """Reference CABT public-log masking for one selecting actor.

    Raw GPU logs retain the native engine's private bookkeeping fields. This
    projection mirrors ApiJson.h: opponent draws lose card identity, and card
    moves reveal identity only when their native openType permits that actor to
    see it. The internal openType value itself is never part of the public log.
    """
    if actor not in (0, 1):
        raise ValueError("actor must be 0 or 1")
    values = tuple(int(value) for value in params)

    if log_type == LOG_DRAW:
        if len(values) < 3:
            raise ValueError("Draw requires playerIndex, cardId, serial")
        if values[0] != actor:
            return LOG_DRAW_REVERSE, (values[0],)
        return LOG_DRAW, values[:3]

    if log_type == LOG_MOVE_CARD:
        if len(values) < 6:
            raise ValueError(
                "MoveCard requires playerIndex, cardId, serial, fromArea, toArea, openType"
            )
        player, card_id, serial, from_area, to_area, open_type = values[:6]
        visible = (
            open_type == 0
            or (open_type == 1 and player == actor)
            or (open_type == 3 and actor == 0)
            or (open_type == 4 and actor == 1)
        )
        if visible:
            return LOG_MOVE_CARD, (player, card_id, serial, from_area, to_area)
        return LOG_MOVE_CARD_REVERSE, (player, from_area, to_area)

    return int(log_type), values
