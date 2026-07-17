from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any


class AssetError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_symlink():
            raise AssetError(f"symlink is not allowed: {path.relative_to(root)}")
        if path.is_file():
            files.append(path)
        elif not path.is_dir():
            raise AssetError(f"special file is not allowed: {path.relative_to(root)}")
    return sorted(files, key=lambda path: path.relative_to(root).as_posix())


def tree_manifest(root: Path) -> dict[str, dict[str, Any]]:
    return {
        path.relative_to(root).as_posix(): {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in _files(root)
    }


def tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for relative, item in tree_manifest(root).items():
        digest.update(f"{relative}\0{item['bytes']}\0{item['sha256']}\n".encode())
    return digest.hexdigest()


def _validate_member(info: zipfile.ZipInfo, seen: set[str]) -> PurePosixPath:
    if "\\" in info.filename or "\0" in info.filename:
        raise AssetError(f"unsafe archive member: {info.filename!r}")
    member = PurePosixPath(info.filename)
    if member.is_absolute() or ".." in member.parts:
        raise AssetError(f"unsafe archive member: {info.filename!r}")
    normalized = member.as_posix().rstrip("/")
    if normalized in seen:
        raise AssetError(f"duplicate archive member: {info.filename!r}")
    seen.add(normalized)
    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode):
        raise AssetError(f"archive symlink is not allowed: {info.filename!r}")
    return member


