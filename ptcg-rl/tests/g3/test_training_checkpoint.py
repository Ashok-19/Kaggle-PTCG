from __future__ import annotations

import hashlib
import io
import json
import random
from pathlib import Path

import numpy as np
import pytest
import torch

from ptcg_rl.g3.checkpoint import (
    CHECKPOINT_KIND,
    CHECKPOINT_SCHEMA_VERSION,
    TrainingCheckpointError,
    restore_training_checkpoint,
    save_training_checkpoint,
)
from ptcg_rl.g3.evaluation import canonical_json_bytes


class UnsafeCheckpointObject:
    pass


def build_state():
    model = torch.nn.Sequential(torch.nn.Linear(3, 8), torch.nn.Tanh(), torch.nn.Linear(8, 2))
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
    scheduler = torch.optim.lr_scheduler.LinearLR(optimizer, start_factor=1.0, end_factor=0.5, total_iters=4)
    inputs = torch.tensor([[1.0, 2.0, 3.0], [3.0, 2.0, 1.0]])
    loss = model(inputs).square().mean()
    loss.backward()
    optimizer.step()
    scheduler.step()
    optimizer.zero_grad(set_to_none=True)
    return model, optimizer, scheduler, inputs


def read_payload(path: Path):
    return torch.load(io.BytesIO(path.read_bytes()), map_location="cpu", weights_only=True)


