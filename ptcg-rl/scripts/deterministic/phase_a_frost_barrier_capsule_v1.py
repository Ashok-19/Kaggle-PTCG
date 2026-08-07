"""Native, public-state Frost Barrier next-turn damage capsule.

The primary formulation measures two fixed 40-damage attacks in one official
engine battle: one during the opponent turn covered by Frost Barrier and one
on the following opponent turn.  The secondary formulation is a no-barrier
control.  The runner never sets a seed, coin, deck order, HP, status, or
engine field; it only submits legal actions selected from public semantics.
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from ptcg_rl.g1.actions import CompoundActionBuilder, validate_compound_action
from ptcg_rl.g1.models import ContractViolation, EngineObservationV1, SelectionRequestV1
from ptcg_rl.g1.native import NativeCABTTransport
from ptcg_rl.g1.semantic import AREA, semantic_snapshot

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.deterministic.phase_a_route_capsules_v1 import (  # noqa: E402
    ProbePolicy,
    _entity_card,
    _event_dict,
)

DEFAULT_CONFIG = ROOT / "configs/deterministic/phase_a_frost_barrier_capsule_v1.json"
DEFAULT_REPORT = ROOT / "reports/deterministic/phase-a-frost-barrier-capsule-v1.json"

RELIABILITY_COUNTER_KEYS = (
    "invalid_actions", "semantic_contract_failures", "request_cap_failures", "timeouts",
    "native_errors", "fallbacks", "post_terminal_actions", "unclassified_terminal",
    "incomplete_games", "other_failures",
)

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
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


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


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    expected = {"schema_version", "record_id", "knowledge_base_ids", "candidate", "opponent", "formulations", "assets", "limits", "attack_contract", "deck_specs"}
    if set(config) != expected or config["schema_version"] != 1 or config["record_id"] != "phase-a-frost-barrier-capsule-v1":
        raise ValueError("Frost Barrier config identity/keys differ")
    if config["knowledge_base_ids"] != ["DR-025", "DR-030", "DR-033", "AP-014", "RQ-007"]:
        raise ValueError("Frost Barrier knowledge-base binding differs")
    if [row["id"] for row in config["formulations"]] != ["same_game_expiry", "no_barrier_baseline"]:
        raise ValueError("the two preregistered formulations are required")
    limits = config["limits"]
    if limits["games_per_formulation"] < 2 or limits["games_per_formulation"] > 24 or limits["wall_seconds"] > 600:
        raise ValueError("Frost Barrier bounds exceed reviewed ceiling")
    contract = config["attack_contract"]
    if contract["barrier_attack_id"] != 1047 or contract["fixed_attack_id"] != 1089 or contract["fixed_base_damage"] != 40 or contract["barrier_reduction"] != 30:
        raise ValueError("attack contract differs from local card table")
    for spec in config["deck_specs"].values():
        if sum(int(value) for value in spec.values()) != 60:
            raise ValueError("deck is not exactly 60 cards")
        if any(int(card_id) != 3 and int(count) > 4 for card_id, count in spec.items()):
            raise ValueError("deck exceeds four-copy limit")
        if not any(int(card_id) not in {3} for card_id in spec):
            raise ValueError("deck has no Basic Pokemon")
    return config


def _validate_assets(config: Mapping[str, Any]) -> dict[str, str]:
    observed: dict[str, str] = {}
    for key, path in ASSET_PATHS.items():
        if not path.is_file():
            raise FileNotFoundError(path)
        observed[key] = sha256(path)
        if observed[key] != config["assets"][key]:
            raise ValueError(f"asset hash mismatch for {key}: {observed[key]}")
    table = json.loads(ASSET_PATHS["card_table_file_sha256"].read_text(encoding="utf-8"))
    cards = {row["card_id"]: row for row in table["cards"]}
    attacks = {row["attack_id"]: row for row in table["attacks"]}
    if 1089 not in cards[754]["attack_ids"] or attacks[1089]["damage"] != 40:
        raise ValueError("fixed Mega Latias attack does not match the local card table")
    if cards[754]["weakness_type"] != -1 or cards[754]["resistance_type"] != -1:
        raise ValueError("fixed target card has an unexpected weakness or resistance")
    if cards[723]["weakness_type"] != 8 or cards[723]["resistance_type"] != -1:
        raise ValueError("Mega Abomasnow weakness/resistance does not match the local card table")
    return observed


def _public_cards(observation: EngineObservationV1) -> list[dict[str, Any]]:
    return [
        {
            "entity_key": entity.entity_key, "card_id": entity.card_id, "serial": entity.serial,
            "owner": entity.owner, "zone": entity.zone, "position": entity.position,
            "parent_entity_key": entity.parent_entity_key, "hp": entity.hp, "max_hp": entity.max_hp,
            "damage": entity.damage, "energy_types": list(entity.energy_types),
            "attached_energy_count": entity.attached_energy_count, "statuses": list(entity.statuses),
        }
        for entity in observation.entities
        if entity.card_id is not None
    ]


def _entity(observation: EngineObservationV1, *, owner: int, zone: int, card_id: int | None = None, serial: int | None = None) -> Any:
    matches = [entity for entity in observation.entities if entity.owner == owner and entity.zone == zone]
    if card_id is not None:
        matches = [entity for entity in matches if entity.card_id == card_id]
    if serial is not None:
        matches = [entity for entity in matches if entity.serial == serial]
    return matches[0] if len(matches) == 1 else None


def _source_target_cards(observation: EngineObservationV1, option: Any) -> tuple[int | None, int | None]:
    return _entity_card(observation, option.source_entity_key), _entity_card(observation, option.target_entity_key)


def _option_score(observation: EngineObservationV1, request: SelectionRequestV1, index: int, *, fixed_attack: bool) -> tuple[int, int, int]:
    option = request.options[index]
    source, target = _source_target_cards(observation, option)
    score = 0
    if option.option_type == 2:
        score = 5000
    elif option.option_type == 1:
        score = -5000
    if option.option_type == 14:
        score = -1000
    if fixed_attack and option.attack_id == 1089:
        score = 10000
    elif not fixed_attack and option.attack_id is not None:
        score = -10000
    if option.option_type == 7 and source == 754:
        score = 9500
    if option.option_type in {3, 7} and source == 754:
        score = 9400
    if option.option_type in {5, 6, 8} and source == 3 and target == 754:
        score = 9000
    if option.option_type in {5, 6, 8} and source == 3 and target is None:
        score = max(score, 8000)
    if option.option_type == 9 and source == 723 and target == 722:
        score = 8500
    return score, -int(source or 0), -index


def _choose_scored(observation: EngineObservationV1, request: SelectionRequestV1, *, fixed_attack: bool) -> Any:
    builder = CompoundActionBuilder(request)
    candidates = [index for index, option in enumerate(request.options) if option.available]
    candidates.sort(key=lambda index: _option_score(observation, request, index, fixed_attack=fixed_attack), reverse=True)
    if request.selection_type == 0 and request.min_count == 0:
        candidates = [index for index in candidates if _option_score(observation, request, index, fixed_attack=fixed_attack)[0] > 0][:1]
    elif request.selection_type in {1, 2, 3, 4, 5, 6, 7, 8, 9, 10}:
        candidates = candidates[: max(request.min_count, 1)]
    for index in candidates:
        if builder.complete:
            break
        builder.choose(index)
    if not builder.complete:
        builder.stop()
    return validate_compound_action(request, builder.build())


class FixedOpponentPolicy:
    policy_id = "phase-a-frost-fixed-opponent-v1"

    def reset(self, episode_uuid: str, player_index: int, reason: str = "start") -> None:
        return None

    def choose(self, observation: EngineObservationV1, request: SelectionRequestV1) -> Any:
        return _choose_scored(observation, request, fixed_attack=True)


class BarrierPolicy(ProbePolicy):
    """Use the existing public probe until Barrier, then preserve the probe state."""

    def __init__(self, variant: int) -> None:
        super().__init__("frost_barrier", variant)
        self.barrier_selected = False

    def reset(self, episode_uuid: str, player_index: int, reason: str = "start") -> None:
        super().reset(episode_uuid, player_index, reason)
        self.barrier_selected = False

    def choose(self, observation: EngineObservationV1, request: SelectionRequestV1) -> Any:
        if self.barrier_selected and request.selection_type == 0:
            end = next((index for index, option in enumerate(request.options) if option.option_type == 14 and option.available), None)
            if end is not None:
                builder = CompoundActionBuilder(request)
                builder.choose(end)
                return validate_compound_action(request, builder.build())
        action = super().choose(observation, request)
        if any(request.options[index].attack_id == 1047 for index in action.submitted_original_indices):
            self.barrier_selected = True
        return action


class NoAttackPolicy(ProbePolicy):
    """Reach a visible Mega Abomasnow, then end turns rather than attacking."""

    def choose(self, observation: EngineObservationV1, request: SelectionRequestV1) -> Any:
        active = _entity(observation, owner=request.acting_player, zone=AREA["ACTIVE"])
        if active is not None and active.card_id == 723 and request.selection_type == 0:
            end = next((index for index, option in enumerate(request.options) if option.option_type == 14 and option.available), None)
            if end is not None:
                builder = CompoundActionBuilder(request)
                builder.choose(end)
                return validate_compound_action(request, builder.build())
        return super().choose(observation, request)


def _attack_events(events: tuple[Any, ...], attack_id: int, player: int) -> list[dict[str, Any]]:
    return [_event_dict(event) for event in events if event.event_name == "ATTACK" and event.fields.get("attackId") == attack_id and event.fields.get("playerIndex") == player]


def _target_hp_delta(before: EngineObservationV1, after: EngineObservationV1, events: tuple[Any, ...], target_serial: int, target_player: int) -> tuple[int | None, dict[str, Any] | None, Any, Any]:
    old = _entity(before, owner=target_player, zone=AREA["ACTIVE"], serial=target_serial)
    new = _entity(after, owner=target_player, zone=AREA["ACTIVE"], serial=target_serial)
    changes = [event for event in events if event.event_name == "HP_CHANGE" and event.fields.get("playerIndex") == target_player and event.fields.get("serial") == target_serial]
    event_change = sum(-int(event.fields["value"]) for event in changes if isinstance(event.fields.get("value"), int) and int(event.fields["value"]) < 0)
    delta = None if old is None or new is None else old.hp - new.hp
    if delta is None and changes:
        delta = event_change
    return delta, (_event_dict(changes[0]) if changes else None), old, new


def _record_attack(before: EngineObservationV1, after: EngineObservationV1, events: tuple[Any, ...], *, attack_id: int, player: int, target_player: int, barrier: bool, source_transition: int) -> dict[str, Any] | None:
    attacks = _attack_events(events, attack_id, player)
    if len(attacks) != 1:
        return None
    attack_fields = attacks[0]["fields"]
    target = _entity(before, owner=target_player, zone=AREA["ACTIVE"])
    if target is None or target.serial is None:
        return None
    delta, hp_event, old, new = _target_hp_delta(before, after, events, target.serial, target_player)
    if old is None or new is None or delta is None:
        return None
    return {
        "source_transition": source_transition, "before_turn": before.turn, "after_turn": after.turn,
        "acting_player": player, "target_player": target_player,
        "attack_id": attack_fields.get("attackId"), "attacker_card_id": attack_fields.get("cardId"),
        "attacker_serial": attack_fields.get("serial"), "target_card_id": old.card_id,
        "target_serial": old.serial, "target_hp_before": old.hp, "target_hp_after": new.hp,
        "target_damage_before": old.damage, "target_damage_after": new.damage,
        "target_statuses_before": list(old.statuses), "target_statuses_after": list(new.statuses),
        "hp_delta": delta, "hp_change_event": hp_event, "barrier_window": barrier,
        "attack_event": attacks[0],
        "confounds": {
            "target_still_active": new.zone == AREA["ACTIVE"],
            "target_serial_stable": old.serial == new.serial,
            "target_card_stable": old.card_id == new.card_id,
            "target_status_free": not old.statuses and not new.statuses,
            "target_not_ko": new.hp is not None and new.hp > 0,
        },
    }


def _resolve_pending_attack(item: Mapping[str, Any], after: EngineObservationV1) -> dict[str, Any] | None:
    """Resolve an attack when the native wrapper emits its HP event later."""
    target_serial = item["target_serial"]
    events = after.public_events
    changes = [event for event in events if event.event_name == "HP_CHANGE" and event.fields.get("playerIndex") == item["target_player"] and event.fields.get("serial") == target_serial]
    if len(changes) != 1:
        return None
    before = item["before"]
    old = _entity(before, owner=item["target_player"], zone=AREA["ACTIVE"], serial=target_serial)
    new = _entity(after, owner=item["target_player"], zone=AREA["ACTIVE"], serial=target_serial)
    if old is None or new is None or not isinstance(changes[0].fields.get("value"), int):
        return None
    value = int(changes[0].fields["value"])
    if value >= 0:
        return None
    return {
        "source_transition": item["source_transition"], "resolution_transition": after.transition_id,
        "before_turn": before.turn, "after_turn": after.turn, "acting_player": item["player"],
        "target_player": item["target_player"], "attack_id": item["attack_id"],
        "attacker_card_id": item["attacker_card_id"], "attacker_serial": item["attacker_serial"],
        "target_card_id": old.card_id, "target_serial": old.serial,
        "target_hp_before": old.hp, "target_hp_after": new.hp,
        "target_damage_before": old.damage, "target_damage_after": new.damage,
        "target_statuses_before": list(old.statuses), "target_statuses_after": list(new.statuses),
        "hp_delta": -value, "hp_change_event": _event_dict(changes[0]),
        "barrier_window": bool(item.get("barrier_window", False)), "attack_event": item["attack_event"],
        "confounds": {
            "target_still_active": new.zone == AREA["ACTIVE"], "target_serial_stable": old.serial == new.serial,
            "target_card_stable": old.card_id == new.card_id, "target_status_free": not old.statuses and not new.statuses,
            "target_not_ko": new.hp is not None and new.hp > 0,
        },
    }


def _new_state() -> dict[str, Any]:
    return {
        "barriers": [],
        "responses": [],
        "evidence": [],
        "invariant_failures": Counter(),
        "attempts": 0,
        "games": [],
        "games_requested": 0,
    }


def _run_game(config: Mapping[str, Any], formulation: str, game_index: int, state: dict[str, Any]) -> dict[str, Any]:
    candidate = expand_deck(config["deck_specs"]["candidate"])
    opponent = expand_deck(config["deck_specs"]["opponent"])
    candidate_player = game_index % 2
    decks = (candidate, opponent) if candidate_player == 0 else (opponent, candidate)
    candidate_policy = BarrierPolicy(game_index % 3) if formulation == "same_game_expiry" else NoAttackPolicy(None, game_index % 3)
    opponent_policy = FixedOpponentPolicy()
    policies = (candidate_policy, opponent_policy) if candidate_player == 0 else (opponent_policy, candidate_policy)
    battle_id = f"phase-a-frost-barrier-{formulation}-{game_index}"
    engine = NativeCABTTransport(ROOT / config["assets"]["engine_root"])
    raw = engine.start(*decks)
    counters = Counter()
    started = time.monotonic()
    transition = 0
    barrier_record: dict[str, Any] | None = None
    pending: list[dict[str, Any]] = []
    response_target_serial: int | None = None
    barrier_proof_complete = False

    def process_resolved(record: dict[str, Any]) -> None:
        nonlocal barrier_record, response_target_serial, barrier_proof_complete
        before = record.pop("before")
        record["game_index"] = game_index
        record["candidate_player"] = candidate_player
        if record["attack_id"] == 1047 and formulation == "same_game_expiry" and barrier_record is None:
            attacker = _entity(before, owner=candidate_player, zone=AREA["ACTIVE"])
            target = _entity(before, owner=1 - candidate_player, zone=AREA["ACTIVE"])
            if (
                target is None or target.card_id != 754 or attacker is None or attacker.card_id != 723
                or attacker.attached_energy_count < 3 or record["hp_delta"] != 200
                or not all(record["confounds"].values())
            ):
                state["invariant_failures"]["barrier_activation_confounded"] += 1
            else:
                barrier_record = record
                barrier_record["barrier_turn"] = record["before_turn"]
                # Frost Barrier protects its attacker, not its attack target.
                # Keep this identity for the subsequent response proof.
                barrier_record["protected_source_serial"] = record["attacker_serial"]
                barrier_record["protected_source_card_id"] = record["attacker_card_id"]
                barrier_record["target_initial_hp"] = target.hp
                barrier_record["target_weakness_type"] = -1
                barrier_record["target_resistance_type"] = -1
                state["barriers"].append(barrier_record)
            return
        if record["attack_id"] != 1089:
            return
        if formulation == "same_game_expiry":
            if barrier_record is None or barrier_proof_complete:
                return
            source_turn = int(record["before_turn"] or -1)
            barrier_turn = int(barrier_record["barrier_turn"])
            # The native turn counter can advance by more than one between
            # observed opponent turns (for example after a compound action).
            # Classify the exact next opponent turn as covered and any later
            # opponent turn as expired; never infer an earlier transition.
            expected_window = True if source_turn == barrier_turn + 1 else False if source_turn > barrier_turn + 1 else None
            if expected_window is None:
                state["invariant_failures"]["response_turn_before_barrier"] += 1
                return
            record["target_required_card_id"] = 723
            record["protected_source_serial"] = barrier_record.get("protected_source_serial")
            record["protected_source_card_id"] = barrier_record.get("protected_source_card_id")
            record["barrier_target_serial"] = barrier_record.get("target_serial")
            record["barrier_turn"] = barrier_turn
            record["barrier_window"] = expected_window
            if (
                record["target_card_id"] != 723
                or record["target_serial"] != barrier_record.get("protected_source_serial")
                or not all(record["confounds"].values())
            ):
                state["invariant_failures"]["response_target_confounded"] += 1
                return
            if expected_window:
                response_target_serial = record["target_serial"]
            elif record["target_serial"] != response_target_serial:
                state["invariant_failures"]["response_serial_changed_before_expiry"] += 1
                return
            record["attacker_weakness_type"] = -1
            record["attacker_resistance_type"] = -1
            state["responses"].append(record)
            if not expected_window:
                barrier_proof_complete = True
            return
        record["target_required_card_id"] = 723
        if record["target_card_id"] == 723 and all(record["confounds"].values()):
            record["attacker_weakness_type"] = -1
            record["attacker_resistance_type"] = -1
            state["responses"].append(record)

    try:
        while transition < config["limits"]["request_cap_per_game"]:
            if time.monotonic() - started > config["limits"]["wall_seconds"]:
                counters["timeouts"] += 1
                break
            before, request = semantic_snapshot(raw, battle_id, transition, config["assets"]["card_data_sha256"])
            if before.terminal_result is not None:
                break
            if request is None:
                counters["semantic_contract_failures"] += 1
                break
            policy = policies[request.acting_player]
            action = policy.choose(before, request)
            raw_after = engine.select(action.submitted_original_indices)
            after, _ = semantic_snapshot(raw_after, battle_id, transition + 1, config["assets"]["card_data_sha256"])
            events = after.public_events
            if barrier_record is not None and response_target_serial is None:
                protected = _entity(
                    after,
                    owner=candidate_player,
                    zone=AREA["ACTIVE"],
                    serial=barrier_record.get("protected_source_serial"),
                )
                if protected is None or protected.card_id != 723:
                    state["invariant_failures"]["barrier_source_left_active_or_evolved"] += 1
            if request.acting_player == candidate_player and any(request.options[index].attack_id == 1047 for index in action.submitted_original_indices):
                state["attempts"] += 1
            for item in list(pending):
                if any(event.event_name == "HP_CHANGE" and event.fields.get("playerIndex") == item["target_player"] and event.fields.get("serial") == item["target_serial"] for event in events):
                    record = _resolve_pending_attack(item, after)
                    pending.remove(item)
                    if record is not None:
                        record["before"] = item["before"]
                        process_resolved(record)
            selected_attack_ids = [request.options[index].attack_id for index in action.submitted_original_indices if request.options[index].attack_id in {1047, 1089}]
            for attack_id in selected_attack_ids:
                attacks = _attack_events(events, attack_id, request.acting_player)
                target = _entity(before, owner=1 - request.acting_player, zone=AREA["ACTIVE"])
                attacker = _entity(before, owner=request.acting_player, zone=AREA["ACTIVE"])
                if len(attacks) != 1 or target is None or target.serial is None or attacker is None or attacker.serial is None:
                    continue
                item = {
                    "attack_id": attack_id, "player": request.acting_player, "target_player": 1 - request.acting_player,
                    "target_serial": target.serial, "attacker_card_id": attacker.card_id, "attacker_serial": attacker.serial,
                    "source_transition": transition, "before": before, "attack_event": attacks[0],
                }
                if any(event.event_name == "HP_CHANGE" and event.fields.get("playerIndex") == item["target_player"] and event.fields.get("serial") == item["target_serial"] for event in events):
                    record = _resolve_pending_attack(item, after)
                    if record is not None:
                        record["before"] = before
                        process_resolved(record)
                else:
                    pending.append(item)
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
    if pending:
        state["invariant_failures"]["unresolved_attack_effect"] += len(pending)
    return {
        "formulation": formulation, "game_index": game_index, "candidate_player": candidate_player,
        "requests": transition, "terminal_result": before.terminal_result if "before" in locals() else None,
        "counters": _normalise_counters(counters), "barrier_captured": barrier_record is not None,
        "fixed_attacks_captured": len([row for row in state["responses"] if row.get("source_transition", -1) < transition]),
    }


def _verdict(formulation: str, state: Mapping[str, Any]) -> tuple[str, str]:
    games = list(state.get("games", ()))
    requested = int(state.get("games_requested", 0))
    seat_counts = Counter(row.get("candidate_player") for row in games)
    coverage_ok = (
        requested > 0
        and len(games) == requested
        and all(row.get("terminal_result") is not None for row in games)
        and seat_counts == {0: requested // 2, 1: requested // 2}
        and requested % 2 == 0
    )
    if not coverage_ok:
        return "PARTIAL", (
            f"coverage incomplete: games={len(games)}/{requested}, "
            f"terminal={sum(row.get('terminal_result') is not None for row in games)}/{len(games)}, "
            f"candidate_seats={dict(seat_counts)}"
        )

    # A repeated serialized transition must never manufacture a second
    # causal observation.  Keep this check independent from proof-game sets.
    seen: set[tuple[Any, ...]] = set()
    for row in state["barriers"] + state["responses"]:
        key = (
            row.get("game_index"), row.get("attack_id"), row.get("source_transition"),
            row.get("resolution_transition"), row.get("attacker_serial"), row.get("target_serial"),
        )
        if key in seen:
            return "PARTIAL", "duplicate serialized attack evidence cannot establish an independent causal proof"
        seen.add(key)
    rows = list(state["responses"])
    if formulation == "same_game_expiry":
        proof_games = set()
        for barrier in state["barriers"]:
            game = barrier["game_index"]
            covered = [row for row in rows if row.get("game_index") == game and row.get("barrier_window") is True and row.get("hp_delta") == 10 and all(row["confounds"].values())]
            expired = [row for row in rows if row.get("game_index") == game and row.get("barrier_window") is False and row.get("hp_delta") == 40 and all(row["confounds"].values())]
            if covered and expired and covered[0]["target_serial"] == expired[0]["target_serial"]:
                proof_games.add(game)
        if proof_games and not state["invariant_failures"]:
            return "PASS", "same target serial received 10 damage during the next opponent turn and 40 after the window expired"
        return "PARTIAL", f"captured barriers={len(state['barriers'])}, complete same-game expiry pairs={len(proof_games)}; controls remain incomplete"
    by_target: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for row in rows:
        if all(row["confounds"].values()) and row["hp_delta"] == 40:
            by_target.setdefault((row["game_index"], row["target_serial"]), []).append(row)
    qualifying = [group for group in by_target.values() if len(group) >= 2]
    if qualifying and not state["invariant_failures"]:
        return "PASS", "same fixed attack measured at 40 damage twice without Barrier"
    return "PARTIAL", f"captured {sum(len(group) for group in qualifying)} qualifying same-target 40-damage baseline attacks"


def _write_sealed_json(path: Path, payload: Mapping[str, Any]) -> tuple[str, int]:
    path.parent.mkdir(parents=True, exist_ok=False)
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    with os.fdopen(descriptor, "wb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    path.chmod(0o444)
    digest = sha256(path)
    sidecar = path.with_suffix(path.suffix + ".sha256")
    sidecar.write_text(f"{digest}  {path.name}\n", encoding="ascii")
    sidecar.chmod(0o444)
    return digest, len(data)


def run_experiment(config: Mapping[str, Any], config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config_path = config_path.resolve()
    observed = _validate_assets(config)
    source_hashes = {path.relative_to(ROOT).as_posix(): sha256(path) for path in SOURCE_PATHS}
    deck_hashes = {name: canonical_hash(sorted(expand_deck(spec))) for name, spec in config["deck_specs"].items()}
    started = time.monotonic()
    formulations: dict[str, Any] = {}
    games: list[dict[str, Any]] = []
    all_counters = Counter()
    for formulation in config["formulations"]:
        if time.monotonic() - started > config["limits"]["wall_seconds"]:
            break
        formulation_id = formulation["id"]
        state = _new_state()
        requested = config["limits"]["games_per_formulation"]
        for game_index in range(requested):
            if time.monotonic() - started > config["limits"]["wall_seconds"]:
                break
            game = _run_game(config, formulation_id, game_index, state)
            games.append(game)
            state["games"].append(game)
            all_counters.update(game["counters"])
        state["games_requested"] = requested
        status, reason = _verdict(formulation_id, state)
        formulations[formulation_id] = {
            "status": status, "reason": reason, "games_requested": requested,
            "games_completed": sum(1 for row in games if row["formulation"] == formulation_id),
            "candidate_attack_attempts": state["attempts"], "barrier_count": len(state["barriers"]),
            "response_count": len(state["responses"]), "invariant_failures": dict(state["invariant_failures"]),
            "evidence": state["barriers"] + state["responses"],
        }
    card_table = json.loads(ASSET_PATHS["card_table_file_sha256"].read_text(encoding="utf-8"))
    attacks = {int(row["attack_id"]): row for row in card_table["attacks"]}
    observed_attack_ids = sorted({
        int(row["attack_id"])
        for formulation in formulations.values()
        for row in formulation["evidence"]
        if row.get("attack_id") is not None
    })
    response_contract_audit = {
        "required_response_attack_id": 1042,
        "required_response_static_damage": 40,
        "configured_response_attack_id": int(config["attack_contract"]["fixed_attack_id"]),
        "configured_response_card_id": int(config["attack_contract"]["fixed_card_id"]),
        "configured_response_static_damage": int(config["attack_contract"]["fixed_base_damage"]),
        "card_table_required_response_damage": attacks.get(1042, {}).get("damage"),
        "card_table_configured_response_damage": attacks.get(int(config["attack_contract"]["fixed_attack_id"]), {}).get("damage"),
        "observed_attack_ids": observed_attack_ids,
        "exact_required_response_available": (
            int(config["attack_contract"]["fixed_attack_id"]) == 1042
            and attacks.get(1042, {}).get("damage") == 40
            and 1042 in observed_attack_ids
        ),
    }
    if not response_contract_audit["exact_required_response_available"]:
        for row in formulations.values():
            if row["status"] == "PASS":
                row["status"] = "PARTIAL"
            row["reason"] += "; required response attack 1042/static 40 contract is not evidenced"
    return {
        "schema_version": 1, "record_id": config["record_id"], "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "SUCCEEDED" if not any(all_counters.values()) else "FAILED", "decision": "FROST_BARRIER_NEXT_TURN_DAMAGE_MODIFIER",
        "provenance": {
            "config_path": config_path.relative_to(ROOT).as_posix(), "config_sha256": sha256(config_path),
            "runner_path": Path(__file__).resolve().relative_to(ROOT).as_posix(), "runner_sha256": sha256(Path(__file__).resolve()),
            "observed_asset_hashes": observed, "source_hashes": source_hashes, "deck_multiset_sha256": deck_hashes,
            "engine_library_sha256": config["assets"]["engine_library_sha256"], "wrapper_sha256": config["assets"]["wrapper_sha256"],
            "api_sha256": config["assets"]["api_sha256"], "card_data_sha256": config["assets"]["card_data_sha256"],
            "native_randomness": "official engine controlled; no manual seed, coin, deck order, HP, status, or outcome",
            "command": shlex.join(["rtk", "uv", "--cache-dir", "data/cache/uv", "run", "python", *[Path(value).resolve().relative_to(ROOT).as_posix() if Path(value).exists() else Path(value).name for value in sys.argv]]),
        },
        "scope": {"formulations": [row["id"] for row in config["formulations"]], "games_requested": len(config["formulations"]) * config["limits"]["games_per_formulation"], "games_completed": len(games), "policy_strength_claimed": False, "promotion_authorized": False},
        "fail_closed_counters": _normalise_counters(all_counters), "games": games, "formulations": formulations,
        "response_contract_audit": response_contract_audit,
        "knowledge_base": {"database": "knowledge_base/ptcg_gold.sqlite", "ids": config["knowledge_base_ids"], "requeried_before_run": True},
    }


def compact_report(full: Mapping[str, Any], raw_path: Path, raw_digest: str, raw_bytes: int) -> dict[str, Any]:
    report = {key: full[key] for key in ("schema_version", "record_id", "created_at_utc", "status", "decision", "provenance", "scope", "fail_closed_counters", "games", "knowledge_base", "response_contract_audit")}
    report["formulations"] = {key: {k: value for k, value in row.items() if k != "evidence"} for key, row in full["formulations"].items()}
    report["formulations"] = {key: {**row, "evidence_digest": canonical_hash(full["formulations"][key]["evidence"])} for key, row in report["formulations"].items()}
    report["raw_evidence"] = {"path": raw_path.relative_to(ROOT).as_posix(), "bytes": raw_bytes, "sha256": raw_digest, "sealed_read_only": True, "content": "complete native Frost Barrier transition evidence retained privately under ignored runs/"}
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()
    args.config = args.config.resolve()
    config = load_config(args.config)
    full = run_experiment(config, args.config)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    raw_path = ROOT / "runs" / f"phase-a-frost-barrier-{stamp}-{uuid.uuid4().hex[:12]}" / "raw-evidence.json"
    digest, size = _write_sealed_json(raw_path, full)
    report = compact_report(full, raw_path, digest, size)
    args.report = args.report.resolve()
    if ROOT not in args.report.parents:
        raise ValueError("report must stay inside repository")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "formulations": {key: value["status"] for key, value in report["formulations"].items()}, "games": report["scope"]["games_completed"], "raw_evidence": report["raw_evidence"]}, sort_keys=True))
    return 0 if report["status"] == "SUCCEEDED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
