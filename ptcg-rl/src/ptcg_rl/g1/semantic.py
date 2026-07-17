from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping, Sequence

from .models import (
    CONTRACT_VERSION,
    ContractViolation,
    ENTITY_FEATURE_NAMES,
    EngineObservationV1,
    EVENT_FEATURE_NAMES,
    GLOBAL_FEATURE_NAMES,
    LegalOptionV1,
    NumericTensorV1,
    OPTION_FEATURE_NAMES,
    PlayerViewV1,
    PublicEventV1,
    SelectionRequestV1,
    VisibleEntityV1,
    stable_hash,
)


AREA = {
    "DECK": 1,
    "HAND": 2,
    "DISCARD": 3,
    "ACTIVE": 4,
    "BENCH": 5,
    "PRIZE": 6,
    "STADIUM": 7,
    "ENERGY": 8,
    "TOOL": 9,
    "PRE_EVOLUTION": 10,
    "LOOKING": 12,
}

OPTION_NAMES = {
    0: "NUMBER",
    1: "YES",
    2: "NO",
    3: "CARD",
    4: "TOOL_CARD",
    5: "ENERGY_CARD",
    6: "ENERGY",
    7: "PLAY",
    8: "ATTACH",
    9: "EVOLVE",
    10: "ABILITY",
    11: "DISCARD",
    12: "RETREAT",
    13: "ATTACK",
    14: "END",
    15: "SKILL",
    16: "SPECIAL_CONDITION",
}

SELECT_NAMES = {
    0: "MAIN",
    1: "CARD",
    2: "ATTACHED_CARD",
    3: "CARD_OR_ATTACHED_CARD",
    4: "ENERGY",
    5: "SKILL",
    6: "ATTACK",
    7: "EVOLVE",
    8: "COUNT",
    9: "YES_NO",
    10: "SPECIAL_CONDITION",
}

LOG_NAMES = {
    0: "SHUFFLE",
    1: "HAS_BASIC_POKEMON",
    2: "TURN_START",
    3: "TURN_END",
    4: "DRAW",
    5: "DRAW_REVERSE",
    6: "MOVE_CARD",
    7: "MOVE_CARD_REVERSE",
    8: "SWITCH",
    9: "CHANGE",
    10: "PLAY",
    11: "ATTACH",
    12: "EVOLVE",
    13: "DEVOLVE",
    14: "MOVE_ATTACHED",
    15: "ATTACK",
    16: "HP_CHANGE",
    17: "POISONED",
    18: "BURNED",
    19: "ASLEEP",
    20: "PARALYZED",
    21: "CONFUSED",
    22: "COIN",
    23: "RESULT",
}


def _integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractViolation(f"{field} must be an integer")
    return value


def _optional_integer(value: Any, field: str) -> int | None:
    return None if value is None else _integer(value, field)


def _entity_key(owner: int, serial: int) -> str:
    return f"p{owner}:s{serial}"


def _card_entity(
    card: Mapping[str, Any], owner: int, zone: int, position: int, card_data_sha256: str,
    *, parent: str | None = None,
) -> VisibleEntityV1:
    card_id = _integer(card["id"], "card.id")
    serial = _integer(card["serial"], "card.serial")
    return VisibleEntityV1(
        entity_key=_entity_key(owner, serial),
        card_id=card_id,
        metadata_ref=f"card:{card_id}@{card_data_sha256}",
        owner=owner,
        zone=zone,
        position=position,
        parent_entity_key=parent,
    )


