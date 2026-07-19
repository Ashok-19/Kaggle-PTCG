from __future__ import annotations

import hashlib
import io
import json
import math
import re
import stat
import struct
from collections import OrderedDict
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence
import zipfile

import numpy as np
import torch
from torch import Tensor

from ptcg_rl.g1.models import stable_hash
from ptcg_rl.g2.card_table import CardTableError, CardTableV1, verify_card_table
from ptcg_rl.g2.models import ProjectedDecisionV1, model_schema_sha256
from ptcg_rl.g2.network import (
    PTCGPolicyV1,
    PolicyConfigV1,
    collate_projected,
    policy_metadata,
)

CHECKPOINT_SCHEMA_VERSION = 1
CHECKPOINT_KIND = "KPTCG_G2_POLICY_CHECKPOINT"
STATE_FORMAT = "canonical-little-endian-tensor-v1"
STATE_MAGIC = b"KPTCG-G2-STATE\x00\x01"
CHECKPOINT_ATOL = 1e-5
CHECKPOINT_RTOL = 0.0
ARCHIVE_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
ARCHIVE_MODE = stat.S_IFREG | 0o600
ARCHIVE_ENTRIES = (
    "card-table-v1.json",
    "manifest.json",
    "reference-v1.json",
    "state-v1.bin",
)
PAYLOAD_ENTRIES = tuple(name for name in ARCHIVE_ENTRIES if name != "manifest.json")
MAX_PACKAGE_BYTES = 64 * 1024 * 1024
MAX_ENTRY_BYTES = 48 * 1024 * 1024
MAX_STATE_ENTRIES = 10_000
MAX_TENSOR_NAME_BYTES = 1_024
MAX_TENSOR_NDIM = 8
MAX_TENSOR_ELEMENTS = 100_000_000
MAX_JSON_BYTES = 8 * 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
TENSOR_NAME_RE = re.compile(r"^[A-Za-z0-9_.]+$")

_DTYPE_TO_CODE: dict[torch.dtype, int] = {
    torch.float32: 1,
    torch.int64: 2,
    torch.bool: 3,
}
_CODE_TO_DTYPE: dict[int, tuple[torch.dtype, np.dtype[Any]]] = {
    1: (torch.float32, np.dtype("<f4")),
    2: (torch.int64, np.dtype("<i8")),
    3: (torch.bool, np.dtype("|b1")),
}
_DTYPE_NAMES = {
    torch.float32: "float32",
    torch.int64: "int64",
    torch.bool: "bool",
}


class CheckpointError(ValueError):
    pass


@dataclass(frozen=True)
class LoadedCheckpointV1:
    model: PTCGPolicyV1
    manifest: dict[str, Any]
    reference: dict[str, Any]
    package_sha256: str
    package_bytes: int


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _require_sha256(value: Any, name: str) -> str:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise CheckpointError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _require_commit(value: Any, name: str = "source commit") -> str:
    if not isinstance(value, str) or not COMMIT_RE.fullmatch(value):
        raise CheckpointError(f"{name} must be a lowercase 40-character Git commit")
    return value


