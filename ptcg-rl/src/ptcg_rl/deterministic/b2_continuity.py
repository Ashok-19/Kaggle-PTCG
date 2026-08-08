"""Fixture-only Phase B2 next-attacker continuity evaluators.

The two evaluators in this module are deliberately narrower than the frozen
B0 controller.  They accept a current G1 public observation and a complete
current G1 request, apply only a declared one-Energy local delta, and score
the complete legal singleton option set.  They do not simulate successors,
read engine objects, infer hidden cards, or establish native card authority.
"""

from __future__ import annotations

import itertools
import json
import math
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from ptcg_rl.g1.actions import CompoundActionBuilder
from ptcg_rl.g1.models import (
    ContractViolation,
    EngineObservationV1,
    LegalOptionV1,
    SelectionRequestV1,
    record_dict,
    stable_hash,
)
from ptcg_rl.g1.semantic import AREA, OPTION_NAMES

from .state import PublicStateError, PublicStateV1


B2_SCHEMA_VERSION = 1
A_FORMULATION = "B2-A-NEXT-THRESHOLD"
B_FORMULATION = "B2-B-TWO-ATTACKER-TAIL"
SELECTED = "SELECTED"
B0_DELEGATE = "B0_DELEGATE"
AMBIGUOUS = "AMBIGUOUS"
UNSUPPORTED = "UNSUPPORTED"
UNKNOWN = "UNKNOWN"
TERMINAL_OVERRIDE = "TERMINAL_OVERRIDE"
FIXTURE_ONLY = "FIXTURE_ONLY"
QUALIFIED_CABT_CAPSULE = "QUALIFIED_CABT_CAPSULE"
PARTIAL = "PARTIAL"
EXPERIMENTAL_FIXTURE_AUTHORITY = "EXPERIMENTAL_CONTINUITY_FIXTURE"

_QUALIFICATION_STATUSES = frozenset(
    {FIXTURE_ONLY, QUALIFIED_CABT_CAPSULE, PARTIAL, UNKNOWN}
)
_CONFIG_RELATIVE = Path("configs/deterministic/phase_b2_continuity_fixture_v1.json")
_OPTION_FIELDS = frozenset(LegalOptionV1.__dataclass_fields__)
_REQUEST_FIELDS = frozenset(SelectionRequestV1.__dataclass_fields__)
_COMMON_FIELDS = frozenset(EngineObservationV1.__dataclass_fields__)
_FIXTURE_METADATA_RECORD_ID = "phase-b2-continuity-fixture-v1"
_FIXTURE_TARGET_REQUIREMENTS = "fixture-only-opponent-active"
_FIXTURE_EVOLUTION_REQUIREMENTS = {
    "fixture-only-basic-721": (721, 0),
    "fixture-only-stage1-723": (723, 1),
}
_FIXTURE_ENERGY_SIGNATURES = {
    (723, 1046): (0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0),
    (721, 1043): (1, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0),
}


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def _finite_tree(value: Any) -> bool:
    if isinstance(value, Mapping):
        return all(_finite_tree(key) and _finite_tree(item) for key, item in value.items())
    if isinstance(value, (tuple, list, frozenset)):
        return all(_finite_tree(item) for item in value)
    if isinstance(value, float):
        return math.isfinite(value)
    return value is None or isinstance(value, (bool, int, str))


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


@dataclass(frozen=True)
class AttackerCapabilityV1:
    """Complete capability metadata; fixture rows are not native authority."""

    card_id: int
    attack_id: int
    qualification_id: str
    qualification_status: str
    energy_counts: tuple[int, ...]
    evolution_requirement: str
    status_constraints: tuple[int, ...]
    public_target_requirements: str

    def __post_init__(self) -> None:
        _positive_int(self.card_id, "capability card_id")
        _positive_int(self.attack_id, "capability attack_id")
        for name, value in (
            ("qualification_id", self.qualification_id),
            ("evolution_requirement", self.evolution_requirement),
            ("public_target_requirements", self.public_target_requirements),
        ):
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a nonempty string")
        if self.qualification_status not in _QUALIFICATION_STATUSES:
            raise ValueError("unknown capability qualification status")
        if not isinstance(self.energy_counts, tuple) or len(self.energy_counts) != 12:
            raise ValueError("capability energy_counts must contain twelve slots")
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in self.energy_counts
        ):
            raise ValueError("capability energy_counts must be nonnegative integers")
        if not isinstance(self.status_constraints, tuple) or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in self.status_constraints
        ):
            raise ValueError("capability status_constraints are malformed")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AttackerCapabilityV1":
        required = {
            "card_id", "attack_id", "qualification_id", "qualification_status",
            "energy_counts", "evolution_requirement", "status_constraints",
            "public_target_requirements",
        }
        if set(value) != required:
            raise ValueError("capability record must contain the complete declared fields")
        return cls(
            **{
                **dict(value),
                "energy_counts": tuple(value["energy_counts"]),
                "status_constraints": tuple(value["status_constraints"]),
            }
        )


