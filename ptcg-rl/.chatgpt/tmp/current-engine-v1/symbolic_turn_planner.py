from __future__ import annotations

import importlib.util
import math
import sys
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

ROOT = Path.cwd().resolve()
ENGINE = ROOT / "private/assets/official/sample_submission/sample_submission"
CANARY = ROOT / ".chatgpt/tmp/search_feasibility_canary.py"
sys.path.insert(0, str(ENGINE))

from cg.api import all_attack, all_card_data, search_end, search_release, search_step, to_observation_class

_spec = importlib.util.spec_from_file_location("symbolic_canary", CANARY)
assert _spec and _spec.loader
_canary = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _canary
_spec.loader.exec_module(_canary)

PF_PATH = ROOT / ".chatgpt/tmp/dragapult-modern-research/arena-agents/flg-nf-dawn3-petrel3/policy_features.py"
_pf_spec = importlib.util.spec_from_file_location("symbolic_policy_features", PF_PATH)
assert _pf_spec and _pf_spec.loader
pf = importlib.util.module_from_spec(_pf_spec)
sys.modules[_pf_spec.name] = pf
_pf_spec.loader.exec_module(pf)

CARD = {int(c.cardId): c for c in all_card_data()}
ATTACK = {int(a.attackId): a for a in all_attack()}

# Our fixed engine pieces.  Opponent scoring is deliberately generic.
DARK = 7
MUNKIDORI = 112
IMPIDIMP = 646
MORGREM = 647
GRIM = 648
CANDY = 1079
STAMP = 1080
POFFIN = 1086
STRETCHER = 1097
POKEGEAR = 1122
POKEPAD = 1152
BOSS = 1182
PETREL = 1219
LILLIE = 1227
DAWN = 1231
SPIKEMUTH = 1259

ROOT_CAP = 14
MAIN_CAP = 10
EFFECT_CAP = 20
DEPTH = 10
WIDTH = 6
PER_ROOT_EXPANSIONS = 260


def _prize_value(cid: int) -> int:
    d = CARD.get(int(cid))
    if d is None:
        return 1
    if bool(getattr(d, "megaEx", False)):
        return 3
    if bool(getattr(d, "ex", False)):
        return 2
    return 1


def _energy_count(p) -> int:
    if p is None:
        return 0
    cards = getattr(p, "energyCards", None)
    if cards is not None:
        return len(cards)
    return len(getattr(p, "energies", None) or [])


def _damage(p) -> int:
    if p is None:
        return 0
    return max(0, int(getattr(p, "maxHp", 0) or 0) - int(getattr(p, "hp", 0) or 0))


def _ready_attack_damage(p) -> int:
    """Conservative generic public-board attack estimate.

    It intentionally does not attempt to resolve conditional text.  The engine search
    handles exact tactical effects on our turn; this is only a boundary-risk feature.
    """
    if p is None:
        return 0
    data = CARD.get(int(p.id))
    if data is None:
        return 0
    energies = list(getattr(p, "energies", None) or [])
    n = len(energies)
    best = 0
    for aid in getattr(data, "attacks", None) or []:
        a = ATTACK.get(int(aid))
        if a is None:
            continue
        cost = len(getattr(a, "energies", None) or [])
        if n >= cost:
            best = max(best, int(getattr(a, "damage", 0) or 0))
            text = (getattr(a, "text", "") or "").lower()
            # Conditional attacks with zero/base-small printed damage are dangerous;
            # give them a modest floor rather than pretending they are harmless.
            if any(k in text for k in ("for each", "times", "more damage", "damage for each")):
                best = max(best, 80)
    return best


def _ability_utility(cid: int) -> float:
    data = CARD.get(int(cid))
    if data is None:
        return 0.0
    value = 0.0
    for skill in getattr(data, "skills", None) or []:
        text = (getattr(skill, "text", "") or "").lower()
        value += 8.0
        if "draw" in text:
            value += 10.0
        if "search your deck" in text:
            value += 10.0
        if "attach" in text and "energy" in text:
            value += 14.0
        if "damage counter" in text:
            value += 12.0
        if "prevent all damage" in text:
            value += 14.0
    return value


