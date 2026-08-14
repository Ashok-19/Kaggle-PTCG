from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np
import torch
from torch import Tensor

from gpu_cabt.device_runtime import GpuCabtRuntime
from ptcg_rl.g2.checkpoint import load_checkpoint_package
from ptcg_rl.g2.network import PTCGPolicyV1, TorchDecisionBatch
from ptcg_rl.g3.checkpoint import load_training_checkpoint_model_state, save_training_checkpoint
from ptcg_rl.g3.gpu_policy_bridge import GpuPolicyDecisionMetaV1, build_torch_policy_batch
from ptcg_rl.g3.ppo import (
    CompoundActionV1,
    compute_gae,
    is_forced_compound_action,
    ppo_loss,
    replay_compound_action,
    require_finite_gradients,
    sample_compound_action,
    verify_probability_replay,
)


class PPOSmokeError(RuntimeError):
    pass


@dataclass(frozen=True)
class RolloutStepV1:
    batch: TorchDecisionBatch
    hidden_before: Tensor
    env_indices: Tensor
    actors: Tensor
    actions: tuple[CompoundActionV1, ...]
    old_log_probabilities: Tensor
    old_values: Tensor
    old_entropies: Tensor
    policy_mask: Tensor


def _load_deck(path: Path) -> np.ndarray:
    values = np.loadtxt(path, dtype=np.int32)
    if values.shape != (60,):
        raise PPOSmokeError(f"expected exactly 60 card ids at {path}, got {values.shape}")
    return values


def _clone_model_parameters(model: PTCGPolicyV1) -> tuple[Tensor, ...]:
    return tuple(parameter.detach().clone() for parameter in model.parameters())


def _parameter_delta_l2(model: PTCGPolicyV1, before: Sequence[Tensor]) -> float:
    parameters = tuple(model.parameters())
    if len(parameters) != len(before):
        raise PPOSmokeError("model parameter count changed during PPO smoke")
    squared = 0.0
    for parameter, reference in zip(parameters, before, strict=True):
        squared += float((parameter.detach().float() - reference.float()).square().sum().item())
    value = math.sqrt(squared)
    if not math.isfinite(value):
        raise PPOSmokeError("parameter delta is nonfinite")
    return value


def _terminal_reward(game_result: int, player: int) -> float:
    if player not in (0, 1):
        raise PPOSmokeError("player must be 0 or 1")
    if game_result == 3:
        return 0.0
    if game_result == player + 1:
        return 1.0
    if game_result in (1, 2):
        return -1.0
    raise PPOSmokeError(f"unsupported GPU terminal result {game_result}")


def _sample_actions(
    model: PTCGPolicyV1,
    output: Any,
    batch: TorchDecisionBatch,
    meta: GpuPolicyDecisionMetaV1,
    *,
    generator: torch.Generator,
) -> tuple[tuple[CompoundActionV1, ...], Tensor, Tensor, Tensor]:
    actions: list[CompoundActionV1] = []
    log_probabilities: list[Tensor] = []
    entropies: list[Tensor] = []
    policy_mask: list[bool] = []
    for row in range(batch.batch_size):
        start = int(output.option_offsets[row].item())
        end = int(output.option_offsets[row + 1].item())
        option_embeddings = output.option_embeddings[start:end]
        available = batch.option_available[start:end]
        minimum = int(meta.minimum_counts[row].item())
        maximum = int(meta.maximum_counts[row].item())
        available_count = int(available.sum().item())
        action, replay = sample_compound_action(
            initial_prefix=model.decoder_initial(output.hidden[row]),
            option_embeddings=option_embeddings,
            available_mask=available,
            minimum_count=minimum,
            maximum_count=maximum,
            decoder_logits=model.decoder_logits,
            decoder_advance=model.decoder_advance,
            generator=generator,
        )
        actions.append(action)
        log_probabilities.append(replay.log_probability.detach())
        entropies.append(replay.normalized_entropy.detach())
        policy_mask.append(
            not is_forced_compound_action(available_count, minimum, maximum)
        )
    return (
        tuple(actions),
        torch.stack(log_probabilities),
        torch.stack(entropies),
        torch.tensor(policy_mask, dtype=torch.bool, device=batch.global_numeric.device),
    )


