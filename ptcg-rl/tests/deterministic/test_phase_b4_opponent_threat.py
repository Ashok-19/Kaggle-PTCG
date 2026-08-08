"""Isolated Phase B4 opponent-threat fixture regressions.

These tests qualify only current-public arithmetic and fail-closed handling.
Fixture capability rows are not native receipts and never establish policy
strength, matchup prevalence, or production authority.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from dataclasses import replace
from itertools import permutations
from pathlib import Path

import pytest

from ptcg_rl.deterministic.b4_opponent_threat import (
    A_FORMULATION,
    B_FORMULATION,
    B0_DELEGATE,
    COMPOUND_UNSUPPORTED,
    FIXTURE_ONLY,
    SELECTED,
    STOP_UNRESOLVED,
    SUCCESSOR_VALUE_FORBIDDEN,
    TERMINAL_OVERRIDE,
    CurrentOpponentThreatEvaluatorV1,
    ThreatLevelScaleV1,
    PublicCensusReceiptV1,
    _seal_case,
    _seal_capability,
    _seal_delta,
    load_b4_fixtures,
    materialize_b4_fixture_data,
    mirror_b4_case,
)
from ptcg_rl.deterministic.state import PublicStateError, PublicStateV1
from ptcg_rl.g1.models import EngineObservationV1, stable_hash
from ptcg_rl.g1.semantic import AREA


@pytest.fixture(scope="module")
def fixtures():
    return load_b4_fixtures()


def _case(fixtures, prefix: str):
    return next(item for item in fixtures.cases if item.case_id.startswith(prefix))


def _evaluate(case, formulation: str):
    evaluator = CurrentOpponentThreatEvaluatorV1(case.receipt)
    return evaluator.evaluate(case.state, case.local_deltas, formulation)


def test_b4_f01_materializes_public_state_and_formulations_diverge(fixtures) -> None:
    case = _case(fixtures, "B4-F01")
    assert isinstance(case.observation, EngineObservationV1)
    assert case.state.observation == case.observation
    assert case.state.request == case.request
    assert case.receipt.scope == FIXTURE_ONLY
    a = _evaluate(case, A_FORMULATION)
    b = _evaluate(case, B_FORMULATION)
    assert a.status == SELECTED
    assert a.chosen_semantic_action_key == ("B4-F01-Y",)
    assert b.status == B0_DELEGATE
    assert b.fail_closed_reason == "INTERVALS_INCOMPARABLE"
    assert a.interval_by_option and b.interval_by_option
    assert a.successor_reads == b.successor_reads == 0


def test_b4_f02_unknown_partial_and_hidden_fields_fail_closed(fixtures) -> None:
    case = _case(fixtures, "B4-F02")
    unknown = replace(case.capabilities[0], unknown_fields=("energy_matching",), ready_now=None)
    changed = replace(
        case,
        capabilities=(unknown, *case.capabilities[1:]),
        receipt=replace(case.receipt, capabilities=(unknown, *case.capabilities[1:])),
    )
    a = CurrentOpponentThreatEvaluatorV1(changed.receipt).evaluate(
        changed.state, changed.local_deltas, A_FORMULATION
    )
    assert a.status == B0_DELEGATE
    assert a.fail_closed_reason in {"UNKNOWN_THREAT_FIELD", "PARTIAL_CAPABILITY", "RECEIPT_CONTENT_MISMATCH"}

    bounded = replace(unknown, guaranteed_level=0, possible_level=3)
    bounded_case = replace(
        changed,
        capabilities=(bounded, *changed.capabilities[1:]),
        receipt=replace(changed.receipt, capabilities=(bounded, *changed.capabilities[1:])),
    )
    b = CurrentOpponentThreatEvaluatorV1(bounded_case.receipt).evaluate(
        bounded_case.state,
        bounded_case.local_deltas,
        B_FORMULATION,
    )
    assert b.status in {SELECTED, B0_DELEGATE}
    assert b.fail_closed_reason != "UNKNOWN_AS_SAFE"

    hidden_entity = replace(
        changed.observation.entities[-1],
        zone=2,
        owner=1,
        entity_key="p1:s50",
        position=0,
        metadata_ref=changed.observation.entities[-1].metadata_ref,
    )
    hidden_observation = replace(
        changed.observation,
        entities=(*changed.observation.entities[:-1], hidden_entity),
    )
    with pytest.raises(PublicStateError):
        PublicStateV1.from_engine(hidden_observation, changed.request)


def test_b4_f03_complete_options_and_builder_stop_are_explicit(fixtures) -> None:
    mixed = _case(fixtures, "B4-F03-MIXED")
    result = _evaluate(mixed, A_FORMULATION)
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason == "INCOMPLETE_THREAT_COVERAGE"
    optional = _case(fixtures, "B4-F03-OPTIONAL")
    selected = _evaluate(optional, A_FORMULATION)
    assert selected.status == SELECTED
    assert selected.action is not None
    assert selected.chosen_semantic_action_key == ("B4-F03-ACTION",)
    stop_case = _case(fixtures, "B4-F03-STOP")
    stop = _evaluate(stop_case, A_FORMULATION)
    assert stop.status == SELECTED
    assert stop.stopped_early
    assert stop.action is not None
    assert stop.action.steps[-1].chosen_token == "STOP"
    assert stop.chosen_option_fingerprints == ()


def test_b4_f04_rejects_compounds_ordering_stop_rows_and_duplicate_semantics(fixtures) -> None:
    for prefix in ("B4-F04-COMPOUND", "B4-F04-UNORDERED"):
        result = _evaluate(_case(fixtures, prefix), A_FORMULATION)
        assert result.status == B0_DELEGATE
        assert result.fail_closed_reason == COMPOUND_UNSUPPORTED
    ordered = _evaluate(_case(fixtures, "B4-F04-ORDERED"), A_FORMULATION)
    assert ordered.status == B0_DELEGATE
    assert ordered.fail_closed_reason == "ORDERED_UNSUPPORTED"
    stop_row = _evaluate(_case(fixtures, "B4-F04-STOP-ROW"), A_FORMULATION)
    assert stop_row.status == B0_DELEGATE
    assert stop_row.fail_closed_reason == STOP_UNRESOLVED
    duplicate = _evaluate(_case(fixtures, "B4-F04-DUPLICATE"), A_FORMULATION)
    assert duplicate.status == B0_DELEGATE
    assert duplicate.fail_closed_reason == "DUPLICATE_SEMANTICS"


def test_b4_f05_every_semantic_permutation_and_player_mirror_is_invariant(fixtures) -> None:
    case = _case(fixtures, "B4-F01")
    expected = _evaluate(case, A_FORMULATION).chosen_option_fingerprints
    for permutation in permutations(range(len(case.request.options))):
        request = replace(case.request, options=tuple(case.request.options[index] for index in permutation))
        state = PublicStateV1.from_engine(case.observation, request)
        permuted = replace(case, request=request, state=state)
        result = _evaluate(permuted, A_FORMULATION)
        assert result.status == SELECTED
        assert result.chosen_option_fingerprints == expected
    mirrored = mirror_b4_case(case)
    mirrored_result = _evaluate(mirrored, A_FORMULATION)
    assert mirrored_result.status == SELECTED
    assert mirrored_result.chosen_semantic_action_key == ("B4-F01-Y",)

    altered_player_counts = replace(
        case.observation.players[0], deck_count=case.observation.players[0].deck_count + 1
    )
    altered_observation = replace(
        case.observation,
        players=(altered_player_counts, case.observation.players[1]),
    )
    altered = replace(case, observation=altered_observation, state=PublicStateV1.from_engine(altered_observation, case.request))
    altered_result = _evaluate(altered, A_FORMULATION)
    assert altered_result.status == B0_DELEGATE
    assert altered_result.fail_closed_reason == "RECEIPT_CONTENT_MISMATCH"


def test_b4_f06_duplicate_stale_reset_and_worker_isolation(fixtures) -> None:
    case = _case(fixtures, "B4-F01")
    evaluator = CurrentOpponentThreatEvaluatorV1(case.receipt)
    first = evaluator.evaluate(case.state, case.local_deltas, A_FORMULATION)
    assert evaluator.evaluate(case.state, case.local_deltas, A_FORMULATION) == first
    changed_request = replace(case.request, request_id="b4-reused-request")
    changed_state = PublicStateV1.from_engine(case.observation, changed_request)
    changed = replace(case, request=changed_request, state=changed_state)
    stale = evaluator.evaluate(changed.state, changed.local_deltas, A_FORMULATION)
    assert stale.status == B0_DELEGATE
    assert stale.fail_closed_reason in {"STALE_OR_REUSED_REQUEST_IDENTITY", "STALE_SELECTION_SEQUENCE"}
    evaluator.reset(case.state.battle_id, case.state.acting_player, reason="error")
    assert evaluator.evaluate(case.state, case.local_deltas, A_FORMULATION).status == SELECTED
    evaluator.reset(case.state.battle_id, case.state.acting_player, reason="worker_replacement")
    assert evaluator.evaluate(case.state, case.local_deltas, A_FORMULATION).status == SELECTED


def test_b4_f07_missing_delta_successor_and_terminal_boundaries(fixtures) -> None:
    case = _case(fixtures, "B4-F07")
    missing = dict(case.local_deltas)
    missing.pop(case.request.options[0].semantic_fingerprint)
    missing_result = CurrentOpponentThreatEvaluatorV1(case.receipt).evaluate(
        case.state, missing, A_FORMULATION
    )
    assert missing_result.status == B0_DELEGATE
    assert missing_result.fail_closed_reason == "MISSING_LOCAL_DELTA"

    successor = replace(case, successor_fields=("post_action_hp",))
    successor_result = CurrentOpponentThreatEvaluatorV1(successor.receipt).evaluate(
        successor.state,
        successor.local_deltas,
        A_FORMULATION,
        fixture=successor,
    )
    assert successor_result.status == B0_DELEGATE
    assert successor_result.fail_closed_reason == SUCCESSOR_VALUE_FORBIDDEN

    terminal_observation = replace(case.observation, terminal_result=1)
    terminal = replace(case, observation=terminal_observation)
    terminal_result = CurrentOpponentThreatEvaluatorV1(terminal.receipt).evaluate(
        terminal_observation, case.request, A_FORMULATION
    )
    assert terminal_result.status == TERMINAL_OVERRIDE
    assert terminal_result.successor_reads == 0


def test_b4_interval_comparison_is_exact_and_nonprobabilistic(fixtures) -> None:
    case = _case(fixtures, "B4-F01")
    result = _evaluate(case, B_FORMULATION)
    assert result.interval_map[case.request.options[0].semantic_fingerprint] == (0, 3)
    assert result.interval_map[case.request.options[1].semantic_fingerprint] == (1, 1)
    assert not hasattr(result, "response_probability")


def test_b4_red001_provenance_graph_binds_every_delta_and_capability(fixtures) -> None:
    case = _case(fixtures, "B4-F01")
    option = case.request.options[0]
    forged_delta = replace(case.local_deltas[option.semantic_fingerprint], receipt_id="fixture-unregistered-delta")
    forged_deltas = dict(case.local_deltas)
    forged_deltas[option.semantic_fingerprint] = forged_delta
    result = CurrentOpponentThreatEvaluatorV1(case.receipt).evaluate(
        case.state, forged_deltas, A_FORMULATION
    )
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason in {"UNREGISTERED_LOCAL_DELTA", "PROVENANCE_GRAPH_INVALID"}

    forged_capability = replace(case.capabilities[0], local_delta_receipt_id="fixture-unregistered-delta")
    result = CurrentOpponentThreatEvaluatorV1(case.receipt).evaluate(
        case.state,
        case.local_deltas,
        A_FORMULATION,
        capabilities=(forged_capability, *case.capabilities[1:]),
    )
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason in {"UNREGISTERED_CAPABILITY", "PROVENANCE_GRAPH_INVALID", "UNREGISTERED_CAPABILITIES"}


def test_b4_red008_whole_receipt_capability_content_is_sealed(fixtures) -> None:
    case = _case(fixtures, "B4-F01")
    forged = _seal_capability(replace(case.capabilities[1], guaranteed_level=0, possible_level=0))
    forged_receipt = replace(case.receipt, capabilities=(case.capabilities[0], forged))
    result = CurrentOpponentThreatEvaluatorV1(forged_receipt).evaluate(
        case.state, case.local_deltas, A_FORMULATION
    )
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason == "RECEIPT_CONTENT_MISMATCH"


def test_b4_red009_public_semantics_and_option_entity_binding_are_strict(fixtures) -> None:
    case = _case(fixtures, "B4-F01")
    capability = case.capabilities[1]
    with pytest.raises(ValueError):
        replace(capability, target_requirements=("HIDDEN_OPPONENT_HAND",))
    with pytest.raises(ValueError):
        replace(capability, status_constraints=("opponent_deck_identity",))
    with pytest.raises(ValueError):
        replace(capability, energy_requirements=(99,))

    forged_capability = _seal_capability(
        replace(capability, source_entity_key="p0:s10", source_card_id=901, target_entity_key="p1:s50")
    )
    forged_receipt = replace(case.receipt, capabilities=(case.capabilities[0], forged_capability))
    forged_result = CurrentOpponentThreatEvaluatorV1(forged_receipt).evaluate(
        case.state, case.local_deltas, A_FORMULATION
    )
    assert forged_result.status == B0_DELEGATE
    assert forged_result.fail_closed_reason == "RECEIPT_CONTENT_MISMATCH"

    option = case.request.options[1]
    changed_option = replace(option, source_ref="p1:s50", source_entity_key="p1:s50")
    changed_option = replace(changed_option, semantic_fingerprint=stable_hash(changed_option.semantic_payload()))
    request = replace(case.request, options=(case.request.options[0], changed_option))
    state = PublicStateV1.from_engine(case.observation, request)
    delta = replace(case.local_deltas[option.semantic_fingerprint], option_fingerprint=changed_option.semantic_fingerprint)
    deltas = {case.request.options[0].semantic_fingerprint: case.local_deltas[case.request.options[0].semantic_fingerprint], changed_option.semantic_fingerprint: delta}
    option_result = CurrentOpponentThreatEvaluatorV1(case.receipt).evaluate(state, deltas, A_FORMULATION)
    assert option_result.status == B0_DELEGATE
    assert option_result.fail_closed_reason == "OPTION_OWNER_MISMATCH"


def test_b4_red002_missing_qualification_and_card_prose_never_rank(fixtures) -> None:
    case = _case(fixtures, "B4-F01")
    incomplete = replace(case.capabilities[0], ready_now=None)
    incomplete_receipt = replace(case.receipt, capabilities=(incomplete, *case.capabilities[1:]))
    result = CurrentOpponentThreatEvaluatorV1(incomplete_receipt).evaluate(
        case.state, case.local_deltas, A_FORMULATION
    )
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason in {"UNKNOWN_THREAT_FIELD", "INCOMPLETE_CAPABILITY", "PARTIAL_CAPABILITY", "RECEIPT_CONTENT_MISMATCH"}

    prose = replace(case.capabilities[0], damage_or_effect_semantics="deal all damage described on the card")
    prose_receipt = replace(case.receipt, capabilities=(prose, *case.capabilities[1:]))
    result = CurrentOpponentThreatEvaluatorV1(prose_receipt).evaluate(
        case.state, case.local_deltas, A_FORMULATION
    )
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason in {"UNQUALIFIED_CAPABILITY", "CARD_PROSE_FORBIDDEN", "PARTIAL_CAPABILITY", "RECEIPT_CONTENT_MISMATCH"}


def test_b4_red003_every_delegated_request_enters_monotonic_lifecycle(fixtures) -> None:
    case = _case(fixtures, "B4-F01")
    unsupported_request = replace(
        case.request,
        selection_type=0,
        selection_context=1,
        options=tuple(
            replace(
                replace(option, selection_type=0, selection_context=1, semantic_fingerprint=""),
                semantic_fingerprint=stable_hash(
                    replace(option, selection_type=0, selection_context=1, semantic_fingerprint="").semantic_payload()
                ),
            )
            for option in case.request.options
        ),
    )
    unsupported_state = PublicStateV1.from_engine(case.observation, unsupported_request)
    evaluator = CurrentOpponentThreatEvaluatorV1(case.receipt)
    first = evaluator.evaluate(unsupported_state, case.local_deltas, A_FORMULATION)
    duplicate = evaluator.evaluate(unsupported_state, case.local_deltas, A_FORMULATION)
    assert first.status == duplicate.status == B0_DELEGATE
    assert first == duplicate
    changed = evaluator.evaluate(case.state, case.local_deltas, A_FORMULATION)
    assert changed.status == B0_DELEGATE
    assert changed.fail_closed_reason in {"STALE_OR_REUSED_REQUEST_IDENTITY", "STALE_SELECTION_SEQUENCE"}

    high_request = replace(unsupported_request, selection_seq=99, request_id="b4-high-delegated")
    high_observation = replace(case.observation, transition_id=99)
    high_state = PublicStateV1.from_engine(high_observation, high_request)
    high = evaluator.evaluate(high_state, case.local_deltas, A_FORMULATION)
    assert high.status == B0_DELEGATE
    low = evaluator.evaluate(case.state, case.local_deltas, A_FORMULATION)
    assert low.status == B0_DELEGATE
    assert low.fail_closed_reason in {"STALE_SELECTION_SEQUENCE", "STALE_OR_REUSED_REQUEST_IDENTITY"}


def test_b4_red003_early_delegations_are_idempotent_and_stale(fixtures) -> None:
    cases = (
        (_case(fixtures, "B4-F04-COMPOUND"), A_FORMULATION),
        (_case(fixtures, "B4-F04-ORDERED"), B_FORMULATION),
        (_case(fixtures, "B4-F04-STOP-ROW"), A_FORMULATION),
    )
    for case, formulation in cases:
        evaluator = CurrentOpponentThreatEvaluatorV1(case.receipt)
        first = evaluator.evaluate(case.state, case.local_deltas, formulation)
        duplicate = evaluator.evaluate(case.state, case.local_deltas, formulation)
        assert first.status == duplicate.status == B0_DELEGATE
        assert first == duplicate
        changed = evaluator.evaluate(case.state, case.local_deltas, A_FORMULATION if formulation == B_FORMULATION else B_FORMULATION)
        assert changed.status == B0_DELEGATE
        assert changed.fail_closed_reason in {"STALE_OR_REUSED_REQUEST_IDENTITY", "STALE_SELECTION_SEQUENCE"}

    case = _case(fixtures, "B4-F01")
    evaluator = CurrentOpponentThreatEvaluatorV1(case.receipt)
    first = evaluator.evaluate(case.state, case.local_deltas, "UNREGISTERED-FORMULATION")
    duplicate = evaluator.evaluate(case.state, case.local_deltas, "UNREGISTERED-FORMULATION")
    assert first == duplicate
    assert first.fail_closed_reason == "UNKNOWN_FORMULATION"
    changed = evaluator.evaluate(case.state, case.local_deltas, A_FORMULATION)
    assert changed.fail_closed_reason in {"STALE_OR_REUSED_REQUEST_IDENTITY", "STALE_SELECTION_SEQUENCE"}


def test_b4_red001_red003_red008_red009_full_receipt_and_global_sequence_binding(fixtures) -> None:
    case = _case(fixtures, "B4-F01")
    option = case.request.options[0]
    delta = case.local_deltas[option.semantic_fingerprint]

    for field, value in (
        ("action_key", "forged-action-key"),
        ("current_public_fields", ("current_source", "forged_public_field")),
        ("action_eligible", False),
    ):
        forged_delta = replace(delta, **{field: value})
        result = CurrentOpponentThreatEvaluatorV1(case.receipt).evaluate(
            case.state,
            {**case.local_deltas, option.semantic_fingerprint: forged_delta},
            A_FORMULATION,
        )
        assert result.status == B0_DELEGATE
        assert result.fail_closed_reason == "RECEIPT_CONTENT_MISMATCH"

    other = _case(fixtures, "B4-F07")
    cross_case_deltas = dict(case.local_deltas)
    cross_case_deltas[option.semantic_fingerprint] = other.local_deltas[option.semantic_fingerprint]
    result = CurrentOpponentThreatEvaluatorV1(case.receipt).evaluate(
        case.state, cross_case_deltas, A_FORMULATION
    )
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason in {"RECEIPT_CONTENT_MISMATCH", "UNREGISTERED_LOCAL_DELTA"}

    forged_receipt = replace(
        case.receipt,
        capabilities=(other.capabilities[0], *case.capabilities[1:]),
    )
    result = CurrentOpponentThreatEvaluatorV1(forged_receipt).evaluate(
        case.state, case.local_deltas, A_FORMULATION
    )
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason == "RECEIPT_CONTENT_MISMATCH"

    capability = case.capabilities[0]
    public_mutations = {
        "target_card_id": capability.target_card_id + 1,
        "source_serial": capability.source_serial + 1,
        "target_serial": capability.target_serial + 1,
        "source_owner": 0,
        "target_owner": 1,
        "source_zone": AREA["BENCH"],
        "target_zone": AREA["BENCH"],
        "source_position": capability.source_position + 1,
        "target_position": capability.target_position + 1,
        "source_hp": capability.source_hp + 1,
        "source_max_hp": capability.source_max_hp + 1,
        "target_hp": capability.target_hp + 1,
        "target_max_hp": capability.target_max_hp + 1,
    }
    for field, value in public_mutations.items():
        forged = _seal_capability(replace(capability, **{field: value}))
        forged_receipt = replace(
            case.receipt,
            capabilities=(forged, *case.capabilities[1:]),
        )
        result = CurrentOpponentThreatEvaluatorV1(forged_receipt).evaluate(
            case.state, case.local_deltas, A_FORMULATION
        )
        assert result.status == B0_DELEGATE
        assert result.fail_closed_reason == "RECEIPT_CONTENT_MISMATCH"

    changed_receipt = replace(case.receipt, canonical_case_sha256="0" * 64)
    result = CurrentOpponentThreatEvaluatorV1(changed_receipt).evaluate(
        case.state, case.local_deltas, A_FORMULATION
    )
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason == "RECEIPT_CONTENT_MISMATCH"

    evaluator = CurrentOpponentThreatEvaluatorV1(case.receipt)
    assert evaluator.evaluate(case.state, case.local_deltas, A_FORMULATION).status == SELECTED
    newer_request = replace(case.request, selection_seq=8, request_id="b4-f01-newer")
    newer_observation = replace(case.observation, transition_id=8)
    newer_state = PublicStateV1.from_engine(newer_observation, newer_request)
    newer = evaluator.evaluate(newer_state, case.local_deltas, A_FORMULATION)
    assert newer.status == B0_DELEGATE
    old = evaluator.evaluate(case.state, case.local_deltas, A_FORMULATION)
    assert old.status == B0_DELEGATE
    assert old.fail_closed_reason == "STALE_SELECTION_SEQUENCE"


def test_b4_red004_config_digest_is_content_authority(fixtures) -> None:
    config_path = Path(fixtures.config_path)
    value = json.loads(config_path.read_text(encoding="utf-8"))
    value["fixture_metadata_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        materialize_b4_fixture_data(value, config_path=config_path)
    value = json.loads(config_path.read_text(encoding="utf-8"))
    value["dependency_manifest"]["src/ptcg_rl/g1/models.py"] = "0" * 64
    with pytest.raises(ValueError):
        materialize_b4_fixture_data(value, config_path=config_path)


def test_b4_red005_no_response_requires_exact_public_census_receipt(fixtures) -> None:
    case = _case(fixtures, "B4-F01")
    option = case.request.options[0]
    delta = replace(
        case.local_deltas[option.semantic_fingerprint],
        remaining_capability_ids=(),
        census_complete=True,
        census_receipt_id="fixture-unregistered-census",
    )
    deltas = dict(case.local_deltas)
    deltas[option.semantic_fingerprint] = delta
    no_response_receipt = replace(
        case.receipt, capabilities=(), local_delta_receipt_ids=(delta.receipt_id,)
    )
    request = replace(case.request, options=(option,))
    state = PublicStateV1.from_engine(case.observation, request)
    deltas = {option.semantic_fingerprint: delta}
    result = CurrentOpponentThreatEvaluatorV1(no_response_receipt).evaluate(state, deltas, A_FORMULATION)
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason in {"INCOMPLETE_PUBLIC_CENSUS", "UNKNOWN_THREAT_FIELD", "UNREGISTERED_CENSUS_RECEIPT", "RECEIPT_CONTENT_MISMATCH"}

    registered_delta = _seal_delta(replace(delta, census_receipt_id="fixture-census-f01-x"))
    deltas = {option.semantic_fingerprint: registered_delta}
    census = PublicCensusReceiptV1(
        receipt_id="fixture-census-f01-x",
        observation_hash=state.public_hash,
        source_scope=(option.source_entity_key,),
        target_scope=(option.target_entity_key,),
        checks=("VISIBLE_SOURCE_CENSUS", "TARGET_LEGALITY", "ENERGY_REQUIREMENTS", "STATUS_CONSTRAINTS"),
        local_delta_receipt_id=registered_delta.receipt_id,
    )
    registered_receipt = replace(
        no_response_receipt,
        local_delta_content_sha256={registered_delta.receipt_id: registered_delta.content_sha256},
        census_receipts=(census,),
        canonical_case_sha256="0" * 64,
    )
    registered_case = _seal_case(replace(
        case,
        request=request,
        state=state,
        receipt=registered_receipt,
        capabilities=(),
        local_deltas={option.semantic_fingerprint: registered_delta},
    ))
    result = CurrentOpponentThreatEvaluatorV1(registered_case.receipt).evaluate(
        registered_case.state, registered_case.local_deltas, A_FORMULATION
    )
    assert result.status == SELECTED
    assert result.interval_map[option.semantic_fingerprint] == (0, 0)


def test_b4_red006_scale_and_numeric_types_are_strict() -> None:
    kwargs = dict(
        schema_version=1,
        scale_id="fixture-threat-level-scale-v1",
        lower_is_safer=True,
        scope=FIXTURE_ONLY,
    )
    with pytest.raises(ValueError):
        ThreatLevelScaleV1(**kwargs, levels=((0.0, "NO"), (1, "LOW")))
    with pytest.raises(ValueError):
        ThreatLevelScaleV1(**kwargs, levels=((0, "NO"), (1, "NO")))
    with pytest.raises(ValueError):
        ThreatLevelScaleV1(**{**kwargs, "schema_version": True}, levels=((0, "NO"),))
    with pytest.raises(ValueError):
        ThreatLevelScaleV1.from_dict({**kwargs, "levels": [[0, "NO"], [1, "LOW"]], "schema_version": "1"})


def test_b4_red006_nan_and_inf_capability_levels_fail_closed(fixtures) -> None:
    case = _case(fixtures, "B4-F01")
    with pytest.raises(ValueError):
        replace(case.capabilities[0], possible_level=math.nan)
    with pytest.raises(ValueError):
        replace(case.capabilities[0], guaranteed_level=math.inf)


def test_b4_red007_fresh_process_covers_all_cases_formulations_permutations_and_mirror(fixtures) -> None:
    repo = Path(__file__).resolve().parents[2]
    script = """
