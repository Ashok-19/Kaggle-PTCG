from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from ptcg_rl.g3.gold_path import sha256_file


AUTHORIZATION_SCHEMA_VERSION = 1
STAGE_CONTRACTS = {
    "single_process_trace": {
        "decision_id": "DEC-011",
        "games": 1,
        "minimum_meaningful_decisions": 1,
        "bridge_checkpoint_interval_games": 1,
    },
    "smoke": {
        "decision_id": "DEC-011",
        "games": 10,
        "minimum_meaningful_decisions": 1,
        "bridge_checkpoint_interval_games": 1,
    },
    "qualification": {
        "decision_id": "DEC-012",
        "games": 180,
        "minimum_meaningful_decisions": 10_000,
        "bridge_checkpoint_interval_games": 10,
    },
}


class E04AuthorizationError(ValueError):
    pass


@dataclass(frozen=True)
class NativeRunAuthorizationV1:
    record_id: str
    stage: str
    games: int
    minimum_meaningful_decisions: int
    output_directory: str
    engine_sha256: str
    wrapper_sha256: str
    card_data_sha256: str
    deck_sha256: str
    checkpoint_sha256: str
    authorized: bool
    optimizer_steps_authorized: int
    external_compute_authorized: bool
    bridge_checkpoint_interval_games: int


def _require_sha256(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise E04AuthorizationError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _safe_relative_path(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise E04AuthorizationError(f"{name} must be a nonempty POSIX relative path")
    path = Path(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise E04AuthorizationError(f"{name} is not a safe relative path")
    return value


def load_native_authorization(
    path: Path,
    *,
    require_authorized: bool = True,
) -> NativeRunAuthorizationV1:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise E04AuthorizationError(f"cannot load E04 authorization: {error}") from error
    if not isinstance(value, Mapping):
        raise E04AuthorizationError("E04 authorization root must be an object")
    if value.get("schema_version") != AUTHORIZATION_SCHEMA_VERSION:
        raise E04AuthorizationError("unsupported E04 authorization schema")
    stage = value.get("stage")
    if stage not in STAGE_CONTRACTS:
        raise E04AuthorizationError("E04 authorization stage differs")
    contract = STAGE_CONTRACTS[str(stage)]
    if value.get("decision_id") != contract["decision_id"]:
        raise E04AuthorizationError("E04 authorization decision binding differs")
    if value.get("games") != contract["games"]:
        raise E04AuthorizationError("E04 authorization game count differs from the stage")
    if value.get("minimum_meaningful_decisions") != contract[
        "minimum_meaningful_decisions"
    ]:
        raise E04AuthorizationError(
            "E04 authorization decision floor differs from the stage"
        )
    checkpoint_interval = value.get("bridge_checkpoint_interval_games", 1)
    if checkpoint_interval != contract["bridge_checkpoint_interval_games"]:
        raise E04AuthorizationError(
            "E04 bridge checkpoint interval differs from the stage"
        )
    if value.get("optimizer_steps_authorized") != 0:
        raise E04AuthorizationError(
            "E04 authorization must permit zero optimizer steps"
        )
    if value.get("external_compute_authorized") is not False:
        raise E04AuthorizationError(
            "E04 native trace must not authorize external compute"
        )
    authorized = value.get("authorized")
    if not isinstance(authorized, bool):
        raise E04AuthorizationError("E04 authorized flag must be boolean")
    if require_authorized and not authorized:
        raise E04AuthorizationError("E04 native execution is not authorized")
    record_id = value.get("record_id")
    if not isinstance(record_id, str) or not record_id:
        raise E04AuthorizationError("E04 authorization record_id must be nonempty")
    return NativeRunAuthorizationV1(
        record_id=record_id,
        stage=str(stage),
        games=int(value["games"]),
        minimum_meaningful_decisions=int(value["minimum_meaningful_decisions"]),
        output_directory=_safe_relative_path(
            value.get("output_directory"), "output_directory"
        ),
        engine_sha256=_require_sha256(value.get("engine_sha256"), "engine_sha256"),
        wrapper_sha256=_require_sha256(value.get("wrapper_sha256"), "wrapper_sha256"),
        card_data_sha256=_require_sha256(
            value.get("card_data_sha256"), "card_data_sha256"
        ),
        deck_sha256=_require_sha256(value.get("deck_sha256"), "deck_sha256"),
        checkpoint_sha256=_require_sha256(
            value.get("checkpoint_sha256"), "checkpoint_sha256"
        ),
        authorized=authorized,
        optimizer_steps_authorized=0,
        external_compute_authorized=False,
        bridge_checkpoint_interval_games=int(checkpoint_interval),
    )


def verify_native_authorization_assets(
    authorization: NativeRunAuthorizationV1,
    *,
    engine_library: Path,
    wrapper_api: Path,
    card_data: Path,
    deck: Path,
    checkpoint: Path,
) -> dict[str, dict[str, Any]]:
    expected = {
        "engine_library": (engine_library, authorization.engine_sha256),
        "wrapper_api": (wrapper_api, authorization.wrapper_sha256),
        "card_data": (card_data, authorization.card_data_sha256),
        "deck": (deck, authorization.deck_sha256),
        "checkpoint": (checkpoint, authorization.checkpoint_sha256),
    }
    records: dict[str, dict[str, Any]] = {}
    for name, (path, expected_sha256) in expected.items():
        if not path.is_file() or path.is_symlink():
            raise E04AuthorizationError(
                f"required E04 asset is missing or a symlink: {name}"
            )
        observed = sha256_file(path)
        if observed != expected_sha256:
            raise E04AuthorizationError(f"E04 asset hash differs: {name}")
        records[name] = {
            "path": path.as_posix(),
            "bytes": path.stat().st_size,
            "sha256": observed,
        }
    return records
