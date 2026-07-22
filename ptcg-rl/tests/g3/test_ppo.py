from __future__ import annotations

import math

import pytest
import torch

from ptcg_rl.g2.network import PTCGPolicyV1, collate_projected

from ptcg_rl.g3.ppo import (
    CompoundActionV1,
    LocalExecutionLimitsV1,
    PPOContractError,
    RolloutEventV1,
    apply_local_execution_limits,
    compound_outcome_count,
    compute_gae,
    is_forced_compound_action,
    ppo_loss,
    replay_compound_action,
    require_finite_gradients,
    split_recurrent_rollout,
    validate_local_workload,
    verify_probability_replay,
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


def test_local_resource_guard_enforces_two_core_cpu_only_boundary() -> None:
    state = apply_local_execution_limits()
    assert state == {"torch_threads": 2, "torch_interop_threads": 1}
    validate_local_workload(non_forced_choices=4096, worker_processes=1, device="cpu")
    with pytest.raises(PPOContractError, match="choice budget"):
        validate_local_workload(non_forced_choices=4097, worker_processes=1, device="cpu")
    with pytest.raises(PPOContractError, match="worker process"):
        validate_local_workload(non_forced_choices=1, worker_processes=2, device="cpu")
    with pytest.raises(PPOContractError, match="CPU-only"):
        validate_local_workload(non_forced_choices=1, worker_processes=0, device="cuda")
    with pytest.raises(PPOContractError, match="thread ceiling"):
        LocalExecutionLimitsV1(max_cpu_threads=3)


def test_compound_outcome_count_classifies_forced_by_complete_ordered_lists() -> None:
    assert compound_outcome_count(0, 0, 0) == 1
    assert compound_outcome_count(1, 1, 1) == 1
    assert compound_outcome_count(1, 0, 1) == 2
    assert compound_outcome_count(2, 2, 2) == 2
    assert compound_outcome_count(3, 1, 2) == 9
    assert is_forced_compound_action(1, 1, 1) is True
    assert is_forced_compound_action(1, 0, 1) is False
    assert is_forced_compound_action(2, 2, 2) is False
    assert compound_outcome_count(100, 0, 100, cap=2) == 2
    assert compound_outcome_count(1, 2, 3) == 0


@pytest.mark.parametrize(
    "action,minimum,maximum",
    [
        (CompoundActionV1((0,), True), 1, 2),
        (CompoundActionV1((2, 0), True), 1, 2),
        (CompoundActionV1((), True), 0, 2),
        (CompoundActionV1((1, 0), False), 2, 2),
    ],
)
def test_compound_log_probability_replays_exactly_and_backpropagates(action, minimum, maximum) -> None:
    prefix = torch.tensor([0.2, -0.1, 0.3], requires_grad=True)
    options = torch.tensor(
        [[0.5, 0.1, -0.2], [-0.3, 0.7, 0.4], [0.2, -0.4, 0.8]],
        requires_grad=True,
    )
    replay = replay_compound_action(
        initial_prefix=prefix,
        option_embeddings=options,
        available_mask=torch.tensor([True, True, True]),
        action=action,
        minimum_count=minimum,
        maximum_count=maximum,
        decoder_logits=decoder_logits,
        decoder_advance=decoder_advance,
    )
    assert torch.isfinite(replay.log_probability)
    assert 0.0 <= float(replay.normalized_entropy.detach()) <= 1.0 + 1e-6
    replay.log_probability.backward()
    assert prefix.grad is not None and torch.isfinite(prefix.grad).all()
    assert options.grad is not None and torch.isfinite(options.grad).all()


def test_compound_replay_matches_manual_two_step_log_probability() -> None:
    prefix = torch.tensor([0.1, 0.2])
    options = torch.tensor([[0.4, -0.2], [0.3, 0.8]])
    replay = replay_compound_action(
        initial_prefix=prefix,
        option_embeddings=options,
        available_mask=torch.tensor([True, True]),
        action=CompoundActionV1((1,), True),
        minimum_count=1,
        maximum_count=2,
        decoder_logits=decoder_logits,
        decoder_advance=decoder_advance,
    )
    first = decoder_logits(prefix, options, torch.tensor([True, True]), False)
    first_logp = torch.log_softmax(first, dim=0)[1]
    advanced = decoder_advance(prefix, options[1])
    second = decoder_logits(advanced, options, torch.tensor([True, False]), True)
    second_logp = torch.log_softmax(second, dim=0)[2]
    assert torch.allclose(replay.log_probability, first_logp + second_logp)


def test_compound_action_rejects_duplicate_indices_at_construction() -> None:
    with pytest.raises(PPOContractError, match="unique"):
        CompoundActionV1((0, 0), True)


@pytest.mark.parametrize(
    "action,mask,minimum,maximum,message",
    [
        (CompoundActionV1((2,), True), [True, True], 1, 1, "out of range"),
        (CompoundActionV1((1,), True), [True, False], 1, 1, "unavailable"),
        (CompoundActionV1((), True), [True, True], 1, 1, "selection count"),
        (CompoundActionV1((), False), [True, True], 0, 1, "implicit completion"),
    ],
)
def test_compound_replay_fails_closed_on_invalid_actions(action, mask, minimum, maximum, message) -> None:
    prefix = torch.zeros(2)
    options = torch.eye(2)
    with pytest.raises(PPOContractError, match=message):
        replay_compound_action(
            initial_prefix=prefix,
            option_embeddings=options,
            available_mask=torch.tensor(mask),
            action=action,
            minimum_count=minimum,
            maximum_count=maximum,
            decoder_logits=decoder_logits,
            decoder_advance=decoder_advance,
        )


def test_compound_replay_matches_the_actual_g2_decoder(tmp_path) -> None:
    from tests.g2.test_card_table import build_fixture
    from tests.g2.test_network import number_decision

    model = PTCGPolicyV1(build_fixture(tmp_path / "cards.csv")).eval()
    decision = number_decision(3)[2]
    output = model(collate_projected((decision,)))
    prefix = model.decoder_initial(output.hidden[0])
    replay = replay_compound_action(
        initial_prefix=prefix,
        option_embeddings=output.option_embeddings,
        available_mask=torch.ones(3, dtype=torch.bool),
        action=CompoundActionV1((0,), True),
        minimum_count=1,
        maximum_count=1,
        decoder_logits=model.decoder_logits,
        decoder_advance=model.decoder_advance,
    )
    first_logits = model.decoder_logits(
        prefix,
        output.option_embeddings,
        torch.ones(3, dtype=torch.bool),
        False,
    )
    expected = torch.log_softmax(first_logits, dim=0)[0]
    assert torch.allclose(replay.log_probability, expected, atol=1e-7, rtol=0)
    replay.log_probability.backward()
    assert model.selection_gru.weight_hh.grad is not None


def test_probability_replay_checks_log_probabilities_and_initial_ratios() -> None:
    old = torch.tensor([-0.3, -1.2, -2.0])
    result = verify_probability_replay(old, old.clone())
    assert result.maximum_log_probability_absolute_error == 0.0
    assert result.maximum_ratio_absolute_error_from_one == 0.0
    assert result.checked_actions == 3
    with pytest.raises(PPOContractError, match="do not reproduce"):
        verify_probability_replay(old, old + 2e-5)
    with pytest.raises(PPOContractError, match="finite"):
        verify_probability_replay(old, torch.tensor([-0.3, float("nan"), -2.0]))


def test_gae_terminal_and_live_truncation_bootstrap_are_distinct() -> None:
    result = compute_gae(
        rewards=torch.tensor([0.0, 1.0, 0.0]),
        values=torch.tensor([0.2, 0.4, 0.3]),
        bootstrap_values=torch.tensor([0.4, 0.0, 0.8]),
        terminals=torch.tensor([False, True, False]),
        truncations=torch.tensor([False, False, True]),
        trace_continues=torch.tensor([True, False, False]),
        gamma=1.0,
        gae_lambda=1.0,
    )
    assert torch.allclose(result.advantages, torch.tensor([0.8, 0.6, 0.5]))
    assert torch.allclose(result.returns, torch.tensor([1.0, 1.0, 0.8]))


@pytest.mark.parametrize(
    "terminals,truncations,continues,bootstrap,message",
    [
        ([True], [True], [False], [0.0], "terminal and truncated"),
        ([True], [False], [True], [0.0], "cannot continue"),
        ([False], [False], [False], [0.0], "classified"),
        ([False], [True], [True], [1.0], "cannot continue"),
        ([True], [False], [False], [1.0], "bootstrap from zero"),
    ],
)
def test_gae_fails_closed_on_boundary_misclassification(
    terminals, truncations, continues, bootstrap, message
) -> None:
    with pytest.raises(PPOContractError, match=message):
        compute_gae(
            rewards=torch.tensor([0.0]),
            values=torch.tensor([0.0]),
            bootstrap_values=torch.tensor(bootstrap),
            terminals=torch.tensor(terminals),
            truncations=torch.tensor(truncations),
            trace_continues=torch.tensor(continues),
        )


def test_recurrent_slices_fold_forced_calls_and_never_cross_terminal_or_version() -> None:
    events = [
        RolloutEventV1("a", 0, "p", 1, 0, True, reset_before=True),
        RolloutEventV1("a", 0, "p", 1, 1, False),
        RolloutEventV1("a", 0, "p", 1, 2, True),
        RolloutEventV1("a", 0, "p", 1, 3, False, terminal=True),
        RolloutEventV1("b", 1, "p", 2, 0, False, reset_before=True, truncation=True),
    ]
    slices = split_recurrent_rollout(events, maximum_learner_steps=1)
    assert len(slices) == 3
    assert slices[0].learner_event_indices == (1,)
    assert [event.selection_seq for event in slices[0].events] == [0, 1]
    assert slices[1].continuation_from_prior_slice is True
    assert [event.selection_seq for event in slices[1].events] == [2, 3]
    assert slices[1].learner_event_indices == (1,)
    assert slices[2].events[0].policy_version == 2


@pytest.mark.parametrize(
    "events,message",
    [
        ([RolloutEventV1("a", 0, "p", 1, 0, False)], "requires an acknowledged reset"),
        (
            [
                RolloutEventV1("a", 0, "p", 1, 0, False, reset_before=True),
                RolloutEventV1("a", 0, "p", 1, 2, False),
            ],
            "out-of-order",
        ),
        (
            [
                RolloutEventV1("a", 0, "p", 1, 0, False, reset_before=True),
                RolloutEventV1("a", 0, "p", 2, 1, False),
            ],
            "requires an acknowledged reset",
        ),
    ],
)
def test_recurrent_slice_contract_fails_closed(events, message) -> None:
    with pytest.raises(PPOContractError, match=message):
        split_recurrent_rollout(events, maximum_learner_steps=4)


def test_ppo_loss_matches_clipped_policy_and_value_definitions_and_masks_forced_nodes() -> None:
    new_logp = torch.tensor([math.log(1.3), math.log(0.7), 10.0], requires_grad=True)
    old_logp = torch.tensor([0.0, 0.0, -10.0])
    advantages = torch.tensor([1.0, -1.0, 1000.0])
    new_values = torch.tensor([1.0, -1.0, 999.0], requires_grad=True)
    old_values = torch.tensor([0.0, 0.0, -999.0])
    returns = torch.tensor([0.5, -0.5, 999.0])
    entropy = torch.tensor([0.5, 0.5, 999.0])
    result = ppo_loss(
        new_log_probabilities=new_logp,
        old_log_probabilities=old_logp,
        advantages=advantages,
        new_values=new_values,
        old_values=old_values,
        returns=returns,
        normalized_entropies=entropy,
        policy_mask=torch.tensor([True, True, False]),
        normalize_advantages=False,
    )
    expected_policy = -torch.tensor([1.2, -0.8]).mean()
    expected_value = 0.5 * torch.tensor([0.25, 0.25]).mean()
    assert torch.allclose(result.policy, expected_policy)
    assert torch.allclose(result.value, expected_value)
    assert result.valid_actions == 2
    result.total.backward()
    assert new_logp.grad is not None and new_logp.grad[2] == 0
    assert new_values.grad is not None and new_values.grad[2] == 0


def test_ppo_loss_and_gradient_checks_fail_closed() -> None:
    base = torch.zeros(2)
    kwargs = dict(
        new_log_probabilities=base,
        old_log_probabilities=base,
        advantages=torch.ones(2),
        new_values=base,
        old_values=base,
        returns=base,
        normalized_entropies=base,
    )
    with pytest.raises(PPOContractError, match="no valid"):
        ppo_loss(**kwargs, policy_mask=torch.tensor([False, False]))
    with pytest.raises(PPOContractError, match="NaN"):
        ppo_loss(
            **{**kwargs, "new_log_probabilities": torch.tensor([0.0, float("nan")])},
            policy_mask=torch.tensor([True, True]),
        )
    parameter = torch.nn.Parameter(torch.tensor([1.0]))
    with pytest.raises(PPOContractError, match="no model gradients"):
        require_finite_gradients([parameter])
    parameter.grad = torch.tensor([float("inf")])
    with pytest.raises(PPOContractError, match="NaN or infinity"):
        require_finite_gradients([parameter])
    parameter.grad = torch.tensor([3.0])
    assert require_finite_gradients([parameter]) == 3.0
