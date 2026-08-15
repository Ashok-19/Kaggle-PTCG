from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import torch
from torch import Tensor


class BatchedCompoundError(ValueError):
    """Raised when batched compound-action tensors violate decoder contracts."""


@dataclass(frozen=True)
class BatchedCompoundActionV1:
    selected_indices: Tensor
    selected_lengths: Tensor
    stopped: Tensor
    log_probabilities: Tensor
    normalized_entropies: Tensor

    @property
    def batch_size(self) -> int:
        return int(self.selected_lengths.numel())


def _pad_options(
    option_embeddings: Tensor,
    option_offsets: Tensor,
    available_mask: Tensor,
) -> tuple[Tensor, Tensor, Tensor]:
    if option_embeddings.ndim != 2:
        raise BatchedCompoundError("option embeddings must be two-dimensional")
    if option_offsets.ndim != 1 or option_offsets.numel() < 2:
        raise BatchedCompoundError("option offsets must contain one boundary per batch row")
    if available_mask.ndim != 1 or available_mask.dtype != torch.bool:
        raise BatchedCompoundError("available mask must be a boolean vector")
    if available_mask.numel() != option_embeddings.shape[0]:
        raise BatchedCompoundError("available mask differs from flattened option embeddings")
    offsets = option_offsets.to(torch.long)
    if int(offsets[0].item()) != 0 or int(offsets[-1].item()) != option_embeddings.shape[0]:
        raise BatchedCompoundError("option offsets do not span the flattened option table")
    lengths = offsets[1:] - offsets[:-1]
    if torch.any(lengths < 0):
        raise BatchedCompoundError("option offsets are not monotonic")
    batch_size = int(lengths.numel())
    maximum_options = int(lengths.max().item()) if lengths.numel() else 0
    padded = option_embeddings.new_zeros(
        (batch_size, maximum_options, option_embeddings.shape[1])
    )
    available = torch.zeros(
        (batch_size, maximum_options), dtype=torch.bool, device=option_embeddings.device
    )
    if option_embeddings.shape[0]:
        owner = torch.repeat_interleave(
            torch.arange(batch_size, dtype=torch.long, device=option_embeddings.device),
            lengths,
        )
        local = torch.arange(
            option_embeddings.shape[0], dtype=torch.long, device=option_embeddings.device
        ) - torch.repeat_interleave(offsets[:-1], lengths)
        padded[owner, local] = option_embeddings
        available[owner, local] = available_mask
    return padded, available, lengths


def _pad_primary_option_logits(
    primary_option_logits: Tensor,
    option_offsets: Tensor,
) -> Tensor:
    if primary_option_logits.ndim != 1:
        raise BatchedCompoundError("primary option logits must be one-dimensional")
    offsets = option_offsets.to(device=primary_option_logits.device, dtype=torch.long)
    if offsets.ndim != 1 or offsets.numel() < 2:
        raise BatchedCompoundError("option offsets must contain one boundary per batch row")
    if int(offsets[0].item()) != 0 or int(offsets[-1].item()) != primary_option_logits.numel():
        raise BatchedCompoundError("primary option logits differ from option offsets")
    lengths = offsets[1:] - offsets[:-1]
    if torch.any(lengths < 0):
        raise BatchedCompoundError("option offsets are not monotonic")
    batch_size = int(lengths.numel())
    maximum_options = int(lengths.max().item()) if lengths.numel() else 0
    padded = primary_option_logits.new_zeros((batch_size, maximum_options))
    if primary_option_logits.numel():
        owner = torch.repeat_interleave(
            torch.arange(batch_size, dtype=torch.long, device=primary_option_logits.device),
            lengths,
        )
        local = torch.arange(
            primary_option_logits.numel(), dtype=torch.long, device=primary_option_logits.device
        ) - torch.repeat_interleave(offsets[:-1], lengths)
        padded[owner, local] = primary_option_logits
    return padded


