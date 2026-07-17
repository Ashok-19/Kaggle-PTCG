from __future__ import annotations

import fnmatch
import subprocess
from pathlib import Path


def load_patterns(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def restricted_paths(paths: list[str], patterns: list[str]) -> list[str]:
    return sorted(
        path
        for path in paths
        if any(fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(Path(path).name, pattern) for pattern in patterns)
    )


def git_paths(repo: Path) -> list[str]:
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.splitlines()
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    return sorted(set(tracked + staged))


def audit_repository(repo: Path) -> list[str]:
    return restricted_paths(git_paths(repo), load_patterns(repo / "private_file_denylist.txt"))

