"""Bounded native counterfactual label collector.

The normal entry point is still a read-only schedule check.  The only native
execution mode previously authorized in this milestone is
``--preflight-complete-root``: one fresh worker finds one live root and evaluates
every legal single-select root action with two shared particles.  The scaled
64-root schedule is declaration-only and remains unauthorized.  Compound and
optional-STOP roots remain an explicit later mechanics gate.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import os
import select
import signal
import subprocess
import sys
import time
import importlib.util
import uuid
from datetime import datetime, timezone
from dataclasses import fields, is_dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG = Path(__file__).resolve().parent / "gate1_schedule_v1.json"
DEFAULT_FIXTURE = Path(__file__).resolve().parent / "probe.json"
OUT = Path(__file__).resolve().parent / "gate1-dry-run.json"
PREFLIGHT_OUT = Path(__file__).resolve().parent / "gate1-preflight-execution.json"
DATASET_SCHEMA = ROOT / ".chatgpt/tmp/outcome-ranker/counterfactual_action_dataset_v1.schema.json"
OPPONENT_LABEL_SCHEMA = ROOT / ".chatgpt/tmp/outcome-ranker/opponent_transition_label_v1.schema.json"
PROJECTOR = ROOT / ".chatgpt/tmp/outcome-ranker/project_public_state.py"
SAMPLE = ROOT / "private/assets/official/sample_submission/sample_submission"
SEMANTIC_HAND_ZONE = 2
MAX_WORKER_STEPS = 20_000
MAX_WORKER_SECONDS = 180.0
MAX_CHILD_STEPS = 20_000
MAX_CHILD_SECONDS = 120.0
PREFLIGHT_ACTIONS = 2
PREFLIGHT_PARTICLES = 2
COMPLETE_ROOT_PARTICLES = 2
MAX_COMPLETE_ROOT_BRANCHES = 20
MAX_IPC_BYTES = 256 * 1024
MAX_DIAGNOSTIC_BYTES = 4_000
SCALE64_PROFILE = "GATE1_SCALE64_V1"
SCALE256_PROFILE = "GATE1_SCALE256_V1"
OPPONENT_TRANSITION_PROFILE = "GATE1_SCALE64_OPPONENT_TRANSITION_V1"
SCALE64_ANCHOR_ALLOCATION = {
    "dragapult-ex": 11,
    "iono": 11,
    "mega-lucario-ex": 11,
    "public-alakazam-v9": 11,
    "public-lopunny-v9-arena-alias": 10,
    "grim-source-mirror": 10,
}
SCALE256_ANCHOR_ALLOCATION = {
    "dragapult-ex": 43,
    "iono": 43,
    "mega-lucario-ex": 43,
    "public-alakazam-v9": 43,
    "public-lopunny-v9-arena-alias": 42,
    "grim-source-mirror": 42,
}
SCALE64_CANDIDATE_WINDOWS = {
    "EARLY": (2, 3),
    "MID": (4, 6),
}
BC_TRUNK_PATH = ROOT / ".chatgpt/tmp/e01-bc-candidates-dataset/epoch-4.pt"
BC_TRUNK_CHECKPOINT_SHA256 = "76478ade97742697cc36aab311373b254ff186c787d772ab39d97cfb27ffafde"
BC_TRUNK_STATE_SHA256 = "b1efa5a137ce51347694daa41417efe080e19c4d6fad3f9bd48ebe268c6e2e1f"
BC_TRUNK_OPTIMIZER_STEPS = 840
TRUNK_MODE = "FROZEN_BC_EPOCH4_HEAD_ONLY"


class ScheduleError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_value(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _git_dirty_sha256() -> str:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=ROOT, check=True, capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ScheduleError(f"cannot capture Git dirty-state digest: {error}") from error
    return sha256_value(result.stdout)


def _new_run_id() -> str:
    return f"counterfactual-q-{datetime.now(timezone.utc):%Y%m%dT%H%M%S.%fZ}-{uuid.uuid4().hex[:12]}"


def _process_group_exists(pid: int) -> bool:
    proc_root = Path("/proc")
    if proc_root.is_dir():
        try:
            for entry in os.scandir(proc_root):
                if not entry.name.isdigit():
                    continue
                try:
                    stat = Path(entry.path, "stat").read_text(encoding="ascii")
                    tail = stat.rsplit(")", 1)[1].split()
                    state = tail[0]
                    process_group = int(tail[2])
                except (OSError, ValueError, IndexError):
                    continue
                if process_group == pid and state not in {"Z", "X"}:
                    return True
            return False
        except OSError:
            pass
    try:
        os.killpg(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _terminate_process_group(pid: int) -> dict[str, Any]:
    """Stop a worker/fork group and truthfully verify that it disappeared."""
    result = {
        "term_sent": False,
        "kill_sent": False,
        "group_gone": False,
        "verification_basis": "NO_LIVE_PROCESS_GROUP_MEMBERS",
        "verification_seconds": 0.0,
    }
    started = time.monotonic()
    try:
        os.killpg(pid, signal.SIGTERM)
        result["term_sent"] = True
    except ProcessLookupError:
        result["group_gone"] = True
        result["verification_seconds"] = time.monotonic() - started
        return result
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if not _process_group_exists(pid):
            result["group_gone"] = True
            result["verification_seconds"] = time.monotonic() - started
            return result
        time.sleep(0.05)
    try:
        os.killpg(pid, signal.SIGKILL)
        result["kill_sent"] = True
    except ProcessLookupError:
        result["group_gone"] = True
        result["verification_seconds"] = time.monotonic() - started
        return result
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if not _process_group_exists(pid):
            result["group_gone"] = True
            result["verification_seconds"] = time.monotonic() - started
            return result
        time.sleep(0.05)
    result["verification_seconds"] = time.monotonic() - started
    return result


def _validate_worker_binding(
    report: dict[str, Any], run_id: str, root_id: str,
    config_sha256: str, git_dirty_sha256: str,
) -> None:
    expected_binding = {
        "run_id": run_id,
        "root_id": root_id,
        "config_sha256": config_sha256,
        "git_dirty_sha256": git_dirty_sha256,
    }
    mismatches = [
        f"{field}={report.get(field)!r} != {expected!r}"
        for field, expected in expected_binding.items()
        if report.get(field) != expected
    ]
    if mismatches:
        raise ScheduleError("worker output binding mismatch: " + ";".join(mismatches))


def _bounded_communicate(process: subprocess.Popen[bytes], timeout: float) -> tuple[str, str]:
    """Drain worker pipes without allowing unbounded diagnostic buffering."""
    streams = {stream: name for stream, name in (
        (process.stdout, "stdout"), (process.stderr, "stderr")
    ) if stream is not None}
    selector = select.epoll() if hasattr(select, "epoll") else None
    if selector is None:
        raise ScheduleError("bounded worker IPC requires epoll")
    retained = {"stdout": bytearray(), "stderr": bytearray()}
    try:
        for stream in streams:
            selector.register(stream.fileno(), select.EPOLLIN | select.EPOLLHUP | select.EPOLLERR)
        deadline = time.monotonic() + timeout
        while streams:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(process.args, timeout)
            for fd, _events in selector.poll(min(remaining, 0.25)):
                stream = next((item for item in streams if item.fileno() == fd), None)
                if stream is None:
                    continue
                chunk = os.read(fd, MAX_IPC_BYTES)
                if not chunk:
                    selector.unregister(fd)
                    streams.pop(stream, None)
                    continue
                name = streams[stream]
                remaining_capacity = MAX_DIAGNOSTIC_BYTES - len(retained[name])
                if remaining_capacity > 0:
                    retained[name].extend(chunk[:remaining_capacity])
            if process.poll() is not None and not streams:
                break
        process.wait(timeout=max(0.1, deadline - time.monotonic()))
    finally:
        selector.close()
        for stream in streams:
            stream.close()
    return tuple(bytes(retained[name]).decode("utf-8", errors="replace") for name in ("stdout", "stderr"))


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_repo_path(value: str) -> Path:
    path = (ROOT / value).resolve()
    if path != ROOT and ROOT not in path.parents:
        raise ScheduleError(f"path escapes repository: {value}")
    return path


def check_hash(relative_path: str, expected: str) -> dict[str, Any]:
    path = resolve_repo_path(relative_path)
    if not path.is_file():
        raise ScheduleError(f"missing asset: {relative_path}")
    actual = sha256_file(path)
    if actual != expected:
        raise ScheduleError(f"SHA-256 mismatch for {relative_path}: {actual} != {expected}")
    return {"path": relative_path, "bytes": path.stat().st_size, "sha256": actual}


def legal_action_count(option_count: int, minimum: int, maximum: int) -> int:
    if not 0 <= minimum <= maximum <= option_count:
        raise ScheduleError("invalid selection bounds")
    return sum(
        len(list(itertools.permutations(range(option_count), count)))
        for count in range(minimum, maximum + 1)
    )


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ScheduleError(f"{name} must be a positive integer")
    return value


def _assignment_plan(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand the declared root cells without creating correlated roots.

    Scale64 uses one fresh worker/native start per assignment.  The candidate
    window only changes which first qualifying decision is accepted; it never
    asks for an nth candidate from one game.
    """
    schedule = config["state_schedule"]
    slots = schedule["candidate_player_slots"]
    slot_policy = schedule.get("learner_slot_policy", "GLOBAL_ALTERNATING")
    assignments: list[dict[str, Any]] = []
    for cell in schedule["anchor_cells"]:
        anchor_id = cell["anchor"]
        anchor_state_index = 0
        windows = cell.get("candidate_windows")
        if windows is None:
            windows = [{"name": None, "states": cell["states"], "min_turn": 2, "max_turn": None}]
        for window in windows:
            for window_state_index in range(window["states"]):
                state_index = len(assignments)
                if slot_policy == "ALTERNATING_PER_ANCHOR":
                    learner_slot = slots[anchor_state_index % len(slots)]
                else:
                    learner_slot = slots[state_index % len(slots)]
                assignments.append({
                    "state_index": state_index,
                    "anchor_id": anchor_id,
                    "anchor_state_index": anchor_state_index,
                    "window_name": window.get("name"),
                    "turn_min": window.get("min_turn", 2),
                    "turn_max": window.get("max_turn"),
                    "window_state_index": window_state_index,
                    "learner_slot": learner_slot,
                })
                anchor_state_index += 1
    return assignments


def _assignment_for_state(config: dict[str, Any], state_index: int) -> dict[str, Any]:
    assignments = _assignment_plan(config)
    if isinstance(state_index, bool) or not isinstance(state_index, int) or not 0 <= state_index < len(assignments):
        raise ScheduleError(f"state_index is outside the declared assignment plan: {state_index}")
    return assignments[state_index]


def validate_probe_fixture(path: Path, cap: int) -> dict[str, Any]:
    if not path.is_file():
        return {"status": "SKIP", "reason": "prior native proof fixture absent"}
    report = load_json(path)
    if report.get("status") != "PASS_COMPLETE":
        raise ScheduleError("prior native proof fixture is not PASS_COMPLETE")
    state = report.get("generated_state")
    if not isinstance(state, dict):
        raise ScheduleError("prior proof has no generated_state")
    records = state.get("action_records")
    legal_count = state.get("complete_legal_action_count")
    if not isinstance(records, list) or not isinstance(legal_count, int):
        raise ScheduleError("prior proof lacks action records/count")
    if legal_count != len(records) or [item.get("action_index") for item in records] != list(
        range(legal_count)
    ):
        raise ScheduleError("prior proof action enumeration is incomplete or duplicated")
    snapshot = state.get("public_feature_snapshot")
    if not isinstance(snapshot, dict) or snapshot.get("search_begin_input") is not None:
        raise ScheduleError("public snapshot retains opaque private search input")
    forbidden = {
        "your_deck", "your_prize", "opponent_deck", "opponent_prize", "opponent_hand",
        "opponent_active", "determinization_arrays",
    }
    found: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            found.update(set(value) & forbidden)
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(snapshot)
    if found:
        raise ScheduleError(f"public snapshot contains label-only fields: {sorted(found)}")
    rollout_count = int(report.get("counters", {}).get("total_continuation_rollouts", 0))
    if rollout_count > cap:
        raise ScheduleError("prior proof exceeds configured continuation cap")
    return {
        "status": "PASS",
        "path": str(path.relative_to(ROOT)),
        "sha256": sha256_file(path),
        "legal_action_count": legal_count,
        "enumerated_action_count": len(records),
        "public_private_boundary": "PASS",
        "continuation_rollouts": rollout_count,
        "native_launches_this_check": 0,
    }


