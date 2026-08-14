from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import torch
from torch import Tensor

from ptcg_rl.g2.network import PTCGPolicyV1, TorchDecisionBatch, collate_projected
from ptcg_rl.g3.ppo import CompoundActionV1, replay_compound_action
from ptcg_rl.replay.semantic_loader import SemanticReplayDecisionV1


class BCTrainingError(ValueError):
    """Raised when a recurrent BC batch violates the semantic training contract."""


@dataclass(frozen=True)
class RecurrentBatchLoss:
    loss: Tensor | None
    next_hidden: Tensor
    policy_targets: int
    recurrent_decisions: int


def _vectorized_compound_nll(
    model: PTCGPolicyV1,
    output_hidden: Tensor,
    option_embeddings: Tensor,
    option_offsets: Tensor,
    option_available: Tensor,
    decisions: Sequence[SemanticReplayDecisionV1],
) -> tuple[Tensor | None, int]:
    """Replay all non-forced compound teacher actions in one dense GPU batch.

    The public recurrent state is produced by the main policy forward and is
    independent of the temporary compound-action decoder prefix. Forced requests
    therefore need no decoder work because they contribute no policy loss.
    """
    count = len(decisions)
    if count == 0 or output_hidden.shape[0] != count:
        raise BCTrainingError("vectorized decoder batch shape differs from decisions")
    device = output_hidden.device
    forced = torch.tensor(
        [decision.request.has_only_one_outcome for decision in decisions],
        dtype=torch.bool,
        device=device,
    )
    policy_mask = ~forced
    policy_targets = int(policy_mask.sum().item())
    if policy_targets == 0:
        return None, 0

    option_counts = option_offsets[1:] - option_offsets[:-1]
    if option_counts.shape != (count,):
        raise BCTrainingError("vectorized decoder option offsets differ from decisions")
    maximum_options = int(option_counts.max().item()) if option_counts.numel() else 0
    if maximum_options <= 0:
        raise BCTrainingError("non-forced BC decision has no decoder options")

    owner = torch.repeat_interleave(
        torch.arange(count, device=device, dtype=torch.long), option_counts
    )
    local = torch.arange(option_embeddings.shape[0], device=device, dtype=torch.long)
    local = local - torch.repeat_interleave(option_offsets[:-1], option_counts)
    padded_options = option_embeddings.new_zeros(
        (count, maximum_options, option_embeddings.shape[1])
    )
    padded_options[owner, local] = option_embeddings
    available = torch.zeros((count, maximum_options), dtype=torch.bool, device=device)
    available[owner, local] = option_available

    selected_lengths = torch.tensor(
        [len(decision.action.submitted_original_indices) for decision in decisions],
        dtype=torch.long,
        device=device,
    )
    stopped = torch.tensor(
        [decision.action.stopped_early for decision in decisions],
        dtype=torch.bool,
        device=device,
    )
    minimum_counts = torch.tensor(
        [decision.request.min_count for decision in decisions],
        dtype=torch.long,
        device=device,
    )
    maximum_counts = torch.tensor(
        [decision.request.max_count for decision in decisions],
        dtype=torch.long,
        device=device,
    )
    maximum_selected = max(
        (len(decision.action.submitted_original_indices) for decision in decisions),
        default=0,
    )
    selected = torch.full(
        (count, maximum_selected), -1, dtype=torch.long, device=device
    )
    for row, decision in enumerate(decisions):
        values = decision.action.submitted_original_indices
        if values:
            selected[row, : len(values)] = torch.tensor(values, dtype=torch.long, device=device)

    subchoices = selected_lengths + stopped.to(torch.long)
    maximum_subchoices = int(subchoices[policy_mask].max().item())
    if maximum_subchoices <= 0:
        raise BCTrainingError("non-forced compound action contains no decoder subchoice")

    prefix = model.decoder_initial(output_hidden)
    # selection_option is invariant across decoder subchoices. The scalar decoder
    # previously recomputed it for every decision/subchoice; precomputing it here
    # removes thousands of tiny GPU kernels per recurrent time step.
    option_state = model.selection_option(padded_options)
    total_log_probability = output_hidden.new_zeros((count,))
    scale = float(model.config.selection_hidden) ** 0.5
    row_indices = torch.arange(count, device=device, dtype=torch.long)

    for subchoice_index in range(maximum_subchoices):
        select_mask = policy_mask & (selected_lengths > subchoice_index)
        stop_mask = policy_mask & stopped & (selected_lengths == subchoice_index)
        active = select_mask | stop_mask
        if not bool(active.any().item()):
            continue

        option_logits = (option_state * prefix.unsqueeze(1)).sum(dim=-1) / scale
        option_logits = option_logits.masked_fill(~available, float("-inf"))
        stop_available = minimum_counts <= subchoice_index
        stop_logits = (model.stop_embedding.unsqueeze(0) * prefix).sum(dim=-1) / scale
        stop_logits = stop_logits.masked_fill(~stop_available, float("-inf"))
        logits = torch.cat((option_logits, stop_logits.unsqueeze(1)), dim=1)
        # Inactive rows are supplied a single dummy STOP logit so the dense
        # log-softmax remains finite without affecting the gathered active loss.
        logits = logits.masked_fill(~active.unsqueeze(1), float("-inf"))
        logits[~active, maximum_options] = 0.0
        log_probabilities = torch.log_softmax(logits, dim=1)

        if subchoice_index < maximum_selected:
            selected_here = selected[:, subchoice_index].clamp_min(0)
        else:
            selected_here = torch.zeros(count, dtype=torch.long, device=device)
        chosen_column = torch.where(
            select_mask,
            selected_here,
            torch.full_like(selected_here, maximum_options),
        )
        chosen_log_probability = log_probabilities[row_indices, chosen_column]
        total_log_probability = total_log_probability + torch.where(
            active, chosen_log_probability, torch.zeros_like(chosen_log_probability)
        )

        if bool(select_mask.any().item()):
            selecting_rows = torch.nonzero(select_mask, as_tuple=False).squeeze(1)
            selecting_options = selected_here[selecting_rows]
            chosen_embeddings = padded_options[selecting_rows, selecting_options]
            updated_prefix = model.selection_gru(
                chosen_embeddings, prefix[selecting_rows]
            )
            prefix = prefix.index_copy(0, selecting_rows, updated_prefix)
            available[selecting_rows, selecting_options] = False
            reached_maximum = (
                (subchoice_index + 1) >= maximum_counts[selecting_rows]
            )
            if bool(reached_maximum.any().item()):
                finished_rows = selecting_rows[reached_maximum]
                available[finished_rows] = False

    loss = -total_log_probability[policy_mask].mean()
    return loss, policy_targets


