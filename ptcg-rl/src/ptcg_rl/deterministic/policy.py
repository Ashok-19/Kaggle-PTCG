"""Phase B policy entry point for the public deterministic controller."""

from __future__ import annotations

from .control import MegaAbomasnowControl


class DeterministicStrategicPolicy(MegaAbomasnowControl):
    """Named PolicyV1-compatible entry point used by Phase B harnesses.

    The first Phase B candidate is intentionally bound to the exact Mega
    Abomasnow deck.  The base class contains all public-boundary, lifecycle,
    compound-action, and control scoring logic.
    """

    policy_id = "deterministic-strategic-mega-abomasnow-v1"


__all__ = ["DeterministicStrategicPolicy"]
