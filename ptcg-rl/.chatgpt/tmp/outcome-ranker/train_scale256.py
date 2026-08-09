"""Fresh Scale256 supervised ranker runner (scratch only).

The dataset root is mandatory.  There is deliberately no default or fallback
to a retained Scale64 run: this entry point accepts only a sealed 256-root
collector output and trains the frozen-BC option head used by the prior proof.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

import torch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from outcome_ranker import (  # noqa: E402
    BC_TRUNK_CHECKPOINT_SHA256,
    G2_MODEL_SCHEMA_SHA256,
    G2_PACKAGE_SHA256,
    OutcomeRankerError,
    OutcomeRankerV1,
    checkpoint_bytes,
    load_checkpoint,
    load_counterfactual_dataset,
    load_gate1_trunk,
)
from ptcg_rl.g2.checkpoint import state_dict_sha256  # noqa: E402
import train_scale64 as scale64  # noqa: E402


EXPECTED_GROUPS = 256
TARGET_SPLITS = {"train": 160, "tune": 48, "test": 48}
FAMILIES = scale64.FAMILIES
SEEDS = (20260810, 20260811, 20260812, 20260813, 20260814)
UNTRAINED_SEED = 20260901
CHECKPOINT_NAME = "scale256_gate1_head.pt"
METRICS_NAME = "scale256_gate1.metrics.json"
KNOWN_RETIRED_RUNS = {
    "full-counterfactual-q-20260809T174041.651492Z-513a20492a53",
    "full-counterfactual-q-20260809T192122.022340Z-5bb37dd8b2ce",
}


class Scale256Error(RuntimeError):
    """Raised when fresh Scale256 provenance or mechanics are invalid."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sealed_manifest(root: Path) -> tuple[dict[str, Any], str]:
    manifest_path = root / "run-manifest.json"
    seal_path = root / "run-manifest.sha256"
    if not manifest_path.is_file() or not seal_path.is_file():
        raise Scale256Error("fresh collection must contain run-manifest.json and run-manifest.sha256")
    manifest_sha = _sha256(manifest_path)
    seal = seal_path.read_text(encoding="utf-8").strip().split()
    if len(seal) < 1 or seal[0] != manifest_sha:
        raise Scale256Error("run manifest sidecar does not bind the actual manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, Mapping) or manifest.get("status") != "SEALED_DIGESTS_ONLY":
        raise Scale256Error("fresh collection manifest is not a sealed collector manifest")
    run_id = manifest.get("run_id")
    if not isinstance(run_id, str) or not run_id or run_id in KNOWN_RETIRED_RUNS:
        raise Scale256Error("fresh Scale256 run_id is missing or points to a retired run")
    binding = manifest.get("dataset_binding")
    if not isinstance(binding, Mapping) or binding.get("run_id") != run_id:
        raise Scale256Error("manifest dataset_binding is not coordinator-bound")
    return dict(manifest), manifest_sha


def _manifest_paths(root: Path, manifest: Mapping[str, Any], field: str, directory: str) -> set[str]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise Scale256Error("manifest artifacts are missing")
    entries = artifacts.get(field)
    if not isinstance(entries, list) or not entries:
        raise Scale256Error(f"manifest lacks {field}")
    result: set[str] = set()
    for entry in entries:
        if not isinstance(entry, Mapping) or not isinstance(entry.get("path"), str):
            raise Scale256Error(f"manifest {field} entry is malformed")
        path = (ROOT / entry["path"]).resolve()
        expected_root = (root / directory).resolve()
        if path.parent != expected_root:
            raise Scale256Error(f"manifest {field} path escapes {directory}")
        if not path.is_file() or _sha256(path) != entry.get("sha256"):
            raise Scale256Error(f"manifest {field} digest does not match disk: {path}")
        result.add(path.name)
    return result


def _load_fresh_records(root: Path, trunk: torch.nn.Module) -> tuple[list[scale64.GroupRecord], dict[str, Any]]:
    root = root.resolve()
    manifest, manifest_sha = _sealed_manifest(root)
    dataset_names = _manifest_paths(root, manifest, "dataset_outputs", "datasets")
    worker_names = _manifest_paths(root, manifest, "worker_outputs", "workers")
    binding_paths = manifest["dataset_binding"].get("dataset_paths")
    if (
        not isinstance(binding_paths, list)
        or any(not isinstance(path, str) for path in binding_paths)
        or {Path(path).name for path in binding_paths} != dataset_names
    ):
        raise Scale256Error("manifest dataset_binding paths differ from dataset artifacts")
    dataset_paths = sorted(root.joinpath("datasets").glob("*.json"))
    worker_paths = sorted(root.joinpath("workers").glob("*.json"))
    if {path.name for path in dataset_paths} != dataset_names or {path.name for path in worker_paths} != worker_names:
        raise Scale256Error("manifest and collection directories disagree")
    workers: dict[str, Mapping[str, Any]] = {}
    for path in worker_paths:
        value = json.loads(path.read_text(encoding="utf-8"))
        state = value.get("state_group") if isinstance(value, Mapping) else None
        if not isinstance(state, Mapping) or not isinstance(state.get("state_group_id"), str):
            raise Scale256Error(f"worker lacks state_group_id: {path.name}")
        state_id = state["state_group_id"]
        if state_id in workers:
            raise Scale256Error(f"duplicate worker state: {state_id}")
        workers[state_id] = value
    if len(workers) != EXPECTED_GROUPS:
        raise Scale256Error(f"fresh Scale256 collection must contain 256 worker records, got {len(workers)}")
    records: list[scale64.GroupRecord] = []
    seen_state: set[str] = set()
    seen_public: set[str] = set()
    seen_episode: set[str] = set()
    seen_particle: set[str] = set()
    run_id = manifest["run_id"]
    dataset_meta: list[dict[str, Any]] = []
    for path in dataset_paths:
        dataset = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(dataset, Mapping) or dataset.get("schema_version") != 1:
            raise Scale256Error(f"dataset schema root is invalid: {path.name}")
        dataset_run = dataset.get("run")
        if not isinstance(dataset_run, Mapping) or dataset_run.get("run_id") != run_id:
            raise Scale256Error(f"dataset run_id does not match manifest: {path.name}")
        batch = load_counterfactual_dataset(path, trunk)
        groups = dataset.get("state_groups")
        if not isinstance(groups, list) or len(groups) != len(batch.state_group_ids):
            raise Scale256Error(f"dataset/loader group count differs: {path.name}")
        for group_index, raw_group in enumerate(groups):
            if not isinstance(raw_group, Mapping):
                raise Scale256Error("state group is not an object")
            state_id = batch.state_group_ids[group_index]
            worker = workers.get(state_id)
            if worker is None:
                raise Scale256Error(f"dataset state has no worker provenance: {state_id}")
            family = worker.get("anchor_id")
            window = worker.get("candidate_window")
            slot = worker.get("learner_slot")
            if family not in FAMILIES or window not in ("EARLY", "MID") or slot not in (0, 1):
                raise Scale256Error(f"unsupported family/seat/window stratum: {state_id}")
            public_sha = raw_group.get("public_state_sha256")
            if not isinstance(public_sha, str) or public_sha != worker["state_group"].get("public_state_sha256"):
                raise Scale256Error(f"public state hash is not worker-bound: {state_id}")
            episode_id = raw_group.get("source_episode_id")
            if not isinstance(episode_id, str):
                raise Scale256Error(f"source episode identity is missing: {state_id}")
            if state_id in seen_state or public_sha in seen_public or episode_id in seen_episode:
                raise Scale256Error("root/state/episode leakage or duplication detected")
            seen_state.add(state_id)
            seen_public.add(public_sha)
            seen_episode.add(episode_id)
            for replicate in raw_group["replicates"]:
                particle = replicate.get("determinization_id")
                if not isinstance(particle, str) or particle in seen_particle:
                    raise Scale256Error("determinization particle leakage or duplication detected")
                seen_particle.add(particle)
            records.append(
                scale64.GroupRecord(path, dataset, raw_group, batch, group_index, family, window, slot, public_sha)
            )
        dataset_meta.append(
            {
                "path": str(path),
                "sha256": _sha256(path),
                "state_groups": len(batch.state_group_ids),
                "actions": int(batch.option_embeddings.shape[0]),
                "raw_branches": sum(
                    len(replicate["actions"])
                    for group in groups
                    for replicate in group["replicates"]
                ),
            }
        )
    if len(records) != EXPECTED_GROUPS:
        raise Scale256Error(f"fresh Scale256 collection must contain exactly 256 groups, got {len(records)}")
    if len(seen_particle) == 0:
        raise Scale256Error("fresh collection contains no determinization particles")
    return records, {
        "run_id": run_id,
        "manifest_sha256": manifest_sha,
        "dataset_hashes": dataset_meta,
        "worker_count": len(workers),
        "group_count": len(records),
        "particle_count": len(seen_particle),
    }


def _allocate_quotas(strata: Mapping[tuple[str, str, int], list[scale64.GroupRecord]]) -> dict[tuple[str, str, int], dict[str, int]]:
    total = sum(len(rows) for rows in strata.values())
    if total != EXPECTED_GROUPS:
        raise Scale256Error("quota allocator received a non-Scale256 population")
    quotas: dict[tuple[str, str, int], dict[str, int]] = {}
    fractional: list[tuple[float, tuple[str, str, int], str]] = []
    assigned = {split: 0 for split in TARGET_SPLITS}
    for key in sorted(strata):
        size = len(strata[key])
        values: dict[str, int] = {}
        for split, target in TARGET_SPLITS.items():
            ideal = size * target / total
            values[split] = math.floor(ideal)
            fractional.append((ideal - values[split], key, split))
            assigned[split] += values[split]
        quotas[key] = values
    remaining = total - sum(assigned.values())
    for _, key, split in sorted(fractional, key=lambda item: (-item[0], item[1], item[2])):
        if remaining == 0:
            break
        if assigned[split] >= TARGET_SPLITS[split]:
            continue
        quotas[key][split] += 1
        assigned[split] += 1
        remaining -= 1
    if remaining or assigned != TARGET_SPLITS:
        raise Scale256Error(f"stratified quotas cannot meet 160/48/48: {assigned}")
    return quotas


def _fresh_split(records: list[scale64.GroupRecord]) -> tuple[dict[str, str], dict[str, Any]]:
    strata: dict[tuple[str, str, int], list[scale64.GroupRecord]] = defaultdict(list)
    for record in records:
        strata[(record.family, record.window, record.slot)].append(record)
    quotas = _allocate_quotas(strata)
    split_by_id: dict[str, str] = {}
    for key in sorted(strata):
        rows = sorted(strata[key], key=lambda record: record.public_state_sha)
        family, window, slot = key
        rotation = (FAMILIES.index(family) + (window == "MID") + slot) % 3
        order = ("train", "tune", "test")
        order = order[rotation:] + order[:rotation]
        cursor = 0
        for split in order:
            for record in rows[cursor : cursor + quotas[key][split]]:
                split_by_id[record.state_group_id] = split
            cursor += quotas[key][split]
    if len(split_by_id) != len(records):
        raise Scale256Error("fresh split does not cover every root group")
    counts = {split: sum(value == split for value in split_by_id.values()) for split in TARGET_SPLITS}
    if counts != TARGET_SPLITS:
        raise Scale256Error(f"fresh split counts differ: {counts}")
    summary = {
        split: {
            "groups": counts[split],
            "actions": sum(record.action_count for record in records if split_by_id[record.state_group_id] == split),
            "classes": sum(
                len(record.batch.equivalence_class_metadata[record.group_index])
                for record in records
                if split_by_id[record.state_group_id] == split
            ),
            "branches": sum(record.branch_count for record in records if split_by_id[record.state_group_id] == split),
        }
        for split in TARGET_SPLITS
    }
    return split_by_id, summary


def _evaluate_fresh(root: Path, output_dir: Path) -> dict[str, Any]:
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    trunk, binding = load_gate1_trunk()
    trunk_state_before = state_dict_sha256(trunk.state_dict())
    records, provenance = _load_fresh_records(root, trunk)
    split_by_id, split_summary = _fresh_split(records)
    train_records = scale64._ordered_records(records, split_by_id, "train")
    tune_records = scale64._ordered_records(records, split_by_id, "tune")
    test_records = scale64._ordered_records(records, split_by_id, "test")
    train_batch = scale64._split_batch(records, split_by_id, "train")
    tune_batch = scale64._split_batch(records, split_by_id, "tune")
    test_batch = scale64._split_batch(records, split_by_id, "test")
    if [record.state_group_id for record in train_records] != list(train_batch.state_group_ids):
        raise Scale256Error("train record/batch ordering differs")
    if [record.state_group_id for record in tune_records] != list(tune_batch.state_group_ids):
        raise Scale256Error("tune record/batch ordering differs")
    if [record.state_group_id for record in test_records] != list(test_batch.state_group_ids):
        raise Scale256Error("test record/batch ordering differs")
    seed_results = [scale64._train_one_seed(seed, train_batch, tune_batch, tune_records) for seed in SEEDS]
    selected = min(
        seed_results,
        key=lambda result: (-result["best_tune_concordance"], result["best_tune_loss"]["total"], result["seed"]),
    )
    ranker = selected["ranker"]
    checkpoint_payload = checkpoint_bytes(ranker, binding)
    restored = load_checkpoint(checkpoint_payload)
    with torch.inference_mode():
        selected_tune_scores = ranker(tune_batch.public_hidden, tune_batch.option_embeddings, tune_batch.option_offsets)
        tune_scores = restored(tune_batch.public_hidden, tune_batch.option_embeddings, tune_batch.option_offsets)
    if not torch.equal(selected_tune_scores, tune_scores):
        raise Scale256Error("strict checkpoint reload changed tune outputs")
    if not torch.isfinite(tune_scores).all().item():
        raise Scale256Error("selected head emitted nonfinite tune scores")
    if state_dict_sha256(trunk.state_dict()) != trunk_state_before or any(
        parameter.grad is not None for parameter in trunk.parameters()
    ):
        raise Scale256Error("frozen trunk changed during Scale256 training")
    # Test is touched exactly once, after tune-only seed selection and strict
    # reload. The three score views share this one final test phase.
    with torch.inference_mode():
        selected_test_scores = restored(test_batch.public_hidden, test_batch.option_embeddings, test_batch.option_offsets)
    torch.manual_seed(UNTRAINED_SEED)
    untrained = OutcomeRankerV1()
    with torch.inference_mode():
        untrained_test_scores = untrained(test_batch.public_hidden, test_batch.option_embeddings, test_batch.option_offsets)
    bc_test_scores = scale64._bc_action_logits(trunk, test_records)
    for value in (selected_test_scores, untrained_test_scores, bc_test_scores):
        if not torch.isfinite(value).all().item():
            raise Scale256Error("test baseline emitted nonfinite scores")
    test_metrics = {
        "selected_frozen_head": scale64._evaluate(selected_test_scores, test_batch, test_records),
        "untrained_head": scale64._evaluate(untrained_test_scores, test_batch, test_records),
        "frozen_bc_action_logits": scale64._evaluate(bc_test_scores, test_batch, test_records),
    }
    cpu_p95_ms = scale64._cpu_p95_ms(restored, test_batch)
    selected_test = test_metrics["selected_frozen_head"]
    point_delta = selected_test["mean_chosen_minus_fallback"]
    lower_delta = selected_test["state_bootstrap_delta_ci95"][0]
    family_failures = {
        family: values["mean_chosen_minus_fallback"]
        for family, values in selected_test["by_family"].items()
        if values["mean_chosen_minus_fallback"] < -0.10
    }
    promotion_killed = (
        selected_test["class_pairwise_concordance"] < 0.65
        or point_delta < 0.10
        or lower_delta <= 0.0
        or bool(family_failures)
        or cpu_p95_ms >= 20.0
    )
    metrics = {
        "status": "SCALE256_PROMOTION_KILLED" if promotion_killed else "SCALE256_PROMOTION_ELIGIBLE_PENDING_REVIEW",
        "dataset_root": str(root.resolve()),
        "provenance": provenance,
        "split_rule": "within family x seat x window, sort public_state_sha; deterministic quota allocation to exactly 160/48/48; no action-level split",
        "split_summary": split_summary,
        "config": {
            "seeds": list(SEEDS),
            "head_only": True,
            "frozen_bc": True,
            "test_evaluation_calls": 1,
            "retrained": True,
        },
        "selected_seed": selected["seed"],
        "selected_step": selected["best_step"],
        "seed_selection": [
            {
                "seed": result["seed"],
                "steps_run": result["steps_run"],
                "best_step": result["best_step"],
                "best_tune_concordance": result["best_tune_concordance"],
                "best_tune_loss": result["best_tune_loss"],
                "seconds": result["seconds"],
            }
            for result in seed_results
        ],
        "trunk_binding": {
            "g2_package_sha256": G2_PACKAGE_SHA256,
            "g2_model_schema_sha256": G2_MODEL_SCHEMA_SHA256,
            "bc_trunk_checkpoint_sha256": BC_TRUNK_CHECKPOINT_SHA256,
            "bc_trunk_state_sha256": trunk_state_before,
            "trunk_state_unchanged": True,
            "trunk_gradients_absent": True,
        },
        "checkpoint": {
            "written": not promotion_killed,
            "bytes": len(checkpoint_payload) if not promotion_killed else 0,
            "sha256": None,
        },
        "test_metrics": test_metrics,
        "promotion_gate": {
            "test_concordance": selected_test["class_pairwise_concordance"],
            "point_delta": point_delta,
            "lower_95_delta": lower_delta,
            "family_failures_below_minus_0_10": family_failures,
            "cpu_p95_ms": cpu_p95_ms,
            "killed": promotion_killed,
        },
    }
    if not promotion_killed:
        checkpoint_path = output_dir / CHECKPOINT_NAME
        checkpoint_path.write_bytes(checkpoint_payload)
        metrics["checkpoint"]["path"] = str(checkpoint_path)
        metrics["checkpoint"]["sha256"] = _sha256(checkpoint_path)
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset_root", type=Path, help="sealed fresh collector run root")
    parser.add_argument("--output-dir", type=Path, required=True, help="new scratch output directory")
    args = parser.parse_args()
    if not args.dataset_root.is_dir():
        raise SystemExit("fresh dataset root does not exist")
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise SystemExit("output directory must be new or empty")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    try:
        metrics = _evaluate_fresh(args.dataset_root, args.output_dir)
    except (Scale256Error, OutcomeRankerError) as error:
        raise SystemExit(f"KILL: {error}") from error
    metrics_path = args.output_dir / METRICS_NAME
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": metrics["status"], "metrics": str(metrics_path)}, sort_keys=True))


if __name__ == "__main__":
    main()
