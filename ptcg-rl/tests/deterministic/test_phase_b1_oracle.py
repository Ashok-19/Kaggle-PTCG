from __future__ import annotations

from dataclasses import replace
from itertools import islice, permutations
from pathlib import Path

import pytest

from ptcg_rl.deterministic.b1_oracle import (
    A_FORMULATION,
    B_FORMULATION,
    B0_DELEGATE,
    TERMINAL_OVERRIDE,
    AMBIGUOUS,
    OFFLINE_FIXTURE,
    RUNTIME_NATIVE,
    SELECTED,
    UNKNOWN,
    UNSUPPORTED,
    AttackStaticV1,
    CapabilityReceiptV1,
    CardStaticV1,
    ContextCapabilityV1,
    CurrentStateRouteOracleV1,
    NO_SAFE_ROUTE,
    OfflineFixtureEvaluatorV1,
    OFFLINE_A_FORMULATION,
    OFFLINE_B_FORMULATION,
    OfflineRouteCandidateV1,
    OfflineResponseClassV1,
    PrizeStaticV1,
    RouteDecisionV1,
)
from ptcg_rl.g1.models import (
    CONTRACT_VERSION,
    EngineObservationV1,
    LegalOptionV1,
    PlayerViewV1,
    SelectionRequestV1,
    VisibleEntityV1,
    stable_hash,
)
from ptcg_rl.g1.semantic import AREA, OPTION_NAMES


HASH = "a" * 64


def _entity(
    card_id: int,
    serial: int,
    *,
    owner: int = 0,
    zone: int = AREA["ACTIVE"],
    position: int = 0,
    hp: int | None = 100,
    energy: tuple[int, ...] = (),
) -> VisibleEntityV1:
    board = zone in {AREA["ACTIVE"], AREA["BENCH"]}
    return VisibleEntityV1(
        entity_key=f"p{owner}:s{serial}",
        card_id=card_id,
        serial=serial,
        metadata_ref=f"card:{card_id}@{HASH}",
        owner=owner,
        zone=zone,
        position=position,
        hp=hp if board else None,
        max_hp=hp if board else None,
        damage=0 if board else None,
        energy_types=energy,
        attached_energy_count=len(energy),
    )


def _option(
    option_type: int,
    index: int,
    *,
    source: str | None = None,
    target: str | None = None,
    attack_id: int | None = None,
    card_id: int | None = None,
    energy_index: int | None = None,
) -> LegalOptionV1:
    # Native ATTACK options carry the active source only; the opponent's
    # active target is implicit in the engine option contract.
    if option_type == 13:
        target = None
    source_kind = "ENTITY" if source is not None else "NONE"
    target_kind = "ENTITY" if target is not None else "NONE"
    row = LegalOptionV1(
        schema_version=CONTRACT_VERSION,
        original_index=index,
        selection_type=6 if option_type == 13 else 0,
        selection_context=35 if option_type == 13 else 0,
        option_type=option_type,
        option_name=OPTION_NAMES[option_type],
        area=AREA["HAND"] if option_type == 8 else None,
        index=index if option_type == 8 else None,
        energy_index=energy_index if option_type == 8 else None,
        in_play_area=AREA["ACTIVE"] if option_type == 8 else None,
        in_play_index=0 if option_type == 8 else None,
        attack_id=attack_id,
        card_id=card_id,
        source_kind=source_kind,
        source_ref=source,
        target_kind=target_kind,
        target_ref=target,
        choice_role=OPTION_NAMES[option_type],
        source_entity_key=source,
        target_entity_key=target,
    )
    return replace(row, semantic_fingerprint=stable_hash(row.semantic_payload()))


def _request(options: tuple[LegalOptionV1, ...], *, min_count: int = 1, max_count: int = 1) -> SelectionRequestV1:
    selection_type = options[0].selection_type if options else 6
    selection_context = options[0].selection_context if options else 35
    return SelectionRequestV1(
        schema_version=CONTRACT_VERSION,
        episode_uuid="b1-test",
        selection_seq=0,
        request_id=f"b1-request-{stable_hash([item.semantic_fingerprint for item in options])}",
        acting_player=0,
        selection_type=selection_type,
        selection_context=selection_context,
        min_count=min_count,
        max_count=max_count,
        remain_damage_counter=0,
        remain_energy_cost=0,
        context_card_id=None,
        effect_card_id=None,
        ordering="UNORDERED",
        options=options,
    )


