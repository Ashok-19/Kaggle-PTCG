"""Fixture-only Phase B3 resource/prize ledger regressions.

These tests deliberately stop at the public ``PublicStateV1`` boundary.  A
passing B3 fixture proves only the arithmetic and fail-closed evaluator
contract; it is not native capability or production-policy evidence.
"""

from __future__ import annotations

import json
from dataclasses import replace
from fractions import Fraction

import pytest

from ptcg_rl.deterministic.b3_ledger import (
    A_FORMULATION,
    B_FORMULATION,
    AMBIGUOUS,
    B0_DELEGATE,
    SELECTED,
    TERMINAL_OVERRIDE,
    FIXTURE_ONLY,
    CurrentResourceLedgerEvaluatorV1,
    DeckoutReceiptV1,
    RecoverabilityReceiptV1,
    _deckout_predicate_digest,
    load_b3_fixtures,
    mirror_b3_case,
    semantic_permutation_suite,
    exact_multivariate_probability,
)
from ptcg_rl.g1.actions import CompoundActionBuilder
from ptcg_rl.g1.models import stable_hash


@pytest.fixture(scope="module")
def fixtures():
    return load_b3_fixtures()


def _case(fixtures, case_id: str):
    return next(item for item in fixtures.cases if item.case_id == case_id)


def _evaluate(case, formulation: str):
    evaluator = CurrentResourceLedgerEvaluatorV1(case.receipt)
    return evaluator.evaluate(case.state, case.ledger, case.local_deltas, case.route, formulation)


def test_b3_f01_materializes_public_state_and_true_formulation_divergence(fixtures) -> None:
    case = _case(fixtures, "B3-F01-RESERVE-ODDS-DIVERGENCE")
    assert case.receipt.candidate_deck_sha256 == "7af2d7e111c084da535b89758730b3fd6cbb7c0543a9444499c5b61efdc8aecd"
    assert dict(case.receipt.candidate_deck_counts) == {
        "3": 34, "721": 2, "722": 4, "723": 4, "1121": 4,
        "1126": 1, "1192": 4, "1227": 4, "1262": 3,
    }
    assert case.state.observation == case.observation
    assert case.state.request == case.request
    a = _evaluate(case, A_FORMULATION)
    b = _evaluate(case, B_FORMULATION)
    assert a.status == b.status == SELECTED
    assert a.chosen_option_fingerprints != b.chosen_option_fingerprints
    assert a.chosen_semantic_action_key != b.chosen_semantic_action_key
    assert a.probability_by_option
    assert a.reserve_by_option
    assert a.complete_option_set_digest == case.complete_option_set_digest
    assert b.probability_by_option
    assert b.probability_by_option[0][1:] == (Fraction(1, 5).numerator, Fraction(1, 5).denominator)
    assert b.probability_by_option[1][1:] == (Fraction(8, 15).numerator, Fraction(8, 15).denominator)
    assert all(item.hard_reserve_ok for item in b.candidates)
    assert a.authority == b.authority == "EXPERIMENTAL_RESOURCE_LEDGER_FIXTURE"
    assert a.receipt_scope == b.receipt_scope == FIXTURE_ONLY


@pytest.mark.parametrize("formulation", [A_FORMULATION, B_FORMULATION])
def test_b3_f01_32_semantic_permutations_are_invariant(fixtures, formulation: str) -> None:
    case = _case(fixtures, "B3-F01-RESERVE-ODDS-DIVERGENCE")
    expected = _evaluate(case, formulation).chosen_option_fingerprints
    evaluator = CurrentResourceLedgerEvaluatorV1(case.receipt)
    outcomes = set()
    for permutation in semantic_permutation_suite(len(case.request.options), 32):
        request = replace(case.request, options=tuple(case.request.options[index] for index in permutation))
        state = replace(case.state, request=request)
        evaluator.reset(state.battle_id, state.acting_player, reason="permutation")
        result = evaluator.evaluate(state, case.ledger, case.local_deltas, case.route, formulation)
        outcomes.add((result.status, result.chosen_option_fingerprints))
    assert outcomes == {(SELECTED, expected)}


