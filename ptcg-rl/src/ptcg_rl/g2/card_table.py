from __future__ import annotations

import csv
import hashlib
import importlib
import json
import platform
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable, Mapping, Sequence

from ptcg_rl.g1.models import stable_hash

CARD_TABLE_SCHEMA_VERSION = 1
ENERGY_TYPE_COUNT = 12
CSV_COLUMNS = (
    "Card ID",
    "Card Name",
    "Expansion",
    "Collection No.",
    "Stage (Pokémon)/Type (Energy and Trainer)",
    "Rule",
    "Category",
    "Previous stage",
    "HP",
    "Type",
    "Weakness",
    "Resistance (Type)",
    "Retreat",
    "Move Name",
    "Cost",
    "Damage",
    "Effect Explanation",
)
STATIC_CSV_COLUMNS = CSV_COLUMNS[:13]
STAGE_TO_CARD_TYPE = {
    "Basic Pokémon": 0,
    "Stage 1 Pokémon": 0,
    "Stage 2 Pokémon": 0,
    "Item": 1,
    "Pokémon Tool": 2,
    "Supporter": 3,
    "Stadium": 4,
    "Basic Energy": 5,
    "Special Energy": 6,
}
STAGE_FLAGS = {
    "Basic Pokémon": (True, False, False),
    "Stage 1 Pokémon": (False, True, False),
    "Stage 2 Pokémon": (False, False, True),
}
ENERGY_SYMBOL = {
    "{C}": 0,
    "{G}": 1,
    "{R}": 2,
    "{W}": 3,
    "{L}": 4,
    "{P}": 5,
    "{F}": 6,
    "{D}": 7,
    "{M}": 8,
    "竜": 9,
}


class CardTableError(ValueError):
    pass


@dataclass(frozen=True)
class CardStaticV1:
    card_id: int
    card_type: int
    energy_type: int
    weakness_type: int
    resistance_type: int
    stage_code: int
    hp: int
    retreat_cost: int
    basic: bool
    stage1: bool
    stage2: bool
    ex: bool
    mega_ex: bool
    tera: bool
    ace_spec: bool
    ancient: bool
    future: bool
    fossil: bool
    technical_machine: bool
    trainers_pokemon: bool
    skill_count: int
    attack_ids: tuple[int, ...]


@dataclass(frozen=True)
class AttackStaticV1:
    attack_id: int
    damage: int
    energy_counts: tuple[int, ...]


@dataclass(frozen=True)
class CardTableV1:
    schema_version: int
    card_data_sha256: str
    engine_library_sha256: str
    wrapper_api_sha256: str
    table_sha256: str
    padding_card_id: int
    unknown_card_id: int
    padding_attack_id: int
    unknown_attack_id: int
    cards: tuple[CardStaticV1, ...]
    attacks: tuple[AttackStaticV1, ...]
    csv_rows: int
    ambiguous_type_cards: int

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> CardTableV1:
        return cls(
            schema_version=int(value["schema_version"]),
            card_data_sha256=str(value["card_data_sha256"]),
            engine_library_sha256=str(value["engine_library_sha256"]),
            wrapper_api_sha256=str(value["wrapper_api_sha256"]),
            table_sha256=str(value["table_sha256"]),
            padding_card_id=int(value["padding_card_id"]),
            unknown_card_id=int(value["unknown_card_id"]),
            padding_attack_id=int(value["padding_attack_id"]),
            unknown_attack_id=int(value["unknown_attack_id"]),
            cards=tuple(
                CardStaticV1(
                    **{
                        **dict(item),
                        "attack_ids": tuple(int(x) for x in item["attack_ids"]),
                    }
                )
                for item in value["cards"]
            ),
            attacks=tuple(
                AttackStaticV1(
                    **{
                        **dict(item),
                        "energy_counts": tuple(int(x) for x in item["energy_counts"]),
                    }
                )
                for item in value["attacks"]
            ),
            csv_rows=int(value["csv_rows"]),
            ambiguous_type_cards=int(value["ambiguous_type_cards"]),
        )


@dataclass(frozen=True)
class NativeCatalog:
    cards: tuple[Any, ...]
    attacks: tuple[Any, ...]
    engine_library_sha256: str
    wrapper_api_sha256: str


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _file_sha256(path: Path) -> str:
    return _sha256(path.read_bytes())


def _require_sha256(value: str, name: str) -> str:
    text = value.lower().strip()
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise CardTableError(f"{name} must be a lowercase SHA-256 digest")
    return text


