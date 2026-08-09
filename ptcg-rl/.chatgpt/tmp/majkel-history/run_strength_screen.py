"""Bounded native Majkel screen and its fixed 480-game confirmation."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / ".chatgpt/tmp/majkel-history"
ARENA_AGENTS = BASE / "arena-agents"
PTCG = ROOT / ".venv/bin/ptcg"
OPPONENTS = (
    "dragapult-ex", "mega-lucario-ex", "lopunny-v9", "roman-v10",
    "crustle-v1", "nithin-1084", "alakazam-v9", "grim-floor4",
)
RELIABILITY_KEYS = ("invalid_selections", "fallback_actions", "post_terminal_actions")
TERM_GRACE_SECONDS = 2.0
PLANS = {
    "screen": {"variants": ("mk-lgb-0p9-pure", "grim-majkel-h-direct", "grim-majkel-h-g020", "grim-majkel-h-c070"), "games_per_cell": 5, "seed_base": 202615000, "overall_timeout": 1_200},
    "confirmation": {"variants": ("mk-lgb-0p9-pure", "grim-majkel-h-c070"), "games_per_cell": 15, "seed_base": 202640000, "overall_timeout": 2_400},
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def tail(value: Any, limit: int = 2_000) -> str:
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return "" if value is None else str(value)[-limit:]


def expected(plan: dict[str, Any]) -> int:
    return len(plan["variants"]) * len(OPPONENTS) * 2 * plan["games_per_cell"]


def run_dir(label: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    path = BASE / f"strength-{label}-{stamp}-{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        json.dump(record, handle, sort_keys=True, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def base_record(variant: str, opponent: str, seat: int, k: int, seed: int, game_id: str) -> dict[str, Any]:
    policy0, policy1 = (variant, opponent) if seat == 0 else (opponent, variant)
    return {
        "record_schema_version": 1, "attempted_at_utc": now(), "variant": variant, "opponent": opponent,
        "candidate_seat": seat, "k": k, "seed": seed, "game_id": game_id,
        "policy0": f"rule:{policy0}", "policy1": f"rule:{policy1}", "process_returncode": None,
        "error_category": None, "error_tail": "", "stdout_tail": "", "stderr_tail": "",
        "reward": None, "score": None, "terminal_result": None, "engine_requests": None,
        "process_metrics": {"wall_seconds": None, "cpu_seconds": None, "peak_rss_bytes": None},
        "reliability_counters": dict.fromkeys(RELIABILITY_KEYS, 0), "arena_status": None,
        "arena_summary": None, "completed": False,
    }


def interpret(
    variant: str,
    opponent: str,
    seat: int,
    k: int,
    seed: int,
    game_id: str,
    returncode: int | None,
    stdout: Any,
    stderr: Any,
    elapsed: float,
    error: str | None = None,
) -> tuple[dict[str, Any], bool]:
    record = base_record(variant, opponent, seat, k, seed, game_id)
    record.update({"process_returncode": returncode, "stdout_tail": tail(stdout), "stderr_tail": tail(stderr)})
    record["process_metrics"]["wall_seconds"] = elapsed
    if error:
        record.update({"error_category": error, "error_tail": tail(stderr or stdout)})
        return record, True
    if returncode != 0:
        record.update({"error_category": "nonzero_returncode", "error_tail": tail(stderr or stdout)})
        return record, True
    if not tail(stdout).strip():
        record["error_category"] = "empty_output"
        return record, True
    try:
        payload = json.loads(stdout)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        record.update({"error_category": "malformed_json", "error_tail": f"{exc!r}: {tail(stdout)}"})
        return record, True
    if not isinstance(payload, dict) or not isinstance(payload.get("summary"), dict) or not isinstance(payload.get("process_metrics"), dict):
        record.update({"error_category": "missing_fields", "error_tail": "missing result/summary/process_metrics"})
        return record, True
    summary = payload["summary"]
    metrics = payload["process_metrics"]
    record["arena_status"] = payload.get("status")
    record["arena_summary"] = {key: summary.get(key) for key in ("player_rewards", "terminal_result", "engine_requests", *RELIABILITY_KEYS, "failure_kind")}
    record["terminal_result"] = summary.get("terminal_result")
    record["engine_requests"] = summary.get("engine_requests")
    record["process_metrics"] = {key: metrics.get(key) for key in ("wall_seconds", "cpu_seconds", "peak_rss_bytes")}
    for key in RELIABILITY_KEYS:
        record["reliability_counters"][key] = summary.get(key, 0)
    missing = [key for key in (*RELIABILITY_KEYS, "player_rewards", "terminal_result", "engine_requests") if key not in summary]
    missing.extend(f"summary.{key} nonnegative int" for key in RELIABILITY_KEYS if not nonnegative_int(summary.get(key)))
    if not isinstance(summary.get("terminal_result"), int) or isinstance(summary.get("terminal_result"), bool) or summary["terminal_result"] not in (0, 1, 2):
        missing.append("summary.terminal_result in {0,1,2}")
    if not nonnegative_int(summary.get("engine_requests")):
        missing.append("summary.engine_requests nonnegative int")
    missing.extend(f"process_metrics.{key}" for key in ("wall_seconds", "cpu_seconds", "peak_rss_bytes") if key not in metrics)
    missing.extend(f"process_metrics.{key} finite nonnegative" for key in ("wall_seconds", "cpu_seconds", "peak_rss_bytes") if not finite(metrics.get(key)) or metrics[key] < 0)
    rewards = summary.get("player_rewards")
    if not isinstance(rewards, list) or len(rewards) != 2 or not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(float(x)) for x in rewards):
        missing.append("summary.player_rewards[2 finite values]")
    if missing:
        record.update({"error_category": "missing_fields", "error_tail": ", ".join(missing)})
        return record, True
    if record["arena_status"] != "pass" or summary.get("failure_kind") not in (None, ""):
        record.update({"error_category": "native_error", "error_tail": str(summary.get("failure_kind") or record["arena_status"])})
        return record, True
    record["reward"] = float(rewards[seat])
    record["score"] = (record["reward"] + 1.0) / 2.0
    bad = {key: value for key, value in record["reliability_counters"].items() if isinstance(value, (int, float)) and not isinstance(value, bool) and value != 0}
    if bad:
        record.update({"error_category": "reliability_counter", "error_tail": json.dumps(bad, sort_keys=True)})
        return record, True
    record["completed"] = True
    return record, False


def terminate_group(process: subprocess.Popen) -> tuple[Any, Any]:
    """TERM the session group, then KILL it if it does not exit, and reap it."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        return process.communicate(timeout=TERM_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        return process.communicate()