def test_b3_f02_revealed_prize_copy_is_removed_without_double_count(fixtures) -> None:
    open_case = _case(fixtures, "B3-F02-OPEN")
    revealed_case = _case(fixtures, "B3-F02-REVEALED-PRIZE-REMOVAL")
    open_ledger = open_case.ledger
    revealed_ledger = revealed_case.ledger
    assert open_ledger.unknown_by_role["route_out"] == 2
    assert revealed_ledger.unknown_by_role["route_out"] == 1
    assert revealed_ledger.known_inaccessible_by_role["route_out"] == 1
    assert len(revealed_ledger.physical_copy_receipts) == len(
        {item.physical_id for item in revealed_ledger.physical_copy_receipts}
    )
    assert len(revealed_ledger.reveal_events) == 1
    a = _evaluate(revealed_case, A_FORMULATION)
    b = _evaluate(revealed_case, B_FORMULATION)
    assert a.status == b.status == SELECTED
    assert all(item.known_inaccessible_total >= 1 for item in a.candidates)
    assert all(item.unknown_route_out == 1 for item in b.candidates)


def test_b3_f03_irreplaceable_discard_preserves_unique_resource(fixtures) -> None:
    case = _case(fixtures, "B3-F03-IRREPLACEABLE-DISCARD")
    a = _evaluate(case, A_FORMULATION)
    b = _evaluate(case, B_FORMULATION)
    assert a.status == b.status == SELECTED
    assert a.chosen_semantic_action_key == ("DISCARD_REPLACEABLE",)
    assert b.chosen_semantic_action_key == ("DISCARD_REPLACEABLE",)
    assert all(item.hard_reserve_ok for item in a.candidates)


def test_b3_f04_low_opponent_deck_count_does_not_prove_deckout(fixtures) -> None:
    case = _case(fixtures, "B3-F04-DECKOUT-NOT-LOW-COUNT")
    for formulation in (A_FORMULATION, B_FORMULATION):
        result = _evaluate(case, formulation)
        assert result.status == B0_DELEGATE
        assert result.fail_closed_reason == "DECKOUT_PROOF_MISSING"
        assert result.chosen_option_fingerprints == ()


def test_b3_f05_complete_options_singletons_stop_and_compounds(fixtures) -> None:
    mandatory = _case(fixtures, "B3-F05-MANDATORY-SINGLETON")
    assert _evaluate(mandatory, A_FORMULATION).status == SELECTED

    optional = _case(fixtures, "B3-F05-OPTIONAL-STOP")
    result = _evaluate(optional, A_FORMULATION)
    assert result.status == SELECTED
    assert result.stopped_early
    assert result.chosen_option_fingerprints == ()
    trace = result.stop_trace
    assert trace is not None
    assert trace.stopped_early
    assert trace.submitted_original_indices == ()
    assert trace.steps[-1].chosen_token == "STOP"

    ordered = _case(fixtures, "B3-F05-ORDERED-MULTI")
    unordered = _case(fixtures, "B3-F05-UNORDERED-MULTI")
    assert _evaluate(ordered, A_FORMULATION).status == B0_DELEGATE
    assert _evaluate(unordered, A_FORMULATION).status == B0_DELEGATE
    assert _evaluate(ordered, A_FORMULATION).fail_closed_reason == "UNSUPPORTED_COUNT_OR_ORDERING"
    assert _evaluate(unordered, A_FORMULATION).fail_closed_reason == "UNSUPPORTED_COUNT_OR_ORDERING"


def test_b3_f06_lifecycle_and_player_mirror_are_isolated(fixtures) -> None:
    case = _case(fixtures, "B3-F06-LIFECYCLE-PLAYER-MIRROR")
    evaluator = CurrentResourceLedgerEvaluatorV1(case.receipt)
    first = evaluator.evaluate(case.state, case.ledger, case.local_deltas, case.route, A_FORMULATION)
    duplicate = evaluator.evaluate(case.state, case.ledger, case.local_deltas, case.route, A_FORMULATION)
    assert duplicate == first
    changed = replace(case.request, request_id="b3-stale-request")
    changed_state = replace(case.state, request=changed)
    assert evaluator.evaluate(changed_state, case.ledger, case.local_deltas, case.route, A_FORMULATION).status == B0_DELEGATE
    evaluator.reset(case.state.battle_id, 0, reason="error")
    assert evaluator.evaluate(case.state, case.ledger, case.local_deltas, case.route, A_FORMULATION).status == SELECTED
    evaluator.reset(case.state.battle_id, 0, reason="worker_replacement")
    assert evaluator.evaluate(case.state, case.ledger, case.local_deltas, case.route, A_FORMULATION).status == SELECTED

    mirrored = mirror_b3_case(case)
    mirrored_result = _evaluate(mirrored, A_FORMULATION)
    assert mirrored_result.status == SELECTED
    assert mirrored_result.chosen_semantic_action_key == first.chosen_semantic_action_key
    assert len(mirrored_result.chosen_option_fingerprints) == len(first.chosen_option_fingerprints)


