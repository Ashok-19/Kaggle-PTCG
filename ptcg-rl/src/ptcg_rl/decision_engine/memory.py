from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Mapping

# CABT enum values from the official competition API. Keeping these integers here
# avoids importing the private/native wrapper into the reusable runtime package.
_AREA_DECK = 1
_AREA_HAND = 2
_AREA_DISCARD = 3

_LOG_SHUFFLE = 0
_LOG_DRAW = 4
_LOG_MOVE_CARD = 6
_LOG_MOVE_CARD_REVERSE = 7
_LOG_PLAY = 10
_LOG_ATTACH = 11
_LOG_EVOLVE = 12
_LOG_ATTACK = 15


@dataclass(frozen=True)
class KnownCard:
    card_id: int
    serial: int
    owner: int
    last_known_area: int
    seen_turn: int


@dataclass
class PublicGameMemory:
    """Persistent memory containing only information legitimately observed in CABT."""

    your_index: int | None = None
    last_turn: int = -1
    last_action_count: int = -1
    known_opponent_hand: dict[int, KnownCard] = field(default_factory=dict)
    opponent_seen_cards: Counter[int] = field(default_factory=Counter)
    opponent_played_cards: Counter[int] = field(default_factory=Counter)
    opponent_discarded_cards: Counter[int] = field(default_factory=Counter)
    opponent_attacks: Counter[int] = field(default_factory=Counter)
    own_played_cards: Counter[int] = field(default_factory=Counter)
    processed_log_events: int = 0
    _last_batch_signature: tuple[object, ...] | None = None

    def reset(self) -> None:
        self.your_index = None
        self.last_turn = -1
        self.last_action_count = -1
        self.known_opponent_hand.clear()
        self.opponent_seen_cards.clear()
        self.opponent_played_cards.clear()
        self.opponent_discarded_cards.clear()
        self.opponent_attacks.clear()
        self.own_played_cards.clear()
        self.processed_log_events = 0
        self._last_batch_signature = None

    def ingest(self, observation: Mapping[str, object]) -> None:
        current = observation.get("current")
        if not isinstance(current, Mapping):
            return

        turn_raw = current.get("turn", -1)
        action_raw = current.get("turnActionCount", -1)
        turn = int(turn_raw) if isinstance(turn_raw, int) else -1
        action_count = int(action_raw) if isinstance(action_raw, int) else -1
        your_index = current.get("yourIndex")
        if not isinstance(your_index, int):
            return

        # A lower turn/action cursor indicates a new battle in a reused process.
        if self.last_turn >= 0 and (turn < self.last_turn or (turn == 0 and self.last_turn > 0)):
            self.reset()
        self.your_index = your_index
        self.last_turn = turn
        self.last_action_count = action_count

        logs = observation.get("logs")
        if not isinstance(logs, list) or not logs:
            return
        batch_signature = (turn, action_count, tuple(self._freeze_log(log) for log in logs))
        if batch_signature == self._last_batch_signature:
            return
        self._last_batch_signature = batch_signature

        for raw in logs:
            if isinstance(raw, Mapping):
                self._ingest_log(raw, turn)
                self.processed_log_events += 1

    def _ingest_log(self, log: Mapping[str, object], turn: int) -> None:
        type_raw = log.get("type")
        owner_raw = log.get("playerIndex")
        if not isinstance(type_raw, int) or not isinstance(owner_raw, int):
            return
        log_type = int(type_raw)
        owner = int(owner_raw)
        opponent = self.your_index is not None and owner != self.your_index

        card_id = log.get("cardId")
        serial = log.get("serial")
        if opponent and isinstance(card_id, int):
            self.opponent_seen_cards[int(card_id)] += 1

        if log_type == _LOG_MOVE_CARD:
            from_area = log.get("fromArea")
            to_area = log.get("toArea")
            if not isinstance(from_area, int) or not isinstance(to_area, int):
                return
            if opponent and isinstance(card_id, int) and isinstance(serial, int):
                if int(to_area) == _AREA_HAND:
                    self.known_opponent_hand[int(serial)] = KnownCard(
                        card_id=int(card_id),
                        serial=int(serial),
                        owner=owner,
                        last_known_area=_AREA_HAND,
                        seen_turn=turn,
                    )
                if int(from_area) == _AREA_HAND and int(to_area) != _AREA_HAND:
                    self.known_opponent_hand.pop(int(serial), None)
                if int(to_area) == _AREA_DISCARD:
                    self.opponent_discarded_cards[int(card_id)] += 1
            return

        # Face-down movement from the opponent hand destroys identity certainty.
        if log_type == _LOG_MOVE_CARD_REVERSE and opponent:
            from_area = log.get("fromArea")
            to_area = log.get("toArea")
            if from_area == _AREA_HAND and to_area != _AREA_HAND:
                self.known_opponent_hand.clear()
            return

        if log_type in {_LOG_PLAY, _LOG_ATTACH, _LOG_EVOLVE} and isinstance(serial, int):
            if opponent:
                self.known_opponent_hand.pop(int(serial), None)
            if log_type == _LOG_PLAY and isinstance(card_id, int):
                if opponent:
                    self.opponent_played_cards[int(card_id)] += 1
                elif self.your_index is not None and owner == self.your_index:
                    self.own_played_cards[int(card_id)] += 1
            return

        if log_type == _LOG_ATTACK and opponent:
            attack_id = log.get("attackId")
            if isinstance(attack_id, int):
                self.opponent_attacks[int(attack_id)] += 1
            return

        # Opponent direct draw is hidden in normal play. If the engine ever exposes
        # an exact opponent DRAW card, preserve it; otherwise DRAW_REVERSE has no ID.
        if log_type == _LOG_DRAW and opponent and isinstance(card_id, int) and isinstance(serial, int):
            self.known_opponent_hand[int(serial)] = KnownCard(
                card_id=int(card_id),
                serial=int(serial),
                owner=owner,
                last_known_area=_AREA_HAND,
                seen_turn=turn,
            )
            return

        # SHUFFLE is deck-only in CABT; it does not imply that known hand identities
        # were lost, so deliberately do nothing here.
        if log_type == _LOG_SHUFFLE:
            return

    @staticmethod
    def _freeze_log(log: object) -> tuple[tuple[str, object], ...] | object:
        if not isinstance(log, Mapping):
            return repr(log)
        frozen: list[tuple[str, object]] = []
        for key in sorted(log):
            value = log[key]
            if isinstance(value, (str, int, float, bool, type(None))):
                frozen.append((str(key), value))
            else:
                frozen.append((str(key), repr(value)))
        return tuple(frozen)

    def known_opponent_hand_ids(self) -> tuple[int, ...]:
        return tuple(sorted(card.card_id for card in self.known_opponent_hand.values()))
