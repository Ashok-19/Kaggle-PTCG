from __future__ import annotations

import json
from pathlib import Path

from scripts.deterministic.phase_a_frost_barrier_capsule_v1 import (
    DEFAULT_CONFIG,
    _verdict,
    expand_deck,
    load_config,
)


def test_frost_config_predeclares_two_non_mutating_formulations() -> None:
    config = load_config(DEFAULT_CONFIG)
    assert [row["id"] for row in config["formulations"]] == ["same_game_expiry", "no_barrier_baseline"]
    assert config["attack_contract"]["fixed_base_damage"] == 40
    assert config["attack_contract"]["barrier_response_damage"] == 10
    assert all(len(expand_deck(spec)) == 60 for spec in config["deck_specs"].values())


def test_expiry_verdict_requires_both_window_measurements() -> None:
    state = {"barriers": [{"barrier_turn": 4, "game_index": 0}], "responses": [
        {"game_index": 0, "target_serial": 9, "barrier_window": True, "hp_delta": 10, "confounds": {"target_still_active": True, "target_serial_stable": True, "target_card_stable": True, "target_status_free": True, "target_not_ko": True}},
    ], "invariant_failures": {}}
    assert _verdict("same_game_expiry", state)[0] == "PARTIAL"


def test_expiry_verdict_requires_complete_balanced_game_coverage() -> None:
    state = {
        "barriers": [{"game_index": 0, "barrier_turn": 4, "attacker_serial": 9}],
        "responses": [
            {"game_index": 0, "source_transition": 1, "resolution_transition": 2, "attacker_serial": 8, "target_serial": 9, "barrier_window": True, "hp_delta": 10, "confounds": {"target_still_active": True, "target_serial_stable": True, "target_card_stable": True, "target_status_free": True, "target_not_ko": True}},
            {"game_index": 0, "source_transition": 3, "resolution_transition": 4, "attacker_serial": 8, "target_serial": 9, "barrier_window": False, "hp_delta": 40, "confounds": {"target_still_active": True, "target_serial_stable": True, "target_card_stable": True, "target_status_free": True, "target_not_ko": True}},
        ],
        "games_requested": 12,
        "games": [{"game_index": 0, "candidate_player": 0, "terminal_result": 1}],
        "invariant_failures": {},
    }
    assert _verdict("same_game_expiry", state)[0] == "PARTIAL"


def test_expiry_verdict_rejects_duplicate_transition_evidence() -> None:
    response = {"game_index": 0, "source_transition": 3, "resolution_transition": 4, "attacker_serial": 8, "target_serial": 9, "barrier_window": True, "hp_delta": 10, "confounds": {"target_still_active": True, "target_serial_stable": True, "target_card_stable": True, "target_status_free": True, "target_not_ko": True}}
    expired = {**response, "barrier_window": False, "hp_delta": 40}
    state = {
        "barriers": [{"game_index": 0, "barrier_turn": 4, "attacker_serial": 8}],
        "responses": [response, response.copy(), expired],
        "games_requested": 2,
        "games": [
            {"game_index": 0, "candidate_player": 0, "terminal_result": 1},
            {"game_index": 1, "candidate_player": 1, "terminal_result": 0},
        ],
        "invariant_failures": {},
    }
    assert _verdict("same_game_expiry", state)[0] == "PARTIAL"


def test_report_path_is_repository_scoped() -> None:
    config = load_config(DEFAULT_CONFIG)
    assert str(Path(config["assets"]["engine_root"])).startswith("private/")
    assert "/tmp" not in json.dumps(config)
