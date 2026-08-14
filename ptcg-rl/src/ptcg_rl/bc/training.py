from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import torch
from torch import Tensor

from ptcg_rl.g2.network import PTCGPolicyV1, collate_projected
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
        option_cursor = 0
        for local_index, (sequence_index, decision) in enumerate(zip(active_indices, decisions)):
            states[sequence_index] = output.hidden[local_index]
            recurrent_decisions += 1
            option_count = len(decision.request.options)
            option_start = option_cursor
            option_end = option_start + option_count
            option_cursor = option_end
            options = output.option_embeddings[option_start:option_end]
            available = batch.option_available[option_start:option_end]
            selected = tuple(decision.action.submitted_original_indices)
            forced = bool(decision.request.has_only_one_outcome)
            stopped = bool(decision.action.stopped_early)

            if verify:
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

            if option_count == 0 and decision.request.min_count == 0 and decision.request.max_count == 0:
                if selected or not forced:
                    raise BCTrainingError("zero-option request is not the unique forced empty outcome")
                continue

            replay = replay_compound_action(
                initial_prefix=model.decoder_initial(output.hidden[local_index]),
                option_embeddings=options,
                available_mask=available,
                action=CompoundActionV1(selected_indices=selected, stopped=stopped),
                minimum_count=decision.request.min_count,
                maximum_count=decision.request.max_count,
                decoder_logits=model.decoder_logits,
                decoder_advance=model.decoder_advance,
            )
            if not forced:
                losses.append(-replay.log_probability)

        if option_cursor != int(output.option_embeddings.shape[0]):
            raise BCTrainingError("batched option slicing did not consume all option embeddings")

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
