from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from .evidence import (
    git_state,
    platform_record,
    sha256_file,
    source_tree_hash,
    technical_run_envelope,
    unique_run_id,
    write_immutable_json,
)


def run_verification(args, repo: Path) -> dict[str, Any]:
    run_id = unique_run_id("g1r-verification")
    run_dir = (args.output or repo / "runs" / run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    executable = Path(sys.executable).with_name
    commands = [
        ("pytest", [sys.executable, "-m", "pytest", "-q", "tests"], repo),
        ("ruff", [str(executable("ruff")), "check", "."], repo),
        ("assets", [str(executable("ptcg")), "assets", "verify"], repo),
        ("contract", [str(executable("ptcg")), "g1", "validate"], repo),
        ("dashboard-tests", ["npm", "test"], repo / "dashboard" / "frontend"),
        ("dashboard-build", ["npm", "run", "build"], repo / "dashboard" / "frontend"),
        ("dashboard-ingest", [str(executable("ptcg")), "dashboard", "rebuild"], repo),
    ]
    results = []
    for name, command, cwd in commands:
        completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
        stdout = run_dir / f"{name}.stdout.log"
        stderr = run_dir / f"{name}.stderr.log"
        stdout.write_text(completed.stdout, encoding="utf-8")
        stderr.write_text(completed.stderr, encoding="utf-8")
        results.append({"name": name, "argv": command, "exit_code": completed.returncode,
                        "stdout_sha256": sha256_file(stdout),
                        "stderr_sha256": sha256_file(stderr)})
    passed = all(result["exit_code"] == 0 for result in results)
    manifest_path = run_dir / "run_manifest.json"
    manifest = {
        **technical_run_envelope(repo, manifest_path, run_id, "ptcg.g1r.verification", passed),
        "checks": results, "repository": git_state(repo), "platform": platform_record(),
        "source_sha256": source_tree_hash(repo), "command": list(sys.argv),
        "training_performed": False, "local_cost_usd": 0.0,
    }
    write_immutable_json(manifest_path, manifest)
    manifest_path.with_suffix(".json.sha256").write_text(
        f"{sha256_file(manifest_path)}  {manifest_path.name}\n", encoding="ascii"
    )
    return manifest