def validate_schedule(config: dict[str, Any], fixture: Path) -> dict[str, Any]:
    if config.get("schema_version") != 1:
        raise ScheduleError("unsupported schedule schema")
    authorized = config.get("authorized")
    mode = config.get("mode")
    if not isinstance(authorized, bool):
        raise ScheduleError("authorized must be a boolean")
    expected_mode = "NATIVE_FULL_AUTHORIZED" if authorized else "DRY_RUN_ONLY"
    if mode != expected_mode:
        raise ScheduleError(f"authorized={authorized} requires mode={expected_mode}")
    source_commit = config.get("source_commit")
    current_commit = _canonical_source_commit()
    if not isinstance(source_commit, str) or source_commit != current_commit:
        raise ScheduleError(f"schedule source_commit differs from current HEAD: {source_commit} != {current_commit}")
    if config.get("label_firewall") != "COUNTERFACTUAL_NATIVE_ONLY_NOT_PPO_ROLLOUT":
        raise ScheduleError("label firewall is missing or changed")
    schema = config["dataset_schema"]
    check_hash(schema["path"], schema["sha256"])
    dataset_schema = load_json(resolve_repo_path(schema["path"]))
    for field in ("schema_version", "run", "state_groups"):
        if field not in dataset_schema.get("required", []):
            raise ScheduleError(f"dataset schema missing required top-level field: {field}")
    for asset in (
        config["assets"]["engine"],
        config["assets"]["card_data"],
        config["assets"]["action_observation_contract"],
        config["assets"]["g2_checkpoint"],
    ):
        check_hash(asset["path"], asset["sha256"])
    anchors = config.get("frozen_anchor_policies")
    if not isinstance(anchors, list) or not anchors:
        raise ScheduleError("frozen_anchor_policies must be a non-empty array")
    if any(not isinstance(anchor, dict) for anchor in anchors):
        raise ScheduleError("each frozen anchor must be an object")
    anchor_ids = [anchor.get("baseline_id") for anchor in anchors]
    if any(not isinstance(anchor_id, str) or not anchor_id for anchor_id in anchor_ids):
        raise ScheduleError("each frozen anchor must have a baseline_id")
    if len(set(anchor_ids)) != len(anchor_ids):
        raise ScheduleError("frozen anchor baseline IDs must be unique")
    policy = config["learner_policy"]
    receipt = resolve_repo_path(policy["directory"]) / "receipt.json"
    if sha256_file(receipt) != policy["receipt_sha256"]:
        raise ScheduleError("qualified Grim receipt hash differs")
    learner_receipt = load_json(receipt)
    if (
        learner_receipt.get("policy_id") != policy["policy_id"]
        or learner_receipt.get("baseline_id") != policy["policy_id"]
    ):
        raise ScheduleError("qualified Grim receipt policy_id differs from configured learner policy")
    learner_deck = resolve_repo_path(policy["directory"]) / "deck.csv"
    learner_module = resolve_repo_path(policy["directory"]) / "main.py"
    if sha256_file(learner_deck) != policy["deck_sha256"]:
        raise ScheduleError("qualified Grim deck hash differs")
    if learner_receipt.get("deck", {}).get("sha256") != policy["deck_sha256"]:
        raise ScheduleError("qualified Grim receipt deck hash differs")
    if learner_receipt.get("module", {}).get("sha256") != sha256_file(learner_module):
        raise ScheduleError("qualified Grim receipt module hash differs")
    for anchor in anchors:
        receipt_path = resolve_repo_path(anchor["directory"]) / "receipt.json"
        if sha256_file(receipt_path) != anchor["receipt_sha256"]:
            raise ScheduleError(f"anchor receipt hash differs: {anchor['baseline_id']}")
        receipt_value = load_json(receipt_path)
        if (
            receipt_value.get("policy_id") != anchor["policy_id"]
            or receipt_value.get("baseline_id") != anchor["baseline_id"]
        ):
            raise ScheduleError(f"anchor policy identity differs: {anchor['baseline_id']}")
        deck_path = receipt_path.parent / "deck.csv"
        module_path = receipt_path.parent / "main.py"
        if sha256_file(deck_path) != anchor["deck_sha256"]:
            raise ScheduleError(f"anchor deck hash differs: {anchor['baseline_id']}")
        if receipt_value.get("deck", {}).get("sha256") != anchor["deck_sha256"]:
            raise ScheduleError(f"anchor receipt deck hash differs: {anchor['baseline_id']}")
        if receipt_value.get("module", {}).get("sha256") != sha256_file(module_path):
            raise ScheduleError(f"anchor receipt module hash differs: {anchor['baseline_id']}")
    state_schedule = config.get("state_schedule")
    if not isinstance(state_schedule, dict):
        raise ScheduleError("state_schedule must be an object")
    profile = state_schedule.get("profile", "GATE1_V1")
    if profile not in {"GATE1_V1", SCALE64_PROFILE, SCALE256_PROFILE, OPPONENT_TRANSITION_PROFILE}:
        raise ScheduleError(f"unsupported state schedule profile: {profile}")
    if state_schedule.get("selection_type_required") != "MAIN":
        raise ScheduleError("Gate-1 root selection_type_required must be MAIN")
    selection_context = state_schedule.get("selection_context_required")
    if isinstance(selection_context, bool) or not isinstance(selection_context, int) or selection_context != 0:
        raise ScheduleError("Gate-1 selection_context_required must be integer 0 (MAIN)")

    states = _positive_int(state_schedule.get("root_state_count"), "root_state_count")
    replicas = _positive_int(state_schedule.get("replicates_per_action"), "replicates_per_action")
    max_actions = _positive_int(
        state_schedule.get("max_legal_actions_per_state"), "max_legal_actions_per_state"
    )
    cap = _positive_int(state_schedule.get("max_continuation_rollouts"), "max_continuation_rollouts")
    max_root_attempts = _positive_int(
        state_schedule.get("max_root_acquisition_attempts", 1), "max_root_acquisition_attempts"
    )
    slots = state_schedule.get("candidate_player_slots")
    if (
        not isinstance(slots, list)
        or len(slots) != 2
        or any(isinstance(slot, bool) or not isinstance(slot, int) for slot in slots)
        or sorted(slots) != [0, 1]
    ):
        raise ScheduleError("candidate_player_slots must contain exactly slots 0 and 1")
    hidden_worlds = config.get("hidden_worlds")
    if not isinstance(hidden_worlds, dict):
        raise ScheduleError("hidden_worlds must be an object")
    particles = _positive_int(hidden_worlds.get("seeds_per_state"), "seeds_per_state")
    if replicas > 8 or particles > 8:
        raise ScheduleError("root/particle bounds exceed the <=8 bound")
    if max_actions < 2 or max_actions > 10:
        raise ScheduleError("max_legal_actions_per_state must be in [2, 10]")
    if replicas != particles:
        raise ScheduleError("replicates_per_action must equal seeds_per_state particles")
    if not state_schedule.get("common_determinization_set_across_root_actions"):
        raise ScheduleError("common hidden particles are required for action comparison")
    anchor_cells = state_schedule.get("anchor_cells")
    expected_anchor_ids = set(anchor_ids)
    scaled_profile = profile in {SCALE64_PROFILE, SCALE256_PROFILE, OPPONENT_TRANSITION_PROFILE}
    expected_cell_count = 6 if scaled_profile else 3
    if not isinstance(anchor_cells, list) or len(anchor_cells) != expected_cell_count:
        raise ScheduleError(f"state_schedule must contain exactly {expected_cell_count} anchor cells")
    cell_ids: list[str] = []
    cell_states = 0
    for cell in anchor_cells:
        if not isinstance(cell, dict) or not isinstance(cell.get("anchor"), str):
            raise ScheduleError("each anchor cell must name an anchor")
        if cell["anchor"] in cell_ids or cell["anchor"] not in expected_anchor_ids:
            raise ScheduleError("anchor cells must be a unique split of the frozen anchors")
        cell_ids.append(cell["anchor"])
        cell_state_count = _positive_int(cell.get("states"), f"states_per_anchor:{cell['anchor']}")
        cell_states += cell_state_count
        windows = cell.get("candidate_windows")
        if scaled_profile:
            if state_schedule.get("root_state_source") != "independent_native_start_and_walk_with_fixed_pair":
                raise ScheduleError("scale64 roots must use independent native starts")
            if state_schedule.get("root_selection_policy") != "FIRST_QUALIFYING_IN_DECLARED_TURN_WINDOW":
                raise ScheduleError("scale64 roots must select the first qualifying state in a declared turn window")
            if not isinstance(windows, list) or {item.get("name") for item in windows} != set(SCALE64_CANDIDATE_WINDOWS):
                raise ScheduleError("scale64 anchor cells must split roots into EARLY and MID windows")
            window_states = 0
            for window in windows:
                if not isinstance(window, dict) or window.get("name") not in SCALE64_CANDIDATE_WINDOWS:
                    raise ScheduleError("scale64 candidate window is invalid")
                window_state_count = _positive_int(
                    window.get("states"), f"candidate_window_states:{cell['anchor']}:{window.get('name')}"
                )
                expected_turns = SCALE64_CANDIDATE_WINDOWS[window["name"]]
                if (window.get("min_turn"), window.get("max_turn")) != expected_turns:
                    raise ScheduleError("scale64 candidate turn windows differ from the declared early/mid split")
                window_states += window_state_count
            if window_states != cell_state_count:
                raise ScheduleError(f"candidate windows do not cover {cell['anchor']} state count")
    if set(cell_ids) != expected_anchor_ids or cell_states != states:
        raise ScheduleError("anchor-cell states must positively split root_state_count across all anchors")
    if profile in {SCALE64_PROFILE, SCALE256_PROFILE, OPPONENT_TRANSITION_PROFILE}:
        expected_states = 256 if profile == SCALE256_PROFILE else 64
        expected_cap = 10240 if profile == SCALE256_PROFILE else 2560
        expected_wall = 1800 if profile == SCALE256_PROFILE else 600
        expected_allocation = (
            SCALE256_ANCHOR_ALLOCATION if profile == SCALE256_PROFILE else SCALE64_ANCHOR_ALLOCATION
        )
        profile_name = "scale256" if profile == SCALE256_PROFILE else "scale64"
        if states != expected_states or replicas != 4 or particles != 4 or max_actions != 10 or cap != expected_cap:
            raise ScheduleError(
                f"{profile_name} requires exactly {expected_states} roots, 4 particles, "
                f"max 10 actions, and cap {expected_cap}"
            )
        if [cell["states"] for cell in anchor_cells] != list(expected_allocation.values()):
            raise ScheduleError(f"{profile_name} anchor allocation differs from the declared order")
        if state_schedule.get("learner_slot_policy") != "ALTERNATING_PER_ANCHOR":
            raise ScheduleError(f"{profile_name} learner slots must alternate independently within each anchor family")
        if state_schedule.get("max_wall_seconds") != expected_wall:
            raise ScheduleError(f"{profile_name} wall cap must be exactly {expected_wall} seconds")
        if profile in {SCALE256_PROFILE, OPPONENT_TRANSITION_PROFILE} and max_root_attempts != 8:
            raise ScheduleError("this profile root acquisition retry cap must be exactly 8")
        if profile == OPPONENT_TRANSITION_PROFILE and (
            authorized is not False or mode != "DRY_RUN_ONLY"
        ):
            raise ScheduleError("opponent-transition ceiling is declaration-only; native full mode is refused")
        if state_schedule.get("root_game_seed_policy") != (
            "INDEPENDENT_ROOT_LABELS_NATIVE_START_SYSTEM_ENTROPY_UNSEEDED"
        ):
            raise ScheduleError(f"{profile_name} root seed policy must disclose native start entropy")
        if hidden_worlds.get("seed_policy") != "UNIQUE_ROOT_ID_PARTICLE_SEEDS":
            raise ScheduleError(f"{profile_name} particle seed policy must be unique per root and particle")
        bc_binding = config.get("bc_binding")
        if not isinstance(bc_binding, dict):
            raise ScheduleError(f"{profile_name} must declare the pinned BC trunk binding")
        if (
            bc_binding.get("path") != str(BC_TRUNK_PATH.relative_to(ROOT))
            or bc_binding.get("checkpoint_sha256") != BC_TRUNK_CHECKPOINT_SHA256
            or bc_binding.get("state_sha256") != BC_TRUNK_STATE_SHA256
            or bc_binding.get("optimizer_steps") != BC_TRUNK_OPTIMIZER_STEPS
            or bc_binding.get("mode") != TRUNK_MODE
        ):
            raise ScheduleError(f"{profile_name} BC trunk binding differs from the pinned epoch-4 receipt")
        check_hash(bc_binding["path"], bc_binding["checkpoint_sha256"])
        if profile == OPPONENT_TRANSITION_PROFILE:
            projector_binding = config.get("assets", {}).get("public_projector")
            if (
                not isinstance(projector_binding, dict)
                or projector_binding.get("path") != str(PROJECTOR.relative_to(ROOT))
                or not isinstance(projector_binding.get("sha256"), str)
            ):
                raise ScheduleError("opponent-transition profile must bind the public G2 projector")
            check_hash(projector_binding["path"], projector_binding["sha256"])
            label_schema = config.get("opponent_transition_label_schema")
            if not isinstance(label_schema, dict):
                raise ScheduleError("opponent-transition profile must bind its restricted label schema")
            check_hash(label_schema["path"], label_schema["sha256"])
            label_schema_value = load_json(resolve_repo_path(label_schema["path"]))
            if label_schema_value.get("title") != "Restricted first opponent transition labels v1":
                raise ScheduleError("restricted label schema title is not bound")
    else:
        if states > 8:
            raise ScheduleError("Gate-1 root bound exceeds the <=8 bound")
        if cap > 480 or states * max_actions * particles > cap:
            raise ScheduleError("Gate-1 continuation cap exceeds the <=480 preflight/full bound")
    if states * max_actions * particles > cap:
        raise ScheduleError("continuation cap is below the declared worst-case root/action/particle bound")
    boundary = config["public_private_boundary"]
    if not boundary.get("label_metadata_only") or not boundary.get("forbidden_in_public_tensor"):
        raise ScheduleError("public/private boundary is incomplete")
    assignments = _assignment_plan(config)
    if len(assignments) != states:
        raise ScheduleError("expanded root assignment plan does not match root_state_count")
    if scaled_profile:
        for anchor_id in expected_anchor_ids:
            family_slots = [item["learner_slot"] for item in assignments if item["anchor_id"] == anchor_id]
            if set(family_slots) != {0, 1} or abs(family_slots.count(0) - family_slots.count(1)) > 1:
                raise ScheduleError(f"scale64 learner slots are not balanced for {anchor_id}")
    return {
        "status": "PASS",
        "authorized": authorized,
        "mode": mode,
        "profile": profile,
        "native_launches": 0,
        "policy_loader": "ptcg_rl.g1.rule_baseline.NativeRulePolicy",
        "continuation_native_api": "cg.api.search_begin/search_step/search_end",
        "anchor_ids": [anchor["baseline_id"] for anchor in anchors],
        "root_states": states,
        "replicates_per_action": replicas,
        "particles_per_state": particles,
        "max_actions_per_state": max_actions,
        "selection_type_required": "MAIN",
        "selection_context_required": selection_context,
        "max_continuation_rollouts": cap,
        "max_root_acquisition_attempts": max_root_attempts,
        "max_wall_seconds": state_schedule.get("max_wall_seconds", MAX_WORKER_SECONDS),
        "assignment_plan": assignments,
        "fixture": validate_probe_fixture(fixture, cap),
        "public_private_boundary": "PASS",
        "opponent_transition_label_schema": (
            config.get("opponent_transition_label_schema")
            if profile == OPPONENT_TRANSITION_PROFILE else None
        ),
        "public_projector": (
            config.get("assets", {}).get("public_projector")
            if profile == OPPONENT_TRANSITION_PROFILE else None
        ),
        "no_native_continuations_run": True,
    }


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {field.name: _jsonable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "value") and isinstance(value.value, int):
        return int(value.value)
    return value


def _option_record(option: Any) -> dict[str, Any]:
    return {
        "option_type": int(option.option_type),
        "source_kind": option.source_kind,
        "target_kind": option.target_kind,
        "choice_role": option.choice_role,
        "source_ref": option.source_ref,
        "target_ref": option.target_ref,
        "is_stop": False,
        "source_card_id": option.card_id if option.source_kind == "ENTITY" else None,
        "target_card_id": option.card_id if option.target_kind == "ENTITY" else None,
        "attack_id": option.attack_id,
        "semantic_fingerprint": option.semantic_fingerprint,
    }


def _request_record(request: Any) -> dict[str, Any]:
    return {
        "request_id": request.request_id,
        "selection_seq": int(request.selection_seq),
        "selection_type": int(request.selection_type),
        "selection_context": int(request.selection_context),
        "min_count": int(request.min_count),
        "max_count": int(request.max_count),
        "ordering": request.ordering,
        "options": [_option_record(option) for option in request.options],
    }


def _entity_by_key(observation: Any) -> dict[str, Any]:
    return {
        entity.entity_key: entity
        for entity in getattr(observation, "entities", ())
        if getattr(entity, "entity_key", None)
    }


def _opponent_endpoint_key(
    entity: Any | None,
    *,
    path_role: str,
    learner_slot: int,
    entities: dict[str, Any],
    seen: set[str] | None = None,
) -> dict[str, Any] | None:
    if entity is None:
        return None
    entity_key = getattr(entity, "entity_key", None)
    if not isinstance(entity_key, str):
        raise ScheduleError("opponent semantic endpoint has no entity key")
    seen = set() if seen is None else seen
    if entity_key in seen:
        raise ScheduleError("opponent semantic endpoint parent path contains a cycle")
    seen.add(entity_key)
    # Hand copies deliberately pool across transport serials and positions.
    if int(entity.zone) == SEMANTIC_HAND_ZONE:
        if entity.card_id is None:
            raise ScheduleError("visible opponent hand option has no factual card_id")
        return {
            "visibility": "HIDDEN_HAND_COPY_POOL",
            "owner_role": "LEARNER" if int(entity.owner) == learner_slot else "OPPONENT",
            "zone": int(entity.zone),
            "card_id": entity.card_id,
            "path_role": path_role,
        }
    parent = entities.get(entity.parent_entity_key) if entity.parent_entity_key else None
    return {
        "visibility": "PUBLIC_ENDPOINT",
        "owner_role": "LEARNER" if int(entity.owner) == learner_slot else "OPPONENT",
        "zone": int(entity.zone),
        "position": entity.position,
        "card_id": entity.card_id,
        "path_role": path_role,
        "parent_path": _opponent_endpoint_key(
            parent,
            path_role="PARENT",
            learner_slot=learner_slot,
            entities=entities,
            seen=seen,
        ) if parent is not None else None,
    }


def _opponent_semantic_equivalence_key(
    request: Any,
    option: Any,
    observation: Any,
    learner_slot: int,
) -> str:
    entities = _entity_by_key(observation)
    source = entities.get(getattr(option, "source_entity_key", None))
    target = entities.get(getattr(option, "target_entity_key", None))
    if getattr(option, "source_kind", "NONE") == "ENTITY" and source is None:
        raise ScheduleError("opponent semantic source endpoint is unresolved")
    if getattr(option, "target_kind", "NONE") == "ENTITY" and target is None:
        raise ScheduleError("opponent semantic target endpoint is unresolved")
    material = {
        "request": {
            "selection_type": int(request.selection_type),
            "selection_context": int(request.selection_context),
            "min_count": int(request.min_count),
            "max_count": int(request.max_count),
            "ordering": request.ordering,
        },
        "option": {
            "option_type": int(option.option_type),
            "choice_role": option.choice_role,
            "number": option.number,
            "count": option.count,
            "attack_id": option.attack_id,
            "special_condition_type": option.special_condition_type,
            "source": _opponent_endpoint_key(
                source, path_role="SOURCE", learner_slot=learner_slot, entities=entities,
            ),
            "target": _opponent_endpoint_key(
                target, path_role="TARGET", learner_slot=learner_slot, entities=entities,
            ),
            "source_kind": option.source_kind,
            "target_kind": option.target_kind,
            "is_stop": False,
        },
    }
    return sha256_value(material)


def _opponent_option_record(
    request: Any, option: Any, observation: Any, learner_slot: int,
) -> dict[str, Any]:
    value = _option_record(option)
    value["original_index"] = int(option.original_index)
    value["semantic_equivalence_key"] = _opponent_semantic_equivalence_key(
        request, option, observation, learner_slot,
    )
    return value


def _opponent_request_record(request: Any, observation: Any, learner_slot: int) -> dict[str, Any]:
    value = _request_record(request)
    value["option_count"] = len(request.options)
    value["options"] = [
        _opponent_option_record(request, option, observation, learner_slot)
        for option in request.options
    ]
    return value


def _public_tensor_from_projection(projection: dict[str, Any], model_schema_sha256: str) -> dict[str, Any]:
    if projection.get("status") != "OK":
        blockers = projection.get("blockers", ["unknown public projection blocker"])
        raise ScheduleError("G2 public projection blocked: " + ";".join(str(item) for item in blockers))
    public_state = projection.get("public_state")
    if not isinstance(public_state, dict):
        raise ScheduleError("G2 public projector returned no public_state")
    history = public_state.get("history_inputs")
    recurrent_prefix = projection.get("recurrent_prefix")
    if not isinstance(history, dict) or not isinstance(recurrent_prefix, dict):
        raise ScheduleError("G2 public projector returned no recorded history")
    public_hidden = history.get("public_hidden")
    if not isinstance(public_hidden, dict) or public_hidden.get("shape") != [1, 160]:
        raise ScheduleError("G2 public projector returned an invalid public hidden shape")
    prefix_digest = sha256_value(recurrent_prefix.get("prefix_digest_chain", []))
    history_source = history.get("history_source")
    history_steps = history.get("history_steps")
    initial_hidden_source = recurrent_prefix.get("initial_hidden_source")
    if not isinstance(history_source, str) or not isinstance(history_steps, int):
        raise ScheduleError("G2 public projector returned incomplete history metadata")
    if not isinstance(initial_hidden_source, str):
        raise ScheduleError("G2 public projector returned no initial hidden provenance")
    history_token = {
        "history_schema_version": 1,
        "history_source": history_source,
        "history_steps": history_steps,
        "prefix_digest": prefix_digest,
        "model_schema_sha256": model_schema_sha256,
        "public_hidden": public_hidden,
    }
    prefix_provenance = {
        "source": "ACTOR_OWNED_PUBLIC_PREFIX",
        "prefix_digest": prefix_digest,
        "history_schema_version": 1,
        "history_source": history_source,
        "history_steps": history_steps,
        "initial_hidden_source": initial_hidden_source,
        "model_schema_sha256": model_schema_sha256,
        "full_public_prefix_retained": False,
    }
    return {
        "schema_version": 1,
        "model_schema_sha256": model_schema_sha256,
        "feature_source": "G2_PROJECTED_PUBLIC_ONLY",
        "projected_decision": public_state.get("projected_decision", {}),
        "history_tokens": [history_token],
        "public_only": True,
        "raw_observation_retained": False,
        "forbidden_actor_features_absent": True,
        "prefix_provenance": prefix_provenance,
    }


def _root_action_equivalence_keys(
    runtime: dict[str, Any],
    public_tensor: dict[str, Any],
    request: Any,
    actions: list[tuple[int, ...]],
) -> list[dict[str, str]]:
    projected = runtime["projected_decision"](public_tensor["projected_decision"])
    request_record = _request_record(request)
    options = request_record["options"]
    keys = []
    for action in actions:
        if len(action) != 1:
            raise ScheduleError("semantic equivalence keys require singleton root actions")
        index = int(action[0])
        keys.append({
            "action_id": _action_id(action, request),
            "semantic_equivalence_key": runtime["semantic_equivalence_key"](
                request_record, options, projected.model, index,
            ),
        })
    return keys


