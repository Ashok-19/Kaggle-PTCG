from __future__ import annotations

import ctypes
import csv
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

ONGOING_RESULT = -1
TERMINAL_RESULTS = {0, 1, 2}


class StartData(ctypes.Structure):
    _fields_ = [
        ("battlePtr", ctypes.c_void_p),
        ("errorPlayer", ctypes.c_int),
        ("errorType", ctypes.c_int),
    ]


class SerialData(ctypes.Structure):
    _fields_ = [
        ("json", ctypes.c_char_p),
        ("data", ctypes.POINTER(ctypes.c_ubyte)),
        ("count", ctypes.c_int),
        ("selectPlayer", ctypes.c_int),
    ]


def should_select(result: int) -> bool:
    return result == ONGOING_RESULT


def select_if_ongoing(observation: dict[str, Any], select: Callable[[list[int]], None]) -> bool:
    result = (observation.get("current") or {}).get("result")
    if not should_select(result):
        if result not in TERMINAL_RESULTS:
            raise RuntimeError(f"unexpected battle result {result!r}")
        return False

    selection = observation.get("select")
    if not selection:
        raise RuntimeError("ongoing battle has no selection request")
    minimum = int(selection.get("minCount", 0))
    maximum = int(selection.get("maxCount", 0))
    option_count = len(selection.get("option") or [])
    if not 0 <= minimum <= maximum <= option_count:
        raise RuntimeError(
            f"invalid selection bounds min={minimum} max={maximum} options={option_count}"
        )
    select(list(range(maximum)))
    return True


def probe(library: Path, deck_file: Path, max_selections: int = 20_000) -> dict[str, object]:
    deck = [int(row[0]) for row in csv.reader(deck_file.open(encoding="utf-8")) if row]
    if len(deck) != 60:
        raise ValueError(f"engineering deck has {len(deck)} cards, expected 60")
    lib = ctypes.CDLL(str(library))
    lib.GameInitialize()
    lib.BattleStart.restype = StartData
    lib.BattleStart.argtypes = [ctypes.POINTER(ctypes.c_int)]
    lib.GetBattleData.restype = SerialData
    lib.GetBattleData.argtypes = [ctypes.c_void_p]
    lib.Select.restype = ctypes.c_int
    lib.Select.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.c_int]
    lib.BattleFinish.argtypes = [ctypes.c_void_p]
    cards = (ctypes.c_int * 120)(*(deck + deck))
    start = lib.BattleStart(cards)
    if not start.battlePtr:
        raise RuntimeError(f"BattleStart failed: player={start.errorPlayer} type={start.errorType}")

    selection_count = 0
    terminal_result: int | None = None
    terminal_had_stale_selection = False

    def submit(indices: list[int]) -> None:
        choice = (ctypes.c_int * len(indices))(*indices)
        error = lib.Select(start.battlePtr, choice, len(indices))
        if error:
            raise RuntimeError(f"Select failed with engine error {error}")

    try:
        observation = json.loads(lib.GetBattleData(start.battlePtr).json.decode())
        while selection_count < max_selections:
            result = (observation.get("current") or {}).get("result")
            if result in TERMINAL_RESULTS:
                terminal_result = result
                terminal_had_stale_selection = bool(observation.get("select"))
                break
            if select_if_ongoing(observation, submit):
                selection_count += 1
            observation = json.loads(lib.GetBattleData(start.battlePtr).json.decode())
        else:
            raise RuntimeError(f"battle did not terminate after {max_selections} selections")
    finally:
        lib.BattleFinish(start.battlePtr)

    if selection_count == 0 or terminal_result not in TERMINAL_RESULTS:
        raise RuntimeError("native smoke did not select and reach a declared terminal result")
    return {
        "finished": True,
        "loaded": True,
        "post_terminal_selection_count": 0,
        "selected": True,
        "selection_count": selection_count,
        "started": True,
        "terminal_had_stale_selection": terminal_had_stale_selection,
        "terminal_result": terminal_result,
    }


if __name__ == "__main__":
    print(json.dumps(probe(Path(sys.argv[1]), Path(sys.argv[2])), sort_keys=True))
