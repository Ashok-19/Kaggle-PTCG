from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path

ROOT = Path.cwd().resolve()
BASE = ROOT / ".chatgpt/tmp/current-engine-v1/symbolic_turn_planner.py"
_spec = importlib.util.spec_from_file_location("symbolic_turn_base", BASE)
assert _spec and _spec.loader
s = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = s
_spec.loader.exec_module(s)

# Own-turn exploration remains broad enough to discover sequencing improvements.
OWN_ROOT_CAP = 12
OWN_MAIN_CAP = 9
OWN_EFFECT_CAP = 18
OWN_DEPTH = 9
OWN_WIDTH = 5
OWN_PER_ROOT_EXPANSIONS = 220
OWN_LINES_PER_ROOT = 3

# Opponent-response search is intentionally adversarial and compact.  It searches
# the complete next opponent turn, not only an immediate attack.
OPP_MAIN_CAP = 12
OPP_EFFECT_CAP = 20
OPP_DEPTH = 18
OPP_WIDTH = 5
OPP_EXPANSION_CAP = 850


class Node:
    __slots__ = ("state", "path", "vector")

    def __init__(self, state, path, vector):
        self.state = state
        self.path = path
        self.vector = vector


def _release(state) -> None:
    try:
        s.search_release(state.searchId)
    except Exception:
        pass


def outcome_vector(obs, root_player: int, start_prizes: tuple[int, int]) -> tuple:
    """Lexicographic game objective from the root player's perspective.

    Exact terminal and prize outcomes dominate the symbolic strategic scalar.
    This prevents a prettier board from compensating for giving away prizes.
    """
    cur = obs.current
    if cur is None:
        return (-9, -9, -9, -1e9)
    result = int(cur.result)
    if result == root_player:
        terminal = 6
    elif result == 1 - root_player:
        terminal = -6
    elif result == 2:
        terminal = 0
    else:
        terminal = 3
    my_taken = start_prizes[root_player] - len(cur.players[root_player].prize)
    opp_taken = start_prizes[1 - root_player] - len(cur.players[1 - root_player].prize)
    return (terminal, int(my_taken), int(-opp_taken), float(s.strategic_scalar(obs, root_player)))


def _own_boundary(obs, root_player: int, root_turn: int) -> bool:
    cur = obs.current
    return (
        cur is None
        or int(cur.result) != -1
        or obs.select is None
        or int(cur.yourIndex) != root_player
        or int(cur.turn) != root_turn
    )


def _opponent_boundary(obs, root_player: int, opponent_turn: int) -> bool:
    cur = obs.current
    return (
        cur is None
        or int(cur.result) != -1
        or obs.select is None
        or int(cur.yourIndex) == root_player
        or int(cur.turn) != opponent_turn
    )


def _ordered(obs, cap: int, preferred=None, maximize: bool = True):
    # Reuse the base planner's functional dedup and context-aware action generator.
    # In particular, DISCARD is enumerated as distinct card sets rather than
    # permutations, so opponent-response budgets cover strategic alternatives
    # instead of reordered copies of the same choice.
    actions = s.legal_actions(obs, cap=max(128, cap * 8))
    actions.sort(key=lambda a: s._action_rank(obs, tuple(a)), reverse=maximize)
    out = []
    pref = tuple(preferred) if preferred is not None else None
    if pref is not None:
        out.append(pref)

    # ATTACK and END are proof-producing turn boundaries. Keep them even when a
    # large menu of development actions would otherwise push them past the cap.
    if obs.select is not None:
        for action in actions:
            types = [int(obs.select.option[i].type) for i in action]
            action = tuple(action)
            if (13 in types or 14 in types) and action not in out:
                out.append(action)

    for action in actions:
        action = tuple(action)
        if action not in out:
            out.append(action)
        if len(out) >= cap:
            break
    return out


