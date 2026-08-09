"""No-data regressions for the fresh Scale256 split contract."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from train_scale256 import FAMILIES, TARGET_SPLITS, _allocate_quotas  # noqa: E402


def test_scale256_quota_allocator_is_exact_and_stratified() -> None:
    keys = [
        (family, window, slot)
        for family in FAMILIES
        for window in ("EARLY", "MID")
        for slot in (0, 1)
    ]
    strata = {key: [None] * (11 if index < 16 else 10) for index, key in enumerate(keys)}
    quotas = _allocate_quotas(strata)
    assert sum(values[split] for values in quotas.values() for split in ("train", "tune", "test")) == 256
    assert {
        split: sum(values[split] for values in quotas.values())
        for split in TARGET_SPLITS
    } == TARGET_SPLITS
    assert all(sum(values.values()) == len(strata[key]) for key, values in quotas.items())


def test_scale256_selection_is_tune_only_and_test_has_one_score_boundary() -> None:
    runner = Path(__file__).with_name("train_scale256.py").read_text(encoding="utf-8")
    assert "RUN_ROOT" not in runner
    assert "DATASET_ROOT" not in runner
    assert runner.index("seed_results =") < runner.index("selected = min(")
    assert runner.index("selected = min(") < runner.index("selected_test_scores")
    assert runner.count("_cpu_p95_ms(restored, test_batch)") == 1
    trainer = Path(__file__).with_name("train_scale64.py").read_text(encoding="utf-8")
    start = trainer.index("def _train_one_seed(")
    end = trainer.index("\ndef _bc_action_logits", start)
    train_body = trainer[start:end]
    assert "test_batch" not in train_body
    assert "test_records" not in train_body
    assert "test_metrics" not in train_body
