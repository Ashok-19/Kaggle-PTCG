from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


EXCLUDED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "checkpoints",
    "data",
    "dist",
    "node_modules",
    "playwright-report",
    "private",
    "reports",
    "runs",
    "submissions",
    "test-results",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
SOURCE_ROOTS = ("src", "tests", "scripts", "contracts", "configs", "schemas", "dashboard")
SOURCE_FILES = ("pyproject.toml", "uv.lock")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_files(repo: Path) -> Iterable[Path]:
    for root_name in SOURCE_ROOTS:
        root = repo / root_name
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(repo)
            if path.is_file() and not any(part in EXCLUDED_PARTS for part in relative.parts):
                if path.suffix not in EXCLUDED_SUFFIXES:
                    yield path
    for name in SOURCE_FILES:
        path = repo / name
        if path.is_file():
            yield path


def source_tree_hash(repo: Path) -> str:
    repo = repo.resolve()
    digest = hashlib.sha256()
    for path in sorted(set(_source_files(repo))):
        relative = path.relative_to(repo).as_posix()
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def unique_run_id(prefix: str) -> str:
    safe_prefix = "".join(character for character in prefix.lower() if character.isalnum() or character == "-")
    if not safe_prefix:
        raise ValueError("run ID prefix has no safe characters")
    return f"{safe_prefix}-{datetime.now(timezone.utc):%Y%m%dT%H%M%S.%fZ}-{uuid.uuid4().hex[:12]}"


def write_immutable_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def git_state(repo: Path) -> dict[str, Any]:
    def run(*args: str) -> bytes:
        return subprocess.run(
            ["git", *args], cwd=repo, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        ).stdout

    commit = run("rev-parse", "HEAD").decode().strip()
    status = run("status", "--porcelain=v1", "-z")
    tracked_diff = run("diff", "--binary", "HEAD")
    digest = hashlib.sha256(status + b"\0" + tracked_diff).hexdigest()
    return {
        "commit": commit,
        "dirty": bool(status),
        "dirty_digest_sha256": digest,
        "status_entry_count": status.count(b"\0"),
    }


def platform_record() -> dict[str, str]:
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": sys.version.split()[0],
    }


def technical_run_envelope(
    repo: Path, manifest_path: Path, run_id: str, producer: str, passed: bool
) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": 1,
        "record_id": f"run-{run_id}",
        "created_at_utc": now,
        "updated_at_utc": now,
        "source_path": manifest_path.resolve().relative_to(repo.resolve()).as_posix(),
        "producer": producer,
        "producer_version": "2",
        "run_id": run_id,
        "gate_id": "G1R",
        "status": "SUCCEEDED" if passed else "FAILED",
        "decision": "NOT_REVIEWED",
        "internal_verdict": "PASS" if passed else "FAIL",
    }
