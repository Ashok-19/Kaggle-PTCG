from __future__ import annotations

from typing import Any, Iterable, Sequence

from ptcg_rl.g1.models import ContractViolation, EngineObservationV1, SelectionRequestV1
from ptcg_rl.g1.semantic import AREA, CHOICE_ROLE_CODE, SOURCE_KIND_CODE

from .models import (
    ENTITY_CATEGORICAL_NAMES,
    ENTITY_NUMERIC_NAMES,
    EVENT_CATEGORICAL_NAMES,
    EVENT_IDENTITY_NAMES,
    EVENT_NUMERIC_NAMES,
    GLOBAL_CATEGORICAL_NAMES,
    GLOBAL_NUMERIC_NAMES,
    MODEL_SCHEMA_VERSION,
    OPTION_CATEGORICAL_NAMES,
    OPTION_NUMERIC_NAMES,
    PLAYER_CATEGORICAL_NAMES,
    PLAYER_NUMERIC_NAMES,
    ModelInputV1,
    OptionTransportMapV1,
    ProjectedDecisionV1,
)

_EVENT_CARD_FIELDS = (
    "cardId",
    "cardIdActive",
    "cardIdBench",
    "cardIdBefore",
    "cardIdAfter",
    "cardIdTarget",
)
_EVENT_SERIAL_FIELDS = (
    "serial",
    "serialActive",
    "serialBench",
    "serialBefore",
    "serialAfter",
    "serialTarget",
)


def _relative_player(player: int | None, acting_player: int) -> int | None:
    if player is None:
        return None
    if player not in (0, 1):
        raise ContractViolation("player reference must be 0 or 1")
    return 0 if player == acting_player else 1


def _categorical_row(values: Iterable[int | bool | None]) -> tuple[tuple[int, ...], tuple[bool, ...]]:
    raw = tuple(values)
    return (
        tuple(0 if value is None else int(value) for value in raw),
        tuple(value is None for value in raw),
    )


def _numeric_row(values: Iterable[int | float | bool | None]) -> tuple[tuple[float, ...], tuple[bool, ...]]:
    raw = tuple(values)
    return (
        tuple(0.0 if value is None else float(value) for value in raw),
        tuple(value is None for value in raw),
    )


def _role_position(zone: int, position: int | None) -> int:
    if position is None:
        return 0
    if zone in {AREA["ACTIVE"], AREA["BENCH"]}:
        return position + 1
    return 0


def _entity_sort_key(entity: Any, acting_player: int, original_position: int) -> tuple[Any, ...]:
    return (
        _relative_player(entity.owner, acting_player),
        entity.zone,
        _role_position(entity.zone, entity.position),
        0 if entity.card_id is None else entity.card_id,
        int(not entity.visible),
        0 if entity.parent_entity_key is None else 1,
        original_position,
    )


def _project_players(
    observation: EngineObservationV1, acting_player: int
) -> tuple[
    tuple[tuple[int, ...], ...],
    tuple[tuple[bool, ...], ...],
    tuple[tuple[float, ...], ...],
    tuple[tuple[bool, ...], ...],
]:
    categorical_rows = []
    numeric_rows = []
    ordered = sorted(
        observation.players,
        key=lambda player: _relative_player(player.player_index, acting_player),
    )
    for player in ordered:
        categorical_rows.append(
            _categorical_row(
                (
                    _relative_player(player.player_index, acting_player),
                    player.hand_visible,
                )
            )
        )
        numeric_rows.append(
            _numeric_row(
                (
                    player.bench_max,
                    player.deck_count,
                    player.hand_count,
                    player.prize_count,
                    player.visible_prize_count,
                    player.facedown_active_count,
                )
            )
        )
    return (
        tuple(row for row, _ in categorical_rows),
        tuple(mask for _, mask in categorical_rows),
        tuple(row for row, _ in numeric_rows),
        tuple(mask for _, mask in numeric_rows),
    )