def _distribution_stats(logits: Tensor, legal: Tensor) -> tuple[Tensor, Tensor, Tensor]:
    if logits.ndim != 2 or legal.shape != logits.shape or legal.dtype != torch.bool:
        raise BatchedCompoundError("batched distribution logits/mask differ")
    if torch.any(~legal.any(dim=1)):
        raise BatchedCompoundError("batched compound distribution has an empty row")
    if torch.isnan(logits).any() or torch.isposinf(logits).any():
        raise BatchedCompoundError("batched compound logits contain NaN or positive infinity")
    masked = logits.masked_fill(~legal, float("-inf"))
    log_probabilities = torch.log_softmax(masked, dim=1)
    probabilities = torch.exp(log_probabilities).masked_fill(~legal, 0.0)
    safe_logs = torch.where(legal, log_probabilities, torch.zeros_like(log_probabilities))
    entropy = -(probabilities * safe_logs).sum(dim=1)
    legal_count = legal.sum(dim=1)
    normalized_entropy = torch.where(
        legal_count > 1,
        entropy / torch.log(legal_count.to(entropy.dtype).clamp_min(2)),
        torch.zeros_like(entropy),
    )
    return log_probabilities, normalized_entropy, legal_count


def _decoder_logits(
    model: Any,
    prefix: Tensor,
    option_state: Tensor,
    primary_option_logits: Tensor,
    available: Tensor,
    stop_available: Tensor,
    *,
    active: Tensor,
    first_subchoice: bool,
) -> tuple[Tensor, Tensor]:
    scale = math.sqrt(float(model.config.selection_hidden))
    if first_subchoice:
        if primary_option_logits.shape != available.shape:
            raise BatchedCompoundError("padded primary option logits differ from available mask")
        option_logits = primary_option_logits
    else:
        option_logits = (option_state * prefix.unsqueeze(1)).sum(dim=-1) / scale
    option_logits = option_logits.masked_fill(~available, float("-inf"))
    stop_logits = (model.stop_embedding.unsqueeze(0) * prefix).sum(dim=-1) / scale
    stop_logits = stop_logits.masked_fill(~stop_available, float("-inf"))
    logits = torch.cat((option_logits, stop_logits.unsqueeze(1)), dim=1)
    legal = torch.cat((available, stop_available.unsqueeze(1)), dim=1)
    # Finished rows participate only as deterministic dummy STOP rows. This avoids
    # shape changes and keeps the entire autoregressive loop GPU-batched.
    legal = legal & active.unsqueeze(1)
    legal[~active, -1] = True
    logits = logits.masked_fill(~legal, float("-inf"))
    logits[~active, -1] = 0.0
    return logits, legal


