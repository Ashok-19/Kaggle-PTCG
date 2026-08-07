"""Public-semantic deterministic control for the Mega Abomasnow fixture.

This is a small, self-contained control translation of the frozen rule
anchor.  It deliberately consumes only :mod:`ptcg_rl.g1` public records.  It
does not import the submission module, engine API objects, or card
text.  The route-specific effects whose Phase A status is still ``PARTIAL``
are retained only as a labelled reproduction of the frozen control; callers
must not treat those decisions as newly qualified card authority.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from ptcg_rl.g1.actions import CompoundActionBuilder
from ptcg_rl.g1.models import (
    ContractViolation,
    EngineObservationV1,
    LegalOptionV1,
    SelectionRequestV1,
    CompoundActionV1,
    stable_hash,
)
from ptcg_rl.g1.semantic import AREA, OPTION_NAMES, SELECT_OPTION_TYPES
from ptcg_rl.deterministic.state import PublicStateError, PublicStateV1

from .deck_profile import MEGA_ABOMASNOW_ORDERED_CARD_IDS


# Exact numeric IDs from the version-bound Phase A profile.  These constants
# are numeric on purpose: importing card names or submission card objects here
# would make the public-information boundary ambiguous.
KYOGRE = 721
SNOVER = 722
MEGA_ABOMASNOW_EX = 723
ULTRA_BALL = 1121
PRECIOUS_TROLLEY = 1126
CARMINE = 1192
LILLIES_DETERMINATION = 1227
SURFING_BEACH = 1262
BASIC_WATER_ENERGY = 3

RIPTIDE = 1042
SWIRLING_WAVES = 1043
HAMMER_LANCHE = 1046
FROST_BARRIER = 1047

FROZEN_CONTROL_REPRODUCTION = "FROZEN_CONTROL_REPRODUCTION"
PUBLIC_SEMANTIC_CONTROL = "PUBLIC_SEMANTIC_CONTROL"

# The Phase A report does not close these route-specific interactions.  The
# IDs are used only to label a faithful control reproduction in diagnostics.
_PARTIAL_ROUTE_CARD_IDS = frozenset({SURFING_BEACH})
_PARTIAL_ROUTE_ATTACK_IDS = frozenset({RIPTIDE, SWIRLING_WAVES, HAMMER_LANCHE, FROST_BARRIER})

_CARD_SELECTION_CONTEXTS = frozenset({
    1, 3, 4, 5, 7, 8, 26, 27, 28, 29, 30, 31, 32, 33,
})
_ACTIVE_SELECTION_CONTEXTS = frozenset({1, 3, 4})
# Official version-bound SelectContext values: TO_BENCH=5, TO_HAND=7, and
# DISCARD=8.  Keep this numeric translation local so the candidate never
# imports the submission API at runtime.
_BENCH_OR_HAND_CONTEXTS = frozenset({5, 7})
_DISCARD_SELECTION_CONTEXTS = frozenset({8})

_REQUIRED_OPTION_FIELDS = {
    0: ("number",),
    1: (),
    2: (),
    3: ("area", "index", "player_index"),
    4: ("area", "index", "player_index", "tool_index"),
    5: ("area", "index", "player_index", "energy_index"),
    6: ("area", "index", "player_index", "energy_index", "count"),
    7: ("index",),
    8: ("area", "index", "in_play_area", "in_play_index"),
    9: ("area", "index", "in_play_area", "in_play_index"),
    10: ("area", "index"),
    11: ("area", "index"),
    12: (),
    13: ("attack_id",),
    14: (),
    15: ("card_id", "serial"),
    16: ("special_condition_type",),
}
_OPTION_FIELD_NAMES = frozenset({
    "number", "area", "index", "player_index", "tool_index", "energy_index", "count",
    "in_play_area", "in_play_index", "attack_id", "card_id", "serial",
    "special_condition_type",
})


@dataclass(frozen=True)
class ControlDecisionV1:
    """Auditable score output for one legal option."""

    score: int
    semantic_key: tuple[object, ...]
    authority: str
    route_label: str | None = None


@dataclass(frozen=True)
class ControlDiagnosticsV1:
    """Lifecycle and boundary counters retained by the policy instance."""

    reset_count: int
    choice_count: int
    duplicate_request_count: int
    rejected_request_count: int
    partial_route_decision_count: int
    last_reset_reason: str | None
    last_episode_uuid: str | None
    last_player_index: int | None
    last_selection_seq: int | None
    last_request_id: str | None


@dataclass
class _MutableDiagnostics:
    reset_count: int = 0
    choice_count: int = 0
    duplicate_request_count: int = 0
    rejected_request_count: int = 0
    partial_route_decision_count: int = 0
    last_reset_reason: str | None = None
    last_episode_uuid: str | None = None
    last_player_index: int | None = None
    last_selection_seq: int | None = None
    last_request_id: str | None = None

    def frozen(self) -> ControlDiagnosticsV1:
        return ControlDiagnosticsV1(**self.__dict__)


def _entity_map(observation: EngineObservationV1) -> dict[str, object]:
    return {entity.entity_key: entity for entity in observation.entities}


def _card_id(entity: object | None) -> int | None:
    return getattr(entity, "card_id", None) if entity is not None else None


def _energy_count(entity: object | None) -> int:
    value = getattr(entity, "attached_energy_count", 0) if entity is not None else 0
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _semantic_key(option: LegalOptionV1) -> tuple[object, ...]:
    """Return a total order based on option meaning, not list position.

    The canonical semantic fingerprint is the only tie key.  Transport indexes
    and input order are not public semantics and must not influence a choice.
    Exact duplicate fingerprints are rejected at the boundary because no
    public-only policy can select between them deterministically.
    """
    return (option.semantic_fingerprint,)


def _own_entities(observation: EngineObservationV1) -> tuple[object, ...]:
    actor = observation.acting_player
    if actor not in (0, 1):
        return ()
    return tuple(entity for entity in observation.entities if entity.owner == actor)


def _count_cards(observation: EngineObservationV1, *, zone: int) -> Counter[int]:
    return Counter(
        entity.card_id
        for entity in _own_entities(observation)
        if entity.zone == zone and isinstance(entity.card_id, int)
    )


def _board_entities(observation: EngineObservationV1, *, zone: int) -> tuple[object, ...]:
    actor = observation.acting_player
    return tuple(
        entity
        for entity in observation.entities
        if entity.owner == actor and entity.zone == zone and entity.card_id is not None
    )


def _active_entity(observation: EngineObservationV1, player: int) -> object | None:
    for entity in observation.entities:
        if entity.owner == player and entity.zone == AREA["ACTIVE"] and entity.position == 0:
            return entity
    return None


def _validate_public_boundary(
    observation: EngineObservationV1, request: SelectionRequestV1
) -> None:
    """Reject stale/non-public/malformed inputs before any strategic scoring."""

    if observation.terminal_result is not None:
        raise ContractViolation("control policy must not read a terminal selection")
    try:
        # Reuse the versioned Phase A public-state validator rather than
        # maintaining a weaker, policy-local copy of entity/option rules.
        PublicStateV1.from_engine(observation, request)
    except PublicStateError as error:
        raise ContractViolation(f"invalid public control snapshot: {error}") from error
    if observation.battle_id != request.episode_uuid:
        raise ContractViolation("observation and request episode identities differ")
    if observation.acting_player != request.acting_player:
        raise ContractViolation("observation and request acting players differ")
    if observation.transition_id != request.selection_seq:
        raise ContractViolation("observation and request transition identities differ")
    if request.selection_type not in SELECT_OPTION_TYPES:
        raise ContractViolation("unknown selection type at control boundary")
    if request.selection_context not in range(49):
        raise ContractViolation("unknown selection context at control boundary")
    if request.ordering not in {"ORDERED", "UNORDERED"}:
        raise ContractViolation("unknown request ordering at control boundary")
    if any(option.selection_type != request.selection_type for option in request.options):
        raise ContractViolation("option selection type differs from request")
    if any(option.selection_context != request.selection_context for option in request.options):
        raise ContractViolation("option selection context differs from request")
    if any(not isinstance(option.available, bool) for option in request.options):
        raise ContractViolation("option availability is not boolean")
    if any(option.option_type not in SELECT_OPTION_TYPES[request.selection_type] for option in request.options):
        raise ContractViolation("option type is incompatible with request")
    if any(option.option_name != OPTION_NAMES[option.option_type] for option in request.options):
        raise ContractViolation("option name is inconsistent with option type")
    if any(option.semantic_fingerprint != _semantic_fingerprint(option) for option in request.options):
        raise ContractViolation("option semantic fingerprint is not canonical")
    fingerprints = [option.semantic_fingerprint for option in request.options]
    if len(fingerprints) != len(set(fingerprints)):
        raise ContractViolation("ambiguous duplicate semantic option fingerprint")
    source_entity_types = frozenset({3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13})
    target_entity_types = frozenset({4, 5, 6, 8, 9})
    for option in request.options:
        required_fields = set(_REQUIRED_OPTION_FIELDS[option.option_type])
        if any(getattr(option, field) is None for field in required_fields):
            raise ContractViolation("legal option is missing a required semantic field")
        if any(
            getattr(option, field) is not None
            for field in _OPTION_FIELD_NAMES - required_fields
        ):
            raise ContractViolation("legal option carries an unexpected semantic field")
        if option.option_type in source_entity_types and option.source_kind != "ENTITY":
            raise ContractViolation("card action source must resolve to a public entity")
        if option.option_type == 15 and option.source_kind not in {"ENTITY", "PSEUDO"}:
            raise ContractViolation("skill source must be a public entity or canonical pseudo")
        if option.option_type not in source_entity_types and option.option_type != 15 and option.source_kind != "NONE":
            raise ContractViolation("non-card option carries an unexpected source")
        if option.option_type in target_entity_types and option.target_kind != "ENTITY":
            raise ContractViolation("targeted card action lacks a public entity target")
        if option.option_type not in target_entity_types and option.target_kind != "NONE":
            raise ContractViolation("option carries an unexpected target")


def _semantic_fingerprint(option: LegalOptionV1) -> str:
    # Keep this exactly aligned with the G1 canonical payload operation.
    return stable_hash(option.semantic_payload())


class MegaAbomasnowControl:
    """Deterministic score controller using only public semantic records."""

    policy_id = "mega-abomasnow-public-control-v1"
    deck = MEGA_ABOMASNOW_ORDERED_CARD_IDS

    def __init__(self) -> None:
        self._episode_uuid: str | None = None
        self._player_index: int | None = None
        self._last_selection_seq: int | None = None
        self._last_request_id: str | None = None
        self._last_request_digest: str | None = None
        self._last_observation_digest: str | None = None
        self._last_action: CompoundActionV1 | None = None
        self._diagnostics = _MutableDiagnostics()

    @property
    def diagnostics(self) -> ControlDiagnosticsV1:
        return self._diagnostics.frozen()

    def reset(self, episode_uuid: str, player_index: int, reason: str = "start") -> None:
        if not isinstance(episode_uuid, str) or not episode_uuid:
            raise ContractViolation("control reset episode identity must be nonempty")
        if isinstance(player_index, bool) or player_index not in (0, 1):
            raise ContractViolation("control reset player index must be 0 or 1")
        if reason not in {"start", "terminal", "error", "worker_replacement"}:
            raise ContractViolation("unknown control reset reason")
        self._episode_uuid = episode_uuid
        self._player_index = player_index
        self._last_selection_seq = None
        self._last_request_id = None
        self._last_request_digest = None
        self._last_observation_digest = None
        self._last_action = None
        self._diagnostics.reset_count += 1
        self._diagnostics.last_reset_reason = reason
        self._diagnostics.last_episode_uuid = episode_uuid
        self._diagnostics.last_player_index = player_index
        self._diagnostics.last_selection_seq = None
        self._diagnostics.last_request_id = None

    def _reject(self, message: str) -> None:
        self._diagnostics.rejected_request_count += 1
        raise ContractViolation(message)

    def choose(
        self, observation: EngineObservationV1, request: SelectionRequestV1
    ) -> CompoundActionV1:
        try:
            _validate_public_boundary(observation, request)
            if self._episode_uuid != request.episode_uuid or self._player_index != request.acting_player:
                self._reject("control lifecycle is not reset for this episode/player")
            request_digest = stable_hash(request)
            observation_digest = stable_hash(observation)
            if (
                self._last_selection_seq == request.selection_seq
                and self._last_request_id == request.request_id
                and self._last_action is not None
            ):
                if (
                    request_digest != self._last_request_digest
                    or observation_digest != self._last_observation_digest
                ):
                    self._reject("duplicate request identity was reused with changed payload")
                self._diagnostics.duplicate_request_count += 1
                return self._last_action
            if self._last_selection_seq is not None and request.selection_seq <= self._last_selection_seq:
                self._reject("stale or out-of-order control selection sequence")
            if self._last_request_id == request.request_id:
                self._reject("request identity was reused for a different selection")

            decisions = [self.score_option(observation, request, option) for option in request.options]
            ranked = sorted(
                (
                    (decision.score, decision.semantic_key, index, decision)
                    for index, decision in enumerate(decisions)
                    if request.options[index].available
                ),
                key=lambda item: (-item[0], item[1]),
            )
            builder = CompoundActionBuilder(request)
            # A genuinely optional negative-value action is not forced merely
            # because it is legal.  This is the strategic STOP branch; the
            # builder records it as an autoregressive token and validates its
            # mask/log-probability just like an option token.
            if request.min_count == 0 and (not ranked or ranked[0][0] < 0):
                builder.stop()
            for score, _, index, _ in ranked:
                if builder.complete:
                    break
                if builder.can_stop and score < 0:
                    builder.stop()
                    break
                if request.options[index].available:
                    builder.choose(index)
            if not builder.complete:
                # STOP is represented in the G1 trace, including optional
                # and ordered selections.  Never synthesize an empty list.
                builder.stop()
            action = builder.build()
            self._last_selection_seq = request.selection_seq
            self._last_request_id = request.request_id
            self._last_request_digest = request_digest
            self._last_observation_digest = observation_digest
            self._last_action = action
            selected = set(action.submitted_original_indices)
            self._diagnostics.partial_route_decision_count += sum(
                decision.route_label == FROZEN_CONTROL_REPRODUCTION
                and request.options[index].original_index in selected
                for index, decision in enumerate(decisions)
            )
            self._diagnostics.choice_count += 1
            self._diagnostics.last_selection_seq = request.selection_seq
            self._diagnostics.last_request_id = request.request_id
            return action
        except ContractViolation:
            raise
        except Exception as error:
            self._diagnostics.rejected_request_count += 1
            raise ContractViolation(f"control policy rejected public request: {error}") from error

    def score_option(
        self,
        observation: EngineObservationV1,
        request: SelectionRequestV1,
        option: LegalOptionV1,
    ) -> ControlDecisionV1:
        """Score one option without consulting submission/engine objects."""

        entities = _entity_map(observation)
        own = observation.acting_player
        hand = _count_cards(observation, zone=AREA["HAND"])
        discard = _count_cards(observation, zone=AREA["DISCARD"])
        field = Counter(
            entity.card_id
            for entity in (*_board_entities(observation, zone=AREA["ACTIVE"]), *_board_entities(observation, zone=AREA["BENCH"]))
            if isinstance(entity.card_id, int)
        )
        source = entities.get(option.source_entity_key) if option.source_entity_key else None
        target = entities.get(option.target_entity_key) if option.target_entity_key else None
        source_id = _card_id(source) if source is not None else option.card_id
        target_id = _card_id(target)

        bench_ready_aboma = any(
            entity.card_id == MEGA_ABOMASNOW_EX and _energy_count(entity) >= 2
            for entity in _board_entities(observation, zone=AREA["BENCH"])
        )
        bench_ready_kyogre = any(
            entity.card_id == KYOGRE and _energy_count(entity) >= 1
            for entity in _board_entities(observation, zone=AREA["BENCH"])
        )
        opponent_active = _active_entity(observation, 1 - own) if own in (0, 1) else None
        opponent_hp = getattr(opponent_active, "hp", 0) or 0
        prefer_kyogre = opponent_hp <= 20 * discard[BASIC_WATER_ENERGY]
        active = _active_entity(observation, own) if own in (0, 1) else None
        switch_target: object | None = None
        ready_abomasnow = tuple(sorted(
            (
                entity
                for entity in _board_entities(observation, zone=AREA["BENCH"])
                if entity.card_id == MEGA_ABOMASNOW_EX and _energy_count(entity) >= 2
            ),
            key=lambda entity: entity.entity_key,
        ))
        ready_kyogre = tuple(sorted(
            (
                entity
                for entity in _board_entities(observation, zone=AREA["BENCH"])
                if entity.card_id == KYOGRE and _energy_count(entity) >= 1
            ),
            key=lambda entity: entity.entity_key,
        ))
        if active is not None:
            if _card_id(active) == MEGA_ABOMASNOW_EX and prefer_kyogre and ready_kyogre:
                switch_target = ready_kyogre[0]
            elif _card_id(active) == KYOGRE and not prefer_kyogre and ready_abomasnow:
                switch_target = ready_abomasnow[0]
            elif ready_abomasnow:
                switch_target = ready_abomasnow[0]

        score = 0
        route_label: str | None = None
        if option.option_type == 0:  # NUMBER
            score = option.number or 0
        elif option.option_type == 1:  # YES
            score = 1
        elif option.option_type == 2:  # NO
            score = 0
        elif option.option_type == 3:  # CARD
            energy_count = _energy_count(source)
            if request.selection_context in _ACTIVE_SELECTION_CONTEXTS:
                score = energy_count * 2
                if source is switch_target:
                    score += 100
                if source_id == MEGA_ABOMASNOW_EX:
                    score += 20
                elif source_id == KYOGRE:
                    score += 10
            elif request.selection_context in _BENCH_OR_HAND_CONTEXTS:
                if source_id == SNOVER:
                    score += 5 if field[SNOVER] >= 1 else (15 if field[MEGA_ABOMASNOW_EX] >= 1 else 30)
                elif source_id == MEGA_ABOMASNOW_EX:
                    score += 100 if field[SNOVER] >= 1 and field[MEGA_ABOMASNOW_EX] + hand[MEGA_ABOMASNOW_EX] == 0 else 10
                elif source_id == KYOGRE:
                    score += 1 if field[KYOGRE] >= 1 else 20
            elif request.selection_context in _CARD_SELECTION_CONTEXTS:
                if (
                    request.selection_context in _DISCARD_SELECTION_CONTEXTS
                    and getattr(source, "zone", None) == AREA["HAND"]
                ):
                    if source_id == BASIC_WATER_ENERGY:
                        score += 100
                    elif source_id == MEGA_ABOMASNOW_EX:
                        score += 10
                    elif source_id == CARMINE and hand[LILLIES_DETERMINATION] >= 1:
                        score += 30
                    elif source_id == LILLIES_DETERMINATION:
                        score -= 20
                    if source_id is not None and hand[source_id] >= 2:
                        score += 500
        elif option.option_type == 7:  # PLAY
            score = 10_000
            if source_id == ULTRA_BALL:
                missing_core = (
                    field[MEGA_ABOMASNOW_EX] + hand[MEGA_ABOMASNOW_EX] == 0
                    or field[MEGA_ABOMASNOW_EX] + field[SNOVER] == 0
                    or field[KYOGRE] == 0
                )
                hand_size = next(
                    (player.hand_count for player in observation.players if player.player_index == own),
                    0,
                )
                score = 4_000 if hand[BASIC_WATER_ENERGY] >= 3 or (hand_size >= 4 and missing_core) else -1
            elif source_id == CARMINE:
                score = -1 if field[SNOVER] >= 1 and hand[MEGA_ABOMASNOW_EX] >= 1 else 3_000
            elif source_id == LILLIES_DETERMINATION:
                score = -1 if field[SNOVER] >= 1 and field[MEGA_ABOMASNOW_EX] == 0 and hand[MEGA_ABOMASNOW_EX] >= 1 else 3_100
        elif option.option_type == 8:  # ATTACH
            pokemon = target
            score = 5_000
            energy_count = _energy_count(pokemon)
            if energy_count == 0 and getattr(pokemon, "zone", None) == AREA["BENCH"]:
                score += 1
            if target_id == SNOVER:
                score += 1
                if energy_count == 1:
                    score -= 100
                elif energy_count >= 2:
                    score -= 400
                if bench_ready_aboma:
                    score -= 300
            elif target_id == MEGA_ABOMASNOW_EX:
                score += 10
                if energy_count == 1:
                    score += 30
                elif energy_count >= 2:
                    score -= 300
                if bench_ready_aboma:
                    score -= 200
            elif target_id == KYOGRE:
                score += 5
                if energy_count >= 1:
                    score -= 200
                if bench_ready_kyogre:
                    score -= 200
            if getattr(pokemon, "zone", None) == AREA["ACTIVE"] and bench_ready_aboma and bench_ready_kyogre and energy_count <= 2:
                score += 200
        elif option.option_type == 9:  # EVOLVE
            score = 10_000 + _energy_count(target)
        elif option.option_type == 10:  # ABILITY
            if source_id == SURFING_BEACH and switch_target is not None:
                score = 2_000
                route_label = FROZEN_CONTROL_REPRODUCTION
            else:
                score = -1
        elif option.option_type == 12:  # RETREAT
            score = 1_500 if switch_target is not None else -1
        elif option.option_type == 13:  # ATTACK
            score = 1_000
            if option.attack_id == RIPTIDE:
                score += discard[BASIC_WATER_ENERGY] * 20 - 90
                route_label = FROZEN_CONTROL_REPRODUCTION
            elif option.attack_id == HAMMER_LANCHE:
                score += -100 if opponent_hp <= 200 else 100
                route_label = FROZEN_CONTROL_REPRODUCTION
            elif option.attack_id in _PARTIAL_ROUTE_ATTACK_IDS:
                route_label = FROZEN_CONTROL_REPRODUCTION
        elif option.option_type == 14:  # END
            score = -10_000
        elif option.option_type == 15:  # SKILL
            score = 0
        elif option.option_type in {4, 5, 6, 11, 16}:
            score = 0
        else:
            raise ContractViolation(f"control cannot score option type {option.option_type}")

        if source_id in _PARTIAL_ROUTE_CARD_IDS and route_label is None:
            route_label = FROZEN_CONTROL_REPRODUCTION
        return ControlDecisionV1(score, _semantic_key(option), PUBLIC_SEMANTIC_CONTROL, route_label)


__all__ = [
    "BASIC_WATER_ENERGY",
    "CARMINE",
    "ControlDecisionV1",
    "ControlDiagnosticsV1",
    "FROZEN_CONTROL_REPRODUCTION",
    "FROST_BARRIER",
    "HAMMER_LANCHE",
    "KYOGRE",
    "LILLIES_DETERMINATION",
    "MEGA_ABOMASNOW_EX",
    "MegaAbomasnowControl",
    "PRECIOUS_TROLLEY",
    "PUBLIC_SEMANTIC_CONTROL",
    "RIPTIDE",
    "SNOVER",
    "SURFING_BEACH",
    "SWIRLING_WAVES",
    "ULTRA_BALL",
]