def _observation(entities: tuple[VisibleEntityV1, ...], *, terminal_result: int | None = None) -> EngineObservationV1:
    return EngineObservationV1(
        schema_version=CONTRACT_VERSION,
        battle_id="b1-test",
        transition_id=0,
        acting_player=0,
        terminal_result=terminal_result,
        turn=2,
        turn_action_count=0,
        first_player=0,
        supporter_played=False,
        stadium_played=False,
        energy_attached=False,
        retreated=False,
        players=(
            PlayerViewV1(0, 5, 20, 3, 4, 0, True, 0),
            PlayerViewV1(1, 5, 20, 3, 4, 0, False, 0),
        ),
        entities=entities,
        public_events=(),
    )


def _receipt(*, scope: str = OFFLINE_FIXTURE, add_setup: bool = False) -> CapabilityReceiptV1:
    cards = (
        CardStaticV1(722, 100, 3, None, None, 0, HASH, HASH, scope),
        CardStaticV1(900, 100, 3, None, None, 0, HASH, HASH, scope),
    )
    attacks = (
        AttackStaticV1(722, 1044, 10, (0, 0, 0, 2) + (0,) * 8, 3, HASH, HASH, scope),
        AttackStaticV1(722, 1045, 20, (0, 0, 0, 2) + (0,) * 8, 3, HASH, HASH, scope),
        AttackStaticV1(900, 2001, 30, (0, 0, 0, 1) + (0,) * 8, 3, HASH, HASH, scope),
    )
    prizes = (
        PrizeStaticV1(722, 1, HASH, HASH, scope),
        PrizeStaticV1(900, 2, HASH, HASH, scope),
    )
    contexts = (ContextCapabilityV1(0, 0, 8, None, None, "ATTACH", scope),) if add_setup else ()
    return CapabilityReceiptV1(
        schema_version=1,
        receipt_id="b1-fixture-receipt",
        engine_sha256=HASH,
        card_data_sha256=HASH,
        scope=scope,
        cards=cards,
        attacks=attacks,
        prizes=prizes,
        contexts=contexts,
    )


def _attack_fixture():
    own = _entity(722, 1, energy=(3, 3))
    backup = _entity(722, 2, zone=AREA["BENCH"], energy=(3, 3))
    opponent = _entity(900, 9, owner=1, hp=10)
    options = (
        _option(13, 0, source=own.entity_key, target=opponent.entity_key, attack_id=1044),
        _option(13, 1, source=own.entity_key, target=opponent.entity_key, attack_id=1045),
    )
    return _observation((own, backup, opponent)), _request(options)


def test_f01_terminal_override_is_checked_before_request_or_selection_data():
    terminal = _observation((), terminal_result=1)
    decision = CurrentStateRouteOracleV1(_receipt()).evaluate(terminal, None)
    assert decision.status == TERMINAL_OVERRIDE
    assert decision.authority == "B0_CONTROL"


def test_f02_and_f03_current_only_formulations_do_not_use_damage_as_a_route_claim():
    observation, request = _attack_fixture()
    oracle = CurrentStateRouteOracleV1(_receipt())
    assert oracle.evaluate(observation, request, A_FORMULATION).status in {"SELECTED", "AMBIGUOUS"}
    assert oracle.evaluate(observation, request, B_FORMULATION).status in {"SELECTED", "AMBIGUOUS"}
    assert oracle.evaluate(observation, request).decision_key


def test_f04_current_attack_target_is_implicit_and_forged_target_delegates():
    observation, request = _attack_fixture()
    forged = replace(request.options[0], target_ref="p1:s9", target_entity_key="p1:s9")
    forged = replace(forged, target_kind="ENTITY")
    forged = replace(forged, semantic_fingerprint=stable_hash(forged.semantic_payload()))
    decision = CurrentStateRouteOracleV1(_receipt()).evaluate(observation, replace(request, options=(forged,)))
    assert decision.status == B0_DELEGATE
    assert "source/target" in (decision.fail_closed_reason or "")


