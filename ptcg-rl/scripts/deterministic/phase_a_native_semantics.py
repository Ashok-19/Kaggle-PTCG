"""Bounded Phase A native semantic canary.

This runner deliberately owns no planner logic.  It qualifies the existing
native/G1 semantic boundary and records only aggregate, hash-bound evidence.
The native engine remains the source of randomness and card interaction
semantics; this script never supplies or edits a random outcome.
"""

from __future__ import annotations

import csv
import hashlib
import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from ptcg_rl.g1.actions import validate_compound_action
from ptcg_rl.g1.models import ContractViolation
from ptcg_rl.g1.native import NativeCABTTransport, load_deck
from ptcg_rl.g1.rule_baseline import NativeRulePolicy
from ptcg_rl.g1.semantic import AREA, semantic_snapshot
from ptcg_rl.g2.card_table import CardTableV1, verify_card_table


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs/deterministic/phase_a_native_semantics_v1.json"
DEFAULT_REPORT = ROOT / "reports/deterministic/phase-a-native-semantics-v1.json"

_CONFIG_KEYS = {"schema_version", "record_id", "phase", "candidate_baseline", "opponent_baseline", "assets", "limits", "coverage"}
_ASSET_KEYS = {"card_data", "card_table", "engine_root", "engine_library_sha256", "wrapper_sha256", "api_sha256", "candidate_deck", "candidate_policy", "opponent_deck", "opponent_policy"}
_HASH_ASSET_KEYS = {"card_data", "card_table", "candidate_deck", "candidate_policy", "opponent_deck", "opponent_policy"}
_LIMIT_KEYS = {"games_requested", "games_max", "wall_seconds", "request_cap_per_game"}
_COVERAGE_KEYS = {"minimum_completed_games", "required_static_cards", "required_static_attack_cards", "route_effect_card_ids", "route_attack_card_ids", "unobserved_status"}
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
_EXPECTED_STATIC_CARD_IDS = frozenset(_ROUTE_CARD_METADATA)
_EXPECTED_STATIC_ATTACK_CARD_IDS = frozenset({721, 722, 723})
_EXPECTED_ROUTE_EFFECT_CARD_IDS = frozenset({1121, 1126, 1192, 1227, 1262})
_EXPECTED_ROUTE_ATTACK_CARD_IDS = frozenset({721, 722, 723})


