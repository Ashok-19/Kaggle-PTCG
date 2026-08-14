from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Sequence

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ptcg_rl.bc.materialized import (  # noqa: E402
    MaterializedDecisionV1,
    MaterializedEpisodeV1,
    load_materialized_episode,
)
from ptcg_rl.bc.training import recurrent_sequence_batch_loss  # noqa: E402
from ptcg_rl.g2.checkpoint import load_checkpoint_package  # noqa: E402
from ptcg_rl.g3.checkpoint import load_training_checkpoint_model_state  # noqa: E402


class EventEntityAblationError(ValueError):
    """Raised when the event/entity bridge ablation violates its evidence contract."""


def _ablated_decision(decision: MaterializedDecisionV1) -> MaterializedDecisionV1:
    model = decision.projected.model
    event_entity_indices = tuple(tuple(-1 for _ in row) for row in model.event_entity_indices)
    projected = replace(
        decision.projected,
        model=replace(model, event_entity_indices=event_entity_indices),
    )
    return replace(decision, projected=projected)


def _gpu_feasible_decision(decision: MaterializedDecisionV1) -> MaterializedDecisionV1:
    """Keep event identity equality but remove current-entity anchoring unavailable on GPU."""
    linked = _ablated_decision(decision)
    model = linked.projected.model
    identity_map: dict[int, int] = {}
    next_identity = 1
    rows: list[tuple[int, ...]] = []
    for values, missing in zip(model.event_identity_values, model.event_identity_missing, strict=True):
        row: list[int] = []
        for value, is_missing in zip(values, missing, strict=True):
            if is_missing:
                row.append(0)
                continue
            identity_value = int(value)
            if identity_value not in identity_map:
                identity_map[identity_value] = next_identity
                next_identity += 1
            row.append(identity_map[identity_value])
        rows.append(tuple(row))
    projected = replace(
        linked.projected,
        model=replace(model, event_identity_values=tuple(rows)),
    )
    return replace(linked, projected=projected)


def _load_split(
    root: Path,
    *,
    split: str,
    limit: int | None,
) -> tuple[list[MaterializedEpisodeV1], dict[str, Any]]:
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = [row for row in manifest["records"] if row["split"] == split]
    records.sort(key=lambda row: int(row["episode_id"]))
    if limit is not None:
        records = records[:limit]
    if not records:
        raise EventEntityAblationError(f"materialized split {split!r} is empty")
    episodes = [
        load_materialized_episode(root / row["path"], expected_sha256=row["sha256"])
        for row in records
    ]
    return episodes, manifest


def _chunks(values: Sequence[Any], size: int) -> list[Sequence[Any]]:
    return [values[start : start + size] for start in range(0, len(values), size)]


