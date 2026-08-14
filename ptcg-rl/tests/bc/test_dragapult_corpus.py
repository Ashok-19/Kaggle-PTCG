from __future__ import annotations

from ptcg_rl.bc.dragapult_corpus import (
    DOMINANT_DRAGAPULT_DECK_SHA256,
    DragapultCorpusPolicy,
    EliteTeacher,
    choose_dragapult_teacher,
    quality_tier,
)
from ptcg_rl.bc.source import ReplayPrefixRecord


def _prefix(*, winner: int = 0, team0: str = "teacher", team1: str = "opponent", module: str = "1.32.6", both_target: bool = False) -> ReplayPrefixRecord:
    rewards = (1, -1) if winner == 0 else (-1, 1)
    hashes = [DOMINANT_DRAGAPULT_DECK_SHA256, "1" * 64]
    if both_target:
        hashes[1] = DOMINANT_DRAGAPULT_DECK_SHA256
    return ReplayPrefixRecord(
        team_names=(team0, team1),
        module_version=module,
        rewards=rewards,
        winner_player_index=winner,
        deck_sha256=(hashes[0], hashes[1]),
        deck_card_ids=(
            (121, *([2] * 59)),
            ((121, *([3] * 59)) if both_target else tuple([3] * 60)),
        ),
    )


def test_qualified_exact_deck_teacher_is_admitted_even_when_losing() -> None:
    teachers = {"teacher": EliteTeacher(team_name="teacher", rank=10, score=1153.3)}
    result = choose_dragapult_teacher(
        _prefix(winner=1),
        policy=DragapultCorpusPolicy(),
        elite_teachers=teachers,
    )
    assert result == (0, "frozen_live_teacher_score")


def test_teacher_floor_is_1090_and_opponent_score_is_not_part_of_selection() -> None:
    policy = DragapultCorpusPolicy()
    assert choose_dragapult_teacher(
        _prefix(),
        policy=policy,
        elite_teachers={
            "teacher": EliteTeacher(team_name="teacher", rank=20, score=1090.0)
        },
    ) == (0, "frozen_live_teacher_score")
    assert choose_dragapult_teacher(
        _prefix(),
        policy=policy,
        elite_teachers={"teacher": EliteTeacher(team_name="teacher", rank=21, score=1089.9)},
    ) is None


def test_mirror_match_prefers_qualified_winner_to_keep_episode_unique() -> None:
    teachers = {
        "teacher": EliteTeacher(team_name="teacher", rank=5, score=1170.0),
        "opponent": EliteTeacher(team_name="opponent", rank=6, score=1160.0),
    }
    assert choose_dragapult_teacher(
        _prefix(winner=1, both_target=True),
        policy=DragapultCorpusPolicy(),
        elite_teachers=teachers,
    ) == (1, "frozen_live_teacher_score")


def test_archetype_wide_accepts_noncanonical_dragapult_variant() -> None:
    teachers = {"teacher": EliteTeacher(team_name="teacher", rank=5, score=1170.0)}
    prefix = _prefix()
    variant = ReplayPrefixRecord(
        team_names=prefix.team_names,
        module_version=prefix.module_version,
        rewards=prefix.rewards,
        winner_player_index=prefix.winner_player_index,
        deck_sha256=("a" * 64, prefix.deck_sha256[1]),
        deck_card_ids=prefix.deck_card_ids,
    )
    assert choose_dragapult_teacher(
        variant,
        policy=DragapultCorpusPolicy(archetype_wide=True),
        elite_teachers=teachers,
    ) == (0, "frozen_live_teacher_score")


def test_wrong_module_or_wrong_deck_is_rejected() -> None:
    policy = DragapultCorpusPolicy()
    teachers = {"teacher": EliteTeacher(team_name="teacher", rank=1, score=1217.0)}
    assert choose_dragapult_teacher(
        _prefix(module="1.32.5"), policy=policy, elite_teachers=teachers
    ) is None
    prefix = _prefix()
    wrong = ReplayPrefixRecord(
        team_names=prefix.team_names,
        module_version=prefix.module_version,
        rewards=prefix.rewards,
        winner_player_index=prefix.winner_player_index,
        deck_sha256=("f" * 64, prefix.deck_sha256[1]),
        deck_card_ids=(tuple([2] * 60), prefix.deck_card_ids[1]),
    )
    assert choose_dragapult_teacher(wrong, policy=policy, elite_teachers=teachers) is None


def test_teacher_score_tiers_preserve_curriculum_signal() -> None:
    assert quality_tier(1210.0) == ("elite_1200", 1.35)
    assert quality_tier(1160.0) == ("elite_1150", 1.25)
    assert quality_tier(1130.0) == ("elite_1120", 1.15)
    assert quality_tier(1090.0) == ("high_1090", 1.0)
    assert quality_tier(1089.9) == ("below_teacher_floor", 0.0)
