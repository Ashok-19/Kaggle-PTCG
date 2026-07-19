from __future__ import annotations

from dataclasses import replace

from ptcg_rl.g1.actions import permute_request
from ptcg_rl.g1.semantic import AREA, semantic_snapshot
from ptcg_rl.g2.models import model_schema_descriptor, model_schema_sha256
from ptcg_rl.g2.projection import project_decision, reorder_option_features
from ..g1_fixtures import raw_observation

CARD_HASH = "c" * 64


def pokemon(card_id: int, serial: int) -> dict[str, object]:
    return {
        "id": card_id,
        "serial": serial,
        "playerIndex": 0,
        "hp": 100,
        "maxHp": 120,
        "appearThisTurn": False,
        "energies": [1],
        "energyCards": [],
        "tools": [],
        "preEvolution": [],
    }


def serial_fixture(serial: int):
    raw = raw_observation(options=[{"type": 15, "cardId": 100, "serial": serial}])
    raw["select"].update({"type": 5, "context": 34})
    raw["current"]["players"][0]["active"] = [pokemon(100, serial)]
    raw["logs"] = [
        {
            "type": 15,
            "playerIndex": 0,
            "cardId": 100,
            "serial": serial,
            "attackId": 7,
        },
        {
            "type": 16,
            "cardIdTarget": 100,
            "serialTarget": serial,
            "value": -20,
            "putDamageCounter": False,
            "isRecover": False,
        },
    ]
    observation, request = semantic_snapshot(raw, "serial-fixture", 0, CARD_HASH)
    assert request is not None
    return observation, request


def test_model_features_are_invariant_to_raw_serial_renumbering() -> None:
    first_observation, first_request = serial_fixture(10)
    second_observation, second_request = serial_fixture(900_001)
    first = project_decision(first_observation, first_request)
    second = project_decision(second_observation, second_request)
    assert first.model == second.model
    assert first.transport.semantic_fingerprints != second.transport.semantic_fingerprints
    assert first.model.event_identity_values[0][0] == first.model.event_identity_values[1][-1]
    assert first.model.event_entity_indices[0][0] == 0
    assert first.model.event_entity_indices[1][-1] == 0


def test_option_permutation_only_permutes_option_feature_rows() -> None:
    raw = raw_observation(options=[{"type": 0, "number": value} for value in range(5)])
    raw["select"].update({"type": 8, "context": 38})
    observation, request = semantic_snapshot(raw, "permutation", 0, CARD_HASH)
    assert request is not None
    permutation = [4, 1, 3, 0, 2]
    original = project_decision(observation, request)
    permuted_request = permute_request(request, permutation)
    permuted = project_decision(observation, permuted_request)
    assert reorder_option_features(original.model, permutation) == permuted.model
    assert permuted.transport.original_indices == tuple(permutation)


def test_only_semantic_active_and_bench_positions_enter_actor_features() -> None:
    raw = raw_observation()
    raw["current"]["players"][0]["active"] = [pokemon(100, 10)]
    raw["current"]["players"][0]["bench"] = [pokemon(101, 11), pokemon(102, 12)]
    raw["current"]["players"][0]["hand"] = [
        {"id": 200, "serial": 20, "playerIndex": 0},
        {"id": 201, "serial": 21, "playerIndex": 0},
    ]
    raw["current"]["players"][0]["handCount"] = 2
    observation, request = semantic_snapshot(raw, "roles", 0, CARD_HASH)
    assert request is not None
    model = project_decision(observation, request).model
    zone_index = model.entity_categorical_names.index("zone")
    role_index = model.entity_categorical_names.index("role_position")
    positions_by_zone: dict[int, list[int]] = {}
    for row in model.entity_categorical_values:
        positions_by_zone.setdefault(row[zone_index], []).append(row[role_index])
    assert positions_by_zone[AREA["ACTIVE"]] == [1]
    assert positions_by_zone[AREA["BENCH"]] == [1, 2]
    assert positions_by_zone[AREA["HAND"]] == [0, 0]


def test_model_schema_explicitly_excludes_transport_and_serial_magnitude() -> None:
    descriptor = model_schema_descriptor()
    feature_groups = descriptor["features"]
    magnitude_groups = (
        feature_groups["entity_categorical"],
        feature_groups["entity_numeric"],
        feature_groups["option_categorical"],
        feature_groups["option_numeric"],
    )
    assert all("serial" not in name for group in magnitude_groups for name in group)
    assert all("original_index" not in name for group in magnitude_groups for name in group)
    assert "entity_serial_magnitude" in descriptor["forbidden_actor_features"]
    assert "option_original_index" in descriptor["forbidden_actor_features"]
    assert len(model_schema_sha256()) == 64


def test_transport_mapping_is_separate_from_model_features() -> None:
    observation, request = serial_fixture(10)
    projected = project_decision(observation, request)
    changed_transport = replace(projected.transport, original_indices=(99,))
    changed_projection = replace(projected, transport=changed_transport)
    assert changed_projection.transport != projected.transport
    assert changed_projection.model == projected.model
