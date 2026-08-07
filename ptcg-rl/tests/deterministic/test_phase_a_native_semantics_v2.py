from __future__ import annotations

import json

import pytest

from scripts.deterministic.phase_a_native_semantics_v2 import (
    DEFAULT_CONFIG,
    DEFAULT_REPORT,
    ROOT,
    _asset_hashes,
    _finish_branch_status,
    _public_snapshot,
    _repo_path,
    load_config,
    run_static_checks,
)
from ptcg_rl.g1.models import EngineObservationV1, PlayerViewV1


def test_v2_config_is_strict_and_repository_scoped() -> None:
    config = load_config(DEFAULT_CONFIG)
    assert config["schema_version"] == 2
    assert sum(row["games"] for row in config["matrix"]) <= 8
    assert config["limits"]["wall_seconds"] <= 180
    assert config["coverage"]["unobserved_status"] == "INCONCLUSIVE"
    assert config["coverage"]["unverifiable_status"] == "PARTIAL"
    assert _repo_path(config["assets"]["card_data"]["path"]).is_relative_to(ROOT)
    with pytest.raises(ValueError, match="escapes repository"):
        _repo_path("../outside")


def test_v2_static_attack_card_coverage_is_enforced() -> None:
    config = load_config(DEFAULT_CONFIG)
    hashes = _asset_hashes(config)
    invalid = dict(config)
    invalid["coverage"] = {**config["coverage"], "required_static_attack_cards": [999]}
    with pytest.raises(ValueError, match="static attack card"):
        run_static_checks(invalid, hashes)


def test_missing_route_effects_never_become_pass() -> None:
    empty = {
        "play_actions": 0,
        "semantic_requests": 0,
        "selected_actions": 0,
        "public_after_deltas": 0,
        "skill_actions": 0,
        "invariant_failures": {},
        "request_bounds": {},
        "request_contexts": {},
    }
    assert _finish_branch_status(empty, "ultra_ball") == "INCONCLUSIVE"
    observed_without_verification = {
        **empty,
        "play_actions": 1,
        "public_after_deltas": 1,
    }
    assert _finish_branch_status(observed_without_verification, "ultra_ball") == "PARTIAL"


def test_route_status_requires_action_scoped_effect_proof() -> None:
    branch = {
        "play_actions": 1,
        "semantic_requests": 1,
        "selected_actions": 1,
        "public_after_deltas": 1,
        "request_bounds": {"2:2", "0:1"},
        "causal_proofs": {},
        "invariant_failures": {},
    }
    assert _finish_branch_status(branch, "carmine") == "PARTIAL"
    assert _finish_branch_status(branch, "precious_trolley") == "PARTIAL"
    assert _finish_branch_status(branch, "snover_evolution") == "PARTIAL"
    branch["causal_proofs"] = {
        "discard_hand_draw_five": 1,
        "search_basic_pokemon_to_bench": 1,
        "evolve_snover_to_mega_abomasnow": 1,
    }
    assert _finish_branch_status(branch, "carmine") == "PASS"
    assert _finish_branch_status(branch, "precious_trolley") == "PASS"
    assert _finish_branch_status(branch, "snover_evolution") == "PASS"


def test_public_snapshot_rejects_hidden_opponent_hand() -> None:
    observation = EngineObservationV1(
        schema_version=2,
        battle_id="fixture",
        transition_id=0,
        acting_player=0,
        terminal_result=None,
        turn=1,
        turn_action_count=0,
        first_player=0,
        supporter_played=False,
        stadium_played=False,
        energy_attached=False,
        retreated=False,
        players=(
            PlayerViewV1(0, 5, 10, 1, 6, 0, True, 0),
            PlayerViewV1(1, 5, 10, 1, 6, 0, False, 0),
        ),
        entities=(),
        public_events=(),
    )
    raw = {
        "current": {
            "yourIndex": 0,
            "players": [
                {"active": [], "bench": [], "discard": [], "prize": [], "hand": [], "handCount": 1, "deckCount": 10, "benchMax": 5},
                {"active": [], "bench": [], "discard": [], "prize": [], "hand": [{"id": 3, "serial": 1}], "handCount": 1, "deckCount": 10, "benchMax": 5},
            ],
        }
    }
    with pytest.raises(ValueError, match="opponent hand"):
        _public_snapshot(raw, observation, None)


def test_retained_v2_report_is_sanitized_when_present() -> None:
    if not DEFAULT_REPORT.is_file():
        pytest.skip("v2 experiment report has not been generated")
    report = json.loads(DEFAULT_REPORT.read_text(encoding="utf-8"))
    assert report["status"] == "SUCCEEDED"
    assert report["claims"]["policy_strength_established"] is False
    assert report["claims"]["promotion_authorized"] is False
    assert all(value == 0 for value in report["live"]["fail_closed_counters"].values())
    assert str(ROOT) not in DEFAULT_REPORT.read_text(encoding="utf-8")
    assert "raw" not in report
    assert report["claims"]["unobserved_effects_status"] == "INCONCLUSIVE"
    assert report["claims"]["observed_but_unverifiable_status"] == "PARTIAL"
