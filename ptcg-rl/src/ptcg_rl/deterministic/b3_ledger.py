"""Fixture-only Phase B3 resource and Prize ledger evaluators.

This module is deliberately below the native policy boundary.  It consumes a
validated ``PublicStateV1`` and an explicit fixture receipt/local-delta record;
it never calls the engine, reads a successor, identifies a hidden card, or
turns a fixture result into native authority.  B3-B uses exact integer
multivariate-hypergeometric counting and ``Fraction`` throughout.
"""

from __future__ import annotations

import itertools
import json
import math
from dataclasses import dataclass, field, replace
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from ptcg_rl.g1.actions import CompoundActionBuilder
from ptcg_rl.g1.models import (
    CompoundActionV1,
    EngineObservationV1,
    LegalOptionV1,
    SelectionRequestV1,
    stable_hash,
)
from .state import PublicStateError, PublicStateV1


B3_SCHEMA_VERSION = 1
A_FORMULATION = "B3-A-KNOWN-COPY-RESERVE"
B_FORMULATION = "B3-B-CONDITIONAL-FINITE-ODDS"
SELECTED = "SELECTED"
B0_DELEGATE = "B0_DELEGATE"
AMBIGUOUS = "AMBIGUOUS"
TERMINAL_OVERRIDE = "TERMINAL_OVERRIDE"
FIXTURE_ONLY = "FIXTURE_ONLY"
EXPERIMENTAL_FIXTURE_AUTHORITY = "EXPERIMENTAL_RESOURCE_LEDGER_FIXTURE"
_FIXTURE_RECORD_ID = "phase-b3-resource-ledger-fixture-v1"
_CONFIG_RELATIVE = Path("configs/deterministic/phase_b3_resource_ledger_fixture_v1.json")
_KB_RELATIVE = Path("knowledge_base/ptcg_gold.sqlite")
_PROVENANCE_SCHEMA_ID = "phase-b3-resource-ledger-fixture-v1"
_PROVENANCE_SOURCE_PATHS = (
    Path("src/ptcg_rl/deterministic/b3_ledger.py"),
    Path("src/ptcg_rl/g1/models.py"),
    Path("src/ptcg_rl/g1/actions.py"),
    Path("src/ptcg_rl/deterministic/state.py"),
)
_SUPPORTED_SINGLETON_OPTIONS = frozenset({7, 8, 11, 12, 13})
_EXPECTED_CANDIDATE_DECK_COUNTS = MappingProxyType({
    "3": 34,
    "721": 2,
    "722": 4,
    "723": 4,
    "1121": 4,
    "1126": 1,
    "1192": 4,
    "1227": 4,
    "1262": 3,
})
_EXPECTED_CANDIDATE_DECK_SHA256 = "7af2d7e111c084da535b89758730b3fd6cbb7c0543a9444499c5b61efdc8aecd"
_CATEGORIES = frozenset({
    "PUBLIC_USABLE",
    "PUBLIC_DISCARD_OR_RECOVERABLE",
    "PUBLIC_INACCESSIBLE",
})


def _int(value: Any, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _digest(value: Any, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _counts(value: Mapping[str, Any], name: str) -> Mapping[str, int]:
    if not isinstance(value, Mapping) or not value:
        raise ValueError(f"{name} must be a nonempty mapping")
    result: dict[str, int] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key:
            raise ValueError(f"{name} has an invalid role")
        result[key] = _int(item, f"{name}.{key}")
    return MappingProxyType(result)


def _optional_counts(value: Mapping[str, Any], name: str) -> Mapping[str, int]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    result: dict[str, int] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key:
            raise ValueError(f"{name} has an invalid role")
        result[key] = _int(item, f"{name}.{key}")
    return MappingProxyType(result)


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{name} must be finite")
    return float(value)


def _canonical_value(value: Any) -> Any:
    """Return JSON-safe, recursively ordered data for hashes and evidence."""

    if isinstance(value, Mapping):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, frozenset):
        return sorted((_canonical_value(item) for item in value), key=lambda item: json.dumps(item, sort_keys=True))
    if hasattr(value, "__dataclass_fields__"):
        return {
            name: _canonical_value(getattr(value, name))
            for name in value.__dataclass_fields__
        }
    if isinstance(value, Fraction):
        return {"numerator": value.numerator, "denominator": value.denominator}
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(_canonical_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256_json(value: Any) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_value(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze_value(item) for item in value)
    return value


def _allocation_population_digest(populations: Sequence[Mapping[str, int]]) -> str:
    """Digest a finite allocation world-set independently of transport order."""

    canonical = sorted(
        (_canonical_value(population) for population in populations),
        key=_canonical_json,
    )
    return _sha256_json(tuple(canonical))


def _file_sha256(path: Path, name: str) -> str:
    try:
        return sha256(path.read_bytes()).hexdigest()
    except OSError as error:
        raise ValueError(f"missing B3 provenance dependency: {name}") from error


def _digest_payload(value: Mapping[str, Any], *, metadata: bool) -> Mapping[str, Any]:
    """Remove only self-referential digest fields before hashing a fixture."""

    payload = _canonical_value(value)
    if not isinstance(payload, dict):
        raise ValueError("B3 fixture metadata must be a mapping")
    if metadata:
        payload["fixture_metadata_sha256"] = ""
        common = payload.get("common_public_state")
        if isinstance(common, dict) and isinstance(common.get("entities"), list):
            for entity in common["entities"]:
                if isinstance(entity, dict) and entity.get("card_id") is not None:
                    entity["metadata_ref"] = f"card:{entity['card_id']}@"
    provenance = payload.get("provenance")
    if isinstance(provenance, dict):
        provenance["config_payload_sha256"] = ""
        if metadata:
            provenance["fixture_metadata_sha256"] = ""
    receipt = payload.get("receipt")
    if isinstance(receipt, dict):
        receipt_provenance = receipt.get("dependency_provenance")
        if isinstance(receipt_provenance, dict):
            receipt_provenance["config_payload_sha256"] = ""
            if metadata:
                receipt_provenance["fixture_metadata_sha256"] = ""
    return payload


@dataclass(frozen=True)
class PrizeStaticV1:
    """Explicit fixture receipt; no card flag or prose is interpreted."""

    card_id: int
    prize_units: int
    receipt_id: str

    def __post_init__(self) -> None:
        _int(self.card_id, "PrizeStatic.card_id", 1)
        _int(self.prize_units, "PrizeStatic.prize_units", 1)
        if not isinstance(self.receipt_id, str) or not self.receipt_id:
            raise ValueError("PrizeStatic.receipt_id must be nonempty")


@dataclass(frozen=True)
class AllocationReceiptV1:
    """Sealed finite-world measure used by a local probability population."""

    receipt_id: str
    measure_id: str
    capacity_source: str
    allowed_population_sha256: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.receipt_id, str) or not self.receipt_id:
            raise ValueError("allocation receipt_id must be nonempty")
        if self.measure_id not in {"EXPLICIT_FINITE_WORLD_SET"}:
            raise ValueError("allocation receipt measure is not explicitly qualified")
        if self.capacity_source != "PUBLIC_STATE_HIDDEN_DECK_SLOTS":
            raise ValueError("allocation receipt capacity source is not public")
        digests = tuple(self.allowed_population_sha256)
        if not digests or len(digests) != len(set(digests)):
            raise ValueError("allocation receipt must seal one or more finite population world-sets")
        for digest in digests:
            _digest(digest, "allocation population digest")
        object.__setattr__(self, "allowed_population_sha256", digests)


@dataclass(frozen=True)
class RecoverabilityReceiptV1:
    """An explicit, role-scoped qualification for public discard recovery."""

    receipt_id: str
    role: str
    recoverable_count: int
    qualification: str

    def __post_init__(self) -> None:
        if not isinstance(self.receipt_id, str) or not self.receipt_id:
            raise ValueError("recoverability receipt_id must be nonempty")
        if not isinstance(self.role, str) or not self.role:
            raise ValueError("recoverability role must be nonempty")
        _int(self.recoverable_count, "recoverable_count", 1)
        if self.qualification != "PUBLIC_DISCARD_OR_RECOVERABLE_EXPLICIT":
            raise ValueError("recoverability is not explicitly qualified")


@dataclass(frozen=True)
class DeckoutReceiptV1:
    """Version-bound exact public predicate; counts alone never activate DECKOUT."""

    receipt_id: str
    schema_version: int
    route_id: str
    opponent_deck_count: int
    predicate_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.receipt_id, str) or not self.receipt_id:
            raise ValueError("deckout receipt_id must be nonempty")
        if self.schema_version != B3_SCHEMA_VERSION:
            raise ValueError("deckout receipt schema is not version-bound")
        if not isinstance(self.route_id, str) or not self.route_id:
            raise ValueError("deckout route_id must be nonempty")
        _int(self.opponent_deck_count, "deckout opponent_deck_count")
        _digest(self.predicate_sha256, "deckout predicate_sha256")


