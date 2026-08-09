"""Mechanics-only Gate-1 head training proof over the retained full run."""

from __future__ import annotations

import hashlib
import json
import random
import sys
import time
from pathlib import Path
from typing import Any, Iterable

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

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
)
from ptcg_rl.g2.checkpoint import state_dict_sha256  # noqa: E402


RUN_ROOT = (
    Path(__file__).resolve().parents[3]
    / ".chatgpt/tmp/counterfactual-q/runs/"
    "full-counterfactual-q-20260809T174041.651492Z-513a20492a53"
)
DATASET_ROOT = RUN_ROOT / "datasets"
CHECKPOINT_PATH = Path(__file__).with_name("gate1_head_only_full_run.pt")
METRICS_PATH = Path(__file__).with_name("gate1_head_only_full_run.metrics.json")
EXPECTED_DATASETS = {
    "counterfactual-action-dataset-dragapult-ex.json",
    "counterfactual-action-dataset-iono.json",
    "counterfactual-action-dataset-mega-lucario-ex.json",
}
SEED = 20260809
LEARNING_RATE = 0.01
PAIRWISE_WEIGHT = 0.25
TEMPERATURE = 0.25
MAX_STEPS = 1000


class TrainingProofError(RuntimeError):
    """Raised when the bounded mechanics proof cannot overfit safely."""


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _concat_batches(batches: Iterable[RankerBatch]) -> RankerBatch:
    items = tuple(batches)
    if not items:
        raise TrainingProofError("full run produced no loader batches")
    option_offset_values = [0]
    group_offset_values = [0]
    for batch in items:
        if batch.group_offsets.numel() != len(batch.state_group_ids) + 1:
            raise TrainingProofError("group boundary count does not match state groups")
        option_offset_values.extend((batch.option_offsets[1:] + option_offset_values[-1]).tolist())
        group_offset_values.extend((batch.group_offsets[1:] + group_offset_values[-1]).tolist())
    state_group_ids = tuple(group_id for batch in items for group_id in batch.state_group_ids)
    if len(state_group_ids) != len(set(state_group_ids)):
        raise TrainingProofError("state group is split or duplicated across dataset files")
    return RankerBatch(
        public_hidden=torch.cat([batch.public_hidden for batch in items], dim=0),
        option_embeddings=torch.cat([batch.option_embeddings for batch in items], dim=0),
        option_available=torch.cat([batch.option_available for batch in items], dim=0),
        option_offsets=torch.tensor(option_offset_values, dtype=torch.long),
        target=torch.cat([batch.target for batch in items], dim=0),
        target_stderr=torch.cat([batch.target_stderr for batch in items], dim=0),
        target_weight=torch.cat([batch.target_weight for batch in items], dim=0),
        target_mask=torch.cat([batch.target_mask for batch in items], dim=0),
        group_offsets=torch.tensor(group_offset_values, dtype=torch.long),
        state_group_ids=state_group_ids,
        action_ids=tuple(action_id for batch in items for action_id in batch.action_ids),
        semantic_fingerprints=tuple(
            fingerprint for batch in items for fingerprint in batch.semantic_fingerprints
        ),
        semantic_equivalence_keys=tuple(
            key for batch in items for key in batch.semantic_equivalence_keys
        ),
        equivalence_class_metadata=tuple(
            group for batch in items for group in batch.equivalence_class_metadata
        ),
    )


