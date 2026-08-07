from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from itertools import permutations
from types import SimpleNamespace
from uuid import uuid4

import pytest

from ptcg_rl.deterministic.harness import (
    aggregate_candidate_records,
    bootstrap_score_delta,
    candidate_outcome,
    candidate_score,
    latency_summary,
    natural_seat_balance,
    permutation_control,
    sanitized_report,
    verify_sealed_json,
    wilson_interval,
)
from scripts.deterministic.b0_control_qualification import (
    _candidate_latency_values,
    _fresh_session_deadline,
    _resolve_budget,
    _resolve_candidate_import,
    _parser,
    _should_stop_after_record,
    _validate_budget_scopes,
    _validate_scale_review_receipt,
    _validate_runtime_record,
    _validate_resume_budget,
    _worker_command,
    _worker_config_import,
)


@dataclass(frozen=True)
class _Option:
    original_index: int
    semantic: str


@dataclass(frozen=True)
class _Request:
    options: tuple[_Option, ...]
    episode_uuid: str = "fixture"
    acting_player: int = 0
    selection_seq: int = 0
    ordering: str = "ORDERED"


@dataclass(frozen=True)
class _Action:
    submitted_original_indices: tuple[int, ...]


class _SemanticPolicy:
    def reset(self, episode_uuid: str, player_index: int, reason: str = "start") -> None:
        return None

    def choose(self, observation: object, request: _Request) -> _Action:
        selected = tuple(option.original_index for option in request.options if option.semantic == "target")
        return _Action(selected)