def test_b3_f01_exact_multivariate_probability_is_rational() -> None:
    assert exact_multivariate_probability(
        {"hit": 2, "blank": 8}, horizon=1, requirements={"hit": 1}
    ) == Fraction(1, 5)
    assert exact_multivariate_probability(
        {"hit": 2, "blank": 8}, horizon=3, requirements={"hit": 1}
    ) == Fraction(8, 15)
    assert exact_multivariate_probability(
        {"a": 2, "b": 2, "blank": 4}, horizon=2, requirements={"a": 1, "b": 1}
    ) == Fraction(1, 7)


def test_b3_hidden_allocation_changes_ordering_delegates(fixtures) -> None:
    case = _case(fixtures, "B3-F01-RESERVE-ODDS-DIVERGENCE")
    altered = replace(
        case.local_deltas[case.request.options[1].semantic_fingerprint],
        allocation_states=(
            {"route_out": 2, "blank": 8},
            {"route_out": 0, "blank": 10},
        ),
    )
    deltas = dict(case.local_deltas)
    deltas[case.request.options[1].semantic_fingerprint] = altered
    result = CurrentResourceLedgerEvaluatorV1(case.receipt).evaluate(
        case.state, case.ledger, deltas, case.route, B_FORMULATION
    )
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason == "HIDDEN_ALLOCATION_CHANGES_ORDERING"


def test_b3_non_equivalent_strategic_tie_is_ambiguous(fixtures) -> None:
    case = _case(fixtures, "B3-F03-IRREPLACEABLE-DISCARD")
    deltas = dict(case.local_deltas)
    for fingerprint, label in (
        (case.request.options[0].semantic_fingerprint, "TIE_A"),
        (case.request.options[1].semantic_fingerprint, "TIE_B"),
    ):
        deltas[fingerprint] = replace(
            deltas[fingerprint],
            action_label=label,
            consume_by_role={},
            opportunity_cost=0,
            opportunity_cost_by_role={},
        )
    result = CurrentResourceLedgerEvaluatorV1(case.receipt).evaluate(
        case.state, case.ledger, deltas, case.route, A_FORMULATION
    )
    assert result.status == AMBIGUOUS
    assert result.fail_closed_reason == "AMBIGUOUS_NON_EQUIVALENT_TIE"


def test_b3_boundary_rejects_duplicate_or_nonfinite_fixture_fields(fixtures) -> None:
    case = _case(fixtures, "B3-F01-RESERVE-ODDS-DIVERGENCE")
    with pytest.raises(ValueError, match="physical copy"):
        replace(
            case.ledger,
            physical_copy_receipts=case.ledger.physical_copy_receipts
            + (case.ledger.physical_copy_receipts[0],),
        )
    poisoned = replace(
        case.local_deltas[case.request.options[0].semantic_fingerprint],
        opportunity_cost=float("nan"),
    )
    deltas = dict(case.local_deltas)
    deltas[case.request.options[0].semantic_fingerprint] = poisoned
    result = CurrentResourceLedgerEvaluatorV1(case.receipt).evaluate(
        case.state, case.ledger, deltas, case.route, A_FORMULATION
    )
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason == "NONFINITE_OR_INVALID_LOCAL_DELTA"


def test_b3_terminal_is_checked_before_stale_request() -> None:
    from ptcg_rl.deterministic.b3_ledger import load_b3_fixtures

    case = next(item for item in load_b3_fixtures().cases if item.case_id.startswith("B3-F01"))
    terminal = replace(case.state.observation, terminal_result=1)
    from ptcg_rl.deterministic.state import PublicStateV1

    terminal_state = PublicStateV1.from_engine(terminal, object())
    result = CurrentResourceLedgerEvaluatorV1(case.receipt).evaluate(
        terminal_state, object(), {}, case.route, A_FORMULATION
    )
    assert result.status == TERMINAL_OVERRIDE


