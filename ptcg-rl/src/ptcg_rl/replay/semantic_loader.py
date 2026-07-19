from __future__ import annotations

import gc
import hashlib
import json
import resource
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from ptcg_rl.g1.models import (
    ContractViolation,
    EngineObservationV1,
    SelectionRequestV1,
    stable_hash,
)
from ptcg_rl.g1.semantic import semantic_snapshot
from ptcg_rl.g2.models import ProjectedDecisionV1, model_schema_sha256
from ptcg_rl.g2.projection import project_decision

from .planner import ReplayPlanError, verify_plan

SEMANTIC_REPLAY_SCHEMA_VERSION = 1
SEMANTIC_LOADER_VERSION = "r1-semantic-loader-v1"


class ReplaySemanticError(ValueError):
    """Raised when a replay cannot be converted into the sealed semantic contract."""


@dataclass(frozen=True)
class SemanticReplayActionV1:
    schema_version: int
    submitted_original_indices: tuple[int, ...]
    chosen_semantic_fingerprints: tuple[str, ...]
    decoder_trace: tuple[str, ...]
    stopped_early: bool

    @property
    def action_sha256(self) -> str:
        return stable_hash(self)


@dataclass(frozen=True)
class SemanticReplayDecisionV1:
    schema_version: int
    episode_id: str
    internal_replay_id: str
    agent_index: int
    request_step_index: int
    action_step_index: int
    sequence_index: int
    observation: EngineObservationV1
    request: SelectionRequestV1
    projected: ProjectedDecisionV1
    action: SemanticReplayActionV1
    reward: float

    @property
    def safe_digest_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "episode_id": self.episode_id,
            "internal_replay_id": self.internal_replay_id,
            "agent_index": self.agent_index,
            "request_step_index": self.request_step_index,
            "action_step_index": self.action_step_index,
            "sequence_index": self.sequence_index,
            "request_id": self.request.request_id,
            "observation_sha256": stable_hash(self.observation),
            "model_input_sha256": stable_hash(self.projected.model),
            "transport_sha256": stable_hash(self.projected.transport),
            "action": asdict(self.action),
            "reward": self.reward,
        }

    @property
    def decision_sha256(self) -> str:
        return stable_hash(self.safe_digest_payload)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def _lowercase_sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ReplaySemanticError(f"{label} must be a lowercase SHA-256")
    return value


def load_verified_official_card_data_sha256(
    asset_hashes_path: Path,
    card_data_path: Path,
) -> str:
    """Return the official card-data hash only after record and file-byte parity."""
    try:
        asset_hashes = json.loads(asset_hashes_path.read_text(encoding="utf-8"))
        recorded = asset_hashes["assets"]["official"]["signature_sha256"]["card_data"]
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise ReplaySemanticError(
            f"cannot resolve official card-data hash from {asset_hashes_path}: {error}"
        ) from error
    expected = _lowercase_sha256(recorded, "official card-data hash")
    try:
        observed = hashlib.sha256(card_data_path.read_bytes()).hexdigest()
    except OSError as error:
        raise ReplaySemanticError(f"cannot hash official card-data file {card_data_path}: {error}") from error
    if observed != expected:
        raise ReplaySemanticError(
            "official card-data file SHA-256 differs from asset record: "
            f"expected {expected}, observed {observed}"
        )
    return expected


