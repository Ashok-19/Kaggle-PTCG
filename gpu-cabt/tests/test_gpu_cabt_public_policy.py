import pytest

from gpu_cabt.public_policy import (
    PUBLIC_LOOKING_FACEDOWN,
    PUBLIC_LOOKING_NONE,
    PUBLIC_LOOKING_VISIBLE,
    public_looking_mode,
)


def test_empty_looking_list_has_no_public_mode() -> None:
    assert public_looking_mode(count=0, looking_player=0, actor=0) == PUBLIC_LOOKING_NONE
    assert public_looking_mode(count=0, looking_player=2, actor=1) == PUBLIC_LOOKING_NONE


@pytest.mark.parametrize("actor", [0, 1])
def test_actor_only_and_both_visible_collapse_to_same_public_mode(actor: int) -> None:
    assert public_looking_mode(count=3, looking_player=actor, actor=actor) == PUBLIC_LOOKING_VISIBLE
    assert public_looking_mode(count=3, looking_player=2, actor=actor) == PUBLIC_LOOKING_VISIBLE


@pytest.mark.parametrize("actor", [0, 1])
def test_facedown_looking_is_distinct_but_identity_free(actor: int) -> None:
    assert public_looking_mode(count=3, looking_player=actor + 3, actor=actor) == PUBLIC_LOOKING_FACEDOWN


@pytest.mark.parametrize("actor", [0, 1])
def test_other_players_private_looking_is_not_visible(actor: int) -> None:
    assert public_looking_mode(count=3, looking_player=1 - actor, actor=actor) == PUBLIC_LOOKING_NONE


def test_invalid_actor_is_rejected() -> None:
    with pytest.raises(ValueError, match="actor"):
        public_looking_mode(count=1, looking_player=0, actor=2)