def complete_own_lines(root, root_action, root_player: int, root_turn: int, start_prizes: tuple[int, int]):
    """Enumerate native effect selections and keep top complete own-turn lines."""
    first = s.search_step(root.searchId, list(root_action))
    expansions = 1
    front = [Node(first, [tuple(root_action)], outcome_vector(first.observation, root_player, start_prizes))]
    completed: list[Node] = []

    for _depth in range(1, OWN_DEPTH):
        nxt: list[Node] = []
        for node in front:
            obs = node.state.observation
            if _own_boundary(obs, root_player, root_turn):
                completed.append(node)
                continue
            if expansions >= OWN_PER_ROOT_EXPANSIONS:
                # A capped partial line is not response-qualified.
                _release(node.state)
                continue
            cap = OWN_MAIN_CAP if int(obs.select.context) == 0 else OWN_EFFECT_CAP
            for action in _ordered(obs, cap, maximize=True):
                if expansions >= OWN_PER_ROOT_EXPANSIONS:
                    break
                try:
                    child = s.search_step(node.state.searchId, list(action))
                except Exception:
                    continue
                expansions += 1
                child_node = Node(
                    child,
                    node.path + [tuple(action)],
                    outcome_vector(child.observation, root_player, start_prizes),
                )
                if _own_boundary(child.observation, root_player, root_turn):
                    completed.append(child_node)
                else:
                    nxt.append(child_node)
            _release(node.state)
        if not nxt:
            front = []
            break
        nxt.sort(key=lambda n: n.vector, reverse=True)
        front = nxt[:OWN_WIDTH]
        for node in nxt[OWN_WIDTH:]:
            _release(node.state)
        if any(n.vector[0] == 6 for n in completed):
            break

    for node in front:
        if _own_boundary(node.state.observation, root_player, root_turn):
            completed.append(node)
        else:
            _release(node.state)

    completed.sort(key=lambda n: n.vector, reverse=True)
    keep = completed[:OWN_LINES_PER_ROOT]
    for node in completed[OWN_LINES_PER_ROOT:]:
        _release(node.state)
    return keep, expansions


def adversarial_response(start_state, root_player: int, start_prizes: tuple[int, int]):
    """Return the worst complete legal opponent-turn outcome for one own line."""
    obs = start_state.observation
    cur = obs.current
    if cur is None or int(cur.result) != -1 or int(cur.yourIndex) == root_player or obs.select is None:
        return outcome_vector(obs, root_player, start_prizes), 0, True
    opponent_turn = int(cur.turn)
    front = [Node(start_state, [], outcome_vector(obs, root_player, start_prizes))]
    completed: list[Node] = []
    expansions = 0

    for _depth in range(OPP_DEPTH):
        nxt: list[Node] = []
        for node in front:
            node_obs = node.state.observation
            if _opponent_boundary(node_obs, root_player, opponent_turn):
                completed.append(node)
                continue
            if expansions >= OPP_EXPANSION_CAP:
                _release(node.state)
                continue
            cap = OPP_MAIN_CAP if int(node_obs.select.context) == 0 else OPP_EFFECT_CAP
            # Attack/evolve/ability/play ordering makes dangerous branches appear
            # early, while minimax value determines which branches survive.
            for action in _ordered(node_obs, cap, maximize=True):
                if expansions >= OPP_EXPANSION_CAP:
                    break
                try:
                    child = s.search_step(node.state.searchId, list(action))
                except Exception:
                    continue
                expansions += 1
                child_node = Node(
                    child,
                    node.path + [tuple(action)],
                    outcome_vector(child.observation, root_player, start_prizes),
                )
                if _opponent_boundary(child.observation, root_player, opponent_turn):
                    completed.append(child_node)
                else:
                    nxt.append(child_node)
            _release(node.state)
        if not nxt:
            front = []
            break
        # Opponent minimizes our exact-outcome vector.
        nxt.sort(key=lambda n: n.vector)
        front = nxt[:OPP_WIDTH]
        for node in nxt[OPP_WIDTH:]:
            _release(node.state)
        if any(n.vector[0] == -6 for n in completed):
            break

    for node in front:
        if _opponent_boundary(node.state.observation, root_player, opponent_turn):
            completed.append(node)
        else:
            _release(node.state)

    if not completed:
        return None, expansions, False
    completed.sort(key=lambda n: n.vector)
    worst = completed[0]
    vector = worst.vector
    # The caller owns start_state; all descendants may now be released.
    for node in completed:
        if node.state.searchId != start_state.searchId:
            _release(node.state)
    return vector, expansions, True


def _determinize_with_known_hand(obs, own_deck: list[int], opponent_deck: list[int], seed: int, known_hand_ids=()):
    """Determinize one world while honoring exact public opponent-hand identities."""
    root_player = int(obs.current.yourIndex)
    if root_player == 0:
        det = s._canary.determinize(obs, own_deck, opponent_deck, seed)
    else:
        det = s._canary.determinize(obs, opponent_deck, own_deck, seed)
    required = [int(x) for x in known_hand_ids]
    if not required:
        return det

    from collections import Counter
    need = Counter(required)
    hand = list(det["opponent_hand"])
    deck = list(det["opponent_deck"])
    prize = list(det["opponent_prize"])
    have = Counter(hand)

    def replacement_index():
        for i, card_id in enumerate(hand):
            if have[card_id] > need.get(card_id, 0):
                return i
        return None

    for card_id, count in need.items():
        for _ in range(max(0, count - have.get(card_id, 0))):
            try:
                zone, zi = deck, deck.index(card_id)
            except ValueError:
                try:
                    zone, zi = prize, prize.index(card_id)
                except ValueError as error:
                    raise ValueError(f"known opponent hand card {card_id} absent from template residual") from error
            hi = replacement_index()
            if hi is None:
                raise ValueError("cannot reconcile exact known opponent hand with predicted hand size")
            outgoing = hand[hi]
            hand[hi] = card_id
            zone[zi] = outgoing
            have[outgoing] -= 1
            have[card_id] += 1

    det["opponent_hand"] = hand
    det["opponent_deck"] = deck
    det["opponent_prize"] = prize
    return det