def _rollout(
    model: PTCGPolicyV1,
    runtime: GpuCabtRuntime,
    decks: np.ndarray,
    *,
    seed: int,
    max_boundaries: int,
) -> tuple[list[RolloutStepV1], Tensor, dict[str, Any]]:
    device = next(model.parameters()).device
    if device.type != "cuda":
        raise PPOSmokeError("GPU PPO smoke requires a CUDA model")
    runtime.reset(decks, seed=seed)
    runtime.synchronize()
    hidden = model.initial_hidden(runtime.env_count * 2, device).reshape(
        runtime.env_count, 2, model.config.public_hidden
    )
    generator = torch.Generator(device=device).manual_seed(seed ^ 0x5A17C0DE)
    steps: list[RolloutStepV1] = []
    decisions = 0
    meaningful = 0
    started = time.perf_counter()

    for boundary in range(max_boundaries):
        raw_status = runtime.status()
        runtime.synchronize()
        status = raw_status.torch(torch)
        errors = status.error_flags.to(torch.long)
        if torch.any(errors != 0):
            bad = torch.nonzero(errors != 0, as_tuple=False).squeeze(1).cpu().tolist()
            raise PPOSmokeError(f"GPU-CABT runtime error before boundary {boundary}: envs={bad}")
        active = status.game_results == 0
        if not torch.any(active):
            elapsed = time.perf_counter() - started
            final_results = status.game_results.to(torch.long).clone()
            return steps, final_results, {
                "boundaries": boundary,
                "rollout_seconds": elapsed,
                "recurrent_decisions": decisions,
                "meaningful_policy_targets": meaningful,
                "decisions_per_second": decisions / max(elapsed, 1e-9),
            }
        if torch.any(active & (status.select_types == 0)):
            bad = torch.nonzero(active & (status.select_types == 0), as_tuple=False).squeeze(1)
            raise PPOSmokeError(
                f"active environment has no selection boundary: {bad.cpu().tolist()}"
            )

        raw_events = runtime.project_events(acknowledge=True)
        raw_projection = runtime.project_policy()
        runtime.synchronize()
        events = raw_events.torch(torch)
        projection = raw_projection.torch(torch)
        active_indices = torch.nonzero(active, as_tuple=False).squeeze(1).to(torch.long)
        batch, meta = build_torch_policy_batch(
            projection,
            events,
            status,
            env_indices=active_indices,
        )
        hidden_before = hidden[meta.env_indices, meta.actors].detach().clone()
        with torch.inference_mode():
            output = model(batch, hidden_before)
            if not torch.isfinite(output.values).all() or not torch.isfinite(output.hidden).all():
                raise PPOSmokeError("rollout policy emitted nonfinite value or hidden state")
            actions, old_logp, entropies, policy_mask = _sample_actions(
                model,
                output,
                batch,
                meta,
                generator=generator,
            )
        hidden[meta.env_indices, meta.actors] = output.hidden.detach()
        steps.append(
            RolloutStepV1(
                batch=batch,
                hidden_before=hidden_before,
                env_indices=meta.env_indices.detach().clone(),
                actors=meta.actors.detach().clone(),
                actions=actions,
                old_log_probabilities=old_logp.detach().clone(),
                old_values=output.values.detach().clone(),
                old_entropies=entropies.detach().clone(),
                policy_mask=policy_mask.detach().clone(),
            )
        )
        decisions += batch.batch_size
        meaningful += int(policy_mask.sum().item())

        response_present = torch.zeros(runtime.env_count, dtype=torch.uint8, device=device)
        selected_counts = torch.zeros(runtime.env_count, dtype=torch.int32, device=device)
        selected_indices = torch.zeros(
            (runtime.env_count, runtime.abi.selected_capacity),
            dtype=torch.int32,
            device=device,
        )
        response_present[meta.env_indices] = 1
        for row, action in enumerate(actions):
            env = int(meta.env_indices[row].item())
            selected_counts[env] = len(action.selected_indices)
            if action.selected_indices:
                selected_indices[env, : len(action.selected_indices)] = torch.tensor(
                    action.selected_indices,
                    dtype=torch.int32,
                    device=device,
                )
        runtime.step(response_present, selected_counts, selected_indices)
        runtime.synchronize()

    raise PPOSmokeError(f"self-play did not terminate within {max_boundaries} selection boundaries")


