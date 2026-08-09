from __future__ import annotations

import hashlib
import itertools
import json
import math
import random
import resource
import sys
import time
from dataclasses import fields, is_dataclass
from enum import IntEnum
from pathlib import Path
from typing import Any


REPO = Path(__file__).resolve().parents[3]
SAMPLE = REPO / "private/assets/official/sample_submission/sample_submission"
CARD_DATA = REPO / "private/assets/official/EN_Card_Data.csv"
DECK_FILE = SAMPLE / "deck.csv"
CANARY = REPO / ".chatgpt/tmp/search_feasibility_canary.py"
OUT = Path(__file__).resolve().parent / "probe.json"

sys.path.insert(0, str(SAMPLE))
sys.path.insert(0, str(CANARY.parent))

from cg.api import (  # noqa: E402
    search_begin,
    search_end,
    search_step,
    to_observation_class,
)
from cg.api import Observation  # noqa: E402
from cg.game import battle_finish, battle_select, battle_start  # noqa: E402
import search_feasibility_canary as canary  # noqa: E402


MAX_ROLLOUTS = 128
MAX_CONTINUATION_STEPS = 20_000
MAX_WALL_SECONDS = 570.0
GENERATION_SEED = 20260809
MIN_ROOT_OPTIONS = 5
MIN_LEGAL_ACTIONS = 8


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {field.name: jsonable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, IntEnum):
        return int(value)
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


