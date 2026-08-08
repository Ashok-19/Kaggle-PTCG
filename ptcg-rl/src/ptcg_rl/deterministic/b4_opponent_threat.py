"""Fixture-only Phase B4 public opponent-threat evaluators.

The B4 arms deliberately sit below the native adapter.  They consume a
validated :class:`PublicStateV1`, complete current legal options, and explicit
fixture receipts only.  No card prose, static-card damage, hidden identity,
response probability, engine call, or successor observation is interpreted.
The two arms are intentionally separate from the frozen B0 control: a
non-selected result is a ``B0_DELEGATE`` decision and never an adapter
fallback.
"""

from __future__ import annotations

import itertools
import json
import hashlib
import re
from dataclasses import dataclass, field as dataclass_field, fields, replace
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from ptcg_rl.g1.actions import CompoundActionBuilder
from ptcg_rl.g1.models import (
    CONTRACT_VERSION,
    CompoundActionV1,
    EngineObservationV1,
    LegalOptionV1,
    PlayerViewV1,
    SelectionRequestV1,
    VisibleEntityV1,
    stable_hash,
)
from ptcg_rl.g1.semantic import AREA, OPTION_NAMES

from .state import PublicStateError, PublicStateV1


B4_SCHEMA_VERSION = 1
FIXTURE_ONLY = "FIXTURE_ONLY"
A_FORMULATION = "B4-A-VISIBLE-THREAT-WORST-CASE"
B_FORMULATION = "B4-B-PUBLIC-THREAT-INTERVAL"
SELECTED = "SELECTED"
B0_DELEGATE = "B0_DELEGATE"
AMBIGUOUS = "AMBIGUOUS"
TERMINAL_OVERRIDE = "TERMINAL_OVERRIDE"
COMPOUND_UNSUPPORTED = "COMPOUND_UNSUPPORTED"
STOP_UNRESOLVED = "STOP_UNRESOLVED"
SUCCESSOR_VALUE_FORBIDDEN = "SUCCESSOR_VALUE_FORBIDDEN"
EXPERIMENTAL_THREAT_AUTHORITY = "EXPERIMENTAL_THREAT_STRESS"
B0_DELEGATION_AUTHORITY = "B0_CONTROL_DELEGATION"
_FIXTURE_RECORD_ID = "phase-b4-opponent-threat-fixture-v1"
_CONFIG_RELATIVE = Path("configs/deterministic/phase_b4_opponent_threat_fixture_v1.json")
_IMPLEMENTATION_PATH = Path("src/ptcg_rl/deterministic/b4_opponent_threat.py")
# These two literals are sealed by the fixture config.  The source digest
# marker is normalized before hashing so updating the seal does not create a
# recursive hash.  A stale config therefore fails closed instead of silently
# accepting changed helper code or fixture content.
B4_CANONICAL_FIXTURE_DIGEST = "a1b25ecde14b5871302fd7a82b03359b55d1f6e17b12fe5c83ffc2c830c53ac6"
B4_IMPLEMENTATION_SOURCE_SHA256 = "70c917b3aa737bfe2f97fa367a1647a78204ac1a417ee9134218180a0558fb35"
_QUALIFICATION_STATUS = frozenset({"QUALIFIED_CABT_CAPSULE", FIXTURE_ONLY, "PARTIAL", "UNKNOWN"})
_RESPONSE_CLASSES = frozenset({
    "KO_VISIBLE_ACTIVE",
    "KO_VISIBLE_BENCH",
    "REMOVE_ROUTE_SUPPORT",
    "DISRUPT_PUBLIC_RESOURCE",
    "FORCE_RETREAT_OR_SWITCH",
})
_DIGEST_FIELDS = (
    "engine_hash", "native_library_sha256", "game_wrapper_sha256", "api_wrapper_sha256",
    "sim_wrapper_sha256", "card_data_sha256", "card_table_file_sha256",
    "card_table_semantic_sha256", "candidate_deck_sha256", "anchor_deck_sha256",
)
_PROVENANCE_FIELDS = _DIGEST_FIELDS + (
    "candidate_deck_profile", "anchor_deck_profile", "scope_version", "threat_level_scale_id",
)
_FIXTURE_SEMANTICS = "FIXTURE_QUALIFIED_RESPONSE_CLASS_ONLY"
_CENSUS_CHECKS = frozenset({
    "VISIBLE_SOURCE_CENSUS", "TARGET_LEGALITY", "ENERGY_REQUIREMENTS", "STATUS_CONSTRAINTS",
})
_PUBLIC_ENERGY_TYPES = frozenset(range(12))
_PUBLIC_STATUS_CONSTRAINTS = frozenset({"NO_STATUS"})
_PUBLIC_TARGET_REQUIREMENTS = frozenset({"VISIBLE_ACTIVE", "VISIBLE_BENCH"})
_CAPABILITY_CHOICE_ROLES = frozenset({"ATTACK", "ABILITY", "RETREAT", "EVOLVE", "PLAY", "ATTACH"})
_B4_OPTION_TYPES = frozenset({8, 9})
_DEPENDENCY_PATHS = (
    _IMPLEMENTATION_PATH,
    Path("src/ptcg_rl/g1/models.py"),
    Path("src/ptcg_rl/g1/actions.py"),
    Path("src/ptcg_rl/g1/semantic.py"),
    Path("src/ptcg_rl/deterministic/state.py"),
)


def _digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a nonempty string")
    return value


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a nonnegative integer")
    return value


def _positive_int(value: Any, field: str) -> int:
    value = _nonnegative_int(value, field)
    if value == 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _optional_level(value: Any, field: str) -> int | None:
    return None if value is None else _nonnegative_int(value, field)


def _strict_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be boolean")
    return value


def _strict_tuple_strings(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        raise ValueError(f"{field} must be a sequence")
    result = tuple(value)
    if any(not isinstance(item, str) or not item for item in result):
        raise ValueError(f"{field} entries must be nonempty strings")
    return result


@dataclass(frozen=True)
class ThreatLevelScaleV1:
    """One shared, fixture-scoped lower-is-safer ordinal scale.

    Levels are ordinals only.  They never imply damage, Prize value, response
    likelihood, or a conversion to a hidden successor state.
    """

    schema_version: int
    scale_id: str
    lower_is_safer: bool
    levels: tuple[tuple[int, str], ...]
    scope: str = FIXTURE_ONLY

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int) or self.schema_version != B4_SCHEMA_VERSION:
            raise ValueError("unknown ThreatLevelScaleV1 schema")
        if not isinstance(self.scale_id, str) or not self.scale_id:
            raise ValueError("scale_id must be a nonempty string")
        if not isinstance(self.scope, str) or self.scope != FIXTURE_ONLY:
            raise ValueError("B4 fixture scale must be FIXTURE_ONLY")
        if not isinstance(self.lower_is_safer, bool) or not self.lower_is_safer:
            raise ValueError("B4 requires a lower-is-safer scale")
        if not isinstance(self.levels, tuple) or not self.levels:
            raise ValueError("ThreatLevelScaleV1 requires levels")
        normalized: list[tuple[int, str]] = []
        for row in self.levels:
            if not isinstance(row, tuple) or len(row) != 2:
                raise ValueError("ThreatLevelScaleV1 level rows must be 2-tuples")
            level, label = row
            if isinstance(level, bool) or not isinstance(level, int):
                raise ValueError("ThreatLevelScaleV1 ordinals must be integers")
            if not isinstance(label, str) or not label:
                raise ValueError("ThreatLevelScaleV1 labels must be nonempty strings")
            normalized.append((level, label))
        numbers = tuple(level for level, _ in normalized)
        if numbers != tuple(range(len(numbers))):
            raise ValueError("ThreatLevelScaleV1 levels must start at zero and be contiguous")
        if len({label for _, label in normalized}) != len(normalized):
            raise ValueError("ThreatLevelScaleV1 labels must be unique")
        expected_labels = ("NO_QUALIFIED_RESPONSE", "LOW", "MEDIUM", "HIGH")
        if tuple(label for _, label in normalized) != expected_labels:
            raise ValueError("ThreatLevelScaleV1 labels do not match the sealed fixture semantics")

    @property
    def maximum_level(self) -> int:
        return len(self.levels) - 1

    def validate_level(self, value: int, field: str = "threat_level") -> int:
        value = _nonnegative_int(value, field)
        if value > self.maximum_level:
            raise ValueError(f"{field} is outside ThreatLevelScaleV1")
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ThreatLevelScaleV1":
        if not isinstance(value, Mapping):
            raise ValueError("ThreatLevelScaleV1 config must be a mapping")
        required = {"schema_version", "scale_id", "lower_is_safer", "levels", "scope"}
        if set(value) != required:
            raise ValueError("ThreatLevelScaleV1 config fields are incomplete or unknown")
        _strict_bool(value["lower_is_safer"], "lower_is_safer")
        if isinstance(value["schema_version"], bool) or not isinstance(value["schema_version"], int):
            raise ValueError("schema_version must be an integer")
        if not isinstance(value["scale_id"], str) or not value["scale_id"]:
            raise ValueError("scale_id must be a nonempty string")
        if not isinstance(value["scope"], str):
            raise ValueError("scope must be a string")
        rows = value["levels"]
        if not isinstance(rows, (tuple, list)):
            raise ValueError("levels must be a sequence")
        normalized_rows: list[tuple[int, str]] = []
        for row in rows:
            if not isinstance(row, (tuple, list)) or len(row) != 2:
                raise ValueError("level rows must have exactly two fields")
            level, label = row
            if isinstance(level, bool) or not isinstance(level, int):
                raise ValueError("level ordinal must be an integer")
            if not isinstance(label, str):
                raise ValueError("level label must be a string")
            normalized_rows.append((level, label))
        return cls(
            schema_version=value["schema_version"],
            scale_id=value["scale_id"],
            lower_is_safer=value["lower_is_safer"],
            levels=tuple(normalized_rows),
            scope=value["scope"],
        )