def solve_particle(raw, own_deck: list[int], opponent_deck: list[int], seed: int, fallback, known_hand_ids=()):
    obs = s.to_observation_class(raw)
    root_player = int(obs.current.yourIndex)
    root_turn = int(obs.current.turn)
    start_prizes = (len(obs.current.players[0].prize), len(obs.current.players[1].prize))
    det = _determinize_with_known_hand(obs, own_deck, opponent_deck, seed, known_hand_ids)
    root = s._canary.begin(obs, det)
    fb = tuple(fallback)
    roots = _ordered(obs, OWN_ROOT_CAP, preferred=fb, maximize=True)
    values = {}
    paths = {}
    own_expansions = 0
    response_expansions = 0
    incomplete = 0
    started = time.perf_counter()

    try:
        for root_action in roots:
            lines, used = complete_own_lines(root, root_action, root_player, root_turn, start_prizes)
            own_expansions += used
            robust = []
            for line in lines:
                vector, used_response, complete = adversarial_response(line.state, root_player, start_prizes)
                response_expansions += used_response
                if complete and vector is not None:
                    robust.append((vector, list(line.path)))
                else:
                    incomplete += 1
                _release(line.state)
            if robust:
                # We choose the continuation of our own turn; opponent then chooses
                # the worst legal next turn.  Maximize that worst case.
                vector, path = max(robust, key=lambda x: x[0])
                values[root_action] = vector
                paths[root_action] = path
    finally:
        s.search_end()

    return {
        "fallback": fb,
        "values": values,
        "paths": paths,
        "own_expansions": own_expansions,
        "response_expansions": response_expansions,
        "incomplete": incomplete,
        "seconds": time.perf_counter() - started,
    }


def solve(raw, own_deck: list[int], opponent_deck: list[int], seed_base: int, fallback, particles: int = 2, known_hand_ids=()):
    """Oracle-deck upper-bound adversarial search.

    `opponent_deck` is allowed here only for controlled experiments.  Live search
    must call a belief-set wrapper and aggregate one action across plausible decks.
    """
    started = time.perf_counter()
    parts = [
        solve_particle(raw, own_deck, opponent_deck, seed_base + i * 7919, fallback, known_hand_ids)
        for i in range(particles)
    ]
    fb = tuple(fallback)
    common = set(parts[0]["values"]) if parts else set()
    for part in parts[1:]:
        common &= set(part["values"])

    def robust_key(action):
        vals = [part["values"][action] for part in parts]
        worst = min(vals)
        mean_scalar = sum(float(v[-1]) for v in vals) / len(vals)
        return (worst, mean_scalar, action == fb)

    best = max(common, key=robust_key) if common else fb
    # Search never earns authority unless the fallback passed the exact same
    # complete-turn and complete-response qualification.
    if fb not in common:
        best = fb
    elif best not in common or robust_key(best) <= robust_key(fb):
        best = fb

    return {
        "fallback": list(fb),
        "suggested": list(best),
        "disagrees": best != fb,
        "fallback_key": None if fb not in common else robust_key(fb),
        "suggested_key": None if best not in common else robust_key(best),
        "particles": parts,
        "seconds": time.perf_counter() - started,
        "own_expansions": sum(p["own_expansions"] for p in parts),
        "response_expansions": sum(p["response_expansions"] for p in parts),
        "incomplete": sum(p["incomplete"] for p in parts),
    }


