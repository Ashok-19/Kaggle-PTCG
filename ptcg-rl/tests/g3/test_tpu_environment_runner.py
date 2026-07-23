from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/kaggle/g3b_tpu_environment_qualification.py"


def load_module():
    spec = importlib.util.spec_from_file_location("g3b_tpu_environment_qualification", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_worker_sweep_and_contract_defaults_are_frozen() -> None:
    module = load_module()
    assert module.DEFAULT_WORKERS == (16, 32, 48, 64, 80, 96)
    assert module.SESSION_HARD_LIMIT_SECONDS == 43_200
    assert module.INTERNAL_CHUNK_LIMIT_SECONDS == 28_800
    assert module.T4X2_BASELINE_CHOICES_PER_SECOND == pytest.approx(228.59829116666842)


def test_worker_parser_rejects_invalid_and_duplicate_counts() -> None:
    module = load_module()
    assert module.parse_workers("16,32,96") == (16, 32, 96)
    with pytest.raises(Exception, match="positive"):
        module.parse_workers("16,0")
    with pytest.raises(Exception, match="duplicates"):
        module.parse_workers("16,16")


def test_embedded_accelerator_probes_preserve_environment_only_scope() -> None:
    module = load_module()
    assert 'backend != "tpu"' in module.JAX_PROBE
    assert 'len(devices) != 8' in module.JAX_PROBE
    assert '"synthetic_tensors_only": True' in module.JAX_PROBE
    assert 'expected_all_reduce_sum": 36.0' in module.TORCH_XLA_MULTI_PROBE
    assert "torch_xla.launch(worker, args=())" in module.TORCH_XLA_MULTI_PROBE
    assert "nprocs=8" not in module.TORCH_XLA_MULTI_PROBE
    assert '"meaningful_training_choices": 0' in module.TORCH_XLA_PROBE
    assert '"optimizer_created": False' in module.TORCH_XLA_PROBE
    assert ".step()" not in module.TORCH_XLA_PROBE


def test_reliability_branch_uses_observed_game_count() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'review.get("observed_games", 0)' in text
    assert 'review.get("games", 0)' not in text


def test_runner_fails_closed_and_does_not_claim_competence() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "output directory collision" in text
    assert '"policy_competence_established": False' in text
    assert '"ppo_training_throughput_established": False' in text
    assert '"training_authorized": False' in text
    assert '"submission_authorized": False' in text
    assert '"external_service_mutated_by_runner": False' in text
