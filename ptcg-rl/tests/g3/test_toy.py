from __future__ import annotations

import pytest
import torch

from ptcg_rl.g3.ppo import PPOContractError, verify_probability_replay
from ptcg_rl.g3.toy import (
    ToyCaseV1,
    ToyPolicyConfigV1,
    ToyRecurrentPolicyV1,
    ToyTaskV1,
    ToyTrainingConfigV1,
    choose_toy_action,
    collect_toy_episodes,
    evaluate_toy_policy,
    masked_bandit_task_v1,
    recurrent_cue_task_v1,
    recurrent_margin,
    replay_toy_episode,
    toy_result_record,
    toy_task_registry_v1,
    train_toy_policy,
    variable_option_multiselect_task_v1,
)


def test_versioned_toy_registry_is_complete_unique_and_hash_stable() -> None:
    first = toy_task_registry_v1()
    second = toy_task_registry_v1()
    assert set(first) == {
        "masked-bandit-v1",
        "recurrent-cue-v1",
        "variable-option-multiselect-v1",
    }
    assert {key: value.task_sha256 for key, value in first.items()} == {
        key: value.task_sha256 for key, value in second.items()
    }
    assert all(len(task.task_sha256) == 64 for task in first.values())
    assert len({task.task_sha256 for task in first.values()}) == 3


def test_recurrent_cue_decision_is_identical_without_memory_and_cue_is_balanced() -> None:
    task = recurrent_cue_task_v1()
    zero, one = task.cases
    assert zero.observations[-1] == one.observations[-1]
    assert zero.observations[0] != one.observations[0]
    assert zero.target_indices == (0,)
    assert one.target_indices == (1,)
    torch.manual_seed(5)
    model = ToyRecurrentPolicyV1().eval()
    zero_stateless = model.encode_case(zero, stateless=True)
    one_stateless = model.encode_case(one, stateless=True)
    assert torch.equal(zero_stateless.public_hidden, one_stateless.public_hidden)
    assert torch.equal(zero_stateless.prefix_hidden, one_stateless.prefix_hidden)
    zero_recurrent = model.encode_case(zero, stateless=False)
    one_recurrent = model.encode_case(one, stateless=False)
    assert not torch.equal(zero_recurrent.public_hidden, one_recurrent.public_hidden)


def test_variable_option_task_covers_stop_order_uniqueness_and_variable_bounds() -> None:
    task = variable_option_multiselect_task_v1()
    assert {len(case.option_features) for case in task.cases} == {2, 3}
    assert {case.minimum_count for case in task.cases} == {0, 1, 2}
    assert {case.maximum_count for case in task.cases} == {1, 2}
    assert any(case.target_indices == () for case in task.cases)
    assert any(len(case.target_indices) > 1 for case in task.cases)
    assert any(case.target_indices == (2, 0) for case in task.cases)
    assert all(len(set(case.target_indices)) == len(case.target_indices) for case in task.cases)


@pytest.mark.parametrize(
    "task_factory",
    [masked_bandit_task_v1, recurrent_cue_task_v1, variable_option_multiselect_task_v1],
)
def test_sampled_and_greedy_actions_are_legal_unique_and_exactly_replayable(task_factory) -> None:
    task = task_factory()
    torch.manual_seed(9)
    model = ToyRecurrentPolicyV1().eval()
    generator = torch.Generator().manual_seed(17)
    episodes = collect_toy_episodes(
        model,
        task,
        count=32,
        start_case_index=0,
        generator=generator,
        stateless=False,
    )
    old = torch.tensor([episode.old_log_probability for episode in episodes])
    with torch.no_grad():
        replayed = torch.stack([replay_toy_episode(model, task, episode)[0] for episode in episodes])
    check = verify_probability_replay(old, replayed)
    assert check.maximum_log_probability_absolute_error <= 1e-5
    for episode in episodes:
        case = task.case(episode.case_id)
        assert len(set(episode.action.selected_indices)) == len(episode.action.selected_indices)
        assert case.minimum_count <= len(episode.action.selected_indices) <= case.maximum_count
        assert all(case.available_mask[index] for index in episode.action.selected_indices)
    evaluation = evaluate_toy_policy(model, task)
    assert evaluation["total_cases"] == len(task.cases)
    assert 0.0 <= evaluation["score"] <= 1.0