def invoke(variant: str, opponent: str, seat: int, k: int, seed: int, game_id: str) -> tuple[dict[str, Any], bool]:
    policy0, policy1 = (variant, opponent) if seat == 0 else (opponent, variant)
    command = [
        str(PTCG), "g1", "arena-one",
        "--engine-root", "private/assets/official/sample_submission/sample_submission",
        "--card-data", "private/assets/official/EN_Card_Data.csv",
        "--default-deck", "private/baselines/mega-lucario-ex/deck.csv",
        "--private-baselines", str(ARENA_AGENTS.relative_to(ROOT)), "--request-cap", "20000", "--game-timeout", "180",
        "--failure-directory", str((BASE / "strength-failures").relative_to(ROOT)),
        "--policy0", f"rule:{policy0}", "--policy1", f"rule:{policy1}",
        "--seed", str(seed), "--game-id", game_id,
    ]
    started = time.perf_counter()
    process = subprocess.Popen(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=30)
    except subprocess.TimeoutExpired as exc:
        stdout, stderr = terminate_group(process)
        stdout = stdout or getattr(exc, "stdout", "")
        stderr = stderr or getattr(exc, "stderr", "")
        return interpret(variant, opponent, seat, k, seed, game_id, process.returncode, stdout, stderr, time.perf_counter() - started, "timeout")
    return interpret(variant, opponent, seat, k, seed, game_id, process.returncode, stdout, stderr, time.perf_counter() - started)


def finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def nonnegative_int(value: Any) -> bool: return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def group_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    clean = [record for record in records if record.get("completed") and not record.get("error_category")]
    scores = [float(record["score"]) for record in clean if finite(record.get("score"))]
    walls = [float(record["process_metrics"]["wall_seconds"]) for record in clean if finite(record.get("process_metrics", {}).get("wall_seconds"))]
    return {"attempted": len(records), "completed": len(clean),
            "errors": dict(sorted(Counter(r.get("error_category") for r in records if r.get("error_category")).items())),
            "reliability_totals": reliability_totals(records),
            "wdl": {"wins": scores.count(1.0), "draws": scores.count(0.5), "losses": scores.count(0.0)},
            "expected_match_score": sum(scores) / len(scores) if scores else None,
            "mean_wall_seconds": sum(walls) / len(walls) if walls else None,
            "max_peak_rss_bytes": max((r["process_metrics"].get("peak_rss_bytes") for r in clean if finite(r["process_metrics"].get("peak_rss_bytes"))), default=None)}


def reliability_totals(records: list[dict[str, Any]]) -> dict[str, int]:
    totals = Counter()
    for record in records:
        for key, value in record.get("reliability_counters", {}).items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                totals[key] += int(value)
    return dict(sorted(totals.items()))


