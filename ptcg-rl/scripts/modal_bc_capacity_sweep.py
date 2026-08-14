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
VOLUME_ARCHETYPE_DIR = Path("/data/materialized/bc-dragapult-archetype-v3")
VOLUME_EXACT_DIR = Path("/data/materialized/bc-dragapult-hq-v2")

LOCAL_ARCHETYPE_TAR = Path("/tmp/bc-dragapult-archetype-v3.tar")
LOCAL_ARCHETYPE_DIR = Path("/tmp/bc-dragapult-archetype-v3")
LOCAL_EXACT_TAR = Path("/tmp/bc-dragapult-hq-v2.tar")
LOCAL_EXACT_DIR = Path("/tmp/bc-dragapult-hq-v2")
OUTPUT_DIR = Path("/data/runs/bc-dragapult-capacity-sweep-v1")
REPORT_PATH = OUTPUT_DIR / "capacity-sweep-report.json"
OBJECT_CACHE_DIR = Path("/data/cache/materialized-episode-objects-v1")
ARCHETYPE_OBJECT_CACHE = OBJECT_CACHE_DIR / "bc-dragapult-archetype-v3.pkl"
EXACT_OBJECT_CACHE = OBJECT_CACHE_DIR / "bc-dragapult-hq-v2.pkl"

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
        if isinstance(event, dict) and event.get("event") in {
            "capacity_object_cache_created",
            "capacity_model_complete",
        }:
            training_volume.commit()
            print(
                json.dumps(
                    {
                        "event": "capacity_volume_committed",
                        "source_event": event.get("event"),
                        "model": event.get("model"),
                        "corpus": event.get("corpus"),
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
def run(force: bool = False, resume: bool = False) -> dict[str, Any]:
    if force and resume:
        raise RuntimeError("force and resume are mutually exclusive")
    cache_ready = all(
        path.is_file()
        for path in (
            ARCHETYPE_OBJECT_CACHE,
            ARCHETYPE_OBJECT_CACHE.with_name(ARCHETYPE_OBJECT_CACHE.name + ".meta.json"),
            EXACT_OBJECT_CACHE,
            EXACT_OBJECT_CACHE.with_name(EXACT_OBJECT_CACHE.name + ".meta.json"),
            VOLUME_ARCHETYPE_DIR / "manifest.json",
            VOLUME_EXACT_DIR / "manifest.json",
        )
    )
    if cache_ready:
        archetype_dir = VOLUME_ARCHETYPE_DIR
        exact_dir = VOLUME_EXACT_DIR
        materialized_stage = {
            "status": "PERSISTENT_OBJECT_CACHE_READY",
            "archetype_dir": str(archetype_dir),
            "exact_dir": str(exact_dir),
        }
        print(json.dumps({"event": "capacity_fast_materialized_stage", **materialized_stage}, sort_keys=True), flush=True)
    else:
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
        archetype_dir = LOCAL_ARCHETYPE_DIR
        exact_dir = LOCAL_EXACT_DIR
        materialized_stage = {
            "status": "LOCAL_TARS_STAGED",
            "archetype": archetype_stage,
            "exact": exact_stage,
        }
    if OUTPUT_DIR.exists():
        if REPORT_PATH.is_file() and not force and not resume:
            report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
            return {
                "status": "EXISTS",
                "report_path": str(REPORT_PATH),
                "report_sha256": _sha256_file(REPORT_PATH),
                "validation_ranking": report.get("validation_ranking"),
                "materialized_stage": materialized_stage,
            }
        if resume:
            pass
        elif force:
            shutil.rmtree(OUTPUT_DIR)
        else:
            raise RuntimeError(f"partial capacity sweep output exists: {OUTPUT_DIR}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    command = [
        "python",
        "/workspace/ptcg-rl/scripts/bc_capacity_sweep.py",
        "--archetype-materialized-dir",
        str(archetype_dir),
        "--exact-materialized-dir",
        str(exact_dir),
        "--archetype-object-cache",
        str(ARCHETYPE_OBJECT_CACHE),
        "--exact-object-cache",
        str(EXACT_OBJECT_CACHE),
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
    if resume:
        resume_checkpoint = OUTPUT_DIR / "1.4m/stage-b-archetype-1175-best.pt"
        if not resume_checkpoint.is_file() or not resume_checkpoint.with_name(
            resume_checkpoint.name + ".manifest.json"
        ).is_file():
            raise RuntimeError("1.4M Stage-B resume checkpoint is missing")
        command[command.index("--model-labels") + 1] = "1.4m,1.8m,2.9m,3.7m,5.0m"
        command.extend(
            [
                "--resume-model-label",
                "1.4m",
                "--resume-checkpoint",
                str(resume_checkpoint),
                "--resume-after-stage",
                "stage-b-archetype-1175",
                "--resume-batch-size",
                "1024",
                "--resume-learning-rate",
                "0.000075",
            ]
        )
        print(
            json.dumps(
                {
                    "event": "capacity_resume_launch",
                    "model": "1.4m",
                    "checkpoint": str(resume_checkpoint),
                    "after_stage": "stage-b-archetype-1175",
                },
                sort_keys=True,
            ),
            flush=True,
        )
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
        "materialized_stage": materialized_stage,
    }


@app.local_entrypoint()
def main(force: bool = False) -> None:
    print(json.dumps(run.remote(force=force), indent=2, sort_keys=True))
