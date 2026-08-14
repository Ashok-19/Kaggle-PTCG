from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ptcg_rl.bc.source import (  # noqa: E402
    BCSourceError,
    ReplayEpisodeRecord,
    ReplayQualityRecord,
    archive_inventory,
    load_archive_manifest,
    load_daily_index,
    quality_select_archive_entries,
    replay_record_from_bytes,
    sha256_file,
)


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def quality_key(item: tuple[ReplayQualityRecord, ReplayEpisodeRecord]) -> tuple[float, float, float, int]:
    quality, record = item
    return (-quality.min_score, -quality.avg_score, -quality.sum_score, record.episode_id)


def locate_archive(root: Path, day: str) -> Path:
    candidates = sorted((root / day / "archive").glob("*.zip"))
    if len(candidates) != 1:
        raise BCSourceError(f"expected exactly one cached archive for {day}, found {len(candidates)}")
    return candidates[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build recent high-quality BC replay bundle")
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--days", nargs="+", required=True)
    parser.add_argument("--minimum-min-score", type=float, default=1100.0)
    parser.add_argument("--candidate-per-day", type=int, default=256)
    parser.add_argument("--quota-per-day", type=int, default=128)
    parser.add_argument("--team-cap", type=int, default=32)
    parser.add_argument("--deck-cap", type=int, default=40)
    parser.add_argument("--minimum-selected", type=int, default=480)
    parser.add_argument("--module-version", default="1.32.6")
    parser.add_argument("--split-seed", type=int, default=20260814)
    parser.add_argument("--record-id", default="bc-recent-hq-v1")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if any(value <= 0 for value in (
        args.candidate_per_day,
        args.quota_per_day,
        args.team_cap,
        args.deck_cap,
        args.minimum_selected,
    )):
        raise BCSourceError("selection counts and caps must be positive")
    if len(args.days) != len(set(args.days)):
        raise BCSourceError("days contain duplicates")

    sources = {item.date: item for item in load_daily_index(args.index)}
    if any(day not in sources for day in args.days):
        missing = sorted(day for day in args.days if day not in sources)
        raise BCSourceError(f"requested days are absent from official index: {missing}")

    archives: dict[str, Path] = {}
    inventories: dict[str, dict[int, Any]] = {}
    candidates_by_day: dict[str, list[tuple[ReplayQualityRecord, ReplayEpisodeRecord]]] = {}
    rejection_counts: Counter[str] = Counter()
    source_reports: list[dict[str, Any]] = []

    for day in args.days:
        archive = locate_archive(args.archive_root, day)
        archives[day] = archive
        entries = archive_inventory(archive)
        source = sources[day]
        if len(entries) != source.episode_count:
            raise BCSourceError(f"archive episode count differs from official index for {day}")
        if sum(item.bytes for item in entries) != source.total_bytes:
            raise BCSourceError(f"archive uncompressed bytes differ from official index for {day}")
        entry_by_id = {item.episode_id: item for item in entries}
        inventories[day] = entry_by_id
        quality = load_archive_manifest(archive)
        eligible_count = sum(item.min_score >= args.minimum_min_score for item in quality)
        if eligible_count < args.quota_per_day:
            raise BCSourceError(
                f"{day} has only {eligible_count} episodes at min_score >= {args.minimum_min_score}"
            )
        candidate_count = min(args.candidate_per_day, eligible_count)
        selected_entries = quality_select_archive_entries(
            entries,
            quality,
            count=candidate_count,
            minimum_min_score=args.minimum_min_score,
        )
        quality_by_id = {item.episode_id: item for item in quality}
        parsed: list[tuple[ReplayQualityRecord, ReplayEpisodeRecord]] = []
        with zipfile.ZipFile(archive) as handle:
            for entry in selected_entries:
                raw = handle.read(entry.name)
                try:
                    record = replay_record_from_bytes(
                        raw,
                        expected_episode_id=entry.episode_id,
                        date=day,
                        relative_path=entry.name,
                        split_seed=args.split_seed,
                    )
                except BCSourceError as error:
                    rejection_counts[type(error).__name__ + ":" + str(error).split(":")[0]] += 1
                    continue
                if record.module_version != args.module_version:
                    rejection_counts[f"module:{record.module_version}"] += 1
                    continue
                parsed.append((quality_by_id[entry.episode_id], record))
        parsed.sort(key=quality_key)
        candidates_by_day[day] = parsed
        source_reports.append(
            {
                "date": day,
                "dataset_slug": source.dataset_slug,
                "archive_sha256": sha256_file(archive),
                "archive_compressed_bytes": archive.stat().st_size,
                "official_episodes": source.episode_count,
                "official_uncompressed_bytes": source.total_bytes,
                "eligible_min_score": eligible_count,
                "candidate_count": candidate_count,
                "qualified_candidates": len(parsed),
            }
        )

    team_counts: Counter[str] = Counter()
    deck_counts: Counter[str] = Counter()
    selected_by_day: dict[str, list[tuple[ReplayQualityRecord, ReplayEpisodeRecord]]] = {}
    for day in reversed(args.days):
        chosen: list[tuple[ReplayQualityRecord, ReplayEpisodeRecord]] = []
        for quality, record in candidates_by_day[day]:
            if team_counts[record.teacher_team_name] >= args.team_cap:
                continue
            if deck_counts[record.teacher_deck_sha256] >= args.deck_cap:
                continue
            chosen.append((quality, record))
            team_counts[record.teacher_team_name] += 1
            deck_counts[record.teacher_deck_sha256] += 1
            if len(chosen) == args.quota_per_day:
                break
        selected_by_day[day] = chosen

    selected = [item for day in args.days for item in selected_by_day[day]]
    if len(selected) < args.minimum_selected:
        raise BCSourceError(
            f"diversity-capped corpus selected {len(selected)} episodes; minimum is {args.minimum_selected}"
        )

    manifest_records: list[dict[str, Any]] = []
    for quality, record in sorted(selected, key=lambda item: (item[1].date, item[1].episode_id)):
        row = asdict(record)
        row.update(
            {
                "source_avg_score": quality.avg_score,
                "source_min_score": quality.min_score,
                "source_sum_score": quality.sum_score,
                "teacher_sample_weight": 1.0,
                "teacher_policy_source": "winning_player",
            }
        )
        manifest_records.append(row)

    split_counts = Counter(record["split"] for record in manifest_records)
    module_counts = Counter(record["module_version"] for record in manifest_records)
    opponent_decks = Counter(record["opponent_deck_sha256"] for record in manifest_records)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "record_id": args.record_id,
        "status": "PASS_RECENT_HIGH_QUALITY_CORPUS_READY",
        "official_index_sha256": sha256_file(args.index),
        "selection": {
            "days": args.days,
            "minimum_min_score": args.minimum_min_score,
            "candidate_per_day": args.candidate_per_day,
            "quota_per_day": args.quota_per_day,
            "team_cap": args.team_cap,
            "winner_deck_cap": args.deck_cap,
            "minimum_selected": args.minimum_selected,
            "required_module_version": args.module_version,
            "split_seed": args.split_seed,
            "winner_only_labels": True,
            "newest_days_receive_cap_priority": True,
        },
        "summary": {
            "episodes": len(manifest_records),
            "teacher_active_requests": sum(int(item["teacher_active_requests"]) for item in manifest_records),
            "bytes": sum(int(item["bytes"]) for item in manifest_records),
            "split_counts": dict(sorted(split_counts.items())),
            "winning_teams": len(team_counts),
            "winning_decks": len(deck_counts),
            "opponent_decks": len(opponent_decks),
            "module_counts": dict(sorted(module_counts.items())),
            "minimum_selected_min_score": min(float(item["source_min_score"]) for item in manifest_records),
            "mean_selected_min_score": sum(float(item["source_min_score"]) for item in manifest_records) / len(manifest_records),
            "per_day": {day: len(selected_by_day[day]) for day in args.days},
            "rejections": sum(rejection_counts.values()),
        },
        "source_archives": source_reports,
        "rejection_counts": dict(sorted(rejection_counts.items())),
        "records": manifest_records,
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    manifest_raw = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")

    if args.bundle.exists() and not args.force:
        raise BCSourceError(f"bundle already exists: {args.bundle}")
    args.bundle.parent.mkdir(parents=True, exist_ok=True)
    partial = args.bundle.with_suffix(args.bundle.suffix + ".partial")
    partial.unlink(missing_ok=True)
    selected_ids = {int(record["episode_id"]): record for record in manifest_records}
    with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as output:
        output.writestr("manifest.json", manifest_raw)
        for day in args.days:
            day_ids = sorted(
                int(record["episode_id"])
                for record in manifest_records
                if record["date"] == day
            )
            with zipfile.ZipFile(archives[day]) as source:
                for episode_id in day_ids:
                    entry = inventories[day][episode_id]
                    raw = source.read(entry.name)
                    record = selected_ids[episode_id]
                    if len(raw) != int(record["bytes"]) or hashlib.sha256(raw).hexdigest() != record["sha256"]:
                        raise BCSourceError(f"selected replay changed while bundling: {episode_id}")
                    output.writestr(f"episodes/{episode_id}.json", raw)
    partial.replace(args.bundle)

    report = {
        "schema_version": 1,
        "record_id": args.record_id + "-build-report",
        "status": "PASS",
        "manifest_sha256": manifest["manifest_sha256"],
        "bundle_path": args.bundle.as_posix(),
        "bundle_sha256": sha256_file(args.bundle),
        "bundle_bytes": args.bundle.stat().st_size,
        "summary": manifest["summary"],
        "top_winning_teams": team_counts.most_common(12),
        "top_winning_decks": deck_counts.most_common(12),
        "top_opponent_decks": opponent_decks.most_common(12),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    report_partial = args.report.with_suffix(args.report.suffix + ".partial")
    report_partial.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_partial.replace(args.report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
