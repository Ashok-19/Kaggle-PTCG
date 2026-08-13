from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import os
import platform
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(SOURCE_ROOT / "src"))
sys.path.insert(0, str(SOURCE_ROOT / "scripts"))

import e01_majkel_corpus_expansion_review as prior  # noqa: E402

REQUEST_SHA256 = "d94c12e424ba26a06a4085c7273faeadd512351828b2b2aa84b85bf014a2f92e"
BASE_MANIFEST_SHA256 = "ccc247edbc4cac0aba11c6acb26fc5e2a8c75e0a4f005d1441ce6949c0c4997f"
CARD_DATA_SHA256 = "a0ea63cf7adcb65d35436ce0eb390de6e2e35654a7c67c065a45f4abaa00f373"
DATASET_INVENTORY_SHA256 = "5620e055a25407c47e7744eaa0ffb9ab2a04fe2287b0f6180f54726cf7a00f77"
DATASET_MANIFEST_SHA256 = "bb190f62f0585dc2a1db2b02752a4d7e6fa6de15a800ed9e769d8daecd8bf9a1"
DATASET_REF = "kaggle/pokemon-tcg-ai-battle-episodes-2026-08-04"
DATASET_ID = 11_506_836
DATASET_VERSION = 1
DATASET_FILES = 4_812
DATASET_JSON_FILES = 4_811
DATASET_TOTAL_BYTES = 21_457_813_826
TEACHER_TEAM_ID = 16_374_395
TEACHER_SUBMISSION_ID = 55_186_239
TEACHER_NAME = "Majkel1337"
TEACHER_DECK_SHA256 = "dc8571d0bc2e546a1f85b938696cfc40a1451c68a4ccc1f695e7c3e1c74f1278"
MINIMUM_TARGETS = 25_000
MAXIMUM_FILES = 48
MAXIMUM_BYTES = 180_695_173
OUTPUT_NAMES = (
    "e01-corpus-target-supplement-review-v1.json",
    "e01-approved-replay-corpus-manifest-v3.json",
    "e01-approved-replay-corpus-review-v3.json",
    "e01-corpus-target-supplement-output-manifest-v1.json",
)


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def pretty_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def self_hash(value: Mapping[str, Any], field: str) -> str:
    payload = copy.deepcopy(dict(value))
    payload.pop(field, None)
    return sha_bytes(canonical_bytes(payload))


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".partial")
    partial.write_bytes(pretty_bytes(value))
    partial.replace(path)


def load_approved_inventory(path: Path) -> tuple[dict[str, int], dict[str, Any]]:
    if sha_file(path) != DATASET_INVENTORY_SHA256:
        raise ValueError("approved dataset inventory hash differs")
    inventory: dict[str, int] = {}
    creation_dates: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["name", "total_bytes", "creation_date"]:
            raise ValueError("dataset inventory columns differ")
        for row in reader:
            name = str(row["name"])
            if name in inventory:
                raise ValueError(f"duplicate dataset inventory filename: {name}")
            inventory[name] = int(row["total_bytes"])
            creation_dates[name] = str(row["creation_date"])
    if len(inventory) != DATASET_FILES:
        raise ValueError("dataset inventory file count differs")
    if sum(name.endswith(".json") for name in inventory) != DATASET_JSON_FILES:
        raise ValueError("dataset inventory JSON count differs")
    if sum(inventory.values()) != DATASET_TOTAL_BYTES:
        raise ValueError("dataset inventory total bytes differ")
    if "manifest.csv" not in inventory:
        raise ValueError("dataset inventory manifest entry is missing")
    return inventory, {
        "approved_inventory_sha256": DATASET_INVENTORY_SHA256,
        "approved_files": len(inventory),
        "approved_json_files": sum(name.endswith(".json") for name in inventory),
        "approved_total_bytes": sum(inventory.values()),
        "creation_dates_bound_by_approved_inventory": len(creation_dates),
    }


