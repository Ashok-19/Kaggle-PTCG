from __future__ import annotations

import argparse
import hashlib
import json
import math
import multiprocessing as mp
import os
import platform
import resource
import subprocess
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from multiprocessing.connection import Connection, wait
from pathlib import Path
from queue import Empty
from typing import Any, Mapping, Sequence

import numpy as np
import torch

from ptcg_rl.g1.environment import DevelopmentEpisodeError, EpisodeEnvironmentV1, FailureMode
from ptcg_rl.g1.evidence import sha256_file
from ptcg_rl.g1.models import SchemaMetadataV1
from ptcg_rl.g1.native import NativeCABTTransport, load_deck
from ptcg_rl.g2.checkpoint import load_checkpoint_package
from ptcg_rl.g2.network import PolicyConfigV1
from ptcg_rl.g2.reliability import (
    AuditedRecurrentLedgerV1,
    PolicyAuditV1,
    RELIABILITY_RECORD_ID,
    ReliabilityError,
    RemoteNeuralPolicyV1,
    canonical_json_line,
    execute_inference_batch,
    game_record,
    read_game_records,
    recalculate_reliability,
    validate_game_record,
)

SOURCE_FILES = (
    "configs/g2_policy_v1.json",
    "scripts/g2_neural_reliability.py",
    "src/ptcg_rl/__init__.py",
    "src/ptcg_rl/g1/__init__.py",
    "src/ptcg_rl/g1/actions.py",
    "src/ptcg_rl/g1/environment.py",
    "src/ptcg_rl/g1/evidence.py",
    "src/ptcg_rl/g1/models.py",
    "src/ptcg_rl/g1/native.py",
    "src/ptcg_rl/g1/recurrent.py",
    "src/ptcg_rl/g1/semantic.py",
    "src/ptcg_rl/g2/__init__.py",
    "src/ptcg_rl/g2/card_table.py",
    "src/ptcg_rl/g2/checkpoint.py",
    "src/ptcg_rl/g2/models.py",
    "src/ptcg_rl/g2/network.py",
    "src/ptcg_rl/g2/projection.py",
    "src/ptcg_rl/g2/reliability.py",
)
CHECKPOINT_REPORT = "reports/artifacts/g2-policy-checkpoint-v1.json"
PARITY_REPORT = "reports/evaluations/g2-policy-cpu-gpu-parity-v4.json"
DEFAULT_ENGINE_ROOT = "private/assets/official/sample_submission/sample_submission"
DEFAULT_CARD_DATA = "private/assets/official/EN_Card_Data.csv"
DEFAULT_DECK = f"{DEFAULT_ENGINE_ROOT}/deck.csv"
DEFAULT_GAMES = 10_000
DEFAULT_WORKERS_PER_DEVICE = 8
DEFAULT_MAX_BATCH = 8
DEFAULT_BATCH_WAIT_MS = 2.0
DEFAULT_GAME_TIMEOUT_SECONDS = 300.0
DEFAULT_RUN_TIMEOUT_SECONDS = 14_400.0
MAX_RESULT_QUEUE_WAIT_SECONDS = 2.0
PEAK_PROCESS_RSS_LIMIT_MIB = 6 * 1024.0


