from __future__ import annotations

import argparse
import gc
import json
import multiprocessing
import os
import pickle
import random
import resource
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, replace
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from bc_train_materialized import (  # noqa: E402
    batch_groups,
    deterministic_order,
    load_all_episodes,
    load_materialized_manifest,
    prepack_mega_groups,
    train_epoch_packed,
    validate_packed,
)
from ptcg_rl.bc.materialized import MaterializedEpisodeV1  # noqa: E402
from ptcg_rl.bc.training import (  # noqa: E402
    PackedMegaRecurrentGroup as PackedRecurrentGroup,
    packed_mega_recurrent_group_to_device,
)
from ptcg_rl.g2.card_table import load_card_table  # noqa: E402
from ptcg_rl.g2.network import PTCGPolicyV1, PolicyConfigV1  # noqa: E402
from ptcg_rl.g3.checkpoint import (  # noqa: E402
    load_training_checkpoint_model_state,
    save_training_checkpoint,
)


class CapacitySweepError(ValueError):
    """Raised when the sequential BC capacity sweep violates its contract."""


def model_configs() -> dict[str, PolicyConfigV1]:
    base = PolicyConfigV1()
    return {
        "970k": base,
        "1.4m": replace(
            base,
            model_width=160,
            entity_heads=5,
            entity_ff_width=320,
            public_hidden=224,
            selection_hidden=128,
            option_width=160,
            max_trainable_parameters=6_000_000,
            target_trainable_parameters=1_500_000,
        ),
        "1.8m": replace(
            base,
            model_width=192,
            entity_heads=6,
            entity_ff_width=384,
            event_hidden=96,
            public_hidden=256,
            selection_hidden=160,
            option_width=192,
            max_trainable_parameters=6_000_000,
            target_trainable_parameters=2_000_000,
        ),
        "2.9m": replace(
            base,
            model_width=224,
            entity_heads=7,
            entity_layers=3,
            entity_ff_width=448,
            card_id_dim=80,
            attack_id_dim=40,
            event_width=80,
            event_hidden=112,
            public_hidden=320,
            selection_hidden=192,
            option_width=224,
            max_trainable_parameters=6_000_000,
            target_trainable_parameters=3_000_000,
        ),
        "3.7m": replace(
            base,
            model_width=256,
            entity_heads=8,
            entity_layers=3,
            entity_ff_width=512,
            card_id_dim=96,
            attack_id_dim=48,
            event_width=96,
            event_hidden=128,
            public_hidden=384,
            selection_hidden=224,
            option_width=256,
            max_trainable_parameters=6_000_000,
            target_trainable_parameters=4_000_000,
        ),
        "5.0m": replace(
            base,
            model_width=288,
            entity_heads=9,
            entity_layers=4,
            entity_ff_width=512,
            card_id_dim=96,
            attack_id_dim=48,
            event_width=96,
            event_hidden=128,
            public_hidden=432,
            selection_hidden=240,
            option_width=288,
            max_trainable_parameters=6_000_000,
            target_trainable_parameters=5_000_000,
        ),
    }


EXPECTED_PARAMETER_COUNTS = {
    "970k": 989_702,
    "1.4m": 1_406_662,
    "1.8m": 1_859_494,
    "2.9m": 2_908_102,
    "3.7m": 3_770_278,
    "5.0m": 5_084_470,
}


def _parse_csv_ints(value: str, label: str) -> tuple[int, ...]:
    try:
        values = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as error:
        raise CapacitySweepError(f"{label} contains a non-integer") from error
    if not values or any(item <= 0 for item in values):
        raise CapacitySweepError(f"{label} must contain positive integers")
    return values


