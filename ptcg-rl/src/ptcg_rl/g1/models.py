from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, fields, is_dataclass
from typing import Any, Mapping


CONTRACT_VERSION = 2

ENTITY_FEATURE_NAMES = (
    "card_id", "serial", "owner", "zone", "position", "parent_entity_index", "hp",
    "max_hp", "damage", "appear_this_turn", "attached_energy_count", "attached_tool_count",
    "evolution_depth", "visible", "status_poisoned", "status_burned", "status_asleep",
    "status_paralyzed", "status_confused",
)
PLAYER_FEATURE_NAMES = (
    "player_index", "bench_max", "deck_count", "hand_count", "prize_count",
    "visible_prize_count", "hand_visible", "facedown_active_count",
)
OPTION_FEATURE_NAMES = (
    "selection_type", "selection_context", "option_type", "number", "area", "index",
    "player_index", "tool_index", "energy_index", "count", "in_play_area", "in_play_index",
    "attack_id", "card_id", "serial", "special_condition_type", "source_kind",
    "source_entity_index", "target_kind", "target_entity_index", "choice_role",
)
EVENT_FEATURE_NAMES = (
    "event_type", "playerIndex", "hasBasicPokemon", "cardId", "serial", "fromArea",
    "toArea", "cardIdActive", "serialActive", "cardIdBench", "serialBench", "cardIdBefore",
    "serialBefore", "cardIdAfter", "serialAfter", "cardIdTarget", "serialTarget", "attackId",
    "value", "putDamageCounter", "isRecover", "head", "result", "reason",
)
GLOBAL_FEATURE_NAMES = (
    "acting_player", "turn", "turn_action_count", "first_player", "supporter_played",
    "stadium_played", "energy_attached", "retreated", "terminal_result", "min_count", "max_count",
    "selection_type", "selection_context", "request_ordered", "context_card_id", "effect_card_id",
    "remain_damage_counter", "remain_energy_cost", "self_deck_count", "self_hand_count",
    "self_prize_count", "opponent_deck_count", "opponent_hand_count", "opponent_prize_count",
)


class ContractViolation(ValueError):
    pass


def canonical_json(value: Any) -> str:
    if is_dataclass(value):
        value = asdict(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def schema_descriptor(*classes: type[Any]) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "records": {
            cls.__name__: [{"name": item.name, "type": str(item.type)} for item in fields(cls)]
            for cls in classes
        },
    }


@dataclass(frozen=True)
class VisibleEntityV1:
    entity_key: str
    card_id: int | None
    serial: int | None
    metadata_ref: str | None
    owner: int
    zone: int
    position: int | None
    parent_entity_key: str | None = None
    hp: int | None = None
    max_hp: int | None = None
    damage: int | None = None
    appear_this_turn: bool | None = None
    energy_types: tuple[int, ...] = ()
    attached_energy_count: int = 0
    attached_tool_count: int = 0
    evolution_depth: int = 0
    statuses: tuple[int, ...] = ()
    visible: bool = True


@dataclass(frozen=True)
class PlayerViewV1:
    player_index: int
    bench_max: int
    deck_count: int
    hand_count: int
    prize_count: int
    visible_prize_count: int
    hand_visible: bool
    facedown_active_count: int


@dataclass(frozen=True)
class PublicEventV1:
    event_type: int
    event_name: str | None
    fields: Mapping[str, int | bool | None]


@dataclass(frozen=True)
class EngineObservationV1:
    schema_version: int
    battle_id: str
    transition_id: int
    acting_player: int | None
    terminal_result: int | None
    turn: int | None
    turn_action_count: int | None
    first_player: int | None
    supporter_played: bool | None
    stadium_played: bool | None
    energy_attached: bool | None
    retreated: bool | None
    players: tuple[PlayerViewV1, ...]
    entities: tuple[VisibleEntityV1, ...]
    public_events: tuple[PublicEventV1, ...]
    previous_request_ref: str | None = None
    previous_action_ref: str | None = None

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> EngineObservationV1:
        entities = []
        for item in value["entities"]:
            converted = dict(item)
            converted["energy_types"] = tuple(converted["energy_types"])
            converted["statuses"] = tuple(converted["statuses"])
            entities.append(VisibleEntityV1(**converted))
        return cls(
            **{
                **dict(value),
                "players": tuple(PlayerViewV1(**item) for item in value["players"]),
                "entities": tuple(entities),
                "public_events": tuple(PublicEventV1(**item) for item in value["public_events"]),
            }
        )


