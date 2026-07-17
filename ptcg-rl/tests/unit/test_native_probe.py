from __future__ import annotations

import pytest

from ptcg_rl.native_probe import select_if_ongoing, should_select


pytestmark = pytest.mark.unit


def observation(result: int) -> dict[str, object]:
    return {
        "current": {"result": result},
        "select": {"minCount": 1, "maxCount": 1, "option": [{}]},
    }


def test_only_ongoing_sentinel_enters_selection() -> None:
    assert should_select(-1)
    assert all(not should_select(result) for result in (0, 1, 2))


def test_terminal_stale_selection_never_calls_engine() -> None:
    calls: list[list[int]] = []
    for result in (0, 1, 2):
        assert not select_if_ongoing(observation(result), calls.append)
    assert calls == []


def test_ongoing_selection_uses_legal_unique_indices() -> None:
    calls: list[list[int]] = []
    assert select_if_ongoing(observation(-1), calls.append)
    assert calls == [[0]]
