from __future__ import annotations

from dataclasses import replace

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from ptcg_rl.g1.semantic import semantic_snapshot

from ptcg_rl.replay.semantic_loader import (
    ReplaySemanticError,
    SemanticReplayLoader,
    audit_semantic_loader,
    decode_replay_action,
    load_verified_official_card_data_sha256,
)
from ..g1_fixtures import raw_observation

CARD_HASH = "c" * 64


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def make_plan(filename: str, size: int) -> dict[str, Any]:
    plan: dict[str, Any] = {
        "schema_version": 1,
        "planner_version": "semantic-fixture-v1",
        "created_at_utc": "2026-07-19T00:00:00Z",
        "source": {
            "index": {
                "dataset_owner": "kaggle",
                "dataset_slug": "index",
                "dataset_version": 33,
            },
            "daily": {
                "dataset_owner": "kaggle",
                "dataset_slug": "daily",
                "dataset_version": 1,
            },
            "source_date": "2026-07-18",
        },
        "selection_profile": {
            "caps": {
                "max_files": 1,
                "max_total_bytes": 100_000,
                "max_file_bytes": 100_000,
            }
        },
        "summary": {"selected_files": 1, "selected_bytes": size},
        "selected_items": [{"remote_filename": filename, "declared_bytes": size}],
        "rows": [],
    }
    payload = dict(plan)
    payload.pop("created_at_utc")
    plan["plan_sha256"] = hashlib.sha256(canonical(payload)).hexdigest()
    return plan


def terminal_observation() -> dict[str, Any]:
    raw = raw_observation(result=0)
    raw["select"] = None
    return raw


def record(
    status: str,
    action: list[int],
    observation: dict[str, Any],
    reward: int = 0,
) -> dict[str, Any]:
    return {
        "action": action,
        "info": {},
        "observation": observation,
        "reward": reward,
        "status": status,
    }


def ordered_request() -> dict[str, Any]:
    raw = raw_observation(min_count=1, max_count=2)
    raw["current"]["firstPlayer"] = -1
    raw["current"]["players"][0]["active"] = [
        {
            "id": 100,
            "serial": 10,
            "playerIndex": 0,
            "hp": 100,
            "maxHp": 120,
            "appearThisTurn": False,
            "energies": [],
            "energyCards": [],
            "tools": [],
            "preEvolution": [],
        }
    ]
    raw["current"]["players"][0]["bench"] = [
        {
            "id": 101,
            "serial": 11,
            "playerIndex": 0,
            "hp": 80,
            "maxHp": 80,
            "appearThisTurn": False,
            "energies": [],
            "energyCards": [],
            "tools": [],
            "preEvolution": [],
        }
    ]
    raw["select"].update(
        {
            "type": 5,
            "context": 34,
            "option": [
                {"type": 15, "cardId": 100, "serial": 10},
                {"type": 15, "cardId": 101, "serial": 11},
            ],
        }
    )
    return raw


def replay(action: list[int] | None = None) -> dict[str, Any]:
    chosen = [1] if action is None else action
    initialization = {"current": None, "logs": [], "select": None}
    inactive = {"current": None, "logs": [], "select": None}
    return {
        "schema_version": 1,
        "module_version": "1.32.0",
        "id": "internal-semantic-fixture",
        "statuses": ["DONE", "DONE"],
        "rewards": [1, -1],
        "steps": [
            [
                record("ACTIVE", [], initialization),
                record("ACTIVE", [], initialization),
            ],
            [
                record("ACTIVE", list(range(60)), ordered_request()),
                record("INACTIVE", list(range(60)), inactive),
            ],
            [
                record("DONE", chosen, terminal_observation(), 1),
                record("DONE", [], terminal_observation(), -1),
            ],
        ],
    }


def write_fixture(
    tmp_path: Path, value: dict[str, Any] | None = None
) -> tuple[dict[str, Any], Path]:
    episodes = tmp_path / "episodes"
    episodes.mkdir()
    path = episodes / "90000001.json"
    path.write_text(json.dumps(value or replay()), encoding="utf-8")
    return make_plan(path.name, path.stat().st_size), episodes