def locate_dataset_root(
    input_root: Path,
    selected_names: set[str],
    approved_inventory: Mapping[str, int],
) -> tuple[Path, dict[str, Path], dict[str, Any]]:
    candidates = [
        path
        for path in input_root.rglob("*")
        if path.is_dir() and "pokemon-tcg-ai-battle-episodes-2026-08-04" in path.name
    ]
    matches: list[tuple[Path, dict[str, Path], dict[str, int]]] = []
    for candidate in candidates:
        observed_paths: dict[str, Path] = {}
        observed_sizes: dict[str, int] = {}
        duplicate_names: set[str] = set()
        for path in candidate.rglob("*"):
            if not path.is_file():
                continue
            name = path.name
            if name in observed_paths:
                duplicate_names.add(name)
                continue
            observed_paths[name] = path
            observed_sizes[name] = path.stat().st_size
        if duplicate_names:
            continue
        if observed_sizes == dict(approved_inventory):
            matches.append((candidate, observed_paths, observed_sizes))
    if len(matches) != 1:
        raise ValueError(f"expected one exact August 4 dataset inventory, observed {len(matches)}")
    dataset_root, observed_paths, observed_sizes = matches[0]
    if not selected_names <= set(observed_paths):
        raise ValueError("one or more selected filenames are absent from mounted dataset")
    manifest_path = observed_paths["manifest.csv"]
    if sha_file(manifest_path) != DATASET_MANIFEST_SHA256:
        raise ValueError("mounted dataset manifest hash differs")
    selected_index = {name: observed_paths[name] for name in selected_names}
    return dataset_root, selected_index, {
        "dataset_reference": DATASET_REF,
        "dataset_id": DATASET_ID,
        "dataset_version": DATASET_VERSION,
        "dataset_root": str(dataset_root),
        "mounted_files": len(observed_sizes),
        "mounted_json_files": sum(name.endswith(".json") for name in observed_sizes),
        "mounted_total_bytes": sum(observed_sizes.values()),
        "mounted_inventory_name_and_size_match": True,
        "mounted_manifest_sha256": DATASET_MANIFEST_SHA256,
        "selected_files_found": len(selected_index),
        "metadata_tree_verified_before_replay_body_reads": True,
    }


def validate_request(request: Mapping[str, Any]) -> list[dict[str, Any]]:
    if request.get("status") != "READY_UNAUTHORIZED":
        raise ValueError("request status differs")
    if request.get("authorized") is not False or request.get("authorization_consumed") is not False:
        raise ValueError("request pre-execution authorization state differs")
    if request.get("maximum_files") != MAXIMUM_FILES or request.get("maximum_declared_bytes") != MAXIMUM_BYTES:
        raise ValueError("request maximum files or bytes differs")
    source = request.get("source")
    if not isinstance(source, Mapping):
        raise ValueError("request source block is missing")
    expected_source = {
        "dataset_reference": DATASET_REF,
        "dataset_id": DATASET_ID,
        "dataset_version": DATASET_VERSION,
        "dataset_status": "READY",
        "dataset_inventory_sha256": DATASET_INVENTORY_SHA256,
        "dataset_inventory_files": DATASET_FILES,
        "dataset_inventory_json_files": DATASET_JSON_FILES,
        "dataset_inventory_total_bytes": DATASET_TOTAL_BYTES,
        "manifest_sha256": DATASET_MANIFEST_SHA256,
    }
    for key, expected in expected_source.items():
        if source.get(key) != expected:
            raise ValueError(f"request source {key} differs")
    teacher = request.get("teacher")
    if not isinstance(teacher, Mapping):
        raise ValueError("request teacher block is missing")
    if (
        teacher.get("team_id") != TEACHER_TEAM_ID
        or teacher.get("submission_id") != TEACHER_SUBMISSION_ID
        or teacher.get("team_name") != TEACHER_NAME
        or teacher.get("deck_multiset_sha256") != TEACHER_DECK_SHA256
    ):
        raise ValueError("request teacher identity differs")
    policy = request.get("corpus_policy")
    if not isinstance(policy, Mapping):
        raise ValueError("request corpus policy is missing")
    if (
        policy.get("base_manifest_sha256") != BASE_MANIFEST_SHA256
        or policy.get("base_policy_loss_targets") != 23_460
        or policy.get("base_qualified_episodes") != 337
        or policy.get("minimum_policy_loss_targets") != MINIMUM_TARGETS
        or policy.get("stop_review_when_cumulative_qualified_targets_reach_floor") is not True
    ):
        raise ValueError("request corpus policy differs")
    files = request.get("files")
    if not isinstance(files, list) or len(files) != MAXIMUM_FILES:
        raise ValueError("request does not contain exactly 48 files")
    normalized = [dict(item) for item in files if isinstance(item, Mapping)]
    if len(normalized) != MAXIMUM_FILES:
        raise ValueError("request file entry differs")
    if [int(item.get("review_order", -1)) for item in normalized] != list(range(1, MAXIMUM_FILES + 1)):
        raise ValueError("request review order differs")
    names = [str(item.get("file_name")) for item in normalized]
    ids = [int(item.get("episode_id")) for item in normalized]
    if len(set(names)) != MAXIMUM_FILES or len(set(ids)) != MAXIMUM_FILES:
        raise ValueError("request filenames or episode ids are not unique")
    if sum(int(item.get("declared_bytes", -1)) for item in normalized) != MAXIMUM_BYTES:
        raise ValueError("request declared byte cap differs")
    for item in normalized:
        if (
            int(item.get("teacher_team_id", 0)) != TEACHER_TEAM_ID
            or int(item.get("teacher_submission_id", 0)) != TEACHER_SUBMISSION_ID
            or str(item.get("teacher_team_name")) != TEACHER_NAME
        ):
            raise ValueError("selected metadata teacher identity differs")
    return normalized