def rewrite_payload(path: Path, transform) -> None:
    payload = read_payload(path)
    transform(payload)
    buffer = io.BytesIO()
    torch.save(payload, buffer)
    raw = buffer.getvalue()
    path.write_bytes(raw)
    manifest_path = path.with_name(path.name + ".manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["payload"]["bytes"] = len(raw)
    manifest["payload"]["sha256"] = hashlib.sha256(raw).hexdigest()
    manifest_path.write_bytes(canonical_json_bytes(manifest))


def test_checkpoint_restores_all_required_state_and_available_rngs(tmp_path: Path) -> None:
    random.seed(11)
    np.random.seed(22)
    torch.manual_seed(33)
    model, optimizer, scheduler, inputs = build_state()
    expected_output = model(inputs).detach().clone()
    expected_optimizer_state_count = len(optimizer.state_dict()["state"])
    expected_scheduler_epoch = scheduler.last_epoch
    checkpoint = tmp_path / "training.pt"
    result = save_training_checkpoint(
        checkpoint,
        model=model,
        optimizer=optimizer,
        scheduler=scheduler,
        scaler=None,
        counters={"updates": 1, "choices": 64},
        league={"current": "toy-policy-v1", "entries": ["toy-policy-v1"]},
        rollout_boundary={"complete": True, "episode": 7},
        include_cuda_rng=False,
    )
    assert result["payload_bytes"] > 0
    assert len(result["payload_sha256"]) == 64
    assert not checkpoint.with_name(checkpoint.name + ".partial").exists()

    expected_random = random.random()
    expected_numpy = float(np.random.random())
    expected_torch = torch.rand(4)
    random.seed(99)
    np.random.seed(99)
    torch.manual_seed(99)
    with torch.no_grad():
        for parameter in model.parameters():
            parameter.add_(100.0)
    optimizer.state.clear()
    scheduler.last_epoch = 99

    loaded = restore_training_checkpoint(
        checkpoint,
        model=model,
        optimizer=optimizer,
        scheduler=scheduler,
        scaler=None,
        expected_sha256=result["payload_sha256"],
    )
    assert torch.equal(model(inputs), expected_output)
    assert len(optimizer.state_dict()["state"]) == expected_optimizer_state_count
    assert scheduler.last_epoch == expected_scheduler_epoch
    assert loaded.counters == {"updates": 1, "choices": 64}
    assert loaded.league["current"] == "toy-policy-v1"
    assert loaded.rollout_boundary == {"complete": True, "episode": 7}
    assert loaded.restored_rng_states == ("python", "numpy", "torch_cpu")
    assert random.random() == expected_random
    assert float(np.random.random()) == expected_numpy
    assert torch.equal(torch.rand(4), expected_torch)


def test_duplicate_checkpoint_builds_are_hash_stable_for_unchanged_state(tmp_path: Path) -> None:
    random.seed(1)
    np.random.seed(2)
    torch.manual_seed(3)
    model, optimizer, scheduler, _ = build_state()
    rng = (random.getstate(), np.random.get_state(), torch.get_rng_state().clone())
    first = tmp_path / "first.pt"
    first_result = save_training_checkpoint(
        first,
        model=model,
        optimizer=optimizer,
        scheduler=scheduler,
        scaler=None,
        counters={"updates": 1},
        league={"entries": []},
        rollout_boundary={"complete": True},
        include_cuda_rng=False,
    )
    random.setstate(rng[0])
    np.random.set_state(rng[1])
    torch.set_rng_state(rng[2])
    second = tmp_path / "second.pt"
    second_result = save_training_checkpoint(
        second,
        model=model,
        optimizer=optimizer,
        scheduler=scheduler,
        scaler=None,
        counters={"updates": 1},
        league={"entries": []},
        rollout_boundary={"complete": True},
        include_cuda_rng=False,
    )
    assert first.read_bytes() == second.read_bytes()
    assert first_result["payload_sha256"] == second_result["payload_sha256"]


def test_checkpoint_manifest_and_expected_identity_fail_closed(tmp_path: Path) -> None:
    model, optimizer, scheduler, _ = build_state()
    path = tmp_path / "checkpoint.pt"
    result = save_training_checkpoint(
        path,
        model=model,
        optimizer=optimizer,
        scheduler=scheduler,
        scaler=None,
        counters={},
        league={},
        rollout_boundary={},
        include_cuda_rng=False,
    )
    with pytest.raises(TrainingCheckpointError, match="SHA-256"):
        restore_training_checkpoint(
            path,
            model=model,
            optimizer=optimizer,
            scheduler=scheduler,
            scaler=None,
            expected_sha256="0" * 64,
        )
    path.write_bytes(path.read_bytes() + b"x")
    with pytest.raises(TrainingCheckpointError, match="differs from manifest"):
        restore_training_checkpoint(
            path, model=model, optimizer=optimizer, scheduler=scheduler, scaler=None
        )
    assert result["payload_sha256"] != hashlib.sha256(path.read_bytes()).hexdigest()


def test_checkpoint_rejects_noncanonical_missing_and_unknown_manifest_fields(tmp_path: Path) -> None:
    model, optimizer, scheduler, _ = build_state()
    path = tmp_path / "checkpoint.pt"
    save_training_checkpoint(
        path,
        model=model,
        optimizer=optimizer,
        scheduler=scheduler,
        scaler=None,
        counters={},
        league={},
        rollout_boundary={},
        include_cuda_rng=False,
    )
    manifest_path = path.with_name(path.name + ".manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    with pytest.raises(TrainingCheckpointError, match="not canonical"):
        restore_training_checkpoint(
            path, model=model, optimizer=optimizer, scheduler=scheduler, scaler=None
        )
    manifest["unexpected"] = True
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    with pytest.raises(TrainingCheckpointError, match="keys differ"):
        restore_training_checkpoint(
            path, model=model, optimizer=optimizer, scheduler=scheduler, scaler=None
        )
    manifest_path.unlink()
    with pytest.raises(TrainingCheckpointError, match="cannot read"):
        restore_training_checkpoint(
            path, model=model, optimizer=optimizer, scheduler=scheduler, scaler=None
        )


@pytest.mark.parametrize(
    "mutation,message",
    [
        (lambda value: value.update(schema_version=99), "schema version"),
        (lambda value: value.update(kind="WRONG"), "kind differs"),
        (lambda value: value.pop("optimizer_state"), "keys differ"),
        (lambda value: value.update(scheduler_state=None), "lacks scheduler"),
        (lambda value: value["rng_states"].update(torch_cpu=torch.tensor([1], dtype=torch.int64)), "uint8"),
        (lambda value: value.update(unexpected=True), "keys differ"),
    ],
)
def test_semantically_invalid_but_hash_consistent_payloads_fail_closed(
    tmp_path: Path, mutation, message
) -> None:
    model, optimizer, scheduler, _ = build_state()
    path = tmp_path / "checkpoint.pt"
    save_training_checkpoint(
        path,
        model=model,
        optimizer=optimizer,
        scheduler=scheduler,
        scaler=None,
        counters={},
        league={},
        rollout_boundary={},
        include_cuda_rng=False,
    )
    rewrite_payload(path, mutation)
    with pytest.raises(TrainingCheckpointError, match=message):
        restore_training_checkpoint(
            path, model=model, optimizer=optimizer, scheduler=scheduler, scaler=None
        )


def test_checkpoint_rejects_unsafe_metadata_and_missing_scheduler_or_scaler(tmp_path: Path) -> None:
    model, optimizer, scheduler, _ = build_state()
    with pytest.raises(TrainingCheckpointError, match="unsupported"):
        save_training_checkpoint(
            tmp_path / "unsafe.pt",
            model=model,
            optimizer=optimizer,
            scheduler=scheduler,
            scaler=None,
            counters={"bad": {1, 2}},
            league={},
            rollout_boundary={},
            include_cuda_rng=False,
        )
    with pytest.raises(TrainingCheckpointError, match="scheduler or scaler"):
        save_training_checkpoint(
            tmp_path / "missing.pt",
            model=model,
            optimizer=optimizer,
            scheduler=None,
            scaler=None,
            counters={},
            league={},
            rollout_boundary={},
            include_cuda_rng=False,
        )


def test_checkpoint_rejects_model_shape_and_scheduler_presence_mismatch(tmp_path: Path) -> None:
    model, optimizer, scheduler, _ = build_state()
    path = tmp_path / "checkpoint.pt"
    save_training_checkpoint(
        path,
        model=model,
        optimizer=optimizer,
        scheduler=scheduler,
        scaler=None,
        counters={},
        league={},
        rollout_boundary={},
        include_cuda_rng=False,
    )
    other = torch.nn.Linear(3, 2)
    other_optimizer = torch.optim.Adam(other.parameters())
    other_scheduler = torch.optim.lr_scheduler.LinearLR(other_optimizer, total_iters=2)
    with pytest.raises(TrainingCheckpointError, match="model keys differ"):
        restore_training_checkpoint(
            path,
            model=other,
            optimizer=other_optimizer,
            scheduler=other_scheduler,
            scaler=None,
        )
    with pytest.raises(TrainingCheckpointError, match="scheduler presence"):
        restore_training_checkpoint(
            path,
            model=model,
            optimizer=optimizer,
            scheduler=None,
            scaler=None,
        )


def test_restricted_loader_rejects_non_weights_only_payload(tmp_path: Path) -> None:
    path = tmp_path / "unsafe.pt"
    buffer = io.BytesIO()
    torch.save({"unsafe": UnsafeCheckpointObject()}, buffer)
    raw = buffer.getvalue()
    path.write_bytes(raw)
    manifest = {
        "schema_version": CHECKPOINT_SCHEMA_VERSION,
        "kind": "KPTCG_G3_TRAINING_CHECKPOINT_MANIFEST",
        "payload": {
            "path": path.name,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        },
    }
    path.with_name(path.name + ".manifest.json").write_bytes(canonical_json_bytes(manifest))
    model, optimizer, scheduler, _ = build_state()
    with pytest.raises(TrainingCheckpointError, match="restricted"):
        restore_training_checkpoint(
            path, model=model, optimizer=optimizer, scheduler=scheduler, scaler=None
        )


def test_payload_identity_constants_are_frozen() -> None:
    assert CHECKPOINT_SCHEMA_VERSION == 1
    assert CHECKPOINT_KIND == "KPTCG_G3_TRAINING_CHECKPOINT"
