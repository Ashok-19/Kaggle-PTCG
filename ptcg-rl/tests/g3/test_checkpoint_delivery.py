from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from scripts.e01_verify_extracted_checkpoint_delivery import (
    CheckpointDeliveryError,
    PACKAGE_SHA256,
    reconstruct_checkpoint,
    sha256_bytes,
)


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "private/g2/checkpoint-v1/g2-policy-checkpoint-v1.zip"


def _extract_members(destination: Path) -> None:
    destination.mkdir()
    with zipfile.ZipFile(PACKAGE, "r") as archive:
        archive.extractall(destination)


def test_exact_extracted_checkpoint_reconstructs_original_package(tmp_path: Path) -> None:
    members = tmp_path / "members"
    _extract_members(members)
    output = tmp_path / "reconstructed.zip"

    report = reconstruct_checkpoint(members, output)

    assert output.read_bytes() == PACKAGE.read_bytes()
    assert sha256_bytes(output.read_bytes()) == PACKAGE_SHA256
    assert report["status"] == "PASS_EXACT_PACKAGE_RECONSTRUCTED"
    assert report["member_files"] == 4
    assert report["training"] is False


def test_extracted_checkpoint_rejects_extra_file(tmp_path: Path) -> None:
    members = tmp_path / "members"
    _extract_members(members)
    (members / "unexpected.txt").write_text("unexpected", encoding="utf-8")

    with pytest.raises(CheckpointDeliveryError, match="filename set differs"):
        reconstruct_checkpoint(members, tmp_path / "reconstructed.zip")


def test_extracted_checkpoint_rejects_member_hash_mismatch(tmp_path: Path) -> None:
    members = tmp_path / "members"
    _extract_members(members)
    state = members / "state-v1.bin"
    raw = bytearray(state.read_bytes())
    raw[0] ^= 0x01
    state.write_bytes(raw)

    with pytest.raises(CheckpointDeliveryError, match="SHA-256 differs"):
        reconstruct_checkpoint(members, tmp_path / "reconstructed.zip")
