"""Preflight the separately addressable exact-deck B1 capability run.

The historical Phase A runner and its report are evidence records, not output
targets for this execution package.  This module reuses the Phase A asset and
deck-spec helpers during a read-only preflight, but it deliberately never calls
``run_experiment`` or constructs a native transport.  Native execution needs
a separate, independently reviewed launch receipt and a new reviewed config.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_CONFIG = ROOT / "configs/deterministic/phase_b1_exact_deck_capability_execution_v2.json"
DEFAULT_REPORT = ROOT / "reports/deterministic/phase-b1-exact-deck-capability-execution-v2.json"
DEFAULT_RAW = ROOT / "reports/deterministic/phase-b1-exact-deck-capability-execution-v2.raw.json"
HISTORICAL_CONFIG = ROOT / "configs/deterministic/phase_b1_exact_deck_capability_rerun_v1.json"
HISTORICAL_REPORT = ROOT / "reports/deterministic/phase-b1-exact-deck-capability-rerun-v1.json"
HISTORICAL_RAW = ROOT / "reports/deterministic/phase-b1-exact-deck-capability-rerun-v1.raw.json"
EXECUTOR_PATH = Path(__file__).relative_to(ROOT)

EXPECTED_RECORD_ID = "phase-b1-exact-deck-capability-execution-v2"
EXPECTED_RUN_ID = "phase-b1-exact-deck-capability-execution-v2-20260808T000000Z"
EXPECTED_ASSET_SCOPES = {
    "native_library": "OFFICIAL_ENGINE",
    "wrapper": "OFFICIAL_WRAPPER",
    "api": "OFFICIAL_API",
    "card_data": "OFFICIAL_CARD_DATA",
    "card_table": "VERSIONED_CARD_TABLE",
    "candidate_deck": "EXACT_PRODUCTION_DECK",
    "knowledge_base": "LOCAL_KNOWLEDGE_BASE",
}
EXPECTED_SOURCE_PATHS = {
    "runner": "scripts/deterministic/phase_a_b1_capability_capsules_v1.py",
    "route_runner": "scripts/deterministic/phase_a_route_capsules_v1.py",
    "actions": "src/ptcg_rl/g1/actions.py",
    "models": "src/ptcg_rl/g1/models.py",
    "native": "src/ptcg_rl/g1/native.py",
    "semantic": "src/ptcg_rl/g1/semantic.py",
}
RELIABILITY_COUNTERS = (
    "invalid_actions",
    "semantic_contract_failures",
    "request_cap_failures",
    "timeouts",
    "native_errors",
    "fallbacks",
    "post_terminal_actions",
    "unclassified_terminal",
    "incomplete_games",
    "other_failures",
    "ambiguous_prize_pairings",
)
EXPECTED_SCOPE_LABELS = {
    "capability": "NATIVE_QUALIFIED_CANDIDATE",
    "policy_integration": "NOT_ESTABLISHED",
    "outcome_promotion": "NOT_ESTABLISHED",
}
EXPECTED_OUTPUT_PATHS = {
    "report_path": "reports/deterministic/phase-b1-exact-deck-capability-execution-v2.json",
    "raw_path": "reports/deterministic/phase-b1-exact-deck-capability-execution-v2.raw.json",
    "report_sidecar_path": "reports/deterministic/phase-b1-exact-deck-capability-execution-v2.json.sha256",
    "raw_sidecar_path": "reports/deterministic/phase-b1-exact-deck-capability-execution-v2.raw.json.sha256",
}
HISTORICAL_PATHS = frozenset(
    {
        str(HISTORICAL_CONFIG.relative_to(ROOT)),
        str(HISTORICAL_REPORT.relative_to(ROOT)),
        str(HISTORICAL_RAW.relative_to(ROOT)),
    }
)
RUN_ID_PATTERN = re.compile(r"^phase-b1-exact-deck-capability-execution-v2-20260808T000000Z$")


class PreflightError(ValueError):
    """The execution package is not bound to its reviewed inputs."""


class LaunchBlocked(RuntimeError):
    """The requested native action is not authorized by this package."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _same(left: Any, right: Any) -> bool:
    return canonical_hash(left) == canonical_hash(right)


