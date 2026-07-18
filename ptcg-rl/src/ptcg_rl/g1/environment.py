from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from .actions import DeterministicFirstLegalPolicy, PolicyV1, validate_compound_action
from .models import (
    CONTRACT_VERSION,
    ContractViolation,
    EpisodeSummaryV1,
    SchemaMetadataV1,
    TransitionRecordV1,
    record_dict,
    stable_hash,
)
from .recurrent import RecurrentRequestLedger
from .semantic import OPTION_NAMES, semantic_snapshot


class EngineTransport(Protocol):
    def start(self, deck0: Sequence[int], deck1: Sequence[int]) -> Mapping[str, Any]: ...

    def select(self, original_indices: Sequence[int]) -> Mapping[str, Any]: ...

    def finish(self) -> None: ...


class EnvironmentState(StrEnum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    TERMINAL = "TERMINAL"
    FAILED = "FAILED"
    CLOSED = "CLOSED"


class FailureMode(StrEnum):
    DEVELOPMENT = "development"
    SUBMISSION = "submission"


@dataclass(frozen=True)
class FailureArtifactV1:
    schema_version: int
    failure_id: str
    created_at_utc: str
    failure_mode: str
    failure_kind: str
    exception_type: str
    message: str
    episode_id: str
    transition_id: int
    request_id: str | None
    request_sha256: str | None
    acting_player: int | None
    selection_type: int | None
    selection_context: int | None
    option_count: int
    min_count: int | None
    max_count: int | None
    submitted_original_indices: tuple[int, ...]
    engine_sha256: str
    card_data_sha256: str
    observation_schema_sha256: str
    action_schema_sha256: str


@dataclass(frozen=True)
class EpisodeResult:
    summary: EpisodeSummaryV1
    transitions: tuple[TransitionRecordV1, ...]
    failure: FailureArtifactV1 | None
    fallback_artifacts: tuple[FailureArtifactV1, ...] = ()
    action_latencies_ms: tuple[float, ...] = ()


class DevelopmentEpisodeError(RuntimeError):
    def __init__(self, result: EpisodeResult) -> None:
        self.result = result
        failure = result.failure or next(iter(result.fallback_artifacts), None)
        super().__init__(failure.message if failure is not None else "development episode failed")


def terminal_rewards(result: int) -> tuple[float, float]:
    if result == 0:
        return (1.0, -1.0)
    if result == 1:
        return (-1.0, 1.0)
    if result == 2:
        return (0.0, 0.0)
    raise ContractViolation(f"cannot reward nonterminal/unknown result {result}")


class EpisodeEnvironmentV1:
    def __init__(
        self,
        transport: EngineTransport,
        schema_metadata: SchemaMetadataV1,
        *,
        max_requests: int,
        deadline_monotonic: float,
        failure_directory: Path | None = None,
        failure_mode: FailureMode = FailureMode.DEVELOPMENT,
        failure_log_limit: int = 4,
        recurrent_ledger: RecurrentRequestLedger | None = None,
    ) -> None:
        if max_requests <= 0:
            raise ValueError("max_requests must be positive")
        if failure_log_limit < 0:
            raise ValueError("failure_log_limit must be nonnegative")
        self.transport = transport
        self.schema_metadata = schema_metadata
        self.max_requests = max_requests
        self.deadline_monotonic = deadline_monotonic
        self.failure_directory = failure_directory
        self.failure_mode = failure_mode
        self.failure_log_limit = failure_log_limit
        self.recurrent_ledger = recurrent_ledger or RecurrentRequestLedger()
        self.state = EnvironmentState.IDLE
        self.end_state: EnvironmentState | None = None
        self._failure_writes = 0

    @staticmethod
    def _policy_id(policy: PolicyV1) -> str:
        value = getattr(policy, "policy_id", type(policy).__qualname__)
        if not isinstance(value, str) or not value:
            raise ContractViolation("policy_id must be a nonempty string")
        return value

    @staticmethod
    def _reset_policy(policy: PolicyV1, episode_id: str, player: int, reason: str) -> None:
        policy.reset(episode_id, player, reason)

    def _failure(
        self,
        error: Exception,
        kind: str,
        episode_id: str,
        transition_id: int,
        request: Any = None,
        submitted: Sequence[int] = (),
    ) -> FailureArtifactV1:
        safe_error = isinstance(error, (ContractViolation, TimeoutError, ValueError, IndexError))
        message = str(error)[:500] if safe_error else "native or policy operation failed; inspect local process logs"
        request_hash = stable_hash(record_dict(request)) if request is not None else None
        artifact = FailureArtifactV1(
            schema_version=CONTRACT_VERSION,
            failure_id=uuid.uuid4().hex,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            failure_mode=self.failure_mode.value,
            failure_kind=kind,
            exception_type=type(error).__name__,
            message=message,
            episode_id=episode_id,
            transition_id=transition_id,
            request_id=getattr(request, "request_id", None),
            request_sha256=request_hash,
            acting_player=getattr(request, "acting_player", None),
            selection_type=getattr(request, "selection_type", None),
            selection_context=getattr(request, "selection_context", None),
            option_count=len(getattr(request, "options", ())),
            min_count=getattr(request, "min_count", None),
            max_count=getattr(request, "max_count", None),
            submitted_original_indices=tuple(submitted),
            engine_sha256=self.schema_metadata.engine_sha256,
            card_data_sha256=self.schema_metadata.card_data_sha256,
            observation_schema_sha256=self.schema_metadata.observation_schema_sha256,
            action_schema_sha256=self.schema_metadata.action_schema_sha256,
        )
        if self.failure_directory is not None and self._failure_writes < self.failure_log_limit:
            self.failure_directory.mkdir(parents=True, exist_ok=True)
            path = self.failure_directory / f"{episode_id}-{transition_id}-{artifact.failure_id}.failure.json"
            with path.open("x", encoding="utf-8") as destination:
                json.dump(asdict(artifact), destination, indent=2, sort_keys=True)
                destination.write("\n")
            self._failure_writes += 1
        return artifact

    def run(
        self,
        episode_id: str,
        deck0: Sequence[int],
        deck1: Sequence[int],
        policies: Mapping[int, PolicyV1],
    ) -> EpisodeResult:
        if self.state is not EnvironmentState.IDLE:
            raise RuntimeError("an environment instance runs exactly one episode")
        if set(policies) != {0, 1}:
            raise ContractViolation("one policy is required for each player")
        if policies[0] is policies[1]:
            raise ContractViolation("two players may not share one policy object")
        started = time.monotonic()
        transitions: list[TransitionRecordV1] = []
        action_latencies_ms: list[float] = []
        selection_counts: dict[str, int] = {}
        option_counts: dict[str, int] = {}
        engine_requests = meaningful = forced = multi = invalid = post_terminal = fallbacks = 0
        max_options = max_selected = 0
        first_player: int | None = None
        terminal_result: int | None = None
        failure: FailureArtifactV1 | None = None
        fallback_artifacts: list[FailureArtifactV1] = []
        previous_action_ref: str | None = None
        previous_request_ref: str | None = None
        current_request: Any = None
        submitted: tuple[int, ...] = ()
        transition_id = 0
        policy_ids = {player: self._policy_id(policy) for player, policy in policies.items()}
        try:
            for player_index in (0, 1):
                self._reset_policy(policies[player_index], episode_id, player_index, "start")
                self.recurrent_ledger.reset_episode(
                    episode_id, player_index, policy_ids[player_index], reason="start"
                )
            raw = self.transport.start(deck0, deck1)
            self.state = EnvironmentState.RUNNING
            while True:
                if time.monotonic() >= self.deadline_monotonic:
                    raise TimeoutError("G1 wall-time cap reached")
                current_request = None
                observation, request = semantic_snapshot(
                    raw,
                    episode_id,
                    transition_id,
                    self.schema_metadata.card_data_sha256,
                    previous_action_ref,
                    previous_request_ref,
                )
                current_request = request
                if observation.first_player in (0, 1):
                    first_player = observation.first_player
                if observation.terminal_result is not None:
                    self.state = EnvironmentState.TERMINAL
                    self.end_state = self.state
                    terminal_result = observation.terminal_result
                    rewards = terminal_rewards(terminal_result)
                    actor_reward = rewards[observation.acting_player]
                    transitions.append(
                        TransitionRecordV1(
                            CONTRACT_VERSION,
                            episode_id,
                            transition_id,
                            observation,
                            None,
                            None,
                            terminal_result,
                            actor_reward,
                            0,
                            self.schema_metadata,
                        )
                    )
                    break
                if request is None:
                    raise ContractViolation("ongoing episode produced no request")
                if engine_requests >= self.max_requests:
                    raise TimeoutError("G1 request cap reached")
                selection_key = str(request.selection_type)
                selection_counts[selection_key] = selection_counts.get(selection_key, 0) + 1
                for option in request.options:
                    key = OPTION_NAMES[option.option_type]
                    option_counts[key] = option_counts.get(key, 0) + 1
                max_options = max(max_options, len(request.options))
                if request.max_count > 1:
                    multi += 1
                policy = policies[request.acting_player]
                policy_id = policy_ids[request.acting_player]
                choose_native = getattr(policy, "choose_native", None)
                try:
                    action_started = time.perf_counter()
                    action = self.recurrent_ledger.dispatch(
                        episode_id,
                        request.acting_player,
                        policy_id,
                        request.selection_seq,
                        request.request_id,
                        lambda: validate_compound_action(
                            request,
                            choose_native(raw, observation, request)
                            if choose_native is not None
                            else policy.choose(observation, request),
                        ),
                    )
                    action_latencies_ms.append((time.perf_counter() - action_started) * 1_000)
                except Exception as policy_error:
                    if self.failure_mode is FailureMode.DEVELOPMENT:
                        raise
                    fallback = self._failure(
                        policy_error,
                        "policy_fallback",
                        episode_id,
                        transition_id,
                        request,
                    )
                    fallback_artifacts.append(fallback)
                    fallbacks += 1
                    action = self.recurrent_ledger.dispatch(
                        episode_id,
                        request.acting_player,
                        policy_id,
                        request.selection_seq,
                        request.request_id,
                        lambda: DeterministicFirstLegalPolicy().choose(observation, request),
                    )
                    action = validate_compound_action(request, action)
                submitted = action.submitted_original_indices
                max_selected = max(max_selected, len(submitted))
                if action.policy_loss_mask:
                    meaningful += 1
                else:
                    forced += 1
                transitions.append(
                    TransitionRecordV1(
                        CONTRACT_VERSION,
                        episode_id,
                        transition_id,
                        observation,
                        request,
                        action,
                        None,
                        None,
                        action.policy_loss_mask,
                        self.schema_metadata,
                    )
                )
                previous_action_ref = stable_hash(record_dict(action))
                previous_request_ref = stable_hash(record_dict(request))
                raw = self.transport.select(submitted)
                engine_requests += 1
                transition_id += 1
        except Exception as error:
            self.state = EnvironmentState.FAILED
            self.end_state = self.state
            invalid = int(isinstance(error, (ContractViolation, IndexError, ValueError)))
            kind = "invalid_selection" if invalid else (
                "timeout" if isinstance(error, TimeoutError) else "native_failure"
            )
            failure = self._failure(error, kind, episode_id, transition_id, current_request, submitted)
        finally:
            try:
                self.transport.finish()
            except Exception as finish_error:
                if failure is None:
                    failure = self._failure(
                        finish_error,
                        "finish_failure",
                        episode_id,
                        transition_id,
                        current_request,
                        submitted,
                    )
                    self.end_state = EnvironmentState.FAILED
            reason = "terminal" if terminal_result is not None and failure is None else "error"
            for player_index in (0, 1):
                try:
                    self._reset_policy(policies[player_index], episode_id, player_index, reason)
                finally:
                    self.recurrent_ledger.reset_episode(
                        episode_id, player_index, policy_ids[player_index], reason=reason
                    )
            self.state = EnvironmentState.CLOSED
        rewards = terminal_rewards(terminal_result) if terminal_result is not None else None
        summary = EpisodeSummaryV1(
            schema_version=CONTRACT_VERSION,
            episode_id=episode_id,
            first_player=first_player,
            terminal_result=terminal_result,
            player_rewards=rewards,
            engine_requests=engine_requests,
            meaningful_choices=meaningful,
            forced_requests=forced,
            transition_records=len(transitions),
            invalid_selections=invalid,
            post_terminal_actions=post_terminal,
            fallback_actions=fallbacks,
            failure_kind=failure.failure_kind if failure else None,
            selection_type_counts=selection_counts,
            option_type_counts=option_counts,
            multi_select_requests=multi,
            max_observed_options=max_options,
            max_observed_select_count=max_selected,
            wall_seconds=time.monotonic() - started,
            schema_metadata=self.schema_metadata,
        )
        result = EpisodeResult(
            summary, tuple(transitions), failure, tuple(fallback_artifacts),
            tuple(action_latencies_ms),
        )
        if failure is not None and self.failure_mode is FailureMode.DEVELOPMENT:
            raise DevelopmentEpisodeError(result)
        return result
