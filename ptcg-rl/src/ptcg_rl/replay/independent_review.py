from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

from ptcg_rl.g1.models import ContractViolation, stable_hash
from ptcg_rl.g1.semantic import semantic_snapshot
from ptcg_rl.g2.models import model_schema_sha256
from ptcg_rl.g2.projection import project_decision

from .planner import ReplayPlanError, verify_plan

INDEPENDENT_REVIEW_VERSION = "r1-independent-review-v1"


class ReplayReviewError(ValueError):
    """Raised when independent replay recalculation disagrees with tracked evidence."""


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReplayReviewError(f"cannot load {label} {path}: {error}") from error


def _expected_files(plan: Mapping[str, Any]) -> dict[str, int]:
    try:
        verify_plan(plan)
    except ReplayPlanError as error:
        raise ReplayReviewError(str(error)) from error
    selected = plan.get("selected_items")
    if not isinstance(selected, list) or not selected:
        raise ReplayReviewError("approved plan has no selected items")
    expected: dict[str, int] = {}
    for position, item in enumerate(selected):
        if not isinstance(item, Mapping):
            raise ReplayReviewError(f"selected_items[{position}] must be an object")
        filename = item.get("remote_filename")
        size = item.get("declared_bytes")
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise ReplayReviewError(f"selected_items[{position}] filename is invalid")
        if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
            raise ReplayReviewError(f"selected_items[{position}] size is invalid")
        expected[filename] = size
    return expected


def _report_audit_is_valid(report: Mapping[str, Any]) -> bool:
    claimed = report.get("audit_sha256")
    if not isinstance(claimed, str):
        return False
    payload = dict(report)
    payload.pop("audit_sha256", None)
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest() == claimed


