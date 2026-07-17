from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from ptcg_rl.assets import AssetError, import_assets, safe_extract, verify_assets


pytestmark = pytest.mark.unit


def test_safe_extract_rejects_traversal(tmp_path: Path) -> None:
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../escape", "no")
    with pytest.raises(AssetError, match="unsafe archive member"):
        safe_extract(archive, tmp_path / "out")


def test_import_and_verify_minimal_assets(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    official = tmp_path / "official"
    sample = tmp_path / "sample"
    research = tmp_path / "research"
    repo.mkdir()
    official.mkdir()
    sample.mkdir()
    research.mkdir()
    for name, content in {
        "libcg.so": b"engine",
        "EN_Card_Data.csv": b"Card ID,Card Name\n1,Energy\n",
        "LicenseRef-PTCG-ABC-Competition-Use-Only.txt": b"competition only",
        "deck.csv": b"1\n" * 60,
        "api.py": b"# wrapper\n",
    }.items():
        (official / name).write_bytes(content)
    (sample / "agent.ipynb").write_text("{}")
    (research / "notes.md").write_text("secondary")

    result = import_assets(repo, official, sample, research)

    assert result["assets"]["official"]["file_count"] == 5
    assert verify_assets(repo) == []
    assert "source_path" not in (repo / "asset_hashes.redacted.json").read_text()
    assert json.loads((repo / "private" / "assets.lock.json").read_text())["assets"]["official"]["source_path"] == str(official)

