"""Build an isolated Grim-plus-outcome-head scratch candidate.

The input qualified Grim archive is only read.  The output is a separate
directory/archive and is never written to the production submission path.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
from pathlib import Path, PurePosixPath


QUALIFIED_GRIM_SHA256 = "e9d4681a5252f563309befc450dd31d8c66171b81455600c9e783b13c6d52657"
G2_SHA256 = "4dfba2adb9f97607cfa5dabadba075236bb7aae51eafab264584e947feae3827"
BC_SHA256 = "76478ade97742697cc36aab311373b254ff186c787d772ab39d97cfb27ffafde"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_member_path(name: str) -> Path:
    relative = PurePosixPath(name)
    parts = tuple(part for part in relative.parts if part not in ("", "."))
    if not parts or any(part == ".." for part in parts) or relative.is_absolute():
        raise ValueError(f"unsafe archive path: {name}")
    return Path(*parts)


def _extract_grim(source: Path, destination: Path) -> None:
    if _sha256(source) != QUALIFIED_GRIM_SHA256:
        raise ValueError("qualified Grim control SHA-256 differs; refusing to build")
    with tarfile.open(source, "r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            relative = _safe_member_path(member.name)
            if "__pycache__" in relative.parts:
                continue
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError(f"cannot read archive member: {member.name}")
            target.write_bytes(stream.read())
            target.chmod(member.mode & 0o777)


def _copy_source(repo: Path, destination: Path) -> None:
    paths = (
        "__init__.py",
        "g1/__init__.py",
        "g1/models.py",
        "g1/semantic.py",
        "g2/__init__.py",
        "g2/card_table.py",
        "g2/checkpoint.py",
        "g2/models.py",
        "g2/network.py",
        "g2/projection.py",
    )
    for relative in paths:
        source = repo / "src/ptcg_rl" / relative
        target = destination / "ptcg_rl" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _copy_assets(root: Path, g2: Path, bc: Path, head: Path) -> dict[str, object]:
    assets = root / ".assets"
    assets.mkdir(parents=True, exist_ok=True)
    copies = {
        "g2-policy-checkpoint-v1.zip": g2,
        "epoch-4.pt": bc,
        "outcome_head.pt": head,
    }
    result: dict[str, object] = {}
    for name, source in copies.items():
        target = assets / name
        shutil.copy2(source, target)
        result[name] = {"bytes": target.stat().st_size, "sha256": _sha256(target)}
    if result["g2-policy-checkpoint-v1.zip"]["sha256"] != G2_SHA256:  # type: ignore[index]
        raise ValueError("G2 package SHA-256 differs from the pinned package")
    if result["epoch-4.pt"]["sha256"] != BC_SHA256:  # type: ignore[index]
        raise ValueError("BC checkpoint SHA-256 differs from epoch 4")
    return result


def build(args: argparse.Namespace) -> Path:
    repo = Path(__file__).resolve().parents[3]
    source_root = Path(args.out_dir).resolve()
    if source_root.exists():
        raise ValueError(f"output directory already exists: {source_root}")
    source_root.mkdir(parents=True)
    _extract_grim(Path(args.grim_tar).resolve(), source_root)
    original_main = source_root / "main.py"
    if not original_main.is_file():
        raise ValueError("qualified Grim archive has no root main.py")
    original_main.rename(source_root / "qualified_grim_main.py")
    _copy_source(repo, source_root)
    shutil.copy2(repo / ".chatgpt/tmp/outcome-ranker/outcome_ranker.py", source_root / "outcome_ranker.py")
    shutil.copy2(Path(__file__).with_name("outcome_main_adapter.py"), source_root / "outcome_main_adapter.py")
    shutil.copy2(Path(__file__).with_name("main.py"), source_root / "main.py")
    assets = _copy_assets(
        source_root,
        Path(args.g2).resolve(),
        Path(args.bc).resolve(),
        Path(args.head).resolve(),
    )
    manifest = {
        "schema_version": 1,
        "candidate_kind": "SCRATCH_GRIM_OUTCOME_MAIN_ADAPTER",
        "qualified_grim_tar_sha256": QUALIFIED_GRIM_SHA256,
        "qualified_grim_module_sha256": _sha256(source_root / "qualified_grim_main.py"),
        "assets": assets,
        "entrypoint": "main.py",
        "ranked_path": "selection_type=0, selection_context=0, min_count=max_count=1",
        "non_main_path": "qualified_grim_main.py",
        "search": False,
        "inference_device": "cpu",
    }
    (source_root / "scratch-candidate-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    archive_path = Path(args.archive).resolve() if args.archive else None
    if archive_path is not None:
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(archive_path, "w:gz") as archive:
            for path in sorted(source_root.rglob("*")):
                if path.is_file():
                    archive.add(path, arcname=path.relative_to(source_root))
    return source_root


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--grim-tar", required=True, type=Path)
    parser.add_argument("--head", required=True, type=Path)
    parser.add_argument("--g2", required=True, type=Path)
    parser.add_argument("--bc", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    print(build(args))


if __name__ == "__main__":
    main()