def _assert_batch_contract(batch: RankerBatch) -> None:
    if len(batch.state_group_ids) != 6:
        raise TrainingProofError(f"expected 6 state groups, got {len(batch.state_group_ids)}")
    if batch.option_embeddings.shape != (34, 128):
        raise TrainingProofError(f"expected 34x128 option tensor, got {tuple(batch.option_embeddings.shape)}")
    if batch.public_hidden.shape != (6, 160):
        raise TrainingProofError(f"expected 6x160 hidden tensor, got {tuple(batch.public_hidden.shape)}")
    if batch.target.shape != (34,) or batch.target_mask.shape != (34,):
        raise TrainingProofError("target/action tensor shape is not the six-group contract")
    if len(batch.semantic_equivalence_keys) != 34:
        raise TrainingProofError("semantic equivalence sidecar does not cover all actions")
    if len(batch.equivalence_class_metadata) != 6:
        raise TrainingProofError("equivalence metadata does not cover all state groups")
    if sum(len(group) for group in batch.equivalence_class_metadata) != 29:
        raise TrainingProofError("six-group run does not have exactly 29 factual equivalence classes")
    if batch.group_offsets.tolist() != [0, 10, 13, 17, 23, 28, 34]:
        raise TrainingProofError("six state-group boundaries were not preserved")
    if not bool(batch.option_available.all()) or not bool(batch.target_mask.all()):
        raise TrainingProofError("full-run batch contains an unavailable or masked action")
    if not torch.isfinite(batch.public_hidden).all() or not torch.isfinite(batch.option_embeddings).all():
        raise TrainingProofError("loader emitted nonfinite public or option tensors")
    if not torch.isfinite(batch.target).all() or not torch.isfinite(batch.target_weight).all():
        raise TrainingProofError("loader emitted nonfinite targets or weights")


def _representation_conflicts(batch: RankerBatch) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    for group_index, (start, end) in enumerate(
        zip(batch.group_offsets[:-1].tolist(), batch.group_offsets[1:].tolist())
    ):
        for left in range(start, end):
            for right in range(left + 1, end):
                if not torch.equal(batch.option_embeddings[left], batch.option_embeddings[right]):
                    continue
                left_target = float(batch.target[left])
                right_target = float(batch.target[right])
                if left_target == right_target:
                    continue
                conflicts.append(
                    {
                        "state_group_id": batch.state_group_ids[group_index],
                        "local_indices": [left - start, right - start],
                        "targets": [left_target, right_target],
                        "semantic_fingerprints": [
                            batch.semantic_fingerprints[left],
                            batch.semantic_fingerprints[right],
                        ],
                    }
                )
    return conflicts


def _equivalence_report(batch: RankerBatch) -> dict[str, Any]:
    classes: list[dict[str, Any]] = []
    for group_index, group_metadata in enumerate(batch.equivalence_class_metadata):
        state_id = batch.state_group_ids[group_index]
        for metadata in group_metadata:
            record = dict(metadata)
            record["state_group_id"] = state_id
            classes.append(record)
    if sum(int(item["branch_count"]) for item in classes) != 272:
        raise TrainingProofError("equivalence metadata does not preserve all 272 raw branches")
    return {
        "class_count": len(classes),
        "classes": classes,
        "branch_count": sum(int(item["branch_count"]) for item in classes),
        "particle_count": sum(int(item["particle_count"]) for item in classes),
        "disagreement_class_count": sum(bool(item["disagreement"]) for item in classes),
    }


def _pairwise_concordance(
    scores: torch.Tensor,
    target: torch.Tensor,
    equivalence_keys: tuple[str, ...] | list[str] | None = None,
) -> tuple[float, int, float]:
    correct = 0.0
    comparable = 0
    if equivalence_keys is None:
        representatives = list(range(scores.numel()))
    else:
        members: dict[str, list[int]] = {}
        for position, key in enumerate(equivalence_keys):
            members.setdefault(key, []).append(position)
        representatives = [min(members[key]) for key in sorted(members)]
    for left_position, left in enumerate(representatives):
        for right in representatives[left_position + 1 :]:
            target_delta = float(target[left] - target[right])
            if target_delta == 0.0:
                continue
            comparable += 1
            score_delta = float(scores[left] - scores[right])
            if score_delta * target_delta > 0:
                correct += 1.0
            elif score_delta == 0.0:
                correct += 0.5
    return (correct / comparable if comparable else 1.0), comparable, correct


def _top_indices(values: torch.Tensor) -> list[int]:
    maximum = float(values.max())
    return [index for index, value in enumerate(values.tolist()) if abs(value - maximum) <= 1e-7]