def test_b3_stop_builder_is_real_decoder_token(fixtures) -> None:
    optional = _case(fixtures, "B3-F05-OPTIONAL-STOP")
    builder = CompoundActionBuilder(optional.request)
    builder.stop()
    action = builder.build()
    assert action.stopped_early
    assert action.submitted_original_indices == ()
    assert action.steps[-1].chosen_token == "STOP"


def test_b3_diagnostics_separate_selection_delegation_and_terminal(fixtures) -> None:
    case = _case(fixtures, "B3-F01-RESERVE-ODDS-DIVERGENCE")
    evaluator = CurrentResourceLedgerEvaluatorV1(case.receipt)
    selected = evaluator.evaluate(case.state, case.ledger, case.local_deltas, case.route, A_FORMULATION)
    assert selected.status == SELECTED
    delegated = _case(fixtures, "B3-F05-UNORDERED-MULTI")
    assert evaluator.evaluate(delegated.state, delegated.ledger, delegated.local_deltas, delegated.route, A_FORMULATION).status == B0_DELEGATE
    from ptcg_rl.deterministic.state import PublicStateV1

    terminal_state = PublicStateV1.from_engine(replace(case.observation, terminal_result=1), object())
    assert evaluator.evaluate(terminal_state, object(), {}, case.route, A_FORMULATION).status == TERMINAL_OVERRIDE
    assert evaluator.diagnostics.requests == 3
    assert evaluator.diagnostics.selected == 1
    assert evaluator.diagnostics.delegated == 1
    assert evaluator.diagnostics.terminal_overrides == 1


def test_b3_missing_prizestatic_delegates_without_native_inference(fixtures) -> None:
    case = _case(fixtures, "B3-F01-RESERVE-ODDS-DIVERGENCE")
    receipt = replace(case.receipt, prize_static=())
    result = CurrentResourceLedgerEvaluatorV1(receipt).evaluate(
        case.state, case.ledger, case.local_deltas, case.route, A_FORMULATION
    )
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason == "MISSING_PRIZESTATIC"


def test_b3_fixture_metadata_is_version_bound(fixtures) -> None:
    config = json.loads(fixtures.config_path.read_text(encoding="utf-8"))
    config["common_public_state"]["entities"][0]["metadata_ref"] = "card:3@" + "0" * 64
    from ptcg_rl.deterministic.b3_ledger import materialize_b3_fixture_data

    with pytest.raises(ValueError, match="FIXTURE_METADATA_VERSION_MISMATCH"):
        materialize_b3_fixture_data(config)


def test_b3_red001_local_delta_mutation_is_stale_for_same_request(fixtures) -> None:
    case = _case(fixtures, "B3-F01-RESERVE-ODDS-DIVERGENCE")
    evaluator = CurrentResourceLedgerEvaluatorV1(case.receipt)
    first = evaluator.evaluate(case.state, case.ledger, case.local_deltas, case.route, A_FORMULATION)
    assert first.status == SELECTED
    fingerprint = case.request.options[0].semantic_fingerprint
    mutated = replace(case.local_deltas[fingerprint], action_label="MUTATED_AFTER_DECISION")
    deltas = dict(case.local_deltas)
    deltas[fingerprint] = mutated
    result = evaluator.evaluate(case.state, case.ledger, deltas, case.route, A_FORMULATION)
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason == "STALE_OR_REUSED_REQUEST_IDENTITY"
    changed_request = replace(case.request, remain_energy_cost=1)
    changed_state = replace(case.state, request=changed_request)
    request_result = evaluator.evaluate(
        changed_state, case.ledger, case.local_deltas, case.route, A_FORMULATION
    )
    assert request_result.status == B0_DELEGATE
    assert request_result.fail_closed_reason == "STALE_OR_REUSED_REQUEST_IDENTITY"


