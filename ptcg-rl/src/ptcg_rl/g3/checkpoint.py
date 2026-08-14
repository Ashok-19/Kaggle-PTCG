from __future__ import annotations

import hashlib
import io
import json
import math
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import torch
from torch import Tensor, nn

from ptcg_rl.g3.evaluation import canonical_json_bytes


CHECKPOINT_SCHEMA_VERSION = 1
CHECKPOINT_KIND = "KPTCG_G3_TRAINING_CHECKPOINT"
MANIFEST_KIND = "KPTCG_G3_TRAINING_CHECKPOINT_MANIFEST"
MAX_CHECKPOINT_BYTES = 512 * 1024 * 1024


class TrainingCheckpointError(ValueError):
    pass


@dataclass(frozen=True)
class LoadedTrainingCheckpointV1:
    counters: dict[str, Any]
    league: dict[str, Any]
    rollout_boundary: dict[str, Any]
    payload_sha256: str
    payload_bytes: int
    restored_rng_states: tuple[str, ...]


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    observed = set(value)
    if observed != expected:
        raise TrainingCheckpointError(
            f"{name} keys differ: missing={sorted(expected - observed)}, "
            f"unexpected={sorted(observed - expected)}"
        )


def _validate_json_safe(value: Any, name: str) -> Any:
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TrainingCheckpointError(f"{name} contains a nonfinite number")
        return value
    if isinstance(value, list):
        return [_validate_json_safe(item, f"{name}[]") for item in value]
    if isinstance(value, tuple):
        return [_validate_json_safe(item, f"{name}[]") for item in value]
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise TrainingCheckpointError(f"{name} keys must be nonempty strings")
            result[key] = _validate_json_safe(item, f"{name}.{key}")
        return result
    raise TrainingCheckpointError(f"{name} contains an unsupported value type")


def capture_rng_states(*, include_cuda: bool = True) -> dict[str, Any]:
    python_state = random.getstate()
    numpy_state = np.random.get_state()
    cuda_states: list[Tensor] = []
    if include_cuda and torch.cuda.is_available():
        cuda_states = [state.cpu() for state in torch.cuda.get_rng_state_all()]
    return {
        "python": {
            "version": int(python_state[0]),
            "internal_state": [int(value) for value in python_state[1]],
            "gaussian": None if python_state[2] is None else float(python_state[2]),
        },
        "numpy": {
            "bit_generator": str(numpy_state[0]),
            "state": torch.from_numpy(numpy_state[1].astype(np.int64, copy=True)),
            "position": int(numpy_state[2]),
            "has_gaussian": int(numpy_state[3]),
            "cached_gaussian": float(numpy_state[4]),
        },
        "torch_cpu": torch.get_rng_state().cpu(),
        "torch_cuda": cuda_states,
    }


