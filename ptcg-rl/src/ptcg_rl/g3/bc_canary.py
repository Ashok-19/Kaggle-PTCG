from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import random
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import torch
from torch import Tensor

from ptcg_rl.g2.checkpoint import load_checkpoint_package, state_dict_sha256
from ptcg_rl.g2.network import PTCGPolicyV1, collate_projected
from ptcg_rl.g3.checkpoint import (
    restore_training_checkpoint,
    save_training_checkpoint,
)
from ptcg_rl.g3.ppo import (
    CompoundActionV1,
    LocalExecutionLimitsV1,
    apply_local_execution_limits,
    replay_compound_action,
    require_finite_gradients,
    validate_local_workload,
)
from ptcg_rl.replay.semantic_loader import (
    SemanticReplayDecisionV1,
    SemanticReplayLoader,
)


CANARY_SCHEMA_VERSION = 1
PREFLIGHT_KIND = "KPTCG_E01_BC_ENGINEERING_CANARY_PREFLIGHT"
EXECUTION_KIND = "KPTCG_E01_BC_ENGINEERING_CANARY_EXECUTION"


class BCCanaryContractError(ValueError):
    """Raised when the bounded BC canary contract is missing or violated."""


@dataclass(frozen=True)
class TeacherEpisodeV1:
    episode_id: int
    teacher_player_index: int
    decisions: tuple[SemanticReplayDecisionV1, ...]
    expected_meaningful_decisions: int
    teacher_key: str
    stratum: str


@dataclass(frozen=True)
class CanaryAssetsV1:
    request_path: Path
    request: dict[str, Any]
    manifest_path: Path
    manifest: dict[str, Any]
    checkpoint_path: Path
    checkpoint_sha256: str
    card_data_path: Path
    card_data_sha256: str


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def pretty_object_hash(value: Mapping[str, Any], field: str) -> str:
    payload = copy.deepcopy(dict(value))
    payload.pop(field, None)
    raw = (
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        + "\n"
    ).encode("utf-8")
    return _sha256(raw)


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise BCCanaryContractError(f"{name} must be a positive integer")
    return value


def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BCCanaryContractError(f"{name} must be a nonnegative integer")
    return value


def _finite_number(value: Any, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BCCanaryContractError(f"{name} must be numeric")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0):
        raise BCCanaryContractError(f"{name} must be finite" + (" and positive" if positive else ""))
    return result


