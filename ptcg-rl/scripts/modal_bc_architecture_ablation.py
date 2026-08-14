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
MATERIALIZED_TAR = Path("/data/materialized/bc-dragapult-archetype-v3.tar")
MATERIALIZED_TAR_SHA256 = Path("/data/materialized/bc-dragapult-archetype-v3.tar.sha256")
EXPECTED_TAR_SHA256 = "c21694a3e5d6a68e7be55ae7dcb749258fbba0ef921e5a769d22281f6d6e2a2b"
LOCAL_TAR = Path("/tmp/bc-dragapult-archetype-v3.tar")
LOCAL_DIR = Path("/tmp/bc-dragapult-archetype-v3")
REPORT_PATH = Path("/data/reports/bc-dragapult-option-entity-cross-attention-ablation-v1.json")

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
        PTCG_RL / "scripts/bc_architecture_ablation.py",
        remote_path="/workspace/ptcg-rl/scripts/bc_architecture_ablation.py",
    )
    .add_local_file(
        PTCG_RL / "private/g2/card-table-v1.json",
        remote_path="/workspace/ptcg-rl/private/g2/card-table-v1.json",
    )
)

app = modal.App("kptcg-bc-dragapult-architecture-ablation", image=image)
training_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stage_materialized() -> dict[str, Any]:
    if not MATERIALIZED_TAR.is_file() or not MATERIALIZED_TAR_SHA256.is_file():
        raise RuntimeError("Dragapult archetype v3 materialized tar or SHA sidecar is missing")
    sidecar = MATERIALIZED_TAR_SHA256.read_text(encoding="ascii").strip()
    if sidecar != EXPECTED_TAR_SHA256:
        raise RuntimeError(
            f"materialized tar sidecar differs: expected {EXPECTED_TAR_SHA256}, observed {sidecar}"
        )
    digest = hashlib.sha256()
    total = 0
    LOCAL_TAR.unlink(missing_ok=True)
    with MATERIALIZED_TAR.open("rb") as source, LOCAL_TAR.open("wb") as destination:
        while True:
            chunk = source.read(16 * 1024 * 1024)
            if not chunk:
                break
            destination.write(chunk)
            digest.update(chunk)
            total += len(chunk)
    observed = digest.hexdigest()
    if observed != EXPECTED_TAR_SHA256:
        LOCAL_TAR.unlink(missing_ok=True)
        raise RuntimeError(
            f"materialized tar SHA-256 differs: expected {EXPECTED_TAR_SHA256}, observed {observed}"
        )
    if LOCAL_DIR.exists():
        shutil.rmtree(LOCAL_DIR)
    LOCAL_DIR.mkdir(parents=True)
    subprocess.run(["tar", "-xf", str(LOCAL_TAR), "-C", str(LOCAL_DIR)], check=True)
    if not (LOCAL_DIR / "manifest.json").is_file():
        raise RuntimeError("staged Dragapult materialized cache has no manifest")
    receipt = {
        "source": str(MATERIALIZED_TAR),
        "local_tar": str(LOCAL_TAR),
        "local_dir": str(LOCAL_DIR),
        "tar_sha256": observed,
        "tar_bytes": total,
    }
    print(json.dumps({"event": "architecture_ablation_materialized_staged", **receipt}, sort_keys=True), flush=True)
    return receipt


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
        if len(tail) > 200:
            tail.pop(0)
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(
            f"architecture ablation subprocess failed with exit code {return_code}; tail="
            + "\n".join(tail[-40:])
        )


@app.function(
    gpu="RTX-PRO-6000",
    cpu=16,
    memory=98304,
    ephemeral_disk=524288,
    timeout=2 * 60 * 60,
    volumes={"/data": training_volume},
)
def run(force: bool = False) -> dict[str, Any]:
    stage = _stage_materialized()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if REPORT_PATH.exists():
        if not force:
            report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
            return {
                "status": "EXISTS",
                "report_path": str(REPORT_PATH),
                "report_sha256": _sha256_file(REPORT_PATH),
                "winner": report.get("provisional_validation_winner"),
                "parameter_counts": report.get("parameter_counts"),
                "chosen_speed_config": report.get("chosen_speed_config"),
                "best_by_variant": report.get("best_by_variant"),
                "materialized_stage": stage,
            }
        REPORT_PATH.unlink()

    command = [
        "python",
        "/workspace/ptcg-rl/scripts/bc_architecture_ablation.py",
        "--materialized-dir",
        str(LOCAL_DIR),
        "--card-table",
        "/workspace/ptcg-rl/private/g2/card-table-v1.json",
        "--output",
        str(REPORT_PATH),
        "--device",
        "cuda",
        "--seed",
        "20260815",
        "--loader-workers",
        "16",
        "--speed-batch-sizes",
        "256",
        "--speed-sequence-lengths",
        "32",
        "--learning-rates",
        "0.00001,0.000025,0.00005",
        "--learning-epochs",
        "3",
        "--learning-train-limit",
        "256",
        "--learning-validation-limit",
        "64",
        "--weight-decay",
        "0.0001",
        "--maximum-gradient-norm",
        "1.0",
        "--bf16",
    ]
    _run_stream(command)
    if not REPORT_PATH.is_file():
        raise RuntimeError("architecture ablation completed without report")
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    if report.get("status") != "PASS_ARCHITECTURE_ABLATION_COMPLETED":
        raise RuntimeError("architecture ablation report did not PASS")
    training_volume.commit()
    return {
        "status": report["status"],
        "report_path": str(REPORT_PATH),
        "report_sha256": _sha256_file(REPORT_PATH),
        "winner": report["provisional_validation_winner"],
        "parameter_counts": report["parameter_counts"],
        "chosen_speed_config": report["chosen_speed_config"],
        "best_by_variant": report["best_by_variant"],
        "materialized_stage": stage,
    }


@app.local_entrypoint()
def main(force: bool = False) -> None:
    print(json.dumps(run.remote(force=force), indent=2, sort_keys=True))