def _project_entities(
    observation: EngineObservationV1, acting_player: int
) -> tuple[
    tuple[Any, ...],
    dict[str, int],
    dict[int, int],
    tuple[tuple[int, ...], ...],
    tuple[tuple[bool, ...], ...],
    tuple[tuple[float, ...], ...],
    tuple[tuple[bool, ...], ...],
    tuple[int, ...],
    tuple[int, ...],
    tuple[int, ...],
]:
    indexed = list(enumerate(observation.entities))
    indexed.sort(key=lambda item: _entity_sort_key(item[1], acting_player, item[0]))
    entities = tuple(entity for _, entity in indexed)
    entity_index = {entity.entity_key: index for index, entity in enumerate(entities)}
    serial_to_entity: dict[int, int] = {}
    categorical_rows = []
    numeric_rows = []
    parent_indices = []
    energy_values: list[int] = []
    energy_offsets = [0]
    for index, entity in enumerate(entities):
        if entity.serial is not None:
            if entity.serial in serial_to_entity:
                raise ContractViolation("visible serial resolves to more than one model entity")
            serial_to_entity[entity.serial] = index
        categorical_rows.append(
            _categorical_row(
                (
                    entity.card_id,
                    _relative_player(entity.owner, acting_player),
                    entity.zone,
                    _role_position(entity.zone, entity.position),
                )
            )
        )
        numeric_rows.append(
            _numeric_row(
                (
                    entity.hp,
                    entity.max_hp,
                    entity.damage,
                    entity.appear_this_turn,
                    entity.attached_energy_count,
                    entity.attached_tool_count,
                    entity.evolution_depth,
                    entity.visible,
                    *(condition in entity.statuses for condition in range(5)),
                )
            )
        )
        parent_indices.append(entity_index.get(entity.parent_entity_key, -1))
        energy_values.extend(entity.energy_types)
        energy_offsets.append(len(energy_values))
    return (
        entities,
        entity_index,
        serial_to_entity,
        tuple(row for row, _ in categorical_rows),
        tuple(mask for _, mask in categorical_rows),
        tuple(row for row, _ in numeric_rows),
        tuple(mask for _, mask in numeric_rows),
        tuple(parent_indices),
        tuple(energy_values),
        tuple(energy_offsets),
    )


def _project_events(
    observation: EngineObservationV1,
    acting_player: int,
    serial_to_entity: dict[int, int],
) -> tuple[
    tuple[tuple[int, ...], ...],
    tuple[tuple[bool, ...], ...],
    tuple[tuple[float, ...], ...],
    tuple[tuple[bool, ...], ...],
    tuple[tuple[int, ...], ...],
    tuple[tuple[bool, ...], ...],
    tuple[tuple[int, ...], ...],
]:
    categorical_rows = []
    numeric_rows = []
    identity_rows = []
    identity_masks = []
    entity_rows = []
    identity_tokens = {serial: entity_index + 1 for serial, entity_index in serial_to_entity.items()}
    next_identity = len(identity_tokens) + 1

    def identity(serial: int | bool | None) -> tuple[int, bool, int]:
        nonlocal next_identity
        if serial is None:
            return 0, True, -1
        if isinstance(serial, bool) or not isinstance(serial, int) or serial <= 0:
            raise ContractViolation("public event serial must be a positive integer")
        if serial not in identity_tokens:
            identity_tokens[serial] = next_identity
            next_identity += 1
        return identity_tokens[serial], False, serial_to_entity.get(serial, -1)

    for event in observation.public_events:
        fields = event.fields
        categorical_rows.append(
            _categorical_row(
                (
                    event.event_type,
                    _relative_player(fields.get("playerIndex"), acting_player),
                    fields.get("hasBasicPokemon"),
                    fields.get(_EVENT_CARD_FIELDS[0]),
                    fields.get("fromArea"),
                    fields.get("toArea"),
                    fields.get(_EVENT_CARD_FIELDS[1]),
                    fields.get(_EVENT_CARD_FIELDS[2]),
                    fields.get(_EVENT_CARD_FIELDS[3]),
                    fields.get(_EVENT_CARD_FIELDS[4]),
                    fields.get(_EVENT_CARD_FIELDS[5]),
                    fields.get("attackId"),
                    fields.get("putDamageCounter"),
                    fields.get("isRecover"),
                    fields.get("head"),
                    fields.get("result"),
                    fields.get("reason"),
                )
            )
        )
        numeric_rows.append(_numeric_row((fields.get("value"),)))
        identities = [identity(fields.get(name)) for name in _EVENT_SERIAL_FIELDS]
        identity_rows.append(tuple(value for value, _, _ in identities))
        identity_masks.append(tuple(missing for _, missing, _ in identities))
        entity_rows.append(tuple(entity_index for _, _, entity_index in identities))
    return (
        tuple(row for row, _ in categorical_rows),
        tuple(mask for _, mask in categorical_rows),
        tuple(row for row, _ in numeric_rows),
        tuple(mask for _, mask in numeric_rows),
        tuple(identity_rows),
        tuple(identity_masks),
        tuple(entity_rows),
    )


