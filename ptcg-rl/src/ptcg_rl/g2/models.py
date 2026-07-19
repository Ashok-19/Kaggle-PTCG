from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any

from ptcg_rl.g1.models import stable_hash

MODEL_SCHEMA_VERSION = 1

PLAYER_CATEGORICAL_NAMES = ("relative_player", "hand_visible")
PLAYER_NUMERIC_NAMES = (
    "bench_max",
    "deck_count",
    "hand_count",
    "prize_count",
    "visible_prize_count",
    "facedown_active_count",
)
ENTITY_CATEGORICAL_NAMES = (
    "card_id",
    "relative_owner",
    "zone",
    "role_position",
)
ENTITY_NUMERIC_NAMES = (
    "hp",
    "max_hp",
    "damage",
    "appear_this_turn",
    "attached_energy_count",
    "attached_tool_count",
    "evolution_depth",
    "visible",
    "status_poisoned",
    "status_burned",
    "status_asleep",
    "status_paralyzed",
    "status_confused",
)
EVENT_CATEGORICAL_NAMES = (
    "event_type",
    "relative_player",
    "has_basic_pokemon",
    "card_id",
    "from_area",
    "to_area",
    "card_id_active",
    "card_id_bench",
    "card_id_before",
    "card_id_after",
    "card_id_target",
    "attack_id",
    "put_damage_counter",
    "is_recover",
    "coin_head",
    "result",
    "reason",
)
EVENT_NUMERIC_NAMES = ("value",)
EVENT_IDENTITY_NAMES = (
    "serial",
    "serial_active",
    "serial_bench",
    "serial_before",
    "serial_after",
    "serial_target",
)
OPTION_CATEGORICAL_NAMES = (
    "selection_type",
    "selection_context",
    "option_type",
    "source_kind",
    "target_kind",
    "choice_role",
    "area",
    "in_play_area",
    "relative_player",
    "attack_id",
    "card_id",
    "special_condition_type",
)
OPTION_NUMERIC_NAMES = ("number", "count")
GLOBAL_CATEGORICAL_NAMES = (
    "first_player_relative",
    "terminal_result",
    "selection_type",
    "selection_context",
    "request_ordered",
    "context_card_id",
    "effect_card_id",
)
GLOBAL_NUMERIC_NAMES = (
    "turn",
    "turn_action_count",
    "min_count",
    "max_count",
    "remain_damage_counter",
    "remain_energy_cost",
    "self_deck_count",
    "self_hand_count",
    "self_prize_count",
    "opponent_deck_count",
    "opponent_hand_count",
    "opponent_prize_count",
)


@dataclass(frozen=True)
class ModelInputV1:
    schema_version: int
    player_categorical_names: tuple[str, ...]
    player_categorical_values: tuple[tuple[int, ...], ...]
    player_categorical_missing: tuple[tuple[bool, ...], ...]
    player_numeric_names: tuple[str, ...]
    player_numeric_values: tuple[tuple[float, ...], ...]
    player_numeric_missing: tuple[tuple[bool, ...], ...]
    entity_categorical_names: tuple[str, ...]
    entity_categorical_values: tuple[tuple[int, ...], ...]
    entity_categorical_missing: tuple[tuple[bool, ...], ...]
    entity_numeric_names: tuple[str, ...]
    entity_numeric_values: tuple[tuple[float, ...], ...]
    entity_numeric_missing: tuple[tuple[bool, ...], ...]
    entity_parent_indices: tuple[int, ...]
    entity_energy_values: tuple[int, ...]
    entity_energy_offsets: tuple[int, ...]
    event_categorical_names: tuple[str, ...]
    event_categorical_values: tuple[tuple[int, ...], ...]
    event_categorical_missing: tuple[tuple[bool, ...], ...]
    event_numeric_names: tuple[str, ...]
    event_numeric_values: tuple[tuple[float, ...], ...]
    event_numeric_missing: tuple[tuple[bool, ...], ...]
    event_identity_names: tuple[str, ...]
    event_identity_values: tuple[tuple[int, ...], ...]
    event_identity_missing: tuple[tuple[bool, ...], ...]
    event_entity_indices: tuple[tuple[int, ...], ...]
    option_categorical_names: tuple[str, ...]
    option_categorical_values: tuple[tuple[int, ...], ...]
    option_categorical_missing: tuple[tuple[bool, ...], ...]
    option_numeric_names: tuple[str, ...]
    option_numeric_values: tuple[tuple[float, ...], ...]
    option_numeric_missing: tuple[tuple[bool, ...], ...]
    option_source_entity_indices: tuple[int, ...]
    option_target_entity_indices: tuple[int, ...]
    option_available_mask: tuple[bool, ...]
    global_categorical_names: tuple[str, ...]
    global_categorical_values: tuple[int, ...]
    global_categorical_missing: tuple[bool, ...]
    global_numeric_names: tuple[str, ...]
    global_numeric_values: tuple[float, ...]
    global_numeric_missing: tuple[bool, ...]


@dataclass(frozen=True)
class OptionTransportMapV1:
    schema_version: int
    request_id: str
    original_indices: tuple[int, ...]
    semantic_fingerprints: tuple[str, ...]


@dataclass(frozen=True)
class ProjectedDecisionV1:
    schema_version: int
    model: ModelInputV1
    transport: OptionTransportMapV1


def model_schema_descriptor() -> dict[str, Any]:
    return {
        "schema_version": MODEL_SCHEMA_VERSION,
        "records": {
            record.__name__: [
                {"name": item.name, "type": str(item.type)} for item in fields(record)
            ]
            for record in (ModelInputV1, OptionTransportMapV1, ProjectedDecisionV1)
        },
        "features": {
            "player_categorical": PLAYER_CATEGORICAL_NAMES,
            "player_numeric": PLAYER_NUMERIC_NAMES,
            "entity_categorical": ENTITY_CATEGORICAL_NAMES,
            "entity_numeric": ENTITY_NUMERIC_NAMES,
            "event_categorical": EVENT_CATEGORICAL_NAMES,
            "event_numeric": EVENT_NUMERIC_NAMES,
            "event_identity": EVENT_IDENTITY_NAMES,
            "option_categorical": OPTION_CATEGORICAL_NAMES,
            "option_numeric": OPTION_NUMERIC_NAMES,
            "global_categorical": GLOBAL_CATEGORICAL_NAMES,
            "global_numeric": GLOBAL_NUMERIC_NAMES,
        },
        "forbidden_actor_features": (
            "entity_serial_magnitude",
            "event_serial_magnitude",
            "option_serial_magnitude",
            "option_original_index",
            "arbitrary_unordered_zone_position",
        ),
    }


def model_schema_sha256() -> str:
    return stable_hash(model_schema_descriptor())


def record_dict(value: Any) -> dict[str, Any]:
    return asdict(value)