def _integer(value: Any, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ReplaySemanticError(f"{label} must be an integer >= {minimum}")
    return value


def _action(value: Any, label: str) -> tuple[int, ...]:
    if not isinstance(value, list) or any(
        isinstance(item, bool) or not isinstance(item, int) for item in value
    ):
        raise ReplaySemanticError(f"{label} must be a list of integers")
    return tuple(value)


def _record(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReplaySemanticError(f"{label} must be an object")
    for key in ("action", "observation", "reward", "status"):
        if key not in value:
            raise ReplaySemanticError(f"{label} is missing {key}")
    _action(value["action"], f"{label}.action")
    if value["status"] not in {"ACTIVE", "INACTIVE", "DONE"}:
        raise ReplaySemanticError(f"{label}.status is unsupported")
    reward = value["reward"]
    if isinstance(reward, bool) or not isinstance(reward, (int, float)):
        raise ReplaySemanticError(f"{label}.reward must be numeric")
    if not isinstance(value["observation"], Mapping):
        raise ReplaySemanticError(f"{label}.observation must be an object")
    return value


def _expected_files(plan: Mapping[str, Any]) -> dict[str, int]:
    try:
        verify_plan(plan)
    except ReplayPlanError as error:
        raise ReplaySemanticError(str(error)) from error
    selected = plan.get("selected_items")
    if not isinstance(selected, list) or not selected:
        raise ReplaySemanticError("verified plan has no selected_items")
    expected: dict[str, int] = {}
    for position, item in enumerate(selected):
        if not isinstance(item, Mapping):
            raise ReplaySemanticError(f"selected_items[{position}] must be an object")
        filename = item.get("remote_filename")
        if (
            not isinstance(filename, str)
            or not filename.endswith(".json")
            or Path(filename).name != filename
        ):
            raise ReplaySemanticError(f"selected_items[{position}].remote_filename is invalid")
        declared = _integer(
            item.get("declared_bytes"),
            f"selected_items[{position}].declared_bytes",
            minimum=1,
        )
        if filename in expected:
            raise ReplaySemanticError(f"duplicate selected replay filename {filename}")
        expected[filename] = declared
    return expected


def decode_replay_action(
    request: SelectionRequestV1,
    transport_indices: Sequence[int],
) -> SemanticReplayActionV1:
    indices = tuple(transport_indices)
    if any(isinstance(index, bool) or not isinstance(index, int) for index in indices):
        raise ReplaySemanticError("replay transport action must contain only integers")
    if len(indices) != len(set(indices)):
        raise ReplaySemanticError("replay transport action contains duplicate option indices")
    if not request.min_count <= len(indices) <= request.max_count:
        raise ReplaySemanticError("replay transport action violates request count bounds")
    if any(index < 0 or index >= len(request.options) for index in indices):
        raise ReplaySemanticError("replay transport action contains an out-of-range zero-based index")
    chosen = tuple(request.options[index] for index in indices)
    if any(not option.available for option in chosen):
        raise ReplaySemanticError("replay transport action selects an unavailable option")
    stopped_early = len(indices) < request.max_count
    trace = tuple(f"OPTION:{option.semantic_fingerprint}" for option in chosen)
    if stopped_early:
        trace = (*trace, "STOP")
    return SemanticReplayActionV1(
        schema_version=SEMANTIC_REPLAY_SCHEMA_VERSION,
        submitted_original_indices=indices,
        chosen_semantic_fingerprints=tuple(
            option.semantic_fingerprint for option in chosen
        ),
        decoder_trace=trace,
        stopped_early=stopped_early,
    )


class SemanticReplayLoader:
    """Deterministically yields semantic decisions with at most one episode resident."""

    def __init__(
        self,
        plan: Mapping[str, Any],
        episodes_dir: Path,
        *,
        card_data_sha256: str,
    ) -> None:
        _lowercase_sha256(card_data_sha256, "card_data_sha256")
        self.plan = plan
        self.episodes_dir = episodes_dir
        self.card_data_sha256 = card_data_sha256
        self.expected_files = _expected_files(plan)
        if not episodes_dir.is_dir():
            raise ReplaySemanticError(f"episode directory does not exist: {episodes_dir}")
        actual = {
            path.name for path in episodes_dir.glob("*.json") if path.is_file()
        }
        missing = sorted(set(self.expected_files) - actual)
        extra = sorted(actual - set(self.expected_files))
        partials = sorted(path.name for path in episodes_dir.glob("*.partial"))
        if missing or extra or partials:
            raise ReplaySemanticError(
                "replay file set differs from approved plan; "
                f"missing={missing}; extra={extra}; partials={partials}"
            )

    def __iter__(self) -> Iterator[SemanticReplayDecisionV1]:
        for filename in sorted(self.expected_files):
            yield from self._iter_episode(filename)
            gc.collect()

    def _iter_episode(self, filename: str) -> Iterator[SemanticReplayDecisionV1]:
        path = self.episodes_dir / filename
        expected_bytes = self.expected_files[filename]
        observed_bytes = path.stat().st_size
        if observed_bytes != expected_bytes:
            raise ReplaySemanticError(
                f"{filename} byte count differs: expected {expected_bytes}, observed {observed_bytes}"
            )
        try:
            with path.open("r", encoding="utf-8") as handle:
                replay = json.load(handle)
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ReplaySemanticError(f"cannot parse replay {filename}: {error}") from error
        if not isinstance(replay, Mapping):
            raise ReplaySemanticError(f"{filename} top level must be an object")
        internal_id = replay.get("id")
        if not isinstance(internal_id, str) or not internal_id:
            raise ReplaySemanticError(f"{filename}.id must be a nonempty string")
        if replay.get("statuses") != ["DONE", "DONE"]:
            raise ReplaySemanticError(f"{filename} is not terminal for both agents")
        rewards = replay.get("rewards")
        if rewards not in ([-1, 1], [1, -1]):
            raise ReplaySemanticError(f"{filename} has unsupported terminal rewards")
        steps = replay.get("steps")
        if not isinstance(steps, list) or len(steps) < 2:
            raise ReplaySemanticError(f"{filename}.steps must contain initialization records")
        parsed_steps: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
        for step_index, step in enumerate(steps):
            if not isinstance(step, list) or len(step) != 2:
                raise ReplaySemanticError(
                    f"{filename}.steps[{step_index}] must contain two agent records"
                )
            parsed_steps.append(
                (
                    _record(step[0], f"{filename}.steps[{step_index}][0]"),
                    _record(step[1], f"{filename}.steps[{step_index}][1]"),
                )
            )
        for agent_index, initial in enumerate(parsed_steps[0]):
            if (
                initial["status"] != "ACTIVE"
                or _action(initial["action"], "initial.action")
                or initial["observation"].get("select") is not None
            ):
                raise ReplaySemanticError(
                    f"{filename}.steps[0][{agent_index}] is not the empty active initialization"
                )
        for agent_index, deck_record in enumerate(parsed_steps[1]):
            if len(_action(deck_record["action"], "deck.action")) != 60:
                raise ReplaySemanticError(
                    f"{filename}.steps[1][{agent_index}] is not a 60-card deck action"
                )

        episode_id = filename.removesuffix(".json")
        sequence_indices = [0, 0]
        previous_request_refs: list[str | None] = [None, None]
        previous_action_refs: list[str | None] = [None, None]
        for action_step_index in range(2, len(parsed_steps)):
            request_step_index = action_step_index - 1
            previous_step = parsed_steps[request_step_index]
            current_step = parsed_steps[action_step_index]
            for agent_index in (0, 1):
                previous_record = previous_step[agent_index]
                current_record = current_step[agent_index]
                transport = _action(
                    current_record["action"],
                    f"{filename}.steps[{action_step_index}][{agent_index}].action",
                )
                if previous_record["status"] != "ACTIVE":
                    if transport:
                        raise ReplaySemanticError(
                            f"{filename}.steps[{action_step_index}][{agent_index}] acts after a non-active record"
                        )
                    continue
                raw_observation = previous_record["observation"]
                if raw_observation.get("select") is None:
                    if transport:
                        raise ReplaySemanticError(
                            f"{filename}.steps[{action_step_index}][{agent_index}] acts after a missing request"
                        )
                    continue
                sequence_index = sequence_indices[agent_index]
                try:
                    observation, request = semantic_snapshot(
                        raw_observation,
                        episode_id,
                        sequence_index,
                        self.card_data_sha256,
                        previous_action_ref=previous_action_refs[agent_index],
                        previous_request_ref=previous_request_refs[agent_index],
                    )
                    if request is None:
                        raise ReplaySemanticError("active replay observation produced no request")
                    projected = project_decision(observation, request)
                except (ContractViolation, KeyError, TypeError, ValueError) as error:
                    raise ReplaySemanticError(
                        f"{filename}.steps[{request_step_index}][{agent_index}] semantic conversion failed: {error}"
                    ) from error
                semantic_action = decode_replay_action(request, transport)
                reward = float(current_record["reward"])
                decision = SemanticReplayDecisionV1(
                    schema_version=SEMANTIC_REPLAY_SCHEMA_VERSION,
                    episode_id=episode_id,
                    internal_replay_id=internal_id,
                    agent_index=agent_index,
                    request_step_index=request_step_index,
                    action_step_index=action_step_index,
                    sequence_index=sequence_index,
                    observation=observation,
                    request=request,
                    projected=projected,
                    action=semantic_action,
                    reward=reward,
                )
                sequence_indices[agent_index] += 1
                previous_request_refs[agent_index] = request.request_id
                previous_action_refs[agent_index] = semantic_action.action_sha256
                yield decision

        final_statuses = [record["status"] for record in parsed_steps[-1]]
        final_rewards = [record["reward"] for record in parsed_steps[-1]]
        if final_statuses != ["DONE", "DONE"] or final_rewards != rewards:
            raise ReplaySemanticError(f"{filename} terminal records differ from top-level result")


def _peak_rss_mib() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def audit_semantic_loader(
    plan: Mapping[str, Any],
    episodes_dir: Path,
    *,
    card_data_sha256: str,
    created_at_utc: str | None = None,
    expected_stream_sha256: str | None = None,
    max_peak_rss_mib: float | None = None,
) -> dict[str, Any]:
    loader = SemanticReplayLoader(
        plan,
        episodes_dir,
        card_data_sha256=card_data_sha256,
    )
    stream_digest = hashlib.sha256()
    decision_count = 0
    chosen_options = 0
    stop_markers = 0
    forced_requests = 0
    meaningful_requests = 0
    ordered_requests = 0
    selection_types: Counter[str] = Counter()
    option_types: Counter[str] = Counter()
    per_episode: Counter[str] = Counter()
    max_legal_options = 0
    max_selected_options = 0
    first_decision_sha256: str | None = None
    last_decision_sha256: str | None = None
    for decision in loader:
        payload = decision.safe_digest_payload
        stream_digest.update(_canonical_bytes(payload))
        stream_digest.update(b"\n")
        digest = decision.decision_sha256
        if first_decision_sha256 is None:
            first_decision_sha256 = digest
        last_decision_sha256 = digest
        decision_count += 1
        per_episode[decision.episode_id] += 1
        chosen_options += len(decision.action.submitted_original_indices)
        stop_markers += int(decision.action.stopped_early)
        forced_requests += int(decision.request.has_only_one_outcome)
        meaningful_requests += int(not decision.request.has_only_one_outcome)
        ordered_requests += int(decision.request.ordering == "ORDERED")
        selection_types[str(decision.request.selection_type)] += 1
        for option in decision.request.options:
            option_types[str(option.option_type)] += 1
        max_legal_options = max(max_legal_options, len(decision.request.options))
        max_selected_options = max(
            max_selected_options, len(decision.action.submitted_original_indices)
        )
    stream_sha256 = stream_digest.hexdigest()
    if expected_stream_sha256 is not None and stream_sha256 != expected_stream_sha256:
        raise ReplaySemanticError(
            "semantic stream SHA-256 differs from expected value: "
            f"expected {expected_stream_sha256}, observed {stream_sha256}"
        )
    peak_rss_mib = _peak_rss_mib()
    if max_peak_rss_mib is not None and peak_rss_mib > max_peak_rss_mib:
        raise ReplaySemanticError(
            f"semantic loader peak RSS {peak_rss_mib:.3f} MiB exceeds {max_peak_rss_mib:.3f} MiB"
        )
    try:
        verified = verify_plan(plan)
    except ReplayPlanError as error:
        raise ReplaySemanticError(str(error)) from error
    timestamp = created_at_utc or datetime.now(UTC).isoformat()
    total_bytes = sum(loader.expected_files.values())
    report = {
        "schema_version": 1,
        "record_id": "replay-r1-semantic-loader-20260719",
        "created_at_utc": timestamp,
        "updated_at_utc": timestamp,
        "source_path": "reports/replays/r1-semantic-loader.json",
        "producer": "ptcg-r1-semantic-loader",
        "producer_version": SEMANTIC_LOADER_VERSION,
        "title": "R1 streaming lag-aligned semantic replay loader",
        "gate_id": "R1",
        "status": "PASS",
        "plan_sha256": verified["plan_sha256"],
        "card_data_sha256": card_data_sha256,
        "model_schema_sha256": model_schema_sha256(),
        "semantic_stream_sha256": stream_sha256,
        "expected_stream_sha256": expected_stream_sha256,
        "expected_stream_sha256_match": (
            None if expected_stream_sha256 is None else True
        ),
        "loader_contract": {
            "episode_residency": "one JSON episode at a time",
            "action_alignment": "action at step t resolves only against the same agent's active request at step t-1",
            "transport_encoding": "zero-based native option indices",
            "semantic_identity": "sealed G1 option semantic fingerprints",
            "stop_rule": "append STOP exactly when submitted count is below max_count",
            "policy_probabilities_invented": False,
            "raw_replay_bodies_emitted": False,
        },
        "coverage": {
            "episodes": len(loader.expected_files),
            "episode_bytes": total_bytes,
            "max_episode_bytes": max(loader.expected_files.values()),
            "decisions": decision_count,
            "chosen_options": chosen_options,
            "stop_markers": stop_markers,
            "forced_requests": forced_requests,
            "meaningful_requests": meaningful_requests,
            "ordered_requests": ordered_requests,
            "unordered_requests": decision_count - ordered_requests,
            "max_legal_options": max_legal_options,
            "max_selected_options": max_selected_options,
            "selection_type_counts": dict(sorted(selection_types.items())),
            "legal_option_type_counts": dict(sorted(option_types.items())),
            "per_episode_decisions": dict(sorted(per_episode.items())),
        },
        "determinism": {
            "first_decision_sha256": first_decision_sha256,
            "last_decision_sha256": last_decision_sha256,
            "stream_sha256": stream_sha256,
        },
        "memory": {
            "peak_rss_mib": peak_rss_mib,
            "max_peak_rss_mib": max_peak_rss_mib,
            "within_limit": max_peak_rss_mib is None or peak_rss_mib <= max_peak_rss_mib,
        },
        "warnings": [
            "The approved daily dataset is elite, rating-selected and capped; it is not an unbiased ladder sample.",
            "Replay actions are observational evidence and are not authorized as imitation-learning supervision.",
            "The loader retains execution order for both ordered and unordered requests but never treats transport position as an actor feature.",
        ],
    }
    report["audit_sha256"] = hashlib.sha256(_canonical_bytes(report)).hexdigest()
    return report


def write_semantic_report(report: Mapping[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    partial.replace(path)