def _pokemon_board_value(p, own: bool) -> float:
    if p is None:
        return 0.0
    cid = int(p.id)
    hp = max(0, int(p.hp))
    mh = max(1, int(p.maxHp))
    energy = _energy_count(p)
    base = 8.0 + 20.0 * hp / mh + 8.0 * energy + 4.0 * _prize_value(cid)
    base += _ability_utility(cid)
    base += 0.08 * _ready_attack_damage(p)
    if own:
        # Our fixed-deck engine values. These are strategy semantics, not matchup IDs.
        if cid == GRIM:
            base += 34.0 + 28.0 * int(energy >= 2)
        elif cid == MORGREM:
            base += 20.0
        elif cid == IMPIDIMP:
            base += 13.0
        elif cid == MUNKIDORI:
            base += 23.0 + 19.0 * int(energy >= 1)
    return base


def _hand_resource_score(ps) -> float:
    hand = getattr(ps, "hand", None)
    if hand is None:
        return 0.0
    ids = Counter(int(c.id) for c in hand if c is not None)
    score = 0.8 * len(hand)
    score += 6.0 * min(2, ids[DARK])
    score += 7.0 * min(1, ids[CANDY])
    score += 7.0 * min(1, ids[STRETCHER])
    score += 5.0 * min(1, ids[POFFIN])
    score += 5.0 * min(1, ids[POKEPAD])
    score += 4.0 * min(1, ids[POKEGEAR])
    score += 8.0 * min(1, ids[BOSS])
    score += 6.0 * min(1, ids[STAMP])
    score += 4.0 * min(1, ids[PETREL] + ids[LILLIE] + ids[DAWN])
    return score


def _engine_structure(ps) -> tuple[int, int, int, int, int, int]:
    cards = [p for p in list(ps.active) + list(ps.bench) if p is not None]
    line = sum(int(p.id) in (IMPIDIMP, MORGREM, GRIM) for p in cards)
    grim = sum(int(p.id) == GRIM for p in cards)
    ready_grim = sum(int(p.id) == GRIM and _energy_count(p) >= 2 for p in cards)
    developing = sum(int(p.id) in (IMPIDIMP, MORGREM) for p in cards)
    munki = sum(int(p.id) == MUNKIDORI for p in cards)
    live_munki = sum(int(p.id) == MUNKIDORI and _energy_count(p) >= 1 for p in cards)
    return line, grim, ready_grim, developing, munki, live_munki


_ENERGY_SYMBOL = {"G": 1, "R": 2, "W": 3, "L": 4, "P": 5, "F": 6, "D": 7, "M": 8}


def _attached_energy_types(p) -> list[int]:
    out = []
    for card in list(getattr(p, "energyCards", None) or []):
        data = CARD.get(int(card.id))
        out.append(int(getattr(data, "energyType", 0) or 0) if data is not None else 0)
    return out


def _can_pay_public_attack(p, attack) -> bool:
    """Conservative public-energy payment test.

    Special Energy with unknown/flexible text is treated as flexible rather than
    silently declaring a visible attacker offline. This is a threat estimator;
    exact legality remains the native engine's responsibility.
    """
    attached = _attached_energy_types(p)
    costs = list(getattr(attack, "energies", None) or [])
    if len(attached) < len(costs):
        return False
    remaining = list(attached)
    flexible = remaining.count(0)
    remaining = [value for value in remaining if value != 0]
    for need in [int(value) for value in costs if int(value) != 0]:
        if need in remaining:
            remaining.remove(need)
        elif flexible:
            flexible -= 1
        else:
            return False
    colorless = sum(int(value) == 0 for value in costs)
    return len(remaining) + flexible >= colorless


def _weakness_adjust(damage: int, attacker, defender, attack_text: str, counters: bool = False) -> int:
    if damage <= 0 or counters or defender is None:
        return max(0, int(damage))
    text = (attack_text or "").lower()
    if "isn’t affected by weakness" in text or "isn't affected by weakness" in text:
        return int(damage)
    adata = CARD.get(int(attacker.id)) if attacker is not None else None
    dtype = int(getattr(adata, "energyType", 0) or 0) if adata is not None else 0
    ddata = CARD.get(int(defender.id))
    if ddata is None or dtype == 0:
        return int(damage)
    if int(getattr(ddata, "weakness", 0) or 0) == dtype:
        damage *= 2
    if (
        int(getattr(ddata, "resistance", 0) or 0) == dtype
        and "isn’t affected by weakness or resistance" not in text
        and "isn't affected by weakness or resistance" not in text
    ):
        damage = max(0, damage - 30)
    return int(damage)


def _basic_energy_in_discard(ps, energy_type: int) -> int:
    total = 0
    for card in list(getattr(ps, "discard", None) or []):
        data = CARD.get(int(card.id))
        if data is None:
            continue
        if int(getattr(data, "cardType", 0) or 0) == 5 and int(getattr(data, "energyType", 0) or 0) == int(energy_type):
            total += 1
    return total


