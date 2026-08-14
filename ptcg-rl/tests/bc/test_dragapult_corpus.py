from __future__ import annotations

from ptcg_rl.bc.dragapult_corpus import (
    DOMINANT_DRAGAPULT_DECK_SHA256,
    DragapultCorpusPolicy,
    EliteTeacher,
    choose_dragapult_winner_teacher,
    quality_tier,
)
from ptcg_rl.bc.source import ReplayPrefixRecord


def _prefix(*, winner: int = 0, team: str = "teacher", module: str = "1.32.6") -> ReplayPrefixRecord:
    rewards = (1, -1) if winner == 0 else (-1, 1)
    hashes = ["0" * 64, "1" * 64]
    hashes[winner] = DOMINANT_DRAGAPULT_DECK_SHA256
    teams = ["opponent", "opponent"]
    teams[winner] = team
    return ReplayPrefixRecord(
        team_names=(teams[0], teams[1]),
        module_version=module,
        rewards=rewards,
        winner_player_index=winner,
        deck_sha256=(hashes[0], hashes[1]),
    )


def test_qualified_teacher_exact_deck_winner_is_admitted() -> None:
    teachers = {"teacher": EliteTeacher(team_name="teacher", rank=10, score=1153.3)}
    result = choose_dragapult_winner_teacher(
        _prefix(winner=1),
        policy=DragapultCorpusPolicy(),
        elite_teachers=teachers,
    )
    assert result == (1, "frozen_live_teacher_score")


def test_teacher_floor_is_1090_and_opponent_score_is_irrelevant() -> None:
    policy = DragapultCorpusPolicy()
    assert choose_dragapult_winner_teacher(
        _prefix(team="qualified"),
        policy=policy,
        elite_teachers={
            "qualified": EliteTeacher(team_name="qualified", rank=20, score=1090.0)
        },
    ) == (0, "frozen_live_teacher_score")
    assert choose_dragapult_winner_teacher(
        _prefix(team="weak"),
        policy=policy,
        elite_teachers={"weak": EliteTeacher(team_name="weak", rank=21, score=1089.9)},
    ) is None


def test_wrong_module_or_wrong_deck_is_rejected() -> None:
    policy = DragapultCorpusPolicy()
    teachers = {"teacher": EliteTeacher(team_name="teacher", rank=1, score=1217.0)}
    assert choose_dragapult_winner_teacher(
        _prefix(module="1.32.5"), policy=policy, elite_teachers=teachers
    ) is None
    prefix = _prefix()
    wrong = ReplayPrefixRecord(
        team_names=prefix.team_names,
        module_version=prefix.module_version,
        rewards=prefix.rewards,
        winner_player_index=prefix.winner_player_index,
        deck_sha256=("f" * 64, prefix.deck_sha256[1]),
    )
    assert choose_dragapult_winner_teacher(
        wrong, policy=policy, elite_teachers=teachers
    ) is None


def test_teacher_score_tiers_preserve_curriculum_signal() -> None:
    assert quality_tier(1210.0) == ("elite_1200", 1.35)
    assert quality_tier(1160.0) == ("elite_1150", 1.25)
    assert quality_tier(1130.0) == ("elite_1120", 1.15)
    assert quality_tier(1090.0) == ("high_1090", 1.0)
    assert quality_tier(1089.9) == ("below_teacher_floor", 0.0)