def compare_pair_particle(
    raw,
    own_deck: list[int],
    opponent_deck: list[int],
    seed: int,
    fallback,
    candidate,
    known_hand_ids=(),
):
    """Evaluate only fallback and one challenger through the next opponent turn."""
    obs = s.to_observation_class(raw)
    root_player = int(obs.current.yourIndex)
    root_turn = int(obs.current.turn)
    start_prizes = (len(obs.current.players[0].prize), len(obs.current.players[1].prize))
    det = _determinize_with_known_hand(obs, own_deck, opponent_deck, seed, known_hand_ids)
    root = s._canary.begin(obs, det)
    fb = tuple(fallback)
    cand = tuple(candidate)
    roots = [fb] if cand == fb else [fb, cand]
    values = {}
    paths = {}
    own_expansions = 0
    response_expansions = 0
    incomplete = 0
    started = time.perf_counter()
    try:
        for root_action in roots:
            lines, used = complete_own_lines(root, root_action, root_player, root_turn, start_prizes)
            own_expansions += used
            robust = []
            for line in lines:
                vector, used_response, complete = adversarial_response(line.state, root_player, start_prizes)
                response_expansions += used_response
                if complete and vector is not None:
                    robust.append((vector, list(line.path)))
                else:
                    incomplete += 1
                _release(line.state)
            if robust:
                vector, path = max(robust, key=lambda item: item[0])
                values[root_action] = vector
                paths[root_action] = path
    finally:
        s.search_end()
    return {
        "fallback": fb,
        "candidate": cand,
        "values": values,
        "paths": paths,
        "qualified": fb in values and cand in values,
        "own_expansions": own_expansions,
        "response_expansions": response_expansions,
        "incomplete": incomplete,
        "seconds": time.perf_counter() - started,
    }


def verify_pair(
    raw,
    own_deck: list[int],
    opponent_deck: list[int],
    seed_base: int,
    fallback,
    candidate,
    *,
    particles: int = 2,
    known_hand_ids=(),
):
    """Robustly compare one challenger with fallback across hidden particles."""
    fb = tuple(fallback)
    cand = tuple(candidate)
    started = time.perf_counter()
    rows = [
        compare_pair_particle(
            raw,
            own_deck,
            opponent_deck,
            seed_base + 7919 * i,
            fb,
            cand,
            known_hand_ids,
        )
        for i in range(particles)
    ]
    qualified = all(row["qualified"] for row in rows)
    if not qualified:
        return {
            "fallback": list(fb),
            "candidate": list(cand),
            "qualified": False,
            "nondown": False,
            "exact_gain": False,
            "worst_scalar_delta": None,
            "mean_scalar_delta": None,
            "particles": rows,
            "seconds": time.perf_counter() - started,
        }
    pairs = [(row["values"][cand], row["values"][fb]) for row in rows]
    nondown = all(tuple(cv[:3]) >= tuple(fv[:3]) for cv, fv in pairs)
    exact_gain = nondown and any(tuple(cv[:3]) > tuple(fv[:3]) for cv, fv in pairs)
    terminal_gain = nondown and any(int(cv[0]) > int(fv[0]) for cv, fv in pairs)
    prize_gain = (
        exact_gain
        and not terminal_gain
        and any(tuple(cv[1:3]) > tuple(fv[1:3]) for cv, fv in pairs)
    )
    deltas = [float(cv[3] - fv[3]) for cv, fv in pairs]
    return {
        "fallback": list(fb),
        "candidate": list(cand),
        "qualified": True,
        "nondown": nondown,
        "exact_gain": exact_gain,
        "terminal_gain": terminal_gain,
        "prize_gain": prize_gain,
        "worst_scalar_delta": min(deltas),
        "mean_scalar_delta": sum(deltas) / len(deltas),
        "particles": rows,
        "seconds": time.perf_counter() - started,
        "own_expansions": sum(row["own_expansions"] for row in rows),
        "response_expansions": sum(row["response_expansions"] for row in rows),
        "incomplete": sum(row["incomplete"] for row in rows),
    }


# Deeper pair verification.  This is intentionally separate from the ordinary
# one-opponent-turn verifier because it is substantially more expensive and
# should run only after fast search has produced one credible challenger.
REPLY_ROOT_CAP = 10
REPLY_LEAF_CAP = 6
REPLY_ROOT_LINES = 2


def _best_next_own_turn_value(start_state, root_player: int, start_prizes: tuple[int, int]):
    """Maximize over the root player's complete next turn from one response leaf."""
    obs = start_state.observation
    cur = obs.current
    if cur is None or int(cur.result) != -1 or obs.select is None:
        return outcome_vector(obs, root_player, start_prizes), 0, True
    if int(cur.yourIndex) != root_player:
        return None, 0, False
    root_turn = int(cur.turn)
    root_actions = _ordered(obs, REPLY_ROOT_CAP, maximize=True)
    best = None
    expansions = 0
    qualified = False
    for root_action in root_actions:
        try:
            lines, used = complete_own_lines(
                start_state, root_action, root_player, root_turn, start_prizes
            )
        except Exception:
            continue
        expansions += used
        if not lines:
            continue
        qualified = True
        for line in lines[:REPLY_ROOT_LINES]:
            value = outcome_vector(line.state.observation, root_player, start_prizes)
            if best is None or value > best:
                best = value
            _release(line.state)
        if best is not None and int(best[0]) == 6:
            break
    return best, expansions, qualified and best is not None


