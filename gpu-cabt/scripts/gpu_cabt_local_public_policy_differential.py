from __future__ import annotations

import json
import struct
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from gpu_cabt.device_runtime import GpuCabtRuntime, default_official_dir

ENV_COUNT = 8
AREAS = {"deck": 1, "hand": 2, "discard": 3, "active": 4, "bench": 5, "prize": 6, "stadium": 7, "looking": 12}


def _deck(path: Path) -> np.ndarray:
    values = np.loadtxt(path, dtype=np.int32)
    if values.shape != (60,):
        raise ValueError(f"expected 60 cards at {path}, got {values.shape}")
    return values


def _compile(source: Path, output: Path, include: Path, standard: str) -> None:
    subprocess.run(
        ["g++", f"-std={standard}", "-O2", "-I", str(include), str(source), "-o", str(output)],
        check=True,
    )


def _fixture_input(decks: np.ndarray) -> bytes:
    return (" ".join(str(int(value)) for value in decks.reshape(-1)) + "\n").encode()


def _native_rows(repo_root: Path, decks: np.ndarray) -> list[dict[str, object]]:
    official = default_official_dir()
    source = repo_root / "scripts/gpu_cabt_public_policy_native_probe.cpp"
    with tempfile.TemporaryDirectory(prefix="gpu-cabt-native-policy-") as tmp:
        exe = Path(tmp) / "probe"
        _compile(source, exe, official, "c++23")
        output = subprocess.check_output([str(exe)], input=_fixture_input(decks))
    rows = [json.loads(line) for line in output.decode().splitlines() if line]
    if len(rows) != ENV_COUNT:
        raise RuntimeError(f"native rows {len(rows)} != {ENV_COUNT}")
    return rows


def _gpuabi(repo_root: Path, decks: np.ndarray) -> tuple[int, int, np.ndarray, np.ndarray]:
    include = repo_root / "src/gpu_cabt/native"
    source = repo_root / "scripts/gpu_cabt_public_policy_gpuabi_probe.cpp"
    with tempfile.TemporaryDirectory(prefix="gpu-cabt-abi-policy-") as tmp:
        exe = Path(tmp) / "probe"
        _compile(source, exe, include, "c++17")
        blob = subprocess.check_output([str(exe)], input=_fixture_input(decks))
    state_size, runtime_size, count = struct.unpack("<III", blob[:12])
    if count != ENV_COUNT:
        raise RuntimeError(f"GPU ABI rows {count} != {ENV_COUNT}")
    state_end = 12 + count * state_size
    runtime_end = state_end + count * runtime_size
    if len(blob) != runtime_end:
        raise RuntimeError(f"GPU ABI payload {len(blob)} != {runtime_end}")
    states = np.frombuffer(blob[12:state_end], dtype=np.uint8).copy()
    runtimes = np.frombuffer(blob[state_end:runtime_end], dtype=np.uint8).copy()
    return state_size, runtime_size, states, runtimes


def _ids(cards: object) -> list[int | None] | None:
    if cards is None:
        return None
    return [None if card is None else int(card["id"]) for card in cards]  # type: ignore[index]


def _zone(rows: np.ndarray, area: int, relative_player: int | None = None) -> list[int | None]:
    selected = rows[rows[:, 2] == area]
    if relative_player is not None:
        selected = selected[selected[:, 1] == relative_player]
    return [int(row[0]) if int(row[4]) else None for row in selected]


def _rel(player: int, actor: int) -> int:
    return 0 if player == actor else 1


