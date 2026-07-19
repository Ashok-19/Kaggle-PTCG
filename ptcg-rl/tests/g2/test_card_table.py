from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest

from ptcg_rl.g2.card_table import (
    CSV_COLUMNS,
    CardTableError,
    build_card_table_from_metadata,
    load_card_table,
    verify_card_table,
    write_card_table,
)


def card(**overrides):
    values = {
        "cardId": 1,
        "cardType": 0,
        "retreatCost": 1,
        "hp": 70,
        "weakness": 2,
        "resistance": None,
        "energyType": 1,
        "basic": True,
        "stage1": False,
        "stage2": False,
        "ex": False,
        "megaEx": False,
        "tera": False,
        "aceSpec": False,
        "evolvesFrom": None,
        "skills": [SimpleNamespace(name="hidden", text="hidden")],
        "attacks": [1, 2],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def attack(attack_id: int, damage: int, energies: list[int]):
    return SimpleNamespace(
        attackId=attack_id,
        name="hidden",
        text="hidden",
        damage=damage,
        energies=energies,
    )


def csv_rows() -> list[dict[str, object]]:
    common = {
        "Card ID": 1,
        "Card Name": "Private Card Name",
        "Expansion": "Private Expansion",
        "Collection No.": "001",
        "Stage (Pokémon)/Type (Energy and Trainer)": "Basic Pokémon",
        "Rule": "n/a",
        "Category": "Ancient",
        "Previous stage": "n/a",
        "HP": "70",
        "Type": "{G}",
        "Weakness": "{R}",
        "Resistance (Type)": "n/a",
        "Retreat": "1",
    }
    return [
        {
            **common,
            "Move Name": "Private Move One",
            "Cost": "{G}",
            "Damage": "20",
            "Effect Explanation": "Private effect text one",
        },
        {
            **common,
            "Move Name": "Private Move Two",
            "Cost": "{C}",
            "Damage": "0",
            "Effect Explanation": "Private effect text two",
        },
        {
            "Card ID": 2,
            "Card Name": "Private Trainer Name",
            "Expansion": "Private Expansion",
            "Collection No.": "002",
            "Stage (Pokémon)/Type (Energy and Trainer)": "Item",
            "Rule": "n/a",
            "Category": "Technical Machine",
            "Previous stage": "n/a",
            "HP": "n/a",
            "Type": "n/a",
            "Weakness": "",
            "Resistance (Type)": "",
            "Retreat": "n/a",
            "Move Name": "n/a",
            "Cost": "n/a",
            "Damage": "n/a",
            "Effect Explanation": "Private trainer text",
        },
    ]


def write_csv(path: Path, rows: list[dict[str, object]] | None = None) -> str:
    rows = rows or csv_rows()
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CSV_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_fixture(path: Path):
    digest = write_csv(path)
    return build_card_table_from_metadata(
        card_csv=path,
        expected_card_data_sha256=digest,
        native_cards=(
            card(),
            card(
                cardId=2,
                cardType=1,
                retreatCost=0,
                hp=0,
                weakness=None,
                resistance=None,
                energyType=0,
                basic=False,
                skills=[],
                attacks=[],
            ),
        ),
        native_attacks=(attack(1, 20, [1]), attack(2, 0, [0, 0])),
        engine_library_sha256="e" * 64,
        wrapper_api_sha256="a" * 64,
    )


def test_builder_collapses_move_rows_and_emits_numeric_only_table(tmp_path: Path) -> None:
    table = build_fixture(tmp_path / "cards.csv")
    assert len(table.cards) == 2
    assert len(table.attacks) == 2
    assert table.cards[0].attack_ids == (1, 2)
    assert table.cards[0].ancient is True
    assert table.cards[1].technical_machine is True
    assert table.unknown_card_id == 3
    assert table.unknown_attack_id == 3
    assert table.attacks[1].energy_counts[0] == 2
    assert verify_card_table(table)["status"] == "pass"

    serialized = json.dumps(asdict(table), sort_keys=True).lower()
    for forbidden in ("private card", "private move", "private effect", "private trainer"):
        assert forbidden not in serialized


def test_card_table_round_trip_preserves_hash(tmp_path: Path) -> None:
    table = build_fixture(tmp_path / "cards.csv")
    output = tmp_path / "card-table.json"
    write_card_table(table, output)
    loaded = load_card_table(output)
    assert loaded == table
    assert loaded.table_sha256 == table.table_sha256


def test_inconsistent_static_csv_field_fails(tmp_path: Path) -> None:
    rows = csv_rows()
    rows[1]["HP"] = "80"
    path = tmp_path / "cards.csv"
    digest = write_csv(path, rows)
    with pytest.raises(CardTableError, match="inconsistent static CSV field"):
        build_card_table_from_metadata(
            path,
            digest,
            (),
            (),
            "e" * 64,
            "a" * 64,
        )


def test_hash_and_native_reconciliation_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "cards.csv"
    digest = write_csv(path)
    with pytest.raises(CardTableError, match="hash mismatch"):
        build_card_table_from_metadata(path, "0" * 64, (), (), "e" * 64, "a" * 64)

    with pytest.raises(CardTableError, match="HP differs"):
        build_card_table_from_metadata(
            path,
            digest,
            (
                card(hp=80),
                card(
                    cardId=2,
                    cardType=1,
                    retreatCost=0,
                    hp=0,
                    weakness=None,
                    resistance=None,
                    energyType=0,
                    basic=False,
                    skills=[],
                    attacks=[],
                ),
            ),
            (attack(1, 20, [1]), attack(2, 0, [0])),
            "e" * 64,
            "a" * 64,
        )


def test_unknown_attack_reference_fails(tmp_path: Path) -> None:
    path = tmp_path / "cards.csv"
    digest = write_csv(path)
    with pytest.raises(CardTableError, match="unknown attack ID"):
        build_card_table_from_metadata(
            path,
            digest,
            (
                card(attacks=[3]),
                card(
                    cardId=2,
                    cardType=1,
                    retreatCost=0,
                    hp=0,
                    weakness=None,
                    resistance=None,
                    energyType=0,
                    basic=False,
                    skills=[],
                    attacks=[],
                ),
            ),
            (attack(1, 20, [1]), attack(2, 0, [0])),
            "e" * 64,
            "a" * 64,
        )