def _project_options(
    request: SelectionRequestV1,
    acting_player: int,
    entity_index: dict[str, int],
) -> tuple[
    tuple[tuple[int, ...], ...],
    tuple[tuple[bool, ...], ...],
    tuple[tuple[float, ...], ...],
    tuple[tuple[bool, ...], ...],
    tuple[int, ...],
    tuple[int, ...],
    tuple[bool, ...],
]:
    categorical_rows = []
    numeric_rows = []
    source_indices = []
    target_indices = []
    for option in request.options:
        categorical_rows.append(
            _categorical_row(
                (
                    option.selection_type,
                    option.selection_context,
                    option.option_type,
                    SOURCE_KIND_CODE[option.source_kind],
                    SOURCE_KIND_CODE[option.target_kind],
                    CHOICE_ROLE_CODE[option.choice_role],
                    option.area,
                    option.in_play_area,
                    _relative_player(option.player_index, acting_player),
                    option.attack_id,
                    option.card_id,
                    option.special_condition_type,
                )
            )
        )
        numeric_rows.append(_numeric_row((option.number, option.count)))
        source_indices.append(entity_index.get(option.source_entity_key, -1))
        target_indices.append(entity_index.get(option.target_entity_key, -1))
    return (
        tuple(row for row, _ in categorical_rows),
        tuple(mask for _, mask in categorical_rows),
        tuple(row for row, _ in numeric_rows),
        tuple(mask for _, mask in numeric_rows),
        tuple(source_indices),
        tuple(target_indices),
        tuple(option.available for option in request.options),
    )


def _player_by_relative(
    observation: EngineObservationV1, acting_player: int, relative: int
) -> Any:
    absolute = acting_player if relative == 0 else 1 - acting_player
    return next(player for player in observation.players if player.player_index == absolute)


