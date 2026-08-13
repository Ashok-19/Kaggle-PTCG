from __future__ import annotations

import json
from pathlib import Path

import pytest

from ptcg_rl.g3.bc_canary import (
    BCCanaryContractError,
    build_semantic_loader_plan,
    execute_authorized_canary,
    pretty_object_hash,
)
from ptcg_rl.replay.planner import verify_plan


def test_pretty_object_hash_ignores_only_declared_self_hash() -> None:
    value = {"a": 1, "manifest_sha256": None}
    digest = pretty_object_hash(value, "manifest_sha256")
    value["manifest_sha256"] = digest
    assert pretty_object_hash(value, "manifest_sha256") == digest
    value["a"] = 2
    assert pretty_object_hash(value, "manifest_sha256") != digest


def test_semantic_loader_plan_is_exact_and_verifiable() -> None:
    records = [
        {"episode_id": 2, "bytes": 20},
        {"episode_id": 1, "bytes": 10},
    ]
    plan = build_semantic_loader_plan(records)
    result = verify_plan(plan)
    assert result == {
        "status": "pass",
        "plan_sha256": plan["plan_sha256"],
        "selected_files": 2,
        "selected_bytes": 30,
        "max_selected_file_bytes": 20,
    }
    assert [item["remote_filename"] for item in plan["selected_items"]] == [
        "1.json",
        "2.json",
    ]


def test_unauthorized_execution_refuses_before_loading_assets(tmp_path: Path) -> None:
    request = {
        "schema_version": 1,
        "record_id": "e01-bc-engineering-canary-request-v1",
        "source_path": "request.json",
        "request_ready": True,
        "authorized": False,
        "authorization": {
            "external_compute": False,
            "git_commit": False,
            "git_push": False,
            "label_generation": False,
            "model_promotion": False,
            "optimizer_steps": False,
            "production_training": False,
            "submission": False,
        },
        "execution": {
            "platform": "local_cpu_only",
            "external_compute": False,
            "accelerator": False,
            "data_workers": 0,
            "production_checkpoint_eligible": False,
            "maximum_optimizer_steps": 64,
            "checkpoint_at_optimizer_step": 32,
            "batch_size_episodes": 2,
            "recurrent_sequence_length": 32,
            "maximum_cpu_threads": 2,
            "maximum_wall_seconds": 1800,
            "seed": 20260804,
            "learning_rate": 0.0001,
            "maximum_gradient_norm": 1.0,
            "optimizer": "AdamW",
            "checkpoint_output": "private/g3/e01/bc-engineering-canary-v1",
        },
        "corpus": {
            "split": "train",
            "episode_count": 8,
            "meaningful_teacher_decisions": 8,
            "manifest_path": "missing.json",
            "manifest_sha256": "0" * 64,
            "episodes": [],
        },
        "assets": {},
    }
    path = tmp_path / "request.json"
    path.write_text(json.dumps(request), encoding="utf-8")
    with pytest.raises(BCCanaryContractError):
        execute_authorized_canary(tmp_path, path)
