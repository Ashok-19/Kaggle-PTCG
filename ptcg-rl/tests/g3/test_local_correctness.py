from __future__ import annotations

import json
from pathlib import Path

import pytest

from ptcg_rl.g3.local_correctness import (
    LocalCorrectnessError,
    expected_local_correctness_config,
    load_local_correctness_config,
    write_local_correctness_report,
)


def test_local_correctness_config_is_exact_frozen_and_resource_safe() -> None:
    root = Path(__file__).resolve().parents[2]
    path = root / "configs/g3a_local_correctness_v1.json"
    loaded = load_local_correctness_config(path)
    assert loaded == expected_local_correctness_config()
    assert loaded["resources"] == {
        "device": "cpu",
        "maximum_cpu_threads": 2,
        "maximum_worker_processes": 0,
        "maximum_non_forced_choices_per_model": 4096,
        "maximum_wall_seconds_per_model": 300,
    }
    assert loaded["declared_seeds"] == [1197953491, 20344180, 1491619630]
    assert loaded["selected_candidate_id"] == "b-1024-lr5e3"
    from ptcg_rl.g3.local_correctness import LOCAL_CORRECTNESS_CONFIG_SHA256

    assert LOCAL_CORRECTNESS_CONFIG_SHA256 == "10874b321250cf87ff4824aafa7de35c557ad194bc76d255d2afc0d4a91471aa"
    assert loaded["authorization"] == {
        "cabt_games_allowed": False,
        "cloud_launch_allowed": False,
        "meaningful_self_play_allowed": False,
        "policy_strength_claim_allowed": False,
    }


def test_local_correctness_config_tampering_fails_closed(tmp_path: Path) -> None:
    value = expected_local_correctness_config()
    value["resources"]["maximum_cpu_threads"] = 3
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(LocalCorrectnessError, match="SHA-256 differs"):
        load_local_correctness_config(path)
    path.write_text('{"schema_version":1,"schema_version":2}', encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        load_local_correctness_config(path)


def test_local_report_writer_is_atomic_canonical_and_replaces_existing(tmp_path: Path) -> None:
    path = tmp_path / "report.json"
    write_local_correctness_report(path, {"b": 2, "a": 1})
    assert path.read_bytes() == b'{"a":1,"b":2}\n'
    assert not path.with_name(path.name + ".partial").exists()
    write_local_correctness_report(path, {"a": 3})
    assert path.read_bytes() == b'{"a":3}\n'
