from __future__ import annotations

import hashlib
import subprocess
import sys
from dataclasses import replace
import json
from pathlib import Path

import pytest

from ptcg_rl.deterministic.b1_oracle import B0_DELEGATE, B_FORMULATION, RouteCandidateV1, RouteFeatureV1, SELECTED
from ptcg_rl.deterministic.b1_policy import (
    B1APolicyV1,
    B1BPolicyV1,
    RECEIPT_PATH,
    RuntimeRouteReceiptV1,
)
from ptcg_rl.g1.actions import permute_request
from ptcg_rl.g1.models import CONTRACT_VERSION, LegalOptionV1, SelectionRequestV1, stable_hash
from ptcg_rl.g1.semantic import AREA, OPTION_NAMES

from .test_phase_b1_oracle import _entity, _observation, _option


ROOT = Path(__file__).resolve().parents[2]


def _reseal_receipt(payload: dict) -> dict:
    payload["provenance"].pop("config_sha256", None)
    payload["provenance"]["config_sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    return payload


def _attack_fixture(*, player: int = 0):
    own = _entity(722, 1, owner=player, energy=(3,))
    backup = _entity(722, 2, owner=player, zone=AREA["BENCH"], position=1, energy=(3, 3))
    opponent = _entity(722, 9, owner=1 - player, hp=10)
    options = (
        _option(13, 0, source=own.entity_key, target=opponent.entity_key, attack_id=1044),
        _option(13, 1, source=own.entity_key, target=opponent.entity_key, attack_id=1045),
    )
    observation = replace(
        _observation((own, backup, opponent)),
        battle_id="b1-policy-test",
        acting_player=player,
        players=tuple(
            replace(row, hand_visible=row.player_index == player)
            for row in _observation((own, backup, opponent)).players
        ),
    )
    request = SelectionRequestV1(
        schema_version=CONTRACT_VERSION,
        episode_uuid="b1-policy-test",
        selection_seq=0,
        request_id=f"request-{player}-attack",
        acting_player=player,
        selection_type=6,
        selection_context=35,
        min_count=1,
        max_count=1,
        remain_damage_counter=0,
        remain_energy_cost=0,
        context_card_id=None,
        effect_card_id=None,
        ordering="UNORDERED",
        options=options,
    )
    return observation, request


def _evolve_option(index: int, source: str) -> LegalOptionV1:
    row = LegalOptionV1(
        schema_version=CONTRACT_VERSION,
        original_index=index,
        selection_type=7,
        selection_context=37,
        option_type=9,
        option_name=OPTION_NAMES[9],
        card_id=723,
        source_kind="ENTITY",
        source_ref=source,
        choice_role="EVOLVE",
        source_entity_key=source,
    )
    return replace(row, semantic_fingerprint=stable_hash(row.semantic_payload()))


def _stop_option(index: int) -> LegalOptionV1:
    row = LegalOptionV1(
        schema_version=CONTRACT_VERSION,
        original_index=index,
        selection_type=6,
        selection_context=35,
        option_type=14,
        option_name=OPTION_NAMES[14],
        choice_role="END",
    )
    return replace(row, semantic_fingerprint=stable_hash(row.semantic_payload()))


def test_receipt_is_exactly_native_qualified_and_binds_route_provenance():
    receipt = RuntimeRouteReceiptV1.from_path(ROOT / RECEIPT_PATH)
    assert receipt.capability.runtime_qualified()
    assert {item.card_id: item.prize_units for item in receipt.capability.prizes} == {
        721: 1,
        722: 1,
        723: 3,
        754: 3,
    }
    assert {item.attack_id: item.damage for item in receipt.capability.attacks} == {1044: 10, 1045: 30}
    assert receipt.payload["route_contract"]["partial_route_ids_never_authority"] == [1042, 1043, 1046, 1047, 1262]


@pytest.mark.parametrize("policy_type", [B1APolicyV1, B1BPolicyV1])
def test_selected_route_uses_semantic_action_and_existing_final_validator(policy_type):
    observation, request = _attack_fixture()
    policy = policy_type(receipt_path=ROOT / RECEIPT_PATH)
    policy.reset(request.episode_uuid, request.acting_player)
    action = policy.choose(observation, request)
    assert action.submitted_original_indices in {(0,), (1,)}
    assert action.steps[0].chosen_token == "OPTION"
    assert policy.diagnostics.last_request is not None
    assert policy.diagnostics.last_request.status == SELECTED
    assert policy.diagnostics.last_request.authority == "EXPERIMENTAL_PUBLIC_ROUTE_RUNTIME"
    assert policy.diagnostics.last_request.route_active is True
    assert policy.diagnostics.last_request.delegated is False


def test_evolution_is_receipt_bound_and_uses_native_local_delta_contract():
    observation = replace(
        _observation((_entity(722, 1, energy=(3,)), _entity(722, 9, owner=1, hp=100))),
        battle_id="b1-policy-evolve",
    )
    option = _evolve_option(0, "p0:s1")
    request = SelectionRequestV1(
        schema_version=CONTRACT_VERSION,
        episode_uuid="b1-policy-evolve",
        selection_seq=0,
        request_id="evolve-0",
        acting_player=0,
        selection_type=7,
        selection_context=37,
        min_count=1,
        max_count=1,
        remain_damage_counter=0,
        remain_energy_cost=0,
        context_card_id=None,
        effect_card_id=None,
        ordering="UNORDERED",
        options=(option,),
    )
    policy = B1APolicyV1(receipt_path=ROOT / RECEIPT_PATH)
    policy.reset(request.episode_uuid, 0)
    action = policy.choose(observation, request)
    assert action.submitted_original_indices == (0,)
    assert policy.diagnostics.last_request is not None
    assert policy.diagnostics.last_request.route_active is True
    assert policy.diagnostics.last_request.status == SELECTED


def test_unsupported_partial_attack_is_explicit_b0_delegation_not_fallback():
    observation, request = _attack_fixture()
    partial = _option(13, 0, source="p0:s1", target="p1:s9", attack_id=1046)
    request = replace(request, options=(partial,), request_id="partial-attack")
    policy = B1APolicyV1(receipt_path=ROOT / RECEIPT_PATH)
    policy.reset(request.episode_uuid, 0)
    action = policy.choose(observation, request)
    assert len(action.submitted_original_indices) == 1
    diagnostic = policy.diagnostics.last_request
    assert diagnostic is not None
    assert diagnostic.status == B0_DELEGATE
    assert diagnostic.authority == "B0_CONTROL"
    assert diagnostic.delegated is True
    assert policy.diagnostics.b0_delegation_count == 1
    assert policy.diagnostics.selected_authority_count == 0


def test_unknown_current_resource_is_counted_as_b0_delegation():
    observation, request = _attack_fixture()
    own, backup, opponent = observation.entities
    observation = replace(observation, entities=(own, opponent))
    policy = B1APolicyV1(receipt_path=ROOT / RECEIPT_PATH)
    policy.reset(request.episode_uuid, 0)
    policy.choose(observation, request)
    assert policy.diagnostics.unknown_count == 1
    assert policy.diagnostics.b0_delegation_count == 1
    assert policy.diagnostics.last_request is not None
    assert policy.diagnostics.last_request.status == "UNKNOWN"


def test_non_equivalent_equal_route_keys_are_counted_as_ambiguous_b0_delegation():
    observation, request = _attack_fixture()
    own, backup, opponent = observation.entities
    own = replace(own, energy_types=(3, 3), attached_energy_count=2)
    observation = replace(observation, entities=(own, backup, opponent))
    policy = B1BPolicyV1(receipt_path=ROOT / RECEIPT_PATH)
    policy.reset(request.episode_uuid, 0)
    policy.choose(observation, request)
    assert policy.diagnostics.ambiguous_count == 1
    assert policy.diagnostics.b0_delegation_count == 1
    assert policy.diagnostics.last_request is not None
    assert policy.diagnostics.last_request.status == "AMBIGUOUS"


def test_optional_route_without_explicit_stop_delegates_and_duplicate_request_is_idempotent():
    observation, request = _attack_fixture()
    request = replace(
        request,
        request_id="optional-stop",
        min_count=0,
        max_count=1,
    )
    policy = B1APolicyV1(receipt_path=ROOT / RECEIPT_PATH)
    policy.reset(request.episode_uuid, 0)
    action = policy.choose(observation, request)
    repeat = policy.choose(observation, request)
    assert action == repeat
    assert policy.diagnostics.duplicate_request_count == 1
    assert policy.diagnostics.last_request is not None
    assert policy.diagnostics.last_request.status == B0_DELEGATE
    assert action.steps[0].stop_available is True
    assert action.steps[0].chosen_token == "OPTION"


def test_compound_action_delegates_to_b0_and_preserves_complete_action_contract():
    observation, request = _attack_fixture()
    request = replace(request, request_id="compound", min_count=1, max_count=2)
    policy = B1BPolicyV1(receipt_path=ROOT / RECEIPT_PATH)
    policy.reset(request.episode_uuid, 0)
    action = policy.choose(observation, request)
    assert len(action.submitted_original_indices) == 2
    assert policy.diagnostics.last_request is not None
    assert policy.diagnostics.last_request.status == B0_DELEGATE
    assert policy.diagnostics.last_request.authority == "B0_CONTROL"


def test_player_one_mirror_has_same_semantic_choice():
    observation, request = _attack_fixture(player=1)
    policy = B1APolicyV1(receipt_path=ROOT / RECEIPT_PATH)
    policy.reset(request.episode_uuid, 1)
    action = policy.choose(observation, request)
    assert action.submitted_original_indices in {(0,), (1,)}
    assert policy.diagnostics.last_request is not None
    assert policy.diagnostics.last_request.authority == "EXPERIMENTAL_PUBLIC_ROUTE_RUNTIME"


def test_thirty_two_semantic_permutations_ignore_transport_order():
    observation, request = _attack_fixture()
    selected: set[tuple[int, ...]] = set()
    # The engine contract reserves 32 permutation trials per candidate arm.
    # This fixture has two legal options, so the two semantic permutations are
    # repeated across the exact 32-call mechanical budget.
    for index in range(32):
        permutation = (0, 1) if index % 2 == 0 else (1, 0)
        policy = B1APolicyV1(receipt_path=ROOT / RECEIPT_PATH)
        policy.reset(request.episode_uuid, 0)
        permuted = replace(permute_request(request, permutation), request_id=f"perm-{index}")
        action = policy.choose(observation, permuted)
        selected.add(action.submitted_original_indices)
    assert len(selected) == 1


def test_fresh_process_receipt_and_policy_import_stays_local_and_native_free():
    code = (
        "from pathlib import Path; "
        "from ptcg_rl.deterministic.b1_policy import B1APolicyV1; "
        "p=B1APolicyV1(receipt_path=Path('configs/deterministic/phase_b1_native_route_receipt_v2.json')); "
        "print(p.policy_id)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "b1-a-native-route-policy-v1"


def test_terminal_boundary_precedes_stale_request_and_resets_oracle_and_b0():
    observation = replace(_observation(()), terminal_result=99)
    stale = replace(_attack_fixture()[1], episode_uuid="stale-episode", selection_seq=999)
    policy = B1APolicyV1(receipt_path=ROOT / RECEIPT_PATH)
    policy.reset("live-episode", 0)
    with pytest.raises(Exception, match="terminal"):
        policy.choose(observation, stale)
    assert policy.diagnostics.terminal_boundary_count == 1
    assert policy.oracle.diagnostics.route_requests == 0
    assert policy.diagnostics.last_request is None
    with pytest.raises(Exception, match="lifecycle"):
        policy.choose(_attack_fixture()[0], _attack_fixture()[1])


def test_policy_error_resets_b0_and_route_lifecycle():
    observation, request = _attack_fixture()
    policy = B1APolicyV1(receipt_path=ROOT / RECEIPT_PATH)
    with pytest.raises(Exception, match="lifecycle"):
        policy.choose(observation, request)
    assert policy.diagnostics.error_reset_count == 1
    policy.reset(request.episode_uuid, request.acting_player)
    assert policy.choose(observation, request).submitted_original_indices in {(0,), (1,)}


def test_runtime_receipt_rejects_report_and_deck_hash_mutations(tmp_path: Path):
    payload = json.loads((ROOT / RECEIPT_PATH).read_text(encoding="utf-8"))
    payload["provenance"]["capability_evidence"]["report_sha256"] = "f" * 64
    mutated_report = tmp_path / "receipt-report-mutated.json"
    mutated_report.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="capability report|config receipt"):
        RuntimeRouteReceiptV1.from_path(mutated_report)

    payload = json.loads((ROOT / RECEIPT_PATH).read_text(encoding="utf-8"))
    payload["candidate_deck_semantic_multiset_sha256"] = "e" * 64
    mutated_deck = tmp_path / "receipt-deck-mutated.json"
    mutated_deck.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="candidate deck semantic|config receipt"):
        RuntimeRouteReceiptV1.from_path(mutated_deck)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda payload: payload["provenance"].__setitem__("knowledge_base_sha256", "a" * 64), "knowledge-base"),
        (lambda payload: payload["provenance"]["asset_scope"].__setitem__("candidate_deck", "ARBITRARY"), "asset receipt"),
        (lambda payload: payload["provenance"]["source_scope"].__setitem__("src/ptcg_rl/g1/actions.py", "ARBITRARY"), "source receipt"),
        (lambda payload: payload["provenance"].__setitem__("component_plan_path", "/inside/repository/plan.json"), "repository"),
        (lambda payload: payload["provenance"]["capability_evidence"].__setitem__("scope", "ARBITRARY"), "capability evidence"),
    ],
)
def test_runtime_receipt_rejects_resealed_scope_hash_and_path_mutations(tmp_path: Path, mutation, message: str):
    payload = json.loads((ROOT / RECEIPT_PATH).read_text(encoding="utf-8"))
    mutation(payload)
    mutated = tmp_path / "receipt-mutated.json"
    mutated.write_text(json.dumps(_reseal_receipt(payload)), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        RuntimeRouteReceiptV1.from_path(mutated)


def test_b1_b_does_not_authorize_unqualified_resource_reserve():
    base = RouteFeatureV1(True, 1, True, 0, 0, 0, True, 10, True, None)
    rich = RouteFeatureV1(True, 1, True, 0, 0, 0, True, 10, True, 5)
    left = RouteCandidateV1("left", ("left",), base)
    right = RouteCandidateV1("right", ("right",), rich)
    from ptcg_rl.deterministic.b1_oracle import CurrentStateRouteOracleV1

    oracle = CurrentStateRouteOracleV1(RuntimeRouteReceiptV1.from_path(ROOT / RECEIPT_PATH).capability)
    assert oracle._strategic_key(left, B_FORMULATION) == oracle._strategic_key(right, B_FORMULATION)
