from __future__ import annotations

B6_SCHEMA_VERSION = 1

import hashlib
import json
from dataclasses import dataclass, fields, is_dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from ptcg_rl.deterministic.state import PublicStateV1
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


FIXTURE_ONLY = "FIXTURE_ONLY"
A_FORMULATION = "B6-A-ROUTE-DISTANCE-CONVERSION"
B_FORMULATION = "B6-B-THREAT-REMOVAL-COVERAGE-DOMINANCE"
SELECTED = "SELECTED"
B0_DELEGATE = "B0_DELEGATE"
AMBIGUOUS = "AMBIGUOUS"
UNSUPPORTED = "UNSUPPORTED"
TERMINAL_OVERRIDE = "TERMINAL_OVERRIDE"
COMPOUND_UNSUPPORTED = "COMPOUND_UNSUPPORTED"
MALFORMED_LOCAL_DELTAS = "MALFORMED_LOCAL_DELTAS"
UNKNOWN_CENSUS = "UNKNOWN_CENSUS"
UNKNOWN_CURRENT_RECEIPT = "UNKNOWN_CURRENT_RECEIPT"
RECEIPT_CONTENT_MISMATCH = "RECEIPT_CONTENT_MISMATCH"
RECEIPT_GRAPH_MISMATCH = "RECEIPT_GRAPH_MISMATCH"
PUBLIC_GRAPH_MISMATCH = "PUBLIC_GRAPH_MISMATCH"
HIDDEN_INFORMATION_FORBIDDEN = "HIDDEN_INFORMATION_FORBIDDEN"
SUCCESSOR_VALUE_FORBIDDEN = "SUCCESSOR_VALUE_FORBIDDEN"
CARD_PROSE_FORBIDDEN = "CARD_PROSE_FORBIDDEN"
NONFINITE_OR_INVALID_CURRENT_DELTA = "NONFINITE_OR_INVALID_CURRENT_DELTA"
STALE_SELECTION_SEQUENCE = "STALE_SELECTION_SEQUENCE"
DUPLICATE_CONTENT_MISMATCH = "DUPLICATE_CONTENT_MISMATCH"
STALE_OR_REUSED_REQUEST_IDENTITY = "STALE_OR_REUSED_REQUEST_IDENTITY"
ACTION_BUILD_FAILED = "ACTION_BUILD_FAILED"
NO_COVERED_ACTION = "NO_COVERED_ACTION"
NO_STRICT_COVERAGE_DOMINATOR = "NO_STRICT_COVERAGE_DOMINATOR"
STOP_UNRESOLVED = "STOP_UNRESOLVED"

_FIXTURE_RECORD_ID = "phase-b6-gust-route-fixture-v1"
_DEFAULT_CONFIG = Path("configs/deterministic/phase_b6_gust_route_fixture_v1.json")
_IMPLEMENTATION_PATH = Path("src/ptcg_rl/deterministic/b6_gust_route.py")
_DEPENDENCY_PATHS = (
    _IMPLEMENTATION_PATH,
    Path("src/ptcg_rl/g1/models.py"),
    Path("src/ptcg_rl/g1/actions.py"),
    Path("src/ptcg_rl/g1/semantic.py"),
    Path("src/ptcg_rl/deterministic/state.py"),
    Path("reports/deterministic/phase-b6-gust-route-design-v1.json"),
)

# Exact values from the bundled official CABT API.
_B6_SELECTION_TYPE = 1
_B6_SELECTION_CONTEXT = 4
_B6_OPTION_TYPE = 3
_BOSS_ORDERS_CARD_ID = 1182

