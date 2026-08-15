from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Callable, Sequence

import torch
from torch import Tensor


class PPOContractError(ValueError):
    """Raised when PPO evidence or a rollout violates the frozen correctness contract."""


@dataclass(frozen=True)
class LocalExecutionLimitsV1:
    max_cpu_threads: int = 2
    max_worker_processes: int = 1
    max_non_forced_choices: int = 4096
    max_wall_seconds: int = 300
    allow_cuda: bool = False

    def __post_init__(self) -> None:
        for name, value in self.__dict__.items():
            if name == "allow_cuda":
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise PPOContractError(f"{name} must be a positive integer")
        if self.max_cpu_threads > 2:
            raise PPOContractError("local CPU thread ceiling is two")
        if self.max_worker_processes > 1:
            raise PPOContractError("local worker-process ceiling is one")


def apply_local_execution_limits(limits: LocalExecutionLimitsV1 | None = None) -> dict[str, int]:
    limits = limits or LocalExecutionLimitsV1()
    thread_value = str(limits.max_cpu_threads)
    for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        os.environ[name] = thread_value
    torch.set_num_threads(limits.max_cpu_threads)
    try:
        torch.set_num_interop_threads(1)
    except RuntimeError:
        if torch.get_num_interop_threads() != 1:
            raise PPOContractError("PyTorch interop threads were initialized above one")
    return {
        "torch_threads": torch.get_num_threads(),
        "torch_interop_threads": torch.get_num_interop_threads(),
    }


def validate_local_workload(
    *,
    non_forced_choices: int,
    worker_processes: int,
    device: str | torch.device,
    limits: LocalExecutionLimitsV1 | None = None,
) -> None:
    limits = limits or LocalExecutionLimitsV1()
    if isinstance(non_forced_choices, bool) or not isinstance(non_forced_choices, int):
        raise PPOContractError("non-forced choice count must be an integer")
    if non_forced_choices < 0 or non_forced_choices > limits.max_non_forced_choices:
        raise PPOContractError("local non-forced choice budget exceeds the safety envelope")
    if isinstance(worker_processes, bool) or not isinstance(worker_processes, int):
        raise PPOContractError("worker process count must be an integer")
    if worker_processes < 0 or worker_processes > limits.max_worker_processes:
        raise PPOContractError("local worker process count exceeds the safety envelope")
    resolved = torch.device(device)
    if resolved.type != "cpu" and not limits.allow_cuda:
        raise PPOContractError("local correctness runs are CPU-only")


@dataclass(frozen=True)
class CompoundActionV1:
    selected_indices: tuple[int, ...]
    stopped: bool = True

    def __post_init__(self) -> None:
        if any(isinstance(index, bool) or not isinstance(index, int) for index in self.selected_indices):
            raise PPOContractError("compound action indices must be integers")
        if len(set(self.selected_indices)) != len(self.selected_indices):
            raise PPOContractError("compound action indices must be unique")
        if not isinstance(self.stopped, bool):
            raise PPOContractError("compound action stopped flag must be boolean")


@dataclass(frozen=True)
class CompoundReplayV1:
    log_probability: Tensor
    normalized_entropy: Tensor
    subchoice_log_probabilities: tuple[Tensor, ...]
    subchoice_entropies: tuple[Tensor, ...]
    selected_indices: tuple[int, ...]
    stopped: bool


DecoderLogits = Callable[[Tensor, Tensor, Tensor, bool], Tensor]
DecoderAdvance = Callable[[Tensor, Tensor], Tensor]


def _require_vector(value: Tensor, name: str) -> Tensor:
    if not isinstance(value, Tensor) or value.ndim != 1:
        raise PPOContractError(f"{name} must be a one-dimensional tensor")
    return value


