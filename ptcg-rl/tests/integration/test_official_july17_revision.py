from __future__ import annotations

import json
from pathlib import Path

import pytest

from ptcg_rl.g1.evidence import sha256_file


REPO = Path(__file__).resolve().parents[2]


def test_loaded_official_assets_match_reviewed_july17_revision() -> None:
    lock_path = REPO / "private" / "assets.lock.json"
    if not lock_path.is_file():
        pytest.skip("private official assets are not bootstrapped")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    official = lock["assets"]["official"]
    root = Path(official["destination"])
    signatures = official["signatures"]
    assert sha256_file(root / signatures["engine_library"]) == (
        "feafd4046b2f688bdb33a4972c139b78e13e243ab5707ece52c43cf39a34b887"
    )
    assert sha256_file(root / signatures["card_data"]) == (
        "a0ea63cf7adcb65d35436ce0eb390de6e2e35654a7c67c065a45f4abaa00f373"
    )
    state_header = root / "ptcg_engine" / "ptcgProgram 22" / "State.h"
    card_implementation = root / "ptcg_engine" / "ptcgProgram 22" / "CardImpl.h"
    assert sha256_file(state_header) == (
        "a12bc5669b4b79c122899142f86616f8d9926684d9029392220c5c886de2a33c"
    )
    assert sha256_file(card_implementation) == (
        "286a51820d36f9b60b5b13c58bc2edff352eb4050581ddadf1960f13fd6f21a9"
    )
    state_text = state_header.read_text(encoding="utf-8-sig")
    assert "onlyTeamRocket" in state_text
    assert "teamRocket" in state_text
