from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SetupCardStatic:
    card_id: int
    is_basic_pokemon: bool
    is_setup_doll: bool
    can_setup: bool
    can_setup_active: bool


def extract_setup_card_static(engine_source_root: Path) -> list[SetupCardStatic]:
    """Extract setup-only flags from the official engine at runtime; persist no card data."""

    root = engine_source_root.resolve(strict=True)
    source = r'''
#include <algorithm>
#include <iostream>
#include <vector>
#include "All.h"
int main() {
    InitializeAll();
    std::vector<int> ids;
    ids.reserve(CardTable.size());
    for (const auto& [id, _] : CardTable) ids.push_back(id);
    std::sort(ids.begin(), ids.end());
    for (int id : ids) {
        const CardMaster& m = CardTable.at(id);
        const bool basic = m.cardType == CardType::Pokemon && m.evolutionType == EvolutionType::Basic;
        const bool doll = m.toBattleFieldOnlySetup || m.toActiveOnlySetup;
        std::cout << id << ' ' << basic << ' ' << doll << ' '
                  << m.canSetup() << ' ' << m.canSetupActive() << '\n';
    }
}
'''
    with tempfile.TemporaryDirectory(prefix="gpu-cabt-card-static-") as tmp:
        cpp = Path(tmp) / "extract.cpp"
        exe = Path(tmp) / "extract"
        cpp.write_text(source, encoding="utf-8")
        subprocess.run(
            ["g++", "-std=c++23", "-O2", "-I", str(root), str(cpp), "-o", str(exe)],
            check=True,
        )
        output = subprocess.check_output([str(exe)], text=True)

    records: list[SetupCardStatic] = []
    for line in output.splitlines():
        card_id, basic, doll, can_setup, can_setup_active = (int(value) for value in line.split())
        records.append(
            SetupCardStatic(
                card_id=card_id,
                is_basic_pokemon=bool(basic),
                is_setup_doll=bool(doll),
                can_setup=bool(can_setup),
                can_setup_active=bool(can_setup_active),
            )
        )
    if not records:
        raise RuntimeError("official setup-card extractor returned no records")
    if len({record.card_id for record in records}) != len(records):
        raise RuntimeError("official setup-card extractor returned duplicate card IDs")
    return records


def dense_setup_card_table(records: list[SetupCardStatic]) -> tuple[bytes, int]:
    """Return a 4-byte-per-card dense table and row count, indexed directly by card ID."""

    if not records:
        raise ValueError("records must not be empty")
    if any(record.card_id < 0 for record in records):
        raise ValueError("card IDs must be nonnegative")
    row_count = max(record.card_id for record in records) + 1
    table = bytearray(row_count * 4)
    seen: set[int] = set()
    for record in records:
        if record.card_id in seen:
            raise ValueError(f"duplicate card ID {record.card_id}")
        seen.add(record.card_id)
        offset = record.card_id * 4
        table[offset : offset + 4] = bytes(
            (
                int(record.is_basic_pokemon),
                int(record.is_setup_doll),
                int(record.can_setup),
                int(record.can_setup_active),
            )
        )
    return bytes(table), row_count
