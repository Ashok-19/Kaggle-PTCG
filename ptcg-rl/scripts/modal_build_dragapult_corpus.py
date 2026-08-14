from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Mapping

import modal

if modal.is_local():
    ROOT = Path(__file__).resolve().parents[2]
else:
    ROOT = Path("/workspace")
PTCG_RL = ROOT / "ptcg-rl"
CONFIG_PATH = PTCG_RL / "configs/bc_dragapult_corpus_v1.json"
VOLUME_NAME = "kptcg-training"
SECRET_NAME = "kptcg-kaggle"
AUTH_BLOB_ENV = "KPTCG_AUTH_BLOB"
REMOTE_CORPUS_ROOT = Path("/data/corpora/bc-dragapult-hq-v1")
RAW_ROOT = Path("/tmp/kptcg-daily-replays")
CLIENT_CONFIG_DIR = Path("/root/.kaggle")
CLIENT_CONFIG_PATH = CLIENT_CONFIG_DIR / "kaggle.json"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("kaggle==1.7.4.5")
    .add_local_dir(PTCG_RL / "src", remote_path="/workspace/ptcg-rl/src")
    .add_local_file(
        PTCG_RL / "scripts/build_bc_dragapult_corpus.py",
        remote_path="/workspace/ptcg-rl/scripts/build_bc_dragapult_corpus.py",
    )
    .add_local_file(
        CONFIG_PATH,
        remote_path="/workspace/ptcg-rl/configs/bc_dragapult_corpus_v1.json",
    )
)

app = modal.App("kptcg-bc-dragapult-corpus", image=image)
training_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
client_auth = modal.Secret.from_name(SECRET_NAME)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_config() -> dict[str, Any]:
    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise RuntimeError("unsupported Dragapult corpus config")
    days = payload.get("days")
    if not isinstance(days, list) or not days or any(not isinstance(day, str) for day in days):
        raise RuntimeError("Dragapult corpus config has invalid days")
    if len(days) != len(set(days)):
        raise RuntimeError("Dragapult corpus config contains duplicate days")
    if payload.get("winner_only_labels") is not True:
        raise RuntimeError("production Dragapult corpus must remain winner-only")
    return payload