def test_f04_offline_response_envelopes_keep_formulations_distinct_and_fail_closed():
    candidates = (
        OfflineRouteCandidateV1("x", (0, 0, 0), (OfflineResponseClassV1("a", 0.8, 1.0), OfflineResponseClassV1("b", 0.8, 1.0))),
        OfflineRouteCandidateV1("y", (0, 0, 0), (OfflineResponseClassV1("a", 1.0, 1.0), OfflineResponseClassV1("b", 0.7, 1.0))),
    )
    result = OfflineFixtureEvaluatorV1().compare(candidates)
    assert result.robust_choice == "x"
    assert result.mean_choice == "y"
    assert OfflineFixtureEvaluatorV1().compare(candidates[:1]).status == UNSUPPORTED
    assert OfflineFixtureEvaluatorV1().compare((object(), object())).status == UNSUPPORTED


def test_f05_partial_attack_ids_and_f06_hidden_metadata_are_not_authority():
    observation, request = _attack_fixture()
    partial = replace(request.options[0], attack_id=1046)
    partial = replace(partial, semantic_fingerprint=stable_hash(partial.semantic_payload()))
    partial_request = replace(request, options=(partial,))
    assert CurrentStateRouteOracleV1(_receipt()).evaluate(observation, partial_request).status == B0_DELEGATE
    assert CurrentStateRouteOracleV1(_receipt()).evaluate(observation, request).status != UNSUPPORTED


def test_f06_opponent_hidden_hand_is_rejected_and_never_becomes_a_feature():
    observation, request = _attack_fixture()
    hidden_hand = _entity(1121, 77, owner=1, zone=AREA["HAND"])
    result = CurrentStateRouteOracleV1(_receipt()).evaluate(
        replace(observation, entities=observation.entities + (hidden_hand,)), request
    )
    assert result.status == UNSUPPORTED
    assert "public boundary" in (result.fail_closed_reason or "")
    assert CurrentStateRouteOracleV1(_receipt()).diagnostics.hidden_leak_rejections == 0
    oracle = CurrentStateRouteOracleV1(_receipt())
    oracle.evaluate(replace(observation, entities=observation.entities + (hidden_hand,)), request)
    assert oracle.diagnostics.hidden_leak_rejections == 1


def test_f07_all_32_option_permutations_are_semantically_invariant():
    observation, request = _attack_fixture()
    opponent_bench = tuple(
        _entity(722, serial, owner=1, zone=AREA["BENCH"], position=serial - 10, hp=10)
        for serial in range(10, 14)
    )
    options = (
        _option(13, 0, source="p0:s1", target="p1:s9", attack_id=1044),
        *tuple(_option(13, serial - 9, source="p0:s1", target=f"p1:s{serial}", attack_id=1045) for serial in range(10, 14)),
    )
    request = replace(request, options=options)
    observation = replace(observation, entities=observation.entities + opponent_bench)
    receipt = _receipt()
    receipt = replace(receipt, attacks=(replace(receipt.attacks[0], damage=5), *receipt.attacks[1:]))
    chosen = []
    for permutation in islice(permutations(range(len(request.options))), 32):
        permuted = replace(request, options=tuple(request.options[index] for index in permutation))
        decision = CurrentStateRouteOracleV1(receipt).evaluate(observation, permuted)
        assert decision.status == SELECTED
        chosen.append(decision.chosen_option_fingerprints)
    assert len(chosen) == 32
    assert len(set(chosen)) == 1


def test_f07_mixed_complete_option_set_delegates_instead_of_scoring_a_safe_prefix():
    observation, request = _attack_fixture()
    partial = replace(request.options[0], attack_id=1046)
    partial = replace(partial, semantic_fingerprint=stable_hash(partial.semantic_payload()))
    mixed = replace(request, options=(request.options[1], partial))
    decision = CurrentStateRouteOracleV1(_receipt()).evaluate(observation, mixed)
    assert decision.status == B0_DELEGATE
    assert decision.candidate_count == 1


