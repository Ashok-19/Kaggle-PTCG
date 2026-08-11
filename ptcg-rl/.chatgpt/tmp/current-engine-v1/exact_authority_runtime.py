from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from ptcg_rl.decision_engine import PublicGameMemory


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


PLANNER = _load(
    "exact_authority_symbolic_planner",
    ROOT / ".chatgpt/tmp/current-engine-v1/symbolic_turn_planner.py",
)
EXECUTOR = _load(
    "exact_authority_semantic_executor",
    ROOT / ".chatgpt/tmp/current-engine-v1/semantic_plan_executor.py",
)


@dataclass
class AuthorityDiagnostics:
    calls: int = 0
    searches: int = 0
    disagreements: int = 0
    exact_candidates: int = 0
    proof_prefix_candidates: int = 0
    proof_verifications: int = 0
    proof_rejections: int = 0
    tactical_authorizations: int = 0
    adrena_ko_authorizations: int = 0
    shadow_split_authorizations: int = 0
    authorizations: int = 0
    terminal_authorizations: int = 0
    prize_authorizations: int = 0
    planned_steps: int = 0
    plan_failures: int = 0
    fallback_unqualified: int = 0
    search_failures: int = 0
    search_seconds: float = 0.0
    verification_seconds: float = 0.0
    last_reason: str = ""