def _true_permutations(count: int = 32) -> list[tuple[int, ...]]:
    return list(permutations(range(5)))[:count]


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
    candidate_latencies: tuple[float, ...] | None = None,
    anchor: str = "rule:anchor",
    missing_output: int = 0,
) -> dict:
    return {
        "game_id": game_id,
        "policy0": "candidate" if candidate_player == 0 else "anchor",
        "policy1": "anchor" if candidate_player == 0 else "candidate",
        "candidate_player": candidate_player,
        "evaluated_policy_player": candidate_player,
        "anchor": anchor,
        "status": status,
        "missing_output": missing_output,
        "summary": {
            "terminal_result": terminal_result,
            "engine_requests": len(latencies),
            "evaluated_policy_requests": len(
                candidate_latencies if candidate_latencies is not None else latencies
            ),
            "invalid_selections": invalid,
            "fallback_actions": fallback,
            "post_terminal_actions": post_terminal,
            "failure_kind": failure_kind,
        },
        "action_latencies_ms": latencies,
        "candidate_action_latencies_ms": candidate_latencies if candidate_latencies is not None else latencies,
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


@pytest.mark.parametrize("ordering", ["ORDERED", "UNORDERED"])
def test_permutation_control_runs_true_permutations_and_uses_ordering(ordering: str) -> None:
    request = _Request(
        tuple(_Option(index, "target" if index == 2 else str(index)) for index in range(5)),
        ordering=ordering,
    )
    result = permutation_control(_SemanticPolicy, object(), request, _true_permutations())
    assert result["permutations_requested"] == 32
    assert result["equivalent"] == 32
    assert result["pass"] is True
    assert result["equivalence"] == ("sequence" if ordering == "ORDERED" else "set")


def test_stop_predicate_is_causal_and_does_not_label_later_tasks() -> None:
    failed = _record(game_id="failed", candidate_player=0, terminal_result=None, status="fail")
    passed = _record(game_id="passed", candidate_player=0, terminal_result=0)
    assert _should_stop_after_record(failed, "stop_on_any_invalid_fallback_timeout_failure_or_incomplete_game")
    assert not _should_stop_after_record(passed, "stop_on_any_invalid_fallback_timeout_failure_or_incomplete_game")


def test_candidate_latency_attribution_fails_closed_on_cardinality_mismatch() -> None:
    transitions = (
        SimpleNamespace(request=SimpleNamespace(acting_player=0)),
        SimpleNamespace(request=None),
        SimpleNamespace(request=SimpleNamespace(acting_player=1)),
    )
    with pytest.raises(ValueError, match="latency/request cardinality"):
        _candidate_latency_values((2.0,), transitions, 0)


def test_resume_uses_a_fresh_session_wall_deadline() -> None:
    assert _fresh_session_deadline(180, now=100.0) == 280.0


def test_candidate_import_is_frozen_and_source_must_be_repo_local() -> None:
    repo = Path(__file__).resolve().parents[2]
    with pytest.raises(ValueError, match="differs from configured"):
        _resolve_candidate_import(
            "ptcg_rl.deterministic.control:MegaAbomasnowControl",
            repo,
            expected_import="ptcg_rl.deterministic.policy:DeterministicStrategicPolicy",
        )
    with pytest.raises(ValueError, match="outside|source"):
        _resolve_candidate_import("json:JSONDecoder", repo, expected_import="json:JSONDecoder")


def test_b0_budget_scope_is_explicit_and_arithmetic_is_checked() -> None:
    import json

    config = json.loads(
        (Path(__file__).resolve().parents[2] / "configs/deterministic/b0_ma_control_v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert config["candidate"]["import_spec"] == (
        "ptcg_rl.deterministic.policy:DeterministicStrategicPolicy"
    )
    _validate_budget_scopes(config, len(config["anchors"]))
    config["scale_budgets"]["local_screen"]["games_total_all_arms"] = 32
    with pytest.raises(ValueError, match="inconsistent arm totals"):
        _validate_budget_scopes(config, len(config["anchors"]))


def test_explicit_budget_selector_resolves_frozen_per_arm_and_all_arm_totals() -> None:
    import json

    config = json.loads(
        (Path(__file__).resolve().parents[2] / "configs/deterministic/b0_ma_control_v1.json").read_text(
            encoding="utf-8"
        )
    )
    mechanical = _resolve_budget(config, "mechanical_canary", len(config["anchors"]))
    screen = _resolve_budget(config, "local_screen", len(config["anchors"]))
    assert mechanical["budget_name"] == "mechanical_canary"
    assert mechanical["games_total_scope"] == "all_arms"
    assert mechanical["games_total_all_arms"] == 16
    assert screen["budget_name"] == "local_screen"
    assert screen["games_total_scope"] == "per_arm"
    assert screen["games_total_per_arm"] == 32
    assert screen["games_total_all_arms"] == 64
    assert screen["games_total"] == 32
    assert screen["request_cap"] == mechanical["request_cap"]
    expected = {
        "mechanical_canary": (16, "all_arms"),
        "local_screen": (64, "per_arm"),
        "local_upper_screen": (128, "per_arm"),
        "private_kaggle_arm": (256, "per_arm"),
        "confirmation": (1024, "per_arm"),
    }
    for name, (all_arms, scope) in expected.items():
        resolved = _resolve_budget(config, name, len(config["anchors"]))
        assert resolved["games_total_all_arms"] == all_arms
        assert resolved["games_total_scope"] == scope
    with pytest.raises(ValueError, match="unknown B0 budget"):
        _resolve_budget(config, "not_a_budget", len(config["anchors"]))


def test_budget_aliases_have_one_default_and_reject_conflicting_duplicates() -> None:
    assert _parser().parse_args([]).budget_name is None
    assert _parser().parse_args(["--budget", "local_screen"]).budget_name == "local_screen"
    assert _parser().parse_args(["--budget-name", "local_upper_screen"]).budget_name == "local_upper_screen"
    with pytest.raises(SystemExit):
        _parser().parse_args(["--budget", "local_screen", "--budget-name", "confirmation"])


def test_scale_budget_requires_a_budget_bound_independent_review_receipt() -> None:
    import json

    config = json.loads(
        (Path(__file__).resolve().parents[2] / "configs/deterministic/b0_ma_control_v1.json").read_text(
            encoding="utf-8"
        )
    )
    with pytest.raises(ValueError, match="requires --independent-review-receipt"):
        _validate_scale_review_receipt(
            config=config,
            budget_name="local_screen",
            budget_sha256="budget",
            config_sha256="config",
            candidate_source_digest="source",
            receipt_path=None,
            repo=Path(__file__).resolve().parents[2],
        )


def test_resume_rejects_a_different_selected_budget_or_budget_digest() -> None:
    import json

    config = json.loads(
        (Path(__file__).resolve().parents[2] / "configs/deterministic/b0_ma_control_v1.json").read_text(
            encoding="utf-8"
        )
    )
    selected = _resolve_budget(config, "local_screen", len(config["anchors"]))
    plan = {"budget_name": "mechanical_canary", "resolved_budget": selected, "budget_sha256": "x"}
    with pytest.raises(ValueError, match="budget name"):
        _validate_resume_budget(plan, selected, "different")
    matching = {"budget_name": "local_screen", "resolved_budget": selected, "budget_sha256": "x"}
    with pytest.raises(ValueError, match="budget digest"):
        _validate_resume_budget(matching, selected, "different")


def test_runtime_guard_rejects_nonfinite_latency_and_cardinality() -> None:
    record = _record(game_id="runtime", candidate_player=0, terminal_result=0, latencies=(1.0, 2.0))
    record["process_metrics"] = {"cpu_seconds": 1.0, "wall_seconds": 1.0, "peak_rss_bytes": 1.0}
    record["summary"]["engine_requests"] = 3
    with pytest.raises(ValueError, match="latency/request cardinality"):
        _validate_runtime_record(record, {
            "latency_ms": {"p50_max": 1000.0, "p95_max": 5000.0, "p99_max": 10000.0, "max_max": 60000.0},
            "cumulative_cpu_seconds_max": 600.0,
            "peak_rss_bytes_max": 8 * 1024**3,
        })
    record["summary"]["engine_requests"] = 2
    record["action_latencies_ms"] = (float("nan"), 2.0)
    with pytest.raises(ValueError, match="finite"):
        _validate_runtime_record(record, {
            "latency_ms": {"p50_max": 1000.0, "p95_max": 5000.0, "p99_max": 10000.0, "max_max": 60000.0},
            "cumulative_cpu_seconds_max": 600.0,
            "peak_rss_bytes_max": 8 * 1024**3,
        })
    record["action_latencies_ms"] = [1.0, 70_000.0]
    with pytest.raises(ValueError, match="latency exceeds"):
        _validate_runtime_record(record, {
            "latency_ms": {"p50_max": 1000.0, "p95_max": 5000.0, "p99_max": 10000.0, "max_max": 60000.0},
            "cumulative_cpu_seconds_max": 600.0,
            "peak_rss_bytes_max": 8 * 1024**3,
        })
    record["action_latencies_ms"] = [1.0, 2.0]
    record["process_metrics"]["cpu_seconds"] = 600.1
    with pytest.raises(ValueError, match="cumulative CPU"):
        _validate_runtime_record(record, {
            "latency_ms": {"p50_max": 1000.0, "p95_max": 5000.0, "p99_max": 10000.0, "max_max": 60000.0},
            "cumulative_cpu_seconds_max": 600.0,
            "peak_rss_bytes_max": 8 * 1024**3,
        })


def test_worker_command_propagates_and_enforces_repo_local_config() -> None:
    repo = Path(__file__).resolve().parents[2]
    alternate_config = repo / "configs/deterministic/phase_a_native_semantics_v1.json"
    command = _worker_command(
        script_path=repo / "scripts/deterministic/b0_control_qualification.py",
        repo=repo,
        config_path=alternate_config,
        engine_root=repo / "private/engine",
        card_data=repo / "private/assets/official/EN_Card_Data.csv",
        card_table=repo / "private/g2/card-table-v1.json",
        default_deck=repo / "private/baselines/mega-abomasnow-ex/deck.csv",
        private_baselines=repo / "private/baselines",
        candidate_import="ptcg_rl.deterministic.policy:DeterministicStrategicPolicy",
        candidate_policy_id="deterministic-strategic-mega-abomasnow-v1",
        game_id="fixture",
        anchor="rule:dragapult-ex",
        arm="candidate",
        player=0,
        policy0="candidate",
        policy1="rule:dragapult-ex",
        request_cap=20_000,
        game_timeout=180,
        permutation_count=32,
    )
    assert command[command.index("--config") + 1] == str(alternate_config)
    with pytest.raises(ValueError, match="candidate.import_spec"):
        _worker_config_import(alternate_config, repo)


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


def test_aggregate_reports_matchup_seat_cells_and_candidate_latency() -> None:
    records = [
        _record(game_id="a", candidate_player=0, terminal_result=0, anchor="rule:x", candidate_latencies=(1.0,)),
        _record(game_id="b", candidate_player=1, terminal_result=1, anchor="rule:x", candidate_latencies=(4.0,)),
    ]
    result = aggregate_candidate_records(records)
    assert result["cells"]["rule:x"]["candidate_player_0"]["wins"] == 1
    assert result["cells"]["rule:x"]["candidate_player_1"]["wins"] == 1
    assert result["candidate_latency"]["count"] == 2
    assert result["candidate_latency"]["p99_ms"] == 4.0


def test_complete_game_with_reliability_error_is_not_promotable() -> None:
    result = aggregate_candidate_records(
        [_record(game_id="bad", candidate_player=0, terminal_result=0, invalid=1)]
    )
    assert result["games_completed"] == 1
    assert result["promotable_reliability"] is False
    assert result["reliability"]["invalid_selections"] == 1


def test_missing_worker_output_is_counted_as_reliability_failure() -> None:
    result = aggregate_candidate_records(
        [_record(game_id="missing", candidate_player=0, terminal_result=None, missing_output=1)]
    )
    assert result["reliability"]["missing_outputs"] == 1
    assert result["reliability"]["failures"] == 1
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


def test_sanitized_report_requires_reliable_complete_aggregate() -> None:
    aggregate = aggregate_candidate_records(
        [_record(game_id="bad", candidate_player=0, terminal_result=0, fallback=1)]
    )
    report = sanitized_report(
        run_id="run",
        config={"experiment_id": "B0-MA-CONTROL-001"},
        aggregate=aggregate,
        repository={"commit": "abc"},
        platform={"python": "3.11"},
        source_sha256="src",
        loaded_artifacts={},
        permutation={"pass": True},
        command=["python", "script.py"],
    )
    assert report["status"] == "FAILED"


def test_sealed_json_detects_tamper_and_requires_digest() -> None:
    path = Path("runs") / f"test-b0-sealed-{uuid4().hex}" / "evidence.json"
    from ptcg_rl.deterministic.harness import write_sealed_json

    write_sealed_json(path, {"x": 1})
    assert verify_sealed_json(path) is True
    path.chmod(0o600)
    path.write_text('{"x": 2}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="digest"):
        verify_sealed_json(path)