_CURRENT_FIELD_ALLOWLIST = frozenset(
    {
        "route_distance_reduction",
        "target_prize_units",
        "target_ko_guaranteed",
        "gust_available_before",
        "gust_cost",
        "gust_reserve_after",
        "visible_threat_capability_ids",
        "selected_entity_identity",
        "selected_entity_hp",
        "selected_entity_energy",
        "local_legality",
    }
)


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def _canonical_value(value: Any) -> Any:
    if is_dataclass(value):
        return {field.name: _canonical_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _canonical_value(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (tuple, list, frozenset)):
        return [_canonical_value(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _sha_json(value: Any) -> str:
    payload = json.dumps(_canonical_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _digest(value: Any, name: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{name} must be a SHA-256 digest")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"{name} must be hexadecimal") from error
    if value.lower() != value:
        raise ValueError(f"{name} must be lowercase")
    return value


def _strict_nonnegative_int(value: Any, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative exact integer")
    return value


def _strict_bool(value: Any, name: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{name} must be a strict boolean")
    return value


def _tuple_strings(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        raise ValueError(f"{name} must be a sequence")
    result = tuple(value)
    if any(not isinstance(item, str) or not item for item in result):
        raise ValueError(f"{name} must contain nonempty strings")
    if len(set(result)) != len(result):
        raise ValueError(f"{name} must not contain duplicates")
    return result


def _content_payload(value: Any) -> Any:
    if is_dataclass(value):
        return {
            field.name: _content_payload(getattr(value, field.name))
            for field in fields(value)
            if field.name != "content_sha256"
        }
    if isinstance(value, Mapping):
        return {
            str(key): _content_payload(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) != "content_sha256"
        }
    if isinstance(value, (tuple, list, frozenset)):
        return [_content_payload(item) for item in value]
    return value


def _content_digest(value: Any) -> str:
    return _sha_json(_content_payload(value))


def _seal(value: Any) -> Any:
    return replace(value, content_sha256=_content_digest(value))

_HIDDEN_FIELD_MARKERS = ("hidden", "archetype")
_SUCCESSOR_FIELD_MARKERS = ("successor", "after_action", "future_", "post_action", "response_", "terminal_after")
_PROSE_FIELD_MARKERS = ("prose", "card_text", "static_damage", "description")


def _public_field_failure(current_fields: Sequence[str], successor_fields: Sequence[str]) -> str | None:
    for raw in (*successor_fields, *current_fields):
        if not isinstance(raw, str) or not raw:
            return UNKNOWN_CURRENT_RECEIPT
        lowered = raw.lower()
        if any(marker in lowered for marker in _HIDDEN_FIELD_MARKERS):
            return HIDDEN_INFORMATION_FORBIDDEN
        if any(marker in lowered for marker in _SUCCESSOR_FIELD_MARKERS):
            return SUCCESSOR_VALUE_FORBIDDEN
        if any(marker in lowered for marker in _PROSE_FIELD_MARKERS):
            return CARD_PROSE_FORBIDDEN
        if raw not in _CURRENT_FIELD_ALLOWLIST:
            return UNKNOWN_CURRENT_RECEIPT
    return None


@dataclass(frozen=True)
class GustRouteLocalDeltaV1:
    schema_version: int
    receipt_id: str
    fixture_case_id: str
    option_semantic_fingerprint: str
    option_semantic_payload_digest: str
    selection_type: int
    selection_context: int
    option_type: int
    action_key: str
    source_entity_key: str
    source_card_id: int
    source_serial: int
    source_owner: int
    source_zone: int
    source_position: int
    source_metadata_ref: str
    target_entity_key: str | None
    choice_role: str
    current_public_observation_digest: str
    action_eligible: bool
    gust_available_before: bool
    gust_cost: int
    gust_reserve_after: int
    route_distance_reduction: int
    target_prize_units: int
    target_ko_guaranteed: bool
    removed_capability_ids: tuple[str, ...]
    remaining_capability_ids: tuple[str, ...]
    current_public_fields: tuple[str, ...]
    successor_fields: tuple[str, ...]
    upstream_receipt_ids: tuple[str, ...]
    qualification_status: str
    content_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != B6_SCHEMA_VERSION:
            raise ValueError("unknown B6 local-delta schema")
        for name in (
            "receipt_id",
            "fixture_case_id",
            "option_semantic_fingerprint",
            "option_semantic_payload_digest",
            "action_key",
            "source_entity_key",
            "source_metadata_ref",
            "choice_role",
            "current_public_observation_digest",
        ):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise ValueError(f"B6 {name} must be a nonempty string")
        _digest(self.option_semantic_fingerprint, "option_semantic_fingerprint")
        _digest(self.option_semantic_payload_digest, "option_semantic_payload_digest")
        _digest(self.current_public_observation_digest, "current_public_observation_digest")
        for name in (
            "selection_type",
            "selection_context",
            "option_type",
            "source_card_id",
            "source_serial",
            "source_owner",
            "source_zone",
            "source_position",
            "gust_cost",
            "gust_reserve_after",
            "route_distance_reduction",
            "target_prize_units",
        ):
            _strict_nonnegative_int(getattr(self, name), name)
        _strict_bool(self.action_eligible, "action_eligible")
        _strict_bool(self.gust_available_before, "gust_available_before")
        _strict_bool(self.target_ko_guaranteed, "target_ko_guaranteed")
        object.__setattr__(
            self,
            "removed_capability_ids",
            _tuple_strings(self.removed_capability_ids, "removed_capability_ids"),
        )
        object.__setattr__(
            self,
            "remaining_capability_ids",
            _tuple_strings(self.remaining_capability_ids, "remaining_capability_ids"),
        )
        object.__setattr__(
            self,
            "current_public_fields",
            _tuple_strings(self.current_public_fields, "current_public_fields"),
        )
        object.__setattr__(
            self,
            "successor_fields",
            _tuple_strings(self.successor_fields, "successor_fields") if self.successor_fields else (),
        )
        object.__setattr__(
            self,
            "upstream_receipt_ids",
            _tuple_strings(self.upstream_receipt_ids, "upstream_receipt_ids"),
        )
        if set(self.removed_capability_ids) & set(self.remaining_capability_ids):
            raise ValueError("B6 capability cannot be both removed and remaining")
        if self.qualification_status != FIXTURE_ONLY:
            raise ValueError("B6 local delta is not fixture-only")
        _digest(self.content_sha256, "content_sha256")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "GustRouteLocalDeltaV1":
        required = {field.name for field in fields(cls)}
        if not isinstance(value, Mapping) or set(value) != required:
            raise ValueError("B6 local-delta fields are incomplete or unknown")
        payload = dict(value)
        for key in (
            "removed_capability_ids",
            "remaining_capability_ids",
            "current_public_fields",
            "successor_fields",
            "upstream_receipt_ids",
        ):
            payload[key] = tuple(payload[key])
        return cls(**payload)


@dataclass(frozen=True)
class VisibleThreatCapabilityCensusV1:
    schema_version: int
    census_id: str
    fixture_case_id: str
    public_snapshot_digest: str
    visible_source_entity_keys: tuple[str, ...]
    capability_ids: tuple[str, ...]
    census_complete: bool
    zero_threat_justification: str | None
    qualification_status: str
    content_sha256: str

    def __post_init__(self) -> None:
        if self.schema_version != B6_SCHEMA_VERSION:
            raise ValueError("unknown B6 census schema")
        for name in ("census_id", "fixture_case_id", "public_snapshot_digest"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise ValueError(f"B6 {name} must be nonempty")
        _digest(self.public_snapshot_digest, "public_snapshot_digest")
        object.__setattr__(
            self,
            "visible_source_entity_keys",
            _tuple_strings(self.visible_source_entity_keys, "visible_source_entity_keys"),
        )
        object.__setattr__(
            self,
            "capability_ids",
            _tuple_strings(self.capability_ids, "capability_ids") if self.capability_ids else (),
        )
        _strict_bool(self.census_complete, "census_complete")
        if self.capability_ids:
            if self.zero_threat_justification is not None:
                raise ValueError("nonempty B6 census must not claim zero-threat justification")
        elif self.census_complete and self.zero_threat_justification != "EXPLICIT_COMPLETE_ZERO_VISIBLE_THREAT":
            raise ValueError("complete empty B6 census requires explicit zero-threat proof")
        elif not self.census_complete and self.zero_threat_justification is not None:
            raise ValueError("incomplete B6 census cannot claim zero-threat proof")
        if self.qualification_status != FIXTURE_ONLY:
            raise ValueError("B6 census is not fixture-only")
        _digest(self.content_sha256, "content_sha256")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "VisibleThreatCapabilityCensusV1":
        required = {field.name for field in fields(cls)}
        if not isinstance(value, Mapping) or set(value) != required:
            raise ValueError("B6 census fields are incomplete or unknown")
        payload = dict(value)
        payload["visible_source_entity_keys"] = tuple(payload["visible_source_entity_keys"])
        payload["capability_ids"] = tuple(payload["capability_ids"])
        return cls(**payload)


@dataclass(frozen=True)
class GustCandidateV1:
    option: LegalOptionV1
    delta: GustRouteLocalDeltaV1


@dataclass(frozen=True)
class GustDecisionV1:
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
    action: CompoundActionV1 | None = None
    stopped_early: bool = False
    fallback_used: bool = False
    successor_reads: int = 0

    def __post_init__(self) -> None:
        if self.schema_version != B6_SCHEMA_VERSION:
            raise ValueError("unknown B6 decision schema")
        if self.status not in {SELECTED, B0_DELEGATE, AMBIGUOUS, UNSUPPORTED, TERMINAL_OVERRIDE}:
            raise ValueError("unknown B6 decision status")
        if self.successor_reads != 0 or self.fallback_used:
            raise ValueError("B6 fixture boundary was crossed")


@dataclass(frozen=True)
class B6FixtureCaseV1:
    case_id: str
    observation: EngineObservationV1
    request: SelectionRequestV1
    state: PublicStateV1
    local_deltas: Mapping[str, GustRouteLocalDeltaV1]
    census: VisibleThreatCapabilityCensusV1
    expected: Mapping[str, str]

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, str) or not self.case_id:
            raise ValueError("B6 case_id must be nonempty")
        if not isinstance(self.observation, EngineObservationV1):
            raise TypeError("B6 observation is invalid")
        if not isinstance(self.request, SelectionRequestV1) or not isinstance(self.state, PublicStateV1):
            raise TypeError("B6 request/state authority is invalid")
        if not isinstance(self.census, VisibleThreatCapabilityCensusV1):
            raise TypeError("B6 fixture case census is invalid")
        object.__setattr__(self, "local_deltas", MappingProxyType(dict(self.local_deltas)))
        object.__setattr__(self, "expected", MappingProxyType(dict(self.expected)))


@dataclass(frozen=True)
class B6FixtureBundleV1:
    config_path: Path
    cases: tuple[B6FixtureCaseV1, ...]


def _decision(
    state: PublicStateV1,
    formulation: str,
    status: str,
    *,
    chosen: GustCandidateV1 | None = None,
    action: CompoundActionV1 | None = None,
    key: tuple[Any, ...] = (),
    candidate_count: int = 0,
    reason: str | None = None,
    stopped_early: bool = False,
) -> GustDecisionV1:
    request = state.request
    return GustDecisionV1(
        schema_version=B6_SCHEMA_VERSION,
        request_id=request.request_id if request is not None else "TERMINAL",
        selection_seq=request.selection_seq if request is not None else -1,
        acting_player=state.acting_player,
        policy_id=CurrentGustRouteEvaluatorV1.policy_id,
        formulation_id=formulation,
        status=status,
        authority="B6_FIXTURE_ONLY" if status in {SELECTED, TERMINAL_OVERRIDE} else "B0_CONTROL_DELEGATION",
        chosen_action_key=(chosen.delta.action_key,) if chosen is not None else (("STOP",) if stopped_early else ()),
        chosen_semantic_action_key=chosen.option.semantic_fingerprint if chosen is not None else None,
        chosen_option_fingerprints=(chosen.option.semantic_fingerprint,) if chosen is not None else (),
        chosen_original_indices=(chosen.option.original_index,) if chosen is not None else (),
        decision_key=key,
        candidate_count=candidate_count,
        fail_closed_reason=reason,
        action=action,
        stopped_early=stopped_early,
    )


def _delegate(
    state: PublicStateV1,
    formulation: str,
    reason: str,
    *,
    candidate_count: int = 0,
) -> GustDecisionV1:
    status = AMBIGUOUS if reason == AMBIGUOUS else B0_DELEGATE
    return _decision(state, formulation, status, reason=reason, candidate_count=candidate_count)


def _entity(owner: int, serial: int, card_id: int, zone: int, position: int, hp: int) -> VisibleEntityV1:
    marker = "f" * 64
    return VisibleEntityV1(
        entity_key=f"p{owner}:s{serial}",
        card_id=card_id,
        serial=serial,
        metadata_ref=f"card:{card_id}@{marker}",
        owner=owner,
        zone=zone,
        position=position,
        hp=hp,
        max_hp=hp,
        damage=0,
        appear_this_turn=False,
        energy_types=(),
        attached_energy_count=0,
        attached_tool_count=0,
        evolution_depth=0,
        statuses=(),
        visible=True,
    )


def _fixture_observation(
    case_id: str,
    *,
    actor: int = 0,
    terminal: int | None = None,
) -> EngineObservationV1:
    opponent = 1 - actor
    entities = (
        _entity(actor, 10, 700, AREA["ACTIVE"], 0, 220),
        _entity(opponent, 50, 900, AREA["ACTIVE"], 0, 250),
        _entity(opponent, 51, 901, AREA["BENCH"], 0, 180),
        _entity(opponent, 52, 902, AREA["BENCH"], 1, 320),
    )
    players = (
        PlayerViewV1(0, 5, 20, 4, 4, 0, actor == 0, 0),
        PlayerViewV1(1, 5, 20, 4, 4, 0, actor == 1, 0),
    )
    return EngineObservationV1(
        schema_version=CONTRACT_VERSION,
        battle_id=case_id,
        transition_id=7,
        acting_player=actor,
        terminal_result=terminal,
        turn=4,
        turn_action_count=2,
        first_player=0,
        supporter_played=True,
        stadium_played=False,
        energy_attached=True,
        retreated=False,
        players=players,
        entities=entities,
        public_events=(),
    )


def _gust_option(index: int, entity: VisibleEntityV1) -> LegalOptionV1:
    option = LegalOptionV1(
        schema_version=CONTRACT_VERSION,
        original_index=index,
        selection_type=_B6_SELECTION_TYPE,
        selection_context=_B6_SELECTION_CONTEXT,
        option_type=_B6_OPTION_TYPE,
        option_name=OPTION_NAMES[_B6_OPTION_TYPE],
        area=AREA["BENCH"],
        index=entity.position,
        player_index=entity.owner,
        source_kind="ENTITY",
        source_ref=entity.entity_key,
        target_kind="NONE",
        target_ref=None,
        choice_role=OPTION_NAMES[_B6_OPTION_TYPE],
        source_entity_key=entity.entity_key,
        target_entity_key=None,
        available=True,
        semantic_fingerprint="",
    )
    return replace(option, semantic_fingerprint=stable_hash(option.semantic_payload()))


def _fixture_request(
    case_id: str,
    options: Sequence[LegalOptionV1],
    *,
    actor: int = 0,
    min_count: int = 1,
    max_count: int = 1,
) -> SelectionRequestV1:
    return SelectionRequestV1(
        schema_version=CONTRACT_VERSION,
        episode_uuid=case_id,
        selection_seq=7,
        request_id=f"{case_id}-r7",
        acting_player=actor,
        selection_type=_B6_SELECTION_TYPE,
        selection_context=_B6_SELECTION_CONTEXT,
        min_count=min_count,
        max_count=max_count,
        remain_damage_counter=None,
        remain_energy_cost=None,
        context_card_id=None,
        effect_card_id=_BOSS_ORDERS_CARD_ID,
        ordering="UNORDERED",
        options=tuple(options),
    )


def _fixture_delta(
    case_id: str,
    option: LegalOptionV1,
    entity: VisibleEntityV1,
    observation_digest: str,
    *,
    action_key: str,
    route: int,
    prize: int,
    ko: bool,
    cost: int,
    reserve: int,
    removed: Sequence[str],
    remaining: Sequence[str],
    eligible: bool = True,
    current_fields: Sequence[str] | None = None,
) -> GustRouteLocalDeltaV1:
    marker = "f" * 64
    delta = GustRouteLocalDeltaV1(
        schema_version=B6_SCHEMA_VERSION,
        receipt_id=f"b6:{case_id}:{action_key}:delta",
        fixture_case_id=case_id,
        option_semantic_fingerprint=option.semantic_fingerprint,
        option_semantic_payload_digest=stable_hash(option.semantic_payload()),
        selection_type=option.selection_type,
        selection_context=option.selection_context,
        option_type=option.option_type,
        action_key=action_key,
        source_entity_key=entity.entity_key,
        source_card_id=entity.card_id,
        source_serial=entity.serial,
        source_owner=entity.owner,
        source_zone=entity.zone,
        source_position=entity.position,
        source_metadata_ref=entity.metadata_ref,
        target_entity_key=None,
        choice_role=option.choice_role,
        current_public_observation_digest=observation_digest,
        action_eligible=eligible,
        gust_available_before=True,
        gust_cost=cost,
        gust_reserve_after=reserve,
        route_distance_reduction=route,
        target_prize_units=prize,
        target_ko_guaranteed=ko,
        removed_capability_ids=tuple(removed),
        remaining_capability_ids=tuple(remaining),
        current_public_fields=tuple(
            current_fields
            or (
                "route_distance_reduction",
                "target_prize_units",
                "target_ko_guaranteed",
                "gust_available_before",
                "gust_cost",
                "gust_reserve_after",
                "visible_threat_capability_ids",
                "selected_entity_identity",
                "local_legality",
            )
        ),
        successor_fields=(),
        upstream_receipt_ids=(
            f"b1:{case_id}:{action_key}:route",
            f"b3:{case_id}:{action_key}:gust",
            f"b4:{case_id}:{action_key}:threat",
        ),
        qualification_status=FIXTURE_ONLY,
        content_sha256=marker,
    )
    return _seal(delta)


def _fixture_census(
    case_id: str,
    observation: EngineObservationV1,
    capability_ids: Sequence[str],
    *,
    complete: bool = True,
) -> VisibleThreatCapabilityCensusV1:
    opponent = 1 - observation.acting_player
    sources = tuple(
        entity.entity_key
        for entity in observation.entities
        if entity.owner == opponent and entity.zone in {AREA["ACTIVE"], AREA["BENCH"]}
    )
    census = VisibleThreatCapabilityCensusV1(
        schema_version=B6_SCHEMA_VERSION,
        census_id=f"b6:{case_id}:census",
        fixture_case_id=case_id,
        public_snapshot_digest=stable_hash(observation),
        visible_source_entity_keys=sources,
        capability_ids=tuple(capability_ids),
        census_complete=complete,
        zero_threat_justification="EXPLICIT_COMPLETE_ZERO_VISIBLE_THREAT" if complete and not capability_ids else None,
        qualification_status=FIXTURE_ONLY,
        content_sha256="f" * 64,
    )
    return _seal(census)


def _make_case(
    case_id: str,
    descriptors: Sequence[Mapping[str, Any]],
    *,
    expected_a: str = SELECTED,
    expected_b: str = SELECTED,
    terminal: int | None = None,
    census_complete: bool = True,
    min_count: int = 1,
    max_count: int = 1,
) -> B6FixtureCaseV1:
    observation = _fixture_observation(case_id, terminal=terminal)
    opponent_entities = [
        entity
        for entity in observation.entities
        if entity.owner == 1 and entity.zone == AREA["BENCH"]
    ]
    options = tuple(_gust_option(index, opponent_entities[index]) for index in range(len(descriptors)))
    request = _fixture_request(case_id, options, min_count=min_count, max_count=max_count)
    state = PublicStateV1.from_engine(observation, request)
    observation_digest = stable_hash(observation)
    deltas: dict[str, GustRouteLocalDeltaV1] = {}
    capabilities: set[str] = set()
    for index, descriptor in enumerate(descriptors):
        removed = tuple(descriptor.get("removed", ()))
        remaining = tuple(descriptor.get("remaining", ()))
        capabilities.update(removed)
        capabilities.update(remaining)
        option = options[index]
        entity = opponent_entities[index]
        delta = _fixture_delta(
            case_id,
            option,
            entity,
            observation_digest,
            action_key=str(descriptor["action_key"]),
            route=int(descriptor.get("route", 0)),
            prize=int(descriptor.get("prize", 1)),
            ko=bool(descriptor.get("ko", True)),
            cost=int(descriptor.get("cost", 1)),
            reserve=int(descriptor.get("reserve", 1)),
            removed=removed,
            remaining=remaining,
            eligible=bool(descriptor.get("eligible", True)),
            current_fields=descriptor.get("current_fields"),
        )
        deltas[option.semantic_fingerprint] = delta
    census = _fixture_census(case_id, observation, sorted(capabilities), complete=census_complete)
    return B6FixtureCaseV1(
        case_id=case_id,
        observation=observation,
        request=request,
        state=state,
        local_deltas=MappingProxyType(deltas),
        census=census,
        expected=MappingProxyType({A_FORMULATION: expected_a, B_FORMULATION: expected_b}),
    )


def _build_cases() -> tuple[B6FixtureCaseV1, ...]:
    divergence = (
        {
            "action_key": "B6-F02-X",
            "route": 2,
            "prize": 2,
            "removed": ("threat-1",),
            "remaining": ("threat-2",),
        },
        {
            "action_key": "B6-F02-Y",
            "route": 1,
            "prize": 1,
            "removed": ("threat-1", "threat-2"),
            "remaining": (),
        },
    )
    control = (
        {
            "action_key": "B6-F03-X",
            "route": 2,
            "prize": 2,
            "removed": ("threat-1", "threat-2"),
            "remaining": (),
        },
        {
            "action_key": "B6-F03-Y",
            "route": 1,
            "prize": 1,
            "removed": ("threat-1",),
            "remaining": ("threat-2",),
        },
    )
    simple = (
        {
            "action_key": "B6-SIMPLE-X",
            "route": 1,
            "prize": 1,
            "removed": ("threat-1",),
            "remaining": (),
        },
    )
    return (
        _make_case(
            "B6-F01-TERMINAL-FIRST",
            simple,
            terminal=1,
            expected_a=TERMINAL_OVERRIDE,
            expected_b=TERMINAL_OVERRIDE,
        ),
        _make_case("B6-F02-REAL-FORMULATION-DIVERGENCE", divergence),
        _make_case("B6-F03-CONTROL-SAME-ROUTE-WINNER", control),
        _make_case(
            "B6-F04-NO-THREAT-CENSUS-CONTROL",
            simple,
            census_complete=False,
            expected_a=B0_DELEGATE,
            expected_b=B0_DELEGATE,
        ),
        _make_case(
            "B6-F05-UNKNOWN-PARTIAL-PROSE-HIDDEN",
            ({**simple[0], "current_fields": ("hidden_identity",)},),
            expected_a=B0_DELEGATE,
            expected_b=B0_DELEGATE,
        ),
        _make_case("B6-F06-OPTION-TARGET-ENTITY-MATRIX", simple),
        _make_case("B6-F07-PERMUTATION-AND-MIRROR", divergence),
        _make_case(
            "B6-F08-STOP-COMPOUND",
            ({**simple[0], "eligible": False},),
            min_count=0,
            max_count=1,
        ),
        _make_case("B6-F09-LIFECYCLE-AND-EARLY-DELEGATION", simple),
        _make_case("B6-F10-NUMERIC-ENUM-SCALE", simple),
        _make_case("B6-F11-CROSS-PHASE-OVERLAP", simple),
        _make_case("B6-F12-FRESH-PROCESS-MATRIX", divergence),
    )


def _case_record(case: B6FixtureCaseV1) -> Mapping[str, Any]:
    return {
        "case_id": case.case_id,
        "observation": _canonical_value(case.observation),
        "request": _canonical_value(case.request),
        "state": _canonical_value(case.state),
        "local_deltas": _canonical_value(dict(case.local_deltas)),
        "census": _canonical_value(case.census),
        "expected": _canonical_value(dict(case.expected)),
    }


def _dependency_manifest(root: Path | None = None) -> Mapping[str, str]:
    base = root or _root()
    result: dict[str, str] = {}
    for relative in _DEPENDENCY_PATHS:
        path = base / relative
        if not path.is_file():
            raise ValueError(f"B6 dependency is missing: {relative}")
        result[str(relative)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _knowledge_base_digest(root: Path | None = None) -> str:
    path = (root or _root()) / "knowledge_base" / "ptcg_gold.sqlite"
    if not path.is_file():
        raise ValueError("B6 knowledge base is missing")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _config_digest(value: Mapping[str, Any]) -> str:
    payload = _canonical_value(value)
    payload["config_payload_sha256"] = ""
    return _sha_json(payload)


def build_b6_fixture_config(path: Path | None = None) -> Path:
    cases = _build_cases()
    output = path or (_root() / _DEFAULT_CONFIG)
    records = [_case_record(case) for case in cases]
    payload: dict[str, Any] = {
        "schema_version": B6_SCHEMA_VERSION,
        "record_id": _FIXTURE_RECORD_ID,
        "scope": FIXTURE_ONLY,
        "fixture_metadata_sha256": _sha_json(records),
        "dependency_manifest": dict(_dependency_manifest()),
        "knowledge_base_sha256": _knowledge_base_digest(),
        "fixture_cases": [
            {"id": case.case_id, "expected": dict(case.expected)}
            for case in cases
        ],
        "fixture_records": records,
        "config_payload_sha256": "",
    }
    payload["config_payload_sha256"] = _config_digest(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def _case_from_record(
    value: Mapping[str, Any],
    expected: Mapping[str, str],
) -> B6FixtureCaseV1:
    required = {
        "case_id",
        "observation",
        "request",
        "state",
        "local_deltas",
        "census",
        "expected",
    }
    if not isinstance(value, Mapping) or set(value) != required:
        raise ValueError("B6 fixture record fields are incomplete or unknown")
    case_id = value["case_id"]
    if not isinstance(case_id, str) or not case_id:
        raise ValueError("B6 fixture record case_id is malformed")
    observation = EngineObservationV1.from_dict(value["observation"])
    request = SelectionRequestV1.from_dict(value["request"])
    state = PublicStateV1.from_engine(observation, request)
    if _canonical_value(state) != value["state"]:
        raise ValueError("B6 fixture state is not exactly derived from observation/request")
    raw_deltas = value["local_deltas"]
    if not isinstance(raw_deltas, Mapping):
        raise ValueError("B6 local_deltas must be a mapping")
    deltas = {
        str(key): GustRouteLocalDeltaV1.from_dict(item)
        for key, item in raw_deltas.items()
    }
    census = VisibleThreatCapabilityCensusV1.from_dict(value["census"])
    if census.fixture_case_id != case_id:
        raise ValueError("B6 census case identity is stale")
    if value["expected"] != dict(expected):
        raise ValueError("B6 expected outcomes differ from declaration")
    return B6FixtureCaseV1(
        case_id,
        observation,
        request,
        state,
        MappingProxyType(deltas),
        census,
        MappingProxyType(dict(expected)),
    )


def load_b6_fixtures(path: Path | None = None) -> B6FixtureBundleV1:
    config_path = path or (_root() / _DEFAULT_CONFIG)
    value = json.loads(config_path.read_text(encoding="utf-8"))
    allowed = {
        "schema_version",
        "record_id",
        "scope",
        "fixture_metadata_sha256",
        "dependency_manifest",
        "knowledge_base_sha256",
        "fixture_cases",
        "fixture_records",
        "config_payload_sha256",
    }
    if not isinstance(value, Mapping) or set(value) != allowed:
        raise ValueError("B6 fixture top-level fields are incomplete or unknown")
    if (
        value["schema_version"] != B6_SCHEMA_VERSION
        or value["record_id"] != _FIXTURE_RECORD_ID
        or value["scope"] != FIXTURE_ONLY
    ):
        raise ValueError("unknown B6 fixture metadata")
    if value["dependency_manifest"] != _dependency_manifest():
        raise ValueError("B6 dependency manifest does not match loaded source/contracts")
    if value["knowledge_base_sha256"] != _knowledge_base_digest():
        raise ValueError("B6 knowledge-base digest is stale")
    if value["config_payload_sha256"] != _config_digest(value):
        raise ValueError("B6 config payload digest is stale")
    declarations = value["fixture_cases"]
    records = value["fixture_records"]
    if (
        not isinstance(declarations, list)
        or not isinstance(records, list)
        or len(declarations) != len(records)
    ):
        raise ValueError("B6 fixture declarations/records are malformed")
    if value["fixture_metadata_sha256"] != _sha_json(records):
        raise ValueError("B6 fixture metadata digest is stale")
    expected_by_id: dict[str, Mapping[str, str]] = {}
    for declaration in declarations:
        if not isinstance(declaration, Mapping) or set(declaration) != {"id", "expected"}:
            raise ValueError("B6 fixture declaration is malformed")
        case_id = declaration["id"]
        expected = declaration["expected"]
        if (
            not isinstance(case_id, str)
            or case_id in expected_by_id
            or not isinstance(expected, Mapping)
            or set(expected) != {A_FORMULATION, B_FORMULATION}
        ):
            raise ValueError("B6 fixture declaration is duplicated or incomplete")
        if any(
            status not in {SELECTED, B0_DELEGATE, TERMINAL_OVERRIDE, AMBIGUOUS}
            for status in expected.values()
        ):
            raise ValueError("B6 expected status is unknown")
        expected_by_id[case_id] = dict(expected)
    cases = tuple(
        _case_from_record(record, expected_by_id[record["case_id"]])
        for record in records
    )
    if {case.case_id for case in cases} != set(expected_by_id):
        raise ValueError("B6 fixture record graph does not match declarations")
    for case in cases:
        for fingerprint, delta in case.local_deltas.items():
            if (
                fingerprint != delta.option_semantic_fingerprint
                or delta.content_sha256 != _content_digest(delta)
            ):
                raise ValueError("B6 nested local-delta content seal is stale")
        if case.census.content_sha256 != _content_digest(case.census):
            raise ValueError("B6 census content seal is stale")
    return B6FixtureBundleV1(config_path, cases)


def _map_entity_key(value: str | None, owner_map: Mapping[int, int]) -> str | None:
    if value is None or not value.startswith("p") or ":" not in value:
        return value
    head, tail = value.split(":", 1)
    try:
        owner = int(head[1:])
    except ValueError:
        return value
    return f"p{owner_map.get(owner, owner)}:{tail}"


def mirror_b6_case(case: B6FixtureCaseV1) -> B6FixtureCaseV1:
    owner_map = {0: 1, 1: 0}
    new_id = f"{case.case_id}-MIRROR"
    entities = tuple(
        replace(
            entity,
            entity_key=_map_entity_key(entity.entity_key, owner_map) or entity.entity_key,
            owner=owner_map[entity.owner],
        )
        for entity in case.observation.entities
    )
    players = tuple(
        sorted(
            (
                replace(
                    player,
                    player_index=owner_map[player.player_index],
                    hand_visible=owner_map[player.player_index] == 1,
                )
                for player in case.observation.players
            ),
            key=lambda player: player.player_index,
        )
    )
    observation = replace(
        case.observation,
        battle_id=new_id,
        acting_player=owner_map[case.observation.acting_player],
        players=players,
        entities=entities,
    )
    options: list[LegalOptionV1] = []
    old_to_new: dict[str, LegalOptionV1] = {}
    for option in case.request.options:
        mirrored = replace(
            option,
            player_index=(
                owner_map.get(option.player_index, option.player_index)
                if option.player_index is not None
                else None
            ),
            source_ref=_map_entity_key(option.source_ref, owner_map),
            source_entity_key=_map_entity_key(option.source_entity_key, owner_map),
            target_ref=_map_entity_key(option.target_ref, owner_map),
            target_entity_key=_map_entity_key(option.target_entity_key, owner_map),
        )
        mirrored = replace(
            mirrored,
            semantic_fingerprint=stable_hash(mirrored.semantic_payload()),
        )
        options.append(mirrored)
        old_to_new[option.semantic_fingerprint] = mirrored
    request = replace(
        case.request,
        episode_uuid=new_id,
        request_id=f"{case.request.request_id}-mirror",
        acting_player=owner_map[case.request.acting_player],
        options=tuple(options),
    )
    observation_digest = stable_hash(observation)
    deltas: dict[str, GustRouteLocalDeltaV1] = {}
    for old_fingerprint, delta in case.local_deltas.items():
        option = old_to_new[old_fingerprint]
        entity = next(item for item in entities if item.entity_key == option.source_entity_key)
        mirrored = replace(
            delta,
            receipt_id=f"{delta.receipt_id}-mirror",
            fixture_case_id=new_id,
            option_semantic_fingerprint=option.semantic_fingerprint,
            option_semantic_payload_digest=stable_hash(option.semantic_payload()),
            source_entity_key=entity.entity_key,
            source_owner=entity.owner,
            source_zone=entity.zone,
            source_position=entity.position,
            source_metadata_ref=entity.metadata_ref,
            current_public_observation_digest=observation_digest,
            upstream_receipt_ids=tuple(
                f"{receipt}-mirror" for receipt in delta.upstream_receipt_ids
            ),
        )
        deltas[option.semantic_fingerprint] = _seal(mirrored)
    census = _seal(
        replace(
            case.census,
            census_id=f"{case.census.census_id}-mirror",
            fixture_case_id=new_id,
            public_snapshot_digest=observation_digest,
            visible_source_entity_keys=tuple(
                _map_entity_key(key, owner_map) or key
                for key in case.census.visible_source_entity_keys
            ),
        )
    )
    state = PublicStateV1.from_engine(observation, request)
    return B6FixtureCaseV1(
        new_id,
        observation,
        request,
        state,
        MappingProxyType(deltas),
        census,
        case.expected,
    )