def _module_under_root(module: ModuleType, root: Path, name: str) -> None:
    module_path = Path(str(module.__file__)).resolve()
    if not module_path.is_relative_to(root):
        raise CardTableError(f"loaded {name} does not come from the requested wrapper root")


def load_native_catalog(sample_submission_root: Path) -> NativeCatalog:
    root = sample_submission_root.resolve()
    api_path = root / "cg" / "api.py"
    if not api_path.is_file():
        raise CardTableError(f"cg/api.py not found under {root}")
    for name in ("cg", "cg.api", "cg.sim"):
        existing = sys.modules.get(name)
        if existing is not None and getattr(existing, "__file__", None):
            _module_under_root(existing, root, name)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    api = importlib.import_module("cg.api")
    sim = importlib.import_module("cg.sim")
    _module_under_root(api, root, "cg.api")
    _module_under_root(sim, root, "cg.sim")
    library_name = (
        "libcg-arm64.so" if platform.machine() in {"arm64", "aarch64"} else "libcg.so"
    )
    expected_library = (root / "cg" / library_name).resolve()
    loaded_library = Path(sim.lib._name).resolve()
    if loaded_library != expected_library:
        raise CardTableError("loaded native library differs from the requested wrapper root")
    return NativeCatalog(
        cards=tuple(api.all_card_data()),
        attacks=tuple(api.all_attack()),
        engine_library_sha256=_file_sha256(loaded_library),
        wrapper_api_sha256=_file_sha256(api_path),
    )


def _read_csv_groups(
    path: Path, expected_sha256: str
) -> tuple[str, int, dict[int, dict[str, str]], int]:
    raw = path.read_bytes()
    digest = _sha256(raw)
    if digest != _require_sha256(expected_sha256, "expected_card_data_sha256"):
        raise CardTableError(
            f"card CSV hash mismatch: expected {expected_sha256}, observed {digest}"
        )
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError as error:
        raise CardTableError("card CSV is not valid UTF-8") from error
    reader = csv.DictReader(text.splitlines())
    if tuple(reader.fieldnames or ()) != CSV_COLUMNS:
        raise CardTableError(f"card CSV columns differ: {tuple(reader.fieldnames or ())}")
    rows = list(reader)
    if not rows:
        raise CardTableError("card CSV is empty")
    groups: dict[int, list[dict[str, str]]] = {}
    for line_number, row in enumerate(rows, 2):
        try:
            card_id = int(row["Card ID"])
        except ValueError as error:
            raise CardTableError(f"invalid card ID on CSV line {line_number}") from error
        if card_id <= 0:
            raise CardTableError(f"nonpositive card ID on CSV line {line_number}")
        groups.setdefault(card_id, []).append(row)
    if sorted(groups) != list(range(1, max(groups) + 1)):
        raise CardTableError("card CSV IDs must be contiguous from one")
    collapsed: dict[int, dict[str, str]] = {}
    ambiguous_type_cards = 0
    for card_id, card_rows in groups.items():
        for column in STATIC_CSV_COLUMNS:
            values = {row[column].strip() for row in card_rows}
            if len(values) != 1:
                raise CardTableError(
                    f"card {card_id} has inconsistent static CSV field {column!r}"
                )
        collapsed[card_id] = {column: card_rows[0][column].strip() for column in CSV_COLUMNS}
        if collapsed[card_id]["Type"] not in ENERGY_SYMBOL:
            ambiguous_type_cards += 1
    return digest, len(rows), collapsed, ambiguous_type_cards


def _parse_optional_int(value: str, name: str, card_id: int) -> int:
    text = value.strip().lower()
    if text in {"", "n/a"}:
        return 0
    try:
        result = int(text)
    except ValueError as error:
        raise CardTableError(f"card {card_id} has invalid {name}: {value!r}") from error
    if result < 0:
        raise CardTableError(f"card {card_id} has negative {name}")
    return result


def _optional_energy(value: str) -> int:
    text = value.strip()
    if text in {"", "n/a"}:
        return -1
    try:
        return ENERGY_SYMBOL[text]
    except KeyError as error:
        raise CardTableError(f"unsupported energy symbol {text!r}") from error


def _stage_code(card: Any) -> int:
    flags = (bool(card.basic), bool(card.stage1), bool(card.stage2))
    if sum(flags) > 1:
        raise CardTableError(f"card {card.cardId} has contradictory stage flags")
    if flags[0]:
        return 1
    if flags[1]:
        return 2
    if flags[2]:
        return 3
    return 0


