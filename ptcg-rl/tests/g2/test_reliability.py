from __future__ import annotations

import json
import math
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import torch

from ptcg_rl.g1.models import ContractViolation
from ptcg_rl.g1.semantic import semantic_snapshot
from ptcg_rl.g2.network import PTCGPolicyV1
from ptcg_rl.g2.projection import project_decision
from ptcg_rl.g2.reliability import (
    AuditedRecurrentLedgerV1,
    PolicyAuditV1,
    ReliabilityError,
    RemoteNeuralPolicyV1,
    canonical_json_line,
    execute_inference_batch,
    percentile,
    read_game_records,
    recalculate_reliability,
    validate_game_record,
)

from ..g1_fixtures import raw_observation
from .test_card_table import build_fixture

CARD_HASH = "c" * 64


def decision_fixture(*, options: int = 2):
    raw = raw_observation(
        options=[{"type": 0, "number": index} for index in range(options)]
    )
    raw["select"].update(
        {"type": 8, "context": 38, "minCount": 1, "maxCount": 1}
    )
    observation, request = semantic_snapshot(raw, "reliability-fixture", 0, CARD_HASH)
    assert request is not None
    return observation, request, project_decision(observation, request)


def audit_record(*, choose_calls: int = 1, allocated_ms: float = 1.0) -> dict[str, Any]:
    return {
        "choose_calls": choose_calls,
        "meaningful_calls": choose_calls,
        "forced_calls": 0,
        "selected_steps": choose_calls,
        "stop_steps": 0,
        "reset_start": 1,
        "reset_terminal": 1,
        "reset_error": 0,
        "ownership_violations": 0,
        "stale_policy_requests": 0,
        "transport_violations": 0,
        "server_errors": 0,
        "invalid_responses": 0,
        "nonfinite_outputs": 0,
        "invalid_distributions": 0,
        "max_options": 2,
        "max_selected": 1,
        "roundtrip_ms_total": allocated_ms + 0.5,
        "roundtrip_ms_max": allocated_ms + 0.5,
        "allocated_inference_ms_total": allocated_ms,
        "allocated_inference_ms_max": allocated_ms,
        "batch_size_sum": 1,
        "batch_size_max": 1,
    }


def valid_game_record(game_index: int = 0, *, allocated_ms: float = 1.0) -> dict[str, Any]:
    engine_requests = 2
    return {
        "schema_version": 1,
        "record_id": f"g2-neural-policy-reliability-v1-game-{game_index:05d}",
        "game_index": game_index,
        "worker_id": 0,
        "server_id": 0,
        "summary": {
            "schema_version": 2,
            "episode_id": f"game-{game_index}",
            "first_player": 0,
            "terminal_result": 0,
            "player_rewards": [1.0, -1.0],
            "engine_requests": engine_requests,
            "meaningful_choices": engine_requests,
            "forced_requests": 0,
            "transition_records": engine_requests + 1,
            "invalid_selections": 0,
            "post_terminal_actions": 0,
            "fallback_actions": 0,
            "failure_kind": None,
            "selection_type_counts": {"8": engine_requests},
            "option_type_counts": {"NUMBER": 4},
            "multi_select_requests": 0,
            "max_observed_options": 2,
            "max_observed_select_count": 1,
            "wall_seconds": 0.1,
            "schema_metadata": {
                "schema_version": 2,
                "engine_sha256": "e" * 64,
                "card_data_sha256": "c" * 64,
                "observation_schema_sha256": "o" * 64,
                "action_schema_sha256": "a" * 64,
                "trajectory_schema_sha256": "t" * 64,
            },
        },
        "policy_audits": {
            "0": audit_record(choose_calls=1, allocated_ms=allocated_ms / 2),
            "1": audit_record(choose_calls=1, allocated_ms=allocated_ms / 2),
        },
        "ledger": {
            "active_keys_after": [],
            "reset_events": [
                [[f"game-{game_index}", 0, "g2-remote-neural-policy-v1"], "start"],
                [[f"game-{game_index}", 1, "g2-remote-neural-policy-v1"], "start"],
                [[f"game-{game_index}", 0, "g2-remote-neural-policy-v1"], "terminal"],
                [[f"game-{game_index}", 1, "g2-remote-neural-policy-v1"], "terminal"],
            ],
            "stale_requests": 0,
            "out_of_order_requests": 0,
            "ownership_violations": 0,
            "invalid_identities": 0,
        },
        "transition_count": engine_requests + 1,
        "action_transition_count": engine_requests,
        "terminal_transition_count": 1,
    }