from dataclasses import replace
from itertools import permutations
from ptcg_rl.deterministic.b4_opponent_threat import (
    A_FORMULATION, B_FORMULATION, CurrentOpponentThreatEvaluatorV1,
    _seal_capability, load_b4_fixtures, mirror_b4_case,
)
from ptcg_rl.deterministic.state import PublicStateV1
from ptcg_rl.g1.models import stable_hash

bundle = load_b4_fixtures()
assert len(bundle.cases) == 11
for original in bundle.cases:
    for case in (original, mirror_b4_case(original)):
        for formulation in (A_FORMULATION, B_FORMULATION):
            result = CurrentOpponentThreatEvaluatorV1(case.receipt).evaluate_case(case, formulation)
            assert result.status in {"SELECTED", "B0_DELEGATE"}
        for ordering in permutations(range(len(case.request.options))):
            request = replace(case.request, options=tuple(case.request.options[index] for index in ordering))
            state = PublicStateV1.from_engine(case.observation, request)
            permuted = replace(case, request=request, state=state)
            result = CurrentOpponentThreatEvaluatorV1(permuted.receipt).evaluate_case(permuted, A_FORMULATION)
            assert result.status in {"SELECTED", "B0_DELEGATE"}
        for capability_index, capability in enumerate(case.capabilities):
            if capability.guaranteed_level is not None and capability.possible_level is not None:
                forged = _seal_capability(replace(capability, guaranteed_level=0, possible_level=0))
                forged_capabilities = list(case.capabilities)
                forged_capabilities[capability_index] = forged
                forged_receipt = replace(case.receipt, capabilities=tuple(forged_capabilities))
                forged_result = CurrentOpponentThreatEvaluatorV1(forged_receipt).evaluate(
                    case.state, case.local_deltas, A_FORMULATION
                )
                assert forged_result.status == "B0_DELEGATE"
                assert forged_result.fail_closed_reason in {
                    "RECEIPT_CONTENT_MISMATCH", "COMPOUND_UNSUPPORTED", "ORDERED_UNSUPPORTED",
                    "STOP_UNRESOLVED", "DUPLICATE_SEMANTICS",
                }
                break
        for option in case.request.options:
            if option.source_kind != "ENTITY":
                continue
            changed_source = f"p{1 - case.request.acting_player}:s50"
            changed_option = replace(option, source_ref=changed_source, source_entity_key=changed_source)
            changed_option = replace(changed_option, semantic_fingerprint=stable_hash(changed_option.semantic_payload()))
            changed_options = tuple(changed_option if item.semantic_fingerprint == option.semantic_fingerprint else item for item in case.request.options)
            try:
                changed_request = replace(case.request, options=changed_options)
                changed_state = PublicStateV1.from_engine(case.observation, changed_request)
                changed_delta = replace(case.local_deltas[option.semantic_fingerprint], option_fingerprint=changed_option.semantic_fingerprint)
            except ValueError:
                break
            changed_deltas = dict(case.local_deltas)
            changed_deltas.pop(option.semantic_fingerprint)
            changed_deltas[changed_option.semantic_fingerprint] = changed_delta
            changed_result = CurrentOpponentThreatEvaluatorV1(case.receipt).evaluate(changed_state, changed_deltas, A_FORMULATION)
            assert changed_result.status == "B0_DELEGATE"
            assert changed_result.fail_closed_reason in {
                "OPTION_OWNER_MISMATCH", "INCOMPLETE_THREAT_COVERAGE", "COMPOUND_UNSUPPORTED",
                "ORDERED_UNSUPPORTED", "STOP_UNRESOLVED", "DUPLICATE_SEMANTICS",
            }
            break