def _visible_entities(
    current: Mapping[str, Any], select: Mapping[str, Any] | None, acting_player: int,
    card_data_sha256: str,
) -> tuple[tuple[VisibleEntityV1, ...], dict[tuple[int, int, int], str]]:
    entities: dict[str, VisibleEntityV1] = {}
    positions: dict[tuple[int, int, int], str] = {}

    def add(entity: VisibleEntityV1) -> None:
        entities[entity.entity_key] = entity
        positions[(entity.owner, entity.zone, entity.position or 0)] = entity.entity_key

    for player_index, player in enumerate(current["players"]):
        status_values = tuple(
            index
            for index, field in enumerate(("poisoned", "burned", "asleep", "paralyzed", "confused"))
            if player.get(field) is True
        )
        for zone_name, field in (("ACTIVE", "active"), ("BENCH", "bench")):
            zone = AREA[zone_name]
            for position, pokemon in enumerate(player[field]):
                if pokemon is None:
                    continue
                card_id = _integer(pokemon["id"], "pokemon.id")
                serial = _integer(pokemon["serial"], "pokemon.serial")
                key = _entity_key(player_index, serial)
                hp = _integer(pokemon["hp"], "pokemon.hp")
                max_hp = _integer(pokemon["maxHp"], "pokemon.maxHp")
                entity = VisibleEntityV1(
                    entity_key=key,
                    card_id=card_id,
                    metadata_ref=f"card:{card_id}@{card_data_sha256}",
                    owner=player_index,
                    zone=zone,
                    position=position,
                    hp=hp,
                    max_hp=max_hp,
                    damage=max_hp - hp,
                    appear_this_turn=bool(pokemon["appearThisTurn"]),
                    energy_types=tuple(int(item) for item in pokemon["energies"]),
                    attached_energy_count=len(pokemon["energyCards"]),
                    attached_tool_count=len(pokemon["tools"]),
                    evolution_depth=len(pokemon["preEvolution"]),
                    statuses=status_values if zone == AREA["ACTIVE"] else (),
                )
                add(entity)
                for attachment_zone, attachment_field in (
                    (AREA["ENERGY"], "energyCards"),
                    (AREA["TOOL"], "tools"),
                    (AREA["PRE_EVOLUTION"], "preEvolution"),
                ):
                    for attachment_index, card in enumerate(pokemon[attachment_field]):
                        child = _card_entity(
                            card,
                            player_index,
                            attachment_zone,
                            attachment_index,
                            card_data_sha256,
                            parent=key,
                        )
                        entities[child.entity_key] = child
                        positions[(player_index, attachment_zone, attachment_index)] = child.entity_key
        for zone_name, field in (("HAND", "hand"), ("DISCARD", "discard"), ("PRIZE", "prize")):
            cards = player[field]
            if cards is None:
                continue
            for position, card in enumerate(cards):
                if card is not None:
                    add(_card_entity(card, player_index, AREA[zone_name], position, card_data_sha256))

    for position, card in enumerate(current.get("stadium", [])):
        if card is not None:
            add(_card_entity(card, int(card["playerIndex"]), AREA["STADIUM"], position, card_data_sha256))
    for position, card in enumerate(current.get("looking") or []):
        if card is not None:
            add(_card_entity(card, acting_player, AREA["LOOKING"], position, card_data_sha256))
    for position, card in enumerate((select or {}).get("deck") or []):
        if card is not None:
            add(_card_entity(card, acting_player, AREA["DECK"], position, card_data_sha256))
    return tuple(entities.values()), positions


def _players(current: Mapping[str, Any]) -> tuple[PlayerViewV1, ...]:
    result = []
    for index, player in enumerate(current["players"]):
        result.append(
            PlayerViewV1(
                player_index=index,
                bench_max=_integer(player["benchMax"], "benchMax"),
                deck_count=_integer(player["deckCount"], "deckCount"),
                hand_count=_integer(player["handCount"], "handCount"),
                prize_count=len(player["prize"]),
                visible_prize_count=sum(card is not None for card in player["prize"]),
                hand_visible=player["hand"] is not None,
                facedown_active_count=sum(card is None for card in player["active"]),
            )
        )
    return tuple(result)


