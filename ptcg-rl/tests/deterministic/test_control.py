from __future__ import annotations

from dataclasses import replace

import pytest

from ptcg_rl.deterministic.control import (
    FROZEN_CONTROL_REPRODUCTION,
    FROST_BARRIER,
    KYOGRE,
    MEGA_ABOMASNOW_EX,
    MegaAbomasnowControl,
    RIPTIDE,
    SNOVER,
    ULTRA_BALL,
    SWIRLING_WAVES,
)
from ptcg_rl.g1.models import (
    CONTRACT_VERSION,
    ContractViolation,
    EngineObservationV1,
    LegalOptionV1,
    PlayerViewV1,
    SelectionRequestV1,
    VisibleEntityV1,
    stable_hash,
)
from ptcg_rl.g1.semantic import AREA, OPTION_NAMES


CARD_HASH = "c" * 64


def entity(card_id: int, serial: int, owner: int = 0, zone: int = AREA["HAND"], position: int = 0, energy: int = 0):
    return VisibleEntityV1(
        entity_key=f"p{owner}:s{serial}",
        card_id=card_id,
        serial=serial,
        metadata_ref=f"card:{card_id}@{CARD_HASH}",
        owner=owner,
        zone=zone,
        position=position,
        hp=100 if zone in {AREA["ACTIVE"], AREA["BENCH"]} else None,
        max_hp=100 if zone in {AREA["ACTIVE"], AREA["BENCH"]} else None,
        damage=0 if zone in {AREA["ACTIVE"], AREA["BENCH"]} else None,
        energy_types=(3,) * energy,
        attached_energy_count=energy,
    )


def observation(entities=(), *, transition: int = 0, actor: int = 0):
    return EngineObservationV1(
        schema_version=CONTRACT_VERSION,
        battle_id="control-test",
        transition_id=transition,
        acting_player=actor,
        terminal_result=None,
        turn=1,
        turn_action_count=0,
        first_player=0,
        supporter_played=False,
        stadium_played=False,
        energy_attached=False,
        retreated=False,
        players=(
            PlayerViewV1(0, 5, 30, 4, 6, 0, actor == 0, 0),
            PlayerViewV1(1, 5, 30, 4, 6, 0, actor == 1, 0),
        ),
        entities=tuple(entities),
        public_events=(),
    )


def option(option_type: int, *, source=None, target=None, index: int = 0, attack_id=None):
    source_kind = "ENTITY" if source is not None else "NONE"
    target_kind = "ENTITY" if target is not None else "NONE"
    owner = int(source.split(":", 1)[0][1:]) if isinstance(source, str) and source.startswith("p") else 0
    row = LegalOptionV1(
        schema_version=CONTRACT_VERSION,
        original_index=index,
        selection_type=0,
        selection_context=0,
        option_type=option_type,
        option_name=OPTION_NAMES[option_type],
        area=AREA["HAND"] if option_type in {3, 4, 5, 6, 8, 9, 10, 11} else None,
        index=index if option_type in {3, 4, 5, 6, 7, 8, 9, 10, 11} else None,
        player_index=owner if option_type in {3, 4, 5, 6} else None,
        in_play_area=AREA["ACTIVE"] if option_type in {8, 9} else None,
        in_play_index=0 if option_type in {8, 9} else None,
        attack_id=attack_id,
        source_kind=source_kind,
        source_ref=source,
        target_kind=target_kind,
        target_ref=target,
        choice_role=OPTION_NAMES[option_type],
        source_entity_key=source,
        target_entity_key=target,
    )
    return replace(row, semantic_fingerprint=stable_hash(row.semantic_payload()))


def request(options, *, selection_type=0, context=0, min_count=1, max_count=1, transition=0, actor=0):
    rows = tuple(replace(item, selection_type=selection_type, selection_context=context) for item in options)
    rows = tuple(replace(item, semantic_fingerprint=stable_hash(item.semantic_payload())) for item in rows)
    return SelectionRequestV1(
        schema_version=CONTRACT_VERSION,
        episode_uuid="control-test",
        selection_seq=transition,
        request_id=f"request-{transition}-{stable_hash([item.semantic_fingerprint for item in rows])}",
        acting_player=actor,
        selection_type=selection_type,
        selection_context=context,
        min_count=min_count,
        max_count=max_count,
        remain_damage_counter=0,
        remain_energy_cost=0,
        context_card_id=None,
        effect_card_id=None,
        ordering="ORDERED" if selection_type == 5 and context == 34 else "UNORDERED",
        options=rows,
    )


