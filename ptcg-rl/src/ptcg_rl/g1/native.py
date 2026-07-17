from __future__ import annotations

import csv
import importlib
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping, Sequence


class NativeEngineError(RuntimeError):
    pass


def load_deck(path: Path) -> list[int]:
    values: list[int] = []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.reader(handle):
            values.extend(int(value) for value in row if value.strip())
    if len(values) != 60:
        raise ValueError(f"deck must contain exactly 60 card IDs, found {len(values)}")
    return values


class NativeCABTTransport:
    """The only layer allowed to own official `cg` wrapper/native objects."""

    _active_battle = False

    def __init__(self, sample_submission_root: Path) -> None:
        root = sample_submission_root.resolve()
        if not (root / "cg" / "game.py").is_file():
            raise NativeEngineError(f"cg/game.py not found under {root}")
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        self._game: ModuleType = importlib.import_module("cg.game")
        self._started = False

    def start(self, deck0: Sequence[int], deck1: Sequence[int]) -> Mapping[str, Any]:
        if self._started or NativeCABTTransport._active_battle:
            raise NativeEngineError("CABT supports exactly one active battle per process")
        observation, start_data = self._game.battle_start(list(deck0), list(deck1))
        if observation is None:
            raise NativeEngineError(
                f"BattleStart failed: error_player={start_data.errorPlayer} "
                f"error_type={start_data.errorType}"
            )
        self._started = True
        NativeCABTTransport._active_battle = True
        return observation

    def select(self, original_indices: Sequence[int]) -> Mapping[str, Any]:
        if not self._started:
            raise NativeEngineError("cannot select without an active battle")
        return self._game.battle_select(list(original_indices))

    def finish(self) -> None:
        if self._started:
            try:
                self._game.battle_finish()
            finally:
                self._started = False
                NativeCABTTransport._active_battle = False

