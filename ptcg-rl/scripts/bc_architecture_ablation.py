from __future__ import annotations

import argparse
import gc
import json
import random
import resource
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from bc_train_materialized import (  # noqa: E402
    load_all_episodes,
    load_materialized_manifest,
    prepack_groups,
    train_epoch_packed,
    validate_packed,
)
from ptcg_rl.bc.materialized import MaterializedEpisodeV1  # noqa: E402
from ptcg_rl.bc.training import (  # noqa: E402
    PackedRecurrentGroup,
    packed_recurrent_group_to_device,
)
from ptcg_rl.g2.card_table import load_card_table  # noqa: E402
from ptcg_rl.g2.checkpoint import state_dict_sha256  # noqa: E402
from ptcg_rl.g2.experimental_policy import (  # noqa: E402
    OptionEntityCrossAttentionConfigV1,
    PTCGPolicyCrossAttentionV1,
)
from ptcg_rl.g2.network import PTCGPolicyV1  # noqa: E402


class ArchitectureAblationError(ValueError):
    """Raised when the controlled BC architecture ablation violates its contract."""


def _parse_ints(value: str, label: str) -> tuple[int, ...]:
    try:
        parsed = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as error:
        raise ArchitectureAblationError(f"{label} contains a non-integer") from error
    if not parsed or any(item <= 0 for item in parsed):
        raise ArchitectureAblationError(f"{label} must contain positive integers")
    return parsed


def _parse_floats(value: str, label: str) -> tuple[float, ...]:
    try:
        parsed = tuple(float(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as error:
        raise ArchitectureAblationError(f"{label} contains a non-number") from error
    if not parsed or any(item <= 0 for item in parsed):
        raise ArchitectureAblationError(f"{label} must contain positive numbers")
    return parsed


def _seed_everything(seed: int, device: torch.device) -> None:
    random.seed(seed)
    np.random.seed(seed % (2**32))
    torch.manual_seed(seed)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(seed)


def _build_model(name: str, card_table: Any, *, seed: int, device: torch.device) -> Any:
    _seed_everything(seed, device)
    if name == "baseline":
        model = PTCGPolicyV1(card_table)
    elif name == "cross":
        model = PTCGPolicyCrossAttentionV1(card_table)
    elif name == "gated":
        model = PTCGPolicyCrossAttentionV1(
            card_table,
            cross_attention=OptionEntityCrossAttentionConfigV1(gated_residual=True),
        )
    else:
        raise ArchitectureAblationError(f"unsupported architecture variant: {name}")
    return model.to(device)


def _common_initial_state_sha(model: Any, baseline_parameter_names: set[str]) -> str:
    state = {
        name: tensor.detach().cpu()
        for name, tensor in model.state_dict().items()
        if name in baseline_parameter_names
    }
    if set(state) != baseline_parameter_names:
        missing = sorted(baseline_parameter_names - set(state))
        raise ArchitectureAblationError(f"variant does not preserve baseline state keys: {missing[:5]}")
    return state_dict_sha256(state)


def _start_gpu_sampler() -> tuple[subprocess.Popen[str], Path]:
    temporary = tempfile.NamedTemporaryFile(prefix="kptcg-ablation-gpu-", suffix=".csv", delete=False)
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
    process._kptcg_handle = handle  # type: ignore[attr-defined]
    return process, path


def _stop_gpu_sampler(process: subprocess.Popen[str], path: Path) -> dict[str, float]:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    handle = getattr(process, "_kptcg_handle", None)
    if handle is not None:
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


def _pack_to_device(
    episodes: Sequence[MaterializedEpisodeV1],
    *,
    batch_size: int,
    sequence_length: int,
    seed: int,
    device: torch.device,
) -> tuple[PackedRecurrentGroup, ...]:
    groups = prepack_groups(
        episodes,
        batch_size=batch_size,
        sequence_length=sequence_length,
        seed=seed,
        pin_memory=device.type == "cuda",
    )
    if device.type == "cuda":
        groups = tuple(
            packed_recurrent_group_to_device(group, device, non_blocking=True) for group in groups
        )
        torch.cuda.synchronize(device)
    return groups


def _run_training(
    *,
    variant: str,
    card_table: Any,
    baseline_parameter_names: set[str],
    train_groups: Sequence[PackedRecurrentGroup],
    validation_groups: Sequence[PackedRecurrentGroup],
    device: torch.device,
    bf16: bool,
    seed: int,
    learning_rate: float,
    epochs: int,
    weight_decay: float,
    maximum_gradient_norm: float,
    maximum_train_groups: int | None = None,
    maximum_validation_groups: int | None = None,
) -> dict[str, Any]:
    if device.type == "cuda":
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats(device)
    model = _build_model(variant, card_table, seed=seed, device=device)
    common_sha = _common_initial_state_sha(model, baseline_parameter_names)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=learning_rate,
        weight_decay=weight_decay,
        fused=device.type == "cuda",
    )
    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda=lambda _step: 1.0)
    sampler, telemetry_path = _start_gpu_sampler() if device.type == "cuda" else (None, None)
    started = time.perf_counter()
    try:
        baseline = validate_packed(
            model,
            validation_groups,
            device=device,
            bf16=bf16,
            maximum_groups=maximum_validation_groups,
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
                maximum_groups=maximum_train_groups,
            )
            validation = validate_packed(
                model,
                validation_groups,
                device=device,
                bf16=bf16,
                maximum_groups=maximum_validation_groups,
            )
            history.append({"epoch": epoch, "training": training, "validation": validation})
    finally:
        telemetry = (
            _stop_gpu_sampler(sampler, telemetry_path)
            if sampler is not None and telemetry_path is not None
            else None
        )
    elapsed = time.perf_counter() - started
    best = min(history, key=lambda item: float(item["validation"]["mean_nll"]))
    result = {
        "variant": variant,
        "trainable_parameters": int(model.trainable_parameter_count),
        "architecture_sha256": model.architecture_sha256,
        "common_initial_state_sha256": common_sha,
        "learning_rate": learning_rate,
        "epochs": epochs,
        "baseline_validation_mean_nll": baseline["mean_nll"],
        "best_validation_mean_nll": best["validation"]["mean_nll"],
        "best_epoch": best["epoch"],
        "validation_nll_improvement": baseline["mean_nll"] - best["validation"]["mean_nll"],
        "history": history,
        "elapsed_seconds": elapsed,
        "gpu_telemetry": telemetry,
        "peak_allocated_bytes": (
            int(torch.cuda.max_memory_allocated(device)) if device.type == "cuda" else 0
        ),
    }
    del scheduler, optimizer, model
    gc.collect()
    if device.type == "cuda":
        torch.cuda.empty_cache()
    return result


