from __future__ import annotations

import hashlib
import io
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import torch

from ptcg_rl.g2.models import (
    ENTITY_CATEGORICAL_NAMES,
    ENTITY_NUMERIC_NAMES,
    EVENT_CATEGORICAL_NAMES,
    EVENT_IDENTITY_NAMES,
    EVENT_NUMERIC_NAMES,
    GLOBAL_CATEGORICAL_NAMES,
    GLOBAL_NUMERIC_NAMES,
    MODEL_SCHEMA_VERSION,
    OPTION_CATEGORICAL_NAMES,
    OPTION_NUMERIC_NAMES,
    PLAYER_CATEGORICAL_NAMES,
    PLAYER_NUMERIC_NAMES,
    ModelInputV1,
    OptionTransportMapV1,
    ProjectedDecisionV1,
    model_schema_sha256,
)
from ptcg_rl.replay.semantic_loader import SemanticReplayDecisionV1

MATERIALIZED_BC_SCHEMA_VERSION = 1
MATERIALIZED_BC_KIND = "KPTCG_MATERIALIZED_BC_EPISODE_V1"
_MODEL_NAME_FIELDS = {
    "player_categorical_names",
    "player_numeric_names",
    "entity_categorical_names",
    "entity_numeric_names",
    "event_categorical_names",
    "event_numeric_names",
    "event_identity_names",
    "option_categorical_names",
    "option_numeric_names",
    "global_categorical_names",
    "global_numeric_names",
}


class MaterializedBCError(ValueError):
    """Raised when a materialized BC episode violates its compact contract."""


@dataclass(frozen=True)
class MaterializedRequestV1:
    min_count: int
    max_count: int
    forced: bool

    @property
    def has_only_one_outcome(self) -> bool:
        return self.forced


@dataclass(frozen=True)
class MaterializedActionV1:
    submitted_original_indices: tuple[int, ...]
    stopped_early: bool


@dataclass(frozen=True)
class MaterializedDecisionV1:
    projected: ProjectedDecisionV1
    request: MaterializedRequestV1
    action: MaterializedActionV1