@dataclass(frozen=True)
class PackedActionSupervision:
    policy_mask: Tensor
    minimum_counts: Tensor
    maximum_counts: Tensor
    stopped: Tensor
    selected_lengths: Tensor
    selected_indices: Tensor
    option_owner: Tensor
    option_local: Tensor
    available_padded: Tensor
    maximum_options: int
    maximum_subchoices: int
    policy_targets: int

    def to(
        self,
        device: torch.device | str,
        *,
        non_blocking: bool = False,
    ) -> PackedActionSupervision:
        values = {
            "maximum_options": self.maximum_options,
            "maximum_subchoices": self.maximum_subchoices,
            "policy_targets": self.policy_targets,
        }
        for name in (
            "policy_mask",
            "minimum_counts",
            "maximum_counts",
            "stopped",
            "selected_lengths",
            "selected_indices",
            "option_owner",
            "option_local",
            "available_padded",
        ):
            values[name] = getattr(self, name).to(device, non_blocking=non_blocking)
        return PackedActionSupervision(**values)

    def pin_memory(self) -> PackedActionSupervision:
        values = {
            "maximum_options": self.maximum_options,
            "maximum_subchoices": self.maximum_subchoices,
            "policy_targets": self.policy_targets,
        }
        for name in (
            "policy_mask",
            "minimum_counts",
            "maximum_counts",
            "stopped",
            "selected_lengths",
            "selected_indices",
            "option_owner",
            "option_local",
            "available_padded",
        ):
            values[name] = getattr(self, name).pin_memory()
        return PackedActionSupervision(**values)


