from __future__ import annotations

from ptcg_rl.decision_engine import DecisionEngineRuntime, SearchBudgetPolicy, SearchSuggestion


def _observation(*, turn: int = 2, action_count: int = 3, logs=None, options=3, overage=600.0):
    return {
        "remainingOverageTime": overage,
        "current": {
            "result": -1,
            "turn": turn,
            "turnActionCount": action_count,
            "yourIndex": 0,
            "players": [
                {"prize": [None, None, None], "handCount": 5, "deckCount": 30},
                {"prize": [None, None, None], "handCount": 5, "deckCount": 30},
            ],
        },
        "select": {"type": 0, "option": [{} for _ in range(options)], "minCount": 1, "maxCount": 1},
        "logs": [] if logs is None else logs,
    }


class _Solver:
    def __init__(self, action=(1,)):
        self.action = action
        self.calls = []

    def suggest(self, observation, memory, budget_seconds, fallback_action):
        self.calls.append((budget_seconds, tuple(fallback_action), memory.known_opponent_hand_ids()))
        return SearchSuggestion(self.action, value=1.0, nodes=42, elapsed_seconds=0.01)


def test_shadow_solver_never_changes_fallback_action():
    solver = _Solver((1,))
    runtime = DecisionEngineRuntime(lambda _: [0], shadow_solver=solver)

    action = runtime.act(_observation())

    assert action == [0]
    assert runtime.diagnostics.shadow_calls == 1
    assert runtime.diagnostics.shadow_suggestions == 1
    assert runtime.diagnostics.shadow_disagreements == 1
    assert runtime.diagnostics.last_suggestion is not None
    assert runtime.diagnostics.last_suggestion.action == (1,)


def test_memory_persists_public_revealed_opponent_hand_card_then_expires_on_play():
    solver = _Solver((0,))
    runtime = DecisionEngineRuntime(lambda _: [0], shadow_solver=solver)
    reveal = {"type": 6, "playerIndex": 1, "cardId": 743, "serial": 91, "fromArea": 1, "toArea": 2}
    runtime.act(_observation(logs=[reveal], action_count=4))
    assert runtime.known_opponent_hand_ids() == (743,)

    # Incremental logs disappear on later callbacks, but the public fact survives.
    runtime.act(_observation(logs=[], action_count=5))
    assert runtime.known_opponent_hand_ids() == (743,)

    played = {"type": 10, "playerIndex": 1, "cardId": 743, "serial": 91}
    runtime.act(_observation(logs=[played], action_count=6))
    assert runtime.known_opponent_hand_ids() == ()


def test_face_down_hand_movement_conservatively_drops_known_identity():
    runtime = DecisionEngineRuntime(lambda _: [0])
    runtime.act(
        _observation(
            logs=[{"type": 6, "playerIndex": 1, "cardId": 743, "serial": 91, "fromArea": 1, "toArea": 2}],
            action_count=4,
        )
    )
    assert runtime.known_opponent_hand_ids() == (743,)

    runtime.act(
        _observation(
            logs=[{"type": 7, "playerIndex": 1, "fromArea": 2, "toArea": 1}],
            action_count=5,
        )
    )
    assert runtime.known_opponent_hand_ids() == ()


def test_duplicate_log_batch_is_not_double_counted():
    runtime = DecisionEngineRuntime(lambda _: [0])
    log = {"type": 10, "playerIndex": 1, "cardId": 1182, "serial": 77}
    obs = _observation(logs=[log], action_count=7)
    runtime.act(obs)
    runtime.act(obs)
    assert runtime.memory.opponent_played_cards[1182] == 1
    assert runtime.memory.processed_log_events == 1


def test_new_battle_cursor_resets_memory():
    runtime = DecisionEngineRuntime(lambda _: [0])
    runtime.act(
        _observation(
            turn=4,
            logs=[{"type": 6, "playerIndex": 1, "cardId": 743, "serial": 91, "fromArea": 1, "toArea": 2}],
            action_count=9,
        )
    )
    assert runtime.known_opponent_hand_ids() == (743,)
    runtime.act(_observation(turn=0, action_count=0, logs=[]))
    assert runtime.known_opponent_hand_ids() == ()


def test_budget_is_selective_and_preserves_overage_reserve():
    policy = SearchBudgetPolicy(normal_seconds=0.25, important_seconds=1.0, critical_seconds=4.0)
    assert policy.budget(_observation(options=1)) == 0.0
    assert policy.budget(_observation(options=3, overage=600.0)) == 0.25
    assert policy.budget(_observation(options=10, overage=600.0)) == 1.0
    assert policy.budget(_observation(options=10, overage=120.4)) == 0.4000000000000057


def test_shadow_failure_is_fail_safe_and_keeps_fallback():
    class BrokenSolver:
        def suggest(self, observation, memory, budget_seconds, fallback_action):
            raise RuntimeError("shadow failure")

    runtime = DecisionEngineRuntime(lambda _: [2], shadow_solver=BrokenSolver())
    assert runtime.act(_observation()) == [2]
    assert runtime.diagnostics.shadow_failures == 1
