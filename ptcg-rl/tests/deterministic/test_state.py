from __future__ import annotations

from dataclasses import replace

import pytest

from ptcg_rl.deterministic.state import (
    EntityLifetime,
    PublicStateError,
    PublicStateTracker,
    PublicStateV1,
    StateOrderError,
    entity_lifetime,
    hidden_slot_key,
    known_entity_key,
)
from ptcg_rl.g1.models import PublicEventV1
from ptcg_rl.g1.semantic import semantic_snapshot

from ..g1_fixtures import raw_observation


CARD_HASH = "c" * 64


def snapshot(*, result: int = -1, transition: int = 0, options=None):
    raw = raw_observation(result=result, options=options)
    return semantic_snapshot(raw, "phase-a", transition, CARD_HASH)


def test_state_is_public_and_recursively_immutable() -> None:
    observation, request = snapshot(options=[{"type": 1}])
    assert request is not None
    state = PublicStateV1.from_engine(observation, request)
    assert state.legal_options == request.options
    assert state.events == observation.public_events
    with pytest.raises(TypeError):
        state.events[0].fields["new"] = 1
    with pytest.raises(AttributeError):
        state.entities[0].owner = 1
    assert "search" not in repr(state).lower()


def test_terminal_state_discards_poisoned_selection_without_reading_it() -> None:
    observation, _ = snapshot(result=0)
    poisoned = object()
    state = PublicStateV1.from_engine(observation, poisoned)  # type: ignore[arg-type]
    assert state.terminal_result == 0
    assert state.request is None
    assert not state.legal_options


def test_complete_options_and_events_are_not_truncated() -> None:
    options = [{"type": 0, "number": index} for index in range(70)]
    raw = raw_observation(options=options)
    raw["select"].update({"type": 8, "context": 38})
    observation, request = semantic_snapshot(raw, "phase-a", 0, CARD_HASH)
    state = PublicStateV1.from_engine(observation, request)
    assert len(state.legal_options) == 70
    assert len(state.events) == len(observation.public_events)


def test_known_and_hidden_slot_keys_and_lifetimes_are_canonical() -> None:
    assert known_entity_key(0, 7) == "p0:s7"
    assert hidden_slot_key(1, 6, 2) == "slot:p1:z6:i2"
    observation, _ = snapshot()
    hidden = next(entity for entity in observation.entities if entity.serial is None)
    known = replace(hidden, entity_key=known_entity_key(0, 7), card_id=100, serial=7, visible=True)
    assert entity_lifetime(known) == EntityLifetime.STABLE
    assert entity_lifetime(hidden) == EntityLifetime.STABLE


def test_ledger_seed_only_contains_public_counts() -> None:
    observation, request = snapshot(options=[{"type": 1}])
    state = PublicStateV1.from_engine(observation, request)
    assert state.ledger_seed.hidden_slot_counts
    assert not hasattr(state.ledger_seed, "score")
    assert not hasattr(state.ledger_seed, "belief")


def test_tracker_is_idempotent_and_rejects_stale_or_conflicting_transitions() -> None:
    tracker = PublicStateTracker("phase-a-test")
    first_observation, first_request = snapshot(transition=0, options=[{"type": 1}])
    first = tracker.observe(first_observation, first_request)
    assert tracker.observe(first_observation, first_request) is first
    stale_observation, stale_request = snapshot(transition=0, options=[{"type": 2}])
    with pytest.raises(StateOrderError, match="different"):
        tracker.observe(stale_observation, stale_request)
    later_observation, later_request = snapshot(transition=1, options=[{"type": 1}])
    tracker.observe(later_observation, later_request)
    with pytest.raises(StateOrderError, match="stale"):
        tracker.observe(first_observation, first_request)
    assert tracker.last("phase-a", 0) is not None
    tracker.reset("phase-a", 0)
    assert tracker.last("phase-a", 0) is None


