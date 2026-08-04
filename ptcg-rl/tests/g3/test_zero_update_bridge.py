from __future__ import annotations

import math

import pytest
import torch

from ptcg_rl.g3.ppo import CompoundActionV1, replay_compound_action
from ptcg_rl.g3.zero_update_bridge import (
    BridgeContractError,
    TruncationClassV1,
    ZeroUpdateBridgeV1,
)


def decoder_logits(prefix, options, available, stop_available):
    option_logits = options @ prefix
    option_logits = option_logits.masked_fill(~available, float("-inf"))
    stop = prefix.sum().reshape(1)
    if not stop_available:
        stop = stop.fill_(float("-inf"))
    return torch.cat((option_logits, stop))


def decoder_advance(prefix, chosen):
    return torch.tanh(prefix + chosen)


def tensors(option_count=2):
    prefix = torch.tensor([0.2, -0.1])
    options = torch.tensor([[0.5, 0.1], [-0.3, 0.7]])[:option_count]
    available = torch.ones(option_count, dtype=torch.bool)
    return prefix, options, available


def old_logp(selected=(0,), stopped=True, minimum=1, maximum=1, option_count=2):
    prefix, options, available = tensors(option_count)
    replay = replay_compound_action(
        initial_prefix=prefix,
        option_embeddings=options,
        available_mask=available,
        action=CompoundActionV1(tuple(selected), stopped),
        minimum_count=minimum,
        maximum_count=maximum,
        decoder_logits=decoder_logits,
        decoder_advance=decoder_advance,
    )
    return float(replay.log_probability)


def record(
    bridge,
    *,
    episode="episode",
    player=0,
    seq=0,
    request="request-0",
    selected=(0,),
    stopped=True,
    minimum=1,
    maximum=1,
    option_count=2,
    before=(0.0, 0.0),
    after=(0.1, 0.2),
    logp=None,
    version=0,
    fallback=False,
):
    prefix, options, available = tensors(option_count)
    return bridge.record_decision(
        episode_id=episode,
        player=player,
        engine_request_seq=seq,
        request_id=request,
        selected_indices=selected,
        stopped=stopped,
        initial_prefix=prefix,
        option_embeddings=options,
        available_mask=available,
        minimum_count=minimum,
        maximum_count=maximum,
        old_log_probability=(
            old_logp(selected, stopped, minimum, maximum, option_count)
            if logp is None
            else logp
        ),
        hidden_before=before,
        hidden_after=after,
        reported_policy_version=version,
        decoder_logits=decoder_logits,
        decoder_advance=decoder_advance,
        fallback_used=fallback,
    )


def test_exact_replay_recurrence_forced_nodes_and_both_player_terminal_boundary() -> None:
    bridge = ZeroUpdateBridgeV1(policy_id="policy")
    bridge.start_episode("episode")
    first = record(
        bridge,
        player=0,
        seq=0,
        request="r0",
        option_count=1,
        before=(0.0, 0.0),
        after=(0.1, 0.2),
    )
    assert first.forced is True
    second = record(
        bridge,
        player=0,
        seq=1,
        request="r1",
        before=(0.1, 0.2),
        after=(0.2, 0.3),
    )
    assert second.forced is False
    record(
        bridge,
        player=1,
        seq=2,
        request="r2",
        before=(0.0, 0.0),
        after=(0.3, 0.4),
    )
    assert bridge.close_terminal_episode("episode", 1) == (1, -1)
    summary = bridge.qualification_summary(minimum_games=1, minimum_meaningful_decisions=2)
    assert summary["status"] == "PASS"
    assert summary["optimizer_steps"] == 0
    assert summary["forced_decisions"] == 1
    assert summary["meaningful_decisions"] == 2
    assert summary["terminal_boundaries_for_both_players"] == 1
    assert summary["maximum_compound_log_probability_absolute_error"] <= 1e-5


def test_partial_multiselect_stop_replays_exactly() -> None:
    bridge = ZeroUpdateBridgeV1(policy_id="policy")
    bridge.start_episode("episode")
    trace = record(
        bridge,
        selected=(1,),
        stopped=True,
        minimum=1,
        maximum=2,
        option_count=2,
    )
    assert trace.selected_indices == (1,)
    assert trace.stopped is True
    assert math.isfinite(trace.replayed_log_probability)


