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
BUNDLE_SHA256 = "4377b1e514f4dff4f453c1dedcbc4af4e81a3b038296408ba86348da5cfe2434"
VOLUME_NAME = "kptcg-training"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .run_commands(
        "python -m pip install --no-cache-dir numpy==2.0.2",
        "python -m pip install --no-cache-dir torch==2.10.0 "
        "--index-url https://download.pytorch.org/whl/cu130",
    )
    .add_local_dir(PTCG_RL / "src", remote_path="/workspace/ptcg-rl/src")
    .add_local_file(
        PTCG_RL / "scripts/bc_train.py",
        remote_path="/workspace/ptcg-rl/scripts/bc_train.py",
    )
    .add_local_file(
        PTCG_RL / "private/g2/card-table-v1.json",
        remote_path="/workspace/ptcg-rl/private/g2/card-table-v1.json",
    )
    .add_local_file(
        PTCG_RL / "private/g2/checkpoint-v1/g2-policy-checkpoint-v1.zip",
        remote_path="/workspace/ptcg-rl/private/g2/checkpoint-v1/g2-policy-checkpoint-v1.zip",
    )
)

app = modal.App("kptcg-bc-production", image=image)
training_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)


@app.function(
    gpu="RTX-PRO-6000",
    cpu=4,
    memory=32768,
    timeout=7200,
    volumes={"/data": training_volume},
)
def run(
    run_name: str = "bc-recent-hq-v1-r1",
    epochs: int = 2,
    batch_size: int = 32,
    sequence_length: int = 32,
    learning_rate: float = 1e-4,
) -> dict[str, Any]:
    output_dir = Path("/data/runs") / run_name
    if output_dir.exists():
        raise RuntimeError(f"training output already exists: {output_dir}")
    command = [
        "python",
        "/workspace/ptcg-rl/scripts/bc_train.py",
        "--bundle",
        "/data/inputs/bc-recent-hq-v1.zip",
        "--expected-bundle-sha256",
        BUNDLE_SHA256,
        "--checkpoint",
        "/workspace/ptcg-rl/private/g2/checkpoint-v1/g2-policy-checkpoint-v1.zip",
        "--card-table",
        "/workspace/ptcg-rl/private/g2/card-table-v1.json",
        "--output-dir",
        str(output_dir),
        "--device",
        "cuda",
        "--epochs",
        str(epochs),
        "--batch-size",
        str(batch_size),
        "--sequence-length",
        str(sequence_length),
        "--learning-rate",
        str(learning_rate),
        "--bf16",
    ]
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
        if len(tail) > 200:
            tail.pop(0)
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(
            f"BC training failed with exit code {return_code}; tail=" + "\n".join(tail[-30:])
        )
    report_path = output_dir / "training-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    training_volume.commit()
    return {
        "status": report["status"],
        "run_name": run_name,
        "volume": VOLUME_NAME,
        "remote_output": f"/runs/{run_name}",
        "best_epoch": report["best_epoch"],
        "baseline_validation_mean_nll": report["baseline_validation_mean_nll"],
        "best_validation_mean_nll": report["best_validation_mean_nll"],
        "selected_checkpoint_for_evaluation": report["selected_checkpoint_for_evaluation"],
        "elapsed_seconds": report["elapsed_seconds"],
        "history": report["history"],
        "gpu": report["gpu"],
        "memory": report["memory"],
    }
