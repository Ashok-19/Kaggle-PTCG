from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ptcg_rl.replay.semantic_loader import SemanticReplayLoader  # noqa: E402

MANIFEST = ROOT / "reports/artifacts/e01-approved-replay-corpus-manifest-v1.json"
OUTPUT = ROOT / "reports/artifacts/e01-approved-replay-policy-loss-recount-v1.json"
CARD_DATA_SHA256 = "a0ea63cf7adcb65d35436ce0eb390de6e2e35654a7c67c065a45f4abaa00f373"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def semantic_loader_plan(records: list[dict[str, Any]]) -> dict[str, Any]:
    selected = [
        {
            "remote_filename": f"{int(record['episode_id'])}.json",
            "declared_bytes": int(record["bytes"]),
        }
        for record in sorted(records, key=lambda item: int(item["episode_id"]))
    ]
    sizes = [item["declared_bytes"] for item in selected]
    plan: dict[str, Any] = {
        "schema_version": 1,
        "planner_version": "e01-policy-loss-recount-v1",
        "created_at_utc": "2026-08-04T10:00:34Z",
        "selection_profile": {
            "caps": {
                "max_files": len(selected),
                "max_total_bytes": sum(sizes),
                "max_file_bytes": max(sizes),
            }
        },
        "summary": {
            "selected_files": len(selected),
            "selected_bytes": sum(sizes),
        },
        "selected_items": selected,
        "rows": [],
    }
    payload = dict(plan)
    payload.pop("created_at_utc")
    plan["plan_sha256"] = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return plan


def build_report() -> dict[str, Any]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    records = manifest["qualified_training_corpus"]["episode_records"]
    by_id = {int(record["episode_id"]): record for record in records}
    plan = semantic_loader_plan(records)
    per_episode: dict[int, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory(prefix="kptcg-e01-recount-") as temporary:
        directory = Path(temporary) / "episodes"
        directory.mkdir()
        for record in records:
            source = ROOT / record["path"]
            raw = source.read_bytes()
            if len(raw) != int(record["bytes"]) or hashlib.sha256(raw).hexdigest() != record["sha256"]:
                raise ValueError(f"frozen replay identity differs for episode {record['episode_id']}")
            destination = directory / f"{record['episode_id']}.json"
            try:
                os.link(source, destination)
            except OSError:
                destination.write_bytes(raw)
        loader = SemanticReplayLoader(
            plan,
            directory,
            card_data_sha256=CARD_DATA_SHA256,
        )
        for decision in loader:
            episode_id = int(decision.episode_id)
            record = by_id[episode_id]
            if decision.agent_index != record["teacher_player_index"]:
                continue
            counts = per_episode.setdefault(
                episode_id,
                {
                    "episode_id": episode_id,
                    "teacher_key": record["teacher_key"],
                    "stratum": record["stratum"],
                    "split": record["split"],
                    "recorded_teacher_active_requests": int(
                        record.get("teacher_active_requests", record["meaningful_teacher_decisions"])
                    ),
                    "teacher_active_requests": 0,
                    "forced_teacher_requests": 0,
                    "policy_loss_targets": 0,
                    "stop_targets": 0,
                    "ordered_requests": 0,
                },
            )
            forced = bool(decision.request.has_only_one_outcome)
            counts["teacher_active_requests"] += 1
            counts["forced_teacher_requests"] += int(forced)
            counts["policy_loss_targets"] += int(not forced)
            counts["stop_targets"] += int(decision.action.stopped_early)
            counts["ordered_requests"] += int(
                decision.request.ordering == "ORDERED"
            )

    if len(per_episode) != len(records):
        raise ValueError("recount episode coverage differs from frozen corpus")
    aggregate: Counter[str] = Counter()
    split: dict[str, Counter[str]] = {
        name: Counter() for name in ("train", "validation", "test")
    }
    teacher: dict[str, Counter[str]] = {
        name: Counter() for name in ("flg", "dries")
    }
    mismatch_episodes = 0
    for episode_id in sorted(per_episode):
        item = per_episode[episode_id]
        item["recorded_minus_recounted_active"] = (
            item["recorded_teacher_active_requests"]
            - item["teacher_active_requests"]
        )
        item["active_minus_policy_loss"] = (
            item["teacher_active_requests"] - item["policy_loss_targets"]
        )
        mismatch_episodes += int(item["recorded_minus_recounted_active"] != 0)
        for key in (
            "recorded_teacher_active_requests",
            "teacher_active_requests",
            "forced_teacher_requests",
            "policy_loss_targets",
            "stop_targets",
            "ordered_requests",
        ):
            aggregate[key] += int(item[key])
            split[item["split"]][key] += int(item[key])
            teacher[item["teacher_key"]][key] += int(item[key])

    report: dict[str, Any] = {
        "schema_version": 1,
        "record_id": "e01-approved-replay-policy-loss-recount-v1",
        "source_path": "reports/artifacts/e01-approved-replay-policy-loss-recount-v1.json",
        "created_at_utc": "2026-08-04T10:00:34Z",
        "producer": "scripts/e01_policy_loss_recount.py",
        "status": "PASS",
        "decision": "DISTINGUISH_ACTIVE_TEACHER_REQUESTS_FROM_FORCED_CALLS_AND_POLICY_LOSS_TARGETS",
        "inputs": {
            "corpus_manifest": {
                "path": str(MANIFEST.relative_to(ROOT)),
                "sha256": sha256_file(MANIFEST),
                "manifest_sha256": manifest["manifest_sha256"],
            },
            "card_data_sha256": CARD_DATA_SHA256,
            "semantic_loader": {
                "path": "src/ptcg_rl/replay/semantic_loader.py",
                "sha256": sha256_file(
                    ROOT / "src/ptcg_rl/replay/semantic_loader.py"
                ),
            },
        },
        "coverage": {
            "episodes": len(per_episode),
            "recorded_active_request_mismatch_episodes": mismatch_episodes,
            **dict(aggregate),
        },
        "by_split": {
            name: dict(values) for name, values in split.items()
        },
        "by_teacher": {
            name: dict(values) for name, values in teacher.items()
        },
        "episodes": [per_episode[key] for key in sorted(per_episode)],
        "semantics": {
            "teacher_active_requests": "Every lag-aligned active teacher selection request, including deterministic forced calls.",
            "forced_teacher_requests": "Requests with exactly one complete legal outcome; recurrence advances but no policy loss is permitted.",
            "policy_loss_targets": "Teacher active requests excluding forced calls; these are the only BC policy-loss targets.",
            "raw_replays_exported": False,
            "raw_observations_exported": False,
            "raw_options_exported": False,
            "raw_actions_exported": False,
            "training_labels_exported": False,
            "optimizer_steps": 0,
        },
        "authorization": {
            "replay_transfer": False,
            "label_generation": False,
            "optimizer_steps": False,
            "external_compute": False,
            "production_training": False,
            "submission": False,
        },
    }
    report["review_sha256"] = hashlib.sha256(
        canonical_json_bytes(report)
    ).hexdigest()
    return report


def main() -> int:
    report = build_report()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(OUTPUT.suffix + ".partial")
    temporary.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(OUTPUT)
    print(json.dumps(report["coverage"], indent=2, sort_keys=True))
    print(json.dumps(report["by_split"], indent=2, sort_keys=True))
    print(json.dumps(report["by_teacher"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
