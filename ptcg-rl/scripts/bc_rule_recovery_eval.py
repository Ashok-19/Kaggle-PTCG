from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

from ptcg_rl.bc.evaluation import candidate_score
from ptcg_rl.g1.environment import DevelopmentEpisodeError, EpisodeEnvironmentV1, FailureMode
from ptcg_rl.g1.models import SchemaMetadataV1
from ptcg_rl.g1.native import NativeCABTTransport, load_deck
from ptcg_rl.g1.rule_baseline import NativeRulePolicy

ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--candidate-deck",
        type=Path,
        default=ROOT / "private/evaluation/dragapult-bc-canonical/deck.csv",
    )
    parser.add_argument(
        "--candidate-rule",
        type=Path,
        default=ROOT / "private/baselines/dragapult-ex",
    )
    parser.add_argument(
        "--opponents",
        nargs="+",
        default=["mega-lucario-ex", "dragapult-ex", "iono", "mega-abomasnow-ex"],
    )
    parser.add_argument("--games-per-opponent", type=int, default=8)
    parser.add_argument(
        "--engine-root",
        type=Path,
        default=ROOT.parent / "pokemon-tcg-ai-battle/sample_submission/sample_submission",
    )
    parser.add_argument(
        "--card-data",
        type=Path,
        default=ROOT / "private/assets/official/EN_Card_Data.csv",
    )
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    if args.games_per_opponent <= 0:
        raise ValueError("games-per-opponent must be positive")
    candidate_deck = load_deck(args.candidate_deck)
    transport_probe = NativeCABTTransport(args.engine_root)
    metadata = SchemaMetadataV1.build(
        _sha256(transport_probe.library_path), _sha256(args.card_data)
    )
    del transport_probe

    games: list[dict[str, Any]] = []
    for opponent_index, opponent_name in enumerate(args.opponents):
        opponent_directory = ROOT / "private/baselines" / opponent_name
        for game_index in range(args.games_per_opponent):
            candidate_player = game_index % 2
            candidate = NativeRulePolicy(args.candidate_rule)
            opponent = NativeRulePolicy(opponent_directory)
            policies = (
                {0: candidate, 1: opponent}
                if candidate_player == 0
                else {0: opponent, 1: candidate}
            )
            decks = (
                (candidate_deck, opponent.deck)
                if candidate_player == 0
                else (opponent.deck, candidate_deck)
            )
            game_id = (
                f"rule-recovery-{opponent_index}-{opponent_name}-"
                f"{game_index:04d}-p{candidate_player}"
            )
            environment = EpisodeEnvironmentV1(
                NativeCABTTransport(args.engine_root),
                metadata,
                max_requests=1000,
                deadline_monotonic=time.monotonic() + 60.0,
                failure_mode=FailureMode.DEVELOPMENT,
            )
            try:
                result = environment.run(game_id, decks[0], decks[1], policies)
            except DevelopmentEpisodeError as error:
                result = error.result
            terminal = result.summary.terminal_result
            score = (
                None
                if terminal is None
                else candidate_score(int(terminal), candidate_player)
            )
            games.append(
                {
                    "game_id": game_id,
                    "opponent": opponent_name,
                    "candidate_player": candidate_player,
                    "score": score,
                    "failure_kind": result.summary.failure_kind,
                    "invalid_selections": result.summary.invalid_selections,
                    "fallback_actions": result.summary.fallback_actions,
                    "engine_requests": result.summary.engine_requests,
                }
            )

    by_opponent: dict[str, dict[str, Any]] = {}
    for opponent_name in args.opponents:
        selected = [game for game in games if game["opponent"] == opponent_name]
        by_opponent[opponent_name] = {
            "games": len(selected),
            "wins": sum(game["score"] == 1.0 for game in selected),
            "losses": sum(game["score"] == 0.0 for game in selected),
            "failures": sum(game["failure_kind"] is not None for game in selected),
            "invalid_selections": sum(int(game["invalid_selections"]) for game in selected),
            "fallback_actions": sum(int(game["fallback_actions"]) for game in selected),
        }
        by_opponent[opponent_name]["win_rate"] = (
            by_opponent[opponent_name]["wins"] / len(selected)
        )
    wins = sum(game["score"] == 1.0 for game in games)
    report = {
        "record_id": "bc-rule-recovery-eval-v1",
        "candidate_deck": str(args.candidate_deck),
        "candidate_rule": str(args.candidate_rule),
        "overall": {
            "games": len(games),
            "wins": wins,
            "losses": sum(game["score"] == 0.0 for game in games),
            "win_rate": wins / len(games),
            "failures": sum(game["failure_kind"] is not None for game in games),
            "invalid_selections": sum(int(game["invalid_selections"]) for game in games),
            "fallback_actions": sum(int(game["fallback_actions"]) for game in games),
        },
        "by_opponent": by_opponent,
        "games": games,
    }
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
