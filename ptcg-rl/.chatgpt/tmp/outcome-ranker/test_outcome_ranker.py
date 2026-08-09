"""Pytest-discoverable, no-native Gate-1 ranker contract proof."""

from __future__ import annotations

import copy
import io
import json
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path

import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from outcome_ranker import (
    BC_TRUNK_CHECKPOINT_SHA256,
    BC_TRUNK_STATE_SHA256,
    G2_MODEL_SCHEMA_SHA256,
    G2_PACKAGE_SHA256,
    OutcomeRankerError,
    OutcomeRankerV1,
    RankerBatch,
    checkpoint_bytes,
    choose_legal_option,
    deterministic_legal_fallback,
    grouped_ranker_loss,
    load_checkpoint,
    load_counterfactual_dataset,
    load_gate1_trunk,
    semantic_equivalence_key,
)
from train_gate1 import _ranking_metrics
from ptcg_rl.g1.models import stable_hash
from ptcg_rl.g2.network import collate_projected
from ptcg_rl.g2.checkpoint import load_checkpoint_package
from outcome_ranker import _projected_decision
from project_public_state import _action_records
from tests.g2.test_network import number_decision


def _semantic_option(option: object, fingerprint: str) -> dict[str, object]:
    return {
        "option_type": option.option_type,
        "source_kind": option.source_kind,
        "target_kind": option.target_kind,
        "choice_role": option.choice_role,
        "source_ref": option.source_ref,
        "target_ref": option.target_ref,
        "is_stop": False,
        "source_card_id": option.card_id if option.source_kind != "NONE" else None,
        "target_card_id": None,
        "attack_id": option.attack_id,
        "semantic_fingerprint": fingerprint,
    }


def _summary(rewards: list[int]) -> dict[str, object]:
    mean = sum(rewards) / len(rewards)
    stderr = 0.0 if len(rewards) == 1 else (
        sum((reward - mean) ** 2 for reward in rewards) / (len(rewards) * (len(rewards) - 1))
    ) ** 0.5
    return {
        "replicate_count": len(rewards),
        "wdl_counts": {
            "W": rewards.count(1),
            "D": rewards.count(0),
            "L": rewards.count(-1),
        },
        "mean_reward": mean,
        "reward_stderr": stderr,
        "ci95_low": max(-1.0, mean - 1.96 * stderr),
        "ci95_high": min(1.0, mean + 1.96 * stderr),
        "baseline_action_id": None,
        "advantage_vs_fallback": None,
    }


