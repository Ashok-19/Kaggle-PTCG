"""Plan and evidence primitives for the bounded B1 component comparison.

This module intentionally has no native-engine entry point.  Stage 0 is an
exact 24-game canary (one game per arm, anchor, and candidate seat).  The
larger 192-game screen is inaccessible until a separately sealed independent
review receipt is supplied.  Evidence helpers write content-addressed,
read-only artifacts and validate them again before a resume.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import resource
import stat
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


DEFAULT_PLAN_PATH = "configs/deterministic/phase_b1_component_qualification_v2.json"
STAGE_CANARY = "stage0_canary"
STAGE_SCREEN = "stage1_screen"
_EXPECTED_ARMS = ("B0", "B1-A", "B1-B")
_EXPECTED_ANCHORS = (
    "rule:dragapult-ex",
    "rule:iono",
    "rule:mega-abomasnow-ex",
    "rule:mega-lucario-ex",
)
_RELIABILITY_COUNTERS = (
    "invalid_selections",
    "fallback_actions",
    "b0_delegations",
    "post_terminal_actions",
    "timeouts",
    "failures",
    "incomplete_games",
    "missing_outputs",
    "stale_requests",
    "duplicate_payload_mismatches",
)
_MIN_P99_SAMPLES = 32
_METRIC_SAMPLER_KIND = "ProcessRuntimeSamplerV1"
_PROCESS_MANIFEST_KIND = "B1_PROCESS_RUNTIME_MANIFEST_V1"
_SOURCE_MANIFEST_KIND = "B1_SOURCE_DEPENDENCY_MANIFEST_V1"
_INDEPENDENT_ATTESTATION_KIND = "B1_INDEPENDENT_STAGE0_ATTESTATION_V1"
_PARENT_AUTHORIZATION_KIND = "B1_PARENT_PREPARED_STAGE0_AUTHORIZATION_V1"
_ZERO_DIGEST = "0" * 64
_SOURCE_RECEIPT_FIELDS = {"source_manifest_path", "source_manifest_sha256"}
_METRIC_PROVENANCE_FIELDS = {
    "schema_version",
    "kind",
    "run_id",
    "stage",
    "plan_sha256",
    "process_manifest_path",
    "process_manifest_sha256",
    "source_manifest_path",
    "source_manifest_sha256",
    "sampler_kind",
    "platform",
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _is_digest(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _p99(values: tuple[float, ...]) -> float:
    if not values:
        raise ValueError("latency sample set is empty")
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(0.99 * len(ordered)) - 1)]


def _safe_name(path: str | Path, field_name: str) -> str:
    value = str(path)
    candidate = Path(value)
    if not value or candidate.is_absolute() or ".." in candidate.parts or len(candidate.parts) != 1:
        raise ValueError(f"{field_name} must be one repository-relative artifact name")
    return value


def _repo_relative_path(value: Any, field_name: str) -> Path:
    """Reject dependency declarations that can escape the repository."""
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError(f"{field_name} must be a nonempty relative path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{field_name} must stay inside the repository")
    return path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _artifact_path(root: Path, value: str | Path, field_name: str) -> Path:
    """Resolve a test or repository-relative sealed-artifact path."""
    path = Path(value)
    if path.is_absolute():
        if root != path.anchor and root not in path.parents:
            # Direct callers may use a temporary artifact root in tests, but
            # the declared paths inside receipts remain relative below.
            return path
        return path
    return root / _repo_relative_path(str(value), field_name)


def _read_json(path: Path, field_name: str, *, require_canonical: bool = True) -> tuple[dict[str, Any], bytes]:
    if not path.is_file():
        raise ValueError(f"{field_name} is unavailable")
    raw_bytes = path.read_bytes()
    try:
        value = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{field_name} is not valid JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be a JSON object")
    if require_canonical and _canonical(value) != raw_bytes:
        raise ValueError(f"{field_name} is not canonically sealed")
    return value, raw_bytes


def _write_read_only(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ValueError(f"sealed artifact already exists: {path}")
    path.write_bytes(content)
    path.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)


@dataclass(frozen=True)
class SourceManifestV1:
    """Typed, content-addressed source/dependency manifest for one run."""

    path: Path
    payload: Mapping[str, Any]
    sha256: str

    @classmethod
    def from_path(
        cls,
        path: Path,
        *,
        run_id: str,
        stage: str,
        plan_sha256: str,
        expected_sources: Mapping[str, Mapping[str, str]],
    ) -> "SourceManifestV1":
        if not path.is_file() or stat.S_IMODE(path.stat().st_mode) != 0o444:
            raise ValueError("source manifest must be an existing 0444 artifact")
        payload, raw_bytes = _read_json(path, "source manifest")
        if set(payload) != {"schema_version", "kind", "run_id", "stage", "plan_sha256", "sources"}:
            raise ValueError("source manifest fields are not the typed enumerated set")
        if payload.get("schema_version") != 1 or payload.get("kind") != _SOURCE_MANIFEST_KIND:
            raise ValueError("source manifest schema or kind is unsupported")
        if payload.get("run_id") != run_id or payload.get("stage") != stage or payload.get("plan_sha256") != plan_sha256:
            raise ValueError("source manifest run/stage/plan lineage differs")
        sources = payload.get("sources")
        if not isinstance(sources, dict) or set(sources) != set(expected_sources):
            raise ValueError("source manifest source set is not the enumerated receipt scope")
        for label, expected in expected_sources.items():
            entry = sources.get(label)
            if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "scope"}:
                raise ValueError(f"source manifest entry is malformed: {label}")
            if entry != dict(expected):
                raise ValueError(f"source manifest entry differs from runtime receipt: {label}")
            source_path = _repo_root() / _repo_relative_path(entry["path"], f"source manifest {label}.path")
            if not source_path.is_file() or hashlib.sha256(source_path.read_bytes()).hexdigest() != entry["sha256"]:
                raise ValueError(f"source manifest source hash mismatch: {label}")
        return cls(path, payload, hashlib.sha256(raw_bytes).hexdigest())


@dataclass(frozen=True)
class ProcessManifestV1:
    """Typed process identity/dependency manifest bound to retained metrics."""

    path: Path
    payload: Mapping[str, Any]
    sha256: str

    @classmethod
    def from_path(
        cls,
        path: Path,
        *,
        run_id: str,
        stage: str,
        plan_sha256: str,
        source_manifest: SourceManifestV1,
        source_manifest_path: str,
        runtime_receipt_path: str,
        runtime_receipt_sha256: str,
        expected_dependencies: Mapping[str, Mapping[str, str]],
        sampler_kind: str,
        platform: str,
    ) -> "ProcessManifestV1":
        if not path.is_file() or stat.S_IMODE(path.stat().st_mode) != 0o444:
            raise ValueError("process manifest must be an existing 0444 artifact")
        payload, raw_bytes = _read_json(path, "process manifest")
        expected_fields = {
            "schema_version",
            "kind",
            "run_id",
            "stage",
            "plan_sha256",
            "source_manifest_path",
            "source_manifest_sha256",
            "runtime_receipt_path",
            "runtime_receipt_sha256",
            "process_identity",
            "command",
            "platform",
            "sampler_kind",
            "native_engine_loaded",
            "dependency_receipts",
        }
        if set(payload) != expected_fields:
            raise ValueError("process manifest fields are not the typed enumerated set")
        if payload.get("schema_version") != 1 or payload.get("kind") != _PROCESS_MANIFEST_KIND:
            raise ValueError("process manifest schema or kind is unsupported")
        if payload.get("run_id") != run_id or payload.get("stage") != stage or payload.get("plan_sha256") != plan_sha256:
            raise ValueError("process manifest run/stage/plan lineage differs")
        if payload.get("source_manifest_path") != source_manifest_path or payload.get("source_manifest_sha256") != source_manifest.sha256:
            raise ValueError("process manifest source receipt differs")
        if payload.get("runtime_receipt_path") != runtime_receipt_path or payload.get("runtime_receipt_sha256") != runtime_receipt_sha256:
            raise ValueError("process manifest runtime receipt binding differs")
        identity = payload.get("process_identity")
        if not isinstance(identity, dict) or set(identity) != {"pid", "start_token", "executable"}:
            raise ValueError("process manifest identity is malformed")
        if isinstance(identity.get("pid"), bool) or not isinstance(identity.get("pid"), int) or identity["pid"] <= 0:
            raise ValueError("process manifest pid is invalid")
        if not isinstance(identity.get("start_token"), str) or not identity["start_token"] or not isinstance(identity.get("executable"), str) or not identity["executable"]:
            raise ValueError("process manifest identity token is invalid")
        if not isinstance(payload.get("command"), str) or not payload["command"]:
            raise ValueError("process manifest command is missing")
        if payload.get("platform") != platform or payload.get("sampler_kind") != sampler_kind:
            raise ValueError("process manifest sampler/platform identity differs")
        if not isinstance(payload.get("native_engine_loaded"), bool):
            raise ValueError("process manifest native-engine load flag is malformed")
        dependencies = payload.get("dependency_receipts")
        if not isinstance(dependencies, dict) or dependencies != dict(expected_dependencies):
            raise ValueError("process manifest dependency path/hash/scope receipts differ from the loaded receipt")
        for label, entry in dependencies.items():
            if not isinstance(entry, Mapping) or set(entry) != {"path", "sha256", "scope"} or not _is_digest(entry.get("sha256")):
                raise ValueError(f"process manifest dependency receipt is malformed: {label}")
            if label == "source_manifest":
                dependency_path = source_manifest.path
            elif label == "runtime_receipt" or label.startswith("capability_") or label in {"api", "candidate_deck", "card_data", "card_table", "knowledge_base", "native_library", "wrapper"}:
                dependency_path = _repo_root() / _repo_relative_path(entry["path"], f"process manifest {label}.path")
            else:
                raise ValueError(f"process manifest dependency label is not enumerated: {label}")
            if not dependency_path.is_file():
                raise ValueError(f"process manifest dependency hash mismatch: {label}")
            if label == "runtime_receipt":
                from .b1_policy import RuntimeRouteReceiptV1, runtime_receipt_binding_sha256

                try:
                    actual_digest = runtime_receipt_binding_sha256(RuntimeRouteReceiptV1.from_path(dependency_path).payload)
                except (OSError, ValueError) as error:
                    raise ValueError("process manifest runtime receipt cannot be reloaded") from error
            else:
                actual_digest = hashlib.sha256(dependency_path.read_bytes()).hexdigest()
            if actual_digest != entry["sha256"]:
                raise ValueError(f"process manifest dependency hash mismatch: {label}")
        return cls(path, payload, hashlib.sha256(raw_bytes).hexdigest())


def _load_runtime_receipt_for_plan(plan_payload: Mapping[str, Any]):
    from .b1_policy import RuntimeRouteReceiptV1, runtime_receipt_binding_sha256

    receipt_path = _repo_root() / _repo_relative_path(plan_payload.get("runtime_receipt"), "runtime_receipt")
    receipt = RuntimeRouteReceiptV1.from_path(receipt_path)
    return receipt, runtime_receipt_binding_sha256(receipt.payload)


def _expected_source_records(receipt_payload: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    provenance = receipt_payload.get("provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError("runtime receipt provenance is missing for source manifest")
    frozen = provenance.get("frozen_source_sha256")
    owned = provenance.get("owned_source_sha256")
    scopes = provenance.get("source_scope")
    if not isinstance(frozen, Mapping) or not isinstance(owned, Mapping) or not isinstance(scopes, Mapping):
        raise ValueError("runtime receipt source declarations are incomplete")
    hashes = {**frozen, **owned}
    if set(hashes) != set(scopes):
        raise ValueError("runtime receipt source declarations are not a duplicate-hash-equal set")
    return {label: {"path": label, "sha256": digest, "scope": scopes[label]} for label, digest in sorted(hashes.items())}


def _expected_dependency_receipts(
    receipt_payload: Mapping[str, Any],
    runtime_receipt_path: str,
    runtime_receipt_sha256: str,
    source_manifest_path: str,
    source_manifest_sha256: str,
) -> dict[str, dict[str, str]]:
    provenance = receipt_payload.get("provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError("runtime receipt provenance is missing for process manifest")
    asset_paths = provenance.get("asset_paths")
    asset_hashes = provenance.get("asset_sha256")
    asset_scopes = provenance.get("asset_scope")
    capability_evidence = provenance.get("capability_evidence")
    if not isinstance(asset_paths, Mapping) or not isinstance(asset_hashes, Mapping) or not isinstance(asset_scopes, Mapping) or not isinstance(capability_evidence, Mapping):
        raise ValueError("runtime receipt dependency path/hash/scope receipts are incomplete")
    dependencies: dict[str, dict[str, str]] = {}
    for label in sorted(asset_paths):
        path = asset_paths[label]
        digest = asset_hashes.get(label)
        scope = asset_scopes.get(label)
        if not isinstance(path, str) or not _is_digest(digest) or not isinstance(scope, str) or not scope:
            raise ValueError(f"runtime receipt dependency receipt is malformed: {label}")
        dependencies[str(label)] = {"path": path, "sha256": digest, "scope": scope}
    evidence_scope = capability_evidence.get("scope")
    for label in ("config", "report", "raw"):
        path = capability_evidence.get(f"{label}_path")
        digest = capability_evidence.get(f"{label}_sha256")
        if not isinstance(path, str) or not _is_digest(digest) or not isinstance(evidence_scope, str) or not evidence_scope:
            raise ValueError(f"runtime receipt capability evidence receipt is malformed: {label}")
        dependencies[f"capability_{label}"] = {"path": path, "sha256": digest, "scope": evidence_scope}
    dependencies["runtime_receipt"] = {"path": runtime_receipt_path, "sha256": runtime_receipt_sha256, "scope": "B1_RUNTIME_ROUTE_RECEIPT"}
    dependencies["source_manifest"] = {"path": source_manifest_path, "sha256": source_manifest_sha256, "scope": "B1_SOURCE_DEPENDENCY_MANIFEST"}
    return dict(sorted(dependencies.items()))


def prepare_runtime_manifests(
    plan: "B1ComponentPlanV1",
    *,
    run_id: str,
    stage: str,
    artifact_root: str | Path,
    source_manifest_path: str = "source-manifest.json",
    process_manifest_path: str = "process-manifest.json",
    command: str = "phase_b1_component_qualification.py --native-launch-blocked",
    platform: str = sys.platform,
    native_engine_loaded: bool = False,
    process_identity: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    """Create the typed 0444 manifests a reviewed launcher must bind to evidence.

    This helper does not execute native games.  It records the actual current
    source/dependency bytes and the caller's process identity so a later
    sealed evidence artifact can only be accepted when it reloads these files.
    """
    if not run_id or not isinstance(stage, str):
        raise ValueError("manifest run/stage identity is malformed")
    root = Path(artifact_root).resolve()
    _repo_relative_path(source_manifest_path, "source_manifest_path")
    _repo_relative_path(process_manifest_path, "process_manifest_path")
    receipt, receipt_binding = _load_runtime_receipt_for_plan(plan.payload)
    source_payload = {
        "schema_version": 1,
        "kind": _SOURCE_MANIFEST_KIND,
        "run_id": run_id,
        "stage": stage,
        "plan_sha256": plan.plan_sha256,
        "sources": _expected_source_records(receipt.payload),
    }
    source_path = _artifact_path(root, source_manifest_path, "source_manifest_path")
    _write_read_only(source_path, _canonical(source_payload))
    source_digest = hashlib.sha256(_canonical(source_payload)).hexdigest()
    dependencies = _expected_dependency_receipts(receipt.payload, str(plan.payload["runtime_receipt"]), receipt_binding, source_manifest_path, source_digest)
    identity = dict(process_identity or {})
    identity.setdefault("pid", os.getpid())
    identity.setdefault("start_token", f"pid-{os.getpid()}-manifest-{time.time_ns()}")
    identity.setdefault("executable", os.path.realpath(sys.executable))
    process_payload = {
        "schema_version": 1,
        "kind": _PROCESS_MANIFEST_KIND,
        "run_id": run_id,
        "stage": stage,
        "plan_sha256": plan.plan_sha256,
        "source_manifest_path": source_manifest_path,
        "source_manifest_sha256": source_digest,
        "runtime_receipt_path": str(plan.payload["runtime_receipt"]),
        "runtime_receipt_sha256": receipt_binding,
        "process_identity": identity,
        "command": command,
        "platform": platform,
        "sampler_kind": _METRIC_SAMPLER_KIND,
        "native_engine_loaded": native_engine_loaded,
        "dependency_receipts": dependencies,
    }
    process_path = _artifact_path(root, process_manifest_path, "process_manifest_path")
    _write_read_only(process_path, _canonical(process_payload))
    process_digest = hashlib.sha256(_canonical(process_payload)).hexdigest()
    return {
        "process_manifest_path": process_manifest_path,
        "process_manifest_sha256": process_digest,
        "source_manifest_path": source_manifest_path,
        "source_manifest_sha256": source_digest,
    }


@dataclass(frozen=True)
class ComponentRuntimeMetricsV1:
    """Finite process/runtime evidence required by the component gate."""

    latency_samples_ms: tuple[float, ...]
    p99_latency_ms: float
    component_cpu_seconds: float
    game_count: int
    request_count: int
    peak_rss_bytes: int
    per_arm: Mapping[str, int]
    per_seat: Mapping[str, int]
    reliability_counters: Mapping[str, int]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ComponentRuntimeMetricsV1":
        raw_samples = value.get("latency_samples_ms", ())
        if not isinstance(raw_samples, (list, tuple)):
            raise ValueError("latency samples must be a sequence")
        samples = tuple(float(item) for item in raw_samples)
        raw_counts = value.get("reliability_counters", {})
        raw_arms = value.get("per_arm", {})
        raw_seats = value.get("per_seat", {})
        if not isinstance(raw_counts, Mapping) or not isinstance(raw_arms, Mapping) or not isinstance(raw_seats, Mapping):
            raise ValueError("runtime metric maps are malformed")
        integer_fields = ("game_count", "request_count", "peak_rss_bytes")
        if any(isinstance(value.get(field), bool) or not isinstance(value.get(field), int) for field in integer_fields):
            raise ValueError("runtime game/request/RSS metrics must be integers")
        metrics = cls(
            samples,
            float(value.get("p99_latency_ms")),
            float(value.get("component_cpu_seconds")),
            value["game_count"],
            value["request_count"],
            value["peak_rss_bytes"],
            {str(key): item for key, item in raw_arms.items()},
            {str(key): item for key, item in raw_seats.items()},
            {str(key): item for key, item in raw_counts.items()},
        )
        metrics.validate()
        return metrics

    def as_dict(self) -> dict[str, Any]:
        return {
            "latency_samples_ms": list(self.latency_samples_ms),
            "p99_latency_ms": self.p99_latency_ms,
            "component_cpu_seconds": self.component_cpu_seconds,
            "game_count": self.game_count,
            "request_count": self.request_count,
            "peak_rss_bytes": self.peak_rss_bytes,
            "per_arm": dict(sorted(self.per_arm.items())),
            "per_seat": dict(sorted(self.per_seat.items())),
            "reliability_counters": dict(sorted(self.reliability_counters.items())),
        }

    def validate(self, *, min_p99_samples: int = _MIN_P99_SAMPLES) -> None:
        if len(self.latency_samples_ms) < min_p99_samples:
            raise ValueError(f"p99 latency requires at least {min_p99_samples} samples")
        if any(not math.isfinite(item) or item < 0 for item in self.latency_samples_ms):
            raise ValueError("latency samples must be finite and nonnegative")
        if not math.isfinite(self.p99_latency_ms) or self.p99_latency_ms < 0 or not math.isclose(self.p99_latency_ms, _p99(self.latency_samples_ms), rel_tol=0, abs_tol=1e-12):
            raise ValueError("p99 latency is not the declared finite sample percentile")
        if not math.isfinite(self.component_cpu_seconds) or self.component_cpu_seconds < 0:
            raise ValueError("component CPU evidence must be finite and nonnegative")
        if isinstance(self.game_count, bool) or self.game_count < 0 or isinstance(self.request_count, bool) or self.request_count < 0:
            raise ValueError("runtime game/request counts must be nonnegative integers")
        if isinstance(self.peak_rss_bytes, bool) or self.peak_rss_bytes < 0:
            raise ValueError("peak RSS evidence must be a nonnegative integer")
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in (*self.per_arm.values(), *self.per_seat.values())):
            raise ValueError("per-arm/per-seat counts must be nonnegative")
        if set(self.reliability_counters) != set(_RELIABILITY_COUNTERS):
            raise ValueError("reliability counter evidence is incomplete")
        for key in _RELIABILITY_COUNTERS:
            value = self.reliability_counters.get(key, 0)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("reliability counters must be nonnegative integers")

    @property
    def reliability_pass(self) -> bool:
        return all(self.reliability_counters.get(key, 0) == 0 for key in _RELIABILITY_COUNTERS)


class ProcessRuntimeSamplerV1:
    """Small process-local sampler used by a future reviewed launcher."""

    def __init__(self) -> None:
        self._cpu_start: float | None = None
        self._latencies: list[float] = []

    def start(self) -> None:
        self._cpu_start = time.process_time()
        self._latencies.clear()

    def observe_latency_ms(self, value: float) -> None:
        if not math.isfinite(value) or value < 0:
            raise ValueError("latency sample must be finite and nonnegative")
        self._latencies.append(value)

    def finish(
        self,
        *,
        game_count: int,
        request_count: int,
        per_arm: Mapping[str, int],
        per_seat: Mapping[str, int],
        reliability_counters: Mapping[str, int],
    ) -> ComponentRuntimeMetricsV1:
        if self._cpu_start is None:
            raise ValueError("process sampler was not started")
        usage = resource.getrusage(resource.RUSAGE_SELF)
        metrics = ComponentRuntimeMetricsV1(
            tuple(self._latencies),
            _p99(tuple(self._latencies)),
            max(0.0, time.process_time() - self._cpu_start),
            game_count,
            request_count,
            max(0, int(usage.ru_maxrss) * 1024),
            dict(per_arm),
            dict(per_seat),
            dict(reliability_counters),
        )
        metrics.validate()
        return metrics


@dataclass(frozen=True)
class B1ComponentPlanV1:
    path: str
    payload: Mapping[str, Any]
    plan_sha256: str

    @classmethod
    def from_path(cls, path: str | Path = DEFAULT_PLAN_PATH) -> "B1ComponentPlanV1":
        resolved = Path(path)
        with resolved.open(encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("B1 component plan must be a JSON object")
        plan = cls(str(resolved), payload, hashlib.sha256(resolved.read_bytes()).hexdigest())
        plan.validate()
        return plan

    @property
    def anchors(self) -> tuple[str, ...]:
        return tuple(self.payload["anchors"])

    @property
    def arms(self) -> tuple[str, ...]:
        return tuple(item["id"] for item in self.payload["candidate"]["arms"])

    @property
    def games_per_arm(self) -> int:
        return int(self.payload["stages"][STAGE_SCREEN]["games_per_arm"])

    @property
    def games_all_arms(self) -> int:
        return int(self.payload["stages"][STAGE_SCREEN]["games_all_arms"])

    @property
    def canary_games_all_arms(self) -> int:
        return int(self.payload["stages"][STAGE_CANARY]["games_all_arms"])

    @property
    def p99_min_samples(self) -> int:
        return int(self.payload["component_runtime_budget"]["p99_min_samples"])

    def validate(self) -> None:
        if self.payload.get("schema_version") != 2:
            raise ValueError("unsupported B1 component plan schema")
        if self.payload.get("status") != "TECHNICALLY_BLOCKED_PENDING_INDEPENDENT_REVIEW_RECEIPT":
            raise ValueError("B1 component plan must remain technically blocked")
        if self.arms != _EXPECTED_ARMS or self.anchors != _EXPECTED_ANCHORS:
            raise ValueError("B1 component arms or anchor matrix changed")
        repo_root = _repo_root()
        runtime_receipt = _repo_relative_path(self.payload.get("runtime_receipt"), "runtime_receipt")
        runtime_receipt_file = repo_root / runtime_receipt
        if not runtime_receipt_file.is_file():
            raise ValueError("B1 runtime receipt path is unavailable")
        runtime_receipt_sha256 = self.payload.get("runtime_receipt_sha256")
        if not _is_digest(runtime_receipt_sha256):
            raise ValueError("B1 runtime receipt canonical content hash is missing")
        try:
            from .b1_policy import RuntimeRouteReceiptV1, runtime_receipt_binding_sha256

            loaded_receipt = RuntimeRouteReceiptV1.from_path(runtime_receipt_file)
            loaded_receipt_binding = runtime_receipt_binding_sha256(loaded_receipt.payload)
        except (OSError, ValueError) as error:
            raise ValueError("B1 runtime receipt parsed-content validation failed") from error
        if loaded_receipt_binding != runtime_receipt_sha256:
            raise ValueError("B1 runtime receipt path/content hash binding differs")
        receipt_provenance = loaded_receipt.payload.get("provenance")
        if not isinstance(receipt_provenance, Mapping):
            raise ValueError("B1 runtime receipt provenance is missing")
        try:
            expected_plan_path = Path(self.path).resolve().relative_to(repo_root).as_posix()
        except ValueError:
            expected_plan_path = Path(self.path).as_posix()
        if receipt_provenance.get("component_plan_path") != expected_plan_path or receipt_provenance.get("component_plan_sha256") != self.plan_sha256:
            raise ValueError("B1 runtime receipt is not bound to this exact component plan")
        candidate = self.payload.get("candidate")
        if not isinstance(candidate, dict):
            raise ValueError("B1 candidate declaration is missing")
        deck_path = _repo_relative_path(candidate.get("deck_path"), "candidate.deck_path")
        deck_file = repo_root / deck_path
        if not deck_file.is_file():
            raise ValueError("B1 candidate deck path is unavailable")
        if hashlib.sha256(deck_file.read_bytes()).hexdigest() != candidate.get("deck_sha256"):
            raise ValueError("B1 candidate deck path/hash receipt mismatch")
        knowledge_base = self.payload.get("knowledge_base")
        if not isinstance(knowledge_base, dict):
            raise ValueError("B1 knowledge-base declaration is missing")
        kb_path = _repo_relative_path(knowledge_base.get("path"), "knowledge_base.path")
        kb_file = repo_root / kb_path
        if not kb_file.is_file() or hashlib.sha256(kb_file.read_bytes()).hexdigest() != knowledge_base.get("sha256"):
            raise ValueError("B1 knowledge-base path/hash receipt mismatch")
        evidence = self.payload.get("evidence")
        if not isinstance(evidence, dict):
            raise ValueError("B1 evidence declaration is missing")
        _repo_relative_path(evidence.get("raw_root"), "evidence.raw_root")
        _repo_relative_path(evidence.get("sanitized_report_root"), "evidence.sanitized_report_root")
        if evidence.get("absolute_paths_forbidden") is not True:
            raise ValueError("B1 evidence must forbid absolute paths")
        if evidence.get("metric_provenance_required") != [
            "schema_version",
            "kind",
            "run_id",
            "stage",
            "plan_sha256",
            "process_manifest_path",
            "process_manifest_sha256",
            "source_manifest_path",
            "source_manifest_sha256",
            "sampler_kind",
            "platform",
        ]:
            raise ValueError("B1 metric provenance requirements changed")
        attestation = self.payload.get("independent_attestation")
        if not isinstance(attestation, dict) or set(attestation) != {
            "schema_version",
            "kind",
            "status",
            "review_artifact_path",
            "review_artifact_sha256",
            "parent_authorization_path",
            "parent_authorization_sha256",
            "requires_post_run_review",
            "requires_parent_prepared_authorization",
        }:
            raise ValueError("B1 independent attestation gate is not the typed enumerated set")
        if (
            attestation.get("schema_version") != 1
            or attestation.get("kind") != _INDEPENDENT_ATTESTATION_KIND
            or attestation.get("status") != "BLOCKED_PENDING_POST_RUN_INDEPENDENT_REVIEW_AND_PARENT_AUTHORIZATION"
            or attestation.get("requires_post_run_review") is not True
            or attestation.get("requires_parent_prepared_authorization") is not True
        ):
            raise ValueError("B1 independent attestation gate must remain blocked")
        for field in ("review_artifact_path", "parent_authorization_path"):
            _repo_relative_path(attestation.get(field), f"independent_attestation.{field}")
        for field in ("review_artifact_sha256", "parent_authorization_sha256"):
            if not _is_digest(attestation.get(field)):
                raise ValueError(f"independent_attestation.{field} is malformed")
        if attestation.get("review_artifact_sha256") != _ZERO_DIGEST or attestation.get("parent_authorization_sha256") != _ZERO_DIGEST:
            raise ValueError("B1 attestation placeholders must remain parent-controlled until review")
        evaluation = self.payload["evaluation"]
        if evaluation.get("natural_deployment") is not True or evaluation.get("candidate_seat_values") != [0, 1]:
            raise ValueError("B1 component plan must be natural-seat balanced")
        if evaluation.get("permutation_control") != 32 or evaluation.get("stop_on_any_reliability_defect") is not True:
            raise ValueError("B1 reliability/permutation contract changed")
        stages = self.payload.get("stages")
        if not isinstance(stages, dict) or set(stages) != {STAGE_CANARY, STAGE_SCREEN}:
            raise ValueError("B1 plan must declare canary and gated screen stages")
        canary = stages[STAGE_CANARY]
        if canary.get("games_per_cell") != 1 or canary.get("games_per_arm") != 8 or canary.get("games_all_arms") != 24:
            raise ValueError("B1 stage-0 canary must be exactly one game per cell")
        if canary.get("requires_independent_review") is not False or canary.get("stop_on_any_reliability_defect") is not True:
            raise ValueError("B1 stage-0 canary gate changed")
        screen = stages[STAGE_SCREEN]
        if screen.get("games_per_cell") != 8 or screen.get("games_per_arm") != 64 or screen.get("games_all_arms") != 192:
            raise ValueError("B1 stage-1 screen budget changed")
        if screen.get("requires_stage0_review") is not True or screen.get("accessible_without_review") is not False:
            raise ValueError("B1 screen is not gated by canary review")
        runtime = self.payload["component_runtime_budget"]
        if runtime.get("scope") != "experiment_local_only" or runtime.get("promotion_criteria_change") is not False:
            raise ValueError("B1 component runtime budget must not alter promotion criteria")
        if runtime.get("p99_latency_ms_max") != 100.0 or runtime.get("component_cpu_seconds_per_game_max") != 1.0 or runtime.get("peak_rss_bytes_max") != 536870912 or runtime.get("p99_min_samples") != _MIN_P99_SAMPLES:
            raise ValueError("B1 component runtime budget changed")
        if self.payload["launch_gate"].get("status") != "BLOCKED" or self.payload["launch_gate"].get("native_run_performed") is not False:
            raise ValueError("B1 native launch gate is not closed")

    def _stage(self, stage: str) -> Mapping[str, Any]:
        if stage not in {STAGE_CANARY, STAGE_SCREEN}:
            raise ValueError(f"unknown B1 stage {stage!r}")
        return self.payload["stages"][stage]

    def _validate_metric_provenance(
        self,
        raw_evidence: Mapping[str, Any],
        stage: str,
        *,
        run_id: str | None = None,
        artifact_root: str | Path | None = None,
    ) -> dict[str, Any]:
        provenance = raw_evidence.get("metric_provenance")
        if not isinstance(provenance, dict):
            raise ValueError("sealed evidence is missing metric provenance")
        if set(provenance) != _METRIC_PROVENANCE_FIELDS:
            raise ValueError("metric provenance fields are incomplete")
        if provenance.get("schema_version") != 1 or provenance.get("kind") != "B1_METRIC_PROVENANCE_V1":
            raise ValueError("metric provenance schema or kind is unsupported")
        if not isinstance(provenance.get("run_id"), str) or not provenance["run_id"] or "/" in provenance["run_id"] or "\\" in provenance["run_id"]:
            raise ValueError("metric provenance run_id is malformed")
        if run_id is not None and provenance["run_id"] != run_id:
            raise ValueError("metric provenance run_id differs from sealed run")
        if provenance.get("stage") != stage or provenance.get("plan_sha256") != self.plan_sha256:
            raise ValueError("metric provenance stage/plan lineage differs")
        for field in ("process_manifest_path", "source_manifest_path"):
            _repo_relative_path(provenance.get(field), f"metric_provenance.{field}")
        if not _is_digest(provenance.get("process_manifest_sha256")) or not _is_digest(provenance.get("source_manifest_sha256")):
            raise ValueError("metric provenance manifest digest is malformed")
        if provenance.get("sampler_kind") != _METRIC_SAMPLER_KIND or not isinstance(provenance.get("platform"), str) or not provenance["platform"]:
            raise ValueError("metric provenance sampler identity is invalid")
        root = Path(artifact_root).resolve() if artifact_root is not None else _repo_root()
        self._validate_manifest_binding(provenance, stage=stage, run_id=provenance["run_id"], artifact_root=root)
        return provenance

    def _validate_manifest_binding(
        self,
        provenance: Mapping[str, Any],
        *,
        stage: str,
        run_id: str,
        artifact_root: Path,
    ) -> tuple[ProcessManifestV1, SourceManifestV1]:
        receipt, receipt_binding = _load_runtime_receipt_for_plan(self.payload)
        configured_receipt = self.payload.get("runtime_receipt")
        if receipt.path != str((_repo_root() / _repo_relative_path(configured_receipt, "runtime_receipt")).resolve()):
            raise ValueError("runtime receipt loaded from an unexpected path")
        if self.payload.get("runtime_receipt_sha256") != receipt_binding:
            raise ValueError("runtime receipt canonical content binding differs from component plan")
        source_manifest_path = str(provenance["source_manifest_path"])
        source_manifest = SourceManifestV1.from_path(
            _artifact_path(artifact_root, source_manifest_path, "source_manifest_path"),
            run_id=run_id,
            stage=stage,
            plan_sha256=self.plan_sha256,
            expected_sources=_expected_source_records(receipt.payload),
        )
        expected_dependencies = _expected_dependency_receipts(
            receipt.payload,
            str(configured_receipt),
            receipt_binding,
            source_manifest_path,
            source_manifest.sha256,
        )
        process_manifest_path = str(provenance["process_manifest_path"])
        process_manifest = ProcessManifestV1.from_path(
            _artifact_path(artifact_root, process_manifest_path, "process_manifest_path"),
            run_id=run_id,
            stage=stage,
            plan_sha256=self.plan_sha256,
            source_manifest=source_manifest,
            source_manifest_path=source_manifest_path,
            runtime_receipt_path=str(configured_receipt),
            runtime_receipt_sha256=receipt_binding,
            expected_dependencies=expected_dependencies,
            sampler_kind=str(provenance["sampler_kind"]),
            platform=str(provenance["platform"]),
        )
        if hashlib.sha256(process_manifest.path.read_bytes()).hexdigest() != provenance["process_manifest_sha256"]:
            raise ValueError("metric provenance process manifest digest differs from loaded artifact")
        if source_manifest.sha256 != provenance["source_manifest_sha256"]:
            raise ValueError("metric provenance source manifest digest differs from loaded artifact")
        return process_manifest, source_manifest

    @staticmethod
    def _recompute_reliability_gate(raw_evidence: Mapping[str, Any], metrics: ComponentRuntimeMetricsV1) -> bool:
        if not metrics.reliability_pass:
            return False
        games = raw_evidence.get("games")
        if not isinstance(games, list):
            return False
        for item in games:
            if not isinstance(item, dict):
                return False
            if item.get("reliability_defect") is True:
                return False
            counters = item.get("reliability_counters", {})
            if not isinstance(counters, Mapping):
                return False
            for value in counters.values():
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    return False
                if value:
                    return False
        return True

    def verify_stage0_artifacts(
        self,
        review_artifact_path: str | Path,
        canary_evidence_path: str | Path,
        canary_sidecar_path: str | Path,
        *,
        artifact_root: str | Path | None = None,
        expected_review_sha256: str | None = None,
        expected_evidence_sha256: str | None = None,
        expected_sidecar_sha256: str | None = None,
    ) -> Mapping[str, Any]:
        """Load and verify the actual sealed canary and independent review files."""
        root = Path(artifact_root).resolve() if artifact_root is not None else _repo_root()
        review_path = _artifact_path(root, review_artifact_path, "review_artifact_path")
        evidence_path = _artifact_path(root, canary_evidence_path, "canary_evidence_path")
        sidecar_path = _artifact_path(root, canary_sidecar_path, "canary_sidecar_path")
        for path, label in ((review_path, "review artifact"), (evidence_path, "canary evidence"), (sidecar_path, "canary sidecar")):
            if not path.is_file():
                raise ValueError(f"{label} is unavailable")
            if stat.S_IMODE(path.stat().st_mode) & 0o222:
                raise ValueError(f"{label} is writable")
        attestation_gate = self.payload["independent_attestation"]
        if str(review_artifact_path) != attestation_gate["review_artifact_path"]:
            raise ValueError("stage-0 review artifact path is not the plan's exact independent-attestation path")
        if expected_review_sha256 != attestation_gate["review_artifact_sha256"]:
            raise ValueError("stage-0 review artifact hash is not parent-authorized")
        review, review_bytes = _read_json(review_path, "review artifact")
        review_digest = hashlib.sha256(review_bytes).hexdigest()
        if expected_review_sha256 is not None and review_digest != expected_review_sha256:
            raise ValueError("review artifact digest differs")
        required_attestation_fields = {
            "schema_version",
            "kind",
            "status",
            "scope",
            "plan_sha256",
            "stage",
            "run_id",
            "reviewer_id",
            "reviewer_role",
            "reviewer_authority_sha256",
            "audited_commit",
            "audited_source_sha256",
            "runtime_receipt_path",
            "runtime_receipt_sha256",
            "capability_evidence",
            "canary_evidence_path",
            "canary_evidence_sha256",
            "canary_sidecar_path",
            "canary_sidecar_sha256",
            "parent_authorization_path",
            "parent_authorization_sha256",
            "post_run_stage0",
            "stage0_game_count",
            "native_launch_authorized",
            "screen_unlocked",
        }
        if set(review) != required_attestation_fields or review.get("kind") != _INDEPENDENT_ATTESTATION_KIND:
            raise ValueError("stage-0 artifact is not the typed independent attestation schema")
        if review.get("status") != "PASS" or review.get("scope") != "B1_STAGE0_CANARY_INDEPENDENT_REVIEW":
            raise ValueError("stage-0 independent attestation is not PASS")
        if review.get("reviewer_role") != "INDEPENDENT_REVIEWER" or not isinstance(review.get("reviewer_id"), str) or not review["reviewer_id"] or not _is_digest(review.get("reviewer_authority_sha256")):
            raise ValueError("stage-0 attestation reviewer authority is malformed")
        if not isinstance(review.get("audited_commit"), str) or len(review["audited_commit"]) != 40 or any(character not in "0123456789abcdef" for character in review["audited_commit"]):
            raise ValueError("stage-0 attestation audited commit is malformed")
        if review.get("post_run_stage0") is not True or review.get("stage0_game_count") != self.canary_games_all_arms:
            raise ValueError("stage-0 attestation is not a post-run 24-game review")
        if review.get("plan_sha256") != self.plan_sha256 or review.get("stage") != STAGE_CANARY:
            raise ValueError("stage-0 independent review artifact is bound to another plan/stage")
        if review.get("native_launch_authorized") is not False or review.get("screen_unlocked") is not True:
            raise ValueError("stage-0 review artifact has invalid launch authority")
        if review.get("parent_authorization_path") != attestation_gate["parent_authorization_path"] or review.get("parent_authorization_sha256") != attestation_gate["parent_authorization_sha256"]:
            raise ValueError("stage-0 attestation parent authorization pointer differs from the plan")
        run_id = review.get("run_id")
        if not isinstance(run_id, str) or not run_id or "/" in run_id or "\\" in run_id:
            raise ValueError("stage-0 review artifact run_id is malformed")
        parent_path = _artifact_path(root, review["parent_authorization_path"], "parent_authorization_path")
        if expected_review_sha256 == _ZERO_DIGEST or review_digest == _ZERO_DIGEST:
            raise ValueError("stage-0 independent attestation is not parent-authorized")
        if not parent_path.is_file() or stat.S_IMODE(parent_path.stat().st_mode) != 0o444:
            raise ValueError("stage-0 parent-prepared authorization receipt is unavailable")
        parent, parent_bytes = _read_json(parent_path, "parent authorization")
        parent_digest = hashlib.sha256(parent_bytes).hexdigest()
        if parent_digest != review["parent_authorization_sha256"] or parent_digest != attestation_gate["parent_authorization_sha256"]:
            raise ValueError("stage-0 parent authorization digest is not the configured receipt")
        parent_fields = {
            "schema_version",
            "kind",
            "status",
            "prepared_by",
            "plan_sha256",
            "run_id",
            "stage",
            "review_artifact_path",
            "review_artifact_sha256",
            "runtime_receipt_path",
            "runtime_receipt_sha256",
            "capability_evidence",
            "canary_evidence_path",
            "canary_evidence_sha256",
            "canary_sidecar_path",
            "canary_sidecar_sha256",
            "audited_commit",
            "audited_source_sha256",
            "native_launch_authorized",
            "stage1_authorized",
        }
        if set(parent) != parent_fields or parent.get("schema_version") != 1 or parent.get("kind") != _PARENT_AUTHORIZATION_KIND or parent.get("status") != "AUTHORIZED_FOR_B1_STAGE0_CANARY" or parent.get("prepared_by") != "PARENT_AGENT":
            raise ValueError("stage-0 parent authorization receipt is not independently prepared")
        if parent.get("plan_sha256") != self.plan_sha256 or parent.get("run_id") != run_id or parent.get("stage") != STAGE_CANARY or parent.get("review_artifact_path") != str(review_artifact_path) or parent.get("review_artifact_sha256") != review_digest or parent.get("stage1_authorized") is not False or parent.get("native_launch_authorized") is not True:
            raise ValueError("stage-0 parent authorization lineage or authority is invalid")
        if parent.get("runtime_receipt_path") != self.payload["runtime_receipt"] or parent.get("runtime_receipt_sha256") != self.payload["runtime_receipt_sha256"]:
            raise ValueError("stage-0 parent authorization runtime receipt differs")
        if review.get("parent_authorization_sha256") != parent_digest:
            raise ValueError("stage-0 attestation is not bound to parent authorization")
        if parent.get("capability_evidence") != review["capability_evidence"] or parent.get("audited_commit") != review["audited_commit"] or parent.get("audited_source_sha256") != review["audited_source_sha256"]:
            raise ValueError("stage-0 parent authorization audited content differs")
        if review.get("runtime_receipt_path") != self.payload["runtime_receipt"] or review.get("runtime_receipt_sha256") != self.payload["runtime_receipt_sha256"]:
            raise ValueError("stage-0 attestation runtime receipt binding differs")
        receipt, receipt_binding = _load_runtime_receipt_for_plan(self.payload)
        if receipt_binding != review["runtime_receipt_sha256"]:
            raise ValueError("stage-0 attestation runtime receipt content hash differs")
        expected_audited_sources = {label: entry["sha256"] for label, entry in _expected_source_records(receipt.payload).items()}
        if review.get("audited_source_sha256") != expected_audited_sources:
            raise ValueError("stage-0 attestation audited source hashes differ from loaded receipt")
        expected_capability_evidence = receipt.payload["provenance"]["capability_evidence"]
        if review.get("capability_evidence") != expected_capability_evidence:
            raise ValueError("stage-0 attestation capability evidence differs from runtime receipt")
        declared_evidence = _repo_relative_path(review.get("canary_evidence_path"), "review.canary_evidence_path")
        declared_sidecar = _repo_relative_path(review.get("canary_sidecar_path"), "review.canary_sidecar_path")
        if declared_evidence.name != evidence_path.name or declared_sidecar.name != sidecar_path.name:
            raise ValueError("stage-0 review artifact paths do not match supplied evidence")
        evidence_bytes = evidence_path.read_bytes()
        sidecar_bytes = sidecar_path.read_bytes()
        evidence_digest = hashlib.sha256(evidence_bytes).hexdigest()
        sidecar_digest = hashlib.sha256(sidecar_bytes).hexdigest()
        if expected_evidence_sha256 is not None and evidence_digest != expected_evidence_sha256:
            raise ValueError("canary evidence digest differs")
        if expected_sidecar_sha256 is not None and sidecar_digest != expected_sidecar_sha256:
            raise ValueError("canary sidecar digest differs")
        if review.get("canary_evidence_sha256") != evidence_digest or review.get("canary_sidecar_sha256") != sidecar_digest:
            raise ValueError("stage-0 review artifact evidence digests differ")
        evidence, _ = _read_json(evidence_path, "canary evidence")
        sidecar, _ = _read_json(sidecar_path, "canary sidecar")
        if sidecar.get("artifact_sha256") != evidence_digest or sidecar.get("artifact_bytes") != len(evidence_bytes) or sidecar.get("artifact_mode") != "0444":
            raise ValueError("stage-0 sidecar artifact binding is invalid")
        expected_sidecar_fields = {
            "plan_sha256": self.plan_sha256,
            "stage": STAGE_CANARY,
            "run_id": run_id,
            "previous_cursor": 0,
            "last_completed_game": self.canary_games_all_arms,
            "sealed": True,
            "native_launch_authorized": False,
        }
        for field, expected in expected_sidecar_fields.items():
            if sidecar.get(field) != expected:
                raise ValueError(f"stage-0 sidecar field {field} is invalid")
        if sidecar.get("artifact_name") != evidence_path.name or sidecar.get("sidecar_name") != sidecar_path.name:
            raise ValueError("stage-0 sidecar artifact names differ")
        source_receipts = sidecar.get("source_receipts")
        provenance = evidence.get("metric_provenance")
        if not isinstance(provenance, Mapping):
            raise ValueError("stage-0 evidence metric provenance is missing")
        self._validate_source_receipt_pointer(source_receipts, provenance, artifact_root=root)
        process_manifest, _ = self._validate_manifest_binding(provenance, stage=STAGE_CANARY, run_id=run_id, artifact_root=root)
        if process_manifest.payload.get("native_engine_loaded") is not True:
            raise ValueError("stage-0 independent review requires a process manifest with native engine loaded")
        metrics = self._validate_records(evidence, STAGE_CANARY, self.canary_games_all_arms, run_id=run_id, artifact_root=root)
        self._validate_gate_metrics(metrics, STAGE_CANARY)
        gate = self._recompute_reliability_gate(evidence, metrics)
        metric_digest = sha256_json(evidence["metric_provenance"])
        if sidecar.get("metric_provenance_sha256") != metric_digest or sidecar.get("reliability_gate_pass") is not gate:
            raise ValueError("stage-0 sidecar derived evidence fields differ")
        if not gate or review.get("reliability_gate_pass") is not True or review.get("metric_provenance_sha256") != metric_digest:
            raise ValueError("stage-0 evidence did not pass the recomputed reliability gate")
        return review

    def verify_canary_review(self, receipt: Mapping[str, Any], *, artifact_root: str | Path | None = None) -> Mapping[str, Any]:
        if not isinstance(receipt, Mapping):
            raise ValueError("stage-0 independent review receipt must be a mapping of artifact references")
        required = {
            "review_artifact_path",
            "review_artifact_sha256",
            "canary_evidence_path",
            "canary_evidence_sha256",
            "canary_sidecar_path",
            "canary_sidecar_sha256",
            "parent_authorization_path",
            "parent_authorization_sha256",
        }
        if not required.issubset(receipt):
            raise ValueError("stage-0 review receipt must reference sealed artifacts")
        if not all(_is_digest(receipt.get(field)) for field in ("review_artifact_sha256", "canary_evidence_sha256", "canary_sidecar_sha256", "parent_authorization_sha256")):
            raise ValueError("stage-0 review receipt artifact digests are malformed")
        for field in ("review_artifact_path", "canary_evidence_path", "canary_sidecar_path", "parent_authorization_path"):
            _repo_relative_path(receipt.get(field), field)
        review = self.verify_stage0_artifacts(
            receipt["review_artifact_path"],
            receipt["canary_evidence_path"],
            receipt["canary_sidecar_path"],
            artifact_root=artifact_root,
            expected_review_sha256=receipt["review_artifact_sha256"],
            expected_evidence_sha256=receipt["canary_evidence_sha256"],
            expected_sidecar_sha256=receipt["canary_sidecar_sha256"],
        )
        if review.get("canary_evidence_path") != receipt["canary_evidence_path"] or review.get("canary_sidecar_path") != receipt["canary_sidecar_path"]:
            raise ValueError("stage-0 review receipt path lineage differs")
        if review.get("parent_authorization_path") != receipt["parent_authorization_path"] or review.get("parent_authorization_sha256") != receipt["parent_authorization_sha256"]:
            raise ValueError("stage-0 review receipt parent authorization lineage differs")
        return review

    def arm_matrix(
        self,
        stage: str = STAGE_CANARY,
        *,
        canary_review: Mapping[str, Any] | None = None,
        artifact_root: str | Path | None = None,
    ) -> tuple[dict[str, Any], ...]:
        if stage == STAGE_SCREEN:
            if canary_review is None:
                raise ValueError("192-game screen is inaccessible without stage-0 review receipt")
            self.verify_canary_review(canary_review, artifact_root=artifact_root)
        per_cell = int(self._stage(stage)["games_per_cell"])
        return tuple(
            {
                "arm": arm,
                "anchor": anchor,
                "candidate_seat": seat,
                "games": per_cell,
                "natural_deployment": True,
            }
            for arm in self.arms
            for anchor in self.anchors
            for seat in (0, 1)
        )

    def _validate_records(
        self,
        raw_evidence: Mapping[str, Any],
        stage: str,
        last_completed_game: int,
        *,
        canary_review: Mapping[str, Any] | None = None,
        run_id: str | None = None,
        artifact_root: str | Path | None = None,
    ) -> ComponentRuntimeMetricsV1:
        self._stage(stage)
        if raw_evidence.get("stage") != stage:
            raise ValueError("sealed evidence stage does not match the requested stage")
        self._validate_metric_provenance(raw_evidence, stage, run_id=run_id, artifact_root=artifact_root)
        games = raw_evidence.get("games")
        if not isinstance(games, list) or len(games) != last_completed_game:
            raise ValueError("sealed evidence must retain exactly one record per completed game")
        expected = self.arm_matrix(stage, canary_review=canary_review, artifact_root=artifact_root)
        allowed = {(cell["arm"], cell["anchor"], cell["candidate_seat"]): cell["games"] for cell in expected}
        counts: dict[tuple[Any, ...], int] = {}
        seen: set[int] = set()
        for item in games:
            if not isinstance(item, dict) or not isinstance(item.get("game_index"), int) or item["game_index"] in seen:
                raise ValueError("sealed evidence game indices are not unique integers")
            seen.add(item["game_index"])
            if item["game_index"] < 0 or item["game_index"] >= last_completed_game:
                raise ValueError("sealed evidence game index is outside the resume cursor")
            key = (item.get("arm"), item.get("anchor"), item.get("candidate_seat"))
            if key not in allowed:
                raise ValueError("sealed evidence contains an undeclared arm/anchor/seat cell")
            counts[key] = counts.get(key, 0) + 1
            if counts[key] > allowed[key]:
                raise ValueError("sealed evidence exceeds the exact cell budget")
        if seen != set(range(last_completed_game)):
            raise ValueError("sealed evidence game records are not contiguous")
        if last_completed_game == int(self._stage(stage)["games_all_arms"]):
            if counts != {key: value for key, value in allowed.items()}:
                raise ValueError("complete sealed evidence does not cover every arm/anchor/seat cell")
        metrics_value = raw_evidence.get("runtime_metrics")
        if not isinstance(metrics_value, dict):
            raise ValueError("sealed evidence is missing runtime metrics")
        metrics = ComponentRuntimeMetricsV1.from_mapping(metrics_value)
        if metrics.game_count != last_completed_game:
            raise ValueError("runtime metric game count does not match retained game records")
        return metrics

    def _validate_gate_metrics(self, metrics: ComponentRuntimeMetricsV1, stage: str) -> None:
        metrics.validate(min_p99_samples=self.p99_min_samples)
        if metrics.p99_latency_ms > 100.0:
            raise ValueError("component p99 latency exceeds experiment-local budget")
        if metrics.game_count > 0 and metrics.component_cpu_seconds / metrics.game_count > 1.0:
            raise ValueError("component CPU per game exceeds experiment-local budget")
        if metrics.peak_rss_bytes > 536870912:
            raise ValueError("component RSS exceeds experiment-local budget")
        expected_games = self.canary_games_all_arms if stage == STAGE_CANARY else self.games_all_arms
        if metrics.game_count < 0 or metrics.game_count > expected_games:
            raise ValueError("runtime metric game count exceeds stage budget")
        if metrics.game_count > 0 and metrics.request_count < metrics.game_count:
            raise ValueError("runtime request cardinality is below completed-game count")
        if set(metrics.per_arm) != set(self.arms) or set(metrics.per_seat) != {"0", "1"}:
            raise ValueError("per-arm/per-seat metric keys are incomplete")
        if sum(metrics.per_arm.values()) != metrics.game_count or sum(metrics.per_seat.values()) != metrics.game_count:
            raise ValueError("per-arm/per-seat metrics do not reconcile to game count")

    def _validate_source_receipt_pointer(
        self,
        source_receipts: Mapping[str, Any],
        provenance: Mapping[str, Any],
        *,
        artifact_root: Path,
    ) -> None:
        if not isinstance(source_receipts, Mapping) or set(source_receipts) != _SOURCE_RECEIPT_FIELDS:
            raise ValueError("source receipts must be the typed source-manifest pointer")
        source_manifest_path = source_receipts.get("source_manifest_path")
        source_manifest_sha256 = source_receipts.get("source_manifest_sha256")
        _repo_relative_path(source_manifest_path, "source_receipts.source_manifest_path")
        if not _is_digest(source_manifest_sha256):
            raise ValueError("source receipt manifest digest is malformed")
        if source_manifest_path != provenance.get("source_manifest_path") or source_manifest_sha256 != provenance.get("source_manifest_sha256"):
            raise ValueError("source receipt pointer differs from metric provenance")
        manifest_path = _artifact_path(artifact_root, source_manifest_path, "source_receipts.source_manifest_path")
        if not manifest_path.is_file() or hashlib.sha256(manifest_path.read_bytes()).hexdigest() != source_manifest_sha256:
            raise ValueError("source manifest receipt path/hash does not resolve to the retained artifact")

    def seal_evidence(
        self,
        *,
        run_id: str,
        raw_evidence: Mapping[str, Any],
        source_receipts: Mapping[str, Any],
        last_completed_game: int,
        raw_artifact_path: str | Path,
        sidecar_path: str | Path | None = None,
        stage: str = STAGE_CANARY,
        previous_cursor: int = 0,
        canary_review: Mapping[str, Any] | None = None,
        previous_envelope: Mapping[str, Any] | None = None,
        artifact_root: str | Path | None = None,
    ) -> dict[str, Any]:
        if not run_id or "/" in run_id or "\\" in run_id:
            raise ValueError("run_id must be a bounded local identifier")
        if previous_cursor < 0 or last_completed_game < previous_cursor:
            raise ValueError("resume cursor is not monotonic")
        if previous_cursor == 0 and previous_envelope is not None:
            raise ValueError("a new run must not carry a previous envelope")
        if previous_cursor > 0:
            if previous_envelope is None:
                raise ValueError("a nonzero resume cursor requires a previous sealed envelope")
            if previous_envelope.get("sealed") is not True or previous_envelope.get("native_launch_authorized") is not False or previous_envelope.get("reliability_gate_pass") is not True:
                raise ValueError("resume previous envelope is not a passing sealed receipt")
            if previous_envelope.get("run_id") != run_id or previous_envelope.get("stage") != stage or previous_envelope.get("plan_sha256") != self.plan_sha256:
                raise ValueError("resume run/stage/plan lineage differs")
            if previous_envelope.get("source_receipts") != dict(sorted(source_receipts.items())):
                raise ValueError("resume source lineage differs")
            if previous_envelope.get("last_completed_game") != previous_cursor:
                raise ValueError("resume cursor does not continue the previous envelope")
        stage_budget = int(self._stage(stage)["games_all_arms"])
        if last_completed_game < 0 or last_completed_game > stage_budget:
            raise ValueError("resume cursor is outside the exact stage budget")
        manifest_root = Path(artifact_root).resolve() if artifact_root is not None else Path(raw_artifact_path).resolve().parent
        provenance = raw_evidence.get("metric_provenance")
        if not isinstance(provenance, Mapping):
            raise ValueError("sealed evidence is missing metric provenance")
        self._validate_source_receipt_pointer(source_receipts, provenance, artifact_root=manifest_root)
        metrics = self._validate_records(raw_evidence, stage, last_completed_game, canary_review=canary_review, run_id=run_id, artifact_root=manifest_root)
        self._validate_gate_metrics(metrics, stage)
        reliability_gate_pass = self._recompute_reliability_gate(raw_evidence, metrics)
        metric_provenance_sha256 = sha256_json(raw_evidence["metric_provenance"])
        artifact = Path(raw_artifact_path)
        sidecar = Path(sidecar_path) if sidecar_path is not None else Path(f"{artifact}.sha256.json")
        artifact_name = _safe_name(artifact.name, "raw_artifact_path")
        sidecar_name = _safe_name(sidecar.name, "sidecar_path")
        raw_bytes = _canonical(raw_evidence)
        raw_digest = hashlib.sha256(raw_bytes).hexdigest()
        sidecar_payload = {
            "schema_version": 1,
            "artifact_name": artifact_name,
            "sidecar_name": sidecar_name,
            "artifact_sha256": raw_digest,
            "artifact_bytes": len(raw_bytes),
            "artifact_mode": "0444",
            "plan_sha256": self.plan_sha256,
            "stage": stage,
            "run_id": run_id,
            "previous_cursor": previous_cursor,
            "last_completed_game": last_completed_game,
            "source_receipts": dict(sorted(source_receipts.items())),
            "process_manifest_path": provenance["process_manifest_path"],
            "process_manifest_sha256": provenance["process_manifest_sha256"],
            "source_manifest_path": provenance["source_manifest_path"],
            "source_manifest_sha256": provenance["source_manifest_sha256"],
            "sealed": True,
            "native_launch_authorized": False,
            "metric_provenance_sha256": metric_provenance_sha256,
            "reliability_gate_pass": reliability_gate_pass,
        }
        sidecar_bytes = _canonical(sidecar_payload)
        _write_read_only(artifact, raw_bytes)
        _write_read_only(sidecar, sidecar_bytes)
        return {
            **sidecar_payload,
            "sidecar_name": sidecar_name,
            "sidecar_sha256": hashlib.sha256(sidecar_bytes).hexdigest(),
            "raw_evidence_sha256": raw_digest,
            "metric_provenance_sha256": metric_provenance_sha256,
            "reliability_gate_pass": reliability_gate_pass,
            "screen_unlocked": False,
        }

    def verify_resume(
        self,
        envelope: Mapping[str, Any],
        *,
        source_receipts: Mapping[str, Any],
        raw_artifact_path: str | Path,
        sidecar_path: str | Path,
        previous_envelope: Mapping[str, Any] | None = None,
        canary_review: Mapping[str, Any] | None = None,
        artifact_root: str | Path | None = None,
    ) -> None:
        if envelope.get("sealed") is not True or envelope.get("native_launch_authorized") is not False:
            raise ValueError("B1 resume envelope is not sealed or is launch-authorizing")
        run_id = envelope.get("run_id")
        if not isinstance(run_id, str) or not run_id or "/" in run_id or "\\" in run_id:
            raise ValueError("B1 resume run_id is malformed")
        if envelope.get("plan_sha256") != self.plan_sha256:
            raise ValueError("B1 resume plan digest differs")
        if envelope.get("source_receipts") != dict(sorted(source_receipts.items())):
            raise ValueError("B1 resume source receipts differ")
        stage = envelope.get("stage")
        cursor = envelope.get("last_completed_game")
        previous_cursor = envelope.get("previous_cursor")
        if isinstance(cursor, bool) or not isinstance(cursor, int) or not 0 <= cursor <= int(self._stage(stage)["games_all_arms"]):
            raise ValueError("B1 resume cursor is invalid")
        if isinstance(previous_cursor, bool) or not isinstance(previous_cursor, int) or not 0 <= previous_cursor <= cursor:
            raise ValueError("B1 resume cursor is not monotonic")
        if previous_envelope is None:
            if previous_cursor != 0:
                raise ValueError("a new run cannot carry a nonzero resume cursor")
        else:
            if previous_cursor == 0:
                raise ValueError("a supplied previous envelope requires a nonzero resume cursor")
            if previous_envelope.get("sealed") is not True or previous_envelope.get("native_launch_authorized") is not False or previous_envelope.get("reliability_gate_pass") is not True:
                raise ValueError("B1 previous envelope is not a passing sealed receipt")
            if cursor < int(previous_envelope.get("last_completed_game", 0)):
                raise ValueError("B1 resume cursor moved backwards")
            if previous_envelope.get("run_id") != run_id or previous_envelope.get("stage") != stage or previous_envelope.get("plan_sha256") != self.plan_sha256:
                raise ValueError("B1 resume run/stage/plan lineage differs")
            if previous_envelope.get("source_receipts") != dict(sorted(source_receipts.items())) or previous_envelope.get("last_completed_game") != previous_cursor:
                raise ValueError("B1 resume source/cursor lineage differs")
        manifest_root = Path(artifact_root).resolve() if artifact_root is not None else Path(raw_artifact_path).resolve().parent
        if stage == STAGE_SCREEN:
            if canary_review is None:
                raise ValueError("B1 screen resume requires stage-0 review receipt")
            self.verify_canary_review(canary_review, artifact_root=artifact_root)
        artifact = Path(raw_artifact_path)
        sidecar = Path(sidecar_path)
        if _safe_name(artifact.name, "raw_artifact_path") != envelope.get("artifact_name") or _safe_name(sidecar.name, "sidecar_path") != envelope.get("sidecar_name"):
            raise ValueError("B1 resume artifact names differ")
        if stat.S_IMODE(artifact.stat().st_mode) & 0o222:
            raise ValueError("B1 raw evidence artifact is writable")
        if stat.S_IMODE(sidecar.stat().st_mode) & 0o222:
            raise ValueError("B1 sidecar is writable")
        raw_bytes = artifact.read_bytes()
        if hashlib.sha256(raw_bytes).hexdigest() != envelope.get("raw_evidence_sha256"):
            raise ValueError("B1 raw evidence digest differs")
        try:
            raw_evidence = json.loads(raw_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("B1 raw evidence is not valid JSON") from error
        if not isinstance(raw_evidence, dict) or _canonical(raw_evidence) != raw_bytes:
            raise ValueError("B1 raw evidence is not canonically sealed")
        sidecar_payload, sidecar_bytes = _read_json(sidecar, "B1 sidecar")
        if hashlib.sha256(sidecar_bytes).hexdigest() != envelope.get("sidecar_sha256"):
            raise ValueError("B1 sidecar digest differs")
        if sidecar_payload.get("artifact_sha256") != envelope.get("raw_evidence_sha256") or sidecar_payload.get("artifact_bytes") != len(raw_bytes) or sidecar_payload.get("plan_sha256") != self.plan_sha256 or sidecar_payload.get("sealed") is not True:
            raise ValueError("B1 sidecar integrity check failed")
        for field in (
            "run_id",
            "stage",
            "previous_cursor",
            "last_completed_game",
            "source_receipts",
            "process_manifest_path",
            "process_manifest_sha256",
            "source_manifest_path",
            "source_manifest_sha256",
            "metric_provenance_sha256",
            "reliability_gate_pass",
        ):
            if sidecar_payload.get(field) != envelope.get(field):
                raise ValueError("B1 sidecar resume fields differ")
        provenance = raw_evidence.get("metric_provenance")
        if not isinstance(provenance, Mapping):
            raise ValueError("B1 raw evidence metric provenance is missing")
        self._validate_source_receipt_pointer(source_receipts, provenance, artifact_root=manifest_root)
        metrics = self._validate_records(raw_evidence, stage, cursor, canary_review=canary_review, run_id=run_id, artifact_root=manifest_root)
        self._validate_gate_metrics(metrics, stage)
        metric_provenance_sha256 = sha256_json(raw_evidence["metric_provenance"])
        if envelope.get("metric_provenance_sha256") != metric_provenance_sha256:
            raise ValueError("B1 metric provenance digest differs")
        reliability_gate_pass = self._recompute_reliability_gate(raw_evidence, metrics)
        if envelope.get("reliability_gate_pass") is not reliability_gate_pass:
            raise ValueError("B1 reliability gate metadata differs from retained evidence")
        if not reliability_gate_pass:
            raise ValueError("B1 evidence contains a reliability defect and cannot resume")


__all__ = [
    "B1ComponentPlanV1",
    "ComponentRuntimeMetricsV1",
    "DEFAULT_PLAN_PATH",
    "prepare_runtime_manifests",
    "ProcessRuntimeSamplerV1",
    "STAGE_CANARY",
    "STAGE_SCREEN",
    "sha256_json",
]