def _safe_relative_path(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise BCCanaryContractError(f"{name} must be a canonical relative path")
    path = Path(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise BCCanaryContractError(f"{name} must be a canonical relative path")
    if path.as_posix() != value:
        raise BCCanaryContractError(f"{name} must use canonical POSIX separators")
    return value


def _require_sha256(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise BCCanaryContractError(f"{name} must be a lowercase SHA-256")
    return value


def load_and_validate_request(root: Path, request_path: Path) -> CanaryAssetsV1:
    try:
        request = json.loads(request_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BCCanaryContractError(f"cannot load BC canary request: {error}") from error
    if not isinstance(request, dict) or request.get("schema_version") != CANARY_SCHEMA_VERSION:
        raise BCCanaryContractError("unsupported BC canary request schema")
    if request.get("record_id") != "e01-bc-engineering-canary-request-v1":
        raise BCCanaryContractError("BC canary request identity differs")
    if request.get("source_path") != request_path.relative_to(root).as_posix():
        raise BCCanaryContractError("BC canary request source_path differs")
    if request.get("request_ready") is not True:
        raise BCCanaryContractError("BC canary request is not ready")
    authorization = request.get("authorization")
    if not isinstance(authorization, Mapping):
        raise BCCanaryContractError("BC canary authorization must be an object")
    expected_false = {
        "external_compute",
        "git_commit",
        "git_push",
        "label_generation",
        "model_promotion",
        "production_training",
        "submission",
    }
    if any(authorization.get(name) is not False for name in expected_false):
        raise BCCanaryContractError("BC canary request expands a forbidden authorization")
    if authorization.get("optimizer_steps") not in {False, True}:
        raise BCCanaryContractError("optimizer_steps authorization must be boolean")
    if request.get("authorized") is not authorization.get("optimizer_steps"):
        raise BCCanaryContractError("top-level authorized must equal optimizer_steps authorization")

    execution = request.get("execution")
    if not isinstance(execution, Mapping):
        raise BCCanaryContractError("BC canary execution must be an object")
    if execution.get("platform") != "local_cpu_only" or execution.get("external_compute") is not False:
        raise BCCanaryContractError("BC canary must be local CPU only")
    if execution.get("accelerator") is not False or execution.get("data_workers") != 0:
        raise BCCanaryContractError("BC canary accelerator and worker boundary differs")
    if execution.get("production_checkpoint_eligible") is not False:
        raise BCCanaryContractError("BC canary checkpoint must be production-ineligible")
    if _positive_int(execution.get("maximum_optimizer_steps"), "maximum_optimizer_steps") != 64:
        raise BCCanaryContractError("BC canary optimizer budget must be exactly 64")
    if _positive_int(execution.get("checkpoint_at_optimizer_step"), "checkpoint_at_optimizer_step") != 32:
        raise BCCanaryContractError("BC canary resume checkpoint must be exactly step 32")
    if _positive_int(execution.get("batch_size_episodes"), "batch_size_episodes") != 2:
        raise BCCanaryContractError("BC canary batch size must be exactly two episodes")
    if _positive_int(execution.get("recurrent_sequence_length"), "recurrent_sequence_length") > 64:
        raise BCCanaryContractError("BC canary recurrent sequence length exceeds 64")
    if _positive_int(execution.get("maximum_cpu_threads"), "maximum_cpu_threads") > 2:
        raise BCCanaryContractError("BC canary CPU thread ceiling exceeds two")
    if _positive_int(execution.get("maximum_wall_seconds"), "maximum_wall_seconds") > 1800:
        raise BCCanaryContractError("BC canary wall cap exceeds 1800 seconds")
    _positive_int(execution.get("seed"), "seed")
    _finite_number(execution.get("learning_rate"), "learning_rate", positive=True)
    _finite_number(execution.get("maximum_gradient_norm"), "maximum_gradient_norm", positive=True)
    if execution.get("optimizer") != "AdamW":
        raise BCCanaryContractError("BC canary optimizer must be AdamW")
    checkpoint_output = _safe_relative_path(execution.get("checkpoint_output"), "checkpoint_output")
    if not checkpoint_output.startswith("private/g3/e01/bc-engineering-canary-v1"):
        raise BCCanaryContractError("BC canary output path differs from its quarantine")

    corpus = request.get("corpus")
    if not isinstance(corpus, Mapping) or corpus.get("split") != "train":
        raise BCCanaryContractError("BC canary corpus must use only the train split")
    episodes = corpus.get("episodes")
    if not isinstance(episodes, list) or len(episodes) != 8 or corpus.get("episode_count") != 8:
        raise BCCanaryContractError("BC canary corpus must contain exactly eight episodes")
    ids: set[int] = set()
    paths: set[str] = set()
    observed_strata: Counter[tuple[str, str]] = Counter()
    decisions = 0
    for position, item in enumerate(episodes):
        if not isinstance(item, Mapping):
            raise BCCanaryContractError(f"corpus episode {position} must be an object")
        episode_id = _positive_int(item.get("episode_id"), f"episodes[{position}].episode_id")
        path = _safe_relative_path(item.get("path"), f"episodes[{position}].path")
        if episode_id in ids or path in paths:
            raise BCCanaryContractError("BC canary corpus contains a duplicate episode")
        ids.add(episode_id)
        paths.add(path)
        if Path(path).name != f"{episode_id}.json":
            raise BCCanaryContractError("BC canary replay path and episode ID differ")
        _positive_int(item.get("bytes"), f"episodes[{position}].bytes")
        _require_sha256(item.get("sha256"), f"episodes[{position}].sha256")
        if item.get("split") != "train":
            raise BCCanaryContractError("BC canary episode is outside the train split")
        teacher_key = item.get("teacher_key")
        stratum = item.get("stratum")
        if teacher_key not in {"flg", "dries"} or stratum not in {
            "seat_0_loss",
            "seat_0_win",
            "seat_1_loss",
            "seat_1_win",
        }:
            raise BCCanaryContractError("BC canary teacher/stratum differs")
        observed_strata[(str(teacher_key), str(stratum))] += 1
        decisions += _nonnegative_int(
            item.get("meaningful_teacher_decisions"),
            f"episodes[{position}].meaningful_teacher_decisions",
        )
        player = item.get("teacher_player_index")
        if player not in (0, 1):
            raise BCCanaryContractError("teacher player index must be zero or one")
    if set(observed_strata.values()) != {1} or len(observed_strata) != 8:
        raise BCCanaryContractError("BC canary must contain one episode per teacher/seat/result stratum")
    if corpus.get("meaningful_teacher_decisions") != decisions:
        raise BCCanaryContractError("BC canary corpus decision total differs")

    manifest_rel = _safe_relative_path(corpus.get("manifest_path"), "corpus manifest path")
    manifest_path = root / manifest_rel
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise BCCanaryContractError(f"cannot load corpus manifest: {error}") from error
    expected_manifest_hash = _require_sha256(corpus.get("manifest_sha256"), "corpus manifest SHA-256")
    if manifest.get("manifest_sha256") != expected_manifest_hash:
        raise BCCanaryContractError("corpus manifest identity differs from request")
    if pretty_object_hash(manifest, "manifest_sha256") != expected_manifest_hash:
        raise BCCanaryContractError("corpus manifest self-hash differs")
    manifest_records = {
        int(item["episode_id"]): item
        for item in manifest.get("qualified_training_corpus", {}).get("episode_records", [])
    }
    for item in episodes:
        record = manifest_records.get(int(item["episode_id"]))
        if record is None:
            raise BCCanaryContractError("BC canary episode is absent from qualified corpus")
        for name in (
            "path",
            "bytes",
            "sha256",
            "split",
            "teacher_key",
            "teacher_player_index",
            "meaningful_teacher_decisions",
            "stratum",
        ):
            if record.get(name) != item.get(name):
                raise BCCanaryContractError(
                    f"BC canary episode {item['episode_id']} differs from corpus manifest at {name}"
                )

    assets = request.get("assets")
    if not isinstance(assets, Mapping):
        raise BCCanaryContractError("BC canary assets must be an object")
    checkpoint = assets.get("initial_checkpoint")
    card_data = assets.get("card_data")
    if not isinstance(checkpoint, Mapping) or not isinstance(card_data, Mapping):
        raise BCCanaryContractError("BC canary asset records are malformed")
    checkpoint_rel = _safe_relative_path(checkpoint.get("path"), "checkpoint path")
    checkpoint_path = root / checkpoint_rel
    checkpoint_sha = _require_sha256(checkpoint.get("sha256"), "checkpoint SHA-256")
    card_rel = _safe_relative_path(card_data.get("path"), "card data path")
    card_path = root / card_rel
    card_sha = _require_sha256(card_data.get("sha256"), "card data SHA-256")
    for path, expected_bytes, expected_sha, label in (
        (checkpoint_path, checkpoint.get("bytes"), checkpoint_sha, "checkpoint"),
        (card_path, card_data.get("bytes"), card_sha, "card data"),
    ):
        try:
            raw = path.read_bytes()
        except OSError as error:
            raise BCCanaryContractError(f"cannot read {label}: {error}") from error
        if len(raw) != _positive_int(expected_bytes, f"{label} bytes") or _sha256(raw) != expected_sha:
            raise BCCanaryContractError(f"{label} bytes or SHA-256 differ")

    return CanaryAssetsV1(
        request_path=request_path,
        request=request,
        manifest_path=manifest_path,
        manifest=manifest,
        checkpoint_path=checkpoint_path,
        checkpoint_sha256=checkpoint_sha,
        card_data_path=card_path,
        card_data_sha256=card_sha,
    )


def build_semantic_loader_plan(episode_records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    selected = [
        {
            "remote_filename": f"{int(item['episode_id'])}.json",
            "declared_bytes": int(item["bytes"]),
        }
        for item in sorted(episode_records, key=lambda item: int(item["episode_id"]))
    ]
    total = sum(item["declared_bytes"] for item in selected)
    maximum = max(item["declared_bytes"] for item in selected)
    plan: dict[str, Any] = {
        "schema_version": 1,
        "planner_version": "e01-bc-engineering-canary-v1",
        "created_at_utc": "2026-08-04T10:00:34Z",
        "selection_profile": {
            "caps": {
                "max_files": len(selected),
                "max_total_bytes": total,
                "max_file_bytes": maximum,
            }
        },
        "summary": {"selected_files": len(selected), "selected_bytes": total},
        "selected_items": selected,
        "rows": [],
    }
    payload = dict(plan)
    payload.pop("created_at_utc")
    plan["plan_sha256"] = _sha256(_canonical_json_bytes(payload))
    return plan


def _stage_replays(root: Path, episode_records: Sequence[Mapping[str, Any]], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=False)
    for item in episode_records:
        source = root / str(item["path"])
        try:
            raw = source.read_bytes()
        except OSError as error:
            raise BCCanaryContractError(f"cannot read replay {source}: {error}") from error
        if len(raw) != int(item["bytes"]) or _sha256(raw) != item["sha256"]:
            raise BCCanaryContractError(f"replay bytes or SHA-256 differ for episode {item['episode_id']}")
        destination = directory / f"{int(item['episode_id'])}.json"
        try:
            os.link(source, destination)
        except OSError:
            destination.write_bytes(raw)


def load_teacher_episodes(root: Path, assets: CanaryAssetsV1) -> tuple[TeacherEpisodeV1, ...]:
    records = assets.request["corpus"]["episodes"]
    plan = build_semantic_loader_plan(records)
    by_id = {int(item["episode_id"]): item for item in records}
    with tempfile.TemporaryDirectory(prefix="kptcg-bc-canary-") as temporary:
        directory = Path(temporary) / "episodes"
        _stage_replays(root, records, directory)
        loader = SemanticReplayLoader(
            plan,
            directory,
            card_data_sha256=assets.card_data_sha256,
        )
        grouped: dict[int, list[SemanticReplayDecisionV1]] = {episode_id: [] for episode_id in by_id}
        for decision in loader:
            episode_id = int(decision.episode_id)
            record = by_id[episode_id]
            if decision.agent_index == record["teacher_player_index"]:
                grouped[episode_id].append(decision)
    result: list[TeacherEpisodeV1] = []
    for episode_id in sorted(grouped):
        record = by_id[episode_id]
        decisions = tuple(grouped[episode_id])
        expected_sequence = list(range(len(decisions)))
        if [item.sequence_index for item in decisions] != expected_sequence:
            raise BCCanaryContractError(f"teacher sequence indices differ for episode {episode_id}")
        meaningful = sum(not item.request.has_only_one_outcome for item in decisions)
        if meaningful != record["meaningful_teacher_decisions"]:
            raise BCCanaryContractError(
                f"teacher meaningful decision count differs for episode {episode_id}: "
                f"expected {record['meaningful_teacher_decisions']}, observed {meaningful}"
            )
        result.append(
            TeacherEpisodeV1(
                episode_id=episode_id,
                teacher_player_index=int(record["teacher_player_index"]),
                decisions=decisions,
                expected_meaningful_decisions=meaningful,
                teacher_key=str(record["teacher_key"]),
                stratum=str(record["stratum"]),
            )
        )
    return tuple(result)


def _action_nll(
    model: PTCGPolicyV1,
    decision: SemanticReplayDecisionV1,
    hidden: Tensor,
) -> tuple[Tensor | None, Tensor, dict[str, Any]]:
    batch = collate_projected((decision.projected,), device=hidden.device)
    output = model(batch, hidden)
    next_hidden = output.hidden
    option_count = int(output.option_offsets[1] - output.option_offsets[0])
    options = output.option_embeddings[:option_count]
    available = batch.option_available[:option_count]
    selected = tuple(decision.action.submitted_original_indices)
    if option_count != len(decision.request.options):
        raise BCCanaryContractError("model option count differs from semantic request")
    if tuple(bool(value) for value in available.tolist()) != tuple(
        option.available for option in decision.request.options
    ):
        raise BCCanaryContractError("model legal-option mask differs from semantic request")
    if tuple(decision.projected.transport.original_indices) != tuple(
        option.original_index for option in decision.request.options
    ):
        raise BCCanaryContractError("model transport map differs from semantic request")
    if len(selected) != len(set(selected)):
        raise BCCanaryContractError("teacher action contains a duplicate ordered selection")
    forced = bool(decision.request.has_only_one_outcome)
    stopped = bool(decision.action.stopped_early)
    replay_logp: Tensor | None = None
    if option_count == 0 and decision.request.min_count == 0 and decision.request.max_count == 0:
        if selected or not forced:
            raise BCCanaryContractError("zero-option request is not the unique forced empty outcome")
    else:
        replay = replay_compound_action(
            initial_prefix=model.decoder_initial(output.hidden[0]),
            option_embeddings=options,
            available_mask=available,
            action=CompoundActionV1(selected_indices=selected, stopped=stopped),
            minimum_count=decision.request.min_count,
            maximum_count=decision.request.max_count,
            decoder_logits=model.decoder_logits,
            decoder_advance=model.decoder_advance,
        )
        replay_logp = replay.log_probability
        if not torch.isfinite(replay_logp):
            raise BCCanaryContractError("compound BC log-probability is nonfinite")
    loss = None if forced else (-replay_logp if replay_logp is not None else None)
    if not forced and loss is None:
        raise BCCanaryContractError("meaningful request lacks a BC policy loss")
    return loss, next_hidden, {
        "forced": forced,
        "ordered": decision.request.ordering == "ORDERED",
        "stopped": stopped,
        "option_count": option_count,
        "selected_count": len(selected),
        "request_digest": decision.decision_sha256,
    }


def _load_model(assets: CanaryAssetsV1) -> PTCGPolicyV1:
    loaded = load_checkpoint_package(
        assets.checkpoint_path,
        device="cpu",
        expected_package_sha256=assets.checkpoint_sha256,
    )
    return loaded.model


def _safe_stream_hash(episodes: Sequence[TeacherEpisodeV1]) -> str:
    digest = hashlib.sha256()
    for episode in episodes:
        for decision in episode.decisions:
            digest.update(decision.decision_sha256.encode("ascii"))
            digest.update(b"\n")
    return digest.hexdigest()


def run_preflight(root: Path, request_path: Path) -> dict[str, Any]:
    assets = load_and_validate_request(root, request_path)
    execution = assets.request["execution"]
    limits = LocalExecutionLimitsV1(
        max_cpu_threads=int(execution["maximum_cpu_threads"]),
        max_worker_processes=1,
        max_non_forced_choices=4096,
        max_wall_seconds=int(execution["maximum_wall_seconds"]),
        allow_cuda=False,
    )
    resource_state = apply_local_execution_limits(limits)
    validate_local_workload(
        non_forced_choices=int(assets.request["corpus"]["meaningful_teacher_decisions"]),
        worker_processes=0,
        device="cpu",
        limits=limits,
    )
    random.seed(int(execution["seed"]))
    np.random.seed(int(execution["seed"]) % (2**32))
    torch.manual_seed(int(execution["seed"]))

    episodes = load_teacher_episodes(root, assets)
    model = _load_model(assets)
    model.eval()
    counts: Counter[str] = Counter()
    maximum_option_count = 0
    maximum_selected_count = 0
    per_episode: dict[str, Any] = {}
    gradient_targets: list[tuple[TeacherEpisodeV1, int]] = []
    with torch.inference_mode():
        for episode in episodes:
            hidden = model.initial_hidden(1, "cpu")
            episode_counts: Counter[str] = Counter()
            first_meaningful: int | None = None
            for index, decision in enumerate(episode.decisions):
                loss, hidden, details = _action_nll(model, decision, hidden)
                hidden = hidden.detach()
                counts["teacher_decisions"] += 1
                counts["forced_decisions"] += int(details["forced"])
                counts["meaningful_decisions"] += int(not details["forced"])
                counts["ordered_requests"] += int(details["ordered"])
                counts["stop_targets"] += int(details["stopped"])
                counts["selected_options"] += int(details["selected_count"])
                episode_counts["teacher_decisions"] += 1
                episode_counts["forced_decisions"] += int(details["forced"])
                episode_counts["meaningful_decisions"] += int(not details["forced"])
                maximum_option_count = max(maximum_option_count, int(details["option_count"]))
                maximum_selected_count = max(maximum_selected_count, int(details["selected_count"]))
                if first_meaningful is None and loss is not None:
                    first_meaningful = index
            if first_meaningful is None:
                raise BCCanaryContractError(f"episode {episode.episode_id} has no meaningful teacher decision")
            gradient_targets.append((episode, first_meaningful))
            per_episode[str(episode.episode_id)] = {
                "teacher_key": episode.teacher_key,
                "stratum": episode.stratum,
                **dict(episode_counts),
            }

    model.train()
    model.zero_grad(set_to_none=True)
    probe_losses: list[Tensor] = []
    for episode, target_index in gradient_targets:
        hidden = model.initial_hidden(1, "cpu")
        for index, decision in enumerate(episode.decisions[: target_index + 1]):
            if index < target_index:
                with torch.no_grad():
                    _, hidden, _ = _action_nll(model, decision, hidden)
                hidden = hidden.detach()
            else:
                loss, _hidden, details = _action_nll(model, decision, hidden)
                if loss is None or details["forced"]:
                    raise BCCanaryContractError("gradient target unexpectedly lacks policy loss")
                probe_losses.append(loss)
    gradient_loss = torch.stack(probe_losses).mean()
    if not torch.isfinite(gradient_loss):
        raise BCCanaryContractError("BC gradient probe loss is nonfinite")
    gradient_loss.backward()
    gradient_norm = require_finite_gradients(tuple(model.parameters()))
    model.zero_grad(set_to_none=True)

    expected_meaningful = int(assets.request["corpus"]["meaningful_teacher_decisions"])
    if counts["meaningful_decisions"] != expected_meaningful:
        raise BCCanaryContractError("preflight meaningful decision total differs from request")
    output_path = root / str(execution["checkpoint_output"])
    if output_path.exists():
        raise BCCanaryContractError("BC canary output path already exists before authorization")
    request_raw = request_path.read_bytes()
    manifest_raw = assets.manifest_path.read_bytes()
    return {
        "schema_version": 1,
        "kind": PREFLIGHT_KIND,
        "record_id": "e01-bc-engineering-canary-preflight-v1",
        "source_path": "reports/artifacts/e01-bc-engineering-canary-preflight-v1.json",
        "status": "PASS",
        "request": {
            "path": request_path.relative_to(root).as_posix(),
            "bytes": len(request_raw),
            "sha256": _sha256(request_raw),
            "authorized": False,
        },
        "corpus_manifest": {
            "path": assets.manifest_path.relative_to(root).as_posix(),
            "bytes": len(manifest_raw),
            "sha256": _sha256(manifest_raw),
            "manifest_sha256": assets.manifest["manifest_sha256"],
        },
        "assets": {
            "initial_checkpoint": {
                "path": assets.checkpoint_path.relative_to(root).as_posix(),
                "sha256": assets.checkpoint_sha256,
                "state_sha256": state_dict_sha256(model.state_dict()),
            },
            "card_data": {
                "path": assets.card_data_path.relative_to(root).as_posix(),
                "sha256": assets.card_data_sha256,
            },
        },
        "coverage": {
            "episodes": len(episodes),
            **dict(counts),
            "maximum_option_count": maximum_option_count,
            "maximum_selected_count": maximum_selected_count,
            "per_episode": per_episode,
            "safe_teacher_stream_sha256": _safe_stream_hash(episodes),
        },
        "gradient_probe": {
            "episodes": len(probe_losses),
            "loss": float(gradient_loss.detach()),
            "global_gradient_norm": gradient_norm,
            "optimizer_constructed": False,
            "optimizer_steps": 0,
            "parameters_changed": False,
        },
        "semantics": {
            "lag_alignment": True,
            "ordered_selection_preserved": True,
            "stop_first_class": True,
            "legal_option_mask_verified": True,
            "forced_calls_advance_recurrence": True,
            "forced_calls_create_policy_loss": False,
            "episode_split_leakage": 0,
        },
        "execution_boundary": {
            "request_authorized": False,
            "optimizer_steps_authorized": False,
            "optimizer_steps_executed": 0,
            "checkpoint_output_exists": False,
            "external_compute": False,
            "production_training": False,
            "model_promotion": False,
            "submission": False,
        },
        "resources": resource_state,
    }


def _episode_chunk_loss(
    model: PTCGPolicyV1,
    episode: TeacherEpisodeV1,
    start: int,
    length: int,
) -> Tensor:
    hidden = model.initial_hidden(1, next(model.parameters()).device)
    with torch.no_grad():
        for decision in episode.decisions[:start]:
            _, hidden, _ = _action_nll(model, decision, hidden)
            hidden = hidden.detach()
    losses: list[Tensor] = []
    for decision in episode.decisions[start : start + length]:
        loss, hidden, _ = _action_nll(model, decision, hidden)
        if loss is not None:
            losses.append(loss)
    if not losses:
        raise BCCanaryContractError("selected recurrent chunk contains no learner-controlled target")
    return torch.stack(losses).mean()


def _set_deterministic_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed % (2**32))
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)


def execute_authorized_canary(root: Path, request_path: Path) -> dict[str, Any]:
    assets = load_and_validate_request(root, request_path)
    request = assets.request
    if request.get("authorized") is not True or request["authorization"].get("optimizer_steps") is not True:
        raise BCCanaryContractError(
            "BC canary optimizer execution is unauthorized; approve this exact request first"
        )
    execution = request["execution"]
    output_dir = root / str(execution["checkpoint_output"])
    if output_dir.exists():
        raise BCCanaryContractError("BC canary output directory already exists")
    limits = LocalExecutionLimitsV1(
        max_cpu_threads=int(execution["maximum_cpu_threads"]),
        max_worker_processes=1,
        max_non_forced_choices=4096,
        max_wall_seconds=int(execution["maximum_wall_seconds"]),
        allow_cuda=False,
    )
    apply_local_execution_limits(limits)
    validate_local_workload(
        non_forced_choices=int(request["corpus"]["meaningful_teacher_decisions"]),
        worker_processes=0,
        device="cpu",
        limits=limits,
    )
    _set_deterministic_seed(int(execution["seed"]))
    episodes = load_teacher_episodes(root, assets)
    model = _load_model(assets)
    model.train()
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(execution["learning_rate"]),
        weight_decay=float(execution["weight_decay"]),
    )
    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda=lambda _step: 1.0)
    maximum_steps = int(execution["maximum_optimizer_steps"])
    recovery = request.get("execution_recovery", {})
    prior_failed_steps = int(recovery.get("optimizer_steps_already_executed", 0))
    if prior_failed_steps < 0 or prior_failed_steps >= maximum_steps:
        raise BCCanaryContractError("BC canary recovery step count is invalid")
    remaining_steps = maximum_steps - prior_failed_steps
    sequence_length = int(execution["recurrent_sequence_length"])
    batch_episodes = int(execution["batch_size_episodes"])
    checkpoint_step = int(execution["checkpoint_at_optimizer_step"])
    maximum_gradient_norm = float(execution["maximum_gradient_norm"])
    schedule: list[tuple[int, int]] = []
    skipped_forced_only_chunks: list[tuple[int, int]] = []
    for episode_index, episode in enumerate(episodes):
        starts = list(range(0, len(episode.decisions), sequence_length))
        for start in starts:
            chunk = episode.decisions[start : start + sequence_length]
            if not any(not decision.request.has_only_one_outcome for decision in chunk):
                skipped_forced_only_chunks.append((episode_index, start))
                continue
            schedule.append((episode_index, start))
    if not schedule:
        raise BCCanaryContractError("BC canary produced an empty recurrent chunk schedule")
    losses: list[float] = []
    gradient_norms: list[float] = []
    checkpoint_receipt: dict[str, Any] | None = None
    output_dir.mkdir(parents=True, exist_ok=False)
    checkpoint_path = output_dir / "step-32.pt"
    for step in range(remaining_steps):
        optimizer.zero_grad(set_to_none=True)
        batch_losses: list[Tensor] = []
        for batch_index in range(batch_episodes):
            episode_index, start = schedule[(step * batch_episodes + batch_index) % len(schedule)]
            batch_losses.append(
                _episode_chunk_loss(model, episodes[episode_index], start, sequence_length)
            )
        loss = torch.stack(batch_losses).mean()
        if not torch.isfinite(loss):
            raise BCCanaryContractError("BC canary loss is nonfinite")
        loss.backward()
        gradient_norm = require_finite_gradients(tuple(model.parameters()))
        torch.nn.utils.clip_grad_norm_(model.parameters(), maximum_gradient_norm, error_if_nonfinite=True)
        optimizer.step()
        scheduler.step()
        losses.append(float(loss.detach()))
        gradient_norms.append(gradient_norm)
        completed = prior_failed_steps + step + 1
        if completed == checkpoint_step:
            checkpoint_receipt = save_training_checkpoint(
                checkpoint_path,
                model=model,
                optimizer=optimizer,
                scheduler=scheduler,
                scaler=None,
                counters={"optimizer_steps": completed},
                league={"kind": "bc-engineering-canary", "production_eligible": False},
                rollout_boundary={"schedule_position": completed * batch_episodes},
                include_cuda_rng=False,
            )
            restored_model = _load_model(assets)
            restored_model.train()
            restored_optimizer = torch.optim.AdamW(
                restored_model.parameters(),
                lr=float(execution["learning_rate"]),
                weight_decay=float(execution["weight_decay"]),
            )
            restored_scheduler = torch.optim.lr_scheduler.LambdaLR(
                restored_optimizer, lr_lambda=lambda _step: 1.0
            )
            restored = restore_training_checkpoint(
                checkpoint_path,
                model=restored_model,
                optimizer=restored_optimizer,
                scheduler=restored_scheduler,
                scaler=None,
                expected_sha256=checkpoint_receipt["payload_sha256"],
                restore_rng=True,
            )
            if restored.counters != {"optimizer_steps": completed}:
                raise BCCanaryContractError("BC canary resume counters differ")
            if state_dict_sha256(restored_model.state_dict()) != state_dict_sha256(model.state_dict()):
                raise BCCanaryContractError("BC canary resumed model state differs")
            model = restored_model
            optimizer = restored_optimizer
            scheduler = restored_scheduler
    if checkpoint_receipt is None:
        raise BCCanaryContractError("BC canary did not create its required resume checkpoint")
    final_state_sha = state_dict_sha256(model.state_dict())
    report = {
        "schema_version": 1,
        "kind": EXECUTION_KIND,
        "record_id": "e01-bc-engineering-canary-execution-v1",
        "source_path": "reports/evaluations/e01-bc-engineering-canary-v1.json",
        "status": "PASS",
        "request_sha256": _sha256(request_path.read_bytes()),
        "optimizer_steps": maximum_steps,
        "successful_attempt_optimizer_steps": remaining_steps,
        "prior_failed_attempt_optimizer_steps": prior_failed_steps,
        "skipped_forced_only_chunks": [
            {"episode_index": episode_index, "start": start}
            for episode_index, start in skipped_forced_only_chunks
        ],
        "loss": {"first": losses[0], "last": losses[-1], "all_finite": True},
        "gradient_norm": {
            "maximum_pre_clip": max(gradient_norms),
            "all_finite": True,
        },
        "resume": {
            "checkpoint_step": checkpoint_step,
            "payload_sha256": checkpoint_receipt["payload_sha256"],
            "state_match_after_restore": True,
        },
        "final_state_sha256": final_state_sha,
        "production_checkpoint_eligible": False,
        "recovery_from_fail_closed_scheduler_bug": prior_failed_steps > 0,
        "policy_competence_claimed": False,
        "external_compute": False,
        "submission_authorized": False,
    }
    report_path = output_dir / "execution-report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