def _require_int(value: Any, name: str, minimum: int = 0, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CheckpointError(f"{name} must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        raise CheckpointError(f"{name} is outside the allowed range")
    return value


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    observed = set(value)
    if observed != expected:
        raise CheckpointError(
            f"{name} keys differ: missing={sorted(expected - observed)}, "
            f"unexpected={sorted(observed - expected)}"
        )


def _safe_relative_path(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or any(ord(character) < 32 for character in value)
    ):
        raise CheckpointError(f"{name} must be a nonempty canonical POSIX relative path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise CheckpointError(f"{name} is not a safe canonical relative path")
    return path.as_posix()


def canonical_json_bytes(value: Any) -> bytes:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as error:
        raise CheckpointError(f"value cannot be encoded as canonical JSON: {error}") from error
    return encoded.encode("utf-8") + b"\n"


def _parse_canonical_json(raw: bytes, name: str) -> dict[str, Any]:
    if len(raw) > MAX_JSON_BYTES:
        raise CheckpointError(f"{name} exceeds the JSON size limit")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise CheckpointError(f"{name} is not valid UTF-8 JSON") from error
    if not isinstance(value, dict):
        raise CheckpointError(f"{name} root must be an object")
    if canonical_json_bytes(value) != raw:
        raise CheckpointError(f"{name} is not canonical JSON")
    return value


def _tensor_bytes(tensor: Tensor) -> bytes:
    value = tensor.detach().cpu().contiguous()
    if value.layout != torch.strided:
        raise CheckpointError("only strided tensors are supported")
    if value.dtype not in _DTYPE_TO_CODE:
        raise CheckpointError(f"unsupported checkpoint tensor dtype: {value.dtype}")
    if value.ndim > MAX_TENSOR_NDIM:
        raise CheckpointError("checkpoint tensor rank exceeds the format limit")
    if value.numel() > MAX_TENSOR_ELEMENTS:
        raise CheckpointError("checkpoint tensor element count exceeds the format limit")
    if value.dtype.is_floating_point and not torch.isfinite(value).all():
        raise CheckpointError("checkpoint tensors must not contain NaN or infinity")
    numpy_dtype = _CODE_TO_DTYPE[_DTYPE_TO_CODE[value.dtype]][1]
    array = value.numpy().astype(numpy_dtype, copy=False)
    return array.tobytes(order="C")


def state_dict_sha256(state_dict: Mapping[str, Tensor]) -> str:
    digest = hashlib.sha256()
    for name in sorted(state_dict):
        tensor = state_dict[name].detach().cpu().contiguous()
        raw = _tensor_bytes(tensor)
        digest.update(name.encode("utf-8"))
        digest.update(str(tensor.dtype).encode("ascii"))
        digest.update(json.dumps(list(tensor.shape)).encode("ascii"))
        digest.update(raw)
    return digest.hexdigest()


def encode_state_dict(
    state_dict: Mapping[str, Tensor],
) -> tuple[bytes, list[dict[str, Any]]]:
    if not isinstance(state_dict, Mapping) or not state_dict:
        raise CheckpointError("state dictionary must be a nonempty mapping")
    names = sorted(state_dict)
    if len(names) > MAX_STATE_ENTRIES:
        raise CheckpointError("state dictionary has too many entries")
    if len(set(names)) != len(names):
        raise CheckpointError("state dictionary contains duplicate names")
    output = io.BytesIO()
    output.write(STATE_MAGIC)
    output.write(struct.pack("<I", len(names)))
    records: list[dict[str, Any]] = []
    for name in names:
        if not isinstance(name, str) or not TENSOR_NAME_RE.fullmatch(name):
            raise CheckpointError(f"invalid state tensor name: {name!r}")
        name_raw = name.encode("utf-8")
        if len(name_raw) > MAX_TENSOR_NAME_BYTES:
            raise CheckpointError(f"state tensor name is too long: {name}")
        tensor = state_dict[name].detach().cpu().contiguous()
        raw = _tensor_bytes(tensor)
        dtype_code = _DTYPE_TO_CODE[tensor.dtype]
        shape = [int(value) for value in tensor.shape]
        output.write(struct.pack("<I", len(name_raw)))
        output.write(name_raw)
        output.write(struct.pack("<B", dtype_code))
        output.write(struct.pack("<B", len(shape)))
        for dimension in shape:
            output.write(struct.pack("<Q", dimension))
        output.write(struct.pack("<Q", len(raw)))
        output.write(raw)
        records.append(
            {
                "name": name,
                "dtype": _DTYPE_NAMES[tensor.dtype],
                "shape": shape,
                "bytes": len(raw),
                "sha256": _sha256(raw),
            }
        )
    return output.getvalue(), records


class _StateReader:
    def __init__(self, raw: bytes) -> None:
        self.raw = raw
        self.offset = 0

    def read(self, count: int, name: str) -> bytes:
        if count < 0 or self.offset + count > len(self.raw):
            raise CheckpointError(f"state tensor stream is truncated while reading {name}")
        result = self.raw[self.offset : self.offset + count]
        self.offset += count
        return result

    def unpack(self, fmt: str, name: str) -> tuple[Any, ...]:
        size = struct.calcsize(fmt)
        return struct.unpack(fmt, self.read(size, name))


def decode_state_dict(raw: bytes) -> tuple[OrderedDict[str, Tensor], list[dict[str, Any]]]:
    reader = _StateReader(raw)
    if reader.read(len(STATE_MAGIC), "magic") != STATE_MAGIC:
        raise CheckpointError("state tensor stream magic or version differs")
    count = _require_int(reader.unpack("<I", "entry count")[0], "state entry count", 1, MAX_STATE_ENTRIES)
    state: OrderedDict[str, Tensor] = OrderedDict()
    records: list[dict[str, Any]] = []
    previous_name = ""
    for index in range(count):
        name_length = _require_int(
            reader.unpack("<I", f"name length {index}")[0],
            f"state tensor name length {index}",
            1,
            MAX_TENSOR_NAME_BYTES,
        )
        try:
            name = reader.read(name_length, f"name {index}").decode("utf-8")
        except UnicodeError as error:
            raise CheckpointError("state tensor name is not valid UTF-8") from error
        if not TENSOR_NAME_RE.fullmatch(name):
            raise CheckpointError(f"invalid state tensor name: {name!r}")
        if name <= previous_name:
            raise CheckpointError("state tensor names must be unique and strictly sorted")
        previous_name = name
        dtype_code = reader.unpack("<B", f"dtype {name}")[0]
        if dtype_code not in _CODE_TO_DTYPE:
            raise CheckpointError(f"unsupported state tensor dtype code for {name}")
        torch_dtype, numpy_dtype = _CODE_TO_DTYPE[dtype_code]
        ndim = _require_int(
            reader.unpack("<B", f"rank {name}")[0],
            f"state tensor rank {name}",
            0,
            MAX_TENSOR_NDIM,
        )
        shape = [
            _require_int(
                reader.unpack("<Q", f"shape {name}")[0],
                f"state tensor dimension {name}",
                0,
                MAX_TENSOR_ELEMENTS,
            )
            for _ in range(ndim)
        ]
        elements = math.prod(shape) if shape else 1
        if elements > MAX_TENSOR_ELEMENTS:
            raise CheckpointError(f"state tensor {name} exceeds the element limit")
        data_length = _require_int(
            reader.unpack("<Q", f"data length {name}")[0],
            f"state tensor byte length {name}",
            0,
            MAX_ENTRY_BYTES,
        )
        expected_length = elements * numpy_dtype.itemsize
        if data_length != expected_length:
            raise CheckpointError(f"state tensor {name} byte length differs from dtype and shape")
        data = reader.read(data_length, f"data {name}")
        array = np.frombuffer(data, dtype=numpy_dtype).astype(
            {torch.float32: np.float32, torch.int64: np.int64, torch.bool: np.bool_}[torch_dtype],
            copy=True,
        )
        tensor = torch.from_numpy(array).reshape(shape)
        if tensor.dtype != torch_dtype:
            raise CheckpointError(f"state tensor {name} decoded to an unexpected dtype")
        if tensor.dtype.is_floating_point and not torch.isfinite(tensor).all():
            raise CheckpointError(f"state tensor {name} contains NaN or infinity")
        state[name] = tensor
        records.append(
            {
                "name": name,
                "dtype": _DTYPE_NAMES[torch_dtype],
                "shape": shape,
                "bytes": len(data),
                "sha256": _sha256(data),
            }
        )
    if reader.offset != len(raw):
        raise CheckpointError("state tensor stream has trailing bytes")
    canonical, canonical_records = encode_state_dict(state)
    if canonical != raw or canonical_records != records:
        raise CheckpointError("state tensor stream is not canonical")
    return state, records


def _tensor_values(value: Tensor) -> list[float | int | bool | str]:
    result: list[float | int | bool | str] = []
    for item in value.detach().cpu().reshape(-1).tolist():
        if isinstance(item, bool):
            result.append(item)
            continue
        if isinstance(item, int):
            result.append(item)
            continue
        number = float(item)
        if math.isnan(number):
            raise CheckpointError("checkpoint reference contains NaN")
        if number == float("-inf"):
            result.append("-inf")
        elif number == float("inf"):
            result.append("inf")
        else:
            result.append(number)
    return result


def _tensor_record(value: Tensor) -> dict[str, Any]:
    return {"shape": [int(item) for item in value.shape], "values": _tensor_values(value)}


def build_checkpoint_reference(
    model: PTCGPolicyV1,
    decisions: Sequence[ProjectedDecisionV1],
    fixture_id: str = "g2-policy-qualification-synthetic-v1",
) -> dict[str, Any]:
    if not fixture_id or not isinstance(fixture_id, str):
        raise CheckpointError("checkpoint fixture ID must be a nonempty string")
    if not decisions:
        raise CheckpointError("checkpoint reference requires at least one projected decision")
    was_training = model.training
    model.eval()
    try:
        device = next(model.parameters()).device
        batch = collate_projected(decisions, device=device)
        with torch.inference_mode():
            initial_hidden = model.initial_hidden(batch.batch_size, device)
            first = model(batch, initial_hidden)
            output = model(batch, first.hidden)
            option_count = int(batch.option_offsets[1] - batch.option_offsets[0])
            if option_count <= 0:
                raise CheckpointError("the first reference decision must expose an option")
            options = output.option_embeddings[:option_count]
            available = batch.option_available[:option_count].clone()
            available_indices = torch.nonzero(available, as_tuple=False).reshape(-1)
            if not len(available_indices):
                raise CheckpointError("the first reference decision has no available option")
            selected_index = int(available_indices[0])
            prefix = model.decoder_initial(output.hidden[0])
            step1_logits = model.decoder_logits(prefix, options, available, False)
            step1_log_probability = torch.log_softmax(step1_logits, dim=0)[selected_index]
            advanced = model.decoder_advance(prefix, options[selected_index])
            remaining = available.clone()
            remaining[selected_index] = False
            step2_logits = model.decoder_logits(advanced, options, remaining, True)
            stop_index = option_count
            step2_log_probability = torch.log_softmax(step2_logits, dim=0)[stop_index]
            compound = step1_log_probability + step2_log_probability
        reference = {
            "schema_version": 1,
            "fixture_id": fixture_id,
            "input_sha256": stable_hash(tuple(asdict(item) for item in decisions)),
            "tolerance": {"atol": CHECKPOINT_ATOL, "rtol": CHECKPOINT_RTOL},
            "action_trace": {
                "selected_option_indices": [selected_index],
                "stop_selected": True,
                "step_log_probabilities": [
                    float(step1_log_probability.detach().cpu()),
                    float(step2_log_probability.detach().cpu()),
                ],
                "compound_log_probability": float(compound.detach().cpu()),
            },
            "outputs": {
                "option_logits": _tensor_record(output.option_logits),
                "values": _tensor_record(output.values),
                "first_hidden": _tensor_record(first.hidden),
                "hidden": _tensor_record(output.hidden),
                "decoder_step1_logits": _tensor_record(step1_logits),
                "decoder_step2_logits": _tensor_record(step2_logits),
                "decoder_advanced": _tensor_record(advanced),
            },
        }
        canonical_json_bytes(reference)
        return reference
    finally:
        model.train(was_training)


def _compare_values(expected: Any, observed: Any, path: str, stats: dict[str, Any]) -> None:
    if isinstance(expected, dict):
        if not isinstance(observed, dict) or set(expected) != set(observed):
            raise CheckpointError(f"checkpoint reference structure differs at {path}")
        for key in sorted(expected):
            _compare_values(expected[key], observed[key], f"{path}.{key}", stats)
        return
    if isinstance(expected, list):
        if not isinstance(observed, list) or len(expected) != len(observed):
            raise CheckpointError(f"checkpoint reference list differs at {path}")
        for index, (left, right) in enumerate(zip(expected, observed, strict=True)):
            _compare_values(left, right, f"{path}[{index}]", stats)
        return
    if isinstance(expected, bool) or expected is None or isinstance(expected, str):
        stats["exact_values"] += 1
        if expected != observed:
            raise CheckpointError(f"checkpoint reference exact value differs at {path}")
        return
    if isinstance(expected, int) and not isinstance(expected, bool):
        stats["exact_values"] += 1
        if expected != observed:
            raise CheckpointError(f"checkpoint reference integer differs at {path}")
        return
    if not isinstance(expected, (float, int)) or not isinstance(observed, (float, int)):
        raise CheckpointError(f"checkpoint reference value type differs at {path}")
    left = float(expected)
    right = float(observed)
    if not math.isfinite(left) or not math.isfinite(right):
        raise CheckpointError(f"checkpoint reference numeric value is not finite at {path}")
    difference = abs(left - right)
    stats["numeric_values"] += 1
    if difference > stats["max_abs_diff"]:
        stats["max_abs_diff"] = difference
        stats["max_abs_diff_path"] = path
    if difference > CHECKPOINT_ATOL:
        raise CheckpointError(
            f"checkpoint reference numerical drift at {path}: {difference} > {CHECKPOINT_ATOL}"
        )


def verify_checkpoint_reference(
    model: PTCGPolicyV1,
    decisions: Sequence[ProjectedDecisionV1],
    expected: Mapping[str, Any],
) -> dict[str, Any]:
    if not isinstance(expected, Mapping):
        raise CheckpointError("checkpoint reference must be an object")
    _require_exact_keys(
        expected,
        {"schema_version", "fixture_id", "input_sha256", "tolerance", "action_trace", "outputs"},
        "checkpoint reference",
    )
    if expected["schema_version"] != 1:
        raise CheckpointError("unsupported checkpoint reference schema version")
    _require_sha256(expected["input_sha256"], "checkpoint reference input SHA-256")
    tolerance = expected["tolerance"]
    if not isinstance(tolerance, Mapping):
        raise CheckpointError("checkpoint reference tolerance must be an object")
    _require_exact_keys(tolerance, {"atol", "rtol"}, "checkpoint reference tolerance")
    if tolerance["atol"] != CHECKPOINT_ATOL or tolerance["rtol"] != CHECKPOINT_RTOL:
        raise CheckpointError("checkpoint reference tolerance differs from the frozen contract")
    observed = build_checkpoint_reference(model, decisions, fixture_id=str(expected["fixture_id"]))
    stats: dict[str, Any] = {
        "numeric_values": 0,
        "exact_values": 0,
        "max_abs_diff": 0.0,
        "max_abs_diff_path": None,
    }
    _compare_values(dict(expected), observed, "reference", stats)
    return {"status": "PASS", **stats}


def _file_record(raw: bytes) -> dict[str, Any]:
    return {"bytes": len(raw), "sha256": _sha256(raw)}


def _source_records(source_files: Mapping[str, bytes]) -> list[dict[str, Any]]:
    if not source_files:
        raise CheckpointError("checkpoint source file set must not be empty")
    records = []
    for path in sorted(source_files):
        safe = _safe_relative_path(path, "checkpoint source path")
        raw = source_files[path]
        if not isinstance(raw, bytes):
            raise CheckpointError(f"checkpoint source file {safe} must be bytes")
        records.append({"path": safe, **_file_record(raw)})
    return records


def _write_archive(path: Path, entries: Mapping[str, bytes]) -> None:
    if set(entries) != set(ARCHIVE_ENTRIES):
        raise CheckpointError("checkpoint archive entry set differs from the contract")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(entries):
            info = zipfile.ZipInfo(name, date_time=ARCHIVE_TIMESTAMP)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = ARCHIVE_MODE << 16
            info.internal_attr = 0
            info.flag_bits = 0
            archive.writestr(info, entries[name], compress_type=zipfile.ZIP_STORED)
    temporary.replace(path)


def build_checkpoint_package(
    output_path: Path,
    model: PTCGPolicyV1,
    card_table_bytes: bytes,
    reference: Mapping[str, Any],
    source_commit: str,
    source_files: Mapping[str, bytes],
    qualification_evidence_path: str,
    qualification_evidence_sha256: str,
    artifact_id: str = "g2-policy-checkpoint-v1",
) -> dict[str, Any]:
    source_commit = _require_commit(source_commit)
    evidence_path = _safe_relative_path(
        qualification_evidence_path, "qualification evidence path"
    )
    evidence_sha = _require_sha256(
        qualification_evidence_sha256, "qualification evidence SHA-256"
    )
    if not isinstance(artifact_id, str) or not artifact_id:
        raise CheckpointError("checkpoint artifact ID must be a nonempty string")
    try:
        table_value = json.loads(card_table_bytes.decode("utf-8"))
        if not isinstance(table_value, Mapping):
            raise CheckpointError("card table root must be an object")
        table = CardTableV1.from_mapping(table_value)
        verify_card_table(table)
    except (UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError, CardTableError) as error:
        if isinstance(error, CheckpointError):
            raise
        raise CheckpointError(f"checkpoint card table is invalid: {error}") from error
    metadata = policy_metadata(model)
    if metadata["card_table_sha256"] != table.table_sha256:
        raise CheckpointError("model and packaged card table hashes differ")
    state_bytes, tensor_records = encode_state_dict(model.state_dict())
    state_sha = state_dict_sha256(model.state_dict())
    reference_value = dict(reference)
    reference_bytes = canonical_json_bytes(reference_value)
    payload_entries = {
        "card-table-v1.json": card_table_bytes,
        "reference-v1.json": reference_bytes,
        "state-v1.bin": state_bytes,
    }
    manifest = {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "artifact_id": artifact_id,
        "kind": CHECKPOINT_KIND,
        "source": {
            "commit": source_commit,
            "files": _source_records(source_files),
        },
        "model_schema_sha256": model_schema_sha256(),
        "model": metadata,
        "state": {
            "format": STATE_FORMAT,
            "semantic_sha256": state_sha,
            "entry_count": len(tensor_records),
            "bytes": len(state_bytes),
            "tensors": tensor_records,
        },
        "reference": {
            "path": "reference-v1.json",
            "fixture_id": reference_value.get("fixture_id"),
            "input_sha256": reference_value.get("input_sha256"),
            "atol": CHECKPOINT_ATOL,
            "rtol": CHECKPOINT_RTOL,
            **_file_record(reference_bytes),
        },
        "files": {name: _file_record(raw) for name, raw in sorted(payload_entries.items())},
        "evidence": {
            "path": evidence_path,
            "sha256": evidence_sha,
            "qualification_state_sha256": state_sha,
        },
        "authorization": {
            "optimizer_included": False,
            "training_state_included": False,
            "training_loop_ran": False,
            "pickle_used": False,
        },
    }
    _validate_manifest(manifest)
    manifest_bytes = canonical_json_bytes(manifest)
    entries = {**payload_entries, "manifest.json": manifest_bytes}
    _write_archive(output_path, entries)
    package_raw = output_path.read_bytes()
    if len(package_raw) > MAX_PACKAGE_BYTES:
        raise CheckpointError("checkpoint package exceeds the package size limit")
    return {
        "manifest": manifest,
        "manifest_sha256": _sha256(manifest_bytes),
        "package_bytes": len(package_raw),
        "package_sha256": _sha256(package_raw),
    }


def _validate_file_record(value: Any, name: str) -> None:
    if not isinstance(value, Mapping):
        raise CheckpointError(f"{name} must be an object")
    _require_exact_keys(value, {"bytes", "sha256"}, name)
    _require_int(value["bytes"], f"{name} bytes", 0, MAX_ENTRY_BYTES)
    _require_sha256(value["sha256"], f"{name} SHA-256")


def _validate_manifest(manifest: Mapping[str, Any]) -> None:
    _require_exact_keys(
        manifest,
        {
            "schema_version",
            "artifact_id",
            "kind",
            "source",
            "model_schema_sha256",
            "model",
            "state",
            "reference",
            "files",
            "evidence",
            "authorization",
        },
        "checkpoint manifest",
    )
    if manifest["schema_version"] != CHECKPOINT_SCHEMA_VERSION:
        raise CheckpointError("unsupported checkpoint manifest schema version")
    if not isinstance(manifest["artifact_id"], str) or not manifest["artifact_id"]:
        raise CheckpointError("checkpoint artifact ID must be a nonempty string")
    if manifest["kind"] != CHECKPOINT_KIND:
        raise CheckpointError("checkpoint kind differs from the contract")
    source = manifest["source"]
    if not isinstance(source, Mapping):
        raise CheckpointError("checkpoint source must be an object")
    _require_exact_keys(source, {"commit", "files"}, "checkpoint source")
    _require_commit(source["commit"])
    if not isinstance(source["files"], list) or not source["files"]:
        raise CheckpointError("checkpoint source files must be a nonempty list")
    source_paths: list[str] = []
    for record in source["files"]:
        if not isinstance(record, Mapping):
            raise CheckpointError("checkpoint source file record must be an object")
        _require_exact_keys(record, {"path", "bytes", "sha256"}, "source file record")
        source_paths.append(_safe_relative_path(record["path"], "source file path"))
        _require_int(record["bytes"], "source file bytes", 0, MAX_ENTRY_BYTES)
        _require_sha256(record["sha256"], "source file SHA-256")
    if source_paths != sorted(source_paths) or len(source_paths) != len(set(source_paths)):
        raise CheckpointError("checkpoint source file paths must be unique and sorted")
    _require_sha256(manifest["model_schema_sha256"], "model schema SHA-256")
    model = manifest["model"]
    if not isinstance(model, Mapping):
        raise CheckpointError("checkpoint model metadata must be an object")
    _require_exact_keys(
        model,
        {
            "schema_version",
            "architecture_sha256",
            "config_sha256",
            "card_table_sha256",
            "trainable_parameters",
            "config",
        },
        "checkpoint model metadata",
    )
    if model["schema_version"] != 1:
        raise CheckpointError("unsupported model metadata schema version")
    for key in ("architecture_sha256", "config_sha256", "card_table_sha256"):
        _require_sha256(model[key], f"model {key}")
    _require_int(model["trainable_parameters"], "trainable parameter count", 1, 1_999_999)
    if not isinstance(model["config"], Mapping):
        raise CheckpointError("checkpoint model config must be an object")
    try:
        config = PolicyConfigV1(**dict(model["config"]))
    except (TypeError, ValueError) as error:
        raise CheckpointError(f"checkpoint model config is invalid: {error}") from error
    if config.config_sha256 != model["config_sha256"]:
        raise CheckpointError("checkpoint model config SHA-256 differs from canonical config")
    state = manifest["state"]
    if not isinstance(state, Mapping):
        raise CheckpointError("checkpoint state metadata must be an object")
    _require_exact_keys(
        state,
        {"format", "semantic_sha256", "entry_count", "bytes", "tensors"},
        "checkpoint state metadata",
    )
    if state["format"] != STATE_FORMAT:
        raise CheckpointError("checkpoint state format differs from the contract")
    _require_sha256(state["semantic_sha256"], "checkpoint state semantic SHA-256")
    entry_count = _require_int(state["entry_count"], "checkpoint state entry count", 1, MAX_STATE_ENTRIES)
    _require_int(state["bytes"], "checkpoint state bytes", 1, MAX_ENTRY_BYTES)
    tensors = state["tensors"]
    if not isinstance(tensors, list) or len(tensors) != entry_count:
        raise CheckpointError("checkpoint tensor record count differs")
    names = []
    for record in tensors:
        if not isinstance(record, Mapping):
            raise CheckpointError("checkpoint tensor record must be an object")
        _require_exact_keys(record, {"name", "dtype", "shape", "bytes", "sha256"}, "tensor record")
        name = record["name"]
        if not isinstance(name, str) or not TENSOR_NAME_RE.fullmatch(name):
            raise CheckpointError("checkpoint tensor record name is invalid")
        names.append(name)
        if record["dtype"] not in set(_DTYPE_NAMES.values()):
            raise CheckpointError("checkpoint tensor record dtype is invalid")
        if not isinstance(record["shape"], list) or len(record["shape"]) > MAX_TENSOR_NDIM:
            raise CheckpointError("checkpoint tensor record shape is invalid")
        for dimension in record["shape"]:
            _require_int(dimension, "checkpoint tensor dimension", 0, MAX_TENSOR_ELEMENTS)
        _require_int(record["bytes"], "checkpoint tensor bytes", 0, MAX_ENTRY_BYTES)
        _require_sha256(record["sha256"], "checkpoint tensor SHA-256")
    if names != sorted(names) or len(names) != len(set(names)):
        raise CheckpointError("checkpoint tensor record names must be unique and sorted")
    reference = manifest["reference"]
    if not isinstance(reference, Mapping):
        raise CheckpointError("checkpoint reference metadata must be an object")
    _require_exact_keys(
        reference,
        {"path", "fixture_id", "input_sha256", "atol", "rtol", "bytes", "sha256"},
        "checkpoint reference metadata",
    )
    if reference["path"] != "reference-v1.json":
        raise CheckpointError("checkpoint reference path differs from the contract")
    if not isinstance(reference["fixture_id"], str) or not reference["fixture_id"]:
        raise CheckpointError("checkpoint reference fixture ID is invalid")
    _require_sha256(reference["input_sha256"], "checkpoint reference input SHA-256")
    if reference["atol"] != CHECKPOINT_ATOL or reference["rtol"] != CHECKPOINT_RTOL:
        raise CheckpointError("checkpoint reference tolerance differs")
    _validate_file_record({"bytes": reference["bytes"], "sha256": reference["sha256"]}, "reference file")
    files = manifest["files"]
    if not isinstance(files, Mapping) or set(files) != set(PAYLOAD_ENTRIES):
        raise CheckpointError("checkpoint payload file records differ from the contract")
    for name in PAYLOAD_ENTRIES:
        _validate_file_record(files[name], f"checkpoint file {name}")
    evidence = manifest["evidence"]
    if not isinstance(evidence, Mapping):
        raise CheckpointError("checkpoint evidence metadata must be an object")
    _require_exact_keys(
        evidence,
        {"path", "sha256", "qualification_state_sha256"},
        "checkpoint evidence metadata",
    )
    _safe_relative_path(evidence["path"], "checkpoint evidence path")
    _require_sha256(evidence["sha256"], "checkpoint evidence SHA-256")
    _require_sha256(
        evidence["qualification_state_sha256"],
        "checkpoint qualification state SHA-256",
    )
    if evidence["qualification_state_sha256"] != state["semantic_sha256"]:
        raise CheckpointError("checkpoint state differs from qualification evidence state")
    authorization = manifest["authorization"]
    if not isinstance(authorization, Mapping):
        raise CheckpointError("checkpoint authorization must be an object")
    expected_authorization = {
        "optimizer_included": False,
        "training_state_included": False,
        "training_loop_ran": False,
        "pickle_used": False,
    }
    if dict(authorization) != expected_authorization:
        raise CheckpointError("checkpoint authorization violates the no-training contract")


def _read_archive(raw: bytes) -> dict[str, bytes]:
    if not raw or len(raw) > MAX_PACKAGE_BYTES:
        raise CheckpointError("checkpoint package is empty or exceeds the size limit")
    try:
        with zipfile.ZipFile(io.BytesIO(raw), "r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise CheckpointError("checkpoint archive contains duplicate entries")
            if set(names) != set(ARCHIVE_ENTRIES) or len(names) != len(ARCHIVE_ENTRIES):
                raise CheckpointError("checkpoint archive entries differ from the contract")
            if names != sorted(names):
                raise CheckpointError("checkpoint archive entries are not sorted")
            total = 0
            for info in infos:
                _safe_relative_path(info.filename, "checkpoint archive entry")
                if info.is_dir():
                    raise CheckpointError("checkpoint archive must not contain directories")
                if info.date_time != ARCHIVE_TIMESTAMP:
                    raise CheckpointError("checkpoint archive timestamp differs from the contract")
                if info.compress_type != zipfile.ZIP_STORED or info.compress_size != info.file_size:
                    raise CheckpointError("checkpoint archive entries must be uncompressed")
                if info.create_system != 3:
                    raise CheckpointError("checkpoint archive creator system differs")
                if info.flag_bits != 0 or info.internal_attr != 0:
                    raise CheckpointError("checkpoint archive flags differ from the contract")
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode) or mode != ARCHIVE_MODE:
                    raise CheckpointError("checkpoint archive entry mode differs from the contract")
                if info.file_size > MAX_ENTRY_BYTES:
                    raise CheckpointError("checkpoint archive entry exceeds the size limit")
                total += info.file_size
            if total > MAX_PACKAGE_BYTES:
                raise CheckpointError("checkpoint archive expanded size exceeds the limit")
            return {name: archive.read(name) for name in names}
    except (zipfile.BadZipFile, RuntimeError, OSError) as error:
        if isinstance(error, CheckpointError):
            raise
        raise CheckpointError(f"cannot read checkpoint archive: {error}") from error


def verify_source_tree(root: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    _validate_manifest(manifest)
    resolved_root = root.resolve()
    checked = 0
    for record in manifest["source"]["files"]:
        relative = _safe_relative_path(record["path"], "checkpoint source path")
        candidate = resolved_root / relative
        current = resolved_root
        for part in PurePosixPath(relative).parts:
            current /= part
            if current.is_symlink():
                raise CheckpointError(f"checkpoint source path is a symlink: {relative}")
        resolved = candidate.resolve()
        if not resolved.is_relative_to(resolved_root) or not resolved.is_file():
            raise CheckpointError(f"checkpoint source file is missing or escapes root: {relative}")
        raw = resolved.read_bytes()
        if len(raw) != record["bytes"] or _sha256(raw) != record["sha256"]:
            raise CheckpointError(f"checkpoint source file differs: {relative}")
        checked += 1
    return {"status": "PASS", "files": checked}


def load_checkpoint_package(
    path: Path,
    *,
    device: torch.device | str = "cpu",
    expected_package_sha256: str | None = None,
    expected_source_commit: str | None = None,
    source_root: Path | None = None,
) -> LoadedCheckpointV1:
    try:
        package_raw = path.read_bytes()
    except OSError as error:
        raise CheckpointError(f"cannot read checkpoint package {path}: {error}") from error
    package_sha = _sha256(package_raw)
    if expected_package_sha256 is not None and package_sha != _require_sha256(
        expected_package_sha256, "expected package SHA-256"
    ):
        raise CheckpointError("checkpoint package SHA-256 differs from expected")
    entries = _read_archive(package_raw)
    manifest = _parse_canonical_json(entries["manifest.json"], "checkpoint manifest")
    _validate_manifest(manifest)
    if expected_source_commit is not None and manifest["source"]["commit"] != _require_commit(
        expected_source_commit, "expected source commit"
    ):
        raise CheckpointError("checkpoint source commit differs from expected")
    if manifest["model_schema_sha256"] != model_schema_sha256():
        raise CheckpointError("checkpoint model schema SHA-256 differs from current source")
    for name in PAYLOAD_ENTRIES:
        record = manifest["files"][name]
        raw = entries[name]
        if len(raw) != record["bytes"] or _sha256(raw) != record["sha256"]:
            raise CheckpointError(f"checkpoint payload hash differs for {name}")
    if source_root is not None:
        verify_source_tree(source_root, manifest)
    try:
        table_value = json.loads(entries["card-table-v1.json"].decode("utf-8"))
        if not isinstance(table_value, Mapping):
            raise CheckpointError("checkpoint card table root must be an object")
        table = CardTableV1.from_mapping(table_value)
        verify_card_table(table)
    except (UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError, CardTableError) as error:
        if isinstance(error, CheckpointError):
            raise
        raise CheckpointError(f"checkpoint card table is invalid: {error}") from error
    reference = _parse_canonical_json(entries["reference-v1.json"], "checkpoint reference")
    if _sha256(entries["reference-v1.json"]) != manifest["reference"]["sha256"]:
        raise CheckpointError("checkpoint reference SHA-256 differs")
    if reference.get("fixture_id") != manifest["reference"]["fixture_id"]:
        raise CheckpointError("checkpoint reference fixture ID differs from manifest")
    if reference.get("input_sha256") != manifest["reference"]["input_sha256"]:
        raise CheckpointError("checkpoint reference input SHA-256 differs from manifest")
    state, tensor_records = decode_state_dict(entries["state-v1.bin"])
    if len(entries["state-v1.bin"]) != manifest["state"]["bytes"]:
        raise CheckpointError("checkpoint state byte count differs from manifest")
    if tensor_records != manifest["state"]["tensors"]:
        raise CheckpointError("checkpoint tensor records differ from manifest")
    state_sha = state_dict_sha256(state)
    if state_sha != manifest["state"]["semantic_sha256"]:
        raise CheckpointError("checkpoint state semantic SHA-256 differs from manifest")
    if state_sha != manifest["evidence"]["qualification_state_sha256"]:
        raise CheckpointError("checkpoint state differs from qualification evidence")
    try:
        config = PolicyConfigV1(**dict(manifest["model"]["config"]))
        model = PTCGPolicyV1(table, config)
        model.load_state_dict(state, strict=True)
    except (TypeError, ValueError, RuntimeError) as error:
        raise CheckpointError(f"checkpoint model cannot load state: {error}") from error
    observed_metadata = policy_metadata(model)
    if observed_metadata != manifest["model"]:
        raise CheckpointError("checkpoint model metadata differs after load")
    if model_schema_sha256() != manifest["model_schema_sha256"]:
        raise CheckpointError("checkpoint model schema differs after load")
    model.eval()
    model.to(device)
    return LoadedCheckpointV1(
        model=model,
        manifest=dict(manifest),
        reference=reference,
        package_sha256=package_sha,
        package_bytes=len(package_raw),
    )
