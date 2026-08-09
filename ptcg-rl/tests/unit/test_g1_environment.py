from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import pytest

from ptcg_rl.g1.actions import DeterministicFirstLegalPolicy
from ptcg_rl.g1.environment import (
    EnvironmentState,
    EpisodeEnvironmentV1,
    FailureMode,
    DevelopmentEpisodeError,
    terminal_rewards,
)
from ptcg_rl.g1.models import SchemaMetadataV1
from ptcg_rl.g1.rule_baseline import NativeRulePolicy
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
        self.resets: list[tuple[str, int, str]] = []

    def reset(self, battle_id: str, player_index: int, reason: str = "start") -> None:
        self.resets.append((battle_id, player_index, reason))


def metadata() -> SchemaMetadataV1:
    return SchemaMetadataV1.build("e" * 64, "c" * 64)


def environment(
    transport, failure_directory: Path | None = None,
    failure_mode: FailureMode = FailureMode.DEVELOPMENT,
):
    return EpisodeEnvironmentV1(
        transport,
        metadata(),
        max_requests=10,
        deadline_monotonic=time.monotonic() + 10,
        failure_directory=failure_directory,
        failure_mode=failure_mode,
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
    assert policy0.resets == [
        ("one", 0, "start"), ("one", 0, "terminal"),
        ("two", 0, "start"), ("two", 0, "terminal"),
    ]
    assert policy1.resets == [
        ("one", 1, "start"), ("one", 1, "terminal"),
        ("two", 1, "start"), ("two", 1, "terminal"),
    ]
    assert first.transitions[0].policy_loss_mask == 0
    assert first.summary.transition_records == 2
    assert first.transitions[-1].observation.previous_request_ref is not None
    assert first.transitions[-1].observation.previous_action_ref is not None
    assert second.summary.terminal_result == 0


def test_native_failure_writes_bounded_redacted_artifact(tmp_path: Path) -> None:
    result = environment(
        FakeTransport(fail_select=True), tmp_path, FailureMode.SUBMISSION
    ).run(
        "failure", [1] * 60, [1] * 60, {0: ResetPolicy(), 1: ResetPolicy()}
    )
    assert result.summary.failure_kind == "native_failure"
    artifact = next(tmp_path.glob("*.failure.json"))
    value = json.loads(artifact.read_text(encoding="utf-8"))
    assert value["message"] == "native or policy operation failed; inspect local process logs"
    assert "PRIVATE_REPLAY_BODY" not in artifact.read_text(encoding="utf-8")


def _private_rule_policy(
    tmp_path: Path, returned: str, *, sibling_helper: str | None = None
) -> NativeRulePolicy:
    directory = tmp_path / "rule"
    directory.mkdir()
    deck = directory / "deck.csv"
    deck.write_text(",".join(["1"] * 60) + "\n", encoding="utf-8")
    module = directory / "main.py"
    if sibling_helper is None:
        module.write_text(f"def agent(observation):\n    return {returned}\n", encoding="utf-8")
    else:
        (directory / "helper.py").write_text(sibling_helper, encoding="utf-8")
        module.write_text(
            "from helper import RETURNED\n\n"
            "def agent(observation):\n"
            "    return RETURNED\n",
            encoding="utf-8",
        )
    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    (directory / "receipt.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "baseline_id": "fixture",
                "policy_id": "fixture-rule-v1",
                "notebook": {"bytes": 1, "sha256": "0" * 64},
                "module": {"bytes": module.stat().st_size, "sha256": digest(module)},
                "deck": {"bytes": deck.stat().st_size, "sha256": digest(deck)},
            }
        ),
        encoding="utf-8",
    )
    return NativeRulePolicy(directory)


def test_private_native_rule_policy_uses_raw_observation_and_final_validator(tmp_path: Path) -> None:
    policy = _private_rule_policy(tmp_path, "[0]")
    result = environment(FakeTransport()).run(
        "native-rule", policy.deck, [1] * 60, {0: policy, 1: ResetPolicy()}
    )
    assert result.summary.terminal_result == 0
    assert result.transitions[0].action is not None
    assert result.transitions[0].action.submitted_original_indices == (0,)


def test_private_native_rule_policy_invalid_output_is_rejected_before_transport(
    tmp_path: Path,
) -> None:
    transport = FakeTransport()
    policy = _private_rule_policy(tmp_path, "[999]")
    try:
        environment(transport).run(
            "invalid-native-rule", policy.deck, [1] * 60, {0: policy, 1: ResetPolicy()}
        )
    except DevelopmentEpisodeError as error:
        assert error.result.summary.invalid_selections == 1
    else:
        raise AssertionError("invalid native rule output was accepted")
    assert transport.select_calls == 0


def test_private_native_rule_policy_binds_exact_deck_hash(tmp_path: Path) -> None:
    policy = _private_rule_policy(tmp_path, "[0]")
    (policy.directory / "deck.csv").write_text(",".join(["2"] * 60), encoding="utf-8")
    try:
        NativeRulePolicy(policy.directory)
    except Exception as error:
        assert "deck hash mismatch" in str(error)
    else:
        raise AssertionError("modified deck was accepted")


def test_private_native_rule_policy_loads_sibling_and_restores_import_context(
    tmp_path: Path,
) -> None:
    previous_cwd = Path.cwd()
    previous_sys_path = sys.path.copy()
    try:
        policy = _private_rule_policy(tmp_path, "[0]", sibling_helper="RETURNED = [0]\n")

        assert policy._module.agent({}) == [0]
        assert Path.cwd() == previous_cwd
        assert sys.path == previous_sys_path
    finally:
        sys.modules.pop("helper", None)


def test_private_native_rule_policy_restores_import_context_on_load_failure(
    tmp_path: Path,
) -> None:
    previous_cwd = Path.cwd()
    previous_sys_path = sys.path.copy()
    sys.modules.pop("helper", None)
    with pytest.raises(RuntimeError, match="sibling import failure"):
        _private_rule_policy(
            tmp_path,
            "[0]",
            sibling_helper="raise RuntimeError('sibling import failure')\n",
        )

    assert Path.cwd() == previous_cwd
    assert sys.path == previous_sys_path
