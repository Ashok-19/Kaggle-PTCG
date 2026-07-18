from __future__ import annotations

import math
import random
from dataclasses import replace
from typing import Protocol, Sequence

from .models import (
    CONTRACT_VERSION,
    CompoundActionV1,
    ContractViolation,
    EngineObservationV1,
    SelectionRequestV1,
    SubSelectionV1,
)


def permute_request(request: SelectionRequestV1, permutation: Sequence[int]) -> SelectionRequestV1:
    if sorted(permutation) != list(range(len(request.options))):
        raise ContractViolation("permutation must contain every model option exactly once")
    return replace(request, options=tuple(request.options[index] for index in permutation))


def validate_original_indices(request: SelectionRequestV1, indices: Sequence[int]) -> tuple[int, ...]:
    if any(isinstance(index, bool) or not isinstance(index, int) for index in indices):
        raise ContractViolation("submitted engine indices must be integers")
    result = tuple(indices)
    legal = {option.original_index for option in request.options if option.available}
    if not request.min_count <= len(result) <= request.max_count:
        raise ContractViolation("submitted selection count violates request bounds")
    if len(result) != len(set(result)):
        raise ContractViolation("submitted engine indices must be unique")
    if any(index not in legal for index in result):
        raise ContractViolation("submitted index is not in the unpermuted legal request")
    return result


class DeterministicReferenceScorer:
    """Uniform masked scorer used only to prove decoder trace arithmetic."""

    @staticmethod
    def distribution(legal_token_mask: Sequence[bool]) -> tuple[float, ...]:
        count = sum(bool(value) for value in legal_token_mask)
        if count == 0:
            raise ContractViolation("decoder has no legal token")
        probability = 1.0 / count
        return tuple(probability if legal else 0.0 for legal in legal_token_mask)


def _validate_distribution(
    probabilities: Sequence[float], legal_mask: Sequence[bool]
) -> tuple[float, ...]:
    values = tuple(float(value) for value in probabilities)
    if len(values) != len(legal_mask):
        raise ContractViolation("decoder distribution length differs from legal-token mask")
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise ContractViolation("decoder distribution contains an invalid probability")
    if any(value != 0.0 for value, legal in zip(values, legal_mask, strict=True) if not legal):
        raise ContractViolation("decoder distribution assigns mass to a masked token")
    if not math.isclose(sum(values), 1.0, rel_tol=0, abs_tol=1e-12):
        raise ContractViolation("decoder distribution is not normalized")
    return values