def sample_compound_actions_batched(
    model: Any,
    *,
    public_hidden: Tensor,
    primary_option_logits: Tensor,
    option_embeddings: Tensor,
    option_offsets: Tensor,
    available_mask: Tensor,
    minimum_counts: Tensor,
    maximum_counts: Tensor,
    generator: torch.Generator | None = None,
) -> BatchedCompoundActionV1:
    if public_hidden.ndim != 2:
        raise BatchedCompoundError("public hidden state must be batched")
    padded_options, available, _ = _pad_options(
        option_embeddings, option_offsets, available_mask
    )
    padded_primary_logits = _pad_primary_option_logits(primary_option_logits, option_offsets)
    batch_size = public_hidden.shape[0]
    minimum = minimum_counts.to(device=public_hidden.device, dtype=torch.long)
    maximum = maximum_counts.to(device=public_hidden.device, dtype=torch.long)
    if minimum.shape != (batch_size,) or maximum.shape != (batch_size,):
        raise BatchedCompoundError("selection bounds differ from batch size")
    available_count = available.sum(dim=1)
    effective_maximum = torch.minimum(maximum, available_count)
    if torch.any(minimum < 0) or torch.any(maximum < minimum):
        raise BatchedCompoundError("selection bounds are invalid")
    if torch.any(minimum > effective_maximum):
        raise BatchedCompoundError("minimum selection count exceeds available options")

    prefix = model.decoder_initial(public_hidden)
    if prefix.ndim != 2 or prefix.shape[0] != batch_size:
        raise BatchedCompoundError("decoder initial state is not batched")
    option_state = model.selection_option(padded_options)
    maximum_options = padded_options.shape[1]
    selected_indices = torch.full(
        (batch_size, maximum_options), -1, dtype=torch.long, device=public_hidden.device
    )
    selected_lengths = torch.zeros(batch_size, dtype=torch.long, device=public_hidden.device)
    stopped = torch.zeros(batch_size, dtype=torch.bool, device=public_hidden.device)
    finished = torch.zeros_like(stopped)
    total_log_probability = public_hidden.new_zeros((batch_size,))
    entropy_sum = public_hidden.new_zeros((batch_size,))
    subchoice_count = torch.zeros(batch_size, dtype=torch.long, device=public_hidden.device)
    maximum_subchoices = max(1, int(effective_maximum.max().item()))
    rows = torch.arange(batch_size, dtype=torch.long, device=public_hidden.device)

    for subchoice in range(maximum_subchoices):
        active = ~finished
        stop_available = selected_lengths >= minimum
        logits, legal = _decoder_logits(
            model,
            prefix,
            option_state,
            padded_primary_logits,
            available,
            stop_available,
            active=active,
            first_subchoice=subchoice == 0,
        )
        log_probabilities, normalized_entropy, _ = _distribution_stats(logits, legal)
        probabilities = torch.softmax(logits, dim=1)
        choice = torch.multinomial(probabilities, 1, generator=generator).squeeze(1)
        chosen_log_probability = log_probabilities[rows, choice]
        total_log_probability = total_log_probability + torch.where(
            active, chosen_log_probability, torch.zeros_like(chosen_log_probability)
        )
        entropy_sum = entropy_sum + torch.where(
            active, normalized_entropy, torch.zeros_like(normalized_entropy)
        )
        subchoice_count = subchoice_count + active.to(torch.long)

        stop_now = active & (choice == maximum_options)
        stopped |= stop_now
        select_now = active & ~stop_now
        selecting_rows = torch.nonzero(select_now, as_tuple=False).squeeze(1)
        if selecting_rows.numel():
            selecting_options = choice[selecting_rows]
            positions = selected_lengths[selecting_rows]
            selected_indices[selecting_rows, positions] = selecting_options
            chosen_embeddings = padded_options[selecting_rows, selecting_options]
            updated_prefix = model.selection_gru(
                chosen_embeddings, prefix[selecting_rows]
            )
            prefix = prefix.index_copy(0, selecting_rows, updated_prefix)
            available[selecting_rows, selecting_options] = False
            selected_lengths[selecting_rows] += 1

        finished |= stop_now | (selected_lengths >= effective_maximum)

    if torch.any(~finished):
        raise BatchedCompoundError("batched compound sampler did not terminate")
    if torch.any(subchoice_count <= 0):
        raise BatchedCompoundError("batched compound sampler produced an empty action")
    normalized_entropies = entropy_sum / subchoice_count.to(entropy_sum.dtype)
    if not torch.isfinite(total_log_probability).all() or not torch.isfinite(normalized_entropies).all():
        raise BatchedCompoundError("batched compound sampler produced nonfinite statistics")
    return BatchedCompoundActionV1(
        selected_indices=selected_indices,
        selected_lengths=selected_lengths,
        stopped=stopped,
        log_probabilities=total_log_probability,
        normalized_entropies=normalized_entropies,
    )


