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
CORPUS_ROOT = Path("/data/corpora/bc-dragapult-live-v6")
BUNDLE_SOURCE = CORPUS_ROOT / "bc-dragapult-live-v6.zip"
BUILD_REPORT = CORPUS_ROOT / "build-report.json"
LOCAL_BUNDLE = Path("/tmp/bc-dragapult-live-v6.zip")
MATERIALIZED_DIR = Path("/data/materialized/bc-dragapult-live-v6-featurefix-v3")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .run_commands(
        "python -m pip install --no-cache-dir numpy==2.0.2",
        "python -m pip install --no-cache-dir torch==2.10.0 --index-url https://download.pytorch.org/whl/cpu",
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

app = modal.App("kptcg-bc-dragapult-live-v6-materialize", image=image)
training_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=False)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verified_bundle() -> tuple[str, int]:
    if not BUNDLE_SOURCE.is_file() or not BUILD_REPORT.is_file():
        raise RuntimeError("live-v6 corpus bundle/build report is missing")
    report = json.loads(BUILD_REPORT.read_text(encoding="utf-8"))
    if report.get("status") != "PASS":
        raise RuntimeError("live-v6 corpus build report did not PASS")
    expected = str(report["bundle_sha256"])
    observed = _sha256_file(BUNDLE_SOURCE)
    if observed != expected:
        raise RuntimeError(
            f"live-v6 bundle SHA-256 differs: expected {expected}, observed {observed}"
        )
    shutil.copyfile(BUNDLE_SOURCE, LOCAL_BUNDLE)
    if _sha256_file(LOCAL_BUNDLE) != expected:
        raise RuntimeError("local live-v6 bundle copy failed SHA verification")
    return expected, BUNDLE_SOURCE.stat().st_size


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
            f"live-v6 materialization failed with exit code {return_code}; tail="
            + "\n".join(tail[-30:])
        )


@app.function(
    cpu=8,
    memory=32768,
    timeout=2 * 60 * 60,
    volumes={"/data": training_volume},
)
def materialize(force: bool = False) -> dict[str, Any]:
    if MATERIALIZED_DIR.exists():
        manifest_path = MATERIALIZED_DIR / "manifest.json"
        if manifest_path.is_file() and not force:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            return {
                "status": "EXISTS",
                "manifest_sha256": manifest["manifest_sha256"],
                "summary": manifest["summary"],
            }
        if not force:
            raise RuntimeError(f"partial live-v6 materialized output exists: {MATERIALIZED_DIR}")
        shutil.rmtree(MATERIALIZED_DIR)
    MATERIALIZED_DIR.parent.mkdir(parents=True, exist_ok=True)

    expected_sha256, bundle_bytes = _verified_bundle()
    try:
        _run_stream(
            [
                "python",
                "/workspace/ptcg-rl/scripts/bc_materialize.py",
                "--bundle",
                str(LOCAL_BUNDLE),
                "--expected-bundle-sha256",
                expected_sha256,
                "--card-table",
                "/workspace/ptcg-rl/private/g2/card-table-v1.json",
                "--output-dir",
                str(MATERIALIZED_DIR),
                "--workers",
                "8",
                "--record-id",
                "bc-dragapult-live-v6-featurefix-v3",
            ]
        )
        manifest = json.loads((MATERIALIZED_DIR / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("status") != "PASS_MATERIALIZED_BC_READY":
            raise RuntimeError("live-v6 materializer did not report PASS")
        if manifest.get("source", {}).get("test_episode_bodies_read") != 0:
            raise RuntimeError("live-v6 materialization did not preserve sealed test bodies")
        training_volume.commit()
        result = {
            "status": manifest["status"],
            "bundle_sha256": expected_sha256,
            "bundle_bytes": bundle_bytes,
            "manifest_sha256": manifest["manifest_sha256"],
            "summary": manifest["summary"],
            "source": manifest["source"],
            "materialized_dir": str(MATERIALIZED_DIR),
        }
        print(json.dumps(result, sort_keys=True), flush=True)
        return result
    except Exception:
        shutil.rmtree(MATERIALIZED_DIR, ignore_errors=True)
        raise
    finally:
        LOCAL_BUNDLE.unlink(missing_ok=True)


@app.local_entrypoint()
def main(force: bool = False) -> None:
    print(json.dumps(materialize.remote(force), indent=2, sort_keys=True))
