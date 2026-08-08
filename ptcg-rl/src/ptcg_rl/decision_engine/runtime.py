from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

from .budget import SearchBudgetPolicy
from .memory import PublicGameMemory
from .search import SearchSuggestion, ShadowSolver

Policy = Callable[[dict], list[int]]


@dataclass
class RuntimeDiagnostics:
    calls: int = 0
    shadow_calls: int = 0
    shadow_suggestions: int = 0
    shadow_disagreements: int = 0
    shadow_failures: int = 0
    last_suggestion: SearchSuggestion | None = None


class DecisionEngineRuntime:
    """Own one CABT battle session and preserve fallback behavior in shadow mode."""

    def __init__(
        self,
        fallback_policy: Policy,
        *,
        shadow_solver: ShadowSolver | None = None,
        budget_policy: SearchBudgetPolicy | None = None,
    ) -> None:
        self._fallback_policy = fallback_policy
        self._shadow_solver = shadow_solver
        self._budget_policy = budget_policy or SearchBudgetPolicy()
        self.memory = PublicGameMemory()
        self.diagnostics = RuntimeDiagnostics()

    def reset(self) -> None:
        self.memory.reset()
        self.diagnostics.last_suggestion = None

    def act(self, observation: dict) -> list[int]:
        self.diagnostics.calls += 1
        current = observation.get("current")
        select = observation.get("select")

        # Deck/start requests have no battle state. They are also the cleanest
        # process-local reset boundary before delegating to the exact fallback.
        if not isinstance(current, Mapping):
            self.reset()
            return self._fallback_policy(observation)

        self.memory.ingest(observation)
        fallback_action = self._fallback_policy(observation)
        if self._shadow_solver is None or not self._eligible_for_shadow(current, select):
            return fallback_action

        budget = self._budget_policy.budget(observation)
        if budget <= 0.0:
            return fallback_action

        self.diagnostics.shadow_calls += 1
        try:
            suggestion = self._shadow_solver.suggest(
                observation,
                self.memory,
                budget,
                fallback_action,
            )
        except Exception:
            # Search is deliberately shadow-only at this milestone. A failed
            # diagnostic search must never break or alter the competition action.
            self.diagnostics.shadow_failures += 1
            return fallback_action

        self.diagnostics.last_suggestion = suggestion
        if suggestion is not None:
            self.diagnostics.shadow_suggestions += 1
            if tuple(suggestion.action) != tuple(fallback_action):
                self.diagnostics.shadow_disagreements += 1
        return fallback_action

    @staticmethod
    def _eligible_for_shadow(current: Mapping[str, object], select: object) -> bool:
        if int(current.get("result", -1)) != -1 or not isinstance(select, Mapping):
            return False
        if int(select.get("type", -1)) != 0:
            return False
        options = select.get("option")
        return isinstance(options, list) and len(options) >= 2

    def shadow_disagreement_rate(self) -> float:
        if self.diagnostics.shadow_suggestions == 0:
            return 0.0
        return self.diagnostics.shadow_disagreements / self.diagnostics.shadow_suggestions

    def known_opponent_hand_ids(self) -> Sequence[int]:
        return self.memory.known_opponent_hand_ids()