def _events(logs: Sequence[Mapping[str, Any]]) -> tuple[PublicEventV1, ...]:
    events = []
    for log in logs:
        event_type = _integer(log["type"], "log.type")
        payload: dict[str, int | bool | None] = {}
        for key, value in log.items():
            if key == "type" or value is None:
                continue
            if not isinstance(value, (int, bool)):
                raise ContractViolation(f"unsupported public log field {key}")
            payload[key] = value
        events.append(PublicEventV1(event_type, LOG_NAMES.get(event_type), payload))
    return tuple(events)


def _resolve_option_entities(
    option: Mapping[str, Any], option_type: int, acting_player: int,
    positions: Mapping[tuple[int, int, int], str], entities: Sequence[VisibleEntityV1],
) -> tuple[str | None, str | None]:
    source: str | None = None
    target: str | None = None
    owner = int(option.get("playerIndex", acting_player))
    area = option.get("area")
    index = option.get("index")
    if option_type == 3 and area is not None and index is not None:
        source = positions.get((owner, int(area), int(index)))
    elif option_type in (4, 5, 6) and area is not None and index is not None:
        parent = positions.get((owner, int(area), int(index)))
        attachment_zone = AREA["TOOL"] if option_type == 4 else AREA["ENERGY"]
        attachment_index = option.get("toolIndex") if option_type == 4 else option.get("energyIndex")
        if parent is not None and attachment_index is not None:
            source = next(
                (
                    entity.entity_key
                    for entity in entities
                    if entity.parent_entity_key == parent
                    and entity.zone == attachment_zone
                    and entity.position == int(attachment_index)
                ),
                None,
            )
    elif option_type == 7 and index is not None:
        source = positions.get((acting_player, AREA["HAND"], int(index)))
    elif option_type in (8, 9):
        if area is not None and index is not None:
            source = positions.get((acting_player, int(area), int(index)))
        if option.get("inPlayArea") is not None and option.get("inPlayIndex") is not None:
            target = positions.get(
                (acting_player, int(option["inPlayArea"]), int(option["inPlayIndex"]))
            )
    elif option_type in (10, 11) and area is not None and index is not None:
        source = positions.get((acting_player, int(area), int(index)))
    elif option_type == 13:
        source = positions.get((acting_player, AREA["ACTIVE"], 0))
    elif option_type == 15 and option.get("serial") is not None:
        serial = int(option["serial"])
        source = next((entity.entity_key for entity in entities if entity.entity_key.endswith(f":s{serial}")), None)
    return source, target


def _request(
    select: Mapping[str, Any], battle_id: str, transition_id: int, acting_player: int,
    entities: Sequence[VisibleEntityV1], positions: Mapping[tuple[int, int, int], str],
) -> SelectionRequestV1:
    selection_type = _integer(select["type"], "select.type")
    context = _integer(select["context"], "select.context")
    options = []
    for original_index, raw in enumerate(select["option"]):
        option_type = _integer(raw["type"], "option.type")
        source, target = _resolve_option_entities(raw, option_type, acting_player, positions, entities)
        option = LegalOptionV1(
            schema_version=CONTRACT_VERSION,
            original_index=original_index,
            selection_type=selection_type,
            selection_context=context,
            option_type=option_type,
            option_name=OPTION_NAMES.get(option_type),
            number=_optional_integer(raw.get("number"), "option.number"),
            area=_optional_integer(raw.get("area"), "option.area"),
            index=_optional_integer(raw.get("index"), "option.index"),
            player_index=_optional_integer(raw.get("playerIndex"), "option.playerIndex"),
            tool_index=_optional_integer(raw.get("toolIndex"), "option.toolIndex"),
            energy_index=_optional_integer(raw.get("energyIndex"), "option.energyIndex"),
            count=_optional_integer(raw.get("count"), "option.count"),
            in_play_area=_optional_integer(raw.get("inPlayArea"), "option.inPlayArea"),
            in_play_index=_optional_integer(raw.get("inPlayIndex"), "option.inPlayIndex"),
            attack_id=_optional_integer(raw.get("attackId"), "option.attackId"),
            card_id=_optional_integer(raw.get("cardId"), "option.cardId"),
            serial=_optional_integer(raw.get("serial"), "option.serial"),
            special_condition_type=_optional_integer(
                raw.get("specialConditionType"), "option.specialConditionType"
            ),
            source_entity_key=source,
            target_entity_key=target,
        )
        options.append(replace(option, semantic_fingerprint=stable_hash(option.semantic_payload())))
    request_id = stable_hash(
        {
            "battle_id": battle_id,
            "transition_id": transition_id,
            "selection_type": selection_type,
            "context": context,
            "fingerprints": [option.semantic_fingerprint for option in options],
        }
    )
    return SelectionRequestV1(
        schema_version=CONTRACT_VERSION,
        request_id=request_id,
        acting_player=acting_player,
        selection_type=selection_type,
        selection_context=context,
        min_count=_integer(select["minCount"], "select.minCount"),
        max_count=_integer(select["maxCount"], "select.maxCount"),
        remain_damage_counter=_optional_integer(
            select.get("remainDamageCounter"), "select.remainDamageCounter"
        ),
        remain_energy_cost=_optional_integer(select.get("remainEnergyCost"), "select.remainEnergyCost"),
        context_card_id=(select.get("contextCard") or {}).get("id"),
        effect_card_id=(select.get("effect") or {}).get("id"),
        options=tuple(options),
    )