def _masked_log_probability_and_entropy(
    logits: Tensor,
    mask: Tensor,
    action_index: int,
) -> tuple[Tensor, Tensor]:
    logits = _require_vector(logits, "logits")
    mask = _require_vector(mask, "mask")
    if mask.dtype != torch.bool or mask.shape != logits.shape:
        raise PPOContractError("mask must be boolean and match logits")
    if not torch.any(mask):
        raise PPOContractError("masked distribution has no legal outcome")
    if torch.isnan(logits).any() or torch.isposinf(logits).any():
        raise PPOContractError("distribution logits contain NaN or positive infinity")
    if not torch.isfinite(logits[mask]).all():
        raise PPOContractError("legal distribution logits must be finite")
    if isinstance(action_index, bool) or not isinstance(action_index, int):
        raise PPOContractError("action index must be an integer")
    if action_index < 0 or action_index >= logits.numel() or not bool(mask[action_index]):
        raise PPOContractError("selected action is outside the legal mask")
    masked = logits.masked_fill(~mask, float("-inf"))
    log_probabilities = torch.log_softmax(masked, dim=0)
    probabilities = torch.exp(log_probabilities[mask])
    entropy = -(probabilities * log_probabilities[mask]).sum()
    if not torch.isfinite(log_probabilities[action_index]) or not torch.isfinite(entropy):
        raise PPOContractError("masked distribution produced a nonfinite result")
    return log_probabilities[action_index], entropy


def _normalized_entropy(entropy: Tensor, legal_count: int) -> Tensor:
    if legal_count <= 1:
        return entropy.new_zeros(())
    return entropy / math.log(legal_count)


def sample_compound_action(
    *,
    initial_prefix: Tensor,
    option_embeddings: Tensor,
    available_mask: Tensor,
    minimum_count: int,
    maximum_count: int,
    decoder_logits: DecoderLogits,
    decoder_advance: DecoderAdvance,
    generator: torch.Generator | None = None,
) -> tuple[CompoundActionV1, CompoundReplayV1]:
    """Sample one legal autoregressive compound action and retain its exact PPO statistics."""
    if initial_prefix.ndim != 1:
        raise PPOContractError("decoder prefix must be one-dimensional")
    if option_embeddings.ndim != 2:
        raise PPOContractError("option embeddings must be two-dimensional")
    if available_mask.dtype != torch.bool or available_mask.shape != (option_embeddings.shape[0],):
        raise PPOContractError("available mask must match option embeddings")
    if isinstance(minimum_count, bool) or isinstance(maximum_count, bool):
        raise PPOContractError("selection bounds must be integers")
    if not isinstance(minimum_count, int) or not isinstance(maximum_count, int):
        raise PPOContractError("selection bounds must be integers")
    if minimum_count < 0 or maximum_count < minimum_count:
        raise PPOContractError("selection bounds are invalid")

    available = available_mask.clone()
    effective_maximum = min(maximum_count, int(available.sum().item()))
    if minimum_count > effective_maximum:
        raise PPOContractError("minimum selection count exceeds available options")

    prefix = initial_prefix
    selected: list[int] = []
    subchoice_log_probabilities: list[Tensor] = []
    subchoice_entropies: list[Tensor] = []
    stopped = False

    while len(selected) < effective_maximum:
        stop_available = len(selected) >= minimum_count
        logits = decoder_logits(prefix, option_embeddings, available, stop_available)
        if logits.shape != (option_embeddings.shape[0] + 1,):
            raise PPOContractError("decoder logits shape differs from option count plus STOP")
        distribution_mask = torch.cat(
            (available, torch.tensor([stop_available], dtype=torch.bool, device=available.device))
        )
        if not torch.any(distribution_mask):
            raise PPOContractError("compound sampler has no legal outcome")
        if torch.isnan(logits).any() or torch.isposinf(logits).any():
            raise PPOContractError("distribution logits contain NaN or positive infinity")
        if not torch.isfinite(logits[distribution_mask]).all():
            raise PPOContractError("legal distribution logits must be finite")
        masked = logits.masked_fill(~distribution_mask, float("-inf"))
        probabilities = torch.softmax(masked, dim=0)
        choice = int(torch.multinomial(probabilities, 1, generator=generator).item())
        log_probability, entropy = _masked_log_probability_and_entropy(
            logits, distribution_mask, choice
        )
        subchoice_log_probabilities.append(log_probability)
        subchoice_entropies.append(_normalized_entropy(entropy, int(distribution_mask.sum())))
        if choice == option_embeddings.shape[0]:
            stopped = True
            break
        selected.append(choice)
        prefix = decoder_advance(prefix, option_embeddings[choice])
        if prefix.ndim != 1 or not torch.isfinite(prefix).all():
            raise PPOContractError("decoder advance produced an invalid prefix")
        available[choice] = False

    if effective_maximum == 0:
        logits = decoder_logits(prefix, option_embeddings, available, True)
        if logits.shape != (option_embeddings.shape[0] + 1,):
            raise PPOContractError("decoder STOP logits shape differs from contract")
        distribution_mask = torch.cat(
            (available, torch.ones(1, dtype=torch.bool, device=available.device))
        )
        log_probability, entropy = _masked_log_probability_and_entropy(
            logits, distribution_mask, option_embeddings.shape[0]
        )
        subchoice_log_probabilities.append(log_probability)
        subchoice_entropies.append(_normalized_entropy(entropy, int(distribution_mask.sum())))
        stopped = True

    if not subchoice_log_probabilities:
        raise PPOContractError("compound sampler produced no decision")
    action = CompoundActionV1(tuple(selected), stopped)
    total_log_probability = torch.stack(subchoice_log_probabilities).sum()
    normalized_entropy = torch.stack(subchoice_entropies).mean()
    replay = CompoundReplayV1(
        log_probability=total_log_probability,
        normalized_entropy=normalized_entropy,
        subchoice_log_probabilities=tuple(subchoice_log_probabilities),
        subchoice_entropies=tuple(subchoice_entropies),
        selected_indices=action.selected_indices,
        stopped=action.stopped,
    )
    if not torch.isfinite(replay.log_probability) or not torch.isfinite(replay.normalized_entropy):
        raise PPOContractError("compound sampler produced a nonfinite result")
    return action, replay


