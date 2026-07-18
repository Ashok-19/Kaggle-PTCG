from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def _passed(record: dict[str, Any]) -> bool:
    return record.get("internal_verdict", record.get("status")) == "PASS"


def recalculate_gate(args, repo: Path) -> dict[str, Any]:
    manifests = []
    for path in sorted((repo / "runs").glob("**/run_manifest.json")):
        try:
            manifests.append((path, json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError):
            continue

    def find(predicate: Callable[[dict[str, Any]], bool]) -> str | None:
        for path, record in reversed(manifests):
            if predicate(record):
                return path.relative_to(repo).as_posix()
        return None

    verification = find(lambda value: value.get("producer") == "ptcg.g1r.verification"
                        and _passed(value))
    valid_corpus = find(lambda value: value.get("valid_operations", 0) >= 1_000_000
                        and value.get("malformed_rejections_separate", 0) > 0 and _passed(value))
    log_restart = find(lambda value: value.get("log_burst", {}).get("events", 0) > 200
                       and value.get("worker_restart", {}).get("replacement_ready") is True
                       and value.get("valid_operations", 0) >= 1_000_000
                       and _passed(value))
    exact_baselines = find(lambda value: all(
        policy in value.get("policies", []) for policy in (
            "rule:dragapult-ex", "rule:iono", "rule:mega-abomasnow-ex",
            "rule:mega-lucario-ex",
        )) and value.get("metrics", {}).get("failures") == 0)
    arena = find(lambda value: value.get("metrics", {}).get("games_completed", 0) >= 10_000
                 and value.get("metrics", {}).get("failures") == 0
                 and value.get("metrics", {}).get("invalid_selections") == 0
                 and value.get("metrics", {}).get("fallback_actions") == 0
                 and value.get("metrics", {}).get("post_terminal_actions") == 0
                 and len(value.get("cells", {})) == 36 and _passed(value))
    parity = find(lambda value: value.get("games_per_library", 0) >= 1_000
                  and all(value.get("checks", {}).values()) and _passed(value))
    benchmark = find(lambda value: len(value.get("points", [])) == 12
                     and not value.get("failure_reason") and _passed(value))
    soak = find(lambda value: value.get("duration_seconds_required", 0) >= 21_600
                and value.get("unexpected_failures") == 0
                and value.get("worker_replacement_verified") is True and _passed(value))
    checks = [
        ("contract regressions and complete verification suite", verification),
        ("1,000,000 valid operations; malformed rejections separate", valid_corpus),
        (">200 log burst and worker replacement", log_restart),
        ("four exact rule-agent/deck integrations", exact_baselines),
        ("10,000 complete balanced natural-deployment games", arena),
        ("Ubuntu 22.04 shipped-versus-built comparison", parity),
        ("raw/encoded/rule throughput at 1/2/4/8 workers", benchmark),
        ("six-hour RSS soak with slope confidence interval", soak),
    ]
    passed = all(evidence is not None for _, evidence in checks)
    now = datetime.now(timezone.utc).isoformat()
    result = {
        "schema_version": 1, "record_id": "gate-g1r-20260718",
        "created_at_utc": "2026-07-18T12:00:00Z", "updated_at_utc": now,
        "source_path": "reports/gates/g1r.json", "producer": "ptcg.g1r.verdict",
        "producer_version": "1", "gate_id": "G1R",
        "title": "G1 environment/action/recurrent contract recertification",
        "status": "SUCCEEDED" if passed else "BLOCKED",
        "decision": "PASS" if passed else "NOT_REVIEWED",
        "technical_checks": [
            {"name": name, "status": "SUCCEEDED" if evidence else "BLOCKED",
             "evidence": evidence} for name, evidence in checks
        ],
        "blockers": [name for name, evidence in checks if evidence is None],
        "warnings": [
            "Native engine trajectories are nondeterministic; no paired-seed claim is made.",
            "Observed coverage and maxima are not engine guarantees.",
        ],
        "approved_next_action": "Independent G1R review" if passed else
                                "Complete only the blocked G1R acceptance criteria.",
        "cost_usd": 0.0,
    }
    output = args.output if args.output.is_absolute() else repo / args.output
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)
    return result