class ExactAuthorityRuntime:
    """Dawn fallback plus conservative native-search authority.

    Search may execute a challenger only when all of the following are true:
      * Dawn and challenger reach genuine current-turn boundaries in every particle;
      * challenger is no worse in (terminal result, prizes taken) in every particle;
      * challenger is strictly better on one of those exact components somewhere;
      * every particle shares one functional path through the step where that
        exact terminal/prize gain is already realized in the native state.

    Only that proof-producing prefix is executed. Everything else returns the
    already-probed Dawn action. This runtime therefore
    does not use scalar/race/model scores as live authority.
    """

    def __init__(
        self,
        fallback_module,
        deck: list[int] | tuple[int, ...],
        *,
        particles: int = 2,
        min_turn: int = 2,
        max_searches_per_turn: int = 2,
        max_root_options: int = 16,
        verification_worlds: int = 4,
        verification_pool: int = 24,
        exact_shortlist: int = 3,
    ) -> None:
        self.fallback = fallback_module
        self.deck = [int(x) for x in deck]
        self.particles = max(2, int(particles))
        self.min_turn = int(min_turn)
        self.max_searches_per_turn = max(1, int(max_searches_per_turn))
        self.max_root_options = max(2, int(max_root_options))
        self.verification_worlds = max(2, int(verification_worlds))
        self.verification_pool = max(self.verification_worlds, int(verification_pool))
        self.exact_shortlist = max(1, int(exact_shortlist))
        self.memory = PublicGameMemory()
        self.diagnostics = AuthorityDiagnostics()
        self._turn_searches: dict[int, int] = {}
        self._plan: dict[str, Any] | None = None
        self._plan_step = 0
        self._plan_turn = -1
        self._plan_player = -1
        self._adrena_counters: dict[int, int] = {}

    def reset(self) -> None:
        self.memory.reset()
        self._turn_searches.clear()
        self._plan = None
        self._plan_step = 0
        self._plan_turn = -1
        self._plan_player = -1
        self._adrena_counters.clear()
        self.diagnostics.last_reason = "reset"

    @staticmethod
    def _current(raw: dict) -> dict:
        current = raw.get("current")
        return current if isinstance(current, dict) else {}

    @staticmethod
    def _select(raw: dict) -> dict:
        select = raw.get("select")
        return select if isinstance(select, dict) else {}

    def _seed(self, raw: dict) -> int:
        current = self._current(raw)
        select = self._select(raw)
        players = current.get("players") or []
        public = {
            "turn": current.get("turn"),
            "turnActionCount": current.get("turnActionCount"),
            "yourIndex": current.get("yourIndex"),
            "stadium": current.get("stadium"),
            "players": [
                {
                    "active": p.get("active") if isinstance(p, dict) else None,
                    "bench": p.get("bench") if isinstance(p, dict) else None,
                    "discard": p.get("discard") if isinstance(p, dict) else None,
                    "handCount": p.get("handCount") if isinstance(p, dict) else None,
                    "deckCount": p.get("deckCount") if isinstance(p, dict) else None,
                    "prize": p.get("prize") if isinstance(p, dict) else None,
                }
                for p in players
            ],
            "context": select.get("context"),
            "options": select.get("option"),
        }
        digest = hashlib.sha256(
            json.dumps(public, sort_keys=True, default=str, separators=(",", ":")).encode()
        ).digest()
        return int.from_bytes(digest[:8], "big") & 0x7FFFFFFF

    def _plausible_exact_turn_route(self, raw: dict) -> bool:
        """Public prerequisite for a current-turn terminal/prize improvement.

        Live search authority is exact current-turn outcome only. Skip expensive
        search when no public legal route can possibly damage the opponent this
        turn. Later MAIN observations are reconsidered after Dawn performs setup.
        """
        select = self._select(raw)
        options = select.get("option") or []
        try:
            semantics = [PLANNER.pf.semantic(raw, option) for option in options if isinstance(option, dict)]
        except Exception:
            return True  # fail open rather than lose exact-search recall
        for item in semantics:
            kind = int(item.get("type", -1))
            source_id = int(item.get("source_id", 0) or 0)
            if kind == 13:  # an attack is already legal
                return True
            if kind == 9 and source_id == 648:  # direct Grimmsnarl evolution -> Punk Up
                return True
            if kind == 7 and source_id == 1079:  # Rare Candy can create Grimmsnarl this turn
                return True
            if kind == 10 and source_id == 112:  # Adrena-Brain can create a prize immediately
                return True
        # A ready benched Grimmsnarl can become an attacker through a legal retreat.
        if any(int(item.get("type", -1)) == 12 for item in semantics):
            current = self._current(raw)
            your_index = current.get("yourIndex")
            players = current.get("players") or []
            if isinstance(your_index, int) and 0 <= your_index < len(players) and isinstance(players[your_index], dict):
                for pokemon in players[your_index].get("bench") or []:
                    if not isinstance(pokemon, dict) or int(pokemon.get("id", 0) or 0) != 648:
                        continue
                    if len(pokemon.get("energyCards") or []) >= 2:
                        return True
        return False

    def _eligible(self, raw: dict, fallback_action=None) -> bool:
        current = self._current(raw)
        select = self._select(raw)
        if not current or not select:
            return False
        if int(current.get("result", -1)) != -1:
            return False
        if int(select.get("type", -1)) != 0:
            return False
        if int(select.get("context", -1)) != 0:
            return False
        turn = int(current.get("turn", -1))
        if turn < self.min_turn:
            return False
        if not self._plausible_exact_turn_route(raw):
            return False
        # Raw CABT menus can contain many interchangeable physical copies. Search
        # complexity is determined by distinct functional actions, not raw option
        # count. Ask for one action beyond the live limit so >limit remains
        # detectable without fully enumerating large duplicate menus.
        try:
            obs = PLANNER.to_observation_class(raw)
            functional_actions = PLANNER.legal_actions(
                obs,
                self.max_root_options + 1,
                fallback=fallback_action,
            )
        except Exception:
            return False
        if not (2 <= len(functional_actions) <= self.max_root_options):
            return False
        used = self._turn_searches.get(turn, 0)
        return used < self.max_searches_per_turn

    @staticmethod
    def _exact_dominance(result: dict) -> dict[str, Any]:
        fb = tuple(result.get("fallback") or [])
        cand = tuple(result.get("suggested") or [])
        if cand == fb:
            return {"qualified": True, "gain": False, "terminal": False, "prize": False}
        parts = result.get("particles") or []
        pairs = []
        proof_lengths = []
        candidate_paths = []
        for part in parts:
            rows = {tuple(row["root_action"]): row for row in part.get("rows") or []}
            fr = rows.get(fb)
            cr = rows.get(cand)
            if not fr or not cr or not fr.get("complete") or not cr.get("complete"):
                return {"qualified": False, "gain": False, "terminal": False, "prize": False}
            fv = tuple(fr.get("boundary") or ())
            cv = tuple(cr.get("boundary") or ())
            if len(fv) < 2 or len(cv) < 2:
                return {"qualified": False, "gain": False, "terminal": False, "prize": False}
            exact_path = [tuple(int(x) for x in step[:2]) for step in (cr.get("exact_path") or [])]
            semantic_path = list(cr.get("semantic_path") or [])
            if not exact_path or len(exact_path) != len(semantic_path):
                return {"qualified": False, "gain": False, "terminal": False, "prize": False}
            pairs.append((cv[:2], fv[:2]))
            candidate_paths.append(semantic_path)
            proof_lengths.append(next(
                (index + 1 for index, exact_step in enumerate(exact_path) if exact_step > fv[:2]),
                0,
            ))
        if not pairs:
            return {"qualified": False, "gain": False, "terminal": False, "prize": False}
        nondown = all(cv >= fv for cv, fv in pairs)
        gain = nondown and any(cv > fv for cv, fv in pairs)
        terminal = gain and any(cv[0] > fv[0] for cv, fv in pairs)
        prize = gain and not terminal and any(cv[1] > fv[1] for cv, fv in pairs)
        if gain and any(length <= 0 for length in proof_lengths):
            return {"qualified": False, "gain": False, "terminal": False, "prize": False}
        return {
            "qualified": True,
            "nondown": nondown,
            "gain": gain,
            "terminal": terminal,
            "prize": prize,
            "pairs": pairs,
            "proof_lengths": proof_lengths,
            "candidate_paths": candidate_paths,
        }

    def _exact_root_shortlist(self, raw: dict, result: dict) -> list[list[int]]:
        """Proposal roots with current-turn exact nondown/gain in every proposal particle."""
        parts = result.get("particles") or []
        if not parts:
            return []
        maps = [{tuple(row.get("root_action") or ()): row for row in part.get("rows") or []} for part in parts]
        fb = tuple(result.get("fallback") or [])
        common = set(maps[0])
        for mapping in maps[1:]:
            common &= set(mapping)
        if fb not in common or not all(bool(mapping[fb].get("complete")) for mapping in maps):
            return []
        fallback_exact = [tuple(mapping[fb].get("boundary") or ())[:2] for mapping in maps]
        rows = []
        fb_functional = PLANNER.functional_signature(raw, fb)
        for action in common:
            if action == fb or PLANNER.functional_signature(raw, action) == fb_functional:
                continue
            candidate_rows = [mapping[action] for mapping in maps]
            if not all(bool(row.get("complete")) for row in candidate_rows):
                continue
            candidate_exact = [tuple(row.get("boundary") or ())[:2] for row in candidate_rows]
            if not all(len(value) == 2 for value in candidate_exact):
                continue
            nondown = all(cv >= fv for cv, fv in zip(candidate_exact, fallback_exact))
            gain = nondown and any(cv > fv for cv, fv in zip(candidate_exact, fallback_exact))
            if not gain:
                continue
            worst = min(candidate_exact)
            mean_prizes = sum(value[1] for value in candidate_exact) / len(candidate_exact)
            gain_count = sum(cv > fv for cv, fv in zip(candidate_exact, fallback_exact))
            rows.append((worst, gain_count, mean_prizes, action == tuple(result.get("suggested") or ()), action))
        rows.sort(reverse=True)
        return [list(row[-1]) for row in rows[: self.exact_shortlist]]

    @staticmethod
    def _proof_plan(exact: dict[str, Any]) -> dict[str, Any] | None:
        paths = list(exact.get("candidate_paths") or [])
        lengths = [int(x) for x in (exact.get("proof_lengths") or [])]
        if not paths or len(paths) != len(lengths) or any(length <= 0 for length in lengths):
            return None
        required = max(lengths)
        if any(len(path) < required for path in paths):
            return None
        prefix = []
        for index in range(required):
            step = paths[0][index]
            if not all(path[index] == step for path in paths[1:]):
                return None
            prefix.append(step)
        return {
            "semantic_path": [[list(sig) for sig in step] for step in prefix],
            "steps": required,
            "proof_lengths": lengths,
            "consensus_particles": len(paths),
        }

    def _continue_plan(self, raw: dict) -> list[int] | None:
        if self._plan is None:
            return None
        current = self._current(raw)
        turn = int(current.get("turn", -1))
        player = int(current.get("yourIndex", -1))
        if turn != self._plan_turn or player != self._plan_player:
            self._plan = None
            self.diagnostics.last_reason = "plan-turn-diverged"
            return None
        semantic_path = self._plan.get("semantic_path") or []
        if self._plan_step >= len(semantic_path):
            self._plan = None
            self.diagnostics.last_reason = "plan-complete"
            return None
        action, check = EXECUTOR.next_planned_action(
            raw, self.fallback, self._plan, self._plan_step
        )
        if action is None or not check.get("ok"):
            self._plan = None
            self.diagnostics.plan_failures += 1
            self.diagnostics.last_reason = str(check.get("reason") or "plan-failed")
            return None
        self._plan_step += 1
        self.diagnostics.planned_steps += 1
        self.diagnostics.last_reason = "planned-step"
        if self._plan_step >= len(semantic_path):
            # Keep no stale commitment after returning the final prefix step.
            self._plan = None
        return list(action)

    @staticmethod
    def _option_public_pokemon(raw: dict, option: dict):
        current = raw.get("current") or {}
        players = current.get("players") or []
        your_index = current.get("yourIndex")
        if not isinstance(your_index, int):
            return None
        opponent_index = 1 - your_index
        if not (0 <= opponent_index < len(players)) or not isinstance(players[opponent_index], dict):
            return None
        opponent = players[opponent_index]
        area = int(option.get("area", 0) or 0)
        index = option.get("index")
        if area == 4:
            active = opponent.get("active") or []
            return active[0] if active and isinstance(active[0], dict) else None
        if area == 5 and isinstance(index, int):
            bench = opponent.get("bench") or []
            return bench[index] if 0 <= index < len(bench) and isinstance(bench[index], dict) else None
        return None

    @staticmethod
    def _has_rule_box(card_id: int) -> bool:
        data = PLANNER.CARD.get(int(card_id))
        return bool(data is not None and (bool(getattr(data, "ex", False)) or bool(getattr(data, "megaEx", False))))

    def _exact_shadow_split_finish(self, raw: dict, fallback_action: list[int], probe_state: dict):
        """Redirect Shadow Bullet's 30 bench damage only for an exact final-prize split."""
        select = self._select(raw)
        context = int(select.get("context", -1) if select.get("context") is not None else -1)
        effect = select.get("effect") if isinstance(select.get("effect"), dict) else {}
        if context != 15 or int(effect.get("id", 0) or 0) != 648:
            return None
        current = self._current(raw)
        your_index = current.get("yourIndex")
        players = current.get("players") or []
        if not isinstance(your_index, int) or not (0 <= your_index < len(players)):
            return None
        opponent_index = 1 - your_index
        if not (0 <= opponent_index < len(players)):
            return None
        me = players[your_index] if isinstance(players[your_index], dict) else {}
        opponent = players[opponent_index] if isinstance(players[opponent_index], dict) else {}
        active = opponent.get("active") or []
        active = active[0] if active and isinstance(active[0], dict) else None
        # CABT exposes the already-hit Active at hp==0 during Shadow Bullet's
        # bench-target selection. Its prizes have not yet been taken at this point.
        if not isinstance(active, dict) or int(active.get("hp", -1) or 0) != 0:
            return None
        active_prize = int(PLANNER._prize_value(int(active.get("id", 0) or 0)))
        remaining_prizes = len(me.get("prize") or [])
        if active_prize <= 0 or remaining_prizes <= active_prize:
            # Active KO alone already wins; target choice cannot improve the result.
            return None
        bench = opponent.get("bench") or []
        shaymin_live = any(
            isinstance(card, dict) and int(card.get("id", 0) or 0) == 343 and int(card.get("hp", 0) or 0) > 0
            for card in bench
        )
        options = select.get("option") or []
        candidates = []
        for index, option in enumerate(options):
            if not isinstance(option, dict) or int(option.get("area", 0) or 0) != 5:
                continue
            bench_index = option.get("index")
            if not isinstance(bench_index, int) or not (0 <= bench_index < len(bench)):
                continue
            pokemon = bench[bench_index]
            if not isinstance(pokemon, dict):
                continue
            card_id = int(pokemon.get("id", 0) or 0)
            hp = int(pokemon.get("hp", 0) or 0)
            if not (0 < hp <= 30):
                continue
            # Known public attack-damage protection: Tera bench rule and Shaymin's
            # Flower Curtain for non-Rule-Box Benched Pokemon.
            if card_id in (96, 117):
                continue
            if shaymin_live and not self._has_rule_box(card_id):
                continue
            prize_value = int(PLANNER._prize_value(card_id))
            if active_prize + prize_value < remaining_prizes:
                continue
            candidates.append((prize_value, -hp, -index, index))
        if not candidates:
            return None
        # Preserve Dawn if it already selected any exact winning split target.
        winning_indices = {row[-1] for row in candidates}
        if any(isinstance(index, int) and index in winning_indices for index in fallback_action):
            return None
        candidate = [int(max(candidates)[-1])]
        EXECUTOR.apply_probe_choice(self.fallback, raw, candidate, probe_state)
        self.diagnostics.tactical_authorizations += 1
        self.diagnostics.shadow_split_authorizations += 1
        self.diagnostics.last_reason = "authorized-shadow-final-split"
        return candidate

    def _exact_adrena_ko(self, raw: dict, fallback_action: list[int], probe_state: dict):
        """Correct only a visible Adrena-Brain KO that Dawn's target would miss."""
        select = self._select(raw)
        context = int(select.get("context", -1) if select.get("context") is not None else -1)
        effect = select.get("effect") if isinstance(select.get("effect"), dict) else {}
        effect_id = int(effect.get("id", 0) or 0)
        effect_serial = int(effect.get("serial", -1) if effect.get("serial") is not None else -1)
        if context == 0:
            self._adrena_counters.clear()
            return None
        if effect_id != 112 or effect_serial < 0:
            return None
        options = select.get("option") or []
        if context == 40:
            chosen_numbers = [
                int(options[index].get("number", 0) or 0)
                for index in fallback_action
                if isinstance(index, int)
                and 0 <= index < len(options)
                and isinstance(options[index], dict)
            ]
            if chosen_numbers:
                self._adrena_counters[effect_serial] = max(chosen_numbers)
            return None
        if context != 13:
            return None
        counters = int(self._adrena_counters.pop(effect_serial, 0) or 0)
        if counters <= 0:
            return None
        packet = 10 * counters
        current = self._current(raw)
        your_index = current.get("yourIndex")
        players = current.get("players") or []
        if not isinstance(your_index, int) or not (0 <= your_index < len(players)) or not isinstance(players[your_index], dict):
            return None
        remaining_prizes = len(players[your_index].get("prize") or [])
        knockout_candidates = []
        for index, option in enumerate(options):
            if not isinstance(option, dict):
                continue
            pokemon = self._option_public_pokemon(raw, option)
            if not isinstance(pokemon, dict):
                continue
            hp = int(pokemon.get("hp", 0) or 0)
            if not (0 < hp <= packet):
                continue
            card_id = int(pokemon.get("id", 0) or 0)
            prize_value = int(PLANNER._prize_value(card_id))
            if prize_value < remaining_prizes:
                continue
            knockout_candidates.append((prize_value, -hp, -index, index))
        if not knockout_candidates:
            return None
        # Preserve Dawn whenever it is already taking a deterministic KO.
        for index in fallback_action:
            if not isinstance(index, int) or not (0 <= index < len(options)):
                continue
            option = options[index]
            pokemon = self._option_public_pokemon(raw, option) if isinstance(option, dict) else None
            if isinstance(pokemon, dict) and 0 < int(pokemon.get("hp", 0) or 0) <= packet:
                return None
        candidate = [int(max(knockout_candidates)[-1])]
        EXECUTOR.apply_probe_choice(self.fallback, raw, candidate, probe_state)
        self.diagnostics.tactical_authorizations += 1
        self.diagnostics.adrena_ko_authorizations += 1
        self.diagnostics.last_reason = "authorized-adrena-final-ko"
        return candidate

    def act(self, raw: dict) -> list[int]:
        self.diagnostics.calls += 1
        current = raw.get("current")
        if not isinstance(current, dict):
            self.reset()
            return list(self.fallback.agent(copy.deepcopy(raw)))

        self.memory.ingest(raw)

        planned = self._continue_plan(raw)
        if planned is not None:
            return planned

        # Probe Dawn exactly once. If search does not earn authority, its state is
        # already synchronized to the action we return.
        fallback_action, probe_state = EXECUTOR.probe_policy_action(self.fallback, raw)
        fallback_action = list(fallback_action)
        tactical = self._exact_shadow_split_finish(raw, fallback_action, probe_state)
        if tactical is not None:
            return tactical
        tactical = self._exact_adrena_ko(raw, fallback_action, probe_state)
        if tactical is not None:
            return tactical
        if not self._eligible(raw, fallback_action):
            self.diagnostics.last_reason = "fallback-ineligible"
            return fallback_action

        turn = int(current.get("turn", -1))
        self._turn_searches[turn] = self._turn_searches.get(turn, 0) + 1
        self.diagnostics.searches += 1
        started = time.perf_counter()
        try:
            result = PLANNER.solve(
                raw,
                self.deck,
                self._seed(raw),
                fallback_action,
                particles=self.particles,
            )
        except Exception:
            self.diagnostics.search_failures += 1
            self.diagnostics.last_reason = "search-failed"
            return fallback_action
        finally:
            self.diagnostics.search_seconds += time.perf_counter() - started

        if not result.get("disagrees"):
            self.diagnostics.last_reason = "fallback-search-agrees"
            return fallback_action
        self.diagnostics.disagreements += 1

        shortlist = self._exact_root_shortlist(raw, result)
        if not shortlist:
            self.diagnostics.last_reason = "no-current-turn-exact-gain"
            return fallback_action
        self.diagnostics.exact_candidates += len(shortlist)

        passed = []
        for shortlist_index, candidate in enumerate(shortlist):
            dependencies = PLANNER.hidden_dependency_ids(result, candidate)
            self.diagnostics.proof_verifications += 1
            verification_started = time.perf_counter()
            try:
                verified = PLANNER.verify_current_turn_pair(
                    raw,
                    self.deck,
                    self._seed(raw) + 5000003 + 100003 * shortlist_index,
                    fallback_action,
                    candidate,
                    dependency_ids=dependencies,
                    worlds=self.verification_worlds,
                    pool_size=self.verification_pool,
                )
            except Exception:
                self.diagnostics.proof_rejections += 1
                continue
            finally:
                self.diagnostics.verification_seconds += time.perf_counter() - verification_started

            exact = self._exact_dominance(verified)
            if not exact.get("qualified") or not exact.get("gain"):
                self.diagnostics.proof_rejections += 1
                continue
            plan = self._proof_plan(exact)
            if not plan:
                self.diagnostics.proof_rejections += 1
                continue
            worst = min(tuple(pair[0]) for pair in exact.get("pairs") or [((0, 0), (0, 0))])
            passed.append((worst, int(bool(exact.get("terminal"))), int(bool(exact.get("prize"))), candidate, plan, exact))

        if not passed:
            self.diagnostics.last_reason = "exact-shortlist-rejected-by-hidden-worlds"
            return fallback_action
        passed.sort(reverse=True, key=lambda row: (row[0], row[1], row[2]))
        _, _, _, candidate, plan, exact = passed[0]
        self.diagnostics.proof_prefix_candidates += 1
        EXECUTOR.apply_probe_choice(self.fallback, raw, candidate, probe_state)
        self._plan = copy.deepcopy(plan)
        self._plan_step = 1
        self._plan_turn = turn
        self._plan_player = int(current.get("yourIndex", -1))
        self.diagnostics.authorizations += 1
        self.diagnostics.terminal_authorizations += int(bool(exact.get("terminal")))
        self.diagnostics.prize_authorizations += int(bool(exact.get("prize")))
        self.diagnostics.planned_steps += 1
        self.diagnostics.last_reason = "authorized-terminal" if exact.get("terminal") else "authorized-prize"
        if self._plan_step >= len(self._plan.get("semantic_path") or []):
            self._plan = None
        return candidate


__all__ = ["ExactAuthorityRuntime", "AuthorityDiagnostics"]