def _evaluate(
    model: Any,
    episodes: Sequence[MaterializedEpisodeV1],
    *,
    batch_size: int,
    bf16: bool,
) -> dict[str, Any]:
    device = next(model.parameters()).device
    full_weighted = 0.0
    link_only_weighted = 0.0
    gpu_feasible_weighted = 0.0
    policy_targets = 0
    recurrent_decisions = 0
    events = 0
    event_identity_slots = 0
    linked_event_identity_slots = 0
    link_only_hidden_squared_error = 0.0
    gpu_feasible_hidden_squared_error = 0.0
    hidden_values = 0

    model.eval()
    with torch.inference_mode():
        for group in _chunks(episodes, batch_size):
            full_sequences = [episode.decisions for episode in group]
            link_only_sequences = [
                tuple(_ablated_decision(decision) for decision in episode.decisions)
                for episode in group
            ]
            gpu_feasible_sequences = [
                tuple(_gpu_feasible_decision(decision) for decision in episode.decisions)
                for episode in group
            ]
            for episode in group:
                for decision in episode.decisions:
                    rows = decision.projected.model.event_entity_indices
                    events += len(rows)
                    event_identity_slots += sum(len(row) for row in rows)
                    linked_event_identity_slots += sum(
                        int(value >= 0) for row in rows for value in row
                    )
            autocast = torch.autocast(
                device_type=device.type,
                dtype=torch.bfloat16,
                enabled=bf16 and device.type == "cuda",
            )
            with autocast:
                full = recurrent_sequence_batch_loss(
                    model,
                    full_sequences,
                    verify=False,
                    require_policy_target=True,
                )
                link_only = recurrent_sequence_batch_loss(
                    model,
                    link_only_sequences,
                    verify=False,
                    require_policy_target=True,
                )
                gpu_feasible = recurrent_sequence_batch_loss(
                    model,
                    gpu_feasible_sequences,
                    verify=False,
                    require_policy_target=True,
                )
            variants = (link_only, gpu_feasible)
            if any(result.policy_targets != full.policy_targets for result in variants):
                raise EventEntityAblationError("full and sensitivity policy-target counts differ")
            if any(result.recurrent_decisions != full.recurrent_decisions for result in variants):
                raise EventEntityAblationError("full and sensitivity recurrent-decision counts differ")
            if full.loss is None or any(result.loss is None for result in variants):
                raise EventEntityAblationError("sensitivity group unexpectedly has no policy loss")
            full_value = float(full.loss.float().cpu())
            link_only_value = float(link_only.loss.float().cpu())
            gpu_feasible_value = float(gpu_feasible.loss.float().cpu())
            values = (full_value, link_only_value, gpu_feasible_value)
            if not all(math.isfinite(value) for value in values):
                raise EventEntityAblationError("sensitivity NLL is nonfinite")
            policy_targets += full.policy_targets
            recurrent_decisions += full.recurrent_decisions
            full_weighted += full_value * full.policy_targets
            link_only_weighted += link_only_value * link_only.policy_targets
            gpu_feasible_weighted += gpu_feasible_value * gpu_feasible.policy_targets
            link_delta = full.next_hidden.float() - link_only.next_hidden.float()
            gpu_delta = full.next_hidden.float() - gpu_feasible.next_hidden.float()
            link_only_hidden_squared_error += float(link_delta.square().sum().cpu())
            gpu_feasible_hidden_squared_error += float(gpu_delta.square().sum().cpu())
            hidden_values += int(link_delta.numel())

    full_nll = full_weighted / policy_targets
    link_only_nll = link_only_weighted / policy_targets
    gpu_feasible_nll = gpu_feasible_weighted / policy_targets
    link_only_delta = link_only_nll - full_nll
    gpu_feasible_delta = gpu_feasible_nll - full_nll
    link_only_relative = link_only_delta / max(abs(full_nll), 1e-12)
    gpu_feasible_relative = gpu_feasible_delta / max(abs(full_nll), 1e-12)
    link_only_hidden_rmse = math.sqrt(link_only_hidden_squared_error / max(hidden_values, 1))
    gpu_feasible_hidden_rmse = math.sqrt(
        gpu_feasible_hidden_squared_error / max(hidden_values, 1)
    )
    return {
        "episodes": len(episodes),
        "policy_targets": policy_targets,
        "recurrent_decisions": recurrent_decisions,
        "public_events": events,
        "event_identity_slots": event_identity_slots,
        "linked_event_identity_slots": linked_event_identity_slots,
        "linked_event_identity_fraction": (
            linked_event_identity_slots / event_identity_slots if event_identity_slots else 0.0
        ),
        "full_validation_nll": full_nll,
        "link_only_validation_nll": link_only_nll,
        "link_only_nll_delta": link_only_delta,
        "link_only_relative_nll_delta": link_only_relative,
        "link_only_terminal_hidden_rmse": link_only_hidden_rmse,
        "gpu_feasible_validation_nll": gpu_feasible_nll,
        "gpu_feasible_nll_delta": gpu_feasible_delta,
        "gpu_feasible_relative_nll_delta": gpu_feasible_relative,
        "gpu_feasible_terminal_hidden_rmse": gpu_feasible_hidden_rmse,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--materialized-dir", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--training-checkpoint", type=Path, required=True)
    parser.add_argument("--training-checkpoint-sha256", required=True)
    parser.add_argument("--split", default="validation", choices=("train", "validation"))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--bf16", action="store_true")
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    if args.batch_size <= 0:
        parser.error("--batch-size must be positive")

    device = torch.device(args.device)
    episodes, manifest = _load_split(args.materialized_dir, split=args.split, limit=args.limit)
    loaded = load_checkpoint_package(args.checkpoint, device=device)
    model = loaded.model
    restored = load_training_checkpoint_model_state(
        args.training_checkpoint,
        model=model,
        expected_sha256=args.training_checkpoint_sha256,
    )
    metrics = _evaluate(model, episodes, batch_size=args.batch_size, bf16=args.bf16)
    result = {
        "schema_version": 1,
        "record_id": "bc-event-entity-link-ablation-v1",
        "status": "PASS_ABLATION_COMPLETED",
        "materialized_manifest_sha256": manifest["manifest_sha256"],
        "materialized_record_id": manifest["record_id"],
        "split": args.split,
        "model_package_sha256": loaded.package_sha256,
        "training_checkpoint_sha256": restored.payload_sha256,
        "device": str(device),
        "bf16": bool(args.bf16),
        "batch_size_episodes": args.batch_size,
        "ablation": "replace every event_entity_indices entry with -1 while preserving public event card/type/value/identity features and recurrent ordering",
        "metrics": metrics,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
