"""Public, immutable state primitives for the deterministic research agent.

This module is deliberately a translation boundary, not a strategy layer.  It
keeps the G1 semantic records intact, removes no legal options or public
events, and adds only ownership/lifetime metadata useful to later modules.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from hashlib import sha256
from json import dumps
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from ptcg_rl.g1.models import (
    CONTRACT_VERSION,
    EVENT_FEATURE_NAMES,
    EngineObservationV1,
    LegalOptionV1,
    PlayerViewV1,
    PublicEventV1,
    SelectionRequestV1,
    stable_hash,
    VisibleEntityV1,
)
from ptcg_rl.g1.semantic import (
    AREA,
    LOG_NAMES,
    OPTION_NAMES,
    PSEUDO_AREAS,
    SELECT_OPTION_TYPES,
    SOURCE_KIND_CODE,
)


STATE_SCHEMA_VERSION = 1
_KNOWN_ZONES = frozenset(AREA.values())
_SELECTION_CONTEXT_COUNT = 49
_ENTITY_KINDS = frozenset(SOURCE_KIND_CODE)


class PublicStateError(ValueError):
    """Raised when a public state cannot be normalized without guessing."""


class StateOrderError(PublicStateError):
    """Raised when a state tracker receives stale or conflicting input."""


class EntityLifetime(str, Enum):
    """Lifetime of a reference in the public observation.

    Known cards in durable physical zones and facedown board/Prize slots are
    stable references. Cards exposed only by a selection-local view are
    transient because no durable physical identity is implied by that view.
    """

    STABLE = "STABLE"
    TRANSIENT = "TRANSIENT"


def known_entity_key(owner: int, serial: int) -> str:
    """Return the canonical key used for a known physical entity."""

    if (
        isinstance(owner, bool)
        or not isinstance(owner, int)
        or owner not in (0, 1)
        or isinstance(serial, bool)
        or not isinstance(serial, int)
    ):
        raise PublicStateError("known entity owner/serial is invalid")
    if serial <= 0:
        raise PublicStateError("known entity serial must be positive")
    return f"p{owner}:s{serial}"


def hidden_slot_key(owner: int, zone: int, position: int) -> str:
    """Return a canonical location key for an unknown card slot."""

    if isinstance(owner, bool) or not isinstance(owner, int) or owner not in (0, 1):
        raise PublicStateError("hidden slot owner must be player 0 or 1")
    if any(isinstance(value, bool) or not isinstance(value, int) for value in (zone, position)):
        raise PublicStateError("hidden slot zone/position must be integers")
    if zone < 0 or position < 0:
        raise PublicStateError("hidden slot zone/position must be nonnegative")
    return f"slot:p{owner}:z{zone}:i{position}"


def canonical_entity_key(entity: VisibleEntityV1) -> str:
    """Recompute the non-semantic identity key and reject mismatches."""

    if not isinstance(entity, VisibleEntityV1):
        raise PublicStateError("entity must be a G1 VisibleEntityV1")
    if not isinstance(entity.visible, bool):
        raise PublicStateError("entity visibility must be a boolean")
    if isinstance(entity.owner, bool) or not isinstance(entity.owner, int) or entity.owner not in (0, 1) or (
        isinstance(entity.zone, bool) or not isinstance(entity.zone, int) or entity.zone not in _KNOWN_ZONES
    ):
        raise PublicStateError("entity owner or zone is outside the G1 public enum")
    if entity.position is not None and (
        isinstance(entity.position, bool) or not isinstance(entity.position, int) or entity.position < 0
    ):
        raise PublicStateError("entity position must be a nonnegative integer")
    hidden = entity.card_id is None and entity.serial is None and not entity.visible
    if hidden:
        if entity.position is None:
            raise PublicStateError("hidden entity needs a position")
        if entity.metadata_ref is not None:
            raise PublicStateError("hidden entity must not carry metadata")
        expected = hidden_slot_key(entity.owner, entity.zone, entity.position)
    else:
        if entity.card_id is None or entity.serial is None or not entity.visible:
            raise PublicStateError("entity must be either fully known or a hidden slot")
        if isinstance(entity.card_id, bool) or not isinstance(entity.card_id, int) or entity.card_id <= 0:
            raise PublicStateError("known entity card_id must be a positive integer")
        if isinstance(entity.serial, bool) or not isinstance(entity.serial, int) or entity.serial <= 0:
            raise PublicStateError("known entity serial must be a positive integer")
        if entity.position is None:
            raise PublicStateError("known entity needs a position")
        if (
            not isinstance(entity.metadata_ref, str)
            or not entity.metadata_ref.startswith(f"card:{entity.card_id}@")
            or len(entity.metadata_ref.rsplit("@", 1)[-1]) != 64
            or any(char not in "0123456789abcdef" for char in entity.metadata_ref.rsplit("@", 1)[-1])
        ):
            raise PublicStateError("known entity metadata is not canonical")
        expected = known_entity_key(entity.owner, entity.serial)
    if entity.entity_key != expected:
        raise PublicStateError(
            f"non-canonical entity key {entity.entity_key!r}; expected {expected!r}"
        )
    return expected


# Selection-local zones are exposed by the semantic adapter to describe a
# request, not to establish a durable board identity.  The values are G1's
# factual AREA enum values; no card names or effects are inferred here.
_TRANSIENT_ZONES = frozenset({1, 12, 13, 24})  # DECK, LOOKING, PLAYING, TEMPORARY
_STABLE_SLOT_ZONES = frozenset({2, 4, 5, 6})  # HAND, ACTIVE, BENCH, PRIZE


def entity_lifetime(entity: VisibleEntityV1) -> EntityLifetime:
    """Classify an entity without retaining private or strategic information."""

    canonical_entity_key(entity)
    if entity.serial is None:
        # A facedown active/bench/Prize position is a durable public slot.  It
        # must not be confused with a selection-local card view just because
        # both lack a card identity.
        return EntityLifetime.STABLE if entity.zone in _STABLE_SLOT_ZONES else EntityLifetime.TRANSIENT
    if entity.zone in _TRANSIENT_ZONES:
        return EntityLifetime.TRANSIENT
    return EntityLifetime.STABLE


def _freeze(value: Any) -> Any:
    """Recursively freeze containers while preserving public scalar values."""

    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, set):
        return frozenset(_freeze(item) for item in value)
    return value


def _canonical_value(value: Any) -> Any:
    """Convert mapping proxies and dataclasses into deterministic JSON values."""

    if isinstance(value, Mapping):
        return {str(key): _canonical_value(item) for key, item in sorted(value.items(), key=lambda x: str(x[0]))}
    if isinstance(value, (tuple, list, frozenset)):
        items = [_canonical_value(item) for item in value]
        return sorted(items, key=lambda item: dumps(item, sort_keys=True, separators=(",", ":"))) if isinstance(value, frozenset) else items
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {
            name: _canonical_value(getattr(value, name))
            for name in value.__dataclass_fields__
        }
    return value


def _digest(value: Any) -> str:
    raw = dumps(_canonical_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return sha256(raw).hexdigest()


def _frozen_event(event: PublicEventV1) -> PublicEventV1:
    try:
        return replace(event, fields=_freeze(dict(event.fields)))
    except (AttributeError, TypeError, ValueError) as error:
        raise PublicStateError("public event row is malformed") from error


def _frozen_entity(entity: VisibleEntityV1) -> VisibleEntityV1:
    try:
        return replace(entity, energy_types=tuple(entity.energy_types), statuses=tuple(entity.statuses))
    except (AttributeError, TypeError, ValueError) as error:
        raise PublicStateError("public entity row is malformed") from error


def _frozen_observation(observation: EngineObservationV1) -> EngineObservationV1:
    try:
        return replace(
            observation,
            players=tuple(observation.players),
            entities=tuple(_frozen_entity(entity) for entity in observation.entities),
            public_events=tuple(_frozen_event(event) for event in observation.public_events),
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise PublicStateError("public observation rows are malformed") from error


def _frozen_request(request: SelectionRequestV1) -> SelectionRequestV1:
    try:
        return replace(request, options=tuple(request.options))
    except (AttributeError, TypeError, ValueError) as error:
        raise PublicStateError("selection request rows are malformed") from error


def _validate_entities(entities: Sequence[VisibleEntityV1]) -> set[str]:
    keys: set[str] = set()
    for entity in entities:
        key = canonical_entity_key(entity)
        for name in ("attached_energy_count", "attached_tool_count", "evolution_depth"):
            value = getattr(entity, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise PublicStateError(f"entity {name} must be a nonnegative integer")
        for name in ("hp", "max_hp", "damage"):
            value = getattr(entity, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
                raise PublicStateError(f"entity {name} must be an integer or None")
        if entity.max_hp is not None and entity.max_hp <= 0:
            raise PublicStateError("entity max_hp must be positive")
        if entity.hp is not None and entity.hp < 0:
            raise PublicStateError("entity hp must be nonnegative")
        if entity.damage is not None and entity.damage < 0:
            raise PublicStateError("entity damage must be nonnegative")
        if entity.hp is not None and entity.max_hp is None:
            raise PublicStateError("entity hp requires max_hp")
        if entity.damage is not None and entity.max_hp is None:
            raise PublicStateError("entity damage requires max_hp")
        if entity.hp is not None and entity.max_hp is not None and entity.hp > entity.max_hp:
            raise PublicStateError("entity hp exceeds max_hp")
        if entity.damage is not None and entity.max_hp is not None and entity.damage > entity.max_hp:
            raise PublicStateError("entity damage exceeds max_hp")
        if (
            entity.hp is not None
            and entity.max_hp is not None
            and entity.damage is not None
            and entity.damage != entity.max_hp - entity.hp
        ):
            raise PublicStateError("entity hp and damage are inconsistent")
        if entity.appear_this_turn is not None and not isinstance(entity.appear_this_turn, bool):
            raise PublicStateError("entity appear_this_turn must be a boolean or None")
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in entity.energy_types):
            raise PublicStateError("entity energy types must be nonnegative integers")
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in entity.statuses):
            raise PublicStateError("entity statuses must be nonnegative integers")
        if key in keys:
            raise PublicStateError(f"duplicate public entity key {key!r}")
        keys.add(key)
        if entity.parent_entity_key is not None and not isinstance(entity.parent_entity_key, str):
            raise PublicStateError("entity parent key must be a string or None")
    for entity in entities:
        if entity.parent_entity_key is not None and entity.parent_entity_key not in keys:
            raise PublicStateError("entity parent key does not resolve in the same public snapshot")
    return keys


def _validate_events(events: Sequence[PublicEventV1]) -> None:
    allowed_fields = set(EVENT_FEATURE_NAMES) - {"event_type"}
    for event in events:
        if (
            not isinstance(event, PublicEventV1)
            or isinstance(event.event_type, bool)
            or not isinstance(event.event_type, int)
            or event.event_type not in LOG_NAMES
        ):
            raise PublicStateError("unknown public event enum")
        if event.event_name != LOG_NAMES[event.event_type]:
            raise PublicStateError("event name is inconsistent with event type")
        if not isinstance(event.fields, Mapping):
            raise PublicStateError("event fields must be a mapping")
        for key, value in event.fields.items():
            if not isinstance(key, str) or key not in allowed_fields:
                raise PublicStateError(f"unsupported public event field {key!r}")
            if value is not None and (not isinstance(value, (int, bool))):
                raise PublicStateError("public event fields must be scalar numeric values")


def _validate_request(request: SelectionRequestV1, entity_keys: set[str]) -> None:
    if not isinstance(request, SelectionRequestV1):
        raise PublicStateError("ongoing state request must be a G1 SelectionRequestV1")
    if (
        isinstance(request.schema_version, bool)
        or not isinstance(request.schema_version, int)
        or request.schema_version != CONTRACT_VERSION
    ):
        raise PublicStateError("request schema version differs from the G1 contract")
    if not isinstance(request.episode_uuid, str) or not request.episode_uuid:
        raise PublicStateError("request episode_uuid must be a nonempty string")
    if isinstance(request.selection_seq, bool) or not isinstance(request.selection_seq, int) or request.selection_seq < 0:
        raise PublicStateError("request selection_seq must be a nonnegative integer")
    if not isinstance(request.request_id, str) or not request.request_id:
        raise PublicStateError("request_id must be a nonempty string")
    if (
        isinstance(request.acting_player, bool)
        or not isinstance(request.acting_player, int)
        or request.acting_player not in (0, 1)
    ):
        raise PublicStateError("request actor must be player 0 or player 1")
    if (
        isinstance(request.selection_type, bool)
        or not isinstance(request.selection_type, int)
        or request.selection_type not in SELECT_OPTION_TYPES
    ):
        raise PublicStateError("unknown selection type")
    if (
        isinstance(request.selection_context, bool)
        or not isinstance(request.selection_context, int)
        or request.selection_context not in range(_SELECTION_CONTEXT_COUNT)
    ):
        raise PublicStateError("unknown selection context")
    for name in ("min_count", "max_count"):
        value = getattr(request, name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise PublicStateError(f"request {name} must be a nonnegative integer")
    if request.max_count < request.min_count:
        raise PublicStateError("request count bounds are invalid")
    if not isinstance(request.ordering, str) or request.ordering not in {"ORDERED", "UNORDERED"}:
        raise PublicStateError("unknown request ordering")
    expected_ordering = "ORDERED" if request.selection_type == 5 and request.selection_context == 34 else "UNORDERED"
    if request.ordering != expected_ordering:
        raise PublicStateError("request ordering is inconsistent with the G1 semantic contract")
    if not isinstance(request.options, tuple):
        raise PublicStateError("request options must be an immutable tuple")
    for name in (
        "remain_damage_counter", "remain_energy_cost", "context_card_id", "effect_card_id"
    ):
        value = getattr(request, name)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            raise PublicStateError(f"request {name} must be an integer or None")
    for option in request.options:
        if not isinstance(option, LegalOptionV1):
            raise PublicStateError("request options contain an invalid G1 legal option")
        if (
            isinstance(option.schema_version, bool)
            or not isinstance(option.schema_version, int)
            or option.schema_version != CONTRACT_VERSION
        ):
            raise PublicStateError("option schema version differs from request")
        if isinstance(option.original_index, bool) or not isinstance(option.original_index, int) or option.original_index < 0:
            raise PublicStateError("option original_index must be a nonnegative integer")
        if (
            isinstance(option.selection_type, bool)
            or not isinstance(option.selection_type, int)
            or option.selection_type != request.selection_type
        ):
            raise PublicStateError("option selection type differs from request")
        if (
            isinstance(option.selection_context, bool)
            or not isinstance(option.selection_context, int)
            or option.selection_context != request.selection_context
        ):
            raise PublicStateError("option selection context differs from request")
        if not isinstance(option.available, bool):
            raise PublicStateError("option availability must be boolean")
        for name in (
            "number", "area", "index", "player_index", "tool_index", "energy_index", "count",
            "in_play_area", "in_play_index", "attack_id", "card_id", "serial",
            "special_condition_type",
        ):
            value = getattr(option, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
                raise PublicStateError(f"option {name} must be an integer or None")
        if (
            isinstance(option.option_type, bool)
            or not isinstance(option.option_type, int)
            or option.option_type not in OPTION_NAMES
        ):
            raise PublicStateError("unknown legal option type")
        if option.option_type not in SELECT_OPTION_TYPES[request.selection_type]:
            raise PublicStateError("option type is incompatible with selection type")
        expected_name = OPTION_NAMES[option.option_type]
        if option.option_name != expected_name:
            raise PublicStateError("option name is inconsistent with option type")
        if option.choice_role != expected_name:
            raise PublicStateError("option choice role is inconsistent with option type")
        if not isinstance(option.semantic_fingerprint, str) or option.semantic_fingerprint != stable_hash(option.semantic_payload()):
            raise PublicStateError("option semantic fingerprint does not match canonical contents")
        if not isinstance(option.source_kind, str) or not isinstance(option.target_kind, str):
            raise PublicStateError("legal option source/target kinds must be strings")
        if option.source_kind not in _ENTITY_KINDS or option.target_kind not in _ENTITY_KINDS:
            raise PublicStateError("unknown legal option entity kind")

        for label, kind, reference, entity_key in (
            ("source", option.source_kind, option.source_ref, option.source_entity_key),
            ("target", option.target_kind, option.target_ref, option.target_entity_key),
        ):
            if kind == "NONE":
                if reference is not None or entity_key is not None:
                    raise PublicStateError(f"legal option {label} reference is inconsistent with NONE kind")
                continue
            if not isinstance(reference, str) or not reference:
                raise PublicStateError(f"legal option {label} reference is missing")
            if kind == "ENTITY":
                if entity_key != reference or entity_key not in entity_keys:
                    raise PublicStateError(f"legal option {label} entity reference is outside the snapshot")
                continue
            if entity_key is not None:
                raise PublicStateError(f"legal option {label} reference carries an entity key")
            if kind == "PLAYER":
                if reference not in {"player:0", "player:1"}:
                    raise PublicStateError(f"legal option {label} player reference is not canonical")
            elif kind == "PSEUDO":
                if reference != "pseudo:skill:default":
                    parts = reference.split(":")
                    if len(parts) != 7 or parts[:2] != ["pseudo", "area"] or parts[3] != "player" or parts[5] != "index":
                        raise PublicStateError(f"legal option {label} pseudo reference is not canonical")
                    try:
                        area = int(parts[2])
                        owner = int(parts[4])
                        index = int(parts[6])
                    except ValueError as error:
                        raise PublicStateError(f"legal option {label} pseudo reference is not canonical") from error
                    if (
                        str(area) != parts[2]
                        or str(owner) != parts[4]
                        or str(index) != parts[6]
                        or area not in PSEUDO_AREAS
                        or owner not in (0, 1)
                        or index < 0
                    ):
                        raise PublicStateError(f"legal option {label} pseudo reference is not canonical")
            elif kind == "TEMPORARY":
                parts = reference.split(":")
                if len(parts) != 5 or parts[0] != "temporary" or parts[1] != "player" or parts[3] != "index":
                    raise PublicStateError(f"legal option {label} temporary reference is not canonical")
                try:
                    owner = int(parts[2])
                    index = int(parts[4])
                except ValueError as error:
                    raise PublicStateError(f"legal option {label} temporary reference is not canonical") from error
                if (
                    str(owner) != parts[2]
                    or str(index) != parts[4]
                    or owner not in (0, 1)
                    or index < 0
                ):
                    raise PublicStateError(f"legal option {label} temporary reference is not canonical")


def _validate_players(players: Sequence[PlayerViewV1], acting_player: int | None) -> None:
    if acting_player is None:
        if players:
            raise PublicStateError("strict empty start marker cannot carry players")
        return
    if len(players) != 2:
        raise PublicStateError("public observation must contain exactly two players")
    if any(not isinstance(player, PlayerViewV1) for player in players):
        raise PublicStateError("public players contain an invalid G1 player row")
    if tuple(player.player_index for player in players) != (0, 1):
        raise PublicStateError("public players must use canonical player indices 0 and 1")
    for player in players:
        if isinstance(player.player_index, bool) or not isinstance(player.player_index, int):
            raise PublicStateError("public player index must be an integer")
        for name in ("bench_max", "deck_count", "hand_count", "prize_count", "visible_prize_count", "facedown_active_count"):
            value = getattr(player, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise PublicStateError(f"public player {name} must be a nonnegative integer")
        if player.visible_prize_count > player.prize_count:
            raise PublicStateError("public player visible Prize count exceeds Prize count")
        if not isinstance(player.hand_visible, bool):
            raise PublicStateError("public player hand visibility must be boolean")
        if player.hand_visible != (player.player_index == acting_player):
            raise PublicStateError("opponent hand visibility violates the public boundary")


def _validate_observation_metadata(observation: EngineObservationV1) -> None:
    if (
        observation.terminal_result is not None
        and (
            isinstance(observation.terminal_result, bool)
            or not isinstance(observation.terminal_result, int)
            or observation.terminal_result not in (0, 1, 2)
        )
    ):
        raise PublicStateError("unknown terminal result enum")
    for name in ("turn", "turn_action_count"):
        value = getattr(observation, name)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
            raise PublicStateError(f"observation {name} must be a nonnegative integer or None")
    if observation.first_player is not None and (
        isinstance(observation.first_player, bool)
        or not isinstance(observation.first_player, int)
        or observation.first_player not in (0, 1)
    ):
        raise PublicStateError("observation first_player must be player 0, player 1, or None")
    for name in ("supporter_played", "stadium_played", "energy_attached", "retreated"):
        value = getattr(observation, name)
        if value is not None and not isinstance(value, bool):
            raise PublicStateError(f"observation {name} must be a boolean or None")


@dataclass(frozen=True)
class ResourceLedgerSeedV1:
    """Public counts from which a later resource ledger may be initialized.

    This is intentionally accounting-only.  It contains no card scoring,
    route ranking, hidden-card inference, or policy decision.
    """

    schema_version: int
    visible_card_counts: tuple[tuple[int, int, int], ...]
    visible_zone_counts: tuple[tuple[int, int, int, int], ...]
    hidden_slot_counts: tuple[tuple[int, int, int], ...]

    def __post_init__(self) -> None:
        if (
            isinstance(self.schema_version, bool)
            or not isinstance(self.schema_version, int)
            or self.schema_version != STATE_SCHEMA_VERSION
        ):
            raise PublicStateError("unknown ledger seed schema version")
        if not all(isinstance(row, tuple) for row in (
            self.visible_card_counts, self.visible_zone_counts, self.hidden_slot_counts
        )):
            raise PublicStateError("ledger seed rows must be immutable tuples")
        if any(not isinstance(row, tuple) for rows in (
            self.visible_card_counts, self.visible_zone_counts, self.hidden_slot_counts
        ) for row in rows):
            raise PublicStateError("ledger seed entries must be immutable tuples")
        for row in self.visible_card_counts:
            if len(row) != 3:
                raise PublicStateError("visible card ledger entries have the wrong shape")
            owner, card_id, count = row
            if any(isinstance(value, bool) or not isinstance(value, int) for value in row):
                raise PublicStateError("visible card ledger entries must be integers")
            if owner not in (0, 1) or card_id <= 0 or count <= 0:
                raise PublicStateError("invalid visible card ledger count")
        for row in self.visible_zone_counts:
            if len(row) != 4:
                raise PublicStateError("visible zone ledger entries have the wrong shape")
            owner, zone, card_id, count = row
            if any(isinstance(value, bool) or not isinstance(value, int) for value in row):
                raise PublicStateError("visible zone ledger entries must be integers")
            if owner not in (0, 1) or zone not in _KNOWN_ZONES or card_id <= 0 or count <= 0:
                raise PublicStateError("invalid visible zone ledger count")
        for row in self.hidden_slot_counts:
            if len(row) != 3:
                raise PublicStateError("hidden ledger entries have the wrong shape")
            owner, zone, count = row
            if any(isinstance(value, bool) or not isinstance(value, int) for value in row):
                raise PublicStateError("hidden ledger entries must be integers")
            if owner not in (0, 1) or zone not in _KNOWN_ZONES or count <= 0:
                raise PublicStateError("invalid hidden slot ledger count")

    @property
    def card_counts(self) -> tuple[tuple[int, int, int], ...]:
        return self.visible_card_counts

    @property
    def unknown_slots(self) -> tuple[tuple[int, int, int], ...]:
        return self.hidden_slot_counts

    @classmethod
    def from_public_entities(
        cls, entities: Sequence[VisibleEntityV1], players: Sequence[PlayerViewV1]
    ) -> "ResourceLedgerSeedV1":
        cards: dict[tuple[int, int], int] = {}
        zones: dict[tuple[int, int, int], int] = {}
        hidden: dict[tuple[int, int], int] = {}
        _validate_entities(entities)
        for entity in entities:
            if entity.card_id is None:
                hidden[(entity.owner, entity.zone)] = hidden.get((entity.owner, entity.zone), 0) + 1
                continue
            cards[(entity.owner, entity.card_id)] = cards.get((entity.owner, entity.card_id), 0) + 1
            zones[(entity.owner, entity.zone, entity.card_id)] = zones.get(
                (entity.owner, entity.zone, entity.card_id), 0
            ) + 1
        # Zone lengths are public even where individual cards are hidden.  A
        # hand/deck/prize count is not converted into guessed card identities.
        for player in players:
            represented_hand = sum(
                count for (owner, zone, _), count in zones.items() if owner == player.player_index and zone == 2
            )
            represented_deck = sum(
                count for (owner, zone, _), count in zones.items() if owner == player.player_index and zone == 1
            )
            represented_prize = sum(
                count for (owner, zone, _), count in zones.items() if owner == player.player_index and zone == 6
            )
            existing_hand = hidden.get((player.player_index, 2), 0)
            existing_deck = hidden.get((player.player_index, 1), 0)
            existing_prize = hidden.get((player.player_index, 6), 0)
            if represented_hand + existing_hand > player.hand_count:
                raise PublicStateError("public hand rows exceed the reported hand count")
            if represented_deck + existing_deck > player.deck_count:
                raise PublicStateError("public deck rows exceed the reported deck count")
            if represented_prize + existing_prize > player.prize_count:
                raise PublicStateError("public Prize rows exceed the reported Prize count")
            hidden_hand = player.hand_count - represented_hand - existing_hand
            hidden_deck = player.deck_count - represented_deck - existing_deck
            hidden_prize = player.prize_count - represented_prize - existing_prize
            for zone, count in ((1, hidden_deck), (2, hidden_hand), (6, hidden_prize)):
                if count:
                    hidden[(player.player_index, zone)] = hidden.get((player.player_index, zone), 0) + count
        return cls(
            schema_version=STATE_SCHEMA_VERSION,
            visible_card_counts=tuple((owner, card_id, count) for (owner, card_id), count in sorted(cards.items())),
            visible_zone_counts=tuple((owner, zone, card_id, count) for (owner, zone, card_id), count in sorted(zones.items())),
            hidden_slot_counts=tuple((owner, zone, count) for (owner, zone), count in sorted(hidden.items())),
        )


@dataclass(frozen=True)
class PublicStateV1:
    """Recursively immutable public observation plus its current request."""

    schema_version: int
    observation: EngineObservationV1
    request: SelectionRequestV1 | None
    ledger_seed: ResourceLedgerSeedV1

    def __post_init__(self) -> None:
        if not isinstance(self.observation, EngineObservationV1):
            raise PublicStateError("state observation must be a G1 EngineObservationV1")
        if not isinstance(self.ledger_seed, ResourceLedgerSeedV1):
            raise PublicStateError("state ledger must be a ResourceLedgerSeedV1")
        # Also protect callers that construct the frozen dataclass directly,
        # rather than going through from_engine().
        object.__setattr__(self, "observation", _frozen_observation(self.observation))
        if self.request is not None:
            if not isinstance(self.request, SelectionRequestV1):
                raise PublicStateError("ongoing state request must be a G1 SelectionRequestV1")
            object.__setattr__(self, "request", _frozen_request(self.request))
        if (
            isinstance(self.schema_version, bool)
            or not isinstance(self.schema_version, int)
            or self.schema_version != STATE_SCHEMA_VERSION
        ):
            raise PublicStateError("unknown public state schema version")
        if (
            isinstance(self.observation.schema_version, bool)
            or not isinstance(self.observation.schema_version, int)
            or self.observation.schema_version != CONTRACT_VERSION
        ):
            raise PublicStateError("observation is not the G1 contract version")
        if not self.observation.battle_id or not isinstance(self.observation.battle_id, str):
            raise PublicStateError("battle_id must be a nonempty string")
        if isinstance(self.observation.transition_id, bool) or not isinstance(self.observation.transition_id, int) or self.observation.transition_id < 0:
            raise PublicStateError("transition_id must be a nonnegative integer")
        if (
            isinstance(self.observation.acting_player, bool)
            or (
                self.observation.acting_player is not None
                and not isinstance(self.observation.acting_player, int)
            )
            or self.observation.acting_player not in (None, 0, 1)
        ):
            raise PublicStateError("acting_player must be player 0, player 1, or None")
        _validate_observation_metadata(self.observation)
        if self.observation.terminal_result is not None and self.request is not None:
            raise PublicStateError("terminal state cannot retain a selection request")
        if self.observation.terminal_result is None and self.request is None and self.observation.acting_player is not None:
            raise PublicStateError("ongoing state must carry its complete selection request")
        _validate_players(self.observation.players, self.observation.acting_player)
        if self.observation.acting_player is None and (
            self.observation.terminal_result is not None
            or self.observation.transition_id != 0
            or self.observation.entities
            or self.observation.public_events
            or self.observation.turn is not None
            or self.observation.turn_action_count is not None
            or self.observation.first_player is not None
            or any(
                getattr(self.observation, name) is not None
                for name in ("supporter_played", "stadium_played", "energy_attached", "retreated")
            )
            or self.observation.previous_request_ref is not None
            or self.observation.previous_action_ref is not None
        ):
            raise PublicStateError("strict empty start marker contains stale state")
        if self.request is not None and self.request.acting_player != self.observation.acting_player:
            raise PublicStateError("request actor differs from observation actor")
        if self.request is not None and self.request.selection_seq != self.observation.transition_id:
            raise PublicStateError("request sequence differs from observation transition")
        if self.request is not None and self.request.episode_uuid != self.observation.battle_id:
            raise PublicStateError("request episode_uuid differs from observation battle_id")
        entity_keys = _validate_entities(self.observation.entities)
        _validate_events(self.observation.public_events)
        if self.request is not None:
            _validate_request(self.request, entity_keys)
        for entity in self.observation.entities:
            if (
                self.observation.acting_player is not None
                and entity.owner != self.observation.acting_player
                and entity.zone == 2
            ):
                raise PublicStateError("opponent hand entity is outside the public boundary")
        if self.ledger_seed != ResourceLedgerSeedV1.from_public_entities(
            self.observation.entities, self.observation.players
        ):
            raise PublicStateError("ledger seed does not match the public observation")
        if (
            isinstance(self.ledger_seed.schema_version, bool)
            or not isinstance(self.ledger_seed.schema_version, int)
            or self.ledger_seed.schema_version != STATE_SCHEMA_VERSION
        ):
            raise PublicStateError("ledger seed schema version differs from state")

    @classmethod
    def from_engine(
        cls, observation: EngineObservationV1, request: SelectionRequestV1 | None = None
    ) -> "PublicStateV1":
        # Do this before touching request fields.  A native terminal response
        # may carry stale/poisoned selection data and must still normalize.
        if not isinstance(observation, EngineObservationV1):
            raise PublicStateError("state observation must be a G1 EngineObservationV1")
        frozen_observation = _frozen_observation(observation)
        effective_request = None if frozen_observation.terminal_result is not None else request
        if effective_request is not None and not isinstance(effective_request, SelectionRequestV1):
            raise PublicStateError("ongoing state request must be a G1 SelectionRequestV1")
        if effective_request is not None:
            effective_request = _frozen_request(effective_request)
        _validate_observation_metadata(frozen_observation)
        _validate_players(frozen_observation.players, frozen_observation.acting_player)
        _validate_entities(frozen_observation.entities)
        ledger = ResourceLedgerSeedV1.from_public_entities(
            frozen_observation.entities, frozen_observation.players
        )
        return cls(STATE_SCHEMA_VERSION, frozen_observation, effective_request, ledger)

    @property
    def battle_id(self) -> str:
        return self.observation.battle_id

    @property
    def transition_id(self) -> int:
        return self.observation.transition_id

    @property
    def acting_player(self) -> int | None:
        return self.observation.acting_player

    @property
    def terminal_result(self) -> int | None:
        return self.observation.terminal_result

    @property
    def entities(self) -> tuple[VisibleEntityV1, ...]:
        return self.observation.entities

    @property
    def events(self) -> tuple[PublicEventV1, ...]:
        return self.observation.public_events

    @property
    def legal_options(self) -> tuple[LegalOptionV1, ...]:
        return self.request.options if self.request is not None else ()

    @property
    def stable_entities(self) -> tuple[VisibleEntityV1, ...]:
        return tuple(entity for entity in self.entities if entity_lifetime(entity) == EntityLifetime.STABLE)

    @property
    def transient_entities(self) -> tuple[VisibleEntityV1, ...]:
        return tuple(entity for entity in self.entities if entity_lifetime(entity) == EntityLifetime.TRANSIENT)

    def canonical_dict(self) -> dict[str, Any]:
        return _canonical_value(self)

    def state_hash(self) -> str:
        return _digest(self)

    @property
    def public_hash(self) -> str:
        return self.state_hash()


@dataclass(frozen=True)
class _TrackedState:
    state: PublicStateV1
    digest: str


class PublicStateTracker:
    """Optional monotonic/idempotent state ownership tracker."""

    def __init__(self, policy_id: str = "deterministic-v1") -> None:
        if not policy_id:
            raise StateOrderError("policy_id must be nonempty")
        self.policy_id = policy_id
        self._states: dict[tuple[str, int | None, str], _TrackedState] = {}
        self._latest: dict[tuple[str, str], int] = {}

    def observe(
        self, observation: EngineObservationV1, request: SelectionRequestV1 | None = None
    ) -> PublicStateV1:
        state = PublicStateV1.from_engine(observation, request)
        if state.acting_player is None and state.request is None:
            # A no-request observation is the explicit start/reset marker.
            self.reset(state.battle_id)
            return state
        key = (state.battle_id, state.acting_player, self.policy_id)
        digest = state.state_hash()
        lifecycle_key = (state.battle_id, self.policy_id)
        latest = self._latest.get(lifecycle_key)
        if latest is not None and state.transition_id < latest:
            raise StateOrderError("stale transition received")
        if latest is not None and state.transition_id == latest and key not in self._states:
            raise StateOrderError("duplicate transition has different acting player")
        previous = self._states.get(key)
        if (
            state.transition_id == 0
            and previous is not None
            and previous.state.terminal_result is not None
            and state.terminal_result is None
        ):
            # A terminal transition is retained for idempotent re-delivery,
            # but the next deck/start request begins a fresh lifecycle.
            self.reset(state.battle_id)
            latest = None
        previous = self._states.get(key)
        if previous is not None:
            prior_id = previous.state.transition_id
            if state.transition_id < prior_id:
                raise StateOrderError("stale transition received")
            if state.transition_id == prior_id:
                if digest != previous.digest:
                    raise StateOrderError("duplicate transition has different public contents")
                return previous.state
        if state.transition_id == 0 and latest is not None:
            if previous is not None and previous.state.terminal_result is None:
                raise StateOrderError("start transition is stale before terminal lifecycle boundary")
            if any(value.state.terminal_result is None for value in self._states.values() if value.state.battle_id == state.battle_id):
                raise StateOrderError("start transition received before terminal lifecycle boundary")
            self.reset(state.battle_id)
        if state.terminal_result is not None:
            self.reset(state.battle_id)
        self._states[key] = _TrackedState(state, digest)
        self._latest[lifecycle_key] = state.transition_id
        return state

    update = observe

    def last(self, battle_id: str, acting_player: int | None) -> PublicStateV1 | None:
        tracked = self._states.get((battle_id, acting_player, self.policy_id))
        return tracked.state if tracked else None

    def reset(self, battle_id: str, acting_player: int | None = None) -> None:
        keys = [
            key for key in self._states
            if key[0] == battle_id and (acting_player is None or key[1] == acting_player)
        ]
        for key in keys:
            del self._states[key]
        if acting_player is None:
            self._latest.pop((battle_id, self.policy_id), None)

    def on_start(self, battle_id: str) -> None:
        """Reset all player state at a new deck/start lifecycle boundary."""

        self.reset(battle_id)

    def on_error(self, battle_id: str) -> None:
        """Drop state after a worker/engine error; errors cannot advance state."""

        self.reset(battle_id)


# Explicit alternate names keep the boundary discoverable without creating a
# second state representation.
PublicState = PublicStateV1
StateTracker = PublicStateTracker
LedgerSeedV1 = ResourceLedgerSeedV1


__all__ = [
    "EntityLifetime",
    "LedgerSeedV1",
    "PublicState",
    "PublicStateError",
    "PublicStateTracker",
    "PublicStateV1",
    "ResourceLedgerSeedV1",
    "StateOrderError",
    "StateTracker",
    "canonical_entity_key",
    "entity_lifetime",
    "hidden_slot_key",
    "known_entity_key",
]
