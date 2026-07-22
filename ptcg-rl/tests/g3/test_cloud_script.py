from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_cloud_run_requires_both_cli_and_environment_authorization(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    output = tmp_path / "output"
    completed = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/g3a_cloud_correctness.py"),
            "run",
            "--root",
            str(root),
            "--plan",
            str(tmp_path / "missing-plan.json"),
            "--input-manifest",
            str(tmp_path / "missing-manifest.json"),
            "--output",
            str(output),
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert "authorization" in completed.stderr.lower()
    assert not output.exists()
    assert (tmp_path / "g3a-cloud-failure-capsule-v1.json").is_file()


def test_cloud_run_rejects_environment_only_authorization(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    output = tmp_path / "output"
    completed = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/g3a_cloud_correctness.py"),
            "run",
            "--root",
            str(root),
            "--plan",
            str(tmp_path / "missing-plan.json"),
            "--input-manifest",
            str(tmp_path / "missing-manifest.json"),
            "--output",
            str(output),
        ],
        cwd=root,
        env={"KPTCG_G3A_TRAINING_APPROVED": "YES"},
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 2
    assert "authorization" in completed.stderr.lower()
    assert not output.exists()
    assert (tmp_path / "g3a-cloud-failure-capsule-v1.json").is_file()