@dataclass(frozen=True)
class VisibleThreatCapabilityV1:
    """A complete fixture receipt for one visible response capability."""

    capability_id: str
    response_class: str
    source_kind: str
    source_entity_key: str | None
    target_entity_key: str | None
    source_card_id: int
    attack_id: int | None
    effect_id: int | None
    qualification_id: str
    qualification_status: str
    energy_requirements: tuple[int, ...]
    status_constraints: tuple[str, ...]
    target_requirements: tuple[str, ...]
    choice_role: str
    damage_or_effect_semantics: str
    engine_hash: str
    native_library_sha256: str
    game_wrapper_sha256: str
    api_wrapper_sha256: str
    sim_wrapper_sha256: str
    card_data_sha256: str
    card_table_file_sha256: str
    card_table_semantic_sha256: str
    candidate_deck_profile: str
    candidate_deck_sha256: str
    anchor_deck_profile: str
    anchor_deck_sha256: str
    scope_version: str
    threat_level_scale_id: str
    local_delta_receipt_id: str
    ready_now: bool | None
    energy_deficit: int | None
    threat_level: int | None
    guaranteed_level: int | None
    possible_level: int | None
    content_sha256: str
    # The semantic references above are not enough by themselves to prove
    # that a capability belongs to the public snapshot that authorized it.
    # These fields are a sealed copy of every public identity/value used by
    # the evaluator.  They are populated by the fixture builder and checked
    # against the current PublicStateV1 before any threat is ranked.
    target_card_id: int | None = None
    source_serial: int | None = None
    target_serial: int | None = None
    source_owner: int | None = None
    target_owner: int | None = None
    source_zone: int | None = None
    target_zone: int | None = None
    source_position: int | None = None
    target_position: int | None = None
    source_hp: int | None = None
    source_max_hp: int | None = None
    target_hp: int | None = None
    target_max_hp: int | None = None
    unknown_fields: tuple[str, ...] = ()
    scope: str = FIXTURE_ONLY

    def __post_init__(self) -> None:
        _nonempty(self.capability_id, "capability_id")
        if self.response_class not in _RESPONSE_CLASSES:
            raise ValueError("unknown visible-threat response class")
        if self.source_kind != "ENTITY":
            raise ValueError("fixture threat source must be a visible entity")
        if not isinstance(self.source_entity_key, str) or not self.source_entity_key:
            raise ValueError("source_entity_key must be a nonempty string")
        if not isinstance(self.target_entity_key, str) or not self.target_entity_key:
            raise ValueError("target_entity_key must be a nonempty string")
        _positive_int(self.source_card_id, "source_card_id")
        if (self.attack_id is None) == (self.effect_id is None):
            raise ValueError("exactly one attack_id or effect_id is required")
        if self.attack_id is not None:
            _positive_int(self.attack_id, "attack_id")
        if self.effect_id is not None:
            _positive_int(self.effect_id, "effect_id")
        _nonempty(self.qualification_id, "qualification_id")
        if self.qualification_status not in _QUALIFICATION_STATUS:
            raise ValueError("unknown threat qualification status")
        if self.choice_role not in _CAPABILITY_CHOICE_ROLES:
            raise ValueError("unknown capability choice role")
        if not isinstance(self.scope, str) or self.scope != FIXTURE_ONLY:
            raise ValueError("B4 capabilities are fixture-only")
        if not isinstance(self.energy_requirements, tuple):
            raise ValueError("energy_requirements must be an immutable tuple")
        if not isinstance(self.status_constraints, tuple) or not isinstance(self.target_requirements, tuple):
            raise ValueError("threat constraints must be immutable tuples")
        if not isinstance(self.unknown_fields, tuple):
            raise ValueError("unknown_fields must be an immutable tuple")
        for value in self.energy_requirements:
            if _nonnegative_int(value, "energy_requirements") not in _PUBLIC_ENERGY_TYPES:
                raise ValueError("energy requirement is outside the public enum")
        if any(value not in _PUBLIC_STATUS_CONSTRAINTS for value in self.status_constraints):
            raise ValueError("unknown public status constraint")
        if any(value not in _PUBLIC_TARGET_REQUIREMENTS for value in self.target_requirements):
            raise ValueError("unknown public target requirement")
        if any(not isinstance(value, str) or not value for value in (*self.status_constraints, *self.target_requirements)):
            raise ValueError("threat constraints must be nonempty strings")
        _nonempty(self.damage_or_effect_semantics, "damage_or_effect_semantics")
        _digest(self.content_sha256, "content_sha256")
        for field in (
            "source_serial", "target_serial", "source_hp", "source_max_hp",
            "target_hp", "target_max_hp", "target_card_id",
        ):
            value = getattr(self, field)
            if value is not None:
                _positive_int(value, field)
        for field in ("source_owner", "target_owner"):
            value = getattr(self, field)
            if value is not None and (isinstance(value, bool) or value not in (0, 1)):
                raise ValueError(f"{field} must be player 0 or 1")
        for field in ("source_zone", "target_zone", "source_position", "target_position"):
            value = getattr(self, field)
            if value is not None:
                _nonnegative_int(value, field)
        for field in _DIGEST_FIELDS:
            _digest(getattr(self, field), field)
        _nonempty(self.candidate_deck_profile, "candidate_deck_profile")
        _nonempty(self.anchor_deck_profile, "anchor_deck_profile")
        _nonempty(self.scope_version, "scope_version")
        _nonempty(self.threat_level_scale_id, "threat_level_scale_id")
        _nonempty(self.local_delta_receipt_id, "local_delta_receipt_id")
        if self.ready_now is not None and not isinstance(self.ready_now, bool):
            raise ValueError("ready_now must be bool or None")
        if self.energy_deficit is not None:
            _nonnegative_int(self.energy_deficit, "energy_deficit")
        for field in ("threat_level", "guaranteed_level", "possible_level"):
            _optional_level(getattr(self, field), field)
        if self.guaranteed_level is not None and self.possible_level is not None and self.guaranteed_level > self.possible_level:
            raise ValueError("guaranteed threat level exceeds possible level")
        if any(not isinstance(value, str) or not value for value in self.unknown_fields):
            raise ValueError("unknown threat fields must be named")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "VisibleThreatCapabilityV1":
        if not isinstance(value, Mapping):
            raise ValueError("capability config must be a mapping")
        if set(value) != {item.name for item in fields(cls)}:
            raise ValueError("capability config fields are incomplete or unknown")
        return cls(
            **{
                **dict(value),
                "energy_requirements": tuple(value.get("energy_requirements", ())),
                "status_constraints": tuple(value.get("status_constraints", ())),
                "target_requirements": tuple(value.get("target_requirements", ())),
                "unknown_fields": tuple(value.get("unknown_fields", ())),
            }
        )


@dataclass(frozen=True)
class PublicCensusReceiptV1:
    """Receipt proving that a no-response result covered this exact snapshot."""

    receipt_id: str
    observation_hash: str
    source_scope: tuple[str, ...]
    target_scope: tuple[str, ...]
    checks: tuple[str, ...]
    local_delta_receipt_id: str
    scope: str = FIXTURE_ONLY

    def __post_init__(self) -> None:
        _nonempty(self.receipt_id, "census receipt_id")
        _digest(self.observation_hash, "census observation_hash")
        _strict_tuple_strings(self.source_scope, "census source_scope")
        _strict_tuple_strings(self.target_scope, "census target_scope")
        _strict_tuple_strings(self.checks, "census checks")
        if not _CENSUS_CHECKS.issubset(self.checks):
            raise ValueError("public census receipt omits a required current-state check")
        _nonempty(self.local_delta_receipt_id, "census local_delta_receipt_id")
        if self.scope != FIXTURE_ONLY:
            raise ValueError("B4 census receipts are fixture-only")


@dataclass(frozen=True)
class ThreatLocalDeltaV1:
    """Exact current-only receipt attached to one legal option."""

    option_fingerprint: str
    receipt_id: str
    qualification_status: str
    current_public_fields: tuple[str, ...]
    remaining_capability_ids: tuple[str, ...]
    action_key: str
    content_sha256: str
    action_eligible: bool = True
    census_complete: bool = False
    census_receipt_id: str | None = None
    unknown_fields: tuple[str, ...] = ()
    successor_fields: tuple[str, ...] = ()
    scope: str = FIXTURE_ONLY

    def __post_init__(self) -> None:
        _digest(self.option_fingerprint, "option_fingerprint")
        _nonempty(self.receipt_id, "receipt_id")
        if self.qualification_status not in _QUALIFICATION_STATUS:
            raise ValueError("unknown local-delta qualification status")
        if self.scope != FIXTURE_ONLY:
            raise ValueError("B4 local deltas are fixture-only")
        if not isinstance(self.current_public_fields, tuple) or not self.current_public_fields:
            raise ValueError("local delta must name current public fields")
        if not isinstance(self.remaining_capability_ids, tuple) or not isinstance(self.unknown_fields, tuple) or not isinstance(self.successor_fields, tuple):
            raise ValueError("local-delta identifier fields must be immutable tuples")
        for field in (*self.current_public_fields, *self.unknown_fields, *self.successor_fields):
            if not isinstance(field, str) or not field:
                raise ValueError("local-delta field names must be nonempty")
        if any(token in field.lower() for field in self.current_public_fields for token in ("post_action", "successor", "future", "terminal", "opponent_hand", "opponent_deck", "opponent_prize", "hidden", "private", "probability")):
            raise ValueError("local delta carries successor or hidden-only fields")
        if any(not isinstance(value, str) or not value for value in self.remaining_capability_ids):
            raise ValueError("remaining capability identifiers must be nonempty")
        if len(set(self.remaining_capability_ids)) != len(self.remaining_capability_ids):
            raise ValueError("remaining capability identifiers must be unique")
        _nonempty(self.action_key, "action_key")
        _digest(self.content_sha256, "content_sha256")
        if not isinstance(self.action_eligible, bool) or not isinstance(self.census_complete, bool):
            raise ValueError("local-delta booleans must be bool")
        if self.census_receipt_id is not None:
            _nonempty(self.census_receipt_id, "census_receipt_id")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ThreatLocalDeltaV1":
        if not isinstance(value, Mapping) or set(value) != {item.name for item in fields(cls)}:
            raise ValueError("local-delta config fields are incomplete or unknown")
        return cls(
            **{
                **dict(value),
                "current_public_fields": tuple(value.get("current_public_fields", ())),
                "remaining_capability_ids": tuple(value.get("remaining_capability_ids", ())),
                "unknown_fields": tuple(value.get("unknown_fields", ())),
                "successor_fields": tuple(value.get("successor_fields", ())),
            }
        )


@dataclass(frozen=True)
class B4CapabilityReceiptV1:
    receipt_id: str
    scope: str
    fixture_case_id: str
    threat_level_scale: ThreatLevelScaleV1
    capabilities: tuple[VisibleThreatCapabilityV1, ...]
    local_delta_receipt_ids: tuple[str, ...]
    local_delta_content_sha256: Mapping[str, str]
    canonical_case_sha256: str
    provenance_manifest: Mapping[str, str] = dataclass_field(default_factory=dict)
    census_receipts: tuple[PublicCensusReceiptV1, ...] = ()

    def __post_init__(self) -> None:
        if self.receipt_id != _FIXTURE_RECORD_ID:
            raise ValueError("unknown B4 fixture receipt")
        if self.scope != FIXTURE_ONLY:
            raise ValueError("B4 accepts fixture-only receipts only")
        _nonempty(self.fixture_case_id, "fixture_case_id")
        if not isinstance(self.threat_level_scale, ThreatLevelScaleV1):
            raise ValueError("B4 receipt requires ThreatLevelScaleV1")
        if not isinstance(self.capabilities, tuple) or any(not isinstance(item, VisibleThreatCapabilityV1) for item in self.capabilities):
            raise ValueError("B4 receipt capabilities must be immutable typed rows")
        if len({item.capability_id for item in self.capabilities}) != len(self.capabilities):
            raise ValueError("duplicate visible-threat capability")
        if any(item.threat_level_scale_id != self.threat_level_scale.scale_id for item in self.capabilities):
            raise ValueError("capability uses a different ThreatLevelScaleV1")
        if not isinstance(self.local_delta_receipt_ids, tuple) or any(not isinstance(item, str) or not item for item in self.local_delta_receipt_ids):
            raise ValueError("B4 local-delta receipt ids must be nonempty strings")
        if not self.local_delta_receipt_ids or len(set(self.local_delta_receipt_ids)) != len(self.local_delta_receipt_ids):
            raise ValueError("B4 local-delta receipts must be unique and nonempty")
        if not isinstance(self.local_delta_content_sha256, Mapping):
            raise ValueError("B4 receipt requires local-delta content digests")
        for key, value in self.local_delta_content_sha256.items():
            _nonempty(key, "local_delta_content_sha256 key")
            _digest(value, f"local_delta_content_sha256.{key}")
        _digest(self.canonical_case_sha256, "canonical_case_sha256")
        if not isinstance(self.provenance_manifest, Mapping):
            raise ValueError("B4 receipt requires an immutable provenance manifest")
        if set(self.provenance_manifest) != set(_PROVENANCE_FIELDS):
            raise ValueError("B4 provenance manifest fields are incomplete or unknown")
        for field in _DIGEST_FIELDS:
            _digest(self.provenance_manifest[field], f"provenance_manifest.{field}")
        for field in ("candidate_deck_profile", "anchor_deck_profile", "scope_version"):
            _nonempty(self.provenance_manifest[field], f"provenance_manifest.{field}")
        if self.provenance_manifest["threat_level_scale_id"] != self.threat_level_scale.scale_id:
            raise ValueError("provenance manifest uses a different ThreatLevelScaleV1")
        object.__setattr__(self, "provenance_manifest", MappingProxyType(dict(self.provenance_manifest)))
        object.__setattr__(self, "local_delta_content_sha256", MappingProxyType(dict(self.local_delta_content_sha256)))
        if not isinstance(self.census_receipts, tuple):
            raise ValueError("census receipts must be immutable")
        if any(not isinstance(item, PublicCensusReceiptV1) for item in self.census_receipts):
            raise ValueError("invalid public census receipt")
        census_ids = tuple(item.receipt_id for item in self.census_receipts)
        if len(set(census_ids)) != len(census_ids):
            raise ValueError("duplicate public census receipt")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "B4CapabilityReceiptV1":
        if not isinstance(value, Mapping) or set(value) != {item.name for item in fields(cls)}:
            raise ValueError("B4 receipt config must be a mapping")
        scale = ThreatLevelScaleV1.from_dict(value["threat_level_scale"])
        return cls(
            receipt_id=value["receipt_id"],
            scope=value["scope"],
            fixture_case_id=value["fixture_case_id"],
            threat_level_scale=scale,
            capabilities=tuple(VisibleThreatCapabilityV1.from_dict(item) for item in value.get("capabilities", ())),
            local_delta_receipt_ids=tuple(value["local_delta_receipt_ids"]),
            local_delta_content_sha256=dict(value["local_delta_content_sha256"]),
            canonical_case_sha256=value["canonical_case_sha256"],
            provenance_manifest=dict(value["provenance_manifest"]),
            census_receipts=tuple(
                PublicCensusReceiptV1(
                    receipt_id=item["receipt_id"],
                    observation_hash=item["observation_hash"],
                    source_scope=tuple(item["source_scope"]),
                    target_scope=tuple(item["target_scope"]),
                    checks=tuple(item["checks"]),
                    local_delta_receipt_id=item["local_delta_receipt_id"],
                    scope=item["scope"],
                )
                for item in value.get("census_receipts", ())
            ),
        )


