from __future__ import annotations

from collections import Counter

from ptcg_rl.decision_engine import ArchetypeRegistry, DeckTemplate, PublicGameMemory


def _deck(*special: int) -> tuple[int, ...]:
    cards = list(special)
    cards.extend([6] * (60 - len(cards)))
    return tuple(cards)


def test_unique_public_card_memory_does_not_double_count_same_serial():
    memory = PublicGameMemory()
    memory.ingest(
        {
            "current": {
                "turn": 3,
                "turnActionCount": 2,
                "yourIndex": 0,
                "result": -1,
                "players": [
                    {"active": [], "bench": [], "discard": []},
                    {
                        "active": [
                            {
                                "id": 743,
                                "serial": 91,
                                "energyCards": [],
                                "tools": [],
                                "preEvolution": [],
                            }
                        ],
                        "bench": [],
                        "discard": [],
                    },
                ],
                "stadium": [],
            },
            "logs": [
                {"type": 10, "playerIndex": 1, "cardId": 743, "serial": 91},
                {"type": 15, "playerIndex": 1, "cardId": 743, "serial": 91, "attackId": 7001},
            ],
        }
    )
    assert memory.opponent_observed_card_counts() == Counter({743: 1})
    assert memory.opponent_seen_cards[743] == 2


def test_registry_keeps_sparse_shared_evidence_broad():
    registry = ArchetypeRegistry(
        [
            DeckTemplate("alpha", _deck(100, 101), frozenset({100})),
            DeckTemplate("beta", _deck(200, 201), frozenset({200})),
        ]
    )
    ranked = registry.rank({6: 1})
    assert ranked[0].normalized_weight == ranked[1].normalized_weight == 0.5
    assert registry.qualified_template({6: 1}) is None


def test_registry_qualifies_distinct_signature_evidence():
    alpha = DeckTemplate("alpha", _deck(100, 101, 102), frozenset({100, 101}))
    beta = DeckTemplate("beta", _deck(200, 201, 102), frozenset({200, 201}))
    registry = ArchetypeRegistry([alpha, beta])
    ranked = registry.rank({100: 1, 101: 1, 102: 1})
    assert ranked[0].name == "alpha"
    assert ranked[0].signature_hits == 2
    assert registry.qualified_template({100: 1, 101: 1, 102: 1}) == alpha


def test_copy_count_contradiction_eliminates_template():
    alpha = DeckTemplate("alpha", _deck(100, 100), frozenset({100}))
    beta = DeckTemplate("beta", _deck(100, 100, 100, 100), frozenset({100}))
    registry = ArchetypeRegistry([alpha, beta])
    ranked = registry.rank({100: 3})
    by_name = {row.name: row for row in ranked}
    assert not by_name["alpha"].compatible
    assert by_name["alpha"].normalized_weight == 0.0
    assert by_name["beta"].compatible
    assert by_name["beta"].normalized_weight == 1.0


def test_known_hand_reveal_is_also_unique_archetype_evidence():
    memory = PublicGameMemory()
    memory.ingest(
        {
            "current": {
                "turn": 2,
                "turnActionCount": 4,
                "yourIndex": 0,
                "result": -1,
                "players": [
                    {"active": [], "bench": [], "discard": []},
                    {"active": [], "bench": [], "discard": []},
                ],
                "stadium": [],
            },
            "logs": [
                {
                    "type": 6,
                    "playerIndex": 1,
                    "cardId": 743,
                    "serial": 91,
                    "fromArea": 1,
                    "toArea": 2,
                }
            ],
        }
    )
    assert memory.known_opponent_hand_ids() == (743,)
    assert memory.opponent_observed_card_counts() == Counter({743: 1})