def test_loader_lag_aligns_projects_and_reconstructs_ordered_stop(tmp_path: Path) -> None:
    plan, episodes = write_fixture(tmp_path)
    decisions = list(SemanticReplayLoader(plan, episodes, card_data_sha256=CARD_HASH))
    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.request_step_index == 1
    assert decision.action_step_index == 2
    assert decision.sequence_index == 0
    assert decision.observation.first_player is None
    assert decision.request.ordering == "ORDERED"
    assert decision.action.submitted_original_indices == (1,)
    assert decision.action.stopped_early is True
    assert decision.action.decoder_trace[-1] == "STOP"
    assert decision.action.chosen_semantic_fingerprints == (
        decision.request.options[1].semantic_fingerprint,
    )
    assert decision.projected.transport.original_indices == (0, 1)


def test_decode_replay_action_rejects_duplicates_range_and_count(tmp_path: Path) -> None:
    plan, episodes = write_fixture(tmp_path)
    request = next(iter(SemanticReplayLoader(plan, episodes, card_data_sha256=CARD_HASH))).request
    with pytest.raises(ReplaySemanticError, match="duplicate"):
        decode_replay_action(request, (0, 0))
    with pytest.raises(ReplaySemanticError, match="out-of-range"):
        decode_replay_action(request, (2,))
    with pytest.raises(ReplaySemanticError, match="count bounds"):
        decode_replay_action(request, ())


def test_decode_replay_action_handles_optional_exact_max_and_invalid_types(tmp_path: Path) -> None:
    plan, episodes = write_fixture(tmp_path)
    request = next(iter(SemanticReplayLoader(plan, episodes, card_data_sha256=CARD_HASH))).request

    exact_max = decode_replay_action(request, (0, 1))
    assert exact_max.stopped_early is False
    assert exact_max.decoder_trace == tuple(
        f"OPTION:{request.options[index].semantic_fingerprint}" for index in (0, 1)
    )

    optional = raw_observation(options=[{"type": 1}], min_count=0, max_count=1)
    optional["current"]["firstPlayer"] = -1
    observation, optional_request = semantic_snapshot(optional, "optional", 0, CARD_HASH)
    assert observation.first_player is None
    assert optional_request is not None
    stopped = decode_replay_action(optional_request, ())
    assert stopped.stopped_early is True
    assert stopped.decoder_trace == ("STOP",)

    with pytest.raises(ReplaySemanticError, match="only integers"):
        decode_replay_action(request, (True,))
    unavailable = replace(request.options[0], available=False)
    unavailable_request = replace(
        request,
        min_count=1,
        max_count=1,
        options=(unavailable, request.options[1]),
    )
    with pytest.raises(ReplaySemanticError, match="unavailable"):
        decode_replay_action(unavailable_request, (0,))


def test_loader_rejects_corrupted_transport_and_extra_files(tmp_path: Path) -> None:
    plan, episodes = write_fixture(tmp_path, replay([9]))
    with pytest.raises(ReplaySemanticError, match="out-of-range"):
        list(SemanticReplayLoader(plan, episodes, card_data_sha256=CARD_HASH))
    (episodes / "extra.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ReplaySemanticError, match="file set differs"):
        SemanticReplayLoader(plan, episodes, card_data_sha256=CARD_HASH)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value.__setitem__("statuses", ["ACTIVE", "DONE"]), "terminal for both"),
        (lambda value: value.__setitem__("rewards", [0, 0]), "unsupported terminal rewards"),
        (lambda value: value["steps"].__setitem__(0, [value["steps"][0][0]]), "two agent records"),
        (lambda value: value["steps"][0][0].__setitem__("action", [0]), "empty active initialization"),
        (lambda value: value["steps"][1][0].__setitem__("action", [0] * 59), "60-card deck action"),
        (lambda value: value["steps"][2][1].__setitem__("action", [0]), "acts after a non-active"),
        (lambda value: value["steps"][-1][0].__setitem__("reward", -1), "terminal records differ"),
    ],
)
def test_loader_fails_closed_on_structural_corruption(
    tmp_path: Path, mutate, message: str
) -> None:
    value = replay()
    mutate(value)
    plan, episodes = write_fixture(tmp_path, value)
    with pytest.raises(ReplaySemanticError, match=message):
        list(SemanticReplayLoader(plan, episodes, card_data_sha256=CARD_HASH))


