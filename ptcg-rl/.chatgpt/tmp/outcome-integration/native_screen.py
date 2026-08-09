"""Bounded scratch native screen for a candidate callback package.

This is intentionally outside ``src`` and is not a replacement for the
qualified arena.  It runs five 16-game opponent cells (eight games in each
candidate seat) and retains only compact per-game summaries.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import sys
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping

from ptcg_rl.g1.actions import CompoundActionBuilder, validate_compound_action
from ptcg_rl.g1.environment import DevelopmentEpisodeError, EpisodeEnvironmentV1, FailureMode
from ptcg_rl.g1.models import ContractViolation, SchemaMetadataV1
from ptcg_rl.g1.native import NativeCABTTransport, load_deck
from ptcg_rl.g1.rule_baseline import NativeRulePolicy


OPPONENTS = (
    ("grim-control", "anchor"),
    ("dragapult-ex", "rule:dragapult-ex"),
    ("iono", "rule:iono"),
    ("mega-abomasnow-ex", "rule:mega-abomasnow-ex"),
    ("mega-lucario-ex", "rule:mega-lucario-ex"),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_module(path: Path) -> ModuleType:
    name = f"screen_policy_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load policy module: {path}")
    module = importlib.util.module_from_spec(spec)
    old_path = sys.path.copy()
    try:
        sys.path.insert(0, str(path.parent))
        sys.modules[name] = module
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = old_path
    if not callable(getattr(module, "agent", None)):
        raise RuntimeError(f"policy module has no agent: {path}")
    return module


class RawModulePolicy:
    """Adapt a raw ``agent(obs)`` callback to the native environment contract."""

    def __init__(self, module: ModuleType, deck: list[int], policy_id: str) -> None:
        self._module = module
        self.deck = deck
        self.policy_id = policy_id

    def reset(self, episode_uuid: str, player_index: int, reason: str = "start") -> None:
        adapter = getattr(self._module, "_ADAPTER", None)
        if adapter is not None and callable(getattr(adapter, "_reset_state", None)):
            adapter._reset_state()
        reset = getattr(self._module, "_reset", None)
        if callable(reset):
            reset()

    def choose_native(self, raw: Mapping[str, Any], observation: Any, request: Any) -> Any:
        returned = self._module.agent(copy.deepcopy(raw))
        if not isinstance(returned, list):
            raise ContractViolation("raw candidate output is not a list")
        by_original = {option.original_index: index for index, option in enumerate(request.options)}
        builder = CompoundActionBuilder(request)
        for original_index in returned:
            if isinstance(original_index, bool) or not isinstance(original_index, int):
                raise ContractViolation("raw candidate output contains a non-integer index")
            if original_index not in by_original:
                raise ContractViolation("raw candidate output contains an unavailable index")
            builder.choose(by_original[original_index])
        if not builder.complete:
            builder.stop()
        return validate_compound_action(request, builder.build())


def _candidate_policy(root: Path) -> RawModulePolicy:
    module = _load_module(root / "main.py")
    return RawModulePolicy(module, load_deck(root / "deck.csv"), "outcome-main-candidate")


def _anchor_policy(root: Path) -> RawModulePolicy:
    module_path = root / "qualified_grim_main.py"
    manifest = json.loads((root / "scratch-candidate-manifest.json").read_text(encoding="utf-8"))
    expected = manifest.get("qualified_grim_module_sha256")
    if not isinstance(expected, str) or _sha256(module_path) != expected:
        raise RuntimeError("qualified Grim anchor copy differs from the sealed candidate manifest")
    module = _load_module(module_path)
    return RawModulePolicy(module, load_deck(root / "deck.csv"), "grim-control-anchor")


def _run_game(
    *,
    engine_root: Path,
    card_data: Path,
    private_baselines: Path,
    policy0: Any,
    policy1: Any,
    policy0_name: str,
    policy1_name: str,
    game_id: str,
    request_cap: int,
    game_timeout: int,
    failure_directory: Path,
) -> dict[str, Any]:
    transport = NativeCABTTransport(engine_root)
    metadata = SchemaMetadataV1.build(_sha256(transport.library_path), _sha256(card_data))
    environment = EpisodeEnvironmentV1(
        transport,
        metadata,
        max_requests=request_cap,
        deadline_monotonic=time.monotonic() + game_timeout,
        failure_directory=failure_directory,
        failure_mode=FailureMode.DEVELOPMENT,
    )
    try:
        result = environment.run(
            game_id,
            policy0.deck,
            policy1.deck,
            {0: policy0, 1: policy1},
        )
    except DevelopmentEpisodeError as error:
        result = error.result
    summary = asdict(result.summary)
    return {
        "game_id": game_id,
        "policy0": policy0_name,
        "policy1": policy1_name,
        "status": "pass" if result.failure is None and summary["terminal_result"] is not None else "fail",
        "summary": summary,
        "failure": asdict(result.failure) if result.failure is not None else None,
        "fallback_artifacts": [asdict(item) for item in result.fallback_artifacts],
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    candidate_root = args.candidate.resolve(strict=True)
    engine_root = args.engine_root.resolve(strict=True)
    card_data = args.card_data.resolve(strict=True)
    private_baselines = args.private_baselines.resolve(strict=True)
    if args.games_per_cell != 8:
        raise ValueError("the bounded screen is fixed at exactly eight games per cell")
    candidate = _candidate_policy(candidate_root)
    anchor = _anchor_policy(candidate_root)
    baseline_cache: dict[str, NativeRulePolicy] = {}
    records: list[dict[str, Any]] = []
    for family, opponent_spec in OPPONENTS:
        opponent = anchor if opponent_spec == "anchor" else baseline_cache.setdefault(
            opponent_spec,
            NativeRulePolicy(private_baselines / opponent_spec.split(":", 1)[1]),
        )
        for candidate_seat in (0, 1):
            for replicate in range(args.games_per_cell):
                left, right = (
                    (candidate, opponent) if candidate_seat == 0 else (opponent, candidate)
                )
                left_name, right_name = (
                    ("outcome-main", family) if candidate_seat == 0 else (family, "outcome-main")
                )
                game_id = f"{args.run_id}-{family}-seat{candidate_seat}-{replicate:02d}"
                records.append(
                    _run_game(
                        engine_root=engine_root,
                        card_data=card_data,
                        private_baselines=private_baselines,
                        policy0=left,
                        policy1=right,
                        policy0_name=left_name,
                        policy1_name=right_name,
                        game_id=game_id,
                        request_cap=args.request_cap,
                        game_timeout=args.game_timeout,
                        failure_directory=args.output / "failures" / game_id,
                    )
                )
    candidate_diagnostics = candidate._module.diagnostics()  # type: ignore[attr-defined]
    result = {
        "schema_version": 1,
        "run_id": args.run_id,
        "candidate_root": str(candidate_root),
        "engine_root": str(engine_root),
        "games_requested": len(records),
        "games_completed": sum(item["summary"]["terminal_result"] is not None for item in records),
        "failed_games": sum(item["status"] != "pass" for item in records),
        "invalid_selections": sum(item["summary"]["invalid_selections"] for item in records),
        "fallback_actions": sum(item["summary"]["fallback_actions"] for item in records),
        "candidate_diagnostics": candidate_diagnostics,
        "records": records,
    }
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "screen.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--engine-root", required=True, type=Path)
    parser.add_argument("--card-data", required=True, type=Path)
    parser.add_argument("--private-baselines", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--games-per-cell", type=int, default=8)
    parser.add_argument("--request-cap", type=int, default=20_000)
    parser.add_argument("--game-timeout", type=int, default=300)
    args = parser.parse_args()
    result = run(args)
    print(json.dumps({key: result[key] for key in ("run_id", "games_requested", "games_completed", "failed_games", "invalid_selections", "fallback_actions")}, sort_keys=True))


if __name__ == "__main__":
    main()
