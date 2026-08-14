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
    ablated_weighted = 0.0
    policy_targets = 0
    recurrent_decisions = 0
    events = 0
    event_identity_slots = 0
    linked_event_identity_slots = 0
    hidden_squared_error = 0.0
    hidden_values = 0

    model.eval()
    with torch.inference_mode():
        for group in _chunks(episodes, batch_size):
            full_sequences = [episode.decisions for episode in group]
            ablated_sequences = [
                tuple(_ablated_decision(decision) for decision in episode.decisions)
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
                ablated = recurrent_sequence_batch_loss(
                    model,
                    ablated_sequences,
                    verify=False,
                    require_policy_target=True,
                )
            if full.policy_targets != ablated.policy_targets:
                raise EventEntityAblationError("full and ablated policy-target counts differ")
            if full.recurrent_decisions != ablated.recurrent_decisions:
                raise EventEntityAblationError("full and ablated recurrent-decision counts differ")
            if full.loss is None or ablated.loss is None:
                raise EventEntityAblationError("ablation group unexpectedly has no policy loss")
            full_value = float(full.loss.float().cpu())
            ablated_value = float(ablated.loss.float().cpu())
            if not math.isfinite(full_value) or not math.isfinite(ablated_value):
                raise EventEntityAblationError("ablation NLL is nonfinite")
            policy_targets += full.policy_targets
            recurrent_decisions += full.recurrent_decisions
            full_weighted += full_value * full.policy_targets
            ablated_weighted += ablated_value * ablated.policy_targets
            hidden_delta = full.next_hidden.float() - ablated.next_hidden.float()
            hidden_squared_error += float(hidden_delta.square().sum().cpu())
            hidden_values += int(hidden_delta.numel())

    full_nll = full_weighted / policy_targets
    ablated_nll = ablated_weighted / policy_targets
    delta = ablated_nll - full_nll
    relative = delta / max(abs(full_nll), 1e-12)
    hidden_rmse = math.sqrt(hidden_squared_error / max(hidden_values, 1))
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
        "ablated_validation_nll": ablated_nll,
        "nll_delta": delta,
        "relative_nll_delta": relative,
        "terminal_hidden_rmse": hidden_rmse,
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