def _public_projection_binding(
    dataset: dict[str, Any], projector_binding: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(projector_binding, dict):
        raise ScheduleError("public projector binding is missing")
    projector_path = resolve_repo_path(str(projector_binding.get("path", "")))
    if not projector_path.is_file() or sha256_file(projector_path) != projector_binding.get("sha256"):
        raise ScheduleError("public projector binding does not match the loaded projector")
    groups = dataset.get("state_groups")
    if not isinstance(groups, list) or not groups:
        raise ScheduleError("dataset has no state groups for projection binding")
    bindings = []
    model_schema = None
    for group in groups:
        tensor = group.get("public_tensor")
        if not isinstance(tensor, dict) or not isinstance(tensor.get("projected_decision"), dict):
            raise ScheduleError("dataset group has no projected public decision")
        provenance = tensor.get("prefix_provenance")
        if not isinstance(provenance, dict) or not isinstance(provenance.get("prefix_digest"), str):
            raise ScheduleError("dataset group has no public history digest")
        history_tokens = tensor.get("history_tokens")
        if (
            not isinstance(history_tokens, list)
            or len(history_tokens) != 1
            or not isinstance(history_tokens[0], dict)
            or history_tokens[0].get("prefix_digest") != provenance["prefix_digest"]
        ):
            raise ScheduleError("dataset history token does not match public prefix provenance")
        current_schema = tensor.get("model_schema_sha256")
        if not isinstance(current_schema, str):
            raise ScheduleError("dataset group has no model schema binding")
        if model_schema is None:
            model_schema = current_schema
        elif model_schema != current_schema:
            raise ScheduleError("dataset groups use different public model schemas")
        bindings.append({
            "state_group_id": group.get("state_group_id"),
            "public_state_sha256": group.get("public_state_sha256"),
            "public_projection_sha256": sha256_value(tensor["projected_decision"]),
            "history_prefix_digest": provenance["prefix_digest"],
            "history_tokens_sha256": sha256_value(history_tokens),
        })
    if any(
        not isinstance(item["state_group_id"], str)
        or not isinstance(item["public_state_sha256"], str)
        or len(item["public_state_sha256"]) != 64
        for item in bindings
    ):
        raise ScheduleError("dataset projection binding contains malformed state identity")
    return {
        "projector_path": str(projector_path.relative_to(ROOT)),
        "projector_sha256": projector_binding["sha256"],
        "model_schema_sha256": model_schema,
        "groups": bindings,
    }


def _action_id(action: tuple[int, ...], request: Any) -> str:
    return sha256_value({
        "ordering": request.ordering,
        "semantic_path": [request.options[index].semantic_fingerprint for index in action],
    })


def _canonical_source_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown0000000"


def _runtime_imports() -> dict[str, Any]:
    sys.path.insert(0, str(SAMPLE))
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(ROOT / ".chatgpt/tmp"))
    from cg.api import search_begin, search_end, search_step, to_observation_class
    from cg.game import battle_finish, battle_select, battle_start
    from ptcg_rl.g1.rule_baseline import NativeRulePolicy
    from ptcg_rl.g1.semantic import semantic_snapshot
    from ptcg_rl.g2.checkpoint import state_dict_sha256
    from search_feasibility_canary import determinize
    projector_spec = importlib.util.spec_from_file_location(
        "counterfactual_public_projector",
        ROOT / ".chatgpt/tmp/outcome-ranker/project_public_state.py",
    )
    if projector_spec is None or projector_spec.loader is None:
        raise ScheduleError("public G2 projector cannot be loaded")
    projector_module = importlib.util.module_from_spec(projector_spec)
    sys.modules[projector_spec.name] = projector_module
    projector_spec.loader.exec_module(projector_module)
    ranker_spec = importlib.util.spec_from_file_location(
        "counterfactual_outcome_ranker",
        ROOT / ".chatgpt/tmp/outcome-ranker/outcome_ranker.py",
    )
    if ranker_spec is None or ranker_spec.loader is None:
        raise ScheduleError("Gate-1 outcome-ranker loader cannot be loaded")
    ranker_module = importlib.util.module_from_spec(ranker_spec)
    sys.modules[ranker_spec.name] = ranker_module
    ranker_spec.loader.exec_module(ranker_module)

    return {
        "search_begin": search_begin,
        "search_end": search_end,
        "search_step": search_step,
        "to_observation_class": to_observation_class,
        "battle_finish": battle_finish,
        "battle_select": battle_select,
        "battle_start": battle_start,
        "NativeRulePolicy": NativeRulePolicy,
        "semantic_snapshot": semantic_snapshot,
        "determinize": determinize,
        "project_public_state": projector_module.project_public_state,
        "advance_public_recurrent_prefix": projector_module.advance_public_recurrent_prefix,
        "load_checkpoint_package": __import__(
            "ptcg_rl.g2.checkpoint", fromlist=["load_checkpoint_package"]
        ).load_checkpoint_package,
        "load_gate1_trunk": ranker_module.load_gate1_trunk,
        "projected_decision": ranker_module._projected_decision,
        "semantic_equivalence_key": ranker_module.semantic_equivalence_key,
        "state_dict_sha256": state_dict_sha256,
    }


def _candidate(
    obs: Any,
    learner_slot: int,
    selection_context: int,
    turn_min: int = 2,
    turn_max: int | None = None,
) -> bool:
    turn = int(obs.current.turn) if obs.current is not None else -1
    return bool(
        obs.current is not None
        and int(obs.current.result) == -1
        and int(obs.current.yourIndex) == learner_slot
        and turn >= turn_min
        and (turn_max is None or turn <= turn_max)
        and obs.select is not None
        and int(obs.select.type) == 0
        and int(obs.select.context) == selection_context
        and int(obs.select.minCount) == 1
        and int(obs.select.maxCount) == 1
        and 2 <= len(obs.select.option) <= 10
    )


def _validate_main_single_root(request: Any, selection_context: int) -> None:
    if (
        int(request.selection_type) != 0
        or int(request.selection_context) != selection_context
        or int(request.min_count) != 1
        or int(request.max_count) != 1
    ):
        raise ScheduleError("root request is not MAIN context 0 with exactly one required selection")


def _validate_gate1_trunk_binding(report: dict[str, Any]) -> None:
    hashes = report.get("hashes")
    expected = {
        "bc_trunk_checkpoint_sha256": BC_TRUNK_CHECKPOINT_SHA256,
        "bc_trunk_state_sha256": BC_TRUNK_STATE_SHA256,
        "bc_trunk_optimizer_steps": BC_TRUNK_OPTIMIZER_STEPS,
        "trunk_mode": TRUNK_MODE,
        "bc_trunk_frozen": True,
    }
    if not isinstance(hashes, dict) or any(hashes.get(key) != value for key, value in expected.items()):
        raise ScheduleError("worker did not prove the pinned frozen BC epoch-4 trunk binding")


def _complete_actions(obs: Any) -> list[tuple[int, ...]]:
    if obs.select is None:
        return []
    count = len(obs.select.option)
    minimum = int(obs.select.minCount)
    maximum = int(obs.select.maxCount)
    if count > 10:
        raise ScheduleError("root option set exceeds hard action cap; truncation is forbidden")
    return [
        action
        for size in range(minimum, maximum + 1)
        for action in itertools.permutations(range(count), size)
    ]


def _validate_action(request: Any, action: Any) -> tuple[int, ...]:
    values = tuple(int(value) for value in action.submitted_original_indices)
    if len(values) != len(set(values)):
        raise ScheduleError("compound action contains duplicate transport indices")
    legal = {int(option.original_index) for option in request.options if option.available}
    if not request.min_count <= len(values) <= request.max_count or not set(values) <= legal:
        raise ScheduleError("compound action violates native semantic request")
    return values


def _search_raw(observation: Any) -> dict[str, Any]:
    """Restore the official sparse raw shape from a SearchState dataclass.

    ``to_dataclass`` materializes every optional option field as ``None``;
    ``semantic_snapshot`` intentionally rejects those keys as impossible
    fields for the option type.  The official live JSON omits them, so only
    option-level nulls are removed.  Hidden cards and face-down slots retain
    their meaningful nulls.
    """
    raw = _jsonable(observation)
    select = raw.get("select")
    if isinstance(select, dict) and isinstance(select.get("option"), list):
        select["option"] = [
            {key: value for key, value in option.items() if value is not None}
            for option in select["option"]
        ]
    return raw


def _public_raw(raw: dict[str, Any]) -> dict[str, Any]:
    copied = json.loads(json.dumps(raw))
    copied["search_begin_input"] = None
    return copied


def _new_opponent_transition_label(learner_slot: int) -> dict[str, Any]:
    return {
        "status": "MISSING_OR_ERROR",
        "opponent_player": 1 - learner_slot,
        "first_opponent_request": None,
        "chosen_action": None,
        "error": {"type": "NotReached", "message": "first opponent request not reached yet"},
    }


def _semantic_action_record(
    request: Any, submitted: tuple[int, ...], observation: Any, learner_slot: int,
) -> dict[str, Any]:
    options = {int(option.original_index): option for option in request.options}
    if any(value not in options for value in submitted):
        raise ScheduleError("opponent action references an unknown semantic option")
    semantic_path = [
        _opponent_option_record(request, options[value], observation, learner_slot)
        for value in submitted
    ]
    semantic_keys = [item["semantic_equivalence_key"] for item in semantic_path]
    action_key = semantic_keys[0] if len(semantic_keys) == 1 else sha256_value({
        "ordering": request.ordering,
        "semantic_path": semantic_keys if request.ordering == "ORDERED" else sorted(semantic_keys),
    })
    return {
        "transport_original_indices": list(submitted),
        "semantic_path": semantic_path,
        "semantic_equivalence_key": action_key,
        "semantic_action_fingerprint": sha256_value(semantic_path),
    }


def _set_opponent_transition_error(label: dict[str, Any], error: Exception) -> None:
    label["status"] = "MISSING_OR_ERROR"
    label["error"] = {"type": type(error).__name__, "message": str(error)[:500]}


def _terminal_record(result: int) -> tuple[dict[str, Any], int]:
    if result not in (0, 1, 2):
        raise ScheduleError(f"continuation ended with nonterminal result {result}")
    return (
        {"winner_player": None if result == 2 else result, "is_draw": result == 2},
        0 if result == 2 else (1 if result == 0 else -1),
    )


def _child_continuation(
    write_fd: int,
    root_observation: Any,
    determinization: dict[str, list[int]],
    action: tuple[int, ...],
    action_id: str,
    learner_slot: int,
    policies: list[Any],
    runtime: dict[str, Any],
    card_data_sha256: str,
    deadline: float,
) -> None:
    record: dict[str, Any] = {
        "status": "RUNNING",
        "pid": os.getpid(),
        "action_id": action_id,
        "action": list(action),
        "invalid_actions": 0,
        "fallback_actions": 0,
        "post_terminal_actions": 0,
        "continuation_steps": 0,
        "first_opponent_response": None,
        "opponent_transition": _new_opponent_transition_label(learner_slot),
        "error": None,
    }
    search_end = runtime["search_end"]
    try:
        search_state = runtime["search_begin"](
            root_observation,
            determinization["your_deck"],
            determinization["your_prize"],
            determinization["opponent_deck"],
            determinization["opponent_prize"],
            determinization["opponent_hand"],
            determinization["opponent_active"],
            manual_coin=False,
        )
        search_state = runtime["search_step"](search_state.searchId, list(action))
        record["continuation_steps"] = 1
        while True:
            if time.monotonic() >= deadline:
                raise TimeoutError("counterfactual child wall-time cap reached")
            observation = search_state.observation
            current = observation.current
            if current is None:
                raise ScheduleError("search observation omitted current state")
            result = int(current.result)
            if result in (0, 1, 2):
                label = record["opponent_transition"]
                if label["status"] == "MISSING_OR_ERROR":
                    label["status"] = "TERMINAL_BEFORE_OPPONENT"
                    label["error"] = None
                terminal, reward = _terminal_record(result)
                record.update({
                    "status": "COMPLETE",
                    "terminal_engine_result": terminal,
                    "reward_for_actor": reward if learner_slot == 0 else -reward,
                })
                break
            if result != -1:
                raise ScheduleError(f"unknown search result {result}")
            if observation.select is None:
                raise ScheduleError("ongoing search observation omitted selection")
            if record["continuation_steps"] >= MAX_CHILD_STEPS:
                raise TimeoutError("counterfactual child step cap reached")
            raw = _search_raw(observation)
            semantic, request = runtime["semantic_snapshot"](
                raw,
                f"counterfactual-child-{os.getpid()}",
                int(record["continuation_steps"]),
                card_data_sha256,
            )
            if request is None or semantic.terminal_result is not None:
                raise ScheduleError("search semantic adapter did not return an ongoing request")
            acting_player = int(current.yourIndex)
            label = record["opponent_transition"]
            first_opponent = acting_player != learner_slot and label["status"] == "MISSING_OR_ERROR"
            if first_opponent:
                label["first_opponent_request"] = _opponent_request_record(
                    request, semantic, learner_slot,
                )
                record["first_opponent_response"] = {
                    "acting_player": acting_player,
                    "selection_type": int(request.selection_type),
                    "selection_context": int(request.selection_context),
                    "option_count": len(request.options),
                    "request_fingerprint": sha256_value(_request_record(request)),
                }
                if (
                    int(request.selection_type) != 0
                    or int(request.selection_context) != 0
                    or int(request.min_count) != 1
                    or int(request.max_count) != 1
                ):
                    label["status"] = "UNSUPPORTED_FIRST_OPPONENT_REQUEST"
                    label["error"] = None
            policy = policies[acting_player]
            chosen = policy.choose_native(raw, semantic, request)
            submitted = _validate_action(request, chosen)
            search_state = runtime["search_step"](search_state.searchId, list(submitted))
            record["continuation_steps"] += 1
            if first_opponent:
                if label["status"] == "MISSING_OR_ERROR":
                    label["status"] = "OBSERVED"
                    label["error"] = None
                    label["chosen_action"] = _semantic_action_record(
                        request, submitted, semantic, learner_slot,
                    )
    except (ValueError, IndexError) as error:
        _set_opponent_transition_error(record["opponent_transition"], error)
        record.update({
            "status": "INVALID",
            "invalid_actions": 1,
            "error": {"type": type(error).__name__, "message": str(error)[:500]},
        })
    except Exception as error:  # child errors must be visible, never a fallback
        _set_opponent_transition_error(record["opponent_transition"], error)
        record.update({
            "status": "ERROR",
            "error": {"type": type(error).__name__, "message": str(error)[:500]},
        })
    finally:
        try:
            search_end()
        except Exception as error:
            record["search_end_error"] = {
                "type": type(error).__name__, "message": str(error)[:500]
            }
            record["status"] = "ERROR"
            record["error"] = {
                "type": "SearchEndError",
                "message": str(error)[:500],
            }
        try:
            payload = (json.dumps(record, sort_keys=True) + "\n").encode("utf-8")
            if len(payload) > MAX_IPC_BYTES:
                payload = json.dumps({
                    "status": "ERROR",
                    "pid": os.getpid(),
                    "action_id": action_id,
                    "error": {
                        "type": "ChildProcessError",
                        "message": "child IPC record exceeded bound",
                    },
                }, sort_keys=True).encode("utf-8") + b"\n"
            os.write(write_fd, payload)
        finally:
            os.close(write_fd)
    os._exit(0)


def _wait_child(pid: int, read_fd: int, deadline: float) -> dict[str, Any]:
    status = None
    while time.monotonic() < deadline:
        waited, value = os.waitpid(pid, os.WNOHANG)
        if waited == pid:
            status = value
            break
        time.sleep(0.01)
    if status is None:
        try:
            os.kill(pid, 9)
        except ProcessLookupError:
            pass
        _, status = os.waitpid(pid, 0)
        os.close(read_fd)
        return {
            "status": "TIMEOUT",
            "pid": pid,
            "error": {"type": "TimeoutError", "message": "child did not exit before deadline"},
        }
    ready, _, _ = select.select([read_fd], [], [], 1.0)
    payload = os.read(read_fd, MAX_IPC_BYTES + 1) if ready else b""
    os.close(read_fd)
    if not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
        return {
            "status": "CRASH",
            "pid": pid,
            "error": {"type": "ChildProcessError", "message": f"wait_status={status}"},
        }
    if not payload:
        return {
            "status": "CRASH",
            "pid": pid,
            "error": {"type": "ChildProcessError", "message": "child returned no record"},
        }
    if len(payload) > MAX_IPC_BYTES:
        return {
            "status": "CRASH",
            "pid": pid,
            "error": {"type": "ChildProcessError", "message": "child IPC record exceeded bound"},
        }
    try:
        return json.loads(payload.decode("utf-8").splitlines()[-1])
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        return {
            "status": "CRASH",
            "pid": pid,
            "error": {"type": "ChildProcessError", "message": f"invalid child IPC: {error}"},
        }


def _run_children(
    root_observation: Any,
    root_request: Any,
    root_actions: list[tuple[int, ...]],
    particles: list[tuple[int, dict[str, list[int]], str]],
    learner_slot: int,
    policies: list[Any],
    runtime: dict[str, Any],
    card_data_sha256: str,
    worker_deadline: float,
    action_limit: int | None = None,
    particle_limit: int | None = None,
) -> list[dict[str, Any]]:
    actions = root_actions if action_limit is None else root_actions[:action_limit]
    chosen_particles = particles if particle_limit is None else particles[:particle_limit]
    children: list[tuple[int, int, int]] = []
    records: list[dict[str, Any]] = []
    for particle_index, (_seed, determinization, particle_id) in enumerate(chosen_particles):
        for action_index, action in enumerate(actions):
            if time.monotonic() >= worker_deadline:
                raise TimeoutError("worker deadline reached before all children launched")
            read_fd, write_fd = os.pipe()
            action_id = _action_id(action, root_request)
            pid = os.fork()
            if pid == 0:
                os.close(read_fd)
                _child_continuation(
                    write_fd, root_observation, determinization, action, action_id,
                    learner_slot, policies, runtime,
                    card_data_sha256,
                    min(worker_deadline, time.monotonic() + MAX_CHILD_SECONDS),
                )
            os.close(write_fd)
            children.append((pid, read_fd, particle_index))
            # The exact child count is itself part of the preflight proof.
            records.append({
                "_pid": pid,
                "_read_fd": read_fd,
                "_particle_index": particle_index,
                "_particle_id": particle_id,
                "_seed": _seed,
                "action_index": action_index,
                "action": action,
                "action_id": action_id,
            })
    completed: list[dict[str, Any]] = []
    for metadata in records:
        result = _wait_child(metadata["_pid"], metadata["_read_fd"], worker_deadline)
        result.update({
            "particle_index": metadata["_particle_index"],
            "particle_id": metadata["_particle_id"],
            "determinization_seed": metadata["_seed"],
            "action_index": metadata["action_index"],
            "action": list(metadata["action"]),
            "action_id": metadata["action_id"],
        })
        completed.append(result)
    return completed


