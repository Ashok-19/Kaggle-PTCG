from __future__ import annotations

import json
import multiprocessing as mp
import os
import queue
import random
import shutil
import time
import uuid
from pathlib import Path
from statistics import median
from types import SimpleNamespace
from typing import Any

from .arena import run_one_native_match
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


def _append(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as destination:
        destination.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


def _worker(slot: int, config: dict[str, Any], stop, events) -> None:
    game = 0
    while not stop.is_set():
        game_id = f"soak-slot-{slot}-pid-{os.getpid()}-game-{game:08d}-{uuid.uuid4().hex[:8]}"
        events.put({"kind": "game_started", "slot": slot, "pid": os.getpid(),
                    "game_id": game_id, "time": time.time()})
        args = SimpleNamespace(**{
            **config, "game_id": game_id, "seed": config["seed"] + game,
            "failure_directory": Path(config["failure_directory"]) / game_id,
        })
        try:
            record = run_one_native_match(args, Path(config["repo"]))
            summary = record["summary"]
            record = {
                "status": record["status"], "game_id": game_id,
                "terminal_result": summary["terminal_result"],
                "engine_requests": summary["engine_requests"],
                "invalid_selections": summary["invalid_selections"],
                "fallback_actions": summary["fallback_actions"],
                "post_terminal_actions": summary["post_terminal_actions"],
                "failure_kind": summary["failure_kind"],
            }
        except BaseException as error:
            record = {"status": "fail", "game_id": game_id,
                      "failure_kind": type(error).__name__}
        events.put({"kind": "game_finished", "slot": slot, "pid": os.getpid(),
                    "game_id": game_id, "time": time.time(), "record": record})
        game += 1


def _rss(pid: int) -> int | None:
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except (FileNotFoundError, ProcessLookupError):
        return None
    return None


def _slope(points: list[tuple[float, int]]) -> float:
    slopes = [
        (right[1] - left[1]) / (right[0] - left[0])
        for index, left in enumerate(points) for right in points[index + 1:]
        if right[0] != left[0]
    ]
    return median(slopes)


def _slope_ci(points: list[tuple[float, int]], samples: int = 500) -> dict[str, float] | None:
    if len(points) < 3:
        return None
    origin = points[0][0]
    normalized = [((when - origin) / 3600, rss / (1024 * 1024)) for when, rss in points]
    rng = random.Random(17)
    bootstrapped = []
    for _ in range(samples):
        chosen = sorted(rng.choices(normalized, k=len(normalized)))
        if len({item[0] for item in chosen}) >= 2:
            bootstrapped.append(_slope(chosen))
    bootstrapped.sort()
    return {
        "estimate_mib_per_hour": _slope(normalized),
        "lower_95_mib_per_hour": bootstrapped[int(0.025 * (len(bootstrapped) - 1))],
        "upper_95_mib_per_hour": bootstrapped[int(0.975 * (len(bootstrapped) - 1))],
    }


def _completed_session_seconds(samples: dict[str, list[tuple[float, int]]]) -> float:
    """Conservatively recover active time without counting gaps between resumes."""
    sessions: dict[str, list[float]] = {}
    for process_key, values in samples.items():
        session_id = process_key.split(":", 1)[0]
        sessions.setdefault(session_id, []).extend(timestamp for timestamp, _ in values)
    return sum(max(values) - min(values) for values in sessions.values() if values)


def run_soak(args, repo: Path) -> dict[str, Any]:
    if args.duration_seconds <= 0 or args.sample_seconds <= 0 or args.workers <= 0:
        raise ValueError("duration, sample period, and workers must be positive")
    if args.warmup_seconds < 0 or args.warmup_seconds >= args.duration_seconds:
        raise ValueError("warmup must be nonnegative and shorter than the soak")
    engine_root = args.engine_root.resolve(strict=True)
    card_data = args.card_data.resolve(strict=True)
    default_deck = args.default_deck.resolve(strict=True)
    private_baselines = args.private_baselines.resolve(strict=True)
    run_config = {
        "policy": args.policy, "workers": args.workers,
        "duration_seconds": args.duration_seconds, "sample_seconds": args.sample_seconds,
        "warmup_seconds": args.warmup_seconds,
        "peak_bytes_per_worker": args.peak_bytes_per_worker,
        "slope_upper_mib_per_hour": args.slope_upper_mib_per_hour,
        "forced_restart_after_seconds": args.force_restart_after_seconds,
        "request_cap": args.request_cap, "game_timeout": args.game_timeout,
        "max_evidence_bytes": args.max_evidence_bytes, "seed": args.seed, "training": False,
    }
    run_id = unique_run_id("g1r-rss-soak")
    run_dir = (args.output or repo / "runs" / run_id).resolve()
    if args.resume:
        plan = json.loads((run_dir / "run-plan.json").read_text(encoding="utf-8"))
        if plan["config_sha256"] != stable_hash(run_config):
            raise ValueError("resume arguments differ from immutable soak plan")
        run_id = plan["run_id"]
    else:
        if shutil.disk_usage(run_dir.parent).free < args.max_evidence_bytes * 2:
            raise ValueError("soak disk preflight failed")
        run_dir.mkdir(parents=True, exist_ok=False)
        plan = {
            "schema_version": 1, "run_id": run_id, "started_epoch": time.time(),
            "config": run_config, "config_sha256": stable_hash(run_config),
            "repository": git_state(repo), "platform": platform_record(),
            "source_sha256": source_tree_hash(repo), "command": list(os.sys.argv),
            "loaded_artifacts": {
                "engine_library": sha256_file(engine_root / "cg" / "libcg.so"),
                "game_wrapper": sha256_file(engine_root / "cg" / "game.py"),
                "api_wrapper": sha256_file(engine_root / "cg" / "api.py"),
                "sim_wrapper": sha256_file(engine_root / "cg" / "sim.py"),
                "card_data": sha256_file(card_data),
                "default_deck": sha256_file(default_deck),
                "private_baseline_receipts": {
                    path.parent.name: sha256_file(path)
                    for path in sorted(private_baselines.glob("*/receipt.json"))
                },
            },
            "resumable": True, "training_performed": False,
        }
        write_immutable_json(run_dir / "run-plan.json", plan)

    worker_config = {
        "repo": str(repo), "engine_root": engine_root, "card_data": card_data,
        "default_deck": default_deck, "private_baselines": private_baselines,
        "policy0": args.policy, "policy1": args.policy, "request_cap": args.request_cap,
        "game_timeout": args.game_timeout, "seed": args.seed,
        "failure_directory": str(run_dir / "failures"),
    }
    context = mp.get_context("spawn")
    stop = context.Event()
    events = context.Queue()
    session_id = uuid.uuid4().hex
    processes: dict[int, mp.Process] = {}
    process_keys: dict[int, str] = {}
    process_started: dict[str, float] = {}
    active_game: dict[int, str] = {}
    samples: dict[str, list[tuple[float, int]]] = {}
    if args.resume and (run_dir / "events.jsonl").exists():
        for line in (run_dir / "events.jsonl").read_text().splitlines():
            event = json.loads(line)
            if event.get("kind") == "worker_started" and event.get("process_key"):
                process_started[event["process_key"]] = event["time"]
        if (run_dir / "rss-samples.jsonl").exists():
            for line in (run_dir / "rss-samples.jsonl").read_text().splitlines():
                sample = json.loads(line)
                samples.setdefault(sample["process_key"], []).append(
                    (sample["time"], sample["rss_bytes"])
                )

    def start_worker(slot: int) -> None:
        process = context.Process(
            target=_worker, args=(slot, worker_config, stop, events), daemon=False
        )
        process.start()
        processes[slot] = process
        key = f"{session_id}:{process.pid}"
        process_keys[slot] = key
        process_started[key] = time.time()
        _append(run_dir / "events.jsonl", {"kind": "worker_started", "slot": slot,
                "pid": process.pid, "process_key": key, "time": time.time()})

    prior_active_seconds = _completed_session_seconds(samples)
    session_started_epoch = time.time()
    for slot in range(args.workers):
        start_worker(slot)
    remaining_seconds = max(0.0, args.duration_seconds - prior_active_seconds)
    end_epoch = session_started_epoch + remaining_seconds
    next_sample = time.time()
    restart_done = any(
        json.loads(line).get("kind") == "forced_worker_death"
        for line in (run_dir / "events.jsonl").read_text().splitlines()
    ) if (run_dir / "events.jsonl").exists() else False
    games_completed = 0
    sample_number = sum(len(values) for values in samples.values()) // args.workers
    evidence_cap_exceeded = False
    while time.time() < end_epoch:
        now = time.time()
        for slot, process in tuple(processes.items()):
            if not process.is_alive():
                process.join()
                _append(run_dir / "events.jsonl", {
                    "kind": "unexpected_worker_death", "slot": slot, "pid": process.pid,
                    "process_key": process_keys[slot],
                    "game_id": active_game.pop(slot, None), "exit_code": process.exitcode,
                    "time": now,
                })
                start_worker(slot)
        if now >= next_sample:
            for slot, process in processes.items():
                rss = _rss(process.pid)
                if rss is not None:
                    key = process_keys[slot]
                    samples.setdefault(key, []).append((now, rss))
                    _append(run_dir / "rss-samples.jsonl", {"slot": slot, "pid": process.pid,
                            "process_key": key, "time": now, "rss_bytes": rss})
            sample_number += 1
            if sample_number % 10 == 0:
                checkpoint = {"schema_version": 1, "run_id": run_id,
                              "sample_number": sample_number, "time": now,
                              "games_completed_this_session": games_completed}
                path = run_dir / "checkpoints" / f"sample-{sample_number:06d}.json"
                write_immutable_json(path, checkpoint)
                path.with_suffix(".json.sha256").write_text(
                    f"{sha256_file(path)}  {path.name}\n", encoding="ascii"
                )
            next_sample += args.sample_seconds
            evidence_bytes = sum(
                path.stat().st_size for path in (
                    run_dir / "events.jsonl", run_dir / "games.jsonl",
                    run_dir / "rss-samples.jsonl",
                ) if path.exists()
            )
            if evidence_bytes > args.max_evidence_bytes:
                evidence_cap_exceeded = True
                _append(run_dir / "events.jsonl", {
                    "kind": "evidence_cap_exceeded", "bytes": evidence_bytes,
                    "limit": args.max_evidence_bytes, "time": now,
                })
                break
        if (not restart_done and args.force_restart_after_seconds is not None
                and prior_active_seconds + now - session_started_epoch
                >= args.force_restart_after_seconds):
            slot = 0
            process = processes[slot]
            process.terminate()
            process.join(10)
            _append(run_dir / "events.jsonl", {"kind": "forced_worker_death", "slot": slot,
                    "pid": process.pid, "process_key": process_keys[slot],
                    "game_id": active_game.get(slot),
                    "exit_code": process.exitcode, "time": time.time()})
            start_worker(slot)
            restart_done = True
        try:
            event = events.get(timeout=min(0.25, max(0.01, end_epoch - time.time())))
        except queue.Empty:
            continue
        if event["kind"] == "game_started":
            active_game[event["slot"]] = event["game_id"]
        else:
            active_game.pop(event["slot"], None)
            _append(run_dir / "games.jsonl", event["record"])
            games_completed += int(event["record"]["status"] == "pass")
    stop.set()
    for process in processes.values():
        process.join(args.game_timeout + 10)
        if process.is_alive():
            process.terminate()
            process.join(10)

    total_games_completed = total_failures = 0
    if (run_dir / "games.jsonl").exists():
        with (run_dir / "games.jsonl").open(encoding="utf-8") as source:
            for line in source:
                record = json.loads(line)
                total_games_completed += record["status"] == "pass"
                total_failures += record["status"] != "pass"
    event_records = [json.loads(line) for line in (run_dir / "events.jsonl").read_text().splitlines()]
    total_failures += sum(event["kind"] == "unexpected_worker_death" for event in event_records)
    total_expected_deaths = sum(
        event["kind"] == "forced_worker_death" for event in event_records
    )
    slope_results = {}
    peak = 0
    for pid, values in samples.items():
        peak = max(peak, *(rss for _, rss in values))
        eligible = [point for point in values if point[0] - process_started[pid] >= args.warmup_seconds]
        slope_results[str(pid)] = {"samples": len(values), "eligible_samples": len(eligible),
                                   "slope": _slope_ci(eligible)}
    eligible_slopes = [value["slope"] for value in slope_results.values()
                       if value["slope"] is not None]
    active_seconds_observed = prior_active_seconds + min(
        remaining_seconds, max(0.0, time.time() - session_started_epoch)
    )
    enough_duration = active_seconds_observed >= args.duration_seconds
    pass_slope = bool(eligible_slopes) and all(
        slope["upper_95_mib_per_hour"] <= args.slope_upper_mib_per_hour
        for slope in eligible_slopes
    )
    passed = (enough_duration and not evidence_cap_exceeded and restart_done and total_failures == 0
              and peak <= args.peak_bytes_per_worker and pass_slope)
    path = run_dir / "run_manifest.json"
    manifest = {
        **technical_run_envelope(repo, path, run_id, "ptcg.g1r.rss-soak", passed),
        "duration_seconds_required": args.duration_seconds,
        "duration_seconds_observed": active_seconds_observed,
        "wall_seconds_since_first_start": time.time() - plan["started_epoch"],
        "games_completed": total_games_completed,
        "games_completed_this_session": games_completed,
        "unexpected_failures": total_failures,
        "expected_worker_deaths": total_expected_deaths,
        "worker_replacement_verified": restart_done,
        "evidence_cap_exceeded": evidence_cap_exceeded,
        "rss_sample_period_seconds": args.sample_seconds,
        "warmup_exclusion_seconds_per_process": args.warmup_seconds,
        "peak_rss_bytes": peak, "peak_ceiling_bytes_per_worker": args.peak_bytes_per_worker,
        "slope_estimator": "Theil-Sen; deterministic 500-resample bootstrap 95% CI",
        "slope_upper_threshold_mib_per_hour_per_worker": args.slope_upper_mib_per_hour,
        "processes": slope_results,
        "run_plan_sha256": sha256_file(run_dir / "run-plan.json"),
        "config": plan["config"], "repository": plan["repository"],
        "platform": plan["platform"], "source_sha256": plan["source_sha256"],
        "loaded_artifacts": plan["loaded_artifacts"],
        "training_performed": False, "local_cost_usd": 0.0,
    }
    write_immutable_json(path, manifest)
    path.with_suffix(".json.sha256").write_text(
        f"{sha256_file(path)}  {path.name}\n", encoding="ascii"
    )
    return manifest
