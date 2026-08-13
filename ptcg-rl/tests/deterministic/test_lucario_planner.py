from __future__ import annotations

from ptcg_rl.decision_engine import LucarioPhase, LucarioStrategicPlanner


def _pokemon(card_id: int, energy: int = 0, hp: int = 100, max_hp: int = 100):
    return {
        "id": card_id,
        "serial": card_id * 10 + energy,
        "hp": hp,
        "maxHp": max_hp,
        "energies": [1] * energy,
        "energyCards": [],
        "tools": [],
        "preEvolution": [],
    }


def _obs(
    *,
    deck=30,
    prizes=4,
    hand_ids=(),
    active=None,
    bench=(),
    options=(),
    supporter_played=False,
    energy_attached=False,
):
    hand = [{"id": card_id, "serial": 1000 + i} for i, card_id in enumerate(hand_ids)]
    return {
        "current": {
            "turn": 4,
            "turnActionCount": 3,
            "yourIndex": 0,
            "result": -1,
            "supporterPlayed": supporter_played,
            "energyAttached": energy_attached,
            "retreated": False,
            "players": [
                {
                    "active": [] if active is None else [active],
                    "bench": list(bench),
                    "hand": hand,
                    "handCount": len(hand),
                    "discard": [],
                    "deckCount": deck,
                    "prize": [None] * prizes,
                },
                {
                    "active": [_pokemon(900, 0, 150, 150)],
                    "bench": [],
                    "hand": None,
                    "handCount": 5,
                    "discard": [],
                    "deckCount": 30,
                    "prize": [None] * 4,
                },
            ],
        },
        "select": {"context": 0, "type": 0, "option": list(options), "minCount": 1, "maxCount": 1},
        "logs": [],
    }


def _play(hand_index: int):
    return {"type": 7, "index": hand_index}


def _ability(area=4, index=0):
    return {"type": 10, "area": area, "index": index}


def _evolve(hand_index: int, area=4, index=0):
    return {"type": 9, "index": hand_index, "inPlayArea": area, "inPlayIndex": index}


def _attach(hand_index: int, area=4, index=0):
    return {"type": 8, "index": hand_index, "inPlayArea": area, "inPlayIndex": index}


def _attack(attack_id: int):
    return {"type": 13, "attackId": attack_id}


def test_deck_preserve_vetoes_optional_lunar_and_ultra():
    planner = LucarioStrategicPlanner()
    obs = _obs(
        deck=9,
        prizes=4,
        hand_ids=(6, 1121),
        active=_pokemon(675),
        bench=(_pokemon(676),),
        options=(_ability(), _play(1)),
    )
    intent = planner.plan(obs)
    assert intent.phase is LucarioPhase.DECK_PRESERVE
    assert not intent.allow_lunar_cycle
    assert not intent.allow_ultra_ball


def test_mega_evolution_precedes_lunar_and_ultra():
    planner = LucarioStrategicPlanner()
    obs = _obs(
        hand_ids=(6, 678, 1121),
        active=_pokemon(677, 1),
        bench=(_pokemon(675), _pokemon(676)),
        options=(_ability(5, 0), _evolve(1), _play(2)),
    )
    intent = planner.plan(obs)
    assert intent.phase is LucarioPhase.BUILD_ATTACKER
    assert intent.prioritize_mega_evolution
    assert not intent.allow_lunar_cycle
    assert not intent.allow_ultra_ball


def test_threshold_crossing_attachment_precedes_refresh_tools():
    planner = LucarioStrategicPlanner()
    obs = _obs(
        hand_ids=(6, 1121),
        active=_pokemon(675),
        bench=(_pokemon(674, 2), _pokemon(676)),
        options=(_ability(), _attach(0, 5, 0), _play(1)),
    )
    intent = planner.plan(obs)
    assert intent.phase is LucarioPhase.BUILD_ATTACKER
    assert intent.prioritize_route_attachment
    assert not intent.allow_lunar_cycle
    assert not intent.allow_ultra_ball


def test_attack_commit_is_selected_after_chain_is_ready():
    planner = LucarioStrategicPlanner()
    obs = _obs(
        hand_ids=(6,),
        active=_pokemon(678, 1, 340, 340),
        bench=(_pokemon(674, 3, 150, 150),),
        options=(_attack(982),),
    )
    intent = planner.plan(obs)
    assert intent.phase is LucarioPhase.TRADE
    assert intent.prefer_attack_commit


def test_wally_recovery_phase_precedes_trade_on_damaged_mega():
    planner = LucarioStrategicPlanner()
    obs = _obs(
        hand_ids=(1229,),
        active=_pokemon(678, 1, 170, 340),
        bench=(_pokemon(674, 3, 150, 150),),
        options=(_play(0), _attack(982)),
    )
    intent = planner.plan(obs)
    assert intent.phase is LucarioPhase.RECOVER
    assert intent.prefer_wally
    assert not intent.prefer_attack_commit


def test_ultra_is_allowed_only_for_missing_route_role():
    planner = LucarioStrategicPlanner()
    obs = _obs(
        hand_ids=(1121,),
        active=_pokemon(677, 0, 80, 80),
        options=(_play(0),),
    )
    intent = planner.plan(obs)
    assert intent.phase is LucarioPhase.SETUP
    assert intent.allow_ultra_ball

    obs = _obs(
        hand_ids=(1121,),
        active=_pokemon(678, 1, 340, 340),
        bench=(_pokemon(674, 3, 150, 150),),
        options=(_play(0), _attack(982)),
    )
    intent = planner.plan(obs)
    assert intent.phase is LucarioPhase.TRADE
    assert not intent.allow_ultra_ball
