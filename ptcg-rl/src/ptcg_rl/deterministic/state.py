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
    VisibleEntityV1,
)


STATE_SCHEMA_VERSION = 1
_KNOWN_ZONES = frozenset(range(1, 25))
_EVENT_TYPE_COUNT = 24
_OPTION_TYPE_COUNT = 17
_SELECTION_TYPE_COUNT = 11
_SELECTION_CONTEXT_COUNT = 49
_ENTITY_KINDS = frozenset({"NONE", "ENTITY", "PLAYER", "PSEUDO", "TEMPORARY"})
_CHOICE_ROLES = frozenset(
    {"NUMBER", "YES", "NO", "CARD", "TOOL_CARD", "ENERGY_CARD", "ENERGY", "PLAY", "ATTACH",
     "EVOLVE", "ABILITY", "DISCARD", "RETREAT", "ATTACK", "END", "SKILL", "SPECIAL_CONDITION"}
)


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

    if isinstance(owner, bool) or owner not in (0, 1) or isinstance(serial, bool) or not isinstance(serial, int):
        raise PublicStateError("known entity owner/serial is invalid")
    if serial <= 0:
        raise PublicStateError("known entity serial must be positive")
    return f"p{owner}:s{serial}"


def hidden_slot_key(owner: int, zone: int, position: int) -> str:
    """Return a canonical location key for an unknown card slot."""

    if isinstance(owner, bool) or owner not in (0, 1):
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
    if isinstance(entity.owner, bool) or entity.owner not in (0, 1) or (
        isinstance(entity.zone, bool) or entity.zone not in _KNOWN_ZONES
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
        expected = hidden_slot_key(entity.owner, entity.zone, entity.position)
    else:
        if entity.card_id is None or entity.serial is None or not entity.visible:
            raise PublicStateError("entity must be either fully known or a hidden slot")
        if isinstance(entity.card_id, bool) or not isinstance(entity.card_id, int) or entity.card_id <= 0:
            raise PublicStateError("known entity card_id must be a positive integer")
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
    return replace(event, fields=_freeze(dict(event.fields)))


def _frozen_entity(entity: VisibleEntityV1) -> VisibleEntityV1:
    return replace(entity, energy_types=tuple(entity.energy_types), statuses=tuple(entity.statuses))


def _frozen_observation(observation: EngineObservationV1) -> EngineObservationV1:
    return replace(
        observation,
        players=tuple(observation.players),
        entities=tuple(_frozen_entity(entity) for entity in observation.entities),
        public_events=tuple(_frozen_event(event) for event in observation.public_events),
    )


def _frozen_request(request: SelectionRequestV1) -> SelectionRequestV1:
    return replace(request, options=tuple(request.options))


def _validate_entities(entities: Sequence[VisibleEntityV1]) -> set[str]:
    keys: set[str] = set()
    for entity in entities:
        key = canonical_entity_key(entity)
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
        if not isinstance(event, PublicEventV1) or isinstance(event.event_type, bool) or event.event_type not in range(_EVENT_TYPE_COUNT):
            raise PublicStateError("unknown public event enum")
        if event.event_name is not None and (not isinstance(event.event_name, str) or not event.event_name):
            raise PublicStateError("event_name must be a nonempty string or None")
        if not isinstance(event.fields, Mapping):
            raise PublicStateError("event fields must be a mapping")
        for key, value in event.fields.items():
            if key not in allowed_fields or not isinstance(key, str):
                raise PublicStateError(f"unsupported public event field {key!r}")
            if value is not None and (not isinstance(value, (int, bool))):
                raise PublicStateError("public event fields must be scalar numeric values")


def _validate_request(request: SelectionRequestV1, entity_keys: set[str]) -> None:
    if not isinstance(request, SelectionRequestV1):
        raise PublicStateError("ongoing state request must be a G1 SelectionRequestV1")
    if isinstance(request.selection_type, bool) or request.selection_type not in range(_SELECTION_TYPE_COUNT):
        raise PublicStateError("unknown selection type")
    if isinstance(request.selection_context, bool) or request.selection_context not in range(_SELECTION_CONTEXT_COUNT):
        raise PublicStateError("unknown selection context")
    if request.ordering not in {"ORDERED", "UNORDERED"}:
        raise PublicStateError("unknown request ordering")
    for option in request.options:
        if isinstance(option.option_type, bool) or option.option_type not in range(_OPTION_TYPE_COUNT):
            raise PublicStateError("unknown legal option type")
        if option.source_kind not in _ENTITY_KINDS or option.target_kind not in _ENTITY_KINDS:
            raise PublicStateError("unknown legal option entity kind")
        if option.choice_role not in _CHOICE_ROLES:
            raise PublicStateError("unknown legal option choice role")
        if option.source_kind == "ENTITY":
            if option.source_entity_key is None or option.source_entity_key not in entity_keys:
                raise PublicStateError("legal option source entity is outside the snapshot")
        elif option.source_entity_key is not None:
            raise PublicStateError("non-entity option source carries an entity key")
        if option.target_kind == "ENTITY":
            if option.target_entity_key is None or option.target_entity_key not in entity_keys:
                raise PublicStateError("legal option target entity is outside the snapshot")
        elif option.target_entity_key is not None:
            raise PublicStateError("non-entity option target carries an entity key")


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
        if self.schema_version != STATE_SCHEMA_VERSION:
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
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int) or self.schema_version != STATE_SCHEMA_VERSION:
            raise PublicStateError("unknown public state schema version")
        if self.observation.schema_version != CONTRACT_VERSION:
            raise PublicStateError("observation is not the G1 contract version")
        if not self.observation.battle_id or not isinstance(self.observation.battle_id, str):
            raise PublicStateError("battle_id must be a nonempty string")
        if isinstance(self.observation.transition_id, bool) or not isinstance(self.observation.transition_id, int) or self.observation.transition_id < 0:
            raise PublicStateError("transition_id must be a nonnegative integer")
        if isinstance(self.observation.acting_player, bool) or self.observation.acting_player not in (None, 0, 1):
            raise PublicStateError("acting_player must be player 0, player 1, or None")
        if self.observation.terminal_result not in (None, 0, 1, 2):
            raise PublicStateError("unknown terminal result enum")
        if self.observation.terminal_result is not None and self.request is not None:
            raise PublicStateError("terminal state cannot retain a selection request")
        if self.observation.terminal_result is None and self.request is None and self.observation.acting_player is not None:
            raise PublicStateError("ongoing state must carry its complete selection request")
        if self.observation.acting_player is None and self.observation.players:
            raise PublicStateError("a lifecycle/start state cannot carry player-private rows")
        if self.request is not None and self.request.acting_player != self.observation.acting_player:
            raise PublicStateError("request actor differs from observation actor")
        if self.request is not None and self.request.selection_seq != self.observation.transition_id:
            raise PublicStateError("request sequence differs from observation transition")
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
        if self.ledger_seed.schema_version != STATE_SCHEMA_VERSION:
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