def independently_review_semantic_report(
    plan: Mapping[str, Any],
    episodes_dir: Path,
    semantic_report: Mapping[str, Any],
    *,
    created_at_utc: str | None = None,
    source_commit: str | None = None,
) -> dict[str, Any]:
    if semantic_report.get("status") != "PASS":
        raise ReplayReviewError("semantic loader report is not PASS")
    if not _report_audit_is_valid(semantic_report):
        raise ReplayReviewError("semantic loader report audit SHA-256 is invalid")
    card_data_sha256 = semantic_report.get("card_data_sha256")
    if not isinstance(card_data_sha256, str) or len(card_data_sha256) != 64:
        raise ReplayReviewError("semantic loader report card-data SHA-256 is invalid")
    expected = _expected_files(plan)
    actual = {path.name for path in episodes_dir.glob("*.json") if path.is_file()}
    if actual != set(expected):
        raise ReplayReviewError("episode file set differs from approved plan")

    stream_digest = hashlib.sha256()
    decisions = 0
    chosen_options = 0
    stop_markers = 0
    forced_requests = 0
    meaningful_requests = 0
    ordered_requests = 0
    max_legal_options = 0
    max_selected_options = 0
    selection_types: Counter[str] = Counter()
    option_types: Counter[str] = Counter()
    per_episode: Counter[str] = Counter()

    for filename in sorted(expected):
        path = episodes_dir / filename
        if path.stat().st_size != expected[filename]:
            raise ReplayReviewError(f"{filename} byte count differs from approved plan")
        replay = _load_json(path, "episode")
        if not isinstance(replay, Mapping):
            raise ReplayReviewError(f"{filename} is not a JSON object")
        internal_id = replay.get("id")
        steps = replay.get("steps")
        if not isinstance(internal_id, str) or not internal_id:
            raise ReplayReviewError(f"{filename} internal id is invalid")
        if not isinstance(steps, list) or len(steps) < 2:
            raise ReplayReviewError(f"{filename} steps are invalid")
        sequence_indices = [0, 0]
        previous_request_refs: list[str | None] = [None, None]
        previous_action_refs: list[str | None] = [None, None]
        episode_id = filename.removesuffix(".json")
        for action_step_index in range(2, len(steps)):
            request_step_index = action_step_index - 1
            previous_step = steps[request_step_index]
            current_step = steps[action_step_index]
            if not isinstance(previous_step, list) or not isinstance(current_step, list):
                raise ReplayReviewError(f"{filename} step shape is invalid")
            if len(previous_step) != 2 or len(current_step) != 2:
                raise ReplayReviewError(f"{filename} step agent count is invalid")
            for agent_index in (0, 1):
                previous_record = previous_step[agent_index]
                current_record = current_step[agent_index]
                if not isinstance(previous_record, Mapping) or not isinstance(
                    current_record, Mapping
                ):
                    raise ReplayReviewError(f"{filename} record is invalid")
                raw_action = current_record.get("action")
                if not isinstance(raw_action, list) or any(
                    isinstance(index, bool) or not isinstance(index, int)
                    for index in raw_action
                ):
                    raise ReplayReviewError(f"{filename} transport action is invalid")
                if previous_record.get("status") != "ACTIVE":
                    if raw_action:
                        raise ReplayReviewError(f"{filename} action follows non-active state")
                    continue
                raw_observation = previous_record.get("observation")
                if not isinstance(raw_observation, Mapping):
                    raise ReplayReviewError(f"{filename} observation is invalid")
                if raw_observation.get("select") is None:
                    if raw_action:
                        raise ReplayReviewError(f"{filename} action follows missing request")
                    continue
                sequence_index = sequence_indices[agent_index]
                try:
                    observation, request = semantic_snapshot(
                        raw_observation,
                        episode_id,
                        sequence_index,
                        card_data_sha256,
                        previous_action_ref=previous_action_refs[agent_index],
                        previous_request_ref=previous_request_refs[agent_index],
                    )
                    if request is None:
                        raise ReplayReviewError("active record produced no semantic request")
                    projected = project_decision(observation, request)
                except (ContractViolation, KeyError, TypeError, ValueError) as error:
                    raise ReplayReviewError(
                        f"{filename} semantic recalculation failed: {error}"
                    ) from error
                indices = tuple(raw_action)
                if len(indices) != len(set(indices)):
                    raise ReplayReviewError(f"{filename} action has duplicate indices")
                if not request.min_count <= len(indices) <= request.max_count:
                    raise ReplayReviewError(f"{filename} action count violates request")
                if any(index < 0 or index >= len(request.options) for index in indices):
                    raise ReplayReviewError(f"{filename} action index is out of range")
                chosen = tuple(request.options[index] for index in indices)
                if any(not option.available for option in chosen):
                    raise ReplayReviewError(f"{filename} action selects unavailable option")
                stopped_early = len(indices) < request.max_count
                trace = tuple(
                    f"OPTION:{option.semantic_fingerprint}" for option in chosen
                )
                if stopped_early:
                    trace = (*trace, "STOP")
                semantic_action = {
                    "schema_version": 1,
                    "submitted_original_indices": indices,
                    "chosen_semantic_fingerprints": tuple(
                        option.semantic_fingerprint for option in chosen
                    ),
                    "decoder_trace": trace,
                    "stopped_early": stopped_early,
                }
                reward = current_record.get("reward")
                if isinstance(reward, bool) or not isinstance(reward, (int, float)):
                    raise ReplayReviewError(f"{filename} reward is invalid")
                payload = {
                    "schema_version": 1,
                    "episode_id": episode_id,
                    "internal_replay_id": internal_id,
                    "agent_index": agent_index,
                    "request_step_index": request_step_index,
                    "action_step_index": action_step_index,
                    "sequence_index": sequence_index,
                    "request_id": request.request_id,
                    "observation_sha256": stable_hash(observation),
                    "model_input_sha256": stable_hash(projected.model),
                    "transport_sha256": stable_hash(projected.transport),
                    "action": semantic_action,
                    "reward": float(reward),
                }
                stream_digest.update(_canonical_bytes(payload))
                stream_digest.update(b"\n")
                decisions += 1
                per_episode[episode_id] += 1
                chosen_options += len(indices)
                stop_markers += int(stopped_early)
                forced_requests += int(request.has_only_one_outcome)
                meaningful_requests += int(not request.has_only_one_outcome)
                ordered_requests += int(request.ordering == "ORDERED")
                selection_types[str(request.selection_type)] += 1
                for option in request.options:
                    option_types[str(option.option_type)] += 1
                max_legal_options = max(max_legal_options, len(request.options))
                max_selected_options = max(max_selected_options, len(indices))
                sequence_indices[agent_index] += 1
                previous_request_refs[agent_index] = request.request_id
                previous_action_refs[agent_index] = stable_hash(semantic_action)

    recalculated_coverage = {
        "episodes": len(expected),
        "episode_bytes": sum(expected.values()),
        "max_episode_bytes": max(expected.values()),
        "decisions": decisions,
        "chosen_options": chosen_options,
        "stop_markers": stop_markers,
        "forced_requests": forced_requests,
        "meaningful_requests": meaningful_requests,
        "ordered_requests": ordered_requests,
        "unordered_requests": decisions - ordered_requests,
        "max_legal_options": max_legal_options,
        "max_selected_options": max_selected_options,
        "selection_type_counts": dict(sorted(selection_types.items())),
        "legal_option_type_counts": dict(sorted(option_types.items())),
        "per_episode_decisions": dict(sorted(per_episode.items())),
    }
    stream_sha256 = stream_digest.hexdigest()
    mismatches: list[str] = []
    if semantic_report.get("plan_sha256") != plan.get("plan_sha256"):
        mismatches.append("plan_sha256")
    if semantic_report.get("model_schema_sha256") != model_schema_sha256():
        mismatches.append("model_schema_sha256")
    if semantic_report.get("semantic_stream_sha256") != stream_sha256:
        mismatches.append("semantic_stream_sha256")
    if semantic_report.get("coverage") != recalculated_coverage:
        mismatches.append("coverage")
    if mismatches:
        raise ReplayReviewError(
            "independent semantic review disagrees on: " + ", ".join(mismatches)
        )

    timestamp = created_at_utc or datetime.now(UTC).isoformat()
    report = {
        "schema_version": 1,
        "record_id": "replay-r1-independent-review-20260719",
        "created_at_utc": timestamp,
        "updated_at_utc": timestamp,
        "source_path": "reports/replays/r1-independent-review.json",
        "producer": "ptcg-r1-independent-review",
        "producer_version": INDEPENDENT_REVIEW_VERSION,
        "title": "Independent R1 semantic replay recalculation",
        "gate_id": "R1",
        "status": "PASS",
        "decision": "PASS",
        "source_commit": source_commit,
        "reviewed_record_id": semantic_report.get("record_id"),
        "reviewed_audit_sha256": semantic_report.get("audit_sha256"),
        "plan_sha256": plan.get("plan_sha256"),
        "card_data_sha256": card_data_sha256,
        "model_schema_sha256": model_schema_sha256(),
        "semantic_stream_sha256": stream_sha256,
        "recalculated_coverage": recalculated_coverage,
        "checks": {
            "report_audit_sha256": "PASS",
            "exact_file_set_and_sizes": "PASS",
            "independent_lag_alignment": "PASS",
            "zero_based_transport_indices": "PASS",
            "semantic_projection": "PASS",
            "ordered_action_and_stop_reconstruction": "PASS",
            "stream_sha256_match": "PASS",
            "aggregate_coverage_match": "PASS",
        },
        "mismatches": [],
        "warnings": [
            "This review independently recalculates structure and semantics but does not establish policy strength.",
            "The elite replay sample remains biased and is not authorized as imitation-learning supervision.",
        ],
    }
    report["review_sha256"] = hashlib.sha256(_canonical_bytes(report)).hexdigest()
    return report


def write_review_report(report: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    partial.replace(path)