def _select_speed_config(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    stable = [
        row
        for row in rows
        if row["finite"]
        and np.isfinite(float(row["gradient_norm_max_pre_clip"]))
        and float(row["targets_per_second"]) > 0.0
    ]
    if not stable:
        raise ArchitectureAblationError("no stable speed configuration survived")
    return max(stable, key=lambda row: float(row["targets_per_second"]))


def _record_subset(
    records: Sequence[Mapping[str, Any]], split: str, limit: int | None
) -> list[dict[str, Any]]:
    selected = [dict(record) for record in records if str(record["split"]) == split]
    selected.sort(key=lambda record: int(record["episode_id"]))
    return selected if limit is None else selected[:limit]


def main() -> int:
    parser = argparse.ArgumentParser(description="Controlled PTCG BC architecture ablation")
    parser.add_argument("--materialized-dir", type=Path, required=True)
    parser.add_argument("--card-table", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--seed", type=int, default=20260815)
    parser.add_argument("--loader-workers", type=int, default=16)
    parser.add_argument("--speed-batch-sizes", default="256,512,1024")
    parser.add_argument("--speed-sequence-lengths", default="16,32,64")
    parser.add_argument("--learning-rates", default="0.00001,0.000025,0.00005")
    parser.add_argument("--learning-epochs", type=int, default=2)
    parser.add_argument("--learning-train-limit", type=int)
    parser.add_argument("--learning-validation-limit", type=int)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--maximum-gradient-norm", type=float, default=1.0)
    parser.add_argument("--bf16", action="store_true")
    args = parser.parse_args()

    batch_sizes = _parse_ints(args.speed_batch_sizes, "speed batch sizes")
    sequence_lengths = _parse_ints(args.speed_sequence_lengths, "speed sequence lengths")
    learning_rates = _parse_floats(args.learning_rates, "learning rates")
    if args.learning_epochs <= 0 or args.loader_workers <= 0:
        raise ArchitectureAblationError("learning epochs and loader workers must be positive")
    if args.weight_decay < 0 or args.maximum_gradient_norm <= 0:
        raise ArchitectureAblationError("optimizer regularization arguments are invalid")

    device = torch.device(args.device)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise ArchitectureAblationError("CUDA requested but unavailable")
    if args.bf16 and (device.type != "cuda" or not torch.cuda.is_bf16_supported()):
        raise ArchitectureAblationError("BF16 requested but unsupported")
    torch.set_float32_matmul_precision("high")

    manifest, records = load_materialized_manifest(args.materialized_dir)
    train_records = _record_subset(records, "train", args.learning_train_limit)
    validation_records = _record_subset(records, "validation", args.learning_validation_limit)
    if not train_records or not validation_records:
        raise ArchitectureAblationError("ablation requires nonempty train and validation records")
    selected_records = [*train_records, *validation_records]
    load_started = time.perf_counter()
    episodes = load_all_episodes(args.materialized_dir, selected_records, args.loader_workers)
    load_seconds = time.perf_counter() - load_started
    train_episodes = [episode for episode in episodes if episode.split == "train"]
    validation_episodes = [episode for episode in episodes if episode.split == "validation"]

    card_table = load_card_table(args.card_table)
    if manifest.get("card_data_sha256") != card_table.card_data_sha256:
        raise ArchitectureAblationError("materialized card-data hash differs from card table")
    _seed_everything(args.seed, device)
    baseline_probe = PTCGPolicyV1(card_table)
    baseline_parameter_names = set(baseline_probe.state_dict())
    baseline_parameter_count = baseline_probe.trainable_parameter_count
    del baseline_probe

    variants = ("baseline", "cross", "gated")
    parameter_counts: dict[str, int] = {}
    architecture_hashes: dict[str, str] = {}
    common_initial_hashes: dict[str, str] = {}
    for variant in variants:
        probe = _build_model(variant, card_table, seed=args.seed, device=torch.device("cpu"))
        parameter_counts[variant] = int(probe.trainable_parameter_count)
        architecture_hashes[variant] = probe.architecture_sha256
        common_initial_hashes[variant] = _common_initial_state_sha(probe, baseline_parameter_names)
        del probe
    if len(set(common_initial_hashes.values())) != 1:
        raise ArchitectureAblationError(
            "shared baseline parameters did not initialize identically across architecture variants"
        )

    speed_rows: list[dict[str, Any]] = []
    chosen_speed: dict[str, dict[str, Any]] = {}
    for variant in variants:
        variant_rows: list[dict[str, Any]] = []
        for batch_size in batch_sizes:
            speed_train = train_episodes[: min(batch_size, len(train_episodes))]
            speed_validation = validation_episodes[: min(64, len(validation_episodes))]
            for sequence_length in sequence_lengths:
                train_groups = _pack_to_device(
                    speed_train,
                    batch_size=len(speed_train),
                    sequence_length=sequence_length,
                    seed=args.seed,
                    device=device,
                )
                validation_groups = _pack_to_device(
                    speed_validation,
                    batch_size=len(speed_validation),
                    sequence_length=sequence_length,
                    seed=args.seed + 1,
                    device=device,
                )
                run = _run_training(
                    variant=variant,
                    card_table=card_table,
                    baseline_parameter_names=baseline_parameter_names,
                    train_groups=train_groups,
                    validation_groups=validation_groups,
                    device=device,
                    bf16=args.bf16,
                    seed=args.seed,
                    learning_rate=2.5e-5,
                    epochs=1,
                    weight_decay=args.weight_decay,
                    maximum_gradient_norm=args.maximum_gradient_norm,
                    maximum_train_groups=1,
                    maximum_validation_groups=1,
                )
                training = run["history"][0]["training"]
                row = {
                    "variant": variant,
                    "batch_size": len(speed_train),
                    "sequence_length": sequence_length,
                    "targets_per_second": training["policy_targets_per_second"],
                    "training_policy_targets": training["policy_targets"],
                    "training_elapsed_seconds": training["elapsed_seconds"],
                    "training_mean_nll": training["mean_nll"],
                    "validation_mean_nll": run["history"][0]["validation"]["mean_nll"],
                    "gradient_norm_max_pre_clip": training["gradient_norm_max_pre_clip"],
                    "peak_allocated_bytes": run["peak_allocated_bytes"],
                    "gpu_telemetry": run["gpu_telemetry"],
                    "finite": bool(
                        np.isfinite(training["mean_nll"])
                        and np.isfinite(run["history"][0]["validation"]["mean_nll"])
                    ),
                }
                print(json.dumps({"event": "architecture_speed_smoke", **row}, sort_keys=True), flush=True)
                speed_rows.append(row)
                variant_rows.append(row)
                del train_groups, validation_groups
                gc.collect()
                if device.type == "cuda":
                    torch.cuda.empty_cache()
        chosen_speed[variant] = _select_speed_config(variant_rows)

    learning_rows: list[dict[str, Any]] = []
    for variant in variants:
        selected = chosen_speed[variant]
        batch_size = int(selected["batch_size"])
        sequence_length = int(selected["sequence_length"])
        train_groups = _pack_to_device(
            train_episodes,
            batch_size=batch_size,
            sequence_length=sequence_length,
            seed=args.seed,
            device=device,
        )
        validation_groups = _pack_to_device(
            validation_episodes,
            batch_size=min(batch_size, len(validation_episodes)),
            sequence_length=sequence_length,
            seed=args.seed + 1,
            device=device,
        )
        for learning_rate in learning_rates:
            run = _run_training(
                variant=variant,
                card_table=card_table,
                baseline_parameter_names=baseline_parameter_names,
                train_groups=train_groups,
                validation_groups=validation_groups,
                device=device,
                bf16=args.bf16,
                seed=args.seed,
                learning_rate=learning_rate,
                epochs=args.learning_epochs,
                weight_decay=args.weight_decay,
                maximum_gradient_norm=args.maximum_gradient_norm,
            )
            run["batch_size"] = batch_size
            run["sequence_length"] = sequence_length
            print(
                json.dumps(
                    {
                        "event": "architecture_learning_run",
                        "variant": variant,
                        "learning_rate": learning_rate,
                        "best_validation_mean_nll": run["best_validation_mean_nll"],
                        "validation_nll_improvement": run["validation_nll_improvement"],
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            learning_rows.append(run)
        del train_groups, validation_groups
        gc.collect()
        if device.type == "cuda":
            torch.cuda.empty_cache()

    best_by_variant: dict[str, dict[str, Any]] = {}
    for variant in variants:
        candidates = [row for row in learning_rows if row["variant"] == variant]
        best_by_variant[variant] = min(
            candidates, key=lambda row: float(row["best_validation_mean_nll"])
        )
    winner = min(
        variants,
        key=lambda variant: float(best_by_variant[variant]["best_validation_mean_nll"]),
    )

    report = {
        "schema_version": 1,
        "record_id": "bc-dragapult-option-entity-cross-attention-ablation-v1",
        "status": "PASS_ARCHITECTURE_ABLATION_COMPLETED",
        "materialized_manifest_sha256": manifest["manifest_sha256"],
        "materialized_record_id": manifest.get("record_id"),
        "train_episodes": len(train_episodes),
        "validation_episodes": len(validation_episodes),
        "load_seconds": load_seconds,
        "baseline_trainable_parameters": baseline_parameter_count,
        "parameter_counts": parameter_counts,
        "architecture_hashes": architecture_hashes,
        "common_initial_state_sha256": next(iter(common_initial_hashes.values())),
        "shared_initialization_verified": True,
        "configuration": {
            "seed": args.seed,
            "bf16": args.bf16,
            "speed_batch_sizes": batch_sizes,
            "speed_sequence_lengths": sequence_lengths,
            "learning_rates": learning_rates,
            "learning_epochs": args.learning_epochs,
            "weight_decay": args.weight_decay,
            "maximum_gradient_norm": args.maximum_gradient_norm,
        },
        "speed_smoke": speed_rows,
        "chosen_speed_config": chosen_speed,
        "learning_runs": learning_rows,
        "best_by_variant": best_by_variant,
        "provisional_validation_winner": winner,
        "host_peak_rss_kib": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        "production_architecture_promoted": False,
        "native_gameplay_required_before_promotion": True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"event": "architecture_ablation_complete", "winner": winner}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
