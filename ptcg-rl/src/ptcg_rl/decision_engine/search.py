from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence

from .memory import PublicGameMemory


@dataclass(frozen=True)
class SearchSuggestion:
    """A shadow-search result expressed in CABT option indices."""

    action: tuple[int, ...]
    value: float | None = None
    nodes: int = 0
    elapsed_seconds: float = 0.0
    reason: str = ""


class ShadowSolver(Protocol):
    """Interface used by the runtime while search is still non-authoritative."""

    def suggest(
        self,
        observation: Mapping[str, object],
        memory: PublicGameMemory,
        budget_seconds: float,
        fallback_action: Sequence[int],
    ) -> SearchSuggestion | None: ...