@dataclass(frozen=True)
class CapabilityReceiptV1:
    receipt_id: str
    scope: str
    capabilities: tuple[AttackerCapabilityV1, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.receipt_id, str) or not self.receipt_id:
            raise ValueError("capability receipt id must be nonempty")
        if self.scope not in {FIXTURE_ONLY, QUALIFIED_CABT_CAPSULE}:
            raise ValueError("unknown capability receipt scope")
        if not isinstance(self.capabilities, tuple) or not self.capabilities:
            raise ValueError("capability receipt must contain records")
        keys = [(item.card_id, item.attack_id) for item in self.capabilities]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate capability record")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CapabilityReceiptV1":
        return cls(
            receipt_id=str(value.get("record_id", "b2-fixture-capability-receipt")),
            scope=str(value.get("scope", FIXTURE_ONLY)),
            capabilities=tuple(
                AttackerCapabilityV1.from_dict(item) for item in value["fixture_capabilities"]
            ),
        )

    def for_card(self, card_id: int) -> tuple[AttackerCapabilityV1, ...]:
        return tuple(item for item in self.capabilities if item.card_id == card_id)


@dataclass(frozen=True)
class ContinuityFeaturesV1:
    ready_after: int | None
    best_deficit_after: int | None
    two_backup_tail_after: int | None
    backup_ready_count_after: int | None
    backup_near_ready_count_after: int | None
    next_attacker_ready_after: int | None
    non_active_target_role: int
    unresolved_count: int

    def __post_init__(self) -> None:
        for name in (
            "ready_after", "best_deficit_after", "two_backup_tail_after",
            "backup_ready_count_after", "backup_near_ready_count_after",
            "next_attacker_ready_after", "unresolved_count",
        ):
            value = getattr(self, name)
            if value is not None:
                _nonnegative_int(value, name)
        _nonnegative_int(self.non_active_target_role, "non_active_target_role")


@dataclass(frozen=True)
class ContinuityCandidateV1:
    option: LegalOptionV1
    target_key: str
    semantic_key: tuple[str, ...]
    features: ContinuityFeaturesV1


@dataclass(frozen=True)
class ContinuityDecisionV1:
    schema_version: int
    request_id: str
    selection_seq: int
    acting_player: int | None
    policy_id: str
    formulation_id: str
    status: str
    authority: str
    chosen_target: str | None = None
    chosen_semantic_action_key: tuple[str, ...] = ()
    chosen_option_fingerprints: tuple[str, ...] = ()
    decision_key: tuple[Any, ...] = ()
    candidate_count: int = 0
    fail_closed_reason: str | None = None
    features_by_target: tuple[tuple[str, ContinuityFeaturesV1], ...] = ()

    def __post_init__(self) -> None:
        if self.schema_version != B2_SCHEMA_VERSION:
            raise ValueError("unknown B2 decision schema version")
        if self.status not in {
            SELECTED, B0_DELEGATE, AMBIGUOUS, UNSUPPORTED, UNKNOWN, TERMINAL_OVERRIDE
        }:
            raise ValueError("unknown B2 decision status")
        _nonnegative_int(self.candidate_count, "candidate_count")
        if not _finite_tree(self.decision_key):
            raise ValueError("B2 decision key contains NaN/Inf")


@dataclass(frozen=True)
class ContinuityDiagnosticsV1:
    requests: int = 0
    selected: int = 0
    delegated: int = 0
    ambiguous: int = 0
    terminal_overrides: int = 0
    boundary_rejections: int = 0
    stale_request_rejections: int = 0


@dataclass
class _MutableDiagnostics:
    requests: int = 0
    selected: int = 0
    delegated: int = 0
    ambiguous: int = 0
    terminal_overrides: int = 0
    boundary_rejections: int = 0
    stale_request_rejections: int = 0

    def snapshot(self) -> ContinuityDiagnosticsV1:
        return ContinuityDiagnosticsV1(**self.__dict__)


@dataclass(frozen=True)
class B2FixtureBundleV1:
    config_path: Path
    observation: EngineObservationV1
    request: SelectionRequestV1
    state: PublicStateV1
    receipt: CapabilityReceiptV1
    semantic_targets: Mapping[str, str]


def _entity_map(observation: EngineObservationV1) -> dict[str, Any]:
    return {entity.entity_key: entity for entity in observation.entities}


