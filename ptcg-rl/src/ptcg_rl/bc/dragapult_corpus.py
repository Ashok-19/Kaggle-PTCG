from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ptcg_rl.bc.source import ReplayPrefixRecord


DOMINANT_DRAGAPULT_DECK_SHA256 = (
    "89e6155f25310ee695c0761c85d3ae8e44f376456ff0539231820f8e803f2d5e"
)
DRAGAPULT_EX_CARD_ID = 121
CURRENT_REPLAY_MODULE_VERSION = "1.32.6"


@dataclass(frozen=True)
class EliteTeacher:
    team_name: str
    rank: int
    score: float


@dataclass(frozen=True)
class DragapultCorpusPolicy:
    target_deck_sha256: str = DOMINANT_DRAGAPULT_DECK_SHA256
    module_version: str = CURRENT_REPLAY_MODULE_VERSION
    teacher_score_floor: float = 1090.0
    archetype_wide: bool = False

    def __post_init__(self) -> None:
        if len(self.target_deck_sha256) != 64:
            raise ValueError("target deck SHA-256 must have 64 hexadecimal characters")
        int(self.target_deck_sha256, 16)
        if self.teacher_score_floor <= 0:
            raise ValueError("teacher score floor must be positive")
        if not self.module_version:
            raise ValueError("module version cannot be empty")


def quality_tier(teacher_score: float) -> tuple[str, float]:
    """Return a teacher-score tier and retained future curriculum weight."""

    if teacher_score >= 1200.0:
        return "elite_1200", 1.35
    if teacher_score >= 1150.0:
        return "elite_1150", 1.25
    if teacher_score >= 1120.0:
        return "elite_1120", 1.15
    if teacher_score >= 1090.0:
        return "high_1090", 1.0
    if teacher_score >= 1050.0:
        return "coverage_1050", 0.85
    return "below_teacher_floor", 0.0


def choose_dragapult_teacher(
    prefix: ReplayPrefixRecord,
    *,
    policy: DragapultCorpusPolicy,
    elite_teachers: Mapping[str, EliteTeacher],
) -> tuple[int, str] | None:
    """Choose one qualified exact-deck teacher perspective for an episode.

    Outcome and opponent score are deliberately not admission criteria. If both
    seats are qualified exact-deck teachers in a mirror match, prefer the winner
    to preserve the one-record-per-episode contract used by materialization.
    """

    if prefix.module_version != policy.module_version:
        return None
    candidates: list[int] = []
    for seat in (0, 1):
        if policy.archetype_wide:
            if DRAGAPULT_EX_CARD_ID not in prefix.deck_card_ids[seat]:
                continue
        elif prefix.deck_sha256[seat] != policy.target_deck_sha256:
            continue
        teacher = elite_teachers.get(prefix.team_names[seat])
        if teacher is not None and teacher.score >= policy.teacher_score_floor:
            candidates.append(seat)
    if not candidates:
        return None
    winner = prefix.winner_player_index
    teacher_seat = winner if winner in candidates else candidates[0]
    return teacher_seat, "frozen_live_teacher_score"