print("fresh-process-b4-matrix-ok")
"""
    completed = subprocess.run(
        [sys.executable, "-c", script], cwd=repo, capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "fresh-process-b4-matrix-ok"


def test_b4_red010_fresh_process_receipt_delta_snapshot_and_sequence_matrix(fixtures) -> None:
    repo = Path(__file__).resolve().parents[2]
    script = """
from dataclasses import replace
from ptcg_rl.deterministic.b4_opponent_threat import (
    A_FORMULATION, B0_DELEGATE, CurrentOpponentThreatEvaluatorV1,
    _seal_capability, load_b4_fixtures, mirror_b4_case,
)
from ptcg_rl.deterministic.state import PublicStateV1

bundle = load_b4_fixtures()
base = next(case for case in bundle.cases if case.case_id.startswith("B4-F01"))
donor = next(case for case in bundle.cases if case.case_id.startswith("B4-F07"))
for original in (base, mirror_b4_case(base)):
    for field, value in (
        ("action_key", "forged-action-key"),
        ("current_public_fields", ("current_source", "forged_public_field")),
        ("action_eligible", False),
    ):
        option = original.request.options[0]
        forged_delta = replace(original.local_deltas[option.semantic_fingerprint], **{field: value})
        deltas = dict(original.local_deltas)
        deltas[option.semantic_fingerprint] = forged_delta
        result = CurrentOpponentThreatEvaluatorV1(original.receipt).evaluate(
            original.state, deltas, A_FORMULATION
        )
        assert result.status == B0_DELEGATE
        assert result.fail_closed_reason == "RECEIPT_CONTENT_MISMATCH"

    capability = original.capabilities[0] if original.capabilities else None
    if capability is not None:
        forged = _seal_capability(replace(capability, source_hp=capability.source_hp + 1))
        receipt = replace(original.receipt, capabilities=(forged, *original.capabilities[1:]))
        result = CurrentOpponentThreatEvaluatorV1(receipt).evaluate(
            original.state, original.local_deltas, A_FORMULATION
        )
        assert result.status == B0_DELEGATE
        assert result.fail_closed_reason == "RECEIPT_CONTENT_MISMATCH"

    expected = dict(original.expected)
    expected[A_FORMULATION] = B0_DELEGATE
    altered = replace(original, expected=expected)
    result = CurrentOpponentThreatEvaluatorV1(original.receipt).evaluate_case(altered, A_FORMULATION)
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason == "RECEIPT_CONTENT_MISMATCH"