def _synthetic_dataset(trunk: torch.nn.Module) -> dict[str, object]:
    _, request, decision = number_decision(3)
    fingerprints = list(decision.transport.semantic_fingerprints)
    fingerprints[1] = fingerprints[0]
    transport = asdict(decision.transport)
    transport["semantic_fingerprints"] = fingerprints
    hidden = trunk.initial_hidden(1, "cpu")[0].tolist()
    prefix_digest = stable_hash({"fixture": "gate1", "history_steps": 0})
    options = [_semantic_option(option, fingerprints[index]) for index, option in enumerate(request.options)]
    public_tensor = {
        "schema_version": 1,
        "model_schema_sha256": G2_MODEL_SCHEMA_SHA256,
        "feature_source": "G2_PROJECTED_PUBLIC_ONLY",
        "projected_decision": {
            "schema_version": 1,
            "model_input": asdict(decision.model),
            "transport_sidecar": transport,
        },
        "history_tokens": [{
            "history_schema_version": 1,
            "history_source": "RECORDED_PUBLIC_GRU_HIDDEN",
            "history_steps": 0,
            "prefix_digest": prefix_digest,
            "model_schema_sha256": G2_MODEL_SCHEMA_SHA256,
            "public_hidden": {"dtype": "float32", "shape": [1, 160], "values": [hidden]},
        }],
        "public_only": True,
        "raw_observation_retained": False,
        "forbidden_actor_features_absent": True,
        "prefix_provenance": {
            "source": "ACTOR_OWNED_PUBLIC_PREFIX",
            "prefix_digest": prefix_digest,
            "history_schema_version": 1,
            "history_source": "RECORDED_PUBLIC_GRU_HIDDEN",
            "history_steps": 0,
            "initial_hidden_source": "PRODUCTION_INITIAL_HIDDEN_EPISODE_START",
            "model_schema_sha256": G2_MODEL_SCHEMA_SHA256,
            "full_public_prefix_retained": False,
        },
    }
    rewards_by_fingerprint = {
        fingerprints[0]: [1, 1, 1, 1],
        fingerprints[2]: [-1, -1, -1, -1],
    }
    replicates = []
    for replicate_id in range(4):
        actions = []
        for option_index, fingerprint in enumerate(fingerprints):
            action_id = stable_hash({"ordering": request.ordering, "semantic_path": [fingerprint]})
            reward = rewards_by_fingerprint[fingerprint][replicate_id]
            actions.append({
                "action_id": action_id,
                "semantic_path": [options[option_index]],
                "semantic_action_fingerprint": stable_hash([options[option_index]]),
                "transport_original_indices": [request.options[option_index].original_index],
                "terminal_engine_result": {
                    "winner_player": 0 if reward == 1 else 1 if reward == -1 else None,
                    "is_draw": reward == 0,
                },
                "reward_for_actor": reward,
                "completed": True,
                "continuation_steps": 1,
                "first_opponent_response": None,
                "fallback_used": False,
                "nonfinite": False,
                "error": None,
            })
        replicates.append({
            "replicate_id": replicate_id,
            "determinization_id": f"fixture-world-{replicate_id}",
            "determinization_seed": replicate_id,
            "engine_rng": "EXPLICIT_SEED",
            "world_independence": "INDEPENDENT",
            "actions": actions,
        })
    aggregate_ids = [
        stable_hash({"ordering": request.ordering, "semantic_path": [fingerprint]})
        for fingerprint in dict.fromkeys(fingerprints)
    ]
    aggregates = []
    for action_id, rewards in zip(aggregate_ids, rewards_by_fingerprint.values()):
        aggregate = _summary(rewards)
        aggregate["action_id"] = action_id
        aggregates.append(aggregate)
    return {
        "schema_version": 1,
        "run": {
            "run_id": "synthetic-gate1",
            "source_commit": "a" * 40,
            "engine_sha256": "b" * 64,
            "card_data_sha256": "c" * 64,
            "action_schema_sha256": "d" * 64,
            "observation_schema_sha256": "e" * 64,
            "model_schema_sha256": G2_MODEL_SCHEMA_SHA256,
            "self_deck_sha256": "f" * 64,
            "opponent_deck_sha256": "0" * 64,
            "continuation_policy_id": "synthetic-continuation",
            "continuation_policy_sha256": "1" * 64,
            "opponent_policy_id": "synthetic-opponent",
            "opponent_policy_sha256": "2" * 64,
            "determinization_contract": {
                "hidden_state_source": "LABEL_ONLY_NOT_PUBLIC_INPUT",
                "world_sampling": "INDEPENDENT_PER_REPLICATE",
                "engine_rng": "EXPLICIT_SEED",
                "per_replicate_identity": True,
            },
            "label_firewall": "COUNTERFACTUAL_NATIVE_ONLY_NOT_PPO_ROLLOUT",
            "g2_package_sha256": G2_PACKAGE_SHA256,
            "bc_trunk_checkpoint_sha256": BC_TRUNK_CHECKPOINT_SHA256,
            "bc_trunk_state_sha256": BC_TRUNK_STATE_SHA256,
            "trunk_mode": "FROZEN_BC_EPOCH4_HEAD_ONLY",
        },
        "state_groups": [{
            "state_group_id": "synthetic-state-0",
            "split_group_key": "synthetic-split-0",
            "source_episode_id": "synthetic-episode-0",
            "public_state_sha256": "3" * 64,
            "acting_player": 0,
            "root_player": 0,
            "request": {
                "request_id": request.request_id,
                "selection_seq": request.selection_seq,
                "selection_type": request.selection_type,
                "selection_context": request.selection_context,
                "min_count": 1,
                "max_count": 1,
                "ordering": request.ordering,
                "options": options,
            },
            "public_tensor": public_tensor,
            "legal_action_count": 3,
            "enumerated_action_count": 3,
            "action_enumeration_complete": True,
            "compound_coverage": "SINGLE_CHOICE",
            "stop_tested": False,
            "replicates": replicates,
            "action_aggregates": aggregates,
        }],
    }


def _concordance(scores: torch.Tensor, target: torch.Tensor, mask: torch.Tensor) -> float:
    valid = torch.nonzero(mask, as_tuple=False).flatten().tolist()
    comparable = 0
    correct = 0.0
    for left_position, left in enumerate(valid):
        for right in valid[left_position + 1 :]:
            delta = float(target[left] - target[right])
            if delta == 0:
                continue
            comparable += 1
            score_delta = float((scores[left] - scores[right]).detach())
            correct += float(score_delta * delta > 0) + 0.5 * float(score_delta == 0)
    return correct / comparable if comparable else 0.0


