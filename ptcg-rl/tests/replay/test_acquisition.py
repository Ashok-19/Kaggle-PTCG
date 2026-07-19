from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from ptcg_rl.replay.acquisition import ReplayAcquisitionError, audit_acquisition


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def make_plan(filename: str, size: int) -> dict[str, Any]:
    plan: dict[str, Any] = {
        "schema_version": 1,
        "planner_version": "fixture-v1",
        "created_at_utc": "2026-07-19T00:00:00Z",
        "source": {
            "index": {"dataset_owner": "kaggle", "dataset_slug": "index", "dataset_version": 33},
            "daily": {"dataset_owner": "kaggle", "dataset_slug": "daily", "dataset_version": 1},
            "source_date": "2026-07-18",
        },
        "selection_profile": {
            "caps": {"max_files": 1, "max_total_bytes": 100_000, "max_file_bytes": 100_000}
        },
        "summary": {"selected_files": 1, "selected_bytes": size},
        "selected_items": [{"remote_filename": filename, "declared_bytes": size}],
        "rows": [],
    }
    payload = dict(plan)
    payload.pop("created_at_utc")
    plan["plan_sha256"] = hashlib.sha256(canonical(payload)).hexdigest()
    return plan


def observation(select: dict[str, Any] | None) -> dict[str, Any]:
    return {"current": None, "logs": [], "remainingOverageTime": 0, "search_begin_input": None, "select": select}


def record(status: str, action: list[int], select: dict[str, Any] | None, reward: int = 0) -> dict[str, Any]:
    return {"action": action, "info": {}, "observation": observation(select), "reward": reward, "status": status}


def replay() -> dict[str, Any]:
    request_one = {"type": 1, "minCount": 1, "maxCount": 1, "option": [{"type": 3, "index": 9}, {"type": 3, "index": 10}]}
    request_zero = {"type": 1, "minCount": 0, "maxCount": 1, "option": [{"type": 4, "index": 2}]}
    return {
        "schema_version": 1,
        "module_version": "1.32.0",
        "id": "internal-fixture-id",
        "statuses": ["DONE", "DONE"],
        "rewards": [1, -1],
        "steps": [
            [record("ACTIVE", [], None), record("ACTIVE", [], None)],
            [record("ACTIVE", list(range(60)), request_one), record("INACTIVE", list(range(60)), None)],
            [record("INACTIVE", [0], request_one), record("ACTIVE", [], request_zero)],
            [record("DONE", [], request_one, 1), record("DONE", [], request_zero, -1)],
        ],
    }


def write_fixture(tmp_path: Path, value: dict[str, Any] | None = None) -> tuple[dict[str, Any], Path]:
    episodes = tmp_path / "episodes"
    episodes.mkdir()
    path = episodes / "90000001.json"
    path.write_text(json.dumps(value or replay()), encoding="utf-8")
    return make_plan(path.name, path.stat().st_size), episodes


def test_acquisition_audit_validates_lagged_actions_and_terminal_contract(tmp_path: Path) -> None:
    plan, episodes = write_fixture(tmp_path)
    report = audit_acquisition(
        plan,
        episodes,
        provider="fixture",
        acquired_at_utc="2026-07-19T00:00:00Z",
    )
    assert report["status"] == "PASS"
    assert report["acquisition"]["observed_files"] == 1
    assert report["replay_contract"]["initial_60_card_actions"] == 2
    assert report["replay_contract"]["active_selection_requests"] == 2
    assert report["replay_contract"]["nonempty_lagged_selections"] == 1
    assert report["replay_contract"]["empty_lagged_selections"] == 1
    assert report["replay_contract"]["selection_count_violations"] == 0


def test_acquisition_audit_rejects_extra_files(tmp_path: Path) -> None:
    plan, episodes = write_fixture(tmp_path)
    (episodes / "extra.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ReplayAcquisitionError, match="file set differs"):
        audit_acquisition(plan, episodes, provider="fixture")


def test_acquisition_audit_rejects_size_drift(tmp_path: Path) -> None:
    plan, episodes = write_fixture(tmp_path)
    path = episodes / "90000001.json"
    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ReplayAcquisitionError, match="byte count differs"):
        audit_acquisition(plan, episodes, provider="fixture")


def test_acquisition_audit_rejects_same_step_or_unresolvable_action(tmp_path: Path) -> None:
    value = replay()
    value["steps"][2][0]["action"] = [99]
    plan, episodes = write_fixture(tmp_path, value)
    with pytest.raises(ReplayAcquisitionError, match="cannot be resolved"):
        audit_acquisition(plan, episodes, provider="fixture")


def test_acquisition_audit_rejects_selection_count_violation(tmp_path: Path) -> None:
    value = replay()
    value["steps"][2][0]["action"] = []
    plan, episodes = write_fixture(tmp_path, value)
    with pytest.raises(ReplayAcquisitionError, match="selection count"):
        audit_acquisition(plan, episodes, provider="fixture")