def replay_compound_action(
    *,
    initial_prefix: Tensor,
    option_embeddings: Tensor,
    available_mask: Tensor,
    action: CompoundActionV1,
    minimum_count: int,
    maximum_count: int,
    decoder_logits: DecoderLogits,
    decoder_advance: DecoderAdvance,
) -> CompoundReplayV1:
    if initial_prefix.ndim != 1:
        raise PPOContractError("decoder prefix must be one-dimensional")
    if option_embeddings.ndim != 2:
        raise PPOContractError("option embeddings must be two-dimensional")
    if available_mask.dtype != torch.bool or available_mask.shape != (option_embeddings.shape[0],):
        raise PPOContractError("available mask must match option embeddings")
    if isinstance(minimum_count, bool) or isinstance(maximum_count, bool):
        raise PPOContractError("selection bounds must be integers")
    if not isinstance(minimum_count, int) or not isinstance(maximum_count, int):
        raise PPOContractError("selection bounds must be integers")
    if minimum_count < 0 or maximum_count < minimum_count:
        raise PPOContractError("selection bounds are invalid")
    initial_available = int(available_mask.sum().item())
    effective_maximum = min(maximum_count, initial_available)
    if minimum_count > effective_maximum:
        raise PPOContractError("minimum selection count exceeds available options")
    if len(action.selected_indices) < minimum_count or len(action.selected_indices) > effective_maximum:
        raise PPOContractError("compound action selection count violates bounds")
    if not action.stopped and len(action.selected_indices) != effective_maximum:
        raise PPOContractError("implicit completion is allowed only at the effective maximum")

    prefix = initial_prefix
    available = available_mask.clone()
    subchoice_log_probabilities: list[Tensor] = []
    subchoice_entropies: list[Tensor] = []

    for selected_count, option_index in enumerate(action.selected_indices):
        if option_index < 0 or option_index >= option_embeddings.shape[0]:
            raise PPOContractError("compound action option index is out of range")
        if not bool(available[option_index]):
            raise PPOContractError("compound action selects an unavailable or duplicate option")
        stop_available = selected_count >= minimum_count
        logits = decoder_logits(prefix, option_embeddings, available, stop_available)
        expected_shape = (option_embeddings.shape[0] + 1,)
        if logits.shape != expected_shape:
            raise PPOContractError("decoder logits shape differs from option count plus STOP")
        distribution_mask = torch.cat(
            (available, torch.tensor([stop_available], dtype=torch.bool, device=available.device))
        )
        log_probability, entropy = _masked_log_probability_and_entropy(
            logits, distribution_mask, option_index
        )
        subchoice_log_probabilities.append(log_probability)
        subchoice_entropies.append(_normalized_entropy(entropy, int(distribution_mask.sum())))
        prefix = decoder_advance(prefix, option_embeddings[option_index])
        if prefix.ndim != 1 or not torch.isfinite(prefix).all():
            raise PPOContractError("decoder advance produced an invalid prefix")
        available[option_index] = False
        if selected_count + 1 >= effective_maximum:
            available[:] = False

    if action.stopped:
        stop_available = len(action.selected_indices) >= minimum_count
        logits = decoder_logits(prefix, option_embeddings, available, stop_available)
        if logits.shape != (option_embeddings.shape[0] + 1,):
            raise PPOContractError("decoder STOP logits shape differs from contract")
        distribution_mask = torch.cat(
            (available, torch.tensor([stop_available], dtype=torch.bool, device=available.device))
        )
        log_probability, entropy = _masked_log_probability_and_entropy(
            logits, distribution_mask, option_embeddings.shape[0]
        )
        subchoice_log_probabilities.append(log_probability)
        subchoice_entropies.append(_normalized_entropy(entropy, int(distribution_mask.sum())))

    if not subchoice_log_probabilities:
        raise PPOContractError("compound action contains no explicit or implicit decision")
    total_log_probability = torch.stack(subchoice_log_probabilities).sum()
    normalized_entropy = torch.stack(subchoice_entropies).mean()
    if not torch.isfinite(total_log_probability) or not torch.isfinite(normalized_entropy):
        raise PPOContractError("compound replay produced a nonfinite result")
    return CompoundReplayV1(
        log_probability=total_log_probability,
        normalized_entropy=normalized_entropy,
        subchoice_log_probabilities=tuple(subchoice_log_probabilities),
        subchoice_entropies=tuple(subchoice_entropies),
        selected_indices=action.selected_indices,
        stopped=action.stopped,
    )


