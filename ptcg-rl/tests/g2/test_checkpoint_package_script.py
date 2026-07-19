from __future__ import annotations

import ast
import runpy
from pathlib import Path


def test_checkpoint_qualification_script_has_explicit_source_and_parity_allowlists() -> None:
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts/g2_checkpoint_package.py"
    namespace = runpy.run_path(str(script))
    source_files = namespace["SOURCE_FILES"]
    parity_files = namespace["MODEL_PARITY_FILES"]
    assert isinstance(source_files, tuple)
    assert isinstance(parity_files, tuple)
    assert len(source_files) == len(set(source_files))
    assert len(parity_files) == len(set(parity_files))
    assert set(parity_files) < set(source_files)
    assert source_files == tuple(sorted(source_files))
    assert parity_files == tuple(sorted(parity_files))
    assert "src/ptcg_rl/g2/checkpoint.py" in source_files
    assert "scripts/g2_checkpoint_package.py" in source_files
    assert "scripts/kaggle/g2_policy_qualification.py" in parity_files
    assert "private/g2/card-table-v1.json" not in source_files
    assert "reports/evaluations/g2-policy-cpu-gpu-parity-v4.json" not in source_files


def test_checkpoint_qualification_script_has_no_training_pickle_or_broad_discovery() -> None:
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts/g2_checkpoint_package.py"
    text = script.read_text(encoding="utf-8")
    lower = text.lower()
    tree = ast.parse(text)
    forbidden_names = {
        "backward",
        "step",
        "save",
        "load",
        "rglob",
        "glob",
    }
    calls = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            function = node.func
            if isinstance(function, ast.Attribute):
                calls.add(function.attr)
            elif isinstance(function, ast.Name):
                calls.add(function.id)
    assert "backward" not in calls
    assert "step" not in calls
    assert "rglob" not in calls
    assert "glob" not in calls
    assert "torch.optim" not in lower
    assert "torch.save" not in lower
    assert "torch.load" not in lower
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert "pickle" not in imported_modules
    assert "--untracked-files=all" in text
    assert "git\", \"show" in text
    assert 'git(root, "rev-parse", "--show-prefix")' in text
    assert 'object_path = f"{repository_prefix}{relative}"' in text
    assert "TemporaryDirectory" in text
    assert "PYTHONPATH" in text
    assert "model_source_files_unchanged" in text
    assert not (forbidden_names & {"backward", "step", "rglob", "glob"} & calls)


def test_checkpoint_qualification_verify_command_requires_source_and_reference_checks() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / "scripts/g2_checkpoint_package.py").read_text(encoding="utf-8")
    verify_text = text[text.index("def verify_command") : text.index("def isolated_verify")]
    assert "load_checkpoint_package" in verify_text
    assert "source_root=root" in verify_text
    assert "verify_checkpoint_reference" in verify_text
    assert "verify_source_tree" in verify_text
    assert "module_origins" in verify_text
    assert '"optimizer_created": False' in verify_text
    assert '"training_loop_ran": False' in verify_text
    assert '"pickle_used": False' in verify_text


def test_checkpoint_qualification_builds_twice_and_compares_exact_bytes() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / "scripts/g2_checkpoint_package.py").read_text(encoding="utf-8")
    qualify_text = text[text.index("def qualify_command") : text.index("def parser")]
    assert qualify_text.count("build_checkpoint_package(") == 2
    assert "dict(reversed(list(source_files.items())))" in qualify_text
    assert "output.read_bytes() != duplicate.read_bytes()" in qualify_text
    assert "duplicate_build_match\": True" in qualify_text
    assert "isolated_verify(" in qualify_text
    assert '"kaggle_run_performed": False' in qualify_text