@dataclass(frozen=True)
class LegalOptionV1:
    schema_version: int
    original_index: int
    selection_type: int
    selection_context: int
    option_type: int
    option_name: str | None
    number: int | None = None
    area: int | None = None
    index: int | None = None
    player_index: int | None = None
    tool_index: int | None = None
    energy_index: int | None = None
    count: int | None = None
    in_play_area: int | None = None
    in_play_index: int | None = None
    attack_id: int | None = None
    card_id: int | None = None
    serial: int | None = None
    special_condition_type: int | None = None
    source_kind: str = "NONE"
    source_ref: str | None = None
    target_kind: str = "NONE"
    target_ref: str | None = None
    choice_role: str = "UNKNOWN"
    source_entity_key: str | None = None
    target_entity_key: str | None = None
    available: bool = True
    semantic_fingerprint: str = ""

    def semantic_payload(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("original_index")
        value.pop("semantic_fingerprint")
        return value


@dataclass(frozen=True)
class SelectionRequestV1:
    schema_version: int
    episode_uuid: str
    selection_seq: int
    request_id: str
    acting_player: int
    selection_type: int
    selection_context: int
    min_count: int
    max_count: int
    remain_damage_counter: int | None
    remain_energy_cost: int | None
    context_card_id: int | None
    effect_card_id: int | None
    ordering: str
    options: tuple[LegalOptionV1, ...]

    def __post_init__(self) -> None:
        if self.schema_version != CONTRACT_VERSION:
            raise ContractViolation("request schema version differs from contract")
        if not self.episode_uuid or not self.request_id:
            raise ContractViolation("request identities must be nonempty")
        if self.acting_player not in (0, 1):
            raise ContractViolation("request acting player must be 0 or 1")
        if self.min_count < 0 or self.max_count < self.min_count:
            raise ContractViolation("invalid request bounds")
        available_count = sum(option.available for option in self.options)
        if self.max_count > available_count:
            raise ContractViolation("max_count exceeds available legal option count")
        if self.selection_seq < 0:
            raise ContractViolation("selection_seq must be nonnegative")
        if self.ordering not in {"ORDERED", "UNORDERED"}:
            raise ContractViolation("unknown request ordering")
        originals = [option.original_index for option in self.options]
        if len(originals) != len(set(originals)):
            raise ContractViolation("duplicate original engine index")
        if set(originals) != set(range(len(self.options))):
            raise ContractViolation("original engine indices must cover the native option list")
        for option in self.options:
            if option.schema_version != CONTRACT_VERSION:
                raise ContractViolation("option schema version differs from request")
            if option.selection_type != self.selection_type:
                raise ContractViolation("option selection type differs from request")
            if option.selection_context != self.selection_context:
                raise ContractViolation("option selection context differs from request")
            if not isinstance(option.available, bool):
                raise ContractViolation("option availability must be boolean")

    @property
    def is_optional(self) -> bool:
        return self.min_count == 0

    @property
    def has_only_one_outcome(self) -> bool:
        return self.max_count == 0 or (
            self.min_count == self.max_count == 1 and len(self.options) == 1
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> SelectionRequestV1:
        return cls(
            **{
                **dict(value),
                "options": tuple(LegalOptionV1(**item) for item in value["options"]),
            }
        )


@dataclass(frozen=True)
class SubSelectionV1:
    substep: int
    model_order_original_indices: tuple[int, ...]
    available_model_mask: tuple[bool, ...]
    stop_available: bool
    chosen_prefix_original_indices: tuple[int, ...]
    chosen_token: str
    chosen_model_index: int | None
    chosen_semantic_fingerprint: str | None
    original_index: int | None
    token_probabilities: tuple[float, ...]
    log_probability: float


@dataclass(frozen=True)
class CompoundActionV1:
    schema_version: int
    episode_uuid: str
    acting_player: int
    selection_seq: int
    request_id: str
    steps: tuple[SubSelectionV1, ...]
    submitted_original_indices: tuple[int, ...]
    stopped_early: bool
    policy_loss_mask: int
    log_probability_sum: float

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> CompoundActionV1:
        steps = []
        for item in value["steps"]:
            converted = dict(item)
            converted["model_order_original_indices"] = tuple(
                converted["model_order_original_indices"]
            )
            converted["available_model_mask"] = tuple(converted["available_model_mask"])
            converted["chosen_prefix_original_indices"] = tuple(
                converted["chosen_prefix_original_indices"]
            )
            converted["token_probabilities"] = tuple(converted["token_probabilities"])
            steps.append(SubSelectionV1(**converted))
        return cls(
            **{
                **dict(value),
                "steps": tuple(steps),
                "submitted_original_indices": tuple(value["submitted_original_indices"]),
            }
        )


@dataclass(frozen=True)
class SchemaMetadataV1:
    schema_version: int
    engine_sha256: str
    card_data_sha256: str
    observation_schema_sha256: str
    action_schema_sha256: str
    trajectory_schema_sha256: str

    @classmethod
    def build(cls, engine_sha256: str, card_data_sha256: str) -> SchemaMetadataV1:
        return cls(
            schema_version=CONTRACT_VERSION,
            engine_sha256=engine_sha256,
            card_data_sha256=card_data_sha256,
            observation_schema_sha256=stable_hash(
                {
                    "records": schema_descriptor(
                        VisibleEntityV1, PlayerViewV1, PublicEventV1, EngineObservationV1,
                        NumericTensorV1,
                    ),
                    "entity_features": ENTITY_FEATURE_NAMES,
                    "player_features": PLAYER_FEATURE_NAMES,
                    "event_features": EVENT_FEATURE_NAMES,
                    "global_features": GLOBAL_FEATURE_NAMES,
                }
            ),
            action_schema_sha256=stable_hash(
                {
                    "records": schema_descriptor(
                        LegalOptionV1, SelectionRequestV1, SubSelectionV1, CompoundActionV1
                    ),
                    "option_features": OPTION_FEATURE_NAMES,
                }
            ),
            trajectory_schema_sha256=stable_hash(
                schema_descriptor(TransitionRecordV1, EpisodeSummaryV1)
            ),
        )


@dataclass(frozen=True)
class TransitionRecordV1:
    schema_version: int
    episode_id: str
    sequence_index: int
    observation: EngineObservationV1
    request: SelectionRequestV1 | None
    action: CompoundActionV1 | None
    terminal_result: int | None
    reward: float | None
    policy_loss_mask: int
    schema_metadata: SchemaMetadataV1

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> TransitionRecordV1:
        converted = dict(value)
        converted["observation"] = EngineObservationV1.from_dict(value["observation"])
        converted["request"] = (
            SelectionRequestV1.from_dict(value["request"]) if value["request"] else None
        )
        converted["action"] = CompoundActionV1.from_dict(value["action"]) if value["action"] else None
        converted["schema_metadata"] = SchemaMetadataV1(**value["schema_metadata"])
        return cls(**converted)


@dataclass(frozen=True)
class EpisodeSummaryV1:
    schema_version: int
    episode_id: str
    first_player: int | None
    terminal_result: int | None
    player_rewards: tuple[float, float] | None
    engine_requests: int
    meaningful_choices: int
    forced_requests: int
    transition_records: int
    invalid_selections: int
    post_terminal_actions: int
    fallback_actions: int
    failure_kind: str | None
    selection_type_counts: Mapping[str, int]
    option_type_counts: Mapping[str, int]
    multi_select_requests: int
    max_observed_options: int
    max_observed_select_count: int
    wall_seconds: float
    schema_metadata: SchemaMetadataV1

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> EpisodeSummaryV1:
        converted = dict(value)
        converted["player_rewards"] = (
            tuple(value["player_rewards"]) if value["player_rewards"] is not None else None
        )
        converted["schema_metadata"] = SchemaMetadataV1(**value["schema_metadata"])
        return cls(**converted)


@dataclass(frozen=True)
class NumericTensorV1:
    schema_version: int
    player_feature_names: tuple[str, ...]
    player_values: tuple[tuple[float, ...], ...]
    player_missing_masks: tuple[tuple[bool, ...], ...]
    player_length: int
    entity_feature_names: tuple[str, ...]
    entity_values: tuple[tuple[float, ...], ...]
    entity_missing_masks: tuple[tuple[bool, ...], ...]
    entity_length: int
    entity_energy_values: tuple[int, ...]
    entity_energy_offsets: tuple[int, ...]
    option_feature_names: tuple[str, ...]
    option_values: tuple[tuple[float, ...], ...]
    option_missing_masks: tuple[tuple[bool, ...], ...]
    option_available_mask: tuple[bool, ...]
    option_offsets: tuple[int, ...]
    option_length: int
    event_feature_names: tuple[str, ...]
    event_values: tuple[tuple[float, ...], ...]
    event_missing_masks: tuple[tuple[bool, ...], ...]
    event_length: int
    global_feature_names: tuple[str, ...]
    global_values: tuple[float, ...]
    global_missing_mask: tuple[bool, ...]

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> NumericTensorV1:
        converted = dict(value)
        for key in (
            "player_feature_names",
            "entity_feature_names",
            "option_feature_names",
            "option_available_mask",
            "option_offsets",
            "event_feature_names",
            "global_feature_names",
            "global_values",
            "global_missing_mask",
            "entity_energy_values",
            "entity_energy_offsets",
        ):
            converted[key] = tuple(converted[key])
        for key in (
            "player_values",
            "player_missing_masks",
            "entity_values",
            "entity_missing_masks",
            "option_values",
            "option_missing_masks",
            "event_values",
            "event_missing_masks",
        ):
            converted[key] = tuple(tuple(row) for row in converted[key])
        return cls(**converted)


def record_dict(value: Any) -> dict[str, Any]:
    if not is_dataclass(value):
        raise TypeError("record must be a dataclass")
    return asdict(value)
