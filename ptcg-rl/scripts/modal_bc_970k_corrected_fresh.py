from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
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
OBJECT_CACHE_DIR = Path("/data/cache/materialized-episode-objects-v1")
ARCHETYPE_OBJECT_CACHE = OBJECT_CACHE_DIR / "bc-dragapult-archetype-v3.pkl"
EXACT_OBJECT_CACHE = OBJECT_CACHE_DIR / "bc-dragapult-hq-v2.pkl"
OUTPUT_DIR = Path("/data/runs/bc-dragapult-970k-corrected-fresh-v1")
REPORT_PATH = OUTPUT_DIR / "capacity-sweep-report.json"
MODEL_REPORT_PATH = OUTPUT_DIR / "970k/model-report.json"
RECEIPT_PATH = OUTPUT_DIR / "research-run-receipt.json"

MODEL_LABEL = "970k"
SCORING_CONTRACT = "corrected-primary-head-first-choice"
HISTORICAL_OLD_CONTRACT_SHA256 = (
    "e23a33c8b8c6322a0ce6776a79fd9493f6c2d4af6a3df79ad66d3f181b32fb7b"
)

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

app = modal.App("kptcg-bc-970k-corrected-fresh", image=image)
training_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_inputs() -> None:
    required = (
        ARCHETYPE_DIR / "manifest.json",
        EXACT_DIR / "manifest.json",
        ARCHETYPE_OBJECT_CACHE,
        ARCHETYPE_OBJECT_CACHE.with_name(ARCHETYPE_OBJECT_CACHE.name + ".meta.json"),
        EXACT_OBJECT_CACHE,
        EXACT_OBJECT_CACHE.with_name(EXACT_OBJECT_CACHE.name + ".meta.json"),
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError(f"required persistent BC inputs are missing: {missing}")


def _run_command(command: list[str]) -> None:
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"970k corrected-fresh training failed with exit code {completed.returncode}")


@app.function(
    gpu="RTX-PRO-6000",
    cpu=16,
    memory=98304,
    ephemeral_disk=65536,
    timeout=60 * 60,
    volumes={"/data": training_volume},
)
def run(code_commit: str) -> dict[str, Any]:
    if re.fullmatch(r"[0-9a-f]{40}", code_commit) is None:
        raise RuntimeError("code_commit must be a full lowercase Git SHA")
    _require_inputs()

    if OUTPUT_DIR.exists():
        if REPORT_PATH.is_file() and MODEL_REPORT_PATH.is_file() and RECEIPT_PATH.is_file():
            receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
            if receipt.get("code_commit") != code_commit:
                raise RuntimeError(
                    "existing corrected-fresh output was produced by a different code commit"
                )
            return {"status": "EXISTS", **receipt}
        raise RuntimeError(f"partial corrected-fresh output exists: {OUTPUT_DIR}")

    OUTPUT_DIR.mkdir(parents=True)
    command = [
        "python",
        "/workspace/ptcg-rl/scripts/bc_capacity_sweep.py",
        "--archetype-materialized-dir",
        str(ARCHETYPE_DIR),
        "--exact-materialized-dir",
        str(EXACT_DIR),
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
        MODEL_LABEL,
        "--batch-size-candidates",
        "1024",
        "--learning-rate-candidates",
        "0.000075",
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
    print(
        json.dumps(
            {
                "event": "bc_970k_corrected_fresh_launch",
                "code_commit": code_commit,
                "scoring_contract": SCORING_CONTRACT,
                "output_dir": str(OUTPUT_DIR),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    _run_command(command)

    if not REPORT_PATH.is_file() or not MODEL_REPORT_PATH.is_file():
        raise RuntimeError("corrected-fresh training completed without required reports")
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    model_report = json.loads(MODEL_REPORT_PATH.read_text(encoding="utf-8"))
    if report.get("status") != "PASS_BC_CAPACITY_SWEEP_COMPLETED":
        raise RuntimeError("corrected-fresh capacity report did not PASS")
    if model_report.get("model_label") != MODEL_LABEL:
        raise RuntimeError("corrected-fresh model report has the wrong model label")

    receipt = {
        "status": "PASS_BC_970K_CORRECTED_FRESH",
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "code_commit": code_commit,
        "scoring_contract": SCORING_CONTRACT,
        "model_label": MODEL_LABEL,
        "trainable_parameters": int(model_report["trainable_parameters"]),
        "requested_batch_size": 1024,
        "chosen_batch_size": int(model_report["chosen_batch_size"]),
        "chosen_learning_rate": float(model_report["chosen_learning_rate"]),
        "effective_stage_batch_sizes": model_report["effective_stage_batch_sizes"],
        "final_validation_mean_nll": float(model_report["final_validation_mean_nll"]),
        "final_checkpoint_path": str(model_report["final_checkpoint_path"]),
        "final_checkpoint_sha256": str(model_report["final_checkpoint_sha256"]),
        "historical_old_contract_checkpoint_sha256": HISTORICAL_OLD_CONTRACT_SHA256,
        "report_path": str(REPORT_PATH),
        "report_sha256": _sha256_file(REPORT_PATH),
        "model_report_path": str(MODEL_REPORT_PATH),
        "model_report_sha256": _sha256_file(MODEL_REPORT_PATH),
    }
    RECEIPT_PATH.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    training_volume.commit()
    print(json.dumps({"event": "bc_970k_corrected_fresh_complete", **receipt}, sort_keys=True), flush=True)
    return receipt
