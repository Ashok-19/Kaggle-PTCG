from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from enum import Enum
from typing import Any, Callable, Mapping, Sequence

import torch
from torch import Tensor

from ptcg_rl.g3.ppo import (
    CompoundActionV1,
    PPOContractError,
    RolloutEventV1,
    is_forced_compound_action,
    replay_compound_action,
    split_recurrent_rollout,
    verify_probability_replay,
)


BRIDGE_SCHEMA_VERSION = 1
RELIABILITY_KEYS = (
    "invalid_actions",
    "fallback_actions",
    "stale_requests",
    "duplicate_requests",
    "out_of_order_requests",
    "policy_lag",
    "recurrent_owner_failures",
    "replay_mismatches",
    "nonfinite_values",
    "terminal_errors",
    "worker_deaths",
    "optimizer_attempts",
)


class BridgeContractError(ValueError):
    pass


class TruncationClassV1(str, Enum):
    WORKER_DEATH = "WORKER_DEATH"
    WALL_TIME = "WALL_TIME"
    ENGINE_ERROR = "ENGINE_ERROR"
    EXTERNAL_CANCEL = "EXTERNAL_CANCEL"


DecoderLogits = Callable[[Tensor, Tensor, Tensor, bool], Tensor]
DecoderAdvance = Callable[[Tensor, Tensor], Tensor]


@dataclass(frozen=True)
class DecisionTraceV1:
    engine_request_seq: int
    request_id: str
    player: int
    owner_sequence: int
    forced: bool
    selected_indices: tuple[int, ...]
    stopped: bool
    old_log_probability: float
    replayed_log_probability: float
    replay_absolute_error: float
    hidden_before: tuple[float, ...]
    hidden_after: tuple[float, ...]
    policy_version: int


@dataclass
class _OwnerStateV1:
    next_sequence: int
    hidden: tuple[float, ...] | None
    traces: list[DecisionTraceV1]
    events: list[RolloutEventV1]


@dataclass(frozen=True)
class PlayerBoundaryV1:
    player: int
    terminal: bool
    truncation: bool
    terminal_reward: int | None
    truncation_class: str | None


@dataclass
class _EpisodeStateV1:
    owners: dict[int, _OwnerStateV1]
    player_boundaries: dict[int, PlayerBoundaryV1]
    closed: bool = False
    boundary: str | None = None
    terminal_result: int | None = None
    truncation_class: str | None = None


