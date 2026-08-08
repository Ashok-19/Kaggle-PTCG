"""Fixture-only regressions for the Phase B2 continuity evaluator.

These tests intentionally exercise the G1 records at the public boundary.  A
passing fixture is arithmetic evidence only; it does not authorize the B2
variant for a native PolicyV1 run.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import replace

import pytest

from ptcg_rl.deterministic.b2_continuity import (
    A_FORMULATION,
    B_FORMULATION,
    AMBIGUOUS,
    B0_DELEGATE,
    QUALIFIED_CABT_CAPSULE,
    TERMINAL_OVERRIDE,
    CurrentStateContinuityEvaluatorV1,
    load_b2_f01,
    materialize_b2_fixture_data,
    mirror_fixture,
    semantic_permutation_suite,
)
from ptcg_rl.g1.models import LegalOptionV1, stable_hash
from ptcg_rl.g1.semantic import OPTION_NAMES


@pytest.fixture()
def fixture():
    return load_b2_f01()


def test_f01_materializes_as_valid_public_state_and_diverges(fixture) -> None:
    assert fixture.state.observation == fixture.observation
    assert fixture.state.request == fixture.request
    assert fixture.semantic_targets == {A_FORMULATION: "p0:s11", B_FORMULATION: "p0:s12"}

    evaluator = CurrentStateContinuityEvaluatorV1(fixture.receipt)
    a = evaluator.evaluate(fixture.observation, fixture.request, A_FORMULATION)
    evaluator.reset(fixture.observation.battle_id, fixture.observation.acting_player)
    b = evaluator.evaluate(fixture.observation, fixture.request, B_FORMULATION)
    assert a.status == b.status == "SELECTED"
    assert a.chosen_target == "p0:s11"
    assert b.chosen_target == "p0:s12"
    assert a.authority == b.authority == "EXPERIMENTAL_CONTINUITY_FIXTURE"


@pytest.mark.parametrize("formulation", [A_FORMULATION, B_FORMULATION])
def test_all_four_option_permutations_are_semantic_invariant(fixture, formulation) -> None:
    expected = fixture.semantic_targets[formulation]
    outcomes = set()
    evaluator = CurrentStateContinuityEvaluatorV1(fixture.receipt)
    for permutation in itertools.permutations(range(4)):
        request = replace(fixture.request, options=tuple(fixture.request.options[i] for i in permutation))
        evaluator.reset(fixture.observation.battle_id, fixture.observation.acting_player)
        result = evaluator.evaluate(fixture.observation, request, formulation)
        outcomes.add((result.status, result.chosen_target))
    assert outcomes == {("SELECTED", expected)}


def test_b0_32_permutation_suite_is_exact_and_invariant(fixture) -> None:
    permutations = semantic_permutation_suite(4, 32)
    assert len(permutations) == 32
    assert len(set(permutations)) == 24
    assert len(set(permutations[:24])) == 24
    evaluator = CurrentStateContinuityEvaluatorV1(fixture.receipt)
    for formulation in (A_FORMULATION, B_FORMULATION):
        for permutation in permutations:
            request = replace(fixture.request, options=tuple(fixture.request.options[i] for i in permutation))
            evaluator.reset(fixture.observation.battle_id, fixture.observation.acting_player)
            result = evaluator.evaluate(fixture.observation, request, formulation)
            assert result.status == "SELECTED"
            assert result.chosen_target == fixture.semantic_targets[formulation]


def test_player_one_mirror_is_semantic_and_lifecycle_safe(fixture) -> None:
    mirrored = mirror_fixture(fixture)
    assert mirrored.observation.first_player == 1
    assert mirrored.observation.acting_player == mirrored.request.acting_player == 1
    evaluator = CurrentStateContinuityEvaluatorV1(mirrored.receipt)
    for formulation in (A_FORMULATION, B_FORMULATION):
        result = evaluator.evaluate(mirrored.observation, mirrored.request, formulation)
        assert result.status == "SELECTED"
        assert result.chosen_target == fixture.semantic_targets[formulation].replace("p0:", "p1:")

    duplicate = evaluator.evaluate(mirrored.observation, mirrored.request, A_FORMULATION)
    assert duplicate == evaluator.evaluate(mirrored.observation, mirrored.request, A_FORMULATION)
    changed = replace(mirrored.request, request_id="same-sequence-different-request")
    assert evaluator.evaluate(mirrored.observation, changed, A_FORMULATION).status == B0_DELEGATE


def test_partial_capability_delegates_without_safe_prefix(fixture) -> None:
    partial = replace(
        fixture.receipt,
        capabilities=tuple(
            replace(item, qualification_status="PARTIAL" if item.card_id == 723 else item.qualification_status)
            for item in fixture.receipt.capabilities
        ),
    )
    result = CurrentStateContinuityEvaluatorV1(partial).evaluate(
        fixture.observation, fixture.request, A_FORMULATION
    )
    assert result.status == B0_DELEGATE
    assert "PARTIAL" in (result.fail_closed_reason or "")
    assert result.chosen_target is None


def test_hidden_state_mutation_does_not_change_semantic_action(fixture) -> None:
    players = list(fixture.observation.players)
    players[1] = replace(players[1], hand_count=players[1].hand_count + 9, deck_count=players[1].deck_count - 9)
    hidden_mutation = replace(fixture.observation, players=tuple(players))
    result = CurrentStateContinuityEvaluatorV1(fixture.receipt).evaluate(
        hidden_mutation, fixture.request, A_FORMULATION
    )
    assert result.status == "SELECTED"
    assert result.chosen_target == "p0:s11"


def test_duplicate_semantics_and_duplicate_entities_delegate_or_fail_closed(fixture) -> None:
    first = fixture.request.options[0]
    duplicate = replace(
        fixture.request.options[1],
        source_entity_key=first.source_entity_key,
        source_ref=first.source_ref,
        target_entity_key=first.target_entity_key,
        target_ref=first.target_ref,
        in_play_area=first.in_play_area,
        in_play_index=first.in_play_index,
    )
    duplicate = replace(duplicate, semantic_fingerprint=stable_hash(duplicate.semantic_payload()))
    request = replace(fixture.request, options=(first, duplicate, *fixture.request.options[2:]))
    assert CurrentStateContinuityEvaluatorV1(fixture.receipt).evaluate(
        fixture.observation, request, A_FORMULATION
    ).status == B0_DELEGATE


def test_f04_non_equivalent_tie_and_unknown_public_candidate_delegate(fixture) -> None:
    entities = list(fixture.observation.entities)
    for index, item in enumerate(entities):
        if item.entity_key == "p0:s11":
            entities[index] = replace(item, energy_types=(), attached_energy_count=0)
    tied_observation = replace(fixture.observation, entities=tuple(entities))
    tie = CurrentStateContinuityEvaluatorV1(fixture.receipt).evaluate(
        tied_observation, fixture.request, A_FORMULATION
    )
    assert tie.status == AMBIGUOUS
    assert tie.chosen_target is None

    unknown = replace(
        fixture.receipt,
        capabilities=tuple(item for item in fixture.receipt.capabilities if item.card_id != 721),
    )
    no_public_candidate = CurrentStateContinuityEvaluatorV1(unknown).evaluate(
        fixture.observation, fixture.request, A_FORMULATION
    )
    assert no_public_candidate.status == B0_DELEGATE
    assert "UNKNOWN_CAPABILITY" in (no_public_candidate.fail_closed_reason or "")

    duplicated_entities = replace(
        fixture.observation, entities=fixture.observation.entities + (fixture.observation.entities[0],)
    )
    assert CurrentStateContinuityEvaluatorV1(fixture.receipt).evaluate(
        duplicated_entities, fixture.request, A_FORMULATION
    ).status == B0_DELEGATE


def test_complete_option_coverage_rejects_mixed_unsupported_option(fixture) -> None:
    row = LegalOptionV1(
        schema_version=2,
        original_index=4,
        selection_type=0,
        selection_context=0,
        option_type=7,
        option_name=OPTION_NAMES[7],
        index=0,
        choice_role=OPTION_NAMES[7],
        semantic_fingerprint="",
    )
    row = replace(row, semantic_fingerprint=stable_hash(row.semantic_payload()))
    mixed = replace(fixture.request, options=fixture.request.options + (row,))
    assert CurrentStateContinuityEvaluatorV1(fixture.receipt).evaluate(
        fixture.observation, mixed, A_FORMULATION
    ).status == B0_DELEGATE


def test_f06_unknown_attach_fields_and_evolution_local_delta_delegate(fixture) -> None:
    poisoned = replace(fixture.request.options[1], card_id=723)
    poisoned = replace(poisoned, semantic_fingerprint=stable_hash(poisoned.semantic_payload()))
    poisoned_request = replace(
        fixture.request,
        options=(fixture.request.options[0], poisoned, *fixture.request.options[2:]),
    )
    result = CurrentStateContinuityEvaluatorV1(fixture.receipt).evaluate(
        fixture.observation, poisoned_request, A_FORMULATION
    )
    assert result.status == B0_DELEGATE
    assert "SUCCESSOR_VALUE" in (result.fail_closed_reason or "")

    evolve = replace(fixture.request.options[0], option_type=9, option_name="EVOLVE", choice_role="EVOLVE")
    evolve = replace(evolve, semantic_fingerprint=stable_hash(evolve.semantic_payload()))
    evolve_request = replace(fixture.request, options=(evolve, *fixture.request.options[1:]))
    assert CurrentStateContinuityEvaluatorV1(fixture.receipt).evaluate(
        fixture.observation, evolve_request, A_FORMULATION
    ).status == B0_DELEGATE


def test_compound_ordered_and_nonfinite_inputs_delegate(fixture) -> None:
    compound = replace(fixture.request, max_count=2)
    assert CurrentStateContinuityEvaluatorV1(fixture.receipt).evaluate(
        fixture.observation, compound, A_FORMULATION
    ).status == B0_DELEGATE

    nonfinite = replace(fixture.request, remain_energy_cost=math.nan)
    assert CurrentStateContinuityEvaluatorV1(fixture.receipt).evaluate(
        fixture.observation, nonfinite, A_FORMULATION
    ).status == B0_DELEGATE


def test_optional_stop_is_a_real_g1_decoder_trace(fixture) -> None:
    optional = replace(fixture.request, min_count=0, max_count=1)
    built = CurrentStateContinuityEvaluatorV1.build_optional_stop(optional)
    assert built.stopped_early
    assert built.submitted_original_indices == ()
    assert built.steps[-1].chosen_token == "STOP"


def test_terminal_first_does_not_touch_stale_selection(fixture) -> None:
    terminal = replace(fixture.observation, terminal_result=1)
    poisoned = object()
    result = CurrentStateContinuityEvaluatorV1(fixture.receipt).evaluate(terminal, poisoned, A_FORMULATION)
    assert result.status == TERMINAL_OVERRIDE


def test_successor_only_fixture_fields_are_rejected(fixture) -> None:
    import json

    config = json.loads(fixture.config_path.read_text(encoding="utf-8"))
    config["fixture_cases"][0]["request"]["successor_energy"] = 99
    with pytest.raises(ValueError, match="SUCCESSOR_VALUE_FORBIDDEN"):
        materialize_b2_fixture_data(config)


def test_fixture_metadata_and_authority_receipts_are_version_bound(fixture) -> None:
    import json

    config = json.loads(fixture.config_path.read_text(encoding="utf-8"))
    config["fixture_metadata_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="FIXTURE_METADATA_VERSION_MISMATCH"):
        materialize_b2_fixture_data(config)

    config = json.loads(fixture.config_path.read_text(encoding="utf-8"))
    config["fixture_capabilities"][0]["qualification_status"] = QUALIFIED_CABT_CAPSULE
    with pytest.raises(ValueError, match="non-fixture authority"):
        materialize_b2_fixture_data(config)

    config = json.loads(fixture.config_path.read_text(encoding="utf-8"))
    config["record_id"] = "future-b2-fixture"
    with pytest.raises(ValueError, match="record id"):
        materialize_b2_fixture_data(config)


def test_native_capability_status_cannot_activate_fixture_evaluator(fixture) -> None:
    receipt = replace(
        fixture.receipt,
        capabilities=tuple(
            replace(item, qualification_status=QUALIFIED_CABT_CAPSULE)
            for item in fixture.receipt.capabilities
        ),
    )
    result = CurrentStateContinuityEvaluatorV1(receipt).evaluate(
        fixture.observation, fixture.request, A_FORMULATION
    )
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason == "NATIVE_CAPABILITY_SCOPE_NOT_AUTHORIZED"

    receipt = replace(fixture.receipt, receipt_id="unbound-receipt")
    result = CurrentStateContinuityEvaluatorV1(receipt).evaluate(
        fixture.observation, fixture.request, A_FORMULATION
    )
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason == "UNKNOWN_CAPABILITY_RECEIPT"


def test_current_attach_delta_rejects_forged_source_energy(fixture) -> None:
    entities = tuple(
        replace(entity, energy_types=(3,), attached_energy_count=1)
        if entity.entity_key == "p0:s20"
        else entity
        for entity in fixture.observation.entities
    )
    observation = replace(fixture.observation, entities=entities)
    result = CurrentStateContinuityEvaluatorV1(fixture.receipt).evaluate(
        observation, fixture.request, A_FORMULATION
    )
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason == "MISSING_LOCAL_DELTA_SOURCE"


def test_fixture_capability_rejects_forged_evolution_and_target_metadata(fixture) -> None:
    entities = tuple(
        replace(entity, evolution_depth=0)
        if entity.entity_key == "p0:s11"
        else entity
        for entity in fixture.observation.entities
    )
    evolution_result = CurrentStateContinuityEvaluatorV1(fixture.receipt).evaluate(
        replace(fixture.observation, entities=entities), fixture.request, A_FORMULATION
    )
    assert evolution_result.status == B0_DELEGATE
    assert evolution_result.fail_closed_reason == "EVOLUTION_REQUIREMENT_MISMATCH"

    receipt = replace(
        fixture.receipt,
        capabilities=tuple(
            replace(item, public_target_requirements="forged-target")
            for item in fixture.receipt.capabilities
        ),
    )
    target_result = CurrentStateContinuityEvaluatorV1(receipt).evaluate(
        fixture.observation, fixture.request, A_FORMULATION
    )
    assert target_result.status == B0_DELEGATE
    assert target_result.fail_closed_reason == "UNKNOWN_PUBLIC_TARGET_REQUIREMENTS"

    receipt = replace(
        fixture.receipt,
        capabilities=tuple(
            replace(item, qualification_id="forged-qualification")
            for item in fixture.receipt.capabilities
        ),
    )
    qualification_result = CurrentStateContinuityEvaluatorV1(receipt).evaluate(
        fixture.observation, fixture.request, A_FORMULATION
    )
    assert qualification_result.status == B0_DELEGATE
    assert qualification_result.fail_closed_reason == "UNKNOWN_FIXTURE_CAPABILITY"


def test_duplicate_public_location_cannot_forge_target_resolution(fixture) -> None:
    entities = tuple(
        replace(entity, position=0)
        if entity.entity_key == "p0:s12"
        else entity
        for entity in fixture.observation.entities
    )
    options = []
    for option in fixture.request.options:
        if option.target_entity_key == "p0:s12":
            option = replace(option, in_play_index=0)
            option = replace(option, semantic_fingerprint=stable_hash(option.semantic_payload()))
        options.append(option)
    request = replace(fixture.request, options=tuple(options))
    result = CurrentStateContinuityEvaluatorV1(fixture.receipt).evaluate(
        replace(fixture.observation, entities=entities), request, A_FORMULATION
    )
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason == "AMBIGUOUS_PUBLIC_LOCATION"


def test_noncanonical_original_indices_are_not_a_raw_order_feature(fixture) -> None:
    options = tuple(
        replace(option, original_index=99 - index)
        for index, option in enumerate(fixture.request.options)
    )
    request = object.__new__(type(fixture.request))
    for name in fixture.request.__dataclass_fields__:
        object.__setattr__(request, name, getattr(fixture.request, name))
    object.__setattr__(request, "options", options)
    result = CurrentStateContinuityEvaluatorV1(fixture.receipt).evaluate(
        fixture.observation, request, A_FORMULATION
    )
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason.startswith("PUBLIC_BOUNDARY:")
