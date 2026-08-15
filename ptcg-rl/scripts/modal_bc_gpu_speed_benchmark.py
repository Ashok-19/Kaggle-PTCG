from __future__ import annotations

import json
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

ARCHETYPE_DIR = Path("/data/materialized/bc-dragapult-archetype-v3")
EXACT_DIR = Path("/data/materialized/bc-dragapult-hq-v2")
ARCHETYPE_CACHE = Path("/data/cache/materialized-episode-objects-v1/bc-dragapult-archetype-v3.pkl")
EXACT_CACHE = Path("/data/cache/materialized-episode-objects-v1/bc-dragapult-hq-v2.pkl")

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

app = modal.App("kptcg-bc-gpu-speed-benchmark", image=image)
training_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)


def _run_benchmark(batch_size: int, speed_train_limit: int, speed_validation_limit: int) -> dict[str, Any]:
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
        "/tmp/kptcg-bc-gpu-speed-benchmark",
        "--device",
        "cuda",
        "--model-labels",
        "3.7m",
        "--batch-size-candidates",
        str(batch_size),
        "--learning-rate-candidates",
        "0.00005",
        "--sequence-length",
        "32",
        "--speed-train-limit",
        str(speed_train_limit),
        "--speed-validation-limit",
        str(speed_validation_limit),
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
        "--speed-only",
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert process.stdout is not None
    speed_row: dict[str, Any] | None = None
    for line in process.stdout:
        print(line, end="", flush=True)
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("event") == "capacity_speed_smoke":
            speed_row = event
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(f"GPU speed benchmark failed with exit code {return_code}")
    if speed_row is None:
        raise RuntimeError("GPU speed benchmark completed without capacity_speed_smoke telemetry")
    return speed_row


@app.function(
    gpu="T4",
    cpu=16,
    memory=65536,
    ephemeral_disk=524288,
    timeout=30 * 60,
    volumes={"/data": training_volume},
)
def run_t4(batch_size: int, speed_train_limit: int, speed_validation_limit: int) -> dict[str, Any]:
    return _run_benchmark(batch_size, speed_train_limit, speed_validation_limit)


@app.function(
    gpu="RTX-PRO-6000",
    cpu=16,
    memory=65536,
    ephemeral_disk=524288,
    timeout=30 * 60,
    volumes={"/data": training_volume},
)
def run_rtx(batch_size: int, speed_train_limit: int, speed_validation_limit: int) -> dict[str, Any]:
    return _run_benchmark(batch_size, speed_train_limit, speed_validation_limit)


@app.local_entrypoint()
def main(
    gpu_type: str = "t4",
    batch_size: int = 32,
    speed_train_limit: int = 256,
    speed_validation_limit: int = 64,
) -> None:
    if gpu_type == "t4":
        result = run_t4.remote(batch_size, speed_train_limit, speed_validation_limit)
    elif gpu_type == "rtx-pro-6000":
        result = run_rtx.remote(batch_size, speed_train_limit, speed_validation_limit)
    else:
        raise ValueError("gpu_type must be 't4' or 'rtx-pro-6000'")
    print(json.dumps({"event": "gpu_speed_benchmark_result", "gpu_type": gpu_type, **result}, sort_keys=True))