def test_b3_red002_optional_stop_validates_every_option_before_stopping(fixtures) -> None:
    case = _case(fixtures, "B3-F05-OPTIONAL-STOP")
    original = case.request.options[0]
    unsupported = replace(
        original,
        option_type=9,
        option_name="EVOLVE",
        choice_role="EVOLVE",
    )
    unsupported = replace(unsupported, semantic_fingerprint=stable_hash(unsupported.semantic_payload()))
    request = replace(case.request, options=(unsupported,))
    state = replace(case.state, request=request)
    delta = replace(
        case.local_deltas[original.semantic_fingerprint],
        option_fingerprint=unsupported.semantic_fingerprint,
    )
    result = CurrentResourceLedgerEvaluatorV1(case.receipt).evaluate(
        state, case.ledger, {unsupported.semantic_fingerprint: delta}, case.route, A_FORMULATION
    )
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason == "COMPLETE_OPTION_SET_UNSUPPORTED"


def test_b3_red003_rejects_consumption_beyond_known_capacity(fixtures) -> None:
    case = _case(fixtures, "B3-F01-RESERVE-ODDS-DIVERGENCE")
    fingerprint = case.request.options[1].semantic_fingerprint
    deltas = dict(case.local_deltas)
    deltas[fingerprint] = replace(
        deltas[fingerprint], consume_by_role={"replaceable_search": 99}
    )
    result = _evaluate(replace(case, local_deltas=deltas), A_FORMULATION)
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason == "IMPOSSIBLE_LOCAL_DELTA_OVERCONSUMPTION"


@pytest.mark.parametrize("proof_field", ["draw_obligation_known", "recovery_known", "alternate_prize_route_known"])
def test_b3_red004_route_proof_uncertainty_delegates(fixtures, proof_field: str) -> None:
    case = _case(fixtures, "B3-F01-RESERVE-ODDS-DIVERGENCE")
    route = replace(case.route, **{proof_field: False})
    result = _evaluate(replace(case, route=route), A_FORMULATION)
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason == "ROUTE_PROOF_MISSING"


def test_b3_red005_deckout_requires_exact_sealed_receipt(fixtures) -> None:
    case = _case(fixtures, "B3-F04-DECKOUT-NOT-LOW-COUNT")
    route = replace(
        case.route,
        draw_obligation_known=True,
        recovery_known=True,
        alternate_prize_route_known=True,
        deckout_receipt_id="unsealed-deckout-proof",
    )
    forged_proof = DeckoutReceiptV1(
        receipt_id="unsealed-deckout-proof",
        schema_version=1,
        route_id=route.route_id,
        opponent_deck_count=route.opponent_deck_count,
        predicate_sha256=_deckout_predicate_digest(route),
    )
    forged_receipt = replace(
        case.receipt,
        deckout_receipt_ids=(forged_proof.receipt_id,),
        deckout_receipts=(forged_proof,),
    )
    with pytest.raises(ValueError, match="canonical"):
        CurrentResourceLedgerEvaluatorV1(forged_receipt)

    count_mismatch_route = replace(
        case.route,
        draw_obligation_known=True,
        recovery_known=True,
        alternate_prize_route_known=True,
    )
    result = CurrentResourceLedgerEvaluatorV1(case.receipt).evaluate(
        case.state, case.ledger, case.local_deltas, count_mismatch_route, A_FORMULATION
    )
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason == "DECKOUT_PROOF_MISSING"


def test_b3_red006_physical_and_reveal_receipts_are_unique_monotonic_and_bound(fixtures) -> None:
    case = _case(fixtures, "B3-F01-RESERVE-ODDS-DIVERGENCE")
    copies = list(case.ledger.physical_copy_receipts)
    copies[1] = replace(copies[1], source_digest=copies[0].source_digest)
    with pytest.raises(ValueError, match="duplicate source digest"):
        replace(case.ledger, physical_copy_receipts=tuple(copies))

    revealed = _case(fixtures, "B3-F02-REVEALED-PRIZE-REMOVAL")
    event = revealed.ledger.reveal_events[0]
    with pytest.raises(ValueError, match="no-op"):
        replace(event, before_category="PUBLIC_INACCESSIBLE")
    with pytest.raises(ValueError, match="does not resolve"):
        replace(
            revealed.ledger,
            reveal_events=(replace(event, before_category="PUBLIC_DISCARD_OR_RECOVERABLE"),),
        )
    with pytest.raises(ValueError, match="does not resolve"):
        replace(
            revealed.ledger,
            reveal_events=(replace(event, source_digest="f" * 64),),
        )
    with pytest.raises(ValueError, match="missing its reveal event"):
        replace(revealed.ledger, reveal_events=())