def compound_outcome_count(
    available_count: int,
    minimum_count: int,
    maximum_count: int,
    *,
    cap: int | None = None,
) -> int:
    for name, value in {
        "available_count": available_count,
        "minimum_count": minimum_count,
        "maximum_count": maximum_count,
    }.items():
        if isinstance(value, bool) or not isinstance(value, int):
            raise PPOContractError(f"{name} must be an integer")
    if available_count < 0 or minimum_count < 0 or maximum_count < minimum_count:
        raise PPOContractError("compound outcome bounds are invalid")
    if cap is not None and (isinstance(cap, bool) or not isinstance(cap, int) or cap <= 0):
        raise PPOContractError("outcome-count cap must be a positive integer")
    effective_maximum = min(available_count, maximum_count)
    if minimum_count > effective_maximum:
        return 0
    total = 0
    for count in range(minimum_count, effective_maximum + 1):
        total += math.perm(available_count, count)
        if cap is not None and total >= cap:
            return cap
    return total


def is_forced_compound_action(
    available_count: int,
    minimum_count: int,
    maximum_count: int,
) -> bool:
    return compound_outcome_count(available_count, minimum_count, maximum_count, cap=2) == 1


@dataclass(frozen=True)
class ProbabilityReplayCheckV1:
    maximum_log_probability_absolute_error: float
    maximum_ratio_absolute_error_from_one: float
    checked_actions: int


def verify_probability_replay(
    old_log_probabilities: Tensor,
    recomputed_log_probabilities: Tensor,
    *,
    maximum_absolute_error: float = 1e-5,
    maximum_ratio_error: float = 1e-5,
) -> ProbabilityReplayCheckV1:
    old = _require_vector(old_log_probabilities, "old log probabilities")
    new = _require_vector(recomputed_log_probabilities, "recomputed log probabilities")
    if old.shape != new.shape or old.numel() == 0:
        raise PPOContractError("probability replay tensors must be nonempty and shape-matched")
    if not torch.isfinite(old).all() or not torch.isfinite(new).all():
        raise PPOContractError("probability replay tensors must be finite")
    difference = torch.abs(new - old)
    ratio_error = torch.abs(torch.exp(new - old) - 1.0)
    maximum_difference = float(difference.max().item())
    maximum_ratio_difference = float(ratio_error.max().item())
    if maximum_difference > maximum_absolute_error:
        raise PPOContractError("old compound log-probabilities do not reproduce")
    if maximum_ratio_difference > maximum_ratio_error:
        raise PPOContractError("initial PPO ratios differ from one")
    return ProbabilityReplayCheckV1(
        maximum_log_probability_absolute_error=maximum_difference,
        maximum_ratio_absolute_error_from_one=maximum_ratio_difference,
        checked_actions=old.numel(),
    )