@dataclass(frozen=True)
class PackedRecurrentStep:
    active_indices: Tensor
    batch: TorchDecisionBatch
    supervision: PackedActionSupervision
    recurrent_decisions: int


@dataclass(frozen=True)
class PackedRecurrentChunk:
    steps: tuple[PackedRecurrentStep, ...]
    policy_targets: int
    recurrent_decisions: int


@dataclass(frozen=True)
class PackedRecurrentGroup:
    batch_size: int
    chunks: tuple[PackedRecurrentChunk, ...]
    policy_targets: int
    recurrent_decisions: int


def _pack_action_supervision(
    decisions: Sequence[SemanticReplayDecisionV1],
    *,
    pin_memory: bool,
) -> PackedActionSupervision:
    if not decisions:
        raise BCTrainingError("cannot pack empty BC action supervision")
    count = len(decisions)
    option_counts = [len(decision.projected.model.option_available_mask) for decision in decisions]
    maximum_options = max(option_counts, default=0)
    policy = [not decision.request.has_only_one_outcome for decision in decisions]
    selected_values = [tuple(decision.action.submitted_original_indices) for decision in decisions]
    selected_lengths_values = [len(values) for values in selected_values]
    maximum_selected = max(selected_lengths_values, default=0)
    stopped_values = [bool(decision.action.stopped_early) for decision in decisions]
    minimum_values = [int(decision.request.min_count) for decision in decisions]
    maximum_values = [int(decision.request.max_count) for decision in decisions]

    selected = torch.full((count, maximum_selected), -1, dtype=torch.long)
    available = torch.zeros((count, maximum_options), dtype=torch.bool)
    owner: list[int] = []
    local: list[int] = []
    for row, decision in enumerate(decisions):
        option_mask = tuple(bool(value) for value in decision.projected.model.option_available_mask)
        available_count = sum(option_mask)
        if maximum_values[row] > available_count or minimum_values[row] > maximum_values[row]:
            raise BCTrainingError("packed request bounds differ from legal option mask")
        if option_mask:
            available[row, : len(option_mask)] = torch.tensor(option_mask, dtype=torch.bool)
        owner.extend([row] * len(option_mask))
        local.extend(range(len(option_mask)))
        values = selected_values[row]
        if len(values) != len(set(values)):
            raise BCTrainingError("packed teacher action contains duplicate selections")
        if any(index < 0 or index >= len(option_mask) or not option_mask[index] for index in values):
            raise BCTrainingError("packed teacher action selects an unavailable option")
        if values:
            selected[row, : len(values)] = torch.tensor(values, dtype=torch.long)

    policy_targets = sum(policy)
    maximum_subchoices = max(
        (
            selected_lengths_values[index] + int(stopped_values[index])
            for index in range(count)
            if policy[index]
        ),
        default=0,
    )
    if policy_targets > 0 and maximum_subchoices <= 0:
        raise BCTrainingError("packed non-forced action has no decoder subchoice")
    supervision = PackedActionSupervision(
        policy_mask=torch.tensor(policy, dtype=torch.bool),
        minimum_counts=torch.tensor(minimum_values, dtype=torch.long),
        maximum_counts=torch.tensor(maximum_values, dtype=torch.long),
        stopped=torch.tensor(stopped_values, dtype=torch.bool),
        selected_lengths=torch.tensor(selected_lengths_values, dtype=torch.long),
        selected_indices=selected,
        option_owner=torch.tensor(owner, dtype=torch.long),
        option_local=torch.tensor(local, dtype=torch.long),
        available_padded=available,
        maximum_options=maximum_options,
        maximum_subchoices=maximum_subchoices,
        policy_targets=policy_targets,
    )
    return supervision.pin_memory() if pin_memory else supervision


