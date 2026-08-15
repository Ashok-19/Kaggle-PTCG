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
    PLAYER_FEATURE_NAMES,
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
    "PLAYER": 11,
    "LOOKING": 12,
    "PLAYING": 13,
    "DECK_BOTTOM": 14,
    "ME": 15,
    "EFFECTED": 16,
    "EFFECTED_PRE_TARGET": 17,
    "SELECTED_LIST": 18,
    "TRIGGER_SUBJECT": 19,
    "TRIGGER_OBJECT": 20,
    "ATTACH": 21,
    "TURN_PLAY": 22,
    "ATTACK_PRE_MY_TURN": 23,
    "TEMPORARY": 24,
}
PHYSICAL_AREAS = set(range(AREA["DECK"], AREA["DECK_BOTTOM"] + 1))
PSEUDO_AREAS = set(range(AREA["ME"], AREA["TEMPORARY"]))

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

SELECT_OPTION_TYPES = {
    0: set(range(7, 15)),
    1: {3},
    2: {4, 5},
    3: {3, 4, 5},
    4: {6},
    5: {15},
    6: {13},
    7: {9},
    8: {0},
    9: {1, 2},
    10: {16},
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

OPTION_FIELDS = {
    0: ("number",),
    1: (),
    2: (),
    3: ("area", "index", "playerIndex"),
    4: ("area", "index", "playerIndex", "toolIndex"),
    5: ("area", "index", "playerIndex", "energyIndex"),
    6: ("area", "index", "playerIndex", "energyIndex", "count"),
    7: ("index",),
    8: ("area", "index", "inPlayArea", "inPlayIndex"),
    9: ("area", "index", "inPlayArea", "inPlayIndex"),
    10: ("area", "index"),
    11: ("area", "index"),
    12: (),
    13: ("attackId",),
    14: (),
    15: ("cardId", "serial"),
    16: ("specialConditionType",),
}

SOURCE_KIND_CODE = {"NONE": 0, "ENTITY": 1, "PLAYER": 2, "PSEUDO": 3, "TEMPORARY": 4}
CHOICE_ROLE_CODE = {name: index for index, name in enumerate(OPTION_NAMES.values(), start=1)}

NUMERIC_DROPPED_PUBLIC_FIELDS = {
    "VisibleEntityV1.entity_key": "derived from owner and engine serial",
    "VisibleEntityV1.metadata_ref": "derived from card_id and card-data hash",
    "LegalOptionV1.option_name": "derived from option_type",
    "LegalOptionV1.semantic_fingerprint": "integrity metadata, not game information",
    "PublicEventV1.event_name": "derived from event_type",
    "EngineObservationV1.battle_id": "sequence ownership metadata",
    "EngineObservationV1.transition_id": "sequence ownership metadata",
    "EngineObservationV1.previous_request_ref": "trajectory integrity metadata",
    "EngineObservationV1.previous_action_ref": "trajectory integrity metadata",
    "SelectionRequestV1.request_id": "trajectory integrity metadata",
    "SelectionRequestV1.episode_uuid": "sequence ownership metadata",
    "SelectionRequestV1.selection_seq": "sequence ownership metadata",
    "LegalOptionV1.original_index": "transport-only mapping; raw option position is forbidden as a model feature",
}

NUMERIC_FIELD_COVERAGE = {
    "VisibleEntityV1": {
        "entity_key": "drop_allowlist", "card_id": "entity.card_id", "serial": "entity.serial",
        "metadata_ref": "drop_allowlist", "owner": "entity.owner", "zone": "entity.zone",
        "position": "entity.position", "parent_entity_key": "entity.parent_entity_index",
        "hp": "entity.hp", "max_hp": "entity.max_hp", "damage": "entity.damage",
        "appear_this_turn": "entity.appear_this_turn", "energy_types": "entity_energy_values/offsets",
        "attached_energy_count": "entity.attached_energy_count",
        "attached_tool_count": "entity.attached_tool_count", "evolution_depth": "entity.evolution_depth",
        "statuses": "entity.status_*", "visible": "entity.visible",
    },
    "PlayerViewV1": {name: f"player.{name}" for name in (
        "player_index", "bench_max", "deck_count", "hand_count", "prize_count",
        "visible_prize_count", "hand_visible", "facedown_active_count",
    )},
    "PublicEventV1": {
        "event_type": "event.event_type", "event_name": "drop_allowlist", "fields": "event.*",
    },
    "EngineObservationV1": {
        "schema_version": "tensor.schema_version", "battle_id": "drop_allowlist",
        "transition_id": "drop_allowlist", "acting_player": "global.acting_player",
        "terminal_result": "global.terminal_result", "turn": "global.turn",
        "turn_action_count": "global.turn_action_count", "first_player": "global.first_player",
        "supporter_played": "global.supporter_played", "stadium_played": "global.stadium_played",
        "energy_attached": "global.energy_attached", "retreated": "global.retreated",
        "players": "player rows", "entities": "entity rows", "public_events": "event rows",
        "previous_request_ref": "drop_allowlist", "previous_action_ref": "drop_allowlist",
    },
    "LegalOptionV1": {
        "schema_version": "tensor.schema_version", "original_index": "drop_allowlist",
        "selection_type": "option.selection_type", "selection_context": "option.selection_context",
        "option_type": "option.option_type", "option_name": "drop_allowlist",
        "number": "option.number", "area": "option.area", "index": "option.index",
        "player_index": "option.player_index", "tool_index": "option.tool_index",
        "energy_index": "option.energy_index", "count": "option.count",
        "in_play_area": "option.in_play_area", "in_play_index": "option.in_play_index",
        "attack_id": "option.attack_id", "card_id": "option.card_id", "serial": "option.serial",
        "special_condition_type": "option.special_condition_type", "source_kind": "option.source_kind",
        "source_ref": "source kind plus entity/raw positional fields", "target_kind": "option.target_kind",
        "target_ref": "target kind plus entity/raw positional fields", "choice_role": "option.choice_role",
        "source_entity_key": "option.source_entity_index",
        "target_entity_key": "option.target_entity_index", "available": "option_available_mask",
        "semantic_fingerprint": "drop_allowlist",
    },
    "SelectionRequestV1": {
        "schema_version": "tensor.schema_version", "episode_uuid": "drop_allowlist",
        "selection_seq": "drop_allowlist", "request_id": "drop_allowlist",
        "acting_player": "global.acting_player", "selection_type": "global.selection_type",
        "selection_context": "global.selection_context", "min_count": "global.min_count",
        "max_count": "global.max_count", "remain_damage_counter": "global.remain_damage_counter",
        "remain_energy_cost": "global.remain_energy_cost", "context_card_id": "global.context_card_id",
        "effect_card_id": "global.effect_card_id", "ordering": "global.request_ordered",
        "options": "option rows",
    },
}


def _integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractViolation(f"{field} must be an integer")
    return value


def _nonnegative(value: Any, field: str) -> int:
    result = _integer(value, field)
    if result < 0:
        raise ContractViolation(f"{field} has an impossible negative position")
    return result


def _optional_integer(value: Any, field: str) -> int | None:
    return None if value is None else _integer(value, field)


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ContractViolation(f"{field} must be a boolean")
    return value


def _player(value: Any, field: str) -> int:
    result = _integer(value, field)
    if result not in (0, 1):
        raise ContractViolation(f"{field} must be player 0 or 1")
    return result


def _optional_player(value: Any, field: str) -> int | None:
    if value is None or value == -1:
        return None
    return _player(value, field)


def _entity_key(owner: int, serial: int) -> str:
    return f"p{owner}:s{serial}"


def _card_entity(
    card: Mapping[str, Any], owner: int, zone: int, position: int, card_data_sha256: str,
    *, parent: str | None = None,
) -> VisibleEntityV1:
    card_id = _integer(card["id"], "card.id")
    serial = _integer(card["serial"], "card.serial")
    if card_id <= 0 or serial <= 0:
        raise ContractViolation("visible card id and serial must be positive")
    if zone not in PHYSICAL_AREAS or position < 0:
        raise ContractViolation("visible card has an unknown zone or impossible position")
    return VisibleEntityV1(
        entity_key=_entity_key(owner, serial),
        card_id=card_id,
        serial=serial,
        metadata_ref=f"card:{card_id}@{card_data_sha256}",
        owner=owner,
        zone=zone,
        position=position,
        parent_entity_key=parent,
    )


def _hidden_slot(owner: int, zone: int, position: int) -> VisibleEntityV1:
    return VisibleEntityV1(
        entity_key=f"slot:p{owner}:z{zone}:i{position}",
        card_id=None,
        serial=None,
        metadata_ref=None,
        owner=owner,
        zone=zone,
        position=position,
        visible=False,
    )


def _visible_entities(
    current: Mapping[str, Any], select: Mapping[str, Any] | None, acting_player: int,
    card_data_sha256: str,
) -> tuple[tuple[VisibleEntityV1, ...], dict[tuple[int, int, int], str]]:
    entities: dict[str, VisibleEntityV1] = {}
    positions: dict[tuple[int, int, int], str] = {}

    def add(entity: VisibleEntityV1) -> None:
        if entity.entity_key in entities and entities[entity.entity_key] != entity:
            raise ContractViolation("one engine serial resolves to conflicting visible entities")
        entities[entity.entity_key] = entity
        if entity.position is not None:
            positions[(entity.owner, entity.zone, entity.position)] = entity.entity_key

    for player_index, player_state in enumerate(current["players"]):
        status_values = tuple(
            index
            for index, field in enumerate(("poisoned", "burned", "asleep", "paralyzed", "confused"))
            if _boolean(player_state[field], f"player.{field}")
        )
        for zone_name, field in (("ACTIVE", "active"), ("BENCH", "bench")):
            zone = AREA[zone_name]
            for position, pokemon in enumerate(player_state[field]):
                if pokemon is None:
                    if zone == AREA["ACTIVE"]:
                        add(_hidden_slot(player_index, zone, position))
                    continue
                card_id = _integer(pokemon["id"], "pokemon.id")
                serial = _integer(pokemon["serial"], "pokemon.serial")
                if card_id <= 0 or serial <= 0:
                    raise ContractViolation("visible Pokemon id and serial must be positive")
                key = _entity_key(player_index, serial)
                hp = _integer(pokemon["hp"], "pokemon.hp")
                max_hp = _integer(pokemon["maxHp"], "pokemon.maxHp")
                # Native cleanup can expose an over-knocked-out Pokemon briefly.
                if max_hp <= 0 or hp > max_hp:
                    raise ContractViolation(
                        "Pokemon HP fields are impossible: "
                        f"hp={hp}, max_hp={max_hp}, owner={player_index}, "
                        f"zone={zone_name}, position={position}"
                    )
                energy_types = tuple(_nonnegative(item, "pokemon.energies[]") for item in pokemon["energies"])
                entity = VisibleEntityV1(
                    entity_key=key,
                    card_id=card_id,
                    serial=serial,
                    metadata_ref=f"card:{card_id}@{card_data_sha256}",
                    owner=player_index,
                    zone=zone,
                    position=position,
                    hp=hp,
                    max_hp=max_hp,
                    damage=max_hp - hp,
                    appear_this_turn=_boolean(pokemon["appearThisTurn"], "pokemon.appearThisTurn"),
                    energy_types=energy_types,
                    attached_energy_count=len(energy_types),
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
                        owner = _player(card.get("playerIndex", player_index), "attachment.playerIndex")
                        child = _card_entity(
                            card, owner, attachment_zone, attachment_index, card_data_sha256, parent=key
                        )
                        add(child)
        for zone_name, field in (("HAND", "hand"), ("DISCARD", "discard"), ("PRIZE", "prize")):
            cards = player_state[field]
            if cards is None:
                continue
            for position, card in enumerate(cards):
                if card is None and zone_name == "PRIZE":
                    add(_hidden_slot(player_index, AREA[zone_name], position))
                elif card is not None:
                    owner = _player(card.get("playerIndex", player_index), "card.playerIndex")
                    add(_card_entity(card, owner, AREA[zone_name], position, card_data_sha256))

    for position, card in enumerate(current.get("stadium", [])):
        if card is not None:
            owner = _player(card["playerIndex"], "stadium.playerIndex")
            add(_card_entity(card, owner, AREA["STADIUM"], position, card_data_sha256))
    for position, card in enumerate(current.get("looking") or []):
        if card is not None:
            owner = _player(card.get("playerIndex", acting_player), "looking.playerIndex")
            add(_card_entity(card, owner, AREA["LOOKING"], position, card_data_sha256))
    if select is not None:
        for position, card in enumerate(select.get("deck") or []):
            if card is not None:
                owner = _player(card.get("playerIndex", acting_player), "select.deck.playerIndex")
                add(_card_entity(card, owner, AREA["DECK"], position, card_data_sha256))
        for field in ("contextCard", "effect"):
            card = select.get(field)
            if card is not None:
                owner = _player(card.get("playerIndex", acting_player), f"select.{field}.playerIndex")
                entity = _card_entity(card, owner, AREA["PLAYING"], 0, card_data_sha256)
                if entity.entity_key not in entities:
                    add(entity)
    return tuple(entities.values()), positions


def _players(current: Mapping[str, Any]) -> tuple[PlayerViewV1, ...]:
    result = []
    for index, player_state in enumerate(current["players"]):
        hand = player_state["hand"]
        result.append(
            PlayerViewV1(
                player_index=index,
                bench_max=_nonnegative(player_state["benchMax"], "benchMax"),
                deck_count=_nonnegative(player_state["deckCount"], "deckCount"),
                hand_count=_nonnegative(player_state["handCount"], "handCount"),
                prize_count=len(player_state["prize"]),
                visible_prize_count=sum(card is not None for card in player_state["prize"]),
                hand_visible=hand is not None,
                facedown_active_count=sum(card is None for card in player_state["active"]),
            )
        )
    return tuple(result)


def _events(logs: Sequence[Mapping[str, Any]]) -> tuple[PublicEventV1, ...]:
    events = []
    allowed = set(EVENT_FEATURE_NAMES) - {"event_type"}
    for log in logs:
        event_type = _integer(log["type"], "log.type")
        if event_type not in LOG_NAMES:
            raise ContractViolation(f"unknown log type {event_type}")
        unexpected = set(log) - {"type"} - allowed
        if unexpected:
            raise ContractViolation(f"unsupported public log field {sorted(unexpected)[0]}")
        payload: dict[str, int | bool | None] = {}
        for key, value in log.items():
            if key == "type" or value is None:
                continue
            if not isinstance(value, (int, bool)):
                raise ContractViolation(f"unsupported public log field {key}")
            payload[key] = value
        events.append(PublicEventV1(event_type, LOG_NAMES[event_type], payload))
    return tuple(events)


def _position_ref(
    owner: int,
    area: int,
    index: int,
    positions: Mapping[tuple[int, int, int], str],
) -> tuple[str, str, str | None]:
    owner = _player(owner, "option.playerIndex")
    index = _nonnegative(index, "option.index")
    if area == AREA["PLAYER"]:
        return "PLAYER", f"player:{owner}", None
    if area in PSEUDO_AREAS:
        return "PSEUDO", f"pseudo:area:{area}:player:{owner}:index:{index}", None
    if area == AREA["TEMPORARY"]:
        return "TEMPORARY", f"temporary:player:{owner}:index:{index}", None
    if area not in PHYSICAL_AREAS:
        raise ContractViolation(f"unknown entity area {area}")
    key = positions.get((owner, area, index))
    if key is None and area == AREA["STADIUM"]:
        matches = [value for (candidate_owner, candidate_area, candidate_index), value in positions.items()
                   if candidate_area == area and candidate_index == index]
        key = matches[0] if len(matches) == 1 else None
    if key is None:
        raise ContractViolation(
            f"unresolved option entity reference player={owner} area={area} index={index}"
        )
    return "ENTITY", key, key


def _resolve_option(
    option: Mapping[str, Any], option_type: int, acting_player: int,
    positions: Mapping[tuple[int, int, int], str], entities: Sequence[VisibleEntityV1],
) -> tuple[str, str | None, str, str | None, str | None, str | None, str]:
    none = ("NONE", None, "NONE", None, None, None)
    role = OPTION_NAMES[option_type]
    if option_type in {0, 1, 2, 14, 16}:
        return (*none, role)
    if option_type == 3:
        source_kind, source_ref, source_entity = _position_ref(
            option["playerIndex"], option["area"], option["index"], positions
        )
        return source_kind, source_ref, "NONE", None, source_entity, None, role
    if option_type in {4, 5, 6}:
        owner = option["playerIndex"]
        _, parent_ref, parent_entity = _position_ref(owner, option["area"], option["index"], positions)
        attachment_zone = AREA["TOOL"] if option_type == 4 else AREA["ENERGY"]
        attachment_index = option["toolIndex"] if option_type == 4 else option["energyIndex"]
        attachment_index = _nonnegative(attachment_index, "option.attachmentIndex")
        source = next(
            (
                entity.entity_key
                for entity in entities
                if entity.parent_entity_key == parent_entity
                and entity.zone == attachment_zone
                and entity.position == attachment_index
            ),
            None,
        )
        if source is None:
            raise ContractViolation("unresolved attached-card option entity reference")
        return "ENTITY", source, "ENTITY", parent_ref, source, parent_entity, role
    if option_type == 7:
        source_kind, source_ref, source_entity = _position_ref(
            acting_player, AREA["HAND"], option["index"], positions
        )
        return source_kind, source_ref, "NONE", None, source_entity, None, role
    if option_type in {8, 9}:
        source_kind, source_ref, source_entity = _position_ref(
            acting_player, option["area"], option["index"], positions
        )
        target_kind, target_ref, target_entity = _position_ref(
            acting_player, option["inPlayArea"], option["inPlayIndex"], positions
        )
        return source_kind, source_ref, target_kind, target_ref, source_entity, target_entity, role
    if option_type in {10, 11}:
        source_kind, source_ref, source_entity = _position_ref(
            acting_player, option["area"], option["index"], positions
        )
        return source_kind, source_ref, "NONE", None, source_entity, None, role
    if option_type in {12, 13}:
        source_kind, source_ref, source_entity = _position_ref(
            acting_player, AREA["ACTIVE"], 0, positions
        )
        return source_kind, source_ref, "NONE", None, source_entity, None, role
    if option_type == 15:
        card_id = option["cardId"]
        serial = option["serial"]
        if card_id == 0 and serial == 0:
            return "PSEUDO", "pseudo:skill:default", "NONE", None, None, None, role
        matches = [entity for entity in entities if entity.serial == serial]
        if len(matches) != 1 or matches[0].card_id != card_id:
            raise ContractViolation("unresolved SKILL cardId/serial reference")
        return "ENTITY", matches[0].entity_key, "NONE", None, matches[0].entity_key, None, role
    raise ContractViolation(f"unknown option type {option_type}")


def _request(
    select: Mapping[str, Any], battle_id: str, transition_id: int, acting_player: int,
    entities: Sequence[VisibleEntityV1], positions: Mapping[tuple[int, int, int], str],
) -> SelectionRequestV1:
    selection_type = _integer(select["type"], "select.type")
    if selection_type not in SELECT_NAMES:
        raise ContractViolation(f"unknown selection type {selection_type}")
    context = _integer(select["context"], "select.context")
    if context not in range(49):
        raise ContractViolation(f"unknown selection context {context}")
    options = []
    for original_index, raw in enumerate(select["option"]):
        option_type = _integer(raw["type"], "option.type")
        if option_type not in OPTION_NAMES:
            raise ContractViolation(f"unknown option type {option_type}")
        if option_type not in SELECT_OPTION_TYPES[selection_type]:
            raise ContractViolation("option type is incompatible with selection type")
        required = set(OPTION_FIELDS[option_type])
        missing = required - set(raw)
        if missing:
            raise ContractViolation(f"required field {sorted(missing)[0]} is missing for option type")
        unexpected = set(raw) - {"type"} - required
        if unexpected:
            raise ContractViolation(f"unsupported field {sorted(unexpected)[0]} for option type")
        for field in required:
            _integer(raw[field], f"option.{field}")
        try:
            resolved = _resolve_option(raw, option_type, acting_player, positions, entities)
        except ContractViolation as error:
            raise ContractViolation(f"option type {option_type}: {error}") from error
        source_kind, source_ref, target_kind, target_ref, source_entity, target_entity, role = resolved
        option = LegalOptionV1(
            schema_version=CONTRACT_VERSION,
            original_index=original_index,
            selection_type=selection_type,
            selection_context=context,
            option_type=option_type,
            option_name=OPTION_NAMES[option_type],
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
            source_kind=source_kind,
            source_ref=source_ref,
            target_kind=target_kind,
            target_ref=target_ref,
            choice_role=role,
            source_entity_key=source_entity,
            target_entity_key=target_entity,
        )
        options.append(replace(option, semantic_fingerprint=stable_hash(option.semantic_payload())))
    min_count = _nonnegative(select["minCount"], "select.minCount")
    max_count = _nonnegative(select["maxCount"], "select.maxCount")
    request_id = stable_hash(
        {
            "episode_uuid": battle_id,
            "selection_seq": transition_id,
            "acting_player": acting_player,
            "selection_type": selection_type,
            "context": context,
            "min_count": min_count,
            "max_count": max_count,
            "fingerprints": [option.semantic_fingerprint for option in options],
        }
    )
    context_card = select.get("contextCard")
    effect_card = select.get("effect")
    return SelectionRequestV1(
        schema_version=CONTRACT_VERSION,
        episode_uuid=battle_id,
        selection_seq=transition_id,
        request_id=request_id,
        acting_player=acting_player,
        selection_type=selection_type,
        selection_context=context,
        min_count=min_count,
        max_count=max_count,
        remain_damage_counter=_optional_integer(
            select.get("remainDamageCounter"), "select.remainDamageCounter"
        ),
        remain_energy_cost=_optional_integer(select.get("remainEnergyCost"), "select.remainEnergyCost"),
        context_card_id=(
            _integer(context_card["id"], "select.contextCard.id") if context_card is not None else None
        ),
        effect_card_id=(
            _integer(effect_card["id"], "select.effect.id") if effect_card is not None else None
        ),
        ordering="ORDERED" if selection_type == 5 and context == 34 else "UNORDERED",
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
    acting_player = _player(current["yourIndex"], "current.yourIndex")
    players = current["players"]
    if len(players) != 2:
        raise ContractViolation("engine contract requires exactly two players")
    if players[1 - acting_player]["hand"] is not None:
        raise ContractViolation("opponent hidden hand leaked into public observation")
    result = _integer(current["result"], "current.result")
    if result not in (-1, 0, 1, 2):
        raise ContractViolation(f"unknown terminal result {result}")
    terminal_result = None if result == -1 else result

    # Terminal is deliberately decided before the selection object is read.
    select = None if terminal_result is not None else raw.get("select")
    entities, positions = _visible_entities(current, select, acting_player, card_data_sha256)
    observation = EngineObservationV1(
        schema_version=CONTRACT_VERSION,
        battle_id=battle_id,
        transition_id=transition_id,
        acting_player=acting_player,
        terminal_result=terminal_result,
        turn=_nonnegative(current["turn"], "current.turn"),
        turn_action_count=_nonnegative(current["turnActionCount"], "current.turnActionCount"),
        first_player=_optional_player(current.get("firstPlayer"), "current.firstPlayer"),
        supporter_played=_boolean(current["supporterPlayed"], "current.supporterPlayed"),
        stadium_played=_boolean(current["stadiumPlayed"], "current.stadiumPlayed"),
        energy_attached=_boolean(current["energyAttached"], "current.energyAttached"),
        retreated=_boolean(current["retreated"], "current.retreated"),
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
PLAYER_FEATURES = PLAYER_FEATURE_NAMES
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
    player_rows = [
        _row(
            (
                player.player_index, player.bench_max, player.deck_count, player.hand_count,
                player.prize_count, player.visible_prize_count, player.hand_visible,
                player.facedown_active_count,
            )
        )
        for player in observation.players
    ]
    entity_rows = [
        _row(
            (
                entity.card_id, entity.serial, entity.owner, entity.zone, entity.position,
                entity_index.get(entity.parent_entity_key), entity.hp, entity.max_hp, entity.damage,
                entity.appear_this_turn, entity.attached_energy_count, entity.attached_tool_count,
                entity.evolution_depth, entity.visible,
                *(index in entity.statuses for index in range(5)),
            )
        )
        for entity in observation.entities
    ]
    energy_values: list[int] = []
    energy_offsets = [0]
    for entity in observation.entities:
        energy_values.extend(entity.energy_types)
        energy_offsets.append(len(energy_values))
    option_rows = [
        _row(
            (
                option.selection_type, option.selection_context, option.option_type, option.number,
                option.area, option.index, option.player_index, option.tool_index, option.energy_index,
                option.count, option.in_play_area, option.in_play_index, option.attack_id, option.card_id,
                option.serial, option.special_condition_type, SOURCE_KIND_CODE[option.source_kind],
                entity_index.get(option.source_entity_key), SOURCE_KIND_CODE[option.target_kind],
                entity_index.get(option.target_entity_key), CHOICE_ROLE_CODE[option.choice_role],
            )
        )
        for option in (request.options if request else ())
    ]
    event_rows = [
        _row((event.event_type, *(event.fields.get(name) for name in EVENT_FEATURES[1:])))
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
            request.selection_type if request else None, request.selection_context if request else None,
            request.ordering == "ORDERED" if request else None,
            request.context_card_id if request else None, request.effect_card_id if request else None,
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
        player_feature_names=PLAYER_FEATURES,
        player_values=tuple(row for row, _ in player_rows),
        player_missing_masks=tuple(mask for _, mask in player_rows),
        player_length=len(player_rows),
        entity_feature_names=ENTITY_FEATURES,
        entity_values=tuple(row for row, _ in entity_rows),
        entity_missing_masks=tuple(mask for _, mask in entity_rows),
        entity_length=len(entity_rows),
        entity_energy_values=tuple(energy_values),
        entity_energy_offsets=tuple(energy_offsets),
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
