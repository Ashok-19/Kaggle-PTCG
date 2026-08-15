from __future__ import annotations

import math

import torch
from torch import Tensor

from ptcg_rl.g1.actions import CompoundActionBuilder, validate_compound_action
from ptcg_rl.g1.models import CompoundActionV1, ContractViolation, EngineObservationV1, SelectionRequestV1
from ptcg_rl.g2.network import PTCGPolicyV1, collate_projected
from ptcg_rl.g2.projection import project_decision


class GreedyRecurrentNeuralPolicyV1:
    """Direct greedy recurrent policy for native competence evaluation.

    This adapter deliberately uses the same semantic projection, legal-option mask,
    recurrent hidden state, and autoregressive compound decoder as training. It
    performs no fallback: an invalid neural action fails the evaluation game.
    """

    policy_id = "bc-greedy-recurrent-neural-v1"

    def __init__(self, model: PTCGPolicyV1, player_index: int) -> None:
        if player_index not in (0, 1):
            raise ValueError("player_index must be zero or one")
        self.model = model
        self.player_index = player_index
        self._episode_uuid: str | None = None
        self._hidden: Tensor | None = None
        self._last_selection_seq: int | None = None

    @property
    def device(self) -> torch.device:
        try:
            return next(self.model.parameters()).device
        except StopIteration as error:
            raise ContractViolation("neural policy model contains no parameters") from error

    def reset(self, episode_uuid: str, player_index: int, reason: str = "start") -> None:
        if player_index != self.player_index:
            raise ContractViolation("neural policy reset player differs")
        if reason == "start":
            if self._episode_uuid is not None:
                raise ContractViolation("neural policy start reset while episode is active")
            self._episode_uuid = episode_uuid
            self._hidden = None
            self._last_selection_seq = None
            return
        if self._episode_uuid != episode_uuid:
            raise ContractViolation("neural policy terminal/error reset episode differs")
        if reason not in {"terminal", "error"}:
            raise ContractViolation("unsupported neural policy reset reason")
        self._episode_uuid = None
        self._hidden = None
        self._last_selection_seq = None

    def choose(
        self,
        observation: EngineObservationV1,
        request: SelectionRequestV1,
    ) -> CompoundActionV1:
        if self._episode_uuid != request.episode_uuid:
            raise ContractViolation("neural policy request episode differs")
        if request.acting_player != self.player_index:
            raise ContractViolation("neural policy request player differs")
        if self._last_selection_seq is not None and request.selection_seq <= self._last_selection_seq:
            raise ContractViolation("neural policy received stale or duplicate request")
        self._last_selection_seq = request.selection_seq

        projected = project_decision(observation, request)
        batch = collate_projected((projected,), device=self.device)
        hidden = (
            self.model.initial_hidden(1, self.device)
            if self._hidden is None
            else self._hidden.unsqueeze(0).to(device=self.device, dtype=torch.float32)
        )
        with torch.inference_mode():
            output = self.model(batch, hidden)
            if not torch.isfinite(output.hidden).all() or not torch.isfinite(output.values).all():
                raise ContractViolation("neural policy emitted nonfinite recurrent/value output")
            start = int(output.option_offsets[0])
            end = int(output.option_offsets[1])
            option_embeddings = output.option_embeddings[start:end]
            available = batch.option_available[start:end].clone()
            prefix = self.model.decoder_initial(output.hidden[0])
            builder = CompoundActionBuilder(request)
            first_subchoice = True
            while not builder.complete:
                if first_subchoice:
                    logits = self.model.decoder_first_logits(
                        prefix,
                        output.option_logits[start:end],
                        available,
                        builder.can_stop,
                    )
                else:
                    logits = self.model.decoder_logits(
                        prefix,
                        option_embeddings,
                        available,
                        builder.can_stop,
                    )
                if torch.isnan(logits).any() or torch.isposinf(logits).any():
                    raise ContractViolation("neural policy decoder emitted invalid logits")
                choice = int(torch.argmax(logits).item())
                if choice == len(request.options):
                    builder.stop()
                else:
                    if choice < 0 or choice >= len(request.options) or not bool(available[choice]):
                        raise ContractViolation("neural policy decoder selected an illegal option")
                    builder.choose(choice)
                    available[choice] = False
                    prefix = self.model.decoder_advance(prefix, option_embeddings[choice])
                first_subchoice = False
            action = validate_compound_action(request, builder.build())
            hidden_after = output.hidden[0].detach().clone()
            if hidden_after.shape != (self.model.config.public_hidden,) or not torch.isfinite(
                hidden_after
            ).all():
                raise ContractViolation("neural policy recurrent state is invalid")
            self._hidden = hidden_after
            return action


def candidate_score(terminal_result: int, candidate_player: int) -> float:
    if candidate_player not in (0, 1):
        raise ValueError("candidate player must be zero or one")
    if terminal_result == candidate_player:
        return 1.0
    if terminal_result == 2:
        return 0.5
    if terminal_result == 1 - candidate_player:
        return 0.0
    raise ValueError(f"unsupported terminal result {terminal_result}")


def normal_score_interval(scores: list[float]) -> tuple[float, float]:
    if not scores:
        return (0.0, 1.0)
    mean = sum(scores) / len(scores)
    if len(scores) == 1:
        return (mean, mean)
    variance = sum((value - mean) ** 2 for value in scores) / (len(scores) - 1)
    half = 1.96 * math.sqrt(variance / len(scores))
    return (max(0.0, mean - half), min(1.0, mean + half))
