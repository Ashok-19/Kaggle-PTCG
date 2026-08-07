from __future__ import annotations

import math

import pytest

from ptcg_rl.deterministic.harness import (
    aggregate_candidate_records,
    bootstrap_score_delta,
    candidate_outcome,
    candidate_score,
    latency_summary,
    natural_seat_balance,
    wilson_interval,
)


def _record(
    *,
    game_id: str,
    candidate_player: int,
    terminal_result: int | None,
    status: str = "pass",
    invalid: int = 0,
    fallback: int = 0,
    post_terminal: int = 0,
    failure_kind: str | None = None,
    latencies: tuple[float, ...] = (1.0, 2.0, 3.0),
) -> dict:
    return {
        "game_id": game_id,
        "policy0": "candidate" if candidate_player == 0 else "anchor",
        "policy1": "anchor" if candidate_player == 0 else "candidate",
        "candidate_player": candidate_player,
        "status": status,
        "summary": {
            "terminal_result": terminal_result,
            "invalid_selections": invalid,
            "fallback_actions": fallback,
            "post_terminal_actions": post_terminal,
            "failure_kind": failure_kind,
        },
        "action_latencies_ms": latencies,
    }


@pytest.mark.parametrize(
    ("terminal_result", "candidate_player", "expected"),
    [(0, 0, "win"), (1, 0, "loss"), (2, 0, "draw"), (0, 1, "loss"), (1, 1, "win")],
)
def test_candidate_outcome_inverts_player_one(
    terminal_result: int, candidate_player: int, expected: str
) -> None:
    assert candidate_outcome(terminal_result, candidate_player) == expected
    assert candidate_score(terminal_result, candidate_player) == {
        "win": 1.0,
        "draw": 0.5,
        "loss": 0.0,
    }[expected]


def test_incomplete_game_is_not_scored() -> None:
    assert candidate_outcome(None, 0) == "incomplete"
    assert candidate_score(None, 0) is None


def test_wilson_is_deterministic_and_bounded() -> None:
    lower, upper = wilson_interval(5, 8)
    assert 0.0 <= lower < 5 / 8 < upper <= 1.0
    assert wilson_interval(0, 0) == (0.0, 1.0)
    assert wilson_interval(8, 8) == pytest.approx((0.675592, 1.0), abs=1e-5)


def test_bootstrap_delta_uses_exact_resample_count_and_seed() -> None:
    result = bootstrap_score_delta(
        [1.0, 0.5, 0.0], [0.0, 0.0, 0.5], resamples=10_000, seed=17
    )
    assert result["resamples"] == 10_000
    assert result == bootstrap_score_delta(
        [1.0, 0.5, 0.0], [0.0, 0.0, 0.5], resamples=10_000, seed=17
    )
    assert result["observed_delta"] == pytest.approx(1 / 3)
    assert result["percentile_2_5"] <= result["observed_delta"] <= result["percentile_97_5"]


def test_aggregate_inverts_result_and_sums_reliability() -> None:
    records = [
        _record(game_id="a", candidate_player=0, terminal_result=0),
        _record(game_id="b", candidate_player=1, terminal_result=0),
        _record(game_id="c", candidate_player=0, terminal_result=2),
        _record(
            game_id="d",
            candidate_player=1,
            terminal_result=None,
            status="fail",
            invalid=1,
            fallback=2,
            failure_kind="timeout",
        ),
    ]
    result = aggregate_candidate_records(records, control_scores=[0.0, 1.0, 0.5])
    assert result["games_requested"] == 4
    assert result["games_completed"] == 3
    assert result["candidate_wins"] == 1
    assert result["candidate_draws"] == 1
    assert result["candidate_losses"] == 1
    assert result["candidate_score"] == pytest.approx(0.5)
    assert result["reliability"]["invalid_selections"] == 1
    assert result["reliability"]["fallback_actions"] == 2
    assert result["reliability"]["incomplete_games"] == 1
    assert result["reliability"]["timeouts"] == 1
    assert result["promotable_reliability"] is False


def test_seat_balance_and_latency_summary() -> None:
    records = [
        _record(game_id="a", candidate_player=0, terminal_result=0, latencies=(1.0, 10.0)),
        _record(game_id="b", candidate_player=1, terminal_result=1, latencies=(2.0, 20.0)),
    ]
    assert natural_seat_balance(records) == {"candidate_player_0": 1, "candidate_player_1": 1}
    summary = latency_summary(records)
    assert summary["count"] == 4
    assert summary["p50_ms"] == 2.0
    assert summary["p95_ms"] == 20.0
    assert summary["p99_ms"] == 20.0
    assert math.isclose(summary["max_ms"], 20.0)
