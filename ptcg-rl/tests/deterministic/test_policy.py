from __future__ import annotations

from ptcg_rl.deterministic.policy import DeterministicStrategicPolicy


def test_phase_b_policy_entry_point_is_a_policy_v1_compatible_object():
    policy = DeterministicStrategicPolicy()
    assert isinstance(policy.policy_id, str)
    assert policy.policy_id == "deterministic-strategic-mega-abomasnow-v1"
    assert isinstance(policy.deck, tuple)
    assert hasattr(policy, "reset") and hasattr(policy, "choose")


def test_diagnostics_entry_point_is_public_and_starts_empty():
    policy = DeterministicStrategicPolicy()
    assert policy.diagnostics.reset_count == 0
    policy.reset("episode", 1)
    assert policy.diagnostics.last_episode_uuid == "episode"
    assert policy.diagnostics.last_player_index == 1