def pack_recurrent_group(
    sequences: Sequence[Sequence[SemanticReplayDecisionV1]],
    *,
    sequence_length: int,
    pin_memory: bool = False,
) -> PackedRecurrentGroup:
    if sequence_length <= 0 or not sequences or any(not sequence for sequence in sequences):
        raise BCTrainingError("packed recurrent group requires nonempty sequences and positive length")
    maximum_length = max(len(sequence) for sequence in sequences)
    chunks: list[PackedRecurrentChunk] = []
    total_targets = 0
    total_decisions = 0
    for start in range(0, maximum_length, sequence_length):
        steps: list[PackedRecurrentStep] = []
        chunk_targets = 0
        chunk_decisions = 0
        stop = min(start + sequence_length, maximum_length)
        for time_index in range(start, stop):
            active = [
                index for index, sequence in enumerate(sequences) if time_index < len(sequence)
            ]
            if not active:
                continue
            decisions = [sequences[index][time_index] for index in active]
            batch = collate_projected(tuple(decision.projected for decision in decisions))
            supervision = _pack_action_supervision(decisions, pin_memory=pin_memory)
            active_tensor = torch.tensor(active, dtype=torch.long)
            if pin_memory:
                batch = batch.pin_memory()
                active_tensor = active_tensor.pin_memory()
            step = PackedRecurrentStep(
                active_indices=active_tensor,
                batch=batch,
                supervision=supervision,
                recurrent_decisions=len(decisions),
            )
            steps.append(step)
            chunk_targets += supervision.policy_targets
            chunk_decisions += len(decisions)
        if not steps:
            continue
        chunks.append(
            PackedRecurrentChunk(
                steps=tuple(steps),
                policy_targets=chunk_targets,
                recurrent_decisions=chunk_decisions,
            )
        )
        total_targets += chunk_targets
        total_decisions += chunk_decisions
    if not chunks:
        raise BCTrainingError("packed recurrent group produced no chunks")
    return PackedRecurrentGroup(
        batch_size=len(sequences),
        chunks=tuple(chunks),
        policy_targets=total_targets,
        recurrent_decisions=total_decisions,
    )


def _packed_vectorized_compound_nll(
    model: PTCGPolicyV1,
    output_hidden: Tensor,
    option_embeddings: Tensor,
    supervision: PackedActionSupervision,
) -> Tensor | None:
    count = int(supervision.policy_mask.shape[0])
    if output_hidden.shape[0] != count:
        raise BCTrainingError("packed decoder batch shape differs from supervision")
    if supervision.policy_targets == 0:
        return None
    if supervision.maximum_options <= 0:
        raise BCTrainingError("packed non-forced BC decision has no options")
    if supervision.option_owner.numel() != option_embeddings.shape[0]:
        raise BCTrainingError("packed decoder option mapping differs from embeddings")

    padded_options = option_embeddings.new_zeros(
        (count, supervision.maximum_options, option_embeddings.shape[1])
    )
    padded_options[supervision.option_owner, supervision.option_local] = option_embeddings
    available = supervision.available_padded.clone()
    prefix = model.decoder_initial(output_hidden)
    option_state = model.selection_option(padded_options)
    total_log_probability = output_hidden.new_zeros((count,))
    scale = float(model.config.selection_hidden) ** 0.5
    row_indices = torch.arange(count, device=output_hidden.device, dtype=torch.long)

    for subchoice_index in range(supervision.maximum_subchoices):
        select_mask = supervision.policy_mask & (
            supervision.selected_lengths > subchoice_index
        )
        stop_mask = (
            supervision.policy_mask
            & supervision.stopped
            & (supervision.selected_lengths == subchoice_index)
        )
        active = select_mask | stop_mask
        option_logits = (option_state * prefix.unsqueeze(1)).sum(dim=-1) / scale
        option_logits = option_logits.masked_fill(~available, float("-inf"))
        stop_available = supervision.minimum_counts <= subchoice_index
        stop_logits = (model.stop_embedding.unsqueeze(0) * prefix).sum(dim=-1) / scale
        stop_logits = stop_logits.masked_fill(~stop_available, float("-inf"))
        logits = torch.cat((option_logits, stop_logits.unsqueeze(1)), dim=1)
        logits = logits.masked_fill(~active.unsqueeze(1), float("-inf"))
        logits[~active, supervision.maximum_options] = 0.0
        log_probabilities = torch.log_softmax(logits, dim=1)

        if subchoice_index < supervision.selected_indices.shape[1]:
            selected_here = supervision.selected_indices[:, subchoice_index].clamp_min(0)
        else:
            selected_here = torch.zeros(count, dtype=torch.long, device=output_hidden.device)
        chosen_column = torch.where(
            select_mask,
            selected_here,
            torch.full_like(selected_here, supervision.maximum_options),
        )
        chosen_log_probability = log_probabilities[row_indices, chosen_column]
        total_log_probability = total_log_probability + torch.where(
            active, chosen_log_probability, torch.zeros_like(chosen_log_probability)
        )

        selecting_rows = torch.nonzero(select_mask, as_tuple=False).squeeze(1)
        if selecting_rows.numel():
            selecting_options = selected_here[selecting_rows]
            chosen_embeddings = padded_options[selecting_rows, selecting_options]
            updated_prefix = model.selection_gru(chosen_embeddings, prefix[selecting_rows])
            prefix = prefix.index_copy(0, selecting_rows, updated_prefix)
            available[selecting_rows, selecting_options] = False
            reached_maximum = (
                (subchoice_index + 1) >= supervision.maximum_counts[selecting_rows]
            )
            finished_rows = selecting_rows[reached_maximum]
            available[finished_rows] = False

    return -total_log_probability[supervision.policy_mask].mean()


