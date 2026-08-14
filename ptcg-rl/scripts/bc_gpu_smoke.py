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
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ptcg_rl.g2.card_table import load_card_table  # noqa: E402
from ptcg_rl.g2.checkpoint import load_checkpoint_package, state_dict_sha256  # noqa: E402
from ptcg_rl.bc.training import recurrent_sequence_batch_loss  # noqa: E402
from ptcg_rl.g3.bc_canary import (  # noqa: E402
    TeacherEpisodeV1,
    _action_nll,
    build_semantic_loader_plan,
)
from ptcg_rl.g3.ppo import require_finite_gradients  # noqa: E402
from ptcg_rl.replay.semantic_loader import SemanticReplayLoader  # noqa: E402


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path) -> tuple[dict, list[dict]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("unsupported BC smoke manifest")
    records = value.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("BC smoke manifest has no records")
    for record in records:
        episode_id = int(record["episode_id"])
        if record["path"] != f"{episode_id}.json":
            raise ValueError(f"episode/path mismatch: {episode_id}")
        if record["split"] not in {"train", "validation", "test"}:
            raise ValueError(f"invalid split: {episode_id}")
        if record["teacher_player_index"] not in (0, 1):
            raise ValueError(f"invalid teacher seat: {episode_id}")
    return value, records


def choose(records: list[dict], split: str, count: int, seed: int) -> list[dict]:
    candidates = [record for record in records if record["split"] == split]
    if len(candidates) < count:
        raise ValueError(f"need {count} {split} episodes, found {len(candidates)}")
    candidates.sort(
        key=lambda record: (
            hashlib.sha256(
                f"{seed}|{split}|{int(record['episode_id'])}".encode("ascii")
            ).hexdigest(),
            int(record["episode_id"]),
        )
    )
    return sorted(candidates[:count], key=lambda record: int(record["episode_id"]))


def stage(records: list[dict], source: Path, destination: Path) -> None:
    destination.mkdir(parents=True)
    for record in records:
        replay = source / record["path"]
        if replay.stat().st_size != int(record["bytes"]):
            raise ValueError(f"replay byte mismatch: {record['episode_id']}")
        if sha256_file(replay) != record["sha256"]:
            raise ValueError(f"replay hash mismatch: {record['episode_id']}")
        target = destination / replay.name
        try:
            os.link(replay, target)
        except OSError:
            shutil.copyfile(replay, target)


def load_teacher_episodes(
    records: list[dict], episodes: Path, card_data_sha256: str
) -> tuple[TeacherEpisodeV1, ...]:
    plan = build_semantic_loader_plan(
        [
            {"episode_id": int(record["episode_id"]), "bytes": int(record["bytes"])}
            for record in records
        ]
    )
    by_id = {int(record["episode_id"]): record for record in records}
    grouped = {episode_id: [] for episode_id in by_id}
    for decision in SemanticReplayLoader(plan, episodes, card_data_sha256=card_data_sha256):
        episode_id = int(decision.episode_id)
        if decision.agent_index == int(by_id[episode_id]["teacher_player_index"]):
            grouped[episode_id].append(decision)
    result = []
    for episode_id in sorted(grouped):
        record = by_id[episode_id]
        decisions = tuple(grouped[episode_id])
        if [decision.sequence_index for decision in decisions] != list(range(len(decisions))):
            raise ValueError(f"noncontiguous teacher sequence: {episode_id}")
        meaningful = sum(not decision.request.has_only_one_outcome for decision in decisions)
        if meaningful <= 0:
            raise ValueError(f"no meaningful teacher targets: {episode_id}")
        result.append(
            TeacherEpisodeV1(
                episode_id=episode_id,
                teacher_player_index=int(record["teacher_player_index"]),
                decisions=decisions,
                expected_meaningful_decisions=meaningful,
                teacher_key=str(record.get("teacher_team_name") or "public-winner"),
                stratum=f"seat_{int(record['teacher_player_index'])}_win",
            )
        )
    return tuple(result)


def validation_nll(model, episodes, device, decision_cap: int) -> tuple[float, int]:
    model.eval()
    losses = []
    with torch.inference_mode():
        for episode in episodes:
            hidden = model.initial_hidden(1, device)
            for decision in episode.decisions[:decision_cap]:
                loss, hidden, _ = _action_nll(model, decision, hidden)
                if loss is not None:
                    losses.append(float(loss.detach().float().cpu()))
    if not losses or not all(math.isfinite(value) for value in losses):
        raise ValueError("validation loss stream is empty or nonfinite")
    return sum(losses) / len(losses), len(losses)


def training_loss(model, episode, device, decision_cap: int):
    hidden = model.initial_hidden(1, device)
    losses = []
    for decision in episode.decisions[:decision_cap]:
        loss, hidden, _ = _action_nll(model, decision, hidden)
        if loss is not None:
            losses.append(loss)
    if not losses:
        raise ValueError(f"training window has no policy target: {episode.episode_id}")
    return torch.stack(losses).mean(), len(losses)


def main() -> int:
    parser = argparse.ArgumentParser(description="Bounded recurrent BC GPU smoke")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--episodes-dir", type=Path, required=True)
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=ROOT / "private/g2/checkpoint-v1/g2-policy-checkpoint-v1.zip",
    )
    parser.add_argument(
        "--card-table", type=Path, default=ROOT / "private/g2/card-table-v1.json"
    )
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--seed", type=int, default=20260814)
    parser.add_argument("--train-episodes", type=int, default=8)
    parser.add_argument("--validation-episodes", type=int, default=4)
    parser.add_argument("--steps", type=int, default=8)
    parser.add_argument("--decision-cap", type=int, default=24)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--bf16", action="store_true")
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    if args.steps <= 0 or args.decision_cap <= 0 or args.batch_size <= 0:
        raise ValueError("steps, decision-cap, and batch-size must be positive")
    if args.bf16 and args.device != "cuda":
        raise ValueError("BF16 smoke mode requires CUDA")
    device = torch.device(args.device)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA requested but unavailable")
    random.seed(args.seed)
    np.random.seed(args.seed % (2**32))
    torch.manual_seed(args.seed)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(args.seed)
        torch.cuda.reset_peak_memory_stats(device)

    manifest, records = load_manifest(args.manifest)
    train_records = choose(records, "train", args.train_episodes, args.seed)
    validation_records = choose(records, "validation", args.validation_episodes, args.seed)
    selected = train_records + validation_records
    card_table = load_card_table(args.card_table)

    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="kptcg-bc-smoke-") as temporary:
        staged = Path(temporary) / "episodes"
        stage(selected, args.episodes_dir, staged)
        teacher = load_teacher_episodes(selected, staged, card_table.card_data_sha256)
    by_id = {episode.episode_id: episode for episode in teacher}
    train = tuple(by_id[int(record["episode_id"])] for record in train_records)
    validation = tuple(by_id[int(record["episode_id"])] for record in validation_records)

    loaded = load_checkpoint_package(args.checkpoint, device=device)
    model = loaded.model
    initial_state = state_dict_sha256(
        {name: tensor.detach().cpu() for name, tensor in model.state_dict().items()}
    )
    baseline_nll, validation_targets = validation_nll(
        model, validation, device, args.decision_cap
    )
    model.train()
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=args.learning_rate,
        weight_decay=1e-4,
        fused=device.type == "cuda",
    )
    losses = []
    gradient_norms = []
    target_counts = []
    step_seconds = []
    for step_index in range(args.steps):
        optimizer.zero_grad(set_to_none=True)
        step_started = time.perf_counter()
        if args.batch_size == 1:
            loss, targets = training_loss(
                model, train[step_index % len(train)], device, args.decision_cap
            )
        else:
            selected_episodes = [
                train[(step_index * args.batch_size + offset) % len(train)]
                for offset in range(args.batch_size)
            ]
            sequences = tuple(
                episode.decisions[: args.decision_cap] for episode in selected_episodes
            )
            with torch.autocast(
                device_type="cuda",
                dtype=torch.bfloat16,
                enabled=args.bf16 and device.type == "cuda",
            ):
                batch_result = recurrent_sequence_batch_loss(
                    model, sequences, verify=False
                )
            loss = batch_result.loss
            targets = batch_result.policy_targets
        if not torch.isfinite(loss):
            raise RuntimeError("nonfinite training loss")
        loss.backward()
        gradient_norm = require_finite_gradients(tuple(model.parameters()))
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0, error_if_nonfinite=True)
        optimizer.step()
        if device.type == "cuda":
            torch.cuda.synchronize(device)
        losses.append(float(loss.detach().float().cpu()))
        gradient_norms.append(float(gradient_norm))
        target_counts.append(targets)
        step_seconds.append(time.perf_counter() - step_started)

    final_nll, final_targets = validation_nll(model, validation, device, args.decision_cap)
    if final_targets != validation_targets:
        raise RuntimeError("validation target count changed")
    final_state = state_dict_sha256(
        {name: tensor.detach().cpu() for name, tensor in model.state_dict().items()}
    )
    if final_state == initial_state:
        raise RuntimeError("optimizer did not mutate model state")

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
        "record_id": "bc-smoke-v1",
        "status": "PASS_SMOKE_TRAINING_COMPLETED",
        "corpus": {
            "manifest_record_id": manifest.get("record_id"),
            "manifest_episodes": len(records),
            "train_episode_ids": [int(record["episode_id"]) for record in train_records],
            "validation_episode_ids": [int(record["episode_id"]) for record in validation_records],
            "train_targets_used": sum(target_counts),
            "validation_targets": validation_targets,
        },
        "model": {
            "checkpoint_sha256": loaded.package_sha256,
            "trainable_parameters": int(model.trainable_parameter_count),
            "architecture_sha256": model.architecture_sha256,
            "initial_state_sha256": initial_state,
            "final_state_sha256": final_state,
            "state_changed": True,
        },
        "training": {
            "device": str(device),
            "optimizer": "AdamW-fused" if device.type == "cuda" else "AdamW",
            "optimizer_steps": args.steps,
            "decision_cap": args.decision_cap,
            "batch_size": args.batch_size,
            "bf16": bool(args.bf16),
            "targets_per_second": sum(target_counts) / max(sum(step_seconds), 1e-9),
            "learning_rate": args.learning_rate,
            "loss_first": losses[0],
            "loss_last": losses[-1],
            "loss_all_finite": all(math.isfinite(value) for value in losses),
            "gradient_norm_max_pre_clip": max(gradient_norms),
            "gradient_norms_all_finite": all(math.isfinite(value) for value in gradient_norms),
            "mean_step_seconds": sum(step_seconds) / len(step_seconds),
            "elapsed_seconds": time.perf_counter() - started,
        },
        "validation": {
            "baseline_mean_nll": baseline_nll,
            "final_mean_nll": final_nll,
            "delta_mean_nll": final_nll - baseline_nll,
        },
        "gpu": gpu,
        "memory": memory,
        "production_checkpoint_eligible": False,
    }
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        partial = args.out.with_suffix(args.out.suffix + ".partial")
        partial.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        partial.replace(args.out)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
