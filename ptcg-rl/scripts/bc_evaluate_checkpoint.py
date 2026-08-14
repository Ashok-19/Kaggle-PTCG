from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any, Sequence

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ptcg_rl.bc.evaluation import (  # noqa: E402
    GreedyRecurrentNeuralPolicyV1,
    candidate_score,
    normal_score_interval,
)
from ptcg_rl.g1.environment import (  # noqa: E402
    DevelopmentEpisodeError,
    EpisodeEnvironmentV1,
    FailureMode,
)
from ptcg_rl.g1.models import SchemaMetadataV1  # noqa: E402
from ptcg_rl.g1.native import NativeCABTTransport, load_deck  # noqa: E402
from ptcg_rl.g1.rule_baseline import NativeRulePolicy  # noqa: E402
from ptcg_rl.g2.checkpoint import load_checkpoint_package, state_dict_sha256  # noqa: E402
from ptcg_rl.g3.checkpoint import restore_training_checkpoint  # noqa: E402


class BCEvaluationError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_candidate(
    initial_checkpoint: Path,
    training_checkpoint: Path,
    training_checkpoint_sha256: str | None,
    device: torch.device,
) -> tuple[Any, dict[str, Any]]:
    loaded = load_checkpoint_package(initial_checkpoint, device=device)
    model = loaded.model
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-4, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda=lambda _step: 1.0)
    restored = restore_training_checkpoint(
        training_checkpoint,
        model=model,
        optimizer=optimizer,
        scheduler=scheduler,
        scaler=None,
        expected_sha256=training_checkpoint_sha256,
        restore_rng=False,
    )
    model.eval()
    state_sha = state_dict_sha256(
        {name: tensor.detach().cpu() for name, tensor in model.state_dict().items()}
    )
    return model, {
        "initial_package_sha256": loaded.package_sha256,
        "training_checkpoint_sha256": restored.payload_sha256,
        "training_checkpoint_bytes": restored.payload_bytes,
        "training_counters": restored.counters,
        "training_league": restored.league,
        "model_state_sha256": state_sha,
        "architecture_sha256": model.architecture_sha256,
        "trainable_parameters": model.trainable_parameter_count,
    }


