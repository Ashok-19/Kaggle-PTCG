from __future__ import annotations

import json
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
ARCHETYPE_DIR = Path("/data/materialized/bc-dragapult-archetype-v3-featurefix-v1")
EXACT_DIR = Path("/data/materialized/bc-dragapult-hq-v2-featurefix-v1")
CACHE_ROOT = Path("/data/cache/materialized-episode-objects-v1")
ARCHETYPE_CACHE = CACHE_ROOT / "bc-dragapult-archetype-v3-featurefix-v1.pkl"
EXACT_CACHE = CACHE_ROOT / "bc-dragapult-hq-v2-featurefix-v1.pkl"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .run_commands(
        "python -m pip install --no-cache-dir numpy==2.0.2",
        "python -m pip install --no-cache-dir torch==2.10.0 --index-url https://download.pytorch.org/whl/cpu",
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

app = modal.App("kptcg-bc-featurefix-object-cache", image=image)
training_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)


@app.function(
    cpu=16,
    memory=98304,
    ephemeral_disk=524288,
    timeout=60 * 60,
    volumes={"/data": training_volume},
)
def build(force: bool = False) -> dict[str, Any]:
    if force:
        for path in (ARCHETYPE_CACHE, EXACT_CACHE):
            path.unlink(missing_ok=True)
            path.with_name(path.name + ".meta.json").unlink(missing_ok=True)
    for root in (ARCHETYPE_DIR, EXACT_DIR):
        if not (root / "manifest.json").is_file():
            raise RuntimeError(f"feature-fix materialized corpus is missing: {root}")
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
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
        "/tmp/kptcg-featurefix-cache-only",
        "--device",
        "cpu",
        "--loader-workers",
        "8",
        "--cache-only",
    ]
    process = subprocess.run(command, text=True, capture_output=True)
    print(process.stdout, end="", flush=True)
    if process.stderr:
        print(process.stderr, end="", flush=True)
    if process.returncode != 0:
        raise RuntimeError(f"feature-fix object-cache build failed with exit code {process.returncode}")
    for path in (ARCHETYPE_CACHE, EXACT_CACHE):
        if not path.is_file() or not path.with_name(path.name + ".meta.json").is_file():
            raise RuntimeError(f"feature-fix object cache was not created: {path}")
    training_volume.commit()
    return {
        "status": "PASS_FEATUREFIX_OBJECT_CACHE_READY",
        "archetype_cache": str(ARCHETYPE_CACHE),
        "archetype_cache_bytes": ARCHETYPE_CACHE.stat().st_size,
        "exact_cache": str(EXACT_CACHE),
        "exact_cache_bytes": EXACT_CACHE.stat().st_size,
    }


@app.local_entrypoint()
def main(force: bool = False) -> None:
    print(json.dumps(build.remote(force), sort_keys=True))
