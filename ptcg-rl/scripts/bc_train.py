from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ptcg_rl.bc.training import recurrent_sequence_batch_loss  # noqa: E402
from ptcg_rl.g2.card_table import load_card_table  # noqa: E402
from ptcg_rl.g2.checkpoint import load_checkpoint_package, state_dict_sha256  # noqa: E402
from ptcg_rl.g3.bc_canary import TeacherEpisodeV1, build_semantic_loader_plan  # noqa: E402
from ptcg_rl.g3.checkpoint import save_training_checkpoint  # noqa: E402
from ptcg_rl.g3.ppo import require_finite_gradients  # noqa: E402
from ptcg_rl.replay.semantic_loader import SemanticReplayLoader  # noqa: E402


class BCTrainError(ValueError):
    """Raised when a production BC training input or runtime invariant fails."""


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
        raise BCTrainError(f"{label} must be positive")
    return value


def load_bundle_manifest(
    bundle: Path, *, expected_bundle_sha256: str | None = None
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not bundle.is_file():
        raise BCTrainError(f"BC bundle is missing: {bundle}")
    observed_bundle_sha = sha256_file(bundle)
    if expected_bundle_sha256 is not None and observed_bundle_sha != expected_bundle_sha256:
        raise BCTrainError(
            "BC bundle SHA-256 differs: "
            f"expected {expected_bundle_sha256}, observed {observed_bundle_sha}"
        )
    try:
        with zipfile.ZipFile(bundle) as archive:
            raw = archive.read("manifest.json")
    except (OSError, zipfile.BadZipFile, KeyError) as error:
        raise BCTrainError(f"cannot read BC bundle manifest: {error}") from error
    try:
        manifest = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BCTrainError(f"BC manifest is invalid JSON: {error}") from error
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise BCTrainError("unsupported BC bundle manifest")
    manifest_sha = manifest.get("manifest_sha256")
    if manifest_sha is not None:
        if not isinstance(manifest_sha, str) or len(manifest_sha) != 64:
            raise BCTrainError("BC manifest SHA-256 field is invalid")
        unhashed = dict(manifest)
        unhashed.pop("manifest_sha256")
        observed_manifest_sha = canonical_sha256(unhashed)
        if observed_manifest_sha != manifest_sha:
            raise BCTrainError(
                "BC manifest self-hash differs: "
                f"expected {manifest_sha}, observed {observed_manifest_sha}"
            )
    records = manifest.get("records")
    if not isinstance(records, list) or not records:
        raise BCTrainError("BC manifest contains no records")
    episode_ids: set[int] = set()
    for position, value in enumerate(records):
        if not isinstance(value, dict):
            raise BCTrainError(f"BC record {position} must be an object")
        try:
            episode_id = int(value["episode_id"])
            split = str(value["split"])
            path = str(value["path"])
            byte_count = int(value["bytes"])
            teacher_index = int(value["teacher_player_index"])
        except (KeyError, TypeError, ValueError) as error:
            raise BCTrainError(f"BC record {position} is malformed: {error}") from error
        if episode_id <= 0 or episode_id in episode_ids:
            raise BCTrainError(f"duplicate or invalid episode ID: {episode_id}")
        episode_ids.add(episode_id)
        if split not in {"train", "validation", "test"}:
            raise BCTrainError(f"unsupported BC split for {episode_id}: {split}")
        if path != f"{episode_id}.json" or byte_count <= 0 or teacher_index not in (0, 1):
            raise BCTrainError(f"BC record contract differs for episode {episode_id}")
        digest = value.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise BCTrainError(f"BC replay SHA-256 is invalid for episode {episode_id}")
    return manifest, records


def deterministic_order(records: Sequence[dict[str, Any]], seed: int, epoch: int) -> list[dict[str, Any]]:
    return sorted(
        records,
        key=lambda record: (
            hashlib.sha256(
                f"bc-order|{seed}|{epoch}|{int(record['episode_id'])}".encode("ascii")
            ).hexdigest(),
            int(record["episode_id"]),
        ),
    )


def extract_records(
    bundle: Path,
    records: Sequence[dict[str, Any]],
    destination: Path,
) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(bundle) as archive:
        for record in records:
            episode_id = int(record["episode_id"])
            name = f"episodes/{episode_id}.json"
            try:
                info = archive.getinfo(name)
            except KeyError as error:
                raise BCTrainError(f"BC bundle is missing episode {episode_id}") from error
            if info.file_size != int(record["bytes"]):
                raise BCTrainError(f"BC bundle size differs for episode {episode_id}")
            target = destination / f"{episode_id}.json"
            digest = hashlib.sha256()
            with archive.open(info, "r") as source, target.open("wb") as sink:
                while True:
                    chunk = source.read(8 * 1024 * 1024)
                    if not chunk:
                        break
                    sink.write(chunk)
                    digest.update(chunk)
            if digest.hexdigest() != record["sha256"]:
                target.unlink(missing_ok=True)
                raise BCTrainError(f"BC replay SHA-256 differs for episode {episode_id}")


def load_teacher_batch(
    records: Sequence[dict[str, Any]],
    extracted: Path,
    card_data_sha256: str,
) -> tuple[TeacherEpisodeV1, ...]:
    if not records:
        raise BCTrainError("cannot load an empty teacher batch")
    with tempfile.TemporaryDirectory(prefix="kptcg-bc-batch-") as temporary:
        staged = Path(temporary) / "episodes"
        staged.mkdir()
        for record in records:
            episode_id = int(record["episode_id"])
            source = extracted / f"{episode_id}.json"
            target = staged / source.name
            try:
                os.link(source, target)
            except OSError:
                shutil.copyfile(source, target)
        plan = build_semantic_loader_plan(
            [
                {"episode_id": int(record["episode_id"]), "bytes": int(record["bytes"])}
                for record in records
            ]
        )
        by_id = {int(record["episode_id"]): record for record in records}
        grouped: dict[int, list[Any]] = {episode_id: [] for episode_id in by_id}
        loader = SemanticReplayLoader(plan, staged, card_data_sha256=card_data_sha256)
        for decision in loader:
            episode_id = int(decision.episode_id)
            if decision.agent_index == int(by_id[episode_id]["teacher_player_index"]):
                grouped[episode_id].append(decision)

    episodes: list[TeacherEpisodeV1] = []
    for record in records:
        episode_id = int(record["episode_id"])
        decisions = tuple(grouped[episode_id])
        if not decisions:
            raise BCTrainError(f"teacher episode {episode_id} produced no decisions")
        if [decision.sequence_index for decision in decisions] != list(range(len(decisions))):
            raise BCTrainError(f"teacher sequence is noncontiguous for episode {episode_id}")
        expected_requests = int(record["teacher_active_requests"])
        if len(decisions) != expected_requests:
            raise BCTrainError(
                f"teacher decision count differs for episode {episode_id}: "
                f"expected {expected_requests}, observed {len(decisions)}"
            )
        meaningful = sum(not decision.request.has_only_one_outcome for decision in decisions)
        if meaningful <= 0:
            raise BCTrainError(f"teacher episode {episode_id} has no policy target")
        episodes.append(
            TeacherEpisodeV1(
                episode_id=episode_id,
                teacher_player_index=int(record["teacher_player_index"]),
                decisions=decisions,
                expected_meaningful_decisions=meaningful,
                teacher_key=str(record.get("teacher_team_name", "public-winner")),
                stratum=f"seat_{int(record['teacher_player_index'])}_{record.get('teacher_result', 'win')}",
            )
        )
    return tuple(episodes)


def _batch_groups(records: Sequence[dict[str, Any]], batch_size: int) -> list[list[dict[str, Any]]]:
    return [list(records[start : start + batch_size]) for start in range(0, len(records), batch_size)]


def train_epoch(
    model: Any,
    optimizer: torch.optim.Optimizer,
    scheduler: Any,
    records: Sequence[dict[str, Any]],
    extracted: Path,
    card_data_sha256: str,
    *,
    device: torch.device,
    batch_size: int,
    sequence_length: int,
    bf16: bool,
    maximum_gradient_norm: float,
    seed: int,
    epoch: int,
    maximum_batches: int | None,
) -> dict[str, Any]:
    model.train()
    ordered = deterministic_order(records, seed, epoch)
    groups = _batch_groups(ordered, batch_size)
    if maximum_batches is not None:
        groups = groups[:maximum_batches]
    if not groups:
        raise BCTrainError("training epoch has no episode groups")

    started = time.perf_counter()
    policy_targets = 0
    recurrent_decisions = 0
    weighted_loss = 0.0
    optimizer_steps = 0
    gradient_norm_max = 0.0
    forced_only_chunks = 0
    episode_count = 0

    for group in groups:
        episodes = load_teacher_batch(group, extracted, card_data_sha256)
        episode_count += len(episodes)
        hidden_states = [model.initial_hidden(1, device)[0] for _ in episodes]
        maximum_length = max(len(episode.decisions) for episode in episodes)
        for start in range(0, maximum_length, sequence_length):
            active = [index for index, episode in enumerate(episodes) if start < len(episode.decisions)]
            sequences = tuple(
                episodes[index].decisions[start : start + sequence_length] for index in active
            )
            hidden = torch.stack([hidden_states[index] for index in active], dim=0)
            has_policy_target = any(
                not decision.request.has_only_one_outcome
                for sequence in sequences
                for decision in sequence
            )
            optimizer.zero_grad(set_to_none=True)
            context = (
                torch.enable_grad() if has_policy_target else torch.no_grad()
            )
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
                raise BCTrainError("training loss is nonfinite")
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
        raise BCTrainError("training epoch executed no policy targets")
    return {
        "epoch": epoch,
        "episode_groups": len(groups),
        "episodes": episode_count,
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
    records: Sequence[dict[str, Any]],
    extracted: Path,
    card_data_sha256: str,
    *,
    device: torch.device,
    batch_size: int,
    sequence_length: int,
    bf16: bool,
    maximum_batches: int | None,
) -> dict[str, Any]:
    model.eval()
    groups = _batch_groups(sorted(records, key=lambda record: int(record["episode_id"])), batch_size)
    if maximum_batches is not None:
        groups = groups[:maximum_batches]
    if not groups:
        raise BCTrainError("validation has no episode groups")
    started = time.perf_counter()
    policy_targets = 0
    recurrent_decisions = 0
    weighted_loss = 0.0
    episode_count = 0
    with torch.inference_mode():
        for group in groups:
            episodes = load_teacher_batch(group, extracted, card_data_sha256)
            episode_count += len(episodes)
            hidden_states = [model.initial_hidden(1, device)[0] for _ in episodes]
            maximum_length = max(len(episode.decisions) for episode in episodes)
            for start in range(0, maximum_length, sequence_length):
                active = [index for index, episode in enumerate(episodes) if start < len(episode.decisions)]
                sequences = tuple(
                    episodes[index].decisions[start : start + sequence_length] for index in active
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
                        raise BCTrainError("validation NLL is nonfinite")
                    policy_targets += result.policy_targets
                    weighted_loss += value * result.policy_targets
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    elapsed = time.perf_counter() - started
    if policy_targets <= 0:
        raise BCTrainError("validation produced no policy targets")
    return {
        "episode_groups": len(groups),
        "episodes": episode_count,
        "policy_targets": policy_targets,
        "recurrent_decisions": recurrent_decisions,
        "mean_nll": weighted_loss / policy_targets,
        "elapsed_seconds": elapsed,
        "policy_targets_per_second": policy_targets / max(elapsed, 1e-9),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Full-episode recurrent behavior cloning")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--expected-bundle-sha256")
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
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--epochs", type=int, default=2)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--sequence-length", type=int, default=32)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--maximum-gradient-norm", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=20260814)
    parser.add_argument("--bf16", action="store_true")
    parser.add_argument("--train-limit", type=int)
    parser.add_argument("--validation-limit", type=int)
    parser.add_argument("--maximum-train-batches", type=int)
    parser.add_argument("--maximum-validation-batches", type=int)
    args = parser.parse_args()

    for value, label in (
        (args.epochs, "epochs"),
        (args.batch_size, "batch-size"),
        (args.sequence_length, "sequence-length"),
    ):
        _positive(value, label)
    if args.learning_rate <= 0 or args.weight_decay < 0 or args.maximum_gradient_norm <= 0:
        raise BCTrainError("optimizer hyperparameters are invalid")
    for value, label in (
        (args.train_limit, "train-limit"),
        (args.validation_limit, "validation-limit"),
        (args.maximum_train_batches, "maximum-train-batches"),
        (args.maximum_validation_batches, "maximum-validation-batches"),
    ):
        if value is not None:
            _positive(value, label)

    device = torch.device(args.device)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise BCTrainError("CUDA requested but unavailable")
    if args.bf16 and (device.type != "cuda" or not torch.cuda.is_bf16_supported()):
        raise BCTrainError("BF16 requested but unsupported")
    if args.output_dir.exists():
        raise BCTrainError(f"output directory already exists: {args.output_dir}")

    random.seed(args.seed)
    np.random.seed(args.seed % (2**32))
    torch.manual_seed(args.seed)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(args.seed)
        torch.cuda.reset_peak_memory_stats(device)

    manifest, all_records = load_bundle_manifest(
        args.bundle, expected_bundle_sha256=args.expected_bundle_sha256
    )
    train_records = [record for record in all_records if record["split"] == "train"]
    validation_records = [record for record in all_records if record["split"] == "validation"]
    test_records = [record for record in all_records if record["split"] == "test"]
    if args.train_limit is not None:
        train_records = sorted(train_records, key=lambda record: int(record["episode_id"]))[: args.train_limit]
    if args.validation_limit is not None:
        validation_records = sorted(validation_records, key=lambda record: int(record["episode_id"]))[: args.validation_limit]
    if not train_records or not validation_records:
        raise BCTrainError("training and validation splits must both be nonempty")

    card_table = load_card_table(args.card_table)
    loaded = load_checkpoint_package(args.checkpoint, device=device)
    model = loaded.model
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
    staging_root = Path(tempfile.mkdtemp(prefix="kptcg-bc-train-staging-"))
    data_dir = staging_root / "episodes"
    selected_records = [*train_records, *validation_records]
    extract_records(args.bundle, selected_records, data_dir)

    baseline_validation = validate(
        model,
        validation_records,
        data_dir,
        card_table.card_data_sha256,
        device=device,
        batch_size=args.batch_size,
        sequence_length=args.sequence_length,
        bf16=args.bf16,
        maximum_batches=args.maximum_validation_batches,
    )
    print(
        json.dumps(
            {
                "event": "baseline_validation",
                "episodes": baseline_validation["episodes"],
                "policy_targets": baseline_validation["policy_targets"],
                "mean_nll": baseline_validation["mean_nll"],
                "elapsed_seconds": baseline_validation["elapsed_seconds"],
            },
            sort_keys=True,
        ),
        flush=True,
    )
    history: list[dict[str, Any]] = [
        {"epoch": 0, "validation": baseline_validation, "training": None}
    ]
    checkpoint_receipts: list[dict[str, Any]] = []
    cumulative_optimizer_steps = 0
    for epoch in range(1, args.epochs + 1):
        training = train_epoch(
            model,
            optimizer,
            scheduler,
            train_records,
            data_dir,
            card_table.card_data_sha256,
            device=device,
            batch_size=args.batch_size,
            sequence_length=args.sequence_length,
            bf16=args.bf16,
            maximum_gradient_norm=args.maximum_gradient_norm,
            seed=args.seed,
            epoch=epoch,
            maximum_batches=args.maximum_train_batches,
        )
        cumulative_optimizer_steps += int(training["optimizer_steps"])
        validation = validate(
            model,
            validation_records,
            data_dir,
            card_table.card_data_sha256,
            device=device,
            batch_size=args.batch_size,
            sequence_length=args.sequence_length,
            bf16=args.bf16,
            maximum_batches=args.maximum_validation_batches,
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
                "policy_targets": sum(
                    int(item["training"]["policy_targets"])
                    for item in history[1:]
                    if item["training"] is not None
                )
                + int(training["policy_targets"]),
            },
            league={
                "kind": "recent-high-quality-recurrent-bc",
                "production_eligible": False,
                "bundle_sha256": sha256_file(args.bundle),
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
        print(
            json.dumps(
                {
                    "event": "epoch_complete",
                    "epoch": epoch,
                    "training_mean_nll": training["mean_nll"],
                    "training_policy_targets": training["policy_targets"],
                    "training_targets_per_second": training["policy_targets_per_second"],
                    "validation_mean_nll": validation["mean_nll"],
                    "validation_policy_targets": validation["policy_targets"],
                    "optimizer_steps": training["optimizer_steps"],
                },
                sort_keys=True,
            ),
            flush=True,
        )

    shutil.rmtree(staging_root)
    final_state_sha = state_dict_sha256(
        {name: tensor.detach().cpu() for name, tensor in model.state_dict().items()}
    )
    best = min(history, key=lambda item: float(item["validation"]["mean_nll"]))
    if int(best["epoch"]) == 0:
        selected_checkpoint = None
    else:
        selected_checkpoint = f"epoch-{int(best['epoch'])}.pt"
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
        "record_id": "bc-full-episode-training-v1",
        "status": "PASS_BC_TRAINING_COMPLETED",
        "bundle": {
            "record_id": manifest.get("record_id"),
            "sha256": sha256_file(args.bundle),
            "manifest_sha256": manifest.get("manifest_sha256"),
            "all_episodes": len(all_records),
            "train_episodes_used": len(train_records),
            "validation_episodes_used": len(validation_records),
            "test_episodes_sealed": len(test_records),
            "test_episode_bodies_read": 0,
        },
        "model": {
            "checkpoint_sha256": loaded.package_sha256,
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
            "truncated_bptt": True,
            "hidden_carried_between_chunks": True,
            "forced_calls_advance_recurrence": True,
            "forced_calls_create_policy_loss": False,
        },
        "history": history,
        "best_epoch": int(best["epoch"]),
        "best_validation_mean_nll": float(best["validation"]["mean_nll"]),
        "baseline_validation_mean_nll": float(baseline_validation["mean_nll"]),
        "selected_checkpoint_for_evaluation": selected_checkpoint,
        "checkpoint_receipts": checkpoint_receipts,
        "gpu": gpu,
        "memory": memory,
        "elapsed_seconds": time.perf_counter() - started,
        "production_checkpoint_eligible": False,
        "competence_claimed": False,
    }
    report_path = args.output_dir / "training-report.json"
    partial = report_path.with_suffix(".json.partial")
    partial.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    partial.replace(report_path)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
