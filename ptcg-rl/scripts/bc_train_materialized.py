from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import resource
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ptcg_rl.bc.materialized import (  # noqa: E402
    MaterializedEpisodeV1,
    load_materialized_episode,
)
from ptcg_rl.bc.training import (  # noqa: E402
    PackedRecurrentGroup,
    pack_recurrent_group,
    packed_recurrent_chunk_loss,
    packed_recurrent_group_to_device,
    recurrent_sequence_batch_loss,
)
from ptcg_rl.g2.card_table import load_card_table  # noqa: E402
from ptcg_rl.g2.checkpoint import load_checkpoint_package, state_dict_sha256  # noqa: E402
from ptcg_rl.g3.checkpoint import (  # noqa: E402
    load_training_checkpoint_model_state,
    save_training_checkpoint,
)
from ptcg_rl.g3.ppo import require_finite_gradients  # noqa: E402


class MaterializedBCTrainError(ValueError):
    """Raised when high-throughput materialized BC violates its training contract."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Mapping[str, Any]) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _positive(value: int, label: str) -> int:
    if isinstance(value, bool) or value <= 0:
        raise MaterializedBCTrainError(f"{label} must be positive")
    return value


def load_materialized_manifest(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    path = root / "manifest.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise MaterializedBCTrainError(f"cannot read materialized manifest: {error}") from error
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise MaterializedBCTrainError("unsupported materialized BC manifest")
    recorded_sha = manifest.get("manifest_sha256")
    if not isinstance(recorded_sha, str) or len(recorded_sha) != 64:
        raise MaterializedBCTrainError("materialized manifest SHA-256 is invalid")
    unhashed = dict(manifest)
    unhashed.pop("manifest_sha256")
    if canonical_sha256(unhashed) != recorded_sha:
        raise MaterializedBCTrainError("materialized manifest self-hash differs")
    source = manifest.get("source")
    if not isinstance(source, Mapping) or source.get("test_episode_bodies_read") != 0:
        raise MaterializedBCTrainError("materialized source did not preserve sealed test bodies")
    records = manifest.get("records")
    if not isinstance(records, list) or not records:
        raise MaterializedBCTrainError("materialized manifest contains no records")
    seen: set[int] = set()
    checked: list[dict[str, Any]] = []
    for position, value in enumerate(records):
        if not isinstance(value, dict):
            raise MaterializedBCTrainError(f"materialized record {position} is not an object")
        try:
            episode_id = int(value["episode_id"])
            split = str(value["split"])
            relative_path = str(value["path"])
            digest = str(value["sha256"])
            byte_count = int(value["bytes"])
        except (KeyError, TypeError, ValueError) as error:
            raise MaterializedBCTrainError(f"materialized record {position} is malformed: {error}") from error
        if episode_id <= 0 or episode_id in seen:
            raise MaterializedBCTrainError(f"duplicate/invalid materialized episode ID {episode_id}")
        seen.add(episode_id)
        if split not in {"train", "validation"}:
            raise MaterializedBCTrainError("materialized cache must contain train/validation only")
        if relative_path != f"episodes/{episode_id}.pt" or len(digest) != 64 or byte_count <= 0:
            raise MaterializedBCTrainError(f"materialized record contract differs for {episode_id}")
        checked.append(dict(value))
    return manifest, checked


def load_all_episodes(
    root: Path,
    records: Sequence[dict[str, Any]],
    workers: int,
) -> list[MaterializedEpisodeV1]:
    if workers <= 0:
        raise MaterializedBCTrainError("loader workers must be positive")

    def load_one(record: dict[str, Any]) -> MaterializedEpisodeV1:
        path = root / str(record["path"])
        if path.stat().st_size != int(record["bytes"]):
            raise MaterializedBCTrainError(
                f"materialized byte count differs for episode {record['episode_id']}"
            )
        episode = load_materialized_episode(path, expected_sha256=str(record["sha256"]))
        if episode.episode_id != int(record["episode_id"]) or episode.split != str(record["split"]):
            raise MaterializedBCTrainError(
                f"materialized episode identity differs for {record['episode_id']}"
            )
        if episode.policy_targets != int(record["policy_targets"]):
            raise MaterializedBCTrainError(
                f"materialized policy-target count differs for {record['episode_id']}"
            )
        return episode

    with ThreadPoolExecutor(max_workers=workers) as pool:
        episodes = list(pool.map(load_one, records))
    episodes.sort(key=lambda episode: episode.episode_id)
    return episodes


def deterministic_order(
    episodes: Sequence[MaterializedEpisodeV1], seed: int, epoch: int
) -> list[MaterializedEpisodeV1]:
    return sorted(
        episodes,
        key=lambda episode: (
            hashlib.sha256(
                f"bc-materialized-order|{seed}|{epoch}|{episode.episode_id}".encode("ascii")
            ).hexdigest(),
            episode.episode_id,
        ),
    )


def batch_groups(
    episodes: Sequence[MaterializedEpisodeV1], batch_size: int
) -> list[list[MaterializedEpisodeV1]]:
    return [list(episodes[start : start + batch_size]) for start in range(0, len(episodes), batch_size)]


def prepack_groups(
    episodes: Sequence[MaterializedEpisodeV1],
    *,
    batch_size: int,
    sequence_length: int,
    seed: int,
    pin_memory: bool,
) -> tuple[PackedRecurrentGroup, ...]:
    ordered = deterministic_order(episodes, seed, 0)
    groups = batch_groups(ordered, batch_size)
    packed: list[PackedRecurrentGroup] = []
    for group in groups:
        packed.append(
            pack_recurrent_group(
                tuple(episode.decisions for episode in group),
                sequence_length=sequence_length,
                pin_memory=pin_memory,
            )
        )
    return tuple(packed)


def train_epoch_packed(
    model: Any,
    optimizer: torch.optim.Optimizer,
    scheduler: Any,
    groups: Sequence[PackedRecurrentGroup],
    *,
    device: torch.device,
    bf16: bool,
    maximum_gradient_norm: float,
    epoch: int,
    maximum_groups: int | None,
) -> dict[str, Any]:
    model.train()
    selected_groups = list(groups)
    if maximum_groups is not None:
        selected_groups = selected_groups[:maximum_groups]
    if not selected_groups:
        raise MaterializedBCTrainError("packed training epoch has no groups")
    started = time.perf_counter()
    policy_targets = 0
    recurrent_decisions = 0
    weighted_loss = 0.0
    optimizer_steps = 0
    gradient_norm_max = 0.0
    forced_only_chunks = 0
    episodes_used = 0

    for group in selected_groups:
        episodes_used += group.batch_size
        hidden = model.initial_hidden(group.batch_size, device)
        for chunk in group.chunks:
            optimizer.zero_grad(set_to_none=True)
            has_policy_target = chunk.policy_targets > 0
            context = torch.enable_grad() if has_policy_target else torch.no_grad()
            with context:
                with torch.autocast(
                    device_type=device.type,
                    dtype=torch.bfloat16,
                    enabled=bf16 and device.type == "cuda",
                ):
                    result = packed_recurrent_chunk_loss(
                        model,
                        chunk,
                        hidden=hidden,
                        non_blocking=device.type == "cuda",
                    )
            hidden = result.next_hidden.detach()
            recurrent_decisions += result.recurrent_decisions
            if result.loss is None:
                forced_only_chunks += 1
                continue
            loss = result.loss
            if not bool(torch.isfinite(loss).detach().cpu()):
                raise MaterializedBCTrainError("packed training loss is nonfinite")
            loss.backward()
            gradient_norm = require_finite_gradients(tuple(model.parameters()))
            gradient_norm_max = max(gradient_norm_max, float(gradient_norm))
            torch.nn.utils.clip_grad_norm_(
                model.parameters(), maximum_gradient_norm, error_if_nonfinite=True
            )
            optimizer.step()
            scheduler.step()
            optimizer_steps += 1
            policy_targets += result.policy_targets
            weighted_loss += float(loss.detach().float().cpu()) * result.policy_targets

    if device.type == "cuda":
        torch.cuda.synchronize(device)
    elapsed = time.perf_counter() - started
    if policy_targets <= 0 or optimizer_steps <= 0:
        raise MaterializedBCTrainError("packed training epoch executed no policy targets")
    return {
        "epoch": epoch,
        "episode_groups": len(selected_groups),
        "episodes": episodes_used,
        "optimizer_steps": optimizer_steps,
        "policy_targets": policy_targets,
        "recurrent_decisions": recurrent_decisions,
        "forced_only_chunks": forced_only_chunks,
        "mean_nll": weighted_loss / policy_targets,
        "gradient_norm_max_pre_clip": gradient_norm_max,
        "elapsed_seconds": elapsed,
        "policy_targets_per_second": policy_targets / max(elapsed, 1e-9),
        "recurrent_decisions_per_second": recurrent_decisions / max(elapsed, 1e-9),
    }


def validate_packed(
    model: Any,
    groups: Sequence[PackedRecurrentGroup],
    *,
    device: torch.device,
    bf16: bool,
    maximum_groups: int | None,
) -> dict[str, Any]:
    model.eval()
    selected_groups = list(groups)
    if maximum_groups is not None:
        selected_groups = selected_groups[:maximum_groups]
    if not selected_groups:
        raise MaterializedBCTrainError("packed validation has no groups")
    started = time.perf_counter()
    policy_targets = 0
    recurrent_decisions = 0
    weighted_loss = 0.0
    episodes_used = 0
    with torch.inference_mode():
        for group in selected_groups:
            episodes_used += group.batch_size
            hidden = model.initial_hidden(group.batch_size, device)
            for chunk in group.chunks:
                with torch.autocast(
                    device_type=device.type,
                    dtype=torch.bfloat16,
                    enabled=bf16 and device.type == "cuda",
                ):
                    result = packed_recurrent_chunk_loss(
                        model,
                        chunk,
                        hidden=hidden,
                        non_blocking=device.type == "cuda",
                    )
                hidden = result.next_hidden
                recurrent_decisions += result.recurrent_decisions
                if result.loss is not None:
                    value = float(result.loss.detach().float().cpu())
                    if not math.isfinite(value):
                        raise MaterializedBCTrainError("packed validation NLL is nonfinite")
                    policy_targets += result.policy_targets
                    weighted_loss += value * result.policy_targets
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    elapsed = time.perf_counter() - started
    if policy_targets <= 0:
        raise MaterializedBCTrainError("packed validation produced no policy targets")
    return {
        "episode_groups": len(selected_groups),
        "episodes": episodes_used,
        "policy_targets": policy_targets,
        "recurrent_decisions": recurrent_decisions,
        "mean_nll": weighted_loss / policy_targets,
        "elapsed_seconds": elapsed,
        "policy_targets_per_second": policy_targets / max(elapsed, 1e-9),
    }


def train_epoch(
    model: Any,
    optimizer: torch.optim.Optimizer,
    scheduler: Any,
    episodes: Sequence[MaterializedEpisodeV1],
    *,
    device: torch.device,
    batch_size: int,
    sequence_length: int,
    bf16: bool,
    maximum_gradient_norm: float,
    seed: int,
    epoch: int,
    maximum_groups: int | None,
) -> dict[str, Any]:
    model.train()
    ordered = deterministic_order(episodes, seed, epoch)
    groups = batch_groups(ordered, batch_size)
    if maximum_groups is not None:
        groups = groups[:maximum_groups]
    if not groups:
        raise MaterializedBCTrainError("materialized training epoch has no groups")

    started = time.perf_counter()
    policy_targets = 0
    recurrent_decisions = 0
    weighted_loss = 0.0
    optimizer_steps = 0
    gradient_norm_max = 0.0
    forced_only_chunks = 0
    episodes_used = 0

    for group in groups:
        episodes_used += len(group)
        hidden_states = [model.initial_hidden(1, device)[0] for _ in group]
        maximum_length = max(len(episode.decisions) for episode in group)
        for start in range(0, maximum_length, sequence_length):
            active = [index for index, episode in enumerate(group) if start < len(episode.decisions)]
            sequences = tuple(
                group[index].decisions[start : start + sequence_length] for index in active
            )
            hidden = torch.stack([hidden_states[index] for index in active], dim=0)
            has_policy_target = any(
                not decision.request.has_only_one_outcome
                for sequence in sequences
                for decision in sequence
            )
            optimizer.zero_grad(set_to_none=True)
            context = torch.enable_grad() if has_policy_target else torch.no_grad()
            with context:
                with torch.autocast(
                    device_type=device.type,
                    dtype=torch.bfloat16,
                    enabled=bf16 and device.type == "cuda",
                ):
                    result = recurrent_sequence_batch_loss(
                        model,
                        sequences,
                        hidden=hidden,
                        verify=False,
                        require_policy_target=has_policy_target,
                    )
            for local_index, episode_index in enumerate(active):
                hidden_states[episode_index] = result.next_hidden[local_index].detach()
            recurrent_decisions += result.recurrent_decisions
            if result.loss is None:
                forced_only_chunks += 1
                continue
            loss = result.loss
            if not bool(torch.isfinite(loss).detach().cpu()):
                raise MaterializedBCTrainError("materialized training loss is nonfinite")
            loss.backward()
            gradient_norm = require_finite_gradients(tuple(model.parameters()))
            gradient_norm_max = max(gradient_norm_max, float(gradient_norm))
            torch.nn.utils.clip_grad_norm_(
                model.parameters(), maximum_gradient_norm, error_if_nonfinite=True
            )
            optimizer.step()
            scheduler.step()
            optimizer_steps += 1
            policy_targets += result.policy_targets
            weighted_loss += float(loss.detach().float().cpu()) * result.policy_targets

    if device.type == "cuda":
        torch.cuda.synchronize(device)
    elapsed = time.perf_counter() - started
    if policy_targets <= 0 or optimizer_steps <= 0:
        raise MaterializedBCTrainError("materialized training epoch executed no policy targets")
    return {
        "epoch": epoch,
        "episode_groups": len(groups),
        "episodes": episodes_used,
        "optimizer_steps": optimizer_steps,
        "policy_targets": policy_targets,
        "recurrent_decisions": recurrent_decisions,
        "forced_only_chunks": forced_only_chunks,
        "mean_nll": weighted_loss / policy_targets,
        "gradient_norm_max_pre_clip": gradient_norm_max,
        "elapsed_seconds": elapsed,
        "policy_targets_per_second": policy_targets / max(elapsed, 1e-9),
        "recurrent_decisions_per_second": recurrent_decisions / max(elapsed, 1e-9),
    }


def validate(
    model: Any,
    episodes: Sequence[MaterializedEpisodeV1],
    *,
    device: torch.device,
    batch_size: int,
    sequence_length: int,
    bf16: bool,
    maximum_groups: int | None,
) -> dict[str, Any]:
    model.eval()
    groups = batch_groups(sorted(episodes, key=lambda episode: episode.episode_id), batch_size)
    if maximum_groups is not None:
        groups = groups[:maximum_groups]
    if not groups:
        raise MaterializedBCTrainError("materialized validation has no groups")
    started = time.perf_counter()
    policy_targets = 0
    recurrent_decisions = 0
    weighted_loss = 0.0
    episodes_used = 0
    with torch.inference_mode():
        for group in groups:
            episodes_used += len(group)
            hidden_states = [model.initial_hidden(1, device)[0] for _ in group]
            maximum_length = max(len(episode.decisions) for episode in group)
            for start in range(0, maximum_length, sequence_length):
                active = [index for index, episode in enumerate(group) if start < len(episode.decisions)]
                sequences = tuple(
                    group[index].decisions[start : start + sequence_length] for index in active
                )
                hidden = torch.stack([hidden_states[index] for index in active], dim=0)
                with torch.autocast(
                    device_type=device.type,
                    dtype=torch.bfloat16,
                    enabled=bf16 and device.type == "cuda",
                ):
                    result = recurrent_sequence_batch_loss(
                        model,
                        sequences,
                        hidden=hidden,
                        verify=False,
                        require_policy_target=False,
                    )
                for local_index, episode_index in enumerate(active):
                    hidden_states[episode_index] = result.next_hidden[local_index]
                recurrent_decisions += result.recurrent_decisions
                if result.loss is not None:
                    value = float(result.loss.detach().float().cpu())
                    if not math.isfinite(value):
                        raise MaterializedBCTrainError("materialized validation NLL is nonfinite")
                    policy_targets += result.policy_targets
                    weighted_loss += value * result.policy_targets
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    elapsed = time.perf_counter() - started
    if policy_targets <= 0:
        raise MaterializedBCTrainError("materialized validation produced no policy targets")
    return {
        "episode_groups": len(groups),
        "episodes": episodes_used,
        "policy_targets": policy_targets,
        "recurrent_decisions": recurrent_decisions,
        "mean_nll": weighted_loss / policy_targets,
        "elapsed_seconds": elapsed,
        "policy_targets_per_second": policy_targets / max(elapsed, 1e-9),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="High-throughput materialized recurrent behavior cloning")
    parser.add_argument("--materialized-dir", type=Path, required=True)
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=ROOT / "private/g2/checkpoint-v1/g2-policy-checkpoint-v1.zip",
    )
    parser.add_argument(
        "--card-table",
        type=Path,
        default=ROOT / "private/g2/card-table-v1.json",
    )
    parser.add_argument("--warm-start-training-checkpoint", type=Path, required=True)
    parser.add_argument("--warm-start-training-checkpoint-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--sequence-length", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=2.5e-5)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--maximum-gradient-norm", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=20260814)
    parser.add_argument("--loader-workers", type=int, default=16)
    parser.add_argument("--bf16", action="store_true")
    parser.add_argument("--train-limit", type=int)
    parser.add_argument("--validation-limit", type=int)
    parser.add_argument("--minimum-teacher-score", type=float)
    parser.add_argument("--maximum-train-groups", type=int)
    parser.add_argument("--maximum-validation-groups", type=int)
    args = parser.parse_args()

    for value, label in (
        (args.epochs, "epochs"),
        (args.batch_size, "batch-size"),
        (args.sequence_length, "sequence-length"),
        (args.loader_workers, "loader-workers"),
    ):
        _positive(value, label)
    for value, label in (
        (args.train_limit, "train-limit"),
        (args.validation_limit, "validation-limit"),
        (args.maximum_train_groups, "maximum-train-groups"),
        (args.maximum_validation_groups, "maximum-validation-groups"),
    ):
        if value is not None:
            _positive(value, label)
    if args.learning_rate <= 0 or args.weight_decay < 0 or args.maximum_gradient_norm <= 0:
        raise MaterializedBCTrainError("optimizer hyperparameters are invalid")
    if args.minimum_teacher_score is not None and args.minimum_teacher_score <= 0:
        raise MaterializedBCTrainError("minimum teacher score must be positive")

    device = torch.device(args.device)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise MaterializedBCTrainError("CUDA requested but unavailable")
    if args.bf16 and (device.type != "cuda" or not torch.cuda.is_bf16_supported()):
        raise MaterializedBCTrainError("BF16 requested but unsupported")
    if args.output_dir.exists():
        raise MaterializedBCTrainError(f"output directory already exists: {args.output_dir}")

    random.seed(args.seed)
    np.random.seed(args.seed % (2**32))
    torch.manual_seed(args.seed)
    torch.set_float32_matmul_precision("high")
    if device.type == "cuda":
        torch.cuda.manual_seed_all(args.seed)
        torch.cuda.reset_peak_memory_stats(device)

    manifest, records = load_materialized_manifest(args.materialized_dir)
    if args.minimum_teacher_score is not None:
        filtered_records: list[dict[str, Any]] = []
        for record in records:
            value = record.get("teacher_score_qualification_value")
            if value is None:
                raise MaterializedBCTrainError(
                    "minimum-teacher-score requested but materialized records lack teacher score provenance"
                )
            try:
                teacher_score = float(value)
            except (TypeError, ValueError) as error:
                raise MaterializedBCTrainError(
                    f"invalid teacher score provenance for episode {record['episode_id']}"
                ) from error
            if teacher_score >= args.minimum_teacher_score:
                filtered_records.append(record)
        records = filtered_records
        if not records:
            raise MaterializedBCTrainError("minimum teacher score filter removed all materialized records")
    train_records = sorted(
        (record for record in records if record["split"] == "train"),
        key=lambda record: int(record["episode_id"]),
    )
    validation_records = sorted(
        (record for record in records if record["split"] == "validation"),
        key=lambda record: int(record["episode_id"]),
    )
    if args.train_limit is not None:
        train_records = train_records[: args.train_limit]
    if args.validation_limit is not None:
        validation_records = validation_records[: args.validation_limit]
    selected_records = [*train_records, *validation_records]
    load_started = time.perf_counter()
    episodes = load_all_episodes(args.materialized_dir, selected_records, args.loader_workers)
    load_elapsed = time.perf_counter() - load_started
    train_episodes = [episode for episode in episodes if episode.split == "train"]
    validation_episodes = [episode for episode in episodes if episode.split == "validation"]
    if not train_episodes or not validation_episodes:
        raise MaterializedBCTrainError("materialized train/validation splits must both be nonempty")

    prepack_started = time.perf_counter()
    train_groups = prepack_groups(
        train_episodes,
        batch_size=args.batch_size,
        sequence_length=args.sequence_length,
        seed=args.seed,
        pin_memory=device.type == "cuda",
    )
    validation_groups = prepack_groups(
        validation_episodes,
        batch_size=args.batch_size,
        sequence_length=args.sequence_length,
        seed=args.seed + 1,
        pin_memory=device.type == "cuda",
    )
    prepack_elapsed = time.perf_counter() - prepack_started
    train_episode_count = len(train_episodes)
    gpu_resident_started = time.perf_counter()
    gpu_resident_packed = device.type == "cuda"
    if gpu_resident_packed:
        train_groups = tuple(
            packed_recurrent_group_to_device(group, device, non_blocking=True)
            for group in train_groups
        )
        validation_groups = tuple(
            packed_recurrent_group_to_device(group, device, non_blocking=True)
            for group in validation_groups
        )
        torch.cuda.synchronize(device)
    gpu_resident_elapsed = time.perf_counter() - gpu_resident_started
    validation_episode_count = len(validation_episodes)
    del episodes, train_episodes, validation_episodes

    card_table = load_card_table(args.card_table)
    if manifest.get("card_data_sha256") != card_table.card_data_sha256:
        raise MaterializedBCTrainError("materialized card-data hash differs from trainer")
    loaded = load_checkpoint_package(args.checkpoint, device=device)
    model = loaded.model
    base_state_sha = state_dict_sha256(
        {name: tensor.detach().cpu() for name, tensor in model.state_dict().items()}
    )
    warm_start = load_training_checkpoint_model_state(
        args.warm_start_training_checkpoint,
        model=model,
        expected_sha256=args.warm_start_training_checkpoint_sha256,
    )
    initial_state_sha = state_dict_sha256(
        {name: tensor.detach().cpu() for name, tensor in model.state_dict().items()}
    )
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=args.learning_rate,
        weight_decay=args.weight_decay,
        fused=device.type == "cuda",
    )
    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda=lambda _step: 1.0)

    started = time.perf_counter()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    baseline = validate_packed(
        model,
        validation_groups,
        device=device,
        bf16=args.bf16,
        maximum_groups=args.maximum_validation_groups,
    )
    print(
        json.dumps(
            {
                "event": "materialized_baseline_validation",
                "episodes": baseline["episodes"],
                "policy_targets": baseline["policy_targets"],
                "mean_nll": baseline["mean_nll"],
                "targets_per_second": baseline["policy_targets_per_second"],
                "materialized_load_seconds": load_elapsed,
                "prepack_seconds": prepack_elapsed,
                "gpu_resident_pack_seconds": gpu_resident_elapsed,
            },
            sort_keys=True,
        ),
        flush=True,
    )

    history: list[dict[str, Any]] = [{"epoch": 0, "training": None, "validation": baseline}]
    checkpoint_receipts: list[dict[str, Any]] = []
    cumulative_optimizer_steps = 0
    cumulative_policy_targets = 0
    for epoch in range(1, args.epochs + 1):
        training = train_epoch_packed(
            model,
            optimizer,
            scheduler,
            train_groups,
            device=device,
            bf16=args.bf16,
            maximum_gradient_norm=args.maximum_gradient_norm,
            epoch=epoch,
            maximum_groups=args.maximum_train_groups,
        )
        cumulative_optimizer_steps += int(training["optimizer_steps"])
        cumulative_policy_targets += int(training["policy_targets"])
        validation = validate_packed(
            model,
            validation_groups,
            device=device,
            bf16=args.bf16,
            maximum_groups=args.maximum_validation_groups,
        )
        checkpoint_path = args.output_dir / f"epoch-{epoch}.pt"
        receipt = save_training_checkpoint(
            checkpoint_path,
            model=model,
            optimizer=optimizer,
            scheduler=scheduler,
            scaler=None,
            counters={
                "epoch": epoch,
                "optimizer_steps": cumulative_optimizer_steps,
                "policy_targets": cumulative_policy_targets,
            },
            league={
                "kind": "materialized-deck-specialist-bc",
                "production_eligible": False,
                "materialized_manifest_sha256": manifest["manifest_sha256"],
                "warm_start_training_checkpoint_sha256": warm_start.payload_sha256,
            },
            rollout_boundary={"completed_epoch": epoch},
            include_cuda_rng=device.type == "cuda",
        )
        checkpoint_receipts.append(
            {
                "epoch": epoch,
                "path": checkpoint_path.name,
                "payload_sha256": receipt["payload_sha256"],
                "payload_bytes": receipt["payload_bytes"],
            }
        )
        history.append({"epoch": epoch, "training": training, "validation": validation})
        memory = int(torch.cuda.max_memory_allocated(device)) if device.type == "cuda" else 0
        print(
            json.dumps(
                {
                    "event": "materialized_epoch_complete",
                    "epoch": epoch,
                    "training_mean_nll": training["mean_nll"],
                    "training_policy_targets": training["policy_targets"],
                    "training_targets_per_second": training["policy_targets_per_second"],
                    "validation_mean_nll": validation["mean_nll"],
                    "validation_targets_per_second": validation["policy_targets_per_second"],
                    "optimizer_steps": training["optimizer_steps"],
                    "peak_allocated_bytes": memory,
                },
                sort_keys=True,
            ),
            flush=True,
        )

    final_state_sha = state_dict_sha256(
        {name: tensor.detach().cpu() for name, tensor in model.state_dict().items()}
    )
    best = min(history, key=lambda item: float(item["validation"]["mean_nll"]))
    gpu = None
    memory = {"peak_allocated_bytes": 0, "allocated_bytes": 0, "reserved_bytes": 0}
    if device.type == "cuda":
        properties = torch.cuda.get_device_properties(device)
        gpu = {
            "name": properties.name,
            "compute_capability": f"{properties.major}.{properties.minor}",
            "total_memory_bytes": int(properties.total_memory),
            "bf16_supported": bool(torch.cuda.is_bf16_supported()),
        }
        memory = {
            "peak_allocated_bytes": int(torch.cuda.max_memory_allocated(device)),
            "allocated_bytes": int(torch.cuda.memory_allocated(device)),
            "reserved_bytes": int(torch.cuda.memory_reserved(device)),
        }
    report = {
        "schema_version": 1,
        "record_id": "bc-materialized-training-v1",
        "status": "PASS_MATERIALIZED_BC_TRAINING_COMPLETED",
        "materialized": {
            "record_id": manifest.get("record_id"),
            "manifest_sha256": manifest["manifest_sha256"],
            "episodes_loaded": train_episode_count + validation_episode_count,
            "train_episodes_used": train_episode_count,
            "validation_episodes_used": validation_episode_count,
            "test_episode_bodies_read": 0,
            "load_seconds": load_elapsed,
            "prepack_seconds": prepack_elapsed,
            "gpu_resident_pack_seconds": gpu_resident_elapsed,
            "host_peak_rss_kib": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
        },
        "model": {
            "checkpoint_sha256": loaded.package_sha256,
            "base_package_state_sha256": base_state_sha,
            "warm_start_training_checkpoint_sha256": warm_start.payload_sha256,
            "warm_start_optimizer_state_restored": False,
            "warm_start_rng_state_restored": False,
            "trainable_parameters": int(model.trainable_parameter_count),
            "architecture_sha256": model.architecture_sha256,
            "initial_state_sha256": initial_state_sha,
            "final_state_sha256": final_state_sha,
            "state_changed": final_state_sha != initial_state_sha,
        },
        "configuration": {
            "device": str(device),
            "bf16": bool(args.bf16),
            "batch_size_episodes": args.batch_size,
            "sequence_length": args.sequence_length,
            "epochs": args.epochs,
            "learning_rate": args.learning_rate,
            "weight_decay": args.weight_decay,
            "maximum_gradient_norm": args.maximum_gradient_norm,
            "optimizer": "AdamW-fused" if device.type == "cuda" else "AdamW",
            "scheduler": "constant",
            "seed": args.seed,
            "loader_workers": args.loader_workers,
            "minimum_teacher_score": args.minimum_teacher_score,
            "vectorized_compound_decoder": True,
            "replay_json_parsing_inside_epoch": False,
            "projected_features_reused_across_epochs": True,
            "precollated_tensors_reused_across_epochs": True,
            "pinned_host_batches": device.type == "cuda",
            "nonblocking_h2d": device.type == "cuda",
            "gpu_resident_packed_batches": gpu_resident_packed,
            "truncated_bptt": True,
            "hidden_carried_between_chunks": True,
        },
        "history": history,
        "best_epoch": int(best["epoch"]),
        "best_validation_mean_nll": float(best["validation"]["mean_nll"]),
        "baseline_validation_mean_nll": float(baseline["mean_nll"]),
        "selected_checkpoint_for_evaluation": (
            None if int(best["epoch"]) == 0 else f"epoch-{int(best['epoch'])}.pt"
        ),
        "checkpoint_receipts": checkpoint_receipts,
        "gpu": gpu,
        "memory": memory,
        "elapsed_seconds": time.perf_counter() - started,
        "production_checkpoint_eligible": False,
        "competence_claimed": False,
    }
    report_path = args.output_dir / "training-report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