@dataclass(frozen=True)
class B3CapabilityReceiptV1:
    receipt_id: str
    scope: str
    candidate_deck_sha256: str
    candidate_deck_counts: Mapping[str, int]
    prize_static: tuple[PrizeStaticV1, ...]
    local_delta_receipts: tuple[str, ...]
    allocation_receipts: tuple[AllocationReceiptV1, ...] = ()
    recoverability_receipts: tuple[RecoverabilityReceiptV1, ...] = ()
    deckout_receipt_ids: tuple[str, ...] = ()
    deckout_receipts: tuple[DeckoutReceiptV1, ...] = ()
    dependency_provenance: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if self.receipt_id != _FIXTURE_RECORD_ID:
            raise ValueError("unknown B3 fixture receipt")
        if self.scope != FIXTURE_ONLY:
            raise ValueError("B3 accepts fixture-only receipt scope")
        _digest(self.candidate_deck_sha256, "candidate_deck_sha256")
        object.__setattr__(self, "candidate_deck_counts", _counts(self.candidate_deck_counts, "candidate_deck_counts"))
        if sum(self.candidate_deck_counts.values()) != 60:
            raise ValueError("candidate deck multiset must contain exactly 60 cards")
        if dict(self.candidate_deck_counts) != dict(_EXPECTED_CANDIDATE_DECK_COUNTS):
            raise ValueError("candidate deck multiset is not the sealed Mega Abomasnow profile")
        if self.candidate_deck_sha256 != _EXPECTED_CANDIDATE_DECK_SHA256:
            raise ValueError("candidate deck multiset is not the sealed Mega Abomasnow receipt")
        if not self.local_delta_receipts or len(set(self.local_delta_receipts)) != len(self.local_delta_receipts):
            raise ValueError("B3 local delta receipts must be nonempty and unique")
        allocation_ids = [item.receipt_id for item in self.allocation_receipts]
        if not allocation_ids or len(allocation_ids) != len(set(allocation_ids)):
            raise ValueError("B3 allocation receipts must be nonempty and unique")
        recovery_ids = [item.receipt_id for item in self.recoverability_receipts]
        recovery_roles = [item.role for item in self.recoverability_receipts]
        if len(recovery_ids) != len(set(recovery_ids)) or len(recovery_roles) != len(set(recovery_roles)):
            raise ValueError("B3 recoverability receipts must be unique")
        if len(self.deckout_receipt_ids) != len(set(self.deckout_receipt_ids)):
            raise ValueError("B3 deckout receipts must be unique")
        deckout_ids = [item.receipt_id for item in self.deckout_receipts]
        if len(deckout_ids) != len(set(deckout_ids)):
            raise ValueError("B3 exact deckout receipts must be unique")
        object.__setattr__(self, "dependency_provenance", _freeze_value(self.dependency_provenance))
        _validate_dependency_provenance(self.dependency_provenance)

    @property
    def allocation_by_id(self) -> Mapping[str, AllocationReceiptV1]:
        return MappingProxyType({item.receipt_id: item for item in self.allocation_receipts})

    @property
    def recoverable_by_role(self) -> Mapping[str, int]:
        return MappingProxyType({item.role: item.recoverable_count for item in self.recoverability_receipts})

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "B3CapabilityReceiptV1":
        return cls(
            receipt_id=str(value["receipt_id"]),
            scope=str(value["scope"]),
            candidate_deck_sha256=str(value["candidate_deck_sha256"]),
            candidate_deck_counts=value["candidate_deck_counts"],
            prize_static=tuple(PrizeStaticV1(**row) for row in value["prize_static"]),
            local_delta_receipts=tuple(str(item) for item in value["local_delta_receipts"]),
            allocation_receipts=tuple(AllocationReceiptV1(**row) for row in value.get("allocation_receipts", ())),
            recoverability_receipts=tuple(
                RecoverabilityReceiptV1(**row) for row in value.get("recoverability_receipts", ())
            ),
            deckout_receipt_ids=tuple(str(item) for item in value.get("deckout_receipt_ids", ())),
            deckout_receipts=tuple(DeckoutReceiptV1(**row) for row in value.get("deckout_receipts", ())),
            dependency_provenance=value["dependency_provenance"],
        )


@dataclass(frozen=True)
class PhysicalCopyReceiptV1:
    physical_id: str
    role: str
    category: str
    source_digest: str
    previous_category: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.physical_id, str) or not self.physical_id:
            raise ValueError("physical copy id must be nonempty")
        if not isinstance(self.role, str) or not self.role:
            raise ValueError("physical copy role must be nonempty")
        if self.category not in _CATEGORIES:
            raise ValueError("unknown physical copy category")
        _digest(self.source_digest, "physical copy source_digest")
        if self.previous_category is not None:
            if self.previous_category not in _CATEGORIES:
                raise ValueError("unknown physical copy previous category")
            if self.previous_category == self.category:
                raise ValueError("physical copy category transition is a no-op")
            if (self.previous_category, self.category) not in {
                ("PUBLIC_USABLE", "PUBLIC_INACCESSIBLE"),
                ("PUBLIC_USABLE", "PUBLIC_DISCARD_OR_RECOVERABLE"),
                ("PUBLIC_DISCARD_OR_RECOVERABLE", "PUBLIC_INACCESSIBLE"),
            }:
                raise ValueError("physical copy category transition is not monotonic")


@dataclass(frozen=True)
class RevealEventV1:
    event_digest: str
    physical_id: str
    before_category: str
    after_category: str
    source_digest: str

    def __post_init__(self) -> None:
        _digest(self.event_digest, "reveal event digest")
        if not isinstance(self.physical_id, str) or not self.physical_id:
            raise ValueError("reveal event physical_id must be nonempty")
        if self.before_category not in _CATEGORIES or self.after_category not in _CATEGORIES:
            raise ValueError("reveal event category is unknown")
        _digest(self.source_digest, "reveal event source_digest")
        if self.before_category == self.after_category:
            raise ValueError("reveal event category transition is a no-op")
        if (self.before_category, self.after_category) not in {
            ("PUBLIC_USABLE", "PUBLIC_INACCESSIBLE"),
            ("PUBLIC_USABLE", "PUBLIC_DISCARD_OR_RECOVERABLE"),
            ("PUBLIC_DISCARD_OR_RECOVERABLE", "PUBLIC_INACCESSIBLE"),
        }:
            raise ValueError("reveal event category transition is not monotonic")


