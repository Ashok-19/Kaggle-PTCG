from __future__ import annotations

from ptcg_rl.bc.dragapult_corpus import (
    DOMINANT_DRAGAPULT_DECK_SHA256,
    DragapultCorpusPolicy,
    EliteTeacher,
    choose_dragapult_winner_teacher,
    quality_tier,
)
from ptcg_rl.bc.source import ReplayPrefixRecord, ReplayQualityRecord


def _quality(score: float) -> ReplayQualityRecord:
    return ReplayQualityRecord(
        episode_id=1,
        create_time="2026-08-13T00:00:00Z",
        avg_score=score + 10.0,
        min_score=score,
        sum_score=2.0 * score + 20.0,
        agent_count=2,
        size_bytes=1234,
    )


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


def test_score_floor_admits_exact_deck_winner() -> None:
    result = choose_dragapult_winner_teacher(
        _prefix(winner=1),
        _quality(950.0),
        policy=DragapultCorpusPolicy(),
        elite_teachers={},
    )
    assert result == (1, "score_floor")


def test_live_top20_rescue_is_narrow_and_winner_only() -> None:
    elites = {"elite": EliteTeacher(team_name="elite", rank=3, score=1188.3)}
    policy = DragapultCorpusPolicy()
    assert choose_dragapult_winner_teacher(
        _prefix(team="elite"), _quality(925.0), policy=policy, elite_teachers=elites
    ) == (0, "live_top20_rescue")
    assert choose_dragapult_winner_teacher(
        _prefix(team="ordinary"), _quality(925.0), policy=policy, elite_teachers=elites
    ) is None
    assert choose_dragapult_winner_teacher(
        _prefix(team="elite"), _quality(899.9), policy=policy, elite_teachers=elites
    ) is None


def test_wrong_module_or_wrong_deck_is_rejected() -> None:
    policy = DragapultCorpusPolicy()
    assert choose_dragapult_winner_teacher(
        _prefix(module="1.32.5"), _quality(1200.0), policy=policy, elite_teachers={}
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
        wrong, _quality(1200.0), policy=policy, elite_teachers={}
    ) is None


def test_quality_tiers_preserve_curriculum_signal() -> None:
    assert quality_tier(1160.0) == ("elite_1150", 1.35)
    assert quality_tier(1110.0) == ("elite_1100", 1.25)
    assert quality_tier(1060.0) == ("high_1050", 1.15)
    assert quality_tier(1010.0) == ("high_1000", 1.05)
    assert quality_tier(960.0) == ("solid_950", 1.0)
    assert quality_tier(925.0) == ("top20_rescue_900", 0.9)