def _equivalence_transport_map(keys: list[str]) -> tuple[list[str], list[int], list[list[int]]]:
    members: dict[str, list[int]] = {}
    for position, key in enumerate(keys):
        members.setdefault(key, []).append(position)
    ordered_keys = sorted(members)
    representatives = [min(members[key]) for key in ordered_keys]
    inverse_transport = [sorted(members[key]) for key in ordered_keys]
    return ordered_keys, representatives, inverse_transport


def _ranking_metrics(scores: torch.Tensor, batch: RankerBatch) -> dict[str, Any]:
    scores = scores.detach().cpu()
    target = batch.target.detach().cpu()
    group_metrics: list[dict[str, Any]] = []
    total_comparable = 0
    total_correct = 0.0
    for group_index, (start, end) in enumerate(
        zip(batch.group_offsets[:-1].tolist(), batch.group_offsets[1:].tolist())
    ):
        local_scores = scores[start:end]
        local_target = target[start:end]
        local_equivalence_keys = list(batch.semantic_equivalence_keys[start:end])
        concordance, comparable, correct = _pairwise_concordance(
            local_scores, local_target, local_equivalence_keys
        )
        equivalence_keys, representatives, inverse_transport = _equivalence_transport_map(
            local_equivalence_keys
        )
        representative_targets = local_target[representatives]
        representative_scores = local_scores[representatives]
        target_top = _top_indices(representative_targets)
        predicted_top = _top_indices(representative_scores)
        target_order = sorted(
            range(len(representatives)),
            key=lambda index: (-float(representative_targets[index]), index),
        )
        predicted_order = sorted(
            range(len(representatives)),
            key=lambda index: (-float(representative_scores[index]), index),
        )
        physical_target_top = _top_indices(local_target)
        physical_predicted_top = _top_indices(local_scores)
        physical_target_order = sorted(
            range(end - start), key=lambda index: (-float(local_target[index]), index)
        )
        physical_predicted_order = sorted(
            range(end - start), key=lambda index: (-float(local_scores[index]), index)
        )
        group_metrics.append(
            {
                "state_group_id": batch.state_group_ids[group_index],
                "start": start,
                "end": end,
                "concordance": concordance,
                "comparable_pairs": comparable,
                "target_top_indices": target_top,
                "predicted_top_indices": predicted_top,
                "top_action_agreement_tie_aware": bool(set(target_top) & set(predicted_top)),
                "target_order": target_order,
                "predicted_order": predicted_order,
                "equivalence_class_keys": equivalence_keys,
                "equivalence_representative_indices": representatives,
                "inverse_transport_mapping": [
                    {
                        "class_index": class_index,
                        "semantic_equivalence_key": key,
                        "representative_transport_index": start + representatives[class_index],
                        "transport_indices": [start + index for index in members],
                    }
                    for class_index, (key, members) in enumerate(
                        zip(equivalence_keys, inverse_transport)
                    )
                ],
                "representative_target": [float(value) for value in representative_targets.tolist()],
                "representative_scores": [float(value) for value in representative_scores.tolist()],
                "physical_target_top_indices": physical_target_top,
                "physical_predicted_top_indices": physical_predicted_top,
                "physical_target_order": physical_target_order,
                "physical_predicted_order": physical_predicted_order,
                "physical_selected_index_tie_mapping": {
                    "target": {
                        "top_indices": physical_target_top,
                        "selected_index": min(physical_target_top),
                    },
                    "predicted": {
                        "top_indices": physical_predicted_top,
                        "selected_index": min(physical_predicted_top),
                    },
                },
                "target": [float(value) for value in local_target.tolist()],
                "scores": [float(value) for value in local_scores.tolist()],
                "action_ids": list(batch.action_ids[start:end]),
                "semantic_fingerprints": list(batch.semantic_fingerprints[start:end]),
                "semantic_equivalence_keys": local_equivalence_keys,
                "equivalence_class_count": len(equivalence_keys),
            }
        )
        total_comparable += comparable
        total_correct += correct
    return {
        "all_pairwise_concordance": (
            total_correct / total_comparable if total_comparable else 1.0
        ),
        "distinguishable_pair_count": total_comparable,
        "group_concordance": group_metrics,
        "all_groups_at_least_0_95": all(
            item["concordance"] >= 0.95 for item in group_metrics
        ),
    }


