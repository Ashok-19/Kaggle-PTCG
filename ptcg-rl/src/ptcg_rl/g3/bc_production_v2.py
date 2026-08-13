from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import torch
from torch import Tensor

from ptcg_rl.g2.checkpoint import load_checkpoint_package
from ptcg_rl.g3.bc_canary import (
    TeacherEpisodeV1,
    _action_nll,
    _episode_chunk_loss,
    _set_deterministic_seed,
    build_semantic_loader_plan,
)
from ptcg_rl.g3.checkpoint import save_training_checkpoint
from ptcg_rl.g3.ppo import require_finite_gradients
from ptcg_rl.replay.semantic_loader import SemanticReplayLoader


PUBLICATION_RECORD_ID = "e01-production-bc-input-publication-request-v1"
REMEDIATION_RECORD_ID = "e01-production-bc-retained-dataset-remediation-request-v1"
TRAINING_RECORD_ID = "e01-production-recurrent-bc-request-v2"
STRATA = ("seat_0_loss", "seat_0_win", "seat_1_loss", "seat_1_win")
CORPUS_MANIFEST_PATH = "reports/artifacts/e01-approved-replay-corpus-manifest-v3.json"
CORPUS_MANIFEST_FILE_SHA256 = "c032694d3601d2570c8e2199c886e452af11f2d72b47379ad08761f16a6b3267"
CORPUS_MANIFEST_SELF_HASH = "bb6319e23f3d5b12bd9ed7383b0f3e007dd7059cbf39afcd5325af12392c35a9"


class ProductionBCContractError(ValueError):
    """Raised when a production-BC publication or training contract differs."""


@dataclass(frozen=True)
class ChunkRef:
    episode_index: int
    episode_id: int
    teacher_key: str
    stratum: str
    start: int


@dataclass(frozen=True)
class ProductionAssets:
    request: dict[str, Any]
    request_path: Path
    manifest: dict[str, Any]
    manifest_path: Path


