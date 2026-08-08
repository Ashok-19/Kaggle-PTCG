"""Bounded native capability capsules for the restricted Phase B1 oracle.

This experiment is deliberately separate from ``PolicyV1``.  It uses only the
semantic public observation/request boundary and legal selections.  The native
engine supplies shuffle, coin, and Prize placement entropy; this runner never
sets a seed, rearranges a deck, mutates HP/status/energy, or imports a private
baseline.  A capability is PASS only when the claimed public transition is
observed with the exact version-bound assets and zero reliability failures.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
import uuid
from collections import Counter, deque
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ptcg_rl.g1.actions import CompoundActionBuilder, validate_compound_action  # noqa: E402
from ptcg_rl.g1.models import ContractViolation, EngineObservationV1, SelectionRequestV1  # noqa: E402
from ptcg_rl.g1.native import NativeCABTTransport  # noqa: E402
from ptcg_rl.g1.semantic import AREA, semantic_snapshot  # noqa: E402
from scripts.deterministic.phase_a_route_capsules_v1 import ProbePolicy as RouteProbePolicy  # noqa: E402


DEFAULT_CONFIG = ROOT / "configs/deterministic/phase_a_b1_capability_capsules_v1.json"
DEFAULT_REPORT = ROOT / "reports/deterministic/phase-a-b1-capability-capsules-v1.json"
RELIABILITY_COUNTER_KEYS = (
    "invalid_actions", "semantic_contract_failures", "request_cap_failures", "timeouts",
    "native_errors", "fallbacks", "post_terminal_actions", "unclassified_terminal",
    "incomplete_games", "other_failures", "ambiguous_prize_pairings",
)
POKEMON = {721, 722, 723, 754}
TARGET_PRIZE_CLASSES = (721, 722, 723, 754)
ATTACK_IDS = (1044, 1045)
EXPECTED_PRIZE_DELTAS = {721: 1, 722: 1, 723: 3, 754: 3}

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
    ROOT / "scripts/deterministic/phase_a_route_capsules_v1.py",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def expand_deck(spec: Mapping[str, int]) -> list[int]:
    deck: list[int] = []
    for card_id, count in sorted(spec.items(), key=lambda item: int(item[0])):
        deck.extend([int(card_id)] * int(count))
    if len(deck) != 60:
        raise ValueError("expanded deck is not exactly 60 cards")
    return deck


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "schema_version", "record_id", "scope", "knowledge_base_ids", "candidate_deck",
        "engine_root", "assets", "formulations", "attack_contract", "evolution_contract",
        "prize_contract", "deck_specs", "limits", "raw_evidence",
    }
    if set(value) != expected or value["schema_version"] != 1 or value["record_id"] != "phase-a-b1-capability-capsules-v1":
        raise ValueError("capability config identity/keys differ")
    required_kb = ["DR-004", "DR-005", "DR-006", "DR-025", "DR-030", "DR-033", "AP-014", "RQ-004", "RQ-005", "RQ-007"]
    if value["knowledge_base_ids"] != required_kb:
        raise ValueError("capability knowledge-base binding differs")
    if [row["id"] for row in value["formulations"]] != [
        "snover_1044_first", "snover_1045_first", "snover_to_mega_evolution", "prize_route_targets"
    ]:
        raise ValueError("capability formulations differ")
    for key in ASSET_PATHS:
        if not isinstance(value["assets"].get(key), str) or len(value["assets"][key]) != 64:
            raise ValueError(f"invalid asset receipt {key}")
    if value["attack_contract"] != {
        "card_id": 722,
        "attack_ids": [1044, 1045],
        "energy_type": 3,
        "energy_counts": {"1044": 1, "1045": 2},
        "damage": {"1044": 10, "1045": 30},
        "target_zone": "ACTIVE",
        "allowed_event_names": ["ATTACK", "HP_CHANGE"],
    }:
        raise ValueError("Snover attack contract differs")
    evolution = value["evolution_contract"]
    if evolution["source_card_id"] != 722 or evolution["target_card_id"] != 723 or evolution["option_type"] != 9:
        raise ValueError("evolution contract differs")
    prize = value["prize_contract"]
    if prize["target_card_ids"] != list(TARGET_PRIZE_CLASSES) or not prize["unknown_if_unobserved"]:
        raise ValueError("Prize contract differs")
    if value["limits"]["request_cap_per_game"] > 1200 or value["limits"]["wall_seconds"] > 600:
        raise ValueError("capability bounds exceed reviewed ceiling")
    for name, spec in value["deck_specs"].items():
        if sum(int(count) for count in spec.values()) != 60:
            raise ValueError(f"{name} deck is not exactly 60 cards")
        if any(int(card_id) != 3 and int(count) > 4 for card_id, count in spec.items()):
            raise ValueError(f"{name} deck exceeds four-copy same-name limit")
        if not any(int(card_id) not in {3} for card_id in spec):
            raise ValueError(f"{name} deck has no Basic Pokemon")
    return value


def validate_assets(config: Mapping[str, Any], config_path: Path) -> dict[str, str]:
    observed: dict[str, str] = {}
    for key, path in ASSET_PATHS.items():
        if not path.is_file():
            raise FileNotFoundError(path)
        observed[key] = sha256(path)
        if observed[key] != config["assets"][key]:
            raise ValueError(f"asset hash mismatch for {key}: {observed[key]}")
    table = json.loads(ASSET_PATHS["card_table_file_sha256"].read_text(encoding="utf-8"))
    if table.get("table_sha256") != config["assets"]["card_table_semantic_sha256"]:
        raise ValueError("card table semantic receipt mismatch")
    cards = {int(row["card_id"]): row for row in table["cards"]}
    attacks = {int(row["attack_id"]): row for row in table["attacks"]}
    if cards[722]["attack_ids"] != [1044, 1045]:
        raise ValueError("card table Snover attack identity changed")
    for attack_id, expected_damage, expected_water in ((1044, 10, 1), (1045, 30, 2)):
        attack = attacks[attack_id]
        if attack["damage"] != expected_damage or attack["energy_counts"][3] != expected_water or sum(attack["energy_counts"]) != expected_water:
            raise ValueError(f"card table attack {attack_id} static contract changed")
    with ASSET_PATHS["card_data_sha256"].open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    expected_rows = {
        1044: ("Snover", "Beat", "{W}", "10"),
        1045: ("Snover", "Icy Snow", "{W}{W}", "30"),
    }
    for attack_id, (name, move, cost, damage) in expected_rows.items():
        matches = [row for row in rows if row["Card ID"] == "722" and row["Card Name"] == name and row["Move Name"] == move]
        if len(matches) != 1 or matches[0]["Cost"] != cost or matches[0]["Damage"] != damage:
            raise ValueError(f"card data attack {attack_id} static contract changed")
    if config_path.resolve() == (ROOT / "configs/deterministic/phase_a_b1_capability_capsules_v1.json").resolve():
        observed["config_sha256"] = sha256(config_path)
    return observed


def _normalise_counters(counter: Mapping[str, int]) -> dict[str, int]:
    result = {key: int(counter.get(key, 0)) for key in RELIABILITY_COUNTER_KEYS}
    result["native_errors"] = int(counter.get("native_errors", 0)) + sum(
        int(value) for key, value in counter.items() if key.startswith("native_error:")
    )
    known = set(RELIABILITY_COUNTER_KEYS) | {key for key in counter if key.startswith("native_error:")}
    result["other_failures"] = sum(int(value) for key, value in counter.items() if key not in known)
    return result


def _entity(observation: EngineObservationV1, key: str | None) -> Any | None:
    if key is None:
        return None
    return next((item for item in observation.entities if item.entity_key == key), None)


def _card(observation: EngineObservationV1, option: Any, source: bool = True) -> int | None:
    key = option.source_entity_key if source else option.target_entity_key
    entity = _entity(observation, key)
    return entity.card_id if entity is not None else (option.card_id if source else None)


def _active(observation: EngineObservationV1, player: int) -> Any | None:
    return next((entity for entity in observation.entities if entity.owner == player and entity.zone == AREA["ACTIVE"] and entity.position == 0), None)


def _hand_card_ids(observation: EngineObservationV1, player: int) -> set[int]:
    return {int(entity.card_id) for entity in observation.entities if entity.owner == player and entity.zone == AREA["HAND"] and entity.card_id is not None}


def _public_cards(observation: EngineObservationV1) -> list[dict[str, Any]]:
    return [
        {
            "entity_key": entity.entity_key, "card_id": entity.card_id, "serial": entity.serial,
            "owner": entity.owner, "zone": entity.zone, "position": entity.position,
            "parent_entity_key": entity.parent_entity_key, "hp": entity.hp, "max_hp": entity.max_hp,
            "damage": entity.damage, "energy_types": list(entity.energy_types),
            "attached_energy_count": entity.attached_energy_count, "statuses": list(entity.statuses),
        }
        for entity in observation.entities if entity.card_id is not None
    ]


def _event_dict(event: Any) -> dict[str, Any]:
    result = {key: item for key, item in asdict(event).items() if item is not None}
    result["event_name"] = event.event_name
    return result


def _request_dict(observation: EngineObservationV1, request: SelectionRequestV1) -> dict[str, Any]:
    return {
        "selection_type": request.selection_type, "selection_context": request.selection_context,
        "acting_player": request.acting_player, "min_count": request.min_count, "max_count": request.max_count,
        "remain_damage_counter": request.remain_damage_counter, "remain_energy_cost": request.remain_energy_cost,
        "context_card_id": request.context_card_id, "effect_card_id": request.effect_card_id,
        "ordering": request.ordering,
        "options": [
            {
                "original_index": option.original_index, "option_type": option.option_type,
                "option_name": option.option_name, "card_id": option.card_id, "attack_id": option.attack_id,
                "source_card_id": _card(observation, option), "target_card_id": _card(observation, option, False),
                "serial": option.serial, "choice_role": option.choice_role,
                "semantic_fingerprint": option.semantic_fingerprint, "available": option.available,
            }
            for option in request.options
        ],
    }


def _score(observation: EngineObservationV1, request: SelectionRequestV1, index: int, *, formulation: str, seat: int) -> tuple[int, int, int]:
    option = request.options[index]
    source = _card(observation, option)
    target = _card(observation, option, False)
    score = 0
    if formulation in {"opponent_passive", "opponent_stage_evolve"}:
        # The stage-evolve formulation is a separate deterministic public
        # probe: when an evolution is legal, prefer it over ending the turn so
        # the 723 target class can actually be reached.  It never inspects
        # hidden zones or mutates native state.
        if formulation == "opponent_stage_evolve" and option.option_type == 9:
            return (25000, -int(source or 0), -index)
        if option.option_type == 14:
            return (20000, -int(source or 0), -index)
        if option.option_type == 9:
            return (15000, -int(source or 0), -index)
        if option.option_type == 7 and source in {721, 722, 723}:
            return (10000, -int(source or 0), -index)
        if option.option_type == 13:
            return (-10000, -int(source or 0), -index)
        if option.option_type == 8:
            return (-1000, -int(source or 0), -index)
    if option.option_type == 14:  # END/STOP
        score = -10000
    if option.option_type == 13:  # ATTACK
        if formulation == "snover_1044_first":
            score = 10000 if option.attack_id == 1044 else 9000 if option.attack_id == 1045 else -1000
        elif formulation == "snover_1045_first":
            score = 10000 if option.attack_id == 1045 else 9000 if option.attack_id == 1044 else -1000
        elif formulation in {"snover_to_mega_evolution", "prize_route_targets"}:
            score = 10000 if option.attack_id == 1047 else 9000 if option.attack_id == 1044 else 100
    if option.option_type == 9:  # EVOLVE
        score = 11000 if source == 723 and target == 722 else -2000
    if option.option_type == 7:  # PLAY
        if source == 722:
            score = 9000
        elif source == 721:
            score = 8500
        elif source == 723:
            score = 8000
        elif source == 1121:
            score = 2000
        elif source in {1126, 1192, 1227}:
            score = 1000
    if option.option_type == 8:  # ATTACH
        if source == 3 and target in {721, 722, 723}:
            score = 9500
    if option.option_type == 3:  # CARD in a search/bench/hand selection
        if source == 722:
            score = 9000
        elif source == 723:
            score = 8500
        elif source == 721:
            score = 8000
        elif source == 3:
            score = 3000
    if option.option_type == 1:  # YES
        score = 1000
    if formulation == "prize_route_targets" and option.option_type == 13 and option.attack_id == 1047:
        score = 12000
    return score, -int(source or 0), -index


class PublicCapabilityPolicy:
    """Deterministic public semantic policy used only to elicit capsules."""

    policy_id = "phase-a-b1-public-capability-probe-v1"

    def __init__(self, formulation: str, seat: int, prize_target_card: int | None = None) -> None:
        self.formulation = formulation
        self.seat = seat
        self.prize_target_card = prize_target_card

    def reset(self, episode_uuid: str, player_index: int, reason: str = "start") -> None:
        return None

    def choose(self, observation: EngineObservationV1, request: SelectionRequestV1) -> Any:
        candidates = [index for index, option in enumerate(request.options) if option.available]
        candidates.sort(key=lambda index: _score(observation, request, index, formulation=self.formulation, seat=self.seat), reverse=True)
        if self.formulation == "prize_route_targets":
            target = _active(observation, 1 - self.seat)
            target_card = target.card_id if target is not None else None
            def prize_priority(index: int) -> tuple[int, int, int]:
                option = request.options[index]
                base = _score(observation, request, index, formulation=self.formulation, seat=self.seat)
                own_active = _active(observation, self.seat)
                own_hand = _hand_card_ids(observation, self.seat)
                bench_route = any(entity.card_id in {722, 723} for entity in observation.entities if entity.owner == self.seat and entity.zone == AREA["BENCH"])
                if own_active is not None and own_active.card_id != 723 and bench_route:
                    if option.option_type == 8 and _card(observation, option) == 3:
                        target_entity = _entity(observation, option.target_entity_key)
                        if target_entity is not None and target_entity.card_id == 723:
                            return (23000, *base[1:])
                        if target_entity is not None and target_entity.card_id == own_active.card_id:
                            return (22000 if own_active.attached_energy_count < 3 else 5000, *base[1:])
                    if option.option_type == 12:
                        return (22500, *base[1:])
                if request.selection_type == 1 and request.selection_context in {3, 4}:
                    if _card(observation, option) in {722, 723}:
                        return (22000, *base[1:])
                    if _card(observation, option) == 721:
                        return (18000, *base[1:])
                if self.prize_target_card in {723, 754} and own_active is not None and own_active.card_id in {721, 722}:
                    if option.option_type == 7 and _card(observation, option) in {1121, 1192, 1227} and 723 not in own_hand:
                        return (21000 if _card(observation, option) == 1121 else 20500, *base[1:])
                    if option.option_type == 7 and _card(observation, option) in {722, 723}:
                        return (20000, *base[1:])
                    if option.option_type == 14:
                        return (19000, *base[1:])
                    if option.option_type == 13 and option.attack_id in {1044, 1045}:
                        return (-19000, *base[1:])
                if self.prize_target_card == 723 and target_card == 722:
                    if option.option_type == 14:
                        return (20000, -int(option.card_id or 0), -index)
                    if option.option_type == 13:
                        return (-20000, *base[1:])
                # A setup-only turn may spend a public Ultra Ball or draw
                # supporter to expose the Stage-1 copy.  This is still a
                # legal current action; no private hand/deck information is
                # consulted beyond the actor's public hand entities.
                if option.option_type == 7 and own_active is not None and own_active.card_id in {721, 722} and 723 not in own_hand:
                    if _card(observation, option) == 1121:
                        return (16000, *base[1:])
                    if _card(observation, option) in {1192, 1227}:
                        return (15000, *base[1:])
                if request.selection_type == 1 and _card(observation, option) == 723:
                    return (18000, *base[1:])
                if request.selection_type == 1 and _card(observation, option) == 722:
                    return (-5000, *base[1:])
                if option.option_type == 13:
                    attack_priority = {1047: 12000, 1046: 9000, 1045: 8000, 1044: 7000}
                    return (attack_priority.get(int(option.attack_id or -1), -10000), *base[1:])
                return base
            candidates.sort(key=prize_priority, reverse=True)
        if request.min_count == 0:
            positive = [index for index in candidates if _score(observation, request, index, formulation=self.formulation, seat=self.seat)[0] > 0]
            candidates = positive[:1]
        elif request.selection_type == 0:
            candidates = candidates[:max(request.min_count, 1)]
        else:
            candidates = candidates[:max(request.min_count, 1)]
        builder = CompoundActionBuilder(request)
        for index in candidates:
            if builder.complete:
                break
            builder.choose(index)
        if not builder.complete:
            builder.stop()
        return validate_compound_action(request, builder.build())


def _hp_delta(before: EngineObservationV1, after: EngineObservationV1, target: Any | None) -> int | None:
    if target is None or target.hp is None:
        return None
    same = _entity(after, target.entity_key)
    if same is None or same.hp is None:
        return target.hp
    return target.hp - same.hp


def _event_hp_deltas(events: Sequence[Any], *, owner: int) -> dict[int, int]:
    result: dict[int, int] = {}
    for event in events:
        if event.event_name != "HP_CHANGE" or event.fields.get("playerIndex") != owner:
            continue
        serial = event.fields.get("serial")
        if not isinstance(serial, int):
            serial = event.fields.get("serialTarget")
        value = event.fields.get("value")
        if isinstance(serial, int) and isinstance(value, int):
            result[serial] = result.get(serial, 0) - value
    return result


def _event_serials(event: Any) -> set[int]:
    """Return every entity serial named by one public event."""
    return {
        value for key, value in event.fields.items()
        if key.startswith("serial") and isinstance(value, int) and not isinstance(value, bool)
    }


def _event_card_ids(event: Any) -> set[int]:
    return {
        value for key, value in event.fields.items()
        if key.startswith("cardId") and isinstance(value, int) and not isinstance(value, bool)
    }


def _attack_record(before: EngineObservationV1, request: SelectionRequestV1, action: Any, after: EngineObservationV1, formulation: str, transition: int, events: Sequence[Any]) -> dict[str, Any] | None:
    chosen = [request.options[index] for index in action.submitted_original_indices]
    attack = next((option for option in chosen if option.attack_id in ATTACK_IDS), None)
    if attack is None:
        return None
    source = _entity(before, attack.source_entity_key)
    target = _active(before, 1 - request.acting_player)
    attack_events = [event for event in events if event.event_name == "ATTACK" and event.fields.get("attackId") == attack.attack_id and event.fields.get("playerIndex") == request.acting_player]
    expected_energy = {1044: 1, 1045: 2}[int(attack.attack_id)]
    expected_damage = {1044: 10, 1045: 30}[int(attack.attack_id)]
    target_after = _entity(after, target.entity_key) if target is not None else None
    hp_delta = _hp_delta(before, after, target)
    event_deltas = _event_hp_deltas(events, owner=1 - request.acting_player)
    target_event_delta = event_deltas.get(target.serial, 0) if target is not None and target.serial is not None else None
    source_serial = source.serial if source is not None else None
    target_serial = target.serial if target is not None else None
    non_allowed: list[str] = []
    source_target_serials = {serial for serial in (source_serial, target_serial) if isinstance(serial, int)}
    attack_identity_events = [
        event for event in attack_events
        if source is not None
        and event.fields.get("serial") == source_serial
        and event.fields.get("cardId") == source.card_id
    ]
    target_hp_events = [
        event for event in events
        if event.event_name == "HP_CHANGE" and event.fields.get("serial") == target_serial
    ]
    for event in events:
        serials = _event_serials(event)
        if serials.intersection(source_target_serials) and event.event_name not in {"ATTACK", "HP_CHANGE"}:
            non_allowed.append(event.event_name)
        if event.event_name == "HP_CHANGE" and serials.intersection(source_target_serials) and target_serial not in serials:
            non_allowed.append(event.event_name)
        if event.event_name == "ATTACK" and serials.intersection(source_target_serials) and event not in attack_identity_events:
            non_allowed.append(event.event_name)
        if event.event_name == "HP_CHANGE" and target_serial in serials:
            if event.fields.get("playerIndex") != (1 - request.acting_player) or event.fields.get("cardId") != target.card_id:
                non_allowed.append(event.event_name)
    energy_valid = bool(source is not None and source.card_id == 722 and source.attached_energy_count >= expected_energy and source.energy_types.count(3) >= expected_energy)
    target_valid = bool(target is not None and target.zone == AREA["ACTIVE"] and target.position == 0 and target_after is not None and target_after.zone == AREA["ACTIVE"] and target_after.position == 0 and target_after.serial == target.serial and target_after.card_id == target.card_id and target_after.owner == target.owner)
    target_event_valid = bool(
        len(target_hp_events) == 1
        and target_event_delta == expected_damage
        and target_hp_events[0].fields.get("playerIndex") == (1 - request.acting_player)
        and target_hp_events[0].fields.get("cardId") == target.card_id
        and target_hp_events[0].fields.get("serial") == target_serial
    )
    proof = bool(attack_identity_events and len(attack_identity_events) == 1 and energy_valid and target_valid and target_event_valid and hp_delta == expected_damage and not non_allowed)
    return {
        "formulation": formulation,
        "transition": transition,
        "attack_id": attack.attack_id,
        "source_card_id": source.card_id if source else None,
        "source_serial": source.serial if source else None,
        "source_energy_types": list(source.energy_types) if source else [],
        "source_attached_energy_count": source.attached_energy_count if source else None,
        "target_card_id": target.card_id if target else None,
        "target_serial": target.serial if target else None,
        "target_zone_before": target.zone if target else None,
        "target_zone_after": target_after.zone if target_after else None,
        "target_hp_before": target.hp if target else None,
        "target_hp_after": target_after.hp if target_after else None,
        "hp_delta": hp_delta,
        "target_event_delta": target_event_delta,
        "attack_events": [_event_dict(event) for event in attack_events],
        "event_window": [_event_dict(event) for event in events],
        "attack_identity_valid": len(attack_identity_events) == 1,
        "target_event_identity_valid": target_event_valid,
        "non_allowed_event_names": non_allowed,
        "energy_legal": energy_valid,
        "active_target_preserved": target_valid,
        "expected_damage": expected_damage,
        "proof": proof,
    }


def _evolution_record(before: EngineObservationV1, request: SelectionRequestV1, action: Any, after: EngineObservationV1, transition: int, events: Sequence[Any]) -> dict[str, Any] | None:
    chosen = [request.options[index] for index in action.submitted_original_indices]
    option = next((item for item in chosen if item.option_type == 9), None)
    if option is None:
        return None
    source = _entity(before, option.target_entity_key)
    if source is None:
        source = _entity(before, option.source_entity_key)
    evolution_event = next((event for event in events if event.event_name == "EVOLVE" and event.fields.get("serialTarget") == source.serial), None) if source else None
    target_serial = evolution_event.fields.get("serial") if evolution_event else None
    after_same = next((entity for entity in after.entities if entity.serial == target_serial and entity.owner == source.owner), None) if source and isinstance(target_serial, int) else None
    legal = bool(
        option.option_type == 9 and _card(before, option) == 723 and _card(before, option, False) == 722
        and source is not None and source.card_id == 722 and source.zone in {AREA["ACTIVE"], AREA["BENCH"]}
    )
    serial_linked = bool(
        evolution_event is not None and evolution_event.fields.get("cardId") == 723
        and evolution_event.fields.get("cardIdTarget") == source.card_id
        and evolution_event.fields.get("playerIndex") == source.owner
        and evolution_event.fields.get("serialTarget") == source.serial
        and evolution_event.fields.get("serial") == target_serial
    )
    preserve = bool(
        legal and after_same is not None and after_same.card_id == 723 and after_same.serial == source.serial
        and after_same.zone == source.zone and after_same.position == source.position
        and after_same.attached_energy_count == source.attached_energy_count
        and tuple(after_same.energy_types) == tuple(source.energy_types)
        and after_same.damage == source.damage and tuple(after_same.statuses) == tuple(source.statuses)
    )
    # Native evolution creates a new entity serial and retires the old serial;
    # the public EVOLVE event is the authoritative identity link.  Preserve
    # every local state field that the engine promises to carry, while
    # reporting serial replacement explicitly rather than mislabelling it.
    local_fields_preserved = bool(
        legal and after_same is not None and after_same.card_id == 723
        and source.serial is not None and after_same.serial is not None and source.serial != after_same.serial
        and after_same.zone == source.zone and after_same.position == source.position
        and after_same.attached_energy_count == source.attached_energy_count
        and tuple(after_same.energy_types) == tuple(source.energy_types)
        and after_same.damage == source.damage and tuple(after_same.statuses) == tuple(source.statuses)
    )
    return {
        "transition": transition,
        "source_card_id": source.card_id if source else None,
        "target_card_id": after_same.card_id if after_same else None,
        "source_serial": source.serial if source else None,
        "target_serial": after_same.serial if after_same else None,
        "source_owner": source.owner if source else None,
        "target_owner": after_same.owner if after_same else None,
        "source_zone": source.zone if source else None,
        "target_zone": after_same.zone if after_same else None,
        "source_position": source.position if source else None,
        "target_position": after_same.position if after_same else None,
        "source_attached_energy_count": source.attached_energy_count if source else None,
        "target_attached_energy_count": after_same.attached_energy_count if after_same else None,
        "source_energy_types": list(source.energy_types) if source else [],
        "target_energy_types": list(after_same.energy_types) if after_same else [],
        "source_damage": source.damage if source else None,
        "target_damage": after_same.damage if after_same else None,
        "source_statuses": list(source.statuses) if source else [],
        "target_statuses": list(after_same.statuses) if after_same else [],
        "legal_boundary": legal,
        "serial_linked_by_native_event": serial_linked,
        "serial_replaced": bool(
            source is not None and after_same is not None
            and source.serial is not None and after_same.serial is not None
            and source.serial != after_same.serial
        ),
        "local_delta_preserved": local_fields_preserved and serial_linked,
        "serial_preserved": preserve,
        "events": [_event_dict(event) for event in events],
    }


def _ko_from_attack(before: EngineObservationV1, request: SelectionRequestV1, action: Any, after: EngineObservationV1, events: Sequence[Any], transition: int) -> dict[str, Any] | None:
    chosen = [request.options[index] for index in action.submitted_original_indices]
    attack = next((item for item in chosen if item.attack_id is not None), None)
    target = _active(before, 1 - request.acting_player)
    if attack is None or target is None or target.card_id not in TARGET_PRIZE_CLASSES:
        return None
    delta = _hp_delta(before, after, target)
    target_after = _entity(after, target.entity_key)
    source = _entity(before, attack.source_entity_key)
    attack_events = [event for event in events if event.event_name == "ATTACK" and event.fields.get("playerIndex") == request.acting_player and event.fields.get("attackId") == attack.attack_id]
    attack_identity_events = [
        event for event in attack_events
        if source is not None
        and event.fields.get("serial") == source.serial
        and event.fields.get("cardId") == source.card_id
    ]
    hp_events = _event_hp_deltas(events, owner=1 - request.acting_player)
    event_delta = hp_events.get(target.serial, 0) if target.serial is not None else None
    target_hp_events = [
        event for event in events
        if event.event_name == "HP_CHANGE" and event.fields.get("serial") == target.serial
    ]
    opponent_entity_serials = {
        entity.serial for entity in before.entities
        if entity.owner == (1 - request.acting_player) and entity.serial is not None
    }
    hp_serials = {
        serial for event in events if event.event_name == "HP_CHANGE"
        for serial in _event_serials(event) if serial in opponent_entity_serials
    }
    distinct_ko_serials = {
        serial for serial in hp_serials
        if any(
            event.event_name == "HP_CHANGE"
            and serial in _event_serials(event)
            and isinstance(event.fields.get("value"), int)
            and event.fields.get("value") < 0
            for event in events
        )
    }
    expected_prize_delta = EXPECTED_PRIZE_DELTAS[target.card_id]
    target_event_valid = bool(
        target.serial is not None
        and len(target_hp_events) == 1
        and event_delta is not None and event_delta > 0
        and target_hp_events[0].fields.get("playerIndex") == (1 - request.acting_player)
        and target_hp_events[0].fields.get("cardId") == target.card_id
        and target_hp_events[0].fields.get("serial") == target.serial
    )
    ko = bool(
        len(attack_identity_events) == 1
        and target_event_valid
        and target.hp is not None and delta is not None and delta >= target.hp
        and (target_after is None or target_after.zone != AREA["ACTIVE"])
        and distinct_ko_serials == {target.serial}
    )
    return {
        "transition": transition,
        "target_card_id": target.card_id,
        "target_serial": target.serial,
        "target_hp_before": target.hp,
        "target_hp_after": target_after.hp if target_after else None,
        "target_zone_after": target_after.zone if target_after else None,
        "attack_id": attack.attack_id,
        "attacking_card_id": _card(before, attack),
        "hp_delta": delta,
        "event_hp_delta": event_delta,
        "expected_prize_delta": expected_prize_delta,
        "attack_events": [_event_dict(event) for event in attack_events],
        "attack_identity_valid": len(attack_identity_events) == 1,
        "target_event_identity_valid": target_event_valid,
        "distinct_opponent_hp_serials": sorted(hp_serials),
        "distinct_ko_serials": sorted(distinct_ko_serials),
        "event_window": [_event_dict(event) for event in events],
        "causal_ko": ko,
        "prize_proof": False,
    }


def _run_game(config: Mapping[str, Any], *, formulation: str, game_index: int, deck_key: str | None = None, candidate_seat: int | None = None) -> dict[str, Any]:
    probe = next(row for row in config["formulations"] if row["id"] == formulation)
    kind = probe["probe"]
    candidate_player = game_index % 2 if candidate_seat is None else candidate_seat
    if kind == "prize_units":
        if deck_key is None:
            raise ValueError("prize probe requires target deck key")
        candidate_deck = expand_deck(config["deck_specs"]["candidate"])
        opponent_deck = expand_deck(config["deck_specs"][deck_key])
    else:
        candidate_deck = expand_deck(config["deck_specs"]["candidate"])
        opponent_deck = expand_deck(config["deck_specs"]["target_754"])
    decks = (candidate_deck, opponent_deck) if candidate_player == 0 else (opponent_deck, candidate_deck)
    policies = tuple(
        (
            RouteProbePolicy("frost_barrier")
            if kind == "prize_units" and player == candidate_player and deck_key in {"target_723", "target_754"}
            else PublicCapabilityPolicy(
                formulation if player == candidate_player else ("opponent_stage_evolve" if deck_key == "target_723" else "opponent_passive"),
                player,
                int(deck_key.split("_", 1)[1]) if player == candidate_player and deck_key and deck_key.startswith("target_") else None,
            )
        )
        for player in (0, 1)
    )
    engine = NativeCABTTransport(ROOT / config["engine_root"])
    battle_id = f"phase-a-b1-capability-{formulation}-{game_index}-{uuid.uuid4().hex[:8]}"
    raw = engine.start(*decks)
    started = time.monotonic()
    transition = 0
    terminal = None
    counters = Counter()
    attacks: list[dict[str, Any]] = []
    evolutions: list[dict[str, Any]] = []
    kos: list[dict[str, Any]] = []
    prize_pending: deque[dict[str, Any]] = deque()
    selected_option_type_counts: Counter[str] = Counter()
    selected_attack_counts: Counter[str] = Counter()
    evolution_option_count = 0
    illegal_evolution_options = 0
    try:
        while transition < config["limits"]["request_cap_per_game"]:
            if time.monotonic() - started > config["limits"]["wall_seconds"]:
                counters["timeouts"] += 1
                break
            observation, request = semantic_snapshot(raw, battle_id, transition, config["assets"]["card_data_sha256"])
            if observation.terminal_result is not None:
                # A final Prize selection can make the next snapshot
                # terminal; settle the public count before returning so a
                # terminal KO is not incorrectly labelled UNKNOWN.
                for pending in list(prize_pending):
                    player = int(pending["attacking_player"])
                    current = observation.players[player].prize_count
                    if current < pending["prize_count_before"]:
                        pending["prize_count_after"] = current
                        pending["prize_delta"] = pending["prize_count_before"] - current
                        pending["prize_proof"] = bool(
                            not pending.get("ambiguous_prize_pairing")
                            and pending["prize_delta"] == pending["expected_prize_delta"]
                        )
                        kos.append(dict(pending))
                        prize_pending.remove(pending)
                terminal = observation.terminal_result
                break
            if request is None:
                counters["semantic_contract_failures"] += 1
                break
            for option in request.options:
                if option.option_type == 9:
                    evolution_option_count += 1
                    if not (_card(observation, option) == 723 and _card(observation, option, False) == 722):
                        illegal_evolution_options += 1
            policy = policies[request.acting_player]
            action = policy.choose(observation, request)
            for index in action.submitted_original_indices:
                selected_option_type_counts[str(request.options[index].option_type)] += 1
                if request.options[index].attack_id is not None:
                    selected_attack_counts[str(request.options[index].attack_id)] += 1
            before = observation
            attack_selected = any(option.attack_id in ATTACK_IDS for option in (request.options[index] for index in action.submitted_original_indices))
            raw_after = engine.select(action.submitted_original_indices)
            after, _ = semantic_snapshot(raw_after, battle_id, transition + 1, config["assets"]["card_data_sha256"])
            # Native logs are consumptive and represent this transition only;
            # never subtract one snapshot from another.
            interval_events = after.public_events
            if attack_selected:
                # Recompute against the actual post-selection snapshot.
                attack_record = _attack_record(before, request, action, after, formulation, transition, interval_events)
                if attack_record is not None:
                    attacks.append(attack_record)
            evolution_record = _evolution_record(before, request, action, after, transition, interval_events)
            if evolution_record is not None:
                evolutions.append(evolution_record)
            ko_record = _ko_from_attack(before, request, action, after, interval_events, transition)
            # PrizeStatic qualification is for the configured target deck and
            # must be caused by the candidate policy; opponent KOs of the
            # candidate's own cards are a separate diagnostic, never paired
            # to the target class.
            if ko_record is not None and request.acting_player == candidate_player and ko_record.get("causal_ko"):
                ko_record.update({"attacking_player": request.acting_player, "prize_count_before": before.players[request.acting_player].prize_count, "prize_count_after_at_ko": after.players[request.acting_player].prize_count})
                if prize_pending:
                    counters["ambiguous_prize_pairings"] += len(prize_pending) + 1
                    for pending in prize_pending:
                        pending["ambiguous_prize_pairing"] = True
                    ko_record["ambiguous_prize_pairing"] = True
                prize_pending.append(ko_record)
            for pending in list(prize_pending):
                player = int(pending["attacking_player"])
                current = after.players[player].prize_count
                if current < pending["prize_count_before"]:
                    pending["prize_count_after"] = current
                    pending["prize_delta"] = pending["prize_count_before"] - current
                    pending["prize_proof"] = bool(
                        not pending.get("ambiguous_prize_pairing")
                        and pending["prize_delta"] == pending["expected_prize_delta"]
                    )
                    kos.append(dict(pending))
                    prize_pending.remove(pending)
                # Keep a causal KO pending until a public Prize-count delta
                # or terminal state.  The request cap bounds this queue; an
                # unresolved entry is explicitly UNKNOWN at game close.
            raw = raw_after
            transition += 1
        else:
            counters["request_cap_failures"] += 1
    except ContractViolation:
        counters["invalid_actions"] += 1
    except Exception as error:  # retained in raw evidence, never a silent pass
        counters[f"native_error:{type(error).__name__}"] += 1
    finally:
        engine.finish()
    if terminal is None:
        counters["incomplete_games"] += 1
    for pending in prize_pending:
        pending = dict(pending)
        pending["prize_proof"] = False
        kos.append(pending)
    return {
        "game_index": game_index, "candidate_player": candidate_player, "deck_key": deck_key,
        "formulation": formulation, "probe": kind, "requests": transition,
        "terminal_result": terminal, "counters": _normalise_counters(counters),
        "attacks": attacks, "evolutions": evolutions, "kos": kos,
        "selected_option_type_counts": dict(selected_option_type_counts),
        "selected_attack_counts": dict(selected_attack_counts),
        "evolution_option_count": evolution_option_count,
        "illegal_evolution_options": illegal_evolution_options,
    }


def _write_sealed_json(path: Path, payload: Mapping[str, Any]) -> tuple[str, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode()
    if len(encoded) > 64 * 1024 * 1024:
        raise ValueError("raw evidence exceeds configured 64 MiB cap")
    path.write_bytes(encoded)
    os.chmod(path, 0o444)
    digest = hashlib.sha256(encoded).hexdigest()
    sidecar = path.with_name(path.name + ".sha256")
    sidecar.write_text(f"{digest}  {path.name}\n", encoding="ascii")
    os.chmod(sidecar, 0o444)
    return digest, len(encoded)


def _capability_status(kind: str, games: Sequence[Mapping[str, Any]], config: Mapping[str, Any], *, required_attack_ids: Sequence[int] = ATTACK_IDS) -> dict[str, Any]:
    counters = Counter()
    for game in games:
        counters.update(game["counters"])
    if kind == "snover_attacks":
        all_records = [record for game in games for record in game["attacks"]]
        records = [record for record in all_records if record["proof"]]
        by_attack = {str(attack_id): [record for record in records if record["attack_id"] == attack_id] for attack_id in ATTACK_IDS}
        duplicate_keys = [key for key, count in Counter((game.get("game_index"), record.get("transition"), record.get("attack_id"), record.get("source_serial"), record.get("target_serial")) for game in games for record in game["attacks"] if record.get("proof")).items() if count > 1]
        threshold = 2
        per_seat = {
            str(seat): {str(attack_id): sum(1 for game in games if game["candidate_player"] == seat for record in game["attacks"] if record["proof"] and record["attack_id"] == attack_id) for attack_id in ATTACK_IDS}
            for seat in (0, 1)
        }
        passed = all(len(by_attack[str(attack_id)]) >= threshold for attack_id in required_attack_ids) and all(per_seat[str(seat)][str(attack_id)] >= 1 for seat in (0, 1) for attack_id in required_attack_ids)
        return {
            "status": "PASS" if passed and not duplicate_keys and not any(counters[key] for key in RELIABILITY_COUNTER_KEYS) else "PARTIAL",
            "attempt_count": len(all_records),
            "rejected_attempt_count": len(all_records) - len(records),
            "duplicate_proof_count": len(duplicate_keys),
            "required_attack_ids": list(required_attack_ids),
            "proof_count_by_attack": {key: len(value) for key, value in by_attack.items()},
            "proof_count_by_candidate_seat": per_seat,
            "observed_hp_deltas_by_attack": {key: sorted({int(record["hp_delta"]) for record in value if record.get("hp_delta") is not None}) for key, value in by_attack.items()},
            "observed_event_hp_deltas_by_attack": {key: sorted({int(record["target_event_delta"]) for record in value if record.get("target_event_delta") is not None}) for key, value in by_attack.items()},
            "energy_legal_proofs": sum(1 for record in records if record.get("energy_legal")),
            "active_target_preserved_proofs": sum(1 for record in records if record.get("active_target_preserved")),
            "non_allowed_event_records": sum(1 for record in records if record.get("non_allowed_event_names")),
            "records": records,
            "counters": _normalise_counters(counters),
        }
    if kind == "evolution":
        records = [record for game in games for record in game["evolutions"]]
        valid = [record for record in records if record["legal_boundary"] and record["local_delta_preserved"]]
        duplicate_keys = [key for key, count in Counter((game.get("game_index"), record.get("transition"), record.get("source_serial"), record.get("target_serial")) for game in games for record in game["evolutions"] if record.get("local_delta_preserved")).items() if count > 1]
        seats = {str(seat): sum(1 for game in games if game["candidate_player"] == seat for record in game["evolutions"] if record["local_delta_preserved"]) for seat in (0, 1)}
        passed = len(valid) >= 2 and all(value >= 1 for value in seats.values()) and all(game["illegal_evolution_options"] == 0 for game in games) and all(record.get("serial_replaced") and record.get("serial_linked_by_native_event") for record in valid) and not duplicate_keys
        return {
            "status": "PASS" if passed and not any(counters[key] for key in RELIABILITY_COUNTER_KEYS) else "PARTIAL",
            "proof_count": len(valid),
            "proof_count_by_candidate_seat": seats,
            "evolution_option_count": sum(game["evolution_option_count"] for game in games),
            "illegal_evolution_options": sum(game["illegal_evolution_options"] for game in games),
            "serial_linked_proofs": sum(1 for record in valid if record.get("serial_linked_by_native_event")),
            "serial_replaced_proofs": sum(1 for record in valid if record.get("serial_replaced")),
            "serial_preserved_proofs": sum(1 for record in valid if record.get("serial_preserved")),
            "local_delta_preserved_proofs": sum(1 for record in valid if record.get("local_delta_preserved")),
            "duplicate_proof_count": len(duplicate_keys),
            "source_target_zone_pairs": sorted({(record.get("source_zone"), record.get("target_zone")) for record in valid}),
            "records": records,
            "counters": _normalise_counters(counters),
        }
    records = [record for game in games for record in game["kos"]]
    by_target = {str(card_id): [record for record in records if record["target_card_id"] == card_id and record.get("prize_proof")] for card_id in TARGET_PRIZE_CLASSES}
    per_seat = {str(card_id): {str(seat): sum(1 for game in games if game["candidate_player"] == seat for record in game["kos"] if record["target_card_id"] == card_id and record.get("prize_proof")) for seat in (0, 1)} for card_id in TARGET_PRIZE_CLASSES}
    duplicate_keys = [key for key, count in Counter((game.get("game_index"), record.get("transition"), record.get("target_serial"), record.get("target_card_id")) for game in games for record in game["kos"] if record.get("prize_proof")).items() if count > 1]
    statuses = {key: ("PASS" if len(value) >= config["prize_contract"]["minimum_ko_proofs_per_target"] and all(per_seat[key][str(seat)] >= 1 for seat in (0, 1)) and all(record.get("expected_prize_delta") == EXPECTED_PRIZE_DELTAS[int(key)] and record.get("prize_delta") == EXPECTED_PRIZE_DELTAS[int(key)] for record in value) else "UNKNOWN") for key, value in by_target.items()}
    return {
        "status": "PASS" if all(value == "PASS" for value in statuses.values()) and not duplicate_keys and not any(counters[key] for key in RELIABILITY_COUNTER_KEYS) else "PARTIAL",
        "status_by_target_card": statuses,
        "proof_count_by_target_card": {key: len(value) for key, value in by_target.items()},
        "proof_count_by_target_card_and_candidate_seat": per_seat,
        "observed_prize_units": {key: sorted({int(record["prize_delta"]) for record in value if record.get("prize_delta") is not None}) for key, value in by_target.items()},
        "causal_ko_proofs": sum(1 for record in records if record.get("prize_proof") and record.get("causal_ko")),
        "ambiguous_prize_pairings": sum(1 for record in records if record.get("ambiguous_prize_pairing")),
        "duplicate_proof_count": len(duplicate_keys),
        "rejected_ko_count": sum(1 for record in records if record.get("causal_ko") and not record.get("prize_proof")),
        "records": records,
        "counters": _normalise_counters(counters),
    }


def run_experiment(config: Mapping[str, Any], config_path: Path = DEFAULT_CONFIG, *, mode: str = "all") -> dict[str, Any]:
    config_path = config_path.resolve()
    observed_assets = validate_assets(config, config_path)
    all_games: list[dict[str, Any]] = []
    capability_results: dict[str, Any] = {}
    plans = [(row["id"], row["probe"]) for row in config["formulations"]]
    for formulation, kind in plans:
        if mode not in {"all", kind, formulation}:
            continue
        games: list[dict[str, Any]] = []
        if kind == "prize_units":
            for target in TARGET_PRIZE_CLASSES:
                for index in range(config["limits"]["games_per_prize_target"]):
                    game = _run_game(config, formulation=formulation, game_index=len(all_games), deck_key=f"target_{target}", candidate_seat=index % 2)
                    games.append(game)
                    all_games.append(game)
        elif kind == "evolution":
            for index in range(config["limits"]["games_per_evolution_seat"] * 2):
                game = _run_game(config, formulation=formulation, game_index=len(all_games), candidate_seat=index % 2)
                games.append(game)
                all_games.append(game)
        else:
            for index in range(config["limits"]["games_per_attack_formulation"] * 2):
                game = _run_game(config, formulation=formulation, game_index=len(all_games), candidate_seat=index % 2)
                games.append(game)
                all_games.append(game)
        required = (1044,) if formulation == "snover_1044_first" else (1045,) if formulation == "snover_1045_first" else ATTACK_IDS
        capability_results[formulation] = _capability_status(kind, games, config, required_attack_ids=required)
    attack_formulations = [capability_results[key] for key in ("snover_1044_first", "snover_1045_first") if key in capability_results]
    if len(attack_formulations) == 2:
        combined_games = [game for key in ("snover_1044_first", "snover_1045_first") for game in all_games if game["formulation"] == key]
        capability_results["snover_attack_capability_combined"] = _capability_status("snover_attacks", combined_games, config, required_attack_ids=ATTACK_IDS)
    source_receipts = {str(path.relative_to(ROOT)): sha256(path) for path in (*SOURCE_PATHS, config_path)}
    payload = {
        "schema_version": 1,
        "record_id": "phase-a-b1-capability-capsules-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "NATIVE_QUALIFIED_CANDIDATE",
        "status": "PASS" if all(result["status"] == "PASS" for result in capability_results.values()) else "PARTIAL",
        "decision": "B1_CAPABILITY_CAPSULE_MATRIX",
        "knowledge_base": {"path": "knowledge_base/ptcg_gold.sqlite", "validation": "PASS", "ids": config["knowledge_base_ids"]},
        "provenance": {
            "repo_root": str(ROOT), "config": str(config_path.relative_to(ROOT)), "assets": observed_assets,
            "sources": source_receipts, "native_randomness": "official engine entropy only; no seed/order/state mutation",
            "candidate_deck_sha256": canonical_hash(sorted(expand_deck(config["deck_specs"]["candidate"]))),
            "target_deck_sha256": {key: canonical_hash(sorted(expand_deck(value))) for key, value in config["deck_specs"].items() if key.startswith("target_")},
        },
        "reliability_floor": {key: 0 for key in RELIABILITY_COUNTER_KEYS},
        "games": all_games,
        "capability_results": capability_results,
    }
    run_dir = ROOT / "runs" / f"phase-a-b1-capability-capsules-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:12]}"
    raw_path = run_dir / "raw-evidence.json"
    raw_digest, raw_bytes = _write_sealed_json(raw_path, payload)
    prize_status = capability_results.get("prize_route_targets", {}).get("status_by_target_card", {})
    unknown_targets = [card_id for card_id in TARGET_PRIZE_CLASSES if prize_status.get(str(card_id)) != "PASS"]
    if payload["status"] == "PASS":
        conclusion = "All configured native capability capsules passed with zero reliability failures; no capability is production authority and no PolicyV1 integration occurred."
    elif unknown_targets:
        conclusion = f"Unobserved or incomplete Prize target classes remain UNKNOWN: {unknown_targets}; no capability is production authority and no PolicyV1 integration occurred."
    else:
        conclusion = "One or more capability capsules are PARTIAL; no capability is production authority and no PolicyV1 integration occurred."
    report_provenance = dict(payload["provenance"])
    report_provenance["repo_root"] = "repo"
    report = {
        "schema_version": 1, "record_id": payload["record_id"], "created_at_utc": payload["created_at_utc"],
        "scope": payload["scope"], "status": payload["status"], "decision": payload["decision"],
        "knowledge_base": payload["knowledge_base"], "capability_results": {
            key: {name: value for name, value in result.items() if name not in {"records"}}
            for key, result in capability_results.items()
        },
        "raw_evidence": {"path": str(raw_path.relative_to(ROOT)), "sha256": raw_digest, "bytes": raw_bytes, "mode": "0444", "sidecar": str(raw_path.with_name(raw_path.name + ".sha256").relative_to(ROOT))},
        "provenance": report_provenance,
        "conclusion": conclusion,
    }
    DEFAULT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_REPORT.write_text(json.dumps(report, sort_keys=True, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--mode", choices=("all", "snover_attacks", "evolution", "prize_units", "snover_1044_first", "snover_1045_first", "snover_to_mega_evolution", "prize_route_targets"), default="all")
    args = parser.parse_args()
    config = load_config(args.config)
    report = run_experiment(config, args.config, mode=args.mode)
    print(json.dumps({"status": report["status"], "report": str(DEFAULT_REPORT.relative_to(ROOT)), "raw_evidence": report["raw_evidence"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
