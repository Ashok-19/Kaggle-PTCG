from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import random

import pytest

from ptcg_rl.g1.actions import CompoundActionBuilder, permute_request
from ptcg_rl.g1.models import (
    ContractViolation,
    EngineObservationV1,
    LegalOptionV1,
    NumericTensorV1,
    PlayerViewV1,
    PublicEventV1,
    SchemaMetadataV1,
    SelectionRequestV1,
    TransitionRecordV1,
    schema_descriptor,
    stable_hash,
)
from ptcg_rl.g1.semantic import (
    EVENT_FEATURES,
    NUMERIC_FIELD_COVERAGE,
    OPTION_FEATURES,
    encode_numeric,
    semantic_snapshot,
)
from ..g1_fixtures import raw_observation


CARD_HASH = "c" * 64


def snapshot(**kwargs):
    selection_type = kwargs.pop("selection_type", None)
    selection_context = kwargs.pop("selection_context", None)
    raw = raw_observation(**kwargs)
    if selection_type is not None:
        raw["select"]["type"] = selection_type
    if selection_context is not None:
        raw["select"]["context"] = selection_context
    return semantic_snapshot(raw, "battle", 0, CARD_HASH)


def test_ongoing_and_every_terminal_result_branch_before_selection() -> None:
    observation, request = snapshot(result=-1)
    assert observation.terminal_result is None
    assert request is not None
    for result in (0, 1, 2):
        observation, request = snapshot(result=result)
        assert observation.terminal_result == result
        assert request is None


def test_forced_and_optional_empty_policy_masks() -> None:
    _, forced = snapshot(options=[{"type": 1}], min_count=1, max_count=1)
    assert forced is not None
    builder = CompoundActionBuilder(forced)
    builder.choose(0)
    assert builder.build().policy_loss_mask == 0

    _, optional = snapshot(min_count=0, max_count=1)
    assert optional is not None
    builder = CompoundActionBuilder(optional)
    builder.stop()
    action = builder.build()
    assert action.submitted_original_indices == ()
    assert action.policy_loss_mask == 1


def test_multiselect_min_max_stop_and_uniqueness() -> None:
    options = [{"type": 0, "number": index} for index in range(4)]
    _, request = snapshot(
        options=options, min_count=2, max_count=3, selection_type=8, selection_context=38
    )
    assert request is not None
    builder = CompoundActionBuilder(request)
    with pytest.raises(ContractViolation):
        builder.stop()
    builder.choose(1)
    with pytest.raises(ContractViolation):
        builder.choose(1)
    builder.choose(3)
    builder.stop()
    assert builder.build().submitted_original_indices == (1, 3)

    builder = CompoundActionBuilder(request)
    for index in (0, 1, 2):
        builder.choose(index)
    assert builder.complete
    with pytest.raises(ContractViolation):
        builder.choose(3)


def test_permutation_round_trips_original_engine_indices() -> None:
    _, request = snapshot(
        options=[{"type": 0, "number": i} for i in range(5)],
        selection_type=8, selection_context=38,
    )
    assert request is not None
    for permutation in ([4, 3, 2, 1, 0], [2, 0, 4, 1, 3], [1, 2, 3, 4, 0]):
        model_request = permute_request(request, permutation)
        builder = CompoundActionBuilder(model_request, request)
        builder.choose(0)
        assert builder.build().submitted_original_indices == (permutation[0],)
    generator = random.Random(9)
    for _ in range(100):
        permutation = list(range(5))
        generator.shuffle(permutation)
        model_request = permute_request(request, permutation)
        builder = CompoundActionBuilder(model_request, request)
        builder.choose(2)
        assert builder.build().submitted_original_indices == (permutation[2],)


def test_all_official_selection_context_and_option_codes_are_structurally_preserved() -> None:
    raw = raw_observation()
    raw["current"]["players"][0]["active"] = [{
        "id": 100, "serial": 10, "playerIndex": 0, "hp": 100, "maxHp": 120,
        "appearThisTurn": False, "energies": [1],
        "energyCards": [{"id": 15, "serial": 20, "playerIndex": 0}],
        "tools": [{"id": 70, "serial": 21, "playerIndex": 0}], "preEvolution": [],
    }]
    raw["current"]["players"][0]["hand"] = [
        {"id": 50, "serial": 30, "playerIndex": 0}
    ]
    raw["current"]["players"][0]["handCount"] = 1
    cases = [
        (8, 38, {"type": 0, "number": 0}),
        (9, 41, {"type": 1}), (9, 41, {"type": 2}),
        (1, 8, {"type": 3, "area": 2, "index": 0, "playerIndex": 0}),
        (2, 26, {"type": 4, "area": 4, "index": 0, "playerIndex": 0, "toolIndex": 0}),
        (2, 26, {"type": 5, "area": 4, "index": 0, "playerIndex": 0, "energyIndex": 0}),
        (4, 30, {"type": 6, "area": 4, "index": 0, "playerIndex": 0, "energyIndex": 0, "count": 1}),
        (0, 0, {"type": 7, "index": 0}),
        (0, 0, {"type": 8, "area": 2, "index": 0, "inPlayArea": 4, "inPlayIndex": 0}),
        (7, 37, {"type": 9, "area": 2, "index": 0, "inPlayArea": 4, "inPlayIndex": 0}),
        (0, 0, {"type": 10, "area": 4, "index": 0}),
        (0, 0, {"type": 11, "area": 4, "index": 0}),
        (0, 0, {"type": 12}), (6, 35, {"type": 13, "attackId": 7}),
        (0, 0, {"type": 14}), (5, 34, {"type": 15, "cardId": 100, "serial": 10}),
        (10, 47, {"type": 16, "specialConditionType": 4}),
    ]
    for transition, (selection_type, context, option) in enumerate(cases):
        raw["select"].update({"type": selection_type, "context": context, "option": [option]})
        _, request = semantic_snapshot(raw, "battle", transition, CARD_HASH)
        assert request is not None
        assert request.selection_type == selection_type
        assert request.options[0].option_type == option["type"]
        assert request.options[0].choice_role != "UNKNOWN"
    for context in range(49):
        raw["select"].update({"type": 9, "option": [{"type": 1}]})
        raw["select"]["context"] = context
        _, request = semantic_snapshot(raw, "context", context, CARD_HASH)
        assert request is not None and request.selection_context == context


