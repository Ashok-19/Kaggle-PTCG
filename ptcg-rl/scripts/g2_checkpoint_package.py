from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import platform
import runpy
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch

from ptcg_rl.g2.card_table import load_card_table
from ptcg_rl.g2.checkpoint import (
    CheckpointError,
    build_checkpoint_package,
    build_checkpoint_reference,
    load_checkpoint_package,
    state_dict_sha256,
    verify_checkpoint_reference,
    verify_source_tree,
)
from ptcg_rl.g2.models import model_schema_sha256
from ptcg_rl.g2.network import PTCGPolicyV1, policy_metadata

SOURCE_FILES = (
    "configs/g2_policy_v1.json",
    "scripts/g2_checkpoint_package.py",
    "scripts/kaggle/g2_policy_qualification.py",
    "src/ptcg_rl/__init__.py",
    "src/ptcg_rl/g1/__init__.py",
    "src/ptcg_rl/g1/models.py",
    "src/ptcg_rl/g1/semantic.py",
    "src/ptcg_rl/g2/__init__.py",
    "src/ptcg_rl/g2/card_table.py",
    "src/ptcg_rl/g2/checkpoint.py",
    "src/ptcg_rl/g2/models.py",
    "src/ptcg_rl/g2/network.py",
    "src/ptcg_rl/g2/projection.py",
)
MODEL_PARITY_FILES = (
    "configs/g2_policy_v1.json",
    "scripts/kaggle/g2_policy_qualification.py",
    "src/ptcg_rl/__init__.py",
    "src/ptcg_rl/g1/__init__.py",
    "src/ptcg_rl/g1/models.py",
    "src/ptcg_rl/g1/semantic.py",
    "src/ptcg_rl/g2/__init__.py",
    "src/ptcg_rl/g2/card_table.py",
    "src/ptcg_rl/g2/models.py",
    "src/ptcg_rl/g2/network.py",
    "src/ptcg_rl/g2/projection.py",
)
PRIVATE_CARD_TABLE = "private/g2/card-table-v1.json"
PARITY_REPORT = "reports/evaluations/g2-policy-cpu-gpu-parity-v4.json"
EXPECTED_QUALIFICATION_STATE_ALGORITHM = "sha256-name-lcg24-v1"
EXPECTED_ARTIFACT_ID = "g2-policy-checkpoint-v1"