@dataclass(frozen=True)
class ThreatCandidateV1:
    option: LegalOptionV1
    action_key: str
    guaranteed_level: int
    possible_level: int
    interval_width: Fraction
    unknown_count: int
    response_count: int
    route_support_denial_count: int
    ready_capability_count: int
    capability_ids: tuple[str, ...]


@dataclass(frozen=True)
class ThreatDecisionV1:
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
    candidates: tuple[ThreatCandidateV1, ...] = ()
    interval_by_option: tuple[tuple[str, tuple[int, int]], ...] = ()
    receipt_scope: str = FIXTURE_ONLY
    action: CompoundActionV1 | None = None
    stopped_early: bool = False
    successor_reads: int = 0

    def __post_init__(self) -> None:
        if self.schema_version != B4_SCHEMA_VERSION:
            raise ValueError("unknown B4 decision schema")
        if self.status not in {SELECTED, B0_DELEGATE, AMBIGUOUS, TERMINAL_OVERRIDE}:
            raise ValueError("unknown B4 decision status")
        if self.receipt_scope != FIXTURE_ONLY:
            raise ValueError("B4 decision scope must be fixture-only")
        if self.successor_reads != 0:
            raise ValueError("B4 decisions may not read successors")
        if any(len(interval) != 2 or interval[0] < 0 or interval[1] < interval[0] for _, interval in self.interval_by_option):
            raise ValueError("B4 decision intervals are invalid")

    @property
    def interval_map(self) -> Mapping[str, tuple[int, int]]:
        return MappingProxyType(dict(self.interval_by_option))

    @property
    def stop_trace(self) -> CompoundActionV1 | None:
        """Compatibility view for callers that name the explicit STOP trace."""

        return self.action if self.stopped_early else None


@dataclass(frozen=True)
class B4FixtureCaseV1:
    case_id: str
    observation: EngineObservationV1
    request: SelectionRequestV1
    state: PublicStateV1
    receipt: B4CapabilityReceiptV1
    capabilities: tuple[VisibleThreatCapabilityV1, ...]
    local_deltas: Mapping[str, ThreatLocalDeltaV1]
    expected: Mapping[str, str]
    successor_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class B4FixtureBundleV1:
    config_path: Path
    receipt: B4CapabilityReceiptV1
    cases: tuple[B4FixtureCaseV1, ...]


@dataclass
class _Diagnostics:
    requests: int = 0
    selected: int = 0
    delegated: int = 0
    terminal_overrides: int = 0
    stale_rejections: int = 0
    hidden_boundary_rejections: int = 0


def _sha_fixture() -> str:
    return "f" * 64


def _fixture_provenance(scale_id: str = "fixture-threat-level-scale-v1") -> Mapping[str, str]:
    digest = _sha_fixture()
    return MappingProxyType({
        "engine_hash": digest,
        "native_library_sha256": digest,
        "game_wrapper_sha256": digest,
        "api_wrapper_sha256": digest,
        "sim_wrapper_sha256": digest,
        "card_data_sha256": digest,
        "card_table_file_sha256": digest,
        "card_table_semantic_sha256": digest,
        "candidate_deck_profile": "fixture-candidate",
        "candidate_deck_sha256": digest,
        "anchor_deck_profile": "fixture-anchor",
        "anchor_deck_sha256": digest,
        "scope_version": "fixture-scope-v1",
        "threat_level_scale_id": scale_id,
    })


def _entity(owner: int, serial: int, card_id: int, zone: int, position: int, *, hp: int | None = None) -> VisibleEntityV1:
    return VisibleEntityV1(
        entity_key=f"p{owner}:s{serial}",
        card_id=card_id,
        serial=serial,
        metadata_ref=f"card:{card_id}@{_sha_fixture()}",
        owner=owner,
        zone=zone,
        position=position,
        hp=hp,
        max_hp=hp,
        damage=0 if hp is not None else None,
        appear_this_turn=False,
        energy_types=(),
        attached_energy_count=0,
        attached_tool_count=0,
        evolution_depth=0,
        statuses=(),
        visible=True,
    )


def _public_observation(battle_id: str, *, actor: int = 0, transition: int = 7) -> EngineObservationV1:
    return EngineObservationV1(
        schema_version=CONTRACT_VERSION,
        battle_id=battle_id,
        transition_id=transition,
        acting_player=actor,
        terminal_result=None,
        turn=4,
        turn_action_count=1,
        first_player=0,
        supporter_played=False,
        stadium_played=False,
        energy_attached=False,
        retreated=False,
        players=(
            PlayerViewV1(0, 5, 10, 3, 6, 0, actor == 0, 0),
            PlayerViewV1(1, 5, 10, 3, 6, 0, actor == 1, 0),
        ),
        entities=(
            _entity(0, 1, 900, AREA["HAND"], 0),
            _entity(0, 10, 901, AREA["ACTIVE"], 0, hp=120),
            _entity(0, 11, 902, AREA["BENCH"], 0, hp=100),
            _entity(1, 50, 100, AREA["ACTIVE"], 0, hp=150),
            _entity(1, 51, 101, AREA["BENCH"], 0, hp=100),
        ),
        public_events=(),
    )


def _option(index: int, target_serial: int, *, actor: int = 0, option_type: int = 8) -> LegalOptionV1:
    source = f"p{actor}:s1"
    target = f"p{actor}:s{target_serial}"
    option = LegalOptionV1(
        schema_version=CONTRACT_VERSION,
        original_index=index,
        selection_type=0,
        selection_context=0,
        option_type=option_type,
        option_name=OPTION_NAMES[option_type],
        area=AREA["HAND"],
        index=0,
        player_index=None,
        tool_index=None,
        energy_index=None,
        count=None,
        in_play_area=AREA["ACTIVE"] if target_serial == 10 else AREA["BENCH"],
        in_play_index=0,
        attack_id=None,
        card_id=None,
        serial=None,
        special_condition_type=None,
        source_kind="ENTITY",
        source_ref=source,
        target_kind="ENTITY",
        target_ref=target,
        choice_role=OPTION_NAMES[option_type],
        source_entity_key=source,
        target_entity_key=target,
        available=True,
        semantic_fingerprint="",
    )
    return replace(option, semantic_fingerprint=stable_hash(option.semantic_payload()))


def _skill_option(index: int) -> LegalOptionV1:
    option = LegalOptionV1(
        schema_version=CONTRACT_VERSION,
        original_index=index,
        selection_type=5,
        selection_context=34,
        option_type=15,
        option_name="SKILL",
        source_kind="NONE",
        target_kind="NONE",
        choice_role="SKILL",
        available=True,
        semantic_fingerprint="",
    )
    return replace(option, semantic_fingerprint=stable_hash(option.semantic_payload()))


def _request(case_id: str, options: Sequence[LegalOptionV1], *, min_count: int = 1, max_count: int = 1, actor: int = 0, ordering: str = "UNORDERED", selection_type: int = 0, selection_context: int = 0) -> SelectionRequestV1:
    return SelectionRequestV1(
        schema_version=CONTRACT_VERSION,
        episode_uuid=case_id,
        selection_seq=7,
        request_id=f"{case_id}-r7",
        acting_player=actor,
        selection_type=selection_type,
        selection_context=selection_context,
        min_count=min_count,
        max_count=max_count,
        remain_damage_counter=None,
        remain_energy_cost=None,
        context_card_id=None,
        effect_card_id=None,
        ordering=ordering,
        options=tuple(options),
    )


def _capability(capability_id: str, *, level: int, ready: bool, lower: int | None, upper: int | None, delta_id: str, unknown: tuple[str, ...] = (), target_entity_key: str = "p0:s10", target_requirement: str = "VISIBLE_ACTIVE") -> VisibleThreatCapabilityV1:
    digest = _sha_fixture()
    return VisibleThreatCapabilityV1(
        capability_id=capability_id,
        response_class="KO_VISIBLE_ACTIVE",
        source_kind="ENTITY",
        source_entity_key="p1:s50",
        target_entity_key=target_entity_key,
        source_card_id=100,
        attack_id=1001,
        effect_id=None,
        qualification_id=f"fixture-capability-{capability_id}",
        qualification_status=FIXTURE_ONLY,
        energy_requirements=(1,),
        status_constraints=("NO_STATUS",),
        target_requirements=(target_requirement,),
        choice_role="ATTACK",
        damage_or_effect_semantics="FIXTURE_QUALIFIED_RESPONSE_CLASS_ONLY",
        engine_hash=digest,
        native_library_sha256=digest,
        game_wrapper_sha256=digest,
        api_wrapper_sha256=digest,
        sim_wrapper_sha256=digest,
        card_data_sha256=digest,
        card_table_file_sha256=digest,
        card_table_semantic_sha256=digest,
        candidate_deck_profile="fixture-candidate",
        candidate_deck_sha256=digest,
        anchor_deck_profile="fixture-anchor",
        anchor_deck_sha256=digest,
        scope_version="fixture-scope-v1",
        threat_level_scale_id="fixture-threat-level-scale-v1",
        local_delta_receipt_id=delta_id,
        ready_now=ready,
        energy_deficit=0 if ready else 1,
        threat_level=level,
        guaranteed_level=lower,
        possible_level=upper,
        content_sha256=digest,
        unknown_fields=unknown,
    )


