from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType


def load_freezer(root: Path) -> ModuleType:
    path = root / "scripts/kaggle/freeze_g3a_cloud_plan.py"
    spec = importlib.util.spec_from_file_location("freeze_g3a_cloud_plan", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_bundle_is_nonempty_deterministic_and_head_bound(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    repository = root.parent
    freezer = load_freezer(root)
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repository, text=True
    ).strip()
    output = tmp_path / "source.bundle"
    record = freezer.build_bundle(repository, output, head)
    assert output.is_file()
    assert output.stat().st_size == record["bytes"] > 0
    listed = subprocess.check_output(
        ["git", "bundle", "list-heads", str(output)],
        cwd=repository,
        text=True,
    )
    assert head in listed
    verification = subprocess.run(
        ["git", "bundle", "verify", str(output)],
        cwd=repository,
        check=False,
        capture_output=True,
        text=True,
    )
    assert verification.returncode == 0, verification.stderr


def test_freezer_edge_case_matrix_references_existing_files() -> None:
    root = Path(__file__).resolve().parents[2]
    freezer = load_freezer(root)
    missing = sorted(
        {
            path
            for category in freezer.EDGE_CASE_MATRIX.values()
            for paths in category.values()
            for path in paths
            if not (root / path).is_file()
        }
    )
    assert missing == []
