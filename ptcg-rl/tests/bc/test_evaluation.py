from __future__ import annotations

from ptcg_rl.bc.evaluation import (
    GreedyRecurrentNeuralPolicyV1,
    candidate_score,
    normal_score_interval,
)
from ..g2.test_network import model, number_decision


def test_greedy_neural_policy_emits_legal_compound_action_and_recurrence(tmp_path) -> None:
    policy = model(tmp_path).eval()
    observation, request, _ = number_decision(4)
    neural = GreedyRecurrentNeuralPolicyV1(policy, player_index=0)
    neural.reset(request.episode_uuid, 0, "start")
    action = neural.choose(observation, request)
    assert len(action.submitted_original_indices) == 1
    assert action.submitted_original_indices[0] in tuple(
        option.original_index for option in request.options if option.available
    )
    assert neural._hidden is not None
    neural.reset(request.episode_uuid, 0, "terminal")
    assert neural._hidden is None


def test_candidate_score_and_interval() -> None:
    assert candidate_score(0, 0) == 1.0
    assert candidate_score(1, 0) == 0.0
    assert candidate_score(2, 0) == 0.5
    low, high = normal_score_interval([1.0, 1.0, 0.0, 1.0])
    assert 0.0 <= low <= 0.75 <= high <= 1.0
