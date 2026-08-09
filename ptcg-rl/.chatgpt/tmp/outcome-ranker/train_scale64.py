"""First Scale64 frozen-BC-head experiment (scratch only).

This script is deliberately state-grouped: all legal actions from a public
root stay in one split, and only the 27,841-parameter outcome head sees the
training tensors. Test outcomes are not scored until the selected seed has a
strictly reloaded checkpoint on disk.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import torch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from outcome_ranker import (  # noqa: E402
    BC_TRUNK_CHECKPOINT_SHA256,
    BC_TRUNK_STATE_SHA256,
    G2_MODEL_SCHEMA_SHA256,
    G2_PACKAGE_SHA256,
    OutcomeRankerError,
    OutcomeRankerV1,
    RankerBatch,
    checkpoint_bytes,
    grouped_ranker_loss,
    load_checkpoint,
    load_counterfactual_dataset,
    load_gate1_trunk,
    _hidden_from_history,
    _projected_decision,
)
from ptcg_rl.g2.checkpoint import state_dict_sha256  # noqa: E402
from ptcg_rl.g2.network import collate_projected  # noqa: E402


RUN_ROOT = ROOT / ".chatgpt/tmp/counterfactual-q/runs/full-counterfactual-q-20260809T192122.022340Z-5bb37dd8b2ce"
DATASET_ROOT = RUN_ROOT / "datasets"
WORKER_ROOT = RUN_ROOT / "workers"
CHECKPOINT_PATH = Path(__file__).with_name("scale64_gate1_head_experimental.pt")
METRICS_PATH = Path(__file__).with_name("scale64_gate1.metrics.json")
MANIFEST_SHA256 = "b2d07cf24bd71a456d779b94abacc7eb784c2bce348ccd7a924f0f6f577c52e0"

DATASET_HASHES = {
    "counterfactual-action-dataset-dragapult-ex.json": "5810c77058c4c362a9c33ef43579ee46d584846807643abe9d0daf19d748227a",
    "counterfactual-action-dataset-grim-source-mirror.json": "c1d7d1ce621b638ea9a5c575cabb8c0a6de0c3c766bdb054ea40e0463264bbb4",
    "counterfactual-action-dataset-iono.json": "e6c16038b0b75717071b1e6d181b36580c6f4f27f877d3db42fe4179129fb55a",
    "counterfactual-action-dataset-mega-lucario-ex.json": "c6f109224f3ef6e54a6d6e4cc10b21c151e96189654a28559de201eefbfb54c0",
    "counterfactual-action-dataset-public-alakazam-v9.json": "508ecbfd485716d0fec5b4011f583157f466c27df6db0c9f779ad75a283f1959",
    "counterfactual-action-dataset-public-lopunny-v9-arena-alias.json": "83b134fc9f611d508803148607e70ec5920c009955a0709599878a8739be72e3",
}
FAMILIES = (
    "dragapult-ex",
    "grim-source-mirror",
    "iono",
    "mega-lucario-ex",
    "public-alakazam-v9",
    "public-lopunny-v9-arena-alias",
)
EXPECTED_SPLITS = {
    "train": {"groups": 40, "actions": 247, "classes": 228, "branches": 988, "nondegenerate": 36, "pairs": 386},
    "tune": {"groups": 12, "actions": 78, "classes": 66, "branches": 312, "nondegenerate": 11, "pairs": 98},
    "test": {"groups": 12, "actions": 72, "classes": 67, "branches": 288, "nondegenerate": 10, "pairs": 106},
}
SEEDS = (20260810, 20260811, 20260812, 20260813, 20260814)
UNTRAINED_SEED = 20260901
BOOTSTRAP_SEED = 20260810
LEARNING_RATE = 0.01
PAIRWISE_WEIGHT = 0.25
TEMPERATURE = 0.25
MAX_STEPS = 500
PATIENCE = 60


class Scale64Error(RuntimeError):
    """Raised when the bounded Scale64 experiment cannot be trusted."""


@dataclass(frozen=True)
class GroupRecord:
    path: Path
    dataset: Mapping[str, Any]
    raw_group: Mapping[str, Any]
    batch: RankerBatch
    group_index: int
    family: str
    window: str
    slot: int
    public_state_sha: str

    @property
    def state_group_id(self) -> str:
        return self.batch.state_group_ids[self.group_index]

    @property
    def action_count(self) -> int:
        start, end = self.batch.group_offsets[self.group_index : self.group_index + 2].tolist()
        return end - start

    @property
    def branch_count(self) -> int:
        return sum(len(replicate["actions"]) for replicate in self.raw_group["replicates"])


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _finite_tensor(value: torch.Tensor, label: str) -> None:
    if not torch.isfinite(value).all().item():
        raise Scale64Error(f"nonfinite {label}")


def _load_workers() -> dict[str, Mapping[str, Any]]:
    workers: dict[str, Mapping[str, Any]] = {}
    for path in WORKER_ROOT.glob("*.json"):
        value = json.loads(path.read_text(encoding="utf-8"))
        state = value.get("state_group")
        if not isinstance(state, Mapping) or not isinstance(state.get("state_group_id"), str):
            raise Scale64Error(f"worker metadata lacks state identity: {path}")
        state_id = state["state_group_id"]
        if state_id in workers:
            raise Scale64Error(f"duplicate worker state identity: {state_id}")
        workers[state_id] = value
    if len(workers) != 64:
        raise Scale64Error(f"expected 64 worker state records, got {len(workers)}")
    return workers


def _load_records(trunk: torch.nn.Module) -> tuple[list[GroupRecord], dict[str, Any]]:
    manifest_path = RUN_ROOT / "run-manifest.json"
    if _sha256_file(manifest_path) != MANIFEST_SHA256:
        raise Scale64Error("sealed Scale64 run manifest hash differs")
    workers = _load_workers()
    paths = sorted(DATASET_ROOT.glob("*.json"))
    if {path.name for path in paths} != set(DATASET_HASHES):
        raise Scale64Error("sealed Scale64 dataset file set differs")
    records: list[GroupRecord] = []
    seen_state_ids: set[str] = set()
    seen_public_shas: set[str] = set()
    seen_episode_ids: set[str] = set()
    seen_determinization_ids: set[str] = set()
    dataset_metadata: list[dict[str, Any]] = []
    for path in paths:
        digest = _sha256_file(path)
        if digest != DATASET_HASHES[path.name]:
            raise Scale64Error(f"dataset hash differs: {path.name}")
        dataset = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(dataset, Mapping):
            raise Scale64Error(f"dataset root is not an object: {path.name}")
        run = dataset.get("run")
        if not isinstance(run, Mapping) or {
            run.get("g2_package_sha256"),
            run.get("model_schema_sha256"),
            run.get("bc_trunk_checkpoint_sha256"),
            run.get("bc_trunk_state_sha256"),
            run.get("trunk_mode"),
        } != {
            G2_PACKAGE_SHA256,
            G2_MODEL_SCHEMA_SHA256,
            BC_TRUNK_CHECKPOINT_SHA256,
            BC_TRUNK_STATE_SHA256,
            "FROZEN_BC_EPOCH4_HEAD_ONLY",
        }:
            raise Scale64Error(f"dataset provenance differs: {path.name}")
        batch = load_counterfactual_dataset(path, trunk)
        groups = dataset.get("state_groups")
        if not isinstance(groups, list) or len(groups) != len(batch.state_group_ids):
            raise Scale64Error(f"dataset/group loader count mismatch: {path.name}")
        for group_index, raw_group in enumerate(groups):
            if not isinstance(raw_group, Mapping):
                raise Scale64Error("raw state group is not an object")
            state_id = batch.state_group_ids[group_index]
            if state_id in seen_state_ids:
                raise Scale64Error(f"state group appears in multiple datasets: {state_id}")
            worker = workers.get(state_id)
            if worker is None:
                raise Scale64Error(f"state group lacks worker provenance: {state_id}")
            state = worker["state_group"]
            family = worker.get("anchor_id")
            window = worker.get("candidate_window")
            slot = worker.get("learner_slot")
            if family not in FAMILIES or window not in ("EARLY", "MID") or slot not in (0, 1):
                raise Scale64Error(f"state worker stratum is malformed: {state_id}")
            public_sha = raw_group.get("public_state_sha256")
            if public_sha != state.get("public_state_sha256") or public_sha in seen_public_shas:
                raise Scale64Error(f"public-state identity is missing or duplicated: {state_id}")
            episode_id = raw_group.get("source_episode_id")
            if not isinstance(episode_id, str) or episode_id in seen_episode_ids:
                raise Scale64Error(f"source episode identity is missing or duplicated: {state_id}")
            seen_state_ids.add(state_id)
            seen_public_shas.add(public_sha)
            seen_episode_ids.add(episode_id)
            for replicate in raw_group["replicates"]:
                determinization_id = replicate.get("determinization_id")
                if not isinstance(determinization_id, str) or determinization_id in seen_determinization_ids:
                    raise Scale64Error(f"particle identity leaks or duplicates: {state_id}")
                seen_determinization_ids.add(determinization_id)
            records.append(
                GroupRecord(path, dataset, raw_group, batch, group_index, family, window, slot, public_sha)
            )
        dataset_metadata.append(
            {
                "path": str(path),
                "sha256": digest,
                "state_group_count": len(batch.state_group_ids),
                "action_count": int(batch.option_embeddings.shape[0]),
                "raw_branch_count": sum(
                    len(replicate["actions"])
                    for group in dataset["state_groups"]
                    for replicate in group["replicates"]
                ),
            }
        )
    if len(records) != 64 or sum(record.action_count for record in records) != 397:
        raise Scale64Error("sealed Scale64 coverage is not 64 groups/397 actions")
    if sum(record.branch_count for record in records) != 1588 or len(seen_determinization_ids) != 256:
        raise Scale64Error("sealed Scale64 coverage is not 1,588 branches/256 particles")
    return records, {"manifest_sha256": MANIFEST_SHA256, "datasets": dataset_metadata}


def _class_view(batch: RankerBatch, group_index: int) -> dict[str, Any]:
    start, end = batch.group_offsets[group_index : group_index + 2].tolist()
    keys = list(batch.semantic_equivalence_keys[start:end])
    members: dict[str, list[int]] = defaultdict(list)
    for index, key in enumerate(keys):
        members[key].append(index)
    metadata = {
        str(item["semantic_equivalence_key"]): item
        for item in batch.equivalence_class_metadata[group_index]
    }
    ordered_keys = sorted(members)
    representatives = [min(members[key]) for key in ordered_keys]
    if set(ordered_keys) != set(metadata):
        raise Scale64Error("batch class metadata and transport keys differ")
    targets = [float(metadata[key]["target"]) for key in ordered_keys]
    return {
        "start": start,
        "end": end,
        "keys": ordered_keys,
        "members": [sorted(members[key]) for key in ordered_keys],
        "representatives": representatives,
        "targets": targets,
    }


def _class_pairs(targets: list[float]) -> tuple[int, float]:
    comparable = 0
    for left in range(len(targets)):
        for right in range(left + 1, len(targets)):
            if targets[left] != targets[right]:
                comparable += 1
    return comparable, int(comparable > 0)


def _validate_split(records: list[GroupRecord]) -> tuple[dict[str, str], dict[str, Any]]:
    strata: dict[tuple[str, str, int], list[GroupRecord]] = defaultdict(list)
    for record in records:
        strata[(record.family, record.window, record.slot)].append(record)
    split_by_id: dict[str, str] = {}
    for (family, window, slot), values in strata.items():
        values.sort(key=lambda record: record.public_state_sha)
        if len(values) not in (2, 3):
            raise Scale64Error("Scale64 stratum must contain two or three states")
        family_index = FAMILIES.index(family)
        window_index = 0 if window == "EARLY" else 1
        for index, record in enumerate(values):
            if index:
                split = "train"
            else:
                split = "test" if (family_index + window_index + slot) % 2 == 1 else "tune"
            if record.state_group_id in split_by_id:
                raise Scale64Error("split assigns a state group more than once")
            split_by_id[record.state_group_id] = split
    if len(split_by_id) != len(records):
        raise Scale64Error("split does not cover every state group")

    summaries: dict[str, dict[str, int]] = {}
    for split in ("train", "tune", "test"):
        chosen = [record for record in records if split_by_id[record.state_group_id] == split]
        classes = 0
        nondegenerate = 0
        pairs = 0
        for record in chosen:
            view = _class_view(record.batch, record.group_index)
            count, nondeg = _class_pairs(view["targets"])
            classes += len(view["keys"])
            nondegenerate += nondeg
            pairs += count
        summaries[split] = {
            "groups": len(chosen),
            "actions": sum(record.action_count for record in chosen),
            "classes": classes,
            "branches": sum(record.branch_count for record in chosen),
            "nondegenerate": nondegenerate,
            "pairs": pairs,
        }
    if summaries != EXPECTED_SPLITS:
        raise Scale64Error(f"audited Scale64 split mismatch: {json.dumps(summaries, sort_keys=True)}")
    # All roots/classes/particles/source episodes are whole-state keys. These
    # checks are intentionally explicit rather than relying on a random split.
    for key, split in split_by_id.items():
        if not key or not split:
            raise Scale64Error("empty split identity")
    class_keys = [
        (record.state_group_id, key)
        for record in records
        for key in set(record.batch.semantic_equivalence_keys)
    ]
    if len(class_keys) != len(set(class_keys)):
        raise Scale64Error("semantic class key collision across root groups")
    particle_keys = [
        (record.state_group_id, replicate["determinization_id"])
        for record in records
        for replicate in record.raw_group["replicates"]
    ]
    if len(particle_keys) != len(set(particle_keys)):
        raise Scale64Error("particle key collision across root groups")
    return split_by_id, summaries


def _one_group(record: GroupRecord) -> RankerBatch:
    batch = record.batch
    group_index = record.group_index
    option_start, option_end = batch.group_offsets[group_index : group_index + 2].tolist()
    return RankerBatch(
        public_hidden=batch.public_hidden[group_index : group_index + 1],
        option_embeddings=batch.option_embeddings[option_start:option_end],
        option_available=batch.option_available[option_start:option_end],
        option_offsets=torch.tensor([0, option_end - option_start], dtype=torch.long),
        target=batch.target[option_start:option_end],
        target_stderr=batch.target_stderr[option_start:option_end],
        target_weight=batch.target_weight[option_start:option_end],
        target_mask=batch.target_mask[option_start:option_end],
        group_offsets=torch.tensor([0, option_end - option_start], dtype=torch.long),
        state_group_ids=(record.state_group_id,),
        action_ids=tuple(batch.action_ids[option_start:option_end]),
        semantic_fingerprints=tuple(batch.semantic_fingerprints[option_start:option_end]),
        semantic_equivalence_keys=tuple(batch.semantic_equivalence_keys[option_start:option_end]),
        equivalence_class_metadata=(batch.equivalence_class_metadata[group_index],),
    )


def _concat(batches: Iterable[RankerBatch]) -> RankerBatch:
    values = tuple(batches)
    if not values:
        raise Scale64Error("cannot build an empty split batch")
    state_ids = tuple(state_id for batch in values for state_id in batch.state_group_ids)
    if len(state_ids) != len(set(state_ids)):
        raise Scale64Error("state group is duplicated in a split batch")
    option_offsets = [0]
    group_offsets = [0]
    for batch in values:
        option_count = int(batch.option_embeddings.shape[0])
        option_offsets.append(option_offsets[-1] + option_count)
        group_offsets.append(group_offsets[-1] + option_count)
    return RankerBatch(
        public_hidden=torch.cat([batch.public_hidden for batch in values]),
        option_embeddings=torch.cat([batch.option_embeddings for batch in values]),
        option_available=torch.cat([batch.option_available for batch in values]),
        option_offsets=torch.tensor(option_offsets, dtype=torch.long),
        target=torch.cat([batch.target for batch in values]),
        target_stderr=torch.cat([batch.target_stderr for batch in values]),
        target_weight=torch.cat([batch.target_weight for batch in values]),
        target_mask=torch.cat([batch.target_mask for batch in values]),
        group_offsets=torch.tensor(group_offsets, dtype=torch.long),
        state_group_ids=state_ids,
        action_ids=tuple(action_id for batch in values for action_id in batch.action_ids),
        semantic_fingerprints=tuple(fp for batch in values for fp in batch.semantic_fingerprints),
        semantic_equivalence_keys=tuple(key for batch in values for key in batch.semantic_equivalence_keys),
        equivalence_class_metadata=tuple(
            metadata for batch in values for metadata in batch.equivalence_class_metadata
        ),
    )


def _ordered_records(
    records: list[GroupRecord], split_by_id: Mapping[str, str], split: str
) -> list[GroupRecord]:
    return sorted(
        (record for record in records if split_by_id[record.state_group_id] == split),
        key=lambda record: (FAMILIES.index(record.family), record.window, record.slot, record.public_state_sha),
    )


def _split_batch(records: list[GroupRecord], split_by_id: Mapping[str, str], split: str) -> RankerBatch:
    ordered = _ordered_records(records, split_by_id, split)
    return _concat(_one_group(record) for record in ordered)


def _pairwise(scores: list[float], targets: list[float]) -> tuple[float, int, float]:
    correct = 0.0
    comparable = 0
    for left in range(len(targets)):
        for right in range(left + 1, len(targets)):
            delta = targets[left] - targets[right]
            if delta == 0.0:
                continue
            comparable += 1
            score_delta = scores[left] - scores[right]
            if score_delta * delta > 0:
                correct += 1.0
            elif score_delta == 0.0:
                correct += 0.5
    return (correct / comparable if comparable else 1.0), comparable, correct


def _top(values: list[float]) -> list[int]:
    maximum = max(values)
    return [index for index, value in enumerate(values) if abs(value - maximum) <= 1e-7]


def _evaluate(scores: torch.Tensor, batch: RankerBatch, records: list[GroupRecord]) -> dict[str, Any]:
    if scores.ndim != 1 or scores.shape != batch.target.shape:
        raise Scale64Error("score shape differs from the complete option batch")
    _finite_tensor(scores, "evaluation scores")
    records_by_id = {record.state_group_id: record for record in records}
    groups: list[dict[str, Any]] = []
    total_correct = 0.0
    total_pairs = 0
    calibration_values: list[tuple[float, float]] = []
    for group_index, state_id in enumerate(batch.state_group_ids):
        record = records_by_id[state_id]
        view = _class_view(batch, group_index)
        start, end = view["start"], view["end"]
        representative_scores = [float(scores[start + index]) for index in view["representatives"]]
        concordance, pairs, correct = _pairwise(representative_scores, view["targets"])
        total_correct += correct
        total_pairs += pairs
        target_top = _top(view["targets"])
        predicted_top = _top(representative_scores)
        local_scores = scores[start:end]
        chosen_index = int(torch.argmax(local_scores).item())
        action_ids = list(batch.action_ids[start:end])
        aggregate_baselines = {
            aggregate.get("baseline_action_id")
            for aggregate in record.raw_group["action_aggregates"]
            if aggregate.get("baseline_action_id") is not None
        }
        if len(aggregate_baselines) != 1:
            raise Scale64Error(f"state has no unique recorded fallback: {state_id}")
        fallback_action_id = next(iter(aggregate_baselines))
        fallback_indices = [index for index, action_id in enumerate(action_ids) if action_id == fallback_action_id]
        if not fallback_indices:
            raise Scale64Error(f"recorded fallback action is absent from transport: {state_id}")
        fallback_index = min(fallback_indices)
        local_target = batch.target[start:end]
        oracle_target = max(view["targets"])
        chosen_target = float(local_target[chosen_index])
        fallback_target = float(local_target[fallback_index])
        for score, target in zip(representative_scores, view["targets"]):
            calibration_values.append((max(-1.0, min(1.0, score)), target))
        groups.append(
            {
                "state_group_id": state_id,
                "family": record.family,
                "window": record.window,
                "slot": record.slot,
                "public_state_sha256": record.public_state_sha,
                "class_pairwise_concordance": concordance,
                "comparable_class_pairs": pairs,
                "target_top_class_indices": target_top,
                "predicted_top_class_indices": predicted_top,
                "top_class_agreement_tie_aware": bool(set(target_top) & set(predicted_top)),
                "chosen_transport_index": chosen_index,
                "chosen_action_id": action_ids[chosen_index],
                "chosen_target": chosen_target,
                "oracle_target": oracle_target,
                "chosen_regret": oracle_target - chosen_target,
                "recorded_fallback_transport_index": fallback_index,
                "recorded_fallback_action_id": fallback_action_id,
                "recorded_fallback_target": fallback_target,
                "recorded_fallback_regret": oracle_target - fallback_target,
                "chosen_minus_fallback": chosen_target - fallback_target,
                "class_targets": view["targets"],
                "class_scores": representative_scores,
                "equivalence_class_keys": view["keys"],
                "inverse_transport_mapping": view["members"],
            }
        )
    if not groups:
        raise Scale64Error("evaluation produced no groups")

    def aggregate(items: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "groups": len(items),
            "class_pairwise_concordance": (
                sum(item["class_pairwise_concordance"] * item["comparable_class_pairs"] for item in items)
                / sum(item["comparable_class_pairs"] for item in items)
                if sum(item["comparable_class_pairs"] for item in items)
                else 1.0
            ),
            "top_class_agreement_rate": sum(item["top_class_agreement_tie_aware"] for item in items) / len(items),
            "mean_chosen_target": sum(item["chosen_target"] for item in items) / len(items),
            "mean_oracle_target": sum(item["oracle_target"] for item in items) / len(items),
            "mean_chosen_regret": sum(item["chosen_regret"] for item in items) / len(items),
            "mean_recorded_fallback_target": sum(item["recorded_fallback_target"] for item in items) / len(items),
            "mean_recorded_fallback_regret": sum(item["recorded_fallback_regret"] for item in items) / len(items),
            "mean_chosen_minus_fallback": sum(item["chosen_minus_fallback"] for item in items) / len(items),
        }

    family_results: dict[str, Any] = {}
    for family in FAMILIES:
        items = [item for item in groups if item["family"] == family]
        if not items:
            raise Scale64Error(f"test split lacks family: {family}")
        family_results[family] = aggregate(items)
    slot_results = {str(slot): aggregate([item for item in groups if item["slot"] == slot]) for slot in (0, 1)}
    window_results = {
        window: aggregate([item for item in groups if item["window"] == window])
        for window in ("EARLY", "MID")
    }
    combination_results = {
        f"{family}|{window}|{slot}": aggregate(
            [item for item in groups if item["family"] == family and item["window"] == window and item["slot"] == slot]
        )
        for family in FAMILIES
        for window in ("EARLY", "MID")
        for slot in (0, 1)
        if any(item["family"] == family and item["window"] == window and item["slot"] == slot for item in groups)
    }
    sorted_deltas = sorted(item["chosen_minus_fallback"] for item in groups)
    rng = random.Random(BOOTSTRAP_SEED)
    bootstrap_means = sorted(
        sum(rng.choice(sorted_deltas) for _ in sorted_deltas) / len(sorted_deltas)
        for _ in range(2000)
    )
    lower_index = int(0.025 * (len(bootstrap_means) - 1))
    upper_index = int(0.975 * (len(bootstrap_means) - 1))
    bins = []
    for bin_index in range(5):
        values = [target for score, target in calibration_values if int(min(4, max(0, math.floor((score + 1.0) * 2.5)))) == bin_index]
        predicted = [score for score, target in calibration_values if int(min(4, max(0, math.floor((score + 1.0) * 2.5)))) == bin_index]
        bins.append(
            {
                "bin": bin_index,
                "count": len(values),
                "mean_predicted_clipped_score": sum(predicted) / len(predicted) if predicted else None,
                "mean_target": sum(values) / len(values) if values else None,
                "absolute_gap": abs(sum(predicted) / len(predicted) - sum(values) / len(values)) if values else None,
            }
        )
    return {
        "groups": groups,
        "state_count": len(groups),
        "class_pairwise_concordance": total_correct / total_pairs if total_pairs else 1.0,
        "comparable_class_pairs": total_pairs,
        "top_class_agreement_rate": sum(item["top_class_agreement_tie_aware"] for item in groups) / len(groups),
        "mean_chosen_target": sum(item["chosen_target"] for item in groups) / len(groups),
        "mean_oracle_target": sum(item["oracle_target"] for item in groups) / len(groups),
        "mean_chosen_regret": sum(item["chosen_regret"] for item in groups) / len(groups),
        "mean_recorded_fallback_target": sum(item["recorded_fallback_target"] for item in groups) / len(groups),
        "mean_recorded_fallback_regret": sum(item["recorded_fallback_regret"] for item in groups) / len(groups),
        "mean_chosen_minus_fallback": sum(item["chosen_minus_fallback"] for item in groups) / len(groups),
        "state_bootstrap_delta_ci95": [bootstrap_means[lower_index], bootstrap_means[upper_index]],
        "calibration": bins,
        "by_family": family_results,
        "by_slot": slot_results,
        "by_window": window_results,
        "by_family_window_slot": combination_results,
    }


def _loss_report(scores: torch.Tensor, batch: RankerBatch) -> dict[str, float]:
    huber = grouped_ranker_loss(
        scores, batch.target, batch.target_mask, batch.group_offsets,
        target_weight=batch.target_weight, pairwise_weight=0.0,
        temperature=TEMPERATURE, semantic_fingerprints=batch.semantic_fingerprints,
        semantic_equivalence_keys=batch.semantic_equivalence_keys,
    )
    total = grouped_ranker_loss(
        scores, batch.target, batch.target_mask, batch.group_offsets,
        target_weight=batch.target_weight, pairwise_weight=PAIRWISE_WEIGHT,
        temperature=TEMPERATURE, semantic_fingerprints=batch.semantic_fingerprints,
        semantic_equivalence_keys=batch.semantic_equivalence_keys,
    )
    values = {"huber": float(huber), "bradley_terry_weighted_contribution": float(total - huber), "total": float(total)}
    if not all(math.isfinite(value) for value in values.values()):
        raise Scale64Error("nonfinite loss report")
    return values


def _train_one_seed(
    seed: int,
    train_batch: RankerBatch,
    tune_batch: RankerBatch,
    tune_records: list[GroupRecord],
) -> dict[str, Any]:
    random.seed(seed)
    torch.manual_seed(seed)
    ranker = OutcomeRankerV1()
    if sum(parameter.numel() for parameter in ranker.parameters()) != 27_841:
        raise Scale64Error("head parameter count differs from 27,841")
    optimizer = torch.optim.Adam(ranker.parameters(), lr=LEARNING_RATE)
    best_state: dict[str, torch.Tensor] | None = None
    best_key: tuple[float, float, int] | None = None
    best_tune: dict[str, Any] | None = None
    best_loss: dict[str, float] | None = None
    best_step = 0
    no_improvement = 0
    started = time.perf_counter()
    for step in range(MAX_STEPS + 1):
        with torch.inference_mode():
            tune_scores = ranker(tune_batch.public_hidden, tune_batch.option_embeddings, tune_batch.option_offsets)
        tune_metrics = _evaluate(tune_scores, tune_batch, tune_records)
        tune_loss = _loss_report(tune_scores, tune_batch)
        candidate_key = (-tune_metrics["class_pairwise_concordance"], tune_loss["total"], step)
        if best_key is None or candidate_key < best_key:
            best_key = candidate_key
            best_state = {key: value.detach().clone() for key, value in ranker.state_dict().items()}
            best_tune = tune_metrics
            best_loss = tune_loss
            best_step = step
            no_improvement = 0
        else:
            no_improvement += 1
        if step == MAX_STEPS or no_improvement >= PATIENCE:
            break
        optimizer.zero_grad(set_to_none=True)
        scores = ranker(train_batch.public_hidden, train_batch.option_embeddings, train_batch.option_offsets)
        loss = grouped_ranker_loss(
            scores, train_batch.target, train_batch.target_mask, train_batch.group_offsets,
            target_weight=train_batch.target_weight, pairwise_weight=PAIRWISE_WEIGHT,
            temperature=TEMPERATURE, semantic_fingerprints=train_batch.semantic_fingerprints,
            semantic_equivalence_keys=train_batch.semantic_equivalence_keys,
        )
        if not torch.isfinite(loss).all().item():
            raise Scale64Error(f"seed {seed} produced nonfinite training loss")
        loss.backward()
        for parameter in ranker.parameters():
            if parameter.grad is None or not torch.isfinite(parameter.grad).all().item():
                raise Scale64Error(f"seed {seed} produced a missing/nonfinite head gradient")
        optimizer.step()
        if any(not torch.isfinite(value).all().item() for value in ranker.state_dict().values()):
            raise Scale64Error(f"seed {seed} produced nonfinite head weights")
    if best_state is None or best_tune is None or best_loss is None:
        raise Scale64Error("seed never produced a tune checkpoint")
    ranker.load_state_dict(best_state, strict=True)
    return {
        "seed": seed,
        "steps_run": step,
        "best_step": best_step,
        "best_tune_concordance": best_tune["class_pairwise_concordance"],
        "best_tune_loss": best_loss,
        "best_state": best_state,
        "tune_metrics": best_tune,
        "seconds": time.perf_counter() - started,
        "ranker": ranker,
    }


def _bc_action_logits(trunk: torch.nn.Module, records: list[GroupRecord]) -> torch.Tensor:
    rows: list[torch.Tensor] = []
    for record in records:
        decision = _projected_decision(record.raw_group["public_tensor"]["projected_decision"])
        hidden = _hidden_from_history(record.raw_group["public_tensor"])
        projected = collate_projected((decision,), device="cpu")
        with torch.inference_mode():
            output = trunk(projected, hidden)
        _finite_tensor(output.option_logits, "frozen BC action logits")
        if output.option_logits.shape != (record.action_count,):
            raise Scale64Error("frozen BC logits do not cover the complete legal option set")
        rows.append(output.option_logits)
    return torch.cat(rows)


def _cpu_p95_ms(ranker: OutcomeRankerV1, batch: RankerBatch) -> float:
    for _ in range(10):
        with torch.inference_mode():
            ranker(batch.public_hidden, batch.option_embeddings, batch.option_offsets)
    samples = []
    for _ in range(100):
        started = time.perf_counter()
        with torch.inference_mode():
            ranker(batch.public_hidden, batch.option_embeddings, batch.option_offsets)
        samples.append((time.perf_counter() - started) * 1000.0)
    samples.sort()
    return samples[94]


def run() -> dict[str, Any]:
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    if CHECKPOINT_PATH.exists():
        CHECKPOINT_PATH.unlink()
    trunk, binding = load_gate1_trunk()
    trunk_state_before = state_dict_sha256(trunk.state_dict())
    if trunk_state_before != BC_TRUNK_STATE_SHA256 or any(parameter.requires_grad for parameter in trunk.parameters()):
        raise Scale64Error("loaded trunk is not the exact frozen BC state")
    records, provenance = _load_records(trunk)
    split_by_id, split_summary = _validate_split(records)
    tune_records = _ordered_records(records, split_by_id, "tune")
    test_records = _ordered_records(records, split_by_id, "test")
    train_batch = _split_batch(records, split_by_id, "train")
    tune_batch = _split_batch(records, split_by_id, "tune")
    test_batch = _split_batch(records, split_by_id, "test")
    if set(train_batch.state_group_ids) & set(tune_batch.state_group_ids) or set(train_batch.state_group_ids) & set(test_batch.state_group_ids) or set(tune_batch.state_group_ids) & set(test_batch.state_group_ids):
        raise Scale64Error("state group leakage across split batches")
    if set(test_batch.state_group_ids) != {record.state_group_id for record in test_records}:
        raise Scale64Error("test transport order does not match sealed test groups")
    # The optimizer receives only this batch; no test tensor is passed below.
    optimizer_group_ids = set(train_batch.state_group_ids)
    if optimizer_group_ids & set(test_batch.state_group_ids):
        raise Scale64Error("test group entered the optimizer batch")

    seed_results = []
    for seed in SEEDS:
        result = _train_one_seed(seed, train_batch, tune_batch, tune_records)
        seed_results.append(result)
    selected = min(seed_results, key=lambda result: (-result["best_tune_concordance"], result["best_tune_loss"]["total"], result["seed"]))
    ranker = selected["ranker"]
    if not isinstance(ranker, OutcomeRankerV1):
        raise Scale64Error("selected seed did not return a ranker")
    checkpoint_payload = checkpoint_bytes(ranker, binding)
    restored = load_checkpoint(checkpoint_payload)
    with torch.inference_mode():
        selected_tune_scores = ranker(tune_batch.public_hidden, tune_batch.option_embeddings, tune_batch.option_offsets)
        restored_tune_scores = restored(tune_batch.public_hidden, tune_batch.option_embeddings, tune_batch.option_offsets)
    if not torch.equal(selected_tune_scores, restored_tune_scores):
        raise Scale64Error("strict checkpoint reload changed selected tune outputs")
    if any(not torch.isfinite(value).all().item() for value in ranker.state_dict().values()):
        raise Scale64Error("selected head weights are nonfinite")
    trunk_state_after = state_dict_sha256(trunk.state_dict())
    if trunk_state_after != trunk_state_before or any(parameter.grad is not None for parameter in trunk.parameters()):
        raise Scale64Error("frozen trunk state/gradients changed")
    CHECKPOINT_PATH.write_bytes(checkpoint_payload)
    checkpoint_hash = _sha256_file(CHECKPOINT_PATH)

    # This is the sole test evaluation phase. Selection, strict reload, and
    # checkpoint sealing all occur before any test score or target is read.
    test_evaluation_calls = 0
    test_evaluation_calls += 1
    if test_evaluation_calls != 1:
        raise Scale64Error("test evaluation was attempted more than once")
    with torch.inference_mode():
        selected_test_scores = restored(test_batch.public_hidden, test_batch.option_embeddings, test_batch.option_offsets)
    _finite_tensor(selected_test_scores, "selected test scores")
    torch.manual_seed(UNTRAINED_SEED)
    untrained = OutcomeRankerV1()
    with torch.inference_mode():
        untrained_test_scores = untrained(test_batch.public_hidden, test_batch.option_embeddings, test_batch.option_offsets)
    _finite_tensor(untrained_test_scores, "untrained-head test scores")
    bc_test_scores = _bc_action_logits(trunk, test_records)
    if bc_test_scores.shape != selected_test_scores.shape:
        raise Scale64Error("baseline test score shape differs from selected ranker")
    test_record_order = list(test_batch.state_group_ids)
    if test_record_order != [record.state_group_id for record in test_records]:
        raise Scale64Error("test record/batch order changed before baseline evaluation")
    baseline_metrics = {
        "selected_frozen_head": _evaluate(selected_test_scores, test_batch, test_records),
        "untrained_head": _evaluate(untrained_test_scores, test_batch, test_records),
        "frozen_bc_action_logits": _evaluate(bc_test_scores, test_batch, test_records),
    }
    selected_test = baseline_metrics["selected_frozen_head"]
    point_delta = selected_test["mean_chosen_minus_fallback"]
    lower_delta = selected_test["state_bootstrap_delta_ci95"][0]
    family_failures = {
        family: values["mean_chosen_minus_fallback"]
        for family, values in selected_test["by_family"].items()
        if values["mean_chosen_minus_fallback"] < 0.0
    }
    promotion_killed = (
        selected_test["class_pairwise_concordance"] < 0.60
        or point_delta < 0.05
        or lower_delta <= 0.02
        or bool(family_failures)
    )
    status = "MECHANICS_PASS_SCALE64_INCONCLUSIVE_PROMOTION_KILLED" if promotion_killed else "MECHANICS_PASS_SCALE64_INCONCLUSIVE"
    metrics = {
        "status": status,
        "purpose": "first state-grouped Scale64 frozen-BC-head experiment; no competence claim",
        "dataset_run_root": str(RUN_ROOT),
        "provenance": provenance,
        "dataset_hashes": DATASET_HASHES,
        "split_rule": "sort public_state_sha within family x window x slot; first row held out; test when family ordinal + window ordinal + slot is odd; all remaining rows train",
        "split_summary": split_summary,
        "split_groups": {split: sorted(state_id for state_id, value in split_by_id.items() if value == split) for split in ("train", "tune", "test")},
        "leakage_checks": {
            "root_state_ids_disjoint": True,
            "semantic_class_keys_disjoint": True,
            "particle_keys_disjoint": True,
            "source_episode_ids_disjoint": True,
            "complete_legal_groups_only": True,
            "optimizer_group_ids": sorted(optimizer_group_ids),
            "test_group_ids_entered_optimizer": False,
        },
        "config": {
            "seeds": list(SEEDS),
            "learning_rate": LEARNING_RATE,
            "pairwise_weight": PAIRWISE_WEIGHT,
            "temperature": TEMPERATURE,
            "max_steps": MAX_STEPS,
            "patience": PATIENCE,
            "threads": 1,
            "head_only": True,
            "test_evaluation_calls": test_evaluation_calls,
        },
        "trunk_binding": {
            "mode": binding.mode,
            "g2_package_sha256": G2_PACKAGE_SHA256,
            "g2_model_schema_sha256": G2_MODEL_SCHEMA_SHA256,
            "bc_trunk_checkpoint_sha256": BC_TRUNK_CHECKPOINT_SHA256,
            "bc_trunk_state_sha256": BC_TRUNK_STATE_SHA256,
            "state_before": trunk_state_before,
            "state_after": trunk_state_after,
            "trunk_gradients_absent": True,
        },
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
        "selected_seed": selected["seed"],
        "selected_step": selected["best_step"],
        "selected_tune": {
            "class_pairwise_concordance": selected["best_tune_concordance"],
            "loss": selected["best_tune_loss"],
        },
        "checkpoint": {
            "path": str(CHECKPOINT_PATH),
            "bytes": len(checkpoint_payload),
            "sha256": checkpoint_hash,
            "strict_reload_output_equal": True,
            "mechanical_checks_passed": True,
        },
        "test_metrics": baseline_metrics,
        "promotion_gate": {
            "test_concordance_threshold": 0.60,
            "point_delta_threshold": 0.05,
            "lower_95_delta_threshold": 0.02,
            "test_class_pairwise_concordance": selected_test["class_pairwise_concordance"],
            "point_delta": point_delta,
            "lower_95_delta": lower_delta,
            "family_catastrophic_failures": family_failures,
            "killed": promotion_killed,
        },
        "cpu_p95_ms": _cpu_p95_ms(restored, test_batch),
    }
    if not all(math.isfinite(float(value)) for value in (selected_test["class_pairwise_concordance"], point_delta, lower_delta)):
        raise Scale64Error("final test metrics are nonfinite")
    METRICS_PATH.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return metrics


if __name__ == "__main__":
    try:
        print(json.dumps(run(), indent=2, sort_keys=True))
    except (OutcomeRankerError, Scale64Error) as error:
        raise SystemExit(f"KILL: {error}") from error
