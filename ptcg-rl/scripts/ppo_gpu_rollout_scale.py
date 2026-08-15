from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import torch

from gpu_cabt.device_runtime import GpuCabtRuntime
from ptcg_rl.g2.capacity import model_config, model_configs
from ptcg_rl.g2.card_table import load_card_table
from ptcg_rl.g2.network import PTCGPolicyV1
from ptcg_rl.g3.checkpoint import load_training_checkpoint_model_state
from ptcg_rl.g3.compound_batch import sample_compound_actions_batched
from ptcg_rl.g3.gpu_policy_bridge import build_torch_policy_batch


class RolloutScaleError(RuntimeError):
    pass


def _load_deck(path: Path) -> np.ndarray:
    values = np.loadtxt(path, dtype=np.int32)
    if values.shape != (60,):
        raise RolloutScaleError(f"expected 60 card ids at {path}, got {values.shape}")
    return values


def run(args: argparse.Namespace) -> dict[str, Any]:
    device = torch.device(args.device)
    if device.type != "cuda" or not torch.cuda.is_available():
        raise RolloutScaleError("rollout scaling probe requires CUDA")
    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)
    np.random.seed(args.seed & 0xFFFFFFFF)

    card_table = load_card_table(args.card_table)
    model = PTCGPolicyV1(card_table, model_config(args.model_label)).to(device)
    restored = load_training_checkpoint_model_state(
        args.bc_checkpoint,
        model=model,
        expected_sha256=args.bc_checkpoint_sha256,
    )
    model.eval()
    deck = _load_deck(args.deck)
    decks = np.broadcast_to(deck, (args.env_count, 2, 60)).copy()

    init_started = time.perf_counter()
    runtime = GpuCabtRuntime(args.env_count, stack_size_bytes=args.stack_bytes)
    runtime.reset(decks, seed=args.seed)
    runtime.synchronize()
    init_seconds = time.perf_counter() - init_started

    hidden = model.initial_hidden(args.env_count * 2, device).reshape(
        args.env_count, 2, model.config.public_hidden
    )
    generator = torch.Generator(device=device).manual_seed(args.seed ^ 0x1A2B3C4D)
    response_present = torch.zeros(args.env_count, dtype=torch.uint8, device=device)
    selected_counts = torch.zeros(args.env_count, dtype=torch.int32, device=device)
    selected_indices = torch.zeros(
        (args.env_count, runtime.abi.selected_capacity), dtype=torch.int32, device=device
    )

    recurrent_decisions = 0
    meaningful_boundaries = 0
    active_counts: list[int] = []
    model_seconds = 0.0
    bridge_seconds = 0.0
    projection_seconds = 0.0
    step_seconds = 0.0
    warmup = min(args.warmup_boundaries, args.boundaries)
    measured_started: float | None = None
    measured_decisions = 0
    measured_boundaries = 0

    for boundary in range(args.boundaries):
        raw_status = runtime.status()
        runtime.synchronize()
        status = raw_status.torch(torch)
        errors = status.error_flags.to(torch.long)
        if torch.any(errors != 0):
            bad = torch.nonzero(errors != 0, as_tuple=False).squeeze(1).cpu().tolist()[:16]
            raise RolloutScaleError(f"runtime errors at boundary {boundary}: {bad}")
        active = status.game_results == 0
        active_indices = torch.nonzero(active, as_tuple=False).squeeze(1).to(torch.long)
        active_count = int(active_indices.numel())
        active_counts.append(active_count)
        if active_count == 0:
            break
        if torch.any(active & (status.select_types == 0)):
            bad = torch.nonzero(active & (status.select_types == 0), as_tuple=False).squeeze(1)
            raise RolloutScaleError(
                f"active environment has no selection boundary: {bad[:16].cpu().tolist()}"
            )
        if boundary == warmup:
            runtime.synchronize()
            measured_started = time.perf_counter()

        projection_started = time.perf_counter()
        raw_events = runtime.project_events(acknowledge=True)
        raw_projection = runtime.project_policy()
        runtime.synchronize()
        projection_seconds += time.perf_counter() - projection_started
        events = raw_events.torch(torch)
        projection = raw_projection.torch(torch)

        bridge_started = time.perf_counter()
        batch, meta = build_torch_policy_batch(
            projection, events, status, env_indices=active_indices
        )
        bridge_seconds += time.perf_counter() - bridge_started
        hidden_before = hidden[meta.env_indices, meta.actors]

        model_started = time.perf_counter()
        autocast = torch.autocast(
            device_type="cuda", dtype=torch.bfloat16, enabled=args.bf16
        )
        with torch.inference_mode(), autocast:
            output = model(batch, hidden_before)
            actions = sample_compound_actions_batched(
                model,
                public_hidden=output.hidden,
                primary_option_logits=output.option_logits,
                option_embeddings=output.option_embeddings,
                option_offsets=output.option_offsets,
                available_mask=batch.option_available,
                minimum_counts=meta.minimum_counts,
                maximum_counts=meta.maximum_counts,
                generator=generator,
            )
        runtime.synchronize()
        model_seconds += time.perf_counter() - model_started
        if not torch.isfinite(output.values).all() or not torch.isfinite(actions.log_probabilities).all():
            raise RolloutScaleError("policy emitted nonfinite outputs")
        hidden[meta.env_indices, meta.actors] = output.hidden.to(hidden.dtype)

        response_present.zero_()
        selected_counts.zero_()
        selected_indices.zero_()
        response_present[meta.env_indices] = 1
        selected_counts[meta.env_indices] = actions.selected_lengths.to(torch.int32)
        action_width = actions.selected_indices.shape[1]
        if action_width:
            selected_indices[meta.env_indices, :action_width] = torch.where(
                actions.selected_indices >= 0,
                actions.selected_indices,
                torch.zeros_like(actions.selected_indices),
            ).to(torch.int32)

        step_started = time.perf_counter()
        runtime.step(response_present, selected_counts, selected_indices)
        runtime.synchronize()
        step_seconds += time.perf_counter() - step_started

        recurrent_decisions += active_count
        meaningful_boundaries += 1
        if boundary >= warmup:
            measured_decisions += active_count
            measured_boundaries += 1

    runtime.synchronize()
    measured_seconds = (
        time.perf_counter() - measured_started if measured_started is not None else 0.0
    )
    final_status = runtime.status()
    runtime.synchronize()
    final_status_torch = final_status.torch(torch)
    final_errors = final_status_torch.error_flags.to(torch.long)
    if torch.any(final_errors != 0):
        raise RolloutScaleError("runtime error appeared after final benchmark boundary")
    terminal_count = int((final_status_torch.game_results != 0).sum().item())

    return {
        "schema_version": 1,
        "record_id": "kptcg-neural-rollout-scale-v1",
        "status": "PASS",
        "env_count": args.env_count,
        "requested_boundaries": args.boundaries,
        "completed_boundaries": meaningful_boundaries,
        "warmup_boundaries": warmup,
        "measured_boundaries": measured_boundaries,
        "recurrent_decisions_total": recurrent_decisions,
        "measured_decisions": measured_decisions,
        "measured_seconds": measured_seconds,
        "measured_decisions_per_second": (
            measured_decisions / measured_seconds if measured_seconds > 0 else 0.0
        ),
        "active_count_first": active_counts[0] if active_counts else 0,
        "active_count_last": active_counts[-1] if active_counts else 0,
        "active_count_min": min(active_counts) if active_counts else 0,
        "terminal_envs_at_end": terminal_count,
        "bf16": bool(args.bf16),
        "gpu_name": torch.cuda.get_device_name(device),
        "model_parameters": model.trainable_parameter_count,
        "model_label": args.model_label,
        "card_table_sha256": model.card_table_sha256,
        "bc_initializer_sha256": restored.payload_sha256,
        "runtime_memory_bytes": runtime.memory_bytes(),
        "torch_peak_allocated_bytes": int(torch.cuda.max_memory_allocated(device)),
        "init_seconds": init_seconds,
        "timing_accumulators_seconds": {
            "projection": projection_seconds,
            "bridge": bridge_seconds,
            "model_and_compound": model_seconds,
            "engine_step": step_seconds,
        },
        "full_run_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--card-table", type=Path, required=True)
    parser.add_argument("--model-label", default="3.7m", choices=tuple(model_configs()))
    parser.add_argument("--bc-checkpoint", type=Path, required=True)
    parser.add_argument("--bc-checkpoint-sha256")
    parser.add_argument("--deck", type=Path, required=True)
    parser.add_argument("--env-count", type=int, required=True)
    parser.add_argument("--boundaries", type=int, default=64)
    parser.add_argument("--warmup-boundaries", type=int, default=8)
    parser.add_argument("--seed", type=int, default=20260814)
    parser.add_argument("--stack-bytes", type=int, default=16 * 1024)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--bf16", action="store_true")
    args = parser.parse_args()
    if args.env_count <= 0 or args.boundaries <= 0 or args.warmup_boundaries < 0:
        parser.error("env-count/boundaries must be positive and warmup nonnegative")
    if args.warmup_boundaries >= args.boundaries:
        parser.error("warmup-boundaries must be smaller than boundaries")
    result = run(args)
    print(json.dumps(result, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