def _loss_report(scores: torch.Tensor, batch: RankerBatch) -> dict[str, float]:
    huber = grouped_ranker_loss(
        scores,
        batch.target,
        batch.target_mask,
        batch.group_offsets,
        target_weight=batch.target_weight,
        pairwise_weight=0.0,
        temperature=TEMPERATURE,
        semantic_fingerprints=batch.semantic_fingerprints,
        semantic_equivalence_keys=batch.semantic_equivalence_keys,
    )
    total = grouped_ranker_loss(
        scores,
        batch.target,
        batch.target_mask,
        batch.group_offsets,
        target_weight=batch.target_weight,
        pairwise_weight=PAIRWISE_WEIGHT,
        temperature=TEMPERATURE,
        semantic_fingerprints=batch.semantic_fingerprints,
        semantic_equivalence_keys=batch.semantic_equivalence_keys,
    )
    bradley_terry_contribution = total - huber
    values = {
        "huber": float(huber.detach()),
        "bradley_terry_weighted_contribution": float(bradley_terry_contribution.detach()),
        "total": float(total.detach()),
    }
    if not all(torch.isfinite(torch.tensor(value)) for value in values.values()):
        raise TrainingProofError("loss report contains a nonfinite value")
    return values


def _cpu_p95_ms(ranker: OutcomeRankerV1, batch: RankerBatch) -> float:
    for _ in range(5):
        with torch.inference_mode():
            ranker(batch.public_hidden, batch.option_embeddings, batch.option_offsets)
    samples: list[float] = []
    for _ in range(50):
        started = time.perf_counter()
        with torch.inference_mode():
            ranker(batch.public_hidden, batch.option_embeddings, batch.option_offsets)
        samples.append((time.perf_counter() - started) * 1000.0)
    samples.sort()
    return samples[47]


def _load_full_run(trunk: torch.nn.Module) -> tuple[RankerBatch, list[dict[str, Any]]]:
    paths = sorted(DATASET_ROOT.glob("*.json"))
    if {path.name for path in paths} != EXPECTED_DATASETS:
        raise TrainingProofError("full-run dataset file set differs from the audited six-group run")
    batches: list[RankerBatch] = []
    metadata: list[dict[str, Any]] = []
    for path in paths:
        dataset = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(dataset, dict):
            raise TrainingProofError(f"dataset root is not an object: {path}")
        raw_branch_count = sum(
            len(replicate["actions"])
            for group in dataset["state_groups"]
            for replicate in group["replicates"]
        )
        batch = load_counterfactual_dataset(path, trunk)
        batches.append(batch)
        metadata.append(
            {
                "path": str(path),
                "sha256": _sha256_file(path),
                "state_group_ids": list(batch.state_group_ids),
                "option_count": int(batch.option_embeddings.shape[0]),
                "raw_branch_count": raw_branch_count,
                "run_hashes": {
                    "g2_package_sha256": dataset["run"]["g2_package_sha256"],
                    "model_schema_sha256": dataset["run"]["model_schema_sha256"],
                    "bc_trunk_checkpoint_sha256": dataset["run"]["bc_trunk_checkpoint_sha256"],
                    "bc_trunk_state_sha256": dataset["run"]["bc_trunk_state_sha256"],
                    "trunk_mode": dataset["run"]["trunk_mode"],
                },
            }
        )
    combined = _concat_batches(batches)
    _assert_batch_contract(combined)
    if sum(item["raw_branch_count"] for item in metadata) != 272:
        raise TrainingProofError("full-run raw branch count is not exactly 272")
    if sum(item["option_count"] for item in metadata) != 34:
        raise TrainingProofError("full-run action count is not exactly 34")
    return combined, metadata


