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

BASE_MANIFEST_SHA256 = "ccc247edbc4cac0aba11c6acb26fc5e2a8c75e0a4f005d1441ce6949c0c4997f"
CARD_DATA_SHA256 = "a0ea63cf7adcb65d35436ce0eb390de6e2e35654a7c67c065a45f4abaa00f373"
DATASET_INVENTORY_SHA256 = "5620e055a25407c47e7744eaa0ffb9ab2a04fe2287b0f6180f54726cf7a00f77"
DATASET_MANIFEST_SHA256 = "bb190f62f0585dc2a1db2b02752a4d7e6fa6de15a800ed9e769d8daecd8bf9a1"
PROBE_REVIEW_SHA256 = "e956d010552bcab7489852daa8367a8c11eb06138b98dc21486c11b9ae30d4f2"
PROBE_REVIEW_SELF_HASH = "ba28a9baabd2799934936138386aaeec2e58e666e6f3d486e9b378113b797faa"
PROBE_OUTPUT_MANIFEST_SHA256 = "72f467b09326d488fd860221cae6647b6ceafd8b4b00c2d4f3fa54844e1a89e3"
PROBE_OUTPUT_MANIFEST_SELF_HASH = "3521bda8656c2c5a05408f069205b79cf79f372894da4a9a96be163f3c1bf2f5"
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
ACCEPTED_MODULES = {"1.32.2", "1.32.3", "1.32.4"}
BASE_EPISODES = 337
BASE_TARGETS = 23_460
PREQUALIFIED_TARGETS = 69
MINIMUM_TARGETS = 25_000
MAXIMUM_FILES = 47
MAXIMUM_BYTES = 175_812_936
PREQUALIFIED_EPISODE_ID = 90_037_133
PREQUALIFIED_BODY_SHA256 = "6cd39f9c21eb5c62abe3b44fcaa69ef8423bb7fcabfc8b14a1693a9d88abbf9e"
OUTPUT_NAMES = (
    "e01-corpus-target-supplement-review-v2.json",
    "e01-approved-replay-corpus-manifest-v3.json",
    "e01-approved-replay-corpus-review-v3.json",
    "e01-corpus-target-supplement-output-manifest-v2.json",
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
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ["name", "total_bytes", "creation_date"]:
            raise ValueError("dataset inventory columns differ")
        for row in reader:
            name = str(row["name"])
            if name in inventory:
                raise ValueError(f"duplicate dataset inventory filename: {name}")
            inventory[name] = int(row["total_bytes"])
    if len(inventory) != DATASET_FILES:
        raise ValueError("dataset inventory file count differs")
    if sum(name.endswith(".json") for name in inventory) != DATASET_JSON_FILES:
        raise ValueError("dataset inventory JSON count differs")
    if sum(inventory.values()) != DATASET_TOTAL_BYTES:
        raise ValueError("dataset inventory total bytes differs")
    if "manifest.csv" not in inventory:
        raise ValueError("dataset inventory manifest entry is missing")
    return inventory, {
        "approved_inventory_sha256": DATASET_INVENTORY_SHA256,
        "approved_files": len(inventory),
        "approved_json_files": sum(name.endswith(".json") for name in inventory),
        "approved_total_bytes": sum(inventory.values()),
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


def validate_request(
    request: Mapping[str, Any],
    approved_request_sha256: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if request.get("schema_version") != 2 or request.get("status") != "READY_UNAUTHORIZED":
        raise ValueError("request schema or status differs")
    if request.get("authorized") is not False or request.get("authorization_consumed") is not False:
        raise ValueError("request pre-execution authorization state differs")
    if request.get("maximum_files") != MAXIMUM_FILES or request.get("maximum_declared_bytes") != MAXIMUM_BYTES:
        raise ValueError("request maximum files or bytes differs")
    if request.get("maximum_total_corpus_additions") != 48:
        raise ValueError("request maximum corpus additions differs")

    support = request.get("execution_support")
    if not isinstance(support, Mapping):
        raise ValueError("request execution support is missing")
    if support.get("runner_path") != "scripts/e01_corpus_target_supplement_review_v2.py":
        raise ValueError("request runner path differs")
    if support.get("runner_sha256") != sha_file(Path(__file__).resolve()):
        raise ValueError("request runner hash differs")
    if support.get("approved_request_sha256_argument_required") is not True:
        raise ValueError("request approved-hash argument contract differs")

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
        or set(teacher.get("accepted_module_versions", [])) != ACCEPTED_MODULES
    ):
        raise ValueError("request teacher identity or module set differs")

    policy = request.get("corpus_policy")
    if not isinstance(policy, Mapping):
        raise ValueError("request corpus policy is missing")
    if (
        policy.get("base_manifest_sha256") != BASE_MANIFEST_SHA256
        or policy.get("base_policy_loss_targets") != BASE_TARGETS
        or policy.get("base_qualified_episodes") != BASE_EPISODES
        or policy.get("prequalified_probe_policy_loss_targets") != PREQUALIFIED_TARGETS
        or policy.get("effective_starting_policy_loss_targets_if_approved") != BASE_TARGETS + PREQUALIFIED_TARGETS
        or policy.get("minimum_policy_loss_targets") != MINIMUM_TARGETS
        or policy.get("stop_review_when_cumulative_qualified_targets_reach_floor") is not True
    ):
        raise ValueError("request corpus policy differs")

    prequalified = request.get("prequalified_probe")
    if not isinstance(prequalified, Mapping):
        raise ValueError("request prequalified probe is missing")
    if (
        prequalified.get("review_sha256") != PROBE_REVIEW_SHA256
        or prequalified.get("review_self_hash") != PROBE_REVIEW_SELF_HASH
        or prequalified.get("output_manifest_sha256") != PROBE_OUTPUT_MANIFEST_SHA256
        or prequalified.get("output_manifest_self_hash") != PROBE_OUTPUT_MANIFEST_SELF_HASH
        or prequalified.get("body_reread_authorized") is not False
        or prequalified.get("promotion_requires_this_new_request_approval") is not True
    ):
        raise ValueError("request prequalified probe identity differs")
    record = prequalified.get("record")
    if not isinstance(record, Mapping):
        raise ValueError("request prequalified record is missing")
    normalized_record = copy.deepcopy(dict(record))
    if (
        normalized_record.get("episode_id") != PREQUALIFIED_EPISODE_ID
        or normalized_record.get("file_name") != "90037133.json"
        or normalized_record.get("bytes") != 4_882_237
        or normalized_record.get("sha256") != PREQUALIFIED_BODY_SHA256
        or normalized_record.get("module_version") != "1.32.4"
        or normalized_record.get("policy_loss_targets") != PREQUALIFIED_TARGETS
        or normalized_record.get("teacher_deck_multiset_sha256") != TEACHER_DECK_SHA256
        or normalized_record.get("body_reread_for_v3") is not False
    ):
        raise ValueError("request prequalified record differs")

    files = request.get("files")
    if not isinstance(files, list) or len(files) != MAXIMUM_FILES:
        raise ValueError("request does not contain exactly 47 body-read files")
    normalized = [copy.deepcopy(dict(item)) for item in files if isinstance(item, Mapping)]
    if len(normalized) != MAXIMUM_FILES:
        raise ValueError("request file entry differs")
    if [int(item.get("review_order", -1)) for item in normalized] != list(range(1, MAXIMUM_FILES + 1)):
        raise ValueError("request review order differs")
    if [int(item.get("prior_dec029_review_order", -1)) for item in normalized] != list(range(2, 49)):
        raise ValueError("request preserved DEC-029 order differs")
    names = [str(item.get("file_name")) for item in normalized]
    ids = [int(item.get("episode_id")) for item in normalized]
    if len(set(names)) != MAXIMUM_FILES or len(set(ids)) != MAXIMUM_FILES:
        raise ValueError("request filenames or episode ids are not unique")
    if "90037133.json" in names or PREQUALIFIED_EPISODE_ID in ids:
        raise ValueError("prequalified file remains in body-read list")
    if sum(int(item.get("declared_bytes", -1)) for item in normalized) != MAXIMUM_BYTES:
        raise ValueError("request declared byte cap differs")
    for item in normalized:
        if (
            int(item.get("teacher_team_id", 0)) != TEACHER_TEAM_ID
            or int(item.get("teacher_submission_id", 0)) != TEACHER_SUBMISSION_ID
            or str(item.get("teacher_team_name")) != TEACHER_NAME
        ):
            raise ValueError("selected metadata teacher identity differs")
    return normalized, normalized_record


def validate_probe_evidence(
    probe_review: Mapping[str, Any],
    probe_output_manifest: Mapping[str, Any],
    prequalified_record: Mapping[str, Any],
) -> None:
    if probe_review.get("status") != "PASS_COMPATIBLE_FOR_FUTURE_EXACT_REQUEST_ONLY":
        raise ValueError("probe review status differs")
    if probe_review.get("review_sha256") != PROBE_REVIEW_SELF_HASH:
        raise ValueError("probe review self hash differs")
    if self_hash(probe_review, "review_sha256") != PROBE_REVIEW_SELF_HASH:
        raise ValueError("probe review self hash does not verify")
    if probe_output_manifest.get("manifest_sha256") != PROBE_OUTPUT_MANIFEST_SELF_HASH:
        raise ValueError("probe output manifest self hash differs")
    if self_hash(probe_output_manifest, "manifest_sha256") != PROBE_OUTPUT_MANIFEST_SELF_HASH:
        raise ValueError("probe output manifest self hash does not verify")
    episode = probe_review.get("episode")
    if not isinstance(episode, Mapping):
        raise ValueError("probe episode evidence differs")
    comparisons = {
        "episode_id": "episode_id",
        "file_name": "file_name",
        "bytes": "bytes",
        "sha256": "sha256",
        "module_version": "module_version",
        "teacher_player_index": "teacher_player_index",
        "teacher_reward": "teacher_reward",
        "teacher_deck_multiset_sha256": "teacher_deck_multiset_sha256",
        "opponent_deck_multiset_sha256": "opponent_deck_multiset_sha256",
        "teacher_active_requests": "teacher_active_requests",
        "forced_teacher_requests": "forced_teacher_requests",
        "policy_loss_targets": "policy_loss_targets",
        "stop_targets": "stop_targets",
        "ordered_requests": "ordered_requests",
        "maximum_option_count": "maximum_option_count",
        "maximum_selection_count": "maximum_selection_count",
    }
    for probe_key, record_key in comparisons.items():
        if episode.get(probe_key) != prequalified_record.get(record_key):
            raise ValueError(f"prequalified record differs from probe evidence: {record_key}")
    if episode.get("candidate_split_if_later_separately_authorized") != prequalified_record.get("split"):
        raise ValueError("prequalified split differs from probe evidence")
    if episode.get("candidate_split_key_sha256") != prequalified_record.get("split_key_sha256"):
        raise ValueError("prequalified split hash differs from probe evidence")


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
    parser.add_argument("--approved-request-sha256", required=True)
    parser.add_argument("--base-manifest", type=Path, required=True)
    parser.add_argument("--card-data", type=Path, required=True)
    parser.add_argument("--dataset-inventory", type=Path, required=True)
    parser.add_argument("--probe-review", type=Path, required=True)
    parser.add_argument("--probe-output-manifest", type=Path, required=True)
    args = parser.parse_args()

    started_monotonic = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    approved_request_sha256 = str(args.approved_request_sha256)
    if len(approved_request_sha256) != 64 or any(char not in "0123456789abcdef" for char in approved_request_sha256):
        raise ValueError("approved request hash argument is malformed")
    if sha_file(args.request) != approved_request_sha256:
        raise ValueError("approved renewed supplement request hash differs")
    if sha_file(args.base_manifest) != BASE_MANIFEST_SHA256:
        raise ValueError("base corpus-v2 manifest hash differs")
    if sha_file(args.card_data) != CARD_DATA_SHA256:
        raise ValueError("official card-data hash differs")
    if sha_file(args.probe_review) != PROBE_REVIEW_SHA256:
        raise ValueError("probe review file hash differs")
    if sha_file(args.probe_output_manifest) != PROBE_OUTPUT_MANIFEST_SHA256:
        raise ValueError("probe output manifest file hash differs")

    request = load_json(args.request)
    base_manifest = load_json(args.base_manifest)
    probe_review = load_json(args.probe_review)
    probe_output_manifest = load_json(args.probe_output_manifest)
    selected, prequalified_record = validate_request(request, approved_request_sha256)
    validate_probe_evidence(probe_review, probe_output_manifest, prequalified_record)

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
    if int(base_corpus.get("episodes", -1)) != BASE_EPISODES or int(base_corpus.get("policy_loss_targets", -1)) != BASE_TARGETS:
        raise ValueError("base corpus-v2 counts differ")
    base_records_value = base_corpus.get("episode_records")
    if not isinstance(base_records_value, list):
        raise ValueError("base corpus-v2 episode records differ")
    base_records = [copy.deepcopy(dict(item)) for item in base_records_value if isinstance(item, Mapping)]
    if len(base_records) != BASE_EPISODES:
        raise ValueError("base corpus-v2 episode record count differs")
    known_ids = {int(item["episode_id"]) for item in base_records}
    known_hashes = {str(item["sha256"]) for item in base_records}
    if len(known_ids) != BASE_EPISODES or len(known_hashes) != BASE_EPISODES:
        raise ValueError("base corpus-v2 duplicate identity differs")
    if int(prequalified_record["episode_id"]) in known_ids or str(prequalified_record["sha256"]) in known_hashes:
        raise ValueError("prequalified record duplicates corpus v2")
    if known_ids & {int(item["episode_id"]) for item in selected}:
        raise ValueError("selected episode already exists in corpus v2")

    split_seed = int(request["corpus_policy"]["split_seed"])
    split, split_digest = prior.split_for(prequalified_record, split_seed)
    if split != prequalified_record["split"] or split_digest != prequalified_record["split_key_sha256"]:
        raise ValueError("prequalified split reproduction differs")

    prior.ACCEPTED_MODULES = set(ACCEPTED_MODULES)
    cards = prior.base.card_table()
    qualified_body_records: list[dict[str, Any]] = []
    body_reads: list[dict[str, Any]] = []
    observed_new_hashes = {str(prequalified_record["sha256"])}
    read_bytes = 0
    cumulative_targets = BASE_TARGETS + int(prequalified_record["policy_loss_targets"])

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
        if episode_id in known_ids or episode_id == PREQUALIFIED_EPISODE_ID:
            raise ValueError("duplicate episode id against corpus v2 or prequalified record")
        if body_hash in known_hashes or body_hash in observed_new_hashes:
            raise ValueError("duplicate replay content hash")
        observed_new_hashes.add(body_hash)
        record["source_dataset_path"] = str(path.relative_to(dataset_root))
        record["source_review"] = OUTPUT_NAMES[0]
        record["teacher_key"] = "majkel"
        record["review_order"] = int(item["review_order"])
        record_split, record_split_digest = prior.split_for(record, split_seed)
        record["split"] = record_split
        record["split_key_sha256"] = record_split_digest
        qualified_body_records.append(record)
        cumulative_targets += int(record["policy_loss_targets"])
        body_reads.append(
            {
                "review_order": int(item["review_order"]),
                "prior_dec029_review_order": int(item["prior_dec029_review_order"]),
                "episode_id": episode_id,
                "file_name": file_name,
                "bytes": len(raw),
                "sha256": body_hash,
                "module_version": str(record["module_version"]),
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
                    "qualified_body_files": len(qualified_body_records),
                    "cumulative_policy_loss_targets": cumulative_targets,
                },
                sort_keys=True,
            ),
            flush=True,
        )

    if cumulative_targets < MINIMUM_TARGETS:
        raise ValueError("approved maximum-47 review did not reach the 25,000-target floor")
    if len(qualified_body_records) > MAXIMUM_FILES:
        raise ValueError("qualified body record count differs")
    expected_prefix = selected[: len(qualified_body_records)]
    if [int(item["episode_id"]) for item in expected_prefix] != [int(item["episode_id"]) for item in qualified_body_records]:
        raise ValueError("reviewed files do not match the approved order prefix")

    promoted_prequalified = copy.deepcopy(prequalified_record)
    promoted_prequalified["promotion_source_request_sha256"] = approved_request_sha256
    promoted_prequalified["promotion_source_decision"] = "DEC-031"
    all_records = base_records + [promoted_prequalified] + qualified_body_records
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
        "producer": "scripts/e01_corpus_target_supplement_review_v2.py",
        "decision_id": "DEC-031",
        "status": "PASS_QUALIFIED_ONLY_CORPUS_V3_FROZEN",
        "inputs": {
            "approved_request_sha256": approved_request_sha256,
            "runner_sha256": sha_file(Path(__file__).resolve()),
            "base_manifest_sha256": BASE_MANIFEST_SHA256,
            "card_data_sha256": CARD_DATA_SHA256,
            "probe_review_sha256": PROBE_REVIEW_SHA256,
            "probe_review_self_hash": PROBE_REVIEW_SELF_HASH,
            "probe_output_manifest_sha256": PROBE_OUTPUT_MANIFEST_SHA256,
            "dataset_reference": DATASET_REF,
            "dataset_id": DATASET_ID,
            "dataset_version": DATASET_VERSION,
            "dataset_inventory_sha256": DATASET_INVENTORY_SHA256,
            "dataset_manifest_sha256": DATASET_MANIFEST_SHA256,
            "dataset_root": str(dataset_root),
        },
        "selection_review": {
            "prequalified_metadata_records_promoted": 1,
            "prequalified_replay_bodies_reread": 0,
            "prequalified_policy_loss_targets": PREQUALIFIED_TARGETS,
            "maximum_requested_body_files": MAXIMUM_FILES,
            "maximum_requested_body_bytes": MAXIMUM_BYTES,
            "replay_bodies_read": len(body_reads),
            "replay_body_bytes_read": read_bytes,
            "qualified_new_body_files": len(qualified_body_records),
            "unread_approved_body_files": MAXIMUM_FILES - len(body_reads),
            "base_policy_loss_targets": BASE_TARGETS,
            "effective_starting_policy_loss_targets": BASE_TARGETS + PREQUALIFIED_TARGETS,
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
        "producer": "scripts/e01_corpus_target_supplement_review_v2.py",
        "status": "PASS",
        "decision": "ACCEPT_QUALIFIED_ONLY_CORPUS_V3_TARGET_FLOOR_PASSED_STOP_BEFORE_TRAINING",
        "reviewed_decision": "DEC-031",
        "corpus_manifest_sha256": sha_bytes(pretty_bytes(corpus_manifest)),
        "qualification": {
            "minimum_200_episodes": aggregate["episodes"] >= 200,
            "minimum_25000_policy_loss_targets": aggregate["policy_loss_targets"] >= MINIMUM_TARGETS,
            "prequalified_probe_metadata_promoted_without_body_reread": True,
            "approved_request_order_prefix_read": True,
            "stopped_at_first_completed_file_reaching_target_floor": True,
            "maximum_47_files_respected": len(body_reads) <= MAXIMUM_FILES,
            "maximum_175812936_bytes_respected": read_bytes <= MAXIMUM_BYTES,
            "dataset_inventory_identity_verified_before_body_reads": True,
            "dataset_manifest_identity_verified_before_body_reads": True,
            "action_alignment_verified": True,
            "deck_and_module_filtering_applied": True,
            "accepted_module_versions": sorted(ACCEPTED_MODULES),
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
            "prequalified_promoted": 1,
            "qualified_body_files": len(qualified_body_records),
            "rejected": 0,
            "read_bytes": read_bytes,
            "unread_approved_body_files": MAXIMUM_FILES - len(body_reads),
            "reviewed_episode_ids": [int(item["episode_id"]) for item in qualified_body_records],
        },
        "review_sha256": None,
    }
    corpus_review["review_sha256"] = self_hash(corpus_review, "review_sha256")

    run_review: dict[str, Any] = {
        "schema_version": 2,
        "record_id": "e01-corpus-target-supplement-review-v2",
        "source_path": OUTPUT_NAMES[0],
        "created_at_utc": completed_at,
        "producer": "scripts/e01_corpus_target_supplement_review_v2.py",
        "status": "PASS",
        "decision": "COMPLETE_APPROVED_PREQUALIFIED_PROMOTION_AND_PRIVATE_KAGGLE_CPU_PREFIX_REVIEW_FINALIZE_CORPUS_V3_AND_STOP",
        "approved_request_sha256": approved_request_sha256,
        "runner_sha256": sha_file(Path(__file__).resolve()),
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
            "prequalified_metadata_records_promoted": 1,
            "prequalified_replay_bodies_reread": 0,
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
            "prequalified_episode_id": PREQUALIFIED_EPISODE_ID,
            "prequalified_policy_loss_targets": PREQUALIFIED_TARGETS,
            "qualified_new_body_files": len(qualified_body_records),
            "rejected_new_files": 0,
            "body_reads": body_reads,
            "base_policy_loss_targets": BASE_TARGETS,
            "effective_starting_policy_loss_targets": BASE_TARGETS + PREQUALIFIED_TARGETS,
            "final_policy_loss_targets": cumulative_targets,
            "target_floor": MINIMUM_TARGETS,
            "stop_reason": "CUMULATIVE_QUALIFIED_POLICY_LOSS_TARGET_FLOOR_REACHED",
        },
        "authorization": {
            "external_compute_private_kaggle_cpu": True,
            "prequalified_probe_record_promotion": True,
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
    for name in OUTPUT_NAMES:
        path = args.out_dir / name
        if path.exists():
            path.unlink()
    outputs: dict[str, Mapping[str, Any]] = {
        OUTPUT_NAMES[0]: run_review,
        OUTPUT_NAMES[1]: corpus_manifest,
        OUTPUT_NAMES[2]: corpus_review,
    }
    for name, value in outputs.items():
        write_json(args.out_dir / name, value)
    output_manifest: dict[str, Any] = {
        "schema_version": 2,
        "record_id": "e01-corpus-target-supplement-output-manifest-v2",
        "source_path": OUTPUT_NAMES[3],
        "created_at_utc": completed_at,
        "producer": "scripts/e01_corpus_target_supplement_review_v2.py",
        "approved_request_sha256": approved_request_sha256,
        "runner_sha256": sha_file(Path(__file__).resolve()),
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
                "prequalified_metadata_records_promoted": 1,
                "prequalified_replay_bodies_reread": 0,
                "replay_bodies_read": len(body_reads),
                "replay_body_bytes_read": read_bytes,
                "qualified_new_body_files": len(qualified_body_records),
                "corpus_v3_episodes": aggregate["episodes"],
                "corpus_v3_policy_loss_targets": aggregate["policy_loss_targets"],
                "unread_approved_body_files": MAXIMUM_FILES - len(body_reads),
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
