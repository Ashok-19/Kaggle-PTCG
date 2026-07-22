from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_cloud_run_has_no_authorization_preflight(tmp_path: Path) -> None:
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
    assert "cannot read cloud plan" in completed.stderr.lower()
    assert "authorization" not in completed.stderr.lower()
    assert not output.exists()
    assert (tmp_path / "g3a-cloud-failure-capsule-v1.json").is_file()


def test_cloud_cli_exposes_no_authorization_flag() -> None:
    root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/g3a_cloud_correctness.py"),
            "run",
            "--help",
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert "--authorize-training" not in completed.stdout
    assert "KPTCG_G3A_TRAINING_APPROVED" not in completed.stdout
