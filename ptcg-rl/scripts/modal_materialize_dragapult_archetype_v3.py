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
BUNDLE_SOURCE = Path("/data/corpora/bc-dragapult-archetype-v3/bc-dragapult-archetype-v3.zip")
BUNDLE_SHA256 = "e689e6bebf7dea9e1764b44a6be13b1774699f47b211d46ec9ee16237f036f4a"
LOCAL_BUNDLE = Path("/tmp/bc-dragapult-archetype-v3.zip")
MATERIALIZED_DIR = Path("/data/materialized/bc-dragapult-archetype-v3-featurefix-v3")
MATERIALIZED_TAR = Path("/data/materialized/bc-dragapult-archetype-v3-featurefix-v3.tar")
MATERIALIZED_TAR_SHA256 = Path("/data/materialized/bc-dragapult-archetype-v3-featurefix-v3.tar.sha256")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .run_commands(
        "python -m pip install --no-cache-dir numpy==2.0.2",
        "python -m pip install --no-cache-dir torch==2.10.0 --index-url https://download.pytorch.org/whl/cu130",
    )
    .add_local_dir(PTCG_RL / "src", remote_path="/workspace/ptcg-rl/src")
    .add_local_file(
        PTCG_RL / "scripts/bc_materialize.py",
        remote_path="/workspace/ptcg-rl/scripts/bc_materialize.py",
    )
    .add_local_file(
        PTCG_RL / "private/g2/card-table-v1.json",
        remote_path="/workspace/ptcg-rl/private/g2/card-table-v1.json",
    )
)

app = modal.App("kptcg-bc-dragapult-archetype-featurefix-v3", image=image)
training_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_verified_bundle() -> dict[str, Any]:
    if not BUNDLE_SOURCE.is_file():
        raise RuntimeError(f"Dragapult archetype v3 bundle is missing: {BUNDLE_SOURCE}")
    digest = hashlib.sha256()
    byte_count = 0
    LOCAL_BUNDLE.unlink(missing_ok=True)
    with BUNDLE_SOURCE.open("rb") as source, LOCAL_BUNDLE.open("wb") as destination:
        while True:
            chunk = source.read(16 * 1024 * 1024)
            if not chunk:
                break
            destination.write(chunk)
            digest.update(chunk)
            byte_count += len(chunk)
    observed = digest.hexdigest()
    if observed != BUNDLE_SHA256:
        LOCAL_BUNDLE.unlink(missing_ok=True)
        raise RuntimeError(
            f"Dragapult archetype v3 bundle SHA-256 differs: expected {BUNDLE_SHA256}, observed {observed}"
        )
    receipt = {
        "bundle_path": str(BUNDLE_SOURCE),
        "local_bundle_path": str(LOCAL_BUNDLE),
        "bundle_bytes": byte_count,
        "bundle_sha256": observed,
    }
    print(json.dumps({"event": "bundle_preflight", **receipt}, sort_keys=True), flush=True)
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
        if len(tail) > 120:
            tail.pop(0)
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(
            f"materialization subprocess failed with exit code {return_code}; tail="
            + "\n".join(tail[-30:])
        )


def _ensure_tar() -> dict[str, Any]:
    if MATERIALIZED_TAR.is_file() and MATERIALIZED_TAR_SHA256.is_file():
        expected = MATERIALIZED_TAR_SHA256.read_text(encoding="ascii").strip()
        observed = _sha256_file(MATERIALIZED_TAR)
        if observed != expected:
            raise RuntimeError(
                f"existing materialized tar SHA-256 differs: expected {expected}, observed {observed}"
            )
        return {
            "tar_path": str(MATERIALIZED_TAR),
            "tar_sha256": observed,
            "tar_bytes": MATERIALIZED_TAR.stat().st_size,
        }
    partial = MATERIALIZED_TAR.with_suffix(".tar.partial")
    partial.unlink(missing_ok=True)
    subprocess.run(
        ["tar", "-cf", str(partial), "-C", str(MATERIALIZED_DIR), "."],
        check=True,
    )
    digest = _sha256_file(partial)
    partial.replace(MATERIALIZED_TAR)
    MATERIALIZED_TAR_SHA256.write_text(digest + "\n", encoding="ascii")
    receipt = {
        "tar_path": str(MATERIALIZED_TAR),
        "tar_sha256": digest,
        "tar_bytes": MATERIALIZED_TAR.stat().st_size,
    }
    print(json.dumps({"event": "materialized_tar_ready", **receipt}, sort_keys=True), flush=True)
    return receipt


@app.function(
    cpu=16,
    memory=65536,
    ephemeral_disk=524288,
    timeout=2 * 60 * 60,
    volumes={"/data": training_volume},
)
def materialize(force: bool = False) -> dict[str, Any]:
    if MATERIALIZED_DIR.exists():
        if not force:
            manifest_path = MATERIALIZED_DIR / "manifest.json"
            if not manifest_path.is_file():
                raise RuntimeError(
                    f"partial materialized output exists without manifest: {MATERIALIZED_DIR}"
                )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            archive = _ensure_tar()
            training_volume.commit()
            return {
                "status": "EXISTS",
                "manifest_sha256": manifest["manifest_sha256"],
                "summary": manifest["summary"],
                "archive": archive,
            }
        shutil.rmtree(MATERIALIZED_DIR)
        MATERIALIZED_TAR.unlink(missing_ok=True)
        MATERIALIZED_TAR_SHA256.unlink(missing_ok=True)
    MATERIALIZED_DIR.parent.mkdir(parents=True, exist_ok=True)

    bundle_receipt = _copy_verified_bundle()
    try:
        command = [
            "python",
            "/workspace/ptcg-rl/scripts/bc_materialize.py",
            "--bundle",
            str(LOCAL_BUNDLE),
            "--expected-bundle-sha256",
            BUNDLE_SHA256,
            "--card-table",
            "/workspace/ptcg-rl/private/g2/card-table-v1.json",
            "--output-dir",
            str(MATERIALIZED_DIR),
            "--workers",
            "16",
            "--record-id",
            "bc-dragapult-archetype-v3-featurefix-v3",
        ]
        _run_stream(command)
        manifest = json.loads(
            (MATERIALIZED_DIR / "manifest.json").read_text(encoding="utf-8")
        )
        if manifest.get("status") != "PASS_MATERIALIZED_BC_READY":
            raise RuntimeError("Dragapult archetype v3 materializer did not report PASS")
        source = manifest.get("source", {})
        if source.get("test_episode_bodies_read") != 0:
            raise RuntimeError("Dragapult archetype v3 materialization did not preserve sealed test bodies")
        archive = _ensure_tar()
        training_volume.commit()
        return {
            "status": manifest["status"],
            "manifest_sha256": manifest["manifest_sha256"],
            "summary": manifest["summary"],
            "source": source,
            "bundle": bundle_receipt,
            "archive": archive,
        }
    except Exception:
        shutil.rmtree(MATERIALIZED_DIR, ignore_errors=True)
        MATERIALIZED_TAR.unlink(missing_ok=True)
        MATERIALIZED_TAR_SHA256.unlink(missing_ok=True)
        raise
    finally:
        LOCAL_BUNDLE.unlink(missing_ok=True)