def aggregate(records: list[dict[str, Any]], path: Path, started: str, label: str, plan: dict[str, Any], stopped: str | None) -> dict[str, Any]:
    clean = sum(record.get("completed") and not record.get("error_category") for record in records)
    by_variant = {variant: group_summary([r for r in records if r["variant"] == variant]) for variant in plan["variants"]}
    by_opponent = {opponent: group_summary([r for r in records if r["opponent"] == opponent]) for opponent in OPPONENTS}
    by_seat = {str(seat): group_summary([r for r in records if r["candidate_seat"] == seat]) for seat in (0, 1)}
    return {"schema_version": 1, "run_id": path.name, "started_at_utc": started, "ended_at_utc": now(),
            "status": "PASS" if clean == expected(plan) else "STOPPED", "stopped_reason": stopped,
            "design": {"label": label, "variants": plan["variants"], "opponents": OPPONENTS, "seats": [0, 1], "games_per_variant_opponent_seat": plan["games_per_cell"], "expected_games": expected(plan), "native_entropy": True, "paired": False, "policy_seed_base": plan["seed_base"]},
            "limits": {"outer_game_timeout_seconds": 30, "overall_timeout_seconds": plan["overall_timeout"], "engine_game_timeout_seconds": 180, "request_cap": 20_000, "stop_on_any_error_or_reliability_counter": True},
            "attempted_games": len(records), "completed_games": clean, "reliability_totals": reliability_totals(records),
            "error_totals": dict(sorted(Counter(r.get("error_category") for r in records if r.get("error_category")).items())),
            "by_variant": by_variant, "by_opponent": by_opponent, "by_seat": by_seat, "records_jsonl": str((path / "results.jsonl").relative_to(ROOT))}


def self_check() -> None:
    assert expected(PLANS["screen"]) == 320
    assert expected(PLANS["confirmation"]) == 480
    assert PLANS["screen"]["variants"] == ("mk-lgb-0p9-pure", "grim-majkel-h-direct", "grim-majkel-h-g020", "grim-majkel-h-c070")
    assert PLANS["confirmation"]["variants"] == ("mk-lgb-0p9-pure", "grim-majkel-h-c070")
    assert PLANS["confirmation"]["seed_base"] > PLANS["screen"]["seed_base"] + 15_000 + 2_100 + 50 + 4
    payload = {"status": "pass", "summary": {"player_rewards": [1.0, -1.0], "terminal_result": 1, "engine_requests": 2, "invalid_selections": 0, "fallback_actions": 0, "post_terminal_actions": 0, "failure_kind": None}, "process_metrics": {"wall_seconds": 1.0, "cpu_seconds": 0.5, "peak_rss_bytes": 10}}
    record, stop = interpret("a", "b", 0, 0, 1, "self-check", 0, json.dumps(payload), "", 1.0)
    assert record["completed"] and not stop and record["score"] == 1.0
    record, stop = interpret("a", "b", 0, 0, 1, "self-check-fail", 1, "", "boom", 1.0)
    assert stop and record["error_category"] == "nonzero_returncode"
    bad = json.loads(json.dumps(payload))
    bad["summary"]["fallback_actions"] = -1
    record, stop = interpret("a", "b", 0, 0, 1, "self-check-bad-counter", 0, json.dumps(bad), "", 1.0)
    assert stop and record["error_category"] == "missing_fields"
    bad["summary"]["fallback_actions"] = 0
    bad["process_metrics"]["cpu_seconds"] = float("inf")
    record, stop = interpret("a", "b", 0, 0, 1, "self-check-bad-metric", 0, json.dumps(bad), "", 1.0)
    assert stop and record["error_category"] == "missing_fields"
    assert group_summary([])["expected_match_score"] is None
    probe = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    terminate_group(probe)
    assert probe.poll() is not None
    print("self-check: PASS (no arena games launched)")


def run(label: str) -> None:
    plan = PLANS[label]
    directory = run_dir(label)
    records_path = directory / "results.jsonl"
    started = now()
    started_clock = time.monotonic()
    records = []
    stopped = None
    for vi, variant in enumerate(plan["variants"]):
        for oi, opponent in enumerate(OPPONENTS):
            for seat in (0, 1):
                for k in range(plan["games_per_cell"]):
                    if time.monotonic() - started_clock >= plan["overall_timeout"]:
                        stopped = "overall_timeout"
                        break
                    seed = plan["seed_base"] + vi * 5_000 + oi * 300 + seat * 50 + k
                    game_id = f"mjh-{variant}-{opponent}-{seat}-{k}" if label == "screen" else f"mjh-{label}-{variant}-{opponent}-{seat}-{k}"
                    record, stop = invoke(variant, opponent, seat, k, seed, game_id)
                    records.append(record)
                    append_jsonl(records_path, record)
                    print(f"attempt {len(records)}/{expected(plan)} {variant} vs {opponent} seat={seat} k={k} status={record['error_category'] or 'pass'} score={record['score']}", flush=True)
                    if stop:
                        stopped = record["error_category"] or "screen_stop"
                        break
                if stopped:
                    break
            if stopped:
                break
        if stopped:
            break
    summary = aggregate(records, directory, started, label, plan, stopped)
    summary["records_jsonl_sha256"] = hashlib.sha256(records_path.read_bytes()).hexdigest() if records_path.exists() else None
    summary["records_jsonl_bytes"] = records_path.stat().st_size if records_path.exists() else 0
    aggregate_path = directory / "aggregate.json"
    aggregate_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"aggregate={aggregate_path}")
    print(f"records={records_path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--confirmation", action="store_true")
    args = parser.parse_args()
    if args.self_check:
        self_check()
    else:
        run("confirmation" if args.confirmation else "screen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