def _state_group(
    config: dict[str, Any],
    root_raw: dict[str, Any],
    root_observation: Any,
    root_request: Any,
    root_actions: list[tuple[int, ...]],
    baseline_action: tuple[int, ...],
    results: list[dict[str, Any]],
    learner_slot: int,
    anchor: dict[str, Any],
    episode_id: str,
    projection: dict[str, Any],
    root_id: str,
    split_sequence_utc: str,
) -> dict[str, Any]:
    model_schema = config["assets"]["model_schema_sha256"]
    public_state = {
        "observation": _jsonable(root_observation),
        "request": _request_record(root_request),
    }
    public_tensor = _public_tensor_from_projection(projection, model_schema)
    baseline_id = _action_id(baseline_action, root_request)
    aggregates: list[dict[str, Any]] = []
    for action in root_actions:
        action_id = _action_id(action, root_request)
        action_results = [
            item for item in results
            if item.get("action_id") == action_id and item.get("status") == "COMPLETE"
        ]
        if not action_results:
            continue
        rewards = [float(item["reward_for_actor"]) for item in action_results]
        counts = {
            "W": sum(value == 1 for value in rewards),
            "D": sum(value == 0 for value in rewards),
            "L": sum(value == -1 for value in rewards),
        }
        mean = sum(rewards) / len(rewards)
        stderr = 0.0 if len(rewards) < 2 else math.sqrt(
            sum((value - mean) ** 2 for value in rewards) / (len(rewards) - 1) / len(rewards)
        )
        action_aggregate = {
            "action_id": action_id,
            "replicate_count": len(rewards),
            "wdl_counts": counts,
            "mean_reward": mean,
            "reward_stderr": stderr,
            "ci95_low": max(-1.0, mean - 1.96 * stderr),
            "ci95_high": min(1.0, mean + 1.96 * stderr),
            "baseline_action_id": baseline_id,
            "advantage_vs_fallback": None,
        }
        aggregates.append(action_aggregate)
    by_action = {item["action_id"]: item for item in aggregates}
    if baseline_id in by_action:
        baseline_mean = by_action[baseline_id]["mean_reward"]
        for item in aggregates:
            item["advantage_vs_fallback"] = item["mean_reward"] - baseline_mean
    replicates: list[dict[str, Any]] = []
    for particle_index in sorted({item["particle_index"] for item in results}):
        particle_results = [item for item in results if item["particle_index"] == particle_index]
        actions: list[dict[str, Any]] = []
        for item in particle_results:
            option = root_request.options[item["action"][0]]
            actions.append({
                "action_id": item["action_id"],
                "semantic_action_fingerprint": sha256_value(
                    [_option_record(root_request.options[index]) for index in item["action"]]
                ),
                "semantic_path": [_option_record(option)],
                "transport_original_indices": item["action"],
                "terminal_engine_result": item.get("terminal_engine_result", {"winner_player": None, "is_draw": True}),
                "reward_for_actor": item.get("reward_for_actor", 0),
                "completed": item.get("status") == "COMPLETE",
                "continuation_steps": int(item.get("continuation_steps", 0)),
                # Opponent transition labels are restricted to the sidecar;
                # the trainable dataset carries no opponent-view response.
                "first_opponent_response": None,
                "fallback_used": False,
                "nonfinite": False,
                "error": None if item.get("status") == "COMPLETE" else item.get("error"),
            })
        particle_id = particle_results[0]["particle_id"] if particle_results else "missing"
        seed = particle_results[0]["determinization_seed"] if particle_results else None
        replicates.append({
            "replicate_id": particle_index,
            "determinization_id": particle_id,
            "determinization_seed": seed,
            "engine_rng": "SYSTEM_ENTROPY_UNCONTROLLED",
            "world_independence": "PAIRED_SHARED_WORLD",
            "actions": actions,
        })
    split_hash_input = "|".join((episode_id, root_id, anchor["baseline_id"], str(learner_slot)))
    split_group_key = f"{split_sequence_utc}|{hashlib.sha256(split_hash_input.encode('utf-8')).hexdigest()}"
    return {
        "state_group_id": sha256_value({"episode": episode_id, "request": root_request.request_id}),
        "split_group_key": split_group_key,
        "source_episode_id": episode_id,
        "public_state_sha256": sha256_value(public_state),
        "acting_player": int(root_request.acting_player),
        "root_player": learner_slot,
        "request": _request_record(root_request),
        "public_tensor": public_tensor,
        "legal_action_count": len(root_actions),
        "enumerated_action_count": len(root_actions),
        "action_enumeration_complete": True,
        "compound_coverage": "SINGLE_CHOICE",
        "stop_tested": False,
        "replicates": replicates,
        "action_aggregates": aggregates,
    }


