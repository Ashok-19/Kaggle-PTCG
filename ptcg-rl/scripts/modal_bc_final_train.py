from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import modal

if modal.is_local():
    ROOT = Path(__file__).resolve().parents[2]
else:
    ROOT = Path("/workspace")
PTCG_RL = ROOT / "ptcg-rl"
VOLUME_NAME = "kptcg-training"

ARCHETYPE_DIR = Path("/data/materialized/bc-dragapult-archetype-v3-featurefix-v3")
EXACT_DIR = Path("/data/materialized/bc-dragapult-hq-v2-featurefix-v3")
ARCHETYPE_CACHE = Path("/data/cache/materialized-episode-objects-v1/bc-dragapult-archetype-v3-featurefix-v3.pkl")
EXACT_CACHE = Path("/data/cache/materialized-episode-objects-v1/bc-dragapult-hq-v2-featurefix-v3.pkl")
OUTPUT_ROOT = Path("/data/runs/bc-dragapult-final-v5-schema-v3-fused-update-density")

SUPPORTED_MODELS = {"970k", "1.4m", "1.8m", "2.9m", "3.7m", "5.0m"}

image = (
    modal.Image.debian_slim(python_version="3.11")
    .run_commands(
        "python -m pip install --no-cache-dir numpy==2.0.2",
        "python -m pip install --no-cache-dir torch==2.10.0 --index-url https://download.pytorch.org/whl/cu130",
    )
    .add_local_dir(PTCG_RL / "src", remote_path="/workspace/ptcg-rl/src")
    .add_local_file(
        PTCG_RL / "scripts/bc_train_materialized.py",
        remote_path="/workspace/ptcg-rl/scripts/bc_train_materialized.py",
    )
    .add_local_file(
        PTCG_RL / "scripts/bc_capacity_sweep.py",
        remote_path="/workspace/ptcg-rl/scripts/bc_capacity_sweep.py",
    )
    .add_local_file(
        PTCG_RL / "private/g2/card-table-v1.json",
        remote_path="/workspace/ptcg-rl/private/g2/card-table-v1.json",
    )
)

app = modal.App("kptcg-bc-dragapult-final-train", image=image)
training_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=False)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_fast_inputs() -> None:
    for root, label in ((ARCHETYPE_DIR, "archetype-v3"), (EXACT_DIR, "exact-v2")):
        if not (root / "manifest.json").is_file():
            raise RuntimeError(f"{label} materialized directory is missing manifest.json: {root}")
    for cache, label in ((ARCHETYPE_CACHE, "archetype-v3"), (EXACT_CACHE, "exact-v2")):
        if not cache.is_file():
            raise RuntimeError(f"{label} persistent object cache is missing: {cache}")
    print(
        json.dumps(
            {
                "event": "final_bc_fast_inputs_ready",
                "archetype_dir": str(ARCHETYPE_DIR),
                "exact_dir": str(EXACT_DIR),
                "archetype_cache_bytes": ARCHETYPE_CACHE.stat().st_size,
                "exact_cache_bytes": EXACT_CACHE.stat().st_size,
            },
            sort_keys=True,
        ),
        flush=True,
    )