def test_more_than_64_options_are_preserved_and_overflow_fails() -> None:
    _, request = snapshot(
        options=[{"type": 0, "number": i} for i in range(70)],
        selection_type=8, selection_context=38,
    )
    observation, _ = snapshot(
        options=[{"type": 0, "number": i} for i in range(70)],
        selection_type=8, selection_context=38,
    )
    assert request is not None and len(request.options) == 70
    tensor = encode_numeric(observation, request)
    assert tensor.option_length == 70
    with pytest.raises(ContractViolation, match="truncation is forbidden"):
        encode_numeric(observation, request, max_options=64)


def test_semantic_and_tensor_json_round_trip_preserves_missing_vs_zero() -> None:
    raw = raw_observation(options=[{"type": 0, "number": 0}])
    raw["select"].update({"type": 8, "context": 38})
    raw["current"]["players"][0]["hand"] = [
        {"id": 42, "serial": 1001, "playerIndex": 0}
    ]
    raw["current"]["players"][0]["handCount"] = 1
    observation, request = semantic_snapshot(raw, "battle", 7, CARD_HASH)
    assert request is not None
    tensor = encode_numeric(observation, request)
    observation_copy = EngineObservationV1.from_dict(asdict(observation))
    request_copy = SelectionRequestV1.from_dict(asdict(request))
    tensor_copy = NumericTensorV1.from_dict(asdict(tensor))
    assert observation_copy == observation
    assert request_copy == request
    assert tensor_copy == tensor
    number_index = OPTION_FEATURES.index("number")
    count_index = OPTION_FEATURES.index("count")
    assert tensor.option_values[0][number_index] == 0
    assert tensor.option_missing_masks[0][number_index] is False
    assert tensor.option_missing_masks[0][count_index] is True
    assert "serial" in EVENT_FEATURES
    builder = CompoundActionBuilder(request)
    builder.choose(0)
    action = builder.build()
    transition = TransitionRecordV1(
        observation.schema_version,
        "battle",
        7,
        observation,
        request,
        action,
        None,
        None,
        action.policy_loss_mask,
        SchemaMetadataV1.build("e" * 64, CARD_HASH),
    )
    assert TransitionRecordV1.from_dict(asdict(transition)) == transition


def test_hidden_opponent_hand_is_rejected_and_search_state_is_excluded() -> None:
    raw = raw_observation()
    raw["current"]["players"][1]["hand"] = [{"id": 9, "serial": 99, "playerIndex": 1}]
    with pytest.raises(ContractViolation, match="hidden hand"):
        semantic_snapshot(raw, "battle", 0, CARD_HASH)
    observation, _ = snapshot()
    assert "search" not in repr(observation).lower()


def test_schema_hash_changes_for_incompatible_field_change() -> None:
    @dataclass
    class Before:
        value: int

    @dataclass
    class After:
        value: int
        added: int

    assert stable_hash(schema_descriptor(Before)) != stable_hash(schema_descriptor(After))
    assert stable_hash({"records": schema_descriptor(Before), "features": ("a",)}) != stable_hash(
        {"records": schema_descriptor(Before), "features": ("a", "b")}
    )


def test_numeric_contract_has_field_by_field_public_coverage() -> None:
    classes = (
        EngineObservationV1,
        PlayerViewV1,
        PublicEventV1,
        LegalOptionV1,
        SelectionRequestV1,
    )
    for record in classes:
        assert set(NUMERIC_FIELD_COVERAGE[record.__name__]) == {
            field.name for field in fields(record)
        }


def test_attached_energy_resolution_uses_engine_owner_and_index_not_actor() -> None:
    raw = raw_observation(
        options=[{
            "type": 6, "area": 4, "index": 0, "playerIndex": 1,
            "energyIndex": 0, "count": 2,
        }]
    )
    raw["select"].update({"type": 4, "context": 30})
    raw["current"]["players"][1]["active"] = [{
        "id": 900, "serial": 80, "playerIndex": 1, "hp": 100, "maxHp": 100,
        "appearThisTurn": False, "energies": [11],
        "energyCards": [{"id": 15, "serial": 81, "playerIndex": 1}],
        "tools": [], "preEvolution": [],
    }]
    observation, request = semantic_snapshot(raw, "ownership", 0, CARD_HASH)
    assert request is not None
    option = request.options[0]
    source = next(entity for entity in observation.entities if entity.entity_key == option.source_ref)
    assert source.owner == 1
    assert source.card_id == 15
    assert source.position == 0
    assert source.parent_entity_key == "p1:s80"
