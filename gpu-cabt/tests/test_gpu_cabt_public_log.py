import pytest

from gpu_cabt.public_log import (
    LOG_DRAW,
    LOG_DRAW_REVERSE,
    LOG_MOVE_CARD,
    LOG_MOVE_CARD_REVERSE,
    project_public_log_for_actor,
    public_event_actor,
)


def test_event_actor_retains_last_selector_at_terminal() -> None:
    assert public_event_actor(0, 1, 2) == 1
    assert public_event_actor(1, 0, 0) == 0
    assert public_event_actor(0, 0, 0) is None
    assert public_event_actor(0, -1, 1) is None


def test_opponent_draw_masks_card_identity() -> None:
    assert project_public_log_for_actor(LOG_DRAW, (1, 678, 91), actor=0) == (
        LOG_DRAW_REVERSE,
        (1,),
    )
    assert project_public_log_for_actor(LOG_DRAW, (1, 678, 91), actor=1) == (
        LOG_DRAW,
        (1, 678, 91),
    )


@pytest.mark.parametrize(
    ("open_type", "actor", "visible"),
    [
        (0, 0, True),
        (0, 1, True),
        (1, 0, True),
        (1, 1, False),
        (2, 0, False),
        (2, 1, False),
        (3, 0, True),
        (3, 1, False),
        (4, 0, False),
        (4, 1, True),
    ],
)
def test_move_card_matches_native_open_type_visibility(
    open_type: int,
    actor: int,
    visible: bool,
) -> None:
    raw = (0, 678, 91, 2, 3, open_type)
    projected_type, params = project_public_log_for_actor(LOG_MOVE_CARD, raw, actor=actor)
    if visible:
        assert projected_type == LOG_MOVE_CARD
        assert params == raw[:5]
    else:
        assert projected_type == LOG_MOVE_CARD_REVERSE
        assert params == (0, 2, 3)


def test_already_public_reverse_events_pass_through() -> None:
    assert project_public_log_for_actor(LOG_DRAW_REVERSE, (1,), actor=0) == (
        LOG_DRAW_REVERSE,
        (1,),
    )
    assert project_public_log_for_actor(LOG_MOVE_CARD_REVERSE, (1, 2, 3), actor=0) == (
        LOG_MOVE_CARD_REVERSE,
        (1, 2, 3),
    )


def test_projection_rejects_non_player_actor() -> None:
    with pytest.raises(ValueError, match="actor"):
        project_public_log_for_actor(LOG_DRAW, (0, 678, 91), actor=2)