def adversarial_response_with_reply(start_state, root_player: int, start_prizes: tuple[int, int]):
    """Minimize opponent turn after allowing our best complete following turn.

    The opponent search first retains a bounded set of the most dangerous complete
    response leaves.  Each retained leaf is then evaluated after the root player
    gets a full native reply turn.  This is a selective max-min-max horizon and is
    used only as a final pair verifier, never as the fast proposal generator.
    """
    obs = start_state.observation
    cur = obs.current
    if cur is None or int(cur.result) != -1 or obs.select is None:
        return outcome_vector(obs, root_player, start_prizes), 0, 0, True
    if int(cur.yourIndex) == root_player:
        reply, reply_exp, ok = _best_next_own_turn_value(start_state, root_player, start_prizes)
        return reply, 0, reply_exp, ok

    opponent_turn = int(cur.turn)
    front = [Node(start_state, [], outcome_vector(obs, root_player, start_prizes))]
    completed: list[Node] = []
    opponent_expansions = 0

    for _depth in range(OPP_DEPTH):
        nxt: list[Node] = []
        for node in front:
            node_obs = node.state.observation
            if _opponent_boundary(node_obs, root_player, opponent_turn):
                completed.append(node)
                continue
            if opponent_expansions >= OPP_EXPANSION_CAP:
                _release(node.state)
                continue
            cap = OPP_MAIN_CAP if int(node_obs.select.context) == 0 else OPP_EFFECT_CAP
            for action in _ordered(node_obs, cap, maximize=True):
                if opponent_expansions >= OPP_EXPANSION_CAP:
                    break
                try:
                    child = s.search_step(node.state.searchId, list(action))
                except Exception:
                    continue
                opponent_expansions += 1
                child_node = Node(
                    child,
                    node.path + [tuple(action)],
                    outcome_vector(child.observation, root_player, start_prizes),
                )
                if _opponent_boundary(child.observation, root_player, opponent_turn):
                    completed.append(child_node)
                else:
                    nxt.append(child_node)
            _release(node.state)
        if not nxt:
            front = []
            break
        nxt.sort(key=lambda n: n.vector)
        front = nxt[:OPP_WIDTH]
        for node in nxt[OPP_WIDTH:]:
            _release(node.state)
        if any(int(node.vector[0]) == -6 for node in completed):
            break

    for node in front:
        if _opponent_boundary(node.state.observation, root_player, opponent_turn):
            completed.append(node)
        else:
            _release(node.state)

    if not completed:
        return None, opponent_expansions, 0, False

    # Terminal losses need no reply and are necessarily worst. Otherwise retain
    # only the most dangerous response leaves before the expensive reply search.
    terminal_losses = [node for node in completed if int(node.vector[0]) == -6]
    if terminal_losses:
        value = min(node.vector for node in terminal_losses)
        for node in completed:
            if node.state.searchId != start_state.searchId:
                _release(node.state)
        return value, opponent_expansions, 0, True

    completed.sort(key=lambda n: n.vector)
    retained = completed[:REPLY_LEAF_CAP]
    for node in completed[REPLY_LEAF_CAP:]:
        if node.state.searchId != start_state.searchId:
            _release(node.state)

    evaluated = []
    reply_expansions = 0
    for node in retained:
        value, used, ok = _best_next_own_turn_value(node.state, root_player, start_prizes)
        reply_expansions += used
        if ok and value is not None:
            evaluated.append(value)
        if node.state.searchId != start_state.searchId:
            _release(node.state)
    if not evaluated:
        return None, opponent_expansions, reply_expansions, False
    return min(evaluated), opponent_expansions, reply_expansions, True