def test_f08_player_mirror_uses_role_relative_public_state():
    observation, request = _attack_fixture()
    mirror_own = _entity(722, 11, owner=1, energy=(3, 3))
    mirror_backup = _entity(722, 12, owner=1, zone=AREA["BENCH"], energy=(3, 3))
    mirror_opponent = _entity(900, 19, owner=0, hp=10)
    mirrored_observation = replace(
        observation,
        acting_player=1,
        entities=(mirror_opponent, mirror_own, mirror_backup),
        players=(replace(observation.players[0], hand_visible=False), replace(observation.players[1], hand_visible=True)),
    )
    mirrored_options = tuple(
        replace(
            item,
            source_ref="p1:s11",
            source_entity_key="p1:s11",
            semantic_fingerprint=stable_hash(
                replace(
                    item,
                    source_ref="p1:s11",
                    source_entity_key="p1:s11",
                ).semantic_payload()
            ),
        )
        for item in request.options
    )
    mirrored_request = replace(request, acting_player=1, options=mirrored_options)
    left = CurrentStateRouteOracleV1(_receipt()).evaluate(observation, request)
    right = CurrentStateRouteOracleV1(_receipt()).evaluate(mirrored_observation, mirrored_request)
    assert left.status == right.status == AMBIGUOUS
    assert left.decision_key == right.decision_key


def test_r02_current_energy_readiness_is_exact_and_public_only():
    observation, request = _attack_fixture()
    singleton = replace(request, options=(request.options[0],))
    keys = []
    for energy in ((), (3,), (3, 3)):
        active = replace(observation.entities[0], energy_types=energy, attached_energy_count=len(energy))
        current = replace(observation, entities=(active, *observation.entities[1:]))
        decision = CurrentStateRouteOracleV1(_receipt()).evaluate(current, singleton)
        assert decision.status == SELECTED
        keys.append(decision.decision_key)
    assert keys[0][0] == 0
    assert keys[1][0] == 0
    assert keys[2][0] == 1


def test_r03_current_formulation_keys_are_separate_without_successor_data():
    observation, request = _attack_fixture()
    singleton = replace(request, options=(request.options[0],))
    robust = CurrentStateRouteOracleV1(_receipt()).evaluate(observation, singleton, A_FORMULATION)
    threat = CurrentStateRouteOracleV1(_receipt()).evaluate(observation, singleton, B_FORMULATION)
    assert robust.status == threat.status == SELECTED
    assert robust.decision_key != threat.decision_key
    assert robust.chosen_option_fingerprints == threat.chosen_option_fingerprints


def test_f09_public_only_unknown_resource_never_becomes_a_ready_attacker():
    observation, request = _attack_fixture()
    no_energy = replace(observation.entities[0], energy_types=(), attached_energy_count=1)
    result = CurrentStateRouteOracleV1(_receipt()).evaluate(replace(observation, entities=(no_energy, observation.entities[1], observation.entities[2])), request)
    assert result.status == UNKNOWN
    assert "unknown" in (result.fail_closed_reason or "")


def test_r05_missing_prize_receipt_fails_closed_without_ex_flag_inference():
    observation, request = _attack_fixture()
    receipt = _receipt()
    receipt = replace(receipt, prizes=(receipt.prizes[0],))
    decision = CurrentStateRouteOracleV1(receipt).evaluate(observation, replace(request, options=(request.options[0],)))
    assert decision.status == UNKNOWN
    assert decision.chosen_option_fingerprints == ()


def test_f10_optional_stop_and_all_compound_requests_delegate_to_b0():
    observation, request = _attack_fixture()
    optional = replace(request, min_count=0, max_count=1)
    assert CurrentStateRouteOracleV1(_receipt()).evaluate(observation, optional).status == B0_DELEGATE
    compound = replace(request, min_count=1, max_count=2)
    assert CurrentStateRouteOracleV1(_receipt()).evaluate(observation, compound).status == B0_DELEGATE