class _CanaryContractViolation(ContractViolation):
    """A semantic observation failure with an auditable counter category."""

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
    if isinstance(value["schema_version"], bool) or value["schema_version"] != 1:
        raise ValueError("unsupported Phase A config schema version")
    if value["record_id"] != "phase-a-native-semantics-v1":
        raise ValueError("unsupported Phase A config identity")
    if value["phase"] != "A":
        raise ValueError("config phase must be A")
    for name in ("candidate_baseline", "opponent_baseline"):
        if not isinstance(value[name], str) or not value[name]:
            raise ValueError(f"{name} must be a nonempty string")
    if value["candidate_baseline"] == value["opponent_baseline"]:
        raise ValueError("candidate and opponent baselines must be distinct")
    assets = _mapping(value["assets"], "assets")
    _exact_keys(assets, _ASSET_KEYS, "assets")
    for baseline, deck_name, policy_name in (
        (value["candidate_baseline"], "candidate_deck", "candidate_policy"),
        (value["opponent_baseline"], "opponent_deck", "opponent_policy"),
    ):
        if Path(assets[deck_name]["path"]).parent.name != baseline:
            raise ValueError(f"{deck_name} path does not match its baseline identity")
        if Path(assets[policy_name]["path"]).parent.name != baseline:
            raise ValueError(f"{policy_name} path does not match its baseline identity")
    for name in _HASH_ASSET_KEYS:
        item = _mapping(assets[name], f"assets.{name}")
        expected = {"path", "sha256"} | ({"semantic_sha256"} if name == "card_table" else set())
        _exact_keys(item, expected, f"assets.{name}")
        if not isinstance(item["path"], str) or not isinstance(item["sha256"], str):
            raise ValueError(f"assets.{name} path/hash types are invalid")
        if len(item["sha256"]) != 64 or item["sha256"] != item["sha256"].lower():
            raise ValueError(f"assets.{name}.sha256 is not a lowercase SHA-256")
        if name == "card_table" and len(item["semantic_sha256"]) != 64:
            raise ValueError("card table semantic hash is invalid")
    for name in ("engine_root", "engine_library_sha256", "wrapper_sha256", "api_sha256", "candidate_baseline", "opponent_baseline"):
        if name in assets and not isinstance(assets[name], str):
            raise ValueError(f"assets.{name} must be a string")
    limits = _mapping(value["limits"], "limits")
    _exact_keys(limits, _LIMIT_KEYS, "limits")
    if any(not isinstance(limits[key], int) or isinstance(limits[key], bool) for key in _LIMIT_KEYS):
        raise ValueError("limits must contain integer values")
    if not 1 <= limits["games_requested"] <= limits["games_max"] <= 8:
        raise ValueError("games must remain within the Phase A eight-game ceiling")
    if limits["wall_seconds"] <= 0 or limits["wall_seconds"] > 180:
        raise ValueError("wall_seconds exceeds the Phase A cap")
    if not 1 <= limits["request_cap_per_game"] <= 20_000:
        raise ValueError("request cap must remain within the Phase A per-game ceiling")
    coverage = _mapping(value["coverage"], "coverage")
    _exact_keys(coverage, _COVERAGE_KEYS, "coverage")
    minimum = coverage["minimum_completed_games"]
    if isinstance(minimum, bool) or not isinstance(minimum, int):
        raise ValueError("coverage.minimum_completed_games must be an integer")
    if not 1 <= minimum <= limits["games_requested"]:
        raise ValueError("coverage.minimum_completed_games must be within requested games")
    for name in ("required_static_cards", "required_static_attack_cards", "route_effect_card_ids", "route_attack_card_ids"):
        if (
            not isinstance(coverage[name], list)
            or not coverage[name]
            or any(isinstance(item, bool) or not isinstance(item, int) for item in coverage[name])
            or len(set(coverage[name])) != len(coverage[name])
        ):
            raise ValueError(f"coverage.{name} must be an integer list")
    if coverage["unobserved_status"] != "INCONCLUSIVE":
        raise ValueError("unobserved routes must remain INCONCLUSIVE")
    if set(coverage["required_static_cards"]) != _EXPECTED_STATIC_CARD_IDS:
        raise ValueError("required static card coverage differs from the route contract")
    if set(coverage["required_static_attack_cards"]) != _EXPECTED_STATIC_ATTACK_CARD_IDS:
        raise ValueError("required static attack card coverage differs from the route contract")
    if set(coverage["route_effect_card_ids"]) != _EXPECTED_ROUTE_EFFECT_CARD_IDS:
        raise ValueError("route effect card coverage differs from the route contract")
    if set(coverage["route_attack_card_ids"]) != _EXPECTED_ROUTE_ATTACK_CARD_IDS:
        raise ValueError("route attack card coverage differs from the route contract")
    return dict(value)