def test_toy_policy_gradients_reach_observation_memory_options_decoder_stop_and_value() -> None:
    task = variable_option_multiselect_task_v1()
    model = ToyRecurrentPolicyV1().train()
    case = task.cases[2]
    action, replay, value = choose_toy_action(
        model,
        case,
        stateless=False,
        generator=torch.Generator().manual_seed(3),
    )
    loss = -replay.log_probability + value.square() + model.encode_case(case).public_hidden.square().mean()
    loss.backward()
    gradients = {
        name: parameter.grad
        for name, parameter in model.named_parameters()
        if parameter.grad is not None
    }
    required = {
        "observation_projection.0.weight",
        "public_gru.weight_hh",
        "option_projection.0.weight",
        "decoder_initial_projection.weight",
        "decoder_gru.weight_hh",
        "stop_embedding",
        "value_head.0.weight",
    }
    assert required <= gradients.keys()
    assert all(torch.isfinite(gradients[name]).all() for name in required)
    assert action.stopped is True


def test_stateless_cue_policy_can_score_only_one_of_two_balanced_cases() -> None:
    task = recurrent_cue_task_v1()
    for seed in range(10):
        torch.manual_seed(seed)
        score = evaluate_toy_policy(ToyRecurrentPolicyV1(), task, stateless=True)["score"]
        assert score == 0.5


def test_toy_case_and_task_contracts_fail_closed() -> None:
    with pytest.raises(PPOContractError, match="fixed-width"):
        ToyCaseV1("bad", ((0.0,),), (), (), 0, 0, ())
    with pytest.raises(PPOContractError, match="equal length"):
        ToyCaseV1("bad", ((0.0,) * 8,), ((0.0,) * 8,), (), 0, 1, ())
    with pytest.raises(PPOContractError, match="target selects"):
        ToyCaseV1(
            "bad",
            ((0.0,) * 8,),
            ((0.0,) * 8, (0.0,) * 8),
            (False, True),
            0,
            1,
            (0,),
        )
    case = ToyCaseV1("a", ((0.0,) * 8,), (), (), 0, 0, ())
    with pytest.raises(PPOContractError, match="unique"):
        ToyTaskV1(1, "x", "x", (case, case), False)
    with pytest.raises(PPOContractError, match="schema"):
        ToyTaskV1(2, "x", "x", (case,), False)
    with pytest.raises(PPOContractError, match="observation width"):
        ToyPolicyConfigV1(observation_width=7)


def test_toy_training_config_rejects_unbounded_or_incoherent_values() -> None:
    with pytest.raises(PPOContractError, match="divisible"):
        ToyTrainingConfigV1(total_non_forced_choices=100, choices_per_update=64)
    with pytest.raises(PPOContractError, match="positive"):
        ToyTrainingConfigV1(ppo_epochs=0)
    with pytest.raises(PPOContractError, match="nonnegative"):
        ToyTrainingConfigV1(learning_rate=-1.0)


def test_recurrent_margin_requires_matching_roles_tasks_and_seeds() -> None:
    config = ToyTrainingConfigV1(total_non_forced_choices=64, choices_per_update=64, ppo_epochs=1)
    task = recurrent_cue_task_v1()
    _, _, _, recurrent = train_toy_policy(task, seed=101, config=config, stateless=False)
    _, _, _, stateless = train_toy_policy(task, seed=101, config=config, stateless=True)
    assert recurrent_margin(recurrent, stateless) == recurrent.final_score - stateless.final_score
    record = toy_result_record(recurrent)
    assert record["zero_tolerance_total"] == 0
    with pytest.raises(PPOContractError, match="same seed"):
        recurrent_margin(recurrent, stateless.__class__(**{**stateless.__dict__, "seed": 102}))
    with pytest.raises(PPOContractError, match="roles are reversed"):
        recurrent_margin(stateless, recurrent)
