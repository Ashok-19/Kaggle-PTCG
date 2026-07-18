from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Callable, TypeVar

from .models import ContractViolation


T = TypeVar("T")
RecurrentKey = tuple[str, int, str]


@dataclass
class _RequestState:
    responses: dict[tuple[int, str], object] = field(default_factory=dict)


class RecurrentRequestLedger:
    """Owns request ordering and duplicate replay independently of policy objects."""

    def __init__(self) -> None:
        self._states: dict[RecurrentKey, _RequestState] = {}
        self._episode_next: dict[str, int] = {}
        self._lock = Lock()
        self.reset_events: list[tuple[RecurrentKey, str]] = []

    @staticmethod
    def _key(episode_uuid: str, player: int, policy_id: str) -> RecurrentKey:
        if not episode_uuid or not policy_id or player not in (0, 1):
            raise ContractViolation("invalid recurrent ownership key")
        return episode_uuid, player, policy_id

    @property
    def active_keys(self) -> tuple[RecurrentKey, ...]:
        with self._lock:
            return tuple(sorted(self._states))

    def reset_episode(
        self, episode_uuid: str, player: int, policy_id: str, *, reason: str
    ) -> None:
        if reason not in {"start", "deck", "terminal", "error", "worker_replacement"}:
            raise ContractViolation("unknown recurrent reset reason")
        key = self._key(episode_uuid, player, policy_id)
        with self._lock:
            if reason in {"start", "deck"}:
                self._states[key] = _RequestState()
                self._episode_next.setdefault(episode_uuid, 0)
            else:
                self._states.pop(key, None)
                if not any(candidate[0] == episode_uuid for candidate in self._states):
                    self._episode_next.pop(episode_uuid, None)
            self.reset_events.append((key, reason))

    def dispatch(
        self,
        episode_uuid: str,
        player: int,
        policy_id: str,
        selection_seq: int,
        request_id: str,
        compute: Callable[[], T],
    ) -> T:
        key = self._key(episode_uuid, player, policy_id)
        if selection_seq < 0 or not request_id:
            raise ContractViolation("invalid recurrent request identity")
        with self._lock:
            state = self._states.get(key)
            if state is None:
                raise ContractViolation("recurrent request arrived before reset acknowledgement")
            cached = state.responses.get((selection_seq, request_id))
            if cached is not None:
                return cached  # type: ignore[return-value]
            next_selection_seq = self._episode_next[episode_uuid]
            if selection_seq < next_selection_seq:
                raise ContractViolation("stale recurrent request")
            if selection_seq > next_selection_seq:
                raise ContractViolation("out-of-order recurrent request")
            value = compute()
            state.responses[(selection_seq, request_id)] = value
            self._episode_next[episode_uuid] = next_selection_seq + 1
            return value

    def worker_replaced(self, policy_id: str) -> None:
        if not policy_id:
            raise ContractViolation("policy_id is required for worker replacement")
        with self._lock:
            keys = [key for key in self._states if key[2] == policy_id]
            for key in keys:
                self._states.pop(key)
                self.reset_events.append((key, "worker_replacement"))
            affected_episodes = {key[0] for key in keys}
            for episode_uuid in affected_episodes:
                for key in [candidate for candidate in self._states if candidate[0] == episode_uuid]:
                    self._states.pop(key)
                    self.reset_events.append((key, "worker_replacement"))
                self._episode_next.pop(episode_uuid, None)