def aggregate_records(records: list[Mapping[str, Any]]) -> tuple[Counter[str], dict[str, Counter[str]], dict[str, Counter[str]]]:
    aggregate: Counter[str] = Counter()
    splits: dict[str, Counter[str]] = defaultdict(Counter)
    teachers: dict[str, Counter[str]] = defaultdict(Counter)
    for item in records:
        split = str(item["split"])
        teacher = str(item["teacher_key"])
        for key in ("bytes", "teacher_active_requests", "forced_teacher_requests", "meaningful_teacher_decisions", "policy_loss_targets"):
            value = int(item[key])
            aggregate[key] += value
            splits[split][key] += value
            teachers[teacher][key] += value
        aggregate["episodes"] += 1
        splits[split]["episodes"] += 1
        teachers[teacher]["episodes"] += 1
    return aggregate, splits, teachers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, default=Path("/kaggle/input"))
    parser.add_argument("--out-dir", type=Path, default=Path("/kaggle/working"))
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--base-manifest", type=Path, required=True)
    parser.add_argument("--card-data", type=Path, required=True)
    parser.add_argument("--dataset-inventory", type=Path, required=True)
    args = parser.parse_args()

    started_monotonic = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if sha_file(args.request) != REQUEST_SHA256:
        raise ValueError("approved supplement request hash differs")
    if sha_file(args.base_manifest) != BASE_MANIFEST_SHA256:
        raise ValueError("base corpus-v2 manifest hash differs")
    if sha_file(args.card_data) != CARD_DATA_SHA256:
        raise ValueError("official card-data hash differs")

    request = load_json(args.request)
    base_manifest = load_json(args.base_manifest)
    selected = validate_request(request)
    approved_inventory, approved_inventory_report = load_approved_inventory(args.dataset_inventory)
    selected_names = {str(item["file_name"]) for item in selected}
    dataset_root, selected_index, mounted_inventory_report = locate_dataset_root(
        args.input_root,
        selected_names,
        approved_inventory,
    )

    base_corpus = base_manifest.get("qualified_training_corpus")
    if not isinstance(base_corpus, Mapping):
        raise ValueError("base corpus-v2 payload differs")
    if int(base_corpus.get("episodes", -1)) != 337 or int(base_corpus.get("policy_loss_targets", -1)) != 23_460:
        raise ValueError("base corpus-v2 counts differ")
    base_records_value = base_corpus.get("episode_records")
    if not isinstance(base_records_value, list):
        raise ValueError("base corpus-v2 episode records differ")
    base_records = [copy.deepcopy(dict(item)) for item in base_records_value if isinstance(item, Mapping)]
    if len(base_records) != 337:
        raise ValueError("base corpus-v2 episode record count differs")
    known_ids = {int(item["episode_id"]) for item in base_records}
    known_hashes = {str(item["sha256"]) for item in base_records}
    if len(known_ids) != 337 or len(known_hashes) != 337:
        raise ValueError("base corpus-v2 duplicate identity differs")
    if known_ids & {int(item["episode_id"]) for item in selected}:
        raise ValueError("selected episode already exists in corpus v2")

    cards = prior.base.card_table()
    qualified: list[dict[str, Any]] = []
    body_reads: list[dict[str, Any]] = []
    observed_new_hashes: set[str] = set()
    read_bytes = 0
    cumulative_targets = int(base_corpus["policy_loss_targets"])
    split_seed = int(request["corpus_policy"]["split_seed"])

    for item in selected:
        if cumulative_targets >= MINIMUM_TARGETS:
            break
        file_name = str(item["file_name"])
        path = selected_index[file_name]
        raw = path.read_bytes()
        read_bytes += len(raw)
        if read_bytes > MAXIMUM_BYTES:
            raise ValueError("approved maximum replay-body bytes exceeded")
        record = prior.inspect_raw_replay(raw, item, cards)
        episode_id = int(record["episode_id"])
        body_hash = str(record["sha256"])
        if episode_id in known_ids:
            raise ValueError("duplicate episode id against corpus v2")
        if body_hash in known_hashes or body_hash in observed_new_hashes:
            raise ValueError("duplicate replay content hash")
        observed_new_hashes.add(body_hash)
        record["source_dataset_path"] = str(path.relative_to(dataset_root))
        record["source_review"] = OUTPUT_NAMES[0]
        record["teacher_key"] = "majkel"
        record["review_order"] = int(item["review_order"])
        split, split_digest = prior.split_for(record, split_seed)
        record["split"] = split
        record["split_key_sha256"] = split_digest
        qualified.append(record)
        cumulative_targets += int(record["policy_loss_targets"])
        body_reads.append(
            {
                "review_order": int(item["review_order"]),
                "episode_id": episode_id,
                "file_name": file_name,
                "bytes": len(raw),
                "sha256": body_hash,
                "policy_loss_targets": int(record["policy_loss_targets"]),
                "cumulative_policy_loss_targets": cumulative_targets,
            }
        )
        print(
            json.dumps(
                {
                    "review_order": int(item["review_order"]),
                    "episode_id": episode_id,
                    "read_files": len(body_reads),
                    "read_bytes": read_bytes,
                    "qualified": len(qualified),
                    "cumulative_policy_loss_targets": cumulative_targets,
                },
                sort_keys=True,
            ),
            flush=True,
        )

    if cumulative_targets < MINIMUM_TARGETS:
        raise ValueError("approved maximum-48 review did not reach the 25,000-target floor")
    if not qualified or len(qualified) > MAXIMUM_FILES:
        raise ValueError("qualified supplement count differs")
    expected_prefix = selected[: len(qualified)]
    if [int(item["episode_id"]) for item in expected_prefix] != [int(item["episode_id"]) for item in qualified]:
        raise ValueError("reviewed files do not match the approved order prefix")

    all_records = base_records + qualified
    all_ids = [int(item["episode_id"]) for item in all_records]
    all_hashes = [str(item["sha256"]) for item in all_records]
    if len(set(all_ids)) != len(all_ids) or len(set(all_hashes)) != len(all_hashes):
        raise ValueError("corpus-v3 duplicate identity detected")
    aggregate, splits, teachers = aggregate_records(all_records)
    if aggregate["policy_loss_targets"] != cumulative_targets:
        raise ValueError("corpus-v3 target recount differs")

    completed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    corpus_manifest: dict[str, Any] = {
        "schema_version": 3,
        "record_id": "e01-approved-replay-corpus-manifest-v3",
        "source_path": OUTPUT_NAMES[1],
        "created_at_utc": completed_at,
        "producer": "scripts/e01_corpus_target_supplement_review.py",
        "decision_id": "DEC-029",
        "status": "PASS_QUALIFIED_ONLY_CORPUS_V3_FROZEN",
        "inputs": {
            "approved_request_sha256": REQUEST_SHA256,
            "base_manifest_sha256": BASE_MANIFEST_SHA256,
            "card_data_sha256": CARD_DATA_SHA256,
            "dataset_reference": DATASET_REF,
            "dataset_id": DATASET_ID,
            "dataset_version": DATASET_VERSION,
            "dataset_inventory_sha256": DATASET_INVENTORY_SHA256,
            "dataset_manifest_sha256": DATASET_MANIFEST_SHA256,
            "dataset_root": str(dataset_root),
        },
        "selection_review": {
            "maximum_requested_files": MAXIMUM_FILES,
            "maximum_requested_bytes": MAXIMUM_BYTES,
            "replay_bodies_read": len(body_reads),
            "replay_body_bytes_read": read_bytes,
            "qualified_new_files": len(qualified),
            "rejected_new_files": 0,
            "unread_approved_files": MAXIMUM_FILES - len(body_reads),
            "base_policy_loss_targets": 23_460,
            "final_policy_loss_targets": cumulative_targets,
            "target_floor": MINIMUM_TARGETS,
            "stop_reason": "CUMULATIVE_QUALIFIED_POLICY_LOSS_TARGET_FLOOR_REACHED",
            "replay_body_outputs": 0,
            "agent_log_outputs": 0,
            "training_label_outputs": 0,
        },
        "qualified_training_corpus": {
            "episodes": aggregate["episodes"],
            "bytes": aggregate["bytes"],
            "teacher_active_requests": aggregate["teacher_active_requests"],
            "forced_teacher_requests": aggregate["forced_teacher_requests"],
            "meaningful_teacher_decisions": aggregate["meaningful_teacher_decisions"],
            "policy_loss_targets": aggregate["policy_loss_targets"],
            "episode_records": sorted(all_records, key=lambda value: int(value["episode_id"])),
            "split_counts": {key: dict(value) for key, value in sorted(splits.items())},
            "teacher_counts": {key: dict(value) for key, value in sorted(teachers.items())},
        },
        "sampling_policy": request["corpus_policy"],
        "manifest_sha256": None,
    }
    corpus_manifest["manifest_sha256"] = self_hash(corpus_manifest, "manifest_sha256")

    corpus_review: dict[str, Any] = {
        "schema_version": 3,
        "record_id": "e01-approved-replay-corpus-review-v3",
        "source_path": OUTPUT_NAMES[2],
        "created_at_utc": completed_at,
        "producer": "scripts/e01_corpus_target_supplement_review.py",
        "status": "PASS",
        "decision": "ACCEPT_QUALIFIED_ONLY_CORPUS_V3_TARGET_FLOOR_PASSED_STOP_BEFORE_TRAINING",
        "reviewed_decision": "DEC-029",
        "corpus_manifest_sha256": sha_bytes(pretty_bytes(corpus_manifest)),
        "qualification": {
            "minimum_200_episodes": aggregate["episodes"] >= 200,
            "minimum_25000_policy_loss_targets": aggregate["policy_loss_targets"] >= MINIMUM_TARGETS,
            "approved_request_order_prefix_read": True,
            "stopped_at_first_completed_file_reaching_target_floor": True,
            "maximum_48_files_respected": len(body_reads) <= MAXIMUM_FILES,
            "maximum_180695173_bytes_respected": read_bytes <= MAXIMUM_BYTES,
            "dataset_inventory_identity_verified_before_body_reads": True,
            "dataset_manifest_identity_verified_before_body_reads": True,
            "action_alignment_verified": True,
            "deck_and_module_filtering_applied": True,
            "duplicate_episode_or_content_hashes": 0,
            "episode_level_split": True,
            "replay_body_outputs": 0,
            "agent_log_outputs": 0,
            "training_label_outputs": 0,
            "optimizer_steps": 0,
            "training": False,
            "model_mutation": False,
            "model_promotion": False,
            "submission": False,
        },
        "counts": dict(aggregate),
        "supplement_review": {
            "qualified": len(qualified),
            "rejected": 0,
            "read_bytes": read_bytes,
            "unread_approved_files": MAXIMUM_FILES - len(body_reads),
            "reviewed_episode_ids": [int(item["episode_id"]) for item in qualified],
        },
        "review_sha256": None,
    }
    corpus_review["review_sha256"] = self_hash(corpus_review, "review_sha256")

    run_review: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e01-corpus-target-supplement-review-v1",
        "source_path": OUTPUT_NAMES[0],
        "created_at_utc": completed_at,
        "producer": "scripts/e01_corpus_target_supplement_review.py",
        "status": "PASS",
        "decision": "COMPLETE_APPROVED_PRIVATE_KAGGLE_CPU_PREFIX_REVIEW_FINALIZE_CORPUS_V3_AND_STOP",
        "approved_request_sha256": REQUEST_SHA256,
        "runtime": {
            "started_at_utc": started_at,
            "completed_at_utc": completed_at,
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count(),
            "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
            "internet_requested": False,
            "gpu_used": False,
            "tpu_used": False,
            "wall_seconds": time.monotonic() - started_monotonic,
        },
        "approved_inventory": approved_inventory_report,
        "mounted_inventory": mounted_inventory_report,
        "transfer": {
            "approved_named_replay_bodies": MAXIMUM_FILES,
            "named_replay_bodies_read": len(body_reads),
            "replay_body_bytes_read": read_bytes,
            "maximum_replay_body_bytes": MAXIMUM_BYTES,
            "unread_approved_replay_bodies": MAXIMUM_FILES - len(body_reads),
            "additional_replay_bodies_read": 0,
            "replay_body_outputs": 0,
            "agent_logs_read": 0,
            "agent_log_outputs": 0,
        },
        "review": {
            "qualified_new_files": len(qualified),
            "rejected_new_files": 0,
            "body_reads": body_reads,
            "base_policy_loss_targets": 23_460,
            "final_policy_loss_targets": cumulative_targets,
            "target_floor": MINIMUM_TARGETS,
            "stop_reason": "CUMULATIVE_QUALIFIED_POLICY_LOSS_TARGET_FLOOR_REACHED",
        },
        "authorization": {
            "external_compute_private_kaggle_cpu": True,
            "replay_body_reads_exact_named_files": True,
            "corpus_v3_qualified_only_finalization": True,
            "raw_replay_body_outputs": 0,
            "agent_log_outputs": 0,
            "training_label_outputs": 0,
            "optimizer_created": False,
            "optimizer_steps": 0,
            "training": False,
            "gpu": False,
            "tpu": False,
            "model_mutation": False,
            "model_promotion": False,
            "submission": False,
            "git_commit": False,
            "git_push": False,
        },
        "outputs": list(OUTPUT_NAMES),
        "review_sha256": None,
    }
    run_review["review_sha256"] = self_hash(run_review, "review_sha256")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, Mapping[str, Any]] = {
        OUTPUT_NAMES[0]: run_review,
        OUTPUT_NAMES[1]: corpus_manifest,
        OUTPUT_NAMES[2]: corpus_review,
    }
    for name, value in outputs.items():
        write_json(args.out_dir / name, value)
    output_manifest: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e01-corpus-target-supplement-output-manifest-v1",
        "source_path": OUTPUT_NAMES[3],
        "created_at_utc": completed_at,
        "producer": "scripts/e01_corpus_target_supplement_review.py",
        "files": [
            {
                "path": name,
                "bytes": (args.out_dir / name).stat().st_size,
                "sha256": sha_file(args.out_dir / name),
            }
            for name in OUTPUT_NAMES[:3]
        ],
        "metadata_files": 4,
        "replay_body_outputs": 0,
        "agent_log_outputs": 0,
        "training_label_outputs": 0,
        "manifest_sha256": None,
    }
    output_manifest["manifest_sha256"] = self_hash(output_manifest, "manifest_sha256")
    write_json(args.out_dir / OUTPUT_NAMES[3], output_manifest)

    actual_outputs = {path.name for path in args.out_dir.glob("*.json") if path.is_file()}
    if actual_outputs != set(OUTPUT_NAMES):
        raise ValueError(f"unexpected JSON output set: {sorted(actual_outputs)}")
    print(
        json.dumps(
            {
                "status": "PASS",
                "replay_bodies_read": len(body_reads),
                "replay_body_bytes_read": read_bytes,
                "qualified_new_files": len(qualified),
                "corpus_v3_episodes": aggregate["episodes"],
                "corpus_v3_policy_loss_targets": aggregate["policy_loss_targets"],
                "unread_approved_files": MAXIMUM_FILES - len(body_reads),
                "output_dir": str(args.out_dir),
                "optimizer_steps": 0,
                "training": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
