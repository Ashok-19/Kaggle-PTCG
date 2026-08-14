from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import modal


if modal.is_local():
    ROOT = Path(__file__).resolve().parents[2]
else:
    ROOT = Path("/workspace")

PTCG_RL = ROOT / "ptcg-rl"
GPU_CABT = ROOT / "gpu-cabt"
OFFICIAL = ROOT / "pokemon-tcg-ai-battle/ptcg_engine/ptcgProgram 22"
LOCAL_CACHE = ROOT / ".cache/bc-training-runs"
BC_CHECKPOINT_SHA256 = "a6a136f2f0012b40ce67ea3eccbbf005ec0cd22d2670a02eeaf52843c6f29cc4"
VOLUME_NAME = "kptcg-training"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("g++")
    .run_commands(
        "python -m pip install --no-cache-dir numpy==2.0.2",
        "python -m pip install --no-cache-dir torch==2.10.0 "
        "--index-url https://download.pytorch.org/whl/cu130",
        "python -m pip install --no-cache-dir cupy-cuda12x==14.1.1 "
        "nvidia-cuda-nvrtc-cu12==12.9.86",
    )
    .add_local_dir(PTCG_RL / "src", remote_path="/workspace/ptcg-rl/src")
    .add_local_file(
        PTCG_RL / "scripts/ppo_gpu_selfplay_smoke.py",
        remote_path="/workspace/ptcg-rl/scripts/ppo_gpu_selfplay_smoke.py",
    )
    .add_local_file(
        PTCG_RL / "private/g2/checkpoint-v1/g2-policy-checkpoint-v1.zip",
        remote_path="/workspace/ptcg-rl/private/g2/checkpoint-v1/g2-policy-checkpoint-v1.zip",
    )
    .add_local_file(
        LOCAL_CACHE / "bc-current-lucario-fast-v2-files/epoch-1.pt",
        remote_path="/workspace/inputs/bc/epoch-1.pt",
    )
    .add_local_file(
        LOCAL_CACHE / "bc-current-lucario-fast-v2-files/epoch-1.pt.manifest.json",
        remote_path="/workspace/inputs/bc/epoch-1.pt.manifest.json",
    )
    .add_local_file(
        LOCAL_CACHE / "current-majkel-luca-lucario-deck.csv",
        remote_path="/workspace/inputs/current-lucario.csv",
    )
    .add_local_dir(GPU_CABT / "src", remote_path="/workspace/gpu-cabt/src")
    .add_local_file(
        GPU_CABT / "scripts/gpu_cabt_rule_extract.cpp",
        remote_path="/workspace/gpu-cabt/scripts/gpu_cabt_rule_extract.cpp",
    )
    .add_local_dir(OFFICIAL, remote_path="/workspace/official-engine")
)

app = modal.App("kptcg-ppo-smoke", image=image)
training_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)


@app.function(
    gpu="RTX-PRO-6000",
    timeout=20 * 60,
    volumes={"/data": training_volume},
)
def smoke(env_count: int = 16, seed: int = 20260814) -> dict[str, object]:
    if env_count <= 0 or env_count > 512:
        raise ValueError("PPO smoke env_count must stay within 1..512")
    output_dir = Path(f"/data/runs/ppo-smoke-v1-e{env_count}-s{seed}")
    output_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = "/workspace/ptcg-rl/src:/workspace/gpu-cabt/src"
    env["GPU_CABT_OFFICIAL_DIR"] = "/workspace/official-engine"
    env["GPU_CABT_NVRTC_FAST_COMPILE"] = "max"
    command = [
        "python",
        "/workspace/ptcg-rl/scripts/ppo_gpu_selfplay_smoke.py",
        "--checkpoint-package",
        "/workspace/ptcg-rl/private/g2/checkpoint-v1/g2-policy-checkpoint-v1.zip",
        "--bc-checkpoint",
        "/workspace/inputs/bc/epoch-1.pt",
        "--bc-checkpoint-sha256",
        BC_CHECKPOINT_SHA256,
        "--deck",
        "/workspace/inputs/current-lucario.csv",
        "--output-dir",
        str(output_dir),
        "--env-count",
        str(env_count),
        "--seed",
        str(seed),
        "--max-boundaries",
        "3000",
        "--gamma",
        "0.999",
        "--gae-lambda",
        "0.95",
        "--clip-coefficient",
        "0.2",
        "--value-clip-coefficient",
        "0.2",
        "--value-coefficient",
        "0.5",
        "--entropy-coefficient",
        "0.01",
        "--learning-rate",
        "0.00003",
        "--max-gradient-norm",
        "1.0",
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )
    assert process.stdout is not None
    tail: list[str] = []
    for line in process.stdout:
        print(line, end="", flush=True)
        tail.append(line.rstrip())
        if len(tail) > 100:
            tail.pop(0)
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(
            f"PPO smoke exited {return_code}; tail=" + "\n".join(tail[-30:])
        )
    report_path = output_dir / "ppo-smoke-report.json"
    if not report_path.is_file():
        raise RuntimeError("PPO smoke completed without its report")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("status") != "PASS" or report.get("full_run_authorized") is not False:
        raise RuntimeError("PPO smoke report did not satisfy the smoke-only contract")
    training_volume.commit()
    return report


@app.local_entrypoint()
def main(env_count: int = 16, seed: int = 20260814) -> None:
    result = smoke.remote(env_count=env_count, seed=seed)
    print(json.dumps(result, indent=2, sort_keys=True))