def replay_compound_actions_batched(
    model: Any,
    *,
    public_hidden: Tensor,
    primary_option_logits: Tensor,
    option_embeddings: Tensor,
    option_offsets: Tensor,
    available_mask: Tensor,
    minimum_counts: Tensor,
    maximum_counts: Tensor,
    actions: BatchedCompoundActionV1,
) -> tuple[Tensor, Tensor]:
    padded_options, available, _ = _pad_options(
        option_embeddings, option_offsets, available_mask
    )
    padded_primary_logits = _pad_primary_option_logits(primary_option_logits, option_offsets)
    batch_size = public_hidden.shape[0]
    if actions.selected_lengths.shape != (batch_size,) or actions.stopped.shape != (batch_size,):
        raise BatchedCompoundError("batched action metadata differs from replay batch")
    minimum = minimum_counts.to(device=public_hidden.device, dtype=torch.long)
    maximum = maximum_counts.to(device=public_hidden.device, dtype=torch.long)
    if minimum.shape != (batch_size,) or maximum.shape != (batch_size,):
        raise BatchedCompoundError("selection bounds differ from replay batch")
    prefix = model.decoder_initial(public_hidden)
    option_state = model.selection_option(padded_options)
    maximum_options = padded_options.shape[1]
    if actions.selected_indices.shape[0] != batch_size:
        raise BatchedCompoundError("selected-index tensor differs from replay batch")
    maximum_subchoices = int(
        (actions.selected_lengths + actions.stopped.to(torch.long)).max().item()
    )
    if maximum_subchoices <= 0:
        raise BatchedCompoundError("batched replay contains no decoder subchoices")
    total_log_probability = public_hidden.new_zeros((batch_size,))
    entropy_sum = public_hidden.new_zeros((batch_size,))
    subchoice_count = torch.zeros(batch_size, dtype=torch.long, device=public_hidden.device)
    rows = torch.arange(batch_size, dtype=torch.long, device=public_hidden.device)

    for subchoice in range(maximum_subchoices):
        select_now = actions.selected_lengths > subchoice
        stop_now = actions.stopped & (actions.selected_lengths == subchoice)
        active = select_now | stop_now
        stop_available = torch.full_like(active, subchoice, dtype=torch.long) >= minimum
        logits, legal = _decoder_logits(
            model,
            prefix,
            option_state,
            padded_primary_logits,
            available,
            stop_available,
            active=active,
            first_subchoice=subchoice == 0,
        )
        log_probabilities, normalized_entropy, _ = _distribution_stats(logits, legal)
        if subchoice < actions.selected_indices.shape[1]:
            selected = actions.selected_indices[:, subchoice].clamp_min(0)
        else:
            selected = torch.zeros(batch_size, dtype=torch.long, device=public_hidden.device)
        chosen = torch.where(
            select_now,
            selected,
            torch.full_like(selected, maximum_options),
        )
        if torch.any(select_now & (selected >= maximum_options)):
            raise BatchedCompoundError("replayed selected option is outside the padded option table")
        chosen_log_probability = log_probabilities[rows, chosen]
        total_log_probability = total_log_probability + torch.where(
            active, chosen_log_probability, torch.zeros_like(chosen_log_probability)
        )
        entropy_sum = entropy_sum + torch.where(
            active, normalized_entropy, torch.zeros_like(normalized_entropy)
        )
        subchoice_count = subchoice_count + active.to(torch.long)

        selecting_rows = torch.nonzero(select_now, as_tuple=False).squeeze(1)
        if selecting_rows.numel():
            selecting_options = selected[selecting_rows]
            if torch.any(~available[selecting_rows, selecting_options]):
                raise BatchedCompoundError("replayed action selects an unavailable or duplicate option")
            chosen_embeddings = padded_options[selecting_rows, selecting_options]
            updated_prefix = model.selection_gru(
                chosen_embeddings, prefix[selecting_rows]
            )
            prefix = prefix.index_copy(0, selecting_rows, updated_prefix)
            available[selecting_rows, selecting_options] = False

    if torch.any(subchoice_count <= 0):
        raise BatchedCompoundError("batched replay produced an empty action")
    normalized_entropies = entropy_sum / subchoice_count.to(entropy_sum.dtype)
    if not torch.isfinite(total_log_probability).all() or not torch.isfinite(normalized_entropies).all():
        raise BatchedCompoundError("batched compound replay produced nonfinite statistics")
    return total_log_probability, normalized_entropies