def test_f10_optional_stop_must_be_available_and_is_a_first_class_candidate():
    observation, request = _attack_fixture()
    attack = replace(request.options[1], original_index=0)
    attack = replace(attack, selection_type=0, selection_context=0)
    attack = replace(attack, semantic_fingerprint=stable_hash(attack.semantic_payload()))
    stop = _option(14, 1)
    optional = replace(request, selection_type=0, selection_context=0, options=(attack, stop), min_count=0, max_count=1)
    decision = CurrentStateRouteOracleV1(_receipt()).evaluate(observation, optional)
    assert decision.status == SELECTED
    assert decision.chosen_option_fingerprints == (attack.semantic_fingerprint,)

    unavailable_stop = replace(stop, available=False)
    unavailable_stop = replace(unavailable_stop, semantic_fingerprint=stable_hash(unavailable_stop.semantic_payload()))
    unavailable = replace(optional, options=(attack, unavailable_stop))
    assert CurrentStateRouteOracleV1(_receipt()).evaluate(observation, unavailable).status == B0_DELEGATE


def test_r09_stale_lifecycle_identity_delegates_before_route_scoring():
    observation, request = _attack_fixture()
    stale = replace(request, selection_seq=1)
    assert CurrentStateRouteOracleV1(_receipt()).evaluate(observation, stale).status == UNSUPPORTED


def test_runtime_boundary_rejects_duplicate_board_positions_and_nonfinite_keys():
    observation, request = _attack_fixture()
    duplicate = _entity(722, 10, owner=1, zone=AREA["BENCH"], position=0)
    duplicate_again = _entity(722, 11, owner=1, zone=AREA["BENCH"], position=0)
    decision = CurrentStateRouteOracleV1(_receipt()).evaluate(
        replace(observation, entities=observation.entities + (duplicate, duplicate_again)), request
    )
    assert decision.status == UNSUPPORTED
    assert "duplicated" in (decision.fail_closed_reason or "")
    with pytest.raises(ValueError, match="NaN/Inf"):
        RouteDecisionV1(
            schema_version=1,
            request_id="finite-test",
            selection_seq=0,
            acting_player=0,
            policy_id="test",
            status=SELECTED,
            formulation_id=A_FORMULATION,
            authority="B0_CONTROL",
            decision_key=({"score": float("nan")},),
        )


def test_runtime_api_rejects_offline_successor_candidate_without_reading_it():
    observation, request = _attack_fixture()
    offline = OfflineRouteCandidateV1(
        "successor",
        (0, 0, 0),
        (OfflineResponseClassV1("public", 1.0, 1.0),),
        route_distance=1,
        horizon_required=1,
        horizon_limit=1,
        branch_count=1,
        branch_budget=1,
        next_attacker_ready=True,
        live_backup_count=1,
        bench_liability=0,
        resource_reserve=1,
    )
    decision = CurrentStateRouteOracleV1(_receipt()).evaluate(offline, None)
    assert decision.status == UNSUPPORTED
    assert decision.authority == "B0_CONTROL"


def test_terminal_boundary_rejects_unknown_result_without_reading_stale_request():
    terminal = _observation((), terminal_result=99)
    decision = CurrentStateRouteOracleV1(_receipt()).evaluate(terminal, object())
    assert decision.status == UNSUPPORTED
    assert "terminal public boundary" in (decision.fail_closed_reason or "")


def test_f11_bounded_horizon_and_branch_pruning_has_no_strength_score():
    horizon_pruned = OfflineRouteCandidateV1(
        "horizon",
        (0, 0, 0),
        (OfflineResponseClassV1("complete", 0.9, 1.0),),
        route_distance=2,
        horizon_required=5,
        horizon_limit=4,
        branch_count=4,
        branch_budget=4,
        next_attacker_ready=True,
        live_backup_count=1,
        bench_liability=0,
        resource_reserve=1,
    )
    branch_pruned = OfflineRouteCandidateV1(
        "branch",
        (0, 0, 0),
        (OfflineResponseClassV1("complete", 1.0, 1.0),),
        route_distance=1,
        horizon_required=4,
        horizon_limit=4,
        branch_count=5,
        branch_budget=4,
        next_attacker_ready=True,
        live_backup_count=1,
        bench_liability=0,
        resource_reserve=1,
    )
    result = OfflineFixtureEvaluatorV1().compare((horizon_pruned, branch_pruned), OFFLINE_A_FORMULATION)
    assert result.status == NO_SAFE_ROUTE
    assert result.max_horizon_pruned == 2
    assert result.selected_choice is None
    assert result.strength_score is None
    assert OfflineFixtureEvaluatorV1().compare((horizon_pruned, branch_pruned), A_FORMULATION).status == UNSUPPORTED


