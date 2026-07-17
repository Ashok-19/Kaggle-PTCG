from __future__ import annotations

import pytest

from ptcg_rl.doctor import unresolved_values


pytestmark = pytest.mark.unit


def test_unresolved_values_are_rejected_recursively() -> None:
    assert unresolved_values({"ok": 1, "nested": ["REQUIRED_LIMIT", {"x": "done"}]}) == ["REQUIRED_LIMIT"]

