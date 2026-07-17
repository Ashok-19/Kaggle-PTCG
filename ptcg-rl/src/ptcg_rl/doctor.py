from __future__ import annotations

import csv
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .assets import verify_assets


def unresolved_values(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [item for child in value.values() for item in unresolved_values(child)]
    if isinstance(value, list):
        return [item for child in value for item in unresolved_values(child)]
    return [value] if isinstance(value, str) and value.startswith("REQUIRED") else []


def _run(args: list[str], cwd: Path, timeout: int = 10) -> tuple[bool, str]:
    try:
        result = subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True, timeout=timeout)
        return True, (result.stdout or result.stderr).strip()
    except (OSError, subprocess.SubprocessError) as error:
        return False, str(error)


def _card_check(path: Path) -> dict[str, int]:
    names_by_id: dict[str, set[str]] = {}
    rows = 0
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            rows += 1
            names_by_id.setdefault(row["Card ID"], set()).add(row["Card Name"])
    inconsistent = sum(len(names) > 1 for names in names_by_id.values())
    if inconsistent:
        raise ValueError(f"{inconsistent} card IDs map to multiple names")
    return {"rows": rows, "unique_card_ids": len(names_by_id), "repeated_move_rows": rows - len(names_by_id)}


def run_doctor(repo: Path, cloud: bool = False, policy: str = "development") -> dict[str, Any]:
    checks: list[dict[str, str]] = []

    def add(name: str, status: str, detail: str, remediation: str = "") -> None:
        checks.append({"name": name, "status": status, "detail": detail, "remediation": remediation})

    git_ok, commit = _run(["git", "rev-parse", "HEAD"], repo)
    _, dirty = _run(["git", "status", "--porcelain"], repo)
    add("git", "pass" if git_ok else "fail", f"commit={commit if git_ok else 'none'} dirty={bool(dirty)}")

    compiler_ok, compiler = _run(["g++", "--version"], repo)
    memory_bytes = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    disk = shutil.disk_usage(repo)
    add(
        "platform",
        "pass" if compiler_ok else "fail",
        f"{platform.platform()} arch={platform.machine()} python={platform.python_version()} "
        f"compiler={compiler.splitlines()[0] if compiler_ok else 'missing'} cpu={os.cpu_count()} "
        f"ram_bytes={memory_bytes} free_disk_bytes={disk.free}",
        "Install a C++20-capable g++ compiler." if not compiler_ok else "",
    )

    try:
        import torch

        torch_detail = f"torch={torch.__version__} cuda={torch.version.cuda} available={torch.cuda.is_available()}"
    except ImportError:
        torch_detail = "torch not installed in G0 local profile"
    add("torch_cuda", "warn", torch_detail, "Freeze the platform CUDA/PyTorch source at its first GPU gate.")

    official = json.loads((repo / "configs" / "official.json").read_text(encoding="utf-8"))
    runtime = official["runtime"]
    provisional = [
        name
        for name in ("python_patch", "timeout_seconds")
        if runtime[name]["status"] != "verified"
    ]
    add(
        "official_limits",
        "pass",
        f"package_limit_kb={official['submission']['hard_package_limit_kb']} "
        f"internal_target_mb<{official['submission']['internal_package_target_mb']} "
        f"raw_resources={json.dumps(runtime['raw_simulation_settings'], sort_keys=True)}",
    )
    primary_python = platform.python_version().startswith("3.11.")
    add(
        "runtime_family",
        "pass" if primary_python else ("fail" if policy == "submission" else "warn"),
        f"expected={runtime['python_family']} actual={platform.python_version()} image={runtime['image']}",
        "Run the primary profile with Python 3.11; retain 3.12 only as secondary compatibility.",
    )
    add(
        "submission_provisionals",
        "fail" if provisional and policy == "submission" else ("warn" if provisional else "pass"),
        f"policy={policy} unresolved={provisional}",
        "Probe the exact Python patch and timeout before final submission qualification.",
    )

    asset_issues = verify_assets(repo)
    add("asset_hashes", "fail" if asset_issues else "pass", "; ".join(asset_issues) or "all imported files match")
    lock_path = repo / "private" / "assets.lock.json"
    if lock_path.exists() and not asset_issues:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        official_asset = lock["assets"]["official"]
        root = Path(official_asset["destination"])
        signatures = official_asset["signatures"]
        try:
            card = _card_check(root / signatures["card_data"])
            add("card_csv", "pass", json.dumps(card, sort_keys=True))
        except Exception as error:
            add("card_csv", "fail", str(error), "Re-import the exact official card CSV.")
        native_ok, native = _run(
            [
                sys.executable,
                "-m",
                "ptcg_rl.native_probe",
                str(root / signatures["engine_library"]),
                str(root / signatures["deck"]),
            ],
            repo,
            timeout=120,
        )
        add("native_engine", "pass" if native_ok else "fail", native, "Re-import or rebuild the official engine.")
        license_path = root / signatures["license"]
        add("engine_license", "pass" if license_path.is_file() else "fail", "bundled notice present")

    kaggle_auth = bool(os.environ.get("KAGGLE_API_TOKEN") or (Path.home() / ".kaggle" / "kaggle.json").is_file())
    add(
        "kaggle_provider",
        "warn" if not kaggle_auth else "pass",
        f"cli={bool(shutil.which('kaggle'))} local_credentials={kaggle_auth}; interactive MCP checked externally",
        "Authorize the configured Kaggle MCP before replay Gate R0." if not kaggle_auth else "",
    )
    if cloud:
        modal_ready = bool(shutil.which("modal") and os.environ.get("MODAL_TOKEN_ID"))
        add("modal", "pass" if modal_ready else "fail", f"available={modal_ready}", "Configure Modal only before G4.")

    failed = [check["name"] for check in checks if check["status"] == "fail"]
    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "policy": policy,
        "status": "pass" if not failed else "fail",
        "failed_checks": failed,
        "checks": checks,
    }
