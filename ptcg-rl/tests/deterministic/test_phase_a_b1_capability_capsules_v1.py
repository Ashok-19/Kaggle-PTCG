from __future__ import annotations

from pathlib import Path

import scripts.deterministic.phase_a_b1_capability_capsules_v1 as capsule


def _zero_counters() -> dict[str, int]:
    return {key: 0 for key in capsule.RELIABILITY_COUNTER_KEYS}


def _attack_game(game_index: int, seat: int, attack_id: int, formulation: str) -> dict[str, object]:
    return {
        "game_index": game_index,
        "candidate_player": seat,
        "formulation": formulation,
        "counters": _zero_counters(),
        "attacks": [{"attack_id": attack_id, "proof": True}],
        "evolutions": [],
        "kos": [],
        "evolution_option_count": 0,
        "illegal_evolution_options": 0,
    }


def _prize_game(game_index: int, seat: int, target: int, delta: int = 1) -> dict[str, object]:
    return {
        "game_index": game_index,
        "candidate_player": seat,
        "formulation": "prize_route_targets",
        "counters": _zero_counters(),
        "attacks": [],
        "evolutions": [],
        "kos": [{"target_card_id": target, "prize_delta": delta, "expected_prize_delta": capsule.EXPECTED_PRIZE_DELTAS[target], "prize_proof": True}],
        "evolution_option_count": 0,
        "illegal_evolution_options": 0,
    }


def test_config_and_exact_decks_are_bound() -> None:
    config = capsule.load_config()
    assert capsule.validate_assets(config, capsule.DEFAULT_CONFIG)["card_data_sha256"] == config["assets"]["card_data_sha256"]
    assert len(capsule.expand_deck(config["deck_specs"]["candidate"])) == 60
    assert config["deck_specs"]["candidate"]["723"] == 4
    assert config["prize_contract"]["target_card_ids"] == [721, 722, 723, 754]


def test_attack_formulations_are_separate_and_complete_in_combination() -> None:
    config = capsule.load_config()
    games = [
        _attack_game(0, 0, 1044, "snover_1044_first"),
        _attack_game(1, 1, 1044, "snover_1044_first"),
        _attack_game(2, 0, 1045, "snover_1045_first"),
        _attack_game(3, 1, 1045, "snover_1045_first"),
    ]
    first = capsule._capability_status("snover_attacks", games[:2], config, required_attack_ids=(1044,))
    second = capsule._capability_status("snover_attacks", games[2:], config, required_attack_ids=(1045,))
    combined = capsule._capability_status("snover_attacks", games, config)
    assert first["status"] == "PASS"
    assert second["status"] == "PASS"
    assert combined["status"] == "PASS"


def test_evolution_requires_native_identity_link_and_local_delta() -> None:
    config = capsule.load_config()
    base = {
        "game_index": 0,
        "candidate_player": 0,
        "formulation": "snover_to_mega_evolution",
        "counters": _zero_counters(),
        "attacks": [],
        "evolutions": [{"legal_boundary": True, "local_delta_preserved": True, "serial_replaced": True, "serial_linked_by_native_event": True, "source_serial": 10, "target_serial": 20}],
        "kos": [],
        "evolution_option_count": 1,
        "illegal_evolution_options": 0,
    }
    status = capsule._capability_status("evolution", [base, {**base, "game_index": 1, "candidate_player": 1}], config)
    assert status["status"] == "PASS"
    rejected = {**base, "evolutions": [{"legal_boundary": True, "local_delta_preserved": False}]}
    assert capsule._capability_status("evolution", [rejected], config)["status"] == "PARTIAL"


def test_prize_classes_fail_closed_unknown_when_unobserved() -> None:
    config = capsule.load_config()
    games = [_prize_game(index, index % 2, 721) for index in range(4)]
    result = capsule._capability_status("prize_units", games, config)
    assert result["status_by_target_card"]["721"] == "PASS"
    assert result["status_by_target_card"]["722"] == "UNKNOWN"
    assert result["status_by_target_card"]["723"] == "UNKNOWN"
    assert result["status_by_target_card"]["754"] == "UNKNOWN"
    assert result["observed_prize_units"]["722"] == []


def test_prize_classes_require_exact_static_delta_and_reject_duplicate_proofs() -> None:
    config = capsule.load_config()
    bad = [_prize_game(index, index % 2, 721, delta=3) for index in range(4)]
    assert capsule._capability_status("prize_units", bad, config)["status_by_target_card"]["721"] == "UNKNOWN"
    duplicate = [_prize_game(0, 0, 721), _prize_game(0, 0, 721)]
    result = capsule._capability_status("prize_units", duplicate, config)
    assert result["duplicate_proof_count"] == 1
    assert result["status"] == "PARTIAL"


def test_evolution_requires_serial_replacement_and_native_link() -> None:
    config = capsule.load_config()
    base = {
        "game_index": 0,
        "candidate_player": 0,
        "counters": _zero_counters(),
        "attacks": [],
        "evolutions": [{
            "legal_boundary": True,
            "local_delta_preserved": True,
            "serial_replaced": False,
            "serial_linked_by_native_event": True,
            "source_serial": 10,
            "target_serial": 20,
        }],
        "kos": [],
        "evolution_option_count": 1,
        "illegal_evolution_options": 0,
    }
    result = capsule._capability_status("evolution", [base, {**base, "game_index": 1, "candidate_player": 1}], config)
    assert result["status"] == "PARTIAL"


def test_raw_and_report_paths_are_repo_scoped() -> None:
    config = capsule.load_config()
    assert str(Path(config["engine_root"])).startswith("private/")
    assert "/tmp" not in capsule.DEFAULT_REPORT.as_posix()
