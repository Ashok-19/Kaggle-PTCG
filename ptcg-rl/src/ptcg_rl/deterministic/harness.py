"""Evidence helpers and bounded runner for the Phase B deterministic canary.

The module deliberately keeps experiment arithmetic separate from native CABT
loading.  That makes the candidate-perspective calculations independently
testable and prevents a report from accidentally treating player-one results
as player-zero results.
"""

from __future__ import annotations

import json
import hashlib
import math
import random
import statistics
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from ptcg_rl.g1.actions import permute_request
from ptcg_rl.g1.evidence import sha256_file, write_immutable_json


B0_EXPERIMENT_ID = "B0-MA-CONTROL-001"
B0_SCHEMA_VERSION = 1
B0_BOOTSTRAP_RESAMPLES = 10_000
RELIABILITY_COUNTERS = (
    "invalid_selections",
    "fallback_actions",
    "post_terminal_actions",
    "timeouts",
    "failures",
    "incomplete_games",
    "missing_outputs",
)


def candidate_outcome(terminal_result: int | None, candidate_player: int) -> str:
    """Convert native result codes into the candidate's perspective."""
    if candidate_player not in (0, 1):
        raise ValueError("candidate_player must be 0 or 1")
    if terminal_result is None:
        return "incomplete"
    if terminal_result == 2:
        return "draw"
    if terminal_result not in (0, 1):
        raise ValueError(f"unknown native terminal result: {terminal_result}")
    return "win" if terminal_result == candidate_player else "loss"


def candidate_score(terminal_result: int | None, candidate_player: int) -> float | None:
    outcomes = {"win": 1.0, "draw": 0.5, "loss": 0.0}
    outcome = candidate_outcome(terminal_result, candidate_player)
    return outcomes.get(outcome)


def wilson_interval(successes: int, trials: int, z: float = 1.959963984540054) -> tuple[float, float]:
    """Return a two-sided Wilson interval for a binary rate."""
    if trials < 0 or successes < 0 or successes > trials:
        raise ValueError("Wilson counts must satisfy 0 <= successes <= trials")
    if trials == 0:
        return (0.0, 1.0)
    proportion = successes / trials
    denominator = 1.0 + z * z / trials
    center = (proportion + z * z / (2.0 * trials)) / denominator
    radius = z * math.sqrt(
        proportion * (1.0 - proportion) / trials + z * z / (4.0 * trials * trials)
    ) / denominator
    return (max(0.0, center - radius), min(1.0, center + radius))


