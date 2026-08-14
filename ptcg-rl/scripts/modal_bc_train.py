from __future__ import annotations

import hashlib
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
BUNDLE_SHA256 = "da8e4b906523c98dfc47e4a39c51170a3c2cfb9ce8e5e764048a68a5d03e25cc"
BUNDLE_PARTS = tuple(f"/data/inputs/bc-current-lucario-specialist-v1/part-{index:02d}" for index in range(6))
WARM_START_PATH = "/data/inputs/bc-recent-hq-v1-r1-epoch-2.pt"
WARM_START_SHA256 = "1d8ad47f1bd2942e4235d69320eba6261a22b2f1891844e7f82d15480b15befe"
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
    run_name: str = "bc-current-lucario-specialist-v1-r1",
    epochs: int = 4,
    batch_size: int = 32,
    sequence_length: int = 32,
    learning_rate: float = 5e-5,
) -> dict[str, Any]:
    output_dir = Path("/data/runs") / run_name
    if output_dir.exists():
        raise RuntimeError(f"training output already exists: {output_dir}")
    bundle_path = Path("/tmp/bc-current-lucario-specialist-v1.zip")
    digest = hashlib.sha256()
    total_bytes = 0
    with bundle_path.open("wb") as destination:
        for part_name in BUNDLE_PARTS:
            part = Path(part_name)
            if not part.is_file():
                raise RuntimeError(f"specialist bundle part is missing: {part}")
            with part.open("rb") as source:
                while True:
                    chunk = source.read(8 * 1024 * 1024)
                    if not chunk:
                        break
                    destination.write(chunk)
                    digest.update(chunk)
                    total_bytes += len(chunk)
    if digest.hexdigest() != BUNDLE_SHA256:
        raise RuntimeError(
            f"reassembled specialist bundle SHA-256 differs: {digest.hexdigest()}"
        )
    warm_start = Path(WARM_START_PATH)
    warm_manifest = warm_start.with_name(warm_start.name + ".manifest.json")
    if not warm_start.is_file() or not warm_manifest.is_file():
        raise RuntimeError("warm-start checkpoint payload or manifest is missing")
    warm_digest = hashlib.sha256(warm_start.read_bytes()).hexdigest()
    if warm_digest != WARM_START_SHA256:
        raise RuntimeError(f"warm-start checkpoint SHA-256 differs: {warm_digest}")
    print(
        json.dumps(
            {
                "event": "specialist_input_preflight",
                "bundle_bytes": total_bytes,
                "bundle_sha256": digest.hexdigest(),
                "warm_start_sha256": warm_digest,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    command = [
        "python",
        "/workspace/ptcg-rl/scripts/bc_train.py",
        "--bundle",
        str(bundle_path),
        "--expected-bundle-sha256",
        BUNDLE_SHA256,
        "--warm-start-training-checkpoint",
        WARM_START_PATH,
        "--warm-start-training-checkpoint-sha256",
        WARM_START_SHA256,
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
