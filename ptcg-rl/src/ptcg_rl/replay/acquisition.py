from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from .planner import ReplayPlanError, verify_plan


class ReplayAcquisitionError(ValueError):
    """Raised when acquired replay files do not match the approved plan or contract."""


@dataclass(frozen=True)
class AcquisitionPaths:
    plan: Path
    episodes: Path
    receipt: Path
    report: Path


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReplayAcquisitionError(f"cannot load {label} {path}: {error}") from error


def load_verified_plan(path: Path) -> Mapping[str, Any]:
    value = _load_json(path, "plan")
    if not isinstance(value, Mapping):
        raise ReplayAcquisitionError("plan must be a JSON object")
    try:
        verify_plan(value)
    except ReplayPlanError as error:
        raise ReplayAcquisitionError(str(error)) from error
    return value


def _integer(value: Any, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ReplayAcquisitionError(f"{label} must be an integer >= {minimum}")
    return value


def _selected_items(plan: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    selected = plan.get("selected_items")
    if not isinstance(selected, list) or not selected:
        raise ReplayAcquisitionError("plan selected_items must be a nonempty list")
    result: dict[str, Mapping[str, Any]] = {}
    for position, item in enumerate(selected):
        if not isinstance(item, Mapping):
            raise ReplayAcquisitionError(f"selected_items[{position}] must be an object")
        filename = item.get("remote_filename")
        if not isinstance(filename, str) or not filename.endswith(".json") or Path(filename).name != filename:
            raise ReplayAcquisitionError(f"selected_items[{position}].remote_filename is invalid")
        _integer(item.get("declared_bytes"), f"selected_items[{position}].declared_bytes", minimum=1)
        if filename in result:
            raise ReplayAcquisitionError(f"duplicate selected filename: {filename}")
        result[filename] = item
    return result


def _numeric_option_fields(options: Sequence[Mapping[str, Any]]) -> dict[str, set[int]]:
    fields: dict[str, set[int]] = {}
    for option in options:
        for key, value in option.items():
            if isinstance(value, int) and not isinstance(value, bool):
                fields.setdefault(key, set()).add(value)
    return fields


def _resolves_against_options(action: Sequence[int], options: Sequence[Mapping[str, Any]]) -> bool:
    if not action:
        return True
    if all(0 <= value < len(options) for value in action):
        return True
    if all(1 <= value <= len(options) for value in action):
        return True
    return any(all(value in values for value in action) for values in _numeric_option_fields(options).values())


def _selection_request(record: Mapping[str, Any], label: str) -> Mapping[str, Any] | None:
    observation = record.get("observation")
    if not isinstance(observation, Mapping):
        raise ReplayAcquisitionError(f"{label}.observation must be an object")
    select = observation.get("select")
    if select is None:
        return None
    if not isinstance(select, Mapping):
        raise ReplayAcquisitionError(f"{label}.observation.select must be an object or null")
    return select


def _validate_action(action: Any, label: str) -> list[int]:
    if not isinstance(action, list) or any(isinstance(value, bool) or not isinstance(value, int) for value in action):
        raise ReplayAcquisitionError(f"{label}.action must be a list of integers")
    return action


def _validate_record(record: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(record, Mapping):
        raise ReplayAcquisitionError(f"{label} must be an object")
    required = {"action", "info", "observation", "reward", "status"}
    missing = sorted(required - set(record))
    if missing:
        raise ReplayAcquisitionError(f"{label} is missing keys: {', '.join(missing)}")
    _validate_action(record.get("action"), label)
    _selection_request(record, label)
    if record.get("status") not in {"ACTIVE", "INACTIVE", "DONE"}:
        raise ReplayAcquisitionError(f"{label}.status is unsupported")
    reward = record.get("reward")
    if isinstance(reward, bool) or not isinstance(reward, (int, float)):
        raise ReplayAcquisitionError(f"{label}.reward must be numeric")
    return record


def _safe_source(plan: Mapping[str, Any]) -> dict[str, Any]:
    source = plan.get("source")
    if not isinstance(source, Mapping):
        raise ReplayAcquisitionError("plan source must be an object")
    return json.loads(json.dumps(source))


def audit_acquisition(
    plan: Mapping[str, Any],
    episodes_dir: Path,
    *,
    provider: str,
    acquired_at_utc: str | None = None,
) -> dict[str, Any]:
    try:
        verified = verify_plan(plan)
    except ReplayPlanError as error:
        raise ReplayAcquisitionError(str(error)) from error
    selected = _selected_items(plan)
    if not episodes_dir.is_dir():
        raise ReplayAcquisitionError(f"episode directory does not exist: {episodes_dir}")

    partials = sorted(path.name for path in episodes_dir.glob("*.partial"))
    if partials:
        raise ReplayAcquisitionError(f"partial episode files remain: {', '.join(partials)}")
    actual = {path.name: path for path in episodes_dir.glob("*.json") if path.is_file()}
    missing = sorted(set(selected) - set(actual))
    extra = sorted(set(actual) - set(selected))
    if missing or extra:
        raise ReplayAcquisitionError(
            f"episode file set differs; missing={missing or []}; extra={extra or []}"
        )

    file_rows: list[dict[str, Any]] = []
    schema_versions: Counter[str] = Counter()
    module_versions: Counter[str] = Counter()
    reward_orientations: Counter[str] = Counter()
    top_key_variants: Counter[tuple[str, ...]] = Counter()
    internal_ids: set[str] = set()
    step_counts: list[int] = []
    initial_deck_actions = 0
    active_requests = 0
    nonempty_selections = 0
    empty_selections = 0
    max_option_count = 0
    max_selection_count = 0

    for filename in sorted(selected):
        expected = selected[filename]
        path = actual[filename]
        raw = path.read_bytes()
        declared_bytes = _integer(expected.get("declared_bytes"), f"{filename}.declared_bytes", minimum=1)
        if len(raw) != declared_bytes:
            raise ReplayAcquisitionError(
                f"{filename} byte count differs: expected {declared_bytes}, observed {len(raw)}"
            )
        try:
            replay = json.loads(raw)
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ReplayAcquisitionError(f"{filename} is not valid JSON: {error}") from error
        if not isinstance(replay, Mapping):
            raise ReplayAcquisitionError(f"{filename} top level must be an object")
        top_key_variants[tuple(sorted(str(key) for key in replay))] += 1
        schema_versions[str(replay.get("schema_version"))] += 1
        module_versions[str(replay.get("module_version"))] += 1
        internal_id = replay.get("id")
        if not isinstance(internal_id, str) or not internal_id:
            raise ReplayAcquisitionError(f"{filename}.id must be a nonempty internal identifier")
        if internal_id in internal_ids:
            raise ReplayAcquisitionError(f"duplicate internal replay id in {filename}")
        internal_ids.add(internal_id)

        statuses = replay.get("statuses")
        rewards = replay.get("rewards")
        if statuses != ["DONE", "DONE"]:
            raise ReplayAcquisitionError(f"{filename} is not terminal for both agents")
        if rewards not in ([-1, 1], [1, -1]):
            raise ReplayAcquisitionError(f"{filename} has unsupported terminal rewards: {rewards!r}")
        reward_orientations[str(rewards)] += 1

        steps = replay.get("steps")
        if not isinstance(steps, list) or not steps:
            raise ReplayAcquisitionError(f"{filename}.steps must be a nonempty list")
        step_counts.append(len(steps))
        parsed_steps: list[list[Mapping[str, Any]]] = []
        for step_index, step in enumerate(steps):
            if not isinstance(step, list) or len(step) != 2:
                raise ReplayAcquisitionError(f"{filename}.steps[{step_index}] must contain two agents")
            parsed_steps.append(
                [
                    _validate_record(record, f"{filename}.steps[{step_index}][{agent_index}]")
                    for agent_index, record in enumerate(step)
                ]
            )

        if len(parsed_steps) < 2:
            raise ReplayAcquisitionError(f"{filename} must contain initialization and deck-action steps")
        for agent_index, record in enumerate(parsed_steps[0]):
            action = _validate_action(record.get("action"), f"{filename}.steps[0][{agent_index}]")
            if action or record.get("status") != "ACTIVE" or _selection_request(
                record, f"{filename}.steps[0][{agent_index}]"
            ) is not None:
                raise ReplayAcquisitionError(
                    f"{filename}.steps[0][{agent_index}] must be the empty active initialization record"
                )
        for agent_index, record in enumerate(parsed_steps[1]):
            action = _validate_action(record.get("action"), f"{filename}.steps[1][{agent_index}]")
            if len(action) != 60:
                raise ReplayAcquisitionError(
                    f"{filename}.steps[1][{agent_index}] must contain the 60-card deck action"
                )
            initial_deck_actions += 1

        for step_index in range(2, len(parsed_steps)):
            current_step = parsed_steps[step_index]
            previous_step = parsed_steps[step_index - 1]
            for agent_index, current_record in enumerate(current_step):
                action = _validate_action(
                    current_record.get("action"), f"{filename}.steps[{step_index}][{agent_index}]"
                )
                previous_record = previous_step[agent_index]
                previous_status = previous_record.get("status")
                if previous_status != "ACTIVE":
                    if action:
                        raise ReplayAcquisitionError(
                            f"{filename}.steps[{step_index}][{agent_index}] has an action after a non-active record"
                        )
                    continue
                request = _selection_request(
                    previous_record, f"{filename}.steps[{step_index - 1}][{agent_index}]"
                )
                if request is None:
                    if action:
                        raise ReplayAcquisitionError(
                            f"{filename}.steps[{step_index}][{agent_index}] has an action after a missing request"
                        )
                    continue
                minimum = _integer(
                    request.get("minCount"),
                    f"{filename}.steps[{step_index - 1}][{agent_index}].select.minCount",
                )
                maximum = _integer(
                    request.get("maxCount"),
                    f"{filename}.steps[{step_index - 1}][{agent_index}].select.maxCount",
                )
                if maximum < minimum:
                    raise ReplayAcquisitionError("selection request maximum is below minimum")
                options_value = request.get("option")
                if not isinstance(options_value, list) or any(
                    not isinstance(option, Mapping) for option in options_value
                ):
                    raise ReplayAcquisitionError("selection request options must be a list of objects")
                options = list(options_value)
                active_requests += 1
                max_option_count = max(max_option_count, len(options))
                max_selection_count = max(max_selection_count, len(action))
                if not minimum <= len(action) <= maximum:
                    raise ReplayAcquisitionError(
                        f"{filename}.steps[{step_index}][{agent_index}] selection count is outside the preceding request"
                    )
                if not _resolves_against_options(action, options):
                    raise ReplayAcquisitionError(
                        f"{filename}.steps[{step_index}][{agent_index}] action cannot be resolved against preceding options"
                    )
                if action:
                    nonempty_selections += 1
                else:
                    empty_selections += 1

        final_rewards = [record.get("reward") for record in parsed_steps[-1]]
        final_statuses = [record.get("status") for record in parsed_steps[-1]]
        if final_statuses != ["DONE", "DONE"] or final_rewards != rewards:
            raise ReplayAcquisitionError(f"{filename} terminal step differs from top-level result")

        file_rows.append(
            {
                "filename": filename,
                "episode_id": filename.removesuffix(".json"),
                "declared_bytes": declared_bytes,
                "observed_bytes": len(raw),
                "sha256": _sha256(raw),
                "steps": len(steps),
                "schema_version": replay.get("schema_version"),
                "module_version": replay.get("module_version"),
                "statuses": statuses,
                "rewards": rewards,
            }
        )

    timestamp = acquired_at_utc or datetime.now(UTC).isoformat()
    total_bytes = sum(row["observed_bytes"] for row in file_rows)
    report = {
        "schema_version": 1,
        "audit_version": "r0-acquisition-v1",
        "created_at_utc": timestamp,
        "plan_sha256": verified["plan_sha256"],
        "status": "PASS",
        "provider": provider,
        "source": _safe_source(plan),
        "acquisition": {
            "expected_files": len(selected),
            "observed_files": len(file_rows),
            "total_bytes": total_bytes,
            "max_file_bytes": max(row["observed_bytes"] for row in file_rows),
            "missing_files": 0,
            "extra_files": 0,
            "partial_files": 0,
            "json_parse_failures": 0,
            "size_mismatches": 0,
        },
        "replay_contract": {
            "schema_versions": dict(sorted(schema_versions.items())),
            "module_versions": dict(sorted(module_versions.items())),
            "top_level_key_variants": len(top_key_variants),
            "unique_internal_ids": len(internal_ids),
            "episodes_terminal_for_both_agents": len(file_rows),
            "reward_orientations": dict(sorted(reward_orientations.items())),
            "total_steps": sum(step_counts),
            "min_steps": min(step_counts),
            "max_steps": max(step_counts),
            "initial_60_card_actions": initial_deck_actions,
            "active_selection_requests": active_requests,
            "nonempty_lagged_selections": nonempty_selections,
            "empty_lagged_selections": empty_selections,
            "selection_count_violations": 0,
            "unresolvable_actions": 0,
            "max_legal_options": max_option_count,
            "max_selection_count": max_selection_count,
            "action_alignment": "Action at step t resolves against the preceding active record's observation.select request.",
        },
        "files": file_rows,
        "warnings": [
            "The replay top-level id is an internal identifier; the Kaggle episode id is carried by the filename.",
            "The daily dataset is elite, rating-selected and capped, so this is not an unbiased ladder sample.",
            "Transport action integers require semantic decoding before they can be used as model supervision.",
            "Replay bodies remain ignored private data and are not included in this report.",
        ],
    }
    report["audit_sha256"] = _sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    )
    return report


def write_acquisition_records(
    report: Mapping[str, Any],
    *,
    receipt_path: Path,
    report_path: Path,
) -> None:
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    for path in (receipt_path, report_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(path.suffix + ".partial")
        partial.write_text(payload, encoding="utf-8")
        partial.replace(path)
