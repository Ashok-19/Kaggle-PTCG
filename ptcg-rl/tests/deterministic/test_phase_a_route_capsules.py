from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from scripts.deterministic.phase_a_route_capsules_v1 import (
    DEFAULT_CONFIG,
    ProbePolicy,
    _record_proof,
    _route_verdict,
    _new_route_state,
    expand_deck,
    load_config,
)
from ptcg_rl.g1.models import (
    CONTRACT_VERSION,
    EngineObservationV1,
    LegalOptionV1,
    PlayerViewV1,
    PublicEventV1,
    SelectionRequestV1,
    VisibleEntityV1,
)

REPORT = Path(__file__).resolve().parents[2] / "reports/deterministic/phase-a-route-capsules-v1.json"


def _observation() -> EngineObservationV1:
    return EngineObservationV1(
        schema_version=CONTRACT_VERSION,
        battle_id="capsule-test",
        transition_id=0,
        acting_player=0,
        terminal_result=None,
        turn=1,
        turn_action_count=0,
        first_player=0,
        supporter_played=False,
        stadium_played=False,
        energy_attached=False,
        retreated=False,
        players=(
            PlayerViewV1(0, 5, 40, 2, 6, 0, True, 0),
            PlayerViewV1(1, 5, 40, 2, 6, 0, False, 0),
        ),
        entities=(
            VisibleEntityV1("p0:s1", 721, 1, "card:721", 0, 2, 0),
            VisibleEntityV1("p0:s2", 3, 2, "card:3", 0, 2, 1),
        ),
        public_events=(PublicEventV1(0, "SHUFFLE", {}),),
    )


def _request(options: tuple[LegalOptionV1, ...], *, selection_type: int = 0, selection_context: int = 0, min_count: int = 1, max_count: int = 1) -> SelectionRequestV1:
    return SelectionRequestV1(
        schema_version=CONTRACT_VERSION,
        episode_uuid="capsule-test",
        selection_seq=0,
        request_id="request",
        acting_player=0,
        selection_type=selection_type,
        selection_context=selection_context,
        min_count=min_count,
        max_count=max_count,
        remain_damage_counter=None,
        remain_energy_cost=None,
        context_card_id=None,
        effect_card_id=None,
        ordering="UNORDERED",
        options=options,
    )


def _option(index: int, *, option_type: int, attack_id: int | None = None, source: str | None = None, card_id: int | None = None, selection_type: int = 0, selection_context: int = 0) -> LegalOptionV1:
    return LegalOptionV1(
        schema_version=CONTRACT_VERSION,
        original_index=index,
        selection_type=selection_type,
        selection_context=selection_context,
        option_type=option_type,
        option_name={5: "ENERGY_CARD", 7: "PLAY", 13: "ATTACK", 14: "END"}[option_type],
        attack_id=attack_id,
        card_id=card_id,
        source_entity_key=source,
        semantic_fingerprint=f"fingerprint-{index}",
    )


def test_route_config_decks_are_legal_sized_and_repository_scoped() -> None:
    config = load_config(DEFAULT_CONFIG)
    assert sum(config["limits"].values()) > 0
    for spec in config["deck_specs"].values():
        assert len(expand_deck(spec)) == 60
        assert all(int(card_id) == 3 or count <= 4 for card_id, count in spec.items())


def test_probe_selects_target_attack_over_end() -> None:
    policy = ProbePolicy("swirling_waves")
    request = _request(
        (
            _option(0, option_type=13, attack_id=1042),
            _option(1, option_type=13, attack_id=1043),
            _option(2, option_type=14),
        )
    )
    action = policy.choose(_observation(), request)
    assert action.submitted_original_indices == (1,)


def test_probe_handles_ordered_energy_selection_without_private_state() -> None:
    policy = ProbePolicy("swirling_waves")
    options = tuple(
        replace(
                _option(index, option_type=5, source="p0:s2", selection_type=4, selection_context=30),
                source_entity_key="p0:s2",
        )
        for index in range(2)
    )
    request = replace(_request(options, selection_type=4, selection_context=30, min_count=2, max_count=2), ordering="UNORDERED")
    action = policy.choose(_observation(), request)
    assert action.submitted_original_indices == (0, 1)
    assert not action.stopped_early


def test_probe_optional_request_stops_explicitly() -> None:
    policy = ProbePolicy(None)
    request = _request((_option(0, option_type=13, attack_id=1042), _option(1, option_type=13, attack_id=1043)), min_count=0, max_count=1)
    action = policy.choose(_observation(), request)
    assert action.stopped_early
    assert action.submitted_original_indices == ()


def test_route_state_starts_empty_and_capsule_does_not_claim_strength() -> None:
    state = _new_route_state()
    assert state["attempts"] == 0
    assert not state["proofs"]
    assert not state["proof_keys"]


def test_duplicate_direct_and_pending_observations_count_one_attack() -> None:
    state = _new_route_state()
    payload = {"attack_events": [{"fields": {"playerIndex": 0, "serial": 9, "attackId": 1046}}], "stratum": "zero", "water_count": 0}
    assert _record_proof(state, "hammer_lanche", 0, 12, "hammer_six_top_discard_and_damage", payload)
    assert not _record_proof(state, "hammer_lanche", 0, 12, "hammer_six_top_discard_and_damage", payload)
    assert state["proofs"] == {"hammer_six_top_discard_and_damage": 1}
    assert state["strata"] == {"zero": 1}


def test_surfing_verdict_requires_same_game_player_and_ordered_causal_pair() -> None:
    state = _new_route_state()
    state["evidence"] = [
        {"proof": "surfing_beach_play", "game_index": 0, "acting_player": 0, "turn": 3, "stadium_serials": [1]},
        {"proof": "surfing_beach_water_switch", "game_index": 1, "acting_player": 0, "turn": 4, "all_water_targets": True},
    ]
    assert _route_verdict("surfing_beach", state)[0] == "PARTIAL"
    state["evidence"][1]["game_index"] = 0
    assert _route_verdict("surfing_beach", state)[0] == "PASS"


def test_retained_route_report_is_sanitized_and_fail_closed() -> None:
    if not REPORT.is_file():
        return
    report_text = REPORT.read_text(encoding="utf-8")
    report = json.loads(report_text)
    assert report["status"] == "SUCCEEDED"
    assert all(value == 0 for value in report["fail_closed_counters"].values())
    assert report["route_results"]["riptide"]["status"] in {"PASS", "PARTIAL"}
    assert report["route_results"]["swirling_waves"]["status"] == "PASS"
    assert report["route_results"]["surfing_beach"]["status"] == "PASS"
    assert report["route_results"]["hammer_lanche"]["status"] == "PASS"
    assert report["route_results"]["frost_barrier"]["status"] == "PARTIAL"
    assert report["raw_evidence"]["sealed_read_only"] is True
    assert report["raw_evidence"]["path"].startswith("runs/")
    assert "capsules" not in report["route_results"]["riptide"]
    assert report["raw_evidence"]["bytes"] > 0
    assert report["scope"]["games_requested"] == 120
    assert report["scope"]["games_completed"] == 120
    assert all(value == 0 for value in report["fail_closed_counters"].values())
    assert report["route_results"]["surfing_beach"]["proofs"]["surfing_beach_play"] > 0
    assert len(report_text) < 250_000
    assert str(Path(__file__).resolve().parents[2]) not in report_text
    assert "/tmp" not in report_text
