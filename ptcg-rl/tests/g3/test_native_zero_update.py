from __future__ import annotations

import json
from pathlib import Path

import pytest
import torch

from ptcg_rl.g1.semantic import semantic_snapshot
from ptcg_rl.g2.network import PTCGPolicyV1
from ptcg_rl.g3.e04_authorization import (
    E04AuthorizationError,
    load_native_authorization,
)
from ptcg_rl.g3.native_zero_update import (
    EngineRequestSequenceV1,
    NATIVE_POLICY_ID,
    NativeTraceNeuralPolicyV1,
)
from ptcg_rl.g3.zero_update_bridge import ZeroUpdateBridgeV1
from ..g1_fixtures import raw_observation
from ..g2.test_card_table import build_fixture


ROOT = Path(__file__).resolve().parents[2]
CARD_HASH = "c" * 64


def decision(*, episode: str, selection_seq: int):
    raw = raw_observation(
        options=[{"type": 0, "number": value} for value in range(3)],
        min_count=1,
        max_count=2,
    )
    raw["select"].update({"type": 8, "context": 38})
    observation, request = semantic_snapshot(raw, episode, selection_seq, CARD_HASH)
    assert request is not None
    return observation, request


def model(tmp_path: Path) -> PTCGPolicyV1:
    policy = PTCGPolicyV1(build_fixture(tmp_path / "cards.csv"))
    policy.eval()
    return policy


def test_exact_request_is_consumed_and_non_authorizing() -> None:
    path = ROOT / "configs/e04_single_process_trace_request_v1.json"
    value = json.loads(path.read_text())
    request = load_native_authorization(path, require_authorized=False)
    assert request.stage == "single_process_trace"
    assert request.games == 1
    assert request.minimum_meaningful_decisions == 1
    assert request.optimizer_steps_authorized == 0
    assert request.external_compute_authorized is False
    assert request.authorized is False
    assert value["authorization_scope"] == "CONSUMED_AFTER_SINGLE_APPROVED_EXECUTION"
    assert value["consumed_authorization_sha256"] == (
        "8b801f8432e821c3a43be10645f3fc89d1422ab329c2acd2df26ce1aac7a72ad"
    )
    assert value["bridge_checkpoint_sha256"] == (
        "bb71dcbee278478af9f1c37c206a99da2a47471b08905c11a7b7ddbb05f0f59f"
    )
    with pytest.raises(E04AuthorizationError, match="not authorized"):
        load_native_authorization(path, require_authorized=True)


def test_authorization_rejects_game_count_or_optimizer_escalation(tmp_path: Path) -> None:
    value = json.loads(
        (ROOT / "configs/e04_single_process_trace_request_v1.json").read_text()
    )
    value["authorized"] = True
    value["games"] = 2
    path = tmp_path / "bad-games.json"
    path.write_text(json.dumps(value))
    with pytest.raises(E04AuthorizationError, match="game count"):
        load_native_authorization(path)
    value["games"] = 1
    value["optimizer_steps_authorized"] = 1
    path.write_text(json.dumps(value))
    with pytest.raises(E04AuthorizationError, match="zero optimizer"):
        load_native_authorization(path)


def test_single_process_trace_public_evidence_passes_without_authorizing_more() -> None:
    report = json.loads(
        (ROOT / "reports/evaluations/e04-single-process-trace-v1.json").read_text()
    )
    assert report["status"] == "SUCCEEDED"
    assert report["decision"] == "PASS"
    assert report["authorization"]["authorization_consumed"] is True
    assert report["authorization"]["current_request_authorized"] is False
    assert report["authorization"]["rerun_authorized"] is False
    assert report["authorization"]["later_stage_authorized"] is False
    assert report["execution"] == {
        "cabt_episode_count": 1,
        "cabt_rerun_count_during_recovery": 0,
        "device": "cpu",
        "external_compute_used": False,
        "optimizer_created": False,
        "optimizer_steps": 0,
        "single_process": True,
        "training_loop_ran": False,
    }
    results = report["results"]
    assert results["games"] == 1
    assert results["engine_decisions"] == 67
    assert results["meaningful_decisions"] == 63
    assert results["forced_decisions"] == 4
    assert results["terminal_result"] == 1
    assert results["terminal_boundaries_for_both_players"] == 1
    assert results["maximum_compound_log_probability_absolute_error"] <= 1e-5
    assert set(results["zero_tolerance"].values()) == {0}
    assert report["incident"]["additional_cabt_execution"] is False
    assert report["qualification_scope"]["ten_game_smoke"] is False
    assert report["qualification_scope"]["policy_competence"] is False