def _delta(option: LegalOptionV1, capability_ids: Sequence[str], action_key: str, *, action_eligible: bool = True, census_complete: bool = False) -> ThreatLocalDeltaV1:
    return ThreatLocalDeltaV1(
        option_fingerprint=option.semantic_fingerprint,
        receipt_id=f"fixture-local-delta-{action_key}",
        qualification_status=FIXTURE_ONLY,
        current_public_fields=("current_source", "current_target", "current_legality"),
        remaining_capability_ids=tuple(capability_ids),
        action_key=action_key,
        content_sha256=_sha_fixture(),
        action_eligible=action_eligible,
        census_complete=census_complete,
    )


def _bind_capability_public_fields(
    capability: VisibleThreatCapabilityV1, state: PublicStateV1
) -> VisibleThreatCapabilityV1:
    """Copy the exact public identity/value tuple into a capability receipt."""

    entities = {entity.entity_key: entity for entity in state.entities}
    source = entities.get(capability.source_entity_key)
    target = entities.get(capability.target_entity_key)
    if source is None or target is None:
        raise ValueError("capability references an entity outside the public fixture")
    if any(value is None for value in (source.card_id, source.serial, target.card_id, target.serial)):
        raise ValueError("capability fixture entities must be fully visible")
    return replace(
        capability,
        source_card_id=source.card_id,
        target_card_id=target.card_id,
        source_serial=source.serial,
        target_serial=target.serial,
        source_owner=source.owner,
        target_owner=target.owner,
        source_zone=source.zone,
        target_zone=target.zone,
        source_position=source.position,
        target_position=target.position,
        source_hp=source.hp,
        source_max_hp=source.max_hp,
        target_hp=target.hp,
        target_max_hp=target.max_hp,
    )


def _case(case_id: str, options: Sequence[LegalOptionV1], capabilities: Sequence[VisibleThreatCapabilityV1], deltas: Mapping[str, ThreatLocalDeltaV1], *, min_count: int = 1, max_count: int = 1, ordering: str = "UNORDERED", successor_fields: tuple[str, ...] = (), selection_type: int = 0, selection_context: int = 0) -> B4FixtureCaseV1:
    request = _request(case_id, options, min_count=min_count, max_count=max_count, ordering=ordering, selection_type=selection_type, selection_context=selection_context)
    observation = _public_observation(case_id)
    state = PublicStateV1.from_engine(observation, request)
    scale = ThreatLevelScaleV1(
        schema_version=B4_SCHEMA_VERSION,
        scale_id="fixture-threat-level-scale-v1",
        lower_is_safer=True,
        levels=((0, "NO_QUALIFIED_RESPONSE"), (1, "LOW"), (2, "MEDIUM"), (3, "HIGH")),
    )
    # The builder assigns each capability to the one delta that names it.  A
    # capability cannot carry an unrelated or stale receipt id merely because
    # a neighboring fixture happened to reuse the same semantic row.
    bound_deltas = {key: _seal_delta(delta) for key, delta in deltas.items()}
    bound_capabilities = []
    for capability in capabilities:
        referenced = [delta.receipt_id for delta in bound_deltas.values() if capability.capability_id in delta.remaining_capability_ids]
        if len(referenced) == 1 and capability.local_delta_receipt_id != referenced[0]:
            capability = replace(capability, local_delta_receipt_id=referenced[0])
        bound_capabilities.append(_bind_capability_public_fields(capability, state))
    bound_capabilities_tuple = tuple(_seal_capability(item) for item in bound_capabilities)
    receipt = B4CapabilityReceiptV1(
        receipt_id=_FIXTURE_RECORD_ID,
        scope=FIXTURE_ONLY,
        fixture_case_id=case_id,
        threat_level_scale=scale,
        capabilities=bound_capabilities_tuple,
        local_delta_receipt_ids=tuple(delta.receipt_id for delta in bound_deltas.values()),
        local_delta_content_sha256={
            delta.receipt_id: _delta_content_digest(delta) for delta in bound_deltas.values()
        },
        canonical_case_sha256="0" * 64,
        provenance_manifest=_fixture_provenance(scale.scale_id),
    )
    return B4FixtureCaseV1(
        case_id=case_id,
        observation=observation,
        request=request,
        state=state,
        receipt=receipt,
        capabilities=bound_capabilities_tuple,
        local_deltas=MappingProxyType(bound_deltas),
        expected={},
        successor_fields=successor_fields,
    )


def _build_cases() -> tuple[B4FixtureCaseV1, ...]:
    x = _option(0, 10)
    y = _option(1, 11)
    cap_x = _capability("cap-x", level=3, ready=False, lower=0, upper=3, delta_id="fixture-local-delta-B4-F01-X")
    cap_y = _capability("cap-y", level=1, ready=True, lower=1, upper=1, delta_id="fixture-local-delta-B4-F01-Y", target_entity_key="p0:s11", target_requirement="VISIBLE_BENCH")
    f01 = _case(
        "B4-F01-FORMULATION-DIVERGENCE",
        (x, y),
        (cap_x, cap_y),
        {x.semantic_fingerprint: _delta(x, ("cap-x",), "B4-F01-X"), y.semantic_fingerprint: _delta(y, ("cap-y",), "B4-F01-Y")},
    )

    unknown = _capability("cap-f02", level=2, ready=False, lower=None, upper=None, delta_id="fixture-local-delta-B4-F02", unknown=("energy_matching",))
    f02 = _case("B4-F02-UNKNOWN-AND-PARTIAL", (x,), (unknown,), {x.semantic_fingerprint: _delta(x, ("cap-f02",), "B4-F02")})

    mixed_option = _option(1, 11)
    mixed_cap = _capability("cap-f03", level=1, ready=True, lower=1, upper=1, delta_id="fixture-local-delta-B4-F03")
    f03_mixed = _case("B4-F03-MIXED-COVERAGE", (x, mixed_option), (mixed_cap,), {x.semantic_fingerprint: _delta(x, ("cap-f03",), "B4-F03"), mixed_option.semantic_fingerprint: _delta(mixed_option, ("missing-capability",), "B4-F03-UNSUPPORTED")})
    f03_optional = _case("B4-F03-OPTIONAL-ACTION", (x,), (mixed_cap,), {x.semantic_fingerprint: _delta(x, ("cap-f03",), "B4-F03-ACTION")}, min_count=0)
    f03_stop = _case("B4-F03-STOP", (x,), (mixed_cap,), {x.semantic_fingerprint: _delta(x, ("cap-f03",), "B4-F03-STOP", action_eligible=False)}, min_count=0)

    f04_compound = _case("B4-F04-COMPOUND", (x, y), (cap_x, cap_y), {x.semantic_fingerprint: _delta(x, ("cap-x",), "B4-F04-X"), y.semantic_fingerprint: _delta(y, ("cap-y",), "B4-F04-Y")}, max_count=2)
    ordered_x = _skill_option(0)
    ordered_y = _skill_option(1)
    ordered_x_delta = _delta(ordered_x, ("cap-x",), "B4-F04-X")
    ordered_y_delta = _delta(ordered_y, ("cap-y",), "B4-F04-Y")
    f04_ordered = _case("B4-F04-ORDERED", (ordered_x, ordered_y), (cap_x, cap_y), {ordered_x.semantic_fingerprint: ordered_x_delta, ordered_y.semantic_fingerprint: ordered_y_delta}, ordering="ORDERED", selection_type=5, selection_context=34, max_count=2)
    f04_unordered = _case("B4-F04-UNORDERED", (x, y), (cap_x, cap_y), {x.semantic_fingerprint: _delta(x, ("cap-x",), "B4-F04-X"), y.semantic_fingerprint: _delta(y, ("cap-y",), "B4-F04-Y")}, max_count=2)
    end_option = LegalOptionV1(
        schema_version=CONTRACT_VERSION, original_index=0, selection_type=0, selection_context=0,
        option_type=14, option_name="END", choice_role="END", source_kind="NONE", target_kind="NONE",
        available=True, semantic_fingerprint="",
    )
    end_option = replace(end_option, semantic_fingerprint=stable_hash(end_option.semantic_payload()))
    f04_stop_row = _case("B4-F04-STOP-ROW", (end_option,), (cap_x,), {end_option.semantic_fingerprint: _delta(end_option, ("cap-x",), "B4-F04-END")})
    # Duplicate semantics are still a valid G1 request when only transport
    # original_index differs; the evaluator must reject them before ranking.
    duplicate = replace(x, original_index=1)
    f04_duplicate = _case("B4-F04-DUPLICATE", (x, duplicate), (cap_x, cap_y), {x.semantic_fingerprint: _delta(x, ("cap-x",), "B4-F04-X")})

    f07 = _case("B4-F07-CURRENT-DELTA-ONLY", (x, y), (cap_x, cap_y), {x.semantic_fingerprint: _delta(x, ("cap-x",), "B4-F07-X"), y.semantic_fingerprint: _delta(y, ("cap-y",), "B4-F07-Y")})
    return (f01, f02, f03_mixed, f03_optional, f03_stop, f04_compound, f04_ordered, f04_unordered, f04_stop_row, f04_duplicate, f07)


def semantic_permutation_suite(option_count: int, count: int = 32) -> tuple[tuple[int, ...], ...]:
    _nonnegative_int(option_count, "option_count")
    if option_count <= 0 or not isinstance(count, int) or count <= 0:
        raise ValueError("permutation dimensions must be positive")
    values = tuple(itertools.permutations(range(option_count)))
    return tuple(values[index % len(values)] for index in range(count))


def _map_key(value: str | None, owner_map: Mapping[int, int]) -> str | None:
    if value is None or not value.startswith("p") or ":" not in value:
        return value
    prefix, suffix = value.split(":", 1)
    try:
        owner = int(prefix[1:])
    except ValueError:
        return value
    return f"p{owner_map.get(owner, owner)}:{suffix}"


def mirror_b4_case(case: B4FixtureCaseV1) -> B4FixtureCaseV1:
    owner_map = {0: 1, 1: 0}
    observation = case.observation
    entities = tuple(
        replace(entity, entity_key=_map_key(entity.entity_key, owner_map), owner=owner_map[entity.owner])
        for entity in observation.entities
    )
    players = tuple(sorted((replace(player, player_index=owner_map[player.player_index], hand_visible=owner_map[player.player_index] == 1) for player in observation.players), key=lambda item: item.player_index))
    mirrored_observation = replace(observation, battle_id=f"{observation.battle_id}-mirror", acting_player=1, players=players, entities=entities)
    options: list[LegalOptionV1] = []
    remapped_deltas: dict[str, ThreatLocalDeltaV1] = {}
    for option in case.request.options:
        mirrored = replace(
            option,
            source_ref=_map_key(option.source_ref, owner_map), source_entity_key=_map_key(option.source_entity_key, owner_map),
            target_ref=_map_key(option.target_ref, owner_map), target_entity_key=_map_key(option.target_entity_key, owner_map),
        )
        mirrored = replace(mirrored, semantic_fingerprint=stable_hash(mirrored.semantic_payload()))
        options.append(mirrored)
        original_delta = case.local_deltas[option.semantic_fingerprint]
        remapped_deltas[mirrored.semantic_fingerprint] = _seal_delta(
            replace(original_delta, option_fingerprint=mirrored.semantic_fingerprint)
        )
    request = replace(case.request, episode_uuid=mirrored_observation.battle_id, request_id=f"{case.request.request_id}-mirror", acting_player=1, options=tuple(options))
    state = PublicStateV1.from_engine(mirrored_observation, request)
    capabilities = tuple(
        _seal_capability(
            _bind_capability_public_fields(
                replace(
                    cap,
                    source_entity_key=_map_key(cap.source_entity_key, owner_map),
                    target_entity_key=_map_key(cap.target_entity_key, owner_map),
                ),
                state,
            )
        )
        for cap in case.capabilities
    )
    census_receipts = tuple(
        replace(
            census,
            observation_hash=state.public_hash,
            source_scope=tuple(_map_key(value, owner_map) or value for value in census.source_scope),
            target_scope=tuple(_map_key(value, owner_map) or value for value in census.target_scope),
        )
        for census in case.receipt.census_receipts
    )
    receipt = replace(
        case.receipt,
        capabilities=capabilities,
        local_delta_receipt_ids=tuple(delta.receipt_id for delta in remapped_deltas.values()),
        local_delta_content_sha256={
            delta.receipt_id: _delta_content_digest(delta) for delta in remapped_deltas.values()
        },
        census_receipts=census_receipts,
        canonical_case_sha256="0" * 64,
    )
    mirrored = replace(
        case,
        case_id=f"{case.case_id}-MIRROR",
        observation=mirrored_observation,
        request=request,
        state=state,
        receipt=receipt,
        capabilities=capabilities,
        local_deltas=MappingProxyType(remapped_deltas),
    )
    return _seal_case(mirrored)