class CompoundActionBuilder:
    def __init__(
        self, model_request: SelectionRequestV1, original_request: SelectionRequestV1 | None = None
    ) -> None:
        self.model_request = model_request
        self.original_request = original_request or model_request
        if {item.original_index for item in model_request.options} != {
            item.original_index for item in self.original_request.options
        }:
            raise ContractViolation("model and original requests do not contain the same options")
        self._available = [option.available for option in model_request.options]
        self._steps: list[SubSelectionV1] = []
        self._chosen: list[int] = []
        self._stopped = False

    @property
    def chosen_count(self) -> int:
        return len(self._chosen)

    @property
    def complete(self) -> bool:
        return self._stopped or self.chosen_count == self.model_request.max_count

    @property
    def can_stop(self) -> bool:
        return (
            self.chosen_count >= self.model_request.min_count
            and self.chosen_count < self.model_request.max_count
        )

    @property
    def legal_token_mask(self) -> tuple[bool, ...]:
        option_mask = tuple(value and not self.complete for value in self._available)
        return (*option_mask, self.can_stop and not self.complete)

    def _probabilities(self, supplied: Sequence[float] | None) -> tuple[float, ...]:
        values = supplied or DeterministicReferenceScorer.distribution(self.legal_token_mask)
        return _validate_distribution(values, self.legal_token_mask)

    def choose(
        self, model_index: int, *, token_probabilities: Sequence[float] | None = None
    ) -> None:
        if self.complete:
            raise ContractViolation("compound action is already complete")
        if isinstance(model_index, bool) or not isinstance(model_index, int):
            raise ContractViolation("model index must be an integer")
        if not 0 <= model_index < len(self._available) or not self._available[model_index]:
            raise ContractViolation("model selected a masked or nonexistent option")
        probabilities = self._probabilities(token_probabilities)
        probability = probabilities[model_index]
        if probability <= 0:
            raise ContractViolation("chosen decoder token has zero probability")
        option = self.model_request.options[model_index]
        self._steps.append(
            SubSelectionV1(
                substep=len(self._steps),
                model_order_original_indices=tuple(
                    item.original_index for item in self.model_request.options
                ),
                available_model_mask=tuple(self._available),
                stop_available=self.can_stop,
                chosen_prefix_original_indices=tuple(self._chosen),
                chosen_token="OPTION",
                chosen_model_index=model_index,
                chosen_semantic_fingerprint=option.semantic_fingerprint,
                original_index=option.original_index,
                token_probabilities=probabilities,
                log_probability=math.log(probability),
            )
        )
        self._chosen.append(option.original_index)
        self._available[model_index] = False

    def stop(self, *, token_probabilities: Sequence[float] | None = None) -> None:
        if self.complete:
            if self.chosen_count == self.model_request.max_count:
                return
            raise ContractViolation("compound action is already complete")
        if not self.can_stop:
            raise ContractViolation("STOP is illegal before min_count or at max_count")
        probabilities = self._probabilities(token_probabilities)
        probability = probabilities[-1]
        if probability <= 0:
            raise ContractViolation("chosen STOP token has zero probability")
        self._steps.append(
            SubSelectionV1(
                substep=len(self._steps),
                model_order_original_indices=tuple(
                    item.original_index for item in self.model_request.options
                ),
                available_model_mask=tuple(self._available),
                stop_available=True,
                chosen_prefix_original_indices=tuple(self._chosen),
                chosen_token="STOP",
                chosen_model_index=None,
                chosen_semantic_fingerprint=None,
                original_index=None,
                token_probabilities=probabilities,
                log_probability=math.log(probability),
            )
        )
        self._stopped = True

    def build(self) -> CompoundActionV1:
        if not self.complete:
            raise ContractViolation("compound action must explicitly STOP or reach max_count")
        submitted = validate_original_indices(self.original_request, self._chosen)
        action = CompoundActionV1(
            schema_version=CONTRACT_VERSION,
            episode_uuid=self.original_request.episode_uuid,
            acting_player=self.original_request.acting_player,
            selection_seq=self.original_request.selection_seq,
            request_id=self.original_request.request_id,
            steps=tuple(self._steps),
            submitted_original_indices=submitted,
            stopped_early=self._stopped,
            policy_loss_mask=0 if self.original_request.has_only_one_outcome else 1,
            log_probability_sum=sum(step.log_probability for step in self._steps),
        )
        return validate_compound_action(self.original_request, action)