def _repo_path(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError(f"asset path escapes repository: {relative}")
    return path


def _asset_hashes(config: Mapping[str, Any]) -> dict[str, str]:
    assets = config["assets"]
    observed: dict[str, str] = {}
    for name in _HASH_ASSET_KEYS:
        item = assets[name]
        path = _repo_path(item["path"])
        if not path.is_file():
            raise FileNotFoundError(item["path"])
        digest = _sha256(path)
        if digest != item["sha256"]:
            raise ValueError(f"asset hash mismatch: {name}")
        observed[name] = digest
    for name, relative in (
        ("engine_library", f"{assets['engine_root']}/cg/libcg.so"),
        ("wrapper", f"{assets['engine_root']}/cg/game.py"),
        ("api", f"{assets['engine_root']}/cg/api.py"),
    ):
        observed[name] = _sha256(_repo_path(relative))
        if observed[name] != assets[f"{name}_sha256"]:
            raise ValueError(f"asset hash mismatch: {name}")
    return observed


def _verify_runtime_policy_assets(
    policy: NativeRulePolicy, expected_deck_sha256: str, expected_policy_sha256: str
) -> None:
    """Ensure the policy actually loaded matches the hash-bound config assets."""

    if policy.deck_sha256 != expected_deck_sha256:
        raise ContractViolation("loaded rule deck receipt differs from configured deck hash")
    if _sha256(policy.directory / "deck.csv") != expected_deck_sha256:
        raise ContractViolation("loaded rule deck bytes differ from configured deck hash")
    if _sha256(policy.directory / "main.py") != expected_policy_sha256:
        raise ContractViolation("loaded rule module differs from configured policy hash")


def _load_card_rows(path: Path) -> dict[int, list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        if set(reader.fieldnames or ()) != _CSV_COLUMNS:
            raise ValueError("card CSV columns differ from the official schema")
        rows: dict[int, list[dict[str, str]]] = {}
        for row in reader:
            card_id = int(row["Card ID"])
            rows.setdefault(card_id, []).append({str(key): str(value).strip() for key, value in row.items()})
    return rows


def run_static_checks(config: Mapping[str, Any], hashes: Mapping[str, str]) -> dict[str, Any]:
    table_path = _repo_path(config["assets"]["card_table"]["path"])
    table = CardTableV1.from_mapping(json.loads(table_path.read_text(encoding="utf-8")))
    verification = verify_card_table(table)
    if verification["table_sha256"] != config["assets"]["card_table"]["semantic_sha256"]:
        raise ValueError("card table semantic hash differs from config")
    if table.card_data_sha256 != hashes["card_data"]:
        raise ValueError("card table card-data hash differs from config")
    if table.engine_library_sha256 != hashes["engine_library"]:
        raise ValueError("card table engine hash differs from config")
    if table.wrapper_api_sha256 != hashes["api"]:
        raise ValueError("card table API hash differs from config")
    rows = _load_card_rows(_repo_path(config["assets"]["card_data"]["path"]))
    expected_ids = tuple(config["coverage"]["required_static_cards"])
    checked: list[int] = []
    attack_ids: list[int] = []
    effect_rows: list[int] = []
    by_id = {card.card_id: card for card in table.cards}
    attacks = {attack.attack_id: attack for attack in table.attacks}
    for card_id in expected_ids:
        if card_id not in _ROUTE_CARD_METADATA or card_id not in by_id or card_id not in rows:
            raise ValueError(f"missing route-critical card metadata: {card_id}")
        expected_name, expected_stage, expected_previous = _ROUTE_CARD_METADATA[card_id]
        static_rows = rows[card_id]
        if any(
            (row["Card Name"], row["Stage (Pokémon)/Type (Energy and Trainer)"], row["Previous stage"])
            != (expected_name, expected_stage, expected_previous)
            for row in static_rows
        ):
            raise ValueError(f"route-critical CSV identity differs for card {card_id}")
        card = by_id[card_id]
        for attack_id in card.attack_ids:
            if attack_id not in attacks:
                raise ValueError(f"card {card_id} references unknown attack {attack_id}")
            attack_ids.append(attack_id)
        if any(row["Effect Explanation"] not in {"", "n/a"} for row in static_rows):
            effect_rows.append(card_id)
        checked.append(card_id)
    # Keep the separately declared attack-card coverage meaningful.  A caller
    # must not be able to replace it with an unknown/non-attacking card while
    # still receiving a static PASS.
    required_attack_cards = config["coverage"]["required_static_attack_cards"]
    if not set(required_attack_cards).issubset(set(expected_ids)):
        raise ValueError("required static attack cards must be among required static cards")
    for card_id in required_attack_cards:
        card = by_id.get(card_id)
        if card is None or not card.attack_ids:
            raise ValueError(f"missing required static attack card metadata: {card_id}")
    deck = load_deck(_repo_path(config["assets"]["candidate_deck"]["path"]))
    deck_counts = Counter(deck)
    missing_from_deck = [card_id for card_id in expected_ids if deck_counts[card_id] == 0]
    if missing_from_deck:
        raise ValueError(f"candidate deck lacks expected route card IDs: {missing_from_deck}")
    return {
        "status": "PASS",
        "card_table_schema_version": table.schema_version,
        "card_table_cards": len(table.cards),
        "card_table_attacks": len(table.attacks),
        "csv_rows": sum(len(value) for value in rows.values()),
        "route_cards_checked": checked,
        "route_attack_ids_checked": sorted(set(attack_ids)),
        "local_effect_metadata_rows_available": sorted(set(effect_rows)),
        "candidate_deck_size": len(deck),
        "candidate_deck_distinct_ids": len(deck_counts),
        "card_data_sha256": hashes["card_data"],
        "card_table_file_sha256": hashes["card_table"],
        "card_table_semantic_sha256": verification["table_sha256"],
        "note": "Static effect text is metadata only; executable effects are counted only after a live observation.",
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
    }


def _card_ids_from_raw(raw: Mapping[str, Any]) -> list[int]:
    found: list[int] = []
    current = raw.get("current") or {}
    for player in current.get("players", []):
        for zone in ("active", "bench", "hand", "discard", "prize"):
            for card in player.get(zone) or []:
                if card is not None and isinstance(card.get("id"), int):
                    found.append(card["id"])
                if isinstance(card, Mapping):
                    for nested in ("energyCards", "tools", "preEvolution"):
                        for child in card.get(nested) or []:
                            if isinstance(child, Mapping) and isinstance(child.get("id"), int):
                                found.append(child["id"])
    for card in (current.get("stadium") or [], current.get("looking") or []):
        if isinstance(card, Mapping) and isinstance(card.get("id"), int):
            found.append(card["id"])
    select = raw.get("select") or {}
    for card in (select.get("deck") or [], select.get("contextCard"), select.get("effect")):
        if isinstance(card, Mapping) and isinstance(card.get("id"), int):
            found.append(card["id"])
    return found


def _observe_request(
    raw: Mapping[str, Any],
    observation: Any,
    request: Any,
    known_card_ids: set[int],
    aggregate: dict[str, Any],
) -> None:
    select = raw.get("select")
    if not isinstance(select, Mapping) or not isinstance(select.get("option"), list):
        raise ContractViolation("ongoing state does not carry a native option list")
    raw_options = select["option"]
    if len(raw_options) != len(request.options):
        raise _CanaryContractViolation(
            "semantic option count differs from native option count", "option_count_mismatches"
        )
    if request.max_count > len(request.options) or request.min_count > request.max_count:
        raise _CanaryContractViolation(
            "semantic selection bounds are impossible", "option_bounds_failures"
        )
    if {option.original_index for option in request.options} != set(range(len(raw_options))):
        raise _CanaryContractViolation(
            "semantic original indices do not cover complete native options", "option_count_mismatches"
        )
    acting = observation.acting_player
    if acting in (0, 1):
        opponent = observation.players[1 - acting]
        if opponent.hand_visible or any(
            entity.owner == 1 - acting and entity.zone == AREA["HAND"] and entity.card_id is not None
            for entity in observation.entities
        ):
            raise _CanaryContractViolation(
                "opponent hand became visible in public semantic state", "hidden_hand_leaks"
            )
    route_effect_ids = set(aggregate["route_effect_ids"])
    for card_id in _card_ids_from_raw(raw):
        if card_id not in known_card_ids:
            raise _CanaryContractViolation(
                "native exposed a card ID absent from the verified table", "unknown_observed_card_ids"
            )
    for card_id in (request.context_card_id, request.effect_card_id):
        if card_id is not None:
            aggregate["observed_context_effect_card_ids"].add(card_id)
            if card_id in route_effect_ids:
                aggregate["observed_route_effect_card_ids"].add(card_id)
    for option in request.options:
        if option.card_id is not None:
            aggregate["observed_option_card_ids"].add(option.card_id)
        if option.attack_id is not None:
            aggregate["observed_attack_ids"].add(option.attack_id)
            for card_id, attack_ids in aggregate["route_attack_map"].items():
                if option.attack_id in attack_ids:
                    aggregate["observed_route_attack_card_ids"].add(card_id)
    aggregate["request_count"] += 1
    aggregate["option_count_total"] += len(request.options)
    aggregate["max_option_count"] = max(aggregate["max_option_count"], len(request.options))
    aggregate["selection_types"][str(request.selection_type)] += 1
    if request.min_count == 0:
        aggregate["optional_requests"] += 1
    if request.max_count > 1:
        aggregate["multiselect_requests"] += 1
    if request.ordering == "ORDERED":
        aggregate["ordered_requests"] += 1
    if request.effect_card_id is not None or request.context_card_id is not None or select.get("effect") is not None:
        aggregate["transient_effect_contexts"] += 1
    aggregate["public_log_events"] += len(observation.public_events)
    aggregate["transitions_with_logs"] += bool(observation.public_events)
    # Selection-local entities are transient even though their factual AREA
    # enum values precede the pseudo-area range (DECK=1, LOOKING=12,
    # PLAYING=13, TEMPORARY=24).  Counting only zones >= ME silently missed
    # every normal deck/search/effect transient.
    transient_zones = {AREA["DECK"], AREA["LOOKING"], AREA["PLAYING"], AREA["TEMPORARY"]}
    aggregate["transient_entity_zones"] += sum(
        entity.zone in transient_zones for entity in observation.entities
    )


def _new_live_aggregate(
    route_effect_ids: Sequence[int], route_attack_ids: Sequence[int],
    route_attack_map: Mapping[int, Sequence[int]],
) -> dict[str, Any]:
    return {
        "counters": _counter(),
        "terminal_results": [],
        "request_count": 0,
        "option_count_total": 0,
        "max_option_count": 0,
        "selection_types": Counter(),
        "optional_requests": 0,
        "multiselect_requests": 0,
        "ordered_requests": 0,
        "stop_actions": 0,
        "transient_effect_contexts": 0,
        "public_log_events": 0,
        "transitions_with_logs": 0,
        "transient_entity_zones": 0,
        "face_down_slots": 0,
        "public_reveal_entities": 0,
        "terminal_first_checks": 0,
        "stale_terminal_selections": 0,
        "observed_context_effect_card_ids": set(),
        "observed_route_effect_card_ids": set(),
        "observed_option_card_ids": set(),
        "observed_attack_ids": set(),
        "observed_route_attack_card_ids": set(),
        "route_effect_ids": tuple(route_effect_ids),
        "route_attack_ids": tuple(route_attack_ids),
        "route_attack_map": {int(card_id): tuple(attack_ids) for card_id, attack_ids in route_attack_map.items()},
    }


def _run_one_game(
    config: Mapping[str, Any], hashes: Mapping[str, str], game_index: int,
    aggregate: dict[str, Any], known_card_ids: set[int],
) -> dict[str, Any]:
    assets = config["assets"]
    candidate_first = game_index % 2 == 0
    left_name, right_name = (
        (config["candidate_baseline"], config["opponent_baseline"])
        if candidate_first else (config["opponent_baseline"], config["candidate_baseline"])
    )
    engine: NativeCABTTransport | None = None
    left_dir: Path
    right_dir: Path
    left_policy: NativeRulePolicy | None = None
    right_policy: NativeRulePolicy | None = None
    left_deck: list[int] = []
    right_deck: list[int] = []
    game = {
        "game_index": game_index,
        "candidate_player": 0 if candidate_first else 1,
        "candidate_baseline": config["candidate_baseline"],
        "opponent_baseline": config["opponent_baseline"],
        "terminal_result": None,
        "requests": 0,
        "elapsed_seconds": 0.0,
        "status": "FAIL",
        "counters": _counter(),
        "coverage": {
            "face_down_slots": 0,
            "public_reveal_entities": 0,
            "optional_requests": 0,
            "multiselect_requests": 0,
            "ordered_requests": 0,
            "stop_actions": 0,
            "transient_effect_contexts": 0,
            "public_log_events": 0,
        },
    }
    started = time.monotonic()
    raw: Mapping[str, Any] | None = None
    failure_counter: str | None = None
    try:
        left_dir = _repo_path(f"private/baselines/{left_name}")
        right_dir = _repo_path(f"private/baselines/{right_name}")
        engine = NativeCABTTransport(_repo_path(assets["engine_root"]))
        left_policy, right_policy = NativeRulePolicy(left_dir), NativeRulePolicy(right_dir)
        expected_deck_hash = {
            config["candidate_baseline"]: hashes["candidate_deck"],
            config["opponent_baseline"]: hashes["opponent_deck"],
        }
        expected_policy_hash = {
            config["candidate_baseline"]: hashes["candidate_policy"],
            config["opponent_baseline"]: hashes["opponent_policy"],
        }
        _verify_runtime_policy_assets(
            left_policy, expected_deck_hash[left_name], expected_policy_hash[left_name]
        )
        _verify_runtime_policy_assets(
            right_policy, expected_deck_hash[right_name], expected_policy_hash[right_name]
        )
        left_deck, right_deck = left_policy.deck, right_policy.deck
        left_policy.reset(f"phase-a-{game_index}", 0, "start")
        right_policy.reset(f"phase-a-{game_index}", 1, "start")
        raw = engine.start(left_deck, right_deck)
        for transition_id in range(config["limits"]["request_cap_per_game"]):
            if time.monotonic() - started > config["limits"]["wall_seconds"]:
                game["counters"]["timeouts"] += 1
                aggregate["counters"]["timeouts"] += 1
                break
            observation, request = semantic_snapshot(
                raw, f"phase-a-{game_index}", transition_id, hashes["card_data"]
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
                game["counters"]["semantic_contract_failures"] += 1
                aggregate["counters"]["semantic_contract_failures"] += 1
                break
            before_faces = sum(
                entity.card_id is None and entity.zone in {AREA["ACTIVE"], AREA["PRIZE"]}
                for entity in observation.entities
            )
            aggregate["face_down_slots"] += before_faces
            game["coverage"]["face_down_slots"] += before_faces
            revealed = sum(entity.card_id is not None and entity.visible for entity in observation.entities)
            aggregate["public_reveal_entities"] += revealed
            game["coverage"]["public_reveal_entities"] += revealed
            _observe_request(raw, observation, request, known_card_ids, aggregate)
            game["requests"] += 1
            game["coverage"]["optional_requests"] = aggregate["optional_requests"]
            game["coverage"]["multiselect_requests"] = aggregate["multiselect_requests"]
            game["coverage"]["ordered_requests"] = aggregate["ordered_requests"]
            game["coverage"]["transient_effect_contexts"] = aggregate["transient_effect_contexts"]
            game["coverage"]["public_log_events"] = aggregate["public_log_events"]
            # The native snapshot's yourIndex is the acting player.  The policy
            # map above is therefore selected by the engine's actual seat.
            policy = left_policy if request.acting_player == 0 else right_policy
            assert policy is not None
            try:
                action = policy.choose_native(raw, observation, request)
                validate_compound_action(request, action)
            except ContractViolation:
                failure_counter = "invalid_actions"
                game["counters"][failure_counter] += 1
                aggregate["counters"][failure_counter] += 1
                raise
            if action.stopped_early:
                aggregate["stop_actions"] += 1
                game["coverage"]["stop_actions"] += 1
            raw = engine.select(action.submitted_original_indices)
        else:
            game["counters"]["request_cap_failures"] += 1
            aggregate["counters"]["request_cap_failures"] += 1
    except _CanaryContractViolation as error:
        failure_counter = error.counter_name
        game["counters"][failure_counter] += 1
        aggregate["counters"][failure_counter] += 1
    except ContractViolation as error:
        if failure_counter is None:
            failure_counter = (
                "hidden_hand_leaks" if "hidden hand" in str(error).lower()
                else "semantic_contract_failures"
            )
            game["counters"][failure_counter] += 1
            aggregate["counters"][failure_counter] += 1
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
    return game


def _coverage_status(observed: set[int], required: Sequence[int]) -> dict[str, Any]:
    missing = sorted(set(required) - observed)
    return {
        "observed_ids": sorted(observed),
        "required_ids": sorted(set(required)),
        "missing_ids": missing,
        "status": "PASS" if not missing else "INCONCLUSIVE",
    }


def run_canary(config: Mapping[str, Any], config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    hashes = _asset_hashes(config)
    static = run_static_checks(config, hashes)
    table = CardTableV1.from_mapping(json.loads(_repo_path(config["assets"]["card_table"]["path"]).read_text(encoding="utf-8")))
    table_cards = {card.card_id: card for card in table.cards}
    aggregate = _new_live_aggregate(
        config["coverage"]["route_effect_card_ids"], config["coverage"]["route_attack_card_ids"],
        {card_id: table_cards[card_id].attack_ids for card_id in config["coverage"]["route_attack_card_ids"]},
    )
    games: list[dict[str, Any]] = []
    started = time.monotonic()
    for game_index in range(config["limits"]["games_requested"]):
        if time.monotonic() - started > config["limits"]["wall_seconds"]:
            aggregate["counters"]["timeouts"] += 1
            break
        games.append(_run_one_game(config, hashes, game_index, aggregate, set(table_cards)))
    completed = sum(game["terminal_result"] is not None for game in games)
    all_zero = all(value == 0 for value in aggregate["counters"].values())
    technical = completed >= config["coverage"]["minimum_completed_games"] and all_zero
    known_card_ids = set(table_cards)
    report = {
        "schema_version": 1,
        "record_id": config["record_id"],
        "phase": "A",
        "status": "SUCCEEDED" if technical else "FAILED",
        "decision": "PASS_WITH_INCONCLUSIVE_ROUTE_COVERAGE" if technical else "FAIL_CLOSED",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "provenance": {
            "config_path": config_path.relative_to(ROOT).as_posix(),
            "config_sha256": _sha256(config_path),
            "runner_path": Path(__file__).resolve().relative_to(ROOT).as_posix(),
            "runner_sha256": _sha256(Path(__file__).resolve()),
            "card_data_sha256": hashes["card_data"],
            "card_table_file_sha256": hashes["card_table"],
            "card_table_semantic_sha256": config["assets"]["card_table"]["semantic_sha256"],
            "engine_library_sha256": hashes["engine_library"],
            "wrapper_sha256": hashes["wrapper"],
            "api_sha256": hashes["api"],
            "candidate_deck_sha256": hashes["candidate_deck"],
            "candidate_policy_sha256": hashes["candidate_policy"],
            "opponent_deck_sha256": hashes["opponent_deck"],
            "opponent_policy_sha256": hashes["opponent_policy"],
            "native_randomness": "engine-controlled; no manual coin/random outcome",
        },
        "scope": {
            "candidate_baseline": config["candidate_baseline"],
            "opponent_baseline": config["opponent_baseline"],
            "games_requested": config["limits"]["games_requested"],
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
            "request_count": aggregate["request_count"],
            "option_count_total": aggregate["option_count_total"],
            "max_option_count": aggregate["max_option_count"],
            "selection_type_counts": dict(sorted(aggregate["selection_types"].items())),
            "fail_closed_counters": aggregate["counters"],
            "terminal_first": {
                "checks": aggregate["terminal_first_checks"],
                "stale_terminal_selections_observed": aggregate["stale_terminal_selections"],
                "status": "PASS" if aggregate["terminal_first_checks"] == completed and completed else "INCONCLUSIVE",
            },
            "complete_legal_options": {
                "status": "PASS" if all_zero and aggregate["request_count"] else "INCONCLUSIVE",
                "native_option_lists_not_truncated": True,
            },
            "face_down_and_public_reveal": {
                "face_down_slots": aggregate["face_down_slots"],
                "public_reveal_entities": aggregate["public_reveal_entities"],
                "status": "PASS" if aggregate["face_down_slots"] and aggregate["public_reveal_entities"] else "INCONCLUSIVE",
            },
            "transient_effect_and_logs": {
                "effect_or_context_requests": aggregate["transient_effect_contexts"],
                "public_log_events": aggregate["public_log_events"],
                "transient_entity_zone_observations": aggregate["transient_entity_zones"],
                "observed_context_effect_card_ids": sorted(aggregate["observed_context_effect_card_ids"]),
                "status": "PASS" if aggregate["transient_effect_contexts"] and aggregate["public_log_events"] else "INCONCLUSIVE",
            },
            "optional_and_multiselect": {
                "optional_requests": aggregate["optional_requests"],
                "multiselect_requests": aggregate["multiselect_requests"],
                "ordered_requests": aggregate["ordered_requests"],
                "stop_actions": aggregate["stop_actions"],
                "status": "PASS" if aggregate["optional_requests"] and aggregate["multiselect_requests"] else "INCONCLUSIVE",
            },
            "route_card_observations": {
                "known_card_vocabulary_size": len(known_card_ids),
                "observed_option_card_ids": sorted(aggregate["observed_option_card_ids"]),
                "observed_attack_ids": sorted(aggregate["observed_attack_ids"]),
                "route_effects": _coverage_status(
                    aggregate["observed_route_effect_card_ids"], config["coverage"]["route_effect_card_ids"]
                ),
                "route_attacks": _coverage_status(
                    aggregate["observed_route_attack_card_ids"], config["coverage"]["route_attack_card_ids"]
                ),
            },
        },
        "claims": {
            "native_semantic_boundary_qualified": technical,
            "route_specific_effects_qualified": False,
            "policy_strength_established": False,
            "promotion_authorized": False,
        },
        "knowledge_base_ids": ["DR-025", "DR-030", "DR-033", "AP-009", "AP-010", "AP-014", "RQ-001", "RQ-002", "RQ-007"],
    }
    return report


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
    report = run_canary(config, config_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "decision": report["decision"], "output": output_path.relative_to(ROOT).as_posix()}, sort_keys=True))
    return 0 if report["status"] == "SUCCEEDED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