def _config_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _canonical_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _canonical_value(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (tuple, list)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, Fraction):
        return {"denominator": value.denominator, "numerator": value.numerator}
    if hasattr(value, "__dataclass_fields__"):
        return {field.name: _canonical_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Path):
        return str(value)
    return value


def _capability_content_payload(capability: VisibleThreatCapabilityV1) -> Mapping[str, Any]:
    return {
        field.name: _canonical_value(getattr(capability, field.name))
        for field in fields(capability)
        if field.name != "content_sha256"
    }


def _capability_content_digest(capability: VisibleThreatCapabilityV1) -> str:
    return stable_hash(_capability_content_payload(capability))


def _seal_capability(capability: VisibleThreatCapabilityV1) -> VisibleThreatCapabilityV1:
    return replace(capability, content_sha256=_capability_content_digest(capability))


def _delta_content_payload(delta: ThreatLocalDeltaV1) -> Mapping[str, Any]:
    return {
        field.name: _canonical_value(getattr(delta, field.name))
        for field in fields(delta)
        if field.name != "content_sha256"
    }


def _delta_content_digest(delta: ThreatLocalDeltaV1) -> str:
    return stable_hash(_delta_content_payload(delta))


def _seal_delta(delta: ThreatLocalDeltaV1) -> ThreatLocalDeltaV1:
    return replace(delta, content_sha256=_delta_content_digest(delta))


def _receipt_content_payload(receipt: B4CapabilityReceiptV1) -> Mapping[str, Any]:
    """Canonical receipt payload with its outer self-digest excluded."""

    return {
        field.name: _canonical_value(getattr(receipt, field.name))
        for field in fields(receipt)
        if field.name != "canonical_case_sha256"
    }


def _canonical_case_payload(case: B4FixtureCaseV1) -> Mapping[str, Any]:
    """Every public/current fixture input covered by the per-case seal.

    ``local_deltas`` is deliberately an ordered sequence rather than a
    canonicalized mapping.  The request's option order and the receipt's
    local-delta order are part of the exact transport contract, even though
    the evaluator separately reasons over semantic fingerprints.
    """

    request_payload = _canonical_value(case.request)
    request_payload["options"] = sorted(
        request_payload["options"], key=lambda item: item["semantic_fingerprint"]
    )
    state_payload = _canonical_value(case.state)
    if state_payload.get("request") is not None:
        state_payload["request"] = request_payload
    return {
        "observation": _canonical_value(case.observation),
        "request": request_payload,
        "state": state_payload,
        "receipt": _receipt_content_payload(case.receipt),
        "capabilities": _canonical_value(case.capabilities),
        "local_deltas": [
            (key, _canonical_value(case.local_deltas[key]))
            for key in sorted(case.local_deltas)
        ],
        "expected": _canonical_value(dict(case.expected)),
        "successor_fields": _canonical_value(case.successor_fields),
    }


def _case_content_digest(case: B4FixtureCaseV1) -> str:
    return stable_hash(_canonical_case_payload(case))


def _seal_case(case: B4FixtureCaseV1) -> B4FixtureCaseV1:
    """Rebuild the receipt seal after all case content is materialized."""

    deltas = MappingProxyType({
        key: _seal_delta(delta) for key, delta in case.local_deltas.items()
    })
    receipt = replace(
        case.receipt,
        capabilities=tuple(case.capabilities),
        local_delta_receipt_ids=tuple(delta.receipt_id for delta in deltas.values()),
        local_delta_content_sha256={
            delta.receipt_id: _delta_content_digest(delta) for delta in deltas.values()
        },
        canonical_case_sha256="0" * 64,
    )
    materialized = replace(case, receipt=receipt, local_deltas=deltas)
    return replace(
        materialized,
        receipt=replace(
            materialized.receipt, canonical_case_sha256=_case_content_digest(materialized)
        ),
    )


@lru_cache(maxsize=1)
def _canonical_capability_digest_catalog() -> Mapping[str, Mapping[str, frozenset[str]]]:
    catalog: dict[str, dict[str, set[str]]] = {}
    for original in _build_cases():
        for variant in (original, mirror_b4_case(original)):
            case_catalog = catalog.setdefault(variant.receipt.fixture_case_id, {})
            for capability in variant.capabilities:
                case_catalog.setdefault(capability.capability_id, set()).add(capability.content_sha256)
    return {
        case_id: {capability_id: frozenset(digests) for capability_id, digests in capabilities.items()}
        for case_id, capabilities in catalog.items()
    }


def _validate_capability_content_authority(
    receipt: B4CapabilityReceiptV1,
    capabilities: Sequence[VisibleThreatCapabilityV1],
) -> str | None:
    case_authority = _canonical_case_authority_catalog().get(receipt.fixture_case_id)
    expected = case_authority["capabilities"] if case_authority is not None else None
    if expected is None:
        return "RECEIPT_CONTENT_MISMATCH"
    for capability in capabilities:
        digest = _capability_content_digest(capability)
        if capability.content_sha256 != digest:
            return "RECEIPT_CONTENT_MISMATCH"
        if digest not in expected.get(capability.capability_id, ()):
            return "RECEIPT_CONTENT_MISMATCH"
    return None


def _canonical_fixture_payload(
    cases: Sequence[B4FixtureCaseV1],
    scale: ThreatLevelScaleV1,
    dependency_manifest: Mapping[str, str],
) -> Mapping[str, Any]:
    return {
        "schema_version": B4_SCHEMA_VERSION,
        "record_id": _FIXTURE_RECORD_ID,
        "scope": FIXTURE_ONLY,
        "threat_level_scale": _canonical_value(scale),
        # The implementation hash is checked independently against the exact
        # loaded source.  Excluding its value here avoids a recursive content
        # digest while retaining the path as part of the sealed dependency
        # graph.
        "dependency_manifest": {
            key: ("IMPLEMENTATION_SOURCE_BOUND_SEPARATELY" if key == str(_IMPLEMENTATION_PATH) else dependency_manifest[key])
            for key in sorted(dependency_manifest)
        },
        "fixture_cases": [
            {
                "case_id": case.case_id,
                **_canonical_case_payload(case),
            }
            for case in cases
        ],
    }


def _normalized_source_digest(path: Path) -> str:
    raw = path.read_bytes()
    pattern = rb'(B4_IMPLEMENTATION_SOURCE_SHA256\s*=\s*["\'])([0-9a-f]{64})(["\'])'
    normalized, count = re.subn(pattern, rb'\g<1>' + (b"0" * 64) + rb'\g<3>', raw)
    if count != 1:
        raise ValueError("B4 implementation source hash marker is missing or duplicated")
    return hashlib.sha256(normalized).hexdigest()


def _dependency_manifest(root: Path) -> Mapping[str, str]:
    result: dict[str, str] = {}
    for relative in _DEPENDENCY_PATHS:
        path = root / relative
        if not path.is_file():
            raise ValueError(f"B4 dependency is missing: {relative}")
        result[str(relative)] = _normalized_source_digest(path) if relative == _IMPLEMENTATION_PATH else hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _apply_declared_expectations(
    cases: Sequence[B4FixtureCaseV1], expected_by_id: Mapping[str, Mapping[str, str]]
) -> tuple[B4FixtureCaseV1, ...]:
    result = []
    for case in cases:
        expected = expected_by_id.get(case.case_id)
        if expected is None or set(expected) != {A_FORMULATION, B_FORMULATION}:
            raise ValueError(f"B4 config lacks exact expected outcomes for {case.case_id}")
        if any(not isinstance(key, str) or not isinstance(status, str) or not status for key, status in expected.items()):
            raise ValueError(f"B4 expected outcome is malformed for {case.case_id}")
        result.append(_seal_case(replace(case, expected=MappingProxyType(dict(expected)))))
    return tuple(result)


def _canonical_zero_response_variant(case: B4FixtureCaseV1) -> B4FixtureCaseV1 | None:
    """Build the one canonical zero-threat census row used by F01 probes."""

    if case.case_id != "B4-F01-FORMULATION-DIVERGENCE" or not case.request.options:
        return None
    option = case.request.options[0]
    original_delta = case.local_deltas[option.semantic_fingerprint]
    request = replace(case.request, options=(option,))
    state = PublicStateV1.from_engine(case.observation, request)
    delta = _seal_delta(replace(
        original_delta,
        remaining_capability_ids=(),
        census_complete=True,
        census_receipt_id="fixture-census-f01-x",
    ))
    census = PublicCensusReceiptV1(
        receipt_id="fixture-census-f01-x",
        observation_hash=state.public_hash,
        source_scope=(option.source_entity_key,),
        target_scope=(option.target_entity_key,),
        checks=("VISIBLE_SOURCE_CENSUS", "TARGET_LEGALITY", "ENERGY_REQUIREMENTS", "STATUS_CONSTRAINTS"),
        local_delta_receipt_id=delta.receipt_id,
    )
    receipt = replace(
        case.receipt,
        capabilities=(),
        local_delta_receipt_ids=(delta.receipt_id,),
        local_delta_content_sha256={delta.receipt_id: _delta_content_digest(delta)},
        census_receipts=(census,),
        canonical_case_sha256="0" * 64,
    )
    return _seal_case(replace(
        case,
        request=request,
        state=state,
        receipt=receipt,
        capabilities=(),
        local_deltas=MappingProxyType({option.semantic_fingerprint: delta}),
    ))