def compare_pair_particle_deep(
    raw,
    own_deck: list[int],
    opponent_deck: list[int],
    seed: int,
    fallback,
    candidate,
    known_hand_ids=(),
):
    """Compare fallback/challenger through own turn, opponent turn, own reply."""
    obs = s.to_observation_class(raw)
    root_player = int(obs.current.yourIndex)
    root_turn = int(obs.current.turn)
    start_prizes = (len(obs.current.players[0].prize), len(obs.current.players[1].prize))
    det = _determinize_with_known_hand(obs, own_deck, opponent_deck, seed, known_hand_ids)
    root = s._canary.begin(obs, det)
    fb = tuple(fallback)
    cand = tuple(candidate)
    roots = [fb] if cand == fb else [fb, cand]
    values = {}
    own_expansions = 0
    response_expansions = 0
    reply_expansions = 0
    incomplete = 0
    started = time.perf_counter()
    try:
        for root_action in roots:
            lines, used = complete_own_lines(root, root_action, root_player, root_turn, start_prizes)
            own_expansions += used
            robust = []
            for line in lines:
                value, opp_used, reply_used, ok = adversarial_response_with_reply(
                    line.state, root_player, start_prizes
                )
                response_expansions += opp_used
                reply_expansions += reply_used
                if ok and value is not None:
                    robust.append(value)
                else:
                    incomplete += 1
                _release(line.state)
            if robust:
                # We control the remainder of the root turn, so keep its best line;
                # each line value already includes the opponent minimum and our reply max.
                values[root_action] = max(robust)
    finally:
        s.search_end()
    return {
        "fallback": fb,
        "candidate": cand,
        "values": values,
        "qualified": fb in values and cand in values,
        "own_expansions": own_expansions,
        "response_expansions": response_expansions,
        "reply_expansions": reply_expansions,
        "incomplete": incomplete,
        "seconds": time.perf_counter() - started,
    }


def verify_pair_deep(
    raw,
    own_deck: list[int],
    opponent_deck: list[int],
    seed_base: int,
    fallback,
    candidate,
    *,
    particles: int = 2,
    known_hand_ids=(),
):
    """Final selective max-min-max verifier across hidden particles."""
    fb = tuple(fallback)
    cand = tuple(candidate)
    started = time.perf_counter()
    rows = [
        compare_pair_particle_deep(
            raw,
            own_deck,
            opponent_deck,
            seed_base + 7919 * i,
            fb,
            cand,
            known_hand_ids,
        )
        for i in range(particles)
    ]
    qualified = all(row["qualified"] for row in rows)
    if not qualified:
        return {
            "fallback": list(fb), "candidate": list(cand), "qualified": False,
            "nondown": False, "exact_gain": False, "terminal_gain": False,
            "prize_gain": False, "worst_scalar_delta": None,
            "mean_scalar_delta": None, "particles": rows,
            "seconds": time.perf_counter() - started,
        }
    pairs = [(row["values"][cand], row["values"][fb]) for row in rows]
    nondown = all(tuple(cv[:3]) >= tuple(fv[:3]) for cv, fv in pairs)
    exact_gain = nondown and any(tuple(cv[:3]) > tuple(fv[:3]) for cv, fv in pairs)
    terminal_gain = nondown and any(int(cv[0]) > int(fv[0]) for cv, fv in pairs)
    prize_gain = exact_gain and not terminal_gain and any(
        tuple(cv[1:3]) > tuple(fv[1:3]) for cv, fv in pairs
    )
    deltas = [float(cv[3] - fv[3]) for cv, fv in pairs]
    return {
        "fallback": list(fb), "candidate": list(cand), "qualified": True,
        "nondown": nondown, "exact_gain": exact_gain,
        "terminal_gain": terminal_gain, "prize_gain": prize_gain,
        "worst_scalar_delta": min(deltas),
        "mean_scalar_delta": sum(deltas) / len(deltas),
        "particles": rows, "seconds": time.perf_counter() - started,
        "own_expansions": sum(row["own_expansions"] for row in rows),
        "response_expansions": sum(row["response_expansions"] for row in rows),
        "reply_expansions": sum(row["reply_expansions"] for row in rows),
        "incomplete": sum(row["incomplete"] for row in rows),
    }


# Practical two-turn verifier. Unlike verify_pair_deep(), this uses a bounded
# native reply probe rather than a full second-turn enumeration.
FAST_REPLY_DEPTH = 6
FAST_REPLY_WIDTH = 4
FAST_REPLY_EXPANSION_CAP = 180
FAST_REPLY_MAIN_CAP = 8
FAST_REPLY_EFFECT_CAP = 12
FAST_REPLY_LEAF_CAP = 4
FAST_REPLY_OWN_LINES = 2