def _run_stream(command: list[str]) -> None:
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    tail: list[str] = []
    for line in process.stdout:
        print(line, end="", flush=True)
        tail.append(line.rstrip())
        if len(tail) > 300:
            tail.pop(0)
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            event = None
        if isinstance(event, dict) and event.get("event") == "capacity_model_complete":
            training_volume.commit()
            print(
                json.dumps(
                    {
                        "event": "final_bc_model_volume_committed",
                        "model": event.get("model"),
                        "checkpoint_sha256": event.get("final_checkpoint_sha256"),
                        "final_validation_nll": event.get("final_validation_nll"),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(
            f"final BC subprocess failed with exit code {return_code}; tail="
            + "\n".join(tail[-60:])
        )


@app.function(
    gpu="T4",
    cpu=8,
    memory=32768,
    timeout=8 * 60 * 60,
    volumes={"/data": training_volume},
)
def run(
    model_label: str,
    batch_size: int,
    learning_rate: float,
    force: bool = False,
) -> dict[str, Any]:
    if model_label not in SUPPORTED_MODELS:
        raise ValueError(f"unsupported model label: {model_label}")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    if learning_rate <= 0:
        raise ValueError("learning_rate must be positive")

    _require_fast_inputs()
    output_dir = OUTPUT_ROOT / model_label
    report_path = output_dir / "capacity-sweep-report.json"
    if output_dir.exists():
        if report_path.is_file() and not force:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            return {
                "status": "EXISTS",
                "model_label": model_label,
                "report_path": str(report_path),
                "report_sha256": _sha256_file(report_path),
                "validation_ranking": report.get("validation_ranking"),
            }
        if not force:
            raise RuntimeError(f"partial final BC output exists: {output_dir}")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    print(
        json.dumps(
            {
                "event": "final_bc_launch",
                "model": model_label,
                "batch_size": batch_size,
                "learning_rate": learning_rate,
                "curriculum_epochs": {
                    "stage_a_archetype_all": 12,
                    "stage_b_archetype_1175": 6,
                    "stage_c_exact_all": 10,
                    "stage_d_exact_1150": 6,
                },
                "selection_contract": "best checkpoint restored after every stage",
            },
            sort_keys=True,
        ),
        flush=True,
    )

    command = [
        "python",
        "/workspace/ptcg-rl/scripts/bc_capacity_sweep.py",
        "--archetype-materialized-dir",
        str(ARCHETYPE_DIR),
        "--exact-materialized-dir",
        str(EXACT_DIR),
        "--archetype-object-cache",
        str(ARCHETYPE_CACHE),
        "--exact-object-cache",
        str(EXACT_CACHE),
        "--card-table",
        "/workspace/ptcg-rl/private/g2/card-table-v1.json",
        "--output-dir",
        str(output_dir),
        "--device",
        "cuda",
        "--model-labels",
        model_label,
        "--batch-size-candidates",
        str(batch_size),
        "--learning-rate-candidates",
        format(learning_rate, ".12g"),
        "--sequence-length",
        "32",
        "--speed-train-limit",
        "1024",
        "--speed-validation-limit",
        "64",
        "--lr-train-limit",
        "256",
        "--lr-validation-limit",
        "64",
        "--lr-smoke-epochs",
        "1",
        "--stage-a-epochs",
        "12",
        "--stage-b-epochs",
        "6",
        "--stage-c-epochs",
        "10",
        "--stage-d-epochs",
        "6",
        "--seed",
        "20260815",
        "--loader-workers",
        "8",
        "--weight-decay",
        "0.0001",
        "--maximum-gradient-norm",
        "1.0",
        "--maximum-targets-per-optimizer-step",
        "512",
        "--bf16",
        "--speed-stop-after-first-pass",
    ]
    _run_stream(command)
    if not report_path.is_file():
        raise RuntimeError("final BC run completed without capacity-sweep-report.json")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("status") != "PASS_BC_CAPACITY_SWEEP_COMPLETED":
        raise RuntimeError("final BC report did not PASS")
    training_volume.commit()
    return {
        "status": "PASS_FINAL_BC_TRAINING_COMPLETED",
        "model_label": model_label,
        "batch_size": batch_size,
        "learning_rate": learning_rate,
        "report_path": str(report_path),
        "report_sha256": _sha256_file(report_path),
        "validation_ranking": report["validation_ranking"],
        "elapsed_seconds": report["elapsed_seconds"],
    }


@app.local_entrypoint()
def main(
    model_label: str,
    batch_size: int,
    learning_rate: float,
    force: bool = False,
) -> None:
    print(run.remote(model_label, batch_size, learning_rate, force))
