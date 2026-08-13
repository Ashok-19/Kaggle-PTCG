"""Restricted native-qualified Phase B1 policy adapters.

The adapters in this module are deliberately thinner than the frozen B0
controller.  They never infer an effect, use option order, inspect a future
state, or turn a route abstention into a final-adapter fallback.  A route
decision is used only after the versioned native receipt covers every
available current option; every other status is an explicit B0 delegation.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ptcg_rl.g1.actions import CompoundActionBuilder
from ptcg_rl.g1.models import (
    ContractViolation,
    CompoundActionV1,
    EngineObservationV1,
    LegalOptionV1,
    SelectionRequestV1,
    stable_hash,
)
from ptcg_rl.g1.semantic import AREA

from .b1_oracle import (
    A_FORMULATION,
    AMBIGUOUS,
    B0_DELEGATE,
    B_FORMULATION,
    CapabilityReceiptV1,
    CurrentStateRouteOracleV1,
    NO_SAFE_ROUTE,
    RUNTIME_NATIVE,
    RouteDecisionV1,
    SELECTED,
    TERMINAL_OVERRIDE,
    UNKNOWN,
    UNSUPPORTED,
)
from .policy import DeterministicStrategicPolicy
from .state import PublicStateError, PublicStateV1


RECEIPT_PATH = "configs/deterministic/phase_b1_native_route_receipt_v2.json"
_ROUTE_ABSTENTIONS = frozenset({B0_DELEGATE, UNKNOWN, UNSUPPORTED, AMBIGUOUS, NO_SAFE_ROUTE})
_STOP_TYPES = frozenset({14})
_QUALIFIED_ATTACKS = frozenset({1044, 1045})
_SOURCE_CARD = 722
_TARGET_CARD = 723
_EVOLVE_TYPE = 9
_EVOLVE_SELECT_TYPE = 7
_EVOLVE_CONTEXT = 37
_ATTACK_SELECT_TYPE = 6
_ATTACK_CONTEXT = 35
_EXPECTED_SCOPE_LABELS = {
    "capability": "NATIVE_QUALIFIED_CANDIDATE",
    "policy_integration": "NOT_ESTABLISHED",
    "outcome_promotion": "NOT_ESTABLISHED",
}
_EXPECTED_ASSET_SCOPES = {
    "native_library": "OFFICIAL_ENGINE",
    "api": "OFFICIAL_API",
    "wrapper": "OFFICIAL_WRAPPER",
    "card_data": "OFFICIAL_CARD_DATA",
    "card_table": "VERSIONED_CARD_TABLE",
    "candidate_deck": "EXACT_PRODUCTION_DECK",
    "knowledge_base": "LOCAL_KNOWLEDGE_BASE",
}
_EXPECTED_SOURCE_SCOPES = {
    "src/ptcg_rl/g1/actions.py": "FROZEN_CONTRACT_DEPENDENCY",
    "src/ptcg_rl/g1/models.py": "FROZEN_CONTRACT_DEPENDENCY",
    "src/ptcg_rl/g1/semantic.py": "FROZEN_CONTRACT_DEPENDENCY",
    "src/ptcg_rl/deterministic/b1_oracle.py": "B1_ORACLE_DEPENDENCY",
    "src/ptcg_rl/deterministic/control.py": "FROZEN_B0_CONTROL",
    "src/ptcg_rl/deterministic/policy.py": "FROZEN_B0_POLICY_ENTRY",
    "src/ptcg_rl/deterministic/b1_policy.py": "B1_OWNED_RUNTIME",
    "src/ptcg_rl/deterministic/b1_component_harness.py": "B1_OWNED_HARNESS",
    "scripts/deterministic/phase_b1_component_qualification.py": "B1_OWNED_PLANNER",
    "scripts/deterministic/phase_b1_exact_deck_capability_rerun.py": "B1_OWNED_CAPABILITY_PLAN",
}
_EXPECTED_CAPABILITY_EVIDENCE_KEYS = {
    "scope",
    "status",
    "config_path",
    "config_sha256",
    "report_path",
    "report_sha256",
    "raw_path",
    "raw_sha256",
}


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def runtime_receipt_binding_sha256(payload: Mapping[str, Any]) -> str:
    """Hash the route receipt content without its cross-file binding fields.

    The component plan binds this digest, while the receipt binds the plan's
    file digest.  Excluding both binding fields (and their derived digests)
    makes the relationship acyclic without weakening the parsed-content and
    exact-plan checks performed by the validators.
    """
    if not isinstance(payload, Mapping):
        raise ValueError("B1 runtime receipt binding payload must be a mapping")
    canonical_payload = json.loads(json.dumps(payload))
    provenance = canonical_payload.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("B1 runtime receipt binding provenance is missing")
    for field in ("component_plan_sha256", "config_sha256", "runtime_receipt_binding_sha256"):
        provenance.pop(field, None)
    return _sha256_bytes(_canonical_json(canonical_payload))


def _is_digest(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _repo_relative_path(value: Any, field_name: str) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError(f"{field_name} must be a nonempty relative path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{field_name} must stay inside the repository")
    return path


def _deck_multiset_sha256(path: Path) -> str:
    cards: list[int] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        value = line.strip()
        if not value:
            continue
        try:
            card_id = int(value)
        except ValueError as error:
            raise ValueError(f"candidate deck line {line_number} is not a card id") from error
        if card_id <= 0:
            raise ValueError(f"candidate deck line {line_number} is not positive")
        cards.append(card_id)
    if len(cards) != 60:
        raise ValueError(f"candidate deck must contain exactly 60 cards, got {len(cards)}")
    return _sha256_bytes(_canonical_json(sorted(cards)))


@dataclass(frozen=True)
class RuntimeRouteReceiptV1:
    """A capability receipt plus its immutable route/provenance envelope."""

    path: str
    payload: Mapping[str, Any]
    capability: CapabilityReceiptV1

    @classmethod
    def from_path(cls, path: str | Path) -> "RuntimeRouteReceiptV1":
        resolved = Path(path)
        with resolved.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("B1 runtime receipt must be a JSON object")
        capability = CapabilityReceiptV1.from_dict(payload)
        receipt = cls(str(resolved), payload, capability)
        receipt.validate()
        return receipt

    def validate(self) -> None:
        if self.capability.scope != RUNTIME_NATIVE or not self.capability.runtime_qualified():
            raise ValueError("B1 runtime receipt is not native-qualified")
        if self.payload.get("scope") != "NATIVE_QUALIFIED":
            raise ValueError("B1 runtime receipt scope is not the enumerated capability scope")
        exact_prizes = {721: 1, 722: 1, 723: 3, 754: 3}
        if {item.card_id: item.prize_units for item in self.capability.prizes} != exact_prizes:
            raise ValueError("B1 PrizeStatic capsule differs from the native proof")
        attacks = {item.attack_id: item for item in self.capability.attacks}
        expected_attacks = {
            1044: (722, 10, (0, 0, 0, 1) + (0,) * 8),
            1045: (722, 30, (0, 0, 0, 2) + (0,) * 8),
        }
        if set(attacks) != set(expected_attacks):
            raise ValueError("B1 attack capsule contains an unsupported attack")
        for attack_id, (card_id, damage, energy_counts) in expected_attacks.items():
            attack = attacks[attack_id]
            if (
                attack.card_id,
                attack.damage,
                attack.energy_counts,
                attack.attack_type,
                attack.qualified,
            ) != (card_id, damage, energy_counts, 3, True):
                raise ValueError(f"B1 attack capsule {attack_id} differs from the native proof")
        cards = {item.card_id: item for item in self.capability.cards}
        expected_cards = {721: (150, 4), 722: (90, 8), 723: (350, 8), 754: (280, -1)}
        if set(cards) != set(expected_cards):
            raise ValueError("B1 card capsule is incomplete or overbroad")
        for card_id, (hp, weakness) in expected_cards.items():
            if (cards[card_id].hp, cards[card_id].weakness_type) != (hp, weakness):
                raise ValueError(f"B1 card capsule {card_id} differs from the card table")
        contexts = {(item.selection_type, item.selection_context, item.option_type, item.choice_role) for item in self.capability.contexts}
        if contexts != {
            (_ATTACK_SELECT_TYPE, _ATTACK_CONTEXT, 13, "ATTACK"),
            (_EVOLVE_SELECT_TYPE, _EVOLVE_CONTEXT, _EVOLVE_TYPE, "EVOLVE"),
        }:
            raise ValueError("B1 context capsule is not exact")
        route = self.payload.get("route_contract")
        if not isinstance(route, dict):
            raise ValueError("B1 route contract is missing")
        if route.get("qualified_attack_ids") != [1044, 1045] or route.get("snover_card_id") != 722:
            raise ValueError("B1 route contract attack identity changed")
        evolution = route.get("evolution")
        if not isinstance(evolution, dict) or {
            evolution.get("selection_type"),
            evolution.get("selection_context"),
            evolution.get("option_type"),
            evolution.get("source_card_id"),
            evolution.get("target_card_id"),
        } != {_EVOLVE_SELECT_TYPE, _EVOLVE_CONTEXT, _EVOLVE_TYPE, _SOURCE_CARD, _TARGET_CARD}:
            raise ValueError("B1 evolution contract is not exact")
        provenance = self.payload.get("provenance")
        if not isinstance(provenance, dict):
            raise ValueError("B1 provenance receipt is missing")
        if self.payload.get("scope_labels") != _EXPECTED_SCOPE_LABELS:
            raise ValueError("B1 capability, integration, and promotion scopes must remain distinct")
        if self.payload.get("runtime_authority") != "ROUTE_CAPABILITY_ONLY":
            raise ValueError("B1 runtime receipt cannot claim policy integration authority")
        capability_evidence = provenance.get("capability_evidence")
        if not isinstance(capability_evidence, dict):
            raise ValueError("B1 capability evidence receipt is missing")
        if set(capability_evidence) != _EXPECTED_CAPABILITY_EVIDENCE_KEYS:
            raise ValueError("B1 capability evidence receipt fields are not the enumerated set")
        if capability_evidence.get("scope") != "NATIVE_QUALIFIED_CANDIDATE" or capability_evidence.get("status") != "BLOCKED_PENDING_EXACT_DECK_CAPABILITY_RERUN":
            raise ValueError("B1 capability evidence is not a blocked exact-deck rerun")
        evidence_paths = {
            "config": capability_evidence.get("config_path"),
            "report": capability_evidence.get("report_path"),
            "raw": capability_evidence.get("raw_path"),
        }
        evidence_hashes = {
            "config": capability_evidence.get("config_sha256"),
            "report": capability_evidence.get("report_sha256"),
            "raw": capability_evidence.get("raw_sha256"),
        }
        if set(evidence_paths) != set(evidence_hashes) or not all(_is_digest(value) for value in evidence_hashes.values()):
            raise ValueError("B1 capability config/report/raw receipts are malformed")
        repo_root = Path(__file__).resolve().parents[3]
        for label, path_value in evidence_paths.items():
            path = _repo_relative_path(path_value, f"capability_evidence.{label}_path")
            actual = repo_root / path
            if not actual.is_file() or _sha256_bytes(actual.read_bytes()) != evidence_hashes[label]:
                raise ValueError(f"B1 capability {label} receipt hash mismatch")
        plan = json.loads((repo_root / _repo_relative_path(evidence_paths["config"], "capability_evidence.config_path")).read_text(encoding="utf-8"))
        report = json.loads((repo_root / _repo_relative_path(evidence_paths["report"], "capability_evidence.report_path")).read_text(encoding="utf-8"))
        raw = json.loads((repo_root / _repo_relative_path(evidence_paths["raw"], "capability_evidence.raw_path")).read_text(encoding="utf-8"))
        knowledge_base_path = _repo_relative_path(provenance.get("knowledge_base"), "provenance.knowledge_base")
        knowledge_base_sha = provenance.get("knowledge_base_sha256")
        if not _is_digest(knowledge_base_sha):
            raise ValueError("B1 knowledge-base receipt is not hashed")
        knowledge_base_file = repo_root / knowledge_base_path
        if not knowledge_base_file.is_file() or _sha256_bytes(knowledge_base_file.read_bytes()) != knowledge_base_sha:
            raise ValueError("B1 knowledge-base path/hash receipt mismatch")
        if plan.get("status") != "BLOCKED_PENDING_INDEPENDENT_TECHNICAL_REVIEW" or report.get("status") != "BLOCKED_PENDING_INDEPENDENT_TECHNICAL_REVIEW" or raw.get("status") != "BLOCKED_PENDING_INDEPENDENT_TECHNICAL_REVIEW":
            raise ValueError("B1 capability evidence must remain plan-only and blocked")
        for label, value in (("plan", plan), ("report", report), ("raw", raw)):
            value_scope_labels = value.get("scope_labels") if label != "plan" else value.get("provenance", {}).get("scope_labels")
            if value.get("scope") != "NATIVE_QUALIFIED_CANDIDATE" or value_scope_labels != _EXPECTED_SCOPE_LABELS:
                raise ValueError(f"B1 capability {label} scope labels are not enumerated")
        if plan.get("candidate_deck", {}).get("file_sha256") != self.payload.get("candidate_deck_sha256"):
            raise ValueError("B1 exact-deck capability plan differs from runtime receipt")
        plan_assets = plan.get("assets")
        if not isinstance(plan_assets, dict) or set(plan_assets) != set(_EXPECTED_ASSET_SCOPES):
            raise ValueError("B1 exact-deck asset scope set is not enumerated")
        receipt_asset_hashes = provenance.get("asset_sha256")
        if not isinstance(receipt_asset_hashes, dict):
            raise ValueError("B1 asset hashes are missing")
        for label, expected_scope in _EXPECTED_ASSET_SCOPES.items():
            entry = plan_assets.get(label)
            if not isinstance(entry, dict) or entry.get("scope") != expected_scope:
                raise ValueError(f"B1 exact-deck asset scope is invalid: {label}")
            path = _repo_relative_path(entry.get("path"), f"capability plan assets.{label}.path")
            actual = repo_root / path
            if not actual.is_file() or _sha256_bytes(actual.read_bytes()) != entry.get("sha256") or entry.get("sha256") != receipt_asset_hashes.get(label):
                raise ValueError(f"B1 exact-deck asset hash mismatch: {label}")
        if plan_assets["card_table"].get("semantic_sha256") != self.payload.get("card_table_semantic_sha256"):
            raise ValueError("B1 exact-deck card-table semantic receipt differs")
        plan_kb = plan.get("knowledge_base")
        if not isinstance(plan_kb, dict) or plan_kb.get("path") != provenance.get("knowledge_base") or plan_kb.get("sha256") != knowledge_base_sha:
            raise ValueError("B1 knowledge-base duplicate declarations differ")
        for label, evidence in (("plan", plan), ("report", report), ("raw", raw)):
            declared_kb = evidence.get("knowledge_base_sha256")
            if declared_kb is not None and declared_kb != knowledge_base_sha:
                raise ValueError(f"B1 {label} knowledge-base duplicate differs")
        plan_source_paths = plan.get("provenance", {}).get("source_paths")
        plan_source_hashes = plan.get("provenance", {}).get("source_sha256")
        if not isinstance(plan_source_paths, dict) or not isinstance(plan_source_hashes, dict) or set(plan_source_paths) != set(plan_source_hashes):
            raise ValueError("B1 exact-deck source receipt is incomplete")
        for label, source_path in plan_source_paths.items():
            actual_source = repo_root / _repo_relative_path(source_path, f"capability plan source_paths.{label}")
            if not actual_source.is_file() or _sha256_bytes(actual_source.read_bytes()) != plan_source_hashes[label]:
                raise ValueError(f"B1 exact-deck source hash mismatch: {label}")
        if report.get("plan_sha256") != evidence_hashes["config"] or raw.get("plan_sha256") != evidence_hashes["config"]:
            raise ValueError("B1 capability report/raw are not bound to the exact plan")
        source_hashes = provenance.get("frozen_source_sha256")
        if not isinstance(source_hashes, dict) or not source_hashes or not all(_is_digest(item) for item in source_hashes.values()):
            raise ValueError("B1 source receipt is incomplete")
        owned_hashes = provenance.get("owned_source_sha256", {})
        if not isinstance(owned_hashes, dict) or not all(_is_digest(item) for item in owned_hashes.values()):
            raise ValueError("B1 owned source receipt is malformed")
        source_scopes = provenance.get("source_scope")
        if not isinstance(source_scopes, dict) or set(source_scopes) != set(_EXPECTED_SOURCE_SCOPES) or set(source_hashes) | set(owned_hashes) != set(_EXPECTED_SOURCE_SCOPES) or source_scopes != _EXPECTED_SOURCE_SCOPES:
            raise ValueError("B1 source receipt scopes are not the enumerated set")
        for source_path, expected in {**source_hashes, **owned_hashes}.items():
            actual_path = repo_root / _repo_relative_path(source_path, "source path")
            if not actual_path.is_file():
                raise ValueError(f"B1 source receipt path is unavailable: {source_path}")
            if _sha256_bytes(actual_path.read_bytes()) != expected:
                raise ValueError(f"B1 source receipt hash mismatch: {source_path}")
        asset_paths = provenance.get("asset_paths")
        asset_hashes = provenance.get("asset_sha256")
        asset_scopes = provenance.get("asset_scope")
        if not isinstance(asset_paths, dict) or not isinstance(asset_hashes, dict) or not isinstance(asset_scopes, dict) or set(asset_paths) != set(_EXPECTED_ASSET_SCOPES) or set(asset_hashes) != set(asset_paths) | {"candidate_deck_semantic_multiset"} or asset_scopes != _EXPECTED_ASSET_SCOPES:
            raise ValueError("B1 asset receipt is not the enumerated set")
        for label, asset_path in asset_paths.items():
            expected = asset_hashes.get(label)
            if not isinstance(asset_path, str) or not _is_digest(expected):
                raise ValueError(f"B1 asset receipt is malformed: {label}")
            actual_path = repo_root / _repo_relative_path(asset_path, f"asset_paths.{label}")
            if not actual_path.is_file() or _sha256_bytes(actual_path.read_bytes()) != expected:
                raise ValueError(f"B1 asset receipt hash mismatch: {label}")
        if asset_hashes.get("candidate_deck") != self.payload.get("candidate_deck_sha256"):
            raise ValueError("B1 candidate deck receipt differs from the exact deck")
        if asset_hashes.get("candidate_deck_semantic_multiset") != self.payload.get("candidate_deck_semantic_multiset_sha256"):
            raise ValueError("B1 candidate deck semantic receipt differs from the exact deck")
        if asset_hashes.get("native_library") != self.payload.get("engine_sha256"):
            raise ValueError("B1 native library receipt differs from engine capability hash")
        if asset_hashes.get("wrapper") != self.payload.get("wrapper_sha256") or asset_hashes.get("api") != self.payload.get("api_sha256"):
            raise ValueError("B1 wrapper/API receipt differs from runtime capability hash")
        candidate_deck_path = repo_root / _repo_relative_path(asset_paths.get("candidate_deck"), "asset_paths.candidate_deck")
        if _deck_multiset_sha256(candidate_deck_path) != self.payload.get("candidate_deck_semantic_multiset_sha256"):
            raise ValueError("B1 candidate deck multiset does not match the exact receipt")
        if asset_hashes.get("card_data") != self.payload.get("card_data_sha256"):
            raise ValueError("B1 card-data receipt differs from the exact card data")
        if asset_hashes.get("card_table") != self.payload.get("card_table_file_sha256"):
            raise ValueError("B1 card-table receipt differs from the exact card table")
        table = json.loads((repo_root / asset_paths["card_table"]).read_text(encoding="utf-8"))
        if table.get("table_sha256") != self.payload.get("card_table_semantic_sha256"):
            raise ValueError("B1 card-table semantic receipt differs from the exact table")
        component_plan_path = provenance.get("component_plan_path")
        component_plan_sha = provenance.get("component_plan_sha256")
        if not isinstance(component_plan_path, str) or not _is_digest(component_plan_sha):
            raise ValueError("B1 component-plan receipt is incomplete")
        plan_file = repo_root / _repo_relative_path(component_plan_path, "provenance.component_plan_path")
        if not plan_file.is_file() or _sha256_bytes(plan_file.read_bytes()) != component_plan_sha:
            raise ValueError("B1 component-plan receipt hash mismatch")
        declared_binding = provenance.get("runtime_receipt_binding_sha256")
        if not _is_digest(declared_binding) or declared_binding != runtime_receipt_binding_sha256(self.payload):
            raise ValueError("B1 runtime receipt canonical content binding differs")
        declared = provenance.get("config_sha256")
        if not _is_digest(declared):
            raise ValueError("B1 config receipt is not sealed")
        without_digest = json.loads(json.dumps(self.payload))
        without_digest["provenance"].pop("config_sha256", None)
        if _sha256_bytes(_canonical_json(without_digest)) != declared:
            raise ValueError("B1 config receipt digest mismatch")


@dataclass(frozen=True)
class B1RequestDiagnosticV1:
    request_id: str
    selection_seq: int
    status: str
    authority: str
    route_active: bool
    delegated: bool
    reason: str | None
    latency_ms: float
    candidate_count: int
    chosen_option_fingerprints: tuple[str, ...]


@dataclass(frozen=True)
class B1DiagnosticsV1:
    route_requests: int
    route_active_requests: int
    b0_delegation_count: int
    unknown_count: int
    ambiguous_count: int
    unsupported_count: int
    no_safe_route_count: int
    selected_authority_count: int
    b0_authority_count: int
    duplicate_request_count: int
    rejected_request_count: int
    reset_count: int
    terminal_boundary_count: int
    error_reset_count: int
    latency_samples: tuple[float, ...]
    last_request: B1RequestDiagnosticV1 | None

    @property
    def p99_latency_ms(self) -> float:
        if not self.latency_samples:
            return 0.0
        values = sorted(self.latency_samples)
        index = min(len(values) - 1, math.ceil(0.99 * len(values)) - 1)
        return values[index]


class _B1PolicyBase:
    formulation_id = A_FORMULATION
    policy_id = "b1-native-route-policy-v1"

    def __init__(self, *, receipt_path: str | Path = RECEIPT_PATH) -> None:
        self.receipt = RuntimeRouteReceiptV1.from_path(receipt_path)
        self.oracle = CurrentStateRouteOracleV1(self.receipt.capability, mode=RUNTIME_NATIVE)
        self._control = DeterministicStrategicPolicy()
        self._episode_uuid: str | None = None
        self._player_index: int | None = None
        self._last_selection_seq: int | None = None
        self._last_request_id: str | None = None
        self._last_request_digest: str | None = None
        self._last_observation_digest: str | None = None
        self._last_action: CompoundActionV1 | None = None
        self._reset_count = 0
        self._terminal_boundary_count = 0
        self._error_reset_count = 0
        self._duplicate_count = 0
        self._rejected_count = 0
        self._route_requests = 0
        self._active_requests = 0
        self._delegation_count = 0
        self._unknown_count = 0
        self._ambiguous_count = 0
        self._unsupported_count = 0
        self._no_safe_count = 0
        self._selected_authority_count = 0
        self._b0_authority_count = 0
        self._latencies: list[float] = []
        self._last_request: B1RequestDiagnosticV1 | None = None

    @property
    def diagnostics(self) -> B1DiagnosticsV1:
        return B1DiagnosticsV1(
            self._route_requests,
            self._active_requests,
            self._delegation_count,
            self._unknown_count,
            self._ambiguous_count,
            self._unsupported_count,
            self._no_safe_count,
            self._selected_authority_count,
            self._b0_authority_count,
            self._duplicate_count,
            self._rejected_count,
            self._reset_count,
            self._terminal_boundary_count,
            self._error_reset_count,
            tuple(self._latencies),
            self._last_request,
        )

    def reset(self, episode_uuid: str, player_index: int, reason: str = "start") -> None:
        self._control.reset(episode_uuid, player_index, reason)
        self.oracle = CurrentStateRouteOracleV1(self.receipt.capability, mode=RUNTIME_NATIVE)
        self._episode_uuid = episode_uuid
        self._player_index = player_index
        self._last_selection_seq = None
        self._last_request_id = None
        self._last_request_digest = None
        self._last_observation_digest = None
        self._last_action = None
        self._reset_count += 1

    def _reset_boundary(self, reason: str) -> None:
        """Reset both authorities without reading a terminal request payload."""

        if self._episode_uuid is not None and self._player_index is not None:
            self._control.reset(self._episode_uuid, self._player_index, reason)
        self.oracle = CurrentStateRouteOracleV1(self.receipt.capability, mode=RUNTIME_NATIVE)
        self._episode_uuid = None
        self._player_index = None
        self._last_selection_seq = None
        self._last_request_id = None
        self._last_request_digest = None
        self._last_observation_digest = None
        self._last_action = None
        self._reset_count += 1
        if reason == "terminal":
            self._terminal_boundary_count += 1
        elif reason == "error":
            self._error_reset_count += 1

    def choose(self, observation: EngineObservationV1, request: SelectionRequestV1) -> CompoundActionV1:
        started = time.perf_counter_ns()
        # Terminal state is the only observation field touched before any
        # request identity, lifecycle, or selection-local data.  The adapter
        # emits no action and resets both authorities at this boundary.
        if isinstance(observation, EngineObservationV1) and observation.terminal_result is not None:
            self._reset_boundary("terminal")
            raise ContractViolation("B1 received a terminal observation at the action boundary")
        try:
            if self._episode_uuid != request.episode_uuid or self._player_index != request.acting_player:
                self._rejected_count += 1
                raise ContractViolation("B1 lifecycle is not reset for this episode/player")
            request_digest = stable_hash(request)
            observation_digest = stable_hash(observation)
            if (
                self._last_selection_seq == request.selection_seq
                and self._last_request_id == request.request_id
                and self._last_action is not None
            ):
                if request_digest != self._last_request_digest or observation_digest != self._last_observation_digest:
                    self._rejected_count += 1
                    raise ContractViolation("B1 duplicate request identity was reused with changed payload")
                self._duplicate_count += 1
                return self._last_action
            if self._last_selection_seq is not None and request.selection_seq <= self._last_selection_seq:
                self._rejected_count += 1
                raise ContractViolation("B1 stale or out-of-order selection sequence")
            if self._last_request_id == request.request_id:
                self._rejected_count += 1
                raise ContractViolation("B1 request identity was reused for a different selection")

            self._route_requests += 1
            decision = self._evaluate(observation, request)
            if decision.status == SELECTED:
                action = self._build_selected(request, decision)
                authority = decision.authority
                self._active_requests += 1
                self._selected_authority_count += 1
            elif decision.status == TERMINAL_OVERRIDE:
                self._rejected_count += 1
                raise ContractViolation("B1 received a terminal observation at the action boundary")
            else:
                # Route abstentions are explicit authority transfer.  B0 is
                # itself a deterministic policy, not a submission fallback.
                self._delegation_count += 1
                if decision.status == UNKNOWN:
                    self._unknown_count += 1
                elif decision.status == AMBIGUOUS:
                    self._ambiguous_count += 1
                elif decision.status == UNSUPPORTED:
                    self._unsupported_count += 1
                elif decision.status == NO_SAFE_ROUTE:
                    self._no_safe_count += 1
                action = self._control.choose(observation, request)
                authority = "B0_CONTROL"
                self._b0_authority_count += 1
            latency = (time.perf_counter_ns() - started) / 1_000_000.0
            self._latencies.append(latency)
            if len(self._latencies) > 2048:
                del self._latencies[:-2048]
            self._last_request = B1RequestDiagnosticV1(
                request.request_id,
                request.selection_seq,
                decision.status,
                authority,
                decision.status == SELECTED,
                decision.status != SELECTED,
                decision.fail_closed_reason,
                latency,
                decision.candidate_count,
                decision.chosen_option_fingerprints,
            )
            self._last_selection_seq = request.selection_seq
            self._last_request_id = request.request_id
            self._last_request_digest = request_digest
            self._last_observation_digest = observation_digest
            self._last_action = action
            return action
        except ContractViolation:
            self._reset_boundary("error")
            raise
        except Exception as error:
            self._rejected_count += 1
            self._reset_boundary("error")
            raise ContractViolation(f"B1 policy rejected current request: {error}") from error

    def _evaluate(self, observation: EngineObservationV1, request: SelectionRequestV1) -> RouteDecisionV1:
        # Terminal status is inspected before any selection-local route
        # fields.  A terminal request is never converted into a route action.
        if observation.terminal_result is not None:
            return self.oracle.evaluate(observation, request, self.formulation_id)
        if self._is_evolution_request(request):
            return self._evaluate_evolution(observation, request)
        return self.oracle.evaluate(observation, request, self.formulation_id)

    def _is_evolution_request(self, request: SelectionRequestV1) -> bool:
        return request.selection_type == _EVOLVE_SELECT_TYPE and request.selection_context == _EVOLVE_CONTEXT

    def _evaluate_evolution(self, observation: EngineObservationV1, request: SelectionRequestV1) -> RouteDecisionV1:
        try:
            PublicStateV1.from_engine(observation, request)
        except PublicStateError as error:
            return self._delegate(request, f"public evolution boundary: {error}")
        if request.min_count != request.max_count or request.max_count != 1:
            if not (request.min_count == 0 and request.max_count == 1 and any(self._is_stop(item) and item.available for item in request.options)):
                return self._delegate(request, "unsupported evolution compound contract")
        entities = {entity.entity_key: entity for entity in observation.entities}
        candidates: list[LegalOptionV1] = []
        for option in request.options:
            if not option.available:
                continue
            if self._is_stop(option):
                candidates.append(option)
                continue
            source = entities.get(option.source_entity_key or "")
            if (
                option.option_type != _EVOLVE_TYPE
                or option.card_id != _TARGET_CARD
                or option.choice_role != "EVOLVE"
                or option.source_kind != "ENTITY"
                or source is None
                or source.owner != observation.acting_player
                or source.card_id != _SOURCE_CARD
                or source.zone not in {AREA["ACTIVE"], AREA["BENCH"]}
                or not self.receipt.capability.supports_context(request, option)
            ):
                return self._delegate(request, "evolution option is outside exact native capability")
            candidates.append(option)
        evolutions = [item for item in candidates if not self._is_stop(item)]
        if len(evolutions) != 1:
            return self._delegate(request, "evolution request is empty or semantically ambiguous")
        option = evolutions[0]
        return RouteDecisionV1(
            schema_version=1,
            request_id=request.request_id,
            selection_seq=request.selection_seq,
            acting_player=request.acting_player,
            policy_id=self.policy_id,
            status=SELECTED,
            formulation_id=self.formulation_id,
            authority="EXPERIMENTAL_PUBLIC_ROUTE_RUNTIME",
            chosen_semantic_action_key=(option.semantic_fingerprint,),
            chosen_option_fingerprints=(option.semantic_fingerprint,),
            decision_key=(1, 1, 0),
            candidate_count=len(candidates),
            complete_route_count=len(candidates),
            route_activation_id="B1-RUNTIME-EVOLUTION-001",
            route_key_sha256=stable_hash({"formulation": self.formulation_id, "option": option.semantic_fingerprint}),
        )

    @staticmethod
    def _is_stop(option: LegalOptionV1) -> bool:
        return option.option_type in _STOP_TYPES or option.choice_role.upper() in {"STOP", "END"}

    def _delegate(self, request: SelectionRequestV1, reason: str) -> RouteDecisionV1:
        return RouteDecisionV1(
            schema_version=1,
            request_id=request.request_id,
            selection_seq=request.selection_seq,
            acting_player=request.acting_player,
            policy_id=self.policy_id,
            status=B0_DELEGATE,
            formulation_id=self.formulation_id,
            authority="B0_CONTROL",
            fail_closed_reason=reason,
        )

    @staticmethod
    def _build_selected(request: SelectionRequestV1, decision: RouteDecisionV1) -> CompoundActionV1:
        if len(decision.chosen_option_fingerprints) != 1:
            raise ContractViolation("B1 selected route does not identify exactly one current action")
        fingerprint = decision.chosen_option_fingerprints[0]
        matches = [index for index, option in enumerate(request.options) if option.available and option.semantic_fingerprint == fingerprint]
        stop = any(
            option.available and option.semantic_fingerprint == fingerprint and _B1PolicyBase._is_stop(option)
            for option in request.options
        )
        builder = CompoundActionBuilder(request)
        if stop:
            if not (request.min_count == 0 and request.max_count == 1):
                raise ContractViolation("B1 selected STOP outside optional singleton contract")
            builder.stop()
        elif len(matches) == 1:
            builder.choose(matches[0])
        else:
            raise ContractViolation("B1 route fingerprint is absent or non-unique")
        # build() invokes the existing compound-action validator and retains
        # STOP as a first-class decoder token.
        return builder.build()


class B1APolicyV1(_B1PolicyBase):
    """B1-A lexicographic current robust lower-bound variant."""

    formulation_id = A_FORMULATION
    policy_id = "b1-a-native-route-policy-v1"


class B1BPolicyV1(_B1PolicyBase):
    """B1-B public threat-margin current-state variant."""

    formulation_id = B_FORMULATION
    policy_id = "b1-b-native-route-policy-v1"


__all__ = [
    "B1APolicyV1",
    "B1BPolicyV1",
    "B1DiagnosticsV1",
    "B1RequestDiagnosticV1",
    "RECEIPT_PATH",
    "RuntimeRouteReceiptV1",
    "runtime_receipt_binding_sha256",
]