def _fast_reply_value(start_state, root_player: int, start_prizes: tuple[int, int]):
    """Bounded native probe of our best next complete turn from one opponent leaf."""
    obs = start_state.observation
    cur = obs.current
    if cur is None or int(cur.result) != -1 or obs.select is None:
        return outcome_vector(obs, root_player, start_prizes), 0, True
    if int(cur.yourIndex) != root_player:
        return None, 0, False
    root_turn = int(cur.turn)
    front = [Node(start_state, [], outcome_vector(obs, root_player, start_prizes))]
    completed: list[Node] = []
    expansions = 0

    for _depth in range(FAST_REPLY_DEPTH):
        nxt: list[Node] = []
        for node in front:
            node_obs = node.state.observation
            if _own_boundary(node_obs, root_player, root_turn):
                completed.append(node)
                continue
            if expansions >= FAST_REPLY_EXPANSION_CAP:
                if node.state.searchId != start_state.searchId:
                    _release(node.state)
                continue
            cap = FAST_REPLY_MAIN_CAP if int(node_obs.select.context) == 0 else FAST_REPLY_EFFECT_CAP
            for action in _ordered(node_obs, cap, maximize=True):
                if expansions >= FAST_REPLY_EXPANSION_CAP:
                    break
                try:
                    child = s.search_step(node.state.searchId, list(action))
                except Exception:
                    continue
                expansions += 1
                child_node = Node(
                    child,
                    node.path + [tuple(action)],
                    outcome_vector(child.observation, root_player, start_prizes),
                )
                if _own_boundary(child.observation, root_player, root_turn):
                    completed.append(child_node)
                else:
                    nxt.append(child_node)
            if node.state.searchId != start_state.searchId:
                _release(node.state)
        if not nxt:
            front = []
            break
        nxt.sort(key=lambda node: node.vector, reverse=True)
        front = nxt[:FAST_REPLY_WIDTH]
        for node in nxt[FAST_REPLY_WIDTH:]:
            _release(node.state)
        if any(int(node.vector[0]) == 6 for node in completed):
            break

    for node in front:
        if _own_boundary(node.state.observation, root_player, root_turn):
            completed.append(node)
        elif node.state.searchId != start_state.searchId:
            _release(node.state)

    if not completed:
        return None, expansions, False
    best_node = max(completed, key=lambda node: node.vector)
    value = best_node.vector
    for node in completed:
        if node.state.searchId != start_state.searchId:
            _release(node.state)
    return value, expansions, True


def adversarial_response_with_fast_reply(start_state, root_player: int, start_prizes: tuple[int, int]):
    """Opponent minimum after a bounded best-reply probe for the root player."""
    obs = start_state.observation
    cur = obs.current
    if cur is None or int(cur.result) != -1 or obs.select is None:
        return outcome_vector(obs, root_player, start_prizes), 0, 0, True
    if int(cur.yourIndex) == root_player:
        value, used, ok = _fast_reply_value(start_state, root_player, start_prizes)
        return value, 0, used, ok

    opponent_turn = int(cur.turn)
    front = [Node(start_state, [], outcome_vector(obs, root_player, start_prizes))]
    completed: list[Node] = []
    opponent_expansions = 0

    for _depth in range(OPP_DEPTH):
        nxt: list[Node] = []
        for node in front:
            node_obs = node.state.observation
            if _opponent_boundary(node_obs, root_player, opponent_turn):
                completed.append(node)
                continue
            if opponent_expansions >= OPP_EXPANSION_CAP:
                if node.state.searchId != start_state.searchId:
                    _release(node.state)
                continue
            cap = OPP_MAIN_CAP if int(node_obs.select.context) == 0 else OPP_EFFECT_CAP
            for action in _ordered(node_obs, cap, maximize=True):
                if opponent_expansions >= OPP_EXPANSION_CAP:
                    break
                try:
                    child = s.search_step(node.state.searchId, list(action))
                except Exception:
                    continue
                opponent_expansions += 1
                child_node = Node(
                    child,
                    node.path + [tuple(action)],
                    outcome_vector(child.observation, root_player, start_prizes),
                )
                if _opponent_boundary(child.observation, root_player, opponent_turn):
                    completed.append(child_node)
                else:
                    nxt.append(child_node)
            if node.state.searchId != start_state.searchId:
                _release(node.state)
        if not nxt:
            front = []
            break
        nxt.sort(key=lambda node: node.vector)
        front = nxt[:OPP_WIDTH]
        for node in nxt[OPP_WIDTH:]:
            _release(node.state)
        if any(int(node.vector[0]) == -6 for node in completed):
            break

    for node in front:
        if _opponent_boundary(node.state.observation, root_player, opponent_turn):
            completed.append(node)
        elif node.state.searchId != start_state.searchId:
            _release(node.state)

    if not completed:
        return None, opponent_expansions, 0, False
    terminal_losses = [node for node in completed if int(node.vector[0]) == -6]
    if terminal_losses:
        value = min(node.vector for node in terminal_losses)
        for node in completed:
            if node.state.searchId != start_state.searchId:
                _release(node.state)
        return value, opponent_expansions, 0, True

    completed.sort(key=lambda node: node.vector)
    retained = completed[:FAST_REPLY_LEAF_CAP]
    for node in completed[FAST_REPLY_LEAF_CAP:]:
        if node.state.searchId != start_state.searchId:
            _release(node.state)

    reply_values = []
    reply_expansions = 0
    for node in retained:
        value, used, ok = _fast_reply_value(node.state, root_player, start_prizes)
        reply_expansions += used
        if ok and value is not None:
            reply_values.append(value)
        if node.state.searchId != start_state.searchId:
            _release(node.state)
    if not reply_values:
        return None, opponent_expansions, reply_expansions, False
    return min(reply_values), opponent_expansions, reply_expansions, True


