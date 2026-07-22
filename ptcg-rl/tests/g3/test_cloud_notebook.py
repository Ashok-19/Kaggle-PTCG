from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ptcg_rl.g3.cloud_notebook import (
    NotebookContractError,
    build_kaggle_notebook,
    validate_notebook_contract,
)


def test_single_notebook_is_thin_private_cpu_launcher(tmp_path: Path) -> None:
    output = tmp_path / "kptcg-g3a-cloud-correctness-v1.ipynb"
    record = build_kaggle_notebook(
        output,
        source_commit="1" * 40,
        source_tree="2" * 40,
        bundle_name="g3a-cloud-source-v1.bundle",
        bundle_sha256="3" * 64,
        plan_name="g3a-cloud-plan-v1.json",
        plan_sha256="4" * 64,
        input_manifest_name="g3a-cloud-input-manifest-v1.json",
        input_manifest_sha256="5" * 64,
    )
    assert record["bytes"] == output.stat().st_size
    assert record["sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    notebook = json.loads(output.read_text(encoding="utf-8"))
    validate_notebook_contract(notebook)
    code_cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
    assert len(code_cells) == 1
    source = "".join(code_cells[0]["source"])
    assert "enable_internet" not in source
    assert "g3a_cloud_correctness.py" in source
    assert "--authorize-training" in source
    assert "KPTCG_G3A_TRAINING_APPROVED" in source
    assert "kaggle/working" in source
    assert "urllib.error.HTTPError" in source
    assert "urllib.error.URLError" in source


def test_notebook_contract_rejects_outputs_or_extra_code_cells(tmp_path: Path) -> None:
    output = tmp_path / "notebook.ipynb"
    build_kaggle_notebook(
        output,
        source_commit="1" * 40,
        source_tree="2" * 40,
        bundle_name="bundle",
        bundle_sha256="3" * 64,
        plan_name="plan",
        plan_sha256="4" * 64,
        input_manifest_name="manifest",
        input_manifest_sha256="5" * 64,
    )
    notebook = json.loads(output.read_text(encoding="utf-8"))
    notebook["cells"][1]["outputs"] = [{"output_type": "stream", "name": "stdout", "text": ["x"]}]
    with pytest.raises(NotebookContractError, match="output"):
        validate_notebook_contract(notebook)

    notebook["cells"][1]["outputs"] = []
    notebook["cells"].append(dict(notebook["cells"][1]))
    with pytest.raises(NotebookContractError, match="one code cell"):
        validate_notebook_contract(notebook)
