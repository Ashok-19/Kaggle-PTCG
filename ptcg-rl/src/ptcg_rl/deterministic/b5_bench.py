"""Fixture-only Phase B5 bench role/liability experiment.

The module is deliberately below the native adapter.  It accepts a complete
public current snapshot and sealed fixture receipts, then either makes the
small, auditable B5-A/B choice or delegates to the frozen B0 control.  No
card prose, hidden cards, successor values, response probabilities, or native
engine calls are interpreted here.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import re
from dataclasses import dataclass, field as dataclass_field, fields, replace
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

from .state import PublicStateV1


B5_SCHEMA_VERSION = 1
FIXTURE_ONLY = "FIXTURE_ONLY"
A_FORMULATION = "B5-A-CAPACITY-ROUTE-ROLE-RESERVE"
B_FORMULATION = "B5-B-RECEIPT-BOUNDED-LIABILITY-DOMINANCE"
SELECTED = "SELECTED"
B0_DELEGATE = "B0_DELEGATE"
AMBIGUOUS = "AMBIGUOUS"
TERMINAL_OVERRIDE = "TERMINAL_OVERRIDE"
COMPOUND_UNSUPPORTED = "COMPOUND_UNSUPPORTED"
STOP_UNRESOLVED = "STOP_UNRESOLVED"
SUCCESSOR_VALUE_FORBIDDEN = "SUCCESSOR_VALUE_FORBIDDEN"
HIDDEN_INFORMATION_FORBIDDEN = "HIDDEN_INFORMATION_FORBIDDEN"
CARD_PROSE_FORBIDDEN = "CARD_PROSE_FORBIDDEN"
UNKNOWN_CURRENT_RECEIPT = "UNKNOWN_CURRENT_RECEIPT"
ROLE_FLOOR_UNSATISFIED = "ROLE_FLOOR_UNSATISFIED"
NONFINITE_OR_INVALID_LIABILITY = "NONFINITE_OR_INVALID_LIABILITY"
MALFORMED_LOCAL_DELTAS = "MALFORMED_LOCAL_DELTAS"
EXPERIMENTAL_BENCH_AUTHORITY = "EXPERIMENTAL_BENCH"
B0_DELEGATION_AUTHORITY = "B0_CONTROL_DELEGATION"
_FIXTURE_RECORD_ID = "phase-b5-bench-liability-fixture-v1"
_CONFIG_RELATIVE = Path("configs/deterministic/phase_b5_bench_liability_fixture_v1.json")
_IMPLEMENTATION_PATH = Path("src/ptcg_rl/deterministic/b5_bench.py")
# The source digest is normalized to zeros before hashing, avoiding a
# self-referential literal while still binding the loaded implementation.
B5_CANONICAL_FIXTURE_DIGEST = "4e45147390df5702ae231fbc02fb67b21fb3ed433119ab5b0ec83651064aec32"
B5_IMPLEMENTATION_SOURCE_SHA256 = "4aff7dd8e4a296dff1992cfce9961d0ba55213213753e5b01fa780b3a831685b"

_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_QUALIFICATION_STATUS = frozenset({"QUALIFIED_CABT_CAPSULE", FIXTURE_ONLY, "PARTIAL", "CONFLICT", "UNKNOWN"})
_ROLE_IDS = frozenset({
    "NEXT_ATTACKER", "BACKUP_ATTACKER", "DRAW_ENGINE", "PIVOT", "ROUTE_SUPPORT",
    "GUST_TARGET", "SPREAD_TARGET", "LIABILITY", "UNCLASSIFIED",
})
_ROLE_STATUS = frozenset({"COVERED", "REQUIRED_UNCOVERED", "EXPOSED", "CONFLICT", "UNKNOWN"})
_NECESSITY = frozenset({"REQUIRED", "USEFUL", "OPTIONAL", "EXPOSED", "FORBIDDEN", "UNKNOWN"})
_CURRENT_FIELD_ALLOWLIST = frozenset({"bench_occupancy", "role_coverage", "local_legality"})
_HIDDEN_FIELD_TOKENS = frozenset({"hidden", "private", "opponent_hand", "opponent_deck", "opponent_prize", "facedown", "unknown_identity"})
_SUCCESSOR_FIELD_TOKENS = frozenset({"successor", "post_action", "future", "terminal", "response", "next_state", "changed_hp", "changed_status"})
_PROSE_FIELD_TOKENS = frozenset({"prose", "text", "card_name", "static_damage", "card_effect", "description", "attack_text"})
_RESPONSE_CLASSES = frozenset({"NONE", "ROUTE_CONVERTING", "DISRUPTIVE"})
_DEPENDENCY_PATHS = (
    _IMPLEMENTATION_PATH,
    Path("src/ptcg_rl/g1/models.py"),
    Path("src/ptcg_rl/g1/actions.py"),
    Path("src/ptcg_rl/g1/semantic.py"),
    Path("src/ptcg_rl/deterministic/state.py"),
)


def _digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _DIGEST_RE.fullmatch(value):
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


def _strict_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be boolean")
    return value


def _strict_tuple_strings(value: Any, field: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        raise ValueError(f"{field} must be a sequence")
    result = tuple(value)
    if not allow_empty and not result:
        raise ValueError(f"{field} must not be empty")
    if any(not isinstance(item, str) or not item for item in result):
        raise ValueError(f"{field} entries must be nonempty strings")
    return result


def _finite_number(value: Any, field: str) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a finite number")
    if not math.isfinite(float(value)):
        raise ValueError(f"{field} must be finite")
    return value


def _canonical_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _canonical_value(item) for key, item in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (tuple, list, frozenset)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "__dataclass_fields__"):
        return {item.name: _canonical_value(getattr(value, item.name)) for item in fields(value)}
    return value


def _sha_json(value: Any) -> str:
    raw = json.dumps(_canonical_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class BenchLiabilityScaleV1:
    """Shared lower-is-safer ordinal scale for the three liability axes."""

    schema_version: int
    scale_id: str
    lower_is_safer: bool
    prize_levels: tuple[tuple[int, str], ...]
    gust_levels: tuple[tuple[int, str], ...]
    spread_levels: tuple[tuple[int, str], ...]
    scope: str = FIXTURE_ONLY
    exact_integer_type: str = "int"
    scale_content_sha256: str = "f" * 64
    qualification_status: str = FIXTURE_ONLY
    review_id: str = "phase-b5-bench-liability-design-v1-review"
    fixture_content_sha256: str = "f" * 64
    fixture_config_sha256: str = "f" * 64
    receipt_manifest_sha256: str = "f" * 64
    scope_version: str = "fixture-scope-v1"

    def __post_init__(self) -> None:
        if self.schema_version != B5_SCHEMA_VERSION or isinstance(self.schema_version, bool):
            raise ValueError("unknown BenchLiabilityScaleV1 schema")
        _nonempty(self.scale_id, "scale_id")
        if self.scope != FIXTURE_ONLY or not self.lower_is_safer:
            raise ValueError("B5 scale must be fixture-only and lower-is-safer")
        if not isinstance(self.lower_is_safer, bool):
            raise ValueError("lower_is_safer must be boolean")
        if self.exact_integer_type != "int":
            raise ValueError("B5 scale requires exact integer ordinals")
        if self.qualification_status not in _QUALIFICATION_STATUS:
            raise ValueError("unknown B5 scale qualification status")
        _nonempty(self.review_id, "review_id")
        _nonempty(self.scope_version, "scope_version")
        for name in ("scale_content_sha256", "fixture_content_sha256", "fixture_config_sha256", "receipt_manifest_sha256"):
            _digest(getattr(self, name), name)
        expected = ("NONE", "LOW", "MEDIUM", "HIGH")
        for name in ("prize_levels", "gust_levels", "spread_levels"):
            rows = getattr(self, name)
            if not isinstance(rows, tuple) or any(not isinstance(row, tuple) or len(row) != 2 for row in rows):
                raise ValueError(f"{name} must contain two-field rows")
            if tuple(level for level, _ in rows) != tuple(range(len(rows))):
                raise ValueError(f"{name} ordinals must start at zero and be contiguous")
            if tuple(label for _, label in rows) != expected:
                raise ValueError(f"{name} labels do not match the sealed fixture scale")
            if len({label for _, label in rows}) != len(rows):
                raise ValueError(f"{name} labels must be unique")
            for level, label in rows:
                _nonnegative_int(level, f"{name}.level")
                _nonempty(label, f"{name}.label")
        expected_content = _sha_json({
            "schema_version": self.schema_version, "scale_id": self.scale_id, "lower_is_safer": self.lower_is_safer,
            "prize_levels": self.prize_levels, "gust_levels": self.gust_levels, "spread_levels": self.spread_levels,
            "scope": self.scope, "exact_integer_type": self.exact_integer_type,
            "qualification_status": self.qualification_status, "review_id": self.review_id, "scope_version": self.scope_version,
        })
        if self.scale_content_sha256 != expected_content and self.scale_content_sha256 != "f" * 64:
            raise ValueError("scale_content_sha256 does not match the sealed scale")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "BenchLiabilityScaleV1":
        required = {
            "schema_version", "scale_id", "lower_is_safer", "prize_levels", "gust_levels", "spread_levels", "scope",
            "exact_integer_type", "scale_content_sha256", "qualification_status", "review_id",
            "fixture_content_sha256", "fixture_config_sha256", "receipt_manifest_sha256", "scope_version",
        }
        if not isinstance(value, Mapping) or set(value) != required:
            raise ValueError("BenchLiabilityScaleV1 config fields are incomplete or unknown")
        rows = {}
        for name in ("prize_levels", "gust_levels", "spread_levels"):
            if not isinstance(value[name], (tuple, list)):
                raise ValueError(f"{name} must be a sequence")
            rows[name] = tuple(tuple(item) for item in value[name])
        converted = dict(value)
        converted.update(rows)
        return cls(**converted)

    def validate_level(self, value: Any, field: str) -> int:
        value = _nonnegative_int(value, field)
        if value >= len(self.prize_levels) or value >= len(self.gust_levels) or value >= len(self.spread_levels):
            raise ValueError(f"{field} is outside the sealed scale")
        return value


@dataclass(frozen=True)
class BenchRoleReceiptV1:
    receipt_id: str
    entity_key: str
    card_id: int
    owner: int
    zone: int
    role_id: str
    role_status: str
    route_id: str
    necessity: str
    required_count: int
    source_observation_digest: str
    candidate_deck_profile: str
    candidate_deck_sha256: str
    card_data_sha256: str
    card_table_semantic_sha256: str
    scope_version: str
    qualification_status: str
    content_sha256: str
    qualification_id: str = ""
    metadata_ref: str = ""
    card_table_file_sha256: str = "f" * 64
    fixture_content_sha256: str = "f" * 64
    fixture_config_sha256: str = "f" * 64
    receipt_manifest_sha256: str = "f" * 64

    def __post_init__(self) -> None:
        _nonempty(self.receipt_id, "role receipt_id")
        _nonempty(self.entity_key, "role entity_key")
        _nonnegative_int(self.card_id, "role card_id")
        if self.owner not in (0, 1) or isinstance(self.owner, bool):
            raise ValueError("role owner must be player 0 or player 1")
        _nonnegative_int(self.zone, "role zone")
        if self.role_id not in _ROLE_IDS or self.role_status not in _ROLE_STATUS or self.necessity not in _NECESSITY:
            raise ValueError("unknown role receipt enum")
        _nonempty(self.route_id, "route_id")
        _nonnegative_int(self.required_count, "required_count")
        _digest(self.source_observation_digest, "source_observation_digest")
        _nonempty(self.qualification_id, "qualification_id")
        _nonempty(self.metadata_ref, "metadata_ref")
        _nonempty(self.candidate_deck_profile, "candidate_deck_profile")
        for name in (
            "candidate_deck_sha256", "card_data_sha256", "card_table_file_sha256", "card_table_semantic_sha256",
            "fixture_content_sha256", "fixture_config_sha256", "receipt_manifest_sha256", "content_sha256",
        ):
            _digest(getattr(self, name), name)
        _nonempty(self.scope_version, "scope_version")
        if self.qualification_status not in _QUALIFICATION_STATUS:
            raise ValueError("unknown role qualification status")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "BenchRoleReceiptV1":
        if not isinstance(value, Mapping) or set(value) != {item.name for item in fields(cls)}:
            raise ValueError("role receipt fields are incomplete or unknown")
        return cls(**dict(value))


@dataclass(frozen=True)
class BenchLocalDeltaV1:
    option_fingerprint: str
    receipt_id: str
    qualification_status: str
    current_public_observation_digest: str
    source_entity_key: str
    target_entity_key: str | None
    choice_role: str
    before_bench_occupancy: int
    after_bench_occupancy: int
    before_role_coverage: Mapping[str, int]
    after_role_coverage: Mapping[str, int]
    after_role_surplus: Mapping[str, int]
    required_role_counts: Mapping[str, int]
    affected_role_receipt_ids: tuple[str, ...]
    action_key: str
    action_eligible: bool = True
    current_public_fields: tuple[str, ...] = ("bench_occupancy", "role_coverage", "local_legality")
    unknown_fields: tuple[str, ...] = ()
    successor_fields: tuple[str, ...] = ()
    scope: str = FIXTURE_ONLY
    content_sha256: str = "f" * 64
    option_semantic_fingerprint: str = ""
    option_semantic_payload_digest: str = "f" * 64
    selection_type: int = 0
    selection_context: int = 0
    option_type: int = 7
    source_card_id: int | None = None
    target_card_id: int | None = None
    source_owner: int = 0
    target_owner: int | None = None
    source_zone: int = AREA["HAND"]
    target_zone: int | None = None
    source_metadata_ref: str = ""
    target_metadata_ref: str | None = None
    qualification_id: str = ""
    no_successor_fields: bool = True
    scope_version: str = "fixture-scope-v1"
    fixture_content_sha256: str = "f" * 64
    fixture_config_sha256: str = "f" * 64
    receipt_manifest_sha256: str = "f" * 64

    def __post_init__(self) -> None:
        _digest(self.option_fingerprint, "option_fingerprint")
        if self.option_semantic_fingerprint and self.option_semantic_fingerprint != self.option_fingerprint:
            raise ValueError("option semantic fingerprint aliases must agree")
        object.__setattr__(self, "option_semantic_fingerprint", self.option_fingerprint)
        _digest(self.option_semantic_payload_digest, "option_semantic_payload_digest")
        _nonempty(self.receipt_id, "local delta receipt_id")
        if self.qualification_status not in _QUALIFICATION_STATUS or self.scope != FIXTURE_ONLY:
            raise ValueError("unknown local-delta scope or qualification")
        _digest(self.current_public_observation_digest, "current_public_observation_digest")
        _nonempty(self.source_entity_key, "source_entity_key")
        if self.target_entity_key is not None:
            _nonempty(self.target_entity_key, "target_entity_key")
        if self.choice_role != "PLAY":
            raise ValueError("B5 bench local delta requires PLAY choice role")
        for name in ("selection_type", "selection_context", "option_type", "source_card_id", "target_card_id", "source_owner", "target_owner", "source_zone", "target_zone"):
            value = getattr(self, name)
            if value is not None:
                _nonnegative_int(value, name)
        if self.selection_type != 0 or self.selection_context != 0 or self.option_type != 7:
            raise ValueError("unsupported B5 local-delta option enum")
        if self.source_owner not in (0, 1) or (self.target_owner is not None and self.target_owner not in (0, 1)):
            raise ValueError("local-delta owner enum is outside public scope")
        if self.source_zone != AREA["HAND"] or self.target_zone not in (None, AREA["BENCH"], AREA["ME"]):
            raise ValueError("local-delta zone enum is outside bench scope")
        _nonempty(self.source_metadata_ref, "source_metadata_ref")
        if self.target_metadata_ref is not None:
            _nonempty(self.target_metadata_ref, "target_metadata_ref")
        _nonempty(self.qualification_id, "qualification_id")
        _nonempty(self.scope_version, "scope_version")
        if not isinstance(self.no_successor_fields, bool) or not self.no_successor_fields:
            raise ValueError("local delta must explicitly exclude successor fields")
        for name in ("before_bench_occupancy", "after_bench_occupancy"):
            value = getattr(self, name)
            # Keep malformed numeric mutations representable so the evaluator
            # can fail closed with its boundary-specific reason (rather than
            # allowing construction to turn NaN/Inf into an exception path).
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be numeric")
            if math.isfinite(float(value)) and value < 0:
                raise ValueError(f"{name} must be nonnegative")
        for name in ("before_role_coverage", "after_role_coverage", "after_role_surplus", "required_role_counts"):
            _validate_role_map(getattr(self, name), name)
            object.__setattr__(self, name, MappingProxyType(dict(getattr(self, name))))
        _strict_tuple_strings(self.affected_role_receipt_ids, "affected_role_receipt_ids", allow_empty=False)
        _nonempty(self.action_key, "action_key")
        if not isinstance(self.action_eligible, bool):
            raise ValueError("action_eligible must be boolean")
        for name in ("current_public_fields", "unknown_fields", "successor_fields"):
            _strict_tuple_strings(getattr(self, name), name, allow_empty=(name != "current_public_fields"))
        for name in ("fixture_content_sha256", "fixture_config_sha256", "receipt_manifest_sha256", "content_sha256"):
            _digest(getattr(self, name), name)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "BenchLocalDeltaV1":
        if not isinstance(value, Mapping) or set(value) != {item.name for item in fields(cls)}:
            raise ValueError("local delta fields are incomplete or unknown")
        converted = dict(value)
        for name in ("affected_role_receipt_ids", "current_public_fields", "unknown_fields", "successor_fields"):
            converted[name] = tuple(converted[name])
        return cls(**converted)


def _validate_role_map(value: Mapping[str, int], field: str) -> None:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be a mapping")
    for key, item in value.items():
        if key not in _ROLE_IDS:
            raise ValueError(f"{field} contains an unknown role")
        _nonnegative_int(item, f"{field}.{key}")


@dataclass(frozen=True)
class PrizeStaticV1:
    receipt_id: str
    entity_key: str
    card_id: int
    prize_units: int
    engine_hash: str
    card_data_sha256: str
    scope_version: str
    qualification_status: str
    content_sha256: str
    native_library_sha256: str = "f" * 64
    wrapper_hashes: Mapping[str, str] = dataclass_field(default_factory=lambda: {"game": "f" * 64, "api": "f" * 64, "sim": "f" * 64})
    card_table_file_sha256: str = "f" * 64
    card_table_semantic_sha256: str = "f" * 64
    metadata_ref: str = ""
    source_observation_digest: str = "f" * 64
    candidate_deck_profile: str = "fixture-candidate"
    candidate_deck_sha256: str = "f" * 64
    anchor_deck_profile: str = "fixture-anchor"
    anchor_deck_sha256: str = "f" * 64
    qualification_id: str = ""
    fixture_content_sha256: str = "f" * 64
    fixture_config_sha256: str = "f" * 64
    receipt_manifest_sha256: str = "f" * 64

    def __post_init__(self) -> None:
        for name in ("receipt_id", "entity_key", "scope_version"):
            _nonempty(getattr(self, name), name)
        _nonnegative_int(self.card_id, "card_id")
        _nonnegative_int(self.prize_units, "prize_units")
        for name in (
            "engine_hash", "native_library_sha256", "card_data_sha256", "card_table_file_sha256", "card_table_semantic_sha256", "source_observation_digest",
            "candidate_deck_sha256", "anchor_deck_sha256", "fixture_content_sha256", "fixture_config_sha256",
            "receipt_manifest_sha256", "content_sha256",
        ):
            _digest(getattr(self, name), name)
        if not isinstance(self.wrapper_hashes, Mapping) or set(self.wrapper_hashes) != {"game", "api", "sim"}:
            raise ValueError("Prize wrapper hash scope is incomplete")
        for name, value in self.wrapper_hashes.items():
            _digest(value, f"wrapper_hashes.{name}")
        object.__setattr__(self, "wrapper_hashes", MappingProxyType(dict(self.wrapper_hashes)))
        for name in ("metadata_ref", "candidate_deck_profile", "anchor_deck_profile", "qualification_id"):
            _nonempty(getattr(self, name), name)
        if self.qualification_status not in _QUALIFICATION_STATUS:
            raise ValueError("unknown Prize qualification status")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "PrizeStaticV1":
        if not isinstance(value, Mapping) or set(value) != {item.name for item in fields(cls)}:
            raise ValueError("Prize static fields are incomplete or unknown")
        return cls(**dict(value))


@dataclass(frozen=True)
class GustExposureV1:
    receipt_id: str
    source_entity_key: str
    target_entity_key: str
    target_role: str
    current_targetable: bool
    route_conversion_class: str
    exposure_level: int
    engine_hash: str
    candidate_deck_sha256: str
    anchor_deck_sha256: str
    scope_version: str
    qualification_status: str
    content_sha256: str
    candidate_deck_profile: str = "fixture-candidate"
    qualification_id: str = ""
    option_semantic_fingerprint: str = "f" * 64
    current_public_observation_digest: str = "f" * 64
    source_card_id: int = 0
    target_card_id: int = 0
    source_owner: int = 1
    target_owner: int = 0
    source_zone: int = AREA["ACTIVE"]
    target_zone: int = AREA["HAND"]
    source_metadata_ref: str = ""
    target_metadata_ref: str = ""
    native_library_sha256: str = "f" * 64
    wrapper_hashes: Mapping[str, str] = dataclass_field(default_factory=lambda: {"game": "f" * 64, "api": "f" * 64, "sim": "f" * 64})
    card_data_sha256: str = "f" * 64
    card_table_file_sha256: str = "f" * 64
    card_table_semantic_sha256: str = "f" * 64
    anchor_deck_profile: str = "fixture-anchor"
    fixture_content_sha256: str = "f" * 64
    fixture_config_sha256: str = "f" * 64
    receipt_manifest_sha256: str = "f" * 64

    def __post_init__(self) -> None:
        for name in ("receipt_id", "source_entity_key", "target_entity_key", "target_role", "scope_version"):
            _nonempty(getattr(self, name), name)
        if not isinstance(self.current_targetable, bool) or self.route_conversion_class not in _RESPONSE_CLASSES:
            raise ValueError("invalid gust exposure semantics")
        _nonnegative_int(self.exposure_level, "exposure_level")
        for name in (
            "source_card_id", "target_card_id", "source_owner", "target_owner", "source_zone", "target_zone",
        ):
            _nonnegative_int(getattr(self, name), name)
        if self.source_owner not in (0, 1) or self.target_owner not in (0, 1):
            raise ValueError("gust owner enum is outside public scope")
        for name in ("qualification_id", "source_metadata_ref", "target_metadata_ref", "candidate_deck_profile", "anchor_deck_profile"):
            _nonempty(getattr(self, name), name)
        for name in (
            "engine_hash", "native_library_sha256", "candidate_deck_sha256", "anchor_deck_sha256", "card_data_sha256",
            "card_table_file_sha256", "card_table_semantic_sha256", "option_semantic_fingerprint",
            "current_public_observation_digest", "fixture_content_sha256", "fixture_config_sha256",
            "receipt_manifest_sha256", "content_sha256",
        ):
            _digest(getattr(self, name), name)
        if not isinstance(self.wrapper_hashes, Mapping) or set(self.wrapper_hashes) != {"game", "api", "sim"}:
            raise ValueError("gust wrapper hash scope is incomplete")
        for name, value in self.wrapper_hashes.items():
            _digest(value, f"wrapper_hashes.{name}")
        object.__setattr__(self, "wrapper_hashes", MappingProxyType(dict(self.wrapper_hashes)))
        if self.qualification_status not in _QUALIFICATION_STATUS:
            raise ValueError("unknown gust qualification status")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "GustExposureV1":
        if not isinstance(value, Mapping) or set(value) != {item.name for item in fields(cls)}:
            raise ValueError("gust exposure fields are incomplete or unknown")
        return cls(**dict(value))


@dataclass(frozen=True)
class SpreadExposureV1:
    receipt_id: str
    source_entity_key: str
    target_entity_key: str
    target_role: str
    current_spread_threshold: int
    current_damage_counter_state: int
    response_class: str
    exposure_level: int
    engine_hash: str
    candidate_deck_sha256: str
    anchor_deck_sha256: str
    scope_version: str
    qualification_status: str
    content_sha256: str
    candidate_deck_profile: str = "fixture-candidate"
    qualification_id: str = ""
    option_semantic_fingerprint: str = "f" * 64
    current_public_observation_digest: str = "f" * 64
    source_card_id: int = 0
    target_card_id: int = 0
    source_owner: int = 1
    target_owner: int = 0
    source_zone: int = AREA["ACTIVE"]
    target_zone: int = AREA["HAND"]
    source_metadata_ref: str = ""
    target_metadata_ref: str = ""
    native_library_sha256: str = "f" * 64
    wrapper_hashes: Mapping[str, str] = dataclass_field(default_factory=lambda: {"game": "f" * 64, "api": "f" * 64, "sim": "f" * 64})
    card_data_sha256: str = "f" * 64
    card_table_file_sha256: str = "f" * 64
    card_table_semantic_sha256: str = "f" * 64
    anchor_deck_profile: str = "fixture-anchor"
    fixture_content_sha256: str = "f" * 64
    fixture_config_sha256: str = "f" * 64
    receipt_manifest_sha256: str = "f" * 64

    def __post_init__(self) -> None:
        for name in ("receipt_id", "source_entity_key", "target_entity_key", "target_role", "scope_version"):
            _nonempty(getattr(self, name), name)
        for name in ("current_spread_threshold", "current_damage_counter_state", "exposure_level"):
            _nonnegative_int(getattr(self, name), name)
        if self.response_class not in _RESPONSE_CLASSES:
            raise ValueError("invalid spread response class")
        for name in ("source_card_id", "target_card_id", "source_owner", "target_owner", "source_zone", "target_zone"):
            _nonnegative_int(getattr(self, name), name)
        if self.source_owner not in (0, 1) or self.target_owner not in (0, 1):
            raise ValueError("spread owner enum is outside public scope")
        for name in ("qualification_id", "source_metadata_ref", "target_metadata_ref", "candidate_deck_profile", "anchor_deck_profile"):
            _nonempty(getattr(self, name), name)
        for name in ("engine_hash", "candidate_deck_sha256", "anchor_deck_sha256", "content_sha256"):
            _digest(getattr(self, name), name)
        for name in (
            "native_library_sha256", "card_data_sha256", "card_table_file_sha256", "card_table_semantic_sha256",
            "option_semantic_fingerprint", "current_public_observation_digest", "fixture_content_sha256",
            "fixture_config_sha256", "receipt_manifest_sha256",
        ):
            _digest(getattr(self, name), name)
        if not isinstance(self.wrapper_hashes, Mapping) or set(self.wrapper_hashes) != {"game", "api", "sim"}:
            raise ValueError("spread wrapper hash scope is incomplete")
        for name, value in self.wrapper_hashes.items():
            _digest(value, f"wrapper_hashes.{name}")
        object.__setattr__(self, "wrapper_hashes", MappingProxyType(dict(self.wrapper_hashes)))
        if self.qualification_status not in _QUALIFICATION_STATUS:
            raise ValueError("unknown spread qualification status")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SpreadExposureV1":
        if not isinstance(value, Mapping) or set(value) != {item.name for item in fields(cls)}:
            raise ValueError("spread exposure fields are incomplete or unknown")
        return cls(**dict(value))


@dataclass(frozen=True)
class B5CapabilityReceiptV1:
    receipt_id: str
    scope: str
    fixture_case_id: str
    scale: BenchLiabilityScaleV1
    role_receipts: tuple[BenchRoleReceiptV1, ...]
    local_deltas: tuple[BenchLocalDeltaV1, ...]
    prize_static: tuple[PrizeStaticV1, ...]
    gust_exposures: tuple[GustExposureV1, ...]
    spread_exposures: tuple[SpreadExposureV1, ...]
    provenance_manifest: Mapping[str, Any]
    content_sha256: str

    def __post_init__(self) -> None:
        if self.receipt_id != _FIXTURE_RECORD_ID or self.scope != FIXTURE_ONLY:
            raise ValueError("unknown B5 receipt scope or record")
        _nonempty(self.fixture_case_id, "fixture_case_id")
        if not isinstance(self.scale, BenchLiabilityScaleV1):
            raise ValueError("B5 receipt requires BenchLiabilityScaleV1")
        for name, typ in (
            ("role_receipts", BenchRoleReceiptV1), ("local_deltas", BenchLocalDeltaV1),
            ("prize_static", PrizeStaticV1), ("gust_exposures", GustExposureV1),
            ("spread_exposures", SpreadExposureV1),
        ):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(not isinstance(item, typ) for item in values):
                raise ValueError(f"{name} must be immutable typed rows")
            ids = [item.receipt_id for item in values]
            if len(ids) != len(set(ids)):
                raise ValueError(f"{name} receipt ids must be unique")
        if not isinstance(self.provenance_manifest, Mapping):
            raise ValueError("B5 receipt requires provenance manifest")
        required_manifest = {
            "schema_id", "schema_version", "fixture_metadata_sha256", "config_payload_sha256", "knowledge_base_sha256", "source_hashes",
            "engine_hash", "native_library_sha256", "game_wrapper_sha256", "api_wrapper_sha256", "sim_wrapper_sha256",
            "card_data_sha256", "card_table_file_sha256", "card_table_semantic_sha256", "candidate_deck_profile", "candidate_deck_sha256",
            "anchor_deck_profile", "anchor_deck_sha256", "scope_version", "scale_id", "policy_id", "implementation_sha256",
            "transitive_source_hashes", "config_sha256", "schema_hashes", "dependency_scan_digest", "wrapper_hashes",
            "fixture_content_sha256", "fixture_config_sha256", "receipt_manifest_sha256",
        }
        if set(self.provenance_manifest) != required_manifest:
            raise ValueError("B5 receipt provenance manifest is incomplete or unknown")
        for name in (
            "fixture_metadata_sha256", "config_payload_sha256", "knowledge_base_sha256", "engine_hash", "native_library_sha256",
            "game_wrapper_sha256", "api_wrapper_sha256", "sim_wrapper_sha256", "card_data_sha256", "card_table_file_sha256",
            "card_table_semantic_sha256", "candidate_deck_sha256", "anchor_deck_sha256", "implementation_sha256", "config_sha256",
            "dependency_scan_digest", "fixture_content_sha256", "fixture_config_sha256", "receipt_manifest_sha256",
        ):
            _digest(self.provenance_manifest[name], f"provenance.{name}")
        for name in ("candidate_deck_profile", "anchor_deck_profile", "scope_version", "policy_id", "scale_id"):
            _nonempty(self.provenance_manifest[name], f"provenance.{name}")
        if self.provenance_manifest["schema_id"] != _FIXTURE_RECORD_ID or self.provenance_manifest["schema_version"] != B5_SCHEMA_VERSION:
            raise ValueError("B5 receipt provenance identity is unknown")
        for name in ("source_hashes", "transitive_source_hashes", "schema_hashes"):
            if not isinstance(self.provenance_manifest[name], Mapping):
                raise ValueError(f"provenance.{name} must be a mapping")
        if not isinstance(self.provenance_manifest["wrapper_hashes"], Mapping) or set(self.provenance_manifest["wrapper_hashes"]) != {"game", "api", "sim"}:
            raise ValueError("provenance.wrapper_hashes is incomplete")
        for name, value in self.provenance_manifest["wrapper_hashes"].items():
            _digest(value, f"provenance.wrapper_hashes.{name}")
        _nonempty(self.provenance_manifest["scope_version"], "provenance.scope_version")
        _digest(self.content_sha256, "content_sha256")
        object.__setattr__(self, "provenance_manifest", MappingProxyType(dict(self.provenance_manifest)))

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "B5CapabilityReceiptV1":
        required = {item.name for item in fields(cls)}
        if not isinstance(value, Mapping) or set(value) != required:
            raise ValueError("B5 receipt fields are incomplete or unknown")
        return cls(
            receipt_id=value["receipt_id"], scope=value["scope"], fixture_case_id=value["fixture_case_id"],
            scale=BenchLiabilityScaleV1.from_dict(value["scale"]),
            role_receipts=tuple(BenchRoleReceiptV1.from_dict(item) for item in value["role_receipts"]),
            local_deltas=tuple(BenchLocalDeltaV1.from_dict(item) for item in value["local_deltas"]),
            prize_static=tuple(PrizeStaticV1.from_dict(item) for item in value["prize_static"]),
            gust_exposures=tuple(GustExposureV1.from_dict(item) for item in value["gust_exposures"]),
            spread_exposures=tuple(SpreadExposureV1.from_dict(item) for item in value["spread_exposures"]),
            provenance_manifest=dict(value["provenance_manifest"]), content_sha256=value["content_sha256"],
        )


@dataclass(frozen=True)
class BenchCandidateV1:
    option: LegalOptionV1
    action_key: str
    role_feasible: bool
    remaining_required_slots: int
    backup_surplus: int
    next_surplus: int
    capacity_slack: int
    liability: tuple[int, int, int]


@dataclass(frozen=True)
class BenchDecisionV1:
    schema_version: int
    request_id: str
    selection_seq: int
    acting_player: int | None
    policy_id: str
    formulation_id: str
    status: str
    authority: str
    chosen_action_key: tuple[str, ...] = ()
    chosen_semantic_action_key: str | None = None
    chosen_option_fingerprints: tuple[str, ...] = ()
    chosen_original_indices: tuple[int, ...] = ()
    decision_key: tuple[Any, ...] = ()
    candidate_count: int = 0
    fail_closed_reason: str | None = None
    candidates: tuple[BenchCandidateV1, ...] = ()
    receipt_scope: str = FIXTURE_ONLY
    action: CompoundActionV1 | None = None
    stopped_early: bool = False
    fallback_used: bool = False
    successor_reads: int = 0

    def __post_init__(self) -> None:
        if self.schema_version != B5_SCHEMA_VERSION:
            raise ValueError("unknown B5 decision schema")
        if self.status not in {SELECTED, B0_DELEGATE, AMBIGUOUS, TERMINAL_OVERRIDE}:
            raise ValueError("unknown B5 decision status")
        if self.receipt_scope != FIXTURE_ONLY or self.successor_reads != 0:
            raise ValueError("B5 decision boundary was crossed")


@dataclass(frozen=True)
class B5FixtureCaseV1:
    case_id: str
    observation: EngineObservationV1
    request: SelectionRequestV1
    state: PublicStateV1
    receipt: B5CapabilityReceiptV1
    local_deltas: Mapping[str, BenchLocalDeltaV1]
    expected: Mapping[str, str]
    successor_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.observation, EngineObservationV1) or not isinstance(self.request, SelectionRequestV1) or not isinstance(self.state, PublicStateV1) or not isinstance(self.receipt, B5CapabilityReceiptV1):
            raise TypeError("B5 fixture case contains an invalid immutable authority row")
        object.__setattr__(self, "local_deltas", MappingProxyType(dict(self.local_deltas)))
        object.__setattr__(self, "expected", MappingProxyType(dict(self.expected)))
        object.__setattr__(self, "successor_fields", tuple(self.successor_fields))


@dataclass(frozen=True)
class B5FixtureBundleV1:
    config_path: Path
    scale: BenchLiabilityScaleV1
    cases: tuple[B5FixtureCaseV1, ...]


_CONTENT_AUTHORITY_FIELDS = frozenset({
    "content_sha256", "fixture_metadata_sha256", "fixture_content_sha256", "fixture_config_sha256",
    "config_payload_sha256", "config_sha256", "receipt_manifest_sha256",
})
_CONFIG_DIGEST_FIELDS = frozenset({
    "fixture_metadata_sha256", "fixture_content_sha256", "fixture_config_sha256",
    "config_payload_sha256", "config_sha256", "receipt_manifest_sha256",
})


def _content_payload(value: Any) -> Any:
    """Build a content payload without recursively re-sealing authority fields."""

    if hasattr(value, "__dataclass_fields__"):
        return {
            item.name: _content_payload(getattr(value, item.name))
            for item in fields(value) if item.name not in _CONTENT_AUTHORITY_FIELDS
        }
    if isinstance(value, Mapping):
        return {
            str(key): _content_payload(item)
            for key, item in sorted(value.items(), key=lambda item: str(item[0]))
            if str(key) not in _CONTENT_AUTHORITY_FIELDS
        }
    if isinstance(value, (tuple, list, frozenset)):
        return [_content_payload(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _content_digest(value: Any) -> str:
    return _sha_json(_content_payload(value))


def _scale_content_digest(scale: BenchLiabilityScaleV1) -> str:
    return _sha_json({
        "schema_version": scale.schema_version, "scale_id": scale.scale_id, "lower_is_safer": scale.lower_is_safer,
        "prize_levels": scale.prize_levels, "gust_levels": scale.gust_levels, "spread_levels": scale.spread_levels,
        "scope": scale.scope, "exact_integer_type": scale.exact_integer_type,
        "qualification_status": scale.qualification_status, "review_id": scale.review_id, "scope_version": scale.scope_version,
    })


def _safe_payload_hash(state: Any, request: Any, formulation: str, local_deltas: Any, fixture_id: Any) -> str | None:
    """Hash request identity only when every payload value is serializable."""

    try:
        return stable_hash({
            "observation": stable_hash(state.observation),
            "request": stable_hash(request),
            "formulation": formulation,
            "local_deltas": _canonical_value(local_deltas),
            "fixture": fixture_id,
        })
    except Exception:
        # A malformed caller payload must never cross the receipt evaluator or
        # leak an unbounded serializer exception into the policy boundary.
        return None


def _public_field_failure(current_fields: Sequence[str], successor_fields: Sequence[str]) -> str | None:
    """Classify every receipt field before any scoring or content fallback."""

    for raw in (*successor_fields, *current_fields):
        if not isinstance(raw, str) or not raw:
            return UNKNOWN_CURRENT_RECEIPT
        field = raw.lower()
        if any(token in field for token in _HIDDEN_FIELD_TOKENS):
            return HIDDEN_INFORMATION_FORBIDDEN
        if any(token in field for token in _SUCCESSOR_FIELD_TOKENS):
            return SUCCESSOR_VALUE_FORBIDDEN
        if any(token in field for token in _PROSE_FIELD_TOKENS):
            return CARD_PROSE_FORBIDDEN
        if raw not in _CURRENT_FIELD_ALLOWLIST:
            return UNKNOWN_CURRENT_RECEIPT
    return None


def _seal(value: Any) -> Any:
    return replace(value, content_sha256=_content_digest(value))


def _sha_fixture() -> str:
    return "f" * 64


def _normalized_source_digest(path: Path) -> str:
    raw = path.read_bytes()
    pattern = rb'((?:B5_IMPLEMENTATION_SOURCE_SHA256|B5_CANONICAL_FIXTURE_DIGEST)\s*=\s*["\'])([0-9a-f]{64})(["\'])'
    normalized, count = re.subn(pattern, rb'\g<1>' + (b"0" * 64) + rb'\g<3>', raw)
    if count != 2:
        raise ValueError("B5 sealed source markers are missing or duplicated")
    return hashlib.sha256(normalized).hexdigest()


def _config_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _dependency_manifest(root: Path) -> Mapping[str, str]:
    result: dict[str, str] = {}
    for relative in _DEPENDENCY_PATHS:
        path = root / relative
        if not path.is_file():
            raise ValueError(f"B5 dependency is missing: {relative}")
        result[str(relative)] = _normalized_source_digest(path) if relative == _IMPLEMENTATION_PATH else hashlib.sha256(path.read_bytes()).hexdigest()
    if result[str(_IMPLEMENTATION_PATH)] != B5_IMPLEMENTATION_SOURCE_SHA256:
        raise ValueError("B5 implementation source marker does not match the loaded source")
    return result


def _fixture_provenance(scale_id: str) -> Mapping[str, Any]:
    digest = _sha_fixture()
    return {
        "schema_id": _FIXTURE_RECORD_ID,
        "schema_version": B5_SCHEMA_VERSION,
        "fixture_metadata_sha256": digest,
        "config_payload_sha256": digest,
        "knowledge_base_sha256": digest,
        "source_hashes": {str(path): digest for path in _DEPENDENCY_PATHS},
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
        "scale_id": scale_id,
        "wrapper_hashes": {"game": digest, "api": digest, "sim": digest},
        "fixture_content_sha256": digest,
        "fixture_config_sha256": digest,
        "receipt_manifest_sha256": digest,
        "policy_id": "b5-current-public-bench-liability-fixture-v1",
        "implementation_sha256": digest,
        "transitive_source_hashes": {str(path): digest for path in _DEPENDENCY_PATHS},
        "config_sha256": digest,
        "schema_hashes": {"models": digest, "actions": digest, "semantic": digest, "state": digest},
        "dependency_scan_digest": digest,
    }


def _entity(owner: int, serial: int, card_id: int, zone: int, position: int, *, hp: int | None = None) -> VisibleEntityV1:
    return VisibleEntityV1(
        entity_key=f"p{owner}:s{serial}", card_id=card_id, serial=serial,
        metadata_ref=f"card:{card_id}@{_sha_fixture()}", owner=owner, zone=zone, position=position,
        hp=hp, max_hp=hp, damage=0 if hp is not None else None, appear_this_turn=False,
        energy_types=(), attached_energy_count=0, attached_tool_count=0, evolution_depth=0,
        statuses=(), visible=True,
    )


def _public_observation(case_id: str, *, actor: int = 0, transition: int = 7, bench_max: int = 3, bench_count: int = 1, terminal: int | None = None) -> EngineObservationV1:
    entities = [
        _entity(0, 1, 723, AREA["HAND"], 0), _entity(0, 2, 721, AREA["HAND"], 1),
        _entity(0, 10, 723, AREA["ACTIVE"], 0, hp=350), _entity(0, 11, 721, AREA["BENCH"], 0, hp=150),
        _entity(1, 50, 100, AREA["ACTIVE"], 0, hp=150),
    ]
    if bench_count >= 2:
        entities.append(_entity(0, 12, 722, AREA["BENCH"], 1, hp=100))
    return EngineObservationV1(
        schema_version=CONTRACT_VERSION, battle_id=case_id, transition_id=transition,
        acting_player=actor, terminal_result=terminal, turn=4, turn_action_count=1,
        first_player=0, supporter_played=False, stadium_played=False, energy_attached=False,
        retreated=False, players=(PlayerViewV1(0, bench_max, 10, 3, 6, 0, actor == 0, 0), PlayerViewV1(1, 5, 10, 3, 6, 0, actor == 1, 0)),
        entities=tuple(entities), public_events=(),
    )


def _option(index: int, serial: int, card_id: int, *, actor: int = 0) -> LegalOptionV1:
    source = f"p{actor}:s{serial}"
    # G1 reserves PSEUDO references for the ME..ATTACK_PRE_MY_TURN range;
    # the PLAY row's in_play_area still carries the factual BENCH enum.
    target = f"pseudo:area:{AREA['ME']}:player:{actor}:index:1"
    option = LegalOptionV1(
        schema_version=CONTRACT_VERSION, original_index=index, selection_type=0, selection_context=0,
        option_type=7, option_name=OPTION_NAMES[7], area=AREA["HAND"], index=index, player_index=None,
        tool_index=None, energy_index=None, count=None, in_play_area=AREA["BENCH"], in_play_index=1,
        attack_id=None, card_id=card_id, serial=serial, special_condition_type=None,
        source_kind="ENTITY", source_ref=source, target_kind="PSEUDO", target_ref=target,
        choice_role="PLAY", source_entity_key=source, target_entity_key=None, available=True,
        semantic_fingerprint="",
    )
    return replace(option, semantic_fingerprint=stable_hash(option.semantic_payload()))


def _request(case_id: str, options: Sequence[LegalOptionV1], *, min_count: int = 1, max_count: int = 1, actor: int = 0, ordering: str = "UNORDERED") -> SelectionRequestV1:
    return SelectionRequestV1(
        schema_version=CONTRACT_VERSION, episode_uuid=case_id, selection_seq=7,
        request_id=f"{case_id}-r7", acting_player=actor, selection_type=0, selection_context=0,
        min_count=min_count, max_count=max_count, remain_damage_counter=None, remain_energy_cost=None,
        context_card_id=None, effect_card_id=None, ordering=ordering, options=tuple(options),
    )


def _observation_digest(observation: EngineObservationV1) -> str:
    return stable_hash(observation)


def _role_receipt(case_id: str, option: LegalOptionV1, observation_digest: str, *, conflict: bool = False) -> BenchRoleReceiptV1:
    digest = _sha_fixture()
    return _seal(BenchRoleReceiptV1(
        receipt_id=f"b5-{case_id}-{option.original_index}-role{'-conflict' if conflict else ''}",
        entity_key=option.source_entity_key or "", card_id=option.card_id or 0, owner=0, zone=AREA["HAND"],
        role_id="BACKUP_ATTACKER", role_status="CONFLICT" if conflict else "COVERED", route_id="route-v1",
        necessity="FORBIDDEN" if conflict else "REQUIRED", required_count=0 if conflict else 1,
        source_observation_digest=observation_digest, candidate_deck_profile="fixture-candidate",
        candidate_deck_sha256=digest, card_data_sha256=digest, card_table_semantic_sha256=digest,
        scope_version="fixture-scope-v1", qualification_status=FIXTURE_ONLY, content_sha256=digest,
        qualification_id=f"b5-{case_id}-{option.original_index}-qualification",
        metadata_ref=f"card:{option.card_id}@{digest}", card_table_file_sha256=digest,
    ))


def _local_delta(case_id: str, option: LegalOptionV1, observation_digest: str, *, before: int, after: int, surplus: int, action_eligible: bool = True, unknown: bool = False) -> BenchLocalDeltaV1:
    delta = BenchLocalDeltaV1(
        option_fingerprint=option.semantic_fingerprint, receipt_id=f"b5-{case_id}-{option.original_index}-delta",
        qualification_status=FIXTURE_ONLY, current_public_observation_digest=observation_digest,
        source_entity_key=option.source_entity_key or "", target_entity_key=None, choice_role="PLAY",
        before_bench_occupancy=before, after_bench_occupancy=after,
        before_role_coverage={"BACKUP_ATTACKER": 1}, after_role_coverage={"BACKUP_ATTACKER": 1},
        after_role_surplus={"BACKUP_ATTACKER": surplus, "NEXT_ATTACKER": 0}, required_role_counts={"BACKUP_ATTACKER": 1},
        affected_role_receipt_ids=(f"b5-{case_id}-{option.original_index}-role",), action_key=f"B5-{case_id.split('-')[1]}-{chr(88 + option.original_index)}",
        action_eligible=action_eligible, current_public_fields=("bench_occupancy", "role_coverage", "local_legality"),
        unknown_fields=("role_necessity",) if unknown else (), content_sha256=_sha_fixture(),
        option_semantic_payload_digest=stable_hash(option.semantic_payload()), selection_type=option.selection_type,
        selection_context=option.selection_context, option_type=option.option_type, source_card_id=option.card_id,
        target_card_id=None, source_owner=0, target_owner=0, source_zone=AREA["HAND"], target_zone=AREA["BENCH"],
        source_metadata_ref=f"card:{option.card_id}@{_sha_fixture()}", target_metadata_ref=None,
        qualification_id=f"b5-{case_id}-{option.original_index}-qualification", scope_version="fixture-scope-v1",
    )
    return _seal(delta)


def _prize(case_id: str, option: LegalOptionV1, level: int, observation_digest: str) -> PrizeStaticV1:
    digest = _sha_fixture()
    return _seal(PrizeStaticV1(
        f"b5-{case_id}-{option.original_index}-prize", option.source_entity_key or "", option.card_id or 0, level,
        digest, digest, "fixture-scope-v1", FIXTURE_ONLY, digest, native_library_sha256=digest,
        wrapper_hashes={"game": digest, "api": digest, "sim": digest}, card_table_file_sha256=digest, card_table_semantic_sha256=digest,
        metadata_ref=f"card:{option.card_id}@{digest}", source_observation_digest=observation_digest,
        candidate_deck_profile="fixture-candidate", candidate_deck_sha256=digest,
        anchor_deck_profile="fixture-anchor", anchor_deck_sha256=digest,
        qualification_id=f"b5-{case_id}-{option.original_index}-qualification",
    ))


def _gust(case_id: str, option: LegalOptionV1, level: int, observation_digest: str) -> GustExposureV1:
    digest = _sha_fixture()
    return _seal(GustExposureV1(
        f"b5-{case_id}-{option.original_index}-gust", "p1:s50", option.source_entity_key or "", "BACKUP_ATTACKER", True,
        "ROUTE_CONVERTING", level, digest, digest, digest, "fixture-scope-v1", FIXTURE_ONLY, digest,
        candidate_deck_profile="fixture-candidate", qualification_id=f"b5-{case_id}-{option.original_index}-qualification",
        option_semantic_fingerprint=option.semantic_fingerprint, current_public_observation_digest=observation_digest,
        source_card_id=100, target_card_id=option.card_id or 0, source_owner=1, target_owner=0,
        source_zone=AREA["ACTIVE"], target_zone=AREA["HAND"], source_metadata_ref=f"card:100@{digest}",
        target_metadata_ref=f"card:{option.card_id}@{digest}", native_library_sha256=digest,
        wrapper_hashes={"game": digest, "api": digest, "sim": digest}, card_data_sha256=digest,
        card_table_file_sha256=digest, card_table_semantic_sha256=digest, anchor_deck_profile="fixture-anchor",
    ))


def _spread(case_id: str, option: LegalOptionV1, level: int, observation_digest: str) -> SpreadExposureV1:
    digest = _sha_fixture()
    return _seal(SpreadExposureV1(
        f"b5-{case_id}-{option.original_index}-spread", "p1:s50", option.source_entity_key or "", "BACKUP_ATTACKER", 1,
        0, "ROUTE_CONVERTING", level, digest, digest, digest, "fixture-scope-v1", FIXTURE_ONLY, digest,
        candidate_deck_profile="fixture-candidate", qualification_id=f"b5-{case_id}-{option.original_index}-qualification",
        option_semantic_fingerprint=option.semantic_fingerprint, current_public_observation_digest=observation_digest,
        source_card_id=100, target_card_id=option.card_id or 0, source_owner=1, target_owner=0,
        source_zone=AREA["ACTIVE"], target_zone=AREA["HAND"], source_metadata_ref=f"card:100@{digest}",
        target_metadata_ref=f"card:{option.card_id}@{digest}", native_library_sha256=digest,
        wrapper_hashes={"game": digest, "api": digest, "sim": digest}, card_data_sha256=digest,
        card_table_file_sha256=digest, card_table_semantic_sha256=digest, anchor_deck_profile="fixture-anchor",
    ))


def _make_case(case_id: str, descriptors: Sequence[tuple[int, int, int, int, int, int, bool]], *, bench_max: int = 3, bench_count: int = 1, min_count: int = 1, max_count: int = 1, terminal: int | None = None, unknown: bool = False, conflict: bool = False) -> B5FixtureCaseV1:
    observation = _public_observation(case_id, bench_max=bench_max, bench_count=bench_count, terminal=terminal)
    options = tuple(_option(index, serial, card_id) for index, serial, card_id, _prize_level, _gust_level, _spread_level, _eligible in descriptors)
    request = _request(case_id, options, min_count=min_count, max_count=max_count)
    state = PublicStateV1.from_engine(observation, request)
    observation_digest = _observation_digest(observation)
    roles: list[BenchRoleReceiptV1] = []
    deltas: dict[str, BenchLocalDeltaV1] = {}
    prizes: list[PrizeStaticV1] = []
    gusts: list[GustExposureV1] = []
    spreads: list[SpreadExposureV1] = []
    for index, option in enumerate(options):
        _, _, _, prize_level, gust_level, spread_level, eligible = descriptors[index]
        roles.append(_role_receipt(case_id, option, observation_digest))
        if conflict and index == 0:
            roles.append(_role_receipt(case_id, option, observation_digest, conflict=True))
        deltas[option.semantic_fingerprint] = _local_delta(case_id, option, observation_digest, before=bench_count, after=bench_count + 1, surplus=(1 if index == 0 else 0), action_eligible=eligible, unknown=unknown)
        prizes.append(_prize(case_id, option, prize_level, observation_digest))
        gusts.append(_gust(case_id, option, gust_level, observation_digest))
        spreads.append(_spread(case_id, option, spread_level, observation_digest))
    scale = BenchLiabilityScaleV1(1, "fixture-bench-liability-scale-v1", True, ((0, "NONE"), (1, "LOW"), (2, "MEDIUM"), (3, "HIGH")), ((0, "NONE"), (1, "LOW"), (2, "MEDIUM"), (3, "HIGH")), ((0, "NONE"), (1, "LOW"), (2, "MEDIUM"), (3, "HIGH")))
    receipt = B5CapabilityReceiptV1(_FIXTURE_RECORD_ID, FIXTURE_ONLY, case_id, scale, tuple(roles), tuple(deltas.values()), tuple(prizes), tuple(gusts), tuple(spreads), _fixture_provenance(scale.scale_id), _sha_fixture())
    receipt = replace(receipt, content_sha256=_content_digest(receipt))
    return B5FixtureCaseV1(case_id, observation, request, state, receipt, MappingProxyType(deltas), {}, ())


def _build_cases() -> tuple[B5FixtureCaseV1, ...]:
    two = ((0, 1, 723, 2, 2, 2, True), (1, 2, 721, 1, 0, 0, True))
    control = ((0, 1, 723, 1, 0, 0, True), (1, 2, 721, 2, 1, 1, True))
    simple = ((0, 1, 723, 1, 1, 1, True),)
    return (
        _make_case("B5-F01-FORMULATION-DIVERGENCE", two),
        _make_case("B5-F02-STRICT-DOMINANCE-CONTROL", control),
        _make_case("B5-F03-BENCH-FULL", simple, bench_max=1, bench_count=1),
        _make_case("B5-F04-TERMINAL-FIRST", simple, terminal=1),
        _make_case("B5-F05-PLAYER-MIRROR", two),
        _make_case("B5-F06-SEMANTIC-PERMUTATION", two),
        _make_case("B5-F07-UNKNOWN-SUCCESSOR", simple, unknown=True),
        _make_case("B5-F08-NAN-ENUM", simple),
        _make_case("B5-F09-ROLE-CONFLICT", simple, conflict=True),
        _make_case("B5-F10-OPTIONAL-STOP-COMPOUND", ((0, 1, 723, 1, 1, 1, False), (1, 2, 721, 1, 1, 1, False)), min_count=0, max_count=1),
        _make_case("B5-F11-LIFECYCLE-IDEMPOTENCY", simple),
        _make_case("B5-F12-FORGED-RECEIPT", simple),
    )


def _map_key(value: str | None, owner_map: Mapping[int, int]) -> str | None:
    if value is None:
        return None
    if value.startswith("pseudo:area:"):
        parts = value.split(":")
        if len(parts) == 7 and parts[3] == "player":
            return ":".join((*parts[:4], str(owner_map.get(int(parts[4]), int(parts[4]))), *parts[5:]))
    if value.startswith("p") and ":" in value:
        head, tail = value.split(":", 1)
        try:
            owner = int(head[1:])
        except ValueError:
            return value
        return f"p{owner_map.get(owner, owner)}:{tail}"
    return value


def mirror_b5_case(case: B5FixtureCaseV1) -> B5FixtureCaseV1:
    owner_map = {0: 1, 1: 0}
    observation = case.observation
    entities = tuple(replace(item, entity_key=_map_key(item.entity_key, owner_map) or item.entity_key, owner=owner_map[item.owner]) for item in observation.entities)
    players = tuple(sorted((replace(item, player_index=owner_map[item.player_index], hand_visible=owner_map[item.player_index] == 1) for item in observation.players), key=lambda item: item.player_index))
    mirrored_observation = replace(observation, battle_id=f"{case.case_id}-MIRROR", acting_player=1, players=players, entities=entities)
    options: list[LegalOptionV1] = []
    deltas: dict[str, BenchLocalDeltaV1] = {}
    roles: list[BenchRoleReceiptV1] = []
    prizes: list[PrizeStaticV1] = []
    gusts: list[GustExposureV1] = []
    spreads: list[SpreadExposureV1] = []
    digest = _observation_digest(mirrored_observation)
    for option in case.request.options:
        mirrored = replace(option, source_ref=_map_key(option.source_ref, owner_map), source_entity_key=_map_key(option.source_entity_key, owner_map), target_ref=_map_key(option.target_ref, owner_map), target_entity_key=_map_key(option.target_entity_key, owner_map))
        mirrored = replace(mirrored, semantic_fingerprint=stable_hash(mirrored.semantic_payload()))
        options.append(mirrored)
        delta = case.local_deltas[option.semantic_fingerprint]
        deltas[mirrored.semantic_fingerprint] = replace(_seal(replace(
            delta,
            option_fingerprint=mirrored.semantic_fingerprint,
            option_semantic_fingerprint=mirrored.semantic_fingerprint,
            option_semantic_payload_digest=mirrored.semantic_fingerprint,
            current_public_observation_digest=digest,
            source_entity_key=mirrored.source_entity_key or "",
            source_owner=1,
            target_owner=1,
        )), action_key=delta.action_key)
        for role in case.receipt.role_receipts:
            if role.entity_key == option.source_entity_key:
                roles.append(_seal(replace(role, entity_key=mirrored.source_entity_key or "", owner=1, source_observation_digest=digest)))
        for prize in case.receipt.prize_static:
            if prize.entity_key == option.source_entity_key:
                prizes.append(_seal(replace(prize, entity_key=mirrored.source_entity_key or "", source_observation_digest=digest)))
        for item in case.receipt.gust_exposures:
            if item.target_entity_key == option.source_entity_key:
                gusts.append(_seal(replace(item, source_entity_key="p0:s50", target_entity_key=mirrored.source_entity_key or "", source_owner=0, target_owner=1, current_public_observation_digest=digest, option_semantic_fingerprint=mirrored.semantic_fingerprint)))
        for item in case.receipt.spread_exposures:
            if item.target_entity_key == option.source_entity_key:
                spreads.append(_seal(replace(item, source_entity_key="p0:s50", target_entity_key=mirrored.source_entity_key or "", source_owner=0, target_owner=1, current_public_observation_digest=digest, option_semantic_fingerprint=mirrored.semantic_fingerprint)))
    request = replace(case.request, episode_uuid=mirrored_observation.battle_id, request_id=f"{case.request.request_id}-mirror", acting_player=1, options=tuple(options))
    receipt = replace(case.receipt, fixture_case_id=f"{case.case_id}-MIRROR", role_receipts=tuple(roles), local_deltas=tuple(deltas.values()), prize_static=tuple(prizes), gust_exposures=tuple(gusts), spread_exposures=tuple(spreads), provenance_manifest=dict(case.receipt.provenance_manifest))
    receipt = replace(receipt, content_sha256=_content_digest(receipt))
    state = PublicStateV1.from_engine(mirrored_observation, request)
    return replace(case, case_id=f"{case.case_id}-MIRROR", observation=mirrored_observation, request=request, state=state, receipt=receipt, local_deltas=MappingProxyType(deltas))


def semantic_permutation_suite(option_count: int, count: int = 32) -> tuple[tuple[int, ...], ...]:
    """Return deterministic transport permutations without sampling semantics."""

    _nonnegative_int(option_count, "option_count")
    _nonnegative_int(count, "count")
    if option_count <= 0 or count <= 0:
        raise ValueError("permutation dimensions must be positive")
    values = tuple(itertools.permutations(range(option_count)))
    return tuple(values[index % len(values)] for index in range(count))


def _case_record(case: B5FixtureCaseV1) -> Mapping[str, Any]:
    return {
        "case_id": case.case_id,
        "observation": _canonical_value(case.observation),
        "request": _canonical_value(case.request),
        "state": _canonical_value(case.state),
        "receipt": _canonical_value(case.receipt),
        "local_deltas": _canonical_value(dict(sorted(case.local_deltas.items()))),
        "expected": _canonical_value(dict(sorted(case.expected.items()))),
        "successor_fields": _canonical_value(case.successor_fields),
    }


def _fixture_payload(cases: Sequence[B5FixtureCaseV1], scale: BenchLiabilityScaleV1, dependency_manifest: Mapping[str, str]) -> Mapping[str, Any]:
    payload = {
        "schema_version": B5_SCHEMA_VERSION, "record_id": _FIXTURE_RECORD_ID, "scope": FIXTURE_ONLY,
        "scale": _canonical_value(scale),
        "dependency_manifest": {key: ("IMPLEMENTATION_SOURCE_BOUND_SEPARATELY" if key == str(_IMPLEMENTATION_PATH) else dependency_manifest[key]) for key in sorted(dependency_manifest)},
        "fixture_cases": [{"id": item.case_id, "expected": _canonical_value(dict(sorted(item.expected.items())))} for item in cases],
        "fixture_records": [_case_record(item) for item in cases],
    }
    # Fixture and receipt content digests are authority fields, not inputs to
    # their own digest.  Strip those fields recursively before sealing.
    return _strip_recursive(payload)


def _expected_cases(value: Mapping[str, Any]) -> Mapping[str, Mapping[str, str]]:
    if not isinstance(value, list):
        raise ValueError("B5 fixture_cases must be an ordered list")
    result: dict[str, Mapping[str, str]] = {}
    for item in value:
        if not isinstance(item, Mapping) or set(item) != {"id", "expected"} or not isinstance(item["id"], str) or not isinstance(item["expected"], Mapping):
            raise ValueError("B5 fixture case declaration is incomplete or unknown")
        if item["id"] in result:
            raise ValueError("B5 fixture case declaration is duplicated")
        expected = dict(item["expected"])
        if set(expected) != {A_FORMULATION, B_FORMULATION} or any(status not in {SELECTED, B0_DELEGATE, TERMINAL_OVERRIDE, AMBIGUOUS} for status in expected.values()):
            raise ValueError("B5 expected outcomes are malformed")
        result[item["id"]] = expected
    return result


def _case_from_record(value: Mapping[str, Any], expected: Mapping[str, str]) -> B5FixtureCaseV1:
    required = {"case_id", "observation", "request", "state", "receipt", "local_deltas", "expected", "successor_fields"}
    if not isinstance(value, Mapping) or set(value) != required:
        raise ValueError("B5 fixture record fields are incomplete or unknown")
    case_id = value["case_id"]
    if not isinstance(case_id, str) or not case_id:
        raise ValueError("B5 fixture record case_id is malformed")
    observation = EngineObservationV1.from_dict(value["observation"])
    request = SelectionRequestV1.from_dict(value["request"])
    state = PublicStateV1.from_engine(observation, request)
    if _canonical_value(state) != value["state"]:
        raise ValueError("B5 fixture record state is not exactly derived from its observation/request")
    receipt = B5CapabilityReceiptV1.from_dict(value["receipt"])
    if receipt.fixture_case_id != case_id:
        raise ValueError("B5 fixture record receipt case identity is stale")
    raw_deltas = value["local_deltas"]
    if not isinstance(raw_deltas, Mapping):
        raise ValueError("B5 fixture record local_deltas must be a mapping")
    deltas = {str(key): BenchLocalDeltaV1.from_dict(item) for key, item in raw_deltas.items()}
    if set(deltas) != {row.option_fingerprint for row in receipt.local_deltas}:
        raise ValueError("B5 fixture record local-delta graph is incomplete")
    if value["expected"] != dict(expected):
        raise ValueError("B5 fixture record expected outcomes differ from the declaration")
    successor_fields = tuple(value["successor_fields"])
    _strict_tuple_strings(successor_fields, "successor_fields")
    return B5FixtureCaseV1(case_id, observation, request, state, receipt, MappingProxyType(deltas), MappingProxyType(dict(expected)), successor_fields)


def _strip_recursive(value: Any, keys: frozenset[str] = frozenset({
    "fixture_metadata_sha256", "fixture_content_sha256", "fixture_config_sha256", "config_payload_sha256", "config_sha256",
    "receipt_manifest_sha256", "content_sha256",
})) -> Any:
    if isinstance(value, Mapping):
        return {key: ("" if key in keys else _strip_recursive(item, keys)) for key, item in value.items()}
    if isinstance(value, list):
        return [_strip_recursive(item, keys) for item in value]
    return value


def _config_payload_digest(value: Mapping[str, Any]) -> str:
    # Keep each row's content seal in the config authority.  Only the
    # self-referential provenance references are stripped here; otherwise a
    # content_sha256-only mutation would be invisible to the loader.
    return _sha_json(_strip_recursive(value, _CONFIG_DIGEST_FIELDS))


def _bind_case_provenance(case: B5FixtureCaseV1, metadata_digest: str, config_digest: str, kb_digest: str, dependencies: Mapping[str, str]) -> B5FixtureCaseV1:
    manifest = dict(case.receipt.provenance_manifest)
    manifest.update({
        "fixture_metadata_sha256": metadata_digest,
        "config_payload_sha256": config_digest,
        "knowledge_base_sha256": kb_digest,
        "source_hashes": dict(dependencies),
        "implementation_sha256": dependencies[str(_IMPLEMENTATION_PATH)],
        "transitive_source_hashes": dict(dependencies),
        "config_sha256": config_digest,
        "wrapper_hashes": {
            "game": manifest["game_wrapper_sha256"],
            "api": manifest["api_wrapper_sha256"],
            "sim": manifest["sim_wrapper_sha256"],
        },
        "fixture_content_sha256": metadata_digest,
        "fixture_config_sha256": config_digest,
        "schema_hashes": {
            "models": dependencies[str(Path("src/ptcg_rl/g1/models.py"))],
            "actions": dependencies[str(Path("src/ptcg_rl/g1/actions.py"))],
            "semantic": dependencies[str(Path("src/ptcg_rl/g1/semantic.py"))],
            "state": dependencies[str(Path("src/ptcg_rl/deterministic/state.py"))],
        },
        "dependency_scan_digest": _sha_json(dict(sorted(dependencies.items()))),
    })
    manifest_digest = _sha_json(_strip_recursive(manifest, frozenset({"fixture_metadata_sha256", "fixture_content_sha256", "fixture_config_sha256", "config_payload_sha256", "config_sha256", "receipt_manifest_sha256", "content_sha256"})))
    manifest["receipt_manifest_sha256"] = manifest_digest
    scale = replace(
        case.receipt.scale,
        scale_content_sha256=_sha_json({
            "schema_version": case.receipt.scale.schema_version,
            "scale_id": case.receipt.scale.scale_id,
            "lower_is_safer": case.receipt.scale.lower_is_safer,
            "prize_levels": case.receipt.scale.prize_levels,
            "gust_levels": case.receipt.scale.gust_levels,
            "spread_levels": case.receipt.scale.spread_levels,
            "scope": case.receipt.scale.scope,
            "exact_integer_type": case.receipt.scale.exact_integer_type,
            "qualification_status": case.receipt.scale.qualification_status,
            "review_id": case.receipt.scale.review_id,
            "scope_version": case.receipt.scale.scope_version,
        }),
        fixture_content_sha256=metadata_digest,
        fixture_config_sha256=config_digest,
        receipt_manifest_sha256=manifest_digest,
    )
    def bind_row(row: Any) -> Any:
        row = replace(row, fixture_content_sha256=metadata_digest, fixture_config_sha256=config_digest, receipt_manifest_sha256=manifest_digest)
        return _seal(row)
    roles = tuple(bind_row(row) for row in case.receipt.role_receipts)
    deltas_rows = tuple(bind_row(row) for row in case.receipt.local_deltas)
    prizes = tuple(bind_row(row) for row in case.receipt.prize_static)
    gusts = tuple(bind_row(row) for row in case.receipt.gust_exposures)
    spreads = tuple(bind_row(row) for row in case.receipt.spread_exposures)
    receipt = replace(case.receipt, scale=scale, role_receipts=roles, local_deltas=deltas_rows, prize_static=prizes, gust_exposures=gusts, spread_exposures=spreads, provenance_manifest=manifest)
    receipt = replace(receipt, content_sha256=_content_digest(receipt))
    delta_map = MappingProxyType({row.option_fingerprint: row for row in deltas_rows})
    return replace(case, receipt=receipt, local_deltas=delta_map)


def _knowledge_base_digest(root: Path) -> str:
    path = root / "knowledge_base" / "ptcg_gold.sqlite"
    if not path.is_file():
        raise ValueError("B5 knowledge base is missing")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_content_seals(scale: BenchLiabilityScaleV1, cases: Sequence[B5FixtureCaseV1]) -> None:
    if scale.scale_content_sha256 != _scale_content_digest(scale):
        raise ValueError("B5 scale content seal does not match its fields")
    for case in cases:
        rows = (
            *case.receipt.role_receipts,
            *case.receipt.local_deltas,
            *case.receipt.prize_static,
            *case.receipt.gust_exposures,
            *case.receipt.spread_exposures,
            *case.local_deltas.values(),
        )
        if any(row.content_sha256 != _content_digest(row) for row in rows):
            raise ValueError("B5 nested receipt content seal does not match its fields")
        if case.receipt.content_sha256 != _content_digest(case.receipt):
            raise ValueError("B5 receipt content seal does not match its fields")


def materialize_b5_fixture_data(value: Mapping[str, Any], *, config_path: Path | None = None) -> B5FixtureBundleV1:
    allowed = {"schema_version", "record_id", "scope", "fixture_metadata_sha256", "scale", "fixture_cases", "fixture_records", "dependency_manifest", "provenance"}
    if not isinstance(value, Mapping) or set(value) != allowed:
        raise ValueError("B5 fixture top-level fields are incomplete or unknown")
    if value["schema_version"] != B5_SCHEMA_VERSION or value["record_id"] != _FIXTURE_RECORD_ID or value["scope"] != FIXTURE_ONLY:
        raise ValueError("unknown B5 fixture metadata")
    metadata_digest = _digest(value["fixture_metadata_sha256"], "fixture_metadata_sha256")
    dependencies = _dependency_manifest(_config_root())
    declared_dependencies = value["dependency_manifest"]
    if not isinstance(declared_dependencies, Mapping) or set(declared_dependencies) != set(dependencies):
        raise ValueError("B5 dependency manifest is incomplete or unknown")
    if {key: _digest(item, f"dependency_manifest.{key}") for key, item in declared_dependencies.items()} != dependencies:
        raise ValueError("B5 dependency manifest does not match loaded source/schema files")
    provenance = value["provenance"]
    if not isinstance(provenance, Mapping):
        raise ValueError("B5 provenance is missing")
    required_provenance = {
        "schema_id", "schema_version", "fixture_metadata_sha256", "config_payload_sha256", "knowledge_base_sha256", "source_hashes",
        "engine_hash", "native_library_sha256", "game_wrapper_sha256", "api_wrapper_sha256", "sim_wrapper_sha256",
        "card_data_sha256", "card_table_file_sha256", "card_table_semantic_sha256", "candidate_deck_profile", "candidate_deck_sha256",
        "anchor_deck_profile", "anchor_deck_sha256", "scope_version", "scale_id", "policy_id", "implementation_sha256",
        "transitive_source_hashes", "config_sha256", "schema_hashes", "dependency_scan_digest", "wrapper_hashes",
        "fixture_content_sha256", "fixture_config_sha256", "receipt_manifest_sha256",
    }
    if set(provenance) != required_provenance:
        raise ValueError("B5 provenance fields are incomplete or unknown")
    if provenance["schema_id"] != _FIXTURE_RECORD_ID or provenance["schema_version"] != B5_SCHEMA_VERSION or provenance["fixture_metadata_sha256"] != metadata_digest or provenance["source_hashes"] != dependencies:
        raise ValueError("B5 provenance does not bind the loaded fixture")
    config_digest = _config_payload_digest(value)
    if provenance["config_payload_sha256"] != config_digest:
        raise ValueError("B5 canonical fixture content/config payload digest does not match its sealed authority")
    if provenance["config_sha256"] != config_digest:
        raise ValueError("B5 runtime source manifest config digest is stale")
    if provenance["implementation_sha256"] != dependencies[str(_IMPLEMENTATION_PATH)] or provenance["transitive_source_hashes"] != dependencies:
        raise ValueError("B5 runtime source manifest implementation digest is stale")
    expected_schema_hashes = {
        "models": dependencies[str(Path("src/ptcg_rl/g1/models.py"))],
        "actions": dependencies[str(Path("src/ptcg_rl/g1/actions.py"))],
        "semantic": dependencies[str(Path("src/ptcg_rl/g1/semantic.py"))],
        "state": dependencies[str(Path("src/ptcg_rl/deterministic/state.py"))],
    }
    if provenance["schema_hashes"] != expected_schema_hashes or provenance["dependency_scan_digest"] != _sha_json(dict(sorted(dependencies.items()))):
        raise ValueError("B5 runtime source manifest dependency scan is stale")
    if not isinstance(provenance["wrapper_hashes"], Mapping) or set(provenance["wrapper_hashes"]) != {"game", "api", "sim"}:
        raise ValueError("B5 runtime source manifest wrapper scope is incomplete")
    for name, value_hash in provenance["wrapper_hashes"].items():
        _digest(value_hash, f"provenance.wrapper_hashes.{name}")
    for name in ("fixture_content_sha256", "fixture_config_sha256", "receipt_manifest_sha256"):
        _digest(provenance[name], f"provenance.{name}")
    kb_digest = _knowledge_base_digest(_config_root())
    _digest(provenance["knowledge_base_sha256"], "provenance.knowledge_base_sha256")
    if provenance["knowledge_base_sha256"] != kb_digest:
        raise ValueError("B5 provenance knowledge-base digest does not match the loaded KB")
    scale = BenchLiabilityScaleV1.from_dict(value["scale"])
    expected_by_id = _expected_cases(value["fixture_cases"])
    records = value["fixture_records"]
    if not isinstance(records, list):
        raise ValueError("B5 fixture_records must be an ordered list")
    if tuple(expected_by_id) != tuple(item.get("case_id") for item in records if isinstance(item, Mapping)):
        raise ValueError("B5 config does not declare exactly the materialized fixture cases")
    cases = tuple(_case_from_record(item, expected_by_id[item["case_id"]]) for item in records)
    if len(cases) != len(expected_by_id) or len({case.case_id for case in cases}) != len(cases):
        raise ValueError("B5 fixture records contain duplicate or missing case identities")
    _validate_content_seals(scale, cases)
    if scale.scale_id != provenance["scale_id"]:
        raise ValueError("B5 scale identity is not bound to provenance")
    if scale.fixture_content_sha256 != metadata_digest or scale.fixture_config_sha256 != config_digest:
        raise ValueError("B5 scale provenance is not bound to the loaded fixture")
    for case in cases:
        manifest = case.receipt.provenance_manifest
        if manifest != provenance:
            raise ValueError("B5 case receipt provenance is not exactly the committed authority")
        if case.receipt.scale != scale:
            raise ValueError("B5 case scale is not exactly the committed authority")
        for row in (*case.receipt.role_receipts, *case.receipt.local_deltas, *case.receipt.prize_static, *case.receipt.gust_exposures, *case.receipt.spread_exposures):
            if row.fixture_content_sha256 != metadata_digest or row.fixture_config_sha256 != config_digest:
                raise ValueError("B5 nested receipt row provenance is stale")
    canonical = _sha_json(_fixture_payload(cases, scale, dependencies))
    if canonical != metadata_digest or canonical != B5_CANONICAL_FIXTURE_DIGEST:
        raise ValueError("B5 canonical fixture content digest does not match its sealed authority")
    return B5FixtureBundleV1(config_path or Path("<memory>"), scale, cases)


def load_b5_fixtures(path: str | Path | None = None) -> B5FixtureBundleV1:
    config_path = Path(path) if path is not None else _config_root() / _CONFIG_RELATIVE
    with config_path.open(encoding="utf-8") as handle:
        return materialize_b5_fixture_data(json.load(handle), config_path=config_path)


def _decision(state: PublicStateV1 | None, formulation: str, status: str, *, reason: str | None = None, candidates: Sequence[BenchCandidateV1] = (), chosen: BenchCandidateV1 | None = None, action: CompoundActionV1 | None = None, key: tuple[Any, ...] = ()) -> BenchDecisionV1:
    request = state.request if isinstance(state, PublicStateV1) else None
    return BenchDecisionV1(
        B5_SCHEMA_VERSION, request.request_id if request else "terminal", request.selection_seq if request else (state.transition_id if state else 0), request.acting_player if request else (state.acting_player if state else None), CurrentBenchLiabilityEvaluatorV1.policy_id, formulation, status, EXPERIMENTAL_BENCH_AUTHORITY if status == SELECTED else B0_DELEGATION_AUTHORITY,
        (chosen.action_key,) if chosen else (), chosen.option.semantic_fingerprint if chosen else None, (chosen.option.semantic_fingerprint,) if chosen else (), (chosen.option.original_index,) if chosen else (), key, len(candidates), reason, tuple(candidates), FIXTURE_ONLY, action, bool(action.stopped_early) if action else False, False, 0,
    )


def _delegate(state: PublicStateV1 | None, formulation: str, reason: str, candidates: Sequence[BenchCandidateV1] = ()) -> BenchDecisionV1:
    return _decision(state, formulation, B0_DELEGATE, reason=reason, candidates=candidates)


def _receipt_axis_failure(receipt: B5CapabilityReceiptV1) -> str | None:
    """Reject duplicate semantic axes even when an attacker reseals the aggregate."""

    role_axes: dict[tuple[Any, ...], BenchRoleReceiptV1] = {}
    role_routes: dict[tuple[Any, ...], BenchRoleReceiptV1] = {}
    for row in receipt.role_receipts:
        route_key = (row.entity_key, row.route_id, row.role_id)
        semantic_key = route_key + (row.necessity, row.required_count, row.source_observation_digest)
        if route_key in role_routes and _canonical_value(role_routes[route_key]) != _canonical_value(row):
            return "ROLE_RECEIPT_CONFLICT"
        if semantic_key in role_axes:
            return "RECEIPT_GRAPH_MISMATCH"
        role_routes[route_key] = row
        role_axes[semantic_key] = row
    axes: dict[str, set[tuple[Any, ...]]] = {
        "local": set(), "prize": set(), "gust": set(), "spread": set(),
    }
    for row in receipt.local_deltas:
        key = (row.option_fingerprint, row.current_public_observation_digest)
        if key in axes["local"]:
            return "RECEIPT_GRAPH_MISMATCH"
        axes["local"].add(key)
    for row in receipt.prize_static:
        key = (row.entity_key, row.card_id, row.source_observation_digest)
        if key in axes["prize"]:
            return "RECEIPT_GRAPH_MISMATCH"
        axes["prize"].add(key)
    for row in receipt.gust_exposures:
        key = (row.option_semantic_fingerprint, row.source_entity_key, row.target_entity_key, row.current_public_observation_digest, row.target_role)
        if key in axes["gust"]:
            return "RECEIPT_GRAPH_MISMATCH"
        axes["gust"].add(key)
    for row in receipt.spread_exposures:
        key = (row.option_semantic_fingerprint, row.source_entity_key, row.target_entity_key, row.current_public_observation_digest, row.target_role)
        if key in axes["spread"]:
            return "RECEIPT_GRAPH_MISMATCH"
        axes["spread"].add(key)
    return None


class CurrentBenchLiabilityEvaluatorV1:
    """Stateful, fixture-only B5-A/B evaluator."""

    policy_id = "b5-current-public-bench-liability-fixture-v1"

    def __init__(self, receipt: B5CapabilityReceiptV1) -> None:
        if not isinstance(receipt, B5CapabilityReceiptV1):
            raise TypeError("B5 evaluator requires a B5CapabilityReceiptV1")
        self.receipt = receipt
        self._authority_case: B5FixtureCaseV1 | None = None
        self._authority_error: str | None = None
        try:
            bundle = load_b5_fixtures()
            # F05 itself is named ``...PLAYER-MIRROR``.  Only the explicit
            # mirror transport variant has the doubled suffix.
            mirror_variant = receipt.fixture_case_id.endswith("-MIRROR-MIRROR")
            base_id = receipt.fixture_case_id.removesuffix("-MIRROR") if mirror_variant else receipt.fixture_case_id
            base = next((item for item in bundle.cases if item.case_id == base_id), None)
            if base is None:
                self._authority_error = "RECEIPT_CONTENT_MISMATCH"
            else:
                self._authority_case = mirror_b5_case(base) if mirror_variant else base
                if _canonical_value(receipt) != _canonical_value(self._authority_case.receipt):
                    self._authority_error = "RECEIPT_CONTENT_MISMATCH"
        except (OSError, TypeError, ValueError, KeyError):
            self._authority_error = "FIXTURE_AUTHORITY_UNAVAILABLE"
        self._outcomes: dict[tuple[tuple[str, int, int], str, str], BenchDecisionV1] = {}
        self._latest: dict[tuple[str, int, int], tuple[str, BenchDecisionV1]] = {}
        self._request_ids: dict[tuple[str, int], dict[str, int]] = {}

    def reset(self, episode_uuid: str, player_index: int, *, reason: str = "start") -> None:
        if not isinstance(episode_uuid, str) or not episode_uuid or player_index not in (0, 1):
            raise ValueError("invalid B5 lifecycle identity")
        if reason not in {"start", "terminal", "error", "worker_replacement", "permutation"}:
            raise ValueError("unknown B5 lifecycle reset reason")
        self._latest = {key: value for key, value in self._latest.items() if key[:2] != (episode_uuid, player_index)}
        self._outcomes = {key: value for key, value in self._outcomes.items() if key[0][:2] != (episode_uuid, player_index)}
        self._request_ids = {key: value for key, value in self._request_ids.items() if key != (episode_uuid, player_index)}

    @staticmethod
    def build_optional_stop(request: SelectionRequestV1) -> CompoundActionV1:
        if request.min_count != 0 or request.max_count != 1:
            raise ValueError("B5 STOP requires a 0..1 singleton request")
        builder = CompoundActionBuilder(request)
        builder.stop()
        return builder.build()

    def evaluate_case(self, case: B5FixtureCaseV1, formulation: str) -> BenchDecisionV1:
        return self.evaluate(case.state, case.local_deltas, formulation, fixture=case)

    def evaluate(self, state_or_observation: PublicStateV1 | EngineObservationV1, local_deltas: Mapping[str, BenchLocalDeltaV1] | None, formulation: str, *, fixture: B5FixtureCaseV1 | None = None) -> BenchDecisionV1:
        if formulation not in {A_FORMULATION, B_FORMULATION}:
            raise ValueError("unknown B5 formulation")
        # Terminal-first is intentional: request/local-delta fields are stale
        # and must not be touched after a terminal observation.
        if isinstance(state_or_observation, EngineObservationV1):
            state = PublicStateV1.from_engine(state_or_observation, None)
        elif isinstance(state_or_observation, PublicStateV1):
            state = state_or_observation
        else:
            raise TypeError("B5 evaluator requires PublicStateV1 or EngineObservationV1")
        if state.terminal_result is not None:
            return _decision(state, formulation, TERMINAL_OVERRIDE)
        if state.request is None:
            return _delegate(state, formulation, "MISSING_CURRENT_REQUEST")
        request = state.request
        payload = _safe_payload_hash(state, request, formulation, local_deltas, fixture.case_id if fixture else self.receipt.fixture_case_id)
        if payload is None:
            return _delegate(state, formulation, MALFORMED_LOCAL_DELTAS)
        lifecycle = (request.episode_uuid, request.acting_player, request.selection_seq)
        prior = self._request_ids.get((request.episode_uuid, request.acting_player), {})
        if prior and request.selection_seq < max(prior.values()):
            return self._remember(lifecycle, formulation, payload, request, _delegate(state, formulation, "STALE_SELECTION_SEQUENCE"))
        if request.request_id in prior and prior[request.request_id] != request.selection_seq:
            return self._remember(lifecycle, formulation, payload, request, _delegate(state, formulation, "STALE_OR_REUSED_REQUEST_IDENTITY"))
        cached = self._outcomes.get((lifecycle, formulation, payload))
        if cached is not None:
            return cached
        if lifecycle in self._latest:
            return self._remember(lifecycle, formulation, payload, request, _delegate(state, formulation, "STALE_OR_REUSED_REQUEST_IDENTITY"))
        result = self._evaluate_current(state, local_deltas, formulation, fixture)
        return self._remember(lifecycle, formulation, payload, request, result)

    def _remember(self, lifecycle: tuple[str, int, int], formulation: str, payload: str, request: SelectionRequestV1, result: BenchDecisionV1) -> BenchDecisionV1:
        self._outcomes[(lifecycle, formulation, payload)] = result
        self._latest[lifecycle] = (payload, result)
        self._request_ids.setdefault((request.episode_uuid, request.acting_player), {})[request.request_id] = request.selection_seq
        return result

    def _evaluate_current(self, state: PublicStateV1, local_deltas: Mapping[str, BenchLocalDeltaV1] | None, formulation: str, fixture: B5FixtureCaseV1 | None) -> BenchDecisionV1:
        request = state.request
        assert request is not None
        if request.selection_type != 0 or request.selection_context != 0:
            return _delegate(state, formulation, "UNSUPPORTED_BENCH_REQUEST")
        if (
            type(request.min_count) is not int or type(request.max_count) is not int
            or (request.min_count, request.max_count) not in {(0, 1), (1, 1)}
        ):
            return _delegate(state, formulation, COMPOUND_UNSUPPORTED)
        if request.ordering != "UNORDERED" or request.max_count > 1:
            return _delegate(state, formulation, COMPOUND_UNSUPPORTED)
        if any(option.option_type == 14 for option in request.options):
            return _delegate(state, formulation, STOP_UNRESOLVED)
        if not isinstance(local_deltas, Mapping):
            return _delegate(state, formulation, "UNKNOWN_CURRENT_RECEIPT")
        authority = self._validate_receipts(state, request, local_deltas, fixture)
        if authority is not None:
            return _delegate(state, formulation, authority)
        bench_count = sum(entity.owner == request.acting_player and entity.zone == AREA["BENCH"] for entity in state.entities)
        player = next((item for item in state.observation.players if item.player_index == request.acting_player), None)
        if player is None:
            return _delegate(state, formulation, "UNKNOWN_CURRENT_RECEIPT")
        if bench_count >= player.bench_max:
            return _delegate(state, formulation, "BENCH_CAPACITY_EXHAUSTED")
        candidates: list[BenchCandidateV1] = []
        for option in request.options:
            if not option.available:
                continue
            delta = local_deltas[option.semantic_fingerprint]
            if not delta.action_eligible:
                continue
            surplus = delta.after_role_surplus
            try:
                liability = self._liability(option, self.receipt)
            except (StopIteration, ValueError, TypeError):
                return _delegate(state, formulation, UNKNOWN_CURRENT_RECEIPT)
            candidates.append(BenchCandidateV1(option, delta.action_key, True, max(0, delta.required_role_counts.get("BACKUP_ATTACKER", 0) - delta.after_role_coverage.get("BACKUP_ATTACKER", 0)), surplus.get("BACKUP_ATTACKER", 0), surplus.get("NEXT_ATTACKER", 0), player.bench_max - delta.after_bench_occupancy, liability))
        if not candidates:
            if request.min_count == 0:
                try:
                    action = self.build_optional_stop(request)
                except (TypeError, ValueError):
                    return _delegate(state, formulation, COMPOUND_UNSUPPORTED)
                return _decision(state, formulation, SELECTED, action=action, key=("STOP",))
            return _delegate(state, formulation, "NO_COVERED_ACTION")
        if formulation == A_FORMULATION:
            ranked = sorted(candidates, key=lambda item: (item.remaining_required_slots, -item.backup_surplus, -item.next_surplus, -item.capacity_slack, *item.liability))
            best_key = (ranked[0].remaining_required_slots, -ranked[0].backup_surplus, -ranked[0].next_surplus, -ranked[0].capacity_slack, *ranked[0].liability)
            tied = [item for item in ranked if (item.remaining_required_slots, -item.backup_surplus, -item.next_surplus, -item.capacity_slack, *item.liability) == best_key]
        else:
            def dominates(left: BenchCandidateV1, right: BenchCandidateV1) -> bool:
                # B5-B is intentionally receipt-bounded: role/capacity
                # feasibility has already been established above, and the
                # formulation may select only a strict component-wise
                # liability dominator.  It never lexicographically resolves
                # incomparable liability vectors.
                lv = left.liability
                rv = right.liability
                return all(a <= b for a, b in zip(lv, rv)) and any(a < b for a, b in zip(lv, rv))
            tied = [item for item in candidates if all(item is other or dominates(item, other) for other in candidates)]
            best_key = ("STRICT_DOMINANCE",) if len(tied) == 1 else ()
        if len(tied) != 1:
            return _delegate(state, formulation, "LIABILITY_NOT_STRICTLY_DOMINATING" if formulation == B_FORMULATION else AMBIGUOUS, candidates)
        chosen = tied[0]
        index = next(index for index, item in enumerate(request.options) if item.semantic_fingerprint == chosen.option.semantic_fingerprint)
        try:
            builder = CompoundActionBuilder(request)
            builder.choose(index)
            action = builder.build()
        except Exception:
            return _delegate(state, formulation, "ACTION_BUILD_FAILED", candidates)
        return _decision(state, formulation, SELECTED, chosen=chosen, action=action, candidates=candidates, key=best_key)

    # The methods below intentionally appear after the narrow historical
    # implementation above: keeping the replacement local makes the fixture
    # gate reviewable without touching B0-B4 modules.
    def _fixture_authority_failure(self, state: PublicStateV1, request: SelectionRequestV1, deltas: Mapping[str, BenchLocalDeltaV1], fixture: B5FixtureCaseV1 | None) -> str | None:
        if self._authority_error is not None:
            return self._authority_error
        authority = self._authority_case
        if authority is None or fixture is None or fixture.case_id != authority.case_id:
            return "RECEIPT_CONTENT_MISMATCH"
        if _canonical_value(fixture.observation) != _canonical_value(authority.observation):
            return "RECEIPT_CONTENT_MISMATCH"
        if _canonical_value(fixture.receipt) != _canonical_value(authority.receipt):
            return "RECEIPT_CONTENT_MISMATCH"
        if _canonical_value(state.observation) != _canonical_value(authority.observation):
            return "RECEIPT_CONTENT_MISMATCH"
        canonical_request = authority.request
        if (
            request.episode_uuid != canonical_request.episode_uuid or request.selection_seq != canonical_request.selection_seq
            or request.request_id != canonical_request.request_id or request.acting_player != canonical_request.acting_player
            or request.selection_type != canonical_request.selection_type or request.selection_context != canonical_request.selection_context
            or request.min_count != canonical_request.min_count or request.max_count != canonical_request.max_count
            or request.ordering != canonical_request.ordering
        ):
            return "RECEIPT_CONTENT_MISMATCH"
        canonical_options = {item.semantic_fingerprint: item for item in canonical_request.options}
        supplied_options = {item.semantic_fingerprint: item for item in request.options}
        if set(canonical_options) != set(supplied_options):
            return "RECEIPT_GRAPH_MISMATCH"
        if any(_canonical_value(canonical_options[key]) != _canonical_value(supplied_options[key]) for key in canonical_options):
            return "RECEIPT_CONTENT_MISMATCH"
        if _canonical_value(state) != _canonical_value(PublicStateV1.from_engine(state.observation, request)):
            return "RECEIPT_CONTENT_MISMATCH"
        expected_deltas = {row.option_fingerprint: row for row in authority.receipt.local_deltas}
        if set(deltas) != set(expected_deltas):
            return "RECEIPT_GRAPH_MISMATCH"
        for fingerprint, supplied in deltas.items():
            if any(type(value) is not int or value < 0 for value in (supplied.before_bench_occupancy, supplied.after_bench_occupancy)):
                return "NONFINITE_OR_INVALID_CURRENT_DELTA"
            field_failure = _public_field_failure(supplied.current_public_fields, supplied.successor_fields)
            if field_failure is not None:
                return field_failure
            if supplied.receipt_id != expected_deltas[fingerprint].receipt_id:
                return "UNREGISTERED_LOCAL_DELTA"
            if _canonical_value(supplied) != _canonical_value(expected_deltas[fingerprint]):
                return "RECEIPT_CONTENT_MISMATCH"
        return None

    def _liability(self, option: LegalOptionV1, receipt: B5CapabilityReceiptV1) -> tuple[int, int, int]:
        prize = next(item for item in receipt.prize_static if item.entity_key == option.source_entity_key)
        gust = next(item for item in receipt.gust_exposures if item.target_entity_key == option.source_entity_key)
        spread = next(item for item in receipt.spread_exposures if item.target_entity_key == option.source_entity_key)
        prize_level = receipt.scale.validate_level(prize.prize_units, "prize_units")
        gust_level = receipt.scale.validate_level(gust.exposure_level, "gust.exposure_level")
        spread_level = receipt.scale.validate_level(spread.exposure_level, "spread.exposure_level")
        return (prize_level, gust_level if gust.current_targetable else 0, spread_level)

    def _validate_receipts(self, state: PublicStateV1, request: SelectionRequestV1, deltas: Mapping[str, BenchLocalDeltaV1], fixture: B5FixtureCaseV1 | None) -> str | None:
        receipt = self.receipt
        axis_failure = _receipt_axis_failure(receipt)
        if axis_failure is not None:
            return axis_failure
        try:
            for row in receipt.prize_static:
                receipt.scale.validate_level(row.prize_units, "prize_units")
            for row in receipt.gust_exposures:
                receipt.scale.validate_level(row.exposure_level, "gust.exposure_level")
            for row in receipt.spread_exposures:
                receipt.scale.validate_level(row.exposure_level, "spread.exposure_level")
        except (TypeError, ValueError):
            return NONFINITE_OR_INVALID_LIABILITY
        authority_failure = self._fixture_authority_failure(state, request, deltas, fixture)
        if authority_failure is not None:
            return authority_failure
        if receipt.content_sha256 != _content_digest(receipt):
            return "RECEIPT_CONTENT_MISMATCH"
        observation_digest = stable_hash(state.observation)
        roles_for_entity: dict[str, list[BenchRoleReceiptV1]] = {}
        role_by_id = {item.receipt_id: item for item in receipt.role_receipts}
        for role in receipt.role_receipts:
            if role.content_sha256 != _content_digest(role) or role.source_observation_digest != observation_digest:
                return "RECEIPT_CONTENT_MISMATCH"
            entity = next((item for item in state.entities if item.entity_key == role.entity_key), None)
            if entity is None or (entity.card_id, entity.owner, entity.zone, entity.metadata_ref) != (role.card_id, role.owner, role.zone, role.metadata_ref):
                return UNKNOWN_CURRENT_RECEIPT
            if role.qualification_status != FIXTURE_ONLY or role.role_status not in {"COVERED", "REQUIRED_UNCOVERED", "EXPOSED"}:
                return UNKNOWN_CURRENT_RECEIPT
            roles_for_entity.setdefault(role.entity_key, []).append(role)
        if any(role.necessity == "REQUIRED" and role.role_status != "COVERED" for role in receipt.role_receipts):
            return ROLE_FLOOR_UNSATISFIED
        for option in request.options:
            if not option.available:
                if option.semantic_fingerprint in deltas:
                    return "RECEIPT_GRAPH_MISMATCH"
                continue
            if option.option_type != 7 or option.option_name != "PLAY" or option.choice_role != "PLAY" or option.source_kind != "ENTITY" or option.target_kind != "PSEUDO":
                return "UNSUPPORTED_BENCH_OPTION"
            if option.in_play_area != AREA["BENCH"] or option.in_play_index != 1:
                return "UNSUPPORTED_BENCH_OPTION"
            if (option.target_ref or "").split(":") != ["pseudo", "area", str(AREA["ME"]), "player", str(request.acting_player), "index", "1"]:
                return "UNSUPPORTED_BENCH_OPTION"
            entity = next((item for item in state.entities if item.entity_key == option.source_entity_key), None)
            if entity is None or (entity.owner, entity.zone) != (request.acting_player, AREA["HAND"]):
                return UNKNOWN_CURRENT_RECEIPT
            delta = deltas[option.semantic_fingerprint]
            if any(type(value) is not int or value < 0 for value in (delta.before_bench_occupancy, delta.after_bench_occupancy)):
                return "NONFINITE_OR_INVALID_CURRENT_DELTA"
            field_failure = _public_field_failure(delta.current_public_fields, delta.successor_fields)
            if field_failure is not None:
                return field_failure
            if delta.unknown_fields:
                return UNKNOWN_CURRENT_RECEIPT
            if delta.qualification_status != FIXTURE_ONLY or delta.scope != FIXTURE_ONLY or not delta.no_successor_fields:
                return UNKNOWN_CURRENT_RECEIPT
            if (
                delta.option_fingerprint != option.semantic_fingerprint
                or delta.option_semantic_fingerprint != option.semantic_fingerprint
                or delta.option_semantic_payload_digest != stable_hash(option.semantic_payload())
                or (delta.selection_type, delta.selection_context, delta.option_type) != (option.selection_type, option.selection_context, option.option_type)
                or (delta.source_entity_key, delta.source_card_id, delta.source_owner, delta.source_zone, delta.source_metadata_ref) != (option.source_entity_key, option.card_id, entity.owner, entity.zone, entity.metadata_ref)
                or delta.target_entity_key is not None or delta.target_card_id is not None or delta.target_metadata_ref is not None
                or delta.target_owner != request.acting_player or delta.target_zone != AREA["BENCH"]
            ):
                return "RECEIPT_GRAPH_MISMATCH"
            if delta.current_public_observation_digest != observation_digest:
                return UNKNOWN_CURRENT_RECEIPT
            bench_count = sum(item.owner == request.acting_player and item.zone == AREA["BENCH"] for item in state.entities)
            if delta.before_bench_occupancy != bench_count:
                return "NONFINITE_OR_INVALID_CURRENT_DELTA"
            player = next((item for item in state.observation.players if item.player_index == request.acting_player), None)
            if player is None:
                return UNKNOWN_CURRENT_RECEIPT
            if delta.after_bench_occupancy > player.bench_max:
                return "BENCH_CAPACITY_EXHAUSTED"
            if not delta.affected_role_receipt_ids or any(item not in role_by_id for item in delta.affected_role_receipt_ids):
                return "RECEIPT_GRAPH_MISMATCH"
            entity_roles = roles_for_entity.get(option.source_entity_key, [])
            if not entity_roles:
                return UNKNOWN_CURRENT_RECEIPT
            for role_id, required_count in delta.required_role_counts.items():
                if type(required_count) is not int or required_count < 0:
                    return ROLE_FLOOR_UNSATISFIED
                if required_count and (
                    sum(item.required_count for item in entity_roles if item.role_id == role_id and item.role_status == "COVERED") < required_count
                    or delta.after_role_coverage.get(role_id, 0) < required_count
                ):
                    return ROLE_FLOOR_UNSATISFIED
            if any(type(value) is not int or value < 0 for value in (*delta.before_role_coverage.values(), *delta.after_role_coverage.values(), *delta.after_role_surplus.values())):
                return ROLE_FLOOR_UNSATISFIED
        manifest = receipt.provenance_manifest
        opponent_active = next((item for item in state.entities if item.owner != request.acting_player and item.zone == AREA["ACTIVE"]), None)
        if opponent_active is None:
            return UNKNOWN_CURRENT_RECEIPT
        for row in (*receipt.prize_static, *receipt.gust_exposures, *receipt.spread_exposures):
            if row.content_sha256 != _content_digest(row) or row.qualification_status != FIXTURE_ONLY or row.scope_version != manifest["scope_version"]:
                return "RECEIPT_CONTENT_MISMATCH"
            expected_manifest_digest = _sha_json(_strip_recursive(manifest, frozenset({"fixture_metadata_sha256", "fixture_content_sha256", "fixture_config_sha256", "config_payload_sha256", "config_sha256", "receipt_manifest_sha256", "content_sha256"})))
            if manifest["receipt_manifest_sha256"] != expected_manifest_digest or row.fixture_content_sha256 != manifest["fixture_metadata_sha256"] or row.fixture_config_sha256 != manifest["config_payload_sha256"] or row.receipt_manifest_sha256 != expected_manifest_digest:
                return "RECEIPT_CONTENT_MISMATCH"
        for option in request.options:
            if not option.available:
                continue
            entity = next(item for item in state.entities if item.entity_key == option.source_entity_key)
            prize = next((item for item in receipt.prize_static if item.entity_key == option.source_entity_key), None)
            gust = next((item for item in receipt.gust_exposures if item.target_entity_key == option.source_entity_key), None)
            spread = next((item for item in receipt.spread_exposures if item.target_entity_key == option.source_entity_key), None)
            if prize is None or gust is None or spread is None:
                return UNKNOWN_CURRENT_RECEIPT
            if prize.card_id != option.card_id or prize.metadata_ref != entity.metadata_ref or prize.source_observation_digest != observation_digest:
                return "RECEIPT_GRAPH_MISMATCH"
            if gust.source_entity_key != opponent_active.entity_key or spread.source_entity_key != opponent_active.entity_key:
                return "RECEIPT_GRAPH_MISMATCH"
            if gust.target_role != "BACKUP_ATTACKER" or spread.target_role != "BACKUP_ATTACKER":
                return "RECEIPT_GRAPH_MISMATCH"
            if gust.option_semantic_fingerprint != option.semantic_fingerprint or spread.option_semantic_fingerprint != option.semantic_fingerprint:
                return "RECEIPT_GRAPH_MISMATCH"
            if gust.current_public_observation_digest != observation_digest or spread.current_public_observation_digest != observation_digest:
                return UNKNOWN_CURRENT_RECEIPT
            target_meta = entity.metadata_ref
            source_tuple = (opponent_active.card_id, opponent_active.owner, opponent_active.zone, opponent_active.metadata_ref)
            target_tuple = (option.card_id, request.acting_player, AREA["HAND"], target_meta)
            if (gust.source_card_id, gust.source_owner, gust.source_zone, gust.source_metadata_ref) != source_tuple or (spread.source_card_id, spread.source_owner, spread.source_zone, spread.source_metadata_ref) != source_tuple:
                return "RECEIPT_GRAPH_MISMATCH"
            if (gust.target_card_id, gust.target_owner, gust.target_zone, gust.target_metadata_ref) != target_tuple or (spread.target_card_id, spread.target_owner, spread.target_zone, spread.target_metadata_ref) != target_tuple:
                return "RECEIPT_GRAPH_MISMATCH"
            try:
                self._liability(option, receipt)
            except (StopIteration, ValueError, TypeError):
                return NONFINITE_OR_INVALID_LIABILITY
        return None


__all__ = [
    "A_FORMULATION", "AMBIGUOUS", "B0_DELEGATE", "B_FORMULATION", "B5CapabilityReceiptV1", "B5FixtureBundleV1", "B5FixtureCaseV1", "B5_SCHEMA_VERSION", "BenchLiabilityScaleV1", "CurrentBenchLiabilityEvaluatorV1", "CARD_PROSE_FORBIDDEN", "COMPOUND_UNSUPPORTED", "FIXTURE_ONLY", "HIDDEN_INFORMATION_FORBIDDEN", "MALFORMED_LOCAL_DELTAS", "NONFINITE_OR_INVALID_LIABILITY", "ROLE_FLOOR_UNSATISFIED", "SELECTED", "STOP_UNRESOLVED", "SUCCESSOR_VALUE_FORBIDDEN", "TERMINAL_OVERRIDE", "UNKNOWN_CURRENT_RECEIPT", "load_b5_fixtures", "materialize_b5_fixture_data", "mirror_b5_case", "semantic_permutation_suite",
]
