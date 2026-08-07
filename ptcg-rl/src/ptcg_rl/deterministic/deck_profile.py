"""Exact-deck, numeric-only profiles bound to the versioned G2 card table.

The profile records identity and explicit requirements only.  It does not
contain card names, effect prose, strategic scores, beliefs, or an inference
policy.  A caller must provide the already-validated :class:`CardTableV1`.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from json import dumps
from collections import Counter
from typing import Any, Mapping, Sequence

from ptcg_rl.g2.card_table import CardTableV1, verify_card_table


DECK_PROFILE_SCHEMA_VERSION = 1
EXACT_DECK_SIZE = 60
MEGA_ABOMASNOW_CARD_IDS = (721, 722, 723, 1121, 1126, 1192, 1227, 1262, 3)
MEGA_ABOMASNOW_CARD_COUNTS = (
    (3, 34), (721, 2), (722, 4), (723, 4), (1121, 4),
    (1126, 1), (1192, 4), (1227, 4), (1262, 3),
)
MEGA_ABOMASNOW_ORDERED_CARD_IDS = (
    721, 721,
    722, 722, 722, 722,
    723, 723, 723, 723,
    1121, 1121, 1121, 1121,
    1126,
    1192, 1192, 1192, 1192,
    1227, 1227, 1227, 1227,
    1262, 1262, 1262,
    *(3 for _ in range(34)),
)


class DeckProfileError(ValueError):
    """Raised when a profile is not an exact, table-bound deck."""


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _canonical(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return {name: _canonical(getattr(value, name)) for name in value.__dataclass_fields__}
    return value


def _canonical_bytes(value: Any) -> bytes:
    return dumps(_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _hash(value: Any) -> str:
    return sha256(_canonical_bytes(value)).hexdigest()


def _digest(value: str, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise DeckProfileError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise DeckProfileError(f"{field} must be a positive integer")
    return value


ROLE_LABELS = frozenset({
    "ACE_SPEC", "BASIC_ENERGY", "BASIC_POKEMON", "EVOLUTION_PIECE", "OPENING",
    "PRIMARY_ATTACKER", "SEARCH", "STADIUM", "SUPPORTER",
})


@dataclass(frozen=True)
class RoleAssignmentV1:
    card_id: int
    roles: tuple[str, ...]

    def __post_init__(self) -> None:
        _positive_int(self.card_id, "role card_id")
        if any(role not in ROLE_LABELS for role in self.roles):
            raise DeckProfileError("role label is not in the deterministic allowlist")
        if not self.roles or tuple(sorted(set(self.roles))) != self.roles:
            raise DeckProfileError("roles must be a sorted, nonempty unique tuple")
        if any(not role or role != role.upper() for role in self.roles):
            raise DeckProfileError("roles must be nonempty uppercase labels")


@dataclass(frozen=True)
class EvolutionRequirementV1:
    card_id: int
    previous_card_ids: tuple[int, ...]

    def __post_init__(self) -> None:
        _positive_int(self.card_id, "evolution card_id")
        if not self.previous_card_ids or tuple(sorted(set(self.previous_card_ids))) != self.previous_card_ids:
            raise DeckProfileError("evolution previous_card_ids must be sorted and unique")
        for card_id in self.previous_card_ids:
            _positive_int(card_id, "evolution previous card_id")

    @property
    def previous_card_id(self) -> int:
        """Convenience view for the common single-predecessor evolution."""

        if len(self.previous_card_ids) != 1:
            raise DeckProfileError("requirement has multiple previous card IDs")
        return self.previous_card_ids[0]


@dataclass(frozen=True)
class AttackRequirementV1:
    card_id: int
    attack_id: int
    energy_counts: tuple[int, ...]

    def __post_init__(self) -> None:
        _positive_int(self.card_id, "attack card_id")
        _positive_int(self.attack_id, "attack_id")
        if not isinstance(self.energy_counts, tuple):
            raise DeckProfileError("attack energy_counts must be an immutable tuple")
        if len(self.energy_counts) != 12:
            raise DeckProfileError("attack energy_counts must have 12 G2 energy entries")
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in self.energy_counts):
            raise DeckProfileError("attack energy_counts must be nonnegative integers")


@dataclass(frozen=True)
class DeckProfileV1:
    schema_version: int
    deck_id: str
    card_table_sha256: str
    card_data_sha256: str
    engine_library_sha256: str
    wrapper_api_sha256: str
    ordered_card_ids: tuple[int, ...]
    roles: tuple[RoleAssignmentV1, ...]
    evolution_requirements: tuple[EvolutionRequirementV1, ...]
    attack_requirements: tuple[AttackRequirementV1, ...]
    ordered_hash: str
    multiset_hash: str
    role_hash: str
    requirements_hash: str
    profile_hash: str

    def __post_init__(self) -> None:
        if self.schema_version != DECK_PROFILE_SCHEMA_VERSION:
            raise DeckProfileError("unknown deck profile schema version")
        if not isinstance(self.deck_id, str) or not self.deck_id:
            raise DeckProfileError("deck_id must be a nonempty string")
        _digest(self.card_table_sha256, "card_table_sha256")
        _digest(self.card_data_sha256, "card_data_sha256")
        _digest(self.engine_library_sha256, "engine_library_sha256")
        _digest(self.wrapper_api_sha256, "wrapper_api_sha256")
        if len(self.ordered_card_ids) != EXACT_DECK_SIZE:
            raise DeckProfileError("deck must contain exactly 60 cards")
        if not isinstance(self.ordered_card_ids, tuple):
            raise DeckProfileError("ordered card IDs must be an immutable tuple")
        if any(isinstance(card_id, bool) or not isinstance(card_id, int) or card_id <= 0 for card_id in self.ordered_card_ids):
            raise DeckProfileError("ordered card IDs must be positive integers")
        if not isinstance(self.roles, tuple) or not isinstance(self.evolution_requirements, tuple) or not isinstance(self.attack_requirements, tuple):
            raise DeckProfileError("profile records must be immutable tuples")
        if any(not isinstance(row, RoleAssignmentV1) for row in self.roles):
            raise DeckProfileError("roles contain an invalid record")
        if any(not isinstance(row, EvolutionRequirementV1) for row in self.evolution_requirements):
            raise DeckProfileError("evolution requirements contain an invalid record")
        if any(not isinstance(row, AttackRequirementV1) for row in self.attack_requirements):
            raise DeckProfileError("attack requirements contain an invalid record")
        distinct_ids = set(self.ordered_card_ids)
        role_ids = tuple(row.card_id for row in self.roles)
        if role_ids != tuple(sorted(distinct_ids)):
            raise DeckProfileError("roles must cover every distinct deck card exactly once")
        evolution_keys = [(row.card_id, row.previous_card_ids) for row in self.evolution_requirements]
        if len(evolution_keys) != len(set(evolution_keys)):
            raise DeckProfileError("duplicate evolution requirement")
        attack_keys = [(row.card_id, row.attack_id) for row in self.attack_requirements]
        if len(attack_keys) != len(set(attack_keys)):
            raise DeckProfileError("duplicate attack requirement")
        expected = self._hash_payloads()
        for name, actual in expected.items():
            if actual != getattr(self, name):
                raise DeckProfileError(f"{name} does not match canonical profile contents")

    @classmethod
    def build(
        cls,
        card_table: CardTableV1,
        ordered_card_ids: Sequence[int],
        *,
        deck_id: str,
        roles: Sequence[RoleAssignmentV1] = (),
        evolution_requirements: Sequence[EvolutionRequirementV1] = (),
        attack_requirements: Sequence[AttackRequirementV1] = (),
    ) -> "DeckProfileV1":
        if card_table.schema_version != 1:
            raise DeckProfileError("profile requires CardTableV1")
        try:
            verify_card_table(card_table)
        except Exception as error:
            raise DeckProfileError(f"card table verification failed: {error}") from error
        ordered = tuple(ordered_card_ids)
        if len(ordered) != EXACT_DECK_SIZE:
            raise DeckProfileError("deck must contain exactly 60 cards")
        if any(isinstance(card_id, bool) or not isinstance(card_id, int) or card_id <= 0 for card_id in ordered):
            raise DeckProfileError("ordered card IDs must be positive integers")
        known_ids = {card.card_id for card in card_table.cards}
        if len(known_ids) != len(card_table.cards) or any(
            isinstance(card_id, bool) or not isinstance(card_id, int) or card_id <= 0 for card_id in known_ids
        ):
            raise DeckProfileError("card table contains duplicate or nonpositive card IDs")
        attack_ids = [attack.attack_id for attack in card_table.attacks]
        if len(set(attack_ids)) != len(attack_ids) or any(attack_id <= 0 for attack_id in attack_ids):
            raise DeckProfileError("card table contains duplicate or nonpositive attack IDs")
        if any(card_id not in known_ids for card_id in ordered):
            unknown = next(card_id for card_id in ordered if card_id not in known_ids)
            raise DeckProfileError(f"deck card ID {unknown} is absent from CardTableV1")
        if any(not isinstance(row, RoleAssignmentV1) for row in roles):
            raise DeckProfileError("roles contain an invalid record")
        if any(not isinstance(row, EvolutionRequirementV1) for row in evolution_requirements):
            raise DeckProfileError("evolution requirements contain an invalid record")
        if any(not isinstance(row, AttackRequirementV1) for row in attack_requirements):
            raise DeckProfileError("attack requirements contain an invalid record")
        role_rows = tuple(sorted(roles, key=lambda row: row.card_id))
        evolution_rows = tuple(sorted(evolution_requirements, key=lambda row: (row.card_id, row.previous_card_ids)))
        attack_rows = tuple(sorted(attack_requirements, key=lambda row: (row.card_id, row.attack_id)))
        deck_ids = set(ordered)
        if tuple(row.card_id for row in role_rows) != tuple(sorted(deck_ids)):
            raise DeckProfileError("roles must cover every distinct deck card exactly once")
        ace_spec_cards = [card_id for card_id in ordered if _require_card(card_table, card_id).ace_spec]
        if len(ace_spec_cards) > 1:
            raise DeckProfileError("deck contains more than one Ace Spec copy")
        for row in role_rows:
            if row.card_id not in deck_ids:
                raise DeckProfileError(f"role card ID {row.card_id} is absent from deck")
            card = _require_card(card_table, row.card_id)
            role_set = set(row.roles)
            if "BASIC_ENERGY" in role_set and (card.card_type != 5 or not card.energy_type >= 0):
                raise DeckProfileError("BASIC_ENERGY role is not bound to a basic energy card")
            if "BASIC_POKEMON" in role_set and (card.card_type != 0 or not card.basic):
                raise DeckProfileError("BASIC_POKEMON role is not bound to a basic Pokemon card")
            if "OPENING" in role_set and not card.basic:
                raise DeckProfileError("OPENING role is not bound to a basic card")
            if "EVOLUTION_PIECE" in role_set and (card.card_type != 0 or card.stage_code <= 1):
                raise DeckProfileError("EVOLUTION_PIECE role is not bound to an evolution card")
            if "PRIMARY_ATTACKER" in role_set and (card.card_type != 0 or not card.attack_ids):
                raise DeckProfileError("PRIMARY_ATTACKER role is not bound to a card with an attack")
            if "SUPPORTER" in role_set and card.card_type != 3:
                raise DeckProfileError("SUPPORTER role is not bound to a supporter card")
            if "STADIUM" in role_set and card.card_type != 4:
                raise DeckProfileError("STADIUM role is not bound to a stadium card")
            if "SEARCH" in role_set and card.card_type not in {1, 3, 4}:
                raise DeckProfileError("SEARCH role is not bound to an item/supporter/stadium card")
            if "BASIC_ENERGY" in row.roles and card.card_type != 5:
                raise DeckProfileError("BASIC_ENERGY role is not bound to an energy card")
            if "ACE_SPEC" in row.roles and not card.ace_spec:
                raise DeckProfileError("ACE_SPEC role is not bound to an Ace Spec card")
            if card.ace_spec and "ACE_SPEC" not in role_set:
                raise DeckProfileError("every Ace Spec card must carry the ACE_SPEC role")
        for row in evolution_rows:
            if row.card_id not in deck_ids or not set(row.previous_card_ids).issubset(deck_ids):
                raise DeckProfileError("evolution requirement references card outside deck")
            _require_card(card_table, row.card_id)
            for previous in row.previous_card_ids:
                _require_card(card_table, previous)
            target = _require_card(card_table, row.card_id)
            if target.stage_code <= 1:
                raise DeckProfileError("evolution target is not a non-basic card")
            if any(_require_card(card_table, previous).stage_code != target.stage_code - 1 for previous in row.previous_card_ids):
                raise DeckProfileError("evolution predecessor stage is not provenance-compatible")
        for row in attack_rows:
            card = _require_card(card_table, row.card_id)
            attack = _require_attack(card_table, row.attack_id)
            if row.card_id not in deck_ids or row.attack_id not in card.attack_ids:
                raise DeckProfileError("attack requirement is not owned by its card")
            if tuple(row.energy_counts) != tuple(attack.energy_counts):
                raise DeckProfileError("attack energy requirement differs from CardTableV1")
        payload = {
            "schema_version": DECK_PROFILE_SCHEMA_VERSION,
            "deck_id": deck_id,
            "card_table_sha256": card_table.table_sha256,
            "card_data_sha256": card_table.card_data_sha256,
            "engine_library_sha256": card_table.engine_library_sha256,
            "wrapper_api_sha256": card_table.wrapper_api_sha256,
            "ordered_card_ids": ordered,
            "roles": role_rows,
            "evolution_requirements": evolution_rows,
            "attack_requirements": attack_rows,
        }
        hashes = cls._hash_payloads_for(payload)
        return cls(**payload, **hashes)

    def _hash_payloads(self) -> dict[str, str]:
        return self._hash_payloads_for({
            "schema_version": self.schema_version,
            "deck_id": self.deck_id,
            "card_table_sha256": self.card_table_sha256,
            "card_data_sha256": self.card_data_sha256,
            "engine_library_sha256": self.engine_library_sha256,
            "wrapper_api_sha256": self.wrapper_api_sha256,
            "ordered_card_ids": self.ordered_card_ids,
            "roles": self.roles,
            "evolution_requirements": self.evolution_requirements,
            "attack_requirements": self.attack_requirements,
        })

    @staticmethod
    def _hash_payloads_for(payload: Mapping[str, Any]) -> dict[str, str]:
        ordered = tuple(payload["ordered_card_ids"])
        counts: dict[int, int] = {}
        for card_id in ordered:
            counts[card_id] = counts.get(card_id, 0) + 1
        multiset = tuple((card_id, count) for card_id, count in sorted(counts.items()))
        roles = tuple(payload["roles"])
        requirements = {
            "evolution": tuple(payload["evolution_requirements"]),
            "attack": tuple(payload["attack_requirements"]),
        }
        ordered_hash = _hash({"ordered_card_ids": ordered})
        multiset_hash = _hash({"multiset": multiset})
        role_hash = _hash({"roles": roles})
        requirements_hash = _hash({"requirements": requirements})
        profile_hash = _hash({
            "schema_version": payload["schema_version"],
            "deck_id": payload["deck_id"],
            "card_table_sha256": payload["card_table_sha256"],
            "card_data_sha256": payload["card_data_sha256"],
            "engine_library_sha256": payload["engine_library_sha256"],
            "wrapper_api_sha256": payload["wrapper_api_sha256"],
            "ordered_hash": ordered_hash,
            "multiset_hash": multiset_hash,
            "role_hash": role_hash,
            "requirements_hash": requirements_hash,
        })
        return {
            "ordered_hash": ordered_hash,
            "multiset_hash": multiset_hash,
            "role_hash": role_hash,
            "requirements_hash": requirements_hash,
            "profile_hash": profile_hash,
        }

    @property
    def multiset(self) -> tuple[tuple[int, int], ...]:
        counts: dict[int, int] = {}
        for card_id in self.ordered_card_ids:
            counts[card_id] = counts.get(card_id, 0) + 1
        return tuple(sorted(counts.items()))

    @property
    def card_counts(self) -> tuple[tuple[int, int], ...]:
        return self.multiset

    @property
    def table_hash(self) -> str:
        return self.card_table_sha256

    @property
    def card_table_hash(self) -> str:
        return self.card_table_sha256

    @property
    def deck(self) -> tuple[int, ...]:
        return self.ordered_card_ids

    @property
    def ordered_sha256(self) -> str:
        return self.ordered_hash

    @property
    def multiset_sha256(self) -> str:
        return self.multiset_hash

    @property
    def role_sha256(self) -> str:
        return self.role_hash

    @property
    def requirements_sha256(self) -> str:
        return self.requirements_hash

    @property
    def profile_sha256(self) -> str:
        return self.profile_hash

    @property
    def hashes(self) -> dict[str, str]:
        return {
            "ordered": self.ordered_hash,
            "multiset": self.multiset_hash,
            "role": self.role_hash,
            "requirements": self.requirements_hash,
            "profile": self.profile_hash,
        }

    @property
    def asset_hashes(self) -> dict[str, str]:
        return {
            "card_table": self.card_table_sha256,
            "card_data": self.card_data_sha256,
            "engine_library": self.engine_library_sha256,
            "wrapper_api": self.wrapper_api_sha256,
        }

    def canonical_dict(self) -> dict[str, Any]:
        return _canonical(self)

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self)

    def canonical_json(self) -> str:
        return self.canonical_bytes().decode("utf-8")

    to_dict = canonical_dict

    def serialize(self) -> bytes:
        return self.canonical_bytes()

    to_bytes = serialize

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "DeckProfileV1":
        """Parse canonical profile data and verify all tamper-evident hashes."""

        try:
            payload = dict(value)
            if not isinstance(payload.get("ordered_card_ids"), (list, tuple)):
                raise DeckProfileError("ordered_card_ids must be a list or tuple")
            if not isinstance(payload.get("roles"), (list, tuple)):
                raise DeckProfileError("roles must be a list or tuple")
            if not isinstance(payload.get("evolution_requirements"), (list, tuple)):
                raise DeckProfileError("evolution_requirements must be a list or tuple")
            if not isinstance(payload.get("attack_requirements"), (list, tuple)):
                raise DeckProfileError("attack_requirements must be a list or tuple")
            if any(isinstance(item, bool) or not isinstance(item, int) for item in payload["ordered_card_ids"]):
                raise DeckProfileError("ordered_card_ids must contain integers")
            payload["ordered_card_ids"] = tuple(payload["ordered_card_ids"])
            payload["roles"] = tuple(
                RoleAssignmentV1(item["card_id"], tuple(item["roles"]))
                for item in payload["roles"]
            )
            payload["evolution_requirements"] = tuple(
                EvolutionRequirementV1(item["card_id"], tuple(item["previous_card_ids"]))
                for item in payload["evolution_requirements"]
            )
            payload["attack_requirements"] = tuple(
                AttackRequirementV1(item["card_id"], item["attack_id"], tuple(item["energy_counts"]))
                for item in payload["attack_requirements"]
            )
            return cls(**payload)
        except (KeyError, TypeError, ValueError, DeckProfileError) as error:
            raise DeckProfileError(f"invalid deck profile mapping: {error}") from error

    @classmethod
    def from_ordered_ids(cls, card_table: CardTableV1, ordered_card_ids: Sequence[int], **kwargs: Any) -> "DeckProfileV1":
        return cls.build(card_table, ordered_card_ids, **kwargs)

    def verify(self) -> None:
        self.__post_init__()


def _require_card(card_table: CardTableV1, card_id: int):
    try:
        return next(card for card in card_table.cards if card.card_id == card_id)
    except StopIteration as error:
        raise DeckProfileError(f"card ID {card_id} is absent from CardTableV1") from error


def _require_attack(card_table: CardTableV1, attack_id: int):
    try:
        return next(attack for attack in card_table.attacks if attack.attack_id == attack_id)
    except StopIteration as error:
        raise DeckProfileError(f"attack ID {attack_id} is absent from CardTableV1") from error


def mega_abomasnow_profile(card_table: CardTableV1) -> DeckProfileV1:
    """Build the exact numeric Mega Abomasnow research fixture.

    The fixture is intentionally written as numeric IDs and role labels only;
    it does not import a deck file or card text.  Attack requirements are
    derived from the supplied G2 numeric table so this factory remains bound
    to the table actually used by the caller.
    """

    role_rows = (
        RoleAssignmentV1(3, ("BASIC_ENERGY",)),
        RoleAssignmentV1(721, ("BASIC_POKEMON", "OPENING")),
        RoleAssignmentV1(722, ("EVOLUTION_PIECE",)),
        RoleAssignmentV1(723, ("PRIMARY_ATTACKER",)),
        RoleAssignmentV1(1121, ("SEARCH",)),
        RoleAssignmentV1(1126, ("ACE_SPEC", "SEARCH")),
        RoleAssignmentV1(1192, ("SUPPORTER",)),
        RoleAssignmentV1(1227, ("SUPPORTER",)),
        RoleAssignmentV1(1262, ("STADIUM",)),
    )
    if tuple(sorted(Counter(MEGA_ABOMASNOW_ORDERED_CARD_IDS).items())) != MEGA_ABOMASNOW_CARD_COUNTS:
        raise DeckProfileError("Mega Abomasnow fixture multiset does not match the sanctioned exact deck")
    attack_rows = tuple(
        AttackRequirementV1(card.card_id, attack_id, _require_attack(card_table, attack_id).energy_counts)
        for card_id in MEGA_ABOMASNOW_CARD_IDS
        for card in (_require_card(card_table, card_id),)
        for attack_id in card.attack_ids
    )
    return DeckProfileV1.build(
        card_table,
        MEGA_ABOMASNOW_ORDERED_CARD_IDS,
        deck_id="mega-abomasnow-ex",
        roles=role_rows,
        evolution_requirements=(EvolutionRequirementV1(723, (722,)),),
        attack_requirements=attack_rows,
    )


# Friendly aliases used by canaries and callers that prefer noun-first names.
DeckProfile = DeckProfileV1
RoleRequirementV1 = RoleAssignmentV1
mega_abomasnow_deck_profile = mega_abomasnow_profile
make_mega_abomasnow_profile = mega_abomasnow_profile


__all__ = [
    "AttackRequirementV1",
    "DECK_PROFILE_SCHEMA_VERSION",
    "DeckProfile",
    "DeckProfileError",
    "DeckProfileV1",
    "EXACT_DECK_SIZE",
    "EvolutionRequirementV1",
    "MEGA_ABOMASNOW_CARD_IDS",
    "MEGA_ABOMASNOW_CARD_COUNTS",
    "MEGA_ABOMASNOW_ORDERED_CARD_IDS",
    "RoleAssignmentV1",
    "RoleRequirementV1",
    "ROLE_LABELS",
    "make_mega_abomasnow_profile",
    "mega_abomasnow_deck_profile",
    "mega_abomasnow_profile",
]