@dataclass(frozen=True)
class ResourceLedgerV1:
    """Known usable/inaccessible/unknown counts with receipt-level accounting."""

    total_by_role: Mapping[str, int]
    known_usable_by_role: Mapping[str, int]
    known_inaccessible_by_role: Mapping[str, int]
    known_discard_by_role: Mapping[str, int]
    unknown_by_role: Mapping[str, int]
    hidden_own_deck_slots: int
    hidden_own_prize_slots: int
    hidden_opponent_slots: int
    prize_static_receipt_id: str
    physical_copy_receipts: tuple[PhysicalCopyReceiptV1, ...]
    reveal_events: tuple[RevealEventV1, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "total_by_role", _counts(self.total_by_role, "total_by_role"))
        for name in (
            "known_usable_by_role", "known_inaccessible_by_role", "known_discard_by_role", "unknown_by_role"
        ):
            object.__setattr__(self, name, _optional_counts(getattr(self, name), name))
        for name in ("hidden_own_deck_slots", "hidden_own_prize_slots", "hidden_opponent_slots"):
            _int(getattr(self, name), name)
        if not isinstance(self.prize_static_receipt_id, str) or not self.prize_static_receipt_id:
            raise ValueError("prize_static_receipt_id must be nonempty")
        self.validate()

    @property
    def known_inaccessible_total(self) -> int:
        return sum(self.known_inaccessible_by_role.values())

    def validate(self) -> None:
        roles = set(self.total_by_role)
        all_ids = [item.physical_id for item in self.physical_copy_receipts]
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("physical copy receipts contain a duplicate physical copy")
        source_digests = [item.source_digest for item in self.physical_copy_receipts]
        if len(source_digests) != len(set(source_digests)):
            raise ValueError("physical copy receipts contain a duplicate source digest")
        event_ids = [item.physical_id for item in self.reveal_events]
        event_digests = [item.event_digest for item in self.reveal_events]
        if len(event_ids) != len(set(event_ids)) or len(event_digests) != len(set(event_digests)):
            raise ValueError("reveal events contain a duplicate physical copy or digest")
        receipt_by_id = {item.physical_id: item for item in self.physical_copy_receipts}
        for event in self.reveal_events:
            receipt = receipt_by_id.get(event.physical_id)
            if (
                receipt is None
                or receipt.category != event.after_category
                or receipt.source_digest != event.source_digest
                or receipt.previous_category != event.before_category
            ):
                raise ValueError("reveal event does not resolve to exactly one public physical copy")
        event_by_id = {event.physical_id: event for event in self.reveal_events}
        for receipt in self.physical_copy_receipts:
            if receipt.previous_category is not None and receipt.physical_id not in event_by_id:
                raise ValueError("physical copy transition is missing its reveal event")
        for role in roles:
            known = sum(
                mapping.get(role, 0)
                for mapping in (
                    self.known_usable_by_role,
                    self.known_inaccessible_by_role,
                    self.known_discard_by_role,
                )
            )
            unknown = self.unknown_by_role.get(role, 0)
            if known + unknown != self.total_by_role[role]:
                raise ValueError(f"ledger counts do not close for role {role}")
        for mapping_name, mapping in (
            ("known_usable_by_role", self.known_usable_by_role),
            ("known_inaccessible_by_role", self.known_inaccessible_by_role),
            ("known_discard_by_role", self.known_discard_by_role),
            ("unknown_by_role", self.unknown_by_role),
        ):
            if set(mapping) - roles:
                raise ValueError(f"{mapping_name} contains a role absent from total_by_role")
        category_counts: dict[tuple[str, str], int] = {}
        for item in self.physical_copy_receipts:
            if item.role not in roles:
                raise ValueError("physical copy role is absent from total_by_role")
            category_counts[(item.role, item.category)] = category_counts.get((item.role, item.category), 0) + 1
        expected = {
            **{(role, "PUBLIC_USABLE"): count for role, count in self.known_usable_by_role.items()},
            **{(role, "PUBLIC_INACCESSIBLE"): count for role, count in self.known_inaccessible_by_role.items()},
            **{(role, "PUBLIC_DISCARD_OR_RECOVERABLE"): count for role, count in self.known_discard_by_role.items()},
        }
        for key, count in expected.items():
            if category_counts.get(key, 0) != count:
                raise ValueError(f"physical copy receipts do not match {key[0]} {key[1]} count")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ResourceLedgerV1":
        return cls(
            total_by_role=value["total_by_role"],
            known_usable_by_role=value.get("known_usable_by_role", {}),
            known_inaccessible_by_role=value.get("known_inaccessible_by_role", {}),
            known_discard_by_role=value.get("known_discard_by_role", {}),
            unknown_by_role=value.get("unknown_by_role", {}),
            hidden_own_deck_slots=value.get("hidden_own_deck_slots", 0),
            hidden_own_prize_slots=value.get("hidden_own_prize_slots", 0),
            hidden_opponent_slots=value.get("hidden_opponent_slots", 0),
            prize_static_receipt_id=str(value["prize_static_receipt_id"]),
            physical_copy_receipts=tuple(PhysicalCopyReceiptV1(**row) for row in value.get("physical_copy_receipts", ())),
            reveal_events=tuple(RevealEventV1(**row) for row in value.get("reveal_events", ())),
        )