def test_f12_equal_route_distance_applies_liability_and_live_backup_late():
    def candidate(name: str, score: float, liability: int, backup: int) -> OfflineRouteCandidateV1:
        return OfflineRouteCandidateV1(
            name,
            (0, 0, 0),
            (OfflineResponseClassV1("complete", score, 1.0),),
            route_distance=2,
            horizon_required=2,
            horizon_limit=4,
            branch_count=2,
            branch_budget=4,
            next_attacker_ready=True,
            live_backup_count=backup,
            bench_liability=liability,
            resource_reserve=1,
        )

    liability_candidates = (candidate("liable", 0.8, 2, 1), candidate("safe", 0.8, 0, 1))
    evaluator = OfflineFixtureEvaluatorV1()
    robust = evaluator.compare(liability_candidates, OFFLINE_A_FORMULATION)
    expected = evaluator.compare(liability_candidates, OFFLINE_B_FORMULATION)
    assert robust.selected_choice == expected.selected_choice == "safe"

    # B's expected route score precedes the later public liability tiebreak.
    expected_score = evaluator.compare(
        (candidate("liable", 0.9, 2, 1), candidate("safe", 0.8, 0, 1)), OFFLINE_B_FORMULATION
    )
    assert expected_score.selected_choice == "liable"

    # When all earlier keys tie, a visible live backup is still deterministic,
    # without consulting option order or a hidden successor.
    backup = evaluator.compare(
        (candidate("no-backup", 0.8, 0, 0), candidate("backup", 0.8, 0, 1)), OFFLINE_A_FORMULATION
    )
    assert backup.selected_choice == "backup"

    # The formulation-specific ordering is observable only when an earlier
    # field disagrees with a later field: A prefers the low-liability route,
    # while B's resource reserve wins before liability is consulted.
    def ordered(name: str, reserve: int, liability: int) -> OfflineRouteCandidateV1:
        value = candidate(name, 0.8, liability, 0)
        return replace(value, resource_reserve=reserve)

    a_late = evaluator.compare(
        (ordered("reserve-rich-liable", 2, 2), ordered("reserve-poor-safe", 1, 0)),
        OFFLINE_A_FORMULATION,
    )
    b_late = evaluator.compare(
        (ordered("reserve-rich-liable", 2, 2), ordered("reserve-poor-safe", 1, 0)),
        OFFLINE_B_FORMULATION,
    )
    assert a_late.selected_choice == "reserve-poor-safe"
    assert b_late.selected_choice == "reserve-rich-liable"


def test_f12_and_context_boundary_are_explicit_and_deterministic():
    observation, request = _attack_fixture()
    no_context = CurrentStateRouteOracleV1(_receipt(add_setup=True)).evaluate(observation, request)
    assert no_context.status in {"SELECTED", AMBIGUOUS}
    setup = _option(8, 0, source="p0:s3", target="p0:s1", card_id=3, energy_index=0)
    setup_req = SelectionRequestV1(
        schema_version=CONTRACT_VERSION,
        episode_uuid="b1-test",
        selection_seq=0,
        request_id="setup",
        acting_player=0,
        selection_type=0,
        selection_context=0,
        min_count=1,
        max_count=1,
        remain_damage_counter=0,
        remain_energy_cost=0,
        context_card_id=None,
        effect_card_id=None,
        ordering="UNORDERED",
        options=(setup,),
    )
    setup_observation = _observation((observation.entities[0], observation.entities[1], observation.entities[2], _entity(3, 3, zone=AREA["HAND"])))
    assert CurrentStateRouteOracleV1(_receipt(add_setup=True)).evaluate(setup_observation, setup_req).status in {"SELECTED", AMBIGUOUS}
    bad_context = replace(setup_req, context_card_id=721)
    assert CurrentStateRouteOracleV1(_receipt(add_setup=True)).evaluate(setup_observation, bad_context).status == B0_DELEGATE

    forged_source = _entity(3, 4, zone=AREA["DISCARD"])
    forged_option = replace(setup, source_ref=forged_source.entity_key, source_entity_key=forged_source.entity_key)
    forged_option = replace(forged_option, semantic_fingerprint=stable_hash(forged_option.semantic_payload()))
    forged_request = replace(setup_req, options=(forged_option,))
    forged_observation = replace(setup_observation, entities=setup_observation.entities + (forged_source,))
    assert CurrentStateRouteOracleV1(_receipt(add_setup=True)).evaluate(forged_observation, forged_request).status == B0_DELEGATE