@dataclass(frozen=True)
class TrainingRunOptions:
    """Optional runtime limits for bounded engineering runs.

    Production defaults are unchanged when this object is omitted. Smoke mode
    selects a small deterministic train/validation subset and never produces an
    evaluation-eligible checkpoint.
    """

    smoke_sample: bool = False
    maximum_epochs: int | None = None
    maximum_optimizer_steps: int | None = None
    validation_episode_limit: int = 8


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def pretty_self_hash(value: Mapping[str, Any], field: str) -> str:
    payload = copy.deepcopy(dict(value))
    payload.pop(field, None)
    raw = (
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    return sha256_bytes(raw)


def canonical_listing_hash(records: Sequence[Mapping[str, Any]]) -> str:
    payload = [dict(item) for item in records]
    raw = (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode(
        "utf-8"
    )
    return sha256_bytes(raw)


def remote_inventory_hash(records: Sequence[Mapping[str, Any]]) -> str:
    payload = [{"name": str(item["name"]), "bytes": int(item["bytes"])} for item in records]
    raw = (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode(
        "utf-8"
    )
    return sha256_bytes(raw)


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProductionBCContractError(f"cannot load {label}: {error}") from error
    if not isinstance(value, dict):
        raise ProductionBCContractError(f"{label} must be a JSON object")
    return value


def _require_sha(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ProductionBCContractError(f"{label} must be a lowercase SHA-256")
    return value


def _safe_relative(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ProductionBCContractError(f"{label} must be a canonical relative path")
    path = Path(value)
    if path.is_absolute() or path.as_posix() != value or any(part in {"", ".", ".."} for part in path.parts):
        raise ProductionBCContractError(f"{label} must be a canonical relative path")
    return value


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ProductionBCContractError(f"{label} must be a positive integer")
    return value


def _load_manifest(root: Path, request: Mapping[str, Any]) -> tuple[Path, dict[str, Any]]:
    manifest_meta = request.get("corpus_manifest")
    if not isinstance(manifest_meta, Mapping):
        raise ProductionBCContractError("corpus_manifest must be an object")
    path = root / _safe_relative(manifest_meta.get("path"), "corpus manifest path")
    if path.relative_to(root).as_posix() != CORPUS_MANIFEST_PATH:
        raise ProductionBCContractError("production BC must use frozen corpus v3")
    raw = path.read_bytes()
    if sha256_bytes(raw) != CORPUS_MANIFEST_FILE_SHA256:
        raise ProductionBCContractError("corpus-v3 file hash differs")
    manifest = _load_object(path, "corpus-v3 manifest")
    if manifest.get("manifest_sha256") != CORPUS_MANIFEST_SELF_HASH:
        raise ProductionBCContractError("corpus-v3 self-hash field differs")
    if pretty_self_hash(manifest, "manifest_sha256") != CORPUS_MANIFEST_SELF_HASH:
        raise ProductionBCContractError("corpus-v3 self-hash does not reproduce")
    if manifest_meta.get("sha256") != CORPUS_MANIFEST_FILE_SHA256:
        raise ProductionBCContractError("request corpus-v3 file hash differs")
    if manifest_meta.get("self_hash") != CORPUS_MANIFEST_SELF_HASH:
        raise ProductionBCContractError("request corpus-v3 self-hash differs")
    corpus = manifest.get("qualified_training_corpus", {})
    if corpus.get("episodes") != 362 or corpus.get("policy_loss_targets") != 25056:
        raise ProductionBCContractError("corpus-v3 counts differ")
    return path, manifest


def _load_training_manifest(root: Path, request: Mapping[str, Any]) -> tuple[Path, dict[str, Any]]:
    """Load corpus v3 for training using structural checks rather than hash gates."""
    manifest_meta = request.get("corpus_manifest")
    if not isinstance(manifest_meta, Mapping):
        raise ProductionBCContractError("corpus_manifest must be an object")
    path = root / _safe_relative(manifest_meta.get("path"), "corpus manifest path")
    if path.relative_to(root).as_posix() != CORPUS_MANIFEST_PATH:
        raise ProductionBCContractError("production BC must use corpus v3")
    manifest = _load_object(path, "corpus-v3 manifest")
    corpus = manifest.get("qualified_training_corpus", {})
    if corpus.get("episodes") != 362 or corpus.get("policy_loss_targets") != 25056:
        raise ProductionBCContractError("corpus-v3 counts differ")
    return path, manifest


def retained_publication_records(manifest: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    records = manifest.get("qualified_training_corpus", {}).get("episode_records", [])
    selected: list[dict[str, Any]] = []
    for item in records:
        if item.get("teacher_key") not in {"flg", "dries"} or item.get("split") not in {
            "train",
            "validation",
        }:
            continue
        source_path = _safe_relative(item.get("path"), "retained replay source path")
        selected.append(
            {
                "episode_id": int(item["episode_id"]),
                "split": str(item["split"]),
                "teacher_key": str(item["teacher_key"]),
                "stratum": str(item["stratum"]),
                "source_path": source_path,
                "dataset_path": f"episodes/{int(item['episode_id'])}.json",
                "bytes": int(item["bytes"]),
                "sha256": _require_sha(item.get("sha256"), "retained replay SHA-256"),
            }
        )
    selected.sort(key=lambda item: int(item["episode_id"]))
    if len(selected) != 58 or sum(item["bytes"] for item in selected) != 341559745:
        raise ProductionBCContractError("retained train/validation publication selection differs")
    if sum(item["split"] == "train" for item in selected) != 50:
        raise ProductionBCContractError("retained train publication count differs")
    if sum(item["split"] == "validation" for item in selected) != 8:
        raise ProductionBCContractError("retained validation publication count differs")
    if any(item["split"] == "test" for item in selected):
        raise ProductionBCContractError("test record entered publication selection")
    return tuple(selected)


def training_records(manifest: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    records = manifest.get("qualified_training_corpus", {}).get("episode_records", [])
    selected: list[dict[str, Any]] = []
    for item in records:
        if item.get("split") not in {"train", "validation"}:
            continue
        source_review = str(item.get("source_review", ""))
        teacher_key = str(item["teacher_key"])
        if teacher_key in {"flg", "dries"}:
            source = "retained_private"
            dataset_path = f"{int(item['episode_id'])}.json"
        elif "module-1324" in source_review or "corpus-target-supplement" in source_review:
            source = "august_4_daily"
            dataset_path = _safe_relative(item.get("source_dataset_path"), "August 4 dataset path")
        elif teacher_key == "majkel":
            source = "august_3_daily"
            source_dataset_path = item.get("source_dataset_path")
            dataset_path = (
                _safe_relative(source_dataset_path, "August 3 dataset path")
                if source_dataset_path is not None
                else f"{int(item['episode_id'])}.json"
            )
        else:
            raise ProductionBCContractError("unknown corpus-v3 teacher source")
        selected.append(
            {
                "episode_id": int(item["episode_id"]),
                "split": str(item["split"]),
                "teacher_key": teacher_key,
                "teacher_player_index": int(item["teacher_player_index"]),
                "stratum": str(item["stratum"]),
                "source": source,
                "dataset_path": dataset_path,
                "bytes": int(item["bytes"]),
                "teacher_active_requests": int(item["teacher_active_requests"]),
                "policy_loss_targets": int(item["policy_loss_targets"]),
            }
        )
    selected.sort(key=lambda item: int(item["episode_id"]))
    if len(selected) != 316:
        raise ProductionBCContractError("production train/validation episode count differs")
    train = [item for item in selected if item["split"] == "train"]
    validation = [item for item in selected if item["split"] == "validation"]
    if len(train) != 284 or sum(item["policy_loss_targets"] for item in train) != 19646:
        raise ProductionBCContractError("production train split differs")
    if len(validation) != 32 or sum(item["policy_loss_targets"] for item in validation) != 2318:
        raise ProductionBCContractError("production validation split differs")
    if any(item["split"] == "test" for item in selected):
        raise ProductionBCContractError("test record entered production selection")
    return tuple(selected)


def select_smoke_records(
    records: Sequence[Mapping[str, Any]], *, validation_episode_limit: int = 8
) -> tuple[dict[str, Any], ...]:
    """Select a small deterministic subset while preserving training strata."""
    if validation_episode_limit <= 0:
        raise ProductionBCContractError("smoke validation episode limit must be positive")

    train = [dict(item) for item in records if item["split"] == "train"]
    validation = [dict(item) for item in records if item["split"] == "validation"]
    selected_train: list[dict[str, Any]] = []

    for stratum in STRATA:
        candidates = [
            item
            for item in train
            if item["teacher_key"] == "majkel" and item["stratum"] == stratum
        ]
        if not candidates:
            raise ProductionBCContractError(f"smoke sample has no Majkel record for {stratum}")
        selected_train.append(min(candidates, key=lambda item: int(item["episode_id"])))

    legacy_added = 0
    for teacher_key in ("flg", "dries"):
        candidates = [item for item in train if item["teacher_key"] == teacher_key]
        if candidates:
            selected_train.append(min(candidates, key=lambda item: int(item["episode_id"])))
            legacy_added += 1
    if legacy_added == 0:
        raise ProductionBCContractError("smoke sample has no legacy teacher record")

    selected_validation = sorted(validation, key=lambda item: int(item["episode_id"]))[
        :validation_episode_limit
    ]
    if not selected_validation:
        raise ProductionBCContractError("smoke sample has no validation records")

    selected = selected_train + selected_validation
    selected.sort(key=lambda item: int(item["episode_id"]))
    return tuple(selected)


def metadata_schedule_bound(records: Sequence[Mapping[str, Any]], sequence_length: int) -> dict[str, int]:
    primary: dict[str, int] = {stratum: 0 for stratum in STRATA}
    legacy = 0
    for item in records:
        if item["split"] != "train":
            continue
        chunks = math.ceil(int(item["teacher_active_requests"]) / sequence_length)
        if item["teacher_key"] == "majkel":
            primary[str(item["stratum"])] += chunks
        else:
            legacy += chunks
    if any(value <= 0 for value in primary.values()) or legacy <= 0:
        raise ProductionBCContractError("balanced sampling group is empty")
    per_epoch = max(legacy, max(primary.values()))
    return {
        "legacy_chunk_upper": legacy,
        "primary_stratum_chunk_upper_max": max(primary.values()),
        "balanced_steps_per_epoch_upper": per_epoch,
    }


def _verify_runner(root: Path, request: Mapping[str, Any]) -> None:
    runner = request.get("runner")
    if not isinstance(runner, Mapping):
        raise ProductionBCContractError("runner binding must be an object")
    path = root / _safe_relative(runner.get("path"), "runner path")
    expected = _require_sha(runner.get("sha256"), "runner SHA-256")
    if sha256_file(path) != expected:
        raise ProductionBCContractError("runner SHA-256 differs")
    implementation = request.get("implementation")
    if not isinstance(implementation, Mapping):
        raise ProductionBCContractError("implementation binding must be an object")
    implementation_path = root / _safe_relative(
        implementation.get("path"), "implementation path"
    )
    implementation_sha = _require_sha(
        implementation.get("sha256"), "implementation SHA-256"
    )
    if sha256_file(implementation_path) != implementation_sha:
        raise ProductionBCContractError("implementation SHA-256 differs")


def validate_publication_request(root: Path, request_path: Path) -> ProductionAssets:
    request = _load_object(request_path, "publication request")
    if request.get("schema_version") != 1 or request.get("record_id") != PUBLICATION_RECORD_ID:
        raise ProductionBCContractError("publication request identity differs")
    if request.get("source_path") != request_path.relative_to(root).as_posix():
        raise ProductionBCContractError("publication request source_path differs")
    if request.get("status") != "READY_UNAUTHORIZED" or request.get("request_ready") is not True:
        raise ProductionBCContractError("publication request is not ready and unauthorized")
    authorization = request.get("authorization")
    if not isinstance(authorization, Mapping) or any(value is not False for value in authorization.values()):
        raise ProductionBCContractError("publication request contains an authorization")
    manifest_path, manifest = _load_manifest(root, request)
    expected = retained_publication_records(manifest)
    if request.get("records") != list(expected):
        raise ProductionBCContractError("publication record listing differs from corpus v3")
    publication = request.get("publication", {})
    if publication.get("private") is not True or publication.get("dataset_version") != 1:
        raise ProductionBCContractError("publication target must be private version 1")
    if publication.get("files") != 58 or publication.get("bytes") != 341559745:
        raise ProductionBCContractError("publication aggregate differs")
    if publication.get("listing_sha256") != canonical_listing_hash(expected):
        raise ProductionBCContractError("publication listing hash differs")
    _verify_runner(root, request)
    return ProductionAssets(request=request, request_path=request_path, manifest=manifest, manifest_path=manifest_path)


def validate_retained_dataset_remediation_request(
    root: Path, request_path: Path
) -> dict[str, Any]:
    request = _load_object(request_path, "retained dataset remediation request")
    if request.get("schema_version") != 1 or request.get("record_id") != REMEDIATION_RECORD_ID:
        raise ProductionBCContractError("retained dataset remediation request identity differs")
    if request.get("source_path") != request_path.relative_to(root).as_posix():
        raise ProductionBCContractError("retained dataset remediation request source_path differs")
    if request.get("status") != "READY_UNAUTHORIZED" or request.get("request_ready") is not True:
        raise ProductionBCContractError("retained dataset remediation request is not ready and unauthorized")
    authorization = request.get("authorization")
    if not isinstance(authorization, Mapping) or any(value is not False for value in authorization.values()):
        raise ProductionBCContractError("retained dataset remediation request contains an authorization")
    _, manifest = _load_manifest(root, request)
    retained = retained_publication_records(manifest)
    expected_records = [
        {
            "episode_id": int(item["episode_id"]),
            "split": str(item["split"]),
            "remote_name": f"{int(item['episode_id'])}.json",
            "bytes": int(item["bytes"]),
            "sha256": str(item["sha256"]),
        }
        for item in retained
    ]
    if request.get("records") != expected_records:
        raise ProductionBCContractError("retained dataset remediation record listing differs")
    dataset = request.get("dataset")
    if not isinstance(dataset, Mapping):
        raise ProductionBCContractError("retained dataset remediation dataset binding must be an object")
    expected_dataset = {
        "ref": "ashok205/kptcg-e01-production-bc-retained-inputs",
        "dataset_id": 11514316,
        "version": 1,
        "private": True,
        "status": "READY",
        "files": 58,
        "bytes": 341559745,
        "remote_inventory_sha256": "d03105906d9e066045410bc4da07ec7bd045f5b1285d35ddc516c1e7960b5c43",
        "path_contract": "root_basename",
    }
    if dict(dataset) != expected_dataset:
        raise ProductionBCContractError("retained dataset remediation dataset identity differs")
    remote_records = [{"name": item["remote_name"], "bytes": item["bytes"]} for item in expected_records]
    if remote_inventory_hash(remote_records) != expected_dataset["remote_inventory_sha256"]:
        raise ProductionBCContractError("retained dataset remediation inventory hash differs")
    if request.get("remediation_method") != "contract_only_adopt_verified_root_basenames":
        raise ProductionBCContractError("retained dataset remediation method differs")
    evidence = request.get("evidence")
    expected_evidence = {
        "raw_verification": {
            "path": "reports/artifacts/raw/e01-production-bc-retained-dataset-verification-20260805-v1.json",
            "sha256": "1a08b64f1f492a09536fb4894797b1e3cd59fa34283532f83ec538280157c991",
            "self_hash": "f2c3a75129117b88a88320f26d9b2de4fdd816a462cc559338a0ad986afea864",
            "self_hash_field": "evidence_sha256",
        },
        "execution_review": {
            "path": "reports/artifacts/e01-production-bc-input-publication-execution-review-v1.json",
            "sha256": "ad80752c394408153a4ea1db4790b100cc6a3444cc63e8a388e0431a76b53765",
            "self_hash": "54bf03e9c243f45522174acdc47d30c0af4a002362327468aa6a83100a15c750",
            "self_hash_field": "review_sha256",
        },
        "incident": {
            "path": "reports/incidents/e01-production-bc-retained-dataset-path-flattening-v1.json",
            "sha256": "7d4f993cd5f2b85413590708f50e94d5a6cd7fc53b7abb97f58af86aec50f7c3",
            "self_hash": "5baf9bd2fa399d7858fb55bde665dee26177fcdd72ed00b0ed0c2c8bef25774b",
            "self_hash_field": "incident_sha256",
        },
        "decision": {
            "path": "docs/decisions/DEC-034_E01_PRODUCTION_BC_RETAINED_DATASET_PATH_FLATTENING.md",
            "sha256": "28c4b3ea1c256ce68507481729850c93bd4fc70c4d1dc63f1ab2f108387172c8",
        },
    }
    if evidence != expected_evidence:
        raise ProductionBCContractError("retained dataset remediation evidence binding differs")
    for item in expected_evidence.values():
        path = root / str(item["path"])
        if sha256_file(path) != str(item["sha256"]):
            raise ProductionBCContractError("retained dataset remediation evidence file hash differs")
        self_hash_field = item.get("self_hash_field")
        if self_hash_field is not None:
            value = _load_object(path, "retained dataset remediation evidence")
            if value.get(str(self_hash_field)) != item.get("self_hash"):
                raise ProductionBCContractError("retained dataset remediation evidence self-hash field differs")
            if pretty_self_hash(value, str(self_hash_field)) != item.get("self_hash"):
                raise ProductionBCContractError("retained dataset remediation evidence self-hash does not reproduce")
    return request


def validate_training_request(root: Path, request_path: Path) -> ProductionAssets:
    request = _load_object(request_path, "production BC request")
    if request.get("schema_version") != 1 or request.get("record_id") != TRAINING_RECORD_ID:
        raise ProductionBCContractError("production BC request identity differs")
    if request.get("source_path") != request_path.relative_to(root).as_posix():
        raise ProductionBCContractError("production BC request source_path differs")
    if request.get("request_ready") is not True:
        raise ProductionBCContractError("production BC request is not ready")
    manifest_path, manifest = _load_training_manifest(root, request)
    records = training_records(manifest)
    corpus = request.get("corpus", {})
    if corpus.get("train_episodes") != 284 or corpus.get("validation_episodes") != 32:
        raise ProductionBCContractError("training split episode counts differ")
    if corpus.get("train_policy_loss_targets") != 19646 or corpus.get("validation_policy_loss_targets") != 2318:
        raise ProductionBCContractError("training split target counts differ")
    if corpus.get("test_episodes_sealed") != 46 or corpus.get("test_policy_loss_targets_sealed") != 3092:
        raise ProductionBCContractError("sealed test split counts differ")
    execution = request.get("execution", {})
    if execution.get("platform") != "private_kaggle_cpu":
        raise ProductionBCContractError("production BC platform differs")
    if any(execution.get(name) is not False for name in ("internet", "gpu", "tpu")):
        raise ProductionBCContractError("production BC accelerator/network boundary differs")
    if execution.get("optimizer") != "AdamW" or float(execution.get("learning_rate", 0.0)) != 0.0001:
        raise ProductionBCContractError("production BC optimizer differs")
    if int(execution.get("recurrent_sequence_length", 0)) != 32:
        raise ProductionBCContractError("production BC recurrent sequence length differs")
    if int(execution.get("maximum_epochs", 0)) != 4 or int(execution.get("maximum_optimizer_steps", 0)) != 844:
        raise ProductionBCContractError("production BC epoch or step cap differs")
    if execution.get("primary_chunks_per_step") != 4 or execution.get("legacy_chunks_per_step") != 1:
        raise ProductionBCContractError("production BC 80/20 sampling contract differs")
    bound = metadata_schedule_bound(records, 32)
    if bound != request.get("metadata_schedule_bound"):
        raise ProductionBCContractError("production BC metadata schedule bound differs")
    if bound["balanced_steps_per_epoch_upper"] * 4 != 844:
        raise ProductionBCContractError("production BC optimizer cap does not derive from metadata")
    retained_dependency = request.get("retained_dataset_dependency", {})
    retained_dataset = retained_dependency.get("dataset")
    if not isinstance(retained_dataset, Mapping):
        raise ProductionBCContractError("retained dataset dependency must be an object")
    expected_retained = {
        "ref": "ashok205/kptcg-e01-production-bc-retained-inputs",
        "dataset_id": 11514316,
        "version": 1,
        "private": True,
        "status": "READY",
        "files": 58,
        "bytes": 341559745,
        "path_contract": "root_basename",
    }
    for key, expected in expected_retained.items():
        if retained_dataset.get(key) != expected:
            raise ProductionBCContractError(f"retained dataset {key} differs")
    for name in ("initial_checkpoint", "card_data"):
        asset = request.get("assets", {}).get(name, {})
        path = root / _safe_relative(asset.get("path"), f"{name} path")
        if not path.is_file():
            raise ProductionBCContractError(f"{name} file is missing")
        if path.stat().st_size != _positive_int(asset.get("bytes"), f"{name} bytes"):
            raise ProductionBCContractError(f"{name} byte count differs")
    return ProductionAssets(request=request, request_path=request_path, manifest=manifest, manifest_path=manifest_path)


def _ordered_chunks(chunks: Sequence[ChunkRef], seed: int, epoch: int, bucket: str) -> tuple[ChunkRef, ...]:
    def key(item: ChunkRef) -> str:
        raw = f"{seed}|{epoch}|{bucket}|{item.episode_id}|{item.start}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    return tuple(sorted(chunks, key=key))


def build_balanced_schedule(
    chunks: Sequence[ChunkRef], *, seed: int, epochs: int
) -> tuple[tuple[tuple[ChunkRef, ...], ...], ...]:
    if epochs <= 0:
        raise ProductionBCContractError("epochs must be positive")
    primary = {stratum: [] for stratum in STRATA}
    legacy: list[ChunkRef] = []
    for chunk in chunks:
        if chunk.teacher_key == "majkel":
            if chunk.stratum not in primary:
                raise ProductionBCContractError("unknown primary stratum")
            primary[chunk.stratum].append(chunk)
        else:
            legacy.append(chunk)
    if any(not values for values in primary.values()) or not legacy:
        raise ProductionBCContractError("balanced chunk schedule has an empty group")
    result: list[tuple[tuple[ChunkRef, ...], ...]] = []
    for epoch in range(epochs):
        ordered_primary = {
            stratum: _ordered_chunks(values, seed, epoch, f"majkel:{stratum}")
            for stratum, values in primary.items()
        }
        ordered_legacy = _ordered_chunks(legacy, seed, epoch, "legacy")
        steps = max(len(ordered_legacy), *(len(values) for values in ordered_primary.values()))
        epoch_steps: list[tuple[ChunkRef, ...]] = []
        for index in range(steps):
            batch = tuple(
                ordered_primary[stratum][index % len(ordered_primary[stratum])] for stratum in STRATA
            ) + (ordered_legacy[index % len(ordered_legacy)],)
            epoch_steps.append(batch)
        result.append(tuple(epoch_steps))
    return tuple(result)


def _approval(path: Path, request_path: Path, runner_path: Path, kind: str) -> dict[str, Any]:
    approval = _load_object(path, f"{kind} approval receipt")
    if approval.get("kind") != kind or approval.get("approved_by") != "user":
        raise ProductionBCContractError("approval receipt identity differs")
    if approval.get("request_sha256") != sha256_file(request_path):
        raise ProductionBCContractError("approval receipt request hash differs")
    if approval.get("runner_sha256") != sha256_file(runner_path):
        raise ProductionBCContractError("approval receipt runner hash differs")
    return approval


def stage_authorized_publication(
    root: Path, request_path: Path, approval_path: Path, output_dir: Path
) -> dict[str, Any]:
    assets = validate_publication_request(root, request_path)
    runner_path = root / str(assets.request["runner"]["path"])
    approval = _approval(approval_path, request_path, runner_path, "E01_PRODUCTION_BC_INPUT_PUBLICATION_APPROVAL_V1")
    required = approval.get("authorization", {})
    for field in ("replay_body_read", "copy", "stage", "private_dataset_create", "private_dataset_upload"):
        if required.get(field) is not True:
            raise ProductionBCContractError(f"publication approval does not authorize {field}")
    if any(required.get(field) is not False for field in ("training", "optimizer_steps", "model_promotion", "submission", "git_commit", "git_push")):
        raise ProductionBCContractError("publication approval expands forbidden scope")
    if output_dir.exists():
        raise ProductionBCContractError("publication staging output already exists")
    records = retained_publication_records(assets.manifest)
    dataset_dir = output_dir / "dataset"
    episodes_dir = dataset_dir / "episodes"
    episodes_dir.mkdir(parents=True, exist_ok=False)
    staged: list[dict[str, Any]] = []
    for item in records:
        source = root / str(item["source_path"])
        raw = source.read_bytes()
        if len(raw) != item["bytes"] or sha256_bytes(raw) != item["sha256"]:
            raise ProductionBCContractError(f"retained replay differs for episode {item['episode_id']}")
        destination = dataset_dir / str(item["dataset_path"])
        destination.write_bytes(raw)
        staged.append({key: item[key] for key in ("episode_id", "dataset_path", "bytes", "sha256", "split")})
    dataset_metadata = {
        "title": "KPTCG E01 Production BC Retained Inputs",
        "id": str(assets.request["publication"]["dataset_ref"]),
        "licenses": [{"name": "CC0-1.0"}],
        "isPrivate": True,
    }
    (dataset_dir / "dataset-metadata.json").write_text(
        json.dumps(dataset_metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    content = {
        "schema_version": 1,
        "status": "PASS_STAGED_PRIVATE_PUBLICATION_INPUT_ONLY",
        "request_sha256": sha256_file(request_path),
        "records": staged,
        "files": len(staged),
        "bytes": sum(item["bytes"] for item in staged),
        "listing_sha256": canonical_listing_hash(records),
        "test_replay_files": 0,
        "training_labels": 0,
        "optimizer_steps": 0,
        "training": False,
    }
    (output_dir / "publication-report.json").write_text(
        json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return content


def _resolve_replay(root: Path, dataset_path: str) -> Path:
    direct = root / dataset_path
    nested = root / "episodes" / Path(dataset_path).name
    candidates = [path for path in (direct, nested) if path.is_file()]
    if len(candidates) != 1:
        raise ProductionBCContractError(f"expected exactly one mounted replay for {dataset_path}")
    return candidates[0]


def _load_teacher_episodes(
    records: Sequence[Mapping[str, Any]], roots: Mapping[str, Path], card_data_sha256: str
) -> tuple[TeacherEpisodeV1, ...]:
    with tempfile.TemporaryDirectory(prefix="kptcg-production-bc-") as temporary:
        staged = Path(temporary) / "episodes"
        staged.mkdir()
        for item in records:
            source = _resolve_replay(roots[str(item["source"])], str(item["dataset_path"]))
            if source.stat().st_size != int(item["bytes"]):
                raise ProductionBCContractError(
                    f"mounted replay byte count differs for episode {item['episode_id']}"
                )
            destination = staged / f"{int(item['episode_id'])}.json"
            try:
                os.link(source, destination)
            except OSError:
                destination.write_bytes(source.read_bytes())
        plan_records = [
            {"episode_id": int(item["episode_id"]), "bytes": int(item["bytes"])} for item in records
        ]
        plan = build_semantic_loader_plan(plan_records)
        by_id = {int(item["episode_id"]): item for item in records}
        grouped: dict[int, list[Any]] = {episode_id: [] for episode_id in by_id}
        loader = SemanticReplayLoader(plan, staged, card_data_sha256=card_data_sha256)
        for decision in loader:
            record = by_id[int(decision.episode_id)]
            if decision.agent_index == int(record["teacher_player_index"]):
                grouped[int(decision.episode_id)].append(decision)
    episodes: list[TeacherEpisodeV1] = []
    for episode_id in sorted(grouped):
        record = by_id[episode_id]
        decisions = tuple(grouped[episode_id])
        meaningful = sum(not decision.request.has_only_one_outcome for decision in decisions)
        if meaningful != int(record["policy_loss_targets"]):
            raise ProductionBCContractError(f"policy-loss target count differs for episode {episode_id}")
        episodes.append(
            TeacherEpisodeV1(
                episode_id=episode_id,
                teacher_player_index=int(record["teacher_player_index"]),
                decisions=decisions,
                expected_meaningful_decisions=meaningful,
                teacher_key=str(record["teacher_key"]),
                stratum=str(record["stratum"]),
            )
        )
    return tuple(episodes)


def _validation_nll(model: Any, episodes: Sequence[TeacherEpisodeV1]) -> tuple[float, int]:
    model.eval()
    losses: list[float] = []
    with torch.inference_mode():
        for episode in episodes:
            hidden = model.initial_hidden(1, "cpu")
            for decision in episode.decisions:
                loss, hidden, _ = _action_nll(model, decision, hidden)
                hidden = hidden.detach()
                if loss is not None:
                    losses.append(float(loss))
    if not losses or any(not math.isfinite(value) for value in losses):
        raise ProductionBCContractError("validation loss stream is empty or nonfinite")
    return sum(losses) / len(losses), len(losses)


def execute_training(
    root: Path,
    request_path: Path,
    dataset_roots: Mapping[str, Path],
    output_dir: Path,
    options: TrainingRunOptions | None = None,
) -> dict[str, Any]:
    assets = validate_training_request(root, request_path)
    if output_dir.exists():
        raise ProductionBCContractError("production BC output directory already exists")
    required_roots = {"retained_private", "august_3_daily", "august_4_daily"}
    if set(dataset_roots) != required_roots:
        raise ProductionBCContractError("production BC dataset roots differ")
    request = assets.request
    execution = request["execution"]
    torch.set_num_threads(int(execution["torch_num_threads"]))
    torch.set_num_interop_threads(int(execution["torch_num_interop_threads"]))
    _set_deterministic_seed(int(execution["seed"]))
    run_options = options or TrainingRunOptions()
    records = training_records(assets.manifest)
    if run_options.smoke_sample:
        records = select_smoke_records(
            records, validation_episode_limit=run_options.validation_episode_limit
        )
    episodes = _load_teacher_episodes(records, dataset_roots, str(request["assets"]["card_data"]["sha256"]))
    by_id = {int(item["episode_id"]): item for item in records}
    train = tuple(episode for episode in episodes if by_id[episode.episode_id]["split"] == "train")
    validation = tuple(episode for episode in episodes if by_id[episode.episode_id]["split"] == "validation")
    chunks: list[ChunkRef] = []
    sequence_length = int(execution["recurrent_sequence_length"])
    for episode_index, episode in enumerate(train):
        for start in range(0, len(episode.decisions), sequence_length):
            window = episode.decisions[start : start + sequence_length]
            if any(not decision.request.has_only_one_outcome for decision in window):
                chunks.append(
                    ChunkRef(
                        episode_index=episode_index,
                        episode_id=episode.episode_id,
                        teacher_key=episode.teacher_key,
                        stratum=episode.stratum,
                        start=start,
                    )
                )
    configured_epochs = int(execution["maximum_epochs"])
    maximum_epochs = (
        configured_epochs
        if run_options.maximum_epochs is None
        else min(configured_epochs, int(run_options.maximum_epochs))
    )
    configured_step_cap = int(execution["maximum_optimizer_steps"])
    maximum_optimizer_steps = (
        configured_step_cap
        if run_options.maximum_optimizer_steps is None
        else min(configured_step_cap, int(run_options.maximum_optimizer_steps))
    )
    if maximum_epochs <= 0 or maximum_optimizer_steps <= 0:
        raise ProductionBCContractError("training runtime limits must be positive")

    full_schedule = build_balanced_schedule(
        chunks, seed=int(execution["seed"]), epochs=maximum_epochs
    )
    limited_schedule: list[tuple[tuple[ChunkRef, ...], ...]] = []
    remaining_steps = maximum_optimizer_steps
    for epoch_steps in full_schedule:
        if remaining_steps <= 0:
            break
        selected_steps = tuple(epoch_steps[:remaining_steps])
        if selected_steps:
            limited_schedule.append(selected_steps)
            remaining_steps -= len(selected_steps)
    schedule = tuple(limited_schedule)
    total_steps = sum(len(epoch) for epoch in schedule)
    if total_steps <= 0 or total_steps > maximum_optimizer_steps:
        raise ProductionBCContractError("derived optimizer schedule violates runtime limits")
    checkpoint = request["assets"]["initial_checkpoint"]
    loaded = load_checkpoint_package(
        root / str(checkpoint["path"]),
        device="cpu",
    )
    model = loaded.model
    baseline_nll, validation_targets = _validation_nll(model, validation)
    model.train()
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(execution["learning_rate"]),
        weight_decay=float(execution["weight_decay"]),
    )
    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda=lambda _step: 1.0)
    output_dir.mkdir(parents=True, exist_ok=False)
    history: list[dict[str, Any]] = [
        {"epoch": 0, "optimizer_steps": 0, "validation_mean_nll": baseline_nll}
    ]
    completed = 0
    checkpoint_receipts: list[dict[str, Any]] = []
    for epoch_index, epoch_steps in enumerate(schedule, start=1):
        for batch in epoch_steps:
            optimizer.zero_grad(set_to_none=True)
            batch_losses: list[Tensor] = []
            for chunk in batch:
                batch_losses.append(
                    _episode_chunk_loss(
                        model,
                        train[chunk.episode_index],
                        chunk.start,
                        sequence_length,
                    )
                )
            loss = torch.stack(batch_losses).mean()
            if not torch.isfinite(loss):
                raise ProductionBCContractError("production BC loss is nonfinite")
            loss.backward()
            require_finite_gradients(tuple(model.parameters()))
            torch.nn.utils.clip_grad_norm_(
                model.parameters(), float(execution["maximum_gradient_norm"]), error_if_nonfinite=True
            )
            optimizer.step()
            scheduler.step()
            completed += 1
        validation_nll, observed_targets = _validation_nll(model, validation)
        if observed_targets != validation_targets:
            raise ProductionBCContractError("validation target count changed across epochs")
        checkpoint_path = output_dir / f"epoch-{epoch_index}.pt"
        save_training_checkpoint(
            checkpoint_path,
            model=model,
            optimizer=optimizer,
            scheduler=scheduler,
            scaler=None,
            counters={"optimizer_steps": completed, "epoch": epoch_index},
            league={
                "kind": (
                    "recurrent-bc-smoke"
                    if run_options.smoke_sample
                    else "production-recurrent-bc-candidate"
                ),
                "production_eligible": False,
            },
            rollout_boundary={"completed_epochs": epoch_index},
            include_cuda_rng=False,
        )
        checkpoint_receipts.append(
            {
                "epoch": epoch_index,
                "path": checkpoint_path.name,
            }
        )
        history.append(
            {
                "epoch": epoch_index,
                "optimizer_steps": completed,
                "validation_mean_nll": validation_nll,
            }
        )
        model.train()
    best = min(history, key=lambda item: (float(item["validation_mean_nll"]), int(item["epoch"])))
    candidate_eligible = (
        not run_options.smoke_sample
        and int(best["epoch"]) > 0
        and float(best["validation_mean_nll"]) < baseline_nll - 1e-6
    )
    report = {
        "schema_version": 1,
        "record_id": (
            "e01-recurrent-bc-smoke-execution-v1"
            if run_options.smoke_sample
            else "e01-production-recurrent-bc-execution-v1"
        ),
        "status": (
            "PASS_SMOKE_TRAINING_COMPLETED"
            if run_options.smoke_sample
            else (
                "PASS_CANDIDATE_READY_FOR_SEPARATE_EVALUATION"
                if candidate_eligible
                else "PASS_NO_IMPROVED_CANDIDATE"
            )
        ),
        "run_kind": "smoke" if run_options.smoke_sample else "production",
        "optimizer_steps": completed,
        "maximum_optimizer_steps": maximum_optimizer_steps,
        "epochs": len(schedule),
        "train_episodes": len(train),
        "validation_episodes": len(validation),
        "train_episode_ids": [episode.episode_id for episode in train],
        "validation_episode_ids": [episode.episode_id for episode in validation],
        "validation_targets": validation_targets,
        "validation_history": history,
        "selected_epoch": int(best["epoch"]),
        "candidate_checkpoint_eligible_for_evaluation_only": candidate_eligible,
        "candidate_checkpoint": (
            None
            if run_options.smoke_sample or int(best["epoch"]) == 0
            else f"epoch-{int(best['epoch'])}.pt"
        ),
        "checkpoint_receipts": checkpoint_receipts,
        "training_labels_materialized": 0,
        "test_replay_bodies_read": 0,
        "gpu": False,
        "tpu": False,
        "model_promoted": False,
        "submission": False,
    }
    (output_dir / "execution-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def execute_authorized_training(
    root: Path,
    request_path: Path,
    _approval_path: Path,
    dataset_roots: Mapping[str, Path],
    output_dir: Path,
) -> dict[str, Any]:
    """Compatibility shim for historical v1/v2 wrappers.

    New training code should call ``execute_training`` directly. The approval
    receipt is intentionally ignored and is no longer part of runtime logic.
    """
    return execute_training(root, request_path, dataset_roots, output_dir)
