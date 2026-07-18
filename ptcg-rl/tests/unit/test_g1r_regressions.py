from __future__ import annotations

from dataclasses import replace
import math
from pathlib import Path
import time

import pytest

from ptcg_rl.g1.actions import (
    CompoundActionBuilder,
    DeterministicReferenceScorer,
    validate_compound_action,
)
from ptcg_rl.g1.cli import hash_loaded_artifacts, smoke_is_promotable
from ptcg_rl.g1.environment import (
    DevelopmentEpisodeError,
    EpisodeEnvironmentV1,
    FailureMode,
)
from ptcg_rl.g1.evidence import source_tree_hash, unique_run_id, write_immutable_json
from ptcg_rl.g1.models import ContractViolation, SchemaMetadataV1
from ptcg_rl.g1.recurrent import RecurrentRequestLedger
from ptcg_rl.g1.semantic import semantic_snapshot

from ..g1_fixtures import raw_observation


CARD_HASH = "c" * 64


def snapshot(**kwargs):
    selection_type = kwargs.pop("selection_type", None)
    selection_context = kwargs.pop("selection_context", None)
    raw = raw_observation(**kwargs)
    if selection_type is not None:
        raw["select"]["type"] = selection_type
    if selection_context is not None:
        raw["select"]["context"] = selection_context
    return semantic_snapshot(raw, "episode", 0, CARD_HASH)


def valid_action(request):
    builder = CompoundActionBuilder(request)
    for index, option in enumerate(request.options):
        if builder.complete:
            break
        if option.available:
            builder.choose(index)
    if not builder.complete:
        builder.stop()
    return builder.build()


def test_smoke_requires_every_requested_game_and_zero_disqualifying_counter() -> None:
    clean = {
        "games_completed": 50,
        "invalid_selections": 0,
        "failures": 0,
        "timeouts": 0,
        "post_terminal_actions": 0,
        "fallback_actions": 0,
    }
    assert smoke_is_promotable(clean, requested_games=50)
    for key in clean:
        changed = dict(clean)
        changed[key] = 49 if key == "games_completed" else 1
        assert not smoke_is_promotable(changed, requested_games=50)


def test_loaded_artifact_hashes_come_from_resolved_inputs(tmp_path: Path) -> None:
    engine = tmp_path / "engine"
    (engine / "cg").mkdir(parents=True)
    files = {
        engine / "cg" / "libcg.so": b"distinguishable-test-library",
        engine / "cg" / "game.py": b"game-wrapper",
        engine / "cg" / "api.py": b"api-wrapper",
        engine / "cg" / "sim.py": b"sim-wrapper",
        tmp_path / "cards.csv": b"card-test-asset",
        tmp_path / "deck.csv": b"deck-test-asset",
    }
    for path, content in files.items():
        path.write_bytes(content)
    hashes = hash_loaded_artifacts(engine, tmp_path / "cards.csv", tmp_path / "deck.csv")
    assert hashes["engine_library"]["sha256"] != "e" * 64
    assert hashes["card_data"]["sha256"] != "c" * 64
    assert hashes["engine_library"]["path"] == "engine/cg/libcg.so"
    assert hashes["deck"]["bytes"] == len(b"deck-test-asset")


@pytest.mark.parametrize(
    "mutation",
    [
        lambda action: replace(action, submitted_original_indices=(999,)),
        lambda action: replace(action, submitted_original_indices=(0, 0)),
        lambda action: replace(action, submitted_original_indices=()),
        lambda action: replace(action, request_id="stale"),
        lambda action: replace(action, selection_seq=99),
        lambda action: replace(action, acting_player=1),
        lambda action: replace(action, episode_uuid="other"),
    ],
)
def test_forged_actions_fail_final_adapter_validation(mutation) -> None:
    _, request = snapshot(options=[{"type": 1}], min_count=1, max_count=1)
    assert request is not None
    action = mutation(valid_action(request))
    with pytest.raises(ContractViolation):
        validate_compound_action(request, action)


def test_unavailable_option_is_rejected_at_final_boundary() -> None:
    _, request = snapshot(options=[{"type": 1}, {"type": 2}], min_count=1, max_count=1)
    assert request is not None
    unavailable = replace(request.options[0], available=False)
    request = replace(request, options=(unavailable, request.options[1]))
    action = replace(valid_action(request), submitted_original_indices=(0,))
    with pytest.raises(ContractViolation):
        validate_compound_action(request, action)


