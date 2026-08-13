from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Mapping

# Current rank-1 Mega Lucario core card IDs, bound to CABT 2026 card data.
FIGHTING_ENERGY = 6
MAKUHITA = 673
HARIYAMA = 674
LUNATONE = 675
SOLROCK = 676
RIOLU = 677
MEGA_LUCARIO_EX = 678
ULTRA_BALL = 1121
SWITCH = 1123
PREMIUM_POWER_PRO = 1141
FIGHTING_GONG = 1142
POKE_PAD = 1152
BOSS_ORDERS = 1182
JUDGE = 1213
LILLIE_DETERMINATION = 1227
WALLY_COMPASSION = 1229

# CABT OptionType / AreaType integers from the official API.
_PLAY = 7
_ATTACH = 8
_EVOLVE = 9
_ABILITY = 10
_RETREAT = 12
_ATTACK = 13
_END = 14
_ACTIVE = 4
_BENCH = 5
_MAIN_CONTEXT = 0


class LucarioPhase(str, Enum):
    DECK_PRESERVE = "DECK_PRESERVE"
    RECOVER = "RECOVER"
    BUILD_ATTACKER = "BUILD_ATTACKER"
    BUILD_CHAIN = "BUILD_CHAIN"
    CLOSE = "CLOSE"
    TRADE = "TRADE"
    SETUP = "SETUP"
    REFRESH = "REFRESH"


@dataclass(frozen=True)
class LucarioSnapshot:
    turn: int
    turn_actions: int
    hand_count: int
    deck_count: int
    prizes_remaining: int
    opponent_prizes_remaining: int
    supporter_played: bool
    energy_attached: bool
    active_id: int | None
    active_energy: int
    active_damage: int
    fighting_in_hand: int
    fighting_in_discard: int
    primary_ready: int
    primary_near: int
    backup_ready: bool
    legal_attack: bool
    legal_aura_jab: bool
    legal_mega_brave: bool
    legal_lunar_cycle: bool
    legal_ultra_ball: bool
    legal_wally: bool
    legal_lillie: bool
    legal_boss: bool
    legal_premium: bool
    legal_evolve: bool
    legal_evolve_mega: bool
    legal_evolve_hariyama: bool
    legal_attach: bool
    attach_makes_primary_ready: bool
    attach_builds_backup: bool
    route_search_need: bool


@dataclass(frozen=True)
class LucarioIntent:
    phase: LucarioPhase
    deck_reserve: int
    deck_deficit: int
    allow_lunar_cycle: bool
    allow_ultra_ball: bool
    prioritize_mega_evolution: bool
    prioritize_route_attachment: bool
    prefer_wally: bool
    prefer_attack_commit: bool
    reasons: tuple[str, ...]


def _card_id(value: object) -> int | None:
    if isinstance(value, Mapping) and isinstance(value.get("id"), int):
        return int(value["id"])
    return None


def _energy_count(value: object) -> int:
    if not isinstance(value, Mapping):
        return 0
    energies = value.get("energies")
    return len(energies) if isinstance(energies, list) else 0


def _pokemon_at(player: Mapping[str, object], area: int, index: int) -> Mapping[str, object] | None:
    zone = player.get("active") if area == _ACTIVE else player.get("bench") if area == _BENCH else None
    if not isinstance(zone, list) or not 0 <= index < len(zone):
        return None
    value = zone[index]
    return value if isinstance(value, Mapping) else None


def _hand_card_id(hand: list[object], index: object) -> int | None:
    if not isinstance(index, int) or not 0 <= index < len(hand):
        return None
    return _card_id(hand[index])


def _primary_ready_counts(
    player: Mapping[str, object],
    hand_counts: Counter[int],
) -> tuple[int, int]:
    board = []
    for key in ("active", "bench"):
        zone = player.get(key)
        if isinstance(zone, list):
            board.extend(card for card in zone if isinstance(card, Mapping))
    has_lunatone = any(_card_id(card) == LUNATONE for card in board)
    ready = 0
    near = 0
    for pokemon in board:
        card_id = _card_id(pokemon)
        energy = _energy_count(pokemon)
        if card_id == MEGA_LUCARIO_EX:
            if energy >= 1:
                ready += 1
            if energy >= 0:
                near += 1
        elif card_id == HARIYAMA:
            if energy >= 3:
                ready += 1
            if energy >= 2:
                near += 1
        elif card_id == SOLROCK and has_lunatone:
            if energy >= 1:
                ready += 1
            near += 1
        elif card_id == RIOLU and hand_counts[MEGA_LUCARIO_EX] > 0:
            # One legal evolution creates an Aura-Jab attacker. Energy may be
            # attached before or after the evolution, so a 0-energy Riolu is near.
            near += 1
        elif card_id == MAKUHITA and hand_counts[HARIYAMA] > 0 and energy >= 2:
            near += 1
    return ready, near