def _start_worker(
    config_path: Path,
    config: dict[str, Any],
    output: Path,
    state_index: int,
    anchor_id: str,
    slot: int,
    run_id: str,
    root_id: str,
    config_sha256: str,
    git_dirty_sha256: str,
    preflight: bool = False,
    complete_root: bool = False,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    if output.exists():
        raise ScheduleError(f"refusing stale expected worker output: {output}")
    command = [
        sys.executable, str(Path(__file__).resolve()), "--worker",
        "--config", str(config_path), "--output", str(output),
        "--state-index", str(state_index), "--anchor-id", anchor_id, "--learner-slot", str(slot),
        "--run-id", run_id, "--root-id", root_id, "--config-sha256", config_sha256,
        "--git-dirty-sha256", git_dirty_sha256,
    ]
    if preflight:
        command.append("--preflight-worker")
    if complete_root:
        command.append("--complete-root-worker")
    try:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            start_new_session=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            communication_timeout = MAX_WORKER_SECONDS + 30 if timeout_seconds is None else max(1.0, timeout_seconds)
            stdout, stderr = _bounded_communicate(process, communication_timeout)
        except subprocess.TimeoutExpired:
            cleanup = _terminate_process_group(process.pid)
            try:
                stdout, stderr = _bounded_communicate(process, 5)
            except (OSError, ValueError, subprocess.TimeoutExpired):
                process.kill()
                process.wait(timeout=5)
                stdout, stderr = "", ""
            return {
                "status": "WORKER_TIMEOUT" if cleanup["group_gone"] else "WORKER_TIMEOUT_GROUP_NOT_GONE",
                "returncode": process.returncode,
                "stdout": stdout[-4_000:],
                "stderr": stderr[-4_000:],
                "process_group_cleanup": cleanup,
                "process_group_killed": bool(cleanup["group_gone"]),
                "process_group_gone": bool(cleanup["group_gone"]),
            }
    except (OSError, subprocess.SubprocessError) as error:
        return {"status": "WORKER_FAILED", "error": str(error)}
    if output.is_file():
        report = load_json(output)
        _validate_worker_binding(report, run_id, root_id, config_sha256, git_dirty_sha256)
        report.setdefault("worker_returncode", process.returncode)
        return report
    return {
        "status": "WORKER_FAILED",
        "returncode": process.returncode,
        "stdout": stdout[-4_000:],
        "stderr": stderr[-4_000:],
    }


def _worker(
    config: dict[str, Any], output: Path, state_index: int, anchor_id: str,
    learner_slot: int, run_id: str, root_id: str, config_sha256: str,
    git_dirty_sha256: str,
    preflight: bool = False, complete_root: bool = False,
) -> int:
    actual_config_sha256 = sha256_file(Path(config["_config_path"]))
    if actual_config_sha256 != config_sha256:
        raise ScheduleError("worker config SHA-256 differs from coordinator")
    actual_git_dirty_sha256 = _git_dirty_sha256()
    if actual_git_dirty_sha256 != git_dirty_sha256:
        raise ScheduleError("worker Git dirty-state SHA-256 differs from coordinator")
    if output.exists() and output.stat().st_size:
        raise ScheduleError(f"worker refuses pre-existing output: {output}")
    assignment = _assignment_for_state(config, state_index)
    if assignment["anchor_id"] != anchor_id or assignment["learner_slot"] != learner_slot:
        raise ScheduleError("worker assignment does not match the declared root schedule")
    config["_run_id"] = run_id
    config["_root_id"] = root_id
    runtime = _runtime_imports()
    learner_cfg = config["learner_policy"]
    anchor = next(item for item in config["frozen_anchor_policies"] if item["baseline_id"] == anchor_id)
    Policy = runtime["NativeRulePolicy"]
    policies = [None, None]
    learner = Policy(resolve_repo_path(learner_cfg["directory"]))
    opponent = Policy(resolve_repo_path(anchor["directory"]))
    policies[learner_slot] = learner
    policies[1 - learner_slot] = opponent
    learner.reset(f"{run_id}:{root_id}:attempt-1", learner_slot, "start")
    opponent.reset(f"{run_id}:{root_id}:attempt-1", 1 - learner_slot, "start")
    deck0 = policies[0].deck
    deck1 = policies[1].deck
    expected_engine = config["assets"]["engine"]["sha256"]
    actual_engine = sha256_file(SAMPLE / "cg/libcg.so")
    if actual_engine != expected_engine:
        raise ScheduleError(f"loaded engine hash differs: {actual_engine} != {expected_engine}")
    actual_card_data = sha256_file(ROOT / "private/assets/official/EN_Card_Data.csv")
    if actual_card_data != config["assets"]["card_data"]["sha256"]:
        raise ScheduleError("loaded card data hash differs from schedule")
    started = time.monotonic()
    deadline = started + MAX_WORKER_SECONDS
    report: dict[str, Any] = {
        "schema_version": 1,
        "status": "RUNNING",
        "run_id": run_id,
        "root_id": root_id,
        "config_sha256": config_sha256,
        "git_dirty_sha256": git_dirty_sha256,
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "state_index": state_index,
        "anchor_id": anchor_id,
        "learner_slot": learner_slot,
        "anchor_state_index": assignment["anchor_state_index"],
        "candidate_window": assignment["window_name"],
        "candidate_turn_min": assignment["turn_min"],
        "candidate_turn_max": assignment["turn_max"],
        "root_seed_label": sha256_value({"root_id": root_id, "kind": "native-start"}),
        "root_game_seed_policy": config["state_schedule"].get(
            "root_game_seed_policy", "NATIVE_START_SYSTEM_ENTROPY_UNSEEDED"
        ),
        "native_launches": 0,
        "counters": {
            "invalid_actions": 0,
            "fallback_actions": 0,
            "post_terminal_actions": 0,
            "child_crashes": 0,
            "child_timeouts": 0,
            "continuation_rollouts": 0,
            "parent_valid_steps": 0,
            "opponent_transition_observed": 0,
            "opponent_transition_terminal_before_opponent": 0,
            "opponent_transition_unsupported": 0,
            "opponent_transition_missing_or_error": 0,
        },
        "limits": {
            "max_worker_steps": MAX_WORKER_STEPS,
            "max_worker_seconds": MAX_WORKER_SECONDS,
            "max_child_steps": MAX_CHILD_STEPS,
            "max_child_seconds": MAX_CHILD_SECONDS,
        },
        "coverage_scope": {
            "root_selection": "MAIN_SINGLE_CHOICE_ONLY",
            "preflight_actions_executed": (
                "ALL_LEGAL_ROOT_ACTIONS" if complete_root else (PREFLIGHT_ACTIONS if preflight else None)
            ),
            "compound_selection": "REFUSED_PENDING_SEPARATE_MECHANICS_GATE",
            "optional_stop": "REFUSED_PENDING_SEPARATE_MECHANICS_GATE",
            "separate_mechanics_gate_required": True,
        },
        "complete_root_preflight": complete_root,
        "root_acquisition": {
            "max_attempts": int(config["state_schedule"].get("max_root_acquisition_attempts", 1)),
            "attempts": 0,
            "terminal_before_candidate": 0,
            "attempt_ids": [],
        },
        "hashes": {
            "git_dirty_sha256": git_dirty_sha256,
            "source_commit": config.get("source_commit") or _canonical_source_commit(),
            "collector_sha256": sha256_file(Path(__file__).resolve()),
            "engine_sha256": actual_engine,
            "card_data_sha256": actual_card_data,
            "game_wrapper_sha256": sha256_file(SAMPLE / "cg/game.py"),
            "api_wrapper_sha256": sha256_file(SAMPLE / "cg/api.py"),
            "sim_wrapper_sha256": sha256_file(SAMPLE / "cg/sim.py"),
            "action_schema_sha256": config["assets"]["action_observation_contract"]["action_schema_sha256"],
            "observation_schema_sha256": config["assets"]["action_observation_contract"]["observation_schema_sha256"],
            "model_schema_sha256": config["assets"]["model_schema_sha256"],
            "learner_receipt_sha256": learner_cfg["receipt_sha256"],
            "learner_deck_sha256": learner_cfg["deck_sha256"],
            "learner_module_sha256": sha256_file(resolve_repo_path(learner_cfg["directory"]) / "main.py"),
            "opponent_receipt_sha256": anchor["receipt_sha256"],
            "opponent_deck_sha256": anchor["deck_sha256"],
            "opponent_module_sha256": sha256_file(resolve_repo_path(anchor["directory"]) / "main.py"),
            "g2_checkpoint_sha256": config["assets"]["g2_checkpoint"]["sha256"],
        },
    }
    raw = None
    option_encoder = None
    try:
        checkpoint_path = resolve_repo_path(config["assets"]["g2_checkpoint"]["path"])
        option_encoder, trunk_binding = runtime["load_gate1_trunk"](
            package_path=checkpoint_path,
            bc_checkpoint_path=BC_TRUNK_PATH,
            device="cpu",
        )
        actual_trunk_state_sha256 = runtime["state_dict_sha256"](option_encoder.state_dict())
        if actual_trunk_state_sha256 != BC_TRUNK_STATE_SHA256:
            raise ScheduleError("loaded G2 projection model is not the pinned BC epoch-4 state")
        if any(parameter.requires_grad for parameter in option_encoder.parameters()):
            raise ScheduleError("loaded BC projection model has trainable parameters")
        if (
            trunk_binding.g2_package_sha256 != config["assets"]["g2_checkpoint"]["sha256"]
            or trunk_binding.bc_trunk_checkpoint_sha256 != BC_TRUNK_CHECKPOINT_SHA256
            or trunk_binding.bc_trunk_state_sha256 != actual_trunk_state_sha256
            or trunk_binding.bc_trunk_optimizer_steps != BC_TRUNK_OPTIMIZER_STEPS
            or trunk_binding.mode != TRUNK_MODE
        ):
            raise ScheduleError("loaded projection model binding differs from pinned BC epoch-4 provenance")
        report["hashes"].update({
            "bc_trunk_checkpoint_sha256": trunk_binding.bc_trunk_checkpoint_sha256,
            "bc_trunk_state_sha256": actual_trunk_state_sha256,
            "bc_trunk_optimizer_steps": trunk_binding.bc_trunk_optimizer_steps,
            "trunk_mode": trunk_binding.mode,
            "bc_trunk_frozen": True,
        })
        max_root_attempts = int(config["state_schedule"].get("max_root_acquisition_attempts", 1))
        root_attempt = 1
        episode_id = f"{run_id}:{root_id}:attempt-{root_attempt}"
        report["root_acquisition"]["attempts"] = root_attempt
        report["root_acquisition"]["attempt_ids"].append(episode_id)
        raw, start_data = runtime["battle_start"](deck0, deck1)
        report["native_launches"] = 1
        if raw is None:
            raise ScheduleError(f"BattleStart failed: {start_data.errorPlayer=} {start_data.errorType=}")
        generation_steps = 0
        transition = 0
        public_prefix: list[dict[str, Any]] = []
        root_raw = None
        root_observation = None
        root_semantic = None
        root_request = None
        baseline_action = None
        required_selection_context = int(config["state_schedule"]["selection_context_required"])
        while time.monotonic() < deadline and generation_steps < MAX_WORKER_STEPS:
            observation = runtime["to_observation_class"](raw)
            if observation.current is None:
                raise ScheduleError("live battle omitted current state")
            result = int(observation.current.result)
            if result in (0, 1, 2):
                report["root_acquisition"]["terminal_before_candidate"] += 1
                if root_attempt >= max_root_attempts:
                    raise ScheduleError(
                        "battle ended before a qualifying learner decision after "
                        f"{root_attempt} root-acquisition attempts"
                    )
                runtime["battle_finish"]()
                root_attempt += 1
                episode_id = f"{run_id}:{root_id}:attempt-{root_attempt}"
                report["root_acquisition"]["attempts"] = root_attempt
                report["root_acquisition"]["attempt_ids"].append(episode_id)
                learner.reset(episode_id, learner_slot, "start")
                opponent.reset(episode_id, 1 - learner_slot, "start")
                raw, start_data = runtime["battle_start"](deck0, deck1)
                report["native_launches"] += 1
                if raw is None:
                    raise ScheduleError(f"BattleStart failed: {start_data.errorPlayer=} {start_data.errorType=}")
                generation_steps = 0
                transition = 0
                public_prefix = []
                continue
            if _candidate(
                observation,
                learner_slot,
                required_selection_context,
                int(assignment["turn_min"]),
                assignment["turn_max"],
            ):
                semantic, request = runtime["semantic_snapshot"](
                    raw, episode_id, transition, config["assets"]["card_data"]["sha256"],
                )
                if request is None:
                    raise ScheduleError("candidate state has no semantic request")
                _validate_main_single_root(request, required_selection_context)
                root_actions = _complete_actions(observation)
                if len(root_actions) < 2 or len(root_actions) > 10:
                    raise ScheduleError("candidate action set violates complete action cap")
                chosen = learner.choose_native(raw, semantic, request)
                baseline_action = _validate_action(request, chosen)
                root_raw = raw
                root_observation = runtime["to_observation_class"](raw)
                root_semantic = semantic
                root_request = request
                break
            acting = int(observation.current.yourIndex)
            semantic, request = runtime["semantic_snapshot"](
                raw, episode_id, transition, config["assets"]["card_data"]["sha256"],
            )
            if request is None or semantic.terminal_result is not None:
                raise ScheduleError("ongoing live battle has no semantic request")
            if acting == learner_slot:
                public_prefix.append({
                    "raw_observation": _public_raw(raw),
                    "battle_id": episode_id,
                    "selection_seq": transition,
                    "observation_schema_version": int(semantic.schema_version),
                    "acting_player": acting,
                })
            chosen = policies[acting].choose_native(raw, semantic, request)
            _validate_action(request, chosen)
            raw = runtime["battle_select"](list(chosen.submitted_original_indices))
            generation_steps += 1
            transition += 1
        if (
            root_raw is None or root_observation is None or root_semantic is None
            or root_request is None or baseline_action is None
        ):
            raise TimeoutError("no qualifying learner MAIN state before worker bound")
        root_actions = _complete_actions(root_observation)
        if complete_root:
            _validate_main_single_root(
                root_request,
                int(config["state_schedule"]["selection_context_required"]),
            )
            if root_request.min_count <= 0 < root_request.max_count:
                raise ScheduleError(
                    "complete-root preflight refuses compound/optional-STOP root; separate mechanics gate pending"
                )
            if len(root_actions) * COMPLETE_ROOT_PARTICLES > MAX_COMPLETE_ROOT_BRANCHES:
                raise ScheduleError("complete-root preflight exceeds hard 20-branch cap")
        particle_entries: list[tuple[int, dict[str, list[int]], str]] = []
        particle_count = COMPLETE_ROOT_PARTICLES if complete_root else int(config["hidden_worlds"]["seeds_per_state"])
        for particle_index in range(particle_count):
            seed = int(sha256_value({"root_id": root_id, "particle_index": particle_index})[:16], 16) % (2**31 - 1)
            if seed == 0:
                seed = particle_index + 1
            determinization = runtime["determinize"](
                root_observation, deck0, deck1, seed,
                known_transients={0: [], 1: []}, known_hidden_active={},
            )
            particle_id = sha256_value(determinization)
            particle_entries.append((seed, determinization, particle_id))
        action_limit = PREFLIGHT_ACTIONS if preflight and not complete_root else None
        particle_limit = PREFLIGHT_PARTICLES if preflight and not complete_root else None
        results = _run_children(
            root_observation, root_request, root_actions, particle_entries,
            learner_slot, policies, runtime,
            config["assets"]["card_data"]["sha256"], deadline,
            action_limit=action_limit, particle_limit=particle_limit,
        )
        report["counters"]["continuation_rollouts"] = len(results)
        report["counters"]["invalid_actions"] = sum(item.get("invalid_actions", 0) for item in results)
        report["counters"]["fallback_actions"] = sum(item.get("fallback_actions", 0) for item in results)
        report["counters"]["post_terminal_actions"] = sum(item.get("post_terminal_actions", 0) for item in results)
        report["counters"]["child_crashes"] = sum(item.get("status") == "CRASH" for item in results)
        report["counters"]["child_timeouts"] = sum(item.get("status") == "TIMEOUT" for item in results)
        transition_status_counts = {
            "OBSERVED": "opponent_transition_observed",
            "TERMINAL_BEFORE_OPPONENT": "opponent_transition_terminal_before_opponent",
            "UNSUPPORTED_FIRST_OPPONENT_REQUEST": "opponent_transition_unsupported",
            "MISSING_OR_ERROR": "opponent_transition_missing_or_error",
        }
        for result in results:
            counter = transition_status_counts.get(
                result.get("opponent_transition", {}).get("status")
            )
            if counter is None:
                raise ScheduleError("child emitted unknown opponent transition status")
            report["counters"][counter] += 1
        report["child_results"] = results
        expected_children = (action_limit or len(root_actions)) * (particle_limit or len(particle_entries))
        if len(results) != expected_children:
            raise ScheduleError("continuation child count does not equal complete actions x particles")
        if complete_root and expected_children != len(root_actions) * COMPLETE_ROOT_PARTICLES:
            raise ScheduleError("complete-root branch count is not exactly two particles per legal action")
        if any(item.get("status") != "COMPLETE" for item in results):
            raise ScheduleError("failed continuation cannot enter dataset")
        # Apply the baseline only in the parent.  A valid parent transition is
        # the COW proof that children did not corrupt the live Battle pointer or
        # the inherited exact-Grim history.
        parent_next = runtime["battle_select"](list(baseline_action))
        parent_observation = runtime["to_observation_class"](parent_next)
        if parent_observation.current is None:
            raise ScheduleError("parent continuation omitted current state")
        report["counters"]["parent_valid_steps"] = 1
        parent_result = int(parent_observation.current.result)
        if parent_result in (0, 1, 2):
            parent_request = None
            parent_semantic = None
        elif parent_result == -1:
            parent_semantic, parent_request = runtime["semantic_snapshot"](
                parent_next,
                episode_id,
                int(root_request.selection_seq) + 1,
                config["assets"]["card_data"]["sha256"],
            )
            if parent_request is None or parent_semantic.terminal_result is not None:
                raise ScheduleError("parent post-baseline ongoing state has no coherent request")
        else:
            raise ScheduleError(f"parent returned unknown terminal result {parent_result}")
        report["parent_cow_check"] = {
            "pre_public_state_sha256": sha256_value({
                "observation": _jsonable(root_semantic),
                "request": _request_record(root_request),
            }),
            "post_public_state_sha256": sha256_value({
                "observation": _jsonable(parent_semantic) if parent_semantic is not None else {
                    "terminal_result": parent_result,
                    "acting_player": int(parent_observation.current.yourIndex),
                    "turn": int(parent_observation.current.turn),
                },
                "request": _request_record(parent_request) if parent_request is not None else None,
            }),
            "pre_request_id": root_request.request_id,
            "post_request_id": parent_request.request_id if parent_request is not None else None,
            "post_selection_seq": parent_request.selection_seq if parent_request is not None else None,
            "post_terminal_result": parent_result if parent_result in (0, 1, 2) else None,
            "request_or_terminal_coherent": (
                parent_request is not None and parent_request.episode_uuid == episode_id
                and parent_request.selection_seq > root_request.selection_seq
            ) or (parent_result in (0, 1, 2) and parent_request is None),
        }
        if not report["parent_cow_check"]["request_or_terminal_coherent"]:
            raise ScheduleError("parent COW request/terminal coherence check failed")
        if int(root_request.selection_seq) > 0 and not public_prefix:
            raise ScheduleError("root has nonzero selection_seq but no retained actor public prefix")
        public_raw = dict(root_raw)
        public_raw["search_begin_input"] = None
        projection = runtime["advance_public_recurrent_prefix"](
            option_encoder,
            public_prefix,
            root_raw_observation=public_raw,
            root_actions=root_actions,
            battle_id=episode_id,
            root_selection_seq=int(root_request.selection_seq),
            player_index=learner_slot,
            card_data_sha256=config["assets"]["card_data"]["sha256"],
            observation_schema_version=int(root_request.schema_version),
            initial_hidden_source="PRODUCTION_INITIAL_HIDDEN_EPISODE_START",
            prefix_starts_at_episode_start=True,
        )
        report["g2_projection"] = projection
        if projection.get("status") != "OK":
            report.update({
                "status": "PASS_EXECUTION_G2_BLOCKED",
                "generation_steps": generation_steps,
                "root": {
                    "episode_id": episode_id,
                    "battle_id_or_episode_uuid": episode_id,
                    "observation_schema_version": int(root_request.schema_version),
                    "selection_seq": int(root_request.selection_seq),
                    "card_data_sha256": config["assets"]["card_data"]["sha256"],
                    "history_recorded": bool(public_prefix),
                    "public_prefix_record_count": len(public_prefix),
                    "public_prefix_selection_seqs": [item["selection_seq"] for item in public_prefix],
                    "turn": int(root_observation.current.turn),
                    "acting_player": int(root_observation.current.yourIndex),
                    "legal_action_count": len(root_actions),
                    "min_count": int(root_request.min_count),
                    "max_count": int(root_request.max_count),
                    "selection_type": int(root_request.selection_type),
                    "selection_context": int(root_request.selection_context),
                    "option_semantics": [
                        dict(_option_record(option), is_end=option.choice_role == "END")
                        for option in root_request.options
                    ],
                    "option_semantic_fingerprints": [
                        option.semantic_fingerprint for option in root_request.options
                    ],
                    "end_option_count": sum(option.choice_role == "END" for option in root_request.options),
                    "stop_legal": root_request.min_count <= 0 < root_request.max_count,
                    "stop_tested": False,
                    "preflight_actions_executed": (
                        len(root_actions) if complete_root else (PREFLIGHT_ACTIONS if preflight else len(root_actions))
                    ),
                    "preflight_actions_legal": len(root_actions),
                    "complete_root_preflight": complete_root,
                    "baseline_action_id": _action_id(baseline_action, root_request),
                    "baseline_transport_original_indices": list(baseline_action),
                    "search_begin_input_retained": False,
                },
                "private_provenance": {
                    "anchor_baseline_id": anchor["baseline_id"],
                    "continuation_policy_id": learner_cfg["policy_id"],
                    "opponent_policy_id": anchor["policy_id"],
                    "hidden_state_source": "LABEL_ONLY_NOT_PUBLIC_INPUT",
                    "root_search_begin_input_retained": False,
                    "source_raw_observation_sha256": sha256_value(root_raw),
                    "preflight_partial": preflight,
                    "complete_root_preflight": complete_root,
                    "compound_stop_coverage": "PENDING_SEPARATE_MECHANICS_GATE",
                    "coverage_scope": "SINGLE_CHOICE_ONLY; COMPOUND_AND_OPTIONAL_STOP_REQUIRE_SEPARATE_MECHANICS_GATE",
                },
            })
            return 0
        public_tensor = _public_tensor_from_projection(
            projection, config["assets"]["model_schema_sha256"],
        )
        root_action_equivalence_keys = _root_action_equivalence_keys(
            runtime, public_tensor, root_request, root_actions,
        )
        group = _state_group(
            config, root_raw, root_observation, root_request, root_actions,
            baseline_action, results, learner_slot, anchor, episode_id, projection,
            root_id, datetime.now(timezone.utc).isoformat(),
        )
        for item in root_action_equivalence_keys:
            item["state_group_id"] = group["state_group_id"]
        if complete_root:
            expected_action_ids = {_action_id(action, root_request) for action in root_actions}
            if len(group["action_aggregates"]) != len(root_actions):
                raise ScheduleError("complete-root action aggregate set is incomplete")
            if {item["action_id"] for item in group["action_aggregates"]} != expected_action_ids:
                raise ScheduleError("complete-root aggregate action IDs are incomplete")
            if any(
                len(replicate["actions"]) != len(root_actions)
                for replicate in group["replicates"]
            ):
                raise ScheduleError("complete-root replicate action set is incomplete")
            dataset_check = _validate_dataset_shape(_dataset_from_group(config, group, anchor))
            if dataset_check:
                raise ScheduleError(f"complete-root dataset schema validation failed: {dataset_check}")
            report["dataset_schema_status"] = "PASS"
            report["dataset_schema_errors"] = []
        report.update({
            "status": "PASS_COMPLETE",
            "generation_steps": generation_steps,
            "root": {
                "episode_id": episode_id,
                "battle_id_or_episode_uuid": episode_id,
                "observation_schema_version": int(root_request.schema_version),
                "selection_seq": int(root_request.selection_seq),
                "card_data_sha256": config["assets"]["card_data"]["sha256"],
                "history_recorded": bool(public_prefix),
                "public_prefix_record_count": len(public_prefix),
                "public_prefix_selection_seqs": [item["selection_seq"] for item in public_prefix],
                "turn": int(root_observation.current.turn),
                "acting_player": int(root_observation.current.yourIndex),
                "legal_action_count": len(root_actions),
                "min_count": int(root_request.min_count),
                "max_count": int(root_request.max_count),
                "selection_type": int(root_request.selection_type),
                "selection_context": int(root_request.selection_context),
                "option_semantics": [
                    dict(_option_record(option), is_end=option.choice_role == "END")
                    for option in root_request.options
                ],
                "option_semantic_fingerprints": [
                    option.semantic_fingerprint for option in root_request.options
                ],
                "end_option_count": sum(option.choice_role == "END" for option in root_request.options),
                "stop_legal": root_request.min_count <= 0 < root_request.max_count,
                "stop_tested": False,
                "preflight_actions_executed": (
                    len(root_actions) if complete_root else (PREFLIGHT_ACTIONS if preflight else len(root_actions))
                ),
                "preflight_actions_legal": len(root_actions),
                "complete_root_preflight": complete_root,
                "baseline_action_id": _action_id(baseline_action, root_request),
                "baseline_transport_original_indices": list(baseline_action),
                "public_state_sha256": group["public_state_sha256"],
                "search_begin_input_retained": False,
            },
            "private_provenance": {
                "anchor_baseline_id": anchor["baseline_id"],
                "continuation_policy_id": learner_cfg["policy_id"],
                "opponent_policy_id": anchor["policy_id"],
                "hidden_state_source": "LABEL_ONLY_NOT_PUBLIC_INPUT",
                "root_search_begin_input_retained": False,
                "source_raw_observation_sha256": sha256_value(root_raw),
                "preflight_partial": preflight,
                "complete_root_preflight": complete_root,
                "compound_stop_coverage": "PENDING_SEPARATE_MECHANICS_GATE",
                "coverage_scope": "SINGLE_CHOICE_ONLY; COMPOUND_AND_OPTIONAL_STOP_REQUIRE_SEPARATE_MECHANICS_GATE",
            },
            "root_action_equivalence_keys": root_action_equivalence_keys,
            "state_group": group,
        })
    except Exception as error:
        report.update({
            "status": "FAIL",
            "error": {"type": type(error).__name__, "message": str(error)[:1000]},
        })
    finally:
        if raw is not None:
            try:
                report["parent_battle_finished"] = True
                runtime["battle_finish"]()
            except Exception as error:
                report["parent_battle_finished"] = False
                report["finish_error"] = {"type": type(error).__name__, "message": str(error)[:500]}
        if report.get("status") in {"PASS_COMPLETE", "PASS_EXECUTION_G2_BLOCKED"} and not report.get(
            "parent_battle_finished", False
        ):
            report["status"] = "FAIL"
            report["error"] = {
                "type": "BattleCleanupError",
                "message": "parent native battle did not finish cleanly",
            }
        report["elapsed_seconds"] = time.monotonic() - started
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if report["status"] in {"PASS_COMPLETE", "PASS_EXECUTION_G2_BLOCKED"} else 1


def _validate_dataset_shape(value: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    try:
        import jsonschema
    except ImportError:
        script = f"""
const fs = require('fs');
const Ajv2020 = require('ajv/dist/2020');
const schema = JSON.parse(fs.readFileSync({json.dumps(str(DATASET_SCHEMA))}, 'utf8'));
const data = JSON.parse(fs.readFileSync(0, 'utf8'));
const validate = new Ajv2020({{allErrors: true, strict: false}}).compile(schema);
if (validate(data)) process.stdout.write('[]');
else {{ process.stdout.write(JSON.stringify(validate.errors)); process.exitCode = 1; }}
"""
        try:
            result = subprocess.run(
                ["node", "-e", script], cwd=ROOT, input=json.dumps(value),
                capture_output=True, text=True, timeout=10, check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            return [f"schema validator unavailable: {error}"]
        if result.returncode:
            try:
                node_errors = json.loads(result.stdout)
                errors.extend(
                    f"{item.get('instancePath', '$')}: {item.get('message', 'schema error')}"
                    for item in node_errors
                )
            except (TypeError, json.JSONDecodeError):
                errors.append(f"Ajv schema validation failed: {result.stderr[-500:]}")
    else:
        schema = load_json(DATASET_SCHEMA)
        errors.extend(error.message for error in jsonschema.Draft202012Validator(schema).iter_errors(value))
    for group in value.get("state_groups", []):
        if group.get("legal_action_count") != group.get("enumerated_action_count"):
            errors.append("action enumeration count mismatch")
        if len(group.get("action_aggregates", [])) != group.get("legal_action_count"):
            errors.append("action aggregate count mismatch")
        for replicate in group.get("replicates", []):
            if len(replicate.get("actions", [])) != group.get("legal_action_count"):
                errors.append("replicate action count mismatch")
            for action in replicate.get("actions", []):
                if action.get("first_opponent_response") is not None:
                    errors.append("opponent response must be emitted only in the restricted sidecar")
    return errors


def _validate_opponent_sidecar_shape(value: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    try:
        import jsonschema
    except ImportError:
        script = f"""
const fs = require('fs');
const Ajv2020 = require('ajv/dist/2020');
const schema = JSON.parse(fs.readFileSync({json.dumps(str(OPPONENT_LABEL_SCHEMA))}, 'utf8'));
const data = JSON.parse(fs.readFileSync(0, 'utf8'));
const validate = new Ajv2020({{allErrors: true, strict: false}}).compile(schema);
if (validate(data)) process.stdout.write('[]');
else {{ process.stdout.write(JSON.stringify(validate.errors)); process.exitCode = 1; }}
"""
        try:
            result = subprocess.run(
                ["node", "-e", script], cwd=ROOT, input=json.dumps(value),
                capture_output=True, text=True, timeout=10, check=False,
            )
        except (OSError, subprocess.SubprocessError) as error:
            return [f"restricted label schema validator unavailable: {error}"]
        if result.returncode:
            try:
                node_errors = json.loads(result.stdout)
                errors.extend(
                    f"{item.get('instancePath', '$')}: {item.get('message', 'schema error')}"
                    for item in node_errors
                )
            except (TypeError, json.JSONDecodeError):
                errors.append(f"restricted label Ajv validation failed: {result.stderr[-500:]}")
    else:
        schema = load_json(OPPONENT_LABEL_SCHEMA)
        errors.extend(error.message for error in jsonschema.Draft202012Validator(schema).iter_errors(value))

    forbidden = {
        "model_input", "public_tensor", "history_tokens", "public_hidden",
        "opponent_view_observation", "raw_observation", "search_begin_input",
        "hidden_determinization_output", "determinization", "determinization_seed",
    }

    def visit(item: Any, path: str = "$") -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if str(key).lower() in forbidden:
                    errors.append(f"restricted label firewall forbids {path}.{key}")
                visit(child, f"{path}.{key}")
        elif isinstance(item, list):
            for index, child in enumerate(item):
                visit(child, f"{path}[{index}]")

    visit(value)
    labels = value.get("labels", [])
    projection_binding = value.get("public_projection_binding", {})
    projection_groups = projection_binding.get("groups", []) if isinstance(projection_binding, dict) else []
    projection_ids = {item.get("state_group_id") for item in projection_groups}
    root_keys = value.get("root_action_keys", [])
    root_key_map = {
        (item.get("state_group_id"), item.get("action_id")): item.get("semantic_equivalence_key")
        for item in root_keys
        if isinstance(item, dict)
    }
    if len(root_key_map) != len(root_keys):
        errors.append("root action equivalence keys contain duplicate joins")
    for index, label in enumerate(labels):
        status = label.get("status")
        request = label.get("first_opponent_request")
        chosen = label.get("chosen_action")
        join = (label.get("state_group_id"), label.get("action_id"))
        if label.get("state_group_id") not in projection_ids:
            errors.append(f"label {index}: public projection binding misses state group")
        if root_key_map.get(join) != label.get("root_action_semantic_equivalence_key"):
            errors.append(f"label {index}: root action equivalence key join mismatch")
        if status == "OBSERVED":
            if not request or not chosen:
                errors.append("label %d: OBSERVED requires request and chosen action" % index)
            elif (
                request.get("selection_type") != 0
                or request.get("selection_context") != 0
                or request.get("min_count") != 1
                or request.get("max_count") != 1
            ):
                errors.append(f"label {index}: OBSERVED request is not MAIN context0 singleton")
        elif status == "UNSUPPORTED_FIRST_OPPONENT_REQUEST":
            if not request or chosen is not None:
                errors.append(f"label {index}: unsupported request must retain request and no chosen action")
        elif status == "TERMINAL_BEFORE_OPPONENT":
            if request is not None or chosen is not None:
                errors.append(f"label {index}: terminal-before-opponent must have no request/action")
        elif status == "MISSING_OR_ERROR" and not label.get("error"):
            errors.append(f"label {index}: missing/error status requires an error record")
        if request is not None and request.get("option_count") != len(request.get("options", [])):
            errors.append(f"label {index}: complete opponent legal set count mismatch")
        if request is not None and any(
            not isinstance(option.get("semantic_equivalence_key"), str)
            for option in request.get("options", [])
        ):
            errors.append(f"label {index}: opponent legal set lacks canonical equivalence keys")
        option_by_index = {
            option.get("original_index"): option
            for option in request.get("options", [])
            if isinstance(option, dict) and isinstance(option.get("original_index"), int)
        } if request is not None else {}
        if request is not None and len(option_by_index) != len(request.get("options", [])):
            errors.append(f"label {index}: opponent legal set has duplicate/missing transport indices")
        if request is not None and chosen is not None:
            legal_keys = {
                option.get("semantic_equivalence_key") for option in request.get("options", [])
            }
            chosen_keys = {
                option.get("semantic_equivalence_key") for option in chosen.get("semantic_path", [])
            }
            if not chosen_keys <= legal_keys:
                errors.append(f"label {index}: chosen semantic path is outside retained legal set")
            if status == "OBSERVED" and (
                len(chosen_keys) != 1
                or chosen.get("semantic_equivalence_key") != next(iter(chosen_keys))
            ):
                errors.append(f"label {index}: chosen action equivalence key is inconsistent")
            if status == "OBSERVED":
                indices = chosen.get("transport_original_indices")
                if (
                    not isinstance(indices, list)
                    or len(indices) != 1
                    or len(set(indices)) != 1
                    or not isinstance(indices[0], int)
                    or indices[0] < 0
                ):
                    errors.append(f"label {index}: OBSERVED requires one unique in-range transport index")
                else:
                    selected = option_by_index.get(indices[0])
                    path = chosen.get("semantic_path")
                    if selected is None:
                        errors.append(f"label {index}: chosen transport index is outside the retained legal set")
                    if not isinstance(path, list) or len(path) != 1:
                        errors.append(f"label {index}: OBSERVED requires exactly one semantic path option")
                    elif selected is not None:
                        path_option = path[0]
                        if path_option.get("semantic_equivalence_key") != selected.get("semantic_equivalence_key"):
                            errors.append(f"label {index}: chosen canonical key does not match transport option")
                        if path_option.get("semantic_fingerprint") != selected.get("semantic_fingerprint"):
                            errors.append(f"label {index}: chosen audit fingerprint does not match transport option")
                        if chosen.get("semantic_equivalence_key") != selected.get("semantic_equivalence_key"):
                            errors.append(f"label {index}: chosen action key does not match transport option")
                        if chosen.get("semantic_action_fingerprint") != sha256_value(path):
                            errors.append(f"label {index}: chosen action fingerprint was not recomputed from semantic path")
    return errors


def _opponent_labels_for_group(
    group: dict[str, Any], child_results: list[dict[str, Any]],
    root_action_keys: list[dict[str, str]],
) -> list[dict[str, Any]]:
    action_rows = {
        (int(replicate["replicate_id"]), action["action_id"]): action
        for replicate in group.get("replicates", [])
        for action in replicate.get("actions", [])
    }
    root_key_map = {
        item["action_id"]: item["semantic_equivalence_key"]
        for item in root_action_keys
        if item.get("state_group_id") == group["state_group_id"]
    }
    labels: list[dict[str, Any]] = []
    for result in child_results:
        label = result.get("opponent_transition")
        if not isinstance(label, dict):
            label = _new_opponent_transition_label(int(group["root_player"]))
            label["error"] = {"type": "MissingChildLabel", "message": "worker omitted transition label"}
        row = action_rows.get((int(result["particle_index"]), result["action_id"]))
        if row is None:
            raise ScheduleError("opponent label has no matching dataset branch")
        root_key = root_key_map.get(result["action_id"])
        if root_key is None:
            raise ScheduleError("opponent label has no matching root equivalence key")
        item = json.loads(json.dumps(label))
        item.update({
            "state_group_id": group["state_group_id"],
            "replicate_id": int(result["particle_index"]),
            "particle_id": result["particle_id"],
            "action_id": result["action_id"],
            "root_player": int(group["root_player"]),
            "root_action_semantic_fingerprint": row["semantic_action_fingerprint"],
            "root_action_semantic_equivalence_key": root_key,
        })
        labels.append(item)
    return labels


def _build_opponent_sidecar(
    config: dict[str, Any], dataset: dict[str, Any], dataset_path: Path,
    config_sha256: str, anchor: dict[str, Any], labels: list[dict[str, Any]],
    root_action_keys: list[dict[str, str]],
) -> dict[str, Any]:
    sidecar = {
        "schema_version": 1,
        "sidecar_kind": "RESTRICTED_OPPONENT_TRANSITION_LABELS",
        "run": {
            "run_id": dataset["run"]["run_id"],
            "source_commit": config["source_commit"],
            "config_sha256": config_sha256,
            "profile": OPPONENT_TRANSITION_PROFILE,
        },
        "dataset_binding": {
            "dataset_path": str(dataset_path.resolve().relative_to(ROOT)),
            "dataset_sha256": sha256_file(dataset_path),
            "state_group_ids": sorted({item["state_group_id"] for item in labels}),
        },
        "public_projection_binding": _public_projection_binding(
            dataset, config["assets"]["public_projector"],
        ),
        "root_action_keys": root_action_keys,
        "provenance": {
            "anchor_baseline_id": anchor["baseline_id"],
            "opponent_policy_id": anchor["policy_id"],
            "opponent_policy_sha256": anchor["receipt_sha256"],
            "opponent_deck_sha256": anchor["deck_sha256"],
            "split_role": "LABEL_AUDIT_METADATA_ONLY",
        },
        "firewall": {
            "consumer": "LABEL_AUDIT_ONLY",
            "model_facing_fields_present": False,
            "public_root_source": "G2_PROJECTED_PUBLIC_ONLY",
            "opponent_view_retention": "NONE",
            "opponent_legal_set_retention": "SEMANTIC_LABEL_AUDIT_ONLY",
            "post_evidence_source": "NONE_FIRST_OPPONENT_ACTION_ONLY",
            "ppo_rollout_eligible": False,
        },
        "labels": labels,
    }
    errors = _validate_opponent_sidecar_shape(sidecar)
    if errors:
        raise ScheduleError(f"restricted opponent sidecar validation failed: {errors}")
    return sidecar


def _artifact_entry(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise ScheduleError(f"manifest artifact is missing: {resolved}")
    return {
        "path": str(resolved.relative_to(ROOT)),
        "bytes": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }


def _write_run_manifest(
    run_dir: Path,
    *,
    run_id: str,
    root_ids: list[str],
    config_path: Path,
    config_sha256: str,
    git_dirty_sha256: str,
    worker_outputs: list[Path],
    execution_output: Path,
    dataset_outputs: list[Path],
    created_utc: str,
    finished_utc: str,
    label_sidecar_outputs: list[Path] | None = None,
) -> dict[str, Any]:
    if not root_ids:
        raise ScheduleError("manifest requires at least one root_id")
    manifest_path = run_dir / "run-manifest.json"
    seal_path = run_dir / "run-manifest.sha256"
    worker_entries = [_artifact_entry(path) for path in worker_outputs]
    dataset_entries = [_artifact_entry(path) for path in dataset_outputs]
    label_entries = [_artifact_entry(path) for path in (label_sidecar_outputs or [])]
    artifacts = {
        "worker_outputs": worker_entries,
        "worker_output": worker_entries[0] if len(worker_entries) == 1 else None,
        "execution_output": _artifact_entry(execution_output),
        "dataset_outputs": dataset_entries,
        "dataset_output": dataset_entries[0] if len(dataset_entries) == 1 else None,
        "opponent_transition_label_outputs": label_entries,
        "opponent_transition_label_output": label_entries[0] if len(label_entries) == 1 else None,
        "collector": _artifact_entry(Path(__file__).resolve()),
        "projector": _artifact_entry(PROJECTOR),
        "dataset_schema": _artifact_entry(DATASET_SCHEMA),
        "opponent_transition_label_schema": _artifact_entry(OPPONENT_LABEL_SCHEMA),
        "bc_trunk_checkpoint": _artifact_entry(BC_TRUNK_PATH),
        "config": _artifact_entry(config_path),
    }
    manifest = {
        "schema_version": 1,
        "status": "SEALED_DIGESTS_ONLY",
        "filesystem_immutability": "NOT_CLAIMED",
        "seal_method": "SHA256_MANIFEST_SIDECAR",
        "run_id": run_id,
        "root_id": root_ids[0] if len(root_ids) == 1 else None,
        "root_ids": root_ids,
        "created_utc": created_utc,
        "finished_utc": finished_utc,
        "config_sha256": config_sha256,
        "git_dirty_sha256": git_dirty_sha256,
        "source_commit": _canonical_source_commit(),
        "dataset_binding": {
            "run_id": run_id,
            "root_ids": root_ids,
            "config_sha256": config_sha256,
            "dataset_paths": [entry["path"] for entry in dataset_entries],
            "opponent_transition_label_paths": [entry["path"] for entry in label_entries],
        },
        "artifacts": artifacts,
        "seal_sidecar": str(seal_path.relative_to(ROOT)),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest_sha256 = sha256_file(manifest_path)
    seal_path.write_text(f"{manifest_sha256}  {manifest_path.name}\n", encoding="utf-8")
    return {
        "manifest_path": str(manifest_path.relative_to(ROOT)),
        "manifest_seal_path": str(seal_path.relative_to(ROOT)),
        "manifest_sha256": manifest_sha256,
        "filesystem_immutability": "NOT_CLAIMED_DIGEST_ONLY",
    }


def _dataset_from_group(config: dict[str, Any], group: dict[str, Any], anchor: dict[str, Any]) -> dict[str, Any]:
    learner = config["learner_policy"]
    run_id = config.get("_run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ScheduleError("dataset emission requires coordinator-bound run_id")
    return {
        "schema_version": 1,
        "run": {
            "run_id": run_id,
            "source_commit": config["source_commit"],
            "engine_sha256": config["assets"]["engine"]["sha256"],
            "card_data_sha256": config["assets"]["card_data"]["sha256"],
            "action_schema_sha256": config["assets"]["action_observation_contract"]["action_schema_sha256"],
            "observation_schema_sha256": config["assets"]["action_observation_contract"]["observation_schema_sha256"],
            "model_schema_sha256": config["assets"]["model_schema_sha256"],
            "g2_package_sha256": config["assets"]["g2_checkpoint"]["sha256"],
            "bc_trunk_checkpoint_sha256": BC_TRUNK_CHECKPOINT_SHA256,
            "bc_trunk_state_sha256": BC_TRUNK_STATE_SHA256,
            "trunk_mode": TRUNK_MODE,
            "self_deck_sha256": learner["deck_sha256"],
            "opponent_deck_sha256": anchor["deck_sha256"],
            "continuation_policy_id": learner["policy_id"],
            "continuation_policy_sha256": learner["receipt_sha256"],
            "opponent_policy_id": anchor["policy_id"],
            "opponent_policy_sha256": anchor["receipt_sha256"],
            "determinization_contract": {
                "hidden_state_source": "LABEL_ONLY_NOT_PUBLIC_INPUT",
                "world_sampling": "PAIRED_SHARED_WORLD",
                "engine_rng": "SYSTEM_ENTROPY_UNCONTROLLED",
                "per_replicate_identity": True,
            },
            "label_firewall": "COUNTERFACTUAL_NATIVE_ONLY_NOT_PPO_ROLLOUT",
        },
        "state_groups": [group],
    }


def _execute_full(config: dict[str, Any], fixture: Path) -> int:
    """Coordinator for a future explicitly authorized full run.

    This branch is unreachable with the checked-in schedules.  Keeping the
    authorization and mode checks adjacent to the coordinator prevents a
    preflight flag or an accidental config typo from starting a full rollout.
    """
    validation = validate_schedule(config, fixture)
    if config.get("authorized") is not True or config.get("mode") != "NATIVE_FULL_AUTHORIZED":
        print(json.dumps({
            "status": "REFUSED",
            "reason": "schedule authorized=false or mode is not NATIVE_FULL_AUTHORIZED",
            "schedule_validation": validation,
            "native_launches": 0,
        }, sort_keys=True))
        return 2
    schedule = config["state_schedule"]
    state_count = schedule["root_state_count"]
    assignments = _assignment_plan(config)
    if len(assignments) != state_count:
        raise ScheduleError("anchor-cell state counts do not equal root_state_count")
    config_path = Path(config["_config_path"])
    config_sha256 = sha256_file(config_path)
    run_id = _new_run_id()
    config["_run_id"] = run_id
    run_dir = Path(__file__).resolve().parent / "runs" / f"full-{run_id}"
    if run_dir.exists():
        raise ScheduleError(f"refusing stale full-run directory: {run_dir}")
    run_dir.mkdir(parents=True)
    worker_dir = run_dir / "workers"
    dataset_dir = run_dir / "datasets"
    worker_dir.mkdir()
    dataset_dir.mkdir()
    execution_output = run_dir / "full-execution.json"
    created_utc = datetime.now(timezone.utc).isoformat()
    git_dirty_sha256 = _git_dirty_sha256()
    groups_by_anchor: dict[str, list[dict[str, Any]]] = {}
    labels_by_anchor: dict[str, list[dict[str, Any]]] = {}
    root_keys_by_anchor: dict[str, list[dict[str, str]]] = {}
    reports: list[dict[str, Any]] = []
    worker_outputs: list[Path] = []
    dataset_outputs: list[Path] = []
    label_sidecar_outputs: list[Path] = []
    root_ids: list[str] = []
    status = "RUNNING"
    error_value: dict[str, str] | None = None
    run_deadline = time.monotonic() + float(schedule.get("max_wall_seconds", MAX_WORKER_SECONDS * state_count))
    try:
        for state_index, assignment in enumerate(assignments):
            if time.monotonic() >= run_deadline:
                raise TimeoutError("full collection wall cap reached before next root")
            anchor_id = assignment["anchor_id"]
            slot = assignment["learner_slot"]
            root_id = sha256_value({"run_id": run_id, **assignment})
            root_ids.append(root_id)
            worker_output = worker_dir / f"worker-{state_index:02d}-{anchor_id}.json"
            worker_dirty_sha256 = _git_dirty_sha256()
            report = _start_worker(
                config_path, config, worker_output, state_index, anchor_id,
                slot, run_id, root_id, config_sha256,
                worker_dirty_sha256, preflight=False, complete_root=False,
                timeout_seconds=max(1.0, run_deadline - time.monotonic()),
            )
            reports.append(report)
            if worker_output.is_file():
                worker_outputs.append(worker_output)
            if report.get("status") != "PASS_COMPLETE":
                raise ScheduleError(f"full worker {state_index} did not complete: {report.get('status')}")
            _validate_gate1_trunk_binding(report)
            groups_by_anchor.setdefault(anchor_id, []).append(report["state_group"])
            root_keys_by_anchor.setdefault(anchor_id, []).extend(
                report.get("root_action_equivalence_keys", [])
            )
            labels_by_anchor.setdefault(anchor_id, []).extend(
                _opponent_labels_for_group(
                    report["state_group"], report.get("child_results", []),
                    report.get("root_action_equivalence_keys", []),
                )
            )
        for anchor_id, groups in groups_by_anchor.items():
            anchor = next(item for item in config["frozen_anchor_policies"] if item["baseline_id"] == anchor_id)
            dataset = _dataset_from_group(config, groups[0], anchor)
            if dataset["run"]["run_id"] != run_id:
                raise ScheduleError("full dataset run_id is not coordinator-bound")
            dataset["state_groups"] = groups
            errors = _validate_dataset_shape(dataset)
            if errors:
                raise ScheduleError(f"full dataset schema/completeness validation failed: {errors}")
            output = dataset_dir / f"counterfactual-action-dataset-{anchor_id}.json"
            output.write_text(json.dumps(dataset, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            dataset_outputs.append(output)
            if config["state_schedule"]["profile"] == OPPONENT_TRANSITION_PROFILE:
                label_output = dataset_dir / f"opponent-transition-labels-{anchor_id}.json"
                label_sidecar = _build_opponent_sidecar(
                    config, dataset, output, config_sha256, anchor,
                    labels_by_anchor[anchor_id], root_keys_by_anchor[anchor_id],
                )
                label_output.write_text(
                    json.dumps(label_sidecar, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                )
                label_sidecar_outputs.append(label_output)
        status = "PASS_COMPLETE"
    except Exception as error:
        status = "FAIL"
        error_value = {"type": type(error).__name__, "message": str(error)[:1000]}
    finished_utc = datetime.now(timezone.utc).isoformat()
    execution_report: dict[str, Any] = {
        "status": status,
        "mode": "NATIVE_FULL_AUTHORIZED",
        "created_utc": created_utc,
        "finished_utc": finished_utc,
        "run_id": run_id,
        "root_ids": root_ids,
        "config_sha256": config_sha256,
        "git_dirty_sha256": git_dirty_sha256,
        "config_path": str(config_path.relative_to(ROOT)),
        "execution_output": str(execution_output.relative_to(ROOT)),
        "worker_outputs": [str(path.relative_to(ROOT)) for path in worker_outputs],
        "dataset_outputs": [str(path.relative_to(ROOT)) for path in dataset_outputs],
        "opponent_transition_label_outputs": [str(path.relative_to(ROOT)) for path in label_sidecar_outputs],
        "native_launches": sum(report.get("native_launches", 0) for report in reports),
        "continuation_rollouts": sum(report.get("counters", {}).get("continuation_rollouts", 0) for report in reports),
        "max_wall_seconds": schedule.get("max_wall_seconds"),
        "anchors": sorted(groups_by_anchor),
        "workers": reports,
        "full_schedule_authorized": True,
        "full_schedule_launched": status == "PASS_COMPLETE" or bool(reports),
        "filesystem_immutability": "NOT_CLAIMED_DIGEST_ONLY",
        "manifest": {
            "path": str((run_dir / "run-manifest.json").relative_to(ROOT)),
            "seal_sidecar": str((run_dir / "run-manifest.sha256").relative_to(ROOT)),
            "status": "SEALED_DIGESTS_ONLY",
        },
    }
    if error_value is not None:
        execution_report["error"] = error_value
    execution_output.write_text(json.dumps(execution_report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = _write_run_manifest(
        run_dir,
        run_id=run_id,
        root_ids=root_ids or [sha256_value({"run_id": run_id, "state_count": state_count})],
        config_path=config_path,
        config_sha256=config_sha256,
        git_dirty_sha256=git_dirty_sha256,
        worker_outputs=worker_outputs,
        execution_output=execution_output,
        dataset_outputs=dataset_outputs,
        created_utc=created_utc,
        finished_utc=finished_utc,
        label_sidecar_outputs=label_sidecar_outputs,
    )
    execution_report["manifest_seal_sha256"] = manifest["manifest_sha256"]
    print(json.dumps(execution_report, sort_keys=True))
    return 0 if status == "PASS_COMPLETE" else 1


def _mark_preflight_blocked(report: dict[str, Any], error: Exception) -> None:
    report.update({
        "status": "BLOCKED",
        "dataset_schema_status": "BLOCKED_EMISSION",
        "dataset_schema_errors": [{"type": type(error).__name__, "message": str(error)[:1000]}],
        "dataset_emitted": False,
        "full_schedule_launched": False,
        "error": {"type": type(error).__name__, "message": str(error)[:1000]},
    })


def _execute_complete_root_preflight(config: dict[str, Any], config_path: Path) -> int:
    anchor_id = config["state_schedule"]["anchor_cells"][0]["anchor"]
    config_sha256 = sha256_file(config_path)
    run_id = _new_run_id()
    config["_run_id"] = run_id
    root_id = sha256_value({
        "run_id": run_id,
        "state_index": 0,
        "anchor_id": anchor_id,
        "learner_slot": 0,
    })
    run_dir = Path(__file__).resolve().parent / "runs" / run_id
    if run_dir.exists():
        raise ScheduleError(f"refusing stale run directory: {run_dir}")
    run_dir.mkdir(parents=True)
    git_dirty_sha256 = _git_dirty_sha256()
    worker_output = run_dir / "worker.json"
    execution_output = run_dir / "preflight-execution.json"
    dataset_output: Path | None = None
    label_sidecar_output: Path | None = None
    created_utc = datetime.now(timezone.utc).isoformat()
    worker: dict[str, Any] = {"status": "NOT_STARTED", "native_launches": 0}
    report: dict[str, Any] = {
        "status": "BLOCKED",
        "mode": "PREFLIGHT_COMPLETE_ROOT",
        "created_utc": created_utc,
        "finished_utc": None,
        "run_id": run_id,
        "root_id": root_id,
        "config_sha256": config_sha256,
        "git_dirty_sha256": git_dirty_sha256,
        "config_path": str(config_path.relative_to(ROOT)),
        "worker_output": str(worker_output.relative_to(ROOT)),
        "execution_output": str(execution_output.relative_to(ROOT)),
        "native_launches": 0,
        "required_continuation_rollouts": None,
        "opponent_transition_label_output": None,
        "preflight_scope": "ALL legal root actions x exactly 2 shared particles; max 20 branches",
        "coverage_scope": (
            "MAIN_SINGLE_CHOICE_ONLY; COMPOUND_AND_OPTIONAL_STOP_REFUSED_PENDING_SEPARATE_MECHANICS_GATE"
        ),
        "worker": worker,
        "dataset_schema_status": "NOT_STARTED",
        "dataset_schema_errors": [],
        "dataset_emitted": False,
        "full_schedule_authorized": False,
        "full_schedule_launched": False,
        "filesystem_immutability": "NOT_CLAIMED_DIGEST_ONLY",
        "manifest": {
            "path": str((run_dir / "run-manifest.json").relative_to(ROOT)),
            "seal_sidecar": str((run_dir / "run-manifest.sha256").relative_to(ROOT)),
            "status": "PENDING",
        },
    }
    try:
        worker = _start_worker(
            config_path, config, worker_output, 0, anchor_id, 0,
            run_id, root_id, config_sha256, git_dirty_sha256,
            preflight=False, complete_root=True,
        )
        report["worker"] = worker
        report["native_launches"] = worker.get("native_launches", 0)
        worker_ok = worker.get("status") == "PASS_COMPLETE"
        if not worker_ok:
            report["dataset_schema_status"] = "BLOCKED_WORKER"
            report["dataset_schema_errors"] = [worker.get("error", worker.get("status", "worker failed"))]
        else:
            _validate_gate1_trunk_binding(worker)
            anchor = next(item for item in config["frozen_anchor_policies"] if item["baseline_id"] == anchor_id)
            dataset = _dataset_from_group(config, worker["state_group"], anchor)
            if dataset["run"]["run_id"] != run_id:
                raise ScheduleError("dataset run_id is not coordinator-bound")
            errors = _validate_dataset_shape(dataset)
            if errors:
                raise ScheduleError(f"complete-root dataset schema validation failed: {errors}")
            dataset_output = run_dir / "complete-root-dataset.json"
            dataset_output.write_text(json.dumps(dataset, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            if config["state_schedule"]["profile"] == OPPONENT_TRANSITION_PROFILE:
                label_sidecar_output = run_dir / "opponent-transition-labels.json"
                labels = _opponent_labels_for_group(
                    worker["state_group"], worker.get("child_results", []),
                    worker.get("root_action_equivalence_keys", []),
                )
                label_sidecar = _build_opponent_sidecar(
                    config, dataset, dataset_output, config_sha256, anchor, labels,
                    worker.get("root_action_equivalence_keys", []),
                )
                label_sidecar_output.write_text(
                    json.dumps(label_sidecar, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                )
                report["opponent_transition_label_output"] = str(label_sidecar_output.relative_to(ROOT))
            report["required_continuation_rollouts"] = worker["counters"]["continuation_rollouts"]
            report["dataset_schema_status"] = "PASS"
            report["dataset_schema_errors"] = []
            report["dataset_emitted"] = True
            report["dataset_output"] = str(dataset_output.relative_to(ROOT))
            report["status"] = "PASS_EXECUTION"
    except Exception as error:
        report["worker"] = worker
        _mark_preflight_blocked(report, error)

    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    try:
        execution_output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except Exception as error:
        _mark_preflight_blocked(report, error)
        try:
            execution_output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        except Exception:
            pass
    try:
        manifest = _write_run_manifest(
            run_dir,
            run_id=run_id,
            root_ids=[root_id],
            config_path=config_path,
            config_sha256=config_sha256,
            git_dirty_sha256=git_dirty_sha256,
            worker_outputs=[worker_output] if worker_output.is_file() else [],
            execution_output=execution_output,
            dataset_outputs=[dataset_output] if dataset_output is not None and dataset_output.is_file() else [],
            label_sidecar_outputs=[label_sidecar_output] if label_sidecar_output is not None and label_sidecar_output.is_file() else [],
            created_utc=created_utc,
            finished_utc=report["finished_utc"],
        )
        report["manifest"]["status"] = "SEALED_DIGESTS_ONLY"
        report["manifest_seal_sha256"] = manifest["manifest_sha256"]
    except Exception as error:
        _mark_preflight_blocked(report, error)
        report["manifest"]["status"] = "BLOCKED_MANIFEST"
        try:
            execution_output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        except Exception:
            pass
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "PASS_EXECUTION" else 1


def _self_check() -> int:
    """Exercise refusal, binding, cleanup, and schema checks without native imports."""
    schedule_config = load_json(DEFAULT_CONFIG)
    schedule_config["_config_path"] = str(DEFAULT_CONFIG.resolve())
    # Existing declaration fixtures are intentionally reusable across source
    # commits; the real dry-run still validates the on-disk config binding.
    schedule_config["source_commit"] = _canonical_source_commit()

    def schedule_copy() -> dict[str, Any]:
        return json.loads(json.dumps(schedule_config))

    def expect_schedule_error(label: str, mutate: Any) -> None:
        candidate = schedule_copy()
        mutate(candidate)
        try:
            validate_schedule(candidate, DEFAULT_FIXTURE)
        except ScheduleError:
            return
        raise ScheduleError(f"schedule self-check did not reject {label}")

    for field in (
        "root_state_count", "replicates_per_action", "max_legal_actions_per_state",
        "max_continuation_rollouts",
    ):
        for value in (0, -1):
            expect_schedule_error(
                f"{field}={value}",
                lambda candidate, field=field, value=value: candidate["state_schedule"].__setitem__(field, value),
            )
    for value in (0, -1):
        expect_schedule_error(
            f"states_per_anchor={value}",
            lambda candidate, value=value: candidate["state_schedule"]["anchor_cells"][0].__setitem__("states", value),
        )
        expect_schedule_error(
            f"particles={value}",
            lambda candidate, value=value: candidate["hidden_worlds"].__setitem__("seeds_per_state", value),
        )
    expect_schedule_error(
        "duplicate candidate slots",
        lambda candidate: candidate["state_schedule"].__setitem__("candidate_player_slots", [0, 0]),
    )
    expect_schedule_error(
        "empty candidate slots",
        lambda candidate: candidate["state_schedule"].__setitem__("candidate_player_slots", []),
    )
    expect_schedule_error(
        "authorized dry-run mismatch",
        lambda candidate: (candidate.__setitem__("authorized", True), candidate.__setitem__("mode", "DRY_RUN_ONLY")),
    )
    expect_schedule_error(
        "unauthorized native mismatch",
        lambda candidate: (candidate.__setitem__("authorized", False), candidate.__setitem__("mode", "NATIVE_FULL_AUTHORIZED")),
    )
    expect_schedule_error(
        "stale source commit",
        lambda candidate: candidate.__setitem__("source_commit", "0" * 40),
    )
    expect_schedule_error(
        "non-MAIN selection type",
        lambda candidate: candidate["state_schedule"].__setitem__("selection_type_required", "CARD"),
    )
    expect_schedule_error(
        "non-MAIN selection context",
        lambda candidate: candidate["state_schedule"].__setitem__("selection_context_required", 1),
    )
    valid_binding = {
        "hashes": {
            "bc_trunk_checkpoint_sha256": BC_TRUNK_CHECKPOINT_SHA256,
            "bc_trunk_state_sha256": BC_TRUNK_STATE_SHA256,
            "bc_trunk_optimizer_steps": BC_TRUNK_OPTIMIZER_STEPS,
            "trunk_mode": TRUNK_MODE,
            "bc_trunk_frozen": True,
        }
    }
    _validate_gate1_trunk_binding(valid_binding)
    base_binding = json.loads(json.dumps(valid_binding))
    base_binding["hashes"]["bc_trunk_state_sha256"] = "531b799b29830954dce62cd7d1b455eb30d5189cf670158723ee01b3e2ed6ab0"
    try:
        _validate_gate1_trunk_binding(base_binding)
    except ScheduleError:
        pass
    else:
        raise ScheduleError("base G2 state self-check did not reject the untrained state")
    authorized_config = schedule_copy()
    authorized_config["authorized"] = True
    authorized_config["mode"] = "NATIVE_FULL_AUTHORIZED"
    authorized_validation = validate_schedule(authorized_config, DEFAULT_FIXTURE)
    if authorized_validation.get("authorized") is not True or authorized_validation.get("native_launches") != 0:
        raise ScheduleError("authorized-mode reachability self-check failed")

    scale_path = Path(__file__).resolve().parent / "gate1_schedule_scale64_v1.json"
    scale_config = load_json(scale_path)
    scale_config["_config_path"] = str(scale_path.resolve())
    scale_config["source_commit"] = _canonical_source_commit()
    scale_validation = validate_schedule(scale_config, DEFAULT_FIXTURE)
    if (
        scale_validation.get("profile") != SCALE64_PROFILE
        or scale_validation.get("root_states") != 64
        or len(scale_validation.get("assignment_plan", [])) != 64
        or scale_validation.get("max_continuation_rollouts") != 2560
        or scale_validation.get("max_wall_seconds") != 600
    ):
        raise ScheduleError("scale64 declaration self-check did not expand the exact root schedule")

    def expect_scale_schedule_error(label: str, mutate: Any) -> None:
        candidate = json.loads(json.dumps(scale_config))
        mutate(candidate)
        try:
            validate_schedule(candidate, DEFAULT_FIXTURE)
        except ScheduleError:
            return
        raise ScheduleError(f"scale64 self-check did not reject {label}")

    expect_scale_schedule_error(
        "wrong scale64 wall cap",
        lambda candidate: candidate["state_schedule"].__setitem__("max_wall_seconds", 599),
    )
    expect_scale_schedule_error(
        "wrong scale64 anchor allocation",
        lambda candidate: candidate["state_schedule"]["anchor_cells"][0].__setitem__("states", 10),
    )
    expect_scale_schedule_error(
        "missing scale64 MID window",
        lambda candidate: candidate["state_schedule"]["anchor_cells"][0]["candidate_windows"].pop(),
    )
    expect_scale_schedule_error(
        "scale64 seed policy that claims native determinism",
        lambda candidate: candidate["state_schedule"].__setitem__(
            "root_game_seed_policy", "EXPLICIT_SEED"
        ),
    )

    transition_path = Path(__file__).resolve().parent / "gate1_schedule_scale64_opponent_transition_v1.json"
    transition_config = load_json(transition_path)
    transition_config["_config_path"] = str(transition_path.resolve())
    transition_config["source_commit"] = _canonical_source_commit()
    transition_validation = validate_schedule(transition_config, DEFAULT_FIXTURE)
    if (
        transition_validation.get("profile") != OPPONENT_TRANSITION_PROFILE
        or transition_validation.get("root_states") != 64
        or transition_validation.get("replicates_per_action") != 4
        or transition_validation.get("max_continuation_rollouts") != 2560
        or transition_validation.get("max_wall_seconds") != 600
        or transition_validation.get("max_root_acquisition_attempts") != 8
        or transition_validation.get("authorized") is not False
    ):
        raise ScheduleError("opponent-transition ceiling declaration self-check failed")

    def expect_transition_schedule_error(label: str, mutate: Any) -> None:
        candidate = json.loads(json.dumps(transition_config))
        mutate(candidate)
        try:
            validate_schedule(candidate, DEFAULT_FIXTURE)
        except ScheduleError:
            return
        raise ScheduleError(f"opponent-transition self-check did not reject {label}")

    expect_transition_schedule_error(
        "opponent-transition authorization",
        lambda candidate: (candidate.__setitem__("authorized", True), candidate.__setitem__("mode", "NATIVE_FULL_AUTHORIZED")),
    )
    expect_transition_schedule_error(
        "opponent-transition retry cap",
        lambda candidate: candidate["state_schedule"].__setitem__("max_root_acquisition_attempts", 7),
    )
    expect_transition_schedule_error(
        "opponent-transition sidecar schema hash",
        lambda candidate: candidate["opponent_transition_label_schema"].__setitem__("sha256", "0" * 64),
    )

    scale256_path = Path(__file__).resolve().parent / "gate1_schedule_scale256_v1_authorized_compat_sys_v1.json"
    scale256_config = load_json(scale256_path)
    scale256_config["_config_path"] = str(scale256_path.resolve())
    scale256_config["source_commit"] = _canonical_source_commit()
    scale256_validation = validate_schedule(scale256_config, DEFAULT_FIXTURE)
    if (
        scale256_validation.get("profile") != SCALE256_PROFILE
        or scale256_validation.get("root_states") != 256
        or len(scale256_validation.get("assignment_plan", [])) != 256
        or scale256_validation.get("max_continuation_rollouts") != 10240
        or scale256_validation.get("max_wall_seconds") != 1800
        or scale256_validation.get("max_root_acquisition_attempts") != 8
    ):
        raise ScheduleError("scale256 declaration self-check did not expand the exact root schedule")

    def expect_scale256_schedule_error(label: str, mutate: Any) -> None:
        candidate = json.loads(json.dumps(scale256_config))
        mutate(candidate)
        try:
            validate_schedule(candidate, DEFAULT_FIXTURE)
        except ScheduleError:
            return
        raise ScheduleError(f"scale256 self-check did not reject {label}")

    expect_scale256_schedule_error(
        "wrong scale256 wall cap",
        lambda candidate: candidate["state_schedule"].__setitem__("max_wall_seconds", 1799),
    )
    expect_scale256_schedule_error(
        "wrong scale256 anchor allocation",
        lambda candidate: candidate["state_schedule"]["anchor_cells"][0].__setitem__("states", 42),
    )
    expect_scale256_schedule_error(
        "scale256 branch cap below worst case",
        lambda candidate: candidate["state_schedule"].__setitem__("max_continuation_rollouts", 10239),
    )
    expect_scale256_schedule_error(
        "scale256 root acquisition retry cap changed",
        lambda candidate: candidate["state_schedule"].__setitem__("max_root_acquisition_attempts", 7),
    )

    with TemporaryDirectory(
        prefix="counterfactual-q-self-check-",
        dir=Path(__file__).resolve().parent,
    ) as directory:
        temp_dir = Path(directory)
        stale = temp_dir / "stale-worker.json"
        stale.write_text("stale\n", encoding="utf-8")
        try:
            _start_worker(
                DEFAULT_CONFIG, {}, stale, 0, "anchor", 0,
                "run", "root", "config", "dirty", preflight=True,
            )
        except ScheduleError:
            pass
        else:
            raise ScheduleError("stale-output self-check did not refuse")
        try:
            _validate_worker_binding(
                {"run_id": "wrong", "root_id": "root", "config_sha256": "config", "git_dirty_sha256": "dirty"},
                "run", "root", "config", "dirty",
            )
        except ScheduleError:
            pass
        else:
            raise ScheduleError("worker-binding self-check did not refuse")

        config_path = temp_dir / "config.json"
        config_path.write_text("{}\n", encoding="utf-8")
        try:
            _worker(
                {"_config_path": str(config_path)}, temp_dir / "worker.json", 0,
                "anchor", 0, "run", "root", "0" * 64, "dirty", preflight=True,
            )
        except ScheduleError as error:
            if "config SHA-256" not in str(error):
                raise
        else:
            raise ScheduleError("config-mismatch self-check did not refuse")

        descendant_code = (
            "import os, signal, time; "
            "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            "os.fork(); time.sleep(60)"
        )
        process = subprocess.Popen([sys.executable, "-c", descendant_code], start_new_session=True)
        time.sleep(0.2)
        cleanup = _terminate_process_group(process.pid)
        process.wait(timeout=2)
        if process.poll() is None or not cleanup["kill_sent"] or not cleanup["group_gone"]:
            raise ScheduleError(f"process-group cleanup self-check failed: {cleanup}")

        worker_artifact = temp_dir / "worker.json"
        execution_artifact = temp_dir / "execution.json"
        dataset_artifact = temp_dir / "dataset.json"
        worker_artifact.write_text("worker\n", encoding="utf-8")
        execution_artifact.write_text("execution\n", encoding="utf-8")
        dataset_artifact.write_text("dataset\n", encoding="utf-8")
        manifest = _write_run_manifest(
            temp_dir,
            run_id="self-check-run",
            root_ids=["self-check-root"],
            config_path=config_path,
            config_sha256=sha256_file(config_path),
            git_dirty_sha256="0" * 64,
            worker_outputs=[worker_artifact],
            execution_output=execution_artifact,
            dataset_outputs=[dataset_artifact],
            created_utc=datetime.now(timezone.utc).isoformat(),
            finished_utc=datetime.now(timezone.utc).isoformat(),
        )
        sealed_value = manifest["manifest_sha256"]
        sidecar_value = Path(ROOT / manifest["manifest_seal_path"]).read_text(encoding="utf-8").split()[0]
        if sealed_value != sidecar_value:
            raise ScheduleError("manifest sidecar self-check hash mismatch")

    zero_hash = "0" * 64
    from ptcg_rl.g1.semantic import AREA
    if AREA.get("HAND") != SEMANTIC_HAND_ZONE:
        raise ScheduleError("collector hand zone is not bound to semantic AREA['HAND']")
    option = {
        "option_type": 0, "source_kind": "NONE", "target_kind": "NONE",
        "choice_role": "CHOICE", "source_ref": None, "target_ref": None,
        "is_stop": False, "semantic_fingerprint": zero_hash,
    }
    action_id = "schema-self-check-action"
    synthetic_hidden = [0.125] * 160
    dataset = {
        "schema_version": 1,
        "run": {
            "run_id": "schema-self-check", "source_commit": "0123456",
            "engine_sha256": zero_hash, "card_data_sha256": zero_hash,
            "action_schema_sha256": zero_hash, "observation_schema_sha256": zero_hash,
            "model_schema_sha256": zero_hash, "self_deck_sha256": zero_hash,
            "g2_package_sha256": "4dfba2adb9f97607cfa5dabadba075236bb7aae51eafab264584e947feae3827",
            "bc_trunk_checkpoint_sha256": BC_TRUNK_CHECKPOINT_SHA256,
            "bc_trunk_state_sha256": BC_TRUNK_STATE_SHA256,
            "trunk_mode": TRUNK_MODE,
            "opponent_deck_sha256": zero_hash, "continuation_policy_id": "learner",
            "continuation_policy_sha256": zero_hash, "opponent_policy_id": "anchor",
            "opponent_policy_sha256": zero_hash,
            "determinization_contract": {
                "hidden_state_source": "LABEL_ONLY_NOT_PUBLIC_INPUT",
                "world_sampling": "PAIRED_SHARED_WORLD",
                "engine_rng": "SYSTEM_ENTROPY_UNCONTROLLED",
                "per_replicate_identity": True,
            },
            "label_firewall": "COUNTERFACTUAL_NATIVE_ONLY_NOT_PPO_ROLLOUT",
        },
        "state_groups": [{
            "state_group_id": "schema-self-check-group", "split_group_key": "schema-self-check-split",
            "public_state_sha256": zero_hash, "acting_player": 0, "root_player": 0,
            "request": {
                "request_id": "schema-self-check-request", "selection_seq": 0,
                "selection_type": 0, "selection_context": 0, "min_count": 1,
                "max_count": 1, "ordering": "ORDERED", "options": [option],
            },
            "public_tensor": {
                "schema_version": 1,
                "model_schema_sha256": "61f6f71008c847b03bbab913d767da2c6bc6469311a0fe7249f3d03ee512bf68",
                "feature_source": "G2_PROJECTED_PUBLIC_ONLY",
                "projected_decision": {
                    "schema_version": 1, "model_input": {}, "transport_sidecar": {},
                },
                "history_tokens": [{
                    "history_schema_version": 1,
                    "history_source": "RECORDED_PUBLIC_GRU_HIDDEN",
                    "history_steps": 1,
                    "prefix_digest": zero_hash,
                    "model_schema_sha256": "61f6f71008c847b03bbab913d767da2c6bc6469311a0fe7249f3d03ee512bf68",
                    "public_hidden": {"dtype": "float32", "shape": [1, 160], "values": [synthetic_hidden]},
                }],
                "public_only": True,
                "raw_observation_retained": False, "forbidden_actor_features_absent": True,
                "prefix_provenance": {
                    "source": "ACTOR_OWNED_PUBLIC_PREFIX",
                    "prefix_digest": zero_hash,
                    "history_schema_version": 1,
                    "history_source": "RECORDED_PUBLIC_GRU_HIDDEN",
                    "history_steps": 1,
                    "initial_hidden_source": "RECORDED_PUBLIC_GRU_HIDDEN",
                    "model_schema_sha256": "61f6f71008c847b03bbab913d767da2c6bc6469311a0fe7249f3d03ee512bf68",
                    "full_public_prefix_retained": False,
                },
            },
            "legal_action_count": 1, "enumerated_action_count": 1,
            "action_enumeration_complete": True, "compound_coverage": "SINGLE_CHOICE",
            "stop_tested": False,
            "replicates": [{
                "replicate_id": 0, "determinization_id": "particle", "determinization_seed": 1,
                "engine_rng": "SYSTEM_ENTROPY_UNCONTROLLED", "world_independence": "PAIRED_SHARED_WORLD",
                "actions": [{
                    "action_id": action_id, "semantic_action_fingerprint": zero_hash,
                    "semantic_path": [option], "transport_original_indices": [0],
                    "terminal_engine_result": {"winner_player": 0, "is_draw": False},
                    "reward_for_actor": 1, "completed": True, "continuation_steps": 1,
                    "first_opponent_response": None, "fallback_used": False,
                    "nonfinite": False, "error": None,
                }],
            }],
            "action_aggregates": [{
                "action_id": action_id, "replicate_count": 1,
                "wdl_counts": {"W": 1, "D": 0, "L": 0}, "mean_reward": 1,
                "reward_stderr": 0, "ci95_low": 1, "ci95_high": 1,
                "baseline_action_id": action_id, "advantage_vs_fallback": 0,
            }],
        }],
    }
    errors = _validate_dataset_shape(dataset)
    if errors:
        raise ScheduleError(f"schema-valid projection self-check failed: {errors}")
    sidecar_option = {**option, "original_index": 0, "semantic_equivalence_key": zero_hash}
    synthetic_sidecar = {
        "schema_version": 1,
        "sidecar_kind": "RESTRICTED_OPPONENT_TRANSITION_LABELS",
        "run": {
            "run_id": "schema-self-check",
            "source_commit": _canonical_source_commit(),
            "config_sha256": zero_hash,
            "profile": OPPONENT_TRANSITION_PROFILE,
        },
        "dataset_binding": {
            "dataset_path": "scratch/dataset.json",
            "dataset_sha256": zero_hash,
            "state_group_ids": ["schema-self-check-group"],
        },
        "public_projection_binding": {
            "projector_path": ".chatgpt/tmp/outcome-ranker/project_public_state.py",
            "projector_sha256": zero_hash,
            "model_schema_sha256": "61f6f71008c847b03bbab913d767da2c6bc6469311a0fe7249f3d03ee512bf68",
            "groups": [{
                "state_group_id": "schema-self-check-group",
                "public_state_sha256": zero_hash,
                "public_projection_sha256": sha256_value(dataset["state_groups"][0]["public_tensor"]["projected_decision"]),
                "history_prefix_digest": zero_hash,
                "history_tokens_sha256": sha256_value(dataset["state_groups"][0]["public_tensor"]["history_tokens"]),
            }],
        },
        "root_action_keys": [{
            "state_group_id": "schema-self-check-group",
            "action_id": action_id,
            "semantic_equivalence_key": zero_hash,
        }],
        "provenance": {
            "anchor_baseline_id": "audit-anchor",
            "opponent_policy_id": "audit-policy",
            "opponent_policy_sha256": zero_hash,
            "opponent_deck_sha256": zero_hash,
            "split_role": "LABEL_AUDIT_METADATA_ONLY",
        },
        "firewall": {
            "consumer": "LABEL_AUDIT_ONLY",
            "model_facing_fields_present": False,
            "public_root_source": "G2_PROJECTED_PUBLIC_ONLY",
            "opponent_view_retention": "NONE",
            "opponent_legal_set_retention": "SEMANTIC_LABEL_AUDIT_ONLY",
            "post_evidence_source": "NONE_FIRST_OPPONENT_ACTION_ONLY",
            "ppo_rollout_eligible": False,
        },
        "labels": [{
            "state_group_id": "schema-self-check-group",
            "replicate_id": 0,
            "particle_id": "particle",
            "action_id": action_id,
            "root_player": 0,
            "opponent_player": 1,
            "root_action_semantic_fingerprint": zero_hash,
            "root_action_semantic_equivalence_key": zero_hash,
            "status": "OBSERVED",
            "first_opponent_request": {
                "request_id": "opponent-request",
                "selection_seq": 1,
                "selection_type": 0,
                "selection_context": 0,
                "min_count": 1,
                "max_count": 1,
                "ordering": "UNORDERED",
                "option_count": 1,
                "options": [sidecar_option],
            },
            "chosen_action": {
                "transport_original_indices": [0],
                "semantic_path": [sidecar_option],
                "semantic_equivalence_key": zero_hash,
                "semantic_action_fingerprint": sha256_value([sidecar_option]),
            },
            "error": None,
        }],
    }
    sidecar_errors = _validate_opponent_sidecar_shape(synthetic_sidecar)
    if sidecar_errors:
        raise ScheduleError(f"restricted sidecar self-check failed: {sidecar_errors}")
    sidecar_with_model_field = json.loads(json.dumps(synthetic_sidecar))
    sidecar_with_model_field["labels"][0]["public_tensor"] = {}
    if not _validate_opponent_sidecar_shape(sidecar_with_model_field):
        raise ScheduleError("restricted sidecar model-input firewall did not reject public_tensor")
    sidecar_bad_status = json.loads(json.dumps(synthetic_sidecar))
    sidecar_bad_status["labels"][0]["chosen_action"] = None
    if not _validate_opponent_sidecar_shape(sidecar_bad_status):
        raise ScheduleError("restricted sidecar parity check did not reject incomplete OBSERVED label")
    sidecar_bad_transport = json.loads(json.dumps(synthetic_sidecar))
    sidecar_bad_transport["labels"][0]["chosen_action"]["transport_original_indices"] = [99]
    if not _validate_opponent_sidecar_shape(sidecar_bad_transport):
        raise ScheduleError("restricted sidecar parity check did not reject out-of-range transport index")
    sidecar_bad_fingerprint = json.loads(json.dumps(synthetic_sidecar))
    sidecar_bad_fingerprint["labels"][0]["chosen_action"]["semantic_action_fingerprint"] = "1" * 64
    if not _validate_opponent_sidecar_shape(sidecar_bad_fingerprint):
        raise ScheduleError("restricted sidecar parity check did not reject stale action fingerprint")
    blocked_report = {"status": "PASS_EXECUTION", "dataset_emitted": True}
    _mark_preflight_blocked(blocked_report, ScheduleError("synthetic emission failure"))
    if (
        blocked_report["status"] != "BLOCKED"
        or blocked_report["dataset_emitted"]
        or blocked_report["dataset_schema_status"] != "BLOCKED_EMISSION"
    ):
        raise ScheduleError("complete-root preflight failure path did not fail closed")

    fake_request = SimpleNamespace(
        selection_type=0, selection_context=0, min_count=1, max_count=1,
        ordering="UNORDERED", acting_player=1,
    )

    def fake_entity(key: str, owner: int, zone: int, position: int, card_id: int = 42) -> Any:
        return SimpleNamespace(
            entity_key=key, card_id=card_id, serial=999, owner=owner, zone=zone,
            position=position, parent_entity_key=None,
        )

    def fake_option(source: str, target: str | None = None, *, attack_id: int | None = None) -> Any:
        return SimpleNamespace(
            option_type=13 if attack_id is not None else 7,
            source_kind="ENTITY", target_kind="ENTITY" if target else "NONE",
            choice_role="ATTACK" if attack_id is not None else "PLAY",
            source_entity_key=source, target_entity_key=target,
            source_ref=source, target_ref=target, card_id=42, attack_id=attack_id,
            number=None, count=None, special_condition_type=None,
            original_index=0, semantic_fingerprint=zero_hash,
        )

    hand_a = fake_entity("p1:s1", 1, 2, 0)
    hand_b = fake_entity("p1:s2", 1, 2, 1)
    active = fake_entity("p1:s3", 1, 4, 0, 100)
    bench = fake_entity("p1:s4", 1, 5, 1, 100)
    public_view = SimpleNamespace(entities=(hand_a, hand_b, active, bench))
    hand_key_a = _opponent_semantic_equivalence_key(fake_request, fake_option(hand_a.entity_key), public_view, 0)
    hand_key_b = _opponent_semantic_equivalence_key(fake_request, fake_option(hand_b.entity_key), public_view, 0)
    if hand_key_a != hand_key_b:
        raise ScheduleError("hidden-hand duplicate aliases did not pool")
    serial_mutated = fake_option(hand_a.entity_key)
    serial_mutated.source_ref = "p1:s999"
    if _opponent_semantic_equivalence_key(fake_request, serial_mutated, public_view, 0) != hand_key_a:
        raise ScheduleError("opponent canonical key depends on serial-bearing transport reference")
    if _opponent_semantic_equivalence_key(fake_request, fake_option(active.entity_key), public_view, 0) == hand_key_a:
        raise ScheduleError("public endpoint was aliased with hidden-hand copy")
    if _opponent_semantic_equivalence_key(fake_request, fake_option(active.entity_key, bench.entity_key), public_view, 0) == _opponent_semantic_equivalence_key(fake_request, fake_option(active.entity_key), public_view, 0):
        raise ScheduleError("source/target endpoint distinction was lost")
    if _opponent_semantic_equivalence_key(fake_request, fake_option(active.entity_key, attack_id=1), public_view, 0) == _opponent_semantic_equivalence_key(fake_request, fake_option(active.entity_key, attack_id=2), public_view, 0):
        raise ScheduleError("attack distinction was lost")
    mirror_request = SimpleNamespace(**{**vars(fake_request), "acting_player": 0})
    mirror_hand = fake_entity("p0:s1", 0, 2, 0)
    mirror_view = SimpleNamespace(entities=(mirror_hand,))
    if _opponent_semantic_equivalence_key(mirror_request, fake_option(mirror_hand.entity_key), mirror_view, 1) != hand_key_a:
        raise ScheduleError("seat-mirrored opponent key changed owner class")
    projection_binding = _public_projection_binding(
        dataset,
        {"path": str(PROJECTOR.relative_to(ROOT)), "sha256": sha256_file(PROJECTOR)},
    )
    if (
        projection_binding["groups"][0]["public_projection_sha256"] != sha256_value(
            dataset["state_groups"][0]["public_tensor"]["projected_decision"]
        )
        or projection_binding["groups"][0]["history_prefix_digest"] != zero_hash
        or projection_binding["groups"][0]["history_tokens_sha256"] != sha256_value(
            dataset["state_groups"][0]["public_tensor"]["history_tokens"]
        )
    ):
        raise ScheduleError("public projection/history join self-check failed")
    print(json.dumps({
        "status": "PASS", "native_imports": 0, "stale_output_refused": True,
        "config_mismatch_refused": True, "worker_binding_refused": True,
        "schedule_positive_bounds_refused": True,
        "schedule_mode_pair_mismatch_refused": True,
        "stale_source_commit_refused": True,
        "selection_context_refused": True,
        "selection_type_refused": True,
        "base_g2_state_refused": True,
        "authorized_mode_reachable_without_native": True,
        "scale64_declaration_validated_without_native": True,
        "scale64_invalid_allocation_refused": True,
        "scale64_invalid_window_refused": True,
        "scale64_native_seed_claim_refused": True,
        "process_group_cleanup": True,
        "manifest_seal": True,
        "schema_valid_projection_shape": True,
        "opponent_transition_ceiling_validated_without_native": True,
        "opponent_transition_authorization_refused": True,
        "opponent_transition_sidecar_schema_valid": True,
        "opponent_transition_model_firewall_refused": True,
        "opponent_transition_incomplete_label_refused": True,
        "opponent_key_aliases_and_permutations": True,
        "opponent_key_endpoint_and_attack_distinction": True,
        "opponent_key_serial_rejected": True,
        "opponent_key_seat_mirror_normalized": True,
        "public_projection_history_join": True,
        "history_token_binding": True,
        "opponent_transport_index_and_fingerprint_refused": True,
        "complete_root_emission_failure_blocked": True,
        "semantic_hand_zone_bound": True,
    }, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--dry-run", action="store_true", help="validate only; this is the default")
    parser.add_argument("--execute-native", action="store_true", help="future full authorization gate")
    parser.add_argument("--preflight-child", action="store_true", help="run exactly four native search children")
    parser.add_argument(
        "--preflight-complete-root", action="store_true",
        help="run every legal single-select root action with two shared particles",
    )
    parser.add_argument("--self-check", action="store_true", help="run pure-stdlib refusal/schema self-checks")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--preflight-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--complete-root-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--output", type=Path, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--state-index", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--anchor-id", default="dragapult-ex", help=argparse.SUPPRESS)
    parser.add_argument("--learner-slot", type=int, choices=(0, 1), default=0, help=argparse.SUPPRESS)
    parser.add_argument("--run-id", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--root-id", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--config-sha256", default=None, help=argparse.SUPPRESS)
    parser.add_argument("--git-dirty-sha256", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.self_check:
        return _self_check()
    config_path = args.config if args.config.is_absolute() else ROOT / args.config
    fixture_path = args.fixture if args.fixture.is_absolute() else ROOT / args.fixture
    config = load_json(config_path)
    config["_config_path"] = str(config_path.resolve())
    if args.worker:
        validate_schedule(config, fixture_path)
        output = args.output or (Path(__file__).resolve().parent / "gate1-worker.json")
        if not args.run_id or not args.root_id or not args.config_sha256 or not args.git_dirty_sha256:
            raise SystemExit("worker requires run_id, root_id, config_sha256, and git_dirty_sha256")
        return _worker(
            config, output, args.state_index, args.anchor_id, args.learner_slot,
            args.run_id, args.root_id, args.config_sha256,
            args.git_dirty_sha256,
            preflight=args.preflight_worker,
            complete_root=args.complete_root_worker,
        )
    if sum(bool(value) for value in (
        args.dry_run, args.execute_native, args.preflight_child, args.preflight_complete_root
    )) > 1:
        parser.error("choose only one execution mode")
    if args.execute_native:
        return _execute_full(config, fixture_path)
    try:
        report = validate_schedule(config, fixture_path)
        if args.preflight_complete_root:
            return _execute_complete_root_preflight(config, config_path)
        if args.preflight_child:
            anchor_id = config["state_schedule"]["anchor_cells"][0]["anchor"]
            config_sha256 = sha256_file(config_path)
            run_id = _new_run_id()
            root_id = sha256_value({
                "run_id": run_id,
                "state_index": 0,
                "anchor_id": anchor_id,
                "learner_slot": 0,
            })
            run_dir = Path(__file__).resolve().parent / "runs" / run_id
            if run_dir.exists():
                raise ScheduleError(f"refusing stale run directory: {run_dir}")
            run_dir.mkdir(parents=True)
            git_dirty_sha256 = _git_dirty_sha256()
            worker_output = run_dir / "worker.json"
            worker = _start_worker(
                config_path, config, worker_output, 0, anchor_id, 0,
                run_id, root_id, config_sha256, git_dirty_sha256, preflight=True,
            )
            worker_execution_ok = worker.get("status") in {
                "PASS_COMPLETE", "PASS_EXECUTION_G2_BLOCKED",
            }
            report = {
                "status": "PASS_EXECUTION" if worker_execution_ok else "BLOCKED",
                "mode": "PREFLIGHT_CHILD",
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "run_id": run_id,
                "root_id": root_id,
                "config_sha256": config_sha256,
                "git_dirty_sha256": git_dirty_sha256,
                "config_path": str(config_path.relative_to(ROOT)),
                "worker_output": str(worker_output.relative_to(ROOT)),
                "native_launches": worker.get("native_launches", 0),
                "required_continuation_rollouts": PREFLIGHT_ACTIONS * PREFLIGHT_PARTICLES,
                "preflight_scope": "2/10 root actions x 2 shared particles; execution evidence only",
                "coverage_scope": "MAIN_SINGLE_CHOICE_ONLY; COMPOUND_AND_OPTIONAL_STOP_REQUIRE_SEPARATE_MECHANICS_GATE",
                "worker": worker,
                "full_schedule_authorized": False,
                "full_schedule_launched": False,
            }
            if worker.get("status") == "PASS_COMPLETE":
                anchor = next(item for item in config["frozen_anchor_policies"] if item["baseline_id"] == anchor_id)
                group = worker["state_group"]
                partial_group = dict(group)
                partial_group["action_aggregates"] = group["action_aggregates"][:PREFLIGHT_ACTIONS]
                partial_group["replicates"] = [
                    dict(item, actions=item["actions"][:PREFLIGHT_ACTIONS])
                    for item in group["replicates"][:PREFLIGHT_PARTICLES]
                ]
                dataset = _dataset_from_group(config, partial_group, anchor)
                errors = _validate_dataset_shape(dataset)
                report["dataset_schema_status"] = (
                    "BLOCKED_PREFLIGHT_IS_PARTIAL" if errors else "UNEXPECTED_PASS"
                )
                report["dataset_schema_errors"] = errors
                report["dataset_emitted"] = False
                report["dataset_shape_note"] = (
                    "The four-child preflight is intentionally not a trainable artifact: "
                    "the root has a complete action set but only its first two actions were run."
                )
            elif worker.get("status") == "PASS_EXECUTION_G2_BLOCKED":
                report["dataset_schema_status"] = "BLOCKED_G2_PUBLIC_PROJECTION"
                report["dataset_schema_errors"] = worker.get("g2_projection", {}).get("blockers", [])
                report["dataset_emitted"] = False
                report["dataset_shape_note"] = (
                    "Native search and parent-COW execution completed, but no trainable/public record "
                    "was emitted because the frozen G2 projector requires recorded public GRU history."
                )
            execution_output = run_dir / "preflight-execution.json"
            report["execution_output"] = str(execution_output.relative_to(ROOT))
            execution_output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(json.dumps(report, sort_keys=True))
            return 0 if report["status"] == "PASS_EXECUTION" else 1
        report["config_sha256"] = sha256_file(config_path)
        OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(report, sort_keys=True))
        return 0
    except (OSError, KeyError, TypeError, ValueError, ScheduleError) as error:
        report = {"status": "FAIL", "native_launches": 0, "error": f"{type(error).__name__}: {error}"}
        OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(report, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