def _flatten_rollout(
    steps: Sequence[RolloutStepV1],
) -> tuple[Tensor, Tensor, Tensor, Tensor, Tensor, Tensor]:
    if not steps:
        raise PPOSmokeError("rollout contains no decision steps")
    return (
        torch.cat([step.env_indices for step in steps]),
        torch.cat([step.actors for step in steps]),
        torch.cat([step.old_log_probabilities for step in steps]),
        torch.cat([step.old_values for step in steps]),
        torch.cat([step.old_entropies for step in steps]),
        torch.cat([step.policy_mask for step in steps]),
    )


def _advantages_and_returns(
    envs: Tensor,
    actors: Tensor,
    old_values: Tensor,
    final_results: Tensor,
    *,
    gamma: float,
    gae_lambda: float,
) -> tuple[Tensor, Tensor, dict[str, Any]]:
    advantages = torch.zeros_like(old_values)
    returns = torch.zeros_like(old_values)
    trajectory_lengths: list[int] = []
    reward_counts = {"win": 0, "loss": 0, "draw": 0}
    for env in range(final_results.numel()):
        result = int(final_results[env].item())
        for player in (0, 1):
            indices = torch.nonzero(
                (envs == env) & (actors == player), as_tuple=False
            ).squeeze(1)
            if indices.numel() == 0:
                continue
            trajectory_lengths.append(int(indices.numel()))
            reward = _terminal_reward(result, player)
            reward_counts["win" if reward > 0 else "loss" if reward < 0 else "draw"] += 1
            values = old_values.index_select(0, indices)
            rewards = torch.zeros_like(values)
            rewards[-1] = reward
            bootstrap = torch.zeros_like(values)
            if values.numel() > 1:
                bootstrap[:-1] = values[1:]
            terminals = torch.zeros(values.numel(), dtype=torch.bool, device=values.device)
            terminals[-1] = True
            truncations = torch.zeros_like(terminals)
            continues = torch.ones_like(terminals)
            continues[-1] = False
            gae = compute_gae(
                rewards=rewards,
                values=values,
                bootstrap_values=bootstrap,
                terminals=terminals,
                truncations=truncations,
                trace_continues=continues,
                gamma=gamma,
                gae_lambda=gae_lambda,
            )
            advantages.index_copy_(0, indices, gae.advantages)
            returns.index_copy_(0, indices, gae.returns)
    if not trajectory_lengths:
        raise PPOSmokeError("rollout produced no player trajectories")
    return advantages, returns, {
        "trajectory_count": len(trajectory_lengths),
        "trajectory_length_min": min(trajectory_lengths),
        "trajectory_length_max": max(trajectory_lengths),
        "trajectory_length_mean": sum(trajectory_lengths) / len(trajectory_lengths),
        "terminal_reward_counts": reward_counts,
        "advantage_mean": float(advantages.mean().item()),
        "advantage_std": float(advantages.std(unbiased=False).item()),
        "return_mean": float(returns.mean().item()),
        "return_std": float(returns.std(unbiased=False).item()),
    }


