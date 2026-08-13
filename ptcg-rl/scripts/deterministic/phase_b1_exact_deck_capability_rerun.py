"""Validate the blocked exact-production-deck B1 capability rerun plan.

This command is planning-only.  It loads the actual local ``deck.csv``,
checks its file and semantic multiset digests, validates all bounded proof and
provenance contracts, and never imports or launches the native engine.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "configs/deterministic/phase_b1_exact_deck_capability_rerun_v1.json"
_EXPECTED_ASSET_SCOPES = {
    "native_library": "OFFICIAL_ENGINE",
    "wrapper": "OFFICIAL_WRAPPER",
    "api": "OFFICIAL_API",
    "card_data": "OFFICIAL_CARD_DATA",
    "card_table": "VERSIONED_CARD_TABLE",
    "candidate_deck": "EXACT_PRODUCTION_DECK",
    "knowledge_base": "LOCAL_KNOWLEDGE_BASE",
}
_EXPECTED_SOURCE_PATHS = {
    "runner": "scripts/deterministic/phase_a_b1_capability_capsules_v1.py",
    "route_runner": "scripts/deterministic/phase_a_route_capsules_v1.py",
    "actions": "src/ptcg_rl/g1/actions.py",
    "models": "src/ptcg_rl/g1/models.py",
    "native": "src/ptcg_rl/g1/native.py",
    "semantic": "src/ptcg_rl/g1/semantic.py",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()


def load_deck(path: Path) -> list[int]:
    values: list[int] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        value = line.strip()
        if not value:
            continue
        try:
            card_id = int(value)
        except ValueError as error:
            raise ValueError(f"deck line {line_number} is not a numeric card id") from error
        if card_id <= 0:
            raise ValueError(f"deck line {line_number} is not positive")
        values.append(card_id)
    if len(values) != 60:
        raise ValueError(f"exact production deck must contain 60 cards, got {len(values)}")
    counts: dict[str, int] = {}
    for card_id in values:
        counts[str(card_id)] = counts.get(str(card_id), 0) + 1
    if any(card_id != "3" and count > 4 for card_id, count in counts.items()):
        raise ValueError("exact production deck exceeds four copies of a named card")
    return values


def _check_digest(path: Path, expected: Any, label: str) -> None:
    if not isinstance(expected, str) or len(expected) != 64:
        raise ValueError(f"{label} digest is malformed")
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(f"{label} digest mismatch: {actual}")


def _repo_relative_path(value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError(f"{label} must be a nonempty repository-relative path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{label} must stay inside the repository")
    return path


def load_plan(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    plan = json.loads(path.read_text(encoding="utf-8"))
    if plan.get("schema_version") != 1 or plan.get("record_id") != "phase-b1-exact-deck-capability-rerun-v1":
        raise ValueError("exact-deck plan identity changed")
    if plan.get("status") != "BLOCKED_PENDING_INDEPENDENT_TECHNICAL_REVIEW" or plan.get("scope") != "NATIVE_QUALIFIED_CANDIDATE":
        raise ValueError("exact-deck plan must remain blocked capability-only scope")
    candidate = plan.get("candidate_deck")
    if not isinstance(candidate, dict):
        raise ValueError("exact-deck candidate declaration is missing")
    deck_path = ROOT / _repo_relative_path(candidate.get("path"), "candidate_deck.path")
    _check_digest(deck_path, candidate.get("file_sha256"), "candidate deck file")
    deck = load_deck(deck_path)
    expected_multiset = {str(key): int(value) for key, value in candidate.get("multiset", {}).items()}
    actual_multiset: dict[str, int] = {}
    for card_id in deck:
        actual_multiset[str(card_id)] = actual_multiset.get(str(card_id), 0) + 1
    if actual_multiset != expected_multiset or canonical_hash(sorted(deck)) != candidate.get("semantic_multiset_sha256"):
        raise ValueError("candidate deck semantic multiset differs from exact plan")
    if candidate.get("count") != len(deck):
        raise ValueError("candidate deck count differs from exact plan")
    assets = plan.get("assets")
    if not isinstance(assets, dict) or set(assets) != set(_EXPECTED_ASSET_SCOPES):
        raise ValueError("exact-deck asset declarations are not the enumerated set")
    for label, asset in assets.items():
        if not isinstance(asset, dict) or not isinstance(asset.get("path"), str):
            raise ValueError(f"asset declaration is malformed: {label}")
        if asset.get("scope") != _EXPECTED_ASSET_SCOPES[label]:
            raise ValueError(f"asset scope is not the enumerated value: {label}")
        asset_path = ROOT / _repo_relative_path(asset["path"], f"assets.{label}.path")
        _check_digest(asset_path, asset.get("sha256"), label)
    if plan["assets"]["knowledge_base"].get("sha256") != plan["knowledge_base"].get("sha256") or plan["assets"]["knowledge_base"].get("path") != plan["knowledge_base"].get("path"):
        raise ValueError("knowledge-base duplicate declarations differ")
    table = json.loads((ROOT / _repo_relative_path(plan["assets"]["card_table"]["path"], "assets.card_table.path")).read_text(encoding="utf-8"))
    if table.get("table_sha256") != plan["assets"]["card_table"].get("semantic_sha256"):
        raise ValueError("card-table semantic digest differs from exact plan")
    kb = plan["knowledge_base"]
    _check_digest(ROOT / _repo_relative_path(kb.get("path"), "knowledge_base.path"), kb.get("sha256"), "knowledge base")
    source_paths = plan["provenance"]["source_paths"]
    source_hashes = plan["provenance"]["source_sha256"]
    if set(source_paths) != set(source_hashes) or source_paths != _EXPECTED_SOURCE_PATHS:
        raise ValueError("source path/hash receipt is not the enumerated set")
    for label, source_path in source_paths.items():
        _check_digest(ROOT / _repo_relative_path(source_path, f"source_paths.{label}"), source_hashes[label], f"source {label}")
    if plan["provenance"]["scope_labels"] != {
        "capability": "NATIVE_QUALIFIED_CANDIDATE",
        "policy_integration": "NOT_ESTABLISHED",
        "outcome_promotion": "NOT_ESTABLISHED",
    }:
        raise ValueError("capability and integration scopes are conflated")
    limits = plan["limits"]
    if limits["request_cap_per_game"] > 900 or limits["wall_seconds"] > 600 or limits["evidence_bytes_cap"] > 67108864:
        raise ValueError("exact-deck plan exceeds reviewed capability caps")
    if plan["stop_conditions"]["stop_on_any_reliability_counter"] is not True or plan["stop_conditions"]["native_launch"] is not False:
        raise ValueError("exact-deck stop/launch conditions changed")
    if plan["launch_gate"]["status"] != "BLOCKED" or plan["launch_gate"]["native_run_performed"] is not False:
        raise ValueError("exact-deck plan launch gate is open")
    return plan


def plan_summary(plan: Mapping[str, Any], config_path: Path) -> dict[str, Any]:
    deck = plan["candidate_deck"]
    return {
        "record_id": plan["record_id"],
        "status": plan["status"],
        "scope": plan["scope"],
        "config_sha256": sha256_file(config_path),
        "candidate_deck_file_sha256": deck["file_sha256"],
        "candidate_deck_semantic_multiset_sha256": deck["semantic_multiset_sha256"],
        "candidate_deck_count": deck["count"],
        "proof_goals": [row["id"] for row in plan["formulations"]],
        "request_cap_per_game": plan["limits"]["request_cap_per_game"],
        "wall_seconds": plan["limits"]["wall_seconds"],
        "native_launch_authorized": False,
        "capability_evidence_available": False,
        "policy_integration_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the blocked exact-deck B1 capability rerun plan (native launch remains blocked).")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    config_path = args.config.resolve()
    plan = load_plan(config_path)
    print(json.dumps(plan_summary(plan, config_path), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