cross_delta = next(iter(base.local_deltas))
injected = dict(base.local_deltas)
injected[cross_delta] = donor.local_deltas[cross_delta]
result = CurrentOpponentThreatEvaluatorV1(base.receipt).evaluate(base.state, injected, A_FORMULATION)
assert result.status == B0_DELEGATE
assert result.fail_closed_reason in {"RECEIPT_CONTENT_MISMATCH", "UNREGISTERED_LOCAL_DELTA"}
cross_receipt = replace(base.receipt, capabilities=(donor.capabilities[0], *base.capabilities[1:]))
result = CurrentOpponentThreatEvaluatorV1(cross_receipt).evaluate(base.state, base.local_deltas, A_FORMULATION)
assert result.status == B0_DELEGATE
assert result.fail_closed_reason == "RECEIPT_CONTENT_MISMATCH"

evaluator = CurrentOpponentThreatEvaluatorV1(base.receipt)
assert evaluator.evaluate(base.state, base.local_deltas, A_FORMULATION).status == "SELECTED"
new_request = replace(base.request, selection_seq=8, request_id="b4-fresh-newer")
new_observation = replace(base.observation, transition_id=8)
new_state = PublicStateV1.from_engine(new_observation, new_request)
assert evaluator.evaluate(new_state, base.local_deltas, A_FORMULATION).status == B0_DELEGATE
old = evaluator.evaluate(base.state, base.local_deltas, A_FORMULATION)
assert old.status == B0_DELEGATE
assert old.fail_closed_reason == "STALE_SELECTION_SEQUENCE"
print("fresh-process-b4-receipt-binding-ok")
"""
    completed = subprocess.run(
        [sys.executable, "-c", script], cwd=repo, capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "fresh-process-b4-receipt-binding-ok"


def test_b4_red007_hidden_enum_and_provenance_mutations_delegate_across_all_cases(fixtures) -> None:
    for case in fixtures.cases:
        forged_manifest = dict(case.receipt.provenance_manifest)
        forged_manifest["engine_hash"] = "0" * 64
        forged_receipt = replace(case.receipt, provenance_manifest=forged_manifest)
        for formulation in (A_FORMULATION, B_FORMULATION):
            result = CurrentOpponentThreatEvaluatorV1(forged_receipt).evaluate_case(case, formulation)
            assert result.status == B0_DELEGATE

        for option in case.request.options:
            delta = case.local_deltas[option.semantic_fingerprint]
            with pytest.raises(ValueError):
                replace(delta, current_public_fields=("hidden_opponent_hand",))
            successor_delta = replace(delta, successor_fields=("future_state",))
            changed_deltas = dict(case.local_deltas)
            changed_deltas[option.semantic_fingerprint] = successor_delta
            for formulation in (A_FORMULATION, B_FORMULATION):
                result = CurrentOpponentThreatEvaluatorV1(case.receipt).evaluate(
                    case.state, changed_deltas, formulation
                )
                assert result.status == B0_DELEGATE
            break

        for capability in case.capabilities:
            with pytest.raises(ValueError):
                replace(capability, response_class="UNKNOWN_ENUM")
