"""Bounded Phase A v2 live route-card semantic coverage experiment.

The official native engine owns all shuffles, coins, and other randomness.  The
runner records a hash chain over public before/request/action/after records and
retains only aggregate counters, invariant results, and hashes in its report.
It never reads an opponent hand when that hand is hidden, changes engine state,
or treats card metadata as executable semantics.
"""

from __future__ import annotations

import csv
import hashlib
import json
import time
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from ptcg_rl.g1.actions import validate_compound_action
from ptcg_rl.g1.models import ContractViolation, EngineObservationV1, LegalOptionV1, SelectionRequestV1
from ptcg_rl.g1.native import NativeCABTTransport, load_deck
from ptcg_rl.g1.rule_baseline import NativeRulePolicy
from ptcg_rl.g1.semantic import AREA, LOG_NAMES, semantic_snapshot
from ptcg_rl.g2.card_table import CardTableV1, verify_card_table


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs/deterministic/phase_a_native_semantics_v2.json"
DEFAULT_REPORT = ROOT / "reports/deterministic/phase-a-native-semantics-v2.json"
CARD_DATA_SHA256 = "a0ea63cf7adcb65d35436ce0eb390de6e2e35654a7c67c065a45f4abaa00f373"

_CONFIG_KEYS = {
    "schema_version", "record_id", "phase", "candidate_baseline", "matrix", "assets",
    "limits", "coverage", "knowledge_base_ids",
}
_ASSET_KEYS = {
    "card_data", "card_table", "engine_root", "engine_library_sha256", "wrapper_sha256",
    "api_sha256", "baselines",
}
_HASH_ITEM_KEYS = {"path", "sha256"}
_LIMIT_KEYS = {"games_max", "wall_seconds", "request_cap_per_game"}
_COVERAGE_KEYS = {
    "minimum_completed_games", "required_static_cards", "route_effect_card_ids",
    "required_static_attack_cards", "route_attack_card_ids", "unobserved_status", "unverifiable_status",
}
_CSV_COLUMNS = {
    "Card ID", "Card Name", "Expansion", "Collection No.",
    "Stage (Pokémon)/Type (Energy and Trainer)", "Rule", "Category",
    "Previous stage", "HP", "Type", "Weakness", "Resistance (Type)",
    "Retreat", "Move Name", "Cost", "Damage", "Effect Explanation",
}
_ROUTE_CARD_METADATA = {
    3: ("Basic {W} Energy", "Basic Energy", "n/a"),
    721: ("Kyogre", "Basic Pokémon", "n/a"),
    722: ("Snover", "Basic Pokémon", "n/a"),
    723: ("Mega Abomasnow ex", "Stage 1 Pokémon", "Snover"),
    1121: ("Ultra Ball", "Item", "n/a"),
    1126: ("Precious Trolley", "Item", "n/a"),
    1192: ("Carmine", "Supporter", "n/a"),
    1227: ("Lillie's Determination", "Supporter", "n/a"),
    1262: ("Surfing Beach", "Stadium", "n/a"),
}
_ROUTE_LABELS = {
    3: "basic_water_energy",
    721: "kyogre",
    722: "snover",
    723: "mega_abomasnow",
    1121: "ultra_ball",
    1126: "precious_trolley",
    1192: "carmine",
    1227: "lillie_determination",
    1262: "surfing_beach",
}
_ATTACKS_BY_CARD = {
    721: {1042, 1043},
    722: {1044, 1045},
    723: {1046, 1047},
}
_ROUTE_ATTACK_IDS = {attack_id for values in _ATTACKS_BY_CARD.values() for attack_id in values}
_ROUTE_EFFECT_IDS = {1121, 1126, 1192, 1227, 1262}
_ROUTE_IDS = set(_ROUTE_LABELS)
_EXPECTED_STATIC_CARD_IDS = frozenset(_ROUTE_IDS)
_EXPECTED_STATIC_ATTACK_CARD_IDS = frozenset(_ATTACKS_BY_CARD)
_EXPECTED_ROUTE_EFFECT_CARD_IDS = frozenset(_ROUTE_EFFECT_IDS)
_EXPECTED_ROUTE_ATTACK_CARD_IDS = frozenset(_ATTACKS_BY_CARD)
_EVENT_FIELDS = {
    "cardId", "cardIdActive", "cardIdBench", "cardIdBefore", "cardIdAfter", "cardIdTarget",
}
_EVENT_TYPE_BY_NAME = {name: event_type for event_type, name in LOG_NAMES.items()}


class _V2ContractViolation(ContractViolation):
    def __init__(self, message: str, counter_name: str) -> None:
        super().__init__(message)
        self.counter_name = counter_name


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    if set(value) != expected:
        missing = sorted(expected - set(value))
        extra = sorted(set(value) - expected)
        raise ValueError(f"{name} keys differ; missing={missing}, extra={extra}")


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    value = _mapping(json.loads(path.read_text(encoding="utf-8")), "config")
    _exact_keys(value, _CONFIG_KEYS, "config")
    if value["schema_version"] != 2 or value["record_id"] != "phase-a-native-semantics-v2":
        raise ValueError("unsupported Phase A v2 config identity")
    if value["phase"] != "A" or value["candidate_baseline"] != "mega-abomasnow-ex":
        raise ValueError("Phase A v2 candidate identity is fixed")
    matrix = value["matrix"]
    if not isinstance(matrix, list) or not matrix or sum(item.get("games", 0) for item in matrix) > 8:
        raise ValueError("matrix must contain at most eight requested games")
    opponents: set[str] = set()
    for index, item in enumerate(matrix):
        row = _mapping(item, f"matrix[{index}]")
        _exact_keys(row, {"opponent_baseline", "games"}, f"matrix[{index}]")
        if not isinstance(row["opponent_baseline"], str) or not row["opponent_baseline"]:
            raise ValueError("matrix opponent identity must be nonempty")
        if row["opponent_baseline"] == value["candidate_baseline"] and row["opponent_baseline"] not in {"mega-abomasnow-ex"}:
            raise ValueError("invalid mirror opponent")
        if isinstance(row["games"], bool) or not isinstance(row["games"], int) or not 1 <= row["games"] <= 8:
            raise ValueError("matrix games must be between one and eight")
        opponents.add(row["opponent_baseline"])
    if sum(item["games"] for item in matrix) > 8:
        raise ValueError("matrix exceeds eight-game ceiling")
    assets = _mapping(value["assets"], "assets")
    _exact_keys(assets, _ASSET_KEYS, "assets")
    for name in ("card_data", "card_table"):
        item = _mapping(assets[name], f"assets.{name}")
        expected = _HASH_ITEM_KEYS | ({"semantic_sha256"} if name == "card_table" else set())
        _exact_keys(item, expected, f"assets.{name}")
        if any(not isinstance(item[key], str) or len(item[key]) != 64 for key in expected if key.endswith("sha256")):
            raise ValueError(f"assets.{name} hashes must be SHA-256 strings")
    for name in ("engine_root", "engine_library_sha256", "wrapper_sha256", "api_sha256"):
        if not isinstance(assets[name], str):
            raise ValueError(f"assets.{name} must be a string")
    baselines = _mapping(assets["baselines"], "assets.baselines")
    required_baselines = {value["candidate_baseline"], *opponents}
    if set(baselines) != required_baselines:
        raise ValueError("baseline assets must exactly match candidate and matrix opponents")
    for baseline, item in baselines.items():
        row = _mapping(item, f"assets.baselines.{baseline}")
        _exact_keys(row, {"deck", "policy"}, f"assets.baselines.{baseline}")
        for kind in ("deck", "policy"):
            asset = _mapping(row[kind], f"assets.baselines.{baseline}.{kind}")
            _exact_keys(asset, _HASH_ITEM_KEYS, f"assets.baselines.{baseline}.{kind}")
            if not isinstance(asset["path"], str) or not isinstance(asset["sha256"], str) or len(asset["sha256"]) != 64:
                raise ValueError(f"invalid baseline hash for {baseline}/{kind}")
            if Path(asset["path"]).parent.name != baseline:
                raise ValueError(f"{kind} path does not match baseline identity")
    limits = _mapping(value["limits"], "limits")
    _exact_keys(limits, _LIMIT_KEYS, "limits")
    if any(isinstance(limits[key], bool) or not isinstance(limits[key], int) for key in _LIMIT_KEYS):
        raise ValueError("limits must contain integers")
    if limits["games_max"] != 8 or not 1 <= limits["wall_seconds"] <= 180:
        raise ValueError("Phase A v2 limits exceed the bounded experiment ceiling")
    if not 1 <= limits["request_cap_per_game"] <= 20_000:
        raise ValueError("request cap exceeds the bounded experiment ceiling")
    coverage = _mapping(value["coverage"], "coverage")
    _exact_keys(coverage, _COVERAGE_KEYS, "coverage")
    minimum = coverage["minimum_completed_games"]
    if isinstance(minimum, bool) or not isinstance(minimum, int) or not 1 <= minimum <= sum(item["games"] for item in matrix):
        raise ValueError("minimum completed games is invalid")
    for name in ("required_static_cards", "required_static_attack_cards", "route_effect_card_ids", "route_attack_card_ids"):
        if not isinstance(coverage[name], list) or not coverage[name] or len(set(coverage[name])) != len(coverage[name]):
            raise ValueError(f"coverage.{name} must be a unique list")
        if any(isinstance(card_id, bool) or not isinstance(card_id, int) for card_id in coverage[name]):
            raise ValueError(f"coverage.{name} must contain integer IDs")
    if not set(coverage["required_static_attack_cards"]).issubset(set(coverage["required_static_cards"])):
        raise ValueError("required static attack cards must be among required static cards")
    if set(coverage["required_static_cards"]) != _EXPECTED_STATIC_CARD_IDS:
        raise ValueError("required static card coverage differs from the route contract")
    if set(coverage["required_static_attack_cards"]) != _EXPECTED_STATIC_ATTACK_CARD_IDS:
        raise ValueError("required static attack card coverage differs from the route contract")
    if set(coverage["route_effect_card_ids"]) != _EXPECTED_ROUTE_EFFECT_CARD_IDS:
        raise ValueError("route effect card coverage differs from the route contract")
    if set(coverage["route_attack_card_ids"]) != _EXPECTED_ROUTE_ATTACK_CARD_IDS:
        raise ValueError("route attack card coverage differs from the route contract")
    if coverage["unobserved_status"] != "INCONCLUSIVE" or coverage["unverifiable_status"] != "PARTIAL":
        raise ValueError("coverage must fail closed for missing or unverifiable effects")
    if value["knowledge_base_ids"] != ["DR-025", "DR-030", "DR-033", "AP-009", "AP-010", "AP-014", "RQ-007"]:
        raise ValueError("v2 knowledge-base binding differs")
    return dict(value)


