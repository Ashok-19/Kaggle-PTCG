from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import zipfile
from datetime import UTC, datetime
from pathlib import Path

TRACKED_FILES = (
    "src/ptcg_rl/__init__.py",
    "src/ptcg_rl/g1/__init__.py",
    "src/ptcg_rl/g1/models.py",
    "src/ptcg_rl/g1/semantic.py",
    "src/ptcg_rl/g2/__init__.py",
    "src/ptcg_rl/g2/card_table.py",
    "src/ptcg_rl/g2/models.py",
    "src/ptcg_rl/g2/projection.py",
    "src/ptcg_rl/g2/network.py",
    "scripts/kaggle/g2_policy_qualification.py",
)
PRIVATE_TABLE = "private/g2/card-table-v1.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.out if args.out.is_absolute() else root / args.out
    manifest_path = args.manifest if args.manifest.is_absolute() else root / args.manifest
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    tracked = subprocess.check_output(
        ["git", "ls-files", *TRACKED_FILES], cwd=root, text=True
    ).splitlines()
    if sorted(tracked) != sorted(TRACKED_FILES):
        raise SystemExit("qualification bundle source list is not fully tracked")
    dirty = subprocess.check_output(
        [
            "git",
            "status",
            "--porcelain",
            "--untracked-files=no",
            "--",
            *TRACKED_FILES,
        ],
        cwd=root,
        text=True,
    ).splitlines()
    if dirty:
        raise SystemExit("qualification bundle source files differ from HEAD")
    paths = [root / relative for relative in TRACKED_FILES]
    private_table = root / PRIVATE_TABLE
    if not private_table.is_file():
        raise SystemExit(f"missing private table: {PRIVATE_TABLE}")
    paths.append(private_table)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".partial")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in paths:
            relative = path.relative_to(root).as_posix()
            archive_name = "card-table-v1.json" if relative == PRIVATE_TABLE else relative
            info = zipfile.ZipInfo(archive_name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, path.read_bytes())
    temporary.replace(output)
    records = [
        {
            "source_path": path.relative_to(root).as_posix(),
            "archive_path": "card-table-v1.json"
            if path == private_table
            else path.relative_to(root).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
            "tracked": path != private_table,
        }
        for path in paths
    ]
    manifest = {
        "schema_version": 1,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "source_commit": head,
        "bundle_path": str(output.relative_to(root)),
        "bundle_bytes": output.stat().st_size,
        "bundle_sha256": sha256(output),
        "files": records,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
