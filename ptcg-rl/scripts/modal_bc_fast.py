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
BUNDLE_SHA256 = "da8e4b906523c98dfc47e4a39c51170a3c2cfb9ce8e5e764048a68a5d03e25cc"
BUNDLE_PARTS = tuple(
    f"/data/inputs/bc-current-lucario-specialist-v1/part-{index:02d}" for index in range(6)
)
MATERIALIZED_DIR = "/data/materialized/bc-current-lucario-specialist-v1"
MATERIALIZED_TAR = "/data/materialized/bc-current-lucario-specialist-v1.tar"
MATERIALIZED_TAR_SHA256 = "/data/materialized/bc-current-lucario-specialist-v1.tar.sha256"
WARM_START_PATH = "/data/runs/bc-current-lucario-specialist-v1-r1/epoch-2.pt"
WARM_START_SHA256 = "822fc1bf2312ff1d2bdab02a5ba24c5ab2b491f8a8b7ca89c80ad901c8d47f17"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .run_commands(
        "python -m pip install --no-cache-dir numpy==2.0.2",
        "python -m pip install --no-cache-dir torch==2.10.0 "
        "--index-url https://download.pytorch.org/whl/cu130",
    )
    .add_local_dir(PTCG_RL / "src", remote_path="/workspace/ptcg-rl/src")
    .add_local_file(
        PTCG_RL / "scripts/bc_materialize.py",
        remote_path="/workspace/ptcg-rl/scripts/bc_materialize.py",
    )
    .add_local_file(
        PTCG_RL / "scripts/bc_train_materialized.py",
        remote_path="/workspace/ptcg-rl/scripts/bc_train_materialized.py",
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

app = modal.App("kptcg-bc-fast", image=image)
training_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)