@dataclass(frozen=True)
class GAEResultV1:
    advantages: Tensor
    returns: Tensor


def compute_gae(
    *,
    rewards: Tensor,
    values: Tensor,
    bootstrap_values: Tensor,
    terminals: Tensor,
    truncations: Tensor,
    trace_continues: Tensor,
    gamma: float = 1.0,
    gae_lambda: float = 0.95,
) -> GAEResultV1:
    vectors = {
        "rewards": _require_vector(rewards, "rewards"),
        "values": _require_vector(values, "values"),
        "bootstrap_values": _require_vector(bootstrap_values, "bootstrap values"),
        "terminals": _require_vector(terminals, "terminals"),
        "truncations": _require_vector(truncations, "truncations"),
        "trace_continues": _require_vector(trace_continues, "trace continues"),
    }
    shape = rewards.shape
    if rewards.numel() == 0 or any(value.shape != shape for value in vectors.values()):
        raise PPOContractError("GAE inputs must be nonempty and shape-matched")
    for name in ("terminals", "truncations", "trace_continues"):
        if vectors[name].dtype != torch.bool:
            raise PPOContractError(f"{name} must be boolean")
    if not torch.isfinite(rewards).all() or not torch.isfinite(values).all():
        raise PPOContractError("GAE rewards and values must be finite")
    if not torch.isfinite(bootstrap_values).all():
        raise PPOContractError("GAE bootstrap values must be finite")
    if not (0.0 <= gamma <= 1.0) or not (0.0 <= gae_lambda <= 1.0):
        raise PPOContractError("GAE gamma and lambda must be within [0, 1]")
    if torch.any(terminals & truncations):
        raise PPOContractError("a transition cannot be terminal and truncated")
    if torch.any(terminals & trace_continues) or torch.any(truncations & trace_continues):
        raise PPOContractError("terminal and truncation boundaries cannot continue a trace")
    boundaries = ~trace_continues
    if torch.any(boundaries & ~(terminals | truncations)):
        raise PPOContractError("every stopped GAE trace must be classified")
    if bool(trace_continues[-1]):
        raise PPOContractError("the final GAE node must close with terminal or truncation")
    if torch.any(torch.abs(bootstrap_values[terminals]) > 1e-8):
        raise PPOContractError("terminal transitions must bootstrap from zero")

    advantages = torch.zeros_like(rewards)
    next_advantage = rewards.new_zeros(())
    for index in range(rewards.numel() - 1, -1, -1):
        bootstrap = rewards.new_zeros(()) if bool(terminals[index]) else bootstrap_values[index]
        delta = rewards[index] + gamma * bootstrap - values[index]
        continuation = 1.0 if bool(trace_continues[index]) else 0.0
        next_advantage = delta + gamma * gae_lambda * continuation * next_advantage
        advantages[index] = next_advantage
    returns = advantages + values
    if not torch.isfinite(advantages).all() or not torch.isfinite(returns).all():
        raise PPOContractError("GAE produced a nonfinite result")
    return GAEResultV1(advantages=advantages, returns=returns)