def test_b3_red007_metadata_digest_is_recomputed_from_public_records(fixtures) -> None:
    from ptcg_rl.deterministic.b3_ledger import materialize_b3_fixture_data

    config = json.loads(fixtures.config_path.read_text(encoding="utf-8"))
    entity = config["common_public_state"]["entities"][0]
    entity["card_id"] = 4
    entity["metadata_ref"] = "card:4@" + config["fixture_metadata_sha256"]
    with pytest.raises(ValueError, match="FIXTURE_METADATA_DIGEST_MISMATCH"):
        materialize_b3_fixture_data(config)


def test_b3_red008_allocation_worlds_bind_to_public_capacity_and_measure(fixtures) -> None:
    case = _case(fixtures, "B3-F01-RESERVE-ODDS-DIVERGENCE")
    fingerprint = case.request.options[0].semantic_fingerprint
    deltas = dict(case.local_deltas)
    deltas[fingerprint] = replace(
        deltas[fingerprint], allocation_states=({"route_out": 2, "blank": 1},)
    )
    result = _evaluate(replace(case, local_deltas=deltas), A_FORMULATION)
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason == "ALLOCATION_CAPACITY_MISMATCH"

    unsealed = replace(
        case.local_deltas[fingerprint],
        probability_counts={"route_out": 3, "blank": 7},
        allocation_states=({"route_out": 3, "blank": 7},),
    )
    unsealed_deltas = dict(case.local_deltas)
    unsealed_deltas[fingerprint] = unsealed
    unsealed_result = _evaluate(replace(case, local_deltas=unsealed_deltas), A_FORMULATION)
    assert unsealed_result.status == B0_DELEGATE
    assert unsealed_result.fail_closed_reason == "UNSEALED_ALLOCATION_MEASURE"

    duplicate_world = replace(
        case.local_deltas[fingerprint],
        allocation_states=({"route_out": 2, "blank": 8}, {"route_out": 2, "blank": 8}),
    )
    duplicate_deltas = dict(case.local_deltas)
    duplicate_deltas[fingerprint] = duplicate_world
    duplicate_result = _evaluate(replace(case, local_deltas=duplicate_deltas), A_FORMULATION)
    assert duplicate_result.status == B0_DELEGATE
    assert duplicate_result.fail_closed_reason == "DUPLICATE_ALLOCATION_WORLD"


def test_b3_red009_discard_is_not_recoverable_without_qualification(fixtures) -> None:
    case = _case(fixtures, "B3-F03-IRREPLACEABLE-DISCARD")
    copies = list(case.ledger.physical_copy_receipts)
    copies[1] = replace(copies[1], category="PUBLIC_DISCARD_OR_RECOVERABLE")
    ledger = replace(
        case.ledger,
        known_usable_by_role={"unique_resource": 1, "replaceable_card": 0, "route_out": 0},
        known_discard_by_role={"replaceable_card": 1},
        physical_copy_receipts=tuple(copies),
    )
    result = _evaluate(replace(case, ledger=ledger), A_FORMULATION)
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason == "UNQUALIFIED_RECOVERABILITY"


def test_b3_qualified_recoverability_is_the_only_discard_capacity(fixtures) -> None:
    case = _case(fixtures, "B3-F03-IRREPLACEABLE-DISCARD")
    copies = list(case.ledger.physical_copy_receipts)
    copies[1] = replace(copies[1], category="PUBLIC_DISCARD_OR_RECOVERABLE")
    ledger = replace(
        case.ledger,
        known_usable_by_role={"unique_resource": 1, "replaceable_card": 0, "route_out": 0},
        known_discard_by_role={"replaceable_card": 1},
        physical_copy_receipts=tuple(copies),
    )
    receipt = replace(
        case.receipt,
        recoverability_receipts=(RecoverabilityReceiptV1(
            receipt_id="fixture-recoverability-v1",
            role="replaceable_card",
            recoverable_count=1,
            qualification="PUBLIC_DISCARD_OR_RECOVERABLE_EXPLICIT",
        ),),
    )
    result = CurrentResourceLedgerEvaluatorV1(receipt).evaluate(
        case.state, ledger, case.local_deltas, case.route, A_FORMULATION
    )
    assert result.status == SELECTED

    orphan_receipt = replace(
        case.receipt,
        recoverability_receipts=(RecoverabilityReceiptV1(
            receipt_id="fixture-recoverability-orphan-v1",
            role="replaceable_card",
            recoverable_count=2,
            qualification="PUBLIC_DISCARD_OR_RECOVERABLE_EXPLICIT",
        ),),
    )
    orphan_result = CurrentResourceLedgerEvaluatorV1(orphan_receipt).evaluate(
        case.state, ledger, case.local_deltas, case.route, A_FORMULATION
    )
    assert orphan_result.status == B0_DELEGATE
    assert orphan_result.fail_closed_reason == "RECOVERABILITY_RECEIPT_MISMATCH"


