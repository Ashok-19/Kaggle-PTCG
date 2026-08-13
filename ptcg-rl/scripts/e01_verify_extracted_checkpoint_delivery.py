from __future__ import annotations

import argparse
import hashlib
import json
import stat
import zipfile
from pathlib import Path
from typing import Any


PACKAGE_BYTES = 5_429_190
PACKAGE_SHA256 = "4dfba2adb9f97607cfa5dabadba075236bb7aae51eafab264584e947feae3827"
ARCHIVE_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
ARCHIVE_MODE = stat.S_IFREG | 0o600
MEMBERS: tuple[dict[str, Any], ...] = (
    {
        "name": "card-table-v1.json",
        "bytes": 1_056_442,
        "sha256": "5fc3a1cf31dd5f4b1b3542fc1baa91fe2b68b772cb5748f50f0f75c9a74f7714",
    },
    {
        "name": "manifest.json",
        "bytes": 26_493,
        "sha256": "1185c97d1fca8cb795e2c5f84f5d0a915cf41fac242aefed888b4e0dd84b267c",
    },
    {
        "name": "reference-v1.json",
        "bytes": 24_378,
        "sha256": "cf0fe3bb2e47ff3644f6ea2a8647ca47472e698e1fedd2f14f9156de063bb1c3",
    },
    {
        "name": "state-v1.bin",
        "bytes": 4_321_431,
        "sha256": "bb91fa17ea74101cc70e02b6ef85cefe8f90e096478bf63e1cc63384c23f3e5c",
    },
)


class CheckpointDeliveryError(ValueError):
    """Raised when extracted checkpoint delivery differs from the frozen package."""


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _read_members(input_dir: Path) -> dict[str, bytes]:
    if not input_dir.is_dir() or input_dir.is_symlink():
        raise CheckpointDeliveryError("checkpoint member input must be a real directory")
    expected_names = {str(item["name"]) for item in MEMBERS}
    observed_names = {item.name for item in input_dir.iterdir()}
    if observed_names != expected_names:
        raise CheckpointDeliveryError("checkpoint member filename set differs")
    entries: dict[str, bytes] = {}
    for record in MEMBERS:
        name = str(record["name"])
        path = input_dir / name
        if not path.is_file() or path.is_symlink():
            raise CheckpointDeliveryError(f"checkpoint member is not a real file: {name}")
        raw = path.read_bytes()
        if len(raw) != int(record["bytes"]):
            raise CheckpointDeliveryError(f"checkpoint member byte count differs: {name}")
        if sha256_bytes(raw) != str(record["sha256"]):
            raise CheckpointDeliveryError(f"checkpoint member SHA-256 differs: {name}")
        entries[name] = raw
    return entries


def reconstruct_checkpoint(input_dir: Path, output_zip: Path) -> dict[str, Any]:
    entries = _read_members(input_dir)
    if output_zip.exists() or output_zip.is_symlink():
        raise CheckpointDeliveryError("checkpoint reconstruction output already exists")
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_zip.with_suffix(output_zip.suffix + ".partial")
    if temporary.exists() or temporary.is_symlink():
        raise CheckpointDeliveryError("checkpoint reconstruction partial output already exists")
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
            for name in sorted(entries):
                info = zipfile.ZipInfo(name, date_time=ARCHIVE_TIMESTAMP)
                info.compress_type = zipfile.ZIP_STORED
                info.create_system = 3
                info.external_attr = ARCHIVE_MODE << 16
                info.internal_attr = 0
                info.flag_bits = 0
                archive.writestr(info, entries[name], compress_type=zipfile.ZIP_STORED)
        raw = temporary.read_bytes()
        if len(raw) != PACKAGE_BYTES:
            raise CheckpointDeliveryError("reconstructed checkpoint package byte count differs")
        if sha256_bytes(raw) != PACKAGE_SHA256:
            raise CheckpointDeliveryError("reconstructed checkpoint package SHA-256 differs")
        temporary.replace(output_zip)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {
        "schema_version": 1,
        "record_id": "e01-extracted-checkpoint-delivery-verification-v1",
        "status": "PASS_EXACT_PACKAGE_RECONSTRUCTED",
        "input_directory": input_dir.as_posix(),
        "output_package": output_zip.as_posix(),
        "members": [dict(item) for item in MEMBERS],
        "member_files": len(MEMBERS),
        "member_bytes": sum(int(item["bytes"]) for item in MEMBERS),
        "package_bytes": PACKAGE_BYTES,
        "package_sha256": PACKAGE_SHA256,
        "replay_bodies": 0,
        "agent_logs": 0,
        "labels": 0,
        "optimizer_steps": 0,
        "training": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify four extracted G2 checkpoint members and reconstruct the exact sealed ZIP."
    )
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-zip", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = reconstruct_checkpoint(args.input_dir.resolve(), args.output_zip.resolve())
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report is not None:
        report_path = args.report.resolve()
        if report_path.exists() or report_path.is_symlink():
            raise CheckpointDeliveryError("checkpoint verification report already exists")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