def _public_attack_threat(attacker, defender, attacker_ps, defender_ps) -> tuple[int, bool, bool]:
    """Return (best_damage_or_counters, delayed_auto_ko, uncertain_high_variance).

    Only public state and official attack text are used. Common conditional forms
    in the current card pool are evaluated explicitly; stochastic top-deck attacks
    contribute a ceiling and are marked uncertain so they cannot masquerade as an
    exact next-turn KO.
    """
    if attacker is None:
        return (0, False, False)
    data = CARD.get(int(attacker.id))
    if data is None:
        return (0, False, False)
    best = 0
    delayed = False
    uncertain = False
    for aid in list(getattr(data, "attacks", None) or []):
        attack = ATTACK.get(int(aid))
        if attack is None or not _can_pay_public_attack(attacker, attack):
            continue
        text = (getattr(attack, "text", "") or "")
        low = text.lower()
        damage = int(getattr(attack, "damage", 0) or 0)
        counters = False

        # e.g. Myriad Leaf Shower: 30 more for each Energy on both Active.
        import re
        m = re.search(r"does (\d+) more damage for each energy attached to both active", low)
        if m:
            damage += int(m.group(1)) * (_energy_count(attacker) + _energy_count(defender))

        # e.g. Alakazam Powerful Hand: 2 counters per card in the attacker's hand.
        m = re.search(r"place (\d+) damage counters?.*for each card in your hand", low)
        if m:
            damage = 10 * int(m.group(1)) * int(getattr(attacker_ps, "handCount", 0) or 0)
            counters = True

        # e.g. Kyogre Riptide: 20 per Basic {W} Energy in discard.
        m = re.search(r"does (\d+) damage for each basic \{([grwl pfdm])\} energy card in your discard pile", low.replace("{l}", "{l}"))
        if m:
            symbol = m.group(2).upper().replace(" ", "")
            et = _ENERGY_SYMBOL.get(symbol)
            if et is not None:
                damage = int(m.group(1)) * _basic_energy_in_discard(attacker_ps, et)

        # e.g. Mega Abomasnow Hammer-lanche. Exact top cards are hidden; use the
        # public maximum as a risk ceiling but mark it uncertain.
        m = re.search(r"discard the top (\d+) cards of your deck, and this attack does (\d+) damage for each basic \{([grwlpfdm])\} energy card", low)
        if m:
            damage = max(damage, int(m.group(1)) * int(m.group(2)))
            uncertain = True

        if "will be knocked out" in low and "end of your opponent’s next turn" in low:
            delayed = True

        damage = _weakness_adjust(damage, attacker, defender, low, counters=counters)
        best = max(best, int(damage))
    return (best, delayed, uncertain)


def _greedy_prize_turns(targets, per_hit: int, required_prizes: int, first_bonus: int = 0) -> int:
    """Approximate attacks needed to claim visible prizes with a fixed damage packet."""
    if required_prizes <= 0:
        return 0
    if per_hit <= 0:
        return 9
    routes = []
    for index, p in enumerate(targets):
        hp = max(1, int(getattr(p, "hp", 0) or 0))
        bonus = first_bonus if index == 0 else 0
        hits = max(1, math.ceil(max(1, hp - bonus) / per_hit))
        routes.append((hits / max(1, _prize_value(int(p.id))), hits, -_prize_value(int(p.id))))
    routes.sort()
    turns = 0
    prizes = 0
    for _, hits, neg_prize in routes:
        turns += int(hits)
        prizes += -int(neg_prize)
        if prizes >= required_prizes:
            return min(9, turns)
    # Future unseen replacements are unknown. Penalize each missing prize by one
    # additional attack rather than claiming an artificial forced win.
    return min(9, turns + max(0, required_prizes - prizes))


