from __future__ import annotations

import argparse
import json
import os
import shutil
import stat
import signal
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

SOURCE_BUNDLE_SLUG = "kptcg-e01-majkel-corpus-review-inputs"
RETAINED_SLUG = "kptcg-e01-production-bc-retained-inputs"
AUGUST_3_SLUG = "pokemon-tcg-ai-battle-episodes-2026-08-03"
AUGUST_4_SLUG = "pokemon-tcg-ai-battle-episodes-2026-08-04"
SOURCE_TREE_DIR = "kptcg-e01-majkel-corpus-review-source-v1"
TRAINING_REQUEST_PATH = "configs/e01_production_recurrent_bc_request_v2.json"
IMPLEMENTATION_PATH = "src/ptcg_rl/g3/bc_production_v2.py"
CHECKPOINT_DIRECTORY = "private/g2/checkpoint-v1/g2-policy-checkpoint-v1"
CHECKPOINT_PATH = "private/g2/checkpoint-v1/g2-policy-checkpoint-v1.zip"
CHECKPOINT_MEMBERS = (
    "card-table-v1.json",
    "manifest.json",
    "reference-v1.json",
    "state-v1.bin",
)
CHECKPOINT_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
CHECKPOINT_MODE = stat.S_IFREG | 0o600
MAXIMUM_EPOCHS = 1
MAXIMUM_OPTIMIZER_STEPS = 32
MAXIMUM_WALL_SECONDS = 3_600


class NotebookRuntimeError(RuntimeError):
    pass


def find_mount(input_root: Path, slug: str) -> Path:
    candidates = [
        input_root / slug,
        input_root / "datasets" / "ashok205" / slug,
        input_root / "datasets" / "organizations" / "kaggle" / slug,
        input_root / "datasets" / "kaggle" / slug,
    ]
    found = [path.resolve() for path in candidates if path.is_dir()]
    if len(found) == 1:
        return found[0]

    shallow: list[Path] = []
    if input_root.is_dir():
        for current, dirs, _files in os.walk(input_root):
            current_path = Path(current)
            depth = len(current_path.relative_to(input_root).parts)
            if depth >= 4:
                dirs[:] = []
            for name in dirs:
                if name == slug:
                    shallow.append((current_path / name).resolve())
    unique = sorted(set(found + shallow))
    if len(unique) != 1:
        raise NotebookRuntimeError(f"expected one Kaggle mount for {slug}, found {unique}")
    return unique[0]


def copy_source_tree(source_mount: Path, work_root: Path) -> None:
    if work_root.exists():
        raise NotebookRuntimeError(f"working root already exists: {work_root}")
    source_tree = source_mount / SOURCE_TREE_DIR
    if not source_tree.is_dir():
        raise NotebookRuntimeError(f"source tree is missing: {source_tree}")
    shutil.copytree(source_tree, work_root)
    for path in sorted(source_mount.rglob("*")):
        if not path.is_file() or path.is_relative_to(source_tree):
            continue
        relative = path.relative_to(source_mount)
        destination = work_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)