@lru_cache(maxsize=1)
def _canonical_case_authority_catalog() -> Mapping[str, Mapping[str, Any]]:
    """Return sealed base/mirror case content and per-row authorities."""

    config_path = _config_root() / _CONFIG_RELATIVE
    with config_path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    expected_by_id = {
        item["id"]: item["expected"] for item in value.get("fixture_cases", ())
    }
    cases = _apply_declared_expectations(_build_cases(), expected_by_id)
    variants: list[B4FixtureCaseV1] = []
    for case in cases:
        variants.extend((case, mirror_b4_case(case)))
        zero = _canonical_zero_response_variant(case)
        if zero is not None:
            variants.extend((zero, mirror_b4_case(zero)))
    catalog: dict[str, dict[str, Any]] = {}
    for variant in variants:
        case_id = variant.receipt.fixture_case_id
        entry = catalog.setdefault(case_id, {
            "case_digests": set(),
            "capabilities": {},
            "deltas": {},
            "expected": dict(variant.expected),
        })
        entry["case_digests"].add(variant.receipt.canonical_case_sha256)
        for capability in variant.capabilities:
            entry["capabilities"].setdefault(capability.capability_id, set()).add(
                capability.content_sha256
            )
        for delta in variant.local_deltas.values():
            entry["deltas"].setdefault(delta.receipt_id, set()).add(
                delta.content_sha256
            )
    return {
        case_id: {
            "case_digests": frozenset(entry["case_digests"]),
            "capabilities": {
                key: frozenset(value) for key, value in entry["capabilities"].items()
            },
            "deltas": {
                key: frozenset(value) for key, value in entry["deltas"].items()
            },
            "expected": MappingProxyType(dict(entry["expected"])),
        }
        for case_id, entry in catalog.items()
    }


def materialize_b4_fixture_data(value: Mapping[str, Any], *, config_path: Path | None = None) -> B4FixtureBundleV1:
    allowed = {"schema_version", "record_id", "scope", "fixture_metadata_sha256", "threat_level_scale", "fixture_cases", "dependency_manifest"}
    if not isinstance(value, Mapping) or set(value) != allowed:
        raise ValueError("B4 fixture top-level fields are incomplete or unknown")
    if isinstance(value["schema_version"], bool) or not isinstance(value["schema_version"], int) or value["schema_version"] != B4_SCHEMA_VERSION or value["record_id"] != _FIXTURE_RECORD_ID or value["scope"] != FIXTURE_ONLY:
        raise ValueError("unknown B4 fixture metadata")
    _digest(value["fixture_metadata_sha256"], "fixture_metadata_sha256")
    if not isinstance(value["dependency_manifest"], Mapping) or set(value["dependency_manifest"]) != {str(path) for path in _DEPENDENCY_PATHS}:
        raise ValueError("B4 dependency manifest is incomplete or unknown")
    configured_dependencies = {key: _digest(item, f"dependency_manifest.{key}") for key, item in value["dependency_manifest"].items()}
    actual_dependencies = _dependency_manifest(_config_root())
    if configured_dependencies != actual_dependencies:
        raise ValueError("B4 dependency manifest does not match the loaded source/schema files")
    scale = ThreatLevelScaleV1.from_dict(value["threat_level_scale"])
    if not isinstance(value["fixture_cases"], list):
        raise ValueError("B4 fixture_cases must be an ordered list")
    expected_by_id: dict[str, Mapping[str, str]] = {}
    for item in value["fixture_cases"]:
        if not isinstance(item, Mapping) or set(item) != {"id", "expected"} or not isinstance(item["id"], str) or not isinstance(item["expected"], Mapping):
            raise ValueError("B4 fixture case declaration is incomplete or unknown")
        if item["id"] in expected_by_id:
            raise ValueError("B4 fixture case declaration is duplicated")
        expected_by_id[item["id"]] = item["expected"]
    cases = _apply_declared_expectations(_build_cases(), expected_by_id)
    declared = tuple(item["id"] for item in value["fixture_cases"])
    if declared != tuple(case.case_id for case in cases):
        raise ValueError("B4 config does not declare exactly the materialized fixture cases")
    if any(case.receipt.threat_level_scale != scale for case in cases):
        raise ValueError("B4 fixture case scale differs from config ThreatLevelScaleV1")
    canonical_digest = stable_hash(_canonical_fixture_payload(cases, scale, configured_dependencies))
    if canonical_digest != value["fixture_metadata_sha256"] or canonical_digest != B4_CANONICAL_FIXTURE_DIGEST:
        raise ValueError("B4 canonical fixture content digest does not match its sealed authority")
    return B4FixtureBundleV1(config_path or Path("<memory>"), cases[0].receipt, cases)


def load_b4_fixtures(path: str | Path | None = None) -> B4FixtureBundleV1:
    config_path = Path(path) if path is not None else _config_root() / _CONFIG_RELATIVE
    with config_path.open(encoding="utf-8") as handle:
        return materialize_b4_fixture_data(json.load(handle), config_path=config_path)


def _decision(status: str, state: PublicStateV1 | None, formulation_id: str, *, reason: str | None = None, candidates: Sequence[ThreatCandidateV1] = (), chosen: ThreatCandidateV1 | None = None, key: tuple[Any, ...] = (), action: CompoundActionV1 | None = None) -> ThreatDecisionV1:
    request = state.request if isinstance(state, PublicStateV1) else None
    return ThreatDecisionV1(
        schema_version=B4_SCHEMA_VERSION,
        request_id=request.request_id if request is not None else "unsupported",
        selection_seq=request.selection_seq if request is not None else (state.transition_id if isinstance(state, PublicStateV1) else 0),
        acting_player=request.acting_player if request is not None else (state.acting_player if isinstance(state, PublicStateV1) else None),
        policy_id=CurrentOpponentThreatEvaluatorV1.policy_id,
        formulation_id=formulation_id,
        status=status,
        authority=EXPERIMENTAL_THREAT_AUTHORITY if status == SELECTED else B0_DELEGATION_AUTHORITY,
        chosen_semantic_action_key=(chosen.action_key,) if chosen is not None else (),
        chosen_option_fingerprints=(chosen.option.semantic_fingerprint,) if chosen is not None else (),
        chosen_original_indices=(chosen.option.original_index,) if chosen is not None else (),
        decision_key=key,
        candidate_count=len(candidates),
        fail_closed_reason=reason,
        candidates=tuple(candidates),
        interval_by_option=tuple((item.option.semantic_fingerprint, (item.guaranteed_level, item.possible_level)) for item in candidates),
        receipt_scope=FIXTURE_ONLY,
        action=action,
        stopped_early=bool(action.stopped_early) if action is not None else False,
    )


