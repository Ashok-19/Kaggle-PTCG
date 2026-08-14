from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import zipfile
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ptcg_rl.bc.materialized import (  # noqa: E402
    build_episode_payload,
    save_episode_payload,
    sha256_file,
)
from ptcg_rl.g2.card_table import load_card_table  # noqa: E402
from ptcg_rl.g2.models import model_schema_sha256  # noqa: E402
from ptcg_rl.g3.bc_canary import build_semantic_loader_plan  # noqa: E402
from ptcg_rl.replay.semantic_loader import SemanticReplayLoader  # noqa: E402


class BCMaterializeError(ValueError):
    """Raised when BC materialization violates the source or output contract."""


_WORKER_LOADER: SemanticReplayLoader | None = None
_WORKER_RECORDS: dict[int, dict[str, Any]] = {}
_WORKER_OUTPUT: Path | None = None


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return _sha256_bytes(raw)


def _load_bundle_manifest(bundle: Path, expected_sha256: str | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not bundle.is_file():
        raise BCMaterializeError(f"BC bundle does not exist: {bundle}")
    digest = sha256_file(bundle)
    if expected_sha256 is not None and digest != expected_sha256:
        raise BCMaterializeError(
            f"BC bundle SHA-256 differs: expected {expected_sha256}, observed {digest}"
        )
    try:
        with zipfile.ZipFile(bundle) as archive:
            raw = archive.read("manifest.json")
    except (OSError, zipfile.BadZipFile, KeyError) as error:
        raise BCMaterializeError(f"cannot read BC bundle manifest: {error}") from error
    try:
        manifest = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise BCMaterializeError(f"BC bundle manifest is invalid JSON: {error}") from error
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise BCMaterializeError("unsupported BC bundle manifest")
    records = manifest.get("records")
    if not isinstance(records, list) or not records:
        raise BCMaterializeError("BC bundle manifest contains no records")
    result: list[dict[str, Any]] = []
    seen: set[int] = set()
    for position, value in enumerate(records):
        if not isinstance(value, dict):
            raise BCMaterializeError(f"BC record {position} is not an object")
        try:
            episode_id = int(value["episode_id"])
            split = str(value["split"])
            path = str(value["path"])
            byte_count = int(value["bytes"])
            teacher_player_index = int(value["teacher_player_index"])
            source_sha = str(value["sha256"])
        except (KeyError, TypeError, ValueError) as error:
            raise BCMaterializeError(f"BC record {position} is malformed: {error}") from error
        if episode_id <= 0 or episode_id in seen:
            raise BCMaterializeError(f"duplicate or invalid episode ID: {episode_id}")
        seen.add(episode_id)
        if split not in {"train", "validation", "test"}:
            raise BCMaterializeError(f"unsupported BC split for {episode_id}: {split}")
        if path != f"{episode_id}.json" or byte_count <= 0 or teacher_player_index not in (0, 1):
            raise BCMaterializeError(f"BC record contract differs for episode {episode_id}")
        if len(source_sha) != 64:
            raise BCMaterializeError(f"BC replay SHA-256 is invalid for episode {episode_id}")
        result.append(dict(value))
    return manifest, result


def _extract_train_validation(
    bundle: Path,
    records: list[dict[str, Any]],
    destination: Path,
) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(bundle) as archive:
        for record in records:
            episode_id = int(record["episode_id"])
            name = f"episodes/{episode_id}.json"
            try:
                info = archive.getinfo(name)
            except KeyError as error:
                raise BCMaterializeError(f"BC bundle is missing episode {episode_id}") from error
            if info.file_size != int(record["bytes"]):
                raise BCMaterializeError(f"BC bundle byte count differs for episode {episode_id}")
            target = destination / f"{episode_id}.json"
            digest = hashlib.sha256()
            with archive.open(info) as source, target.open("wb") as sink:
                while True:
                    chunk = source.read(8 * 1024 * 1024)
                    if not chunk:
                        break
                    sink.write(chunk)
                    digest.update(chunk)
            if digest.hexdigest() != record["sha256"]:
                target.unlink(missing_ok=True)
                raise BCMaterializeError(f"BC replay SHA-256 differs for episode {episode_id}")


def _worker_init(
    plan: dict[str, Any],
    episodes_dir: str,
    card_data_sha256: str,
    records: list[dict[str, Any]],
    output_dir: str,
) -> None:
    global _WORKER_LOADER, _WORKER_RECORDS, _WORKER_OUTPUT
    _WORKER_LOADER = SemanticReplayLoader(
        plan,
        Path(episodes_dir),
        card_data_sha256=card_data_sha256,
    )
    _WORKER_RECORDS = {int(record["episode_id"]): record for record in records}
    _WORKER_OUTPUT = Path(output_dir)


def _materialize_one(episode_id: int) -> dict[str, Any]:
    if _WORKER_LOADER is None or _WORKER_OUTPUT is None:
        raise RuntimeError("materialization worker is uninitialized")
    record = _WORKER_RECORDS[episode_id]
    filename = f"{episode_id}.json"
    teacher = int(record["teacher_player_index"])
    decisions = tuple(
        decision
        for decision in _WORKER_LOADER._iter_episode(filename)  # noqa: SLF001
        if decision.agent_index == teacher
    )
    expected_requests = int(record["teacher_active_requests"])
    if len(decisions) != expected_requests:
        raise BCMaterializeError(
            f"teacher decision count differs for {episode_id}: "
            f"expected {expected_requests}, observed {len(decisions)}"
        )
    payload = build_episode_payload(
        episode_id=episode_id,
        teacher_player_index=teacher,
        split=str(record["split"]),
        teacher_result=str(record["teacher_result"]),
        teacher_team_name=str(record["teacher_team_name"]),
        source_replay_sha256=str(record["sha256"]),
        decisions=decisions,
    )
    target = _WORKER_OUTPUT / "episodes" / f"{episode_id}.pt"
    receipt = save_episode_payload(target, payload)
    return {
        "episode_id": episode_id,
        "split": record["split"],
        "teacher_player_index": teacher,
        "teacher_result": record["teacher_result"],
        "teacher_team_name": record["teacher_team_name"],
        "source_replay_sha256": record["sha256"],
        "source_min_score": record.get("source_min_score"),
        "source_avg_score": record.get("source_avg_score"),
        "policy_targets": int(payload["policy_targets"]),
        "recurrent_decisions": len(decisions),
        "path": f"episodes/{episode_id}.pt",
        "bytes": int(receipt["bytes"]),
        "sha256": str(receipt["sha256"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize projected BC episodes once for fast GPU reuse")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--expected-bundle-sha256")
    parser.add_argument("--card-table", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=max(1, min(16, os.cpu_count() or 1)))
    parser.add_argument("--record-id", default="bc-materialized-v1")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    if args.workers <= 0 or (args.limit is not None and args.limit <= 0):
        raise BCMaterializeError("workers and optional limit must be positive")
    if args.output_dir.exists():
        raise BCMaterializeError(f"materialized output already exists: {args.output_dir}")

    manifest, all_records = _load_bundle_manifest(args.bundle, args.expected_bundle_sha256)
    selected = [record for record in all_records if record["split"] in {"train", "validation"}]
    test_records = [record for record in all_records if record["split"] == "test"]
    selected.sort(key=lambda record: int(record["episode_id"]))
    if args.limit is not None:
        selected = selected[: args.limit]
    if not selected:
        raise BCMaterializeError("materialization selected no train/validation episodes")

    card_table = load_card_table(args.card_table)
    started = time.perf_counter()
    staging_root = Path(tempfile.mkdtemp(prefix="kptcg-bc-materialize-"))
    episodes_dir = staging_root / "episodes"
    _extract_train_validation(args.bundle, selected, episodes_dir)
    plan = build_semantic_loader_plan(
        [
            {"episode_id": int(record["episode_id"]), "bytes": int(record["bytes"])}
            for record in selected
        ]
    )
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / "episodes").mkdir()

    receipts: list[dict[str, Any]] = []
    try:
        if args.workers == 1:
            _worker_init(
                plan,
                str(episodes_dir),
                card_table.card_data_sha256,
                selected,
                str(args.output_dir),
            )
            for record in selected:
                receipts.append(_materialize_one(int(record["episode_id"])))
        else:
            with ProcessPoolExecutor(
                max_workers=args.workers,
                initializer=_worker_init,
                initargs=(
                    plan,
                    str(episodes_dir),
                    card_table.card_data_sha256,
                    selected,
                    str(args.output_dir),
                ),
            ) as pool:
                futures = {
                    pool.submit(_materialize_one, int(record["episode_id"])): int(record["episode_id"])
                    for record in selected
                }
                for completed, future in enumerate(as_completed(futures), start=1):
                    receipts.append(future.result())
                    if completed % 100 == 0 or completed == len(futures):
                        print(
                            json.dumps(
                                {
                                    "event": "materialization_progress",
                                    "completed": completed,
                                    "total": len(futures),
                                },
                                sort_keys=True,
                            ),
                            flush=True,
                        )
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)

    receipts.sort(key=lambda row: int(row["episode_id"]))
    split_counts = Counter(str(row["split"]) for row in receipts)
    result_counts = Counter(str(row["teacher_result"]) for row in receipts)
    output_manifest: dict[str, Any] = {
        "schema_version": 1,
        "record_id": args.record_id,
        "status": "PASS_MATERIALIZED_BC_READY",
        "source": {
            "bundle_record_id": manifest.get("record_id"),
            "bundle_sha256": sha256_file(args.bundle),
            "bundle_manifest_sha256": manifest.get("manifest_sha256"),
            "source_episode_count": len(all_records),
            "source_test_episodes": len(test_records),
            "test_episode_bodies_read": 0,
        },
        "model_schema_sha256": model_schema_sha256(),
        "card_data_sha256": card_table.card_data_sha256,
        "workers": args.workers,
        "summary": {
            "episodes": len(receipts),
            "split_counts": dict(sorted(split_counts.items())),
            "teacher_result_counts": dict(sorted(result_counts.items())),
            "policy_targets": sum(int(row["policy_targets"]) for row in receipts),
            "recurrent_decisions": sum(int(row["recurrent_decisions"]) for row in receipts),
            "materialized_bytes": sum(int(row["bytes"]) for row in receipts),
            "elapsed_seconds": time.perf_counter() - started,
        },
        "records": receipts,
    }
    output_manifest["manifest_sha256"] = _canonical_sha256(output_manifest)
    manifest_path = args.output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(output_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(output_manifest["summary"], sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
