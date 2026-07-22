from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


class NotebookContractError(ValueError):
    pass


def _source_lines(source: str) -> list[str]:
    return source.splitlines(keepends=True)


def validate_notebook_contract(value: Mapping[str, Any]) -> None:
    if value.get("nbformat") != 4 or value.get("nbformat_minor") != 5:
        raise NotebookContractError("notebook format differs")
    cells = value.get("cells")
    if not isinstance(cells, list):
        raise NotebookContractError("notebook cells must be a list")
    code_cells = [cell for cell in cells if isinstance(cell, Mapping) and cell.get("cell_type") == "code"]
    if len(code_cells) != 1:
        raise NotebookContractError("notebook must contain exactly one code cell")
    for cell in cells:
        if not isinstance(cell, Mapping):
            raise NotebookContractError("notebook cell must be an object")
        if cell.get("cell_type") == "code":
            if cell.get("outputs") != [] or cell.get("execution_count") is not None:
                raise NotebookContractError("notebook code cell must not retain output or execution state")
    code = "".join(code_cells[0].get("source", []))
    required = (
        "g3a_cloud_correctness.py",
        "/kaggle/input",
        "/kaggle/working",
        "[\"git\", \"clone\"",
        "sha256",
    )
    if any(token not in code for token in required):
        raise NotebookContractError("notebook launcher is missing a required fail-closed operation")
    forbidden = (
        "KPTCG_G3A_TRAINING_APPROVED",
        "--authorize-training",
        "urllib.request",
        "urlopen(",
    )
    if any(token in code for token in forbidden):
        raise NotebookContractError("notebook launcher retains a removed preflight check")


def build_kaggle_notebook(
    output: Path,
    *,
    source_commit: str,
    source_tree: str,
    bundle_name: str,
    bundle_sha256: str,
    plan_name: str,
    plan_sha256: str,
    input_manifest_name: str,
    input_manifest_sha256: str,
) -> dict[str, Any]:
    markdown = """# KPTCG G3a Cloud Correctness v1

Import this notebook into a private Kaggle CPU session, attach exactly the specified private input dataset version, and run all cells without editing. No Kaggle secret, environment variable, or network probe is required. The launcher verifies the exact source bundle, source commit/tree, plan and input-manifest hashes, clean checkout, CPU/thread topology, output collision policy, fresh-process resume receipts, and final independent review. It performs no submission, no Pokémon self-play, and no policy-strength evaluation.
"""
    code = f'''from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

SOURCE_COMMIT = "{source_commit}"
SOURCE_TREE = "{source_tree}"
BUNDLE_NAME = "{bundle_name}"
BUNDLE_SHA256 = "{bundle_sha256}"
PLAN_NAME = "{plan_name}"
PLAN_SHA256 = "{plan_sha256}"
INPUT_MANIFEST_NAME = "{input_manifest_name}"
INPUT_MANIFEST_SHA256 = "{input_manifest_sha256}"
INPUT_ROOT = Path("/kaggle/input")
WORK_ROOT = Path("/kaggle/working/kptcg-g3a-cloud-correctness-v1")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def unique_input(name: str) -> Path:
    matches = sorted(path for path in INPUT_ROOT.rglob(name) if path.is_file())
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one {{name}}, found {{len(matches)}}")
    return matches[0]


if WORK_ROOT.exists():
    raise RuntimeError(f"output directory collision: {{WORK_ROOT}}")
for name, expected in (
    (BUNDLE_NAME, BUNDLE_SHA256),
    (PLAN_NAME, PLAN_SHA256),
    (INPUT_MANIFEST_NAME, INPUT_MANIFEST_SHA256),
):
    path = unique_input(name)
    if sha256(path) != expected:
        raise RuntimeError(f"input SHA-256 differs: {{name}}")

WORK_ROOT.mkdir(parents=True)
repo = WORK_ROOT / "repo"
bundle = unique_input(BUNDLE_NAME)
subprocess.run(["git", "clone", "--quiet", str(bundle), str(repo)], check=True)
head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
tree = subprocess.check_output(["git", "rev-parse", "HEAD^{{tree}}"], cwd=repo, text=True).strip()
status = subprocess.check_output(["git", "status", "--porcelain"], cwd=repo, text=True)
if head != SOURCE_COMMIT or tree != SOURCE_TREE or status:
    raise RuntimeError("offline source identity or cleanliness differs")
project = repo / "ptcg-rl"
plan = unique_input(PLAN_NAME)
manifest = unique_input(INPUT_MANIFEST_NAME)
command = [
    sys.executable,
    str(project / "scripts/g3a_cloud_correctness.py"),
    "run",
    "--root",
    str(project),
    "--plan",
    str(plan),
    "--input-manifest",
    str(manifest),
    "--output",
    str(WORK_ROOT / "output"),
]
environment = dict(os.environ)
environment.update({{
    "PYTHONPATH": str(project / "src"),
    "OMP_NUM_THREADS": "2",
    "MKL_NUM_THREADS": "2",
    "OPENBLAS_NUM_THREADS": "1",
    "NUMEXPR_NUM_THREADS": "1",
}})
completed = subprocess.run(command, cwd=project, env=environment, check=False)
if completed.returncode:
    raise RuntimeError(f"G3a cloud correctness runner failed with {{completed.returncode}}")
'''
    notebook = {
        "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": _source_lines(markdown)},
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": _source_lines(code),
            },
        ],
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.12"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    validate_notebook_contract(notebook)
    raw = (json.dumps(notebook, indent=1, sort_keys=True, ensure_ascii=True) + "\n").encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(raw)
    return {"path": output.as_posix(), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