class CurrentOpponentThreatEvaluatorV1:
    """Stateful, fixture-only B4-A/B evaluator."""

    policy_id = "b4-current-public-opponent-threat-fixture-v1"

    def __init__(self, receipt: B4CapabilityReceiptV1) -> None:
        if not isinstance(receipt, B4CapabilityReceiptV1):
            raise TypeError("B4 evaluator requires a B4CapabilityReceiptV1")
        self.receipt = receipt
        self._last: dict[tuple[str, int, int], tuple[str, ThreatDecisionV1]] = {}
        self._outcomes: dict[tuple[tuple[str, int, int], str], ThreatDecisionV1] = {}
        self._request_ids: dict[tuple[str, int], dict[str, int]] = {}
        self._diagnostics = _Diagnostics()

    @property
    def diagnostics(self) -> _Diagnostics:
        return replace(self._diagnostics)

    def reset(self, episode_uuid: str, player_index: int, reason: str = "start") -> None:
        if not isinstance(episode_uuid, str) or not episode_uuid or player_index not in (0, 1):
            raise ValueError("invalid B4 lifecycle identity")
        if reason not in {"start", "terminal", "error", "worker_replacement", "permutation"}:
            raise ValueError("unknown B4 lifecycle reset reason")
        self._last = {key: value for key, value in self._last.items() if not (key[0] == episode_uuid and key[1] == player_index)}
        self._outcomes = {key: value for key, value in self._outcomes.items() if not (key[0][0] == episode_uuid and key[0][1] == player_index)}
        self._request_ids = {key: value for key, value in self._request_ids.items() if not (key[0] == episode_uuid and key[1] == player_index)}

    def _delegate(self, state: PublicStateV1 | None, formulation_id: str, reason: str, candidates: Sequence[ThreatCandidateV1] = ()) -> ThreatDecisionV1:
        self._diagnostics.delegated += 1
        if reason.startswith("STALE"):
            self._diagnostics.stale_rejections += 1
        if reason.startswith("PUBLIC_BOUNDARY"):
            self._diagnostics.hidden_boundary_rejections += 1
        return _decision(B0_DELEGATE, state, formulation_id, reason=reason, candidates=candidates)

    @staticmethod
    def build_optional_stop(request: SelectionRequestV1) -> CompoundActionV1:
        """Build a first-class STOP token for an optional singleton request."""

        if request.min_count != 0 or request.max_count != 1:
            raise ValueError("B4 STOP requires a 0..1 singleton request")
        if any(option.option_type == 14 for option in request.options):
            raise ValueError("STOP is a builder token, not a LegalOptionV1 row")
        builder = CompoundActionBuilder(request)
        builder.stop()
        return builder.build()

    def _payload_digest(
        self,
        state: PublicStateV1,
        request: SelectionRequestV1,
        formulation_id: str,
        local_deltas: Any,
        capabilities: Any,
        fixture: Any,
    ) -> str:
        # Request identity includes all current public inputs and receipt
        # content.  repr is used only as a lossless digest envelope here; no
        # value from it is interpreted as game state.
        return stable_hash({
            "state": state.state_hash(),
            "request": repr(request),
            "formulation": formulation_id,
            "local_deltas": repr(local_deltas),
            "capabilities": repr(capabilities),
            "fixture": repr(fixture),
        })

    def _remember(
        self,
        lifecycle_key: tuple[str, int],
        request_key: tuple[str, int, int],
        payload_digest: str,
        request: SelectionRequestV1,
        decision: ThreatDecisionV1,
    ) -> ThreatDecisionV1:
        outcome_key = (request_key, payload_digest)
        self._outcomes[outcome_key] = decision
        self._last.setdefault(request_key, (payload_digest, decision))
        self._request_ids.setdefault(lifecycle_key, {})[request.request_id] = request.selection_seq
        return decision

    def _lifecycle_guard(
        self,
        state: PublicStateV1,
        request: SelectionRequestV1,
        formulation_id: str,
        payload_digest: str,
    ) -> ThreatDecisionV1 | None:
        lifecycle_key = (request.episode_uuid, request.acting_player)
        request_key = (request.episode_uuid, request.acting_player, request.selection_seq)
        prior_seq = self._request_ids.get(lifecycle_key, {})
        # The monotonic sequence check must precede duplicate-cache lookup.
        # Otherwise an exact old request could replay a prior decision after a
        # newer selection has already entered the lifecycle.
        if prior_seq and request.selection_seq < max(prior_seq.values()):
            result = self._delegate(state, formulation_id, "STALE_SELECTION_SEQUENCE")
            return self._remember(lifecycle_key, request_key, payload_digest, request, result)
        cached = self._outcomes.get((request_key, payload_digest))
        if cached is not None:
            return cached
        prior = self._last.get(request_key)
        if prior is not None:
            result = self._delegate(state, formulation_id, "STALE_OR_REUSED_REQUEST_IDENTITY")
            return self._remember(lifecycle_key, request_key, payload_digest, request, result)
        if request.request_id in prior_seq and prior_seq[request.request_id] != request.selection_seq:
            result = self._delegate(state, formulation_id, "STALE_OR_REUSED_REQUEST_IDENTITY")
            return self._remember(lifecycle_key, request_key, payload_digest, request, result)
        return None

    def _validate_case_authority(
        self,
        state: PublicStateV1,
        request: SelectionRequestV1,
        local_deltas: Mapping[str, ThreatLocalDeltaV1],
        capabilities: Sequence[VisibleThreatCapabilityV1],
        fixture: B4FixtureCaseV1 | None,
    ) -> str | None:
        """Bind the complete runtime payload to a sealed canonical case."""

        authority = _canonical_case_authority_catalog().get(self.receipt.fixture_case_id)
        if authority is None:
            return "RECEIPT_CONTENT_MISMATCH"
        if fixture is not None:
            if fixture.receipt != self.receipt:
                return "UNREGISTERED_CAPABILITIES"
            if _case_content_digest(fixture) != self.receipt.canonical_case_sha256:
                return "RECEIPT_CONTENT_MISMATCH"
        expected = authority["expected"]
        candidate = B4FixtureCaseV1(
            case_id=self.receipt.fixture_case_id,
            observation=state.observation,
            request=request,
            state=state,
            receipt=self.receipt,
            capabilities=tuple(capabilities),
            local_deltas=MappingProxyType(dict(local_deltas)),
            expected=expected,
            successor_fields=fixture.successor_fields if fixture is not None else (),
        )
        digest = _case_content_digest(candidate)
        if digest != self.receipt.canonical_case_sha256:
            return "RECEIPT_CONTENT_MISMATCH"
        if digest not in authority["case_digests"]:
            return "RECEIPT_CONTENT_MISMATCH"
        return None

    def _validate_provenance_graph(
        self,
        local_deltas: Mapping[str, ThreatLocalDeltaV1],
        capabilities: Sequence[VisibleThreatCapabilityV1],
    ) -> str | None:
        case_authority = _canonical_case_authority_catalog().get(self.receipt.fixture_case_id)
        if case_authority is None:
            return "RECEIPT_CONTENT_MISMATCH"
        content_reason = _validate_capability_content_authority(self.receipt, capabilities)
        if content_reason is not None:
            return content_reason
        registered_delta_ids = set(self.receipt.local_delta_receipt_ids)
        if set(self.receipt.local_delta_content_sha256) != registered_delta_ids:
            return "RECEIPT_CONTENT_MISMATCH"
        expected_delta_digests = case_authority["deltas"]
        expected_manifest = _fixture_provenance(self.receipt.threat_level_scale.scale_id)
        if dict(self.receipt.provenance_manifest) != dict(expected_manifest):
            return "PROVENANCE_GRAPH_INVALID"
        observed_delta_ids: set[str] = set()
        references: dict[str, list[str]] = {item.capability_id: [] for item in capabilities}
        for delta in local_deltas.values():
            if not isinstance(delta, ThreatLocalDeltaV1):
                return "PROVENANCE_GRAPH_INVALID"
            if delta.receipt_id in observed_delta_ids or delta.receipt_id not in registered_delta_ids:
                return "UNREGISTERED_LOCAL_DELTA"
            digest = _delta_content_digest(delta)
            if delta.content_sha256 != digest:
                return "RECEIPT_CONTENT_MISMATCH"
            if self.receipt.local_delta_content_sha256.get(delta.receipt_id) != digest:
                return "RECEIPT_CONTENT_MISMATCH"
            if digest not in expected_delta_digests.get(delta.receipt_id, ()):
                return "RECEIPT_CONTENT_MISMATCH"
            observed_delta_ids.add(delta.receipt_id)
            for capability_id in delta.remaining_capability_ids:
                capability = next((item for item in capabilities if item.capability_id == capability_id), None)
                if capability is None:
                    return "INCOMPLETE_THREAT_COVERAGE"
                if capability.local_delta_receipt_id != delta.receipt_id:
                    return "PROVENANCE_GRAPH_INVALID"
                references.setdefault(capability_id, []).append(delta.receipt_id)
        if observed_delta_ids != registered_delta_ids:
            return "PROVENANCE_GRAPH_INVALID"
        for capability in capabilities:
            if capability.local_delta_receipt_id not in registered_delta_ids:
                return "UNREGISTERED_CAPABILITY"
            if references.get(capability.capability_id, []) != [capability.local_delta_receipt_id]:
                return "PROVENANCE_GRAPH_INVALID"
            for field in _PROVENANCE_FIELDS:
                if getattr(capability, field) != self.receipt.provenance_manifest[field]:
                    return "PROVENANCE_GRAPH_INVALID"
        return None

    def _validate_capability_fields(self, capability: VisibleThreatCapabilityV1, formulation_id: str) -> str | None:
        if capability.qualification_status != FIXTURE_ONLY:
            return "PARTIAL_CAPABILITY"
        if capability.choice_role not in _CAPABILITY_CHOICE_ROLES:
            return "UNSUPPORTED_CAPABILITY_SEMANTICS"
        if any(value not in _PUBLIC_ENERGY_TYPES for value in capability.energy_requirements):
            return "UNSUPPORTED_CAPABILITY_SEMANTICS"
        if any(value not in _PUBLIC_STATUS_CONSTRAINTS for value in capability.status_constraints):
            return "UNSUPPORTED_CAPABILITY_SEMANTICS"
        if any(value not in _PUBLIC_TARGET_REQUIREMENTS for value in capability.target_requirements):
            return "UNSUPPORTED_CAPABILITY_SEMANTICS"
        if capability.choice_role == "ATTACK" and (capability.attack_id is None or capability.effect_id is not None):
            return "UNSUPPORTED_CAPABILITY_SEMANTICS"
        if capability.choice_role != "ATTACK" and capability.effect_id is None:
            return "UNSUPPORTED_CAPABILITY_SEMANTICS"
        prose_tokens = ("card", "prose", "description", "text", "damage", "effect")
        semantic_fields = (
            capability.damage_or_effect_semantics,
            *capability.status_constraints,
            *capability.target_requirements,
        )
        if capability.damage_or_effect_semantics != _FIXTURE_SEMANTICS or any(
            any(token in value.lower() for token in prose_tokens)
            for value in semantic_fields
        ):
            return "CARD_PROSE_FORBIDDEN"
        if capability.unknown_fields:
            return "UNKNOWN_THREAT_FIELD" if formulation_id == A_FORMULATION else "MISSING_INTERVAL_BOUND"
        if not capability.energy_requirements or not capability.status_constraints or not capability.target_requirements:
            return "INCOMPLETE_CAPABILITY"
        if capability.ready_now is None or not isinstance(capability.ready_now, bool) or capability.energy_deficit is None or capability.threat_level is None:
            return "UNKNOWN_THREAT_FIELD"
        if capability.guaranteed_level is None or capability.possible_level is None:
            return "UNKNOWN_THREAT_FIELD" if formulation_id == A_FORMULATION else "MISSING_INTERVAL_BOUND"
        try:
            self.receipt.threat_level_scale.validate_level(capability.threat_level, "threat_level")
            self.receipt.threat_level_scale.validate_level(capability.guaranteed_level, "guaranteed_level")
            self.receipt.threat_level_scale.validate_level(capability.possible_level, "possible_level")
        except ValueError:
            return "INVALID_THREAT_LEVEL"
        return None

    @staticmethod
    def _validate_capability_public_binding(
        capability: VisibleThreatCapabilityV1,
        source: VisibleEntityV1,
        target: VisibleEntityV1,
    ) -> str | None:
        expected = {
            "source_card_id": source.card_id,
            "target_card_id": target.card_id,
            "source_serial": source.serial,
            "target_serial": target.serial,
            "source_owner": source.owner,
            "target_owner": target.owner,
            "source_zone": source.zone,
            "target_zone": target.zone,
            "source_position": source.position,
            "target_position": target.position,
            "source_hp": source.hp,
            "source_max_hp": source.max_hp,
            "target_hp": target.hp,
            "target_max_hp": target.max_hp,
        }
        if any(getattr(capability, field) != value for field, value in expected.items()):
            return "CAPABILITY_PUBLIC_BINDING_MISMATCH"
        return None

    @staticmethod
    def _validate_option_semantics(
        state: PublicStateV1,
        option: LegalOptionV1,
        entities: Mapping[str, VisibleEntityV1],
    ) -> str | None:
        if option.option_type not in _B4_OPTION_TYPES:
            return "UNSUPPORTED_OPTION_SEMANTICS"
        if option.attack_id is not None or option.special_condition_type is not None:
            return "OPTION_EFFECT_MISMATCH"
        if state.request.context_card_id is not None or state.request.effect_card_id is not None:
            return "OPTION_CONTEXT_MISMATCH"
        if option.source_kind != "ENTITY" or option.target_kind != "ENTITY":
            return "UNSUPPORTED_OPTION_SEMANTICS"
        if option.source_entity_key is None or option.target_entity_key is None:
            return "UNRESOLVED_PUBLIC_REFERENCE"
        source = entities.get(option.source_entity_key)
        target = entities.get(option.target_entity_key)
        if source is None or target is None:
            return "UNRESOLVED_PUBLIC_REFERENCE"
        if source.owner != state.acting_player or target.owner != state.acting_player:
            return "OPTION_OWNER_MISMATCH"
        if source.zone != AREA["HAND"]:
            return "OPTION_SOURCE_ZONE_MISMATCH"
        if target.zone not in {AREA["ACTIVE"], AREA["BENCH"]}:
            return "OPTION_TARGET_ZONE_MISMATCH"
        if option.source_ref != option.source_entity_key or option.target_ref != option.target_entity_key:
            return "OPTION_REFERENCE_MISMATCH"
        if option.choice_role != OPTION_NAMES[option.option_type]:
            return "OPTION_CHOICE_ROLE_MISMATCH"
        if option.in_play_area != target.zone or option.in_play_index != target.position:
            return "OPTION_TARGET_POSITION_MISMATCH"
        if option.card_id is not None and option.card_id != source.card_id:
            return "OPTION_SOURCE_CARD_MISMATCH"
        if option.serial is not None and option.serial != source.serial:
            return "OPTION_SOURCE_SERIAL_MISMATCH"
        return None

    def _evaluate_strict(
        self,
        state_or_observation: PublicStateV1 | EngineObservationV1,
        local_deltas_or_request: Mapping[str, ThreatLocalDeltaV1] | SelectionRequestV1 | None,
        formulation_id: str,
        *,
        capabilities: Sequence[VisibleThreatCapabilityV1] | None,
        fixture: B4FixtureCaseV1 | None,
    ) -> ThreatDecisionV1:
        self._diagnostics.requests += 1
        observation = state_or_observation.observation if isinstance(state_or_observation, PublicStateV1) else state_or_observation
        request_hint = local_deltas_or_request if isinstance(local_deltas_or_request, SelectionRequestV1) else None
        # Terminal is checked before request-local fields, including a stale
        # request supplied alongside a terminal native response.
        if isinstance(observation, EngineObservationV1) and observation.terminal_result is not None:
            try:
                terminal_state = PublicStateV1.from_engine(observation, None)
            except PublicStateError as error:
                return self._delegate(None, formulation_id, f"PUBLIC_BOUNDARY:{error}")
            self._diagnostics.terminal_overrides += 1
            return _decision(TERMINAL_OVERRIDE, terminal_state, formulation_id, reason="terminal checked first")
        if not isinstance(observation, EngineObservationV1):
            return self._delegate(None, formulation_id, "CURRENT_OBSERVATION_REQUIRED")
        request = request_hint
        if request is None and isinstance(state_or_observation, PublicStateV1):
            request = state_or_observation.request
        if not isinstance(request, SelectionRequestV1):
            return self._delegate(None, formulation_id, "CURRENT_REQUEST_REQUIRED")
        try:
            state = PublicStateV1.from_engine(observation, request)
        except PublicStateError as error:
            return self._delegate(None, formulation_id, f"PUBLIC_BOUNDARY:{error}")
        try:
            caps = tuple(self.receipt.capabilities if capabilities is None else capabilities)
        except TypeError:
            caps = ()
        payload_digest = self._payload_digest(state, request, formulation_id, local_deltas_or_request, caps, fixture)
        lifecycle_key = (request.episode_uuid, request.acting_player)
        request_key = (request.episode_uuid, request.acting_player, request.selection_seq)
        cached = self._lifecycle_guard(state, request, formulation_id, payload_digest)
        if cached is not None:
            return cached

        def finish(reason: str, candidates: Sequence[ThreatCandidateV1] = ()) -> ThreatDecisionV1:
            return self._remember(
                lifecycle_key,
                request_key,
                payload_digest,
                request,
                self._delegate(state, formulation_id, reason, candidates),
            )

        if formulation_id not in {A_FORMULATION, B_FORMULATION}:
            return finish("UNKNOWN_FORMULATION")
        if fixture is not None and fixture.successor_fields:
            return finish(SUCCESSOR_VALUE_FORBIDDEN)
        if isinstance(local_deltas_or_request, Mapping):
            local_deltas = local_deltas_or_request
        elif fixture is not None:
            local_deltas = fixture.local_deltas
        else:
            return finish("LOCAL_DELTAS_REQUIRED")
        if capabilities is not None and caps != self.receipt.capabilities:
            return finish("UNREGISTERED_CAPABILITIES")
        if fixture is not None and (fixture.receipt != self.receipt or tuple(fixture.capabilities) != self.receipt.capabilities):
            return finish("UNREGISTERED_CAPABILITIES")
        if self.receipt.scope != FIXTURE_ONLY:
            return finish("NATIVE_OR_UNKNOWN_RECEIPT_SCOPE")
        if request.ordering != "UNORDERED":
            return finish("ORDERED_UNSUPPORTED")
        if request.max_count != 1 or request.min_count not in {0, 1}:
            return finish(COMPOUND_UNSUPPORTED)
        if request.selection_type != 0 or request.selection_context != 0:
            return finish("UNSUPPORTED_REQUEST_CONTEXT")
        if any(option.option_type == 14 for option in request.options):
            return finish(STOP_UNRESOLVED)
        fingerprints = [option.semantic_fingerprint for option in request.options]
        if len(fingerprints) != len(set(fingerprints)):
            return finish("DUPLICATE_SEMANTICS")
        available = tuple(option for option in request.options if option.available)
        if not available:
            return finish("INCOMPLETE_THREAT_COVERAGE")
        expected_keys = {option.semantic_fingerprint for option in available}
        if not isinstance(local_deltas, Mapping) or set(local_deltas) != expected_keys:
            missing = expected_keys - set(local_deltas) if isinstance(local_deltas, Mapping) else expected_keys
            return finish("MISSING_LOCAL_DELTA" if missing else "INCOMPLETE_THREAT_COVERAGE")
        entity_by_key = {entity.entity_key: entity for entity in state.entities}
        entity_keys = set(entity_by_key)
        for option in available:
            option_reason = self._validate_option_semantics(state, option, entity_by_key)
            if option_reason is not None:
                return finish(option_reason)
        graph_reason = self._validate_provenance_graph(local_deltas, caps)
        if graph_reason is not None:
            return finish(graph_reason)
        authority_reason = self._validate_case_authority(
            state, request, local_deltas, caps, fixture
        )
        if authority_reason is not None:
            return finish(authority_reason)
        candidates: list[ThreatCandidateV1] = []
        for option in available:
            delta = local_deltas[option.semantic_fingerprint]
            if not isinstance(delta, ThreatLocalDeltaV1) or delta.option_fingerprint != option.semantic_fingerprint:
                return finish("MISSING_LOCAL_DELTA", candidates)
            if delta.successor_fields:
                return finish(SUCCESSOR_VALUE_FORBIDDEN, candidates)
            if delta.qualification_status != FIXTURE_ONLY:
                return finish("PARTIAL_CAPABILITY", candidates)
            if delta.unknown_fields:
                return finish("UNKNOWN_THREAT_FIELD" if formulation_id == A_FORMULATION else "MISSING_INTERVAL_BOUND", candidates)
            if not delta.action_eligible:
                continue
            if any(item not in entity_keys for item in (option.source_entity_key, option.target_entity_key) if item is not None):
                return finish("UNRESOLVED_PUBLIC_REFERENCE", candidates)
            rows: list[VisibleThreatCapabilityV1] = []
            for capability_id in delta.remaining_capability_ids:
                capability = next(item for item in caps if item.capability_id == capability_id)
                if capability.source_entity_key not in entity_keys or capability.target_entity_key not in entity_keys:
                    return finish("UNRESOLVED_PUBLIC_REFERENCE", candidates)
                source_entity = entity_by_key[capability.source_entity_key]
                target_entity = entity_by_key[capability.target_entity_key]
                if source_entity.owner == state.acting_player:
                    return finish("CAPABILITY_SOURCE_OWNER_MISMATCH", candidates)
                if target_entity.owner != state.acting_player:
                    return finish("CAPABILITY_TARGET_OWNER_MISMATCH", candidates)
                if source_entity.zone not in {AREA["ACTIVE"], AREA["BENCH"]}:
                    return finish("CAPABILITY_SOURCE_ZONE_MISMATCH", candidates)
                if capability.target_requirements == ("VISIBLE_ACTIVE",) and target_entity.zone != AREA["ACTIVE"]:
                    return finish("CAPABILITY_TARGET_ZONE_MISMATCH", candidates)
                if capability.target_requirements == ("VISIBLE_BENCH",) and target_entity.zone != AREA["BENCH"]:
                    return finish("CAPABILITY_TARGET_ZONE_MISMATCH", candidates)
                if capability.status_constraints == ("NO_STATUS",) and target_entity.statuses:
                    return finish("CAPABILITY_STATUS_MISMATCH", candidates)
                if source_entity.card_id != capability.source_card_id:
                    return finish("CAPABILITY_SOURCE_MISMATCH", candidates)
                binding_reason = self._validate_capability_public_binding(
                    capability, source_entity, target_entity
                )
                if binding_reason is not None:
                    return finish(binding_reason, candidates)
                if capability.target_entity_key != option.target_entity_key:
                    return finish("CAPABILITY_TARGET_MISMATCH", candidates)
                if capability.threat_level_scale_id != self.receipt.threat_level_scale.scale_id:
                    return finish("THREAT_SCALE_MISMATCH", candidates)
                field_reason = self._validate_capability_fields(capability, formulation_id)
                if field_reason is not None:
                    return finish(field_reason, candidates)
                rows.append(capability)
            if not rows:
                if not delta.census_complete or not delta.census_receipt_id:
                    return finish("INCOMPLETE_PUBLIC_CENSUS", candidates)
                census = next((item for item in self.receipt.census_receipts if item.receipt_id == delta.census_receipt_id), None)
                if census is None or census.local_delta_receipt_id != delta.receipt_id or census.observation_hash != state.public_hash:
                    return finish("UNREGISTERED_CENSUS_RECEIPT", candidates)
                if census.source_scope != (option.source_entity_key,) or census.target_scope != (option.target_entity_key,):
                    return finish("INCOMPLETE_PUBLIC_CENSUS", candidates)
                lower = upper = unknown_count = 0
            else:
                lower = max(item.guaranteed_level for item in rows if item.guaranteed_level is not None)
                upper = max(item.possible_level for item in rows if item.possible_level is not None)
                unknown_count = sum(len(item.unknown_fields) for item in rows)
            try:
                self.receipt.threat_level_scale.validate_level(lower, "guaranteed_level")
                self.receipt.threat_level_scale.validate_level(upper, "possible_level")
            except ValueError:
                return finish("INVALID_THREAT_INTERVAL", candidates)
            candidates.append(ThreatCandidateV1(
                option=option,
                action_key=delta.action_key,
                guaranteed_level=lower,
                possible_level=upper,
                interval_width=Fraction(upper - lower, 1),
                unknown_count=unknown_count,
                response_count=len(rows),
                route_support_denial_count=sum(item.response_class == "REMOVE_ROUTE_SUPPORT" for item in rows),
                ready_capability_count=sum(item.ready_now is True for item in rows),
                capability_ids=tuple(item.capability_id for item in rows),
            ))
        if not candidates:
            if request.min_count == 0:
                action = self.build_optional_stop(request)
                result = _decision(SELECTED, state, formulation_id, key=("STOP",), action=action)
                self._diagnostics.selected += 1
                return self._remember(lifecycle_key, request_key, payload_digest, request, result)
            return finish("NO_COVERED_ACTION")
        if formulation_id == A_FORMULATION:
            keys = {candidate: (candidate.possible_level, candidate.response_count, -candidate.route_support_denial_count, -candidate.ready_capability_count) for candidate in candidates}
            best_key = min(keys.values())
            top = [candidate for candidate in candidates if keys[candidate] == best_key]
        else:
            dominates = [candidate for candidate in candidates if all(
                candidate.guaranteed_level <= other.guaranteed_level
                and candidate.possible_level <= other.possible_level
                and (candidate.guaranteed_level < other.guaranteed_level or candidate.possible_level < other.possible_level)
                for other in candidates if other is not candidate
            )]
            if len(dominates) != 1:
                return finish("INTERVALS_INCOMPARABLE", candidates)
            top = dominates
            best_key = (top[0].guaranteed_level, top[0].possible_level, top[0].interval_width.numerator, top[0].interval_width.denominator)
        if len(top) != 1:
            return finish("AMBIGUOUS_NON_EQUIVALENT_TIE", candidates)
        selected = top[0]
        builder = CompoundActionBuilder(request)
        model_index = next(index for index, option in enumerate(request.options) if option.semantic_fingerprint == selected.option.semantic_fingerprint)
        builder.choose(model_index)
        result = _decision(SELECTED, state, formulation_id, key=best_key, candidates=candidates, chosen=selected, action=builder.build())
        self._diagnostics.selected += 1
        return self._remember(lifecycle_key, request_key, payload_digest, request, result)

    def evaluate_case(
        self, case: B4FixtureCaseV1, formulation_id: str = A_FORMULATION
    ) -> ThreatDecisionV1:
        """Evaluate a materialized fixture, retaining its boundary metadata."""

        if not isinstance(case, B4FixtureCaseV1):
            raise TypeError("B4 evaluate_case requires a B4FixtureCaseV1")
        return self.evaluate(
            case.state,
            case.local_deltas,
            formulation_id,
            capabilities=case.capabilities,
            fixture=case,
        )

    def evaluate(
        self,
        state_or_observation: PublicStateV1 | EngineObservationV1,
        local_deltas_or_request: Mapping[str, ThreatLocalDeltaV1] | SelectionRequestV1 | None,
        formulation_id: str = A_FORMULATION,
        *,
        capabilities: Sequence[VisibleThreatCapabilityV1] | None = None,
        fixture: B4FixtureCaseV1 | None = None,
    ) -> ThreatDecisionV1:
        return self._evaluate_strict(
            state_or_observation,
            local_deltas_or_request,
            formulation_id,
            capabilities=capabilities,
            fixture=fixture,
        )



__all__ = [
    "A_FORMULATION", "AMBIGUOUS", "B0_DELEGATE", "B4CapabilityReceiptV1", "B4FixtureBundleV1",
    "B4FixtureCaseV1", "B4_SCHEMA_VERSION", "B_FORMULATION", "COMPOUND_UNSUPPORTED", "FIXTURE_ONLY",
    "CurrentOpponentThreatEvaluatorV1", "STOP_UNRESOLVED", "SELECTED", "SUCCESSOR_VALUE_FORBIDDEN",
    "TERMINAL_OVERRIDE", "ThreatCandidateV1", "ThreatDecisionV1", "ThreatLevelScaleV1", "PublicCensusReceiptV1",
    "ThreatLocalDeltaV1", "VisibleThreatCapabilityV1", "load_b4_fixtures", "materialize_b4_fixture_data",
    "mirror_b4_case", "semantic_permutation_suite",
]