def semantic_snapshot(
    raw: Mapping[str, Any], battle_id: str, transition_id: int, card_data_sha256: str,
    previous_action_ref: str | None = None, previous_request_ref: str | None = None,
) -> tuple[EngineObservationV1, SelectionRequestV1 | None]:
    current = raw.get("current")
    if current is None:
        return (
            EngineObservationV1(
                schema_version=CONTRACT_VERSION,
                battle_id=battle_id,
                transition_id=transition_id,
                acting_player=None,
                terminal_result=None,
                turn=None,
                turn_action_count=None,
                first_player=None,
                supporter_played=None,
                stadium_played=None,
                energy_attached=None,
                retreated=None,
                players=(),
                entities=(),
                public_events=_events(raw.get("logs", [])),
                previous_request_ref=previous_request_ref,
                previous_action_ref=previous_action_ref,
            ),
            None,
        )
    acting_player = _integer(current["yourIndex"], "current.yourIndex")
    if acting_player not in (0, 1):
        raise ContractViolation("acting player must be 0 or 1")
    players = current["players"]
    if len(players) != 2:
        raise ContractViolation("engine contract requires exactly two players")
    if players[1 - acting_player]["hand"] is not None:
        raise ContractViolation("opponent hidden hand leaked into public observation")
    result = _integer(current["result"], "current.result")
    if result not in (-1, 0, 1, 2):
        raise ContractViolation(f"unknown terminal result {result}")
    terminal_result = None if result == -1 else result
    select = raw.get("select")
    entities, positions = _visible_entities(current, select, acting_player, card_data_sha256)
    observation = EngineObservationV1(
        schema_version=CONTRACT_VERSION,
        battle_id=battle_id,
        transition_id=transition_id,
        acting_player=acting_player,
        terminal_result=terminal_result,
        turn=_integer(current["turn"], "current.turn"),
        turn_action_count=_integer(current["turnActionCount"], "current.turnActionCount"),
        first_player=_optional_integer(current.get("firstPlayer"), "current.firstPlayer"),
        supporter_played=bool(current["supporterPlayed"]),
        stadium_played=bool(current["stadiumPlayed"]),
        energy_attached=bool(current["energyAttached"]),
        retreated=bool(current["retreated"]),
        players=_players(current),
        entities=entities,
        public_events=_events(raw.get("logs", [])),
        previous_request_ref=previous_request_ref,
        previous_action_ref=previous_action_ref,
    )
    if terminal_result is not None:
        return observation, None
    if select is None:
        raise ContractViolation("ongoing native state has no selection request")
    return observation, _request(select, battle_id, transition_id, acting_player, entities, positions)


