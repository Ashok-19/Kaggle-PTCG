from __future__ import annotations

import json
import os
import re
import select
import subprocess
import time
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
V6_CHECKPOINT_RELATIVE = "runs/bc-dragapult-final-v6-live-continue/3.7m/final-selected.pt"
V7_CHECKPOINT_RELATIVE = "runs/bc-dragapult-final-v7-live-rehearsal/3.7m/final-selected.pt"
V5_CHECKPOINT_RELATIVE = "runs/bc-dragapult-final-v5-schema-v3-fused-update-density/3.7m/3.7m/stage-d-exact-1150-best.pt"
LIVE_BC_ROOT = "/data/materialized/bc-dragapult-live-v6-featurefix-v3"
EXACT_BC_ROOT = "/data/materialized/bc-dragapult-hq-v2-featurefix-v3"
MAX_BOUNDED_DECISIONS = 30_000_000
REQUIRED_MODAL_PROFILE = "ashokraja863801"


def _require_modal_profile() -> None:
    if not modal.is_local():
        return
    active = subprocess.check_output(
        ["modal", "profile", "current"], text=True
    ).strip()
    if active != REQUIRED_MODAL_PROFILE:
        raise RuntimeError(
            f"refusing Modal operation under profile {active!r}; "
            f"required profile is {REQUIRED_MODAL_PROFILE!r}"
        )


_require_modal_profile()

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