def snapshot(observation: Mapping[str, object]) -> LucarioSnapshot:
    current = observation.get("current")
    select = observation.get("select")
    if not isinstance(current, Mapping) or not isinstance(select, Mapping):
        raise ValueError("Lucario planner requires a live CABT selection")
    if int(select.get("context", -1)) != _MAIN_CONTEXT:
        raise ValueError("Lucario planner is defined only at MAIN selections")
    your_index = current.get("yourIndex")
    players = current.get("players")
    if not isinstance(your_index, int) or not isinstance(players, list) or not 0 <= your_index < len(players):
        raise ValueError("invalid CABT current-player state")
    player = players[your_index]
    opponent = players[1 - your_index]
    if not isinstance(player, Mapping) or not isinstance(opponent, Mapping):
        raise ValueError("invalid CABT player state")

    hand = player.get("hand")
    hand_values = hand if isinstance(hand, list) else []
    hand_counts = Counter(
        card_id for card_id in (_card_id(card) for card in hand_values) if card_id is not None
    )
    discard = player.get("discard")
    discard_values = discard if isinstance(discard, list) else []
    discard_counts = Counter(
        card_id for card_id in (_card_id(card) for card in discard_values) if card_id is not None
    )
    primary_ready, primary_near = _primary_ready_counts(player, hand_counts)

    active_zone = player.get("active")
    active = active_zone[0] if isinstance(active_zone, list) and active_zone and isinstance(active_zone[0], Mapping) else None
    active_id = _card_id(active)
    active_energy = _energy_count(active)
    active_damage = 0
    if active is not None:
        hp = active.get("hp")
        max_hp = active.get("maxHp")
        if isinstance(hp, int) and isinstance(max_hp, int):
            active_damage = max(0, max_hp - hp)

    legal_attack = False
    legal_aura = False
    legal_brave = False
    legal_lunar = False
    legal_ultra = False
    legal_wally = False
    legal_lillie = False
    legal_boss = False
    legal_premium = False
    legal_evolve = False
    legal_evolve_mega = False
    legal_evolve_hariyama = False
    legal_attach = False
    attach_makes_primary_ready = False
    attach_builds_backup = False

    options = select.get("option")
    if not isinstance(options, list):
        options = []
    for raw_option in options:
        if not isinstance(raw_option, Mapping):
            continue
        option_type = int(raw_option.get("type", -1))
        if option_type == _PLAY:
            card_id = _hand_card_id(hand_values, raw_option.get("index"))
            legal_ultra |= card_id == ULTRA_BALL
            legal_wally |= card_id == WALLY_COMPASSION
            legal_lillie |= card_id == LILLIE_DETERMINATION
            legal_boss |= card_id == BOSS_ORDERS
            legal_premium |= card_id == PREMIUM_POWER_PRO
        elif option_type == _ABILITY:
            area = raw_option.get("area")
            index = raw_option.get("index")
            if isinstance(area, int) and isinstance(index, int):
                legal_lunar |= _card_id(_pokemon_at(player, area, index)) == LUNATONE
        elif option_type == _EVOLVE:
            legal_evolve = True
            card_id = _hand_card_id(hand_values, raw_option.get("index"))
            legal_evolve_mega |= card_id == MEGA_LUCARIO_EX
            legal_evolve_hariyama |= card_id == HARIYAMA
        elif option_type == _ATTACH:
            legal_attach = True
            area = raw_option.get("inPlayArea")
            index = raw_option.get("inPlayIndex")
            target = (
                _pokemon_at(player, area, index)
                if isinstance(area, int) and isinstance(index, int)
                else None
            )
            target_id = _card_id(target)
            energy = _energy_count(target)
            makes_ready = (
                (target_id in {RIOLU, MEGA_LUCARIO_EX} and energy == 0)
                or (target_id == HARIYAMA and energy == 2)
                or (target_id == SOLROCK and energy == 0)
            )
            attach_makes_primary_ready |= makes_ready
            attach_builds_backup |= makes_ready and primary_ready >= 1
        elif option_type == _ATTACK:
            legal_attack = True
            attack_id = raw_option.get("attackId")
            legal_aura |= attack_id == 982
            legal_brave |= attack_id == 983

    # Ultra Ball is route-critical only when it can plausibly fill a missing
    # attacker/evolution role, not merely because it is legal and hand-thinning.
    board_ids = Counter()
    for key in ("active", "bench"):
        zone = player.get(key)
        if isinstance(zone, list):
            for card in zone:
                card_id = _card_id(card)
                if card_id is not None:
                    board_ids[card_id] += 1
    missing_mega_for_riolu = board_ids[RIOLU] > 0 and hand_counts[MEGA_LUCARIO_EX] == 0
    missing_hariyama_for_makuhita = board_ids[MAKUHITA] > 0 and hand_counts[HARIYAMA] == 0
    route_search_need = (
        primary_ready == 0
        or missing_mega_for_riolu
        or missing_hariyama_for_makuhita
    )

    return LucarioSnapshot(
        turn=int(current.get("turn", 0)),
        turn_actions=int(current.get("turnActionCount", 0)),
        hand_count=int(player.get("handCount", len(hand_values))),
        deck_count=int(player.get("deckCount", 0)),
        prizes_remaining=len(player.get("prize") or []),
        opponent_prizes_remaining=len(opponent.get("prize") or []),
        supporter_played=bool(current.get("supporterPlayed")),
        energy_attached=bool(current.get("energyAttached")),
        active_id=active_id,
        active_energy=active_energy,
        active_damage=active_damage,
        fighting_in_hand=hand_counts[FIGHTING_ENERGY],
        fighting_in_discard=discard_counts[FIGHTING_ENERGY],
        primary_ready=primary_ready,
        primary_near=primary_near,
        backup_ready=primary_ready >= 2,
        legal_attack=legal_attack,
        legal_aura_jab=legal_aura,
        legal_mega_brave=legal_brave,
        legal_lunar_cycle=legal_lunar,
        legal_ultra_ball=legal_ultra,
        legal_wally=legal_wally,
        legal_lillie=legal_lillie,
        legal_boss=legal_boss,
        legal_premium=legal_premium,
        legal_evolve=legal_evolve,
        legal_evolve_mega=legal_evolve_mega,
        legal_evolve_hariyama=legal_evolve_hariyama,
        legal_attach=legal_attach,
        attach_makes_primary_ready=attach_makes_primary_ready,
        attach_builds_backup=attach_builds_backup,
        route_search_need=route_search_need,
    )