@dataclass(frozen=True)
class RouteRequirementV1:
    route_id: str
    reserve_requirements: Mapping[str, int]
    draw_requirements: Mapping[str, int]
    horizon: int
    objective_kind: str = "ROUTE"
    opponent_deck_count: int | None = None
    draw_obligation_known: bool = True
    recovery_known: bool = True
    alternate_prize_route_known: bool = True
    allocation_receipt_id: str | None = None
    allocation_measure_id: str | None = None
    deckout_receipt_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.route_id, str) or not self.route_id:
            raise ValueError("route_id must be nonempty")
        object.__setattr__(self, "reserve_requirements", _optional_counts(self.reserve_requirements, "reserve_requirements"))
        object.__setattr__(self, "draw_requirements", _optional_counts(self.draw_requirements, "draw_requirements"))
        _int(self.horizon, "route horizon", 1)
        if self.objective_kind not in {"ROUTE", "DECKOUT"}:
            raise ValueError("unknown route objective")
        if self.opponent_deck_count is not None:
            _int(self.opponent_deck_count, "opponent deck count")
        for name in ("draw_obligation_known", "recovery_known", "alternate_prize_route_known"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be boolean")
        for name in ("allocation_receipt_id", "allocation_measure_id", "deckout_receipt_id"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"{name} must be a nonempty string or None")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RouteRequirementV1":
        return cls(**dict(value))


@dataclass(frozen=True)
class LocalDeltaV1:
    option_fingerprint: str
    action_label: str
    consume_by_role: Mapping[str, int]
    opportunity_cost: int | float
    opportunity_cost_by_role: Mapping[str, int | float]
    exact_receipt_id: str
    probability_counts: Mapping[str, int]
    probability_horizon: int
    probability_requirements: Mapping[str, int]
    allocation_states: tuple[Mapping[str, int], ...]
    allocation_receipt_id: str

    def __post_init__(self) -> None:
        _digest(self.option_fingerprint, "local delta option fingerprint")
        if not isinstance(self.action_label, str) or not self.action_label:
            raise ValueError("local delta action_label must be nonempty")
        object.__setattr__(self, "consume_by_role", _optional_counts(self.consume_by_role, "consume_by_role"))
        object.__setattr__(self, "opportunity_cost_by_role", MappingProxyType(dict(self.opportunity_cost_by_role)))
        object.__setattr__(self, "probability_counts", _counts(self.probability_counts, "probability_counts"))
        object.__setattr__(self, "probability_requirements", _optional_counts(self.probability_requirements, "probability_requirements"))
        _int(self.probability_horizon, "probability_horizon")
        if not isinstance(self.exact_receipt_id, str) or not self.exact_receipt_id:
            raise ValueError("exact_receipt_id must be nonempty")
        if not isinstance(self.allocation_receipt_id, str) or not self.allocation_receipt_id:
            raise ValueError("allocation_receipt_id must be nonempty")
        for role, value in self.opportunity_cost_by_role.items():
            if not isinstance(role, str) or not role or isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("opportunity cost vector is malformed")
        object.__setattr__(
            self,
            "allocation_states",
            tuple(_counts(allocation, "allocation_state") for allocation in self.allocation_states),
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "LocalDeltaV1":
        return cls(
            option_fingerprint=str(value["option_fingerprint"]),
            action_label=str(value["action_label"]),
            consume_by_role=value.get("consume_by_role", {}),
            opportunity_cost=value["opportunity_cost"],
            opportunity_cost_by_role=value.get("opportunity_cost_by_role", {}),
            exact_receipt_id=str(value["exact_receipt_id"]),
            probability_counts=value["probability_counts"],
            probability_horizon=value["probability_horizon"],
            probability_requirements=value.get("probability_requirements", {}),
            allocation_states=tuple(value["allocation_states"]),
            allocation_receipt_id=str(value["allocation_receipt_id"]),
        )


@dataclass(frozen=True)
class LedgerCandidateV1:
    option: LegalOptionV1
    action_label: str
    reserve_vector: tuple[tuple[str, int], ...]
    hard_reserve_ok: bool
    probability_by_allocation: tuple[Fraction, ...]
    opportunity_cost: float
    unknown_route_out: int
    known_inaccessible_total: int

    @property
    def probability(self) -> Fraction | None:
        if not self.probability_by_allocation:
            return None
        if len(set(self.probability_by_allocation)) == 1:
            return self.probability_by_allocation[0]
        return None


@dataclass(frozen=True)
class LedgerDecisionV1:
    schema_version: int
    request_id: str
    selection_seq: int
    acting_player: int | None
    policy_id: str
    formulation_id: str
    status: str
    authority: str
    chosen_semantic_action_key: tuple[str, ...] = ()
    chosen_option_fingerprints: tuple[str, ...] = ()
    chosen_original_indices: tuple[int, ...] = ()
    decision_key: tuple[Any, ...] = ()
    candidate_count: int = 0
    fail_closed_reason: str | None = None
    candidates: tuple[LedgerCandidateV1, ...] = ()
    reserve_by_option: tuple[tuple[str, tuple[tuple[str, int], ...]], ...] = ()
    probability_by_option: tuple[tuple[str, int, int], ...] = ()
    allocation_probability_by_option: tuple[tuple[str, tuple[tuple[int, int], ...]], ...] = ()
    complete_option_set_digest: str | None = None
    receipt_scope: str = FIXTURE_ONLY
    stopped_early: bool = False
    stop_trace: CompoundActionV1 | None = None

    def __post_init__(self) -> None:
        if self.schema_version != B3_SCHEMA_VERSION:
            raise ValueError("unknown B3 decision schema")
        if self.status not in {SELECTED, B0_DELEGATE, AMBIGUOUS, TERMINAL_OVERRIDE}:
            raise ValueError("unknown B3 decision status")
        _int(self.candidate_count, "candidate_count")
        if any(isinstance(item, float) and not math.isfinite(item) for item in self.decision_key):
            raise ValueError("decision key contains nonfinite value")


@dataclass(frozen=True)
class LedgerDiagnosticsV1:
    requests: int = 0
    selected: int = 0
    delegated: int = 0
    ambiguous: int = 0
    terminal_overrides: int = 0
    stale_request_rejections: int = 0
    invalid_or_incomplete_decisions: int = 0
    fallback_actions: int = 0


@dataclass
class _MutableLedgerDiagnostics:
    requests: int = 0
    selected: int = 0
    delegated: int = 0
    ambiguous: int = 0
    terminal_overrides: int = 0
    stale_request_rejections: int = 0
    invalid_or_incomplete_decisions: int = 0
    fallback_actions: int = 0

    def snapshot(self) -> LedgerDiagnosticsV1:
        return LedgerDiagnosticsV1(**self.__dict__)


@dataclass(frozen=True)
class B3FixtureCaseV1:
    case_id: str
    state: PublicStateV1
    ledger: ResourceLedgerV1
    route: RouteRequirementV1
    local_deltas: Mapping[str, LocalDeltaV1]
    receipt: B3CapabilityReceiptV1
    expected: Mapping[str, Any]

    @property
    def observation(self) -> EngineObservationV1:
        return self.state.observation

    @property
    def request(self) -> SelectionRequestV1:
        if self.state.request is None:
            raise ValueError("fixture case requires a current request")
        return self.state.request

    @property
    def complete_option_set_digest(self) -> str:
        return stable_hash(tuple(sorted(
            (option.semantic_fingerprint, option.available)
            for option in self.request.options
        )))


@dataclass(frozen=True)
class B3FixtureBundleV1:
    config_path: Path
    receipt: B3CapabilityReceiptV1
    cases: tuple[B3FixtureCaseV1, ...]


def _entity_map(state: PublicStateV1) -> dict[str, Any]:
    return {entity.entity_key: entity for entity in state.entities}


def _player_hidden_capacity(state: PublicStateV1, player_index: int, *, own: bool) -> tuple[int, int, int]:
    players = {player.player_index: player for player in state.observation.players}
    player = players.get(player_index)
    if player is None:
        raise ValueError("PUBLIC_PLAYER_CAPACITY_MISSING")
    hidden_prizes = player.prize_count - player.visible_prize_count
    if hidden_prizes < 0:
        raise ValueError("PUBLIC_PLAYER_CAPACITY_INVALID")
    hidden_hand = 0 if own or player.hand_visible else player.hand_count
    return player.deck_count, hidden_prizes, (
        player.deck_count + hidden_prizes + hidden_hand + player.facedown_active_count
    )


def _public_lifecycle_digest(state: PublicStateV1, request: SelectionRequestV1) -> str:
    """Digest public semantics without transport order or original indices."""

    observation = state.observation
    return stable_hash({
        "observation": {
            "schema_version": observation.schema_version,
            "battle_id": observation.battle_id,
            "transition_id": observation.transition_id,
            "acting_player": observation.acting_player,
            "terminal_result": observation.terminal_result,
            "turn": observation.turn,
            "turn_action_count": observation.turn_action_count,
            "first_player": observation.first_player,
            "supporter_played": observation.supporter_played,
            "stadium_played": observation.stadium_played,
            "energy_attached": observation.energy_attached,
            "retreated": observation.retreated,
            "previous_request_ref": observation.previous_request_ref,
            "previous_action_ref": observation.previous_action_ref,
            "players": tuple(
                (item.player_index, item.bench_max, item.deck_count, item.hand_count, item.prize_count,
                 item.visible_prize_count, item.hand_visible, item.facedown_active_count)
                for item in observation.players
            ),
            "entities": tuple(sorted(
                (item.entity_key, item.card_id, item.serial, item.owner, item.zone, item.position,
                 item.parent_entity_key, item.hp, item.max_hp, item.damage, item.energy_types,
                 item.appear_this_turn, item.attached_energy_count, item.attached_tool_count, item.evolution_depth,
                 item.statuses, item.visible)
                for item in observation.entities
            )),
            "events": tuple(sorted(
                (item.event_type, item.event_name, tuple(sorted(dict(item.fields).items())))
                for item in observation.public_events
            )),
        },
        "request": {
            "schema_version": request.schema_version,
            "episode_uuid": request.episode_uuid,
            "selection_seq": request.selection_seq,
            "request_id": request.request_id,
            "acting_player": request.acting_player,
            "selection_type": request.selection_type,
            "selection_context": request.selection_context,
            "min_count": request.min_count,
            "max_count": request.max_count,
            "ordering": request.ordering,
            "remain_damage_counter": request.remain_damage_counter,
            "remain_energy_cost": request.remain_energy_cost,
            "context_card_id": request.context_card_id,
            "effect_card_id": request.effect_card_id,
            "options": tuple(sorted(
                (option.semantic_fingerprint, option.original_index, option.available, option.semantic_payload())
                for option in request.options
            )),
        },
    })


def _decision_input_digest(
    state: PublicStateV1,
    ledger: ResourceLedgerV1,
    local_deltas: Mapping[str, LocalDeltaV1],
    route: RouteRequirementV1,
    receipt: B3CapabilityReceiptV1,
    formulation_id: str,
) -> str:
    """Bind every public input and sealed local delta to request idempotency."""

    return _sha256_json({
        "state": _public_lifecycle_digest(state, state.request),
        "formulation": formulation_id,
        "route": route,
        "ledger": ledger,
        "local_deltas": tuple(
            (key, local_deltas[key]) for key in sorted(local_deltas)
        ),
        "receipt": receipt,
    })


def _deckout_predicate_digest(route: RouteRequirementV1) -> str:
    return _sha256_json({
        "schema_version": B3_SCHEMA_VERSION,
        "route_id": route.route_id,
        "opponent_deck_count": route.opponent_deck_count,
        "draw_requirements": route.draw_requirements,
        "horizon": route.horizon,
        "proof": (route.draw_obligation_known, route.recovery_known, route.alternate_prize_route_known),
    })


def exact_multivariate_probability(
    population: Mapping[str, int], *, horizon: int, requirements: Mapping[str, int]
) -> Fraction:
    """Return exact finite-population route probability, without replacement."""

    counts = _counts(population, "population")
    required = _optional_counts(requirements, "requirements")
    horizon = _int(horizon, "horizon")
    total = sum(counts.values())
    if horizon > total:
        raise ValueError("horizon exceeds finite population")
    if set(required) - set(counts):
        raise ValueError("requirement role absent from finite population")
    denominator = math.comb(total, horizon)
    if denominator <= 0:
        raise ValueError("finite population has an empty denominator")
    roles = tuple(sorted(counts))
    numerator = 0

    def visit(index: int, remaining: int, weight: int, drawn: dict[str, int]) -> None:
        nonlocal numerator
        if index == len(roles):
            if remaining != 0:
                return
            if all(drawn.get(role, 0) >= need for role, need in required.items()):
                numerator += weight
            return
        role = roles[index]
        upper = min(counts[role], remaining)
        for amount in range(upper + 1):
            drawn[role] = amount
            visit(index + 1, remaining - amount, weight * math.comb(counts[role], amount), drawn)
        drawn.pop(role, None)

    visit(0, horizon, 1, {})
    result = Fraction(numerator, denominator)
    if not 0 <= result <= 1:
        raise ValueError("finite probability is outside [0, 1]")
    return result


def semantic_permutation_suite(option_count: int, count: int = 32) -> tuple[tuple[int, ...], ...]:
    if isinstance(option_count, bool) or not isinstance(option_count, int) or option_count <= 0:
        raise ValueError("option_count must be positive")
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        raise ValueError("permutation count must be positive")
    permutations = tuple(itertools.permutations(range(option_count)))
    if not permutations:
        raise ValueError("no semantic permutations")
    return tuple(permutations[index % len(permutations)] for index in range(count))


def _config_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _validate_dependency_provenance(value: Mapping[str, Any]) -> None:
    if not isinstance(value, Mapping):
        raise ValueError("B3 receipt dependency provenance must be a mapping")
    required = {
        "schema_id", "schema_version", "fixture_metadata_sha256", "config_payload_sha256",
        "knowledge_base_sha256", "source_hashes",
    }
    if set(value) != required:
        raise ValueError("B3 receipt dependency provenance is incomplete or unknown")
    if value["schema_id"] != _PROVENANCE_SCHEMA_ID or value["schema_version"] != B3_SCHEMA_VERSION:
        raise ValueError("B3 receipt dependency schema is not version-bound")
    _digest(value["fixture_metadata_sha256"], "receipt fixture_metadata_sha256")
    _digest(value["config_payload_sha256"], "receipt config_payload_sha256")
    _digest(value["knowledge_base_sha256"], "receipt knowledge_base_sha256")
    source_hashes = value["source_hashes"]
    if not isinstance(source_hashes, Mapping) or set(source_hashes) != {str(path) for path in _PROVENANCE_SOURCE_PATHS}:
        raise ValueError("B3 receipt source dependency set is incomplete")
    for relative_path in _PROVENANCE_SOURCE_PATHS:
        actual = _file_sha256(_config_root() / relative_path, str(relative_path))
        if source_hashes[str(relative_path)] != actual:
            raise ValueError(f"B3 receipt source dependency digest mismatch: {relative_path}")
    actual_kb = _file_sha256(_config_root() / _KB_RELATIVE, str(_KB_RELATIVE))
    if value["knowledge_base_sha256"] != actual_kb:
        raise ValueError("B3 receipt knowledge-base dependency digest mismatch")


def _option_from_dict(raw: Mapping[str, Any]) -> LegalOptionV1:
    allowed = set(LegalOptionV1.__dataclass_fields__)
    if set(raw) != allowed:
        raise ValueError("B3 option fields must be complete and exact")
    option = LegalOptionV1(**dict(raw))
    if option.semantic_fingerprint != stable_hash(option.semantic_payload()):
        raise ValueError("B3 option semantic fingerprint is not canonical")
    return option


def _materialize_state(raw: Mapping[str, Any], request_raw: Mapping[str, Any]) -> PublicStateV1:
    if set(raw) != set(EngineObservationV1.__dataclass_fields__):
        raise ValueError("B3 observation fields must match EngineObservationV1 exactly")
    request = SelectionRequestV1.from_dict(request_raw)
    observation = EngineObservationV1.from_dict(raw)
    return PublicStateV1.from_engine(observation, request)


def materialize_b3_fixture_data(value: Mapping[str, Any], *, config_path: Path | None = None) -> B3FixtureBundleV1:
    allowed = {
        "schema_version", "record_id", "scope", "fixture_metadata_sha256", "provenance",
        "receipt", "common_public_state", "fixture_cases",
    }
    if not isinstance(value, Mapping) or set(value) != allowed:
        raise ValueError("B3 fixture top-level fields are incomplete or unknown")
    if value["schema_version"] != B3_SCHEMA_VERSION or value["record_id"] != _FIXTURE_RECORD_ID:
        raise ValueError("unknown B3 fixture metadata")
    if value["scope"] != FIXTURE_ONLY or not isinstance(value["fixture_metadata_sha256"], str):
        raise ValueError("B3 fixture scope or metadata is invalid")
    metadata_digest = value["fixture_metadata_sha256"]
    _digest(metadata_digest, "fixture_metadata_sha256")
    common = value["common_public_state"]
    if not isinstance(common, Mapping):
        raise ValueError("B3 common public state must be a mapping")
    raw_entities = common.get("entities")
    if not isinstance(raw_entities, list):
        raise ValueError("B3 public entities must be a list")
    for entity in raw_entities:
        if not isinstance(entity, Mapping):
            raise ValueError("B3 public entity must be a mapping")
        if entity.get("card_id") is not None:
            metadata_ref = entity.get("metadata_ref")
            expected_ref = f"card:{entity['card_id']}@{metadata_digest}"
            if metadata_ref != expected_ref:
                raise ValueError("FIXTURE_METADATA_VERSION_MISMATCH")
    provenance = value["provenance"]
    if not isinstance(provenance, Mapping):
        raise ValueError("B3 fixture provenance must be a mapping")
    expected_provenance = {
        "schema_id", "schema_version", "fixture_metadata_sha256", "source_hashes",
        "knowledge_base_sha256", "config_payload_sha256"
    }
    if set(provenance) != expected_provenance:
        raise ValueError("B3 fixture provenance fields are incomplete or unknown")
    if provenance["schema_id"] != _PROVENANCE_SCHEMA_ID or provenance["schema_version"] != B3_SCHEMA_VERSION:
        raise ValueError("B3 fixture provenance schema is not version-bound")
    _digest(provenance["fixture_metadata_sha256"], "provenance fixture_metadata_sha256")
    if provenance["fixture_metadata_sha256"] != metadata_digest:
        raise ValueError("B3 fixture provenance metadata digest mismatch")
    source_hashes = provenance["source_hashes"]
    if not isinstance(source_hashes, Mapping) or set(source_hashes) != {str(path) for path in _PROVENANCE_SOURCE_PATHS}:
        raise ValueError("B3 fixture source dependency set is incomplete")
    for relative_path in _PROVENANCE_SOURCE_PATHS:
        actual = _file_sha256(_config_root() / relative_path, str(relative_path))
        if source_hashes[str(relative_path)] != actual:
            raise ValueError(f"B3 fixture source dependency digest mismatch: {relative_path}")
    _digest(provenance["knowledge_base_sha256"], "knowledge_base_sha256")
    actual_kb = _file_sha256(_config_root() / _KB_RELATIVE, str(_KB_RELATIVE))
    if provenance["knowledge_base_sha256"] != actual_kb:
        raise ValueError("B3 knowledge-base dependency digest mismatch")
    _digest(provenance["config_payload_sha256"], "config_payload_sha256")
    actual_metadata = _sha256_json(_digest_payload(value, metadata=True))
    if metadata_digest != actual_metadata:
        raise ValueError("FIXTURE_METADATA_DIGEST_MISMATCH")
    actual_config = _sha256_json(_digest_payload(value, metadata=False))
    if provenance["config_payload_sha256"] != actual_config:
        raise ValueError("B3 fixture config dependency digest mismatch")
    receipt = B3CapabilityReceiptV1.from_dict(value["receipt"])
    if _canonical_value(receipt.dependency_provenance) != _canonical_value(provenance):
        raise ValueError("B3 receipt/config provenance mismatch")
    raw_cases = value["fixture_cases"]
    if not isinstance(raw_cases, list) or len(raw_cases) < 6:
        raise ValueError("B3 requires F01-F06 fixture cases")
    cases: list[B3FixtureCaseV1] = []
    for raw_case in raw_cases:
        if not isinstance(raw_case, Mapping):
            raise ValueError("B3 case must be a mapping")
        required = {"id", "request", "ledger", "route", "local_deltas", "expected"}
        if set(raw_case) != required:
            raise ValueError("B3 case fields are incomplete or unknown")
        raw_request = raw_case["request"]
        if not isinstance(raw_request, Mapping):
            raise ValueError("B3 request must be a mapping")
        options = raw_request.get("options")
        if not isinstance(options, list):
            raise ValueError("B3 request options must be a complete list")
        request = SelectionRequestV1(**{**dict(raw_request), "options": tuple(_option_from_dict(item) for item in options)})
        observation_raw = dict(common)
        observation_raw["battle_id"] = request.episode_uuid
        observation_raw["transition_id"] = request.selection_seq
        # A fixture may alter only the current request, never inject successor state.
        observation = EngineObservationV1.from_dict(observation_raw)
        state = PublicStateV1.from_engine(observation, request)
        ledger = ResourceLedgerV1.from_dict(raw_case["ledger"])
        route = RouteRequirementV1.from_dict(raw_case["route"])
        local_deltas = {
            str(key): LocalDeltaV1.from_dict(item) for key, item in raw_case["local_deltas"].items()
        }
        if set(local_deltas) != {option.semantic_fingerprint for option in request.options if option.available}:
            raise ValueError("B3 local deltas must cover every available legal option exactly")
        cases.append(B3FixtureCaseV1(
            case_id=str(raw_case["id"]),
            state=state,
            ledger=ledger,
            route=route,
            local_deltas=MappingProxyType(local_deltas),
            receipt=receipt,
            expected=MappingProxyType(dict(raw_case["expected"])),
        ))
    ids = [case.case_id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("B3 fixture case IDs must be unique")
    required_prefixes = {
        "B3-F01", "B3-F02", "B3-F03", "B3-F04", "B3-F05", "B3-F06"
    }
    if not required_prefixes.issubset({case.case_id.split("-", 2)[0] + "-" + case.case_id.split("-", 2)[1] for case in cases}):
        raise ValueError("B3 F01-F06 materialization is incomplete")
    return B3FixtureBundleV1(config_path or Path("<memory>"), receipt, tuple(cases))


def load_b3_fixtures(path: str | Path | None = None) -> B3FixtureBundleV1:
    config_path = Path(path) if path is not None else _config_root() / _CONFIG_RELATIVE
    with config_path.open(encoding="utf-8") as handle:
        return materialize_b3_fixture_data(json.load(handle), config_path=config_path)


def _canonical_fixture_receipt() -> B3CapabilityReceiptV1:
    """Load the sealed receipt that is allowed to activate the fixture evaluator."""

    return load_b3_fixtures().receipt


def _validate_canonical_receipt(receipt: B3CapabilityReceiptV1) -> B3CapabilityReceiptV1:
    canonical = _canonical_fixture_receipt()
    if _canonical_value(receipt.dependency_provenance) != _canonical_value(canonical.dependency_provenance):
        raise ValueError("B3 evaluator requires canonical fixture provenance")
    for field_name in (
        "receipt_id", "scope", "candidate_deck_sha256", "candidate_deck_counts",
        "local_delta_receipts", "allocation_receipts", "deckout_receipt_ids", "deckout_receipts",
    ):
        if _canonical_value(getattr(receipt, field_name)) != _canonical_value(getattr(canonical, field_name)):
            raise ValueError(f"B3 evaluator receipt field is not canonical: {field_name}")
    return canonical


def _map_key(value: str | None, owner_map: Mapping[int, int]) -> str | None:
    if value is None or not value.startswith("p") or ":" not in value:
        return value
    prefix, suffix = value.split(":", 1)
    try:
        owner = int(prefix[1:])
    except ValueError:
        return value
    return f"p{owner_map.get(owner, owner)}:{suffix}"


def _resize_mirrored_population(population: Mapping[str, int], capacity: int) -> Mapping[str, int]:
    """Keep the synthetic mirror finite while preserving its qualified roles."""

    result = dict(population)
    difference = capacity - sum(result.values())
    if difference >= 0:
        result["blank"] = result.get("blank", 0) + difference
        return result
    removable = -difference
    for role in sorted(result, reverse=True):
        if role == "blank":
            continue
        amount = min(result[role], removable)
        result[role] -= amount
        removable -= amount
        if removable == 0:
            break
    if removable:
        raise ValueError("mirror population cannot fit its public capacity")
    return result


def mirror_b3_case(case: B3FixtureCaseV1) -> B3FixtureCaseV1:
    owner_map = {0: 1, 1: 0}
    observation = case.observation
    entities = tuple(
        replace(
            entity,
            entity_key=_map_key(entity.entity_key, owner_map),
            parent_entity_key=_map_key(entity.parent_entity_key, owner_map),
            owner=owner_map[entity.owner],
        )
        for entity in observation.entities
    )
    players = tuple(
        sorted(
            (
                replace(
                    player,
                    player_index=owner_map[player.player_index],
                    hand_visible=owner_map[player.player_index] == 1,
                )
                for player in observation.players
            ),
            key=lambda item: item.player_index,
        )
    )
    mirrored_observation = replace(
        observation,
        battle_id=f"{observation.battle_id}-mirror",
        acting_player=1,
        first_player=owner_map.get(observation.first_player, observation.first_player),
        players=players,
        entities=entities,
    )
    mirrored_players = {player.player_index: player for player in mirrored_observation.players}
    mirrored_actor = mirrored_players[1]
    mirrored_opponent = mirrored_players[0]
    mirrored_deck = mirrored_actor.deck_count
    mirrored_prize = mirrored_actor.prize_count - mirrored_actor.visible_prize_count
    mirrored_opponent_hidden = (
        mirrored_opponent.deck_count
        + (0 if mirrored_opponent.hand_visible else mirrored_opponent.hand_count)
        + mirrored_opponent.prize_count
        - mirrored_opponent.visible_prize_count
        + mirrored_opponent.facedown_active_count
    )
    options: list[LegalOptionV1] = []
    new_deltas: dict[str, LocalDeltaV1] = {}
    for option in case.request.options:
        updated = replace(
            option,
            source_ref=_map_key(option.source_ref, owner_map),
            source_entity_key=_map_key(option.source_entity_key, owner_map),
            target_ref=_map_key(option.target_ref, owner_map),
            target_entity_key=_map_key(option.target_entity_key, owner_map),
        )
        updated = replace(updated, semantic_fingerprint=stable_hash(updated.semantic_payload()))
        options.append(updated)
        delta = case.local_deltas[option.semantic_fingerprint]
        new_deltas[updated.semantic_fingerprint] = replace(
            delta,
            option_fingerprint=updated.semantic_fingerprint,
            probability_counts=_resize_mirrored_population(delta.probability_counts, mirrored_deck),
            allocation_states=tuple(
                _resize_mirrored_population(population, mirrored_deck)
                for population in delta.allocation_states
            ),
        )
    request = replace(
        case.request,
        episode_uuid=mirrored_observation.battle_id,
        request_id=f"{case.request.request_id}-mirror",
        acting_player=1,
        options=tuple(options),
    )
    state = PublicStateV1.from_engine(mirrored_observation, request)
    copied_receipts = tuple(
        replace(item, physical_id=_map_key(item.physical_id, owner_map) or item.physical_id)
        for item in case.ledger.physical_copy_receipts
    )
    copied_events = tuple(
        replace(item, physical_id=_map_key(item.physical_id, owner_map) or item.physical_id)
        for item in case.ledger.reveal_events
    )
    mirrored_ledger = replace(
        case.ledger,
        hidden_own_deck_slots=mirrored_deck,
        hidden_own_prize_slots=mirrored_prize,
        hidden_opponent_slots=mirrored_opponent_hidden,
        physical_copy_receipts=copied_receipts,
        reveal_events=copied_events,
    )
    return replace(case, state=state, ledger=mirrored_ledger, local_deltas=MappingProxyType(new_deltas))


def _decision(
    status: str,
    state: PublicStateV1 | None,
    formulation_id: str,
    *,
    reason: str | None = None,
    candidates: Sequence[LedgerCandidateV1] = (),
    key: tuple[Any, ...] = (),
    chosen: LedgerCandidateV1 | None = None,
    stop_trace: CompoundActionV1 | None = None,
) -> LedgerDecisionV1:
    request = state.request if isinstance(state, PublicStateV1) else None
    return LedgerDecisionV1(
        schema_version=B3_SCHEMA_VERSION,
        request_id=request.request_id if request else "unsupported",
        selection_seq=request.selection_seq if request else (state.transition_id if state else 0),
        acting_player=request.acting_player if request else (state.acting_player if state else None),
        policy_id=CurrentResourceLedgerEvaluatorV1.policy_id,
        formulation_id=formulation_id,
        status=status,
        authority=EXPERIMENTAL_FIXTURE_AUTHORITY if status == SELECTED else "B0_CONTROL_DELEGATION",
        chosen_semantic_action_key=(chosen.action_label,) if chosen else (),
        chosen_option_fingerprints=(chosen.option.semantic_fingerprint,) if chosen else (),
        chosen_original_indices=(chosen.option.original_index,) if chosen else (),
        decision_key=key,
        candidate_count=len(candidates),
        fail_closed_reason=reason,
        candidates=tuple(candidates),
        reserve_by_option=tuple(
            (item.option.semantic_fingerprint, item.reserve_vector)
            for item in sorted(candidates, key=lambda item: (item.action_label, item.option.semantic_fingerprint))
        ),
        probability_by_option=tuple(
            (item.option.semantic_fingerprint, item.probability.numerator, item.probability.denominator)
            for item in sorted(candidates, key=lambda item: (item.action_label, item.option.semantic_fingerprint))
            if item.probability is not None
        ),
        allocation_probability_by_option=tuple(
            (
                item.option.semantic_fingerprint,
                tuple((value.numerator, value.denominator) for value in item.probability_by_allocation),
            )
            for item in sorted(candidates, key=lambda item: (item.action_label, item.option.semantic_fingerprint))
        ),
        complete_option_set_digest=(
            stable_hash(tuple(sorted((option.semantic_fingerprint, option.available) for option in request.options)))
            if request is not None else None
        ),
        receipt_scope=FIXTURE_ONLY,
        stopped_early=stop_trace.stopped_early if stop_trace else False,
        stop_trace=stop_trace,
    )


class CurrentResourceLedgerEvaluatorV1:
    """Pure public B3-A/B evaluator; fixture receipts cannot activate native use."""

    policy_id = "b3-current-public-resource-ledger-fixture-v1"

    def __init__(self, receipt: B3CapabilityReceiptV1) -> None:
        if not isinstance(receipt, B3CapabilityReceiptV1):
            raise TypeError("B3 evaluator requires a B3CapabilityReceiptV1")
        _validate_canonical_receipt(receipt)
        self.receipt = receipt
        self._last: dict[tuple[str, int, int, str], tuple[str, LedgerDecisionV1]] = {}
        self._diagnostics = _MutableLedgerDiagnostics()

    @property
    def diagnostics(self) -> LedgerDiagnosticsV1:
        return self._diagnostics.snapshot()

    def reset(self, episode_uuid: str, player_index: int, reason: str = "start") -> None:
        if not isinstance(episode_uuid, str) or player_index not in (0, 1):
            raise ValueError("invalid B3 lifecycle identity")
        if reason not in {"start", "terminal", "error", "worker_replacement", "permutation"}:
            raise ValueError("unknown B3 lifecycle reset reason")
        self._last = {
            key: value for key, value in self._last.items()
            if key[0] != episode_uuid or key[1] != player_index
        }

    def _reject(self, state: PublicStateV1 | None, formulation_id: str, reason: str, candidates: Sequence[LedgerCandidateV1] = ()) -> LedgerDecisionV1:
        self._diagnostics.delegated += 1
        if reason.startswith("STALE"):
            self._diagnostics.stale_request_rejections += 1
        if reason in {"INCOMPLETE_LEGAL_OPTIONS", "NONFINITE_OR_INVALID_LOCAL_DELTA", "PUBLIC_BOUNDARY:UNKNOWN"}:
            self._diagnostics.invalid_or_incomplete_decisions += 1
        return _decision(B0_DELEGATE, state, formulation_id, reason=reason, candidates=candidates)

    def evaluate(
        self,
        state: PublicStateV1,
        ledger: ResourceLedgerV1,
        local_deltas: Mapping[str, LocalDeltaV1],
        route: RouteRequirementV1,
        formulation_id: str = A_FORMULATION,
    ) -> LedgerDecisionV1:
        self._diagnostics.requests += 1
        if isinstance(state, PublicStateV1) and state.terminal_result is not None:
            self._diagnostics.terminal_overrides += 1
            return _decision(TERMINAL_OVERRIDE, state, formulation_id, reason="terminal checked first")
        if formulation_id not in {A_FORMULATION, B_FORMULATION}:
            return self._reject(state if isinstance(state, PublicStateV1) else None, formulation_id, "UNKNOWN_FORMULATION")
        if not isinstance(state, PublicStateV1) or not isinstance(ledger, ResourceLedgerV1) or not isinstance(route, RouteRequirementV1):
            return self._reject(None, formulation_id, "PUBLIC_STATE_LEDGER_ROUTE_REQUIRED")
        request = state.request
        if request is None:
            return self._reject(state, formulation_id, "CURRENT_REQUEST_REQUIRED")
        if not isinstance(local_deltas, Mapping) or any(
            not isinstance(key, str) or not isinstance(delta, LocalDeltaV1)
            for key, delta in local_deltas.items()
        ):
            return self._reject(state, formulation_id, "LOCAL_DELTAS_REQUIRED")
        try:
            _validate_canonical_receipt(self.receipt)
        except (OSError, ValueError):
            return self._reject(state, formulation_id, "FIXTURE_PROVENANCE_MISMATCH")
        if self.receipt.scope != FIXTURE_ONLY or self.receipt.receipt_id != _FIXTURE_RECORD_ID:
            return self._reject(state, formulation_id, "NATIVE_OR_UNKNOWN_RECEIPT_SCOPE")
        if ledger.prize_static_receipt_id not in {item.receipt_id for item in self.receipt.prize_static}:
            return self._reject(state, formulation_id, "MISSING_PRIZESTATIC")
        try:
            ledger.validate()
            PublicStateV1.from_engine(state.observation, request)
            own_deck, own_prize, _ = _player_hidden_capacity(state, request.acting_player, own=True)
            opponent = 1 - request.acting_player
            opponent_deck, _, opponent_hidden = _player_hidden_capacity(state, opponent, own=False)
            if ledger.hidden_own_deck_slots != own_deck or ledger.hidden_own_prize_slots != own_prize:
                raise ValueError("LEDGER_PUBLIC_CAPACITY_MISMATCH")
            if ledger.hidden_opponent_slots != opponent_hidden:
                raise ValueError("LEDGER_PUBLIC_CAPACITY_MISMATCH")
            entity_keys = _entity_map(state)
            for physical in ledger.physical_copy_receipts:
                if physical.physical_id.startswith("prize:"):
                    if physical.category != "PUBLIC_INACCESSIBLE":
                        raise ValueError("LEDGER_PUBLIC_COPY_MISMATCH")
                elif physical.physical_id not in entity_keys:
                    raise ValueError("LEDGER_PUBLIC_COPY_MISMATCH")
        except (PublicStateError, ValueError) as error:
            return self._reject(state, formulation_id, f"PUBLIC_BOUNDARY:{error}")
        request_key = (request.episode_uuid, request.acting_player, request.selection_seq, formulation_id)
        payload_digest = _decision_input_digest(state, ledger, local_deltas, route, self.receipt, formulation_id)
        prior = self._last.get(request_key)
        if prior is not None:
            if prior[0] == payload_digest:
                return prior[1]
            return self._reject(state, formulation_id, "STALE_OR_REUSED_REQUEST_IDENTITY")
        prior_sequences = [
            sequence for (episode, player, sequence, formulation) in self._last
            if episode == request.episode_uuid and player == request.acting_player and formulation == formulation_id
        ]
        if prior_sequences and request.selection_seq < max(prior_sequences):
            return self._reject(state, formulation_id, "STALE_SELECTION_SEQUENCE")
        if route.objective_kind == "ROUTE" and not (
            route.draw_obligation_known and route.recovery_known and route.alternate_prize_route_known
        ):
            result = self._reject(state, formulation_id, "ROUTE_PROOF_MISSING")
            self._last[request_key] = (payload_digest, result)
            return result
        if route.objective_kind == "DECKOUT" and (
            route.opponent_deck_count is None
            or route.opponent_deck_count != opponent_deck
            or route.deckout_receipt_id is None
            or route.deckout_receipt_id not in self.receipt.deckout_receipt_ids
            or not any(
                proof.receipt_id == route.deckout_receipt_id
                and proof.route_id == route.route_id
                and proof.opponent_deck_count == route.opponent_deck_count
                and proof.predicate_sha256 == _deckout_predicate_digest(route)
                for proof in self.receipt.deckout_receipts
            )
            or not (route.draw_obligation_known and route.recovery_known and route.alternate_prize_route_known)
        ):
            result = self._reject(state, formulation_id, "DECKOUT_PROOF_MISSING")
            self._last[request_key] = (payload_digest, result)
            return result
        if request.ordering != "UNORDERED" or request.max_count != 1 or request.min_count not in {0, 1}:
            result = self._reject(state, formulation_id, "UNSUPPORTED_COUNT_OR_ORDERING")
            self._last[request_key] = (payload_digest, result)
            return result
        if request.selection_type != 0 or request.selection_context != 0:
            result = self._reject(state, formulation_id, "UNSUPPORTED_REQUEST_CONTEXT")
            self._last[request_key] = (payload_digest, result)
            return result
        if any(option.option_type == 14 for option in request.options):
            result = self._reject(state, formulation_id, "STOP_OPTION_ROW_FORBIDDEN")
            self._last[request_key] = (payload_digest, result)
            return result
        fingerprints = [option.semantic_fingerprint for option in request.options]
        if len(fingerprints) != len(set(fingerprints)):
            result = self._reject(state, formulation_id, "DUPLICATE_SEMANTIC_FINGERPRINT")
            self._last[request_key] = (payload_digest, result)
            return result
        if not request.options or not any(option.available for option in request.options):
            result = self._reject(state, formulation_id, "INCOMPLETE_LEGAL_OPTIONS")
            self._last[request_key] = (payload_digest, result)
            return result
        available_fingerprints = {option.semantic_fingerprint for option in request.options if option.available}
        if set(local_deltas) != available_fingerprints:
            result = self._reject(state, formulation_id, "INCOMPLETE_LEGAL_OPTIONS")
            self._last[request_key] = (payload_digest, result)
            return result
        candidates: list[LedgerCandidateV1] = []
        for option in request.options:
            if not option.available:
                continue
            if option.option_type not in _SUPPORTED_SINGLETON_OPTIONS:
                result = self._reject(state, formulation_id, "COMPLETE_OPTION_SET_UNSUPPORTED", candidates)
                self._last[request_key] = (payload_digest, result)
                return result
            delta = local_deltas.get(option.semantic_fingerprint)
            if delta is None or delta.option_fingerprint != option.semantic_fingerprint:
                result = self._reject(state, formulation_id, "INCOMPLETE_LEGAL_OPTIONS", candidates)
                self._last[request_key] = (payload_digest, result)
                return result
            try:
                candidate = self._candidate(option, delta, ledger, route, self.receipt)
            except ValueError as error:
                result = self._reject(state, formulation_id, str(error), candidates)
                self._last[request_key] = (payload_digest, result)
                return result
            candidates.append(candidate)
        if not candidates:
            result = self._reject(state, formulation_id, "INCOMPLETE_LEGAL_OPTIONS")
            self._last[request_key] = (payload_digest, result)
            return result
        if request.min_count == 0:
            # STOP is an explicit decoder action, but never bypasses option validation.
            stop_trace = self.build_optional_stop(request)
            result = _decision(
                SELECTED, state, formulation_id, key=("STOP",), candidates=candidates, stop_trace=stop_trace
            )
            self._diagnostics.selected += 1
            self._last[request_key] = (payload_digest, result)
            return result
        feasible = [candidate for candidate in candidates if candidate.hard_reserve_ok]
        if not feasible:
            result = self._reject(state, formulation_id, "NO_HARD_RESERVE_FEASIBLE", candidates)
            self._last[request_key] = (payload_digest, result)
            return result
        if formulation_id == A_FORMULATION:
            keys = {
                candidate: (candidate.reserve_vector, -candidate.opportunity_cost)
                for candidate in feasible
            }
            best_key = max(keys.values())
            top = [candidate for candidate in feasible if keys[candidate] == best_key]
        else:
            allocations = max((len(candidate.probability_by_allocation) for candidate in feasible), default=0)
            if allocations == 0:
                result = self._reject(state, formulation_id, "MISSING_PROBABILITY_COUNTS", candidates)
                self._last[request_key] = (payload_digest, result)
                return result
            per_allocation: list[tuple[str, ...]] = []
            for index in range(allocations):
                scored = []
                for candidate in feasible:
                    if len(candidate.probability_by_allocation) != allocations:
                        result = self._reject(state, formulation_id, "HIDDEN_ALLOCATION_CHANGES_ORDERING", candidates)
                        self._last[request_key] = (payload_digest, result)
                        return result
                    scored.append((candidate.probability_by_allocation[index], -candidate.opportunity_cost, candidate))
                best = max((item[0], item[1]) for item in scored)
                top_at_state = tuple(sorted(item[2].option.semantic_fingerprint for item in scored if (item[0], item[1]) == best))
                if len(top_at_state) != 1:
                    result = self._reject(state, formulation_id, "AMBIGUOUS_NON_EQUIVALENT_TIE", candidates)
                    self._last[request_key] = (payload_digest, result)
                    return result
                per_allocation.append(top_at_state)
            if len(set(per_allocation)) != 1:
                result = self._reject(state, formulation_id, "HIDDEN_ALLOCATION_CHANGES_ORDERING", candidates)
                self._last[request_key] = (payload_digest, result)
                return result
            chosen_fingerprint = per_allocation[0][0]
            top = [
                candidate for candidate in feasible
                if candidate.option.semantic_fingerprint == chosen_fingerprint
            ]
            chosen_candidate = top[0]
            best_key = (
                tuple((value.numerator, value.denominator) for value in chosen_candidate.probability_by_allocation),
                -chosen_candidate.opportunity_cost,
            )
        if len(top) != 1:
            self._diagnostics.ambiguous += 1
            self._diagnostics.delegated += 1
            result = _decision(AMBIGUOUS, state, formulation_id, reason="AMBIGUOUS_NON_EQUIVALENT_TIE", candidates=candidates, key=best_key)
            self._last[request_key] = (payload_digest, result)
            return result
        result = _decision(SELECTED, state, formulation_id, candidates=candidates, key=best_key, chosen=top[0])
        self._diagnostics.selected += 1
        self._last[request_key] = (payload_digest, result)
        return result

    @staticmethod
    def _candidate(
        option: LegalOptionV1,
        delta: LocalDeltaV1,
        ledger: ResourceLedgerV1,
        route: RouteRequirementV1,
        receipt: B3CapabilityReceiptV1,
    ) -> LedgerCandidateV1:
        if not isinstance(delta.opportunity_cost, (int, float)) or isinstance(delta.opportunity_cost, bool) or not math.isfinite(float(delta.opportunity_cost)):
            raise ValueError("NONFINITE_OR_INVALID_LOCAL_DELTA")
        if any(not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)) for value in delta.opportunity_cost_by_role.values()):
            raise ValueError("NONFINITE_OR_INVALID_LOCAL_DELTA")
        if delta.exact_receipt_id not in receipt.local_delta_receipts:
            raise ValueError("PARTIAL_EFFECT_OR_LOCAL_DELTA")
        allocation_receipt = receipt.allocation_by_id.get(delta.allocation_receipt_id)
        if allocation_receipt is None:
            raise ValueError("UNSEALED_ALLOCATION_MEASURE")
        if route.allocation_receipt_id != delta.allocation_receipt_id:
            raise ValueError("ALLOCATION_RECEIPT_ROUTE_MISMATCH")
        if route.allocation_measure_id != allocation_receipt.measure_id:
            raise ValueError("ALLOCATION_MEASURE_ROUTE_MISMATCH")
        if delta.probability_horizon > route.horizon:
            raise ValueError("MISSING_ROUTE_HORIZON")
        if dict(delta.probability_requirements) != dict(route.draw_requirements):
            raise ValueError("MISSING_ROUTE_REQUIREMENT")
        for role, qualified in receipt.recoverable_by_role.items():
            if role not in ledger.total_by_role:
                raise ValueError("UNKNOWN_RESOURCE_ROLE")
            if qualified != ledger.known_discard_by_role.get(role, 0):
                raise ValueError("RECOVERABILITY_RECEIPT_MISMATCH")
        for role, discarded in ledger.known_discard_by_role.items():
            qualified = receipt.recoverable_by_role.get(role, 0)
            if discarded and qualified < discarded:
                raise ValueError("UNQUALIFIED_RECOVERABILITY")
            if qualified > discarded:
                raise ValueError("RECOVERABILITY_RECEIPT_MISMATCH")
        for role, consumed in delta.consume_by_role.items():
            if role not in ledger.total_by_role:
                raise ValueError("UNKNOWN_RESOURCE_ROLE")
            if consumed < 0:
                raise ValueError("NONFINITE_OR_INVALID_LOCAL_DELTA")
            recoverable = receipt.recoverable_by_role.get(role, 0)
            available = ledger.known_usable_by_role.get(role, 0) + recoverable
            if consumed > available:
                raise ValueError("IMPOSSIBLE_LOCAL_DELTA_OVERCONSUMPTION")
        reserve: list[tuple[str, int]] = []
        for role, requirement in sorted(route.reserve_requirements.items()):
            if role not in ledger.total_by_role:
                raise ValueError("UNKNOWN_RESOURCE_ROLE")
            after = (
                ledger.known_usable_by_role.get(role, 0)
                + receipt.recoverable_by_role.get(role, 0)
                - delta.consume_by_role.get(role, 0)
                - requirement
            )
            reserve.append((role, after))
        probabilities: list[Fraction] = []
        populations = delta.allocation_states
        if not populations:
            raise ValueError("UNSEALED_ALLOCATION_MEASURE")
        population_roles = set(delta.probability_counts)
        if len({_canonical_json(population) for population in populations}) != len(populations):
            raise ValueError("DUPLICATE_ALLOCATION_WORLD")
        if sum(delta.probability_counts.values()) != ledger.hidden_own_deck_slots:
            raise ValueError("ALLOCATION_CAPACITY_MISMATCH")
        for population in populations:
            if set(population) != population_roles or sum(population.values()) != ledger.hidden_own_deck_slots:
                raise ValueError("ALLOCATION_CAPACITY_MISMATCH")
        if dict(populations[0]) != dict(delta.probability_counts):
            raise ValueError("ALLOCATION_BASE_STATE_MISMATCH")
        population_digest = _allocation_population_digest(populations)
        if population_digest not in allocation_receipt.allowed_population_sha256:
            raise ValueError("UNSEALED_ALLOCATION_MEASURE")
        for population in populations:
            probabilities.append(exact_multivariate_probability(
                population,
                horizon=delta.probability_horizon,
                requirements=delta.probability_requirements,
            ))
        return LedgerCandidateV1(
            option=option,
            action_label=delta.action_label,
            reserve_vector=tuple(reserve),
            hard_reserve_ok=all(value >= 0 for _, value in reserve),
            probability_by_allocation=tuple(probabilities),
            opportunity_cost=float(delta.opportunity_cost),
            unknown_route_out=ledger.unknown_by_role.get("route_out", 0),
            known_inaccessible_total=ledger.known_inaccessible_total,
        )

    @staticmethod
    def build_optional_stop(request: SelectionRequestV1) -> CompoundActionV1:
        if request.min_count != 0 or request.max_count != 1:
            raise ValueError("B3 STOP requires a 0..1 singleton request")
        if any(option.option_type == 14 for option in request.options):
            raise ValueError("STOP is a builder token, not a LegalOptionV1 row")
        builder = CompoundActionBuilder(request)
        builder.stop()
        return builder.build()


__all__ = [
    "A_FORMULATION", "AMBIGUOUS", "AllocationReceiptV1", "B3CapabilityReceiptV1", "B3FixtureBundleV1", "B3FixtureCaseV1",
    "B3_SCHEMA_VERSION", "B0_DELEGATE", "B_FORMULATION", "DeckoutReceiptV1", "FIXTURE_ONLY", "LedgerCandidateV1",
    "LedgerDecisionV1", "LedgerDiagnosticsV1", "LocalDeltaV1", "PrizeStaticV1", "RecoverabilityReceiptV1",
    "ResourceLedgerV1", "RouteRequirementV1",
    "SELECTED", "TERMINAL_OVERRIDE", "CurrentResourceLedgerEvaluatorV1", "exact_multivariate_probability",
    "load_b3_fixtures", "materialize_b3_fixture_data", "mirror_b3_case", "semantic_permutation_suite",
]