def _validate_csv_native(card: Any, row: Mapping[str, str]) -> None:
    card_id = int(card.cardId)
    stage = row["Stage (Pokémon)/Type (Energy and Trainer)"]
    expected_card_type = STAGE_TO_CARD_TYPE.get(stage)
    if expected_card_type is None:
        raise CardTableError(f"card {card_id} has unsupported stage/type {stage!r}")
    if int(card.cardType) != expected_card_type:
        raise CardTableError(f"card {card_id} card type differs between CSV and native metadata")
    expected_flags = STAGE_FLAGS.get(stage)
    if expected_flags is not None and expected_flags != (
        bool(card.basic),
        bool(card.stage1),
        bool(card.stage2),
    ):
        raise CardTableError(f"card {card_id} stage flags differ between CSV and native metadata")
    if int(card.hp) != _parse_optional_int(row["HP"], "HP", card_id):
        raise CardTableError(f"card {card_id} HP differs between CSV and native metadata")
    if int(card.retreatCost) != _parse_optional_int(row["Retreat"], "retreat", card_id):
        raise CardTableError(f"card {card_id} retreat differs between CSV and native metadata")
    weakness = -1 if card.weakness is None else int(card.weakness)
    resistance = -1 if card.resistance is None else int(card.resistance)
    if weakness != _optional_energy(row["Weakness"]):
        raise CardTableError(f"card {card_id} weakness differs between CSV and native metadata")
    if resistance != _optional_energy(row["Resistance (Type)"]):
        raise CardTableError(f"card {card_id} resistance differs between CSV and native metadata")
    csv_energy = ENERGY_SYMBOL.get(row["Type"])
    if csv_energy is not None and int(card.energyType) != csv_energy:
        raise CardTableError(f"card {card_id} type differs between CSV and native metadata")


def _category_flags(value: str) -> tuple[bool, bool, bool, bool, bool]:
    text = value.strip()
    return (
        text == "Ancient",
        text == "Future",
        text == "Fossil",
        text == "Technical Machine",
        text.startswith("Trainer's Pokémon"),
    )


def _attack_record(attack: Any) -> AttackStaticV1:
    attack_id = int(attack.attackId)
    if attack_id <= 0:
        raise CardTableError("native attack IDs must be positive")
    counts = [0] * ENERGY_TYPE_COUNT
    for energy in attack.energies:
        value = int(energy)
        if not 0 <= value < ENERGY_TYPE_COUNT:
            raise CardTableError(f"attack {attack_id} contains an unknown energy enum")
        counts[value] += 1
    damage = int(attack.damage)
    if damage < 0:
        raise CardTableError(f"attack {attack_id} has negative base damage")
    return AttackStaticV1(attack_id=attack_id, damage=damage, energy_counts=tuple(counts))


def _table_payload(
    card_data_sha256: str,
    engine_library_sha256: str,
    wrapper_api_sha256: str,
    cards: Sequence[CardStaticV1],
    attacks: Sequence[AttackStaticV1],
    csv_rows: int,
    ambiguous_type_cards: int,
) -> dict[str, Any]:
    return {
        "schema_version": CARD_TABLE_SCHEMA_VERSION,
        "card_data_sha256": card_data_sha256,
        "engine_library_sha256": engine_library_sha256,
        "wrapper_api_sha256": wrapper_api_sha256,
        "padding_card_id": 0,
        "unknown_card_id": len(cards) + 1,
        "padding_attack_id": 0,
        "unknown_attack_id": len(attacks) + 1,
        "cards": [asdict(card) for card in cards],
        "attacks": [asdict(attack) for attack in attacks],
        "csv_rows": csv_rows,
        "ambiguous_type_cards": ambiguous_type_cards,
    }


