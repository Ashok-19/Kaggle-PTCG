from __future__ import annotations

import csv
import importlib
import platform
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
        existing = sys.modules.get("cg.game")
        if existing is not None and not Path(existing.__file__).resolve().is_relative_to(root):
            raise NativeEngineError("a different cg wrapper is already loaded in this process")
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        self._game: ModuleType = importlib.import_module("cg.game")
        if not Path(self._game.__file__).resolve().is_relative_to(root):
            raise NativeEngineError("loaded cg.game does not come from the requested engine root")
        sim = importlib.import_module("cg.sim")
        library_name = (
            "libcg-arm64.so" if platform.machine() in {"arm64", "aarch64"} else "libcg.so"
        )
        expected_library = (root / "cg" / library_name).resolve()
        loaded_library = Path(sim.lib._name).resolve()
        if loaded_library != expected_library:
            raise NativeEngineError("loaded native library differs from the requested engine root")
        self.root = root
        self.library_path = loaded_library
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
        if any(
            isinstance(index, bool) or not isinstance(index, int) or index < 0
            for index in original_indices
        ):
            raise NativeEngineError("native selection indices must be nonnegative integers")
        if len(original_indices) != len(set(original_indices)):
            raise NativeEngineError("native selection indices must be unique")
        return self._game.battle_select(list(original_indices))

    def finish(self) -> None:
        if self._started:
            try:
                self._game.battle_finish()
            finally:
                self._started = False
                NativeCABTTransport._active_battle = False