def _batch_tensor_ids(batch: object) -> set[int]:
    return {
        id(getattr(batch, name))
        for name in (
            "public_hidden",
            "option_embeddings",
            "option_available",
            "option_offsets",
            "target",
            "target_stderr",
            "target_weight",
            "target_mask",
            "group_offsets",
        )
    }


def run() -> dict[str, float | int | bool]:
    torch.set_num_threads(1)
    torch.manual_seed(17)
    trunk, binding = load_gate1_trunk()
    assert all(not parameter.requires_grad for parameter in trunk.parameters())
    dataset = _synthetic_dataset(trunk)
    dataset_path = Path(__file__).with_name("synthetic_gate1_fixture.json")
    dataset_path.write_text(json.dumps(dataset), encoding="utf-8")
    synthetic_batch = load_counterfactual_dataset(dataset_path, trunk)
    if not torch.equal(synthetic_batch.target[0:1], synthetic_batch.target[1:2]):
        raise AssertionError("duplicate semantic targets were not broadcast")

    real_dataset_path = (
        Path(__file__).resolve().parents[3]
        / ".chatgpt/tmp/counterfactual-q/runs/"
        "counterfactual-q-20260809T172507.610589Z-76d4dfd075e8/complete-root-dataset.json"
    )
    if not real_dataset_path.is_file():
        raise AssertionError(f"retained real complete-root dataset is missing: {real_dataset_path}")
    real_batch = load_counterfactual_dataset(real_dataset_path, trunk)
    real_tensor_ids = _batch_tensor_ids(real_batch)
    if any(getattr(real_batch, name).requires_grad for name in (
        "public_hidden",
        "option_embeddings",
        "option_available",
        "option_offsets",
        "target",
        "target_stderr",
        "target_weight",
        "target_mask",
        "group_offsets",
    )):
        raise AssertionError("real interchange tensors unexpectedly require gradients")
    if (
        len(real_batch.state_group_ids) != 1
        or real_batch.option_embeddings.shape != (9, 128)
        or real_batch.target.shape != (9,)
        or real_batch.target_mask.tolist() != [True] * 9
    ):
        raise AssertionError("real complete-root interchange shape/legality changed")

    synthetic_tensor_ids = _batch_tensor_ids(synthetic_batch)
    if real_tensor_ids & synthetic_tensor_ids:
        raise AssertionError("real interchange tensors aliased synthetic training tensors")

    base_trunk = load_checkpoint_package(
        Path(__file__).resolve().parents[3] / "private/g2/checkpoint-v1/g2-policy-checkpoint-v1.zip",
        device="cpu",
        expected_package_sha256=G2_PACKAGE_SHA256,
    ).model
    base_trunk.requires_grad_(False)
    with pytest.raises(OutcomeRankerError, match="state SHA"):
        load_counterfactual_dataset(dataset_path, base_trunk)
    random_trunk = copy.deepcopy(trunk)
    with torch.no_grad():
        next(random_trunk.parameters()).add_(0.001)
    with pytest.raises(OutcomeRankerError, match="state SHA"):
        load_counterfactual_dataset(dataset_path, random_trunk)
    unfrozen_trunk = copy.deepcopy(trunk)
    next(unfrozen_trunk.parameters()).requires_grad_(True)
    with pytest.raises(OutcomeRankerError, match="fully frozen"):
        load_counterfactual_dataset(dataset_path, unfrozen_trunk)

    determinization_tamper = copy.deepcopy(dataset)
    determinization_tamper["state_groups"][0]["replicates"][1]["determinization_id"] = (
        determinization_tamper["state_groups"][0]["replicates"][0]["determinization_id"]
    )
    determinization_path = Path("/tmp/outcome-ranker-gate1-determinization-tamper.json")
    determinization_path.write_text(json.dumps(determinization_tamper), encoding="utf-8")
    with pytest.raises(OutcomeRankerError, match="determinization_id"):
        load_counterfactual_dataset(determinization_path, trunk)

    # Real interchange is inference-only; the optimizer below sees synthetic tensors only.
    ranker = OutcomeRankerV1()
    with torch.no_grad():
        ranker.head[2].weight.zero_()
        ranker.head[2].bias.zero_()
    before = ranker(
        synthetic_batch.public_hidden,
        synthetic_batch.option_embeddings,
        synthetic_batch.option_offsets,
    )
    before_concordance = _concordance(before, synthetic_batch.target, synthetic_batch.target_mask)
    optimizer = torch.optim.Adam(ranker.parameters(), lr=0.01)
    optimizer_parameter_ids = {
        id(parameter)
        for parameter_group in optimizer.param_groups
        for parameter in parameter_group["params"]
    }
    if real_tensor_ids & optimizer_parameter_ids:
        raise AssertionError("real interchange tensor entered the synthetic optimizer")
    finite_gradients = True
    for _ in range(350):
        optimizer.zero_grad(set_to_none=True)
        if real_tensor_ids & _batch_tensor_ids(synthetic_batch):
            raise AssertionError("real interchange tensor entered synthetic training")
        scores = ranker(
            synthetic_batch.public_hidden,
            synthetic_batch.option_embeddings,
            synthetic_batch.option_offsets,
        )
        loss = grouped_ranker_loss(
            scores,
            synthetic_batch.target,
            synthetic_batch.target_mask,
            synthetic_batch.group_offsets,
            target_weight=synthetic_batch.target_weight,
            semantic_fingerprints=synthetic_batch.semantic_fingerprints,
            semantic_equivalence_keys=synthetic_batch.semantic_equivalence_keys,
        )
        if not torch.isfinite(loss):
            raise AssertionError("Gate-1 synthetic loss became nonfinite")
        loss.backward()
        finite_gradients &= all(
            parameter.grad is not None and torch.isfinite(parameter.grad).all().item()
            for parameter in ranker.parameters()
        )
        if not finite_gradients:
            raise AssertionError("Gate-1 synthetic gradient became nonfinite")
        optimizer.step()
    after = ranker(
        synthetic_batch.public_hidden,
        synthetic_batch.option_embeddings,
        synthetic_batch.option_offsets,
    ).detach()
    after_concordance = _concordance(after, synthetic_batch.target, synthetic_batch.target_mask)
    if after_concordance < 0.99 or after_concordance <= before_concordance:
        raise AssertionError(f"synthetic ranking did not improve: {before_concordance} -> {after_concordance}")

    masked_available = torch.tensor([False, True, True])
    choice = choose_legal_option(after, masked_available)
    if choice == 0 or not masked_available[choice]:
        raise AssertionError("legal mask was not enforced")
    equal_scores = torch.ones(3)
    if choose_legal_option(equal_scores, torch.tensor([True, True, False])) != 0:
        raise AssertionError("equal-score tie did not choose the lowest legal index")
    if deterministic_legal_fallback(torch.tensor([False, True]), fallback_index=0) != 1:
        raise AssertionError("deterministic legal fallback was not legal")
    try:
        ranker(
            synthetic_batch.public_hidden,
            synthetic_batch.option_embeddings[:0],
            torch.tensor([0, 0], dtype=torch.long),
        )
    except OutcomeRankerError:
        pass
    else:
        raise AssertionError("empty option group was not rejected")
    try:
        ranker(
            torch.full_like(synthetic_batch.public_hidden, float("nan")),
            synthetic_batch.option_embeddings,
            synthetic_batch.option_offsets,
        )
    except OutcomeRankerError:
        pass
    else:
        raise AssertionError("nonfinite hidden input was not rejected")

    restored = load_checkpoint(checkpoint_bytes(ranker, binding))
    restored_scores = restored(
        synthetic_batch.public_hidden,
        synthetic_batch.option_embeddings,
        synthetic_batch.option_offsets,
    ).detach()
    if not torch.equal(after, restored_scores):
        raise AssertionError("Gate-1 checkpoint roundtrip changed scores")

    checkpoint_value = torch.load(
        io.BytesIO(checkpoint_bytes(ranker, binding)), map_location="cpu", weights_only=True
    )
    bad_dimensions = copy.deepcopy(checkpoint_value)
    bad_dimensions["hidden_width"] = 159
    bad_dimensions_stream = io.BytesIO()
    torch.save(bad_dimensions, bad_dimensions_stream)
    with pytest.raises(OutcomeRankerError, match="dimensions"):
        load_checkpoint(bad_dimensions_stream.getvalue())
    bad_weights = copy.deepcopy(checkpoint_value)
    bad_weights["state_dict"]["head.0.weight"][0, 0] = float("nan")
    bad_weights_stream = io.BytesIO()
    torch.save(bad_weights, bad_weights_stream)
    with pytest.raises(OutcomeRankerError, match="nonfinite"):
        load_checkpoint(bad_weights_stream.getvalue())

    alignment_tamper = copy.deepcopy(dataset)
    alignment_tamper["state_groups"][0]["public_tensor"]["projected_decision"]["transport_sidecar"]["request_id"] = "tampered"
    alignment_path = Path("/tmp/outcome-ranker-gate1-alignment-tamper.json")
    alignment_path.write_text(json.dumps(alignment_tamper), encoding="utf-8")
    with pytest.raises(OutcomeRankerError, match="transport"):
        load_counterfactual_dataset(alignment_path, trunk)

    aggregate_tamper = copy.deepcopy(dataset)
    aggregate_tamper["state_groups"][0]["action_aggregates"][0]["mean_reward"] = 0.0
    aggregate_path = Path("/tmp/outcome-ranker-gate1-aggregate-tamper.json")
    aggregate_path.write_text(json.dumps(aggregate_tamper), encoding="utf-8")
    with pytest.raises(OutcomeRankerError, match="aggregate mean_reward"):
        load_counterfactual_dataset(aggregate_path, trunk)

    for _ in range(5):
        with torch.inference_mode():
            output = trunk(collate_projected((number_decision(3)[2],)), trunk.initial_hidden(1, "cpu"))
            ranker(output.hidden, output.option_embeddings, output.option_offsets)
    latency_samples: list[float] = []
    decision = number_decision(3)[2]
    decision_batch = collate_projected((decision,))
    hidden = trunk.initial_hidden(1, "cpu")
    for _ in range(40):
        started = time.perf_counter()
        with torch.inference_mode():
            output = trunk(decision_batch, hidden)
            ranker(output.hidden, output.option_embeddings, output.option_offsets)
        latency_samples.append((time.perf_counter() - started) * 1000.0)
    latency_samples.sort()
    return {
        "bc_trunk_frozen": True,
        "transport_alignment_rejected": True,
        "aggregate_tamper_rejected": True,
        "real_dataset_loaded": True,
        "real_dataset_groups": len(real_batch.state_group_ids),
        "real_dataset_options": int(real_batch.option_embeddings.shape[0]),
        "real_dataset_no_grad": True,
        "real_dataset_not_optimized": True,
        "base_trunk_rejected": True,
        "random_trunk_rejected": True,
        "unfrozen_trunk_rejected": True,
        "duplicate_determinization_rejected": True,
        "standalone_semantic_alias_checked": True,
        "duplicate_semantics_broadcast": True,
        "empty_group_rejected": True,
        "finite_gradients": finite_gradients,
        "checkpoint_roundtrip_exact": True,
        "before_concordance": before_concordance,
        "after_concordance": after_concordance,
        "combined_cpu_p95_ms": latency_samples[37],
        "ranker_parameters": sum(parameter.numel() for parameter in ranker.parameters()),
    }