def build_card_table_from_metadata(
    card_csv: Path,
    expected_card_data_sha256: str,
    native_cards: Iterable[Any],
    native_attacks: Iterable[Any],
    engine_library_sha256: str,
    wrapper_api_sha256: str,
) -> CardTableV1:
    card_data_sha256, csv_rows, csv_cards, ambiguous_type_cards = _read_csv_groups(
        card_csv, expected_card_data_sha256
    )
    native_card_values = tuple(native_cards)
    native_attack_values = tuple(native_attacks)
    cards_by_id = {int(card.cardId): card for card in native_card_values}
    if len(cards_by_id) != len(native_card_values):
        raise CardTableError("native card IDs are duplicated")
    if sorted(cards_by_id) != sorted(csv_cards):
        raise CardTableError("native card IDs differ from the CSV card IDs")
    attacks_by_id = {int(attack.attackId): attack for attack in native_attack_values}
    if len(attacks_by_id) != len(native_attack_values):
        raise CardTableError("native attack IDs are duplicated")
    if sorted(attacks_by_id) != list(range(1, len(attacks_by_id) + 1)):
        raise CardTableError("native attack IDs must be contiguous from one")

    attacks = tuple(_attack_record(attacks_by_id[index]) for index in sorted(attacks_by_id))
    valid_attack_ids = set(attacks_by_id)
    cards: list[CardStaticV1] = []
    for card_id in sorted(cards_by_id):
        card = cards_by_id[card_id]
        row = csv_cards[card_id]
        _validate_csv_native(card, row)
        attack_ids = tuple(int(value) for value in card.attacks)
        if len(attack_ids) != len(set(attack_ids)):
            raise CardTableError(f"card {card_id} repeats an attack ID")
        if any(value not in valid_attack_ids for value in attack_ids):
            raise CardTableError(f"card {card_id} references an unknown attack ID")
        category_flags = _category_flags(row["Category"])
        cards.append(
            CardStaticV1(
                card_id=card_id,
                card_type=int(card.cardType),
                energy_type=int(card.energyType),
                weakness_type=-1 if card.weakness is None else int(card.weakness),
                resistance_type=-1 if card.resistance is None else int(card.resistance),
                stage_code=_stage_code(card),
                hp=int(card.hp),
                retreat_cost=int(card.retreatCost),
                basic=bool(card.basic),
                stage1=bool(card.stage1),
                stage2=bool(card.stage2),
                ex=bool(card.ex),
                mega_ex=bool(card.megaEx),
                tera=bool(card.tera),
                ace_spec=bool(card.aceSpec),
                ancient=category_flags[0],
                future=category_flags[1],
                fossil=category_flags[2],
                technical_machine=category_flags[3],
                trainers_pokemon=category_flags[4],
                skill_count=len(card.skills),
                attack_ids=attack_ids,
            )
        )
    card_records = tuple(cards)
    payload = _table_payload(
        card_data_sha256,
        _require_sha256(engine_library_sha256, "engine_library_sha256"),
        _require_sha256(wrapper_api_sha256, "wrapper_api_sha256"),
        card_records,
        attacks,
        csv_rows,
        ambiguous_type_cards,
    )
    return CardTableV1(
        **{
            **payload,
            "table_sha256": stable_hash(payload),
            "cards": card_records,
            "attacks": attacks,
        }
    )


def build_card_table(
    card_csv: Path,
    expected_card_data_sha256: str,
    sample_submission_root: Path,
) -> CardTableV1:
    catalog = load_native_catalog(sample_submission_root)
    return build_card_table_from_metadata(
        card_csv=card_csv,
        expected_card_data_sha256=expected_card_data_sha256,
        native_cards=catalog.cards,
        native_attacks=catalog.attacks,
        engine_library_sha256=catalog.engine_library_sha256,
        wrapper_api_sha256=catalog.wrapper_api_sha256,
    )


def verify_card_table(table: CardTableV1) -> dict[str, Any]:
    payload = _table_payload(
        table.card_data_sha256,
        table.engine_library_sha256,
        table.wrapper_api_sha256,
        table.cards,
        table.attacks,
        table.csv_rows,
        table.ambiguous_type_cards,
    )
    actual = stable_hash(payload)
    if actual != table.table_sha256:
        raise CardTableError("card table SHA-256 does not match its canonical contents")
    if table.padding_card_id != 0 or table.padding_attack_id != 0:
        raise CardTableError("padding IDs must remain zero")
    if table.unknown_card_id != len(table.cards) + 1:
        raise CardTableError("unknown card ID is not immediately above the card vocabulary")
    if table.unknown_attack_id != len(table.attacks) + 1:
        raise CardTableError("unknown attack ID is not immediately above the attack vocabulary")
    return {
        "status": "pass",
        "table_sha256": actual,
        "cards": len(table.cards),
        "attacks": len(table.attacks),
        "csv_rows": table.csv_rows,
        "ambiguous_type_cards": table.ambiguous_type_cards,
        "max_attacks_per_card": max((len(card.attack_ids) for card in table.cards), default=0),
        "max_energy_cost": max(
            (sum(attack.energy_counts) for attack in table.attacks), default=0
        ),
    }


def write_card_table(table: CardTableV1, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(json.dumps(asdict(table), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_card_table(path: Path) -> CardTableV1:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CardTableError(f"cannot load card table {path}: {error}") from error
    if not isinstance(value, Mapping):
        raise CardTableError("card table root must be an object")
    table = CardTableV1.from_mapping(value)
    verify_card_table(table)
    return table