def test_terminal_snapshot_never_reads_poisoned_selection_local_state() -> None:
    raw = raw_observation(result=0)
    raw["select"] = {"deck": [{"id": "poison", "serial": "poison"}]}
    observation, request = semantic_snapshot(raw, "terminal", 3, CARD_HASH)
    assert observation.terminal_result == 0
    assert request is None
    assert all(entity.card_id is None for entity in observation.entities)
    assert all("poison" not in entity.entity_key for entity in observation.entities)


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda raw: raw["select"].__setitem__("type", 999), "selection type"),
        (lambda raw: raw["select"]["option"][0].__setitem__("type", 999), "option type"),
        (
            lambda raw: raw["select"].__setitem__("option", [{"type": 3}]),
            "required field",
        ),
        (
            lambda raw: raw["select"].__setitem__(
                "option", [{"type": 3, "area": 2, "index": 99, "playerIndex": 0}]
            ),
            "unresolved",
        ),
    ],
)
def test_semantics_fail_closed(mutate, message: str) -> None:
    raw = raw_observation(options=[{"type": 1}])
    mutate(raw)
    if raw["select"]["option"][0].get("type") == 3:
        raw["select"]["type"] = 1
        raw["select"]["context"] = 8
    with pytest.raises(ContractViolation, match=message):
        semantic_snapshot(raw, "fail-closed", 0, CARD_HASH)


def test_selection_local_and_sentinel_references_are_canonical() -> None:
    cases = [
        (1, "ENTITY"),
        (12, "ENTITY"),
        (11, "PLAYER"),
        (15, "PSEUDO"),
        (24, "TEMPORARY"),
    ]
    for area, source_kind in cases:
        raw = raw_observation(
            options=[{"type": 3, "area": area, "index": 0, "playerIndex": 0}]
        )
        raw["select"]["type"] = 1
        raw["select"]["context"] = 8
        if area == 1:
            raw["select"]["deck"] = [{"id": 41, "serial": 101, "playerIndex": 0}]
        if area == 12:
            raw["current"]["looking"] = [{"id": 42, "serial": 102, "playerIndex": 0}]
        _, request = semantic_snapshot(raw, f"area-{area}", area, CARD_HASH)
        assert request is not None
        option = request.options[0]
        assert option.source_kind == source_kind
        assert option.source_ref is not None
        assert option.choice_role == "CARD"


def test_skill_zero_face_down_forced_optional_ordered_and_select_all_fixtures() -> None:
    raw = raw_observation(options=[{"type": 15, "cardId": 0, "serial": 0}])
    raw["select"]["type"] = 5
    raw["select"]["context"] = 34
    raw["current"]["players"][0]["active"] = [None]
    observation, request = semantic_snapshot(raw, "skill-zero", 0, CARD_HASH)
    assert request is not None
    assert request.ordering == "ORDERED"
    assert request.options[0].source_kind == "PSEUDO"
    assert request.options[0].choice_role == "SKILL"
    assert observation.players[0].facedown_active_count == 1
    assert valid_action(request).policy_loss_mask == 0

    _, optional = snapshot(min_count=0, max_count=1)
    assert optional is not None
    optional_builder = CompoundActionBuilder(optional)
    optional_builder.stop()
    assert optional_builder.build().submitted_original_indices == ()

    _, select_all = snapshot(
        options=[{"type": 0, "number": i} for i in range(3)], min_count=3, max_count=3,
        selection_type=8, selection_context=38,
    )
    assert select_all is not None
    assert valid_action(select_all).submitted_original_indices == (0, 1, 2)


def test_stop_is_a_real_scored_decoder_token_and_joint_logp_reconstructs() -> None:
    _, request = snapshot(
        options=[{"type": 0, "number": i} for i in range(3)], min_count=1, max_count=3,
        selection_type=8, selection_context=38,
    )
    assert request is not None
    scorer = DeterministicReferenceScorer()
    builder = CompoundActionBuilder(request)
    distribution = scorer.distribution(builder.legal_token_mask)
    builder.choose(0, token_probabilities=distribution)
    distribution = scorer.distribution(builder.legal_token_mask)
    builder.stop(token_probabilities=distribution)
    action = builder.build()
    assert [step.chosen_token for step in action.steps] == ["OPTION", "STOP"]
    assert action.steps[-1].stop_available
    assert action.steps[-1].chosen_prefix_original_indices == (0,)
    assert all(math.isclose(sum(step.token_probabilities), 1.0) for step in action.steps)
    reconstructed = sum(step.log_probability for step in action.steps)
    assert math.isclose(action.log_probability_sum, reconstructed, rel_tol=0, abs_tol=1e-15)