def test_gate1_contract() -> None:
    result = run()
    assert result["bc_trunk_frozen"]
    assert result["transport_alignment_rejected"]
    assert result["aggregate_tamper_rejected"]
    assert result["real_dataset_loaded"]
    assert result["real_dataset_groups"] == 1
    assert result["real_dataset_options"] == 9
    assert result["real_dataset_no_grad"]
    assert result["real_dataset_not_optimized"]
    assert result["base_trunk_rejected"]
    assert result["random_trunk_rejected"]
    assert result["unfrozen_trunk_rejected"]
    assert result["duplicate_determinization_rejected"]
    assert result["standalone_semantic_alias_checked"]
    assert result["duplicate_semantics_broadcast"]
    assert result["empty_group_rejected"]
    assert result["finite_gradients"]
    assert result["checkpoint_roundtrip_exact"]
    assert result["after_concordance"] > result["before_concordance"]


def test_standalone_projector_semantic_fingerprint_matches_collector() -> None:
    _, request, _ = number_decision(3)
    records = _action_records(request, [(index,) for index in range(len(request.options))])
    assert all(
        record["action_id"]
        == stable_hash({
            "ordering": request.ordering,
            "semantic_path": [request.options[index].semantic_fingerprint],
        })
        for index, record in enumerate(records)
    )
    assert all(
        record["semantic_action_fingerprint"] == stable_hash(record["semantic_path"])
        for record in records
    )
    assert any(record["semantic_action_fingerprint"] != record["action_id"] for record in records)


