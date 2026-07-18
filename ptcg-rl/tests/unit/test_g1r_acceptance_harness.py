from __future__ import annotations

import math

from ptcg_rl.g1.acceptance import _case
from ptcg_rl.g1.actions import validate_compound_action
from ptcg_rl.g1.engine_compare import _ks
from ptcg_rl.g1.soak import _completed_session_seconds, _slope_ci


def test_generated_acceptance_corpus_covers_stop_permutation_and_select_all() -> None:
    optional_request, optional = _case(9, 1, 1)
    assert optional.steps[-1].chosen_token == "STOP"
    assert optional.submitted_original_indices == ()
    validate_compound_action(optional_request, optional)

    permuted_request, permuted = _case(1, 3, 3)
    assert permuted.submitted_original_indices == (2, 0)
    validate_compound_action(permuted_request, permuted)

    select_all_request, select_all = _case(5, 15, 4)
    assert select_all.submitted_original_indices == (0, 1, 2)
    validate_compound_action(select_all_request, select_all)


def test_distribution_comparison_ks() -> None:
    assert _ks([1, 2, 3], [1, 2, 3]) == 0
    assert _ks([1, 1], [2, 2]) == 1


def test_theil_sen_bootstrap_reports_known_linear_slope() -> None:
    points = [(0.0, 10 * 1024 * 1024), (1800.0, 11 * 1024 * 1024),
              (3600.0, 12 * 1024 * 1024), (5400.0, 13 * 1024 * 1024)]
    result = _slope_ci(points, samples=100)
    assert result is not None
    assert math.isclose(result["estimate_mib_per_hour"], 2.0)
    assert result["lower_95_mib_per_hour"] == 2.0
    assert result["upper_95_mib_per_hour"] == 2.0


def test_resumed_soak_counts_active_sessions_without_offline_gap() -> None:
    samples = {
        "first:101": [(100.0, 1), (160.0, 1)],
        "first:102": [(100.0, 1), (160.0, 1)],
        "second:201": [(10_000.0, 1), (10_120.0, 1)],
    }
    assert _completed_session_seconds(samples) == 180.0