@pytest.mark.parametrize(
    "mutation,message,counter",
    [
        ({"seq": 1}, "out-of-order", "out_of_order_requests"),
        ({"selected": (0, 0), "logp": 0.0}, "duplicate action", "invalid_actions"),
        ({"version": 1}, "policy version", "policy_lag"),
        ({"fallback": True}, "fallback", "fallback_actions"),
        ({"logp": 0.0}, "log-probabilities", "replay_mismatches"),
        ({"after": (float("nan"), 0.0)}, "NaN", "nonfinite_values"),
    ],
)
def test_bridge_rejects_negative_controls(mutation, message, counter) -> None:
    bridge = ZeroUpdateBridgeV1(policy_id="policy")
    bridge.start_episode("episode")
    with pytest.raises(BridgeContractError, match=message):
        record(bridge, **mutation)
    assert bridge.reliability[counter] == 1


def test_duplicate_stale_and_recurrent_owner_controls_are_classified() -> None:
    duplicate = ZeroUpdateBridgeV1(policy_id="policy")
    duplicate.start_episode("episode")
    record(duplicate)
    with pytest.raises(BridgeContractError, match="duplicate request"):
        record(
            duplicate,
            seq=1,
            request="request-0",
            before=(0.1, 0.2),
            after=(0.2, 0.3),
        )
    assert duplicate.reliability["duplicate_requests"] == 1

    stale = ZeroUpdateBridgeV1(policy_id="policy")
    stale.start_episode("episode")
    record(stale)
    with pytest.raises(BridgeContractError, match="stale"):
        record(
            stale,
            seq=0,
            request="request-1",
            before=(0.1, 0.2),
            after=(0.2, 0.3),
        )
    assert stale.reliability["stale_requests"] == 1

    recurrent = ZeroUpdateBridgeV1(policy_id="policy")
    recurrent.start_episode("episode")
    record(recurrent)
    with pytest.raises(BridgeContractError, match="continuity"):
        record(
            recurrent,
            seq=1,
            request="request-1",
            before=(9.0, 9.0),
            after=(0.2, 0.3),
        )
    assert recurrent.reliability["recurrent_owner_failures"] == 1


def test_worker_death_is_explicit_truncation_and_never_silently_qualifies() -> None:
    bridge = ZeroUpdateBridgeV1(policy_id="policy")
    bridge.start_episode("episode")
    record(bridge, player=0, seq=0, request="r0")
    record(bridge, player=1, seq=1, request="r1")
    bridge.close_truncated_episode("episode", TruncationClassV1.WORKER_DEATH)
    state = bridge.state_dict()["episodes"]["episode"]
    assert state["boundary"] == "TRUNCATION"
    assert state["truncation_class"] == "WORKER_DEATH"
    assert bridge.reliability["worker_deaths"] == 1
    with pytest.raises(BridgeContractError, match="reliability counters"):
        bridge.qualification_summary(minimum_games=1, minimum_meaningful_decisions=1)


def test_checkpoint_resume_parity_and_continuation() -> None:
    first = ZeroUpdateBridgeV1(policy_id="policy")
    first.start_episode("episode")
    record(first, player=0, seq=0, request="r0")
    restored = ZeroUpdateBridgeV1.from_state_dict(first.state_dict())
    assert restored.state_sha256() == first.state_sha256()

    for bridge in (first, restored):
        record(bridge, player=1, seq=1, request="r1")
        bridge.close_terminal_episode("episode", 0)
    assert restored.state_dict() == first.state_dict()
    assert restored.state_sha256() == first.state_sha256()


def test_optimizer_step_attempt_is_impossible_and_classified() -> None:
    bridge = ZeroUpdateBridgeV1(policy_id="policy")
    with pytest.raises(BridgeContractError, match="cannot execute"):
        bridge.attempt_optimizer_step()
    assert bridge.optimizer_steps == 0
    assert bridge.reliability["optimizer_attempts"] == 1
