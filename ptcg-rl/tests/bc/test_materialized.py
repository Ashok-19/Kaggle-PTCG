from __future__ import annotations

import hashlib

import torch

from ptcg_rl.bc.materialized import (
    build_episode_payload,
    load_materialized_episode,
    save_episode_payload,
)
from ptcg_rl.bc.training import recurrent_sequence_batch_loss
from ptcg_rl.replay.semantic_loader import SemanticReplayActionV1, SemanticReplayDecisionV1
from ..g2.test_network import model, number_decision


def _decision(sequence_index: int, choice: int) -> SemanticReplayDecisionV1:
    observation, request, projected = number_decision(5)
    action = SemanticReplayActionV1(
        schema_version=1,
        submitted_original_indices=(choice,),
        chosen_semantic_fingerprints=(request.options[choice].semantic_fingerprint,),
        decoder_trace=(f"OPTION:{request.options[choice].semantic_fingerprint}",),
        stopped_early=False,
    )
    return SemanticReplayDecisionV1(
        schema_version=1,
        episode_id="123",
        internal_replay_id="fixture",
        agent_index=1,
        request_step_index=sequence_index,
        action_step_index=sequence_index + 1,
        sequence_index=sequence_index,
        observation=observation,
        request=request,
        projected=projected,
        action=action,
        reward=0.0,
    )


def test_materialized_episode_round_trip_and_loss_parity(tmp_path) -> None:
    decisions = (_decision(0, 1), _decision(1, 3), _decision(2, 4))
    source_sha = hashlib.sha256(b"source-replay").hexdigest()
    payload = build_episode_payload(
        episode_id=123,
        teacher_player_index=1,
        split="train",
        teacher_result="loss",
        teacher_team_name="teacher",
        source_replay_sha256=source_sha,
        decisions=decisions,
    )
    path = tmp_path / "123.pt"
    receipt = save_episode_payload(path, payload)
    loaded = load_materialized_episode(path, expected_sha256=receipt["sha256"])
    assert loaded.episode_id == 123
    assert loaded.teacher_player_index == 1
    assert loaded.teacher_result == "loss"
    assert loaded.source_replay_sha256 == source_sha
    assert loaded.policy_targets == 3
    assert len(loaded.decisions) == 3

    torch.manual_seed(11)
    policy = model(tmp_path).eval()
    reference = recurrent_sequence_batch_loss(policy, (decisions,), verify=False)
    observed = recurrent_sequence_batch_loss(policy, (loaded.decisions,), verify=False)
    assert reference.policy_targets == observed.policy_targets == 3
    assert torch.allclose(reference.next_hidden, observed.next_hidden, atol=1e-6, rtol=1e-6)
    assert torch.allclose(reference.loss, observed.loss, atol=1e-6, rtol=1e-6)