def project_decision(
    observation: EngineObservationV1,
    request: SelectionRequestV1,
) -> ProjectedDecisionV1:
    if observation.acting_player is None:
        raise ContractViolation("model projection requires a nonterminal acting player")
    acting_player = observation.acting_player
    if request.acting_player != acting_player:
        raise ContractViolation("observation and request acting players differ")
    if request.schema_version != observation.schema_version:
        raise ContractViolation("observation and request schema versions differ")

    player_cat, player_cat_mask, player_num, player_num_mask = _project_players(
        observation, acting_player
    )
    (
        _entities,
        entity_index,
        serial_to_entity,
        entity_cat,
        entity_cat_mask,
        entity_num,
        entity_num_mask,
        parent_indices,
        energy_values,
        energy_offsets,
    ) = _project_entities(observation, acting_player)
    (
        event_cat,
        event_cat_mask,
        event_num,
        event_num_mask,
        event_identity,
        event_identity_mask,
        event_entity_indices,
    ) = _project_events(observation, acting_player, serial_to_entity)
    (
        option_cat,
        option_cat_mask,
        option_num,
        option_num_mask,
        source_indices,
        target_indices,
        option_available,
    ) = _project_options(request, acting_player, entity_index)

    self_player = _player_by_relative(observation, acting_player, 0)
    opponent = _player_by_relative(observation, acting_player, 1)
    global_cat, global_cat_mask = _categorical_row(
        (
            _relative_player(observation.first_player, acting_player),
            observation.terminal_result,
            request.selection_type,
            request.selection_context,
            request.ordering == "ORDERED",
            request.context_card_id,
            request.effect_card_id,
            observation.supporter_played,
            observation.stadium_played,
            observation.energy_attached,
            observation.retreated,
        )
    )
    global_num, global_num_mask = _numeric_row(
        (
            observation.turn,
            observation.turn_action_count,
            request.min_count,
            request.max_count,
            request.remain_damage_counter,
            request.remain_energy_cost,
            self_player.deck_count,
            self_player.hand_count,
            self_player.prize_count,
            opponent.deck_count,
            opponent.hand_count,
            opponent.prize_count,
        )
    )

    model = ModelInputV1(
        schema_version=MODEL_SCHEMA_VERSION,
        player_categorical_names=PLAYER_CATEGORICAL_NAMES,
        player_categorical_values=player_cat,
        player_categorical_missing=player_cat_mask,
        player_numeric_names=PLAYER_NUMERIC_NAMES,
        player_numeric_values=player_num,
        player_numeric_missing=player_num_mask,
        entity_categorical_names=ENTITY_CATEGORICAL_NAMES,
        entity_categorical_values=entity_cat,
        entity_categorical_missing=entity_cat_mask,
        entity_numeric_names=ENTITY_NUMERIC_NAMES,
        entity_numeric_values=entity_num,
        entity_numeric_missing=entity_num_mask,
        entity_parent_indices=parent_indices,
        entity_energy_values=energy_values,
        entity_energy_offsets=energy_offsets,
        event_categorical_names=EVENT_CATEGORICAL_NAMES,
        event_categorical_values=event_cat,
        event_categorical_missing=event_cat_mask,
        event_numeric_names=EVENT_NUMERIC_NAMES,
        event_numeric_values=event_num,
        event_numeric_missing=event_num_mask,
        event_identity_names=EVENT_IDENTITY_NAMES,
        event_identity_values=event_identity,
        event_identity_missing=event_identity_mask,
        event_entity_indices=event_entity_indices,
        option_categorical_names=OPTION_CATEGORICAL_NAMES,
        option_categorical_values=option_cat,
        option_categorical_missing=option_cat_mask,
        option_numeric_names=OPTION_NUMERIC_NAMES,
        option_numeric_values=option_num,
        option_numeric_missing=option_num_mask,
        option_source_entity_indices=source_indices,
        option_target_entity_indices=target_indices,
        option_available_mask=option_available,
        global_categorical_names=GLOBAL_CATEGORICAL_NAMES,
        global_categorical_values=global_cat,
        global_categorical_missing=global_cat_mask,
        global_numeric_names=GLOBAL_NUMERIC_NAMES,
        global_numeric_values=global_num,
        global_numeric_missing=global_num_mask,
    )
    transport = OptionTransportMapV1(
        schema_version=MODEL_SCHEMA_VERSION,
        request_id=request.request_id,
        original_indices=tuple(option.original_index for option in request.options),
        semantic_fingerprints=tuple(option.semantic_fingerprint for option in request.options),
    )
    return ProjectedDecisionV1(MODEL_SCHEMA_VERSION, model, transport)


def reorder_option_features(
    model: ModelInputV1, permutation: Sequence[int]
) -> ModelInputV1:
    if sorted(permutation) != list(range(len(model.option_available_mask))):
        raise ContractViolation("option permutation must cover the complete model option set")

    def reorder(rows: Sequence[Any]) -> tuple[Any, ...]:
        return tuple(rows[index] for index in permutation)

    values = model.__dict__.copy()
    for field in (
        "option_categorical_values",
        "option_categorical_missing",
        "option_numeric_values",
        "option_numeric_missing",
        "option_source_entity_indices",
        "option_target_entity_indices",
        "option_available_mask",
    ):
        values[field] = reorder(values[field])
    return ModelInputV1(**values)