@dataclass(frozen=True)
class MaterializedEpisodeV1:
    episode_id: int
    teacher_player_index: int
    split: str
    teacher_result: str
    teacher_team_name: str
    source_replay_sha256: str
    decisions: tuple[MaterializedDecisionV1, ...]
    policy_targets: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_sha256(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise MaterializedBCError(f"{label} must be a lowercase SHA-256")
    return value


def _model_payload(model: ModelInputV1) -> dict[str, Any]:
    if model.schema_version != MODEL_SCHEMA_VERSION:
        raise MaterializedBCError("unsupported model-input schema version")
    expected_names = {
        "player_categorical_names": PLAYER_CATEGORICAL_NAMES,
        "player_numeric_names": PLAYER_NUMERIC_NAMES,
        "entity_categorical_names": ENTITY_CATEGORICAL_NAMES,
        "entity_numeric_names": ENTITY_NUMERIC_NAMES,
        "event_categorical_names": EVENT_CATEGORICAL_NAMES,
        "event_numeric_names": EVENT_NUMERIC_NAMES,
        "event_identity_names": EVENT_IDENTITY_NAMES,
        "option_categorical_names": OPTION_CATEGORICAL_NAMES,
        "option_numeric_names": OPTION_NUMERIC_NAMES,
        "global_categorical_names": GLOBAL_CATEGORICAL_NAMES,
        "global_numeric_names": GLOBAL_NUMERIC_NAMES,
    }
    for name, expected in expected_names.items():
        if getattr(model, name) != expected:
            raise MaterializedBCError(f"model feature names differ for {name}")
    payload = asdict(model)
    payload.pop("schema_version")
    for name in _MODEL_NAME_FIELDS:
        payload.pop(name)
    return payload


def _model_from_payload(value: Any) -> ModelInputV1:
    if not isinstance(value, Mapping):
        raise MaterializedBCError("materialized model payload must be an object")
    return ModelInputV1(
        schema_version=MODEL_SCHEMA_VERSION,
        player_categorical_names=PLAYER_CATEGORICAL_NAMES,
        player_numeric_names=PLAYER_NUMERIC_NAMES,
        entity_categorical_names=ENTITY_CATEGORICAL_NAMES,
        entity_numeric_names=ENTITY_NUMERIC_NAMES,
        event_categorical_names=EVENT_CATEGORICAL_NAMES,
        event_numeric_names=EVENT_NUMERIC_NAMES,
        event_identity_names=EVENT_IDENTITY_NAMES,
        option_categorical_names=OPTION_CATEGORICAL_NAMES,
        option_numeric_names=OPTION_NUMERIC_NAMES,
        global_categorical_names=GLOBAL_CATEGORICAL_NAMES,
        global_numeric_names=GLOBAL_NUMERIC_NAMES,
        **dict(value),
    )


def materialize_decision(decision: SemanticReplayDecisionV1) -> dict[str, Any]:
    request = decision.request
    action = decision.action
    return {
        "model": _model_payload(decision.projected.model),
        "min_count": int(request.min_count),
        "max_count": int(request.max_count),
        "forced": bool(request.has_only_one_outcome),
        "selected_indices": tuple(int(value) for value in action.submitted_original_indices),
        "stopped_early": bool(action.stopped_early),
    }


def _decision_from_payload(value: Any) -> MaterializedDecisionV1:
    if not isinstance(value, Mapping):
        raise MaterializedBCError("materialized decision must be an object")
    expected = {
        "model",
        "min_count",
        "max_count",
        "forced",
        "selected_indices",
        "stopped_early",
    }
    if set(value) != expected:
        raise MaterializedBCError("materialized decision keys differ")
    minimum = value["min_count"]
    maximum = value["max_count"]
    forced = value["forced"]
    selected = value["selected_indices"]
    stopped = value["stopped_early"]
    if (
        isinstance(minimum, bool)
        or not isinstance(minimum, int)
        or isinstance(maximum, bool)
        or not isinstance(maximum, int)
        or minimum < 0
        or maximum < minimum
    ):
        raise MaterializedBCError("materialized request bounds are invalid")
    if not isinstance(forced, bool) or not isinstance(stopped, bool):
        raise MaterializedBCError("materialized request/action flags must be boolean")
    if not isinstance(selected, (list, tuple)) or any(
        isinstance(index, bool) or not isinstance(index, int) or index < 0 for index in selected
    ):
        raise MaterializedBCError("materialized selected indices are invalid")
    if len(selected) != len(set(selected)):
        raise MaterializedBCError("materialized selected indices contain duplicates")
    model = _model_from_payload(value["model"])
    projected = ProjectedDecisionV1(
        schema_version=MODEL_SCHEMA_VERSION,
        model=model,
        transport=OptionTransportMapV1(
            schema_version=MODEL_SCHEMA_VERSION,
            request_id="materialized",
            original_indices=(),
            semantic_fingerprints=(),
        ),
    )
    return MaterializedDecisionV1(
        projected=projected,
        request=MaterializedRequestV1(min_count=minimum, max_count=maximum, forced=forced),
        action=MaterializedActionV1(
            submitted_original_indices=tuple(selected),
            stopped_early=stopped,
        ),
    )


def build_episode_payload(
    *,
    episode_id: int,
    teacher_player_index: int,
    split: str,
    teacher_result: str,
    teacher_team_name: str,
    source_replay_sha256: str,
    decisions: Sequence[SemanticReplayDecisionV1],
) -> dict[str, Any]:
    if episode_id <= 0 or teacher_player_index not in (0, 1):
        raise MaterializedBCError("materialized episode identity is invalid")
    if split not in {"train", "validation"}:
        raise MaterializedBCError("materialized BC may contain train/validation episodes only")
    if teacher_result not in {"win", "loss"} or not teacher_team_name:
        raise MaterializedBCError("materialized teacher metadata is invalid")
    _require_sha256(source_replay_sha256, "source replay SHA-256")
    if not decisions:
        raise MaterializedBCError("materialized episode contains no decisions")
    if any(decision.agent_index != teacher_player_index for decision in decisions):
        raise MaterializedBCError("materialized decision belongs to the wrong teacher seat")
    if [decision.sequence_index for decision in decisions] != list(range(len(decisions))):
        raise MaterializedBCError("materialized decision sequence is noncontiguous")
    rows = [materialize_decision(decision) for decision in decisions]
    policy_targets = sum(not bool(row["forced"]) for row in rows)
    if policy_targets <= 0:
        raise MaterializedBCError("materialized episode contains no policy target")
    return {
        "schema_version": MATERIALIZED_BC_SCHEMA_VERSION,
        "kind": MATERIALIZED_BC_KIND,
        "model_schema_sha256": model_schema_sha256(),
        "episode_id": episode_id,
        "teacher_player_index": teacher_player_index,
        "split": split,
        "teacher_result": teacher_result,
        "teacher_team_name": teacher_team_name,
        "source_replay_sha256": source_replay_sha256,
        "policy_targets": policy_targets,
        "decisions": rows,
    }


def save_episode_payload(path: Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    buffer = io.BytesIO()
    torch.save(dict(payload), buffer)
    raw = buffer.getvalue()
    if not raw:
        raise MaterializedBCError("materialized episode serialization is empty")
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    partial.write_bytes(raw)
    partial.replace(path)
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def load_materialized_episode(
    path: Path,
    *,
    expected_sha256: str | None = None,
) -> MaterializedEpisodeV1:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise MaterializedBCError("materialized episode SHA-256 differs")
    try:
        payload = torch.load(io.BytesIO(raw), map_location="cpu", weights_only=True)
    except Exception as error:
        raise MaterializedBCError(f"restricted materialized episode load failed: {error}") from error
    if not isinstance(payload, Mapping):
        raise MaterializedBCError("materialized episode payload must be an object")
    expected = {
        "schema_version",
        "kind",
        "model_schema_sha256",
        "episode_id",
        "teacher_player_index",
        "split",
        "teacher_result",
        "teacher_team_name",
        "source_replay_sha256",
        "policy_targets",
        "decisions",
    }
    if set(payload) != expected:
        raise MaterializedBCError("materialized episode payload keys differ")
    if payload["schema_version"] != MATERIALIZED_BC_SCHEMA_VERSION or payload["kind"] != MATERIALIZED_BC_KIND:
        raise MaterializedBCError("materialized episode identity differs")
    if payload["model_schema_sha256"] != model_schema_sha256():
        raise MaterializedBCError("materialized model schema differs")
    episode_id = payload["episode_id"]
    teacher = payload["teacher_player_index"]
    split = payload["split"]
    result = payload["teacher_result"]
    team = payload["teacher_team_name"]
    source_sha = _require_sha256(payload["source_replay_sha256"], "source replay SHA-256")
    policy_targets = payload["policy_targets"]
    rows = payload["decisions"]
    if (
        isinstance(episode_id, bool)
        or not isinstance(episode_id, int)
        or episode_id <= 0
        or teacher not in (0, 1)
        or split not in {"train", "validation"}
        or result not in {"win", "loss"}
        or not isinstance(team, str)
        or not team
        or isinstance(policy_targets, bool)
        or not isinstance(policy_targets, int)
        or policy_targets <= 0
        or not isinstance(rows, (list, tuple))
        or not rows
    ):
        raise MaterializedBCError("materialized episode metadata is invalid")
    decisions = tuple(_decision_from_payload(row) for row in rows)
    observed_targets = sum(not decision.request.forced for decision in decisions)
    if observed_targets != policy_targets:
        raise MaterializedBCError("materialized episode policy-target count differs")
    return MaterializedEpisodeV1(
        episode_id=episode_id,
        teacher_player_index=teacher,
        split=split,
        teacher_result=result,
        teacher_team_name=team,
        source_replay_sha256=source_sha,
        decisions=decisions,
        policy_targets=policy_targets,
    )
