"""Restricted Phase B1 current-state route oracle.

This module is intentionally separate from the frozen B0 control.  The
``CurrentStateRouteOracleV1`` is a diagnostic evaluator, not a PolicyV1
adapter: it only scores the complete current legal option set using public
observation fields and explicitly qualified numeric receipts.  It never
accepts successor states, counterfactual outcomes, hidden-card identities,
response priors, or native engine objects.  The separate
``OfflineFixtureEvaluatorV1`` accepts only sealed, declared public fixture
classes for the original F01-F12 design tests; those fields never enter the
runtime oracle.

The receipt boundary is deliberately strict.  ``FIXTURE_ONLY`` metadata may
be used by deterministic fixture tests, while ``NATIVE_QUALIFIED`` metadata
is required for a future runtime caller.  No static card text or ``ex`` flag
is interpreted as a Prize value or an effect.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from ptcg_rl.g1.models import EngineObservationV1, LegalOptionV1, SelectionRequestV1, stable_hash
from ptcg_rl.g1.semantic import AREA, OPTION_NAMES, SELECT_OPTION_TYPES

from .state import PublicStateError, PublicStateV1


B1_SCHEMA_VERSION = 1
A_FORMULATION = "B1-R-A-CURRENT-ROBUST-LOWER-BOUND"
B_FORMULATION = "B1-R-B-CURRENT-PUBLIC-THREAT-MARGIN"
OFFLINE_A_FORMULATION = "B1-A-LEXICOGRAPHIC-ROBUST-ROUTE"
OFFLINE_B_FORMULATION = "B1-B-FINITE-PUBLIC-ENVELOPE"
SELECTED = "SELECTED"
NO_SAFE_ROUTE = "NO_SAFE_ROUTE"
AMBIGUOUS = "AMBIGUOUS"
UNSUPPORTED = "UNSUPPORTED"
B0_DELEGATE = "B0_DELEGATE"
TERMINAL_OVERRIDE = "TERMINAL_OVERRIDE"
UNRESOLVED = "UNRESOLVED"
UNKNOWN = "UNKNOWN"
OFFLINE_FIXTURE = "FIXTURE_ONLY"
RUNTIME_NATIVE = "NATIVE_QUALIFIED"

EXACT_PASS_ATTACK_IDS = frozenset({1044, 1045})
PARTIAL_ATTACK_IDS = frozenset({1042, 1043, 1046, 1047})
PARTIAL_EFFECT_CARD_IDS = frozenset({1262})
_ALLOWED_SCOPES = frozenset({OFFLINE_FIXTURE, RUNTIME_NATIVE})


def _digest(value: str, field_name: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{field_name} must be a SHA-256 digest")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"{field_name} must be hexadecimal") from error
    return value.lower()


def _positive_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def _finite_number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{field_name} must be finite numeric")
    return float(value)


def _finite_tree(value: Any) -> bool:
    """Return false for non-finite numeric values anywhere in a decision key."""

    if isinstance(value, Mapping):
        return all(_finite_tree(key) and _finite_tree(item) for key, item in value.items())
    if isinstance(value, (tuple, list, frozenset)):
        return all(_finite_tree(item) for item in value)
    if isinstance(value, float):
        return math.isfinite(value)
    return value is None or isinstance(value, (bool, int, str))


def _scope(value: str) -> str:
    if value not in _ALLOWED_SCOPES:
        raise ValueError(f"unknown receipt scope {value!r}")
    return value


@dataclass(frozen=True)
class CardStaticV1:
    """Numeric card metadata; effect prose is intentionally absent."""

    card_id: int
    hp: int
    card_type: int | None
    weakness_type: int | None
    resistance_type: int | None
    resistance_value: int
    engine_sha256: str
    card_data_sha256: str
    scope: str = OFFLINE_FIXTURE

    def __post_init__(self) -> None:
        _positive_int(self.card_id, "card_id")
        _positive_int(self.hp, "hp")
        if self.card_type is not None and (isinstance(self.card_type, bool) or not isinstance(self.card_type, int)):
            raise ValueError("card_type must be numeric or None")
        for name, value in (("weakness_type", self.weakness_type), ("resistance_type", self.resistance_type)):
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
                raise ValueError(f"{name} must be numeric or None")
        if isinstance(self.resistance_value, bool) or not isinstance(self.resistance_value, int) or self.resistance_value < 0:
            raise ValueError("resistance_value must be a nonnegative integer")
        _digest(self.engine_sha256, "engine_sha256")
        _digest(self.card_data_sha256, "card_data_sha256")
        _scope(self.scope)


@dataclass(frozen=True)
class AttackStaticV1:
    """A fully qualified numeric attack capsule."""

    card_id: int
    attack_id: int
    damage: int
    energy_counts: tuple[int, ...]
    attack_type: int | None
    engine_sha256: str
    card_data_sha256: str
    scope: str = OFFLINE_FIXTURE
    effect_status: str = "PASS"

    def __post_init__(self) -> None:
        _positive_int(self.card_id, "attack card_id")
        _positive_int(self.attack_id, "attack_id")
        if isinstance(self.damage, bool) or not isinstance(self.damage, int) or self.damage < 0:
            raise ValueError("attack damage must be a nonnegative integer")
        if not isinstance(self.energy_counts, tuple) or len(self.energy_counts) != 12:
            raise ValueError("energy_counts must contain twelve numeric slots")
        if any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in self.energy_counts):
            raise ValueError("energy_counts must be nonnegative integers")
        if self.attack_type is not None and (isinstance(self.attack_type, bool) or not isinstance(self.attack_type, int)):
            raise ValueError("attack_type must be numeric or None")
        _digest(self.engine_sha256, "engine_sha256")
        _digest(self.card_data_sha256, "card_data_sha256")
        _scope(self.scope)
        if self.effect_status not in {"PASS", "PARTIAL", "UNKNOWN"}:
            raise ValueError("unknown attack effect status")

    @property
    def qualified(self) -> bool:
        return self.effect_status == "PASS"


@dataclass(frozen=True)
class PrizeStaticV1:
    """Explicit engine-qualified Prize-unit metadata.

    Prize values are not inferred from card type, ``ex`` flags, or card text.
    """

    card_id: int
    prize_units: int
    engine_sha256: str
    card_data_sha256: str
    scope: str = OFFLINE_FIXTURE

    def __post_init__(self) -> None:
        _positive_int(self.card_id, "prize card_id")
        _positive_int(self.prize_units, "prize_units")
        _digest(self.engine_sha256, "engine_sha256")
        _digest(self.card_data_sha256, "card_data_sha256")
        _scope(self.scope)


@dataclass(frozen=True)
class ContextCapabilityV1:
    """Exact current-request context capsule; no wildcard effect semantics."""

    selection_type: int
    selection_context: int
    option_type: int
    context_card_id: int | None
    effect_card_id: int | None
    choice_role: str
    scope: str = OFFLINE_FIXTURE

    def __post_init__(self) -> None:
        for name, value in (
            ("selection_type", self.selection_type),
            ("selection_context", self.selection_context),
            ("option_type", self.option_type),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"context {name} must be an integer")
        if self.selection_type not in SELECT_OPTION_TYPES:
            raise ValueError("unknown context selection type")
        if self.selection_context < 0 or self.selection_context >= 49:
            raise ValueError("unknown context selection context")
        if self.option_type not in OPTION_NAMES or self.option_type not in SELECT_OPTION_TYPES[self.selection_type]:
            raise ValueError("context option type is incompatible")
        for name, value in (("context_card_id", self.context_card_id), ("effect_card_id", self.effect_card_id)):
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
                raise ValueError(f"context {name} must be an integer or None")
        if not isinstance(self.choice_role, str) or self.choice_role != OPTION_NAMES[self.option_type]:
            raise ValueError("context choice role is not canonical")
        _scope(self.scope)

    def matches(self, request: SelectionRequestV1, option: LegalOptionV1) -> bool:
        return (
            self.selection_type == request.selection_type
            and self.selection_context == request.selection_context
            and self.option_type == option.option_type
            and self.context_card_id == request.context_card_id
            and self.effect_card_id == request.effect_card_id
            and self.choice_role == option.choice_role
        )


@dataclass(frozen=True)
class CapabilityReceiptV1:
    """Version-bound capability receipt used as the runtime trust boundary."""

    schema_version: int
    receipt_id: str
    engine_sha256: str
    card_data_sha256: str
    scope: str
    cards: tuple[CardStaticV1, ...] = ()
    attacks: tuple[AttackStaticV1, ...] = ()
    prizes: tuple[PrizeStaticV1, ...] = ()
    contexts: tuple[ContextCapabilityV1, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int) or self.schema_version != B1_SCHEMA_VERSION:
            raise ValueError("unknown B1 capability schema version")
        if not isinstance(self.receipt_id, str) or not self.receipt_id:
            raise ValueError("receipt_id must be nonempty")
        _digest(self.engine_sha256, "engine_sha256")
        _digest(self.card_data_sha256, "card_data_sha256")
        _scope(self.scope)
        if not all(isinstance(item, CardStaticV1) for item in self.cards):
            raise ValueError("cards contain an invalid capsule")
        if not all(isinstance(item, AttackStaticV1) for item in self.attacks):
            raise ValueError("attacks contain an invalid capsule")
        if not all(isinstance(item, PrizeStaticV1) for item in self.prizes):
            raise ValueError("prizes contain an invalid capsule")
        if not all(isinstance(item, ContextCapabilityV1) for item in self.contexts):
            raise ValueError("contexts contain an invalid capsule")
        nested = (*self.cards, *self.attacks, *self.prizes, *self.contexts)
        if any(item.scope != self.scope for item in nested):
            raise ValueError("nested receipt scope differs from parent scope")
        for item in (*self.cards, *self.attacks, *self.prizes):
            if item.engine_sha256 != self.engine_sha256 or item.card_data_sha256 != self.card_data_sha256:
                raise ValueError("nested receipt asset digest differs from parent receipt")
        if len({item.card_id for item in self.cards}) != len(self.cards):
            raise ValueError("duplicate card capsule")
        if len({item.attack_id for item in self.attacks}) != len(self.attacks):
            raise ValueError("duplicate attack capsule")
        if len({item.card_id for item in self.prizes}) != len(self.prizes):
            raise ValueError("duplicate Prize capsule")

    @property
    def card_by_id(self) -> dict[int, CardStaticV1]:
        return {item.card_id: item for item in self.cards}

    @property
    def attack_by_id(self) -> dict[int, AttackStaticV1]:
        return {item.attack_id: item for item in self.attacks}

    @property
    def prize_by_id(self) -> dict[int, PrizeStaticV1]:
        return {item.card_id: item for item in self.prizes}

    def runtime_qualified(self) -> bool:
        nested = (*self.cards, *self.attacks, *self.prizes, *self.contexts)
        return bool(nested) and self.scope == RUNTIME_NATIVE and all(
            item.scope == RUNTIME_NATIVE for item in nested
        )

    def supports_context(self, request: SelectionRequestV1, option: LegalOptionV1) -> bool:
        return any(item.matches(request, option) for item in self.contexts)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CapabilityReceiptV1":
        return cls(
            schema_version=int(value["schema_version"]),
            receipt_id=str(value["receipt_id"]),
            engine_sha256=str(value["engine_sha256"]),
            card_data_sha256=str(value["card_data_sha256"]),
            scope=str(value["scope"]),
            cards=tuple(CardStaticV1(**item) for item in value.get("cards", ())),
            attacks=tuple(
                AttackStaticV1(
                    **{
                        **item,
                        "energy_counts": tuple(item["energy_counts"]),
                    }
                )
                for item in value.get("attacks", ())
            ),
            prizes=tuple(PrizeStaticV1(**item) for item in value.get("prizes", ())),
            contexts=tuple(ContextCapabilityV1(**item) for item in value.get("contexts", ())),
        )


@dataclass(frozen=True)
class RouteFeatureV1:
    guaranteed_current_ko: bool | None
    public_prize_distance_lower_bound: int | None
    visible_threat_loss_guard: bool | None
    next_attacker_energy_deficit: int | None
    backup_attacker_count: int | None
    bench_liability: int | None
    visible_threat_denial: bool | None
    current_active_survival_slack: int | None
    next_attacker_ready: bool | None
    resource_reserve: int | None

    def __post_init__(self) -> None:
        for name in (
            "guaranteed_current_ko", "visible_threat_loss_guard", "visible_threat_denial",
            "next_attacker_ready",
        ):
            value = getattr(self, name)
            if value is not None and not isinstance(value, bool):
                raise ValueError(f"{name} must be boolean or None")
        for name in (
            "public_prize_distance_lower_bound", "next_attacker_energy_deficit",
            "backup_attacker_count", "bench_liability", "resource_reserve",
        ):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                raise ValueError(f"{name} must be a nonnegative integer or None")
        slack = self.current_active_survival_slack
        if slack is not None and (isinstance(slack, bool) or not isinstance(slack, int)):
            raise ValueError("current_active_survival_slack must be an integer or None")

    def as_named(self) -> dict[str, dict[str, Any]]:
        return {
            name: {"value": value, "known": value is not None, "source": "current_public_or_receipt"}
            for name, value in self.__dict__.items()
        }


@dataclass(frozen=True)
class RouteCandidateV1:
    fingerprint: str
    semantic_key: tuple[str, ...]
    features: RouteFeatureV1
    is_stop: bool = False


@dataclass(frozen=True)
class RouteDecisionV1:
    schema_version: int
    request_id: str
    selection_seq: int
    acting_player: int | None
    policy_id: str
    status: str
    formulation_id: str
    authority: str
    chosen_semantic_action_key: tuple[str, ...] = ()
    chosen_option_fingerprints: tuple[str, ...] = ()
    decision_key: tuple[Any, ...] = ()
    candidate_count: int = 0
    complete_route_count: int = 0
    pruned_count: int = 0
    declared_response_class_count: int = 0
    fail_closed_reason: str | None = None
    partial_effect_dependencies: tuple[int, ...] = ()
    route_activation_id: str | None = None
    route_key_sha256: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or not isinstance(self.schema_version, int) or self.schema_version != B1_SCHEMA_VERSION:
            raise ValueError("unknown route decision schema version")
        if self.status not in {
            SELECTED, NO_SAFE_ROUTE, AMBIGUOUS, UNSUPPORTED, B0_DELEGATE, TERMINAL_OVERRIDE, UNRESOLVED, UNKNOWN
        }:
            raise ValueError("unknown route decision status")
        for name in ("candidate_count", "complete_route_count", "pruned_count", "declared_response_class_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be nonnegative")
        if not _finite_tree(self.decision_key):
            raise ValueError("route decision key contains NaN/Inf")


@dataclass(frozen=True)
class RouteDiagnosticsV1:
    route_requests: int = 0
    route_active_requests: int = 0
    route_abstention_count: int = 0
    b0_delegation_count: int = 0
    unsupported_requests: int = 0
    ambiguous_requests: int = 0
    no_safe_route: int = 0
    terminal_overrides: int = 0
    hidden_leak_rejections: int = 0
    unknown_resource_count: int = 0
    unsupported_partial_semantic_count: int = 0
    tie_count: int = 0


@dataclass
class _MutableDiagnostics:
    route_requests: int = 0
    route_active_requests: int = 0
    route_abstention_count: int = 0
    b0_delegation_count: int = 0
    unsupported_requests: int = 0
    ambiguous_requests: int = 0
    no_safe_route: int = 0
    terminal_overrides: int = 0
    hidden_leak_rejections: int = 0
    unknown_resource_count: int = 0
    unsupported_partial_semantic_count: int = 0
    tie_count: int = 0

    def snapshot(self) -> RouteDiagnosticsV1:
        return RouteDiagnosticsV1(**self.__dict__)


@dataclass(frozen=True)
class OfflineResponseClassV1:
    label: str
    score: float
    weight: float

    def __post_init__(self) -> None:
        if not isinstance(self.label, str) or not self.label:
            raise ValueError("response class label must be nonempty")
        _finite_number(self.score, "response score")
        if _finite_number(self.weight, "response weight") <= 0:
            raise ValueError("response weight must be positive")


@dataclass(frozen=True)
class OfflineRouteCandidateV1:
    semantic_key: str
    strategic_key: tuple[int, ...]
    response_classes: tuple[OfflineResponseClassV1, ...]
    # These fields are deliberately offline-only.  They describe a sealed
    # public successor fixture; CurrentStateRouteOracleV1 never accepts them.
    route_distance: int | None = None
    horizon_required: int | None = None
    horizon_limit: int | None = None
    branch_count: int | None = None
    branch_budget: int | None = None
    next_attacker_ready: bool | None = None
    live_backup_count: int | None = None
    bench_liability: int | None = None
    resource_reserve: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.semantic_key, str) or not self.semantic_key:
            raise ValueError("offline candidate semantic key must be nonempty")
        if not isinstance(self.strategic_key, tuple) or any(
            isinstance(item, bool) or not isinstance(item, int) for item in self.strategic_key
        ):
            raise ValueError("offline candidate strategic key must be an integer tuple")
        if not isinstance(self.response_classes, tuple) or any(
            not isinstance(item, OfflineResponseClassV1) for item in self.response_classes
        ):
            raise ValueError("offline candidate response classes are malformed")
        for name in (
            "route_distance", "horizon_required", "horizon_limit", "branch_count",
            "branch_budget", "live_backup_count", "bench_liability", "resource_reserve",
        ):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                raise ValueError(f"offline candidate {name} must be a nonnegative integer or None")
        if self.next_attacker_ready is not None and not isinstance(self.next_attacker_ready, bool):
            raise ValueError("offline candidate next_attacker_ready must be boolean or None")


@dataclass(frozen=True)
class OfflineFixtureResultV1:
    status: str
    robust_choice: str | None = None
    mean_choice: str | None = None
    candidate_count: int = 0
    declared_response_class_count: int = 0
    reason: str | None = None
    selected_choice: str | None = None
    max_horizon_pruned: int = 0
    strength_score: float | None = None
    tie_break_field: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {SELECTED, NO_SAFE_ROUTE, AMBIGUOUS, UNSUPPORTED, UNRESOLVED}:
            raise ValueError("unknown offline fixture result status")
        for name in ("candidate_count", "declared_response_class_count", "max_horizon_pruned"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        if self.strength_score is not None and not math.isfinite(float(self.strength_score)):
            raise ValueError("offline fixture strength score must be finite")


class OfflineFixtureEvaluatorV1:
    """Evaluate declared public response envelopes, never native snapshots."""

    def compare(
        self,
        candidates: Sequence[OfflineRouteCandidateV1],
        formulation_id: str | None = None,
    ) -> OfflineFixtureResultV1:
        values = tuple(candidates)
        if any(not isinstance(item, OfflineRouteCandidateV1) for item in values):
            return OfflineFixtureResultV1(UNSUPPORTED, candidate_count=len(values), reason="offline candidate type required")
        if formulation_id is not None:
            if formulation_id not in {OFFLINE_A_FORMULATION, OFFLINE_B_FORMULATION}:
                return OfflineFixtureResultV1(UNSUPPORTED, candidate_count=len(values), reason="unknown offline formulation")
            return self._compare_bounded_routes(values, formulation_id)
        if len(values) < 2:
            return OfflineFixtureResultV1(UNSUPPORTED, candidate_count=len(values), reason="complete candidate set required")
        if any(not isinstance(item.semantic_key, str) or not item.semantic_key for item in values):
            return OfflineFixtureResultV1(UNSUPPORTED, candidate_count=len(values), reason="candidate semantic key is missing")
        if len({item.semantic_key for item in values}) != len(values):
            return OfflineFixtureResultV1(UNSUPPORTED, candidate_count=len(values), reason="duplicate candidate semantic key")
        if any(not item.response_classes for item in values):
            return OfflineFixtureResultV1(UNSUPPORTED, candidate_count=len(values), reason="response envelope incomplete")
        classes = [item for candidate in values for item in candidate.response_classes]
        if any(not math.isfinite(float(item.score)) or not math.isfinite(float(item.weight)) for item in classes):
            return OfflineFixtureResultV1(UNSUPPORTED, candidate_count=len(values), reason="non-finite response envelope")
        robust_values: dict[str, float] = {}
        mean_values: dict[str, float] = {}
        for candidate in values:
            total_weight = sum(item.weight for item in candidate.response_classes)
            if total_weight <= 0 or not math.isfinite(total_weight):
                return OfflineFixtureResultV1(UNRESOLVED, candidate_count=len(values), reason="response weights unresolved")
            robust_values[candidate.semantic_key] = min(item.score for item in candidate.response_classes)
            mean = sum(item.score * item.weight for item in candidate.response_classes) / total_weight
            if not math.isfinite(mean):
                return OfflineFixtureResultV1(UNRESOLVED, candidate_count=len(values), reason="response mean is non-finite")
            mean_values[candidate.semantic_key] = mean
        robust_best = max(robust_values.values())
        mean_best = max(mean_values.values())
        robust_keys = sorted(key for key, value in robust_values.items() if value == robust_best)
        mean_keys = sorted(key for key, value in mean_values.items() if value == mean_best)
        if len(robust_keys) != 1 or len(mean_keys) != 1:
            return OfflineFixtureResultV1(AMBIGUOUS, candidate_count=len(values), declared_response_class_count=len(classes), reason="non-equivalent response tie")
        return OfflineFixtureResultV1(
            SELECTED,
            robust_choice=robust_keys[0],
            mean_choice=mean_keys[0],
            candidate_count=len(values),
            declared_response_class_count=len(classes),
        )

    @staticmethod
    def _pruned_branches(candidate: OfflineRouteCandidateV1) -> int:
        excess: list[int] = []
        if candidate.horizon_required is not None and candidate.horizon_limit is not None:
            if candidate.horizon_required > candidate.horizon_limit:
                excess.append(candidate.horizon_required - candidate.horizon_limit)
        if candidate.branch_count is not None and candidate.branch_budget is not None:
            if candidate.branch_count > candidate.branch_budget:
                excess.append(candidate.branch_count - candidate.branch_budget)
        return max(excess, default=0)

    def _compare_bounded_routes(
        self,
        values: tuple[OfflineRouteCandidateV1, ...],
        formulation_id: str,
    ) -> OfflineFixtureResultV1:
        """Compare sealed public successor fixtures only.

        This is deliberately not shared with CurrentStateRouteOracleV1.  A
        route is inactive when the declared horizon/branch envelope is
        incomplete; it must not receive a proxy strength score or silently
        outrank a complete route.
        """

        if len(values) < 2:
            return OfflineFixtureResultV1(UNSUPPORTED, candidate_count=len(values), reason="complete candidate set required")
        if len({item.semantic_key for item in values}) != len(values):
            return OfflineFixtureResultV1(UNSUPPORTED, candidate_count=len(values), reason="duplicate candidate semantic key")
        if any(not item.response_classes for item in values):
            return OfflineFixtureResultV1(UNSUPPORTED, candidate_count=len(values), reason="response envelope incomplete")
        classes = [item for candidate in values for item in candidate.response_classes]
        if any(not math.isfinite(float(item.score)) or not math.isfinite(float(item.weight)) for item in classes):
            return OfflineFixtureResultV1(UNSUPPORTED, candidate_count=len(values), reason="non-finite response envelope")

        robust_values: dict[str, float] = {}
        mean_values: dict[str, float] = {}
        for candidate in values:
            total_weight = sum(item.weight for item in candidate.response_classes)
            if total_weight <= 0 or not math.isfinite(total_weight):
                return OfflineFixtureResultV1(UNRESOLVED, candidate_count=len(values), reason="response weights unresolved")
            robust_values[candidate.semantic_key] = min(item.score for item in candidate.response_classes)
            mean = sum(item.score * item.weight for item in candidate.response_classes) / total_weight
            if not math.isfinite(mean):
                return OfflineFixtureResultV1(UNRESOLVED, candidate_count=len(values), reason="response mean is non-finite")
            mean_values[candidate.semantic_key] = mean

        pruned = sum(self._pruned_branches(candidate) for candidate in values)
        if pruned:
            return OfflineFixtureResultV1(
                NO_SAFE_ROUTE,
                candidate_count=len(values),
                declared_response_class_count=len(classes),
                reason="bounded public route horizon or branch budget was pruned",
                max_horizon_pruned=pruned,
            )
        paired_bounds = (
            (candidate.horizon_required, candidate.horizon_limit) for candidate in values
        )
        if any((required is None) != (limit is None) for required, limit in paired_bounds):
            return OfflineFixtureResultV1(UNSUPPORTED, candidate_count=len(values), reason="horizon bound is incomplete")
        paired_branches = ((candidate.branch_count, candidate.branch_budget) for candidate in values)
        if any((count is None) != (budget is None) for count, budget in paired_branches):
            return OfflineFixtureResultV1(UNSUPPORTED, candidate_count=len(values), reason="branch bound is incomplete")
        required_fields = (
            "route_distance", "next_attacker_ready", "live_backup_count", "bench_liability", "resource_reserve"
        )
        if any(getattr(candidate, name) is None for candidate in values for name in required_fields):
            return OfflineFixtureResultV1(UNSUPPORTED, candidate_count=len(values), reason="complete route metadata required")

        def key(candidate: OfflineRouteCandidateV1) -> tuple[Any, ...]:
            if formulation_id == OFFLINE_A_FORMULATION:
                return (
                    robust_values[candidate.semantic_key],
                    -candidate.route_distance,
                    int(candidate.next_attacker_ready),
                    -candidate.bench_liability,
                    candidate.resource_reserve,
                    candidate.live_backup_count,
                )
            return (
                mean_values[candidate.semantic_key],
                -candidate.route_distance,
                int(candidate.next_attacker_ready),
                candidate.resource_reserve,
                -candidate.bench_liability,
                candidate.live_backup_count,
            )

        keys = {candidate.semantic_key: key(candidate) for candidate in values}
        best_key = max(keys.values())
        best = tuple(candidate for candidate in values if keys[candidate.semantic_key] == best_key)
        if len(best) != 1:
            return OfflineFixtureResultV1(
                AMBIGUOUS,
                candidate_count=len(values),
                declared_response_class_count=len(classes),
                reason="non-equivalent offline route tie",
            )
        selected = best[0]
        score = robust_values[selected.semantic_key] if formulation_id == OFFLINE_A_FORMULATION else mean_values[selected.semantic_key]
        return OfflineFixtureResultV1(
            SELECTED,
            robust_choice=selected.semantic_key if formulation_id == OFFLINE_A_FORMULATION else None,
            mean_choice=selected.semantic_key if formulation_id == OFFLINE_B_FORMULATION else None,
            candidate_count=len(values),
            declared_response_class_count=len(classes),
            selected_choice=selected.semantic_key,
            strength_score=score,
        )


def _entity_map(observation: EngineObservationV1) -> dict[str, Any]:
    return {entity.entity_key: entity for entity in observation.entities}


def _active(observation: EngineObservationV1, player: int) -> Any | None:
    return next(
        (
            entity
            for entity in observation.entities
            if entity.owner == player and entity.zone == AREA["ACTIVE"] and entity.position == 0
        ),
        None,
    )


def _board(observation: EngineObservationV1, player: int, zone: int) -> tuple[Any, ...]:
    return tuple(entity for entity in observation.entities if entity.owner == player and entity.zone == zone)


def _energy_deficit(entity: Any, attack: AttackStaticV1) -> int | None:
    if not isinstance(entity.attached_energy_count, int) or entity.attached_energy_count < 0:
        return None
    if len(entity.energy_types) != entity.attached_energy_count:
        return None
    counts = Counter(entity.energy_types)
    if any(isinstance(item, bool) or not isinstance(item, int) or item < 0 or item >= 12 for item in entity.energy_types):
        return None
    return sum(max(required - counts.get(index, 0), 0) for index, required in enumerate(attack.energy_counts))


class CurrentStateRouteOracleV1:
    """Pure current-observation evaluator for the preregistered A/B keys."""

    policy_id = "b1-current-public-route-oracle-v1"

    def __init__(self, receipt: CapabilityReceiptV1, *, mode: str = OFFLINE_FIXTURE) -> None:
        if not isinstance(receipt, CapabilityReceiptV1):
            raise TypeError("B1 oracle requires a CapabilityReceiptV1")
        if mode not in _ALLOWED_SCOPES:
            raise ValueError("unknown oracle mode")
        self.receipt = receipt
        self.mode = mode
        self._diagnostics = _MutableDiagnostics()

    @property
    def diagnostics(self) -> RouteDiagnosticsV1:
        return self._diagnostics.snapshot()

    def _decision(
        self,
        status: str,
        observation: EngineObservationV1 | None,
        request: SelectionRequestV1 | None,
        *,
        formulation_id: str,
        reason: str | None = None,
        candidate_count: int = 0,
        complete_route_count: int = 0,
        key: tuple[Any, ...] = (),
        chosen: RouteCandidateV1 | None = None,
        partial: tuple[int, ...] = (),
    ) -> RouteDecisionV1:
        authority = "EXPERIMENTAL_PUBLIC_ROUTE" if status == SELECTED else "B0_CONTROL"
        if isinstance(request, SelectionRequestV1):
            request_id = request.request_id
            sequence = request.selection_seq
            acting = request.acting_player
        elif isinstance(observation, EngineObservationV1):
            request_id = "terminal" if observation.terminal_result is not None else "unsupported"
            sequence = observation.transition_id
            acting = observation.acting_player
        else:
            request_id = "unsupported"
            sequence = 0
            acting = None
        chosen_key = chosen.semantic_key if chosen else ()
        fingerprints = (chosen.fingerprint,) if chosen else ()
        route_key = (
            stable_hash(
                {
                    "mode": self.mode,
                    "receipt_id": self.receipt.receipt_id,
                    "engine_sha256": self.receipt.engine_sha256,
                    "card_data_sha256": self.receipt.card_data_sha256,
                    "formulation": formulation_id,
                    "key": key,
                    "chosen": chosen_key,
                }
            )
            if key
            else None
        )
        if status == SELECTED:
            authority = (
                "EXPERIMENTAL_PUBLIC_ROUTE_RUNTIME"
                if self.mode == RUNTIME_NATIVE
                else "EXPERIMENTAL_PUBLIC_ROUTE_FIXTURE"
            )
        return RouteDecisionV1(
            schema_version=B1_SCHEMA_VERSION,
            request_id=request_id,
            selection_seq=sequence,
            acting_player=acting,
            policy_id=self.policy_id,
            status=status,
            formulation_id=formulation_id,
            authority=authority,
            chosen_semantic_action_key=chosen_key,
            chosen_option_fingerprints=fingerprints,
            decision_key=key,
            candidate_count=candidate_count,
            complete_route_count=complete_route_count,
            fail_closed_reason=reason,
            partial_effect_dependencies=partial,
            route_activation_id=(
                "B1-RUNTIME-ORACLE-001" if self.mode == RUNTIME_NATIVE else "B1-OFFLINE-FIXTURE-001"
            ) if status == SELECTED else None,
            route_key_sha256=route_key,
        )

    def evaluate(
        self,
        observation: EngineObservationV1,
        request: SelectionRequestV1 | None,
        formulation_id: str = A_FORMULATION,
    ) -> RouteDecisionV1:
        """Return a decision without touching request data for terminal states."""

        if isinstance(observation, EngineObservationV1) and observation.terminal_result is not None:
            # Normalize the terminal record without ever reading request fields.  The
            # PublicState boundary intentionally ignores a stale terminal request.
            try:
                PublicStateV1.from_engine(observation, request)
            except PublicStateError as error:
                if "opponent hand" in str(error) or "hidden" in str(error):
                    self._diagnostics.hidden_leak_rejections += 1
                self._diagnostics.unsupported_requests += 1
                self._diagnostics.b0_delegation_count += 1
                return self._decision(UNSUPPORTED, observation, None, formulation_id=formulation_id, reason=f"terminal public boundary: {error}")
            self._diagnostics.terminal_overrides += 1
            return self._decision(TERMINAL_OVERRIDE, observation, None, formulation_id=formulation_id, reason="terminal checked first")
        self._diagnostics.route_requests += 1
        if formulation_id not in {A_FORMULATION, B_FORMULATION}:
            self._diagnostics.unsupported_requests += 1
            self._diagnostics.b0_delegation_count += 1
            return self._decision(UNSUPPORTED, observation, request, formulation_id=formulation_id, reason="unknown formulation")
        if self.mode == RUNTIME_NATIVE and not self.receipt.runtime_qualified():
            self._diagnostics.b0_delegation_count += 1
            return self._decision(B0_DELEGATE, observation, request, formulation_id=formulation_id, reason="fixture-only receipt is not runtime qualified")
        if not isinstance(observation, EngineObservationV1) or not isinstance(request, SelectionRequestV1):
            self._diagnostics.unsupported_requests += 1
            self._diagnostics.b0_delegation_count += 1
            return self._decision(UNSUPPORTED, observation, request, formulation_id=formulation_id, reason="current observation/request required")
        try:
            PublicStateV1.from_engine(observation, request)
        except PublicStateError as error:
            if "opponent hand" in str(error) or "hidden" in str(error):
                self._diagnostics.hidden_leak_rejections += 1
            self._diagnostics.unsupported_requests += 1
            self._diagnostics.b0_delegation_count += 1
            return self._decision(UNSUPPORTED, observation, request, formulation_id=formulation_id, reason=f"public boundary: {error}")
        board_positions: set[tuple[int, int, int]] = set()
        for entity in observation.entities:
            if entity.zone not in {AREA["ACTIVE"], AREA["BENCH"]} or entity.position is None:
                continue
            position = (entity.owner, entity.zone, entity.position)
            if position in board_positions:
                self._diagnostics.unsupported_requests += 1
                self._diagnostics.b0_delegation_count += 1
                return self._decision(
                    UNSUPPORTED,
                    observation,
                    request,
                    formulation_id=formulation_id,
                    reason="public board position is duplicated",
                )
            board_positions.add(position)
        if observation.battle_id != request.episode_uuid or observation.acting_player != request.acting_player or observation.transition_id != request.selection_seq:
            self._diagnostics.unsupported_requests += 1
            self._diagnostics.b0_delegation_count += 1
            return self._decision(UNSUPPORTED, observation, request, formulation_id=formulation_id, reason="request lifecycle identity mismatch")
        available_stop = any(self._is_stop(option) and option.available for option in request.options)
        if request.max_count != request.min_count or request.max_count != 1:
            if not (request.min_count == 0 and request.max_count == 1 and available_stop):
                self._diagnostics.b0_delegation_count += 1
                return self._decision(B0_DELEGATE, observation, request, formulation_id=formulation_id, reason="unsupported compound count or missing explicit STOP")
        elif any(self._is_stop(option) and option.available for option in request.options):
            self._diagnostics.b0_delegation_count += 1
            return self._decision(B0_DELEGATE, observation, request, formulation_id=formulation_id, reason="STOP is illegal for a forced singleton request")
        available = tuple(option for option in request.options if option.available)
        if not available:
            self._diagnostics.b0_delegation_count += 1
            return self._decision(B0_DELEGATE, observation, request, formulation_id=formulation_id, reason="no available legal option")
        candidates: list[RouteCandidateV1] = []
        partial: set[int] = set()
        entity_map = _entity_map(observation)
        for option in available:
            if request.min_count == 0 and self._is_stop(option):
                candidates.append(
                    RouteCandidateV1(
                        fingerprint=option.semantic_fingerprint,
                        semantic_key=(option.semantic_fingerprint,),
                        features=self._unknown_features(),
                        is_stop=True,
                    )
                )
                continue
            candidate, reason, partial_ids = self._candidate(observation, request, option, entity_map)
            partial.update(partial_ids)
            if candidate is None:
                self._diagnostics.unsupported_requests += 1
                self._diagnostics.unsupported_partial_semantic_count += bool(partial_ids)
                self._diagnostics.b0_delegation_count += 1
                return self._decision(
                    B0_DELEGATE,
                    observation,
                    request,
                    formulation_id=formulation_id,
                    reason=reason,
                    candidate_count=len(candidates),
                    partial=tuple(sorted(partial)),
                )
            # ``resource_reserve`` is intentionally diagnostic-only until an
            # exact card-role receipt exists.  It must not deactivate an
            # otherwise complete route merely because the non-authoritative
            # field is unknown.
            if not candidate.is_stop and any(
                value is None
                for name, value in candidate.features.__dict__.items()
                if name != "resource_reserve"
            ):
                self._diagnostics.unknown_resource_count += 1
                self._diagnostics.b0_delegation_count += 1
                return self._decision(
                    UNKNOWN,
                    observation,
                    request,
                    formulation_id=formulation_id,
                    reason="current route feature is unknown",
                    candidate_count=len(candidates),
                )
            candidates.append(candidate)
        if not candidates:
            self._diagnostics.b0_delegation_count += 1
            return self._decision(B0_DELEGATE, observation, request, formulation_id=formulation_id, reason="STOP is not a route candidate")
        selected = self._select(candidates, formulation_id)
        if selected is None:
            self._diagnostics.ambiguous_requests += 1
            self._diagnostics.route_abstention_count += 1
            self._diagnostics.tie_count += 1
            key = self._strategic_key(candidates[0], formulation_id)
            return self._decision(AMBIGUOUS, observation, request, formulation_id=formulation_id, candidate_count=len(candidates), complete_route_count=len(candidates), key=key)
        self._diagnostics.route_active_requests += 1
        return self._decision(
            SELECTED,
            observation,
            request,
            formulation_id=formulation_id,
            candidate_count=len(candidates),
            complete_route_count=len(candidates),
            key=self._strategic_key(selected, formulation_id),
            chosen=selected,
        )

    @staticmethod
    def _is_stop(option: LegalOptionV1) -> bool:
        return option.option_type == 14 or option.choice_role.upper() in {"STOP", "END"}

    def _candidate(
        self,
        observation: EngineObservationV1,
        request: SelectionRequestV1,
        option: LegalOptionV1,
        entities: Mapping[str, Any],
    ) -> tuple[RouteCandidateV1 | None, str, tuple[int, ...]]:
        if option.option_type == 13:
            if option.attack_id not in EXACT_PASS_ATTACK_IDS:
                partial_ids = (option.attack_id,) if option.attack_id in PARTIAL_ATTACK_IDS else ()
                return None, "attack is outside the qualified current route subset", partial_ids
            attack = self.receipt.attack_by_id.get(option.attack_id)
            if attack is None:
                return None, "unknown attack capsule", (option.attack_id,) if option.attack_id is not None else ()
            if not attack.qualified:
                return None, "partial or unknown attack effect", (attack.attack_id,)
            source = entities.get(option.source_entity_key) if option.source_entity_key else None
            target = _active(observation, 1 - observation.acting_player)
            if (
                source is None
                or target is None
                or option.source_kind != "ENTITY"
                or option.target_kind != "NONE"
                or option.target_entity_key is not None
                or source.owner != observation.acting_player
                or target.owner != 1 - observation.acting_player
                or source.card_id != attack.card_id
                or source.zone != AREA["ACTIVE"]
                or source.position != 0
                or target.zone not in {AREA["ACTIVE"], AREA["BENCH"]}
            ):
                return None, "attack source/target is not a current public entity", ()
            features = self._attack_features(observation, source, target, attack)
        elif option.option_type == 8 and self.receipt.supports_context(request, option):
            source = entities.get(option.source_entity_key) if option.source_entity_key else None
            target = entities.get(option.target_entity_key) if option.target_entity_key else None
            if (
                source is None
                or target is None
                or source.owner != observation.acting_player
                or target.owner != observation.acting_player
                or source.card_id != 3
                or source.zone != AREA["HAND"]
                or target.zone not in {AREA["ACTIVE"], AREA["BENCH"]}
                or option.area not in {None, AREA["HAND"]}
                or option.in_play_area not in {None, target.zone}
                or option.in_play_index not in {None, target.position}
            ):
                return None, "attach context lacks explicit public Basic Water source", ()
            features = self._attach_features(observation, target)
        else:
            partial_ids = (option.attack_id,) if option.attack_id in PARTIAL_ATTACK_IDS else ((option.card_id,) if option.card_id in PARTIAL_EFFECT_CARD_IDS else ())
            return None, "unsupported current option context or partial effect", tuple(item for item in partial_ids if item is not None)
        key = (option.semantic_fingerprint,)
        return RouteCandidateV1(option.semantic_fingerprint, key, features), "", ()

    def _attack_features(self, observation: EngineObservationV1, source: Any, target: Any, attack: AttackStaticV1) -> RouteFeatureV1:
        actor = observation.acting_player
        opponent = 1 - actor
        source_card = self.receipt.card_by_id.get(source.card_id)
        target_card = self.receipt.card_by_id.get(target.card_id)
        prize = self.receipt.prize_by_id.get(target.card_id)
        deficit = _energy_deficit(source, attack)
        if source_card is None or target_card is None or prize is None or target.hp is None or source_card.hp is None:
            return self._unknown_features()
        effective = self._effective_damage(attack, target_card)
        if deficit is None or effective is None:
            return self._unknown_features()
        ko = deficit == 0 and effective >= target.hp
        active = _active(observation, actor)
        active_card = self.receipt.card_by_id.get(active.card_id) if active is not None else None
        threat_damage, threat_known = self._strongest_opponent_damage(observation, active_card)
        if active is None or active.hp is None or not threat_known:
            survival = None
            guard = None
        else:
            survival = active.hp - threat_damage
            ready_backup = self._ready_backup_count(observation)
            guard = not (threat_damage >= active.hp and not ko and ready_backup == 0)
        backup = self._ready_backup_count(observation)
        next_deficit = self._next_attacker_deficit(observation)
        liability = self._bench_liability(observation)
        return RouteFeatureV1(
            guaranteed_current_ko=ko,
            public_prize_distance_lower_bound=max(0, observation.players[opponent].prize_count - prize.prize_units) if ko else observation.players[opponent].prize_count,
            visible_threat_loss_guard=guard,
            next_attacker_energy_deficit=next_deficit,
            backup_attacker_count=backup,
            bench_liability=liability,
            visible_threat_denial=ko and target.zone == AREA["ACTIVE"] and target.position == 0,
            current_active_survival_slack=survival,
            next_attacker_ready=next_deficit == 0 if next_deficit is not None else None,
            resource_reserve=None,
        )

    def _attach_features(self, observation: EngineObservationV1, target: Any) -> RouteFeatureV1:
        next_deficit = self._next_attacker_deficit(observation, attached_target=target)
        active = _active(observation, observation.acting_player)
        active_card = self.receipt.card_by_id.get(active.card_id) if active is not None else None
        threat_damage, known = self._strongest_opponent_damage(observation, active_card)
        survival = active.hp - threat_damage if known and active is not None and active.hp is not None else None
        # A plain Energy attachment does not remove the current public threat.
        # It can make a replacement ready, which is represented separately.
        denial = False
        return RouteFeatureV1(
            guaranteed_current_ko=False,
            public_prize_distance_lower_bound=observation.players[1 - observation.acting_player].prize_count,
            visible_threat_loss_guard=not (known and active is not None and active.hp is not None and threat_damage >= active.hp),
            next_attacker_energy_deficit=next_deficit,
            backup_attacker_count=self._ready_backup_count(observation),
            bench_liability=self._bench_liability(observation),
            visible_threat_denial=denial,
            current_active_survival_slack=survival,
            next_attacker_ready=next_deficit == 0 if next_deficit is not None else None,
            resource_reserve=None,
        )

    @staticmethod
    def _unknown_features() -> RouteFeatureV1:
        return RouteFeatureV1(None, None, None, None, None, None, None, None, None, None)

    def _effective_damage(self, attack: AttackStaticV1, target: CardStaticV1) -> int | None:
        if attack.attack_type is None:
            return None
        damage = attack.damage
        if target.weakness_type is not None and target.weakness_type == attack.attack_type:
            damage *= 2
        if target.resistance_type is not None and target.resistance_type == attack.attack_type:
            damage = max(0, damage - target.resistance_value)
        return damage

    def _strongest_opponent_damage(self, observation: EngineObservationV1, target_card: CardStaticV1 | None) -> tuple[int, bool]:
        opponent_active = _active(observation, 1 - observation.acting_player)
        if opponent_active is None or target_card is None:
            return 0, False
        attacks = tuple(attack for attack in self.receipt.attacks if attack.card_id == opponent_active.card_id)
        if not attacks:
            return 0, False
        values: list[int] = []
        for attack in attacks:
            if not attack.qualified:
                return 0, False
            if _energy_deficit(opponent_active, attack) is None:
                return 0, False
            if _energy_deficit(opponent_active, attack) == 0:
                damage = self._effective_damage(attack, target_card)
                if damage is None:
                    return 0, False
                values.append(damage)
        return (max(values) if values else 0), True

    def _ready_backup_count(self, observation: EngineObservationV1) -> int | None:
        count = 0
        for entity in _board(observation, observation.acting_player, AREA["BENCH"]):
            attacks = tuple(attack for attack in self.receipt.attacks if attack.card_id == entity.card_id)
            if not attacks:
                continue
            if any(not attack.qualified for attack in attacks):
                return None
            if any(_energy_deficit(entity, attack) == 0 for attack in attacks):
                count += 1
        return count

    def _next_attacker_deficit(self, observation: EngineObservationV1, attached_target: Any | None = None) -> int | None:
        values: list[int] = []
        for entity in _board(observation, observation.acting_player, AREA["BENCH"]):
            if attached_target is not None and entity.entity_key == attached_target.entity_key:
                energy_types = entity.energy_types + (3,)
                entity = replace(entity, energy_types=energy_types, attached_energy_count=len(energy_types))
            attacks = tuple(attack for attack in self.receipt.attacks if attack.card_id == entity.card_id)
            for attack in attacks:
                if not attack.qualified:
                    return None
                deficit = _energy_deficit(entity, attack)
                if deficit is None:
                    return None
                values.append(deficit)
        return min(values) if values else None

    def _bench_liability(self, observation: EngineObservationV1) -> int | None:
        total = 0
        for entity in _board(observation, observation.acting_player, AREA["BENCH"]):
            prize = self.receipt.prize_by_id.get(entity.card_id)
            if prize is None:
                return None
            total += prize.prize_units
        return total

    @staticmethod
    def _strategic_key(candidate: RouteCandidateV1, formulation_id: str) -> tuple[Any, ...]:
        feature = candidate.features
        if formulation_id == A_FORMULATION:
            return (
                int(feature.guaranteed_current_ko) if feature.guaranteed_current_ko is not None else -1,
                -(feature.public_prize_distance_lower_bound if feature.public_prize_distance_lower_bound is not None else 10**9),
                int(feature.visible_threat_loss_guard) if feature.visible_threat_loss_guard is not None else -1,
                -(feature.next_attacker_energy_deficit if feature.next_attacker_energy_deficit is not None else 10**9),
                feature.backup_attacker_count if feature.backup_attacker_count is not None else -1,
                -(feature.bench_liability if feature.bench_liability is not None else 10**9),
            )
        return (
            int(feature.visible_threat_denial) if feature.visible_threat_denial is not None else -1,
            feature.current_active_survival_slack if feature.current_active_survival_slack is not None else -10**9,
            int(feature.guaranteed_current_ko) if feature.guaranteed_current_ko is not None else -1,
            int(feature.next_attacker_ready) if feature.next_attacker_ready is not None else -1,
            -(feature.public_prize_distance_lower_bound if feature.public_prize_distance_lower_bound is not None else 10**9),
            feature.backup_attacker_count if feature.backup_attacker_count is not None else -1,
            -(feature.bench_liability if feature.bench_liability is not None else 10**9),
        )

    def _select(self, candidates: Sequence[RouteCandidateV1], formulation_id: str) -> RouteCandidateV1 | None:
        ranked = sorted(candidates, key=lambda candidate: self._strategic_key(candidate, formulation_id), reverse=True)
        best_key = self._strategic_key(ranked[0], formulation_id)
        top = [candidate for candidate in ranked if self._strategic_key(candidate, formulation_id) == best_key]
        fingerprints = {candidate.fingerprint for candidate in top}
        if len(fingerprints) > 1:
            return None
        return sorted(top, key=lambda candidate: candidate.fingerprint)[0]


def load_capability_receipt(path: str | Path) -> CapabilityReceiptV1:
    """Load only the versioned local JSON receipt; no native assets are read."""

    with Path(path).open(encoding="utf-8") as handle:
        return CapabilityReceiptV1.from_dict(json.load(handle))


__all__ = [
    "A_FORMULATION", "AMBIGUOUS", "AttackStaticV1", "B0_DELEGATE", "B_FORMULATION",
    "B1_SCHEMA_VERSION", "CapabilityReceiptV1", "CardStaticV1", "ContextCapabilityV1",
    "CurrentStateRouteOracleV1", "NO_SAFE_ROUTE", "OFFLINE_FIXTURE", "OfflineFixtureEvaluatorV1",
    "OfflineFixtureResultV1", "OfflineResponseClassV1", "OfflineRouteCandidateV1", "PrizeStaticV1",
    "RUNTIME_NATIVE", "RouteCandidateV1", "RouteDecisionV1", "RouteDiagnosticsV1", "RouteFeatureV1",
    "OFFLINE_A_FORMULATION", "OFFLINE_B_FORMULATION", "SELECTED", "TERMINAL_OVERRIDE", "UNKNOWN",
    "UNRESOLVED", "UNSUPPORTED", "load_capability_receipt",
]