@dataclass(frozen=True)
class RolloutEventV1:
    episode_id: str
    player: int
    policy_id: str
    policy_version: int
    selection_seq: int
    forced: bool
    terminal: bool = False
    truncation: bool = False
    reset_before: bool = False

    def __post_init__(self) -> None:
        if not self.episode_id or not self.policy_id:
            raise PPOContractError("rollout ownership identity must be nonempty")
        if self.player not in (0, 1):
            raise PPOContractError("rollout player must be zero or one")
        for name in ("policy_version", "selection_seq"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise PPOContractError(f"{name} must be a nonnegative integer")
        if self.terminal and self.truncation:
            raise PPOContractError("rollout event cannot be terminal and truncated")

    @property
    def owner(self) -> tuple[str, int, str]:
        return self.episode_id, self.player, self.policy_id


@dataclass(frozen=True)
class RecurrentSliceV1:
    events: tuple[RolloutEventV1, ...]
    learner_event_indices: tuple[int, ...]
    continuation_from_prior_slice: bool


def split_recurrent_rollout(
    events: Sequence[RolloutEventV1],
    *,
    maximum_learner_steps: int,
) -> tuple[RecurrentSliceV1, ...]:
    if isinstance(maximum_learner_steps, bool) or not isinstance(maximum_learner_steps, int):
        raise PPOContractError("maximum learner steps must be an integer")
    if maximum_learner_steps <= 0:
        raise PPOContractError("maximum learner steps must be positive")
    if not events:
        raise PPOContractError("recurrent rollout must not be empty")

    slices: list[RecurrentSliceV1] = []
    current: list[RolloutEventV1] = []
    learner_indices: list[int] = []
    current_owner: tuple[str, int, str] | None = None
    current_version: int | None = None
    expected_sequence: int | None = None
    continuation = False

    def flush() -> None:
        nonlocal current, learner_indices, continuation
        if current:
            slices.append(
                RecurrentSliceV1(
                    events=tuple(current),
                    learner_event_indices=tuple(learner_indices),
                    continuation_from_prior_slice=continuation,
                )
            )
        current = []
        learner_indices = []
        continuation = False

    previous_closed = True
    for event in events:
        identity_changed = current_owner is not None and (
            event.owner != current_owner or event.policy_version != current_version
        )
        if current_owner is None or identity_changed or previous_closed:
            if current:
                flush()
            if not event.reset_before:
                raise PPOContractError("new recurrent owner/version/episode requires an acknowledged reset")
            current_owner = event.owner
            current_version = event.policy_version
            expected_sequence = 0
            previous_closed = False
        assert expected_sequence is not None
        if event.selection_seq != expected_sequence:
            relation = "stale" if event.selection_seq < expected_sequence else "out-of-order"
            raise PPOContractError(f"{relation} rollout selection sequence")
        expected_sequence += 1
        current.append(event)
        if not event.forced:
            learner_indices.append(len(current) - 1)
        if event.terminal or event.truncation:
            previous_closed = True
            flush()
            current_owner = None
            current_version = None
            expected_sequence = None
        elif len(learner_indices) >= maximum_learner_steps:
            flush()
            continuation = True
    flush()
    if not slices:
        raise PPOContractError("recurrent rollout produced no slices")
    return tuple(slices)


@dataclass(frozen=True)
class PPOLossV1:
    total: Tensor
    policy: Tensor
    value: Tensor
    entropy: Tensor
    approximate_kl: Tensor
    clip_fraction: Tensor
    valid_actions: int
    valid_value_nodes: int


def ppo_loss(
    *,
    new_log_probabilities: Tensor,
    old_log_probabilities: Tensor,
    advantages: Tensor,
    new_values: Tensor,
    old_values: Tensor,
    returns: Tensor,
    normalized_entropies: Tensor,
    policy_mask: Tensor,
    value_mask: Tensor | None = None,
    clip_coefficient: float = 0.2,
    value_clip_coefficient: float = 0.2,
    value_coefficient: float = 0.5,
    entropy_coefficient: float = 0.01,
    normalize_advantages: bool = True,
) -> PPOLossV1:
    tensors = {
        "new_log_probabilities": _require_vector(new_log_probabilities, "new log probabilities"),
        "old_log_probabilities": _require_vector(old_log_probabilities, "old log probabilities"),
        "advantages": _require_vector(advantages, "advantages"),
        "new_values": _require_vector(new_values, "new values"),
        "old_values": _require_vector(old_values, "old values"),
        "returns": _require_vector(returns, "returns"),
        "normalized_entropies": _require_vector(normalized_entropies, "normalized entropies"),
        "policy_mask": _require_vector(policy_mask, "policy mask"),
    }
    if value_mask is None:
        value_mask = policy_mask
    tensors["value_mask"] = _require_vector(value_mask, "value mask")
    shape = new_log_probabilities.shape
    if any(value.shape != shape for value in tensors.values()):
        raise PPOContractError("PPO loss tensors must have matching shapes")
    if policy_mask.dtype != torch.bool:
        raise PPOContractError("PPO policy mask must be boolean")
    if value_mask.dtype != torch.bool:
        raise PPOContractError("PPO value mask must be boolean")
    has_policy_actions = bool(torch.any(policy_mask))
    if not torch.any(value_mask):
        raise PPOContractError("PPO batch contains no valid critic nodes")
    for name, value in tensors.items():
        if name in {"policy_mask", "value_mask"}:
            continue
        if not torch.isfinite(value).all():
            raise PPOContractError(f"{name} contains NaN or infinity")
    for name, value in {
        "clip_coefficient": clip_coefficient,
        "value_clip_coefficient": value_clip_coefficient,
        "value_coefficient": value_coefficient,
        "entropy_coefficient": entropy_coefficient,
    }.items():
        if not math.isfinite(value) or value < 0:
            raise PPOContractError(f"{name} must be finite and nonnegative")

    if has_policy_actions:
        selected_advantages = advantages[policy_mask]
        if normalize_advantages:
            standard_deviation = selected_advantages.std(unbiased=False)
            selected_advantages = (selected_advantages - selected_advantages.mean()) / (
                standard_deviation + 1e-8
            )
        log_ratio = new_log_probabilities[policy_mask] - old_log_probabilities[policy_mask]
        ratio = torch.exp(log_ratio)
        unclipped = ratio * selected_advantages
        clipped = torch.clamp(ratio, 1.0 - clip_coefficient, 1.0 + clip_coefficient) * selected_advantages
        policy = -torch.minimum(unclipped, clipped).mean()
        entropy = normalized_entropies[policy_mask].mean()
        approximate_kl = ((ratio - 1.0) - log_ratio).mean()
        clip_fraction = (torch.abs(ratio - 1.0) > clip_coefficient).float().mean()
    else:
        policy = new_values.new_zeros(())
        entropy = new_values.new_zeros(())
        approximate_kl = new_values.new_zeros(())
        clip_fraction = new_values.new_zeros(())

    selected_new_values = new_values[value_mask]
    selected_old_values = old_values[value_mask]
    selected_returns = returns[value_mask]
    clipped_values = selected_old_values + torch.clamp(
        selected_new_values - selected_old_values,
        -value_clip_coefficient,
        value_clip_coefficient,
    )
    value_unclipped = (selected_new_values - selected_returns).square()
    value_clipped = (clipped_values - selected_returns).square()
    value = 0.5 * torch.maximum(value_unclipped, value_clipped).mean()
    total = policy + value_coefficient * value - entropy_coefficient * entropy
    for name, value_tensor in {
        "total": total,
        "policy": policy,
        "value": value,
        "entropy": entropy,
        "approximate_kl": approximate_kl,
        "clip_fraction": clip_fraction,
    }.items():
        if not torch.isfinite(value_tensor):
            raise PPOContractError(f"PPO {name} is nonfinite")
    return PPOLossV1(
        total=total,
        policy=policy,
        value=value,
        entropy=entropy,
        approximate_kl=approximate_kl,
        clip_fraction=clip_fraction,
        valid_actions=int(policy_mask.sum().item()),
        valid_value_nodes=int(value_mask.sum().item()),
    )


def require_finite_gradients(parameters: Sequence[torch.nn.Parameter]) -> float:
    squared_norm = 0.0
    observed = 0
    for parameter in parameters:
        if parameter.grad is None:
            continue
        observed += 1
        if not torch.isfinite(parameter.grad).all():
            raise PPOContractError("model gradient contains NaN or infinity")
        squared_norm += float(parameter.grad.detach().double().square().sum().item())
    if observed == 0:
        raise PPOContractError("no model gradients were produced")
    norm = math.sqrt(squared_norm)
    if not math.isfinite(norm):
        raise PPOContractError("gradient norm is nonfinite")
    return norm
