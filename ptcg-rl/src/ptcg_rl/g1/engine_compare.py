from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path
from statistics import mean, variance
from typing import Any

from .evidence import (
    git_state,
    platform_record,
    sha256_file,
    source_tree_hash,
    technical_run_envelope,
    unique_run_id,
    write_immutable_json,
)
from .models import stable_hash


def _matches(directory: Path) -> list[dict[str, Any]]:
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(
        (directory / "matches").glob("*.json")
    )]


def _ks(left: list[int], right: list[int]) -> float:
    values = sorted(set(left + right))
    return max(
        abs(sum(item <= value for item in left) / len(left)
            - sum(item <= value for item in right) / len(right))
        for value in values
    )


def _symbols(library: Path) -> list[str]:
    output = subprocess.check_output(
        ["nm", "-D", "--defined-only", str(library)], text=True
    )
    symbols = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[-2] == "T" and not fields[-1].startswith("_"):
            symbols.append(fields[-1])
    return sorted(symbols)


def run_engine_compare(args, repo: Path) -> dict[str, Any]:
    if args.games_per_library <= 0 or args.games_per_library % 4:
        raise ValueError("games-per-library must be positive and divisible by four")
    run_id = unique_run_id("g1r-engine-compare")
    run_dir = (args.output or repo / "runs" / run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    executable = str(Path(sys.executable).with_name("ptcg"))
    roots = {
        "shipped": args.shipped_engine_root.resolve(strict=True),
        "built": args.built_engine_root.resolve(strict=True),
    }
    commands = {}
    for label, root in roots.items():
        command = [
            executable, "g1", "arena", "--engine-root", str(root),
            "--card-data", str(args.card_data.resolve(strict=True)),
            "--default-deck", str(args.default_deck.resolve(strict=True)),
            "--private-baselines", str(args.private_baselines.resolve(strict=True)),
            "--policies", "random,first", "--games-per-cell",
            str(args.games_per_library // 4), "--workers", str(args.workers),
            "--request-cap", str(args.request_cap), "--game-timeout", str(args.game_timeout),
            "--seed", str(args.seed), "--output", str(run_dir / label),
        ]
        completed = subprocess.run(command, cwd=repo, text=True, capture_output=True, check=False)
        commands[label] = {"argv": command, "exit_code": completed.returncode,
                           "stdout_tail": completed.stdout[-500:] if completed.returncode else ""}
        if completed.returncode:
            raise ValueError(f"{label} engine corpus failed")
    corpora = {label: _matches(run_dir / label) for label in roots}
    request_counts = {
        label: [record["summary"]["engine_requests"] for record in records]
        for label, records in corpora.items()
    }
    selection_sets = {
        label: sorted({key for record in records for key in record["summary"]["selection_type_counts"]})
        for label, records in corpora.items()
    }
    option_sets = {
        label: sorted({key for record in records for key in record["summary"]["option_type_counts"]})
        for label, records in corpora.items()
    }
    left, right = request_counts["shipped"], request_counts["built"]
    pooled_mean = (mean(left) + mean(right)) / 2
    pooled_se = math.sqrt(variance(left) / len(left) + variance(right) / len(right))
    allowed_mean_delta = max(args.mean_relative_max * pooled_mean,
                             args.mean_se_floor * pooled_se)
    shipped_library = roots["shipped"] / "cg" / "libcg.so"
    built_library = roots["built"] / "cg" / "libcg.so"
    counters_ok = all(
        record["status"] == "pass" and record["summary"]["failure_kind"] is None
        and record["summary"]["invalid_selections"] == 0
        and record["summary"]["fallback_actions"] == 0
        and record["summary"]["post_terminal_actions"] == 0
        for records in corpora.values() for record in records
    )
    checks = {
        "exact_games": all(len(records) == args.games_per_library for records in corpora.values()),
        "zero_error_counters": counters_ok,
        "abi_symbols_equal": _symbols(shipped_library) == _symbols(built_library),
        "selection_type_sets_equal": selection_sets["shipped"] == selection_sets["built"],
        "option_type_sets_equal": option_sets["shipped"] == option_sets["built"],
        "ks_within_tolerance": _ks(left, right) <= args.ks_max,
        "mean_within_tolerance": abs(mean(left) - mean(right)) <= allowed_mean_delta,
    }
    passed = all(checks.values())
    manifest_path = run_dir / "run_manifest.json"
    config = {
        "games_per_library": args.games_per_library, "workers": args.workers,
        "request_cap": args.request_cap, "game_timeout": args.game_timeout,
        "seed": args.seed, "ks_max": args.ks_max,
        "mean_relative_max": args.mean_relative_max,
        "mean_se_floor": args.mean_se_floor, "training": False,
    }
    manifest = {
        **technical_run_envelope(repo, manifest_path, run_id, "ptcg.g1r.engine-compare", passed),
        "trajectory_equality_claim": False,
        "games_per_library": args.games_per_library,
        "libraries": {
            label: {"sha256": sha256_file(root / "cg" / "libcg.so"),
                    "games": len(corpora[label]),
                    "mean_requests": mean(request_counts[label]),
                    "selection_types": selection_sets[label], "option_types": option_sets[label]}
            for label, root in roots.items()
        },
        "distribution": {"request_count_ks": _ks(left, right),
                         "mean_absolute_delta": abs(mean(left) - mean(right)),
                         "allowed_mean_delta": allowed_mean_delta,
                         "thresholds": {"ks_max": args.ks_max,
                                        "mean_relative_max": args.mean_relative_max,
                                        "mean_se_floor": args.mean_se_floor}},
        "checks": checks,
        "commands": commands,
        "config": config, "config_sha256": stable_hash(config),
        "repository": git_state(repo), "platform": platform_record(),
        "source_sha256": source_tree_hash(repo), "command": list(sys.argv),
        "training_performed": False, "local_cost_usd": 0.0,
    }
    write_immutable_json(manifest_path, manifest)
    (run_dir / "run_manifest.json.sha256").write_text(
        f"{sha256_file(manifest_path)}  run_manifest.json\n", encoding="ascii"
    )
    return manifest
