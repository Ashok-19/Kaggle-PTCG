from __future__ import annotations

import math
from dataclasses import dataclass

import torch
from torch import Tensor

from ptcg_rl.g1.actions import CompoundActionBuilder, validate_compound_action
from ptcg_rl.g1.models import ContractViolation, EngineObservationV1, SelectionRequestV1
from ptcg_rl.g2.network import PTCGPolicyV1, collate_projected
from ptcg_rl.g2.projection import project_decision
from ptcg_rl.g2.reliability import PROBABILITY_ARGUMENT
from ptcg_rl.g3.zero_update_bridge import BridgeContractError, ZeroUpdateBridgeV1


NATIVE_POLICY_ID = "e04-native-zero-update-policy-v1"


class NativeZeroUpdateError(ValueError):
    pass


@dataclass
class EngineRequestSequenceV1:
    next_value: int = 0

    def claim(self) -> int:
        if isinstance(self.next_value, bool) or not isinstance(self.next_value, int) or self.next_value < 0:
            raise NativeZeroUpdateError("engine request sequence is invalid")
        value = self.next_value
        self.next_value += 1
        return value


class NativeTraceNeuralPolicyV1:
    policy_id = NATIVE_POLICY_ID

    def __init__(
        self,
        *,
        model: PTCGPolicyV1,
        bridge: ZeroUpdateBridgeV1,
        player_index: int,
        request_sequence: EngineRequestSequenceV1,
    ) -> None:
        if player_index not in (0, 1):
            raise NativeZeroUpdateError("player index must be zero or one")
        if bridge.policy_id != self.policy_id:
            raise NativeZeroUpdateError("bridge policy identity differs")
        self.model = model
        self.bridge = bridge
        self.player_index = player_index
        self.request_sequence = request_sequence
        self._episode_uuid: str | None = None
        self._hidden: Tensor | None = None
        self._last_selection_seq: int | None = None

    @property
    def device(self) -> torch.device:
        try:
            return next(self.model.parameters()).device
        except StopIteration as error:
            raise NativeZeroUpdateError("policy model contains no parameters") from error

    def reset(self, episode_uuid: str, player_index: int, reason: str = "start") -> None:
        if player_index != self.player_index:
            raise ContractViolation("native trace policy reset player differs")
        if reason == "start":
            if self._episode_uuid is not None:
                raise ContractViolation("native trace policy start reset while active")
            self._episode_uuid = episode_uuid
            self._hidden = None
            self._last_selection_seq = None
            return
        if self._episode_uuid != episode_uuid:
            raise ContractViolation("native trace policy terminal/error reset episode differs")
        if reason not in {"terminal", "error"}:
            raise ContractViolation("native trace policy reset reason differs")
        self._episode_uuid = None
        self._hidden = None
        self._last_selection_seq = None

    def choose(
        self,
        observation: EngineObservationV1,
        request: SelectionRequestV1,
    ):
        if self._episode_uuid != request.episode_uuid or request.acting_player != self.player_index:
            raise ContractViolation("native trace policy request ownership differs")
        if self._last_selection_seq is not None and request.selection_seq <= self._last_selection_seq:
            raise ContractViolation("native trace policy request is stale or duplicate")
        self._last_selection_seq = request.selection_seq
        projection = project_decision(observation, request)
        if projection.transport.request_id != request.request_id:
            raise ContractViolation("native trace projection identity differs")

        batch = collate_projected((projection,), device=self.device)
        hidden_before = (
            torch.zeros(self.model.config.public_hidden, dtype=torch.float32, device=self.device)
            if self._hidden is None
            else self._hidden.to(device=self.device, dtype=torch.float32)
        )
        if hidden_before.shape != (self.model.config.public_hidden,) or not torch.isfinite(hidden_before).all():
            raise ContractViolation("native trace recurrent input is invalid")

        with torch.inference_mode():
            output = self.model(batch, hidden_before.unsqueeze(0))
            if (
                output.hidden.shape != (1, self.model.config.public_hidden)
                or not torch.isfinite(output.hidden).all()
                or not torch.isfinite(output.values).all()
                or not torch.isfinite(output.option_logits).all()
            ):
                raise ContractViolation("native trace model output is invalid")
            start = int(output.option_offsets[0])
            end = int(output.option_offsets[1])
            option_embeddings = output.option_embeddings[start:end]
            initial_available = batch.option_available[start:end].clone()
            available = initial_available.clone()
            initial_prefix = self.model.decoder_initial(output.hidden[0])
            prefix = initial_prefix.clone()
            builder = CompoundActionBuilder(request)
            selected_model_indices: list[int] = []
            while not builder.complete:
                logits = self.model.decoder_logits(
                    prefix,
                    option_embeddings,
                    available,
                    builder.can_stop,
                )
                if torch.isnan(logits).any() or torch.isposinf(logits).any():
                    raise ContractViolation("native trace decoder emitted invalid logits")
                probabilities = torch.softmax(logits.double(), dim=0)
                probability_values = probabilities.detach().cpu().tolist()
                if any(not math.isfinite(value) or value < 0 for value in probability_values):
                    raise ContractViolation("native trace decoder distribution is invalid")
                probability_kwargs = {PROBABILITY_ARGUMENT: probability_values}
                choice = int(torch.argmax(probabilities).item())
                if choice == len(request.options):
                    builder.stop(**probability_kwargs)
                else:
                    builder.choose(choice, **probability_kwargs)
                    selected_model_indices.append(choice)
                    available[choice] = False
                    prefix = self.model.decoder_advance(prefix, option_embeddings[choice])
            action = validate_compound_action(request, builder.build())
            hidden_after = output.hidden[0].detach().clone()
            try:
                self.bridge.record_decision(
                    episode_id=request.episode_uuid,
                    player=self.player_index,
                    engine_request_seq=self.request_sequence.claim(),
                    request_id=f"{request.episode_uuid}:{request.request_id}",
                    selected_indices=tuple(selected_model_indices),
                    stopped=action.stopped_early,
                    initial_prefix=initial_prefix,
                    option_embeddings=option_embeddings,
                    available_mask=initial_available,
                    minimum_count=request.min_count,
                    maximum_count=request.max_count,
                    old_log_probability=action.log_probability_sum,
                    hidden_before=hidden_before,
                    hidden_after=hidden_after,
                    reported_policy_version=self.bridge.policy_version,
                    decoder_logits=self.model.decoder_logits,
                    decoder_advance=self.model.decoder_advance,
                    fallback_used=False,
                )
            except BridgeContractError as error:
                raise ContractViolation(f"native trace bridge rejected decision: {error}") from error
            self._hidden = hidden_after
            return action