def _parse_csv_floats(value: str, label: str) -> tuple[float, ...]:
    try:
        values = tuple(float(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as error:
        raise CapacitySweepError(f"{label} contains a non-number") from error
    if not values or any(item <= 0 for item in values):
        raise CapacitySweepError(f"{label} must contain positive values")
    return values


def _seed_everything(seed: int, device: torch.device) -> None:
    random.seed(seed)
    np.random.seed(seed % (2**32))
    torch.manual_seed(seed)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(seed)


def _start_gpu_sampler() -> tuple[subprocess.Popen[str], Path, Any]:
    temporary = tempfile.NamedTemporaryFile(prefix="kptcg-capacity-gpu-", suffix=".csv", delete=False)
    path = Path(temporary.name)
    temporary.close()
    handle = path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            "nvidia-smi",
            "--query-gpu=utilization.gpu,memory.used,power.draw",
            "--format=csv,noheader,nounits",
            "--loop-ms=200",
        ],
        stdout=handle,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    return process, path, handle


def _stop_gpu_sampler(process: subprocess.Popen[str], path: Path, handle: Any) -> dict[str, float]:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    handle.close()
    utilization: list[float] = []
    memory: list[float] = []
    power: list[float] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    finally:
        path.unlink(missing_ok=True)
    for line in lines:
        fields = [field.strip() for field in line.split(",")]
        if len(fields) != 3:
            continue
        try:
            utilization.append(float(fields[0]))
            memory.append(float(fields[1]))
            power.append(float(fields[2]))
        except ValueError:
            continue
    if not utilization:
        return {"samples": 0.0}
    return {
        "samples": float(len(utilization)),
        "utilization_mean_percent": sum(utilization) / len(utilization),
        "utilization_peak_percent": max(utilization),
        "memory_mean_mib": sum(memory) / len(memory),
        "memory_peak_mib": max(memory),
        "power_mean_watts": sum(power) / len(power),
        "power_peak_watts": max(power),
    }


def _records_for_split(
    records: Sequence[Mapping[str, Any]],
    split: str,
    *,
    minimum_teacher_score: float | None = None,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for record in records:
        if str(record["split"]) != split:
            continue
        if minimum_teacher_score is not None:
            value = record.get("teacher_score_qualification_value")
            if value is None:
                raise CapacitySweepError("teacher-score filtering requested without score provenance")
            if float(value) < minimum_teacher_score:
                continue
        selected.append(dict(record))
    selected.sort(key=lambda record: int(record["episode_id"]))
    return selected


def _episode_subset(
    episodes: Sequence[MaterializedEpisodeV1],
    allowed_ids: set[int],
) -> list[MaterializedEpisodeV1]:
    return [episode for episode in episodes if episode.episode_id in allowed_ids]


def _validate_cached_episodes(
    episodes: Sequence[MaterializedEpisodeV1],
    records: Sequence[Mapping[str, Any]],
) -> list[MaterializedEpisodeV1]:
    if len(episodes) != len(records):
        raise CapacitySweepError("object-cache episode count differs from manifest records")
    expected = {
        int(record["episode_id"]): (
            str(record["split"]),
            int(record["policy_targets"]),
        )
        for record in records
    }
    observed: dict[int, MaterializedEpisodeV1] = {}
    for episode in episodes:
        if not isinstance(episode, MaterializedEpisodeV1):
            raise CapacitySweepError("object cache contains a non-materialized episode")
        if episode.episode_id in observed:
            raise CapacitySweepError("object cache contains duplicate episode IDs")
        contract = expected.get(episode.episode_id)
        if contract is None:
            raise CapacitySweepError("object cache contains an unexpected episode ID")
        if episode.split != contract[0] or episode.policy_targets != contract[1]:
            raise CapacitySweepError("object-cache episode contract differs from manifest")
        observed[episode.episode_id] = episode
    if set(observed) != set(expected):
        raise CapacitySweepError("object-cache episode ID set differs from manifest")
    return [observed[episode_id] for episode_id in sorted(observed)]


def _load_episode_object_shard(
    root_text: str,
    records: list[dict[str, Any]],
    shard_path_text: str,
) -> dict[str, Any]:
    root = Path(root_text)
    shard_path = Path(shard_path_text)
    episodes = load_all_episodes(root, records, 1)
    with shard_path.open("wb") as handle:
        pickle.dump(tuple(episodes), handle, protocol=pickle.HIGHEST_PROTOCOL)
        handle.flush()
        os.fsync(handle.fileno())
    return {
        "path": str(shard_path),
        "episodes": len(episodes),
        "bytes": shard_path.stat().st_size,
    }


def _parallel_load_materialized_episodes(
    *,
    root: Path,
    records: Sequence[dict[str, Any]],
    processes: int,
    corpus_label: str,
) -> list[MaterializedEpisodeV1]:
    process_count = min(max(1, processes), 8, len(records))
    if process_count == 1:
        return load_all_episodes(root, records, 1)
    chunks = [list(records[index::process_count]) for index in range(process_count)]
    print(
        json.dumps(
            {
                "event": "capacity_parallel_loader_start",
                "corpus": corpus_label,
                "processes": process_count,
                "episodes": len(records),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    started = time.perf_counter()
    context = multiprocessing.get_context("spawn")
    with tempfile.TemporaryDirectory(prefix=f"kptcg-{corpus_label}-objects-") as temporary:
        temporary_root = Path(temporary)
        jobs = [
            (str(root), chunk, str(temporary_root / f"shard-{index:02d}.pkl"))
            for index, chunk in enumerate(chunks)
            if chunk
        ]
        with ProcessPoolExecutor(max_workers=process_count, mp_context=context) as pool:
            futures = [pool.submit(_load_episode_object_shard, *job) for job in jobs]
            receipts = [future.result() for future in futures]
        episodes: list[MaterializedEpisodeV1] = []
        for receipt in receipts:
            with Path(str(receipt["path"])).open("rb") as handle:
                shard = pickle.load(handle)
            if not isinstance(shard, (list, tuple)):
                raise CapacitySweepError("parallel loader shard is not an episode sequence")
            episodes.extend(shard)
    print(
        json.dumps(
            {
                "event": "capacity_parallel_loader_complete",
                "corpus": corpus_label,
                "processes": process_count,
                "episodes": len(episodes),
                "elapsed_seconds": time.perf_counter() - started,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return episodes


def _load_or_build_object_cache(
    *,
    root: Path,
    records: Sequence[dict[str, Any]],
    workers: int,
    manifest_sha256: str,
    cache_path: Path | None,
    corpus_label: str,
) -> tuple[list[MaterializedEpisodeV1], str]:
    meta_path = None if cache_path is None else cache_path.with_name(cache_path.name + ".meta.json")
    if cache_path is not None and meta_path is not None and cache_path.is_file() and meta_path.is_file():
        started = time.perf_counter()
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            expected_meta = {
                "schema_version": 1,
                "kind": "KPTCG_MATERIALIZED_EPISODE_OBJECT_CACHE_V1",
                "source_manifest_sha256": manifest_sha256,
                "episode_count": len(records),
                "payload_bytes": cache_path.stat().st_size,
            }
            if meta != expected_meta:
                raise CapacitySweepError("object-cache metadata differs")
            with cache_path.open("rb") as handle:
                loaded = pickle.load(handle)
            if not isinstance(loaded, (list, tuple)):
                raise CapacitySweepError("object-cache payload is not an episode sequence")
            episodes = _validate_cached_episodes(loaded, records)
            elapsed = time.perf_counter() - started
            print(
                json.dumps(
                    {
                        "event": "capacity_object_cache_hit",
                        "corpus": corpus_label,
                        "episodes": len(episodes),
                        "cache_path": str(cache_path),
                        "cache_bytes": cache_path.stat().st_size,
                        "elapsed_seconds": elapsed,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            return episodes, "cache"
        except Exception as error:
            print(
                json.dumps(
                    {
                        "event": "capacity_object_cache_invalid",
                        "corpus": corpus_label,
                        "cache_path": str(cache_path),
                        "error": f"{type(error).__name__}: {error}",
                    },
                    sort_keys=True,
                ),
                flush=True,
            )

    episodes = _parallel_load_materialized_episodes(
        root=root,
        records=records,
        processes=workers,
        corpus_label=corpus_label,
    )
    episodes = _validate_cached_episodes(episodes, records)
    if cache_path is None or meta_path is None:
        return episodes, "materialized"

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload_partial = cache_path.with_name(cache_path.name + ".partial")
    meta_partial = meta_path.with_name(meta_path.name + ".partial")
    payload_partial.unlink(missing_ok=True)
    meta_partial.unlink(missing_ok=True)
    try:
        with payload_partial.open("wb") as handle:
            pickle.dump(tuple(episodes), handle, protocol=pickle.HIGHEST_PROTOCOL)
            handle.flush()
            os.fsync(handle.fileno())
        payload_bytes = payload_partial.stat().st_size
        meta = {
            "schema_version": 1,
            "kind": "KPTCG_MATERIALIZED_EPISODE_OBJECT_CACHE_V1",
            "source_manifest_sha256": manifest_sha256,
            "episode_count": len(episodes),
            "payload_bytes": payload_bytes,
        }
        meta_partial.write_text(json.dumps(meta, sort_keys=True) + "\n", encoding="utf-8")
        payload_partial.replace(cache_path)
        meta_partial.replace(meta_path)
    finally:
        payload_partial.unlink(missing_ok=True)
        meta_partial.unlink(missing_ok=True)
    print(
        json.dumps(
            {
                "event": "capacity_object_cache_created",
                "corpus": corpus_label,
                "episodes": len(episodes),
                "cache_path": str(cache_path),
                "cache_bytes": cache_path.stat().st_size,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return episodes, "materialized"


def _pack(
    episodes: Sequence[MaterializedEpisodeV1],
    *,
    batch_size: int,
    sequence_length: int,
    seed: int,
    device: torch.device,
) -> tuple[PackedRecurrentGroup, ...]:
    groups = prepack_mega_groups(
        episodes,
        batch_size=batch_size,
        sequence_length=sequence_length,
        seed=seed,
        pin_memory=device.type == "cuda",
    )
    if device.type == "cuda":
        groups = tuple(
            packed_mega_recurrent_group_to_device(group, device, non_blocking=True) for group in groups
        )
        torch.cuda.synchronize(device)
    return groups


def _build_model(
    config: PolicyConfigV1,
    card_table: Any,
    *,
    seed: int,
    device: torch.device,
) -> PTCGPolicyV1:
    _seed_everything(seed, device)
    return PTCGPolicyV1(card_table, config).to(device)


def _one_epoch_smoke(
    *,
    config: PolicyConfigV1,
    card_table: Any,
    train_groups: Sequence[PackedRecurrentGroup],
    validation_groups: Sequence[PackedRecurrentGroup],
    learning_rate: float,
    seed: int,
    device: torch.device,
    bf16: bool,
    maximum_gradient_norm: float,
    weight_decay: float,
) -> dict[str, Any]:
    if device.type == "cuda":
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats(device)
    model = _build_model(config, card_table, seed=seed, device=device)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=learning_rate, weight_decay=weight_decay, fused=device.type == "cuda"
    )
    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda=lambda _step: 1.0)
    sampler = _start_gpu_sampler() if device.type == "cuda" else None
    try:
        training = train_epoch_packed(
            model,
            optimizer,
            scheduler,
            train_groups,
            device=device,
            bf16=bf16,
            maximum_gradient_norm=maximum_gradient_norm,
            epoch=1,
            maximum_groups=None,
        )
        validation = validate_packed(
            model,
            validation_groups,
            device=device,
            bf16=bf16,
            maximum_groups=None,
        )
    finally:
        telemetry = _stop_gpu_sampler(*sampler) if sampler is not None else None
    result = {
        "training": training,
        "validation": validation,
        "gpu_telemetry": telemetry,
        "peak_allocated_bytes": int(torch.cuda.max_memory_allocated(device)) if device.type == "cuda" else 0,
    }
    del scheduler, optimizer, model
    gc.collect()
    if device.type == "cuda":
        torch.cuda.empty_cache()
    return result


def _lr_smoke(
    *,
    config: PolicyConfigV1,
    card_table: Any,
    train_groups: Sequence[PackedRecurrentGroup],
    validation_groups: Sequence[PackedRecurrentGroup],
    learning_rate: float,
    epochs: int,
    seed: int,
    device: torch.device,
    bf16: bool,
    maximum_gradient_norm: float,
    weight_decay: float,
) -> dict[str, Any]:
    if device.type == "cuda":
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats(device)
    model = _build_model(config, card_table, seed=seed, device=device)
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=learning_rate, weight_decay=weight_decay, fused=device.type == "cuda"
    )
    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda=lambda _step: 1.0)
    baseline = validate_packed(
        model, validation_groups, device=device, bf16=bf16, maximum_groups=None
    )
    history: list[dict[str, Any]] = []
    for epoch in range(1, epochs + 1):
        training = train_epoch_packed(
            model,
            optimizer,
            scheduler,
            train_groups,
            device=device,
            bf16=bf16,
            maximum_gradient_norm=maximum_gradient_norm,
            epoch=epoch,
            maximum_groups=None,
        )
        validation = validate_packed(
            model, validation_groups, device=device, bf16=bf16, maximum_groups=None
        )
        history.append({"epoch": epoch, "training": training, "validation": validation})
    best = min(history, key=lambda row: float(row["validation"]["mean_nll"]))
    result = {
        "learning_rate": learning_rate,
        "baseline_validation_mean_nll": baseline["mean_nll"],
        "best_validation_mean_nll": best["validation"]["mean_nll"],
        "best_epoch": best["epoch"],
        "history": history,
        "peak_allocated_bytes": int(torch.cuda.max_memory_allocated(device)) if device.type == "cuda" else 0,
    }
    del scheduler, optimizer, model
    gc.collect()
    if device.type == "cuda":
        torch.cuda.empty_cache()
    return result


def _train_stage(
    *,
    model: PTCGPolicyV1,
    model_label: str,
    model_config: PolicyConfigV1,
    stage_name: str,
    materialized_manifest_sha256: str,
    train_groups: Sequence[PackedRecurrentGroup],
    validation_groups: Sequence[PackedRecurrentGroup],
    output_dir: Path,
    learning_rate: float,
    epochs: int,
    minimum_teacher_score: float | None,
    device: torch.device,
    bf16: bool,
    maximum_gradient_norm: float,
    weight_decay: float,
    early_stopping_patience: int | None = None,
    early_stopping_min_delta: float = 0.0,
) -> dict[str, Any]:
    optimizer = torch.optim.AdamW(
        model.parameters(), lr=learning_rate, weight_decay=weight_decay, fused=device.type == "cuda"
    )
    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda=lambda _step: 1.0)
    baseline = validate_packed(
        model, validation_groups, device=device, bf16=bf16, maximum_groups=None
    )
    history: list[dict[str, Any]] = []
    checkpoint_path = output_dir / f"{stage_name}-best.pt"
    best_epoch = 0
    stopped_early = False
    epochs_without_improvement = 0
    if early_stopping_patience is None:
        best_validation = float("inf")
        best_receipt: dict[str, Any] | None = None
    else:
        best_validation = float(baseline["mean_nll"])
        best_receipt = save_training_checkpoint(
            checkpoint_path,
            model=model,
            optimizer=optimizer,
            scheduler=scheduler,
            scaler=None,
            counters={"stage_epoch": 0},
            league={
                "kind": "dragapult-bc-capacity-sweep-v1",
                "model_label": model_label,
                "model_config": asdict(model_config),
                "stage": stage_name,
                "materialized_manifest_sha256": materialized_manifest_sha256,
                "minimum_teacher_score": minimum_teacher_score,
                "early_stopping_patience": early_stopping_patience,
                "early_stopping_min_delta": early_stopping_min_delta,
            },
            rollout_boundary={"completed_stage": stage_name, "completed_epoch": 0},
            include_cuda_rng=device.type == "cuda",
        )
    sampler = _start_gpu_sampler() if device.type == "cuda" else None
    try:
        for epoch in range(1, epochs + 1):
            training = train_epoch_packed(
                model,
                optimizer,
                scheduler,
                train_groups,
                device=device,
                bf16=bf16,
                maximum_gradient_norm=maximum_gradient_norm,
                epoch=epoch,
                maximum_groups=None,
            )
            validation = validate_packed(
                model, validation_groups, device=device, bf16=bf16, maximum_groups=None
            )
            history.append({"epoch": epoch, "training": training, "validation": validation})
            validation_nll = float(validation["mean_nll"])
            improved = validation_nll < best_validation - early_stopping_min_delta
            if improved:
                best_validation = validation_nll
                best_epoch = epoch
                epochs_without_improvement = 0
                best_receipt = save_training_checkpoint(
                    checkpoint_path,
                    model=model,
                    optimizer=optimizer,
                    scheduler=scheduler,
                    scaler=None,
                    counters={"stage_epoch": epoch},
                    league={
                        "kind": "dragapult-bc-capacity-sweep-v1",
                        "model_label": model_label,
                        "model_config": asdict(model_config),
                        "stage": stage_name,
                        "materialized_manifest_sha256": materialized_manifest_sha256,
                        "minimum_teacher_score": minimum_teacher_score,
                        "early_stopping_patience": early_stopping_patience,
                        "early_stopping_min_delta": early_stopping_min_delta,
                    },
                    rollout_boundary={"completed_stage": stage_name, "completed_epoch": epoch},
                    include_cuda_rng=device.type == "cuda",
                )
            elif early_stopping_patience is not None:
                epochs_without_improvement += 1
            print(
                json.dumps(
                    {
                        "event": "capacity_stage_epoch",
                        "model": model_label,
                        "stage": stage_name,
                        "epoch": epoch,
                        "training_nll": training["mean_nll"],
                        "validation_nll": validation_nll,
                        "best_validation_nll": best_validation,
                        "meaningful_improvement": improved,
                        "epochs_without_improvement": epochs_without_improvement,
                        "targets_per_second": training["policy_targets_per_second"],
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            if (
                early_stopping_patience is not None
                and epochs_without_improvement >= early_stopping_patience
            ):
                stopped_early = True
                print(
                    json.dumps(
                        {
                            "event": "capacity_stage_early_stop",
                            "model": model_label,
                            "stage": stage_name,
                            "epoch": epoch,
                            "best_epoch": best_epoch,
                            "best_validation_nll": best_validation,
                            "patience": early_stopping_patience,
                            "minimum_delta": early_stopping_min_delta,
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
                break
    finally:
        telemetry = _stop_gpu_sampler(*sampler) if sampler is not None else None
    if best_receipt is None:
        raise CapacitySweepError(f"stage {stage_name} produced no best checkpoint")
    load_training_checkpoint_model_state(
        checkpoint_path,
        model=model,
        expected_sha256=str(best_receipt["payload_sha256"]),
    )
    return {
        "stage": stage_name,
        "learning_rate": learning_rate,
        "epochs": epochs,
        "epochs_ran": len(history),
        "stopped_early": stopped_early,
        "early_stopping_patience": early_stopping_patience,
        "early_stopping_min_delta": early_stopping_min_delta,
        "minimum_teacher_score": minimum_teacher_score,
        "baseline_validation_mean_nll": baseline["mean_nll"],
        "best_validation_mean_nll": best_validation,
        "best_epoch": best_epoch,
        "checkpoint_path": str(checkpoint_path),
        "checkpoint_sha256": best_receipt["payload_sha256"],
        "checkpoint_bytes": best_receipt["payload_bytes"],
        "history": history,
        "gpu_telemetry": telemetry,
    }


def _expanded_batch_candidates(values: Sequence[int]) -> tuple[int, ...]:
    """Expand requested batch sizes through their halving fallbacks, largest first."""
    candidates: set[int] = set()
    for requested in values:
        value = int(requested)
        if value <= 0:
            raise CapacitySweepError("batch-size candidates must be positive")
        while value >= 1:
            candidates.add(value)
            if value == 1:
                break
            value = max(1, value // 2)
    return tuple(sorted(candidates, reverse=True))


def _estimated_optimizer_update_density(
    episodes: Sequence[MaterializedEpisodeV1],
    *,
    batch_size: int,
    sequence_length: int,
    seed: int,
) -> tuple[int, int, float]:
    """Compute exact packed update density without collating tensors or touching the GPU."""
    if batch_size <= 0 or sequence_length <= 0 or not episodes:
        raise CapacitySweepError("update-density estimate requires positive sizes and episodes")
    ordered = deterministic_order(episodes, seed, 0)
    groups = batch_groups(ordered, min(batch_size, len(ordered)))
    policy_targets = 0
    optimizer_steps = 0
    for group in groups:
        maximum_length = max(len(episode.decisions) for episode in group)
        for start in range(0, maximum_length, sequence_length):
            stop = start + sequence_length
            chunk_targets = sum(
                not decision.request.has_only_one_outcome
                for episode in group
                for decision in episode.decisions[start:stop]
            )
            policy_targets += int(chunk_targets)
            optimizer_steps += int(chunk_targets > 0)
    if policy_targets <= 0 or optimizer_steps <= 0:
        raise CapacitySweepError("estimated training groups contain no optimizer updates")
    return policy_targets, optimizer_steps, policy_targets / optimizer_steps


def _optimizer_update_density(
    groups: Sequence[PackedRecurrentGroup],
) -> tuple[int, int, float]:
    policy_targets = sum(int(group.policy_targets) for group in groups)
    optimizer_steps = sum(
        int(chunk.policy_targets > 0)
        for group in groups
        for chunk in group.chunks
    )
    if policy_targets <= 0 or optimizer_steps <= 0:
        raise CapacitySweepError("packed training groups contain no optimizer updates")
    return policy_targets, optimizer_steps, policy_targets / optimizer_steps


def _pack_with_fallback(
    episodes: Sequence[MaterializedEpisodeV1],
    *,
    preferred_batch_size: int,
    sequence_length: int,
    seed: int,
    device: torch.device,
    maximum_targets_per_optimizer_step: float | None = None,
) -> tuple[tuple[PackedRecurrentGroup, ...], int]:
    if preferred_batch_size <= 0:
        raise CapacitySweepError("preferred batch size must be positive")
    if (
        maximum_targets_per_optimizer_step is not None
        and maximum_targets_per_optimizer_step <= 0
    ):
        raise CapacitySweepError("maximum targets per optimizer step must be positive")

    candidates: list[int] = []
    value = min(preferred_batch_size, len(episodes))
    while value >= 1:
        if value not in candidates:
            candidates.append(value)
        if value == 1:
            break
        value = max(1, value // 2)

    last_error: Exception | None = None
    for batch_size in candidates:
        try:
            groups = _pack(
                episodes,
                batch_size=batch_size,
                sequence_length=sequence_length,
                seed=seed,
                device=device,
            )
            if maximum_targets_per_optimizer_step is None:
                return groups, batch_size
            _, _, targets_per_step = _optimizer_update_density(groups)
            if targets_per_step <= maximum_targets_per_optimizer_step or batch_size == 1:
                return groups, batch_size
            del groups
            gc.collect()
            if device.type == "cuda":
                torch.cuda.empty_cache()
        except torch.cuda.OutOfMemoryError as error:
            last_error = error
            gc.collect()
            if device.type == "cuda":
                torch.cuda.empty_cache()
    raise CapacitySweepError("all batch-size fallbacks OOM while packing a training stage") from last_error


def main() -> int:
    parser = argparse.ArgumentParser(description="Sequential 970k-to-5M Dragapult BC capacity sweep")
    parser.add_argument("--archetype-materialized-dir", type=Path, required=True)
    parser.add_argument("--exact-materialized-dir", type=Path, required=True)
    parser.add_argument("--card-table", type=Path, required=True)
    parser.add_argument("--archetype-object-cache", type=Path)
    parser.add_argument("--exact-object-cache", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--model-labels", default="970k,1.4m,1.8m,2.9m,3.7m,5.0m")
    parser.add_argument("--resume-model-label")
    parser.add_argument("--resume-checkpoint", type=Path)
    parser.add_argument("--resume-after-stage")
    parser.add_argument("--resume-batch-size", type=int)
    parser.add_argument("--resume-learning-rate", type=float)
    parser.add_argument("--batch-size-candidates", default="256,512,1024")
    parser.add_argument("--learning-rate-candidates", default="0.000025,0.00005,0.000075")
    parser.add_argument("--sequence-length", type=int, default=32)
    parser.add_argument("--speed-train-limit", type=int, default=1024)
    parser.add_argument("--speed-validation-limit", type=int, default=64)
    parser.add_argument("--lr-train-limit", type=int, default=256)
    parser.add_argument("--lr-validation-limit", type=int, default=64)
    parser.add_argument("--lr-smoke-epochs", type=int, default=2)
    parser.add_argument("--stage-a-epochs", type=int, default=4)
    parser.add_argument("--stage-b-epochs", type=int, default=2)
    parser.add_argument("--stage-c-epochs", type=int, default=3)
    parser.add_argument("--stage-d-epochs", type=int, default=2)
    parser.add_argument("--stage-d-early-stopping-patience", type=int)
    parser.add_argument("--stage-d-early-stopping-min-delta", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=20260815)
    parser.add_argument("--loader-workers", type=int, default=16)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--maximum-gradient-norm", type=float, default=1.0)
    parser.add_argument("--maximum-targets-per-optimizer-step", type=float, default=512.0)
    parser.add_argument("--bf16", action="store_true")
    parser.add_argument("--speed-only", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    args = parser.parse_args()

    configs = model_configs()
    labels = tuple(item.strip() for item in args.model_labels.split(",") if item.strip())
    if not labels or any(label not in configs for label in labels):
        raise CapacitySweepError("model labels contain an unsupported variant")
    resume_values = (
        args.resume_model_label,
        args.resume_checkpoint,
        args.resume_after_stage,
        args.resume_batch_size,
        args.resume_learning_rate,
    )
    resume_enabled = any(value is not None for value in resume_values)
    if args.speed_only and resume_enabled:
        raise CapacitySweepError("speed-only mode cannot be combined with resume arguments")
    if args.speed_only and len(labels) != 1:
        raise CapacitySweepError("speed-only mode requires exactly one model label")
    if resume_enabled and not all(value is not None for value in resume_values):
        raise CapacitySweepError("resume arguments must be supplied together")
    stage_names = (
        "stage-a-archetype-all",
        "stage-b-archetype-1175",
        "stage-c-exact-all",
        "stage-d-exact-1150",
    )
    if resume_enabled:
        if args.resume_model_label not in labels or labels[0] != args.resume_model_label:
            raise CapacitySweepError("resume model must be the first requested model label")
        if args.resume_after_stage not in stage_names[:-1]:
            raise CapacitySweepError("resume-after stage is unsupported")
        if args.resume_batch_size is None or args.resume_batch_size <= 0:
            raise CapacitySweepError("resume batch size must be positive")
        if args.resume_learning_rate is None or args.resume_learning_rate <= 0:
            raise CapacitySweepError("resume learning rate must be positive")
        assert args.resume_checkpoint is not None
        if not args.resume_checkpoint.is_file():
            raise CapacitySweepError("resume checkpoint is missing")
    batch_candidates = _expanded_batch_candidates(
        _parse_csv_ints(args.batch_size_candidates, "batch-size candidates")
    )
    lr_candidates = _parse_csv_floats(args.learning_rate_candidates, "learning-rate candidates")
    for value, label in (
        (args.sequence_length, "sequence length"),
        (args.speed_train_limit, "speed train limit"),
        (args.speed_validation_limit, "speed validation limit"),
        (args.lr_train_limit, "LR train limit"),
        (args.lr_validation_limit, "LR validation limit"),
        (args.lr_smoke_epochs, "LR smoke epochs"),
        (args.stage_a_epochs, "stage A epochs"),
        (args.stage_b_epochs, "stage B epochs"),
        (args.stage_c_epochs, "stage C epochs"),
        (args.stage_d_epochs, "stage D epochs"),
        (args.loader_workers, "loader workers"),
    ):
        if value <= 0:
            raise CapacitySweepError(f"{label} must be positive")

    if args.stage_d_early_stopping_patience is not None and args.stage_d_early_stopping_patience <= 0:
        raise CapacitySweepError("stage D early-stopping patience must be positive")
    if args.maximum_targets_per_optimizer_step <= 0:
        raise CapacitySweepError("maximum targets per optimizer step must be positive")
    if args.stage_d_early_stopping_min_delta < 0:
        raise CapacitySweepError("stage D early-stopping minimum delta must be nonnegative")

    device = torch.device(args.device)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise CapacitySweepError("CUDA requested but unavailable")
    if args.bf16 and (device.type != "cuda" or not torch.cuda.is_bf16_supported()):
        raise CapacitySweepError("BF16 requested but unsupported")
    torch.set_float32_matmul_precision("high")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    archetype_manifest, archetype_records = load_materialized_manifest(args.archetype_materialized_dir)
    exact_manifest, exact_records = load_materialized_manifest(args.exact_materialized_dir)
    archetype_train_records = _records_for_split(archetype_records, "train")
    archetype_validation_records = _records_for_split(archetype_records, "validation")
    exact_train_records = _records_for_split(exact_records, "train")
    exact_validation_records = _records_for_split(exact_records, "validation")

    print(
        json.dumps(
            {"event": "capacity_corpus_load_start", "corpus": "archetype-v3"},
            sort_keys=True,
        ),
        flush=True,
    )
    load_started = time.perf_counter()
    archetype_episodes, archetype_load_source = _load_or_build_object_cache(
        root=args.archetype_materialized_dir,
        records=[*archetype_train_records, *archetype_validation_records],
        workers=args.loader_workers,
        manifest_sha256=str(archetype_manifest["manifest_sha256"]),
        cache_path=args.archetype_object_cache,
        corpus_label="archetype-v3",
    )
    archetype_load_seconds = time.perf_counter() - load_started
    archetype_train = [episode for episode in archetype_episodes if episode.split == "train"]
    archetype_validation = [episode for episode in archetype_episodes if episode.split == "validation"]
    print(
        json.dumps(
            {
                "event": "capacity_corpus_load_complete",
                "corpus": "archetype-v3",
                "episodes": len(archetype_episodes),
                "elapsed_seconds": archetype_load_seconds,
                "source": archetype_load_source,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    print(
        json.dumps(
            {"event": "capacity_corpus_load_start", "corpus": "exact-v2"},
            sort_keys=True,
        ),
        flush=True,
    )
    exact_started = time.perf_counter()
    exact_episodes, exact_load_source = _load_or_build_object_cache(
        root=args.exact_materialized_dir,
        records=[*exact_train_records, *exact_validation_records],
        workers=args.loader_workers,
        manifest_sha256=str(exact_manifest["manifest_sha256"]),
        cache_path=args.exact_object_cache,
        corpus_label="exact-v2",
    )
    exact_load_seconds = time.perf_counter() - exact_started
    exact_train = [episode for episode in exact_episodes if episode.split == "train"]
    exact_validation = [episode for episode in exact_episodes if episode.split == "validation"]
    print(
        json.dumps(
            {
                "event": "capacity_corpus_load_complete",
                "corpus": "exact-v2",
                "episodes": len(exact_episodes),
                "elapsed_seconds": exact_load_seconds,
                "source": exact_load_source,
            },
            sort_keys=True,
        ),
        flush=True,
    )

    archetype_1175_train_ids = {
        int(record["episode_id"])
        for record in _records_for_split(archetype_records, "train", minimum_teacher_score=1175.0)
    }
    archetype_1175_validation_ids = {
        int(record["episode_id"])
        for record in _records_for_split(archetype_records, "validation", minimum_teacher_score=1175.0)
    }
    exact_1150_train_ids = {
        int(record["episode_id"])
        for record in _records_for_split(exact_records, "train", minimum_teacher_score=1150.0)
    }
    exact_1150_validation_ids = {
        int(record["episode_id"])
        for record in _records_for_split(exact_records, "validation", minimum_teacher_score=1150.0)
    }
    archetype_1175_train = _episode_subset(archetype_train, archetype_1175_train_ids)
    archetype_1175_validation = _episode_subset(archetype_validation, archetype_1175_validation_ids)
    exact_1150_train = _episode_subset(exact_train, exact_1150_train_ids)
    exact_1150_validation = _episode_subset(exact_validation, exact_1150_validation_ids)

    card_table = load_card_table(args.card_table)
    for manifest in (archetype_manifest, exact_manifest):
        if manifest.get("card_data_sha256") != card_table.card_data_sha256:
            raise CapacitySweepError("materialized card-data hash differs from trainer card table")

    if args.cache_only:
        print(
            json.dumps(
                {
                    "event": "capacity_cache_only_complete",
                    "archetype_episodes": len(archetype_episodes),
                    "exact_episodes": len(exact_episodes),
                    "archetype_cache": str(args.archetype_object_cache) if args.archetype_object_cache else None,
                    "exact_cache": str(args.exact_object_cache) if args.exact_object_cache else None,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        return 0

    # Verify the frozen scale ladder exactly before spending GPU time.
    parameter_counts: dict[str, int] = {}
    for label in labels:
        probe = PTCGPolicyV1(card_table, configs[label])
        parameter_counts[label] = probe.trainable_parameter_count
        expected = EXPECTED_PARAMETER_COUNTS[label]
        if probe.trainable_parameter_count != expected:
            raise CapacitySweepError(
                f"{label} parameter count differs: expected {expected}, observed {probe.trainable_parameter_count}"
            )
        del probe

    sweep_started = time.perf_counter()
    model_reports: list[dict[str, Any]] = []
    for model_index, label in enumerate(labels):
        config = configs[label]
        model_seed = args.seed
        print(
            json.dumps(
                {
                    "event": "capacity_model_start",
                    "model": label,
                    "parameters": parameter_counts[label],
                    "ordinal": model_index + 1,
                    "total_models": len(labels),
                },
                sort_keys=True,
            ),
            flush=True,
        )

        is_resume_model = resume_enabled and label == args.resume_model_label
        speed_rows: list[dict[str, Any]] = []
        lr_rows: list[dict[str, Any]] = []
        if is_resume_model:
            assert args.resume_batch_size is not None
            assert args.resume_learning_rate is not None
            chosen_batch_size = args.resume_batch_size
            chosen_lr = args.resume_learning_rate
            print(
                json.dumps(
                    {
                        "event": "capacity_resume_hyperparameters",
                        "model": label,
                        "batch_size": chosen_batch_size,
                        "learning_rate": chosen_lr,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
        else:
            speed_train = archetype_train[: min(args.speed_train_limit, len(archetype_train))]
            speed_validation = archetype_validation[: min(args.speed_validation_limit, len(archetype_validation))]
            for batch_size in batch_candidates:
                effective_batch_size = min(batch_size, len(speed_train))
                _, estimated_optimizer_steps, estimated_targets_per_step = (
                    _estimated_optimizer_update_density(
                        speed_train,
                        batch_size=effective_batch_size,
                        sequence_length=args.sequence_length,
                        seed=args.seed,
                    )
                )
                if estimated_targets_per_step > args.maximum_targets_per_optimizer_step:
                    row = {
                        "batch_size": effective_batch_size,
                        "sequence_length": args.sequence_length,
                        "status": "SKIP_UPDATE_DENSITY",
                        "optimizer_steps": estimated_optimizer_steps,
                        "targets_per_optimizer_step": estimated_targets_per_step,
                    }
                    speed_rows.append(row)
                    print(
                        json.dumps(
                            {"event": "capacity_speed_smoke", "model": label, **row},
                            sort_keys=True,
                        ),
                        flush=True,
                    )
                    continue
                train_groups: tuple[PackedRecurrentGroup, ...] | None = None
                validation_groups: tuple[PackedRecurrentGroup, ...] | None = None
                try:
                    train_groups = _pack(
                        speed_train,
                        batch_size=min(batch_size, len(speed_train)),
                        sequence_length=args.sequence_length,
                        seed=args.seed,
                        device=device,
                    )
                    validation_groups = _pack(
                        speed_validation,
                        batch_size=min(batch_size, len(speed_validation)),
                        sequence_length=args.sequence_length,
                        seed=args.seed + 1,
                        device=device,
                    )
                    smoke = _one_epoch_smoke(
                        config=config,
                        card_table=card_table,
                        train_groups=train_groups,
                        validation_groups=validation_groups,
                        learning_rate=5e-5,
                        seed=model_seed,
                        device=device,
                        bf16=args.bf16,
                        maximum_gradient_norm=args.maximum_gradient_norm,
                        weight_decay=args.weight_decay,
                    )
                    row = {
                        "batch_size": min(batch_size, len(speed_train)),
                        "sequence_length": args.sequence_length,
                        "status": "PASS",
                        "targets_per_second": smoke["training"]["policy_targets_per_second"],
                        "optimizer_steps": smoke["training"]["optimizer_steps"],
                        "targets_per_optimizer_step": (
                            smoke["training"]["policy_targets"]
                            / smoke["training"]["optimizer_steps"]
                        ),
                        "training_mean_nll": smoke["training"]["mean_nll"],
                        "validation_mean_nll": smoke["validation"]["mean_nll"],
                        "gradient_norm_max_pre_clip": smoke["training"]["gradient_norm_max_pre_clip"],
                        "peak_allocated_bytes": smoke["peak_allocated_bytes"],
                        "gpu_telemetry": smoke["gpu_telemetry"],
                    }
                except torch.cuda.OutOfMemoryError:
                    row = {
                        "batch_size": min(batch_size, len(speed_train)),
                        "sequence_length": args.sequence_length,
                        "status": "OOM",
                    }
                    gc.collect()
                    if device.type == "cuda":
                        torch.cuda.empty_cache()
                finally:
                    del train_groups, validation_groups
                    gc.collect()
                    if device.type == "cuda":
                        torch.cuda.empty_cache()
                speed_rows.append(row)
                print(
                    json.dumps({"event": "capacity_speed_smoke", "model": label, **row}, sort_keys=True),
                    flush=True,
                )
            passing_speed = [row for row in speed_rows if row["status"] == "PASS"]
            if not passing_speed:
                raise CapacitySweepError(f"{label} has no viable batch-size smoke")
            learning_viable_speed = [
                row
                for row in passing_speed
                if float(row["targets_per_optimizer_step"])
                <= args.maximum_targets_per_optimizer_step
            ]
            if learning_viable_speed:
                chosen_speed = max(
                    learning_viable_speed,
                    key=lambda row: float(row["targets_per_second"]),
                )
            else:
                chosen_speed = min(
                    passing_speed,
                    key=lambda row: float(row["targets_per_optimizer_step"]),
                )
            chosen_batch_size = int(chosen_speed["batch_size"])
            if args.speed_only:
                print(
                    json.dumps(
                        {
                            "event": "capacity_speed_only_complete",
                            "model": label,
                            "chosen_batch_size": chosen_batch_size,
                            "maximum_targets_per_optimizer_step": args.maximum_targets_per_optimizer_step,
                            "speed_rows": speed_rows,
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
                return 0

            lr_train = archetype_train[: min(args.lr_train_limit, len(archetype_train))]
            lr_validation = archetype_validation[: min(args.lr_validation_limit, len(archetype_validation))]
            lr_train_groups, lr_batch = _pack_with_fallback(
                lr_train,
                preferred_batch_size=chosen_batch_size,
                sequence_length=args.sequence_length,
                seed=args.seed,
                device=device,
                maximum_targets_per_optimizer_step=args.maximum_targets_per_optimizer_step,
            )
            lr_validation_groups, _ = _pack_with_fallback(
                lr_validation,
                preferred_batch_size=lr_batch,
                sequence_length=args.sequence_length,
                seed=args.seed + 1,
                device=device,
            )
            for learning_rate in lr_candidates:
                row = _lr_smoke(
                    config=config,
                    card_table=card_table,
                    train_groups=lr_train_groups,
                    validation_groups=lr_validation_groups,
                    learning_rate=learning_rate,
                    epochs=args.lr_smoke_epochs,
                    seed=model_seed,
                    device=device,
                    bf16=args.bf16,
                    maximum_gradient_norm=args.maximum_gradient_norm,
                    weight_decay=args.weight_decay,
                )
                lr_rows.append(row)
                print(
                    json.dumps(
                        {
                            "event": "capacity_lr_smoke",
                            "model": label,
                            "learning_rate": learning_rate,
                            "best_validation_nll": row["best_validation_mean_nll"],
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
            del lr_train_groups, lr_validation_groups
            gc.collect()
            if device.type == "cuda":
                torch.cuda.empty_cache()
            chosen_lr_row = min(lr_rows, key=lambda row: float(row["best_validation_mean_nll"]))
            chosen_lr = float(chosen_lr_row["learning_rate"])

        model_output = args.output_dir / label
        model_output.mkdir(parents=True, exist_ok=True)
        model = _build_model(config, card_table, seed=model_seed, device=device)
        resumed_checkpoint: dict[str, Any] | None = None
        resume_after_index = -1
        if is_resume_model:
            assert args.resume_checkpoint is not None
            assert args.resume_after_stage is not None
            loaded = load_training_checkpoint_model_state(args.resume_checkpoint, model=model)
            resume_after_index = stage_names.index(args.resume_after_stage)
            resumed_checkpoint = {
                "path": str(args.resume_checkpoint),
                "payload_sha256": loaded.payload_sha256,
                "payload_bytes": loaded.payload_bytes,
                "after_stage": args.resume_after_stage,
            }
            print(
                json.dumps(
                    {
                        "event": "capacity_model_resumed",
                        "model": label,
                        **resumed_checkpoint,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
        stage_specs: list[tuple[str, list[MaterializedEpisodeV1], list[MaterializedEpisodeV1], str, float | None, int, float]] = [
            (
                "stage-a-archetype-all",
                archetype_train,
                archetype_validation,
                str(archetype_manifest["manifest_sha256"]),
                None,
                args.stage_a_epochs,
                chosen_lr,
            ),
            (
                "stage-b-archetype-1175",
                archetype_1175_train,
                archetype_1175_validation,
                str(archetype_manifest["manifest_sha256"]),
                1175.0,
                args.stage_b_epochs,
                chosen_lr * 0.5,
            ),
            (
                "stage-c-exact-all",
                exact_train,
                exact_validation,
                str(exact_manifest["manifest_sha256"]),
                None,
                args.stage_c_epochs,
                chosen_lr * 0.5,
            ),
            (
                "stage-d-exact-1150",
                exact_1150_train,
                exact_1150_validation,
                str(exact_manifest["manifest_sha256"]),
                1150.0,
                args.stage_d_epochs,
                chosen_lr * 0.25,
            ),
        ]
        stage_reports: list[dict[str, Any]] = []
        effective_batch_sizes: dict[str, int] = {}
        effective_stage_update_density: dict[str, dict[str, float | int]] = {}
        for stage_index, (
            stage_name,
            stage_train,
            stage_validation,
            manifest_sha,
            minimum_teacher_score,
            epochs,
            stage_lr,
        ) in enumerate(stage_specs):
            if is_resume_model and stage_index <= resume_after_index:
                continue
            train_groups, effective_batch = _pack_with_fallback(
                stage_train,
                preferred_batch_size=chosen_batch_size,
                sequence_length=args.sequence_length,
                seed=args.seed + stage_index * 10,
                device=device,
                maximum_targets_per_optimizer_step=args.maximum_targets_per_optimizer_step,
            )
            validation_groups, _ = _pack_with_fallback(
                stage_validation,
                preferred_batch_size=effective_batch,
                sequence_length=args.sequence_length,
                seed=args.seed + stage_index * 10 + 1,
                device=device,
            )
            effective_batch_sizes[stage_name] = effective_batch
            stage_targets, stage_optimizer_steps, stage_targets_per_step = _optimizer_update_density(
                train_groups
            )
            effective_stage_update_density[stage_name] = {
                "policy_targets": stage_targets,
                "optimizer_steps_per_epoch": stage_optimizer_steps,
                "targets_per_optimizer_step": stage_targets_per_step,
            }
            print(
                json.dumps(
                    {
                        "event": "capacity_stage_update_density",
                        "model": label,
                        "stage": stage_name,
                        "effective_batch_size": effective_batch,
                        **effective_stage_update_density[stage_name],
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            stage_report = _train_stage(
                model=model,
                model_label=label,
                model_config=config,
                stage_name=stage_name,
                materialized_manifest_sha256=str(manifest_sha),
                train_groups=train_groups,
                validation_groups=validation_groups,
                output_dir=model_output,
                learning_rate=stage_lr,
                epochs=epochs,
                minimum_teacher_score=minimum_teacher_score,
                device=device,
                bf16=args.bf16,
                maximum_gradient_norm=args.maximum_gradient_norm,
                weight_decay=args.weight_decay,
                early_stopping_patience=(
                    args.stage_d_early_stopping_patience
                    if stage_name == "stage-d-exact-1150"
                    else None
                ),
                early_stopping_min_delta=(
                    args.stage_d_early_stopping_min_delta
                    if stage_name == "stage-d-exact-1150"
                    else 0.0
                ),
            )
            stage_reports.append(stage_report)
            del train_groups, validation_groups
            gc.collect()
            if device.type == "cuda":
                torch.cuda.empty_cache()

        final_stage = stage_reports[-1]
        model_report = {
            "model_label": label,
            "trainable_parameters": parameter_counts[label],
            "config": asdict(config),
            "architecture_sha256": model.architecture_sha256,
            "speed_smoke": speed_rows,
            "chosen_batch_size": chosen_batch_size,
            "chosen_learning_rate": chosen_lr,
            "learning_rate_smoke": lr_rows,
            "resumed_checkpoint": resumed_checkpoint,
            "effective_stage_batch_sizes": effective_batch_sizes,
            "effective_stage_update_density": effective_stage_update_density,
            "maximum_targets_per_optimizer_step": args.maximum_targets_per_optimizer_step,
            "stages": stage_reports,
            "final_checkpoint_path": final_stage["checkpoint_path"],
            "final_checkpoint_sha256": final_stage["checkpoint_sha256"],
            "final_validation_mean_nll": final_stage["best_validation_mean_nll"],
            "peak_allocated_bytes": int(torch.cuda.max_memory_allocated(device)) if device.type == "cuda" else 0,
        }
        (model_output / "model-report.json").write_text(
            json.dumps(model_report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        model_reports.append(model_report)
        print(
            json.dumps(
                {
                    "event": "capacity_model_complete",
                    "model": label,
                    "parameters": parameter_counts[label],
                    "final_validation_nll": model_report["final_validation_mean_nll"],
                    "final_checkpoint_sha256": model_report["final_checkpoint_sha256"],
                },
                sort_keys=True,
            ),
            flush=True,
        )
        del model
        gc.collect()
        if device.type == "cuda":
            torch.cuda.empty_cache()

    ranked = sorted(model_reports, key=lambda row: float(row["final_validation_mean_nll"]))
    report = {
        "schema_version": 1,
        "record_id": "bc-dragapult-capacity-sweep-v1",
        "status": "PASS_BC_CAPACITY_SWEEP_COMPLETED",
        "archetype_manifest_sha256": archetype_manifest["manifest_sha256"],
        "exact_manifest_sha256": exact_manifest["manifest_sha256"],
        "load_seconds": archetype_load_seconds + exact_load_seconds,
        "parameter_counts": parameter_counts,
        "configuration": {
            "model_labels": labels,
            "batch_size_candidates": batch_candidates,
            "learning_rate_candidates": lr_candidates,
            "sequence_length": args.sequence_length,
            "seed": args.seed,
            "bf16": args.bf16,
            "weight_decay": args.weight_decay,
            "maximum_gradient_norm": args.maximum_gradient_norm,
        },
        "corpus": {
            "archetype_train": len(archetype_train),
            "archetype_validation": len(archetype_validation),
            "archetype_1175_train": len(archetype_1175_train),
            "archetype_1175_validation": len(archetype_1175_validation),
            "exact_train": 0 if exact_train is None else len(exact_train),
            "exact_validation": 0 if exact_validation is None else len(exact_validation),
            "exact_1150_train": 0 if exact_1150_train is None else len(exact_1150_train),
            "exact_1150_validation": 0 if exact_1150_validation is None else len(exact_1150_validation),
        },
        "models": model_reports,
        "validation_ranking": [
            {
                "rank": index + 1,
                "model_label": row["model_label"],
                "trainable_parameters": row["trainable_parameters"],
                "final_validation_mean_nll": row["final_validation_mean_nll"],
                "final_checkpoint_path": row["final_checkpoint_path"],
                "final_checkpoint_sha256": row["final_checkpoint_sha256"],
            }
            for index, row in enumerate(ranked)
        ],
        "elapsed_seconds": time.perf_counter() - sweep_started,
        "host_peak_rss_kib": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        "native_gameplay_comparison_required": True,
    }
    report_path = args.output_dir / "capacity-sweep-report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "event": "capacity_sweep_complete",
                "validation_winner": ranked[0]["model_label"],
                "validation_winner_nll": ranked[0]["final_validation_mean_nll"],
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
