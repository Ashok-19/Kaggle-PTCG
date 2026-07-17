from __future__ import annotations

from typing import Any


def player(hand: list[dict[str, Any]] | None) -> dict[str, Any]:
    return {
        "active": [],
        "bench": [],
        "benchMax": 5,
        "deckCount": 46,
        "discard": [],
        "prize": [None] * 6,
        "handCount": 7,
        "hand": hand,
        "poisoned": False,
        "burned": False,
        "asleep": False,
        "paralyzed": False,
        "confused": False,
    }


def raw_observation(
    *, result: int = -1, options: list[dict[str, Any]] | None = None,
    min_count: int = 1, max_count: int = 1,
) -> dict[str, Any]:
    choices = options if options is not None else [{"type": 1}, {"type": 2}]
    return {
        "search_begin_input": "excluded-search-state",
        "select": {
            "type": 9,
            "context": 41,
            "minCount": min_count,
            "maxCount": max_count,
            "remainDamageCounter": 0,
            "remainEnergyCost": 0,
            "option": choices,
            "deck": None,
            "contextCard": None,
            "effect": None,
        },
        "logs": [{"type": 2, "playerIndex": 0}],
        "current": {
            "turn": 1,
            "turnActionCount": 1,
            "yourIndex": 0,
            "firstPlayer": 0,
            "supporterPlayed": False,
            "stadiumPlayed": False,
            "energyAttached": False,
            "retreated": False,
            "result": result,
            "stadium": [],
            "looking": None,
            "players": [player([]), player(None)],
        },
    }
