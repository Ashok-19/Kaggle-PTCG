from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import torch

from ptcg_rl.g2.network import PolicyConfigV1


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "bc_capacity_sweep.py"
SPEC = importlib.util.spec_from_file_location("bc_capacity_sweep_test_module", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
SWEEP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SWEEP)


def test_batch_candidates_expand_through_small_learning_batches() -> None:
    assert SWEEP._expanded_batch_candidates((256,)) == (
        256,
        128,
        64,
        32,
        16,
        8,
        4,
        2,
        1,
    )


def test_update_density_estimate_needs_no_tensor_packing() -> None:
    episodes = tuple(
        SimpleNamespace(
            episode_id=index + 1,
            decisions=tuple(
                SimpleNamespace(request=SimpleNamespace(has_only_one_outcome=False))
                for _ in range(5)
            ),
        )
        for index in range(4)
    )
    targets, steps, targets_per_step = SWEEP._estimated_optimizer_update_density(
        episodes,
        batch_size=2,
        sequence_length=2,
        seed=17,
    )
    assert targets == 20
    assert steps == 6
    assert targets_per_step == 20 / 6


def test_stage_early_stopping_keeps_incoming_baseline(monkeypatch, tmp_path) -> None:
    model = torch.nn.Linear(1, 1)
    validation_nlls = iter((1.0, 1.01, 1.02, 1.03))
    saved_epochs: list[int] = []

    def fake_validate(*_args, **_kwargs):
        return {"mean_nll": next(validation_nlls)}

    def fake_train(*_args, **kwargs):
        return {
            "mean_nll": 0.9,
            "policy_targets_per_second": 1000.0,
            "gradient_norm_max_pre_clip": 1.0,
            "epoch": kwargs["epoch"],
        }

    def fake_save(path, **kwargs):
        epoch = int(kwargs["counters"]["stage_epoch"])
        saved_epochs.append(epoch)
        path.write_bytes(f"epoch-{epoch}".encode())
        return {"payload_sha256": f"sha-{epoch}", "payload_bytes": path.stat().st_size}

    monkeypatch.setattr(SWEEP, "validate_packed", fake_validate)
    monkeypatch.setattr(SWEEP, "train_epoch_packed", fake_train)
    monkeypatch.setattr(SWEEP, "save_training_checkpoint", fake_save)
    monkeypatch.setattr(
        SWEEP,
        "load_training_checkpoint_model_state",
        lambda *_args, **_kwargs: SimpleNamespace(),
    )

    result = SWEEP._train_stage(
        model=model,
        model_label="3.7m",
        model_config=PolicyConfigV1(max_trainable_parameters=6_000_000),
        stage_name="stage-d-exact-1150",
        materialized_manifest_sha256="a" * 64,
        train_groups=(),
        validation_groups=(),
        output_dir=tmp_path,
        learning_rate=1.25e-5,
        epochs=12,
        minimum_teacher_score=1150.0,
        device=torch.device("cpu"),
        bf16=False,
        maximum_gradient_norm=1.0,
        weight_decay=1e-4,
        early_stopping_patience=3,
        early_stopping_min_delta=0.00025,
    )

    assert result["baseline_validation_mean_nll"] == 1.0
    assert result["best_validation_mean_nll"] == 1.0
    assert result["best_epoch"] == 0
    assert result["epochs_ran"] == 3
    assert result["stopped_early"] is True
    assert saved_epochs == [0]


def test_stage_early_stopping_resets_patience_on_meaningful_improvement(
    monkeypatch, tmp_path
) -> None:
    model = torch.nn.Linear(1, 1)
    validation_nlls = iter((1.0, 0.9998, 0.9996, 1.0000, 1.0001, 1.0002))
    saved_epochs: list[int] = []

    def fake_validate(*_args, **_kwargs):
        return {"mean_nll": next(validation_nlls)}

    def fake_train(*_args, **kwargs):
        return {
            "mean_nll": 0.9,
            "policy_targets_per_second": 1000.0,
            "gradient_norm_max_pre_clip": 1.0,
            "epoch": kwargs["epoch"],
        }

    def fake_save(path, **kwargs):
        epoch = int(kwargs["counters"]["stage_epoch"])
        saved_epochs.append(epoch)
        path.write_bytes(f"epoch-{epoch}".encode())
        return {"payload_sha256": f"sha-{epoch}", "payload_bytes": path.stat().st_size}

    monkeypatch.setattr(SWEEP, "validate_packed", fake_validate)
    monkeypatch.setattr(SWEEP, "train_epoch_packed", fake_train)
    monkeypatch.setattr(SWEEP, "save_training_checkpoint", fake_save)
    monkeypatch.setattr(
        SWEEP,
        "load_training_checkpoint_model_state",
        lambda *_args, **_kwargs: SimpleNamespace(),
    )

    result = SWEEP._train_stage(
        model=model,
        model_label="3.7m",
        model_config=PolicyConfigV1(max_trainable_parameters=6_000_000),
        stage_name="stage-d-exact-1150",
        materialized_manifest_sha256="b" * 64,
        train_groups=(),
        validation_groups=(),
        output_dir=tmp_path,
        learning_rate=1.25e-5,
        epochs=12,
        minimum_teacher_score=1150.0,
        device=torch.device("cpu"),
        bf16=False,
        maximum_gradient_norm=1.0,
        weight_decay=1e-4,
        early_stopping_patience=3,
        early_stopping_min_delta=0.00025,
    )

    assert result["best_validation_mean_nll"] == 0.9996
    assert result["best_epoch"] == 2
    assert result["epochs_ran"] == 5
    assert result["stopped_early"] is True
    assert saved_epochs == [0, 2]