def _permute_option_rows(model: object, permutation: tuple[int, ...]) -> object:
    row_fields = (
        "option_categorical_values",
        "option_categorical_missing",
        "option_numeric_values",
        "option_numeric_missing",
        "option_source_entity_indices",
        "option_target_entity_indices",
        "option_available_mask",
    )
    return replace(
        model,
        **{
            field: tuple(getattr(model, field)[index] for index in permutation)
            for field in row_fields
        },
    )


def _mutate_entity_row(model: object, entity_index: int, *, categorical: int | None = None,
                       numeric: int | None = None, value: int | float = 0) -> object:
    if categorical is not None:
        rows = [list(row) for row in model.entity_categorical_values]
        rows[entity_index][categorical] = value
        return replace(model, entity_categorical_values=tuple(tuple(row) for row in rows))
    if numeric is not None:
        rows = [list(row) for row in model.entity_numeric_values]
        rows[entity_index][numeric] = value
        return replace(model, entity_numeric_values=tuple(tuple(row) for row in rows))
    raise AssertionError("a categorical or numeric entity field is required")


def _mutate_entity_parent(model: object, entity_index: int, parent_index: int) -> object:
    parents = list(model.entity_parent_indices)
    parents[entity_index] = parent_index
    return replace(model, entity_parent_indices=tuple(parents))


