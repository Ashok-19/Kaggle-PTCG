from __future__ import annotations

import pytest

from ptcg_rl.audit import restricted_paths


pytestmark = pytest.mark.unit


def test_private_patterns_match_paths_and_basenames() -> None:
    paths = ["src/main.py", "private/assets/libcg.so", "notes/agent.ipynb", "config/.env"]
    patterns = ["private/**", "libcg*", "*.ipynb", "**/.env"]
    assert restricted_paths(paths, patterns) == [
        "config/.env",
        "notes/agent.ipynb",
        "private/assets/libcg.so",
    ]