class FakeConnection:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.sent: list[dict[str, Any]] = []

    def send(self, message: dict[str, Any]) -> None:
        self.sent.append(message)

    def recv(self) -> dict[str, Any]:
        request_id = self.sent[-1]["request_id"]
        return {"request_id": request_id, **self.response}


def successful_response(*, server_id: int = 0) -> dict[str, Any]:
    return {
        "kind": "response",
        "server_id": server_id,
        "batch_size": 1,
        "server_ms": 1.0,
        "hidden": [0.0] * 160,
        "steps": [
            {
                "kind": "choose",
                "index": 0,
                "probabilities": [0.5, 0.5, 0.0],
            }
        ],
    }


def test_policy_audit_timing_accepts_valid_and_rejects_all_invalid_boundaries() -> None:
    audit = PolicyAuditV1()
    audit.record_timing(3.0, 1.0, 2)
    assert audit.roundtrip_ms_total == 3.0
    assert audit.allocated_inference_ms_total == 1.0
    assert audit.batch_size_sum == 2
    for roundtrip, allocated, batch in (
        (-1.0, 1.0, 1),
        (math.nan, 1.0, 1),
        (1.0, -1.0, 1),
        (1.0, math.inf, 1),
        (1.0, 1.0, 0),
    ):
        with pytest.raises(ContractViolation):
            PolicyAuditV1().record_timing(roundtrip, allocated, batch)


def test_audited_recurrent_ledger_counts_stale_out_of_order_and_invalid_identity() -> None:
    ledger = AuditedRecurrentLedgerV1()
    ledger.reset_episode("episode", 0, "policy", reason="start")
    assert ledger.dispatch("episode", 0, "policy", 0, "request-0", lambda: 7) == 7
    with pytest.raises(ContractViolation, match="stale"):
        ledger.dispatch("episode", 0, "policy", 0, "different", lambda: 8)
    with pytest.raises(ContractViolation, match="out-of-order"):
        ledger.dispatch("episode", 0, "policy", 2, "request-2", lambda: 9)
    with pytest.raises(ContractViolation):
        ledger.dispatch("episode", 0, "policy", -1, "bad", lambda: 10)
    assert ledger.stale_requests == 1
    assert ledger.out_of_order_requests == 1
    assert ledger.invalid_identities == 1


def test_remote_policy_builds_valid_action_and_updates_audit() -> None:
    observation, request, _ = decision_fixture()
    connection = FakeConnection(successful_response())
    audit = PolicyAuditV1()
    policy = RemoteNeuralPolicyV1(connection, 3, 0, 0, 160, audit)
    policy.reset(request.episode_uuid, 0, "start")
    action = policy.choose(observation, request)
    policy.reset(request.episode_uuid, 0, "terminal")
    assert action.submitted_original_indices == (0,)
    assert audit.choose_calls == 1
    assert audit.selected_steps == 1
    assert audit.invalid_responses == 0
    assert audit.reset_start == audit.reset_terminal == 1
    assert connection.sent[0]["projection"].transport.request_id == request.request_id


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.update(server_id=1), "identity"),
        (lambda value: value.update(hidden=[0.0]), "hidden"),
        (lambda value: value.update(steps=None), "steps"),
        (lambda value: value.update(batch_size=0), "timing"),
        (lambda value: value.update(server_ms=float("nan")), "timing"),
        (
            lambda value: value.update(
                steps=[{"kind": "choose", "index": 9, "probabilities": [0.5, 0.5, 0.0]}]
            ),
            "masked or nonexistent",
        ),
    ],
)
def test_remote_policy_rejects_malformed_responses(mutation, message: str) -> None:
    observation, request, _ = decision_fixture()
    response = successful_response()
    mutation(response)
    audit = PolicyAuditV1()
    policy = RemoteNeuralPolicyV1(FakeConnection(response), 0, 0, 0, 160, audit)
    policy.reset(request.episode_uuid, 0, "start")
    with pytest.raises(ContractViolation, match=message):
        policy.choose(observation, request)
    assert audit.invalid_responses == 1


def test_remote_policy_rejects_stale_request_and_wrong_reset_ownership() -> None:
    observation, request, _ = decision_fixture()
    audit = PolicyAuditV1()
    policy = RemoteNeuralPolicyV1(FakeConnection(successful_response()), 0, 0, 0, 160, audit)
    with pytest.raises(ContractViolation, match="player differs"):
        policy.reset(request.episode_uuid, 1, "start")
    policy.reset(request.episode_uuid, 0, "start")
    policy.choose(observation, request)
    with pytest.raises(ContractViolation, match="stale"):
        policy.choose(observation, request)
    assert audit.ownership_violations == 1
    assert audit.stale_policy_requests == 1