ENTITY_FEATURES = ENTITY_FEATURE_NAMES
OPTION_FEATURES = OPTION_FEATURE_NAMES
EVENT_FEATURES = EVENT_FEATURE_NAMES
GLOBAL_FEATURES = GLOBAL_FEATURE_NAMES


def _row(values: Sequence[int | float | bool | None]) -> tuple[tuple[float, ...], tuple[bool, ...]]:
    return (
        tuple(0.0 if value is None else float(value) for value in values),
        tuple(value is None for value in values),
    )


def encode_numeric(
    observation: EngineObservationV1, request: SelectionRequestV1 | None,
    *, max_entities: int | None = None, max_options: int | None = None,
) -> NumericTensorV1:
    if max_entities is not None and len(observation.entities) > max_entities:
        raise ContractViolation("entity batching capacity exceeded; truncation is forbidden")
    option_count = len(request.options) if request else 0
    if max_options is not None and option_count > max_options:
        raise ContractViolation("option batching capacity exceeded; truncation is forbidden")
    entity_index = {entity.entity_key: index for index, entity in enumerate(observation.entities)}
    entity_rows = [
        _row(
            (
                entity.card_id, entity.owner, entity.zone, entity.position, entity.hp, entity.max_hp,
                entity.damage, entity.appear_this_turn, entity.attached_energy_count,
                entity.attached_tool_count, entity.evolution_depth,
            )
        )
        for entity in observation.entities
    ]
    option_rows = [
        _row(
            (
                option.selection_type, option.selection_context, option.option_type, option.number,
                option.area, option.index, option.player_index, option.tool_index, option.energy_index,
                option.count, option.in_play_area, option.in_play_index, option.attack_id, option.card_id,
                option.special_condition_type, entity_index.get(option.source_entity_key),
                entity_index.get(option.target_entity_key),
            )
        )
        for option in (request.options if request else ())
    ]
    event_rows = [
        _row(
            (
                event.event_type, event.fields.get("playerIndex"), event.fields.get("cardId"),
                event.fields.get("value"), event.fields.get("count"), event.fields.get("result"),
            )
        )
        for event in observation.public_events
    ]
    actor = observation.acting_player
    self_player = observation.players[actor] if actor is not None and observation.players else None
    opponent = observation.players[1 - actor] if actor is not None and observation.players else None
    global_row = _row(
        (
            actor, observation.turn, observation.turn_action_count, observation.first_player,
            observation.supporter_played, observation.stadium_played, observation.energy_attached,
            observation.retreated, observation.terminal_result,
            request.min_count if request else None, request.max_count if request else None,
            request.remain_damage_counter if request else None,
            request.remain_energy_cost if request else None,
            self_player.deck_count if self_player else None, self_player.hand_count if self_player else None,
            self_player.prize_count if self_player else None,
            opponent.deck_count if opponent else None, opponent.hand_count if opponent else None,
            opponent.prize_count if opponent else None,
        )
    )
    return NumericTensorV1(
        schema_version=CONTRACT_VERSION,
        entity_feature_names=ENTITY_FEATURES,
        entity_values=tuple(row for row, _ in entity_rows),
        entity_missing_masks=tuple(mask for _, mask in entity_rows),
        entity_length=len(entity_rows),
        option_feature_names=OPTION_FEATURES,
        option_values=tuple(row for row, _ in option_rows),
        option_missing_masks=tuple(mask for _, mask in option_rows),
        option_available_mask=tuple(option.available for option in (request.options if request else ())),
        option_offsets=(0, option_count),
        option_length=option_count,
        event_feature_names=EVENT_FEATURES,
        event_values=tuple(row for row, _ in event_rows),
        event_missing_masks=tuple(mask for _, mask in event_rows),
        event_length=len(event_rows),
        global_feature_names=GLOBAL_FEATURES,
        global_values=global_row[0],
        global_missing_mask=global_row[1],
    )