def _validate_rng_states(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TrainingCheckpointError("checkpoint RNG state must be an object")
    _require_exact_keys(value, {"python", "numpy", "torch_cpu", "torch_cuda"}, "RNG state")
    python_state = value["python"]
    if not isinstance(python_state, Mapping):
        raise TrainingCheckpointError("Python RNG state must be an object")
    _require_exact_keys(python_state, {"version", "internal_state", "gaussian"}, "Python RNG state")
    if not isinstance(python_state["version"], int) or isinstance(python_state["version"], bool):
        raise TrainingCheckpointError("Python RNG version must be an integer")
    internal = python_state["internal_state"]
    if not isinstance(internal, list) or not internal or any(
        not isinstance(item, int) or isinstance(item, bool) for item in internal
    ):
        raise TrainingCheckpointError("Python RNG internal state must be a nonempty integer list")
    gaussian = python_state["gaussian"]
    if gaussian is not None and (not isinstance(gaussian, (int, float)) or not math.isfinite(float(gaussian))):
        raise TrainingCheckpointError("Python RNG Gaussian cache must be finite or null")

    numpy_state = value["numpy"]
    if not isinstance(numpy_state, Mapping):
        raise TrainingCheckpointError("NumPy RNG state must be an object")
    _require_exact_keys(
        numpy_state,
        {"bit_generator", "state", "position", "has_gaussian", "cached_gaussian"},
        "NumPy RNG state",
    )
    if not isinstance(numpy_state["bit_generator"], str) or not numpy_state["bit_generator"]:
        raise TrainingCheckpointError("NumPy bit generator must be a nonempty string")
    if not isinstance(numpy_state["state"], Tensor) or numpy_state["state"].ndim != 1:
        raise TrainingCheckpointError("NumPy RNG array must be a one-dimensional tensor")
    if numpy_state["state"].dtype != torch.int64:
        raise TrainingCheckpointError("NumPy RNG array must use int64 checkpoint transport")
    for name in ("position", "has_gaussian"):
        if not isinstance(numpy_state[name], int) or isinstance(numpy_state[name], bool):
            raise TrainingCheckpointError(f"NumPy RNG {name} must be an integer")
    if not isinstance(numpy_state["cached_gaussian"], (int, float)) or not math.isfinite(
        float(numpy_state["cached_gaussian"])
    ):
        raise TrainingCheckpointError("NumPy RNG Gaussian cache must be finite")

    torch_cpu = value["torch_cpu"]
    if not isinstance(torch_cpu, Tensor) or torch_cpu.dtype != torch.uint8 or torch_cpu.ndim != 1:
        raise TrainingCheckpointError("Torch CPU RNG state must be a one-dimensional uint8 tensor")
    torch_cuda = value["torch_cuda"]
    if not isinstance(torch_cuda, list) or any(
        not isinstance(item, Tensor) or item.dtype != torch.uint8 or item.ndim != 1
        for item in torch_cuda
    ):
        raise TrainingCheckpointError("Torch CUDA RNG states must be a tensor list")
    return dict(value)


def restore_rng_states(value: Mapping[str, Any]) -> tuple[str, ...]:
    state = _validate_rng_states(value)
    python_state = state["python"]
    random.setstate(
        (
            python_state["version"],
            tuple(python_state["internal_state"]),
            python_state["gaussian"],
        )
    )
    numpy_state = state["numpy"]
    np.random.set_state(
        (
            numpy_state["bit_generator"],
            numpy_state["state"].cpu().numpy().astype(np.uint32, copy=True),
            numpy_state["position"],
            numpy_state["has_gaussian"],
            numpy_state["cached_gaussian"],
        )
    )
    torch.set_rng_state(state["torch_cpu"].cpu())
    restored = ["python", "numpy", "torch_cpu"]
    cuda_states = state["torch_cuda"]
    if cuda_states:
        if not torch.cuda.is_available():
            raise TrainingCheckpointError("checkpoint contains CUDA RNG states but CUDA is unavailable")
        if len(cuda_states) != torch.cuda.device_count():
            raise TrainingCheckpointError("checkpoint CUDA RNG device count differs")
        torch.cuda.set_rng_state_all([item.cpu() for item in cuda_states])
        restored.append("torch_cuda")
    return tuple(restored)


def _checkpoint_payload(
    *,
    model: nn.Module,
    optimizer: torch.optim.Optimizer,
    scheduler: Any | None,
    scaler: Any | None,
    counters: Mapping[str, Any],
    league: Mapping[str, Any],
    rollout_boundary: Mapping[str, Any],
    include_cuda_rng: bool,
) -> dict[str, Any]:
    if scheduler is None and scaler is None:
        raise TrainingCheckpointError("checkpoint requires a scheduler or scaler state")
    return {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "kind": CHECKPOINT_KIND,
        "model_state": model.state_dict(),
        "optimizer_state": optimizer.state_dict(),
        "scheduler_state": None if scheduler is None else scheduler.state_dict(),
        "scaler_state": None if scaler is None else scaler.state_dict(),
        "counters": _validate_json_safe(dict(counters), "counters"),
        "league": _validate_json_safe(dict(league), "league"),
        "rollout_boundary": _validate_json_safe(dict(rollout_boundary), "rollout boundary"),
        "rng_states": capture_rng_states(include_cuda=include_cuda_rng),
    }


def _validate_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TrainingCheckpointError("checkpoint payload must be an object")
    expected = {
        "schema_version",
        "kind",
        "model_state",
        "optimizer_state",
        "scheduler_state",
        "scaler_state",
        "counters",
        "league",
        "rollout_boundary",
        "rng_states",
    }
    _require_exact_keys(value, expected, "checkpoint payload")
    if value["schema_version"] != CHECKPOINT_SCHEMA_VERSION:
        raise TrainingCheckpointError("unsupported training checkpoint schema version")
    if value["kind"] != CHECKPOINT_KIND:
        raise TrainingCheckpointError("training checkpoint kind differs")
    if not isinstance(value["model_state"], Mapping) or not value["model_state"]:
        raise TrainingCheckpointError("checkpoint model state must be nonempty")
    if not isinstance(value["optimizer_state"], Mapping):
        raise TrainingCheckpointError("checkpoint optimizer state must be an object")
    if value["scheduler_state"] is None and value["scaler_state"] is None:
        raise TrainingCheckpointError("checkpoint lacks scheduler and scaler state")
    for name in ("counters", "league", "rollout_boundary"):
        if not isinstance(value[name], Mapping):
            raise TrainingCheckpointError(f"checkpoint {name} must be an object")
        _validate_json_safe(dict(value[name]), name)
    _validate_rng_states(value["rng_states"])
    return dict(value)


def _manifest_path(path: Path) -> Path:
    return path.with_name(path.name + ".manifest.json")


def _parse_manifest(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise TrainingCheckpointError("training checkpoint manifest is not valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise TrainingCheckpointError("training checkpoint manifest root must be an object")
    if canonical_json_bytes(value) != raw:
        raise TrainingCheckpointError("training checkpoint manifest is not canonical JSON")
    _require_exact_keys(value, {"schema_version", "kind", "payload"}, "checkpoint manifest")
    if value["schema_version"] != CHECKPOINT_SCHEMA_VERSION or value["kind"] != MANIFEST_KIND:
        raise TrainingCheckpointError("training checkpoint manifest identity differs")
    payload = value["payload"]
    if not isinstance(payload, Mapping):
        raise TrainingCheckpointError("training checkpoint manifest payload must be an object")
    _require_exact_keys(payload, {"path", "bytes", "sha256"}, "manifest payload")
    if not isinstance(payload["path"], str) or not payload["path"]:
        raise TrainingCheckpointError("manifest payload path must be nonempty")
    if not isinstance(payload["bytes"], int) or isinstance(payload["bytes"], bool) or payload["bytes"] <= 0:
        raise TrainingCheckpointError("manifest payload bytes must be positive")
    if not isinstance(payload["sha256"], str) or len(payload["sha256"]) != 64:
        raise TrainingCheckpointError("manifest payload SHA-256 is invalid")
    return value


def save_training_checkpoint(
    path: Path,
    *,
    model: nn.Module,
    optimizer: torch.optim.Optimizer,
    scheduler: Any | None,
    scaler: Any | None,
    counters: Mapping[str, Any],
    league: Mapping[str, Any],
    rollout_boundary: Mapping[str, Any],
    include_cuda_rng: bool = True,
) -> dict[str, Any]:
    payload = _checkpoint_payload(
        model=model,
        optimizer=optimizer,
        scheduler=scheduler,
        scaler=scaler,
        counters=counters,
        league=league,
        rollout_boundary=rollout_boundary,
        include_cuda_rng=include_cuda_rng,
    )
    buffer = io.BytesIO()
    torch.save(payload, buffer)
    raw = buffer.getvalue()
    if not raw or len(raw) > MAX_CHECKPOINT_BYTES:
        raise TrainingCheckpointError("training checkpoint is empty or exceeds the size limit")
    digest = _sha256(raw)
    manifest = {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "kind": MANIFEST_KIND,
        "payload": {"path": path.name, "bytes": len(raw), "sha256": digest},
    }
    manifest_raw = canonical_json_bytes(manifest)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    temporary_manifest = _manifest_path(path).with_name(_manifest_path(path).name + ".partial")
    try:
        temporary.write_bytes(raw)
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary_manifest.write_bytes(manifest_raw)
        with temporary_manifest.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary_manifest, _manifest_path(path))
    finally:
        temporary.unlink(missing_ok=True)
        temporary_manifest.unlink(missing_ok=True)
    return {"payload_bytes": len(raw), "payload_sha256": digest, "manifest": manifest}


def _load_payload(path: Path, *, expected_sha256: str | None = None) -> tuple[dict[str, Any], str, int]:
    manifest_path = _manifest_path(path)
    try:
        manifest_raw = manifest_path.read_bytes()
        raw = path.read_bytes()
    except OSError as error:
        raise TrainingCheckpointError(f"cannot read training checkpoint: {error}") from error
    manifest = _parse_manifest(manifest_raw)
    record = manifest["payload"]
    digest = _sha256(raw)
    if record["path"] != path.name or record["bytes"] != len(raw) or record["sha256"] != digest:
        raise TrainingCheckpointError("training checkpoint payload differs from manifest")
    if expected_sha256 is not None and digest != expected_sha256:
        raise TrainingCheckpointError("training checkpoint SHA-256 differs from expected")
    if len(raw) > MAX_CHECKPOINT_BYTES:
        raise TrainingCheckpointError("training checkpoint exceeds the size limit")
    try:
        loaded = torch.load(io.BytesIO(raw), map_location="cpu", weights_only=True)
    except Exception as error:
        raise TrainingCheckpointError(f"restricted training checkpoint load failed: {error}") from error
    return _validate_payload(loaded), digest, len(raw)


def load_training_checkpoint_model_state(
    path: Path,
    *,
    model: nn.Module,
    expected_sha256: str | None = None,
) -> LoadedTrainingCheckpointV1:
    """Load only model weights from a validated training checkpoint.

    Optimizer, scheduler, scaler and RNG state are intentionally left untouched.
    This is the warm-start path for a new training distribution or optimizer run.
    """
    payload, digest, size = _load_payload(path, expected_sha256=expected_sha256)
    current_model = model.state_dict()
    saved_model = payload["model_state"]
    if set(current_model) != set(saved_model):
        raise TrainingCheckpointError("checkpoint model keys differ from current model")
    for name, tensor in current_model.items():
        saved = saved_model[name]
        if not isinstance(saved, Tensor) or saved.shape != tensor.shape or saved.dtype != tensor.dtype:
            raise TrainingCheckpointError(f"checkpoint model tensor differs for {name}")
    try:
        model.load_state_dict(saved_model, strict=True)
    except (KeyError, TypeError, ValueError, RuntimeError) as error:
        raise TrainingCheckpointError(f"training checkpoint model cannot be restored: {error}") from error
    return LoadedTrainingCheckpointV1(
        counters=dict(payload["counters"]),
        league=dict(payload["league"]),
        rollout_boundary=dict(payload["rollout_boundary"]),
        payload_sha256=digest,
        payload_bytes=size,
        restored_rng_states=(),
    )


def restore_training_checkpoint(
    path: Path,
    *,
    model: nn.Module,
    optimizer: torch.optim.Optimizer,
    scheduler: Any | None,
    scaler: Any | None,
    expected_sha256: str | None = None,
    restore_rng: bool = True,
) -> LoadedTrainingCheckpointV1:
    payload, digest, size = _load_payload(path, expected_sha256=expected_sha256)
    current_model = model.state_dict()
    saved_model = payload["model_state"]
    if set(current_model) != set(saved_model):
        raise TrainingCheckpointError("checkpoint model keys differ from current model")
    for name, tensor in current_model.items():
        saved = saved_model[name]
        if not isinstance(saved, Tensor) or saved.shape != tensor.shape or saved.dtype != tensor.dtype:
            raise TrainingCheckpointError(f"checkpoint model tensor differs for {name}")
    if (payload["scheduler_state"] is None) != (scheduler is None):
        raise TrainingCheckpointError("checkpoint scheduler presence differs from current run")
    if (payload["scaler_state"] is None) != (scaler is None):
        raise TrainingCheckpointError("checkpoint scaler presence differs from current run")
    try:
        model.load_state_dict(saved_model, strict=True)
        optimizer.load_state_dict(payload["optimizer_state"])
        if scheduler is not None:
            scheduler.load_state_dict(payload["scheduler_state"])
        if scaler is not None:
            scaler.load_state_dict(payload["scaler_state"])
    except (KeyError, TypeError, ValueError, RuntimeError) as error:
        raise TrainingCheckpointError(f"training checkpoint state cannot be restored: {error}") from error
    restored_rng = restore_rng_states(payload["rng_states"]) if restore_rng else ()
    return LoadedTrainingCheckpointV1(
        counters=dict(payload["counters"]),
        league=dict(payload["league"]),
        rollout_boundary=dict(payload["rollout_boundary"]),
        payload_sha256=digest,
        payload_bytes=size,
        restored_rng_states=restored_rng,
    )