def _mutate_entity_energy(model: object, entity_index: int, values: tuple[int, ...]) -> object:
    offsets = list(model.entity_energy_offsets)
    start, end = offsets[entity_index], offsets[entity_index + 1]
    flattened = list(model.entity_energy_values)
    flattened[start:end] = values
    delta = len(values) - (end - start)
    for offset_index in range(entity_index + 1, len(offsets)):
        offsets[offset_index] += delta
    return replace(
        model,
        entity_energy_values=tuple(flattened),
        entity_energy_offsets=tuple(offsets),
    )


def test_real_equivalence_pooling_is_public_and_permutation_invariant() -> None:
    root = (
        Path(__file__).resolve().parents[3]
        / ".chatgpt/tmp/counterfactual-q/runs/full-counterfactual-q-20260809T174041.651492Z-513a20492a53"
    )
    trunk, _ = load_gate1_trunk()
    batches = [
        load_counterfactual_dataset(path, trunk)
        for path in sorted((root / "datasets").glob("*.json"))
    ]
    classes = [metadata for batch in batches for group in batch.equivalence_class_metadata for metadata in group]
    assert len(classes) == 29
    assert sum(metadata["branch_count"] for metadata in classes) == 272
    assert all(metadata["particle_count"] == 8 for metadata in classes)
    assert all(
        metadata["sample_unit"] == "PAIRED_DETERMINIZATION_EQUIVALENCE_CLUSTER_MEAN"
        for metadata in classes
    )
    duplicate_classes = [metadata for metadata in classes if len(metadata["member_indices"]) > 1]
    assert sorted(metadata["target"] for metadata in duplicate_classes) == pytest.approx(
        sorted([-1 / 6, -0.125, 0.625, 0.75])
    )
    assert all(metadata["disagreement"] for metadata in duplicate_classes)

    pooled_pair_count = 0
    for batch in batches:
        for group in batch.equivalence_class_metadata:
            for left_index, left in enumerate(group):
                for right in group[left_index + 1 :]:
                    pooled_pair_count += int(left["target"] != right["target"])
    assert pooled_pair_count == 64

    dataset = json.loads(
        (root / "datasets/counterfactual-action-dataset-iono.json").read_text(encoding="utf-8")
    )
    group = next(
        item
        for item in dataset["state_groups"]
        if item["state_group_id"].startswith("9d298d5f")
    )
    request = group["request"]
    model = _projected_decision(group["public_tensor"]["projected_decision"]).model
    options = request["options"]
    original_keys = [semantic_equivalence_key(request, options, model, index) for index in range(len(options))]
    permutation = tuple(reversed(range(len(options))))
    permuted_options = [options[index] for index in permutation]
    permuted_model = _permute_option_rows(model, permutation)
    assert [
        semantic_equivalence_key(request, permuted_options, permuted_model, index)
        for index in range(len(options))
    ] == [original_keys[index] for index in permutation]

    moved_refs = copy.deepcopy(options)
    moved_refs[1]["source_ref"] = "p9:s999"
    moved_refs[1]["target_ref"] = "p9:s998"
    assert semantic_equivalence_key(request, moved_refs, model, 1) == original_keys[1]

    source_index = model.option_source_entity_indices[1]
    target_index = model.option_target_entity_indices[1]
    assert source_index >= 0 and target_index >= 0
    source_card_column = model.entity_categorical_names.index("card_id")
    target_zone_column = model.entity_categorical_names.index("zone")
    target_damage_column = model.entity_numeric_names.index("damage")
    target_status_column = model.entity_numeric_names.index("status_poisoned")
    assert semantic_equivalence_key(
        request, options, _mutate_entity_row(model, source_index, categorical=source_card_column, value=9999), 1
    ) != original_keys[1]
    assert semantic_equivalence_key(
        request, options, _mutate_entity_row(model, target_index, categorical=source_card_column, value=9998), 1
    ) != original_keys[1]
    assert semantic_equivalence_key(
        request, options, _mutate_entity_row(model, target_index, categorical=target_zone_column, value=99), 1
    ) != original_keys[1]
    assert semantic_equivalence_key(
        request, options, _mutate_entity_row(model, target_index, numeric=target_damage_column, value=10), 1
    ) != original_keys[1]
    assert semantic_equivalence_key(
        request, options, _mutate_entity_row(model, target_index, numeric=target_status_column, value=1.0), 1
    ) != original_keys[1]

    _, amount_request_object, amount_decision = number_decision(3)
    amount_request = {
        "selection_type": amount_request_object.selection_type,
        "selection_context": amount_request_object.selection_context,
        "min_count": 1,
        "max_count": 3,
        "ordering": amount_request_object.ordering,
    }
    amount_options = [{"is_stop": False} for _ in amount_decision.model.option_numeric_values]
    amount_key = semantic_equivalence_key(amount_request, amount_options, amount_decision.model, 1)
    amount_rows = [list(row) for row in amount_decision.model.option_numeric_values]
    amount_rows[1][0] += 1.0
    amount_model = replace(
        amount_decision.model,
        option_numeric_values=tuple(tuple(row) for row in amount_rows),
    )
    assert semantic_equivalence_key(amount_request, amount_options, amount_model, 1) != amount_key

    parent_key = semantic_equivalence_key(
        request, options, _mutate_entity_parent(model, source_index, target_index), 1
    )
    assert parent_key != original_keys[1]
    with pytest.raises(OutcomeRankerError, match="cycle"):
        semantic_equivalence_key(
            request, options, _mutate_entity_parent(model, source_index, source_index), 1
        )
    with pytest.raises(OutcomeRankerError, match="unknown"):
        semantic_equivalence_key(
            request, options, _mutate_entity_parent(model, source_index, len(model.entity_parent_indices)), 1
        )

    energy_four_key = semantic_equivalence_key(
        request, options, _mutate_entity_energy(model, source_index, (4,)), 1
    )
    energy_five_key = semantic_equivalence_key(
        request, options, _mutate_entity_energy(model, source_index, (5,)), 1
    )
    energy_four_twice_key = semantic_equivalence_key(
        request, options, _mutate_entity_energy(model, source_index, (4, 4)), 1
    )
    assert energy_four_key != original_keys[1]
    assert energy_five_key != energy_four_key
    assert energy_four_twice_key != energy_four_key
    for invalid_energy in ((-1,), (12,), (999,), (1.0,)):
        with pytest.raises(OutcomeRankerError, match="energy"):
            semantic_equivalence_key(
                request,
                options,
                _mutate_entity_energy(model, source_index, invalid_energy),
                1,
            )


