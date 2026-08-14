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
    ReplayArchiveEntry,
    ReplayEpisodeRecord,
    ReplayQualityRecord,
    archive_inventory,
    load_archive_manifest,
    load_daily_index,
    replay_record_from_bytes,
    scan_replay_prefix,
    sha256_file,
)

PREFIX_BYTES = 65_536


def canonical_sha256(value: Any) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def locate_archive(root: Path, day: str) -> Path:
    candidates = sorted((root / day / "archive").glob("*.zip"))
    if len(candidates) != 1:
        raise BCSourceError(f"expected exactly one cached archive for {day}, found {len(candidates)}")
    return candidates[0]


def deterministic_fraction(seed: int, episode_id: int, teacher_player_index: int) -> float:
    digest = hashlib.sha256(
        f"bc-specialist-loss|{seed}|{episode_id}|{teacher_player_index}".encode("ascii")
    ).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64)


def choose_teacher(
    *,
    episode_id: int,
    winner_player_index: int | None,
    deck_sha256: tuple[str, str],
    target_deck_sha256: str,
    min_score: float,
    winner_min_score: float,
    loser_min_score: float,
    loser_keep_fraction: float,
    seed: int,
) -> tuple[int, str] | None:
    target_seats = [seat for seat in (0, 1) if deck_sha256[seat] == target_deck_sha256]
    if not target_seats or winner_player_index not in (0, 1):
        return None
    if winner_player_index in target_seats and min_score >= winner_min_score:
        return winner_player_index, "win"
    loser = 1 - winner_player_index
    if (
        loser in target_seats
        and min_score >= loser_min_score
        and deterministic_fraction(seed, episode_id, loser) < loser_keep_fraction
    ):
        return loser, "loss"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a recent exact-deck specialist BC replay bundle")
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--days", nargs="+", required=True)
    parser.add_argument("--target-deck-sha256", required=True)
    parser.add_argument("--winner-min-score", type=float, default=950.0)
    parser.add_argument("--loser-min-score", type=float, default=1050.0)
    parser.add_argument("--loser-keep-fraction", type=float, default=0.5)
    parser.add_argument("--module-version", default="1.32.6")
    parser.add_argument("--split-seed", type=int, default=20260814)
    parser.add_argument("--selection-seed", type=int, default=20260814)
    parser.add_argument("--minimum-selected", type=int, default=900)
    parser.add_argument("--record-id", default="bc-current-lucario-specialist-v1")
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if len(args.target_deck_sha256) != 64:
        raise BCSourceError("target deck SHA-256 must contain 64 hexadecimal characters")
    try:
        int(args.target_deck_sha256, 16)
    except ValueError as error:
        raise BCSourceError("target deck SHA-256 is not hexadecimal") from error
    if args.winner_min_score <= 0 or args.loser_min_score <= 0:
        raise BCSourceError("score floors must be positive")
    if not 0.0 <= args.loser_keep_fraction <= 1.0:
        raise BCSourceError("loser keep fraction must be between zero and one")
    if args.minimum_selected <= 0:
        raise BCSourceError("minimum selected count must be positive")
    if len(args.days) != len(set(args.days)):
        raise BCSourceError("days contain duplicates")

    sources = {item.date: item for item in load_daily_index(args.index)}
    missing_days = sorted(day for day in args.days if day not in sources)
    if missing_days:
        raise BCSourceError(f"requested days are absent from official index: {missing_days}")

    archives: dict[str, Path] = {}
    inventories: dict[str, dict[int, ReplayArchiveEntry]] = {}
    selected_specs: list[tuple[str, ReplayArchiveEntry, ReplayQualityRecord, int, str]] = []
    source_reports: list[dict[str, Any]] = []
    discovery_rejections: Counter[str] = Counter()

    discovery_floor = min(args.winner_min_score, args.loser_min_score)
    for day in args.days:
        source = sources[day]
        archive_path = locate_archive(args.archive_root, day)
        archives[day] = archive_path
        entries = archive_inventory(archive_path)
        if len(entries) != source.episode_count:
            raise BCSourceError(f"archive episode count differs from official index for {day}")
        if sum(item.bytes for item in entries) != source.total_bytes:
            raise BCSourceError(f"archive uncompressed bytes differ from official index for {day}")
        entry_by_id = {item.episode_id: item for item in entries}
        inventories[day] = entry_by_id
        quality = load_archive_manifest(archive_path)
        quality_by_id = {item.episode_id: item for item in quality}
        if set(entry_by_id) != set(quality_by_id):
            raise BCSourceError(f"archive/quality episode sets differ for {day}")

        day_selected = 0
        day_winners = 0
        day_losers = 0
        scanned = 0
        with zipfile.ZipFile(archive_path) as archive:
            for entry in entries:
                score = quality_by_id[entry.episode_id]
                if score.min_score < discovery_floor:
                    continue
                scanned += 1
                try:
                    with archive.open(entry.name, "r") as source_handle:
                        prefix = source_handle.read(PREFIX_BYTES)
                    discovered = scan_replay_prefix(prefix)
                except BCSourceError as error:
                    discovery_rejections[str(error).split(":")[0]] += 1
                    continue
                if discovered.module_version != args.module_version:
                    discovery_rejections[f"module:{discovered.module_version}"] += 1
                    continue
                choice = choose_teacher(
                    episode_id=entry.episode_id,
                    winner_player_index=discovered.winner_player_index,
                    deck_sha256=discovered.deck_sha256,
                    target_deck_sha256=args.target_deck_sha256,
                    min_score=score.min_score,
                    winner_min_score=args.winner_min_score,
                    loser_min_score=args.loser_min_score,
                    loser_keep_fraction=args.loser_keep_fraction,
                    seed=args.selection_seed,
                )
                if choice is None:
                    continue
                teacher_player_index, teacher_result = choice
                selected_specs.append((day, entry, score, teacher_player_index, teacher_result))
                day_selected += 1
                day_winners += int(teacher_result == "win")
                day_losers += int(teacher_result == "loss")
        source_reports.append(
            {
                "date": day,
                "dataset_slug": source.dataset_slug,
                "archive_sha256": sha256_file(archive_path),
                "archive_compressed_bytes": archive_path.stat().st_size,
                "official_episodes": source.episode_count,
                "official_uncompressed_bytes": source.total_bytes,
                "prefix_scanned": scanned,
                "selected_before_full_parse": day_selected,
                "selected_winners_before_full_parse": day_winners,
                "selected_losers_before_full_parse": day_losers,
            }
        )

    if len(selected_specs) < args.minimum_selected:
        raise BCSourceError(
            f"specialist discovery selected {len(selected_specs)} trajectories; minimum is {args.minimum_selected}"
        )

    full_parse_rejections: Counter[str] = Counter()
    selected: list[tuple[ReplayQualityRecord, ReplayEpisodeRecord]] = []
    specs_by_day: dict[str, list[tuple[ReplayArchiveEntry, ReplayQualityRecord, int, str]]] = {
        day: [] for day in args.days
    }
    for day, entry, quality, teacher, result in selected_specs:
        specs_by_day[day].append((entry, quality, teacher, result))

    for day in args.days:
        with zipfile.ZipFile(archives[day]) as archive:
            for entry, quality, teacher, expected_result in sorted(
                specs_by_day[day], key=lambda item: item[0].episode_id
            ):
                raw = archive.read(entry.name)
                try:
                    record = replay_record_from_bytes(
                        raw,
                        expected_episode_id=entry.episode_id,
                        date=day,
                        relative_path=entry.name,
                        split_seed=args.split_seed,
                        teacher_player_index=teacher,
                    )
                except BCSourceError as error:
                    full_parse_rejections[str(error).split(":")[0]] += 1
                    continue
                if record.module_version != args.module_version:
                    full_parse_rejections[f"module:{record.module_version}"] += 1
                    continue
                if record.teacher_deck_sha256 != args.target_deck_sha256:
                    raise BCSourceError(f"full parser target deck differs for episode {entry.episode_id}")
                if record.teacher_result != expected_result:
                    raise BCSourceError(f"teacher result changed for episode {entry.episode_id}")
                selected.append((quality, record))

    if len(selected) < args.minimum_selected:
        raise BCSourceError(
            f"specialist full parse retained {len(selected)} trajectories; minimum is {args.minimum_selected}"
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
                "teacher_policy_source": (
                    "current_deck_winning_player"
                    if record.teacher_result == "win"
                    else "current_deck_strong_losing_player_downsampled"
                ),
            }
        )
        manifest_records.append(row)

    split_counts = Counter(row["split"] for row in manifest_records)
    result_counts = Counter(row["teacher_result"] for row in manifest_records)
    team_counts = Counter(row["teacher_team_name"] for row in manifest_records)
    opponent_decks = Counter(row["opponent_deck_sha256"] for row in manifest_records)
    per_day = Counter(row["date"] for row in manifest_records)
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "record_id": args.record_id,
        "status": "PASS_RECENT_DECK_SPECIALIST_CORPUS_READY",
        "official_index_sha256": sha256_file(args.index),
        "selection": {
            "days": args.days,
            "target_deck_sha256": args.target_deck_sha256,
            "winner_min_score": args.winner_min_score,
            "loser_min_score": args.loser_min_score,
            "loser_keep_fraction": args.loser_keep_fraction,
            "loser_keep_rule": "sha256-first-u64 deterministic fraction",
            "required_module_version": args.module_version,
            "split_seed": args.split_seed,
            "selection_seed": args.selection_seed,
            "minimum_selected": args.minimum_selected,
            "prefix_bytes": PREFIX_BYTES,
        },
        "summary": {
            "episodes": len(manifest_records),
            "teacher_active_requests": sum(int(row["teacher_active_requests"]) for row in manifest_records),
            "bytes": sum(int(row["bytes"]) for row in manifest_records),
            "split_counts": dict(sorted(split_counts.items())),
            "teacher_result_counts": dict(sorted(result_counts.items())),
            "teacher_teams": len(team_counts),
            "opponent_decks": len(opponent_decks),
            "module_counts": dict(
                sorted(Counter(row["module_version"] for row in manifest_records).items())
            ),
            "minimum_selected_min_score": min(float(row["source_min_score"]) for row in manifest_records),
            "mean_selected_min_score": sum(float(row["source_min_score"]) for row in manifest_records)
            / len(manifest_records),
            "per_day": dict(sorted(per_day.items())),
            "discovery_rejections": sum(discovery_rejections.values()),
            "full_parse_rejections": sum(full_parse_rejections.values()),
        },
        "source_archives": source_reports,
        "discovery_rejection_counts": dict(sorted(discovery_rejections.items())),
        "full_parse_rejection_counts": dict(sorted(full_parse_rejections.items())),
        "records": manifest_records,
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    manifest_raw = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")

    if args.bundle.exists() and not args.force:
        raise BCSourceError(f"bundle already exists: {args.bundle}")
    args.bundle.parent.mkdir(parents=True, exist_ok=True)
    partial = args.bundle.with_suffix(args.bundle.suffix + ".partial")
    partial.unlink(missing_ok=True)
    record_by_id = {int(row["episode_id"]): row for row in manifest_records}
    if len(record_by_id) != len(manifest_records):
        raise BCSourceError("specialist corpus contains duplicate episode IDs")
    with zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as output:
        output.writestr("manifest.json", manifest_raw)
        for day in args.days:
            episode_ids = sorted(
                int(row["episode_id"])
                for row in manifest_records
                if row["date"] == day
            )
            with zipfile.ZipFile(archives[day]) as source_archive:
                for episode_id in episode_ids:
                    entry = inventories[day][episode_id]
                    raw = source_archive.read(entry.name)
                    record = record_by_id[episode_id]
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
        "top_teacher_teams": team_counts.most_common(16),
        "top_opponent_decks": opponent_decks.most_common(16),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    report_partial = args.report.with_suffix(args.report.suffix + ".partial")
    report_partial.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report_partial.replace(args.report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
