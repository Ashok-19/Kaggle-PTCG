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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

SOURCE_ROOT = Path.cwd()
sys.path.insert(0, str(SOURCE_ROOT / "src"))
sys.path.insert(0, str(SOURCE_ROOT / "scripts"))

import e01_majkel_corpus_expansion_review as prior  # noqa: E402

REQUEST_SHA256 = "dc38df7b76e01682d3e735499aab352e963c9d454423c71756ededee98b69331"
BASE_MANIFEST_SHA256 = "ccc247edbc4cac0aba11c6acb26fc5e2a8c75e0a4f005d1441ce6949c0c4997f"
CARD_DATA_SHA256 = "a0ea63cf7adcb65d35436ce0eb390de6e2e35654a7c67c065a45f4abaa00f373"
DATASET_INVENTORY_SHA256 = "5620e055a25407c47e7744eaa0ffb9ab2a04fe2287b0f6180f54726cf7a00f77"
DATASET_MANIFEST_SHA256 = "bb190f62f0585dc2a1db2b02752a4d7e6fa6de15a800ed9e769d8daecd8bf9a1"
DATASET_REFERENCE = "kaggle/pokemon-tcg-ai-battle-episodes-2026-08-04"
DATASET_ID = 11_506_836
DATASET_VERSION = 1
DATASET_FILES = 4_812
DATASET_JSON_FILES = 4_811
DATASET_TOTAL_BYTES = 21_457_813_826
EPISODE_ID = 90_037_133
FILE_NAME = "90037133.json"
DECLARED_BYTES = 4_882_237
MODULE_VERSION = "1.32.4"
TEACHER_TEAM_ID = 16_374_395
TEACHER_SUBMISSION_ID = 55_186_239
TEACHER_NAME = "Majkel1337"
TEACHER_DECK_SHA256 = "dc8571d0bc2e546a1f85b938696cfc40a1451c68a4ccc1f695e7c3e1c74f1278"
SPLIT_SEED = 20_260_804
OUTPUT_NAMES = (
    "e01-majkel-module-1324-compatibility-probe-review-v1.json",
    "e01-majkel-module-1324-compatibility-probe-output-manifest-v1.json",
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


def validate_request(request: Mapping[str, Any]) -> dict[str, Any]:
    if request.get("status") != "READY_UNAUTHORIZED":
        raise ValueError("probe request status differs")
    if request.get("authorized") is not False or request.get("authorization_consumed") is not False:
        raise ValueError("probe request authorization state differs")
    if request.get("maximum_files") != 1 or request.get("maximum_declared_bytes") != DECLARED_BYTES:
        raise ValueError("probe request transfer cap differs")
    source = request.get("source")
    expected_source = {
        "dataset_reference": DATASET_REFERENCE,
        "dataset_id": DATASET_ID,
        "dataset_version": DATASET_VERSION,
        "dataset_status": "READY",
        "dataset_inventory_sha256": DATASET_INVENTORY_SHA256,
        "dataset_inventory_files": DATASET_FILES,
        "dataset_inventory_json_files": DATASET_JSON_FILES,
        "dataset_inventory_total_bytes": DATASET_TOTAL_BYTES,
        "manifest_sha256": DATASET_MANIFEST_SHA256,
    }
    if not isinstance(source, Mapping):
        raise ValueError("probe source block is missing")
    for key, expected in expected_source.items():
        if source.get(key) != expected:
            raise ValueError(f"probe source {key} differs")
    teacher = request.get("teacher")
    if not isinstance(teacher, Mapping):
        raise ValueError("probe teacher block is missing")
    if (
        teacher.get("team_id") != TEACHER_TEAM_ID
        or teacher.get("submission_id") != TEACHER_SUBMISSION_ID
        or teacher.get("team_name") != TEACHER_NAME
        or teacher.get("deck_multiset_sha256") != TEACHER_DECK_SHA256
    ):
        raise ValueError("probe teacher identity differs")
    review_contract = request.get("review_contract")
    if not isinstance(review_contract, Mapping):
        raise ValueError("probe review contract is missing")
    if (
        review_contract.get("accepted_for_probe_only") != [MODULE_VERSION]
        or review_contract.get("observed_module_version") != MODULE_VERSION
        or review_contract.get("corpus_promotion") is not False
        or review_contract.get("supplement_continuation") is not False
    ):
        raise ValueError("probe review contract differs")
    output_contract = request.get("output_contract")
    if not isinstance(output_contract, Mapping) or output_contract.get("metadata_files") != list(OUTPUT_NAMES):
        raise ValueError("probe output contract differs")
    if (
        output_contract.get("raw_replay_body_outputs") != 0
        or output_contract.get("agent_log_outputs") != 0
        or output_contract.get("training_label_outputs") != 0
    ):
        raise ValueError("probe output boundary differs")
    files = request.get("files")
    if not isinstance(files, list) or len(files) != 1 or not isinstance(files[0], Mapping):
        raise ValueError("probe file selection differs")
    item = dict(files[0])
    if (
        item.get("episode_id") != EPISODE_ID
        or item.get("file_name") != FILE_NAME
        or item.get("declared_bytes") != DECLARED_BYTES
        or item.get("review_order") != 1
        or item.get("teacher_team_id") != TEACHER_TEAM_ID
        or item.get("teacher_submission_id") != TEACHER_SUBMISSION_ID
        or item.get("teacher_team_name") != TEACHER_NAME
        or item.get("teacher_player_index") != 0
        or float(item.get("teacher_reward")) != -1.0
    ):
        raise ValueError("probe selected file identity differs")
    requested = request.get("requested_authorization")
    if not isinstance(requested, Mapping):
        raise ValueError("probe requested authorization is missing")
    true_fields = {key for key, value in requested.items() if value is True}
    if true_fields != {"external_compute_private_kaggle_cpu", "replay_body_reads_exact_named_files"}:
        raise ValueError("probe requested authorization scope differs")
    return item


def load_approved_inventory(path: Path) -> dict[str, int]:
    if sha_file(path) != DATASET_INVENTORY_SHA256:
        raise ValueError("approved dataset inventory hash differs")
    inventory: dict[str, int] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["name", "total_bytes", "creation_date"]:
            raise ValueError("approved dataset inventory columns differ")
        for row in reader:
            name = str(row["name"])
            if name in inventory:
                raise ValueError(f"duplicate inventory filename: {name}")
            inventory[name] = int(row["total_bytes"])
    if len(inventory) != DATASET_FILES:
        raise ValueError("approved inventory file count differs")
    if sum(name.endswith(".json") for name in inventory) != DATASET_JSON_FILES:
        raise ValueError("approved inventory JSON count differs")
    if sum(inventory.values()) != DATASET_TOTAL_BYTES:
        raise ValueError("approved inventory total bytes differ")
    if inventory.get(FILE_NAME) != DECLARED_BYTES or "manifest.csv" not in inventory:
        raise ValueError("approved inventory selected file or manifest differs")
    return inventory


def locate_dataset_root(input_root: Path, approved_inventory: Mapping[str, int]) -> tuple[Path, Path]:
    candidates = [
        path
        for path in input_root.rglob("*")
        if path.is_dir() and "pokemon-tcg-ai-battle-episodes-2026-08-04" in path.name
    ]
    matches: list[tuple[Path, dict[str, Path]]] = []
    for candidate in candidates:
        observed_paths: dict[str, Path] = {}
        observed_sizes: dict[str, int] = {}
        duplicate = False
        for path in candidate.rglob("*"):
            if not path.is_file():
                continue
            if path.name in observed_paths:
                duplicate = True
                break
            observed_paths[path.name] = path
            observed_sizes[path.name] = path.stat().st_size
        if not duplicate and observed_sizes == dict(approved_inventory):
            matches.append((candidate, observed_paths))
    if len(matches) != 1:
        raise ValueError(f"expected one exact August 4 dataset root, observed {len(matches)}")
    dataset_root, observed_paths = matches[0]
    if sha_file(observed_paths["manifest.csv"]) != DATASET_MANIFEST_SHA256:
        raise ValueError("mounted dataset manifest hash differs")
    return dataset_root, observed_paths[FILE_NAME]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, default=Path("/kaggle/input"))
    parser.add_argument("--out-dir", type=Path, default=Path("/kaggle/working"))
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--base-manifest", type=Path, required=True)
    parser.add_argument("--card-data", type=Path, required=True)
    parser.add_argument("--dataset-inventory", type=Path, required=True)
    args = parser.parse_args()

    started = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if sha_file(args.request) != REQUEST_SHA256:
        raise ValueError("approved compatibility probe request hash differs")
    if sha_file(args.base_manifest) != BASE_MANIFEST_SHA256:
        raise ValueError("base corpus-v2 manifest hash differs")
    if sha_file(args.card_data) != CARD_DATA_SHA256:
        raise ValueError("official card data hash differs")

    request = load_json(args.request)
    item = validate_request(request)
    approved_inventory = load_approved_inventory(args.dataset_inventory)
    dataset_root, body_path = locate_dataset_root(args.input_root, approved_inventory)

    base_manifest = load_json(args.base_manifest)
    corpus = base_manifest.get("qualified_training_corpus")
    if not isinstance(corpus, Mapping):
        raise ValueError("base corpus-v2 payload differs")
    records = corpus.get("episode_records")
    if not isinstance(records, list) or len(records) != 337:
        raise ValueError("base corpus-v2 episode records differ")
    if int(corpus.get("episodes", -1)) != 337 or int(corpus.get("policy_loss_targets", -1)) != 23_460:
        raise ValueError("base corpus-v2 counts differ")
    known_ids = {int(record["episode_id"]) for record in records if isinstance(record, Mapping)}
    known_hashes = {str(record["sha256"]) for record in records if isinstance(record, Mapping)}
    if len(known_ids) != 337 or len(known_hashes) != 337 or EPISODE_ID in known_ids:
        raise ValueError("base corpus-v2 duplicate identity or episode exclusion differs")

    raw = body_path.read_bytes()
    if len(raw) != DECLARED_BYTES:
        raise ValueError("approved replay body byte count differs")

    prior.ACCEPTED_MODULES = {MODULE_VERSION}
    cards = prior.base.card_table()
    record = prior.inspect_raw_replay(raw, item, cards)
    if record.get("module_version") != MODULE_VERSION:
        raise ValueError("observed module version differs")
    if record.get("teacher_deck_multiset_sha256") != TEACHER_DECK_SHA256:
        raise ValueError("teacher deck differs")
    if record.get("action_alignment") != "PASS" or record.get("current_asset_construction_compatibility") != "PASS":
        raise ValueError("action or current-card compatibility differs")
    body_sha256 = str(record["sha256"])
    if body_sha256 in known_hashes:
        raise ValueError("replay content already exists in corpus v2")
    split, split_key = prior.split_for({**record, "stratum": str(item["stratum"])}, SPLIT_SEED)

    completed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    review: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e01-majkel-module-1324-compatibility-probe-review-v1",
        "source_path": OUTPUT_NAMES[0],
        "created_at_utc": completed_at,
        "producer": "scripts/e01_majkel_module_1324_compatibility_probe.py",
        "status": "PASS_COMPATIBLE_FOR_FUTURE_EXACT_REQUEST_ONLY",
        "decision": "MODULE_1324_PASSES_EXISTING_DECK_CURRENT_CARD_TERMINAL_REWARD_AND_FULL_ACTION_CONTRACT_NO_CORPUS_PROMOTION",
        "reviewed_decision": "DEC-030",
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
            "wall_seconds": time.monotonic() - started,
        },
        "source_identity": {
            "dataset_reference": DATASET_REFERENCE,
            "dataset_id": DATASET_ID,
            "dataset_version": DATASET_VERSION,
            "dataset_inventory_sha256": DATASET_INVENTORY_SHA256,
            "dataset_manifest_sha256": DATASET_MANIFEST_SHA256,
            "dataset_root": str(dataset_root),
            "teacher_team_id": TEACHER_TEAM_ID,
            "teacher_submission_id": TEACHER_SUBMISSION_ID,
            "teacher_team_name": TEACHER_NAME,
        },
        "transfer": {
            "approved_named_replay_bodies": 1,
            "named_replay_bodies_read": 1,
            "replay_body_bytes_read": DECLARED_BYTES,
            "maximum_replay_body_bytes": DECLARED_BYTES,
            "additional_replay_bodies_read": 0,
            "replay_body_outputs": 0,
            "agent_log_outputs": 0,
        },
        "episode": {
            "episode_id": EPISODE_ID,
            "file_name": FILE_NAME,
            "bytes": DECLARED_BYTES,
            "sha256": body_sha256,
            "module_version": record["module_version"],
            "teacher_player_index": record["teacher_player_index"],
            "teacher_reward": record["teacher_reward"],
            "teacher_deck_multiset_sha256": record["teacher_deck_multiset_sha256"],
            "opponent_deck_multiset_sha256": record["opponent_deck_multiset_sha256"],
            "teacher_active_requests": record["teacher_active_requests"],
            "forced_teacher_requests": record["forced_teacher_requests"],
            "policy_loss_targets": record["policy_loss_targets"],
            "stop_targets": record["stop_targets"],
            "ordered_requests": record["ordered_requests"],
            "maximum_option_count": record["maximum_option_count"],
            "maximum_selection_count": record["maximum_selection_count"],
            "candidate_split_if_later_separately_authorized": split,
            "candidate_split_key_sha256": split_key,
        },
        "qualification": {
            "schema_and_environment_identity": True,
            "module_version_exact_1324": True,
            "exact_mega_lucario_deck_multiset": True,
            "teacher_player_and_terminal_reward_identity": True,
            "current_card_construction_compatibility": True,
            "lag_aligned_full_compound_action_validity_including_stop": True,
            "forced_singleton_recurrence_only_classification": True,
            "duplicate_episode_id_against_corpus_v2": False,
            "duplicate_content_hash_against_corpus_v2": False,
            "episode_level_split_candidate_only": True,
            "corpus_promotion": False,
            "supplement_continuation": False,
            "training_label_outputs": 0,
            "optimizer_steps": 0,
            "training": False,
            "model_mutation": False,
            "model_promotion": False,
            "submission": False,
            "git_commit": False,
            "git_push": False,
        },
        "next_boundary": "A_NEW_EXACT_REQUEST_IS_REQUIRED_BEFORE_ANY_SUPPLEMENT_CONTINUATION_OR_CORPUS_PROMOTION",
        "review_sha256": None,
    }
    review["review_sha256"] = self_hash(review, "review_sha256")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for name in OUTPUT_NAMES:
        path = args.out_dir / name
        if path.exists():
            path.unlink()
    review_path = args.out_dir / OUTPUT_NAMES[0]
    write_json(review_path, review)
    output_manifest: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e01-majkel-module-1324-compatibility-probe-output-manifest-v1",
        "source_path": OUTPUT_NAMES[1],
        "created_at_utc": completed_at,
        "producer": "scripts/e01_majkel_module_1324_compatibility_probe.py",
        "approved_request_sha256": REQUEST_SHA256,
        "files": [
            {
                "path": OUTPUT_NAMES[0],
                "bytes": review_path.stat().st_size,
                "sha256": sha_file(review_path),
            }
        ],
        "metadata_files": 2,
        "replay_body_outputs": 0,
        "agent_log_outputs": 0,
        "training_label_outputs": 0,
        "corpus_promotion": False,
        "manifest_sha256": None,
    }
    output_manifest["manifest_sha256"] = self_hash(output_manifest, "manifest_sha256")
    write_json(args.out_dir / OUTPUT_NAMES[1], output_manifest)
    actual = {path.name for path in args.out_dir.glob("*.json") if path.is_file()}
    if actual != set(OUTPUT_NAMES):
        raise ValueError(f"unexpected JSON output set: {sorted(actual)}")
    print(
        json.dumps(
            {
                "status": review["status"],
                "episode_id": EPISODE_ID,
                "module_version": MODULE_VERSION,
                "replay_bodies_read": 1,
                "replay_body_bytes_read": DECLARED_BYTES,
                "policy_loss_targets_observed": record["policy_loss_targets"],
                "corpus_promotion": False,
                "optimizer_steps": 0,
                "training": False,
                "outputs": list(OUTPUT_NAMES),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