def test_ten_game_smoke_request_is_consumed_and_non_authorizing() -> None:
    path = ROOT / "configs/e04_ten_game_smoke_request_v1.json"
    value = json.loads(path.read_text())
    request = load_native_authorization(path, require_authorized=False)
    assert request.stage == "smoke"
    assert request.games == 10
    assert request.minimum_meaningful_decisions == 1
    assert request.authorized is False
    assert request.optimizer_steps_authorized == 0
    assert request.external_compute_authorized is False
    assert value["authorization_scope"] == (
        "CONSUMED_AFTER_TEN_GAME_APPROVED_EXECUTION"
    )
    assert value["authorization_snapshot_sha256"] == (
        "f8019962c4914fa1cfac754b1af7616db69fdb4e0503e89cb46f6282cd2f4922"
    )
    assert value["runner_sha256"] == (
        "e30ce8d0b468058a95473ee7a0f5fc67dafe797d21c3f40c1c6baa81bd8a8bd3"
    )
    assert value["prerequisite_evidence_sha256"] == (
        "d169bb3c955197607bb4ae9c13c46ba9aedb79afbc708548d5b680374ba99653"
    )
    with pytest.raises(E04AuthorizationError, match="not authorized"):
        load_native_authorization(path, require_authorized=True)


def test_ten_game_smoke_public_evidence_passes_without_authorizing_more() -> None:
    report = json.loads(
        (ROOT / "reports/evaluations/e04-ten-game-smoke-v1.json").read_text()
    )
    assert report["status"] == "SUCCEEDED"
    assert report["decision"] == "PASS"
    assert report["stage"] == "smoke"
    assert report["authorization"]["authorization_consumed"] is True
    assert report["authorization"]["current_request_authorized"] is False
    assert report["authorization"]["rerun_authorized"] is False
    assert report["authorization"]["hundred_game_stage_authorized"] is False
    assert report["execution"]["device"] == "cpu"
    assert report["execution"]["optimizer_steps"] == 0
    assert report["execution"]["training_loop_ran"] is False
    results = report["results"]
    assert results["games"] == 10
    assert results["engine_decisions"] == 711
    assert results["meaningful_decisions"] == 648
    assert results["forced_decisions"] == 63
    assert results["terminal_boundaries_for_both_players"] == 10
    assert results["terminal_result_counts"] == {"-1": 0, "0": 4, "1": 6}
    assert results["maximum_compound_log_probability_absolute_error"] <= 1e-5
    assert set(results["zero_tolerance"].values()) == {0}
    assert len(results["per_game"]) == 10
    assert report["qualification_scope"]["ten_game_smoke"] is True
    assert report["qualification_scope"]["hundred_game_qualification"] is False
    assert report["qualification_scope"]["policy_competence"] is False


def test_qualification_request_is_consumed_and_non_authorizing() -> None:
    path = ROOT / "configs/e04_qualification_request_v1.json"
    value = json.loads(path.read_text())
    request = load_native_authorization(path, require_authorized=False)
    assert value["decision_id"] == "DEC-012"
    assert request.stage == "qualification"
    assert request.games == 180
    assert request.minimum_meaningful_decisions == 10_000
    assert request.bridge_checkpoint_interval_games == 10
    assert request.authorized is False
    assert request.optimizer_steps_authorized == 0
    assert request.external_compute_authorized is False
    assert value["authorization_scope"] == (
        "CONSUMED_AFTER_180_GAME_APPROVED_EXECUTION"
    )
    assert value["authorization_snapshot_sha256"] == (
        "cab752414df29ad9d7ceb78baf46c44cb2fbba7384c02e6aad3e72b55ad1a947"
    )
    assert value["native_report_sha256"] == (
        "e7c85dfeeb14d8bdc23c5ed11bf4fe86bdcbf4f64348fe9a313f11b999e3a56e"
    )
    assert value["game_ledger_sha256"] == (
        "b45be2af9f8011fa99e040a5b4069aa59a3e59d78450ca0b08a4a019e02e0672"
    )
    assert value["bridge_checkpoint_sha256"] == (
        "9a9e89d737ef640ab14eb64d4756c89d37dc75b4049bc5a7a3c0598114bc9c22"
    )
    assert value["maximum_requests_per_game"] == 20_000
    assert value["game_timeout_seconds"] == 300.0
    assert value["runner_sha256"] == (
        "cd5ef3a7e987f92172f218991084e3a0a1f3002e9df9acac57919a4ee23c63b7"
    )
    assert value["authorization_validator_sha256"] == (
        "f84fa26251c4ae4cf0294b12eadf5b0b87fdd9193909ed21b4f116776e7941e3"
    )
    assert value["decision_sha256"] == (
        "4667d8c08f9fb6782d37729f14ed097323c4b31efafdd87f44da9bdb2ad40307"
    )
    assert value["prerequisite_evidence_sha256"] == (
        "66d00da9e0b99783fd3f7ec441a89fa298597acbc1818220014a97481ba68236"
    )
    assert (ROOT / request.output_directory).is_dir()
    with pytest.raises(E04AuthorizationError, match="not authorized"):
        load_native_authorization(path, require_authorized=True)