def _repo_relative(value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise PreflightError(f"{label} must be a nonempty repository-relative path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or path == Path("."):
        raise PreflightError(f"{label} must stay inside the repository")
    return path


def _repo_file(value: Any, label: str) -> Path:
    relative = _repo_relative(value, label)
    path = ROOT / relative
    if not path.is_file():
        raise PreflightError(f"{label} does not name a file: {relative}")
    return path


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise PreflightError(f"{label} digest is malformed")
    return value


def _check_digest(path: Path, expected: Any, label: str) -> str:
    expected_digest = _digest(expected, label)
    actual = sha256_file(path)
    if actual != expected_digest:
        raise PreflightError(f"{label} digest mismatch: expected {expected_digest}, got {actual}")
    return actual


def _normalise_spec(value: Any, label: str) -> dict[str, int]:
    if not isinstance(value, Mapping) or not value:
        raise PreflightError(f"{label} must be a nonempty card-count mapping")
    result: dict[str, int] = {}
    for key, count in value.items():
        if not isinstance(key, str) or not key.isdigit() or str(int(key)) != key:
            raise PreflightError(f"{label} contains a non-canonical card id")
        if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
            raise PreflightError(f"{label}.{key} must be a positive integer count")
        if int(key) != 3 and count > 4:
            raise PreflightError(f"{label}.{key} exceeds the four-copy named-card limit")
        result[key] = count
    if sum(result.values()) != 60:
        raise PreflightError(f"{label} must contain exactly 60 cards")
    return result


def _deck_spec(deck: list[int]) -> dict[str, int]:
    return {key: count for key, count in sorted(Counter(str(value) for value in deck).items(), key=lambda item: int(item[0]))}


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PreflightError(f"could not load {label}: {path}") from error
    if not isinstance(value, dict):
        raise PreflightError(f"{label} must be a JSON object")
    return value


def load_execution_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    """Load and validate the immutable identity/shape of the new config."""

    path = path.resolve()
    try:
        path.relative_to(ROOT)
    except ValueError as error:
        raise PreflightError("execution config must be inside the repository") from error
    config = _load_json(path, "execution config")
    expected_keys = {
        "schema_version", "record_id", "status", "scope", "purpose", "base_plan", "executor", "run_identity",
        "candidate_deck", "assets", "knowledge_base", "route_capsule", "formulations",
        "phase_a_compatibility", "limits", "stop_conditions", "provenance", "output",
        "reviewed_launch_receipt", "launch_gate",
    }
    if set(config) != expected_keys:
        raise PreflightError("execution config keys differ from the versioned contract")
    if config["schema_version"] != 2 or config["record_id"] != EXPECTED_RECORD_ID:
        raise PreflightError("execution config identity changed")
    if config["status"] != "BLOCKED_PENDING_INDEPENDENT_TECHNICAL_REVIEW" or config["scope"] != "NATIVE_QUALIFIED_CANDIDATE":
        raise PreflightError("execution config must remain blocked capability-only scope")
    return config


def _load_base_plan(config: Mapping[str, Any]) -> tuple[dict[str, Any], Path]:
    from scripts.deterministic.phase_b1_exact_deck_capability_rerun import load_plan

    binding = config["base_plan"]
    if not isinstance(binding, Mapping):
        raise PreflightError("base_plan binding is missing")
    if binding.get("record_id") != "phase-b1-exact-deck-capability-rerun-v1":
        raise PreflightError("base plan record identity differs")
    plan_path = _repo_file(binding.get("path"), "base_plan.path")
    if plan_path != HISTORICAL_CONFIG:
        raise PreflightError("execution config must bind the immutable historical v1 plan")
    _check_digest(plan_path, binding.get("sha256"), "base plan")
    try:
        plan = load_plan(plan_path)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise PreflightError("historical exact-deck plan failed its own validation") from error
    return plan, plan_path


def _validate_executor(config: Mapping[str, Any]) -> str:
    executor = config.get("executor")
    if not isinstance(executor, Mapping) or executor.get("scope") != "B1_OWNED_PREFLIGHT_EXECUTOR":
        raise PreflightError("executor provenance binding is missing")
    if executor.get("path") != str(EXECUTOR_PATH):
        raise PreflightError("executor path differs from the versioned preflight entry point")
    path = _repo_file(executor.get("path"), "executor.path")
    return _check_digest(path, executor.get("sha256"), "executor")


def _validate_candidate(config: Mapping[str, Any], plan: Mapping[str, Any]) -> dict[str, Any]:
    candidate = config.get("candidate_deck")
    planned = plan.get("candidate_deck")
    if not isinstance(candidate, Mapping) or not isinstance(planned, Mapping):
        raise PreflightError("candidate deck binding is missing")
    for key in ("path", "file_sha256", "semantic_multiset_sha256", "count", "multiset"):
        if candidate.get(key) != planned.get(key):
            raise PreflightError(f"candidate deck binding differs from historical plan: {key}")
    if candidate.get("order_is_not_authority") is not True:
        raise PreflightError("candidate deck order must not be treated as semantic authority")
    deck_path = _repo_file(candidate.get("path"), "candidate_deck.path")
    from scripts.deterministic.phase_b1_exact_deck_capability_rerun import load_deck

    _check_digest(deck_path, candidate.get("file_sha256"), "candidate deck file")
    try:
        deck = load_deck(deck_path)
    except (OSError, ValueError, TypeError) as error:
        raise PreflightError("actual exact-production deck could not be loaded") from error
    actual_spec = _deck_spec(deck)
    expected_spec = _normalise_spec(candidate.get("multiset"), "candidate_deck.multiset")
    if actual_spec != expected_spec:
        raise PreflightError("actual exact-production deck multiset differs from config")
    if len(deck) != candidate.get("count") or canonical_hash(sorted(deck)) != candidate.get("semantic_multiset_sha256"):
        raise PreflightError("actual exact-production deck semantic digest differs from config")
    if canonical_hash(actual_spec) != candidate.get("deck_spec_sha256"):
        raise PreflightError("candidate deck spec digest is not recomputed from the actual file")
    asset = config["assets"].get("candidate_deck")
    if not isinstance(asset, Mapping) or asset.get("path") != candidate.get("path") or asset.get("sha256") != candidate.get("file_sha256"):
        raise PreflightError("candidate deck asset receipt is not duplicated consistently")
    return {"path": str(deck_path.relative_to(ROOT)), "file_sha256": sha256_file(deck_path), "semantic_multiset_sha256": canonical_hash(sorted(deck)), "count": len(deck), "multiset": actual_spec, "deck_spec_sha256": canonical_hash(actual_spec)}


def _validate_assets(config: Mapping[str, Any], plan: Mapping[str, Any]) -> dict[str, str]:
    assets = config.get("assets")
    planned = plan.get("assets")
    if not isinstance(assets, Mapping) or set(assets) != set(EXPECTED_ASSET_SCOPES) or not isinstance(planned, Mapping):
        raise PreflightError("asset declarations are not the enumerated set")
    if not _same(assets, planned):
        raise PreflightError("execution asset declarations differ from the immutable exact-deck plan")
    observed: dict[str, str] = {}
    for label, expected_scope in EXPECTED_ASSET_SCOPES.items():
        entry = assets[label]
        if not isinstance(entry, Mapping) or entry.get("scope") != expected_scope:
            raise PreflightError(f"asset scope is not the enumerated value: {label}")
        path = _repo_file(entry.get("path"), f"assets.{label}.path")
        observed[label] = _check_digest(path, entry.get("sha256"), label)
    top_level_kb = config.get("knowledge_base")
    if not isinstance(top_level_kb, Mapping):
        raise PreflightError("top-level knowledge-base declaration is missing")
    if assets["knowledge_base"].get("path") != top_level_kb.get("path") or assets["knowledge_base"].get("sha256") != top_level_kb.get("sha256"):
        raise PreflightError("knowledge-base asset and top-level declarations differ")
    table = _load_json(_repo_file(assets["card_table"]["path"], "assets.card_table.path"), "card table")
    if table.get("table_sha256") != assets["card_table"].get("semantic_sha256"):
        raise PreflightError("card-table semantic digest differs from receipt")
    kb = config["knowledge_base"]
    if not isinstance(kb, Mapping) or kb.get("path") != plan["knowledge_base"].get("path") or kb.get("sha256") != plan["knowledge_base"].get("sha256") or kb.get("ids") != plan["knowledge_base"].get("ids"):
        raise PreflightError("knowledge-base binding differs from the historical plan")
    _check_digest(_repo_file(kb.get("path"), "knowledge_base.path"), kb.get("sha256"), "knowledge base")

    # Delegate the static card-data/card-table contract to the proven Phase A
    # helper.  Its run_experiment entry point is intentionally never called.
    phase_a = importlib.import_module("scripts.deterministic.phase_a_b1_capability_capsules_v1")
    adapter = {
        "assets": {
            "card_data_sha256": assets["card_data"]["sha256"],
            "card_table_file_sha256": assets["card_table"]["sha256"],
            "card_table_semantic_sha256": assets["card_table"]["semantic_sha256"],
            "engine_library_sha256": assets["native_library"]["sha256"],
            "wrapper_sha256": assets["wrapper"]["sha256"],
            "api_sha256": assets["api"]["sha256"],
        }
    }
    try:
        delegated = phase_a.validate_assets(adapter, DEFAULT_CONFIG)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise PreflightError("Phase A static asset validation failed") from error
    return {**observed, "phase_a_static_validation": "PASS", "phase_a_observed": delegated}


def _validate_compatibility(config: Mapping[str, Any], plan: Mapping[str, Any], actual: Mapping[str, Any]) -> dict[str, Any]:
    compatibility = config.get("phase_a_compatibility")
    if not isinstance(compatibility, Mapping) or compatibility.get("schema_version") != 1:
        raise PreflightError("Phase A compatibility contract is missing")
    provenance = config.get("provenance")
    if not isinstance(provenance, Mapping):
        raise PreflightError("source provenance binding is missing")
    source_paths = provenance.get("source_paths")
    source_hashes = provenance.get("source_sha256")
    if not isinstance(source_paths, Mapping) or not isinstance(source_hashes, Mapping):
        raise PreflightError("source paths and hashes must be mappings")
    if compatibility.get("runner_path") != EXPECTED_SOURCE_PATHS["runner"] or compatibility.get("runner_sha256") != source_hashes.get("runner"):
        raise PreflightError("Phase A runner binding differs from the source receipt")
    if source_paths != plan["provenance"]["source_paths"] or source_hashes != plan["provenance"]["source_sha256"]:
        raise PreflightError("source paths/hashes differ from the immutable exact-deck plan")
    for label, relative in EXPECTED_SOURCE_PATHS.items():
        _check_digest(_repo_file(relative, f"source_paths.{label}"), source_hashes.get(label), f"source {label}")
    candidate_spec = _normalise_spec(compatibility.get("candidate_deck_spec"), "phase_a_compatibility.candidate_deck_spec")
    if candidate_spec != actual["multiset"] or canonical_hash(candidate_spec) != actual["deck_spec_sha256"]:
        raise PreflightError("Phase A candidate deck spec was not recomputed from the actual deck")
    deck_specs = compatibility.get("deck_specs")
    if not isinstance(deck_specs, Mapping):
        raise PreflightError("Phase A compatible deck specs are missing")
    expected_specs = {
        "candidate": actual["multiset"],
        "target_721": {"3": 56, "721": 4},
        "target_722": {"3": 56, "722": 4},
        "target_723": {"3": 52, "722": 4, "723": 4},
        "target_754": {"3": 56, "754": 4},
    }
    normalised_specs = {key: _normalise_spec(deck_specs.get(key), f"phase_a_compatibility.deck_specs.{key}") for key in expected_specs}
    if normalised_specs != expected_specs or canonical_hash(normalised_specs) != compatibility.get("deck_specs_sha256"):
        raise PreflightError("Phase A compatible deck specs differ from the exact route contract")
    if compatibility.get("formulation_ids") != [row["id"] for row in plan["formulations"]]:
        raise PreflightError("Phase A formulation binding differs from the exact plan")
    phase_a = importlib.import_module("scripts.deterministic.phase_a_b1_capability_capsules_v1")
    try:
        expanded = {key: len(phase_a.expand_deck(spec)) for key, spec in normalised_specs.items()}
    except (TypeError, ValueError, KeyError) as error:
        raise PreflightError("Phase A deck expansion rejected a compatible deck spec") from error
    return {"schema_version": 1, "expanded_card_counts": expanded, "candidate_spec_sha256": actual["deck_spec_sha256"]}


def _validate_output(config: Mapping[str, Any]) -> dict[str, str]:
    output = config.get("output")
    if not isinstance(output, Mapping):
        raise PreflightError("output binding is missing")
    for key, expected in EXPECTED_OUTPUT_PATHS.items():
        if output.get(key) != expected:
            raise PreflightError(f"output.{key} must use the new v2 destination")
        relative = _repo_relative(output[key], f"output.{key}")
        if str(relative) in HISTORICAL_PATHS:
            raise PreflightError(f"output.{key} cannot overwrite historical v1 evidence")
    if len({output[key] for key in EXPECTED_OUTPUT_PATHS}) != len(EXPECTED_OUTPUT_PATHS):
        raise PreflightError("report, raw evidence, and sidecar destinations must be unique")
    if output.get("overwrite_policy") != "REJECT_EXISTING_AND_NEVER_TOUCH_HISTORICAL_V1":
        raise PreflightError("output overwrite policy is not fail-closed")
    return {key: str(_repo_relative(value, f"output.{key}")) for key, value in EXPECTED_OUTPUT_PATHS.items()}


def _validate_receipt(config: Mapping[str, Any]) -> dict[str, Any]:
    receipt = config.get("reviewed_launch_receipt")
    if not isinstance(receipt, Mapping) or receipt.get("required") is not True:
        raise PreflightError("a separate reviewed launch receipt is required")
    receipt_relative = _repo_relative(receipt.get("path"), "reviewed_launch_receipt.path")
    receipt_path = ROOT / receipt_relative
    if str(receipt_path.relative_to(ROOT)) in HISTORICAL_PATHS or str(receipt_path.relative_to(ROOT)) in EXPECTED_OUTPUT_PATHS.values():
        raise PreflightError("reviewed launch receipt must be a separate destination")
    if receipt_path.exists() and not receipt_path.is_file():
        raise PreflightError("reviewed launch receipt path is not a regular file")
    if receipt_path.is_file():
        actual = _check_digest(receipt_path, receipt.get("sha256"), "reviewed launch receipt")
        payload = _load_json(receipt_path, "reviewed launch receipt")
        if payload.get("schema") != receipt.get("schema") or payload.get("status") != "PASS":
            raise PreflightError("reviewed launch receipt is not an independent PASS receipt")
        return {"path": str(receipt_path.relative_to(ROOT)), "available": True, "sha256": actual}
    if receipt.get("sha256") is not None:
        raise PreflightError("missing reviewed launch receipt cannot declare a digest")
    if receipt.get("status") != "MISSING_PENDING_INDEPENDENT_REVIEW":
        raise PreflightError("missing reviewed launch receipt status is not blocked")
    return {"path": str(receipt_path.relative_to(ROOT)), "available": False, "sha256": None}


def preflight(config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    """Recompute and return a read-only receipt for the exact-deck run."""

    config_path = config_path.resolve()
    config = load_execution_config(config_path)
    if config_path != DEFAULT_CONFIG:
        # Alternate configs are useful only for adversarial tests; they may not
        # redirect the production execution identity or output namespace.
        if config["record_id"] != EXPECTED_RECORD_ID:
            raise PreflightError("alternate config has an unexpected execution identity")
    plan, plan_path = _load_base_plan(config)
    executor_sha256 = _validate_executor(config)
    if config["scope"] != plan["scope"] or config["status"] != plan["status"]:
        raise PreflightError("execution and base-plan scope/status differ")
    actual_deck = _validate_candidate(config, plan)
    asset_hashes = _validate_assets(config, plan)
    compatibility = _validate_compatibility(config, plan, actual_deck)
    if not _same(config["route_capsule"], plan["route_capsule"]):
        raise PreflightError("route capsule differs from the immutable exact-deck plan")
    if not _same(config["formulations"], plan["formulations"]):
        raise PreflightError("formulations differ from the immutable exact-deck plan")
    if not _same(config["limits"], plan["limits"]):
        raise PreflightError("execution limits must remain exactly the reviewed caps")
    stops = config.get("stop_conditions")
    if not isinstance(stops, Mapping):
        raise PreflightError("stop conditions binding is missing")
    if not _same(stops, plan["stop_conditions"]):
        raise PreflightError("stop conditions differ from the immutable exact-deck plan")
    if stops.get("stop_on_any_reliability_counter") is not True or stops.get("required_zero_counters") != list(RELIABILITY_COUNTERS):
        raise PreflightError("execution must stop on every reliability defect")
    provenance = config.get("provenance")
    if not isinstance(provenance, Mapping) or provenance.get("scope_labels") != EXPECTED_SCOPE_LABELS:
        raise PreflightError("capability and integration scope labels changed")
    run_identity = config.get("run_identity")
    if not isinstance(run_identity, Mapping):
        raise PreflightError("run identity binding is missing")
    if run_identity.get("run_id") != EXPECTED_RUN_ID or not RUN_ID_PATTERN.fullmatch(str(run_identity.get("run_id"))):
        raise PreflightError("run identity is not the versioned exact-deck identity")
    if run_identity.get("native_games") != 0:
        raise PreflightError("preflight run identity cannot claim native games")
    output = _validate_output(config)
    if config["output"].get("run_id") != run_identity["run_id"]:
        raise PreflightError("output and run identities differ")
    receipt = _validate_receipt(config)
    gate = config.get("launch_gate")
    if not isinstance(gate, Mapping) or gate.get("status") != "BLOCKED" or gate.get("native_launch_authorized") is not False or gate.get("native_run_performed") is not False or gate.get("capability_evidence_available") is not False:
        raise PreflightError("native launch gate is not closed")
    if config["output"].get("report_kind") != "STANDALONE_BLOCKED_PLAN" or config["output"].get("raw_kind") != "PREFLIGHT_RECEIPT_ONLY":
        raise PreflightError("output artifacts are not plan-only")
    return {
        "schema_version": 2,
        "record_id": EXPECTED_RECORD_ID,
        "run_id": run_identity["run_id"],
        "status": "PREFLIGHT_PASS_LAUNCH_BLOCKED",
        "scope": config["scope"],
        "config_path": str(config_path.relative_to(ROOT)),
        "config_sha256": sha256_file(config_path),
        "base_plan_path": str(plan_path.relative_to(ROOT)),
        "base_plan_sha256": sha256_file(plan_path),
        "executor_path": str(EXECUTOR_PATH),
        "executor_sha256": executor_sha256,
        "candidate_deck": actual_deck,
        "assets": asset_hashes,
        "phase_a_compatibility": compatibility,
        "limits": dict(config["limits"]),
        "stop_conditions": dict(stops),
        "scope_labels": dict(provenance["scope_labels"]),
        "output": output,
        "reviewed_launch_receipt": receipt,
        "native_launch_authorized": False,
        "native_games": 0,
        "capability_evidence_available": False,
        "policy_integration_authorized": False,
    }


def execute(config_path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    """Refuse native execution until a separately reviewed gate is installed.

    This function intentionally has no native-engine call.  A future reviewed
    executor must be a new versioned package with an independently reviewed
    launch receipt; it must not turn this plan-only helper into an authority.
    """

    receipt = preflight(config_path)
    raise LaunchBlocked(
        "native execution is disabled: separate independent reviewed launch receipt is absent "
        f"for {receipt['run_id']}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight the blocked exact-production-deck B1 capability execution package.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--execute", action="store_true", help="prove that native execution remains blocked")
    args = parser.parse_args()
    try:
        result = execute(args.config) if args.execute else preflight(args.config)
    except (PreflightError, LaunchBlocked) as error:
        print(json.dumps({"status": "BLOCKED", "error": str(error)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