def read_deck() -> list[int]:
    deck = [int(line.strip()) for line in DECK_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(deck) != 60:
        raise RuntimeError(f"sample deck has {len(deck)} cards, expected 60")
    return deck


def legal_action_count(option_count: int, minimum: int, maximum: int) -> int:
    return sum(math.factorial(option_count) // math.factorial(option_count - count) for count in range(minimum, maximum + 1))


def legal_actions(obs: Observation) -> list[tuple[int, ...]]:
    if obs.select is None:
        return []
    option_count = len(obs.select.option)
    minimum = int(obs.select.minCount)
    maximum = int(obs.select.maxCount)
    expected = legal_action_count(option_count, minimum, maximum)
    if expected > MAX_ROLLOUTS:
        raise ValueError(f"complete legal action set has {expected} actions, over {MAX_ROLLOUTS}")
    actions: list[tuple[int, ...]] = []
    for count in range(minimum, maximum + 1):
        actions.extend(itertools.permutations(range(option_count), count))
    if len(actions) != expected:
        raise AssertionError("legal action enumeration is incomplete")
    return actions


def first_legal_action(obs: Observation) -> list[int]:
    if obs.select is None:
        raise RuntimeError("continuation requested without a selection")
    minimum = int(obs.select.minCount)
    return list(range(minimum))


def random_legal_action(obs: Observation, rng: random.Random) -> list[int]:
    if obs.select is None:
        raise RuntimeError("generated battle has no selection")
    minimum = int(obs.select.minCount)
    maximum = int(obs.select.maxCount)
    count = rng.randint(minimum, maximum)
    return rng.sample(range(len(obs.select.option)), count)


def public_snapshot(obs: Observation) -> dict[str, Any]:
    # search_begin_input is an opaque native serialization and is deliberately not
    # retained as a feature. Everything else is exactly the observation exposed to
    # the acting agent, including its own visible hand and the opponent's hidden
    # placeholders.
    value = jsonable(obs)
    value["search_begin_input"] = None
    return value


def rollout(root_action: tuple[int, ...], root_player: int, obs: Observation, det: dict[str, list[int]], deadline: float) -> dict[str, Any]:
    root = search_begin(
        obs,
        det["your_deck"],
        det["your_prize"],
        det["opponent_deck"],
        det["opponent_prize"],
        det["opponent_hand"],
        det["opponent_active"],
        manual_coin=False,
    )
    steps = 0
    invalid = 0
    post_terminal = 0
    try:
        node = search_step(root.searchId, list(root_action))
        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError("probe wall-time cap reached")
            child_obs = node.observation
            current = child_obs.current
            if current is None:
                raise RuntimeError("search child omitted current state")
            result = int(current.result)
            if result in (0, 1, 2):
                winner = result
                break
            if result != -1:
                raise RuntimeError(f"unknown native result {result}")
            if child_obs.select is None:
                raise RuntimeError("ongoing search child omitted selection")
            if steps >= MAX_CONTINUATION_STEPS:
                raise TimeoutError("continuation step cap reached")
            action = first_legal_action(child_obs)
            try:
                node = search_step(node.searchId, action)
            except (ValueError, IndexError):
                invalid += 1
                raise
            steps += 1
        return {
            "status": "complete",
            "winner": winner,
            "perspective": "W" if winner == root_player else "L" if winner == 1 - root_player else "D",
            "continuation_steps": steps,
            "invalid_actions": invalid,
            "post_terminal_actions": post_terminal,
            "fallback_actions": 0,
            "manual_coin": False,
            "continuation_policy": "first_legal_action(minCount prefix)",
        }
    finally:
        search_end()


def summarize_rollouts(records: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {label: sum(record["perspective"] == label for record in records) for label in ("W", "D", "L")}
    n = len(records)
    probs = {label: counts[label] / n for label in counts} if n else {label: None for label in counts}
    rewards = [(1.0 if record["perspective"] == "W" else 0.5 if record["perspective"] == "D" else 0.0) for record in records]
    mean_reward = sum(rewards) / n if n else None
    variance = (sum((value - mean_reward) ** 2 for value in rewards) / n) if n and mean_reward is not None else None
    return {
        "rollouts": n,
        "wdl_counts": counts,
        "wdl_probabilities": probs,
        "expected_match_score": mean_reward,
        "expected_match_score_stderr": math.sqrt(variance / n) if variance is not None and n else None,
        "uncertainty": "multinomial empirical uncertainty; single continuation policy and native coin randomness",
        "continuation_steps": {
            "min": min((record["continuation_steps"] for record in records), default=None),
            "max": max((record["continuation_steps"] for record in records), default=None),
            "mean": sum(record["continuation_steps"] for record in records) / n if n else None,
        },
    }


def generate_state(deck: list[int], deadline: float) -> tuple[dict[str, Any], Observation, int]:
    rng = random.Random(GENERATION_SEED)
    raw, start = battle_start(deck, deck)
    if raw is None:
        raise RuntimeError(f"BattleStart failed: player={start.errorPlayer} type={start.errorType}")
    steps = 0
    try:
        while time.monotonic() < deadline and steps < MAX_CONTINUATION_STEPS:
            obs = to_observation_class(raw)
            if obs.current is None:
                raise RuntimeError("generated state has no current state")
            if int(obs.current.result) in (0, 1, 2):
                break
            if obs.select is None:
                raise RuntimeError("ongoing generated state has no selection")
            if int(obs.select.type) == 0:
                count = legal_action_count(len(obs.select.option), int(obs.select.minCount), int(obs.select.maxCount))
                if len(obs.select.option) >= MIN_ROOT_OPTIONS and count >= MIN_LEGAL_ACTIONS and count <= MAX_ROLLOUTS:
                    return raw, obs, steps
            raw = battle_select(random_legal_action(obs, rng))
            steps += 1
    finally:
        # The search API consumes the serialized observation, not the live battle.
        battle_finish()
    raise TimeoutError("no generated high-branching MAIN state within generation cap")


def main() -> int:
    started = time.monotonic()
    deadline = started + MAX_WALL_SECONDS
    deck = read_deck()
    source_hashes = {
        "probe": sha256_file(Path(__file__)),
        "search_feasibility_canary": sha256_file(CANARY),
        "game_wrapper": sha256_file(SAMPLE / "cg/game.py"),
        "api_wrapper": sha256_file(SAMPLE / "cg/api.py"),
        "sim_wrapper": sha256_file(SAMPLE / "cg/sim.py"),
        "native_library": sha256_file(SAMPLE / "cg/libcg.so"),
        "card_data": sha256_file(CARD_DATA),
        "deck": sha256_file(DECK_FILE),
    }
    report: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "counterfactual-q-one-state-v1",
        "status": "RUNNING",
        "created_at_epoch": time.time(),
        "command": sys.argv,
        "limits": {
            "max_total_continuation_rollouts": MAX_ROLLOUTS,
            "max_continuation_steps_per_rollout": MAX_CONTINUATION_STEPS,
            "max_wall_seconds": MAX_WALL_SECONDS,
        },
        "assets": source_hashes,
        "label_generation": {
            "native_search_api": "cg.api.search_begin/search_step/search_end",
            "hidden_state_use": "determinized hidden deck/prize/hand/active arrays only for native label generation",
            "hidden_state_in_public_features": False,
            "inference_policy": "not run; no production policy changed",
            "continuation_policy": "first legal action (minimum-count prefix) for both players",
            "manual_coin": False,
        },
        "counters": {
            "invalid_actions": 0,
            "fallback_actions": 0,
            "post_terminal_actions": 0,
            "continuation_errors": 0,
            "incomplete_rollouts": 0,
        },
    }
    try:
        raw, obs, generation_steps = generate_state(deck, deadline)
        actions = legal_actions(obs)
        if len(actions) < MIN_LEGAL_ACTIONS:
            raise RuntimeError(f"generated state legal action count {len(actions)} below high-branching threshold")
        root_player = int(obs.current.yourIndex)
        det = canary.determinize(obs, deck, deck, GENERATION_SEED + generation_steps)
        budget = MAX_ROLLOUTS
        base = budget // len(actions)
        remainder = budget % len(actions)
        per_action = [base + (index < remainder) for index in range(len(actions))]
        action_records: list[dict[str, Any]] = []
        for action_index, action in enumerate(actions):
            labels: list[dict[str, Any]] = []
            for repeat in range(per_action[action_index]):
                if time.monotonic() >= deadline:
                    raise TimeoutError("probe wall-time cap reached before all action labels")
                try:
                    labels.append(rollout(action, root_player, obs, det, deadline))
                except (ValueError, IndexError):
                    report["counters"]["invalid_actions"] += 1
                    raise
                except TimeoutError:
                    report["counters"]["incomplete_rollouts"] += 1
                    raise
                except Exception:
                    report["counters"]["continuation_errors"] += 1
                    raise
            action_records.append({
                "action_index": action_index,
                "action": list(action),
                "option_semantics": [jsonable(obs.select.option[index]) for index in action],
                "rollouts": labels,
                "label": summarize_rollouts(labels),
            })
        report["status"] = "PASS_COMPLETE"
        report["generated_state"] = {
            "generation_seed": GENERATION_SEED,
            "generation_steps": generation_steps,
            "root_player": root_player,
            "turn": int(obs.current.turn),
            "selection_type": int(obs.select.type),
            "selection_context": int(obs.select.context),
            "root_option_count": len(obs.select.option),
            "complete_legal_action_count": len(actions),
            "legal_action_enumeration": "all ordered unique permutations for every count in [minCount,maxCount]",
            "public_feature_snapshot": public_snapshot(obs),
            "public_feature_snapshot_sha256": hashlib.sha256(json.dumps(public_snapshot(obs), sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "action_records": action_records,
        }
        report["counters"]["total_continuation_rollouts"] = sum(per_action)
        report["counters"]["terminal_labels"] = sum(record["label"]["rollouts"] for record in action_records)
        report["counters"]["nonterminal_labels"] = 0
    except Exception as error:
        report["status"] = "BLOCKED_OR_FAILED"
        report["error"] = {"type": type(error).__name__, "message": str(error)[:1000]}
    finally:
        report["elapsed_seconds"] = time.monotonic() - started
        report["peak_rss_bytes"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        OUT.with_suffix(OUT.suffix + ".sha256").write_text(sha256_file(OUT) + "  " + OUT.name + "\n", encoding="ascii")
    print(json.dumps({
        "status": report["status"],
        "output": str(OUT),
        "elapsed_seconds": report["elapsed_seconds"],
        "counters": report["counters"],
        "error": report.get("error"),
    }, sort_keys=True))
    return 0 if report["status"] == "PASS_COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