class RunnerError(RuntimeError):
    pass


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def file_record(path: Path) -> dict[str, Any]:
    return {
        "path": path.as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RunnerError(f"cannot read JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise RunnerError(f"JSON root must be an object: {path}")
    return value


def git(root: Path, *arguments: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *arguments], cwd=root, text=True, stderr=subprocess.STDOUT
        ).strip()
    except subprocess.CalledProcessError as error:
        raise RunnerError(
            f"git {' '.join(arguments)} failed: {error.output.strip()}"
        ) from error


def verify_source_allowlist(root: Path) -> tuple[str, list[dict[str, Any]]]:
    head = git(root, "rev-parse", "HEAD")
    if len(head) != 40:
        raise RunnerError("Git HEAD is not a full commit SHA")
    tracked = git(root, "ls-files", "--", *SOURCE_FILES).splitlines()
    if sorted(tracked) != sorted(SOURCE_FILES):
        raise RunnerError(
            "reliability source allowlist is not exactly tracked: "
            f"missing={sorted(set(SOURCE_FILES) - set(tracked))}, "
            f"unexpected={sorted(set(tracked) - set(SOURCE_FILES))}"
        )
    dirty = git(
        root,
        "status",
        "--porcelain",
        "--untracked-files=all",
        "--",
        *SOURCE_FILES,
    ).splitlines()
    if dirty:
        raise RunnerError(f"reliability source allowlist differs from HEAD: {dirty}")
    records = []
    for relative in SOURCE_FILES:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise RunnerError(f"source file is missing or a symlink: {relative}")
        records.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return head, records


def checkpoint_context(root: Path) -> dict[str, Any]:
    report_path = root / CHECKPOINT_REPORT
    report = read_json(report_path)
    if report.get("status") != "SUCCEEDED":
        raise RunnerError("checkpoint report is not SUCCEEDED")
    package = report.get("private_artifacts", {}).get("package")
    model = report.get("model")
    if not isinstance(package, Mapping) or not isinstance(model, Mapping):
        raise RunnerError("checkpoint report structure differs")
    package_path = root / str(package.get("path"))
    if not package_path.is_file():
        raise RunnerError("qualified checkpoint package is missing")
    if (
        package_path.stat().st_size != package.get("bytes")
        or sha256_file(package_path) != package.get("sha256")
    ):
        raise RunnerError("checkpoint package bytes differ from the public report")
    parity_path = root / PARITY_REPORT
    parity = read_json(parity_path)
    if parity.get("status") != "SUCCEEDED" or parity.get("decision") != "PASS":
        raise RunnerError("CPU/T4 parity evidence is not a PASS")
    if parity.get("identity", {}).get("qualification_state_sha256") != model.get(
        "qualification_state_sha256"
    ):
        raise RunnerError("checkpoint state differs from parity state")
    config_record = read_json(root / "configs/g2_policy_v1.json")
    policy_config = config_record.get("policy_config")
    if not isinstance(policy_config, Mapping):
        raise RunnerError("tracked policy configuration is missing")
    try:
        verified_config = PolicyConfigV1(**dict(policy_config))
    except (TypeError, ValueError) as error:
        raise RunnerError("tracked policy configuration is invalid") from error
    if verified_config.config_sha256 != model.get("config_sha256"):
        raise RunnerError("tracked policy configuration hash differs from checkpoint report")
    if config_record.get("card_table_sha256") != model.get("card_table_sha256"):
        raise RunnerError("tracked card table hash differs from checkpoint report")
    if config_record.get("model_schema_sha256") != model.get("model_schema_sha256"):
        raise RunnerError("tracked model schema hash differs from checkpoint report")
    return {
        "report": report,
        "report_path": report_path,
        "report_sha256": sha256_file(report_path),
        "package_path": package_path,
        "package": dict(package),
        "model": dict(model),
        "config": dict(policy_config),
        "parity_path": parity_path,
        "parity_sha256": sha256_file(parity_path),
    }


def asset_context(root: Path, engine_root: Path, card_data: Path, deck: Path) -> dict[str, Any]:
    files = {
        "engine_library": engine_root / "cg/libcg.so",
        "engine_wrapper": engine_root / "cg/game.py",
        "card_data": card_data,
        "deck": deck,
    }
    for name, path in files.items():
        if not path.is_file() or path.is_symlink():
            raise RunnerError(f"required asset is missing or a symlink: {name} -> {path}")
    return {
        name: {
            "path": path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for name, path in files.items()
    }


def parse_devices(value: str) -> list[str]:
    devices = [item.strip() for item in value.split(",") if item.strip()]
    if not devices:
        raise argparse.ArgumentTypeError("at least one device is required")
    if len(devices) != len(set(devices)):
        raise argparse.ArgumentTypeError("device list contains duplicates")
    for device in devices:
        if (
            device != "cpu"
            and not device.startswith("cpu:")
            and not device.startswith("cuda:")
        ):
            raise argparse.ArgumentTypeError(f"unsupported device: {device}")
    return devices


def validate_device_topology(devices: Sequence[str], require_t4x2: bool) -> dict[str, Any]:
    cuda_count = torch.cuda.device_count()
    cuda_names = [torch.cuda.get_device_name(index) for index in range(cuda_count)]
    if require_t4x2:
        if list(devices) != ["cuda:0", "cuda:1"]:
            raise RunnerError("T4x2 qualification requires devices cuda:0,cuda:1")
        if cuda_count != 2:
            raise RunnerError(f"expected exactly two visible CUDA devices, observed {cuda_count}")
        if not all("T4" in name for name in cuda_names):
            raise RunnerError(f"expected only NVIDIA T4 devices, observed {cuda_names}")
    for device in devices:
        if device.startswith("cpu:"):
            suffix = device.split(":", 1)[1]
            if not suffix.isdigit():
                raise RunnerError(f"CPU server alias must end in an integer: {device}")
        if device.startswith("cuda:"):
            suffix = device.split(":", 1)[1]
            if not suffix.isdigit():
                raise RunnerError(f"CUDA device index is invalid: {device}")
            index = int(suffix)
            if index >= cuda_count:
                raise RunnerError(f"requested CUDA device is not visible: {device}")
            if not torch.cuda.is_available():
                raise RunnerError("CUDA device requested but torch.cuda is unavailable")
    return {
        "requested_devices": list(devices),
        "cuda_available": torch.cuda.is_available(),
        "visible_cuda_device_count": cuda_count,
        "visible_cuda_device_names": cuda_names,
        "require_t4x2": require_t4x2,
    }


def process_peak_rss_mib() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return float(value) / 1024.0


def load_server_model(root: Path, checkpoint: Mapping[str, Any], device_text: str):
    device = torch.device("cpu" if device_text.startswith("cpu:") else device_text)
    if device.type == "cuda":
        torch.cuda.set_device(device)
        torch.backends.cudnn.enabled = False
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    loaded = load_checkpoint_package(
        root / str(checkpoint["path"]),
        device=device,
        expected_package_sha256=str(checkpoint["sha256"]),
        expected_source_commit=None,
        source_root=root,
    )
    loaded.model.eval()
    return loaded.model, device


def inference_server_process(
    root_text: str,
    server_id: int,
    device_text: str,
    checkpoint: dict[str, Any],
    connections: list[Connection],
    max_batch: int,
    batch_wait_ms: float,
    result_queue: Any,
) -> None:
    root = Path(root_text)
    histogram: Counter[int] = Counter()
    calls = 0
    decisions = 0
    total_ms = 0.0
    max_ms = 0.0
    errors: list[str] = []
    active = list(connections)
    try:
        model, device = load_server_model(root, checkpoint, device_text)
        while active:
            ready = wait(active, timeout=1.0)
            if not ready:
                continue
            pending: list[tuple[Connection, dict[str, Any]]] = []
            for connection in ready:
                try:
                    message = connection.recv()
                except (EOFError, OSError):
                    if connection in active:
                        active.remove(connection)
                    continue
                if message.get("kind") == "done":
                    if connection in active:
                        active.remove(connection)
                else:
                    pending.append((connection, message))
            deadline = time.perf_counter() + batch_wait_ms / 1_000.0
            while len(pending) < max_batch and active and time.perf_counter() < deadline:
                additional = wait(active, timeout=max(0.0, deadline - time.perf_counter()))
                if not additional:
                    break
                for connection in additional:
                    try:
                        message = connection.recv()
                    except (EOFError, OSError):
                        if connection in active:
                            active.remove(connection)
                        continue
                    if message.get("kind") == "done":
                        if connection in active:
                            active.remove(connection)
                    else:
                        pending.append((connection, message))
                    if len(pending) >= max_batch:
                        break
            if not pending:
                continue
            started = time.perf_counter()
            responses = execute_inference_batch(
                model, [message for _, message in pending], device
            )
            if device.type == "cuda":
                torch.cuda.synchronize(device)
            elapsed_ms = (time.perf_counter() - started) * 1_000.0
            batch_size = len(pending)
            histogram[batch_size] += 1
            calls += 1
            decisions += batch_size
            total_ms += elapsed_ms
            max_ms = max(max_ms, elapsed_ms)
            for (connection, message), response in zip(pending, responses, strict=True):
                connection.send(
                    {
                        "kind": "response",
                        "request_id": message.get("request_id"),
                        "server_id": server_id,
                        "batch_size": batch_size,
                        "server_ms": elapsed_ms,
                        **response,
                    }
                )
    except Exception as error:
        errors.append(f"{type(error).__name__}: {error}")
        for connection in active:
            try:
                connection.send({"kind": "error", "error": errors[-1]})
            except Exception:
                pass
    finally:
        result_queue.put(
            {
                "kind": "server_done",
                "server_id": server_id,
                "device": device_text,
                "batch_histogram": dict(sorted(histogram.items())),
                "inference_calls": calls,
                "decisions": decisions,
                "total_inference_ms": total_ms,
                "max_batch_inference_ms": max_ms,
                "errors": errors,
                "peak_rss_mib": process_peak_rss_mib(),
            }
        )


def worker_process(
    root_text: str,
    worker_id: int,
    server_id: int,
    connection: Connection,
    hidden_size: int,
    engine_root_text: str,
    card_data_text: str,
    deck_text: str,
    game_indices: list[int],
    game_timeout_seconds: float,
    result_queue: Any,
) -> None:
    root = Path(root_text)
    engine_root = Path(engine_root_text)
    card_data = Path(card_data_text)
    deck_path = Path(deck_text)
    completed = 0
    errors: list[str] = []
    started = time.monotonic()
    try:
        metadata = SchemaMetadataV1.build(
            sha256_file(engine_root / "cg/libcg.so"), sha256_file(card_data)
        )
        deck = load_deck(deck_path)
        for game_index in game_indices:
            episode_id = f"g2-neural-reliability-{game_index:05d}"
            audits = {player: PolicyAuditV1() for player in (0, 1)}
            policies = {
                player: RemoteNeuralPolicyV1(
                    connection,
                    worker_id,
                    server_id,
                    player,
                    hidden_size,
                    audits[player],
                )
                for player in (0, 1)
            }
            ledger = AuditedRecurrentLedgerV1()
            environment = EpisodeEnvironmentV1(
                NativeCABTTransport(engine_root),
                metadata,
                max_requests=20_000,
                deadline_monotonic=time.monotonic() + game_timeout_seconds,
                failure_directory=root / "private/g2/reliability-v1/failures",
                failure_mode=FailureMode.DEVELOPMENT,
                recurrent_ledger=ledger,
            )
            try:
                result = environment.run(episode_id, deck, deck, policies)
            except DevelopmentEpisodeError as error:
                result = error.result
            record = game_record(
                result,
                audits,
                ledger,
                worker_id,
                server_id,
                game_index,
            )
            result_queue.put({"kind": "game", "record": record})
            completed += 1
            if validate_game_record(record):
                break
    except Exception as error:
        errors.append(f"{type(error).__name__}: {error}")
    finally:
        try:
            connection.send({"kind": "done"})
        except Exception:
            pass
        result_queue.put(
            {
                "kind": "worker_done",
                "worker_id": worker_id,
                "server_id": server_id,
                "assigned_games": len(game_indices),
                "completed_games": completed,
                "errors": errors,
                "wall_seconds": time.monotonic() - started,
                "peak_rss_mib": process_peak_rss_mib(),
            }
        )


def validate_process_evidence(
    worker_records: Sequence[Mapping[str, Any]],
    server_records: Sequence[Mapping[str, Any]],
    *,
    expected_workers: int,
    expected_servers: int,
    expected_engine_requests: int,
    max_batch: int,
    parent_peak_rss_mib: float,
) -> dict[str, Any]:
    failures: list[str] = []
    valid_expected_workers = (
        isinstance(expected_workers, int)
        and not isinstance(expected_workers, bool)
        and expected_workers >= 0
    )
    valid_expected_servers = (
        isinstance(expected_servers, int)
        and not isinstance(expected_servers, bool)
        and expected_servers >= 0
    )
    valid_expected_requests = (
        isinstance(expected_engine_requests, int)
        and not isinstance(expected_engine_requests, bool)
        and expected_engine_requests >= 0
    )
    valid_max_batch = (
        isinstance(max_batch, int) and not isinstance(max_batch, bool) and max_batch > 0
    )
    if not all(
        (
            valid_expected_workers,
            valid_expected_servers,
            valid_expected_requests,
            valid_max_batch,
        )
    ):
        failures.append("expected process accounting values are invalid")
    safe_expected_workers = expected_workers if valid_expected_workers else 0
    safe_expected_servers = expected_servers if valid_expected_servers else 0
    safe_expected_requests = expected_engine_requests if valid_expected_requests else 0
    safe_max_batch = max_batch if valid_max_batch else 1
    worker_ids = [record.get("worker_id") for record in worker_records]
    server_ids = [record.get("server_id") for record in server_records]
    valid_worker_ids = all(
        isinstance(value, int) and not isinstance(value, bool) for value in worker_ids
    )
    valid_server_ids = all(
        isinstance(value, int) and not isinstance(value, bool) for value in server_ids
    )
    if not valid_worker_ids or sorted(worker_ids) != list(range(safe_expected_workers)):
        failures.append("worker record identity set differs")
    if not valid_server_ids or sorted(server_ids) != list(range(safe_expected_servers)):
        failures.append("server record identity set differs")
    for record in worker_records:
        worker_id = record.get("worker_id")
        if record.get("errors") != []:
            failures.append(f"worker {worker_id} reported errors")
        if record.get("completed_games") != record.get("assigned_games"):
            failures.append(f"worker {worker_id} did not complete every assigned game")
        rss = record.get("peak_rss_mib")
        if (
            isinstance(rss, bool)
            or not isinstance(rss, (int, float))
            or not math.isfinite(float(rss))
            or float(rss) >= PEAK_PROCESS_RSS_LIMIT_MIB
        ):
            failures.append(f"worker {worker_id} peak RSS is invalid or above limit")
    server_decisions = 0
    for record in server_records:
        server_id = record.get("server_id")
        if record.get("errors") != []:
            failures.append(f"server {server_id} reported errors")
        decisions = record.get("decisions")
        calls = record.get("inference_calls")
        histogram = record.get("batch_histogram")
        if (
            isinstance(decisions, bool)
            or not isinstance(decisions, int)
            or decisions < 0
            or isinstance(calls, bool)
            or not isinstance(calls, int)
            or calls < 0
            or not isinstance(histogram, Mapping)
        ):
            failures.append(f"server {server_id} accounting metadata is invalid")
            continue
        histogram_calls = 0
        histogram_decisions = 0
        for raw_batch_size, raw_count in histogram.items():
            try:
                batch_size = int(raw_batch_size)
            except (TypeError, ValueError):
                failures.append(f"server {server_id} batch histogram key is invalid")
                continue
            if (
                batch_size <= 0
                or batch_size > safe_max_batch
                or isinstance(raw_count, bool)
                or not isinstance(raw_count, int)
                or raw_count < 0
            ):
                failures.append(f"server {server_id} batch histogram value is invalid")
                continue
            histogram_calls += raw_count
            histogram_decisions += batch_size * raw_count
        if histogram_calls != calls or histogram_decisions != decisions:
            failures.append(f"server {server_id} histogram accounting differs")
        server_decisions += decisions
        rss = record.get("peak_rss_mib")
        if (
            isinstance(rss, bool)
            or not isinstance(rss, (int, float))
            or not math.isfinite(float(rss))
            or float(rss) >= PEAK_PROCESS_RSS_LIMIT_MIB
        ):
            failures.append(f"server {server_id} peak RSS is invalid or above limit")
    if server_decisions != safe_expected_requests:
        failures.append("server decision count differs from engine requests")
    if (
        isinstance(parent_peak_rss_mib, bool)
        or not isinstance(parent_peak_rss_mib, (int, float))
        or not math.isfinite(float(parent_peak_rss_mib))
        or float(parent_peak_rss_mib) >= PEAK_PROCESS_RSS_LIMIT_MIB
    ):
        failures.append("parent peak RSS is invalid or above limit")
    rss_values = [float(parent_peak_rss_mib)]
    rss_values.extend(
        float(record["peak_rss_mib"])
        for record in worker_records
        if isinstance(record.get("peak_rss_mib"), (int, float))
        and not isinstance(record.get("peak_rss_mib"), bool)
    )
    rss_values.extend(
        float(record["peak_rss_mib"])
        for record in server_records
        if isinstance(record.get("peak_rss_mib"), (int, float))
        and not isinstance(record.get("peak_rss_mib"), bool)
    )
    return {
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "expected_workers": safe_expected_workers,
        "observed_workers": len(worker_records),
        "expected_servers": safe_expected_servers,
        "observed_servers": len(server_records),
        "expected_engine_requests": safe_expected_requests,
        "server_decisions": server_decisions,
        "peak_process_rss_limit_mib": PEAK_PROCESS_RSS_LIMIT_MIB,
        "max_observed_process_rss_mib": max(rss_values, default=None),
    }


def atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def initial_receipt(
    source_commit: str,
    source_files: list[dict[str, Any]],
    topology: Mapping[str, Any],
    assets: Mapping[str, Any],
    checkpoint: Mapping[str, Any],
    games_path: Path,
    review_path: Path,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "record_id": f"{RELIABILITY_RECORD_ID}-receipt",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "updated_at_utc": datetime.now(UTC).isoformat(),
        "status": "RUNNING",
        "source_commit": source_commit,
        "source_files": source_files,
        "topology": dict(topology),
        "assets": dict(assets),
        "checkpoint": dict(checkpoint),
        "outputs": {
            "games": {"path": games_path.as_posix()},
            "review": {"path": review_path.as_posix()},
        },
        "process_failures": [],
        "server_failures": [],
        "workers": [],
        "servers": [],
        "authorization": {
            "optimizer_created": False,
            "optimizer_steps": 0,
            "training_loop_ran": False,
            "training_state_included": False,
            "ppo_ran": False,
            "kaggle_run_launched_by_script": False,
        },
        "cost_usd": 0.0,
    }


def terminate_processes(processes: Sequence[mp.Process]) -> None:
    for process in processes:
        if process.is_alive():
            process.terminate()
    for process in processes:
        if process.is_alive():
            process.join(timeout=10)


def run_command(args: argparse.Namespace) -> dict[str, Any]:
    root = args.root.resolve()
    output_directory = args.output_dir.resolve()
    games_path = output_directory / "g2-neural-reliability-v1-games.jsonl"
    review_path = output_directory / "g2-neural-reliability-v1-review.json"
    receipt_path = output_directory / "g2-neural-reliability-v1-receipt.json"
    for path in (games_path, review_path, receipt_path):
        if path.exists() and not args.overwrite:
            raise RunnerError(f"output exists; use --overwrite: {path}")
    output_directory.mkdir(parents=True, exist_ok=True)
    for path in (games_path, review_path, receipt_path):
        path.unlink(missing_ok=True)

    source_commit, source_files = verify_source_allowlist(root)
    checkpoint = checkpoint_context(root)
    engine_root = (root / args.engine_root).resolve()
    card_data = (root / args.card_data).resolve()
    deck = (root / args.deck).resolve()
    assets = asset_context(root, engine_root, card_data, deck)
    topology = validate_device_topology(args.devices, args.require_t4x2)
    if args.games <= 0 or args.workers_per_device <= 0 or args.max_batch <= 0:
        raise RunnerError("game, worker and batch counts must be positive")
    if args.batch_wait_ms < 0 or args.game_timeout_seconds <= 0:
        raise RunnerError("batch wait and game timeout values are invalid")
    total_workers = len(args.devices) * args.workers_per_device
    topology.update(
        {
            "games": args.games,
            "servers": len(args.devices),
            "workers_per_device": args.workers_per_device,
            "total_workers": total_workers,
            "max_batch": args.max_batch,
            "batch_wait_ms": args.batch_wait_ms,
            "game_timeout_seconds": args.game_timeout_seconds,
            "run_timeout_seconds": args.run_timeout_seconds,
            "multiprocessing_start_method": "spawn",
        }
    )
    receipt = initial_receipt(
        source_commit,
        source_files,
        topology,
        assets,
        {
            "report_path": CHECKPOINT_REPORT,
            "report_sha256": checkpoint["report_sha256"],
            "package_path": checkpoint["package"]["path"],
            "package_bytes": checkpoint["package"]["bytes"],
            "package_sha256": checkpoint["package"]["sha256"],
            "qualification_state_sha256": checkpoint["model"][
                "qualification_state_sha256"
            ],
            "parity_path": PARITY_REPORT,
            "parity_sha256": checkpoint["parity_sha256"],
        },
        games_path,
        review_path,
    )
    atomic_json(receipt_path, receipt)

    context = mp.get_context("spawn")
    result_queue = context.Queue()
    server_pairs: list[list[tuple[Connection, Connection]]] = []
    for _ in args.devices:
        server_pairs.append(
            [context.Pipe(duplex=True) for _ in range(args.workers_per_device)]
        )
    servers: list[mp.Process] = []
    workers: list[mp.Process] = []
    worker_id = 0
    hidden_size = int(checkpoint["config"]["public_hidden"])
    for server_id, device in enumerate(args.devices):
        server_connections = [pair[0] for pair in server_pairs[server_id]]
        server = context.Process(
            target=inference_server_process,
            args=(
                str(root),
                server_id,
                device,
                dict(checkpoint["package"]),
                server_connections,
                args.max_batch,
                args.batch_wait_ms,
                result_queue,
            ),
            name=f"inference-server-{server_id}",
        )
        servers.append(server)
        for local_worker_index, pair in enumerate(server_pairs[server_id]):
            assigned_worker_id = worker_id
            game_indices = list(range(assigned_worker_id, args.games, total_workers))
            worker = context.Process(
                target=worker_process,
                args=(
                    str(root),
                    assigned_worker_id,
                    server_id,
                    pair[1],
                    hidden_size,
                    str(engine_root),
                    str(card_data),
                    str(deck),
                    game_indices,
                    args.game_timeout_seconds,
                    result_queue,
                ),
                name=f"engine-worker-{server_id}-{local_worker_index}",
            )
            workers.append(worker)
            worker_id += 1

    started = time.monotonic()
    all_processes = servers + workers
    process_failures: list[str] = []
    server_failures: list[str] = []
    server_records: dict[int, dict[str, Any]] = {}
    worker_records: dict[int, dict[str, Any]] = {}
    observed_indices: set[int] = set()
    fail_fast = False
    games_handle = games_path.open("wb")
    try:
        for server in servers:
            server.start()
        for worker in workers:
            worker.start()
        for pairs in server_pairs:
            for server_connection, worker_connection in pairs:
                server_connection.close()
                worker_connection.close()
        while True:
            elapsed = time.monotonic() - started
            if elapsed > args.run_timeout_seconds:
                process_failures.append("global run timeout")
                fail_fast = True
            try:
                message = result_queue.get(timeout=MAX_RESULT_QUEUE_WAIT_SECONDS)
            except Empty:
                message = None
            if message is not None:
                kind = message.get("kind")
                if kind == "game":
                    record = message.get("record")
                    if not isinstance(record, dict):
                        process_failures.append("worker emitted a non-object game record")
                        fail_fast = True
                    else:
                        game_index = record.get("game_index")
                        if (
                            isinstance(game_index, bool)
                            or not isinstance(game_index, int)
                            or game_index in observed_indices
                        ):
                            process_failures.append(
                                f"duplicate or invalid game index: {game_index}"
                            )
                            fail_fast = True
                        else:
                            observed_indices.add(game_index)
                            failures = validate_game_record(record)
                            games_handle.write(canonical_json_line(record))
                            games_handle.flush()
                            if len(observed_indices) % 100 == 0:
                                os.fsync(games_handle.fileno())
                            if failures:
                                process_failures.append(
                                    f"game {game_index} failed: {'; '.join(failures)}"
                                )
                                fail_fast = True
                elif kind == "worker_done":
                    worker_records[int(message["worker_id"])] = dict(message)
                    if message.get("errors"):
                        process_failures.extend(
                            f"worker {message['worker_id']}: {error}"
                            for error in message["errors"]
                        )
                        fail_fast = True
                elif kind == "server_done":
                    server_records[int(message["server_id"])] = dict(message)
                    if message.get("errors"):
                        server_failures.extend(
                            f"server {message['server_id']}: {error}"
                            for error in message["errors"]
                        )
                        fail_fast = True
                else:
                    process_failures.append(f"unexpected result message kind: {kind}")
                    fail_fast = True
            for process in all_processes:
                if process.exitcode is not None and process.exitcode != 0:
                    failure = f"{process.name} exited with code {process.exitcode}"
                    if failure not in process_failures:
                        process_failures.append(failure)
                        fail_fast = True
            if fail_fast:
                break
            if len(worker_records) == len(workers) and len(server_records) == len(servers):
                break
    except KeyboardInterrupt:
        process_failures.append("run interrupted")
        fail_fast = True
    finally:
        games_handle.flush()
        os.fsync(games_handle.fileno())
        games_handle.close()
        if fail_fast:
            terminate_processes(all_processes)
        else:
            for process in workers:
                process.join(timeout=30)
            for process in servers:
                process.join(timeout=30)
            for process in all_processes:
                if process.is_alive():
                    process_failures.append(f"{process.name} did not exit")
                    process.terminate()
                    process.join(timeout=10)
                elif process.exitcode != 0:
                    process_failures.append(
                        f"{process.name} exited with code {process.exitcode}"
                    )

    records, games_sha256, games_bytes = read_game_records(games_path)
    review = recalculate_reliability(
        records,
        args.games,
        process_failures=process_failures,
        server_failures=server_failures,
    )
    parent_peak_rss_mib = process_peak_rss_mib()
    process_evidence = validate_process_evidence(
        [worker_records[index] for index in sorted(worker_records)],
        [server_records[index] for index in sorted(server_records)],
        expected_workers=len(workers),
        expected_servers=len(servers),
        expected_engine_requests=int(review["engine_requests"]),
        max_batch=args.max_batch,
        parent_peak_rss_mib=parent_peak_rss_mib,
    )
    review.update(
        {
            "created_at_utc": datetime.now(UTC).isoformat(),
            "source_commit": source_commit,
            "games_jsonl": {
                "path": games_path.as_posix(),
                "bytes": games_bytes,
                "sha256": games_sha256,
            },
            "process_evidence": process_evidence,
        }
    )
    if process_evidence["status"] != "PASS":
        review["status"] = "FAIL"
    atomic_json(review_path, review)
    receipt.update(
        {
            "updated_at_utc": datetime.now(UTC).isoformat(),
            "status": review["status"],
            "wall_seconds": time.monotonic() - started,
            "process_failures": process_failures,
            "server_failures": server_failures,
            "workers": [worker_records[index] for index in sorted(worker_records)],
            "servers": [server_records[index] for index in sorted(server_records)],
            "review": review,
            "outputs": {
                "games": {
                    "path": games_path.as_posix(),
                    "bytes": games_bytes,
                    "sha256": games_sha256,
                },
                "review": {
                    "path": review_path.as_posix(),
                    "bytes": review_path.stat().st_size,
                    "sha256": sha256_file(review_path),
                },
            },
            "runtime": {
                "python": sys.version,
                "torch": torch.__version__,
                "numpy": np.__version__,
                "platform": platform.platform(),
                "machine": platform.machine(),
                "parent_peak_rss_mib": parent_peak_rss_mib,
            },
        }
    )
    atomic_json(receipt_path, receipt)
    return receipt


def review_command(args: argparse.Namespace) -> dict[str, Any]:
    games_path = args.games.resolve()
    receipt_path = args.receipt.resolve()
    records, games_sha256, games_bytes = read_game_records(games_path)
    if args.expected_games_sha256 and games_sha256 != args.expected_games_sha256:
        raise RunnerError("games JSONL SHA-256 differs from expected")
    receipt_sha256 = sha256_file(receipt_path)
    if args.expected_receipt_sha256 and receipt_sha256 != args.expected_receipt_sha256:
        raise RunnerError("receipt SHA-256 differs from expected")
    receipt = read_json(receipt_path)
    topology = receipt.get("topology")
    outputs = receipt.get("outputs")
    workers = receipt.get("workers")
    servers = receipt.get("servers")
    runtime = receipt.get("runtime")
    if not all(isinstance(value, Mapping) for value in (topology, outputs, runtime)):
        raise RunnerError("receipt topology, outputs or runtime structure differs")
    if not isinstance(workers, list) or not isinstance(servers, list):
        raise RunnerError("receipt worker or server records are missing")
    games_output = outputs.get("games")
    if not isinstance(games_output, Mapping):
        raise RunnerError("receipt games output record is missing")
    if games_output.get("sha256") != games_sha256 or games_output.get("bytes") != games_bytes:
        raise RunnerError("receipt games output identity differs")
    if topology.get("games") != args.expected_games:
        raise RunnerError("receipt expected game count differs")
    review = recalculate_reliability(
        records,
        args.expected_games,
        process_failures=receipt.get("process_failures", []),
        server_failures=receipt.get("server_failures", []),
    )
    try:
        receipt_workers = int(topology.get("total_workers", -1))
        receipt_servers = int(topology.get("servers", -1))
        receipt_max_batch = int(topology.get("max_batch", -1))
        receipt_parent_rss = float(runtime.get("parent_peak_rss_mib", math.nan))
    except (TypeError, ValueError) as error:
        raise RunnerError("receipt process-accounting values are invalid") from error
    process_evidence = validate_process_evidence(
        workers,
        servers,
        expected_workers=receipt_workers,
        expected_servers=receipt_servers,
        expected_engine_requests=int(review["engine_requests"]),
        max_batch=receipt_max_batch,
        parent_peak_rss_mib=receipt_parent_rss,
    )
    receipt_review = receipt.get("review")
    if not isinstance(receipt_review, Mapping):
        raise RunnerError("receipt embedded review is missing")
    comparison_fields = (
        "expected_games",
        "observed_games",
        "complete_game_index_set",
        "failing_game_count",
        "zero_tolerance",
        "engine_requests",
        "meaningful_choices",
        "forced_requests",
        "multi_select_requests",
        "max_observed_options",
        "max_observed_select_count",
        "allocated_inference_ms_per_game",
        "roundtrip_ms_per_game",
        "projected_cpu_host_inference_limit",
    )
    comparison_failures = [
        field_name
        for field_name in comparison_fields
        if receipt_review.get(field_name) != review.get(field_name)
    ]
    review.update(
        {
            "created_at_utc": datetime.now(UTC).isoformat(),
            "games_jsonl": {
                "path": games_path.as_posix(),
                "bytes": games_bytes,
                "sha256": games_sha256,
            },
            "receipt": {
                "path": receipt_path.as_posix(),
                "bytes": receipt_path.stat().st_size,
                "sha256": receipt_sha256,
            },
            "process_evidence": process_evidence,
            "receipt_comparison_failures": comparison_failures,
            "independent_process": True,
        }
    )
    if (
        process_evidence["status"] != "PASS"
        or comparison_failures
        or receipt.get("status") != "PASS"
    ):
        review["status"] = "FAIL"
    atomic_json(args.output.resolve(), review)
    return review


def parser() -> argparse.ArgumentParser:
    root_default = Path(__file__).resolve().parents[1]
    value = argparse.ArgumentParser(
        description="Run or independently review G2 neural-policy reliability qualification"
    )
    commands = value.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run")
    run.add_argument("--root", type=Path, default=root_default)
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument("--games", type=int, default=DEFAULT_GAMES)
    run.add_argument("--devices", type=parse_devices, default=["cpu"])
    run.add_argument("--workers-per-device", type=int, default=DEFAULT_WORKERS_PER_DEVICE)
    run.add_argument("--max-batch", type=int, default=DEFAULT_MAX_BATCH)
    run.add_argument("--batch-wait-ms", type=float, default=DEFAULT_BATCH_WAIT_MS)
    run.add_argument(
        "--game-timeout-seconds", type=float, default=DEFAULT_GAME_TIMEOUT_SECONDS
    )
    run.add_argument(
        "--run-timeout-seconds", type=float, default=DEFAULT_RUN_TIMEOUT_SECONDS
    )
    run.add_argument("--engine-root", type=Path, default=Path(DEFAULT_ENGINE_ROOT))
    run.add_argument("--card-data", type=Path, default=Path(DEFAULT_CARD_DATA))
    run.add_argument("--deck", type=Path, default=Path(DEFAULT_DECK))
    run.add_argument("--require-t4x2", action="store_true")
    run.add_argument("--overwrite", action="store_true")
    run.set_defaults(function=run_command)

    review = commands.add_parser("review")
    review.add_argument("--games", type=Path, required=True)
    review.add_argument("--receipt", type=Path, required=True)
    review.add_argument("--expected-games", type=int, required=True)
    review.add_argument("--expected-games-sha256")
    review.add_argument("--expected-receipt-sha256")
    review.add_argument("--output", type=Path, required=True)
    review.set_defaults(function=review_command)
    return value


def main() -> None:
    args = parser().parse_args()
    try:
        result = args.function(args)
    except (RunnerError, ReliabilityError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit(f"G2 reliability failed closed: {error}") from error
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    if result.get("status") != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
