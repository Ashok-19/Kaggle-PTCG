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

ARCHETYPE_TAR = Path("/data/materialized/bc-dragapult-archetype-v3.tar")
ARCHETYPE_SHA = Path("/data/materialized/bc-dragapult-archetype-v3.tar.sha256")
ARCHETYPE_EXPECTED_SHA256 = "c21694a3e5d6a68e7be55ae7dcb749258fbba0ef921e5a769d22281f6d6e2a2b"
EXACT_TAR = Path("/data/materialized/bc-dragapult-hq-v2.tar")
EXACT_SHA = Path("/data/materialized/bc-dragapult-hq-v2.tar.sha256")
EXACT_EXPECTED_SHA256 = "d7ccdbefe0b04f669a88017ded5d184c2f6448deceda3cc80aaa45c39ed3132d"

LOCAL_ARCHETYPE_TAR = Path("/tmp/bc-dragapult-archetype-v3.tar")
LOCAL_ARCHETYPE_DIR = Path("/tmp/bc-dragapult-archetype-v3")
LOCAL_EXACT_TAR = Path("/tmp/bc-dragapult-hq-v2.tar")
LOCAL_EXACT_DIR = Path("/tmp/bc-dragapult-hq-v2")
OUTPUT_DIR = Path("/data/runs/bc-dragapult-capacity-sweep-v1")
REPORT_PATH = OUTPUT_DIR / "capacity-sweep-report.json"

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

app = modal.App("kptcg-bc-dragapult-capacity-sweep", image=image)
training_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _stage_tar(
    source: Path,
    sidecar: Path,
    expected_sha256: str,
    local_tar: Path,
    local_dir: Path,
    label: str,
) -> dict[str, Any]:
    if not source.is_file() or not sidecar.is_file():
        raise RuntimeError(f"{label} materialized tar or SHA sidecar is missing")
    recorded = sidecar.read_text(encoding="ascii").strip()
    if recorded != expected_sha256:
        raise RuntimeError(
            f"{label} materialized SHA sidecar differs: expected {expected_sha256}, observed {recorded}"
        )
    digest = hashlib.sha256()
    total = 0
    local_tar.unlink(missing_ok=True)
    with source.open("rb") as src, local_tar.open("wb") as dst:
        while True:
            chunk = src.read(16 * 1024 * 1024)
            if not chunk:
                break
            dst.write(chunk)
            digest.update(chunk)
            total += len(chunk)
    observed = digest.hexdigest()
    if observed != expected_sha256:
        local_tar.unlink(missing_ok=True)
        raise RuntimeError(
            f"{label} materialized tar SHA-256 differs: expected {expected_sha256}, observed {observed}"
        )
    if local_dir.exists():
        shutil.rmtree(local_dir)
    local_dir.mkdir(parents=True)
    subprocess.run(["tar", "-xf", str(local_tar), "-C", str(local_dir)], check=True)
    if not (local_dir / "manifest.json").is_file():
        raise RuntimeError(f"staged {label} materialized cache has no manifest")
    receipt = {
        "label": label,
        "source": str(source),
        "local_dir": str(local_dir),
        "tar_sha256": observed,
        "tar_bytes": total,
    }
    print(json.dumps({"event": "capacity_materialized_staged", **receipt}, sort_keys=True), flush=True)
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
                        "event": "capacity_model_volume_committed",
                        "model": event.get("model"),
                        "checkpoint_sha256": event.get("final_checkpoint_sha256"),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(
            f"capacity sweep subprocess failed with exit code {return_code}; tail="
            + "\n".join(tail[-50:])
        )


@app.function(
    gpu="RTX-PRO-6000",
    cpu=16,
    memory=98304,
    ephemeral_disk=524288,
    timeout=8 * 60 * 60,
    volumes={"/data": training_volume},
)
def run(force: bool = False) -> dict[str, Any]:
    archetype_stage = _stage_tar(
        ARCHETYPE_TAR,
        ARCHETYPE_SHA,
        ARCHETYPE_EXPECTED_SHA256,
        LOCAL_ARCHETYPE_TAR,
        LOCAL_ARCHETYPE_DIR,
        "archetype-v3",
    )
    exact_stage = _stage_tar(
        EXACT_TAR,
        EXACT_SHA,
        EXACT_EXPECTED_SHA256,
        LOCAL_EXACT_TAR,
        LOCAL_EXACT_DIR,
        "exact-v2",
    )
    if OUTPUT_DIR.exists():
        if REPORT_PATH.is_file() and not force:
            report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
            return {
                "status": "EXISTS",
                "report_path": str(REPORT_PATH),
                "report_sha256": _sha256_file(REPORT_PATH),
                "validation_ranking": report.get("validation_ranking"),
                "materialized_stage": [archetype_stage, exact_stage],
            }
        if not force:
            raise RuntimeError(f"partial capacity sweep output exists: {OUTPUT_DIR}")
        shutil.rmtree(OUTPUT_DIR)
    OUTPUT_DIR.mkdir(parents=True)

    command = [
        "python",
        "/workspace/ptcg-rl/scripts/bc_capacity_sweep.py",
        "--archetype-materialized-dir",
        str(LOCAL_ARCHETYPE_DIR),
        "--exact-materialized-dir",
        str(LOCAL_EXACT_DIR),
        "--card-table",
        "/workspace/ptcg-rl/private/g2/card-table-v1.json",
        "--output-dir",
        str(OUTPUT_DIR),
        "--device",
        "cuda",
        "--model-labels",
        "970k,1.4m,1.8m,2.9m,3.7m,5.0m",
        "--batch-size-candidates",
        "256,512,1024",
        "--learning-rate-candidates",
        "0.000025,0.00005,0.000075",
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
        "2",
        "--stage-a-epochs",
        "4",
        "--stage-b-epochs",
        "2",
        "--stage-c-epochs",
        "3",
        "--stage-d-epochs",
        "2",
        "--seed",
        "20260815",
        "--loader-workers",
        "16",
        "--weight-decay",
        "0.0001",
        "--maximum-gradient-norm",
        "1.0",
        "--bf16",
    ]
    _run_stream(command)
    if not REPORT_PATH.is_file():
        raise RuntimeError("capacity sweep completed without a final report")
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    if report.get("status") != "PASS_BC_CAPACITY_SWEEP_COMPLETED":
        raise RuntimeError("capacity sweep report did not PASS")
    training_volume.commit()
    return {
        "status": report["status"],
        "report_path": str(REPORT_PATH),
        "report_sha256": _sha256_file(REPORT_PATH),
        "parameter_counts": report["parameter_counts"],
        "validation_ranking": report["validation_ranking"],
        "elapsed_seconds": report["elapsed_seconds"],
        "materialized_stage": [archetype_stage, exact_stage],
    }


@app.local_entrypoint()
def main(force: bool = False) -> None:
    print(json.dumps(run.remote(force=force), indent=2, sort_keys=True))