class ZeroUpdateBridgeV1:
    """Fail-closed, zero-optimizer bridge for real CABT trajectory qualification.

    The bridge owns transport sequencing, per-player recurrent ownership, exact
    compound-action probability replay and both-player episode boundaries. It
    deliberately contains no optimizer and cannot advance a policy version.
    """

    def __init__(
        self,
        *,
        policy_id: str,
        policy_version: int = 0,
        maximum_replay_error: float = 1e-5,
    ) -> None:
        if not isinstance(policy_id, str) or not policy_id:
            raise BridgeContractError("policy_id must be a nonempty string")
        if isinstance(policy_version, bool) or not isinstance(policy_version, int) or policy_version < 0:
            raise BridgeContractError("policy_version must be a nonnegative integer")
        if not math.isfinite(maximum_replay_error) or maximum_replay_error < 0:
            raise BridgeContractError("maximum replay error must be finite and nonnegative")
        self.policy_id = policy_id
        self.policy_version = policy_version
        self.maximum_replay_error = float(maximum_replay_error)
        self.optimizer_steps = 0
        self.next_engine_request_seq = 0
        self.seen_request_ids: set[str] = set()
        self.episodes: dict[str, _EpisodeStateV1] = {}
        self.reliability = {key: 0 for key in RELIABILITY_KEYS}

    def _fail(self, counter: str, message: str) -> None:
        self.reliability[counter] += 1
        raise BridgeContractError(message)

    @staticmethod
    def _hidden(value: Sequence[float] | Tensor, name: str) -> tuple[float, ...]:
        if isinstance(value, Tensor):
            tensor = value.detach().cpu().reshape(-1)
            if not torch.isfinite(tensor).all():
                raise BridgeContractError(f"{name} contains NaN or infinity")
            result = tuple(float(item) for item in tensor.tolist())
        else:
            try:
                result = tuple(float(item) for item in value)
            except (TypeError, ValueError) as error:
                raise BridgeContractError(f"{name} must be a numeric sequence") from error
            if not result:
                raise BridgeContractError(f"{name} must be nonempty")
            if any(not math.isfinite(item) for item in result):
                raise BridgeContractError(f"{name} contains NaN or infinity")
        return result

    def start_episode(self, episode_id: str) -> None:
        if not isinstance(episode_id, str) or not episode_id:
            raise BridgeContractError("episode_id must be a nonempty string")
        if episode_id in self.episodes:
            self._fail("duplicate_requests", "episode already exists")
        self.episodes[episode_id] = _EpisodeStateV1(
            owners={
                0: _OwnerStateV1(0, None, [], []),
                1: _OwnerStateV1(0, None, [], []),
            },
            player_boundaries={},
        )

    def _open_episode(self, episode_id: str) -> _EpisodeStateV1:
        episode = self.episodes.get(episode_id)
        if episode is None:
            self._fail("recurrent_owner_failures", "episode has not been started")
        assert episode is not None
        if episode.closed:
            self._fail("terminal_errors", "cannot record after episode boundary")
        return episode

    def record_decision(
        self,
        *,
        episode_id: str,
        player: int,
        engine_request_seq: int,
        request_id: str,
        selected_indices: Sequence[int],
        stopped: bool,
        initial_prefix: Tensor,
        option_embeddings: Tensor,
        available_mask: Tensor,
        minimum_count: int,
        maximum_count: int,
        old_log_probability: float,
        hidden_before: Sequence[float] | Tensor,
        hidden_after: Sequence[float] | Tensor,
        reported_policy_version: int,
        decoder_logits: DecoderLogits,
        decoder_advance: DecoderAdvance,
        fallback_used: bool = False,
    ) -> DecisionTraceV1:
        episode = self._open_episode(episode_id)
        if player not in (0, 1):
            self._fail("recurrent_owner_failures", "player must be zero or one")
        if not isinstance(request_id, str) or not request_id:
            self._fail("invalid_actions", "request_id must be nonempty")
        if request_id in self.seen_request_ids:
            self._fail("duplicate_requests", "duplicate request_id")
        if isinstance(engine_request_seq, bool) or not isinstance(engine_request_seq, int):
            self._fail("out_of_order_requests", "engine request sequence must be an integer")
        if engine_request_seq < self.next_engine_request_seq:
            self._fail("stale_requests", "stale engine request sequence")
        if engine_request_seq > self.next_engine_request_seq:
            self._fail("out_of_order_requests", "out-of-order engine request sequence")
        if reported_policy_version != self.policy_version:
            self._fail("policy_lag", "reported policy version differs from bridge version")
        if fallback_used:
            self._fail("fallback_actions", "fallback actions are forbidden")
        if not isinstance(stopped, bool):
            self._fail("invalid_actions", "stopped must be boolean")
        if any(isinstance(index, bool) or not isinstance(index, int) for index in selected_indices):
            self._fail("invalid_actions", "selected indices must be integers")
        selected = tuple(selected_indices)
        if len(selected) != len(set(selected)):
            self._fail("invalid_actions", "duplicate action index")
        if not isinstance(old_log_probability, (int, float)) or not math.isfinite(
            float(old_log_probability)
        ):
            self._fail("nonfinite_values", "old compound log-probability must be finite")
        try:
            before = self._hidden(hidden_before, "hidden_before")
            after = self._hidden(hidden_after, "hidden_after")
        except BridgeContractError as error:
            self._fail("nonfinite_values", str(error))
        if len(before) != len(after):
            self._fail("recurrent_owner_failures", "recurrent hidden widths differ")

        owner = episode.owners[player]
        reset_before = owner.hidden is None
        if owner.hidden is not None:
            observed = torch.tensor(before, dtype=torch.float64)
            expected = torch.tensor(owner.hidden, dtype=torch.float64)
            if observed.shape != expected.shape or not torch.allclose(
                observed, expected, rtol=0.0, atol=1e-7
            ):
                self._fail("recurrent_owner_failures", "recurrent hidden ownership or continuity differs")

        try:
            action = CompoundActionV1(selected, stopped)
            replay = replay_compound_action(
                initial_prefix=initial_prefix,
                option_embeddings=option_embeddings,
                available_mask=available_mask,
                action=action,
                minimum_count=minimum_count,
                maximum_count=maximum_count,
                decoder_logits=decoder_logits,
                decoder_advance=decoder_advance,
            )
            check = verify_probability_replay(
                torch.tensor([float(old_log_probability)], dtype=torch.float64),
                replay.log_probability.detach().reshape(1).to(dtype=torch.float64, device="cpu"),
                maximum_absolute_error=self.maximum_replay_error,
                maximum_ratio_error=self.maximum_replay_error,
            )
        except PPOContractError as error:
            self._fail("replay_mismatches", str(error))
        replayed = float(replay.log_probability.detach().cpu())
        if not math.isfinite(replayed):
            self._fail("nonfinite_values", "replayed compound log-probability is nonfinite")

        forced = is_forced_compound_action(
            int(available_mask.sum().item()), minimum_count, maximum_count
        )
        trace = DecisionTraceV1(
            engine_request_seq=engine_request_seq,
            request_id=request_id,
            player=player,
            owner_sequence=owner.next_sequence,
            forced=forced,
            selected_indices=selected,
            stopped=stopped,
            old_log_probability=float(old_log_probability),
            replayed_log_probability=replayed,
            replay_absolute_error=check.maximum_log_probability_absolute_error,
            hidden_before=before,
            hidden_after=after,
            policy_version=self.policy_version,
        )
        owner.traces.append(trace)
        owner.events.append(
            RolloutEventV1(
                episode_id=episode_id,
                player=player,
                policy_id=self.policy_id,
                policy_version=self.policy_version,
                selection_seq=owner.next_sequence,
                forced=forced,
                reset_before=reset_before,
            )
        )
        owner.next_sequence += 1
        owner.hidden = after
        self.seen_request_ids.add(request_id)
        self.next_engine_request_seq += 1
        return trace

    def _attach_boundary(
        self,
        episode_id: str,
        *,
        terminal: bool,
        truncation: bool,
        terminal_rewards: tuple[int, int] | None = None,
        truncation_class: TruncationClassV1 | None = None,
    ) -> _EpisodeStateV1:
        episode = self._open_episode(episode_id)
        if terminal == truncation:
            self._fail("terminal_errors", "episode boundary must be terminal or truncation")
        if terminal and terminal_rewards is None:
            self._fail("terminal_errors", "terminal boundary requires both player rewards")
        if truncation and truncation_class is None:
            self._fail("terminal_errors", "truncation boundary requires a classification")
        boundaries: dict[int, PlayerBoundaryV1] = {}
        for player in (0, 1):
            owner = episode.owners[player]
            if owner.events:
                owner.events[-1] = replace(
                    owner.events[-1], terminal=terminal, truncation=truncation
                )
            boundaries[player] = PlayerBoundaryV1(
                player=player,
                terminal=terminal,
                truncation=truncation,
                terminal_reward=(
                    terminal_rewards[player] if terminal_rewards is not None else None
                ),
                truncation_class=(
                    truncation_class.value if truncation_class is not None else None
                ),
            )
        episode.player_boundaries = boundaries
        episode.closed = True
        return episode

    def close_terminal_episode(self, episode_id: str, terminal_result_for_player_zero: int) -> tuple[int, int]:
        if terminal_result_for_player_zero not in (-1, 0, 1):
            self._fail("terminal_errors", "terminal result must be -1, 0 or 1")
        rewards = (terminal_result_for_player_zero, -terminal_result_for_player_zero)
        episode = self._attach_boundary(
            episode_id,
            terminal=True,
            truncation=False,
            terminal_rewards=rewards,
        )
        episode.boundary = "TERMINAL"
        episode.terminal_result = terminal_result_for_player_zero
        return rewards

    def close_truncated_episode(
        self, episode_id: str, classification: TruncationClassV1
    ) -> None:
        if not isinstance(classification, TruncationClassV1):
            self._fail("terminal_errors", "truncation classification is invalid")
        episode = self._attach_boundary(
            episode_id,
            terminal=False,
            truncation=True,
            truncation_class=classification,
        )
        episode.boundary = "TRUNCATION"
        episode.truncation_class = classification.value
        if classification is TruncationClassV1.WORKER_DEATH:
            self.reliability["worker_deaths"] += 1

    def attempt_optimizer_step(self) -> None:
        self.reliability["optimizer_attempts"] += 1
        raise BridgeContractError("zero-update bridge cannot execute an optimizer step")

    def state_dict(self) -> dict[str, Any]:
        episodes: dict[str, Any] = {}
        for episode_id, episode in sorted(self.episodes.items()):
            owners: dict[str, Any] = {}
            for player, owner in sorted(episode.owners.items()):
                owners[str(player)] = {
                    "next_sequence": owner.next_sequence,
                    "hidden": None if owner.hidden is None else list(owner.hidden),
                    "traces": [asdict(trace) for trace in owner.traces],
                    "events": [asdict(event) for event in owner.events],
                }
            episodes[episode_id] = {
                "owners": owners,
                "player_boundaries": {
                    str(player): asdict(boundary)
                    for player, boundary in sorted(episode.player_boundaries.items())
                },
                "closed": episode.closed,
                "boundary": episode.boundary,
                "terminal_result": episode.terminal_result,
                "truncation_class": episode.truncation_class,
            }
        return {
            "schema_version": BRIDGE_SCHEMA_VERSION,
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "maximum_replay_error": self.maximum_replay_error,
            "optimizer_steps": self.optimizer_steps,
            "next_engine_request_seq": self.next_engine_request_seq,
            "seen_request_ids": sorted(self.seen_request_ids),
            "reliability": dict(self.reliability),
            "episodes": episodes,
        }

    @classmethod
    def from_state_dict(cls, value: Mapping[str, Any]) -> ZeroUpdateBridgeV1:
        if value.get("schema_version") != BRIDGE_SCHEMA_VERSION:
            raise BridgeContractError("unsupported bridge checkpoint schema")
        bridge = cls(
            policy_id=str(value.get("policy_id", "")),
            policy_version=int(value.get("policy_version", -1)),
            maximum_replay_error=float(value.get("maximum_replay_error", -1.0)),
        )
        if value.get("optimizer_steps") != 0:
            raise BridgeContractError("bridge checkpoint contains optimizer steps")
        bridge.next_engine_request_seq = int(value.get("next_engine_request_seq", -1))
        if bridge.next_engine_request_seq < 0:
            raise BridgeContractError("bridge checkpoint request sequence is invalid")
        seen = value.get("seen_request_ids")
        if not isinstance(seen, list) or any(not isinstance(item, str) or not item for item in seen):
            raise BridgeContractError("bridge checkpoint request IDs are invalid")
        bridge.seen_request_ids = set(seen)
        reliability = value.get("reliability")
        if not isinstance(reliability, Mapping) or set(reliability) != set(RELIABILITY_KEYS):
            raise BridgeContractError("bridge checkpoint reliability counters differ")
        bridge.reliability = {key: int(reliability[key]) for key in RELIABILITY_KEYS}
        episodes = value.get("episodes")
        if not isinstance(episodes, Mapping):
            raise BridgeContractError("bridge checkpoint episodes must be an object")
        bridge.episodes = {}
        for episode_id, episode_value in episodes.items():
            if not isinstance(episode_id, str) or not episode_id or not isinstance(episode_value, Mapping):
                raise BridgeContractError("bridge checkpoint episode is invalid")
            owners_value = episode_value.get("owners")
            if not isinstance(owners_value, Mapping) or set(owners_value) != {"0", "1"}:
                raise BridgeContractError("bridge checkpoint owner set differs")
            owners: dict[int, _OwnerStateV1] = {}
            for player in (0, 1):
                owner_value = owners_value[str(player)]
                if not isinstance(owner_value, Mapping):
                    raise BridgeContractError("bridge checkpoint owner state is invalid")
                traces = [
                    DecisionTraceV1(
                        **{
                            **dict(item),
                            "selected_indices": tuple(item["selected_indices"]),
                            "hidden_before": tuple(item["hidden_before"]),
                            "hidden_after": tuple(item["hidden_after"]),
                        }
                    )
                    for item in owner_value.get("traces", [])
                ]
                events = [RolloutEventV1(**item) for item in owner_value.get("events", [])]
                hidden_value = owner_value.get("hidden")
                owners[player] = _OwnerStateV1(
                    next_sequence=int(owner_value.get("next_sequence", -1)),
                    hidden=None if hidden_value is None else tuple(float(x) for x in hidden_value),
                    traces=traces,
                    events=events,
                )
                if owners[player].next_sequence != len(events) or len(events) != len(traces):
                    raise BridgeContractError("bridge checkpoint owner sequence differs")
            boundaries_value = episode_value.get("player_boundaries")
            if not isinstance(boundaries_value, Mapping):
                raise BridgeContractError("bridge checkpoint player boundaries must be an object")
            boundaries: dict[int, PlayerBoundaryV1] = {}
            for raw_player, boundary_value in boundaries_value.items():
                if raw_player not in {"0", "1"} or not isinstance(boundary_value, Mapping):
                    raise BridgeContractError("bridge checkpoint player boundary is invalid")
                player = int(raw_player)
                boundary = PlayerBoundaryV1(**dict(boundary_value))
                if boundary.player != player:
                    raise BridgeContractError("bridge checkpoint player boundary identity differs")
                boundaries[player] = boundary
            closed = bool(episode_value.get("closed"))
            if closed and set(boundaries) != {0, 1}:
                raise BridgeContractError("closed bridge episode lacks both player boundaries")
            if not closed and boundaries:
                raise BridgeContractError("open bridge episode contains player boundaries")
            bridge.episodes[episode_id] = _EpisodeStateV1(
                owners=owners,
                player_boundaries=boundaries,
                closed=closed,
                boundary=episode_value.get("boundary"),
                terminal_result=episode_value.get("terminal_result"),
                truncation_class=episode_value.get("truncation_class"),
            )
        if len(bridge.seen_request_ids) != bridge.next_engine_request_seq:
            raise BridgeContractError("bridge checkpoint request accounting differs")
        return bridge

    def state_sha256(self) -> str:
        raw = json.dumps(
            self.state_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def qualification_summary(
        self,
        *,
        minimum_games: int,
        minimum_meaningful_decisions: int,
    ) -> dict[str, Any]:
        if isinstance(minimum_games, bool) or not isinstance(minimum_games, int) or minimum_games <= 0:
            raise BridgeContractError("minimum_games must be positive")
        if (
            isinstance(minimum_meaningful_decisions, bool)
            or not isinstance(minimum_meaningful_decisions, int)
            or minimum_meaningful_decisions <= 0
        ):
            raise BridgeContractError("minimum meaningful decisions must be positive")
        if self.optimizer_steps != 0:
            raise BridgeContractError("bridge executed optimizer steps")
        nonzero = {key: value for key, value in self.reliability.items() if value}
        if nonzero:
            raise BridgeContractError(f"bridge reliability counters are nonzero: {nonzero}")
        if len(self.episodes) < minimum_games:
            raise BridgeContractError("bridge game count is below the qualification floor")
        if any(
            not episode.closed
            or episode.boundary != "TERMINAL"
            or set(episode.player_boundaries) != {0, 1}
            or any(
                not boundary.terminal or boundary.truncation
                for boundary in episode.player_boundaries.values()
            )
            for episode in self.episodes.values()
        ):
            raise BridgeContractError("qualification episodes must close terminally for both players")

        meaningful = 0
        engine_decisions = 0
        maximum_error = 0.0
        forced = 0
        for episode in self.episodes.values():
            for owner in episode.owners.values():
                if owner.events:
                    split_recurrent_rollout(owner.events, maximum_learner_steps=128)
                engine_decisions += len(owner.traces)
                meaningful += sum(not trace.forced for trace in owner.traces)
                forced += sum(trace.forced for trace in owner.traces)
                maximum_error = max(
                    maximum_error,
                    max((trace.replay_absolute_error for trace in owner.traces), default=0.0),
                )
        if meaningful < minimum_meaningful_decisions:
            raise BridgeContractError("meaningful decision count is below the qualification floor")
        if maximum_error > self.maximum_replay_error:
            raise BridgeContractError("compound probability replay exceeds tolerance")
        return {
            "schema_version": 1,
            "status": "PASS",
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "optimizer_steps": 0,
            "games": len(self.episodes),
            "engine_decisions": engine_decisions,
            "meaningful_decisions": meaningful,
            "forced_decisions": forced,
            "maximum_compound_log_probability_absolute_error": maximum_error,
            "terminal_boundaries_for_both_players": len(self.episodes),
            "reliability": dict(self.reliability),
            "state_sha256": self.state_sha256(),
        }