def validate_compound_action(
    request: SelectionRequestV1, action: CompoundActionV1
) -> CompoundActionV1:
    if action.schema_version != CONTRACT_VERSION:
        raise ContractViolation("action schema version differs from adapter contract")
    if action.episode_uuid != request.episode_uuid:
        raise ContractViolation("action episode identity differs from request")
    if action.acting_player != request.acting_player:
        raise ContractViolation("action player identity differs from request")
    if action.selection_seq != request.selection_seq:
        raise ContractViolation("action selection sequence differs from request")
    if action.request_id != request.request_id:
        raise ContractViolation("action request identity differs from request")

    option_by_original = {option.original_index: option for option in request.options}
    expected_originals = set(option_by_original)
    available: dict[int, bool] | None = None
    model_order: tuple[int, ...] | None = None
    chosen: list[int] = []
    stopped = False
    logp = 0.0
    for substep, step in enumerate(action.steps):
        if stopped:
            raise ContractViolation("decoder trace continues after STOP")
        if step.substep != substep:
            raise ContractViolation("decoder substeps are not contiguous")
        if set(step.model_order_original_indices) != expected_originals or len(
            step.model_order_original_indices
        ) != len(expected_originals):
            raise ContractViolation("decoder model order is not a full option permutation")
        if model_order is None:
            model_order = step.model_order_original_indices
            available = {
                original: option_by_original[original].available for original in model_order
            }
        elif step.model_order_original_indices != model_order:
            raise ContractViolation("decoder model order changed within one compound action")
        assert available is not None and model_order is not None
        expected_mask = tuple(available[original] for original in model_order)
        can_stop = request.min_count <= len(chosen) < request.max_count
        if step.available_model_mask != expected_mask:
            raise ContractViolation("decoder option mask does not match chosen prefix")
        if step.stop_available != can_stop:
            raise ContractViolation("decoder STOP mask does not match request bounds")
        if step.chosen_prefix_original_indices != tuple(chosen):
            raise ContractViolation("decoder state prefix is stale or forged")
        legal_mask = (*expected_mask, can_stop)
        probabilities = _validate_distribution(step.token_probabilities, legal_mask)
        if step.chosen_token == "OPTION":
            index = step.chosen_model_index
            if index is None or not 0 <= index < len(model_order) or not expected_mask[index]:
                raise ContractViolation("decoder chose a masked or nonexistent option")
            original = model_order[index]
            option = option_by_original[original]
            if step.original_index != original:
                raise ContractViolation("decoder original index does not match model permutation")
            if step.chosen_semantic_fingerprint != option.semantic_fingerprint:
                raise ContractViolation("decoder option semantic fingerprint is stale")
            probability = probabilities[index]
            chosen.append(original)
            available[original] = False
        elif step.chosen_token == "STOP":
            if step.chosen_model_index is not None or step.original_index is not None:
                raise ContractViolation("STOP must not carry an option index")
            if step.chosen_semantic_fingerprint is not None or not can_stop:
                raise ContractViolation("STOP trace is malformed or illegal")
            probability = probabilities[-1]
            stopped = True
        else:
            raise ContractViolation("unknown decoder token")
        expected_logp = math.log(probability) if probability > 0 else float("-inf")
        if not math.isclose(step.log_probability, expected_logp, rel_tol=0, abs_tol=1e-12):
            raise ContractViolation("decoder log-probability does not match retained distribution")
        logp += expected_logp

    submitted = validate_original_indices(request, chosen)
    if action.submitted_original_indices != submitted:
        raise ContractViolation("submitted indices differ from the validated decoder trace")
    if action.stopped_early != stopped:
        raise ContractViolation("action STOP flag differs from decoder trace")
    if not stopped and len(chosen) != request.max_count:
        raise ContractViolation("decoder trace neither STOPs nor reaches max_count")
    expected_loss_mask = 0 if request.has_only_one_outcome else 1
    if action.policy_loss_mask != expected_loss_mask:
        raise ContractViolation("policy-loss mask differs from request outcome count")
    if not math.isclose(action.log_probability_sum, logp, rel_tol=0, abs_tol=1e-12):
        raise ContractViolation("compound log-probability differs from decoder trace sum")
    return action


class PolicyV1(Protocol):
    policy_id: str

    def reset(self, episode_uuid: str, player_index: int, reason: str = "start") -> None: ...

    def choose(
        self, observation: EngineObservationV1, request: SelectionRequestV1
    ) -> CompoundActionV1: ...


class DeterministicFirstLegalPolicy:
    policy_id = "deterministic-first-legal-v2"

    def reset(self, episode_uuid: str, player_index: int, reason: str = "start") -> None:
        return None

    def choose(
        self, observation: EngineObservationV1, request: SelectionRequestV1
    ) -> CompoundActionV1:
        builder = CompoundActionBuilder(request)
        for index, option in enumerate(request.options):
            if builder.complete:
                break
            if option.available:
                builder.choose(index)
        if not builder.complete:
            builder.stop()
        return builder.build()


class RandomLegalPolicy:
    policy_id = "random-legal-v2"

    def __init__(self, seed: int = 0) -> None:
        self.random = random.Random(seed)

    def reset(self, episode_uuid: str, player_index: int, reason: str = "start") -> None:
        return None

    def choose(
        self, observation: EngineObservationV1, request: SelectionRequestV1
    ) -> CompoundActionV1:
        builder = CompoundActionBuilder(request)
        target_count = self.random.randint(request.min_count, request.max_count)
        candidates = [index for index, option in enumerate(request.options) if option.available]
        self.random.shuffle(candidates)
        for index in candidates[:target_count]:
            builder.choose(index)
        if not builder.complete:
            builder.stop()
        return builder.build()