def test_nested_event_payload_is_frozen() -> None:
    observation, request = snapshot(options=[{"type": 1}])
    event = PublicEventV1(2, "TURN_START", {"playerIndex": 0})
    state = PublicStateV1.from_engine(replace(observation, public_events=(event,)), request)
    with pytest.raises(TypeError):
        state.events[0].fields["playerIndex"] = 2


def test_public_boundary_rejects_opponent_hand_and_duplicate_identity() -> None:
    observation, request = snapshot(options=[{"type": 1}])
    opponent_hand = replace(
        observation.entities[0],
        entity_key=known_entity_key(1, 77),
        card_id=100,
        serial=77,
        owner=1,
        zone=2,
        position=0,
        visible=True,
    )
    with pytest.raises(PublicStateError, match="opponent hand"):
        PublicStateV1.from_engine(replace(observation, entities=observation.entities + (opponent_hand,)), request)
    with pytest.raises(PublicStateError, match="duplicate public entity"):
        PublicStateV1.from_engine(
            replace(observation, entities=observation.entities + (observation.entities[0],)), request
        )


def test_transient_and_stable_slots_are_not_conflated() -> None:
    observation, request = snapshot(options=[{"type": 1}])
    hidden_prize = next(entity for entity in observation.entities if entity.serial is None)
    transient = replace(
        hidden_prize,
        entity_key=known_entity_key(0, 19),
        card_id=100,
        serial=19,
        zone=1,
        visible=True,
    )
    assert entity_lifetime(hidden_prize) == EntityLifetime.STABLE
    assert entity_lifetime(transient) == EntityLifetime.TRANSIENT
    same_serial = replace(transient, zone=6)
    with pytest.raises(PublicStateError, match="duplicate public entity"):
        PublicStateV1.from_engine(
            replace(observation, entities=observation.entities + (transient, same_serial)), request
        )


def test_ledger_residual_counts_only_unrepresented_public_cards() -> None:
    observation, request = snapshot(options=[{"type": 1}])
    own_hand = replace(
        observation.entities[0],
        entity_key=known_entity_key(0, 88),
        card_id=100,
        serial=88,
        owner=0,
        zone=2,
        position=0,
        visible=True,
    )
    state = PublicStateV1.from_engine(replace(observation, entities=(own_hand,)), request)
    assert (0, 100, 1) in state.ledger_seed.visible_card_counts
    assert (0, 2, 6) in state.ledger_seed.hidden_slot_counts


def test_unknown_event_and_option_enums_fail_closed() -> None:
    observation, request = snapshot(options=[{"type": 1}])
    assert request is not None
    with pytest.raises(PublicStateError, match="event enum"):
        PublicStateV1.from_engine(
            replace(observation, public_events=(PublicEventV1(99, "UNKNOWN", {}),)), request
        )
    bad_option = replace(request.options[0], option_type=99)
    with pytest.raises(PublicStateError, match="option type"):
        PublicStateV1.from_engine(observation, replace(request, options=(bad_option,)))


def test_tracker_resets_terminal_lifecycle_and_accepts_explicit_start() -> None:
    tracker = PublicStateTracker("phase-a-lifecycle")
    first_observation, first_request = snapshot(transition=0, options=[{"type": 1}])
    tracker.observe(first_observation, first_request)
    terminal_observation, _ = snapshot(result=0, transition=1)
    terminal = tracker.observe(terminal_observation, object())  # type: ignore[arg-type]
    assert tracker.last("phase-a", 0) is terminal
    start_observation, start_request = semantic_snapshot({"logs": []}, "phase-a", 0, CARD_HASH)
    assert start_request is None
    tracker.observe(start_observation, start_request)
    assert tracker.last("phase-a", 0) is None
    tracker.on_error("phase-a")


def test_ongoing_without_request_is_only_allowed_for_start_marker() -> None:
    observation, request = semantic_snapshot({"logs": []}, "start", 0, CARD_HASH)
    assert request is None
    state = PublicStateV1.from_engine(observation, None)
    assert state.acting_player is None