def _energy_deficit(entity: Any, capability: AttackerCapabilityV1) -> int | None:
    if (
        isinstance(entity.attached_energy_count, bool)
        or not isinstance(entity.attached_energy_count, int)
        or entity.attached_energy_count < 0
        or len(entity.energy_types) != entity.attached_energy_count
    ):
        return None
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0 or value >= 12
        for value in entity.energy_types
    ):
        return None
    counts = Counter(entity.energy_types)
    return sum(max(required - counts.get(index, 0), 0) for index, required in enumerate(capability.energy_counts))


def _map_key(key: str, owner_map: Mapping[int, int]) -> str:
    if not isinstance(key, str) or not key.startswith("p") or ":" not in key:
        return key
    prefix, suffix = key.split(":", 1)
    try:
        owner = int(prefix[1:])
    except ValueError:
        return key
    if owner not in owner_map:
        return key
    return f"p{owner_map[owner]}:{suffix}"


def semantic_permutation_suite(option_count: int, count: int = 32) -> tuple[tuple[int, ...], ...]:
    """Return deterministic B0-sized permutation work without RNG.

    Four semantic options have 24 unique permutations.  The B0 contract still
    executes 32 permutation arms, so the remaining arms repeat the first
    lexicographic permutations rather than inventing a fake fifth option.
    """

    if isinstance(option_count, bool) or not isinstance(option_count, int) or option_count <= 0:
        raise ValueError("option_count must be positive")
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        raise ValueError("permutation count must be positive")
    values = tuple(itertools.permutations(range(option_count)))
    if not values:
        raise ValueError("no permutations available")
    return tuple(values[index % len(values)] for index in range(count))