def run() -> dict[str, Any]:
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    random.seed(SEED)
    torch.manual_seed(SEED)
    trunk, binding = load_gate1_trunk()
    if any(parameter.requires_grad for parameter in trunk.parameters()):
        raise TrainingProofError("frozen BC trunk unexpectedly has trainable parameters")
    if any(parameter.grad is not None for parameter in trunk.parameters()):
        raise TrainingProofError("frozen BC trunk already carries gradients")
    trunk_state_before = state_dict_sha256(trunk.state_dict())
    if trunk_state_before != BC_TRUNK_STATE_SHA256:
        raise TrainingProofError("loaded trunk state is not the pinned BC state")
    batch, dataset_metadata = _load_full_run(trunk)
    equivalence_report = _equivalence_report(batch)
    pre_scores = OutcomeRankerV1()(batch.public_hidden, batch.option_embeddings, batch.option_offsets)
    pre_metrics = _ranking_metrics(pre_scores, batch)
    pre_loss = _loss_report(pre_scores, batch)

    torch.manual_seed(SEED)
    ranker = OutcomeRankerV1()
    if sum(parameter.numel() for parameter in ranker.parameters()) != 27_841:
        raise TrainingProofError("head parameter count differs from 27,841")
    optimizer = torch.optim.Adam(ranker.parameters(), lr=LEARNING_RATE)
    step = 0
    final_loss: dict[str, float] | None = None
    final_metrics: dict[str, Any] | None = None
    training_started = time.perf_counter()
    for step in range(1, MAX_STEPS + 1):
        optimizer.zero_grad(set_to_none=True)
        scores = ranker(batch.public_hidden, batch.option_embeddings, batch.option_offsets)
        loss = grouped_ranker_loss(
            scores,
            batch.target,
            batch.target_mask,
            batch.group_offsets,
            target_weight=batch.target_weight,
            pairwise_weight=PAIRWISE_WEIGHT,
            temperature=TEMPERATURE,
            semantic_fingerprints=batch.semantic_fingerprints,
            semantic_equivalence_keys=batch.semantic_equivalence_keys,
        )
        if not torch.isfinite(loss).item():
            raise TrainingProofError(f"nonfinite total loss at step {step}")
        loss.backward()
        if any(parameter.grad is None or not torch.isfinite(parameter.grad).all().item() for parameter in ranker.parameters()):
            raise TrainingProofError(f"nonfinite/missing head gradient at step {step}")
        optimizer.step()
        with torch.inference_mode():
            scores = ranker(batch.public_hidden, batch.option_embeddings, batch.option_offsets)
        if not torch.isfinite(scores).all().item():
            raise TrainingProofError(f"nonfinite head score at step {step}")
        final_metrics = _ranking_metrics(scores, batch)
        if final_metrics["all_groups_at_least_0_95"]:
            break
    if final_metrics is None or not final_metrics["all_groups_at_least_0_95"]:
        with torch.inference_mode():
            failed_scores = ranker(batch.public_hidden, batch.option_embeddings, batch.option_offsets)
        failed_metrics = _ranking_metrics(failed_scores, batch)
        failed_cpu_p95_ms = _cpu_p95_ms(ranker, batch)
        failure_record = {
            "status": "KILL_HEAD_CANNOT_OVERFIT_ALL_GROUPS",
            "reason": "identical option representations have conflicting terminal targets",
            "seed": SEED,
            "config": {
                "learning_rate": LEARNING_RATE,
                "pairwise_weight": PAIRWISE_WEIGHT,
                "temperature": TEMPERATURE,
                "max_steps": MAX_STEPS,
                "threads": 1,
                "head_only": True,
                "heldout_or_test_split": False,
            },
            "steps": step,
            "training_seconds": time.perf_counter() - training_started,
            "dataset_counts": {
                "state_groups": len(batch.state_group_ids),
                "actions": int(batch.option_embeddings.shape[0]),
                "raw_branches": sum(item["raw_branch_count"] for item in dataset_metadata),
                "group_offsets": batch.group_offsets.tolist(),
            },
            "equivalence": equivalence_report,
            "representation_conflicts": _representation_conflicts(batch),
            "dataset_metadata": dataset_metadata,
            "trunk_binding": {
                "mode": binding.mode,
                "g2_package_sha256": G2_PACKAGE_SHA256,
                "g2_model_schema_sha256": G2_MODEL_SCHEMA_SHA256,
                "bc_trunk_checkpoint_sha256": BC_TRUNK_CHECKPOINT_SHA256,
                "bc_trunk_state_sha256": BC_TRUNK_STATE_SHA256,
                "state_before": trunk_state_before,
                "state_after": state_dict_sha256(trunk.state_dict()),
                "trunk_gradients_absent": all(
                    parameter.grad is None for parameter in trunk.parameters()
                ),
            },
            "pre": {"loss": pre_loss, "ranking": pre_metrics},
            "post": {
                "loss": _loss_report(failed_scores, batch),
                "ranking": failed_metrics,
            },
            "head_parameters": sum(parameter.numel() for parameter in ranker.parameters()),
            "checkpoint": {"written": False, "bytes": 0, "sha256": None},
            "cpu_p95_ms": failed_cpu_p95_ms,
        }
        METRICS_PATH.write_text(
            json.dumps(failure_record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        raise TrainingProofError(
            "head did not reach 0.95 concordance for every group within 1000 steps; "
            f"representation_conflicts={json.dumps(failure_record['representation_conflicts'], sort_keys=True)}"
        )
    with torch.inference_mode():
        final_scores = ranker(batch.public_hidden, batch.option_embeddings, batch.option_offsets)
    final_loss = _loss_report(final_scores, batch)
    if any(parameter.grad is None or not torch.isfinite(parameter.grad).all().item() for parameter in ranker.parameters()):
        raise TrainingProofError("final head gradients are missing or nonfinite")
    trunk_state_after = state_dict_sha256(trunk.state_dict())
    if trunk_state_after != trunk_state_before or any(parameter.grad is not None for parameter in trunk.parameters()):
        raise TrainingProofError("trunk state or gradients changed during head-only training")

    checkpoint_payload = checkpoint_bytes(ranker, binding)
    CHECKPOINT_PATH.write_bytes(checkpoint_payload)
    checkpoint_hash = _sha256_file(CHECKPOINT_PATH)
    restored = load_checkpoint(checkpoint_payload)
    with torch.inference_mode():
        restored_scores = restored(batch.public_hidden, batch.option_embeddings, batch.option_offsets)
    if not torch.equal(final_scores, restored_scores):
        raise TrainingProofError("strict checkpoint reload changed head outputs")
    cpu_p95_ms = _cpu_p95_ms(ranker, batch)
    metrics = {
        "status": "PASS_MECHANICS_ONLY_HEAD_OVERFIT_NO_COMPETENCE_CLAIM",
        "purpose": "all six retained groups trained solely to prove loader/head/checkpoint plumbing",
        "seed": SEED,
        "config": {
            "learning_rate": LEARNING_RATE,
            "pairwise_weight": PAIRWISE_WEIGHT,
            "temperature": TEMPERATURE,
            "max_steps": MAX_STEPS,
            "threads": 1,
            "head_only": True,
            "heldout_or_test_split": False,
        },
        "dataset_run_root": str(RUN_ROOT),
        "dataset_metadata": dataset_metadata,
        "dataset_counts": {
            "state_groups": len(batch.state_group_ids),
            "actions": int(batch.option_embeddings.shape[0]),
            "raw_branches": sum(item["raw_branch_count"] for item in dataset_metadata),
            "group_offsets": batch.group_offsets.tolist(),
        },
        "equivalence": equivalence_report,
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
        "head": {
            "parameters": sum(parameter.numel() for parameter in ranker.parameters()),
            "finite": True,
            "steps": step,
            "training_seconds": time.perf_counter() - training_started,
        },
        "pre": {"loss": pre_loss, "ranking": pre_metrics},
        "post": {"loss": final_loss, "ranking": final_metrics},
        "checkpoint": {
            "path": str(CHECKPOINT_PATH),
            "bytes": len(checkpoint_payload),
            "sha256": checkpoint_hash,
            "strict_reload_output_equal": True,
        },
        "cpu_p95_ms": cpu_p95_ms,
    }
    METRICS_PATH.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return metrics


if __name__ == "__main__":
    try:
        print(json.dumps(run(), indent=2, sort_keys=True))
    except (OutcomeRankerError, TrainingProofError) as error:
        raise SystemExit(f"KILL: {error}") from error
