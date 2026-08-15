from __future__ import annotations

import hashlib
import json
import math
import pickle
import re
import sys
from pathlib import Path
from typing import Any

import modal

if not modal.is_local():
    import torch

if modal.is_local():
    ROOT = Path(__file__).resolve().parents[2]
else:
    ROOT = Path("/workspace")
PTCG_RL = ROOT / "ptcg-rl"
if not modal.is_local():
    sys.path.insert(0, str(PTCG_RL / "src"))
    sys.path.insert(0, str(PTCG_RL / "scripts"))

VOLUME_NAME = "kptcg-training"
ARCHETYPE_CACHE = Path("/data/cache/materialized-episode-objects-v1/bc-dragapult-archetype-v3.pkl")
ARCHETYPE_MANIFEST = Path("/data/materialized/bc-dragapult-archetype-v3/manifest.json")
OUTPUT_DIR = Path("/data/runs/bc-dragapult-970k-batch-benchmark-v1")
REPORT_PATH = OUTPUT_DIR / "report.json"
REQUESTED_BATCH_SIZES = (1024, 2048)
SCORING_CONTRACT = "corrected-primary-head-first-choice"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .run_commands(
        "python -m pip install --no-cache-dir numpy==2.0.2",
        "python -m pip install --no-cache-dir torch==2.10.0 --index-url https://download.pytorch.org/whl/cu130",
    )
    .add_local_dir(PTCG_RL / "src", remote_path="/workspace/ptcg-rl/src")
    .add_local_file(
        PTCG_RL / "scripts/bc_capacity_sweep.py",
        remote_path="/workspace/ptcg-rl/scripts/bc_capacity_sweep.py",
    )
    .add_local_file(
        PTCG_RL / "scripts/bc_train_materialized.py",
        remote_path="/workspace/ptcg-rl/scripts/bc_train_materialized.py",
    )
    .add_local_file(
        PTCG_RL / "private/g2/card-table-v1.json",
        remote_path="/workspace/ptcg-rl/private/g2/card-table-v1.json",
    )
)

app = modal.App("kptcg-bc-970k-batch-benchmark", image=image)
training_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_archetype() -> tuple[list[Any], list[Any], str]:
    if not ARCHETYPE_CACHE.is_file() or not ARCHETYPE_MANIFEST.is_file():
        raise RuntimeError("archetype-v3 object cache or manifest is missing")
    with ARCHETYPE_CACHE.open("rb") as handle:
        episodes = pickle.load(handle)
    train = [episode for episode in episodes if episode.split == "train"]
    validation = [episode for episode in episodes if episode.split == "validation"]
    if len(train) != 1682 or len(validation) != 172:
        raise RuntimeError(
            f"unexpected archetype-v3 split sizes: train={len(train)} validation={len(validation)}"
        )
    return train, validation, _sha256(ARCHETYPE_MANIFEST)


def _is_finite_smoke(smoke: dict[str, Any]) -> bool:
    values = (
        smoke["training"]["mean_nll"],
        smoke["training"]["gradient_norm_max_pre_clip"],
        smoke["training"]["policy_targets_per_second"],
        smoke["validation"]["mean_nll"],
    )
    return all(math.isfinite(float(value)) for value in values)