def test_b3_red010_ledger_public_capacity_and_provenance_are_cross_checked(fixtures) -> None:
    case = _case(fixtures, "B3-F01-RESERVE-ODDS-DIVERGENCE")
    ledger = replace(case.ledger, hidden_own_deck_slots=8)
    result = _evaluate(replace(case, ledger=ledger), A_FORMULATION)
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason == "PUBLIC_BOUNDARY:LEDGER_PUBLIC_CAPACITY_MISMATCH"

    copy = replace(case.ledger.physical_copy_receipts[0], physical_id="p0:s999")
    bad_ledger = replace(case.ledger, physical_copy_receipts=(copy,) + case.ledger.physical_copy_receipts[1:])
    copy_result = _evaluate(replace(case, ledger=bad_ledger), A_FORMULATION)
    assert copy_result.status == B0_DELEGATE
    assert copy_result.fail_closed_reason == "PUBLIC_BOUNDARY:LEDGER_PUBLIC_COPY_MISMATCH"

    unknown_copy = replace(case.ledger.physical_copy_receipts[0], physical_id="unknown-copy")
    unknown_ledger = replace(case.ledger, physical_copy_receipts=(unknown_copy,) + case.ledger.physical_copy_receipts[1:])
    unknown_result = _evaluate(replace(case, ledger=unknown_ledger), A_FORMULATION)
    assert unknown_result.status == B0_DELEGATE
    assert unknown_result.fail_closed_reason == "PUBLIC_BOUNDARY:LEDGER_PUBLIC_COPY_MISMATCH"

    config = json.loads(fixtures.config_path.read_text(encoding="utf-8"))
    config["provenance"]["knowledge_base_sha256"] = "0" * 64
    from ptcg_rl.deterministic.b3_ledger import materialize_b3_fixture_data

    with pytest.raises(ValueError, match="knowledge-base dependency digest mismatch"):
        materialize_b3_fixture_data(config)

    source_config = json.loads(fixtures.config_path.read_text(encoding="utf-8"))
    source_config["provenance"]["source_hashes"]["src/ptcg_rl/g1/models.py"] = "0" * 64
    with pytest.raises(ValueError, match="source dependency digest mismatch"):
        materialize_b3_fixture_data(source_config)

    schema_config = json.loads(fixtures.config_path.read_text(encoding="utf-8"))
    schema_config["provenance"]["schema_id"] = "wrong-schema"
    with pytest.raises(ValueError, match="provenance schema"):
        materialize_b3_fixture_data(schema_config)

    metadata_provenance = json.loads(fixtures.config_path.read_text(encoding="utf-8"))
    metadata_provenance["provenance"]["fixture_metadata_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="provenance metadata digest mismatch"):
        materialize_b3_fixture_data(metadata_provenance)

    config_hash = json.loads(fixtures.config_path.read_text(encoding="utf-8"))
    config_hash["provenance"]["config_payload_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="config dependency digest mismatch"):
        materialize_b3_fixture_data(config_hash)

    for field_name in ("fixture_metadata_sha256", "config_payload_sha256"):
        forged_provenance = dict(case.receipt.dependency_provenance)
        forged_provenance[field_name] = "1" * 64
        forged_receipt = replace(case.receipt, dependency_provenance=forged_provenance)
        with pytest.raises(ValueError, match="canonical fixture provenance"):
            CurrentResourceLedgerEvaluatorV1(forged_receipt)

        evaluator = CurrentResourceLedgerEvaluatorV1(case.receipt)
        evaluator.receipt = forged_receipt
        forged_result = evaluator.evaluate(
            case.state, case.ledger, case.local_deltas, case.route, A_FORMULATION
        )
        assert forged_result.status == B0_DELEGATE
        assert forged_result.fail_closed_reason == "FIXTURE_PROVENANCE_MISMATCH"