def test_grouped_loss_rejects_malformed_contract() -> None:
    scores = torch.tensor([0.2, -0.1, 0.4])
    target = torch.tensor([1.0, 0.0, -1.0])
    mask = torch.tensor([True, True, True])
    offsets = torch.tensor([0, 3], dtype=torch.long)
    assert torch.isfinite(grouped_ranker_loss(scores, target, mask, offsets)).item()
    with pytest.raises(OutcomeRankerError, match="one-dimensional"):
        grouped_ranker_loss(scores[:, None], target, mask, offsets)
    with pytest.raises(OutcomeRankerError, match="finite"):
        grouped_ranker_loss(scores, torch.tensor([float("nan"), 0.0, -1.0]), mask, offsets)
    with pytest.raises(OutcomeRankerError, match="finite"):
        grouped_ranker_loss(scores, target, mask, offsets, temperature=float("nan"))
    with pytest.raises(OutcomeRankerError, match="finite"):
        grouped_ranker_loss(scores, target, mask, offsets, pairwise_weight=float("inf"))
    with pytest.raises(OutcomeRankerError, match="finite"):
        grouped_ranker_loss(scores, target, mask, offsets, temperature=float("inf"))
    with pytest.raises(OutcomeRankerError, match="weights"):
        grouped_ranker_loss(scores, target, mask, offsets, target_weight=torch.tensor([1.0, -1.0, 1.0]))
    with pytest.raises(OutcomeRankerError, match="nonnegative"):
        grouped_ranker_loss(scores, target, mask, torch.tensor([-1, 1, 3], dtype=torch.long))
    with pytest.raises(OutcomeRankerError, match="nondecreasing"):
        grouped_ranker_loss(scores, target, mask, torch.tensor([0, 3, 2], dtype=torch.long))
    with pytest.raises(OutcomeRankerError, match="cover"):
        grouped_ranker_loss(scores, target, mask, torch.tensor([0, 2], dtype=torch.long))