class QualificationError(RuntimeError):
    pass


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise QualificationError(f"cannot read JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise QualificationError(f"JSON root must be an object: {path}")
    return value


def git(root: Path, *arguments: str) -> str:
    try:
        return subprocess.check_output(
            ["git", *arguments], cwd=root, text=True, stderr=subprocess.STDOUT
        ).strip()
    except subprocess.CalledProcessError as error:
        raise QualificationError(
            f"git {' '.join(arguments)} failed: {error.output.strip()}"
        ) from error


def verify_source_allowlist(root: Path) -> tuple[str, dict[str, bytes]]:
    head = git(root, "rev-parse", "HEAD")
    if len(head) != 40:
        raise QualificationError("Git HEAD is not a full commit SHA")
    tracked = git(root, "ls-files", "--", *SOURCE_FILES).splitlines()
    if sorted(tracked) != sorted(SOURCE_FILES):
        missing = sorted(set(SOURCE_FILES) - set(tracked))
        extra = sorted(set(tracked) - set(SOURCE_FILES))
        raise QualificationError(
            f"checkpoint source allowlist is not exactly tracked: missing={missing}, extra={extra}"
        )
    dirty = git(
        root,
        "status",
        "--porcelain",
        "--untracked-files=all",
        "--",
        *SOURCE_FILES,
    ).splitlines()
    if dirty:
        raise QualificationError(
            f"checkpoint source allowlist differs from HEAD: {dirty}"
        )
    source_files: dict[str, bytes] = {}
    for relative in SOURCE_FILES:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise QualificationError(f"checkpoint source file is missing or a symlink: {relative}")
        source_files[relative] = path.read_bytes()
    return head, source_files


def qualification_namespace(root: Path) -> dict[str, Any]:
    return runpy.run_path(str(root / "scripts/kaggle/g2_policy_qualification.py"))


def current_model(root: Path) -> tuple[PTCGPolicyV1, tuple[Any, ...], dict[str, Any]]:
    table = load_card_table(root / PRIVATE_CARD_TABLE)
    model = PTCGPolicyV1(table)
    namespace = qualification_namespace(root)
    if namespace.get("QUALIFICATION_STATE_ALGORITHM") != EXPECTED_QUALIFICATION_STATE_ALGORITHM:
        raise QualificationError("qualification-state algorithm differs from the frozen contract")
    namespace["initialize_qualification_state"](model)
    decisions = tuple(namespace["projected_decisions"]())
    if not decisions:
        raise QualificationError("qualification fixture is empty")
    return model, decisions, namespace


def verify_config(root: Path, model: PTCGPolicyV1) -> dict[str, Any]:
    config = read_json(root / "configs/g2_policy_v1.json")
    expected_keys = {
        "schema_version",
        "card_table_sha256",
        "model_schema_sha256",
        "numpy_version",
        "torch_version",
        "policy_config",
    }
    if set(config) != expected_keys:
        raise QualificationError("G2 policy config keys differ from the sealed contract")
    if config["schema_version"] != 1:
        raise QualificationError("unsupported G2 policy config schema version")
    if config["card_table_sha256"] != model.card_table_sha256:
        raise QualificationError("G2 policy config card-table hash differs from model")
    if config["model_schema_sha256"] != model_schema_sha256():
        raise QualificationError("G2 policy config model-schema hash differs from source")
    if config["policy_config"] != asdict(model.config):
        raise QualificationError("G2 policy config values differ from model defaults")
    if config["numpy_version"] != np.__version__:
        raise QualificationError("NumPy runtime differs from the sealed G2 config")
    if config["torch_version"] != torch.__version__:
        raise QualificationError("PyTorch runtime differs from the sealed G2 config")
    return config


def verify_parity_evidence(
    root: Path,
    model: PTCGPolicyV1,
    decisions: tuple[Any, ...],
    state_sha256: str,
) -> tuple[dict[str, Any], str]:
    path = root / PARITY_REPORT
    report = read_json(path)
    if report.get("status") != "SUCCEEDED" or report.get("decision") != "PASS":
        raise QualificationError("Kaggle CPU/T4 parity evidence is not a PASS")
    identity = report.get("identity")
    comparison = report.get("comparison")
    checks = report.get("qualification_checks")
    independent = report.get("independent_recalculation")
    if not all(isinstance(value, dict) for value in (identity, comparison, checks, independent)):
        raise QualificationError("Kaggle parity evidence structure differs")
    metadata = policy_metadata(model)
    expected_identity = {
        "qualification_state_sha256": state_sha256,
        "architecture_sha256": metadata["architecture_sha256"],
        "model_config_sha256": metadata["config_sha256"],
        "trainable_parameters": metadata["trainable_parameters"],
    }
    for key, expected in expected_identity.items():
        if identity.get(key) != expected:
            raise QualificationError(f"Kaggle parity identity differs for {key}")
    reference = build_checkpoint_reference(model, decisions)
    if identity.get("qualification_input_sha256") != reference["input_sha256"]:
        raise QualificationError("Kaggle parity fixture hash differs from checkpoint fixture")
    if identity.get("all_cpu_gpu_identity_fields_match") is not True:
        raise QualificationError("Kaggle parity identity fields did not all match")
    if comparison.get("failure_count") != 0 or comparison.get("all_values_within_tolerance") is not True:
        raise QualificationError("Kaggle parity comparison has failures")
    if checks != {
        "required_checks_per_device": 10,
        "cpu_all_checks": True,
        "gpu_all_checks": True,
        "optimizer_created": False,
        "optimizer_steps": 0,
        "training_loop_ran": False,
    }:
        raise QualificationError("Kaggle parity no-training checks differ")
    if independent.get("status") != "PASS":
        raise QualificationError("Kaggle parity independent recalculation did not pass")
    parity_commit = identity.get("source_commit")
    if not isinstance(parity_commit, str) or len(parity_commit) != 40:
        raise QualificationError("Kaggle parity source commit is invalid")
    repository_prefix = git(root, "rev-parse", "--show-prefix")
    for relative in MODEL_PARITY_FILES:
        current = (root / relative).read_bytes()
        object_path = f"{repository_prefix}{relative}"
        try:
            historical = subprocess.check_output(
                ["git", "show", f"{parity_commit}:{object_path}"], cwd=root
            )
        except subprocess.CalledProcessError as error:
            raise QualificationError(
                f"cannot read parity-source bytes for {relative} at {parity_commit}"
            ) from error
        if current != historical:
            raise QualificationError(
                f"model-relevant source changed since Kaggle parity: {relative}"
            )
    return report, sha256_file(path)


def module_origins(root: Path) -> dict[str, str]:
    resolved_root = root.resolve()
    modules = (
        "ptcg_rl.g1.models",
        "ptcg_rl.g1.semantic",
        "ptcg_rl.g2.card_table",
        "ptcg_rl.g2.checkpoint",
        "ptcg_rl.g2.models",
        "ptcg_rl.g2.network",
        "ptcg_rl.g2.projection",
    )
    result: dict[str, str] = {}
    for name in modules:
        module = importlib.import_module(name)
        path = Path(str(module.__file__)).resolve()
        if not path.is_relative_to(resolved_root):
            raise QualificationError(f"loaded module escapes requested source root: {name} -> {path}")
        result[name] = path.relative_to(resolved_root).as_posix()
    return result


def write_receipt(path: Path, receipt: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(
        json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def verify_command(args: argparse.Namespace) -> dict[str, Any]:
    root = args.root.resolve()
    loaded = load_checkpoint_package(
        args.package.resolve(),
        device="cpu",
        expected_package_sha256=args.expected_package_sha256,
        expected_source_commit=args.expected_source_commit,
        source_root=root,
    )
    namespace = qualification_namespace(root)
    decisions = tuple(namespace["projected_decisions"]())
    reference = verify_checkpoint_reference(loaded.model, decisions, loaded.reference)
    receipt = {
        "schema_version": 1,
        "record_id": "g2-policy-checkpoint-v1-verification",
        "status": "PASS",
        "source_root": str(root),
        "source_commit": loaded.manifest["source"]["commit"],
        "package": {
            "bytes": loaded.package_bytes,
            "sha256": loaded.package_sha256,
        },
        "manifest": loaded.manifest,
        "reference_verification": reference,
        "source_verification": verify_source_tree(root, loaded.manifest),
        "module_origins": module_origins(root),
        "runtime": {
            "python": sys.version,
            "torch": torch.__version__,
            "numpy": np.__version__,
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "authorization": {
            "optimizer_created": False,
            "optimizer_steps": 0,
            "training_loop_ran": False,
            "pickle_used": False,
        },
    }
    if args.receipt is not None:
        write_receipt(args.receipt.resolve(), receipt)
    return receipt


def isolated_verify(
    root: Path,
    package: Path,
    package_sha256: str,
    source_commit: str,
    source_files: dict[str, bytes],
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="kptcg-g2-checkpoint-") as directory:
        isolated = Path(directory).resolve()
        for relative, raw in source_files.items():
            destination = isolated / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
        isolated_package = isolated / "private/checkpoint.zip"
        isolated_package.parent.mkdir(parents=True)
        shutil.copyfile(package, isolated_package)
        receipt_path = isolated / "private/verification.json"
        environment = {
            **os.environ,
            "PYTHONPATH": str(isolated / "src"),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        completed = subprocess.run(
            [
                sys.executable,
                str(isolated / "scripts/g2_checkpoint_package.py"),
                "verify",
                "--root",
                str(isolated),
                "--package",
                str(isolated_package),
                "--expected-package-sha256",
                package_sha256,
                "--expected-source-commit",
                source_commit,
                "--receipt",
                str(receipt_path),
            ],
            cwd=isolated,
            env=environment,
            text=True,
            capture_output=True,
            timeout=180,
            check=False,
        )
        if completed.returncode != 0:
            raise QualificationError(
                "isolated checkpoint verification failed: "
                f"stdout={completed.stdout[-4000:]!r}, stderr={completed.stderr[-4000:]!r}"
            )
        receipt = read_json(receipt_path)
        if receipt.get("status") != "PASS":
            raise QualificationError("isolated checkpoint verification did not pass")
        for relative in receipt.get("module_origins", {}).values():
            if not isinstance(relative, str) or not relative.startswith("src/"):
                raise QualificationError("isolated verification imported a module outside copied source")
        return {
            "status": "PASS",
            "returncode": completed.returncode,
            "reference_verification": receipt["reference_verification"],
            "source_verification": receipt["source_verification"],
            "module_origins": receipt["module_origins"],
            "runtime": receipt["runtime"],
        }


def qualify_command(args: argparse.Namespace) -> dict[str, Any]:
    root = args.root.resolve()
    source_commit, source_files = verify_source_allowlist(root)
    model, decisions, namespace = current_model(root)
    verify_config(root, model)
    state_sha = state_dict_sha256(model.state_dict())
    parity, parity_sha = verify_parity_evidence(root, model, decisions, state_sha)
    reference = build_checkpoint_reference(model, decisions)
    card_table_path = root / PRIVATE_CARD_TABLE
    card_table_bytes = card_table_path.read_bytes()
    output = args.output.resolve()
    duplicate = output.with_suffix(output.suffix + ".duplicate")
    first = build_checkpoint_package(
        output,
        model,
        card_table_bytes,
        reference,
        source_commit,
        source_files,
        PARITY_REPORT,
        parity_sha,
        artifact_id=EXPECTED_ARTIFACT_ID,
    )
    second = build_checkpoint_package(
        duplicate,
        model,
        card_table_bytes,
        reference,
        source_commit,
        dict(reversed(list(source_files.items()))),
        PARITY_REPORT,
        parity_sha,
        artifact_id=EXPECTED_ARTIFACT_ID,
    )
    if output.read_bytes() != duplicate.read_bytes() or first != second:
        raise QualificationError("duplicate checkpoint builds are not byte-identical")
    duplicate.unlink()
    loaded = load_checkpoint_package(
        output,
        expected_package_sha256=first["package_sha256"],
        expected_source_commit=source_commit,
        source_root=root,
    )
    local_reference = verify_checkpoint_reference(loaded.model, decisions, loaded.reference)
    isolated = isolated_verify(
        root,
        output,
        first["package_sha256"],
        source_commit,
        source_files,
    )
    receipt = {
        "schema_version": 1,
        "record_id": "g2-policy-checkpoint-v1-qualification",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": "PASS",
        "artifact_id": EXPECTED_ARTIFACT_ID,
        "source_commit": source_commit,
        "source_files": len(source_files),
        "package": {
            "path": str(output),
            "bytes": first["package_bytes"],
            "sha256": first["package_sha256"],
            "manifest_sha256": first["manifest_sha256"],
            "duplicate_build_match": True,
            "archive_entries": 4,
            "compression": "ZIP_STORED",
        },
        "model": policy_metadata(model),
        "model_schema_sha256": model_schema_sha256(),
        "state": {
            "algorithm": namespace["QUALIFICATION_STATE_ALGORITHM"],
            "sha256": state_sha,
            "matches_parity": state_sha
            == parity["identity"]["qualification_state_sha256"],
        },
        "reference": {
            "fixture_id": reference["fixture_id"],
            "input_sha256": reference["input_sha256"],
            "selected_option_indices": reference["action_trace"]["selected_option_indices"],
            "stop_selected": reference["action_trace"]["stop_selected"],
            "compound_log_probability": reference["action_trace"][
                "compound_log_probability"
            ],
            "verification": local_reference,
        },
        "parity_evidence": {
            "path": PARITY_REPORT,
            "sha256": parity_sha,
            "source_commit": parity["identity"]["source_commit"],
            "model_source_files_unchanged": len(MODEL_PARITY_FILES),
            "decision": parity["decision"],
        },
        "isolated_verification": isolated,
        "runtime": {
            "python": sys.version,
            "torch": torch.__version__,
            "numpy": np.__version__,
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "authorization": {
            "optimizer_created": False,
            "optimizer_steps": 0,
            "training_loop_ran": False,
            "pickle_used": False,
            "kaggle_run_performed": False,
        },
        "cost_usd": 0.0,
    }
    write_receipt(args.receipt.resolve(), receipt)
    return receipt


def parser() -> argparse.ArgumentParser:
    root_default = Path(__file__).resolve().parents[1]
    value = argparse.ArgumentParser(description="Build or verify the G2 policy checkpoint package")
    commands = value.add_subparsers(dest="command", required=True)

    qualify = commands.add_parser("qualify")
    qualify.add_argument("--root", type=Path, default=root_default)
    qualify.add_argument("--output", type=Path, required=True)
    qualify.add_argument("--receipt", type=Path, required=True)
    qualify.set_defaults(function=qualify_command)

    verify = commands.add_parser("verify")
    verify.add_argument("--root", type=Path, default=root_default)
    verify.add_argument("--package", type=Path, required=True)
    verify.add_argument("--expected-package-sha256")
    verify.add_argument("--expected-source-commit")
    verify.add_argument("--receipt", type=Path)
    verify.set_defaults(function=verify_command)
    return value


def main() -> None:
    args = parser().parse_args()
    try:
        receipt = args.function(args)
    except (CheckpointError, QualificationError, OSError, subprocess.SubprocessError) as error:
        raise SystemExit(f"G2 checkpoint qualification failed closed: {error}") from error
    print(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
