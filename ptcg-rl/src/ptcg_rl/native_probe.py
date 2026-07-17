from __future__ import annotations

import ctypes
import csv
import json
import sys
from pathlib import Path


class StartData(ctypes.Structure):
    _fields_ = [("battlePtr", ctypes.c_void_p), ("errorPlayer", ctypes.c_int), ("errorType", ctypes.c_int)]


class SerialData(ctypes.Structure):
    _fields_ = [
        ("json", ctypes.c_char_p),
        ("data", ctypes.POINTER(ctypes.c_ubyte)),
        ("count", ctypes.c_int),
        ("selectPlayer", ctypes.c_int),
    ]


def probe(library: Path, deck_file: Path) -> dict[str, object]:
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
    selected = False
    try:
        first = json.loads(lib.GetBattleData(start.battlePtr).json.decode())
        current = first.get("current") or {}
        selection = first.get("select")
        if current.get("result") == -1 and not selection:
            raise RuntimeError("ongoing battle has no selection request")
        if current.get("result") == -1:
            count = int(selection.get("minCount", 0))
            option_count = len(selection.get("option") or [])
            if count > option_count:
                raise RuntimeError("selection minimum exceeds option count")
            choice = (ctypes.c_int * count)(*range(count))
            error = lib.Select(start.battlePtr, choice, count)
            if error:
                raise RuntimeError(f"Select failed with engine error {error}")
            json.loads(lib.GetBattleData(start.battlePtr).json.decode())
            selected = True
    finally:
        lib.BattleFinish(start.battlePtr)
    return {"loaded": True, "started": True, "selected": selected, "finished": True}


if __name__ == "__main__":
    print(json.dumps(probe(Path(sys.argv[1]), Path(sys.argv[2])), sort_keys=True))
