#!/usr/bin/env python3
"""Independently recalculate G1R from retained raw evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import pstats
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

from ptcg_rl.g1.soak import _completed_session_seconds, _slope_ci


ZERO_COUNTERS = ("invalid_selections", "fallback_actions", "post_terminal_actions")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_seal(path: Path) -> None:
    expected = path.with_suffix(path.suffix + ".sha256").read_text(encoding="ascii").split()[0]
    if sha256(path) != expected:
        raise ValueError(f"seal mismatch: {path}")


def records(path: Path):
    with path.open(encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            try:
                yield json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSONL at {path}:{line_number}") from error


def bad_game(record: dict) -> bool:
    summary = record.get("summary") or record
    return (
        record.get("status") != "pass"
        or summary.get("terminal_result") is None
        or summary.get("failure_kind") is not None
        or any(summary.get(name, 0) != 0 for name in ZERO_COUNTERS)
    )


def ks(left: list[int], right: list[int]) -> float:
    values = sorted(set(left + right))
    return max(
        abs(sum(item <= value for item in left) / len(left)
            - sum(item <= value for item in right) / len(right))
        for value in values
    )


def symbols(path: Path) -> list[str]:
    output = subprocess.run(
        ["nm", "-D", "--defined-only", str(path)], text=True,
        capture_output=True, check=True,
    ).stdout
    result = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[-2] == "T" and not fields[-1].startswith("_"):
            result.append(fields[-1])
    return sorted(result)


def review_contract(run: Path) -> dict:
    manifest_path = run / "run_manifest.json"
    verify_seal(manifest_path)
    manifest = read_json(manifest_path)
    sequences = [record["sequence"] for record in records(run / "log-burst.jsonl")]
    passed = (
        manifest.get("valid_operations", 0) >= 1_000_000
        and manifest.get("malformed_rejections_separate", 0) > 0
        and sequences == list(range(len(sequences)))
        and len(sequences) > 200
        and manifest.get("worker_restart", {}).get("replacement_ready") is True
    )
    return {
        "passed": passed, "valid_operations": manifest.get("valid_operations"),
        "malformed_rejections": manifest.get("malformed_rejections_separate"),
        "log_events": len(sequences), "manifest_sha256": sha256(manifest_path),
    }


def review_arena(run: Path) -> dict:
    manifest_path = run / "run_manifest.json"
    verify_seal(manifest_path)
    manifest = read_json(manifest_path)
    cells: Counter[tuple[str, str]] = Counter()
    first_players: Counter[int] = Counter()
    count = failures = requests = 0
    for record in records(run / "results.jsonl"):
        count += 1
        failures += bad_game(record)
        cells[(record["policy0"], record["policy1"])] += 1
        first_players[record["summary"]["first_player"]] += 1
        requests += record["summary"]["engine_requests"]
    expected_policies = set(manifest["policies"])
    passed = (
        count == 10_080 and failures == 0 and len(cells) == 36
        and set(left for left, _ in cells) == expected_policies
        and set(right for _, right in cells) == expected_policies
        and set(cells.values()) == {280}
        and manifest["metrics"]["games_completed"] == count
        and manifest["metrics"]["engine_requests"] == requests
    )
    return {
        "passed": passed, "games": count, "failures": failures,
        "cells": len(cells), "games_per_cell": sorted(set(cells.values())),
        "engine_requests": requests,
        "realized_first_player": {str(key): first_players[key] for key in (0, 1)},
        "manifest_sha256": sha256(manifest_path),
    }


def review_benchmark(run: Path) -> dict:
    manifest_path = run / "run_manifest.json"
    verify_seal(manifest_path)
    manifest = read_json(manifest_path)
    points = {}
    for mode_dir in sorted((run / "matches").iterdir()):
        for worker_dir in sorted(mode_dir.iterdir()):
            key = (mode_dir.name, int(worker_dir.name.removeprefix("workers-")))
            point_records = [read_json(path) for path in worker_dir.glob("*.json")]
            points[key] = {
                "games": len(point_records),
                "failures": sum(bad_game(record) for record in point_records),
            }
    profile = pstats.Stats(str(run / "encoded-observation.pstats"))
    profile_ok = any(function == "semantic_snapshot" for _, _, function in profile.stats)
    expected = {(mode, workers) for mode in
                ("raw-engine", "encoded-observation", "rule-policy")
                for workers in (1, 2, 4, 8)}
    passed = (
        set(points) == expected
        and all(value == {"games": 200, "failures": 0} for value in points.values())
        and profile_ok and manifest.get("failure_reason") is None
    )
    return {
        "passed": passed, "points": {
            f"{mode}@{workers}": value for (mode, workers), value in sorted(points.items())
        },
        "profile_sha256": sha256(run / "encoded-observation.pstats"),
        "manifest_sha256": sha256(manifest_path),
    }


def review_engine_compare(run: Path, shipped: Path, built: Path) -> dict:
    manifest_path = run / "run_manifest.json"
    verify_seal(manifest_path)
    manifest = read_json(manifest_path)
    corpora = {
        label: list(records(run / label / "results.jsonl")) for label in ("shipped", "built")
    }
    counts = {
        label: [record["summary"]["engine_requests"] for record in values]
        for label, values in corpora.items()
    }
    selections = {
        label: {key for record in values for key in record["summary"]["selection_type_counts"]}
        for label, values in corpora.items()
    }
    options = {
        label: {key for record in values for key in record["summary"]["option_type_counts"]}
        for label, values in corpora.items()
    }
    left, right = counts["shipped"], counts["built"]
    pooled_mean = (statistics.mean(left) + statistics.mean(right)) / 2
    pooled_se = math.sqrt(statistics.variance(left) / len(left)
                          + statistics.variance(right) / len(right))
    config = manifest["config"]
    allowed_delta = max(config["mean_relative_max"] * pooled_mean,
                        config["mean_se_floor"] * pooled_se)
    computed_ks = ks(left, right)
    mean_delta = abs(statistics.mean(left) - statistics.mean(right))
    passed = (
        all(len(values) == 1000 for values in corpora.values())
        and all(not bad_game(record) for values in corpora.values() for record in values)
        and selections["shipped"] == selections["built"]
        and options["shipped"] == options["built"]
        and symbols(shipped) == symbols(built)
        and computed_ks <= config["ks_max"] and mean_delta <= allowed_delta
    )
    return {
        "passed": passed, "games": {key: len(value) for key, value in corpora.items()},
        "request_count_ks": computed_ks, "mean_delta": mean_delta,
        "allowed_mean_delta": allowed_delta,
        "selection_types": sorted(selections["shipped"]),
        "option_types": sorted(options["shipped"]),
        "libraries": {"shipped": sha256(shipped), "built": sha256(built)},
        "manifest_sha256": sha256(manifest_path),
    }


def review_soak(run: Path) -> dict:
    manifest_path = run / "run_manifest.json"
    verify_seal(manifest_path)
    manifest = read_json(manifest_path)
    games = failures = invalid = fallback = post_terminal = 0
    for record in records(run / "games.jsonl"):
        games += 1
        summary = record.get("summary") or record
        failures += bad_game(record)
        invalid += summary.get("invalid_selections", 0)
        fallback += summary.get("fallback_actions", 0)
        post_terminal += summary.get("post_terminal_actions", 0)

    event_records = list(records(run / "events.jsonl"))
    starts = {event["process_key"]: event["time"] for event in event_records
              if event["kind"] == "worker_started"}
    samples: dict[str, list[tuple[float, int]]] = defaultdict(list)
    for sample in records(run / "rss-samples.jsonl"):
        samples[sample["process_key"]].append((sample["time"], sample["rss_bytes"]))
    slopes = {}
    peak = 0
    for key, values in samples.items():
        peak = max(peak, *(rss for _, rss in values))
        eligible = [point for point in values if point[0] - starts[key]
                    >= manifest["warmup_exclusion_seconds_per_process"]]
        slope = _slope_ci(eligible)
        if slope is not None:
            slopes[key] = slope
    forced = [event for event in event_records if event["kind"] == "forced_worker_death"]
    unexpected = [event for event in event_records if event["kind"] == "unexpected_worker_death"]
    raw_span = _completed_session_seconds(samples)
    evidence_bytes = sum((run / name).stat().st_size for name in
                         ("events.jsonl", "games.jsonl", "rss-samples.jsonl"))
    passed = (
        games == manifest["games_completed"] and failures == 0
        and invalid == fallback == post_terminal == 0
        and len(forced) == 1 and not unexpected
        and raw_span >= manifest["duration_seconds_required"] - manifest["rss_sample_period_seconds"]
        and manifest["duration_seconds_observed"] >= manifest["duration_seconds_required"]
        and peak <= manifest["peak_ceiling_bytes_per_worker"]
        and slopes and all(value["upper_95_mib_per_hour"]
                           <= manifest["slope_upper_threshold_mib_per_hour_per_worker"]
                           for value in slopes.values())
        and evidence_bytes <= manifest["config"]["max_evidence_bytes"]
    )
    return {
        "passed": passed, "games": games, "failures": failures,
        "invalid_selections": invalid, "fallback_actions": fallback,
        "post_terminal_actions": post_terminal, "forced_worker_deaths": len(forced),
        "unexpected_worker_deaths": len(unexpected), "raw_sample_span_seconds": raw_span,
        "manifest_active_seconds": manifest["duration_seconds_observed"],
        "peak_rss_bytes": peak, "evidence_bytes": evidence_bytes,
        "slopes": slopes, "manifest_sha256": sha256(manifest_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--acceptance-root", type=Path, required=True)
    parser.add_argument("--contract-run", type=Path, required=True)
    parser.add_argument("--verification-run", type=Path, required=True)
    parser.add_argument("--engine-compare", type=Path, required=True)
    parser.add_argument("--shipped-library", type=Path, required=True)
    parser.add_argument("--built-library", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    verification_path = args.verification_run / "run_manifest.json"
    verify_seal(verification_path)
    verification = read_json(verification_path)
    verification_ok = (
        verification.get("internal_verdict") == "PASS"
        and all(check["exit_code"] == 0 for check in verification["checks"])
    )
    results = {
        "verification": {"passed": verification_ok,
                         "manifest_sha256": sha256(verification_path)},
        "contract": review_contract(args.contract_run),
        "arena": review_arena(args.acceptance_root / "arena"),
        "benchmark": review_benchmark(args.acceptance_root / "benchmark-attempt-2"),
        "engine_compare": review_engine_compare(
            args.engine_compare, args.shipped_library, args.built_library
        ),
        "rss_soak": review_soak(args.acceptance_root / "rss-soak"),
    }
    source_hashes = {
        read_json(path / "run_manifest.json")["source_sha256"]
        for path in (args.verification_run, args.acceptance_root / "arena",
                     args.acceptance_root / "benchmark-attempt-2",
                     args.acceptance_root / "rss-soak", args.engine_compare)
    }
    passed = all(result["passed"] for result in results.values()) and len(source_hashes) == 1
    payload = {
        "schema_version": 1, "producer": "ptcg.g1r.independent-review",
        "status": "SUCCEEDED" if passed else "BLOCKED",
        "decision": "PASS" if passed else "FAIL",
        "checks": results, "acceptance_source_sha256": next(iter(source_hashes), None),
        "source_hashes_equal": len(source_hashes) == 1,
        "reviewer_sha256": sha256(Path(__file__)), "training_performed": False,
        "episode_json_downloads": 0, "local_cost_usd": 0.0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.open("x", encoding="utf-8").write(
        json.dumps(payload, indent=2, sort_keys=True) + "\n"
    )
    args.output.with_suffix(args.output.suffix + ".sha256").open("x", encoding="ascii").write(
        f"{sha256(args.output)}  {args.output.name}\n"
    )
    print(json.dumps({"status": payload["status"], "decision": payload["decision"],
                      "output": str(args.output)}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