def _percentile(values: Sequence[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    index = min(len(ordered) - 1, max(0, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def latency_summary(
    records: Iterable[Mapping[str, Any]], field: str = "action_latencies_ms"
) -> dict[str, float | int | None]:
    latencies = [
        float(value)
        for record in records
        for value in record.get(field, ())
        if math.isfinite(float(value)) and float(value) >= 0
    ]
    return {
        "count": len(latencies),
        "p50_ms": _percentile(latencies, 0.50),
        "p95_ms": _percentile(latencies, 0.95),
        "p99_ms": _percentile(latencies, 0.99),
        "mean_ms": statistics.fmean(latencies) if latencies else None,
        "max_ms": max(latencies) if latencies else None,
    }


def natural_seat_balance(records: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts = {"candidate_player_0": 0, "candidate_player_1": 0}
    for record in records:
        player = record.get("candidate_player")
        if player not in (0, 1):
            raise ValueError("every record must identify candidate_player as 0 or 1")
        counts[f"candidate_player_{player}"] += 1
    return counts


def bootstrap_score_delta(
    candidate_scores: Sequence[float],
    control_scores: Sequence[float],
    *,
    resamples: int = B0_BOOTSTRAP_RESAMPLES,
    seed: int = 17,
) -> dict[str, float | int | None]:
    """Bootstrap two independent score samples; never treats games as paired."""
    if resamples <= 0:
        raise ValueError("resamples must be positive")
    candidate = tuple(float(value) for value in candidate_scores)
    control = tuple(float(value) for value in control_scores)
    if not candidate or not control:
        return {
            "resamples": resamples,
            "seed": seed,
            "observed_delta": None,
            "percentile_2_5": None,
            "percentile_50": None,
            "percentile_97_5": None,
        }
    if any(not math.isfinite(value) for value in (*candidate, *control)):
        raise ValueError("bootstrap scores must be finite")
    observed = statistics.fmean(candidate) - statistics.fmean(control)
    rng = random.Random(seed)
    deltas = []
    for _ in range(resamples):
        candidate_mean = statistics.fmean(rng.choice(candidate) for _ in candidate)
        control_mean = statistics.fmean(rng.choice(control) for _ in control)
        deltas.append(candidate_mean - control_mean)
    return {
        "resamples": resamples,
        "seed": seed,
        "observed_delta": observed,
        "percentile_2_5": _percentile(deltas, 0.025),
        "percentile_50": _percentile(deltas, 0.50),
        "percentile_97_5": _percentile(deltas, 0.975),
    }


def _reliability(record: Mapping[str, Any]) -> dict[str, int]:
    summary = record.get("summary", {})
    if not isinstance(summary, Mapping):
        summary = {}
    failure_kind = summary.get("failure_kind") or record.get("failure_kind")
    missing_output = int(
        bool(record.get("missing_output", 0))
        or not isinstance(record.get("summary"), Mapping)
    )
    invalid = int(summary.get("invalid_selections", 0))
    fallback = int(summary.get("fallback_actions", 0))
    post_terminal = int(summary.get("post_terminal_actions", 0))
    incomplete = int(summary.get("terminal_result") is None)
    timeout = int(failure_kind in {"timeout", "process_timeout", "arena_wall_timeout"})
    failed = int(
        missing_output
        or record.get("status") != "pass"
        or failure_kind is not None
        or invalid
        or fallback
        or post_terminal
        or incomplete
    )
    return {
        "invalid_selections": invalid,
        "fallback_actions": fallback,
        "post_terminal_actions": post_terminal,
        "incomplete_games": incomplete,
        "timeouts": timeout,
        "failures": failed,
        "missing_outputs": missing_output,
    }


def _anchor(record: Mapping[str, Any]) -> str:
    value = record.get("anchor")
    if isinstance(value, str) and value:
        return value
    policy0 = record.get("policy0")
    policy1 = record.get("policy1")
    if policy0 == "candidate":
        return str(policy1)
    if policy1 == "candidate":
        return str(policy0)
    return "unknown"


def _aggregate_summary(
    records: Sequence[Mapping[str, Any]],
    *,
    control_scores: Sequence[float] | None = None,
    bootstrap_seed: int = 17,
) -> dict[str, Any]:
    wins = draws = losses = 0
    scores: list[float] = []
    reliability = {key: 0 for key in RELIABILITY_COUNTERS}
    for record in records:
        summary = record.get("summary", {})
        if not isinstance(summary, Mapping):
            summary = {}
        score = candidate_score(summary.get("terminal_result"), record["candidate_player"])
        for key, value in _reliability(record).items():
            reliability[key] += value
        if score is None:
            continue
        scores.append(score)
        outcome = candidate_outcome(summary.get("terminal_result"), record["candidate_player"])
        if outcome == "win":
            wins += 1
        elif outcome == "draw":
            draws += 1
        else:
            losses += 1
    completed = len(scores)
    report: dict[str, Any] = {
        "games_requested": len(records),
        "games_completed": completed,
        "candidate_wins": wins,
        "candidate_draws": draws,
        "candidate_losses": losses,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "candidate_score": statistics.fmean(scores) if scores else None,
        "candidate_win_rate_wilson_95": wilson_interval(wins, completed),
        "seat_balance": natural_seat_balance(records),
        "reliability": reliability,
        "promotable_reliability": completed == len(records) and not any(reliability.values()),
        "latency": latency_summary(records),
        "candidate_latency": latency_summary(records, "candidate_action_latencies_ms"),
        "paired_seed_claim": False,
        "candidate_scores": scores,
    }
    if control_scores is not None:
        report["control_bootstrap_score_delta"] = bootstrap_score_delta(
            scores, control_scores, seed=bootstrap_seed
        )
    return report


def aggregate_candidate_records(
    records: Sequence[Mapping[str, Any]],
    *,
    control_scores: Sequence[float] | None = None,
    bootstrap_seed: int = 17,
) -> dict[str, Any]:
    materialized = tuple(records)
    report = _aggregate_summary(
        materialized, control_scores=control_scores, bootstrap_seed=bootstrap_seed
    )
    groups: dict[tuple[str, int], list[Mapping[str, Any]]] = {}
    for record in materialized:
        player = record.get("candidate_player")
        if player not in (0, 1):
            raise ValueError("every record must identify candidate_player as 0 or 1")
        groups.setdefault((_anchor(record), player), []).append(record)
    cells: dict[str, dict[str, Any]] = {}
    for (anchor, player), group in sorted(groups.items()):
        cells.setdefault(anchor, {})[f"candidate_player_{player}"] = _aggregate_summary(group)
    report["cells"] = cells
    return report


def permutation_control(
    policy_factory: Any,
    observation: Any,
    request: Any,
    permutations: Sequence[Sequence[int]],
) -> dict[str, Any]:
    """Check semantic action equivalence under deterministic option permutations."""
    if len(permutations) == 0:
        raise ValueError("at least one option permutation is required")
    baseline_policy = policy_factory()
    baseline_policy.reset(request.episode_uuid, request.acting_player, "start")
    baseline_action = baseline_policy.choose(observation, request)
    baseline = baseline_action.submitted_original_indices
    outcomes = []
    for permutation in permutations:
        if sorted(permutation) != list(range(len(request.options))):
            raise ValueError("permutation control requires true option permutations")
        policy = policy_factory()
        policy.reset(request.episode_uuid, request.acting_player, "start")
        permuted = permute_request(request, permutation)
        action = policy.choose(observation, permuted)
        if request.ordering == "ORDERED":
            outcomes.append(tuple(action.submitted_original_indices) == tuple(baseline))
        elif request.ordering == "UNORDERED":
            outcomes.append(set(action.submitted_original_indices) == set(baseline))
        else:
            raise ValueError("permutation control requires ORDERED or UNORDERED request ordering")
    return {
        "permutations_requested": len(permutations),
        "equivalent": sum(outcomes),
        "non_equivalent": len(outcomes) - sum(outcomes),
        "pass": all(outcomes),
        "ordering": request.ordering,
        "equivalence": "sequence" if request.ordering == "ORDERED" else "set",
        "paired_seed_claim": False,
    }


def source_receipt(paths: Mapping[str, Path], project_root: Path) -> dict[str, dict[str, Any]]:
    """Return sanitized hashes and reject assets outside the project scope."""
    root = project_root.resolve()
    receipt: dict[str, dict[str, Any]] = {}
    for label, path in sorted(paths.items()):
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise ValueError(f"asset outside project scope: {label}")
        receipt[label] = {
            "path": resolved.relative_to(root).as_posix(),
            "bytes": resolved.stat().st_size,
            "sha256": sha256_file(resolved),
        }
    return receipt


def candidate_source_sha256(paths: Mapping[str, Path], project_root: Path) -> str:
    """Hash only the candidate implementation/config receipt, not the dirty tree."""
    receipt = source_receipt(paths, project_root)
    payload = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def write_sealed_json(path: Path, value: Mapping[str, Any]) -> str:
    """Write content-addressable evidence once and return its SHA-256."""
    write_immutable_json(path, value)
    digest = sha256_file(path)
    seal = path.with_name(path.name + ".sha256")
    descriptor = f"{digest}  {path.name}\n"
    with seal.open("x", encoding="ascii") as handle:
        handle.write(descriptor)
    path.chmod(0o440)
    seal.chmod(0o440)
    return digest


def verify_sealed_json(path: Path) -> bool:
    """Verify the digest sidecar and read-only mode for retained evidence."""
    path = path.resolve(strict=True)
    sidecar = path.with_name(path.name + ".sha256")
    try:
        descriptor = sidecar.read_text(encoding="ascii").strip().split()
    except (OSError, UnicodeError) as error:
        raise ValueError("sealed evidence digest sidecar is missing or unreadable") from error
    if len(descriptor) != 2 or descriptor[1] != path.name:
        raise ValueError("sealed evidence digest sidecar is malformed")
    actual = sha256_file(path)
    if descriptor[0] != actual:
        raise ValueError("sealed evidence digest does not match content")
    if path.stat().st_mode & 0o222 or sidecar.stat().st_mode & 0o222:
        raise ValueError("sealed evidence is writable")
    return True


def sanitized_report(
    *,
    run_id: str,
    config: Mapping[str, Any],
    aggregate: Mapping[str, Any],
    repository: Mapping[str, Any],
    platform: Mapping[str, Any],
    source_sha256: str,
    loaded_artifacts: Mapping[str, Any],
    permutation: Mapping[str, Any],
    command: Sequence[str] | None = None,
    candidate_source_sha256: str | None = None,
    card_table_semantic_sha256: str | None = None,
) -> dict[str, Any]:
    """Build the committed aggregate report without private absolute paths."""
    sanitized_artifacts = {
        label: {
            "bytes": value.get("bytes"),
            "sha256": value.get("sha256"),
        }
        for label, value in sorted(loaded_artifacts.items())
    }
    reliable = bool(aggregate.get("promotable_reliability"))
    complete = aggregate.get("games_completed") == aggregate.get("games_requested")
    permutation_pass = permutation.get("pass") is True
    return {
        "schema_version": B0_SCHEMA_VERSION,
        "record_id": f"{B0_EXPERIMENT_ID}-{run_id}",
        "experiment_id": B0_EXPERIMENT_ID,
        "status": "SUCCEEDED" if complete and reliable and permutation_pass else "FAILED",
        "decision": "NOT_REVIEWED",
        "candidate_perspective": True,
        "natural_deployment": True,
        "paired_seed_claim": False,
        "config": json.loads(json.dumps(config, sort_keys=True)),
        "aggregate": json.loads(json.dumps(aggregate, sort_keys=True)),
        "permutation_control": json.loads(json.dumps(permutation, sort_keys=True)),
        "repository": dict(repository),
        "platform": dict(platform),
        "source_sha256": source_sha256,
        "candidate_source_sha256": candidate_source_sha256,
        "card_table_semantic_sha256": card_table_semantic_sha256,
        "command": list(command or ()),
        "loaded_artifacts": sanitized_artifacts,
        "training_performed": False,
        "kaggle_runs": 0,
        "submission_created": False,
    }


__all__ = [
    "B0_BOOTSTRAP_RESAMPLES",
    "B0_EXPERIMENT_ID",
    "aggregate_candidate_records",
    "bootstrap_score_delta",
    "candidate_outcome",
    "candidate_score",
    "latency_summary",
    "natural_seat_balance",
    "permutation_control",
    "sanitized_report",
    "source_receipt",
    "candidate_source_sha256",
    "verify_sealed_json",
    "wilson_interval",
    "write_sealed_json",
]