@app.function(
    gpu="RTX-PRO-6000",
    cpu=16,
    memory=98304,
    ephemeral_disk=524288,
    timeout=60 * 60,
    volumes={"/data": training_volume},
)
def run(code_commit: str) -> dict[str, Any]:
    from bc_capacity_sweep import _one_epoch_smoke, _pack, model_configs
    from ptcg_rl.g2.card_table import load_card_table

    if re.fullmatch(r"[0-9a-f]{40}", code_commit) is None:
        raise RuntimeError("code_commit must be a full lowercase Git SHA")
    if REPORT_PATH.is_file():
        existing = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        if existing.get("code_commit") == code_commit:
            return {"status": "EXISTS", **existing}
        raise RuntimeError("batch benchmark report already exists for a different code commit")

    device = torch.device("cuda")
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError("RTX benchmark requires CUDA with BF16 support")
    torch.set_float32_matmul_precision("high")

    train, validation, manifest_sha256 = _load_archetype()
    validation_subset = validation[:64]
    card_table = load_card_table(Path("/workspace/ptcg-rl/private/g2/card-table-v1.json"))
    config = model_configs()["970k"]
    rows: list[dict[str, Any]] = []

    for requested_batch_size in REQUESTED_BATCH_SIZES:
        effective_batch_size = min(requested_batch_size, len(train))
        train_groups = None
        validation_groups = None
        try:
            train_groups = _pack(
                train,
                batch_size=effective_batch_size,
                sequence_length=32,
                seed=20260815,
                device=device,
            )
            validation_groups = _pack(
                validation_subset,
                batch_size=min(effective_batch_size, len(validation_subset)),
                sequence_length=32,
                seed=20260816,
                device=device,
            )
            smoke = _one_epoch_smoke(
                config=config,
                card_table=card_table,
                train_groups=train_groups,
                validation_groups=validation_groups,
                learning_rate=5e-5,
                seed=20260815,
                device=device,
                bf16=True,
                maximum_gradient_norm=1.0,
                weight_decay=1e-4,
            )
            peak_reserved_bytes = int(torch.cuda.max_memory_reserved(device))
            finite = _is_finite_smoke(smoke)
            row = {
                "requested_batch_size": requested_batch_size,
                "effective_batch_size": effective_batch_size,
                "effective_batch_limited_by_episode_count": (
                    effective_batch_size != requested_batch_size
                ),
                "status": "PASS" if finite else "NONFINITE",
                "training_policy_targets": int(smoke["training"]["policy_targets"]),
                "training_elapsed_seconds": float(smoke["training"]["elapsed_seconds"]),
                "optimizer_steps": int(smoke["training"]["optimizer_steps"]),
                "targets_per_second": float(smoke["training"]["policy_targets_per_second"]),
                "training_mean_nll": float(smoke["training"]["mean_nll"]),
                "validation_mean_nll": float(smoke["validation"]["mean_nll"]),
                "gradient_norm_max_pre_clip": float(
                    smoke["training"]["gradient_norm_max_pre_clip"]
                ),
                "peak_allocated_bytes": int(smoke["peak_allocated_bytes"]),
                "peak_reserved_bytes": peak_reserved_bytes,
                "gpu_telemetry": smoke["gpu_telemetry"],
            }
        except torch.cuda.OutOfMemoryError:
            row = {
                "requested_batch_size": requested_batch_size,
                "effective_batch_size": effective_batch_size,
                "effective_batch_limited_by_episode_count": (
                    effective_batch_size != requested_batch_size
                ),
                "status": "OOM",
            }
            torch.cuda.empty_cache()
        rows.append(row)
        print(json.dumps({"event": "bc_970k_batch_benchmark_row", **row}, sort_keys=True), flush=True)
        del train_groups, validation_groups
        torch.cuda.empty_cache()

    passing = [row for row in rows if row["status"] == "PASS"]
    if not passing:
        raise RuntimeError("no requested 970k batch size completed with finite metrics")
    fastest = max(passing, key=lambda row: row["targets_per_second"])
    report = {
        "record_id": "bc-dragapult-970k-batch-benchmark-v1",
        "status": "PASS_BC_970K_BATCH_BENCHMARK",
        "code_commit": code_commit,
        "scoring_contract": SCORING_CONTRACT,
        "archetype_manifest_sha256": manifest_sha256,
        "train_episodes": len(train),
        "validation_subset_episodes": len(validation_subset),
        "requested_batch_sizes": list(REQUESTED_BATCH_SIZES),
        "maximum_literal_effective_batch_size": len(train),
        "batch_4096_skipped_reason": (
            "requested 4096 has the same effective 1682-episode batch as requested 2048"
        ),
        "learning_rate": 5e-5,
        "sequence_length": 32,
        "rows": rows,
        "fastest_requested_batch_size": int(fastest["requested_batch_size"]),
        "fastest_effective_batch_size": int(fastest["effective_batch_size"]),
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    training_volume.commit()
    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    return report