def _stream_child_with_heartbeat(
    process: subprocess.Popen[str],
    *,
    heartbeat_seconds: float,
    run_id: str,
) -> tuple[int, list[str]]:
    if process.stdout is None:
        raise RuntimeError("production PPO child stdout is unavailable")
    tail: list[str] = []
    last_output = time.monotonic()
    last_heartbeat = last_output
    while True:
        ready, _, _ = select.select([process.stdout], [], [], heartbeat_seconds)
        if ready:
            line = process.stdout.readline()
            if line:
                print(line, end="", flush=True)
                tail.append(line.rstrip())
                if len(tail) > 120:
                    tail.pop(0)
                last_output = time.monotonic()
                continue
        return_code = process.poll()
        if return_code is not None:
            for line in process.stdout:
                print(line, end="", flush=True)
                tail.append(line.rstrip())
                if len(tail) > 120:
                    tail.pop(0)
            return return_code, tail
        now = time.monotonic()
        if now - last_heartbeat >= heartbeat_seconds:
            print(
                json.dumps(
                    {
                        "event": "modal_ppo_heartbeat",
                        "run_id": run_id,
                        "child_pid": process.pid,
                        "seconds_since_child_output": round(now - last_output, 3),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            last_heartbeat = now
        if ready:
            # A readable pipe can briefly report EOF before process.poll() observes
            # child exit. Avoid a tight CPU/log loop during that teardown race.
            time.sleep(min(heartbeat_seconds, 0.25))


@app.function(
    gpu="RTX-PRO-6000",
    cpu=32.0,
    memory=131072,
    timeout=90 * 60,
    volumes={"/data": training_volume},
)
def train(
    run_id: str,
    decision_budget: int,
    source_commit: str,
    env_count: int = 8192,
    rollout_horizon: int = 64,
    chunk_boundaries: int = 16,
    learner_lane_envs: int = 2048,
    optimizer_lanes_per_update: int = 1,
    freeze_observation_encoder: bool = True,
    rollout_storage: str = "cuda-compact",
    learning_rate: float = 2e-7,
    critic_learning_rate: float = 3e-4,
    entropy_coefficient: float = 0.0,
    reference_kl_coefficient: float = 0.0,
    bc_anchor_coefficient: float = 0.002,
    frozen_reference_fraction: float = 0.0,
    frozen_v7_fraction: float = 0.0,
    frozen_v5_fraction: float = 0.0,
    heartbeat_seconds: float = 10.0,
    checkpoint_every_updates: int = 10,
    post_validation_lanes: int = 1,
    resume_checkpoint_relative: str = "",
    policy_warmstart_checkpoint_relative: str = "",
    bf16: bool = True,
    seed: int = 20260816,
) -> dict[str, object]:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", run_id):
        raise ValueError("run_id contains unsupported characters")
    if decision_budget <= 0 or decision_budget > MAX_BOUNDED_DECISIONS:
        raise ValueError("decision budget must remain within the bounded 1..30M envelope")
    if env_count <= 0 or env_count > 8192:
        raise ValueError("env_count must stay within 1..8192")
    if rollout_horizon < 16 or rollout_horizon > 256:
        raise ValueError("rollout_horizon must stay within 16..256")
    if chunk_boundaries < 16 or chunk_boundaries > 128:
        raise ValueError("chunk boundaries must stay within 16..128")
    if learner_lane_envs <= 0 or learner_lane_envs > env_count:
        raise ValueError("learner lane envs must stay within 1..env_count")
    if optimizer_lanes_per_update < 0:
        raise ValueError("optimizer_lanes_per_update must be nonnegative")
    if not (0.0 < learning_rate <= 1e-3):
        raise ValueError("learning_rate must stay within (0, 1e-3]")
    if not (0.0 < critic_learning_rate <= 0.1):
        raise ValueError("critic_learning_rate must stay within (0, 0.1]")
    if entropy_coefficient < 0.0:
        raise ValueError("entropy_coefficient must be nonnegative")
    if reference_kl_coefficient < 0.0:
        raise ValueError("reference_kl_coefficient must be nonnegative")
    if bc_anchor_coefficient < 0.0:
        raise ValueError("bc_anchor_coefficient must be nonnegative")
    if not (0.0 <= frozen_reference_fraction <= 1.0):
        raise ValueError("frozen_reference_fraction must stay within [0, 1]")
    if not (0.0 <= frozen_v7_fraction <= 1.0):
        raise ValueError("frozen_v7_fraction must stay within [0, 1]")
    if not (0.0 <= frozen_v5_fraction <= 1.0):
        raise ValueError("frozen_v5_fraction must stay within [0, 1]")
    if frozen_reference_fraction + frozen_v7_fraction + frozen_v5_fraction > 1.0:
        raise ValueError("frozen league fractions must sum to <= 1")
    if heartbeat_seconds <= 0.0 or heartbeat_seconds > 60.0:
        raise ValueError("heartbeat_seconds must stay within (0, 60]")
    if checkpoint_every_updates <= 0:
        raise ValueError("checkpoint_every_updates must be positive")
    if post_validation_lanes <= 0:
        raise ValueError("post_validation_lanes must be positive")
    resume_checkpoint: Path | None = None
    if resume_checkpoint_relative:
        relative = Path(resume_checkpoint_relative)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ValueError("resume checkpoint must be a safe /data-relative path")
        if relative.parts[0] != "runs" or relative.suffix != ".pt":
            raise ValueError("resume checkpoint must point to a .pt file under /data/runs")
        resume_checkpoint = Path("/data") / relative
    policy_warmstart_checkpoint: Path | None = None
    if policy_warmstart_checkpoint_relative:
        relative = Path(policy_warmstart_checkpoint_relative)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ValueError("policy warm-start checkpoint must be a safe /data-relative path")
        if relative.parts[0] != "runs" or relative.suffix != ".pt":
            raise ValueError("policy warm-start checkpoint must point to a .pt file under /data/runs")
        policy_warmstart_checkpoint = Path("/data") / relative
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("source commit must be an exact 40-character Git SHA")

    output_dir = Path("/data/runs") / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    cuda_library_paths = (
        "/usr/local/lib/python3.11/site-packages/nvidia/cu13/lib",
        "/usr/local/lib/python3.11/site-packages/nvidia/cuda_nvrtc/lib",
    )
    env["LD_LIBRARY_PATH"] = ":".join(
        (*cuda_library_paths, env.get("LD_LIBRARY_PATH", ""))
    ).rstrip(":")
    env["PYTHONPATH"] = "/workspace/ptcg-rl/src:/workspace/gpu-cabt/src"
    env["GPU_CABT_OFFICIAL_DIR"] = "/workspace/official-engine"
    env["GPU_CABT_NVRTC_FAST_COMPILE"] = "max"
    env["KPTCG_FAST_VALIDATED_GPU_PATH"] = "1"
    env["PYTORCH_ALLOC_CONF"] = "expandable_segments:True"
    env["OMP_NUM_THREADS"] = "32"
    env["MKL_NUM_THREADS"] = "32"
    command = [
        "python",
        "/workspace/ptcg-rl/scripts/ppo_gpu_train.py",
        "--card-table",
        "/workspace/ptcg-rl/private/g2/card-table-v1.json",
        "--model-label",
        MODEL_LABEL,
        "--bc-checkpoint",
        str(Path("/data") / V6_CHECKPOINT_RELATIVE),
        "--v7-checkpoint",
        str(Path("/data") / V7_CHECKPOINT_RELATIVE),
        "--v5-checkpoint",
        str(Path("/data") / V5_CHECKPOINT_RELATIVE),
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
        "--rollout-horizon",
        str(rollout_horizon),
        "--chunk-boundaries",
        str(chunk_boundaries),
        "--learner-lane-envs",
        str(learner_lane_envs),
        "--optimizer-lanes-per-update",
        str(optimizer_lanes_per_update),
        *( ["--freeze-observation-encoder"] if freeze_observation_encoder else [] ),
        "--rollout-storage",
        rollout_storage,
        "--heartbeat-seconds",
        str(heartbeat_seconds),
        "--checkpoint-every-updates",
        str(checkpoint_every_updates),
        "--post-validation-lanes",
        str(post_validation_lanes),
        "--seed",
        str(seed),
        "--frozen-reference-fraction",
        str(frozen_reference_fraction),
        "--frozen-v7-fraction",
        str(frozen_v7_fraction),
        "--frozen-v5-fraction",
        str(frozen_v5_fraction),
        "--gamma",
        "1.0",
        "--gae-lambda",
        "0.95",
        "--critic-calibration-terminal-trajectories",
        "0",
        "--clip-coefficient",
        "0.2",
        "--value-clip-coefficient",
        "0.2",
        "--value-coefficient",
        "0.5",
        "--entropy-coefficient",
        str(entropy_coefficient),
        "--learning-rate",
        str(learning_rate),
        "--critic-learning-rate",
        str(critic_learning_rate),
        "--reference-kl-coefficient",
        str(reference_kl_coefficient),
        "--bc-anchor-coefficient",
        str(bc_anchor_coefficient),
        "--bc-anchor-live-root",
        LIVE_BC_ROOT,
        "--bc-anchor-exact-root",
        EXACT_BC_ROOT,
        "--max-gradient-norm",
        "1.0",
    ]
    if resume_checkpoint is not None:
        command.extend(["--resume-checkpoint", str(resume_checkpoint)])
    if policy_warmstart_checkpoint is not None:
        command.extend(
            ["--policy-warmstart-checkpoint", str(policy_warmstart_checkpoint)]
        )
    if bf16:
        command.append("--bf16")

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
    telemetry_output = ""
    try:
        return_code, tail = _stream_child_with_heartbeat(
            process,
            heartbeat_seconds=heartbeat_seconds,
            run_id=run_id,
        )
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if telemetry.poll() is None:
            telemetry.terminate()
        try:
            telemetry_output, _ = telemetry.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            telemetry.kill()
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
    rollout_horizon: int = 64,
    chunk_boundaries: int = 16,
    learner_lane_envs: int = 2048,
    optimizer_lanes_per_update: int = 1,
    freeze_observation_encoder: bool = True,
    rollout_storage: str = "cuda-compact",
    learning_rate: float = 2e-7,
    critic_learning_rate: float = 3e-4,
    entropy_coefficient: float = 0.0,
    reference_kl_coefficient: float = 0.0,
    bc_anchor_coefficient: float = 0.002,
    frozen_reference_fraction: float = 0.0,
    frozen_v7_fraction: float = 0.0,
    frozen_v5_fraction: float = 0.0,
    heartbeat_seconds: float = 10.0,
    checkpoint_every_updates: int = 10,
    post_validation_lanes: int = 1,
    resume_checkpoint_relative: str = "",
    policy_warmstart_checkpoint_relative: str = "",
    bf16: bool = True,
    seed: int = 20260816,
) -> None:
    source_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    result = train.remote(
        run_id=run_id,
        decision_budget=decision_budget,
        source_commit=source_commit,
        env_count=env_count,
        rollout_horizon=rollout_horizon,
        chunk_boundaries=chunk_boundaries,
        learner_lane_envs=learner_lane_envs,
        learning_rate=learning_rate,
        optimizer_lanes_per_update=optimizer_lanes_per_update,
        freeze_observation_encoder=freeze_observation_encoder,
        rollout_storage=rollout_storage,
        critic_learning_rate=critic_learning_rate,
        entropy_coefficient=entropy_coefficient,
        reference_kl_coefficient=reference_kl_coefficient,
        bc_anchor_coefficient=bc_anchor_coefficient,
        frozen_reference_fraction=frozen_reference_fraction,
        frozen_v7_fraction=frozen_v7_fraction,
        frozen_v5_fraction=frozen_v5_fraction,
        heartbeat_seconds=heartbeat_seconds,
        checkpoint_every_updates=checkpoint_every_updates,
        post_validation_lanes=post_validation_lanes,
        resume_checkpoint_relative=resume_checkpoint_relative,
        policy_warmstart_checkpoint_relative=policy_warmstart_checkpoint_relative,
        bf16=bf16,
        seed=seed,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
