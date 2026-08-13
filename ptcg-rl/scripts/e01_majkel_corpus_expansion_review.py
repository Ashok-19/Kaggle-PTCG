from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import platform
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import e01_dries_confirmation_teacher_probe_review as base  # noqa: E402

REQUEST_SHA256 = "7652f617e9bba2cd5a18a3d4b9956d348438989359e0fb200ef0f6066a590d3c"
CARD_DATA_SHA256 = "a0ea63cf7adcb65d35436ce0eb390de6e2e35654a7c67c065a45f4abaa00f373"
DECK_SHA256 = "dc8571d0bc2e546a1f85b938696cfc40a1451c68a4ccc1f695e7c3e1c74f1278"
TEACHER_TEAM_ID = 16_374_395
TEACHER_SUBMISSION_ID = 55_186_239
TEACHER_NAME = "Majkel1337"
ACCEPTED_MODULES = {"1.32.2", "1.32.3"}
OUTPUT_NAMES = (
    "e01-majkel-corpus-review-v1.json",
    "e01-approved-replay-corpus-manifest-v2.json",
    "e01-approved-replay-corpus-review-v2.json",
    "e01-majkel-corpus-review-v1-output-manifest.json",
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


def self_hash(value: Mapping[str, Any], field: str = "review_sha256") -> str:
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


def locate_dataset_root(input_root: Path, selected_names: set[str]) -> tuple[Path, dict[str, Path], dict[str, Any]]:
    candidates: list[Path] = []
    for path in input_root.rglob("*"):
        if path.is_dir() and "pokemon-tcg-ai-battle-episodes-2026-08-03" in path.name:
            candidates.append(path)
    if not candidates:
        candidates = [input_root]
    matches: list[tuple[Path, dict[str, Path], int]] = []
    for candidate in candidates:
        index: dict[str, Path] = {}
        json_count = 0
        for path in candidate.rglob("*.json"):
            if not path.is_file():
                continue
            json_count += 1
            if path.name in selected_names:
                if path.name in index:
                    raise ValueError(f"duplicate selected filename in input tree: {path.name}")
                index[path.name] = path
        if set(index) == selected_names:
            matches.append((candidate, index, json_count))
    if len(matches) != 1:
        raise ValueError(f"expected one exact daily dataset root, observed {len(matches)}")
    candidate, index, json_count = matches[0]
    inventory = {
        "input_root": str(input_root),
        "dataset_root": str(candidate),
        "selected_files_found": len(index),
        "json_files_observed_under_dataset_root": json_count,
        "metadata_tree_verified_before_body_reads": True,
    }
    return candidate, index, inventory


def inspect_raw_replay(raw: bytes, item: Mapping[str, Any], cards: Mapping[int, Mapping[str, str]]) -> dict[str, Any]:
    expected_bytes = int(item["declared_bytes"])
    if len(raw) != expected_bytes:
        raise ValueError(f"{item['file_name']} byte count differs")
    replay = json.loads(raw)
    if not isinstance(replay, Mapping):
        raise ValueError("replay top level differs")
    if replay.get("schema_version") != 1 or replay.get("name") != "cabt" or replay.get("version") != "1.0.0":
        raise ValueError("schema or environment differs")
    module_version = replay.get("module_version")
    if module_version not in ACCEPTED_MODULES:
        raise ValueError(f"module version differs: {module_version}")
    info = replay.get("info")
    if not isinstance(info, Mapping) or info.get("EpisodeId") != int(item["episode_id"]):
        raise ValueError("episode identity differs")
    if replay.get("statuses") != ["DONE", "DONE"]:
        raise ValueError("terminal statuses differ")
    rewards = replay.get("rewards")
    teacher_index = int(item["teacher_player_index"])
    if not isinstance(rewards, list) or rewards[teacher_index] != float(item["teacher_reward"]):
        raise ValueError("teacher reward differs")
    steps = replay.get("steps")
    if not isinstance(steps, list) or len(steps) < 2:
        raise ValueError("steps are missing")
    parsed: list[list[Mapping[str, Any]]] = []
    for step_index, step in enumerate(steps):
        if not isinstance(step, list) or len(step) != 2:
            raise ValueError(f"step {step_index} does not contain two players")
        parsed.append([
            base._validate_record(record, f"{item['file_name']}.steps[{step_index}][{player_index}]")
            for player_index, record in enumerate(step)
        ])
    deck_actions: list[list[int]] = []
    for player_index, record in enumerate(parsed[1]):
        action = base._validate_action(record.get("action"), f"deck[{player_index}]")
        if len(action) != 60:
            raise ValueError("initial deck action is not 60 cards")
        deck_actions.append(action)
    agents = info.get("Agents")
    teams = info.get("TeamNames")
    if not isinstance(agents, list) or not isinstance(teams, list):
        raise ValueError("agent metadata differs")
    agent_names = [agent.get("Name") if isinstance(agent, Mapping) else None for agent in agents]
    if agent_names[teacher_index] != TEACHER_NAME or teams[teacher_index] != TEACHER_NAME:
        raise ValueError("Majkel player binding differs")
    decks = [base.deck_construction(action, cards) for action in deck_actions]
    teacher_deck = decks[teacher_index]
    if teacher_deck["multiset_sha256"] != DECK_SHA256:
        raise ValueError("teacher deck differs")
    if teacher_deck["current_asset_construction_checks"] != "PASS":
        raise ValueError("current asset deck construction differs")
    counts = Counter()
    maximum_options = 0
    maximum_selection = 0
    for step_index in range(2, len(parsed)):
        current = parsed[step_index][teacher_index]
        action = base._validate_action(current.get("action"), f"action[{step_index}][{teacher_index}]")
        previous = parsed[step_index - 1][teacher_index]
        if previous.get("status") != "ACTIVE":
            if action:
                raise ValueError("action after inactive record")
            continue
        request = base._selection_request(previous, f"previous[{step_index - 1}][{teacher_index}]")
        if request is None:
            if action:
                raise ValueError("action after missing request")
            continue
        minimum = base._integer(request.get("minCount"), "minimum")
        maximum = base._integer(request.get("maxCount"), "maximum")
        options = request.get("option")
        if not isinstance(options, list) or any(not isinstance(option, Mapping) for option in options):
            raise ValueError("request options differ")
        if not minimum <= len(action) <= maximum:
            raise ValueError("selection count outside bounds")
        if not base._resolves_against_options(action, options):
            raise ValueError("action does not resolve against legal options")
        forced = maximum == 0 or (minimum == maximum == 1 and len(options) == 1)
        counts["teacher_active_requests"] += 1
        counts["forced_teacher_requests"] += int(forced)
        counts["policy_loss_targets"] += int(not forced)
        counts["stop_targets"] += int(len(action) < maximum)
        counts["ordered_requests"] += int(request.get("type") == 5 and request.get("context") == 34)
        maximum_options = max(maximum_options, len(options))
        maximum_selection = max(maximum_selection, len(action))
    return {
        "episode_id": int(item["episode_id"]),
        "file_name": str(item["file_name"]),
        "bytes": len(raw),
        "sha256": sha_bytes(raw),
        "schema_version": 1,
        "environment_name": "cabt",
        "environment_version": "1.0.0",
        "module_version": module_version,
        "teacher_player_index": teacher_index,
        "teacher_reward": float(item["teacher_reward"]),
        "teacher_team_id": TEACHER_TEAM_ID,
        "teacher_team": TEACHER_NAME,
        "teacher_submission_id": TEACHER_SUBMISSION_ID,
        "stratum": str(item["stratum"]),
        "teacher_deck_multiset_sha256": teacher_deck["multiset_sha256"],
        "opponent_deck_multiset_sha256": decks[1 - teacher_index]["multiset_sha256"],
        "teacher_active_requests": counts["teacher_active_requests"],
        "forced_teacher_requests": counts["forced_teacher_requests"],
        "meaningful_teacher_decisions": counts["policy_loss_targets"],
        "policy_loss_targets": counts["policy_loss_targets"],
        "stop_targets": counts["stop_targets"],
        "ordered_requests": counts["ordered_requests"],
        "maximum_option_count": maximum_options,
        "maximum_selection_count": maximum_selection,
        "action_alignment": "PASS",
        "current_asset_construction_compatibility": "PASS",
    }


def split_for(record: Mapping[str, Any], seed: int) -> tuple[str, str]:
    key = f"{seed}|{record['module_version']}|{record['stratum']}|{record['episode_id']}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    bucket = int(digest[:16], 16) % 100
    split = "train" if bucket < 80 else ("validation" if bucket < 90 else "test")
    return split, digest


def prior_probe_records(probe: Mapping[str, Any], seed: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for episode in probe["episodes"]:
        teacher_index = int(episode["teacher_player_index"])
        reward = float(episode["teacher_reward"])
        record = {
            "episode_id": int(episode["episode_id"]),
            "bytes": int(episode["file"]["bytes"]),
            "sha256": str(episode["file"]["sha256"]),
            "path": str(episode["file"]["path"]),
            "schema_version": 1,
            "environment_name": "cabt",
            "environment_version": "1.0.0",
            "module_version": str(episode["module_version"]),
            "teacher_player_index": teacher_index,
            "teacher_reward": reward,
            "teacher_team_id": TEACHER_TEAM_ID,
            "teacher_team": TEACHER_NAME,
            "teacher_submission_id": TEACHER_SUBMISSION_ID,
            "teacher_key": "majkel",
            "stratum": f"seat_{teacher_index}_{'win' if reward > 0 else 'loss'}",
            "teacher_active_requests": int(episode["action_alignment"]["teacher_active_selection_requests"]),
            "forced_teacher_requests": int(episode["action_alignment"]["teacher_forced_singleton_requests"]),
            "meaningful_teacher_decisions": int(episode["action_alignment"]["teacher_policy_loss_targets_if_later_authorized"]),
            "policy_loss_targets": int(episode["action_alignment"]["teacher_policy_loss_targets_if_later_authorized"]),
            "stop_targets": None,
            "ordered_requests": None,
            "source_review": "reports/artifacts/e01-majkel-live-gold-teacher-probe-review-v1.json",
            "body_reread_for_v2": False,
        }
        split, digest = split_for(record, seed)
        record["split"] = split
        record["split_key_sha256"] = digest
        records.append(record)
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, default=Path("/kaggle/input"))
    parser.add_argument("--out-dir", type=Path, default=Path("/kaggle/working/e01-majkel-corpus-review-v1"))
    parser.add_argument("--request", type=Path, default=ROOT / "configs/e01_majkel_corpus_expansion_request_v1.json")
    parser.add_argument("--base-manifest", type=Path, default=ROOT / "reports/artifacts/e01-approved-replay-corpus-manifest-v1.json")
    parser.add_argument("--probe-review", type=Path, default=ROOT / "reports/artifacts/e01-majkel-live-gold-teacher-probe-review-v1.json")
    parser.add_argument("--card-data", type=Path, default=ROOT / "private/assets/official/EN_Card_Data.csv")
    args = parser.parse_args()
    started = time.monotonic()
    if sha_file(args.request) != REQUEST_SHA256:
        raise ValueError("approved expansion request hash differs")
    if sha_file(args.card_data) != CARD_DATA_SHA256:
        raise ValueError("card data hash differs")
    request = load_json(args.request)
    base_manifest = load_json(args.base_manifest)
    probe = load_json(args.probe_review)
    if request.get("status") != "READY_UNAUTHORIZED" or request.get("authorized") is not False:
        raise ValueError("embedded request differs from approved pre-execution form")
    episodes = request.get("episodes")
    if not isinstance(episodes, list) or len(episodes) != 269:
        raise ValueError("request does not contain exactly 269 episodes")
    selected_names = {str(item["file_name"]) for item in episodes}
    if len(selected_names) != 269:
        raise ValueError("request episode filenames are not unique")
    declared_total = sum(int(item["declared_bytes"]) for item in episodes)
    if declared_total != 1_030_207_171:
        raise ValueError("request byte cap differs")
    dataset_root, index, input_inventory = locate_dataset_root(args.input_root, selected_names)
    cards = base.card_table()
    known_ids = {int(item["episode_id"]) for item in base_manifest["inventory"]["files"]}
    known_hashes = {str(item["sha256"]) for item in base_manifest["inventory"]["files"]}
    for episode in probe["episodes"]:
        known_ids.add(int(episode["episode_id"]))
        known_hashes.add(str(episode["file"]["sha256"]))
    qualified: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    read_bytes = 0
    observed_new_hashes: set[str] = set()
    for position, item in enumerate(episodes):
        filename = str(item["file_name"])
        path = index[filename]
        raw = path.read_bytes()
        read_bytes += len(raw)
        try:
            record = inspect_raw_replay(raw, item, cards)
            if record["episode_id"] in known_ids:
                raise ValueError("duplicate episode id against frozen corpus or reviewed probe")
            if record["sha256"] in known_hashes or record["sha256"] in observed_new_hashes:
                raise ValueError("duplicate content hash")
            observed_new_hashes.add(record["sha256"])
            record["source_dataset_path"] = str(path.relative_to(dataset_root))
            record["source_review"] = "e01-majkel-corpus-review-v1.json"
            record["teacher_key"] = "majkel"
            split, digest = split_for(record, int(request["corpus_v2_policy"]["split_seed"]))
            record["split"] = split
            record["split_key_sha256"] = digest
            qualified.append(record)
        except Exception as error:
            rejected.append({
                "episode_id": int(item["episode_id"]),
                "file_name": filename,
                "bytes": len(raw),
                "sha256": sha_bytes(raw),
                "reason": f"{type(error).__name__}: {error}",
            })
        if (position + 1) % 25 == 0:
            print(json.dumps({"reviewed": position + 1, "qualified": len(qualified), "rejected": len(rejected), "read_bytes": read_bytes}), flush=True)
    if read_bytes != declared_total:
        raise ValueError("actual replay bytes read differ from approved cap")
    base_records = copy.deepcopy(base_manifest["qualified_training_corpus"]["episode_records"])
    probe_records = prior_probe_records(probe, int(request["corpus_v2_policy"]["split_seed"]))
    majkel_records = probe_records + qualified
    all_records = base_records + majkel_records
    if len({int(item["episode_id"]) for item in all_records}) != len(all_records):
        raise ValueError("corpus-v2 episode ids are not unique")
    all_hashes = [str(item["sha256"]) for item in all_records]
    if len(set(all_hashes)) != len(all_hashes):
        raise ValueError("corpus-v2 content hashes are not unique")
    aggregate = Counter()
    splits: dict[str, Counter[str]] = defaultdict(Counter)
    teachers: dict[str, Counter[str]] = defaultdict(Counter)
    for item in all_records:
        for key in ("bytes", "teacher_active_requests", "forced_teacher_requests", "meaningful_teacher_decisions", "policy_loss_targets"):
            aggregate[key] += int(item[key])
            splits[str(item["split"])][key] += int(item[key])
            teachers[str(item["teacher_key"])][key] += int(item[key])
        aggregate["episodes"] += 1
        splits[str(item["split"])]["episodes"] += 1
        teachers[str(item["teacher_key"])]["episodes"] += 1
    corpus_manifest: dict[str, Any] = {
        "schema_version": 2,
        "record_id": "e01-approved-replay-corpus-manifest-v2",
        "source_path": "e01-approved-replay-corpus-manifest-v2.json",
        "created_at_utc": "2026-08-04T15:24:13Z",
        "producer": "scripts/e01_majkel_corpus_expansion_review.py",
        "decision_id": "DEC-027",
        "status": "PASS_QUALIFIED_ONLY_CORPUS_V2_FROZEN",
        "inputs": {
            "approved_request_sha256": REQUEST_SHA256,
            "base_manifest_sha256": sha_file(args.base_manifest),
            "probe_review_sha256": sha_file(args.probe_review),
            "card_data_sha256": CARD_DATA_SHA256,
            "dataset_root": str(dataset_root),
        },
        "selection_review": {
            "new_files_read": 269,
            "new_bytes_read": read_bytes,
            "qualified_new_files": len(qualified),
            "rejected_new_files": len(rejected),
            "reused_probe_files_without_body_reread": 2,
            "replay_body_outputs": 0,
        },
        "qualified_training_corpus": {
            "episodes": aggregate["episodes"],
            "bytes": aggregate["bytes"],
            "teacher_active_requests": aggregate["teacher_active_requests"],
            "forced_teacher_requests": aggregate["forced_teacher_requests"],
            "meaningful_teacher_decisions": aggregate["meaningful_teacher_decisions"],
            "policy_loss_targets": aggregate["policy_loss_targets"],
            "episode_records": sorted(all_records, key=lambda item: int(item["episode_id"])),
            "split_counts": {key: dict(value) for key, value in sorted(splits.items())},
            "teacher_counts": {key: dict(value) for key, value in sorted(teachers.items())},
        },
        "sampling_policy": request["corpus_v2_policy"],
        "rejected_new_records": sorted(rejected, key=lambda item: int(item["episode_id"])),
        "manifest_sha256": None,
    }
    corpus_manifest["manifest_sha256"] = self_hash(corpus_manifest, "manifest_sha256")
    corpus_review: dict[str, Any] = {
        "schema_version": 2,
        "record_id": "e01-approved-replay-corpus-review-v2",
        "source_path": "e01-approved-replay-corpus-review-v2.json",
        "created_at_utc": "2026-08-04T15:24:13Z",
        "producer": "scripts/e01_majkel_corpus_expansion_review.py",
        "status": "PASS" if aggregate["episodes"] >= 200 and aggregate["policy_loss_targets"] >= 25_000 else "BLOCKED_FLOORS",
        "decision": "ACCEPT_QUALIFIED_ONLY_MAJKEL_DOMINANT_CORPUS_V2" if aggregate["episodes"] >= 200 and aggregate["policy_loss_targets"] >= 25_000 else "RETAIN_CORPUS_V2_BUT_BLOCK_PRODUCTION_TRAINING_FLOORS",
        "reviewed_decision": "DEC-027",
        "corpus_manifest_sha256": sha_bytes(pretty_bytes(corpus_manifest)),
        "qualification": {
            "minimum_200_episodes": aggregate["episodes"] >= 200,
            "minimum_25000_policy_loss_targets": aggregate["policy_loss_targets"] >= 25_000,
            "exact_named_file_set_read": True,
            "exact_new_byte_cap_met": True,
            "action_alignment_verified": True,
            "deck_and_module_filtering_applied": True,
            "duplicate_episode_or_content_hashes": 0,
            "episode_level_split": True,
            "replay_body_outputs": 0,
            "optimizer_steps": 0,
            "training": False,
            "model_mutation": False,
            "submission": False,
        },
        "counts": dict(aggregate),
        "new_review": {
            "qualified": len(qualified),
            "rejected": len(rejected),
            "read_bytes": read_bytes,
        },
        "review_sha256": None,
    }
    corpus_review["review_sha256"] = self_hash(corpus_review)
    run_review: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e01-majkel-corpus-review-v1",
        "source_path": "e01-majkel-corpus-review-v1.json",
        "created_at_utc": "2026-08-04T15:24:13Z",
        "producer": "scripts/e01_majkel_corpus_expansion_review.py",
        "status": "PASS",
        "decision": "COMPLETE_EXACT_269_FILE_PRIVATE_KAGGLE_CPU_BODY_REVIEW_AND_STOP",
        "approved_request_sha256": REQUEST_SHA256,
        "runtime": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count(),
            "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
            "internet_requested": False,
            "gpu_used": False,
            "tpu_used": False,
            "wall_seconds": time.monotonic() - started,
        },
        "input_inventory": input_inventory,
        "transfer": {
            "named_replay_bodies_read": 269,
            "new_bytes_read": read_bytes,
            "maximum_new_bytes": 1_030_207_171,
            "reused_probe_bodies_without_reread": 2,
            "additional_replay_bodies_read": 0,
            "replay_body_outputs": 0,
            "agent_logs_read": 0,
        },
        "review": {
            "qualified_new_files": len(qualified),
            "rejected_new_files": len(rejected),
            "qualified_episode_ids": [item["episode_id"] for item in qualified],
            "rejected_records": rejected,
        },
        "authorization": {
            "optimizer_created": False,
            "optimizer_steps": 0,
            "training": False,
            "model_mutation": False,
            "model_promotion": False,
            "submission": False,
            "git_commit": False,
            "git_push": False,
        },
        "outputs": list(OUTPUT_NAMES),
        "review_sha256": None,
    }
    run_review["review_sha256"] = self_hash(run_review)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        OUTPUT_NAMES[0]: run_review,
        OUTPUT_NAMES[1]: corpus_manifest,
        OUTPUT_NAMES[2]: corpus_review,
    }
    for name, value in paths.items():
        write_json(args.out_dir / name, value)
    output_manifest: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e01-majkel-corpus-review-v1-output-manifest",
        "source_path": OUTPUT_NAMES[3],
        "created_at_utc": "2026-08-04T15:24:13Z",
        "files": [
            {"path": name, "bytes": (args.out_dir / name).stat().st_size, "sha256": sha_file(args.out_dir / name)}
            for name in OUTPUT_NAMES[:3]
        ],
        "replay_body_outputs": 0,
        "manifest_sha256": None,
    }
    output_manifest["manifest_sha256"] = self_hash(output_manifest, "manifest_sha256")
    write_json(args.out_dir / OUTPUT_NAMES[3], output_manifest)
    print(json.dumps({
        "status": run_review["status"],
        "qualified_new_files": len(qualified),
        "rejected_new_files": len(rejected),
        "corpus_episodes": aggregate["episodes"],
        "policy_loss_targets": aggregate["policy_loss_targets"],
        "new_bytes_read": read_bytes,
        "output_dir": str(args.out_dir),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
