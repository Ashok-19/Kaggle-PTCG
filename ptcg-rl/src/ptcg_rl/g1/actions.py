from __future__ import annotations

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
    result = tuple(indices)
    legal = {option.original_index for option in request.options if option.available}
    if not request.min_count <= len(result) <= request.max_count:
        raise ContractViolation("submitted selection count violates request bounds")
    if len(result) != len(set(result)):
        raise ContractViolation("submitted engine indices must be unique")
    if any(index not in legal for index in result):
        raise ContractViolation("submitted index is not in the unpermuted legal request")
    return result


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
        self._stopped = False

    @property
    def chosen_count(self) -> int:
        return len(self._steps)

    @property
    def complete(self) -> bool:
        return self._stopped or self.chosen_count == self.model_request.max_count

    @property
    def can_stop(self) -> bool:
        return self.chosen_count >= self.model_request.min_count

    def choose(self, model_index: int, log_probability: float | None = None) -> None:
        if self.complete:
            raise ContractViolation("compound action is already complete")
        if not 0 <= model_index < len(self._available) or not self._available[model_index]:
            raise ContractViolation("model selected a masked or nonexistent option")
        option = self.model_request.options[model_index]
        self._steps.append(
            SubSelectionV1(
                substep=len(self._steps),
                model_order_original_indices=tuple(
                    item.original_index for item in self.model_request.options
                ),
                available_model_mask=tuple(self._available),
                chosen_model_index=model_index,
                chosen_semantic_fingerprint=option.semantic_fingerprint,
                original_index=option.original_index,
                log_probability=log_probability,
            )
        )
        self._available[model_index] = False

    def stop(self) -> None:
        if self.complete:
            return
        if not self.can_stop:
            raise ContractViolation("STOP is illegal before min_count")
        self._stopped = True

    def build(self) -> CompoundActionV1:
        if not self.complete:
            raise ContractViolation("compound action must explicitly STOP or reach max_count")
        submitted = validate_original_indices(
            self.original_request, [step.original_index for step in self._steps]
        )
        probabilities = [step.log_probability for step in self._steps]
        log_probability_sum = (
            sum(value for value in probabilities if value is not None)
            if probabilities and all(value is not None for value in probabilities)
            else None
        )
        return CompoundActionV1(
            schema_version=CONTRACT_VERSION,
            request_id=self.original_request.request_id,
            steps=tuple(self._steps),
            submitted_original_indices=submitted,
            stopped_early=len(submitted) < self.original_request.max_count,
            policy_loss_mask=0 if self.original_request.has_only_one_outcome else 1,
            log_probability_sum=log_probability_sum,
        )


class PolicyV1(Protocol):
    def reset(self, battle_id: str, player_index: int) -> None: ...

    def choose(
        self, observation: EngineObservationV1, request: SelectionRequestV1
    ) -> CompoundActionV1: ...


class DeterministicFirstLegalPolicy:
    def reset(self, battle_id: str, player_index: int) -> None:
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
    def __init__(self, seed: int = 0) -> None:
        self.random = random.Random(seed)

    def reset(self, battle_id: str, player_index: int) -> None:
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