def _replay_rollout(
    model: PTCGPolicyV1,
    steps: Sequence[RolloutStepV1],
    *,
    gradient: bool,
) -> tuple[Tensor, Tensor, Tensor]:
    log_probabilities: list[Tensor] = []
    values: list[Tensor] = []
    entropies: list[Tensor] = []
    context = torch.enable_grad() if gradient else torch.inference_mode()
    with context:
        for step in steps:
            output = model(step.batch, step.hidden_before)
            values.append(output.values)
            for row, action in enumerate(step.actions):
                start = int(output.option_offsets[row].item())
                end = int(output.option_offsets[row + 1].item())
                replay = replay_compound_action(
                    initial_prefix=model.decoder_initial(output.hidden[row]),
                    option_embeddings=output.option_embeddings[start:end],
                    available_mask=step.batch.option_available[start:end],
                    action=action,
                    minimum_count=int(step.batch.global_numeric[row, 2].item()),
                    maximum_count=int(step.batch.global_numeric[row, 3].item()),
                    decoder_logits=model.decoder_logits,
                    decoder_advance=model.decoder_advance,
                )
                log_probabilities.append(replay.log_probability)
                entropies.append(replay.normalized_entropy)
    return torch.stack(log_probabilities), torch.cat(values), torch.stack(entropies)