def race_macro_terms(obs, root_player: int) -> tuple[int, int, int, int, int]:
    """Public turns-to-win / turns-to-loss approximation.

    This is a proposal-ranking macro, never independent authority. The native
    adversarial verifier still decides whether a proposed root is safe.
    """
    st = obs.current
    if st is None:
        return (0, -9, 0, -9, 0)
    me = st.players[root_player]
    opp = st.players[1 - root_player]
    own_field = [p for p in list(me.active) + list(me.bench) if p is not None]
    opp_field = [p for p in list(opp.active) + list(opp.bench) if p is not None]
    ma = me.active[0] if me.active else None
    oa = opp.active[0] if opp.active else None

    _, _, ready_grim, developing, _, live_munki = _engine_structure(me)
    own_damage = sum(_damage(p) for p in own_field)
    transfer = min(30 * live_munki, (own_damage // 10) * 10)
    setup_delay = 0 if ready_grim else (1 if developing else 2)
    own_turns = setup_delay + _greedy_prize_turns(opp_field, 180, len(me.prize), first_bonus=transfer)
    own_turns = min(9, own_turns)

    threat, delayed_ko, uncertain = _public_attack_threat(oa, ma, opp, me)
    opp_required = len(opp.prize)
    immediate_ko = bool(ma is not None and threat >= int(ma.hp) > 0 and not uncertain)
    immediate_win = bool(immediate_ko and _prize_value(int(ma.id)) >= opp_required)
    if delayed_ko and ma is not None and _prize_value(int(ma.id)) >= opp_required:
        immediate_win = True

    if delayed_ko:
        opp_turns = 1 + _greedy_prize_turns(own_field[1:], max(1, threat), max(0, opp_required - _prize_value(int(ma.id)) if ma is not None else opp_required))
    elif threat > 0:
        opp_turns = _greedy_prize_turns(own_field, threat, opp_required)
    else:
        opp_turns = 9
    opp_turns = min(9, opp_turns)

    next_shadow_prize = 0
    boss_in_hand = any(int(c.id) == BOSS for c in list(getattr(me, "hand", None) or []))
    targetable = list(opp.active)
    if boss_in_hand:
        targetable += list(opp.bench)
    for p in targetable:
        if p is None:
            continue
        if int(p.hp) <= 180 + transfer:
            next_shadow_prize = max(next_shadow_prize, _prize_value(int(p.id)))

    race_margin = max(-9, min(9, opp_turns - own_turns))
    return (
        int(not immediate_win),
        int(race_margin),
        int(next_shadow_prize),
        int(-own_turns),
        int(opp_turns),
    )


def strategic_scalar(obs, root_player: int) -> float:
    """Generic public strategic value for pruning and non-terminal boundaries."""
    st = obs.current
    if st is None:
        return -1e9
    result = int(st.result)
    if result == root_player:
        return 1e9
    if result == 1 - root_player:
        return -1e9
    if result == 2:
        return 0.0

    me = st.players[root_player]
    opp = st.players[1 - root_player]
    score = 0.0

    # Prize race is the primary non-terminal objective.
    score += 330.0 * (len(opp.prize) - len(me.prize))

    own_cards = [p for p in list(me.active) + list(me.bench) if p is not None]
    opp_cards = [p for p in list(opp.active) + list(opp.bench) if p is not None]
    score += sum(_pokemon_board_value(p, True) for p in own_cards)
    score -= sum(_pokemon_board_value(p, False) for p in opp_cards)

    line, grim, ready_grim, developing, munki, live_munki = _engine_structure(me)
    # Actual Dawn/Petrel structure: three useful Marnie bodies gives attacker
    # continuity, while a second ready Grimmsnarl is a major prize-race buffer.
    score += 18.0 * min(3, line)
    score += 52.0 * ready_grim
    score += 14.0 * min(2, developing)
    score += 22.0 * min(2, munki)
    score += 30.0 * min(2, live_munki)
    if ready_grim >= 2:
        score += 42.0
    if line == 0:
        score -= 70.0
    elif line == 1 and int(st.turn) >= 4:
        score -= 24.0

    score += _hand_resource_score(me)
    # Visible hand/board evolution synergies.  These are deterministic tactical
    # resources, not learned features: Rare Candy + mature Impidimp + Grimmsnarl
    # and the ordinary Impidimp->Morgrem->Grimmsnarl chain both shorten setup.
    hand = getattr(me, "hand", None) or []
    hand_ids = Counter(int(card.id) for card in hand if card is not None)
    own_field = [p for p in list(me.active) + list(me.bench) if p is not None]
    mature_imp = any(int(p.id) == IMPIDIMP and not bool(p.appearThisTurn) for p in own_field)
    mature_morg = any(int(p.id) == MORGREM and not bool(p.appearThisTurn) for p in own_field)
    if mature_imp and hand_ids[CANDY] and hand_ids[GRIM]:
        score += 38.0
    if mature_imp and hand_ids[MORGREM]:
        score += 20.0
    if mature_morg and hand_ids[GRIM]:
        score += 30.0
    # A Darkness Energy on Munkidori is uniquely valuable because Punk Up cannot
    # attach to it; it enables Adrena-Brain whenever damage exists to move.
    own_damage = sum(_damage(p) for p in own_field)
    if live_munki and own_damage >= 10:
        score += 18.0 * min(2, live_munki)
    score += 0.8 * int(me.handCount)
    # Large opponent hands are a distinct danger mode from Energy acceleration
    # (notably in Psychic/development decks). Keep this generic and nonlinear.
    opp_hand = int(opp.handCount)
    score -= 2.2 * opp_hand
    if opp_hand >= 6:
        score -= 3.0 * (opp_hand - 5)
    score += 0.15 * (int(me.deckCount) - int(opp.deckCount))

    own_energy = sum(_energy_count(p) for p in own_cards)
    opp_energy = sum(_energy_count(p) for p in opp_cards)
    score += 5.0 * own_energy
    # Cross-family loss audits consistently show opponent board Energy as the
    # strongest public danger signal. Penalize established acceleration
    # nonlinearly instead of treating all attached Energy as symmetric material.
    score -= 13.0 * opp_energy
    if opp_energy >= 3:
        score -= 10.0 * (opp_energy - 2)

    # Prize liabilities/opportunities are separate from raw board strength.
    score -= 12.0 * sum(max(0, _prize_value(int(p.id)) - 1) for p in own_cards)
    score += 12.0 * sum(max(0, _prize_value(int(p.id)) - 1) for p in opp_cards)

    # Immediate exposed-active risk. Public ready damage is a lower bound; this
    # makes the engine preserve attackers against obviously online threats.
    ma = me.active[0] if me.active else None
    oa = opp.active[0] if opp.active else None
    if ma is not None and oa is not None:
        incoming = _ready_attack_damage(oa)
        hp = int(ma.hp)
        if incoming >= hp > 0:
            score -= 120.0 + 35.0 * _prize_value(int(ma.id))
        elif incoming > 0:
            score -= 0.20 * incoming
        # Damage already placed is future tactical currency for our transfer engine.
        if int(ma.id) == GRIM:
            score -= 0.16 * _damage(ma)

    # At a turn boundary CABT exposes the root player's *actual* legal MAIN
    # menu. This is stronger evidence than guessing readiness from card text.
    # It also gives minimax a useful pruning signal while the opponent is still
    # acting: visible attack/evolution/ability availability is immediate tempo.
    if obs.select is not None and int(obs.select.context) == 0:
        option_types = [int(option.type) for option in obs.select.option]
        attacks = option_types.count(13)
        evolves = option_types.count(9)
        abilities = option_types.count(10)
        attaches = option_types.count(8)
        if int(st.yourIndex) == root_player:
            score += 42.0 * int(attacks > 0)
            score += 14.0 * min(2, evolves)
            score += 10.0 * min(2, abilities)
            score += 6.0 * int(attaches > 0)
            if len(me.prize) <= 2 and attacks > 0:
                score += 28.0
            if int(st.turn) >= 5 and attacks == 0:
                score -= 24.0
        else:
            score -= 34.0 * int(attacks > 0)
            score -= 9.0 * min(2, evolves)
            score -= 7.0 * min(2, abilities)

    stadium = st.stadium[0] if st.stadium else None
    if stadium is not None and int(stadium.id) == SPIKEMUTH and int(stadium.playerIndex) == root_player:
        score += 12.0

    return score


def attacker_macro_terms(obs, root_player: int) -> tuple[int, int, int, int, int, int, int]:
    """Lexicographic attacker-continuity terms for fast proposal search.

    Fresh pure-Dawn diagnostics show that ready Grimmsnarl availability separates
    wins from losses more clearly than raw field size. These deterministic terms
    therefore rank before the generic board scalar.
    """
    st = obs.current
    if st is None:
        return (0, 0, 0, 0, 0, 0, 0)
    me = st.players[root_player]
    own_field = [p for p in list(me.active) + list(me.bench) if p is not None]
    active = me.active[0] if me.active else None
    ready_grim = sum(int(p.id) == GRIM and _energy_count(p) >= 2 for p in own_field)
    active_ready = int(active is not None and int(active.id) == GRIM and _energy_count(active) >= 2)
    reserve_ready = max(0, ready_grim - active_ready)
    stage_points = sum(
        3 if int(p.id) == GRIM else 2 if int(p.id) == MORGREM else 1 if int(p.id) == IMPIDIMP else 0
        for p in own_field
    )
    powered_munki = sum(int(p.id) == MUNKIDORI and _energy_count(p) >= 1 for p in own_field)
    shadow_available = 0
    attack_available = 0
    if obs.select is not None and int(obs.select.context) == 0 and int(st.yourIndex) == root_player:
        for option in obs.select.option:
            if int(option.type) == 13:
                attack_available = 1
                if int(option.attackId or 0) == 937:
                    shadow_available = 1
    return (
        int(shadow_available),
        int(active_ready),
        int(ready_grim),
        int(reserve_ready),
        int(stage_points),
        int(min(2, powered_munki)),
        int(attack_available),
    )


def strategic_vector(obs, root_player: int, root_turn: int, start_prizes: int) -> tuple:
    st = obs.current
    if st is None:
        return (-9, -9, *([0] * 12), -1e9)
    result = int(st.result)
    taken = start_prizes - len(st.players[root_player].prize)
    # Deadline/race terms rank before structural development. A larger tuple means
    # safer from an immediate loss, a better estimated prize-race margin, and a
    # shorter route to our remaining prizes. These remain proposal features only.
    race = race_macro_terms(obs, root_player)
    attacker = attacker_macro_terms(obs, root_player)
    macro = (*race, *attacker)
    scalar = strategic_scalar(obs, root_player)
    if result == root_player:
        return (6, taken, *macro, 1e9)
    if result == 1 - root_player:
        return (-6, taken, *macro, -1e9)
    if result == 2:
        return (0, taken, *macro, 0.0)
    return (3, taken, *macro, scalar)


def synthetic_public_deck(obs, player: int) -> list[int]:
    """Build a legal-length hidden multiset using only public cards plus filler Energy.

    Search stops before the opponent acts, so hidden identities are intentionally not
    used as strategic evidence. This keeps current-turn planning matchup-agnostic.
    """
    ps = obs.current.players[player]
    ids: list[int] = []

    def add_card(c):
        if c is not None:
            ids.append(int(c.id))

    def add_pokemon(p):
        if p is None:
            return
        ids.append(int(p.id))
        for c in p.energyCards:
            add_card(c)
        for c in p.tools:
            add_card(c)
        for c in p.preEvolution:
            add_card(c)

    for p in ps.active:
        add_pokemon(p)
    for p in ps.bench:
        add_pokemon(p)
    for c in ps.discard:
        add_card(c)
    if ps.hand is not None:
        for c in ps.hand:
            add_card(c)
    for c in obs.current.stadium:
        if c is not None and int(c.playerIndex) == player:
            add_card(c)
    if len(ids) > 60:
        raise RuntimeError(f"visible cards exceed deck size: {len(ids)}")
    return ids + [DARK] * (60 - len(ids))


def determinize_public(obs, own_deck: list[int], root_player: int, seed: int):
    fake = synthetic_public_deck(obs, 1 - root_player)
    deck0, deck1 = (own_deck, fake) if root_player == 0 else (fake, own_deck)
    return _canary.determinize(obs, deck0, deck1, seed, known_transients={0: [], 1: []}, known_hidden_active={})


def _action_rank(obs, action: tuple[int, ...]) -> tuple:
    types = [int(obs.select.option[i].type) for i in action]
    # Ordering only. Native successor evaluation decides value.
    return (
        int(13 in types),  # attack
        int(9 in types),   # evolve
        int(10 in types),  # ability
        int(8 in types),   # attach
        int(7 in types),   # play
        int(12 in types),  # retreat
        -sum(action),
    )


def legal_actions(obs, cap: int, fallback=None) -> list[tuple[int, ...]]:
    raw = _canary.legal_actions(obs, cap=max(cap * 5, 64))
    raw.sort(key=lambda a: _action_rank(obs, a), reverse=True)
    out: list[tuple[int, ...]] = []
    fb = tuple(fallback) if fallback is not None else None
    if fb is not None:
        out.append(fb)
    for a in raw:
        a = tuple(a)
        if a not in out:
            out.append(a)
        if len(out) >= cap:
            break
    return out


def semantic_signature(raw: dict, action) -> tuple:
    """Stable-enough semantic identity for current-turn path execution.

    Hidden deck/LOOKING serials are deliberately omitted because determinized
    search may assign different hidden serials. Public hand/discard/in-play
    serials are retained when they identify a concrete live card or target.
    """
    options = (raw.get("select") or {}).get("option") or []
    out = []
    for index in action:
        if not isinstance(index, int) or not 0 <= index < len(options):
            return tuple()
        option = options[index]
        sem = pf.semantic(raw, option)
        source_zone = int(sem.get("source_zone", 0) or 0)
        target_area = int(sem.get("target_area", 0) or 0)
        source_serial = int(sem.get("source_serial", -1) or -1) if source_zone in (2, 3, 4, 5) else -1
        target_serial = int(sem.get("target_serial", -1) or -1) if target_area in (4, 5) else -1
        out.append((
            int(sem.get("type", -1)),
            int(sem.get("source_id", 0)),
            int(sem.get("target_id", 0)),
            int(sem.get("attack_id", 0)),
            int(sem.get("area", 0)),
            int(sem.get("inplay_area", 0)),
            int(sem.get("inplay_index", -1)),
            source_serial,
            target_serial,
            int(option.get("number", -1) if option.get("number") is not None else -1),
        ))
    return tuple(out)


def functional_signature(raw: dict, action) -> tuple:
    """Canonical game-action identity that ignores interchangeable physical copies.

    Two identical cards from hand/deck/discard that produce the same effect on the
    same public target are strategically equivalent. In-play source serials remain
    significant because two same-ID Pokemon can carry different damage/Energy.
    """
    options = (raw.get("select") or {}).get("option") or []
    out = []
    for index in action:
        if not isinstance(index, int) or not 0 <= index < len(options):
            return tuple()
        option = options[index]
        sem = pf.semantic(raw, option)
        source_zone = int(sem.get("source_zone", 0) or 0)
        target_area = int(sem.get("target_area", 0) or 0)
        source_serial = int(sem.get("source_serial", -1) or -1) if source_zone in (4, 5) else -1
        target_serial = int(sem.get("target_serial", -1) or -1) if target_area in (4, 5) else -1
        out.append((
            int(sem.get("type", -1)), int(sem.get("source_id", 0)),
            int(sem.get("target_id", 0)), int(sem.get("attack_id", 0)),
            int(sem.get("area", 0)), int(sem.get("inplay_area", 0)),
            int(sem.get("inplay_index", -1)), source_serial, target_serial,
            int(option.get("number", -1) if option.get("number") is not None else -1),
        ))
    return tuple(out)


class Node:
    __slots__ = ("state", "path", "semantic_path")
    def __init__(self, state, path, semantic_path):
        self.state = state
        self.path = path
        self.semantic_path = semantic_path


def _search_root(root, root_action, root_player: int, root_turn: int, start_prizes: int):
    root_raw = asdict(root.observation)
    root_semantic = semantic_signature(root_raw, root_action)
    first = search_step(root.searchId, list(root_action))
    expansions = 1
    front = [Node(first, [tuple(root_action)], [root_semantic])]
    best_boundary = None
    best_path = None
    best_semantic_path = None
    best_mid = strategic_vector(first.observation, root_player, root_turn, start_prizes)

    for _depth in range(1, DEPTH):
        nxt: list[Node] = []
        for node in front:
            obs = node.state.observation
            st = obs.current
            if st is None:
                continue
            if int(st.result) != -1 or obs.select is None or int(st.yourIndex) != root_player or int(st.turn) != root_turn:
                v = strategic_vector(obs, root_player, root_turn, start_prizes)
                if best_boundary is None or v > best_boundary:
                    best_boundary = v
                    best_path = list(node.path)
                    best_semantic_path = list(node.semantic_path)
                try:
                    search_release(node.state.searchId)
                except Exception:
                    pass
                continue
            if expansions >= PER_ROOT_EXPANSIONS:
                try:
                    search_release(node.state.searchId)
                except Exception:
                    pass
                continue
            cap = MAIN_CAP if int(obs.select.context) == 0 else EFFECT_CAP
            for action in legal_actions(obs, cap):
                if expansions >= PER_ROOT_EXPANSIONS:
                    break
                try:
                    child = search_step(node.state.searchId, list(action))
                except Exception:
                    continue
                expansions += 1
                v = strategic_vector(child.observation, root_player, root_turn, start_prizes)
                if v > best_mid:
                    best_mid = v
                step_semantic = semantic_signature(asdict(obs), action)
                nxt.append(Node(child, node.path + [tuple(action)], node.semantic_path + [step_semantic]))
            try:
                search_release(node.state.searchId)
            except Exception:
                pass
        if not nxt:
            front = []
            break
        nxt.sort(key=lambda n: strategic_vector(n.state.observation, root_player, root_turn, start_prizes), reverse=True)
        front = nxt[:WIDTH]
        for node in nxt[WIDTH:]:
            try:
                search_release(node.state.searchId)
            except Exception:
                pass
        if best_boundary is not None and best_boundary[0] == 6:
            break

    for node in front:
        v = strategic_vector(node.state.observation, root_player, root_turn, start_prizes)
        if best_boundary is None or v > best_boundary:
            best_boundary = v
            best_path = list(node.path)
            best_semantic_path = list(node.semantic_path)
        try:
            search_release(node.state.searchId)
        except Exception:
            pass

    # A root can hit the expansion cap before reaching an explicit end-of-turn
    # boundary.  Keep it comparable, but below any fully resolved boundary, by
    # using its best partial state as a conservative fallback.
    if best_boundary is None:
        # Preserve the full macro vector but rank a capped partial line below any
        # complete non-terminal turn boundary.
        best_boundary = (2, *best_mid[1:])

    return {
        "root_action": tuple(root_action),
        "boundary": best_boundary,
        "mid": best_mid,
        "path": best_path,
        "semantic_path": best_semantic_path,
        "expansions": expansions,
    }


def solve_particle(raw, own_deck: list[int], seed: int, fallback):
    obs = to_observation_class(raw)
    rp = int(obs.current.yourIndex)
    rt = int(obs.current.turn)
    start_prizes = len(obs.current.players[rp].prize)
    det = determinize_public(obs, own_deck, rp, seed)
    root = _canary.begin(obs, det)
    roots = legal_actions(obs, ROOT_CAP, fallback=fallback)
    rows = []
    started = time.perf_counter()
    try:
        for a in roots:
            rows.append(_search_root(root, a, rp, rt, start_prizes))
    finally:
        search_end()

    fb = tuple(fallback)
    def key(r):
        return (r["boundary"], r["mid"], r["root_action"] == fb)
    best = max(rows, key=key)
    fbrow = next((r for r in rows if r["root_action"] == fb), None)
    if fbrow is not None and key(best) <= key(fbrow):
        best = fbrow
    return {
        "fallback": fb,
        "suggested": best["root_action"],
        "rows": rows,
        "seconds": time.perf_counter() - started,
        "expansions": sum(r["expansions"] for r in rows),
    }


def solve(raw, own_deck: list[int], seed_base: int, fallback, particles: int = 2):
    started = time.perf_counter()
    parts = [solve_particle(raw, own_deck, seed_base + 7919 * i, fallback) for i in range(particles)]
    fb = tuple(fallback)
    maps = [{r["root_action"]: r for r in p["rows"]} for p in parts]
    common = set(maps[0])
    for m in maps[1:]:
        common &= set(m)

    def robust_key(a):
        rr = [m[a] for m in maps]
        boundaries = [r["boundary"] for r in rr]
        worst = min(boundaries)
        worst_macro = tuple(worst[:-1])
        mean_scalar = sum(float(v[-1]) for v in boundaries) / len(boundaries)
        # Final root authority is macro-first. If Dawn and a challenger achieve
        # the same worst-case terminal/prize/attacker-continuity vector, Dawn
        # wins regardless of scalar cleanliness. Scalar only separates two
        # non-fallback roots that are otherwise macro-equivalent.
        return (worst_macro, a == fb, mean_scalar)

    best = max(common, key=robust_key) if common else fb
    if fb in common and robust_key(best) <= robust_key(fb):
        best = fb
    # Physical duplicate copies are not strategic disagreements. Keep Dawn's
    # already-synchronized action whenever the functional action is identical.
    if best != fb and functional_signature(raw, best) == functional_signature(raw, fb):
        best = fb

    plan = None
    if best in common:
        best_rows = [m[best] for m in maps]
        semantic_paths = [row.get("semantic_path") for row in best_rows]
        if semantic_paths and all(path is not None and path for path in semantic_paths):
            prefix = []
            for step_group in zip(*semantic_paths):
                if all(step == step_group[0] for step in step_group[1:]):
                    prefix.append(step_group[0])
                else:
                    break
            if prefix:
                complete_consensus = all(len(path) == len(prefix) for path in semantic_paths)
                plan = {
                    "root_action": list(best),
                    "semantic_path": [[list(sig) for sig in step] for step in prefix],
                    "steps": len(prefix),
                    "complete_consensus": bool(complete_consensus),
                    "particle_path_lengths": [len(path) for path in semantic_paths],
                    "consensus_particles": len(semantic_paths),
                }

    return {
        "fallback": list(fb),
        "suggested": list(best),
        "disagrees": best != fb,
        "plan": plan,
        "fallback_key": None if fb not in common else robust_key(fb),
        "suggested_key": None if best not in common else robust_key(best),
        "particles": parts,
        "seconds": time.perf_counter() - started,
        "expansions": sum(p["expansions"] for p in parts),
    }
