from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class SearchBudgetPolicy:
    """Allocate expensive compute only to genuinely branching MAIN decisions."""

    trivial_seconds: float = 0.0
    normal_seconds: float = 0.25
    important_seconds: float = 1.0
    critical_seconds: float = 4.0
    reserve_overage_seconds: float = 120.0

    def budget(self, observation: Mapping[str, object]) -> float:
        current = observation.get("current")
        select = observation.get("select")
        if not isinstance(current, Mapping) or not isinstance(select, Mapping):
            return self.trivial_seconds
        if int(current.get("result", -1)) != -1:
            return self.trivial_seconds
        if int(select.get("type", -1)) != 0:
            return self.trivial_seconds

        options = select.get("option")
        option_count = len(options) if isinstance(options, list) else 0
        if option_count < 2:
            return self.trivial_seconds

        # CABT supplies this at the top observation level in hosted episodes.
        overage_raw = observation.get("remainingOverageTime")
        if isinstance(overage_raw, (int, float)):
            available = max(0.0, float(overage_raw) - self.reserve_overage_seconds)
        else:
            available = self.critical_seconds

        prizes = current.get("players")
        own_prizes = None
        if isinstance(prizes, list):
            your_index = current.get("yourIndex")
            if isinstance(your_index, int) and 0 <= your_index < len(prizes):
                player = prizes[your_index]
                if isinstance(player, Mapping):
                    prize_zone = player.get("prize")
                    if isinstance(prize_zone, list):
                        own_prizes = len(prize_zone)

        if own_prizes is not None and own_prizes <= 2 and option_count >= 4:
            requested = self.critical_seconds
        elif option_count >= 8:
            requested = self.important_seconds
        else:
            requested = self.normal_seconds
        return max(self.trivial_seconds, min(requested, available))