def test_exact_deck_and_numeric_control_identity():
    policy = MegaAbomasnowControl()
    assert policy.deck == (
        721, 721, 722, 722, 722, 722, 723, 723, 723, 723,
        1121, 1121, 1121, 1121, 1126,
        1192, 1192, 1192, 1192, 1227, 1227, 1227, 1227,
        1262, 1262, 1262, *([3] * 34),
    )
    assert len(policy.deck) == 60
    assert policy.policy_id == "mega-abomasnow-public-control-v1"


def test_semantic_option_permutation_does_not_change_choice():
    carmine = entity(1192, 1)
    ultra = entity(ULTRA_BALL, 2)
    obs = observation((carmine, ultra))
    first = request((option(7, source=carmine.entity_key, index=0), option(7, source=ultra.entity_key, index=1)))
    second = request((option(7, source=ultra.entity_key, index=0), option(7, source=carmine.entity_key, index=1)))
    left = MegaAbomasnowControl()
    right = MegaAbomasnowControl()
    left.reset("control-test", 0)
    right.reset("control-test", 0)
    action_left = left.choose(obs, first)
    action_right = right.choose(obs, second)
    chosen_left = first.options[action_left.submitted_original_indices[0]].source_entity_key
    chosen_right = second.options[action_right.submitted_original_indices[0]].source_entity_key
    assert chosen_left == chosen_right


def test_forced_multiselect_and_explicit_stop_are_valid_compound_actions():
    water = entity(3, 1)
    snover = entity(SNOVER, 2)
    rows = (
        option(3, source=water.entity_key, index=0),
        option(3, source=snover.entity_key, index=1),
    )
    forced = request(rows, selection_type=1, context=8, min_count=2, max_count=2)
    policy = MegaAbomasnowControl()
    policy.reset("control-test", 0)
    action = policy.choose(observation((water, snover)), forced)
    assert len(action.submitted_original_indices) == 2
    assert not action.stopped_early

    optional = request((option(14, index=0),), selection_type=0, context=0, min_count=0, max_count=1)
    policy.reset("control-test", 0)
    stopped = policy.choose(observation((water,)), optional)
    assert stopped.stopped_early
    assert len(stopped.steps) == 1
    assert stopped.steps[0].chosen_token == "STOP"


def test_partial_card_route_is_explicitly_labelled_not_promoted():
    attacker = entity(KYOGRE, 1, zone=AREA["ACTIVE"], energy=1)
    opponent = entity(723, 9, owner=1, zone=AREA["ACTIVE"])
    attack = option(13, index=0, attack_id=RIPTIDE)
    req = request((attack,), selection_type=6, context=35)
    policy = MegaAbomasnowControl()
    policy.reset("control-test", 0)
    decision = policy.score_option(observation((attacker, opponent)), req, req.options[0])
    assert decision.route_label == FROZEN_CONTROL_REPRODUCTION
    assert policy.diagnostics.partial_route_decision_count == 0


def test_lifecycle_duplicate_is_idempotent_and_stale_is_rejected():
    yes = option(1)
    req0 = request((yes,), selection_type=9, transition=0)
    policy = MegaAbomasnowControl()
    policy.reset("control-test", 0)
    obs = observation(transition=0)
    first = policy.choose(obs, req0)
    assert policy.choose(obs, req0) == first
    assert policy.diagnostics.duplicate_request_count == 1
    with pytest.raises(ContractViolation, match="stale"):
        policy.choose(obs, replace(req0, request_id="different"))
    req2 = request((yes,), selection_type=9, transition=2)
    assert policy.choose(observation(transition=2), req2).submitted_original_indices == (0,)
    policy.reset("control-test", 0, "terminal")
    assert policy.diagnostics.last_reset_reason == "terminal"


def test_reused_request_identity_with_changed_payload_is_rejected():
    yes = option(1)
    req0 = request((yes,), selection_type=9, transition=0)
    policy = MegaAbomasnowControl()
    policy.reset("control-test", 0)
    obs = observation(transition=0)
    policy.choose(obs, req0)
    changed = replace(
        request((option(2),), selection_type=9, transition=0),
        request_id=req0.request_id,
    )
    with pytest.raises(ContractViolation, match="changed|reused|identity"):
        policy.choose(obs, changed)


def test_optional_multiselect_stops_before_negative_tail():
    water = option(7, source=entity(3, 1).entity_key, index=0)
    end = option(14, index=1)
    req = request((water, end), selection_type=0, context=8, min_count=0, max_count=2)
    policy = MegaAbomasnowControl()
    policy.reset("control-test", 0)
    action = policy.choose(observation((entity(3, 1),)), req)
    assert action.submitted_original_indices == (0,)
    assert action.stopped_early
    assert action.steps[-1].chosen_token == "STOP"