def test_versioned_config_keeps_fixture_scope_and_native_route_blocked():
    config_path = Path(__file__).resolve().parents[2] / "configs/deterministic/phase_b1_prize_route_v1.json"
    payload = __import__("json").loads(config_path.read_text(encoding="utf-8"))
    assert payload["scope"] == OFFLINE_FIXTURE
    assert payload["receipt_boundary"]["fixture_scope_is_not_native"] is True
    assert payload["receipt_boundary"]["offline_fixture_successor_snapshots_allowed"] is True
    assert payload["receipt_boundary"]["runtime_oracle_successor_snapshots_allowed"] is False
    assert payload["offline_fixture_formulations"] == [OFFLINE_A_FORMULATION, OFFLINE_B_FORMULATION]
    assert payload["native_integration_gate"]["status"] == "BLOCKED"
    assert payload["native_integration_gate"]["runtime_policy_input"] is False
    assert payload["native_integration_gate"]["fixture_evaluator_remains_allowed"] is True
    assert payload["native_integration_gate"]["older_route_statuses_do_not_authorize_native_integration"] is True
    assert payload["offline_fixture_gate"]["evaluator"] == "OfflineFixtureEvaluatorV1"
    assert payload["offline_fixture_gate"]["restricted_runtime_fixtures"]["evaluator"] == "CurrentStateRouteOracleV1"
    assert payload["offline_fixture_gate"]["restricted_runtime_fixtures"]["singleton_only"] is True
    assert payload["active_request_contract"]["compound"] == "B0_DELEGATE"


def test_runtime_mode_rejects_fixture_only_receipt_and_nan_is_rejected():
    observation, request = _attack_fixture()
    assert CurrentStateRouteOracleV1(_receipt(), mode=RUNTIME_NATIVE).evaluate(observation, request).status == B0_DELEGATE
    with pytest.raises(ValueError):
        OfflineResponseClassV1("nan", float("nan"), 1.0)


def test_receipt_asset_digests_are_bound_and_runtime_receipt_is_nonempty():
    mismatched_card = replace(_receipt().cards[0], engine_sha256="b" * 64)
    with pytest.raises(ValueError, match="nested receipt asset digest"):
        CapabilityReceiptV1(
            schema_version=1,
            receipt_id="bad",
            engine_sha256=HASH,
            card_data_sha256=HASH,
            scope=OFFLINE_FIXTURE,
            cards=(mismatched_card, *_receipt().cards[1:]),
            attacks=_receipt().attacks,
            prizes=_receipt().prizes,
        )
    empty_runtime = CapabilityReceiptV1(
        schema_version=1,
        receipt_id="empty-runtime",
        engine_sha256=HASH,
        card_data_sha256=HASH,
        scope=RUNTIME_NATIVE,
    )
    assert not empty_runtime.runtime_qualified()


def test_runtime_and_fixture_authority_labels_are_not_interchangeable():
    observation, request = _attack_fixture()
    singleton = replace(request, options=(request.options[0],))
    fixture = CurrentStateRouteOracleV1(_receipt()).evaluate(observation, singleton)
    native = CurrentStateRouteOracleV1(_receipt(scope=RUNTIME_NATIVE), mode=RUNTIME_NATIVE).evaluate(observation, singleton)
    assert fixture.status == native.status == SELECTED
    assert fixture.authority == "EXPERIMENTAL_PUBLIC_ROUTE_FIXTURE"
    assert native.authority == "EXPERIMENTAL_PUBLIC_ROUTE_RUNTIME"
    assert fixture.route_activation_id != native.route_activation_id
    assert fixture.route_key_sha256 != native.route_key_sha256