def _reassemble_bundle() -> Path:
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
    observed = digest.hexdigest()
    if observed != BUNDLE_SHA256:
        raise RuntimeError(f"specialist bundle SHA-256 differs: {observed}")
    print(
        json.dumps(
            {
                "event": "specialist_bundle_preflight",
                "bundle_bytes": total_bytes,
                "bundle_sha256": observed,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return bundle_path


def _run_stream(command: list[str]) -> list[str]:
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
            f"subprocess failed with exit code {return_code}; tail=" + "\n".join(tail[-30:])
        )
    return tail


def _run_stream_with_gpu_telemetry(command: list[str]) -> tuple[list[str], dict[str, float]]:
    telemetry_path = Path("/tmp/kptcg-gpu-telemetry.csv")
    telemetry_path.unlink(missing_ok=True)
    with telemetry_path.open("w", encoding="utf-8") as telemetry_handle:
        sampler = subprocess.Popen(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,power.draw",
                "--format=csv,noheader,nounits",
                "--loop-ms=500",
            ],
            stdout=telemetry_handle,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        try:
            tail = _run_stream(command)
        finally:
            sampler.terminate()
            try:
                sampler.wait(timeout=5)
            except subprocess.TimeoutExpired:
                sampler.kill()
                sampler.wait()
    utilization: list[float] = []
    memory_mib: list[float] = []
    power_watts: list[float] = []
    if telemetry_path.is_file():
        for line in telemetry_path.read_text(encoding="utf-8").splitlines():
            fields = [field.strip() for field in line.split(",")]
            if len(fields) != 3:
                continue
            try:
                utilization.append(float(fields[0]))
                memory_mib.append(float(fields[1]))
                power_watts.append(float(fields[2]))
            except ValueError:
                continue
    if not utilization:
        raise RuntimeError("GPU telemetry produced no samples")
    telemetry = {
        "samples": float(len(utilization)),
        "utilization_mean_percent": sum(utilization) / len(utilization),
        "utilization_peak_percent": max(utilization),
        "memory_mean_mib": sum(memory_mib) / len(memory_mib),
        "memory_peak_mib": max(memory_mib),
        "power_mean_watts": sum(power_watts) / len(power_watts),
        "power_peak_watts": max(power_watts),
    }
    print(json.dumps({"event": "gpu_telemetry", **telemetry}, sort_keys=True), flush=True)
    return tail, telemetry


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ensure_materialized_tar(target: Path) -> dict[str, Any]:
    tar_path = Path(MATERIALIZED_TAR)
    sha_path = Path(MATERIALIZED_TAR_SHA256)
    if tar_path.is_file() and sha_path.is_file():
        return {
            "tar_path": str(tar_path),
            "tar_sha256": sha_path.read_text(encoding="ascii").strip(),
            "tar_bytes": tar_path.stat().st_size,
        }
    partial = tar_path.with_suffix(".tar.partial")
    partial.unlink(missing_ok=True)
    subprocess.run(["tar", "-cf", str(partial), "-C", str(target), "."], check=True)
    digest = _sha256_path(partial)
    partial.replace(tar_path)
    sha_path.write_text(digest + "\n", encoding="ascii")
    receipt = {
        "tar_path": str(tar_path),
        "tar_sha256": digest,
        "tar_bytes": tar_path.stat().st_size,
    }
    print(json.dumps({"event": "materialized_tar_ready", **receipt}, sort_keys=True), flush=True)
    return receipt


def _stage_materialized_tar() -> tuple[Path, dict[str, Any]]:
    source = Path(MATERIALIZED_TAR)
    sha_path = Path(MATERIALIZED_TAR_SHA256)
    if not source.is_file() or not sha_path.is_file():
        raise RuntimeError("materialized tar or SHA-256 sidecar is missing")
    expected = sha_path.read_text(encoding="ascii").strip()
    local_tar = Path("/tmp/bc-current-lucario-specialist-v1.tar")
    digest = hashlib.sha256()
    total = 0
    with source.open("rb") as src, local_tar.open("wb") as dst:
        while True:
            chunk = src.read(16 * 1024 * 1024)
            if not chunk:
                break
            dst.write(chunk)
            digest.update(chunk)
            total += len(chunk)
    observed = digest.hexdigest()
    if observed != expected:
        raise RuntimeError(
            f"materialized tar SHA-256 differs: expected {expected}, observed {observed}"
        )
    local_dir = Path("/tmp/bc-current-lucario-specialist-v1")
    if local_dir.exists():
        shutil.rmtree(local_dir)
    local_dir.mkdir(parents=True)
    subprocess.run(["tar", "-xf", str(local_tar), "-C", str(local_dir)], check=True)
    if not (local_dir / "manifest.json").is_file():
        raise RuntimeError("staged materialized tar has no manifest")
    receipt = {
        "tar_sha256": observed,
        "tar_bytes": total,
        "local_dir": str(local_dir),
    }
    print(json.dumps({"event": "materialized_tar_staged", **receipt}, sort_keys=True), flush=True)
    return local_dir, receipt


@app.function(
    cpu=16,
    memory=65536,
    timeout=3600,
    volumes={"/data": training_volume},
)
def materialize(force: bool = False) -> dict[str, Any]:
    target = Path(MATERIALIZED_DIR)
    if target.exists():
        if not force:
            manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
            archive = _ensure_materialized_tar(target)
            training_volume.commit()
            return {
                "status": "EXISTS",
                "manifest_sha256": manifest["manifest_sha256"],
                "summary": manifest["summary"],
                "archive": archive,
            }
        shutil.rmtree(target)
        Path(MATERIALIZED_TAR).unlink(missing_ok=True)
        Path(MATERIALIZED_TAR_SHA256).unlink(missing_ok=True)
    bundle = _reassemble_bundle()
    command = [
        "python",
        "/workspace/ptcg-rl/scripts/bc_materialize.py",
        "--bundle",
        str(bundle),
        "--expected-bundle-sha256",
        BUNDLE_SHA256,
        "--card-table",
        "/workspace/ptcg-rl/private/g2/card-table-v1.json",
        "--output-dir",
        MATERIALIZED_DIR,
        "--workers",
        "16",
        "--record-id",
        "bc-current-lucario-specialist-materialized-v1",
    ]
    _run_stream(command)
    archive = _ensure_materialized_tar(target)
    training_volume.commit()
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    return {
        "status": manifest["status"],
        "manifest_sha256": manifest["manifest_sha256"],
        "summary": manifest["summary"],
        "archive": archive,
    }


@app.function(
    gpu="RTX-PRO-6000",
    cpu=16,
    memory=98304,
    timeout=3600,
    volumes={"/data": training_volume},
)
def benchmark(
    batch_size: int = 512,
    sequence_length: int = 32,
    train_limit: int = 512,
    validation_limit: int = 64,
) -> dict[str, Any]:
    materialized, stage_receipt = _stage_materialized_tar()
    warm_start = Path(WARM_START_PATH)
    warm_manifest = warm_start.with_name(warm_start.name + ".manifest.json")
    if not warm_start.is_file() or not warm_manifest.is_file():
        raise RuntimeError("specialist warm-start checkpoint is missing")
    observed_warm_sha = hashlib.sha256(warm_start.read_bytes()).hexdigest()
    if observed_warm_sha != WARM_START_SHA256:
        raise RuntimeError(f"specialist warm-start SHA-256 differs: {observed_warm_sha}")
    run_name = f"materialized-bench-b{batch_size}-s{sequence_length}-n{train_limit}"
    output_dir = Path("/data/benchmarks") / run_name
    if output_dir.exists():
        shutil.rmtree(output_dir)
    command = [
        "python",
        "/workspace/ptcg-rl/scripts/bc_train_materialized.py",
        "--materialized-dir",
        str(materialized),
        "--checkpoint",
        "/workspace/ptcg-rl/private/g2/checkpoint-v1/g2-policy-checkpoint-v1.zip",
        "--card-table",
        "/workspace/ptcg-rl/private/g2/card-table-v1.json",
        "--warm-start-training-checkpoint",
        WARM_START_PATH,
        "--warm-start-training-checkpoint-sha256",
        WARM_START_SHA256,
        "--output-dir",
        str(output_dir),
        "--device",
        "cuda",
        "--epochs",
        "1",
        "--batch-size",
        str(batch_size),
        "--sequence-length",
        str(sequence_length),
        "--learning-rate",
        "0.000025",
        "--loader-workers",
        "16",
        "--train-limit",
        str(train_limit),
        "--validation-limit",
        str(validation_limit),
        "--maximum-train-groups",
        "1",
        "--maximum-validation-groups",
        "1",
        "--bf16",
    ]
    _, telemetry = _run_stream_with_gpu_telemetry(command)
    report = json.loads((output_dir / "training-report.json").read_text(encoding="utf-8"))
    training_volume.commit()
    epoch = report["history"][1]["training"]
    validation = report["history"][1]["validation"]
    return {
        "status": report["status"],
        "batch_size": batch_size,
        "sequence_length": sequence_length,
        "train_limit": train_limit,
        "training_policy_targets": epoch["policy_targets"],
        "training_targets_per_second": epoch["policy_targets_per_second"],
        "training_elapsed_seconds": epoch["elapsed_seconds"],
        "optimizer_steps": epoch["optimizer_steps"],
        "validation_mean_nll": validation["mean_nll"],
        "peak_allocated_bytes": report["memory"]["peak_allocated_bytes"],
        "host_peak_rss_kib": report["materialized"]["host_peak_rss_kib"],
        "materialized_load_seconds": report["materialized"]["load_seconds"],
        "gpu": report["gpu"],
        "gpu_telemetry": telemetry,
        "materialized_stage": stage_receipt,
    }


@app.function(
    gpu="RTX-PRO-6000",
    cpu=16,
    memory=98304,
    timeout=7200,
    volumes={"/data": training_volume},
)
def train(
    run_name: str = "bc-current-lucario-materialized-fast-v1",
    batch_size: int = 512,
    sequence_length: int = 32,
    epochs: int = 6,
    learning_rate: float = 2.5e-5,
) -> dict[str, Any]:
    materialized, stage_receipt = _stage_materialized_tar()
    warm_start = Path(WARM_START_PATH)
    observed_warm_sha = hashlib.sha256(warm_start.read_bytes()).hexdigest()
    if observed_warm_sha != WARM_START_SHA256:
        raise RuntimeError(f"specialist warm-start SHA-256 differs: {observed_warm_sha}")
    output_dir = Path("/data/runs") / run_name
    if output_dir.exists():
        raise RuntimeError(f"training output already exists: {output_dir}")
    command = [
        "python",
        "/workspace/ptcg-rl/scripts/bc_train_materialized.py",
        "--materialized-dir",
        str(materialized),
        "--checkpoint",
        "/workspace/ptcg-rl/private/g2/checkpoint-v1/g2-policy-checkpoint-v1.zip",
        "--card-table",
        "/workspace/ptcg-rl/private/g2/card-table-v1.json",
        "--warm-start-training-checkpoint",
        WARM_START_PATH,
        "--warm-start-training-checkpoint-sha256",
        WARM_START_SHA256,
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
        "--loader-workers",
        "16",
        "--bf16",
    ]
    _, telemetry = _run_stream_with_gpu_telemetry(command)
    report = json.loads((output_dir / "training-report.json").read_text(encoding="utf-8"))
    training_volume.commit()
    return {
        "status": report["status"],
        "run_name": run_name,
        "best_epoch": report["best_epoch"],
        "baseline_validation_mean_nll": report["baseline_validation_mean_nll"],
        "best_validation_mean_nll": report["best_validation_mean_nll"],
        "selected_checkpoint_for_evaluation": report["selected_checkpoint_for_evaluation"],
        "history": report["history"],
        "gpu": report["gpu"],
        "memory": report["memory"],
        "materialized": report["materialized"],
        "gpu_telemetry": telemetry,
        "materialized_stage": stage_receipt,
    }