def test_duplicate_semantic_fingerprints_fail_closed_without_order_tiebreak():
    duplicate = option(1, index=0)
    duplicate = replace(duplicate, original_index=1)
    duplicate = replace(duplicate, semantic_fingerprint=stable_hash(duplicate.semantic_payload()))
    req = request((option(1, index=0), duplicate), selection_type=9, min_count=1, max_count=1)
    policy = MegaAbomasnowControl()
    policy.reset("control-test", 0)
    with pytest.raises(ContractViolation, match="ambiguous|duplicate"):
        policy.choose(observation(), req)


def test_partial_attack_effects_all_remain_frozen_reproduction():
    attacker = entity(723, 1, zone=AREA["ACTIVE"], energy=3)
    opponent = entity(723, 9, owner=1, zone=AREA["ACTIVE"])
    req = request(
        tuple(option(13, index=index, attack_id=attack_id) for index, attack_id in enumerate((RIPTIDE, SWIRLING_WAVES, 1046, FROST_BARRIER))),
        selection_type=6,
        context=35,
        min_count=1,
        max_count=1,
    )
    policy = MegaAbomasnowControl()
    policy.reset("control-test", 0)
    decisions = [policy.score_option(observation((attacker, opponent)), req, item) for item in req.options]
    assert all(item.route_label == FROZEN_CONTROL_REPRODUCTION for item in decisions)


def test_public_hidden_boundary_and_malformed_fingerprint_fail_closed():
    hidden_hand = entity(1192, 77, owner=1, zone=AREA["HAND"])
    req = request((option(1),), selection_type=9)
    policy = MegaAbomasnowControl()
    policy.reset("control-test", 0)
    with pytest.raises(ContractViolation, match="opponent hand"):
        policy.choose(observation((hidden_hand,)), req)

    valid = req.options[0]
    malformed = replace(valid, semantic_fingerprint="0" * 64)
    malformed_request = replace(req, options=(malformed,))
    with pytest.raises(ContractViolation, match="fingerprint"):
        policy.choose(observation(), malformed_request)


def test_non_route_ability_is_not_treated_as_a_positive_control():
    active = entity(723, 1, zone=AREA["ACTIVE"])
    req = request((option(10, source=active.entity_key),), selection_type=0)
    policy = MegaAbomasnowControl()
    policy.reset("control-test", 0)
    assert policy.score_option(observation((active,)), req, req.options[0]).score == -1


def test_official_select_context_mapping_scopes_discard_bonus():
    water = entity(3, 1)
    discard_option = option(3, source=water.entity_key)
    to_hand_req = request((discard_option,), selection_type=1, context=7)
    discard_req = request((discard_option,), selection_type=1, context=8)
    policy = MegaAbomasnowControl()
    obs = observation((water,))
    # Bound to the official API enum: TO_HAND=7, DISCARD=8.
    assert policy.score_option(obs, to_hand_req, to_hand_req.options[0]).score == 0
    assert policy.score_option(obs, discard_req, discard_req.options[0]).score == 100
    snover = entity(SNOVER, 2)
    to_hand_snover = request(
        (option(3, source=snover.entity_key),), selection_type=1, context=7
    )
    to_bench_snover = request(
        (option(3, source=snover.entity_key),), selection_type=1, context=5
    )
    assert policy.score_option(observation((snover,)), to_hand_snover, to_hand_snover.options[0]).score == 30
    assert policy.score_option(observation((snover,)), to_bench_snover, to_bench_snover.options[0]).score == 30


def test_acting_player_one_uses_player_one_public_board_as_self():
    own = entity(SNOVER, 1, owner=1, zone=AREA["ACTIVE"])
    opponent = entity(MEGA_ABOMASNOW_EX, 9, owner=0, zone=AREA["ACTIVE"])
    req = request(
        (option(3, source=own.entity_key, index=0),),
        selection_type=1,
        context=1,
        actor=1,
    )
    obs = observation((opponent, own), actor=1)
    policy = MegaAbomasnowControl()
    policy.reset("control-test", 1)
    action = policy.choose(obs, req)
    assert action.submitted_original_indices == (0,)


def test_forged_choice_role_and_source_shape_fail_closed_even_with_rehashed_payload():
    valid = option(7, source=entity(1192, 1).entity_key)
    forged = replace(valid, choice_role="ATTACK")
    forged = replace(forged, semantic_fingerprint=stable_hash(forged.semantic_payload()))
    req = request((forged,), selection_type=0)
    policy = MegaAbomasnowControl()
    policy.reset("control-test", 0)
    with pytest.raises(ContractViolation, match="choice role"):
        policy.choose(observation((entity(1192, 1),)), req)
