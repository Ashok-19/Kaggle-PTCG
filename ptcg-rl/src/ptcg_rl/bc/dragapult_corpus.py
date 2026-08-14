from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from ptcg_rl.bc.source import ReplayPrefixRecord, ReplayQualityRecord


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
    base_min_score: float = 1090.0
    elite_rescue_min_score: float = 1090.0

    def __post_init__(self) -> None:
        if len(self.target_deck_sha256) != 64:
            raise ValueError("target deck SHA-256 must have 64 hexadecimal characters")
        int(self.target_deck_sha256, 16)
        if self.base_min_score <= 0 or self.elite_rescue_min_score <= 0:
            raise ValueError("score floors must be positive")
        if self.elite_rescue_min_score > self.base_min_score:
            raise ValueError("elite rescue floor cannot exceed the base score floor")
        if not self.module_version:
            raise ValueError("module version cannot be empty")


def quality_tier(min_score: float) -> tuple[str, float]:
    """Return a retained quality tier and future training weight.

    The current trainer does not consume this weight yet. It is retained in the
    corpus manifest so later training can use a quality curriculum without
    rebuilding or rereading raw public replay datasets.
    """

    if min_score >= 1200.0:
        return "elite_1200", 1.35
    if min_score >= 1150.0:
        return "elite_1150", 1.25
    if min_score >= 1120.0:
        return "elite_1120", 1.15
    if min_score >= 1090.0:
        return "high_1090", 1.0
    return "below_production_floor", 0.0


def choose_dragapult_winner_teacher(
    prefix: ReplayPrefixRecord,
    quality: ReplayQualityRecord,
    *,
    policy: DragapultCorpusPolicy,
    elite_teachers: Mapping[str, EliteTeacher],
) -> tuple[int, str] | None:
    """Admit only winning teachers using the exact canonical Dragapult list."""

    if prefix.module_version != policy.module_version:
        return None
    winner = prefix.winner_player_index
    if winner not in (0, 1):
        return None
    if prefix.deck_sha256[winner] != policy.target_deck_sha256:
        return None
    if quality.min_score >= policy.base_min_score:
        return winner, "score_floor"
    teacher_name = prefix.team_names[winner]
    if (
        teacher_name in elite_teachers
        and quality.min_score >= policy.elite_rescue_min_score
    ):
        return winner, "live_top20_rescue"
    return None
