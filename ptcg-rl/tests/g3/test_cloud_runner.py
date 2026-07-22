from __future__ import annotations

from pathlib import Path

import pytest
import torch

from ptcg_rl.g3.cloud_runner import (
    CloudRunError,
    StreamTrainingSpecV1,
    run_training_stream,
)
from ptcg_rl.g3.ppo import LocalExecutionLimitsV1


def spec(total_choices: int = 128) -> StreamTrainingSpecV1:
    return StreamTrainingSpecV1(
        task_id="recurrent-cue-v1",
        seed=1197953491,
        stateless=False,
        total_non_forced_choices=total_choices,
        choices_per_update=32,
        ppo_epochs=2,
        learning_rate=0.005,
        adam_epsilon=1e-5,
        clip_coefficient=0.2,
        value_clip_coefficient=0.2,
        value_coefficient=0.5,
        entropy_coefficient=0.01,
        maximum_gradient_norm=0.5,
        checkpoint_cadence_choices=64,
        checkpoint_cadence_wall_seconds=60,
        evaluation_cadence_choices=64,
        intentional_interrupt_after_choices=64,
    )


def limits() -> LocalExecutionLimitsV1:
    return LocalExecutionLimitsV1(
        max_cpu_threads=2,
        max_worker_processes=1,
        max_non_forced_choices=512,
        max_wall_seconds=120,
    )


def test_interrupted_fresh_restore_matches_uninterrupted(tmp_path: Path) -> None:
    uninterrupted = run_training_stream(
        spec=spec(),
        output_dir=tmp_path / "uninterrupted",
        limits=limits(),
        interrupt=False,
    )
    interrupted = run_training_stream(
        spec=spec(),
        output_dir=tmp_path / "resumed",
        limits=limits(),
        interrupt=True,
    )
    assert interrupted["status"] == "INTERRUPTED"
    checkpoint = Path(interrupted["checkpoint_path"])
    assert checkpoint.is_file()

    resumed = run_training_stream(
        spec=spec(),
        output_dir=tmp_path / "resumed",
        limits=limits(),
        resume_from=checkpoint,
        interrupt=False,
    )
    assert resumed["status"] == "SUCCEEDED"
    assert resumed["choices"] == 128
    assert resumed["updates"] == 4
    assert resumed["final_model_sha256"] == uninterrupted["final_model_sha256"]
    assert resumed["fixed_evaluation_sha256"] == uninterrupted["fixed_evaluation_sha256"]
    assert resumed["resume"]["fixed_evaluation_exact"] is True
    assert set(resumed["resume"]["restored_rng_states"]) == {"python", "numpy", "torch_cpu"}


def test_resume_rejects_corrupt_checkpoint(tmp_path: Path) -> None:
    interrupted = run_training_stream(
        spec=spec(),
        output_dir=tmp_path,
        limits=limits(),
        interrupt=True,
    )
    checkpoint = Path(interrupted["checkpoint_path"])
    checkpoint.write_bytes(checkpoint.read_bytes()[:-16])
    with pytest.raises(CloudRunError, match="checkpoint"):
        run_training_stream(
            spec=spec(),
            output_dir=tmp_path,
            limits=limits(),
            resume_from=checkpoint,
            interrupt=False,
        )


def test_resume_rejects_wrong_budget_and_duplicate_output(tmp_path: Path) -> None:
    interrupted = run_training_stream(
        spec=spec(),
        output_dir=tmp_path,
        limits=limits(),
        interrupt=True,
    )
    checkpoint = Path(interrupted["checkpoint_path"])
    with pytest.raises(CloudRunError, match="spec"):
        run_training_stream(
            spec=spec(total_choices=160),
            output_dir=tmp_path,
            limits=limits(),
            resume_from=checkpoint,
            interrupt=False,
        )

    collision = tmp_path / "collision"
    collision.mkdir()
    (collision / "stream-result.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(CloudRunError, match="collision"):
        run_training_stream(spec=spec(), output_dir=collision, limits=limits(), interrupt=False)


def test_stream_rejects_gpu_and_invalid_interruption_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    invalid = spec()
    object.__setattr__(invalid, "intentional_interrupt_after_choices", 65)
    with pytest.raises(CloudRunError, match="interrupt"):
        run_training_stream(
            spec=invalid,
            output_dir=tmp_path / "invalid-interrupt",
            limits=limits(),
            interrupt=True,
        )

    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    with pytest.raises(CloudRunError, match="GPU"):
        run_training_stream(
            spec=spec(),
            output_dir=tmp_path / "gpu-visible",
            limits=limits(),
            interrupt=False,
        )