def _compare(
    native: dict[str, object],
    globals_row: np.ndarray,
    players: np.ndarray,
    entities: np.ndarray,
    options: np.ndarray,
    actor: int,
) -> list[str]:
    errors: list[str] = []
    current = native["current"]  # type: ignore[index]
    select = native["select"]  # type: ignore[index]
    native_players = current["players"]  # type: ignore[index]
    active_player = ((int(current["turn"]) + 1) ^ int(current["firstPlayer"])) & 1  # type: ignore[index]
    context_card = select["contextCard"]  # type: ignore[index]
    effect_card = select["effect"]  # type: ignore[index]
    stadium = current["stadium"]  # type: ignore[index]
    native_looking = _ids(current["looking"])  # type: ignore[index]
    looking_mode = 0 if native_looking is None else (2 if all(card is None for card in native_looking) else 1)
    expected_globals = {
        0: int(current["turn"]), 1: int(current["turnActionCount"]),  # type: ignore[index]
        2: _rel(int(current["firstPlayer"]), actor),  # type: ignore[index]
        3: _rel(active_player, actor), 4: 0, 5: 0,
        6: int(select["type"]) + 1, 7: int(select["context"]) + 1,  # type: ignore[index]
        8: int(select["minCount"]), 9: int(select["maxCount"]),  # type: ignore[index]
        10: int(select["remainDamageCounter"]), 11: int(select["remainEnergyCost"]),  # type: ignore[index]
        12: int(bool(current["supporterPlayed"])), 13: int(bool(current["stadiumPlayed"])),  # type: ignore[index]
        14: int(bool(current["energyAttached"])), 15: int(bool(current["retreated"])),  # type: ignore[index]
        16: int(context_card["id"]), 17: int(effect_card["id"]), 18: 1,
        19: looking_mode, 20: 0 if native_looking is None else len(native_looking),
        21: int(stadium[0]["id"]), 22: len(select["option"]),  # type: ignore[index]
    }
    for index, expected in expected_globals.items():
        if int(globals_row[index]) != expected:
            errors.append(f"global[{index}]={int(globals_row[index])}, expected {expected}")

    for relative, absolute in enumerate((actor, 1 - actor)):
        p = native_players[absolute]
        expected_player = [
            int(p["deckCount"]), int(p["handCount"]), len(p["prize"]),
            sum(card is not None for card in p["prize"]), len(p["bench"]), int(p["benchMax"]),
            int(bool(p["active"] and p["active"][0] is None)), int(bool(p["poisoned"])),
            int(bool(p["burned"])), int(bool(p["asleep"])), int(bool(p["paralyzed"])), int(bool(p["confused"])),
        ]
        if players[relative].tolist() != expected_player:
            errors.append(f"player[{relative}]={players[relative].tolist()}, expected {expected_player}")
        for api_key in ("active", "bench", "discard", "prize"):
            actual = _zone(entities, AREAS[api_key], relative)
            expected = _ids(p[api_key])
            if actual != expected:
                errors.append(f"{api_key}/rel{relative}={actual}, expected {expected}")

    if _zone(entities, AREAS["hand"], 0) != _ids(native_players[actor]["hand"]):
        errors.append("own hand mismatch")
    if _zone(entities, AREAS["hand"], 1):
        errors.append("opponent hand exposed")
    if _zone(entities, AREAS["deck"], 0) != _ids(select["deck"]):
        errors.append("own selected deck mismatch")
    if _zone(entities, AREAS["deck"], 1):
        errors.append("opponent deck exposed")
    if _zone(entities, AREAS["stadium"]) != _ids(stadium):
        errors.append("stadium mismatch")
    expected_looking = [] if native_looking is None else native_looking
    if _zone(entities, AREAS["looking"]) != expected_looking:
        errors.append("looking mismatch")

    native_options = select["option"]
    if len(options) != len(native_options):
        errors.append(f"options={len(options)}, expected {len(native_options)}")
    else:
        for index, (row, option) in enumerate(zip(options, native_options, strict=True)):
            option_type = int(option["type"])
            if int(row[0]) != option_type:
                errors.append(f"option {index} type mismatch")
                continue
            if option_type == 0 and int(row[3]) != int(option["number"]):
                errors.append(f"option {index} number mismatch")
            elif option_type == 3:
                expected = [int(option["area"]), int(option["index"]), int(option["playerIndex"])]
                if row[3:6].tolist() != expected:
                    errors.append(f"option {index} card params mismatch")
            elif option_type == 7 and int(row[3]) != int(option["index"]):
                errors.append(f"option {index} play index mismatch")
            elif option_type == 15:
                if int(row[3]) != int(option["cardId"]) or int(row[8]) != int(option["cardId"]):
                    errors.append(f"option {index} skill id mismatch")
                if int(row[10]) != AREAS["active"] or int(row[12]) != 0:
                    errors.append(f"option {index} skill source mismatch")
            if int(row[19]) != 1:
                errors.append(f"option {index} legal marker missing")
    return errors


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    decks = np.stack(
        (
            _deck(repo_root / "data/decks/lucario-modern-v1.csv"),
            _deck(repo_root / "data/decks/dragapult-ex.csv"),
        )
    )
    native = _native_rows(repo_root, decks)
    state_size, runtime_size, states, runtimes = _gpuabi(repo_root, decks)
    gpu = GpuCabtRuntime(ENV_COUNT)
    if state_size != gpu.abi.state_bytes or runtime_size != gpu.abi.runtime_bytes:
        raise RuntimeError(
            f"ABI mismatch host=({state_size},{runtime_size}) device=({gpu.abi.state_bytes},{gpu.abi.runtime_bytes})"
        )
    gpu.states.set(states)
    gpu.runtimes.set(runtimes)
    projection = gpu.project_policy()
    gpu.synchronize()
    globals_host = projection.globals.get()
    players_host = projection.players.get()
    entities_host = projection.entities.get()
    entity_counts = projection.entity_counts.get()
    options_host = projection.options.get()
    option_counts = projection.option_counts.get()
    status = projection.status.get()

    mismatches: list[dict[str, object]] = []
    for env in range(ENV_COUNT):
        actor, mode = env // 4, env & 3
        if int(status[env]) != 0:
            mismatches.append({"env": env, "actor": actor, "mode": mode, "status": int(status[env])})
            continue
        errors = _compare(
            native[env], globals_host[env], players_host[env],
            entities_host[env, : int(entity_counts[env])],
            options_host[env, : int(option_counts[env])], actor,
        )
        if errors:
            mismatches.append({"env": env, "actor": actor, "mode": mode, "errors": errors})

    for actor in (0, 1):
        actor_env, both_env = actor * 4, actor * 4 + 1
        if native[actor_env]["current"]["looking"] != native[both_env]["current"]["looking"]:  # type: ignore[index]
            mismatches.append({"actor": actor, "error": "native actor/both looking differ"})
        if not np.array_equal(globals_host[actor_env], globals_host[both_env]):
            mismatches.append({"actor": actor, "error": "GPU globals distinguish native-identical looking"})
        left = entities_host[actor_env, : int(entity_counts[actor_env])]
        right = entities_host[both_env, : int(entity_counts[both_env])]
        if not np.array_equal(left, right):
            mismatches.append({"actor": actor, "error": "GPU entities distinguish native-identical looking"})

    result = {
        "status": "PASS" if not mismatches else "FAIL",
        "cases": ENV_COUNT,
        "projection_status": [int(value) for value in status],
        "entity_counts": [int(value) for value in entity_counts],
        "option_counts": [int(value) for value in option_counts],
        "mismatches": mismatches,
    }
    print(json.dumps(result, sort_keys=True))
    if mismatches:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
