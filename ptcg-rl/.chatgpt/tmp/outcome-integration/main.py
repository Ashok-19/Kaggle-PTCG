"""Scratch candidate entrypoint; the qualified Grim archive is not modified."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _candidate_root() -> Path:
    candidates: list[Path] = []
    configured = os.environ.get("PTCG_OUTCOME_ASSET_ROOT")
    if configured:
        candidates.append(Path(configured))
    if "__file__" in globals():
        candidates.append(Path(__file__).resolve().parent)
    candidates.extend((Path("/kaggle_simulations/agent"), Path.cwd()))
    for candidate in candidates:
        root = candidate.resolve()
        if (root / "outcome_main_adapter.py").is_file():
            return root
    raise RuntimeError("outcome candidate root cannot be discovered")


_ROOT = _candidate_root()
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from outcome_main_adapter import OutcomeMainAdapter  # noqa: E402


_ADAPTER = OutcomeMainAdapter(_ROOT)


def agent(obs):
    return _ADAPTER.agent(obs)


def diagnostics():
    return _ADAPTER.diagnostics()

