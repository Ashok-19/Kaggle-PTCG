from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

import torch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ptcg_rl.g1.environment import (  # noqa: E402
    DevelopmentEpisodeError,
    EpisodeEnvironmentV1,
    FailureMode,
)
from ptcg_rl.g1.evidence import sha256_file  # noqa: E402
from ptcg_rl.g1.models import SchemaMetadataV1  # noqa: E402
from ptcg_rl.g1.native import NativeCABTTransport, load_deck  # noqa: E402
from ptcg_rl.g2.checkpoint import load_checkpoint_package  # noqa: E402
from ptcg_rl.g3.e04_authorization import (  # noqa: E402
    load_native_authorization,
    verify_native_authorization_assets,
)
from ptcg_rl.g3.native_zero_update import (  # noqa: E402
    EngineRequestSequenceV1,
    NATIVE_POLICY_ID,
    NativeTraceNeuralPolicyV1,
)
from ptcg_rl.g3.zero_update_bridge import (  # noqa: E402
    TruncationClassV1,
    ZeroUpdateBridgeV1,
)


ENGINE_ROOT = ROOT / "private/assets/official/sample_submission/sample_submission"
ENGINE_LIBRARY = ENGINE_ROOT / "cg/libcg.so"
WRAPPER_API = ENGINE_ROOT / "cg/api.py"
CARD_DATA = ROOT / "private/assets/official/EN_Card_Data.csv"
DECK = ROOT / "private/baselines/mega-lucario-ex/deck.csv"
CHECKPOINT = ROOT / "private/g2/checkpoint-v1/g2-policy-checkpoint-v1.zip"
MAX_REQUESTS = 20_000
GAME_TIMEOUT_SECONDS = 300.0


class E04RunnerError(RuntimeError):
    pass


def atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    authorization_path = args.authorization.resolve()
    authorization = load_native_authorization(
        authorization_path,
        require_authorized=True,
    )
    assets = verify_native_authorization_assets(
        authorization,
        engine_library=ENGINE_LIBRARY,
        wrapper_api=WRAPPER_API,
        card_data=CARD_DATA,
        deck=DECK,
        checkpoint=CHECKPOINT,
    )
    output_directory = (ROOT / authorization.output_directory).resolve()
    try:
        output_directory.relative_to(ROOT)
    except ValueError as error:
        raise E04RunnerError("E04 output directory escapes the project root") from error
    report_path = output_directory / "e04-native-zero-update-report.json"
    bridge_path = output_directory / "e04-native-zero-update-bridge.json"
    games_path = output_directory / "e04-native-zero-update-games.json"
    if not args.overwrite and (
        report_path.exists() or bridge_path.exists() or games_path.exists()
    ):
        raise E04RunnerError(
            "E04 output exists; overwrite requires deliberate review"
        )

    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(1)
    loaded = load_checkpoint_package(
        CHECKPOINT,
        device=torch.device("cpu"),
        expected_package_sha256=authorization.checkpoint_sha256,
        expected_source_commit=None,
        source_root=ROOT,
    )
    loaded.model.eval()
    bridge = ZeroUpdateBridgeV1(policy_id=NATIVE_POLICY_ID, policy_version=0)
    request_sequence = EngineRequestSequenceV1()
    metadata = SchemaMetadataV1.build(
        authorization.engine_sha256,
        authorization.card_data_sha256,
    )
    deck = load_deck(DECK)
    game_records: list[dict[str, Any]] = []
    started = time.monotonic()

    for game_index in range(authorization.games):
        episode_id = f"e04-{authorization.stage}-{game_index:04d}"
        bridge.start_episode(episode_id)
        policies = {
            player: NativeTraceNeuralPolicyV1(
                model=loaded.model,
                bridge=bridge,
                player_index=player,
                request_sequence=request_sequence,
            )
            for player in (0, 1)
        }
        environment = EpisodeEnvironmentV1(
            NativeCABTTransport(ENGINE_ROOT),
            metadata,
            max_requests=MAX_REQUESTS,
            deadline_monotonic=time.monotonic() + GAME_TIMEOUT_SECONDS,
            failure_directory=output_directory / "failures",
            failure_mode=FailureMode.DEVELOPMENT,
        )
        try:
            result = environment.run(episode_id, deck, deck, policies)
        except DevelopmentEpisodeError as error:
            result = error.result
            classification = (
                TruncationClassV1.WALL_TIME
                if result.summary.failure_kind == "timeout"
                else TruncationClassV1.ENGINE_ERROR
            )
            bridge.close_truncated_episode(episode_id, classification)
        else:
            if result.summary.terminal_result not in (-1, 0, 1):
                raise E04RunnerError(
                    "native E04 game did not produce a valid terminal result"
                )
            bridge.close_terminal_episode(
                episode_id,
                result.summary.terminal_result,
            )
        game_records.append(
            {
                "game_index": game_index,
                "episode_id": episode_id,
                "summary": asdict(result.summary),
                "failure": (
                    None if result.failure is None else asdict(result.failure)
                ),
            }
        )
        atomic_json(
            games_path,
            {
                "schema_version": 1,
                "record_id": f"e04-native-zero-update-{authorization.stage}-games-v1",
                "games": game_records,
            },
        )
        if (
            (game_index + 1) % authorization.bridge_checkpoint_interval_games == 0
            or game_index + 1 == authorization.games
        ):
            atomic_json(bridge_path, bridge.state_dict())

    qualification = bridge.qualification_summary(
        minimum_games=authorization.games,
        minimum_meaningful_decisions=authorization.minimum_meaningful_decisions,
    )
    report = {
        "schema_version": 1,
        "record_id": f"e04-native-zero-update-{authorization.stage}-v1",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": "PASS",
        "decision": "QUALIFIED_ZERO_UPDATE_STAGE",
        "authorization": {
            "path": authorization_path.as_posix(),
            "sha256": sha256_file(authorization_path),
            "record_id": authorization.record_id,
            "stage": authorization.stage,
            "games": authorization.games,
            "optimizer_steps_authorized": 0,
            "external_compute_authorized": False,
        },
        "assets": assets,
        "checkpoint": {
            "package_sha256": loaded.package_sha256,
            "package_bytes": loaded.package_bytes,
            "qualification_state_sha256": loaded.manifest["evidence"][
                "qualification_state_sha256"
            ],
        },
        "execution": {
            "device": "cpu",
            "single_process": True,
            "optimizer_created": False,
            "optimizer_steps": 0,
            "training_loop_ran": False,
            "bridge_checkpoint_interval_games": (
                authorization.bridge_checkpoint_interval_games
            ),
            "wall_seconds": time.monotonic() - started,
        },
        "games": game_records,
        "game_ledger": {
            "path": games_path.as_posix(),
            "sha256": sha256_file(games_path),
        },
        "qualification": qualification,
        "bridge_checkpoint": {
            "path": bridge_path.as_posix(),
            "sha256": sha256_file(bridge_path),
        },
        "cost_usd": 0.0,
    }
    atomic_json(report_path, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