def _game(
    *,
    model: Any,
    candidate_deck: Sequence[int],
    opponent_directory: Path,
    candidate_player: int,
    engine_root: Path,
    card_data: Path,
    game_id: str,
    request_cap: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    transport = NativeCABTTransport(engine_root)
    metadata = SchemaMetadataV1.build(
        sha256_file(transport.library_path), sha256_file(card_data)
    )
    opponent = NativeRulePolicy(opponent_directory)
    candidate = GreedyRecurrentNeuralPolicyV1(model, player_index=candidate_player)
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
    environment = EpisodeEnvironmentV1(
        transport,
        metadata,
        max_requests=request_cap,
        deadline_monotonic=time.monotonic() + timeout_seconds,
        failure_mode=FailureMode.DEVELOPMENT,
    )
    started = time.perf_counter()
    try:
        result = environment.run(game_id, decks[0], decks[1], policies)
    except DevelopmentEpisodeError as error:
        result = error.result
    elapsed = time.perf_counter() - started
    summary = asdict(result.summary)
    terminal = summary["terminal_result"]
    passed = (
        terminal is not None
        and summary["failure_kind"] is None
        and summary["invalid_selections"] == 0
        and summary["fallback_actions"] == 0
        and summary["post_terminal_actions"] == 0
    )
    score = None if terminal is None else candidate_score(int(terminal), candidate_player)
    return {
        "game_id": game_id,
        "status": "PASS" if passed else "FAIL",
        "candidate_player": candidate_player,
        "candidate_score": score,
        "opponent": opponent_directory.name,
        "summary": summary,
        "elapsed_seconds": elapsed,
        "mean_action_latency_ms": (
            sum(result.action_latencies_ms) / len(result.action_latencies_ms)
            if result.action_latencies_ms
            else None
        ),
        "max_action_latency_ms": max(result.action_latencies_ms, default=None),
    }


def _aggregate(games: Sequence[dict[str, Any]]) -> dict[str, Any]:
    failures = [game for game in games if game["status"] != "PASS"]
    scores = [float(game["candidate_score"]) for game in games if game["candidate_score"] is not None]
    interval = normal_score_interval(scores)
    terminal_counts: Counter[str] = Counter()
    for game in games:
        score = game["candidate_score"]
        if score == 1.0:
            terminal_counts["win"] += 1
        elif score == 0.5:
            terminal_counts["draw"] += 1
        elif score == 0.0:
            terminal_counts["loss"] += 1
        else:
            terminal_counts["nonterminal"] += 1
    return {
        "games": len(games),
        "failures": len(failures),
        "wins": terminal_counts["win"],
        "draws": terminal_counts["draw"],
        "losses": terminal_counts["loss"],
        "nonterminal": terminal_counts["nonterminal"],
        "candidate_score_mean": sum(scores) / len(scores) if scores else None,
        "candidate_score_normal_approx_95": list(interval),
        "engine_requests": sum(
            int(game["summary"]["engine_requests"]) for game in games
        ),
        "invalid_selections": sum(
            int(game["summary"]["invalid_selections"]) for game in games
        ),
        "fallback_actions": sum(
            int(game["summary"]["fallback_actions"]) for game in games
        ),
        "mean_game_seconds": (
            sum(float(game["elapsed_seconds"]) for game in games) / len(games)
            if games
            else None
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate a BC training checkpoint in native games")
    parser.add_argument("--training-checkpoint", type=Path, required=True)
    parser.add_argument("--training-checkpoint-sha256")
    parser.add_argument(
        "--initial-checkpoint",
        type=Path,
        default=ROOT / "private/g2/checkpoint-v1/g2-policy-checkpoint-v1.zip",
    )
    parser.add_argument(
        "--engine-root",
        type=Path,
        default=ROOT.parent
        / "pokemon-tcg-ai-battle/sample_submission/sample_submission",
    )
    parser.add_argument(
        "--card-data",
        type=Path,
        default=ROOT / "private/assets/official/EN_Card_Data.csv",
    )
    parser.add_argument(
        "--candidate-deck",
        type=Path,
        default=ROOT / "private/baselines/mega-lucario-ex/deck.csv",
    )
    parser.add_argument(
        "--opponents",
        nargs="+",
        default=["mega-lucario-ex", "dragapult-ex", "iono", "mega-abomasnow-ex"],
    )
    parser.add_argument("--games-per-opponent", type=int, default=8)
    parser.add_argument("--request-cap", type=int, default=1000)
    parser.add_argument("--game-timeout", type=float, default=60.0)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    if args.games_per_opponent <= 0 or args.request_cap <= 0 or args.game_timeout <= 0:
        raise BCEvaluationError("game counts and limits must be positive")
    device = torch.device(args.device)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise BCEvaluationError("CUDA requested but unavailable")
    torch.set_num_threads(min(2, max(1, torch.get_num_threads())))
    model, model_record = _load_candidate(
        args.initial_checkpoint,
        args.training_checkpoint,
        args.training_checkpoint_sha256,
        device,
    )
    candidate_deck = load_deck(args.candidate_deck)
    baseline_root = ROOT / "private/baselines"
    opponent_directories = [baseline_root / name for name in args.opponents]
    for directory in opponent_directories:
        if not directory.is_dir():
            raise BCEvaluationError(f"opponent baseline directory is missing: {directory}")

    games: list[dict[str, Any]] = []
    for opponent_index, opponent_directory in enumerate(opponent_directories):
        for game_index in range(args.games_per_opponent):
            candidate_player = game_index % 2
            game_id = (
                f"bc-eval-{opponent_index}-{opponent_directory.name}-"
                f"{game_index:04d}-p{candidate_player}"
            )
            game = _game(
                model=model,
                candidate_deck=candidate_deck,
                opponent_directory=opponent_directory,
                candidate_player=candidate_player,
                engine_root=args.engine_root,
                card_data=args.card_data,
                game_id=game_id,
                request_cap=args.request_cap,
                timeout_seconds=args.game_timeout,
            )
            games.append(game)
            print(
                json.dumps(
                    {
                        "event": "game_complete",
                        "game_id": game_id,
                        "opponent": opponent_directory.name,
                        "candidate_player": candidate_player,
                        "candidate_score": game["candidate_score"],
                        "status": game["status"],
                    },
                    sort_keys=True,
                ),
                flush=True,
            )

    by_opponent = {
        directory.name: _aggregate(
            [game for game in games if game["opponent"] == directory.name]
        )
        for directory in opponent_directories
    }
    report = {
        "schema_version": 1,
        "record_id": "bc-native-gameplay-evaluation-v1",
        "status": "PASS" if all(game["status"] == "PASS" for game in games) else "FAIL",
        "model": model_record,
        "candidate_deck": {
            "path": args.candidate_deck.as_posix(),
            "sha256": sha256_file(args.candidate_deck),
        },
        "engine": {
            "root": args.engine_root.as_posix(),
            "library_sha256": sha256_file(args.engine_root / "cg/libcg.so"),
            "card_data_sha256": sha256_file(args.card_data),
        },
        "configuration": {
            "games_per_opponent": args.games_per_opponent,
            "opponents": args.opponents,
            "alternating_candidate_seat": True,
            "policy": "greedy_recurrent_no_fallback",
            "device": str(device),
        },
        "overall": _aggregate(games),
        "by_opponent": by_opponent,
        "games": games,
        "competence_claimed": False,
    }
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        partial = args.out.with_suffix(args.out.suffix + ".partial")
        partial.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        partial.replace(args.out)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