def test_recurrent_request_identity_isolated_idempotent_and_ordered() -> None:
    ledger = RecurrentRequestLedger()
    calls: list[str] = []
    ledger.reset_episode("episode", 0, "policy-a", reason="start")
    ledger.reset_episode("episode", 1, "policy-a", reason="start")

    def compute(label: str):
        calls.append(label)
        return label

    assert ledger.dispatch("episode", 0, "policy-a", 0, "r0", lambda: compute("p0")) == "p0"
    assert ledger.dispatch("episode", 0, "policy-a", 0, "r0", lambda: compute("duplicate")) == "p0"
    assert ledger.dispatch("episode", 1, "policy-a", 1, "r1", lambda: compute("p1")) == "p1"
    assert calls == ["p0", "p1"]
    with pytest.raises(ContractViolation, match="stale"):
        ledger.dispatch("episode", 0, "policy-a", 0, "old", lambda: None)
    with pytest.raises(ContractViolation, match="out-of-order"):
        ledger.dispatch("episode", 0, "policy-a", 3, "future", lambda: None)
    ledger.worker_replaced("policy-a")
    assert ledger.active_keys == ()


def test_source_hash_is_reproducible_and_ignores_generated_content(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    before = source_tree_hash(tmp_path)
    (tmp_path / "src" / "__pycache__").mkdir()
    (tmp_path / "src" / "__pycache__" / "module.pyc").write_bytes(b"bytecode")
    (tmp_path / "reports").mkdir()
    (tmp_path / "reports" / "generated.json").write_text("{}", encoding="utf-8")
    (tmp_path / "runs").mkdir()
    (tmp_path / "runs" / "run.json").write_text("{}", encoding="utf-8")
    assert source_tree_hash(tmp_path) == before
    (tmp_path / "src" / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
    assert source_tree_hash(tmp_path) != before


def test_run_ids_do_not_collide_and_evidence_never_overwrites(tmp_path: Path) -> None:
    ids = {unique_run_id("g1r-test") for _ in range(100)}
    assert len(ids) == 100
    destination = tmp_path / "manifest.json"
    write_immutable_json(destination, {"run_id": next(iter(ids))})
    with pytest.raises(FileExistsError):
        write_immutable_json(destination, {"run_id": "replacement"})


class RecordingTransport:
    def __init__(self) -> None:
        self.select_calls: list[tuple[int, ...]] = []

    def start(self, deck0, deck1):
        return raw_observation(options=[{"type": 1}], min_count=1, max_count=1)

    def select(self, indices):
        self.select_calls.append(tuple(indices))
        return raw_observation(result=0)

    def finish(self):
        return None


class BrokenPolicy:
    policy_id = "broken"

    def __init__(self, forge: bool = False) -> None:
        self.forge = forge
        self.resets: list[tuple[str, int, str]] = []

    def reset(self, episode_uuid: str, player_index: int, reason: str = "start") -> None:
        self.resets.append((episode_uuid, player_index, reason))

    def choose(self, observation, request):
        if self.forge:
            return replace(valid_action(request), submitted_original_indices=(999,))
        raise RuntimeError("policy failed")


def make_environment(transport, path: Path, mode: FailureMode):
    return EpisodeEnvironmentV1(
        transport,
        SchemaMetadataV1.build("e" * 64, CARD_HASH),
        max_requests=3,
        deadline_monotonic=time.monotonic() + 5,
        failure_directory=path,
        failure_mode=mode,
    )


def test_development_throws_retains_capsule_and_never_dispatches_forgery(tmp_path: Path) -> None:
    transport = RecordingTransport()
    with pytest.raises(DevelopmentEpisodeError):
        make_environment(transport, tmp_path, FailureMode.DEVELOPMENT).run(
            "episode", [1] * 60, [1] * 60, {0: BrokenPolicy(forge=True), 1: BrokenPolicy()}
        )
    assert transport.select_calls == []
    capsules = list(tmp_path.glob("*.failure.json"))
    assert len(capsules) == 1
    assert capsules[0].stat().st_size < 16_384


def test_submission_fallback_is_legal_counted_bounded_and_disqualifying(tmp_path: Path) -> None:
    transport = RecordingTransport()
    result = make_environment(transport, tmp_path, FailureMode.SUBMISSION).run(
        "episode", [1] * 60, [1] * 60, {0: BrokenPolicy(), 1: BrokenPolicy()}
    )
    assert transport.select_calls == [(0,)]
    assert result.summary.fallback_actions == 1
    metrics = {
        "games_completed": 1,
        "invalid_selections": 0,
        "failures": 0,
        "timeouts": 0,
        "post_terminal_actions": 0,
        "fallback_actions": 1,
    }
    assert not smoke_is_promotable(metrics, requested_games=1)
    assert len(list(tmp_path.glob("*.failure.json"))) <= 4