def test_loader_rejects_partial_missing_size_drift_malformed_json_and_bad_hash(
    tmp_path: Path,
) -> None:
    plan, episodes = write_fixture(tmp_path)
    path = episodes / "90000001.json"

    (episodes / "pending.partial").write_text("partial", encoding="utf-8")
    with pytest.raises(ReplaySemanticError, match="partials"):
        SemanticReplayLoader(plan, episodes, card_data_sha256=CARD_HASH)
    (episodes / "pending.partial").unlink()

    original = path.read_text(encoding="utf-8")
    path.write_text(original + " ", encoding="utf-8")
    with pytest.raises(ReplaySemanticError, match="byte count differs"):
        list(SemanticReplayLoader(plan, episodes, card_data_sha256=CARD_HASH))
    path.write_text(original, encoding="utf-8")

    path.write_text("{" + " " * (path.stat().st_size - 1), encoding="utf-8")
    with pytest.raises(ReplaySemanticError, match="cannot parse replay"):
        list(SemanticReplayLoader(plan, episodes, card_data_sha256=CARD_HASH))

    path.unlink()
    with pytest.raises(ReplaySemanticError, match="missing"):
        SemanticReplayLoader(plan, episodes, card_data_sha256=CARD_HASH)
    with pytest.raises(ReplaySemanticError, match="lowercase SHA-256"):
        SemanticReplayLoader(plan, episodes, card_data_sha256="C" * 64)


def test_official_card_data_hash_requires_record_and_file_byte_parity(tmp_path: Path) -> None:
    card_data = tmp_path / "EN_Card_Data.csv"
    card_data.write_bytes(b"verified-card-data")
    expected = hashlib.sha256(card_data.read_bytes()).hexdigest()
    asset_hashes = tmp_path / "asset_hashes.redacted.json"
    asset_hashes.write_text(
        json.dumps(
            {
                "assets": {
                    "official": {
                        "signature_sha256": {"card_data": expected}
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    assert load_verified_official_card_data_sha256(asset_hashes, card_data) == expected
    card_data.write_bytes(b"drifted-card-data")
    with pytest.raises(ReplaySemanticError, match="differs from asset record"):
        load_verified_official_card_data_sha256(asset_hashes, card_data)


def test_semantic_audit_is_deterministic_and_expected_hash_fails_closed(
    tmp_path: Path,
) -> None:
    plan, episodes = write_fixture(tmp_path)
    first = audit_semantic_loader(
        plan,
        episodes,
        card_data_sha256=CARD_HASH,
        created_at_utc="2026-07-19T00:00:00Z",
    )
    second = audit_semantic_loader(
        plan,
        episodes,
        card_data_sha256=CARD_HASH,
        created_at_utc="2026-07-19T00:01:00Z",
        expected_stream_sha256=first["semantic_stream_sha256"],
    )
    assert first["semantic_stream_sha256"] == second["semantic_stream_sha256"]
    assert first["coverage"]["decisions"] == 1
    assert first["coverage"]["chosen_options"] == 1
    assert first["coverage"]["stop_markers"] == 1
    assert first["coverage"]["ordered_requests"] == 1
    with pytest.raises(ReplaySemanticError, match="differs from expected"):
        audit_semantic_loader(
            plan,
            episodes,
            card_data_sha256=CARD_HASH,
            expected_stream_sha256="0" * 64,
        )


def test_loader_uses_preceding_request_not_same_step_observation(tmp_path: Path) -> None:
    value = replay([1])
    value["steps"][2][0]["observation"] = raw_observation(
        options=[{"type": 0, "number": 99}],
        min_count=1,
        max_count=1,
    )
    value["steps"][2][0]["observation"]["select"].update(
        {"type": 8, "context": 38}
    )
    plan, episodes = write_fixture(tmp_path, value)
    decision = next(iter(SemanticReplayLoader(plan, episodes, card_data_sha256=CARD_HASH)))
    assert len(decision.request.options) == 2
    assert decision.request.options[1].card_id == 101