def _install_client_auth() -> None:
    encoded = os.environ.get(AUTH_BLOB_ENV)
    if not encoded:
        raise RuntimeError(f"Modal auth secret is missing {AUTH_BLOB_ENV}")
    try:
        raw = base64.b64decode(encoded, validate=True)
        payload = json.loads(raw)
    except (ValueError, UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeError("Modal auth blob is malformed") from error
    if not isinstance(payload, dict) or len(payload) != 2:
        raise RuntimeError("Modal auth blob has an unexpected client-config schema")
    if not all(isinstance(value, str) and value for value in payload.values()):
        raise RuntimeError("Modal auth blob contains an empty client-config field")
    CLIENT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CLIENT_CONFIG_DIR.chmod(0o700)
    CLIENT_CONFIG_PATH.write_bytes(raw)
    CLIENT_CONFIG_PATH.chmod(0o600)


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
        if len(tail) > 100:
            tail.pop(0)
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(
            f"subprocess failed with exit code {return_code}; tail=" + "\n".join(tail[-30:])
        )


def _download_day(day: str) -> dict[str, Any]:
    slug = f"pokemon-tcg-ai-battle-episodes-{day}"
    dataset = f"kaggle/{slug}"
    target_dir = RAW_ROOT / day / "archive"
    target_dir.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    _run_stream(
        [
            "kaggle",
            "datasets",
            "download",
            dataset,
            "--path",
            str(target_dir),
            "--force",
            "--quiet",
        ]
    )
    candidates = sorted(target_dir.glob("*.zip"))
    if len(candidates) != 1:
        raise RuntimeError(
            f"expected exactly one Kaggle archive for {day}, found {len(candidates)}"
        )
    archive = candidates[0]
    expected_name = f"{slug}.zip"
    if archive.name != expected_name:
        raise RuntimeError(
            f"unexpected Kaggle archive name for {day}: {archive.name}; expected {expected_name}"
        )
    receipt = {
        "date": day,
        "dataset": dataset,
        "archive": archive.name,
        "compressed_bytes": archive.stat().st_size,
        "sha256": _sha256_file(archive),
        "elapsed_seconds": time.perf_counter() - started,
    }
    print(json.dumps({"event": "daily_download_complete", **receipt}, sort_keys=True), flush=True)
    return receipt


def _write_execution_report(
    *,
    config: Mapping[str, Any],
    downloads: list[dict[str, Any]],
    builder_report: Mapping[str, Any],
    elapsed_seconds: float,
) -> Path:
    report = {
        "schema_version": 1,
        "record_id": "bc-dragapult-hq-v1-modal-execution",
        "status": "PASS",
        "volume": VOLUME_NAME,
        "remote_corpus_root": str(REMOTE_CORPUS_ROOT),
        "raw_archives_retained": False,
        "config_sha256": _sha256_file(CONFIG_PATH),
        "days": list(config["days"]),
        "downloads": downloads,
        "downloaded_compressed_bytes": sum(int(row["compressed_bytes"]) for row in downloads),
        "builder_report": dict(builder_report),
        "elapsed_seconds": elapsed_seconds,
    }
    report["report_sha256"] = hashlib.sha256(
        json.dumps(
            report,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    path = REMOTE_CORPUS_ROOT / "modal-execution-report.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


@app.function(
    cpu=16,
    memory=65536,
    ephemeral_disk=524288,
    timeout=12 * 60 * 60,
    secrets=[client_auth],
    volumes={"/data": training_volume},
)
def build(force: bool = False) -> dict[str, Any]:
    started = time.perf_counter()
    config = _load_config()
    bundle = REMOTE_CORPUS_ROOT / "bc-dragapult-hq-v1.zip"
    builder_report_path = REMOTE_CORPUS_ROOT / "build-report.json"
    execution_report_path = REMOTE_CORPUS_ROOT / "modal-execution-report.json"
    if REMOTE_CORPUS_ROOT.exists():
        if not force:
            if bundle.is_file() and builder_report_path.is_file() and execution_report_path.is_file():
                existing = json.loads(execution_report_path.read_text(encoding="utf-8"))
                return {
                    "status": "EXISTS",
                    "volume": VOLUME_NAME,
                    "remote_corpus_root": str(REMOTE_CORPUS_ROOT),
                    "summary": existing.get("builder_report", {}).get("summary"),
                    "bundle_sha256": existing.get("builder_report", {}).get("bundle_sha256"),
                    "bundle_bytes": existing.get("builder_report", {}).get("bundle_bytes"),
                }
            raise RuntimeError(
                f"partial corpus output already exists at {REMOTE_CORPUS_ROOT}; use force only after review"
            )
        shutil.rmtree(REMOTE_CORPUS_ROOT)
    REMOTE_CORPUS_ROOT.mkdir(parents=True, exist_ok=False)
    if RAW_ROOT.exists():
        shutil.rmtree(RAW_ROOT)
    RAW_ROOT.mkdir(parents=True, exist_ok=False)

    downloads: list[dict[str, Any]] = []
    try:
        _install_client_auth()
        version = subprocess.check_output(["kaggle", "--version"], text=True).strip()
        print(json.dumps({"event": "kaggle_cli_ready", "version": version}, sort_keys=True), flush=True)
        for day in config["days"]:
            downloads.append(_download_day(str(day)))

        command = [
            "python",
            "/workspace/ptcg-rl/scripts/build_bc_dragapult_corpus.py",
            "--archive-root",
            str(RAW_ROOT),
            "--days",
            *[str(day) for day in config["days"]],
            "--target-deck-sha256",
            str(config["target_deck_sha256"]),
            "--module-version",
            str(config["required_module_version"]),
            "--teacher-score-floor",
            str(config["teacher_score_floor"]),
            "--elite-teachers",
            str(CONFIG_PATH),
            "--split-seed",
            str(config["split_seed"]),
            "--minimum-selected",
            str(config["minimum_selected"]),
            "--minimum-active-requests",
            str(config["minimum_active_requests"]),
            "--record-id",
            str(config["record_id"]),
            "--bundle",
            str(bundle),
            "--report",
            str(builder_report_path),
        ]
        _run_stream(command)
        builder_report = json.loads(builder_report_path.read_text(encoding="utf-8"))
        if builder_report.get("status") != "PASS":
            raise RuntimeError("Dragapult corpus builder did not report PASS")
        execution_report_path = _write_execution_report(
            config=config,
            downloads=downloads,
            builder_report=builder_report,
            elapsed_seconds=time.perf_counter() - started,
        )
        training_volume.commit()
        return {
            "status": "PASS",
            "volume": VOLUME_NAME,
            "remote_corpus_root": str(REMOTE_CORPUS_ROOT),
            "bundle_sha256": builder_report["bundle_sha256"],
            "bundle_bytes": builder_report["bundle_bytes"],
            "summary": builder_report["summary"],
            "downloaded_compressed_bytes": sum(
                int(row["compressed_bytes"]) for row in downloads
            ),
            "execution_report_sha256": _sha256_file(execution_report_path),
            "elapsed_seconds": time.perf_counter() - started,
        }
    except Exception:
        shutil.rmtree(REMOTE_CORPUS_ROOT, ignore_errors=True)
        raise
    finally:
        CLIENT_CONFIG_PATH.unlink(missing_ok=True)
        shutil.rmtree(RAW_ROOT, ignore_errors=True)
