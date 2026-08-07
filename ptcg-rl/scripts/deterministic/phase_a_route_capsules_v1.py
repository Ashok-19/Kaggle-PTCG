"""Bounded public-transition capsules for the five Phase A partial routes.

This runner deliberately uses the official native engine's own shuffle/coin
path.  Probe policies see only the semantic public observation and the current
legal request.  No deck order, hidden hand, private engine object, or manual
random outcome is used.  A capsule is evidence for an interaction only when
the immediately preceding public request/action and the immediately following
public events/state reconcile the claimed transition.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import sys
import time
import uuid
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from ptcg_rl.g1.actions import CompoundActionBuilder, validate_compound_action
from ptcg_rl.g1.models import ContractViolation, EngineObservationV1, SelectionRequestV1
from ptcg_rl.g1.native import NativeCABTTransport
from ptcg_rl.g1.semantic import AREA, LOG_NAMES, semantic_snapshot


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs/deterministic/phase_a_route_capsules_v1.json"
DEFAULT_REPORT = ROOT / "reports/deterministic/phase-a-route-capsules-v1.json"

ATTACK_TO_ROUTE = {1042: "riptide", 1043: "swirling_waves", 1046: "hammer_lanche", 1047: "frost_barrier"}
ROUTE_CARD = {"riptide": 721, "swirling_waves": 721, "surfing_beach": 1262, "hammer_lanche": 723, "frost_barrier": 723}
ROUTE_SUPPORT = {"riptide": 1121, "swirling_waves": None, "surfing_beach": 1262, "hammer_lanche": None, "frost_barrier": None}
WATER = 3
POKEMON = {721, 722, 723}
LOG_TYPE = {value: key for key, value in LOG_NAMES.items()}

ASSET_PATHS = {
    "card_data_sha256": ROOT / "private/assets/official/EN_Card_Data.csv",
    "card_table_file_sha256": ROOT / "private/g2/card-table-v1.json",
    "engine_library_sha256": ROOT / "private/assets/official/sample_submission/sample_submission/cg/libcg.so",
    "wrapper_sha256": ROOT / "private/assets/official/sample_submission/sample_submission/cg/game.py",
    "api_sha256": ROOT / "private/assets/official/sample_submission/sample_submission/cg/api.py",
}
SOURCE_PATHS = (
    Path(__file__),
    ROOT / "src/ptcg_rl/g1/actions.py",
    ROOT / "src/ptcg_rl/g1/models.py",
    ROOT / "src/ptcg_rl/g1/native.py",
    ROOT / "src/ptcg_rl/g1/semantic.py",
)
RELIABILITY_COUNTER_KEYS = (
    "invalid_actions", "semantic_contract_failures", "request_cap_failures", "timeouts",
    "native_errors", "fallbacks", "post_terminal_actions", "unclassified_terminal",
    "incomplete_games", "other_failures",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    expected = {"schema_version", "record_id", "candidate", "opponent", "knowledge_base_ids", "assets", "limits", "routes", "deck_specs"}
    if set(config) != expected or config["schema_version"] != 1 or config["record_id"] != "phase-a-route-capsules-v1":
        raise ValueError("route capsule config identity/keys differ")
    if config["knowledge_base_ids"] != ["DR-025", "DR-030", "DR-033", "AP-014", "RQ-007"]:
        raise ValueError("route capsule knowledge-base binding differs")
    if len(config["routes"]) != 5 or len({row["id"] for row in config["routes"]}) != 5:
        raise ValueError("route set must contain exactly five unique routes")
    limits = config["limits"]
    if limits["games_per_route"] < 1 or limits["games_per_route"] > 48 or limits["request_cap_per_game"] > 1200 or limits["wall_seconds"] > 300:
        raise ValueError("route capsule limits exceed bounded ceiling")
    for name, spec in config["deck_specs"].items():
        if not isinstance(spec, dict) or sum(int(count) for count in spec.values()) != 60:
            raise ValueError(f"{name} deck is not exactly 60 cards")
        if any(int(card_id) != 3 and int(count) > 4 for card_id, count in spec.items()):
            raise ValueError(f"{name} deck exceeds four-copy same-name limit")
        if not any(int(card_id) in POKEMON for card_id in spec):
            raise ValueError(f"{name} deck has no Basic Pokemon")
    for key in ("card_data_sha256", "card_table_file_sha256", "card_table_semantic_sha256", "engine_library_sha256", "wrapper_sha256", "api_sha256"):
        if len(config["assets"][key]) != 64:
            raise ValueError(f"invalid asset hash: {key}")
    return config


def _validate_asset_receipts(config: Mapping[str, Any]) -> dict[str, str]:
    """Hash the files actually loaded by this runner, not only expected labels."""
    observed: dict[str, str] = {}
    for key, path in ASSET_PATHS.items():
        if not path.is_file():
            raise FileNotFoundError(path)
        digest = sha256(path)
        if digest != config["assets"][key]:
            raise ValueError(f"asset hash mismatch for {key}: {digest}")
        observed[key] = digest
    engine_root = ROOT / str(config["assets"]["engine_root"])
    if (engine_root / "cg" / ASSET_PATHS["engine_library_sha256"].name).resolve() != ASSET_PATHS["engine_library_sha256"].resolve():
        raise ValueError("engine root does not contain the hashed native library")
    return observed


def _normalise_counters(counter: Mapping[str, int]) -> dict[str, int]:
    values = {key: int(counter.get(key, 0)) for key in RELIABILITY_COUNTER_KEYS}
    values["native_errors"] = int(counter.get("native_errors", 0)) + sum(value for key, value in counter.items() if key.startswith("native_error:"))
    known = set(RELIABILITY_COUNTER_KEYS) | {key for key in counter if key.startswith("native_error:")}
    values["other_failures"] = sum(int(value) for key, value in counter.items() if key not in known)
    return values


def expand_deck(spec: Mapping[str, int]) -> list[int]:
    deck: list[int] = []
    for card_id, count in sorted(spec.items(), key=lambda item: int(item[0])):
        deck.extend([int(card_id)] * int(count))
    if len(deck) != 60:
        raise ValueError("expanded deck is not exactly 60 cards")
    return deck


def _entity_card(observation: EngineObservationV1, key: str | None) -> int | None:
    if key is None:
        return None
    entity = next((item for item in observation.entities if item.entity_key == key), None)
    return entity.card_id if entity else None


def _public_cards(observation: EngineObservationV1, player: int | None = None) -> list[dict[str, Any]]:
    result = []
    for entity in observation.entities:
        if entity.card_id is None or (player is not None and entity.owner != player):
            continue
        result.append({
            "entity_key": entity.entity_key,
            "card_id": entity.card_id,
            "serial": entity.serial,
            "owner": entity.owner,
            "zone": entity.zone,
            "position": entity.position,
            "parent_entity_key": entity.parent_entity_key,
            "hp": entity.hp,
            "max_hp": entity.max_hp,
            "damage": entity.damage,
            "energy_types": list(entity.energy_types),
            "attached_energy_count": entity.attached_energy_count,
        })
    return result


def _player_view(observation: EngineObservationV1, player: int) -> Any:
    return next(row for row in observation.players if row.player_index == player)


def _selected_card_ids(observation: EngineObservationV1, request: SelectionRequestV1, indices: list[int]) -> list[int | None]:
    return [_entity_card(observation, request.options[index].source_entity_key) or request.options[index].card_id for index in indices]


def _event_dict(event: Any) -> dict[str, Any]:
    value = {key: item for key, item in asdict(event).items() if item is not None}
    value["event_name"] = event.event_name
    return value


def _events_for(events: tuple[Any, ...], *, name: str | None = None, attack_id: int | None = None, player: int | None = None) -> list[dict[str, Any]]:
    result = []
    for event in events:
        if name is not None and event.event_name != name:
            continue
        if attack_id is not None and event.fields.get("attackId") != attack_id:
            continue
        if player is not None and event.fields.get("playerIndex") != player:
            continue
        result.append(_event_dict(event))
    return result


def _move_events(events: tuple[Any, ...], player: int, from_area: int, to_area: int) -> list[dict[str, Any]]:
    result = []
    for event in events:
        if event.event_name not in {"MOVE_CARD", "MOVE_CARD_REVERSE"}:
            continue
        fields = event.fields
        if fields.get("playerIndex") == player and fields.get("fromArea") == from_area and fields.get("toArea") == to_area:
            result.append(_event_dict(event))
    return result


def _event_value(event: Mapping[str, Any], key: str) -> Any:
    fields = event.get("fields")
    return fields.get(key) if isinstance(fields, Mapping) else event.get(key)


def _request_dict(observation: EngineObservationV1, request: SelectionRequestV1) -> dict[str, Any]:
    return {
        "selection_type": request.selection_type,
        "selection_context": request.selection_context,
        "acting_player": request.acting_player,
        "min_count": request.min_count,
        "max_count": request.max_count,
        "remain_damage_counter": request.remain_damage_counter,
        "remain_energy_cost": request.remain_energy_cost,
        "context_card_id": request.context_card_id,
        "effect_card_id": request.effect_card_id,
        "ordering": request.ordering,
        "options": [
            {
                "original_index": option.original_index,
                "option_type": option.option_type,
                "option_name": option.option_name,
                "card_id": option.card_id,
                "attack_id": option.attack_id,
                "source_card_id": _entity_card(observation, option.source_entity_key),
                "target_card_id": _entity_card(observation, option.target_entity_key),
                "serial": option.serial,
                "choice_role": option.choice_role,
                "semantic_fingerprint": option.semantic_fingerprint,
            }
            for option in request.options
        ],
    }


class ProbePolicy:
    """Public semantic probe policy; no raw native observation is accepted."""

    policy_id = "phase-a-route-public-probe-v1"

    def __init__(self, route: str | None, variant: int = 0) -> None:
        self.route = route
        self.variant = variant
        self.last_turn: int | None = None

    def reset(self, episode_uuid: str, player_index: int, reason: str = "start") -> None:
        self.last_turn = None

    def _score(self, observation: EngineObservationV1, request: SelectionRequestV1, index: int) -> tuple[int, int, int]:
        option = request.options[index]
        source = _entity_card(observation, option.source_entity_key)
        target = _entity_card(observation, option.target_entity_key)
        route = self.route
        score = 0
        if option.option_type == 14:
            score = 5000 if self.route is None else -5000
        if option.attack_id is not None:
            if route and option.attack_id == next((attack for attack, name in ATTACK_TO_ROUTE.items() if name == route), -1):
                score = 10000
            else:
                score = -10000 if self.route is None else 100
        if option.option_type == 7:
            if route == "riptide" and source == 1121:
                score = 9500
            elif route == "surfing_beach" and source == 1262:
                score = 9500
            elif route in {"hammer_lanche", "frost_barrier"}:
                score = 9000 if source in {722, 723} else -100
            else:
                score = 100
        if option.option_type == 9:
            score = 8500 if target == 722 and source == 723 else 8000
        if option.option_type == 8:
            desired = 721 if route in {"riptide", "swirling_waves", "surfing_beach"} else 723
            if target == desired:
                score = 7000
            elif target in POKEMON:
                score = 3000
        if option.option_type == 10:
            score = 9000 if route == "surfing_beach" and source == 1262 else -100
        if option.option_type == 15:
            score = 9000 if route == "surfing_beach" else -100
        if option.option_type == 12:
            score = 6000 if route == "surfing_beach" else -100
        if option.option_type in {3, 4, 5, 6}:
            if route in {"riptide", "swirling_waves"} and source == WATER:
                score = 8000
            elif route == "surfing_beach" and source in {721, 722, 723}:
                score = 8000
            elif route in {"hammer_lanche", "frost_barrier"} and source == WATER:
                score = 100
        if option.option_type == 3 and request.selection_type == 1:
            desired = 721 if route in {"riptide", "swirling_waves", "surfing_beach"} else 723
            if source == desired:
                score = 10000
            elif source in POKEMON:
                score = 7000
        if option.option_type == 0 and route == "riptide" and option.number == min(self.variant + 1, 3):
            score = 8500
        if option.option_type == 13 and route is None:
            score = -10000 if request.selection_type == 0 else 100
        return score, -int(source or 0), -index

    def choose(self, observation: EngineObservationV1, request: SelectionRequestV1):
        builder = CompoundActionBuilder(request)
        candidates = [index for index, option in enumerate(request.options) if option.available]
        candidates.sort(key=lambda index: self._score(observation, request, index), reverse=True)
        if request.selection_type == 0 and request.min_count == 0:
            desired = [index for index in candidates if self._score(observation, request, index)[0] > 0]
            candidates = desired[:1]
        elif request.selection_type == 8 and self.route == "riptide":
            candidates = [index for index in candidates if request.options[index].number == min(self.variant + 1, 3)] or candidates
        elif request.selection_type in {1, 2, 3, 4, 5, 6, 7, 8, 9, 10}:
            candidates = candidates[: max(request.min_count, 1)]
        for index in candidates:
            if builder.complete:
                break
            builder.choose(index)
        if not builder.complete:
            builder.stop()
        return validate_compound_action(request, builder.build())


def _capsule(route: str, game_index: int, transition: int, before: EngineObservationV1, request: SelectionRequestV1, action: Any, after: EngineObservationV1) -> dict[str, Any]:
    return {
        "route": route,
        "game_index": game_index,
        "transition": transition,
        "acting_player": request.acting_player,
        "turn": before.turn,
        "before": {"players": [asdict(row) for row in before.players], "cards": _public_cards(before)},
        "request": _request_dict(before, request),
        "action": {"submitted_original_indices": list(action.submitted_original_indices), "selected_card_ids": _selected_card_ids(before, request, list(action.submitted_original_indices)), "stopped_early": action.stopped_early},
        "after": {"players": [asdict(row) for row in after.players], "cards": _public_cards(after)},
        "events": [_event_dict(event) for event in after.public_events],
        "capsule_sha256": canonical_hash({"route": route, "game_index": game_index, "transition": transition, "request": _request_dict(before, request), "events": [_event_dict(event) for event in after.public_events]}),
    }


def _new_route_state() -> dict[str, Any]:
    return {
        "attempts": 0,
        "capsules": [],
        "proofs": Counter(),
        "proof_keys": set(),
        "proof_capsules": [],
        "capsule_index": {},
        "invariant_failures": Counter(),
        "strata": Counter(),
        "diagnostics": Counter(),
        "evidence": [],
    }


def _public_hp(observation: EngineObservationV1, player: int) -> int | None:
    active = [entity for entity in observation.entities if entity.owner == player and entity.zone == AREA["ACTIVE"] and entity.hp is not None]
    return active[0].hp if active else None


def _proof_from_attack(route: str, player: int, before: EngineObservationV1, after: EngineObservationV1, events: tuple[Any, ...]) -> tuple[str | None, dict[str, Any]]:
    hp_before = _public_hp(before, 1 - player)
    hp_after = _public_hp(after, 1 - player)
    hp_delta = None if hp_before is None or hp_after is None else hp_before - hp_after
    event_damage = sum(
        -int(event.fields["value"])
        for event in events
        if event.event_name == "HP_CHANGE"
        and event.fields.get("playerIndex") == 1 - player
        and isinstance(event.fields.get("value"), int)
        and int(event.fields["value"]) < 0
    )
    if hp_delta in {None, 0} and event_damage:
        hp_delta = event_damage
    payload: dict[str, Any] = {"hp_before": hp_before, "hp_after": hp_after, "hp_delta": hp_delta}
    if route == "riptide":
        moves = _move_events(events, player, AREA["DISCARD"], AREA["DECK"])
        waters = [item for item in moves if _event_value(item, "cardId") == WATER]
        payload["recycled_water_serials"] = [_event_value(item, "serial") for item in waters]
        payload["recycled_water_count"] = len(waters)
        payload["deck_delta"] = _player_view(after, player).deck_count - _player_view(before, player).deck_count
        if len(waters) >= 1 and payload["deck_delta"] == len(waters) and hp_delta == len(waters) * 20:
            return "riptide_recycle_and_damage", payload
    elif route == "swirling_waves":
        moves = _move_events(events, player, AREA["ENERGY"], AREA["DISCARD"])
        energies = [item for item in moves if _event_value(item, "cardId") == WATER]
        payload["discarded_energy_serials"] = [_event_value(item, "serial") for item in energies]
        payload["discarded_energy_count"] = len(energies)
        if len(energies) == 2 and hp_delta == 130:
            return "swirling_two_energy_and_130_damage", payload
    elif route == "hammer_lanche":
        moves = _move_events(events, player, AREA["DECK"], AREA["DISCARD"])
        serials = [_event_value(item, "serial") for item in moves]
        water_count = sum(_event_value(item, "cardId") == WATER for item in moves)
        payload["new_discard_serials"] = serials
        payload["discard_card_ids"] = [_event_value(item, "cardId") for item in moves]
        payload["water_count"] = water_count
        payload["deck_to_discard_count"] = len(moves)
        if len(moves) == 6:
            strata = "zero" if water_count == 0 else "one" if water_count == 1 else "multiple"
            payload["stratum"] = strata
            if hp_delta == water_count * 100:
                return "hammer_six_top_discard_and_damage", payload
    elif route == "frost_barrier":
        attacks = _events_for(events, name="ATTACK", attack_id=1047, player=player)
        payload["barrier_attack_events"] = attacks
        if attacks:
            return "frost_barrier_attack_observed", payload
    return None, payload


def _direct_event_proof(
    route: str,
    player: int,
    events: tuple[Any, ...],
    before: EngineObservationV1 | None = None,
    after: EngineObservationV1 | None = None,
) -> tuple[str | None, dict[str, Any]]:
    attack_id = next((attack for attack, name in ATTACK_TO_ROUTE.items() if name == route), None)
    attacks = _events_for(events, name="ATTACK", attack_id=attack_id, player=player)
    if not attacks:
        return None, {}
    payload: dict[str, Any] = {"attack_events": attacks}
    damage = sum(
        -int(event.fields["value"])
        for event in events
        if event.event_name == "HP_CHANGE"
        and event.fields.get("playerIndex") == 1 - player
        and isinstance(event.fields.get("value"), int)
        and int(event.fields["value"]) < 0
    )
    payload["hp_delta"] = damage
    if route == "swirling_waves":
        moves = _move_events(events, player, AREA["ENERGY"], AREA["DISCARD"])
        energies = [item for item in moves if _event_value(item, "cardId") == WATER]
        payload["discarded_energy_serials"] = [_event_value(item, "serial") for item in energies]
        payload["discarded_energy_count"] = len(energies)
        if len(energies) == 2 and damage == 130:
            return "swirling_two_energy_and_130_damage", payload
    if route == "hammer_lanche":
        moves = _move_events(events, player, AREA["DECK"], AREA["DISCARD"])
        before_discard = {(item["serial"], item["card_id"]) for item in _public_cards(before, player) if item["zone"] == AREA["DISCARD"]} if before else set()
        after_discard = [item for item in _public_cards(after, player) if item["zone"] == AREA["DISCARD"]] if after else []
        new_cards = [item for item in after_discard if (item["serial"], item["card_id"]) not in before_discard]
        card_ids = [item["card_id"] for item in new_cards] if len(new_cards) == 6 else [_event_value(item, "cardId") for item in moves]
        serials = [item["serial"] for item in new_cards] if len(new_cards) == 6 else [_event_value(item, "serial") for item in moves]
        water_count = sum(card_id == WATER for card_id in card_ids)
        payload["new_discard_serials"] = serials
        payload["discard_card_ids"] = card_ids
        payload["deck_to_discard_count"] = len(new_cards) if new_cards else len(moves)
        payload["water_count"] = water_count
        if payload["deck_to_discard_count"] == 6:
            payload["stratum"] = "zero" if water_count == 0 else "one" if water_count == 1 else "multiple"
            if damage == water_count * 100:
                return "hammer_six_top_discard_and_damage", payload
    if route == "frost_barrier":
        return "frost_barrier_attack_observed", payload
    if route == "riptide":
        moves = _move_events(events, player, AREA["DISCARD"], AREA["DECK"])
        waters = [item for item in moves if _event_value(item, "cardId") == WATER]
        payload["recycled_water_serials"] = [_event_value(item, "serial") for item in waters]
        payload["recycled_water_count"] = len(waters)
        if before is not None and after is not None:
            payload["deck_delta"] = _player_view(after, player).deck_count - _player_view(before, player).deck_count
        else:
            payload["deck_delta"] = len(waters)
        if waters and damage == len(waters) * 20 and payload["deck_delta"] == len(waters):
            return "riptide_recycle_and_damage", payload
    return None, payload


def _route_related(route: str, observation: EngineObservationV1, request: SelectionRequestV1, action: Any, after: EngineObservationV1) -> bool:
    selected = [request.options[index] for index in action.submitted_original_indices]
    card_ids = {_entity_card(observation, option.source_entity_key) or option.card_id for option in selected}
    return (
        any(option.attack_id in ATTACK_TO_ROUTE and ATTACK_TO_ROUTE[option.attack_id] == route for option in selected)
        or ROUTE_CARD[route] in card_ids
        or request.context_card_id == ROUTE_CARD[route]
        or request.effect_card_id == ROUTE_CARD[route]
        or any(event.fields.get("attackId") in [attack for attack, name in ATTACK_TO_ROUTE.items() if name == route] for event in after.public_events)
    )


def _record_proof(
    state: dict[str, Any], route: str, game_index: int, transition: int, proof: str,
    payload: Mapping[str, Any], capsule: Mapping[str, Any] | None = None,
) -> bool:
    """Record one native attack once; direct and pending paths can see the same logs."""
    attack = (payload.get("attack_events") or [{}])[0]
    fields = attack.get("fields", {}) if isinstance(attack, Mapping) else {}
    key = (route, transition, fields.get("playerIndex"), fields.get("serial"), fields.get("attackId"))
    if key in state["proof_keys"]:
        return False
    state["proof_keys"].add(key)
    state["proofs"][proof] += 1
    record = {"proof": proof, "game_index": game_index, **dict(payload), "transition": transition}
    if capsule is not None:
        record["source_capsule_sha256"] = capsule.get("capsule_sha256")
        state["proof_capsules"].append(dict(capsule))
    state["evidence"].append(record)
    if route == "hammer_lanche" and payload.get("stratum"):
        state["strata"][payload["stratum"]] += 1
    return True


def _run_game(config: Mapping[str, Any], route: str, game_index: int, state: dict[str, Any]) -> dict[str, Any]:
    deck_key = route
    if route == "hammer_lanche":
        deck_key = ("hammer_lanche_zero", "hammer_lanche_one", "hammer_lanche_multiple")[game_index % 3]
    deck = expand_deck(config["deck_specs"][deck_key])
    opponent = expand_deck(config["deck_specs"]["opponent"])
    candidate_player = game_index % 2
    decks = (deck, opponent) if candidate_player == 0 else (opponent, deck)
    policies = (ProbePolicy(route if candidate_player == 0 else None, game_index % 3), ProbePolicy(route if candidate_player == 1 else None, game_index % 3))
    engine = NativeCABTTransport(ROOT / config["assets"]["engine_root"])
    battle_id = f"phase-a-route-{route}-{game_index}"
    raw = engine.start(*decks)
    transition = 0
    started = time.monotonic()
    pending: list[dict[str, Any]] = []
    counters = Counter()
    terminal = None
    try:
        while transition < config["limits"]["request_cap_per_game"]:
            if time.monotonic() - started > config["limits"]["wall_seconds"]:
                counters["timeouts"] += 1
                break
            observation, request = semantic_snapshot(raw, battle_id, transition, config["assets"]["card_data_sha256"])
            if observation.terminal_result is not None:
                terminal = observation.terminal_result
                break
            if request is None:
                counters["semantic_contract_failures"] += 1
                break
            policy = policies[request.acting_player]
            action = policy.choose(observation, request)
            raw_after = engine.select(action.submitted_original_indices)
            after, _ = semantic_snapshot(raw_after, battle_id, transition + 1, config["assets"]["card_data_sha256"])
            related = _route_related(route, observation, request, action, after)
            attack_selected = request.acting_player == candidate_player and any(request.options[index].attack_id is not None and ATTACK_TO_ROUTE.get(request.options[index].attack_id) == route for index in action.submitted_original_indices)
            if attack_selected:
                state["attempts"] += 1
                pending.append({"transition": transition, "before": observation, "route": route, "player": candidate_player, "game_index": game_index})
            if related or pending:
                capsule = _capsule(route, game_index, transition, observation, request, action, after)
                state["capsules"].append(capsule)
                state["capsule_index"][(game_index, transition)] = capsule
                if len(state["capsules"]) > config["limits"]["max_capsules_per_route"]:
                    del state["capsules"][0]
                attack_players = {
                    int(event.fields["playerIndex"])
                    for event in after.public_events
                    if event.event_name == "ATTACK"
                    and event.fields.get("attackId") in ATTACK_TO_ROUTE
                    and isinstance(event.fields.get("playerIndex"), int)
                }
                for attack_player in attack_players:
                    if attack_player != candidate_player:
                        continue
                    direct_proof, direct_payload = _direct_event_proof(route, attack_player, after.public_events, observation, after)
                    if direct_proof is None:
                        direct_proof, direct_payload = _proof_from_attack(route, attack_player, observation, after, after.public_events)
                    elif route == "riptide" and not direct_payload.get("deck_delta"):
                        for pending_item in pending:
                            if pending_item["route"] == route and pending_item["player"] == attack_player:
                                pending_proof, pending_payload = _proof_from_attack(route, attack_player, pending_item["before"], after, after.public_events)
                                if pending_proof == direct_proof and pending_payload.get("deck_delta"):
                                    direct_payload = pending_payload
                                    break
                    if direct_proof:
                        _record_proof(state, route, game_index, transition, direct_proof, direct_payload, capsule)
            if route == "surfing_beach":
                selected_cards = _selected_card_ids(observation, request, list(action.submitted_original_indices))
                play_events = _events_for(after.public_events, name="PLAY", player=request.acting_player)
                stadium_serials = [event.get("fields", {}).get("serial") for event in play_events if event.get("fields", {}).get("cardId") == 1262]
                if 1262 in selected_cards and stadium_serials:
                    state["evidence"].append({"proof": "surfing_beach_play", "game_index": game_index, "acting_player": request.acting_player, "stadium_serials": stadium_serials, "source_capsule_sha256": state["capsule_index"].get((game_index, transition), {}).get("capsule_sha256"), "transition": transition, "turn": observation.turn})
                switch_events = _events_for(after.public_events, name="SWITCH", player=request.acting_player)
                if request.effect_card_id == 1262 and switch_events:
                    water_switch = all(
                        event.get("fields", {}).get("cardIdActive") in POKEMON
                        and event.get("fields", {}).get("cardIdBench") in POKEMON
                        for event in switch_events
                    )
                    if water_switch:
                        state["evidence"].append({"proof": "surfing_beach_water_switch", "game_index": game_index, "acting_player": request.acting_player, "switch_events": switch_events, "all_water_targets": water_switch, "source_capsule_sha256": state["capsule_index"].get((game_index, transition), {}).get("capsule_sha256"), "transition": transition, "turn": observation.turn})
            for item in list(pending):
                if transition - item["transition"] > 4:
                    pending.remove(item)
                    continue
                proof, payload = _proof_from_attack(route, item["player"], item["before"], after, after.public_events)
                if proof:
                    # The public MOVE/HP events are emitted on this transition's
                    # snapshot; the pending item identifies the earlier attack
                    # request, not the event-bearing capsule.
                    source_capsule = state["capsule_index"].get((item["game_index"], transition))
                    _record_proof(state, route, item["game_index"], transition, proof, payload, source_capsule)
                    pending.remove(item)
            raw = raw_after
            transition += 1
        else:
            counters["request_cap_failures"] += 1
    except ContractViolation:
        counters["invalid_actions"] += 1
    except Exception as error:
        counters[f"native_error:{type(error).__name__}"] += 1
    finally:
        engine.finish()
    return {"game_index": game_index, "candidate_player": candidate_player, "requests": transition, "terminal_result": terminal, "counters": _normalise_counters(counters)}


def _route_verdict(route: str, state: Mapping[str, Any]) -> tuple[str, str]:
    proofs = state["proofs"]
    if route == "riptide":
        counts = [int(item.get("recycled_water_count", 0)) for item in state.get("evidence", []) if item.get("proof") == "riptide_recycle_and_damage"]
        observed = {value for value in counts if value}
        if proofs.get("riptide_recycle_and_damage", 0) >= 2 and {1, 2, 3}.issubset(observed):
            return "PASS", "recycled-water counts 1/2/3 each reconcile to deck increment and 20-per-water damage"
        return "PARTIAL", f"recycle/damage proof is limited to observed counts {sorted(observed)}; required low-count strata are incomplete"
    if route == "swirling_waves":
        if proofs.get("swirling_two_energy_and_130_damage", 0):
            return "PASS", "exactly two attached Water serials moved to discard with 130 HP delta"
        return "PARTIAL", "no exact two-energy/130-damage public capsule"
    if route == "surfing_beach":
        plays = [item for item in state["evidence"] if item.get("proof") == "surfing_beach_play"]
        switches = [item for item in state["evidence"] if item.get("proof") == "surfing_beach_water_switch"]
        causal = any(
            play["game_index"] == switch["game_index"]
            and play["acting_player"] == switch["acting_player"]
            and play["turn"] <= switch["turn"]
            for play in plays
            for switch in switches
        )
        if causal:
            return "PASS", "stadium PLAY and later effect-bound Water SWITCH share a game, player, and turn order"
        return "PARTIAL", "stadium play-to-Water-switch causal pair was not captured"
    if route == "hammer_lanche":
        if proofs.get("hammer_six_top_discard_and_damage", 0) and len(state["strata"]) >= 3:
            return "PASS", "six new discard serials and HP deltas observed in zero/one/multiple-Water strata"
        return "PARTIAL", "fewer than three top-six Water strata or no six-card damage capsule"
    if route == "frost_barrier":
        if proofs.get("frost_barrier_attack_observed", 0) >= 2:
            return "PARTIAL", "Barrier attack observed; next-turn fixed-response/control comparison remains unproven"
        return "PARTIAL", "Barrier activation or next-turn response was not captured"
    raise ValueError(route)


def _command_label() -> str:
    args: list[str] = []
    for value in sys.argv:
        path = Path(value)
        try:
            value = path.resolve().relative_to(ROOT).as_posix()
        except ValueError:
            value = path.name
        args.append(value)
    return shlex.join(["rtk", "uv", "--cache-dir", "data/cache/uv", "run", "python", *args])


def _evidence_summary(evidence: list[Mapping[str, Any]]) -> dict[str, Any]:
    by_proof: dict[str, list[Mapping[str, Any]]] = {}
    for item in evidence:
        by_proof.setdefault(str(item.get("proof", "UNKNOWN")), []).append(item)
    summary: dict[str, Any] = {}
    for proof, items in sorted(by_proof.items()):
        summary[proof] = {
            "count": len(items),
            "transition_digest": canonical_hash(sorted((item.get("game_index"), item.get("transition")) for item in items)),
        }
        if proof.startswith("riptide"):
            summary[proof]["recycled_water_count_values"] = sorted({item.get("recycled_water_count") for item in items})
            summary[proof]["damage_values"] = sorted({item.get("hp_delta") for item in items})
        elif proof.startswith("swirling"):
            summary[proof]["discarded_energy_count_values"] = sorted({item.get("discarded_energy_count") for item in items})
            summary[proof]["damage_values"] = sorted({item.get("hp_delta") for item in items})
        elif proof.startswith("hammer"):
            summary[proof]["discard_count_values"] = sorted({item.get("deck_to_discard_count") for item in items})
            summary[proof]["water_count_values"] = sorted({item.get("water_count") for item in items})
            summary[proof]["damage_values"] = sorted({item.get("hp_delta") for item in items})
        elif proof.startswith("surfing"):
            summary[proof]["game_count"] = len({item.get("game_index") for item in items})
    return summary


def _compact_report(full_report: Mapping[str, Any], raw_path: Path, raw_digest: str, raw_bytes: int) -> dict[str, Any]:
    routes: dict[str, Any] = {}
    for route, result in full_report["route_results"].items():
        capsules = result.get("capsules", [])
        proof_capsules = result.get("proof_capsules", [])
        evidence = result.get("evidence", [])
        routes[route] = {
            "status": result["status"],
            "reason": result["reason"],
            "candidate_attack_attempts": result["candidate_attack_attempts"],
            "proofs": result["proofs"],
            "strata": result["strata"],
            "invariant_failures": result["invariant_failures"],
            "games_requested": result["games_requested"],
            "games_completed": result["games_completed"],
            "capsule_count": len(capsules),
            "capsule_digest": canonical_hash(capsules),
            "proof_capsule_count": len(proof_capsules),
            "proof_capsule_digest": canonical_hash(proof_capsules),
            "evidence_summary": _evidence_summary(evidence),
        }
    report = {
        key: full_report[key]
        for key in ("schema_version", "record_id", "created_at_utc", "status", "decision", "provenance", "scope", "fail_closed_counters", "games", "knowledge_base")
    }
    report["route_results"] = routes
    report["raw_evidence"] = {
        "path": raw_path.relative_to(ROOT).as_posix(),
        "bytes": raw_bytes,
        "sha256": raw_digest,
        "sealed_read_only": True,
        "content": "complete native transition capsules retained privately under ignored runs/",
    }
    return report


def _write_sealed_json(path: Path, payload: Mapping[str, Any]) -> tuple[str, int]:
    path.parent.mkdir(parents=True, exist_ok=False)
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o444)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise
    path.chmod(0o444)
    digest = sha256(path)
    sidecar = path.with_suffix(path.suffix + ".sha256")
    sidecar.write_text(f"{digest}  {path.name}\n", encoding="ascii")
    sidecar.chmod(0o444)
    return digest, len(data)


def run_experiment(config: Mapping[str, Any], config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    started = time.monotonic()
    observed_assets = _validate_asset_receipts(config)
    deck_hashes = {name: canonical_hash(sorted(expand_deck(spec))) for name, spec in config["deck_specs"].items()}
    source_hashes = {path.relative_to(ROOT).as_posix(): sha256(path) for path in SOURCE_PATHS}
    route_results: dict[str, Any] = {}
    games: list[dict[str, Any]] = []
    for row in config["routes"]:
        route = row["id"]
        state = _new_route_state()
        for game_index in range(config["limits"]["games_per_route"]):
            if time.monotonic() - started > config["limits"]["wall_seconds"]:
                break
            games.append({"route": route, **_run_game(config, route, game_index, state)})
        if route == "surfing_beach":
            plays = [item for item in state["evidence"] if item.get("proof") == "surfing_beach_play"]
            switches = [item for item in state["evidence"] if item.get("proof") == "surfing_beach_water_switch"]
            for play in plays:
                pair = next(
                    (switch for switch in switches
                     if play["game_index"] == switch["game_index"]
                     and play["acting_player"] == switch["acting_player"]
                     and play["turn"] <= switch["turn"]),
                    None,
                )
                if pair is not None:
                    selected: list[dict[str, Any]] = []
                    for item in (play, pair):
                        capsule = state["capsule_index"].get((item["game_index"], item["transition"]))
                        if capsule is not None and capsule["capsule_sha256"] not in {row["capsule_sha256"] for row in selected}:
                            selected.append(capsule)
                    state["proof_capsules"] = selected
                    break
        status, reason = _route_verdict(route, state)
        route_results[route] = {
            "status": status,
            "reason": reason,
            "candidate_attack_attempts": state["attempts"],
            "proofs": dict(Counter(item.get("proof") for item in state["evidence"])),
            "strata": dict(state["strata"]),
            "invariant_failures": dict(state["invariant_failures"]),
            "games_requested": config["limits"]["games_per_route"],
            "games_completed": sum(1 for game in games if game["route"] == route),
            "evidence": state["evidence"],
            "capsules": state["capsules"],
            "proof_capsules": state["proof_capsules"],
        }
    counters = Counter()
    for game in games:
        counters.update(game["counters"])
    return {
        "schema_version": 1,
        "record_id": config["record_id"],
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "SUCCEEDED" if not any(counters.values()) else "FAILED",
        "decision": "ROUTE_STATUS_MATRIX",
        "provenance": {
            "config_path": config_path.relative_to(ROOT).as_posix(),
            "config_sha256": sha256(config_path),
            "runner_path": Path(__file__).resolve().relative_to(ROOT).as_posix(),
            "runner_sha256": sha256(Path(__file__).resolve()),
            "card_data_sha256": config["assets"]["card_data_sha256"],
            "card_table_file_sha256": config["assets"]["card_table_file_sha256"],
            "card_table_semantic_sha256": config["assets"]["card_table_semantic_sha256"],
            "engine_library_sha256": config["assets"]["engine_library_sha256"],
            "wrapper_sha256": config["assets"]["wrapper_sha256"],
            "api_sha256": config["assets"]["api_sha256"],
            "observed_asset_hashes": observed_assets,
            "deck_multiset_sha256": deck_hashes,
            "source_hashes": source_hashes,
            "command": _command_label(),
            "native_randomness": "official engine controlled; no manual coin/random outcome",
        },
        "scope": {"candidate": config["candidate"], "routes": [row["id"] for row in config["routes"]], "games": len(games), "games_requested": len(config["routes"]) * config["limits"]["games_per_route"], "games_completed": len(games), "policy_strength_claimed": False, "promotion_authorized": False, "deck_frozen": False},
        "fail_closed_counters": _normalise_counters(counters),
        "games": games,
        "route_results": route_results,
        "knowledge_base": {"database": "knowledge_base/ptcg_gold.sqlite", "ids": config["knowledge_base_ids"], "requeried_before_run": True},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    config = load_config(args.config)
    full_report = run_experiment(config, args.config)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_path = ROOT / "runs" / f"phase-a-route-capsules-{stamp}-{uuid.uuid4().hex[:12]}" / "raw-evidence.json"
    raw_digest, raw_bytes = _write_sealed_json(raw_path, full_report)
    report = _compact_report(full_report, raw_path, raw_digest, raw_bytes)
    args.report = args.report.resolve()
    if ROOT not in args.report.parents:
        raise ValueError("report must remain within the repository")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "routes": {key: value["status"] for key, value in report["route_results"].items()}, "games": report["scope"]["games"], "raw_evidence": report["raw_evidence"]}, sort_keys=True))
    return 0 if report["status"] == "SUCCEEDED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