def test_qualification_public_evidence_passes_without_authorizing_more() -> None:
    report = json.loads(
        (ROOT / "reports/evaluations/e04-qualification-v1.json").read_text()
    )
    assert report["status"] == "SUCCEEDED"
    assert report["decision"] == "PASS"
    assert report["stage"] == "qualification"
    assert report["authorization"]["authorization_consumed"] is True
    assert report["authorization"]["current_request_authorized"] is False
    assert report["authorization"]["rerun_authorized"] is False
    assert report["authorization"]["later_native_stage_authorized"] is False
    assert report["execution"]["device"] == "cpu"
    assert report["execution"]["bridge_checkpoint_interval_games"] == 10
    assert report["execution"]["optimizer_steps"] == 0
    assert report["execution"]["training_loop_ran"] is False
    results = report["results"]
    assert results["games"] == 180
    assert results["engine_decisions"] == 12_194
    assert results["meaningful_decisions"] == 11_250
    assert results["forced_decisions"] == 944
    assert results["terminal_boundaries_for_both_players"] == 180
    assert results["terminal_result_counts"] == {"-1": 0, "0": 99, "1": 81}
    assert results["maximum_compound_log_probability_absolute_error"] <= 1e-5
    assert set(results["zero_tolerance"].values()) == {0}
    assert len(results["per_game"]) == 180
    assert report["qualification_scope"]["zero_update_bridge_qualified"] is True
    assert report["qualification_scope"]["policy_competence"] is False
    assert report["qualification_scope"]["training_authorized"] is False


def test_old_hundred_game_qualification_contract_is_rejected(tmp_path: Path) -> None:
    value = json.loads((ROOT / "configs/e04_qualification_request_v1.json").read_text())
    value["authorized"] = True
    value["games"] = 100
    path = tmp_path / "old-qualification.json"
    path.write_text(json.dumps(value))
    with pytest.raises(E04AuthorizationError, match="game count"):
        load_native_authorization(path)


def test_qualification_contract_review_accepts_180_games_only() -> None:
    report = json.loads(
        (ROOT / "reports/artifacts/e04-qualification-contract-review-v1.json").read_text()
    )
    assert report["status"] == "PASS"
    assert report["decision"] == "ACCEPT_180_GAME_QUALIFICATION_CONTRACT"
    assert report["accepted_decision"]["decision"] == "DEC-012"
    assert report["accepted_decision"]["games"] == 180
    assert report["accepted_decision"]["minimum_meaningful_decisions"] == 10_000
    assert report["sizing"]["games_required_at_observed_minimum"] == 179
    assert report["sizing"]["games_required_at_99_percent_lower_bound"] == 168
    assert report["sizing"]["selected_projection_at_observed_minimum"] == 10_080
    assert report["request"]["authorized"] is False
    assert report["request"]["output_directory_exists"] is False
    assert report["authorization"]["qualification_execution"] is False
    assert report["authorization"]["optimizer_steps"] is False
    assert report["authorization"]["external_compute"] is False


def test_native_policy_records_exact_compound_trace_without_optimizer(
    tmp_path: Path,
) -> None:
    policy_model = model(tmp_path)
    bridge = ZeroUpdateBridgeV1(policy_id=NATIVE_POLICY_ID)
    sequence = EngineRequestSequenceV1()
    bridge.start_episode("episode")
    policy0 = NativeTraceNeuralPolicyV1(
        model=policy_model,
        bridge=bridge,
        player_index=0,
        request_sequence=sequence,
    )
    policy0.reset("episode", 0, "start")
    observation, request = decision(episode="episode", selection_seq=0)
    with torch.inference_mode():
        action = policy0.choose(observation, request)
    assert action.policy_loss_mask == 1
    assert sequence.next_value == 1
    bridge.close_terminal_episode("episode", 1)
    state = bridge.state_dict()["episodes"]["episode"]
    assert set(state["player_boundaries"]) == {"0", "1"}
    assert state["player_boundaries"]["0"]["terminal_reward"] == 1
    assert state["player_boundaries"]["1"]["terminal_reward"] == -1
    assert bridge.optimizer_steps == 0
    assert max(
        trace["replay_absolute_error"]
        for trace in state["owners"]["0"]["traces"]
    ) <= 1e-5


def test_terminal_boundary_exists_for_players_with_zero_decisions() -> None:
    bridge = ZeroUpdateBridgeV1(policy_id="policy")
    bridge.start_episode("episode")
    rewards = bridge.close_terminal_episode("episode", 0)
    assert rewards == (0, 0)
    state = bridge.state_dict()["episodes"]["episode"]
    assert state["owners"]["0"]["events"] == []
    assert state["owners"]["1"]["events"] == []
    assert set(state["player_boundaries"]) == {"0", "1"}
    restored = ZeroUpdateBridgeV1.from_state_dict(bridge.state_dict())
    assert restored.state_dict() == bridge.state_dict()