def test_grouped_loss_is_invariant_to_alias_count() -> None:
    scores = torch.tensor([0.2, -0.1, 0.4])
    target = torch.tensor([1.0, 0.0, -1.0])
    mask = torch.tensor([True, True, True])
    weights = torch.tensor([1.0, 2.0, 3.0])
    keys = ("class-a", "class-b", "class-c")
    offsets = torch.tensor([0, 3], dtype=torch.long)

    def losses(
        local_scores: torch.Tensor,
        local_target: torch.Tensor,
        local_mask: torch.Tensor,
        local_weights: torch.Tensor,
        local_keys: tuple[str, ...],
        local_offsets: torch.Tensor,
    ) -> tuple[float, float, float]:
        huber = grouped_ranker_loss(
            local_scores,
            local_target,
            local_mask,
            local_offsets,
            target_weight=local_weights,
            pairwise_weight=0.0,
            semantic_equivalence_keys=local_keys,
        )
        total = grouped_ranker_loss(
            local_scores,
            local_target,
            local_mask,
            local_offsets,
            target_weight=local_weights,
            pairwise_weight=0.37,
            semantic_equivalence_keys=local_keys,
        )
        return float(huber), float(total - huber), float(total)

    baseline = losses(scores, target, mask, weights, keys, offsets)
    aliased = losses(
        torch.cat((scores, scores[:1])),
        torch.cat((target, target[:1])),
        torch.tensor([True, True, True, True]),
        torch.tensor([1.0, 2.0, 3.0, 999.0]),
        keys + ("class-a",),
        torch.tensor([0, 4], dtype=torch.long),
    )
    assert aliased == pytest.approx(baseline, abs=1e-8)


def test_ranking_diagnostics_are_class_level_with_inverse_transport() -> None:
    keys = ("class-b", "class-a", "class-a", "class-c")
    target = torch.tensor([0.5, -1.0, -1.0, 0.0])
    scores = torch.tensor([0.4, -0.2, -0.2, 0.1])

    def metrics(order: tuple[int, ...]) -> dict[str, object]:
        index = torch.tensor(order, dtype=torch.long)
        ordered_keys = tuple(keys[position] for position in order)
        batch = RankerBatch(
            public_hidden=torch.zeros((1, 160)),
            option_embeddings=torch.zeros((len(order), 128)),
            option_available=torch.ones(len(order), dtype=torch.bool),
            option_offsets=torch.tensor([0, len(order)], dtype=torch.long),
            target=target[index],
            target_stderr=torch.ones(len(order)),
            target_weight=torch.ones(len(order)),
            target_mask=torch.ones(len(order), dtype=torch.bool),
            group_offsets=torch.tensor([0, len(order)], dtype=torch.long),
            state_group_ids=("diagnostic-state",),
            action_ids=tuple(f"action-{position}" for position in order),
            semantic_fingerprints=ordered_keys,
            semantic_equivalence_keys=ordered_keys,
        )
        return _ranking_metrics(scores[index], batch)["group_concordance"][0]

    original = metrics((0, 1, 2, 3))
    permuted = metrics((2, 3, 0, 1))
    for field in (
        "target_top_indices",
        "predicted_top_indices",
        "target_order",
        "predicted_order",
        "equivalence_class_keys",
        "representative_target",
        "representative_scores",
    ):
        assert original[field] == permuted[field]
    assert original["equivalence_class_keys"] == ["class-a", "class-b", "class-c"]
    assert original["inverse_transport_mapping"] != permuted["inverse_transport_mapping"]
    assert original["physical_selected_index_tie_mapping"] != permuted[
        "physical_selected_index_tie_mapping"
    ]


if __name__ == "__main__":
    print(json.dumps(run(), sort_keys=True))
