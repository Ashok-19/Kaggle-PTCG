from __future__ import annotations

import torch

from ptcg_rl.bc.training import (
    pack_recurrent_group,
    packed_recurrent_chunk_loss,
    recurrent_sequence_batch_loss,
)
from ptcg_rl.g3.bc_canary import _action_nll
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
        episode_id=f"fixture-{sequence_index}",
        internal_replay_id="fixture",
        agent_index=0,
        request_step_index=sequence_index,
        action_step_index=sequence_index + 1,
        sequence_index=sequence_index,
        observation=observation,
        request=request,
        projected=projected,
        action=action,
        reward=0.0,
    )


def test_batched_recurrent_loss_matches_sequential_semantics(tmp_path) -> None:
    torch.manual_seed(7)
    policy = model(tmp_path).eval()
    sequences = (
        (_decision(0, 1), _decision(1, 2), _decision(2, 3)),
        (_decision(0, 4), _decision(1, 0)),
    )

    sequential_losses = []
    for sequence in sequences:
        hidden = policy.initial_hidden(1, "cpu")
        for decision in sequence:
            loss, hidden, _ = _action_nll(policy, decision, hidden)
            assert loss is not None
            sequential_losses.append(loss)
    expected = torch.stack(sequential_losses).mean()

    observed = recurrent_sequence_batch_loss(policy, sequences, verify=True)
    assert observed.policy_targets == 5
    assert observed.recurrent_decisions == 5
    assert observed.next_hidden.shape == (2, policy.config.public_hidden)
    assert torch.allclose(observed.loss, expected, atol=1e-6, rtol=1e-6)

    fast = recurrent_sequence_batch_loss(policy, sequences, verify=False)
    assert fast.policy_targets == observed.policy_targets
    assert fast.recurrent_decisions == observed.recurrent_decisions
    assert torch.allclose(fast.next_hidden, observed.next_hidden, atol=1e-6, rtol=1e-6)
    assert torch.allclose(fast.loss, expected, atol=1e-6, rtol=1e-6)


def test_vectorized_compound_decoder_matches_optional_stop_semantics(tmp_path) -> None:
    from ptcg_rl.g1.semantic import semantic_snapshot
    from ptcg_rl.g2.projection import project_decision
    from ..g1_fixtures import raw_observation

    raw = raw_observation(
        options=[
            {"type": 0, "number": 1},
            {"type": 0, "number": 2},
            {"type": 0, "number": 3},
        ],
        min_count=0,
        max_count=2,
    )
    raw["select"].update({"type": 8, "context": 38, "minCount": 0, "maxCount": 2})
    observation, request = semantic_snapshot(raw, "optional-stop", 0, "c" * 64)
    assert request is not None and not request.has_only_one_outcome
    projected = project_decision(observation, request)
    chosen = 1
    action = SemanticReplayActionV1(
        schema_version=1,
        submitted_original_indices=(chosen,),
        chosen_semantic_fingerprints=(request.options[chosen].semantic_fingerprint,),
        decoder_trace=(
            f"OPTION:{request.options[chosen].semantic_fingerprint}",
            "STOP",
        ),
        stopped_early=True,
    )
    decision = SemanticReplayDecisionV1(
        schema_version=1,
        episode_id="optional-stop",
        internal_replay_id="optional-stop",
        agent_index=0,
        request_step_index=0,
        action_step_index=1,
        sequence_index=0,
        observation=observation,
        request=request,
        projected=projected,
        action=action,
        reward=0.0,
    )
    policy = model(tmp_path).eval()
    reference = recurrent_sequence_batch_loss(policy, ((decision,),), verify=True)
    fast = recurrent_sequence_batch_loss(policy, ((decision,),), verify=False)
    assert reference.policy_targets == fast.policy_targets == 1
    assert torch.allclose(fast.loss, reference.loss, atol=1e-6, rtol=1e-6)


def test_packed_recurrent_chunk_matches_unpacked_sequence_loss(tmp_path) -> None:
    torch.manual_seed(17)
    policy = model(tmp_path).eval()
    sequences = (
        (_decision(0, 1), _decision(1, 2), _decision(2, 3)),
        (_decision(0, 4), _decision(1, 0)),
    )
    reference = recurrent_sequence_batch_loss(policy, sequences, verify=False)
    packed = pack_recurrent_group(sequences, sequence_length=8)
    assert len(packed.chunks) == 1
    hidden = policy.initial_hidden(len(sequences), "cpu")
    observed = packed_recurrent_chunk_loss(
        policy,
        packed.chunks[0],
        hidden=hidden,
        non_blocking=False,
    )
    assert observed.policy_targets == reference.policy_targets
    assert observed.recurrent_decisions == reference.recurrent_decisions
    assert torch.allclose(observed.next_hidden, reference.next_hidden, atol=1e-6, rtol=1e-6)
    assert torch.allclose(observed.loss, reference.loss, atol=1e-6, rtol=1e-6)


def test_batched_recurrent_loss_can_advance_forced_only_sequence(tmp_path) -> None:
    from ptcg_rl.g1.semantic import semantic_snapshot
    from ptcg_rl.g2.projection import project_decision
    from ..g1_fixtures import raw_observation

    raw = raw_observation(options=[{"type": 0, "number": 1}], min_count=1, max_count=1)
    raw["select"].update({"type": 8, "context": 38, "minCount": 1, "maxCount": 1})
    observation, request = semantic_snapshot(raw, "forced", 0, "c" * 64)
    assert request is not None and request.has_only_one_outcome
    projected = project_decision(observation, request)
    action = SemanticReplayActionV1(
        schema_version=1,
        submitted_original_indices=(0,),
        chosen_semantic_fingerprints=(request.options[0].semantic_fingerprint,),
        decoder_trace=(f"OPTION:{request.options[0].semantic_fingerprint}",),
        stopped_early=False,
    )
    decision = SemanticReplayDecisionV1(
        schema_version=1,
        episode_id="forced",
        internal_replay_id="forced",
        agent_index=0,
        request_step_index=0,
        action_step_index=1,
        sequence_index=0,
        observation=observation,
        request=request,
        projected=projected,
        action=action,
        reward=0.0,
    )
    policy = model(tmp_path).eval()
    result = recurrent_sequence_batch_loss(
        policy, ((decision,),), verify=True, require_policy_target=False
    )
    assert result.loss is None
    assert result.policy_targets == 0
    assert result.recurrent_decisions == 1
