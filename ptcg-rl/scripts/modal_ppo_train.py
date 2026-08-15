from __future__ import annotations

import json
import os
import re
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
VOLUME_NAME = "kptcg-training"
MODEL_LABEL = "3.7m"
V7_CHECKPOINT_RELATIVE = "runs/bc-dragapult-final-v7-live-rehearsal/3.7m/final-selected.pt"
MAX_BOUNDED_DECISIONS = 30_000_000

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
        PTCG_RL / "scripts/ppo_gpu_train.py",
        remote_path="/workspace/ptcg-rl/scripts/ppo_gpu_train.py",
    )
    .add_local_file(
        PTCG_RL / "private/g2/card-table-v1.json",
        remote_path="/workspace/ptcg-rl/private/g2/card-table-v1.json",
    )
    .add_local_file(
        PTCG_RL / "private/baselines/dragapult-ex/deck.csv",
        remote_path="/workspace/inputs/dragapult-ex.csv",
    )
    .add_local_dir(GPU_CABT / "src", remote_path="/workspace/gpu-cabt/src")
    .add_local_file(
        GPU_CABT / "scripts/gpu_cabt_rule_extract.cpp",
        remote_path="/workspace/gpu-cabt/scripts/gpu_cabt_rule_extract.cpp",
    )
    .add_local_dir(OFFICIAL, remote_path="/workspace/official-engine")
)

app = modal.App("kptcg-ppo-train", image=image)
training_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
    return ordered[index]


def _telemetry_summary(raw: str) -> dict[str, object]:
    samples: list[tuple[float, float, float]] = []
    for line in raw.splitlines():
        fields = [field.strip() for field in line.split(",")]
        if len(fields) != 3:
            continue
        try:
            values = tuple(float(field) for field in fields)
        except ValueError:
            continue
        if len(values) == 3:
            samples.append((values[0], values[1], values[2]))
    if not samples:
        return {"samples": 0}
    utilization = [row[0] for row in samples]
    memory = [row[1] for row in samples]
    power = [row[2] for row in samples]
    return {
        "samples": len(samples),
        "utilization_mean_percent": sum(utilization) / len(utilization),
        "utilization_p95_percent": _percentile(utilization, 0.95),
        "utilization_peak_percent": max(utilization),
        "memory_mean_mib": sum(memory) / len(memory),
        "memory_p95_mib": _percentile(memory, 0.95),
        "memory_peak_mib": max(memory),
        "power_mean_watts": sum(power) / len(power),
        "power_p95_watts": _percentile(power, 0.95),
        "power_peak_watts": max(power),
    }


@app.function(
    gpu="RTX-PRO-6000",
    timeout=90 * 60,
    volumes={"/data": training_volume},
)
def train(
    run_id: str,
    decision_budget: int,
    source_commit: str,
    env_count: int = 8192,
    chunk_boundaries: int = 64,
    learner_lane_envs: int = 1024,
    seed: int = 20260815,
    resume_relative: str = "",
    resume_sha256: str = "",
) -> dict[str, object]:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", run_id):
        raise ValueError("run_id contains unsupported characters")
    if decision_budget <= 0 or decision_budget > MAX_BOUNDED_DECISIONS:
        raise ValueError("decision budget must remain within the bounded 1..30M envelope")
    if env_count <= 0 or env_count > 8192:
        raise ValueError("env_count must stay within 1..8192")
    if chunk_boundaries < 16 or chunk_boundaries > 128:
        raise ValueError("chunk boundaries must stay within 16..128")
    if learner_lane_envs <= 0 or learner_lane_envs > env_count:
        raise ValueError("learner lane envs must stay within 1..env_count")
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("source commit must be an exact 40-character Git SHA")
    if bool(resume_relative) != bool(resume_sha256):
        raise ValueError("resume path and SHA-256 must be supplied together")

    output_dir = Path("/data/runs") / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = "/workspace/ptcg-rl/src:/workspace/gpu-cabt/src"
    env["GPU_CABT_OFFICIAL_DIR"] = "/workspace/official-engine"
    env["GPU_CABT_NVRTC_FAST_COMPILE"] = "max"
    command = [
        "python",
        "/workspace/ptcg-rl/scripts/ppo_gpu_train.py",
        "--card-table",
        "/workspace/ptcg-rl/private/g2/card-table-v1.json",
        "--model-label",
        MODEL_LABEL,
        "--bc-checkpoint",
        str(Path("/data") / V7_CHECKPOINT_RELATIVE),
        "--deck",
        "/workspace/inputs/dragapult-ex.csv",
        "--output-dir",
        str(output_dir),
        "--source-commit",
        source_commit,
        "--env-count",
        str(env_count),
        "--decision-budget",
        str(decision_budget),
        "--chunk-boundaries",
        str(chunk_boundaries),
        "--learner-lane-envs",
        str(learner_lane_envs),
        "--seed",
        str(seed),
        "--historical-fraction",
        "0.20",
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
        "--bf16",
    ]
    if resume_relative:
        if resume_relative.startswith("/") or ".." in Path(resume_relative).parts:
            raise ValueError("resume path must be a safe /data-relative path")
        if not re.fullmatch(r"[0-9a-f]{64}", resume_sha256):
            raise ValueError("resume SHA-256 must be exact")
        command.extend(
            [
                "--resume-checkpoint",
                str(Path("/data") / resume_relative),
                "--resume-checkpoint-sha256",
                resume_sha256,
            ]
        )

    telemetry = subprocess.Popen(
        [
            "nvidia-smi",
            "--query-gpu=utilization.gpu,memory.used,power.draw",
            "--format=csv,noheader,nounits",
            "--loop-ms=250",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    process = subprocess.Popen(
        command,
        env=env,
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
        if len(tail) > 120:
            tail.pop(0)
    return_code = process.wait()
    telemetry.terminate()
    telemetry_output, _ = telemetry.communicate(timeout=5)
    if return_code != 0:
        raise RuntimeError(
            f"production PPO trainer exited {return_code}; tail=" + "\n".join(tail[-40:])
        )
    report_path = output_dir / "training-report.json"
    if not report_path.is_file():
        raise RuntimeError("production PPO trainer completed without its report")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("status") != "PASS" or report.get("full_unbounded_run_authorized") is not False:
        raise RuntimeError("production PPO report violated the bounded-run contract")
    report["gpu_telemetry"] = _telemetry_summary(telemetry_output)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    training_volume.commit()
    return report


@app.local_entrypoint()
def main(
    run_id: str,
    decision_budget: int,
    env_count: int = 8192,
    chunk_boundaries: int = 64,
    learner_lane_envs: int = 1024,
    seed: int = 20260815,
    resume_relative: str = "",
    resume_sha256: str = "",
) -> None:
    source_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    result = train.remote(
        run_id=run_id,
        decision_budget=decision_budget,
        source_commit=source_commit,
        env_count=env_count,
        chunk_boundaries=chunk_boundaries,
        learner_lane_envs=learner_lane_envs,
        seed=seed,
        resume_relative=resume_relative,
        resume_sha256=resume_sha256,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