def packed_recurrent_chunk_loss(
    model: PTCGPolicyV1,
    chunk: PackedRecurrentChunk,
    *,
    hidden: Tensor,
    non_blocking: bool = True,
) -> RecurrentBatchLoss:
    if hidden.ndim != 2 or hidden.shape[1] != model.config.public_hidden:
        raise BCTrainingError("packed recurrent hidden shape differs from model")
    device = hidden.device
    states = hidden
    weighted_losses: list[Tensor] = []
    policy_targets = 0
    recurrent_decisions = 0
    for step in chunk.steps:
        active = step.active_indices.to(device, non_blocking=non_blocking)
        batch = step.batch.to(device, non_blocking=non_blocking)
        supervision = step.supervision.to(device, non_blocking=non_blocking)
        hidden_batch = states.index_select(0, active)
        output = model(batch, hidden_batch)
        states = states.index_copy(0, active, output.hidden)
        loss = _packed_vectorized_compound_nll(
            model,
            output.hidden,
            output.option_embeddings,
            supervision,
        )
        recurrent_decisions += step.recurrent_decisions
        if loss is not None:
            weighted_losses.append(loss * supervision.policy_targets)
            policy_targets += supervision.policy_targets
    if policy_targets != chunk.policy_targets or recurrent_decisions != chunk.recurrent_decisions:
        raise BCTrainingError("packed recurrent chunk accounting differs")
    if not weighted_losses:
        return RecurrentBatchLoss(
            loss=None,
            next_hidden=states,
            policy_targets=0,
            recurrent_decisions=recurrent_decisions,
        )
    loss = torch.stack(weighted_losses).sum() / policy_targets
    return RecurrentBatchLoss(
        loss=loss,
        next_hidden=states,
        policy_targets=policy_targets,
        recurrent_decisions=recurrent_decisions,
    )


