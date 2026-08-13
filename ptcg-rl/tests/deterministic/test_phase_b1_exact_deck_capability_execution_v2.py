from __future__ import annotations

import hashlib
import json

import pytest

import scripts.deterministic.phase_b1_exact_deck_capability_execution_v2 as execution


def _config() -> dict[str, object]:
    return json.loads(execution.DEFAULT_CONFIG.read_text(encoding="utf-8"))


def _with_config(monkeypatch: pytest.MonkeyPatch, value: dict[str, object]) -> None:
    monkeypatch.setattr(execution, "load_execution_config", lambda _path: value)


def test_preflight_recomputes_exact_deck_and_phase_a_target_specs() -> None:
    result = execution.preflight()
    assert result["status"] == "PREFLIGHT_PASS_LAUNCH_BLOCKED"
    assert result["candidate_deck"]["path"] == "private/baselines/mega-abomasnow-ex/deck.csv"
    assert result["candidate_deck"]["count"] == 60
    assert result["candidate_deck"]["multiset"] == {
        "3": 34,
        "721": 2,
        "722": 4,
        "723": 4,
        "1121": 4,
        "1126": 1,
        "1192": 4,
        "1227": 4,
        "1262": 3,
    }
    assert result["candidate_deck"]["deck_spec_sha256"] == "7fcc91a4f646652b20dbe9efc4de382a33218b5e7ce9442b63a509b4ced8e7a6"
    assert result["phase_a_compatibility"]["expanded_card_counts"] == {
        "candidate": 60,
        "target_721": 60,
        "target_722": 60,
        "target_723": 60,
        "target_754": 60,
    }


def test_candidate_spec_mutation_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    value = _config()
    candidate = value["candidate_deck"]
    assert isinstance(candidate, dict)
    candidate["multiset"]["3"] = 33
    _with_config(monkeypatch, value)
    with pytest.raises(execution.PreflightError, match="multiset"):
        execution.preflight()


def test_phase_a_target_mutation_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    value = _config()
    compatibility = value["phase_a_compatibility"]
    assert isinstance(compatibility, dict)
    compatibility["deck_specs"]["target_723"]["3"] = 51
    _with_config(monkeypatch, value)
    with pytest.raises(execution.PreflightError, match="deck_specs"):
        execution.preflight()


def test_caps_are_exactly_900_requests_600_seconds_and_64_mib() -> None:
    result = execution.preflight()
    assert result["limits"]["request_cap_per_game"] == 900
    assert result["limits"]["wall_seconds"] == 600
    assert result["limits"]["evidence_bytes_cap"] == 64 * 1024 * 1024


@pytest.mark.parametrize(
    ("key", "value"),
    (("request_cap_per_game", 901), ("wall_seconds", 601), ("evidence_bytes_cap", 64 * 1024 * 1024 + 1)),
)
def test_cap_mutation_is_rejected(monkeypatch: pytest.MonkeyPatch, key: str, value: int) -> None:
    config = _config()
    config["limits"][key] = value
    _with_config(monkeypatch, config)
    with pytest.raises(execution.PreflightError, match="limits"):
        execution.preflight()


def test_stop_on_any_defect_is_mandatory(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _config()
    config["stop_conditions"]["stop_on_any_reliability_counter"] = False
    _with_config(monkeypatch, config)
    with pytest.raises(execution.PreflightError, match="stop conditions"):
        execution.preflight()


def test_output_namespace_is_new_unique_and_cannot_be_v1() -> None:
    config = _config()
    output = execution._validate_output(config)
    assert len(set(output.values())) == 4
    assert set(output.values()).isdisjoint(execution.HISTORICAL_PATHS)
    assert output["report_path"] == "reports/deterministic/phase-b1-exact-deck-capability-execution-v2.json"
    assert output["raw_path"] == "reports/deterministic/phase-b1-exact-deck-capability-execution-v2.raw.json"


def test_historical_v1_output_path_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    config = _config()
    config["output"]["report_path"] = "reports/deterministic/phase-b1-exact-deck-capability-rerun-v1.json"
    _with_config(monkeypatch, config)
    with pytest.raises(execution.PreflightError, match="v2 destination"):
        execution.preflight()


def test_duplicate_report_raw_destination_is_rejected() -> None:
    config = _config()
    config["output"]["raw_path"] = config["output"]["report_path"]
    with pytest.raises(execution.PreflightError, match="v2 destination"):
        execution._validate_output(config)


def test_preflight_does_not_overwrite_historical_report() -> None:
    before = hashlib.sha256(execution.HISTORICAL_REPORT.read_bytes()).hexdigest()
    result = execution.preflight()
    after = hashlib.sha256(execution.HISTORICAL_REPORT.read_bytes()).hexdigest()
    assert result["native_games"] == 0
    assert before == after


def test_native_execution_remains_disabled_without_reviewed_receipt() -> None:
    with pytest.raises(execution.LaunchBlocked, match="reviewed launch receipt"):
        execution.execute()


def test_launch_receipt_is_separate_and_missing_by_design() -> None:
    result = execution.preflight()
    receipt = result["reviewed_launch_receipt"]
    assert receipt["available"] is False
    assert receipt["path"] not in execution.HISTORICAL_PATHS
    assert receipt["path"] not in result["output"].values()


def test_config_and_executor_receipts_are_content_bound() -> None:
    config = _config()
    executor = config["executor"]
    assert executor["path"] == "scripts/deterministic/phase_b1_exact_deck_capability_execution_v2.py"
    assert executor["sha256"] == execution.sha256_file(execution.ROOT / executor["path"])
    assert config["base_plan"]["sha256"] == execution.sha256_file(execution.HISTORICAL_CONFIG)