def _repo_path(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError(f"asset path escapes repository: {relative}")
    return path


def _asset_hashes(config: Mapping[str, Any]) -> dict[str, Any]:
    assets = config["assets"]
    observed: dict[str, Any] = {}
    for name in ("card_data", "card_table"):
        item = assets[name]
        path = _repo_path(item["path"])
        if not path.is_file() or _sha256(path) != item["sha256"]:
            raise ValueError(f"asset hash mismatch: {name}")
        observed[f"{name}_sha256"] = item["sha256"]
    for name, relative in (
        ("engine_library", f"{assets['engine_root']}/cg/libcg.so"),
        ("wrapper", f"{assets['engine_root']}/cg/game.py"),
        ("api", f"{assets['engine_root']}/cg/api.py"),
    ):
        path = _repo_path(relative)
        digest = _sha256(path)
        if digest != assets[f"{name}_sha256"]:
            raise ValueError(f"asset hash mismatch: {name}")
        observed[f"{name}_sha256"] = digest
    observed["baselines"] = {}
    for baseline, row in assets["baselines"].items():
        observed["baselines"][baseline] = {}
        for kind in ("deck", "policy"):
            item = row[kind]
            path = _repo_path(item["path"])
            if not path.is_file() or _sha256(path) != item["sha256"]:
                raise ValueError(f"asset hash mismatch: {baseline}/{kind}")
            observed["baselines"][baseline][kind] = item["sha256"]
    return observed


def _load_card_rows(path: Path) -> dict[int, list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        if set(reader.fieldnames or ()) != _CSV_COLUMNS:
            raise ValueError("card CSV columns differ from the official schema")
        rows: dict[int, list[dict[str, str]]] = defaultdict(list)
        for row in reader:
            rows[int(row["Card ID"])].append({str(key): str(value).strip() for key, value in row.items()})
    return rows


def run_static_checks(config: Mapping[str, Any], hashes: Mapping[str, Any]) -> dict[str, Any]:
    assets = config["assets"]
    table_path = _repo_path(assets["card_table"]["path"])
    table = CardTableV1.from_mapping(json.loads(table_path.read_text(encoding="utf-8")))
    verification = verify_card_table(table)
    if verification["table_sha256"] != assets["card_table"]["semantic_sha256"]:
        raise ValueError("card table semantic hash differs from config")
    if table.card_data_sha256 != hashes["card_data_sha256"]:
        raise ValueError("card table card-data hash differs from config")
    if table.engine_library_sha256 != hashes["engine_library_sha256"]:
        raise ValueError("card table engine hash differs from config")
    if table.wrapper_api_sha256 != hashes["api_sha256"]:
        raise ValueError("card table API hash differs from config")
    rows = _load_card_rows(_repo_path(assets["card_data"]["path"]))
    by_id = {card.card_id: card for card in table.cards}
    attack_ids: set[int] = set()
    checked: list[int] = []
    for card_id in config["coverage"]["required_static_cards"]:
        expected = _ROUTE_CARD_METADATA.get(card_id)
        if expected is None or card_id not in by_id or card_id not in rows:
            raise ValueError(f"missing route-critical card metadata: {card_id}")
        if any(
            (row["Card Name"], row["Stage (Pokémon)/Type (Energy and Trainer)"], row["Previous stage"])
            != expected for row in rows[card_id]
        ):
            raise ValueError(f"route-critical CSV identity differs for card {card_id}")
        attack_ids.update(by_id[card_id].attack_ids)
        checked.append(card_id)
    required_attack_cards = config["coverage"]["required_static_attack_cards"]
    if not set(required_attack_cards).issubset(set(config["coverage"]["required_static_cards"])):
        raise ValueError("required static attack cards must be among required static cards")
    for card_id in required_attack_cards:
        card = by_id.get(card_id)
        if card is None or not card.attack_ids:
            raise ValueError(f"missing required static attack card metadata: {card_id}")
    candidate_deck = load_deck(_repo_path(assets["baselines"][config["candidate_baseline"]]["deck"]["path"]))
    counts = Counter(candidate_deck)
    if any(counts[card_id] == 0 for card_id in checked):
        raise ValueError("candidate deck lacks a required route card")
    if sorted(_ROUTE_ATTACK_IDS - attack_ids):
        raise ValueError("route attack metadata is incomplete")
    return {
        "status": "PASS",
        "card_table_schema_version": table.schema_version,
        "card_table_cards": len(table.cards),
        "card_table_attacks": len(table.attacks),
        "csv_rows": sum(len(value) for value in rows.values()),
        "route_cards_checked": checked,
        "route_attack_cards_checked": list(required_attack_cards),
        "route_attack_ids_checked": sorted(attack_ids),
        "candidate_deck_size": len(candidate_deck),
        "candidate_deck_distinct_ids": len(counts),
        "card_data_sha256": hashes["card_data_sha256"],
        "card_table_file_sha256": _sha256(table_path),
        "card_table_semantic_sha256": verification["table_sha256"],
        "note": "Static effect text is metadata only; executable effects require live public transition evidence.",
    }


def _counter() -> dict[str, int]:
    return {
        "semantic_contract_failures": 0,
        "invalid_actions": 0,
        "option_count_mismatches": 0,
        "option_bounds_failures": 0,
        "hidden_hand_leaks": 0,
        "unknown_observed_card_ids": 0,
        "request_cap_failures": 0,
        "timeouts": 0,
        "native_failures": 0,
        "fallback_actions": 0,
        "manual_randomness_controls": 0,
        "public_delta_contract_failures": 0,
    }


def _new_branch() -> dict[str, Any]:
    return {
        "play_actions": 0,
        "semantic_requests": 0,
        "selected_actions": 0,
        "public_after_deltas": 0,
        "public_log_events": 0,
        "skill_actions": 0,
        "request_contexts": Counter(),
        "request_bounds": Counter(),
        "selected_card_ids": Counter(),
        "causal_proofs": Counter(),
        "log_event_types": Counter(),
        "invariant_failures": Counter(),
        "observations": 0,
    }


def _new_aggregate(config: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "counters": _counter(),
        "terminal_results": [],
        "request_count": 0,
        "option_count_total": 0,
        "max_option_count": 0,
        "selection_type_counts": Counter(),
        "optional_requests": 0,
        "multiselect_requests": 0,
        "ordered_requests": 0,
        "stop_actions": 0,
        "public_log_events": 0,
        "transitions_with_logs": 0,
        "face_down_slots": 0,
        "public_reveal_entities": 0,
        "terminal_first_checks": 0,
        "stale_terminal_selections": 0,
        "route_effect_mentions": Counter(),
        "route_attack_mentions": Counter(),
        "route_card_actions": Counter(),
        "route_card_logs": Counter(),
        "route_card_after_deltas": Counter(),
        "route_card_zone_deltas": defaultdict(Counter),
        "transition_count": 0,
        "transition_digest": "0" * 64,
        "transition_shape_counts": Counter(),
        "branches": {label: _new_branch() for label in (
            "ultra_ball", "precious_trolley", "carmine", "lillie_determination",
            "surfing_beach", "kyogre_riptide", "kyogre_swirling_waves",
            "mega_abomasnow_hammer_lanche", "mega_abomasnow_frost_barrier", "snover_evolution",
        )},
        "barrier_pending": {},
        "pending_effects": {},
        "beach_skill_turns": set(),
        "matrix": {row["opponent_baseline"]: {"games": row["games"], "completed": 0} for row in config["matrix"]},
    }


def _plain_counter(value: Mapping[Any, int]) -> dict[str, int]:
    return {str(key): int(value[key]) for key in sorted(value, key=str)}


def _card_public(card: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if card is None:
        return None
    result: dict[str, Any] = {}
    for key in ("id", "serial", "playerIndex", "hp", "maxHp", "appearThisTurn"):
        if key in card and card[key] is not None:
            result[key] = card[key]
    return result


def _pokemon_public(pokemon: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if pokemon is None:
        return None
    result = _card_public(pokemon) or {}
    for key in ("energies", "energyCards", "tools", "preEvolution"):
        if key in pokemon:
            values = pokemon[key] or []
            result[key] = list(values) if key == "energies" else [_card_public(value) for value in values]
    return result


def _public_snapshot(raw: Mapping[str, Any], observation: EngineObservationV1, request: SelectionRequestV1 | None) -> dict[str, Any]:
    """Return the complete public projection without reading hidden hand identities."""

    current = raw.get("current")
    if not isinstance(current, Mapping):
        return {"lifecycle": True, "events": [asdict(event) for event in observation.public_events]}
    actor = observation.acting_player
    players = []
    for player_index, player in enumerate(current["players"]):
        hand = player.get("hand")
        if hand is not None and not isinstance(hand, list):
            raise _V2ContractViolation("public hand is neither a list nor hidden", "hidden_hand_leaks")
        # The engine exposes only the acting player's hand.  A list for the
        # other player is a contract failure, never a source of extra evidence.
        if hand is not None and player_index != actor:
            raise _V2ContractViolation("opponent hand identities are visible", "hidden_hand_leaks")
        players.append({
            "active": [_pokemon_public(value) for value in player.get("active") or []],
            "bench": [_pokemon_public(value) for value in player.get("bench") or []],
            "discard": [_card_public(value) for value in player.get("discard") or []],
            "prize": [_card_public(value) for value in player.get("prize") or []],
            "hand": [_card_public(value) for value in hand] if hand is not None else None,
            "hand_count": player.get("handCount"),
            "deck_count": player.get("deckCount"),
            "bench_max": player.get("benchMax"),
            "player_index": player_index,
        })
    result: dict[str, Any] = {
        "current": {
            "your_index": current.get("yourIndex"), "result": current.get("result"),
            "turn": current.get("turn"), "turn_action_count": current.get("turnActionCount"),
            "first_player": current.get("firstPlayer"), "supporter_played": current.get("supporterPlayed"),
            "stadium_played": current.get("stadiumPlayed"), "energy_attached": current.get("energyAttached"),
            "retreated": current.get("retreated"), "players": players,
            "stadium": [_card_public(value) for value in current.get("stadium") or []],
            "looking": [_card_public(value) for value in current.get("looking") or []],
        },
        "events": [asdict(event) for event in observation.public_events],
    }
    if request is not None:
        result["request"] = _request_payload(request, observation)
    return result


def _request_payload(request: SelectionRequestV1, observation: EngineObservationV1) -> dict[str, Any]:
    entity_ids = {entity.entity_key: entity.card_id for entity in observation.entities}
    options = []
    for option in request.options:
        item = asdict(option)
        item["source_card_id"] = entity_ids.get(option.source_entity_key)
        item["target_card_id"] = entity_ids.get(option.target_entity_key)
        options.append(item)
    return {
        "acting_player": request.acting_player,
        "selection_type": request.selection_type,
        "selection_context": request.selection_context,
        "min_count": request.min_count,
        "max_count": request.max_count,
        "remain_damage_counter": request.remain_damage_counter,
        "remain_energy_cost": request.remain_energy_cost,
        "context_card_id": request.context_card_id,
        "effect_card_id": request.effect_card_id,
        "ordering": request.ordering,
        "options": options,
    }


def _entity_card_ids(observation: EngineObservationV1) -> dict[str, int | None]:
    return {entity.entity_key: entity.card_id for entity in observation.entities}


def _option_card_id(option: LegalOptionV1, entity_ids: Mapping[str, int | None]) -> int | None:
    return option.card_id if option.card_id is not None else entity_ids.get(option.source_entity_key)


def _selected_payload(
    request: SelectionRequestV1, action: Any, observation: EngineObservationV1,
) -> dict[str, Any]:
    entity_ids = _entity_card_ids(observation)
    selected = [request.options[index] for index in action.submitted_original_indices]
    return {
        "indices": list(action.submitted_original_indices),
        "card_ids": [_option_card_id(option, entity_ids) for option in selected],
        "attack_ids": [option.attack_id for option in selected if option.attack_id is not None],
        "choice_roles": [option.choice_role for option in selected],
        "stopped_early": bool(action.stopped_early),
    }


def _public_card_locations(raw: Mapping[str, Any]) -> dict[tuple[int, int], tuple[int, str]]:
    current = raw.get("current")
    if not isinstance(current, Mapping):
        return {}
    result: dict[tuple[int, int], tuple[int, str]] = {}

    def add(card: Mapping[str, Any] | None, zone: str, owner: int) -> None:
        if card is None or not isinstance(card, Mapping):
            return
        serial = card.get("serial")
        card_id = card.get("id")
        if isinstance(serial, int) and isinstance(card_id, int):
            result[(owner, serial)] = (card_id, zone)

    for player_index, player in enumerate(current["players"]):
        hand = player.get("hand")
        if hand is not None:
            for card in hand:
                add(card, "HAND", player_index)
        for card in player.get("discard") or []:
            add(card, "DISCARD", player_index)
        for card in player.get("prize") or []:
            add(card, "PRIZE", player_index)
        for zone_name in ("active", "bench"):
            for pokemon in player.get(zone_name) or []:
                add(pokemon, zone_name.upper(), player_index)
                if pokemon is None:
                    continue
                for field, zone in (("energyCards", "ENERGY"), ("tools", "TOOL"), ("preEvolution", "PRE_EVOLUTION")):
                    for card in pokemon.get(field) or []:
                        add(card, zone, player_index)
    for card in current.get("stadium") or []:
        if isinstance(card, Mapping):
            add(card, "STADIUM", int(card.get("playerIndex", 0)))
    return result


def _public_zone_counts(raw: Mapping[str, Any], player_index: int) -> Counter[tuple[str, int]]:
    current = raw.get("current")
    counts: Counter[tuple[str, int]] = Counter()
    if not isinstance(current, Mapping):
        return counts

    def add(card: Mapping[str, Any] | None, zone: str) -> None:
        if isinstance(card, Mapping) and isinstance(card.get("id"), int):
            counts[(zone, int(card["id"]))] += 1

    player = current["players"][player_index]
    hand = player.get("hand")
    if hand is not None:
        for card in hand:
            add(card, "HAND")
    for card in player.get("discard") or []:
        add(card, "DISCARD")
    for card in player.get("prize") or []:
        add(card, "PRIZE")
    for zone_name in ("active", "bench"):
        for pokemon in player.get(zone_name) or []:
            add(pokemon, zone_name.upper())
            if pokemon is None:
                continue
            for field, zone in (("energyCards", "ENERGY"), ("tools", "TOOL"), ("preEvolution", "PRE_EVOLUTION")):
                for card in pokemon.get(field) or []:
                    add(card, zone)
    return counts


def _public_metrics(raw: Mapping[str, Any], player_index: int) -> dict[str, Any]:
    current = raw.get("current")
    if not isinstance(current, Mapping):
        return {"hand_count": None, "deck_count": None, "discard_count": 0, "bench_count": 0, "active_ids": []}
    player = current["players"][player_index]
    active_ids = [value.get("id") for value in player.get("active") or [] if isinstance(value, Mapping)]
    return {
        "hand_count": player.get("handCount"),
        "deck_count": player.get("deckCount"),
        "discard_count": len(player.get("discard") or []),
        "bench_count": sum(value is not None for value in player.get("bench") or []),
        "bench_max": player.get("benchMax"),
        "prize_count": len(player.get("prize") or []),
        "active_ids": active_ids,
        "turn": current.get("turn"),
        "turn_action_count": current.get("turnActionCount"),
    }


def _public_delta(raw_before: Mapping[str, Any], raw_after: Mapping[str, Any], player_index: int) -> dict[str, Any]:
    before_locations = _public_card_locations(raw_before)
    after_locations = _public_card_locations(raw_after)
    moves = Counter()
    for key in set(before_locations) & set(after_locations):
        before = before_locations[key]
        after = after_locations[key]
        if before != after:
            moves[(before[1], after[1], before[0])] += 1
    for key in set(before_locations) - set(after_locations):
        moves[(before_locations[key][1], "UNOBSERVABLE", before_locations[key][0])] += 1
    for key in set(after_locations) - set(before_locations):
        moves[("UNOBSERVABLE", after_locations[key][1], after_locations[key][0])] += 1
    before_counts = _public_zone_counts(raw_before, player_index)
    after_counts = _public_zone_counts(raw_after, player_index)
    zone_deltas = Counter()
    for key in set(before_counts) | set(after_counts):
        delta = after_counts[key] - before_counts[key]
        if delta:
            zone_deltas[key] = delta
    before_metrics = _public_metrics(raw_before, player_index)
    after_metrics = _public_metrics(raw_after, player_index)
    scalar_deltas = {}
    for field in ("hand_count", "deck_count", "discard_count", "bench_count", "prize_count"):
        before_value = before_metrics[field]
        after_value = after_metrics[field]
        scalar_deltas[field] = None if before_value is None or after_value is None else after_value - before_value
    return {
        "moves": _plain_counter({"%s>%s:%s" % key: value for key, value in moves.items()}),
        "zone_deltas": _plain_counter({"%s:%s" % key: value for key, value in zone_deltas.items()}),
        "scalar_deltas": scalar_deltas,
        "before": before_metrics,
        "after": after_metrics,
    }


def _route_mentions(request: SelectionRequestV1, observation: EngineObservationV1) -> set[int]:
    entity_ids = _entity_card_ids(observation)
    found = {card_id for card_id in (request.context_card_id, request.effect_card_id) if card_id in _ROUTE_IDS}
    for option in request.options:
        for card_id in (_option_card_id(option, entity_ids), entity_ids.get(option.target_entity_key)):
            if card_id in _ROUTE_IDS:
                found.add(card_id)
        if option.attack_id in _ROUTE_ATTACK_IDS:
            for card_id, attack_ids in _ATTACKS_BY_CARD.items():
                if option.attack_id in attack_ids:
                    found.add(card_id)
    return found


def _route_logs(observation: EngineObservationV1) -> tuple[set[int], Counter[str]]:
    found: set[int] = set()
    event_names: Counter[str] = Counter()
    for event in observation.public_events:
        event_names[event.event_name or str(event.event_type)] += 1
        for field in _EVENT_FIELDS:
            value = event.fields.get(field)
            if isinstance(value, int) and value in _ROUTE_IDS:
                found.add(value)
    return found, event_names


def _selected_route_ids(request: SelectionRequestV1, action: Any, observation: EngineObservationV1) -> set[int]:
    entity_ids = _entity_card_ids(observation)
    result: set[int] = set()
    for index in action.submitted_original_indices:
        option = request.options[index]
        card_id = _option_card_id(option, entity_ids)
        if card_id in _ROUTE_IDS:
            result.add(card_id)
        target_id = entity_ids.get(option.target_entity_key)
        if target_id in _ROUTE_IDS:
            result.add(target_id)
        if option.attack_id in _ROUTE_ATTACK_IDS:
            result.update(card_id for card_id, attacks in _ATTACKS_BY_CARD.items() if option.attack_id in attacks)
    return result


def _play_ids(request: SelectionRequestV1, action: Any, observation: EngineObservationV1) -> set[int]:
    entity_ids = _entity_card_ids(observation)
    return {
        _option_card_id(request.options[index], entity_ids)
        for index in action.submitted_original_indices
        if request.options[index].choice_role == "PLAY"
    } & _ROUTE_IDS


def _attack_ids(request: SelectionRequestV1, action: Any) -> set[int]:
    return {request.options[index].attack_id for index in action.submitted_original_indices if request.options[index].attack_id is not None}


def _event_count(observation: EngineObservationV1, event_name: str) -> int:
    return sum(event.event_name == event_name for event in observation.public_events)


def _event_count_for_player(
    observation: EngineObservationV1, event_name: str, player: int, card_id: int | None = None,
) -> int:
    return sum(
        event.event_name == event_name
        and event.fields.get("playerIndex") == player
        and (card_id is None or any(event.fields.get(field) == card_id for field in _EVENT_FIELDS))
        for event in observation.public_events
    )


def _zone_delta(delta: Mapping[str, Any], zone: str, card_id: int) -> int:
    return int(delta["zone_deltas"].get(f"{zone}:{card_id}", 0))


def _move_delta_count(delta: Mapping[str, Any], from_zone: str, to_zone: str) -> int:
    prefix = f"{from_zone}>{to_zone}:"
    return sum(value for key, value in delta["moves"].items() if key.startswith(prefix))


def _movement_event_count(observation: EngineObservationV1, from_area: int, to_area: int, card_id: int | None = None) -> int:
    count = 0
    for event in observation.public_events:
        fields = event.fields
        if fields.get("fromArea") != from_area or fields.get("toArea") != to_area:
            continue
        if card_id is None or fields.get("cardId") == card_id:
            count += 1
    return count


def _movement_event_count_for_player(
    observation: EngineObservationV1, from_area: int, to_area: int, player: int, card_id: int | None = None,
) -> int:
    return sum(
        event.event_name in {"MOVE_CARD", "MOVE_CARD_REVERSE"}
        and event.fields.get("playerIndex") == player
        and event.fields.get("fromArea") == from_area
        and event.fields.get("toArea") == to_area
        and (card_id is None or event.fields.get("cardId") == card_id)
        for event in observation.public_events
    )


def _record_branch(branch: dict[str, Any], *, request: bool = False, action: bool = False, after: bool = False) -> None:
    branch["semantic_requests"] += int(request)
    branch["selected_actions"] += int(action)
    branch["public_after_deltas"] += int(after)
    branch["observations"] += int(request or action or after)


def _observe_route_transition(
    aggregate: dict[str, Any], raw_before: Mapping[str, Any], raw_after: Mapping[str, Any],
    observation: EngineObservationV1, request: SelectionRequestV1, action: Any,
    after_observation: EngineObservationV1, table_cards: Mapping[int, Any],
) -> None:
    request_ids = _route_mentions(request, observation)
    selected_ids = _selected_route_ids(request, action, observation)
    play_ids = _play_ids(request, action, observation)
    attack_ids = _attack_ids(request, action)
    log_ids, log_names = _route_logs(after_observation)
    route_ids = request_ids | selected_ids | log_ids
    for card_id in request_ids:
        aggregate["route_effect_mentions"][card_id] += 1
    for card_id in selected_ids:
        aggregate["route_card_actions"][card_id] += 1
    for card_id in log_ids:
        aggregate["route_card_logs"][card_id] += sum(
            1 for event in after_observation.public_events if any(event.fields.get(field) == card_id for field in _EVENT_FIELDS)
        )
    delta = _public_delta(raw_before, raw_after, request.acting_player)
    if route_ids:
        for card_id in route_ids:
            aggregate["route_card_after_deltas"][card_id] += 1
            label = _ROUTE_LABELS[card_id]
            for zone_delta, value in delta["zone_deltas"].items():
                if zone_delta.endswith(f":{card_id}"):
                    aggregate["route_card_zone_deltas"][label][zone_delta] += value
    aggregate["public_log_events"] += len(after_observation.public_events)
    aggregate["transitions_with_logs"] += int(bool(after_observation.public_events))

    # Exact branch observations are assembled only from public request/action
    # semantics and the immediately following public delta/log snapshot.
    ultra = aggregate["branches"]["ultra_ball"]
    if 1121 in play_ids:
        _record_branch(ultra, action=True, after=True)
        ultra["play_actions"] += 1
        aggregate["pending_effects"][("ultra_ball", request.acting_player)] = "played"
    if request.effect_card_id == 1121:
        _record_branch(ultra, request=True)
        ultra["request_contexts"][str(request.selection_context)] += 1
        ultra["request_bounds"][f"{request.min_count}:{request.max_count}"] += 1
        pending_ultra = aggregate["pending_effects"].get(("ultra_ball", request.acting_player))
        entity_ids = _entity_card_ids(observation)
        selected_options = [request.options[index] for index in action.submitted_original_indices]
        selected_card_ids = [_option_card_id(option, entity_ids) for option in selected_options]
        if request.min_count == request.max_count == 2:
            selected = selected_options
            if len(selected) != 2 or len({option.source_entity_key for option in selected}) != 2:
                ultra["invariant_failures"]["discard_action_not_two_unique_sources"] += 1
            elif pending_ultra == "played" and all(
                entity_ids.get(option.source_entity_key) is not None
                and next(
                    (entity for entity in observation.entities if entity.entity_key == option.source_entity_key),
                    None,
                ).zone == AREA["HAND"]
                for option in selected
            ) and delta["scalar_deltas"]["hand_count"] == -2 and delta["scalar_deltas"]["discard_count"] == 2:
                ultra["causal_proofs"]["play_discard_two_from_hand"] += 1
                aggregate["pending_effects"][("ultra_ball", request.acting_player)] = "discarded"
        elif request.min_count == 0 and request.max_count == 1:
            if any(card_id not in table_cards or table_cards[card_id].card_type != 0 for card_id in selected_card_ids if card_id is not None):
                ultra["invariant_failures"]["search_action_selected_nonpokemon"] += 1
            if pending_ultra == "discarded" and len(selected_options) == 1:
                selected = selected_options[0]
                source = next((entity for entity in observation.entities if entity.entity_key == selected.source_entity_key), None)
                card_id = selected_card_ids[0]
                if (
                    source is not None and source.zone == AREA["DECK"]
                    and card_id in table_cards and table_cards[card_id].card_type == 0
                    and delta["scalar_deltas"]["deck_count"] == -1
                    and delta["scalar_deltas"]["hand_count"] == 1
                    and _zone_delta(delta, "HAND", card_id) == 1
                    and _zone_delta(delta, "DISCARD", 1121) == 1
                ):
                    ultra["causal_proofs"]["search_pokemon_to_hand"] += 1
                    aggregate["pending_effects"].pop(("ultra_ball", request.acting_player), None)
        for card_id in selected_ids:
            ultra["selected_card_ids"][card_id] += 1
    ultra["public_log_events"] += sum(
        1 for event in after_observation.public_events if any(event.fields.get(field) == 1121 for field in _EVENT_FIELDS)
    )

    trolley = aggregate["branches"]["precious_trolley"]
    trolley_request = request.effect_card_id == 1126
    if 1126 in play_ids:
        _record_branch(trolley, action=True, after=True)
        trolley["play_actions"] += 1
        aggregate["pending_effects"][("precious_trolley", request.acting_player)] = "played"
    if trolley_request:
        _record_branch(trolley, request=True)
        trolley["request_contexts"][str(request.selection_context)] += 1
        trolley["request_bounds"][f"{request.min_count}:{request.max_count}"] += 1
        if request.acting_player in (0, 1):
            entity_ids = _entity_card_ids(observation)
            selected_cards = [
                _option_card_id(request.options[index], entity_ids) for index in action.submitted_original_indices
            ]
            trolley["selected_card_ids"].update(card_id for card_id in selected_cards if card_id is not None)
            trolley["request_bounds"][
                "bench_delta:%s:before:%s:after:%s:capacity:%s" % (
                    delta["scalar_deltas"]["bench_count"],
                    delta["before"]["bench_count"],
                    delta["after"]["bench_count"],
                    delta["after"]["bench_max"],
                )
            ] += 1
            if any(card_id not in table_cards or not table_cards[card_id].basic for card_id in selected_cards if card_id is not None):
                trolley["invariant_failures"]["bench_action_selected_nonbasic"] += 1
            if delta["after"]["bench_count"] > delta["before"]["bench_max"]:
                trolley["invariant_failures"]["bench_capacity_exceeded"] += 1
            pending_trolley = aggregate["pending_effects"].get(("precious_trolley", request.acting_player))
            sources = [
                next((entity for entity in observation.entities if entity.entity_key == request.options[index].source_entity_key), None)
                for index in action.submitted_original_indices
            ]
            if (
                pending_trolley == "played" and selected_cards and all(
                    card_id in table_cards and table_cards[card_id].basic
                    and source is not None and source.zone == AREA["DECK"]
                    for card_id, source in zip(selected_cards, sources)
                )
                and delta["scalar_deltas"]["bench_count"] == len(selected_cards)
                and delta["scalar_deltas"]["deck_count"] == -len(selected_cards)
                and _movement_event_count(after_observation, AREA["DECK"], AREA["BENCH"]) == len(selected_cards)
            ):
                trolley["causal_proofs"]["search_basic_pokemon_to_bench"] += 1
                aggregate["pending_effects"].pop(("precious_trolley", request.acting_player), None)

    carmine = aggregate["branches"]["carmine"]
    if 1192 in play_ids:
        _record_branch(carmine, action=True, after=True)
        carmine["play_actions"] += 1
        carmine["request_contexts"][str(delta["before"]["prize_count"])] += 1
        carmine["request_bounds"][f"hand:{delta['scalar_deltas']['hand_count']}:discard:{delta['scalar_deltas']['discard_count']}:draw:{_event_count(after_observation, 'DRAW')}"] += 1
        if (
            _event_count_for_player(after_observation, "PLAY", request.acting_player, 1192) == 1
            and _event_count_for_player(after_observation, "DRAW", request.acting_player) == 5
            and delta["after"]["hand_count"] == 5
            and delta["scalar_deltas"]["discard_count"] == delta["before"]["hand_count"]
            and _zone_delta(delta, "DISCARD", 1192) == 1
        ):
            carmine["causal_proofs"]["discard_hand_draw_five"] += 1
    carmine["public_log_events"] += sum(
        1 for event in after_observation.public_events if any(event.fields.get(field) == 1192 for field in _EVENT_FIELDS)
    )

    lillie = aggregate["branches"]["lillie_determination"]
    if 1227 in play_ids:
        _record_branch(lillie, action=True, after=True)
        lillie["play_actions"] += 1
        prize = str(delta["before"]["prize_count"])
        lillie["request_contexts"][prize] += 1
        lillie["request_bounds"][f"hand:{delta['scalar_deltas']['hand_count']}:draw:{_event_count(after_observation, 'DRAW')}"] += 1
        expected_draw = 8 if delta["before"]["prize_count"] == 6 else 6
        if (
            _event_count_for_player(after_observation, "PLAY", request.acting_player, 1227) == 1
            and _event_count_for_player(after_observation, "SHUFFLE", request.acting_player) == 1
            and _event_count_for_player(after_observation, "DRAW", request.acting_player) == expected_draw
            and delta["after"]["hand_count"] == expected_draw
            and _zone_delta(delta, "DISCARD", 1227) == 1
        ):
            lillie["causal_proofs"][f"shuffle_hand_draw_{expected_draw}"] += 1
    lillie["public_log_events"] += sum(
        1 for event in after_observation.public_events if any(event.fields.get(field) == 1227 for field in _EVENT_FIELDS)
    )

    beach = aggregate["branches"]["surfing_beach"]
    beach_request = request.effect_card_id == 1262 or request.context_card_id == 1262
    skill_action = any(request.options[index].choice_role == "SKILL" for index in action.submitted_original_indices)
    if 1262 in play_ids:
        _record_branch(beach, action=True, after=True)
        beach["play_actions"] += 1
        aggregate["pending_effects"][("surfing_beach", request.acting_player)] = "played"
    if beach_request:
        _record_branch(beach, request=True)
        beach["request_contexts"][str(request.selection_context)] += 1
        beach["request_bounds"][f"{request.min_count}:{request.max_count}"] += 1
        entity_ids = _entity_card_ids(observation)
        switch_entity_ids = [
            card_id for option in request.options
            for card_id in (entity_ids.get(option.source_entity_key), entity_ids.get(option.target_entity_key))
            if card_id is not None
        ]
        if not switch_entity_ids:
            beach["invariant_failures"]["unresolved_switch_target"] += 1
        water_ids = {card_id for card_id, card in table_cards.items() if card.energy_type == 3}
        if switch_entity_ids and any(card_id not in water_ids for card_id in switch_entity_ids):
            beach["invariant_failures"]["non_water_switch_target"] += 1
    if skill_action:
        beach["skill_actions"] += 1
        beach["selected_card_ids"]["SKILL"] += 1
        skill_turn = (request.acting_player, delta["before"]["turn"])
        if skill_turn in aggregate["beach_skill_turns"]:
            beach["invariant_failures"]["surfing_beach_reused_same_turn"] += 1
        aggregate["beach_skill_turns"].add(skill_turn)
    if skill_action:
        beach["selected_card_ids"]["SWITCH"] += _event_count(after_observation, "SWITCH")
    beach["public_log_events"] += _event_count(after_observation, "SWITCH")
    if beach_request and skill_action and aggregate["pending_effects"].get(("surfing_beach", request.acting_player)) == "played":
        switch_events = [
            event for event in after_observation.public_events
            if event.event_name == "SWITCH" and event.fields.get("playerIndex") == request.acting_player
        ]
        water_ids = {card_id for card_id, card in table_cards.items() if card.energy_type == 3}
        if switch_events and all(
            event.fields.get("cardIdActive") in water_ids and event.fields.get("cardIdBench") in water_ids
            for event in switch_events
        ):
            beach["causal_proofs"]["stadium_skill_water_switch"] += 1
            aggregate["pending_effects"].pop(("surfing_beach", request.acting_player), None)

    for attack_id, branch_name in (
        (1042, "kyogre_riptide"), (1043, "kyogre_swirling_waves"),
        (1046, "mega_abomasnow_hammer_lanche"), (1047, "mega_abomasnow_frost_barrier"),
    ):
        branch = aggregate["branches"][branch_name]
        chosen = attack_id in attack_ids
        request_has = any(option.attack_id == attack_id for option in request.options)
        if chosen:
            _record_branch(branch, action=True, after=True)
            branch["play_actions"] += 1
            branch["selected_card_ids"][attack_id] += 1
        if request_has:
            _record_branch(branch, request=True)
            branch["request_contexts"][str(request.selection_context)] += 1
            branch["request_bounds"][f"{request.min_count}:{request.max_count}"] += 1
        if chosen:
            branch["request_bounds"][f"deck_delta:{delta['scalar_deltas']['deck_count']}"] += 1
            branch["request_contexts"][f"damage_events:{_event_count(after_observation, 'HP_CHANGE')}"] += 1
        branch["public_log_events"] += sum(event.fields.get("attackId") == attack_id for event in after_observation.public_events)
        if chosen and attack_id == 1042:
            recycle_events = _movement_event_count_for_player(
                after_observation, AREA["DISCARD"], AREA["DECK"], request.acting_player, 3,
            )
            branch["request_contexts"][f"energy_recycle_events:{recycle_events}"] += 1
            if recycle_events and _event_count_for_player(after_observation, "HP_CHANGE", request.acting_player):
                branch["causal_proofs"]["recycle_basic_water_and_damage"] += 1
        if chosen and attack_id == 1043:
            discarded = _movement_event_count_for_player(
                after_observation, AREA["ENERGY"], AREA["DISCARD"], request.acting_player, 3,
            )
            branch["request_contexts"][f"energy_discard_events:{discarded}"] += 1
            if discarded == 2 and _event_count_for_player(after_observation, "HP_CHANGE", request.acting_player):
                branch["causal_proofs"]["discard_two_energy_and_damage"] += 1
        if chosen and attack_id == 1046:
            top_six = delta["scalar_deltas"]["deck_count"] == -6
            branch["request_contexts"][f"top_six_deck_delta:{int(top_six)}"] += 1
            damage_values = sorted(
                event.fields["value"] for event in after_observation.public_events
                if event.event_name == "HP_CHANGE" and isinstance(event.fields.get("value"), int)
            )
            branch["request_contexts"][f"hammer_damage_values:{','.join(str(value) for value in damage_values)}"] += 1
            branch["request_contexts"][
                f"energy_discard_events:{_movement_event_count(after_observation, AREA['DECK'], AREA['DISCARD'], 3)}"
            ] += 1
            if not top_six:
                branch["invariant_failures"]["hammer_lanche_deck_delta_not_minus_six"] += 1
            if (
                top_six
                and _movement_event_count_for_player(
                    after_observation, AREA["DECK"], AREA["DISCARD"], request.acting_player,
                ) == 6
                and _event_count_for_player(after_observation, "HP_CHANGE", request.acting_player)
            ):
                branch["causal_proofs"]["discard_top_six_and_damage"] += 1
        if chosen and attack_id == 1047:
            aggregate["barrier_pending"][request.acting_player] = {
                "turn": delta["after"]["turn"], "transition": aggregate["transition_count"],
            }

    snover = aggregate["branches"]["snover_evolution"]
    entity_ids = _entity_card_ids(observation)
    evolution = [
        request.options[index] for index in action.submitted_original_indices
        if request.options[index].choice_role == "EVOLVE"
    ]
    if any(_option_card_id(option, entity_ids) == 723 and entity_ids.get(option.target_entity_key) == 722 for option in evolution):
        _record_branch(snover, action=True, after=True)
        snover["play_actions"] += 1
        snover["selected_card_ids"]["723->722"] += 1
        if (
            _event_count_for_player(after_observation, "EVOLVE", request.acting_player, 723) == 1
            and any(
                event.event_name == "EVOLVE"
                and event.fields.get("playerIndex") == request.acting_player
                and event.fields.get("cardId") == 723
                and event.fields.get("cardIdTarget") == 722
                for event in after_observation.public_events
            )
            and _zone_delta(delta, "PRE_EVOLUTION", 722) == 1
            and (_zone_delta(delta, "ACTIVE", 723) == 1 or _zone_delta(delta, "BENCH", 723) == 1)
            and _zone_delta(delta, "HAND", 723) == -1
        ):
            snover["causal_proofs"]["evolve_snover_to_mega_abomasnow"] += 1
    if any(option.choice_role == "EVOLVE" for option in request.options):
        _record_branch(snover, request=True)
    if evolution:
        snover["request_contexts"][f"evolve_logs:{_event_count(after_observation, 'EVOLVE')}"] += 1
    snover["public_log_events"] += _event_count(after_observation, "EVOLVE")

    # Frost Barrier's next-turn damage modifier is intentionally not inferred
    # from one trajectory.  We retain only a count of public follow-up events.
    for player, pending in list(aggregate["barrier_pending"].items()):
        if player == request.acting_player or delta["after"]["turn"] <= pending["turn"]:
            continue
        frost = aggregate["branches"]["mega_abomasnow_frost_barrier"]
        follow_up = _event_count(after_observation, "HP_CHANGE")
        frost["request_contexts"][f"post_barrier_hp_events:{follow_up}"] += 1
        if follow_up:
            frost["observations"] += follow_up
        del aggregate["barrier_pending"][player]

    # Branch counters remain mutable during the game matrix.  They are
    # converted to sanitized JSON objects only in _finalize_aggregate().


def _finish_branch_status(branch: Mapping[str, Any], name: str) -> str:
    if not branch["play_actions"] and not branch["semantic_requests"] and not branch["selected_actions"]:
        return "INCONCLUSIVE"
    if branch["invariant_failures"]:
        return "PARTIAL"
    if name == "mega_abomasnow_frost_barrier":
        return "PARTIAL"
    if name == "ultra_ball":
        required = {"2:2", "0:1"}
        proofs = branch.get("causal_proofs", {})
        return "PASS" if required.issubset(branch["request_bounds"]) and proofs.get("search_pokemon_to_hand", 0) else "PARTIAL"
    if name == "precious_trolley":
        return "PASS" if branch.get("causal_proofs", {}).get("search_basic_pokemon_to_bench", 0) else "PARTIAL"
    if name in {"carmine", "lillie_determination"}:
        proofs = branch.get("causal_proofs", {})
        if name == "carmine":
            return "PASS" if proofs.get("discard_hand_draw_five", 0) else "PARTIAL"
        return "PASS" if any(
            key.startswith("shuffle_hand_draw_") and proofs.get(key, 0) for key in proofs
        ) else "PARTIAL"
    if name == "surfing_beach":
        return "PASS" if branch.get("causal_proofs", {}).get("stadium_skill_water_switch", 0) else "PARTIAL"
    if name == "kyogre_riptide":
        return "PASS" if branch.get("causal_proofs", {}).get("recycle_basic_water_and_damage", 0) else "PARTIAL"
    if name == "kyogre_swirling_waves":
        return "PASS" if branch.get("causal_proofs", {}).get("discard_two_energy_and_damage", 0) else "PARTIAL"
    if name == "mega_abomasnow_hammer_lanche":
        return "PASS" if branch.get("causal_proofs", {}).get("discard_top_six_and_damage", 0) else "PARTIAL"
    if name == "snover_evolution":
        return "PASS" if branch.get("causal_proofs", {}).get("evolve_snover_to_mega_abomasnow", 0) else "PARTIAL"
    return "PASS" if branch["public_after_deltas"] else "PARTIAL"


def _finalize_aggregate(aggregate: dict[str, Any], config: Mapping[str, Any], table_cards: Mapping[int, Any]) -> dict[str, Any]:
    branches = {}
    for name, branch in aggregate["branches"].items():
        clean = dict(branch)
        clean["status"] = _finish_branch_status(branch, name)
        for key in ("request_contexts", "request_bounds", "selected_card_ids", "causal_proofs", "log_event_types", "invariant_failures"):
            clean[key] = _plain_counter(branch[key]) if isinstance(branch[key], Counter) else dict(branch[key])
        branches[name] = clean
    return {
        "request_count": aggregate["request_count"],
        "option_count_total": aggregate["option_count_total"],
        "max_option_count": aggregate["max_option_count"],
        "selection_type_counts": _plain_counter(aggregate["selection_type_counts"]),
        "optional_requests": aggregate["optional_requests"],
        "multiselect_requests": aggregate["multiselect_requests"],
        "ordered_requests": aggregate["ordered_requests"],
        "stop_actions": aggregate["stop_actions"],
        "public_log_events": aggregate["public_log_events"],
        "transitions_with_logs": aggregate["transitions_with_logs"],
        "transition_count": aggregate["transition_count"],
        "transition_digest": aggregate["transition_digest"],
        "transition_shape_counts": _plain_counter(aggregate["transition_shape_counts"]),
        "route_card_observations": {
            "semantic_request_mentions": {str(key): value for key, value in sorted(aggregate["route_effect_mentions"].items())},
            "selected_action_mentions": {str(key): value for key, value in sorted(aggregate["route_card_actions"].items())},
            "public_log_mentions": {str(key): value for key, value in sorted(aggregate["route_card_logs"].items())},
            "public_after_delta_mentions": {str(key): value for key, value in sorted(aggregate["route_card_after_deltas"].items())},
            "zone_deltas": {label: _plain_counter(values) for label, values in sorted(aggregate["route_card_zone_deltas"].items())},
        },
        "branches": branches,
        "matrix": aggregate["matrix"],
    }


def _transition_digest(
    aggregate: dict[str, Any], raw_before: Mapping[str, Any], raw_after: Mapping[str, Any],
    observation: EngineObservationV1, request: SelectionRequestV1, action: Any,
    after_observation: EngineObservationV1, after_request: SelectionRequestV1 | None,
) -> None:
    before_payload = _public_snapshot(raw_before, observation, request)
    after_payload = _public_snapshot(raw_after, after_observation, after_request)
    action_payload = _selected_payload(request, action, observation)
    delta = _public_delta(raw_before, raw_after, request.acting_player)
    record = {
        "before": before_payload,
        "request": _request_payload(request, observation),
        "action": action_payload,
        "after": after_payload,
        "delta": delta,
    }
    digest = _canonical_hash(record)
    aggregate["transition_digest"] = _canonical_hash({"prior": aggregate["transition_digest"], "record": digest})
    aggregate["transition_count"] += 1
    aggregate["transition_shape_counts"][
        f"logs:{len(after_observation.public_events)}:moves:{len(delta['moves'])}:zone_deltas:{len(delta['zone_deltas'])}"
    ] += 1


def _card_ids_from_raw(raw: Mapping[str, Any]) -> list[int]:
    current = raw.get("current")
    if not isinstance(current, Mapping):
        return []
    found: list[int] = []

    def add(card: Any) -> None:
        if not isinstance(card, Mapping):
            return
        card_id = card.get("id")
        if isinstance(card_id, int):
            found.append(card_id)
        for field in ("energyCards", "tools", "preEvolution"):
            for child in card.get(field) or []:
                add(child)

    for player in current.get("players") or []:
        if not isinstance(player, Mapping):
            continue
        for field in ("active", "bench", "hand", "discard", "prize"):
            for card in player.get(field) or []:
                add(card)
    for field in ("stadium", "looking"):
        for card in current.get(field) or []:
            add(card)
    select = raw.get("select")
    if isinstance(select, Mapping):
        for card in select.get("deck") or []:
            add(card)
        for field in ("contextCard", "effect"):
            add(select.get(field))
    return found


def _verify_request(raw: Mapping[str, Any], observation: EngineObservationV1, request: SelectionRequestV1, known_card_ids: set[int]) -> None:
    select = raw.get("select")
    if not isinstance(select, Mapping) or not isinstance(select.get("option"), list):
        raise _V2ContractViolation("ongoing state lacks a native option list", "semantic_contract_failures")
    if len(select["option"]) != len(request.options):
        raise _V2ContractViolation("semantic/native option counts differ", "option_count_mismatches")
    if request.min_count > request.max_count or request.max_count > len(request.options):
        raise _V2ContractViolation("semantic selection bounds are impossible", "option_bounds_failures")
    if {option.original_index for option in request.options} != set(range(len(select["option"]))):
        raise _V2ContractViolation("semantic options do not cover the complete native list", "option_count_mismatches")
    if any(card_id not in known_card_ids for card_id in _card_ids_from_raw(raw)):
        raise _V2ContractViolation("unknown public card ID", "unknown_observed_card_ids")
    for entity in observation.entities:
        if entity.card_id is not None and entity.card_id not in known_card_ids:
            raise _V2ContractViolation("unknown public card ID", "unknown_observed_card_ids")
    if any(card_id is not None and card_id not in known_card_ids for card_id in (request.context_card_id, request.effect_card_id)):
        raise _V2ContractViolation("unknown request card ID", "unknown_observed_card_ids")
    if any(option.card_id is not None and option.card_id not in known_card_ids for option in request.options):
        raise _V2ContractViolation("unknown option card ID", "unknown_observed_card_ids")
    if observation.acting_player in (0, 1):
        opponent = observation.players[1 - observation.acting_player]
        if opponent.hand_visible:
            raise _V2ContractViolation("opponent hand became visible", "hidden_hand_leaks")


def _verify_policy(policy: NativeRulePolicy, expected_deck: str, expected_policy: str) -> None:
    if policy.deck_sha256 != expected_deck or _sha256(policy.directory / "deck.csv") != expected_deck:
        raise ContractViolation("loaded baseline deck hash differs from config")
    if _sha256(policy.directory / "main.py") != expected_policy:
        raise ContractViolation("loaded baseline policy hash differs from config")


def _run_one_game(
    config: Mapping[str, Any], hashes: Mapping[str, Any], game_index: int, opponent_baseline: str,
    seat_index: int, aggregate: dict[str, Any], table_cards: Mapping[int, Any],
) -> dict[str, Any]:
    candidate = config["candidate_baseline"]
    candidate_first = seat_index % 2 == 0
    left_name, right_name = (candidate, opponent_baseline) if candidate_first else (opponent_baseline, candidate)
    assets = config["assets"]["baselines"]
    game: dict[str, Any] = {
        "game_index": game_index, "opponent_baseline": opponent_baseline,
        "candidate_player": 0 if candidate_first else 1, "terminal_result": None,
        "requests": 0, "elapsed_seconds": 0.0, "status": "FAIL", "counters": _counter(),
    }
    engine: NativeCABTTransport | None = None
    started = time.monotonic()
    raw: Mapping[str, Any] | None = None
    transition_id = 0
    try:
        # Import the official wrapper before loading native baseline modules;
        # their competition-only imports resolve through this engine root.
        engine = NativeCABTTransport(_repo_path(config["assets"]["engine_root"]))
        left_policy = NativeRulePolicy(_repo_path(assets[left_name]["policy"]["path"]).parent)
        right_policy = NativeRulePolicy(_repo_path(assets[right_name]["policy"]["path"]).parent)
        _verify_policy(left_policy, hashes["baselines"][left_name]["deck"], hashes["baselines"][left_name]["policy"])
        _verify_policy(right_policy, hashes["baselines"][right_name]["deck"], hashes["baselines"][right_name]["policy"])
        left_policy.reset(f"phase-a-v2-{game_index}", 0, "start")
        right_policy.reset(f"phase-a-v2-{game_index}", 1, "start")
        raw = engine.start(left_policy.deck, right_policy.deck)
        while transition_id < config["limits"]["request_cap_per_game"]:
            if time.monotonic() - started > config["limits"]["wall_seconds"]:
                raise _V2ContractViolation("game exceeded wall limit", "timeouts")
            observation, request = semantic_snapshot(
                raw, f"phase-a-v2-{game_index}", transition_id, CARD_DATA_SHA256,
            )
            if observation.terminal_result is not None:
                aggregate["terminal_first_checks"] += 1
                if raw.get("select") is not None:
                    aggregate["stale_terminal_selections"] += 1
                game["terminal_result"] = observation.terminal_result
                aggregate["terminal_results"].append(observation.terminal_result)
                game["status"] = "PASS"
                break
            if request is None:
                raise _V2ContractViolation("ongoing observation has no semantic request", "semantic_contract_failures")
            _verify_request(raw, observation, request, set(table_cards))
            aggregate["request_count"] += 1
            aggregate["option_count_total"] += len(request.options)
            aggregate["max_option_count"] = max(aggregate["max_option_count"], len(request.options))
            aggregate["selection_type_counts"][str(request.selection_type)] += 1
            aggregate["optional_requests"] += int(request.min_count == 0)
            aggregate["multiselect_requests"] += int(request.max_count > 1)
            aggregate["ordered_requests"] += int(request.ordering == "ORDERED")
            aggregate["public_log_events"] += len(observation.public_events)
            aggregate["transitions_with_logs"] += int(bool(observation.public_events))
            aggregate["face_down_slots"] += sum(entity.card_id is None for entity in observation.entities)
            aggregate["public_reveal_entities"] += sum(entity.card_id is not None and entity.visible for entity in observation.entities)
            policy = left_policy if request.acting_player == 0 else right_policy
            action = policy.choose_native(raw, observation, request)
            validate_compound_action(request, action)
            aggregate["stop_actions"] += int(action.stopped_early)
            raw_after = engine.select(action.submitted_original_indices)
            after_observation, after_request = semantic_snapshot(
                raw_after, f"phase-a-v2-{game_index}", transition_id + 1, CARD_DATA_SHA256,
            )
            _transition_digest(aggregate, raw, raw_after, observation, request, action, after_observation, after_request)
            _observe_route_transition(aggregate, raw, raw_after, observation, request, action, after_observation, table_cards)
            raw = raw_after
            transition_id += 1
            game["requests"] = transition_id
            if after_observation.terminal_result is not None:
                aggregate["terminal_first_checks"] += 1
                if raw_after.get("select") is not None:
                    aggregate["stale_terminal_selections"] += 1
                game["terminal_result"] = after_observation.terminal_result
                aggregate["terminal_results"].append(after_observation.terminal_result)
                game["status"] = "PASS"
                break
        else:
            raise _V2ContractViolation("request cap exceeded", "request_cap_failures")
    except _V2ContractViolation as error:
        game["counters"][error.counter_name] += 1
        aggregate["counters"][error.counter_name] += 1
    except ContractViolation:
        game["counters"]["invalid_actions"] += 1
        aggregate["counters"]["invalid_actions"] += 1
    except TimeoutError:
        game["counters"]["timeouts"] += 1
        aggregate["counters"]["timeouts"] += 1
    except Exception:
        game["counters"]["native_failures"] += 1
        aggregate["counters"]["native_failures"] += 1
    finally:
        try:
            if engine is not None:
                engine.finish()
        except Exception:
            game["counters"]["native_failures"] += 1
            aggregate["counters"]["native_failures"] += 1
        game["elapsed_seconds"] = round(time.monotonic() - started, 6)
        aggregate["matrix"][opponent_baseline]["completed"] += int(game["terminal_result"] is not None)
    return game


def run_experiment(config: Mapping[str, Any], config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    hashes = _asset_hashes(config)
    static = run_static_checks(config, hashes)
    table = CardTableV1.from_mapping(json.loads(_repo_path(config["assets"]["card_table"]["path"]).read_text(encoding="utf-8")))
    table_cards = {card.card_id: card for card in table.cards}
    aggregate = _new_aggregate(config)
    games: list[dict[str, Any]] = []
    started = time.monotonic()
    game_index = 0
    for row in config["matrix"]:
        for seat_index in range(row["games"]):
            if time.monotonic() - started > config["limits"]["wall_seconds"]:
                aggregate["counters"]["timeouts"] += 1
                break
            games.append(_run_one_game(config, hashes, game_index, row["opponent_baseline"], seat_index, aggregate, table_cards))
            game_index += 1
    completed = sum(game["terminal_result"] is not None for game in games)
    technical = completed >= config["coverage"]["minimum_completed_games"] and all(value == 0 for value in aggregate["counters"].values())
    route = _finalize_aggregate(aggregate, config, table_cards)
    return {
        "schema_version": 2,
        "record_id": config["record_id"],
        "phase": "A",
        "status": "SUCCEEDED" if technical else "FAILED",
        "decision": "PASS_WITH_ROUTE_STATUS_MATRIX" if technical else "FAIL_CLOSED",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "provenance": {
            "config_path": config_path.relative_to(ROOT).as_posix(),
            "config_sha256": _sha256(config_path),
            "runner_path": Path(__file__).resolve().relative_to(ROOT).as_posix(),
            "runner_sha256": _sha256(Path(__file__).resolve()),
            "card_data_sha256": hashes["card_data_sha256"],
            "card_table_file_sha256": _sha256(_repo_path(config["assets"]["card_table"]["path"])),
            "card_table_semantic_sha256": config["assets"]["card_table"]["semantic_sha256"],
            "engine_library_sha256": hashes["engine_library_sha256"],
            "wrapper_sha256": hashes["wrapper_sha256"],
            "api_sha256": hashes["api_sha256"],
            "baseline_hashes": hashes["baselines"],
            "native_randomness": "engine-controlled; no manual coin/random outcome",
        },
        "scope": {
            "candidate_baseline": config["candidate_baseline"],
            "matrix": config["matrix"],
            "games_requested": sum(row["games"] for row in config["matrix"]),
            "games_completed": completed,
            "wall_seconds_cap": config["limits"]["wall_seconds"],
            "request_cap_per_game": config["limits"]["request_cap_per_game"],
            "policy_strength_claimed": False,
            "deck_frozen": False,
        },
        "static_checks": static,
        "live": {
            "games": games,
            "terminal_results": aggregate["terminal_results"],
            "fail_closed_counters": aggregate["counters"],
            "terminal_first": {
                "checks": aggregate["terminal_first_checks"],
                "stale_terminal_selections_observed": aggregate["stale_terminal_selections"],
                "status": "PASS" if aggregate["terminal_first_checks"] >= completed and completed else "INCONCLUSIVE",
            },
            "complete_legal_options": {
                "status": "PASS" if technical and aggregate["request_count"] else "INCONCLUSIVE",
                "native_option_lists_not_truncated": True,
            },
            "public_before_request_action_after": {
                "status": "PASS" if technical and route["transition_count"] else "INCONCLUSIVE",
                "transition_count": route["transition_count"],
                "transition_digest": route["transition_digest"],
                "transition_shape_counts": route["transition_shape_counts"],
                "note": "Digest covers complete sanitized public projections and exact semantic request/action/after deltas; raw snapshots are not retained.",
            },
            "face_down_and_public_reveal": {
                "face_down_slots": aggregate["face_down_slots"],
                "public_reveal_entities": aggregate["public_reveal_entities"],
                "status": "PASS" if aggregate["face_down_slots"] and aggregate["public_reveal_entities"] else "INCONCLUSIVE",
            },
            "semantic_requests_and_logs": {
                "request_count": route["request_count"],
                "public_log_events": route["public_log_events"],
                "status": "PASS" if route["request_count"] and route["public_log_events"] else "INCONCLUSIVE",
            },
            "route_card_observations": route["route_card_observations"],
            "route_branches": route["branches"],
            "matrix": route["matrix"],
        },
        "claims": {
            "native_semantic_boundary_qualified": technical,
            "route_specific_effects_qualified": False,
            "policy_strength_established": False,
            "promotion_authorized": False,
            "unobserved_effects_status": config["coverage"]["unobserved_status"],
            "observed_but_unverifiable_status": config["coverage"]["unverifiable_status"],
        },
        "knowledge_base_ids": config["knowledge_base_ids"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args(argv)
    config_path = args.config.resolve()
    output_path = args.output.resolve()
    if not config_path.is_relative_to(ROOT) or not output_path.is_relative_to(ROOT):
        raise SystemExit("config/output must remain within the repository")
    config = load_config(config_path)
    report = run_experiment(config, config_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "decision": report["decision"], "output": output_path.relative_to(ROOT).as_posix()}, sort_keys=True))
    return 0 if report["status"] == "SUCCEEDED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