class LucarioStrategicPlanner:
    """Turn-objective planner; it constrains sequencing but does not select CABT options."""

    def plan(self, observation: Mapping[str, object]) -> LucarioIntent:
        state = snapshot(observation)
        reserve = state.prizes_remaining + 5
        deficit = min(0, state.deck_count - reserve)
        deck_preserve = state.deck_count <= reserve
        reasons: list[str] = []

        prefer_wally = (
            state.legal_wally
            and state.active_id == MEGA_LUCARIO_EX
            and state.active_damage >= 150
            and not state.supporter_played
        )

        if deck_preserve:
            phase = LucarioPhase.DECK_PRESERVE
            reasons.append("deck_at_or_below_prize_route_reserve")
        elif prefer_wally:
            phase = LucarioPhase.RECOVER
            reasons.append("damaged_three_prize_mega_has_wally_reset")
        elif state.legal_evolve_mega:
            phase = LucarioPhase.BUILD_ATTACKER
            reasons.append("mega_evolution_is_immediately_available")
        elif state.attach_makes_primary_ready:
            phase = LucarioPhase.BUILD_ATTACKER
            reasons.append("manual_attachment_crosses_primary_attack_threshold")
        elif state.primary_ready == 0:
            phase = LucarioPhase.SETUP
            reasons.append("no_primary_attacker_ready")
        elif state.primary_ready < 2 and (state.legal_evolve or state.attach_builds_backup):
            phase = LucarioPhase.BUILD_CHAIN
            reasons.append("current_attacker_exists_but_backup_chain_is_not_ready")
        elif state.legal_attack and state.prizes_remaining <= 2:
            phase = LucarioPhase.CLOSE
            reasons.append("late_prize_route_has_legal_attack")
        elif state.legal_attack:
            phase = LucarioPhase.TRADE
            reasons.append("attack_available_after_route_setup")
        else:
            phase = LucarioPhase.REFRESH
            reasons.append("no_attack_or_threshold_crossing_setup_action")

        prioritize_mega_evolution = (
            not deck_preserve and state.legal_evolve_mega
        )
        prioritize_route_attachment = (
            not deck_preserve and state.attach_makes_primary_ready
        )

        # Majkel chooses Lunar in only ~20% of legal states, ~11% when evolution
        # is legal, ~15% when Aura Jab is already legal and ~12% with Mega Brave.
        # Treat it as a refresh tool after route-critical setup, not a default opener.
        allow_lunar = (
            state.legal_lunar_cycle
            and not deck_preserve
            and state.fighting_in_hand > 0
            and not state.legal_evolve
            and not state.attach_makes_primary_ready
            and not state.legal_attack
        )

        # Ultra Ball costs two other cards. Use it to fill a missing attacker or
        # evolution role, never simply because the option exists. Existing legal
        # evolution/threshold-crossing attachment takes precedence.
        allow_ultra = (
            state.legal_ultra_ball
            and not deck_preserve
            and state.route_search_need
            and not state.legal_evolve
            and not state.attach_makes_primary_ready
        )

        prefer_attack = (
            state.legal_attack
            and phase in {LucarioPhase.CLOSE, LucarioPhase.TRADE}
        )
        return LucarioIntent(
            phase=phase,
            deck_reserve=reserve,
            deck_deficit=deficit,
            allow_lunar_cycle=allow_lunar,
            allow_ultra_ball=allow_ultra,
            prioritize_mega_evolution=prioritize_mega_evolution,
            prioritize_route_attachment=prioritize_route_attachment,
            prefer_wally=prefer_wally,
            prefer_attack_commit=prefer_attack,
            reasons=tuple(reasons),
        )


__all__ = [
    "LucarioIntent",
    "LucarioPhase",
    "LucarioSnapshot",
    "LucarioStrategicPlanner",
    "snapshot",
]