def safe_extract(source: Path, destination: Path) -> None:
    with zipfile.ZipFile(source) as archive:
        seen: set[str] = set()
        for info in archive.infolist():
            member = _validate_member(info, seen)
            target = destination.joinpath(*member.parts)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, target.open("xb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)


def _copy_source(source: Path, destination: Path) -> None:
    if source.is_file():
        if not zipfile.is_zipfile(source):
            raise AssetError(f"not a ZIP archive: {source}")
        safe_extract(source, destination)
        return
    if source.is_dir():
        for path in _files(source):
            target = destination / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        return
    raise AssetError(f"missing or unreadable asset source: {source}")


def _payload_root(staging: Path) -> Path:
    entries = list(staging.iterdir())
    return entries[0] if len(entries) == 1 and entries[0].is_dir() else staging


def _one(root: Path, name: str) -> Path:
    matches = [path for path in _files(root) if path.name == name]
    if len(matches) != 1:
        raise AssetError(f"expected exactly one {name}, found {len(matches)}")
    return matches[0]


def _discover(kind: str, root: Path) -> dict[str, Path]:
    if kind == "official":
        return {
            "engine_library": _one(root, "libcg.so"),
            "card_data": _one(root, "EN_Card_Data.csv"),
            "license": _one(root, "LicenseRef-PTCG-ABC-Competition-Use-Only.txt"),
            "deck": _one(root, "deck.csv"),
            "wrapper": _one(root, "api.py"),
        }
    if kind == "sample_agents":
        notebooks = [path for path in _files(root) if path.suffix == ".ipynb"]
        if not notebooks:
            raise AssetError("sample-agent bundle contains no notebooks")
        return {"sample_notebook": notebooks[0]}
    files = _files(root)
    if not files:
        raise AssetError("research source is empty")
    return {"research_file": files[0]}


def _source_hash(source: Path) -> str:
    if source.is_file():
        return sha256_file(source)
    if source.is_dir():
        return tree_sha256(source)
    raise AssetError(f"missing or unreadable asset source: {source}")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _write_license_notes(repo: Path, license_hash: str, official_hash: str) -> None:
    text = f"""# License Notes

The official `ptcgProgram` engine is competition-only and is not part of this repository. Its bundled notice says it may be used only for the Pokemon TCG AI Battle Challenge while the competition is running, must not be redistributed, and must be deleted after the competition, subject to the binding [official competition rules](https://www.kaggle.com/competitions/pokemon-tcg-ai-battle/rules).

- Official archive SHA-256: `{official_hash}`
- Bundled license-notice SHA-256: `{license_hash}`

The original notice remains unchanged in ignored private asset storage.
"""
    (repo / "LICENSE-NOTES.md").write_text(text, encoding="utf-8")


def import_assets(
    repo: Path,
    official_archive: Path,
    sample_agents: Path,
    research: Path,
    force: bool = False,
) -> dict[str, Any]:
    sources = {
        "official": official_archive.expanduser().resolve(),
        "sample_agents": sample_agents.expanduser().resolve(),
        "research": research.expanduser().resolve(),
    }
    source_hashes = {kind: _source_hash(source) for kind, source in sources.items()}
    private = repo / "private"
    asset_root = Path(os.environ.get("PTCG_ASSET_ROOT", private / "assets")).expanduser().resolve()
    staging_parent = private / ".staging"
    staging_parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="import-", dir=staging_parent))
    lock_path = private / "assets.lock.json"
    old_lock = json.loads(lock_path.read_text()) if lock_path.exists() else {"assets": {}}
    prepared: dict[str, dict[str, Any]] = {}
    try:
        for kind, source in sources.items():
            stage = staging / kind
            stage.mkdir()
            _copy_source(source, stage)
            payload = _payload_root(stage)
            signatures = _discover(kind, payload)
            manifest = tree_manifest(payload)
            prepared[kind] = {"payload": payload, "signatures": signatures, "manifest": manifest}

        for kind in sources:
            destination = asset_root / kind
            previous = old_lock.get("assets", {}).get(kind, {})
            if destination.exists() and previous.get("source_sha256") != source_hashes[kind] and not force:
                raise AssetError(f"{kind} assets already differ; rerun with --force to back up and replace")

        imported_at = datetime.now(UTC).isoformat()
        backup_stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        records: dict[str, Any] = {}
        for kind, item in prepared.items():
            destination = asset_root / kind
            if destination.exists() and old_lock.get("assets", {}).get(kind, {}).get("source_sha256") == source_hashes[kind]:
                shutil.rmtree(item["payload"])
            else:
                if destination.exists():
                    shutil.move(destination, destination.with_name(f"{kind}.backup.{backup_stamp}"))
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(item["payload"], destination)
            signature_rel = {
                name: path.relative_to(item["payload"]).as_posix()
                for name, path in item["signatures"].items()
            }
            records[kind] = {
                "source_path": str(sources[kind]),
                "source_sha256": source_hashes[kind],
                "imported_at_utc": imported_at,
                "destination": str(destination),
                "version": "ptcgProgram 22" if kind == "official" else "unversioned",
                "signatures": signature_rel,
                "files": item["manifest"],
            }

        lock = {"schema_version": 1, "asset_root": str(asset_root), "assets": records}
        _write_json(lock_path, lock)
        redacted = {
            "schema_version": 1,
            "assets": {
                kind: {
                    "source_sha256": record["source_sha256"],
                    "version": record["version"],
                    "file_count": len(record["files"]),
                    "total_bytes": sum(item["bytes"] for item in record["files"].values()),
                    "signature_sha256": {
                        name: record["files"][relative]["sha256"]
                        for name, relative in record["signatures"].items()
                    },
                }
                for kind, record in records.items()
            },
        }
        _write_json(repo / "asset_hashes.redacted.json", redacted)
        official = records["official"]
        license_hash = official["files"][official["signatures"]["license"]]["sha256"]
        _write_license_notes(repo, license_hash, source_hashes["official"])
        shutil.rmtree(staging)
        return redacted
    except Exception as error:
        raise AssetError(f"{error}; diagnostic staging preserved at {staging}") from error


def verify_assets(repo: Path) -> list[str]:
    lock_path = repo / "private" / "assets.lock.json"
    if not lock_path.exists():
        return ["private/assets.lock.json is missing; run ptcg assets import"]
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    issues: list[str] = []
    for kind, record in lock.get("assets", {}).items():
        root = Path(record["destination"])
        for relative, expected in record["files"].items():
            path = root / relative
            if not path.is_file():
                issues.append(f"{kind}: missing {relative}")
            elif path.stat().st_size != expected["bytes"] or sha256_file(path) != expected["sha256"]:
                issues.append(f"{kind}: hash mismatch {relative}")
    return issues