def run(args: argparse.Namespace) -> dict[str, Any]:
    device = torch.device(args.device)
    if device.type != "cuda" or not torch.cuda.is_available():
        raise PPOSmokeError("PPO GPU smoke requires CUDA")
    torch.manual_seed(args.seed)
    torch.cuda.manual_seed_all(args.seed)
    np.random.seed(args.seed & 0xFFFFFFFF)

    loaded = load_checkpoint_package(args.checkpoint_package, device=device)
    model = loaded.model
    bc = load_training_checkpoint_model_state(
        args.bc_checkpoint,
        model=model,
        expected_sha256=args.bc_checkpoint_sha256,
    )
    # PPO probability replay must be deterministic. The current network uses
    # zero dropout, but keep evaluation mode as an explicit rollout/replay contract;
    # autograd remains enabled during the optimizer replay below.
    model.eval()
    deck = _load_deck(args.deck)
    decks = np.broadcast_to(deck, (args.env_count, 2, 60)).copy()
    runtime = GpuCabtRuntime(args.env_count, stack_size_bytes=args.stack_bytes)

    parameters_before = _clone_model_parameters(model)
    rollout_steps, final_results, rollout_metrics = _rollout(
        model,
        runtime,
        decks,
        seed=args.seed,
        max_boundaries=args.max_boundaries,
    )
    envs, actors, old_logp, old_values, old_entropies, policy_mask = _flatten_rollout(
        rollout_steps
    )
    if not torch.any(policy_mask):
        raise PPOSmokeError("rollout contains no meaningful learner-controlled choices")
    advantages, returns, gae_metrics = _advantages_and_returns(
        envs,
        actors,
        old_values,
        final_results,
        gamma=args.gamma,
        gae_lambda=args.gae_lambda,
    )

    replay_logp, replay_values, replay_entropies = _replay_rollout(
        model, rollout_steps, gradient=False
    )
    replay_check = verify_probability_replay(
        old_logp,
        replay_logp,
        maximum_absolute_error=args.replay_tolerance,
        maximum_ratio_error=args.replay_tolerance,
    )
    value_replay_error = float(torch.max(torch.abs(replay_values - old_values)).item())
    if value_replay_error > args.replay_tolerance:
        raise PPOSmokeError(
            f"old value predictions do not replay: max_abs_error={value_replay_error}"
        )

    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=0.0)
    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda=lambda _: 1.0)
    optimizer.zero_grad(set_to_none=True)
    train_logp, train_values, train_entropies = _replay_rollout(
        model, rollout_steps, gradient=True
    )
    loss = ppo_loss(
        new_log_probabilities=train_logp,
        old_log_probabilities=old_logp,
        advantages=advantages,
        new_values=train_values,
        old_values=old_values,
        returns=returns,
        normalized_entropies=train_entropies,
        policy_mask=policy_mask,
        clip_coefficient=args.clip_coefficient,
        value_clip_coefficient=args.value_clip_coefficient,
        value_coefficient=args.value_coefficient,
        entropy_coefficient=args.entropy_coefficient,
        normalize_advantages=True,
    )
    loss.total.backward()
    gradient_norm = require_finite_gradients(tuple(model.parameters()))
    clipped_gradient_norm = float(
        torch.nn.utils.clip_grad_norm_(model.parameters(), args.max_gradient_norm).item()
    )
    optimizer.step()
    scheduler.step()
    parameter_delta = _parameter_delta_l2(model, parameters_before)
    if parameter_delta <= 0:
        raise PPOSmokeError("PPO optimizer step did not change model parameters")

    post_logp, post_values, post_entropies = _replay_rollout(
        model, rollout_steps, gradient=False
    )
    post_loss = ppo_loss(
        new_log_probabilities=post_logp,
        old_log_probabilities=old_logp,
        advantages=advantages,
        new_values=post_values,
        old_values=old_values,
        returns=returns,
        normalized_entropies=post_entropies,
        policy_mask=policy_mask,
        clip_coefficient=args.clip_coefficient,
        value_clip_coefficient=args.value_clip_coefficient,
        value_coefficient=args.value_coefficient,
        entropy_coefficient=args.entropy_coefficient,
        normalize_advantages=True,
    )

    # A second complete rollout is a strict post-update legality/runtime gate.
    post_steps, post_results, post_rollout_metrics = _rollout(
        model,
        runtime,
        decks,
        seed=args.seed + 1,
        max_boundaries=args.max_boundaries,
    )
    _, _, _, post_old_values, _, post_policy_mask = _flatten_rollout(post_steps)
    if not torch.isfinite(post_old_values).all() or not torch.any(post_policy_mask):
        raise PPOSmokeError("post-update rollout is numerically or behaviorally invalid")

    terminal_counts = {
        str(value): int((final_results == value).sum().item()) for value in (1, 2, 3)
    }
    post_terminal_counts = {
        str(value): int((post_results == value).sum().item()) for value in (1, 2, 3)
    }
    report: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "kptcg-bc-init-selfplay-ppo-smoke-v1",
        "status": "PASS",
        "device": str(device),
        "gpu_name": torch.cuda.get_device_name(device),
        "model_package_sha256": loaded.package_sha256,
        "bc_initializer_sha256": bc.payload_sha256,
        "model_parameters": model.trainable_parameter_count,
        "env_count": args.env_count,
        "seed": args.seed,
        "hyperparameters": {
            "gamma": args.gamma,
            "gae_lambda": args.gae_lambda,
            "clip_coefficient": args.clip_coefficient,
            "value_clip_coefficient": args.value_clip_coefficient,
            "value_coefficient": args.value_coefficient,
            "entropy_coefficient": args.entropy_coefficient,
            "learning_rate": args.learning_rate,
            "max_gradient_norm": args.max_gradient_norm,
            "ppo_epochs": 1,
            "reward": "terminal-only +/-1, draw 0",
        },
        "rollout": {
            **rollout_metrics,
            "terminal_counts": terminal_counts,
            "runtime_memory_bytes": runtime.memory_bytes(),
            "old_value_mean": float(old_values.mean().item()),
            "old_value_std": float(old_values.std(unbiased=False).item()),
            "old_value_min": float(old_values.min().item()),
            "old_value_max": float(old_values.max().item()),
            "old_entropy_mean": float(old_entropies[policy_mask].mean().item()),
        },
        "gae": gae_metrics,
        "probability_replay": {
            "checked_actions": replay_check.checked_actions,
            "max_log_probability_absolute_error": replay_check.maximum_log_probability_absolute_error,
            "max_ratio_absolute_error_from_one": replay_check.maximum_ratio_absolute_error_from_one,
            "max_value_absolute_error": value_replay_error,
        },
        "update": {
            "pre_total_loss": float(loss.total.detach().item()),
            "pre_policy_loss": float(loss.policy.detach().item()),
            "pre_value_loss": float(loss.value.detach().item()),
            "pre_entropy": float(loss.entropy.detach().item()),
            "pre_approximate_kl": float(loss.approximate_kl.detach().item()),
            "pre_clip_fraction": float(loss.clip_fraction.detach().item()),
            "gradient_norm": gradient_norm,
            "clip_grad_norm_return": clipped_gradient_norm,
            "parameter_delta_l2": parameter_delta,
            "post_total_loss": float(post_loss.total.detach().item()),
            "post_policy_loss": float(post_loss.policy.detach().item()),
            "post_value_loss": float(post_loss.value.detach().item()),
            "post_entropy": float(post_loss.entropy.detach().item()),
            "post_approximate_kl": float(post_loss.approximate_kl.detach().item()),
            "post_clip_fraction": float(post_loss.clip_fraction.detach().item()),
        },
        "post_update_rollout": {
            **post_rollout_metrics,
            "terminal_counts": post_terminal_counts,
            "meaningful_policy_targets": int(post_policy_mask.sum().item()),
        },
        "full_run_authorized": False,
    }

    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_path = args.output_dir / "ppo-smoke-after.pt"
        checkpoint = save_training_checkpoint(
            checkpoint_path,
            model=model,
            optimizer=optimizer,
            scheduler=scheduler,
            scaler=None,
            counters={
                "ppo_smoke_updates": 1,
                "rollout_decisions": int(old_logp.numel()),
                "meaningful_policy_targets": int(policy_mask.sum().item()),
            },
            league={
                "initializer": "bc-specialist-epoch-1",
                "initializer_sha256": bc.payload_sha256,
                "opponent_mode": "frozen-symmetric-smoke",
                "full_run_authorized": False,
            },
            rollout_boundary={
                "complete_games": args.env_count,
                "terminal_counts": terminal_counts,
                "seed": args.seed,
            },
            include_cuda_rng=True,
        )
        report["checkpoint"] = {
            "path": checkpoint_path.name,
            "payload_sha256": checkpoint["payload_sha256"],
            "payload_bytes": checkpoint["payload_bytes"],
        }
        report_path = args.output_dir / "ppo-smoke-report.json"
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint-package", type=Path, required=True)
    parser.add_argument("--bc-checkpoint", type=Path, required=True)
    parser.add_argument("--bc-checkpoint-sha256", required=True)
    parser.add_argument("--deck", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--env-count", type=int, default=16)
    parser.add_argument("--seed", type=int, default=20260814)
    parser.add_argument("--max-boundaries", type=int, default=3000)
    parser.add_argument("--stack-bytes", type=int, default=16 * 1024)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--gamma", type=float, default=0.999)
    parser.add_argument("--gae-lambda", type=float, default=0.95)
    parser.add_argument("--clip-coefficient", type=float, default=0.2)
    parser.add_argument("--value-clip-coefficient", type=float, default=0.2)
    parser.add_argument("--value-coefficient", type=float, default=0.5)
    parser.add_argument("--entropy-coefficient", type=float, default=0.01)
    parser.add_argument("--learning-rate", type=float, default=3e-5)
    parser.add_argument("--max-gradient-norm", type=float, default=1.0)
    parser.add_argument("--replay-tolerance", type=float, default=1e-5)
    args = parser.parse_args()
    if args.env_count <= 0 or args.max_boundaries <= 0:
        parser.error("env-count and max-boundaries must be positive")
    report = run(args)
    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