def recurrent_sequence_batch_loss(
    model: PTCGPolicyV1,
    sequences: Sequence[Sequence[SemanticReplayDecisionV1]],
    *,
    hidden: Tensor | None = None,
    verify: bool = False,
    require_policy_target: bool = True,
) -> RecurrentBatchLoss:
    """Evaluate ragged recurrent BC sequences with one network forward per time step.

    Each sequence is one actor trajectory/chunk. The function preserves recurrent
    state independently for each sequence and batches all active trajectories at
    the same recurrent time step. Forced requests advance recurrence but do not
    contribute policy loss, matching the sealed replay semantics.
    """
    if not sequences or any(not sequence for sequence in sequences):
        raise BCTrainingError("recurrent BC batch requires nonempty sequences")
    device = next(model.parameters()).device
    batch_size = len(sequences)
    if hidden is None:
        initial = model.initial_hidden(batch_size, device)
    else:
        if hidden.shape != (batch_size, model.config.public_hidden):
            raise BCTrainingError("initial recurrent hidden shape differs from batch")
        initial = hidden
    states = [initial[index] for index in range(batch_size)]
    losses: list[Tensor] = []
    recurrent_decisions = 0

    for time_index in range(max(len(sequence) for sequence in sequences)):
        active_indices = [
            index for index, sequence in enumerate(sequences) if time_index < len(sequence)
        ]
        decisions = [sequences[index][time_index] for index in active_indices]
        hidden_batch = torch.stack([states[index] for index in active_indices], dim=0)
        batch = collate_projected(tuple(decision.projected for decision in decisions), device=device)
        output = model(batch, hidden_batch)
        for local_index, sequence_index in enumerate(active_indices):
            states[sequence_index] = output.hidden[local_index]
        recurrent_decisions += len(decisions)

        if verify:
            option_cursor = 0
            for local_index, decision in enumerate(decisions):
                option_count = len(decision.request.options)
                option_start = option_cursor
                option_end = option_start + option_count
                option_cursor = option_end
                available = batch.option_available[option_start:option_end]
                selected = tuple(decision.action.submitted_original_indices)
                if tuple(bool(value) for value in available.detach().cpu().tolist()) != tuple(
                    option.available for option in decision.request.options
                ):
                    raise BCTrainingError("batched legal-option mask differs from semantic request")
                if tuple(decision.projected.transport.original_indices) != tuple(
                    option.original_index for option in decision.request.options
                ):
                    raise BCTrainingError("batched transport map differs from semantic request")
                if len(selected) != len(set(selected)):
                    raise BCTrainingError("teacher action contains duplicate ordered selection")
                forced = bool(decision.request.has_only_one_outcome)
                if option_count == 0 and decision.request.min_count == 0 and decision.request.max_count == 0:
                    if selected or not forced:
                        raise BCTrainingError("zero-option request is not the unique forced empty outcome")
                    continue
                replay = replay_compound_action(
                    initial_prefix=model.decoder_initial(output.hidden[local_index]),
                    option_embeddings=output.option_embeddings[option_start:option_end],
                    available_mask=available,
                    action=CompoundActionV1(
                        selected_indices=selected,
                        stopped=bool(decision.action.stopped_early),
                    ),
                    minimum_count=decision.request.min_count,
                    maximum_count=decision.request.max_count,
                    decoder_logits=model.decoder_logits,
                    decoder_advance=model.decoder_advance,
                )
                if not forced:
                    losses.append(-replay.log_probability)
            if option_cursor != int(output.option_embeddings.shape[0]):
                raise BCTrainingError("batched option slicing did not consume all option embeddings")
        else:
            vectorized_loss, vectorized_targets = _vectorized_compound_nll(
                model,
                output.hidden,
                output.option_embeddings,
                batch.option_offsets,
                batch.option_available,
                decisions,
            )
            if vectorized_loss is not None:
                # The outer contract averages one total compound-action NLL per
                # non-forced policy decision across all recurrent time steps.
                losses.extend(vectorized_loss.unsqueeze(0).expand(vectorized_targets))

    if not losses:
        if require_policy_target:
            raise BCTrainingError("recurrent BC batch contains no policy-loss target")
        return RecurrentBatchLoss(
            loss=None,
            next_hidden=torch.stack(states, dim=0),
            policy_targets=0,
            recurrent_decisions=recurrent_decisions,
        )
    loss = torch.stack(losses).mean()
    if verify and not bool(torch.isfinite(loss).detach().cpu()):
        raise BCTrainingError("recurrent BC batch loss is nonfinite")
    return RecurrentBatchLoss(
        loss=loss,
        next_hidden=torch.stack(states, dim=0),
        policy_targets=len(losses),
        recurrent_decisions=recurrent_decisions,
    )
