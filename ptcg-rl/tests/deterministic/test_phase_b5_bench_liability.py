"""Fixture-only Phase B5 bench role/liability regressions.

These tests qualify only the public current-state evaluator boundary.  They do
not run CABT, establish native semantics, or claim policy strength.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import fields, replace
from itertools import permutations

import pytest

from ptcg_rl.deterministic.b5_bench import (
    A_FORMULATION,
    B_FORMULATION,
    B0_DELEGATE,
    COMPOUND_UNSUPPORTED,
    FIXTURE_ONLY,
    MALFORMED_LOCAL_DELTAS,
    SELECTED,
    TERMINAL_OVERRIDE,
    BenchLiabilityScaleV1,
    CurrentBenchLiabilityEvaluatorV1,
    load_b5_fixtures,
    materialize_b5_fixture_data,
    mirror_b5_case,
    _normalized_source_digest,
    _seal,
    B5_IMPLEMENTATION_SOURCE_SHA256,
)
from ptcg_rl.deterministic.state import PublicStateV1


@pytest.fixture(scope="module")
def fixtures():
    return load_b5_fixtures()


def _case(fixtures, prefix: str):
    return next(item for item in fixtures.cases if item.case_id.startswith(prefix))


def _evaluate(case, formulation: str):
    return CurrentBenchLiabilityEvaluatorV1(case.receipt).evaluate_case(case, formulation)


def test_b5_f01_materializes_public_records_and_diverges(fixtures) -> None:
    case = _case(fixtures, "B5-F01")
    assert case.receipt.scope == FIXTURE_ONLY
    assert isinstance(case.state, PublicStateV1)
    a = _evaluate(case, A_FORMULATION)
    b = _evaluate(case, B_FORMULATION)
    assert a.status == b.status == SELECTED
    assert a.chosen_action_key == ("B5-F01-X",)
    assert b.chosen_action_key == ("B5-F01-Y",)
    assert a.authority != "B0_CONTROL_DELEGATION"
    assert b.authority != "B0_CONTROL_DELEGATION"
    assert not a.fallback_used and not b.fallback_used


def test_b5_f02_is_a_shared_strict_dominance_control(fixtures) -> None:
    case = _case(fixtures, "B5-F02")
    for formulation in (A_FORMULATION, B_FORMULATION):
        result = _evaluate(case, formulation)
        assert result.status == SELECTED
        assert result.chosen_action_key == ("B5-F02-X",)


def test_b5_f03_full_bench_delegates_without_fallback(fixtures) -> None:
    case = _case(fixtures, "B5-F03")
    for formulation in (A_FORMULATION, B_FORMULATION):
        result = _evaluate(case, formulation)
        assert result.status == B0_DELEGATE
        assert result.fail_closed_reason == "BENCH_CAPACITY_EXHAUSTED"
        assert result.action is None
        assert not result.fallback_used


def test_b5_f04_terminal_first_ignores_stale_selection_data(fixtures) -> None:
    case = _case(fixtures, "B5-F04")
    for formulation in (A_FORMULATION, B_FORMULATION):
        result = _evaluate(case, formulation)
        assert result.status == TERMINAL_OVERRIDE
        assert result.action is None
        assert result.successor_reads == 0


def test_b5_f05_player_mirror_preserves_role_relative_action(fixtures) -> None:
    case = _case(fixtures, "B5-F05")
    mirrored = mirror_b5_case(case)
    for formulation in (A_FORMULATION, B_FORMULATION):
        original = _evaluate(case, formulation)
        result = _evaluate(mirrored, formulation)
        assert result.status == original.status == SELECTED
        assert result.chosen_action_key == original.chosen_action_key
        assert result.chosen_semantic_action_key == mirrored.request.options[
            result.chosen_original_indices[0]
        ].semantic_fingerprint


def test_b5_f06_all_semantic_permutations_are_invariant(fixtures) -> None:
    case = _case(fixtures, "B5-F06")
    expected = {
        formulation: _evaluate(case, formulation).chosen_action_key
        for formulation in (A_FORMULATION, B_FORMULATION)
    }
    for permutation in permutations(range(len(case.request.options))):
        request = replace(
            case.request,
            options=tuple(case.request.options[index] for index in permutation),
        )
        state = PublicStateV1.from_engine(case.observation, request)
        permuted = replace(case, request=request, state=state)
        for formulation in (A_FORMULATION, B_FORMULATION):
            result = _evaluate(permuted, formulation)
            assert result.status == SELECTED
            assert result.chosen_action_key == expected[formulation]


def test_b5_f07_unknown_receipts_and_successors_fail_closed(fixtures) -> None:
    case = _case(fixtures, "B5-F07")
    for formulation in (A_FORMULATION, B_FORMULATION):
        result = _evaluate(case, formulation)
        assert result.status == B0_DELEGATE
        assert result.fail_closed_reason == "UNKNOWN_CURRENT_RECEIPT"

    fingerprint = case.request.options[0].semantic_fingerprint
    poisoned = replace(
        case.local_deltas[fingerprint],
        current_public_fields=("successor_hp",),
    )
    deltas = dict(case.local_deltas)
    deltas[fingerprint] = poisoned
    result = CurrentBenchLiabilityEvaluatorV1(case.receipt).evaluate(
        case.state, deltas, A_FORMULATION, fixture=case
    )
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason == "SUCCESSOR_VALUE_FORBIDDEN"


def test_b5_f08_nan_inf_and_malformed_scale_reject_before_scoring(fixtures) -> None:
    case = _case(fixtures, "B5-F08")
    fingerprint = case.request.options[0].semantic_fingerprint
    local = replace(case.local_deltas[fingerprint], after_bench_occupancy=float("nan"))
    deltas = dict(case.local_deltas)
    deltas[fingerprint] = local
    result = CurrentBenchLiabilityEvaluatorV1(case.receipt).evaluate(
        case.state, deltas, A_FORMULATION, fixture=case
    )
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason == "NONFINITE_OR_INVALID_CURRENT_DELTA"
    with pytest.raises(ValueError):
        BenchLiabilityScaleV1(
            schema_version=1,
            scale_id="bad",
            lower_is_safer=True,
            prize_levels=((0.0, "NONE"), (1, "HIGH")),
            gust_levels=((0, "NONE"), (1, "HIGH")),
            spread_levels=((0, "NONE"), (1, "HIGH")),
        )
    with pytest.raises(ValueError):
        BenchLiabilityScaleV1(
            schema_version=1,
            scale_id="bad",
            lower_is_safer=True,
            prize_levels=((0, "NONE"), (1, "NONE")),
            gust_levels=((0, "NONE"), (1, "HIGH")),
            spread_levels=((0, "NONE"), (1, "HIGH")),
        )


def test_b5_f09_role_conflicts_delegate_before_ranking(fixtures) -> None:
    case = _case(fixtures, "B5-F09")
    for formulation in (A_FORMULATION, B_FORMULATION):
        result = _evaluate(case, formulation)
        assert result.status == B0_DELEGATE
        assert result.fail_closed_reason == "ROLE_RECEIPT_CONFLICT"


def test_b5_f10_stop_is_builder_token_and_compounds_delegate(fixtures) -> None:
    case = _case(fixtures, "B5-F10")
    stop = _evaluate(case, A_FORMULATION)
    assert stop.status == SELECTED
    assert stop.stopped_early
    assert stop.action is not None
    assert stop.action.submitted_original_indices == ()
    assert stop.action.steps[-1].chosen_token == "STOP"

    compound_request = replace(case.request, min_count=1, max_count=2)
    compound_state = PublicStateV1.from_engine(case.observation, compound_request)
    compound_case = replace(case, request=compound_request, state=compound_state)
    result = _evaluate(compound_case, A_FORMULATION)
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason == COMPOUND_UNSUPPORTED


def test_b5_f11_lifecycle_duplicate_stale_and_reset_are_isolated(fixtures) -> None:
    case = _case(fixtures, "B5-F11")
    evaluator = CurrentBenchLiabilityEvaluatorV1(case.receipt)
    first = evaluator.evaluate_case(case, A_FORMULATION)
    duplicate = evaluator.evaluate_case(case, A_FORMULATION)
    assert duplicate == first

    changed_request = replace(case.request, request_id="b5-reused-request")
    changed_state = PublicStateV1.from_engine(case.observation, changed_request)
    changed_case = replace(case, request=changed_request, state=changed_state)
    stale = evaluator.evaluate_case(changed_case, A_FORMULATION)
    assert stale.status == B0_DELEGATE
    assert stale.fail_closed_reason in {
        "STALE_OR_REUSED_REQUEST_IDENTITY",
        "STALE_SELECTION_SEQUENCE",
    }

    evaluator.reset(case.state.battle_id, case.state.acting_player, reason="error")
    assert evaluator.evaluate_case(case, A_FORMULATION).status == SELECTED
    evaluator.reset(case.state.battle_id, case.state.acting_player, reason="worker_replacement")
    assert evaluator.evaluate_case(case, A_FORMULATION).status == SELECTED


def test_b5_f12_unregistered_and_forged_receipts_delegate(fixtures) -> None:
    case = _case(fixtures, "B5-F12")
    fingerprint = case.request.options[0].semantic_fingerprint
    forged_delta = replace(
        case.local_deltas[fingerprint],
        receipt_id="unregistered-local-delta",
    )
    deltas = dict(case.local_deltas)
    deltas[fingerprint] = forged_delta
    result = CurrentBenchLiabilityEvaluatorV1(case.receipt).evaluate(
        case.state, deltas, A_FORMULATION, fixture=case
    )
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason in {
        "UNREGISTERED_LOCAL_DELTA",
        "RECEIPT_GRAPH_MISMATCH",
    }

    forged_manifest = dict(case.receipt.provenance_manifest)
    forged_manifest["candidate_deck_sha256"] = "0" * 64
    forged_receipt = replace(case.receipt, provenance_manifest=forged_manifest)
    result = CurrentBenchLiabilityEvaluatorV1(forged_receipt).evaluate(
        case.state, case.local_deltas, A_FORMULATION, fixture=case
    )
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason == "RECEIPT_CONTENT_MISMATCH"


@pytest.mark.parametrize("malformed", [object(), set()])
def test_b5_malformed_local_delta_payload_hash_delegates(fixtures, malformed) -> None:
    case = _case(fixtures, "B5-F01")
    evaluator = CurrentBenchLiabilityEvaluatorV1(case.receipt)
    fingerprint = case.request.options[0].semantic_fingerprint
    for payload in ({fingerprint: malformed}, malformed):
        result = evaluator.evaluate(case.state, payload, A_FORMULATION, fixture=case)
        assert result.status == B0_DELEGATE
        assert result.fail_closed_reason == MALFORMED_LOCAL_DELTAS
        assert not result.fallback_used


def test_b5_public_receipt_axes_are_complete_and_prose_hidden_fail_closed(fixtures) -> None:
    case = _case(fixtures, "B5-F01")
    assert len(case.receipt.role_receipts) == 2
    assert len(case.receipt.local_deltas) == 2
    assert len(case.receipt.prize_static) == 2
    assert len(case.receipt.gust_exposures) == 2
    assert len(case.receipt.spread_exposures) == 2
    assert all(row.scope_version == "fixture-scope-v1" for row in (*case.receipt.prize_static, *case.receipt.gust_exposures, *case.receipt.spread_exposures))

    fingerprint = case.request.options[0].semantic_fingerprint
    expected_reason = {
        "hidden_opponent_hand": "HIDDEN_INFORMATION_FORBIDDEN",
        "card_prose": "CARD_PROSE_FORBIDDEN",
    }
    for forbidden in ("hidden_opponent_hand", "card_prose"):
        poisoned = replace(case.local_deltas[fingerprint], current_public_fields=(forbidden,))
        deltas = dict(case.local_deltas)
        deltas[fingerprint] = poisoned
        result = CurrentBenchLiabilityEvaluatorV1(case.receipt).evaluate(case.state, deltas, A_FORMULATION, fixture=case)
        assert result.status == B0_DELEGATE
        assert result.fail_closed_reason == expected_reason[forbidden]

    with pytest.raises(ValueError):
        replace(case.receipt.role_receipts[0], role_id="UNDECLARED_ROLE")


def test_b5_complete_option_graph_and_nested_forgery_delegate(fixtures) -> None:
    case = _case(fixtures, "B5-F01")
    fingerprint = case.request.options[1].semantic_fingerprint
    incomplete = dict(case.local_deltas)
    incomplete.pop(fingerprint)
    result = CurrentBenchLiabilityEvaluatorV1(case.receipt).evaluate(case.state, incomplete, A_FORMULATION, fixture=case)
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason == "RECEIPT_GRAPH_MISMATCH"

    forged_prize = replace(case.receipt.prize_static[0], prize_units=3)
    forged_receipt = replace(case.receipt, prize_static=(forged_prize, *case.receipt.prize_static[1:]))
    result = CurrentBenchLiabilityEvaluatorV1(forged_receipt).evaluate(case.state, case.local_deltas, A_FORMULATION, fixture=case)
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason == "RECEIPT_CONTENT_MISMATCH"


def test_b5_self_sealed_local_delta_cannot_change_liability_or_role_math(fixtures) -> None:
    case = _case(fixtures, "B5-F01")
    fingerprint = case.request.options[0].semantic_fingerprint
    forged = _seal(replace(case.local_deltas[fingerprint], after_role_surplus={"BACKUP_ATTACKER": 99, "NEXT_ATTACKER": 99}))
    result = CurrentBenchLiabilityEvaluatorV1(case.receipt).evaluate(
        case.state, {**case.local_deltas, fingerprint: forged}, A_FORMULATION, fixture=case
    )
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason == "RECEIPT_CONTENT_MISMATCH"


def test_b5_caller_self_consistent_cross_case_receipt_is_not_authority(fixtures) -> None:
    case = _case(fixtures, "B5-F01")
    manifest = dict(case.receipt.provenance_manifest)
    manifest["candidate_deck_sha256"] = "0" * 64
    forged_receipt = _seal(replace(case.receipt, provenance_manifest=manifest))
    forged_case = replace(case, receipt=forged_receipt)
    result = CurrentBenchLiabilityEvaluatorV1(forged_receipt).evaluate_case(forged_case, A_FORMULATION)
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason == "RECEIPT_CONTENT_MISMATCH"


def test_b5_required_role_floor_is_checked_before_both_formulations(fixtures) -> None:
    case = _case(fixtures, "B5-F01")
    assert all(
        any(row.role_id == role_id and row.role_status == "COVERED" for row in case.receipt.role_receipts)
        for delta in case.local_deltas.values()
        for role_id, count in delta.required_role_counts.items()
        if count
    )
    fingerprint = case.request.options[0].semantic_fingerprint
    forged = _seal(replace(case.local_deltas[fingerprint], after_role_coverage={}))
    for formulation in (A_FORMULATION, B_FORMULATION):
        result = CurrentBenchLiabilityEvaluatorV1(case.receipt).evaluate(
            case.state, {**case.local_deltas, fingerprint: forged}, formulation, fixture=case
        )
        assert result.status == B0_DELEGATE
        assert result.fail_closed_reason == "RECEIPT_CONTENT_MISMATCH"


def test_b5_option_graph_rejects_missing_option_even_when_count_is_valid(fixtures) -> None:
    case = _case(fixtures, "B5-F01")
    request = replace(case.request, options=(case.request.options[0],))
    state = PublicStateV1.from_engine(case.observation, request)
    forged_case = replace(case, request=request, state=state, local_deltas={case.request.options[0].semantic_fingerprint: case.local_deltas[case.request.options[0].semantic_fingerprint]})
    result = _evaluate(forged_case, A_FORMULATION)
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason == "RECEIPT_GRAPH_MISMATCH"


def test_b5_malformed_zero_count_delegates_without_attempting_stop(fixtures) -> None:
    case = _case(fixtures, "B5-F01")
    request = replace(case.request, min_count=0, max_count=0, options=())
    state = PublicStateV1.from_engine(case.observation, request)
    forged_case = replace(case, request=request, state=state, local_deltas={})
    result = _evaluate(forged_case, A_FORMULATION)
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason == COMPOUND_UNSUPPORTED


def test_b5_fractional_occupancy_and_out_of_scale_liability_fail_closed(fixtures) -> None:
    case = _case(fixtures, "B5-F01")
    fingerprint = case.request.options[0].semantic_fingerprint
    fractional = replace(case.local_deltas[fingerprint], after_bench_occupancy=1.5)
    result = CurrentBenchLiabilityEvaluatorV1(case.receipt).evaluate(
        case.state, {**case.local_deltas, fingerprint: fractional}, A_FORMULATION, fixture=case
    )
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason == "NONFINITE_OR_INVALID_CURRENT_DELTA"
    forged_prize = replace(case.receipt.prize_static[0], prize_units=99)
    forged_receipt = _seal(replace(case.receipt, prize_static=(forged_prize, *case.receipt.prize_static[1:])))
    result = CurrentBenchLiabilityEvaluatorV1(forged_receipt).evaluate(
        case.state, case.local_deltas, A_FORMULATION, fixture=replace(case, receipt=forged_receipt)
    )
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason == "NONFINITE_OR_INVALID_LIABILITY"


def test_b5_duplicate_semantic_role_axis_rejects_new_receipt_id(fixtures) -> None:
    case = _case(fixtures, "B5-F01")
    duplicate = _seal(replace(case.receipt.role_receipts[0], receipt_id="b5-duplicate-role-axis"))
    forged_receipt = _seal(replace(case.receipt, role_receipts=(*case.receipt.role_receipts, duplicate)))
    result = CurrentBenchLiabilityEvaluatorV1(forged_receipt).evaluate(
        case.state, case.local_deltas, A_FORMULATION, fixture=replace(case, receipt=forged_receipt)
    )
    assert result.status == B0_DELEGATE
    assert result.fail_closed_reason == "ROLE_RECEIPT_CONFLICT"


def test_b5_config_rows_and_runtime_source_digest_are_loader_owned(fixtures) -> None:
    raw = json.loads(fixtures.config_path.read_text(encoding="utf-8"))
    assert len(raw["fixture_records"]) == 12
    assert all(set(row["receipt"]) == {item.name for item in fields(fixtures.cases[0].receipt)} for row in raw["fixture_records"])
    assert raw["provenance"]["implementation_sha256"] == B5_IMPLEMENTATION_SOURCE_SHA256
    assert B5_IMPLEMENTATION_SOURCE_SHA256 == _normalized_source_digest(fixtures.config_path.parents[2] / "src/ptcg_rl/deterministic/b5_bench.py")
    broken = json.loads(fixtures.config_path.read_text(encoding="utf-8"))
    broken["fixture_records"][0]["receipt"]["role_receipts"][0].pop("metadata_ref")
    with pytest.raises(ValueError):
        materialize_b5_fixture_data(broken, config_path=fixtures.config_path)


def test_b5_stale_sequence_is_checked_before_idempotent_cache(fixtures) -> None:
    case = _case(fixtures, "B5-F11")
    evaluator = CurrentBenchLiabilityEvaluatorV1(case.receipt)
    first = evaluator.evaluate_case(case, A_FORMULATION)
    evaluator._request_ids[(case.request.episode_uuid, case.request.acting_player)]["newer-request"] = case.request.selection_seq + 1
    stale = evaluator.evaluate_case(case, A_FORMULATION)
    assert first.status == SELECTED
    assert stale.status == B0_DELEGATE
    assert stale.fail_closed_reason == "STALE_SELECTION_SEQUENCE"


def test_b5_config_digest_and_expected_case_set_are_sealed(fixtures) -> None:
    assert len(fixtures.cases) == 12
    assert len({case.case_id for case in fixtures.cases}) == 12
    raw = json.loads(fixtures.config_path.read_text(encoding="utf-8"))
    raw["fixture_cases"][0]["expected"][A_FORMULATION] = B0_DELEGATE
    with pytest.raises(ValueError, match="canonical fixture content"):
        materialize_b5_fixture_data(raw, config_path=fixtures.config_path)


def test_b5_config_loader_rejects_content_seal_only_mutation(fixtures) -> None:
    raw = json.loads(fixtures.config_path.read_text(encoding="utf-8"))
    original = raw["fixture_records"][0]["receipt"]["local_deltas"][0]["content_sha256"]
    raw["fixture_records"][0]["receipt"]["local_deltas"][0]["content_sha256"] = "0" * 64
    assert raw["fixture_records"][0]["receipt"]["local_deltas"][0]["content_sha256"] != original
    with pytest.raises(ValueError, match="canonical fixture content"):
        materialize_b5_fixture_data(raw, config_path=fixtures.config_path)


def test_b5_fresh_process_load_and_boundary_review() -> None:
    code = (
        "from ptcg_rl.deterministic.b5_bench import load_b5_fixtures; "
        "b=load_b5_fixtures(); assert len(b.cases)==12; "
        "print('B5_FRESH_PROCESS_PASS')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "B5_FRESH_PROCESS_PASS" in result.stdout
