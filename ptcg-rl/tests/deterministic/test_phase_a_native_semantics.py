from __future__ import annotations

import json

import pytest

from scripts.deterministic.phase_a_native_semantics import (
    DEFAULT_CONFIG,
    DEFAULT_REPORT,
    ROOT,
    _asset_hashes,
    _coverage_status,
    _repo_path,
    load_config,
    run_static_checks,
)


def test_phase_a_config_is_strict_and_repository_scoped() -> None:
    config = load_config(DEFAULT_CONFIG)
    assert config["limits"]["games_requested"] <= config["limits"]["games_max"] <= 8
    assert config["limits"]["wall_seconds"] <= 180
    assert config["coverage"]["unobserved_status"] == "INCONCLUSIVE"
    assert _repo_path(config["assets"]["card_data"]["path"]).is_relative_to(ROOT)
    with pytest.raises(ValueError, match="escapes repository"):
        _repo_path("../outside")
    invalid_minimum = dict(config)
    invalid_minimum["coverage"] = {**config["coverage"], "minimum_completed_games": 0}
    with pytest.raises(ValueError, match="minimum_completed_games"):
        load_config_from_mapping(invalid_minimum)
    invalid_cap = dict(config)
    invalid_cap["limits"] = {**config["limits"], "request_cap_per_game": 20_001}
    with pytest.raises(ValueError, match="request cap"):
        load_config_from_mapping(invalid_cap)


def load_config_from_mapping(value: dict) -> dict:
    """Exercise strict validation without creating a second config artifact."""

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory(dir=ROOT / "data") as directory:
        path = Path(directory) / "config.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return load_config(path)


def test_static_route_metadata_is_exact_and_hash_bound() -> None:
    config = load_config(DEFAULT_CONFIG)
    hashes = _asset_hashes(config)
    result = run_static_checks(config, hashes)
    assert result["status"] == "PASS"
    assert result["route_cards_checked"] == config["coverage"]["required_static_cards"]
    assert result["route_attack_ids_checked"]
    assert result["card_data_sha256"] == config["assets"]["card_data"]["sha256"]
    assert result["card_table_semantic_sha256"] == config["assets"]["card_table"]["semantic_sha256"]


def test_unobserved_route_case_is_inconclusive_not_failure() -> None:
    assert _coverage_status({1121}, [1121, 1126])["status"] == "INCONCLUSIVE"
    assert _coverage_status({1121, 1126}, [1121, 1126])["status"] == "PASS"


def test_retained_report_is_sanitized_and_fail_closed() -> None:
    if not DEFAULT_REPORT.is_file():
        pytest.skip("live canary report has not been generated")
    report = json.loads(DEFAULT_REPORT.read_text(encoding="utf-8"))
    assert report["status"] == "SUCCEEDED"
    assert report["claims"]["policy_strength_established"] is False
    assert report["claims"]["promotion_authorized"] is False
    assert all(value == 0 for value in report["live"]["fail_closed_counters"].values())
    serialized = DEFAULT_REPORT.read_text(encoding="utf-8")
    assert str(ROOT) not in serialized
    assert "raw" not in report["live"]
    assert report["live"]["route_card_observations"]["route_effects"]["status"] == "INCONCLUSIVE"
    assert report["claims"]["route_specific_effects_qualified"] is False
