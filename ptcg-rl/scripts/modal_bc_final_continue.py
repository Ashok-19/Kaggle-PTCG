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

ARCHETYPE_DIR = Path("/data/materialized/bc-dragapult-archetype-v3")
EXACT_DIR = Path("/data/materialized/bc-dragapult-hq-v2")
ARCHETYPE_CACHE = Path("/data/cache/materialized-episode-objects-v1/bc-dragapult-archetype-v3.pkl")
EXACT_CACHE = Path("/data/cache/materialized-episode-objects-v1/bc-dragapult-hq-v2.pkl")
SOURCE_CHECKPOINT = Path(
    "/data/runs/bc-dragapult-final-v1/3.7m/3.7m/stage-d-exact-1150-best.pt"
)
EXPECTED_SOURCE_SHA256 = "dec8a1a212bf8183f603042dc858eae3223d2fb0b27cb512fb60294bf098b145"
OUTPUT_ROOT = Path("/data/runs/bc-dragapult-final-v1-stage-d-continuation-v1")

MODEL_LABEL = "3.7m"
BATCH_SIZE = 512
BASE_LEARNING_RATE = 5e-5
STAGE_D_LEARNING_RATE = BASE_LEARNING_RATE * 0.25
MAX_ADDITIONAL_EPOCHS = 12
EARLY_STOPPING_PATIENCE = 3
EARLY_STOPPING_MIN_DELTA = 0.00025

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

app = modal.App("kptcg-bc-dragapult-final-continue", image=image)
training_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_inputs() -> None:
    for root, label in ((ARCHETYPE_DIR, "archetype-v3"), (EXACT_DIR, "exact-v2")):
        if not (root / "manifest.json").is_file():
            raise RuntimeError(f"{label} materialized directory is missing manifest.json: {root}")
    for cache, label in ((ARCHETYPE_CACHE, "archetype-v3"), (EXACT_CACHE, "exact-v2")):
        if not cache.is_file():
            raise RuntimeError(f"{label} persistent object cache is missing: {cache}")
    if not SOURCE_CHECKPOINT.is_file():
        raise RuntimeError(f"source checkpoint is missing: {SOURCE_CHECKPOINT}")
    manifest = SOURCE_CHECKPOINT.with_suffix(SOURCE_CHECKPOINT.suffix + ".manifest.json")
    if not manifest.is_file():
        raise RuntimeError(f"source checkpoint manifest is missing: {manifest}")
    observed_sha = _sha256_file(SOURCE_CHECKPOINT)
    if observed_sha != EXPECTED_SOURCE_SHA256:
        raise RuntimeError(
            f"source checkpoint SHA-256 differs: expected {EXPECTED_SOURCE_SHA256}, got {observed_sha}"
        )
    print(
        json.dumps(
            {
                "event": "final_bc_continuation_inputs_ready",
                "source_checkpoint": str(SOURCE_CHECKPOINT),
                "source_checkpoint_sha256": observed_sha,
                "stage_d_learning_rate": STAGE_D_LEARNING_RATE,
                "max_additional_epochs": MAX_ADDITIONAL_EPOCHS,
                "early_stopping_patience": EARLY_STOPPING_PATIENCE,
                "early_stopping_min_delta": EARLY_STOPPING_MIN_DELTA,
            },
            sort_keys=True,
        ),
        flush=True,
    )


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
                        "event": "final_bc_continuation_volume_committed",
                        "model": event.get("model"),
                        "checkpoint_sha256": event.get("final_checkpoint_sha256"),
                        "final_validation_nll": event.get("final_validation_nll"),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(
            f"final BC continuation subprocess failed with exit code {return_code}; tail="
            + "\n".join(tail[-60:])
        )


@app.function(
    gpu="RTX-PRO-6000",
    cpu=16,
    memory=98304,
    ephemeral_disk=524288,
    timeout=4 * 60 * 60,
    volumes={"/data": training_volume},
)
def run(force: bool = False) -> dict[str, Any]:
    _require_inputs()
    output_dir = OUTPUT_ROOT
    report_path = output_dir / "capacity-sweep-report.json"
    if output_dir.exists():
        if report_path.is_file() and not force:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            return {
                "status": "EXISTS",
                "report_path": str(report_path),
                "report_sha256": _sha256_file(report_path),
                "validation_ranking": report.get("validation_ranking"),
            }
        if not force:
            raise RuntimeError(f"partial continuation output exists: {output_dir}")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    print(
        json.dumps(
            {
                "event": "final_bc_continuation_launch",
                "model": MODEL_LABEL,
                "batch_size": BATCH_SIZE,
                "source_validation_nll": 1.0532460389871248,
                "stage_d_learning_rate": STAGE_D_LEARNING_RATE,
                "max_additional_epochs": MAX_ADDITIONAL_EPOCHS,
                "early_stopping_patience": EARLY_STOPPING_PATIENCE,
                "early_stopping_min_delta": EARLY_STOPPING_MIN_DELTA,
                "promotion_contract": "epoch-0 incumbent remains eligible and challenger must beat it by min_delta",
            },
            sort_keys=True,
        ),
        flush=True,
    )

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
        str(output_dir),
        "--device",
        "cuda",
        "--model-labels",
        MODEL_LABEL,
        "--resume-model-label",
        MODEL_LABEL,
        "--resume-checkpoint",
        str(SOURCE_CHECKPOINT),
        "--resume-after-stage",
        "stage-c-exact-all",
        "--resume-batch-size",
        str(BATCH_SIZE),
        "--resume-learning-rate",
        format(BASE_LEARNING_RATE, ".12g"),
        "--sequence-length",
        "32",
        "--stage-a-epochs",
        "1",
        "--stage-b-epochs",
        "1",
        "--stage-c-epochs",
        "1",
        "--stage-d-epochs",
        str(MAX_ADDITIONAL_EPOCHS),
        "--stage-d-early-stopping-patience",
        str(EARLY_STOPPING_PATIENCE),
        "--stage-d-early-stopping-min-delta",
        format(EARLY_STOPPING_MIN_DELTA, ".12g"),
        "--seed",
        "20260815",
        "--loader-workers",
        "8",
        "--weight-decay",
        "0.0001",
        "--maximum-gradient-norm",
        "1.0",
        "--bf16",
    ]
    _run_stream(command)
    if not report_path.is_file():
        raise RuntimeError("continuation completed without capacity-sweep-report.json")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("status") != "PASS_BC_CAPACITY_SWEEP_COMPLETED":
        raise RuntimeError("continuation report did not PASS")
    training_volume.commit()
    winner = report["validation_ranking"][0]
    return {
        "status": "PASS_FINAL_BC_CONTINUATION_COMPLETED",
        "report_path": str(report_path),
        "report_sha256": _sha256_file(report_path),
        "validation_ranking": report["validation_ranking"],
        "incumbent_validation_nll": 1.0532460389871248,
        "challenger_validation_nll": winner["final_validation_mean_nll"],
        "elapsed_seconds": report["elapsed_seconds"],
    }


@app.local_entrypoint()
def main(force: bool = False) -> None:
    print(json.dumps(run.remote(force=force), indent=2, sort_keys=True))
