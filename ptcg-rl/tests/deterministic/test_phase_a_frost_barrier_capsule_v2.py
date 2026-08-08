from __future__ import annotations

import json
from pathlib import Path

from scripts.deterministic.phase_a_frost_barrier_capsule_v2 import (
    DEFAULT_CONFIG,
    _verdict,
    expand_deck,
    load_config,
)


def _game(index: int = 0) -> dict[str, object]:
    return {"game_index": index, "candidate_player": index % 2, "terminal_result": 1, "formulation": "same_game_expiry"}


def _row(*, game_index: int = 0, attack_id: int = 1089, attacker_card_id: int = 754, hp_delta: int = 10, window: bool = True, source_serial: int = 71) -> dict[str, object]:
    return {
        "game_index": game_index,
        "source_transition": 10 if window else 20,
        "resolution_transition": 11 if window else 21,
        "attacker_serial": source_serial,
        "acting_player": 1,
        "target_serial": 22,
        "protected_source_serial": 22,
        "response_source_serial": source_serial,
        "attack_id": attack_id,
        "attacker_card_id": attacker_card_id,
        "target_card_id": 723,
        "barrier_window": window,
        "hp_delta": hp_delta,
        "confounds": {
            "target_still_active": True,
            "target_serial_stable": True,
            "target_card_stable": True,
            "target_status_free": True,
            "target_not_ko": True,
            "no_interval_confounds": True,
        },
    }


def test_v2_config_preregisters_primary_and_secondary_strata() -> None:
    config = load_config(DEFAULT_CONFIG)
    assert [row["id"] for row in config["formulations"]] == [
        "same_game_expiry", "no_barrier_baseline", "same_game_expiry_1043", "no_barrier_baseline_1043"
    ]
    assert config["attack_contract"]["fixed_attack_id"] == 1089
    assert config["attack_contract"]["fixed_card_id"] == 754
    assert config["attack_contract"]["fixed_base_damage"] == 40
    assert config["attack_contract"]["secondary_attack_id"] == 1043
    assert all(len(expand_deck(spec)) == 60 for spec in config["deck_specs"].values())


def test_primary_expiry_requires_exact_attack_card_and_delta() -> None:
    state = {
        "barriers": [{"game_index": 0, "barrier_turn": 4}, {"game_index": 1, "barrier_turn": 4}],
        "responses": [_row(hp_delta=10), _row(hp_delta=40, window=False), _row(game_index=1, hp_delta=10, source_serial=72), _row(game_index=1, hp_delta=40, window=False, source_serial=72)],
        "games_requested": 2,
        "games": [_game(0), _game(1)],
        "invariant_failures": {},
    }
    assert _verdict("same_game_expiry", state)[0] == "PASS"
    assert _verdict("same_game_expiry", {**state, "responses": [_row(attack_id=1043), _row(hp_delta=40, window=False)]})[0] == "PARTIAL"
    assert _verdict("same_game_expiry", {**state, "responses": [_row(attacker_card_id=721), _row(hp_delta=40, window=False)]})[0] == "PARTIAL"
    assert _verdict("same_game_expiry", {**state, "responses": [_row(hp_delta=11), _row(hp_delta=40, window=False)]})[0] == "PARTIAL"
    assert _verdict("same_game_expiry", {**state, "responses": [_row(), _row(hp_delta=40, window=False, source_serial=72)]})[0] == "PARTIAL"


def test_primary_rejects_interval_switch_or_status_evidence() -> None:
    state = {
        "barriers": [{"game_index": 0, "barrier_turn": 4}, {"game_index": 1, "barrier_turn": 4}],
        "responses": [_row(hp_delta=10), _row(hp_delta=40, window=False), _row(game_index=1, hp_delta=10, source_serial=72), _row(game_index=1, hp_delta=40, window=False, source_serial=72)],
        "games_requested": 2,
        "games": [_game(0), _game(1)],
        "invariant_failures": {},
    }
    contaminated = dict(state["responses"][1])
    contaminated["confounds"] = dict(contaminated["confounds"], no_interval_confounds=False)
    contaminated["interval_confound_events"] = [{"event": {"event_name": "SWITCH"}}]
    assert _verdict("same_game_expiry", {**state, "responses": [state["responses"][0], contaminated, *state["responses"][2:]]})[0] == "PARTIAL"


def test_primary_requires_complete_balanced_game_coverage() -> None:
    state = {
        "barriers": [{"game_index": 0, "barrier_turn": 4}],
        "responses": [_row(), _row(hp_delta=40, window=False)],
        "games_requested": 2,
        "games": [_game(0)],
        "invariant_failures": {},
    }
    assert _verdict("same_game_expiry", state)[0] == "PARTIAL"


def test_secondary_stays_partial_when_native_barrier_sequence_is_sparse() -> None:
    state = {
        "barriers": [{"game_index": 0, "barrier_turn": 4}],
        "responses": [_row(attack_id=1043, attacker_card_id=721, hp_delta=100), _row(attack_id=1043, attacker_card_id=721, hp_delta=130, window=False)],
        "games_requested": 2,
        "games": [_game(0), _game(1)],
        "invariant_failures": {},
    }
    assert _verdict("same_game_expiry_1043", state)[0] == "PARTIAL"


def test_baseline_requires_same_attacker_and_target_serials() -> None:
    first = _row(hp_delta=40, window=False, source_serial=71)
    second = _row(hp_delta=40, window=False, source_serial=72)
    state = {
        "barriers": [],
        "responses": [first, second, _row(game_index=1, hp_delta=40, window=False, source_serial=73), _row(game_index=1, hp_delta=40, window=False, source_serial=74)],
        "games_requested": 2,
        "games": [_game(0), _game(1)],
        "invariant_failures": {},
    }
    assert _verdict("no_barrier_baseline", state)[0] == "PARTIAL"


def test_report_path_is_repository_scoped() -> None:
    config = load_config(DEFAULT_CONFIG)
    assert str(Path(config["assets"]["engine_root"])).startswith("private/")
    assert "/tmp" not in json.dumps(config)