def install_training_code(work_root: Path, request_source: Path, implementation_source: Path) -> None:
    for source, destination in (
        (request_source, work_root / TRAINING_REQUEST_PATH),
        (implementation_source, work_root / IMPLEMENTATION_PATH),
    ):
        if not source.is_file():
            raise NotebookRuntimeError(f"bootstrap source is missing: {source}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def ensure_checkpoint_package(work_root: Path) -> Path:
    checkpoint = work_root / CHECKPOINT_PATH
    if checkpoint.is_file():
        return checkpoint
    member_dir = work_root / CHECKPOINT_DIRECTORY
    if not member_dir.is_dir():
        raise NotebookRuntimeError(f"checkpoint member directory is missing: {member_dir}")
    observed = {path.name for path in member_dir.iterdir() if path.is_file()}
    if observed != set(CHECKPOINT_MEMBERS):
        raise NotebookRuntimeError(
            f"checkpoint members differ: expected={sorted(CHECKPOINT_MEMBERS)} observed={sorted(observed)}"
        )
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(checkpoint, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(CHECKPOINT_MEMBERS):
            info = zipfile.ZipInfo(name, date_time=CHECKPOINT_TIMESTAMP)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = CHECKPOINT_MODE << 16
            info.internal_attr = 0
            info.flag_bits = 0
            archive.writestr(
                info,
                (member_dir / name).read_bytes(),
                compress_type=zipfile.ZIP_STORED,
            )
    return checkpoint


def output_inventory(root: Path) -> list[dict[str, Any]]:
    return [
        {"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size}
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a bounded E01 recurrent-BC smoke train on Kaggle CPU.")
    parser.add_argument("--input-root", type=Path, default=Path("/kaggle/input"))
    parser.add_argument("--working-root", type=Path, default=Path("/kaggle/working/kptcg-e01-recurrent-bc-smoke-v1"))
    parser.add_argument("--request-source", type=Path, required=True)
    parser.add_argument("--implementation-source", type=Path, required=True)
    args = parser.parse_args()

    started = time.monotonic()
    source_mount = find_mount(args.input_root, SOURCE_BUNDLE_SLUG)
    retained_mount = find_mount(args.input_root, RETAINED_SLUG)
    august_3_mount = find_mount(args.input_root, AUGUST_3_SLUG)
    august_4_mount = find_mount(args.input_root, AUGUST_4_SLUG)

    copy_source_tree(source_mount, args.working_root)
    install_training_code(args.working_root, args.request_source.resolve(), args.implementation_source.resolve())
    ensure_checkpoint_package(args.working_root)

    sys.path.insert(0, str(args.working_root / "src"))
    import torch

    if torch.cuda.is_available():
        raise NotebookRuntimeError("GPU is visible in the CPU smoke notebook")

    from ptcg_rl.g3.bc_production_v2 import TrainingRunOptions, execute_training

    output_dir = args.working_root / "outputs/e01-recurrent-bc-smoke-v1"
    remaining = MAXIMUM_WALL_SECONDS - int(time.monotonic() - started)
    if remaining <= 0:
        raise NotebookRuntimeError("setup exhausted the smoke wall-time cap")

    def timeout_handler(_signum: int, _frame: Any) -> None:
        raise TimeoutError("recurrent-BC smoke train exceeded its wall-time cap")

    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(remaining)
    try:
        report = execute_training(
            args.working_root,
            args.working_root / TRAINING_REQUEST_PATH,
            {
                "retained_private": retained_mount,
                "august_3_daily": august_3_mount,
                "august_4_daily": august_4_mount,
            },
            output_dir,
            options=TrainingRunOptions(
                smoke_sample=True,
                maximum_epochs=MAXIMUM_EPOCHS,
                maximum_optimizer_steps=MAXIMUM_OPTIMIZER_STEPS,
                validation_episode_limit=8,
            ),
        )
    finally:
        signal.alarm(0)

    if report.get("status") != "PASS_SMOKE_TRAINING_COMPLETED":
        raise NotebookRuntimeError(f"unexpected smoke status: {report.get('status')}")
    if int(report.get("optimizer_steps", -1)) > MAXIMUM_OPTIMIZER_STEPS:
        raise NotebookRuntimeError("smoke optimizer step cap exceeded")
    if int(report.get("epochs", -1)) > MAXIMUM_EPOCHS:
        raise NotebookRuntimeError("smoke epoch cap exceeded")
    if report.get("test_replay_bodies_read") != 0:
        raise NotebookRuntimeError("test replay was read during smoke training")
    if report.get("candidate_checkpoint_eligible_for_evaluation_only") is not False:
        raise NotebookRuntimeError("smoke checkpoint became evaluation eligible")
    if report.get("model_promoted") is not False or report.get("submission") is not False:
        raise NotebookRuntimeError("smoke run unexpectedly promoted or submitted a model")

    envelope = {
        "schema_version": 1,
        "record_id": "e01-recurrent-bc-smoke-notebook-execution-v1",
        "status": "PASS_SMOKE_TRAINING_COMPLETED",
        "optimizer_steps": int(report["optimizer_steps"]),
        "epochs": int(report["epochs"]),
        "train_episodes": int(report["train_episodes"]),
        "validation_episodes": int(report["validation_episodes"]),
        "train_episode_ids": report["train_episode_ids"],
        "validation_episode_ids": report["validation_episode_ids"],
        "test_replay_bodies_read": 0,
        "gpu": False,
        "tpu": False,
        "internet": False,
        "model_promoted": False,
        "submission": False,
        "output_inventory": output_inventory(output_dir),
        "wall_seconds": time.monotonic() - started,
    }
    (output_dir / "notebook-execution-envelope.json").write_text(
        json.dumps(envelope, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(envelope, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
