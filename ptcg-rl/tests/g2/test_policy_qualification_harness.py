from __future__ import annotations

import ast
import json
import runpy
from pathlib import Path


def test_policy_qualification_harness_is_bounded_and_has_no_optimizer() -> None:
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "kaggle" / "g2_policy_qualification.py"
    tree = ast.parse(script.read_text(encoding="utf-8"))
    calls = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "backward" in calls
    assert "step" not in calls
    text = script.read_text(encoding="utf-8").lower()
    assert "torch.optim" not in text
    assert all(
        node.id.lower() != "optimizer"
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
    )
    assert "samples=200" in text
    assert "samples=100" in text
    main_text = text[text.index("def main() -> none:") :]
    assert main_text.index("model.eval()") < main_text.index("with torch.inference_mode():")
    assert main_text.index("model.train()") < main_text.index("gradient_loss.backward()")
    assert main_text.rindex("model.eval()") < main_text.index("single_latency = benchmark")
    assert '"gradient_pass_training_mode"' in main_text
    assert '"latency_pass_evaluation_mode"' in main_text


def test_policy_qualification_fixture_matches_the_sealed_g1_contract() -> None:
    root = Path(__file__).resolve().parents[2]
    namespace = runpy.run_path(
        str(root / "scripts" / "kaggle" / "g2_policy_qualification.py")
    )
    small, large, card = namespace["projected_decisions"]()
    assert len(small.model.option_available_mask) == 5
    assert len(large.model.option_available_mask) == 70
    assert len(card.model.option_available_mask) == 1


def test_policy_qualification_serializes_masked_infinities_without_allowing_nan() -> None:
    root = Path(__file__).resolve().parents[2]
    namespace = runpy.run_path(
        str(root / "scripts" / "kaggle" / "g2_policy_qualification.py")
    )
    torch = namespace["torch"]
    tensor_values = namespace["tensor_values"]
    assert tensor_values(torch.tensor([1.5, float("-inf"), float("inf")])) == [
        1.5,
        "-inf",
        "inf",
    ]
    try:
        tensor_values(torch.tensor([float("nan")]))
    except RuntimeError as error:
        assert "NaN" in str(error)
    else:
        raise AssertionError("NaN must fail qualification serialization")


def test_cpu_and_gpu_qualification_configs_preserve_private_no_training_boundary() -> None:
    root = Path(__file__).resolve().parents[2]
    cpu = json.loads(
        (root / "configs" / "kaggle" / "g2_policy_cpu_qualification.json").read_text(
            encoding="utf-8"
        )
    )
    gpu = json.loads(
        (root / "configs" / "kaggle" / "g2_policy_gpu_qualification.json").read_text(
            encoding="utf-8"
        )
    )
    for config in (cpu, gpu):
        assert config["private"] is True
        assert config["internet"] is False
        assert config["tpu"] is False
        assert config["timeout_seconds"] == 900
        assert config["no_training"] is True
    assert cpu["gpu"] is False
    assert gpu["gpu"] is True
    assert gpu["parity_absolute_tolerance"] == 0.00001
    assert gpu["parity_relative_tolerance"] == 0.00001


def test_bundle_builder_uses_an_explicit_source_allowlist() -> None:
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "kaggle" / "build_g2_qualification_bundle.py"
    tree = ast.parse(script.read_text(encoding="utf-8"))
    text = script.read_text(encoding="utf-8")
    assert "TRACKED_FILES" in text
    assert "PRIVATE_TABLE" in text
    assert "--untracked-files=no" in text
    assert "qualification bundle source files differ from HEAD" in text
    assert "rglob" not in text
    assert "glob(" not in text
    assert any(isinstance(node, ast.Tuple) for node in ast.walk(tree))
