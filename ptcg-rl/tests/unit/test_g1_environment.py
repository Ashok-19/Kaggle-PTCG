from __future__ import annotations

import json
import time
from pathlib import Path

from ptcg_rl.g1.actions import DeterministicFirstLegalPolicy
from ptcg_rl.g1.environment import EnvironmentState, EpisodeEnvironmentV1, terminal_rewards
from ptcg_rl.g1.models import SchemaMetadataV1
from ..g1_fixtures import raw_observation


class FakeTransport:
    def __init__(self, start_result: int = -1, fail_select: bool = False) -> None:
        self.start_result = start_result
        self.fail_select = fail_select
        self.select_calls = 0
        self.finished = 0

    def start(self, deck0, deck1):
        return raw_observation(result=self.start_result, options=[{"type": 1}])

    def select(self, indices):
        self.select_calls += 1
        if self.fail_select:
            raise RuntimeError("PRIVATE_REPLAY_BODY_SHOULD_NOT_APPEAR")
        return raw_observation(result=0, options=[{"type": 1}])

    def finish(self):
        self.finished += 1


class ResetPolicy(DeterministicFirstLegalPolicy):
    def __init__(self) -> None:
        self.resets: list[tuple[str, int]] = []

    def reset(self, battle_id: str, player_index: int) -> None:
        self.resets.append((battle_id, player_index))


def metadata() -> SchemaMetadataV1:
    return SchemaMetadataV1.build("e" * 64, "c" * 64)


def environment(transport, failure_directory: Path | None = None):
    return EpisodeEnvironmentV1(
        transport,
        metadata(),
        max_requests=10,
        deadline_monotonic=time.monotonic() + 10,
        failure_directory=failure_directory,
    )


def test_terminal_start_never_submits_stale_selection() -> None:
    transport = FakeTransport(start_result=2)
    policies = {0: ResetPolicy(), 1: ResetPolicy()}
    wrapper = environment(transport)
    result = wrapper.run("terminal", [1] * 60, [1] * 60, policies)
    assert result.summary.terminal_result == 2
    assert result.summary.post_terminal_actions == 0
    assert transport.select_calls == 0
    assert wrapper.state is EnvironmentState.CLOSED
    assert wrapper.end_state is EnvironmentState.TERMINAL
    assert terminal_rewards(2) == (0.0, 0.0)
    assert terminal_rewards(0) == (1.0, -1.0)
    assert terminal_rewards(1) == (-1.0, 1.0)


def test_episode_reset_prevents_state_leakage_and_forced_step_is_recorded() -> None:
    policy0, policy1 = ResetPolicy(), ResetPolicy()
    policies = {0: policy0, 1: policy1}
    first = environment(FakeTransport()).run("one", [1] * 60, [1] * 60, policies)
    second = environment(FakeTransport()).run("two", [1] * 60, [1] * 60, policies)
    assert policy0.resets == [("one", 0), ("two", 0)]
    assert policy1.resets == [("one", 1), ("two", 1)]
    assert first.transitions[0].policy_loss_mask == 0
    assert first.summary.transition_records == 2
    assert first.transitions[-1].observation.previous_request_ref is not None
    assert first.transitions[-1].observation.previous_action_ref is not None
    assert second.summary.terminal_result == 0


def test_native_failure_writes_bounded_redacted_artifact(tmp_path: Path) -> None:
    result = environment(FakeTransport(fail_select=True), tmp_path).run(
        "failure", [1] * 60, [1] * 60, {0: ResetPolicy(), 1: ResetPolicy()}
    )
    assert result.summary.failure_kind == "native_failure"
    artifact = next(tmp_path.glob("*.failure.json"))
    value = json.loads(artifact.read_text(encoding="utf-8"))
    assert value["message"] == "native operation failed; inspect local process logs"
    assert "PRIVATE_REPLAY_BODY" not in artifact.read_text(encoding="utf-8")
