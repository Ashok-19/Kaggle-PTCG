"""Contract tests for the actual restricted collector ``labels`` sidecar."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ceiling_analyzer import _stable_hash, _target_key, analyze, analyze_pairs, load_branch_sidecar, stratified_group_split

SCHEMA = "61f6f71008c847b03bbab913d767da2c6bc6469311a0fe7249f3d03ee512bf68"
FIREWALL = {
    "consumer": "LABEL_AUDIT_ONLY", "model_facing_fields_present": False,
    "public_root_source": "G2_PROJECTED_PUBLIC_ONLY", "opponent_view_retention": "NONE",
    "opponent_legal_set_retention": "SEMANTIC_LABEL_AUDIT_ONLY",
    "post_evidence_source": "NONE_FIRST_OPPONENT_ACTION_ONLY", "ppo_rollout_eligible": False,
}


def _feature(tensor, index, trunk=None):
    value = tensor["marker"]
    return tuple([float(value), float(index)] + [0.0] * 286)


def _option(seed: int, role: str = "PLAY", original_index: int = 0, *, option_type: int = 7) -> dict:
    return {
        "option_type": option_type, "source_kind": "ENTITY", "target_kind": "NONE", "choice_role": role,
        "source_ref": f"p1:s{seed}", "target_ref": None, "is_stop": False, "original_index": original_index,
        "source_card_id": None, "target_card_id": None, "attack_id": None,
        "semantic_fingerprint": f"{seed + 1:064x}", "semantic_equivalence_key": f"{seed + 1:064x}",
    }


def _fixture(tmp_path: Path, roots: int = 64, *, unseen: bool = False, aliases: bool = False, collide: bool = False):
    root_groups, labels, projection_groups, action_keys = [], [], [], []
    policy = "rule-family"
    test_roots = set()
    for seat in (0, 1):
        ordered = sorted((f"state-{i}" for i in range(roots) if i % 2 == seat), key=lambda x: hashlib.sha256(x.encode()).hexdigest())
        test_roots.update(ordered[round(len(ordered) * .625) + round(len(ordered) * .1875):])
    for root_i in range(roots):
        state = f"state-{root_i}"
        root_key = f"{root_i + 1:064x}"
        projected = {"root_marker": root_i}
        history = f"{root_i + 100:064x}"
        kind = root_i % 3
        selection_type, selection_context = ((0, 0), (1, 4), (5, 34))[kind]
        ordering = "ORDERED" if kind == 2 else "UNORDERED"
        minimum = maximum = 2 if kind == 2 else 1
        option_count = 3 if kind == 1 else 2
        tensor = {
            "public_only": True, "raw_observation_retained": False, "forbidden_actor_features_absent": True,
            "marker": 0 if collide else root_i % 6,
            "projected_decision": {**projected, "transport_sidecar": {"original_indices": [0, 1]}},
            "history_tokens": [{"history_schema_version": 1, "history_source": "RECORDED_PUBLIC_GRU_HIDDEN", "history_steps": 1, "prefix_digest": history, "model_schema_sha256": SCHEMA}],
            "prefix_provenance": {"prefix_digest": history},
        }
        root_options = [_option(root_i + 10, original_index=0), _option(root_i + 100, "ATTACH", original_index=1)]
        options = [
            _option(root_i * 10 + index, "CARD" if kind == 1 else "SKILL" if kind == 2 else "PLAY", index, option_type=3 if kind == 1 else 15 if kind == 2 else 7)
            for index in range(option_count)
        ]
        unseen_root = unseen and state in test_roots
        class_id = root_i % 6
        if kind == 2:
            base = 0xA000 + root_i * 2 if unseen_root else 0x700 + class_id * 2
            option_keys = [f"{base:064x}", f"{base + 1:064x}"]
            selected_indices = [0, 1] if class_id % 2 == 0 else [1, 0]
        else:
            target_key = f"{0x9000 + root_i:064x}" if unseen_root else f"{0x500 + class_id:064x}"
            option_keys = [target_key] * option_count
            selected_indices = [root_i % option_count]
        for option, key in zip(options, option_keys):
            option["semantic_equivalence_key"] = key
        groups = []
        for replicate in range(4):
            groups.append({"replicate_id": replicate, "determinization_id": f"particle-{root_i}-{replicate}", "actions": []})
            for alias in range(2 if aliases else 1):
                action_id = f"action-{root_i}-{alias}"
                fingerprint = f"{root_i + replicate + alias + 1000:064x}"
                action_keys.append({"state_group_id": state, "action_id": action_id, "semantic_equivalence_key": root_key})
                groups[-1]["actions"].append({"action_id": action_id, "transport_original_indices": [0], "semantic_action_fingerprint": fingerprint})
                path = [options[index] for index in selected_indices]
                if kind != 2:
                    path = [options[(selected_indices[0] + replicate) % option_count]]
                action_key = path[0]["semantic_equivalence_key"] if len(path) == 1 else _stable_hash({"ordering": ordering, "semantic_path": [option["semantic_equivalence_key"] for option in path]})
                chosen = {"transport_original_indices": [option["original_index"] for option in path], "semantic_path": path, "semantic_equivalence_key": action_key}
                chosen["semantic_action_fingerprint"] = _stable_hash(chosen["semantic_path"])
                labels.append({
                    "state_group_id": state, "replicate_id": replicate, "particle_id": f"particle-{root_i}-{replicate}",
                    "action_id": action_id, "root_player": root_i % 2, "opponent_player": 1 - (root_i % 2),
                    "root_action_semantic_fingerprint": fingerprint, "root_action_semantic_equivalence_key": root_key,
                    "status": "OBSERVED", "first_opponent_request": {"request_id": f"request-{root_i}-{replicate}-{alias}", "selection_seq": 0, "selection_type": selection_type, "selection_context": selection_context, "min_count": minimum, "max_count": maximum, "ordering": ordering, "option_count": option_count, "options": options},
                    "chosen_action": chosen, "error": None,
                })
        root_groups.append({"state_group_id": state, "public_state_sha256": f"{root_i + 10000:064x}", "root_player": root_i % 2, "request": {"options": root_options}, "public_tensor": tensor, "replicates": groups})
        projection_groups.append({"state_group_id": state, "public_state_sha256": root_groups[-1]["public_state_sha256"], "public_projection_sha256": _stable_hash(root_groups[-1]["public_tensor"]["projected_decision"]), "history_prefix_digest": history, "history_tokens_sha256": _stable_hash(tensor["history_tokens"])})
    root = {"schema_version": 1, "run": {"run_id": "run-1", "source_commit": "abcdef1"}, "state_groups": root_groups}
    sidecar = {
        "schema_version": 1, "sidecar_kind": "RESTRICTED_OPPONENT_TRANSITION_LABELS",
        "run": {"run_id": "run-1", "source_commit": "abcdef1", "config_sha256": "1" * 64, "profile": "GATE1_SCALE64_OPPONENT_TRANSITION_V1"},
        "dataset_binding": {"dataset_path": str(tmp_path / "root.json"), "dataset_sha256": "", "state_group_ids": [f"state-{i}" for i in range(roots)]},
        "public_projection_binding": {"projector_path": "x", "projector_sha256": "2" * 64, "model_schema_sha256": SCHEMA, "groups": projection_groups},
        "root_action_keys": action_keys, "provenance": {"anchor_baseline_id": "anchor", "opponent_policy_id": policy, "opponent_policy_sha256": "3" * 64, "opponent_deck_sha256": "4" * 64, "split_role": "LABEL_AUDIT_METADATA_ONLY"},
        "firewall": FIREWALL, "labels": labels,
    }
    root_path = tmp_path / "root.json"
    sidecar_path = tmp_path / "labels.json"
    root_path.write_text(json.dumps(root), encoding="utf-8")
    sidecar["dataset_binding"]["dataset_sha256"] = hashlib.sha256(root_path.read_bytes()).hexdigest()
    sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")
    return sidecar_path, root_path


def _config(tmp_path: Path, sidecar: Path, *, profile: str = "GATE1_SCALE64_OPPONENT_TRANSITION_V1") -> Path:
    config = {"source_commit": "abcdef1", "frozen_anchor_policies": [{"baseline_id": "anchor", "policy_id": "rule-family"}], "state_schedule": {"profile": profile, "anchor_cells": [{"anchor": "anchor", "states": 4}]}}
    path = tmp_path / "schedule.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    data = json.loads(sidecar.read_text())
    data["run"]["config_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    sidecar.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_actual_labels_learnable_signal_and_metrics(tmp_path):
    sidecar, root = _fixture(tmp_path)
    result = analyze(sidecar, root, feature_extractor=_feature)
    assert result["fit"]["status"] == "FIT"
    assert result["features"]["public_only"] == ["pre_root_public_hidden[160]", "candidate_option_embedding[128]"]
    assert result["reports"]["test"]["top3"] >= 0.75
    assert result["target"] == "selection_type/context/ordering/semantic_action_path"
    assert result["reports"]["test"]["context_top1"] is not None
    assert result["status"] == "BLOCKED_MECHANICS"
    assert result["gates"]["real_frozen_feature_path"] is False


def test_factual_request_context_and_ordered_target(tmp_path):
    sidecar, root = _fixture(tmp_path)
    records, _ = load_branch_sidecar(sidecar, root, feature_extractor=_feature)
    assert {context for row in records for context in row.target_contexts} == {"0:0", "1:4", "5:34"}
    data = json.loads(sidecar.read_text())
    skill = next(label for label in data["labels"] if label["first_opponent_request"]["selection_type"] == 5)
    assert skill["first_opponent_request"]["ordering"] == "ORDERED"
    assert len(skill["chosen_action"]["semantic_path"]) == 2
    left, right = "a" * 64, "b" * 64
    assert _target_key(5, 34, "ORDERED", [left, right]) != _target_key(5, 34, "ORDERED", [right, left])
    assert _target_key(1, 4, "UNORDERED", [left, right]) == _target_key(1, 4, "UNORDERED", [right, left])


def test_malformed_compound_path_is_rejected(tmp_path):
    sidecar, root = _fixture(tmp_path)
    data = json.loads(sidecar.read_text())
    label = next(label for label in data["labels"] if label["first_opponent_request"]["selection_type"] == 5)
    option = label["first_opponent_request"]["options"][0]
    label["chosen_action"] = {
        "transport_original_indices": [0], "semantic_path": [option],
        "semantic_equivalence_key": option["semantic_equivalence_key"],
        "semantic_action_fingerprint": _stable_hash([option]),
    }
    sidecar.write_text(json.dumps(data), encoding="utf-8")
    _, ingest = load_branch_sidecar(sidecar, root, feature_extractor=_feature)
    assert any("selection bounds" in error for error in ingest["join_errors"])


def test_selection_context_binding_is_not_ignored(tmp_path):
    sidecar, root = _fixture(tmp_path)
    data = json.loads(sidecar.read_text())
    label = next(label for label in data["labels"] if label["first_opponent_request"]["selection_type"] == 5)
    label["first_opponent_request"]["selection_context"] = 0
    sidecar.write_text(json.dumps(data), encoding="utf-8")
    _, ingest = load_branch_sidecar(sidecar, root, feature_extractor=_feature)
    assert any("ordering" in error for error in ingest["join_errors"])


def test_support_gate_fails_on_missing_choice_labels(tmp_path):
    sidecar, root = _fixture(tmp_path)
    data = json.loads(sidecar.read_text())
    for label in data["labels"][:20]:
        label["status"] = "UNSUPPORTED_FIRST_OPPONENT_REQUEST"
        label["chosen_action"] = None
    sidecar.write_text(json.dumps(data), encoding="utf-8")
    result = analyze(sidecar, root, feature_extractor=_feature)
    assert result["gates"]["support_ge_0_95"] is False
    assert result["gates"]["support_ge_0_90_each_anchor_pair"] is False
    assert result["status"] == "BLOCKED_MECHANICS"


def test_root_only_stratified_split_and_alias_pooling(tmp_path):
    sidecar, root = _fixture(tmp_path, roots=64, aliases=True)
    records, ingest = load_branch_sidecar(sidecar, root, feature_extractor=_feature)
    assert ingest["supported_label_count"] == 64 * 4 * 2
    assert len(records) == 64
    split = stratified_group_split(records)
    assert {name: len({row.root for row in rows}) for name, rows in split.items()} == {"train": 40, "tune": 12, "test": 12}
    assert not ({row.root for row in split["train"]} & {row.root for row in split["test"]})


def test_sha_path_and_feature_firewall(tmp_path):
    sidecar, root = _fixture(tmp_path, roots=4)
    data = json.loads(root.read_text())
    data["state_groups"][0]["public_tensor"]["opponent_legal_options"] = []
    root.write_text(json.dumps(data), encoding="utf-8")
    side = json.loads(sidecar.read_text())
    side["dataset_binding"]["dataset_sha256"] = hashlib.sha256(root.read_bytes()).hexdigest()
    sidecar.write_text(json.dumps(side), encoding="utf-8")
    with pytest.raises(ValueError, match="forbidden public feature field"):
        load_branch_sidecar(sidecar, root, feature_extractor=_feature)
    data = json.loads(sidecar.read_text())
    data["dataset_binding"]["dataset_path"] = str(tmp_path / "other.json")
    sidecar.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="dataset_path"):
        load_branch_sidecar(sidecar, root, feature_extractor=_feature)


def test_unseen_labels_are_reported(tmp_path):
    sidecar, root = _fixture(tmp_path, unseen=True)
    result = analyze(sidecar, root, feature_extractor=_feature)
    assert result["reports"]["test"]["unseen_class_rate"] == 1.0
    assert result["reports"]["test"]["root_bootstrap_top3_lcb95"] == 0.0


def test_collision_gate_is_explicit(tmp_path):
    sidecar, root = _fixture(tmp_path, roots=8, collide=True)
    result = analyze(sidecar, root, feature_extractor=_feature)
    assert result["collisions"]["collision_group_count"] > 0
    assert not result["gates"]["zero_join_firewall_reliability_collision_errors"]


def test_global_pairs_duplicate_roots_are_blocked(tmp_path):
    sidecar, root = _fixture(tmp_path, roots=4)
    result = analyze_pairs([(sidecar, root), (sidecar, root)], feature_extractor=_feature)
    assert result["status"] == "BLOCKED_MECHANICS"
    assert result["gates"]["no_duplicate_roots"] is False


def test_exact_history_original_index_replicate_and_status_checks(tmp_path):
    sidecar, root = _fixture(tmp_path, roots=4)
    data = json.loads(sidecar.read_text())
    data["public_projection_binding"]["groups"][0]["history_tokens_sha256"] = "f" * 64
    sidecar.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="history_tokens_sha256"):
        load_branch_sidecar(sidecar, root, feature_extractor=_feature)
    sidecar, root = _fixture(tmp_path, roots=4)
    data = json.loads(sidecar.read_text())
    data["labels"][0]["replicate_id"] = 4
    sidecar.write_text(json.dumps(data), encoding="utf-8")
    _, ingest = load_branch_sidecar(sidecar, root, feature_extractor=_feature)
    assert any("replicate_id" in error for error in ingest["join_errors"])
    sidecar, root = _fixture(tmp_path, roots=4)
    data = json.loads(sidecar.read_text())
    data["labels"][0]["status"] = "UNKNOWN"
    sidecar.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="schema validation"):
        load_branch_sidecar(sidecar, root, feature_extractor=_feature)


def test_root_action_fingerprint_is_required(tmp_path):
    sidecar, root = _fixture(tmp_path, roots=4)
    data = json.loads(root.read_text())
    data["state_groups"][0]["replicates"][0]["actions"][0]["semantic_action_fingerprint"] = "bad"
    root.write_text(json.dumps(data), encoding="utf-8")
    side = json.loads(sidecar.read_text())
    side["dataset_binding"]["dataset_sha256"] = hashlib.sha256(root.read_bytes()).hexdigest()
    sidecar.write_text(json.dumps(side), encoding="utf-8")
    with pytest.raises(ValueError, match="fingerprint"):
        load_branch_sidecar(sidecar, root, feature_extractor=_feature)


def test_actual_config_anchor_join_and_profile_binding(tmp_path):
    sidecar, root = _fixture(tmp_path, roots=4)
    config = _config(tmp_path, sidecar)
    result = analyze(sidecar, root, config_path=config, feature_extractor=_feature)
    assert result["status"] == "BLOCKED_MECHANICS"
    bad = json.loads(config.read_text())
    bad["state_schedule"]["profile"] = "WRONG"
    config.write_text(json.dumps(bad), encoding="utf-8")
    data = json.loads(sidecar.read_text())
    data["run"]["config_sha256"] = hashlib.sha256(config.read_bytes()).hexdigest()
    sidecar.write_text(json.dumps(data), encoding="utf-8")
    result = analyze(sidecar, root, config_path=config, feature_extractor=_feature)
    assert any("profile" in error for error in result["ingest"]["join_errors"])


def test_external_trunk_cannot_pass_frozen_feature_gate(tmp_path):
    sidecar, root = _fixture(tmp_path, roots=4)
    config = _config(tmp_path, sidecar)
    result = analyze(sidecar, root, config_path=config, trunk=object(), feature_extractor=_feature)
    assert result["gates"]["real_frozen_feature_path"] is False