def test_execute_inference_batch_runs_real_model_and_decoder(tmp_path: Path) -> None:
    _, request, projection = decision_fixture()
    model = PTCGPolicyV1(build_fixture(tmp_path / "cards.csv")).eval()
    responses = execute_inference_batch(
        model,
        [{"projection": projection, "request": request, "hidden": None}],
        torch.device("cpu"),
    )
    assert len(responses) == 1
    assert len(responses[0]["hidden"]) == model.config.public_hidden
    assert responses[0]["steps"]


@pytest.mark.parametrize(
    "message",
    [
        {"projection": object(), "request": object(), "hidden": None},
        {"projection": None, "request": None, "hidden": None},
    ],
)
def test_execute_inference_batch_rejects_invalid_message_types(
    tmp_path: Path, message: dict[str, Any]
) -> None:
    model = PTCGPolicyV1(build_fixture(tmp_path / "cards.csv")).eval()
    with pytest.raises(ReliabilityError):
        execute_inference_batch(model, [message], torch.device("cpu"))


def test_execute_inference_batch_rejects_nonfinite_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, request, projection = decision_fixture()
    model = PTCGPolicyV1(build_fixture(tmp_path / "cards.csv")).eval()
    original = model.forward

    def corrupted(batch, hidden=None):
        output = original(batch, hidden)
        return replace(output, values=torch.full_like(output.values, float("nan")))

    monkeypatch.setattr(model, "forward", corrupted)
    with pytest.raises(ContractViolation, match="nonfinite"):
        execute_inference_batch(
            model,
            [{"projection": projection, "request": request, "hidden": None}],
            torch.device("cpu"),
        )


def test_validate_game_record_accepts_exact_record_and_rejects_each_zero_counter() -> None:
    record = valid_game_record()
    assert validate_game_record(record) == []
    mutations = (
        ("summary", "invalid_selections"),
        ("summary", "fallback_actions"),
        ("summary", "post_terminal_actions"),
        ("ledger", "stale_requests"),
        ("ledger", "out_of_order_requests"),
        ("ledger", "ownership_violations"),
        ("ledger", "invalid_identities"),
    )
    for section, field in mutations:
        changed = json.loads(json.dumps(record))
        changed[section][field] = 1
        assert validate_game_record(changed)
    for field in (
        "ownership_violations",
        "stale_policy_requests",
        "transport_violations",
        "server_errors",
        "invalid_responses",
        "nonfinite_outputs",
        "invalid_distributions",
        "reset_error",
    ):
        changed = json.loads(json.dumps(record))
        changed["policy_audits"]["0"][field] = 1
        assert validate_game_record(changed)


def test_recalculate_reliability_detects_complete_duplicate_missing_and_limit() -> None:
    first = valid_game_record(0, allocated_ms=10.0)
    second = valid_game_record(1, allocated_ms=20.0)
    passed = recalculate_reliability([first, second], 2)
    assert passed["status"] == "PASS"
    assert passed["observed_games"] == 2
    assert passed["projected_cpu_host_inference_limit"]["pass"] is True

    duplicate = recalculate_reliability([first, first], 2)
    assert duplicate["status"] == "FAIL"
    assert duplicate["duplicate_indices"] == [0]
    assert duplicate["missing_indices"] == [1]

    slow = valid_game_record(0, allocated_ms=120_000.01)
    limited = recalculate_reliability([slow], 1)
    assert limited["status"] == "FAIL"
    assert limited["projected_cpu_host_inference_limit"]["pass"] is False

    failed = recalculate_reliability([first], 1, process_failures=["worker crash"])
    assert failed["status"] == "FAIL"
    assert failed["process_failures"] == ["worker crash"]


def test_canonical_jsonl_round_trip_and_rejection(tmp_path: Path) -> None:
    record = valid_game_record()
    path = tmp_path / "games.jsonl"
    raw = canonical_json_line(record)
    path.write_bytes(raw)
    records, digest, size = read_game_records(path)
    assert records == [json.loads(raw)]
    assert len(digest) == 64
    assert size == len(raw)

    path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ReliabilityError, match="canonical"):
        read_game_records(path)
    path.write_bytes(b"not-json\n")
    with pytest.raises(ReliabilityError, match="valid UTF-8 JSON"):
        read_game_records(path)


def test_percentile_boundaries() -> None:
    assert percentile([], 0.5) is None
    assert percentile([3.0, 1.0, 2.0], 0.0) == 1.0
    assert percentile([3.0, 1.0, 2.0], 1.0) == 3.0
    with pytest.raises(ValueError):
        percentile([1.0], -0.1)