def compare_pair_particle_two_turn(
    raw,
    own_deck: list[int],
    opponent_deck: list[int],
    seed: int,
    fallback,
    candidate,
    known_hand_ids=(),
):
    """Practical fallback/challenger max-min-max comparison in one hidden world."""
    obs = s.to_observation_class(raw)
    root_player = int(obs.current.yourIndex)
    root_turn = int(obs.current.turn)
    start_prizes = (len(obs.current.players[0].prize), len(obs.current.players[1].prize))
    det = _determinize_with_known_hand(obs, own_deck, opponent_deck, seed, known_hand_ids)
    root = s._canary.begin(obs, det)
    fb = tuple(fallback)
    cand = tuple(candidate)
    roots = [fb] if cand == fb else [fb, cand]
    values = {}
    own_expansions = response_expansions = reply_expansions = incomplete = 0
    started = time.perf_counter()
    try:
        for root_action in roots:
            lines, used = complete_own_lines(root, root_action, root_player, root_turn, start_prizes)
            own_expansions += used
            robust = []
            for line in lines[:FAST_REPLY_OWN_LINES]:
                value, opp_used, reply_used, ok = adversarial_response_with_fast_reply(
                    line.state, root_player, start_prizes
                )
                response_expansions += opp_used
                reply_expansions += reply_used
                if ok and value is not None:
                    robust.append(value)
                else:
                    incomplete += 1
                _release(line.state)
            for line in lines[FAST_REPLY_OWN_LINES:]:
                _release(line.state)
            if robust:
                values[root_action] = max(robust)
    finally:
        s.search_end()
    return {
        "fallback": fb, "candidate": cand, "values": values,
        "qualified": fb in values and cand in values,
        "own_expansions": own_expansions,
        "response_expansions": response_expansions,
        "reply_expansions": reply_expansions,
        "incomplete": incomplete,
        "seconds": time.perf_counter() - started,
    }


def verify_pair_two_turn(
    raw,
    own_deck: list[int],
    opponent_deck: list[int],
    seed_base: int,
    fallback,
    candidate,
    *,
    particles: int = 2,
    known_hand_ids=(),
):
    """Budgeted two-turn pair verifier across independent hidden particles."""
    fb = tuple(fallback); cand = tuple(candidate); started = time.perf_counter()
    rows = [
        compare_pair_particle_two_turn(
            raw, own_deck, opponent_deck, seed_base + 7919 * i,
            fb, cand, known_hand_ids,
        )
        for i in range(particles)
    ]
    qualified = all(row["qualified"] for row in rows)
    if not qualified:
        return {
            "fallback": list(fb), "candidate": list(cand), "qualified": False,
            "nondown": False, "exact_gain": False, "terminal_gain": False,
            "prize_gain": False, "worst_scalar_delta": None,
            "mean_scalar_delta": None, "particles": rows,
            "seconds": time.perf_counter() - started,
        }
    pairs = [(row["values"][cand], row["values"][fb]) for row in rows]
    nondown = all(tuple(cv[:3]) >= tuple(fv[:3]) for cv, fv in pairs)
    exact_gain = nondown and any(tuple(cv[:3]) > tuple(fv[:3]) for cv, fv in pairs)
    terminal_gain = nondown and any(int(cv[0]) > int(fv[0]) for cv, fv in pairs)
    prize_gain = exact_gain and not terminal_gain and any(
        tuple(cv[1:3]) > tuple(fv[1:3]) for cv, fv in pairs
    )
    deltas = [float(cv[3] - fv[3]) for cv, fv in pairs]
    return {
        "fallback": list(fb), "candidate": list(cand), "qualified": True,
        "nondown": nondown, "exact_gain": exact_gain,
        "terminal_gain": terminal_gain, "prize_gain": prize_gain,
        "worst_scalar_delta": min(deltas),
        "mean_scalar_delta": sum(deltas) / len(deltas),
        "particles": rows, "seconds": time.perf_counter() - started,
        "own_expansions": sum(row["own_expansions"] for row in rows),
        "response_expansions": sum(row["response_expansions"] for row in rows),
        "reply_expansions": sum(row["reply_expansions"] for row in rows),
        "incomplete": sum(row["incomplete"] for row in rows),
    }