def _config_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _reject_unknown_fields(value: Mapping[str, Any], allowed: frozenset[str], label: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        if any(str(item).startswith("successor") for item in unknown):
            raise ValueError(f"SUCCESSOR_VALUE_FORBIDDEN: unknown {label} field")
        raise ValueError(f"unknown {label} field: {sorted(unknown)}")


def materialize_b2_fixture_data(value: Mapping[str, Any], *, config_path: Path | None = None) -> B2FixtureBundleV1:
    """Materialize a declared fixture through the real G1/PublicState boundary."""

    if not isinstance(value, Mapping):
        raise ValueError("fixture config must be a mapping")
    allowed_top = frozenset({
        "schema_version", "record_id", "scope", "fixture_metadata_sha256",
        "common_public_state", "fixture_capabilities", "fixture_cases",
    })
    _reject_unknown_fields(value, allowed_top, "fixture")
    if value.get("schema_version") != B2_SCHEMA_VERSION:
        raise ValueError("unknown B2 fixture schema version")
    if value.get("record_id") != _FIXTURE_METADATA_RECORD_ID:
        raise ValueError("unknown B2 fixture record id")
    if value.get("scope") != FIXTURE_ONLY:
        raise ValueError("fixture materializer accepts FIXTURE_ONLY scope only")
    metadata_sha256 = value.get("fixture_metadata_sha256")
    if not _is_sha256(metadata_sha256):
        raise ValueError("fixture metadata digest is not canonical")
    common = value.get("common_public_state")
    if not isinstance(common, Mapping):
        raise ValueError("common_public_state must be a mapping")
    _reject_unknown_fields(common, _COMMON_FIELDS, "observation")
    raw_entities = common.get("entities")
    if not isinstance(raw_entities, list):
        raise ValueError("fixture observation entities must be a list")
    for raw_entity in raw_entities:
        if not isinstance(raw_entity, Mapping):
            raise ValueError("fixture entity must be a mapping")
        if raw_entity.get("card_id") is not None:
            metadata_ref = raw_entity.get("metadata_ref")
            if not isinstance(metadata_ref, str) or metadata_ref.rsplit("@", 1)[-1] != metadata_sha256:
                raise ValueError("FIXTURE_METADATA_VERSION_MISMATCH")
    case_rows = value.get("fixture_cases")
    if (
        not isinstance(case_rows, list)
        or len(case_rows) != 1
        or not isinstance(case_rows[0], Mapping)
        or case_rows[0].get("id") != "B2-F01"
    ):
        raise ValueError("exactly the declared B2-F01 fixture is required")
    case = case_rows[0]
    if set(case) != {"id", "request", "semantic_targets"}:
        raise ValueError("fixture case has unknown or missing fields")
    raw_request = case["request"]
    if not isinstance(raw_request, Mapping):
        raise ValueError("fixture request must be a mapping")
    _reject_unknown_fields(raw_request, _REQUEST_FIELDS | {"options"}, "request")
    raw_options = raw_request.get("options")
    if not isinstance(raw_options, list):
        raise ValueError("fixture request options must be a list")
    options: list[LegalOptionV1] = []
    for raw in raw_options:
        if not isinstance(raw, Mapping):
            raise ValueError("fixture option must be a mapping")
        _reject_unknown_fields(raw, _OPTION_FIELDS | {"semantic_target"}, "option")
        semantic_target = raw.get("semantic_target")
        option_values = {key: item for key, item in raw.items() if key != "semantic_target"}
        option = LegalOptionV1(**option_values)
        if semantic_target != option.target_entity_key:
            raise ValueError("fixture semantic_target does not match the canonical target")
        expected = stable_hash(option.semantic_payload())
        if option.semantic_fingerprint != expected:
            raise ValueError("fixture option semantic fingerprint is not canonical")
        options.append(option)
    request = SelectionRequestV1(**{**dict(raw_request), "options": tuple(options)})
    observation = EngineObservationV1.from_dict(common)
    state = PublicStateV1.from_engine(observation, request)
    if not isinstance(value.get("fixture_capabilities"), list):
        raise ValueError("fixture capabilities must be a list")
    receipt = CapabilityReceiptV1.from_dict(value)
    if receipt.scope != FIXTURE_ONLY:
        raise ValueError("fixture capability receipt must remain FIXTURE_ONLY")
    if any(item.qualification_status != FIXTURE_ONLY for item in receipt.capabilities):
        raise ValueError("fixture capability receipt contains non-fixture authority")
    targets = case.get("semantic_targets")
    if not isinstance(targets, Mapping) or set(targets) != {A_FORMULATION, B_FORMULATION}:
        raise ValueError("fixture semantic targets are incomplete")
    return B2FixtureBundleV1(
        config_path=config_path or Path("<memory>"),
        observation=observation,
        request=request,
        state=state,
        receipt=receipt,
        semantic_targets={str(key): str(item) for key, item in targets.items()},
    )


def load_b2_f01(path: str | Path | None = None) -> B2FixtureBundleV1:
    config_path = Path(path) if path is not None else _config_root() / _CONFIG_RELATIVE
    with config_path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    return materialize_b2_fixture_data(value, config_path=config_path)


def mirror_fixture(fixture: B2FixtureBundleV1) -> B2FixtureBundleV1:
    """Mirror the public fixture to acting player one without hidden identities."""

    owner_map = {0: 1, 1: 0}
    entities = tuple(
        replace(
            entity,
            entity_key=_map_key(entity.entity_key, owner_map),
            parent_entity_key=_map_key(entity.parent_entity_key, owner_map)
            if entity.parent_entity_key
            else None,
            owner=owner_map[entity.owner],
        )
        for entity in fixture.observation.entities
    )
    players = tuple(
        replace(
            player,
            player_index=owner_map[player.player_index],
            hand_visible=owner_map[player.player_index] == 1,
        )
        for player in fixture.observation.players
    )
    observation = replace(
        fixture.observation,
        battle_id=f"{fixture.observation.battle_id}-mirror",
        acting_player=1,
        first_player=(owner_map[fixture.observation.first_player]
                      if fixture.observation.first_player in owner_map else fixture.observation.first_player),
        players=tuple(sorted(players, key=lambda player: player.player_index)),
        entities=entities,
    )
    options: list[LegalOptionV1] = []
    for option in fixture.request.options:
        updated = replace(
            option,
            source_ref=_map_key(option.source_ref, owner_map) if option.source_ref else None,
            source_entity_key=_map_key(option.source_entity_key, owner_map) if option.source_entity_key else None,
            target_ref=_map_key(option.target_ref, owner_map) if option.target_ref else None,
            target_entity_key=_map_key(option.target_entity_key, owner_map) if option.target_entity_key else None,
        )
        options.append(replace(updated, semantic_fingerprint=stable_hash(updated.semantic_payload())))
    request = replace(
        fixture.request,
        episode_uuid=observation.battle_id,
        request_id=f"{fixture.request.request_id}-mirror",
        acting_player=1,
        options=tuple(options),
    )
    state = PublicStateV1.from_engine(observation, request)
    return B2FixtureBundleV1(
        config_path=fixture.config_path,
        observation=observation,
        request=request,
        state=state,
        receipt=fixture.receipt,
        semantic_targets={
            key: target.replace("p0:", "p1:") for key, target in fixture.semantic_targets.items()
        },
    )


def _decision(
    status: str,
    observation: EngineObservationV1 | None,
    request: SelectionRequestV1 | None,
    *,
    formulation_id: str,
    policy_id: str,
    reason: str | None = None,
    candidate_count: int = 0,
    chosen: ContinuityCandidateV1 | None = None,
    key: tuple[Any, ...] = (),
    candidates: Sequence[ContinuityCandidateV1] = (),
    authority: str = "B0_CONTROL_DELEGATION",
) -> ContinuityDecisionV1:
    request_id = request.request_id if isinstance(request, SelectionRequestV1) else "unsupported"
    sequence = request.selection_seq if isinstance(request, SelectionRequestV1) else (
        observation.transition_id if isinstance(observation, EngineObservationV1) else 0
    )
    acting = request.acting_player if isinstance(request, SelectionRequestV1) else (
        observation.acting_player if isinstance(observation, EngineObservationV1) else None
    )
    selected_key = chosen.semantic_key if chosen else ()
    return ContinuityDecisionV1(
        schema_version=B2_SCHEMA_VERSION,
        request_id=request_id,
        selection_seq=sequence,
        acting_player=acting,
        policy_id=policy_id,
        formulation_id=formulation_id,
        status=status,
        authority=authority if status == SELECTED else "B0_CONTROL_DELEGATION",
        chosen_target=chosen.target_key if chosen else None,
        chosen_semantic_action_key=selected_key,
        chosen_option_fingerprints=(chosen.option.semantic_fingerprint,) if chosen else (),
        decision_key=key,
        candidate_count=candidate_count,
        fail_closed_reason=reason,
        features_by_target=tuple((item.target_key, item.features) for item in candidates),
    )


class CurrentStateContinuityEvaluatorV1:
    """Pure public current-state B2-A/B evaluator.

    ``FIXTURE_ONLY`` receipts are accepted solely to exercise the arithmetic
    and boundary contract.  This class is not imported by the frozen B0
    PolicyV1 and cannot grant native route authority.
    """

    policy_id = "b2-current-public-continuity-fixture-v1"

    def __init__(self, receipt: CapabilityReceiptV1) -> None:
        if not isinstance(receipt, CapabilityReceiptV1):
            raise TypeError("B2 evaluator requires a CapabilityReceiptV1")
        self.receipt = receipt
        self._diagnostics = _MutableDiagnostics()
        self._last: dict[tuple[str, int, int, str], tuple[str, ContinuityDecisionV1]] = {}

    @property
    def diagnostics(self) -> ContinuityDiagnosticsV1:
        return self._diagnostics.snapshot()

    def reset(self, episode_uuid: str, player_index: int, reason: str = "start") -> None:
        if not isinstance(episode_uuid, str) or player_index not in (0, 1):
            raise ValueError("invalid B2 lifecycle identity")
        self._last = {
            key: value for key, value in self._last.items() if key[0] != episode_uuid or key[1] != player_index
        }

    def _reject(
        self,
        observation: EngineObservationV1 | None,
        request: SelectionRequestV1 | None,
        formulation_id: str,
        reason: str,
        *,
        status: str = B0_DELEGATE,
        candidate_count: int = 0,
        candidates: Sequence[ContinuityCandidateV1] = (),
    ) -> ContinuityDecisionV1:
        self._diagnostics.delegated += 1
        if reason.startswith("STALE"):
            self._diagnostics.stale_request_rejections += 1
        return _decision(
            status,
            observation,
            request,
            formulation_id=formulation_id,
            policy_id=self.policy_id,
            reason=reason,
            candidate_count=candidate_count,
            candidates=candidates,
        )

    def evaluate(
        self,
        observation: EngineObservationV1,
        request: SelectionRequestV1 | None,
        formulation_id: str = A_FORMULATION,
    ) -> ContinuityDecisionV1:
        self._diagnostics.requests += 1
        # Terminal is checked before request type, identity, or selection-local
        # fields.  A native terminal response may carry stale poison data.
        if isinstance(observation, EngineObservationV1) and observation.terminal_result is not None:
            try:
                PublicStateV1.from_engine(observation, request)
            except PublicStateError as error:
                return self._reject(observation, None, formulation_id, f"terminal public boundary: {error}")
            self._diagnostics.terminal_overrides += 1
            return _decision(
                TERMINAL_OVERRIDE,
                observation,
                None,
                formulation_id=formulation_id,
                policy_id=self.policy_id,
                reason="terminal checked first",
            )
        if formulation_id not in {A_FORMULATION, B_FORMULATION}:
            return self._reject(observation, request, formulation_id, "UNKNOWN_FORMULATION")
        if self.receipt.scope != FIXTURE_ONLY:
            return self._reject(observation, request, formulation_id, "NATIVE_CAPABILITY_SCOPE_NOT_AUTHORIZED")
        if self.receipt.receipt_id != _FIXTURE_METADATA_RECORD_ID:
            return self._reject(observation, request, formulation_id, "UNKNOWN_CAPABILITY_RECEIPT")
        if any(item.qualification_status == QUALIFIED_CABT_CAPSULE for item in self.receipt.capabilities):
            return self._reject(observation, request, formulation_id, "NATIVE_CAPABILITY_SCOPE_NOT_AUTHORIZED")
        if not isinstance(observation, EngineObservationV1) or not isinstance(request, SelectionRequestV1):
            return self._reject(observation, request, formulation_id, "CURRENT_OBSERVATION_AND_REQUEST_REQUIRED")
        try:
            PublicStateV1.from_engine(observation, request)
        except PublicStateError as error:
            self._diagnostics.boundary_rejections += 1
            return self._reject(observation, request, formulation_id, f"PUBLIC_BOUNDARY: {error}")
        request_key = (request.episode_uuid, request.acting_player, request.selection_seq, formulation_id)
        payload_digest = stable_hash(
            {
                "formulation": formulation_id,
                "observation": record_dict(observation),
                "request": record_dict(request),
            }
        )
        prior = self._last.get(request_key)
        if prior is not None:
            if prior[0] == payload_digest:
                return prior[1]
            return self._reject(observation, request, formulation_id, "STALE_OR_REUSED_REQUEST_IDENTITY")
        prior_sequences = [
            sequence for (episode, player, sequence, formulation) in self._last
            if episode == request.episode_uuid
            and player == request.acting_player
            and formulation == formulation_id
        ]
        if prior_sequences and request.selection_seq < max(prior_sequences):
            return self._reject(observation, request, formulation_id, "STALE_SELECTION_SEQUENCE")
        if request.selection_type != 0 or request.selection_context != 0:
            result = self._reject(observation, request, formulation_id, "UNSUPPORTED_REQUEST_CONTEXT")
            self._last[request_key] = (payload_digest, result)
            return result
        if request.ordering != "UNORDERED" or request.min_count != request.max_count:
            result = self._reject(observation, request, formulation_id, "COMPOUND_OR_ORDERED_REQUEST")
            self._last[request_key] = (payload_digest, result)
            return result
        if request.max_count != 1:
            result = self._reject(observation, request, formulation_id, "UNSUPPORTED_SELECTION_COUNT")
            self._last[request_key] = (payload_digest, result)
            return result
        if request.context_card_id is not None or request.effect_card_id is not None:
            result = self._reject(observation, request, formulation_id, "CONTEXT_EFFECT_CARD_NOT_CURRENT_ONLY")
            self._last[request_key] = (payload_digest, result)
            return result
        if request.remain_damage_counter is not None or request.remain_energy_cost is not None:
            result = self._reject(observation, request, formulation_id, "UNKNOWN_REQUEST_SCALAR")
            self._last[request_key] = (payload_digest, result)
            return result
        if any(option.option_type == 14 for option in request.options):
            result = self._reject(observation, request, formulation_id, "STOP_OPTION_ROW_FORBIDDEN")
            self._last[request_key] = (payload_digest, result)
            return result
        fingerprints = [option.semantic_fingerprint for option in request.options]
        if len(fingerprints) != len(set(fingerprints)):
            result = self._reject(observation, request, formulation_id, "DUPLICATE_SEMANTIC_FINGERPRINT")
            self._last[request_key] = (payload_digest, result)
            return result
        available = tuple(option for option in request.options if option.available)
        if not available or any(option.option_type != 8 for option in available):
            result = self._reject(observation, request, formulation_id, "COMPLETE_OPTION_SET_UNSUPPORTED")
            self._last[request_key] = (payload_digest, result)
            return result
        entity_map = _entity_map(observation)
        candidates: list[ContinuityCandidateV1] = []
        for option in available:
            candidate, reason = self._candidate(observation, request, option, entity_map)
            if candidate is None:
                result = self._reject(
                    observation, request, formulation_id, reason, candidate_count=len(candidates), candidates=candidates
                )
                self._last[request_key] = (payload_digest, result)
                return result
            candidates.append(candidate)
        selected_prefixes = {
            candidate.semantic_key: self._strategic_key(candidate.features, formulation_id)
            for candidate in candidates
        }
        best_prefix = max(selected_prefixes.values())
        top = [candidate for candidate in candidates if selected_prefixes[candidate.semantic_key] == best_prefix]
        if len(top) != 1:
            self._diagnostics.ambiguous += 1
            result = _decision(
                AMBIGUOUS,
                observation,
                request,
                formulation_id=formulation_id,
                policy_id=self.policy_id,
                reason="NON_EQUIVALENT_STRATEGIC_TIE",
                candidate_count=len(candidates),
                key=best_prefix,
                candidates=candidates,
            )
            self._diagnostics.delegated += 1
            self._last[request_key] = (payload_digest, result)
            return result
        selected = top[0]
        self._diagnostics.selected += 1
        result = _decision(
            SELECTED,
            observation,
            request,
            formulation_id=formulation_id,
            policy_id=self.policy_id,
            candidate_count=len(candidates),
            key=(*best_prefix, selected.option.semantic_fingerprint),
            chosen=selected,
            candidates=candidates,
            authority=EXPERIMENTAL_FIXTURE_AUTHORITY,
        )
        self._last[request_key] = (payload_digest, result)
        return result

    def _candidate(
        self,
        observation: EngineObservationV1,
        request: SelectionRequestV1,
        option: LegalOptionV1,
        entities: Mapping[str, Any],
    ) -> tuple[ContinuityCandidateV1 | None, str]:
        if option.option_type != 8 or option.choice_role != OPTION_NAMES[8]:
            return None, "UNSUPPORTED_OPTION_TYPE"
        if any(
            getattr(option, name) is not None
            for name in (
                "number", "player_index", "tool_index", "energy_index", "count",
                "attack_id", "card_id", "serial", "special_condition_type",
            )
        ):
            return None, "SUCCESSOR_VALUE_FORBIDDEN_OR_UNKNOWN_OPTION_FIELD"
        if option.source_kind != "ENTITY" or option.target_kind != "ENTITY":
            return None, "MISSING_LOCAL_DELTA_ENTITY_REFERENCES"
        source = entities.get(option.source_entity_key) if option.source_entity_key else None
        target = entities.get(option.target_entity_key) if option.target_entity_key else None
        actor = observation.acting_player
        if source is None or target is None:
            return None, "MISSING_PUBLIC_ENTITY"
        if (
            source.owner != actor
            or source.card_id != 3
            or source.zone != AREA["HAND"]
            or not source.visible
            or source.attached_energy_count != 0
            or source.energy_types != ()
            or option.source_ref != source.entity_key
            or option.source_entity_key != source.entity_key
            or option.area != AREA["HAND"]
            or option.index != source.position
        ):
            return None, "MISSING_LOCAL_DELTA_SOURCE"
        if (
            target.owner != actor
            or not target.visible
            or target.zone not in {AREA["ACTIVE"], AREA["BENCH"]}
            or option.target_ref != target.entity_key
            or option.target_entity_key != target.entity_key
            or option.in_play_area != target.zone
            or option.in_play_index != target.position
        ):
            return None, "MISSING_LOCAL_DELTA_TARGET"
        for entity in (source, target):
            if sum(
                candidate.owner == entity.owner
                and candidate.zone == entity.zone
                and candidate.position == entity.position
                for candidate in entities.values()
            ) != 1:
                return None, "AMBIGUOUS_PUBLIC_LOCATION"
        if observation.energy_attached is not False:
            return None, "ENERGY_ATTACHMENT_ALREADY_USED_OR_UNKNOWN"
        capabilities = self.receipt.for_card(target.card_id)
        if len(capabilities) != 1:
            return None, "UNKNOWN_CAPABILITY"
        capability = capabilities[0]
        if capability.qualification_status in {PARTIAL, UNKNOWN}:
            return None, f"PARTIAL_CAPABILITY_OR_EFFECT:{capability.qualification_id}"
        compatibility = self._fixture_capability_compatibility(target, capability)
        if compatibility is not None:
            return None, compatibility
        if capability.status_constraints and not set(target.statuses).issubset(set(capability.status_constraints)):
            return None, "UNKNOWN_STATUS_CONSTRAINT"
        if target.statuses is None or not isinstance(target.statuses, tuple):
            return None, "UNKNOWN_STATUS_CONSTRAINT"
        features, reason = self._features_after_attach(observation, target, capability)
        if features is None:
            return None, reason
        return ContinuityCandidateV1(
            option=option,
            target_key=target.entity_key,
            semantic_key=(option.semantic_fingerprint,),
            features=features,
        ), ""

    def _features_after_attach(
        self,
        observation: EngineObservationV1,
        target: Any,
        target_capability: AttackerCapabilityV1,
    ) -> tuple[ContinuityFeaturesV1 | None, str]:
        deficits: list[int] = []
        for entity in observation.entities:
            if entity.owner != observation.acting_player or entity.zone != AREA["BENCH"]:
                continue
            capabilities = self.receipt.for_card(entity.card_id)
            if len(capabilities) != 1:
                return None, "UNKNOWN_CAPABILITY"
            capability = capabilities[0]
            if capability.qualification_status in {PARTIAL, UNKNOWN}:
                return None, f"PARTIAL_CAPABILITY_OR_EFFECT:{capability.qualification_id}"
            compatibility = self._fixture_capability_compatibility(entity, capability)
            if compatibility is not None:
                return None, compatibility
            if capability.status_constraints and not set(entity.statuses).issubset(set(capability.status_constraints)):
                return None, "UNKNOWN_STATUS_CONSTRAINT"
            energy_types = entity.energy_types
            if entity.entity_key == target.entity_key:
                energy_types = energy_types + (3,)
            virtual = replace(entity, energy_types=energy_types, attached_energy_count=len(energy_types))
            deficit = _energy_deficit(virtual, capability)
            if deficit is None:
                return None, "UNKNOWN_ENERGY_MATCHING"
            deficits.append(deficit)
        if not deficits:
            return None, "UNKNOWN_NO_PUBLIC_CANDIDATE"
        ordered = sorted(deficits)
        ready = sum(value == 0 for value in ordered)
        features = ContinuityFeaturesV1(
            ready_after=ready,
            best_deficit_after=ordered[0],
            two_backup_tail_after=ordered[1] if len(ordered) >= 2 else None,
            backup_ready_count_after=ready,
            backup_near_ready_count_after=sum(value == 1 for value in ordered),
            next_attacker_ready_after=ready,
            non_active_target_role=int(target.zone == AREA["BENCH"]),
            unresolved_count=0,
        )
        if features.two_backup_tail_after is None:
            return None, "UNKNOWN_TWO_ATTACKER_TAIL"
        return features, ""

    @staticmethod
    def _fixture_capability_compatibility(
        entity: Any, capability: AttackerCapabilityV1
    ) -> str | None:
        """Reject forged fixture metadata instead of treating opaque prose as proof."""

        if capability.qualification_status != FIXTURE_ONLY:
            return "NATIVE_CAPABILITY_SCOPE_NOT_AUTHORIZED"
        expected_energy = _FIXTURE_ENERGY_SIGNATURES.get((capability.card_id, capability.attack_id))
        if (
            expected_energy is None
            or tuple(capability.energy_counts) != expected_energy
            or capability.qualification_id != f"fixture-only-{capability.card_id}-{capability.attack_id}"
            or capability.status_constraints != ()
        ):
            return "UNKNOWN_FIXTURE_CAPABILITY"
        expected_identity = _FIXTURE_EVOLUTION_REQUIREMENTS.get(capability.evolution_requirement)
        if expected_identity is None:
            return "UNKNOWN_EVOLUTION_REQUIREMENT"
        if (entity.card_id, entity.evolution_depth) != expected_identity:
            return "EVOLUTION_REQUIREMENT_MISMATCH"
        if capability.public_target_requirements != _FIXTURE_TARGET_REQUIREMENTS:
            return "UNKNOWN_PUBLIC_TARGET_REQUIREMENTS"
        return None

    @staticmethod
    def _strategic_key(features: ContinuityFeaturesV1, formulation_id: str) -> tuple[int, ...]:
        if formulation_id == A_FORMULATION:
            return (
                features.next_attacker_ready_after or 0,
                -(features.best_deficit_after or 0),
                features.backup_ready_count_after or 0,
                features.backup_near_ready_count_after or 0,
                features.non_active_target_role,
            )
        return (
            -int(features.two_backup_tail_after or 0),
            features.backup_ready_count_after or 0,
            -(features.best_deficit_after or 0),
            features.backup_near_ready_count_after or 0,
            features.next_attacker_ready_after or 0,
            features.non_active_target_role,
        )

    @staticmethod
    def build_optional_stop(request: SelectionRequestV1):
        """Build the explicit G1 STOP trace for a legal 0..1 request."""

        if request.min_count != 0 or request.max_count != 1:
            raise ContractViolation("B2 STOP requires a 0..1 singleton request")
        if any(option.available and option.option_type == 14 for option in request.options):
            raise ContractViolation("STOP is a decoder token, not a LegalOptionV1 row")
        builder = CompoundActionBuilder(request)
        builder.stop()
        return builder.build()


__all__ = [
    "A_FORMULATION", "AMBIGUOUS", "AttackerCapabilityV1", "B0_DELEGATE", "B_FORMULATION",
    "B2FixtureBundleV1", "B2_SCHEMA_VERSION", "CapabilityReceiptV1", "CurrentStateContinuityEvaluatorV1",
    "ContinuityDecisionV1", "ContinuityDiagnosticsV1", "ContinuityFeaturesV1", "FIXTURE_ONLY",
    "PARTIAL", "QUALIFIED_CABT_CAPSULE", "SELECTED", "TERMINAL_OVERRIDE", "load_b2_f01",
    "materialize_b2_fixture_data", "mirror_fixture", "semantic_permutation_suite",
]
