#!/usr/bin/env python3
"""Run one command and append an immutable, hash-backed evidence journal entry."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _redact_argument(value: str) -> str:
    if "X-Goog-Signature=" in value or "X-Amz-Signature=" in value:
        return value.split("?", 1)[0] + "?SIGNED_QUERY_REDACTED"
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command is required after --")

    run_dir = args.run_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    journal = run_dir / "command-journal.jsonl"
    entry_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S.%fZ}-{uuid.uuid4().hex[:8]}"
    stdout_path = run_dir / f"{entry_id}.stdout.log"
    stderr_path = run_dir / f"{entry_id}.stderr.log"
    started_at = datetime.now(timezone.utc)
    started = time.monotonic()
    with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
        completed = subprocess.run(command, stdout=stdout, stderr=stderr, check=False)
    entry = {
        "schema_version": 1,
        "entry_id": entry_id,
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": time.monotonic() - started,
        "cwd": os.getcwd(),
        "argv": [_redact_argument(value) for value in command],
        "exit_code": completed.returncode,
        "stdout": {"path": stdout_path.name, "sha256": _sha256(stdout_path)},
        "stderr": {"path": stderr_path.name, "sha256": _sha256(stderr_path)},
    }
    line = json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n"
    descriptor = os.open(journal, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(descriptor, line.encode("utf-8"))
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    print(json.dumps(entry, indent=2, sort_keys=True))
    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
